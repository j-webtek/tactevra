"""Evaluate admitted collision evidence over both profile-bound partitions.

This boundary joins the immutable partition plans to the reviewed typed evidence,
runs discrete FK collision checks, and then runs conservative adjacent-sample
sweeps only when the discrete checks are clear.  It is offline and produces no
controller commands or physical authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.kinematics import ARM_JOINT_NAMES

from .bounded_segment_collision_qualification import BoundedJointConfigurationSample
from .conservative_segment_sweep_qualification import (
    evaluate_conservative_segment_sweeps_from_plan,
)
from .context import SimulationContext
from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_collision_evidence_admission_v1 import (
    AdmittedProfileCollisionEvidenceV1,
)
from .fk_collision_pose_adapter import derive_and_evaluate_fk_waypoint_collisions
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .measured_trajectory_screening import SCHEMA as TRAJECTORY_SCREENING_SCHEMA
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY_STATUS,
    SCHEMA as PARTITION_SCHEMA,
)


SCHEMA = "rocell.fixed_camera_keyboard_profiled_partition_collision_evaluation.v1"
STATUS_CLEAR = "PROFILED_PARTITION_COLLISIONS_CLEAR_RELEASE_GATES_REMAIN"
STATUS_COLLISION = "BLOCKED_PROFILED_PARTITION_COLLISION_DETECTED"
STATUS_INCOMPLETE = "BLOCKED_PROFILED_PARTITION_COLLISION_EVIDENCE_INCOMPLETE"
MAX_PARTITIONS_PER_PROFILE = 64
ZERO_AUTHORITY: Mapping[str, object] = {
    "installed_geometry_collision_screening_executed": True,
    "fresh_observed_start_state_present": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(ValueError):
    """Partition plans, evidence, or profile lineage are crossed or malformed."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _profile_map(value: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
            f"{label} must contain the exact supported profile set"
        )


def _decode_plan(
    raw: object, partition_index: int
) -> tuple[BoundedJointConfigurationSample, ...]:
    if not isinstance(raw, list) or len(raw) < 2:
        raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
            f"partition {partition_index} bounded sample plan is incomplete"
        )
    plan: list[BoundedJointConfigurationSample] = []
    for sequence, row in enumerate(raw):
        if not isinstance(row, Mapping) or set(row) != {
            "sample_sequence",
            "sample_id",
            "source_segment_index",
            "subdivision_index",
            "subdivision_count",
            "interpolation_ratio",
            "joint_positions_rad",
        }:
            raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                f"partition {partition_index} sample {sequence} has a malformed plan"
            )
        for field in (
            "sample_sequence",
            "source_segment_index",
            "subdivision_index",
            "subdivision_count",
        ):
            if isinstance(row[field], bool) or not isinstance(row[field], int):
                raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                    f"partition {partition_index} sample {sequence} {field} is not an integer"
                )
        ratio = row["interpolation_ratio"]
        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(float(ratio))
            or not 0.0 <= float(ratio) <= 1.0
            or row["subdivision_count"] < 1
            or not 0 <= row["subdivision_index"] <= row["subdivision_count"]
        ):
            raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                f"partition {partition_index} sample {sequence} subdivision is invalid"
            )
        joints = row["joint_positions_rad"]
        if not isinstance(joints, Mapping) or set(joints) != set(ARM_JOINT_NAMES):
            raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                f"partition {partition_index} sample {sequence} joint coverage differs"
            )
        values: dict[str, float] = {}
        for name in ARM_JOINT_NAMES:
            value = joints[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                    f"partition {partition_index} sample {sequence} joint is not numeric"
                )
            values[name] = float(value)
            if not math.isfinite(values[name]):
                raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                    f"partition {partition_index} sample {sequence} joint is not finite"
                )
        try:
            sample = BoundedJointConfigurationSample(
                row["sample_sequence"],
                row["source_segment_index"],
                row["subdivision_index"],
                row["subdivision_count"],
                float(ratio),
                values,
            )
        except (TypeError, ValueError) as exc:
            raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                f"partition {partition_index} sample {sequence} is invalid"
            ) from exc
        if sample.sample_sequence != sequence or sample.to_dict() != dict(row):
            raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                f"partition {partition_index} sample {sequence} is noncanonical"
            )
        plan.append(sample)
    return tuple(plan)


def _evaluate_discrete_partition(
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    installed_profile: InstalledCollisionGeometryProfile,
    partition_document: Mapping[str, Any],
    partition: Mapping[str, Any],
    plan: Sequence[BoundedJointConfigurationSample],
    evidence: AdmittedProfileCollisionEvidenceV1,
    partition_index: int,
) -> Mapping[str, Any]:
    expanded_core: dict[str, Any] = {
        "schema": TRAJECTORY_SCREENING_SCHEMA,
        "calibration_snapshot_sha256": partition_document[
            "calibration_snapshot_sha256"
        ],
        "build_snapshot_sha256": partition_document["build_snapshot_sha256"],
        "kinematic_model_sha256": partition_document["kinematic_model_sha256"],
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "collision_contract_sha256": installed_profile.contract.content_hash,
        "ik_all_waypoints_accepted": True,
        "waypoints": [
            {
                "sequence": item.sample_sequence,
                "sample_id": item.sample_id,
                "source_segment_index": item.source_segment_index,
                "subdivision_index": item.subdivision_index,
                "subdivision_count": item.subdivision_count,
                "interpolation_ratio": item.interpolation_ratio,
            }
            for item in plan
        ],
        "joint_results": [
            {
                "waypoint_sequence": item.sample_sequence,
                "accepted": True,
                "solution_arm_joint_positions_rad": dict(item.joint_positions_rad),
            }
            for item in plan
        ],
        "source_trajectory_screening_sha256": partition_document[
            "typing_trajectory_ik_screen_sha256"
        ],
        "partition_intake_sha256": partition["partition_intake_sha256"],
    }
    expanded = {**expanded_core, "trajectory_screening_sha256": _sha(expanded_core)}
    return derive_and_evaluate_fk_waypoint_collisions(
        context,
        snapshot,
        installed_profile,
        expanded,
        evidence.attachment_bindings,
        evidence.configuration_geometry_by_partition[partition_index],
    )


def evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
    context: SimulationContext,
    calibration_snapshot: PlannerCalibrationSnapshot,
    partition_documents: Mapping[str, Mapping[str, Any]],
    admitted_profiles: Mapping[str, AdmittedProfileCollisionEvidenceV1],
    installed_collision_profiles: Mapping[str, InstalledCollisionGeometryProfile],
) -> dict[str, Any]:
    """Evaluate every admitted partition for both attachment profiles."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(calibration_snapshot, PlannerCalibrationSnapshot):
        raise TypeError("calibration_snapshot must be a PlannerCalibrationSnapshot")
    for value, label in (
        (partition_documents, "partition_documents"),
        (admitted_profiles, "admitted_profiles"),
        (installed_collision_profiles, "installed_collision_profiles"),
    ):
        _profile_map(value, label)

    profile_reports: dict[str, Any] = {}
    aggregate_collision = False
    aggregate_incomplete = False
    for profile_name in SUPPORTED_PROFILES:
        document = partition_documents[profile_name]
        evidence = admitted_profiles[profile_name]
        installed = installed_collision_profiles[profile_name]
        if not isinstance(document, Mapping):
            raise TypeError("partition document must be an object")
        if not isinstance(evidence, AdmittedProfileCollisionEvidenceV1):
            raise TypeError("admitted profile has an unsupported type")
        if not isinstance(installed, InstalledCollisionGeometryProfile):
            raise TypeError("installed collision profile has an unsupported type")
        unsigned = dict(document)
        claimed = unsigned.pop("partitioned_typing_collision_intake_sha256", None)
        partitions = document.get("partitions")
        if (
            evidence.profile != profile_name
            or document.get("schema") != PARTITION_SCHEMA
            or document.get("status") != PARTITION_READY_STATUS
            or claimed != _sha(unsigned)
            or document.get("calibration_snapshot_sha256")
            != calibration_snapshot.snapshot_sha256
            or document.get("build_snapshot_sha256") != context.snapshot.snapshot_hash
            or document.get("kinematic_model_sha256") != context.scenario.model_sha256
            or document.get("installed_collision_profile_sha256")
            != installed.content_sha256
            or document.get("collision_contract_sha256")
            != installed.contract.content_hash
            or not isinstance(partitions, list)
            or not 1 <= len(partitions) <= MAX_PARTITIONS_PER_PROFILE
            or len(evidence.configuration_geometry_by_partition) != len(partitions)
            or len(evidence.sweep_envelopes_by_partition) != len(partitions)
        ):
            raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                f"partition, evidence, calibration, or profile lineage differs: {profile_name}"
            )

        boundary_lineage = document.get("boundary_lineage")
        if (
            not isinstance(boundary_lineage, list)
            or len(boundary_lineage) != len(partitions) - 1
        ):
            raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                f"partition boundary lineage coverage differs: {profile_name}"
            )

        partition_reports: list[dict[str, Any]] = []
        profile_collision = False
        profile_incomplete = False
        previous_partition: Mapping[str, Any] | None = None
        previous_terminal: BoundedJointConfigurationSample | None = None
        for index, partition in enumerate(partitions):
            if (
                not isinstance(partition, Mapping)
                or partition.get("partition_index") != index
            ):
                raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                    f"partition ordering differs: {profile_name}"
                )
            core = dict(partition)
            intake_hash = core.pop("partition_intake_sha256", None)
            if intake_hash != _sha(core):
                raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                    f"partition intake hash is invalid: {profile_name}:{index}"
                )
            plan = _decode_plan(partition.get("bounded_joint_sample_plan"), index)
            if (
                partition.get("bounded_sample_count") != len(plan)
                or partition.get("first_sample_sha256") != plan[0].content_sha256
                or partition.get("terminal_sample_sha256") != plan[-1].content_sha256
                or len(evidence.configuration_geometry_by_partition[index]) != len(plan)
                or len(evidence.sweep_envelopes_by_partition[index]) != len(plan) - 1
            ):
                raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                    f"partition evidence coverage or boundary lineage differs: {profile_name}:{index}"
                )
            if previous_terminal is not None and previous_partition is not None:
                boundary = boundary_lineage[index - 1]
                if not isinstance(boundary, Mapping):
                    raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                        f"partition boundary lineage is malformed: {profile_name}:{index - 1}"
                    )
                boundary_core = dict(boundary)
                boundary_hash = boundary_core.pop("boundary_lineage_sha256", None)
                maximum_delta = max(
                    abs(
                        previous_terminal.joint_positions_rad[name]
                        - plan[0].joint_positions_rad[name]
                    )
                    for name in ARM_JOINT_NAMES
                )
                if (
                    boundary_hash != _sha(boundary_core)
                    or boundary.get("predecessor_partition_index") != index - 1
                    or boundary.get("successor_partition_index") != index
                    or boundary.get("source_boundary_result_index")
                    != partition.get("source_result_start_index") - 1
                    or boundary.get("predecessor_terminal_sample_sha256")
                    != previous_terminal.content_sha256
                    or boundary.get("successor_boundary_recheck_sample_sha256")
                    != plan[0].content_sha256
                    or boundary.get("maximum_joint_difference_rad") != 0.0
                    or maximum_delta != 0.0
                    or boundary.get("boundary_recheck_required") is not True
                    or boundary.get("extra_zero_length_sweep_envelope_required")
                    is not False
                    or boundary.get("first_successor_route_segment_owned_by_partition")
                    != index
                    or previous_partition.get("source_result_end_index_exclusive")
                    != partition.get("source_result_start_index")
                ):
                    raise FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error(
                        f"partition boundary lineage differs: {profile_name}:{index - 1}"
                    )
            previous_partition = partition
            previous_terminal = plan[-1]
            discrete = _evaluate_discrete_partition(
                context,
                calibration_snapshot,
                installed,
                document,
                partition,
                plan,
                evidence,
                index,
            )
            discrete_status = discrete.get("status")
            sweep: Mapping[str, Any] | None = None
            partition_collision = False
            partition_incomplete = False
            if discrete_status == "DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED":
                sweep = evaluate_conservative_segment_sweeps_from_plan(
                    context,
                    installed,
                    plan,
                    discrete,
                    evidence.attachment_bindings,
                    evidence.sweep_envelopes_by_partition[index],
                )
                if sweep.get("status") == "BLOCKED_CONSERVATIVE_SWEEP_COLLISION":
                    partition_collision = True
                elif (
                    sweep.get("status")
                    != "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"
                ):
                    partition_incomplete = True
            elif discrete_status == "BLOCKED_COLLISION_DETECTED":
                partition_collision = True
            else:
                partition_incomplete = True
            profile_collision = profile_collision or partition_collision
            profile_incomplete = profile_incomplete or partition_incomplete
            partition_reports.append(
                {
                    "partition_index": index,
                    "partition_intake_sha256": intake_hash,
                    "sample_count": len(plan),
                    "segment_count": len(plan) - 1,
                    "discrete_collision_qualification": discrete,
                    "conservative_sweep_qualification": sweep,
                    "collision_detected": partition_collision,
                    "evidence_incomplete": partition_incomplete,
                }
            )

        profile_status = (
            STATUS_COLLISION
            if profile_collision
            else STATUS_INCOMPLETE
            if profile_incomplete
            else STATUS_CLEAR
        )
        aggregate_collision = aggregate_collision or profile_collision
        aggregate_incomplete = aggregate_incomplete or profile_incomplete
        profile_reports[profile_name] = {
            "profile": profile_name,
            "status": profile_status,
            "installed_collision_profile_sha256": installed.content_sha256,
            "source_partitioned_typing_collision_intake_sha256": claimed,
            "source_completion_sha256": evidence.completion_sha256,
            "source_review_sha256": evidence.review_sha256,
            "partition_count": len(partition_reports),
            "partitions": partition_reports,
        }

    status = (
        STATUS_COLLISION
        if aggregate_collision
        else STATUS_INCOMPLETE
        if aggregate_incomplete
        else STATUS_CLEAR
    )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "calibration_snapshot_sha256": calibration_snapshot.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "profiles": profile_reports,
        "profile_separation_preserved": True,
        "all_profiled_partitions_clear": status == STATUS_CLEAR,
        "blockers": (
            ["PROFILE_BOUND_COLLISION_DETECTED"]
            if status == STATUS_COLLISION
            else ["PROFILE_BOUND_COLLISION_EVIDENCE_INCOMPLETE"]
            if status == STATUS_INCOMPLETE
            else ["FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION"]
        ),
        "next_required_stage": (
            "CORRECT_ROUTE_OR_INSTALLED_GEOMETRY"
            if status == STATUS_COLLISION
            else "SUPPLY_COMPLETE_PROFILE_BOUND_COLLISION_EVIDENCE"
            if status == STATUS_INCOMPLETE
            else "RECONSTRUCT_CROSS_PARTITION_MINIMUM_CLEARANCE_REPORT"
        ),
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**report, "profiled_partition_collision_evaluation_sha256": _sha(report)}


__all__ = [
    "SCHEMA",
    "STATUS_CLEAR",
    "STATUS_COLLISION",
    "STATUS_INCOMPLETE",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error",
    "evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1",
]
