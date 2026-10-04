"""Offline composition of ARM-050/053 with the real ARM-054 adapter class."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import pytest

from rocell.application.native_t102_handoff_journal_v1 import (
    DurableNativeT102HandoffV1,
)
import rocell.application.native_t102_production_transport_v1 as production_module
import rocell.application.t102_machine_ledger_v1 as ledger_module
from rocell.application.native_t102_production_transport_v1 import (
    ExternalAuthorityVerificationV1,
    ExternalNativeT102AuthorityRecordV1,
    NativeT102ProductionTransportError,
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
from rocell.providers.windows.native_t102_serial_transport_v1 import (
    WindowsNativeT102SerialTransportV1,
)
from rocell.rc03.build_snapshot import Capability
from rocell.safety.permit import MotionPermit, goal_hash


ADAPTER = "f" * 64


@pytest.fixture(autouse=True)
def machine_ledger(tmp_path, monkeypatch):
    root = tmp_path / "machine-ledger"
    root.mkdir()
    monkeypatch.setattr(ledger_module, "machine_root",
                        lambda: root)
    monkeypatch.setattr(production_module, "_machine_verifier",
                        lambda: Verifier())
    monkeypatch.setattr(production_module, "_trusted_monotonic_ns",
                        lambda: 1_070)
    monkeypatch.setattr(production_module, "_verify_machine_authority_at_sink",
                        lambda record, now: None)


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def message():
    return all_joint_command(
        [.1, .2, .3, .4, .5, .6], speed=20, acceleration=1)


def frame():
    return RuntimeCommandFrameV1(
        sequence=1, correlation_id="arm055-correlation-1",
        writer_instance_id="arm055-writer",
        controller_session_id="arm055-controller-session",
        configuration_epoch_sha256="d" * 64,
        encoding_profile_sha256="e" * 64,
        issued_monotonic_ns=900, expires_monotonic_ns=3_000,
        wire_bytes=encode_line(message()),
    )


def admission():
    values = dict(
        review_sha256="a" * 64, consumption_sha256="b" * 64,
        capability=Capability.KEYBOARD_CONTACT, snapshot_sha256="c" * 64,
        ordered_goal_sha256=(goal_hash(message()),),
        permit_expires_at_monotonic=102.0,
    )
    binding = digest({
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


def motion_permit(issued_admission):
    return MotionPermit._issue(
        capability=issued_admission.capability,
        snapshot_hash=issued_admission.snapshot_sha256,
        plan_hash=issued_admission.review_sha256,
        goals=(message(),), ttl_s=102.0, now_monotonic=0.0,
    )


def endpoint(port="COM7"):
    return PinnedNativeT102EndpointV1(
        port_name=port, usb_vid="10C4", usb_pid="EA60",
        usb_serial_number="ARM055UNIT001")


class Verifier:
    def verify_external_native_t102_authority(self, record, now_monotonic_ns):
        return ExternalAuthorityVerificationV1(
            approved=True,
            signed_payload_sha256=record.signed_payload_sha256,
            verifier_id="external-reviewer",
            verifier_build_sha256="8" * 64,
            verified_monotonic_ns=1_060,
            decision_code="APPROVED_EXACT_SINGLE_ACTION",
        )


def authority(handoff, command_frame, pinned):
    record = ExternalNativeT102AuthorityRecordV1(
        authority_id="arm055-authority-1",
        approval_record_sha256="9" * 64,
        review_sha256="a" * 64,
        claim_sha256=handoff.snapshot().claim_sha256,
        frame_sha256=command_frame.frame_sha256,
        wire_bytes_sha256=command_frame.wire_bytes_sha256,
        endpoint_sha256=pinned.endpoint_sha256,
        writer_instance_id=command_frame.writer_instance_id,
        controller_session_id=command_frame.controller_session_id,
        configuration_epoch_sha256=command_frame.configuration_epoch_sha256,
        encoding_profile_sha256=command_frame.encoding_profile_sha256,
        issued_monotonic_ns=1_050, expires_monotonic_ns=2_900,
        issuer_key_id="outside-authority-key-1",
        detached_signature="TEST-SIGNATURE-NOT-A-PRODUCTION-KEY",
    )
    return admit_external_native_t102_authority_v1(record)


@dataclass
class PortInfo:
    device: str = "COM7"
    vid: int = 0x10C4
    pid: int = 0xEA60
    serial_number: str = "ARM055UNIT001"


class Serial:
    def __init__(self, command_frame):
        response = encode_line({
            "T": 1051, "b": .1, "s": .2, "e": .3,
            "t": .4, "r": .5, "g": .6,
        })
        self.lines = [encode_line({
            "T": 1021, "status": "ACCEPTED_ONCE",
            "ordinal": command_frame.sequence,
        }), response, response]
        self.is_open = False
        self.in_waiting = 0
        self.writes = []
        self.opens = self.closes = 0

    def open(self): self.opens += 1; self.is_open = True
    def close(self): self.closes += 1; self.is_open = False
    def write(self, payload): self.writes.append(payload); return len(payload)
    def readline(self, maximum): return self.lines.pop(0)[:maximum]


def prepared(tmp_path):
    command_frame = frame()
    permit = admission()
    ledger_module.reserve_review(permit.consumption_sha256,
                                 permit.review_sha256,
                                 permit.ordered_goal_sha256[0])
    handoff_root = tmp_path / "handoff"
    receipt_root = tmp_path / "receipts"
    handoff_root.mkdir(); receipt_root.mkdir()
    handoff = DurableNativeT102HandoffV1.prepare(
        handoff_root, command_frame, permit,
        adapter_candidate_sha256=ADAPTER, created_monotonic_ns=950)
    handoff.claim_writer(
        command_frame, permit, adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_000)
    return receipt_root, handoff, command_frame, permit


def transport(serial):
    ticks = iter((1_150, 1_160))
    return WindowsNativeT102SerialTransportV1(
        serial_factory=lambda: serial,
        port_inventory=lambda: [PortInfo()],
        monotonic_ns=lambda: next(ticks),
    )


def test_real_adapter_class_composes_through_durable_authority_boundary(tmp_path):
    root, handoff, command_frame, permit = prepared(tmp_path)
    pinned = endpoint()
    admitted = authority(handoff, command_frame, pinned)
    native = Serial(command_frame)
    adapter = transport(native)
    journal, receipt, terminal = execute_native_t102_production_candidate_v1(
        root, handoff, command_frame, permit, admitted, pinned, adapter,
        motion_permit=motion_permit(permit),
        adapter_candidate_sha256=ADAPTER,
        started_monotonic_ns=1_100,
        assessment_monotonic_ns=1_200,
        completed_monotonic_ns=1_250,
    )
    assert receipt.status == "CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED"
    assert terminal.recovery_disposition is ProductionAttemptRecovery.TERMINAL_NO_REPLAY
    assert journal.snapshot() == terminal
    assert native.writes == [
        command_frame.wire_bytes, b'{"T":105}\n', b'{"T":105}\n']
    assert native.opens == native.closes == 1
    assert receipt.to_dict()["transport_implementation_qualified"] is False
    assert receipt.to_dict()["physical_movement_verified"] is False


def test_crossed_authority_is_durably_started_and_rejected_before_adapter_open(tmp_path):
    root, handoff, command_frame, permit = prepared(tmp_path)
    admitted = authority(handoff, command_frame, endpoint())
    native = Serial(command_frame)
    adapter = transport(native)
    with pytest.raises(NativeT102ProductionTransportError, match="binding or lifetime"):
        execute_native_t102_production_candidate_v1(
            root, handoff, command_frame, permit, admitted, endpoint("COM8"),
            adapter, motion_permit=motion_permit(permit), adapter_candidate_sha256=ADAPTER,
            started_monotonic_ns=1_100,
            assessment_monotonic_ns=1_200,
            completed_monotonic_ns=1_250,
        )
    assert adapter.open_attempts == 0
    assert native.opens == 0
    attempts = tuple(root.iterdir())
    assert len(attempts) == 1
    assert {item.name for item in attempts[0].iterdir()} == {"started.json"}
