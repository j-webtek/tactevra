from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/ai"))

import rocell.application.typing_runtime_supervisor_v1 as supervisor
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256
from software.tests.integration import test_typing_shadow_pipeline_v1 as fixture


def _start(*, evidence=None):
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    return supervisor.TypingRuntimeSupervisorV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="supervisor-test", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=evidence or QUALIFIED_EVIDENCE_SHA256,
        maximum_queued=4, maximum_requests=16)


def _inputs(value, request_id):
    from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2
    source = fixture._inputs(("R", "O", "B", "O", "T"), "robot",
                             context=value.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"batch-{request_id}", request_id=request_id)


def test_qualified_and_mismatch_start_states_are_explicit():
    warm = _start()
    assert warm.state == supervisor.WARM
    assert warm.exact_reuse_enabled is True
    changed = dict(QUALIFIED_EVIDENCE_SHA256)
    changed[next(iter(changed))] = "f" * 64
    fallback = _start(evidence=changed)
    assert fallback.state == supervisor.FULL_SOLVE_ONLY
    assert fallback.exact_reuse_enabled is False
    snap = fallback.snapshot()
    assert supervisor.parse_typing_runtime_supervisor_snapshot_v1(snap) == snap


@pytest.mark.parametrize("transition", ("reload", "restart"))
def test_lifecycle_transition_blocks_new_work_until_explicit_continuation(transition):
    value = _start()
    value.submit("queued", _inputs(value, "queued"))
    if transition == "reload":
        value.reload_sources(issued_monotonic_ns=200)
    else:
        value.restart(service_instance_id="supervisor-test-new",
                      issued_monotonic_ns=200)
    assert value.state == supervisor.REQUALIFICATION_REQUIRED
    with pytest.raises(supervisor.TypingRuntimeSupervisorV1Error,
                       match="requalification required"):
        value.submit("blocked", _inputs(value, "blocked"))
    assert value.execute_next()["status"] == "STALE_GENERATION_REJECTED"
    value.continue_full_solve_only()
    assert value.state == supervisor.FULL_SOLVE_ONLY
    value.submit("fallback", _inputs(value, "fallback"))
    assert value.execute_next()["status"] == "SHADOW_COMPLETED"
    assert value.snapshot()["full_solve_continuations"] == 1


def test_snapshot_tamper_and_invalidated_supervisor_fail_closed():
    value = _start(); snapshot = value.snapshot()
    changed = copy.deepcopy(snapshot); changed["physical_authority"] = True
    changed["supervisor_snapshot_sha256"] = supervisor._sha({
        key: item for key, item in changed.items()
        if key != "supervisor_snapshot_sha256"
    })
    with pytest.raises(supervisor.TypingRuntimeSupervisorV1Error, match="authority"):
        supervisor.parse_typing_runtime_supervisor_snapshot_v1(changed)
    value.invalidate()
    assert value.state == supervisor.REQUALIFICATION_REQUIRED
    with pytest.raises(supervisor.TypingRuntimeSupervisorV1Error, match="invalidated"):
        value.submit("blocked", {})
