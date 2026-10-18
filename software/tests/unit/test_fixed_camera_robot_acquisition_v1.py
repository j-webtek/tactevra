from __future__ import annotations

from io import BytesIO
import hashlib
import json

from PIL import Image
import pytest

from rocell.calibration.fixed_camera_robot_acquisition_v1 import (
    FixedCameraRobotAcquisitionError,
    ReadOnlyCalibrationAcquisitionPermitV1,
    RetainedFeedbackSampleV1,
    acquire_calibration_bracket_v1,
    build_capture_input_v1,
)
from rocell.kinematics.firmware_reference import forward
from rocell.vision.camera import CameraStatus, FramePacket, TimestampQuality


IDENTITY = "windows-device-instance:USB\\VID_04B4&PID_0477\\fixture"
IDENTITY_SHA = hashlib.sha256(IDENTITY.encode()).hexdigest()
SETTINGS_SHA = "2" * 64


def jpeg() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (4, 3), (20, 40, 60)).save(stream, format="JPEG")
    return stream.getvalue()


def feedback_line(*, base: float = 0.0) -> str:
    xyz = forward(base, 0.0, 0.0, 0.0)[:3]
    return json.dumps({
        "T": 1051,
        "x": xyz[0],
        "y": xyz[1],
        "z": xyz[2],
        "tit": 0.0,
        "b": base,
        "s": 0.0,
        "e": 0.0,
        "t": 0.0,
        "r": 0.0,
        "g": 0.0,
    }, separators=(",", ":")) + "\n"


def permit(**changes: object) -> ReadOnlyCalibrationAcquisitionPermitV1:
    values = {
        "permit_id": "calibration-bracket-001",
        "installation_epoch_id": "rc03-installed-camera-2026-10-17",
        "camera_identity_sha256": IDENTITY_SHA,
        "settings_sha256": SETTINGS_SHA,
        "robot_base_identity": "roarm-m3-base-fixture",
        "clock_id": "host-monotonic-ns",
        "camera_qualification_sha256": "a" * 64,
        "feedback_qualification_sha256": "b" * 64,
        "installation_witness_sha256": "c" * 64,
        "review_record_sha256": "d" * 64,
        "camera_qualified": True,
        "feedback_source_qualified": True,
        "installation_unchanged": True,
        "arm_confirmed_stationary": True,
    }
    values.update(changes)
    return ReadOnlyCalibrationAcquisitionPermitV1(**values)  # type: ignore[arg-type]


def sample(timestamp: int, *, base: float = 0.0) -> RetainedFeedbackSampleV1:
    return RetainedFeedbackSampleV1(
        feedback_line(base=base), timestamp, "host-monotonic-ns",
        "roarm-m3-base-fixture",
    )


def packet(*, settings_sha: str = SETTINGS_SHA) -> FramePacket:
    return FramePacket(
        capture_id="capture-fit-a",
        jpeg_bytes=jpeg(),
        width_px=4,
        height_px=3,
        source_sequence=None,
        source_timestamp_ns=None,
        source_clock=None,
        host_request_ns=120,
        host_first_byte_ns=140,
        host_complete_ns=160,
        settings_hash=settings_sha,
        timestamp_quality=TimestampQuality.HOST_RECEIPT,
    )


class Camera:
    def __init__(self, events: list[str], *, frame: FramePacket | None = None) -> None:
        self.events = events
        self.frame = packet() if frame is None else frame
        self.captures = 0

    def probe(self) -> CameraStatus:
        self.events.append("probe")
        return CameraStatus(
            backend="fixture",
            identity=IDENTITY,
            is_open=True,
            width_px=4,
            height_px=3,
            fps=8.0,
            settings_hash=SETTINGS_SHA,
            timestamp_quality=TimestampQuality.HOST_RECEIPT,
            persistent_identity=True,
        )

    def capture(self) -> FramePacket:
        self.events.append("frame")
        self.captures += 1
        return self.frame


class Feedback:
    def __init__(self, events: list[str], samples: list[RetainedFeedbackSampleV1]) -> None:
        self.events = events
        self.samples = list(samples)
        self.calls = 0

    def sample_feedback(self) -> RetainedFeedbackSampleV1:
        self.events.append("feedback")
        self.calls += 1
        return self.samples.pop(0)


class FailingCamera(Camera):
    def capture(self) -> FramePacket:
        self.events.append("frame")
        self.captures += 1
        raise RuntimeError("fixture capture failed")


def acquire(
    *, post_base: float = 0.0, frame: FramePacket | None = None,
) -> tuple[object, Camera, Feedback, list[str]]:
    events: list[str] = []
    camera = Camera(events, frame=frame)
    feedback = Feedback(events, [sample(100), sample(180, base=post_base)])
    result = acquire_calibration_bracket_v1(camera, feedback, permit())
    return result, camera, feedback, events


def test_acquires_exact_feedback_frame_feedback_sequence_without_motion_surface() -> None:
    bracket, camera, feedback, events = acquire()

    assert events == ["probe", "feedback", "frame", "feedback"]
    assert camera.captures == 1
    assert feedback.calls == 2
    document = bracket.to_dict()  # type: ignore[union-attr]
    assert document["feedback_requests"] == 2
    assert document["camera_frames_captured"] == 1
    assert document["automatic_retries"] == 0
    assert document["movement_commands"] == []
    assert document["motion_authorized"] is False
    assert document["frame"]["frame_sha256"] == hashlib.sha256(jpeg()).hexdigest()


def test_builds_existing_passive_capture_input_after_image_observations() -> None:
    bracket, _, _, _ = acquire()
    frame_sha = bracket.frame.sha256  # type: ignore[union-attr]
    board_pose = {
        "observation_sha256": "3" * 64,
        "frame_sha256": frame_sha,
        "camera_intrinsics_sha256": "4" * 64,
        "tag_map_sha256": "5" * 64,
        "pose_fit_tag_ids": [0, 1, 2, 3],
        "held_out_tag_ids": [4, 5],
        "reprojection_rms_px": 0.5,
        "held_out_max_residual_px": 0.75,
    }
    tool_reference = {
        "method": "CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE",
        "observation_sha256": "6" * 64,
        "frame_sha256": frame_sha,
        "detector_id": "fixture-bare-jaw-detector",
        "detector_version": "1",
        "configuration_sha256": "7" * 64,
        "implementation_sha256": "8" * 64,
        "board_xyz_mm": [200.0, 150.0, 50.0],
        "uncertainty_mm": 1.0,
    }

    document = build_capture_input_v1(
        bracket, role="FIT", board_pose=board_pose,
        tool_reference=tool_reference,
    )

    assert document["profile"] == "no_attachment"
    assert document["frame"]["captured_at_ns"] == 140
    assert document["robot_feedback"]["pre_timestamp_ns"] == 100
    assert document["robot_feedback"]["post_timestamp_ns"] == 180


def test_rejects_unqualified_permit_before_any_device_operation() -> None:
    with pytest.raises(
        FixedCameraRobotAcquisitionError,
        match="all read-only acquisition gates",
    ):
        permit(camera_qualified=False)


def test_rejects_camera_identity_before_feedback_or_capture() -> None:
    events: list[str] = []
    camera = Camera(events)
    feedback = Feedback(events, [sample(100), sample(180)])

    with pytest.raises(
        FixedCameraRobotAcquisitionError,
        match="identity or settings",
    ):
        acquire_calibration_bracket_v1(
            camera,
            feedback,
            permit(camera_identity_sha256="9" * 64),
        )

    assert events == ["probe"]
    assert camera.captures == 0
    assert feedback.calls == 0


def test_rejects_frame_outside_feedback_bracket_without_retry() -> None:
    out_of_bracket = packet()
    object.__setattr__(out_of_bracket, "host_complete_ns", 200)
    events: list[str] = []
    camera = Camera(events, frame=out_of_bracket)
    feedback = Feedback(events, [sample(100), sample(180)])

    with pytest.raises(
        FixedCameraRobotAcquisitionError,
        match="do not bracket",
    ):
        acquire_calibration_bracket_v1(camera, feedback, permit())

    assert events == ["probe", "feedback", "frame", "feedback"]
    assert camera.captures == 1
    assert feedback.calls == 2


def test_camera_failure_is_not_retried_or_followed_by_another_feedback_request() -> None:
    events: list[str] = []
    camera = FailingCamera(events)
    feedback = Feedback(events, [sample(100), sample(180)])

    with pytest.raises(RuntimeError, match="fixture capture failed"):
        acquire_calibration_bracket_v1(camera, feedback, permit())

    assert events == ["probe", "feedback", "frame"]
    assert camera.captures == 1
    assert feedback.calls == 1


def test_rejects_joint_change_during_capture() -> None:
    with pytest.raises(
        FixedCameraRobotAcquisitionError,
        match="joints changed",
    ):
        acquire(post_base=0.02)


def test_rejects_observation_bound_to_another_frame() -> None:
    bracket, _, _, _ = acquire()
    board_pose = {
        "observation_sha256": "3" * 64,
        "frame_sha256": "a" * 64,
        "camera_intrinsics_sha256": "4" * 64,
        "tag_map_sha256": "5" * 64,
        "pose_fit_tag_ids": [0, 1, 2, 3],
        "held_out_tag_ids": [4, 5],
        "reprojection_rms_px": 0.5,
        "held_out_max_residual_px": 0.75,
    }
    tool_reference = {
        "method": "CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE",
        "observation_sha256": "6" * 64,
        "frame_sha256": bracket.frame.sha256,  # type: ignore[union-attr]
        "detector_id": "fixture",
        "detector_version": "1",
        "configuration_sha256": "7" * 64,
        "implementation_sha256": "8" * 64,
        "board_xyz_mm": [200.0, 150.0, 50.0],
        "uncertainty_mm": 1.0,
    }

    with pytest.raises(ValueError, match="different frame"):
        build_capture_input_v1(
            bracket, role="FIT", board_pose=board_pose,
            tool_reference=tool_reference,
        )
