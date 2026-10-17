from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import jsonschema
import pytest

from rocell.vision.fixed_camera_keyboard_anchor_package_v1 import (
    compile_package as compile_keyboard_package,
    measurement_template as keyboard_measurement_template,
)
from rocell.vision.fixed_camera_keyboard_robot_localization_v1 import (
    FixedCameraKeyboardRobotLocalizationError,
    compile_localization,
    measurement_template,
)


ROOT = Path(__file__).resolve().parents[3]
ELEVATED = ROOT / (
    "software/config/calibration_candidates/"
    "rc03_int_r1_fixed_camera_elevated_key_plane_validation_2026-10-17.json")
TARGETS = ROOT / "software/config/static_nominal_target_profiles.json"
MEASUREMENT_SCHEMA = ROOT / (
    "software/ai/schemas/board_to_robot_measurements_v1.schema.json")
RESULT_SCHEMA = ROOT / (
    "software/ai/schemas/fixed_camera_keyboard_robot_localization_v1.schema.json")


def _keyboard_package() -> tuple[dict, dict]:
    elevated_raw = ELEVATED.read_bytes()
    targets_raw = TARGETS.read_bytes()
    targets = json.loads(targets_raw)
    measurement = keyboard_measurement_template()
    measurement["status"] = "REVIEWED_INDEPENDENT_BOARD_FRAME_MEASUREMENTS"
    measurement["review"] = {
        "reviewed": True,
        "reviewer": "test reviewer",
        "reviewed_at": "2026-10-17T18:00:00-04:00",
        "notes": "synthetic unit-test geometry",
    }
    angle = math.radians(3.0)
    local = ((0.0, 0.0), (315.0, 0.0), (315.0, 147.0), (0.0, 147.0))
    for anchor, (x, y) in zip(measurement["anchors"], local, strict=True):
        anchor["board_xy_mm"] = [
            x * math.cos(angle) - y * math.sin(angle) + 81.0,
            x * math.sin(angle) + y * math.cos(angle) + 72.0,
        ]
    package = compile_keyboard_package(
        measurement,
        json.loads(elevated_raw),
        targets,
        measurement_sha256="a" * 64,
        elevated_sha256=hashlib.sha256(elevated_raw).hexdigest(),
        target_profile_sha256=hashlib.sha256(targets_raw).hexdigest(),
    )
    return package, targets


def _compile(measurement: dict, package: dict, targets: dict) -> dict:
    return compile_localization(
        measurement,
        package,
        targets,
        target_profile_sha256=hashlib.sha256(TARGETS.read_bytes()).hexdigest(),
    )


def _measurement() -> dict:
    value = measurement_template()
    value["status"] = "REVIEWED_INDEPENDENT_BOARD_TO_ROBOT_MEASUREMENTS"
    value["installation"] = {
        "robot_base_identity": "ROARM-M3-S2-TEST",
        "board_identity": "RC03-INT-R1",
        "installation_unchanged": True,
        "reseat_check_passed": True,
    }
    value["review"] = {
        "reviewed": True,
        "reviewer": "test reviewer",
        "reviewed_at": "2026-10-17T18:10:00-04:00",
        "notes": "synthetic unit-test transform",
    }
    angle = math.radians(-12.0)
    rotation = (
        (math.cos(angle), -math.sin(angle), 0.0),
        (math.sin(angle), math.cos(angle), 0.0),
        (0.0, 0.0, 1.0),
    )
    translation = (305.0, -42.0, 70.0)
    points = (
        ("FIT_ORIGIN", "FIT", (0.0, 0.0, 0.0)),
        ("FIT_RIGHT", "FIT", (610.0, 0.0, 0.0)),
        ("FIT_REAR", "FIT", (0.0, 457.0, 0.0)),
        ("FIT_CENTRE", "FIT", (305.0, 228.5, 0.0)),
        ("HOLDOUT_A", "HOLDOUT", (610.0, 457.0, 0.0)),
        ("HOLDOUT_B", "HOLDOUT", (152.5, 342.75, 0.0)),
    )
    for point_id, role, board in points:
        robot = tuple(
            sum(rotation[row][column] * board[column] for column in range(3))
            + translation[row]
            for row in range(3)
        )
        value["correspondences"].append({
            "point_id": point_id,
            "role": role,
            "board_xyz_mm": list(board),
            "robot_xyz_mm": list(robot),
        })
    return value


def test_reviewed_board_transform_composes_both_profiles_without_authority():
    package, targets = _keyboard_package()
    measurement = _measurement()
    jsonschema.Draft202012Validator(
        json.loads(MEASUREMENT_SCHEMA.read_text())).validate(measurement)
    result = _compile(measurement, package, targets)
    jsonschema.Draft202012Validator(
        json.loads(RESULT_SCHEMA.read_text())).validate(result)

    assert result["board_to_robot_transform_verified"] is True
    assert result["transform"]["fit_rms_residual_mm"] == pytest.approx(0.0)
    assert len(result["profiles"]["no_attachment"][
        "robot_frame_localization_candidates"]) == 46
    assert result["profiles"]["no_attachment"]["blockers"] == [
        "PHYSICAL_CLEARANCE_UNVERIFIED"]
    assert "STYLUS_TCP_UNVERIFIED" in result["profiles"][
        "stylus_attachment"]["blockers"]
    assert result["motion_targets_emitted"] is False
    assert result["motion_authorized"] is False
    assert result["contact_authorized"] is False


def test_excessive_held_out_error_rejects_transform_and_emits_no_candidates():
    package, targets = _keyboard_package()
    measurement = _measurement()
    measurement["correspondences"][-1]["robot_xyz_mm"][0] += 8.0
    result = _compile(measurement, package, targets)

    assert result["board_to_robot_transform_verified"] is False
    assert result["profiles"]["no_attachment"][
        "robot_frame_localization_candidates"] == []
    assert "BOARD_TO_ROBOT_REGISTRATION_RESIDUAL_EXCEEDED" in result[
        "profiles"]["no_attachment"]["blockers"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update({"status": "DRAFT_UNREVIEWED"}),
         "independent review"),
        (lambda value: value["installation"].update(
            {"reseat_check_passed": False}), "reseat checks"),
        (lambda value: value["thresholds"].update(
            {"max_holdout_residual_mm": 50.0}), "cannot exceed"),
        (lambda value: value["correspondences"].__setitem__(
            1, {**value["correspondences"][1],
                "board_xyz_mm": [100.0, 0.0, 0.0]}), "span both"),
    ],
)
def test_unqualified_board_to_robot_evidence_is_rejected(mutation, message):
    package, targets = _keyboard_package()
    measurement = _measurement()
    if message == "span both":
        measurement["correspondences"][2]["board_xyz_mm"] = [200.0, 0.0, 0.0]
        measurement["correspondences"][3]["board_xyz_mm"] = [300.0, 0.0, 0.0]
    mutation(measurement)
    with pytest.raises(FixedCameraKeyboardRobotLocalizationError, match=message):
        _compile(measurement, package, targets)


def test_target_profile_hash_binding_is_enforced():
    package, targets = _keyboard_package()
    targets["keyboard"]["target_plane_z_board_mm"] += 1.0
    with pytest.raises(FixedCameraKeyboardRobotLocalizationError,
                       match="bytes differ"):
        compile_localization(
            _measurement(),
            package,
            targets,
            target_profile_sha256="b" * 64,
        )
