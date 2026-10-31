"""Zero-I/O owner-governed intake for the current native T=102 provider.

The record binds the exact owner acceptance, one retained diagnostic checkpoint,
one host, and one pinned endpoint to a closed passive-read proposal.  Retained
identity is historical evidence only: a later, separate authorization must
verify the exact identity both before and after its single open.  This module
cannot enumerate, open, or write hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any

from .native_t102_current_provider_owner_ai_review_acceptance_v1 import (
    GOVERNANCE_CAVEAT,
    NativeT102CurrentProviderOwnerAIReviewAcceptanceV1,
)
from .native_t102_current_provider_review_decision_v1 import (
    CANDIDATE_COMMIT,
    MANIFEST_SHA256,
    PACKET_SHA256,
    PROVIDER_SOURCE_SHA256,
)
from .native_t102_production_transport_v1 import PinnedNativeT102EndpointV1


SCHEMA = "rocell.native_t102_current_provider_owner_read_only_intake.v1"
STATUS = "READY_FOR_SEPARATE_OWNER_GOVERNED_READ_ONLY_AUTHORIZATION"
OPERATIONS = (
    "VERIFY_PINNED_IDENTITY_BEFORE_OPEN",
    "OPEN_EXACT_ENDPOINT_ONCE",
    "VERIFY_PINNED_IDENTITY_AFTER_OPEN",
    "PASSIVE_READ_BOUNDED_LINES",
    "CLOSE_EXACT_ENDPOINT_ONCE",
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class NativeT102CurrentProviderOwnerReadOnlyIntakeError(ValueError):
    """The owner-governed read-only intake is invalid or crossed."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "intake value is not canonical JSON") from exc


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            f"{label} must be a bounded identifier")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            f"{label} must be a SHA-256 digest")
    return value


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            f"{label} must be whole-second UTC")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError as exc:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            f"{label} must be valid UTC") from exc


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "passive_read_timeout_s must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0 < result <= 10:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "passive_read_timeout_s must be finite and in (0, 10]")
    return result


@dataclass(frozen=True, slots=True)
class NativeT102CurrentProviderOwnerReadOnlyIntakeV1:
    intake_id: str
    owner_acceptance_sha256: str
    owner_acceptance_id: str
    host_id: str
    created_utc: str
    endpoint: PinnedNativeT102EndpointV1
    operational_checkpoint_sha256: str
    controller_metadata_session_id: str
    controller_metadata_source_sha256: str
    controller_metadata_log_head_sha256: str
    passive_read_timeout_s: float = 1.0
    maximum_passive_lines: int = 4
    maximum_line_bytes: int = 2048
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
                "unsupported owner-governed read-only intake schema")
        for name in ("intake_id", "owner_acceptance_id", "host_id",
                     "controller_metadata_session_id"):
            _identifier(getattr(self, name), name)
        for name in (
            "owner_acceptance_sha256", "operational_checkpoint_sha256",
            "controller_metadata_source_sha256",
            "controller_metadata_log_head_sha256",
        ):
            _digest(getattr(self, name), name)
        _utc(self.created_utc, "created_utc")
        if not isinstance(self.endpoint, PinnedNativeT102EndpointV1):
            raise TypeError("endpoint must be PinnedNativeT102EndpointV1")
        object.__setattr__(
            self, "passive_read_timeout_s", _timeout(self.passive_read_timeout_s))
        if type(self.maximum_passive_lines) is not int or not (
            1 <= self.maximum_passive_lines <= 16
        ):
            raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
                "maximum_passive_lines must be in 1..16")
        if type(self.maximum_line_bytes) is not int or not (
            64 <= self.maximum_line_bytes <= 4096
        ):
            raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
                "maximum_line_bytes must be in 64..4096")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": STATUS,
            "intake_id": self.intake_id,
            "owner_acceptance_sha256": self.owner_acceptance_sha256,
            "owner_acceptance_id": self.owner_acceptance_id,
            "governance_caveat": GOVERNANCE_CAVEAT,
            "owner_governance_override": True,
            "human_review_claimed": False,
            "external_independence_claimed": False,
            "reviewed_packet_sha256": PACKET_SHA256,
            "reviewed_manifest_sha256": MANIFEST_SHA256,
            "reviewed_candidate_commit": CANDIDATE_COMMIT,
            "reviewed_provider_source_sha256": PROVIDER_SOURCE_SHA256,
            "host_id": self.host_id,
            "created_utc": self.created_utc,
            "endpoint": self.endpoint.to_dict(),
            "endpoint_sha256": self.endpoint.endpoint_sha256,
            "retained_identity_is_live_verification": False,
            "operational_checkpoint_sha256": self.operational_checkpoint_sha256,
            "controller_metadata_session_id": self.controller_metadata_session_id,
            "controller_metadata_source_sha256": (
                self.controller_metadata_source_sha256),
            "controller_metadata_log_head_sha256": (
                self.controller_metadata_log_head_sha256),
            "operations": list(OPERATIONS),
            "passive_read_timeout_s": self.passive_read_timeout_s,
            "maximum_passive_lines": self.maximum_passive_lines,
            "maximum_line_bytes": self.maximum_line_bytes,
            "open_count_limit": 1,
            "close_count_limit": 1,
            "transport_write_count_limit": 0,
            "active_request_count_limit": 0,
            "movement_command_count_limit": 0,
            "torque_command_count_limit": 0,
            "buffer_purge_allowed": False,
            "fallback_endpoint_allowed": False,
            "automatic_retry_allowed": False,
            "dtr_assertion_allowed": False,
            "rts_assertion_allowed": False,
            "ready_for_separate_read_only_authorization": True,
            "read_only_endpoint_authorized": False,
            "endpoint_open_authorized": False,
            "controller_start_authorized": False,
            "transport_write_authorized": False,
            "execution_authorized": False,
            "hardware_access": False,
            "physical_authority": False,
        }

    @property
    def intake_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "intake_sha256": self.intake_sha256}


def build_native_t102_current_provider_owner_read_only_intake_v1(
    owner_acceptance: NativeT102CurrentProviderOwnerAIReviewAcceptanceV1,
    endpoint: PinnedNativeT102EndpointV1,
    *, intake_id: str, host_id: str, created_utc: str,
    operational_checkpoint_sha256: str,
    controller_metadata_session_id: str,
    controller_metadata_source_sha256: str,
    controller_metadata_log_head_sha256: str,
    passive_read_timeout_s: float = 1.0,
    maximum_passive_lines: int = 4,
    maximum_line_bytes: int = 2048,
) -> NativeT102CurrentProviderOwnerReadOnlyIntakeV1:
    """Build one offline proposal from a valid owner acceptance."""

    if not isinstance(
        owner_acceptance, NativeT102CurrentProviderOwnerAIReviewAcceptanceV1
    ):
        raise TypeError("owner_acceptance must be the current-provider acceptance")
    if _utc(created_utc, "created_utc") < _utc(
        owner_acceptance.accepted_utc, "owner accepted_utc"
    ):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "created_utc cannot predate owner acceptance")
    if _utc(created_utc, "created_utc") < _utc(
        owner_acceptance.accepted_utc, "accepted_utc"
    ):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "read-only intake cannot predate owner acceptance")
    return NativeT102CurrentProviderOwnerReadOnlyIntakeV1(
        intake_id=intake_id,
        owner_acceptance_sha256=owner_acceptance.acceptance_sha256,
        owner_acceptance_id=owner_acceptance.acceptance_id,
        host_id=host_id,
        created_utc=created_utc,
        endpoint=endpoint,
        operational_checkpoint_sha256=operational_checkpoint_sha256,
        controller_metadata_session_id=controller_metadata_session_id,
        controller_metadata_source_sha256=controller_metadata_source_sha256,
        controller_metadata_log_head_sha256=controller_metadata_log_head_sha256,
        passive_read_timeout_s=passive_read_timeout_s,
        maximum_passive_lines=maximum_passive_lines,
        maximum_line_bytes=maximum_line_bytes,
    )


def parse_native_t102_current_provider_owner_read_only_intake_v1(
    document: dict[str, Any],
) -> NativeT102CurrentProviderOwnerReadOnlyIntakeV1:
    """Strictly parse an intake without enumerating or opening hardware."""

    template = NativeT102CurrentProviderOwnerReadOnlyIntakeV1(
        intake_id="field-template", owner_acceptance_sha256="0" * 64,
        owner_acceptance_id="field-template", host_id="field-template",
        created_utc="2000-01-01T00:00:00Z",
        endpoint=PinnedNativeT102EndpointV1(
            port_name="COM1", usb_vid="0000", usb_pid="0000",
            usb_serial_number="field-template"),
        operational_checkpoint_sha256="0" * 64,
        controller_metadata_session_id="field-template",
        controller_metadata_source_sha256="0" * 64,
        controller_metadata_log_head_sha256="0" * 64,
    ).to_dict()
    if type(document) is not dict or set(document) != set(template):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "owner-governed intake must contain exactly the closed fields")
    variable = {
        "intake_id", "owner_acceptance_sha256", "owner_acceptance_id",
        "host_id", "created_utc", "endpoint", "endpoint_sha256",
        "operational_checkpoint_sha256", "controller_metadata_session_id",
        "controller_metadata_source_sha256",
        "controller_metadata_log_head_sha256", "passive_read_timeout_s",
        "maximum_passive_lines", "maximum_line_bytes", "intake_sha256",
    }
    if any(document.get(key) != value for key, value in template.items()
           if key not in variable):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "owner-governed policy, subject, provenance, or authority differs")
    raw_endpoint = document["endpoint"]
    if type(raw_endpoint) is not dict:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "endpoint must be a closed object")
    try:
        endpoint = PinnedNativeT102EndpointV1(
            port_name=raw_endpoint["port_name"], usb_vid=raw_endpoint["usb_vid"],
            usb_pid=raw_endpoint["usb_pid"],
            usb_serial_number=raw_endpoint["usb_serial_number"],
            baud_rate=raw_endpoint["baud_rate"], data_bits=raw_endpoint["data_bits"],
            parity=raw_endpoint["parity"], stop_bits=raw_endpoint["stop_bits"],
            flow_control=raw_endpoint["flow_control"],
        )
        parsed = NativeT102CurrentProviderOwnerReadOnlyIntakeV1(
            intake_id=document["intake_id"],
            owner_acceptance_sha256=document["owner_acceptance_sha256"],
            owner_acceptance_id=document["owner_acceptance_id"],
            host_id=document["host_id"], created_utc=document["created_utc"],
            endpoint=endpoint,
            operational_checkpoint_sha256=document["operational_checkpoint_sha256"],
            controller_metadata_session_id=document["controller_metadata_session_id"],
            controller_metadata_source_sha256=document[
                "controller_metadata_source_sha256"],
            controller_metadata_log_head_sha256=document[
                "controller_metadata_log_head_sha256"],
            passive_read_timeout_s=document["passive_read_timeout_s"],
            maximum_passive_lines=document["maximum_passive_lines"],
            maximum_line_bytes=document["maximum_line_bytes"],
            schema=document["schema"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "owner-governed intake contains invalid typed values") from exc
    if raw_endpoint != endpoint.to_dict() or document["endpoint_sha256"] != (
        endpoint.endpoint_sha256
    ):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "embedded endpoint identity differs")
    _digest(document["intake_sha256"], "intake_sha256")
    if document["intake_sha256"] != parsed.intake_sha256:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "owner-governed intake content hash differs")
    return parsed


__all__ = [
    "OPERATIONS", "SCHEMA", "STATUS",
    "NativeT102CurrentProviderOwnerReadOnlyIntakeError",
    "NativeT102CurrentProviderOwnerReadOnlyIntakeV1",
    "build_native_t102_current_provider_owner_read_only_intake_v1",
    "parse_native_t102_current_provider_owner_read_only_intake_v1",
]
