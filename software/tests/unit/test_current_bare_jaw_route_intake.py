from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.current_bare_jaw_route_intake import (
    CurrentBareJawRouteIntakeError,
    build_current_bare_jaw_route_intake,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write(path: Path, value: object) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _with_digest(value: dict, field: str) -> dict:
    result = dict(value)
    result[field] = hashlib.sha256(_canonical(value)).hexdigest()
    return result


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    observation_path = tmp_path / "observation.json"
    draft_path = tmp_path / "draft.json"
    readiness_path = tmp_path / "readiness.json"
    observation = _with_digest(
        {
            "schema": "rocell.current_planar_keyboard_observation.v1",
            "status": "CURRENT_PLANAR_KEYBOARD_OBSERVATION_READ_ONLY",
            "workcell_epoch_id": "epoch-1",
            "inputs": {
                "selected_frame_path": "frames/frame.jpg",
                "selected_frame_sha256": "a" * 64,
            },
            "current_frame": {
                "image_size_px": [1920, 1080],
                "detected_tag_ids": [0, 1, 2, 3, 4, 5],
                "world_corner_fit_rmse_px": 6.9,
                "world_corner_fit_max_px": 17.5,
                "held_out_station_checks": {"4": {"error_px": 4.8}},
            },
            "targets": {
                "H": {
                    "board_center_xy_mm": [212.951, 149.21],
                    "current_center_px": [706.572, 670.911],
                    "current_region_corners_px": [[1.0, 2.0]] * 4,
                }
            },
            "target_count": 46,
            "scene_binding": {
                "camera_scene_agrees_with_retained_epoch": True,
                "maximum_reference_center_shift_mm": 1.5494,
            },
        },
        "observation_sha256",
    )
    observation_file_sha = _write(observation_path, observation)
    draft = _with_digest(
        {
            "schema": "rocell.current_keyboard_hover_draft.v1",
            "status": "UNSENT_CURRENT_SCENE_HOVER_DRAFT_BLOCKED_FROM_INGRESS",
            "bindings": {
                "current_observation_sha256": observation_file_sha,
                "workcell_epoch_id": "epoch-1",
                "selected_frame_sha256": "a" * 64,
                "attachment_profile": "BARE_JAW",
                "profile_id": "bare-jaw-v1",
            },
            "proposal": {
                "device": "keyboard",
                "target_id": "H",
                "interaction": "HOVER",
                "target_mm": {"x": 212.9507, "y": 149.2096, "z": 21.0},
            },
            "current_image_target": {
                "target_id": "H",
                "center_px": [706.572, 670.911],
            },
            "requested_waypoints": [
                {
                    "phase": "HOVER_DESTINATION",
                    "point_mm": {
                        "frame": "board",
                        "x": 212.9507,
                        "y": 149.2096,
                        "z": 48.7953,
                    },
                }
            ],
        },
        "draft_sha256",
    )
    _write(draft_path, draft)
    readiness = _with_digest(
        {
            "schema": "rocell.bare_jaw_route_readiness.v1",
            "bindings": {"workcell_epoch_id": "epoch-1"},
            "attachment_profiles": {
                "active": "BARE_JAW",
                "trajectory_invalidated_on_attachment_change": True,
                "pose_inheritance_allowed": False,
            },
            "observed_start": {
                "named_pose": "KEYBOARD_FORWARD_CAL_1",
                "servo_register_positions": [2052, 2149, 1956, 2550, 2227, 2041, 2042],
                "classification": "OBSERVED_CONTROLLER_REGISTERS_NOT_MODEL_JOINT_RADIANS",
            },
            "blockers": [
                "MEASURED_BOARD_TO_ARM_TRANSFORM_REQUIRED",
                "MEASURED_BARE_JAW_TCP_REQUIRED",
            ],
        },
        "readiness_sha256",
    )
    _write(readiness_path, readiness)
    return observation_path, draft_path, readiness_path


def test_current_route_intake_binds_camera_target_and_stops_before_arm_space(
    tmp_path: Path,
) -> None:
    paths = _inputs(tmp_path)
    first = build_current_bare_jaw_route_intake(*paths)
    second = build_current_bare_jaw_route_intake(*paths)

    assert first == second
    assert first["status"] == "BLOCKED_ARM_SPACE_CALIBRATION_REQUIRED"
    assert first["current_camera_evidence"]["detected_tag_ids"] == [0, 1, 2, 3, 4, 5]
    assert first["selected_target"]["target_id"] == "H"
    assert first["selected_target"]["current_center_px"] == [706.572, 670.911]
    assert first["arm_start_evidence"]["current_camera_synchronized"] is False
    assert first["screening_progress"]["selected_pixel_target_bound_to_board_hover"] is True
    assert first["screening_progress"]["board_target_projected_to_arm_frame"] is False
    assert first["screening_progress"]["ik_executed"] is False
    assert first["blockers"][0] == (
        "CURRENT_ARM_TELEMETRY_BOUND_TO_CAMERA_OBSERVATION_REQUIRED"
    )
    assert first["controller_commands"] == []
    assert first["transport_writes"] == 0
    assert first["physical_authority"] is False
    assert len(first["intake_sha256"]) == 64


def test_current_route_intake_rejects_attachment_profile_mismatch(
    tmp_path: Path,
) -> None:
    observation_path, draft_path, readiness_path = _inputs(tmp_path)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft.pop("draft_sha256")
    draft["bindings"]["attachment_profile"] = "STYLUS"
    _write(draft_path, _with_digest(draft, "draft_sha256"))

    with pytest.raises(CurrentBareJawRouteIntakeError, match="requires BARE_JAW"):
        build_current_bare_jaw_route_intake(
            observation_path, draft_path, readiness_path
        )


def test_current_route_intake_rejects_changed_observation(
    tmp_path: Path,
) -> None:
    observation_path, draft_path, readiness_path = _inputs(tmp_path)
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    observation["targets"]["H"]["current_center_px"][0] += 1.0
    _write(observation_path, observation)

    with pytest.raises(CurrentBareJawRouteIntakeError, match="embedded digest mismatch"):
        build_current_bare_jaw_route_intake(
            observation_path, draft_path, readiness_path
        )
