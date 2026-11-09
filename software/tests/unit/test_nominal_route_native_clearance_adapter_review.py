from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_native_clearance_adapter.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_native_clearance_adapter_review.py"
SUPPORT_SOURCE = Path(__file__).with_name("test_nominal_route_native_clearance_adapter.py")


def _load_module(name, path):
    if name in sys.modules:
        return sys.modules[name]
    for folder in (str(INTEGRATION), str(path.parent)):
        if folder not in sys.path:
            sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Binding:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs


def _setup(monkeypatch):
    support = _load_module("arm265_test_support", SUPPORT_SOURCE)
    adapter = support._module("arm265_adapter_for_review")
    preflight, binding, binding_review = support._sources(adapter)
    source_sha = adapter._file_sha(SOURCE)
    definition = adapter.build_adapter_definition(
        preflight,
        binding,
        binding_review,
        preflight_file_sha256="1" * 64,
        binding_file_sha256="2" * 64,
        binding_review_file_sha256="3" * 64,
        proof_source_file_sha256="4" * 64,
        binding_source_file_sha256="5" * 64,
        adapter_source_file_sha256=source_sha,
    )
    reviewer = _load_module("arm265_review", REVIEW_SOURCE)
    reviewer.EXPECTED_ADAPTER_SHA256 = definition["adapter_sha256"]
    reviewer.EXPECTED_ADAPTER_FILE_SHA256 = "a" * 64
    reviewer.EXPECTED_ADAPTER_SOURCE_SHA256 = source_sha
    monkeypatch.setattr(reviewer, "_import_adapter", lambda _path: adapter)
    monkeypatch.setattr(adapter, "NativeIsaacConservativeSweepBinding", _Binding)

    def proof(runtime, **_kwargs):
        query = runtime.kwargs["scene_query"]
        query.sweep_sphere_any()
        query.sweep_sphere_any()
        query.sweep_sphere_any()
        return {
            "continuous": True,
            "determinate": True,
            "minimum_clearance_mm": 0.5,
            "intervals_inspected": 3,
        }

    monkeypatch.setattr(adapter, "check_continuous_clearance", proof)
    return reviewer, adapter, definition, preflight, binding, binding_review


def _review(monkeypatch, *, adapter_document=None, source=SOURCE):
    reviewer, _adapter, definition, preflight, binding, binding_review = _setup(monkeypatch)
    result = reviewer.review_adapter(
        adapter_document or definition,
        preflight,
        binding,
        binding_review,
        adapter_file_sha256="a" * 64,
        adapter_source_path=source,
        preflight_file_sha256="1" * 64,
        binding_file_sha256="2" * 64,
        binding_review_file_sha256="3" * 64,
        proof_source_file_sha256="4" * 64,
        binding_source_file_sha256="5" * 64,
    )
    return reviewer, result, definition


def test_arm265_review_accepts_exact_zero_authority_composition(monkeypatch):
    _module, result, _definition = _review(monkeypatch)
    assert result["status"] == "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
    assert result["definition_reproduced"] is True
    assert result["source_call_surface_reviewed"] is True
    assert result["non_isaac_runtime_composition_verified"] is True
    assert result["recursive_refinement_verified"] is True
    assert result["runtime_integration_admitted"] is True
    assert result["launch_admitted"] is False
    assert result["next_required_stage"] == "PREPARE_ZERO_AUTHORITY_NOMINAL_ROUTE_RUNTIME_COMPOSITION"


def test_arm265_review_rejects_self_consistent_artifact_substitution(monkeypatch):
    reviewer, _adapter, definition, _preflight, _binding, _binding_review = _setup(monkeypatch)
    changed = dict(definition)
    changed["maximum_subdivision_depth"] = 11
    unsigned = dict(changed)
    unsigned.pop("adapter_sha256")
    changed["adapter_sha256"] = reviewer._sha(unsigned)
    with pytest.raises(reviewer.NativeClearanceAdapterReviewError, match="boundary changed"):
        _review(monkeypatch, adapter_document=changed)


def test_arm265_review_rejects_source_drift(monkeypatch, tmp_path):
    changed = tmp_path / SOURCE.name
    changed.write_bytes(SOURCE.read_bytes() + b"\n# drift\n")
    reviewer, _adapter, _definition, _preflight, _binding, _binding_review = _setup(monkeypatch)
    with pytest.raises(reviewer.NativeClearanceAdapterReviewError, match="boundary changed"):
        _review(monkeypatch, source=changed)


def test_arm265_source_review_rejects_runtime_import():
    module = _load_module("arm265_review_source", REVIEW_SOURCE)
    with pytest.raises(module.NativeClearanceAdapterReviewError, match="forbidden runtime"):
        module._review_source(b"import isaacsim\nclass NativeClearanceRuntimeAdapter: pass\n")


def test_arm265_review_cli_is_zero_authority():
    source = REVIEW_SOURCE.read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "import isaacsim" not in source
    assert "import serial" not in source
