"""Extract one fixed-camera RC03 board pose with disjoint fit and audit tags.

The generic detector and planar estimator intentionally know nothing about the
RC03 tag roles.  This module supplies that missing policy boundary.  Tags 0--3
are the only observations allowed into the pose fit.  Tags 4--5 are projected
through the completed pose afterward and can only accept or reject it.

The service is offline and zero-authority.  It receives an immutable frame and
already configured detector/rectifier services; it cannot open a camera or
command the robot.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Protocol

from rocell.geometry import Vec3

from .camera import FramePacket
from .detections import AprilTagDetection, AprilTagDetectionBatch
from .planar_pose_estimator import (
    PinholeIntrinsics,
    PlanarBoardTag,
    PlanarBoardTagMap,
    PlanarPoseEstimatorConfig,
    estimate_planar_board_pose,
)
from .pose_estimation_records import AprilTagPoseObservation


EXTRACTOR_ID = "rocell.fixed_camera_board_pose_extractor"
EXTRACTOR_VERSION = "1.0.0"
POSE_FIT_TAG_IDS = (0, 1, 2, 3)
HELD_OUT_TAG_IDS = (4, 5)
REQUIRED_TAG_IDS = POSE_FIT_TAG_IDS + HELD_OUT_TAG_IDS
TAG_FAMILY = "tag36h11"
DEFAULT_MAXIMUM_HELD_OUT_RESIDUAL_PX = 2.0


class FixedCameraBoardPoseError(ValueError):
    """The frame, tag evidence, or fitted pose fails the RC03 contract."""


class FrameTagDetector(Protocol):
    """The only detector operation used by this offline coordinator."""

    def detect(self, frame: FramePacket) -> AprilTagDetectionBatch: ...


class DetectionRectifier(Protocol):
    """Map raw detector corners into the calibrated pinhole pixel space."""

    def rectify_detection_batch(
        self, batch: AprilTagDetectionBatch
    ) -> AprilTagDetectionBatch: ...


def _canonical_hash(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraBoardPoseError(
            "board-pose evidence is not canonical JSON"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _implementation_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraBoardPoseError(f"{label} must be a nonnegative number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise FixedCameraBoardPoseError(f"{label} must be a nonnegative number")
    return result


@dataclass(frozen=True, slots=True)
class HeldOutTagResidual:
    """Independent reprojection evidence for one excluded station tag."""

    tag_id: int
    corner_residuals_px: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if self.tag_id not in HELD_OUT_TAG_IDS:
            raise FixedCameraBoardPoseError("held-out diagnostic has an invalid tag id")
        values = tuple(
            _finite_nonnegative(value, "held-out corner residual")
            for value in self.corner_residuals_px
        )
        if len(values) != 4:
            raise FixedCameraBoardPoseError(
                "held-out diagnostic must contain four corner residuals"
            )
        object.__setattr__(self, "corner_residuals_px", values)

    @property
    def rms_px(self) -> float:
        return math.sqrt(sum(value * value for value in self.corner_residuals_px) / 4.0)

    @property
    def maximum_px(self) -> float:
        return max(self.corner_residuals_px)

    def to_dict(self) -> dict[str, object]:
        return {
            "tag_id": self.tag_id,
            "corner_residuals_px": list(self.corner_residuals_px),
            "rms_px": self.rms_px,
            "maximum_px": self.maximum_px,
            "used_in_pose_fit": False,
        }


@dataclass(frozen=True, slots=True)
class FixedCameraBoardPoseResult:
    """Hash-bound full detection, fit pose, and held-out audit result."""

    full_detection_batch: AprilTagDetectionBatch
    fit_observation: AprilTagPoseObservation
    full_tag_map_sha256: str
    maximum_held_out_residual_px: float
    held_out_residuals: tuple[HeldOutTagResidual, HeldOutTagResidual]
    extractor_configuration_sha256: str
    extractor_implementation_sha256: str

    def __post_init__(self) -> None:
        if (
            self.fit_observation.detection_batch.frame
            != self.full_detection_batch.frame
        ):
            raise FixedCameraBoardPoseError(
                "fit observation and full detections bind different frames"
            )
        if tuple(item.tag_id for item in self.held_out_residuals) != HELD_OUT_TAG_IDS:
            raise FixedCameraBoardPoseError(
                "held-out residuals must be ordered tag IDs 4 and 5"
            )
        limit = _finite_nonnegative(
            self.maximum_held_out_residual_px,
            "maximum held-out residual threshold",
        )
        object.__setattr__(self, "maximum_held_out_residual_px", limit)
        for label, digest in (
            ("full tag map", self.full_tag_map_sha256),
            ("extractor configuration", self.extractor_configuration_sha256),
            ("extractor implementation", self.extractor_implementation_sha256),
        ):
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise FixedCameraBoardPoseError(f"{label} digest is invalid")

    @property
    def held_out_maximum_px(self) -> float:
        return max(item.maximum_px for item in self.held_out_residuals)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "rocell.fixed_camera_board_pose_observation.v1",
            "extractor": {
                "id": EXTRACTOR_ID,
                "version": EXTRACTOR_VERSION,
                "configuration_sha256": self.extractor_configuration_sha256,
                "implementation_sha256": self.extractor_implementation_sha256,
            },
            "full_detection_batch": self.full_detection_batch.to_dict(),
            "full_detection_batch_sha256": self.full_detection_batch.content_hash,
            "fit_observation": self.fit_observation.to_dict(),
            "fit_observation_sha256": self.fit_observation.content_hash,
            "tag_policy": {
                "pose_fit_tag_ids": list(POSE_FIT_TAG_IDS),
                "held_out_tag_ids": list(HELD_OUT_TAG_IDS),
                "held_out_maximum_residual_limit_px": (
                    self.maximum_held_out_residual_px
                ),
            },
            "source_hashes": {
                "camera_intrinsics_sha256": (
                    self.fit_observation.camera_intrinsics_sha256
                ),
                "tag_map_sha256": self.full_tag_map_sha256,
            },
            "quality": {
                "fit_reprojection_rms_px": self.fit_observation.inlier_rmse_px,
                "held_out_maximum_residual_px": self.held_out_maximum_px,
                "held_out_residuals": [
                    item.to_dict() for item in self.held_out_residuals
                ],
                "passed": (
                    self.held_out_maximum_px <= self.maximum_held_out_residual_px
                ),
            },
            "authority": {
                "physical_authority": "NONE",
                "physical_commands_generated": 0,
                "can_authorize_motion": False,
                "can_release_physical_gates": False,
            },
        }

    @property
    def content_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def capture_board_pose(self) -> dict[str, object]:
        """Return the exact board-pose object accepted by capture compiler v1."""

        if self.held_out_maximum_px > self.maximum_held_out_residual_px:
            raise FixedCameraBoardPoseError(
                "held-out tag residual exceeds the configured pixel limit"
            )
        return {
            "observation_sha256": self.content_hash,
            "frame_sha256": self.full_detection_batch.frame.jpeg_sha256,
            "camera_intrinsics_sha256": (self.fit_observation.camera_intrinsics_sha256),
            "tag_map_sha256": self.full_tag_map_sha256,
            "pose_fit_tag_ids": list(POSE_FIT_TAG_IDS),
            "held_out_tag_ids": list(HELD_OUT_TAG_IDS),
            "reprojection_rms_px": self.fit_observation.inlier_rmse_px,
            "held_out_max_residual_px": self.held_out_maximum_px,
        }


def _required_detections(
    batch: AprilTagDetectionBatch,
) -> dict[int, AprilTagDetection]:
    accepted = {
        detection.tag.tag_id: detection
        for detection in batch.detections
        if detection.detector_accepted and detection.tag.family == TAG_FAMILY
    }
    accepted_ids = tuple(sorted(accepted))
    if accepted_ids != REQUIRED_TAG_IDS:
        raise FixedCameraBoardPoseError(
            "accepted tag36h11 IDs must be exactly 0 through 5"
        )
    if any(
        detection.detector_accepted and detection.tag.family != TAG_FAMILY
        for detection in batch.detections
    ):
        raise FixedCameraBoardPoseError("an unexpected accepted tag family is present")
    return accepted


def _definitions(tag_map: PlanarBoardTagMap) -> dict[int, PlanarBoardTag]:
    if any(definition.tag.family != TAG_FAMILY for definition in tag_map.tags):
        raise FixedCameraBoardPoseError(
            "RC03 board map cannot contain another tag family"
        )
    definitions = {
        definition.tag.tag_id: definition
        for definition in tag_map.tags
        if definition.tag.family == TAG_FAMILY
    }
    if tuple(sorted(definitions)) != REQUIRED_TAG_IDS:
        raise FixedCameraBoardPoseError(
            "RC03 board map must contain exactly tag36h11 IDs 0 through 5"
        )
    return definitions


def _project(
    definition: PlanarBoardTag,
    pose: AprilTagPoseObservation,
    intrinsics: PinholeIntrinsics,
) -> tuple[tuple[float, float], ...]:
    projected: list[tuple[float, float]] = []
    for corner in definition.corners_board_mm:
        camera = pose.pose.transform_position_mm(Vec3(corner.x, corner.y, corner.z))
        if camera.z <= 0.0:
            raise FixedCameraBoardPoseError(
                f"held-out tag {definition.tag.tag_id} projects behind the camera"
            )
        normalized_x = camera.x / camera.z
        normalized_y = camera.y / camera.z
        projected.append(
            (
                intrinsics.fx_px * normalized_x
                + intrinsics.skew_px * normalized_y
                + intrinsics.cx_px,
                intrinsics.fy_px * normalized_y + intrinsics.cy_px,
            )
        )
    return tuple(projected)


def estimate_fixed_camera_board_pose(
    rectified_batch: AprilTagDetectionBatch,
    intrinsics: PinholeIntrinsics,
    tag_map: PlanarBoardTagMap,
    *,
    estimator_config: PlanarPoseEstimatorConfig | None = None,
    maximum_held_out_residual_px: float = DEFAULT_MAXIMUM_HELD_OUT_RESIDUAL_PX,
) -> FixedCameraBoardPoseResult:
    """Fit tags 0--3 and independently score tags 4--5."""

    if not isinstance(rectified_batch, AprilTagDetectionBatch):
        raise TypeError("rectified_batch must be AprilTagDetectionBatch")
    if not isinstance(intrinsics, PinholeIntrinsics):
        raise TypeError("intrinsics must be PinholeIntrinsics")
    if not isinstance(tag_map, PlanarBoardTagMap):
        raise TypeError("tag_map must be PlanarBoardTagMap")
    limit = _finite_nonnegative(
        maximum_held_out_residual_px,
        "maximum held-out residual threshold",
    )
    detections = _required_detections(rectified_batch)
    definitions = _definitions(tag_map)
    config = estimator_config or PlanarPoseEstimatorConfig(
        maximum_tag_reprojection_rmse_px=2.0,
        minimum_inlier_tags=4,
    )
    if config.minimum_inlier_tags != 4:
        raise FixedCameraBoardPoseError(
            "RC03 fixed-camera pose policy requires all four fit tags"
        )

    fit_batch = AprilTagDetectionBatch(
        frame=rectified_batch.frame,
        detector=rectified_batch.detector,
        detections=tuple(detections[tag_id] for tag_id in POSE_FIT_TAG_IDS),
    )
    fit_map = PlanarBoardTagMap(
        map_id=f"{tag_map.map_id}.pose-fit-0-3",
        board_frame=tag_map.board_frame,
        tag_plane_z_board_mm=tag_map.tag_plane_z_board_mm,
        tags=tuple(definitions[tag_id] for tag_id in POSE_FIT_TAG_IDS),
        source_sha256=tag_map.source_sha256,
    )
    observation = estimate_planar_board_pose(fit_batch, intrinsics, fit_map, config)
    used_ids = tuple(tag.tag_id for tag in observation.used_tags)
    if used_ids != POSE_FIT_TAG_IDS:
        raise FixedCameraBoardPoseError(
            "all ordered tags 0 through 3 must remain pose inliers"
        )

    held_out: list[HeldOutTagResidual] = []
    for tag_id in HELD_OUT_TAG_IDS:
        detection = detections[tag_id]
        predicted = _project(definitions[tag_id], observation, intrinsics)
        residuals = tuple(
            math.hypot(corner.x_px - expected[0], corner.y_px - expected[1])
            for corner, expected in zip(detection.corners_px, predicted, strict=True)
        )
        held_out.append(HeldOutTagResidual(tag_id, residuals))  # type: ignore[arg-type]

    configuration_sha256 = _canonical_hash(
        {
            "schema": "rocell.fixed_camera_board_pose_extractor_config.v1",
            "pose_fit_tag_ids": list(POSE_FIT_TAG_IDS),
            "held_out_tag_ids": list(HELD_OUT_TAG_IDS),
            "maximum_held_out_residual_px": limit,
            "estimator": config.to_dict(),
        }
    )
    return FixedCameraBoardPoseResult(
        full_detection_batch=rectified_batch,
        fit_observation=observation,
        full_tag_map_sha256=tag_map.content_hash,
        maximum_held_out_residual_px=limit,
        held_out_residuals=(held_out[0], held_out[1]),
        extractor_configuration_sha256=configuration_sha256,
        extractor_implementation_sha256=_implementation_sha256(),
    )


def extract_fixed_camera_board_pose(
    frame: FramePacket,
    detector: FrameTagDetector,
    rectifier: DetectionRectifier,
    intrinsics: PinholeIntrinsics,
    tag_map: PlanarBoardTagMap,
    *,
    estimator_config: PlanarPoseEstimatorConfig | None = None,
    maximum_held_out_residual_px: float = DEFAULT_MAXIMUM_HELD_OUT_RESIDUAL_PX,
) -> FixedCameraBoardPoseResult:
    """Run the frame-only detector, rectifier, and disjoint board-pose policy."""

    if not isinstance(frame, FramePacket):
        raise TypeError("frame must be FramePacket")
    raw = detector.detect(frame)
    if (
        raw.frame.jpeg_sha256 != frame.sha256
        or raw.frame.capture_id != frame.capture_id
    ):
        raise FixedCameraBoardPoseError("detector output binds a different frame")
    rectified = rectifier.rectify_detection_batch(raw)
    if rectified.frame != raw.frame:
        raise FixedCameraBoardPoseError("rectifier changed the frame binding")
    return estimate_fixed_camera_board_pose(
        rectified,
        intrinsics,
        tag_map,
        estimator_config=estimator_config,
        maximum_held_out_residual_px=maximum_held_out_residual_px,
    )


__all__ = [
    "DEFAULT_MAXIMUM_HELD_OUT_RESIDUAL_PX",
    "DetectionRectifier",
    "EXTRACTOR_ID",
    "EXTRACTOR_VERSION",
    "FixedCameraBoardPoseError",
    "FixedCameraBoardPoseResult",
    "FrameTagDetector",
    "HELD_OUT_TAG_IDS",
    "HeldOutTagResidual",
    "POSE_FIT_TAG_IDS",
    "REQUIRED_TAG_IDS",
    "estimate_fixed_camera_board_pose",
    "extract_fixed_camera_board_pose",
]
