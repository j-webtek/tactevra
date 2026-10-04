"""Deterministic review-only packet for the ARM-054 Windows adapter.

The packet carries exact source, test, documentation, and offline verification
evidence to an external reviewer.  Building or inspecting it performs no
hardware access and cannot issue an approval or physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import PurePosixPath
from typing import Any, Mapping
import zipfile


SCHEMA = "rocell.native_t102_adapter_review_packet.v1"
STATUS = "AWAITING_EXTERNAL_INDEPENDENT_REVIEW"
MAX_PACKET_BYTES = 512 * 1024
_CANDIDATE_NAMES = (
    "source/native_t102_serial_transport_v1.py",
    "tests/test_windows_native_t102_serial_transport_v1.py",
    "docs/WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md",
)
_FIXED_NAMES = (
    *_CANDIDATE_NAMES,
    "evidence/offline-verification.json",
    "REVIEW_INSTRUCTIONS.md",
)
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class NativeT102AdapterReviewPacketError(ValueError):
    """Review evidence is incomplete, ambiguous, or internally inconsistent."""


def _canonical(value: object) -> bytes:
    try:
        return (json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeT102AdapterReviewPacketError(
            "review value is not canonical JSON") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json(payload: bytes) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise NativeT102AdapterReviewPacketError(
                    f"verification contains duplicate field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                NativeT102AdapterReviewPacketError(
                    f"verification contains {item}")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NativeT102AdapterReviewPacketError(
            "verification is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise NativeT102AdapterReviewPacketError(
            "verification must be an object")
    return value


def _member_info(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "bytes": len(data), "sha256": _sha(data)}


def _instructions(candidate_commit: str) -> bytes:
    return f"""# ARM-054 adapter independent-review handoff

Candidate commit: `{candidate_commit}`

This archive is a review input, not an approval, executable bundle, or physical
authorization. The independent reviewer must:

1. verify every member against `manifest.json`;
2. inspect endpoint identity before and after open;
3. verify exact 115200 8N1/no-flow setup and finite read/write timeouts;
4. verify the only movement write accepts canonical T=102 and occurs once;
5. verify capture permits one T=1021 and exactly two T=105/T=1051 exchanges;
6. verify no fallback, reopen, resend, recapture, purge, reset, torque, homing,
   startup movement, or automatic retry path exists;
7. verify ARM-053 consumes external authority after durable start and before
   transport open, then seals terminal no-replay evidence; and
8. record findings in a separately authenticated decision without changing
   this archive.

Even a passing review does not authorize endpoint opening or movement.
""".encode("utf-8")


def _validate_verification(
    value: Mapping[str, Any], members: Mapping[str, bytes],
) -> str:
    fields = {
        "schema", "status", "candidate_commit", "candidate_files",
        "focused_tests_passed", "shared_tests_passed",
        "documentation_tests_passed", "github_checks_passed",
        "real_endpoint_opened", "hardware_writes", "physical_movements",
        "independent_review_complete", "physical_authority",
    }
    if set(value) != fields:
        raise NativeT102AdapterReviewPacketError(
            "verification fields differ")
    commit = value["candidate_commit"]
    if not isinstance(commit, str) or len(commit) != 40 \
            or any(ch not in "0123456789abcdef" for ch in commit):
        raise NativeT102AdapterReviewPacketError(
            "candidate commit must be a full lowercase git object ID")
    if (
        value["schema"] != "rocell.native_t102_adapter_offline_verification.v1"
        or value["status"] != "PASS_OFFLINE_NO_HARDWARE"
        or value["focused_tests_passed"] != 33
        or value["shared_tests_passed"] != 305
        or value["documentation_tests_passed"] != 43
        or value["github_checks_passed"] != 8
        or value["real_endpoint_opened"] is not False
        or value["hardware_writes"] != 0
        or value["physical_movements"] != 0
        or value["independent_review_complete"] is not False
        or value["physical_authority"] is not False
    ):
        raise NativeT102AdapterReviewPacketError(
            "verification exceeds or differs from offline evidence")
    described = value["candidate_files"]
    if not isinstance(described, list) or len(described) != len(_CANDIDATE_NAMES):
        raise NativeT102AdapterReviewPacketError(
            "verification candidate file list differs")
    expected = [_member_info(name, members[name])
                for name in sorted(_CANDIDATE_NAMES)]
    if described != expected:
        raise NativeT102AdapterReviewPacketError(
            "verification does not bind exact candidate files")
    return commit


@dataclass(frozen=True, slots=True)
class NativeT102AdapterReviewPacketResultV1:
    packet_bytes: bytes
    packet_sha256: str
    manifest_sha256: str
    candidate_commit: str
    member_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rocell.native_t102_adapter_review_packet_result.v1",
            "status": STATUS,
            "packet_sha256": self.packet_sha256,
            "manifest_sha256": self.manifest_sha256,
            "candidate_commit": self.candidate_commit,
            "member_count": self.member_count,
            "independent_review_complete": False,
            "endpoint_open_authorized": False,
            "execution_authorized": False,
            "hardware_access": False,
            "physical_authority": False,
        }


def build_native_t102_adapter_review_packet_v1(
    *, candidate_members: Mapping[str, bytes], verification_record: bytes,
) -> NativeT102AdapterReviewPacketResultV1:
    if set(candidate_members) != set(_CANDIDATE_NAMES) \
            or any(not isinstance(data, bytes) or not data
                   for data in candidate_members.values()):
        raise NativeT102AdapterReviewPacketError(
            "candidate member set differs or contains empty data")
    verification = _strict_json(verification_record)
    candidate_commit = _validate_verification(
        verification, candidate_members)
    members = {
        **candidate_members,
        "evidence/offline-verification.json": verification_record,
        "REVIEW_INSTRUCTIONS.md": _instructions(candidate_commit),
    }
    manifest = {
        "schema": SCHEMA,
        "candidate": "ARM-054_WINDOWS_NATIVE_T102_SERIAL_ADAPTER",
        "candidate_commit": candidate_commit,
        "status": STATUS,
        "members": [_member_info(name, members[name]) for name in sorted(members)],
        "independent_review_complete": False,
        "endpoint_open_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    manifest_bytes = _canonical(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED,
                         strict_timestamps=True) as archive:
        for name, data in (("manifest.json", manifest_bytes),
                           *sorted(members.items())):
            info = zipfile.ZipInfo(name, _ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, data)
    packet = output.getvalue()
    if len(packet) > MAX_PACKET_BYTES:
        raise NativeT102AdapterReviewPacketError(
            "review packet exceeds size bound")
    inspected = inspect_native_t102_adapter_review_packet_v1(packet)
    return NativeT102AdapterReviewPacketResultV1(
        packet_bytes=packet,
        packet_sha256=_sha(packet),
        manifest_sha256=_sha(manifest_bytes),
        candidate_commit=candidate_commit,
        member_count=inspected.member_count,
    )


def inspect_native_t102_adapter_review_packet_v1(
    packet: bytes,
) -> NativeT102AdapterReviewPacketResultV1:
    if not isinstance(packet, bytes) or not packet \
            or len(packet) > MAX_PACKET_BYTES:
        raise NativeT102AdapterReviewPacketError(
            "review packet size is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(packet), "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise NativeT102AdapterReviewPacketError(
                    "review packet contains duplicate members")
            if set(names) != {"manifest.json", *_FIXED_NAMES}:
                raise NativeT102AdapterReviewPacketError(
                    "review packet membership differs")
            for name in names:
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise NativeT102AdapterReviewPacketError(
                        "review packet contains an unsafe member path")
            if any(
                item.compress_type != zipfile.ZIP_STORED
                or item.flag_bits & 1
                or item.file_size > MAX_PACKET_BYTES
                for item in infos
            ) or sum(item.file_size for item in infos) > MAX_PACKET_BYTES:
                raise NativeT102AdapterReviewPacketError(
                    "review packet member exceeds size or format bound")
            payloads = {}
            remaining = MAX_PACKET_BYTES
            for item in infos:
                with archive.open(item) as member:
                    data = member.read(min(item.file_size, remaining) + 1)
                if len(data) != item.file_size or len(data) > remaining:
                    raise NativeT102AdapterReviewPacketError(
                        "review packet member exceeds size bound")
                payloads[item.filename] = data
                remaining -= len(data)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise NativeT102AdapterReviewPacketError(
            "review packet is not a valid archive") from exc
    manifest = _strict_json(payloads["manifest.json"])
    fields = {
        "schema", "candidate", "candidate_commit", "status", "members",
        "independent_review_complete", "endpoint_open_authorized",
        "execution_authorized", "hardware_access", "physical_authority",
    }
    if set(manifest) != fields or (
        manifest["schema"] != SCHEMA
        or manifest["candidate"] != "ARM-054_WINDOWS_NATIVE_T102_SERIAL_ADAPTER"
        or manifest["status"] != STATUS
        or any(manifest[name] is not False for name in (
            "independent_review_complete", "endpoint_open_authorized",
            "execution_authorized", "hardware_access", "physical_authority"))
    ):
        raise NativeT102AdapterReviewPacketError(
            "manifest differs or exceeds review-only authority")
    raw_members = manifest["members"]
    if not isinstance(raw_members, list) or len(raw_members) != len(_FIXED_NAMES):
        raise NativeT102AdapterReviewPacketError(
            "manifest member list differs")
    expected = [_member_info(name, payloads[name]) for name in sorted(_FIXED_NAMES)]
    if raw_members != expected:
        raise NativeT102AdapterReviewPacketError(
            "manifest member identity or digest differs")
    verification = _strict_json(payloads["evidence/offline-verification.json"])
    candidate_members = {name: payloads[name] for name in _CANDIDATE_NAMES}
    commit = _validate_verification(verification, candidate_members)
    if manifest["candidate_commit"] != commit:
        raise NativeT102AdapterReviewPacketError(
            "manifest candidate commit differs")
    return NativeT102AdapterReviewPacketResultV1(
        packet_bytes=packet,
        packet_sha256=_sha(packet),
        manifest_sha256=_sha(payloads["manifest.json"]),
        candidate_commit=commit,
        member_count=len(_FIXED_NAMES),
    )


__all__ = [
    "MAX_PACKET_BYTES", "SCHEMA", "STATUS",
    "NativeT102AdapterReviewPacketError",
    "NativeT102AdapterReviewPacketResultV1",
    "build_native_t102_adapter_review_packet_v1",
    "inspect_native_t102_adapter_review_packet_v1",
]
