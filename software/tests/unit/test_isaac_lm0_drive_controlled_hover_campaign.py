import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software" / "integrations" / "isaac_sim" / "drive_controlled_hover_campaign.py"
SPEC = importlib.util.spec_from_file_location("drive_controlled_hover_campaign", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _signed_trial(error: float = 0.0002) -> dict:
    trial = {
        "schema": MODULE.INPUT_SCHEMA,
        "status": "PASS",
        "source_bindings": {"usd_sha256": "a", "bundle_file_sha256": "b", "profile_file_sha256": "c"},
        "physics_steps": 270,
        "state_teleports_after_initialization": 0,
        "target": [0.0] * 6,
        "maximum_final_joint_error_rad": error,
        "threshold_rad": 0.001,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    trial["receipt_sha256"] = MODULE._digest(MODULE._canonical(trial))
    return trial


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_three_bound_trials_produce_repeatability_receipt(tmp_path):
    paths = [_write(tmp_path / f"trial-{index}.json", _signed_trial()) for index in range(3)]
    result = MODULE.build_campaign(paths, minimum_trials=3, maximum_error_spread_rad=1e-9)
    assert result["status"] == "PASS_REPEATABLE_GRAVITY_OFF_DRIVE_CONTROL"
    assert result["trial_count"] == 3
    assert result["final_joint_error_spread_rad"] == 0.0
    assert result["hardware_access"] is False


def test_tampered_or_mismatched_trial_is_rejected(tmp_path):
    valid = _signed_trial()
    tampered = copy.deepcopy(valid)
    tampered["maximum_final_joint_error_rad"] = 0.0003
    paths = [_write(tmp_path / "valid.json", valid), _write(tmp_path / "tampered.json", tampered)]
    with pytest.raises(ValueError, match="digest mismatch"):
        MODULE.build_campaign(paths, minimum_trials=2, maximum_error_spread_rad=1e-9)


def test_retained_campaign_receipt_is_intact_and_zero_authority():
    path = (
        ROOT
        / "software"
        / "integrations"
        / "isaac_sim"
        / "evidence"
        / "drive_controlled_hover_campaign_20261101.json"
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))
    claimed = receipt.pop("campaign_receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS_REPEATABLE_GRAVITY_OFF_DRIVE_CONTROL"
    assert receipt["trial_count"] == 3
    assert receipt["final_joint_error_spread_rad"] == 0.0
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
