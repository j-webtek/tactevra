import hashlib
import json
import threading

from rocell.application import calibrated_position_vector_feedback_execution as execution
from rocell.application import calibrated_position_vector_execution_review as review
from rocell.application import calibrated_position_vector_observation_admission as admission
from rocell.application import calibrated_position_vector_observation_redemption as redemption
from rocell.application import calibrated_position_vector_state_ingestion as ingestion
from rocell.application import calibrated_position_vector_state_snapshot_read_admission as snapshot_read
from rocell.application import camera_feedback_state_fusion_admission as fusion
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
CONSUMER_CONTEXT = {
    "schema": "rocell.test_joint_state_consumer_context.v1",
    "consumer_id": "joint-state-estimator-01",
    "state_epoch": "state-epoch-01",
}
READER_CONTEXT = {
    "schema": "rocell.test_camera_state_fusion_reader_context.v1",
    "reader_id": "camera-state-fusion-01",
    "pipeline_epoch": "fusion-epoch-01",
    "purpose": "camera_feedback_state_fusion",
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


def accepted_review_receipt(tmp_path, monkeypatch):
    result, _ = run(tmp_path, monkeypatch)
    artifact = calibration()
    basis = review.build_calibrated_position_vector_execution_review_basis(
        result.working_directory,
        execution_receipt_document=result.execution_receipt,
        calibration_document=artifact,
    )
    document = {
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
        review_document=document,
    )
    return result.execution_receipt, receipt


def admission_document(execution_receipt, review_receipt):
    return {
        "schema": admission.ADMISSION_SCHEMA,
        "consumer_id": "joint-state-estimator-01",
        "consumer_context_sha256": canonical_sha256(CONSUMER_CONTEXT),
        "admitted_at": "2026-10-25T14:02:10-04:00",
        "valid_until": "2026-10-25T14:03:00-04:00",
        "review_receipt_sha256": canonical_sha256(review_receipt),
        "execution_receipt_sha256": canonical_sha256(execution_receipt),
        "calibration_sha256": review_receipt["calibration_sha256"],
        "controller_binding_sha256": execution_receipt[
            "controller_binding_sha256"
        ],
        "attempt_id": execution_receipt["attempt_id"],
        "runtime_session_id": execution_receipt["runtime_session_id"],
        "calibration_id": execution_receipt["calibration_id"],
        "attachment_profile": execution_receipt["attachment_profile"],
        "freshness_policy": {
            "maximum_observation_age_seconds": 180,
            "maximum_admission_lifetime_seconds": 60,
        },
    }


def admitted_receipt(tmp_path, monkeypatch):
    execution_receipt, review_receipt = accepted_review_receipt(
        tmp_path, monkeypatch
    )
    return admission.admit_calibrated_position_vector_observation(
        execution_receipt_document=execution_receipt,
        review_receipt_document=review_receipt,
        admission_document=admission_document(
            execution_receipt, review_receipt
        ),
        consumer_context_document=CONSUMER_CONTEXT,
        current_calibration_document=calibration(),
        current_controller_binding_document=CONTROLLER,
        current_attachment_profile="no_attachment",
    )


def redeemed_receipt(tmp_path, monkeypatch):
    admitted = admitted_receipt(tmp_path, monkeypatch)
    redemption_root = tmp_path / "redemptions"
    redemption_root.mkdir()
    return redemption.redeem_calibrated_position_vector_observation(
        redemption_root.resolve(),
        admission_receipt_document=admitted,
        consumer_id="joint-state-estimator-01",
        consumer_context_document=CONSUMER_CONTEXT,
        redeemed_at="2026-10-25T14:02:20-04:00",
    )


def ingested_receipt(tmp_path, monkeypatch):
    redeemed = redeemed_receipt(tmp_path, monkeypatch)
    state_root = tmp_path / "consumer-state"
    state_root.mkdir()
    receipt = ingestion.ingest_calibrated_position_vector_state(
        state_root.resolve(),
        redemption_receipt_document=redeemed,
        consumer_id="joint-state-estimator-01",
        consumer_context_document=CONSUMER_CONTEXT,
        ingested_at="2026-10-25T14:02:21-04:00",
    )
    return state_root, receipt


def snapshot_admission_document(ingested):
    return {
        "schema": snapshot_read.SNAPSHOT_READ_ADMISSION_SCHEMA,
        "reader_id": "camera-state-fusion-01",
        "reader_context_sha256": canonical_sha256(READER_CONTEXT),
        "consumer_id": "joint-state-estimator-01",
        "consumer_context_sha256": canonical_sha256(CONSUMER_CONTEXT),
        "state_ingestion_receipt_sha256": canonical_sha256(ingested),
        "calibration_sha256": canonical_sha256(calibration()),
        "controller_binding_sha256": canonical_sha256(CONTROLLER),
        "calibration_id": calibration()["calibration_id"],
        "attachment_profile": "no_attachment",
        "admitted_at": "2026-10-25T14:02:30-04:00",
        "valid_until": "2026-10-25T14:02:50-04:00",
        "freshness_policy": {
            "maximum_snapshot_age_seconds": 180,
            "maximum_read_lifetime_seconds": 30,
        },
    }


def test_admits_reviewed_observation_to_one_named_consumer(tmp_path, monkeypatch):
    execution_receipt, review_receipt = accepted_review_receipt(
        tmp_path, monkeypatch
    )
    document = admission_document(execution_receipt, review_receipt)

    receipt = admission.admit_calibrated_position_vector_observation(
        execution_receipt_document=execution_receipt,
        review_receipt_document=review_receipt,
        admission_document=document,
        consumer_context_document=CONSUMER_CONTEXT,
        current_calibration_document=calibration(),
        current_controller_binding_document=CONTROLLER,
        current_attachment_profile="no_attachment",
    )

    assert receipt["status"] == (
        "CALIBRATED_POSITION_VECTOR_OBSERVATION_STATE_ADMITTED"
    )
    assert receipt["consumer_id"] == "joint-state-estimator-01"
    assert receipt["calibrated_feedback"] == execution_receipt[
        "calibrated_feedback"
    ]
    assert receipt["named_consumer_state_use_authorized"] is True
    assert receipt["motion_authorized"] is False
    assert receipt["physical_authority"] is False


def test_admission_rejects_stale_crossed_or_rejected_review(tmp_path, monkeypatch):
    execution_receipt, review_receipt = accepted_review_receipt(
        tmp_path, monkeypatch
    )
    document = admission_document(execution_receipt, review_receipt)
    document["admitted_at"] = "2026-10-25T14:05:00-04:00"
    document["valid_until"] = "2026-10-25T14:05:01-04:00"
    try:
        admission.admit_calibrated_position_vector_observation(
            execution_receipt_document=execution_receipt,
            review_receipt_document=review_receipt,
            admission_document=document,
            consumer_context_document=CONSUMER_CONTEXT,
            current_calibration_document=calibration(),
            current_controller_binding_document=CONTROLLER,
            current_attachment_profile="no_attachment",
        )
    except admission.CalibratedPositionVectorObservationAdmissionError as error:
        assert "stale" in str(error)
    else:
        raise AssertionError("stale observation was admitted")

    document = admission_document(execution_receipt, review_receipt)
    document["execution_receipt_sha256"] = "0" * 64
    try:
        admission.admit_calibrated_position_vector_observation(
            execution_receipt_document=execution_receipt,
            review_receipt_document=review_receipt,
            admission_document=document,
            consumer_context_document=CONSUMER_CONTEXT,
            current_calibration_document=calibration(),
            current_controller_binding_document=CONTROLLER,
            current_attachment_profile="no_attachment",
        )
    except admission.CalibratedPositionVectorObservationAdmissionError as error:
        assert "execution_receipt_sha256" in str(error)
    else:
        raise AssertionError("crossed execution receipt was admitted")

    document = admission_document(execution_receipt, review_receipt)
    changed_consumer_context = {**CONSUMER_CONTEXT, "state_epoch": "state-epoch-02"}
    try:
        admission.admit_calibrated_position_vector_observation(
            execution_receipt_document=execution_receipt,
            review_receipt_document=review_receipt,
            admission_document=document,
            consumer_context_document=changed_consumer_context,
            current_calibration_document=calibration(),
            current_controller_binding_document=CONTROLLER,
            current_attachment_profile="no_attachment",
        )
    except admission.CalibratedPositionVectorObservationAdmissionError as error:
        assert "consumer_context_sha256" in str(error)
    else:
        raise AssertionError("changed consumer context was admitted")

    document = admission_document(execution_receipt, review_receipt)
    changed_controller = {**CONTROLLER, "unit_serial": "DIFFERENT-CONTROLLER"}
    try:
        admission.admit_calibrated_position_vector_observation(
            execution_receipt_document=execution_receipt,
            review_receipt_document=review_receipt,
            admission_document=document,
            consumer_context_document=CONSUMER_CONTEXT,
            current_calibration_document=calibration(),
            current_controller_binding_document=changed_controller,
            current_attachment_profile="no_attachment",
        )
    except admission.CalibratedPositionVectorObservationAdmissionError as error:
        assert "controller_binding_sha256" in str(error)
    else:
        raise AssertionError("changed controller was admitted")

    rejected = dict(review_receipt)
    rejected["status"] = "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_REJECTED"
    rejected["decision"] = "REJECT"
    rejected["calibrated_feedback_observation_accepted"] = False
    rejected["calibrated_feedback"] = None
    rejected["next_required_gate"] = (
        "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_REMEDIATION"
    )
    document = admission_document(execution_receipt, rejected)
    try:
        admission.admit_calibrated_position_vector_observation(
            execution_receipt_document=execution_receipt,
            review_receipt_document=rejected,
            admission_document=document,
            consumer_context_document=CONSUMER_CONTEXT,
            current_calibration_document=calibration(),
            current_controller_binding_document=CONTROLLER,
            current_attachment_profile="no_attachment",
        )
    except admission.CalibratedPositionVectorObservationAdmissionError as error:
        assert "not accepted" in str(error)
    else:
        raise AssertionError("rejected observation was admitted")


def test_named_consumer_redeems_admitted_observation_once(tmp_path, monkeypatch):
    admitted = admitted_receipt(tmp_path, monkeypatch)
    redemption_root = tmp_path / "redemptions"
    redemption_root.mkdir()

    receipt = redemption.redeem_calibrated_position_vector_observation(
        redemption_root.resolve(),
        admission_receipt_document=admitted,
        consumer_id="joint-state-estimator-01",
        consumer_context_document=CONSUMER_CONTEXT,
        redeemed_at="2026-10-25T14:02:20-04:00",
    )

    assert receipt["status"] == (
        "CALIBRATED_POSITION_VECTOR_OBSERVATION_REDEEMED"
    )
    assert receipt["calibrated_feedback"] == admitted["calibrated_feedback"]
    assert receipt["calibrated_feedback_observation_redeemed_once"] is True
    assert receipt["redemption_replay_allowed"] is False
    assert receipt["motion_authorized"] is False
    retained = list(redemption_root.iterdir())
    assert len(retained) == 1
    assert json.loads(retained[0].read_text(encoding="utf-8")) == receipt

    try:
        redemption.redeem_calibrated_position_vector_observation(
            redemption_root.resolve(),
            admission_receipt_document=admitted,
            consumer_id="joint-state-estimator-01",
            consumer_context_document=CONSUMER_CONTEXT,
            redeemed_at="2026-10-25T14:02:21-04:00",
        )
    except redemption.CalibratedPositionVectorObservationRedemptionError as error:
        assert "already redeemed" in str(error)
    else:
        raise AssertionError("admission was redeemed twice")


def test_named_consumer_redemption_is_exclusive_under_concurrency(
    tmp_path, monkeypatch
):
    admitted = admitted_receipt(tmp_path, monkeypatch)
    redemption_root = tmp_path / "redemptions"
    redemption_root.mkdir()
    barrier = threading.Barrier(2)
    receipts = []
    errors = []

    def redeem() -> None:
        barrier.wait()
        try:
            receipts.append(
                redemption.redeem_calibrated_position_vector_observation(
                    redemption_root.resolve(),
                    admission_receipt_document=admitted,
                    consumer_id="joint-state-estimator-01",
                    consumer_context_document=CONSUMER_CONTEXT,
                    redeemed_at="2026-10-25T14:02:20-04:00",
                )
            )
        except redemption.CalibratedPositionVectorObservationRedemptionError as error:
            errors.append(error)

    threads = [threading.Thread(target=redeem) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(receipts) == 1
    assert len(errors) == 1
    assert "already redeemed" in str(errors[0])
    assert len(list(redemption_root.iterdir())) == 1


def test_named_consumer_redemption_rejects_stale_or_changed_context(
    tmp_path, monkeypatch
):
    admitted = admitted_receipt(tmp_path, monkeypatch)
    redemption_root = tmp_path / "redemptions"
    redemption_root.mkdir()

    for context, consumed_at, expected in (
        (
            {**CONSUMER_CONTEXT, "state_epoch": "state-epoch-02"},
            "2026-10-25T14:02:20-04:00",
            "consumer context differs",
        ),
        (CONSUMER_CONTEXT, "2026-10-25T14:03:00-04:00", "not fresh"),
    ):
        try:
            redemption.redeem_calibrated_position_vector_observation(
                redemption_root.resolve(),
                admission_receipt_document=admitted,
                consumer_id="joint-state-estimator-01",
                consumer_context_document=context,
                redeemed_at=consumed_at,
            )
        except redemption.CalibratedPositionVectorObservationRedemptionError as error:
            assert expected in str(error)
        else:
            raise AssertionError("ineligible admission was redeemed")

    crossed = dict(admitted)
    crossed["consumer_id"] = "different-consumer"
    try:
        redemption.redeem_calibrated_position_vector_observation(
            redemption_root.resolve(),
            admission_receipt_document=crossed,
            consumer_id="joint-state-estimator-01",
            consumer_context_document=CONSUMER_CONTEXT,
            redeemed_at="2026-10-25T14:02:20-04:00",
        )
    except redemption.CalibratedPositionVectorObservationRedemptionError as error:
        assert "consumer_id mismatch" in str(error)
    else:
        raise AssertionError("crossed consumer admission was redeemed")

    assert not list(redemption_root.iterdir())


def test_named_consumer_state_ingestion_is_idempotent(tmp_path, monkeypatch):
    redeemed = redeemed_receipt(tmp_path, monkeypatch)
    state_root = tmp_path / "consumer-state"
    state_root.mkdir()

    first = ingestion.ingest_calibrated_position_vector_state(
        state_root.resolve(),
        redemption_receipt_document=redeemed,
        consumer_id="joint-state-estimator-01",
        consumer_context_document=CONSUMER_CONTEXT,
        ingested_at="2026-10-25T14:02:21-04:00",
    )
    repeated = ingestion.ingest_calibrated_position_vector_state(
        state_root.resolve(),
        redemption_receipt_document=redeemed,
        consumer_id="joint-state-estimator-01",
        consumer_context_document=CONSUMER_CONTEXT,
        ingested_at="2026-10-25T15:00:00-04:00",
    )

    assert repeated == first
    assert first["status"] == "CALIBRATED_POSITION_VECTOR_STATE_INGESTED"
    assert first["calibrated_feedback"] == redeemed["calibrated_feedback"]
    assert first["duplicate_delivery_idempotent"] is True
    assert first["motion_authorized"] is False
    retained = list(state_root.iterdir())
    assert len(retained) == 1
    assert json.loads(retained[0].read_text(encoding="utf-8")) == first


def test_named_consumer_state_ingestion_converges_under_concurrency(
    tmp_path, monkeypatch
):
    redeemed = redeemed_receipt(tmp_path, monkeypatch)
    state_root = tmp_path / "consumer-state"
    state_root.mkdir()
    barrier = threading.Barrier(2)
    receipts = []
    errors = []

    def ingest(observed_at: str) -> None:
        barrier.wait()
        try:
            receipts.append(
                ingestion.ingest_calibrated_position_vector_state(
                    state_root.resolve(),
                    redemption_receipt_document=redeemed,
                    consumer_id="joint-state-estimator-01",
                    consumer_context_document=CONSUMER_CONTEXT,
                    ingested_at=observed_at,
                )
            )
        except ingestion.CalibratedPositionVectorStateIngestionError as error:
            errors.append(error)

    threads = [
        threading.Thread(
            target=ingest, args=(f"2026-10-25T14:02:2{index}-04:00",)
        )
        for index in (1, 2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(receipts) == 2
    assert receipts[0] == receipts[1]
    assert len(list(state_root.iterdir())) == 1


def test_named_consumer_state_ingestion_rejects_changed_or_stale_delivery(
    tmp_path, monkeypatch
):
    redeemed = redeemed_receipt(tmp_path, monkeypatch)
    state_root = tmp_path / "consumer-state"
    state_root.mkdir()

    try:
        ingestion.ingest_calibrated_position_vector_state(
            state_root.resolve(),
            redemption_receipt_document=redeemed,
            consumer_id="joint-state-estimator-01",
            consumer_context_document=CONSUMER_CONTEXT,
            ingested_at="2026-10-25T14:03:00-04:00",
        )
    except ingestion.CalibratedPositionVectorStateIngestionError as error:
        assert "not fresh" in str(error)
    else:
        raise AssertionError("stale redemption was first-ingested")

    original = ingestion.ingest_calibrated_position_vector_state(
        state_root.resolve(),
        redemption_receipt_document=redeemed,
        consumer_id="joint-state-estimator-01",
        consumer_context_document=CONSUMER_CONTEXT,
        ingested_at="2026-10-25T14:02:21-04:00",
    )
    changed = dict(redeemed)
    changed["calibrated_feedback"] = {
        **redeemed["calibrated_feedback"], "pose": "CHANGED"
    }
    try:
        ingestion.ingest_calibrated_position_vector_state(
            state_root.resolve(),
            redemption_receipt_document=changed,
            consumer_id="joint-state-estimator-01",
            consumer_context_document=CONSUMER_CONTEXT,
            ingested_at="2026-10-25T14:02:22-04:00",
        )
    except ingestion.CalibratedPositionVectorStateIngestionError as error:
        assert "different payload" in str(error)
    else:
        raise AssertionError("changed payload reused an ingested redemption_id")

    assert ingestion.ingest_calibrated_position_vector_state(
        state_root.resolve(),
        redemption_receipt_document=redeemed,
        consumer_id="joint-state-estimator-01",
        consumer_context_document=CONSUMER_CONTEXT,
        ingested_at="2026-10-25T14:02:22-04:00",
    ) == original

    try:
        ingestion.ingest_calibrated_position_vector_state(
            state_root.resolve(),
            redemption_receipt_document=redeemed,
            consumer_id="joint-state-estimator-01",
            consumer_context_document={
                **CONSUMER_CONTEXT, "state_epoch": "state-epoch-02"
            },
            ingested_at="2026-10-25T14:02:22-04:00",
        )
    except ingestion.CalibratedPositionVectorStateIngestionError as error:
        assert "consumer context differs" in str(error)
    else:
        raise AssertionError("changed consumer context read stored state")

    retained = next(state_root.iterdir())
    tampered = json.loads(retained.read_text(encoding="utf-8"))
    tampered["calibrated_feedback"] = {
        **tampered["calibrated_feedback"], "pose": "TAMPERED"
    }
    retained.write_bytes(canonical(tampered) + b"\n")
    try:
        ingestion.ingest_calibrated_position_vector_state(
            state_root.resolve(),
            redemption_receipt_document=redeemed,
            consumer_id="joint-state-estimator-01",
            consumer_context_document=CONSUMER_CONTEXT,
            ingested_at="2026-10-25T14:02:23-04:00",
        )
    except ingestion.CalibratedPositionVectorStateIngestionError as error:
        assert "differs from the original result" in str(error)
    else:
        raise AssertionError("tampered stored state was returned")


def test_admits_stored_state_snapshot_to_one_named_reader(tmp_path, monkeypatch):
    state_root, ingested = ingested_receipt(tmp_path, monkeypatch)
    receipt = snapshot_read.admit_calibrated_state_snapshot_read(
        state_root.resolve(),
        state_ingestion_receipt_document=ingested,
        admission_document=snapshot_admission_document(ingested),
        reader_context_document=READER_CONTEXT,
        current_consumer_context_document=CONSUMER_CONTEXT,
        current_calibration_document=calibration(),
        current_controller_binding_document=CONTROLLER,
        current_attachment_profile="no_attachment",
    )

    assert receipt["status"] == "CALIBRATED_STATE_SNAPSHOT_READ_ADMITTED"
    assert receipt["reader_id"] == "camera-state-fusion-01"
    assert receipt["calibrated_feedback"] == ingested["calibrated_feedback"]
    assert receipt["named_reader_snapshot_use_authorized"] is True
    assert receipt["next_required_gate"] == (
        "CAMERA_FEEDBACK_STATE_FUSION_ADMISSION"
    )
    assert receipt["motion_authorized"] is False
    assert receipt["physical_authority"] is False


def test_snapshot_read_rejects_changed_reader_or_current_profile(
    tmp_path, monkeypatch
):
    state_root, ingested = ingested_receipt(tmp_path, monkeypatch)
    document = snapshot_admission_document(ingested)
    cases = (
        (
            {**READER_CONTEXT, "pipeline_epoch": "fusion-epoch-02"},
            CONSUMER_CONTEXT, calibration(), CONTROLLER, "no_attachment",
            "reader context differs",
        ),
        (
            READER_CONTEXT,
            {**CONSUMER_CONTEXT, "state_epoch": "state-epoch-02"},
            calibration(), CONTROLLER, "no_attachment",
            "consumer context differs",
        ),
        (
            READER_CONTEXT, CONSUMER_CONTEXT,
            {**calibration(), "calibration_id": "different-calibration"},
            CONTROLLER, "no_attachment", "calibration differs",
        ),
        (
            READER_CONTEXT, CONSUMER_CONTEXT, calibration(),
            {**CONTROLLER, "unit_serial": "DIFFERENT-CONTROLLER"},
            "no_attachment", "controller binding differs",
        ),
        (
            READER_CONTEXT, CONSUMER_CONTEXT, calibration(), CONTROLLER,
            "stylus_attachment", "attachment profile differs",
        ),
    )
    for reader_context, consumer_context, artifact, controller, profile, expected in cases:
        try:
            snapshot_read.admit_calibrated_state_snapshot_read(
                state_root.resolve(),
                state_ingestion_receipt_document=ingested,
                admission_document=document,
                reader_context_document=reader_context,
                current_consumer_context_document=consumer_context,
                current_calibration_document=artifact,
                current_controller_binding_document=controller,
                current_attachment_profile=profile,
            )
        except snapshot_read.CalibratedStateSnapshotReadAdmissionError as error:
            assert expected in str(error)
        else:
            raise AssertionError("changed reader or current profile was admitted")


def test_snapshot_read_rejects_stale_crossed_or_tampered_state(
    tmp_path, monkeypatch
):
    state_root, ingested = ingested_receipt(tmp_path, monkeypatch)
    stale = snapshot_admission_document(ingested)
    stale["admitted_at"] = "2026-10-25T14:10:00-04:00"
    stale["valid_until"] = "2026-10-25T14:10:20-04:00"
    crossed = snapshot_admission_document(ingested)
    crossed["state_ingestion_receipt_sha256"] = "0" * 64

    for document, expected in (
        (stale, "freshness policy"),
        (crossed, "state_ingestion_receipt_sha256"),
    ):
        try:
            snapshot_read.admit_calibrated_state_snapshot_read(
                state_root.resolve(),
                state_ingestion_receipt_document=ingested,
                admission_document=document,
                reader_context_document=READER_CONTEXT,
                current_consumer_context_document=CONSUMER_CONTEXT,
                current_calibration_document=calibration(),
                current_controller_binding_document=CONTROLLER,
                current_attachment_profile="no_attachment",
            )
        except snapshot_read.CalibratedStateSnapshotReadAdmissionError as error:
            assert expected in str(error)
        else:
            raise AssertionError("stale or crossed snapshot read was admitted")

    retained = next(state_root.iterdir())
    tampered = json.loads(retained.read_text(encoding="utf-8"))
    tampered["calibrated_feedback"] = {
        **tampered["calibrated_feedback"], "pose": "TAMPERED"
    }
    retained.write_bytes(canonical(tampered) + b"\n")
    try:
        snapshot_read.admit_calibrated_state_snapshot_read(
            state_root.resolve(),
            state_ingestion_receipt_document=ingested,
            admission_document=snapshot_admission_document(ingested),
            reader_context_document=READER_CONTEXT,
            current_consumer_context_document=CONSUMER_CONTEXT,
            current_calibration_document=calibration(),
            current_controller_binding_document=CONTROLLER,
            current_attachment_profile="no_attachment",
        )
    except snapshot_read.CalibratedStateSnapshotReadAdmissionError as error:
        assert "differs from the selected receipt" in str(error)
    else:
        raise AssertionError("tampered stored state was admitted for reading")


def _snapshot_receipt(tmp_path, monkeypatch):
    state_root, ingested = ingested_receipt(tmp_path, monkeypatch)
    return snapshot_read.admit_calibrated_state_snapshot_read(
        state_root.resolve(),
        state_ingestion_receipt_document=ingested,
        admission_document=snapshot_admission_document(ingested),
        reader_context_document=READER_CONTEXT,
        current_consumer_context_document=CONSUMER_CONTEXT,
        current_calibration_document=calibration(),
        current_controller_binding_document=CONTROLLER,
        current_attachment_profile="no_attachment",
    )


def _camera_observation():
    return {
        "schema": fusion.CAMERA_OBSERVATION_SCHEMA,
        "source_hashes": {
            "camera_intrinsics_sha256": "8" * 64,
            "tag_map_sha256": "9" * 64,
        },
        "quality": {"passed": True},
        "authority": {
            "physical_authority": "NONE",
            "physical_commands_generated": 0,
            "can_authorize_motion": False,
            "can_release_physical_gates": False,
        },
        "board_pose": {"translation_mm": [10.0, 20.0, 0.0]},
    }


def _camera_calibration(registration=None):
    registration = registration or _board_registration()
    return {
        "schema": "rocell.camera_fusion_calibration_binding.v1",
        "status": "CAMERA_FUSION_CALIBRATION_READY",
        "camera_intrinsics_sha256": "8" * 64,
        "tag_map_sha256": "9" * 64,
        "board_registration_sha256": canonical_sha256(registration),
        "safe_for_runtime_observation_fusion": True,
        "motion_authorized": False,
    }


def _board_registration():
    return {
        "schema": fusion.BOARD_REGISTRATION_SCHEMA,
        "status": "ABSOLUTE_KEYBOARD_TO_BOARD_LOCALIZATION_READY",
        "profile": "no_attachment",
        "absolute_keyboard_to_board_transform_verified": True,
        "board_space_key_candidates_emitted": True,
        "motion_targets_emitted": False,
        "motion_authorized": False,
        "contact_authorized": False,
    }


def _fusion_admission(snapshot):
    observation = _camera_observation()
    registration = _board_registration()
    camera_calibration = _camera_calibration(registration)
    return {
        "schema": fusion.FUSION_ADMISSION_SCHEMA,
        "fusion_consumer_id": "camera-state-fusion-01",
        "fusion_context_sha256": canonical_sha256(READER_CONTEXT),
        "snapshot_read_receipt_sha256": canonical_sha256(snapshot),
        "camera_observation_sha256": canonical_sha256(observation),
        "camera_calibration_sha256": canonical_sha256(camera_calibration),
        "board_registration_sha256": canonical_sha256(registration),
        "attachment_profile": "no_attachment",
        "camera_observed_at": snapshot["executed_at"],
        "fused_at": "2026-10-25T14:02:31-04:00",
        "valid_until": "2026-10-25T14:02:45-04:00",
        "maximum_camera_state_skew_seconds": 1,
        "maximum_fusion_lifetime_seconds": 20,
    }


def _admit_fusion(snapshot, document=None, **overrides):
    values = {
        "snapshot_read_receipt_document": snapshot,
        "camera_observation_document": _camera_observation(),
        "camera_calibration_document": _camera_calibration(),
        "board_registration_document": _board_registration(),
        "admission_document": document or _fusion_admission(snapshot),
        "fusion_context_document": READER_CONTEXT,
        "current_attachment_profile": "no_attachment",
    }
    values.update(overrides)
    return fusion.admit_camera_feedback_state_fusion(**values)


def test_admits_camera_observation_and_exact_state_snapshot_for_fusion(
    tmp_path, monkeypatch
):
    snapshot = _snapshot_receipt(tmp_path, monkeypatch)
    receipt = _admit_fusion(snapshot)

    assert receipt["status"] == "CAMERA_FEEDBACK_STATE_FUSION_ADMITTED"
    assert receipt["snapshot_id"] == snapshot["snapshot_id"]
    assert receipt["calibrated_feedback"] == snapshot["calibrated_feedback"]
    assert receipt["camera_observation"] == _camera_observation()
    assert receipt["next_required_gate"] == (
        "FUSED_CAMERA_STATE_PLANNING_ADMISSION"
    )
    assert receipt["planning_authorized"] is False
    assert receipt["motion_authorized"] is False
    assert receipt["physical_authority"] is False


def test_fusion_rejects_crossed_camera_calibration_registration_or_snapshot(
    tmp_path, monkeypatch
):
    snapshot = _snapshot_receipt(tmp_path, monkeypatch)
    cases = (
        (
            {"camera_calibration_document": {
                **_camera_calibration(), "camera_intrinsics_sha256": "0" * 64
            }},
            "intrinsics differ",
        ),
        (
            {"camera_calibration_document": {
                **_camera_calibration(), "tag_map_sha256": "0" * 64
            }},
            "tag map differ",
        ),
        (
            {"fusion_context_document": {
                **READER_CONTEXT, "pipeline_epoch": "fusion-epoch-02"
            }},
            "fusion context differs",
        ),
        (
            {"current_attachment_profile": "stylus_attachment"},
            "attachment profile differs",
        ),
    )
    for overrides, expected in cases:
        try:
            _admit_fusion(snapshot, **overrides)
        except fusion.CameraFeedbackStateFusionAdmissionError as error:
            assert expected in str(error)
        else:
            raise AssertionError("crossed fusion evidence was admitted")


def test_fusion_rejects_failed_quality_tampering_and_time_skew(
    tmp_path, monkeypatch
):
    snapshot = _snapshot_receipt(tmp_path, monkeypatch)
    failed = _camera_observation()
    failed["quality"] = {"passed": False}
    crossed = _fusion_admission(snapshot)
    crossed["camera_observation_sha256"] = "0" * 64
    skewed = _fusion_admission(snapshot)
    skewed["camera_observed_at"] = "2026-10-25T14:02:20-04:00"

    cases = (
        ({"camera_observation_document": failed}, "quality failed"),
        ({"document": crossed}, "camera_observation_sha256 mismatch"),
        ({"document": skewed}, "exceed the admitted skew"),
    )
    for overrides, expected in cases:
        try:
            _admit_fusion(snapshot, **overrides)
        except fusion.CameraFeedbackStateFusionAdmissionError as error:
            assert expected in str(error)
        else:
            raise AssertionError("unsafe fusion evidence was admitted")
