from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import jsonschema
import pytest

from rocell.vision.fixed_camera_keyboard_board_registration_v1 import (
    FixedCameraKeyboardBoardRegistrationError,
    assess,
)


ROOT = Path(__file__).resolve().parents[3]
ELEVATED = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_elevated_key_plane_validation_2026-10-17.json"
TARGETS = ROOT / "software/config/static_nominal_target_profiles.json"
SCHEMA = ROOT / "software/ai/schemas/fixed_camera_keyboard_board_registration_v1.schema.json"
DIGEST = "a" * 64


def _fixture(*, bad_anchor: bool = False) -> tuple[dict, dict, dict]:
    elevated = json.loads(ELEVATED.read_text())
    targets = json.loads(TARGETS.read_text())
    local = {
        "HOUSING_FRONT_LEFT": (0.0, 0.0),
        "HOUSING_FRONT_RIGHT": (315.0, 0.0),
        "HOUSING_REAR_LEFT": (0.0, 147.0),
        "HOUSING_REAR_RIGHT": (315.0, 147.0),
    }
    angle = math.radians(4.0)
    anchors = []
    for point_id, (x, y) in local.items():
        bx = x * math.cos(angle) - y * math.sin(angle) + 82.0
        by = x * math.sin(angle) + y * math.cos(angle) + 71.0
        if bad_anchor and point_id == "HOUSING_REAR_RIGHT":
            bx += 18.0
        anchors.append({"point_id": point_id, "board_xy_mm": [bx, by]})
    evidence = {
        "schema": "rocell.fixed_camera_keyboard_board_registration_input.v1",
        "status": "REVIEWED_INDEPENDENT_BOARD_FRAME_MEASUREMENTS",
        "source_kind": "independent_board_frame_measurements",
        "source_artifact_sha256": "b" * 64,
        "bindings": {
            "elevated_validation_sha256": hashlib.sha256(
                ELEVATED.read_bytes()).hexdigest(),
            "target_profile_sha256": hashlib.sha256(
                TARGETS.read_bytes()).hexdigest(),
        },
        "board": {"width_mm": 610.0, "depth_mm": 457.0},
        "anchors": anchors,
        "thresholds": {
            "max_rms_residual_mm": 3.0,
            "max_anchor_residual_mm": 5.0,
        },
    }
    return evidence, elevated, targets["keyboard"]


def _assess(profile: str = "no_attachment", *, bad_anchor: bool = False) -> dict:
    evidence, elevated, keyboard = _fixture(bad_anchor=bad_anchor)
    return assess(
        evidence, elevated, keyboard,
        evidence_sha256=DIGEST,
        elevated_sha256=evidence["bindings"]["elevated_validation_sha256"],
        profile_sha256=evidence["bindings"]["target_profile_sha256"],
        profile=profile,
    )


def test_independent_anchors_emit_46_candidates_without_motion_authority():
    result = _assess()
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(result)
    assert result["absolute_keyboard_to_board_transform_verified"] is True
    assert result["pose"]["front_left_board_xy_mm"] == [82.0, 71.0]
    assert result["pose"]["yaw_deg"] == 4.0
    assert len(result["board_space_key_candidates"]) == 46
    assert result["motion_targets_emitted"] is False
    assert result["motion_authorized"] is False
    assert result["contact_authorized"] is False


def test_stylus_profile_retains_tcp_and_trajectory_blockers():
    result = _assess("stylus_attachment")
    assert result["absolute_keyboard_to_board_transform_verified"] is True
    assert "STYLUS_TCP_UNVERIFIED" in result["blockers"]
    assert "STYLUS_TRAJECTORY_UNVERIFIED" in result["blockers"]
    assert result["motion_authorized"] is False


def test_excessive_anchor_residual_rejects_candidates():
    result = _assess(bad_anchor=True)
    assert result["absolute_keyboard_to_board_transform_verified"] is False
    assert result["board_space_key_candidates"] == []
    assert "KEYBOARD_TO_BOARD_REGISTRATION_RESIDUAL_EXCEEDED" in result["blockers"]


def test_collinear_anchors_are_rejected():
    evidence, elevated, keyboard = _fixture()
    evidence["anchors"] = evidence["anchors"][:2] + [{
        "point_id": "SPACE", "board_xy_mm": [220.0, 71.0]}]
    keyboard["explicit_targets"]["SPACE"]["center_xy_mm"] = [139.0, 0.0]
    with pytest.raises(FixedCameraKeyboardBoardRegistrationError,
                       match="span two keyboard-plane axes"):
        assess(
            evidence, elevated, keyboard,
            evidence_sha256=DIGEST,
            elevated_sha256=evidence["bindings"]["elevated_validation_sha256"],
            profile_sha256=evidence["bindings"]["target_profile_sha256"],
            profile="no_attachment",
        )
