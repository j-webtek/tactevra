from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/ai"))

from rocell.application.typing_execution_handoff_candidate_v1 import (
    TypingExecutionHandoffCandidateV1Error,
    build_typing_execution_handoff_candidate_v1,
    parse_typing_execution_handoff_candidate_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import run_typing_shadow_pipeline_v1
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner


def _evidence():
    ledger, supervisor = runner._ledger()
    inputs = runner._inputs(ledger, "handoff")
    shadow = run_typing_shadow_pipeline_v1(**inputs)
    queued = ledger.submit("mission-handoff", "handoff", inputs)
    terminal = ledger.run_next_shadow()
    service = ledger.terminal_service_receipt("handoff")
    admission = ledger.admission_receipt("handoff")
    assert admission["admission_receipt_sha256"] == queued[
        "admission_receipt_sha256"]
    supervisor.invalidate()
    return terminal, admission, service, shadow


def test_completed_evidence_builds_blocked_zero_authority_candidate():
    terminal, admission, service, shadow = _evidence()
    value = build_typing_execution_handoff_candidate_v1(
        terminal, admission, service, shadow)
    assert parse_typing_execution_handoff_candidate_v1(value) == value
    assert value["status"] == "BLOCKED_PENDING_EXECUTION_QUALIFICATION"
    assert value["eligible_for_executor"] is False
    assert value["controller_commands"] == []


def test_lineage_mismatch_and_noncompleted_session_fail_closed():
    terminal, admission, service, shadow = _evidence()
    changed = copy.deepcopy(shadow)
    changed["typing_shadow_pipeline_sha256"] = "f" * 64
    with pytest.raises(TypingExecutionHandoffCandidateV1Error):
        build_typing_execution_handoff_candidate_v1(
            terminal, admission, service, changed)
    changed = copy.deepcopy(terminal); changed["status"] = "SHADOW_REJECTED"
    changed["blocker"] = "SHADOW_PIPELINE_REJECTED"
    with pytest.raises(TypingExecutionHandoffCandidateV1Error):
        build_typing_execution_handoff_candidate_v1(
            changed, admission, service, shadow)


def test_candidate_authority_tamper_fails_closed():
    terminal, admission, service, shadow = _evidence()
    value = build_typing_execution_handoff_candidate_v1(
        terminal, admission, service, shadow)
    changed = copy.deepcopy(value); changed["eligible_for_executor"] = True
    changed["handoff_candidate_sha256"] = "f" * 64
    with pytest.raises(TypingExecutionHandoffCandidateV1Error, match="hash"):
        parse_typing_execution_handoff_candidate_v1(changed)
