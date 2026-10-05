from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/ai"))

from rocell.application.typing_command_session_ledger_v1 import (
    TypingCommandSessionLedgerV1,
    TypingCommandSessionLedgerV1Error,
    parse_typing_command_session_ledger_snapshot_v1,
    parse_typing_command_session_receipt_v1,
)
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256
from rocell.application.typing_runtime_supervisor_v1 import TypingRuntimeSupervisorV1
from rocell.application.typing_supervised_command_gateway_v1 import TypingSupervisedCommandGatewayV1
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2
from software.tests.integration import test_typing_shadow_pipeline_v1 as fixture


def _ledger(*, sessions=8, queued=2, requests=8):
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    supervisor = TypingRuntimeSupervisorV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="session-ledger-test", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=QUALIFIED_EVIDENCE_SHA256,
        maximum_queued=queued, maximum_requests=requests)
    return TypingCommandSessionLedgerV1(
        TypingSupervisedCommandGatewayV1(supervisor),
        maximum_sessions=sessions), supervisor


def _inputs(value, request_id, text="robot"):
    source = fixture._inputs(tuple(text.upper()), text, context=value.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"batch-{request_id}", request_id=request_id)


def test_session_chains_admission_to_terminal_and_supports_lookup():
    ledger, _ = _ledger()
    queued = ledger.submit("mission-1", "robot", _inputs(ledger, "robot"))
    assert parse_typing_command_session_receipt_v1(queued) == queued
    assert queued["status"] == "QUEUED" and queued["revision"] == 0
    terminal = ledger.run_next_shadow()
    assert parse_typing_command_session_receipt_v1(terminal) == terminal
    assert terminal["status"] == "SHADOW_COMPLETED"
    assert terminal["previous_session_receipt_sha256"] == queued["session_receipt_sha256"]
    assert ledger.get("robot") == terminal
    snapshot = ledger.snapshot()
    assert parse_typing_command_session_ledger_snapshot_v1(snapshot) == snapshot
    assert snapshot["queued_sessions"] == 0 and snapshot["terminal_sessions"] == 1


def test_identical_duplicate_is_idempotent_but_changed_duplicate_fails_closed():
    ledger, _ = _ledger()
    inputs = _inputs(ledger, "robot")
    first = ledger.submit("mission-1", "robot", inputs)
    assert ledger.submit("mission-1", "robot", inputs) == first
    changed = _inputs(ledger, "robot", text="robots")
    with pytest.raises(TypingCommandSessionLedgerV1Error, match="different input"):
        ledger.submit("mission-1", "robot", changed)
    snapshot = ledger.snapshot()
    assert snapshot["duplicate_replays"] == 1
    assert snapshot["conflicting_duplicates"] == 1


def test_cancellation_admission_rejection_and_capacity_are_terminal():
    ledger, _ = _ledger(sessions=2, queued=1, requests=4)
    queued = ledger.submit("mission-1", "first", _inputs(ledger, "first"))
    rejected = ledger.submit("mission-1", "second", _inputs(ledger, "second"))
    assert rejected["status"] == "ADMISSION_REJECTED"
    assert rejected["blocker"] == "BACKPRESSURE_QUEUE_FULL"
    canceled = ledger.cancel("first")
    assert canceled["status"] == "CANCELED_BEFORE_ADMISSION"
    capacity = ledger.submit("mission-2", "third", _inputs(ledger, "third"))
    assert capacity["status"] == "LEDGER_CAPACITY_REJECTED"
    assert capacity["admission_receipt_sha256"] is None
    assert parse_typing_command_session_receipt_v1(capacity) == capacity


def test_stale_terminal_and_receipt_tamper_fail_closed():
    ledger, supervisor = _ledger()
    queued = ledger.submit("mission-1", "robot", _inputs(ledger, "robot"))
    supervisor.reload_sources(issued_monotonic_ns=200)
    stale = ledger.run_next_shadow()
    assert stale["status"] == "STALE_GENERATION_REJECTED"
    assert stale["previous_session_receipt_sha256"] == queued["session_receipt_sha256"]
    changed = copy.deepcopy(stale); changed["physical_authority"] = True
    changed["session_receipt_sha256"] = "f" * 64
    with pytest.raises(TypingCommandSessionLedgerV1Error, match="hash"):
        parse_typing_command_session_receipt_v1(changed)
