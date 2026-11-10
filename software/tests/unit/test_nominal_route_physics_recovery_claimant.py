from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _module():
    return importlib.import_module("nominal_route_physics_recovery_claimant")


def _bundle(tmp_path: Path):
    module = _module()
    worker_core = {
        "schema": module.WORKER_SCHEMA,
        "worker_id": "arm254-space-nominal-route-physics-worker-001",
        "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
        "source_request_sha256": "1" * 64,
        "source_files_sha256": {"route_plan": "2" * 64},
        "runtime_bindings_sha256": {"robot_usd": "3" * 64},
        "proposed_output_directory": str(tmp_path / "attempt-001"),
        "attempt_ledger": {
            "maximum_attempt_count": 1,
            "attempts_consumed_by_preparation": 0,
            "automatic_retry": False,
        },
        "required_authorization_statement": module.WORKER_AUTHORIZATION,
        "isaac_execution_authorized": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    worker = {**worker_core, "worker_sha256": module._sha(worker_core)}
    recovery_core = {
        "schema": module.RECOVERY_REQUEST_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW",
        "source_request_sha256": "1" * 64,
        "required_authorization_statement": module.EXACT_AUTHORIZATION,
        "old_authorization_reusable": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "claim_only_after_fresh_memory_preflight": True,
            "trajectory_playback": False,
            "hardware_or_physical_authority": False,
        },
        "proposed_output_directory": str(tmp_path / "attempt-001"),
    }
    recovery = {**recovery_core, "request_sha256": module._sha(recovery_core)}
    definition = module.build_claimant_definition(
        recovery,
        worker,
        recovery_request_file_sha256="4" * 64,
        worker_preparation_file_sha256="5" * 64,
        claimant_source_sha256="6" * 64,
        memory_preflight_source_sha256="7" * 64,
        worker_source_sha256="8" * 64,
    )
    review_core = {
        "schema": module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_EXACT_ARM280_ONE_ATTEMPT_AUTHORIZATION",
        "source_claimant_sha256": definition["claimant_sha256"],
        "launch_admitted": True,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    review = {
        **review_core,
        "claimant_review_sha256": module._sha(review_core),
    }
    return module, definition, review


def _pass_memory(module):
    return module.MemorySnapshot(
        total_physical_bytes=128 * 1024**3,
        available_physical_bytes=96 * 1024**3,
        commit_limit_bytes=224 * 1024**3,
        available_commit_bytes=192 * 1024**3,
    )


def test_arm281_definition_is_inert_and_binds_new_worker(tmp_path: Path) -> None:
    module, definition, _ = _bundle(tmp_path)

    assert definition["status"] == "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW"
    assert definition["required_authorization_statement"] == module.EXACT_AUTHORIZATION
    assert (
        definition["worker_review"]["source_worker_sha256"]
        == (definition["source_worker_sha256"])
    )
    assert definition["runtime_execution_admitted"] is False
    assert definition["attempt_claimed"] is False
    assert definition["isaac_started"] is False


def test_arm281_rejects_old_or_inexact_authorization_before_memory(
    tmp_path: Path,
) -> None:
    module, definition, review = _bundle(tmp_path)
    memory_calls = 0

    def collect():
        nonlocal memory_calls
        memory_calls += 1
        return _pass_memory(module)

    claimant = module.RecoveryClaimant(definition, review, memory_collector=collect)
    with pytest.raises(module.RecoveryClaimantError):
        claimant.run(
            authorization_statement=module.WORKER_AUTHORIZATION,
            output_directory=tmp_path / "attempt-001",
            fresh_preflight_receipt=tmp_path / "memory" / "receipt.json",
            current_source_files_sha256={"route_plan": "2" * 64},
            current_runtime_bindings_sha256={"robot_usd": "3" * 64},
            backend=lambda _: {},
        )
    assert memory_calls == 0
    assert not (tmp_path / "attempt-001").exists()


def test_arm281_low_memory_fails_before_attempt_claim(tmp_path: Path) -> None:
    module, definition, review = _bundle(tmp_path)
    low = module.MemorySnapshot(
        total_physical_bytes=128 * 1024**3,
        available_physical_bytes=4 * 1024**3,
        commit_limit_bytes=224 * 1024**3,
        available_commit_bytes=1 * 1024**3,
    )
    claimant = module.RecoveryClaimant(definition, review, memory_collector=lambda: low)

    with pytest.raises(module.RecoveryClaimantError, match="memory"):
        claimant.run(
            authorization_statement=module.EXACT_AUTHORIZATION,
            output_directory=tmp_path / "attempt-001",
            fresh_preflight_receipt=tmp_path / "memory" / "receipt.json",
            current_source_files_sha256={"route_plan": "2" * 64},
            current_runtime_bindings_sha256={"robot_usd": "3" * 64},
            backend=lambda _: {},
        )
    assert not (tmp_path / "attempt-001").exists()
    assert not (tmp_path / "memory" / "receipt.json").exists()


def test_arm281_passes_once_to_worker_after_retaining_memory(tmp_path: Path) -> None:
    module, definition, review = _bundle(tmp_path)
    calls = []

    def worker_runner(preparation, **kwargs):
        calls.append((preparation, kwargs))
        return {"status": "SYNTHETIC_PASS"}

    claimant = module.RecoveryClaimant(
        definition,
        review,
        memory_collector=lambda: _pass_memory(module),
        worker_runner=worker_runner,
    )
    receipt = tmp_path / "memory" / "receipt.json"
    result = claimant.run(
        authorization_statement=module.EXACT_AUTHORIZATION,
        output_directory=tmp_path / "attempt-001",
        fresh_preflight_receipt=receipt,
        current_source_files_sha256={"route_plan": "2" * 64},
        current_runtime_bindings_sha256={"robot_usd": "3" * 64},
        backend=lambda _: {},
    )

    assert result == {"status": "SYNTHETIC_PASS"}
    assert len(calls) == 1
    assert calls[0][1]["authorization_statement"] == module.WORKER_AUTHORIZATION
    assert json.loads(receipt.read_bytes())["status"] == "PASS_MEMORY_PREFLIGHT"

    with pytest.raises(module.RecoveryClaimantError):
        claimant.run(
            authorization_statement=module.EXACT_AUTHORIZATION,
            output_directory=tmp_path / "attempt-001",
            fresh_preflight_receipt=tmp_path / "memory-2" / "receipt.json",
            current_source_files_sha256={"route_plan": "2" * 64},
            current_runtime_bindings_sha256={"robot_usd": "3" * 64},
            backend=lambda _: {},
        )
    assert len(calls) == 1
