from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from rocell.vision.fixed_camera_key_row_repeatability_v1 import compare_rows


ROOT = Path(__file__).resolve().parents[3]
RESULT = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_key_row_repeatability_2026-10-17.json"
SCHEMA = ROOT / "software/ai/schemas/fixed_camera_key_row_repeatability_v1.schema.json"


def _row(index: int, contrast: float, phase: float, observable: bool = True):
    return {
        "row_index": index, "first_key": f"FIRST{index}",
        "last_key": f"LAST{index}", "key_count": 10,
        "contrast_band_offset_mm": contrast,
        "repeated_gap_phase_offset_mm": phase, "observable": observable,
    }


def test_compare_rows_enforces_temporal_limit():
    reference = [_row(index, 0.0, 0.0) for index in range(4)]
    repeat = [_row(index, 1.0, -0.5) for index in range(4)]
    repeat[3] = _row(3, 2.001, 0.0)
    comparisons = compare_rows(reference, repeat)
    assert [row["repeatability_passed"] for row in comparisons] == [
        True, True, True, False]


def test_physical_result_is_repeatable_but_grants_no_key_authority():
    result = json.loads(RESULT.read_text())
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(result)
    assert result["row_feature_temporal_repeatability_ready"] is True
    assert max(abs(row["contrast_band_temporal_delta_mm"])
               for row in result["row_comparisons"]) == 1.667
    assert all(row["gap_phase_temporal_delta_mm"] == 0.0
               for row in result["row_comparisons"])
    assert result["individual_key_localization_ready"] is False
    assert result["board_space_motion_targets_emitted"] is False
    assert result["motion_authorized"] is False
    assert result["contact_authorized"] is False
