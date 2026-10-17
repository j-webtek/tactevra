"""Derive bounded image-space key feedback windows from a reviewed keyboard ROI.

This module maps the nominal keyboard layout into the retained camera frame. Its
output tells a later image detector where to look. It never promotes nominal
pixels into measured key centers, board targets, motion, descent, or contact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.vision.fixed_camera_keyboard_registration_v1 import (
    CORNER_ORDER,
    STYLUS_PROFILE,
    SUPPORTED_PROFILE,
    FixedCameraKeyboardRegistrationError,
    estimate_files as estimate_registration_files,
)


MAX_INPUT_BYTES = 256 * 1024
SEARCH_MARGIN_PX = 3.0
EXPECTED_KEY_COUNT = 46


class FixedCameraKeyFeedbackRoiError(ValueError):
    """The key-feedback ROI inputs are invalid or internally inconsistent."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        if path.is_symlink() or not path.is_file():
            raise FixedCameraKeyFeedbackRoiError("input path must be a regular file")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise FixedCameraKeyFeedbackRoiError("input JSON is too large")
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyFeedbackRoiError(f"could not read input JSON: {exc}") from exc
    if type(document) is not dict:
        raise FixedCameraKeyFeedbackRoiError("input JSON must be an object")
    return document, raw


def _xy(value: object, label: str) -> tuple[float, float]:
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(item, bool) or not isinstance(item, (int, float))
                   or not math.isfinite(float(item)) for item in value)):
        raise FixedCameraKeyFeedbackRoiError(f"{label} must be a finite XY pair")
    return float(value[0]), float(value[1])


def _positive_xy(value: object, label: str) -> tuple[float, float]:
    result = _xy(value, label)
    if result[0] <= 0 or result[1] <= 0:
        raise FixedCameraKeyFeedbackRoiError(f"{label} must be positive")
    return result


def _homography(local_points: list[tuple[float, float]],
                pixel_points: list[tuple[float, float]]):
    import numpy as np

    rows: list[list[float]] = []
    values: list[float] = []
    for (x_value, y_value), (u_value, v_value) in zip(local_points, pixel_points):
        rows.append([x_value, y_value, 1.0, 0.0, 0.0, 0.0,
                     -u_value * x_value, -u_value * y_value])
        values.append(u_value)
        rows.append([0.0, 0.0, 0.0, x_value, y_value, 1.0,
                     -v_value * x_value, -v_value * y_value])
        values.append(v_value)
    try:
        solution = np.linalg.solve(np.asarray(rows, dtype=float),
                                   np.asarray(values, dtype=float))
    except np.linalg.LinAlgError as exc:
        raise FixedCameraKeyFeedbackRoiError(
            "keyboard corners do not define a projective map") from exc
    return np.append(solution, 1.0).reshape(3, 3)


def _project(matrix, point: tuple[float, float]) -> tuple[float, float]:
    import numpy as np

    projected = matrix @ np.asarray([point[0], point[1], 1.0], dtype=float)
    if abs(float(projected[2])) < 1e-12:
        raise FixedCameraKeyFeedbackRoiError("projective key point is singular")
    result = projected[:2] / projected[2]
    if not np.all(np.isfinite(result)):
        raise FixedCameraKeyFeedbackRoiError("projective key point is not finite")
    return float(result[0]), float(result[1])


def _key_layout(keyboard: Mapping[str, Any]) -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
    default_extent = _positive_xy(keyboard.get("key_half_extent_mm"),
                                  "default key half extent")
    keys: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    rows = keyboard.get("rows")
    if not isinstance(rows, list):
        raise FixedCameraKeyFeedbackRoiError("keyboard rows are missing")
    for row in rows:
        if not isinstance(row, Mapping):
            raise FixedCameraKeyFeedbackRoiError("keyboard row is invalid")
        names = row.get("key_ids")
        if not isinstance(names, list) or any(not isinstance(name, str) or not name
                                               for name in names):
            raise FixedCameraKeyFeedbackRoiError("keyboard row key IDs are invalid")
        first = _xy(row.get("first_center_xy_mm"), "row first center")
        step = _xy(row.get("step_xy_mm"), "row step")
        for index, name in enumerate(names):
            if name in keys:
                raise FixedCameraKeyFeedbackRoiError(f"duplicate key ID: {name}")
            keys[name] = ((first[0] + index * step[0],
                           first[1] + index * step[1]), default_extent)
    explicit = keyboard.get("explicit_targets")
    if not isinstance(explicit, Mapping):
        raise FixedCameraKeyFeedbackRoiError("explicit key targets are missing")
    for name, item in explicit.items():
        if not isinstance(name, str) or not isinstance(item, Mapping) or name in keys:
            raise FixedCameraKeyFeedbackRoiError("explicit key target is invalid")
        keys[name] = (_xy(item.get("center_xy_mm"), f"{name} center"),
                      _positive_xy(item.get("half_extent_mm"), f"{name} half extent"))
    if len(keys) != EXPECTED_KEY_COUNT:
        raise FixedCameraKeyFeedbackRoiError(
            f"expected {EXPECTED_KEY_COUNT} unique keyboard targets, got {len(keys)}")
    return keys


def build_fixed_camera_key_feedback_roi_v1(
    registration_document: Mapping[str, Any],
    registration_assessment: Mapping[str, Any],
    profile_document: Mapping[str, Any], *,
    profile: str = SUPPORTED_PROFILE,
) -> dict[str, Any]:
    """Build nominal camera search windows after registration validation."""
    import numpy as np

    frame = registration_document.get("frame")
    corners = registration_document.get("keyboard_corners_px")
    keyboard = profile_document.get("keyboard")
    if not all(isinstance(item, Mapping) for item in (frame, corners, keyboard)):
        raise FixedCameraKeyFeedbackRoiError("camera, corner, or keyboard data is missing")
    if registration_assessment.get("schema") != (
            "rocell.fixed_camera_keyboard_registration_assessment.v1"):
        raise FixedCameraKeyFeedbackRoiError("registration assessment contract differs")
    if registration_assessment.get("profile") != profile:
        raise FixedCameraKeyFeedbackRoiError("registration profile differs")
    if registration_assessment.get("source_frame_sha256") != frame.get("sha256"):
        raise FixedCameraKeyFeedbackRoiError("source frame binding differs")

    width_px = frame.get("width_px")
    height_px = frame.get("height_px")
    if type(width_px) is not int or type(height_px) is not int or min(width_px, height_px) <= 0:
        raise FixedCameraKeyFeedbackRoiError("camera dimensions are invalid")
    dimensions = registration_document.get("housing_dimensions_mm")
    if not isinstance(dimensions, list) or len(dimensions) != 3:
        raise FixedCameraKeyFeedbackRoiError("keyboard dimensions are invalid")
    width_mm = float(dimensions[0])
    depth_mm = float(dimensions[1])
    local_corners = [(0.0, 0.0), (width_mm, 0.0),
                     (width_mm, depth_mm), (0.0, depth_mm)]
    pixel_corners = [_xy(corners.get(name), name) for name in CORNER_ORDER]
    matrix = _homography(local_corners, pixel_corners)
    reprojection = [math.dist(_project(matrix, local), pixel)
                    for local, pixel in zip(local_corners, pixel_corners)]
    if max(reprojection) > 1e-6:
        raise FixedCameraKeyFeedbackRoiError("corner projective map is incoherent")

    windows: dict[str, Any] = {}
    for name, (center, extent) in _key_layout(keyboard).items():
        x_value, y_value = center
        half_x, half_y = extent
        if (x_value - half_x < 0 or x_value + half_x > width_mm
                or y_value - half_y < 0 or y_value + half_y > depth_mm):
            raise FixedCameraKeyFeedbackRoiError(
                f"nominal key footprint lies outside keyboard housing: {name}")
        local_polygon = [
            (x_value - half_x, y_value - half_y),
            (x_value + half_x, y_value - half_y),
            (x_value + half_x, y_value + half_y),
            (x_value - half_x, y_value + half_y),
        ]
        polygon = [_project(matrix, point) for point in local_polygon]
        center_px = _project(matrix, center)
        x_values = [point[0] for point in polygon]
        y_values = [point[1] for point in polygon]
        rectangle = [
            max(0.0, min(x_values) - SEARCH_MARGIN_PX),
            max(0.0, min(y_values) - SEARCH_MARGIN_PX),
            min(float(width_px - 1), max(x_values) + SEARCH_MARGIN_PX),
            min(float(height_px - 1), max(y_values) + SEARCH_MARGIN_PX),
        ]
        if not (rectangle[0] <= center_px[0] <= rectangle[2]
                and rectangle[1] <= center_px[1] <= rectangle[3]):
            raise FixedCameraKeyFeedbackRoiError(
                f"search rectangle excludes nominal center: {name}")
        windows[name] = {
            "nominal_center_pixel_xy": [round(value, 3) for value in center_px],
            "nominal_key_polygon_pixel_xy": [
                [round(value, 3) for value in point] for point in polygon],
            "search_rect_pixel_xyxy": [round(value, 3) for value in rectangle],
        }

    profile_blockers = list(registration_assessment.get("profile_blockers", []))
    blockers = ["INDEPENDENT_KEY_CENTER_OBSERVATIONS_MISSING"]
    if not registration_assessment.get("individual_key_localization_ready", False):
        blockers.append("BOARD_SPACE_INDIVIDUAL_KEY_LIMIT_NOT_MET")
    blockers.extend(profile_blockers)
    windows_ready = (profile == SUPPORTED_PROFILE
                     and registration_assessment.get(
                         "keyboard_region_localization_ready") is True)
    return {
        "schema": "rocell.fixed_camera_key_feedback_roi.v1",
        "status": "IMAGE_SEARCH_WINDOWS_ONLY_NOT_MOTION_AUTHORITY",
        "registration_input_sha256": registration_assessment["input_sha256"],
        "calibration_sha256": registration_assessment["calibration_sha256"],
        "profile_sha256": registration_assessment["profile_sha256"],
        "source_frame_sha256": registration_assessment["source_frame_sha256"],
        "source_frame_bytes_verified": registration_assessment[
            "source_frame_bytes_verified"],
        "profile": profile,
        "camera_width_px": width_px,
        "camera_height_px": height_px,
        "keyboard_corner_order": list(CORNER_ORDER),
        "keyboard_polygon_pixel_xy": [list(point) for point in pixel_corners],
        "local_keyboard_to_pixel_homography": [
            [round(float(value), 12) for value in row] for row in np.asarray(matrix)],
        "search_margin_px": SEARCH_MARGIN_PX,
        "key_feedback_windows": windows,
        "key_feedback_window_count": len(windows),
        "image_space_feedback_windows_ready": windows_ready,
        "independent_key_center_observations_present": False,
        "individual_key_localization_ready": False,
        "board_space_motion_targets_emitted": False,
        "board_to_robot_transform_verified": False,
        "physical_clearance_verified": False,
        "contact_authorized": False,
        "motion_authorized": False,
        "blockers": blockers,
        "limitations": [
            "Each window is a nominal projective search region derived from reviewed housing corners, not an observed key center.",
            "The projective map is image-space only and does not correct the elevated keyboard plane in board coordinates.",
            "A later detector must supply independent key-center or row-feature observations before individual-key localization can be reconsidered.",
        ],
    }


def estimate_files(
    registration_input_path: Path, calibration_path: Path,
    profile_path: Path, *, profile: str = SUPPORTED_PROFILE,
    source_frame_path: Path | None = None,
) -> dict[str, Any]:
    registration_document, _ = _load_json(Path(registration_input_path))
    profile_document, _ = _load_json(Path(profile_path))
    try:
        registration = estimate_registration_files(
            Path(registration_input_path), Path(calibration_path), Path(profile_path),
            profile=profile, source_frame_path=source_frame_path)
    except FixedCameraKeyboardRegistrationError as exc:
        raise FixedCameraKeyFeedbackRoiError(str(exc)) from exc
    return build_fixed_camera_key_feedback_roi_v1(
        registration_document, registration, profile_document, profile=profile)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build bounded per-key image search windows")
    parser.add_argument("registration", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("targets", type=Path)
    parser.add_argument("--profile", choices=(SUPPORTED_PROFILE, STYLUS_PROFILE),
                        default=SUPPORTED_PROFILE)
    parser.add_argument("--source-frame", type=Path)
    args = parser.parse_args(argv)
    result = estimate_files(
        args.registration, args.calibration, args.targets,
        profile=args.profile, source_frame_path=args.source_frame)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["image_space_feedback_windows_ready"] else 2


__all__ = [
    "EXPECTED_KEY_COUNT", "FixedCameraKeyFeedbackRoiError", "SEARCH_MARGIN_PX",
    "build_fixed_camera_key_feedback_roi_v1", "estimate_files",
]


if __name__ == "__main__":
    raise SystemExit(main())
