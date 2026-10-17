"""Audit fixed-camera key centers in the keyboard's elevated local plane.

The key-center candidates were measured after rectifying the visible keyboard
housing into its declared 315 x 147 mm plane. This audit therefore checks the
46 observations in that plane before any projection onto the RC03 board. It
can distinguish key-layout error from Z=0 board-plane parallax, but it cannot
recover an absolute keyboard-to-board transform or emit motion targets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from rocell.vision.fixed_camera_board_key_validation_v1 import (
    EXPECTED_KEY_COUNT,
    FixedCameraBoardKeyValidationError,
    _nominal_centers,
    _read_json,
    _xy,
    fit_rigid_board_pose,
)


class FixedCameraElevatedKeyPlaneValidationError(ValueError):
    """The elevated key-plane audit input is invalid."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _local_pose(
    nominal: Mapping[str, tuple[float, float]],
    observed: Mapping[str, tuple[float, float]],
) -> tuple[dict[str, Any], dict[str, float]]:
    pose, residuals = fit_rigid_board_pose(nominal, observed)
    return {
        "front_left_keyboard_xy_mm": pose["front_left_board_xy_mm"],
        "yaw_deg": pose["yaw_deg"],
        "rms_residual_mm": pose["rms_residual_mm"],
        "maximum_residual_mm": pose["maximum_residual_mm"],
        "median_residual_mm": pose["median_residual_mm"],
    }, residuals


def assess(
    candidates: Mapping[str, Any],
    keyboard: Mapping[str, Any],
    *,
    individual_limit_mm: float,
) -> dict[str, Any]:
    """Evaluate two-frame candidates in the elevated keyboard plane."""
    if (candidates.get("schema")
            != "rocell.fixed_camera_key_center_candidates.v1"
            or candidates.get("profile") != "no_attachment"
            or candidates.get("image_space_key_center_candidates_ready") is not True):
        raise FixedCameraElevatedKeyPlaneValidationError(
            "candidate prerequisite is not ready")
    if (isinstance(individual_limit_mm, bool)
            or not isinstance(individual_limit_mm, (int, float))
            or not math.isfinite(float(individual_limit_mm))
            or float(individual_limit_mm) <= 0):
        raise FixedCameraElevatedKeyPlaneValidationError(
            "individual limit is invalid")
    try:
        nominal = _nominal_centers(keyboard)
    except FixedCameraBoardKeyValidationError as exc:
        raise FixedCameraElevatedKeyPlaneValidationError(str(exc)) from exc
    dimensions = keyboard.get("device_size_mm")
    if (not isinstance(dimensions, list) or len(dimensions) != 3
            or any(isinstance(value, bool)
                   or not isinstance(value, (int, float))
                   or not math.isfinite(float(value))
                   or float(value) <= 0 for value in dimensions)):
        raise FixedCameraElevatedKeyPlaneValidationError(
            "keyboard dimensions are invalid")

    rows = candidates.get("key_center_candidates")
    if not isinstance(rows, list) or len(rows) != EXPECTED_KEY_COUNT:
        raise FixedCameraElevatedKeyPlaneValidationError(
            "candidate rows are incomplete")
    if {row.get("key_id") for row in rows if isinstance(row, Mapping)} != set(nominal):
        raise FixedCameraElevatedKeyPlaneValidationError(
            "candidate key identities differ")

    observations: dict[str, dict[str, tuple[float, float]]] = {
        "reference": {}, "repeat": {}}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FixedCameraElevatedKeyPlaneValidationError(
                "candidate row is invalid")
        name = row["key_id"]
        try:
            observations["reference"][name] = _xy(
                row.get("reference_center_xy_mm"), f"{name} reference center")
            observations["repeat"][name] = _xy(
                row.get("repeat_center_xy_mm"), f"{name} repeat center")
        except FixedCameraBoardKeyValidationError as exc:
            raise FixedCameraElevatedKeyPlaneValidationError(str(exc)) from exc

    reference_pose, reference_errors = _local_pose(
        nominal, observations["reference"])
    repeat_pose, repeat_errors = _local_pose(nominal, observations["repeat"])
    temporal_limit = candidates.get("maximum_key_center_temporal_delta_mm")
    if (isinstance(temporal_limit, bool)
            or not isinstance(temporal_limit, (int, float))
            or not math.isfinite(float(temporal_limit))
            or float(temporal_limit) <= 0):
        raise FixedCameraElevatedKeyPlaneValidationError(
            "temporal limit is invalid")
    temporal_limit = float(temporal_limit)

    comparisons: list[dict[str, Any]] = []
    for name in nominal:
        reference = observations["reference"][name]
        repeat = observations["repeat"][name]
        temporal = math.dist(reference, repeat)
        passed = (reference_errors[name] <= individual_limit_mm
                  and repeat_errors[name] <= individual_limit_mm
                  and temporal <= temporal_limit)
        comparisons.append({
            "key_id": name,
            "reference_local_observation_xy_mm": [round(v, 3) for v in reference],
            "repeat_local_observation_xy_mm": [round(v, 3) for v in repeat],
            "reference_rigid_layout_residual_mm": round(reference_errors[name], 3),
            "repeat_rigid_layout_residual_mm": round(repeat_errors[name], 3),
            "local_observation_temporal_delta_mm": round(temporal, 3),
            "elevated_plane_coherence_passed": passed,
        })
    failed = [row["key_id"] for row in comparisons
              if not row["elevated_plane_coherence_passed"]]
    complete = not failed
    blockers = [
        "ABSOLUTE_KEYBOARD_TO_BOARD_TRANSFORM_UNVERIFIED",
        "INDEPENDENT_PHYSICAL_KEY_MEASUREMENT_MISSING",
        "BOARD_TO_ROBOT_TRANSFORM_UNVERIFIED",
        "PHYSICAL_CLEARANCE_UNVERIFIED",
    ]
    if failed:
        blockers.insert(0, "ELEVATED_KEY_PLANE_ALL_KEYS_NOT_WITHIN_LIMIT")
    return {
        "schema": "rocell.fixed_camera_elevated_key_plane_validation.v1",
        "status": ("ELEVATED_KEY_PLANE_COHERENCE_READY_NO_BOARD_TARGETS"
                   if complete else
                   "ELEVATED_KEY_PLANE_COHERENCE_INCOMPLETE_NO_BOARD_TARGETS"),
        "profile": "no_attachment",
        "keyboard_plane_dimensions_mm": [float(value) for value in dimensions],
        "individual_key_limit_mm": float(individual_limit_mm),
        "local_observation_temporal_limit_mm": temporal_limit,
        "reference_rigid_layout": reference_pose,
        "repeat_rigid_layout": repeat_pose,
        "key_validations": comparisons,
        "key_validation_count": len(comparisons),
        "validated_key_count": len(comparisons) - len(failed),
        "failed_key_ids": failed,
        "elevated_key_plane_coherence_ready": complete,
        "space_key_elevated_plane_coherence_passed": "SPACE" not in failed,
        "absolute_keyboard_to_board_transform_verified": False,
        "independent_physical_key_measurement_present": False,
        "board_space_motion_targets_emitted": False,
        "board_to_robot_transform_verified": False,
        "physical_clearance_verified": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "blockers": blockers,
        "limitations": [
            "The audit uses the rectified 315 x 147 mm keyboard housing plane and does not project observations through the RC03 Z=0 board homography.",
            "Passing local-plane coherence isolates the earlier SPACE failure to plane projection, but does not determine the keyboard plane's absolute board-frame translation.",
            "Both observations originate from retained camera views rather than an independent physical key-center measurement.",
            "No board-space target, board-to-robot transform, clearance result, motion command, or contact authority is produced.",
            "The no-attachment result does not apply to the separate stylus_attachment TCP and trajectory profile.",
        ],
    }


def estimate_files(
    candidate_path: Path,
    registration_path: Path,
    profile_path: Path,
) -> dict[str, Any]:
    candidates, candidate_raw = _read_json(candidate_path, "candidate result")
    registration, registration_raw = _read_json(registration_path, "registration")
    profile, profile_raw = _read_json(profile_path, "target profile")
    thresholds = registration.get("thresholds")
    keyboard = profile.get("keyboard")
    if not isinstance(thresholds, Mapping) or not isinstance(keyboard, Mapping):
        raise FixedCameraElevatedKeyPlaneValidationError(
            "validation configuration is missing")
    result = assess(
        candidates,
        keyboard,
        individual_limit_mm=float(
            thresholds["individual_key_localization_limit_mm"]),
    )
    result.update({
        "candidate_result_sha256": _digest(candidate_raw),
        "registration_input_sha256": _digest(registration_raw),
        "profile_sha256": _digest(profile_raw),
        "reference_frame_sha256": candidates["reference_frame_sha256"],
        "repeat_frame_sha256": candidates["repeat_frame_sha256"],
    })
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit fixed-camera keys in the elevated keyboard plane")
    parser.add_argument("candidates", type=Path)
    parser.add_argument("registration", type=Path)
    parser.add_argument("targets", type=Path)
    args = parser.parse_args(argv)
    result = estimate_files(args.candidates, args.registration, args.targets)
    sys.stdout.buffer.write(
        (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return 0 if result["elevated_key_plane_coherence_ready"] else 2


__all__ = [
    "FixedCameraElevatedKeyPlaneValidationError", "assess", "estimate_files",
]


if __name__ == "__main__":
    raise SystemExit(main())
