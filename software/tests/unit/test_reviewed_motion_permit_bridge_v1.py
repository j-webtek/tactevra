from __future__ import annotations

import pytest
from pathlib import Path
import json
import jsonschema

from rocell.application.context import load_simulation_context
from rocell.application.reviewed_motion_permit_bridge_v1 import (
    ReviewedActionLifecycleV1,
    ReviewedMotionDispatchReceiptV1,
    ReviewedMotionPermitBridgeError,
    issue_reviewed_motion_permit_v1,
)
from rocell.application.single_action_execution_review_v1 import (
    SingleUseExecutionReviewGateV1,
)
import rocell.application.t102_machine_ledger_v1 as ledger_module
from rocell.application.t102_machine_ledger_v1 import T102MachineLedgerError
from rocell.rc03.build_snapshot import Capability
from rocell.safety.permit import goal_hash
from rocell.safety.supervisor import AuthorizationError, SafetySupervisor

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


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json")


def _validate(name, document):
    schema = json.loads(
        (WORKSPACE / "software/ai/schemas" / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)


def _consumed(context):
    review = execution_review._review(context)
    receipt = SingleUseExecutionReviewGateV1(review).consume(
        review.review_sha256, consumed_monotonic_ns=1_500)
    return review, receipt


def test_consumed_review_can_reach_only_exact_supervisor_permit(
    context, released_snapshot,
) -> None:
    review, receipt = _consumed(context)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    now = 100.0
    goal = execution_review._t102_goal(context)
    permit, admission = issue_reviewed_motion_permit_v1(
        supervisor, review, receipt, Capability.KEYBOARD_CONTACT,
        calibrations=_valid_calibrations(), interlocks=_healthy_interlocks(now),
        runtime=_healthy_runtime(), ttl_s=2.0, now_monotonic=now,
    )
    assert permit.plan_hash == review.review_sha256
    assert permit.remaining_uses == 1
    assert admission.to_dict()["physical_authority"] is True
    assert admission.to_dict()["hardware_access"] is False
    assert admission.ordered_goal_sha256 == (goal_hash(goal),)
    _validate("reviewed_motion_permit_admission_v1.schema.json", admission.to_dict())


def test_copied_consumption_receipt_cannot_issue_a_second_permit(
    context, released_snapshot,
) -> None:
    review, receipt = _consumed(context)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    arguments = dict(
        calibrations=_valid_calibrations(), interlocks=_healthy_interlocks(100),
        runtime=_healthy_runtime(), ttl_s=2, now_monotonic=100,
    )
    issue_reviewed_motion_permit_v1(
        supervisor, review, receipt, Capability.KEYBOARD_CONTACT, **arguments)
    with pytest.raises(T102MachineLedgerError, match="already spent"):
        issue_reviewed_motion_permit_v1(
            supervisor, review, dict(receipt), Capability.KEYBOARD_CONTACT,
            **arguments)


def test_wrong_capability_and_tampered_consumption_reject_before_preflight(
    context, released_snapshot,
) -> None:
    review, receipt = _consumed(context)
    supervisor = SafetySupervisor(released_snapshot)
    with pytest.raises(ReviewedMotionPermitBridgeError, match="capability differs"):
        issue_reviewed_motion_permit_v1(
            supervisor, review, receipt, Capability.EMPTY_CELL_MOTION,
            calibrations=_valid_calibrations(), interlocks=_healthy_interlocks(10),
            runtime=_healthy_runtime(), ttl_s=2, now_monotonic=10)
    tampered = {**receipt, "proposal_v2_sha256": "f" * 64}
    with pytest.raises(ReviewedMotionPermitBridgeError, match="content hash"):
        issue_reviewed_motion_permit_v1(
            supervisor, review, tampered, Capability.KEYBOARD_CONTACT,
            calibrations=_valid_calibrations(), interlocks=_healthy_interlocks(10),
            runtime=_healthy_runtime(), ttl_s=2, now_monotonic=10)


def test_permit_issuance_rejects_unreviewed_t102_target_and_settings(
    context, released_snapshot,
) -> None:
    review, receipt = _consumed(context)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    approved = dict(review.reviewed_t102_goal)
    for changed in ({"base": approved["base"] + 0.01},
                    {"hand": approved["hand"] + 0.01},
                    {"spd": approved["spd"] + 1}):
        with pytest.raises(TypeError):
            issue_reviewed_motion_permit_v1(
                supervisor, review, receipt, Capability.KEYBOARD_CONTACT,
                [{**approved, **changed}],
                calibrations=_valid_calibrations(),
                interlocks=_healthy_interlocks(100),
                runtime=_healthy_runtime(), ttl_s=2, now_monotonic=100,
            )


def test_supervisor_still_blocks_missing_current_physical_conditions(
    context, released_snapshot,
) -> None:
    review, receipt = _consumed(context)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    with pytest.raises(AuthorizationError, match="Preflight is blocked"):
        issue_reviewed_motion_permit_v1(
            supervisor, review, receipt, Capability.KEYBOARD_CONTACT,
            calibrations=_valid_calibrations(),
            interlocks=_healthy_interlocks(10), runtime=type(_healthy_runtime())(),
            ttl_s=2, now_monotonic=10)
    with pytest.raises(T102MachineLedgerError, match="already spent"):
        issue_reviewed_motion_permit_v1(
            supervisor, review, receipt, Capability.KEYBOARD_CONTACT,
            calibrations=_valid_calibrations(),
            interlocks=_healthy_interlocks(10), runtime=_healthy_runtime(),
            ttl_s=2, now_monotonic=10)


@pytest.mark.parametrize("terminal", ["COMPLETED", "FAILED", "UNCERTAIN"])
def test_lifecycle_is_hash_chained_terminal_and_never_retries(
    context, released_snapshot, terminal,
) -> None:
    review, receipt = _consumed(context)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    now = 100.0
    goal = execution_review._t102_goal(context)
    permit, admission = issue_reviewed_motion_permit_v1(
        supervisor, review, receipt, Capability.KEYBOARD_CONTACT,
        calibrations=_valid_calibrations(), interlocks=_healthy_interlocks(now),
        runtime=_healthy_runtime(), ttl_s=2, now_monotonic=now)
    lifecycle = ReviewedActionLifecycleV1(admission)
    assert permit.allows(goal, now_monotonic=100.1)
    dispatch = {
        "schema": "rocell.reviewed_motion_dispatch_receipt.v1",
        "status": "REPLAY_WRITE_CONFIRMED",
        "review_sha256": review.review_sha256,
        "permit_binding_sha256": admission.permit_binding_sha256,
        "goal_sha256": goal_hash(goal),
        "payload_sha256": "a" * 64,
        "payload_bytes": 10,
        "confirmed_bytes": 10,
        "retained_bytes_sha256": "a" * 64,
        "permit_consumed": True,
        "write_attempts": 1,
        "dispatched_monotonic_ns": 1_000,
        "error_code": None,
        "composition": "HARDWARE_INCAPABLE_REPLAY",
        "automatic_retry_allowed": False,
        "hardware_access": False,
        "physical_authority": False,
        "physical_command_writes": 0,
    }
    import hashlib
    dispatch["dispatch_receipt_sha256"] = hashlib.sha256(json.dumps(
        dispatch, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("utf-8")).hexdigest()
    typed_dispatch = ReviewedMotionDispatchReceiptV1._issue_from_owned_writer(dispatch)
    lifecycle.started_from_dispatch(typed_dispatch, event_monotonic_ns=1_000)
    lifecycle.terminal(
        terminal, detail_sha256="d" * 64, event_monotonic_ns=2_000)
    snapshot = lifecycle.snapshot()
    assert snapshot["phase"] == terminal
    assert snapshot["automatic_retry_allowed"] is False
    assert snapshot["follow_on_movement_authorized"] is False
    assert snapshot["events"][1]["previous_event_sha256"] == (
        snapshot["events"][0]["event_sha256"])
    _validate("reviewed_action_lifecycle_v1.schema.json", snapshot)
    with pytest.raises(ReviewedMotionPermitBridgeError, match="requires STARTED"):
        lifecycle.terminal(
            terminal, detail_sha256="e" * 64, event_monotonic_ns=3_000)


def test_lifecycle_rejects_caller_authored_or_tampered_start(
    context, released_snapshot,
) -> None:
    review, receipt = _consumed(context)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    goal = execution_review._t102_goal(context)
    _, admission = issue_reviewed_motion_permit_v1(
        supervisor, review, receipt, Capability.KEYBOARD_CONTACT,
        calibrations=_valid_calibrations(), interlocks=_healthy_interlocks(100),
        runtime=_healthy_runtime(), ttl_s=2, now_monotonic=100)
    lifecycle = ReviewedActionLifecycleV1(admission)
    with pytest.raises(ReviewedMotionPermitBridgeError, match="verified sole-writer"):
        lifecycle.started_from_dispatch({
            "schema": "rocell.reviewed_motion_dispatch_receipt.v1",
            "review_sha256": review.review_sha256,
            "permit_binding_sha256": admission.permit_binding_sha256,
            "goal_sha256": goal_hash(goal),
            "permit_consumed": True,
            "write_attempts": 1,
            "automatic_retry_allowed": False,
            "dispatch_receipt_sha256": "0" * 64,
        }, event_monotonic_ns=1_000)
