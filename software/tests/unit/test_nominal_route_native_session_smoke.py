from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = (
    ROOT
    / "software"
    / "integrations"
    / "isaac_sim"
    / "nominal_route_native_session_smoke.py"
)
SPEC = importlib.util.spec_from_file_location("native_session_smoke", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def observation():
    return {
        "isaacsim_distribution": "6.1.0.0",
        "kit_version": "107.3",
        "articulation_prim_path": "/roarm_m3",
        "actual_root_prim_path": "/roarm_m3/Geometry/world/base_link",
        "planned_root_alias": "/roarm_m3/base_link",
        "planned_root_alias_exists": False,
        "dof_names": [f"joint{i}" for i in range(1, 7)],
        "link_count": 7,
        "key_position_m": [0.224, 0.112, 0.018],
        "root_position_m": [0.305, 0.457, 0.0],
        "root_orientation_wxyz": [0.707, 0.0, 0.0, -0.707],
        "scene_query_methods": ["overlap_sphere_any", "sweep_sphere_any"],
    }


class Driver:
    def __init__(self, result=None, failure=None, start_failure=None):
        self.calls = []
        self.result = result or observation()
        self.failure = failure
        self.start_failure = start_failure

    def start(self):
        self.calls.append("start")
        if self.start_failure:
            raise self.start_failure

    def load_and_initialize(self):
        self.calls.append("load_and_initialize")
        if self.failure:
            raise self.failure
        return self.result

    def shutdown(self):
        self.calls.append("shutdown")


def test_inert_smoke_retains_zero_authority_receipt_and_shutdown(tmp_path):
    driver = Driver()
    output = tmp_path / "smoke"
    governed = tmp_path / "arm254-nominal-route-physics-attempt-001"
    result = MODULE.run_inert_smoke(
        driver, output_directory=output, governed_attempt_directory=governed
    )
    assert driver.calls == ["start", "load_and_initialize", "shutdown"]
    assert result["status"].startswith("PASS_INERT_NATIVE_SESSION")
    assert result["attempt_consumed"] is False
    assert result["worker_invoked"] is False
    assert result["backend_invoked"] is False
    assert result["physics_steps"] == 0
    assert result["joint_targets_submitted"] is False
    assert result["key_contact"] is False
    assert result["automatic_retry"] is False
    assert (output / "receipt.json").is_file()
    assert not governed.exists()


def test_inert_smoke_shutdowns_on_native_failure_without_retry(tmp_path):
    driver = Driver(failure=RuntimeError("native failure"))
    with pytest.raises(RuntimeError, match="native failure"):
        MODULE.run_inert_smoke(
            driver,
            output_directory=tmp_path / "smoke",
            governed_attempt_directory=tmp_path / "governed",
        )
    assert driver.calls == ["start", "load_and_initialize", "shutdown"]
    failure = (tmp_path / "smoke" / "receipt.json").read_text()
    assert "FAIL_INERT_NATIVE_SESSION" in failure
    assert "native failure" in failure


def test_inert_smoke_shutdowns_on_start_failure(tmp_path):
    driver = Driver(start_failure=RuntimeError("bootstrap failure"))
    with pytest.raises(RuntimeError, match="bootstrap failure"):
        MODULE.run_inert_smoke(
            driver,
            output_directory=tmp_path / "smoke",
            governed_attempt_directory=tmp_path / "governed",
        )
    assert driver.calls == ["start", "shutdown"]


def test_inert_smoke_refuses_existing_output_before_start(tmp_path):
    output = tmp_path / "smoke"
    output.mkdir()
    driver = Driver()
    with pytest.raises(MODULE.InertSmokeError, match="retry refused"):
        MODULE.run_inert_smoke(
            driver,
            output_directory=output,
            governed_attempt_directory=tmp_path / "governed",
        )
    assert driver.calls == []


def test_inert_smoke_fails_closed_when_planned_alias_exists(tmp_path):
    changed = observation()
    changed["planned_root_alias_exists"] = True
    driver = Driver(result=changed)
    with pytest.raises(MODULE.InertSmokeError, match="inventory changed"):
        MODULE.run_inert_smoke(
            driver,
            output_directory=tmp_path / "smoke",
            governed_attempt_directory=tmp_path / "governed",
        )
    assert driver.calls[-1] == "shutdown"


def test_articulation_adapter_exposes_native_link_view():
    class Native:
        def get_link_transforms(self):
            return "links"

    class Articulation:
        dof_names = ["joint1"]
        _physics_articulation_view = Native()

    adapter = MODULE.IsaacArticulationLinkView(Articulation())
    assert adapter.dof_names == ["joint1"]
    assert adapter.get_link_transforms() == "links"


def test_articulation_adapter_rejects_missing_native_method():
    class Articulation:
        _physics_articulation_view = object()

    with pytest.raises(MODULE.InertSmokeError, match="link view is unavailable"):
        MODULE.IsaacArticulationLinkView(Articulation())
