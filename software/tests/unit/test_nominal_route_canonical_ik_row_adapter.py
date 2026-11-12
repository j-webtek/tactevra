from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_canonical_ik_row_adapter.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_canonical_ik_row_adapter_review.py"


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
    backend_core = {
        "schema": module.BACKEND_SCHEMA,
        "source_route_plan_sha256": "pending",
        "runtime_protocol": {
            "canonical_ik": "ONE_ACCEPTED_DETERMINATE_RESULT_PER_REGENERATED_ROW"
        },
    }
    rows = [
        {
            "sequence": index,
            "phase": "TRANSIT" if 654 <= index <= 940 else "CONTACT",
            "joint_position_target_rad": [0.0, 0.1, 0.2, 0.3, 0.4, 0.25],
        }
        for index in range(1416)
    ]
    route_core = {
        "schema": module.ROUTE_SCHEMA,
        "joint_order": list(module.JOINT_ORDER),
        "joint_targets": rows,
    }
    route = {**route_core, "plan_sha256": module._sha(route_core)}
    backend_core["source_route_plan_sha256"] = route["plan_sha256"]
    backend = {**backend_core, "backend_sha256": module._sha(backend_core)}
    readiness_core = {
        "schema": module.READINESS_SCHEMA,
        "status": "READY_TO_IMPLEMENT_REMAINING_ZERO_AUTHORITY_RUNTIME_ADAPTERS",
        "source_backend_sha256": backend["backend_sha256"],
        "reviewed_methods": ["check_continuous_clearance"],
        "remaining_methods": ["regenerate_row", "measure_tool_key", "root_drift"],
        "next_required_stage": "IMPLEMENT_AND_REVIEW_CANONICAL_IK_ROW_ADAPTER",
        **_authority(),
    }
    readiness = {
        **readiness_core,
        "readiness_sha256": module._sha(readiness_core),
    }
    module.EXPECTED_READINESS_SHA256 = readiness["readiness_sha256"]
    module.EXPECTED_BACKEND_SHA256 = backend["backend_sha256"]
    module.EXPECTED_ROUTE_SHA256 = route["plan_sha256"]
    module.EXPECTED_READINESS_FILE_SHA256 = "1" * 64
    module.EXPECTED_BACKEND_FILE_SHA256 = "2" * 64
    module.EXPECTED_ROUTE_FILE_SHA256 = "3" * 64
    module.EXPECTED_IK_SOURCE_SHA256 = "4" * 64
    module.EXPECTED_URDF_SHA256 = "5" * 64
    return readiness, backend, route


def _definition(module):
    readiness, backend, route = _sources(module)
    result = module.build_adapter_definition(
        readiness,
        backend,
        route,
        readiness_file_sha256="1" * 64,
        backend_file_sha256="2" * 64,
        route_file_sha256="3" * 64,
        ik_source_file_sha256="4" * 64,
        urdf_file_sha256="5" * 64,
        adapter_source_file_sha256=module._file_sha(SOURCE),
    )
    return result, readiness, backend, route


class _Joint:
    def __init__(self, value):
        self.value = float(value)

    @classmethod
    def radians(cls, value):
        return cls(value)


class _Point:
    def __init__(self, frame, x, y, z):
        self.frame, self.x, self.y, self.z = frame, x, y, z


class _Vec:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class _Rotation:
    @staticmethod
    def identity():
        return _Rotation()


class _Transform:
    def __init__(self, *args, translation_mm=None, **kwargs):
        self.parent_frame = args[0] if args else "board"
        self.translation_mm = translation_mm or (args[3] if len(args) > 3 else _Vec(0, 0, 0))

    def compose(self, other):
        a, b = self.translation_mm, other.translation_mm
        return _Transform(self.parent_frame, translation_mm=_Vec(a.x + b.x, a.y + b.y, a.z + b.z))


class _Target:
    def __init__(self, point):
        self.position_mm = point


class _Model:
    def forward_kinematics(self, state):
        assert len(state) == 6
        return {"hand_tcp": _Transform("world", translation_mm=_Vec(1, 2, 8))}


class _Solver:
    def __init__(self, converged=True):
        self.model = _Model()
        self.board_T_world = _Transform("board")
        self.hand_tcp_to_tip_z_mm = -3.0
        self.fixed_gripper_position = _Joint(0.25)
        self.converged = converged

    def solve(self, target, *, seed_joint_positions):
        assert target.position_mm.z == 5
        assert seed_joint_positions[0]["base_link_to_link1"].value == 0.0
        return SimpleNamespace(
            converged=self.converged,
            solution_arm_joint_positions=tuple(
                SimpleNamespace(name=name, position=_Joint(index / 10))
                for index, name in enumerate((
                    "base_link_to_link1", "link1_to_link2", "link2_to_link3",
                    "link3_to_link4", "link4_to_link5",
                ))
            ),
            residual=SimpleNamespace(position_error_mm=0.002),
        )


def _types():
    return (_Joint, _Point, _Transform, _Rotation, _Vec, _Target, "hand_tcp", _Solver)


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


def test_arm267_definition_pins_canonical_fk_to_ik_contract():
    module = _load("arm267_definition", SOURCE)
    result, *_ = _definition(module)
    assert result["backend_method"] == "regenerate_row"
    assert result["target_derivation"] == "SOURCE_ROW_FORWARD_KINEMATICS_TOOL_TIP_POSE"
    assert result["continuity_seed"] == "PREVIOUS_ACCEPTED_ROW_FIRST_SEED"
    assert result["runtime_integration_admitted"] is False


def test_arm267_definition_rejects_self_consistent_route_substitution():
    module = _load("arm267_drift", SOURCE)
    readiness, backend, route = _sources(module)
    route["joint_order"] = list(reversed(route["joint_order"]))
    unsigned = dict(route)
    unsigned.pop("plan_sha256")
    route["plan_sha256"] = module._sha(unsigned)
    with pytest.raises(module.CanonicalIkRowAdapterError, match="boundary changed"):
        module.build_adapter_definition(
            readiness, backend, route, readiness_file_sha256="1" * 64,
            backend_file_sha256="2" * 64, route_file_sha256="3" * 64,
            ik_source_file_sha256="4" * 64, urdf_file_sha256="5" * 64,
            adapter_source_file_sha256="6" * 64,
        )


def test_arm267_runtime_preserves_fk_pose_and_uses_previous_seed(monkeypatch):
    module = _load("arm267_runtime", SOURCE)
    definition, *_ = _definition(module)
    monkeypatch.setattr(module, "_runtime_types", _types)
    runtime = module.CanonicalIkRowRuntimeAdapter(
        definition, adapter_review=_accepted_review(module, definition), solver=_Solver()
    )
    result = runtime.regenerate_row(
        source_row={"sequence": 654, "phase": "TRANSIT", "joint_position_target_rad": [1, 1, 1, 1, 1, 0.25]},
        previous_joint_targets_rad=[0, 0.1, 0.2, 0.3, 0.4, 0.25],
    )
    assert result["accepted"] is True
    assert result["determinate"] is True
    assert result["joint_position_target_rad"] == [0, 0.1, 0.2, 0.3, 0.4, 0.25]
    assert result["position_error_mm"] == 0.002


def test_arm267_runtime_accepts_the_canonical_start_boundary(monkeypatch):
    module = _load("arm267_boundary", SOURCE)
    definition, *_ = _definition(module)
    monkeypatch.setattr(module, "_runtime_types", _types)
    runtime = module.CanonicalIkRowRuntimeAdapter(
        definition,
        adapter_review=_accepted_review(module, definition),
        solver=_Solver(),
    )
    result = runtime.regenerate_row(
        source_row={
            "sequence": 653,
            "phase": "TRANSIT",
            "joint_position_target_rad": [1, 1, 1, 1, 1, 0.25],
        },
        previous_joint_targets_rad=[0, 0.1, 0.2, 0.3, 0.4, 0.25],
    )
    assert result["sequence"] == 653


def test_arm267_runtime_fails_closed_on_no_solution(monkeypatch):
    module = _load("arm267_no_solution", SOURCE)
    definition, *_ = _definition(module)
    monkeypatch.setattr(module, "_runtime_types", _types)
    runtime = module.CanonicalIkRowRuntimeAdapter(
        definition, adapter_review=_accepted_review(module, definition), solver=_Solver(False)
    )
    with pytest.raises(module.CanonicalIkRowAdapterError, match="did not converge"):
        runtime.regenerate_row(
            source_row={"sequence": 654, "phase": "TRANSIT", "joint_position_target_rad": [1, 1, 1, 1, 1, 0.25]},
            previous_joint_targets_rad=[0, 0.1, 0.2, 0.3, 0.4, 0.25],
        )


def test_arm267_review_reproduces_and_accepts_offline_composition(monkeypatch):
    adapter = _load("arm267_review_adapter", SOURCE)
    definition, readiness, backend, route = _definition(adapter)
    reviewer = _load("arm267_reviewer", REVIEW_SOURCE)
    source_sha = adapter._file_sha(SOURCE)
    reviewer.EXPECTED_ADAPTER_SHA256 = definition["adapter_sha256"]
    reviewer.EXPECTED_ADAPTER_FILE_SHA256 = "a" * 64
    reviewer.EXPECTED_ADAPTER_SOURCE_SHA256 = source_sha
    monkeypatch.setattr(reviewer, "_import_adapter", lambda path: adapter)
    result = reviewer.review_adapter(
        definition, readiness, backend, route,
        adapter_file_sha256="a" * 64, adapter_source_path=SOURCE,
        readiness_file_sha256="1" * 64, backend_file_sha256="2" * 64,
        route_file_sha256="3" * 64, ik_source_file_sha256="4" * 64,
        urdf_file_sha256="5" * 64,
    )
    assert result["status"] == "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
    assert result["offline_fk_to_ik_composition_verified"] is True
    assert result["next_required_stage"] == "IMPLEMENT_AND_REVIEW_TOOL_KEY_METRICS_ADAPTER"


def test_arm267_source_surfaces_are_zero_authority():
    adapter = SOURCE.read_text(encoding="utf-8")
    review = REVIEW_SOURCE.read_text(encoding="utf-8")
    assert "from isaacsim import" not in adapter
    assert "SimulationApp(" not in adapter
    assert "import serial" not in adapter
    assert "from isaacsim import" not in review
    assert not any(
        line.strip() == "import isaacsim" for line in review.splitlines()
    )
