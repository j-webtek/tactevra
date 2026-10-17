from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import numpy as np

from rocell.vision.fixed_camera_key_row_observability_v1 import (
    RECTIFIED_PIXELS_PER_MM,
    assess_rectified_luminance,
)


ROOT = Path(__file__).resolve().parents[3]
TARGETS = ROOT / "software/config/static_nominal_target_profiles.json"
RESULT = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_key_row_observability_2026-10-17.json"
SCHEMA = ROOT / "software/ai/schemas/fixed_camera_key_row_observability_v1.schema.json"


def _synthetic_rectified(keyboard):
    width, depth = keyboard["device_size_mm"][:2]
    scale = RECTIFIED_PIXELS_PER_MM
    image = np.full((round(depth * scale), round(width * scale)), 8.0)
    for row in keyboard["rows"]:
        first_x, center_y = row["first_center_xy_mm"]
        step_x, _ = row["step_xy_mm"]
        count = len(row["key_ids"])
        observed_y = round((center_y - 2.0) * scale)
        image[observed_y, round((first_x - 7) * scale):
              round((first_x + (count - 1) * step_x + 7) * scale)] = 90.0
        for index in range(count - 1):
            gap_x = round((first_x + (index + 0.5) * step_x - 1.0) * scale)
            y0 = round((center_y - 6) * scale)
            y1 = round((center_y + 6) * scale) + 1
            image[y0:y1, gap_x:] += 35.0
    return image


def test_synthetic_rows_supply_contrast_and_repeated_gap_features():
    keyboard = json.loads(TARGETS.read_text())["keyboard"]
    rows = assess_rectified_luminance(_synthetic_rectified(keyboard), keyboard)
    assert len(rows) == 4
    assert all(row["observable"] for row in rows)
    assert all(abs(row["contrast_band_offset_mm"]) <= 2.1 for row in rows)
    assert all(abs(row["repeated_gap_phase_offset_mm"]) <= 1.1 for row in rows)


def test_retained_frame_result_records_observability_without_key_authority():
    result = json.loads(RESULT.read_text())
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(result)
    assert result["source_frame_bytes_verified"] is True
    assert result["standard_row_observation_count"] == 4
    assert result["image_feedback_observability_ready"] is True
    assert max(abs(row["contrast_band_offset_mm"])
               for row in result["standard_row_observations"]) == 5.0
    assert result["independent_key_center_observations_present"] is False
    assert result["individual_key_localization_ready"] is False
    assert result["board_space_motion_targets_emitted"] is False
    assert result["motion_authorized"] is False
    assert result["blockers"] == ["INDIVIDUAL_KEY_CENTERS_NOT_OBSERVED"]
