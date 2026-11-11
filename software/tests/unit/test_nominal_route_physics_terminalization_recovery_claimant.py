from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_physics_terminalization_recovery_claimant.py"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _module():
    name = "arm290_terminalization_claimant"
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _bundle():
    module = _module()
    output_directory = str(Path("C:/artifacts/arm289-attempt-001"))
    integration_source = "7" * 64
    review_source = "8" * 64
    integration = _signed(
        module,
        {
            "schema": module.INTEGRATION_SCHEMA,
            "integration_id": (
                "arm287-terminalizing-native-runtime-worker-integration-001"
            ),
            "source_files_sha256": {
                "arm274_integration_source": integration_source
            },
            "lifecycle": ["terminalize_failure_before_shutdown"],
            "launch_admitted": False,
        },
        "integration_sha256",
    )
    review = _signed(
        module,
        {
            "schema": module.INTEGRATION_REVIEW_SCHEMA,
            "source_integration_sha256": integration["integration_sha256"],
            "source_integration_source_sha256": integration_source,
            "review_source_sha256": review_source,
            "failure_terminalization_precedes_shutdown": True,
            "launch_admitted": False,
        },
        "integration_review_sha256",
    )
    worker = _signed(
        module,
        {
            "schema": module.WORKER_SCHEMA,
            "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
            "source_request_sha256": "a" * 64,
            "proposed_output_directory": output_directory,
            "required_authorization_statement": module.WORKER_AUTHORIZATION,
            "attempt_ledger": {
                "maximum_attempt_count": 1,
                "attempts_consumed_by_preparation": 0,
                "automatic_retry": False,
            },
            "isaac_execution_authorized": False,
            "isaac_started": False,
            "hardware_access": False,
            "physical_authority": False,
        },
        "worker_sha256",
    )
    request = _signed(
        module,
        {
            "schema": module.RECOVERY_REQUEST_SCHEMA,
            "status": (
                "READY_FOR_INDEPENDENT_TERMINALIZED_RECOVERY_CLAIMANT_REVIEW"
            ),
            "required_authorization_statement": module.EXACT_AUTHORIZATION,
            "old_authorization_reusable": False,
            "attempt_claimed": False,
            "isaac_started": False,
            "request_source_file_sha256": "6" * 64,
            "source_worker_request_sha256": "a" * 64,
            "source_integration_sha256": integration["integration_sha256"],
            "source_integration_file_sha256": "3" * 64,
            "source_integration_review_sha256": review[
                "integration_review_sha256"
            ],
            "source_integration_review_file_sha256": "4" * 64,
            "proposed_output_directory": output_directory,
            "attempt_contract": {
                "maximum_attempt_count": 1,
                "automatic_retry": False,
                "claim_only_after_fresh_memory_preflight": True,
                "claim_only_after_fresh_eula_preflight": True,
                "terminalize_before_simulator_shutdown": True,
                "trajectory_playback": False,
                "hardware_or_physical_authority": False,
            },
        },
        "request_sha256",
    )
    kwargs = {
        "recovery_request_file_sha256": "1" * 64,
        "worker_preparation_file_sha256": "2" * 64,
        "integration_file_sha256": "3" * 64,
        "integration_review_file_sha256": "4" * 64,
        "claimant_source_sha256": "5" * 64,
        "recovery_request_source_sha256": "6" * 64,
        "integration_source_sha256": integration_source,
        "integration_review_source_sha256": review_source,
        "memory_preflight_source_sha256": "9" * 64,
        "eula_preflight_source_sha256": "b" * 64,
        "worker_source_sha256": "c" * 64,
    }
    definition = module.build_claimant_definition(
        request, worker, integration, review, **kwargs
    )
    return module, request, worker, integration, review, kwargs, definition


def test_arm290_builds_inert_single_use_claimant():
    module, _, _, _, _, _, definition = _bundle()
    assert definition["required_authorization_statement"] == module.EXACT_AUTHORIZATION
    assert definition["callable_is_single_use_after_admission"] is True
    assert definition["failure_terminalization"][
        "required_before_simulator_shutdown"
    ] is True
    assert definition["attempt_claimed"] is False
    assert definition["isaac_started"] is False
    assert definition["hardware_access"] is False
    assert definition["physical_authority"] is False


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("request", "old_authorization_reusable", True),
        ("request_attempt", "terminalize_before_simulator_shutdown", False),
        ("worker", "isaac_started", True),
        ("integration", "launch_admitted", True),
        ("review", "failure_terminalization_precedes_shutdown", False),
    ],
)
def test_arm290_rejects_lineage_or_authority_drift(target, key, value):
    module, request, worker, integration, review, kwargs, _ = _bundle()
    request = copy.deepcopy(request)
    worker = copy.deepcopy(worker)
    integration = copy.deepcopy(integration)
    review = copy.deepcopy(review)
    if target == "request_attempt":
        request["attempt_contract"][key] = value
        request.pop("request_sha256")
        request["request_sha256"] = module._sha(request)
    elif target == "request":
        request[key] = value
        request.pop("request_sha256")
        request["request_sha256"] = module._sha(request)
    elif target == "worker":
        worker[key] = value
        worker.pop("worker_sha256")
        worker["worker_sha256"] = module._sha(worker)
    elif target == "integration":
        integration[key] = value
        integration.pop("integration_sha256")
        integration["integration_sha256"] = module._sha(integration)
        request["source_integration_sha256"] = integration["integration_sha256"]
        request.pop("request_sha256")
        request["request_sha256"] = module._sha(request)
        review["source_integration_sha256"] = integration["integration_sha256"]
        review.pop("integration_review_sha256")
        review["integration_review_sha256"] = module._sha(review)
    else:
        review[key] = value
        review.pop("integration_review_sha256")
        review["integration_review_sha256"] = module._sha(review)
        request["source_integration_review_sha256"] = review[
            "integration_review_sha256"
        ]
        request.pop("request_sha256")
        request["request_sha256"] = module._sha(request)

    with pytest.raises(module.TerminalizationRecoveryClaimantError):
        module.build_claimant_definition(
            request, worker, integration, review, **kwargs
        )


def _review(module, definition):
    core = {
        "schema": module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_EXACT_ARM289_ONE_ATTEMPT_AUTHORIZATION",
        "source_claimant_sha256": definition["claimant_sha256"],
        "launch_admitted": True,
        "failure_terminalization_precedes_shutdown": True,
        **module._zero_authority(),
    }
    return _signed(module, core, "claimant_review_sha256")


def _passing_eula():
    return {
        "status": "PASS_EULA_PREFLIGHT",
        "launch_admitted": True,
        "acceptance_observed": True,
        "acceptance_performed_by_preflight": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def _passing_memory():
    return {
        "status": "PASS_MEMORY_PREFLIGHT",
        "launch_admitted": True,
        "attempt_claimed": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def test_arm290_collects_and_retains_gates_before_single_delegation(tmp_path):
    module, _, _, _, _, _, definition = _bundle()
    events = []

    def worker(*args, **kwargs):
        events.append("worker")
        assert eula_path.exists() and memory_path.exists()
        assert kwargs["authorization_statement"] == module.WORKER_AUTHORIZATION
        return {"status": "delegated"}

    claimant = module.TerminalizationRecoveryClaimant(
        definition,
        _review(module, definition),
        eula_collector=lambda: events.append("eula_collect") or {},
        eula_evaluator=lambda _: events.append("eula_evaluate") or _passing_eula(),
        memory_collector=lambda: events.append("memory_collect") or object(),
        memory_evaluator=lambda _: events.append("memory_evaluate")
        or _passing_memory(),
        worker_runner=worker,
    )
    output = Path(definition["proposed_output_directory"])
    eula_path = tmp_path / "eula" / "receipt.json"
    memory_path = tmp_path / "memory" / "receipt.json"
    assert claimant.run(
        authorization_statement=module.EXACT_AUTHORIZATION,
        output_directory=output,
        fresh_eula_receipt=eula_path,
        fresh_memory_receipt=memory_path,
        current_source_files_sha256={},
        current_runtime_bindings_sha256={},
        backend=lambda _: {},
    ) == {"status": "delegated"}
    assert events == [
        "eula_collect",
        "eula_evaluate",
        "memory_collect",
        "memory_evaluate",
        "worker",
    ]
    assert json.loads(eula_path.read_text())["status"] == "PASS_EULA_PREFLIGHT"
    with pytest.raises(module.TerminalizationRecoveryClaimantError):
        claimant.run(
            authorization_statement=module.EXACT_AUTHORIZATION,
            output_directory=output,
            fresh_eula_receipt=tmp_path / "eula-2.json",
            fresh_memory_receipt=tmp_path / "memory-2.json",
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )


def test_arm290_rejects_inexact_authority_before_gate_collection(tmp_path):
    module, _, _, _, _, _, definition = _bundle()
    events = []
    claimant = module.TerminalizationRecoveryClaimant(
        definition,
        _review(module, definition),
        eula_collector=lambda: events.append("gate") or {},
        worker_runner=lambda *args, **kwargs: pytest.fail("worker must not run"),
    )
    with pytest.raises(module.TerminalizationRecoveryClaimantError):
        claimant.run(
            authorization_statement="wrong",
            output_directory=Path(definition["proposed_output_directory"]),
            fresh_eula_receipt=tmp_path / "eula.json",
            fresh_memory_receipt=tmp_path / "memory.json",
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )
    assert events == []


@pytest.mark.parametrize("target", ["definition", "review"])
def test_arm290_runtime_rejects_resigned_hardware_authority(target):
    module, _, _, _, _, _, definition = _bundle()
    definition = copy.deepcopy(definition)
    review = _review(module, definition)
    if target == "definition":
        definition["hardware_access"] = True
        definition.pop("claimant_sha256")
        definition["claimant_sha256"] = module._sha(definition)
        review = _review(module, definition)
    else:
        review["physical_authority"] = True
        review.pop("claimant_review_sha256")
        review["claimant_review_sha256"] = module._sha(review)

    with pytest.raises(module.TerminalizationRecoveryClaimantError):
        module.TerminalizationRecoveryClaimant(definition, review)
