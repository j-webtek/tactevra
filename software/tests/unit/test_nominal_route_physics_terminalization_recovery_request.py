from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = (
    ROOT
    / "software/integrations/isaac_sim/"
    "nominal_route_physics_terminalization_recovery_request.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("arm289_recovery_request", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _bundle():
    module = _module()
    request = _signed(
        module,
        {
            "schema": module.SOURCE_REQUEST_SCHEMA,
            "request_id": module.SOURCE_REQUEST_ID,
            "required_authorization_statement": module.SOURCE_AUTHORIZATION,
            "episode_id": "episode-ef340d0ad2740c118d87",
            "target_id": "SPACE",
            "source_worker_request_sha256": "a" * 64,
            "proposed_output_directory": "C:/artifacts/arm284-attempt-001",
            "attempt_contract": {
                "maximum_attempt_count": 1,
                "automatic_retry": False,
                "trajectory_playback": False,
                "hardware_or_physical_authority": False,
            },
        },
        "request_sha256",
    )
    status = {
        "status": "ATTEMPT_CLAIMED_BACKEND_PENDING",
        "attempt_count": 1,
        "automatic_retry": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    eula = {
        "schema": module.EULA_SCHEMA,
        "status": "PASS_EULA_PREFLIGHT",
        "launch_admitted": True,
        "acceptance_observed": True,
        "acceptance_performed_by_preflight": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "automatic_retry": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    memory = {
        "schema": module.MEMORY_SCHEMA,
        "status": "PASS_MEMORY_PREFLIGHT",
        "launch_admitted": True,
        "attempt_claimed": False,
        "isaac_started": False,
        "automatic_retry": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    integration = _signed(
        module,
        {
            "schema": module.INTEGRATION_SCHEMA,
            "integration_id": (
                "arm287-terminalizing-native-runtime-worker-integration-001"
            ),
            "callable_is_single_use": True,
            "automatic_retry": False,
            "launch_admitted": False,
            "attempt_consumed": False,
            "lifecycle": ["terminalize_failure_before_shutdown"],
        },
        "integration_sha256",
    )
    review = _signed(
        module,
        {
            "schema": module.INTEGRATION_REVIEW_SCHEMA,
            "review_id": (
                "arm288-terminalizing-native-runtime-worker-integration-review-001"
            ),
            "status": (
                "ACCEPTED_FOR_SEPARATELY_AUTHORIZED_ONE_ATTEMPT_WORKER_USE"
            ),
            "source_integration_sha256": integration["integration_sha256"],
            "failure_terminalization_precedes_shutdown": True,
            "launch_admitted": False,
            "attempt_consumed": False,
        },
        "integration_review_sha256",
    )
    result = module.build_request(
        request,
        status,
        eula,
        memory,
        integration,
        review,
        source_request_file_sha256="1" * 64,
        consumed_status_file_sha256="2" * 64,
        eula_receipt_file_sha256="3" * 64,
        memory_receipt_file_sha256="4" * 64,
        postmortem_file_sha256="5" * 64,
        kit_log_file_sha256="6" * 64,
        integration_file_sha256="7" * 64,
        integration_review_file_sha256="8" * 64,
        request_source_file_sha256="9" * 64,
        proposed_output_directory="C:/artifacts/arm289-attempt-001",
    )
    return module, request, status, eula, memory, integration, review, result


def test_arm289_builds_inert_terminalized_recovery_request():
    module, _, _, _, _, _, _, result = _bundle()
    assert result["required_authorization_statement"] == module.EXACT_AUTHORIZATION
    assert result["source_worker_request_sha256"] == "a" * 64
    assert result["old_authorization_reusable"] is False
    assert result["attempt_claimed"] is False
    assert result["isaac_started"] is False
    assert result["attempt_contract"]["terminalize_before_simulator_shutdown"] is True
    assert result["remediation"]["failing_lifecycle_phase_retained"] is True
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("status", "status", "FAILED_RETAINED_NO_RETRY"),
        ("status", "automatic_retry", True),
        ("eula", "acceptance_observed", False),
        ("memory", "launch_admitted", False),
        ("integration", "launch_admitted", True),
        ("review", "failure_terminalization_precedes_shutdown", False),
    ],
)
def test_arm289_rejects_evidence_or_authority_drift(target, key, value):
    module, request, status, eula, memory, integration, review, _ = _bundle()
    values = {
        "status": copy.deepcopy(status),
        "eula": copy.deepcopy(eula),
        "memory": copy.deepcopy(memory),
        "integration": copy.deepcopy(integration),
        "review": copy.deepcopy(review),
    }
    changed = values[target]
    changed[key] = value
    if target == "integration":
        changed.pop("integration_sha256")
        changed["integration_sha256"] = module._sha(changed)
        values["review"]["source_integration_sha256"] = changed[
            "integration_sha256"
        ]
        values["review"].pop("integration_review_sha256")
        values["review"]["integration_review_sha256"] = module._sha(
            values["review"]
        )
    elif target == "review":
        changed.pop("integration_review_sha256")
        changed["integration_review_sha256"] = module._sha(changed)

    with pytest.raises(module.TerminalizationRecoveryRequestError):
        module.build_request(
            request,
            values["status"],
            values["eula"],
            values["memory"],
            values["integration"],
            values["review"],
            source_request_file_sha256="1" * 64,
            consumed_status_file_sha256="2" * 64,
            eula_receipt_file_sha256="3" * 64,
            memory_receipt_file_sha256="4" * 64,
            postmortem_file_sha256="5" * 64,
            kit_log_file_sha256="6" * 64,
            integration_file_sha256="7" * 64,
            integration_review_file_sha256="8" * 64,
            request_source_file_sha256="9" * 64,
            proposed_output_directory="C:/artifacts/arm289-attempt-001",
        )


def test_arm289_rejects_arm284_output_reuse():
    module, request, status, eula, memory, integration, review, _ = _bundle()
    with pytest.raises(module.TerminalizationRecoveryRequestError):
        module.build_request(
            request,
            status,
            eula,
            memory,
            integration,
            review,
            source_request_file_sha256="1" * 64,
            consumed_status_file_sha256="2" * 64,
            eula_receipt_file_sha256="3" * 64,
            memory_receipt_file_sha256="4" * 64,
            postmortem_file_sha256="5" * 64,
            kit_log_file_sha256="6" * 64,
            integration_file_sha256="7" * 64,
            integration_review_file_sha256="8" * 64,
            request_source_file_sha256="9" * 64,
            proposed_output_directory=request["proposed_output_directory"],
        )
