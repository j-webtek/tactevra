from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "software/integrations/isaac_sim/nominal_route_native_clearance_adapter.py"


def _module(name="arm265_adapter"):
    integration = str(SOURCE.parent)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _authority():
    return {
        "launch_admitted": False, "attempt_consumed": False,
        "hardware_access": False, "hardware_writes": 0,
        "physical_authority": False, "physical_movements": 0,
        "controller_commands": [], "wire_commands": [], "gate_promotions": [],
    }


def _sources(module):
    pairs = [[f"robot:link{i}", f"robot:link{i + 1}"] for i in range(6)]
    binding_core = {
        "schema": module.BINDING_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW",
        "accepted_exclusion_pairs": pairs,
        "source_files_sha256": {"binding_source": "5" * 64},
        **_authority(),
    }
    binding = {**binding_core, "binding_sha256": module._sha(binding_core)}
    review_core = {
        "schema": module.BINDING_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": binding["binding_sha256"],
        **_authority(),
    }
    review = {**review_core, "binding_review_sha256": module._sha(review_core)}
    preflight_core = {
        "schema": module.PREFLIGHT_SCHEMA,
        "status": "READY_TO_IMPLEMENT_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER",
        "source_binding_sha256": binding["binding_sha256"],
        "source_binding_review_sha256": review["binding_review_sha256"],
        "next_required_stage": "IMPLEMENT_AND_INDEPENDENTLY_REVIEW_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER",
        "source_files_sha256": {
            "conservative_sweep_adapter_source": "4" * 64,
            "native_binding_source": "5" * 64,
        },
        "runtime_construction_admitted_by_source_review": True,
        "integration_adapter_implemented": False,
        "integration_execution_admitted": False,
        "verified_integration_surface": {
            "clearance_margin_mm": 0.5,
            "certified_exclusion_pair_count": 6,
        },
        **_authority(),
    }
    preflight = {**preflight_core, "integration_preflight_sha256": module._sha(preflight_core)}
    module.EXPECTED_PREFLIGHT_SHA256 = preflight["integration_preflight_sha256"]
    module.EXPECTED_BINDING_SHA256 = binding["binding_sha256"]
    module.EXPECTED_BINDING_REVIEW_SHA256 = review["binding_review_sha256"]
    module.EXPECTED_PREFLIGHT_FILE_SHA256 = "1" * 64
    module.EXPECTED_BINDING_FILE_SHA256 = "2" * 64
    module.EXPECTED_BINDING_REVIEW_FILE_SHA256 = "3" * 64
    module.EXPECTED_PROOF_SOURCE_SHA256 = "4" * 64
    module.EXPECTED_BINDING_SOURCE_SHA256 = "5" * 64
    return preflight, binding, review


def _definition(module):
    preflight, binding, review = _sources(module)
    definition = module.build_adapter_definition(
        preflight, binding, review,
        preflight_file_sha256="1" * 64,
        binding_file_sha256="2" * 64,
        binding_review_file_sha256="3" * 64,
        proof_source_file_sha256="4" * 64,
        binding_source_file_sha256="5" * 64,
        adapter_source_file_sha256="6" * 64,
    )
    return definition, binding, review


class _Binding:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def _accepted_review(module, definition):
    core = {
        "schema": module.ADAPTER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": definition["adapter_sha256"],
        "runtime_integration_admitted": True,
        "launch_admitted": False, "attempt_consumed": False,
        "hardware_access": False, "physical_authority": False,
    }
    return {**core, "adapter_review_sha256": module._sha(core)}


def test_arm265_definition_pins_reviewed_composition_boundary():
    module = _module()
    result, _binding, _review = _definition(module)
    assert result["status"] == "READY_FOR_INDEPENDENT_NATIVE_CLEARANCE_ADAPTER_REVIEW"
    assert result["backend_method"] == "check_continuous_clearance"
    assert result["clearance_margin_mm"] == 0.5
    assert result["maximum_subdivision_depth"] == 12
    assert len(result["accepted_exclusion_pairs"]) == 6
    assert result["environment_only_scene_required"] is True
    assert result["integration_execution_admitted"] is False


def test_arm265_definition_rejects_self_consistent_lineage_substitution():
    module = _module()
    preflight, binding, review = _sources(module)
    preflight["status"] = "SUBSTITUTED"
    unsigned = dict(preflight)
    unsigned.pop("integration_preflight_sha256")
    preflight["integration_preflight_sha256"] = module._sha(unsigned)
    with pytest.raises(module.NativeClearanceAdapterError, match="boundary changed"):
        module.build_adapter_definition(
            preflight, binding, review,
            preflight_file_sha256="1" * 64, binding_file_sha256="2" * 64,
            binding_review_file_sha256="3" * 64,
            proof_source_file_sha256="4" * 64,
            binding_source_file_sha256="5" * 64,
            adapter_source_file_sha256="6" * 64,
        )


def test_arm265_runtime_composes_native_binding_into_backend_method(monkeypatch):
    module = _module()
    definition, binding, binding_review = _definition(module)
    captured = {}

    def proof(runtime, **kwargs):
        captured.update(kwargs)
        assert isinstance(runtime, _Binding)
        return {"continuous": True, "determinate": True, "minimum_clearance_mm": 0.5}

    monkeypatch.setattr(module, "NativeIsaacConservativeSweepBinding", _Binding)
    monkeypatch.setattr(module, "check_continuous_clearance", proof)
    runtime = module.NativeClearanceRuntimeAdapter(
        definition, adapter_review=_accepted_review(module, definition),
        binding_definition=binding, binding_review=binding_review,
        articulation=object(), scene_query=object(), environment_only_scene=True,
        robot_collision_query_shapes_enabled=False,
    )
    result = runtime.check_continuous_clearance(
        start_sequence=7, end_sequence=8,
        start_joint_targets_rad=[0.0] * 6, end_joint_targets_rad=[0.001] * 6,
    )
    assert result["continuous"] is True
    assert captured["clearance_margin_mm"] == 0.5
    assert captured["max_depth"] == 12
    assert len(captured["reviewed_excluded_pairs"]) == 6


def test_arm265_runtime_requires_environment_only_scene(monkeypatch):
    module = _module()
    definition, binding, binding_review = _definition(module)
    monkeypatch.setattr(module, "NativeIsaacConservativeSweepBinding", _Binding)
    with pytest.raises(module.NativeClearanceAdapterError, match="not admissible"):
        module.NativeClearanceRuntimeAdapter(
            definition, adapter_review=_accepted_review(module, definition),
            binding_definition=binding, binding_review=binding_review,
            articulation=object(), scene_query=object(), environment_only_scene=False,
            robot_collision_query_shapes_enabled=True,
        )


def test_arm265_import_and_definition_cli_have_no_runtime_side_effect():
    source = SOURCE.read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "execute_backend(" not in source
    assert "import serial" not in source
