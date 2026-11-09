from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_root_drift_adapter.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_root_drift_adapter_review.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _authority():
    return {
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }


def _sources(module):
    backend_core = {
        "schema": module.BACKEND_SCHEMA,
        "runtime_protocol": {"root_drift": "ONE_DETERMINATE_TERMINAL_OBSERVATION"},
    }
    backend = {**backend_core, "backend_sha256": module._sha(backend_core)}
    readiness_core = {"schema": module.READINESS_SCHEMA, **_authority()}
    readiness = {**readiness_core, "readiness_sha256": module._sha(readiness_core)}
    metrics_core = {"schema": module.METRICS_ADAPTER_SCHEMA, **_authority()}
    metrics = {**metrics_core, "adapter_sha256": module._sha(metrics_core)}
    review_core = {
        "schema": module.METRICS_REVIEW_SCHEMA,
        "source_adapter_sha256": metrics["adapter_sha256"],
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "next_required_stage": "IMPLEMENT_AND_REVIEW_ROOT_DRIFT_ADAPTER",
        **_authority(),
    }
    review = {**review_core, "adapter_review_sha256": module._sha(review_core)}
    module.EXPECTED_READINESS_SHA256 = readiness["readiness_sha256"]
    module.EXPECTED_BACKEND_SHA256 = backend["backend_sha256"]
    module.EXPECTED_METRICS_ADAPTER_SHA256 = metrics["adapter_sha256"]
    module.EXPECTED_METRICS_REVIEW_SHA256 = review["adapter_review_sha256"]
    module.EXPECTED_READINESS_FILE_SHA256 = "1" * 64
    module.EXPECTED_BACKEND_FILE_SHA256 = "2" * 64
    module.EXPECTED_METRICS_ADAPTER_FILE_SHA256 = "3" * 64
    module.EXPECTED_METRICS_REVIEW_FILE_SHA256 = "4" * 64
    module.EXPECTED_MECHANICS_SOURCE_SHA256 = "5" * 64
    return readiness, backend, metrics, review


def _definition(module):
    sources = _sources(module)
    result = module.build_adapter_definition(
        *sources,
        readiness_file_sha256="1" * 64,
        backend_file_sha256="2" * 64,
        metrics_adapter_file_sha256="3" * 64,
        metrics_review_file_sha256="4" * 64,
        mechanics_source_file_sha256="5" * 64,
        adapter_source_file_sha256=module._file_sha(SOURCE),
    )
    return result, sources


class _Tensor:
    def __init__(self, value):
        self.value = value

    def numpy(self):
        return self

    def tolist(self):
        return self.value


class _View:
    def __init__(self, position, orientation=(1, 0, 0, 0)):
        self.position = position
        self.orientation = orientation
        self.reads = 0

    def get_world_poses(self):
        self.reads += 1
        return _Tensor([self.position]), _Tensor([self.orientation])


def _review(module, definition):
    core = {
        "schema": module.ADAPTER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": definition["adapter_sha256"],
        "runtime_integration_admitted": True,
    }
    return {**core, "adapter_review_sha256": module._sha(core)}


def _runtime(module, definition, view):
    return module.RootDriftRuntimeAdapter(
        definition,
        adapter_review=_review(module, definition),
        root_view=view,
        expected_position_stage=[0, 0, 0],
        expected_quaternion_wxyz=[1, 0, 0, 0],
    )


def test_arm269_definition_pins_terminal_read_only_contract():
    module = _load("arm269_definition", SOURCE)
    result, _ = _definition(module)
    assert result["backend_method"] == "root_drift"
    assert result["sample_count"] == 1
    assert result["translation_tolerance_mm"] == 0.05
    assert result["orientation_tolerance_deg"] == 0.1
    assert result["joint_submission_required"] is False


def test_arm269_runtime_reads_once_and_is_quaternion_sign_invariant():
    module = _load("arm269_runtime", SOURCE)
    definition, _ = _definition(module)
    view = _View([0.00002, 0, 0], (-1, 0, 0, 0))
    result = _runtime(module, definition, view).root_drift()
    assert view.reads == 1
    assert result == {
        "determinate": True,
        "translation_mm": pytest.approx(0.02),
        "rotation_deg": 0.0,
    }


def test_arm269_runtime_fails_closed_outside_translation_tolerance():
    module = _load("arm269_tolerance", SOURCE)
    definition, _ = _definition(module)
    with pytest.raises(module.RootDriftAdapterError, match="exceeds"):
        _runtime(module, definition, _View([0.000051, 0, 0])).root_drift()


def test_arm269_runtime_fails_closed_on_bad_native_shape():
    module = _load("arm269_shape", SOURCE)
    definition, _ = _definition(module)
    with pytest.raises(module.RootDriftAdapterError, match="must contain 3"):
        _runtime(module, definition, _View([0, 0])).root_drift()


def test_arm269_review_reproduces_and_accepts_composition(monkeypatch):
    adapter = _load("arm269_review_adapter", SOURCE)
    definition, sources = _definition(adapter)
    reviewer = _load("arm269_reviewer", REVIEW_SOURCE)
    reviewer.EXPECTED_ADAPTER_SHA256 = definition["adapter_sha256"]
    reviewer.EXPECTED_ADAPTER_FILE_SHA256 = "a" * 64
    reviewer.EXPECTED_ADAPTER_SOURCE_SHA256 = adapter._file_sha(SOURCE)
    monkeypatch.setattr(reviewer, "_import_adapter", lambda path: adapter)
    result = reviewer.review_adapter(
        definition,
        *sources,
        adapter_file_sha256="a" * 64,
        adapter_source_path=SOURCE,
        readiness_file_sha256="1" * 64,
        backend_file_sha256="2" * 64,
        metrics_adapter_file_sha256="3" * 64,
        metrics_review_file_sha256="4" * 64,
        mechanics_source_file_sha256="5" * 64,
    )
    assert result["status"] == "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
    assert result["out_of_tolerance_failure_verified"] is True
    assert (
        result["next_required_stage"]
        == "PREPARE_AND_REVIEW_COMPLETE_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
    )


def test_arm269_sources_are_zero_authority():
    adapter = SOURCE.read_text(encoding="utf-8")
    review = REVIEW_SOURCE.read_text(encoding="utf-8")
    assert "SimulationApp(" not in adapter
    assert "set_dof_positions" not in adapter
    assert "set_dof_position_targets" not in adapter
    assert "import serial" not in adapter
    assert not any(
        line.strip() in {"import isaacsim", "import serial"}
        or line.strip().startswith("from isaacsim")
        for line in review.splitlines()
    )
