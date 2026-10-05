from __future__ import annotations

import pytest

from rocell.application.typing_execution_handoff_assembler_v1 import (
    TypingExecutionHandoffAssemblerV1Error,
    assemble_typing_execution_handoff_candidate_v1,
)
from rocell.application.typing_execution_handoff_candidate_v1 import (
    build_typing_execution_handoff_candidate_v1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner


def test_completed_session_assembles_exact_candidate_without_replanning():
    ledger, supervisor = runner._ledger()
    inputs = runner._inputs(ledger, "assembled")
    ledger.submit("mission-assembled", "assembled", inputs)
    session = ledger.run_next_shadow()
    before = ledger.artifact_store_snapshot()
    assembled = assemble_typing_execution_handoff_candidate_v1(
        ledger, "assembled"
    )
    expected = build_typing_execution_handoff_candidate_v1(
        session, ledger.admission_receipt("assembled"),
        ledger.terminal_service_receipt("assembled"),
        ledger.shadow_artifact("assembled"),
    )
    after = ledger.artifact_store_snapshot()
    assert assembled == expected
    assert after["retained_entries"] == before["retained_entries"] == 1
    assert after["retrievals"] == before["retrievals"] + 2
    supervisor.invalidate()


def test_repeat_and_post_invalidation_assembly_are_identical():
    ledger, supervisor = runner._ledger()
    ledger.submit("mission-audit", "audit", runner._inputs(ledger, "audit"))
    ledger.run_next_shadow()
    first = assemble_typing_execution_handoff_candidate_v1(ledger, "audit")
    second = assemble_typing_execution_handoff_candidate_v1(ledger, "audit")
    supervisor.invalidate()
    audited = assemble_typing_execution_handoff_candidate_v1(ledger, "audit")
    assert first == second == audited


@pytest.mark.parametrize("state", ("queued", "canceled", "stale", "unknown"))
def test_incomplete_or_unknown_session_fails_closed(state):
    ledger, supervisor = runner._ledger()
    request_id = state
    if state != "unknown":
        ledger.submit(
            f"mission-{state}", request_id, runner._inputs(ledger, request_id)
        )
    if state == "canceled":
        ledger.cancel(request_id)
    elif state == "stale":
        supervisor.reload_sources(issued_monotonic_ns=200)
        ledger.run_next_shadow()
    with pytest.raises(
        TypingExecutionHandoffAssemblerV1Error, match="unavailable"
    ):
        assemble_typing_execution_handoff_candidate_v1(ledger, request_id)
    supervisor.invalidate()


def test_noncanonical_ledger_fails_closed():
    with pytest.raises(
        TypingExecutionHandoffAssemblerV1Error, match="canonical"
    ):
        assemble_typing_execution_handoff_candidate_v1(object(), "request")
