"""Independently review the inert ARM-297 route-physics lineage plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PLAN_SCHEMA = "tactevra.isaac_lm4_arm297_route_physics_lineage_plan.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_arm297_route_physics_lineage_plan_review.v1"
EXPECTED_GATE_FILE_SHA256 = (
    "6c81aa58affb57218fd88ca38ea977a62c5aa305f0f4dad9a007fd6625a7a2c1"
)
EXPECTED_REVIEW_FILE_SHA256 = (
    "f6ec2f7b7aa84df312057e532062f2938b6b4bce1a56891a1aae5d832ec27e4d"
)
EXPECTED_GATE_SHA256 = (
    "e240eae3f47edeeca8d4010889440bce89d0a10f495793cc286e5b47d290650b"
)
EXPECTED_REVIEW_SHA256 = (
    "9649483e22931a982c865ce209d24ed12446373375a6f2c4522c349dcaaac003"
)
EXPECTED_CORRECTED_BINDING_SHA256 = (
    "2d93fe5647e3596fded4c3f8ba7e33f7c89a495f76fcf69620327588eb2d1fe7"
)
RUNTIME_SOURCE_KEYS = (
    "complete_runtime_composition",
    "concrete_native_attempt_binding",
    "constructor_completeness_gate",
    "constructor_completeness_gate_review",
    "native_root_path_correction",
    "native_runtime_factory",
    "native_runtime_worker_integration",
    "native_sweep_binding",
    "physics_backend",
    "physics_worker",
)
EXPECTED_AUTHORIZATION = (
    "I authorize exactly one ARM-297 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "attempt_consumed": False,
    "claimant_constructed": False,
    "launch_admitted": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "isaac_imported": False,
    "isaac_started": False,
    "scene_loaded": False,
    "timeline_played": False,
    "physics_steps": 0,
    "runtime_methods_called": [],
    "trajectory_playback": False,
    "joint_positions_submitted": False,
    "joint_targets_submitted": False,
    "key_contact": False,
    "automatic_retry": False,
    "hardware_access": False,
    "hardware_writes": 0,
    "physical_authority": False,
    "physical_movements": 0,
    "controller_commands": [],
    "wire_commands": [],
    "gate_promotions": [],
}


class Arm297LineagePlanReviewError(ValueError):
    """Raised when the proposed lineage or any bound source changes."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Arm297LineagePlanReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm297LineagePlanReviewError(
            f"required input unavailable: {path}"
        ) from exc


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _require_hash(
    document: Mapping[str, Any], key: str, label: str
) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise Arm297LineagePlanReviewError(f"{label} hash changed")
    return claimed


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm297LineagePlanReviewError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise Arm297LineagePlanReviewError(f"{path} must contain an object")
    return value


def _static_review(plan_source: Path) -> dict[str, Any]:
    text = plan_source.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    if any(
        name.startswith(("isaac", "omni", "serial", "socket", "requests"))
        for name in imports
    ):
        raise Arm297LineagePlanReviewError(
            "runtime- or transport-capable import found"
        )
    forbidden = (
        "SimulationApp(",
        "start_headless(",
        "initialize_physics(",
        "SimulationManager.step(",
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "construct_runtime(",
        "execute_backend(",
        "run_one_attempt(",
        "serial.Serial(",
    )
    if any(token in text for token in forbidden):
        raise Arm297LineagePlanReviewError(
            "runtime, motion, or transport call surface found"
        )
    build = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_arm297_lineage_plan"
        ),
        None,
    )
    if build is None:
        raise Arm297LineagePlanReviewError("lineage plan builder is absent")
    return {
        "runtime_and_transport_imports_absent": True,
        "runtime_motion_and_transport_calls_absent": True,
        "lineage_plan_builder_present": True,
    }


def review_arm297_lineage_plan(
    plan: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_source: Path,
    gate_receipt_file: Path,
    gate_review_file: Path,
    runtime_sources: Mapping[str, Path],
    review_source_file_sha256: str,
) -> dict[str, Any]:
    """Rebind every source and prove the proposed ARM-297 outputs stay absent."""

    plan_hash = _require_hash(plan, "plan_sha256", "ARM-297 lineage plan")
    if not all(_digest(value) for value in (plan_file_sha256, review_source_file_sha256)):
        raise Arm297LineagePlanReviewError("review source digest changed")
    if set(runtime_sources) != set(RUNTIME_SOURCE_KEYS):
        raise Arm297LineagePlanReviewError("runtime source inventory changed")
    static_review = _static_review(plan_source.resolve(strict=True))
    gate = _load(gate_receipt_file.resolve(strict=True))
    gate_review = _load(gate_review_file.resolve(strict=True))
    gate_hash = _require_hash(gate, "gate_sha256", "ARM-296 gate")
    gate_review_hash = _require_hash(
        gate_review, "gate_review_sha256", "ARM-296 gate review"
    )
    current_runtime_hashes = {
        key: _file_sha(path.resolve(strict=True))
        for key, path in runtime_sources.items()
    }
    attempt = Path(str(plan.get("proposed_attempt_directory", "")))
    eula_receipt = Path(str(plan.get("proposed_eula_receipt", "")))
    memory_receipt = Path(str(plan.get("proposed_memory_receipt", "")))
    paths = (attempt, eula_receipt, memory_receipt)

    if (
        _file_sha(gate_receipt_file) != EXPECTED_GATE_FILE_SHA256
        or _file_sha(gate_review_file) != EXPECTED_REVIEW_FILE_SHA256
        or gate_hash != EXPECTED_GATE_SHA256
        or gate_review_hash != EXPECTED_REVIEW_SHA256
        or gate_review.get("source_gate_sha256") != gate_hash
        or gate.get("status")
        != "PASS_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS"
        or gate_review.get("status")
        != "ACCEPTED_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS"
    ):
        raise Arm297LineagePlanReviewError("ARM-296 evidence changed")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("plan_id")
        != "arm297-recovered-nominal-route-physics-lineage-plan-001"
        or plan.get("status")
        != "READY_FOR_INDEPENDENT_ARM297_LINEAGE_PLAN_REVIEW"
        or plan.get("case_id") != "nominal-fixture-baseline"
        or plan.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or plan.get("target_id") != "SPACE"
        or plan.get("source_arm296_gate_sha256") != gate_hash
        or plan.get("source_arm296_gate_file_sha256")
        != EXPECTED_GATE_FILE_SHA256
        or plan.get("source_arm296_review_sha256") != gate_review_hash
        or plan.get("source_arm296_review_file_sha256")
        != EXPECTED_REVIEW_FILE_SHA256
        or plan.get("superseded_attempts")
        != ["ARM-253", "ARM-280", "ARM-284", "ARM-289", "ARM-295"]
        or plan.get("superseded_authorizations_reusable") is not False
        or plan.get("arm295_replay_permitted") is not False
        or plan.get("arm296_is_attempt_authority") is not False
        or plan.get("fresh_eula_preflight_required") is not True
        or plan.get("fresh_memory_preflight_required") is not True
        or plan.get("preflights_must_precede_attempt_claim") is not True
        or plan.get("terminal_status_must_precede_simulator_shutdown") is not True
        or plan.get("claimant_review_required_before_authorization") is not True
        or plan.get("required_authorization_statement") != EXPECTED_AUTHORIZATION
        or plan.get("authorization_reusable") is not False
        or any(plan.get(key) != value for key, value in ZERO_AUTHORITY.items())
        or plan.get("next_required_stage")
        != "INDEPENDENT_ARM297_LINEAGE_PLAN_REVIEW"
    ):
        raise Arm297LineagePlanReviewError("ARM-297 lineage boundary changed")
    if (
        plan.get("plan_source_file_sha256") != _file_sha(plan_source)
        or plan.get("runtime_sources_sha256") != current_runtime_hashes
        or current_runtime_hashes.get("concrete_native_attempt_binding")
        != EXPECTED_CORRECTED_BINDING_SHA256
    ):
        raise Arm297LineagePlanReviewError("ARM-297 source binding changed")
    if (
        not all(path.is_absolute() for path in paths)
        or len({str(path) for path in paths}) != len(paths)
        or attempt.name != "arm297-nominal-route-physics-attempt-001"
        or eula_receipt.parent.name
        != "arm297-nominal-route-physics-eula-preflight-001"
        or memory_receipt.parent.name
        != "arm297-nominal-route-physics-memory-preflight-001"
        or eula_receipt.name != "receipt.json"
        or memory_receipt.name != "receipt.json"
        or any(path.exists() for path in paths)
        or eula_receipt.parent.exists()
        or memory_receipt.parent.exists()
    ):
        raise Arm297LineagePlanReviewError("ARM-297 output boundary changed")

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm297-route-physics-lineage-plan-review-001",
        "status": "ACCEPTED_ARM297_LINEAGE_FOR_CLAIMANT_CONSTRUCTION",
        "source_plan_sha256": plan_hash,
        "source_plan_file_sha256": plan_file_sha256,
        "source_plan_source_file_sha256": _file_sha(plan_source),
        "source_arm296_gate_sha256": gate_hash,
        "source_arm296_gate_file_sha256": EXPECTED_GATE_FILE_SHA256,
        "source_arm296_review_sha256": gate_review_hash,
        "source_arm296_review_file_sha256": EXPECTED_REVIEW_FILE_SHA256,
        "verified_runtime_sources_sha256": dict(
            sorted(current_runtime_hashes.items())
        ),
        "static_review": static_review,
        "proposed_attempt_directory": str(attempt),
        "proposed_attempt_directory_absent": True,
        "proposed_eula_receipt": str(eula_receipt),
        "proposed_eula_receipt_absent": True,
        "proposed_memory_receipt": str(memory_receipt),
        "proposed_memory_receipt_absent": True,
        "required_authorization_statement": EXPECTED_AUTHORIZATION,
        **ZERO_AUTHORITY,
        "next_required_stage": (
            "BUILD_SINGLE_USE_ARM297_CLAIMANT_AND_INDEPENDENT_REVIEW"
        ),
        "limitations": [
            "review_does_not_construct_a_claimant_or_collect_live_preflights",
            "review_does_not_accept_authorization_or_claim_an_attempt",
            "review_does_not_start_isaac_or_invoke_runtime_or_backend",
            "review_does_not_authorize_hardware_or_physical_motion",
        ],
        "review_source_file_sha256": review_source_file_sha256,
    }
    return {**core, "lineage_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--gate-receipt", type=Path, required=True)
    parser.add_argument("--gate-review", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_sources = {key: Path(value) for key, value in args.runtime_source}
    result = review_arm297_lineage_plan(
        _load(args.plan),
        plan_file_sha256=_file_sha(args.plan),
        plan_source=args.plan_source,
        gate_receipt_file=args.gate_receipt,
        gate_review_file=args.gate_review,
        runtime_sources=runtime_sources,
        review_source_file_sha256=_file_sha(Path(__file__).resolve()),
    )
    if args.output.exists():
        raise Arm297LineagePlanReviewError("review output exists; overwrite refused")
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
