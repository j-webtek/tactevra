from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    ROOT / "software/integrations/isaac_sim/nominal_route_isaac_runtime_capability.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("arm256_capability", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backend(module):
    value = {
        "schema": module.BACKEND_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW",
        "runtime_protocol": {
            "continuous_clearance": "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING"
        },
        "acceptance": {"minimum_noncontact_tool_key_clearance_mm": 0.5},
    }
    return {**value, "backend_sha256": module._sha(value)}


def _toolchain(module):
    return {
        "schema": module.TOOLCHAIN_SCHEMA,
        "selection_status": "SELECTED",
        "isaac_sim_version": "6.1.0.0",
        "hardware_access": False,
        "physical_authority": False,
        "wire_commands": [],
    }


def _observation(module):
    value = {
        "schema": module.OBSERVATION_SCHEMA,
        "status": "PASS_NATIVE_LINEAR_SWEEP_CAPABILITY",
        "isaacsim_distribution": "6.1.0.0",
        "kit_version": "6.1.0",
        "scene_query_methods": list(module.REQUIRED_SWEEP_METHODS),
        "required_sweep_methods": list(module.REQUIRED_SWEEP_METHODS),
        "missing_required_sweep_methods": [],
        "api_stub_file_sha256": "a" * 64,
        "observed_api_semantics": {
            "native_linear_translation_sweeps": True,
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
    return {**value, "observation_sha256": module._sha(value)}


def _assess(module, backend=None, toolchain=None, observation=None):
    return module.assess_runtime_capability(
        backend or _backend(module),
        toolchain or _toolchain(module),
        observation or _observation(module),
        backend_file_sha256="b" * 64,
        toolchain_file_sha256="c" * 64,
        observation_file_sha256="d" * 64,
    )


def test_arm256_import_is_isaac_side_effect_free() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    prefix = source.split("def probe_installed_runtime", 1)[0]

    assert "from isaacsim import" not in prefix
    assert "SimulationApp(" not in prefix


def test_arm256_admits_native_sweeps_but_not_direct_articulated_proof() -> None:
    module = _module()
    result = _assess(module)

    assert result["status"] == (
        "READY_TO_IMPLEMENT_CONSERVATIVE_SWEPT_ENVELOPE_ADAPTER"
    )
    assert result["native_capability"] == {
        "continuous_linear_shape_sweep_available": True,
        "shape_mesh_box_and_sphere_sweeps_available": True,
        "direct_articulated_path_query_available": False,
        "direct_signed_minimum_distance_available": False,
        "arm255_protocol_satisfied_directly": False,
    }
    assert result["required_adapter_strategy"]["name"] == (
        "CONSERVATIVE_BOUNDING_SPHERE_INTERVAL_SWEEPS"
    )
    assert result["required_adapter_strategy"]["clearance_margin_inflation_mm"] == 0.5
    assert result["adapter_implemented"] is False
    assert result["attempt_consumed"] is False
    assert result["physical_authority"] is False
    unsigned = dict(result)
    assert unsigned.pop("assessment_sha256") == module._sha(unsigned)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("end_orientation_parameter_available", True),
        ("articulated_joint_interpolation_parameter_available", True),
        ("signed_minimum_distance_query_available", True),
    ],
)
def test_arm256_rejects_semantic_claim_drift(field: str, value: bool) -> None:
    module = _module()
    observation = copy.deepcopy(_observation(module))
    observation["observed_api_semantics"][field] = value
    observation.pop("observation_sha256")
    observation["observation_sha256"] = module._sha(observation)

    with pytest.raises(module.RuntimeCapabilityError, match="inadmissible"):
        _assess(module, observation=observation)


def test_arm256_rejects_missing_native_sweep() -> None:
    module = _module()
    observation = copy.deepcopy(_observation(module))
    observation["scene_query_methods"].remove("sweep_shape_closest")
    observation["missing_required_sweep_methods"] = ["sweep_shape_closest"]
    observation["status"] = "FAIL_REQUIRED_SWEEP_METHOD_ABSENT"
    observation.pop("observation_sha256")
    observation["observation_sha256"] = module._sha(observation)

    with pytest.raises(module.RuntimeCapabilityError, match="inadmissible"):
        _assess(module, observation=observation)


def test_arm256_rejects_backend_or_toolchain_drift() -> None:
    module = _module()
    backend = _backend(module)
    backend["acceptance"]["minimum_noncontact_tool_key_clearance_mm"] = 0.4
    with pytest.raises(module.RuntimeCapabilityError, match="hash mismatch"):
        _assess(module, backend=backend)

    toolchain = _toolchain(module)
    toolchain["isaac_sim_version"] = "6.2.0.0"
    with pytest.raises(module.RuntimeCapabilityError, match="toolchain"):
        _assess(module, toolchain=toolchain)
