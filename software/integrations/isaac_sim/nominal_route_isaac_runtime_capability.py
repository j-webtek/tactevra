"""Probe and assess the Isaac scene-query boundary required by ARM-255.

The module is import-safe outside Isaac.  Only ``probe_installed_runtime``
imports or starts ``SimulationApp``.  The resulting evidence deliberately
distinguishes native linear primitive sweeps from a proof over an articulated
joint interpolation: the former is available in Isaac Sim 6.1, while the
latter still requires a reviewed conservative swept-envelope adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any, Mapping


OBSERVATION_SCHEMA = "tactevra.isaac_lm4_runtime_capability_observation.v1"
ASSESSMENT_SCHEMA = "tactevra.isaac_lm4_runtime_capability_assessment.v1"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
TOOLCHAIN_SCHEMA = "rocell.isaac_sim_toolchain_lock.v1"

REQUIRED_SWEEP_METHODS = (
    "sweep_box_all",
    "sweep_box_any",
    "sweep_box_closest",
    "sweep_mesh_all",
    "sweep_mesh_any",
    "sweep_mesh_closest",
    "sweep_shape_all",
    "sweep_shape_any",
    "sweep_shape_closest",
    "sweep_sphere_all",
    "sweep_sphere_any",
    "sweep_sphere_closest",
)
REQUIRED_STUB_MARKERS = (
    "def sweep_shape_closest",
    "unit_dir:",
    "distance: float",
    "A convex mesh approximation will be used",
)


class RuntimeCapabilityError(ValueError):
    """Raised when capability evidence or source bindings fail closed."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(value: Mapping[str, Any], key: str, label: str) -> str:
    claimed = value.get(key)
    unsigned = dict(value)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise RuntimeCapabilityError(f"{label} hash mismatch")
    return claimed


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def probe_installed_runtime(
    api_stub: Path, *, output_path: Path | None = None
) -> dict[str, Any]:
    """Start Isaac headlessly and retain only scene-query capability evidence."""
    stub = api_stub.resolve(strict=True)
    stub_text = stub.read_text(encoding="utf-8")
    missing_markers = [item for item in REQUIRED_STUB_MARKERS if item not in stub_text]
    if missing_markers:
        raise RuntimeCapabilityError(
            f"Isaac scene-query stub semantics changed: {missing_markers}"
        )

    app = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.kit.app
        from omni.physx import get_physx_scene_query_interface

        query = get_physx_scene_query_interface()
        methods = sorted(
            name
            for name in dir(query)
            if name.startswith(("sweep_", "overlap_", "raycast_"))
        )
        missing_methods = sorted(set(REQUIRED_SWEEP_METHODS) - set(methods))
        kit = omni.kit.app.get_app()
        observation: dict[str, Any] = {
            "schema": OBSERVATION_SCHEMA,
            "status": (
                "PASS_NATIVE_LINEAR_SWEEP_CAPABILITY"
                if not missing_methods
                else "FAIL_REQUIRED_SWEEP_METHOD_ABSENT"
            ),
            "isaacsim_distribution": importlib.metadata.version("isaacsim"),
            "kit_version": kit.get_app_version(),
            "scene_query_methods": methods,
            "required_sweep_methods": list(REQUIRED_SWEEP_METHODS),
            "missing_required_sweep_methods": missing_methods,
            "api_stub_file_sha256": _file_sha(stub),
            "observed_api_semantics": {
                "native_linear_translation_sweeps": not missing_methods,
                "shape_sweep_uses_current_gprim_pose": True,
                "sweep_direction_and_distance_required": True,
                "mesh_sweep_uses_convex_approximation": True,
                "end_orientation_parameter_available": False,
                "articulated_joint_interpolation_parameter_available": False,
                "signed_minimum_distance_query_available": False,
            },
            "scene_loaded": False,
            "trajectory_loaded": False,
            "trajectory_playback": False,
            "attempt_consumed": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "wire_commands": [],
            "gate_promotions": [],
        }
        observation["observation_sha256"] = _sha(observation)
        # Standalone Kit may terminate the interpreter from ``app.close()``.
        # Retain evidence before shutdown, as the other native probes do.
        if output_path is not None:
            _write_json(output_path, observation)
        return observation
    finally:
        if app is not None:
            app.close()


def assess_runtime_capability(
    backend: Mapping[str, Any],
    toolchain: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    backend_file_sha256: str,
    toolchain_file_sha256: str,
    observation_file_sha256: str,
) -> dict[str, Any]:
    """Bind the live probe and state exactly what remains for the adapter."""
    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    observation_hash = _require_hash(
        observation, "observation_sha256", "runtime capability observation"
    )
    if (
        backend.get("schema") != BACKEND_SCHEMA
        or backend.get("status")
        != "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW"
        or backend.get("runtime_protocol", {}).get("continuous_clearance")
        != "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING"
    ):
        raise RuntimeCapabilityError("ARM-255 backend contract changed")
    if (
        toolchain.get("schema") != TOOLCHAIN_SCHEMA
        or toolchain.get("selection_status") != "SELECTED"
        or toolchain.get("isaac_sim_version") != "6.1.0.0"
        or toolchain.get("hardware_access") is not False
        or toolchain.get("physical_authority") is not False
        or toolchain.get("wire_commands") != []
    ):
        raise RuntimeCapabilityError("selected Isaac toolchain changed")
    semantics = observation.get("observed_api_semantics", {})
    methods = observation.get("scene_query_methods")
    if (
        observation.get("schema") != OBSERVATION_SCHEMA
        or observation.get("status") != "PASS_NATIVE_LINEAR_SWEEP_CAPABILITY"
        or observation.get("isaacsim_distribution") != toolchain["isaac_sim_version"]
        or not isinstance(methods, list)
        or not set(REQUIRED_SWEEP_METHODS).issubset(methods)
        or observation.get("missing_required_sweep_methods") != []
        or semantics.get("native_linear_translation_sweeps") is not True
        or semantics.get("end_orientation_parameter_available") is not False
        or semantics.get("articulated_joint_interpolation_parameter_available")
        is not False
        or semantics.get("signed_minimum_distance_query_available") is not False
        or observation.get("attempt_consumed") is not False
        or observation.get("hardware_access") is not False
        or observation.get("physical_authority") is not False
    ):
        raise RuntimeCapabilityError("runtime capability observation is inadmissible")
    for digest, label in (
        (backend_file_sha256, "backend file"),
        (toolchain_file_sha256, "toolchain file"),
        (observation_file_sha256, "observation file"),
    ):
        if not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeCapabilityError(f"{label} hash is invalid")

    result: dict[str, Any] = {
        "schema": ASSESSMENT_SCHEMA,
        "assessment_id": "arm256-isaac-runtime-capability-gate-001",
        "status": "READY_TO_IMPLEMENT_CONSERVATIVE_SWEPT_ENVELOPE_ADAPTER",
        "source_backend_sha256": backend_hash,
        "source_backend_file_sha256": backend_file_sha256,
        "source_toolchain_file_sha256": toolchain_file_sha256,
        "source_observation_sha256": observation_hash,
        "source_observation_file_sha256": observation_file_sha256,
        "isaacsim_distribution": observation["isaacsim_distribution"],
        "kit_version": observation["kit_version"],
        "native_capability": {
            "continuous_linear_shape_sweep_available": True,
            "shape_mesh_box_and_sphere_sweeps_available": True,
            "direct_articulated_path_query_available": False,
            "direct_signed_minimum_distance_available": False,
            "arm255_protocol_satisfied_directly": False,
        },
        "required_adapter_strategy": {
            "name": "CONSERVATIVE_BOUNDING_SPHERE_INTERVAL_SWEEPS",
            "per_link_collision_primitive_envelopes": True,
            "clearance_margin_inflation_mm": backend["acceptance"][
                "minimum_noncontact_tool_key_clearance_mm"
            ],
            "bound_center_path_deviation_over_joint_interval": True,
            "bound_rotation_with_orientation_invariant_spheres": True,
            "recursively_subdivide_until_bounds_are_determinate": True,
            "separately_check_moving_self_collision_pairs": True,
            "apply_only_reviewed_pair_exclusions": True,
            "indeterminate_or_budget_exhausted_disposition": "FAIL_CLOSED",
            "discrete_overlap_sampling_accepted": False,
        },
        "adapter_implemented": False,
        "backend_review_admitted": False,
        "attempt_consumed": False,
        "trajectory_playback": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "IMPLEMENT_AND_TEST_HASH_PINNED_CONSERVATIVE_ENVELOPE_ADAPTER"
        ),
        "limitations": [
            "native_sweep_methods_do_not_alone_prove_articulated_joint_motion_clearance",
            "native_sweeps_do_not_return_signed_minimum_distance_without_a_hit",
            "capability_probe_loads_no_scene_and_consumes_no_route_attempt",
            "assessment_does_not_authorize_backend_launch_or_physical_motion",
        ],
    }
    result["assessment_sha256"] = _sha(result)
    return result


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RuntimeCapabilityError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe-runtime", action="store_true")
    mode.add_argument("--assess", action="store_true")
    parser.add_argument("--api-stub", type=Path)
    parser.add_argument("--backend", type=Path)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--observation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.probe_runtime:
        if args.api_stub is None:
            parser.error("--probe-runtime requires --api-stub")
        result = probe_installed_runtime(args.api_stub, output_path=args.output)
    else:
        if args.backend is None or args.toolchain is None or args.observation is None:
            parser.error("--assess requires --backend, --toolchain, and --observation")
        result = assess_runtime_capability(
            _load(args.backend),
            _load(args.toolchain),
            _load(args.observation),
            backend_file_sha256=_file_sha(args.backend),
            toolchain_file_sha256=_file_sha(args.toolchain),
            observation_file_sha256=_file_sha(args.observation),
        )
    _write_json(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
