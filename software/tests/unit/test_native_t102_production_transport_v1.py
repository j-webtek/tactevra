"""ARM-053 production-boundary tests; abstract scripted I/O only."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import base64
import hashlib
import json
from pathlib import Path

import pytest
import jsonschema
from referencing import Registry, Resource

from rocell.application.native_t102_handoff_journal_v1 import (
    DurableNativeT102HandoffV1,
)
import rocell.application.native_t102_production_transport_v1 as production_module
import rocell.application.t102_machine_ledger_v1 as ledger_module
from rocell.application.t102_machine_ledger_v1 import T102MachineLedgerError
from rocell.application.native_t102_production_transport_v1 import (
    DurableNativeT102ProductionAttemptV1,
    ExternalAuthorityVerificationV1,
    ExternalNativeT102AuthorityRecordV1,
    NativeT102ControllerCaptureV1,
    NativeT102FeedbackSampleV1,
    NativeT102ProductionTransportError,
    NativeT102ProductionTransportV1,
    PinnedNativeT102EndpointV1,
    ProductionAttemptRecovery,
    admit_external_native_t102_authority_v1,
    execute_native_t102_production_candidate_v1,
)
from rocell.application.production_controller_runtime_contract_v1 import (
    RuntimeCommandFrameV1,
)
from rocell.application.reviewed_motion_permit_bridge_v1 import (
    ReviewedMotionPermitAdmissionV1,
)
from rocell.arm.all_joint_command import all_joint_command
from rocell.arm.protocol import encode_line
from rocell.rc03.build_snapshot import Capability
from rocell.safety.permit import MotionPermit, goal_hash


ADAPTER = "f" * 64
APPROVAL = "9" * 64
VERIFIER_BUILD = "8" * 64
WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def machine_ledger(tmp_path, monkeypatch):
    root = tmp_path / "machine-ledger"
    root.mkdir()
    monkeypatch.setattr(ledger_module, "machine_root",
                        lambda: root)
    monkeypatch.setattr(production_module, "_machine_verifier",
                        lambda: ScriptedVerifier())
    monkeypatch.setattr(production_module, "_trusted_monotonic_ns",
                        lambda: 1_070)
    monkeypatch.setattr(production_module, "_verify_machine_authority_at_sink",
                        lambda record, now: None)
    return root


def _hash(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _schema(name):
    return json.loads((WORKSPACE / "software/ai/schemas" / name).read_text(
        encoding="utf-8"))


def _message():
    return all_joint_command(
        [.1, .2, .3, .4, .5, .6], speed=20, acceleration=1)


def _frame(message):
    return RuntimeCommandFrameV1(
        sequence=1,
        correlation_id="arm053-correlation-1",
        writer_instance_id="arm053-writer",
        controller_session_id="arm053-controller-session",
        configuration_epoch_sha256="d" * 64,
        encoding_profile_sha256="e" * 64,
        issued_monotonic_ns=900,
        expires_monotonic_ns=3_000,
        wire_bytes=encode_line(message),
    )


def _admission(message):
    values = dict(
        review_sha256="a" * 64,
        consumption_sha256="b" * 64,
        capability=Capability.KEYBOARD_CONTACT,
        snapshot_sha256="c" * 64,
        ordered_goal_sha256=(goal_hash(message),),
        permit_expires_at_monotonic=102.0,
    )
    binding = _hash({
        "review_sha256": values["review_sha256"],
        "consumption_sha256": values["consumption_sha256"],
        "capability": values["capability"].value,
        "snapshot_sha256": values["snapshot_sha256"],
        "plan_hash": values["review_sha256"],
        "ordered_goal_sha256": list(values["ordered_goal_sha256"]),
        "permit_expires_at_monotonic": values["permit_expires_at_monotonic"],
    })
    return ReviewedMotionPermitAdmissionV1(
        **values, permit_binding_sha256=binding)


def _motion_permit(message, admission):
    return MotionPermit._issue(
        capability=admission.capability,
        snapshot_hash=admission.snapshot_sha256,
        plan_hash=admission.review_sha256,
        goals=(message,), ttl_s=102.0, now_monotonic=0.0,
    )


def _endpoint(**changes):
    values = dict(
        port_name="COM7", usb_vid="10C4", usb_pid="EA60",
        usb_serial_number="ARM053UNIT001",
    )
    values.update(changes)
    return PinnedNativeT102EndpointV1(**values)


def _claimed(tmp_path, *, reserve=True):
    message = _message()
    frame = _frame(message)
    admission = _admission(message)
    if reserve:
        ledger_module.reserve_review(admission.consumption_sha256,
                                     admission.review_sha256,
                                     admission.ordered_goal_sha256[0])
    handoff_root = tmp_path / "handoff"
    receipt_root = tmp_path / "receipts"
    handoff_root.mkdir()
    receipt_root.mkdir()
    handoff = DurableNativeT102HandoffV1.prepare(
        handoff_root, frame, admission, adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=950,
    )
    handoff.claim_writer(
        frame, admission, adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_000,
    )
    return receipt_root, handoff, frame, admission


class ScriptedVerifier:
    def __init__(self, *, approved=True, crossed=False):
        self.approved = approved
        self.crossed = crossed
        self.calls = 0

    def verify_external_native_t102_authority(self, record, now_monotonic_ns):
        self.calls += 1
        return ExternalAuthorityVerificationV1(
            approved=self.approved,
            signed_payload_sha256=(
                "7" * 64 if self.crossed else record.signed_payload_sha256),
            verifier_id="external-reviewer",
            verifier_build_sha256=VERIFIER_BUILD,
            verified_monotonic_ns=1_060,
            decision_code=("APPROVED_EXACT_SINGLE_ACTION"
                           if self.approved else "DENIED"),
        )


def _authority(handoff, frame, endpoint, **changes):
    snapshot = handoff.snapshot()
    values = dict(
        authority_id="arm053-authority-1",
        approval_record_sha256=APPROVAL,
        review_sha256="a" * 64,
        claim_sha256=snapshot.claim_sha256,
        frame_sha256=frame.frame_sha256,
        wire_bytes_sha256=frame.wire_bytes_sha256,
        endpoint_sha256=endpoint.endpoint_sha256,
        writer_instance_id=frame.writer_instance_id,
        controller_session_id=frame.controller_session_id,
        configuration_epoch_sha256=frame.configuration_epoch_sha256,
        encoding_profile_sha256=frame.encoding_profile_sha256,
        issued_monotonic_ns=1_050,
        expires_monotonic_ns=2_900,
        issuer_key_id="outside-authority-key-1",
        detached_signature="TEST-SIGNATURE-NOT-A-PRODUCTION-KEY",
    )
    values.update(changes)
    record = ExternalNativeT102AuthorityRecordV1(**values)
    return record, admit_external_native_t102_authority_v1(record)


def _capture(frame, *, error=0.0):
    target = _message()
    values = [target[name] + error for name in
              ("base", "shoulder", "elbow", "wrist", "roll", "hand")]
    response = encode_line({
        "T": 1051, "b": values[0], "s": values[1], "e": values[2],
        "t": values[3], "r": values[4], "g": values[5],
    })
    return NativeT102ControllerCaptureV1(
        acknowledgment_bytes=encode_line({
            "T": 1021, "status": "ACCEPTED_ONCE", "ordinal": frame.sequence}),
        feedback_samples=(
            NativeT102FeedbackSampleV1(1_150, response),
            NativeT102FeedbackSampleV1(1_160, response),
        ),
    )


class ScriptedTransport(NativeT102ProductionTransportV1):
    """Test-only abstract implementation; owns no port or external handle."""

    def __init__(self, frame, *, observed=None, write_count=None,
                 capture=None, fault=None):
        self.frame = frame
        self.observed = observed
        self.write_count = write_count
        self.scripted_capture = capture
        self.fault = fault
        self._open = self._write = self._capture = self._close = 0

    @property
    def open_attempts(self): return self._open

    @property
    def write_attempts(self): return self._write

    @property
    def capture_attempts(self): return self._capture

    @property
    def close_attempts(self): return self._close

    def open_once(self, endpoint):
        if self._open:
            raise AssertionError("reopen")
        self._open = 1
        if self.fault == "open":
            raise OSError("scripted open")
        return self.observed or endpoint

    def write_once(self, payload):
        if self._write:
            raise AssertionError("rewrite")
        self._write = 1
        if payload != self.frame.wire_bytes:
            raise AssertionError("crossed payload")
        if self.fault == "write":
            raise OSError("scripted write")
        return len(payload) if self.write_count is None else self.write_count

    def capture_once(self):
        if self._capture:
            raise AssertionError("recapture")
        self._capture = 1
        if self.fault == "capture":
            raise OSError("scripted capture")
        return self.scripted_capture or _capture(self.frame)

    def close_once(self):
        if self._close:
            return
        self._close = 1
        if self.fault == "close":
            raise OSError("scripted close")


def _execute(tmp_path, *, transport_factory=None):
    root, handoff, frame, admission = _claimed(tmp_path)
    endpoint = _endpoint()
    _, authority = _authority(handoff, frame, endpoint)
    transport = ((transport_factory or ScriptedTransport)(frame))
    result = execute_native_t102_production_candidate_v1(
        root, handoff, frame, admission, authority, endpoint, transport,
        motion_permit=_motion_permit(_message(), admission),
        adapter_candidate_sha256=ADAPTER,
        started_monotonic_ns=1_100,
        assessment_monotonic_ns=1_200,
        completed_monotonic_ns=1_250,
    )
    return result, transport


def test_exact_external_authority_and_capture_seal_no_replay_receipt(tmp_path):
    (journal, receipt, snapshot), transport = _execute(tmp_path)
    document = receipt.to_dict()
    assert document["status"] == (
        "CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED")
    assert document["confirmed_bytes"] == document["requested_bytes"]
    assert document["open_attempts"] == document["write_attempts"] == 1
    assert document["capture_attempts"] == document["close_attempts"] == 1
    assert document["external_authority_verification_record_accepted"] is True
    assert document["physical_authority_claimed"] is False
    assert document["transport_implementation_qualified"] is False
    assert document["authentic_controller_receipt_claimed"] is False
    assert document["physical_movement_verified"] is False
    assert snapshot.recovery_disposition is ProductionAttemptRecovery.TERMINAL_NO_REPLAY
    assert journal.snapshot() == snapshot
    assert {item.name for item in journal.directory.iterdir()} == {
        "started.json", "terminal.json"}
    assert transport.write_attempts == 1
    for name, value in (
        ("native_t102_production_transport_receipt_v1.schema.json", document),
        ("native_t102_production_attempt_snapshot_v1.schema.json",
         snapshot.to_dict()),
    ):
        jsonschema.Draft202012Validator(_schema(name)).validate(value)
    endpoint = _endpoint()
    jsonschema.Draft202012Validator(_schema(
        "native_t102_pinned_endpoint_v1.schema.json")).validate(
            endpoint.to_dict())
    started = json.loads((journal.directory / "started.json").read_text("utf-8"))
    jsonschema.Draft202012Validator(_schema(
        "native_t102_production_attempt_started_v1.schema.json")).validate(started)
    terminal = json.loads((journal.directory / "terminal.json").read_text("utf-8"))
    receipt_schema = _schema(
        "native_t102_production_transport_receipt_v1.schema.json")
    registry = Registry().with_resource(
        "https://rocell.local/schemas/native_t102_production_transport_receipt_v1.schema.json",
        Resource.from_contents(receipt_schema),
    )
    jsonschema.Draft202012Validator(
        _schema("native_t102_production_attempt_terminal_v1.schema.json"),
        registry=registry,
    ).validate(terminal)


def test_authority_and_external_verification_match_closed_schemas(tmp_path):
    _, handoff, frame, _ = _claimed(tmp_path)
    endpoint = _endpoint()
    record, authority = _authority(handoff, frame, endpoint)
    jsonschema.Draft202012Validator(_schema(
        "external_native_t102_authority_v1.schema.json")).validate(
            record.to_dict())
    jsonschema.Draft202012Validator(_schema(
        "external_native_t102_authority_verification_v1.schema.json")).validate(
            authority.verification.to_dict())


def test_started_record_alone_is_retry_forbidden(tmp_path):
    root, handoff, frame, _ = _claimed(tmp_path)
    endpoint = _endpoint()
    _, authority = _authority(handoff, frame, endpoint)
    snapshot = handoff.snapshot()
    journal = DurableNativeT102ProductionAttemptV1.begin(
        root, claim_sha256=snapshot.claim_sha256,
        prepared_sha256=snapshot.prepared_sha256, frame=frame,
        authority=authority, endpoint=endpoint, started_monotonic_ns=1_100,
    )
    reopened = journal.snapshot()
    assert reopened.recovery_disposition is (
        ProductionAttemptRecovery.RETRY_FORBIDDEN_EXECUTION_UNCERTAIN)
    assert {item.name for item in journal.directory.iterdir()} == {"started.json"}


@pytest.mark.parametrize("approved,crossed", [(False, False), (True, True)])
def test_external_verifier_denial_or_crossing_rejects(
    approved, crossed, tmp_path, monkeypatch,
):
    _, handoff, frame, _ = _claimed(tmp_path)
    endpoint = _endpoint()
    verifier = ScriptedVerifier(approved=approved, crossed=crossed)
    monkeypatch.setattr(production_module, "_machine_verifier", lambda: verifier)
    with pytest.raises(NativeT102ProductionTransportError, match="not positively"):
        _authority(handoff, frame, endpoint)
    assert verifier.calls == 1


def test_machine_keyring_verifies_signature_and_rejects_forged_payload(
    tmp_path, machine_ledger, monkeypatch,
):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    _, handoff, frame, _ = _claimed(tmp_path)
    record, _ = _authority(handoff, frame, _endpoint())
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    keyring = machine_ledger.parent / "t102-authority-keys-v1.json"
    keyring.write_text(json.dumps({
        "schema": "rocell.native_t102_issuer_keyring.v1",
        "keys": {
            record.issuer_key_id: base64.b64encode(public_key).decode(),
            "same-key-alias": base64.b64encode(public_key).decode(),
        },
    }), encoding="utf-8")
    signature = private_key.sign(json.dumps(
        record.signed_payload(), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode())
    signed = replace(record, detached_signature=base64.b64encode(signature).decode())
    monkeypatch.setattr(production_module, "_machine_verifier",
                        production_module.MachinePinnedEd25519AuthorityVerifierV1)
    admitted = admit_external_native_t102_authority_v1(signed)
    assert admitted.record == signed
    with pytest.raises(NativeT102ProductionTransportError, match="signature"):
        admit_external_native_t102_authority_v1(
            replace(signed, endpoint_sha256="f" * 64))
    with pytest.raises(NativeT102ProductionTransportError, match="signature"):
        admit_external_native_t102_authority_v1(
            replace(signed, review_sha256="f" * 64))
    with pytest.raises(NativeT102ProductionTransportError, match="signature"):
        admit_external_native_t102_authority_v1(
            replace(signed, issuer_key_id="same-key-alias"))


def test_trusted_clock_rejects_expired_authority(
    tmp_path, monkeypatch,
):
    _, handoff, frame, _ = _claimed(tmp_path)
    record, _ = _authority(handoff, frame, _endpoint())
    monkeypatch.setattr(production_module, "_trusted_monotonic_ns",
                        lambda: 3_000)
    with pytest.raises(NativeT102ProductionTransportError,
                       match="not positively"):
        admit_external_native_t102_authority_v1(
            record)


def test_native_sink_rechecks_machine_signature_even_for_admitted_wrapper(
    tmp_path, monkeypatch,
):
    root, handoff, frame, admission = _claimed(tmp_path)
    _, authority = _authority(handoff, frame, _endpoint())
    monkeypatch.setattr(
        production_module, "_verify_machine_authority_at_sink",
        lambda record, now: production_module.MachinePinnedEd25519AuthorityVerifierV1(
        ).verify_external_native_t102_authority(record, now),
    )
    transport = ScriptedTransport(frame)
    with pytest.raises(NativeT102ProductionTransportError,
                       match="keyring is unavailable"):
        execute_native_t102_production_candidate_v1(
            root, handoff, frame, admission, authority, _endpoint(), transport,
            motion_permit=_motion_permit(_message(), admission),
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_100, assessment_monotonic_ns=1_200,
            completed_monotonic_ns=1_250,
        )
    assert transport.open_attempts == 0


def test_signed_authority_for_another_review_cannot_open_transport(tmp_path):
    root, handoff, frame, admission = _claimed(tmp_path)
    endpoint = _endpoint()
    _, authority = _authority(
        handoff, frame, endpoint, review_sha256="9" * 64)
    transport = ScriptedTransport(frame)
    with pytest.raises(NativeT102ProductionTransportError,
                       match="does not bind this reviewed action"):
        execute_native_t102_production_candidate_v1(
            root, handoff, frame, admission, authority, endpoint, transport,
            motion_permit=_motion_permit(_message(), admission),
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_100, assessment_monotonic_ns=1_200,
            completed_monotonic_ns=1_250,
        )
    assert transport.open_attempts == 0
    assert transport.write_attempts == 0


def test_endpoint_mismatch_opens_once_but_never_writes(tmp_path):
    def factory(frame):
        return ScriptedTransport(frame, observed=_endpoint(port_name="COM8"))
    (_, receipt, _), transport = _execute(tmp_path, transport_factory=factory)
    assert receipt.status == "ENDPOINT_IDENTITY_MISMATCH_NO_WRITE"
    assert receipt.error_code == "ENDPOINT_IDENTITY_MISMATCH"
    assert transport.open_attempts == 1
    assert transport.write_attempts == 0
    assert transport.capture_attempts == 0
    assert transport.close_attempts == 1


@pytest.mark.parametrize("fault,status,code,writes,captures", [
    ("open", "NOT_OPENED_AUTHORITY_CONSUMED_NO_RETRY", "OPEN_FAILURE", 0, 0),
    ("write", "WRITE_UNCERTAIN_NO_RETRY", "WRITE_EXCEPTION", 1, 0),
    ("capture", "EVIDENCE_UNCERTAIN_NO_RETRY",
     "CAPTURE_OR_EVIDENCE_FAILURE", 1, 1),
    ("close", "CLOSE_UNCERTAIN_NO_RETRY", "CLOSE_FAILURE", 1, 1),
])
def test_transport_faults_are_terminal_without_retry(
    tmp_path, fault, status, code, writes, captures,
):
    def factory(frame): return ScriptedTransport(frame, fault=fault)
    (_, receipt, snapshot), transport = _execute(
        tmp_path, transport_factory=factory)
    assert receipt.status == status
    assert receipt.error_code == code
    assert transport.open_attempts == 1
    assert transport.write_attempts == writes
    assert transport.capture_attempts == captures
    assert snapshot.recovery_disposition is ProductionAttemptRecovery.TERMINAL_NO_REPLAY


@pytest.mark.parametrize("count,code", [(0, "ZERO_WRITE"), (1, "PARTIAL_WRITE")])
def test_short_write_never_captures_or_retries(tmp_path, count, code):
    def factory(frame): return ScriptedTransport(frame, write_count=count)
    (_, receipt, _), transport = _execute(tmp_path, transport_factory=factory)
    assert receipt.status == "WRITE_UNCERTAIN_NO_RETRY"
    assert receipt.error_code == code
    assert transport.write_attempts == 1
    assert transport.capture_attempts == 0


def test_bad_ack_or_unsettled_feedback_is_uncertain(tmp_path):
    def factory(frame):
        capture = NativeT102ControllerCaptureV1(
            acknowledgment_bytes=encode_line({
                "T": 1021, "status": "ACCEPTED_ONCE", "ordinal": 2}),
            feedback_samples=_capture(frame).feedback_samples,
        )
        return ScriptedTransport(frame, capture=capture)
    (_, receipt, _), _ = _execute(tmp_path, transport_factory=factory)
    assert receipt.status == "EVIDENCE_UNCERTAIN_NO_RETRY"
    assert receipt.acknowledgment_sha256 is None


def test_authority_has_exactly_one_concurrent_consumer(tmp_path):
    root, handoff, frame, admission = _claimed(tmp_path)
    endpoint = _endpoint()
    _, authority = _authority(handoff, frame, endpoint)
    motion_permit = _motion_permit(_message(), admission)

    def consume(index):
        transport = ScriptedTransport(frame)
        try:
            execute_native_t102_production_candidate_v1(
                root, handoff, frame, admission, authority, endpoint, transport,
                motion_permit=motion_permit,
                adapter_candidate_sha256=ADAPTER,
                started_monotonic_ns=1_100 + index,
                assessment_monotonic_ns=1_200 + index,
                completed_monotonic_ns=1_250 + index,
            )
            return "CONSUMED"
        except (NativeT102ProductionTransportError, T102MachineLedgerError):
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(consume, range(8)))
    assert outcomes.count("CONSUMED") == 1
    assert outcomes.count("REJECTED") == 7


def test_native_sink_rejects_wrong_or_consumed_motion_permit_before_open(tmp_path):
    root, handoff, frame, admission = _claimed(tmp_path)
    endpoint = _endpoint()
    _, authority = _authority(handoff, frame, endpoint)
    transport = ScriptedTransport(frame)
    wrong = MotionPermit._issue(
        capability=admission.capability,
        snapshot_hash=admission.snapshot_sha256,
        plan_hash=admission.review_sha256,
        goals=(all_joint_command([0, 0, 0, 0, 0, 0], speed=20,
                                 acceleration=1),),
        ttl_s=102.0, now_monotonic=0.0,
    )
    with pytest.raises(NativeT102ProductionTransportError,
                       match="not consumable"):
        execute_native_t102_production_candidate_v1(
            root, handoff, frame, admission, authority, endpoint, transport,
            motion_permit=wrong, adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_100, assessment_monotonic_ns=1_200,
            completed_monotonic_ns=1_250,
        )
    assert transport.open_attempts == 0
    assert wrong.remaining_uses == 1


def test_reconstructed_authority_cannot_replay_with_another_receipt_root(
    tmp_path, machine_ledger,
):
    root, handoff, frame, admission = _claimed(tmp_path)
    endpoint = _endpoint()
    _, first_authority = _authority(handoff, frame, endpoint)
    execute_native_t102_production_candidate_v1(
        root, handoff, frame, admission, first_authority, endpoint,
        ScriptedTransport(frame),
        motion_permit=_motion_permit(_message(), admission),
        adapter_candidate_sha256=ADAPTER,
        started_monotonic_ns=1_100, assessment_monotonic_ns=1_200,
        completed_monotonic_ns=1_250,
    )
    other_root = tmp_path / "other-receipts"
    other_root.mkdir()
    _, reconstructed = _authority(handoff, frame, endpoint)
    second_transport = ScriptedTransport(frame)
    with pytest.raises(T102MachineLedgerError, match="already spent"):
        execute_native_t102_production_candidate_v1(
            other_root, handoff, frame, admission, reconstructed, endpoint,
            second_transport,
            motion_permit=_motion_permit(_message(), admission),
            adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_101, assessment_monotonic_ns=1_201,
            completed_monotonic_ns=1_251,
        )
    assert second_transport.open_attempts == 0
    assert len(tuple(machine_ledger.iterdir())) == 3


def test_rehashed_impossible_terminal_receipt_fails_closed(tmp_path):
    (journal, _, _), _ = _execute(tmp_path)
    path = journal.directory / "terminal.json"
    terminal = json.loads(path.read_text("utf-8"))
    receipt = terminal["transport_receipt"]
    receipt["confirmed_bytes"] = 0
    unsigned_receipt = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"}
    receipt["receipt_sha256"] = _hash(unsigned_receipt)
    unsigned_terminal = {
        key: value for key, value in terminal.items() if key != "terminal_sha256"}
    terminal["terminal_sha256"] = _hash(unsigned_terminal)
    path.write_bytes(json.dumps(
        terminal, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8"))
    with pytest.raises(NativeT102ProductionTransportError, match="receipt"):
        journal.snapshot()


def test_noncanonical_or_unexpected_attempt_content_fails_closed(tmp_path):
    root, handoff, frame, _ = _claimed(tmp_path)
    endpoint = _endpoint()
    _, authority = _authority(handoff, frame, endpoint)
    snapshot = handoff.snapshot()
    journal = DurableNativeT102ProductionAttemptV1.begin(
        root, claim_sha256=snapshot.claim_sha256,
        prepared_sha256=snapshot.prepared_sha256, frame=frame,
        authority=authority, endpoint=endpoint, started_monotonic_ns=1_100,
    )
    started = journal.directory / "started.json"
    started.write_bytes(started.read_bytes() + b"\n")
    with pytest.raises(NativeT102ProductionTransportError, match="noncanonical"):
        journal.snapshot()

    # A separate attempt proves an unexpected file fails before trusting state.
    other = tmp_path / "other"
    other.mkdir()
    root2, handoff2, frame2, _ = _claimed(other, reserve=False)
    endpoint2 = _endpoint()
    _, authority2 = _authority(handoff2, frame2, endpoint2)
    snapshot2 = handoff2.snapshot()
    journal2 = DurableNativeT102ProductionAttemptV1.begin(
        root2, claim_sha256=snapshot2.claim_sha256,
        prepared_sha256=snapshot2.prepared_sha256, frame=frame2,
        authority=authority2, endpoint=endpoint2, started_monotonic_ns=1_100,
    )
    (journal2.directory / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(NativeT102ProductionTransportError, match="entries"):
        journal2.snapshot()


def test_module_contains_no_concrete_transport_or_authority_issuer():
    assert NativeT102ProductionTransportV1.__abstractmethods__ == {
        "open_attempts", "write_attempts", "capture_attempts", "close_attempts",
        "open_once", "write_once", "capture_once", "close_once",
    }
    module = Path(__file__).resolve().parents[2] / "src/rocell/application" \
        / "native_t102_production_transport_v1.py"
    text = module.read_text(encoding="utf-8")
    assert "import serial" not in text
    assert "CreateFile" not in text
    assert "issue_external_native_t102" not in text
