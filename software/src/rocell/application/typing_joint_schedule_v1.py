"""Deterministic, zero-authority joint timing for exact typing IK samples.

PC1 consumes the exact ordered samples from the T2A/T2B-IK boundary.  It does
not regenerate geometry, infer measured dynamics, encode controller commands,
or grant physical authority.  The retained PC0 profile is synthetic and exists
only to exercise the scheduling contract until measured limits are qualified.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from rocell.kinematics import ARM_JOINT_NAMES

from .pre_camera_typing_qualification_basis_v1 import (
    PreCameraTypingQualificationBasisV1,
)
from .typing_trajectory_ik_screen_v1 import READY_STATUS as IK_READY_STATUS
from .typing_trajectory_plan_v1 import TypingTrajectoryPlanV1


SCHEMA = "rocell.typing_joint_schedule.v1"
PROFILE_SCHEMA = "rocell.typing_joint_dynamics_profile.v1"
READY_STATUS = "READY_FOR_INSTALLED_GEOMETRY_AND_FRESH_STATE_SCREENING"
MINIMUM_SEGMENT_DURATION_NS = 1_000_000
MAXIMUM_SCALE_ITERATIONS = 32
PC0_SEMANTIC_ARM_JOINT_NAMES = (
    "base",
    "shoulder",
    "elbow",
    "wrist_pitch",
    "wrist_roll",
)


class TypingJointScheduleV1Error(ValueError):
    """The exact IK results cannot form a bounded deterministic schedule."""


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
        raise TypingJointScheduleV1Error("value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TypingJointScheduleV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
    ):
        raise TypingJointScheduleV1Error(
            f"{label} must be bounded nonempty unpadded text"
        )
    return value


def _positive(value: object, label: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypingJointScheduleV1Error(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.0 < parsed <= maximum:
        raise TypingJointScheduleV1Error(
            f"{label} must be finite in (0, {maximum}]"
        )
    return parsed


def _joint_map(
    value: Mapping[str, float], label: str, *, maximum: float
) -> MappingProxyType:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingJointScheduleV1Error(
            f"{label} must use the exact canonical arm-joint order"
        )
    return MappingProxyType(
        {
            name: _positive(value[name], f"{label}.{name}", maximum)
            for name in ARM_JOINT_NAMES
        }
    )


def _joint_positions(value: object, label: str) -> MappingProxyType:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingJointScheduleV1Error(
            f"{label} must use the exact canonical arm-joint order"
        )
    parsed: dict[str, float] = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypingJointScheduleV1Error(f"{label}.{name} must be numeric")
        number = float(raw)
        if not math.isfinite(number):
            raise TypingJointScheduleV1Error(f"{label}.{name} must be finite")
        parsed[name] = number
    return MappingProxyType(parsed)


@dataclass(frozen=True, slots=True)
class TypingJointDynamicsProfileV1:
    profile_id: str
    source_kind: str
    maximum_velocity_rad_s: Mapping[str, float]
    maximum_acceleration_rad_s2: Mapping[str, float]
    maximum_jerk_rad_s3: Mapping[str, float]
    maximum_time_scale_factor: float
    physical_tracking_qualification: bool = False
    minimum_segment_duration_ns: int = MINIMUM_SEGMENT_DURATION_NS
    schema: str = PROFILE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROFILE_SCHEMA:
            raise TypingJointScheduleV1Error("unsupported dynamics profile schema")
        _identifier(self.profile_id, "profile_id")
        if self.source_kind != "SYNTHETIC_OFFLINE":
            raise TypingJointScheduleV1Error(
                "PC1 accepts only the explicitly synthetic offline profile"
            )
        if self.physical_tracking_qualification is not False:
            raise TypingJointScheduleV1Error(
                "synthetic profile cannot claim physical tracking qualification"
            )
        object.__setattr__(
            self,
            "maximum_velocity_rad_s",
            _joint_map(
                self.maximum_velocity_rad_s,
                "maximum_velocity_rad_s",
                maximum=100.0,
            ),
        )
        object.__setattr__(
            self,
            "maximum_acceleration_rad_s2",
            _joint_map(
                self.maximum_acceleration_rad_s2,
                "maximum_acceleration_rad_s2",
                maximum=1_000.0,
            ),
        )
        object.__setattr__(
            self,
            "maximum_jerk_rad_s3",
            _joint_map(
                self.maximum_jerk_rad_s3,
                "maximum_jerk_rad_s3",
                maximum=10_000.0,
            ),
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
        if (
            isinstance(self.minimum_segment_duration_ns, bool)
            or not isinstance(self.minimum_segment_duration_ns, int)
            or not 1 <= self.minimum_segment_duration_ns <= 1_000_000_000
        ):
            raise TypingJointScheduleV1Error(
                "minimum_segment_duration_ns must be an integer in [1, 1000000000]"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "profile_id": self.profile_id,
            "source_kind": self.source_kind,
            "maximum_velocity_rad_s": dict(self.maximum_velocity_rad_s),
            "maximum_acceleration_rad_s2": dict(
                self.maximum_acceleration_rad_s2
            ),
            "maximum_jerk_rad_s3": dict(self.maximum_jerk_rad_s3),
            "maximum_time_scale_factor": self.maximum_time_scale_factor,
            "minimum_segment_duration_ns": self.minimum_segment_duration_ns,
            "physical_tracking_qualification": False,
        }

    @property
    def profile_sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class TimedTypingJointSampleV1:
    sequence: int
    endpoint_sequence: int
    phase: str
    action_index: int | None
    target_id: str | None
    phase_endpoint: bool
    time_from_start_ns: int
    joint_positions_rad: Mapping[str, float]

    def __post_init__(self) -> None:
        for label, value in (
            ("sequence", self.sequence),
            ("endpoint_sequence", self.endpoint_sequence),
            ("time_from_start_ns", self.time_from_start_ns),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypingJointScheduleV1Error(
                    f"{label} must be a nonnegative integer"
                )
        if not isinstance(self.phase, str) or not self.phase:
            raise TypingJointScheduleV1Error("phase must be nonempty text")
        if self.action_index is not None and (
            isinstance(self.action_index, bool)
            or not isinstance(self.action_index, int)
            or self.action_index < 0
        ):
            raise TypingJointScheduleV1Error(
                "action_index must be null or a nonnegative integer"
            )
        if self.target_id is not None:
            _identifier(self.target_id, "target_id")
        if not isinstance(self.phase_endpoint, bool):
            raise TypingJointScheduleV1Error("phase_endpoint must be boolean")
        object.__setattr__(
            self,
            "joint_positions_rad",
            _joint_positions(self.joint_positions_rad, "joint_positions_rad"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "endpoint_sequence": self.endpoint_sequence,
            "phase": self.phase,
            "action_index": self.action_index,
            "target_id": self.target_id,
            "phase_endpoint": self.phase_endpoint,
            "time_from_start_ns": self.time_from_start_ns,
            "joint_positions_rad": dict(self.joint_positions_rad),
        }


@dataclass(frozen=True, slots=True)
class TypingJointSegmentDynamicsV1:
    sequence: int
    source_sample_sequence: int
    destination_sample_sequence: int
    duration_ns: int
    destination_phase: str
    action_index: int | None
    target_id: str | None
    velocity_rad_s: Mapping[str, float]
    acceleration_rad_s2: Mapping[str, float]
    jerk_rad_s3: Mapping[str, float]
    velocity_margin_rad_s: Mapping[str, float]
    acceleration_margin_rad_s2: Mapping[str, float]
    jerk_margin_rad_s3: Mapping[str, float]
    limiting_joint: str
    limiting_constraint: str

    def __post_init__(self) -> None:
        for label, value in (
            ("sequence", self.sequence),
            ("source_sample_sequence", self.source_sample_sequence),
            ("destination_sample_sequence", self.destination_sample_sequence),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypingJointScheduleV1Error(
                    f"{label} must be a nonnegative integer"
                )
        if (
            isinstance(self.duration_ns, bool)
            or not isinstance(self.duration_ns, int)
            or self.duration_ns <= 0
        ):
            raise TypingJointScheduleV1Error("duration_ns must be positive")
        if not isinstance(self.destination_phase, str) or not self.destination_phase:
            raise TypingJointScheduleV1Error(
                "destination_phase must be nonempty text"
            )
        if self.action_index is not None and (
            isinstance(self.action_index, bool)
            or not isinstance(self.action_index, int)
            or self.action_index < 0
        ):
            raise TypingJointScheduleV1Error(
                "action_index must be null or a nonnegative integer"
            )
        if self.target_id is not None:
            _identifier(self.target_id, "target_id")
        for field, maximum in (
            ("velocity_rad_s", 100.0),
            ("acceleration_rad_s2", 1_000.0),
            ("jerk_rad_s3", 10_000.0),
            ("velocity_margin_rad_s", 100.0),
            ("acceleration_margin_rad_s2", 1_000.0),
            ("jerk_margin_rad_s3", 10_000.0),
        ):
            value = getattr(self, field)
            if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
                raise TypingJointScheduleV1Error(
                    f"{field} must use the exact canonical arm-joint order"
                )
            parsed: dict[str, float] = {}
            for name in ARM_JOINT_NAMES:
                raw = value[name]
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    raise TypingJointScheduleV1Error(
                        f"{field}.{name} must be numeric"
                    )
                number = float(raw)
                if not math.isfinite(number) or number < -1e-12 or number > maximum:
                    raise TypingJointScheduleV1Error(
                        f"{field}.{name} is outside its bounded range"
                    )
                parsed[name] = max(0.0, number)
            object.__setattr__(self, field, MappingProxyType(parsed))
        if self.limiting_joint not in ARM_JOINT_NAMES:
            raise TypingJointScheduleV1Error("limiting_joint is not canonical")
        if self.limiting_constraint not in {"VELOCITY", "ACCELERATION", "JERK"}:
            raise TypingJointScheduleV1Error("limiting_constraint is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "source_sample_sequence": self.source_sample_sequence,
            "destination_sample_sequence": self.destination_sample_sequence,
            "duration_ns": self.duration_ns,
            "destination_phase": self.destination_phase,
            "action_index": self.action_index,
            "target_id": self.target_id,
            "velocity_rad_s": dict(self.velocity_rad_s),
            "acceleration_rad_s2": dict(self.acceleration_rad_s2),
            "jerk_rad_s3": dict(self.jerk_rad_s3),
            "velocity_margin_rad_s": dict(self.velocity_margin_rad_s),
            "acceleration_margin_rad_s2": dict(self.acceleration_margin_rad_s2),
            "jerk_margin_rad_s3": dict(self.jerk_margin_rad_s3),
            "limiting_joint": self.limiting_joint,
            "limiting_constraint": self.limiting_constraint,
        }


@dataclass(frozen=True, slots=True)
class TypingJointScheduleV1:
    source_trajectory_plan_sha256: str
    source_ik_screen_sha256: str
    profile: TypingJointDynamicsProfileV1
    time_scale_factor: float
    samples: tuple[TimedTypingJointSampleV1, ...]
    segments: tuple[TypingJointSegmentDynamicsV1, ...]
    total_motion_and_dwell_time_ns: int
    peak_velocity_rad_s: Mapping[str, float]
    peak_acceleration_rad_s2: Mapping[str, float]
    peak_jerk_rad_s3: Mapping[str, float]
    minimum_velocity_margin_rad_s: Mapping[str, float]
    minimum_acceleration_margin_rad_s2: Mapping[str, float]
    minimum_jerk_margin_rad_s3: Mapping[str, float]
    limiting_joint: str
    limiting_constraint: str
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise TypingJointScheduleV1Error("unsupported joint schedule schema")
        _digest(self.source_trajectory_plan_sha256, "source_trajectory_plan_sha256")
        _digest(self.source_ik_screen_sha256, "source_ik_screen_sha256")
        if not isinstance(self.profile, TypingJointDynamicsProfileV1):
            raise TypeError("profile must be a TypingJointDynamicsProfileV1")
        _positive(self.time_scale_factor, "time_scale_factor", 1_000.0)
        if (
            isinstance(self.total_motion_and_dwell_time_ns, bool)
            or not isinstance(self.total_motion_and_dwell_time_ns, int)
            or self.total_motion_and_dwell_time_ns <= 0
        ):
            raise TypingJointScheduleV1Error(
                "total_motion_and_dwell_time_ns must be positive"
            )
        samples = tuple(self.samples)
        if not 2 <= len(samples) <= 4096:
            raise TypingJointScheduleV1Error("sample count is outside [2, 4096]")
        if [sample.sequence for sample in samples] != list(range(len(samples))):
            raise TypingJointScheduleV1Error("sample sequence is not contiguous")
        if samples[0].time_from_start_ns != 0 or any(
            right.time_from_start_ns <= left.time_from_start_ns
            for left, right in zip(samples, samples[1:])
        ):
            raise TypingJointScheduleV1Error("sample timing is not strictly monotonic")
        object.__setattr__(self, "samples", samples)
        segments = tuple(self.segments)
        if len(segments) != len(samples) - 1:
            raise TypingJointScheduleV1Error(
                "segment count must equal sample count minus one"
            )
        if [segment.sequence for segment in segments] != list(range(len(segments))):
            raise TypingJointScheduleV1Error("segment sequence is not contiguous")
        for index, segment in enumerate(segments):
            if (
                segment.source_sample_sequence != index
                or segment.destination_sample_sequence != index + 1
                or segment.duration_ns
                != samples[index + 1].time_from_start_ns
                - samples[index].time_from_start_ns
            ):
                raise TypingJointScheduleV1Error(
                    "segment/sample timing or lineage is crossed"
                )
        object.__setattr__(self, "segments", segments)
        for field, maximum in (
            ("peak_velocity_rad_s", 100.0),
            ("peak_acceleration_rad_s2", 1_000.0),
            ("peak_jerk_rad_s3", 10_000.0),
            ("minimum_velocity_margin_rad_s", 100.0),
            ("minimum_acceleration_margin_rad_s2", 1_000.0),
            ("minimum_jerk_margin_rad_s3", 10_000.0),
        ):
            value = getattr(self, field)
            if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
                raise TypingJointScheduleV1Error(
                    f"{field} must use the exact canonical arm-joint order"
                )
            parsed: dict[str, float] = {}
            for name in ARM_JOINT_NAMES:
                raw = value[name]
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    raise TypingJointScheduleV1Error(f"{field}.{name} must be numeric")
                number = float(raw)
                if not math.isfinite(number) or number < -1e-12 or number > maximum:
                    raise TypingJointScheduleV1Error(
                        f"{field}.{name} is outside its bounded range"
                    )
                parsed[name] = max(0.0, number)
            object.__setattr__(self, field, MappingProxyType(parsed))
        if self.limiting_joint not in ARM_JOINT_NAMES:
            raise TypingJointScheduleV1Error("limiting_joint is not canonical")
        if self.limiting_constraint not in {"VELOCITY", "ACCELERATION", "JERK"}:
            raise TypingJointScheduleV1Error("limiting_constraint is invalid")

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": READY_STATUS,
            "source_trajectory_plan_sha256": self.source_trajectory_plan_sha256,
            "source_ik_screen_sha256": self.source_ik_screen_sha256,
            "profile": self.profile.to_dict(),
            "profile_sha256": self.profile.profile_sha256,
            "time_scale_factor": self.time_scale_factor,
            "samples": [sample.to_dict() for sample in self.samples],
            "sample_count": len(self.samples),
            "segments": [segment.to_dict() for segment in self.segments],
            "segment_count": len(self.segments),
            "total_motion_and_dwell_time_ns": self.total_motion_and_dwell_time_ns,
            "peak_velocity_rad_s": dict(self.peak_velocity_rad_s),
            "peak_acceleration_rad_s2": dict(self.peak_acceleration_rad_s2),
            "peak_jerk_rad_s3": dict(self.peak_jerk_rad_s3),
            "minimum_velocity_margin_rad_s": dict(
                self.minimum_velocity_margin_rad_s
            ),
            "minimum_acceleration_margin_rad_s2": dict(
                self.minimum_acceleration_margin_rad_s2
            ),
            "minimum_jerk_margin_rad_s3": dict(self.minimum_jerk_margin_rad_s3),
            "limiting_joint": self.limiting_joint,
            "limiting_constraint": self.limiting_constraint,
            "joint_dynamics_screening_executed": True,
            "joint_dynamics_all_samples_accepted": True,
            "installed_dynamics_qualified": False,
            "controller_tracking_qualified": False,
            "collision_screening_executed": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
            "blockers": [
                "MEASURED_INSTALLED_DYNAMICS_REQUIRED",
                "INSTALLED_GEOMETRY_COLLISION_SCREENING_REQUIRED",
                "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
            ],
        }

    @property
    def schedule_sha256(self) -> str:
        return _sha256(self.unsigned_dict())

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "schedule_sha256": self.schedule_sha256}

    def to_bytes(self) -> bytes:
        return _canonical(self.to_dict())


def dynamics_profile_from_pc0_basis_v1(
    basis: PreCameraTypingQualificationBasisV1,
) -> TypingJointDynamicsProfileV1:
    if not isinstance(basis, PreCameraTypingQualificationBasisV1):
        raise TypeError("basis must be a PreCameraTypingQualificationBasisV1")
    document = basis.document["synthetic_joint_dynamics_profile"]
    identities = basis.document["fixture_identities"]
    order = tuple(document["joint_order"])
    if order != PC0_SEMANTIC_ARM_JOINT_NAMES:
        raise TypingJointScheduleV1Error("PC0 dynamics joint order is crossed")
    return TypingJointDynamicsProfileV1(
        profile_id=identities["joint_dynamics_profile_id"],
        source_kind=document["source_kind"],
        maximum_velocity_rad_s=dict(
            zip(
                ARM_JOINT_NAMES,
                document["maximum_velocity_rad_s"],
                strict=True,
            )
        ),
        maximum_acceleration_rad_s2=dict(
            zip(
                ARM_JOINT_NAMES,
                document["maximum_acceleration_rad_s2"],
                strict=True,
            )
        ),
        maximum_jerk_rad_s3=dict(
            zip(
                ARM_JOINT_NAMES,
                document["maximum_jerk_rad_s3"],
                strict=True,
            )
        ),
        maximum_time_scale_factor=document["maximum_time_scale_factor"],
        physical_tracking_qualification=document["physical_tracking_qualification"],
    )


def _inverse_quintic(position_ratio: float) -> float:
    if position_ratio <= 0.0:
        return 0.0
    if position_ratio >= 1.0:
        return 1.0
    lower = 0.0
    upper = 1.0
    for _ in range(64):
        middle = (lower + upper) / 2.0
        value = 10.0 * middle**3 - 15.0 * middle**4 + 6.0 * middle**5
        if value < position_ratio:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2.0


def _timestamps(
    plan: TypingTrajectoryPlanV1,
    scale: float,
    minimum_segment_duration_ns: int,
) -> tuple[tuple[int, ...], int]:
    samples = plan.screening_samples
    timestamps = [0]
    prior_index = 1
    elapsed_ns = 0
    for segment in plan.timing_segments:
        destination = segment.destination_endpoint_sequence
        group: list[int] = []
        while prior_index < len(samples) and samples[prior_index].endpoint_sequence == destination:
            group.append(prior_index)
            prior_index += 1
        if not group:
            raise TypingJointScheduleV1Error(
                "timing segment has no exact screening samples"
            )
        duration_ns = max(
            minimum_segment_duration_ns,
            int(math.ceil(segment.duration_ms * 1_000_000.0 * scale)),
            len(group),
        )
        segment_start_ns = elapsed_ns
        previous_timestamp = timestamps[-1]
        for ordinal, _ in enumerate(group, start=1):
            ratio = ordinal / len(group)
            candidate = segment_start_ns + int(
                round(duration_ns * _inverse_quintic(ratio))
            )
            candidate = max(previous_timestamp + 1, candidate)
            if ordinal == len(group):
                candidate = segment_start_ns + duration_ns
            if candidate <= previous_timestamp:
                raise TypingJointScheduleV1Error(
                    "bounded timing cannot remain strictly monotonic"
                )
            timestamps.append(candidate)
            previous_timestamp = candidate
        elapsed_ns = segment_start_ns + duration_ns + segment.dwell_after_ms * 1_000_000
    if prior_index != len(samples) or len(timestamps) != len(samples):
        raise TypingJointScheduleV1Error(
            "timing segments do not cover the exact screening sample sequence"
        )
    return tuple(timestamps), elapsed_ns


def _demands(
    timestamps: tuple[int, ...],
    positions: tuple[Mapping[str, float], ...],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    velocities: list[dict[str, float]] = []
    durations: list[float] = []
    for index in range(len(positions) - 1):
        duration = (timestamps[index + 1] - timestamps[index]) / 1e9
        if duration <= 0.0:
            raise TypingJointScheduleV1Error("sample timing is not monotonic")
        durations.append(duration)
        velocities.append(
            {
                name: (positions[index + 1][name] - positions[index][name])
                / duration
                for name in ARM_JOINT_NAMES
            }
        )
    accelerations: list[dict[str, float]] = []
    acceleration_intervals: list[float] = []
    for index in range(1, len(velocities)):
        interval = (durations[index - 1] + durations[index]) / 2.0
        acceleration_intervals.append(interval)
        accelerations.append(
            {
                name: (velocities[index][name] - velocities[index - 1][name])
                / interval
                for name in ARM_JOINT_NAMES
            }
        )
    jerks: list[dict[str, float]] = []
    for index in range(1, len(accelerations)):
        interval = (
            acceleration_intervals[index - 1] + acceleration_intervals[index]
        ) / 2.0
        jerks.append(
            {
                name: (accelerations[index][name] - accelerations[index - 1][name])
                / interval
                for name in ARM_JOINT_NAMES
            }
        )

    def peaks(values: list[dict[str, float]]) -> dict[str, float]:
        return {
            name: max((abs(item[name]) for item in values), default=0.0)
            for name in ARM_JOINT_NAMES
        }

    return peaks(velocities), peaks(accelerations), peaks(jerks)


def _demand_series(
    timestamps: tuple[int, ...],
    positions: tuple[Mapping[str, float], ...],
) -> tuple[
    tuple[dict[str, float], ...],
    tuple[dict[str, float], ...],
    tuple[dict[str, float], ...],
]:
    durations = [
        (timestamps[index + 1] - timestamps[index]) / 1e9
        for index in range(len(positions) - 1)
    ]
    velocities = [
        {
            name: (positions[index + 1][name] - positions[index][name])
            / durations[index]
            for name in ARM_JOINT_NAMES
        }
        for index in range(len(durations))
    ]
    zero = {name: 0.0 for name in ARM_JOINT_NAMES}
    accelerations = [dict(zero) for _ in velocities]
    acceleration_intervals = [0.0 for _ in velocities]
    for index in range(1, len(velocities)):
        interval = (durations[index - 1] + durations[index]) / 2.0
        acceleration_intervals[index] = interval
        accelerations[index] = {
            name: (velocities[index][name] - velocities[index - 1][name])
            / interval
            for name in ARM_JOINT_NAMES
        }
    jerks = [dict(zero) for _ in velocities]
    for index in range(2, len(accelerations)):
        interval = (
            acceleration_intervals[index - 1]
            + acceleration_intervals[index]
        ) / 2.0
        jerks[index] = {
            name: (accelerations[index][name] - accelerations[index - 1][name])
            / interval
            for name in ARM_JOINT_NAMES
        }
    return tuple(velocities), tuple(accelerations), tuple(jerks)


def _validate_ik_report(
    plan: TypingTrajectoryPlanV1,
    report: Mapping[str, Any],
) -> tuple[str, tuple[Mapping[str, float], ...]]:
    if not isinstance(report, Mapping):
        raise TypingJointScheduleV1Error("IK report must be an object")
    report_hash = _digest(
        report.get("typing_trajectory_ik_screen_sha256"),
        "typing_trajectory_ik_screen_sha256",
    )
    unsigned = dict(report)
    unsigned.pop("typing_trajectory_ik_screen_sha256", None)
    if _sha256(unsigned) != report_hash:
        raise TypingJointScheduleV1Error("IK report hash is invalid")
    if (
        report.get("schema") != "rocell.typing_trajectory_ik_screen.v1"
        or report.get("status") != IK_READY_STATUS
        or report.get("typing_trajectory_plan_sha256") != plan.trajectory_plan_sha256
        or report.get("typing_execution_plan_sha256") != plan.source_plan_sha256
        or report.get("trajectory_policy_sha256") != plan.policy.policy_sha256
        or report.get("sample_count") != len(plan.screening_samples)
        or report.get("evaluated_sample_count") != len(plan.screening_samples)
        or report.get("ik_screening_executed") is not True
        or report.get("ik_all_samples_accepted") is not True
        or report.get("hardware_commands_generated") != 0
        or report.get("hardware_access") is not False
        or report.get("physical_authority") is not False
    ):
        raise TypingJointScheduleV1Error(
            "IK report does not match the exact accepted zero-authority trajectory"
        )
    seed = report.get("seed")
    if not isinstance(seed, Mapping) or seed.get("source_kind") != "SYNTHETIC_OFFLINE":
        raise TypingJointScheduleV1Error(
            "PC1 requires the explicit synthetic offline IK seed"
        )
    results = report.get("joint_results")
    if not isinstance(results, list) or len(results) != len(plan.screening_samples):
        raise TypingJointScheduleV1Error("IK joint result count is crossed")
    positions: list[Mapping[str, float]] = []
    for sample, result in zip(plan.screening_samples, results, strict=True):
        if (
            not isinstance(result, Mapping)
            or result.get("waypoint_sequence") != sample.sequence
            or result.get("phase") != sample.phase.value
            or result.get("action_index") != sample.action_index
            or result.get("semantic_target") != sample.target_id
            or result.get("accepted") is not True
            or result.get("hardware_commands_generated") != 0
        ):
            raise TypingJointScheduleV1Error(
                "IK result order or semantic binding differs from the exact sample"
            )
        positions.append(
            _joint_positions(
                result.get("solution_arm_joint_positions_rad"),
                f"joint_results[{sample.sequence}]",
            )
        )
    return report_hash, tuple(positions)


def compile_typing_joint_schedule_v1(
    plan: TypingTrajectoryPlanV1,
    ik_report: Mapping[str, Any],
    profile: TypingJointDynamicsProfileV1,
) -> TypingJointScheduleV1:
    """Time-scale exact accepted IK samples against one synthetic PC1 profile."""

    if not isinstance(plan, TypingTrajectoryPlanV1):
        raise TypeError("plan must be a TypingTrajectoryPlanV1")
    if not isinstance(profile, TypingJointDynamicsProfileV1):
        raise TypeError("profile must be a TypingJointDynamicsProfileV1")
    report_hash, positions = _validate_ik_report(plan, ik_report)
    if not 2 <= len(positions) <= 4096:
        raise TypingJointScheduleV1Error("exact IK sample count is outside [2, 4096]")

    scale = 1.0
    final: tuple[
        tuple[int, ...],
        int,
        dict[str, float],
        dict[str, float],
        dict[str, float],
    ] | None = None
    for _ in range(MAXIMUM_SCALE_ITERATIONS):
        timestamps, total_ns = _timestamps(
            plan, scale, profile.minimum_segment_duration_ns
        )
        velocity, acceleration, jerk = _demands(timestamps, positions)
        required = max(
            max(
                velocity[name] / profile.maximum_velocity_rad_s[name]
                for name in ARM_JOINT_NAMES
            ),
            math.sqrt(
                max(
                    acceleration[name]
                    / profile.maximum_acceleration_rad_s2[name]
                    for name in ARM_JOINT_NAMES
                )
            ),
            max(
                jerk[name] / profile.maximum_jerk_rad_s3[name]
                for name in ARM_JOINT_NAMES
            )
            ** (1.0 / 3.0),
        )
        if required <= 1.0 + 1e-12:
            final = timestamps, total_ns, velocity, acceleration, jerk
            break
        next_scale = scale * required * (1.0 + 1e-9)
        if next_scale > profile.maximum_time_scale_factor + 1e-12:
            raise TypingJointScheduleV1Error(
                "required joint-dynamics time scaling exceeds the profile bound"
            )
        scale = next_scale
    if final is None:
        raise TypingJointScheduleV1Error(
            "joint-dynamics time scaling did not converge within the iteration bound"
        )

    timestamps, total_ns, velocity, acceleration, jerk = final
    samples = tuple(
        TimedTypingJointSampleV1(
            sequence=sample.sequence,
            endpoint_sequence=sample.endpoint_sequence,
            phase=sample.phase.value,
            action_index=sample.action_index,
            target_id=sample.target_id,
            phase_endpoint=sample.phase_endpoint,
            time_from_start_ns=timestamps[sample.sequence],
            joint_positions_rad=positions[sample.sequence],
        )
        for sample in plan.screening_samples
    )
    velocity_margin = {
        name: profile.maximum_velocity_rad_s[name] - velocity[name]
        for name in ARM_JOINT_NAMES
    }
    acceleration_margin = {
        name: profile.maximum_acceleration_rad_s2[name] - acceleration[name]
        for name in ARM_JOINT_NAMES
    }
    jerk_margin = {
        name: profile.maximum_jerk_rad_s3[name] - jerk[name]
        for name in ARM_JOINT_NAMES
    }
    if any(
        margin < -1e-12
        for margins in (velocity_margin, acceleration_margin, jerk_margin)
        for margin in margins.values()
    ):
        raise TypingJointScheduleV1Error(
            "time-scaled schedule still exceeds a joint-dynamics limit"
        )
    candidates = []
    for name in ARM_JOINT_NAMES:
        candidates.extend(
            (
                (
                    velocity[name] / profile.maximum_velocity_rad_s[name],
                    name,
                    "VELOCITY",
                ),
                (
                    acceleration[name]
                    / profile.maximum_acceleration_rad_s2[name],
                    name,
                    "ACCELERATION",
                ),
                (
                    jerk[name] / profile.maximum_jerk_rad_s3[name],
                    name,
                    "JERK",
                ),
            )
        )
    _, limiting_joint, limiting_constraint = max(candidates)
    velocity_series, acceleration_series, jerk_series = _demand_series(
        timestamps, positions
    )
    segments: list[TypingJointSegmentDynamicsV1] = []
    for index, (velocity_item, acceleration_item, jerk_item) in enumerate(
        zip(velocity_series, acceleration_series, jerk_series, strict=True)
    ):
        absolute_velocity = {
            name: abs(velocity_item[name]) for name in ARM_JOINT_NAMES
        }
        absolute_acceleration = {
            name: abs(acceleration_item[name]) for name in ARM_JOINT_NAMES
        }
        absolute_jerk = {
            name: abs(jerk_item[name]) for name in ARM_JOINT_NAMES
        }
        segment_candidates = []
        for name in ARM_JOINT_NAMES:
            segment_candidates.extend(
                (
                    (
                        absolute_velocity[name]
                        / profile.maximum_velocity_rad_s[name],
                        name,
                        "VELOCITY",
                    ),
                    (
                        absolute_acceleration[name]
                        / profile.maximum_acceleration_rad_s2[name],
                        name,
                        "ACCELERATION",
                    ),
                    (
                        absolute_jerk[name]
                        / profile.maximum_jerk_rad_s3[name],
                        name,
                        "JERK",
                    ),
                )
            )
        _, segment_joint, segment_constraint = max(segment_candidates)
        destination = samples[index + 1]
        segments.append(
            TypingJointSegmentDynamicsV1(
                sequence=index,
                source_sample_sequence=index,
                destination_sample_sequence=index + 1,
                duration_ns=timestamps[index + 1] - timestamps[index],
                destination_phase=destination.phase,
                action_index=destination.action_index,
                target_id=destination.target_id,
                velocity_rad_s=absolute_velocity,
                acceleration_rad_s2=absolute_acceleration,
                jerk_rad_s3=absolute_jerk,
                velocity_margin_rad_s={
                    name: profile.maximum_velocity_rad_s[name]
                    - absolute_velocity[name]
                    for name in ARM_JOINT_NAMES
                },
                acceleration_margin_rad_s2={
                    name: profile.maximum_acceleration_rad_s2[name]
                    - absolute_acceleration[name]
                    for name in ARM_JOINT_NAMES
                },
                jerk_margin_rad_s3={
                    name: profile.maximum_jerk_rad_s3[name]
                    - absolute_jerk[name]
                    for name in ARM_JOINT_NAMES
                },
                limiting_joint=segment_joint,
                limiting_constraint=segment_constraint,
            )
        )
    return TypingJointScheduleV1(
        source_trajectory_plan_sha256=plan.trajectory_plan_sha256,
        source_ik_screen_sha256=report_hash,
        profile=profile,
        time_scale_factor=scale,
        samples=samples,
        segments=tuple(segments),
        total_motion_and_dwell_time_ns=total_ns,
        peak_velocity_rad_s=velocity,
        peak_acceleration_rad_s2=acceleration,
        peak_jerk_rad_s3=jerk,
        minimum_velocity_margin_rad_s=velocity_margin,
        minimum_acceleration_margin_rad_s2=acceleration_margin,
        minimum_jerk_margin_rad_s3=jerk_margin,
        limiting_joint=limiting_joint,
        limiting_constraint=limiting_constraint,
    )


def parse_typing_joint_schedule_v1(
    document: Mapping[str, Any],
) -> TypingJointScheduleV1:
    """Reconstruct and verify one canonical zero-authority schedule artifact."""

    if not isinstance(document, Mapping):
        raise TypingJointScheduleV1Error("joint schedule artifact must be an object")
    artifact_hash = _digest(document.get("schedule_sha256"), "schedule_sha256")
    unsigned = dict(document)
    unsigned.pop("schedule_sha256", None)
    if _sha256(unsigned) != artifact_hash:
        raise TypingJointScheduleV1Error("joint schedule artifact hash is invalid")
    try:
        profile_document = document["profile"]
        if not isinstance(profile_document, Mapping):
            raise TypingJointScheduleV1Error("profile must be an object")
        if _sha256(profile_document) != document["profile_sha256"]:
            raise TypingJointScheduleV1Error("profile hash is invalid")
        profile = TypingJointDynamicsProfileV1(
            profile_id=profile_document["profile_id"],
            source_kind=profile_document["source_kind"],
            maximum_velocity_rad_s=profile_document["maximum_velocity_rad_s"],
            maximum_acceleration_rad_s2=profile_document[
                "maximum_acceleration_rad_s2"
            ],
            maximum_jerk_rad_s3=profile_document["maximum_jerk_rad_s3"],
            maximum_time_scale_factor=profile_document[
                "maximum_time_scale_factor"
            ],
            physical_tracking_qualification=profile_document[
                "physical_tracking_qualification"
            ],
            minimum_segment_duration_ns=profile_document[
                "minimum_segment_duration_ns"
            ],
            schema=profile_document["schema"],
        )
        samples = tuple(
            TimedTypingJointSampleV1(
                sequence=item["sequence"],
                endpoint_sequence=item["endpoint_sequence"],
                phase=item["phase"],
                action_index=item["action_index"],
                target_id=item["target_id"],
                phase_endpoint=item["phase_endpoint"],
                time_from_start_ns=item["time_from_start_ns"],
                joint_positions_rad=item["joint_positions_rad"],
            )
            for item in document["samples"]
        )
        segments = tuple(
            TypingJointSegmentDynamicsV1(
                sequence=item["sequence"],
                source_sample_sequence=item["source_sample_sequence"],
                destination_sample_sequence=item["destination_sample_sequence"],
                duration_ns=item["duration_ns"],
                destination_phase=item["destination_phase"],
                action_index=item["action_index"],
                target_id=item["target_id"],
                velocity_rad_s=item["velocity_rad_s"],
                acceleration_rad_s2=item["acceleration_rad_s2"],
                jerk_rad_s3=item["jerk_rad_s3"],
                velocity_margin_rad_s=item["velocity_margin_rad_s"],
                acceleration_margin_rad_s2=item["acceleration_margin_rad_s2"],
                jerk_margin_rad_s3=item["jerk_margin_rad_s3"],
                limiting_joint=item["limiting_joint"],
                limiting_constraint=item["limiting_constraint"],
            )
            for item in document["segments"]
        )
        schedule = TypingJointScheduleV1(
            source_trajectory_plan_sha256=document[
                "source_trajectory_plan_sha256"
            ],
            source_ik_screen_sha256=document["source_ik_screen_sha256"],
            profile=profile,
            time_scale_factor=document["time_scale_factor"],
            samples=samples,
            segments=segments,
            total_motion_and_dwell_time_ns=document[
                "total_motion_and_dwell_time_ns"
            ],
            peak_velocity_rad_s=document["peak_velocity_rad_s"],
            peak_acceleration_rad_s2=document["peak_acceleration_rad_s2"],
            peak_jerk_rad_s3=document["peak_jerk_rad_s3"],
            minimum_velocity_margin_rad_s=document[
                "minimum_velocity_margin_rad_s"
            ],
            minimum_acceleration_margin_rad_s2=document[
                "minimum_acceleration_margin_rad_s2"
            ],
            minimum_jerk_margin_rad_s3=document["minimum_jerk_margin_rad_s3"],
            limiting_joint=document["limiting_joint"],
            limiting_constraint=document["limiting_constraint"],
            schema=document["schema"],
        )
    except KeyError as exc:
        raise TypingJointScheduleV1Error(
            f"joint schedule artifact is missing {exc.args[0]}"
        ) from exc
    if schedule.to_dict() != dict(document):
        raise TypingJointScheduleV1Error(
            "joint schedule artifact contains crossed or unsupported fields"
        )
    return schedule


__all__ = [
    "PROFILE_SCHEMA",
    "READY_STATUS",
    "SCHEMA",
    "TimedTypingJointSampleV1",
    "TypingJointDynamicsProfileV1",
    "TypingJointSegmentDynamicsV1",
    "TypingJointScheduleV1",
    "TypingJointScheduleV1Error",
    "compile_typing_joint_schedule_v1",
    "dynamics_profile_from_pc0_basis_v1",
    "parse_typing_joint_schedule_v1",
]
