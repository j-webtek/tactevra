"""Independently review an inert ARM-295 route-physics lineage plan.

This reviewer imports no plan implementation, Isaac, transport, or backend
module.  It re-hashes every retained evidence file and corrected runtime source,
checks that all proposed governed outputs remain absent, and emits a review that
still grants no launch, attempt, motion, hardware, or physical authority.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PLAN_SCHEMA = "tactevra.isaac_lm4_native_inventory_recovery_plan.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_inventory_recovery_plan_review.v1"
RECEIPT_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_native_link_inventory_receipt_review.v1"
)
RECEIPT_REVIEW_STATUS = "ACCEPTED_NATIVE_LINK_INVENTORY_ZERO_MOTION_EVIDENCE"
EXPECTED_LINK_NAMES = (
    "base_link",
    "link1",
    "link2",
    "link3",
    "link4",
    "link5",
    "gripper_link",
)
RUNTIME_SOURCE_KEYS = (
    "concrete_native_attempt_binding",
    "concrete_native_session",
    "native_root_path_correction",
    "native_session",
    "native_sweep_binding",
    "native_worker_integration",
    "physics_backend",
    "physics_worker",
)
EXPECTED_AUTHORIZATION = (
    "I authorize exactly one ARM-295 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "launch_admitted": False,
    "isaac_started": False,
    "timeline_played": False,
    "physics_steps": 0,
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


class NativeInventoryRecoveryPlanReviewError(ValueError):
    """Raised when a proposed recovered lineage is incomplete or has drifted."""


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
        raise NativeInventoryRecoveryPlanReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise NativeInventoryRecoveryPlanReviewError(
            f"required input unavailable: {path}"
        ) from exc


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise NativeInventoryRecoveryPlanReviewError(f"{label} hash changed")
    return claimed


def _static_review(plan_source: Path) -> dict[str, bool]:
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
        raise NativeInventoryRecoveryPlanReviewError(
            "runtime- or transport-capable import found"
        )
    forbidden = (
        "start_headless(",
        "initialize_physics(",
        "SimulationManager.step(",
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "execute_backend(",
        "run_one_attempt(",
        "serial.Serial(",
    )
    if any(token in text for token in forbidden):
        raise NativeInventoryRecoveryPlanReviewError(
            "runtime, motion, or transport call surface found"
        )
    build = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_plan"
        ),
        None,
    )
    if build is None:
        raise NativeInventoryRecoveryPlanReviewError("build_plan is unavailable")
    return {
        "runtime_and_transport_imports_absent": True,
        "runtime_motion_and_transport_calls_absent": True,
        "plan_builder_present": True,
    }


def review_plan(
    plan: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_source: Path,
    receipt_review_file: Path,
    arm289_status_file: Path,
    runtime_sources: Mapping[str, Path],
    review_source_file_sha256: str,
) -> dict[str, Any]:
    """Rebind the plan to current files without admitting ARM-295."""

    plan_hash = _require_hash(plan, "plan_sha256", "ARM-295 lineage plan")
    if not all(_digest(value) for value in (plan_file_sha256, review_source_file_sha256)):
        raise NativeInventoryRecoveryPlanReviewError("review source digest changed")
    if set(runtime_sources) != set(RUNTIME_SOURCE_KEYS):
        raise NativeInventoryRecoveryPlanReviewError(
            "runtime source inventory changed"
        )
    static = _static_review(plan_source.resolve(strict=True))
    receipt_review = _load(receipt_review_file.resolve(strict=True))
    receipt_review_hash = _require_hash(
        receipt_review, "receipt_review_sha256", "ARM-294 receipt review"
    )
    arm289_status = _load(arm289_status_file.resolve(strict=True))
    current_runtime_hashes = {
        key: _file_sha(path.resolve(strict=True))
        for key, path in runtime_sources.items()
    }
    attempt = Path(str(plan.get("proposed_attempt_directory", "")))
    eula_receipt = Path(str(plan.get("proposed_eula_receipt", "")))
    memory_receipt = Path(str(plan.get("proposed_memory_receipt", "")))
    paths = (attempt, eula_receipt, memory_receipt)
    receipt_zero_authority = {
        "route_attempt_admitted": False,
        "launch_admitted": False,
        "isaac_started": False,
        "attempt_consumed": False,
        "worker_invoked": False,
        "backend_invoked": False,
        "timeline_played": False,
        "physics_steps": 0,
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
    expected_arm289 = {
        "attempt_count": 1,
        "automatic_retry": False,
        "error_message": "native articulation link inventory changed",
        "error_stage": "construct_runtime",
        "error_type": "NativeSweepBindingError",
        "hardware_access": False,
        "physical_authority": False,
        "status": "FAILED_RETAINED_NO_RETRY",
    }
    if (
        receipt_review.get("schema") != RECEIPT_REVIEW_SCHEMA
        or receipt_review.get("review_id")
        != "arm294-native-link-inventory-receipt-review-001"
        or receipt_review.get("status") != RECEIPT_REVIEW_STATUS
        or receipt_review.get("verified_link_names") != list(EXPECTED_LINK_NAMES)
        or receipt_review.get("verified_link_count") != len(EXPECTED_LINK_NAMES)
        or receipt_review.get("verified_transform_batch_count") != 1
        or receipt_review.get("verified_transform_count") != len(EXPECTED_LINK_NAMES)
        or receipt_review.get("source_isaac_started") is not True
        or receipt_review.get("source_physics_steps") != 0
        or receipt_review.get("governed_attempt_directory") != str(attempt)
        or receipt_review.get("governed_attempt_directory_absent") is not True
        or receipt_review.get("next_required_stage")
        != "REBUILD_NEWLY_NUMBERED_ROUTE_PHYSICS_LINEAGE_WITH_FRESH_GATES"
        or any(
            receipt_review.get(key) != value
            for key, value in receipt_zero_authority.items()
        )
    ):
        raise NativeInventoryRecoveryPlanReviewError(
            "ARM-294 retained receipt review boundary changed"
        )
    if dict(arm289_status) != expected_arm289:
        raise NativeInventoryRecoveryPlanReviewError(
            "ARM-289 retained terminal evidence changed"
        )
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("plan_id")
        != "arm295-native-inventory-recovered-route-physics-plan-001"
        or plan.get("status")
        != "READY_FOR_INDEPENDENT_ARM295_LINEAGE_PLAN_REVIEW"
        or plan.get("case_id") != "nominal-fixture-baseline"
        or plan.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or plan.get("target_id") != "SPACE"
        or plan.get("source_arm294_receipt_review_sha256") != receipt_review_hash
        or plan.get("verified_native_link_names") != list(EXPECTED_LINK_NAMES)
        or plan.get("superseded_attempts")
        != ["ARM-253", "ARM-280", "ARM-284", "ARM-289"]
        or plan.get("superseded_authorizations_reusable") is not False
        or plan.get("fresh_eula_preflight_required") is not True
        or plan.get("fresh_memory_preflight_required") is not True
        or plan.get("preflights_must_precede_attempt_claim") is not True
        or plan.get("terminal_status_must_precede_simulator_shutdown") is not True
        or plan.get("required_authorization_statement") != EXPECTED_AUTHORIZATION
        or plan.get("authorization_reusable") is not False
        or any(plan.get(key) != value for key, value in ZERO_AUTHORITY.items())
        or plan.get("next_required_stage")
        != "INDEPENDENT_ARM295_LINEAGE_PLAN_REVIEW"
    ):
        raise NativeInventoryRecoveryPlanReviewError(
            "ARM-295 lineage plan boundary changed"
        )
    if (
        plan.get("source_arm294_receipt_review_file_sha256")
        != _file_sha(receipt_review_file.resolve(strict=True))
        or plan.get("source_arm289_status_file_sha256")
        != _file_sha(arm289_status_file.resolve(strict=True))
        or plan.get("plan_source_file_sha256") != _file_sha(plan_source)
        or plan.get("runtime_sources_sha256") != current_runtime_hashes
    ):
        raise NativeInventoryRecoveryPlanReviewError(
            "ARM-295 lineage file binding changed"
        )
    if (
        not all(path.is_absolute() for path in paths)
        or len({str(path) for path in paths}) != len(paths)
        or eula_receipt.name != "receipt.json"
        or memory_receipt.name != "receipt.json"
        or any(path.exists() for path in paths)
        or eula_receipt.parent.exists()
        or memory_receipt.parent.exists()
    ):
        raise NativeInventoryRecoveryPlanReviewError(
            "ARM-295 proposed output boundary changed"
        )

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm295-native-inventory-recovery-plan-review-001",
        "status": "ACCEPTED_FOR_FRESH_PREFLIGHT_AND_CLAIMANT_CONSTRUCTION",
        "source_plan_sha256": plan_hash,
        "source_plan_file_sha256": plan_file_sha256,
        "source_plan_source_file_sha256": _file_sha(plan_source),
        "source_arm294_receipt_review_file_sha256": _file_sha(
            receipt_review_file
        ),
        "source_arm294_receipt_review_sha256": receipt_review_hash,
        "source_arm289_status_file_sha256": _file_sha(arm289_status_file),
        "verified_runtime_sources_sha256": dict(
            sorted(current_runtime_hashes.items())
        ),
        "static_review": static,
        "verified_native_link_names": list(EXPECTED_LINK_NAMES),
        "proposed_attempt_directory": str(attempt),
        "proposed_attempt_directory_absent": True,
        "proposed_eula_receipt": str(eula_receipt),
        "proposed_eula_receipt_absent": True,
        "proposed_memory_receipt": str(memory_receipt),
        "proposed_memory_receipt_absent": True,
        "required_authorization_statement": EXPECTED_AUTHORIZATION,
        **ZERO_AUTHORITY,
        "next_required_stage": (
            "BUILD_FRESH_ARM295_PREFLIGHT_BOUND_CLAIMANT_WITH_SEPARATE_REVIEW"
        ),
        "limitations": [
            "review_does_not_collect_live_eula_or_memory_evidence",
            "review_does_not_accept_authorization_or_claim_an_attempt",
            "review_does_not_construct_or_invoke_a_backend",
            "review_does_not_authorize_hardware_or_physical_motion",
        ],
        "review_source_file_sha256": review_source_file_sha256,
    }
    return {**core, "review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeInventoryRecoveryPlanReviewError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise NativeInventoryRecoveryPlanReviewError(
            f"required JSON is not an object: {path}"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--receipt-review", type=Path, required=True)
    parser.add_argument("--arm289-status", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_sources = {key: Path(value) for key, value in args.runtime_source}
    result = review_plan(
        _load(args.plan),
        plan_file_sha256=_file_sha(args.plan),
        plan_source=args.plan_source,
        receipt_review_file=args.receipt_review,
        arm289_status_file=args.arm289_status,
        runtime_sources=runtime_sources,
        review_source_file_sha256=_file_sha(Path(__file__).resolve()),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
