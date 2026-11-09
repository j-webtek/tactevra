"""Plan zero-authority native object construction for the ARM-270 runtime.

ARM-271 specifies the supplied objects, identity constraints, baseline capture,
and constructor order required to instantiate the reviewed four-method runtime.
It constructs nothing, imports no Isaac module, and calls no backend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PLAN_SCHEMA = "tactevra.isaac_lm4_native_runtime_construction_plan.v1"
PLAN_REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_construction_plan_review.v1"
PREFLIGHT_SCHEMA = "tactevra.isaac_lm4_native_binding_integration_preflight.v1"
COMPOSITION_SCHEMA = "tactevra.isaac_lm4_complete_runtime_composition.v1"
COMPOSITION_REVIEW_SCHEMA = "tactevra.isaac_lm4_complete_runtime_composition_review.v1"

EXPECTED_PREFLIGHT_SHA256 = (
    "e87de97b9c6ab066113f8eff8ad55712d134e073da035f4d447f3ee941914e69"
)
EXPECTED_COMPOSITION_SHA256 = (
    "05b0bc6e8c63022fcecde6fab02302de0abd63432084a6e84fe8e6c916ed2d19"
)
EXPECTED_COMPOSITION_REVIEW_SHA256 = (
    "75909dfe78ddc0c5ce8ec0c8bb84660e9cd38086d077b570277733a243f0fca1"
)
EXPECTED_PREFLIGHT_FILE_SHA256 = (
    "af8c7e59d8edb1f2c137b4f032f37ae0d1df03282dd43fa02474ac8164d0ff4a"
)
EXPECTED_COMPOSITION_FILE_SHA256 = (
    "7d091f477dc1986b505693cbf8faed0d27cebd605860520f29e3535f6b15aa32"
)
EXPECTED_COMPOSITION_REVIEW_FILE_SHA256 = (
    "5657126f17c4415caed380e5aaf5194f985f8a93c1423764a3cfd471acb95645"
)
EXPECTED_SOURCE_SHA256 = {
    "arm264_preflight_source": "2640e2003cf4dceaa3120206436d3ec376c43123a010468d3f7ec42781ca8d2f",
    "arm270_composition_source": "a1d8813ae9bdb032eed21e399cab263effbcc32b8786d64836170cb562e95b4b",
    "arm270_review_source": "2500c57e6fea3c00c31394722536217934d6493df43ae34528aa03ea512eca29",
    "native_mechanics_source": "ba12db530d8ffb0a9b22068238a604a935f6adaff8ba6f3fa7364581ec18d9a3",
    "canonical_ik_source": "4feb5adb8c33d7b3017f29c17130dc934269ae159bed88b06d8aa63d8474569a",
    "pinned_urdf": "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190",
}


class NativeRuntimeConstructionPlanError(ValueError):
    """Raised when construction lineage or ordering changes."""


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
        raise NativeRuntimeConstructionPlanError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeConstructionPlanError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("launch_admitted") is False
        and document.get("attempt_consumed") is False
        and document.get("hardware_access") is False
        and document.get("physical_authority") is False
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def build_construction_plan(
    preflight: Mapping[str, Any],
    composition: Mapping[str, Any],
    composition_review: Mapping[str, Any],
    *,
    preflight_file_sha256: str,
    composition_file_sha256: str,
    composition_review_file_sha256: str,
    source_files_sha256: Mapping[str, str],
    plan_source_file_sha256: str,
) -> dict[str, Any]:
    """Build a deterministic construction plan without constructing objects."""

    preflight_hash = _require_hash(
        preflight, "integration_preflight_sha256", "ARM-264 preflight"
    )
    composition_hash = _require_hash(
        composition, "composition_sha256", "ARM-270 composition"
    )
    review_hash = _require_hash(
        composition_review, "composition_review_sha256", "ARM-270 review"
    )
    if (
        preflight.get("schema") != PREFLIGHT_SCHEMA
        or preflight_hash != EXPECTED_PREFLIGHT_SHA256
        or preflight.get("status")
        != "READY_TO_IMPLEMENT_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER"
        or composition.get("schema") != COMPOSITION_SCHEMA
        or composition_hash != EXPECTED_COMPOSITION_SHA256
        or composition_review.get("schema") != COMPOSITION_REVIEW_SCHEMA
        or review_hash != EXPECTED_COMPOSITION_REVIEW_SHA256
        or composition_review.get("source_composition_sha256") != composition_hash
        or composition_review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION"
        or composition_review.get("runtime_construction_admitted") is not True
        or composition_review.get("backend_execution_admitted") is not False
        or preflight_file_sha256 != EXPECTED_PREFLIGHT_FILE_SHA256
        or composition_file_sha256 != EXPECTED_COMPOSITION_FILE_SHA256
        or composition_review_file_sha256 != EXPECTED_COMPOSITION_REVIEW_FILE_SHA256
        or dict(source_files_sha256) != EXPECTED_SOURCE_SHA256
        or not isinstance(plan_source_file_sha256, str)
        or len(plan_source_file_sha256) != 64
        or not _zero_authority(preflight)
        or not _zero_authority(composition)
        or not _zero_authority(composition_review)
    ):
        raise NativeRuntimeConstructionPlanError("native construction lineage changed")

    core: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "plan_id": "arm271-zero-authority-native-runtime-construction-plan-001",
        "status": "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_CONSTRUCTION_PLAN_REVIEW",
        "source_preflight_sha256": preflight_hash,
        "source_composition_sha256": composition_hash,
        "source_composition_review_sha256": review_hash,
        "source_files_sha256": {
            "arm264_preflight": preflight_file_sha256,
            "arm270_composition": composition_file_sha256,
            "arm270_composition_review": composition_review_file_sha256,
            **dict(source_files_sha256),
            "arm271_plan_source": plan_source_file_sha256,
        },
        "supplied_native_objects": {
            "articulation": {
                "type": "isaacsim.core.experimental.prims.Articulation",
                "prim_path": "/roarm_m3",
                "initialized": True,
                "required_methods": ["get_link_transforms"],
            },
            "scene_query": {
                "type": "omni.physx.SceneQueryInterface",
                "environment_only": True,
                "robot_collision_query_shapes_enabled": False,
                "required_methods": ["overlap_sphere_any", "sweep_sphere_any"],
            },
            "key_view": {
                "type": "isaacsim.core.experimental.prims.RigidPrim",
                "prim_count": 1,
                "required_methods": ["get_world_poses"],
                "quaternion_order": "WXYZ",
            },
            "root_view": {
                "type": "isaacsim.core.experimental.prims.RigidPrim",
                "prim_path": "/roarm_m3/base_link",
                "prim_count": 1,
                "required_methods": ["get_world_poses"],
                "quaternion_order": "WXYZ",
            },
            "solver": {
                "type": "rocell.kinematics.ik.RoArmM3NumericalIk",
                "shared_identity_between_ik_and_metrics": True,
                "source_sha256": EXPECTED_SOURCE_SHA256["canonical_ik_source"],
            },
        },
        "scene_preconditions": {
            "scene_already_loaded": True,
            "physics_already_initialized": True,
            "scene_already_settled": True,
            "construction_plan_may_step_physics": False,
            "construction_plan_may_write_articulation": False,
            "target_key_prim_path_supplied_by_worker": True,
            "root_and_key_views_must_be_distinct": True,
        },
        "baseline_capture": {
            "sample_count_per_view": 1,
            "timing": "AFTER_SCENE_SETTLE_BEFORE_ANY_GOVERNED_ROUTE_OPERATION",
            "key_value": "SETTLED_KEY_CENTER_Z_STAGE",
            "root_values": [
                "EXPECTED_ROOT_POSITION_STAGE",
                "EXPECTED_ROOT_QUATERNION_WXYZ",
            ],
            "finite_shape_validation_required": True,
            "no_physics_step_between_key_and_root_samples": True,
        },
        "required_construction_order": [
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
        ],
        "constructor_bindings": {
            "NativeClearanceRuntimeAdapter": [
                "definition",
                "adapter_review",
                "binding_definition",
                "binding_review",
                "articulation",
                "scene_query",
                "environment_only_scene",
                "robot_collision_query_shapes_enabled",
            ],
            "CanonicalIkRowRuntimeAdapter": [
                "definition",
                "adapter_review",
                "solver",
            ],
            "ToolKeyMetricsRuntimeAdapter": [
                "definition",
                "adapter_review",
                "solver",
                "key_view",
                "settled_key_center_z_stage",
            ],
            "RootDriftRuntimeAdapter": [
                "definition",
                "adapter_review",
                "root_view",
                "expected_position_stage",
                "expected_quaternion_wxyz",
            ],
            "CompleteRuntimeComposition": [
                "definition",
                "composition_review",
                "clearance",
                "ik",
                "metrics",
                "drift",
            ],
        },
        "constructor_outputs": {
            "type": "CompleteRuntimeComposition",
            "methods_present": [
                "regenerate_row",
                "check_continuous_clearance",
                "measure_tool_key",
                "root_drift",
            ],
            "methods_called_during_construction": [],
        },
        "factory_implemented": False,
        "native_objects_constructed": False,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_NATIVE_RUNTIME_CONSTRUCTION_PLAN",
        "limitations": [
            "plan_does_not_import_isaac_construct_objects_or_load_a_scene",
            "worker_must_supply_an_already_initialized_and_settled_scene",
            "target_key_prim_path_remains_worker_supplied_and_must_be_separately_pinned",
            "factory_implementation_and_native_execution_require_separate_reviews",
        ],
    }
    return {**core, "plan_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeConstructionPlanError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--composition-review", type=Path, required=True)
    parser.add_argument("--preflight-source", type=Path, required=True)
    parser.add_argument("--composition-source", type=Path, required=True)
    parser.add_argument("--composition-review-source", type=Path, required=True)
    parser.add_argument("--mechanics-source", type=Path, required=True)
    parser.add_argument("--ik-source", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = {
        "arm264_preflight_source": _file_sha(args.preflight_source),
        "arm270_composition_source": _file_sha(args.composition_source),
        "arm270_review_source": _file_sha(args.composition_review_source),
        "native_mechanics_source": _file_sha(args.mechanics_source),
        "canonical_ik_source": _file_sha(args.ik_source),
        "pinned_urdf": _file_sha(args.urdf),
    }
    result = build_construction_plan(
        _load(args.preflight),
        _load(args.composition),
        _load(args.composition_review),
        preflight_file_sha256=_file_sha(args.preflight),
        composition_file_sha256=_file_sha(args.composition),
        composition_review_file_sha256=_file_sha(args.composition_review),
        source_files_sha256=sources,
        plan_source_file_sha256=_file_sha(args.plan_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
