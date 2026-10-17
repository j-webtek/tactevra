"""Fit an absolute keyboard-to-board transform from independent evidence.

The elevated-plane audit proves local key-layout coherence but cannot recover
translation in the board frame.  This module accepts the missing independent
anchors, fits one rigid transform, and emits localization candidates only.
It never grants robot motion or contact authority.
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


SUPPORTED_PROFILES = {"no_attachment", "stylus_attachment"}
SOURCE_STATUSES = {
    "REVIEWED_INDEPENDENT_BOARD_FRAME_MEASUREMENTS":
        "independent_board_frame_measurements",
    "ACCEPTED_3D_CAMERA_MODEL_MEASUREMENTS": "accepted_3d_camera_model",
}


class FixedCameraKeyboardBoardRegistrationError(ValueError):
    """The absolute keyboard-to-board registration input is invalid."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256(value: object, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise FixedCameraKeyboardBoardRegistrationError(
            f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive(value: object, label: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) <= 0):
        raise FixedCameraKeyboardBoardRegistrationError(
            f"{label} must be a positive finite number")
    return float(value)


def _expected_points(keyboard: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    try:
        points = _nominal_centers(keyboard)
    except FixedCameraBoardKeyValidationError as exc:
        raise FixedCameraKeyboardBoardRegistrationError(str(exc)) from exc
    dimensions = keyboard.get("device_size_mm")
    if (not isinstance(dimensions, list) or len(dimensions) != 3
            or any(isinstance(value, bool)
                   or not isinstance(value, (int, float))
                   or not math.isfinite(float(value))
                   or float(value) <= 0 for value in dimensions)):
        raise FixedCameraKeyboardBoardRegistrationError(
            "keyboard dimensions are invalid")
    width, depth = map(float, dimensions[:2])
    points.update({
        "HOUSING_FRONT_LEFT": (0.0, 0.0),
        "HOUSING_FRONT_RIGHT": (width, 0.0),
        "HOUSING_REAR_RIGHT": (width, depth),
        "HOUSING_REAR_LEFT": (0.0, depth),
    })
    return points


def assess(
    evidence: Mapping[str, Any],
    elevated: Mapping[str, Any],
    keyboard: Mapping[str, Any],
    *,
    evidence_sha256: str,
    elevated_sha256: str,
    profile_sha256: str,
    profile: str,
) -> dict[str, Any]:
    """Fit and gate one absolute keyboard-to-board registration."""
    _sha256(evidence_sha256, "evidence_sha256")
    _sha256(elevated_sha256, "elevated_sha256")
    _sha256(profile_sha256, "profile_sha256")
    if profile not in SUPPORTED_PROFILES:
        raise FixedCameraKeyboardBoardRegistrationError(
            "profile must be no_attachment or stylus_attachment")
    if (elevated.get("schema")
            != "rocell.fixed_camera_elevated_key_plane_validation.v1"
            or elevated.get("elevated_key_plane_coherence_ready") is not True
            or elevated.get("profile") != "no_attachment"):
        raise FixedCameraKeyboardBoardRegistrationError(
            "elevated key-plane prerequisite is not ready")
    if evidence.get("schema") != (
            "rocell.fixed_camera_keyboard_board_registration_input.v1"):
        raise FixedCameraKeyboardBoardRegistrationError(
            "unexpected keyboard-to-board evidence contract")
    status = evidence.get("status")
    source_kind = evidence.get("source_kind")
    if SOURCE_STATUSES.get(status) != source_kind:
        raise FixedCameraKeyboardBoardRegistrationError(
            "evidence status and source kind differ")
    bindings = evidence.get("bindings")
    thresholds = evidence.get("thresholds")
    board = evidence.get("board")
    if not all(isinstance(item, Mapping)
               for item in (bindings, thresholds, board)):
        raise FixedCameraKeyboardBoardRegistrationError(
            "evidence bindings, thresholds, or board are missing")
    if (_sha256(bindings.get("elevated_validation_sha256"),
                "elevated validation binding") != elevated_sha256
            or _sha256(bindings.get("target_profile_sha256"),
                       "target profile binding") != profile_sha256):
        raise FixedCameraKeyboardBoardRegistrationError(
            "evidence binding digest differs")
    source_digest = _sha256(
        evidence.get("source_artifact_sha256"), "source artifact digest")

    expected = _expected_points(keyboard)
    anchors = evidence.get("anchors")
    if not isinstance(anchors, list) or len(anchors) < 3:
        raise FixedCameraKeyboardBoardRegistrationError(
            "at least three independent anchors are required")
    nominal: dict[str, tuple[float, float]] = {}
    observed: dict[str, tuple[float, float]] = {}
    for anchor in anchors:
        if not isinstance(anchor, Mapping):
            raise FixedCameraKeyboardBoardRegistrationError("anchor is invalid")
        point_id = anchor.get("point_id")
        if not isinstance(point_id, str) or point_id not in expected:
            raise FixedCameraKeyboardBoardRegistrationError(
                "anchor point ID is not in the bound keyboard geometry")
        if point_id in nominal:
            raise FixedCameraKeyboardBoardRegistrationError(
                f"duplicate anchor point ID: {point_id}")
        nominal[point_id] = expected[point_id]
        try:
            observed[point_id] = _xy(
                anchor.get("board_xy_mm"), f"{point_id} board coordinate")
        except FixedCameraBoardKeyValidationError as exc:
            raise FixedCameraKeyboardBoardRegistrationError(str(exc)) from exc

    import numpy as np

    local = np.asarray(list(nominal.values()), dtype=float)
    if np.linalg.matrix_rank(local - local.mean(axis=0)) < 2:
        raise FixedCameraKeyboardBoardRegistrationError(
            "anchor geometry must span two keyboard-plane axes")
    try:
        pose, residuals = fit_rigid_board_pose(nominal, observed)
    except FixedCameraBoardKeyValidationError as exc:
        raise FixedCameraKeyboardBoardRegistrationError(str(exc)) from exc
    rms_limit = _positive(thresholds.get("max_rms_residual_mm"), "RMS limit")
    maximum_limit = _positive(
        thresholds.get("max_anchor_residual_mm"), "anchor residual limit")
    registration_ready = (
        pose["rms_residual_mm"] <= rms_limit
        and pose["maximum_residual_mm"] <= maximum_limit)

    width = _positive(board.get("width_mm"), "board width")
    depth = _positive(board.get("depth_mm"), "board depth")
    theta = math.radians(float(pose["yaw_deg"]))
    rotation = np.asarray([
        [math.cos(theta), math.sin(theta)],
        [-math.sin(theta), math.cos(theta)],
    ])
    translation = np.asarray(pose["front_left_board_xy_mm"], dtype=float)
    key_points: list[dict[str, Any]] = []
    if registration_ready:
        keys = _nominal_centers(keyboard)
        for key_id, point in keys.items():
            board_point = np.asarray(point) @ rotation + translation
            if not (0 <= board_point[0] <= width and 0 <= board_point[1] <= depth):
                raise FixedCameraKeyboardBoardRegistrationError(
                    "registered key center lies outside the board")
            key_points.append({
                "key_id": key_id,
                "board_xy_mm": [round(float(value), 3) for value in board_point],
            })
        if len(key_points) != EXPECTED_KEY_COUNT:
            raise FixedCameraKeyboardBoardRegistrationError(
                "registered key set is incomplete")

    blockers = [
        "BOARD_TO_ROBOT_TRANSFORM_UNVERIFIED",
        "PHYSICAL_CLEARANCE_UNVERIFIED",
    ]
    if not registration_ready:
        blockers.insert(0, "KEYBOARD_TO_BOARD_REGISTRATION_RESIDUAL_EXCEEDED")
    if profile == "stylus_attachment":
        blockers.extend([
            "STYLUS_TCP_UNVERIFIED",
            "STYLUS_TRAJECTORY_UNVERIFIED",
        ])
    return {
        "schema": "rocell.fixed_camera_keyboard_board_registration.v1",
        "status": ("ABSOLUTE_KEYBOARD_TO_BOARD_LOCALIZATION_READY"
                   if registration_ready else
                   "ABSOLUTE_KEYBOARD_TO_BOARD_LOCALIZATION_REJECTED"),
        "profile": profile,
        "evidence_sha256": evidence_sha256,
        "elevated_validation_sha256": elevated_sha256,
        "target_profile_sha256": profile_sha256,
        "source_kind": source_kind,
        "source_artifact_sha256": source_digest,
        "anchor_count": len(anchors),
        "pose": pose,
        "anchor_residuals_mm": {
            name: round(value, 3) for name, value in residuals.items()},
        "max_rms_residual_mm": rms_limit,
        "max_anchor_residual_mm": maximum_limit,
        "absolute_keyboard_to_board_transform_verified": registration_ready,
        "board_space_key_candidates_emitted": registration_ready,
        "board_space_key_candidates": key_points,
        "board_to_robot_transform_verified": False,
        "physical_clearance_verified": False,
        "motion_targets_emitted": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "blockers": blockers,
        "limitations": [
            "The transform is accepted only from an accepted 3-D camera model or independently reviewed board-frame measurements.",
            "Board-space key coordinates are localization candidates, not robot-base motion targets.",
            "Board-to-robot registration and installed clearance remain separate required gates.",
            "The stylus profile additionally requires its own TCP and trajectory qualification.",
        ],
    }


def estimate_files(
    evidence_path: Path,
    elevated_path: Path,
    profile_path: Path,
    *,
    profile: str,
) -> dict[str, Any]:
    evidence, evidence_raw = _read_json(evidence_path, "registration evidence")
    elevated, elevated_raw = _read_json(elevated_path, "elevated validation")
    targets, targets_raw = _read_json(profile_path, "target profile")
    keyboard = targets.get("keyboard")
    if not isinstance(keyboard, Mapping):
        raise FixedCameraKeyboardBoardRegistrationError(
            "keyboard target profile is missing")
    return assess(
        evidence, elevated, keyboard,
        evidence_sha256=_digest(evidence_raw),
        elevated_sha256=_digest(elevated_raw),
        profile_sha256=_digest(targets_raw),
        profile=profile,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fit an absolute keyboard-to-board registration")
    parser.add_argument("evidence", type=Path)
    parser.add_argument("elevated_validation", type=Path)
    parser.add_argument("targets", type=Path)
    parser.add_argument("--profile", choices=sorted(SUPPORTED_PROFILES),
                        default="no_attachment")
    args = parser.parse_args(argv)
    result = estimate_files(
        args.evidence, args.elevated_validation, args.targets,
        profile=args.profile)
    sys.stdout.buffer.write(
        (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return 0 if result["absolute_keyboard_to_board_transform_verified"] else 2


__all__ = [
    "FixedCameraKeyboardBoardRegistrationError", "assess", "estimate_files",
]


if __name__ == "__main__":
    raise SystemExit(main())
