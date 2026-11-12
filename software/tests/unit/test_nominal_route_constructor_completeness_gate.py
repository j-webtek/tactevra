from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
GATE_SOURCE = INTEGRATION / "nominal_route_constructor_completeness_gate.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_constructor_completeness_gate_review.py"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_module("arm296_gate_test", GATE_SOURCE)
REVIEW = _load_module("arm296_review_test", REVIEW_SOURCE)


class _FakeComposition:
    def __init__(self):
        solver = SimpleNamespace()
        self._clearance = type("NativeClearanceRuntimeAdapter", (), {})()
        self._ik = type("CanonicalIkRowRuntimeAdapter", (), {})()
        self._metrics = type("ToolKeyMetricsRuntimeAdapter", (), {})()
        self._drift = type("RootDriftRuntimeAdapter", (), {})()
        self._ik._solver = solver
        self._metrics._solver = solver


def _solver_kwargs():
    model = SimpleNamespace(root_link="world")
    board = SimpleNamespace(parent_frame="board", child_frame="world")
    fixed = SimpleNamespace(value=0.0)
    options = SimpleNamespace(max_attempts=4, max_iterations_per_attempt=45)
    joints = {
        name: object()
        for name in (
            "base_link_to_link1",
            "link1_to_link2",
            "link2_to_link3",
            "link3_to_link4",
            "link4_to_link5",
        )
    }
    return {
        "model": model,
        "board_T_world": board,
        "hand_tcp_to_tip_z_mm": -100.0,
        "fixed_gripper_position": fixed,
        "ready_arm_joint_positions": joints,
        "gripper_bounds_rad": object(),
        "options": options,
        "joint_bounds_rad": joints,
    }


def test_arm296_crosses_constructor_boundary_without_protocol_calls(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    artifact = tmp_path / "artifact"
    binding_source = (
        repo
        / "software/integrations/isaac_sim/nominal_route_concrete_native_attempt_binding.py"
    )
    binding_source.parent.mkdir(parents=True)
    binding_source.write_text("corrected", encoding="utf-8")
    status = artifact / "arm295-nominal-route-physics-attempt-001/status.json"
    status.parent.mkdir(parents=True)
    status.write_text("{}", encoding="utf-8")
    for relative in (
        "arm272-native-runtime-factory-001/factory.json",
        "arm272-native-runtime-factory-review-001/review.json",
        "arm271-native-runtime-construction-plan-002/plan.json",
        "arm271-native-runtime-construction-plan-review-002/review.json",
    ):
        path = artifact / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(GATE, "_validate_arm295", lambda path: {})
    monkeypatch.setattr(
        GATE,
        "_file_sha",
        lambda path: GATE.EXPECTED_CORRECTED_BINDING_SOURCE_SHA256,
    )
    monkeypatch.setattr(GATE, "_load_runtime_documents", lambda paths: {})
    monkeypatch.setattr(GATE, "_build_solver_kwargs", lambda paths: _solver_kwargs())
    monkeypatch.setattr(GATE, "CompleteRuntimeComposition", _FakeComposition)

    class Factory:
        def __init__(self, legacy):
            self.calls = 0

        def __call__(self, definition, **kwargs):
            self.calls += 1
            assert kwargs["articulation"].protocol_calls == []
            assert kwargs["scene_query"].protocol_calls == []
            kwargs["key_view"].get_world_poses()
            kwargs["root_view"].get_world_poses()
            return _FakeComposition()

    monkeypatch.setattr(GATE, "CorrectedRootRuntimeFactory", Factory)
    receipt = GATE.run_constructor_completeness_gate(
        artifact_root=artifact, repo_root=repo
    )
    assert receipt["status"] == "PASS_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS"
    assert receipt["former_failure_crossed"] is True
    assert receipt["baseline_reads"] == {"key_view": 1, "root_view": 1}
    assert receipt["protocol_calls"] == {"articulation": [], "scene_query": []}
    assert receipt["attempt_consumed"] is False
    assert receipt["physics_steps"] == 0
    assert receipt["joint_targets_submitted"] is False
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False


def test_arm296_reviewer_accepts_complete_zero_authority_receipt(tmp_path, monkeypatch):
    gate_source = tmp_path / "gate.py"
    gate_source.write_text(
        "def run_constructor_completeness_gate():\n"
        "    _validate_arm295()\n"
        "    _build_solver_kwargs()\n"
        "    CorrectedRootRuntimeFactory()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        REVIEW, "EXPECTED_GATE_SOURCE_SHA256", REVIEW._file_sha(gate_source)
    )
    core = {
        "schema": REVIEW.GATE_SCHEMA,
        "gate_id": "arm296-constructor-completeness-gate-001",
        "status": "PASS_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS",
        "source_arm295_status_sha256": REVIEW.EXPECTED_ARM295_STATUS_SHA256,
        "source_corrected_binding_sha256": (
            REVIEW.EXPECTED_CORRECTED_BINDING_SOURCE_SHA256
        ),
        "former_failure_stage": "construct_runtime",
        "former_failure_crossed": True,
        "runtime_type": "CompleteRuntimeComposition",
        "component_types": {
            "clearance": "NativeClearanceRuntimeAdapter",
            "ik": "CanonicalIkRowRuntimeAdapter",
            "metrics": "ToolKeyMetricsRuntimeAdapter",
            "drift": "RootDriftRuntimeAdapter",
            "solver": "RoArmM3NumericalIk",
        },
        "solver": GATE._solver_summary(_solver_kwargs()),
        "shared_solver_identity_verified": True,
        "baseline_reads": {"key_view": 1, "root_view": 1},
        "protocol_calls": {"articulation": [], "scene_query": []},
        "attempt_consumed": False,
        "isaac_imported": False,
        "isaac_started": False,
        "scene_loaded": False,
        "physics_steps": 0,
        "runtime_methods_called": [],
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "automatic_retry": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "next_required_stage": "INDEPENDENTLY_REVIEW_ARM296_GATE_RECEIPT",
    }
    receipt = {**core, "gate_sha256": REVIEW._sha(core)}
    review = REVIEW.review_constructor_completeness_gate(
        receipt, gate_source=gate_source
    )
    assert review["status"] == ("ACCEPTED_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS")
    assert review["former_arm295_constructor_failure_crossed"] is True
    assert review["attempt_consumed"] is False
    assert review["physics_steps"] == 0


def test_arm296_gate_refuses_changed_terminal_evidence(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"status": "changed"}), encoding="utf-8")
    monkeypatch.setattr(GATE, "EXPECTED_ARM295_STATUS_SHA256", GATE._file_sha(status))
    with pytest.raises(
        GATE.ConstructorCompletenessGateError, match="terminal evidence"
    ):
        GATE._validate_arm295(status)


def test_arm296_sources_contain_no_runtime_or_hardware_authority():
    gate = GATE_SOURCE.read_text(encoding="utf-8")
    assert "import isaacsim" not in gate
    assert "SimulationApp(" not in gate
    assert "serial.Serial" not in gate
    assert "execute_backend(" not in gate
    assert "run_one_attempt(" not in gate
    assert (
        REVIEW._static_review(GATE_SOURCE)["backend_physics_and_hardware_calls_absent"]
        is True
    )
