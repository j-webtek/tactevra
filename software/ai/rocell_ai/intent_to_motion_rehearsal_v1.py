"""Bind exact keyboard intent to the retained C03 simulated movement plan.

This operator-facing composition remains offline and zero authority.  It does
not create a new route or controller command.  It proves that exact text
compiles to the same ordered semantic targets already carried through
ModelMotionBatchV2, strict ingress, Cartesian planning, and canonical IK.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .c03_arm_route_reconciliation_v1 import (
    canonical_hash,
    file_hash,
    load_strict_json,
)
from .end_to_end_typing_twin import compile_virtual_us_sticky_keys


SCHEMA = "tactevra.intent_to_simulated_motion_rehearsal.v1"
STATUS = "PASS_INTENT_TO_SIMULATED_IK_PLAN_RETAIN_COLLISION_BLOCKERS"
SOURCE_FIXTURE_SCHEMA = "tactevra.c03_exact_route_reconstruction_fixture.v1"
ROUTE_WRAPPER_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1_9"
ROUTE_RESULT_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STAGE_FIELDS = (
    "batch_sha256",
    "ingress_sha256",
    "freshness_sha256",
    "execution_plan_sha256",
    "trajectory_plan_sha256",
)
_AUTHORITY_FIELDS = {
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "hardware_writes": 0,
    "physical_movements": 0,
    "physical_authority": False,
}


class IntentToMotionRehearsalV1Error(ValueError):
    """The intent-to-motion evidence chain failed closed."""


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise IntentToMotionRehearsalV1Error(f"{label} must be a SHA-256 digest")
    return value


def _load_bound(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    expected = _digest(expected_sha256, f"{label}_sha256")
    if not path.is_file():
        raise IntentToMotionRehearsalV1Error(f"{label} is absent: {path}")
    if file_hash(path) != expected:
        raise IntentToMotionRehearsalV1Error(f"{label} bytes changed")
    return load_strict_json(path)


def _verify_canonical_receipt(
    document: Mapping[str, Any], field: str, label: str
) -> str:
    claimed = _digest(document.get(field), field)
    unsigned = {key: value for key, value in document.items() if key != field}
    if canonical_hash(unsigned) != claimed:
        raise IntentToMotionRehearsalV1Error(f"{label} canonical receipt changed")
    return claimed


def _verify_zero_authority(document: Mapping[str, Any], label: str) -> None:
    for field, expected in _AUTHORITY_FIELDS.items():
        if document.get(field) != expected:
            raise IntentToMotionRehearsalV1Error(
                f"{label} violates zero authority at {field}"
            )
    if document.get("controller_commands") != []:
        raise IntentToMotionRehearsalV1Error(
            f"{label} contains controller commands"
        )


def parse_intent_to_motion_rehearsal_v1(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one canonical rehearsal receipt and return a mutable copy."""

    expected = {
        "schema", "status", "scope", "requested_text", "requested_text_sha256",
        "ordered_target_ids", "action_count", "source_fixture_file_sha256",
        "source_fixture_sha256", "route_result_file_sha256",
        "route_wrapper_receipt_sha256", "route_receipt_sha256", "stage_hashes",
        "trajectory_sample_count", "ik_accepted_sample_count",
        "canonical_ik_route_accepted", "canonical_joint_continuity_accepted",
        "collision_screen_executed", "installed_collision_gate_cleared",
        "terminal_blockers", "controller_commands", "hardware_commands_generated",
        "hardware_access", "hardware_writes", "physical_movements",
        "physical_authority", "receipt_sha256",
    }
    if not isinstance(document, Mapping) or set(document) != expected:
        raise IntentToMotionRehearsalV1Error("receipt fields differ from contract")
    _verify_canonical_receipt(document, "receipt_sha256", "rehearsal")
    if (
        document["schema"] != SCHEMA
        or document["status"] != STATUS
        or document["scope"] != SCOPE
    ):
        raise IntentToMotionRehearsalV1Error("receipt identity changed")
    text = document["requested_text"]
    if not isinstance(text, str) or not text or len(text) > 256:
        raise IntentToMotionRehearsalV1Error("requested_text is invalid")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != document[
        "requested_text_sha256"
    ]:
        raise IntentToMotionRehearsalV1Error("requested text digest changed")
    targets = document["ordered_target_ids"]
    if not isinstance(targets, list) or not targets or len(targets) > 64:
        raise IntentToMotionRehearsalV1Error("ordered targets are invalid")
    if document["action_count"] != len(targets):
        raise IntentToMotionRehearsalV1Error("action count differs from targets")
    if list(compile_virtual_us_sticky_keys(text)) != targets:
        raise IntentToMotionRehearsalV1Error("text no longer compiles to targets")
    for field in (
        "source_fixture_file_sha256", "source_fixture_sha256",
        "route_result_file_sha256", "route_wrapper_receipt_sha256",
        "route_receipt_sha256",
    ):
        _digest(document[field], field)
    stage_hashes = document["stage_hashes"]
    if not isinstance(stage_hashes, Mapping) or set(stage_hashes) != set(_STAGE_FIELDS):
        raise IntentToMotionRehearsalV1Error("stage hash set changed")
    for field in _STAGE_FIELDS:
        _digest(stage_hashes[field], field)
    samples = document["trajectory_sample_count"]
    accepted = document["ik_accepted_sample_count"]
    if (
        isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0
        or accepted != samples
        or document["canonical_ik_route_accepted"] is not True
        or document["canonical_joint_continuity_accepted"] is not True
    ):
        raise IntentToMotionRehearsalV1Error("IK route is incomplete")
    if (
        document["collision_screen_executed"] is not False
        or document["installed_collision_gate_cleared"] is not False
        or document["terminal_blockers"] != [
            "INSTALLED_COLLISION_PROFILE_REQUIRED",
            "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
        ]
    ):
        raise IntentToMotionRehearsalV1Error("collision blocker state changed")
    _verify_zero_authority(document, "rehearsal receipt")
    return dict(document)


def run_intent_to_motion_rehearsal_v1(
    intent_text: str,
    *,
    source_fixture_path: Path,
    source_fixture_sha256: str,
    route_result_path: Path,
    route_result_sha256: str,
) -> dict[str, Any]:
    """Bind exact text to a previously generated, hash-pinned C03 IK route."""

    if not isinstance(intent_text, str) or not intent_text or len(intent_text) > 256:
        raise IntentToMotionRehearsalV1Error(
            "intent text must contain 1 to 256 characters"
        )
    compiled = list(compile_virtual_us_sticky_keys(intent_text))
    if len(compiled) > 64:
        raise IntentToMotionRehearsalV1Error("compiled intent exceeds 64 actions")

    source = _load_bound(
        source_fixture_path, source_fixture_sha256, "source route fixture"
    )
    source_claim = source.pop("fixture_sha256", None)
    if source_claim != canonical_hash(source):
        raise IntentToMotionRehearsalV1Error("source fixture canonical hash changed")
    source["fixture_sha256"] = source_claim
    if source.get("schema") != SOURCE_FIXTURE_SCHEMA or source.get("scope") != SCOPE:
        raise IntentToMotionRehearsalV1Error("source fixture identity changed")
    route_contract = source.get("route")
    if not isinstance(route_contract, Mapping):
        raise IntentToMotionRehearsalV1Error("source route contract is absent")
    if route_contract.get("text") != intent_text:
        raise IntentToMotionRehearsalV1Error(
            "requested text differs from frozen route text"
        )
    if route_contract.get("ordered_targets") != compiled:
        raise IntentToMotionRehearsalV1Error(
            "compiled targets differ from frozen route order"
        )

    wrapper = _load_bound(route_result_path, route_result_sha256, "route result")
    wrapper_receipt = _verify_canonical_receipt(
        wrapper, "receipt_sha256", "route wrapper"
    )
    if wrapper.get("schema") != ROUTE_WRAPPER_SCHEMA or wrapper.get("scope") != SCOPE:
        raise IntentToMotionRehearsalV1Error("route wrapper identity changed")
    _verify_zero_authority(wrapper, "route wrapper")
    rebinding = wrapper.get("fixture_rebinding_receipt")
    if not isinstance(rebinding, Mapping):
        raise IntentToMotionRehearsalV1Error("route rebinding receipt is absent")
    if rebinding.get("source_predecessor_fixture_sha256") != source_claim:
        raise IntentToMotionRehearsalV1Error("route does not descend from source fixture")
    if rebinding.get("numerical_policy_change_count") != 0:
        raise IntentToMotionRehearsalV1Error("route rebinding changed numerical policy")
    changed = rebinding.get("changed_semantic_fields")
    if not isinstance(changed, list) or any(
        field in {"predecessor.route.text", "predecessor.route.ordered_targets"}
        or field.endswith(".route.text")
        or field.endswith(".route.ordered_targets")
        for field in changed
    ):
        raise IntentToMotionRehearsalV1Error("route semantics were rebound")

    route = wrapper.get("route_result")
    if not isinstance(route, Mapping):
        raise IntentToMotionRehearsalV1Error("nested route result is absent")
    route_receipt = _verify_canonical_receipt(route, "receipt_sha256", "route")
    if route.get("schema") != ROUTE_RESULT_SCHEMA or route.get("scope") != SCOPE:
        raise IntentToMotionRehearsalV1Error("nested route identity changed")
    _verify_zero_authority(route, "nested route")
    if route.get("ordered_targets") != compiled:
        raise IntentToMotionRehearsalV1Error("route target order differs from intent")
    if route.get("decision") != "PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY":
        raise IntentToMotionRehearsalV1Error("route has not passed IK and continuity")
    samples = route.get("trajectory_sample_count")
    accepted = route.get("ik_accepted_sample_count")
    if (
        isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0
        or accepted != samples
        or route.get("canonical_ik_route_accepted") is not True
        or route.get("canonical_joint_continuity_accepted") is not True
    ):
        raise IntentToMotionRehearsalV1Error("nested IK route is incomplete")
    if (
        route.get("collision_screen_executed") is not False
        or route.get("installed_collision_gate_cleared") is not False
    ):
        raise IntentToMotionRehearsalV1Error("unexpected collision gate claim")
    stage_hashes = {field: _digest(route.get(field), field) for field in _STAGE_FIELDS}

    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "scope": SCOPE,
        "requested_text": intent_text,
        "requested_text_sha256": hashlib.sha256(intent_text.encode("utf-8")).hexdigest(),
        "ordered_target_ids": compiled,
        "action_count": len(compiled),
        "source_fixture_file_sha256": source_fixture_sha256,
        "source_fixture_sha256": source_claim,
        "route_result_file_sha256": route_result_sha256,
        "route_wrapper_receipt_sha256": wrapper_receipt,
        "route_receipt_sha256": route_receipt,
        "stage_hashes": stage_hashes,
        "trajectory_sample_count": samples,
        "ik_accepted_sample_count": accepted,
        "canonical_ik_route_accepted": True,
        "canonical_joint_continuity_accepted": True,
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
    parse_intent_to_motion_rehearsal_v1(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind exact text to a retained zero-authority C03 IK route"
    )
    parser.add_argument("--intent-text", required=True)
    parser.add_argument("--source-fixture", required=True, type=Path)
    parser.add_argument("--source-fixture-sha256", required=True)
    parser.add_argument("--route-result", required=True, type=Path)
    parser.add_argument("--route-result-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_intent_to_motion_rehearsal_v1(
        args.intent_text,
        source_fixture_path=args.source_fixture,
        source_fixture_sha256=args.source_fixture_sha256,
        route_result_path=args.route_result,
        route_result_sha256=args.route_result_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": result["status"],
        "action_count": result["action_count"],
        "trajectory_sample_count": result["trajectory_sample_count"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "IntentToMotionRehearsalV1Error",
    "parse_intent_to_motion_rehearsal_v1",
    "run_intent_to_motion_rehearsal_v1",
]
