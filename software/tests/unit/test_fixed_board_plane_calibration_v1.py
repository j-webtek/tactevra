from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
import jsonschema

from rocell.vision.fixed_board_plane_calibration_v1 import (
    CameraModeV1,
    FixedBoardPlaneCalibrationError,
    load_fixed_board_plane_calibration_v1,
    parse_fixed_board_plane_calibration_v1,
)


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = (
    ROOT / "software/config/calibration_candidates"
    / "rc03_int_r1_fixed_board_plane_2026-10-17.json"
)


def _document() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_candidate_manifest_binds_repository_artifact_and_external_original():
    raw = ARTIFACT.read_bytes()
    manifest = json.loads(ARTIFACT.with_suffix(".manifest.json").read_text(
        encoding="utf-8"))
    assert manifest["artifact"] == {
        "path": ARTIFACT.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    original = manifest["externally_retained_sources"][0]
    assert original == {
        "name": "board-plane-homography.json",
        "bytes": 3937,
        "sha256": "bb6a16ad8fb9460cd7ccbf58aa4ed7ddad595fca909c6e4d68769507acacc73b",
    }


def test_retained_candidate_projects_pixels_and_admits_only_bare_jaw():
    calibration = load_fixed_board_plane_calibration_v1(ARTIFACT)
    assert calibration.camera_mode == CameraModeV1(
        "DirectShow", 1920, 1080, "YUY2", 60.0)
    assert calibration.world_tags_used == (1, 2, 3)
    assert calibration.rms_error_mm == pytest.approx(3.533161024549304)
    board = calibration.project_pixel(749.75, 408.75)
    assert board == pytest.approx((266.17326485013217, 251.72262730620338))

    bare = calibration.assess(
        observed_mode=calibration.camera_mode,
        profile="no_attachment",
        camera_and_board_fixed=True,
    ).to_dict()
    assert bare["guarded_localization_ready"] is True
    assert bare["open_loop_contact_authorized"] is False
    assert bare["motion_authorized"] is False
    assert bare["blockers"] == []
    schema = json.loads((
        ROOT / "software/ai/schemas/fixed_board_plane_assessment_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(bare)

    stylus = calibration.assess(
        observed_mode=calibration.camera_mode,
        profile="stylus_attachment",
        camera_and_board_fixed=True,
    ).to_dict()
    assert stylus["guarded_localization_ready"] is False
    assert stylus["blockers"] == ["STYLUS_TCP_AND_CONTACT_PROFILE_MISSING"]
    jsonschema.Draft202012Validator(schema).validate(stylus)


def test_mode_or_installation_drift_fails_closed():
    calibration = load_fixed_board_plane_calibration_v1(ARTIFACT)
    result = calibration.assess(
        observed_mode=CameraModeV1("DirectShow", 1280, 720, "YUY2", 60.0),
        profile="no_attachment",
        camera_and_board_fixed=False,
    ).to_dict()
    assert result["guarded_localization_ready"] is False
    assert result["blockers"] == [
        "CAMERA_MODE_DRIFT", "CAMERA_OR_BOARD_MOVED"]
    with pytest.raises(FixedBoardPlaneCalibrationError, match="camera frame"):
        calibration.project_pixel(1920, 100)
    with pytest.raises(FixedBoardPlaneCalibrationError, match="board plane"):
        calibration.project_pixel(0, 0)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item.update(safe_for_open_loop_contact=True),
         "open-loop contact must remain disabled"),
        (lambda item: item["fit"].update(max_error_mm=6.01),
         "residual exceeds"),
        (lambda item: item["profiles"]["stylus_attachment"].update(
            status="ready for guarded camera-feedback integration"),
         "stylus profile must remain pending"),
        (lambda item: item.update(pixel_to_board_homography=[
            [1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [0.0, 0.0, 1.0]]),
         "singular"),
    ],
)
def test_unsafe_candidate_variants_are_rejected(mutation, message):
    document = _document()
    mutation(document)
    with pytest.raises(FixedBoardPlaneCalibrationError, match=message):
        parse_fixed_board_plane_calibration_v1(
            document, artifact_sha256="0" * 64)
