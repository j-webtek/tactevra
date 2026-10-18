"""Auditable landmark adapter for the fixed-camera bare-jaw observer.

This module does not open a camera or solve a pose.  It turns an injected,
identity-bound landmark pose source into the strict ``CalibratedBareJawDetector``
contract only after independently reprojecting every retained landmark.  Fit
and holdout landmarks are checked separately so a pose source cannot validate
itself solely with the points it fitted.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Protocol

from rocell.geometry import Point3Mm, RigidTransform
from rocell.vision.camera import FramePacket
from rocell.vision.planar_pose_estimator import PinholeIntrinsics

from .fixed_camera_bare_jaw_observer_v1 import (
    BareJawCameraObservationV1,
    ReviewedBareJawDetectorCalibrationV1,
)


REFERENCE_FRAME = "bare_jaw_reference"
FIT_ROLE = "FIT"
HOLDOUT_ROLE = "HOLDOUT"
MINIMUM_FIT_LANDMARKS = 4
MINIMUM_HOLDOUT_LANDMARKS = 2
MAXIMUM_FIT_RMS_PX = 2.0
MAXIMUM_HOLDOUT_RMS_PX = 2.0
MAXIMUM_SINGLE_LANDMARK_ERROR_PX = 3.0


class BareJawLandmarkError(ValueError):
    """The jaw landmark evidence is incomplete, crossed, or inaccurate."""


def _text(value: object, label: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BareJawLandmarkError(f"{label} must be non-empty text")
    return value


def _digest(value: object, label: str) -> str:
    text = _text(value, label, maximum=64).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise BareJawLandmarkError(f"{label} must be a hexadecimal SHA-256 digest")
    return text


def _finite(value: object, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BareJawLandmarkError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise BareJawLandmarkError(
            f"{label} must be between {minimum} and {maximum}"
        )
    return result


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class BareJawReferenceLandmarkV1:
    """One named millimetre landmark in the rigid bare-jaw reference frame."""

    landmark_id: str
    point: Point3Mm

    def __post_init__(self) -> None:
        object.__setattr__(self, "landmark_id", _text(self.landmark_id, "landmark_id"))
        if not isinstance(self.point, Point3Mm):
            raise TypeError("point must be Point3Mm")
        if self.point.frame != REFERENCE_FRAME:
            raise BareJawLandmarkError(
                f"reference landmark must be expressed in {REFERENCE_FRAME}"
            )
        for axis, value in zip("xyz", (self.point.x, self.point.y, self.point.z)):
            _finite(value, f"point.{axis}", minimum=-1000.0, maximum=1000.0)


@dataclass(frozen=True, slots=True)
class BareJawReferenceModelV1:
    """Exact retained geometry used by the reviewed bare-jaw calibration."""

    model_id: str
    source_sha256: str
    landmarks: tuple[BareJawReferenceLandmarkV1, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        object.__setattr__(
            self, "source_sha256", _digest(self.source_sha256, "source_sha256")
        )
        if not isinstance(self.landmarks, tuple):
            raise TypeError("landmarks must be a tuple")
        if len(self.landmarks) < MINIMUM_FIT_LANDMARKS + MINIMUM_HOLDOUT_LANDMARKS:
            raise BareJawLandmarkError("reference model requires at least six landmarks")
        identifiers: set[str] = set()
        coordinates: set[tuple[float, float, float]] = set()
        for landmark in self.landmarks:
            if not isinstance(landmark, BareJawReferenceLandmarkV1):
                raise TypeError("landmarks must contain BareJawReferenceLandmarkV1")
            if landmark.landmark_id in identifiers:
                raise BareJawLandmarkError("reference landmark ids must be unique")
            coordinate = (landmark.point.x, landmark.point.y, landmark.point.z)
            if coordinate in coordinates:
                raise BareJawLandmarkError("reference landmark coordinates must be unique")
            identifiers.add(landmark.landmark_id)
            coordinates.add(coordinate)
        if not _contains_noncollinear_points(tuple(coordinates)):
            raise BareJawLandmarkError("reference landmarks must not all be collinear")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "rocell.bare_jaw_reference_model.v1",
            "model_id": self.model_id,
            "reference_frame": REFERENCE_FRAME,
            "source_sha256": self.source_sha256,
            "landmarks": [
                {
                    "landmark_id": landmark.landmark_id,
                    "xyz_mm": [landmark.point.x, landmark.point.y, landmark.point.z],
                }
                for landmark in sorted(self.landmarks, key=lambda item: item.landmark_id)
            ],
            "physical_release_effect": "NONE",
        }

    @property
    def content_hash(self) -> str:
        return _canonical_hash(self.to_dict())


def _contains_noncollinear_points(
    points: tuple[tuple[float, float, float], ...],
) -> bool:
    origin = points[0]
    first = tuple(points[1][axis] - origin[axis] for axis in range(3))
    for point in points[2:]:
        second = tuple(point[axis] - origin[axis] for axis in range(3))
        cross = (
            first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0],
        )
        if math.sqrt(sum(value * value for value in cross)) > 1e-9:
            return True
    return False


@dataclass(frozen=True, slots=True)
class BareJawPixelLandmarkV1:
    """One landmark observation and its predeclared validation role."""

    landmark_id: str
    x_px: float
    y_px: float
    role: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "landmark_id", _text(self.landmark_id, "landmark_id"))
        object.__setattr__(
            self, "x_px", _finite(self.x_px, "x_px", minimum=-1_000_000.0, maximum=1_000_000.0)
        )
        object.__setattr__(
            self, "y_px", _finite(self.y_px, "y_px", minimum=-1_000_000.0, maximum=1_000_000.0)
        )
        if self.role not in (FIT_ROLE, HOLDOUT_ROLE):
            raise BareJawLandmarkError("landmark role must be FIT or HOLDOUT")


@dataclass(frozen=True, slots=True)
class BareJawLandmarkPoseEstimateV1:
    """Untrusted pose-source result that the adapter independently verifies."""

    frame_sha256: str
    camera_T_reference: RigidTransform
    landmarks: tuple[BareJawPixelLandmarkV1, ...]
    uncertainty_mm: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "frame_sha256", _digest(self.frame_sha256, "frame_sha256")
        )
        if not isinstance(self.camera_T_reference, RigidTransform):
            raise TypeError("camera_T_reference must be RigidTransform")
        if not isinstance(self.landmarks, tuple):
            raise TypeError("landmarks must be a tuple")
        for landmark in self.landmarks:
            if not isinstance(landmark, BareJawPixelLandmarkV1):
                raise TypeError("landmarks must contain BareJawPixelLandmarkV1")
        object.__setattr__(
            self,
            "uncertainty_mm",
            _finite(self.uncertainty_mm, "uncertainty_mm", minimum=0.0, maximum=100.0),
        )


class BareJawLandmarkPoseSource(Protocol):
    """Injected landmark detector/pose solver with a retained code identity."""

    detector_id: str
    detector_version: str
    configuration_sha256: str
    implementation_sha256: str

    def estimate(
        self,
        frame: FramePacket,
        intrinsics: PinholeIntrinsics,
        model: BareJawReferenceModelV1,
    ) -> BareJawLandmarkPoseEstimateV1: ...


@dataclass(frozen=True, slots=True)
class AuditedBareJawLandmarkDetectorV1:
    """Verify landmark pose evidence and emit the existing detector contract."""

    calibration: ReviewedBareJawDetectorCalibrationV1
    intrinsics: PinholeIntrinsics
    model: BareJawReferenceModelV1
    source: BareJawLandmarkPoseSource

    def __post_init__(self) -> None:
        if not isinstance(self.calibration, ReviewedBareJawDetectorCalibrationV1):
            raise TypeError("calibration must be ReviewedBareJawDetectorCalibrationV1")
        if not isinstance(self.intrinsics, PinholeIntrinsics):
            raise TypeError("intrinsics must be PinholeIntrinsics")
        if not isinstance(self.model, BareJawReferenceModelV1):
            raise TypeError("model must be BareJawReferenceModelV1")
        if not callable(getattr(self.source, "estimate", None)):
            raise TypeError("source must provide estimate(frame, intrinsics, model)")
        bindings = (
            (self.intrinsics.content_hash, self.calibration.camera_intrinsics_sha256, "intrinsics"),
            (self.intrinsics.camera_frame, self.calibration.camera_frame, "camera frame"),
            (self.model.source_sha256, self.calibration.reference_model_sha256, "reference model"),
            (
                getattr(self.source, "detector_id", None),
                self.calibration.detector_id,
                "detector id",
            ),
            (
                getattr(self.source, "detector_version", None),
                self.calibration.detector_version,
                "detector version",
            ),
            (
                getattr(self.source, "configuration_sha256", None),
                self.calibration.configuration_sha256,
                "configuration",
            ),
            (
                getattr(self.source, "implementation_sha256", None),
                self.calibration.implementation_sha256,
                "implementation",
            ),
        )
        for actual, expected, label in bindings:
            if actual != expected:
                raise BareJawLandmarkError(f"{label} differs from reviewed calibration")

    def detect(self, frame: FramePacket) -> BareJawCameraObservationV1:
        if not isinstance(frame, FramePacket):
            raise TypeError("frame must be FramePacket")
        if (frame.width_px, frame.height_px) != (
            self.intrinsics.width_px,
            self.intrinsics.height_px,
        ):
            raise BareJawLandmarkError("frame resolution differs from reviewed intrinsics")
        estimate = self.source.estimate(frame, self.intrinsics, self.model)
        if not isinstance(estimate, BareJawLandmarkPoseEstimateV1):
            raise TypeError("landmark pose source must return BareJawLandmarkPoseEstimateV1")
        if estimate.frame_sha256 != frame.sha256:
            raise BareJawLandmarkError("landmark estimate belongs to a different frame")
        transform = estimate.camera_T_reference
        if (
            transform.parent_frame != self.calibration.camera_frame
            or transform.child_frame != REFERENCE_FRAME
        ):
            raise BareJawLandmarkError("landmark pose frames differ from calibration")
        if estimate.uncertainty_mm > self.calibration.maximum_detector_uncertainty_mm:
            raise BareJawLandmarkError("landmark uncertainty exceeds reviewed limit")

        model_by_id = {item.landmark_id: item for item in self.model.landmarks}
        observed_by_id: dict[str, BareJawPixelLandmarkV1] = {}
        for observed in estimate.landmarks:
            if observed.landmark_id in observed_by_id:
                raise BareJawLandmarkError("observed landmark ids must be unique")
            if observed.landmark_id not in model_by_id:
                raise BareJawLandmarkError("observed landmark is absent from reference model")
            if not (
                0.0 <= observed.x_px < frame.width_px
                and 0.0 <= observed.y_px < frame.height_px
            ):
                raise BareJawLandmarkError("observed landmark lies outside the frame")
            observed_by_id[observed.landmark_id] = observed
        if set(observed_by_id) != set(model_by_id):
            raise BareJawLandmarkError("every reference landmark must be observed exactly once")

        residuals: dict[str, list[float]] = {FIT_ROLE: [], HOLDOUT_ROLE: []}
        for landmark_id, reference in model_by_id.items():
            camera_point = transform.transform_point(reference.point)
            if camera_point.z <= 1e-6:
                raise BareJawLandmarkError("projected reference landmark is behind the camera")
            expected_x = (
                self.intrinsics.fx_px * camera_point.x
                + self.intrinsics.skew_px * camera_point.y
            ) / camera_point.z + self.intrinsics.cx_px
            expected_y = (
                self.intrinsics.fy_px * camera_point.y / camera_point.z
                + self.intrinsics.cy_px
            )
            if not (
                0.0 <= expected_x < frame.width_px
                and 0.0 <= expected_y < frame.height_px
            ):
                raise BareJawLandmarkError(
                    "projected reference landmark lies outside the frame"
                )
            observed = observed_by_id[landmark_id]
            error = math.hypot(observed.x_px - expected_x, observed.y_px - expected_y)
            if error > MAXIMUM_SINGLE_LANDMARK_ERROR_PX:
                raise BareJawLandmarkError("single-landmark reprojection error exceeds limit")
            residuals[observed.role].append(error)

        if len(residuals[FIT_ROLE]) < MINIMUM_FIT_LANDMARKS:
            raise BareJawLandmarkError("at least four FIT landmarks are required")
        if len(residuals[HOLDOUT_ROLE]) < MINIMUM_HOLDOUT_LANDMARKS:
            raise BareJawLandmarkError("at least two HOLDOUT landmarks are required")
        fit_rms = _rms(residuals[FIT_ROLE])
        holdout_rms = _rms(residuals[HOLDOUT_ROLE])
        if fit_rms > MAXIMUM_FIT_RMS_PX:
            raise BareJawLandmarkError("FIT landmark reprojection RMS exceeds limit")
        if holdout_rms > MAXIMUM_HOLDOUT_RMS_PX:
            raise BareJawLandmarkError("HOLDOUT landmark reprojection RMS exceeds limit")

        translation = transform.translation_mm
        return BareJawCameraObservationV1(
            frame_sha256=frame.sha256,
            calibration_record_sha256=self.calibration.canonical_sha256,
            detector_id=self.calibration.detector_id,
            detector_version=self.calibration.detector_version,
            configuration_sha256=self.calibration.configuration_sha256,
            implementation_sha256=self.calibration.implementation_sha256,
            camera_frame=self.calibration.camera_frame,
            camera_xyz_mm=(translation.x, translation.y, translation.z),
            uncertainty_mm=estimate.uncertainty_mm,
        )


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values))
