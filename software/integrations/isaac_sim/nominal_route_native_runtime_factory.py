"""Assemble the reviewed nominal-route runtime from supplied native objects.

ARM-272 is import-safe and starts no simulator. The factory accepts an already
initialized and settled scene, captures one key and root baseline, constructs
the reviewed adapters, and returns the uncalled ARM-270 composition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from nominal_route_canonical_ik_row_adapter import CanonicalIkRowRuntimeAdapter
from nominal_route_complete_runtime_composition import CompleteRuntimeComposition
from nominal_route_native_clearance_adapter import NativeClearanceRuntimeAdapter
from nominal_route_root_drift_adapter import RootDriftRuntimeAdapter
from nominal_route_tool_key_metrics_adapter import ToolKeyMetricsRuntimeAdapter
from rocell.kinematics.ik import RoArmM3NumericalIk


FACTORY_SCHEMA = "tactevra.isaac_lm4_native_runtime_factory.v1"
FACTORY_REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_factory_review.v1"
PLAN_SCHEMA = "tactevra.isaac_lm4_native_runtime_construction_plan.v1"
PLAN_REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_construction_plan_review.v1"

EXPECTED_PLAN_SHA256 = (
    "ab258550a9a598ae3e65bc509cf781d8641ae7cae92ff793383e0f51d7bccea8"
)
EXPECTED_PLAN_REVIEW_SHA256 = (
    "d6141674573401a760e82a6831fa41a0421a4bca4b3a2339acd55566a807bff0"
)
EXPECTED_PLAN_FILE_SHA256 = (
    "a912687cf0b2e1595d4c6de7b038ce5c17d11056a23f3648d1d3ae2ad8f56b25"
)
EXPECTED_PLAN_REVIEW_FILE_SHA256 = (
    "f5b7bc5cdaf0e8728ee213415e614ea4fe176c8770a92a4e577607d5eb12ccce"
)
EXPECTED_PLAN_SOURCE_SHA256 = (
    "66dbf4fe0dcb68c2581b29fe30579a80dca926a6f1808c5bd498561eae4988cb"
)
EXPECTED_PLAN_REVIEW_SOURCE_SHA256 = (
    "c77e5cf149ccd277aebee82bad1aa8c6f0bfe462d6fb6d5ffd949f61ce3020d8"
)


class NativeRuntimeFactoryError(ValueError):
    """Raised when factory lineage, supplied objects, or baselines change."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise NativeRuntimeFactoryError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeFactoryError(f"{label} hash changed")
    return claimed


def build_factory_definition(
    plan: Mapping[str, Any],
    plan_review: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_review_file_sha256: str,
    plan_source_sha256: str,
    plan_review_source_sha256: str,
    factory_source_sha256: str,
) -> dict[str, Any]:
    """Build the reviewable factory definition without constructing anything."""
    plan_hash = _require_hash(plan, "plan_sha256", "ARM-271 plan")
    review_hash = _require_hash(plan_review, "plan_review_sha256", "ARM-271 review")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan_hash != EXPECTED_PLAN_SHA256
        or plan.get("factory_implemented") is not False
        or plan_review.get("schema") != PLAN_REVIEW_SCHEMA
        or review_hash != EXPECTED_PLAN_REVIEW_SHA256
        or plan_review.get("source_plan_sha256") != plan_hash
        or plan_review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_IMPLEMENTATION"
        or plan_review.get("factory_implementation_admitted") is not True
        or plan_review.get("native_object_construction_admitted") is not False
        or plan_file_sha256 != EXPECTED_PLAN_FILE_SHA256
        or plan_review_file_sha256 != EXPECTED_PLAN_REVIEW_FILE_SHA256
        or plan_source_sha256 != EXPECTED_PLAN_SOURCE_SHA256
        or plan_review_source_sha256 != EXPECTED_PLAN_REVIEW_SOURCE_SHA256
        or not isinstance(factory_source_sha256, str)
        or len(factory_source_sha256) != 64
    ):
        raise NativeRuntimeFactoryError("native runtime factory lineage changed")
    core = {
        "schema": FACTORY_SCHEMA,
        "factory_id": "arm272-zero-authority-native-runtime-factory-001",
        "status": "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_FACTORY_REVIEW",
        "source_plan_sha256": plan_hash,
        "source_plan_review_sha256": review_hash,
        "source_files_sha256": {
            "arm271_plan": plan_file_sha256,
            "arm271_plan_review": plan_review_file_sha256,
            "arm271_plan_source": plan_source_sha256,
            "arm271_plan_review_source": plan_review_source_sha256,
            "arm272_factory_source": factory_source_sha256,
        },
        "baseline_reads": {"key_view": 1, "root_view": 1},
        "shared_solver_identity": True,
        "returned_type": "CompleteRuntimeComposition",
        "protocol_methods_called_during_construction": [],
        "factory_implemented": True,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_NATIVE_RUNTIME_FACTORY",
    }
    return {**core, "factory_sha256": _sha(core)}


def _tolist(value: Any, label: str) -> list[Any]:
    try:
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            value = value.tolist()
    except Exception as exc:  # pragma: no cover - native tensor boundary
        raise NativeRuntimeFactoryError(f"{label} cannot be converted") from exc
    if not isinstance(value, list):
        raise NativeRuntimeFactoryError(f"{label} shape changed")
    return value


def _finite_vector(value: Any, size: int, label: str) -> list[float]:
    values = _tolist(value, label)
    if (
        len(values) != 1
        or not isinstance(values[0], (list, tuple))
        or len(values[0]) != size
    ):
        raise NativeRuntimeFactoryError(f"{label} shape changed")
    result = [float(item) for item in values[0]]
    if not all(math.isfinite(item) for item in result):
        raise NativeRuntimeFactoryError(f"{label} must be finite")
    return result


def construct_runtime(
    definition: Mapping[str, Any],
    *,
    factory_review: Mapping[str, Any],
    plan: Mapping[str, Any],
    plan_review: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    articulation: Any,
    scene_query: Any,
    key_view: Any,
    root_view: Any,
    solver_kwargs: Mapping[str, Any],
    native_metadata: Mapping[str, Any],
) -> CompleteRuntimeComposition:
    """Construct adapters from supplied objects without invoking runtime methods."""
    factory_hash = _require_hash(definition, "factory_sha256", "ARM-272 factory")
    _require_hash(factory_review, "factory_review_sha256", "ARM-272 review")
    plan_hash = _require_hash(plan, "plan_sha256", "ARM-271 plan")
    plan_review_hash = _require_hash(
        plan_review, "plan_review_sha256", "ARM-271 review"
    )
    required_documents = {
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
    }
    if (
        definition.get("schema") != FACTORY_SCHEMA
        or definition.get("status")
        != "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_FACTORY_REVIEW"
        or factory_review.get("schema") != FACTORY_REVIEW_SCHEMA
        or factory_review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_USE"
        or factory_review.get("source_factory_sha256") != factory_hash
        or factory_review.get("runtime_construction_admitted") is not True
        or factory_review.get("backend_execution_admitted") is not False
        or plan_hash != EXPECTED_PLAN_SHA256
        or plan_review_hash != EXPECTED_PLAN_REVIEW_SHA256
        or set(documents) != required_documents
        or key_view is root_view
        or not callable(getattr(articulation, "get_link_transforms", None))
        or not callable(getattr(scene_query, "overlap_sphere_any", None))
        or not callable(getattr(scene_query, "sweep_sphere_any", None))
        or not callable(getattr(key_view, "get_world_poses", None))
        or not callable(getattr(root_view, "get_world_poses", None))
        or dict(native_metadata)
        != {
            "articulation_prim_path": "/roarm_m3",
            "root_prim_path": "/roarm_m3/base_link",
            "key_prim_count": 1,
            "root_prim_count": 1,
            "environment_only_scene": True,
            "robot_collision_query_shapes_enabled": False,
            "scene_already_settled": True,
        }
    ):
        raise NativeRuntimeFactoryError("native runtime factory boundary changed")

    key_poses = key_view.get_world_poses()
    root_poses = root_view.get_world_poses()
    if (
        not isinstance(key_poses, (list, tuple))
        or not isinstance(root_poses, (list, tuple))
        or len(root_poses) < 2
    ):
        raise NativeRuntimeFactoryError("native baseline pose result changed")
    key_position = _finite_vector(key_poses[0], 3, "key baseline position")
    root_position = _finite_vector(root_poses[0], 3, "root baseline position")
    root_quaternion = _finite_vector(root_poses[1], 4, "root baseline quaternion")

    clearance = NativeClearanceRuntimeAdapter(
        documents["clearance_definition"],
        adapter_review=documents["clearance_review"],
        binding_definition=documents["binding_definition"],
        binding_review=documents["binding_review"],
        articulation=articulation,
        scene_query=scene_query,
        environment_only_scene=True,
        robot_collision_query_shapes_enabled=False,
    )
    solver = RoArmM3NumericalIk(**dict(solver_kwargs))
    ik = CanonicalIkRowRuntimeAdapter(
        documents["ik_definition"], adapter_review=documents["ik_review"], solver=solver
    )
    metrics = ToolKeyMetricsRuntimeAdapter(
        documents["metrics_definition"],
        adapter_review=documents["metrics_review"],
        solver=solver,
        key_view=key_view,
        settled_key_center_z_stage=key_position[2],
    )
    drift = RootDriftRuntimeAdapter(
        documents["drift_definition"],
        adapter_review=documents["drift_review"],
        root_view=root_view,
        expected_position_stage=root_position,
        expected_quaternion_wxyz=root_quaternion,
    )
    return CompleteRuntimeComposition(
        documents["composition_definition"],
        composition_review=documents["composition_review"],
        clearance=clearance,
        ik=ik,
        metrics=metrics,
        drift=drift,
    )


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeFactoryError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-review", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--plan-review-source", type=Path, required=True)
    parser.add_argument("--factory-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_factory_definition(
        _load(args.plan),
        _load(args.plan_review),
        plan_file_sha256=_file_sha(args.plan),
        plan_review_file_sha256=_file_sha(args.plan_review),
        plan_source_sha256=_file_sha(args.plan_source),
        plan_review_source_sha256=_file_sha(args.plan_review_source),
        factory_source_sha256=_file_sha(args.factory_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
