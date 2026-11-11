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
    return importlib.import_module("nominal_route_physics_eula_recovery_claimant")


def _bundle(tmp_path: Path):
    module = _module()
    worker_core = {
        "schema": module.WORKER_SCHEMA,
        "worker_id": "arm284-space-nominal-route-physics-worker-001",
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
        "status": "READY_FOR_INDEPENDENT_EULA_RECOVERY_CLAIMANT_REVIEW",
        "source_worker_request_sha256": "1" * 64,
        "required_authorization_statement": module.EXACT_AUTHORIZATION,
        "old_authorization_reusable": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "claim_only_after_fresh_memory_preflight": True,
            "claim_only_after_fresh_eula_preflight": True,
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
        eula_preflight_source_sha256="8" * 64,
        worker_source_sha256="9" * 64,
    )
    review_core = {
        "schema": module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_EXACT_ARM284_ONE_ATTEMPT_AUTHORIZATION",
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
    review = {**review_core, "claimant_review_sha256": module._sha(review_core)}
    return module, definition, review


def _pass_memory(module):
    return module.MemorySnapshot(
        total_physical_bytes=128 * 1024**3,
        available_physical_bytes=96 * 1024**3,
        commit_limit_bytes=224 * 1024**3,
        available_commit_bytes=192 * 1024**3,
    )


def _run(claimant, module, tmp_path: Path, **overrides):
    values = {
        "authorization_statement": module.EXACT_AUTHORIZATION,
        "output_directory": tmp_path / "attempt-001",
        "fresh_eula_receipt": tmp_path / "eula" / "receipt.json",
        "fresh_memory_receipt": tmp_path / "memory" / "receipt.json",
        "current_source_files_sha256": {"route_plan": "2" * 64},
        "current_runtime_bindings_sha256": {"robot_usd": "3" * 64},
        "backend": lambda _: {},
    }
    values.update(overrides)
    return claimant.run(**values)


def test_arm285_definition_is_inert_and_binds_both_gates(tmp_path: Path) -> None:
    module, definition, _ = _bundle(tmp_path)

    assert definition["status"] == "READY_FOR_INDEPENDENT_EULA_RECOVERY_CLAIMANT_REVIEW"
    assert definition["required_authorization_statement"] == module.EXACT_AUTHORIZATION
    assert definition["fresh_eula_preflight"]["required_before_attempt_claim"] is True
    assert definition["fresh_memory_preflight"]["required_before_attempt_claim"] is True
    assert definition["runtime_execution_admitted"] is False
    assert definition["attempt_claimed"] is False
    assert definition["isaac_started"] is False


def test_arm285_rejects_old_authorization_before_gate_collection(tmp_path: Path) -> None:
    module, definition, review = _bundle(tmp_path)
    calls: list[str] = []
    claimant = module.RecoveryClaimant(
        definition,
        review,
        eula_collector=lambda: calls.append("eula") or {},
        memory_collector=lambda: calls.append("memory") or _pass_memory(module),
    )

    with pytest.raises(module.EulaRecoveryClaimantError):
        _run(
            claimant,
            module,
            tmp_path,
            authorization_statement=module.WORKER_AUTHORIZATION,
        )
    assert calls == []


def test_arm285_eula_failure_precedes_memory_and_worker(tmp_path: Path) -> None:
    module, definition, review = _bundle(tmp_path)
    calls: list[str] = []
    claimant = module.RecoveryClaimant(
        definition,
        review,
        eula_collector=lambda: calls.append("eula") or {},
        memory_collector=lambda: calls.append("memory") or _pass_memory(module),
        worker_runner=lambda *_args, **_kwargs: calls.append("worker") or {},
    )

    with pytest.raises(module.EulaRecoveryClaimantError, match="EULA"):
        _run(claimant, module, tmp_path)
    assert calls == ["eula"]
    assert not (tmp_path / "eula" / "receipt.json").exists()


def test_arm285_memory_failure_precedes_receipts_and_worker(tmp_path: Path) -> None:
    module, definition, review = _bundle(tmp_path)
    low = module.MemorySnapshot(
        total_physical_bytes=128 * 1024**3,
        available_physical_bytes=4 * 1024**3,
        commit_limit_bytes=224 * 1024**3,
        available_commit_bytes=1 * 1024**3,
    )
    worker_calls = 0

    def worker(*_args, **_kwargs):
        nonlocal worker_calls
        worker_calls += 1
        return {}

    claimant = module.RecoveryClaimant(
        definition,
        review,
        eula_collector=lambda: {"OMNI_KIT_ACCEPT_EULA": "YES"},
        memory_collector=lambda: low,
        worker_runner=worker,
    )
    with pytest.raises(module.EulaRecoveryClaimantError, match="memory"):
        _run(claimant, module, tmp_path)
    assert worker_calls == 0
    assert not (tmp_path / "eula" / "receipt.json").exists()
    assert not (tmp_path / "memory" / "receipt.json").exists()


def test_arm285_retains_both_receipts_then_delegates_once(tmp_path: Path) -> None:
    module, definition, review = _bundle(tmp_path)
    calls = []

    def worker(preparation, **kwargs):
        eula_exists = (tmp_path / "eula" / "receipt.json").exists()
        memory_exists = (tmp_path / "memory" / "receipt.json").exists()
        calls.append((preparation, kwargs, eula_exists, memory_exists))
        return {"status": "SYNTHETIC_PASS"}

    claimant = module.RecoveryClaimant(
        definition,
        review,
        eula_collector=lambda: {"OMNI_KIT_ACCEPT_EULA": "YES"},
        memory_collector=lambda: _pass_memory(module),
        worker_runner=worker,
    )
    result = _run(claimant, module, tmp_path)

    assert result == {"status": "SYNTHETIC_PASS"}
    assert len(calls) == 1
    assert calls[0][1]["authorization_statement"] == module.WORKER_AUTHORIZATION
    assert calls[0][2:] == (True, True)
    assert json.loads((tmp_path / "eula" / "receipt.json").read_bytes())[
        "status"
    ] == "PASS_EULA_PREFLIGHT"
    assert json.loads((tmp_path / "memory" / "receipt.json").read_bytes())[
        "status"
    ] == "PASS_MEMORY_PREFLIGHT"

    with pytest.raises(module.EulaRecoveryClaimantError):
        _run(
            claimant,
            module,
            tmp_path,
            fresh_eula_receipt=tmp_path / "eula-2" / "receipt.json",
            fresh_memory_receipt=tmp_path / "memory-2" / "receipt.json",
        )
    assert len(calls) == 1


def test_arm285_requires_matching_independent_review(tmp_path: Path) -> None:
    module, definition, review = _bundle(tmp_path)
    drifted = dict(review)
    drifted["launch_admitted"] = False
    core = dict(drifted)
    core.pop("claimant_review_sha256")
    drifted["claimant_review_sha256"] = module._sha(core)

    with pytest.raises(module.EulaRecoveryClaimantError, match="review"):
        module.RecoveryClaimant(definition, drifted)


def test_arm285_rejects_worker_lineage_drift(tmp_path: Path) -> None:
    module, definition, _ = _bundle(tmp_path)
    worker = dict(definition["worker_preparation"])
    worker["source_request_sha256"] = "a" * 64
    core = dict(worker)
    core.pop("worker_sha256")
    worker["worker_sha256"] = module._sha(core)
    recovery = {
        "schema": module.RECOVERY_REQUEST_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_EULA_RECOVERY_CLAIMANT_REVIEW",
        "source_worker_request_sha256": "1" * 64,
        "required_authorization_statement": module.EXACT_AUTHORIZATION,
        "old_authorization_reusable": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "claim_only_after_fresh_memory_preflight": True,
            "claim_only_after_fresh_eula_preflight": True,
            "trajectory_playback": False,
            "hardware_or_physical_authority": False,
        },
        "proposed_output_directory": str(tmp_path / "attempt-001"),
    }
    recovery["request_sha256"] = module._sha(recovery)

    with pytest.raises(module.EulaRecoveryClaimantError, match="boundary"):
        module.build_claimant_definition(
            recovery,
            worker,
            recovery_request_file_sha256="4" * 64,
            worker_preparation_file_sha256="5" * 64,
            claimant_source_sha256="6" * 64,
            memory_preflight_source_sha256="7" * 64,
            eula_preflight_source_sha256="8" * 64,
            worker_source_sha256="9" * 64,
        )
