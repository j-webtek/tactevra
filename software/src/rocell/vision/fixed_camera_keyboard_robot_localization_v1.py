"""Compose keyboard localization with reviewed board-to-robot measurements.

The boundary fits a rigid 3-D board-to-robot transform from independent
correspondences, checks held-out points, and maps accepted board-space key
centres into robot-frame localization candidates.  Candidates are deliberately
not motion targets and this module never grants motion or contact authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

import numpy as np


MEASUREMENT_SCHEMA = "rocell.board_to_robot_measurements.v1"
RESULT_SCHEMA = "rocell.fixed_camera_keyboard_robot_localization.v1"
REVIEWED_STATUS = "REVIEWED_INDEPENDENT_BOARD_TO_ROBOT_MEASUREMENTS"
BOARD_FRAME = "RC03_board"
ROBOT_FRAME = "robot_base"
BOARD_WIDTH_MM = 610.0
BOARD_DEPTH_MM = 457.0
SUPPORTED_PROFILES = ("no_attachment", "stylus_attachment")


class FixedCameraKeyboardRobotLocalizationError(ValueError):
    """The composed localization evidence is invalid."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardRobotLocalizationError(
            "value is not canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(value: object, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise FixedCameraKeyboardRobotLocalizationError(
            f"{label} must be a lowercase SHA-256 digest")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (positive and float(value) <= 0)):
        qualifier = "positive " if positive else ""
        raise FixedCameraKeyboardRobotLocalizationError(
            f"{label} must be a {qualifier}finite number")
    return float(value)


def _vector3(value: object, label: str) -> np.ndarray:
    if not isinstance(value, list) or len(value) != 3:
        raise FixedCameraKeyboardRobotLocalizationError(
            f"{label} must contain three numbers")
    return np.asarray([
        _number(component, f"{label}[{index}]")
        for index, component in enumerate(value)
    ], dtype=float)


def _reviewed_at(value: object) -> str:
    if not isinstance(value, str):
        raise FixedCameraKeyboardRobotLocalizationError(
            "review.reviewed_at must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixedCameraKeyboardRobotLocalizationError(
            "review.reviewed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise FixedCameraKeyboardRobotLocalizationError(
            "review.reviewed_at must include a UTC offset")
    return value


def measurement_template() -> dict[str, Any]:
    """Return a blank no-print measurement contract."""
    return {
        "schema": MEASUREMENT_SCHEMA,
        "status": "DRAFT_UNREVIEWED",
        "source_frame": BOARD_FRAME,
        "target_frame": ROBOT_FRAME,
        "units": "mm",
        "measurement_method": "independent_robot_to_board_correspondences",
        "board": {"width_mm": BOARD_WIDTH_MM, "depth_mm": BOARD_DEPTH_MM},
        "installation": {
            "robot_base_identity": "",
            "board_identity": "RC03-INT-R1",
            "installation_unchanged": False,
            "reseat_check_passed": False,
        },
        "review": {
            "reviewed": False, "reviewer": "", "reviewed_at": "", "notes": "",
        },
        "correspondences": [],
        "thresholds": {
            "max_fit_rms_residual_mm": 3.0,
            "max_fit_residual_mm": 5.0,
            "max_holdout_residual_mm": 5.0,
        },
    }


def _fit_rigid(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    covariance = (source - source_mean).T @ (target - target_mean)
    left, _, right_t = np.linalg.svd(covariance)
    rotation = right_t.T @ left.T
    if np.linalg.det(rotation) < 0:
        right_t[-1, :] *= -1
        rotation = right_t.T @ left.T
    translation = target_mean - rotation @ source_mean
    return rotation, translation


def _validate_measurements(
    measurement: Mapping[str, Any],
) -> tuple[list[tuple[str, np.ndarray, np.ndarray]], list[tuple[str, np.ndarray, np.ndarray]], dict[str, float]]:
    if measurement.get("schema") != MEASUREMENT_SCHEMA:
        raise FixedCameraKeyboardRobotLocalizationError(
            "unexpected board-to-robot measurement contract")
    if measurement.get("status") != REVIEWED_STATUS:
        raise FixedCameraKeyboardRobotLocalizationError(
            "board-to-robot measurements require independent review")
    if (measurement.get("source_frame") != BOARD_FRAME
            or measurement.get("target_frame") != ROBOT_FRAME
            or measurement.get("units") != "mm"):
        raise FixedCameraKeyboardRobotLocalizationError(
            "measurements must map RC03_board to robot_base in mm")
    if measurement.get("measurement_method") != (
            "independent_robot_to_board_correspondences"):
        raise FixedCameraKeyboardRobotLocalizationError(
            "unexpected measurement method")

    board = measurement.get("board")
    installation = measurement.get("installation")
    review = measurement.get("review")
    thresholds = measurement.get("thresholds")
    if not all(isinstance(item, Mapping)
               for item in (board, installation, review, thresholds)):
        raise FixedCameraKeyboardRobotLocalizationError(
            "board, installation, review, and thresholds are required")
    if (not math.isclose(_number(board.get("width_mm"), "board width"),
                         BOARD_WIDTH_MM, abs_tol=1e-9)
            or not math.isclose(_number(board.get("depth_mm"), "board depth"),
                                BOARD_DEPTH_MM, abs_tol=1e-9)):
        raise FixedCameraKeyboardRobotLocalizationError(
            "board dimensions must match the 610 x 457 mm RC03 board")
    if (not isinstance(installation.get("robot_base_identity"), str)
            or not installation["robot_base_identity"].strip()
            or not isinstance(installation.get("board_identity"), str)
            or not installation["board_identity"].strip()):
        raise FixedCameraKeyboardRobotLocalizationError(
            "board and robot-base identities are required")
    if (installation.get("installation_unchanged") is not True
            or installation.get("reseat_check_passed") is not True):
        raise FixedCameraKeyboardRobotLocalizationError(
            "unchanged-installation and reseat checks must pass")
    if (review.get("reviewed") is not True
            or not isinstance(review.get("reviewer"), str)
            or not review["reviewer"].strip()):
        raise FixedCameraKeyboardRobotLocalizationError(
            "measurement review metadata is incomplete")
    _reviewed_at(review.get("reviewed_at"))

    limits = {
        "fit_rms": _number(thresholds.get("max_fit_rms_residual_mm"),
                           "fit RMS limit", positive=True),
        "fit_max": _number(thresholds.get("max_fit_residual_mm"),
                           "fit residual limit", positive=True),
        "holdout_max": _number(thresholds.get("max_holdout_residual_mm"),
                               "holdout residual limit", positive=True),
    }
    if limits["fit_rms"] > 3 or limits["fit_max"] > 5 or limits["holdout_max"] > 5:
        raise FixedCameraKeyboardRobotLocalizationError(
            "measurement thresholds cannot exceed 3 mm RMS and 5 mm maximum")

    rows = measurement.get("correspondences")
    if not isinstance(rows, list):
        raise FixedCameraKeyboardRobotLocalizationError(
            "correspondences must be an array")
    fit: list[tuple[str, np.ndarray, np.ndarray]] = []
    holdout: list[tuple[str, np.ndarray, np.ndarray]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise FixedCameraKeyboardRobotLocalizationError(
                "correspondence is invalid")
        point_id = row.get("point_id")
        role = row.get("role")
        if not isinstance(point_id, str) or not point_id or point_id in seen:
            raise FixedCameraKeyboardRobotLocalizationError(
                "correspondence point IDs must be unique and non-empty")
        seen.add(point_id)
        board_point = _vector3(row.get("board_xyz_mm"), f"{point_id} board point")
        robot_point = _vector3(row.get("robot_xyz_mm"), f"{point_id} robot point")
        if not (0 <= board_point[0] <= BOARD_WIDTH_MM
                and 0 <= board_point[1] <= BOARD_DEPTH_MM):
            raise FixedCameraKeyboardRobotLocalizationError(
                f"{point_id} lies outside the RC03 board")
        destination = fit if role == "FIT" else holdout if role == "HOLDOUT" else None
        if destination is None:
            raise FixedCameraKeyboardRobotLocalizationError(
                "correspondence role must be FIT or HOLDOUT")
        destination.append((point_id, board_point, robot_point))
    if len(fit) < 3 or len(holdout) < 2:
        raise FixedCameraKeyboardRobotLocalizationError(
            "at least three fit and two held-out correspondences are required")
    fit_board = np.asarray([row[1] for row in fit])
    if np.linalg.matrix_rank(fit_board[:, :2] - fit_board[:, :2].mean(axis=0)) < 2:
        raise FixedCameraKeyboardRobotLocalizationError(
            "fit correspondences must span both board axes")
    return fit, holdout, limits


def compile_localization(
    measurement: Mapping[str, Any],
    keyboard_package: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    *,
    target_profile_sha256: str,
) -> dict[str, Any]:
    """Fit the board transform and compose both keyboard profiles."""
    if keyboard_package.get("schema") != (
            "rocell.fixed_camera_keyboard_anchor_package.v1"):
        raise FixedCameraKeyboardRobotLocalizationError(
            "unexpected keyboard registration package")
    if keyboard_package.get("shared_keyboard_to_board_transform_verified") is not True:
        raise FixedCameraKeyboardRobotLocalizationError(
            "keyboard-to-board registration package is not ready")
    target_sha = _sha256(
        keyboard_package.get("target_profile_sha256"), "target profile binding")
    if _sha256(target_profile_sha256, "target_profile_sha256") != target_sha:
        raise FixedCameraKeyboardRobotLocalizationError(
            "target profile bytes differ from the keyboard package binding")
    keyboard = target_profile.get("keyboard")
    if not isinstance(keyboard, Mapping):
        raise FixedCameraKeyboardRobotLocalizationError(
            "keyboard target profile is missing")
    target_z = _number(
        keyboard.get("target_plane_z_board_mm"), "keyboard target-plane height")

    fit, holdout, limits = _validate_measurements(measurement)
    source = np.asarray([row[1] for row in fit])
    target = np.asarray([row[2] for row in fit])
    rotation, translation = _fit_rigid(source, target)
    fit_errors = np.linalg.norm((rotation @ source.T).T + translation - target, axis=1)
    hold_source = np.asarray([row[1] for row in holdout])
    hold_target = np.asarray([row[2] for row in holdout])
    hold_errors = np.linalg.norm(
        (rotation @ hold_source.T).T + translation - hold_target, axis=1)
    fit_rms = float(np.sqrt(np.mean(np.square(fit_errors))))
    fit_max = float(np.max(fit_errors))
    hold_max = float(np.max(hold_errors))
    ready = (fit_rms <= limits["fit_rms"] and fit_max <= limits["fit_max"]
             and hold_max <= limits["holdout_max"])

    transform = {
        "source_frame": BOARD_FRAME,
        "target_frame": ROBOT_FRAME,
        "rotation_matrix": [
            [round(float(value), 12) for value in row] for row in rotation],
        "translation_mm": [round(float(value), 6) for value in translation],
        "fit_rms_residual_mm": round(fit_rms, 6),
        "maximum_fit_residual_mm": round(fit_max, 6),
        "maximum_holdout_residual_mm": round(hold_max, 6),
    }
    profiles: dict[str, Any] = {}
    package_profiles = keyboard_package.get("profiles")
    if not isinstance(package_profiles, Mapping):
        raise FixedCameraKeyboardRobotLocalizationError(
            "keyboard package profiles are missing")
    for profile in SUPPORTED_PROFILES:
        source_profile = package_profiles.get(profile)
        if not isinstance(source_profile, Mapping):
            raise FixedCameraKeyboardRobotLocalizationError(
                f"keyboard package profile is missing: {profile}")
        keys = source_profile.get("board_space_key_candidates")
        if not isinstance(keys, list) or len(keys) != 46:
            raise FixedCameraKeyboardRobotLocalizationError(
                f"keyboard package key candidates are incomplete: {profile}")
        candidates = []
        if ready:
            for key in keys:
                if not isinstance(key, Mapping) or not isinstance(key.get("key_id"), str):
                    raise FixedCameraKeyboardRobotLocalizationError(
                        "keyboard key candidate is invalid")
                xy = key.get("board_xy_mm")
                if not isinstance(xy, list) or len(xy) != 2:
                    raise FixedCameraKeyboardRobotLocalizationError(
                        "keyboard key board coordinate is invalid")
                board_point = np.asarray([
                    _number(xy[0], "key board x"),
                    _number(xy[1], "key board y"),
                    target_z,
                ])
                robot_point = rotation @ board_point + translation
                candidates.append({
                    "key_id": key["key_id"],
                    "robot_xyz_mm": [round(float(value), 3) for value in robot_point],
                })
        blockers = ["PHYSICAL_CLEARANCE_UNVERIFIED"]
        if not ready:
            blockers.insert(0, "BOARD_TO_ROBOT_REGISTRATION_RESIDUAL_EXCEEDED")
        if profile == "stylus_attachment":
            blockers.extend(["STYLUS_TCP_UNVERIFIED", "STYLUS_TRAJECTORY_UNVERIFIED"])
        profiles[profile] = {
            "profile": profile,
            "board_to_robot_transform_verified": ready,
            "robot_frame_localization_candidates_emitted": ready,
            "robot_frame_localization_candidates": candidates,
            "motion_targets_emitted": False,
            "physical_clearance_verified": False,
            "motion_authorized": False,
            "contact_authorized": False,
            "blockers": blockers,
        }

    return {
        "schema": RESULT_SCHEMA,
        "status": ("ROBOT_FRAME_LOCALIZATION_CANDIDATES_READY" if ready
                   else "BOARD_TO_ROBOT_REGISTRATION_REJECTED"),
        "measurement_sha256": _digest(measurement),
        "keyboard_package_sha256": _digest(keyboard_package),
        "target_profile_sha256": target_sha,
        "transform": transform,
        "fit_residuals_mm": {
            row[0]: round(float(error), 6) for row, error in zip(fit, fit_errors, strict=True)},
        "holdout_residuals_mm": {
            row[0]: round(float(error), 6) for row, error in zip(holdout, hold_errors, strict=True)},
        "board_to_robot_transform_verified": ready,
        "profiles": profiles,
        "profile_separation_preserved": True,
        "motion_targets_emitted": False,
        "physical_clearance_verified": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "limitations": [
            "Robot-frame points are localization candidates, not motion targets.",
            "Installed continuous clearance remains a separate required gate.",
            "The stylus profile requires its own measured TCP and trajectory qualification.",
        ],
    }


def compile_files(
    measurement_path: Path,
    keyboard_package_path: Path,
    target_profile_path: Path,
) -> dict[str, Any]:
    """Load exact input bytes and compile a robot-localization result."""
    try:
        measurement = json.loads(measurement_path.read_bytes())
        keyboard_package = json.loads(keyboard_package_path.read_bytes())
        target_raw = target_profile_path.read_bytes()
        target_profile = json.loads(target_raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardRobotLocalizationError(
            "localization input could not be read as JSON") from exc
    if not all(isinstance(value, Mapping) for value in (
            measurement, keyboard_package, target_profile)):
        raise FixedCameraKeyboardRobotLocalizationError(
            "localization inputs must be JSON objects")
    return compile_localization(
        measurement,
        keyboard_package,
        target_profile,
        target_profile_sha256=hashlib.sha256(target_raw).hexdigest(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compose keyboard and board-to-robot localization evidence")
    parser.add_argument("measurement", type=Path, nargs="?")
    parser.add_argument("keyboard_package", type=Path, nargs="?")
    parser.add_argument("target_profile", type=Path, nargs="?")
    parser.add_argument("--write-template", type=Path)
    args = parser.parse_args(argv)
    inputs = (args.measurement, args.keyboard_package, args.target_profile)
    if args.write_template is not None:
        if any(value is not None for value in inputs):
            parser.error("--write-template cannot be combined with inputs")
        args.write_template.write_text(
            json.dumps(measurement_template(), indent=2) + "\n",
            encoding="utf-8",
        )
        return 0
    if any(value is None for value in inputs):
        parser.error("measurement, keyboard_package, and target_profile are required")
    result = compile_files(
        args.measurement, args.keyboard_package, args.target_profile)
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0 if result["board_to_robot_transform_verified"] else 2


__all__ = [
    "FixedCameraKeyboardRobotLocalizationError", "compile_files",
    "compile_localization", "measurement_template",
]


if __name__ == "__main__":
    raise SystemExit(main())
