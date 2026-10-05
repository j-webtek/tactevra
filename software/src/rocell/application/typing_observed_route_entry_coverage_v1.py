"""Qualify bounded retained telemetry coverage over an ARM-153 schedule.

This hardware-incapable adapter consumes an ARM-154 sampled-tracking result and
a denser retained joint stream.  It bounds observation gaps and interpolation
residuals over the scheduled motion.  Finite sampling never becomes a
mathematical proof of continuous tracking or execution authority.
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
from .typing_observed_route_entry_tracking_v1 import (
    TypingObservedRouteEntryTrackingV1Error,
    parse_typing_observed_route_entry_tracking_v1,
)


SCHEMA = "rocell.typing_observed_route_entry_coverage.v1"
POLICY_SCHEMA = "rocell.installed_joint_telemetry_coverage_policy.v1"
SAMPLE_SCHEMA = "rocell.retained_dense_joint_telemetry_sample.v1"
STATUS = "BOUNDED_MOTION_TELEMETRY_COVERAGE_QUALIFIED"
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
    "observed_route_entry_tracking", "observed_route_entry_tracking_sha256",
    "observed_route_entry_dynamics_sha256", "build_snapshot_sha256",
    "controller_session_id", "policy", "policy_sha256",
    "source_export_sha256", "native_identity_sha256",
    "acquisition_qualification_sha256", "telemetry_samples",
    "telemetry_set_sha256", "coverage_analysis", "coverage_analysis_sha256",
    "bounded_motion_telemetry_coverage_qualified",
    "bounded_interpolated_tracking_qualified",
    "continuous_controller_tracking_qualified", "continuous_collision_proven",
    "required_next_evidence", "permit_review_ready", "eligible_for_executor",
    "automatic_retry_allowed", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "physical_authority",
    "observed_route_entry_coverage_sha256",
}
_POLICY_FIELDS = {
    "schema", "policy_id", "source_kind", "build_snapshot_sha256",
    "controller_session_id", "qualification_evidence_sha256",
    "maximum_observation_gap_ns", "maximum_interpolated_error_rad",
    "installed_policy_qualification",
}


class TypingObservedRouteEntryCoverageV1Error(ValueError):
    """Dense telemetry coverage or its exact lineage is invalid."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedRouteEntryCoverageV1Error(
            "telemetry coverage is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise TypingObservedRouteEntryCoverageV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _joint_map(value: object, label: str, *, bounded: bool) -> MappingProxyType:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingObservedRouteEntryCoverageV1Error(
            f"{label} must use exact canonical joint order"
        )
    result = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypingObservedRouteEntryCoverageV1Error(
                f"{label}.{name} must be numeric"
            )
        number = float(raw)
        if not math.isfinite(number) or (bounded and not 0.0 < number <= 1.0):
            raise TypingObservedRouteEntryCoverageV1Error(
                f"{label}.{name} is outside its finite bound"
            )
        result[name] = number
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class InstalledJointTelemetryCoveragePolicyV1:
    policy_id: str
    build_snapshot_sha256: str
    controller_session_id: str
    qualification_evidence_sha256: str
    maximum_observation_gap_ns: int
    maximum_interpolated_error_rad: Mapping[str, float]
    source_kind: str = "PHYSICAL_QUALIFIED"
    installed_policy_qualification: bool = True
    schema: str = POLICY_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != POLICY_SCHEMA
            or self.source_kind != "PHYSICAL_QUALIFIED"
            or self.installed_policy_qualification is not True
        ):
            raise TypingObservedRouteEntryCoverageV1Error(
                "coverage policy lacks installed physical qualification"
            )
        if (
            not isinstance(self.policy_id, str)
            or not self.policy_id
            or self.policy_id != self.policy_id.strip()
            or not isinstance(self.controller_session_id, str)
            or not self.controller_session_id
            or self.controller_session_id != self.controller_session_id.strip()
        ):
            raise TypingObservedRouteEntryCoverageV1Error(
                "coverage policy identifiers must be nonempty"
            )
        _digest(self.build_snapshot_sha256, "build_snapshot_sha256")
        _digest(
            self.qualification_evidence_sha256,
            "qualification_evidence_sha256",
        )
        if (
            isinstance(self.maximum_observation_gap_ns, bool)
            or not isinstance(self.maximum_observation_gap_ns, int)
            or not 1_000_000 <= self.maximum_observation_gap_ns <= 2_000_000_000
        ):
            raise TypingObservedRouteEntryCoverageV1Error(
                "maximum_observation_gap_ns is outside its bounded range"
            )
        object.__setattr__(
            self,
            "maximum_interpolated_error_rad",
            _joint_map(
                self.maximum_interpolated_error_rad,
                "maximum_interpolated_error_rad",
                bounded=True,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "source_kind": self.source_kind,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "controller_session_id": self.controller_session_id,
            "qualification_evidence_sha256": self.qualification_evidence_sha256,
            "maximum_observation_gap_ns": self.maximum_observation_gap_ns,
            "maximum_interpolated_error_rad": dict(
                self.maximum_interpolated_error_rad
            ),
            "installed_policy_qualification": True,
        }

    @property
    def policy_sha256(self) -> str:
        return _sha(self.to_dict())


@dataclass(frozen=True, slots=True)
class RetainedDenseJointTelemetrySampleV1:
    captured_monotonic_ns: int
    schedule_elapsed_ns: int
    joint_positions_rad: Mapping[str, float]
    joint_velocities_rad_s: Mapping[str, float]
    source_record_sha256: str
    schema: str = SAMPLE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SAMPLE_SCHEMA:
            raise TypingObservedRouteEntryCoverageV1Error(
                "dense telemetry sample schema differs"
            )
        if (
            isinstance(self.captured_monotonic_ns, bool)
            or not isinstance(self.captured_monotonic_ns, int)
            or self.captured_monotonic_ns <= 0
            or isinstance(self.schedule_elapsed_ns, bool)
            or not isinstance(self.schedule_elapsed_ns, int)
            or self.schedule_elapsed_ns < 0
        ):
            raise TypingObservedRouteEntryCoverageV1Error(
                "dense telemetry timestamps are invalid"
            )
        object.__setattr__(
            self,
            "joint_positions_rad",
            _joint_map(self.joint_positions_rad, "joint_positions_rad", bounded=False),
        )
        object.__setattr__(
            self,
            "joint_velocities_rad_s",
            _joint_map(
                self.joint_velocities_rad_s,
                "joint_velocities_rad_s",
                bounded=False,
            ),
        )
        _digest(self.source_record_sha256, "source_record_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "captured_monotonic_ns": self.captured_monotonic_ns,
            "schedule_elapsed_ns": self.schedule_elapsed_ns,
            "joint_positions_rad": dict(self.joint_positions_rad),
            "joint_velocities_rad_s": dict(self.joint_velocities_rad_s),
            "source_record_sha256": self.source_record_sha256,
        }

    @property
    def sample_sha256(self) -> str:
        return _sha(self.to_dict())


def _policy(value: object) -> InstalledJointTelemetryCoveragePolicyV1:
    if not isinstance(value, Mapping) or set(value) != _POLICY_FIELDS:
        raise TypingObservedRouteEntryCoverageV1Error(
            "coverage policy fields differ"
        )
    return InstalledJointTelemetryCoveragePolicyV1(
        policy_id=value["policy_id"],
        build_snapshot_sha256=value["build_snapshot_sha256"],
        controller_session_id=value["controller_session_id"],
        qualification_evidence_sha256=value["qualification_evidence_sha256"],
        maximum_observation_gap_ns=value["maximum_observation_gap_ns"],
        maximum_interpolated_error_rad=value["maximum_interpolated_error_rad"],
        source_kind=value["source_kind"],
        installed_policy_qualification=value["installed_policy_qualification"],
        schema=value["schema"],
    )


def _sample(value: object) -> RetainedDenseJointTelemetrySampleV1:
    if not isinstance(value, Mapping):
        raise TypingObservedRouteEntryCoverageV1Error(
            "dense telemetry sample must be an object"
        )
    return RetainedDenseJointTelemetrySampleV1(
        captured_monotonic_ns=value.get("captured_monotonic_ns"),
        schedule_elapsed_ns=value.get("schedule_elapsed_ns"),
        joint_positions_rad=value.get("joint_positions_rad"),
        joint_velocities_rad_s=value.get("joint_velocities_rad_s"),
        source_record_sha256=value.get("source_record_sha256"),
        schema=value.get("schema"),
    )


def _interpolated_target(
    scheduled: Sequence[Mapping[str, Any]], elapsed_ns: int,
) -> tuple[int, float, dict[str, float]]:
    if elapsed_ns == scheduled[-1]["time_from_start_ns"]:
        return len(scheduled) - 2, 1.0, dict(scheduled[-1]["joint_positions_rad"])
    for index in range(len(scheduled) - 1):
        start = scheduled[index]
        end = scheduled[index + 1]
        if start["time_from_start_ns"] <= elapsed_ns < end["time_from_start_ns"]:
            span = end["time_from_start_ns"] - start["time_from_start_ns"]
            ratio = (elapsed_ns - start["time_from_start_ns"]) / span
            target = {
                name: start["joint_positions_rad"][name] + ratio * (
                    end["joint_positions_rad"][name]
                    - start["joint_positions_rad"][name]
                )
                for name in ARM_JOINT_NAMES
            }
            return index, ratio, target
    raise TypingObservedRouteEntryCoverageV1Error(
        "dense telemetry sample is outside the scheduled motion interval"
    )


def _analyze(
    tracking: Mapping[str, Any],
    policy: InstalledJointTelemetryCoveragePolicyV1,
    samples: Sequence[RetainedDenseJointTelemetrySampleV1],
) -> dict[str, Any]:
    scheduled = tracking["observed_route_entry_dynamics"]["schedule"]["samples"]
    total = scheduled[-1]["time_from_start_ns"]
    if not 2 <= len(samples) <= 4_096:
        raise TypingObservedRouteEntryCoverageV1Error(
            "dense telemetry stream is empty or oversized"
        )
    if samples[0].schedule_elapsed_ns != 0 or samples[-1].schedule_elapsed_ns != total:
        raise TypingObservedRouteEntryCoverageV1Error(
            "dense telemetry must cover exact scheduled motion boundaries"
        )
    prior_capture = 0
    prior_elapsed = -1
    maximum_gap = 0
    maximum_error = {name: 0.0 for name in ARM_JOINT_NAMES}
    rows = []
    for index, sample in enumerate(samples):
        if (
            sample.captured_monotonic_ns <= prior_capture
            or sample.schedule_elapsed_ns <= prior_elapsed
            and index > 0
        ):
            raise TypingObservedRouteEntryCoverageV1Error(
                "dense telemetry order is not strictly increasing"
            )
        if index:
            gap = sample.schedule_elapsed_ns - prior_elapsed
            maximum_gap = max(maximum_gap, gap)
            if gap > policy.maximum_observation_gap_ns:
                raise TypingObservedRouteEntryCoverageV1Error(
                    "dense telemetry exceeds the maximum observation gap"
                )
        segment, ratio, target = _interpolated_target(
            scheduled, sample.schedule_elapsed_ns
        )
        errors = {
            name: abs(sample.joint_positions_rad[name] - target[name])
            for name in ARM_JOINT_NAMES
        }
        if any(
            errors[name] > policy.maximum_interpolated_error_rad[name]
            for name in ARM_JOINT_NAMES
        ):
            raise TypingObservedRouteEntryCoverageV1Error(
                "interpolated telemetry tracking exceeds its qualified bound"
            )
        for name in ARM_JOINT_NAMES:
            maximum_error[name] = max(maximum_error[name], errors[name])
        rows.append({
            "sample_sequence": index,
            "sample_sha256": sample.sample_sha256,
            "source_segment_index": segment,
            "interpolation_ratio": ratio,
            "absolute_position_error_rad": errors,
        })
        prior_capture = sample.captured_monotonic_ns
        prior_elapsed = sample.schedule_elapsed_ns
    return {
        "telemetry_sample_count": len(samples),
        "covered_motion_duration_ns": total,
        "maximum_observation_gap_ns": maximum_gap,
        "maximum_interpolated_error_rad": maximum_error,
        "sample_rows": rows,
        "motion_boundaries_observed": True,
        "all_observation_gaps_within_bound": True,
        "all_interpolated_samples_within_bound": True,
    }


def qualify_typing_observed_route_entry_coverage_v1(
    observed_route_entry_tracking: Mapping[str, Any],
    context: SimulationContext,
    policy: InstalledJointTelemetryCoveragePolicyV1,
    telemetry_samples: Sequence[RetainedDenseJointTelemetrySampleV1],
    *,
    source_export_sha256: str,
    native_identity_sha256: str,
    acquisition_qualification_sha256: str,
) -> dict[str, Any]:
    """Bind a bounded dense retained stream to one exact ARM-154 result."""

    try:
        tracking = parse_typing_observed_route_entry_tracking_v1(
            observed_route_entry_tracking
        )
    except TypingObservedRouteEntryTrackingV1Error as exc:
        raise TypingObservedRouteEntryCoverageV1Error(str(exc)) from exc
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(policy, InstalledJointTelemetryCoveragePolicyV1):
        raise TypeError("policy must be InstalledJointTelemetryCoveragePolicyV1")
    revalidate_simulation_context(context)
    for value, label in (
        (source_export_sha256, "source_export_sha256"),
        (native_identity_sha256, "native_identity_sha256"),
        (acquisition_qualification_sha256, "acquisition_qualification_sha256"),
    ):
        _digest(value, label)
    try:
        retained = tuple(telemetry_samples)
    except TypeError as exc:
        raise TypeError("telemetry_samples must be a finite sequence") from exc
    if any(not isinstance(item, RetainedDenseJointTelemetrySampleV1) for item in retained):
        raise TypingObservedRouteEntryCoverageV1Error(
            "dense telemetry stream contains a malformed sample"
        )
    if (
        policy.build_snapshot_sha256 != tracking["build_snapshot_sha256"]
        or policy.build_snapshot_sha256 != context.snapshot.snapshot_hash
        or policy.controller_session_id != tracking["controller_session_id"]
    ):
        raise TypingObservedRouteEntryCoverageV1Error(
            "coverage policy, tracking evidence, or active context lineage differs"
        )
    analysis = _analyze(tracking, policy, retained)
    sample_documents = [item.to_dict() for item in retained]
    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": tracking["request_id"],
        "materialization_sha256": tracking["materialization_sha256"],
        "observed_route_entry_tracking": tracking,
        "observed_route_entry_tracking_sha256": tracking[
            "observed_route_entry_tracking_sha256"
        ],
        "observed_route_entry_dynamics_sha256": tracking[
            "observed_route_entry_dynamics_sha256"
        ],
        "build_snapshot_sha256": tracking["build_snapshot_sha256"],
        "controller_session_id": tracking["controller_session_id"],
        "policy": policy.to_dict(),
        "policy_sha256": policy.policy_sha256,
        "source_export_sha256": source_export_sha256,
        "native_identity_sha256": native_identity_sha256,
        "acquisition_qualification_sha256": acquisition_qualification_sha256,
        "telemetry_samples": sample_documents,
        "telemetry_set_sha256": _sha(sample_documents),
        "coverage_analysis": analysis,
        "coverage_analysis_sha256": _sha(analysis),
        "bounded_motion_telemetry_coverage_qualified": True,
        "bounded_interpolated_tracking_qualified": True,
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
    return {**core, "observed_route_entry_coverage_sha256": _sha(core)}


def parse_typing_observed_route_entry_coverage_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct dense coverage analysis and retained zero-authority gates."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedRouteEntryCoverageV1Error(
            "entry coverage fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("observed_route_entry_coverage_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedRouteEntryCoverageV1Error(
            "entry coverage hash differs"
        )
    try:
        tracking = parse_typing_observed_route_entry_tracking_v1(
            value["observed_route_entry_tracking"]
        )
    except (TypeError, TypingObservedRouteEntryTrackingV1Error) as exc:
        raise TypingObservedRouteEntryCoverageV1Error(str(exc)) from exc
    policy = _policy(value["policy"])
    samples = tuple(_sample(item) for item in value["telemetry_samples"])
    analysis = _analyze(tracking, policy, samples)
    digests = (
        "materialization_sha256", "observed_route_entry_tracking_sha256",
        "observed_route_entry_dynamics_sha256", "build_snapshot_sha256",
        "policy_sha256", "source_export_sha256", "native_identity_sha256",
        "acquisition_qualification_sha256", "telemetry_set_sha256",
        "coverage_analysis_sha256",
    )
    if (
        value["schema"] != SCHEMA
        or value["status"] != STATUS
        or any(
            not isinstance(value[field], str)
            or _SHA.fullmatch(value[field]) is None
            for field in digests
        )
        or value["observed_route_entry_tracking_sha256"]
        != tracking["observed_route_entry_tracking_sha256"]
        or value["observed_route_entry_dynamics_sha256"]
        != tracking["observed_route_entry_dynamics_sha256"]
        or value["build_snapshot_sha256"] != tracking["build_snapshot_sha256"]
        or value["controller_session_id"] != tracking["controller_session_id"]
        or value["controller_session_id"] != policy.controller_session_id
        or value["policy_sha256"] != policy.policy_sha256
        or value["telemetry_set_sha256"] != _sha([item.to_dict() for item in samples])
        or value["coverage_analysis"] != analysis
        or value["coverage_analysis_sha256"] != _sha(analysis)
        or value["bounded_motion_telemetry_coverage_qualified"] is not True
        or value["bounded_interpolated_tracking_qualified"] is not True
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
        raise TypingObservedRouteEntryCoverageV1Error(
            "entry coverage lineage, analysis, gates, or authority differs"
        )
    return dict(value)


__all__ = [
    "InstalledJointTelemetryCoveragePolicyV1", "POLICY_SCHEMA",
    "REQUIRED_NEXT_EVIDENCE", "RetainedDenseJointTelemetrySampleV1", "SCHEMA",
    "SAMPLE_SCHEMA", "STATUS", "TypingObservedRouteEntryCoverageV1Error",
    "parse_typing_observed_route_entry_coverage_v1",
    "qualify_typing_observed_route_entry_coverage_v1",
]
