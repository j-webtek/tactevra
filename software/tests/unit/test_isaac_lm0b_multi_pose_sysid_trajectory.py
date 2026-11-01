import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "software" / "integrations" / "isaac_sim"
SCRIPT = SCRIPT_DIR / "multi_pose_sysid_trajectory_probe.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("multi_pose_sysid_trajectory_probe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

EVIDENCE = SCRIPT_DIR / "evidence"
BUNDLE = EVIDENCE / "actual_emitter_joint_schedule_bundle_9e5c878_20260929.json"


def test_selects_one_governed_endpoint_for_each_pose():
    sequence = MODULE.select_pose_sequence(json.loads(BUNDLE.read_text(encoding="utf-8")))
    assert [row["pose_id"] for row in sequence] == ["PARK", "H", "1", "PERIOD"]
    assert all(len(row["target_rad"]) == 6 for row in sequence)
    assert all(row["target_rad"][-1] == 0.0 for row in sequence)
    assert len({tuple(row["target_rad"]) for row in sequence}) == 4


def test_independent_sine_sequence_excites_every_joint_separately():
    sequence = MODULE.select_pose_sequence(json.loads(BUNDLE.read_text(encoding="utf-8")))
    segments = MODULE.build_independent_sine_sequence(sequence[1]["target_rad"], steps_per_joint=360, dt=1 / 120)
    assert [row["joint_index"] for row in segments] == list(range(6))
    assert all(len(row["targets_rad"]) == 360 for row in segments)
    for segment in segments:
        varying = {
            index
            for index in range(6)
            if max(row[index] for row in segment["targets_rad"])
            - min(row[index] for row in segment["targets_rad"])
            > 1e-6
        }
        assert varying == {segment["joint_index"]}
        assert min(row[5] for row in segment["targets_rad"]) >= 0.0


def test_independent_chirp_sequence_is_smooth_bounded_and_nonperiodic():
    sequence = MODULE.select_pose_sequence(json.loads(BUNDLE.read_text(encoding="utf-8")))
    segments = MODULE.build_independent_chirp_sequence(sequence[1]["target_rad"], steps_per_joint=480, dt=1 / 120)
    assert [row["joint_index"] for row in segments] == list(range(6))
    for segment in segments:
        targets = segment["targets_rad"]
        joint = segment["joint_index"]
        assert len(targets) == 480
        assert targets[0][joint] == targets[-1][joint]
        assert max(abs(targets[i + 1][joint] - targets[i][joint]) for i in range(419)) < 0.03
        assert segment["frequency_hz"]["end"] > segment["frequency_hz"]["start"]
        assert min(row[5] for row in targets) >= 0.0


def test_retained_multi_pose_receipt_and_csv_outputs_are_bound():
    receipt = json.loads((EVIDENCE / "geometry_prior_multi_pose_sysid_trajectory_20261101.json").read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS"
    assert receipt["pose_order"] == ["PARK", "H", "1", "PERIOD"]
    assert receipt["samples"] == 960
    assert receipt["state_teleports_after_initialization"] == 0
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
    assert receipt["effort_semantics"]["applied_actuation_force_nm"] == (
        "ISAAC_EXPLICIT_ACTUATION_FORCE_NOT_INTERNAL_DRIVE_OUTPUT"
    )
    assert receipt["effort_semantics"]["physical_t1051_load"] == "NOT_CAPTURED_OR_CALIBRATED"
    assert receipt["outputs"]["isaac_sysid_loader_readback"] == {
        "extension": "isaacsim.robot_setup.sysid",
        "num_joints": 6,
        "samples": 960,
        "duration_s": 7.991666666666666,
        "positions_shape": [960, 6],
        "commands_shape": [960, 6],
    }

    telemetry = EVIDENCE / "geometry_prior_multi_pose_telemetry_20261101.csv"
    sysid = EVIDENCE / "geometry_prior_multi_pose_sysid_20261101.csv"
    assert MODULE._digest(telemetry.read_bytes()) == receipt["outputs"]["rich_telemetry_csv_sha256"]
    assert MODULE._digest(sysid.read_bytes()) == receipt["outputs"]["isaac_sysid_csv_sha256"]
    with sysid.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == (
        ["time"]
        + [f"q{i}" for i in range(1, 7)]
        + [f"dq{i}" for i in range(1, 7)]
        + [f"cmd{i}" for i in range(1, 7)]
    )
    assert len(rows) == receipt["samples"] + 1
    timestamps = [float(row[0]) for row in rows[1:]]
    assert all(right > left for left, right in zip(timestamps, timestamps[1:]))


def test_retained_independent_excitation_covers_all_six_joints():
    receipt = json.loads((EVIDENCE / "independent_joint_excitation_20261101.json").read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS"
    assert receipt["trajectory"] == "independent-sine"
    assert receipt["samples"] == 2160
    assert receipt["pose_order"] == [f"SINE_J{i}" for i in range(1, 7)]
    assert receipt["telemetry_quality"]["weak_excitation_joint_indices"] == []
    assert receipt["telemetry_quality"]["error_count"] == 0
    assert receipt["telemetry_quality"]["train_chunk_count"] == 5
    assert receipt["telemetry_quality"]["validation_chunk_count"] == 1
    assert min(receipt["telemetry_quality"]["excitation_range_by_joint"]) > 0.38
    assert receipt["maximum_final_joint_error_rad"] < receipt["threshold_rad"]
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
    telemetry = EVIDENCE / "independent_joint_excitation_telemetry_20261101.csv"
    sysid = EVIDENCE / "independent_joint_excitation_sysid_20261101.csv"
    assert MODULE._digest(telemetry.read_bytes()) == receipt["outputs"]["rich_telemetry_csv_sha256"]
    assert MODULE._digest(sysid.read_bytes()) == receipt["outputs"]["isaac_sysid_csv_sha256"]


def test_retained_chirp_disambiguates_common_lag_from_periodic_alias():
    receipt = json.loads((EVIDENCE / "independent_joint_chirp_20261101.json").read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS"
    assert receipt["trajectory"] == "independent-chirp"
    assert receipt["samples"] == 2880
    quality = receipt["telemetry_quality"]
    assert quality["weak_excitation_joint_indices"] == []
    assert quality["error_count"] == 0
    lag = quality["command_lag"]
    assert 0.08 < lag["common_mode_lag_seconds"] < 0.095
    assert lag["residual_spread_samples"] < 0.3
    assert all(row["correlation_peak"] > 0.999 for row in lag["joints"])
    assert receipt["maximum_final_joint_error_rad"] < receipt["threshold_rad"]
    telemetry = EVIDENCE / "independent_joint_chirp_telemetry_20261101.csv"
    sysid = EVIDENCE / "independent_joint_chirp_sysid_20261101.csv"
    assert MODULE._digest(telemetry.read_bytes()) == receipt["outputs"]["rich_telemetry_csv_sha256"]
    assert MODULE._digest(sysid.read_bytes()) == receipt["outputs"]["isaac_sysid_csv_sha256"]
