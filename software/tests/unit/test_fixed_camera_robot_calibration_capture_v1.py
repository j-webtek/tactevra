from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.calibration.fixed_camera_robot_calibration_capture_v1 import (
    FixedCameraRobotCalibrationCaptureError,
    compile_campaign,
    compile_capture,
    compile_files,
    main,
)
from rocell.kinematics.firmware_reference import REFERENCE_SHA256, forward


ROOT = Path(__file__).resolve().parents[3]
INPUT_SCHEMA = ROOT / (
    "software/ai/schemas/"
    "fixed_camera_robot_calibration_capture_input_v1.schema.json")
CAPTURE_SCHEMA = ROOT / (
    "software/ai/schemas/fixed_camera_robot_calibration_capture_v1.schema.json")
MEASUREMENT_SCHEMA = ROOT / (
    "software/ai/schemas/board_to_robot_measurements_v1.schema.json")


def _feedback(joints: tuple[float, ...]) -> str:
    xyz = forward(*joints[:4])[:3]
    return json.dumps({
        "T": 1051, "x": xyz[0], "y": xyz[1], "z": xyz[2], "tit": 0.0,
        "b": joints[0], "s": joints[1], "e": joints[2], "t": joints[3],
        "r": joints[4], "g": joints[5],
    }, separators=(",", ":")) + "\n"


def _capture(
    capture_id: str = "fit-a",
    *,
    role: str = "FIT",
    board_xyz: tuple[float, float, float] = (40.0, 40.0, 0.0),
    joints: tuple[float, ...] = (0.0, 0.55, 1.1, -0.2, 0.0, 0.0),
) -> dict:
    line = _feedback(joints)
    def digest(label: str) -> str:
        return hashlib.sha256(f"{capture_id}:{label}".encode()).hexdigest()

    return {
        "schema": "rocell.fixed_camera_robot_calibration_capture_input.v1",
        "capture_id": capture_id,
        "installation_epoch_id": "rc03-installation-2026-10-17",
        "profile": "no_attachment",
        "role": role,
        "frame": {
            "capture_id": capture_id,
            "frame_sha256": digest("frame"),
            "captured_at_ns": 1_200_000_000,
            "clock_id": "host-monotonic-1",
            "camera_identity_sha256": "b" * 64,
            "settings_sha256": "c" * 64,
        },
        "board_pose": {
            "observation_sha256": digest("board-pose"),
            "frame_sha256": digest("frame"),
            "camera_intrinsics_sha256": "e" * 64,
            "tag_map_sha256": "f" * 64,
            "pose_fit_tag_ids": [0, 1, 2, 3],
            "held_out_tag_ids": [4, 5],
            "reprojection_rms_px": 0.7,
            "held_out_max_residual_px": 0.9,
        },
        "tool_reference": {
            "method": "CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE",
            "observation_sha256": digest("tool-reference"),
            "frame_sha256": digest("frame"),
            "detector_id": "rocell.bare-jaw-reference",
            "detector_version": "1.0.0",
            "configuration_sha256": "2" * 64,
            "implementation_sha256": "3" * 64,
            "board_xyz_mm": list(board_xyz),
            "uncertainty_mm": 1.2,
        },
        "robot_feedback": {
            "robot_base_identity": "ROARM-M3-S2-INSTALLED",
            "clock_id": "host-monotonic-1",
            "pre_timestamp_ns": 1_000_000_000,
            "post_timestamp_ns": 1_400_000_000,
            "pre_feedback_line": line,
            "post_feedback_line": line,
        },
        "kinematic_binding": {
            "model_id": "roarm_m3_firmware_reference_v1",
            "reference_sha256": REFERENCE_SHA256,
            "robot_frame": "robot_base",
            "endpoint_frame": "bare_jaw_reference",
        },
    }


def test_passive_capture_replays_feedback_and_emits_no_authority():
    source = _capture()
    jsonschema.Draft202012Validator(
        json.loads(INPUT_SCHEMA.read_text())).validate(source)
    result = compile_capture(source)
    jsonschema.Draft202012Validator(
        json.loads(CAPTURE_SCHEMA.read_text())).validate(result)

    assert result["status"] == "PASSIVE_CORRESPONDENCE_CAPTURED"
    assert result["correspondence"]["board_xyz_mm"] == [40.0, 40.0, 0.0]
    assert result["quality"]["maximum_joint_span_rad"] == 0.0
    assert result["quality"]["maximum_reported_fk_error_mm"] == 0.0
    assert result["hardware_access"] is False
    assert result["controller_commands"] == []
    assert result["motion_authorized"] is False
    assert result["contact_authorized"] is False


def test_campaign_builds_exact_unreviewed_measurement_draft():
    captures = [
        _capture("fit-a", board_xyz=(40.0, 40.0, 0.0)),
        _capture("fit-b", board_xyz=(560.0, 45.0, 0.0),
                 joints=(0.4, 0.55, 1.1, -0.2, 0.0, 0.0)),
        _capture("fit-c", board_xyz=(60.0, 410.0, 0.0),
                 joints=(-0.4, 0.6, 1.05, -0.2, 0.0, 0.0)),
        _capture("holdout-a", role="HOLDOUT", board_xyz=(545.0, 400.0, 0.0),
                 joints=(0.25, 0.7, 0.95, -0.3, 0.0, 0.0)),
        _capture("holdout-b", role="HOLDOUT", board_xyz=(305.0, 228.5, 0.0),
                 joints=(-0.1, 0.65, 1.0, -0.25, 0.0, 0.0)),
    ]
    result = compile_campaign(captures)
    measurement = result["measurement_draft"]
    jsonschema.Draft202012Validator(
        json.loads(MEASUREMENT_SCHEMA.read_text())).validate(measurement)

    assert result["capture_count"] == 5
    assert result["fit_count"] == 3
    assert result["holdout_count"] == 2
    assert measurement["status"] == "DRAFT_UNREVIEWED"
    assert measurement["review"]["reviewed"] is False
    assert measurement["installation"]["installation_unchanged"] is False
    assert result["stylus_profile_status"] == (
        "SEPARATE_TCP_AND_CLEARANCE_CAPTURE_REQUIRED")
    assert result["motion_targets_emitted"] is False


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update({"profile": "stylus_attachment"}),
         "no_attachment"),
        (lambda value: value["board_pose"].update({"held_out_tag_ids": [4]}),
         "tag IDs 4 and 5"),
        (lambda value: value["tool_reference"].update({"uncertainty_mm": 3.1}),
         "uncertainty exceeds"),
        (lambda value: value["robot_feedback"].update(
            {"post_timestamp_ns": 2_100_000_001}), "bracket exceeds"),
    ],
)
def test_capture_rejects_unqualified_inputs(mutate, message):
    value = _capture()
    mutate(value)
    with pytest.raises(FixedCameraRobotCalibrationCaptureError, match=message):
        compile_capture(value)


def test_capture_rejects_robot_motion_inside_bracket():
    value = _capture()
    moved = (0.03, 0.55, 1.1, -0.2, 0.0, 0.0)
    value["robot_feedback"]["post_feedback_line"] = _feedback(moved)
    with pytest.raises(FixedCameraRobotCalibrationCaptureError,
                       match="joints changed"):
        compile_capture(value)


def test_campaign_rejects_collinear_fit_observations():
    captures = [
        _capture("fit-a", board_xyz=(10.0, 10.0, 0.0)),
        _capture("fit-b", board_xyz=(20.0, 20.0, 0.0)),
        _capture("fit-c", board_xyz=(30.0, 30.0, 0.0)),
        _capture("hold-a", role="HOLDOUT", board_xyz=(40.0, 50.0, 0.0)),
        _capture("hold-b", role="HOLDOUT", board_xyz=(50.0, 60.0, 0.0)),
    ]
    with pytest.raises(FixedCameraRobotCalibrationCaptureError,
                       match="span both board axes"):
        compile_campaign(captures)


def test_campaign_rejects_camera_binding_drift():
    captures = [
        _capture("fit-a", board_xyz=(40.0, 40.0, 0.0)),
        _capture("fit-b", board_xyz=(560.0, 45.0, 0.0)),
        _capture("fit-c", board_xyz=(60.0, 410.0, 0.0)),
        _capture("hold-a", role="HOLDOUT", board_xyz=(545.0, 400.0, 0.0)),
        _capture("hold-b", role="HOLDOUT", board_xyz=(305.0, 228.5, 0.0)),
    ]
    captures[-1] = copy.deepcopy(captures[-1])
    captures[-1]["frame"]["settings_sha256"] = "9" * 64
    with pytest.raises(FixedCameraRobotCalibrationCaptureError,
                       match="bindings drifted"):
        compile_campaign(captures)


def test_campaign_rejects_reused_frame_evidence():
    captures = [
        _capture("fit-a", board_xyz=(40.0, 40.0, 0.0)),
        _capture("fit-b", board_xyz=(560.0, 45.0, 0.0)),
        _capture("fit-c", board_xyz=(60.0, 410.0, 0.0)),
        _capture("hold-a", role="HOLDOUT", board_xyz=(545.0, 400.0, 0.0)),
        _capture("hold-b", role="HOLDOUT", board_xyz=(305.0, 228.5, 0.0)),
    ]
    captures[-1]["frame"]["frame_sha256"] = captures[0]["frame"]["frame_sha256"]
    captures[-1]["board_pose"]["frame_sha256"] = captures[0]["frame"][
        "frame_sha256"]
    captures[-1]["tool_reference"]["frame_sha256"] = captures[0]["frame"][
        "frame_sha256"]
    with pytest.raises(FixedCameraRobotCalibrationCaptureError,
                       match="camera frames must be unique"):
        compile_campaign(captures)


def test_file_workflow_pins_exact_bytes_and_compiles_campaign(tmp_path):
    captures = [
        _capture("fit-a", board_xyz=(40.0, 40.0, 0.0)),
        _capture("fit-b", board_xyz=(560.0, 45.0, 0.0),
                 joints=(0.4, 0.55, 1.1, -0.2, 0.0, 0.0)),
        _capture("fit-c", board_xyz=(60.0, 410.0, 0.0),
                 joints=(-0.4, 0.6, 1.05, -0.2, 0.0, 0.0)),
        _capture("holdout-a", role="HOLDOUT", board_xyz=(545.0, 400.0, 0.0),
                 joints=(0.25, 0.7, 0.95, -0.3, 0.0, 0.0)),
        _capture("holdout-b", role="HOLDOUT", board_xyz=(305.0, 228.5, 0.0),
                 joints=(-0.1, 0.65, 1.0, -0.25, 0.0, 0.0)),
    ]
    paths = []
    pins = []
    for index, capture in enumerate(captures):
        payload = (json.dumps(capture, sort_keys=True) + "\n").encode()
        path = tmp_path / f"capture-{index}.json"
        path.write_bytes(payload)
        paths.append(path)
        pins.append(hashlib.sha256(payload).hexdigest())

    result = compile_files(paths, campaign=True, expected_sha256s=pins)
    assert result["status"] == "MEASUREMENT_DRAFT_READY_FOR_INDEPENDENT_REVIEW"
    assert result["capture_count"] == 5

    with pytest.raises(FixedCameraRobotCalibrationCaptureError,
                       match="SHA-256 mismatch"):
        compile_files(paths, campaign=True, expected_sha256s=["0" * 64] * 5)


def test_file_workflow_rejects_duplicate_keys_and_cli_reports_error(
    tmp_path, capsys,
):
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(FixedCameraRobotCalibrationCaptureError,
                       match="duplicate JSON key"):
        compile_files([duplicate], campaign=False)

    assert main([str(duplicate)]) == 2
    assert "duplicate JSON key" in capsys.readouterr().err
