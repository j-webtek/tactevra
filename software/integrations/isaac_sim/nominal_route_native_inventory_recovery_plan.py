"""Build an inert ARM-295 route-physics lineage plan.

The plan can be built only from an accepted ARM-294 zero-motion receipt review
and the retained terminal ARM-289 failure.  It freezes the corrected runtime
sources and the three still-unclaimed output locations needed by a future
attempt.  It does not collect live gates, accept authorization, start Isaac,
claim an attempt, or construct a motion-capable backend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_native_inventory_recovery_plan.v1"
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
EXACT_AUTHORIZATION = (
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


class NativeInventoryRecoveryPlanError(ValueError):
    """Raised when retained evidence or the future lineage boundary drifts."""


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
        raise NativeInventoryRecoveryPlanError(
            "lineage input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise NativeInventoryRecoveryPlanError(
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
        raise NativeInventoryRecoveryPlanError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    expected = {
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
    return all(document.get(key) == value for key, value in expected.items())


def build_plan(
    receipt_review: Mapping[str, Any],
    arm289_status: Mapping[str, Any],
    *,
    receipt_review_file_sha256: str,
    arm289_status_file_sha256: str,
    plan_source_file_sha256: str,
    runtime_sources_sha256: Mapping[str, str],
    proposed_attempt_directory: Path,
    proposed_eula_receipt: Path,
    proposed_memory_receipt: Path,
) -> dict[str, Any]:
    """Freeze a fresh lineage without admitting or claiming its attempt."""

    receipt_review_hash = _require_hash(
        receipt_review, "receipt_review_sha256", "ARM-294 receipt review"
    )
    digests = (
        receipt_review_file_sha256,
        arm289_status_file_sha256,
        plan_source_file_sha256,
        *runtime_sources_sha256.values(),
    )
    if not all(_digest(value) for value in digests):
        raise NativeInventoryRecoveryPlanError("lineage source digest changed")
    if set(runtime_sources_sha256) != set(RUNTIME_SOURCE_KEYS):
        raise NativeInventoryRecoveryPlanError("runtime source inventory changed")

    governed = Path(str(receipt_review.get("governed_attempt_directory", "")))
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
        or receipt_review.get("governed_attempt_directory_absent") is not True
        or receipt_review.get("next_required_stage")
        != "REBUILD_NEWLY_NUMBERED_ROUTE_PHYSICS_LINEAGE_WITH_FRESH_GATES"
        or not _zero_authority(receipt_review)
    ):
        raise NativeInventoryRecoveryPlanError(
            "ARM-294 receipt review boundary changed"
        )
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
    if dict(arm289_status) != expected_arm289:
        raise NativeInventoryRecoveryPlanError("ARM-289 terminal evidence changed")

    paths = (
        proposed_attempt_directory,
        proposed_eula_receipt,
        proposed_memory_receipt,
    )
    if (
        governed != proposed_attempt_directory
        or not all(path.is_absolute() for path in paths)
        or len({str(path) for path in paths}) != len(paths)
        or proposed_eula_receipt.name != "receipt.json"
        or proposed_memory_receipt.name != "receipt.json"
        or any(path.exists() for path in paths)
        or proposed_eula_receipt.parent.exists()
        or proposed_memory_receipt.parent.exists()
    ):
        raise NativeInventoryRecoveryPlanError("fresh output boundary changed")

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "plan_id": "arm295-native-inventory-recovered-route-physics-plan-001",
        "status": "READY_FOR_INDEPENDENT_ARM295_LINEAGE_PLAN_REVIEW",
        "case_id": "nominal-fixture-baseline",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "source_arm294_receipt_review_sha256": receipt_review_hash,
        "source_arm294_receipt_review_file_sha256": receipt_review_file_sha256,
        "source_arm289_status_file_sha256": arm289_status_file_sha256,
        "plan_source_file_sha256": plan_source_file_sha256,
        "runtime_sources_sha256": dict(sorted(runtime_sources_sha256.items())),
        "verified_native_link_names": list(EXPECTED_LINK_NAMES),
        "superseded_attempts": ["ARM-253", "ARM-280", "ARM-284", "ARM-289"],
        "superseded_authorizations_reusable": False,
        "proposed_attempt_directory": str(proposed_attempt_directory),
        "proposed_eula_receipt": str(proposed_eula_receipt),
        "proposed_memory_receipt": str(proposed_memory_receipt),
        "fresh_eula_preflight_required": True,
        "fresh_memory_preflight_required": True,
        "preflights_must_precede_attempt_claim": True,
        "terminal_status_must_precede_simulator_shutdown": True,
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "authorization_reusable": False,
        **ZERO_AUTHORITY,
        "next_required_stage": "INDEPENDENT_ARM295_LINEAGE_PLAN_REVIEW",
        "limitations": [
            "plan_build_does_not_collect_live_preflights",
            "plan_build_does_not_accept_or_reuse_authorization",
            "plan_build_does_not_create_any_governed_output_directory",
            "plan_build_does_not_construct_or_invoke_a_backend",
            "simulation_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "plan_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeInventoryRecoveryPlanError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise NativeInventoryRecoveryPlanError(
            f"required JSON is not an object: {path}"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-review", type=Path, required=True)
    parser.add_argument("--arm289-status", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", nargs=2, required=True)
    parser.add_argument("--proposed-attempt-directory", type=Path, required=True)
    parser.add_argument("--proposed-eula-receipt", type=Path, required=True)
    parser.add_argument("--proposed-memory-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_paths = {key: Path(value) for key, value in args.runtime_source}
    if set(runtime_paths) != set(RUNTIME_SOURCE_KEYS):
        raise NativeInventoryRecoveryPlanError("runtime source inventory changed")
    result = build_plan(
        _load(args.receipt_review),
        _load(args.arm289_status),
        receipt_review_file_sha256=_file_sha(args.receipt_review),
        arm289_status_file_sha256=_file_sha(args.arm289_status),
        plan_source_file_sha256=_file_sha(Path(__file__).resolve()),
        runtime_sources_sha256={
            key: _file_sha(path.resolve(strict=True))
            for key, path in runtime_paths.items()
        },
        proposed_attempt_directory=args.proposed_attempt_directory,
        proposed_eula_receipt=args.proposed_eula_receipt,
        proposed_memory_receipt=args.proposed_memory_receipt,
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
