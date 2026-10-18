"""Compose one native fixed-camera frame into passive calibration evidence.

This module closes the offline seam between the read-only acquisition bracket,
the six-tag board-pose extractor, and the existing passive camera/robot capture
compiler.  It deliberately has no camera or robot provider surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol

from rocell.vision.camera import FramePacket
from rocell.vision.fixed_camera_board_pose_extractor_v1 import (
    DetectionRectifier,
    FixedCameraBoardPoseResult,
    FrameTagDetector,
    extract_fixed_camera_board_pose,
)
from rocell.vision.planar_pose_estimator import PinholeIntrinsics, PlanarBoardTagMap

from .fixed_camera_robot_acquisition_v1 import (
    CalibrationCaptureBracketV1,
    build_capture_input_v1,
)
from .fixed_camera_robot_calibration_capture_v1 import compile_capture


NATIVE_WIDTH_PX = 5472
NATIVE_HEIGHT_PX = 3648
REVIEW_STATUS = "REVIEWED_PHYSICAL_FIXED_CAMERA_INTRINSICS"


class FixedCameraCalibrationObservationError(ValueError):
    """The native-frame observation composition is inconsistent or incomplete."""


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
        raise FixedCameraCalibrationObservationError(
            "observation evidence is not canonical JSON"
        ) from exc


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraCalibrationObservationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FixedCameraCalibrationObservationError(f"{label} must be nonempty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ReviewedNativeIntrinsicsV1:
    """Reviewed physical calibration binding for the exact full B0477 frame."""

    calibration_record_id: str
    camera_identity_sha256: str
    settings_sha256: str
    intrinsics: PinholeIntrinsics
    tag_map_sha256: str
    distortion_model: str
    rectification_configuration_sha256: str
    review_record_sha256: str
    physical_calibration_valid: bool
    native_mode_verified: bool
    full_frame_without_crop_or_rescale: bool
    status: str = REVIEW_STATUS

    def __post_init__(self) -> None:
        _text(self.calibration_record_id, "calibration_record_id")
        if self.status != REVIEW_STATUS:
            raise FixedCameraCalibrationObservationError(
                "intrinsics binding is not independently reviewed"
            )
        for value, label in (
            (self.camera_identity_sha256, "camera_identity_sha256"),
            (self.settings_sha256, "settings_sha256"),
            (self.tag_map_sha256, "tag_map_sha256"),
            (
                self.rectification_configuration_sha256,
                "rectification_configuration_sha256",
            ),
            (self.review_record_sha256, "review_record_sha256"),
        ):
            _digest(value, label)
        if not isinstance(self.intrinsics, PinholeIntrinsics):
            raise TypeError("intrinsics must be PinholeIntrinsics")
        if (self.intrinsics.width_px, self.intrinsics.height_px) != (
            NATIVE_WIDTH_PX,
            NATIVE_HEIGHT_PX,
        ):
            raise FixedCameraCalibrationObservationError(
                "reviewed intrinsics must describe the exact 5472 x 3648 native mode"
            )
        if self.intrinsics.pixel_space != "UNDISTORTED_PINHOLE_PIXELS":
            raise FixedCameraCalibrationObservationError(
                "reviewed intrinsics must use undistorted pinhole pixels"
            )
        if self.distortion_model != "OPENCV_RATIONAL_POLYNOMIAL_8":
            raise FixedCameraCalibrationObservationError(
                "reviewed intrinsics must retain the qualified distortion model"
            )
        gates = (
            self.physical_calibration_valid,
            self.native_mode_verified,
            self.full_frame_without_crop_or_rescale,
        )
        if any(type(value) is not bool for value in gates) or not all(gates):
            raise FixedCameraCalibrationObservationError(
                "all physical intrinsics and native-frame gates must be true"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "rocell.reviewed_native_fixed_camera_intrinsics.v1",
            "status": self.status,
            "calibration_record_id": self.calibration_record_id,
            "camera_identity_sha256": self.camera_identity_sha256,
            "settings_sha256": self.settings_sha256,
            "intrinsics_sha256": self.intrinsics.content_hash,
            "intrinsics_source_sha256": self.intrinsics.source_sha256,
            "width_px": self.intrinsics.width_px,
            "height_px": self.intrinsics.height_px,
            "pixel_space": self.intrinsics.pixel_space,
            "tag_map_sha256": self.tag_map_sha256,
            "distortion_model": self.distortion_model,
            "rectification_configuration_sha256": (
                self.rectification_configuration_sha256
            ),
            "review_record_sha256": self.review_record_sha256,
            "physical_calibration_valid": self.physical_calibration_valid,
            "native_mode_verified": self.native_mode_verified,
            "full_frame_without_crop_or_rescale": (
                self.full_frame_without_crop_or_rescale
            ),
            "physical_authority": "NONE",
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


class BareJawReferenceObserver(Protocol):
    """Offline detector for the calibrated bare-jaw reference in one frame."""

    def observe(
        self,
        frame: FramePacket,
        board_pose: FixedCameraBoardPoseResult,
    ) -> Mapping[str, Any]: ...


class ReviewedDetectionRectifier(DetectionRectifier, Protocol):
    """Rectifier whose exact configuration can be matched to review evidence."""

    @property
    def configuration_sha256(self) -> str: ...


@dataclass(frozen=True, slots=True)
class FixedCameraCalibrationObservationV1:
    """Complete offline composition and existing compiler result."""

    intrinsics_review_sha256: str
    board_pose: FixedCameraBoardPoseResult
    tool_reference: Mapping[str, Any]
    capture_input: Mapping[str, Any]
    compiled_capture: Mapping[str, Any]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "rocell.fixed_camera_calibration_observation.v1",
            "status": "PASSIVE_NATIVE_FRAME_OBSERVATION_COMPILED",
            "intrinsics_review_sha256": self.intrinsics_review_sha256,
            "board_pose": self.board_pose.to_dict(),
            "tool_reference": dict(self.tool_reference),
            "capture_input": dict(self.capture_input),
            "compiled_capture": dict(self.compiled_capture),
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "controller_commands": [],
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
            },
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


def compile_fixed_camera_calibration_observation_v1(
    bracket: CalibrationCaptureBracketV1,
    intrinsics_review: ReviewedNativeIntrinsicsV1,
    detector: FrameTagDetector,
    rectifier: ReviewedDetectionRectifier,
    tag_map: PlanarBoardTagMap,
    bare_jaw_observer: BareJawReferenceObserver,
    *,
    role: str,
) -> FixedCameraCalibrationObservationV1:
    """Join one retained native frame to board, tool, and feedback evidence."""

    if not isinstance(bracket, CalibrationCaptureBracketV1):
        raise TypeError("bracket must be CalibrationCaptureBracketV1")
    if not isinstance(intrinsics_review, ReviewedNativeIntrinsicsV1):
        raise TypeError("intrinsics_review must be ReviewedNativeIntrinsicsV1")
    if not isinstance(tag_map, PlanarBoardTagMap):
        raise TypeError("tag_map must be PlanarBoardTagMap")
    frame = bracket.frame
    if (frame.width_px, frame.height_px) != (NATIVE_WIDTH_PX, NATIVE_HEIGHT_PX):
        raise FixedCameraCalibrationObservationError(
            "calibration observation requires the complete native 5472 x 3648 frame"
        )
    if bracket.camera_identity_sha256 != intrinsics_review.camera_identity_sha256:
        raise FixedCameraCalibrationObservationError(
            "frame camera identity differs from reviewed intrinsics"
        )
    if frame.settings_hash != intrinsics_review.settings_sha256:
        raise FixedCameraCalibrationObservationError(
            "frame settings differ from reviewed intrinsics"
        )
    if tag_map.content_hash != intrinsics_review.tag_map_sha256:
        raise FixedCameraCalibrationObservationError(
            "six-tag map differs from reviewed intrinsics binding"
        )
    rectifier_sha256 = getattr(rectifier, "configuration_sha256", None)
    if (
        _digest(rectifier_sha256, "rectifier configuration")
        != intrinsics_review.rectification_configuration_sha256
    ):
        raise FixedCameraCalibrationObservationError(
            "rectifier configuration differs from reviewed intrinsics"
        )

    board_pose = extract_fixed_camera_board_pose(
        frame,
        detector,
        rectifier,
        intrinsics_review.intrinsics,
        tag_map,
    )
    tool_reference = bare_jaw_observer.observe(frame, board_pose)
    if not isinstance(tool_reference, Mapping):
        raise FixedCameraCalibrationObservationError(
            "bare-jaw observer must return a mapping"
        )
    capture_input = build_capture_input_v1(
        bracket,
        role=role,
        board_pose=board_pose.capture_board_pose(),
        tool_reference=tool_reference,
    )
    compiled = compile_capture(capture_input)
    return FixedCameraCalibrationObservationV1(
        intrinsics_review_sha256=intrinsics_review.sha256,
        board_pose=board_pose,
        tool_reference=dict(tool_reference),
        capture_input=capture_input,
        compiled_capture=compiled,
    )


__all__ = [
    "BareJawReferenceObserver",
    "FixedCameraCalibrationObservationError",
    "FixedCameraCalibrationObservationV1",
    "NATIVE_HEIGHT_PX",
    "NATIVE_WIDTH_PX",
    "REVIEW_STATUS",
    "ReviewedDetectionRectifier",
    "ReviewedNativeIntrinsicsV1",
    "compile_fixed_camera_calibration_observation_v1",
]
