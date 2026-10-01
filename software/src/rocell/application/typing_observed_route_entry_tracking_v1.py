"""Qualify retained joint observations against one ARM-153 schedule.

The adapter is hardware-incapable.  It accepts already-retained, independently
qualified joint observations and checks scheduled sample tracking plus endpoint
settling.  Sample agreement is not continuous tracking, collision clearance,
task-effect verification, a permit, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from rocell.kinematics import ARM_JOINT_NAMES

from .context import SimulationContext, revalidate_simulation_context
from .typing_observed_route_entry_dynamics_v1 import (
    TypingObservedRouteEntryDynamicsV1Error,
    parse_typing_observed_route_entry_dynamics_v1,
)


SCHEMA = "rocell.typing_observed_route_entry_tracking.v1"
POLICY_SCHEMA = "rocell.installed_joint_tracking_observation_policy.v1"
SAMPLE_SCHEMA = "rocell.retained_joint_tracking_observation.v1"
STATUS = "SAMPLED_TRACKING_AND_ENDPOINT_SETTLING_OBSERVED"
REQUIRED_NEXT_EVIDENCE = (
    "CONTINUOUS_CONTROLLER_TRACKING_QUALIFICATION_REQUIRED",
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
    "ACCEPTED_GLOBAL_PAIR_EXCLUSIONS_REQUIRED",
    "PHASE_LOCAL_CONTACT_POLICY_REQUIRED",
    "INSTALLED_PHYSICAL_QUALIFICATION_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "status", "request_id", "materialization_sha256",
    "observed_route_entry_dynamics", "observed_route_entry_dynamics_sha256",
    "build_snapshot_sha256", "controller_session_id", "policy",
    "policy_sha256", "source_export_sha256", "native_identity_sha256",
    "acquisition_qualification_sha256", "observations",
    "observation_set_sha256", "analysis", "analysis_sha256",
    "sampled_tracking_qualified", "endpoint_settling_observed",
    "continuous_controller_tracking_qualified", "continuous_collision_proven",
    "required_next_evidence", "permit_review_ready", "eligible_for_executor",
    "automatic_retry_allowed", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "physical_authority",
    "observed_route_entry_tracking_sha256",
}
_POLICY_FIELDS = {
    "schema", "policy_id", "source_kind", "build_snapshot_sha256",
    "controller_session_id", "qualification_evidence_sha256",
    "maximum_tracking_error_rad", "maximum_timing_error_ns",
    "minimum_settling_samples", "installed_policy_qualification",
}


class TypingObservedRouteEntryTrackingV1Error(ValueError):
    """Retained tracking evidence or its exact lineage is invalid."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedRouteEntryTrackingV1Error(
            "tracking evidence is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise TypingObservedRouteEntryTrackingV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _joint_map(value: object, label: str, *, positive: bool) -> MappingProxyType:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingObservedRouteEntryTrackingV1Error(
            f"{label} must use exact canonical joint order"
        )
    result = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypingObservedRouteEntryTrackingV1Error(
                f"{label}.{name} must be numeric"
            )
        number = float(raw)
        if not math.isfinite(number) or (positive and not 0.0 < number <= 1.0):
            raise TypingObservedRouteEntryTrackingV1Error(
                f"{label}.{name} is outside its finite bound"
            )
        result[name] = number
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class InstalledJointTrackingObservationPolicyV1:
    policy_id: str
    build_snapshot_sha256: str
    controller_session_id: str
    qualification_evidence_sha256: str
    maximum_tracking_error_rad: Mapping[str, float]
    maximum_timing_error_ns: int
    minimum_settling_samples: int
    source_kind: str = "PHYSICAL_QUALIFIED"
    installed_policy_qualification: bool = True
    schema: str = POLICY_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != POLICY_SCHEMA
            or self.source_kind != "PHYSICAL_QUALIFIED"
            or self.installed_policy_qualification is not True
        ):
            raise TypingObservedRouteEntryTrackingV1Error(
                "tracking policy lacks installed physical qualification"
            )
        if (
            not isinstance(self.policy_id, str)
            or not self.policy_id
            or self.policy_id != self.policy_id.strip()
            or not isinstance(self.controller_session_id, str)
            or not self.controller_session_id
            or self.controller_session_id != self.controller_session_id.strip()
        ):
            raise TypingObservedRouteEntryTrackingV1Error(
                "tracking policy identifiers must be nonempty"
            )
        _digest(self.build_snapshot_sha256, "build_snapshot_sha256")
        _digest(
            self.qualification_evidence_sha256,
            "qualification_evidence_sha256",
        )
        object.__setattr__(
            self,
            "maximum_tracking_error_rad",
            _joint_map(
                self.maximum_tracking_error_rad,
                "maximum_tracking_error_rad",
                positive=True,
            ),
        )
        if (
            isinstance(self.maximum_timing_error_ns, bool)
            or not isinstance(self.maximum_timing_error_ns, int)
            or not 0 <= self.maximum_timing_error_ns <= 1_000_000_000
        ):
            raise TypingObservedRouteEntryTrackingV1Error(
                "maximum_timing_error_ns is outside its bounded range"
            )
        if (
            isinstance(self.minimum_settling_samples, bool)
            or not isinstance(self.minimum_settling_samples, int)
            or not 2 <= self.minimum_settling_samples <= 64
        ):
            raise TypingObservedRouteEntryTrackingV1Error(
                "minimum_settling_samples must be in [2, 64]"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "source_kind": self.source_kind,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "controller_session_id": self.controller_session_id,
            "qualification_evidence_sha256": self.qualification_evidence_sha256,
            "maximum_tracking_error_rad": dict(self.maximum_tracking_error_rad),
            "maximum_timing_error_ns": self.maximum_timing_error_ns,
            "minimum_settling_samples": self.minimum_settling_samples,
            "installed_policy_qualification": True,
        }

    @property
    def policy_sha256(self) -> str:
        return _sha(self.to_dict())


@dataclass(frozen=True, slots=True)
class RetainedJointTrackingObservationV1:
    phase: str
    scheduled_sample_sequence: int
    captured_monotonic_ns: int
    schedule_elapsed_ns: int
    joint_positions_rad: Mapping[str, float]
    joint_velocities_rad_s: Mapping[str, float]
    source_record_sha256: str
    schema: str = SAMPLE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SAMPLE_SCHEMA or self.phase not in {"TRACKING", "SETTLING"}:
            raise TypingObservedRouteEntryTrackingV1Error(
                "tracking observation schema or phase differs"
            )
        for field in (
            "scheduled_sample_sequence", "captured_monotonic_ns",
            "schedule_elapsed_ns",
        ):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < (1 if field == "captured_monotonic_ns" else 0)
            ):
                raise TypingObservedRouteEntryTrackingV1Error(
                    f"{field} must be a bounded nonnegative integer"
                )
        object.__setattr__(
            self, "joint_positions_rad",
            _joint_map(self.joint_positions_rad, "joint_positions_rad", positive=False),
        )
        object.__setattr__(
            self, "joint_velocities_rad_s",
            _joint_map(
                self.joint_velocities_rad_s,
                "joint_velocities_rad_s",
                positive=False,
            ),
        )
        _digest(self.source_record_sha256, "source_record_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "phase": self.phase,
            "scheduled_sample_sequence": self.scheduled_sample_sequence,
            "captured_monotonic_ns": self.captured_monotonic_ns,
            "schedule_elapsed_ns": self.schedule_elapsed_ns,
            "joint_positions_rad": dict(self.joint_positions_rad),
            "joint_velocities_rad_s": dict(self.joint_velocities_rad_s),
            "source_record_sha256": self.source_record_sha256,
        }

    @property
    def observation_sha256(self) -> str:
        return _sha(self.to_dict())


def _policy(value: object) -> InstalledJointTrackingObservationPolicyV1:
    if not isinstance(value, Mapping) or set(value) != _POLICY_FIELDS:
        raise TypingObservedRouteEntryTrackingV1Error(
            "tracking policy fields differ"
        )
    return InstalledJointTrackingObservationPolicyV1(
        policy_id=value["policy_id"],
        build_snapshot_sha256=value["build_snapshot_sha256"],
        controller_session_id=value["controller_session_id"],
        qualification_evidence_sha256=value["qualification_evidence_sha256"],
        maximum_tracking_error_rad=value["maximum_tracking_error_rad"],
        maximum_timing_error_ns=value["maximum_timing_error_ns"],
        minimum_settling_samples=value["minimum_settling_samples"],
        source_kind=value["source_kind"],
        installed_policy_qualification=value["installed_policy_qualification"],
        schema=value["schema"],
    )


def _observation(value: object) -> RetainedJointTrackingObservationV1:
    if not isinstance(value, Mapping):
        raise TypingObservedRouteEntryTrackingV1Error(
            "tracking observation must be an object"
        )
    return RetainedJointTrackingObservationV1(
        phase=value.get("phase"),
        scheduled_sample_sequence=value.get("scheduled_sample_sequence"),
        captured_monotonic_ns=value.get("captured_monotonic_ns"),
        schedule_elapsed_ns=value.get("schedule_elapsed_ns"),
        joint_positions_rad=value.get("joint_positions_rad"),
        joint_velocities_rad_s=value.get("joint_velocities_rad_s"),
        source_record_sha256=value.get("source_record_sha256"),
        schema=value.get("schema"),
    )


def _analyze(
    dynamics: Mapping[str, Any],
    policy: InstalledJointTrackingObservationPolicyV1,
    observations: Sequence[RetainedJointTrackingObservationV1],
) -> dict[str, Any]:
    schedule = dynamics["schedule"]
    expected = schedule["samples"]
    tracking = tuple(item for item in observations if item.phase == "TRACKING")
    settling = tuple(item for item in observations if item.phase == "SETTLING")
    if len(tracking) != len(expected):
        raise TypingObservedRouteEntryTrackingV1Error(
            "tracking observations must cover every scheduled sample exactly once"
        )
    prior_capture = 0
    prior_elapsed = -1
    rows = []
    maximum_error = {name: 0.0 for name in ARM_JOINT_NAMES}
    for index, (observed, target) in enumerate(zip(tracking, expected)):
        if (
            observed.scheduled_sample_sequence != index
            or observed.captured_monotonic_ns <= prior_capture
            or observed.schedule_elapsed_ns <= prior_elapsed
            and index > 0
        ):
            raise TypingObservedRouteEntryTrackingV1Error(
                "tracking observations are not canonical and increasing"
            )
        timing_error = abs(
            observed.schedule_elapsed_ns - target["time_from_start_ns"]
        )
        errors = {
            name: abs(
                observed.joint_positions_rad[name]
                - target["joint_positions_rad"][name]
            )
            for name in ARM_JOINT_NAMES
        }
        if (
            timing_error > policy.maximum_timing_error_ns
            or any(
                errors[name] > policy.maximum_tracking_error_rad[name]
                for name in ARM_JOINT_NAMES
            )
        ):
            raise TypingObservedRouteEntryTrackingV1Error(
                "scheduled sample tracking exceeds its qualified bound"
            )
        for name in ARM_JOINT_NAMES:
            maximum_error[name] = max(maximum_error[name], errors[name])
        rows.append({
            "scheduled_sample_sequence": index,
            "scheduled_sample_sha256": target["sample_sha256"],
            "observation_sha256": observed.observation_sha256,
            "timing_error_ns": timing_error,
            "absolute_position_error_rad": errors,
        })
        prior_capture = observed.captured_monotonic_ns
        prior_elapsed = observed.schedule_elapsed_ns

    profile = dynamics["dynamics_profile"]
    endpoint = expected[-1]
    if len(settling) < policy.minimum_settling_samples:
        raise TypingObservedRouteEntryTrackingV1Error(
            "endpoint settling has too few retained observations"
        )
    for observed in settling:
        if (
            observed.scheduled_sample_sequence != len(expected) - 1
            or observed.captured_monotonic_ns <= prior_capture
            or observed.schedule_elapsed_ns <= prior_elapsed
            or observed.schedule_elapsed_ns < schedule["total_motion_time_ns"]
        ):
            raise TypingObservedRouteEntryTrackingV1Error(
                "settling observations are not endpoint-bound and increasing"
            )
        for name in ARM_JOINT_NAMES:
            if (
                abs(
                    observed.joint_positions_rad[name]
                    - endpoint["joint_positions_rad"][name]
                ) > profile["settle_position_tolerance_rad"][name]
                or abs(observed.joint_velocities_rad_s[name])
                > profile["settle_velocity_tolerance_rad_s"][name]
            ):
                raise TypingObservedRouteEntryTrackingV1Error(
                    "endpoint settling exceeds its measured profile bound"
                )
        prior_capture = observed.captured_monotonic_ns
        prior_elapsed = observed.schedule_elapsed_ns
    settling_span = (
        settling[-1].schedule_elapsed_ns - settling[0].schedule_elapsed_ns
    )
    if settling_span < profile["settle_dwell_ns"]:
        raise TypingObservedRouteEntryTrackingV1Error(
            "endpoint settling does not span the required dwell"
        )
    return {
        "tracking_sample_count": len(tracking),
        "settling_sample_count": len(settling),
        "maximum_tracking_error_rad": maximum_error,
        "settling_span_ns": settling_span,
        "tracking_rows": rows,
        "settling_observation_sha256": [
            item.observation_sha256 for item in settling
        ],
        "all_scheduled_samples_within_bounds": True,
        "endpoint_within_settling_bounds": True,
    }


def qualify_typing_observed_route_entry_tracking_v1(
    observed_route_entry_dynamics: Mapping[str, Any],
    context: SimulationContext,
    policy: InstalledJointTrackingObservationPolicyV1,
    observations: Sequence[RetainedJointTrackingObservationV1],
    *,
    source_export_sha256: str,
    native_identity_sha256: str,
    acquisition_qualification_sha256: str,
) -> dict[str, Any]:
    """Bind retained installed observations to one exact measured schedule."""

    try:
        dynamics = parse_typing_observed_route_entry_dynamics_v1(
            observed_route_entry_dynamics
        )
    except TypingObservedRouteEntryDynamicsV1Error as exc:
        raise TypingObservedRouteEntryTrackingV1Error(str(exc)) from exc
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(policy, InstalledJointTrackingObservationPolicyV1):
        raise TypeError("policy must be InstalledJointTrackingObservationPolicyV1")
    revalidate_simulation_context(context)
    for value, label in (
        (source_export_sha256, "source_export_sha256"),
        (native_identity_sha256, "native_identity_sha256"),
        (acquisition_qualification_sha256, "acquisition_qualification_sha256"),
    ):
        _digest(value, label)
    try:
        retained = tuple(observations)
    except TypeError as exc:
        raise TypeError("observations must be a finite sequence") from exc
    if not retained or len(retained) > 1_024 or any(
        not isinstance(item, RetainedJointTrackingObservationV1)
        for item in retained
    ):
        raise TypingObservedRouteEntryTrackingV1Error(
            "retained observations are empty, oversized, or malformed"
        )
    if (
        policy.build_snapshot_sha256 != dynamics["build_snapshot_sha256"]
        or policy.build_snapshot_sha256 != context.snapshot.snapshot_hash
        or policy.controller_session_id != dynamics["controller_session_id"]
    ):
        raise TypingObservedRouteEntryTrackingV1Error(
            "tracking policy, schedule, or active context lineage differs"
        )
    analysis = _analyze(dynamics, policy, retained)
    observation_documents = [item.to_dict() for item in retained]
    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": dynamics["request_id"],
        "materialization_sha256": dynamics["materialization_sha256"],
        "observed_route_entry_dynamics": dynamics,
        "observed_route_entry_dynamics_sha256": dynamics[
            "observed_route_entry_dynamics_sha256"
        ],
        "build_snapshot_sha256": dynamics["build_snapshot_sha256"],
        "controller_session_id": dynamics["controller_session_id"],
        "policy": policy.to_dict(),
        "policy_sha256": policy.policy_sha256,
        "source_export_sha256": source_export_sha256,
        "native_identity_sha256": native_identity_sha256,
        "acquisition_qualification_sha256": acquisition_qualification_sha256,
        "observations": observation_documents,
        "observation_set_sha256": _sha(observation_documents),
        "analysis": analysis,
        "analysis_sha256": _sha(analysis),
        "sampled_tracking_qualified": True,
        "endpoint_settling_observed": True,
        "continuous_controller_tracking_qualified": False,
        "continuous_collision_proven": False,
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
    return {**core, "observed_route_entry_tracking_sha256": _sha(core)}


def parse_typing_observed_route_entry_tracking_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly reconstruct retained sample analysis and execution gates."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedRouteEntryTrackingV1Error(
            "entry tracking fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("observed_route_entry_tracking_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedRouteEntryTrackingV1Error(
            "entry tracking hash differs"
        )
    try:
        dynamics = parse_typing_observed_route_entry_dynamics_v1(
            value["observed_route_entry_dynamics"]
        )
    except (TypeError, TypingObservedRouteEntryDynamicsV1Error) as exc:
        raise TypingObservedRouteEntryTrackingV1Error(str(exc)) from exc
    policy = _policy(value["policy"])
    observations = tuple(_observation(item) for item in value["observations"])
    analysis = _analyze(dynamics, policy, observations)
    digests = (
        "materialization_sha256", "observed_route_entry_dynamics_sha256",
        "build_snapshot_sha256", "policy_sha256", "source_export_sha256",
        "native_identity_sha256", "acquisition_qualification_sha256",
        "observation_set_sha256", "analysis_sha256",
    )
    if (
        value["schema"] != SCHEMA
        or value["status"] != STATUS
        or any(
            not isinstance(value[field], str)
            or _SHA.fullmatch(value[field]) is None
            for field in digests
        )
        or value["observed_route_entry_dynamics_sha256"]
        != dynamics["observed_route_entry_dynamics_sha256"]
        or value["build_snapshot_sha256"] != dynamics["build_snapshot_sha256"]
        or value["controller_session_id"] != dynamics["controller_session_id"]
        or value["controller_session_id"] != policy.controller_session_id
        or value["policy_sha256"] != policy.policy_sha256
        or value["observation_set_sha256"]
        != _sha([item.to_dict() for item in observations])
        or value["analysis"] != analysis
        or value["analysis_sha256"] != _sha(analysis)
        or value["sampled_tracking_qualified"] is not True
        or value["endpoint_settling_observed"] is not True
        or value["continuous_controller_tracking_qualified"] is not False
        or value["continuous_collision_proven"] is not False
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
        raise TypingObservedRouteEntryTrackingV1Error(
            "entry tracking lineage, analysis, gates, or authority differs"
        )
    return dict(value)


__all__ = [
    "InstalledJointTrackingObservationPolicyV1", "POLICY_SCHEMA",
    "REQUIRED_NEXT_EVIDENCE", "RetainedJointTrackingObservationV1", "SCHEMA",
    "SAMPLE_SCHEMA", "STATUS", "TypingObservedRouteEntryTrackingV1Error",
    "parse_typing_observed_route_entry_tracking_v1",
    "qualify_typing_observed_route_entry_tracking_v1",
]
