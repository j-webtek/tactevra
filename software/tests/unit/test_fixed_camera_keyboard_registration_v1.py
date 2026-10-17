from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.vision.fixed_board_plane_calibration_v1 import (
    load_fixed_board_plane_calibration_v1,
)
from rocell.vision.fixed_camera_keyboard_registration_v1 import (
    FixedCameraKeyboardRegistrationError,
    estimate_fixed_camera_keyboard_registration_v1,
    estimate_files,
)


ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_keyboard_2026-10-17.json"
CALIBRATION = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json"
TARGETS = ROOT / "software/config/static_nominal_target_profiles.json"


def _materials():
    input_raw = INPUT.read_bytes()
    calibration_raw = CALIBRATION.read_bytes()
    target_raw = TARGETS.read_bytes()
    return (
        json.loads(input_raw), hashlib.sha256(input_raw).hexdigest(),
        load_fixed_board_plane_calibration_v1(CALIBRATION),
        hashlib.sha256(calibration_raw).hexdigest(), json.loads(target_raw),
        hashlib.sha256(target_raw).hexdigest(),
    )


def _estimate(document=None, *, profile="no_attachment"):
    values = list(_materials())
    if document is not None:
        values[0] = document
    return estimate_fixed_camera_keyboard_registration_v1(
        values[0], input_sha256=values[1], calibration=values[2],
        calibration_sha256=values[3], profile_document=values[4],
        profile_sha256=values[5], profile=profile,
        source_frame_verified=False,
    )


def test_held_out_frame_registers_keyboard_region_but_not_individual_keys():
    result = estimate_files(INPUT, CALIBRATION, TARGETS)
    assert result["camera_and_board_temporal_check_passed"] is True
    assert result["world_tag_center_max_error_mm"] == pytest.approx(0.664)
    assert result["station_tag_center_max_drift_px"] == pytest.approx(0.431)
    assert result["fitted_front_left_board_xy_mm"] == pytest.approx([110.29, 68.29])
    assert result["fitted_yaw_deg"] == pytest.approx(2.48)
    assert result["housing_corner_max_residual_mm"] == pytest.approx(13.38)
    assert result["keyboard_region_localization_ready"] is True
    assert result["individual_key_localization_ready"] is False
    assert result["actual_key_centers_measured"] is False
    assert result["motion_authorized"] is False
    assert result["nominal_key_centers_board_xy_mm"]["H"] == pytest.approx(
        [238.73, 142.91])
    schema = json.loads((ROOT / "software/ai/schemas/fixed_camera_keyboard_registration_assessment_v1.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(result)


def test_stylus_profile_remains_separate_and_blocked():
    result = _estimate(profile="stylus_attachment")
    assert result["keyboard_region_localization_ready"] is False
    assert result["individual_key_localization_ready"] is False
    assert result["profile_blockers"] == [
        "STYLUS_TCP_AND_CONTACT_PROFILE_MISSING"]
    assert result["motion_authorized"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item["detected_world_tag_centers_px"]["1"].__setitem__(0, 1300),
         "world-tag residual"),
        (lambda item: item["detected_station_tag_centers_px"]["4"].__setitem__(0, 760),
         "station-tag drift"),
        (lambda item: item["keyboard_corners_px"].update(front_left=[100, 1000]),
         "housing fit"),
        (lambda item: item["bindings"]["target_profile"].update(sha256="0" * 64),
         "target profile digest differs"),
    ],
)
def test_drift_crossed_binding_or_incoherent_housing_fails_closed(mutation, message):
    document = copy.deepcopy(_materials()[0])
    mutation(document)
    with pytest.raises(FixedCameraKeyboardRegistrationError, match=message):
        _estimate(document)


def test_external_source_frame_bytes_must_match_when_supplied(tmp_path):
    altered = tmp_path / "heldout.png"
    altered.write_bytes(b"not the retained frame")
    with pytest.raises(FixedCameraKeyboardRegistrationError,
                       match="source frame bytes differ"):
        estimate_files(INPUT, CALIBRATION, TARGETS, source_frame_path=altered)
