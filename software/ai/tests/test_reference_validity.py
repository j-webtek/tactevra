from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))
from rocell_ai.reference_validity import evaluate_reference_validity  # noqa: E402


def records():
    reference = {
        "reference_id": "commissioned-keyboard-G-v1",
        "captured_at_ms": 1_000,
        "maximum_age_ms": 604_800_000,
        "camera_calibration_sha256": "a" * 64,
        "fixture_pose_sha256": "b" * 64,
        "target_map_sha256": "c" * 64,
        "lighting_descriptor": {"luminance": 100.0, "red_green_ratio": 1.0, "blue_green_ratio": 1.0},
        "maximum_relative_lighting_drift": 0.2,
    }
    capture = {
        "frame_id": "frame-1",
        "captured_at_ms": 2_000,
        "camera_calibration_sha256": "a" * 64,
        "fixture_pose_sha256": "b" * 64,
        "target_map_sha256": "c" * 64,
        "lighting_descriptor": {"luminance": 110.0, "red_green_ratio": 1.05, "blue_green_ratio": 0.95},
    }
    return reference, capture


def test_valid_reference_passes_schema():
    reference, capture = records()
    result = evaluate_reference_validity(reference, capture)
    schema = json.loads((AI_ROOT / "schemas" / "reference_validity_v1.schema.json").read_text())
    Draft202012Validator(schema).validate(result)
    assert result["status"] == "VALID"


def test_age_camera_fixture_target_and_lighting_changes_abstain():
    reference, capture = records()
    capture["captured_at_ms"] = reference["captured_at_ms"] + reference["maximum_age_ms"] + 1
    capture["camera_calibration_sha256"] = "d" * 64
    capture["fixture_pose_sha256"] = "e" * 64
    capture["target_map_sha256"] = "f" * 64
    capture["lighting_descriptor"]["luminance"] = 150.0
    result = evaluate_reference_validity(reference, capture)
    assert result["status"] == "ABSTAIN"
    assert set(result["reasons"]) == {
        "reference_age_exceeded", "camera_calibration_changed", "fixture_pose_changed",
        "target_map_changed", "lighting_drift_exceeded",
    }
