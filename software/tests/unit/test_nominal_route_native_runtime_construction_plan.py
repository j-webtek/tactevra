from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_native_runtime_construction_plan.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_native_runtime_construction_plan_review.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _authority() -> dict[str, object]:
    return {
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }


def _signed(module, core: dict[str, object], key: str) -> dict[str, object]:
    return {**core, key: module._sha(core)}


def _inputs(module):
    preflight = _signed(
        module,
        {
            "schema": module.PREFLIGHT_SCHEMA,
            "status": "READY_TO_IMPLEMENT_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER",
            **_authority(),
        },
        "integration_preflight_sha256",
    )
    composition = _signed(
        module,
        {"schema": module.COMPOSITION_SCHEMA, **_authority()},
        "composition_sha256",
    )
    composition_review = _signed(
        module,
        {
            "schema": module.COMPOSITION_REVIEW_SCHEMA,
            "source_composition_sha256": composition["composition_sha256"],
            "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION",
            "runtime_construction_admitted": True,
            "backend_execution_admitted": False,
            **_authority(),
        },
        "composition_review_sha256",
    )
    module.EXPECTED_PREFLIGHT_SHA256 = preflight["integration_preflight_sha256"]
    module.EXPECTED_COMPOSITION_SHA256 = composition["composition_sha256"]
    module.EXPECTED_COMPOSITION_REVIEW_SHA256 = composition_review[
        "composition_review_sha256"
    ]
    module.EXPECTED_PREFLIGHT_FILE_SHA256 = "1" * 64
    module.EXPECTED_COMPOSITION_FILE_SHA256 = "2" * 64
    module.EXPECTED_COMPOSITION_REVIEW_FILE_SHA256 = "3" * 64
    source_paths = {
        "preflight": INTEGRATION
        / "nominal_route_native_binding_integration_preflight.py",
        "composition": INTEGRATION / "nominal_route_complete_runtime_composition.py",
        "composition_review": INTEGRATION
        / "nominal_route_complete_runtime_composition_review.py",
        "clearance_adapter": INTEGRATION / "nominal_route_native_clearance_adapter.py",
        "ik_adapter": INTEGRATION / "nominal_route_canonical_ik_row_adapter.py",
        "metrics_adapter": INTEGRATION / "nominal_route_tool_key_metrics_adapter.py",
        "drift_adapter": INTEGRATION / "nominal_route_root_drift_adapter.py",
        "mechanics": INTEGRATION / "representative_key_mechanics.py",
        "ik": ROOT / "software/src/rocell/kinematics/ik.py",
        "urdf": ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf",
    }
    source_hashes = {
        "arm264_preflight_source": module._file_sha(source_paths["preflight"]),
        "arm270_composition_source": module._file_sha(source_paths["composition"]),
        "arm270_review_source": module._file_sha(source_paths["composition_review"]),
        "native_mechanics_source": module._file_sha(source_paths["mechanics"]),
        "canonical_ik_source": module._file_sha(source_paths["ik"]),
        "pinned_urdf": module._file_sha(source_paths["urdf"]),
    }
    module.EXPECTED_SOURCE_SHA256 = source_hashes
    return preflight, composition, composition_review, source_hashes, source_paths


def _plan(module):
    preflight, composition, review, source_hashes, source_paths = _inputs(module)
    result = module.build_construction_plan(
        preflight,
        composition,
        review,
        preflight_file_sha256="1" * 64,
        composition_file_sha256="2" * 64,
        composition_review_file_sha256="3" * 64,
        source_files_sha256=source_hashes,
        plan_source_file_sha256=module._file_sha(SOURCE),
    )
    return result, (preflight, composition, review, source_paths)


def test_arm271_plan_pins_native_objects_order_and_baselines():
    module = _load("arm271_plan", SOURCE)
    plan, _ = _plan(module)
    objects = plan["supplied_native_objects"]
    assert objects["articulation"]["prim_path"] == "/roarm_m3"
    assert objects["root_view"]["prim_path"] == "/roarm_m3/base_link"
    assert objects["solver"]["shared_identity_between_ik_and_metrics"] is True
    assert plan["baseline_capture"]["sample_count_per_view"] == 1
    assert plan["baseline_capture"]["no_physics_step_between_key_and_root_samples"]
    assert plan["required_construction_order"][-1] == (
        "return_composition_without_calling_any_protocol_method"
    )
    assert plan["constructor_outputs"]["methods_called_during_construction"] == []


def test_arm271_plan_rejects_changed_lineage():
    module = _load("arm271_lineage", SOURCE)
    preflight, composition, review, source_hashes, _ = _inputs(module)
    with pytest.raises(
        module.NativeRuntimeConstructionPlanError,
        match="native construction lineage changed",
    ):
        module.build_construction_plan(
            preflight,
            composition,
            review,
            preflight_file_sha256="9" * 64,
            composition_file_sha256="2" * 64,
            composition_review_file_sha256="3" * 64,
            source_files_sha256=source_hashes,
            plan_source_file_sha256=module._file_sha(SOURCE),
        )


def test_arm271_review_reproduces_and_checks_constructor_surfaces(monkeypatch):
    module = _load("arm271_reviewed_plan_test", SOURCE)
    plan, inputs = _plan(module)
    preflight, composition, composition_review, source_paths = inputs
    reviewer = _load("arm271_reviewer_test", REVIEW_SOURCE)
    reviewer.EXPECTED_PLAN_SHA256 = plan["plan_sha256"]
    reviewer.EXPECTED_PLAN_FILE_SHA256 = "4" * 64
    reviewer.EXPECTED_PLAN_SOURCE_SHA256 = module._file_sha(SOURCE)
    monkeypatch.setattr(reviewer, "_import_plan", lambda _path: module)
    result = reviewer.review_construction_plan(
        plan,
        preflight,
        composition,
        composition_review,
        plan_file_sha256="4" * 64,
        plan_source_path=SOURCE,
        preflight_file_sha256="1" * 64,
        composition_file_sha256="2" * 64,
        composition_review_file_sha256="3" * 64,
        source_paths=source_paths,
    )
    assert result["status"] == (
        "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_IMPLEMENTATION"
    )
    assert result["definition_reproduced"] is True
    assert result["construction_boundary_verified"]["physics_steps"] == 0
    assert result["native_object_construction_admitted"] is False
    assert set(result["constructor_surfaces_verified"]) == set(
        plan["constructor_bindings"]
    )


def test_arm271_sources_are_zero_authority():
    source = SOURCE.read_text(encoding="utf-8")
    review = REVIEW_SOURCE.read_text(encoding="utf-8")
    assert "SimulationApp(" not in source
    assert "execute_backend(" not in source
    assert "set_dof_position_targets" not in source
    for text in (source, review):
        assert not any(
            line.strip() in {"import isaacsim", "import serial"}
            or line.strip().startswith("from isaacsim")
            for line in text.splitlines()
        )
