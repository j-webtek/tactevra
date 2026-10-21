"""Strict calibration boundary for installed T=1051 position vectors.

The installed controller reports seven servo positions rather than the six
joint fields used by the stock Waveshare feedback profile.  This module keeps
the observed servo order separate from canonical joints and converts counts
only when a reviewed, controller-bound calibration artifact is supplied.

It performs no device I/O and never grants motion or physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping

from .feedback_profile import Feedback1051Profile, classify_feedback_1051_profile


SCHEMA = "rocell.position_vector_calibration.v1"
PROFILE = Feedback1051Profile.POSITION_VECTOR_NAMED_POSE.value
SERVO_ORDER = (11, 12, 13, 14, 15, 16, 17)
JOINT_ORDER = (
    "base",
    "shoulder",
    "elbow",
    "wrist_pitch",
    "wrist_roll",
    "gripper",
)
PRIMARY_INDEX = {
    "base": 0,
    "shoulder": 1,
    "elbow": 3,
    "wrist_pitch": 4,
    "wrist_roll": 5,
    "gripper": 6,
}

_TOP_FIELDS = frozenset(
    {
        "schema",
        "calibration_id",
        "response_profile",
        "controller_binding",
        "position_order_servo_ids",
        "joint_order",
        "joints",
        "shoulder_pair",
        "evidence",
    }
)
_CONTROLLER_FIELDS = frozenset({"vid", "pid", "unit_serial", "firmware_sha256"})
_JOINT_FIELDS = frozenset(
    {
        "joint",
        "primary_index",
        "count_zero",
        "radians_per_count",
        "minimum_rad",
        "maximum_rad",
        "training_sample_count",
        "held_out_sample_count",
        "held_out_max_abs_error_rad",
        "accepted_max_abs_error_rad",
    }
)
_SHOULDER_FIELDS = frozenset(
    {
        "driving_index",
        "driven_index",
        "nominal_sum_counts",
        "runtime_tolerance_counts",
        "training_max_abs_residual_counts",
        "held_out_max_abs_residual_counts",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {"dataset_sha256", "fit_report_sha256", "independent_review_sha256"}
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HEX4 = re.compile(r"^[0-9a-f]{4}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class PositionVectorCalibrationError(ValueError):
    """The calibration or observation cannot support a calibrated conversion."""


@dataclass(frozen=True)
class JointCountCalibration:
    joint: str
    primary_index: int
    count_zero: float
    radians_per_count: float
    minimum_rad: float
    maximum_rad: float
    training_sample_count: int
    held_out_sample_count: int
    held_out_max_abs_error_rad: float
    accepted_max_abs_error_rad: float

    def convert(self, count: int) -> float:
        value = (count - self.count_zero) * self.radians_per_count
        if not self.minimum_rad <= value <= self.maximum_rad:
            raise PositionVectorCalibrationError(
                f"{self.joint} calibrated value is outside its validated range"
            )
        return value


@dataclass(frozen=True)
class PositionVectorCalibration:
    calibration_id: str
    controller_binding: tuple[tuple[str, str], ...]
    joints: tuple[JointCountCalibration, ...]
    shoulder_nominal_sum_counts: int
    shoulder_runtime_tolerance_counts: int
    evidence: tuple[tuple[str, str], ...]


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PositionVectorCalibrationError(f"{label} must be an object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise PositionVectorCalibrationError(f"{label} fields do not match the contract")


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PositionVectorCalibrationError(f"{label} is outside its integer bound")
    return value


def _number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise PositionVectorCalibrationError(f"{label} is outside its numeric bound")
    return float(value)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise PositionVectorCalibrationError(f"{label} is not a bounded identifier")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise PositionVectorCalibrationError(f"{label} is not a lowercase SHA-256")
    return value


def _controller_binding(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    binding = _mapping(value, label)
    _exact_fields(binding, _CONTROLLER_FIELDS, label)
    vid = binding.get("vid")
    pid = binding.get("pid")
    if not isinstance(vid, str) or _HEX4.fullmatch(vid) is None:
        raise PositionVectorCalibrationError(f"{label}.vid must be four lowercase hex digits")
    if not isinstance(pid, str) or _HEX4.fullmatch(pid) is None:
        raise PositionVectorCalibrationError(f"{label}.pid must be four lowercase hex digits")
    unit_serial = _identifier(binding.get("unit_serial"), f"{label}.unit_serial")
    firmware = _digest(binding.get("firmware_sha256"), f"{label}.firmware_sha256")
    return tuple(sorted({"vid": vid, "pid": pid, "unit_serial": unit_serial,
                         "firmware_sha256": firmware}.items()))


def load_position_vector_calibration(document: Mapping[str, Any]) -> PositionVectorCalibration:
    """Validate an independently reviewed count-to-joint calibration artifact."""

    body = _mapping(document, "calibration")
    _exact_fields(body, _TOP_FIELDS, "calibration")
    if body.get("schema") != SCHEMA or body.get("response_profile") != PROFILE:
        raise PositionVectorCalibrationError("calibration schema or response profile mismatch")
    calibration_id = _identifier(body.get("calibration_id"), "calibration_id")
    controller = _controller_binding(body.get("controller_binding"), "controller_binding")
    if body.get("position_order_servo_ids") != list(SERVO_ORDER):
        raise PositionVectorCalibrationError("position vector is not bound to servo IDs 11 through 17")
    if body.get("joint_order") != list(JOINT_ORDER):
        raise PositionVectorCalibrationError("canonical joint order mismatch")

    raw_joints = body.get("joints")
    if not isinstance(raw_joints, list) or len(raw_joints) != len(JOINT_ORDER):
        raise PositionVectorCalibrationError("exactly six joint calibrations are required")
    joints: list[JointCountCalibration] = []
    for index, expected_joint in enumerate(JOINT_ORDER):
        raw = _mapping(raw_joints[index], f"joints[{index}]")
        _exact_fields(raw, _JOINT_FIELDS, f"joints[{index}]")
        if raw.get("joint") != expected_joint:
            raise PositionVectorCalibrationError("joint calibration order mismatch")
        primary = _integer(raw.get("primary_index"), "primary_index", 0, 6)
        if primary != PRIMARY_INDEX[expected_joint]:
            raise PositionVectorCalibrationError(f"{expected_joint} primary index mismatch")
        count_zero = _number(raw.get("count_zero"), "count_zero", 0.0, 4095.0)
        scale = _number(raw.get("radians_per_count"), "radians_per_count", -0.1, 0.1)
        if scale == 0.0:
            raise PositionVectorCalibrationError("radians_per_count cannot be zero")
        minimum = _number(raw.get("minimum_rad"), "minimum_rad", -2 * math.pi, 2 * math.pi)
        maximum = _number(raw.get("maximum_rad"), "maximum_rad", -2 * math.pi, 2 * math.pi)
        if minimum >= maximum:
            raise PositionVectorCalibrationError("validated joint range is empty")
        training = _integer(raw.get("training_sample_count"), "training_sample_count", 2, 1_000_000)
        held_out = _integer(raw.get("held_out_sample_count"), "held_out_sample_count", 1, 1_000_000)
        observed_error = _number(
            raw.get("held_out_max_abs_error_rad"), "held_out_max_abs_error_rad", 0.0, math.pi
        )
        accepted_error = _number(
            raw.get("accepted_max_abs_error_rad"), "accepted_max_abs_error_rad", 0.0, math.pi
        )
        if observed_error > accepted_error:
            raise PositionVectorCalibrationError("held-out joint error exceeds its accepted limit")
        joints.append(
            JointCountCalibration(
                expected_joint, primary, count_zero, scale, minimum, maximum,
                training, held_out, observed_error, accepted_error,
            )
        )

    shoulder = _mapping(body.get("shoulder_pair"), "shoulder_pair")
    _exact_fields(shoulder, _SHOULDER_FIELDS, "shoulder_pair")
    if shoulder.get("driving_index") != 1 or shoulder.get("driven_index") != 2:
        raise PositionVectorCalibrationError("mirrored shoulder indices must be 1 and 2")
    nominal_sum = _integer(shoulder.get("nominal_sum_counts"), "nominal_sum_counts", 0, 8190)
    tolerance = _integer(
        shoulder.get("runtime_tolerance_counts"), "runtime_tolerance_counts", 0, 256
    )
    training_residual = _integer(
        shoulder.get("training_max_abs_residual_counts"),
        "training_max_abs_residual_counts", 0, 8190,
    )
    held_out_residual = _integer(
        shoulder.get("held_out_max_abs_residual_counts"),
        "held_out_max_abs_residual_counts", 0, 8190,
    )
    if max(training_residual, held_out_residual) > tolerance:
        raise PositionVectorCalibrationError("shoulder-pair residual exceeds runtime tolerance")

    raw_evidence = _mapping(body.get("evidence"), "evidence")
    _exact_fields(raw_evidence, _EVIDENCE_FIELDS, "evidence")
    evidence = tuple(
        (name, _digest(raw_evidence.get(name), f"evidence.{name}"))
        for name in sorted(_EVIDENCE_FIELDS)
    )
    if len({value for _, value in evidence}) != len(evidence):
        raise PositionVectorCalibrationError("calibration evidence hashes must be distinct")
    return PositionVectorCalibration(
        calibration_id, controller, tuple(joints), nominal_sum, tolerance, evidence
    )


def describe_uncalibrated_position_vector(message: Mapping[str, Any]) -> dict[str, Any]:
    """Retain known slot semantics without claiming calibrated joint state."""

    if classify_feedback_1051_profile(message) is not Feedback1051Profile.POSITION_VECTOR_NAMED_POSE:
        raise PositionVectorCalibrationError("exact installed position-vector feedback required")
    positions = list(message["p"])
    return {
        "schema": "rocell.position_vector_calibration_readiness.v1",
        "status": "CALIBRATION_REQUIRED",
        "response_profile": PROFILE,
        "source_pose": message["pose"],
        "raw_position_counts": positions,
        "position_order_servo_ids": list(SERVO_ORDER),
        "known_slot_semantics": [
            {"index": index, "servo_id": servo_id} for index, servo_id in enumerate(SERVO_ORDER)
        ],
        "required_evidence": [
            "controller-bound firmware identity",
            "multi-pose per-joint training observations",
            "held-out count-to-joint residuals",
            "mirrored-shoulder residual bounds",
            "independent review",
        ],
        "accepted_as_calibrated_joint_state": False,
        "motion_authorized": False,
        "physical_authority": False,
    }


def convert_position_vector_feedback(
    message: Mapping[str, Any],
    calibration_document: Mapping[str, Any],
    controller_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert a response only through an exact, reviewed calibration artifact."""

    if classify_feedback_1051_profile(message) is not Feedback1051Profile.POSITION_VECTOR_NAMED_POSE:
        raise PositionVectorCalibrationError("exact installed position-vector feedback required")
    calibration = load_position_vector_calibration(calibration_document)
    observed_controller = _controller_binding(controller_binding, "observed_controller")
    if observed_controller != calibration.controller_binding:
        raise PositionVectorCalibrationError("controller binding does not match calibration")
    positions = message["p"]
    shoulder_residual = abs(
        positions[1] + positions[2] - calibration.shoulder_nominal_sum_counts
    )
    if shoulder_residual > calibration.shoulder_runtime_tolerance_counts:
        raise PositionVectorCalibrationError("runtime mirrored-shoulder residual exceeds calibration")
    converted = {
        joint.joint: joint.convert(positions[joint.primary_index]) for joint in calibration.joints
    }
    return {
        "schema": "rocell.calibrated_position_vector_feedback.v1",
        "calibration_id": calibration.calibration_id,
        "response_profile": PROFILE,
        "source_pose": message["pose"],
        "motion_active": message["motion_active"],
        "trajectory_progress_permille": message["trajectory_progress_permille"],
        "raw_position_counts": list(positions),
        "position_order_servo_ids": list(SERVO_ORDER),
        "canonical_joint_order": list(JOINT_ORDER),
        "canonical_joints_rad": converted,
        "shoulder_pair_residual_counts": shoulder_residual,
        "calibration_evidence": dict(calibration.evidence),
        "accepted_as_calibrated_joint_state": True,
        "motion_authorized": False,
        "physical_authority": False,
    }


__all__ = [
    "JOINT_ORDER",
    "PRIMARY_INDEX",
    "PROFILE",
    "SCHEMA",
    "SERVO_ORDER",
    "JointCountCalibration",
    "PositionVectorCalibration",
    "PositionVectorCalibrationError",
    "convert_position_vector_feedback",
    "describe_uncalibrated_position_vector",
    "load_position_vector_calibration",
]
