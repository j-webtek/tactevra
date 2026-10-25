import copy
import json

import pytest

from rocell.application import calibrated_position_vector_feedback_execution as subject
from rocell.calibration.position_vector_campaign import (
    CALIBRATED_FEEDBACK_REQUEST_CONTRACT,
    QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTION_APPROVAL_RECEIPT_SCHEMA,
    canonical_sha256,
)


CONTROLLER = {
    "vid": "10c4",
    "pid": "ea60",
    "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
    "firmware_sha256": "a" * 64,
}
COUNTS = [2050, 2147, 1958, 2550, 2227, 2041, 2042]
JOINTS = ("base", "shoulder", "elbow", "wrist_pitch", "wrist_roll", "gripper")
PRIMARY = (0, 1, 3, 4, 5, 6)


def calibration():
    joints = []
    for joint, index in zip(JOINTS, PRIMARY, strict=True):
        joints.append(
            {
                "joint": joint,
                "primary_index": index,
                "count_zero": COUNTS[index],
                "radians_per_count": 0.001,
                "minimum_rad": -1.0,
                "maximum_rad": 1.0,
                "training_sample_count": 5,
                "held_out_sample_count": 3,
                "held_out_max_abs_error_rad": 0.01,
                "accepted_max_abs_error_rad": 0.035,
            }
        )
    return {
        "schema": "rocell.position_vector_calibration.v1",
        "calibration_id": "installed-arm-no-attachment-calibration-01",
        "response_profile": "POSITION_VECTOR_NAMED_POSE",
        "controller_binding": dict(CONTROLLER),
        "position_order_servo_ids": [11, 12, 13, 14, 15, 16, 17],
        "joint_order": list(JOINTS),
        "joints": joints,
        "shoulder_pair": {
            "driving_index": 1,
            "driven_index": 2,
            "nominal_sum_counts": COUNTS[1] + COUNTS[2],
            "runtime_tolerance_counts": 24,
            "training_max_abs_residual_counts": 8,
            "held_out_max_abs_residual_counts": 9,
        },
        "evidence": {
            "dataset_sha256": "b" * 64,
            "fit_report_sha256": "c" * 64,
            "independent_review_sha256": "d" * 64,
        },
    }


def approval_receipt(artifact):
    return {
        "schema": (
            QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTION_APPROVAL_RECEIPT_SCHEMA
        ),
        "runtime_session_id": "feedback-runtime-session-01",
        "artifact_sha256": canonical_sha256(artifact),
        "controller_binding_sha256": canonical_sha256(CONTROLLER),
        "calibration_id": artifact["calibration_id"],
        "attachment_profile": "no_attachment",
        "request_contract": dict(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
        "request_contract_sha256": canonical_sha256(
            CALIBRATED_FEEDBACK_REQUEST_CONTRACT
        ),
        "calibrated_feedback_request_execution_authorized": True,
        "calibrated_feedback_requests_authorized": True,
    }


def prerequisites(receipt, **updates):
    value = {
        "schema": subject.PREREQUISITES_SCHEMA,
        "attempt_id": "calibrated-feedback-attempt-01",
        "runtime_session_id": receipt["runtime_session_id"],
        "request_execution_approval_receipt_sha256": canonical_sha256(receipt),
        "operator_id": "operator-physical-01",
        "confirmed_at": "2026-10-25T14:00:00-04:00",
        "expires_at": "2026-10-25T14:05:00-04:00",
        "operator_present": True,
        "adapter_powered": True,
        "usb_connected": True,
        "arm_secured": True,
        "arm_stationary": True,
        "area_clear": True,
        "firmware_unchanged": True,
    }
    value.update(updates)
    return value


def exchange_evidence(attempt_id, **updates):
    response = {
        "T": 1051,
        "p": list(COUNTS),
        "pose": "KEYBOARD_FORWARD_CAL_1",
        "motion_active": False,
        "trajectory_progress_permille": 1000,
    }
    value = {
        "schema": subject.EXCHANGE_EVIDENCE_SCHEMA,
        "attempt_id": attempt_id,
        "status": "RESPONSE_OBSERVED_CLOSED",
        "request_line_utf8": "{\"T\":105}\n",
        "response_line_utf8": json.dumps(
            response, separators=(",", ":")
        )
        + "\n",
        "request_count": 1,
        "write_attempt_count": 1,
        "confirmed_write_bytes": 10,
        "automatic_retry_count": 0,
        "response_count": 1,
        "cleanup_confirmed": True,
        "motion_command_count": 0,
        "started_at": "2026-10-25T14:01:00-04:00",
        "finished_at": "2026-10-25T14:01:01-04:00",
        "errors": [],
    }
    value.update(updates)
    return value


def execute(monkeypatch, *, prerequisite_updates=None, exchange_updates=None):
    artifact = calibration()
    approval = approval_receipt(artifact)
    monkeypatch.setattr(
        subject,
        "approve_qualified_calibrated_feedback_request_execution",
        lambda **arguments: approval,
    )
    calls = []

    def exchange(request):
        calls.append(request)
        return exchange_evidence(request["attempt_id"], **(exchange_updates or {}))

    receipt = subject.execute_qualified_calibrated_feedback_request(
        feedback_request_execution_approval_receipt_document=approval,
        execution_prerequisites_document=prerequisites(
            approval, **(prerequisite_updates or {})
        ),
        calibration_document=artifact,
        executed_at="2026-10-25T14:01:02-04:00",
        exchange=exchange,
        approval_arguments={"complete": "approval-chain"},
    )
    return receipt, calls


def test_executes_one_exact_request_and_converts_position_vector(monkeypatch):
    receipt, calls = execute(monkeypatch)

    assert len(calls) == 1
    assert calls[0]["request_contract"] == CALIBRATED_FEEDBACK_REQUEST_CONTRACT
    assert receipt["schema"] == subject.EXECUTION_RECEIPT_SCHEMA
    assert receipt["status"] == "QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTED"
    assert receipt["response_message"]["p"] == COUNTS
    assert receipt["calibrated_feedback"]["accepted_as_calibrated_joint_state"] is True
    assert set(receipt["calibrated_feedback"]["canonical_joints_rad"]) == set(JOINTS)
    assert receipt["calibrated_feedback"]["shoulder_pair_residual_counts"] == 0
    assert receipt["next_required_gate"] == (
        "CALIBRATED_POSITION_VECTOR_FEEDBACK_REQUEST_EXECUTION_REVIEW"
    )
    assert receipt["authority"] == {
        "controller_opened": True,
        "camera_opened": False,
        "commands_sent": 1,
        "motion_commands_sent": 0,
        "automatic_retries": 0,
        "motion_authorized": False,
        "physical_authority": False,
    }


@pytest.mark.parametrize(
    "updates,match",
    [
        ({"operator_present": False}, "freshly confirmed"),
        ({"adapter_powered": False}, "freshly confirmed"),
        ({"firmware_unchanged": False}, "freshly confirmed"),
        ({"expires_at": "2026-10-25T14:00:30-04:00"}, "outside"),
        ({"expires_at": "2026-10-25T14:10:00-04:00"}, "at most five minutes"),
    ],
)
def test_rejects_invalid_live_prerequisites_before_exchange(
    monkeypatch, updates, match
):
    artifact = calibration()
    approval = approval_receipt(artifact)
    monkeypatch.setattr(
        subject,
        "approve_qualified_calibrated_feedback_request_execution",
        lambda **arguments: approval,
    )
    calls = []

    with pytest.raises(subject.CalibratedFeedbackExecutionError, match=match):
        subject.execute_qualified_calibrated_feedback_request(
            feedback_request_execution_approval_receipt_document=approval,
            execution_prerequisites_document=prerequisites(approval, **updates),
            calibration_document=artifact,
            executed_at="2026-10-25T14:01:02-04:00",
            exchange=lambda request: calls.append(request),
            approval_arguments={},
        )
    assert calls == []


@pytest.mark.parametrize(
    "updates,match",
    [
        ({"automatic_retry_count": 1}, "automatic_retry_count"),
        ({"request_count": 2}, "request_count"),
        ({"motion_command_count": 1}, "motion_command_count"),
        ({"cleanup_confirmed": False}, "cleanup"),
        (
            {
                "response_line_utf8": (
                    '{"T":1051,"x":1,"y":2,"z":3,"tit":0,'
                    '"b":0,"s":0,"e":0,"t":0,"r":0,"g":0,"v":1200}\n'
                )
            },
            "position-vector profile",
        ),
        ({"response_line_utf8": "not-json\n"}, "feedback wire contract"),
        (
            {"started_at": "2026-10-25T13:59:59-04:00"},
            "confirmed execution interval",
        ),
    ],
)
def test_rejects_widened_or_wrong_profile_exchange(monkeypatch, updates, match):
    with pytest.raises(subject.CalibratedFeedbackExecutionError, match=match):
        execute(monkeypatch, exchange_updates=updates)


def test_rejects_nonreproducing_approval_before_exchange(monkeypatch):
    artifact = calibration()
    expected = approval_receipt(artifact)
    supplied = copy.deepcopy(expected)
    supplied["runtime_session_id"] = "feedback-runtime-session-other"
    monkeypatch.setattr(
        subject,
        "approve_qualified_calibrated_feedback_request_execution",
        lambda **arguments: expected,
    )
    calls = []

    with pytest.raises(
        subject.CalibratedFeedbackExecutionError,
        match="approval receipt does not reproduce",
    ):
        subject.execute_qualified_calibrated_feedback_request(
            feedback_request_execution_approval_receipt_document=supplied,
            execution_prerequisites_document=prerequisites(supplied),
            calibration_document=artifact,
            executed_at="2026-10-25T14:01:02-04:00",
            exchange=lambda request: calls.append(request),
            approval_arguments={},
        )
    assert calls == []
