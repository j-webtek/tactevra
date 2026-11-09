from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_native_runtime_factory.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_native_runtime_factory_review.py"
for import_root in (INTEGRATION, ROOT / "software/src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _lineage(module):
    plan = _signed(
        module,
        {"schema": module.PLAN_SCHEMA, "factory_implemented": False},
        "plan_sha256",
    )
    review = _signed(
        module,
        {
            "schema": module.PLAN_REVIEW_SCHEMA,
            "source_plan_sha256": plan["plan_sha256"],
            "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_IMPLEMENTATION",
            "factory_implementation_admitted": True,
            "native_object_construction_admitted": False,
        },
        "plan_review_sha256",
    )
    module.EXPECTED_PLAN_SHA256 = plan["plan_sha256"]
    module.EXPECTED_PLAN_REVIEW_SHA256 = review["plan_review_sha256"]
    module.EXPECTED_PLAN_FILE_SHA256 = "1" * 64
    module.EXPECTED_PLAN_REVIEW_FILE_SHA256 = "2" * 64
    module.EXPECTED_PLAN_SOURCE_SHA256 = "3" * 64
    module.EXPECTED_PLAN_REVIEW_SOURCE_SHA256 = "4" * 64
    definition = module.build_factory_definition(
        plan,
        review,
        plan_file_sha256="1" * 64,
        plan_review_file_sha256="2" * 64,
        plan_source_sha256="3" * 64,
        plan_review_source_sha256="4" * 64,
        factory_source_sha256=module._file_sha(SOURCE),
    )
    return plan, review, definition


class _View:
    def __init__(self, poses):
        self.poses = poses
        self.reads = 0

    def get_world_poses(self):
        self.reads += 1
        return self.poses


class _Articulation:
    def get_link_transforms(self):
        return None


class _Scene:
    def overlap_sphere_any(self):
        return None

    def sweep_sphere_any(self):
        return None


def _metadata():
    return {
        "articulation_prim_path": "/roarm_m3",
        "root_prim_path": "/roarm_m3/base_link",
        "key_prim_count": 1,
        "root_prim_count": 1,
        "environment_only_scene": True,
        "robot_collision_query_shapes_enabled": False,
        "scene_already_settled": True,
    }


def test_arm272_factory_captures_once_and_shares_solver(monkeypatch):
    module = _load("arm272_factory_test", SOURCE)
    plan, plan_review, definition = _lineage(module)
    events = []

    def component(name):
        class Component:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs
                events.append((name, self))

        return Component

    class Solver:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Composition:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(module, "NativeClearanceRuntimeAdapter", component("clearance"))
    monkeypatch.setattr(module, "RoArmM3NumericalIk", Solver)
    monkeypatch.setattr(module, "CanonicalIkRowRuntimeAdapter", component("ik"))
    monkeypatch.setattr(module, "ToolKeyMetricsRuntimeAdapter", component("metrics"))
    monkeypatch.setattr(module, "RootDriftRuntimeAdapter", component("drift"))
    monkeypatch.setattr(module, "CompleteRuntimeComposition", Composition)
    review_core = {
        "schema": module.FACTORY_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_USE",
        "source_factory_sha256": definition["factory_sha256"],
        "runtime_construction_admitted": True,
        "backend_execution_admitted": False,
    }
    factory_review = _signed(module, review_core, "factory_review_sha256")
    docs = {
        name: {}
        for name in (
            "clearance_definition",
            "clearance_review",
            "binding_definition",
            "binding_review",
            "ik_definition",
            "ik_review",
            "metrics_definition",
            "metrics_review",
            "drift_definition",
            "drift_review",
            "composition_definition",
            "composition_review",
        )
    }
    key = _View(([[1.0, 2.0, 3.0]], [[1.0, 0.0, 0.0, 0.0]]))
    root = _View(([[4.0, 5.0, 6.0]], [[1.0, 0.0, 0.0, 0.0]]))
    result = module.construct_runtime(
        definition,
        factory_review=factory_review,
        plan=plan,
        plan_review=plan_review,
        documents=docs,
        articulation=_Articulation(),
        scene_query=_Scene(),
        key_view=key,
        root_view=root,
        solver_kwargs={"test": True},
        native_metadata=_metadata(),
    )
    assert isinstance(result, Composition)
    assert key.reads == root.reads == 1
    assert [name for name, _ in events] == ["clearance", "ik", "metrics", "drift"]
    assert events[1][1].kwargs["solver"] is events[2][1].kwargs["solver"]
    assert events[2][1].kwargs["settled_key_center_z_stage"] == 3.0
    assert events[3][1].kwargs["expected_position_stage"] == [4.0, 5.0, 6.0]


def test_arm272_factory_rejects_unsettled_metadata():
    module = _load("arm272_boundary_test", SOURCE)
    plan, plan_review, definition = _lineage(module)
    review_core = {
        "schema": module.FACTORY_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_USE",
        "source_factory_sha256": definition["factory_sha256"],
        "runtime_construction_admitted": True,
        "backend_execution_admitted": False,
    }
    metadata = _metadata()
    metadata["scene_already_settled"] = False
    with pytest.raises(module.NativeRuntimeFactoryError, match="boundary changed"):
        module.construct_runtime(
            definition,
            factory_review=_signed(module, review_core, "factory_review_sha256"),
            plan=plan,
            plan_review=plan_review,
            documents={},
            articulation=_Articulation(),
            scene_query=_Scene(),
            key_view=_View(([[0, 0, 0]],)),
            root_view=_View(([[0, 0, 0]], [[1, 0, 0, 0]])),
            solver_kwargs={},
            native_metadata=metadata,
        )


def test_arm272_static_review_rejects_runtime_authority():
    reviewer = _load("arm272_static_reviewer", REVIEW_SOURCE)
    result = reviewer._static_review(SOURCE)
    assert result["forbidden_runtime_imports_absent"] is True
    assert result["backend_and_joint_submission_calls_absent"] is True
