from __future__ import annotations

import hashlib

import pytest

from rocell.calibration.fixed_camera_calibration_observation_v1 import (
    FixedCameraCalibrationObservationError,
    ReviewedNativeIntrinsicsV1,
    compile_fixed_camera_calibration_observation_v1,
)
from rocell.calibration.fixed_camera_robot_acquisition_v1 import (
    CalibrationCaptureBracketV1,
)
from rocell.vision.camera import FramePacket, TimestampQuality
from rocell.vision.detections import (
    AprilTagDetection,
    AprilTagDetectionBatch,
    FrameCaptureBinding,
    PixelCorner,
)
from rocell.vision.planar_pose_estimator import PinholeIntrinsics

from test_fixed_camera_board_pose_extractor_v1 import (
    CAMERA_FRAME,
    HEIGHT,
    WIDTH,
    _batch,
    _tag_map,
)
from test_fixed_camera_robot_acquisition_v1 import IDENTITY_SHA, SETTINGS_SHA, sample


NATIVE_WIDTH = 5472
NATIVE_HEIGHT = 3648


def minimal_jpeg(width: int, height: int) -> bytes:
    sof_payload = (
        b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    return (
        b"\xff\xd8\xff\xc0"
        + (len(sof_payload) + 2).to_bytes(2, "big")
        + sof_payload
        + b"\xff\xd9"
    )


def frame(width: int = NATIVE_WIDTH, height: int = NATIVE_HEIGHT) -> FramePacket:
    return FramePacket(
        capture_id="native-fit-a",
        jpeg_bytes=minimal_jpeg(width, height),
        width_px=width,
        height_px=height,
        source_sequence=8,
        source_timestamp_ns=140,
        source_clock="b0477-device",
        host_request_ns=120,
        host_first_byte_ns=140,
        host_complete_ns=160,
        settings_hash=SETTINGS_SHA,
        timestamp_quality=TimestampQuality.HOST_RECEIPT,
        freshness_token="sequence:8",
    )


def bracket(packet: FramePacket | None = None) -> CalibrationCaptureBracketV1:
    selected = packet or frame()
    return CalibrationCaptureBracketV1(
        permit_sha256="1" * 64,
        installation_epoch_id="rc03-static-camera-epoch-1",
        frame=selected,
        camera_identity_sha256=IDENTITY_SHA,
        pre_feedback=sample(100),
        post_feedback=sample(180),
        maximum_joint_span_rad=0.0,
        endpoint_span_mm=0.0,
        maximum_reported_fk_error_mm=0.0,
    )


def intrinsics() -> PinholeIntrinsics:
    scale_x = NATIVE_WIDTH / WIDTH
    scale_y = NATIVE_HEIGHT / HEIGHT
    return PinholeIntrinsics(
        calibration_id="b0477-native-reviewed",
        width_px=NATIVE_WIDTH,
        height_px=NATIVE_HEIGHT,
        fx_px=1000.0 * scale_x,
        fy_px=1000.0 * scale_y,
        cx_px=800.0 * scale_x,
        cy_px=600.0 * scale_y,
        source_sha256="2" * 64,
        camera_frame=CAMERA_FRAME,
    )


def review(**changes: object) -> ReviewedNativeIntrinsicsV1:
    values = {
        "calibration_record_id": "b0477-native-physical-intrinsics-1",
        "camera_identity_sha256": IDENTITY_SHA,
        "settings_sha256": SETTINGS_SHA,
        "intrinsics": intrinsics(),
        "tag_map_sha256": _tag_map().content_hash,
        "distortion_model": "OPENCV_RATIONAL_POLYNOMIAL_8",
        "rectification_configuration_sha256": "3" * 64,
        "review_record_sha256": "4" * 64,
        "physical_calibration_valid": True,
        "native_mode_verified": True,
        "full_frame_without_crop_or_rescale": True,
    }
    values.update(changes)
    return ReviewedNativeIntrinsicsV1(**values)  # type: ignore[arg-type]


def scaled_batch(packet: FramePacket) -> AprilTagDetectionBatch:
    original = _batch(frame=packet)
    scale_x = NATIVE_WIDTH / WIDTH
    scale_y = NATIVE_HEIGHT / HEIGHT
    detections = tuple(
        AprilTagDetection(
            detection.tag,
            tuple(
                PixelCorner(corner.x_px * scale_x, corner.y_px * scale_y)
                for corner in detection.corners_px
            ),  # type: ignore[arg-type]
            detection.decision_margin,
            detection.hamming,
        )
        for detection in original.detections
    )
    return AprilTagDetectionBatch(
        FrameCaptureBinding.from_frame_packet(packet, host_clock="test.monotonic"),
        original.detector,
        detections,
    )


class Detector:
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, packet: FramePacket) -> AprilTagDetectionBatch:
        self.calls += 1
        return scaled_batch(packet)


class Rectifier:
    configuration_sha256 = "3" * 64

    def rectify_detection_batch(
        self, batch: AprilTagDetectionBatch
    ) -> AprilTagDetectionBatch:
        return batch


class JawObserver:
    def __init__(self, *, wrong_frame: bool = False) -> None:
        self.wrong_frame = wrong_frame
        self.calls = 0

    def observe(self, packet: object, board_pose: object) -> dict[str, object]:
        self.calls += 1
        frame_sha = getattr(packet, "sha256")
        if self.wrong_frame:
            frame_sha = "f" * 64
        body = {
            "method": "CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE",
            "frame_sha256": frame_sha,
            "detector_id": "bare-jaw-reference-detector",
            "detector_version": "1.0.0",
            "configuration_sha256": "5" * 64,
            "implementation_sha256": "6" * 64,
            "board_xyz_mm": [200.0, 150.0, 50.0],
            "uncertainty_mm": 1.0,
        }
        body["observation_sha256"] = hashlib.sha256(
            repr(sorted(body.items())).encode()
        ).hexdigest()
        return body


def test_compiles_exact_native_frame_through_existing_passive_boundary() -> None:
    detector = Detector()
    jaw = JawObserver()
    result = compile_fixed_camera_calibration_observation_v1(
        bracket(), review(), detector, Rectifier(), _tag_map(), jaw, role="FIT"
    )

    assert detector.calls == jaw.calls == 1
    assert result.capture_input["frame"]["frame_sha256"] == frame().sha256
    assert result.compiled_capture["status"] == "PASSIVE_CORRESPONDENCE_CAPTURED"
    assert result.compiled_capture["bindings"]["camera_intrinsics_sha256"] == (
        intrinsics().content_hash
    )
    assert result.to_dict()["authority"]["controller_commands"] == []


def test_rejects_non_native_frame_before_any_detector_call() -> None:
    detector = Detector()
    jaw = JawObserver()
    small = frame(1600, 1200)

    with pytest.raises(FixedCameraCalibrationObservationError, match="complete native"):
        compile_fixed_camera_calibration_observation_v1(
            bracket(small), review(), detector, Rectifier(), _tag_map(), jaw, role="FIT"
        )

    assert detector.calls == jaw.calls == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("camera_identity_sha256", "a" * 64, "camera identity"),
        ("settings_sha256", "b" * 64, "settings"),
        ("tag_map_sha256", "c" * 64, "six-tag map"),
    ),
)
def test_rejects_crossed_review_bindings(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(FixedCameraCalibrationObservationError, match=message):
        compile_fixed_camera_calibration_observation_v1(
            bracket(),
            review(**{field: value}),
            Detector(),
            Rectifier(),
            _tag_map(),
            JawObserver(),
            role="FIT",
        )


def test_review_requires_physical_intrinsics_and_full_native_frame() -> None:
    for field in (
        "physical_calibration_valid",
        "native_mode_verified",
        "full_frame_without_crop_or_rescale",
    ):
        with pytest.raises(
            FixedCameraCalibrationObservationError, match="must be true"
        ):
            review(**{field: False})


def test_rejects_bare_jaw_observation_from_another_frame() -> None:
    with pytest.raises(ValueError, match="different frame"):
        compile_fixed_camera_calibration_observation_v1(
            bracket(),
            review(),
            Detector(),
            Rectifier(),
            _tag_map(),
            JawObserver(wrong_frame=True),
            role="FIT",
        )


def test_rejects_rectifier_not_bound_to_review() -> None:
    rectifier = Rectifier()
    rectifier.configuration_sha256 = "9" * 64
    with pytest.raises(FixedCameraCalibrationObservationError, match="rectifier"):
        compile_fixed_camera_calibration_observation_v1(
            bracket(),
            review(),
            Detector(),
            rectifier,
            _tag_map(),
            JawObserver(),
            role="FIT",
        )
