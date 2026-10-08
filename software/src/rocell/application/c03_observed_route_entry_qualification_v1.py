"""Qualify a fresh observed-state entry into the exact retained C03 route.

This boundary authenticates the retained C03 route, applies the existing
read-only observed-planner-state freshness contract, expands the single entry
segment with the shared bounded sampler, and reuses the established FK and
conservative sweep evaluators.  It is evidence only: every result remains
execution-ineligible and contains no controller or wire command.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from rocell.calibration import PlannerCalibrationSnapshot

from .bounded_segment_collision_qualification import (
    BoundedSegmentCollisionQualificationError,
    BoundedSegmentSamplingPolicy,
    MeasuredSegmentConfigurationSample,
    build_bounded_joint_sample_plan_from_results,
    qualify_bounded_segment_collisions,
)
from .c03_route_collision_handoff_v1 import (
    prepare_c03_route_collision_handoff_v1,
)
from .conservative_segment_sweep_qualification import (
    ConservativeSegmentSweepQualificationError,
    MeasuredConfigurationSweepEnvelopeBinding,
    evaluate_conservative_segment_sweeps_from_plan,
)
from .context import SimulationContext, revalidate_simulation_context
from .fk_collision_pose_adapter import MeasuredRigidAttachmentBinding
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .measured_trajectory_screening import SCHEMA as TRAJECTORY_SCREENING_SCHEMA
from .observed_planner_start_state import (
    ObservedPlannerStartState,
    ObservedPlannerStartStateError,
)


SCHEMA = "tactevra.c03_observed_route_entry_qualification.v1"
CLEAR_STATUS = "CLEAR_BOUND_ENTRY_EXECUTION_INELIGIBLE"
COLLISION_STATUS = "COLLISION_REPLAN_REQUIRED"
INDETERMINATE_STATUS = "INDETERMINATE_REPLAN_REQUIRED"
REQUIRED_NEXT_EVIDENCE = (
    "PHYSICAL_INSTALLED_PROFILE_REQUIRED",
    "FRESH_OBSERVED_STATE_REQUIRED_AT_USE",
    "ICQ8_COMPLETE_ROUTE_RECEIPT_REQUIRED",
    "PHYSICALLY_QUALIFIED_DYNAMICS_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "SEPARATE_EXECUTION_PERMIT_REQUIRED",
)
_FIELDS = {
    "schema", "status", "reason", "source_result_receipt_sha256",
    "source_route_receipt_sha256", "c03_collision_handoff_sha256",
    "tool_configuration_sha256", "target_catalog_sha256",
    "installed_collision_profile_sha256", "collision_contract_sha256",
    "build_snapshot_sha256", "kinematic_model_sha256",
    "calibration_snapshot_sha256", "observed_start_state_sha256",
    "feedback_receipt_sha256", "controller_session_id",
    "evaluated_monotonic_ns", "observation_valid_until_monotonic_ns",
    "sampling_policy", "route_entry_waypoint_sequence",
    "route_entry_joint_positions_rad", "sample_count", "segment_count",
    "sample_plan", "attachment_bindings_sha256",
    "configuration_samples_sha256", "configuration_sweeps_sha256",
    "bounded_collision_qualification", "continuous_sweep_qualification",
    "entry_samples_collision_free", "entry_continuous_sweep_clear",
    "collision_detected", "mismatch_requires_replanning",
    "route_reusable_after_identity_change",
    "synthetic_route_execution_eligible", "required_next_evidence",
    "permit_review_ready", "eligible_for_executor", "automatic_retry_allowed",
    "controller_commands", "wire_commands", "hardware_commands_generated",
    "hardware_access", "hardware_writes", "physical_movements",
    "physical_authority", "c03_observed_route_entry_qualification_sha256",
}


class C03ObservedRouteEntryQualificationV1Error(ValueError):
    """Entry inputs are malformed, crossed, or outside bounded resources."""


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
        raise C03ObservedRouteEntryQualificationV1Error(
            "C03 observed-entry evidence is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _binding_hashes(
    attachment_bindings: Sequence[MeasuredRigidAttachmentBinding],
    configuration_samples: Sequence[MeasuredSegmentConfigurationSample],
    configuration_sweeps: Sequence[
        Mapping[str, MeasuredConfigurationSweepEnvelopeBinding]
    ],
) -> tuple[str, str, str]:
    attachments = [item.to_dict() for item in attachment_bindings]
    samples: list[dict[str, Any]] = []
    for item in configuration_samples:
        if not isinstance(item, MeasuredSegmentConfigurationSample):
            raise TypeError(
                "configuration_samples must contain measured segment samples"
            )
        samples.append({
            "sample_sequence": item.sample_sequence,
            "sample_plan_sha256": item.sample_plan_sha256,
            "geometry_by_body": {
                body_id: binding.to_dict()
                for body_id, binding in sorted(item.geometry_by_body.items())
            },
        })
    sweeps: list[dict[str, Any]] = []
    for segment_sequence, item in enumerate(configuration_sweeps):
        if not isinstance(item, Mapping):
            raise TypeError("configuration_sweeps must contain mappings")
        sweeps.append({
            "segment_sequence": segment_sequence,
            "geometry_by_body": {
                body_id: binding.to_dict()
                for body_id, binding in sorted(item.items())
            },
        })
    return _sha(attachments), _sha(samples), _sha(sweeps)


def _result(
    *,
    status: str,
    reason: str,
    handoff: Mapping[str, Any],
    route: Mapping[str, Any],
    observed_start: ObservedPlannerStartState,
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    installed_profile: InstalledCollisionGeometryProfile,
    evaluated_monotonic_ns: int,
    policy: BoundedSegmentSamplingPolicy,
    sample_plan: Sequence[Any],
    attachment_bindings_sha256: str,
    configuration_samples_sha256: str,
    configuration_sweeps_sha256: str,
    bounded_collision: Mapping[str, Any] | None,
    continuous_sweep: Mapping[str, Any] | None,
) -> dict[str, Any]:
    clear = status == CLEAR_STATUS
    collision = status == COLLISION_STATUS
    samples_clear = bool(
        bounded_collision is not None
        and bounded_collision.get("all_bounded_samples_collision_free") is True
    )
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "reason": reason,
        "source_result_receipt_sha256": handoff["source_result_receipt_sha256"],
        "source_route_receipt_sha256": handoff["source_route_receipt_sha256"],
        "c03_collision_handoff_sha256": handoff["c03_collision_handoff_sha256"],
        "tool_configuration_sha256": route["tool_configuration_sha256"],
        "target_catalog_sha256": route["target_catalog_sha256"],
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "collision_contract_sha256": installed_profile.contract.content_hash,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "observed_start_state_sha256": observed_start.observed_start_state_sha256,
        "feedback_receipt_sha256": observed_start.feedback_receipt_sha256,
        "controller_session_id": observed_start.controller_session_id,
        "evaluated_monotonic_ns": evaluated_monotonic_ns,
        "observation_valid_until_monotonic_ns": observed_start.valid_until_monotonic_ns,
        "sampling_policy": {
            **policy.to_dict(),
            "sampling_policy_sha256": policy.content_sha256,
        },
        "route_entry_waypoint_sequence": 0,
        "route_entry_joint_positions_rad": dict(
            route["ik_screen"]["joint_results"][0][
                "solution_arm_joint_positions_rad"
            ]
        ),
        "sample_count": len(sample_plan),
        "segment_count": max(0, len(sample_plan) - 1),
        "sample_plan": [
            {**item.to_dict(), "sample_sha256": item.content_sha256}
            for item in sample_plan
        ],
        "attachment_bindings_sha256": attachment_bindings_sha256,
        "configuration_samples_sha256": configuration_samples_sha256,
        "configuration_sweeps_sha256": configuration_sweeps_sha256,
        "bounded_collision_qualification": bounded_collision,
        "continuous_sweep_qualification": continuous_sweep,
        "entry_samples_collision_free": samples_clear,
        "entry_continuous_sweep_clear": clear,
        "collision_detected": collision,
        "mismatch_requires_replanning": status == INDETERMINATE_STATUS,
        "route_reusable_after_identity_change": False,
        "synthetic_route_execution_eligible": False,
        "required_next_evidence": list(REQUIRED_NEXT_EVIDENCE),
        "permit_review_ready": False,
        "eligible_for_executor": False,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "c03_observed_route_entry_qualification_sha256": _sha(core)}


def qualify_c03_observed_route_entry_v1(
    route_result: Mapping[str, Any],
    observed_start: ObservedPlannerStartState,
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    installed_profile: InstalledCollisionGeometryProfile,
    attachment_bindings: Sequence[MeasuredRigidAttachmentBinding],
    configuration_samples: Sequence[MeasuredSegmentConfigurationSample],
    configuration_sweeps: Sequence[
        Mapping[str, MeasuredConfigurationSweepEnvelopeBinding]
    ],
    *,
    evaluated_monotonic_ns: int,
    policy: BoundedSegmentSamplingPolicy | None = None,
) -> dict[str, Any]:
    """Qualify one observed-to-C03-entry path without granting authority."""

    if not isinstance(observed_start, ObservedPlannerStartState):
        raise TypeError("observed_start must be an ObservedPlannerStartState")
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise TypeError("snapshot must be a PlannerCalibrationSnapshot")
    if not isinstance(installed_profile, InstalledCollisionGeometryProfile):
        raise TypeError("installed_profile must be an InstalledCollisionGeometryProfile")
    if (
        isinstance(evaluated_monotonic_ns, bool)
        or not isinstance(evaluated_monotonic_ns, int)
        or evaluated_monotonic_ns <= 0
    ):
        raise C03ObservedRouteEntryQualificationV1Error(
            "evaluated_monotonic_ns must be a positive integer"
        )
    selected = policy or BoundedSegmentSamplingPolicy()
    revalidate_simulation_context(context)
    attachments = tuple(attachment_bindings)
    samples = tuple(configuration_samples)
    sweeps = tuple(configuration_sweeps)
    attachment_sha, samples_sha, sweeps_sha = _binding_hashes(
        attachments, samples, sweeps
    )
    try:
        handoff = prepare_c03_route_collision_handoff_v1(
            route_result,
            context,
            installed_profile=installed_profile,
            sampling_policy=selected,
        )
    except ValueError as exc:
        raise C03ObservedRouteEntryQualificationV1Error(str(exc)) from exc
    route = route_result["route_result"]
    empty_plan: tuple[Any, ...] = ()
    try:
        observed_joints = observed_start.require_fresh_for(
            snapshot, evaluated_monotonic_ns
        )
    except ObservedPlannerStartStateError as exc:
        return _result(
            status=INDETERMINATE_STATUS,
            reason=str(exc),
            handoff=handoff,
            route=route,
            observed_start=observed_start,
            context=context,
            snapshot=snapshot,
            installed_profile=installed_profile,
            evaluated_monotonic_ns=evaluated_monotonic_ns,
            policy=selected,
            sample_plan=empty_plan,
            attachment_bindings_sha256=attachment_sha,
            configuration_samples_sha256=samples_sha,
            configuration_sweeps_sha256=sweeps_sha,
            bounded_collision=None,
            continuous_sweep=None,
        )
    if (
        route["calibration_snapshot_sha256"] != snapshot.snapshot_sha256
        or installed_profile.build_snapshot_sha256 != context.snapshot.snapshot_hash
        or installed_profile.robot_model_sha256 != context.scenario.model_sha256
    ):
        return _result(
            status=INDETERMINATE_STATUS,
            reason="observed state, route, profile, calibration, or build identity differs",
            handoff=handoff,
            route=route,
            observed_start=observed_start,
            context=context,
            snapshot=snapshot,
            installed_profile=installed_profile,
            evaluated_monotonic_ns=evaluated_monotonic_ns,
            policy=selected,
            sample_plan=empty_plan,
            attachment_bindings_sha256=attachment_sha,
            configuration_samples_sha256=samples_sha,
            configuration_sweeps_sha256=sweeps_sha,
            bounded_collision=None,
            continuous_sweep=None,
        )

    endpoint = dict(route["ik_screen"]["joint_results"][0])
    endpoint["waypoint_sequence"] = 0
    try:
        plan = build_bounded_joint_sample_plan_from_results(
            observed_joints, (endpoint,), selected
        )
    except BoundedSegmentCollisionQualificationError as exc:
        raise C03ObservedRouteEntryQualificationV1Error(str(exc)) from exc
    screening_core = {
        "schema": TRAJECTORY_SCREENING_SCHEMA,
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "collision_contract_sha256": installed_profile.contract.content_hash,
        "ik_all_waypoints_accepted": True,
        "observed_start_joint_positions_rad": dict(observed_joints),
        "waypoints": [{"sequence": 0, "phase": "C03_ROUTE_ENTRY"}],
        "joint_results": [endpoint],
        "source_c03_route_receipt_sha256": route["receipt_sha256"],
        "source_observed_start_state_sha256": (
            observed_start.observed_start_state_sha256
        ),
    }
    screening = {
        **screening_core,
        "trajectory_screening_sha256": _sha(screening_core),
    }
    try:
        bounded = qualify_bounded_segment_collisions(
            context,
            snapshot,
            installed_profile,
            screening,
            attachments,
            samples,
            policy=selected,
        )
    except (BoundedSegmentCollisionQualificationError, ValueError) as exc:
        raise C03ObservedRouteEntryQualificationV1Error(str(exc)) from exc

    if bounded["status"] == "BLOCKED_COLLISION_DETECTED_AT_BOUNDED_SAMPLE":
        return _result(
            status=COLLISION_STATUS,
            reason="collision detected at an observed-entry sample",
            handoff=handoff, route=route, observed_start=observed_start,
            context=context, snapshot=snapshot, installed_profile=installed_profile,
            evaluated_monotonic_ns=evaluated_monotonic_ns, policy=selected,
            sample_plan=plan, attachment_bindings_sha256=attachment_sha,
            configuration_samples_sha256=samples_sha,
            configuration_sweeps_sha256=sweeps_sha,
            bounded_collision=bounded, continuous_sweep=None,
        )
    if not bounded["all_bounded_samples_collision_free"]:
        return _result(
            status=INDETERMINATE_STATUS,
            reason="bounded observed-entry collision evidence is incomplete",
            handoff=handoff, route=route, observed_start=observed_start,
            context=context, snapshot=snapshot, installed_profile=installed_profile,
            evaluated_monotonic_ns=evaluated_monotonic_ns, policy=selected,
            sample_plan=plan, attachment_bindings_sha256=attachment_sha,
            configuration_samples_sha256=samples_sha,
            configuration_sweeps_sha256=sweeps_sha,
            bounded_collision=bounded, continuous_sweep=None,
        )
    try:
        continuous = evaluate_conservative_segment_sweeps_from_plan(
            context,
            installed_profile,
            plan,
            bounded["fk_collision_qualification"],
            attachments,
            sweeps,
        )
    except ConservativeSegmentSweepQualificationError as exc:
        raise C03ObservedRouteEntryQualificationV1Error(str(exc)) from exc
    if continuous["status"] == "BLOCKED_CONSERVATIVE_SWEEP_COLLISION":
        status = COLLISION_STATUS
        reason = "collision detected by the conservative observed-entry sweep"
    elif continuous["status"] == "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN":
        status = CLEAR_STATUS
        reason = "bound observed-entry samples and continuous sweeps are clear"
    else:
        status = INDETERMINATE_STATUS
        reason = "continuous observed-entry evidence is incomplete"
    return _result(
        status=status, reason=reason, handoff=handoff, route=route,
        observed_start=observed_start, context=context, snapshot=snapshot,
        installed_profile=installed_profile,
        evaluated_monotonic_ns=evaluated_monotonic_ns, policy=selected,
        sample_plan=plan, attachment_bindings_sha256=attachment_sha,
        configuration_samples_sha256=samples_sha,
        configuration_sweeps_sha256=sweeps_sha,
        bounded_collision=bounded, continuous_sweep=continuous,
    )


def parse_c03_observed_route_entry_qualification_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a sealed ICQ-7 receipt and its zero-authority invariants."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise C03ObservedRouteEntryQualificationV1Error(
            "receipt fields must be exact"
        )
    document = dict(value)
    claimed = document.pop("c03_observed_route_entry_qualification_sha256", None)
    if value.get("schema") != SCHEMA or claimed != _sha(document):
        raise C03ObservedRouteEntryQualificationV1Error(
            "receipt schema or SHA-256 differs"
        )
    if value.get("status") not in {
        CLEAR_STATUS, COLLISION_STATUS, INDETERMINATE_STATUS,
    }:
        raise C03ObservedRouteEntryQualificationV1Error("receipt status differs")
    sample_plan = value.get("sample_plan")
    if not isinstance(sample_plan, list) or value.get("sample_count") != len(sample_plan):
        raise C03ObservedRouteEntryQualificationV1Error(
            "receipt sample accounting differs"
        )
    if any(
        not isinstance(item, Mapping)
        or item.get("sample_sequence") != index
        or item.get("sample_sha256")
        != _sha({key: nested for key, nested in item.items() if key != "sample_sha256"})
        for index, item in enumerate(sample_plan)
    ):
        raise C03ObservedRouteEntryQualificationV1Error(
            "receipt sample plan is crossed or modified"
        )
    clear = value["status"] == CLEAR_STATUS
    collision = value["status"] == COLLISION_STATUS
    bounded = value.get("bounded_collision_qualification")
    expected_samples_clear = bool(
        isinstance(bounded, Mapping)
        and bounded.get("all_bounded_samples_collision_free") is True
    )
    if (
        value.get("segment_count") != max(0, len(sample_plan) - 1)
        or value.get("entry_samples_collision_free") is not expected_samples_clear
        or value.get("entry_continuous_sweep_clear") is not clear
        or value.get("collision_detected") is not collision
        or value.get("mismatch_requires_replanning")
        is not (value["status"] == INDETERMINATE_STATUS)
        or value.get("route_reusable_after_identity_change") is not False
        or value.get("synthetic_route_execution_eligible") is not False
        or value.get("required_next_evidence") != list(REQUIRED_NEXT_EVIDENCE)
        or value.get("permit_review_ready") is not False
        or value.get("eligible_for_executor") is not False
        or value.get("automatic_retry_allowed") is not False
        or value.get("controller_commands") != []
        or value.get("wire_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
        or value.get("physical_authority") is not False
    ):
        raise C03ObservedRouteEntryQualificationV1Error(
            "receipt disposition, gates, or authority differs"
        )
    return dict(value)


__all__ = [
    "CLEAR_STATUS", "COLLISION_STATUS", "INDETERMINATE_STATUS",
    "REQUIRED_NEXT_EVIDENCE", "SCHEMA",
    "C03ObservedRouteEntryQualificationV1Error",
    "parse_c03_observed_route_entry_qualification_v1",
    "qualify_c03_observed_route_entry_v1",
]
