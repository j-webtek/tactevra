from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str):
    path = ROOT / f"software/integrations/isaac_sim/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUNDLE = _load("joint_schedule_replay_bundle")
REPLAY = _load("joint_schedule_isaac_replay_probe")
COMMIT = "5" * 40
JOINTS = {
    "base_link_to_link1": 0.1,
    "link1_to_link2": 0.2,
    "link2_to_link3": 0.3,
    "link3_to_link4": 0.4,
    "link4_to_link5": 0.5,
}


def _report():
    samples = []
    trajectory = []
    ik = []
    for index in range(2):
        samples.append({
            "sequence": index,
            "time_from_start_ns": index * 100,
            "phase": "CONTACT",
            "phase_endpoint": True,
            "action_index": index,
            "target_id": "H",
            "joint_positions_rad": JOINTS,
        })
        trajectory.append({
            "sequence": index,
            "phase": "CONTACT",
            "action_index": index,
            "target_id": "H",
            "point": {"frame": "board", "x": 1.0, "y": 2.0, "z": 3.0},
        })
        ik.append({
            "accepted": True,
            "hardware_commands_generated": 0,
            "position_error_mm": 0.01,
            "minimum_normalized_arm_joint_margin": 0.2,
        })
    return {
        "arm_source_commit": COMMIT,
        "geometry_variant": "UNMEASURED_SENSITIVITY_OVERLAY",
        "virtual_profile_sha256": "a" * 64,
        "ordered_target_ids": ["H", "H"],
        "batch": {"proposals": [{"target_id": "H"}, {"target_id": "H"}]},
        "trajectory": {"screening_samples": trajectory},
        "ik": {
            "status": "READY_FOR_INSTALLED_GEOMETRY_COLLISION_SCREENING",
            "joint_results": ik,
        },
        "schedule": {
            "schema": "rocell.typing_joint_schedule.v1",
            "status": "READY_FOR_INSTALLED_GEOMETRY_AND_FRESH_STATE_SCREENING",
            "hardware_access": False,
            "physical_authority": False,
            "hardware_commands_generated": 0,
            "controller_commands": [],
            "samples": samples,
            "source_trajectory_plan_sha256": "b" * 64,
            "source_ik_screen_sha256": "c" * 64,
            "profile_sha256": "d" * 64,
            "total_motion_and_dwell_time_ns": 100,
            "joint_dynamics_all_samples_accepted": True,
            "blockers": ["INSTALLED_GEOMETRY_COLLISION_SCREENING_REQUIRED"],
        },
    }


def _build(report):
    raw = json.dumps(report, sort_keys=True).encode()
    return BUNDLE.build_replay_bundle(report, raw, COMMIT)


def test_bundle_preserves_repeated_contact_order_and_zero_authority():
    bundle = _build(_report())
    assert bundle["ordered_target_ids"] == ["H", "H"]
    assert bundle["sample_count"] == 2
    assert bundle["controller_commands"] == []
    assert bundle["hardware_writes"] == 0
    assert bundle["physical_movements"] == 0
    REPLAY._validate_bundle(bundle)


@pytest.mark.parametrize("mutation", ["commit", "order", "authority", "sequence"])
def test_bundle_rejects_source_or_semantic_tampering(mutation):
    report = deepcopy(_report())
    if mutation == "commit":
        report["arm_source_commit"] = "6" * 40
    elif mutation == "order":
        report["batch"]["proposals"][1]["target_id"] = "1"
    elif mutation == "authority":
        report["schedule"]["controller_commands"] = [{"unsafe": True}]
    else:
        report["schedule"]["samples"][1]["sequence"] = 9
    with pytest.raises(ValueError):
        _build(report)


def test_isaac_intake_rejects_changed_bundle_digest():
    bundle = _build(_report())
    bundle["samples"][0]["target_id"] = "1"
    with pytest.raises(ValueError, match="digest"):
        REPLAY._validate_bundle(bundle)
