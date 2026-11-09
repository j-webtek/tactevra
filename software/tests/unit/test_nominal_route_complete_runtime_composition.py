from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_complete_runtime_composition.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_complete_runtime_composition_review.py"


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


def _inputs(module):
    backend_core = {
        "schema": module.BACKEND_SCHEMA,
        "runtime_protocol": {
            "canonical_ik": "ONE_ACCEPTED_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "continuous_clearance": "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING",
            "tool_key_metrics": "ONE_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "root_drift": "ONE_DETERMINATE_TERMINAL_OBSERVATION",
            "all_outputs_before_shutdown": True,
        },
        "isaac_execution_authorized": False,
        "trajectory_playback_authorized": False,
        "native_replay_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    backend = {**backend_core, "backend_sha256": module._sha(backend_core)}
    module.EXPECTED_BACKEND_SHA256 = backend["backend_sha256"]
    module.EXPECTED_BACKEND_FILE_SHA256 = "0" * 64
    documents = {}
    files = {}
    sources = {}
    for index, (name, expected) in enumerate(module.COMPONENTS.items(), 1):
        adapter_core = {"schema": expected["adapter_schema"], **_authority()}
        adapter = {**adapter_core, "adapter_sha256": module._sha(adapter_core)}
        review_core = {
            "schema": expected["review_schema"],
            "source_adapter_sha256": adapter["adapter_sha256"],
            "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
            "runtime_integration_admitted": True,
            **_authority(),
        }
        review = {**review_core, "adapter_review_sha256": module._sha(review_core)}
        expected["adapter_hash"] = adapter["adapter_sha256"]
        expected["review_hash"] = review["adapter_review_sha256"]
        expected["adapter_file"] = str(index) * 64
        expected["review_file"] = chr(96 + index) * 64
        expected["adapter_source"] = chr(101 + index) * 64
        expected["review_source"] = chr(105 + index) * 64
        documents[name] = (adapter, review)
        files[name] = {
            "adapter": expected["adapter_file"],
            "review": expected["review_file"],
        }
        sources[name] = {
            "adapter": expected["adapter_source"],
            "review": expected["review_source"],
        }
    return backend, documents, files, sources


def _definition(module):
    backend, documents, files, sources = _inputs(module)
    result = module.build_composition_definition(
        backend,
        documents,
        backend_file_sha256="0" * 64,
        component_file_sha256=files,
        component_source_sha256=sources,
        composition_source_file_sha256=module._file_sha(SOURCE),
    )
    return result, (backend, documents, files, sources)


class _Recorder:
    def __init__(self, result):
        self.result = result
        self.calls = []


def _component(class_name, method_name, result):
    def delegated(self, **kwargs):
        self.recorder.calls.append(kwargs)
        return self.recorder.result

    component_type = type(class_name, (), {method_name: delegated})
    instance = component_type()
    instance.recorder = _Recorder(result)
    return instance


def _components(module):
    results = {
        "clearance": {"continuous": True},
        "ik": {"accepted": True},
        "metrics": {"determinate": True},
        "drift": {"translation_mm": 0.0},
    }
    return {
        name: _component(expected["class"], expected["method"], results[name])
        for name, expected in module.COMPONENTS.items()
    }


def _accepted_review(module, definition):
    core = {
        "schema": module.COMPOSITION_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION",
        "source_composition_sha256": definition["composition_sha256"],
        "runtime_construction_admitted": True,
    }
    return {**core, "composition_review_sha256": module._sha(core)}


def test_arm270_definition_pins_all_four_reviewed_methods():
    module = _load("arm270_definition", SOURCE)
    result, _ = _definition(module)
    assert result["bound_methods"] == [
        "regenerate_row",
        "check_continuous_clearance",
        "measure_tool_key",
        "root_drift",
    ]
    assert set(result["source_components"]) == {"clearance", "ik", "metrics", "drift"}
    assert result["delegation_only"] is True
    assert result["runtime_integration_admitted"] is False


def test_arm270_runtime_delegates_all_methods_once():
    module = _load("arm270_runtime", SOURCE)
    definition, _ = _definition(module)
    components = _components(module)
    runtime = module.CompleteRuntimeComposition(
        definition,
        composition_review=_accepted_review(module, definition),
        **components,
    )
    assert runtime.regenerate_row(
        source_row={"sequence": 654}, previous_joint_targets_rad=[0] * 6
    ) == {"accepted": True}
    assert runtime.check_continuous_clearance(
        start_sequence=653,
        end_sequence=654,
        start_joint_targets_rad=[0] * 6,
        end_joint_targets_rad=[0.01] * 6,
    ) == {"continuous": True}
    assert runtime.measure_tool_key(
        sequence=654, joint_targets_rad=[0.01] * 6, phase="TRANSIT"
    ) == {"determinate": True}
    assert runtime.root_drift() == {"translation_mm": 0.0}
    assert all(len(component.recorder.calls) == 1 for component in components.values())


def test_arm270_runtime_rejects_unreviewed_component_type():
    module = _load("arm270_type", SOURCE)
    definition, _ = _definition(module)
    components = _components(module)
    components["drift"] = _component("UnreviewedDrift", "root_drift", {})
    with pytest.raises(
        module.CompleteRuntimeCompositionError, match="drift runtime component"
    ):
        module.CompleteRuntimeComposition(
            definition,
            composition_review=_accepted_review(module, definition),
            **components,
        )


def test_arm270_definition_rejects_missing_component():
    module = _load("arm270_missing", SOURCE)
    backend, documents, files, sources = _inputs(module)
    documents.pop("drift")
    with pytest.raises(
        module.CompleteRuntimeCompositionError, match="backend composition"
    ):
        module.build_composition_definition(
            backend,
            documents,
            backend_file_sha256="0" * 64,
            component_file_sha256=files,
            component_source_sha256=sources,
            composition_source_file_sha256=module._file_sha(SOURCE),
        )


def test_arm270_review_reproduces_and_accepts_delegation(monkeypatch):
    composition = _load("arm270_review_composition", SOURCE)
    definition, inputs = _definition(composition)
    backend, documents, files, sources = inputs
    reviewer = _load("arm270_reviewer", REVIEW_SOURCE)
    reviewer.EXPECTED_COMPOSITION_SHA256 = definition["composition_sha256"]
    reviewer.EXPECTED_COMPOSITION_FILE_SHA256 = "z" * 64
    reviewer.EXPECTED_COMPOSITION_SOURCE_SHA256 = composition._file_sha(SOURCE)
    monkeypatch.setattr(reviewer, "_import_composition", lambda path: composition)
    result = reviewer.review_composition(
        definition,
        backend,
        documents,
        composition_file_sha256="z" * 64,
        composition_source_path=SOURCE,
        backend_file_sha256="0" * 64,
        component_file_sha256=files,
        component_source_sha256=sources,
    )
    assert result["status"] == "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION"
    assert result["complete_protocol_delegation_verified"] is True
    assert result["backend_execution_admitted"] is False


def test_arm270_sources_are_zero_authority():
    source = SOURCE.read_text(encoding="utf-8")
    review = REVIEW_SOURCE.read_text(encoding="utf-8")
    assert "SimulationApp(" not in source
    assert "execute_backend(" not in source
    assert "set_dof_position_targets" not in source
    assert not any(
        line.strip() in {"import isaacsim", "import serial"}
        or line.strip().startswith("from isaacsim")
        for line in review.splitlines()
    )
