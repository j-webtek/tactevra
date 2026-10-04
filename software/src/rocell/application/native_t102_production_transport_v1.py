"""Production-shaped native T=102 transport boundary with no bundled opener.

This module defines the exact endpoint, machine-pinned Ed25519 authority,
single-use ledger, transport, capture, and durable attempt contracts. The
repository does not contain an authority issuer or provisioned issuer key;
importing this module cannot enumerate or open hardware.

An execution attempt is made durable before ``open_once``.  Once that marker
exists, every outcome is no-retry, including a process crash.  Test doubles
may implement the abstract transport in tests, but their evidence remains
explicitly unqualified and is never promoted to an authentic physical result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import base64
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from threading import Lock
from typing import Any, Mapping, Protocol, Sequence

from rocell.arm.all_joint_command import JOINT_FIELDS
from rocell.arm.protocol import decode_line, encode_line
from rocell.safety.permit import MotionPermit, goal_hash

from .native_t102_handoff_journal_v1 import DurableNativeT102HandoffV1
from .production_controller_runtime_contract_v1 import RuntimeCommandFrameV1
from .reviewed_motion_permit_bridge_v1 import ReviewedMotionPermitAdmissionV1
from . import t102_machine_ledger_v1 as machine_ledger


ENDPOINT_SCHEMA = "rocell.native_t102_pinned_endpoint.v1"
AUTHORITY_SCHEMA = "rocell.external_native_t102_authority.v1"
VERIFICATION_SCHEMA = "rocell.external_native_t102_authority_verification.v1"
_AUTHORITY_ISSUER = object()


def _trusted_monotonic_ns() -> int:
    return time.monotonic_ns()
STARTED_SCHEMA = "rocell.native_t102_production_attempt_started.v1"
RECEIPT_SCHEMA = "rocell.native_t102_production_transport_receipt.v1"
TERMINAL_SCHEMA = "rocell.native_t102_production_attempt_terminal.v1"
SNAPSHOT_SCHEMA = "rocell.native_t102_production_attempt_snapshot.v1"
AUTHORITY_SCOPE = "NATIVE_T102_SINGLE_ACTION_PHYSICAL"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PORT = re.compile(r"^COM(?:[1-9][0-9]{0,2})$")
_HEX4 = re.compile(r"^[0-9A-F]{4}$")
_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FEEDBACK_FIELDS = ("b", "s", "e", "t", "r", "g")


class NativeT102ProductionTransportError(ValueError):
    """A production transport binding or lifecycle value is invalid."""


class ProductionAttemptRecovery(str, Enum):
    RETRY_FORBIDDEN_EXECUTION_UNCERTAIN = "RETRY_FORBIDDEN_EXECUTION_UNCERTAIN"
    TERMINAL_NO_REPLAY = "TERMINAL_NO_REPLAY"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeT102ProductionTransportError(
            "value is not canonical JSON") from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise NativeT102ProductionTransportError(
            f"{label} must be a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise NativeT102ProductionTransportError(
            f"{label} must be a bounded identifier")
    return value


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise NativeT102ProductionTransportError(
            f"{label} must be positive nanoseconds")
    return value


def _bounded_int(value: object, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) \
            or not low <= value <= high:
        raise NativeT102ProductionTransportError(
            f"{label} must be an integer in {low}..{high}")
    return value


@dataclass(frozen=True, slots=True)
class PinnedNativeT102EndpointV1:
    port_name: str
    usb_vid: str
    usb_pid: str
    usb_serial_number: str
    baud_rate: int = 115200
    data_bits: int = 8
    parity: str = "NONE"
    stop_bits: int = 1
    flow_control: str = "NONE"

    def __post_init__(self) -> None:
        if not isinstance(self.port_name, str) or _PORT.fullmatch(
                self.port_name) is None:
            raise NativeT102ProductionTransportError(
                "port_name must be one exact COM endpoint")
        if not isinstance(self.usb_vid, str) or _HEX4.fullmatch(
                self.usb_vid) is None:
            raise NativeT102ProductionTransportError("usb_vid must be uppercase hex")
        if not isinstance(self.usb_pid, str) or _HEX4.fullmatch(
                self.usb_pid) is None:
            raise NativeT102ProductionTransportError("usb_pid must be uppercase hex")
        if not isinstance(self.usb_serial_number, str) or _SERIAL.fullmatch(
                self.usb_serial_number) is None:
            raise NativeT102ProductionTransportError(
                "usb_serial_number must be exact and bounded")
        if self.baud_rate != 115200 or self.data_bits != 8 \
                or self.parity != "NONE" or self.stop_bits != 1 \
                or self.flow_control != "NONE":
            raise NativeT102ProductionTransportError(
                "endpoint serial configuration must be exact 115200 8N1 no-flow")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": ENDPOINT_SCHEMA,
            "port_name": self.port_name,
            "usb_vid": self.usb_vid,
            "usb_pid": self.usb_pid,
            "usb_serial_number": self.usb_serial_number,
            "baud_rate": self.baud_rate,
            "data_bits": self.data_bits,
            "parity": self.parity,
            "stop_bits": self.stop_bits,
            "flow_control": self.flow_control,
        }

    @property
    def endpoint_sha256(self) -> str:
        return _hash(self.unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "endpoint_sha256": self.endpoint_sha256}


@dataclass(frozen=True, slots=True)
class ExternalNativeT102AuthorityRecordV1:
    authority_id: str
    approval_record_sha256: str
    review_sha256: str
    claim_sha256: str
    frame_sha256: str
    wire_bytes_sha256: str
    endpoint_sha256: str
    writer_instance_id: str
    controller_session_id: str
    configuration_epoch_sha256: str
    encoding_profile_sha256: str
    issued_monotonic_ns: int
    expires_monotonic_ns: int
    issuer_key_id: str
    detached_signature: str

    def __post_init__(self) -> None:
        _identifier(self.authority_id, "authority_id")
        _identifier(self.writer_instance_id, "writer_instance_id")
        _identifier(self.controller_session_id, "controller_session_id")
        _identifier(self.issuer_key_id, "issuer_key_id")
        for name in (
            "approval_record_sha256", "review_sha256", "claim_sha256", "frame_sha256",
            "wire_bytes_sha256", "endpoint_sha256",
            "configuration_epoch_sha256", "encoding_profile_sha256",
        ):
            _digest(getattr(self, name), name)
        issued = _positive_ns(self.issued_monotonic_ns, "issued_monotonic_ns")
        expires = _positive_ns(self.expires_monotonic_ns, "expires_monotonic_ns")
        if expires <= issued:
            raise NativeT102ProductionTransportError(
                "authority expiry must follow issuance")
        if not isinstance(self.detached_signature, str) \
                or not 16 <= len(self.detached_signature) <= 4096 \
                or any(ord(char) < 33 or ord(char) > 126
                       for char in self.detached_signature):
            raise NativeT102ProductionTransportError(
                "detached_signature must be bounded printable text")

    def signed_payload(self) -> dict[str, Any]:
        return {
            "schema": AUTHORITY_SCHEMA,
            "scope": AUTHORITY_SCOPE,
            "authority_id": self.authority_id,
            "issuer_key_id": self.issuer_key_id,
            "approval_record_sha256": self.approval_record_sha256,
            "review_sha256": self.review_sha256,
            "claim_sha256": self.claim_sha256,
            "frame_sha256": self.frame_sha256,
            "wire_bytes_sha256": self.wire_bytes_sha256,
            "endpoint_sha256": self.endpoint_sha256,
            "writer_instance_id": self.writer_instance_id,
            "controller_session_id": self.controller_session_id,
            "configuration_epoch_sha256": self.configuration_epoch_sha256,
            "encoding_profile_sha256": self.encoding_profile_sha256,
            "issued_monotonic_ns": self.issued_monotonic_ns,
            "expires_monotonic_ns": self.expires_monotonic_ns,
            "maximum_uses": 1,
            "automatic_retry_allowed": False,
        }

    @property
    def signed_payload_sha256(self) -> str:
        return _hash(self.signed_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.signed_payload(),
            "detached_signature": self.detached_signature,
            "signed_payload_sha256": self.signed_payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class ExternalAuthorityVerificationV1:
    approved: bool
    signed_payload_sha256: str
    verifier_id: str
    verifier_build_sha256: str
    verified_monotonic_ns: int
    decision_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.approved, bool):
            raise TypeError("approved must be bool")
        _digest(self.signed_payload_sha256, "signed_payload_sha256")
        _identifier(self.verifier_id, "verifier_id")
        _digest(self.verifier_build_sha256, "verifier_build_sha256")
        _positive_ns(self.verified_monotonic_ns, "verified_monotonic_ns")
        _identifier(self.decision_code, "decision_code")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": VERIFICATION_SCHEMA,
            "approved": self.approved,
            "signed_payload_sha256": self.signed_payload_sha256,
            "verifier_id": self.verifier_id,
            "verifier_build_sha256": self.verifier_build_sha256,
            "verified_monotonic_ns": self.verified_monotonic_ns,
            "decision_code": self.decision_code,
        }

    @property
    def verification_sha256(self) -> str:
        return _hash(self.unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(),
                "verification_sha256": self.verification_sha256}


class ExternalNativeT102AuthorityVerifierV1(Protocol):
    """Verification interface; production selects the machine-pinned verifier."""

    def verify_external_native_t102_authority(
        self, record: ExternalNativeT102AuthorityRecordV1,
        now_monotonic_ns: int,
    ) -> ExternalAuthorityVerificationV1: ...


class MachinePinnedEd25519AuthorityVerifierV1:
    """Verify an external issuer signature with an installed public keyring."""

    def verify_external_native_t102_authority(
        self, record: ExternalNativeT102AuthorityRecordV1,
        now_monotonic_ns: int,
    ) -> ExternalAuthorityVerificationV1:
        path = machine_ledger.machine_root().parent / "t102-authority-keys-v1.json"
        if path.is_symlink() or not path.is_file():
            raise NativeT102ProductionTransportError(
                "machine T102 issuer keyring is unavailable")
        try:
            with path.open("rb") as stream:
                raw = stream.read(16_385)
            if len(raw) > 16_384:
                raise ValueError("oversized keyring")
            document = json.loads(raw)
            if set(document) != {"schema", "keys"} or document["schema"] != (
                "rocell.native_t102_issuer_keyring.v1"
            ) or not isinstance(document["keys"], dict):
                raise ValueError("invalid keyring")
            encoded_key = document["keys"][record.issuer_key_id]
            if not isinstance(encoded_key, str):
                raise ValueError("invalid issuer key")
            key_bytes = base64.b64decode(encoded_key, validate=True)
            signature = base64.b64decode(record.detached_signature, validate=True)
            if len(key_bytes) != 32 or len(signature) != 64:
                raise ValueError("invalid Ed25519 sizes")
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
            Ed25519PublicKey.from_public_bytes(key_bytes).verify(
                signature, _canonical(record.signed_payload()))
        except Exception as exc:
            raise NativeT102ProductionTransportError(
                "external T102 authority signature was not verified") from exc
        return ExternalAuthorityVerificationV1(
            approved=True,
            signed_payload_sha256=record.signed_payload_sha256,
            verifier_id="machine-pinned-ed25519-v1",
            verifier_build_sha256=hashlib.sha256(
                b"rocell.machine-pinned-ed25519-v1").hexdigest(),
            verified_monotonic_ns=now_monotonic_ns,
            decision_code="APPROVED_EXACT_SINGLE_ACTION",
        )


def _machine_verifier() -> ExternalNativeT102AuthorityVerifierV1:
    return MachinePinnedEd25519AuthorityVerifierV1()


def _verify_machine_authority_at_sink(
    record: ExternalNativeT102AuthorityRecordV1,
    now_monotonic_ns: int,
) -> None:
    decision = MachinePinnedEd25519AuthorityVerifierV1().verify_external_native_t102_authority(
        record, now_monotonic_ns)
    if (
        decision.approved is not True
        or decision.signed_payload_sha256 != record.signed_payload_sha256
    ):
        raise NativeT102ProductionTransportError(
            "native T102 sink rejected external issuer signature")


class AdmittedExternalNativeT102AuthorityV1:
    """A verified record with process-local, atomic, one-use consumption."""

    def __init__(
        self, record: ExternalNativeT102AuthorityRecordV1,
        verification: ExternalAuthorityVerificationV1,
        *, _issuer: object,
    ) -> None:
        if _issuer is not _AUTHORITY_ISSUER:
            raise NativeT102ProductionTransportError(
                "admitted authority must come from the machine verifier")
        self.record = record
        self.verification = verification
        self._consumed = False
        self._lock = Lock()

    def consume(
        self, *, claim_sha256: str, frame: RuntimeCommandFrameV1,
        endpoint: PinnedNativeT102EndpointV1, now_monotonic_ns: int,
    ) -> None:
        if not isinstance(frame, RuntimeCommandFrameV1):
            raise TypeError("frame must be RuntimeCommandFrameV1")
        if not isinstance(endpoint, PinnedNativeT102EndpointV1):
            raise TypeError("endpoint must be PinnedNativeT102EndpointV1")
        now = _positive_ns(now_monotonic_ns, "now_monotonic_ns")
        with self._lock:
            if self._consumed:
                raise NativeT102ProductionTransportError(
                    "external authority already consumed; no retry")
            record = self.record
            if (
                claim_sha256 != record.claim_sha256
                or frame.frame_sha256 != record.frame_sha256
                or frame.wire_bytes_sha256 != record.wire_bytes_sha256
                or endpoint.endpoint_sha256 != record.endpoint_sha256
                or frame.writer_instance_id != record.writer_instance_id
                or frame.controller_session_id != record.controller_session_id
                or frame.configuration_epoch_sha256
                != record.configuration_epoch_sha256
                or frame.encoding_profile_sha256 != record.encoding_profile_sha256
                or not record.issued_monotonic_ns <= now
                < record.expires_monotonic_ns
                or now >= frame.expires_monotonic_ns
            ):
                raise NativeT102ProductionTransportError(
                    "external authority binding or lifetime differs")
            self._consumed = True


def admit_external_native_t102_authority_v1(
    record: ExternalNativeT102AuthorityRecordV1,
) -> AdmittedExternalNativeT102AuthorityV1:
    """Verify against the installed issuer keyring, never a caller verifier."""

    if not isinstance(record, ExternalNativeT102AuthorityRecordV1):
        raise TypeError("record must be ExternalNativeT102AuthorityRecordV1")
    now = _positive_ns(_trusted_monotonic_ns(), "trusted_monotonic_ns")
    method = getattr(_machine_verifier(), "verify_external_native_t102_authority", None)
    if not callable(method):
        raise TypeError("an external native T102 authority verifier is required")
    result = method(record, now)
    if not isinstance(result, ExternalAuthorityVerificationV1):
        raise NativeT102ProductionTransportError(
            "external verifier returned an invalid decision")
    if (
        result.approved is not True
        or result.decision_code != "APPROVED_EXACT_SINGLE_ACTION"
        or result.signed_payload_sha256 != record.signed_payload_sha256
        or not record.issued_monotonic_ns <= result.verified_monotonic_ns
        < record.expires_monotonic_ns
        or result.verified_monotonic_ns > now
        or not record.issued_monotonic_ns <= now < record.expires_monotonic_ns
    ):
        raise NativeT102ProductionTransportError(
            "external authority was not positively verified for this lifetime")
    return AdmittedExternalNativeT102AuthorityV1(
        record, result, _issuer=_AUTHORITY_ISSUER)


@dataclass(frozen=True, slots=True)
class NativeT102FeedbackSampleV1:
    captured_monotonic_ns: int
    response_bytes: bytes

    def __post_init__(self) -> None:
        _positive_ns(self.captured_monotonic_ns, "captured_monotonic_ns")
        if not isinstance(self.response_bytes, bytes) \
                or not 1 <= len(self.response_bytes) <= 1024:
            raise NativeT102ProductionTransportError(
                "feedback response must be bounded bytes")


@dataclass(frozen=True, slots=True)
class NativeT102ControllerCaptureV1:
    acknowledgment_bytes: bytes
    feedback_samples: tuple[NativeT102FeedbackSampleV1, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.acknowledgment_bytes, bytes) \
                or not 1 <= len(self.acknowledgment_bytes) <= 1024:
            raise NativeT102ProductionTransportError(
                "acknowledgment must be bounded bytes")
        if not isinstance(self.feedback_samples, tuple) \
                or not 1 <= len(self.feedback_samples) <= 16 \
                or not all(isinstance(item, NativeT102FeedbackSampleV1)
                           for item in self.feedback_samples):
            raise NativeT102ProductionTransportError(
                "feedback_samples must contain 1..16 typed samples")


class NativeT102ProductionTransportV1(ABC):
    """Abstract exact transport.  No concrete hardware implementation ships."""

    @property
    @abstractmethod
    def open_attempts(self) -> int: ...

    @property
    @abstractmethod
    def write_attempts(self) -> int: ...

    @property
    @abstractmethod
    def capture_attempts(self) -> int: ...

    @property
    @abstractmethod
    def close_attempts(self) -> int: ...

    @abstractmethod
    def open_once(
        self, endpoint: PinnedNativeT102EndpointV1,
    ) -> PinnedNativeT102EndpointV1: ...

    @abstractmethod
    def write_once(self, payload: bytes) -> int: ...

    @abstractmethod
    def capture_once(self) -> NativeT102ControllerCaptureV1: ...

    @abstractmethod
    def close_once(self) -> None: ...

    def bind_execution(self, grant: NativeT102ExecutionGrantV1) -> None:
        """Bind a checked execution to a concrete hardware provider."""


_TRANSPORT_GRANT_ISSUER = object()


class NativeT102ExecutionGrantV1:
    """Process-local binding for the one hardware open/write lifecycle."""

    def __init__(self, endpoint_sha256: str, wire_bytes: bytes, *, _issuer: object) -> None:
        if _issuer is not _TRANSPORT_GRANT_ISSUER:
            raise NativeT102ProductionTransportError("transport grant issuer required")
        self.endpoint_sha256 = endpoint_sha256
        self.wire_bytes = wire_bytes
        self._spent = False
        self._lock = Lock()

    def consume(self, endpoint_sha256: str, wire_bytes: bytes) -> None:
        with self._lock:
            if self._spent or self.endpoint_sha256 != endpoint_sha256 \
                    or self.wire_bytes != wire_bytes:
                raise NativeT102ProductionTransportError(
                    "transport grant spent or differs from exact execution")
            self._spent = True


def _issue_native_t102_execution_grant_v1(
    endpoint: PinnedNativeT102EndpointV1, frame: RuntimeCommandFrameV1,
) -> NativeT102ExecutionGrantV1:
    return NativeT102ExecutionGrantV1(
        endpoint.endpoint_sha256, frame.wire_bytes, _issuer=_TRANSPORT_GRANT_ISSUER)


@dataclass(frozen=True, slots=True)
class NativeT102ProductionTransportReceiptV1:
    status: str
    authority_sha256: str
    verification_sha256: str
    approval_record_sha256: str
    claim_sha256: str
    prepared_sha256: str
    frame_sha256: str
    wire_bytes_sha256: str
    endpoint_sha256: str
    correlation_id: str
    writer_instance_id: str
    controller_session_id: str
    requested_bytes: int
    confirmed_bytes: int
    open_attempts: int
    write_attempts: int
    capture_attempts: int
    close_attempts: int
    acknowledgment_sha256: str | None
    feedback_response_sha256: tuple[str, ...]
    maximum_joint_error_rad: float | None
    error_code: str | None

    def __post_init__(self) -> None:
        allowed_status = {
            "CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED",
            "ENDPOINT_IDENTITY_MISMATCH_NO_WRITE",
            "NOT_OPENED_AUTHORITY_CONSUMED_NO_RETRY",
            "WRITE_UNCERTAIN_NO_RETRY",
            "EVIDENCE_UNCERTAIN_NO_RETRY",
            "CLOSE_UNCERTAIN_NO_RETRY",
        }
        allowed_error = {
            None, "ENDPOINT_IDENTITY_MISMATCH", "OPEN_FAILURE", "ZERO_WRITE",
            "PARTIAL_WRITE", "INVALID_WRITE_COUNT", "WRITE_EXCEPTION",
            "CAPTURE_OR_EVIDENCE_FAILURE", "CLOSE_FAILURE",
        }
        if self.status not in allowed_status or self.error_code not in allowed_error:
            raise NativeT102ProductionTransportError(
                "receipt status or error code is invalid")
        for name in (
            "authority_sha256", "verification_sha256", "approval_record_sha256",
            "claim_sha256", "prepared_sha256", "frame_sha256",
            "wire_bytes_sha256", "endpoint_sha256",
        ):
            _digest(getattr(self, name), name)
        _identifier(self.correlation_id, "correlation_id")
        _identifier(self.writer_instance_id, "writer_instance_id")
        _identifier(self.controller_session_id, "controller_session_id")
        requested = _bounded_int(
            self.requested_bytes, "requested_bytes", 1, 65536)
        confirmed = _bounded_int(
            self.confirmed_bytes, "confirmed_bytes", 0, requested)
        for name in ("open_attempts", "write_attempts", "capture_attempts",
                     "close_attempts"):
            _bounded_int(getattr(self, name), name, 0, 1)
        if self.acknowledgment_sha256 is not None:
            _digest(self.acknowledgment_sha256, "acknowledgment_sha256")
        if not isinstance(self.feedback_response_sha256, tuple) \
                or len(self.feedback_response_sha256) > 16:
            raise NativeT102ProductionTransportError(
                "feedback response hashes must be a bounded tuple")
        for digest in self.feedback_response_sha256:
            _digest(digest, "feedback_response_sha256")
        if self.maximum_joint_error_rad is not None and (
            isinstance(self.maximum_joint_error_rad, bool)
            or not isinstance(self.maximum_joint_error_rad, (int, float))
            or not math.isfinite(float(self.maximum_joint_error_rad))
            or not 0 <= float(self.maximum_joint_error_rad) <= 100
        ):
            raise NativeT102ProductionTransportError(
                "maximum_joint_error_rad must be bounded and finite")
        if self.status == "CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED":
            if (
                self.error_code is not None or confirmed != requested
                or (self.open_attempts, self.write_attempts,
                    self.capture_attempts, self.close_attempts) != (1, 1, 1, 1)
                or self.acknowledgment_sha256 is None
                or len(self.feedback_response_sha256) < 2
                or self.maximum_joint_error_rad is None
            ):
                raise NativeT102ProductionTransportError(
                    "settled receipt content is inconsistent")
        elif self.status == "ENDPOINT_IDENTITY_MISMATCH_NO_WRITE":
            if (
                self.error_code != "ENDPOINT_IDENTITY_MISMATCH"
                or confirmed or self.write_attempts or self.capture_attempts
                or self.open_attempts != 1 or self.acknowledgment_sha256 is not None
                or self.feedback_response_sha256
                or self.maximum_joint_error_rad is not None
            ):
                raise NativeT102ProductionTransportError(
                    "endpoint mismatch receipt content is inconsistent")
        elif self.status == "NOT_OPENED_AUTHORITY_CONSUMED_NO_RETRY":
            if self.error_code != "OPEN_FAILURE" or confirmed \
                    or self.write_attempts or self.capture_attempts:
                raise NativeT102ProductionTransportError(
                    "open-failure receipt content is inconsistent")
        elif self.status == "WRITE_UNCERTAIN_NO_RETRY":
            if self.error_code not in {
                "ZERO_WRITE", "PARTIAL_WRITE", "INVALID_WRITE_COUNT",
                "WRITE_EXCEPTION",
            } or self.write_attempts != 1 or self.capture_attempts:
                raise NativeT102ProductionTransportError(
                    "write-uncertain receipt content is inconsistent")
        elif self.status == "EVIDENCE_UNCERTAIN_NO_RETRY":
            if self.error_code != "CAPTURE_OR_EVIDENCE_FAILURE" \
                    or confirmed != requested or self.write_attempts != 1 \
                    or self.capture_attempts != 1:
                raise NativeT102ProductionTransportError(
                    "evidence-uncertain receipt content is inconsistent")
        elif self.status == "CLOSE_UNCERTAIN_NO_RETRY" \
                and self.error_code != "CLOSE_FAILURE":
            raise NativeT102ProductionTransportError(
                "close-uncertain receipt content is inconsistent")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA,
            "status": self.status,
            "authority_sha256": self.authority_sha256,
            "verification_sha256": self.verification_sha256,
            "approval_record_sha256": self.approval_record_sha256,
            "claim_sha256": self.claim_sha256,
            "prepared_sha256": self.prepared_sha256,
            "frame_sha256": self.frame_sha256,
            "wire_bytes_sha256": self.wire_bytes_sha256,
            "endpoint_sha256": self.endpoint_sha256,
            "correlation_id": self.correlation_id,
            "writer_instance_id": self.writer_instance_id,
            "controller_session_id": self.controller_session_id,
            "requested_bytes": self.requested_bytes,
            "confirmed_bytes": self.confirmed_bytes,
            "open_attempts": self.open_attempts,
            "write_attempts": self.write_attempts,
            "capture_attempts": self.capture_attempts,
            "close_attempts": self.close_attempts,
            "acknowledgment_sha256": self.acknowledgment_sha256,
            "feedback_response_sha256": list(self.feedback_response_sha256),
            "maximum_joint_error_rad": self.maximum_joint_error_rad,
            "error_code": self.error_code,
            "automatic_retry_allowed": False,
            "follow_on_movement_authorized": False,
            "external_authority_verification_record_accepted": True,
            "physical_authority_claimed": False,
            "transport_implementation_qualified": False,
            "authentic_controller_receipt_claimed": False,
            "physical_movement_verified": False,
        }

    @property
    def receipt_sha256(self) -> str:
        return _hash(self.unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "receipt_sha256": self.receipt_sha256}


def _safe_root(root: Path) -> Path:
    if not isinstance(root, Path) or not root.is_absolute() or not root.is_dir() \
            or root.is_symlink():
        raise NativeT102ProductionTransportError(
            "attempt root must be an existing absolute non-symlink directory")
    return root.resolve(strict=True)


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    data = _canonical(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    if os.name != "nt":
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _read_canonical(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise NativeT102ProductionTransportError(
            f"attempt record is unavailable: {path.name}")
    size = path.stat().st_size
    if not 2 <= size <= 131072:
        raise NativeT102ProductionTransportError(
            f"attempt record size is invalid: {path.name}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeT102ProductionTransportError(
            f"attempt record is malformed: {path.name}") from exc
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise NativeT102ProductionTransportError(
            f"attempt record is noncanonical: {path.name}")
    return value


@dataclass(frozen=True, slots=True)
class ProductionAttemptSnapshotV1:
    directory: Path
    recovery_disposition: ProductionAttemptRecovery
    started_sha256: str
    terminal_sha256: str | None
    receipt_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        unsigned = {
            "schema": SNAPSHOT_SCHEMA,
            "recovery_disposition": self.recovery_disposition.value,
            "started_sha256": self.started_sha256,
            "terminal_sha256": self.terminal_sha256,
            "receipt_sha256": self.receipt_sha256,
            "automatic_retry_allowed": False,
            "replay_allowed": False,
        }
        return {**unsigned, "snapshot_sha256": _hash(unsigned)}


class DurableNativeT102ProductionAttemptV1:
    """Immutable started/terminal pair; started is flushed before native open."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @classmethod
    def begin(
        cls, root: Path, *, claim_sha256: str, prepared_sha256: str,
        frame: RuntimeCommandFrameV1,
        authority: AdmittedExternalNativeT102AuthorityV1,
        endpoint: PinnedNativeT102EndpointV1,
        started_monotonic_ns: int,
    ) -> "DurableNativeT102ProductionAttemptV1":
        base = _safe_root(root)
        started_ns = _positive_ns(started_monotonic_ns, "started_monotonic_ns")
        _digest(claim_sha256, "claim_sha256")
        _digest(prepared_sha256, "prepared_sha256")
        attempt_id = _hash({
            "claim_sha256": claim_sha256,
            "authority_sha256": authority.record.signed_payload_sha256,
            "endpoint_sha256": endpoint.endpoint_sha256,
        })
        directory = base / attempt_id
        try:
            directory.mkdir(mode=0o700, exist_ok=False)
        except OSError as exc:
            raise NativeT102ProductionTransportError(
                "production attempt already exists or cannot be created") from exc
        core = {
            "schema": STARTED_SCHEMA,
            "status": "EXECUTION_STARTED_BEFORE_TRANSPORT_OPEN",
            "claim_sha256": claim_sha256,
            "prepared_sha256": prepared_sha256,
            "frame_sha256": frame.frame_sha256,
            "wire_bytes_sha256": frame.wire_bytes_sha256,
            "authority_sha256": authority.record.signed_payload_sha256,
            "verification_sha256": authority.verification.verification_sha256,
            "endpoint_sha256": endpoint.endpoint_sha256,
            "correlation_id": frame.correlation_id,
            "writer_instance_id": frame.writer_instance_id,
            "controller_session_id": frame.controller_session_id,
            "started_monotonic_ns": started_ns,
            "automatic_retry_allowed": False,
            "transport_open_count": 0,
            "physical_command_writes": 0,
        }
        _write_new(directory / "started.json", {
            **core, "started_sha256": _hash(core)})
        return cls(directory)

    def snapshot(self) -> ProductionAttemptSnapshotV1:
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise NativeT102ProductionTransportError(
                "attempt directory is unavailable")
        names = {item.name for item in self.directory.iterdir()}
        if names not in ({"started.json"}, {"started.json", "terminal.json"}):
            raise NativeT102ProductionTransportError(
                "attempt directory entries are not exact")
        started = _read_canonical(self.directory / "started.json")
        started_hash = started.pop("started_sha256", None)
        if started.get("schema") != STARTED_SCHEMA or started_hash != _hash(started):
            raise NativeT102ProductionTransportError("started record is invalid")
        if "terminal.json" not in names:
            return ProductionAttemptSnapshotV1(
                self.directory,
                ProductionAttemptRecovery.RETRY_FORBIDDEN_EXECUTION_UNCERTAIN,
                started_hash, None, None,
            )
        terminal = _read_canonical(self.directory / "terminal.json")
        terminal_hash = terminal.pop("terminal_sha256", None)
        if terminal.get("schema") != TERMINAL_SCHEMA \
                or terminal_hash != _hash(terminal) \
                or terminal.get("started_sha256") != started_hash:
            raise NativeT102ProductionTransportError("terminal record is invalid")
        receipt = terminal.get("transport_receipt")
        if not isinstance(receipt, dict):
            raise NativeT102ProductionTransportError("terminal receipt is invalid")
        try:
            typed = NativeT102ProductionTransportReceiptV1(
                status=receipt["status"],
                authority_sha256=receipt["authority_sha256"],
                verification_sha256=receipt["verification_sha256"],
                approval_record_sha256=receipt["approval_record_sha256"],
                claim_sha256=receipt["claim_sha256"],
                prepared_sha256=receipt["prepared_sha256"],
                frame_sha256=receipt["frame_sha256"],
                wire_bytes_sha256=receipt["wire_bytes_sha256"],
                endpoint_sha256=receipt["endpoint_sha256"],
                correlation_id=receipt["correlation_id"],
                writer_instance_id=receipt["writer_instance_id"],
                controller_session_id=receipt["controller_session_id"],
                requested_bytes=receipt["requested_bytes"],
                confirmed_bytes=receipt["confirmed_bytes"],
                open_attempts=receipt["open_attempts"],
                write_attempts=receipt["write_attempts"],
                capture_attempts=receipt["capture_attempts"],
                close_attempts=receipt["close_attempts"],
                acknowledgment_sha256=receipt["acknowledgment_sha256"],
                feedback_response_sha256=tuple(
                    receipt["feedback_response_sha256"]),
                maximum_joint_error_rad=receipt["maximum_joint_error_rad"],
                error_code=receipt["error_code"],
            )
        except (KeyError, TypeError, NativeT102ProductionTransportError) as exc:
            raise NativeT102ProductionTransportError(
                "terminal receipt is invalid") from exc
        if typed.to_dict() != receipt:
            raise NativeT102ProductionTransportError("terminal receipt is invalid")
        for key in (
            "claim_sha256", "prepared_sha256", "frame_sha256",
            "wire_bytes_sha256", "authority_sha256", "verification_sha256",
            "endpoint_sha256", "correlation_id", "writer_instance_id",
            "controller_session_id",
        ):
            if receipt[key] != started[key]:
                raise NativeT102ProductionTransportError(
                    "terminal receipt crosses the durable start binding")
        return ProductionAttemptSnapshotV1(
            self.directory, ProductionAttemptRecovery.TERMINAL_NO_REPLAY,
            started_hash, terminal_hash, receipt["receipt_sha256"],
        )

    def commit_terminal(
        self, receipt: NativeT102ProductionTransportReceiptV1, *,
        completed_monotonic_ns: int,
    ) -> ProductionAttemptSnapshotV1:
        if not isinstance(receipt, NativeT102ProductionTransportReceiptV1):
            raise TypeError("receipt must be NativeT102ProductionTransportReceiptV1")
        before = self.snapshot()
        if before.recovery_disposition is ProductionAttemptRecovery.TERMINAL_NO_REPLAY:
            raise NativeT102ProductionTransportError(
                "attempt already has a terminal receipt")
        started = _read_canonical(self.directory / "started.json")
        completed = _positive_ns(completed_monotonic_ns, "completed_monotonic_ns")
        if completed < started["started_monotonic_ns"]:
            raise NativeT102ProductionTransportError("terminal time precedes start")
        expected = {
            "claim_sha256": started["claim_sha256"],
            "prepared_sha256": started["prepared_sha256"],
            "frame_sha256": started["frame_sha256"],
            "wire_bytes_sha256": started["wire_bytes_sha256"],
            "authority_sha256": started["authority_sha256"],
            "verification_sha256": started["verification_sha256"],
            "endpoint_sha256": started["endpoint_sha256"],
            "correlation_id": started["correlation_id"],
            "writer_instance_id": started["writer_instance_id"],
            "controller_session_id": started["controller_session_id"],
        }
        actual = receipt.to_dict()
        if any(actual[key] != value for key, value in expected.items()):
            raise NativeT102ProductionTransportError(
                "terminal receipt differs from durable start binding")
        core = {
            "schema": TERMINAL_SCHEMA,
            "status": "TERMINAL_NO_REPLAY",
            "started_sha256": before.started_sha256,
            "completed_monotonic_ns": completed,
            "transport_receipt": actual,
            "automatic_retry_allowed": False,
            "replay_allowed": False,
        }
        _write_new(self.directory / "terminal.json", {
            **core, "terminal_sha256": _hash(core)})
        return self.snapshot()


def _validate_capture(
    frame: RuntimeCommandFrameV1, capture: NativeT102ControllerCaptureV1, *,
    dispatch_monotonic_ns: int, assessment_monotonic_ns: int,
    tolerance_rad: float,
) -> tuple[str, tuple[str, ...], float]:
    expected_ack = {
        "T": 1021, "status": "ACCEPTED_ONCE", "ordinal": frame.sequence}
    if decode_line(capture.acknowledgment_bytes) != expected_ack \
            or encode_line(expected_ack) != capture.acknowledgment_bytes:
        raise NativeT102ProductionTransportError(
            "T1021 acknowledgment differs from dispatched frame")
    target = decode_line(frame.wire_bytes)
    previous = dispatch_monotonic_ns
    hashes: list[str] = []
    maximum_error = 0.0
    settled = 0
    for sample in capture.feedback_samples:
        if not previous < sample.captured_monotonic_ns <= assessment_monotonic_ns:
            raise NativeT102ProductionTransportError(
                "T1051 feedback time is stale, future, or nonmonotonic")
        previous = sample.captured_monotonic_ns
        parsed = decode_line(sample.response_bytes)
        if parsed.get("T") != 1051 or any(
                name not in parsed for name in _FEEDBACK_FIELDS):
            raise NativeT102ProductionTransportError(
                "T1051 feedback lacks exact joint evidence")
        values = []
        for name in _FEEDBACK_FIELDS:
            value = parsed[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise NativeT102ProductionTransportError(
                    "T1051 joint value must be finite")
            values.append(float(value))
        error = max(abs(value - float(target[target_name]))
                    for target_name, value in zip(JOINT_FIELDS, values))
        maximum_error = max(maximum_error, error)
        settled = settled + 1 if error <= tolerance_rad else 0
        hashes.append(hashlib.sha256(sample.response_bytes).hexdigest())
    if settled < 2:
        raise NativeT102ProductionTransportError(
            "two consecutive settled T1051 samples are required")
    return (hashlib.sha256(capture.acknowledgment_bytes).hexdigest(),
            tuple(hashes), maximum_error)


def execute_native_t102_production_candidate_v1(
    receipt_root: Path,
    handoff: DurableNativeT102HandoffV1,
    frame: RuntimeCommandFrameV1,
    admission: ReviewedMotionPermitAdmissionV1,
    authority: AdmittedExternalNativeT102AuthorityV1,
    endpoint: PinnedNativeT102EndpointV1,
    transport: NativeT102ProductionTransportV1, *,
    motion_permit: MotionPermit,
    adapter_candidate_sha256: str,
    started_monotonic_ns: int,
    assessment_monotonic_ns: int,
    completed_monotonic_ns: int,
    settlement_tolerance_rad: float = 0.04,
) -> tuple[
    DurableNativeT102ProductionAttemptV1,
    NativeT102ProductionTransportReceiptV1,
    ProductionAttemptSnapshotV1,
]:
    """Run one abstract production-shaped lifecycle; never retry internally."""

    if not isinstance(handoff, DurableNativeT102HandoffV1):
        raise TypeError("handoff must be DurableNativeT102HandoffV1")
    if not isinstance(authority, AdmittedExternalNativeT102AuthorityV1):
        raise TypeError("authority must be admitted externally")
    if not isinstance(endpoint, PinnedNativeT102EndpointV1):
        raise TypeError("endpoint must be PinnedNativeT102EndpointV1")
    if not isinstance(transport, NativeT102ProductionTransportV1):
        raise TypeError("transport must implement NativeT102ProductionTransportV1")
    if not isinstance(motion_permit, MotionPermit):
        raise TypeError("motion_permit must be a MotionPermit")
    if not isinstance(admission, ReviewedMotionPermitAdmissionV1):
        raise TypeError("admission must be ReviewedMotionPermitAdmissionV1")
    if isinstance(settlement_tolerance_rad, bool) \
            or not isinstance(settlement_tolerance_rad, (int, float)) \
            or not 0 <= float(settlement_tolerance_rad) <= 0.25:
        raise NativeT102ProductionTransportError(
            "settlement_tolerance_rad must be in 0..0.25")
    started_ns = _positive_ns(started_monotonic_ns, "started_monotonic_ns")
    assessment_ns = _positive_ns(
        assessment_monotonic_ns, "assessment_monotonic_ns")
    completed_ns = _positive_ns(completed_monotonic_ns, "completed_monotonic_ns")
    if not started_ns <= assessment_ns <= completed_ns:
        raise NativeT102ProductionTransportError(
            "attempt times must be monotonic")
    trusted_now = _positive_ns(_trusted_monotonic_ns(), "trusted_monotonic_ns")
    if (
        trusted_now >= frame.expires_monotonic_ns
        or trusted_now < authority.record.issued_monotonic_ns
        or trusted_now >= authority.record.expires_monotonic_ns
    ):
        raise NativeT102ProductionTransportError(
            "native T102 frame or external authority expired")
    if (
        authority.verification.approved is not True
        or authority.verification.decision_code
        != "APPROVED_EXACT_SINGLE_ACTION"
        or authority.verification.signed_payload_sha256
        != authority.record.signed_payload_sha256
    ):
        raise NativeT102ProductionTransportError(
            "admitted external authority verification differs from signed record")
    _verify_machine_authority_at_sink(authority.record, trusted_now)
    if authority.record.review_sha256 != admission.review_sha256:
        raise NativeT102ProductionTransportError(
            "external T102 authority does not bind this reviewed action")
    message = decode_line(frame.wire_bytes)
    if (
        message.get("T") != 102
        or tuple(message) != ("T", *JOINT_FIELDS, "spd", "acc")
        or goal_hash(message) not in admission.ordered_goal_sha256
        or motion_permit.capability is not admission.capability
        or motion_permit.plan_hash != admission.review_sha256
        or motion_permit.snapshot_hash != admission.snapshot_sha256
        or motion_permit.expires_at_monotonic
        != admission.permit_expires_at_monotonic
    ):
        raise NativeT102ProductionTransportError(
            "motion permit or exact T102 goal differs from admission")
    snapshot = handoff.verify_claimed_inputs(
        frame, admission, adapter_candidate_sha256=adapter_candidate_sha256,
        now_monotonic_ns=started_ns,
    )
    assert snapshot.claim_sha256 is not None
    machine_ledger.spend_execution(
        admission.consumption_sha256, admission.review_sha256,
        goal_hash(message),
        authority.record.authority_id, authority.record.issuer_key_id,
        authority.record.signed_payload_sha256, snapshot.claim_sha256,
    )
    journal = DurableNativeT102ProductionAttemptV1.begin(
        receipt_root, claim_sha256=snapshot.claim_sha256,
        prepared_sha256=snapshot.prepared_sha256, frame=frame,
        authority=authority, endpoint=endpoint,
        started_monotonic_ns=started_ns,
    )
    # The durable no-retry marker precedes even process-local authority
    # consumption. A crash in this small interval therefore reconciles as an
    # uncertain attempt rather than allowing the external record to replay.
    authority.consume(
        claim_sha256=snapshot.claim_sha256, frame=frame, endpoint=endpoint,
        now_monotonic_ns=trusted_now,
    )
    if motion_permit.allows(message, now_monotonic=trusted_now / 1_000_000_000) is not True:
        raise NativeT102ProductionTransportError(
            "exact motion permit was not consumable; no transport opened")
    status = "CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED"
    error_code: str | None = None
    confirmed = 0
    acknowledgment_sha256: str | None = None
    feedback_hashes: tuple[str, ...] = ()
    maximum_error: float | None = None
    try:
        transport.bind_execution(_issue_native_t102_execution_grant_v1(endpoint, frame))
        observed = transport.open_once(endpoint)
        if not isinstance(observed, PinnedNativeT102EndpointV1) \
                or observed.endpoint_sha256 != endpoint.endpoint_sha256:
            status = "ENDPOINT_IDENTITY_MISMATCH_NO_WRITE"
            error_code = "ENDPOINT_IDENTITY_MISMATCH"
        else:
            count = transport.write_once(frame.wire_bytes)
            if isinstance(count, bool) or not isinstance(count, int) \
                    or not 0 <= count <= len(frame.wire_bytes):
                status = "WRITE_UNCERTAIN_NO_RETRY"
                error_code = "INVALID_WRITE_COUNT"
            else:
                confirmed = count
                if count != len(frame.wire_bytes):
                    status = "WRITE_UNCERTAIN_NO_RETRY"
                    error_code = "ZERO_WRITE" if count == 0 else "PARTIAL_WRITE"
                else:
                    try:
                        capture = transport.capture_once()
                        if not isinstance(capture, NativeT102ControllerCaptureV1):
                            raise NativeT102ProductionTransportError(
                                "transport returned an invalid capture")
                        acknowledgment_sha256, feedback_hashes, maximum_error = \
                            _validate_capture(
                                frame, capture,
                                dispatch_monotonic_ns=started_ns,
                                assessment_monotonic_ns=assessment_ns,
                                tolerance_rad=float(settlement_tolerance_rad),
                            )
                    except Exception:
                        status = "EVIDENCE_UNCERTAIN_NO_RETRY"
                        error_code = "CAPTURE_OR_EVIDENCE_FAILURE"
    except Exception:
        status = (
            "NOT_OPENED_AUTHORITY_CONSUMED_NO_RETRY"
            if transport.open_attempts <= 1 and transport.write_attempts == 0
            else "WRITE_UNCERTAIN_NO_RETRY"
        )
        error_code = (
            "OPEN_FAILURE" if transport.write_attempts == 0
            else "WRITE_EXCEPTION")
    finally:
        try:
            transport.close_once()
        except Exception:
            status = "CLOSE_UNCERTAIN_NO_RETRY"
            error_code = "CLOSE_FAILURE"
    for name in ("open_attempts", "write_attempts", "capture_attempts",
                 "close_attempts"):
        _bounded_int(getattr(transport, name), name, 0, 1)
    receipt = NativeT102ProductionTransportReceiptV1(
        status=status,
        authority_sha256=authority.record.signed_payload_sha256,
        verification_sha256=authority.verification.verification_sha256,
        approval_record_sha256=authority.record.approval_record_sha256,
        claim_sha256=snapshot.claim_sha256,
        prepared_sha256=snapshot.prepared_sha256,
        frame_sha256=frame.frame_sha256,
        wire_bytes_sha256=frame.wire_bytes_sha256,
        endpoint_sha256=endpoint.endpoint_sha256,
        correlation_id=frame.correlation_id,
        writer_instance_id=frame.writer_instance_id,
        controller_session_id=frame.controller_session_id,
        requested_bytes=len(frame.wire_bytes),
        confirmed_bytes=confirmed,
        open_attempts=transport.open_attempts,
        write_attempts=transport.write_attempts,
        capture_attempts=transport.capture_attempts,
        close_attempts=transport.close_attempts,
        acknowledgment_sha256=acknowledgment_sha256,
        feedback_response_sha256=feedback_hashes,
        maximum_joint_error_rad=maximum_error,
        error_code=error_code,
    )
    terminal = journal.commit_terminal(
        receipt, completed_monotonic_ns=completed_ns)
    return journal, receipt, terminal


__all__ = [
    "AUTHORITY_SCHEMA", "AUTHORITY_SCOPE", "ENDPOINT_SCHEMA",
    "RECEIPT_SCHEMA", "SNAPSHOT_SCHEMA", "STARTED_SCHEMA", "TERMINAL_SCHEMA",
    "AdmittedExternalNativeT102AuthorityV1",
    "DurableNativeT102ProductionAttemptV1",
    "ExternalAuthorityVerificationV1",
    "ExternalNativeT102AuthorityRecordV1",
    "ExternalNativeT102AuthorityVerifierV1",
    "MachinePinnedEd25519AuthorityVerifierV1",
    "NativeT102ControllerCaptureV1", "NativeT102FeedbackSampleV1",
    "NativeT102ProductionTransportError",
    "NativeT102ProductionTransportReceiptV1",
    "NativeT102ProductionTransportV1", "PinnedNativeT102EndpointV1",
    "ProductionAttemptRecovery", "ProductionAttemptSnapshotV1",
    "admit_external_native_t102_authority_v1",
    "execute_native_t102_production_candidate_v1",
]
