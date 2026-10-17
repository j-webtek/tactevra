from __future__ import annotations

import json
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[3]
RESULT = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_elevated_key_plane_validation_2026-10-17.json"
SCHEMA = ROOT / "software/ai/schemas/fixed_camera_elevated_key_plane_validation_v1.schema.json"


def test_elevated_plane_result_is_complete_but_emits_no_board_targets():
    result = json.loads(RESULT.read_text())
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(result)
    assert result["key_validation_count"] == 46
    assert result["validated_key_count"] == 46
    assert result["failed_key_ids"] == []
    assert result["reference_rigid_layout"]["maximum_residual_mm"] == 3.1
    assert result["repeat_rigid_layout"]["maximum_residual_mm"] == 3.328
    assert result["space_key_elevated_plane_coherence_passed"] is True
    assert result["elevated_key_plane_coherence_ready"] is True
    assert result["absolute_keyboard_to_board_transform_verified"] is False
    assert result["board_space_motion_targets_emitted"] is False
    assert result["motion_authorized"] is False
    assert result["contact_authorized"] is False


def test_space_failure_is_isolated_to_board_plane_projection():
    result = json.loads(RESULT.read_text())
    space = next(row for row in result["key_validations"]
                 if row["key_id"] == "SPACE")
    assert space["reference_rigid_layout_residual_mm"] == 2.889
    assert space["repeat_rigid_layout_residual_mm"] < 3.0
    assert space["elevated_plane_coherence_passed"] is True
