from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from rocell.vision.fixed_camera_key_center_candidates_v1 import compare_candidates


ROOT = Path(__file__).resolve().parents[3]
RESULT = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_key_center_candidates_2026-10-17.json"
SCHEMA = ROOT / "software/ai/schemas/fixed_camera_key_center_candidates_v1.schema.json"
PROFILE = ROOT / "software/config/static_nominal_target_profiles.json"


def _candidate(center: list[float], span: list[float]) -> dict[str, object]:
    return {
        "center_xy_mm": center,
        "edge_span_xy_mm": span,
        "minimum_edge_peak_ratio": 1.2,
    }


def test_compare_candidates_rejects_excess_temporal_delta():
    profile = json.loads(PROFILE.read_text())["keyboard"]
    keys = {
        key: _candidate([20.0, 20.0], [19.0, 19.0])
        for row in profile["rows"] for key in row["key_ids"]
    }
    keys.update({
        "TAB": _candidate([20.0, 20.0], [20.0, 19.0]),
        "ENTER": _candidate([20.0, 20.0], [26.0, 19.0]),
        "SPACE": _candidate([20.0, 20.0], [96.0, 19.0]),
    })
    repeat = json.loads(json.dumps(keys))
    repeat["A"]["center_xy_mm"] = [23.2, 20.0]
    compared = compare_candidates(keys, repeat, profile)
    by_key = {item["key_id"]: item for item in compared}
    assert by_key["A"]["candidate_repeatability_passed"] is False
    assert by_key["B"]["candidate_repeatability_passed"] is True


def test_physical_result_has_repeatable_candidates_but_no_motion_authority():
    result = json.loads(RESULT.read_text())
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(result)
    assert result["key_center_candidate_count"] == 46
    assert result["image_space_key_center_candidates_ready"] is True
    assert max(item["temporal_center_delta_mm"]
               for item in result["key_center_candidates"]) == 2.166
    assert all(item["candidate_repeatability_passed"]
               for item in result["key_center_candidates"])
    assert result["profile"] == "no_attachment"
    assert result["individual_key_localization_ready"] is False
    assert result["board_space_motion_targets_emitted"] is False
    assert result["motion_authorized"] is False
    assert result["contact_authorized"] is False
