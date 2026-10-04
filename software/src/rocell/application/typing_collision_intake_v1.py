"""Fail-closed collision-evidence intake for optimized typing trajectories.

The T2B IK screen intentionally uses a ``SYNTHETIC_OFFLINE`` start state.  It
must not be relabeled as the measured start state expected by the physical
trajectory boundary.  This adapter instead preserves that provenance, reuses
the canonical bounded joint interpolation, and emits the exact installed-
geometry, attachment, configuration-sample, and sweep-envelope slots needed by
the existing collision pipeline.

No geometry is inferred and no controller command or physical authority is
created.  Missing measured evidence remains explicit.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.simulation.collision import CollisionBindingMode

from ._pinned_model import load_pinned_urdf
from .bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
    build_bounded_joint_sample_plan_from_results,
)
from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext, revalidate_simulation_context
from .context_lifecycle_v1 import (
    SimulationContextLifecycleBindingV1,
    SimulationContextLifecycleV1,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .typing_execution_plan_v1 import TypingExecutionPlanV1
from .typing_trajectory_ik_screen_v1 import (
    READY_STATUS as IK_READY_STATUS,
    SCHEMA as IK_SCHEMA,
)
from .typing_trajectory_plan_v1 import (
    TypingTrajectoryPlanV1,
    compile_typing_trajectory_plan_v1,
)
from .typing_planner_preparation_v1 import (
    PreparedTypingPlannerV1,
    validate_prepared_typing_planner_v1,
)


SCHEMA = "rocell.typing_collision_intake.v1"
READY_STATUS = "READY_FOR_OFFLINE_PROFILE_BOUND_COLLISION_EVIDENCE"
PROFILE_REQUIRED_STATUS = "BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED"


class TypingCollisionIntakeV1Error(ValueError):
    """Typing IK lineage or collision-profile identity is not exact."""


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
        raise TypingCollisionIntakeV1Error("ik_screen must be an object")
    report = dict(value)
    digest = report.pop("typing_trajectory_ik_screen_sha256", None)
    if report.get("schema") != IK_SCHEMA:
        raise TypingCollisionIntakeV1Error("typing IK screen schema mismatch")
    if not isinstance(digest, str) or digest != _sha256(report):
        raise TypingCollisionIntakeV1Error("typing IK screen hash is invalid")
    return dict(value)


def _profile_matches_context(
    profile: InstalledCollisionGeometryProfile,
    context: SimulationContext,
) -> bool:
    readiness = assess_current_collision_readiness(context)
    return (
        profile.manifest_id == context.snapshot.manifest_id
        and profile.manifest_sha256 == context.snapshot.manifest_sha256
        and profile.active_build_id == context.snapshot.active_build_id
        and profile.build_snapshot_sha256 == context.snapshot.snapshot_hash
        and profile.robot_model_sha256 == context.scenario.model_sha256
        and profile.base_contract_sha256 == readiness.contract.content_hash
    )


def prepare_typing_collision_intake_v1(
    source_plan: TypingExecutionPlanV1,
    plan: TypingTrajectoryPlanV1,
    ik_screen: Mapping[str, Any],
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    installed_profile: InstalledCollisionGeometryProfile | None = None,
    *,
    sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    prepared_planner: PreparedTypingPlannerV1 | None = None,
    context_lifecycle: SimulationContextLifecycleV1 | None = None,
    _lifecycle_binding: SimulationContextLifecycleBindingV1 | None = None,
) -> dict[str, Any]:
    """Describe exact collision evidence required for one accepted typing route."""

    if not isinstance(source_plan, TypingExecutionPlanV1):
        raise TypeError("source_plan must be a TypingExecutionPlanV1")
    if not isinstance(plan, TypingTrajectoryPlanV1):
        raise TypeError("plan must be a TypingTrajectoryPlanV1")
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise TypeError("snapshot must be a PlannerCalibrationSnapshot")
    if installed_profile is not None and not isinstance(
        installed_profile, InstalledCollisionGeometryProfile
    ):
        raise TypeError(
            "installed_profile must be an InstalledCollisionGeometryProfile"
        )
    if context_lifecycle is not None:
        if _lifecycle_binding is not None:
            raise TypingCollisionIntakeV1Error(
                "nested context lifecycle binding is invalid"
            )
        if not isinstance(context_lifecycle, SimulationContextLifecycleV1):
            raise TypeError("context_lifecycle must be SimulationContextLifecycleV1")
        if not isinstance(prepared_planner, PreparedTypingPlannerV1):
            raise TypingCollisionIntakeV1Error(
                "lifecycle-managed collision intake requires prepared planner resources"
            )
        with context_lifecycle.validation_scope(context) as binding:
            validate_prepared_typing_planner_v1(prepared_planner, binding)
            return prepare_typing_collision_intake_v1(
                source_plan,
                plan,
                ik_screen,
                context,
                snapshot,
                installed_profile,
                sampling_policy=sampling_policy,
                prepared_planner=prepared_planner,
                _lifecycle_binding=binding,
            )
    if _lifecycle_binding is None:
        if prepared_planner is not None:
            raise TypingCollisionIntakeV1Error(
                "prepared planner requires lifecycle-managed collision intake"
            )
        revalidate_simulation_context(context)
    else:
        if not isinstance(prepared_planner, PreparedTypingPlannerV1):
            raise TypingCollisionIntakeV1Error(
                "lifecycle binding requires prepared planner resources"
            )
        validate_prepared_typing_planner_v1(prepared_planner, _lifecycle_binding)

    ik = _validated_ik_report(ik_screen)
    replayed = compile_typing_trajectory_plan_v1(source_plan, policy=plan.policy)
    if replayed.to_bytes() != plan.to_bytes():
        raise TypingCollisionIntakeV1Error(
            "trajectory plan does not replay from the exact source plan"
        )
    if (
        source_plan.plan_sha256 != plan.source_plan_sha256
        or ik.get("status") != IK_READY_STATUS
        or ik.get("typing_execution_plan_sha256") != source_plan.plan_sha256
        or ik.get("typing_trajectory_plan_sha256") != plan.trajectory_plan_sha256
        or ik.get("trajectory_policy_sha256") != plan.policy.policy_sha256
        or ik.get("calibration_snapshot_sha256") != snapshot.snapshot_sha256
        or ik.get("build_snapshot_sha256") != context.snapshot.snapshot_hash
        or ik.get("kinematic_model_sha256") != context.scenario.model_sha256
        or ik.get("ik_all_samples_accepted") is not True
    ):
        raise TypingCollisionIntakeV1Error(
            "typing plan, IK screen, calibration, build, or model lineage differs"
        )
    seed = ik.get("seed")
    results = ik.get("joint_results")
    if (
        not isinstance(seed, Mapping)
        or seed.get("source_kind") != "SYNTHETIC_OFFLINE"
        or not isinstance(results, list)
        or len(results) != len(plan.screening_samples)
        or ik.get("sample_count") != len(plan.screening_samples)
        or ik.get("evaluated_sample_count") != len(results)
    ):
        raise TypingCollisionIntakeV1Error(
            "typing IK seed classification or exact result coverage is invalid"
        )

    selected = sampling_policy or BoundedSegmentSamplingPolicy()
    bounded = build_bounded_joint_sample_plan_from_results(
        seed.get("joint_positions_rad"),
        results,
        selected,
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
            raise TypingCollisionIntakeV1Error(
                "installed collision profile differs from the active context"
            )
        contract = installed_profile.contract
        status = READY_STATUS
        profile_sha256 = installed_profile.content_sha256
        accepted_source_hashes = sorted(installed_profile.source_bindings.values())
        blockers = [
            "MEASURED_RIGID_ATTACHMENT_BINDINGS_REQUIRED",
            "CONFIGURATION_GEOMETRY_REQUIRED_FOR_EVERY_BOUNDED_SAMPLE",
            "CONFIGURATION_SWEEP_ENVELOPES_REQUIRED_FOR_EVERY_ADJACENT_SAMPLE",
            "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
        ]
        next_stage = "SUPPLY_PROFILE_BOUND_COLLISION_EVIDENCE"

    model_link_names = set((
        prepared_planner.loaded_model.model
        if prepared_planner is not None
        else load_pinned_urdf(
            context.scenario.model_path,
            context.scenario.model_sha256,
        ).model
    ).link_names)
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
    evidence_slots = {
        "rigid_attachment_binding_count": len(rigid_attachment_frames),
        "configuration_sample_count": len(bounded),
        "configuration_body_count_per_sample": len(configuration_body_ids),
        "configuration_geometry_binding_count": (
            len(bounded) * len(configuration_body_ids)
        ),
        "adjacent_sample_segment_count": max(0, len(bounded) - 1),
        "configuration_sweep_envelope_count": (
            max(0, len(bounded) - 1) * len(configuration_body_ids)
        ),
    }
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "typing_execution_plan_sha256": source_plan.plan_sha256,
        "typing_trajectory_plan_sha256": plan.trajectory_plan_sha256,
        "typing_trajectory_ik_screen_sha256": ik["typing_trajectory_ik_screen_sha256"],
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "start_state_source_kind": seed["source_kind"],
        "start_state_execution_eligible": False,
        "installed_collision_profile_sha256": profile_sha256,
        "collision_contract_sha256": contract.content_hash,
        "accepted_profile_source_sha256_values": accepted_source_hashes,
        "sampling_policy": {
            **selected.to_dict(),
            "sampling_policy_sha256": selected.content_sha256,
        },
        "bounded_sample_count": len(bounded),
        "bounded_joint_sample_plan": [item.to_dict() for item in bounded],
        "required_rigid_attachment_frames": rigid_attachment_frames,
        "required_configuration_body_ids": configuration_body_ids,
        "required_evidence_slots": evidence_slots,
        "installed_geometry_collision_screening_executed": False,
        "continuous_collision_proven": False,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**report, "typing_collision_intake_sha256": _sha256(report)}


__all__ = [
    "SCHEMA",
    "READY_STATUS",
    "PROFILE_REQUIRED_STATUS",
    "TypingCollisionIntakeV1Error",
    "prepare_typing_collision_intake_v1",
]
