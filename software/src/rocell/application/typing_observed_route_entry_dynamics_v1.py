"""Time-scale a collision-screened observed entry against measured limits.

This lane is deliberately separate from the synthetic PC1 scheduler.  A fresh,
build/session-bound physical profile may qualify planned velocity, acceleration,
jerk, controller cadence, and settling policy.  It cannot prove that the
controller tracked or settled, and it creates no wire commands or authority.
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

from .bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
)
from .context import SimulationContext, revalidate_simulation_context
from .typing_observed_route_entry_sweep_v1 import (
    CLEAR_STATUS as SWEEP_CLEAR_STATUS,
    TypingObservedRouteEntrySweepV1Error,
    parse_typing_observed_route_entry_sweep_v1,
)
from .typing_observed_route_entry_v1 import (
    TypingObservedRouteEntryV1Error,
    parse_typing_observed_route_entry_v1,
)


SCHEMA = "rocell.typing_observed_route_entry_dynamics.v1"
PROFILE_SCHEMA = "rocell.measured_typing_joint_dynamics_profile.v1"
STATUS = "READY_FOR_CONTROLLER_TRACKING_AND_SETTLING_QUALIFICATION"
MAX_SCALE_ITERATIONS = 32
REQUIRED_NEXT_EVIDENCE = (
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
    "ACCEPTED_GLOBAL_PAIR_EXCLUSIONS_REQUIRED",
    "PHASE_LOCAL_CONTACT_POLICY_REQUIRED",
    "INSTALLED_PHYSICAL_QUALIFICATION_REQUIRED",
    "CONTINUOUS_COLLISION_QUALIFICATION_REQUIRED",
    "CONTROLLER_TRACKING_QUALIFICATION_REQUIRED",
    "POST_EXECUTION_SETTLING_OBSERVATION_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "status", "request_id", "materialization_sha256",
    "observed_route_entry_sha256", "observed_route_entry_sweep_sha256",
    "observed_ik_seed_sha256", "observed_start_state_sha256",
    "calibration_snapshot_sha256", "build_snapshot_sha256",
    "controller_session_id", "dynamics_profile", "dynamics_profile_sha256",
    "sample_count", "segment_count", "sample_plan_sha256", "schedule",
    "schedule_sha256", "installed_dynamics_profile_qualified",
    "planned_dynamics_within_measured_limits", "controller_tracking_qualified",
    "settling_policy_bound", "settling_observed", "continuous_collision_proven",
    "required_next_evidence", "permit_review_ready", "eligible_for_executor",
    "automatic_retry_allowed", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "physical_authority",
    "observed_route_entry_dynamics_sha256",
}
_PROFILE_FIELDS = {
    "schema", "profile_id", "source_kind", "build_snapshot_sha256",
    "controller_session_id", "qualification_evidence_sha256",
    "qualified_monotonic_ns", "valid_until_monotonic_ns",
    "maximum_velocity_rad_s", "maximum_acceleration_rad_s2",
    "maximum_jerk_rad_s3", "maximum_time_scale_factor",
    "minimum_segment_duration_ns", "controller_update_period_ns",
    "settle_position_tolerance_rad", "settle_velocity_tolerance_rad_s",
    "settle_dwell_ns", "installed_dynamics_qualification",
}


class TypingObservedRouteEntryDynamicsV1Error(ValueError):
    """Measured dynamics profile, schedule, or lineage is invalid."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedRouteEntryDynamicsV1Error(
            "entry dynamics value is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise TypingObservedRouteEntryDynamicsV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _positive(value: object, label: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypingObservedRouteEntryDynamicsV1Error(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result <= maximum:
        raise TypingObservedRouteEntryDynamicsV1Error(
            f"{label} must be finite in (0, {maximum}]"
        )
    return result


def _joint_map(value: object, label: str, maximum: float) -> MappingProxyType:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingObservedRouteEntryDynamicsV1Error(
            f"{label} must use exact canonical joint order"
        )
    return MappingProxyType(
        {
            name: _positive(value[name], f"{label}.{name}", maximum)
            for name in ARM_JOINT_NAMES
        }
    )


@dataclass(frozen=True, slots=True)
class MeasuredTypingJointDynamicsProfileV1:
    profile_id: str
    build_snapshot_sha256: str
    controller_session_id: str
    qualification_evidence_sha256: str
    qualified_monotonic_ns: int
    valid_until_monotonic_ns: int
    maximum_velocity_rad_s: Mapping[str, float]
    maximum_acceleration_rad_s2: Mapping[str, float]
    maximum_jerk_rad_s3: Mapping[str, float]
    maximum_time_scale_factor: float
    minimum_segment_duration_ns: int
    controller_update_period_ns: int
    settle_position_tolerance_rad: Mapping[str, float]
    settle_velocity_tolerance_rad_s: Mapping[str, float]
    settle_dwell_ns: int
    source_kind: str = "PHYSICAL_QUALIFIED"
    installed_dynamics_qualification: bool = True
    schema: str = PROFILE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROFILE_SCHEMA or self.source_kind != "PHYSICAL_QUALIFIED":
            raise TypingObservedRouteEntryDynamicsV1Error(
                "measured dynamics profile schema or source differs"
            )
        if self.installed_dynamics_qualification is not True:
            raise TypingObservedRouteEntryDynamicsV1Error(
                "measured dynamics profile must carry installed-limit qualification"
            )
        if (
            not isinstance(self.profile_id, str)
            or not self.profile_id
            or self.profile_id != self.profile_id.strip()
            or not isinstance(self.controller_session_id, str)
            or not self.controller_session_id
            or self.controller_session_id != self.controller_session_id.strip()
        ):
            raise TypingObservedRouteEntryDynamicsV1Error(
                "profile and controller session identifiers must be nonempty"
            )
        _digest(self.build_snapshot_sha256, "build_snapshot_sha256")
        _digest(self.qualification_evidence_sha256, "qualification_evidence_sha256")
        if (
            isinstance(self.qualified_monotonic_ns, bool)
            or not isinstance(self.qualified_monotonic_ns, int)
            or self.qualified_monotonic_ns <= 0
            or isinstance(self.valid_until_monotonic_ns, bool)
            or not isinstance(self.valid_until_monotonic_ns, int)
            or self.valid_until_monotonic_ns <= self.qualified_monotonic_ns
        ):
            raise TypingObservedRouteEntryDynamicsV1Error(
                "profile qualification freshness interval is invalid"
            )
        for field, maximum in (
            ("maximum_velocity_rad_s", 100.0),
            ("maximum_acceleration_rad_s2", 1_000.0),
            ("maximum_jerk_rad_s3", 10_000.0),
            ("settle_position_tolerance_rad", 1.0),
            ("settle_velocity_tolerance_rad_s", 10.0),
        ):
            object.__setattr__(
                self, field, _joint_map(getattr(self, field), field, maximum)
            )
        object.__setattr__(
            self,
            "maximum_time_scale_factor",
            _positive(
                self.maximum_time_scale_factor,
                "maximum_time_scale_factor",
                1_000.0,
            ),
        )
        if self.maximum_time_scale_factor < 1.0:
            raise TypingObservedRouteEntryDynamicsV1Error(
                "maximum_time_scale_factor must be at least 1"
            )
        for field, lower, upper in (
            ("minimum_segment_duration_ns", 1_000_000, 10_000_000_000),
            ("controller_update_period_ns", 100_000, 1_000_000_000),
            ("settle_dwell_ns", 1_000_000, 60_000_000_000),
        ):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not lower <= value <= upper
            ):
                raise TypingObservedRouteEntryDynamicsV1Error(
                    f"{field} is outside its bounded integer range"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "profile_id": self.profile_id,
            "source_kind": self.source_kind,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "controller_session_id": self.controller_session_id,
            "qualification_evidence_sha256": self.qualification_evidence_sha256,
            "qualified_monotonic_ns": self.qualified_monotonic_ns,
            "valid_until_monotonic_ns": self.valid_until_monotonic_ns,
            "maximum_velocity_rad_s": dict(self.maximum_velocity_rad_s),
            "maximum_acceleration_rad_s2": dict(
                self.maximum_acceleration_rad_s2
            ),
            "maximum_jerk_rad_s3": dict(self.maximum_jerk_rad_s3),
            "maximum_time_scale_factor": self.maximum_time_scale_factor,
            "minimum_segment_duration_ns": self.minimum_segment_duration_ns,
            "controller_update_period_ns": self.controller_update_period_ns,
            "settle_position_tolerance_rad": dict(
                self.settle_position_tolerance_rad
            ),
            "settle_velocity_tolerance_rad_s": dict(
                self.settle_velocity_tolerance_rad_s
            ),
            "settle_dwell_ns": self.settle_dwell_ns,
            "installed_dynamics_qualification": True,
        }

    @property
    def profile_sha256(self) -> str:
        return _sha(self.to_dict())


def _demands(
    timestamps: tuple[int, ...],
    positions: tuple[Mapping[str, float], ...],
) -> tuple[list[dict[str, float]], list[dict[str, float]], list[dict[str, float]]]:
    durations = [
        (timestamps[index + 1] - timestamps[index]) / 1e9
        for index in range(len(positions) - 1)
    ]
    velocity = [
        {
            name: abs(
                (positions[index + 1][name] - positions[index][name])
                / durations[index]
            )
            for name in ARM_JOINT_NAMES
        }
        for index in range(len(durations))
    ]
    acceleration = [{name: 0.0 for name in ARM_JOINT_NAMES} for _ in velocity]
    intervals = [0.0 for _ in velocity]
    signed_velocity = [
        {
            name: (positions[index + 1][name] - positions[index][name])
            / durations[index]
            for name in ARM_JOINT_NAMES
        }
        for index in range(len(durations))
    ]
    signed_acceleration = [dict(item) for item in acceleration]
    for index in range(1, len(velocity)):
        intervals[index] = (durations[index - 1] + durations[index]) / 2.0
        signed_acceleration[index] = {
            name: (
                signed_velocity[index][name] - signed_velocity[index - 1][name]
            ) / intervals[index]
            for name in ARM_JOINT_NAMES
        }
        acceleration[index] = {
            name: abs(signed_acceleration[index][name]) for name in ARM_JOINT_NAMES
        }
    jerk = [{name: 0.0 for name in ARM_JOINT_NAMES} for _ in velocity]
    for index in range(2, len(velocity)):
        interval = (intervals[index - 1] + intervals[index]) / 2.0
        jerk[index] = {
            name: abs(
                (signed_acceleration[index][name]
                 - signed_acceleration[index - 1][name]) / interval
            )
            for name in ARM_JOINT_NAMES
        }
    return velocity, acceleration, jerk


def schedule_bounded_joint_samples_v1(
    plan: Sequence[BoundedJointConfigurationSample],
    profile: MeasuredTypingJointDynamicsProfileV1,
) -> dict[str, Any]:
    """Build a cadence-aligned, limit-screened zero-authority schedule."""

    if not isinstance(profile, MeasuredTypingJointDynamicsProfileV1):
        raise TypeError("profile must be MeasuredTypingJointDynamicsProfileV1")
    try:
        samples = tuple(plan)
    except TypeError as exc:
        raise TypeError("plan must be a finite sequence") from exc
    if (
        not 2 <= len(samples) <= 256
        or any(
            not isinstance(item, BoundedJointConfigurationSample)
            or item.sample_sequence != index
            for index, item in enumerate(samples)
        )
    ):
        raise TypingObservedRouteEntryDynamicsV1Error(
            "bounded joint sample plan is incomplete or noncanonical"
        )
    positions = tuple(item.joint_positions_rad for item in samples)
    scale = 1.0
    final = None
    for _ in range(MAX_SCALE_ITERATIONS):
        raw_duration = math.ceil(profile.minimum_segment_duration_ns * scale)
        duration = (
            math.ceil(raw_duration / profile.controller_update_period_ns)
            * profile.controller_update_period_ns
        )
        timestamps = tuple(index * duration for index in range(len(samples)))
        velocity, acceleration, jerk = _demands(timestamps, positions)
        peaks = tuple(
            {
                name: max((item[name] for item in series), default=0.0)
                for name in ARM_JOINT_NAMES
            }
            for series in (velocity, acceleration, jerk)
        )
        required = max(
            max(
                peaks[0][name] / profile.maximum_velocity_rad_s[name]
                for name in ARM_JOINT_NAMES
            ),
            math.sqrt(max(
                peaks[1][name] / profile.maximum_acceleration_rad_s2[name]
                for name in ARM_JOINT_NAMES
            )),
            max(
                peaks[2][name] / profile.maximum_jerk_rad_s3[name]
                for name in ARM_JOINT_NAMES
            ) ** (1.0 / 3.0),
        )
        if required <= 1.0 + 1e-12:
            final = duration, timestamps, velocity, acceleration, jerk, peaks
            break
        scale *= required * (1.0 + 1e-9)
        if scale > profile.maximum_time_scale_factor + 1e-12:
            raise TypingObservedRouteEntryDynamicsV1Error(
                "required measured-dynamics time scaling exceeds profile bound"
            )
    if final is None:
        raise TypingObservedRouteEntryDynamicsV1Error(
            "measured-dynamics time scaling did not converge"
        )
    duration, timestamps, velocity, acceleration, jerk, peaks = final
    segments = []
    for index in range(len(samples) - 1):
        segments.append(
            {
                "sequence": index,
                "source_sample_sha256": samples[index].content_sha256,
                "destination_sample_sha256": samples[index + 1].content_sha256,
                "duration_ns": duration,
                "velocity_rad_s": velocity[index],
                "acceleration_rad_s2": acceleration[index],
                "jerk_rad_s3": jerk[index],
            }
        )
    core = {
        "schema": "rocell.measured_typing_entry_joint_schedule.v1",
        "profile_sha256": profile.profile_sha256,
        "time_scale_factor": scale,
        "controller_update_period_ns": profile.controller_update_period_ns,
        "samples": [
            {
                **item.to_dict(),
                "sample_sha256": item.content_sha256,
                "time_from_start_ns": timestamps[index],
            }
            for index, item in enumerate(samples)
        ],
        "segments": segments,
        "sample_count": len(samples),
        "segment_count": len(segments),
        "total_motion_time_ns": timestamps[-1],
        "planned_settle_dwell_ns": profile.settle_dwell_ns,
        "peak_velocity_rad_s": peaks[0],
        "peak_acceleration_rad_s2": peaks[1],
        "peak_jerk_rad_s3": peaks[2],
        "joint_dynamics_screening_executed": True,
        "joint_dynamics_all_samples_accepted": True,
        "controller_tracking_qualified": False,
        "settling_observed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "schedule_sha256": _sha(core)}


def _plan(entry: Mapping[str, Any]) -> tuple[BoundedJointConfigurationSample, ...]:
    return tuple(
        BoundedJointConfigurationSample(
            item["sample_sequence"], item["source_segment_index"],
            item["subdivision_index"], item["subdivision_count"],
            item["interpolation_ratio"], item["joint_positions_rad"],
        )
        for item in entry["sample_plan"]
    )


def _profile(value: object) -> MeasuredTypingJointDynamicsProfileV1:
    if not isinstance(value, Mapping) or set(value) != _PROFILE_FIELDS:
        raise TypingObservedRouteEntryDynamicsV1Error(
            "measured dynamics profile fields differ"
        )
    return MeasuredTypingJointDynamicsProfileV1(
        profile_id=value["profile_id"],
        build_snapshot_sha256=value["build_snapshot_sha256"],
        controller_session_id=value["controller_session_id"],
        qualification_evidence_sha256=value["qualification_evidence_sha256"],
        qualified_monotonic_ns=value["qualified_monotonic_ns"],
        valid_until_monotonic_ns=value["valid_until_monotonic_ns"],
        maximum_velocity_rad_s=value["maximum_velocity_rad_s"],
        maximum_acceleration_rad_s2=value["maximum_acceleration_rad_s2"],
        maximum_jerk_rad_s3=value["maximum_jerk_rad_s3"],
        maximum_time_scale_factor=value["maximum_time_scale_factor"],
        minimum_segment_duration_ns=value["minimum_segment_duration_ns"],
        controller_update_period_ns=value["controller_update_period_ns"],
        settle_position_tolerance_rad=value["settle_position_tolerance_rad"],
        settle_velocity_tolerance_rad_s=value["settle_velocity_tolerance_rad_s"],
        settle_dwell_ns=value["settle_dwell_ns"],
        source_kind=value["source_kind"],
        installed_dynamics_qualification=value[
            "installed_dynamics_qualification"
        ],
        schema=value["schema"],
    )


def _scheduled_plan(value: object) -> tuple[BoundedJointConfigurationSample, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypingObservedRouteEntryDynamicsV1Error(
            "scheduled samples must be a finite sequence"
        )
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypingObservedRouteEntryDynamicsV1Error(
                "scheduled sample must be an object"
            )
        expected = {
            "sample_sequence", "sample_id", "source_segment_index",
            "subdivision_index", "subdivision_count", "interpolation_ratio",
            "joint_positions_rad", "sample_sha256", "time_from_start_ns",
        }
        if set(item) != expected or item["sample_sequence"] != index:
            raise TypingObservedRouteEntryDynamicsV1Error(
                "scheduled sample fields or order differ"
            )
        sample = BoundedJointConfigurationSample(
            item["sample_sequence"], item["source_segment_index"],
            item["subdivision_index"], item["subdivision_count"],
            item["interpolation_ratio"], item["joint_positions_rad"],
        )
        if item["sample_id"] != sample.sample_id or item["sample_sha256"] != sample.content_sha256:
            raise TypingObservedRouteEntryDynamicsV1Error(
                "scheduled sample identity differs"
            )
        result.append(sample)
    return tuple(result)


def qualify_typing_observed_route_entry_dynamics_v1(
    observed_route_entry: Mapping[str, Any],
    observed_route_entry_sweep: Mapping[str, Any],
    context: SimulationContext,
    profile: MeasuredTypingJointDynamicsProfileV1,
    *,
    evaluated_monotonic_ns: int,
) -> dict[str, Any]:
    """Bind a measured dynamics schedule to collision-screened entry evidence."""

    try:
        entry = parse_typing_observed_route_entry_v1(observed_route_entry)
        sweep = parse_typing_observed_route_entry_sweep_v1(
            observed_route_entry_sweep
        )
    except (TypingObservedRouteEntryV1Error,
            TypingObservedRouteEntrySweepV1Error) as exc:
        raise TypingObservedRouteEntryDynamicsV1Error(str(exc)) from exc
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(profile, MeasuredTypingJointDynamicsProfileV1):
        raise TypeError("profile must be MeasuredTypingJointDynamicsProfileV1")
    revalidate_simulation_context(context)
    if (
        isinstance(evaluated_monotonic_ns, bool)
        or not isinstance(evaluated_monotonic_ns, int)
        or not profile.qualified_monotonic_ns
        <= evaluated_monotonic_ns
        <= profile.valid_until_monotonic_ns
    ):
        raise TypingObservedRouteEntryDynamicsV1Error(
            "measured dynamics profile is unavailable or stale"
        )
    if (
        sweep["status"] != SWEEP_CLEAR_STATUS
        or sweep["all_entry_sweeps_clear"] is not True
        or sweep["observed_route_entry_sha256"]
        != entry["observed_route_entry_sha256"]
        or sweep["request_id"] != entry["request_id"]
        or sweep["materialization_sha256"] != entry["materialization_sha256"]
        or sweep["controller_session_id"] != entry["controller_session_id"]
        or sweep["sample_count"] != entry["sample_count"]
        or profile.build_snapshot_sha256 != entry["build_snapshot_sha256"]
        or profile.build_snapshot_sha256 != context.snapshot.snapshot_hash
        or profile.controller_session_id != entry["controller_session_id"]
    ):
        raise TypingObservedRouteEntryDynamicsV1Error(
            "entry, sweep, profile, or active context lineage differs"
        )
    plan = _plan(entry)
    schedule = schedule_bounded_joint_samples_v1(plan, profile)
    sample_hashes = [item["sample_sha256"] for item in entry["sample_plan"]]
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": entry["request_id"],
        "materialization_sha256": entry["materialization_sha256"],
        "observed_route_entry_sha256": entry["observed_route_entry_sha256"],
        "observed_route_entry_sweep_sha256": sweep[
            "observed_route_entry_sweep_sha256"
        ],
        "observed_ik_seed_sha256": entry["observed_ik_seed_sha256"],
        "observed_start_state_sha256": entry["observed_start_state_sha256"],
        "calibration_snapshot_sha256": entry["calibration_snapshot_sha256"],
        "build_snapshot_sha256": entry["build_snapshot_sha256"],
        "controller_session_id": entry["controller_session_id"],
        "dynamics_profile": profile.to_dict(),
        "dynamics_profile_sha256": profile.profile_sha256,
        "sample_count": len(plan),
        "segment_count": len(plan) - 1,
        "sample_plan_sha256": _sha(sample_hashes),
        "schedule": schedule,
        "schedule_sha256": schedule["schedule_sha256"],
        "installed_dynamics_profile_qualified": True,
        "planned_dynamics_within_measured_limits": True,
        "controller_tracking_qualified": False,
        "settling_policy_bound": True,
        "settling_observed": False,
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
    return {**core, "observed_route_entry_dynamics_sha256": _sha(core)}


def parse_typing_observed_route_entry_dynamics_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the measured-limit schedule and retained execution gates."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedRouteEntryDynamicsV1Error("entry dynamics fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("observed_route_entry_dynamics_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedRouteEntryDynamicsV1Error("entry dynamics hash differs")
    profile = value["dynamics_profile"]
    schedule = value["schedule"]
    if (
        not isinstance(profile, Mapping)
        or value["dynamics_profile_sha256"] != _sha(profile)
        or not isinstance(schedule, Mapping)
    ):
        raise TypingObservedRouteEntryDynamicsV1Error(
            "profile or schedule evidence differs"
        )
    parsed_profile = _profile(profile)
    if parsed_profile.profile_sha256 != value["dynamics_profile_sha256"]:
        raise TypingObservedRouteEntryDynamicsV1Error(
            "reconstructed dynamics profile differs"
        )
    schedule_unsigned = dict(schedule)
    schedule_hash = schedule_unsigned.pop("schedule_sha256", None)
    digests = (
        "materialization_sha256", "observed_route_entry_sha256",
        "observed_route_entry_sweep_sha256", "observed_ik_seed_sha256",
        "observed_start_state_sha256", "calibration_snapshot_sha256",
        "build_snapshot_sha256", "dynamics_profile_sha256",
        "sample_plan_sha256", "schedule_sha256",
    )
    if (
        value["schema"] != SCHEMA
        or value["status"] != STATUS
        or any(
            not isinstance(value[field], str)
            or _SHA.fullmatch(value[field]) is None
            for field in digests
        )
        or schedule_hash != _sha(schedule_unsigned)
        or value["schedule_sha256"] != schedule_hash
        or schedule.get("profile_sha256") != value["dynamics_profile_sha256"]
        or value["sample_count"] != schedule.get("sample_count")
        or value["segment_count"] != value["sample_count"] - 1
        or value["segment_count"] != schedule.get("segment_count")
        or value["installed_dynamics_profile_qualified"] is not True
        or value["planned_dynamics_within_measured_limits"] is not True
        or value["controller_tracking_qualified"] is not False
        or value["settling_policy_bound"] is not True
        or value["settling_observed"] is not False
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
        or schedule.get("controller_commands") != []
        or schedule.get("wire_commands") != []
        or schedule.get("hardware_commands_generated") != 0
        or schedule.get("hardware_access") is not False
        or schedule.get("physical_authority") is not False
    ):
        raise TypingObservedRouteEntryDynamicsV1Error(
            "entry dynamics lineage, limits, gates, or authority differs"
        )
    rebuilt_schedule = schedule_bounded_joint_samples_v1(
        _scheduled_plan(schedule.get("samples")), parsed_profile
    )
    if rebuilt_schedule != dict(schedule):
        raise TypingObservedRouteEntryDynamicsV1Error(
            "scheduled samples do not reproduce the measured-limit schedule"
        )
    return dict(value)


__all__ = [
    "MeasuredTypingJointDynamicsProfileV1", "PROFILE_SCHEMA",
    "REQUIRED_NEXT_EVIDENCE", "SCHEMA", "STATUS",
    "TypingObservedRouteEntryDynamicsV1Error",
    "parse_typing_observed_route_entry_dynamics_v1",
    "qualify_typing_observed_route_entry_dynamics_v1",
    "schedule_bounded_joint_samples_v1",
]
