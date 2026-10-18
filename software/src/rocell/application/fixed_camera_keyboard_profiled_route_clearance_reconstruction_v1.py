"""Reconstruct exact profile-separated route clearance from bounded partitions.

The input evaluator has already performed discrete and continuous collision
checks.  This boundary independently verifies its sealed report against the
partition plans, proves exact ordered ownership of all 328 route segments, and
recomputes the limiting clearance for each attachment profile.  A successful
route reconstruction remains blocked on a fresh observed entry and grants no
execution authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_partition_collision_evaluator_v1 import (
    SCHEMA as EVALUATION_SCHEMA,
    STATUS_CLEAR as EVALUATION_CLEAR,
    STATUS_COLLISION as EVALUATION_COLLISION,
    STATUS_INCOMPLETE as EVALUATION_INCOMPLETE,
)
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY,
    SCHEMA as PARTITION_SCHEMA,
)


SCHEMA = "rocell.fixed_camera_keyboard_profiled_route_clearance_reconstruction.v1"
STATUS_READY = "ROUTE_CLEARANCE_RECONSTRUCTED_FRESH_ENTRY_REQUIRED"
STATUS_REJECTED = "REJECTED_ROUTE_COLLISION_DETECTED"
STATUS_BLOCKED = "BLOCKED_ROUTE_CLEARANCE_EVIDENCE_INCOMPLETE"
EXPECTED_ROUTE_SEGMENT_COUNT = 328
ZERO_AUTHORITY: Mapping[str, object] = {
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "physical_authority": False,
}


class FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(ValueError):
    """Sealed evaluation, route ownership, or profile lineage differs."""


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
        raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
            "route clearance evidence is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any], hash_field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    core = dict(value)
    supplied = core.pop(hash_field, None)
    if not isinstance(supplied, str) or supplied != _sha(core):
        raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
            f"{label} hash differs"
        )
    return dict(value)


def _profile_map(value: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
            f"{label} must contain the exact supported profile set"
        )


def reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute ordered route coverage and profile-specific clearance minima."""

    _profile_map(partition_documents, "partition_documents")
    evaluation = _sealed(
        collision_evaluation,
        "profiled_partition_collision_evaluation_sha256",
        "profiled partition collision evaluation",
    )
    profiles = evaluation.get("profiles")
    _profile_map(profiles, "collision evaluation profiles")
    if evaluation.get("schema") != EVALUATION_SCHEMA:
        raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
            "collision evaluation schema differs"
        )

    reconstructed: dict[str, Any] = {}
    profile_statuses: list[str] = []
    overall_minimum: float | None = None
    overall_limiter: dict[str, Any] | None = None
    for profile_name in SUPPORTED_PROFILES:
        document = _sealed(
            partition_documents[profile_name],
            "partitioned_typing_collision_intake_sha256",
            f"partition document {profile_name}",
        )
        profile = profiles[profile_name]
        if not isinstance(profile, Mapping):
            raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                f"profile evaluation is malformed: {profile_name}"
            )
        partitions = document.get("partitions")
        boundary_lineage = document.get("boundary_lineage")
        reports = profile.get("partitions")
        slots = document.get("required_evidence_slots")
        if (
            document.get("schema") != PARTITION_SCHEMA
            or document.get("status") != PARTITION_READY
            or not isinstance(partitions, list)
            or not isinstance(boundary_lineage, list)
            or len(boundary_lineage) != len(partitions) - 1
            or not isinstance(reports, list)
            or len(partitions) != len(reports)
            or profile.get("profile") != profile_name
            or profile.get("partition_count") != len(partitions)
            or profile.get("source_partitioned_typing_collision_intake_sha256")
            != document["partitioned_typing_collision_intake_sha256"]
            or profile.get("installed_collision_profile_sha256")
            != document.get("installed_collision_profile_sha256")
            or not isinstance(slots, Mapping)
            or slots.get("route_segment_count") != EXPECTED_ROUTE_SEGMENT_COUNT
        ):
            raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                f"partition/evaluation lineage differs: {profile_name}"
            )

        expected_start = 0
        previous_partition: Mapping[str, Any] | None = None
        previous_plan: list[Mapping[str, Any]] | None = None
        minimum: float | None = None
        limiter: dict[str, Any] | None = None
        all_determinate = True
        for partition_index, (partition, report) in enumerate(
            zip(partitions, reports, strict=True)
        ):
            if not isinstance(partition, Mapping) or not isinstance(report, Mapping):
                raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                    f"partition report is malformed: {profile_name}:{partition_index}"
                )
            plan = partition.get("bounded_joint_sample_plan")
            sweep = report.get("conservative_sweep_qualification")
            start = partition.get("source_result_start_index")
            end = partition.get("source_result_end_index_exclusive")
            count = partition.get("source_result_count")
            if (
                partition.get("partition_index") != partition_index
                or report.get("partition_index") != partition_index
                or report.get("partition_intake_sha256")
                != partition.get("partition_intake_sha256")
                or start != expected_start
                or not isinstance(end, int)
                or isinstance(end, bool)
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count <= 0
                or end != start + count
                or not isinstance(plan, list)
                or len(plan) != count + 1
                or any(not isinstance(sample, Mapping) for sample in plan)
                or report.get("sample_count") != len(plan)
                or report.get("segment_count") != count
            ):
                raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                    f"route segment ownership differs: {profile_name}:{partition_index}"
                )
            partition_core = dict(partition)
            partition_hash = partition_core.pop("partition_intake_sha256", None)
            if partition_hash != _sha(partition_core):
                raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                    f"partition intake hash differs: {profile_name}:{partition_index}"
                )
            if previous_partition is not None and previous_plan is not None:
                boundary = boundary_lineage[partition_index - 1]
                if not isinstance(boundary, Mapping):
                    raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                        f"partition boundary is malformed: {profile_name}:{partition_index - 1}"
                    )
                boundary_core = dict(boundary)
                boundary_hash = boundary_core.pop("boundary_lineage_sha256", None)
                predecessor = previous_plan[-1]
                successor = plan[0]
                if (
                    boundary_hash != _sha(boundary_core)
                    or boundary.get("predecessor_partition_index")
                    != partition_index - 1
                    or boundary.get("successor_partition_index") != partition_index
                    or boundary.get("source_boundary_result_index") != start - 1
                    or boundary.get("predecessor_terminal_sample_sha256")
                    != _sha(predecessor)
                    or boundary.get("successor_boundary_recheck_sample_sha256")
                    != _sha(successor)
                    or boundary.get("maximum_joint_difference_rad") != 0.0
                    or boundary.get("boundary_recheck_required") is not True
                    or boundary.get("extra_zero_length_sweep_envelope_required")
                    is not False
                    or boundary.get("first_successor_route_segment_owned_by_partition")
                    != partition_index
                    or predecessor.get("joint_positions_rad")
                    != successor.get("joint_positions_rad")
                    or previous_partition.get("source_result_end_index_exclusive")
                    != start
                ):
                    raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                        f"partition boundary lineage differs: {profile_name}:{partition_index - 1}"
                    )
            expected_start = end
            previous_partition = partition
            previous_plan = plan

            if profile.get("status") != EVALUATION_CLEAR:
                continue
            if not isinstance(sweep, Mapping):
                raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                    f"clear partition lacks sweep evidence: {profile_name}:{partition_index}"
                )
            segment_reports = sweep.get("segment_reports")
            if (
                sweep.get("status")
                != "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"
                or sweep.get("segment_count") != count
                or not isinstance(segment_reports, list)
                or len(segment_reports) != count
                or sweep.get("all_conservative_segment_sweeps_clear") is not True
            ):
                raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                    f"clear partition sweep coverage differs: {profile_name}:{partition_index}"
                )
            computed_partition_minimum: float | None = None
            computed_partition_sequence: int | None = None
            computed_partition_pair: list[str] | None = None
            for local_sequence, (segment, first, second) in enumerate(
                zip(segment_reports, plan[:-1], plan[1:], strict=True)
            ):
                global_sequence = start + local_sequence
                value = segment.get("minimum_clearance_lower_bound_mm")
                pair = segment.get("clearance_limiting_body_pair")
                if (
                    segment.get("segment_sequence") != local_sequence
                    or segment.get("start_sample_sha256") != _sha(first)
                    or segment.get("end_sample_sha256") != _sha(second)
                    or second.get("source_segment_index") != global_sequence
                    or segment.get("clearance_lower_bound_status") != "CLEAR"
                    or isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or float(value) < 0.0
                    or not isinstance(pair, list)
                    or len(pair) != 2
                    or not all(isinstance(item, str) and item for item in pair)
                ):
                    raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                        f"segment clearance lineage differs: {profile_name}:{global_sequence}"
                    )
                numeric = float(value)
                if (
                    computed_partition_minimum is None
                    or numeric < computed_partition_minimum
                ):
                    computed_partition_minimum = numeric
                    computed_partition_sequence = local_sequence
                    computed_partition_pair = list(pair)
                if minimum is None or numeric < minimum:
                    minimum = numeric
                    limiter = {
                        "partition_index": partition_index,
                        "partition_segment_sequence": local_sequence,
                        "source_segment_index": global_sequence,
                        "body_pair": list(pair),
                    }
            if (
                sweep.get("minimum_clearance_lower_bound_mm")
                != computed_partition_minimum
                or sweep.get("limiting_segment_sequence") != computed_partition_sequence
                or sweep.get("limiting_body_pair") != computed_partition_pair
                or sweep.get("all_segment_clearance_bounds_determinate") is not True
            ):
                raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                    f"partition clearance aggregate differs: {profile_name}:{partition_index}"
                )
            all_determinate = all_determinate and True

        if expected_start != EXPECTED_ROUTE_SEGMENT_COUNT:
            raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                f"route segment coverage differs: {profile_name}"
            )
        clear = profile.get("status") == EVALUATION_CLEAR
        if profile.get("status") not in {
            EVALUATION_CLEAR,
            EVALUATION_COLLISION,
            EVALUATION_INCOMPLETE,
        }:
            raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
                f"profile evaluation status differs: {profile_name}"
            )
        profile_statuses.append(profile["status"])
        reconstructed[profile_name] = {
            "profile": profile_name,
            "installed_collision_profile_sha256": profile[
                "installed_collision_profile_sha256"
            ],
            "source_partitioned_typing_collision_intake_sha256": document[
                "partitioned_typing_collision_intake_sha256"
            ],
            "partition_count": len(partitions),
            "route_segment_count": expected_start,
            "route_segment_start_index": 0,
            "route_segment_end_index_exclusive": expected_start,
            "minimum_clearance_lower_bound_mm": minimum if clear else None,
            "limiting_route_segment": limiter if clear else None,
            "all_segment_clearance_bounds_determinate": all_determinate and clear,
            "all_route_segments_continuously_clear": clear,
        }
        if (
            clear
            and minimum is not None
            and (overall_minimum is None or minimum < overall_minimum)
        ):
            overall_minimum = minimum
            overall_limiter = {"profile": profile_name, **(limiter or {})}

    expected_evaluation_status = (
        EVALUATION_COLLISION
        if EVALUATION_COLLISION in profile_statuses
        else EVALUATION_INCOMPLETE
        if EVALUATION_INCOMPLETE in profile_statuses
        else EVALUATION_CLEAR
    )
    evaluation_status = evaluation.get("status")
    if evaluation_status != expected_evaluation_status:
        raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
            "aggregate collision evaluation status differs from profile statuses"
        )
    if evaluation_status == EVALUATION_COLLISION:
        status = STATUS_REJECTED
        disposition = "REJECT"
        blockers = ["PROFILE_BOUND_ROUTE_COLLISION_DETECTED"]
        next_stage = "CORRECT_ROUTE_OR_INSTALLED_GEOMETRY"
    elif evaluation_status == EVALUATION_INCOMPLETE:
        status = STATUS_BLOCKED
        disposition = "BLOCKED"
        blockers = ["PROFILE_BOUND_ROUTE_CLEARANCE_EVIDENCE_INCOMPLETE"]
        next_stage = "SUPPLY_COMPLETE_PROFILE_BOUND_COLLISION_EVIDENCE"
    elif evaluation_status == EVALUATION_CLEAR:
        status = STATUS_READY
        disposition = "BLOCKED"
        blockers = ["FRESH_OBSERVED_START_AND_ENTRY_QUALIFICATION_REQUIRED"]
        next_stage = "QUALIFY_FRESH_OBSERVED_START_AND_ENTRY"
    else:
        raise FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error(
            "collision evaluation status differs"
        )
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "disposition": disposition,
        "source_profiled_partition_collision_evaluation_sha256": evaluation[
            "profiled_partition_collision_evaluation_sha256"
        ],
        "calibration_snapshot_sha256": evaluation["calibration_snapshot_sha256"],
        "build_snapshot_sha256": evaluation["build_snapshot_sha256"],
        "kinematic_model_sha256": evaluation["kinematic_model_sha256"],
        "profiles": reconstructed,
        "profile_separation_preserved": True,
        "expected_route_segment_count_per_profile": EXPECTED_ROUTE_SEGMENT_COUNT,
        "minimum_clearance_lower_bound_mm_across_profiles": overall_minimum,
        "limiting_profile_route_segment": overall_limiter,
        "fresh_observed_start_state_present": False,
        "observed_entry_continuous_clearance_proven": False,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "profiled_route_clearance_reconstruction_sha256": _sha(core)}


__all__ = [
    "SCHEMA",
    "STATUS_READY",
    "STATUS_REJECTED",
    "STATUS_BLOCKED",
    "EXPECTED_ROUTE_SEGMENT_COUNT",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error",
    "reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1",
]
