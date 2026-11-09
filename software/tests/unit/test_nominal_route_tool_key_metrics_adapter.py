from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_tool_key_metrics_adapter.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_tool_key_metrics_adapter_review.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _authority():
    return {
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }


def _sources(module):
    route_core = {
        "schema": module.ROUTE_SCHEMA,
        "joint_order": list(module.JOINT_ORDER),
        "joint_targets": [
            {
                "sequence": index,
                "phase": "TRANSIT" if 654 <= index <= 940 else "CONTACT",
                "joint_position_target_rad": [0.0, 0.1, 0.2, 0.3, 0.4, 0.25],
            }
            for index in range(1416)
        ],
    }
    route = {**route_core, "plan_sha256": module._sha(route_core)}
    backend_core = {
        "schema": module.BACKEND_SCHEMA,
        "source_route_plan_sha256": route["plan_sha256"],
        "runtime_protocol": {
            "tool_key_metrics": "ONE_DETERMINATE_RESULT_PER_REGENERATED_ROW"
        },
        "acceptance": {"minimum_noncontact_tool_key_clearance_mm": 0.5},
    }
    backend = {**backend_core, "backend_sha256": module._sha(backend_core)}
    readiness_core = {
        "schema": module.READINESS_SCHEMA,
        "status": "READY_TO_IMPLEMENT_REMAINING_ZERO_AUTHORITY_RUNTIME_ADAPTERS",
        "source_backend_sha256": backend["backend_sha256"],
        "reviewed_methods": ["check_continuous_clearance"],
        "remaining_methods": ["regenerate_row", "measure_tool_key", "root_drift"],
        **_authority(),
    }
    readiness = {
        **readiness_core,
        "readiness_sha256": module._sha(readiness_core),
    }
    ik_core = {
        "schema": module.IK_ADAPTER_SCHEMA,
        "backend_method": "regenerate_row",
        **_authority(),
    }
    ik_adapter = {**ik_core, "adapter_sha256": module._sha(ik_core)}
    review_core = {
        "schema": module.IK_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": ik_adapter["adapter_sha256"],
        "runtime_integration_admitted": True,
        "next_required_stage": "IMPLEMENT_AND_REVIEW_TOOL_KEY_METRICS_ADAPTER",
        **_authority(),
    }
    ik_review = {
        **review_core,
        "adapter_review_sha256": module._sha(review_core),
    }
    module.EXPECTED_READINESS_SHA256 = readiness["readiness_sha256"]
    module.EXPECTED_BACKEND_SHA256 = backend["backend_sha256"]
    module.EXPECTED_ROUTE_SHA256 = route["plan_sha256"]
    module.EXPECTED_IK_ADAPTER_SHA256 = ik_adapter["adapter_sha256"]
    module.EXPECTED_IK_REVIEW_SHA256 = ik_review["adapter_review_sha256"]
    module.EXPECTED_READINESS_FILE_SHA256 = "1" * 64
    module.EXPECTED_BACKEND_FILE_SHA256 = "2" * 64
    module.EXPECTED_ROUTE_FILE_SHA256 = "3" * 64
    module.EXPECTED_IK_ADAPTER_FILE_SHA256 = "4" * 64
    module.EXPECTED_IK_REVIEW_FILE_SHA256 = "5" * 64
    module.EXPECTED_IK_SOURCE_SHA256 = "6" * 64
    module.EXPECTED_URDF_SHA256 = "7" * 64
    module.EXPECTED_MECHANICS_SOURCE_SHA256 = "8" * 64
    return readiness, backend, route, ik_adapter, ik_review


def _definition(module):
    sources = _sources(module)
    result = module.build_adapter_definition(
        *sources,
        readiness_file_sha256="1" * 64,
        backend_file_sha256="2" * 64,
        route_file_sha256="3" * 64,
        ik_adapter_file_sha256="4" * 64,
        ik_review_file_sha256="5" * 64,
        ik_source_file_sha256="6" * 64,
        urdf_file_sha256="7" * 64,
        mechanics_source_file_sha256="8" * 64,
        adapter_source_file_sha256=module._file_sha(SOURCE),
    )
    return result, sources


class _Joint:
    def __init__(self, value):
        self.value = float(value)

    @classmethod
    def radians(cls, value):
        return cls(value)


class _Vec:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class _Rotation:
    @staticmethod
    def identity():
        return _Rotation()


class _Transform:
    def __init__(self, *args, translation_mm=None, **kwargs):
        self.parent_frame = args[0] if args else "world"
        self.translation_mm = translation_mm or (
            args[3] if len(args) > 3 else _Vec(0, 0, 0)
        )

    def compose(self, other):
        left, right = self.translation_mm, other.translation_mm
        return _Transform(
            self.parent_frame,
            translation_mm=_Vec(left.x + right.x, left.y + right.y, left.z + right.z),
        )


class _Model:
    def forward_kinematics(self, state):
        assert len(state) == 6
        return {"hand_tcp": _Transform("world", translation_mm=_Vec(1, 2, 15))}


class _Solver:
    def __init__(self):
        self.model = _Model()
        self.hand_tcp_to_tip_z_mm = -5.0
        self.fixed_gripper_position = _Joint(0.25)


class _Tensor:
    def __init__(self, value):
        self.value = value

    def numpy(self):
        return self

    def tolist(self):
        return self.value


class _KeyView:
    def __init__(self, z=0.006, positions=None):
        self.z = z
        self.positions = positions

    def get_world_poses(self):
        positions = self.positions if self.positions is not None else [[0, 0, self.z]]
        return _Tensor(positions), _Tensor([[1, 0, 0, 0]])


def _types():
    return _Joint, _Transform, _Rotation, _Vec, "hand_tcp", _Solver


def _accepted_review(module, definition):
    core = {
        "schema": module.ADAPTER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": definition["adapter_sha256"],
        "runtime_integration_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "adapter_review_sha256": module._sha(core)}


def _runtime(module, monkeypatch, definition, key_view=None):
    monkeypatch.setattr(module, "_runtime_types", _types)
    return module.ToolKeyMetricsRuntimeAdapter(
        definition,
        adapter_review=_accepted_review(module, definition),
        solver=_Solver(),
        key_view=key_view or _KeyView(),
        settled_key_center_z_stage=0.006,
    )


def test_arm268_definition_pins_read_only_native_key_contract():
    module = _load("arm268_definition", SOURCE)
    result, _ = _definition(module)
    assert result["backend_method"] == "measure_tool_key"
    assert result["joint_submission_required"] is False
    assert result["key_pose_source"] == "NATIVE_RIGID_PRIM_GET_WORLD_POSES"
    assert result["key_half_height_mm"] == 3.0
    assert result["runtime_integration_admitted"] is False


def test_arm268_runtime_combines_fk_and_native_key_pose(monkeypatch):
    module = _load("arm268_runtime", SOURCE)
    definition, _ = _definition(module)
    runtime = _runtime(module, monkeypatch, definition, _KeyView(0.00598))
    result = runtime.measure_tool_key(
        sequence=654,
        joint_targets_rad=[0, 0.1, 0.2, 0.3, 0.4, 0.25],
        phase="TRANSIT",
    )
    assert result["determinate"] is True
    assert result["tool_key_clearance_mm"] == pytest.approx(1.02)
    assert result["key_displacement_mm"] == pytest.approx(0.02)


def test_arm268_runtime_fails_closed_on_native_pose_shape(monkeypatch):
    module = _load("arm268_bad_pose", SOURCE)
    definition, _ = _definition(module)
    runtime = _runtime(module, monkeypatch, definition, _KeyView(positions=[[0, 0]]))
    with pytest.raises(module.ToolKeyMetricsAdapterError, match="shape changed"):
        runtime.measure_tool_key(
            sequence=654,
            joint_targets_rad=[0, 0.1, 0.2, 0.3, 0.4, 0.25],
            phase="HOVER",
        )


def test_arm268_runtime_fails_closed_on_gripper_drift(monkeypatch):
    module = _load("arm268_gripper", SOURCE)
    definition, _ = _definition(module)
    runtime = _runtime(module, monkeypatch, definition)
    with pytest.raises(module.ToolKeyMetricsAdapterError, match="fixed gripper"):
        runtime.measure_tool_key(
            sequence=654,
            joint_targets_rad=[0, 0.1, 0.2, 0.3, 0.4, 0.3],
            phase="TRANSIT",
        )


def test_arm268_review_reproduces_and_accepts_read_only_composition(monkeypatch):
    adapter = _load("arm268_review_adapter", SOURCE)
    definition, sources = _definition(adapter)
    reviewer = _load("arm268_reviewer", REVIEW_SOURCE)
    source_sha = adapter._file_sha(SOURCE)
    reviewer.EXPECTED_ADAPTER_SHA256 = definition["adapter_sha256"]
    reviewer.EXPECTED_ADAPTER_FILE_SHA256 = "a" * 64
    reviewer.EXPECTED_ADAPTER_SOURCE_SHA256 = source_sha
    monkeypatch.setattr(reviewer, "_import_adapter", lambda path: adapter)
    result = reviewer.review_adapter(
        definition,
        *sources,
        adapter_file_sha256="a" * 64,
        adapter_source_path=SOURCE,
        readiness_file_sha256="1" * 64,
        backend_file_sha256="2" * 64,
        route_file_sha256="3" * 64,
        ik_adapter_file_sha256="4" * 64,
        ik_review_file_sha256="5" * 64,
        ik_source_file_sha256="6" * 64,
        urdf_file_sha256="7" * 64,
        mechanics_source_file_sha256="8" * 64,
    )
    assert result["status"] == "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
    assert result["offline_fk_native_key_composition_verified"] is True
    assert result["source_review"]["joint_submission_calls_absent"] is True
    assert result["next_required_stage"] == "IMPLEMENT_AND_REVIEW_ROOT_DRIFT_ADAPTER"


def test_arm268_source_surfaces_are_zero_authority():
    adapter = SOURCE.read_text(encoding="utf-8")
    review = REVIEW_SOURCE.read_text(encoding="utf-8")
    assert "from isaacsim import" not in adapter
    assert "SimulationApp(" not in adapter
    assert "import serial" not in adapter
    assert "set_dof_positions" not in adapter
    assert "set_dof_position_targets" not in adapter
    assert not any(
        line.strip() in {"import isaacsim", "import serial"}
        or line.strip().startswith("from isaacsim")
        for line in review.splitlines()
    )
