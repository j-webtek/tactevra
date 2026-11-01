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
