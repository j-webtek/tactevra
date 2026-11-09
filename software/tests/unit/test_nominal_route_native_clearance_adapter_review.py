from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_native_clearance_adapter.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_native_clearance_adapter_review.py"
ARTIFACTS = Path("C:/IsaacSim/artifacts/issue190")
ADAPTER = ARTIFACTS / "arm265-native-clearance-adapter-001/adapter.json"
PREFLIGHT = ARTIFACTS / "arm264-native-binding-integration-preflight-001/preflight.json"
BINDING = ARTIFACTS / "arm262-native-sweep-binding-003/binding.json"
BINDING_REVIEW = ARTIFACTS / "arm263-native-sweep-binding-review-001/review.json"
PROOF_SOURCE = INTEGRATION / "nominal_route_conservative_sweep_adapter.py"
BINDING_SOURCE = INTEGRATION / "nominal_route_native_sweep_binding.py"


def _module():
    integration = str(INTEGRATION)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location("arm265_review", REVIEW_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _review(module, *, source=SOURCE, adapter=None):
    return module.review_adapter(
        adapter or _load(ADAPTER),
        _load(PREFLIGHT),
        _load(BINDING),
        _load(BINDING_REVIEW),
        adapter_file_sha256=module._file_sha(ADAPTER),
        adapter_source_path=source,
        preflight_file_sha256=module._file_sha(PREFLIGHT),
        binding_file_sha256=module._file_sha(BINDING),
        binding_review_file_sha256=module._file_sha(BINDING_REVIEW),
        proof_source_file_sha256=module._file_sha(PROOF_SOURCE),
        binding_source_file_sha256=module._file_sha(BINDING_SOURCE),
    )


def test_arm265_review_accepts_exact_zero_authority_composition():
    module = _module()
    result = _review(module)

    assert result["status"] == "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
    assert result["definition_reproduced"] is True
    assert result["source_call_surface_reviewed"] is True
    assert result["non_isaac_runtime_composition_verified"] is True
    assert result["recursive_refinement_verified"] is True
    assert result["runtime_integration_admitted"] is True
    assert result["launch_admitted"] is False
    assert result["attempt_consumed"] is False
    assert result["next_required_stage"] == "PREPARE_ZERO_AUTHORITY_NOMINAL_ROUTE_RUNTIME_COMPOSITION"


def test_arm265_review_rejects_self_consistent_artifact_substitution():
    module = _module()
    changed = _load(ADAPTER)
    changed["maximum_subdivision_depth"] = 11
    unsigned = dict(changed)
    unsigned.pop("adapter_sha256")
    changed["adapter_sha256"] = module._sha(unsigned)

    with pytest.raises(module.NativeClearanceAdapterReviewError, match="boundary changed"):
        _review(module, adapter=changed)


def test_arm265_review_rejects_source_drift(tmp_path):
    module = _module()
    changed = tmp_path / SOURCE.name
    changed.write_bytes(SOURCE.read_bytes() + b"\n# drift\n")

    with pytest.raises(module.NativeClearanceAdapterReviewError, match="boundary changed"):
        _review(module, source=changed)


def test_arm265_source_review_rejects_runtime_import():
    module = _module()
    with pytest.raises(module.NativeClearanceAdapterReviewError, match="forbidden runtime"):
        module._review_source(b"import isaacsim\nclass NativeClearanceRuntimeAdapter: pass\n")


def test_arm265_review_cli_is_zero_authority():
    source = REVIEW_SOURCE.read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "import isaacsim" not in source
    assert "import serial" not in source
