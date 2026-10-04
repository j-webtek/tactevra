"""Deterministic, zero-I/O handoff packet for independent r97 review.

The packet makes the exact source/image evidence portable.  Building or
inspecting it cannot approve firmware, bind a physical configuration epoch,
open a controller, or authorize installation or motion.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import PurePosixPath
from typing import Any, Mapping
import zipfile


SCHEMA = "rocell.r97_independent_review_packet.v1"
STATUS = "AWAITING_INDEPENDENT_REVIEW_NOT_INSTALLED"
MAX_PACKET_BYTES = 32 * 1024 * 1024
_SOURCE_NAMES = (
    "source/RoArm-M3_example.ino",
    "source/production_runtime_v1.h",
)
_FIXED_NAMES = (
    *_SOURCE_NAMES,
    "artifacts/RoArm-M3_example.ino.bin",
    "artifacts/RoArm-M3_example.ino.elf",
    "evidence/attachment-compile-review.json",
    "evidence/first-party-review.json",
    "REVIEW_INSTRUCTIONS.md",
)
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class R97IndependentReviewPacketError(ValueError):
    """The review packet is incomplete, ambiguous, or internally inconsistent."""


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                   allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json(payload: bytes, label: str) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise R97IndependentReviewPacketError(
                    f"{label} contains duplicate field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda item: (_ for _ in ()).throw(
                               R97IndependentReviewPacketError(
                                   f"{label} contains {item}")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise R97IndependentReviewPacketError(
            f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise R97IndependentReviewPacketError(f"{label} must be an object")
    return value


def _member_info(name: str, data: bytes) -> dict[str, Any]:
    return {"path": name, "bytes": len(data), "sha256": _sha(data)}


def _instructions(app_sha256: str, compile_export_id: str) -> bytes:
    return f"""# Independent r97 review handoff

This archive is evidence for review, not an approval or deployment bundle.

Expected app SHA-256: `{app_sha256}`
Compile export: `{compile_export_id}`

The independent reviewer must, using a separate review record and identity:

1. verify every member against `manifest.json`;
2. inspect both source files for the documented narrow command surface;
3. reproduce the build or independently link the app image to the reviewed source;
4. verify startup is safe-idle and contains no startup servo write;
5. verify exactly one seven-servo group-write call site and no retry/replay path;
6. verify malformed input and failed feedback terminal-lock the runtime;
7. verify the runtime app-hash attestation and the null configuration epoch;
8. record any finding without modifying this archive.

Even a passing review does not authorize installation, startup, torque, or
movement. A separately measured configuration epoch and explicit later
physical authorization remain required.
""".encode("utf-8")


@dataclass(frozen=True, slots=True)
class R97ReviewPacketResult:
    packet_bytes: bytes
    packet_sha256: str
    manifest_sha256: str
    app_sha256: str
    member_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rocell.r97_independent_review_packet_result.v1",
            "status": STATUS,
            "packet_sha256": self.packet_sha256,
            "manifest_sha256": self.manifest_sha256,
            "app_sha256": self.app_sha256,
            "member_count": self.member_count,
            "independent_review_complete": False,
            "configuration_epoch_bound": False,
            "hardware_access": False,
            "physical_authority": False,
        }


def build_r97_review_packet(
    *,
    sources: Mapping[str, bytes],
    app_image: bytes,
    elf_image: bytes,
    compile_report: bytes,
    first_party_report: bytes,
) -> R97ReviewPacketResult:
    """Build deterministic archive bytes from already collected offline evidence."""

    if set(sources) != {"RoArm-M3_example.ino", "production_runtime_v1.h"}:
        raise R97IndependentReviewPacketError("r97 source membership differs")
    if not app_image or not elf_image:
        raise R97IndependentReviewPacketError("r97 linked artifacts are missing")
    compile_value = _strict_json(compile_report, "compile report")
    review_value = _strict_json(first_party_report, "first-party review")
    app_sha256 = _sha(app_image)
    if (
        compile_value.get("status") != "COMPILED"
        or compile_value.get("artifact_hashes", {}).get(
            "RoArm-M3_example.ino.bin") != app_sha256
    ):
        raise R97IndependentReviewPacketError(
            "compile report does not bind the supplied app image")
    if (
        review_value.get("status")
        != "COMPILED_AWAITING_INDEPENDENT_REVIEW_NOT_INSTALLED"
        or review_value.get("app_sha256") != app_sha256
        or review_value.get("independent_review_complete") is not False
        or review_value.get("hardware_access") is not False
        or review_value.get("physical_authority") is not False
    ):
        raise R97IndependentReviewPacketError(
            "first-party report does not retain the r97 blocker")
    compile_id = review_value.get("compile_export_id")
    if not isinstance(compile_id, str) or not compile_id:
        raise R97IndependentReviewPacketError("compile export ID is missing")

    members = {
        "source/RoArm-M3_example.ino": sources["RoArm-M3_example.ino"],
        "source/production_runtime_v1.h": sources["production_runtime_v1.h"],
        "artifacts/RoArm-M3_example.ino.bin": app_image,
        "artifacts/RoArm-M3_example.ino.elf": elf_image,
        "evidence/attachment-compile-review.json": compile_report,
        "evidence/first-party-review.json": first_party_report,
        "REVIEW_INSTRUCTIONS.md": _instructions(app_sha256, compile_id),
    }
    manifest = {
        "schema": SCHEMA,
        "candidate": "r97",
        "status": STATUS,
        "compile_export_id": compile_id,
        "app_sha256": app_sha256,
        "members": [_member_info(name, members[name]) for name in sorted(members)],
        "independent_review_complete": False,
        "configuration_epoch_bound": False,
        "firmware_uploaded": False,
        "controller_started": False,
        "movement_command_sent": False,
        "physical_authority": False,
    }
    manifest_bytes = _canonical(manifest)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED,
                         strict_timestamps=True) as archive:
        for name, data in (("manifest.json", manifest_bytes), *sorted(members.items())):
            info = zipfile.ZipInfo(name, _ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, data)
    packet = output.getvalue()
    if len(packet) > MAX_PACKET_BYTES:
        raise R97IndependentReviewPacketError("review packet exceeds size bound")
    inspected = inspect_r97_review_packet(packet)
    return R97ReviewPacketResult(
        packet_bytes=packet,
        packet_sha256=_sha(packet),
        manifest_sha256=_sha(manifest_bytes),
        app_sha256=app_sha256,
        member_count=inspected.member_count,
    )


def inspect_r97_review_packet(packet: bytes) -> R97ReviewPacketResult:
    """Fail closed while checking a packet; creates no review or physical authority."""

    if not packet or len(packet) > MAX_PACKET_BYTES:
        raise R97IndependentReviewPacketError("review packet size is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(packet), "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise R97IndependentReviewPacketError(
                    "review packet contains duplicate members")
            expected = {"manifest.json", *_FIXED_NAMES}
            if set(names) != expected:
                raise R97IndependentReviewPacketError(
                    "review packet membership differs")
            for name in names:
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise R97IndependentReviewPacketError(
                        "review packet contains an unsafe member path")
            if any(
                item.compress_type != zipfile.ZIP_STORED
                or item.flag_bits & 1
                or item.file_size > MAX_PACKET_BYTES
                for item in infos
            ) or sum(item.file_size for item in infos) > MAX_PACKET_BYTES:
                raise R97IndependentReviewPacketError(
                    "review packet member exceeds size or format bound")
            payloads = {}
            remaining = MAX_PACKET_BYTES
            for item in infos:
                with archive.open(item) as member:
                    data = member.read(min(item.file_size, remaining) + 1)
                if len(data) != item.file_size or len(data) > remaining:
                    raise R97IndependentReviewPacketError(
                        "review packet member exceeds size bound")
                payloads[item.filename] = data
                remaining -= len(data)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise R97IndependentReviewPacketError("review packet is not a valid archive") from exc

    manifest = _strict_json(payloads["manifest.json"], "manifest")
    expected_fields = {
        "schema", "candidate", "status", "compile_export_id", "app_sha256",
        "members", "independent_review_complete", "configuration_epoch_bound",
        "firmware_uploaded", "controller_started", "movement_command_sent",
        "physical_authority",
    }
    if set(manifest) != expected_fields:
        raise R97IndependentReviewPacketError("manifest fields differ")
    if (
        manifest["schema"] != SCHEMA
        or manifest["candidate"] != "r97"
        or manifest["status"] != STATUS
        or manifest["independent_review_complete"] is not False
        or manifest["configuration_epoch_bound"] is not False
        or manifest["firmware_uploaded"] is not False
        or manifest["controller_started"] is not False
        or manifest["movement_command_sent"] is not False
        or manifest["physical_authority"] is not False
    ):
        raise R97IndependentReviewPacketError("manifest exceeds review-only authority")
    raw_members = manifest["members"]
    if not isinstance(raw_members, list) or len(raw_members) != len(_FIXED_NAMES):
        raise R97IndependentReviewPacketError("manifest member list differs")
    described: set[str] = set()
    for entry in raw_members:
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}:
            raise R97IndependentReviewPacketError("manifest member entry differs")
        name = entry["path"]
        if name in described or name not in _FIXED_NAMES:
            raise R97IndependentReviewPacketError("manifest member identity differs")
        data = payloads[name]
        if entry["bytes"] != len(data) or entry["sha256"] != _sha(data):
            raise R97IndependentReviewPacketError("manifest member digest differs")
        described.add(name)
    app_sha256 = _sha(payloads["artifacts/RoArm-M3_example.ino.bin"])
    if manifest["app_sha256"] != app_sha256:
        raise R97IndependentReviewPacketError("manifest app digest differs")
    return R97ReviewPacketResult(
        packet_bytes=packet,
        packet_sha256=_sha(packet),
        manifest_sha256=_sha(payloads["manifest.json"]),
        app_sha256=app_sha256,
        member_count=len(_FIXED_NAMES),
    )


__all__ = [
    "MAX_PACKET_BYTES",
    "SCHEMA",
    "STATUS",
    "R97IndependentReviewPacketError",
    "R97ReviewPacketResult",
    "build_r97_review_packet",
    "inspect_r97_review_packet",
]
