from __future__ import annotations

from dataclasses import replace

import pytest

from rocell.geometry import Point3Mm, RigidTransform, Rotation3, Vec3
from rocell.vision.camera import FramePacket, TimestampQuality
from rocell.vision.detections import (
    AprilTagDetection,
    AprilTagDetectionBatch,
    DetectorIdentity,
    FrameCaptureBinding,
    PixelCorner,
    TagReference,
)
from rocell.vision.fixed_camera_board_pose_extractor_v1 import (
    FixedCameraBoardPoseError,
    estimate_fixed_camera_board_pose,
    extract_fixed_camera_board_pose,
)
from rocell.vision.planar_pose_estimator import (
    PinholeIntrinsics,
    PlanarBoardTag,
    PlanarBoardTagMap,
    PlanarPoseEstimationError,
    PlanarPoseEstimatorConfig,
)


WIDTH = 1600
HEIGHT = 1200
BOARD_FRAME = "RC03_board"
CAMERA_FRAME = "fixed_camera_optical"
GROUND_TRUTH = RigidTransform(
    CAMERA_FRAME,
    BOARD_FRAME,
    Rotation3((1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, -1.0)),
    Vec3(-305.0, 228.5, 700.0),
)
CENTRES_MM = {
    0: (47.0, 40.0),
    1: (440.0, 40.0),
    2: (47.0, 410.0),
    3: (563.0, 410.0),
    4: (324.0, 309.0),
    5: (459.0, 309.0),
}


def _minimal_jpeg(width: int = WIDTH, height: int = HEIGHT) -> bytes:
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


def _frame(*, capture_id: str = "fixed-camera-frame-1") -> FramePacket:
    return FramePacket(
        capture_id=capture_id,
        jpeg_bytes=_minimal_jpeg(),
        width_px=WIDTH,
        height_px=HEIGHT,
        source_sequence=11,
        source_timestamp_ns=1_000,
        source_clock="camera.monotonic",
        host_request_ns=900,
        host_first_byte_ns=1_000,
        host_complete_ns=1_100,
        settings_hash="a" * 64,
        timestamp_quality=TimestampQuality.DEVICE_EXPOSURE,
        freshness_token="sequence:11",
        freshness_basis="device_sequence",
    )


def _intrinsics() -> PinholeIntrinsics:
    return PinholeIntrinsics(
        calibration_id="b0477-test-mode",
        width_px=WIDTH,
        height_px=HEIGHT,
        fx_px=1000.0,
        fy_px=1000.0,
        cx_px=800.0,
        cy_px=600.0,
        source_sha256="b" * 64,
        camera_frame=CAMERA_FRAME,
    )


def _tag(tag_id: int, *, family: str = "tag36h11") -> PlanarBoardTag:
    center_x, center_y = CENTRES_MM[tag_id]
    half = 20.0
    return PlanarBoardTag(
        TagReference(family, tag_id),
        (
            Point3Mm(BOARD_FRAME, center_x - half, center_y + half, 0.0),
            Point3Mm(BOARD_FRAME, center_x + half, center_y + half, 0.0),
            Point3Mm(BOARD_FRAME, center_x + half, center_y - half, 0.0),
            Point3Mm(BOARD_FRAME, center_x - half, center_y - half, 0.0),
        ),
    )


def _tag_map(*, replacement: PlanarBoardTag | None = None) -> PlanarBoardTagMap:
    tags = tuple(
        replacement
        if replacement is not None and replacement.tag.tag_id == tag_id
        else _tag(tag_id)
        for tag_id in range(6)
    )
    return PlanarBoardTagMap(
        map_id="rc03-fixed-camera-test-map",
        board_frame=BOARD_FRAME,
        tag_plane_z_board_mm=0.0,
        tags=tags,
        source_sha256="c" * 64,
    )


def _project(point: Point3Mm) -> tuple[float, float]:
    camera = GROUND_TRUTH.transform_position_mm(Vec3(point.x, point.y, point.z))
    intrinsics = _intrinsics()
    return (
        intrinsics.fx_px * camera.x / camera.z + intrinsics.cx_px,
        intrinsics.fy_px * camera.y / camera.z + intrinsics.cy_px,
    )


def _detection(
    definition: PlanarBoardTag,
    *,
    offset_px: tuple[float, float] = (0.0, 0.0),
    family: str | None = None,
) -> AprilTagDetection:
    corners = tuple(
        PixelCorner(
            _project(point)[0] + offset_px[0], _project(point)[1] + offset_px[1]
        )
        for point in definition.corners_board_mm
    )
    return AprilTagDetection(
        TagReference(family or definition.tag.family, definition.tag.tag_id),
        corners,  # type: ignore[arg-type]
        decision_margin=100.0,
        hamming=0,
    )


def _batch(
    *,
    offsets: dict[int, tuple[float, float]] | None = None,
    missing: int | None = None,
    changed_family: int | None = None,
    frame: FramePacket | None = None,
) -> AprilTagDetectionBatch:
    tag_map = _tag_map()
    offsets = offsets or {}
    detections = tuple(
        _detection(
            tag_map.tags[tag_id],
            offset_px=offsets.get(tag_id, (0.0, 0.0)),
            family="tag25h9" if tag_id == changed_family else None,
        )
        for tag_id in range(6)
        if tag_id != missing
    )
    packet = frame or _frame()
    return AprilTagDetectionBatch(
        frame=FrameCaptureBinding.from_frame_packet(
            packet,
            host_clock="test.monotonic",
        ),
        detector=DetectorIdentity(
            "apriltag-test-double",
            "1.0.0",
            "d" * 64,
            "e" * 64,
        ),
        detections=detections,
    )


def _config() -> PlanarPoseEstimatorConfig:
    return PlanarPoseEstimatorConfig(
        maximum_tag_reprojection_rmse_px=2.0,
        minimum_inlier_tags=4,
    )


def test_extracts_fit_from_zero_through_three_and_audits_four_and_five() -> None:
    result = estimate_fixed_camera_board_pose(
        _batch(),
        _intrinsics(),
        _tag_map(),
        estimator_config=_config(),
    )

    assert tuple(tag.tag_id for tag in result.fit_observation.used_tags) == (0, 1, 2, 3)
    translation = result.fit_observation.pose.translation_mm
    assert (translation.x, translation.y, translation.z) == pytest.approx(
        (
            GROUND_TRUTH.translation_mm.x,
            GROUND_TRUTH.translation_mm.y,
            GROUND_TRUTH.translation_mm.z,
        )
    )
    assert result.held_out_maximum_px == pytest.approx(0.0, abs=1e-7)
    capture = result.capture_board_pose()
    assert capture["pose_fit_tag_ids"] == [0, 1, 2, 3]
    assert capture["held_out_tag_ids"] == [4, 5]
    assert capture["frame_sha256"] == _frame().sha256
    assert result.to_dict()["authority"] == {
        "physical_authority": "NONE",
        "physical_commands_generated": 0,
        "can_authorize_motion": False,
        "can_release_physical_gates": False,
    }


def test_held_out_shift_cannot_change_fit_and_fails_capture_gate() -> None:
    baseline = estimate_fixed_camera_board_pose(
        _batch(), _intrinsics(), _tag_map(), estimator_config=_config()
    )
    shifted = estimate_fixed_camera_board_pose(
        _batch(offsets={4: (3.0, 0.0), 5: (0.0, -4.0)}),
        _intrinsics(),
        _tag_map(),
        estimator_config=_config(),
    )

    assert shifted.fit_observation.content_hash == baseline.fit_observation.content_hash
    assert shifted.content_hash != baseline.content_hash
    assert shifted.held_out_maximum_px == pytest.approx(4.0, abs=1e-7)
    with pytest.raises(FixedCameraBoardPoseError, match="held-out"):
        shifted.capture_board_pose()


def test_fit_tag_outlier_cannot_be_discarded() -> None:
    with pytest.raises(
        PlanarPoseEstimationError,
        match="inlier|consensus|pose|reprojection",
    ):
        estimate_fixed_camera_board_pose(
            _batch(offsets={2: (20.0, 20.0)}),
            _intrinsics(),
            _tag_map(),
            estimator_config=_config(),
        )


@pytest.mark.parametrize(
    ("batch", "message"),
    [
        (_batch(missing=5), "exactly 0 through 5"),
        (_batch(changed_family=5), "exactly 0 through 5"),
    ],
)
def test_rejects_incomplete_or_wrong_family_detection_evidence(
    batch: AprilTagDetectionBatch,
    message: str,
) -> None:
    with pytest.raises(FixedCameraBoardPoseError, match=message):
        estimate_fixed_camera_board_pose(
            batch,
            _intrinsics(),
            _tag_map(),
            estimator_config=_config(),
        )


def test_rejects_non_rc03_map_family_and_non_four_tag_policy() -> None:
    with pytest.raises(FixedCameraBoardPoseError, match="another tag family"):
        estimate_fixed_camera_board_pose(
            _batch(),
            _intrinsics(),
            _tag_map(replacement=_tag(5, family="tag25h9")),
            estimator_config=_config(),
        )
    with pytest.raises(FixedCameraBoardPoseError, match="all four fit tags"):
        estimate_fixed_camera_board_pose(
            _batch(),
            _intrinsics(),
            _tag_map(),
            estimator_config=replace(_config(), minimum_inlier_tags=3),
        )


def test_coordinator_orders_services_and_rejects_frame_substitution() -> None:
    events: list[str] = []
    frame = _frame()
    batch = _batch(frame=frame)

    class Detector:
        def detect(self, supplied: FramePacket) -> AprilTagDetectionBatch:
            assert supplied is frame
            events.append("detect")
            return batch

    class Rectifier:
        def rectify_detection_batch(
            self, supplied: AprilTagDetectionBatch
        ) -> AprilTagDetectionBatch:
            assert supplied is batch
            events.append("rectify")
            return supplied

    result = extract_fixed_camera_board_pose(
        frame,
        Detector(),
        Rectifier(),
        _intrinsics(),
        _tag_map(),
        estimator_config=_config(),
    )
    assert events == ["detect", "rectify"]
    assert result.full_detection_batch is batch

    substituted = _batch(frame=_frame(capture_id="substituted-frame"))

    class SubstitutingDetector:
        def detect(self, supplied: FramePacket) -> AprilTagDetectionBatch:
            return substituted

    with pytest.raises(FixedCameraBoardPoseError, match="different frame"):
        extract_fixed_camera_board_pose(
            frame,
            SubstitutingDetector(),
            Rectifier(),
            _intrinsics(),
            _tag_map(),
            estimator_config=_config(),
        )
