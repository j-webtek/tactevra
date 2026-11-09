from __future__ import annotations

import ast
import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    ROOT
    / "software/integrations/isaac_sim/nominal_route_native_binding_integration_preflight.py"
)
BACKEND_SOURCE = ROOT / "software/integrations/isaac_sim/nominal_route_physics_backend.py"
ADAPTER_SOURCE = (
    ROOT
    / "software/integrations/isaac_sim/nominal_route_conservative_sweep_adapter.py"
)
BINDING_SOURCE = (
    ROOT / "software/integrations/isaac_sim/nominal_route_native_sweep_binding.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("arm264_preflight", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _inputs(module):
    backend_core = {
        "schema": module.BACKEND_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW",
        "backend_source_file_sha256": module._file_sha(BACKEND_SOURCE),
        "runtime_protocol": {
            "continuous_clearance": "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING"
        },
        "acceptance": {
            "continuous_clearance_required_for_boundary_and_internal_segments": True,
            "minimum_noncontact_tool_key_clearance_mm": 0.5,
        },
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    backend = {**backend_core, "backend_sha256": module._sha(backend_core)}
    binding_core = {
        "schema": module.BINDING_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW",
        "source_files_sha256": {
            "binding_source": module._file_sha(BINDING_SOURCE)
        },
        "runtime_contract": {"clearance_margin_mm": 0.5},
        "accepted_exclusion_pairs": [[f"left-{index}", f"right-{index}"] for index in range(6)],
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    binding = {**binding_core, "binding_sha256": module._sha(binding_core)}
    review_core = {
        "schema": module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": binding["binding_sha256"],
        "runtime_instantiation_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "PREPARE_ZERO_AUTHORITY_NATIVE_BINDING_INTEGRATION_PREFLIGHT",
    }
    review = {
        **review_core,
        "binding_review_sha256": module._sha(review_core),
    }
    module.EXPECTED_BACKEND_SHA256 = backend["backend_sha256"]
    module.EXPECTED_BINDING_SHA256 = binding["binding_sha256"]
    module.EXPECTED_REVIEW_SHA256 = review["binding_review_sha256"]
    module.EXPECTED_BACKEND_FILE_SHA256 = "a" * 64
    module.EXPECTED_BINDING_FILE_SHA256 = "b" * 64
    module.EXPECTED_REVIEW_FILE_SHA256 = "c" * 64
    module.EXPECTED_BACKEND_SOURCE_SHA256 = module._file_sha(BACKEND_SOURCE)
    module.EXPECTED_ADAPTER_SOURCE_SHA256 = module._file_sha(ADAPTER_SOURCE)
    module.EXPECTED_BINDING_SOURCE_SHA256 = module._file_sha(BINDING_SOURCE)
    return backend, binding, review


def _build(module, backend, binding, review, **overrides):
    arguments = {
        "backend_file_sha256": "a" * 64,
        "binding_file_sha256": "b" * 64,
        "review_file_sha256": "c" * 64,
        "backend_source": BACKEND_SOURCE.read_bytes(),
        "adapter_source": ADAPTER_SOURCE.read_bytes(),
        "binding_source": BINDING_SOURCE.read_bytes(),
    }
    arguments.update(overrides)
    return module.build_preflight(backend, binding, review, **arguments)


def test_arm264_preflight_hash_binds_the_exact_integration_surface():
    module = _module()
    backend, binding, review = _inputs(module)

    result = _build(module, backend, binding, review)

    assert result["status"] == "READY_TO_IMPLEMENT_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER"
    assert result["source_backend_sha256"] == backend["backend_sha256"]
    assert result["source_binding_sha256"] == binding["binding_sha256"]
    assert result["source_binding_review_sha256"] == review["binding_review_sha256"]
    assert result["verified_integration_surface"]["clearance_margin_mm"] == 0.5
    assert result["verified_integration_surface"]["certified_exclusion_pair_count"] == 6
    assert result["runtime_construction_admitted_by_source_review"] is True
    assert result["integration_adapter_implemented"] is False
    assert result["integration_execution_admitted"] is False
    assert result["launch_admitted"] is False
    assert result["attempt_consumed"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


def test_arm264_preflight_is_deterministic():
    module = _module()
    backend, binding, review = _inputs(module)

    first = _build(module, backend, binding, review)
    second = _build(module, backend, binding, review)

    assert first == second
    unsigned = dict(first)
    claimed = unsigned.pop("integration_preflight_sha256")
    assert claimed == module._sha(unsigned)


@pytest.mark.parametrize("source", ["backend", "binding", "review"])
def test_arm264_rejects_self_consistent_lineage_substitution(source):
    module = _module()
    backend, binding, review = _inputs(module)
    documents = {"backend": backend, "binding": binding, "review": review}
    changed = copy.deepcopy(documents[source])
    key = {
        "backend": "backend_sha256",
        "binding": "binding_sha256",
        "review": "binding_review_sha256",
    }[source]
    changed["status"] = "SUBSTITUTED"
    unsigned = dict(changed)
    unsigned.pop(key)
    changed[key] = module._sha(unsigned)
    documents[source] = changed

    with pytest.raises(module.NativeBindingIntegrationPreflightError, match="lineage"):
        _build(module, documents["backend"], documents["binding"], documents["review"])


def test_arm264_rejects_source_drift():
    module = _module()
    backend, binding, review = _inputs(module)

    with pytest.raises(module.NativeBindingIntegrationPreflightError, match="lineage"):
        _build(
            module,
            backend,
            binding,
            review,
            adapter_source=ADAPTER_SOURCE.read_bytes() + b"\n# drift\n",
        )


def test_arm264_rejects_incompatible_call_surface_even_when_hash_pinned():
    module = _module()
    backend, binding, review = _inputs(module)
    changed = ADAPTER_SOURCE.read_text(encoding="utf-8").replace(
        "start_sequence: int,", "renamed_start_sequence: int,", 1
    ).encode()
    module.EXPECTED_ADAPTER_SOURCE_SHA256 = module.hashlib.sha256(changed).hexdigest()

    with pytest.raises(module.NativeBindingIntegrationPreflightError, match="call surface"):
        _build(module, backend, binding, review, adapter_source=changed)


def test_arm264_rejects_authority_escalation():
    module = _module()
    backend, binding, review = _inputs(module)
    changed = copy.deepcopy(review)
    changed["launch_admitted"] = True
    unsigned = dict(changed)
    unsigned.pop("binding_review_sha256")
    changed["binding_review_sha256"] = module._sha(unsigned)
    module.EXPECTED_REVIEW_SHA256 = changed["binding_review_sha256"]

    with pytest.raises(module.NativeBindingIntegrationPreflightError, match="zero-authority"):
        _build(module, backend, binding, changed)


def test_arm264_source_has_no_isaac_launch_or_worker_execution():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not any(name.startswith("isaacsim") for name in imported)
    assert not {
        "SimulationApp",
        "execute_backend",
        "NativeIsaacConservativeSweepBinding",
    }.intersection(calls)
