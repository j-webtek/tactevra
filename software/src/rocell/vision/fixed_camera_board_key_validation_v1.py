"""Audit fixed-camera key centers in the provisional RC03 board plane.

The audit projects already observed image-space candidates through the frozen
keyboard-to-pixel map and the independently calibrated pixel-to-board map.  It
fits one rigid keyboard pose per frame and reports per-key residuals.  It never
emits motion targets or grants physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.vision.fixed_board_plane_calibration_v1 import (
    load_fixed_board_plane_calibration_v1,
)
from rocell.vision.fixed_camera_key_feedback_roi_v1 import (
    EXPECTED_KEY_COUNT,
    estimate_files as estimate_roi_files,
)


MAX_JSON_BYTES = 256 * 1024


class FixedCameraBoardKeyValidationError(ValueError):
    """The board-plane key-center audit input is invalid."""


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise FixedCameraBoardKeyValidationError(f"{label} must be a regular file")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise FixedCameraBoardKeyValidationError(f"{label} exceeds 256 KiB")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraBoardKeyValidationError(
            f"could not read {label}: {exc}") from exc
    if type(value) is not dict:
        raise FixedCameraBoardKeyValidationError(f"{label} must be an object")
    return value, raw


def _xy(value: object, label: str) -> tuple[float, float]:
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(item, bool) or not isinstance(item, (int, float))
                   or not math.isfinite(float(item)) for item in value)):
        raise FixedCameraBoardKeyValidationError(f"{label} must be a finite XY pair")
    return float(value[0]), float(value[1])


def _nominal_centers(keyboard: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    centers: dict[str, tuple[float, float]] = {}
    rows = keyboard.get("rows")
    if not isinstance(rows, list):
        raise FixedCameraBoardKeyValidationError("keyboard rows are missing")
    for row in rows:
        if not isinstance(row, Mapping):
            raise FixedCameraBoardKeyValidationError("keyboard row is invalid")
        names = row.get("key_ids")
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise FixedCameraBoardKeyValidationError("keyboard key IDs are invalid")
        first = _xy(row.get("first_center_xy_mm"), "row first center")
        step = _xy(row.get("step_xy_mm"), "row step")
        for index, name in enumerate(names):
            if name in centers:
                raise FixedCameraBoardKeyValidationError(f"duplicate key ID: {name}")
            centers[name] = (first[0] + index * step[0],
                             first[1] + index * step[1])
    explicit = keyboard.get("explicit_targets")
    if not isinstance(explicit, Mapping):
        raise FixedCameraBoardKeyValidationError("explicit targets are missing")
    for name, target in explicit.items():
        if not isinstance(name, str) or not isinstance(target, Mapping) or name in centers:
            raise FixedCameraBoardKeyValidationError("explicit target is invalid")
        centers[name] = _xy(target.get("center_xy_mm"), f"{name} center")
    if len(centers) != EXPECTED_KEY_COUNT:
        raise FixedCameraBoardKeyValidationError(
            f"expected {EXPECTED_KEY_COUNT} target centers, got {len(centers)}")
    return centers


def _project_homography(matrix: object, point: tuple[float, float]) -> tuple[float, float]:
    import numpy as np

    homography = np.asarray(matrix, dtype=float)
    if homography.shape != (3, 3) or not np.all(np.isfinite(homography)):
        raise FixedCameraBoardKeyValidationError("keyboard homography is invalid")
    result = homography @ np.asarray([point[0], point[1], 1.0], dtype=float)
    if abs(float(result[2])) < 1e-12:
        raise FixedCameraBoardKeyValidationError("keyboard projection is singular")
    pixel = result[:2] / result[2]
    if not np.all(np.isfinite(pixel)):
        raise FixedCameraBoardKeyValidationError("keyboard projection is not finite")
    return float(pixel[0]), float(pixel[1])


def fit_rigid_board_pose(
    nominal_by_key: Mapping[str, tuple[float, float]],
    observed_by_key: Mapping[str, tuple[float, float]],
) -> tuple[dict[str, Any], dict[str, float]]:
    """Fit one row-vector rigid transform and return its per-key residuals."""
    import numpy as np

    if set(nominal_by_key) != set(observed_by_key) or len(nominal_by_key) < 3:
        raise FixedCameraBoardKeyValidationError("rigid-fit key identities differ")
    names = list(nominal_by_key)
    nominal = np.asarray([nominal_by_key[name] for name in names], dtype=float)
    observed = np.asarray([observed_by_key[name] for name in names], dtype=float)
    nominal_centered = nominal - nominal.mean(axis=0)
    observed_centered = observed - observed.mean(axis=0)
    left, _, right = np.linalg.svd(nominal_centered.T @ observed_centered)
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    translation = observed.mean(axis=0) - nominal.mean(axis=0) @ rotation
    fitted = nominal @ rotation + translation
    errors = np.linalg.norm(fitted - observed, axis=1)
    residuals = {name: float(error) for name, error in zip(names, errors)}
    pose = {
        "front_left_board_xy_mm": [round(float(value), 3) for value in translation],
        "yaw_deg": round(float(math.degrees(
            math.atan2(rotation[0, 1], rotation[0, 0]))), 3),
        "rms_residual_mm": round(float(np.sqrt(np.mean(errors ** 2))), 3),
        "maximum_residual_mm": round(float(np.max(errors)), 3),
        "median_residual_mm": round(float(np.median(errors)), 3),
    }
    return pose, residuals


def assess(
    candidates: Mapping[str, Any], roi: Mapping[str, Any],
    keyboard: Mapping[str, Any], calibration: object,
    *, individual_limit_mm: float,
) -> dict[str, Any]:
    """Project two-frame candidates and audit a rigid board pose."""
    if (candidates.get("schema") != "rocell.fixed_camera_key_center_candidates.v1"
            or candidates.get("profile") != "no_attachment"
            or candidates.get("image_space_key_center_candidates_ready") is not True):
        raise FixedCameraBoardKeyValidationError("candidate prerequisite is not ready")
    if (roi.get("schema") != "rocell.fixed_camera_key_feedback_roi.v1"
            or roi.get("profile") != "no_attachment"
            or roi.get("image_space_feedback_windows_ready") is not True):
        raise FixedCameraBoardKeyValidationError("ROI prerequisite is not ready")
    if candidates.get("reference_frame_sha256") != roi.get("source_frame_sha256"):
        raise FixedCameraBoardKeyValidationError("reference frame binding differs")
    if (isinstance(individual_limit_mm, bool)
            or not isinstance(individual_limit_mm, (int, float))
            or not math.isfinite(float(individual_limit_mm))
            or float(individual_limit_mm) <= 0):
        raise FixedCameraBoardKeyValidationError("individual limit is invalid")

    rows = candidates.get("key_center_candidates")
    if not isinstance(rows, list) or len(rows) != EXPECTED_KEY_COUNT:
        raise FixedCameraBoardKeyValidationError("candidate rows are incomplete")
    nominal = _nominal_centers(keyboard)
    if {row.get("key_id") for row in rows if isinstance(row, Mapping)} != set(nominal):
        raise FixedCameraBoardKeyValidationError("candidate key identities differ")
    homography = roi.get("local_keyboard_to_pixel_homography")

    observations: dict[str, dict[str, tuple[float, float]]] = {
        "reference": {}, "repeat": {}}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FixedCameraBoardKeyValidationError("candidate row is invalid")
        name = row["key_id"]
        for label, field in (("reference", "reference_center_xy_mm"),
                             ("repeat", "repeat_center_xy_mm")):
            local = _xy(row.get(field), f"{name} {label} center")
            pixel = _project_homography(homography, local)
            observations[label][name] = tuple(calibration.project_pixel(*pixel))

    reference_pose, reference_errors = fit_rigid_board_pose(
        nominal, observations["reference"])
    repeat_pose, repeat_errors = fit_rigid_board_pose(nominal, observations["repeat"])
    temporal_limit = float(candidates.get("maximum_key_center_temporal_delta_mm", 0))
    if temporal_limit <= 0:
        raise FixedCameraBoardKeyValidationError("temporal limit is invalid")

    comparisons = []
    for name in nominal:
        reference_board = observations["reference"][name]
        repeat_board = observations["repeat"][name]
        temporal = math.dist(reference_board, repeat_board)
        passed = (reference_errors[name] <= individual_limit_mm
                  and repeat_errors[name] <= individual_limit_mm
                  and temporal <= temporal_limit)
        comparisons.append({
            "key_id": name,
            "reference_board_observation_xy_mm": [
                round(value, 3) for value in reference_board],
            "repeat_board_observation_xy_mm": [
                round(value, 3) for value in repeat_board],
            "reference_rigid_pose_residual_mm": round(reference_errors[name], 3),
            "repeat_rigid_pose_residual_mm": round(repeat_errors[name], 3),
            "board_observation_temporal_delta_mm": round(temporal, 3),
            "board_plane_validation_passed": passed,
        })
    validated = [row for row in comparisons if row["board_plane_validation_passed"]]
    failed = [row["key_id"] for row in comparisons
              if not row["board_plane_validation_passed"]]
    complete = len(validated) == EXPECTED_KEY_COUNT
    blockers = [
        "INDEPENDENT_PHYSICAL_KEY_MEASUREMENT_MISSING",
        "ELEVATED_KEY_PLANE_PARALLAX_UNCORRECTED",
        "BOARD_TO_ROBOT_TRANSFORM_UNVERIFIED",
        "PHYSICAL_CLEARANCE_UNVERIFIED",
    ]
    if failed:
        blockers.insert(0, "BOARD_PLANE_ALL_KEYS_NOT_WITHIN_LIMIT")
    return {
        "schema": "rocell.fixed_camera_board_key_validation.v1",
        "status": ("BOARD_PLANE_KEY_VALIDATION_READY_NO_MOTION_AUTHORITY"
                   if complete else
                   "BOARD_PLANE_KEY_VALIDATION_INCOMPLETE_NO_MOTION_AUTHORITY"),
        "profile": "no_attachment",
        "individual_key_limit_mm": float(individual_limit_mm),
        "board_observation_temporal_limit_mm": temporal_limit,
        "reference_rigid_pose": reference_pose,
        "repeat_rigid_pose": repeat_pose,
        "key_validations": comparisons,
        "key_validation_count": len(comparisons),
        "validated_key_count": len(validated),
        "failed_key_ids": failed,
        "board_plane_key_validation_ready": complete,
        "independent_physical_key_measurement_present": False,
        "board_space_motion_targets_emitted": False,
        "board_to_robot_transform_verified": False,
        "physical_clearance_verified": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "blockers": blockers,
        "limitations": [
            "Board observations are projections through the provisional Z=0 board homography; the elevated key plane is not intrinsically corrected.",
            "The AprilTag board map is independent of the key-edge fit, but both key observations originate from the retained camera views rather than an independent physical key measurement.",
            "This audit measures rigid-layout coherence only and does not emit accepted board-space targets.",
            "The no-attachment result does not apply to the separate stylus_attachment TCP and trajectory profile.",
        ],
    }


def estimate_files(
    candidate_path: Path, registration_path: Path, calibration_path: Path,
    profile_path: Path,
) -> dict[str, Any]:
    candidates, candidate_raw = _read_json(candidate_path, "candidate result")
    registration, registration_raw = _read_json(registration_path, "registration")
    profile, profile_raw = _read_json(profile_path, "target profile")
    thresholds = registration.get("thresholds")
    keyboard = profile.get("keyboard")
    if not isinstance(thresholds, Mapping) or not isinstance(keyboard, Mapping):
        raise FixedCameraBoardKeyValidationError("validation configuration is missing")
    roi = estimate_roi_files(registration_path, calibration_path, profile_path)
    calibration_raw = calibration_path.read_bytes()
    calibration = load_fixed_board_plane_calibration_v1(calibration_path)
    result = assess(
        candidates, roi, keyboard, calibration,
        individual_limit_mm=float(thresholds["individual_key_localization_limit_mm"]),
    )
    result.update({
        "candidate_result_sha256": hashlib.sha256(candidate_raw).hexdigest(),
        "registration_input_sha256": hashlib.sha256(registration_raw).hexdigest(),
        "calibration_sha256": hashlib.sha256(calibration_raw).hexdigest(),
        "profile_sha256": hashlib.sha256(profile_raw).hexdigest(),
        "reference_frame_sha256": candidates["reference_frame_sha256"],
        "repeat_frame_sha256": candidates["repeat_frame_sha256"],
    })
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("registration", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("targets", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = estimate_files(
        args.candidates, args.registration, args.calibration, args.targets)
    encoded = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    if args.output:
        args.output.write_bytes(encoded)
    else:
        print(encoded.decode(), end="")
    return 0 if result["board_plane_key_validation_ready"] else 2


__all__ = [
    "FixedCameraBoardKeyValidationError", "assess", "estimate_files",
    "fit_rigid_board_pose",
]


if __name__ == "__main__":
    raise SystemExit(main())
