"""Register a keyboard region from one held-out fixed-camera frame.

The input binds a retained frame, the accepted provisional board-plane map,
and the nominal keyboard profile.  The result is useful for a camera ROI and
nominal target overlays.  It deliberately does not authorize individual-key
localization, motion, descent, or contact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.vision.fixed_board_plane_calibration_v1 import (
    CameraModeV1,
    FixedBoardPlaneCalibrationV1,
    load_fixed_board_plane_calibration_v1,
)


MAX_INPUT_BYTES = 256 * 1024
SUPPORTED_PROFILE = "no_attachment"
STYLUS_PROFILE = "stylus_attachment"
CORNER_ORDER = ("front_left", "front_right", "rear_right", "rear_left")


class FixedCameraKeyboardRegistrationError(ValueError):
    """The registration input or its bound evidence is invalid."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _xy(value: object, label: str) -> tuple[float, float]:
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(item, bool) or not isinstance(item, (int, float))
                   or not math.isfinite(float(item)) for item in value)):
        raise FixedCameraKeyboardRegistrationError(
            f"{label} must be a finite XY pair")
    return float(value[0]), float(value[1])


def _positive(value: object, label: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) <= 0):
        raise FixedCameraKeyboardRegistrationError(
            f"{label} must be a positive finite number")
    return float(value)


def _digest(value: object, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise FixedCameraKeyboardRegistrationError(
            f"{label} must be a lowercase SHA-256 digest")
    return value


def _load_json(path: Path, *, maximum_bytes: int = MAX_INPUT_BYTES) -> tuple[dict, bytes]:
    try:
        if path.is_symlink() or not path.is_file():
            raise FixedCameraKeyboardRegistrationError(
                "registration path must be a regular file")
        if path.stat().st_size > maximum_bytes:
            raise FixedCameraKeyboardRegistrationError(
                "registration artifact is too large")
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardRegistrationError(
            f"could not read registration JSON: {exc}") from exc
    if type(document) is not dict:
        raise FixedCameraKeyboardRegistrationError(
            "registration JSON must be an object")
    return document, raw


def estimate_fixed_camera_keyboard_registration_v1(
    document: Mapping[str, Any], *, input_sha256: str,
    calibration: FixedBoardPlaneCalibrationV1,
    calibration_sha256: str, profile_document: Mapping[str, Any],
    profile_sha256: str, profile: str = SUPPORTED_PROFILE,
    source_frame_verified: bool = False,
) -> dict[str, Any]:
    import numpy as np

    _digest(input_sha256, "input_sha256")
    _digest(calibration_sha256, "calibration_sha256")
    _digest(profile_sha256, "profile_sha256")
    if (document.get("schema") !=
            "rocell.fixed_camera_keyboard_registration_input.v1"
            or document.get("status") !=
            "MANUALLY_REVIEWED_FIXED_CAMERA_ESTIMATE_ONLY"
            or document.get("board_frame") !=
            "RC03_B_FRONT_LEFT_X_RIGHT_Y_REAR_MM"):
        raise FixedCameraKeyboardRegistrationError(
            "unexpected fixed-camera registration contract")

    frame = document.get("frame")
    bindings = document.get("bindings")
    thresholds = document.get("thresholds")
    if not all(isinstance(item, Mapping)
               for item in (frame, bindings, thresholds)):
        raise FixedCameraKeyboardRegistrationError(
            "registration objects are missing")
    if (frame.get("width_px") != calibration.camera_mode.width
            or frame.get("height_px") != calibration.camera_mode.height):
        raise FixedCameraKeyboardRegistrationError(
            "source frame dimensions differ from calibration")
    mode = frame.get("camera_mode")
    if not isinstance(mode, Mapping):
        raise FixedCameraKeyboardRegistrationError("camera mode is missing")
    if CameraModeV1.from_mapping(mode) != calibration.camera_mode:
        raise FixedCameraKeyboardRegistrationError(
            "source camera mode differs from calibration")
    _digest(frame.get("sha256"), "source frame digest")
    if type(frame.get("bytes")) is not int or frame["bytes"] <= 0:
        raise FixedCameraKeyboardRegistrationError(
            "source frame byte length is invalid")

    board_binding = bindings.get("board_plane_calibration")
    target_binding = bindings.get("target_profile")
    if not isinstance(board_binding, Mapping) or not isinstance(target_binding, Mapping):
        raise FixedCameraKeyboardRegistrationError("evidence bindings are missing")
    if (_digest(board_binding.get("sha256"), "calibration binding")
            != calibration_sha256):
        raise FixedCameraKeyboardRegistrationError(
            "board calibration digest differs")
    if (_digest(target_binding.get("sha256"), "profile binding")
            != profile_sha256):
        raise FixedCameraKeyboardRegistrationError("target profile digest differs")

    keyboard = profile_document.get("keyboard")
    if (not isinstance(keyboard, Mapping)
            or keyboard.get("profile_id") != target_binding.get("profile_id")):
        raise FixedCameraKeyboardRegistrationError(
            "keyboard target profile differs")
    dimensions = document.get("housing_dimensions_mm")
    if (not isinstance(dimensions, list) or len(dimensions) != 3
            or [_positive(item, "housing dimension") for item in dimensions]
            != [float(item) for item in keyboard.get("device_size_mm", [])]):
        raise FixedCameraKeyboardRegistrationError(
            "housing dimensions differ from target profile")

    world_observed = document.get("detected_world_tag_centers_px")
    station_observed = document.get("detected_station_tag_centers_px")
    world_expected = calibration.source.get("world_tag_centers_mm")
    station_expected = calibration.source.get("station_tag_audit")
    if not all(isinstance(item, Mapping) for item in (
            world_observed, station_observed, world_expected, station_expected)):
        raise FixedCameraKeyboardRegistrationError(
            "held-out tag observations are missing")
    if set(world_observed) != {str(item) for item in calibration.world_tags_used}:
        raise FixedCameraKeyboardRegistrationError(
            "held-out world tags differ from calibration tags")
    world_errors: dict[str, float] = {}
    for tag, pixel in world_observed.items():
        projected = calibration.project_pixel(*_xy(pixel, f"world tag {tag}"))
        expected = _xy(world_expected.get(tag), f"world tag {tag} expected")
        world_errors[tag] = math.dist(projected, expected)
    world_limit = _positive(
        thresholds.get("max_world_tag_center_error_mm"), "world tag limit")
    if max(world_errors.values()) > world_limit:
        raise FixedCameraKeyboardRegistrationError(
            "held-out world-tag residual exceeds policy")

    if set(station_observed) != set(station_expected):
        raise FixedCameraKeyboardRegistrationError(
            "held-out station tags differ from calibration audit")
    station_drifts: dict[str, float] = {}
    for tag, pixel in station_observed.items():
        observed = _xy(pixel, f"station tag {tag}")
        expected = _xy(station_expected[tag].get("observed_center_px"),
                       f"station tag {tag} baseline")
        station_drifts[tag] = math.dist(observed, expected)
    station_limit = _positive(
        thresholds.get("max_station_tag_center_drift_px"), "station drift limit")
    if max(station_drifts.values()) > station_limit:
        raise FixedCameraKeyboardRegistrationError(
            "held-out station-tag drift exceeds policy")

    corners = document.get("keyboard_corners_px")
    if not isinstance(corners, Mapping) or set(corners) != set(CORNER_ORDER):
        raise FixedCameraKeyboardRegistrationError(
            "four labeled keyboard housing corners are required")
    pixels = np.array([_xy(corners[name], name) for name in CORNER_ORDER])
    if (np.any(pixels < 0)
            or np.any(pixels[:, 0] >= calibration.camera_mode.width)
            or np.any(pixels[:, 1] >= calibration.camera_mode.height)):
        raise FixedCameraKeyboardRegistrationError(
            "keyboard corner lies outside the camera frame")
    observed = np.array([
        calibration.project_pixel(float(point[0]), float(point[1]))
        for point in pixels
    ])

    width, depth = map(float, dimensions[:2])
    footprint = np.array(
        [[0, 0], [width, 0], [width, depth], [0, depth]], dtype=float)
    centered_footprint = footprint - footprint.mean(axis=0)
    centered_observed = observed - observed.mean(axis=0)
    left, _, right = np.linalg.svd(centered_footprint.T @ centered_observed)
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    translation = observed.mean(axis=0) - footprint.mean(axis=0) @ rotation
    fitted = footprint @ rotation + translation
    corner_errors = np.linalg.norm(fitted - observed, axis=1)
    housing_limit = _positive(
        thresholds.get("max_housing_corner_fit_error_mm"), "housing fit limit")
    if float(np.max(corner_errors)) > housing_limit:
        raise FixedCameraKeyboardRegistrationError(
            "housing fit exceeds declared study limit")
    key_limit = _positive(
        thresholds.get("individual_key_localization_limit_mm"),
        "individual key localization limit")

    keys: dict[str, list[float]] = {}
    for row in keyboard.get("rows", []):
        first = np.array(_xy(row.get("first_center_xy_mm"), "row first center"))
        step = np.array(_xy(row.get("step_xy_mm"), "row step"))
        names = row.get("key_ids")
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise FixedCameraKeyboardRegistrationError("key row is invalid")
        for index, name in enumerate(names):
            point = (first + index * step) @ rotation + translation
            keys[name] = [round(float(item), 2) for item in point]
    explicit = keyboard.get("explicit_targets")
    if not isinstance(explicit, Mapping):
        raise FixedCameraKeyboardRegistrationError("explicit key targets are missing")
    for name, item in explicit.items():
        if not isinstance(item, Mapping):
            raise FixedCameraKeyboardRegistrationError("explicit key target is invalid")
        point = np.array(_xy(item.get("center_xy_mm"), name)) @ rotation + translation
        keys[name] = [round(float(value), 2) for value in point]
    if len(keys) < 40 or any(
            not (0 <= point[0] <= calibration.board_width_mm
                 and 0 <= point[1] <= calibration.board_depth_mm)
            for point in keys.values()):
        raise FixedCameraKeyboardRegistrationError(
            "nominal key layout is incomplete or outside the board")

    yaw = math.degrees(math.atan2(rotation[0, 1], rotation[0, 0]))
    rms = float(np.sqrt(np.mean(corner_errors ** 2)))
    maximum = float(np.max(corner_errors))
    profile_blockers: list[str] = []
    if profile == STYLUS_PROFILE:
        profile_blockers.append("STYLUS_TCP_AND_CONTACT_PROFILE_MISSING")
    elif profile != SUPPORTED_PROFILE:
        profile_blockers.append("TOOL_PROFILE_NOT_ADMITTED")
    region_ready = not profile_blockers
    individual_ready = region_ready and maximum <= key_limit
    return {
        "schema": "rocell.fixed_camera_keyboard_registration_assessment.v1",
        "status": "FIXED_CAMERA_REGION_ESTIMATE_NOT_MOTION_AUTHORITY",
        "input_sha256": input_sha256,
        "calibration_sha256": calibration_sha256,
        "profile_sha256": profile_sha256,
        "source_frame_sha256": frame["sha256"],
        "source_frame_bytes_verified": source_frame_verified,
        "profile": profile,
        "camera_and_board_temporal_check_passed": True,
        "world_tag_center_rms_error_mm": round(
            math.sqrt(sum(value * value for value in world_errors.values())
                      / len(world_errors)), 3),
        "world_tag_center_max_error_mm": round(max(world_errors.values()), 3),
        "station_tag_center_max_drift_px": round(max(station_drifts.values()), 3),
        "observed_corners_board_xy_mm": {
            name: [round(float(value), 2) for value in point]
            for name, point in zip(CORNER_ORDER, observed)
        },
        "fitted_front_left_board_xy_mm": [
            round(float(value), 2) for value in translation],
        "fitted_yaw_deg": round(yaw, 3),
        "housing_corner_rms_residual_mm": round(rms, 3),
        "housing_corner_max_residual_mm": round(maximum, 3),
        "individual_key_localization_limit_mm": key_limit,
        "nominal_key_centers_board_xy_mm": keys,
        "keyboard_region_localization_ready": region_ready,
        "individual_key_localization_ready": individual_ready,
        "actual_key_centers_measured": False,
        "board_to_robot_transform_verified": False,
        "physical_clearance_verified": False,
        "open_loop_contact_authorized": False,
        "motion_authorized": False,
        "profile_blockers": profile_blockers,
        "limitations": list(document.get("limitations", [])),
    }


def estimate_files(
    input_path: Path, calibration_path: Path, profile_path: Path, *,
    profile: str = SUPPORTED_PROFILE, source_frame_path: Path | None = None,
) -> dict[str, Any]:
    document, input_raw = _load_json(input_path)
    calibration_raw = Path(calibration_path).read_bytes()
    profile_raw = Path(profile_path).read_bytes()
    calibration = load_fixed_board_plane_calibration_v1(Path(calibration_path))
    profile_document = json.loads(profile_raw.decode("utf-8"))
    verified = False
    if source_frame_path is not None:
        frame = document.get("frame", {})
        source_raw = Path(source_frame_path).read_bytes()
        if len(source_raw) != frame.get("bytes") or _sha256(source_raw) != frame.get("sha256"):
            raise FixedCameraKeyboardRegistrationError(
                "source frame bytes differ from registration input")
        verified = True
    return estimate_fixed_camera_keyboard_registration_v1(
        document, input_sha256=_sha256(input_raw), calibration=calibration,
        calibration_sha256=_sha256(calibration_raw),
        profile_document=profile_document, profile_sha256=_sha256(profile_raw),
        profile=profile, source_frame_verified=verified,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Estimate a keyboard region from a held-out fixed-camera frame")
    parser.add_argument("input", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("targets", type=Path)
    parser.add_argument("--profile", choices=(SUPPORTED_PROFILE, STYLUS_PROFILE),
                        default=SUPPORTED_PROFILE)
    parser.add_argument("--source-frame", type=Path)
    args = parser.parse_args(argv)
    result = estimate_files(
        args.input, args.calibration, args.targets,
        profile=args.profile, source_frame_path=args.source_frame)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["keyboard_region_localization_ready"] else 2


__all__ = [
    "FixedCameraKeyboardRegistrationError",
    "estimate_fixed_camera_keyboard_registration_v1", "estimate_files",
]


if __name__ == "__main__":
    raise SystemExit(main())
