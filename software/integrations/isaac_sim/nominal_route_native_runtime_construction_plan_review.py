"""Independently review the ARM-271 native runtime construction plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_construction_plan_review.v1"
EXPECTED_PLAN_SHA256 = (
    "ab258550a9a598ae3e65bc509cf781d8641ae7cae92ff793383e0f51d7bccea8"
)
EXPECTED_PLAN_FILE_SHA256 = (
    "a912687cf0b2e1595d4c6de7b038ce5c17d11056a23f3648d1d3ae2ad8f56b25"
)
EXPECTED_PLAN_SOURCE_SHA256 = (
    "66dbf4fe0dcb68c2581b29fe30579a80dca926a6f1808c5bd498561eae4988cb"
)


class NativeRuntimeConstructionPlanReviewError(ValueError):
    """Raised when plan evidence or constructor surfaces change."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeRuntimeConstructionPlanReviewError(
            "input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeConstructionPlanReviewError(f"{label} hash changed")
    return claimed


def _import_plan(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("arm271_reviewed_plan", path)
    if spec is None or spec.loader is None:
        raise NativeRuntimeConstructionPlanReviewError("plan source cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _constructor_parameters(path: Path, class_name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for method in node.body:
                if isinstance(method, ast.FunctionDef) and method.name == "__init__":
                    return [
                        argument.arg
                        for argument in (
                            *method.args.posonlyargs,
                            *method.args.args,
                            *method.args.kwonlyargs,
                        )
                        if argument.arg != "self"
                    ]
    raise NativeRuntimeConstructionPlanReviewError(
        f"{class_name} constructor is absent"
    )


def _review_plan_source(path: Path) -> dict[str, bool]:
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "import isaacsim",
        "from isaacsim",
        "SimulationApp(",
        "import serial",
        "execute_backend(",
        "set_dof_positions",
        "set_dof_position_targets",
    )
    if any(token in text for token in forbidden):
        raise NativeRuntimeConstructionPlanReviewError(
            "plan source contains runtime authority"
        )
    return {
        "forbidden_runtime_imports_absent": True,
        "backend_execution_call_absent": True,
        "joint_submission_calls_absent": True,
        "native_construction_calls_absent": True,
    }


def _review_constructor_surfaces(
    plan: Mapping[str, Any], source_paths: Mapping[str, Path]
) -> dict[str, list[str]]:
    expected = {
        "NativeClearanceRuntimeAdapter": (
            "clearance",
            source_paths["clearance_adapter"],
        ),
        "CanonicalIkRowRuntimeAdapter": ("ik", source_paths["ik_adapter"]),
        "ToolKeyMetricsRuntimeAdapter": ("metrics", source_paths["metrics_adapter"]),
        "RootDriftRuntimeAdapter": ("drift", source_paths["drift_adapter"]),
        "CompleteRuntimeComposition": ("composition", source_paths["composition"]),
    }
    bindings = plan.get("constructor_bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != set(expected):
        raise NativeRuntimeConstructionPlanReviewError(
            "constructor binding set changed"
        )
    observed: dict[str, list[str]] = {}
    for class_name, (_label, path) in expected.items():
        parameters = _constructor_parameters(path, class_name)
        if bindings[class_name] != parameters:
            raise NativeRuntimeConstructionPlanReviewError(
                f"{class_name} parameters changed"
            )
        observed[class_name] = parameters
    return observed


def _review_order_and_baselines(plan: Mapping[str, Any]) -> dict[str, Any]:
    order = plan.get("required_construction_order")
    baseline = plan.get("baseline_capture")
    objects = plan.get("supplied_native_objects")
    preconditions = plan.get("scene_preconditions")
    required_order = [
        "revalidate_arm264_arm270_and_all_source_hashes",
        "validate_supplied_object_types_methods_prim_counts_and_paths",
        "assert_environment_only_scene_and_robot_query_shapes_disabled",
        "capture_key_and_root_baselines_without_step_or_write",
        "construct_arm265_clearance_adapter",
        "construct_one_shared_canonical_solver_for_arm267_and_arm268",
        "construct_arm267_ik_adapter",
        "construct_arm268_metrics_adapter_with_same_solver_identity",
        "construct_arm269_root_drift_adapter",
        "construct_arm270_complete_runtime_composition",
        "return_composition_without_calling_any_protocol_method",
    ]
    if (
        order != required_order
        or not isinstance(baseline, Mapping)
        or baseline.get("sample_count_per_view") != 1
        or baseline.get("no_physics_step_between_key_and_root_samples") is not True
        or not isinstance(objects, Mapping)
        or objects.get("root_view", {}).get("prim_path") != "/roarm_m3/base_link"
        or objects.get("solver", {}).get("shared_identity_between_ik_and_metrics")
        is not True
        or not isinstance(preconditions, Mapping)
        or preconditions.get("scene_already_settled") is not True
        or preconditions.get("construction_plan_may_step_physics") is not False
        or preconditions.get("construction_plan_may_write_articulation") is not False
        or plan.get("physics_steps") != 0
        or plan.get("native_objects_constructed") is not False
        or plan.get("backend_execution_admitted") is not False
    ):
        raise NativeRuntimeConstructionPlanReviewError(
            "construction order or baseline boundary changed"
        )
    return {
        "order_step_count": len(required_order),
        "baseline_reads": {"key_view": 1, "root_view": 1},
        "shared_solver_identity_required": True,
        "physics_steps": 0,
        "articulation_writes": 0,
    }


def _review_native_evidence_sources(
    source_paths: Mapping[str, Path],
) -> dict[str, bool]:
    mechanics = source_paths["mechanics"].read_text(encoding="utf-8")
    if (
        "RigidPrim" not in mechanics
        or "get_world_poses" not in mechanics
        or "get_physx_scene_query_interface" not in mechanics
    ):
        raise NativeRuntimeConstructionPlanReviewError(
            "native mechanics evidence changed"
        )
    return {
        "rigid_prim_pose_reads_present": True,
        "scene_query_interface_present": True,
    }


def review_construction_plan(
    plan: Mapping[str, Any],
    preflight: Mapping[str, Any],
    composition: Mapping[str, Any],
    composition_review: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_source_path: Path,
    preflight_file_sha256: str,
    composition_file_sha256: str,
    composition_review_file_sha256: str,
    source_paths: Mapping[str, Path],
) -> dict[str, Any]:
    plan_hash = _require_hash(plan, "plan_sha256", "ARM-271 plan")
    source_sha = _file_sha(plan_source_path)
    if (
        plan_hash != EXPECTED_PLAN_SHA256
        or plan_file_sha256 != EXPECTED_PLAN_FILE_SHA256
        or source_sha != EXPECTED_PLAN_SOURCE_SHA256
    ):
        raise NativeRuntimeConstructionPlanReviewError("plan review boundary changed")
    module = _import_plan(plan_source_path)
    source_hashes = {
        "arm264_preflight_source": _file_sha(source_paths["preflight"]),
        "arm270_composition_source": _file_sha(source_paths["composition"]),
        "arm270_review_source": _file_sha(source_paths["composition_review"]),
        "native_mechanics_source": _file_sha(source_paths["mechanics"]),
        "canonical_ik_source": _file_sha(source_paths["ik"]),
        "pinned_urdf": _file_sha(source_paths["urdf"]),
    }
    reproduced = module.build_construction_plan(
        preflight,
        composition,
        composition_review,
        preflight_file_sha256=preflight_file_sha256,
        composition_file_sha256=composition_file_sha256,
        composition_review_file_sha256=composition_review_file_sha256,
        source_files_sha256=source_hashes,
        plan_source_file_sha256=source_sha,
    )
    if reproduced != plan:
        raise NativeRuntimeConstructionPlanReviewError(
            "construction plan did not reproduce"
        )
    source_review = _review_plan_source(plan_source_path)
    constructors = _review_constructor_surfaces(plan, source_paths)
    boundary = _review_order_and_baselines(plan)
    native_evidence = _review_native_evidence_sources(source_paths)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm271-native-runtime-construction-plan-review-002",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_IMPLEMENTATION",
        "source_plan_sha256": plan_hash,
        "source_plan_file_sha256": plan_file_sha256,
        "source_plan_source_sha256": source_sha,
        "definition_reproduced": True,
        "constructor_surfaces_verified": constructors,
        "construction_boundary_verified": boundary,
        "native_evidence_sources_verified": native_evidence,
        "source_review": source_review,
        "factory_implementation_admitted": True,
        "native_object_construction_admitted": False,
        "backend_execution_admitted": False,
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
        "next_required_stage": "IMPLEMENT_AND_REVIEW_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY",
        "limitations": [
            "review_is_static_and_constructs_no_native_object",
            "factory_must_accept_an_already_initialized_and_settled_scene",
            "target_key_prim_path_requires_separate_worker_pin",
            "backend_execution_and_any_simulation_attempt_remain_unadmitted",
        ],
    }
    return {**core, "plan_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeConstructionPlanReviewError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--composition-review", type=Path, required=True)
    parser.add_argument("--preflight-source", type=Path, required=True)
    parser.add_argument("--composition-source", type=Path, required=True)
    parser.add_argument("--composition-review-source", type=Path, required=True)
    parser.add_argument("--clearance-adapter-source", type=Path, required=True)
    parser.add_argument("--ik-adapter-source", type=Path, required=True)
    parser.add_argument("--metrics-adapter-source", type=Path, required=True)
    parser.add_argument("--drift-adapter-source", type=Path, required=True)
    parser.add_argument("--mechanics-source", type=Path, required=True)
    parser.add_argument("--ik-source", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "preflight": args.preflight_source,
        "composition": args.composition_source,
        "composition_review": args.composition_review_source,
        "clearance_adapter": args.clearance_adapter_source,
        "ik_adapter": args.ik_adapter_source,
        "metrics_adapter": args.metrics_adapter_source,
        "drift_adapter": args.drift_adapter_source,
        "mechanics": args.mechanics_source,
        "ik": args.ik_source,
        "urdf": args.urdf,
    }
    result = review_construction_plan(
        _load(args.plan),
        _load(args.preflight),
        _load(args.composition),
        _load(args.composition_review),
        plan_file_sha256=_file_sha(args.plan),
        plan_source_path=args.plan_source,
        preflight_file_sha256=_file_sha(args.preflight),
        composition_file_sha256=_file_sha(args.composition),
        composition_review_file_sha256=_file_sha(args.composition_review),
        source_paths=paths,
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
