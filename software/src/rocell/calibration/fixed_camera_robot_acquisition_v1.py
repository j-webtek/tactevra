"""Acquire one stationary camera/robot calibration bracket.

The coordinator accepts only an already-open, persistently identified camera
and a feedback-only source.  Its callable surface has no motion, torque, or
contact operation.  One invocation performs exactly this sequence::

    T=1051 feedback -> one camera frame -> T=1051 feedback

It does not open either device, retry a failed operation, move the arm, or
write files.  The returned JPEG and hash-bound bracket can be retained by the
owning application.  A separate builder joins reviewed image observations to
the bracket and delegates final validation to the existing passive capture
compiler.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Protocol

from rocell.arm.feedback import Feedback1051, parse_feedback_line
from rocell.kinematics.firmware_reference import REFERENCE_SHA256, forward
from rocell.vision.camera import CameraStatus, FramePacket, TimestampQuality

from .fixed_camera_robot_calibration_capture_v1 import (
    CAPTURE_INPUT_SCHEMA,
    MAX_BRACKET_NS,
    MAX_ENDPOINT_SPAN_MM,
    MAX_JOINT_SPAN_RAD,
    MAX_REPORTED_FK_ERROR_MM,
    compile_capture,
)


BRACKET_SCHEMA = "rocell.fixed_camera_robot_acquisition_bracket.v1"
PERMIT_SCHEMA = "rocell.fixed_camera_robot_read_only_permit.v1"
PERMIT_STATUS = "REVIEWED_READ_ONLY_CALIBRATION_ACQUISITION"


class FixedCameraRobotAcquisitionError(RuntimeError):
    """The read-only acquisition contract or observed bracket was invalid."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraRobotAcquisitionError(
            "value is not canonical JSON") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraRobotAcquisitionError(
            f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FixedCameraRobotAcquisitionError(f"{label} must be nonempty text")
    return value.strip()


def _feedback_line(value: bytes | str) -> tuple[str, Feedback1051]:
    if isinstance(value, bytes):
        try:
            line = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FixedCameraRobotAcquisitionError(
                "feedback line must be strict UTF-8") from exc
    elif isinstance(value, str):
        line = value
    else:
        raise FixedCameraRobotAcquisitionError(
            "feedback line must be immutable bytes or text")
    if not line or len(line.encode("utf-8")) > 64 * 1024:
        raise FixedCameraRobotAcquisitionError(
            "feedback line is empty or exceeds the byte limit")
    try:
        return line, parse_feedback_line(line)
    except (TypeError, ValueError) as exc:
        raise FixedCameraRobotAcquisitionError(
            "feedback source did not return valid T=1051") from exc


def _joints(value: Feedback1051) -> tuple[float, ...]:
    result = (
        value.base_rad,
        value.shoulder_rad,
        value.elbow_rad,
        value.wrist_pitch_rad,
        value.wrist_roll_rad,
        value.gripper_rad,
    )
    if any(item is None for item in result):
        raise FixedCameraRobotAcquisitionError(
            "T=1051 feedback lacks all six joint fields")
    return tuple(float(item) for item in result)  # type: ignore[arg-type,return-value]


def _reported_xyz(value: Feedback1051) -> tuple[float, float, float]:
    result = (value.x_mm, value.y_mm, value.z_mm)
    if any(item is None for item in result):
        raise FixedCameraRobotAcquisitionError(
            "T=1051 feedback lacks reported endpoint XYZ")
    return tuple(float(item) for item in result)  # type: ignore[arg-type,return-value]


def _distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum(
        (a - b) ** 2 for a, b in zip(left, right, strict=True)))


@dataclass(frozen=True, slots=True)
class ReadOnlyCalibrationAcquisitionPermitV1:
    """Reviewed bindings for acquisition only; never motion authority."""

    permit_id: str
    installation_epoch_id: str
    camera_identity_sha256: str
    settings_sha256: str
    robot_base_identity: str
    clock_id: str
    camera_qualification_sha256: str
    feedback_qualification_sha256: str
    installation_witness_sha256: str
    review_record_sha256: str
    camera_qualified: bool
    feedback_source_qualified: bool
    installation_unchanged: bool
    arm_confirmed_stationary: bool
    status: str = PERMIT_STATUS
    schema: str = PERMIT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PERMIT_SCHEMA or self.status != PERMIT_STATUS:
            raise FixedCameraRobotAcquisitionError(
                "read-only acquisition permit is not reviewed")
        for value, label in (
            (self.permit_id, "permit_id"),
            (self.installation_epoch_id, "installation_epoch_id"),
            (self.robot_base_identity, "robot_base_identity"),
            (self.clock_id, "clock_id"),
        ):
            _text(value, label)
        _sha(self.camera_identity_sha256, "camera_identity_sha256")
        _sha(self.settings_sha256, "settings_sha256")
        for value, label in (
            (self.camera_qualification_sha256, "camera_qualification_sha256"),
            (self.feedback_qualification_sha256, "feedback_qualification_sha256"),
            (self.installation_witness_sha256, "installation_witness_sha256"),
            (self.review_record_sha256, "review_record_sha256"),
        ):
            _sha(value, label)
        gates = (
            self.camera_qualified,
            self.feedback_source_qualified,
            self.installation_unchanged,
            self.arm_confirmed_stationary,
        )
        if any(type(value) is not bool for value in gates) or not all(gates):
            raise FixedCameraRobotAcquisitionError(
                "all read-only acquisition gates must be explicitly true")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "permit_id": self.permit_id,
            "installation_epoch_id": self.installation_epoch_id,
            "camera_identity_sha256": self.camera_identity_sha256,
            "settings_sha256": self.settings_sha256,
            "robot_base_identity": self.robot_base_identity,
            "clock_id": self.clock_id,
            "camera_qualification_sha256": self.camera_qualification_sha256,
            "feedback_qualification_sha256": self.feedback_qualification_sha256,
            "installation_witness_sha256": self.installation_witness_sha256,
            "review_record_sha256": self.review_record_sha256,
            "camera_qualified": self.camera_qualified,
            "feedback_source_qualified": self.feedback_source_qualified,
            "installation_unchanged": self.installation_unchanged,
            "arm_confirmed_stationary": self.arm_confirmed_stationary,
            "allowed_operations": ["T105_FEEDBACK", "CAMERA_CAPTURE", "T105_FEEDBACK"],
            "camera_open_allowed": False,
            "automatic_retry_allowed": False,
            "movement_command_count_limit": 0,
            "torque_command_count_limit": 0,
            "contact_authorized": False,
            "motion_authorized": False,
        }

    @property
    def sha256(self) -> str:
        return _sha256_bytes(_canonical(self.to_dict()))


@dataclass(frozen=True, slots=True)
class RetainedFeedbackSampleV1:
    """One exact feedback line and its host receipt time."""

    line: bytes | str
    received_at_ns: int
    clock_id: str
    robot_base_identity: str

    def __post_init__(self) -> None:
        _feedback_line(self.line)
        if type(self.received_at_ns) is not int or self.received_at_ns < 0:
            raise FixedCameraRobotAcquisitionError(
                "feedback timestamp must be a nonnegative integer")
        _text(self.clock_id, "feedback clock_id")
        _text(self.robot_base_identity, "feedback robot_base_identity")

    @property
    def text(self) -> str:
        return _feedback_line(self.line)[0]

    @property
    def parsed(self) -> Feedback1051:
        return _feedback_line(self.line)[1]


class AlreadyOpenCalibrationCamera(Protocol):
    """Narrow read-only surface; deliberately excludes open and close."""

    def probe(self) -> CameraStatus: ...

    def capture(self) -> FramePacket: ...


class FeedbackOnlyCalibrationSource(Protocol):
    """Narrow source surface; deliberately excludes movement operations."""

    def sample_feedback(self) -> RetainedFeedbackSampleV1: ...


@dataclass(frozen=True, slots=True)
class CalibrationCaptureBracketV1:
    permit_sha256: str
    installation_epoch_id: str
    frame: FramePacket
    camera_identity_sha256: str
    pre_feedback: RetainedFeedbackSampleV1
    post_feedback: RetainedFeedbackSampleV1
    maximum_joint_span_rad: float
    endpoint_span_mm: float
    maximum_reported_fk_error_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BRACKET_SCHEMA,
            "status": "READ_ONLY_STATIONARY_BRACKET_CAPTURED",
            "permit_sha256": self.permit_sha256,
            "installation_epoch_id": self.installation_epoch_id,
            "frame": {
                "capture_id": self.frame.capture_id,
                "frame_sha256": self.frame.sha256,
                "width_px": self.frame.width_px,
                "height_px": self.frame.height_px,
                "host_request_ns": self.frame.host_request_ns,
                "host_first_byte_ns": self.frame.host_first_byte_ns,
                "host_complete_ns": self.frame.host_complete_ns,
                "clock_id": self.pre_feedback.clock_id,
                "camera_identity_sha256": self.camera_identity_sha256,
                "settings_sha256": self.frame.settings_hash,
                "timestamp_quality": self.frame.timestamp_quality.value,
            },
            "robot_feedback": {
                "robot_base_identity": self.pre_feedback.robot_base_identity,
                "clock_id": self.pre_feedback.clock_id,
                "pre_timestamp_ns": self.pre_feedback.received_at_ns,
                "post_timestamp_ns": self.post_feedback.received_at_ns,
                "pre_feedback_line": self.pre_feedback.text,
                "post_feedback_line": self.post_feedback.text,
            },
            "quality": {
                "feedback_bracket_ns": (
                    self.post_feedback.received_at_ns
                    - self.pre_feedback.received_at_ns
                ),
                "maximum_joint_span_rad": self.maximum_joint_span_rad,
                "endpoint_span_mm": self.endpoint_span_mm,
                "maximum_reported_fk_error_mm": self.maximum_reported_fk_error_mm,
            },
            "provider_calls_performed": True,
            "physical_hardware_access_claimed": False,
            "camera_opened_by_coordinator": False,
            "feedback_requests": 2,
            "camera_frames_captured": 1,
            "automatic_retries": 0,
            "controller_commands": ["T=105", "T=105"],
            "movement_commands": [],
            "motion_authorized": False,
            "contact_authorized": False,
        }

    @property
    def sha256(self) -> str:
        return _sha256_bytes(_canonical(self.to_dict()))


def validate_calibration_bracket_v1(
    bracket: CalibrationCaptureBracketV1,
) -> CalibrationCaptureBracketV1:
    """Revalidate one live or retained bracket against the shared policy."""

    if not isinstance(bracket, CalibrationCaptureBracketV1):
        raise TypeError("bracket must be CalibrationCaptureBracketV1")
    _sha(bracket.permit_sha256, "permit_sha256")
    _text(bracket.installation_epoch_id, "installation_epoch_id")
    _sha(bracket.camera_identity_sha256, "camera_identity_sha256")
    if not isinstance(bracket.frame, FramePacket):
        raise TypeError("bracket.frame must be FramePacket")
    pre, post = bracket.pre_feedback, bracket.post_feedback
    if not isinstance(pre, RetainedFeedbackSampleV1) or not isinstance(
        post, RetainedFeedbackSampleV1
    ):
        raise TypeError("bracket feedback must be RetainedFeedbackSampleV1")
    if pre.clock_id != post.clock_id or (
        pre.robot_base_identity != post.robot_base_identity
    ):
        raise FixedCameraRobotAcquisitionError(
            "feedback identity or clock changed inside the retained bracket"
        )
    if bracket.frame.timestamp_quality not in (
        TimestampQuality.HOST_RECEIPT,
        TimestampQuality.SETTLED_BRACKET,
    ):
        raise FixedCameraRobotAcquisitionError(
            "frame lacks usable host timing for a settled bracket"
        )
    if not (
        pre.received_at_ns <= bracket.frame.host_request_ns
        <= bracket.frame.host_first_byte_ns
        <= bracket.frame.host_complete_ns
        <= post.received_at_ns
    ):
        raise FixedCameraRobotAcquisitionError(
            "feedback samples do not bracket the complete frame request"
        )
    if post.received_at_ns - pre.received_at_ns > MAX_BRACKET_NS:
        raise FixedCameraRobotAcquisitionError(
            "camera/feedback bracket exceeds one second"
        )

    pre_joints, post_joints = _joints(pre.parsed), _joints(post.parsed)
    maximum_joint_span = max(
        abs(a - b) for a, b in zip(pre_joints, post_joints, strict=True)
    )
    if maximum_joint_span > MAX_JOINT_SPAN_RAD:
        raise FixedCameraRobotAcquisitionError(
            "robot joints changed during camera capture"
        )
    pre_fk = tuple(float(value) for value in forward(*pre_joints[:4])[:3])
    post_fk = tuple(float(value) for value in forward(*post_joints[:4])[:3])
    endpoint_span = _distance(pre_fk, post_fk)
    if endpoint_span > MAX_ENDPOINT_SPAN_MM:
        raise FixedCameraRobotAcquisitionError(
            "robot endpoint changed during camera capture"
        )
    maximum_reported_error = max(
        _distance(_reported_xyz(pre.parsed), pre_fk),
        _distance(_reported_xyz(post.parsed), post_fk),
    )
    if maximum_reported_error > MAX_REPORTED_FK_ERROR_MM:
        raise FixedCameraRobotAcquisitionError(
            "reported endpoint differs from pinned forward kinematics"
        )
    expected_metrics = (
        (bracket.maximum_joint_span_rad, maximum_joint_span, "joint span"),
        (bracket.endpoint_span_mm, endpoint_span, "endpoint span"),
        (
            bracket.maximum_reported_fk_error_mm,
            maximum_reported_error,
            "reported FK error",
        ),
    )
    for retained, recomputed, label in expected_metrics:
        if (
            isinstance(retained, bool)
            or not isinstance(retained, (int, float))
            or not math.isfinite(float(retained))
            or not math.isclose(
                float(retained), recomputed, rel_tol=0.0, abs_tol=1e-12
            )
        ):
            raise FixedCameraRobotAcquisitionError(
                f"retained {label} differs from recomputed evidence"
            )
    return bracket


def acquire_calibration_bracket_v1(
    camera: AlreadyOpenCalibrationCamera,
    feedback: FeedbackOnlyCalibrationSource,
    permit: ReadOnlyCalibrationAcquisitionPermitV1,
) -> CalibrationCaptureBracketV1:
    """Acquire exactly one frame bracketed by two feedback-only samples."""

    if not isinstance(permit, ReadOnlyCalibrationAcquisitionPermitV1):
        raise TypeError("permit must be ReadOnlyCalibrationAcquisitionPermitV1")
    status = camera.probe()
    if not isinstance(status, CameraStatus):
        raise FixedCameraRobotAcquisitionError(
            "camera probe did not return CameraStatus")
    observed_identity_sha = _sha256_bytes(status.identity.encode("utf-8"))
    if (
        not status.is_open
        or not status.persistent_identity
        or observed_identity_sha != permit.camera_identity_sha256
        or status.settings_hash != permit.settings_sha256
    ):
        raise FixedCameraRobotAcquisitionError(
            "open camera identity or settings differ from the reviewed permit")

    pre = feedback.sample_feedback()
    if not isinstance(pre, RetainedFeedbackSampleV1):
        raise FixedCameraRobotAcquisitionError(
            "feedback source returned an invalid pre-frame sample")
    frame = camera.capture()
    if not isinstance(frame, FramePacket):
        raise FixedCameraRobotAcquisitionError("camera did not return FramePacket")
    post = feedback.sample_feedback()
    if not isinstance(post, RetainedFeedbackSampleV1):
        raise FixedCameraRobotAcquisitionError(
            "feedback source returned an invalid post-frame sample")

    if (
        pre.clock_id != permit.clock_id
        or post.clock_id != permit.clock_id
        or pre.robot_base_identity != permit.robot_base_identity
        or post.robot_base_identity != permit.robot_base_identity
    ):
        raise FixedCameraRobotAcquisitionError(
            "feedback identity or clock differs from the reviewed permit")
    if frame.settings_hash != permit.settings_sha256:
        raise FixedCameraRobotAcquisitionError(
            "captured frame settings differ from the reviewed permit")
    if frame.timestamp_quality not in (
        TimestampQuality.HOST_RECEIPT,
        TimestampQuality.SETTLED_BRACKET,
    ):
        raise FixedCameraRobotAcquisitionError(
            "frame lacks usable host timing for a settled bracket")
    if not (
        pre.received_at_ns <= frame.host_request_ns
        <= frame.host_first_byte_ns <= frame.host_complete_ns
        <= post.received_at_ns
    ):
        raise FixedCameraRobotAcquisitionError(
            "feedback samples do not bracket the complete frame request")
    if post.received_at_ns - pre.received_at_ns > MAX_BRACKET_NS:
        raise FixedCameraRobotAcquisitionError(
            "camera/feedback bracket exceeds one second")

    pre_joints, post_joints = _joints(pre.parsed), _joints(post.parsed)
    maximum_joint_span = max(abs(a - b) for a, b in zip(
        pre_joints, post_joints, strict=True))
    if maximum_joint_span > MAX_JOINT_SPAN_RAD:
        raise FixedCameraRobotAcquisitionError(
            "robot joints changed during camera capture")
    pre_fk = tuple(float(value) for value in forward(*pre_joints[:4])[:3])
    post_fk = tuple(float(value) for value in forward(*post_joints[:4])[:3])
    endpoint_span = _distance(pre_fk, post_fk)
    if endpoint_span > MAX_ENDPOINT_SPAN_MM:
        raise FixedCameraRobotAcquisitionError(
            "robot endpoint changed during camera capture")
    maximum_reported_error = max(
        _distance(_reported_xyz(pre.parsed), pre_fk),
        _distance(_reported_xyz(post.parsed), post_fk),
    )
    if maximum_reported_error > MAX_REPORTED_FK_ERROR_MM:
        raise FixedCameraRobotAcquisitionError(
            "reported endpoint differs from pinned forward kinematics")

    bracket = CalibrationCaptureBracketV1(
        permit_sha256=permit.sha256,
        installation_epoch_id=permit.installation_epoch_id,
        frame=frame,
        camera_identity_sha256=permit.camera_identity_sha256,
        pre_feedback=pre,
        post_feedback=post,
        maximum_joint_span_rad=maximum_joint_span,
        endpoint_span_mm=endpoint_span,
        maximum_reported_fk_error_mm=maximum_reported_error,
    )
    return validate_calibration_bracket_v1(bracket)


def build_capture_input_v1(
    bracket: CalibrationCaptureBracketV1,
    *,
    role: str,
    board_pose: Mapping[str, Any],
    tool_reference: Mapping[str, Any],
) -> dict[str, Any]:
    """Join reviewed image observations and prove compiler compatibility."""

    if not isinstance(bracket, CalibrationCaptureBracketV1):
        raise TypeError("bracket must be CalibrationCaptureBracketV1")
    record = bracket.to_dict()
    frame = record["frame"]
    document = {
        "schema": CAPTURE_INPUT_SCHEMA,
        "capture_id": frame["capture_id"],
        "installation_epoch_id": bracket.installation_epoch_id,
        "profile": "no_attachment",
        "role": role,
        "frame": {
            "capture_id": frame["capture_id"],
            "frame_sha256": frame["frame_sha256"],
            "captured_at_ns": frame["host_first_byte_ns"],
            "clock_id": frame["clock_id"],
            "camera_identity_sha256": frame["camera_identity_sha256"],
            "settings_sha256": frame["settings_sha256"],
        },
        "board_pose": dict(board_pose),
        "tool_reference": dict(tool_reference),
        "robot_feedback": dict(record["robot_feedback"]),
        "kinematic_binding": {
            "model_id": "roarm_m3_firmware_reference_v1",
            "reference_sha256": REFERENCE_SHA256,
            "robot_frame": "robot_base",
            "endpoint_frame": "bare_jaw_reference",
        },
    }
    # Reuse the downstream compiler as the single source of truth for all
    # observation, timing, stationarity, and kinematic bounds.
    compile_capture(document)
    return document


__all__ = [
    "AlreadyOpenCalibrationCamera",
    "BRACKET_SCHEMA",
    "CalibrationCaptureBracketV1",
    "FeedbackOnlyCalibrationSource",
    "FixedCameraRobotAcquisitionError",
    "PERMIT_SCHEMA",
    "PERMIT_STATUS",
    "ReadOnlyCalibrationAcquisitionPermitV1",
    "RetainedFeedbackSampleV1",
    "acquire_calibration_bracket_v1",
    "build_capture_input_v1",
    "validate_calibration_bracket_v1",
]
