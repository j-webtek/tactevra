"""Jerk-bounded, zero-authority Cartesian typing trajectory preparation.

The compiler turns :class:`TypingExecutionPlanV1` semantic endpoints into two
related products:

* phase endpoints with a deterministic quintic rest-to-rest timing estimate;
* bounded Cartesian samples suitable for the existing IK/collision screen.

Timing samples are deliberately not controller commands.  This module neither
solves IK nor claims collision clearance or physical qualification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any

from rocell.models import Point3Mm, ProposalFrame
from rocell.motion.primitives import MotionPhase

from .typing_execution_plan_v1 import TypingExecutionPlanV1


SCHEMA = "rocell.typing_trajectory_plan.v1"
POLICY_SCHEMA = "rocell.typing_trajectory_policy.v1"
STATUS = "READY_FOR_DETERMINISTIC_IK_AND_COLLISION_SCREENING"
MAX_SCREENING_SAMPLES = 16_384
EVIDENCE_FLOAT_DECIMAL_PLACES = 9
_QUINTIC_PEAK_VELOCITY = 1.875
_QUINTIC_PEAK_ACCELERATION = 10.0 / math.sqrt(3.0)
_QUINTIC_PEAK_JERK = 60.0


class TypingTrajectoryPlanV1Error(ValueError):
    """Trajectory preparation failed closed."""


class TimingConstraintV1(str, Enum):
    ZERO_DISTANCE = "ZERO_DISTANCE"
    VELOCITY = "VELOCITY"
    ACCELERATION = "ACCELERATION"
    JERK = "JERK"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _point_dict(point: Point3Mm) -> dict[str, object]:
    return {"frame": point.frame, "x": point.x, "y": point.y, "z": point.z}


def _distance(left: Point3Mm, right: Point3Mm) -> float:
    if left.frame != right.frame:
        raise TypingTrajectoryPlanV1Error("trajectory points use different frames")
    return math.dist((left.x, left.y, left.z), (right.x, right.y, right.z))


def _positive(value: float, label: str, *, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypingTrajectoryPlanV1Error(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result <= maximum:
        raise TypingTrajectoryPlanV1Error(f"{label} is outside its bounded range")
    return result


def _evidence_float(value: float) -> float:
    """Remove sub-nanometre/runtime accumulation noise from plan evidence."""
    result = round(float(value), EVIDENCE_FLOAT_DECIMAL_PLACES)
    return 0.0 if result == 0.0 else result


@dataclass(frozen=True, slots=True)
class TypingTrajectoryPolicyV1:
    policy_id: str
    maximum_cartesian_step_mm: float = 5.0
    maximum_velocity_mm_s: float = 80.0
    maximum_acceleration_mm_s2: float = 160.0
    maximum_jerk_mm_s3: float = 800.0
    hover_settle_ms: int = 100
    contact_dwell_ms: int = 60
    schema: str = POLICY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != POLICY_SCHEMA:
            raise TypingTrajectoryPlanV1Error("unsupported trajectory policy schema")
        if not isinstance(self.policy_id, str) or not self.policy_id or len(self.policy_id) > 128:
            raise TypingTrajectoryPlanV1Error("policy_id must be a bounded identifier")
        for field, maximum in (
            ("maximum_cartesian_step_mm", 100.0),
            ("maximum_velocity_mm_s", 2_000.0),
            ("maximum_acceleration_mm_s2", 20_000.0),
            ("maximum_jerk_mm_s3", 200_000.0),
        ):
            object.__setattr__(self, field, _positive(getattr(self, field), field, maximum=maximum))
        for field in ("hover_settle_ms", "contact_dwell_ms"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
                raise TypingTrajectoryPlanV1Error(f"{field} must be an integer in [0, 10000]")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "maximum_cartesian_step_mm": self.maximum_cartesian_step_mm,
            "maximum_velocity_mm_s": self.maximum_velocity_mm_s,
            "maximum_acceleration_mm_s2": self.maximum_acceleration_mm_s2,
            "maximum_jerk_mm_s3": self.maximum_jerk_mm_s3,
            "hover_settle_ms": self.hover_settle_ms,
            "contact_dwell_ms": self.contact_dwell_ms,
        }

    @property
    def policy_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class TypingPhaseWaypointV1:
    sequence: int
    phase: MotionPhase
    action_index: int | None
    target_id: str | None
    point: Point3Mm

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "phase": self.phase.value,
            "action_index": self.action_index,
            "target_id": self.target_id,
            "point": _point_dict(self.point),
        }


@dataclass(frozen=True, slots=True)
class TypingScreeningSampleV1:
    sequence: int
    endpoint_sequence: int
    phase: MotionPhase
    action_index: int | None
    target_id: str | None
    point: Point3Mm
    phase_endpoint: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "endpoint_sequence": self.endpoint_sequence,
            "phase": self.phase.value,
            "action_index": self.action_index,
            "target_id": self.target_id,
            "point": _point_dict(self.point),
            "phase_endpoint": self.phase_endpoint,
        }


@dataclass(frozen=True, slots=True)
class QuinticTimingSegmentV1:
    sequence: int
    source_endpoint_sequence: int
    destination_endpoint_sequence: int
    distance_mm: float
    duration_ms: float
    dwell_after_ms: int
    limiting_constraint: TimingConstraintV1
    peak_velocity_mm_s: float
    peak_acceleration_mm_s2: float
    peak_jerk_mm_s3: float

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "source_endpoint_sequence": self.source_endpoint_sequence,
            "destination_endpoint_sequence": self.destination_endpoint_sequence,
            "distance_mm": self.distance_mm,
            "duration_ms": self.duration_ms,
            "dwell_after_ms": self.dwell_after_ms,
            "limiting_constraint": self.limiting_constraint.value,
            "peak_velocity_mm_s": self.peak_velocity_mm_s,
            "peak_acceleration_mm_s2": self.peak_acceleration_mm_s2,
            "peak_jerk_mm_s3": self.peak_jerk_mm_s3,
        }


@dataclass(frozen=True, slots=True)
class TypingTrajectoryMetricsV1:
    direct_distance_mm: float
    park_baseline_distance_mm: float
    direct_motion_time_ms: float
    direct_dwell_time_ms: int
    direct_estimated_time_ms: float
    park_baseline_estimated_time_ms: float
    estimated_time_saved_ms: float
    estimated_time_reduction_fraction: float

    def to_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class TypingTrajectoryPlanV1:
    source_plan_sha256: str
    policy: TypingTrajectoryPolicyV1
    phase_waypoints: tuple[TypingPhaseWaypointV1, ...]
    screening_samples: tuple[TypingScreeningSampleV1, ...]
    timing_segments: tuple[QuinticTimingSegmentV1, ...]
    metrics: TypingTrajectoryMetricsV1
    schema: str = SCHEMA

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_plan_sha256": self.source_plan_sha256,
            "policy": self.policy.to_dict(),
            "policy_sha256": self.policy.policy_sha256,
            "phase_waypoints": [item.to_dict() for item in self.phase_waypoints],
            "screening_samples": [item.to_dict() for item in self.screening_samples],
            "timing_segments": [item.to_dict() for item in self.timing_segments],
            "metrics": self.metrics.to_dict(),
            "status": STATUS,
            "timing_profile": "QUINTIC_REST_TO_REST_CARTESIAN_BOUND_V1",
            "ik_screening_executed": False,
            "collision_screening_executed": False,
            "continuous_collision_proven": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }

    @property
    def trajectory_plan_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "trajectory_plan_sha256": self.trajectory_plan_sha256}

    def to_bytes(self) -> bytes:
        return _canonical(self.to_dict())


def _waypoint(
    sequence: int, phase: MotionPhase, action_index: int | None,
    target_id: str | None, point: Point3Mm,
) -> TypingPhaseWaypointV1:
    if point.frame != ProposalFrame.BOARD.value:
        raise TypingTrajectoryPlanV1Error("all trajectory points must use the board frame")
    return TypingPhaseWaypointV1(sequence, phase, action_index, target_id, point)


def _direct_endpoints(plan: TypingExecutionPlanV1) -> tuple[TypingPhaseWaypointV1, ...]:
    result = [_waypoint(0, MotionPhase.PARK, None, None, plan.config.route_reference_point)]
    for action in plan.actions:
        result.extend((
            _waypoint(len(result), MotionPhase.HOVER, action.action_index, action.target_id, action.hover_point),
            _waypoint(len(result) + 1, MotionPhase.CONTACT, action.action_index, action.target_id, action.contact_point),
            _waypoint(len(result) + 2, MotionPhase.RETRACT, action.action_index, action.target_id, action.retract_point),
        ))
    result.append(_waypoint(len(result), MotionPhase.PARK, None, None, plan.config.route_reference_point))
    return tuple(result)


def _park_baseline_points(plan: TypingExecutionPlanV1) -> tuple[Point3Mm, ...]:
    reference = plan.config.route_reference_point
    points = [reference]
    for action in plan.actions:
        points.extend((action.hover_point, action.contact_point, action.retract_point, reference))
    return tuple(points)


def _dwell(waypoint: TypingPhaseWaypointV1, policy: TypingTrajectoryPolicyV1) -> int:
    if waypoint.phase is MotionPhase.HOVER:
        return policy.hover_settle_ms
    if waypoint.phase is MotionPhase.CONTACT:
        return policy.contact_dwell_ms
    return 0


def _timing(
    sequence: int, source_sequence: int, destination_sequence: int,
    distance_mm: float, dwell_after_ms: int, policy: TypingTrajectoryPolicyV1,
) -> QuinticTimingSegmentV1:
    if distance_mm == 0.0:
        return QuinticTimingSegmentV1(
            sequence, source_sequence, destination_sequence, 0.0, 0.0,
            dwell_after_ms, TimingConstraintV1.ZERO_DISTANCE, 0.0, 0.0, 0.0)
    candidates = {
        TimingConstraintV1.VELOCITY:
            _QUINTIC_PEAK_VELOCITY * distance_mm / policy.maximum_velocity_mm_s,
        TimingConstraintV1.ACCELERATION:
            math.sqrt(_QUINTIC_PEAK_ACCELERATION * distance_mm /
                      policy.maximum_acceleration_mm_s2),
        TimingConstraintV1.JERK:
            (_QUINTIC_PEAK_JERK * distance_mm /
             policy.maximum_jerk_mm_s3) ** (1.0 / 3.0),
    }
    limiting, duration_s = max(candidates.items(), key=lambda item: item[1])
    return QuinticTimingSegmentV1(
        sequence, source_sequence, destination_sequence, distance_mm,
        duration_s * 1000.0, dwell_after_ms, limiting,
        _QUINTIC_PEAK_VELOCITY * distance_mm / duration_s,
        _QUINTIC_PEAK_ACCELERATION * distance_mm / duration_s**2,
        _QUINTIC_PEAK_JERK * distance_mm / duration_s**3,
    )


def _timings_for_endpoints(
    endpoints: tuple[TypingPhaseWaypointV1, ...], policy: TypingTrajectoryPolicyV1,
) -> tuple[QuinticTimingSegmentV1, ...]:
    return tuple(
        _timing(index, source.sequence, destination.sequence,
                _distance(source.point, destination.point),
                _dwell(destination, policy), policy)
        for index, (source, destination) in enumerate(zip(endpoints, endpoints[1:]))
    )


def _time_for_points(points: tuple[Point3Mm, ...], policy: TypingTrajectoryPolicyV1) -> float:
    total = 0.0
    for index, (source, destination) in enumerate(zip(points, points[1:])):
        # Baseline sequence is reference->hover->contact->retract->reference.
        ordinal = (index + 1) % 4
        dwell = policy.hover_settle_ms if ordinal == 1 else (
            policy.contact_dwell_ms if ordinal == 2 else 0)
        total += _timing(index, index, index + 1, _distance(source, destination), dwell, policy).duration_ms
        total += dwell
    return total


def _screening_samples(
    endpoints: tuple[TypingPhaseWaypointV1, ...], maximum_step_mm: float,
) -> tuple[TypingScreeningSampleV1, ...]:
    first = endpoints[0]
    result = [TypingScreeningSampleV1(
        0, first.sequence, first.phase, first.action_index, first.target_id,
        first.point, True)]
    for source, destination in zip(endpoints, endpoints[1:]):
        distance = _distance(source.point, destination.point)
        steps = max(1, math.ceil(distance / maximum_step_mm))
        for step in range(1, steps + 1):
            ratio = step / steps
            point = Point3Mm(
                source.point.frame,
                source.point.x + (destination.point.x - source.point.x) * ratio,
                source.point.y + (destination.point.y - source.point.y) * ratio,
                source.point.z + (destination.point.z - source.point.z) * ratio,
            )
            phase = destination.phase if step == steps else (
                MotionPhase.APPROACH
                if destination.phase is MotionPhase.CONTACT
                else MotionPhase.RETRACT
                if destination.phase is MotionPhase.RETRACT
                else MotionPhase.TRANSIT)
            result.append(TypingScreeningSampleV1(
                len(result), destination.sequence, phase,
                destination.action_index, destination.target_id, point,
                step == steps))
            if len(result) > MAX_SCREENING_SAMPLES:
                raise TypingTrajectoryPlanV1Error("screening sample bound exceeded")
    return tuple(result)


def compile_typing_trajectory_plan_v1(
    plan: TypingExecutionPlanV1, *, policy: TypingTrajectoryPolicyV1,
) -> TypingTrajectoryPlanV1:
    """Compile a semantic typing plan into jerk-bounded offline trajectory data."""
    if not isinstance(plan, TypingExecutionPlanV1):
        raise TypeError("plan must be a TypingExecutionPlanV1")
    if not isinstance(policy, TypingTrajectoryPolicyV1):
        raise TypeError("policy must be a TypingTrajectoryPolicyV1")
    endpoints = _direct_endpoints(plan)
    timings = _timings_for_endpoints(endpoints, policy)
    samples = _screening_samples(endpoints, policy.maximum_cartesian_step_mm)
    motion_ms = sum(item.duration_ms for item in timings)
    dwell_ms = sum(item.dwell_after_ms for item in timings)
    direct_ms = motion_ms + dwell_ms
    park_ms = _time_for_points(_park_baseline_points(plan), policy)
    saved = max(0.0, park_ms - direct_ms)
    metrics = TypingTrajectoryMetricsV1(
        direct_distance_mm=_evidence_float(
            sum(item.distance_mm for item in timings)),
        park_baseline_distance_mm=_evidence_float(
            plan.metrics.park_total_distance_mm),
        direct_motion_time_ms=_evidence_float(motion_ms),
        direct_dwell_time_ms=dwell_ms,
        direct_estimated_time_ms=_evidence_float(direct_ms),
        park_baseline_estimated_time_ms=_evidence_float(park_ms),
        estimated_time_saved_ms=_evidence_float(saved),
        estimated_time_reduction_fraction=_evidence_float(
            saved / park_ms if park_ms else 0.0),
    )
    return TypingTrajectoryPlanV1(
        source_plan_sha256=plan.plan_sha256,
        policy=policy,
        phase_waypoints=endpoints,
        screening_samples=samples,
        timing_segments=timings,
        metrics=metrics,
    )


__all__ = [
    "SCHEMA", "POLICY_SCHEMA", "STATUS", "TimingConstraintV1",
    "TypingPhaseWaypointV1", "TypingScreeningSampleV1",
    "TypingTrajectoryMetricsV1", "TypingTrajectoryPlanV1",
    "TypingTrajectoryPlanV1Error", "TypingTrajectoryPolicyV1",
    "QuinticTimingSegmentV1", "compile_typing_trajectory_plan_v1",
]
