"""Fused camera-state review orchestration into one supervisor permit."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.context import load_simulation_context
from rocell.application.fused_camera_state_reviewed_motion_permit_v1 import (
    FusedCameraStateReviewedMotionPermitError,
    FusedCameraStateReviewedMotionPermitSessionV1,
    admit_fused_camera_state_native_t102_authority_v1,
    claim_fused_camera_state_native_t102_writer_v1,
    execute_fused_camera_state_native_t102_production_candidate_v1,
    execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1,
    prepare_fused_camera_state_native_t102_handoff_v1,
)
import rocell.application.native_t102_production_transport_v1 as production_module
from rocell.application.native_t102_production_transport_v1 import (
    ExternalAuthorityVerificationV1,
    ExternalNativeT102AuthorityRecordV1,
    NativeT102ControllerCaptureV1,
    NativeT102FeedbackSampleV1,
    NativeT102ProductionTransportV1,
    PinnedNativeT102EndpointV1,
    ProductionAttemptRecovery,
)
from rocell.application.production_controller_runtime_contract_v1 import (
    ProductionControllerRuntimeContractV1,
    ProductionControllerRuntimeManifestV1,
    RuntimeCommandFrameV1,
)
from rocell.application.reviewed_motion_sole_writer_v1 import (
    IncapableReviewedMotionIoV1,
    IncapableWriteFault,
)
from rocell.application.single_action_execution_review_v1 import (
    SingleActionExecutionReviewError,
)
import rocell.application.t102_machine_ledger_v1 as ledger_module
from rocell.application.t102_machine_ledger_v1 import T102MachineLedgerError
from rocell.arm.all_joint_command import JOINT_FIELDS
from rocell.arm.protocol import encode_line
from rocell.providers.windows.native_t102_serial_transport_v1 import (
    WindowsNativeT102SerialTransportV1,
)
from rocell.rc03.build_snapshot import Capability
from rocell.safety.supervisor import AuthorizationError, SafetySupervisor

import test_fused_camera_state_single_action_execution_review_v1 as fused_review
import test_single_action_execution_review_v1 as execution_review
from test_safety_core import (
    _advance_to_armed,
    _healthy_interlocks,
    _healthy_runtime,
    _valid_calibrations,
)


WORKSPACE = Path(__file__).resolve().parents[3]
ADAPTER = "f" * 64
APPROVAL = "9" * 64
VERIFIER_BUILD = "8" * 64


@pytest.fixture(autouse=True)
def machine_ledger(tmp_path, monkeypatch):
    root = tmp_path / "machine-ledger"
    root.mkdir()
    monkeypatch.setattr(ledger_module, "machine_root", lambda: root)
    return root


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json"
    )


def _session(context):
    return FusedCameraStateReviewedMotionPermitSessionV1(
        fused_review._build(context)
    )


def _arguments(now_ns: int = 1_500):
    now_s = now_ns / 1_000_000_000
    return {
        "calibrations": _valid_calibrations(),
        "interlocks": _healthy_interlocks(now_s),
        "runtime": _healthy_runtime(),
        "now_monotonic_ns": now_ns,
        "permit_ttl_ns": 400,
    }


def _supervisor(released_snapshot):
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    return supervisor


def _runtime_frame(context, *, offset: float = 0.0):
    inputs = execution_review._inputs(context)
    measured = inputs[2].measured_envelope
    goal = execution_review._t102_goal(context)
    if offset:
        goal = {**goal, "base": goal["base"] + offset}
    manifest = ProductionControllerRuntimeManifestV1(
        runtime_id="arm-159-fused-runtime",
        candidate_app_sha256="a" * 64,
        protocol_source_sha256="b" * 64,
        controller_joint_mapping_sha256="c" * 64,
        configuration_epoch_sha256=measured.configuration_epoch_sha256,
        expected_encoding_profile_sha256="3" * 64,
        controller_session_id=measured.controller_session_id,
    )
    frame = RuntimeCommandFrameV1(
        sequence=1,
        correlation_id="arm-159-fused-action-0",
        writer_instance_id="arm-159-writer",
        controller_session_id=manifest.controller_session_id,
        configuration_epoch_sha256=manifest.configuration_epoch_sha256,
        encoding_profile_sha256=manifest.expected_encoding_profile_sha256,
        issued_monotonic_ns=1_550,
        expires_monotonic_ns=1_900,
        wire_bytes=encode_line(goal),
    )
    return goal, frame, ProductionControllerRuntimeContractV1(manifest)


def _ack():
    return encode_line({"T": 1021, "status": "ACCEPTED_ONCE", "ordinal": 1})


def _feedback(goal, captured_monotonic_ns):
    return {
        "captured_monotonic_ns": captured_monotonic_ns,
        "response_bytes": encode_line({
            "T": 1051,
            **dict(zip(("b", "s", "e", "t", "r", "g"),
                       (goal[name] for name in JOINT_FIELDS))),
        }),
    }


class _AuthorityVerifier:
    def __init__(self, *, approved: bool = True) -> None:
        self.approved = approved
        self.calls = 0

    def verify_external_native_t102_authority(self, record, now_monotonic_ns):
        self.calls += 1
        return ExternalAuthorityVerificationV1(
            approved=self.approved,
            signed_payload_sha256=record.signed_payload_sha256,
            verifier_id="fused-external-reviewer",
            verifier_build_sha256=VERIFIER_BUILD,
            verified_monotonic_ns=1_690,
            decision_code=(
                "APPROVED_EXACT_SINGLE_ACTION" if self.approved else "DENIED"
            ),
        )


def _endpoint():
    return PinnedNativeT102EndpointV1(
        port_name="COM7",
        usb_vid="10C4",
        usb_pid="EA60",
        usb_serial_number="ARM162UNIT001",
    )


def _authority_record(result, frame, journal, endpoint, **changes):
    values = {
        "authority_id": "arm162-authority-1",
        "approval_record_sha256": APPROVAL,
        "review_sha256": result.admission.review_sha256,
        "claim_sha256": journal.snapshot().claim_sha256,
        "frame_sha256": frame.frame_sha256,
        "wire_bytes_sha256": frame.wire_bytes_sha256,
        "endpoint_sha256": endpoint.endpoint_sha256,
        "writer_instance_id": frame.writer_instance_id,
        "controller_session_id": frame.controller_session_id,
        "configuration_epoch_sha256": frame.configuration_epoch_sha256,
        "encoding_profile_sha256": frame.encoding_profile_sha256,
        "issued_monotonic_ns": 1_675,
        "expires_monotonic_ns": 1_850,
        "issuer_key_id": "outside-authority-key-1",
        "detached_signature": "TEST-SIGNATURE-NOT-A-PRODUCTION-KEY",
    }
    values.update(changes)
    return ExternalNativeT102AuthorityRecordV1(**values)


class _ProductionTransport(NativeT102ProductionTransportV1):
    """Scripted abstract transport; it owns no port or external handle."""

    def __init__(self, frame, goal, *, fault=None):
        self.frame = frame
        self.goal = goal
        self.fault = fault
        self._open = self._write = self._capture = self._close = 0

    @property
    def open_attempts(self):
        return self._open

    @property
    def write_attempts(self):
        return self._write

    @property
    def capture_attempts(self):
        return self._capture

    @property
    def close_attempts(self):
        return self._close

    def open_once(self, endpoint):
        if self._open:
            raise AssertionError("scripted transport reopened")
        self._open = 1
        if self.fault == "open":
            raise OSError("scripted open uncertainty")
        return endpoint

    def write_once(self, payload):
        if self._write:
            raise AssertionError("scripted transport rewrote")
        self._write = 1
        if payload != self.frame.wire_bytes:
            raise AssertionError("crossed scripted payload")
        if self.fault == "write":
            raise OSError("scripted write uncertainty")
        return len(payload)

    def capture_once(self):
        if self._capture:
            raise AssertionError("scripted transport recaptured")
        self._capture = 1
        if self.fault == "capture":
            raise OSError("scripted capture uncertainty")
        samples = tuple(
            NativeT102FeedbackSampleV1(
                item["captured_monotonic_ns"], item["response_bytes"]
            )
            for item in (
                _feedback(self.goal, 1_750),
                _feedback(self.goal, 1_780),
            )
        )
        return NativeT102ControllerCaptureV1(_ack(), samples)

    def close_once(self):
        if self._close:
            return
        self._close = 1
        if self.fault == "close":
            raise OSError("scripted close uncertainty")


class _WindowsPortInfo:
    device = "COM7"
    vid = 0x10C4
    pid = 0xEA60
    serial_number = "ARM162UNIT001"


class _WindowsSerial:
    """In-memory pyserial shape; no OS handle or device is reachable."""

    def __init__(self, frame, goal):
        response = _feedback(goal, 1_750)["response_bytes"]
        acknowledgment = encode_line({
            "T": 1021,
            "status": "ACCEPTED_ONCE",
            "ordinal": frame.sequence,
        })
        self.lines = [acknowledgment, response, response]
        self.is_open = False
        self.in_waiting = 0
        self.writes = []
        self.opens = 0
        self.closes = 0

    def open(self):
        self.opens += 1
        self.is_open = True

    def close(self):
        self.closes += 1
        self.is_open = False

    def write(self, payload):
        self.writes.append(payload)
        return len(payload)

    def readline(self, maximum):
        return self.lines.pop(0)[:maximum]


def _production_candidate(
    context, released_snapshot, tmp_path, monkeypatch, *, fault=None
):
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    goal, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    receipt_root = tmp_path / "receipts"
    handoff_root.mkdir()
    receipt_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )
    claim_fused_camera_state_native_t102_writer_v1(
        result,
        frame,
        journal,
        adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_650,
    )
    endpoint = _endpoint()
    verifier = _AuthorityVerifier()
    monkeypatch.setattr(production_module, "_machine_verifier", lambda: verifier)
    monkeypatch.setattr(
        production_module, "_trusted_monotonic_ns", lambda: 1_700
    )
    monkeypatch.setattr(
        production_module,
        "_verify_machine_authority_at_sink",
        lambda record, now: None,
    )
    authority = admit_fused_camera_state_native_t102_authority_v1(
        result,
        frame,
        journal,
        _authority_record(result, frame, journal, endpoint),
        endpoint,
        adapter_candidate_sha256=ADAPTER,
    )
    return (
        result,
        goal,
        frame,
        journal,
        authority,
        endpoint,
        receipt_root,
        _ProductionTransport(frame, goal, fault=fault),
    )


def test_fused_review_issues_one_exact_bound_supervisor_permit(
    context, released_snapshot,
) -> None:
    session = _session(context)
    result = session.issue(_supervisor(released_snapshot), **_arguments())
    review = fused_review._build(context)

    assert session.state == "CONSUMED"
    assert result.permit.capability is Capability.KEYBOARD_CONTACT
    assert result.permit.plan_hash == review.review_sha256
    assert result.permit.remaining_uses == 1
    assert result.admission.fused_camera_state_action_review_admission_sha256 == (
        review.fused_camera_state_action_review_admission_sha256
    )
    assert result.consumption_receipt["hardware_access"] is False
    assert result.lifecycle.snapshot()["phase"] == "ACCEPTED"
    schema = json.loads(
        (WORKSPACE / "software/ai/schemas/"
         "reviewed_motion_permit_admission_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(result.admission.to_dict())


def test_legacy_review_cannot_enter_fused_orchestrator(context) -> None:
    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError,
        match="fused camera-state action review admission is required",
    ):
        FusedCameraStateReviewedMotionPermitSessionV1(
            execution_review._review(context)
        )


def test_invalid_ttl_rejects_before_consuming_review(
    context, released_snapshot,
) -> None:
    session = _session(context)
    invalid = {**_arguments(), "permit_ttl_ns": 501}
    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError, match="would outlive"
    ):
        session.issue(_supervisor(released_snapshot), **invalid)
    assert session.state == "PENDING"

    result = session.issue(_supervisor(released_snapshot), **_arguments())
    assert result.permit.remaining_uses == 1


def test_session_cannot_consume_twice(context, released_snapshot) -> None:
    session = _session(context)
    session.issue(_supervisor(released_snapshot), **_arguments())
    with pytest.raises(SingleActionExecutionReviewError, match="already consumed"):
        session.issue(_supervisor(released_snapshot), **_arguments())


def test_reconstructed_review_cannot_reserve_with_a_new_receipt(
    context, released_snapshot,
) -> None:
    _session(context).issue(_supervisor(released_snapshot), **_arguments())
    with pytest.raises(T102MachineLedgerError, match="already spent"):
        _session(context).issue(
            _supervisor(released_snapshot), **_arguments(now_ns=1_600)
        )


def test_preflight_failure_burns_reconstructed_review(
    context, released_snapshot,
) -> None:
    blocked = {**_arguments(), "runtime": type(_healthy_runtime())()}
    with pytest.raises(AuthorizationError, match="Preflight is blocked"):
        _session(context).issue(_supervisor(released_snapshot), **blocked)
    with pytest.raises(T102MachineLedgerError, match="already spent"):
        _session(context).issue(_supervisor(released_snapshot), **_arguments())


def test_fused_permit_rehearses_one_t102_write_ack_and_settlement(
    context, released_snapshot,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    goal, frame, runtime = _runtime_frame(context)
    report = execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1(
        result,
        frame,
        runtime,
        IncapableReviewedMotionIoV1(),
        _ack(),
        [_feedback(goal, 1_700), _feedback(goal, 1_750)],
        writer_instance_id="arm-159-writer",
        dispatch_monotonic_ns=1_600,
        assessment_monotonic_ns=1_800,
    )

    assert report["status"] == "COMPLETED"
    assert report["fused_camera_state_action_review_admission_sha256"] == (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    assert report["review_consumption_sha256"] == (
        result.consumption_receipt["consumption_sha256"]
    )
    assert report["dispatch"]["write_attempts"] == 1
    assert report["acknowledgment"]["status"] == "ACCEPTED_ONCE"
    assert report["settlement"]["status"] == (
        "OBSERVED_SETTLED_JOINT_ARRIVAL"
    )
    assert report["automatic_retry_allowed"] is False
    assert report["physical_command_writes"] == 0
    assert result.permit.remaining_uses == 0
    schema = json.loads(
        (WORKSPACE / "software/ai/schemas/"
         "reviewed_t102_runtime_execution_rehearsal_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(report)


def test_fused_permit_prepares_cancellable_native_handoff_without_claim(
    context, released_snapshot, tmp_path,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )

    snapshot = journal.snapshot()
    document = snapshot.to_dict()
    prepared = json.loads(
        (journal.directory / "prepared.json").read_text(encoding="utf-8")
    )
    assert document["phase"] == "PREPARED"
    assert document["recovery_disposition"] == (
        "CANCEL_AND_REPLAN_WITH_FRESH_AUTHORITY"
    )
    assert document["fused_camera_state_action_review_admission_sha256"] == (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    assert document["review_consumption_sha256"] == (
        result.admission.consumption_sha256
    )
    assert prepared["permit_binding_sha256"] == (
        result.admission.permit_binding_sha256
    )
    assert prepared["fused_camera_state_action_review_admission_sha256"] == (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    assert prepared["review_consumption_sha256"] == (
        result.admission.consumption_sha256
    )
    assert {item.name for item in journal.directory.iterdir()} == {
        "prepared.json"
    }
    assert document["transport_open_count"] == 0
    assert document["physical_command_writes"] == 0
    assert result.permit.remaining_uses == 1
    assert result.lifecycle.snapshot()["phase"] == "ACCEPTED"
    for name, value in (
        ("native_t102_handoff_snapshot_v1.schema.json", document),
        ("native_t102_handoff_prepared_v1.schema.json", prepared),
    ):
        schema = json.loads(
            (WORKSPACE / "software/ai/schemas" / name).read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(value)


def test_crossed_fused_native_handoff_rejects_before_publishing(
    context, released_snapshot, tmp_path,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context, offset=0.1)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError, match="differs"
    ):
        prepare_fused_camera_state_native_t102_handoff_v1(
            result,
            frame,
            handoff_root,
            adapter_candidate_sha256=ADAPTER,
            created_monotonic_ns=1_600,
        )
    assert tuple(handoff_root.iterdir()) == ()
    assert result.permit.remaining_uses == 1


def test_fused_native_handoff_commits_one_zero_authority_writer_claim(
    context, released_snapshot, tmp_path,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )

    snapshot = claim_fused_camera_state_native_t102_writer_v1(
        result,
        frame,
        journal,
        adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_650,
    )

    document = snapshot.to_dict()
    claim = json.loads(
        (journal.directory / "claim.json").read_text(encoding="utf-8")
    )
    assert document["phase"] == "WRITER_CLAIMED"
    assert document["recovery_disposition"] == (
        "RETRY_FORBIDDEN_DISPATCH_UNCERTAIN"
    )
    assert document["fused_camera_state_action_review_admission_sha256"] == (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    assert document["review_consumption_sha256"] == (
        result.admission.consumption_sha256
    )
    assert claim["status"] == "WRITER_CLAIM_COMMITTED_BEFORE_NATIVE_OPEN"
    assert claim["transport_open_authorized"] is False
    assert claim["physical_authority"] is False
    assert claim["automatic_retry_allowed"] is False
    assert claim["transport_open_count"] == 0
    assert claim["physical_command_writes"] == 0
    assert result.permit.remaining_uses == 1
    assert result.lifecycle.snapshot()["phase"] == "ACCEPTED"
    for name, value in (
        ("native_t102_handoff_snapshot_v1.schema.json", document),
        ("native_t102_writer_claim_v1.schema.json", claim),
    ):
        schema = json.loads(
            (WORKSPACE / "software/ai/schemas" / name).read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(value)

    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError, match="not available"
    ):
        claim_fused_camera_state_native_t102_writer_v1(
            result,
            frame,
            journal,
            adapter_candidate_sha256=ADAPTER,
            claimed_monotonic_ns=1_700,
        )
    assert result.permit.remaining_uses == 1


def test_expired_fused_native_writer_claim_rejects_before_commit(
    context, released_snapshot, tmp_path,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )

    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError,
        match="outside the authorized lifetime",
    ):
        claim_fused_camera_state_native_t102_writer_v1(
            result,
            frame,
            journal,
            adapter_candidate_sha256=ADAPTER,
            claimed_monotonic_ns=1_900,
        )
    assert {item.name for item in journal.directory.iterdir()} == {
        "prepared.json"
    }
    assert result.permit.remaining_uses == 1


def test_fused_writer_claim_admits_exact_external_authority_without_consuming(
    context, released_snapshot, tmp_path, monkeypatch,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )
    claim_fused_camera_state_native_t102_writer_v1(
        result,
        frame,
        journal,
        adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_650,
    )
    endpoint = _endpoint()
    record = _authority_record(result, frame, journal, endpoint)
    verifier = _AuthorityVerifier()
    monkeypatch.setattr(production_module, "_machine_verifier", lambda: verifier)
    monkeypatch.setattr(
        production_module, "_trusted_monotonic_ns", lambda: 1_700
    )

    admitted = admit_fused_camera_state_native_t102_authority_v1(
        result,
        frame,
        journal,
        record,
        endpoint,
        adapter_candidate_sha256=ADAPTER,
    )

    assert admitted.record is record
    assert admitted.verification.approved is True
    assert admitted.verification.signed_payload_sha256 == (
        record.signed_payload_sha256
    )
    assert verifier.calls == 1
    assert {item.name for item in journal.directory.iterdir()} == {
        "prepared.json", "claim.json"
    }
    assert result.permit.remaining_uses == 1
    assert result.lifecycle.snapshot()["phase"] == "ACCEPTED"
    for name, value in (
        ("external_native_t102_authority_v1.schema.json", record.to_dict()),
        (
            "external_native_t102_authority_verification_v1.schema.json",
            admitted.verification.to_dict(),
        ),
    ):
        schema = json.loads(
            (WORKSPACE / "software/ai/schemas" / name).read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(value)

    admitted.consume(
        claim_sha256=journal.snapshot().claim_sha256,
        frame=frame,
        endpoint=endpoint,
        now_monotonic_ns=1_750,
    )


def test_crossed_fused_external_authority_rejects_before_verification(
    context, released_snapshot, tmp_path, monkeypatch,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )
    claim_fused_camera_state_native_t102_writer_v1(
        result,
        frame,
        journal,
        adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_650,
    )
    endpoint = _endpoint()
    record = _authority_record(
        result, frame, journal, endpoint, review_sha256="7" * 64
    )
    verifier = _AuthorityVerifier()
    monkeypatch.setattr(production_module, "_machine_verifier", lambda: verifier)

    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError,
        match="does not bind the exact fused writer claim",
    ):
        admit_fused_camera_state_native_t102_authority_v1(
            result,
            frame,
            journal,
            record,
            endpoint,
            adapter_candidate_sha256=ADAPTER,
        )
    assert verifier.calls == 0
    assert result.permit.remaining_uses == 1


def test_external_authority_cannot_outlive_fused_permit_or_frame(
    context, released_snapshot, tmp_path, monkeypatch,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )
    claim_fused_camera_state_native_t102_writer_v1(
        result,
        frame,
        journal,
        adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_650,
    )
    endpoint = _endpoint()
    record = _authority_record(
        result, frame, journal, endpoint, expires_monotonic_ns=1_950
    )
    verifier = _AuthorityVerifier()
    monkeypatch.setattr(production_module, "_machine_verifier", lambda: verifier)

    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError,
        match="does not bind the exact fused writer claim",
    ):
        admit_fused_camera_state_native_t102_authority_v1(
            result,
            frame,
            journal,
            record,
            endpoint,
            adapter_candidate_sha256=ADAPTER,
        )
    assert verifier.calls == 0
    assert result.permit.remaining_uses == 1


def test_exact_fused_production_candidate_seals_one_terminal_receipt(
    context, released_snapshot, tmp_path, monkeypatch,
) -> None:
    (
        result,
        _,
        frame,
        handoff,
        authority,
        endpoint,
        receipt_root,
        transport,
    ) = _production_candidate(
        context, released_snapshot, tmp_path, monkeypatch
    )

    journal, receipt, terminal = (
        execute_fused_camera_state_native_t102_production_candidate_v1(
            result,
            frame,
            handoff,
            authority,
            endpoint,
            transport,
            receipt_root,
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_720,
            assessment_monotonic_ns=1_800,
            completed_monotonic_ns=1_825,
        )
    )

    assert receipt.status == "CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED"
    assert receipt.claim_sha256 == handoff.snapshot().claim_sha256
    assert receipt.authority_sha256 == authority.record.signed_payload_sha256
    assert receipt.endpoint_sha256 == endpoint.endpoint_sha256
    assert terminal.recovery_disposition is ProductionAttemptRecovery.TERMINAL_NO_REPLAY
    assert journal.snapshot() == terminal
    assert (
        transport.open_attempts,
        transport.write_attempts,
        transport.capture_attempts,
        transport.close_attempts,
    ) == (1, 1, 1, 1)
    assert result.permit.remaining_uses == 0
    assert result.lifecycle.snapshot()["phase"] == "ACCEPTED"


def test_fused_candidate_composes_through_real_windows_provider_class(
    context, released_snapshot, tmp_path, monkeypatch,
) -> None:
    (
        result,
        goal,
        frame,
        handoff,
        authority,
        endpoint,
        receipt_root,
        _,
    ) = _production_candidate(
        context, released_snapshot, tmp_path, monkeypatch
    )
    serial = _WindowsSerial(frame, goal)
    ticks = iter((1_750, 1_780))
    transport = WindowsNativeT102SerialTransportV1(
        serial_factory=lambda: serial,
        port_inventory=lambda: [_WindowsPortInfo()],
        monotonic_ns=lambda: next(ticks),
    )

    journal, receipt, terminal = (
        execute_fused_camera_state_native_t102_production_candidate_v1(
            result,
            frame,
            handoff,
            authority,
            endpoint,
            transport,
            receipt_root,
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_720,
            assessment_monotonic_ns=1_800,
            completed_monotonic_ns=1_825,
        )
    )

    document = receipt.to_dict()
    assert receipt.status == "CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED"
    assert terminal.recovery_disposition is ProductionAttemptRecovery.TERMINAL_NO_REPLAY
    assert journal.snapshot() == terminal
    assert serial.writes == [
        frame.wire_bytes,
        b'{"T":105}\n',
        b'{"T":105}\n',
    ]
    assert serial.opens == serial.closes == 1
    assert document["transport_implementation_qualified"] is False
    assert document["authentic_controller_receipt_claimed"] is False
    assert document["physical_movement_verified"] is False
    assert result.permit.remaining_uses == 0


def test_crossed_endpoint_rejects_fused_candidate_before_transport(
    context, released_snapshot, tmp_path, monkeypatch,
) -> None:
    (
        result,
        _,
        frame,
        handoff,
        authority,
        _,
        receipt_root,
        transport,
    ) = _production_candidate(
        context, released_snapshot, tmp_path, monkeypatch
    )
    crossed_endpoint = PinnedNativeT102EndpointV1(
        port_name="COM8",
        usb_vid="10C4",
        usb_pid="EA60",
        usb_serial_number="ARM162UNIT002",
    )

    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError,
        match="does not bind the exact fused writer claim",
    ):
        execute_fused_camera_state_native_t102_production_candidate_v1(
            result,
            frame,
            handoff,
            authority,
            crossed_endpoint,
            transport,
            receipt_root,
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_720,
            assessment_monotonic_ns=1_800,
            completed_monotonic_ns=1_825,
        )

    assert (
        transport.open_attempts,
        transport.write_attempts,
        transport.capture_attempts,
        transport.close_attempts,
    ) == (0, 0, 0, 0)
    assert tuple(receipt_root.iterdir()) == ()
    assert result.permit.remaining_uses == 1


def test_fused_open_uncertainty_is_terminal_and_cannot_replay(
    context, released_snapshot, tmp_path, monkeypatch,
) -> None:
    (
        result,
        goal,
        frame,
        handoff,
        authority,
        endpoint,
        receipt_root,
        transport,
    ) = _production_candidate(
        context, released_snapshot, tmp_path, monkeypatch, fault="open"
    )

    journal, receipt, terminal = (
        execute_fused_camera_state_native_t102_production_candidate_v1(
            result,
            frame,
            handoff,
            authority,
            endpoint,
            transport,
            receipt_root,
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_720,
            assessment_monotonic_ns=1_800,
            completed_monotonic_ns=1_825,
        )
    )

    assert receipt.status == "NOT_OPENED_AUTHORITY_CONSUMED_NO_RETRY"
    assert receipt.error_code == "OPEN_FAILURE"
    assert terminal.recovery_disposition is ProductionAttemptRecovery.TERMINAL_NO_REPLAY
    assert journal.snapshot() == terminal
    assert (transport.open_attempts, transport.write_attempts) == (1, 0)
    assert result.permit.remaining_uses == 0

    replay_transport = _ProductionTransport(frame, goal)
    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError,
        match="does not bind the exact fused writer claim",
    ):
        execute_fused_camera_state_native_t102_production_candidate_v1(
            result,
            frame,
            handoff,
            authority,
            endpoint,
            replay_transport,
            receipt_root,
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_730,
            assessment_monotonic_ns=1_810,
            completed_monotonic_ns=1_830,
        )
    assert replay_transport.open_attempts == 0


def test_fused_runtime_write_uncertainty_is_terminal_without_retry(
    context, released_snapshot,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, runtime = _runtime_frame(context)
    io = IncapableReviewedMotionIoV1(IncapableWriteFault.PARTIAL_WRITE)
    report = execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1(
        result,
        frame,
        runtime,
        io,
        _ack(),
        (),
        writer_instance_id="arm-159-writer",
        dispatch_monotonic_ns=1_600,
        assessment_monotonic_ns=1_800,
    )

    assert report["status"] == "UNCERTAIN"
    assert report["acknowledgment"] is None
    assert report["settlement"] is None
    assert report["automatic_retry_allowed"] is False
    assert report["follow_on_movement_authorized"] is False
    assert io.write_attempts == 1
    assert result.permit.remaining_uses == 0


def test_crossed_fused_t102_goal_rejects_before_consumption_or_write(
    context, released_snapshot,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, runtime = _runtime_frame(context, offset=0.1)
    io = IncapableReviewedMotionIoV1()
    with pytest.raises(ValueError, match="identity differs"):
        execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1(
            result,
            frame,
            runtime,
            io,
            _ack(),
            (),
            writer_instance_id="arm-159-writer",
            dispatch_monotonic_ns=1_600,
            assessment_monotonic_ns=1_800,
        )
    assert io.write_attempts == 0
    assert result.permit.remaining_uses == 1
