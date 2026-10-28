"""Durable, hardware-incapable handoff for one reviewed T=102 command.

The journal publishes an immutable prepared record and then an exclusive writer
claim.  The claim is committed before any future native transport may open.  A
restart that observes a claim can therefore never infer that resending is safe.

This module intentionally owns no serial factory, port, socket, device handle,
controller process, callback, firmware operation, or transport-open function.
Its claim is a durable ambiguity boundary, not physical execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
from typing import Any, Mapping

from rocell.arm.all_joint_command import JOINT_FIELDS
from rocell.arm.protocol import decode_line
from rocell.safety.permit import goal_hash

from .production_controller_runtime_contract_v1 import RuntimeCommandFrameV1
from .reviewed_motion_permit_bridge_v1 import ReviewedMotionPermitAdmissionV1


PREPARED_SCHEMA = "rocell.native_t102_handoff_prepared.v1"
CLAIM_SCHEMA = "rocell.native_t102_writer_claim.v1"
SNAPSHOT_SCHEMA = "rocell.native_t102_handoff_snapshot.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EXPECTED_T102_FIELDS = ("T", *JOINT_FIELDS, "spd", "acc")
_ZERO = "0" * 64


class NativeT102HandoffJournalError(ValueError):
    """The durable handoff is malformed, crossed, stale, or already claimed."""


class NativeT102HandoffPhase(str, Enum):
    PREPARED = "PREPARED"
    WRITER_CLAIMED = "WRITER_CLAIMED"


class NativeT102RecoveryDisposition(str, Enum):
    CANCEL_AND_REPLAN_WITH_FRESH_AUTHORITY = (
        "CANCEL_AND_REPLAN_WITH_FRESH_AUTHORITY")
    RETRY_FORBIDDEN_DISPATCH_UNCERTAIN = (
        "RETRY_FORBIDDEN_DISPATCH_UNCERTAIN")


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value, indent=2, sort_keys=True, ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeT102HandoffJournalError(
            "handoff value is not canonical JSON") from exc


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise NativeT102HandoffJournalError(
            f"{label} must be a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise NativeT102HandoffJournalError(
            f"{label} must be a bounded identifier")
    return value


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise NativeT102HandoffJournalError(
            f"{label} must be positive nanoseconds")
    return value


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical(value)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise NativeT102HandoffJournalError(
            f"immutable handoff file already exists: {path.name}") from exc


def _fsync_directory(path: Path) -> None:
    """Flush a published directory entry where the host exposes that primitive."""

    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise NativeT102HandoffJournalError(
            f"handoff file is unavailable: {path.name}")
    payload = path.read_bytes()
    if not payload or len(payload) > 64 * 1024:
        raise NativeT102HandoffJournalError(
            f"handoff file size is invalid: {path.name}")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeT102HandoffJournalError(
            f"invalid JSON in {path.name}") from exc
    if not isinstance(value, dict) or _canonical(value) != payload:
        raise NativeT102HandoffJournalError(
            f"noncanonical handoff file: {path.name}")
    return value


def _prepared_core(
    frame: RuntimeCommandFrameV1,
    admission: ReviewedMotionPermitAdmissionV1,
    adapter_candidate_sha256: str,
    created_monotonic_ns: int,
) -> dict[str, Any]:
    if not isinstance(frame, RuntimeCommandFrameV1):
        raise TypeError("frame must be RuntimeCommandFrameV1")
    if not isinstance(admission, ReviewedMotionPermitAdmissionV1):
        raise TypeError("admission must be ReviewedMotionPermitAdmissionV1")
    adapter = _digest(adapter_candidate_sha256, "adapter_candidate_sha256")
    created = _positive_ns(created_monotonic_ns, "created_monotonic_ns")
    message = decode_line(frame.wire_bytes)
    goal_sha256 = goal_hash(message)
    if (
        tuple(message) != _EXPECTED_T102_FIELDS
        or message.get("T") != 102
        or goal_sha256 not in admission.ordered_goal_sha256
        or not frame.issued_monotonic_ns <= created < frame.expires_monotonic_ns
    ):
        raise NativeT102HandoffJournalError(
            "frame, reviewed goal, or preparation time differs")
    core = {
        "schema": PREPARED_SCHEMA,
        "status": "PREPARED_BEFORE_NATIVE_OPEN",
        "review_sha256": admission.review_sha256,
        "permit_binding_sha256": admission.permit_binding_sha256,
        "goal_sha256": goal_sha256,
        "frame_sha256": frame.frame_sha256,
        "wire_bytes_sha256": frame.wire_bytes_sha256,
        "sequence": frame.sequence,
        "correlation_id": frame.correlation_id,
        "writer_instance_id": frame.writer_instance_id,
        "controller_session_id": frame.controller_session_id,
        "configuration_epoch_sha256": frame.configuration_epoch_sha256,
        "encoding_profile_sha256": frame.encoding_profile_sha256,
        "adapter_candidate_sha256": adapter,
        "created_monotonic_ns": created,
        "frame_issued_monotonic_ns": frame.issued_monotonic_ns,
        "frame_expires_monotonic_ns": frame.expires_monotonic_ns,
        "transport_open_authorized": False,
        "physical_authority": False,
        "automatic_retry_allowed": False,
        "transport_open_count": 0,
        "physical_command_writes": 0,
    }
    if admission.fused_camera_state_action_review_admission_sha256 is not None:
        core["fused_camera_state_action_review_admission_sha256"] = (
            admission.fused_camera_state_action_review_admission_sha256
        )
        core["review_consumption_sha256"] = admission.consumption_sha256
    return core


def _validate_prepared(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema", "status", "review_sha256", "permit_binding_sha256",
        "goal_sha256", "frame_sha256", "wire_bytes_sha256", "sequence",
        "correlation_id", "writer_instance_id", "controller_session_id",
        "configuration_epoch_sha256", "encoding_profile_sha256",
        "adapter_candidate_sha256", "created_monotonic_ns",
        "frame_issued_monotonic_ns", "frame_expires_monotonic_ns",
        "transport_open_authorized", "physical_authority",
        "automatic_retry_allowed", "transport_open_count",
        "physical_command_writes", "prepared_sha256",
    }
    copy = dict(value)
    optional = {
        "fused_camera_state_action_review_admission_sha256",
        "review_consumption_sha256",
    }
    present_optional = set(copy) & optional
    if set(copy) - optional != required or present_optional not in (set(), optional):
        raise NativeT102HandoffJournalError("prepared fields are not exact")
    for field in (
        "review_sha256", "permit_binding_sha256", "goal_sha256",
        "frame_sha256", "wire_bytes_sha256", "configuration_epoch_sha256",
        "encoding_profile_sha256", "adapter_candidate_sha256",
        "prepared_sha256",
    ):
        _digest(copy.get(field), field)
    for field in present_optional:
        _digest(copy.get(field), field)
    for field in (
        "correlation_id", "writer_instance_id", "controller_session_id",
    ):
        _identifier(copy.get(field), field)
    for field in (
        "sequence", "created_monotonic_ns", "frame_issued_monotonic_ns",
        "frame_expires_monotonic_ns",
    ):
        _positive_ns(copy.get(field), field)
    if (
        copy["schema"] != PREPARED_SCHEMA
        or copy["status"] != "PREPARED_BEFORE_NATIVE_OPEN"
        or not copy["frame_issued_monotonic_ns"]
        <= copy["created_monotonic_ns"]
        < copy["frame_expires_monotonic_ns"]
        or copy["transport_open_authorized"] is not False
        or copy["physical_authority"] is not False
        or copy["automatic_retry_allowed"] is not False
        or copy["transport_open_count"] != 0
        or copy["physical_command_writes"] != 0
        or copy["prepared_sha256"]
        != _hash({key: item for key, item in copy.items()
                  if key != "prepared_sha256"})
    ):
        raise NativeT102HandoffJournalError(
            "prepared content or authority is invalid")
    return copy


def _validate_claim(
    value: Mapping[str, Any], prepared: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "schema", "status", "prepared_sha256", "frame_sha256",
        "writer_instance_id", "controller_session_id", "claimed_monotonic_ns",
        "previous_claim_sha256", "transport_open_authorized",
        "physical_authority", "automatic_retry_allowed",
        "transport_open_count", "physical_command_writes", "claim_sha256",
    }
    copy = dict(value)
    if set(copy) != required:
        raise NativeT102HandoffJournalError("claim fields are not exact")
    for field in (
        "prepared_sha256", "frame_sha256", "previous_claim_sha256",
        "claim_sha256",
    ):
        _digest(copy.get(field), field)
    for field in ("writer_instance_id", "controller_session_id"):
        _identifier(copy.get(field), field)
    claimed = _positive_ns(copy.get("claimed_monotonic_ns"),
                           "claimed_monotonic_ns")
    if (
        copy["schema"] != CLAIM_SCHEMA
        or copy["status"] != "WRITER_CLAIM_COMMITTED_BEFORE_NATIVE_OPEN"
        or copy["prepared_sha256"] != prepared["prepared_sha256"]
        or copy["frame_sha256"] != prepared["frame_sha256"]
        or copy["writer_instance_id"] != prepared["writer_instance_id"]
        or copy["controller_session_id"] != prepared["controller_session_id"]
        or copy["previous_claim_sha256"] != _ZERO
        or not prepared["created_monotonic_ns"] <= claimed
        < prepared["frame_expires_monotonic_ns"]
        or copy["transport_open_authorized"] is not False
        or copy["physical_authority"] is not False
        or copy["automatic_retry_allowed"] is not False
        or copy["transport_open_count"] != 0
        or copy["physical_command_writes"] != 0
        or copy["claim_sha256"]
        != _hash({key: item for key, item in copy.items()
                  if key != "claim_sha256"})
    ):
        raise NativeT102HandoffJournalError(
            "claim binding, timing, or authority is invalid")
    return copy


@dataclass(frozen=True, slots=True)
class NativeT102HandoffSnapshotV1:
    phase: NativeT102HandoffPhase
    prepared_sha256: str
    frame_sha256: str
    permit_binding_sha256: str
    claim_sha256: str | None
    fused_camera_state_action_review_admission_sha256: str | None = None
    review_consumption_sha256: str | None = None

    def __post_init__(self) -> None:
        fused = self.fused_camera_state_action_review_admission_sha256
        consumption = self.review_consumption_sha256
        if (fused is None) != (consumption is None):
            raise NativeT102HandoffJournalError(
                "fused handoff lineage must be present together"
            )
        if fused is not None:
            _digest(fused, "fused_camera_state_action_review_admission_sha256")
            _digest(consumption, "review_consumption_sha256")

    @property
    def recovery_disposition(self) -> NativeT102RecoveryDisposition:
        if self.phase is NativeT102HandoffPhase.WRITER_CLAIMED:
            return NativeT102RecoveryDisposition.RETRY_FORBIDDEN_DISPATCH_UNCERTAIN
        return NativeT102RecoveryDisposition.CANCEL_AND_REPLAN_WITH_FRESH_AUTHORITY

    def to_dict(self) -> dict[str, Any]:
        core = {
            "schema": SNAPSHOT_SCHEMA,
            "phase": self.phase.value,
            "prepared_sha256": self.prepared_sha256,
            "frame_sha256": self.frame_sha256,
            "permit_binding_sha256": self.permit_binding_sha256,
            "claim_sha256": self.claim_sha256,
            "recovery_disposition": self.recovery_disposition.value,
            "transport_open_authorized": False,
            "physical_authority": False,
            "automatic_retry_allowed": False,
            "transport_open_count": 0,
            "physical_command_writes": 0,
        }
        if self.fused_camera_state_action_review_admission_sha256 is not None:
            core["fused_camera_state_action_review_admission_sha256"] = (
                self.fused_camera_state_action_review_admission_sha256
            )
            core["review_consumption_sha256"] = self.review_consumption_sha256
        return {**core, "snapshot_sha256": _hash(core)}


def load_native_t102_handoff_v1(
    directory: Path,
) -> NativeT102HandoffSnapshotV1:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise NativeT102HandoffJournalError("handoff directory is unavailable")
    root = root.resolve()
    entries = {path.name for path in root.iterdir()}
    if entries not in ({"prepared.json"}, {"prepared.json", "claim.json"}):
        raise NativeT102HandoffJournalError(
            "handoff directory entries are not exact")
    prepared = _validate_prepared(_read(root / "prepared.json"))
    claim = None
    if "claim.json" in entries:
        claim = _validate_claim(_read(root / "claim.json"), prepared)
    return NativeT102HandoffSnapshotV1(
        phase=(NativeT102HandoffPhase.WRITER_CLAIMED
               if claim else NativeT102HandoffPhase.PREPARED),
        prepared_sha256=prepared["prepared_sha256"],
        frame_sha256=prepared["frame_sha256"],
        permit_binding_sha256=prepared["permit_binding_sha256"],
        claim_sha256=claim["claim_sha256"] if claim else None,
        fused_camera_state_action_review_admission_sha256=prepared.get(
            "fused_camera_state_action_review_admission_sha256"
        ),
        review_consumption_sha256=prepared.get("review_consumption_sha256"),
    )


@dataclass(frozen=True, slots=True)
class DurableNativeT102HandoffV1:
    directory: Path

    @classmethod
    def prepare(
        cls, root: Path, frame: RuntimeCommandFrameV1,
        admission: ReviewedMotionPermitAdmissionV1, *,
        adapter_candidate_sha256: str, created_monotonic_ns: int,
    ) -> "DurableNativeT102HandoffV1":
        base = Path(root)
        if base.is_symlink() or not base.is_dir():
            raise NativeT102HandoffJournalError("handoff root is unavailable")
        base = base.resolve()
        core = _prepared_core(
            frame, admission, adapter_candidate_sha256, created_monotonic_ns)
        prepared = {**core, "prepared_sha256": _hash(core)}
        destination = base / f"native-t102-{prepared['prepared_sha256'][:24]}"
        if os.path.lexists(destination):
            raise NativeT102HandoffJournalError(
                "immutable native handoff already exists")
        temporary = base / f".partial-{destination.name}-{secrets.token_hex(8)}"
        try:
            temporary.mkdir()
            _write_new(temporary / "prepared.json", prepared)
            os.replace(temporary, destination)
            _fsync_directory(base)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        journal = cls(destination)
        load_native_t102_handoff_v1(journal.directory)
        return journal

    def snapshot(self) -> NativeT102HandoffSnapshotV1:
        return load_native_t102_handoff_v1(self.directory)

    def verify_claimed_inputs(
        self, frame: RuntimeCommandFrameV1,
        admission: ReviewedMotionPermitAdmissionV1, *,
        adapter_candidate_sha256: str, now_monotonic_ns: int,
    ) -> NativeT102HandoffSnapshotV1:
        """Revalidate the exact claimed handoff without creating authority."""

        snapshot = self.snapshot()
        if snapshot.phase is not NativeT102HandoffPhase.WRITER_CLAIMED:
            raise NativeT102HandoffJournalError(
                "native handoff does not have a committed writer claim")
        prepared = _validate_prepared(_read(self.directory / "prepared.json"))
        expected = _prepared_core(
            frame, admission, adapter_candidate_sha256,
            prepared["created_monotonic_ns"],
        )
        if prepared != {**expected, "prepared_sha256": _hash(expected)}:
            raise NativeT102HandoffJournalError(
                "executor inputs differ from the claimed native handoff")
        _validate_claim(_read(self.directory / "claim.json"), prepared)
        now = _positive_ns(now_monotonic_ns, "now_monotonic_ns")
        if not prepared["created_monotonic_ns"] <= now \
                < prepared["frame_expires_monotonic_ns"]:
            raise NativeT102HandoffJournalError(
                "claimed native handoff is stale")
        return snapshot

    def claim_writer(
        self, frame: RuntimeCommandFrameV1,
        admission: ReviewedMotionPermitAdmissionV1, *,
        adapter_candidate_sha256: str, claimed_monotonic_ns: int,
    ) -> NativeT102HandoffSnapshotV1:
        before = self.snapshot()
        if before.phase is not NativeT102HandoffPhase.PREPARED:
            raise NativeT102HandoffJournalError(
                "native handoff already has a writer claim")
        prepared = _validate_prepared(_read(self.directory / "prepared.json"))
        expected = _prepared_core(
            frame, admission, adapter_candidate_sha256,
            prepared["created_monotonic_ns"],
        )
        if prepared != {**expected, "prepared_sha256": _hash(expected)}:
            raise NativeT102HandoffJournalError(
                "claim inputs differ from the prepared native handoff")
        claimed = _positive_ns(claimed_monotonic_ns, "claimed_monotonic_ns")
        claim_core = {
            "schema": CLAIM_SCHEMA,
            "status": "WRITER_CLAIM_COMMITTED_BEFORE_NATIVE_OPEN",
            "prepared_sha256": prepared["prepared_sha256"],
            "frame_sha256": prepared["frame_sha256"],
            "writer_instance_id": prepared["writer_instance_id"],
            "controller_session_id": prepared["controller_session_id"],
            "claimed_monotonic_ns": claimed,
            "previous_claim_sha256": _ZERO,
            "transport_open_authorized": False,
            "physical_authority": False,
            "automatic_retry_allowed": False,
            "transport_open_count": 0,
            "physical_command_writes": 0,
        }
        claim = {**claim_core, "claim_sha256": _hash(claim_core)}
        _validate_claim(claim, prepared)
        _write_new(self.directory / "claim.json", claim)
        _fsync_directory(self.directory)
        return self.snapshot()


__all__ = [
    "CLAIM_SCHEMA", "PREPARED_SCHEMA", "SNAPSHOT_SCHEMA",
    "DurableNativeT102HandoffV1", "NativeT102HandoffJournalError",
    "NativeT102HandoffPhase", "NativeT102HandoffSnapshotV1",
    "NativeT102RecoveryDisposition", "load_native_t102_handoff_v1",
]
