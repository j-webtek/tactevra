"""Closed review packet for the current Windows native T=102 provider.

The historical ARM-054 packet predates the execution-grant gate.  This packet
pins the current provider plus its direct and composed tests and supplies a
closed checklist so an independent reviewer can assess the exact implementation
now reachable from the fused production candidate.  Building or inspecting the
packet performs no hardware access and grants no endpoint or execution
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import PurePosixPath
from typing import Any, Mapping
import zipfile


SCHEMA = "rocell.native_t102_current_provider_review_packet.v1"
VERIFICATION_SCHEMA = (
    "rocell.native_t102_current_provider_offline_verification.v1"
)
STATUS = "AWAITING_EXTERNAL_INDEPENDENT_REVIEW"
CANDIDATE_COMMIT = "9f64afd2e6976624ff380c3770413a44c64a41c0"
MAX_PACKET_BYTES = 1024 * 1024
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

# These are exact bytes at CANDIDATE_COMMIT.  Any later implementation or
# review-surface change requires an explicit packet refresh.
CANDIDATE_FILES = {
    "software/src/rocell/providers/windows/native_t102_serial_transport_v1.py": (
        15687, "ed8c27743e20c66dfaafbcd50f028e55127ba906a39076898f526f96144049b3"
    ),
    "software/tests/unit/test_windows_native_t102_serial_transport_v1.py": (
        8283, "e967215b56a7f1ccf5be60a30237b87838ebdc188e24a6fa27f43c86b50a231f"
    ),
    "software/tests/integration/test_native_t102_windows_composition_v1.py": (
        9181, "649bf9886fd0c1da3fc5a76c9ed8ad9160096541e726502b8d29cd3d27207e63"
    ),
    "software/tests/unit/test_fused_camera_state_reviewed_motion_permit_v1.py": (
        35737, "08226a09d619f5ac0cd59b20f4544425c947f4ef42c284579f26d509eae9ac36"
    ),
}
_FIXED_MEMBERS = (
    *CANDIDATE_FILES,
    "evidence/offline-verification.json",
    "REVIEW_INSTRUCTIONS.md",
)


class NativeT102CurrentProviderReviewPacketError(ValueError):
    """Current-provider review material is incomplete or inconsistent."""


def _canonical(value: object) -> bytes:
    try:
        return (json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeT102CurrentProviderReviewPacketError(
            "review value is not canonical JSON") from exc


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_json(payload: bytes) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise NativeT102CurrentProviderReviewPacketError(
                    f"review JSON repeats {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                NativeT102CurrentProviderReviewPacketError(
                    f"review JSON contains {item}")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NativeT102CurrentProviderReviewPacketError(
            "review JSON is not strict UTF-8") from exc
    if not isinstance(value, dict):
        raise NativeT102CurrentProviderReviewPacketError(
            "review JSON must be an object")
    return value


def _member(path: str, payload: bytes) -> dict[str, Any]:
    return {"path": path, "bytes": len(payload), "sha256": _sha(payload)}


def _validate_candidate_members(candidate_members: Mapping[str, bytes]) -> None:
    if set(candidate_members) != set(CANDIDATE_FILES):
        raise NativeT102CurrentProviderReviewPacketError(
            "candidate member set differs")
    for path, (expected_bytes, expected_sha256) in CANDIDATE_FILES.items():
        payload = candidate_members[path]
        if not isinstance(payload, bytes) or (
            len(payload), _sha(payload)
        ) != (expected_bytes, expected_sha256):
            raise NativeT102CurrentProviderReviewPacketError(
                f"candidate member differs: {path}")


def _validate_verification(
    verification: Mapping[str, Any], candidate_members: Mapping[str, bytes],
) -> None:
    fields = {
        "schema", "status", "candidate_commit", "candidate_files",
        "focused_tests_passed", "github_checks_passed",
        "execution_grant_gate_tested", "fused_composition_tested",
        "real_endpoint_opened", "os_device_handles", "hardware_writes",
        "physical_movements", "independent_review_complete",
        "transport_implementation_qualified", "physical_authority",
    }
    expected_files = [
        _member(path, candidate_members[path]) for path in sorted(CANDIDATE_FILES)
    ]
    constants = {
        "schema": VERIFICATION_SCHEMA,
        "status": "PASS_OFFLINE_NO_HARDWARE",
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_files": expected_files,
        "focused_tests_passed": 40,
        "github_checks_passed": 14,
        "execution_grant_gate_tested": True,
        "fused_composition_tested": True,
        "real_endpoint_opened": False,
        "os_device_handles": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "physical_authority": False,
    }
    if set(verification) != fields or any(
        verification[key] != value for key, value in constants.items()
    ):
        raise NativeT102CurrentProviderReviewPacketError(
            "offline verification differs or exceeds retained evidence")


def _instructions() -> bytes:
    return f"""# Current native T=102 provider independent-review handoff

Candidate commit: `{CANDIDATE_COMMIT}`

This archive is review input only. It is not an approval, executable package,
endpoint authorization, or physical authority. The independent reviewer must:

1. verify every member against `manifest.json`;
2. confirm a sink-issued execution grant is required before endpoint open;
3. confirm that grant binds the exact endpoint and canonical T=102 bytes and is
   consumed before the only movement write;
4. inspect the pre-open and post-open identity checks and exact serial settings;
5. confirm all waits and lines are bounded and no fallback, reopen, resend,
   purge, reset, torque, homing, startup movement, or automatic retry exists;
6. inspect the fused composition from camera-reviewed permit through durable
   start, authority and permit consumption, transport, and terminal no-replay;
7. verify two T=105 requests are feedback-only and that T=1021/T=1051 evidence
   remains unauthenticated until separately captured from the installed device;
8. record findings in a separately authenticated decision without changing
   this archive.

Even a passing source review does not authorize an endpoint open or movement.
""".encode("utf-8")


@dataclass(frozen=True, slots=True)
class NativeT102CurrentProviderReviewPacketResultV1:
    packet_bytes: bytes
    packet_sha256: str
    manifest_sha256: str
    candidate_commit: str
    member_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rocell.native_t102_current_provider_review_packet_result.v1",
            "status": STATUS,
            "packet_sha256": self.packet_sha256,
            "manifest_sha256": self.manifest_sha256,
            "candidate_commit": self.candidate_commit,
            "member_count": self.member_count,
            "independent_review_complete": False,
            "transport_implementation_qualified": False,
            "endpoint_open_authorized": False,
            "execution_authorized": False,
            "hardware_access": False,
            "physical_authority": False,
        }


def build_native_t102_current_provider_review_packet_v1(
    *, candidate_members: Mapping[str, bytes], verification_record: bytes,
) -> NativeT102CurrentProviderReviewPacketResultV1:
    """Build deterministic, authority-free material for an external review."""

    _validate_candidate_members(candidate_members)
    verification = _strict_json(verification_record)
    _validate_verification(verification, candidate_members)
    if verification_record != _canonical(verification):
        raise NativeT102CurrentProviderReviewPacketError(
            "offline verification must use canonical JSON bytes")
    members = {
        **candidate_members,
        "evidence/offline-verification.json": verification_record,
        "REVIEW_INSTRUCTIONS.md": _instructions(),
    }
    manifest = {
        "schema": SCHEMA,
        "candidate": "CURRENT_WINDOWS_NATIVE_T102_SERIAL_PROVIDER",
        "candidate_commit": CANDIDATE_COMMIT,
        "status": STATUS,
        "members": [_member(path, members[path]) for path in sorted(members)],
        "execution_grant_gate_present": True,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "endpoint_open_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    manifest_bytes = _canonical(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True,
    ) as archive:
        for path, payload in (("manifest.json", manifest_bytes),
                              *sorted(members.items())):
            info = zipfile.ZipInfo(path, _ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, payload)
    packet = output.getvalue()
    if len(packet) > MAX_PACKET_BYTES:
        raise NativeT102CurrentProviderReviewPacketError(
            "review packet exceeds size bound")
    inspected = inspect_native_t102_current_provider_review_packet_v1(packet)
    return NativeT102CurrentProviderReviewPacketResultV1(
        packet, _sha(packet), _sha(manifest_bytes), CANDIDATE_COMMIT,
        inspected.member_count,
    )


def inspect_native_t102_current_provider_review_packet_v1(
    packet: bytes,
) -> NativeT102CurrentProviderReviewPacketResultV1:
    """Strictly inspect retained packet bytes without extracting or executing."""

    if not isinstance(packet, bytes) or not packet \
            or len(packet) > MAX_PACKET_BYTES:
        raise NativeT102CurrentProviderReviewPacketError(
            "review packet size is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(packet), "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) \
                    or set(names) != {"manifest.json", *_FIXED_MEMBERS}:
                raise NativeT102CurrentProviderReviewPacketError(
                    "review packet membership differs")
            if any(
                PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or "\\" in name for name in names
            ):
                raise NativeT102CurrentProviderReviewPacketError(
                    "review packet contains an unsafe path")
            if any(
                item.compress_type != zipfile.ZIP_STORED or item.flag_bits & 1
                or item.file_size > MAX_PACKET_BYTES for item in infos
            ) or sum(item.file_size for item in infos) > MAX_PACKET_BYTES:
                raise NativeT102CurrentProviderReviewPacketError(
                    "review packet member exceeds bounds")
            payloads: dict[str, bytes] = {}
            remaining = MAX_PACKET_BYTES
            for item in infos:
                with archive.open(item) as member:
                    payload = member.read(min(item.file_size, remaining) + 1)
                if len(payload) != item.file_size or len(payload) > remaining:
                    raise NativeT102CurrentProviderReviewPacketError(
                        "review packet member exceeds bounds")
                payloads[item.filename] = payload
                remaining -= len(payload)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise NativeT102CurrentProviderReviewPacketError(
            "review packet is not a valid archive") from exc

    candidate_members = {path: payloads[path] for path in CANDIDATE_FILES}
    _validate_candidate_members(candidate_members)
    verification = _strict_json(payloads["evidence/offline-verification.json"])
    _validate_verification(verification, candidate_members)
    if payloads["evidence/offline-verification.json"] != _canonical(verification):
        raise NativeT102CurrentProviderReviewPacketError(
            "offline verification must use canonical JSON bytes")
    manifest = _strict_json(payloads["manifest.json"])
    expected_manifest = {
        "schema": SCHEMA,
        "candidate": "CURRENT_WINDOWS_NATIVE_T102_SERIAL_PROVIDER",
        "candidate_commit": CANDIDATE_COMMIT,
        "status": STATUS,
        "members": [
            _member(path, payloads[path]) for path in sorted(_FIXED_MEMBERS)
        ],
        "execution_grant_gate_present": True,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "endpoint_open_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    if manifest != expected_manifest:
        raise NativeT102CurrentProviderReviewPacketError(
            "review manifest differs or exceeds review-only authority")
    return NativeT102CurrentProviderReviewPacketResultV1(
        packet, _sha(packet), _sha(payloads["manifest.json"]),
        CANDIDATE_COMMIT, len(_FIXED_MEMBERS),
    )


__all__ = [
    "CANDIDATE_COMMIT", "CANDIDATE_FILES", "MAX_PACKET_BYTES", "SCHEMA",
    "STATUS", "VERIFICATION_SCHEMA",
    "NativeT102CurrentProviderReviewPacketError",
    "NativeT102CurrentProviderReviewPacketResultV1",
    "build_native_t102_current_provider_review_packet_v1",
    "inspect_native_t102_current_provider_review_packet_v1",
]
