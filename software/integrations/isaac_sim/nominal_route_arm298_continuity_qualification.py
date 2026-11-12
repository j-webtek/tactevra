"""Qualify the corrected ARM-298 canonical-IK route boundary offline.

This gate evaluates the exact retained nominal SPACE route with the production
RoArm-M3 numerical IK implementation.  It canonicalizes row 653 from row 652,
then checks continuity for every governed row 654 through 940.  It imports no
Isaac module, creates no simulator, claims no attempt, and has no controller or
hardware surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Protocol, Sequence


INTEGRATION_ROOT = Path(__file__).resolve().parent
SOFTWARE_ROOT = INTEGRATION_ROOT.parents[1]
SOURCE_ROOT = SOFTWARE_ROOT / "src"
for source_root in (INTEGRATION_ROOT, SOURCE_ROOT):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from nominal_route_canonical_ik_row_adapter import (  # noqa: E402
    CanonicalIkRowRuntimeAdapter,
)


SCHEMA = "tactevra.isaac_lm4_arm298_continuity_qualification.v1"
FIRST_SEQUENCE = 654
LAST_SEQUENCE = 940
BOUNDARY_SEQUENCE = FIRST_SEQUENCE - 1
MAXIMUM_ADJACENT_JOINT_STEP_RAD = 0.05
EXPECTED_ROW_COUNT = 287
EXPECTED_ARM297_STATUS_FILE_SHA256 = (
    "672c98d42ff12c6e28629a052140f75fa599d30f13d15e1d0ca1cdae12bcedea"
)
EXPECTED_ROUTE_FILE_SHA256 = (
    "d22fffa61b4d481e8c90956828c3c2a58634e9408108f00a2521501e331c0449"
)
EXPECTED_ADAPTER_FILE_SHA256 = (
    "b3e799c4964bec898772730502f3c81cf22f9e0ded7447f76d21b6a284786f1a"
)
EXPECTED_ADAPTER_REVIEW_FILE_SHA256 = (
    "cb61e4005777e0f75556fb238b18608be029375da2b4b11a1be75b0da74fe42f"
)
EXPECTED_ADAPTER_SHA256 = (
    "0c6b35d2392604687bc52bf723b9422967cc9631c5e33557a56cf7f2c5e4829a"
)
EXPECTED_ADAPTER_REVIEW_SHA256 = (
    "45ab4fde0d228893b0adc3e2c25ccb7ac15939742f24712c0b31e358ca41592a"
)
EXPECTED_CURRENT_ADAPTER_SOURCE_SHA256 = (
    "12f79fa15a78aebc3fe8a9ca7ca27e8efa48e70eb6c08b15f30664f2ad4dbdf3"
)
EXPECTED_CURRENT_BACKEND_SOURCE_SHA256 = (
    "f9e76cba8c917f7645142a50334682bcd4dafb68cd4b761b2f227135ef12a96d"
)
EXPECTED_SYSTEM_MANIFEST_SHA256 = (
    "0cfb19c0972d4fe5cc526ca78d44422b2ef9c52354a8da637ec608b8dec7f55d"
)
EXPECTED_IK_SOURCE_SHA256 = (
    "4feb5adb8c33d7b3017f29c17130dc934269ae159bed88b06d8aa63d8474569a"
)
EXPECTED_CONTEXT_SOURCE_SHA256 = (
    "b08cd66421ab5e77ebe4d58ae5c8a6e7a726f3c1faf04103294978955115e21e"
)
EXPECTED_PINNED_MODEL_SOURCE_SHA256 = (
    "49e2b6bb553d98f984f1a3a440c851586e90d3f390206e739a53efd7fed0e344"
)
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "attempt_consumed": False,
    "isaac_imported": False,
    "isaac_started": False,
    "scene_loaded": False,
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


class Arm298ContinuityQualificationError(ValueError):
    """Raised when pinned evidence or the full-route qualification fails."""


class RowRuntime(Protocol):
    def regenerate_row(
        self,
        *,
        source_row: Mapping[str, Any],
        previous_joint_targets_rad: Sequence[float],
    ) -> Mapping[str, Any]: ...


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
        raise Arm298ContinuityQualificationError(
            "qualification input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm298ContinuityQualificationError(
            f"required input unavailable: {path}"
        ) from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm298ContinuityQualificationError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise Arm298ContinuityQualificationError(f"{path} must contain an object")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise Arm298ContinuityQualificationError(f"{label} hash changed")
    return claimed


def _finite_joints(value: Any, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        raise Arm298ContinuityQualificationError(f"{label} must contain six joints")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise Arm298ContinuityQualificationError(f"{label} is not numeric")
        number = float(item)
        if not math.isfinite(number):
            raise Arm298ContinuityQualificationError(f"{label} is not finite")
        result.append(number)
    return result


def evaluate_route_continuity(
    route: Mapping[str, Any], runtime: RowRuntime
) -> dict[str, Any]:
    """Evaluate the real governed window with a supplied canonical row runtime."""

    rows = route.get("joint_targets")
    if (
        route.get("sample_count") != 1416
        or not isinstance(rows, list)
        or len(rows) != 1416
        or any(
            not isinstance(row, Mapping) or row.get("sequence") != sequence
            for sequence, row in enumerate(rows)
        )
    ):
        raise Arm298ContinuityQualificationError("route shape changed")

    boundary = dict(
        runtime.regenerate_row(
            source_row=rows[BOUNDARY_SEQUENCE],
            previous_joint_targets_rad=_finite_joints(
                rows[BOUNDARY_SEQUENCE - 1].get("joint_position_target_rad"),
                "row 652",
            ),
        )
    )
    previous = _finite_joints(
        boundary.get("joint_position_target_rad"), "canonical row 653"
    )
    if (
        boundary.get("sequence") != BOUNDARY_SEQUENCE
        or boundary.get("accepted") is not True
        or boundary.get("determinate") is not True
    ):
        raise Arm298ContinuityQualificationError("canonical boundary failed")

    evidence: list[dict[str, Any]] = []
    maximum_step = -1.0
    maximum_step_sequence = -1
    maximum_residual = -1.0
    maximum_residual_sequence = -1
    for sequence in range(FIRST_SEQUENCE, LAST_SEQUENCE + 1):
        result = dict(
            runtime.regenerate_row(
                source_row=rows[sequence],
                previous_joint_targets_rad=previous,
            )
        )
        joints = _finite_joints(
            result.get("joint_position_target_rad"), f"canonical row {sequence}"
        )
        residual = result.get("position_error_mm")
        if (
            isinstance(residual, bool)
            or not isinstance(residual, (int, float))
            or not math.isfinite(float(residual))
            or result.get("sequence") != sequence
            or result.get("accepted") is not True
            or result.get("determinate") is not True
        ):
            raise Arm298ContinuityQualificationError(f"canonical row {sequence} failed")
        step = max(abs(current - prior) for current, prior in zip(joints, previous))
        if step > MAXIMUM_ADJACENT_JOINT_STEP_RAD:
            raise Arm298ContinuityQualificationError(
                f"canonical row {sequence} exceeds continuity limit"
            )
        if step > maximum_step:
            maximum_step = step
            maximum_step_sequence = sequence
        if float(residual) > maximum_residual:
            maximum_residual = float(residual)
            maximum_residual_sequence = sequence
        evidence.append(
            {
                "sequence": sequence,
                "joint_position_target_rad": joints,
                "position_error_mm": float(residual),
                "maximum_adjacent_joint_step_rad": step,
            }
        )
        previous = joints

    if len(evidence) != EXPECTED_ROW_COUNT:
        raise Arm298ContinuityQualificationError("governed row count changed")
    boundary_residual = boundary.get("position_error_mm")
    if (
        isinstance(boundary_residual, bool)
        or not isinstance(boundary_residual, (int, float))
        or not math.isfinite(float(boundary_residual))
    ):
        raise Arm298ContinuityQualificationError("boundary residual changed")
    return {
        "canonical_boundary_sequence": BOUNDARY_SEQUENCE,
        "canonical_boundary_position_error_mm": float(boundary_residual),
        "first_sequence": FIRST_SEQUENCE,
        "last_sequence": LAST_SEQUENCE,
        "governed_row_count": len(evidence),
        "maximum_adjacent_joint_step_rad": maximum_step,
        "maximum_adjacent_joint_step_sequence": maximum_step_sequence,
        "maximum_position_error_mm": maximum_residual,
        "maximum_position_error_sequence": maximum_residual_sequence,
        "continuity_limit_rad": MAXIMUM_ADJACENT_JOINT_STEP_RAD,
        "canonical_rows_sha256": _sha(evidence),
    }


def _production_runtime(
    repo_root: Path,
    adapter_definition: Mapping[str, Any],
    adapter_review: Mapping[str, Any],
) -> CanonicalIkRowRuntimeAdapter:
    from rocell.application._pinned_model import load_pinned_urdf
    from rocell.application.context import load_simulation_context
    from rocell.kinematics import IkOptions
    from rocell.kinematics.ik import RoArmM3NumericalIk

    context = load_simulation_context(
        repo_root, repo_root / "software/config/system_manifest.json"
    )
    scenario = context.scenario
    model = load_pinned_urdf(scenario.model_path, scenario.model_sha256).model
    solver = RoArmM3NumericalIk(
        model=model,
        board_T_world=scenario.board_T_world,
        hand_tcp_to_tip_z_mm=scenario.hand_tcp_to_tip_z_mm,
        fixed_gripper_position=scenario.fixed_gripper_position,
        ready_arm_joint_positions=scenario.ready_arm_joint_positions_rad,
        gripper_bounds_rad=scenario.controller_gripper_intersection_rad,
        options=IkOptions(
            max_attempts=scenario.ik_policy.max_attempts,
            max_iterations_per_attempt=(scenario.ik_policy.max_iterations_per_attempt),
        ),
        joint_bounds_rad=scenario.controller_joint_intersection_rad,
    )
    return CanonicalIkRowRuntimeAdapter(
        adapter_definition, adapter_review=adapter_review, solver=solver
    )


def build_qualification(
    *,
    arm297_status_path: Path,
    route_path: Path,
    adapter_definition_path: Path,
    adapter_review_path: Path,
    repo_root: Path,
    qualification_source_path: Path,
) -> dict[str, Any]:
    """Bind the terminal failure and prove corrected full-window continuity."""

    status = _load(arm297_status_path)
    route = _load(route_path)
    definition = _load(adapter_definition_path)
    review = _load(adapter_review_path)
    adapter_source = repo_root / (
        "software/integrations/isaac_sim/" "nominal_route_canonical_ik_row_adapter.py"
    )
    backend_source = repo_root / (
        "software/integrations/isaac_sim/nominal_route_physics_backend.py"
    )
    pinned = {
        arm297_status_path: EXPECTED_ARM297_STATUS_FILE_SHA256,
        route_path: EXPECTED_ROUTE_FILE_SHA256,
        adapter_definition_path: EXPECTED_ADAPTER_FILE_SHA256,
        adapter_review_path: EXPECTED_ADAPTER_REVIEW_FILE_SHA256,
        adapter_source: EXPECTED_CURRENT_ADAPTER_SOURCE_SHA256,
        backend_source: EXPECTED_CURRENT_BACKEND_SOURCE_SHA256,
        repo_root / "software/config/system_manifest.json": (
            EXPECTED_SYSTEM_MANIFEST_SHA256
        ),
        repo_root / "software/src/rocell/kinematics/ik.py": (EXPECTED_IK_SOURCE_SHA256),
        repo_root / "software/src/rocell/application/context.py": (
            EXPECTED_CONTEXT_SOURCE_SHA256
        ),
        repo_root / "software/src/rocell/application/_pinned_model.py": (
            EXPECTED_PINNED_MODEL_SOURCE_SHA256
        ),
    }
    for path, expected in pinned.items():
        if _file_sha(path.resolve(strict=True)) != expected:
            raise Arm298ContinuityQualificationError(f"pinned input changed: {path}")
    if status != {
        "attempt_count": 1,
        "automatic_retry": False,
        "error_message": "canonical IK row 654 failed",
        "error_stage": "execute_backend",
        "error_type": "NominalRoutePhysicsBackendError",
        "hardware_access": False,
        "physical_authority": False,
        "status": "FAILED_RETAINED_NO_RETRY",
    }:
        raise Arm298ContinuityQualificationError("ARM-297 terminal status changed")
    if (
        _require_hash(definition, "adapter_sha256", "adapter definition")
        != EXPECTED_ADAPTER_SHA256
        or _require_hash(review, "adapter_review_sha256", "adapter review")
        != EXPECTED_ADAPTER_REVIEW_SHA256
        or review.get("source_adapter_sha256") != EXPECTED_ADAPTER_SHA256
        or review.get("runtime_integration_admitted") is not True
    ):
        raise Arm298ContinuityQualificationError("reviewed adapter changed")

    runtime = _production_runtime(repo_root, definition, review)
    evaluation = evaluate_route_continuity(route, runtime)
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "qualification_id": "arm298-canonical-continuity-qualification-001",
        "status": "PASS_ARM298_CANONICAL_CONTINUITY_QUALIFICATION",
        "case_id": "nominal-fixture-baseline",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "source_arm297_status_file_sha256": EXPECTED_ARM297_STATUS_FILE_SHA256,
        "source_route_file_sha256": EXPECTED_ROUTE_FILE_SHA256,
        "source_adapter_file_sha256": EXPECTED_ADAPTER_FILE_SHA256,
        "source_adapter_review_file_sha256": (EXPECTED_ADAPTER_REVIEW_FILE_SHA256),
        "source_adapter_sha256": EXPECTED_ADAPTER_SHA256,
        "source_adapter_review_sha256": EXPECTED_ADAPTER_REVIEW_SHA256,
        "qualified_source_files_sha256": {
            "canonical_ik_adapter": EXPECTED_CURRENT_ADAPTER_SOURCE_SHA256,
            "physics_backend": EXPECTED_CURRENT_BACKEND_SOURCE_SHA256,
            "system_manifest": EXPECTED_SYSTEM_MANIFEST_SHA256,
            "canonical_ik_solver": EXPECTED_IK_SOURCE_SHA256,
            "simulation_context": EXPECTED_CONTEXT_SOURCE_SHA256,
            "pinned_model_loader": EXPECTED_PINNED_MODEL_SOURCE_SHA256,
            "qualification": _file_sha(qualification_source_path),
        },
        "evaluation": evaluation,
        "arm297_replay_permitted": False,
        "arm298_attempt_authorized": False,
        **ZERO_AUTHORITY,
        "next_required_stage": ("INDEPENDENT_ARM298_CONTINUITY_QUALIFICATION_REVIEW"),
        "limitations": [
            "qualification_runs_forward_kinematics_and_inverse_kinematics_only",
            "qualification_does_not_start_isaac_or_step_physics",
            "qualification_does_not_check_clearance_tool_key_metrics_or_root_drift",
            "qualification_does_not_authorize_or_claim_an_attempt",
            "qualification_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "qualification_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm297-status", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--adapter-definition", type=Path, required=True)
    parser.add_argument("--adapter-review", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_qualification(
        arm297_status_path=args.arm297_status,
        route_path=args.route,
        adapter_definition_path=args.adapter_definition,
        adapter_review_path=args.adapter_review,
        repo_root=args.repo_root.resolve(strict=True),
        qualification_source_path=Path(__file__).resolve(),
    )
    if args.output.exists():
        raise Arm298ContinuityQualificationError(
            "qualification output exists; overwrite refused"
        )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
