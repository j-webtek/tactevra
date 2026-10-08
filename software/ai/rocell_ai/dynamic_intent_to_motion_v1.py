"""Create fresh zero-authority C03 motion plans from bounded keyboard text."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .c03_arm_route_reconciliation_v1 import canonical_hash, file_hash, load_strict_json
from .c03_exact_route_reconstruction_v1 import run_c03_exact_route
from .c03_exact_route_reconstruction_v1_1 import _materialize
from .c03_exact_route_reconstruction_v1_9 import (
    _rebind_route_fixtures,
    _rebind_virtual_profile,
    load_fixture as load_pose_bound_fixture,
)
from .end_to_end_typing_twin import compile_virtual_us_sticky_keys


SCHEMA = "tactevra.dynamic_intent_to_simulated_motion.v1"
STATUS = "PASS_DYNAMIC_INTENT_TO_SIMULATED_IK_PLAN_RETAIN_COLLISION_BLOCKERS"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
MAX_COMPILED_ACTIONS = 12
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_FIELDS = {
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "hardware_writes": 0,
    "physical_movements": 0,
    "physical_authority": False,
}


class DynamicIntentToMotionV1Error(ValueError):
    """The bounded dynamic intent pipeline failed closed."""


def compile_bounded_intent(
    text: str,
    covered_target_ids: Iterable[str],
    *,
    maximum_actions: int = MAX_COMPILED_ACTIONS,
) -> list[str]:
    """Compile exact text and reject any request outside the admitted pose set."""

    if not isinstance(text, str) or not text:
        raise DynamicIntentToMotionV1Error("intent text must be non-empty")
    if isinstance(maximum_actions, bool) or not isinstance(maximum_actions, int):
        raise DynamicIntentToMotionV1Error("maximum actions must be an integer")
    if maximum_actions < 1 or maximum_actions > MAX_COMPILED_ACTIONS:
        raise DynamicIntentToMotionV1Error("maximum actions exceed the frozen bound")
    try:
        targets = list(compile_virtual_us_sticky_keys(text))
    except (KeyError, ValueError) as exc:
        raise DynamicIntentToMotionV1Error("intent contains unsupported text") from exc
    if not targets or len(targets) > maximum_actions:
        raise DynamicIntentToMotionV1Error(
            f"compiled intent exceeds {maximum_actions} actions"
        )
    covered = set(covered_target_ids)
    missing = sorted(set(targets) - covered)
    if missing:
        raise DynamicIntentToMotionV1Error(
            "compiled targets lack admitted poses: " + ", ".join(missing)
        )
    return targets


def derive_dynamic_route_fixture(
    predecessor: Mapping[str, Any],
    text: str,
    covered_target_ids: Iterable[str],
    *,
    maximum_actions: int = MAX_COMPILED_ACTIONS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Change only the route identity and exact ordered semantic targets."""

    derived = deepcopy(dict(predecessor))
    claimed = derived.pop("fixture_sha256", None)
    if claimed != canonical_hash(derived):
        raise DynamicIntentToMotionV1Error("predecessor fixture hash changed")
    targets = compile_bounded_intent(
        text, covered_target_ids, maximum_actions=maximum_actions
    )
    before = deepcopy(derived)
    token = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    route = derived.get("route")
    if not isinstance(route, dict):
        raise DynamicIntentToMotionV1Error("predecessor route is absent")
    route.update({
        "text": text,
        "ordered_targets": targets,
        "batch_id": f"c03-dynamic-{token}-batch-v1",
        "request_id": f"c03-dynamic-{token}-request-v1",
        "config_id": f"c03-dynamic-{token}-config-v1",
        "trajectory_policy_id": f"c03-dynamic-{token}-quintic-v1",
    })
    derived["limitations"] = [
        *derived.get("limitations", []),
        "This derived fixture covers only the exact bounded request recorded in route.text.",
    ]
    derived["fixture_sha256"] = canonical_hash(derived)
    changed_fields = [
        "route.text",
        "route.ordered_targets",
        "route.batch_id",
        "route.request_id",
        "route.config_id",
        "route.trajectory_policy_id",
        "limitations",
    ]
    receipt_core = {
        "schema": "tactevra.dynamic_route_fixture_derivation_receipt.v1",
        "source_fixture_sha256": claimed,
        "derived_fixture_sha256": derived["fixture_sha256"],
        "requested_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "ordered_target_ids": targets,
        "action_count": len(targets),
        "changed_semantic_fields": changed_fields,
        "unchanged_numerical_policy": before.get("decision_rules")
        == derived.get("decision_rules")
        and before.get("resource_limits") == derived.get("resource_limits")
        and before.get("c03_tool") == derived.get("c03_tool"),
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    if receipt_core["unchanged_numerical_policy"] is not True:
        raise DynamicIntentToMotionV1Error("dynamic route changed numerical policy")
    return derived, {
        **receipt_core,
        "receipt_sha256": canonical_hash(receipt_core),
    }


def _pose_targets(document: Mapping[str, Any], tool_sha256: str) -> set[str]:
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        raise DynamicIntentToMotionV1Error("pose family profiles are absent")
    matches = [
        item for item in profiles
        if isinstance(item, Mapping)
        and item.get("tool_configuration_sha256") == tool_sha256
    ]
    if len(matches) != 1:
        raise DynamicIntentToMotionV1Error("exact tool pose profile is ambiguous")
    poses = matches[0].get("pose_bundle", {}).get("poses")
    if not isinstance(poses, list):
        raise DynamicIntentToMotionV1Error("pose list is absent")
    result = {
        pose.get("target_id") for pose in poses if isinstance(pose, Mapping)
    }
    if None in result or len(result) != len(poses):
        raise DynamicIntentToMotionV1Error("pose target IDs are invalid or repeated")
    return {str(value) for value in result}


def _assert_zero_authority(document: Mapping[str, Any], label: str) -> None:
    for field, expected in _AUTHORITY_FIELDS.items():
        if document.get(field) != expected:
            raise DynamicIntentToMotionV1Error(
                f"{label} violates zero authority at {field}"
            )
    if document.get("controller_commands") != []:
        raise DynamicIntentToMotionV1Error(f"{label} contains controller commands")


def parse_dynamic_intent_to_motion_v1(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the aggregate campaign receipt."""

    if not isinstance(document, Mapping):
        raise DynamicIntentToMotionV1Error("result must be an object")
    claimed = document.get("receipt_sha256")
    if not isinstance(claimed, str) or _SHA256.fullmatch(claimed) is None:
        raise DynamicIntentToMotionV1Error("result receipt is invalid")
    unsigned = {key: value for key, value in document.items() if key != "receipt_sha256"}
    if canonical_hash(unsigned) != claimed:
        raise DynamicIntentToMotionV1Error("result receipt changed")
    if (
        document.get("schema") != SCHEMA
        or document.get("status") != STATUS
        or document.get("scope") != SCOPE
    ):
        raise DynamicIntentToMotionV1Error("result identity changed")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise DynamicIntentToMotionV1Error("result cases are absent")
    for case in cases:
        if not isinstance(case, Mapping):
            raise DynamicIntentToMotionV1Error("case is not an object")
        text = case.get("requested_text")
        targets = case.get("ordered_target_ids")
        if list(compile_virtual_us_sticky_keys(text)) != targets:
            raise DynamicIntentToMotionV1Error("case target order changed")
        route = case.get("route_result")
        if not isinstance(route, Mapping) or route.get("ordered_targets") != targets:
            raise DynamicIntentToMotionV1Error("nested route target order changed")
        if route.get("trajectory_sample_count") != route.get("ik_accepted_sample_count"):
            raise DynamicIntentToMotionV1Error("nested IK route is incomplete")
        _assert_zero_authority(route, "nested route")
    _assert_zero_authority(document, "aggregate result")
    if (
        document.get("collision_screen_executed") is not False
        or document.get("installed_collision_gate_cleared") is not False
    ):
        raise DynamicIntentToMotionV1Error("collision blocker changed")
    return dict(document)


def run_dynamic_intent_to_motion_v1(
    fixture_path: Path,
    intent_texts: list[str],
    *,
    workspace: Path,
    derived_workspace: Path,
) -> dict[str, Any]:
    """Materialize one coherent workspace and evaluate fresh bounded requests."""

    if not intent_texts:
        raise DynamicIntentToMotionV1Error("at least one intent is required")
    fixture = load_pose_bound_fixture(fixture_path, workspace)
    fixture = deepcopy(fixture)
    fixture["coherent_workspace"]["path"] = derived_workspace.as_posix()
    fixture["coherent_workspace"]["bundle_id"] = (
        "ROCELL-SIM-BUNDLE-RC03-C03-DYNAMIC-INTENT-V1"
    )
    fixture.pop("fixture_sha256")
    fixture["fixture_sha256"] = canonical_hash(fixture)
    derived, workspace_receipt = _materialize(fixture, workspace)
    profile_receipt, workspace_receipt = _rebind_virtual_profile(
        fixture, derived, workspace_receipt
    )
    base_rebinding = _rebind_route_fixtures(
        fixture, derived, profile_receipt["derived_virtual_profile_sha256"]
    )
    predecessor_path = derived / fixture["predecessor_fixture_path"]
    predecessor = load_strict_json(predecessor_path)

    pose_binding = fixture["bindings"]["regenerated_c03_pose_family"]
    pose_path = Path(pose_binding["path"])
    if file_hash(pose_path) != pose_binding["sha256"]:
        raise DynamicIntentToMotionV1Error("pose family bytes changed")
    covered = _pose_targets(
        load_strict_json(pose_path),
        predecessor["c03_tool"]["tool_configuration_sha256"],
    )

    cases: list[dict[str, Any]] = []
    for text in intent_texts:
        route_fixture, derivation = derive_dynamic_route_fixture(
            predecessor, text, covered
        )
        predecessor_path.write_text(
            json.dumps(route_fixture, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        route = run_c03_exact_route(predecessor_path, workspace=derived)
        _assert_zero_authority(route, "route result")
        if route.get("ordered_targets") != derivation["ordered_target_ids"]:
            raise DynamicIntentToMotionV1Error("route target order differs from intent")
        if route.get("decision") != "PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY":
            raise DynamicIntentToMotionV1Error("route did not pass IK and continuity")
        cases.append({
            "requested_text": text,
            "ordered_target_ids": derivation["ordered_target_ids"],
            "dynamic_fixture_derivation": derivation,
            "route_fixture_file_sha256": file_hash(predecessor_path),
            "route_result": route,
        })

    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "scope": SCOPE,
        "implementation_sha256": file_hash(Path(__file__)),
        "source_fixture_file_sha256": file_hash(fixture_path),
        "source_fixture_sha256": load_strict_json(fixture_path)["fixture_sha256"],
        "coherent_workspace_receipt": workspace_receipt,
        "virtual_profile_rebinding_receipt": profile_receipt,
        "base_fixture_rebinding_receipt": base_rebinding,
        "covered_target_count": len(covered),
        "maximum_compiled_actions": MAX_COMPILED_ACTIONS,
        "case_count": len(cases),
        "cases": cases,
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "terminal_blockers": [
            "INSTALLED_COLLISION_PROFILE_REQUIRED",
            "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
        ],
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    result = {**core, "receipt_sha256": canonical_hash(core)}
    parse_dynamic_intent_to_motion_v1(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile fresh keyboard text into a zero-authority C03 IK plan"
    )
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--derived-workspace", type=Path, required=True)
    parser.add_argument("--intent-text", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_dynamic_intent_to_motion_v1(
        args.fixture,
        args.intent_text,
        workspace=args.workspace.resolve(),
        derived_workspace=args.derived_workspace.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": result["status"],
        "case_count": result["case_count"],
        "actions": [len(case["ordered_target_ids"]) for case in result["cases"]],
        "samples": [
            case["route_result"]["trajectory_sample_count"]
            for case in result["cases"]
        ],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DynamicIntentToMotionV1Error",
    "compile_bounded_intent",
    "derive_dynamic_route_fixture",
    "parse_dynamic_intent_to_motion_v1",
    "run_dynamic_intent_to_motion_v1",
]
