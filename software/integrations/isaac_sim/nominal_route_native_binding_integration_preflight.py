"""Prepare the reviewed native sweep binding for zero-authority integration.

ARM-264 hash-binds the ARM-255 backend protocol, ARM-257 conservative proof
core, ARM-262 native binding, and ARM-263 independent review.  It verifies the
Python call surfaces needed to compose those layers, then emits a deterministic
integration contract.  Importing or running this module never imports Isaac,
constructs a runtime object, loads a scene, or consumes the governed attempt.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PREFLIGHT_SCHEMA = (
    "tactevra.isaac_lm4_native_binding_integration_preflight.v1"
)
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
BINDING_SCHEMA = "tactevra.isaac_lm4_native_conservative_sweep_binding.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_conservative_sweep_binding_review.v1"

EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
EXPECTED_BINDING_SHA256 = (
    "3fc667eabeddee46833c3d181bca1d438a9eb874d51a72565a5b083d110495fc"
)
EXPECTED_REVIEW_SHA256 = (
    "a271316bf5deb863fdb67832a1291158a8292f7950a2e8a8c1b8189b2ef10b91"
)
EXPECTED_BACKEND_FILE_SHA256 = (
    "968140c9b075cc4f6a8d5599edc765cd1b6cde734e32e6632513bd2c94fb6228"
)
EXPECTED_BINDING_FILE_SHA256 = (
    "e620ae81b082a6a1ce957af4b2419464a6d87f5c5c790cf99bc0f8987448c3da"
)
EXPECTED_REVIEW_FILE_SHA256 = (
    "b13a1de38086c865040b81e49045ec3405b6d1b9c12876bec7a3fe45416d7620"
)
EXPECTED_BACKEND_SOURCE_SHA256 = (
    "b7fdcded95e1c2316506cbf9d1c3986e908e63c91e422dea0c90f0bc032862ae"
)
EXPECTED_ADAPTER_SOURCE_SHA256 = (
    "481f2e1e09b9ca45471e130e9022f4ff021b97cc6e72ce5b12f4dd2572b3a433"
)
EXPECTED_BINDING_SOURCE_SHA256 = (
    "a1c49cf0c982df91fe9d07dde7ee9bef3463ecbe4c58ce79d7eec91a66440ebe"
)


class NativeBindingIntegrationPreflightError(ValueError):
    """Raised when the reviewed layers cannot be composed exactly."""


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
        raise NativeBindingIntegrationPreflightError(
            "preflight input is not canonical JSON"
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
        raise NativeBindingIntegrationPreflightError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("hardware_writes") == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements") == 0
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def _function_parameters(node: ast.FunctionDef) -> tuple[str, ...]:
    return tuple(
        argument.arg
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    )


def _source_surface(source: bytes, label: str) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise NativeBindingIntegrationPreflightError(
            f"{label} source is not reviewable Python"
        ) from exc
    imports: set[str] = set()
    functions: dict[str, tuple[str, ...]] = {}
    attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.FunctionDef):
            parent = next(
                (
                    candidate.name
                    for candidate in ast.walk(tree)
                    if isinstance(candidate, ast.ClassDef) and node in candidate.body
                ),
                "",
            )
            functions[f"{parent}.{node.name}" if parent else node.name] = (
                _function_parameters(node)
            )
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)
    if any(name.startswith(("isaacsim", "serial")) for name in imports):
        raise NativeBindingIntegrationPreflightError(
            f"{label} source imports a forbidden runtime"
        )
    return functions, attributes


def _review_source_compatibility(
    backend_source: bytes,
    adapter_source: bytes,
    binding_source: bytes,
) -> None:
    backend_functions, _ = _source_surface(backend_source, "backend")
    adapter_functions, adapter_attributes = _source_surface(adapter_source, "adapter")
    binding_functions, _ = _source_surface(binding_source, "binding")
    backend_parameters = (
        "self",
        "start_sequence",
        "end_sequence",
        "start_joint_targets_rad",
        "end_joint_targets_rad",
    )
    adapter_parameters = (
        "runtime",
        "start_sequence",
        "end_sequence",
        "start_joint_targets_rad",
        "end_joint_targets_rad",
        "reviewed_excluded_pairs",
        "clearance_margin_mm",
        "max_depth",
    )
    required_binding = {
        "NativeIsaacConservativeSweepBinding.__init__",
        "NativeIsaacConservativeSweepBinding.bound_link_spheres",
        "NativeIsaacConservativeSweepBinding.sweep_sphere_any",
        "NativeIsaacConservativeSweepBinding.moving_self_collision_any",
    }
    if (
        backend_functions.get("NominalRoutePhysicsRuntime.check_continuous_clearance")
        != backend_parameters
        or adapter_functions.get("check_continuous_clearance") != adapter_parameters
        or not required_binding.issubset(binding_functions)
        or not {
            "bound_link_spheres",
            "sweep_sphere_any",
            "moving_self_collision_any",
        }.issubset(adapter_attributes)
    ):
        raise NativeBindingIntegrationPreflightError(
            "native clearance integration call surface changed"
        )
    combined = "\n".join(
        source.decode("utf-8")
        for source in (backend_source, adapter_source, binding_source)
    )
    if "SimulationApp(" in combined or "execute_backend(" in binding_source.decode(
        "utf-8"
    ):
        raise NativeBindingIntegrationPreflightError(
            "integration sources contain launch authority"
        )


def build_preflight(
    backend: Mapping[str, Any],
    binding: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    backend_file_sha256: str,
    binding_file_sha256: str,
    review_file_sha256: str,
    backend_source: bytes,
    adapter_source: bytes,
    binding_source: bytes,
) -> dict[str, Any]:
    """Build the exact non-launching integration contract."""

    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    binding_hash = _require_hash(binding, "binding_sha256", "ARM-262 binding")
    review_hash = _require_hash(review, "binding_review_sha256", "ARM-263 review")
    source_hashes = {
        "backend_source": hashlib.sha256(backend_source).hexdigest(),
        "conservative_sweep_adapter_source": hashlib.sha256(adapter_source).hexdigest(),
        "native_binding_source": hashlib.sha256(binding_source).hexdigest(),
    }
    if (
        backend.get("schema") != BACKEND_SCHEMA
        or backend.get("status")
        != "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW"
        or backend_hash != EXPECTED_BACKEND_SHA256
        or binding.get("schema") != BINDING_SCHEMA
        or binding.get("status") != "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW"
        or binding_hash != EXPECTED_BINDING_SHA256
        or review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION"
        or review_hash != EXPECTED_REVIEW_SHA256
        or review.get("source_binding_sha256") != binding_hash
        or review.get("runtime_instantiation_admitted") is not True
        or review.get("next_required_stage")
        != "PREPARE_ZERO_AUTHORITY_NATIVE_BINDING_INTEGRATION_PREFLIGHT"
        or backend_file_sha256 != EXPECTED_BACKEND_FILE_SHA256
        or binding_file_sha256 != EXPECTED_BINDING_FILE_SHA256
        or review_file_sha256 != EXPECTED_REVIEW_FILE_SHA256
        or source_hashes
        != {
            "backend_source": EXPECTED_BACKEND_SOURCE_SHA256,
            "conservative_sweep_adapter_source": EXPECTED_ADAPTER_SOURCE_SHA256,
            "native_binding_source": EXPECTED_BINDING_SOURCE_SHA256,
        }
        or backend.get("backend_source_file_sha256")
        != EXPECTED_BACKEND_SOURCE_SHA256
        or binding.get("source_files_sha256", {}).get("binding_source")
        != EXPECTED_BINDING_SOURCE_SHA256
        or backend.get("runtime_protocol", {}).get("continuous_clearance")
        != "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING"
        or backend.get("acceptance", {}).get(
            "continuous_clearance_required_for_boundary_and_internal_segments"
        )
        is not True
        or backend.get("acceptance", {}).get(
            "minimum_noncontact_tool_key_clearance_mm"
        )
        != 0.5
        or binding.get("runtime_contract", {}).get("clearance_margin_mm") != 0.5
        or len(binding.get("accepted_exclusion_pairs", [])) != 6
        or not _zero_authority(backend)
        or not _zero_authority(binding)
        or not _zero_authority(review)
        or binding.get("launch_admitted") is not False
        or review.get("launch_admitted") is not False
        or binding.get("attempt_consumed") is not False
        or review.get("attempt_consumed") is not False
    ):
        raise NativeBindingIntegrationPreflightError(
            "native integration lineage or zero-authority boundary changed"
        )
    _review_source_compatibility(backend_source, adapter_source, binding_source)

    core: dict[str, Any] = {
        "schema": PREFLIGHT_SCHEMA,
        "preflight_id": "arm264-native-binding-integration-preflight-001",
        "status": "READY_TO_IMPLEMENT_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER",
        "source_backend_sha256": backend_hash,
        "source_binding_sha256": binding_hash,
        "source_binding_review_sha256": review_hash,
        "source_files_sha256": {
            "arm255_backend": backend_file_sha256,
            "arm262_binding": binding_file_sha256,
            "arm263_binding_review": review_file_sha256,
            **source_hashes,
        },
        "verified_integration_surface": {
            "backend_protocol_method": "NominalRoutePhysicsRuntime.check_continuous_clearance",
            "proof_function": "nominal_route_conservative_sweep_adapter.check_continuous_clearance",
            "native_runtime_class": "NativeIsaacConservativeSweepBinding",
            "native_runtime_methods": [
                "bound_link_spheres",
                "sweep_sphere_any",
                "moving_self_collision_any",
            ],
            "clearance_margin_mm": 0.5,
            "certified_exclusion_pair_count": 6,
            "indeterminate_disposition": "FAIL_CLOSED",
        },
        "required_composition_order": [
            "worker_revalidates_arm255_arm262_arm263_and_source_file_hashes",
            "worker_asserts_environment_only_scene_and_robot_query_shapes_disabled",
            "worker_constructs_reviewed_native_binding_from_supplied_articulation_and_scene_query",
            "adapter_calls_arm257_proof_with_exact_six_certified_exclusions",
            "backend_receives_only_determinate_continuous_clearance_evidence",
        ],
        "remaining_implementation_scope": [
            "add_import_safe_runtime_composition_adapter",
            "bind_exact_six_certified_exclusions_without_extension",
            "independently_review_adapter_and_constructor_wiring",
            "separately_admit_any_future_isaac_worker_launch",
        ],
        "runtime_construction_admitted_by_source_review": True,
        "integration_adapter_implemented": False,
        "integration_execution_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "scene_loaded": False,
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
        "next_required_stage": (
            "IMPLEMENT_AND_INDEPENDENTLY_REVIEW_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER"
        ),
        "limitations": [
            "preflight_verifies_static_call_compatibility_not_an_isaac_runtime",
            "preflight_does_not_construct_the_native_binding_or_load_a_scene",
            "canonical_ik_tool_key_metrics_and_root_drift_remain_separate_runtime_dependencies",
            "installed_tool_clamp_cable_and_optional_camera_geometry_remain_excluded",
            "preflight_does_not_consume_the_governed_attempt_or_grant_physical_authority",
        ],
    }
    return {**core, "integration_preflight_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeBindingIntegrationPreflightError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--binding-review", type=Path, required=True)
    parser.add_argument("--backend-source", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--binding-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_preflight(
        _load(args.backend),
        _load(args.binding),
        _load(args.binding_review),
        backend_file_sha256=_file_sha(args.backend),
        binding_file_sha256=_file_sha(args.binding),
        review_file_sha256=_file_sha(args.binding_review),
        backend_source=args.backend_source.read_bytes(),
        adapter_source=args.adapter_source.read_bytes(),
        binding_source=args.binding_source.read_bytes(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
