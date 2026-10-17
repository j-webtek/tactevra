from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import jsonschema
import pytest

from rocell.vision.fixed_camera_keyboard_anchor_package_v1 import (
    FixedCameraKeyboardAnchorPackageError,
    build_evidence,
    compile_package,
    main,
    measurement_template,
)


ROOT = Path(__file__).resolve().parents[3]
ELEVATED = ROOT / "software/config/calibration_candidates/rc03_int_r1_fixed_camera_elevated_key_plane_validation_2026-10-17.json"
TARGETS = ROOT / "software/config/static_nominal_target_profiles.json"
MEASUREMENT_SCHEMA = ROOT / "software/ai/schemas/fixed_camera_keyboard_anchor_measurements_v1.schema.json"
PACKAGE_SCHEMA = ROOT / "software/ai/schemas/fixed_camera_keyboard_anchor_package_v1.schema.json"
DIGEST = "a" * 64


def _measurement() -> dict:
    result = measurement_template()
    result["status"] = "REVIEWED_INDEPENDENT_BOARD_FRAME_MEASUREMENTS"
    result["review"] = {
        "reviewed": True,
        "reviewer": "workcell owner",
        "reviewed_at": "2026-10-17T17:30:00-04:00",
        "notes": "Direct edge-referenced housing measurements.",
    }
    angle = math.radians(3.0)
    local = ((0.0, 0.0), (315.0, 0.0), (315.0, 147.0), (0.0, 147.0))
    for anchor, (x, y) in zip(result["anchors"], local, strict=True):
        anchor["board_xy_mm"] = [
            x * math.cos(angle) - y * math.sin(angle) + 81.0,
            x * math.sin(angle) + y * math.cos(angle) + 72.0,
        ]
    return result


def _compile(measurement: dict | None = None) -> dict:
    elevated_raw = ELEVATED.read_bytes()
    targets_raw = TARGETS.read_bytes()
    return compile_package(
        measurement or _measurement(),
        json.loads(elevated_raw),
        json.loads(targets_raw),
        measurement_sha256=DIGEST,
        elevated_sha256=hashlib.sha256(elevated_raw).hexdigest(),
        target_profile_sha256=hashlib.sha256(targets_raw).hexdigest(),
    )


def test_reviewed_measurements_build_both_profile_results_without_authority():
    measurement = _measurement()
    jsonschema.Draft202012Validator(
        json.loads(MEASUREMENT_SCHEMA.read_text())).validate(measurement)
    package = _compile(measurement)
    jsonschema.Draft202012Validator(
        json.loads(PACKAGE_SCHEMA.read_text())).validate(package)
    assert package["shared_keyboard_to_board_transform_verified"] is True
    assert package["profiles"]["no_attachment"]["pose"] == (
        package["profiles"]["stylus_attachment"]["pose"])
    assert len(package["profiles"]["no_attachment"][
        "board_space_key_candidates"]) == 46
    assert "STYLUS_TCP_UNVERIFIED" not in package["profiles"][
        "no_attachment"]["blockers"]
    assert "STYLUS_TCP_UNVERIFIED" in package["profiles"][
        "stylus_attachment"]["blockers"]
    assert package["motion_authorized"] is False
    assert package["contact_authorized"] is False


def test_draft_template_is_intentionally_rejected(tmp_path: Path):
    output = tmp_path / "anchors.json"
    assert main(["--write-template", str(output)]) == 0
    template = json.loads(output.read_text())
    assert template["status"] == "DRAFT_UNREVIEWED"
    assert len(template["anchors"]) == 4
    with pytest.raises(FixedCameraKeyboardAnchorPackageError,
                       match="independent review"):
        build_evidence(
            template,
            measurement_sha256=DIGEST,
            elevated_sha256=DIGEST,
            target_profile_sha256=DIGEST,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["review"].update(
            {"reviewed_at": "2026-10-17T17:30:00"}), "UTC offset"),
        (lambda value: value["board"].update({"width_mm": 600.0}),
         "610 x 457"),
        (lambda value: value.update({"coordinate_frame": "camera"}),
         "RC03_board"),
        (lambda value: value["thresholds"].update(
            {"max_anchor_residual_mm": 50.0}), "cannot exceed"),
        (lambda value: value["anchors"][0].update(
            {"board_xy_mm": [-1.0, 50.0]}), "outside"),
    ],
)
def test_unqualified_measurement_metadata_is_rejected(mutation, message):
    measurement = _measurement()
    mutation(measurement)
    with pytest.raises(FixedCameraKeyboardAnchorPackageError, match=message):
        _compile(measurement)
