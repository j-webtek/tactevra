"""Contained, canonical persistence for hardware-incapable PC6 trace replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Mapping

from .typing_trace_journal_v1 import (
    MAX_ARTIFACT_BYTES,
    TRACE_STAGE_ORDER,
    parse_typing_trace_journal_v1,
    replay_typing_trace_journal_v1,
)


SCHEMA = "rocell.typing_trace_package.v1"
STATUS = "SEALED_CONTAINED_ZERO_AUTHORITY_PACKAGE"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_JOURNAL_BYTES = 256 * 1024
_PACKAGE_ID = re.compile(r"^typing-trace-[0-9a-f]{24}$")
_FORBIDDEN_KEYS = frozenset({
    "api_key", "credential", "credentials", "host", "hostname", "password",
    "port", "raw_capture", "secret", "serial_port", "token",
})


class TypingTracePackageV1Error(ValueError):
    """A replay package is unsafe, escaped, mutated, or noncanonical."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingTracePackageV1Error("package value is not canonical JSON") from exc


def _file_payload(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_exact(path: Path, maximum: int, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise TypingTracePackageV1Error(f"{label} is unavailable or a symlink")
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if not payload or len(payload) > maximum:
        raise TypingTracePackageV1Error(f"{label} size is invalid")
    return payload


def _write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()


def _decode_canonical_file(payload: bytes, label: str) -> dict[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TypingTracePackageV1Error(f"{label} is not JSON") from exc
    if not isinstance(document, dict) or _file_payload(document) != payload:
        raise TypingTracePackageV1Error(f"{label} is not canonical")
    return document


def _scan_redaction(value: object) -> tuple[int, int]:
    sensitive = 0
    absolute_paths = 0
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_KEYS:
                sensitive += 1
            child_sensitive, child_paths = _scan_redaction(child)
            sensitive += child_sensitive
            absolute_paths += child_paths
    elif isinstance(value, list):
        for child in value:
            child_sensitive, child_paths = _scan_redaction(child)
            sensitive += child_sensitive
            absolute_paths += child_paths
    elif isinstance(value, str) and (
        PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
    ):
        absolute_paths += 1
    return sensitive, absolute_paths


def _validate_artifact_redaction(payload: bytes, stage: str) -> None:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TypingTracePackageV1Error(
            f"{stage} artifact must be canonical JSON for redaction review") from exc
    if _canonical(value) != payload:
        raise TypingTracePackageV1Error(f"{stage} artifact is not canonical JSON")
    sensitive, absolute_paths = _scan_redaction(value)
    if sensitive or absolute_paths:
        raise TypingTracePackageV1Error(
            f"{stage} artifact violates redaction policy")


def _root(path: Path) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_dir():
        raise TypingTracePackageV1Error("evidence root is unavailable or a symlink")
    return candidate.resolve()


def _artifact_name(ordinal: int, stage: str) -> str:
    return f"{ordinal:02d}-{stage.lower().replace('_', '-')}.json"


def write_typing_trace_package_v1(
    evidence_root: Path,
    journal: Mapping[str, Any],
    artifacts: Mapping[str, bytes],
    *,
    expected_correlation_id: str,
    expected_request_id: str,
) -> Path:
    """Create one immutable-by-convention package beneath an explicit root."""

    root = _root(evidence_root)
    trace = parse_typing_trace_journal_v1(
        journal, expected_correlation_id=expected_correlation_id,
        expected_request_id=expected_request_id)
    replay = replay_typing_trace_journal_v1(
        journal, artifacts, expected_correlation_id=expected_correlation_id,
        expected_request_id=expected_request_id)
    if replay["identical"] is not True:
        raise TypingTracePackageV1Error("artifacts do not match the sealed trace")
    for stage in TRACE_STAGE_ORDER:
        _validate_artifact_redaction(artifacts[stage], stage)
    package_id = f"typing-trace-{trace['typing_trace_journal_sha256'][:24]}"
    package = root / package_id
    try:
        package.mkdir()
        artifact_root = package / "artifacts"
        artifact_root.mkdir()
        journal_payload = _file_payload(dict(journal))
        _write_new(package / "journal.json", journal_payload)
        entries = []
        for ordinal, stage in enumerate(TRACE_STAGE_ORDER):
            name = _artifact_name(ordinal, stage)
            payload = artifacts[stage]
            _write_new(artifact_root / name, payload)
            entries.append({
                "ordinal": ordinal,
                "stage": stage,
                "path": f"artifacts/{name}",
                "bytes": len(payload),
                "sha256": _sha256(payload),
            })
        core = {
            "schema": SCHEMA,
            "status": STATUS,
            "package_id": package_id,
            "typing_trace_journal_sha256": trace[
                "typing_trace_journal_sha256"],
            "journal_path": "journal.json",
            "journal_file_sha256": _sha256(journal_payload),
            "correlation_id": trace["correlation_id"],
            "request_id": trace["request_id"],
            "artifacts": entries,
            "redaction_policy": "NO_SENSITIVE_KEYS_OR_ABSOLUTE_PATHS_V1",
            "sensitive_field_count": 0,
            "absolute_path_count": 0,
            "controller_commands": [],
            "hardware_access": False,
            "physical_authority": False,
        }
        manifest = {**core, "package_sha256": _sha256(_canonical(core))}
        _write_new(package / "manifest.json", _file_payload(manifest))
    except (OSError, KeyError) as exc:
        raise TypingTracePackageV1Error("could not create complete trace package") from exc
    return package


def replay_typing_trace_package_v1(
    evidence_root: Path,
    package_id: str,
    *,
    expected_correlation_id: str,
    expected_request_id: str,
) -> dict[str, Any]:
    """Verify a contained package and replay only its byte identities."""

    root = _root(evidence_root)
    if not isinstance(package_id, str) or _PACKAGE_ID.fullmatch(package_id) is None:
        raise TypingTracePackageV1Error("package_id is invalid")
    package = root / package_id
    if package.is_symlink() or not package.is_dir() or package.resolve().parent != root:
        raise TypingTracePackageV1Error("trace package escapes the evidence root")
    manifest_payload = _read_exact(
        package / "manifest.json", MAX_MANIFEST_BYTES, "manifest")
    manifest = _decode_canonical_file(manifest_payload, "manifest")
    fields = {
        "schema", "status", "package_id", "typing_trace_journal_sha256",
        "journal_path", "journal_file_sha256", "correlation_id", "request_id",
        "artifacts", "redaction_policy", "sensitive_field_count",
        "absolute_path_count", "controller_commands", "hardware_access",
        "physical_authority", "package_sha256",
    }
    if set(manifest) != fields:
        raise TypingTracePackageV1Error("manifest fields are not exact")
    unsigned = dict(manifest)
    claimed = unsigned.pop("package_sha256")
    if not isinstance(claimed, str) or _sha256(_canonical(unsigned)) != claimed:
        raise TypingTracePackageV1Error("manifest package hash is invalid")
    if (
        manifest["schema"] != SCHEMA or manifest["status"] != STATUS
        or manifest["package_id"] != package_id
        or manifest["journal_path"] != "journal.json"
        or manifest["correlation_id"] != expected_correlation_id
        or manifest["request_id"] != expected_request_id
        or manifest["redaction_policy"]
        != "NO_SENSITIVE_KEYS_OR_ABSOLUTE_PATHS_V1"
        or manifest["sensitive_field_count"] != 0
        or manifest["absolute_path_count"] != 0
        or manifest["controller_commands"] != []
        or manifest["hardware_access"] is not False
        or manifest["physical_authority"] is not False
    ):
        raise TypingTracePackageV1Error("manifest identity or authority is invalid")
    journal_payload = _read_exact(
        package / "journal.json", MAX_JOURNAL_BYTES, "journal")
    if _sha256(journal_payload) != manifest["journal_file_sha256"]:
        raise TypingTracePackageV1Error("journal file hash is invalid")
    journal = _decode_canonical_file(journal_payload, "journal")
    trace = parse_typing_trace_journal_v1(
        journal, expected_correlation_id=expected_correlation_id,
        expected_request_id=expected_request_id)
    if trace["typing_trace_journal_sha256"] != manifest[
        "typing_trace_journal_sha256"]:
        raise TypingTracePackageV1Error("manifest binds a different journal")
    entries = manifest["artifacts"]
    if not isinstance(entries, list) or len(entries) != len(TRACE_STAGE_ORDER):
        raise TypingTracePackageV1Error("manifest artifact accounting is invalid")
    artifact_root = package / "artifacts"
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise TypingTracePackageV1Error("artifact directory is unavailable")
    artifacts: dict[str, bytes] = {}
    expected_names = set()
    for ordinal, (stage, entry) in enumerate(zip(TRACE_STAGE_ORDER, entries)):
        name = _artifact_name(ordinal, stage)
        expected_path = f"artifacts/{name}"
        expected_names.add(name)
        if not isinstance(entry, Mapping) or dict(entry) != {
            "ordinal": ordinal, "stage": stage, "path": expected_path,
            "bytes": entry.get("bytes"), "sha256": entry.get("sha256"),
        }:
            raise TypingTracePackageV1Error("manifest artifact order is invalid")
        payload = _read_exact(artifact_root / name, MAX_ARTIFACT_BYTES, stage)
        if len(payload) != entry["bytes"] or _sha256(payload) != entry["sha256"]:
            raise TypingTracePackageV1Error(f"{stage} artifact identity is invalid")
        _validate_artifact_redaction(payload, stage)
        artifacts[stage] = payload
    actual_names = {path.name for path in artifact_root.iterdir()}
    if actual_names != expected_names or {
        path.name for path in package.iterdir()
    } != {"manifest.json", "journal.json", "artifacts"}:
        raise TypingTracePackageV1Error("trace package contains unexpected entries")
    replay = replay_typing_trace_journal_v1(
        journal, artifacts, expected_correlation_id=expected_correlation_id,
        expected_request_id=expected_request_id)
    return {
        "schema": "rocell.typing_trace_package_replay.v1",
        "status": replay["status"],
        "package_id": package_id,
        "package_sha256": manifest["package_sha256"],
        "replay": replay,
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
    }


__all__ = [
    "SCHEMA", "STATUS", "TypingTracePackageV1Error",
    "replay_typing_trace_package_v1", "write_typing_trace_package_v1",
]
