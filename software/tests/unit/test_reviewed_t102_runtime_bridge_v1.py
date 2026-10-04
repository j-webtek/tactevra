from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.context import load_simulation_context
from rocell.application.production_controller_runtime_contract_v1 import (
    ProductionControllerRuntimeContractV1,
    ProductionControllerRuntimeManifestV1,
    RuntimeCommandFrameV1,
)
from rocell.application.reviewed_motion_permit_bridge_v1 import (
    ReviewedActionLifecycleV1,
    issue_reviewed_motion_permit_v1,
)
from rocell.application.reviewed_motion_sole_writer_v1 import (
    IncapableReviewedMotionIoV1,
    IncapableWriteFault,
)
from rocell.application.reviewed_t102_runtime_bridge_v1 import (
    JointSettlementPolicyV1,
    ReviewedT102RuntimeBridgeError,
    execute_reviewed_t102_runtime_rehearsal_v1,
)
from rocell.application.single_action_execution_review_v1 import (
    SingleUseExecutionReviewGateV1,
)
import rocell.application.t102_machine_ledger_v1 as ledger_module
from rocell.arm.all_joint_command import all_joint_command
from rocell.arm.protocol import encode_line
from rocell.rc03.build_snapshot import Capability
from rocell.safety.supervisor import SafetySupervisor

import test_single_action_execution_review_v1 as execution_review
from test_safety_core import (
    _advance_to_armed,
    _healthy_interlocks,
    _healthy_runtime,
    _valid_calibrations,
)


WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def machine_ledger(tmp_path, monkeypatch):
    root = tmp_path / "machine-ledger"
    root.mkdir()
    monkeypatch.setattr(ledger_module, "machine_root", lambda: root)
    return root
SESSION = "controller-session-arm049"
EPOCH = "d" * 64
PROFILE = "e" * 64


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json")


def _manifest():
    return ProductionControllerRuntimeManifestV1(
        runtime_id="arm049-runtime",
        candidate_app_sha256="a" * 64,
        protocol_source_sha256="b" * 64,
        controller_joint_mapping_sha256="c" * 64,
        configuration_epoch_sha256=EPOCH,
        expected_encoding_profile_sha256=PROFILE,
        controller_session_id=SESSION,
    )


def _message(offset=0.0):
    return all_joint_command(
        [offset + value for value in (.1, .1, .1, .1, .1, 0.0)],
        speed=20, acceleration=1)


def _frame(message, **changes):
    values = dict(
        sequence=1,
        correlation_id="arm049-correlation-1",
        writer_instance_id="arm049-writer",
        controller_session_id=SESSION,
        configuration_epoch_sha256=EPOCH,
        encoding_profile_sha256=PROFILE,
        issued_monotonic_ns=900,
        expires_monotonic_ns=2_000,
        wire_bytes=encode_line(message),
    )
    values.update(changes)
    return RuntimeCommandFrameV1(**values)


def _ack(sequence=1):
    return encode_line({
        "T": 1021, "status": "ACCEPTED_ONCE", "ordinal": sequence,
    })


def _feedback(ns, joints=(.1, .1, .1, .1, .1, 0.0)):
    return {
        "captured_monotonic_ns": ns,
        "response_bytes": encode_line({
            "T": 1051,
            **dict(zip(("b", "s", "e", "t", "r", "g"), joints)),
        }),
    }


def _issued(context, released_snapshot, message=None):
    message = message or _message()
    review = execution_review._review(context)
    consumption = SingleUseExecutionReviewGateV1(review).consume(
        review.review_sha256, consumed_monotonic_ns=1_500)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    permit, admission = issue_reviewed_motion_permit_v1(
        supervisor, review, consumption, Capability.KEYBOARD_CONTACT,
        calibrations=_valid_calibrations(), interlocks=_healthy_interlocks(100),
        runtime=_healthy_runtime(), ttl_s=2, now_monotonic=100)
    return (
        message, permit, admission, ReviewedActionLifecycleV1(admission),
        ProductionControllerRuntimeContractV1(_manifest()),
    )


def _run(context, released_snapshot, *, fault=IncapableWriteFault.NONE,
         ack=None, feedback=None, frame_changes=None, policy=None):
    message, permit, admission, lifecycle, runtime = _issued(
        context, released_snapshot)
    frame = _frame(message, **(frame_changes or {}))
    report = execute_reviewed_t102_runtime_rehearsal_v1(
        frame, permit, admission, lifecycle, runtime,
        IncapableReviewedMotionIoV1(fault),
        _ack() if ack is None else ack,
        [_feedback(1_100), _feedback(1_200)] if feedback is None else feedback,
        writer_instance_id="arm049-writer", now_monotonic=100.1,
        dispatch_monotonic_ns=1_000, assessment_monotonic_ns=1_300,
        settlement_policy=policy or JointSettlementPolicyV1(),
    )
    return report, permit, runtime


def _schema(name):
    return json.loads((WORKSPACE / "software/ai/schemas" / name).read_text(
        encoding="utf-8"))


def test_exact_t102_ack_and_fresh_joint_settling_complete(context, released_snapshot):
    report, permit, runtime = _run(context, released_snapshot)
    assert report["status"] == "COMPLETED"
    assert report["dispatch"]["status"] == "REPLAY_WRITE_CONFIRMED"
    assert report["acknowledgment"]["status"] == "ACCEPTED_ONCE"
    assert report["acknowledgment"]["authentic_physical_receipt"] is False
    assert report["settlement"]["status"] == "OBSERVED_SETTLED_JOINT_ARRIVAL"
    assert report["settlement"]["controller_arrival_claimed"] is True
    assert report["settlement"]["independent_task_outcome_verified"] is False
    assert report["runtime_report"]["acknowledgment_count"] == 1
    assert report["runtime_report"]["feedback_exchange_count"] == 2
    assert report["runtime_report"]["status"] == "TERMINAL_NO_RETRY"
    assert report["runtime_report"]["terminal_reason"] == (
        "COMMAND_SETTLED_REHEARSAL_COMPLETE")
    assert report["physical_command_writes"] == 0
    assert permit.remaining_uses == 0
    jsonschema.Draft202012Validator(_schema(
        "reviewed_t102_runtime_execution_rehearsal_v1.schema.json"
    )).validate(report)
    jsonschema.Draft202012Validator(_schema(
        "reviewed_t102_joint_settlement_v1.schema.json"
    )).validate(report["settlement"])


@pytest.mark.parametrize(
    "fault, terminal, runtime_reason",
    [
        (IncapableWriteFault.ZERO_WRITE, "FAILED", "COMMAND_ZERO_WRITE_CONFIRMED"),
        (IncapableWriteFault.PARTIAL_WRITE, "UNCERTAIN", "COMMAND_WRITE_COMPLETION_UNCERTAIN"),
        (IncapableWriteFault.DISCONNECT_AFTER_WRITE, "UNCERTAIN", "COMMAND_WRITE_COMPLETION_UNCERTAIN"),
    ],
)
def test_write_faults_lock_runtime_without_ack_feedback_or_retry(
    context, released_snapshot, fault, terminal, runtime_reason,
):
    report, permit, runtime = _run(context, released_snapshot, fault=fault)
    assert report["status"] == terminal
    assert report["acknowledgment"] is None
    assert report["settlement"] is None
    assert report["runtime_report"]["terminal_reason"] == runtime_reason
    assert report["runtime_report"]["feedback_exchange_count"] == 0
    assert report["automatic_retry_allowed"] is False
    assert report["follow_on_movement_authorized"] is False
    assert permit.remaining_uses == 0


def test_wrong_ack_after_full_write_is_uncertain_and_terminal(context, released_snapshot):
    report, _, _ = _run(context, released_snapshot, ack=_ack(2))
    assert report["status"] == "UNCERTAIN"
    assert report["acknowledgment"]["status"] == "ACKNOWLEDGMENT_REJECTED"
    assert report["runtime_report"]["status"] == "TERMINAL_NO_RETRY"
    assert report["runtime_report"]["feedback_exchange_count"] == 0


def test_acknowledged_but_unsettled_or_stale_feedback_is_uncertain(
    context, released_snapshot, machine_ledger, monkeypatch,
):
    report, _, _ = _run(
        context, released_snapshot,
        feedback=[_feedback(1_100, (1, 1, 1, 1, 1, 1)),
                  _feedback(1_200, (1, 1, 1, 1, 1, 1))])
    assert report["status"] == "UNCERTAIN"
    assert report["acknowledgment"]["status"] == "ACCEPTED_ONCE"
    assert report["settlement"]["status"] == "JOINT_ARRIVAL_UNVERIFIED"
    assert report["runtime_report"]["terminal_reason"] == (
        "COMMAND_ARRIVAL_UNCERTAIN")

    second_root = machine_ledger.parent / "second-machine-ledger"
    second_root.mkdir()
    monkeypatch.setattr(ledger_module, "machine_root", lambda: second_root)
    stale, _, _ = _run(
        context, released_snapshot,
        feedback=[_feedback(1_100), _feedback(1_200)],
        policy=JointSettlementPolicyV1(max_feedback_age_ns=50))
    assert stale["status"] == "UNCERTAIN"
    assert stale["settlement"]["accepted_sample_count"] == 0
    assert "STALE_OR_FUTURE_FEEDBACK" in stale["settlement"]["rejected_sample_codes"]


def test_feedback_collection_failure_closes_acknowledged_action_uncertain(
    context, released_snapshot,
):
    def broken_feedback():
        yield _feedback(1_100)
        raise RuntimeError("modeled acquisition loss")

    report, _, _ = _run(
        context, released_snapshot, feedback=broken_feedback())
    assert report["status"] == "UNCERTAIN"
    assert report["acknowledgment"]["status"] == "ACCEPTED_ONCE"
    assert report["settlement"]["accepted_sample_count"] == 0
    assert report["settlement"]["rejected_sample_codes"] == [
        "FEEDBACK_COLLECTION_ERROR"]
    assert report["runtime_report"]["terminal_reason"] == (
        "COMMAND_ARRIVAL_UNCERTAIN")


def test_crossed_session_rejects_before_writer_claim_or_permit_consumption(
    context, released_snapshot,
):
    message, permit, admission, lifecycle, runtime = _issued(
        context, released_snapshot)
    io = IncapableReviewedMotionIoV1()
    with pytest.raises(ReviewedT102RuntimeBridgeError, match="identity differs"):
        execute_reviewed_t102_runtime_rehearsal_v1(
            _frame(message, controller_session_id="wrong-session"),
            permit, admission, lifecycle, runtime, io, _ack(), (),
            writer_instance_id="arm049-writer", now_monotonic=100.1,
            dispatch_monotonic_ns=1_000, assessment_monotonic_ns=1_300)
    assert runtime.report()["state"] == "SAFE_IDLE"
    assert permit.remaining_uses == 1
    assert io.write_attempts == 0


def test_expired_permit_never_attempts_write_and_locks_admitted_runtime(
    context, released_snapshot,
):
    message, permit, admission, lifecycle, runtime = _issued(
        context, released_snapshot)
    io = IncapableReviewedMotionIoV1()
    with pytest.raises(ReviewedT102RuntimeBridgeError, match="not consumable"):
        execute_reviewed_t102_runtime_rehearsal_v1(
            _frame(message), permit, admission, lifecycle, runtime, io,
            _ack(), (), writer_instance_id="arm049-writer", now_monotonic=103,
            dispatch_monotonic_ns=1_000, assessment_monotonic_ns=1_300)
    assert io.write_attempts == 0
    assert runtime.report()["terminal_reason"] == "COMMAND_WRITE_COMPLETION_UNCERTAIN"
