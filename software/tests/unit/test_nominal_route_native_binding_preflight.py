from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = (
        ROOT
        / "software/integrations/isaac_sim/nominal_route_native_binding_preflight.py"
    )
    spec = importlib.util.spec_from_file_location("arm258_preflight", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _inputs(module):
    backend_core = {
        "schema": module.BACKEND_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW",
    }
    backend = {**backend_core, "backend_sha256": module._sha(backend_core)}
    capability_core = {
        "schema": module.ASSESSMENT_SCHEMA,
        "status": "READY_TO_IMPLEMENT_CONSERVATIVE_SWEPT_ENVELOPE_ADAPTER",
        "source_backend_sha256": backend["backend_sha256"],
        "required_adapter_strategy": {
            "name": "CONSERVATIVE_BOUNDING_SPHERE_INTERVAL_SWEEPS"
        },
    }
    capability = {
        **capability_core,
        "assessment_sha256": module._sha(capability_core),
    }
    diagnostic = {
        "schema": "tactevra.isaac_lm1_collision_pair_policy.v1",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY",
        "limitations": ["policy_does_not_prove_continuous_clearance"],
    }
    kwargs = {
        "backend_file_sha256": "1" * 64,
        "capability_file_sha256": "2" * 64,
        "arm257_source_sha256": "3" * 64,
        "api_stub_sha256": "4" * 64,
        "urdf_sha256": module.EXPECTED_URDF_SHA256,
        "geometry_prior_sha256": "5" * 64,
        "diagnostic_pair_policy_file_sha256": "6" * 64,
    }
    return backend, capability, diagnostic, kwargs


def test_arm258_current_inputs_fail_closed_on_exact_two_proof_gaps():
    module = _module()
    backend, capability, diagnostic, kwargs = _inputs(module)

    result = module.build_preflight(backend, capability, diagnostic, **kwargs)

    assert result["status"] == "BLOCKED_PENDING_CERTIFIED_PROOF_INPUTS"
    assert result["blockers"] == [
        "CERTIFIED_LINK_SPHERE_PROFILE_MISSING",
        "CONTINUOUS_CLEARANCE_PAIR_POLICY_MISSING",
    ]
    assert result["launch_admitted"] is False
    assert result["attempt_consumed"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


def test_arm258_becomes_implementation_ready_only_with_proof_scoped_inputs():
    module = _module()
    backend, capability, diagnostic, kwargs = _inputs(module)
    sphere_profile = {
        "schema": module.SPHERE_PROFILE_SCHEMA,
        "status": "CERTIFIED_FOR_SIMULATION_CONTINUOUS_CLEARANCE",
        "source_urdf_sha256": module.EXPECTED_URDF_SHA256,
        "link_spheres": [
            {"link_name": name, "local_center_mm": [0.0, 0.0, 0.0], "radius_mm": 1.0}
            for name in module.REQUIRED_LINKS
        ],
    }
    proof_policy = {
        "schema": module.PROOF_POLICY_SCHEMA,
        "status": "ACCEPTED_FOR_SIMULATION_CONTINUOUS_CLEARANCE",
        "source_urdf_sha256": module.EXPECTED_URDF_SHA256,
        "accepted_exclusion_pairs": [],
        "hardware_access": False,
        "physical_authority": False,
    }

    result = module.build_preflight(
        backend,
        capability,
        diagnostic,
        sphere_profile=sphere_profile,
        proof_pair_policy=proof_policy,
        **kwargs,
    )

    assert result["status"] == "READY_TO_IMPLEMENT_NATIVE_BINDING"
    assert result["blockers"] == []
    assert result["launch_admitted"] is False


@pytest.mark.parametrize("field", ["backend", "capability"])
def test_arm258_rejects_hash_drift(field):
    module = _module()
    backend, capability, diagnostic, kwargs = _inputs(module)
    changed = copy.deepcopy(backend if field == "backend" else capability)
    changed["status"] = "CHANGED"
    args = (changed, capability) if field == "backend" else (backend, changed)

    with pytest.raises(module.NativeBindingPreflightError, match="hash mismatch"):
        module.build_preflight(*args, diagnostic, **kwargs)


def test_arm258_rejects_wrong_urdf_identity():
    module = _module()
    backend, capability, diagnostic, kwargs = _inputs(module)
    kwargs["urdf_sha256"] = "f" * 64

    with pytest.raises(module.NativeBindingPreflightError, match="URDF identity"):
        module.build_preflight(backend, capability, diagnostic, **kwargs)


def test_arm258_import_has_no_isaac_or_hardware_side_effect():
    source = (
        ROOT
        / "software/integrations/isaac_sim/nominal_route_native_binding_preflight.py"
    ).read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "serial" not in source
