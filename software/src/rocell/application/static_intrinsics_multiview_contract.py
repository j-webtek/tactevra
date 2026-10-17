"""Precommit the installed B0477 physical-intrinsics capture split."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "rocell.static_intrinsics_multiview_capture_contract.v1"
STATUS = "PRECOMMITTED_CAPTURE_CONTRACT_TARGET_IDENTITY_REQUIRED"
_LOCKED = Path("software/ai/eval/b0477_locked_controls_qualification_20261016.json")


class StaticIntrinsicsMultiviewContractError(ValueError):
    """The retained locked-camera input is missing or inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _read(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise StaticIntrinsicsMultiviewContractError(f"locked-camera source unavailable: {path}") from exc
    if not isinstance(value, Mapping):
        raise StaticIntrinsicsMultiviewContractError("locked-camera source must be an object")
    return value


def build_static_intrinsics_multiview_contract(workspace: Path) -> dict[str, Any]:
    """Build a fixed 24-fit/8-held-out capture schedule without device access."""

    root = Path(workspace)
    source_path = root / _LOCKED
    locked = _read(source_path)
    if locked.get("schema") != "rocell.b0477_locked_controls_qualification.v1" or locked.get("status") != "LOCKED_ELECTRONIC_CONTROLS_REOPEN_QUALIFIED_PHYSICAL_INTRINSICS_BLOCKED":
        raise StaticIntrinsicsMultiviewContractError("electronic controls are not reopen-qualified")
    camera = locked.get("camera_binding")
    if not isinstance(camera, Mapping):
        raise StaticIntrinsicsMultiviewContractError("camera binding is absent")

    regions = ("TOP_LEFT", "TOP_CENTER", "TOP_RIGHT", "MID_LEFT", "CENTER", "MID_RIGHT", "BOTTOM_LEFT", "BOTTOM_CENTER", "BOTTOM_RIGHT")
    fit_regions = tuple(regions[index % len(regions)] for index in range(24))
    held_regions = ("TOP_LEFT", "TOP_RIGHT", "MID_LEFT", "MID_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT", "TOP_CENTER", "BOTTOM_CENTER")
    slots = []
    for index in range(32):
        fit = index < 24
        ordinal = index + 1
        slots.append(
            {
                "capture_id": f"intrinsics-view-{ordinal:02d}",
                "split": "TRAINING" if fit else "HELD_OUT",
                "requested_image_region": fit_regions[index] if fit else held_regions[index - 24],
                "requested_tilt_band_deg": [5, 15] if ordinal % 3 == 1 else [16, 28] if ordinal % 3 == 2 else [29, 42],
                "requested_rotation_band_deg": [-75, -25] if ordinal % 4 == 1 else [-24, 15] if ordinal % 4 == 2 else [16, 55] if ordinal % 4 == 3 else [56, 85],
                "requested_area_fraction_band": [0.10, 0.17] if ordinal % 2 else [0.18, 0.28],
                "source_image_sha256": None,
                "observed_target_geometry": None,
            }
        )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "camera_binding": camera,
        "locked_controls_qualification": {
            "path": _LOCKED.as_posix(),
            "artifact_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "qualification_sha256": locked.get("qualification_sha256"),
        },
        "target_intake": {
            "new_target_print_requested": False,
            "accept_existing_scale_verified_planar_target": True,
            "required_before_capture": [
                "target kind and immutable identity",
                "metric feature definition and dictionary when applicable",
                "scale measurements across both target axes",
                "rigid flat backing and unchanged physical target witness",
            ],
        },
        "dataset_commitment": {
            "total_slots": 32,
            "training_slots": 24,
            "held_out_slots": 8,
            "split_frozen_before_capture": True,
            "fixed_pose_duplicates_eligible": False,
            "minimum_accepted_views": 26,
            "minimum_training_views": 20,
            "minimum_held_out_views": 6,
            "slots": slots,
        },
        "collection_rules": {
            "camera_and_board_remain_fixed": True,
            "move_target_only": True,
            "capture_mode_must_match_locked_binding": True,
            "controls_must_match_locked_binding": True,
            "one_fresh_frame_per_slot": True,
            "record_source_hash_and_observed_geometry_before_fit": True,
            "do_not_replace_rejected_slot_with_other_split": True,
            "robot_transport_opened": False,
            "robot_commands_sent": 0,
        },
        "next_action": "VERIFY_EXISTING_TARGET_IDENTITY_AND_SCALE",
        "capture_ready": False,
        "authority": {"camera_opened": False, "camera_frames_requested": 0, "robot_transport_opened": False, "robot_commands_sent": 0, "physical_authority": False},
    }
    return {**report, "contract_sha256": hashlib.sha256(_canonical(report)).hexdigest()}


__all__ = ["SCHEMA", "STATUS", "StaticIntrinsicsMultiviewContractError", "build_static_intrinsics_multiview_contract"]
