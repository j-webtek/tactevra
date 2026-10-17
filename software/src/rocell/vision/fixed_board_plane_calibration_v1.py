"""Validated fixed-camera pixel-to-board calibration candidate.

This module consumes the retained RC03 planar mapping without promoting it to
an intrinsic, 3-D, tool, contact, or motion calibration.  It is deliberately a
small boundary: verify the exact stream/profile invariants, project a pixel to
the board plane, and report whether guarded localization may consume it.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
ACCEPTED_STATUS = "accepted-provisional-fixed-plane"
SUPPORTED_PROFILE = "no_attachment"
STYLUS_PROFILE = "stylus_attachment"
MAX_ARTIFACT_BYTES = 256 * 1024
MAX_RMS_ERROR_MM = 4.0
MAX_ERROR_MM = 6.0


class FixedBoardPlaneCalibrationError(ValueError):
    """The candidate artifact is malformed or unsafe for this use."""


def _strict_json(raw: bytes) -> dict[str, Any]:
    def pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise FixedBoardPlaneCalibrationError(
                    f"duplicate calibration field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                FixedBoardPlaneCalibrationError(
                    f"nonfinite calibration constant {item!r}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedBoardPlaneCalibrationError(
            "calibration must be UTF-8 JSON") from exc
    if type(value) is not dict:
        raise FixedBoardPlaneCalibrationError(
            "calibration must be a JSON object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedBoardPlaneCalibrationError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise FixedBoardPlaneCalibrationError(f"{label} must be finite")
    return result


def _matrix3(value: object, label: str) -> tuple[tuple[float, ...], ...]:
    if (not isinstance(value, list) or len(value) != 3
            or any(not isinstance(row, list) or len(row) != 3 for row in value)):
        raise FixedBoardPlaneCalibrationError(f"{label} must be 3 by 3")
    result = tuple(tuple(_number(item, label) for item in row) for row in value)
    determinant = (
        result[0][0] * (result[1][1] * result[2][2] - result[1][2] * result[2][1])
        - result[0][1] * (result[1][0] * result[2][2] - result[1][2] * result[2][0])
        + result[0][2] * (result[1][0] * result[2][1] - result[1][1] * result[2][0])
    )
    if abs(determinant) <= 1e-12:
        raise FixedBoardPlaneCalibrationError(f"{label} is singular")
    return result


@dataclass(frozen=True, slots=True)
class CameraModeV1:
    backend: str
    width: int
    height: int
    pixel_format: str
    fps: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CameraModeV1":
        if set(value) != {"backend", "width", "height", "pixel_format", "fps"}:
            raise FixedBoardPlaneCalibrationError("camera mode fields differ")
        if (type(value["width"]) is not int or type(value["height"]) is not int
                or value["width"] <= 0 or value["height"] <= 0):
            raise FixedBoardPlaneCalibrationError("camera dimensions are invalid")
        if not isinstance(value["backend"], str) or not value["backend"]:
            raise FixedBoardPlaneCalibrationError("camera backend is invalid")
        if not isinstance(value["pixel_format"], str) or not value["pixel_format"]:
            raise FixedBoardPlaneCalibrationError("pixel format is invalid")
        fps = _number(value["fps"], "camera fps")
        if fps <= 0:
            raise FixedBoardPlaneCalibrationError("camera fps must be positive")
        return cls(value["backend"], value["width"], value["height"],
                   value["pixel_format"], fps)


@dataclass(frozen=True, slots=True)
class FixedBoardPlaneCalibrationV1:
    artifact_sha256: str
    camera_mode: CameraModeV1
    board_width_mm: float
    board_depth_mm: float
    pixel_to_board: tuple[tuple[float, ...], ...]
    rms_error_mm: float
    maximum_error_mm: float
    world_tags_used: tuple[int, ...]
    profiles: Mapping[str, Mapping[str, Any]]
    source: Mapping[str, Any]

    def project_pixel(self, x_px: float, y_px: float) -> tuple[float, float]:
        x = _number(x_px, "x_px")
        y = _number(y_px, "y_px")
        if not (0 <= x < self.camera_mode.width
                and 0 <= y < self.camera_mode.height):
            raise FixedBoardPlaneCalibrationError(
                "pixel lies outside the calibrated camera frame")
        h = self.pixel_to_board
        scale = h[2][0] * x + h[2][1] * y + h[2][2]
        if abs(scale) <= 1e-12:
            raise FixedBoardPlaneCalibrationError(
                "pixel projects to infinity on the board plane")
        board_x = (h[0][0] * x + h[0][1] * y + h[0][2]) / scale
        board_y = (h[1][0] * x + h[1][1] * y + h[1][2]) / scale
        if not (math.isfinite(board_x) and math.isfinite(board_y)):
            raise FixedBoardPlaneCalibrationError("projection is nonfinite")
        if not (0 <= board_x <= self.board_width_mm
                and 0 <= board_y <= self.board_depth_mm):
            raise FixedBoardPlaneCalibrationError(
                "pixel lies outside the calibrated board plane")
        return board_x, board_y

    def assess(
        self, *, observed_mode: CameraModeV1, profile: str,
        camera_and_board_fixed: bool,
    ) -> "FixedBoardPlaneAssessmentV1":
        blockers: list[str] = []
        if observed_mode != self.camera_mode:
            blockers.append("CAMERA_MODE_DRIFT")
        if not camera_and_board_fixed:
            blockers.append("CAMERA_OR_BOARD_MOVED")
        if profile not in self.profiles:
            blockers.append("UNKNOWN_TOOL_PROFILE")
        elif profile == STYLUS_PROFILE:
            blockers.append("STYLUS_TCP_AND_CONTACT_PROFILE_MISSING")
        elif profile != SUPPORTED_PROFILE:
            blockers.append("TOOL_PROFILE_NOT_ADMITTED")
        return FixedBoardPlaneAssessmentV1(
            calibration_sha256=self.artifact_sha256,
            profile=profile,
            blockers=tuple(blockers),
        )


@dataclass(frozen=True, slots=True)
class FixedBoardPlaneAssessmentV1:
    calibration_sha256: str
    profile: str
    blockers: tuple[str, ...]

    @property
    def guarded_localization_ready(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rocell.fixed_board_plane_assessment.v1",
            "calibration_sha256": self.calibration_sha256,
            "profile": self.profile,
            "guarded_localization_ready": self.guarded_localization_ready,
            "open_loop_contact_authorized": False,
            "motion_authorized": False,
            "blockers": list(self.blockers),
        }


def parse_fixed_board_plane_calibration_v1(
    document: Mapping[str, Any], *, artifact_sha256: str,
) -> FixedBoardPlaneCalibrationV1:
    if (not isinstance(artifact_sha256, str) or len(artifact_sha256) != 64
            or any(item not in "0123456789abcdef" for item in artifact_sha256)):
        raise FixedBoardPlaneCalibrationError(
            "artifact_sha256 must be a lowercase SHA-256 digest")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise FixedBoardPlaneCalibrationError("unsupported schema version")
    if document.get("status") != ACCEPTED_STATUS:
        raise FixedBoardPlaneCalibrationError("calibration is not provisionally accepted")
    if document.get("safe_for_runtime_board_plane") is not True:
        raise FixedBoardPlaneCalibrationError("board-plane runtime use is disabled")
    if document.get("safe_for_open_loop_contact") is not False:
        raise FixedBoardPlaneCalibrationError("open-loop contact must remain disabled")
    mode = document.get("camera_mode")
    board = document.get("board")
    fit = document.get("fit")
    profiles = document.get("profiles")
    tags = document.get("world_tags_used")
    if not all(isinstance(item, Mapping) for item in (mode, board, fit, profiles)):
        raise FixedBoardPlaneCalibrationError("required calibration objects are missing")
    if (not isinstance(tags, list) or len(tags) < 3
            or any(type(item) is not int for item in tags)
            or len(set(tags)) != len(tags)):
        raise FixedBoardPlaneCalibrationError("at least three unique world tags are required")
    if set(profiles) != {SUPPORTED_PROFILE, STYLUS_PROFILE}:
        raise FixedBoardPlaneCalibrationError("tool profiles differ from the closed set")
    if any(not isinstance(value, Mapping) for value in profiles.values()):
        raise FixedBoardPlaneCalibrationError("tool profile records are invalid")
    if profiles[SUPPORTED_PROFILE].get("status") != (
            "ready for guarded camera-feedback integration"):
        raise FixedBoardPlaneCalibrationError("bare-jaw profile is not ready")
    if profiles[STYLUS_PROFILE].get("status") != "pending attachment calibration":
        raise FixedBoardPlaneCalibrationError("stylus profile must remain pending")
    rms = _number(fit.get("rms_error_mm"), "rms_error_mm")
    maximum = _number(fit.get("max_error_mm"), "max_error_mm")
    if rms > MAX_RMS_ERROR_MM or maximum > MAX_ERROR_MM:
        raise FixedBoardPlaneCalibrationError("planar residual exceeds provisional policy")
    width = _number(board.get("width_mm"), "board width")
    depth = _number(board.get("depth_mm"), "board depth")
    if width <= 0 or depth <= 0 or board.get("z_plane_mm") != 0.0:
        raise FixedBoardPlaneCalibrationError("board geometry is invalid")
    return FixedBoardPlaneCalibrationV1(
        artifact_sha256=artifact_sha256,
        camera_mode=CameraModeV1.from_mapping(mode),
        board_width_mm=width,
        board_depth_mm=depth,
        pixel_to_board=_matrix3(
            document.get("pixel_to_board_homography"),
            "pixel_to_board_homography"),
        rms_error_mm=rms,
        maximum_error_mm=maximum,
        world_tags_used=tuple(tags),
        profiles=profiles,
        source=document,
    )


def load_fixed_board_plane_calibration_v1(
    path: Path,
) -> FixedBoardPlaneCalibrationV1:
    try:
        if path.is_symlink() or not path.is_file():
            raise FixedBoardPlaneCalibrationError(
                "calibration path must be a regular file")
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise FixedBoardPlaneCalibrationError("calibration artifact is too large")
        raw = path.read_bytes()
    except OSError as exc:
        raise FixedBoardPlaneCalibrationError(
            f"could not read calibration: {exc}") from exc
    return parse_fixed_board_plane_calibration_v1(
        _strict_json(raw), artifact_sha256=hashlib.sha256(raw).hexdigest())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assess one fixed board-plane calibration candidate")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--profile", required=True,
                        choices=(SUPPORTED_PROFILE, STYLUS_PROFILE))
    parser.add_argument("--backend", default="DirectShow")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--pixel-format", default="YUY2")
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument(
        "--camera-and-board-fixed", action="store_true",
        help="assert the camera and board have not moved since capture")
    args = parser.parse_args(argv)
    calibration = load_fixed_board_plane_calibration_v1(args.artifact)
    assessment = calibration.assess(
        observed_mode=CameraModeV1(
            args.backend, args.width, args.height, args.pixel_format, args.fps),
        profile=args.profile,
        camera_and_board_fixed=args.camera_and_board_fixed,
    )
    print(json.dumps(assessment.to_dict(), sort_keys=True, indent=2))
    return 0 if assessment.guarded_localization_ready else 2


__all__ = [
    "ACCEPTED_STATUS", "MAX_ERROR_MM", "MAX_RMS_ERROR_MM",
    "STYLUS_PROFILE", "SUPPORTED_PROFILE", "CameraModeV1",
    "FixedBoardPlaneAssessmentV1", "FixedBoardPlaneCalibrationError",
    "FixedBoardPlaneCalibrationV1", "load_fixed_board_plane_calibration_v1",
    "parse_fixed_board_plane_calibration_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
