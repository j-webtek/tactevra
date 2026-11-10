from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_native_runtime_worker_integration.py"
REVIEW_SOURCE = (
    INTEGRATION / "nominal_route_native_runtime_worker_integration_review.py"
)
CLAIM = {
    "status": "ATTEMPT_CLAIMED_BACKEND_PENDING",
    "attempt_count": 1,
    "automatic_retry": False,
    "hardware_access": False,
    "physical_authority": False,
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _definition(module):
    core = {
        "schema": module.INTEGRATION_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_WORKER_INTEGRATION_REVIEW",
        "worker_remains_sole_attempt_claimant": True,
        "callable_is_single_use": True,
        "automatic_retry": False,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "backend_review": {"review": "pinned"},
    }
    return _signed(module, core, "integration_sha256")


def test_arm274_definition_materializes_exact_review_lineage(monkeypatch):
    module = _load("arm274_definition_test", SOURCE)
    plan = _signed(
        module,
        {
            "schema": module.PLAN_SCHEMA,
            "worker_integration_implemented": False,
            "source_documents_sha256": {
                "worker": module.EXPECTED_WORKER_SHA256,
                "backend": module.EXPECTED_BACKEND_SHA256,
                "factory": module.EXPECTED_FACTORY_SHA256,
            },
        },
        "integration_plan_sha256",
    )
    review = _signed(
        module,
        {
            "schema": module.PLAN_REVIEW_SCHEMA,
            "source_plan_sha256": plan["integration_plan_sha256"],
            "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_WORKER_INTEGRATION_IMPLEMENTATION",
            "worker_review_materialization_required": True,
            "backend_review_materialization_required": True,
        },
        "integration_plan_review_sha256",
    )
    monkeypatch.setattr(module, "EXPECTED_PLAN_SHA256", plan["integration_plan_sha256"])
    monkeypatch.setattr(
        module, "EXPECTED_PLAN_REVIEW_SHA256", review["integration_plan_review_sha256"]
    )
    monkeypatch.setattr(module, "EXPECTED_PLAN_FILE_SHA256", "1" * 64)
    monkeypatch.setattr(module, "EXPECTED_PLAN_REVIEW_FILE_SHA256", "2" * 64)
    monkeypatch.setattr(module, "EXPECTED_PLAN_SOURCE_SHA256", "3" * 64)
    monkeypatch.setattr(module, "EXPECTED_PLAN_REVIEW_SOURCE_SHA256", "4" * 64)
    result = module.build_integration_definition(
        plan,
        review,
        plan_file_sha256="1" * 64,
        plan_review_file_sha256="2" * 64,
        plan_source_sha256="3" * 64,
        plan_review_source_sha256="4" * 64,
        integration_source_sha256="5" * 64,
    )
    assert (
        result["worker_review"]["source_worker_sha256"] == module.EXPECTED_WORKER_SHA256
    )
    assert (
        result["worker_review"]["reviewed_backend_sha256"]
        == module.EXPECTED_BACKEND_SHA256
    )
    assert (
        result["backend_review"]["reviewed_runtime_adapter_sha256"]
        == module.EXPECTED_FACTORY_SHA256
    )
    assert result["runtime_execution_admitted"] is False
    assert result["launch_admitted"] is False


class _Session:
    def __init__(self, events, native):
        self.events = events
        self.native = native

    def start_headless(self):
        self.events.append("start")

    def load_scene(self):
        self.events.append("load")

    def initialize_physics(self):
        self.events.append("initialize")

    def settle_scene(self):
        self.events.append("settle")

    def native_objects(self):
        self.events.append("objects")
        return self.native

    def shutdown(self):
        self.events.append("shutdown")


def _backend(module, events):
    native = {
        "articulation": object(),
        "scene_query": object(),
        "key_view": object(),
        "root_view": object(),
    }
    runtime = object()

    def session_factory():
        events.append("session")
        return _Session(events, native)

    def construct(*args, **kwargs):
        events.append("construct")
        assert kwargs["articulation"] is native["articulation"]
        assert kwargs["scene_query"] is native["scene_query"]
        return runtime

    def execute(*args, **kwargs):
        events.append("execute")
        assert kwargs["runtime"] is runtime
        assert kwargs["backend_review"] == {"review": "pinned"}
        return {"status": "PASS"}

    return module.OneAttemptNativeBackend(
        _definition(module),
        session_factory=session_factory,
        construct_runtime_fn=construct,
        execute_backend_fn=execute,
        backend_definition={},
        route={},
        factory_definition={},
        factory_review={},
        factory_plan={},
        factory_plan_review={},
        documents={},
        solver_kwargs={},
        native_metadata={},
    )


def test_arm274_claim_precedes_exact_once_lifecycle_and_runtime_identity(tmp_path):
    module = _load("arm274_order_test", SOURCE)
    events = []
    backend = _backend(module, events)
    assert events == []
    output = tmp_path / "claimed"
    output.mkdir()
    (output / "status.json").write_text(json.dumps(CLAIM))

    assert backend(output) == {"status": "PASS"}
    assert events == [
        "session",
        "start",
        "load",
        "initialize",
        "settle",
        "objects",
        "construct",
        "execute",
        "shutdown",
    ]
    with pytest.raises(
        module.NativeRuntimeWorkerIntegrationError, match="retry refused"
    ):
        backend(output)
    assert events.count("session") == events.count("execute") == 1


def test_arm274_refuses_session_creation_without_worker_claim(tmp_path):
    module = _load("arm274_claim_test", SOURCE)
    events = []
    backend = _backend(module, events)
    with pytest.raises(module.NativeRuntimeWorkerIntegrationError, match="claim"):
        backend(tmp_path / "absent")
    assert events == []


def test_arm274_shutdown_runs_when_factory_fails(tmp_path):
    module = _load("arm274_failure_test", SOURCE)
    events = []
    native = {
        name: object()
        for name in ("articulation", "scene_query", "key_view", "root_view")
    }

    def factory():
        events.append("session")
        return _Session(events, native)

    def fail(*args, **kwargs):
        events.append("construct")
        raise RuntimeError("factory failed")

    backend = module.OneAttemptNativeBackend(
        _definition(module),
        session_factory=factory,
        construct_runtime_fn=fail,
        execute_backend_fn=lambda *args, **kwargs: pytest.fail("backend must not run"),
        backend_definition={},
        route={},
        factory_definition={},
        factory_review={},
        factory_plan={},
        factory_plan_review={},
        documents={},
        solver_kwargs={},
        native_metadata={},
    )
    output = tmp_path / "claimed"
    output.mkdir()
    (output / "status.json").write_text(json.dumps(CLAIM))
    with pytest.raises(RuntimeError, match="factory failed"):
        backend(output)
    assert events[-2:] == ["construct", "shutdown"]


def test_arm274_static_review_blocks_authority_and_worker_claim():
    reviewer = _load("arm274_reviewer_test", REVIEW_SOURCE)
    result = reviewer._static_review(SOURCE)
    assert result["isaac_and_hardware_imports_absent"] is True
    assert result["worker_attempt_call_absent"] is True
    assert result["joint_and_physics_commands_absent"] is True
