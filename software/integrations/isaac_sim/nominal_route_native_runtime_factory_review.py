"""Independently review the ARM-272 zero-authority native runtime factory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_factory_review.v1"
EXPECTED_FACTORY_SHA256 = (
    "1ff2ffdd97b5ec8514a86fdb21e1cac3aae8a445d388a8b10a9fd6775e6fe818"
)
EXPECTED_FACTORY_FILE_SHA256 = (
    "6572a0a9166106c0321349ef4b8276154f06ab775ec478a941869e6b5c7ce854"
)
EXPECTED_FACTORY_SOURCE_SHA256 = (
    "d23a94ee333456c3a0a9ca314b40d5c1568469847f0b9e882709e1fb45d72c44"
)


class NativeRuntimeFactoryReviewError(ValueError):
    """Raised when factory evidence or behavior changes."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeFactoryReviewError(f"{label} hash changed")
    return claimed


def _import_factory(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("arm272_reviewed_factory", path)
    if spec is None or spec.loader is None:
        raise NativeRuntimeFactoryReviewError("factory source cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _static_review(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "import isaacsim",
        "from isaacsim",
        "SimulationApp(",
        "import serial",
        "execute_backend(",
        "set_dof_positions",
        "set_dof_position_targets",
        "step(",
    )
    if any(token in text for token in forbidden):
        raise NativeRuntimeFactoryReviewError(
            "factory source contains runtime authority"
        )
    tree = ast.parse(text)
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "construct_runtime"
        ),
        None,
    )
    if function is None:
        raise NativeRuntimeFactoryReviewError("construct_runtime is absent")
    calls = [
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    required = [
        "NativeClearanceRuntimeAdapter",
        "RoArmM3NumericalIk",
        "CanonicalIkRowRuntimeAdapter",
        "ToolKeyMetricsRuntimeAdapter",
        "RootDriftRuntimeAdapter",
        "CompleteRuntimeComposition",
    ]
    positions = [calls.index(name) for name in required if name in calls]
    if len(positions) != len(required) or positions != sorted(positions):
        raise NativeRuntimeFactoryReviewError("factory construction order changed")
    return {
        "forbidden_runtime_imports_absent": True,
        "backend_and_joint_submission_calls_absent": True,
        "construction_call_order": required,
    }


class _View:
    def __init__(self, result: tuple[Any, ...]):
        self.result = result
        self.reads = 0

    def get_world_poses(self):
        self.reads += 1
        return self.result


class _Articulation:
    def get_link_transforms(self):
        raise AssertionError("factory must not read articulation transforms")


class _SceneQuery:
    def overlap_sphere_any(self):
        raise AssertionError("factory must not query the scene")

    def sweep_sphere_any(self):
        raise AssertionError("factory must not query the scene")


def _behavior_review(module: Any, definition, plan, plan_review) -> dict[str, Any]:
    events: list[tuple[str, dict[str, Any]]] = []

    def component(name):
        class Component:
            def __init__(self, *args, **kwargs):
                events.append((name, {"args": args, **kwargs}))

        Component.__name__ = name
        return Component

    class Solver:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            events.append(("RoArmM3NumericalIk", kwargs))

    class Composition:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            events.append(("CompleteRuntimeComposition", {"args": args, **kwargs}))

    module.NativeClearanceRuntimeAdapter = component("NativeClearanceRuntimeAdapter")
    module.RoArmM3NumericalIk = Solver
    module.CanonicalIkRowRuntimeAdapter = component("CanonicalIkRowRuntimeAdapter")
    module.ToolKeyMetricsRuntimeAdapter = component("ToolKeyMetricsRuntimeAdapter")
    module.RootDriftRuntimeAdapter = component("RootDriftRuntimeAdapter")
    module.CompleteRuntimeComposition = Composition
    review_core = {
        "schema": module.FACTORY_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_USE",
        "source_factory_sha256": definition["factory_sha256"],
        "runtime_construction_admitted": True,
        "backend_execution_admitted": False,
    }
    provisional_review = {
        **review_core,
        "factory_review_sha256": module._sha(review_core),
    }
    documents = {
        name: {"document": name}
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
    key = _View(([[0.1, 0.2, 0.3]], [[1.0, 0.0, 0.0, 0.0]]))
    root = _View(([[0.4, 0.5, 0.6]], [[1.0, 0.0, 0.0, 0.0]]))
    result = module.construct_runtime(
        definition,
        factory_review=provisional_review,
        plan=plan,
        plan_review=plan_review,
        documents=documents,
        articulation=_Articulation(),
        scene_query=_SceneQuery(),
        key_view=key,
        root_view=root,
        solver_kwargs={"marker": "shared"},
        native_metadata={
            "articulation_prim_path": "/roarm_m3",
            "root_prim_path": "/roarm_m3/base_link",
            "key_prim_count": 1,
            "root_prim_count": 1,
            "environment_only_scene": True,
            "robot_collision_query_shapes_enabled": False,
            "scene_already_settled": True,
        },
    )
    names = [name for name, _ in events]
    expected = [
        "NativeClearanceRuntimeAdapter",
        "RoArmM3NumericalIk",
        "CanonicalIkRowRuntimeAdapter",
        "ToolKeyMetricsRuntimeAdapter",
        "RootDriftRuntimeAdapter",
        "CompleteRuntimeComposition",
    ]
    ik_solver = events[2][1]["solver"]
    metrics_solver = events[3][1]["solver"]
    if (
        names != expected
        or key.reads != 1
        or root.reads != 1
        or ik_solver is not metrics_solver
        or not isinstance(result, Composition)
        or events[3][1]["settled_key_center_z_stage"] != 0.3
        or events[4][1]["expected_position_stage"] != [0.4, 0.5, 0.6]
        or events[4][1]["expected_quaternion_wxyz"] != [1.0, 0.0, 0.0, 0.0]
    ):
        raise NativeRuntimeFactoryReviewError("factory behavior changed")
    return {
        "construction_order_verified": True,
        "baseline_reads": {"key_view": 1, "root_view": 1},
        "shared_solver_identity_verified": True,
        "protocol_methods_called": [],
    }


def review_factory(
    definition: Mapping[str, Any],
    plan: Mapping[str, Any],
    plan_review: Mapping[str, Any],
    *,
    factory_file_sha256: str,
    factory_source_path: Path,
) -> dict[str, Any]:
    factory_hash = _require_hash(definition, "factory_sha256", "ARM-272 factory")
    source_hash = _file_sha(factory_source_path)
    if (
        factory_hash != EXPECTED_FACTORY_SHA256
        or factory_file_sha256 != EXPECTED_FACTORY_FILE_SHA256
        or source_hash != EXPECTED_FACTORY_SOURCE_SHA256
    ):
        raise NativeRuntimeFactoryReviewError("factory review boundary changed")
    module = _import_factory(factory_source_path)
    reproduced = module.build_factory_definition(
        plan,
        plan_review,
        plan_file_sha256=module.EXPECTED_PLAN_FILE_SHA256,
        plan_review_file_sha256=module.EXPECTED_PLAN_REVIEW_FILE_SHA256,
        plan_source_sha256=module.EXPECTED_PLAN_SOURCE_SHA256,
        plan_review_source_sha256=module.EXPECTED_PLAN_REVIEW_SOURCE_SHA256,
        factory_source_sha256=source_hash,
    )
    if reproduced != definition:
        raise NativeRuntimeFactoryReviewError("factory definition did not reproduce")
    static = _static_review(factory_source_path)
    behavior = _behavior_review(module, definition, plan, plan_review)
    core = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm272-native-runtime-factory-review-001",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_USE",
        "source_factory_sha256": factory_hash,
        "source_factory_file_sha256": factory_file_sha256,
        "source_factory_source_sha256": source_hash,
        "definition_reproduced": True,
        "static_review": static,
        "behavior_review": behavior,
        "runtime_construction_admitted": True,
        "native_object_construction_admitted": False,
        "backend_execution_admitted": False,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "scene_loaded": False,
        "physics_steps": 0,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "PLAN_SEPARATELY_ADMITTED_NATIVE_RUNTIME_WORKER_INTEGRATION",
    }
    return {**core, "factory_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeFactoryReviewError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", type=Path, required=True)
    parser.add_argument("--factory-source", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_factory(
        _load(args.factory),
        _load(args.plan),
        _load(args.plan_review),
        factory_file_sha256=_file_sha(args.factory),
        factory_source_path=args.factory_source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
