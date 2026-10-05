from __future__ import annotations

import copy

import pytest

from rocell.application.typing_command_session_ledger_v1 import (
    TypingCommandSessionLedgerV1Error,
)
from rocell.application.typing_shadow_materialization_v1 import (
    STAGES,
    TypingShadowMaterializationV1Error,
    parse_typing_shadow_materialization_v1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner


def _completed(request_id="materialized"):
    ledger, supervisor = runner._ledger()
    ledger.submit(
        f"mission-{request_id}", request_id, runner._inputs(ledger, request_id)
    )
    terminal = ledger.run_next_shadow()
    return ledger, supervisor, terminal


def test_runtime_retains_all_five_stage_bodies_with_exact_terminal_lineage():
    ledger, supervisor, terminal = _completed()
    bundle = ledger.shadow_materialization("materialized")
    assert parse_typing_shadow_materialization_v1(bundle) == bundle
    assert set(bundle["stage_artifacts"]) == set(STAGES)
    assert bundle["shadow_pipeline_sha256"] == terminal[
        "shadow_receipt_sha256"
    ]
    candidate_hashes = bundle["stage_hashes"]
    for field, digest in candidate_hashes.items():
        assert len(field) > 0 and len(digest) == 64
    assert bundle["permit_review_ready"] is False
    assert bundle["eligible_for_executor"] is False
    assert bundle["hardware_commands_generated"] == 0
    assert bundle["physical_authority"] is False
    supervisor.invalidate()


def test_materialization_is_stable_after_runtime_invalidation():
    ledger, supervisor, _ = _completed("audit-materialization")
    first = ledger.shadow_materialization("audit-materialization")
    supervisor.invalidate()
    assert ledger.shadow_materialization("audit-materialization") == first


def test_materialization_tamper_fails_closed():
    ledger, supervisor, _ = _completed("tamper-materialization")
    bundle = ledger.shadow_materialization("tamper-materialization")
    changed = copy.deepcopy(bundle)
    changed["stage_artifacts"]["typing_joint_schedule"][
        "hardware_access"
    ] = True
    with pytest.raises(TypingShadowMaterializationV1Error):
        parse_typing_shadow_materialization_v1(changed)
    supervisor.invalidate()


@pytest.mark.parametrize("state", ("queued", "canceled", "stale", "unknown"))
def test_incomplete_or_unknown_request_has_no_materialization(state):
    ledger, supervisor = runner._ledger()
    if state != "unknown":
        ledger.submit(
            f"mission-{state}", state, runner._inputs(ledger, state)
        )
    if state == "canceled":
        ledger.cancel(state)
    elif state == "stale":
        supervisor.reload_sources(issued_monotonic_ns=200)
        ledger.run_next_shadow()
    with pytest.raises(
        TypingCommandSessionLedgerV1Error, match="materialization"
    ):
        ledger.shadow_materialization(state)
    supervisor.invalidate()
