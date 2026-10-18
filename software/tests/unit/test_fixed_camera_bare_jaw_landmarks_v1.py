from __future__ import annotations

import pytest

from rocell.geometry import Point3Mm, RigidTransform, Rotation3, Vec3
from rocell.calibration.fixed_camera_bare_jaw_landmarks_v1 import (
    FIT_ROLE,
    HOLDOUT_ROLE,
    REFERENCE_FRAME,
    AuditedBareJawLandmarkDetectorV1,
    BareJawLandmarkError,
    BareJawLandmarkPoseEstimateV1,
    BareJawPixelLandmarkV1,
    BareJawReferenceLandmarkV1,
    BareJawReferenceModelV1,
)

from test_fixed_camera_bare_jaw_observer_v1 import calibration
from test_fixed_camera_board_pose_extractor_v1 import CAMERA_FRAME, _frame, _intrinsics


def reference_model(*, source_sha256: str = "3" * 64) -> BareJawReferenceModelV1:
    coordinates = (
        ("left-top", -60.0, -35.0, 0.0),
        ("right-top", 60.0, -35.0, 0.0),
        ("left-middle", -60.0, 0.0, 0.0),
        ("right-middle", 60.0, 0.0, 0.0),
        ("left-bottom", -60.0, 35.0, 0.0),
        ("right-bottom", 60.0, 35.0, 0.0),
    )
    return BareJawReferenceModelV1(
        model_id="rc03-bare-jaw-landmarks-physical-1",
        source_sha256=source_sha256,
        landmarks=tuple(
            BareJawReferenceLandmarkV1(
                landmark_id, Point3Mm(REFERENCE_FRAME, x, y, z)
            )
            for landmark_id, x, y, z in coordinates
        ),
    )


class PoseSource:
    detector_id = "rocell.fixed-camera-bare-jaw-reference"
    detector_version = "1.0.0"
    configuration_sha256 = "1" * 64
    implementation_sha256 = "2" * 64

    def __init__(
        self,
        *,
        holdout_offset_px: float = 0.0,
        frame_sha256: str | None = None,
        uncertainty_mm: float = 0.7,
        transform: RigidTransform | None = None,
        roles: tuple[str, ...] = (
            FIT_ROLE,
            FIT_ROLE,
            FIT_ROLE,
            FIT_ROLE,
            HOLDOUT_ROLE,
            HOLDOUT_ROLE,
        ),
    ) -> None:
        self.holdout_offset_px = holdout_offset_px
        self.frame_sha256 = frame_sha256
        self.uncertainty_mm = uncertainty_mm
        self.transform = transform or RigidTransform(
            CAMERA_FRAME,
            REFERENCE_FRAME,
            Rotation3.identity(),
            Vec3(25.0, -10.0, 900.0),
        )
        self.roles = roles
        self.calls = 0

    def estimate(self, frame, intrinsics, model):
        self.calls += 1
        observations = []
        for index, landmark in enumerate(model.landmarks):
            point = self.transform.transform_point(landmark.point)
            role = self.roles[index]
            offset = self.holdout_offset_px if role == HOLDOUT_ROLE else 0.0
            observations.append(
                BareJawPixelLandmarkV1(
                    landmark.landmark_id,
                    intrinsics.fx_px * point.x / point.z + intrinsics.cx_px + offset,
                    intrinsics.fy_px * point.y / point.z + intrinsics.cy_px,
                    role,
                )
            )
        return BareJawLandmarkPoseEstimateV1(
            frame_sha256=self.frame_sha256 or frame.sha256,
            camera_T_reference=self.transform,
            landmarks=tuple(observations),
            uncertainty_mm=self.uncertainty_mm,
        )


def detector(source: PoseSource, *, model: BareJawReferenceModelV1 | None = None):
    return AuditedBareJawLandmarkDetectorV1(
        calibration(), _intrinsics(), model or reference_model(), source
    )


def test_adapter_emits_calibrated_camera_reference_after_fit_and_holdout_checks() -> None:
    source = PoseSource()
    result = detector(source).detect(_frame())

    assert source.calls == 1
    assert result.frame_sha256 == _frame().sha256
    assert result.camera_frame == CAMERA_FRAME
    assert result.camera_xyz_mm == pytest.approx((25.0, -10.0, 900.0))
    assert result.uncertainty_mm == pytest.approx(0.7)
    assert result.calibration_record_sha256 == calibration().canonical_sha256


def test_adapter_rejects_holdout_drift_even_when_fit_landmarks_are_exact() -> None:
    with pytest.raises(BareJawLandmarkError, match="HOLDOUT"):
        detector(PoseSource(holdout_offset_px=2.1)).detect(_frame())


def test_adapter_rejects_crossed_frame_and_excessive_uncertainty() -> None:
    with pytest.raises(BareJawLandmarkError, match="different frame"):
        detector(PoseSource(frame_sha256="f" * 64)).detect(_frame())
    with pytest.raises(BareJawLandmarkError, match="uncertainty"):
        detector(PoseSource(uncertainty_mm=1.6)).detect(_frame())


def test_adapter_requires_independent_holdout_landmarks() -> None:
    source = PoseSource(roles=(FIT_ROLE,) * 6)
    with pytest.raises(BareJawLandmarkError, match="two HOLDOUT"):
        detector(source).detect(_frame())


def test_adapter_rejects_reference_behind_camera() -> None:
    transform = RigidTransform(
        CAMERA_FRAME,
        REFERENCE_FRAME,
        Rotation3.identity(),
        Vec3(0.0, 0.0, -900.0),
    )
    source = PoseSource(transform=transform)
    with pytest.raises(BareJawLandmarkError, match="behind the camera"):
        detector(source).detect(_frame())


def test_constructor_binds_exact_reference_model_and_source_identity() -> None:
    with pytest.raises(BareJawLandmarkError, match="reference model"):
        detector(PoseSource(), model=reference_model(source_sha256="a" * 64))

    source = PoseSource()
    source.detector_version = "2.0.0"
    with pytest.raises(BareJawLandmarkError, match="detector version"):
        detector(source)


def test_reference_model_rejects_duplicate_and_collinear_geometry() -> None:
    with pytest.raises(BareJawLandmarkError, match="coordinates"):
        BareJawReferenceModelV1(
            "duplicate-model",
            "3" * 64,
            tuple(
                BareJawReferenceLandmarkV1(
                    f"duplicate-{index}",
                    Point3Mm(REFERENCE_FRAME, 0.0, 0.0, 0.0),
                )
                for index in range(6)
            ),
        )

    with pytest.raises(BareJawLandmarkError, match="collinear"):
        BareJawReferenceModelV1(
            "line-model",
            "3" * 64,
            tuple(
                BareJawReferenceLandmarkV1(
                    f"p{index}",
                    Point3Mm(REFERENCE_FRAME, float(index), 0.0, 0.0),
                )
                for index in range(6)
            ),
        )
