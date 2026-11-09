from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_native_runtime_worker_integration_plan.py"
REVIEW_SOURCE = (
    INTEGRATION / "nominal_route_native_runtime_worker_integration_plan_review.py"
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _documents(module):
    empty_authority = {
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    worker = _signed(
        module,
        {
            "schema": module.WORKER_SCHEMA,
            "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
            "attempt_ledger": {
                "maximum_attempt_count": 1,
                "automatic_retry": False,
                "attempts_consumed_by_preparation": 0,
            },
            "isaac_started": False,
            **empty_authority,
        },
        "worker_sha256",
    )
    backend = _signed(
        module,
        {
            "schema": module.BACKEND_SCHEMA,
            "status": "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW",
            "source_worker_sha256": worker["worker_sha256"],
            "isaac_runtime_adapter_implemented_by_core": False,
            "isaac_execution_authorized": False,
            **empty_authority,
        },
        "backend_sha256",
    )
    factory = _signed(
        module,
        {
            "schema": module.FACTORY_SCHEMA,
            "status": "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_FACTORY_REVIEW",
            "runtime_execution_admitted": False,
            "launch_admitted": False,
            **empty_authority,
        },
        "factory_sha256",
    )
    review = _signed(
        module,
        {
            "schema": module.FACTORY_REVIEW_SCHEMA,
            "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_USE",
            "source_factory_sha256": factory["factory_sha256"],
            "runtime_construction_admitted": True,
            "backend_execution_admitted": False,
            "runtime_execution_admitted": False,
            "launch_admitted": False,
            **empty_authority,
        },
        "factory_review_sha256",
    )
    documents = {
        "worker": worker,
        "backend": backend,
        "factory": factory,
        "factory_review": review,
    }
    for index, (name, document) in enumerate(documents.items(), start=1):
        module.EXPECTED[name] = {
            "canonical": document[
                {
                    "worker": "worker_sha256",
                    "backend": "backend_sha256",
                    "factory": "factory_sha256",
                    "factory_review": "factory_review_sha256",
                }[name]
            ],
            "file": str(index) * 64,
            "source": str(index + 4) * 64,
        }
    return documents


def _build(module, documents):
    return module.build_worker_integration_plan(
        documents["worker"],
        documents["backend"],
        documents["factory"],
        documents["factory_review"],
        files_sha256={name: value["file"] for name, value in module.EXPECTED.items()},
        sources_sha256={
            name: value["source"] for name, value in module.EXPECTED.items()
        },
        plan_source_sha256="9" * 64,
    )


def test_arm273_plan_pins_claim_factory_backend_and_shutdown_order():
    module = _load("arm273_plan_test", SOURCE)
    result = _build(module, _documents(module))
    order = result["required_future_order"]
    assert order.index("enter_arm254_run_one_attempt_as_sole_directory_claimant") < (
        order.index("after_claim_start_one_headless_isaac_runtime")
    )
    assert order.index("invoke_arm272_factory_once_without_protocol_calls") < (
        order.index("invoke_arm255_backend_once_with_factory_runtime")
    )
    assert order.index("write_all_outputs_before_simulator_shutdown") < order.index(
        "shutdown_once_and_retain_terminal_status_without_retry"
    )
    assert result["attempt_consumed"] is False
    assert result["backend_execution_admitted"] is False


def test_arm273_plan_rejects_backend_execution_authority():
    module = _load("arm273_boundary_test", SOURCE)
    documents = _documents(module)
    core = dict(documents["backend"])
    core.pop("backend_sha256")
    core["isaac_execution_authorized"] = True
    documents["backend"] = _signed(module, core, "backend_sha256")
    module.EXPECTED["backend"]["canonical"] = documents["backend"]["backend_sha256"]
    with pytest.raises(
        module.NativeRuntimeWorkerIntegrationPlanError,
        match="integration lineage changed",
    ):
        _build(module, documents)


def test_arm273_review_verifies_static_plan_and_exact_call_surfaces():
    reviewer = _load("arm273_reviewer_test", REVIEW_SOURCE)
    static = reviewer._static_plan_review(SOURCE)
    surfaces = reviewer._review_call_surfaces(
        {
            "worker": INTEGRATION / "nominal_route_physics_worker.py",
            "backend": INTEGRATION / "nominal_route_physics_backend.py",
            "factory": INTEGRATION / "nominal_route_native_runtime_factory.py",
            "factory_review": (
                INTEGRATION / "nominal_route_native_runtime_factory_review.py"
            ),
        }
    )
    assert static["worker_backend_and_factory_calls_absent"] is True
    assert surfaces["run_one_attempt"][-1] == "backend"
    assert surfaces["execute_backend"][-1] == "runtime"
    assert surfaces["construct_runtime"][-1] == "native_metadata"
