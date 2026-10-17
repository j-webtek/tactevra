from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rocell.vision.fixed_camera_board_key_validation_v1 import fit_rigid_board_pose


ROOT = Path(__file__).resolve().parents[3]
RESULT = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_board_key_validation_2026-10-17.json"
SCHEMA = ROOT / "software/ai/schemas/fixed_camera_board_key_validation_v1.schema.json"


def test_rigid_pose_fit_recovers_translation_and_rotation():
    nominal = {"A": (0.0, 0.0), "B": (10.0, 0.0), "C": (0.0, 10.0)}
    observed = {"A": (4.0, 7.0), "B": (4.0, 17.0), "C": (-6.0, 7.0)}
    pose, residuals = fit_rigid_board_pose(nominal, observed)
    assert pose["front_left_board_xy_mm"] == pytest.approx([4.0, 7.0])
    assert pose["yaw_deg"] == pytest.approx(90.0)
    assert pose["maximum_residual_mm"] == pytest.approx(0.0)
    assert max(residuals.values()) == pytest.approx(0.0, abs=1e-12)


def test_physical_result_narrows_but_does_not_clear_board_validation():
    result = json.loads(RESULT.read_text())
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(result)
    assert result["key_validation_count"] == 46
    assert result["validated_key_count"] == 45
    assert result["failed_key_ids"] == ["SPACE"]
    assert result["reference_rigid_pose"]["maximum_residual_mm"] == 8.048
    assert result["repeat_rigid_pose"]["maximum_residual_mm"] == 8.144
    assert result["board_plane_key_validation_ready"] is False
    assert result["independent_physical_key_measurement_present"] is False
    assert result["board_space_motion_targets_emitted"] is False
    assert result["motion_authorized"] is False
    assert result["contact_authorized"] is False
