from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = (
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_physics_recovery_attempt_request.py"
    )
    spec = importlib.util.spec_from_file_location("arm280_recovery_request", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle():
    module = _module()
    request_core = {
        "schema": module.SOURCE_REQUEST_SCHEMA,
        "request_id": module.SOURCE_REQUEST_ID,
        "required_authorization_statement": module.SOURCE_AUTHORIZATION,
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "trajectory_playback": False,
            "hardware_or_physical_authority": False,
        },
    }
    request = {**request_core, "request_sha256": module._sha(request_core)}
    failure = {
        "status": "FAILED_RETAINED_NO_RETRY",
        "attempt_count": 1,
        "automatic_retry": False,
        "error_type": "NativeIsaacRuntimeAbort",
        "error_message": (
            "CreateFileMapping failed: The paging file is too small for this "
            "operation to complete."
        ),
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
        "checks": {
            "available_commit": True,
            "available_physical": True,
            "commit_utilization": True,
        },
        "thresholds": {
            "minimum_available_commit_bytes": 32 * 1024**3,
            "minimum_available_physical_bytes": 16 * 1024**3,
            "maximum_commit_utilization": 0.9,
        },
    }
    result = module.build_request(
        request,
        failure,
        memory,
        source_request_file_sha256="1" * 64,
        failure_status_file_sha256="2" * 64,
        memory_preflight_file_sha256="3" * 64,
        proposed_output_directory="C:/IsaacSim/artifacts/issue190/arm280-attempt-001",
    )
    return module, request, failure, memory, result


def test_arm280_builds_nonexecuting_recovery_request() -> None:
    module, _, _, _, result = _bundle()

    assert result["status"] == "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW"
    assert result["required_authorization_statement"] == module.EXACT_AUTHORIZATION
    assert result["old_authorization_reusable"] is False
    assert result["attempt_contract"]["maximum_attempt_count"] == 1
    assert result["attempt_contract"]["automatic_retry"] is False
    assert result["attempt_claimed"] is False
    assert result["isaac_started"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("failure", "status", "ATTEMPT_CLAIMED_BACKEND_PENDING"),
        ("failure", "automatic_retry", True),
        ("memory", "launch_admitted", False),
        ("memory", "attempt_claimed", True),
        ("memory", "hardware_access", True),
    ],
)
def test_arm280_rejects_drift(target: str, key: str, value: object) -> None:
    module, request, failure, memory, _ = _bundle()
    changed_failure = copy.deepcopy(failure)
    changed_memory = copy.deepcopy(memory)
    if target == "failure":
        changed_failure[key] = value
    else:
        changed_memory[key] = value

    with pytest.raises(module.RecoveryAttemptRequestError):
        module.build_request(
            request,
            changed_failure,
            changed_memory,
            source_request_file_sha256="1" * 64,
            failure_status_file_sha256="2" * 64,
            memory_preflight_file_sha256="3" * 64,
            proposed_output_directory=(
                "C:/IsaacSim/artifacts/issue190/arm280-attempt-001"
            ),
        )


def test_arm280_rejects_old_request_authorization_reuse() -> None:
    module, request, failure, memory, _ = _bundle()
    changed = copy.deepcopy(request)
    changed["required_authorization_statement"] = module.EXACT_AUTHORIZATION
    changed.pop("request_sha256")
    changed["request_sha256"] = module._sha(changed)

    with pytest.raises(module.RecoveryAttemptRequestError):
        module.build_request(
            changed,
            failure,
            memory,
            source_request_file_sha256="1" * 64,
            failure_status_file_sha256="2" * 64,
            memory_preflight_file_sha256="3" * 64,
            proposed_output_directory=(
                "C:/IsaacSim/artifacts/issue190/arm280-attempt-001"
            ),
        )
