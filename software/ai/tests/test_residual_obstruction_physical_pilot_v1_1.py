import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "software" / "ai" / "eval" / "build_residual_obstruction_physical_pilot_v1_1.py"
SPEC = importlib.util.spec_from_file_location("physical_pilot_v1_1", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
PILOT = ROOT / "software" / "ai" / "eval" / "residual_obstruction_physical_pilot_v1.json"
PILOT_V1_1 = ROOT / "software" / "ai" / "eval" / "residual_obstruction_physical_pilot_v1_1.json"
COMMIT = "09303487afcf6abe840d727efdcb245971e2010a"
SENSOR_NOISE_COMMIT = "6d0f43061edec0e0b8141b2f7e05176de20e8c93"


def test_amendment_requires_post_isolation_pose_and_limits_escrow_claims():
    result = MODULE.build(PILOT, COMMIT)
    pose = result["post_isolation_pose_binding"]
    assert pose["primary_method"] == "PARK_SILHOUETTE_MATCH_AFTER_ISOLATION"
    assert pose["commanded_joint_state_prohibited"] is True
    assert pose["silhouette_tolerance_value"] is None
    assert pose["every_image_binds_pose_evidence_sha256"] is True
    assert result["sag_interpretation"]["post_isolation_pose_is_the_capture_pose"] is True
    escrow = result["escrow_scope"]
    assert escrow["purpose"] == "REAL_WORLD_SANITY_CHECK_ONLY"
    assert escrow["statistical_gate"] is False
    assert escrow["two_percent_miss_rate_claim_permitted"] is False
    assert escrow["powered_real_evaluation_is_separate_future_capture"] is True
    assert result["hardware_writes"] == result["physical_movements"] == 0


def test_amendment_rejects_opened_escrow(tmp_path):
    changed = copy.deepcopy(json.loads(PILOT.read_text(encoding="utf-8")))
    changed["data_use"]["escrow_pixels_opened"] = True
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="escrow was opened"):
        MODULE.build(path, COMMIT)


def test_amendment_rejects_physical_effect_claim(tmp_path):
    changed = copy.deepcopy(json.loads(PILOT.read_text(encoding="utf-8")))
    changed["physical_movements"] = 1
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="physical effects"):
        MODULE.build(path, COMMIT)


def test_amendment_measures_delivered_noise_without_guessing_signal_floor():
    result = MODULE.build_sensor_noise_amendment(PILOT_V1_1, SENSOR_NOISE_COMMIT)
    mode = result["camera_mode_binding"]
    assert (mode["width_px"], mode["height_px"], mode["pixel_format"], mode["nominal_fps"]) == (
        5472, 3648, "YUY2", 9,
    )
    capture = result["sensor_noise_capture"]
    assert capture["lighting_levels"] == ["MEASURED_LOW", "MEASURED_NOMINAL", "MEASURED_HIGH"]
    assert capture["settling_frames_discarded_per_level"] == 8
    assert capture["retained_frames_per_level"] == 32
    assert result["sensor_noise_analysis"]["channels"] == ["Y", "U", "V"]
    assert result["simulation_binding"]["jpeg_intermediate_prohibited"] is True
    assert result["signal_floor"]["selected"] is False
    assert result["signal_floor"]["intensity_levels"] is None
    assert result["signal_floor"]["noise_multiplier"] is None
    assert result["hardware_writes"] == result["physical_movements"] == 0


def test_sensor_noise_amendment_rejects_opened_escrow(tmp_path):
    changed = copy.deepcopy(json.loads(PILOT_V1_1.read_text(encoding="utf-8")))
    changed["escrow_scope"]["pixels_opened"] = True
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="escrow was opened"):
        MODULE.build_sensor_noise_amendment(path, SENSOR_NOISE_COMMIT)


def test_sensor_noise_amendment_rejects_source_without_pose_check(tmp_path):
    changed = copy.deepcopy(json.loads(PILOT_V1_1.read_text(encoding="utf-8")))
    changed["status"] = "READY_FOR_DEENERGIZED_CAPTURE"
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="post-isolation pose"):
        MODULE.build_sensor_noise_amendment(path, SENSOR_NOISE_COMMIT)
