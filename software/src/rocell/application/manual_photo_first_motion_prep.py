"""Prepare a manual-photo live session without granting motion authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.first_motion_contract import fixed_command, fixed_limits
from rocell.application.photo_keyboard_registration import estimate_files


SCHEMA = "rocell.manual_photo_first_motion_preflight.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(annotation_path: Path, profile_path: Path, photo_path: Path) -> dict:
    """Return deterministic preparation evidence; perform no device I/O."""
    annotation_path = Path(annotation_path).resolve(strict=True)
    profile_path = Path(profile_path).resolve(strict=True)
    photo_path = Path(photo_path).resolve(strict=True)
    registration = estimate_files(annotation_path, profile_path, photo_path)
    return {
        "schema": SCHEMA,
        "status": "HOLD_FOR_LIVE_ADMISSION_INPUTS",
        "purpose": "PREPARE_ONE_SUPERVISED_WRIST_RESPONSE_EXPERIMENT",
        "manual_photo": {
            "sha256": registration["photo_sha256"],
            "bytes_verified": registration["source_photo_bytes_verified"],
            "dimensions_verified": registration["source_photo_dimensions_verified"],
            "annotation_sha256": _sha256(annotation_path),
            "profile_sha256": registration["profile_sha256"],
            "board_frame": registration["board_frame"],
            "fiducial_count": registration["fiducial_count"],
            "fiducial_max_residual_mm": registration["fiducial_max_residual_mm"],
            "housing_corner_max_residual_mm": registration["housing_corner_max_residual_mm"],
            "study_xy_margin_mm": registration["study_xy_margin_mm"],
        },
        "photo_contributes": [
            "Immutable scene record for independent human review",
            "Provisional keyboard footprint in the printed board frame",
            "Nominal key-center study coordinates for later calibration",
        ],
        "photo_cannot_establish": [
            "Current controller joint state or feedback freshness",
            "Board-to-arm or tool transform",
            "Three-dimensional cable, tool, and swept-volume clearance",
            "Contact height, key travel, or safe press force",
            "Motion authority",
        ],
        "only_prepared_physical_command": fixed_command(),
        "command_limits": fixed_limits(),
        "required_live_inputs": [
            "CURRENT_READ_ONLY_CONTROLLER_SNAPSHOT",
            "CURRENT_USB_VID_PID_AND_SERIAL_IDENTITY",
            "INDEPENDENT_WRIST_START_INTERVAL_WITHIN_MINUS5_PLUS5_DEG",
            "INDEPENDENT_DISTAL_RADIUS_AT_MOST_200_MM",
            "SECURED_INSTALLATION_AND_FULL_SWEEP_CLEARANCE_REVIEW",
            "REACHABLE_POWER_SHUTDOWN_AND_OPERATOR_PRESENT",
            "INDEPENDENT_OBSERVATION_METHOD_READY",
            "EXACT_TIMED_REQUEST_AND_AUTHENTICATED_REVIEWS",
        ],
        "live_sequence": [
            "Secure the finished board and arm; remove keyboard and loose objects from the swept area.",
            "Place the shutdown control within the attending operator's immediate reach.",
            "Acquire a read-only controller snapshot and bind the current USB device identity.",
            "Independently review wrist start angle, distal radius, cables, and gravity-drop envelope.",
            "Create and approve the short-lived exact first-motion request.",
            "Execute once: joint 4, positive 1 degree, speed 20, acceleration 1.",
            "Observe and record the response, then stop; do not continue to keyboard motion.",
        ],
        "keyboard_motion_prepared": False,
        "device_io_performed": False,
        "physical_authority": False,
        "motion_authorized": False,
    }


def write_preflight(annotation_path: Path, profile_path: Path, photo_path: Path,
                    output_path: Path) -> dict:
    result = prepare(annotation_path, profile_path, photo_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    return result
