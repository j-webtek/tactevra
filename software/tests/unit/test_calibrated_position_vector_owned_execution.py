import hashlib
import json
import threading

from rocell.application import calibrated_position_vector_feedback_execution as execution
from rocell.application import calibrated_position_vector_execution_review as review
from rocell.application import calibrated_position_vector_owned_execution as subject
from rocell.application.physical_connection_contracts import (
    EvidenceOrigin,
    RoArmUsbSerialIdentity,
    UsbDriverIdentity,
)
from rocell.calibration.position_vector_campaign import (
    CALIBRATED_FEEDBACK_REQUEST_CONTRACT,
    QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTION_APPROVAL_RECEIPT_SCHEMA,
    canonical_sha256,
)
from rocell.providers.windows.arm_feedback_worker import ReviewedControllerBinding
from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
    canonical,
    decode_request,
)
from rocell.providers.windows.owned_worker_process import OwnedWorkerResult


FIRMWARE_SHA = "3" * 64
SOURCE_SHA = "7" * 64
COUNTS = [2050, 2147, 1958, 2550, 2227, 2041, 2042]
CONTROLLER = {
    "vid": "10c4",
    "pid": "ea60",
    "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
    "firmware_sha256": FIRMWARE_SHA,
}


def identity():
    return RoArmUsbSerialIdentity(
        "10c4", "ea60", CONTROLLER["unit_serial"],
        "USB\\VID_10C4&PID_EA60\\" + CONTROLLER["unit_serial"],
        "usb-unit:10c4:ea60:" + CONTROLLER["unit_serial"], "COM404",
        UsbDriverIdentity("Silicon Labs", "silabser", "11.3.0", "silabser.inf"),
    )


def reviewed():
    return ReviewedControllerBinding(
        identity(), "1" * 64, "2" * 64, FIRMWARE_SHA, "4" * 64, "5" * 64,
        EvidenceOrigin.PHYSICAL_OBSERVATION,
    )


def calibration():
    primary = (0, 1, 3, 4, 5, 6)
    names = ("base", "shoulder", "elbow", "wrist_pitch", "wrist_roll", "gripper")
    return {
        "schema": "rocell.position_vector_calibration.v1",
        "calibration_id": "installed-arm-no-attachment-calibration-01",
        "response_profile": "POSITION_VECTOR_NAMED_POSE",
        "controller_binding": dict(CONTROLLER),
        "position_order_servo_ids": [11, 12, 13, 14, 15, 16, 17],
        "joint_order": list(names),
        "joints": [
            {
                "joint": name, "primary_index": index,
                "count_zero": COUNTS[index], "radians_per_count": 0.001,
                "minimum_rad": -1.0, "maximum_rad": 1.0,
                "training_sample_count": 5, "held_out_sample_count": 3,
                "held_out_max_abs_error_rad": 0.01,
                "accepted_max_abs_error_rad": 0.035,
            }
            for name, index in zip(names, primary, strict=True)
        ],
        "shoulder_pair": {
            "driving_index": 1, "driven_index": 2,
            "nominal_sum_counts": COUNTS[1] + COUNTS[2],
            "runtime_tolerance_counts": 24,
            "training_max_abs_residual_counts": 8,
            "held_out_max_abs_residual_counts": 9,
        },
        "evidence": {
            "dataset_sha256": "b" * 64, "fit_report_sha256": "c" * 64,
            "independent_review_sha256": "d" * 64,
        },
    }


def inputs(monkeypatch):
    artifact = calibration()
    approval = {
        "schema": QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTION_APPROVAL_RECEIPT_SCHEMA,
        "runtime_session_id": "feedback-runtime-session-01",
        "artifact_sha256": canonical_sha256(artifact),
        "controller_binding_sha256": canonical_sha256(CONTROLLER),
        "calibration_id": artifact["calibration_id"],
        "attachment_profile": "no_attachment",
        "request_contract": dict(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
        "request_contract_sha256": canonical_sha256(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
        "calibrated_feedback_request_execution_authorized": True,
        "calibrated_feedback_requests_authorized": True,
    }
    prerequisites = {
        "schema": execution.PREREQUISITES_SCHEMA,
        "attempt_id": "calibrated-owned-app-01",
        "runtime_session_id": approval["runtime_session_id"],
        "request_execution_approval_receipt_sha256": canonical_sha256(approval),
        "operator_id": "operator-physical-01",
        "confirmed_at": "2026-10-25T14:00:00-04:00",
        "expires_at": "2026-10-25T14:05:00-04:00",
        "operator_present": True, "adapter_powered": True, "usb_connected": True,
        "arm_secured": True, "arm_stationary": True, "area_clear": True,
        "firmware_unchanged": True,
    }
    monkeypatch.setattr(
        execution, "approve_qualified_calibrated_feedback_request_execution",
        lambda **_: approval,
    )
    return artifact, approval, prerequisites


def evidence():
    response = {
        "T": 1051, "p": COUNTS, "pose": "KEYBOARD_FORWARD_CAL_1",
        "motion_active": False, "trajectory_progress_permille": 1000,
    }
    return {
        "schema": execution.EXCHANGE_EVIDENCE_SCHEMA,
        "attempt_id": "calibrated-owned-app-01",
        "status": "RESPONSE_OBSERVED_CLOSED",
        "request_line_utf8": '{"T":105}\n',
        "response_line_utf8": json.dumps(response, separators=(",", ":")) + "\n",
        "request_count": 1, "write_attempt_count": 1,
        "confirmed_write_bytes": 10, "automatic_retry_count": 0,
        "response_count": 1, "cleanup_confirmed": True,
        "motion_command_count": 0,
        "started_at": "2026-10-25T14:01:00-04:00",
        "finished_at": "2026-10-25T14:01:01-04:00", "errors": [],
    }


def worker_factory(child_status="SUCCEEDED"):
    calls = []

    class Worker:
        def __init__(self, registration, *, authorizer, _clock):
            self.registration = registration
            self.authorizer = authorizer
            self.clock = _clock

        def run(self, request, *, cancellation, deadline_ns):
            from rocell.providers.windows.owned_worker_process import owned_request_wire
            wire, digest = owned_request_wire(
                self.registration, request, deadline_ns=deadline_ns
            )
            self.authorizer(self.registration, request, digest)
            calls.append(request)
            decoded = decode_request(wire)
            export_directory = (
                self.registration.working_directory
                / "exports" / ("position-vector-feedback-" + request.attempt_id)
            )
            export_directory.mkdir()
            files = []
            for name, raw in (
                ("header.json", b"{}\n"),
                ("events.jsonl", b"{}\n"),
                ("result.json", b"{}\n"),
            ):
                (export_directory / name).write_bytes(raw)
                files.append(
                    {"name": name, "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest()}
                )
            journal_export = {
                "schema": "rocell.position_vector_feedback_serial_attempt_export.v1",
                "attempt_directory_name": (
                    "position-vector-feedback-" + request.attempt_id
                ),
                "recovery_disposition": "TERMINAL_NO_REPLAY",
                "request_sha256": hashlib.sha256(
                    canonical(decoded["payload"]["binding"]["request"])
                ).hexdigest(),
                "event_count": 1,
                "files": files,
                "automatic_retry_allowed": False,
                "motion_authorized": False,
                "physical_authority": False,
            }
            (export_directory / "manifest.json").write_bytes(
                canonical(journal_export) + b"\n"
            )
            parsed = {
                "schema": "rocell.owned_calibrated_position_vector_result.v1",
                "attempt_id": request.attempt_id,
                "request_sha256": digest,
                "child_result": {
                    "schema": (
                        "rocell.calibrated_position_vector_native_child_result.v1"
                    ),
                    "status": child_status,
                    "error": None if child_status == "SUCCEEDED" else "SHORT_WRITE_NO_RETRY",
                    "exchange_evidence": evidence() if child_status == "SUCCEEDED" else None,
                    "binding_sha256": request.operation_sha256,
                    "journal_export": {
                        **journal_export,
                        "export_directory": str(export_directory.resolve()),
                    },
                    "physical_authority": False,
                    "motion_authorized": False,
                    "automatic_retry_allowed": False,
                    "connected": False,
                },
                "physical_authority": False,
                "motion_authorized": False,
                "automatic_retry_allowed": False,
                "connected": False,
            }
            return OwnedWorkerResult(
                "SUCCEEDED" if child_status == "SUCCEEDED" else "FAILED",
                None if child_status == "SUCCEEDED" else "SHORT_WRITE_NO_RETRY",
                (), digest, request.attempt_id, True, True, True,
                0 if child_status == "SUCCEEDED" else 1, 1, 1, 1, 1,
                b"{}", b"", parsed, 42, self.clock(),
            )

    return Worker, calls


def run(tmp_path, monkeypatch, *, child_status="SUCCEEDED"):
    artifact, approval, prerequisites = inputs(monkeypatch)
    worker, calls = worker_factory(child_status)
    monkeypatch.setattr(
        subject, "verify_exported_journal", lambda value, **_: value
    )
    times = iter(("2026-10-25T14:00:30-04:00", "2026-10-25T14:01:02-04:00"))
    result = subject.run_owned_qualified_calibrated_feedback_request(
        tmp_path.resolve(),
        feedback_request_execution_approval_receipt_document=approval,
        execution_prerequisites_document=prerequisites,
        calibration_document=artifact,
        approval_arguments={}, reviewed_controller=reviewed(), fresh_identity=identity(),
        installed_firmware_sha256=FIRMWARE_SHA, source_sha256=SOURCE_SHA,
        expires_monotonic_ns=2_000_000_000, cancellation=threading.Event(),
        check_current=lambda: None, wall_clock=lambda: next(times),
        monotonic_clock=lambda: 1_000_000_000, _worker_factory=worker,
    )
    return result, calls


def test_runs_once_retains_claim_and_completes_calibrated_receipt(tmp_path, monkeypatch):
    result, calls = run(tmp_path, monkeypatch)

    assert result.stage == "COMPLETED"
    assert len(calls) == 1
    assert result.execution_receipt["calibrated_feedback_conversion_accepted"] is True
    assert result.execution_receipt["motion_authorized"] is False
    claim = json.loads((result.working_directory / "application-claim.json").read_text())
    assert claim["schema"] == subject.CLAIM_SCHEMA
    assert claim["automatic_retry_allowed"] is False
    assert (result.working_directory / "supervisor-request.json").is_file()
    assert (result.working_directory / "supervisor-result.json").is_file()


def test_terminal_child_failure_is_retained_without_retry_or_receipt(tmp_path, monkeypatch):
    result, calls = run(tmp_path, monkeypatch, child_status="FAILED_NO_RETRY")

    assert result.stage == "RETAINED_FAILED_NO_RETRY"
    assert result.execution_receipt is None
    assert result.error_type == "SHORT_WRITE_NO_RETRY"
    assert len(calls) == 1
    assert result.automatic_retry_allowed is False


def test_attempt_directory_is_a_single_use_redemption_boundary(tmp_path, monkeypatch):
    first, _ = run(tmp_path, monkeypatch)
    assert first.stage == "COMPLETED"

    second, calls = run(tmp_path, monkeypatch)
    assert second.stage == "PREPARATION_FAILED"
    assert second.error_type == "FileExistsError"
    assert calls == []


def test_stale_prerequisites_fail_before_staging_or_dispatch(tmp_path, monkeypatch):
    artifact, approval, prerequisites = inputs(monkeypatch)
    worker, calls = worker_factory()
    result = subject.run_owned_qualified_calibrated_feedback_request(
        tmp_path.resolve(),
        feedback_request_execution_approval_receipt_document=approval,
        execution_prerequisites_document=prerequisites,
        calibration_document=artifact,
        approval_arguments={}, reviewed_controller=reviewed(), fresh_identity=identity(),
        installed_firmware_sha256=FIRMWARE_SHA, source_sha256=SOURCE_SHA,
        expires_monotonic_ns=2_000_000_000, cancellation=threading.Event(),
        check_current=lambda: None,
        wall_clock=lambda: "2026-10-25T14:06:00-04:00",
        monotonic_clock=lambda: 1_000_000_000, _worker_factory=worker,
    )
    assert result.stage == "PREPARATION_FAILED"
    assert result.working_directory is None
    assert calls == []


def test_independent_review_reproduces_retained_execution(tmp_path, monkeypatch):
    result, _ = run(tmp_path, monkeypatch)
    artifact = calibration()
    basis = review.build_calibrated_position_vector_execution_review_basis(
        result.working_directory,
        execution_receipt_document=result.execution_receipt,
        calibration_document=artifact,
    )
    review_document = {
        "schema": review.REVIEW_SCHEMA,
        "decision": "ACCEPT",
        "reviewer_id": "independent-reviewer-01",
        "reviewed_at": "2026-10-25T14:02:00-04:00",
        **{field: basis[field] for field in (
            "execution_receipt_sha256", "application_claim_sha256",
            "supervisor_request_sha256", "supervisor_result_sha256",
            "journal_manifest_sha256", "calibration_sha256",
        )},
        "review_notes_sha256": "9" * 64,
    }

    receipt = review.review_calibrated_position_vector_execution(
        result.working_directory,
        execution_receipt_document=result.execution_receipt,
        calibration_document=artifact,
        review_document=review_document,
    )

    assert receipt["status"] == (
        "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_ACCEPTED"
    )
    assert receipt["calibrated_feedback"] == result.execution_receipt[
        "calibrated_feedback"
    ]
    assert receipt["calibrated_feedback_observation_accepted"] is True
    assert receipt["motion_authorized"] is False

    review_document["decision"] = "REJECT"
    rejected = review.review_calibrated_position_vector_execution(
        result.working_directory,
        execution_receipt_document=result.execution_receipt,
        calibration_document=artifact,
        review_document=review_document,
    )
    assert rejected["status"] == (
        "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_REJECTED"
    )
    assert rejected["calibrated_feedback"] is None
    assert rejected["calibrated_feedback_observation_accepted"] is False


def test_execution_review_rejects_crossed_or_nonindependent_evidence(
    tmp_path, monkeypatch
):
    result, _ = run(tmp_path, monkeypatch)
    artifact = calibration()
    basis = review.build_calibrated_position_vector_execution_review_basis(
        result.working_directory,
        execution_receipt_document=result.execution_receipt,
        calibration_document=artifact,
    )
    document = {
        "schema": review.REVIEW_SCHEMA,
        "decision": "REJECT",
        "reviewer_id": result.execution_receipt["operator_id"],
        "reviewed_at": "2026-10-25T14:02:00-04:00",
        **{field: basis[field] for field in (
            "execution_receipt_sha256", "application_claim_sha256",
            "supervisor_request_sha256", "supervisor_result_sha256",
            "journal_manifest_sha256", "calibration_sha256",
        )},
        "review_notes_sha256": "9" * 64,
    }
    try:
        review.review_calibrated_position_vector_execution(
            result.working_directory,
            execution_receipt_document=result.execution_receipt,
            calibration_document=artifact,
            review_document=document,
        )
    except review.CalibratedPositionVectorExecutionReviewError as error:
        assert "independent" in str(error)
    else:
        raise AssertionError("operator was accepted as independent reviewer")

    document["reviewer_id"] = "independent-reviewer-01"
    document["supervisor_result_sha256"] = "0" * 64
    try:
        review.review_calibrated_position_vector_execution(
            result.working_directory,
            execution_receipt_document=result.execution_receipt,
            calibration_document=artifact,
            review_document=document,
        )
    except review.CalibratedPositionVectorExecutionReviewError as error:
        assert "supervisor_result_sha256" in str(error)
    else:
        raise AssertionError("crossed retained result was accepted")
