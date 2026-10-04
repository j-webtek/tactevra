from __future__ import annotations

import json
import hashlib
from pathlib import Path

import jsonschema
import pytest

from rocell.application.context import load_simulation_context
from rocell.application.reviewed_motion_permit_bridge_v1 import (
    ReviewedActionLifecycleV1,
    ReviewedMotionPermitAdmissionV1,
)
from rocell.application.reviewed_motion_sole_writer_v1 import (
    IncapableReviewedMotionIoV1,
    IncapableWriteFault,
    ReviewedMotionSoleWriterError,
    SettlementPolicyV1,
    execute_reviewed_motion_rehearsal_v1,
)
from rocell.application.single_action_execution_review_v1 import (
    SingleUseExecutionReviewGateV1,
)
from rocell.arm.protocol import CartesianGoal
from rocell.rc03.build_snapshot import Capability
from rocell.safety.permit import MotionPermit, goal_hash
from rocell.safety.supervisor import SafetySupervisor

import test_single_action_execution_review_v1 as execution_review
from test_safety_core import (
    _advance_to_armed,
    _healthy_interlocks,
    _healthy_runtime,
    _valid_calibrations,
)


WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json")


def _validate(name, document):
    schema = json.loads(
        (WORKSPACE / "software/ai/schemas" / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)


def _issued(context, released_snapshot):
    review = execution_review._review(context)
    consumption = SingleUseExecutionReviewGateV1(review).consume(
        review.review_sha256, consumed_monotonic_ns=1_500)
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    goal = CartesianGoal(101, 202, 303, 0.1, 0.2, 0.3, 0.15)
    # Hardware-incapable Cartesian rehearsal retains its legacy test fixture.
    # Physical review issuance accepts only the exact reviewed T102 goal.
    permit = MotionPermit._issue(
        capability=Capability.KEYBOARD_CONTACT,
        snapshot_hash="c" * 64, plan_hash=review.review_sha256,
        goals=(goal,), ttl_s=2, now_monotonic=100,
    )
    unsigned = {
        "review_sha256": review.review_sha256,
        "consumption_sha256": consumption["consumption_sha256"],
        "capability": Capability.KEYBOARD_CONTACT.value,
        "snapshot_sha256": permit.snapshot_hash,
        "plan_hash": permit.plan_hash,
        "ordered_goal_sha256": [goal_hash(goal)],
        "permit_expires_at_monotonic": permit.expires_at_monotonic,
    }
    binding = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode()).hexdigest()
    admission = ReviewedMotionPermitAdmissionV1(
        review.review_sha256, consumption["consumption_sha256"],
        Capability.KEYBOARD_CONTACT, permit.snapshot_hash,
        (goal_hash(goal),), permit.expires_at_monotonic, binding,
    )
    return goal, permit, admission, ReviewedActionLifecycleV1(admission)


def _sample(ns, *, x=101, y=202, z=303, tit=0.1, r=0.2, g=0.3):
    return {"captured_monotonic_ns": ns, "message": {
        "T": 1051, "x": x, "y": y, "z": z, "tit": tit, "r": r, "g": g,
    }}


def test_one_exact_write_and_fresh_settled_feedback_complete_rehearsal(
    context, released_snapshot,
) -> None:
    goal, permit, admission, lifecycle = _issued(context, released_snapshot)
    io = IncapableReviewedMotionIoV1()
    report = execute_reviewed_motion_rehearsal_v1(
        goal, permit, admission, lifecycle, io,
        [_sample(1_100), _sample(1_200)],
        now_monotonic=100.1, dispatched_monotonic_ns=1_000,
        assessed_monotonic_ns=1_300)
    assert report["status"] == "COMPLETED"
    assert report["dispatch"]["status"] == "REPLAY_WRITE_CONFIRMED"
    assert report["dispatch"]["write_attempts"] == 1
    assert report["settlement"]["status"] == "OBSERVED_SETTLED_ARRIVAL"
    assert report["settlement"]["controller_receipt_claimed"] is False
    assert report["physical_command_writes"] == 0
    assert permit.remaining_uses == 0
    assert lifecycle.snapshot()["events"][1]["detail_sha256"] == (
        report["dispatch"]["dispatch_receipt_sha256"])
    _validate("reviewed_motion_dispatch_receipt_v1.schema.json", report["dispatch"])
    _validate("reviewed_motion_settlement_evidence_v1.schema.json", report["settlement"])
    _validate("reviewed_motion_execution_rehearsal_v1.schema.json", report)


@pytest.mark.parametrize(
    "fault, expected_status, expected_dispatch",
    [
        (IncapableWriteFault.ZERO_WRITE, "FAILED", "ZERO_WRITE_CONFIRMED"),
        (IncapableWriteFault.PARTIAL_WRITE, "UNCERTAIN", "PARTIAL_WRITE_CONFIRMED"),
        (IncapableWriteFault.DISCONNECT_AFTER_WRITE, "UNCERTAIN", "WRITE_COMPLETION_UNCERTAIN"),
    ],
)
def test_write_faults_are_terminal_single_attempt_without_retry(
    context, released_snapshot, fault, expected_status, expected_dispatch,
) -> None:
    goal, permit, admission, lifecycle = _issued(context, released_snapshot)
    io = IncapableReviewedMotionIoV1(fault)
    report = execute_reviewed_motion_rehearsal_v1(
        goal, permit, admission, lifecycle, io, (), now_monotonic=100.1,
        dispatched_monotonic_ns=1_000, assessed_monotonic_ns=1_200)
    assert report["status"] == expected_status
    assert report["dispatch"]["status"] == expected_dispatch
    assert report["dispatch"]["write_attempts"] == 1
    assert report["automatic_retry_allowed"] is False
    assert report["follow_on_movement_authorized"] is False
    assert permit.remaining_uses == 0
    with pytest.raises(ReviewedMotionSoleWriterError, match="already claimed"):
        execute_reviewed_motion_rehearsal_v1(
            goal, permit, admission, ReviewedActionLifecycleV1(admission), io, (),
            now_monotonic=100.2, dispatched_monotonic_ns=1_300,
            assessed_monotonic_ns=1_400)


def test_stale_wrong_and_missing_feedback_cannot_claim_arrival(
    context, released_snapshot,
) -> None:
    goal, permit, admission, lifecycle = _issued(context, released_snapshot)
    report = execute_reviewed_motion_rehearsal_v1(
        goal, permit, admission, lifecycle, IncapableReviewedMotionIoV1(),
        [
            _sample(1_100),
            _sample(1_200, x=150),
            _sample(1_300, x=150),
        ],
        settlement_policy=SettlementPolicyV1(max_feedback_age_ns=100),
        now_monotonic=100.1, dispatched_monotonic_ns=1_000,
        assessed_monotonic_ns=1_500)
    assert report["status"] == "UNCERTAIN"
    assert report["settlement"]["status"] == "ARRIVAL_UNVERIFIED"
    assert report["settlement"]["accepted_sample_count"] == 0
    assert "STALE_OR_FUTURE_FEEDBACK" in report["settlement"]["rejected_sample_codes"]


def test_expired_or_replayed_permit_never_reaches_write_boundary(
    context, released_snapshot,
) -> None:
    goal, permit, admission, lifecycle = _issued(context, released_snapshot)
    io = IncapableReviewedMotionIoV1()
    with pytest.raises(ReviewedMotionSoleWriterError, match="not consumable"):
        execute_reviewed_motion_rehearsal_v1(
            goal, permit, admission, lifecycle, io, (), now_monotonic=103,
            dispatched_monotonic_ns=1_000, assessed_monotonic_ns=1_100)
    assert io.write_attempts == 0
    assert io.retained_bytes == b""


def test_crossed_admission_goal_is_rejected_before_claim_or_write(
    context, released_snapshot,
) -> None:
    _, permit, admission, lifecycle = _issued(context, released_snapshot)
    wrong = CartesianGoal(999, 202, 303, 0.1, 0.2, 0.3, 0.15)
    io = IncapableReviewedMotionIoV1()
    with pytest.raises(ReviewedMotionSoleWriterError, match="binding mismatch"):
        execute_reviewed_motion_rehearsal_v1(
            wrong, permit, admission, lifecycle, io, (), now_monotonic=100.1,
            dispatched_monotonic_ns=1_000, assessed_monotonic_ns=1_100)
    assert io.write_attempts == 0
