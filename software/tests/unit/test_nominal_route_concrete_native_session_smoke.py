from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software" / "integrations" / "isaac_sim"
SOURCE = INTEGRATION / "nominal_route_concrete_native_session_smoke.py"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))
SPEC = importlib.util.spec_from_file_location("concrete_native_session_smoke", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class View:
    prim_path = MODULE.corrected_native_metadata()["root_prim_path"]

    def __init__(self, poses):
        self.poses = poses
        self.reads = 0

    def get_world_poses(self):
        pose = self.poses[min(self.reads, len(self.poses) - 1)]
        self.reads += 1
        return pose


class Session:
    def __init__(self, after_position=None):
        quaternion = [0.6087614290087207, 0.0, 0.0, -0.7933533402912352]
        before = ([[0.385, 0.532, 0.0701]], [quaternion])
        after = (
            [after_position or [0.385, 0.532, 0.0701]],
            [[-item for item in quaternion]],
        )
        self.root = View([before, after])
        self.events = []
        self._physics_steps = 0

    def start_headless(self):
        self.events.append("start")

    def load_scene(self):
        self.events.append("load")

    def initialize_physics(self):
        self.events.append("initialize")

    def native_objects(self):
        self.events.append("objects")
        return {
            "articulation": object(),
            "scene_query": object(),
            "key_view": object(),
            "root_view": self.root,
        }

    def settle_scene(self):
        self.events.append("settle")
        self._physics_steps = 30

    @property
    def physics_steps(self):
        return self._physics_steps

    def shutdown(self):
        self.events.append("shutdown")


def test_concrete_settle_runs_exact_lifecycle_and_retains_zero_authority(tmp_path):
    session = Session()
    result = MODULE.run_concrete_settle_smoke(
        session,
        output_directory=tmp_path / "smoke",
        governed_attempt_directory=tmp_path / "governed",
    )
    assert result["status"] == "PASS_CONCRETE_NATIVE_SESSION_BOUNDED_SETTLE"
    assert session.events == [
        "start",
        "load",
        "initialize",
        "objects",
        "settle",
        "shutdown",
    ]
    assert result["physics_steps"] == 30
    assert result["joint_positions_submitted"] is False
    assert result["joint_targets_submitted"] is False
    assert result["attempt_consumed"] is False
    assert not (tmp_path / "governed").exists()


def test_concrete_settle_fails_closed_on_root_drift_and_shutdowns(tmp_path):
    session = Session(after_position=[0.386, 0.532, 0.0701])
    with pytest.raises(MODULE.ConcreteSessionSmokeError, match="acceptance"):
        MODULE.run_concrete_settle_smoke(
            session,
            output_directory=tmp_path / "smoke",
            governed_attempt_directory=tmp_path / "governed",
        )
    assert session.events[-1] == "shutdown"
    assert "FAIL_CONCRETE" in (tmp_path / "smoke" / "receipt.json").read_text()


def test_concrete_settle_refuses_existing_output_before_start(tmp_path):
    output = tmp_path / "smoke"
    output.mkdir()
    session = Session()
    with pytest.raises(MODULE.ConcreteSessionSmokeError, match="retry refused"):
        MODULE.run_concrete_settle_smoke(
            session,
            output_directory=output,
            governed_attempt_directory=tmp_path / "governed",
        )
    assert session.events == []
