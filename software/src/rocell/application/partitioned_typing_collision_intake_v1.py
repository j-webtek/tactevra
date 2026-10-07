"""Profile-bound evidence intake for partitioned accepted typing routes.

This adapter accepts only a complete, hash-valid canonical IK report and turns
its long route into bounded collision-evidence partitions.  It enumerates the
configuration and conservative sweep evidence required by each partition while
preserving an exact, rechecked boundary between neighboring partitions.

It does not execute collision checks, create controller commands, or grant
physical authority.  Missing installed geometry remains an explicit blocker.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from rocell.simulation.collision import CollisionBindingMode

from ._pinned_model import load_pinned_urdf
from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext, revalidate_simulation_context
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .partitioned_bounded_segment_collision_v1 import (
    BoundedCollisionPartitionV1,
    build_partitioned_bounded_joint_sample_plans_from_results,
)
from .typing_collision_intake_v1 import _profile_matches_context
from .typing_trajectory_ik_screen_v1 import (
    READY_STATUS as IK_READY_STATUS,
    SCHEMA as IK_SCHEMA,
)


SCHEMA = "rocell.partitioned_typing_collision_intake.v1"
READY_STATUS = "READY_FOR_PARTITIONED_PROFILE_BOUND_COLLISION_EVIDENCE"
PROFILE_REQUIRED_STATUS = "BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED"


class PartitionedTypingCollisionIntakeV1Error(ValueError):
    """Partitioned route lineage or collision-profile identity is not exact."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validated_ik_report(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PartitionedTypingCollisionIntakeV1Error("ik_screen must be an object")
    report = dict(value)
    digest = report.pop("typing_trajectory_ik_screen_sha256", None)
    if report.get("schema") != IK_SCHEMA:
        raise PartitionedTypingCollisionIntakeV1Error("typing IK screen schema mismatch")
    if not isinstance(digest, str) or digest != _sha256(report):
        raise PartitionedTypingCollisionIntakeV1Error(
            "typing IK screen hash is invalid"
        )
    return dict(value)


def _sample_hash(partition: BoundedCollisionPartitionV1, index: int) -> str:
    return partition.samples[index].content_sha256


def prepare_partitioned_typing_collision_intake_v1(
    ik_screen: Mapping[str, Any],
    context: SimulationContext,
    *,
    expected_execution_plan_sha256: str,
    expected_trajectory_plan_sha256: str,
    expected_calibration_snapshot_sha256: str,
    installed_profile: InstalledCollisionGeometryProfile | None = None,
    sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    maximum_partitions: int = 64,
) -> dict[str, Any]:
    """Enumerate exact profile-bound evidence slots for a long accepted route."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if installed_profile is not None and not isinstance(
        installed_profile, InstalledCollisionGeometryProfile
    ):
        raise TypeError(
            "installed_profile must be an InstalledCollisionGeometryProfile"
        )
    expected_hashes = (
        expected_execution_plan_sha256,
        expected_trajectory_plan_sha256,
        expected_calibration_snapshot_sha256,
    )
    if any(
        not isinstance(value, str) or len(value) != 64 for value in expected_hashes
    ):
        raise PartitionedTypingCollisionIntakeV1Error(
            "expected lineage hashes must be SHA-256 strings"
        )
    revalidate_simulation_context(context)
    ik = _validated_ik_report(ik_screen)
    if (
        ik.get("status") != IK_READY_STATUS
        or ik.get("typing_execution_plan_sha256")
        != expected_execution_plan_sha256
        or ik.get("typing_trajectory_plan_sha256")
        != expected_trajectory_plan_sha256
        or ik.get("calibration_snapshot_sha256")
        != expected_calibration_snapshot_sha256
        or ik.get("build_snapshot_sha256") != context.snapshot.snapshot_hash
        or ik.get("kinematic_model_sha256") != context.scenario.model_sha256
        or ik.get("ik_all_samples_accepted") is not True
    ):
        raise PartitionedTypingCollisionIntakeV1Error(
            "typing plan, IK screen, calibration, build, or model lineage differs"
        )
    seed = ik.get("seed")
    results = ik.get("joint_results")
    if (
        not isinstance(seed, Mapping)
        or seed.get("source_kind") != "SYNTHETIC_OFFLINE"
        or not isinstance(results, list)
        or not results
        or ik.get("sample_count") != len(results)
        or ik.get("evaluated_sample_count") != len(results)
    ):
        raise PartitionedTypingCollisionIntakeV1Error(
            "typing IK seed classification or exact result coverage is invalid"
        )

    policy = sampling_policy or BoundedSegmentSamplingPolicy()
    partitions = build_partitioned_bounded_joint_sample_plans_from_results(
        seed.get("joint_positions_rad"),
        results,
        policy,
        maximum_partitions=maximum_partitions,
    )
    readiness = assess_current_collision_readiness(context)
    if installed_profile is None:
        contract = readiness.contract
        status = PROFILE_REQUIRED_STATUS
        profile_sha256 = None
        accepted_source_hashes: list[str] = []
        blockers = [
            "INSTALLED_COLLISION_PROFILE_REQUIRED",
            "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
        ]
        next_stage = "LOAD_EXACT_MEASURED_INSTALLED_COLLISION_PROFILE"
    else:
        if not _profile_matches_context(installed_profile, context):
            raise PartitionedTypingCollisionIntakeV1Error(
                "installed collision profile differs from the active context"
            )
        contract = installed_profile.contract
        status = READY_STATUS
        profile_sha256 = installed_profile.content_sha256
        accepted_source_hashes = sorted(installed_profile.source_bindings.values())
        blockers = [
            "MEASURED_RIGID_ATTACHMENT_BINDINGS_REQUIRED",
            "CONFIGURATION_GEOMETRY_REQUIRED_FOR_EVERY_PARTITION_SAMPLE",
            "CONSERVATIVE_SWEEP_ENVELOPES_REQUIRED_FOR_EVERY_ROUTE_SEGMENT",
            "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
        ]
        next_stage = "SUPPLY_PARTITIONED_PROFILE_BOUND_COLLISION_EVIDENCE"

    model_link_names = set(
        load_pinned_urdf(
            context.scenario.model_path,
            context.scenario.model_sha256,
        ).model.link_names
    )
    rigid_attachment_frames = sorted(
        {
            body.parent_frame
            for body in contract.bodies
            if body.binding_mode is CollisionBindingMode.RIGID_FRAME
            and body.parent_frame not in model_link_names
            and body.parent_frame != contract.root_frame
        }
    )
    configuration_body_ids = sorted(
        body.body_id
        for body in contract.bodies
        if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
    )

    partition_reports: list[dict[str, Any]] = []
    for partition in partitions:
        adjacent_count = max(0, len(partition.samples) - 1)
        slots = {
            "configuration_sample_count": len(partition.samples),
            "configuration_body_count_per_sample": len(configuration_body_ids),
            "configuration_geometry_binding_count": (
                len(partition.samples) * len(configuration_body_ids)
            ),
            "adjacent_sample_segment_count": adjacent_count,
            "configuration_sweep_envelope_count": (
                adjacent_count * len(configuration_body_ids)
            ),
        }
        partition_core = {
            "partition_index": partition.partition_index,
            "partition_sha256": partition.content_sha256,
            "source_result_start_index": partition.source_result_start_index,
            "source_result_end_index_exclusive": (
                partition.source_result_end_index_exclusive
            ),
            "source_result_count": partition.source_result_count,
            "installed_collision_profile_sha256": profile_sha256,
            "collision_contract_sha256": contract.content_hash,
            "first_sample_sha256": _sample_hash(partition, 0),
            "terminal_sample_sha256": _sample_hash(partition, -1),
            "bounded_sample_count": len(partition.samples),
            "bounded_joint_sample_plan": [
                sample.to_dict() for sample in partition.samples
            ],
            "required_evidence_slots": slots,
        }
        partition_reports.append(
            {
                **partition_core,
                "partition_intake_sha256": _sha256(partition_core),
            }
        )

    boundary_lineage: list[dict[str, Any]] = []
    for predecessor, successor in zip(partitions, partitions[1:], strict=False):
        terminal = predecessor.samples[-1]
        recheck = successor.samples[0]
        maximum_delta = max(
            abs(
                float(terminal.joint_positions_rad[name])
                - float(recheck.joint_positions_rad[name])
            )
            for name in terminal.joint_positions_rad
        )
        if not math.isfinite(maximum_delta) or maximum_delta != 0.0:
            raise PartitionedTypingCollisionIntakeV1Error(
                "partition boundary recheck differs from predecessor terminal"
            )
        boundary_core = {
            "predecessor_partition_index": predecessor.partition_index,
            "successor_partition_index": successor.partition_index,
            "source_boundary_result_index": (
                successor.source_result_start_index - 1
            ),
            "predecessor_terminal_sample_sha256": terminal.content_sha256,
            "successor_boundary_recheck_sample_sha256": recheck.content_sha256,
            "maximum_joint_difference_rad": maximum_delta,
            "boundary_recheck_required": True,
            "extra_zero_length_sweep_envelope_required": False,
            "first_successor_route_segment_owned_by_partition": (
                successor.partition_index
            ),
        }
        boundary_lineage.append(
            {**boundary_core, "boundary_lineage_sha256": _sha256(boundary_core)}
        )

    total_samples = sum(len(partition.samples) for partition in partitions)
    total_segments = sum(max(0, len(partition.samples) - 1) for partition in partitions)
    total_slots = {
        "partition_count": len(partitions),
        "partition_sample_count_including_boundary_rechecks": total_samples,
        "unique_route_configuration_count": len(results) + 1,
        "conservative_boundary_recheck_count": len(boundary_lineage),
        "route_segment_count": len(results),
        "partition_owned_adjacent_sample_segment_count": total_segments,
        "configuration_geometry_binding_count": (
            total_samples * len(configuration_body_ids)
        ),
        "configuration_sweep_envelope_count": (
            total_segments * len(configuration_body_ids)
        ),
    }
    if total_segments != len(results):
        raise PartitionedTypingCollisionIntakeV1Error(
            "partition sweep ownership does not exactly cover route segments"
        )

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "typing_execution_plan_sha256": expected_execution_plan_sha256,
        "typing_trajectory_plan_sha256": expected_trajectory_plan_sha256,
        "typing_trajectory_ik_screen_sha256": ik[
            "typing_trajectory_ik_screen_sha256"
        ],
        "calibration_snapshot_sha256": expected_calibration_snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "start_state_source_kind": seed["source_kind"],
        "start_state_execution_eligible": False,
        "installed_collision_profile_sha256": profile_sha256,
        "collision_contract_sha256": contract.content_hash,
        "accepted_profile_source_sha256_values": accepted_source_hashes,
        "sampling_policy": {
            **policy.to_dict(),
            "sampling_policy_sha256": policy.content_sha256,
        },
        "required_rigid_attachment_frames": rigid_attachment_frames,
        "required_configuration_body_ids": configuration_body_ids,
        "partitions": partition_reports,
        "boundary_lineage": boundary_lineage,
        "required_evidence_slots": total_slots,
        "installed_geometry_collision_screening_executed": False,
        "continuous_collision_proven": False,
        "installed_collision_gate_cleared": False,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {
        **report,
        "partitioned_typing_collision_intake_sha256": _sha256(report),
    }


__all__ = [
    "SCHEMA",
    "READY_STATUS",
    "PROFILE_REQUIRED_STATUS",
    "PartitionedTypingCollisionIntakeV1Error",
    "prepare_partitioned_typing_collision_intake_v1",
]
