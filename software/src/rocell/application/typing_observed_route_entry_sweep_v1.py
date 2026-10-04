"""Conservatively screen every adjacent observed-entry sample pair.

ARM-152 reuses the shared conservative sweep evaluator over ARM-150's exact
sample plan and ARM-151's installed-geometry FK collision result.  It requires
profile-bound measured envelopes for configuration-sampled bodies and retains
all remaining physical-dynamics, verification, review, and execution gates.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
)
from .conservative_segment_sweep_qualification import (
    ConservativeSegmentSweepQualificationError,
    MeasuredConfigurationSweepEnvelopeBinding,
    evaluate_conservative_segment_sweeps_from_plan,
)
from .context import SimulationContext, revalidate_simulation_context
from .fk_collision_pose_adapter import MeasuredRigidAttachmentBinding
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .typing_observed_route_entry_collision_v1 import (
    CLEAR_STATUS as ENTRY_COLLISION_CLEAR_STATUS,
    TypingObservedRouteEntryCollisionV1Error,
    parse_typing_observed_route_entry_collision_v1,
)
from .typing_observed_route_entry_v1 import (
    TypingObservedRouteEntryV1Error,
    parse_typing_observed_route_entry_v1,
)


SCHEMA = "rocell.typing_observed_route_entry_sweep.v1"
CLEAR_STATUS = "ENTRY_CONSERVATIVE_SWEEPS_CLEAR_DYNAMICS_REQUIRED"
COLLISION_STATUS = "BLOCKED_ENTRY_CONSERVATIVE_SWEEP_COLLISION"
INCOMPLETE_STATUS = "BLOCKED_INCOMPLETE_ENTRY_SWEEP_EVIDENCE"
REQUIRED_NEXT_EVIDENCE = (
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
    "ACCEPTED_GLOBAL_PAIR_EXCLUSIONS_REQUIRED",
    "PHASE_LOCAL_CONTACT_POLICY_REQUIRED",
    "INSTALLED_PHYSICAL_QUALIFICATION_REQUIRED",
    "PHYSICALLY_QUALIFIED_DYNAMICS_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_NESTED_STATUSES = {
    "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN",
    "BLOCKED_CONSERVATIVE_SWEEP_COLLISION",
    "BLOCKED_INCOMPLETE_CONSERVATIVE_SWEEP_EVIDENCE",
}
_FIELDS = {
    "schema", "status", "request_id", "materialization_sha256",
    "observed_route_entry_sha256", "observed_route_entry_collision_sha256",
    "observed_ik_seed_sha256", "observed_start_state_sha256",
    "calibration_snapshot_sha256", "build_snapshot_sha256",
    "controller_session_id", "installed_collision_profile_sha256",
    "collision_contract_sha256", "sample_count", "segment_count",
    "sample_plan_sha256", "conservative_sweep_evaluation_sha256",
    "conservative_sweep_evaluation", "sweep_screening_executed",
    "all_entry_sweeps_clear", "continuous_collision_proven_for_bound_geometry",
    "continuous_collision_proven", "measured_dynamics_qualified",
    "required_next_evidence", "permit_review_ready", "eligible_for_executor",
    "automatic_retry_allowed", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "physical_authority",
    "observed_route_entry_sweep_sha256",
}


class TypingObservedRouteEntrySweepV1Error(ValueError):
    """Observed-entry sweep evidence is incomplete, crossed, or modified."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedRouteEntrySweepV1Error(
            "entry sweep report is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sample_plan(entry: Mapping[str, Any]) -> tuple[BoundedJointConfigurationSample, ...]:
    result: list[BoundedJointConfigurationSample] = []
    for item in entry["sample_plan"]:
        sample = BoundedJointConfigurationSample(
            sample_sequence=item["sample_sequence"],
            source_segment_index=item["source_segment_index"],
            subdivision_index=item["subdivision_index"],
            subdivision_count=item["subdivision_count"],
            interpolation_ratio=item["interpolation_ratio"],
            joint_positions_rad=item["joint_positions_rad"],
        )
        if sample.content_sha256 != item["sample_sha256"]:
            raise TypingObservedRouteEntrySweepV1Error(
                "entry sample reconstruction hash differs"
            )
        result.append(sample)
    return tuple(result)


def qualify_typing_observed_route_entry_sweep_v1(
    observed_route_entry: Mapping[str, Any],
    observed_route_entry_collision: Mapping[str, Any],
    context: SimulationContext,
    installed_profile: InstalledCollisionGeometryProfile,
    attachment_bindings: Sequence[MeasuredRigidAttachmentBinding],
    configuration_sweep_envelopes: Sequence[
        Mapping[str, MeasuredConfigurationSweepEnvelopeBinding]
    ],
) -> dict[str, Any]:
    """Evaluate continuous conservative bounds without creating authority."""

    try:
        entry = parse_typing_observed_route_entry_v1(observed_route_entry)
        collision = parse_typing_observed_route_entry_collision_v1(
            observed_route_entry_collision
        )
    except (
        TypingObservedRouteEntryV1Error,
        TypingObservedRouteEntryCollisionV1Error,
    ) as exc:
        raise TypingObservedRouteEntrySweepV1Error(str(exc)) from exc
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(installed_profile, InstalledCollisionGeometryProfile):
        raise TypeError("installed_profile must be InstalledCollisionGeometryProfile")
    revalidate_simulation_context(context)
    if (
        collision["status"] != ENTRY_COLLISION_CLEAR_STATUS
        or collision["all_entry_samples_collision_free"] is not True
    ):
        raise TypingObservedRouteEntrySweepV1Error(
            "entry samples must have complete installed collision clearance"
        )
    if (
        collision["observed_route_entry_sha256"]
        != entry["observed_route_entry_sha256"]
        or collision["request_id"] != entry["request_id"]
        or collision["materialization_sha256"] != entry["materialization_sha256"]
        or collision["observed_ik_seed_sha256"]
        != entry["observed_ik_seed_sha256"]
        or collision["observed_start_state_sha256"]
        != entry["observed_start_state_sha256"]
        or collision["controller_session_id"] != entry["controller_session_id"]
        or collision["sample_count"] != entry["sample_count"]
        or collision["installed_collision_profile_sha256"]
        != installed_profile.content_sha256
        or collision["collision_contract_sha256"]
        != installed_profile.contract.content_hash
        or entry["build_snapshot_sha256"] != context.snapshot.snapshot_hash
        or installed_profile.build_snapshot_sha256
        != context.snapshot.snapshot_hash
        or installed_profile.robot_model_sha256 != context.scenario.model_sha256
    ):
        raise TypingObservedRouteEntrySweepV1Error(
            "entry, collision, installed profile, or active context lineage differs"
        )
    plan = _sample_plan(entry)
    try:
        sweep = evaluate_conservative_segment_sweeps_from_plan(
            context,
            installed_profile,
            plan,
            collision["fk_collision_qualification"],
            attachment_bindings,
            configuration_sweep_envelopes,
        )
    except ConservativeSegmentSweepQualificationError as exc:
        raise TypingObservedRouteEntrySweepV1Error(str(exc)) from exc
    nested_status = sweep["status"]
    if nested_status == "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN":
        status = CLEAR_STATUS
        all_clear = True
    elif nested_status == "BLOCKED_CONSERVATIVE_SWEEP_COLLISION":
        status = COLLISION_STATUS
        all_clear = False
    else:
        status = INCOMPLETE_STATUS
        all_clear = False
    sample_hashes = [item["sample_sha256"] for item in entry["sample_plan"]]
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "request_id": entry["request_id"],
        "materialization_sha256": entry["materialization_sha256"],
        "observed_route_entry_sha256": entry["observed_route_entry_sha256"],
        "observed_route_entry_collision_sha256": collision[
            "observed_route_entry_collision_sha256"
        ],
        "observed_ik_seed_sha256": entry["observed_ik_seed_sha256"],
        "observed_start_state_sha256": entry["observed_start_state_sha256"],
        "calibration_snapshot_sha256": entry["calibration_snapshot_sha256"],
        "build_snapshot_sha256": entry["build_snapshot_sha256"],
        "controller_session_id": entry["controller_session_id"],
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "collision_contract_sha256": installed_profile.contract.content_hash,
        "sample_count": len(plan),
        "segment_count": sweep["segment_count"],
        "sample_plan_sha256": _sha(sample_hashes),
        "conservative_sweep_evaluation_sha256": _sha(sweep),
        "conservative_sweep_evaluation": sweep,
        "sweep_screening_executed": True,
        "all_entry_sweeps_clear": all_clear,
        "continuous_collision_proven_for_bound_geometry": sweep[
            "continuous_collision_proven_for_bound_geometry"
        ],
        "continuous_collision_proven": False,
        "measured_dynamics_qualified": False,
        "required_next_evidence": list(REQUIRED_NEXT_EVIDENCE),
        "permit_review_ready": False,
        "eligible_for_executor": False,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "observed_route_entry_sweep_sha256": _sha(core)}


def parse_typing_observed_route_entry_sweep_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the sealed sweep result and all retained release gates."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedRouteEntrySweepV1Error("entry sweep fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("observed_route_entry_sweep_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedRouteEntrySweepV1Error("entry sweep hash differs")
    sweep = value["conservative_sweep_evaluation"]
    if not isinstance(sweep, Mapping) or value[
        "conservative_sweep_evaluation_sha256"
    ] != _sha(sweep):
        raise TypingObservedRouteEntrySweepV1Error(
            "conservative sweep evidence hash differs"
        )
    nested_status = sweep.get("status")
    if nested_status not in _NESTED_STATUSES:
        raise TypingObservedRouteEntrySweepV1Error(
            "conservative sweep status differs"
        )
    expected_status = (
        CLEAR_STATUS
        if nested_status == "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"
        else COLLISION_STATUS
        if nested_status == "BLOCKED_CONSERVATIVE_SWEEP_COLLISION"
        else INCOMPLETE_STATUS
    )
    expected_clear = expected_status == CLEAR_STATUS
    digests = (
        "materialization_sha256", "observed_route_entry_sha256",
        "observed_route_entry_collision_sha256", "observed_ik_seed_sha256",
        "observed_start_state_sha256", "calibration_snapshot_sha256",
        "build_snapshot_sha256", "installed_collision_profile_sha256",
        "collision_contract_sha256", "sample_plan_sha256",
        "conservative_sweep_evaluation_sha256",
    )
    if (
        value["schema"] != SCHEMA
        or any(_SHA.fullmatch(value[field] or "") is None for field in digests)
        or not isinstance(value["request_id"], str)
        or not value["request_id"]
        or not isinstance(value["controller_session_id"], str)
        or not value["controller_session_id"]
        or not isinstance(value["sample_count"], int)
        or isinstance(value["sample_count"], bool)
        or value["sample_count"] < 2
        or value["segment_count"] != value["sample_count"] - 1
        or sweep.get("segment_count") != value["segment_count"]
        or not isinstance(sweep.get("segment_reports"), list)
        or len(sweep["segment_reports"]) != value["segment_count"]
        or any(
            not isinstance(item, Mapping)
            or item.get("segment_sequence") != index
            for index, item in enumerate(sweep["segment_reports"])
        )
        or value["status"] != expected_status
        or value["sweep_screening_executed"] is not True
        or value["all_entry_sweeps_clear"] is not expected_clear
        or sweep.get("all_conservative_segment_sweeps_clear") is not expected_clear
        or value["continuous_collision_proven_for_bound_geometry"]
        is not sweep.get("continuous_collision_proven_for_bound_geometry")
        or value["continuous_collision_proven"] is not False
        or value["measured_dynamics_qualified"] is not False
        or value["required_next_evidence"] != list(REQUIRED_NEXT_EVIDENCE)
        or value["permit_review_ready"] is not False
        or value["eligible_for_executor"] is not False
        or value["automatic_retry_allowed"] is not False
        or value["controller_commands"] != []
        or value["wire_commands"] != []
        or value["hardware_commands_generated"] != 0
        or value["hardware_access"] is not False
        or value["physical_authority"] is not False
    ):
        raise TypingObservedRouteEntrySweepV1Error(
            "entry sweep lineage, result, gates, or authority differs"
        )
    return dict(value)


__all__ = [
    "CLEAR_STATUS", "COLLISION_STATUS", "INCOMPLETE_STATUS",
    "REQUIRED_NEXT_EVIDENCE", "SCHEMA",
    "TypingObservedRouteEntrySweepV1Error",
    "parse_typing_observed_route_entry_sweep_v1",
    "qualify_typing_observed_route_entry_sweep_v1",
]
