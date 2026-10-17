"""Build a governed keyboard-to-board registration package from measurements.

This module turns a small, human-reviewed board-frame measurement document
into the evidence contract consumed by the absolute registration boundary.  It
evaluates both attachment profiles together and never emits motion authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from rocell.vision.fixed_camera_board_key_validation_v1 import _read_json
from rocell.vision.fixed_camera_keyboard_board_registration_v1 import (
    FixedCameraKeyboardBoardRegistrationError,
    assess,
)


MEASUREMENT_SCHEMA = "rocell.fixed_camera_keyboard_anchor_measurements.v1"
PACKAGE_SCHEMA = "rocell.fixed_camera_keyboard_anchor_package.v1"
REVIEWED_STATUS = "REVIEWED_INDEPENDENT_BOARD_FRAME_MEASUREMENTS"
BOARD_FRAME = "RC03_board"
BOARD_WIDTH_MM = 610.0
BOARD_DEPTH_MM = 457.0
DEFAULT_RMS_LIMIT_MM = 3.0
DEFAULT_ANCHOR_LIMIT_MM = 5.0
HOUSING_ANCHORS = (
    "HOUSING_FRONT_LEFT",
    "HOUSING_FRONT_RIGHT",
    "HOUSING_REAR_RIGHT",
    "HOUSING_REAR_LEFT",
)


class FixedCameraKeyboardAnchorPackageError(ValueError):
    """The reviewed anchor measurement package is invalid."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _positive(value: object, label: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) <= 0):
        raise FixedCameraKeyboardAnchorPackageError(
            f"{label} must be a positive finite number")
    return float(value)


def _reviewed_at(value: object) -> str:
    if not isinstance(value, str):
        raise FixedCameraKeyboardAnchorPackageError(
            "review.reviewed_at must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixedCameraKeyboardAnchorPackageError(
            "review.reviewed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise FixedCameraKeyboardAnchorPackageError(
            "review.reviewed_at must include a UTC offset")
    return value


def measurement_template() -> dict[str, Any]:
    """Return a no-print four-corner measurement template."""
    return {
        "schema": MEASUREMENT_SCHEMA,
        "status": "DRAFT_UNREVIEWED",
        "coordinate_frame": BOARD_FRAME,
        "coordinate_definition": (
            "x from board left edge, y from board front edge, millimetres"),
        "units": "mm",
        "measurement_method": "direct_board_frame_measurement",
        "board": {
            "width_mm": BOARD_WIDTH_MM,
            "depth_mm": BOARD_DEPTH_MM,
        },
        "review": {
            "reviewed": False,
            "reviewer": "",
            "reviewed_at": "",
            "notes": "",
        },
        "anchors": [
            {"point_id": point_id, "board_xy_mm": [None, None]}
            for point_id in HOUSING_ANCHORS
        ],
        "thresholds": {
            "max_rms_residual_mm": DEFAULT_RMS_LIMIT_MM,
            "max_anchor_residual_mm": DEFAULT_ANCHOR_LIMIT_MM,
        },
    }


def build_evidence(
    measurement: Mapping[str, Any],
    *,
    measurement_sha256: str,
    elevated_sha256: str,
    target_profile_sha256: str,
) -> dict[str, Any]:
    """Validate reviewed measurements and build the registration input."""
    if measurement.get("schema") != MEASUREMENT_SCHEMA:
        raise FixedCameraKeyboardAnchorPackageError(
            "unexpected anchor measurement contract")
    if measurement.get("status") != REVIEWED_STATUS:
        raise FixedCameraKeyboardAnchorPackageError(
            "measurement status must record independent review")
    if measurement.get("coordinate_frame") != BOARD_FRAME:
        raise FixedCameraKeyboardAnchorPackageError(
            "measurements must use the RC03_board frame")
    if measurement.get("units") != "mm":
        raise FixedCameraKeyboardAnchorPackageError(
            "measurement units must be mm")
    if measurement.get("measurement_method") != (
            "direct_board_frame_measurement"):
        raise FixedCameraKeyboardAnchorPackageError(
            "measurement method must be direct_board_frame_measurement")

    board = measurement.get("board")
    review = measurement.get("review")
    thresholds = measurement.get("thresholds")
    anchors = measurement.get("anchors")
    if not all(isinstance(item, Mapping)
               for item in (board, review, thresholds)):
        raise FixedCameraKeyboardAnchorPackageError(
            "board, review, and thresholds are required")
    if (not math.isclose(_positive(board.get("width_mm"), "board width"),
                         BOARD_WIDTH_MM, abs_tol=1e-9)
            or not math.isclose(
                _positive(board.get("depth_mm"), "board depth"),
                BOARD_DEPTH_MM, abs_tol=1e-9)):
        raise FixedCameraKeyboardAnchorPackageError(
            "board dimensions must match the 610 x 457 mm RC03 board")
    if review.get("reviewed") is not True:
        raise FixedCameraKeyboardAnchorPackageError(
            "review.reviewed must be true")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise FixedCameraKeyboardAnchorPackageError(
            "review.reviewer must be recorded")
    _reviewed_at(review.get("reviewed_at"))
    if not isinstance(anchors, list) or len(anchors) < 3:
        raise FixedCameraKeyboardAnchorPackageError(
            "at least three anchors are required")

    copied_anchors: list[dict[str, Any]] = []
    for anchor in anchors:
        if not isinstance(anchor, Mapping):
            raise FixedCameraKeyboardAnchorPackageError("anchor is invalid")
        point_id = anchor.get("point_id")
        xy = anchor.get("board_xy_mm")
        if not isinstance(point_id, str) or not point_id:
            raise FixedCameraKeyboardAnchorPackageError(
                "anchor point_id is required")
        if (not isinstance(xy, list) or len(xy) != 2
                or any(isinstance(value, bool)
                       or not isinstance(value, (int, float))
                       or not math.isfinite(float(value)) for value in xy)):
            raise FixedCameraKeyboardAnchorPackageError(
                f"{point_id} board_xy_mm must contain two finite numbers")
        if not (0 <= float(xy[0]) <= BOARD_WIDTH_MM
                and 0 <= float(xy[1]) <= BOARD_DEPTH_MM):
            raise FixedCameraKeyboardAnchorPackageError(
                f"{point_id} board_xy_mm lies outside the RC03 board")
        copied_anchors.append({
            "point_id": point_id,
            "board_xy_mm": [float(xy[0]), float(xy[1])],
        })

    rms_limit = _positive(
        thresholds.get("max_rms_residual_mm"), "RMS limit")
    anchor_limit = _positive(
        thresholds.get("max_anchor_residual_mm"), "anchor residual limit")
    if rms_limit > DEFAULT_RMS_LIMIT_MM or anchor_limit > DEFAULT_ANCHOR_LIMIT_MM:
        raise FixedCameraKeyboardAnchorPackageError(
            "measurement thresholds cannot exceed the governed 3 mm RMS and "
            "5 mm anchor limits")
    return {
        "schema": "rocell.fixed_camera_keyboard_board_registration_input.v1",
        "status": REVIEWED_STATUS,
        "source_kind": "independent_board_frame_measurements",
        "source_artifact_sha256": measurement_sha256,
        "bindings": {
            "elevated_validation_sha256": elevated_sha256,
            "target_profile_sha256": target_profile_sha256,
        },
        "board": {
            "width_mm": BOARD_WIDTH_MM,
            "depth_mm": BOARD_DEPTH_MM,
        },
        "anchors": copied_anchors,
        "thresholds": {
            "max_rms_residual_mm": rms_limit,
            "max_anchor_residual_mm": anchor_limit,
        },
    }


def compile_package(
    measurement: Mapping[str, Any],
    elevated: Mapping[str, Any],
    targets: Mapping[str, Any],
    *,
    measurement_sha256: str,
    elevated_sha256: str,
    target_profile_sha256: str,
) -> dict[str, Any]:
    """Build evidence and evaluate no-tool and stylus profiles together."""
    keyboard = targets.get("keyboard")
    if not isinstance(keyboard, Mapping):
        raise FixedCameraKeyboardAnchorPackageError(
            "keyboard target profile is missing")
    evidence = build_evidence(
        measurement,
        measurement_sha256=measurement_sha256,
        elevated_sha256=elevated_sha256,
        target_profile_sha256=target_profile_sha256,
    )
    evidence_raw = (json.dumps(
        evidence, sort_keys=True, separators=(",", ":")) + "\n").encode()
    evidence_sha256 = _digest(evidence_raw)
    profiles: dict[str, Any] = {}
    try:
        for profile in ("no_attachment", "stylus_attachment"):
            profiles[profile] = assess(
                evidence,
                elevated,
                keyboard,
                evidence_sha256=evidence_sha256,
                elevated_sha256=elevated_sha256,
                profile_sha256=target_profile_sha256,
                profile=profile,
            )
    except FixedCameraKeyboardBoardRegistrationError as exc:
        raise FixedCameraKeyboardAnchorPackageError(str(exc)) from exc

    ready = all(
        result["absolute_keyboard_to_board_transform_verified"]
        for result in profiles.values())
    return {
        "schema": PACKAGE_SCHEMA,
        "status": ("KEYBOARD_BOARD_REGISTRATION_PACKAGE_READY"
                   if ready else "KEYBOARD_BOARD_REGISTRATION_PACKAGE_REJECTED"),
        "measurement_sha256": measurement_sha256,
        "elevated_validation_sha256": elevated_sha256,
        "target_profile_sha256": target_profile_sha256,
        "registration_input_sha256": evidence_sha256,
        "registration_input": evidence,
        "profiles": profiles,
        "shared_keyboard_to_board_transform_verified": ready,
        "profile_separation_preserved": True,
        "motion_targets_emitted": False,
        "motion_authorized": False,
        "contact_authorized": False,
    }


def compile_files(
    measurement_path: Path,
    elevated_path: Path,
    targets_path: Path,
) -> dict[str, Any]:
    measurement, measurement_raw = _read_json(
        measurement_path, "anchor measurements")
    elevated, elevated_raw = _read_json(
        elevated_path, "elevated validation")
    targets, targets_raw = _read_json(targets_path, "target profile")
    return compile_package(
        measurement,
        elevated,
        targets,
        measurement_sha256=_digest(measurement_raw),
        elevated_sha256=_digest(elevated_raw),
        target_profile_sha256=_digest(targets_raw),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a reviewed keyboard anchor registration package")
    parser.add_argument("measurement", type=Path, nargs="?")
    parser.add_argument("elevated_validation", type=Path, nargs="?")
    parser.add_argument("targets", type=Path, nargs="?")
    parser.add_argument("--write-template", type=Path)
    args = parser.parse_args(argv)
    if args.write_template is not None:
        if any(value is not None for value in (
                args.measurement, args.elevated_validation, args.targets)):
            parser.error("--write-template cannot be combined with inputs")
        args.write_template.write_text(
            json.dumps(measurement_template(), indent=2) + "\n",
            encoding="utf-8",
        )
        return 0
    if any(value is None for value in (
            args.measurement, args.elevated_validation, args.targets)):
        parser.error("measurement, elevated_validation, and targets are required")
    result = compile_files(
        args.measurement, args.elevated_validation, args.targets)
    sys.stdout.buffer.write(
        (json.dumps(result, sort_keys=True, indent=2) + "\n").encode())
    return 0 if result["shared_keyboard_to_board_transform_verified"] else 2


__all__ = [
    "FixedCameraKeyboardAnchorPackageError",
    "build_evidence",
    "compile_files",
    "compile_package",
    "measurement_template",
]


if __name__ == "__main__":
    raise SystemExit(main())
