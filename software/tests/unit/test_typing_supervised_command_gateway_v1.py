from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/ai"))

from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256
from rocell.application.typing_runtime_supervisor_v1 import TypingRuntimeSupervisorV1
import rocell.application.typing_supervised_command_gateway_v1 as gateway
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2
from software.tests.integration import test_typing_shadow_pipeline_v1 as fixture


def _supervisor(*, queued=2, requests=8):
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    return TypingRuntimeSupervisorV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="gateway-test", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=QUALIFIED_EVIDENCE_SHA256,
        maximum_queued=queued, maximum_requests=requests)


def _inputs(value, request_id):
    source = fixture._inputs(("R", "O", "B", "O", "T"), "robot",
                             context=value.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"batch-{request_id}", request_id=request_id)


def test_gateway_admits_actual_emitter_bytes_and_returns_hashed_receipt():
    supervisor = _supervisor(); value = gateway.TypingSupervisedCommandGatewayV1(supervisor)
    receipt = value.admit("robot", _inputs(value, "robot"))
    assert gateway.parse_typing_supervised_command_admission_v1(receipt) == receipt
    assert receipt["status"] == gateway.ADMITTED
    assert receipt["disposition"] == "WARM"
    assert value.run_next_shadow()["status"] == "SHADOW_COMPLETED"
    snapshot = value.snapshot()
    assert gateway.parse_typing_supervised_command_gateway_snapshot_v1(snapshot) == snapshot
    assert snapshot["admitted"] == 1 and snapshot["rejected"] == 0


def test_gateway_reports_backpressure_input_and_supervisor_state_without_retry():
    supervisor = _supervisor(queued=1, requests=4)
    value = gateway.TypingSupervisedCommandGatewayV1(supervisor)
    assert value.admit("first", _inputs(value, "first"))["status"] == gateway.ADMITTED
    full = value.admit("second", _inputs(value, "second"))
    assert full["blocker"] == "BACKPRESSURE_QUEUE_FULL"
    assert value.run_next_shadow()["status"] == "SHADOW_COMPLETED"
    duplicate = value.admit("first", _inputs(value, "first"))
    assert duplicate["blocker"] == "INPUT_REJECTED"
    supervisor.reload_sources(issued_monotonic_ns=200)
    state = value.admit("blocked", _inputs(value, "blocked"))
    assert state["blocker"] == "REQUALIFICATION_REQUIRED"
    snapshot = value.snapshot()
    assert snapshot["rejected"] == 3
    assert snapshot["backpressure_rejections"] == 1
    assert snapshot["input_rejections"] == 1
    assert snapshot["state_rejections"] == 1
    assert snapshot["automatic_retry_allowed"] is False


def test_gateway_receipt_and_snapshot_authority_tamper_fail_closed():
    value = gateway.TypingSupervisedCommandGatewayV1(_supervisor())
    receipt = value.admit("robot", _inputs(value, "robot"))
    changed = copy.deepcopy(receipt); changed["physical_authority"] = True
    changed["admission_receipt_sha256"] = gateway._sha({
        key: item for key, item in changed.items()
        if key != "admission_receipt_sha256"
    })
    with pytest.raises(gateway.TypingSupervisedCommandGatewayV1Error, match="authority"):
        gateway.parse_typing_supervised_command_admission_v1(changed)
