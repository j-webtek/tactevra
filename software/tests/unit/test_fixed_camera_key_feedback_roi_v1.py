from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rocell.vision.fixed_camera_key_feedback_roi_v1 import (
    FixedCameraKeyFeedbackRoiError,
    estimate_files,
)


ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_keyboard_2026-10-17.json"
CALIBRATION = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json"
TARGETS = ROOT / "software/config/static_nominal_target_profiles.json"
SCHEMA = ROOT / "software/ai/schemas/fixed_camera_key_feedback_roi_v1.schema.json"


def test_builds_46_bounded_key_feedback_windows_without_motion_authority():
    result = estimate_files(INPUT, CALIBRATION, TARGETS)
    assert result["key_feedback_window_count"] == 46
    assert set(result["key_feedback_windows"]) >= {"Q", "A", "H", "ENTER", "SPACE"}
    assert result["key_feedback_windows"]["Q"]["nominal_center_pixel_xy"] == pytest.approx(
        [321.837, 624.517], abs=0.002)
    assert result["key_feedback_windows"]["ENTER"]["nominal_center_pixel_xy"] == pytest.approx(
        [999.734, 630.776], abs=0.002)
    assert result["key_feedback_windows"]["SPACE"]["nominal_center_pixel_xy"] == pytest.approx(
        [645.996, 765.723], abs=0.002)
    assert result["image_space_feedback_windows_ready"] is True
    assert result["independent_key_center_observations_present"] is False
    assert result["individual_key_localization_ready"] is False
    assert result["board_space_motion_targets_emitted"] is False
    assert result["contact_authorized"] is False
    assert result["motion_authorized"] is False
    assert result["blockers"] == [
        "INDEPENDENT_KEY_CENTER_OBSERVATIONS_MISSING",
        "BOARD_SPACE_INDIVIDUAL_KEY_LIMIT_NOT_MET",
    ]
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(result)


def test_every_window_is_finite_bounded_and_contains_its_center():
    result = estimate_files(INPUT, CALIBRATION, TARGETS)
    centers = set()
    for window in result["key_feedback_windows"].values():
        center_x, center_y = window["nominal_center_pixel_xy"]
        left, top, right, bottom = window["search_rect_pixel_xyxy"]
        assert 0 <= left <= center_x <= right < result["camera_width_px"]
        assert 0 <= top <= center_y <= bottom < result["camera_height_px"]
        centers.add((center_x, center_y))
    assert len(centers) == 46


def test_stylus_windows_remain_separate_and_blocked():
    result = estimate_files(INPUT, CALIBRATION, TARGETS,
                            profile="stylus_attachment")
    assert result["image_space_feedback_windows_ready"] is False
    assert result["blockers"] == [
        "INDEPENDENT_KEY_CENTER_OBSERVATIONS_MISSING",
        "BOARD_SPACE_INDIVIDUAL_KEY_LIMIT_NOT_MET",
        "STYLUS_TCP_AND_CONTACT_PROFILE_MISSING",
    ]
    assert result["motion_authorized"] is False


def test_external_source_frame_must_match_when_supplied(tmp_path):
    altered = tmp_path / "heldout.png"
    altered.write_bytes(b"not the retained frame")
    with pytest.raises(FixedCameraKeyFeedbackRoiError,
                       match="source frame bytes differ"):
        estimate_files(INPUT, CALIBRATION, TARGETS, source_frame_path=altered)
