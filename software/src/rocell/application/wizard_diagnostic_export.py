"""Bounded, operator-readable wizard diagnostics; never commissioning authority.

Construction is inert.  A server/CLI assigns the absolute export root, and an
explicit ``prepare(create=True)`` action may create that one directory.  Each
export creates a fresh child and publishes its manifest last.  No existing
files are overwritten, no operational store is read, and no archive is built.

Only caller-supplied JSON records and small UTF-8 text attachments are accepted.
Obvious credential keys and inline credentials are redacted, but that is not a
general private-data detector: callers must not submit camera pixels, arbitrary
debug dumps or private content.  Hashes detect accidental alteration; they are
not signatures and cannot establish hardware provenance or physical authority.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from threading import Lock
from typing import Any
import uuid

from rocell import __version__
from rocell.application.physical_onboarding_durability import (
    PhysicalOnboardingDurabilityError,
    read_bounded_regular_file,
    safe_root,
)


EXPORT_SCHEMA = "rocell.wizard-diagnostic-export.v1"
MAX_EVENTS = 2000
MAX_ATTACHMENTS = 8
MAX_RECORD_BYTES = 256 * 1024
MAX_ATTACHMENT_BYTES = 1024 * 1024
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024
MAX_STRING_CHARS = 64 * 1024
MAX_NODES = 20000
MAX_DEPTH = 12
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_EXPORT_NAME = re.compile(r"wizard-\d{8}T\d{12}Z-[0-9a-f]{32}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_TEXT_SUFFIXES = {".txt", ".log", ".md", ".json", ".jsonl"}
_SECRET_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "apikey",
    "authorization",
    "authentication",
    "credential",
    "credentials",
    "cookie",
    "setcookie",
    "privatekey",
    "clientsecret",
    "accesstoken",
    "refreshtoken",
    "sessiontoken",
    "csrftoken",
    "csrftokenvalue",
    "bearertoken",
    "proxyauthorization",
    "sessionkey",
    "secretkey",
    "signingkey",
    "connectionstring",
}
_INLINE_CREDENTIAL = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_ -]?key|access[_ -]?token|"
    r"refresh[_ -]?token|client[_ -]?secret|token|authorization|cookie)"
    r"(\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_HEADER_CREDENTIAL = re.compile(
    r"(?im)\b(?:proxy-authorization|authorization|cookie|set-cookie)\s*:\s*[^\r\n]*"
)
_URL_CREDENTIAL = re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@")
_LIMITATIONS = [
    "Diagnostic export only; it cannot commission hardware or authorize motion/contact.",
    "Source, session and mode are caller-supplied observations, not independently attested.",
    "SHA-256 checks detect changed bytes but do not authenticate the author or hardware.",
    "No operational ledgers, raw camera frames or native capture datasets are copied.",
    "Obvious credentials are redacted; review remaining private content before sharing.",
    "A missing or invalid final manifest means an incomplete/unusable diagnostic export.",
]


class WizardDiagnosticExportError(ValueError):
    """Invalid input, unsafe destination, or incomplete diagnostic publication."""


def _json_bytes(value: object, *, pretty: bool = True) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
        + "\n"
    ).encode("ascii")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _redact_text(text: str) -> str:
    # Remove complete credential headers and schemes first: removing only the
    # word 'Bearer' from 'Authorization: Bearer secret' would leak the secret.
    text = _HEADER_CREDENTIAL.sub("[REDACTED-CREDENTIAL-HEADER]", text)
    text = _BEARER.sub("[REDACTED-AUTHORIZATION]", text)
    text = _INLINE_CREDENTIAL.sub(lambda match: f"{match[1]}{match[2]}[REDACTED]", text)
    return _URL_CREDENTIAL.sub(r"\1[REDACTED]@", text)


def _sanitize(value: object, *, depth: int = 0, budget: list[int] | None = None) -> Any:
    """Validate bounded JSON values and redact normalized nested credential keys."""
    if budget is None:
        budget = [MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_DEPTH:
        raise WizardDiagnosticExportError("record exceeds its nesting/item budget")
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise WizardDiagnosticExportError(
                "record integer exceeds signed 64-bit range"
            )
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise WizardDiagnosticExportError("record contains a nonfinite number")
        return value
    if type(value) is str:
        if len(value) > MAX_STRING_CHARS:
            raise WizardDiagnosticExportError(
                "record string exceeds its character budget"
            )
        if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
            raise WizardDiagnosticExportError(
                "record string contains control characters"
            )
        return _redact_text(value)
    if isinstance(value, Mapping):
        if len(value) > MAX_NODES:
            raise WizardDiagnosticExportError("record mapping exceeds its item budget")
        result = {}
        for key, item in value.items():
            if type(key) is not str or not key or len(key) > 128:
                raise WizardDiagnosticExportError(
                    "record keys must be short nonempty strings"
                )
            if any(ord(char) < 32 for char in key):
                raise WizardDiagnosticExportError(
                    "record key contains control characters"
                )
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            secret = normalized in _SECRET_KEYS or normalized.endswith(
                ("password", "secret", "apikey", "token")
            )
            result[key] = (
                "[REDACTED]"
                if secret
                else _sanitize(item, depth=depth + 1, budget=budget)
            )
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_NODES:
            raise WizardDiagnosticExportError("record sequence exceeds its item budget")
        return [_sanitize(item, depth=depth + 1, budget=budget) for item in value]
    raise WizardDiagnosticExportError(
        "records must contain JSON values, not bytes/objects"
    )


def sanitize_diagnostic_record(
    value: object, *, maximum_bytes: int = MAX_RECORD_BYTES
) -> Any:
    """Return a bounded JSON copy with obvious credentials redacted.

    Shared by service views and durable diagnostic logging so redaction happens
    before persistence or browser delivery, not only during a later export.
    This is not an unrestricted private-data detection guarantee.
    """
    if type(maximum_bytes) is not int or not 1 <= maximum_bytes <= MAX_EXPORT_BYTES:
        raise WizardDiagnosticExportError("invalid diagnostic record byte budget")
    sanitized = _sanitize(value)
    if len(_json_bytes(sanitized)) > maximum_bytes:
        raise WizardDiagnosticExportError("diagnostic record exceeds its byte budget")
    return sanitized


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise WizardDiagnosticExportError("JSON contains duplicate fields")
        result[key] = value
    return result


def _parse_json(payload: bytes) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                WizardDiagnosticExportError("JSON contains nonfinite values")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise WizardDiagnosticExportError(
            "attachment/export is not bounded strict UTF-8 JSON"
        ) from exc


def _safe_component(name: str, *, filename: bool = False) -> None:
    if (
        not name
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in name)
        or name.split(".")[0].upper() in _RESERVED
        or name.split(".")[0].upper()
        in {"COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³"}
    ):
        raise WizardDiagnosticExportError("export path has an unsafe Windows component")
    if filename and _NAME.fullmatch(name) is None:
        raise WizardDiagnosticExportError(
            "attachment name must be a short plain filename"
        )


def _absolute_directory(path: Path) -> Path:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or str(path).startswith(("\\\\", "//"))
    ):
        raise WizardDiagnosticExportError(
            "assign an absolute local export directory, not UNC/device/relative paths"
        )
    if path == Path(path.anchor):
        raise WizardDiagnosticExportError(
            "a filesystem root is not an export directory"
        )
    for part in path.parts[1:]:
        _safe_component(part)
    return path


def _checked_directory(path: Path) -> Path:
    try:
        # A drive root is eligible only as an internal ancestor guard, never as
        # the externally assigned export destination.
        selected = path if path == Path(path.anchor) else _absolute_directory(path)
        return safe_root(selected, label="wizard diagnostic directory")
    except (OSError, PhysicalOnboardingDurabilityError) as exc:
        raise WizardDiagnosticExportError(
            "diagnostic directory is unavailable or traverses a link/reparse point"
        ) from exc


@contextmanager
def _directory_guard(
    path: Path,
    *,
    allow_directory_write_sharing: bool = False,
    confirm_handle_cleanup: bool = False,
) -> Iterator[None]:
    """Pin Windows directory ancestry against delete/rename during publication.

    On other hosts ancestry is checked but is not a hostile-concurrent-writer
    isolation boundary. Export integrity is diagnostic, not M1 crash authority.
    The private opt-in permits Windows M1 child-file ReplaceFileW operations;
    it still denies delete sharing, but does not exclude writable directory
    handles. M1 retains its own lease, path and content checks. Diagnostic
    publication/verification must keep the stricter default. The capture-time
    checksum owner additionally requires positive directory-handle cleanup;
    legacy export callers retain their existing cleanup semantics by default.
    """
    if type(confirm_handle_cleanup) is not bool:
        raise WizardDiagnosticExportError("invalid directory cleanup policy")
    _checked_directory(path)
    handles: list[Any] = []
    kernel32 = None
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateFileW.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            ]
            kernel32.CreateFileW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            # GENERIC_READ is intentional: an attributes-only handle does not
            # enforce the same sharing restrictions on Windows. Keep read-only
            # sharing on every ancestor until publication/verification ends,
            # except the explicit M1 lease-pointer replacement compatibility
            # mode. Neither mode permits delete/rename sharing.
            # Child-file creation does not require another writable directory
            # handle; a real Windows rename regression exercises this boundary.
            for directory in reversed((path, *path.parents)):
                handle = kernel32.CreateFileW(
                    str(directory),
                    0x80000000,
                    0x3 if allow_directory_write_sharing else 0x1,
                    None,
                    3,
                    0x02200000,
                    None,
                )
                if handle == wintypes.HANDLE(-1).value:
                    raise WizardDiagnosticExportError(
                        "cannot pin export directory ancestry"
                    )
                handles.append(handle)
                (
                    _checked_directory(directory)
                    if directory != Path(directory.anchor)
                    else None
                )
        _checked_directory(path)
        yield
    finally:
        if kernel32 is not None:
            _close_directory_handles(kernel32, handles, confirm_handle_cleanup)


def _close_directory_handles(kernel32, handles, confirm_handle_cleanup):
    """Attempt every close even if one fails; never report confirmed cleanup then."""
    unconfirmed = False
    for handle in reversed(handles):
        if not kernel32.CloseHandle(handle):
            unconfirmed = True
    if confirm_handle_cleanup and unconfirmed:
        raise WizardDiagnosticExportError("directory handle cleanup unconfirmed")


def _identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or getattr(metadata, "st_file_attributes", 0) & 0x400
    ):
        raise WizardDiagnosticExportError("export root is not a plain directory")
    return metadata.st_dev, metadata.st_ino


def _new_export_name() -> str:
    return f"wizard-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex}"


def _write_new(path: Path, payload: bytes) -> dict[str, Any]:
    """Exclusive create only; partial files remain available for diagnosis."""
    with path.open("xb") as stream:
        for start in range(0, len(payload), 64 * 1024):
            stream.write(payload[start : start + 64 * 1024])
        stream.flush()
        os.fsync(stream.fileno())
    return {"name": path.name, "bytes": len(payload), "sha256": _sha256(payload)}


def _attachment(name: str, payload: bytes) -> tuple[str, bytes]:
    if type(name) is not str:
        raise WizardDiagnosticExportError("attachment names must be strings")
    _safe_component(name, filename=True)
    if Path(name).suffix.lower() not in _TEXT_SUFFIXES:
        raise WizardDiagnosticExportError(
            "attachments must be UTF-8 text/JSON; archives, media and executables are not accepted"
        )
    if type(payload) is not bytes or len(payload) > MAX_ATTACHMENT_BYTES:
        raise WizardDiagnosticExportError(
            "attachment must be bytes within its size budget"
        )
    suffix = Path(name).suffix.lower()
    if suffix == ".json":
        sanitized = _json_bytes(_sanitize(_parse_json(payload)))
    elif suffix == ".jsonl":
        lines = payload.splitlines()
        if len(lines) > MAX_EVENTS or any(not line for line in lines):
            raise WizardDiagnosticExportError(
                "JSONL attachment has empty/too many lines"
            )
        sanitized = b"".join(
            _json_bytes(_sanitize(_parse_json(line)), pretty=False) for line in lines
        )
    else:
        try:
            decoded = payload.decode("utf-8")
        except UnicodeError as exc:
            raise WizardDiagnosticExportError("text attachment is not UTF-8") from exc
        if any(ord(char) < 32 and char not in "\n\r\t" for char in decoded):
            raise WizardDiagnosticExportError(
                "text attachment contains control characters"
            )
        sanitized = _redact_text(decoded).encode("utf-8")
    if len(sanitized) > MAX_ATTACHMENT_BYTES:
        raise WizardDiagnosticExportError(
            "sanitized attachment exceeds its byte budget"
        )
    exported_name = f"attachment-{name}"
    _safe_component(exported_name, filename=True)
    return exported_name, sanitized


class WizardDiagnosticExporter:
    """Export snapshots into a server-assigned folder with explicit preparation."""

    def __init__(self, export_root: Path) -> None:
        self.export_root = _absolute_directory(export_root)
        self._root_identity: tuple[int, int] | None = None
        self._lock = Lock()

    def validate(self) -> dict[str, Any]:
        """Read-only destination inspection; never create directories or export."""
        existing = os.path.lexists(self.export_root)
        _checked_directory(self.export_root if existing else self.export_root.parent)
        return {
            "path": str(self.export_root),
            "exists": existing,
            "status": (
                "EXISTING_DIRECTORY" if existing else "EXPLICIT_CREATION_REQUIRED"
            ),
            "physical_authority": "NONE",
        }

    def prepare(self, *, create: bool = False) -> dict[str, Any]:
        """Bind the current directory; optionally create just the assigned leaf."""
        if type(create) is not bool:
            raise WizardDiagnosticExportError("create must be a Boolean")
        with self._lock, _directory_guard(self.export_root.parent):
            state = self.validate()
            if not state["exists"]:
                if not create:
                    raise WizardDiagnosticExportError(
                        "export directory is missing; explicit create=True is required"
                    )
                self.export_root.mkdir(exist_ok=False)
            _checked_directory(self.export_root)
            self._root_identity = _identity(self.export_root)
            return {
                "path": str(self.export_root),
                "status": "PREPARED",
                "created": not state["exists"],
                "physical_authority": "NONE",
            }

    def export(
        self,
        snapshot: Mapping[str, Any],
        events: Sequence[Mapping[str, Any]],
        *,
        attachments: Mapping[str, bytes] | None = None,
    ) -> dict[str, Any]:
        """Publish bounded diagnostics and a final integrity manifest, never a release."""
        if not isinstance(snapshot, Mapping):
            raise WizardDiagnosticExportError("snapshot must be a mapping")
        if (
            not isinstance(events, Sequence)
            or isinstance(events, (str, bytes))
            or len(events) > MAX_EVENTS
        ):
            raise WizardDiagnosticExportError(
                "events must be a bounded sequence of mappings"
            )
        if attachments is not None and (
            not isinstance(attachments, Mapping) or len(attachments) > MAX_ATTACHMENTS
        ):
            raise WizardDiagnosticExportError("attachments must be a bounded mapping")
        clean_snapshot = _sanitize(snapshot)
        if len(_json_bytes(clean_snapshot)) > MAX_RECORD_BYTES:
            raise WizardDiagnosticExportError("snapshot exceeds its byte budget")
        chunks = []
        event_bytes = 0
        for event in events:
            if not isinstance(event, Mapping):
                raise WizardDiagnosticExportError("each event must be a mapping")
            chunk = _json_bytes(_sanitize(event), pretty=False)
            event_bytes += len(chunk)
            if len(chunk) > MAX_RECORD_BYTES or event_bytes > MAX_EXPORT_BYTES:
                raise WizardDiagnosticExportError("events exceed their byte budget")
            chunks.append(chunk)
        additional = [
            _attachment(name, payload) for name, payload in (attachments or {}).items()
        ]
        if len({name.casefold() for name, _ in additional}) != len(additional):
            raise WizardDiagnosticExportError("attachment names collide on Windows")
        name = _new_export_name()
        if _EXPORT_NAME.fullmatch(name) is None:
            raise WizardDiagnosticExportError("generated export identifier is invalid")
        created_at = datetime.now(timezone.utc).isoformat()
        provenance = {
            "session_id": clean_snapshot.get("session_id", "NOT_RECORDED"),
            "mode": clean_snapshot.get("mode", "NOT_RECORDED"),
            "source_binding_sha256": clean_snapshot.get(
                "source_binding_sha256", "NOT_RECORDED"
            ),
            "source_identity": clean_snapshot.get("source_identity", "NOT_RECORDED"),
            "software_version": __version__,
        }
        report = {
            "schema": EXPORT_SCHEMA,
            "export_id": name,
            "created_at": created_at,
            "kind": "DIAGNOSTIC_ONLY",
            "physical_authority": "NONE",
            "provenance": provenance,
            "limitations": _LIMITATIONS,
            "event_count": len(events),
            "snapshot": clean_snapshot,
        }
        readme = (
            "# RoCell wizard diagnostics\n\n"
            "This is a diagnostic report, NOT a commissioning bundle or permission to power, move or contact.\n\n"
            "Open report.json for session/mode/source identity, test outcomes and remediation.\n"
            "Read events.jsonl in order for the bounded event history. Attachments are sanitized UTF-8 text/JSON only.\n"
            "manifest.json is published last and lists each included file's bytes and SHA-256.\n"
            "Use verify_export() from rocell.application.wizard_diagnostic_export to check integrity.\n\n"
            "## Limitations\n\n" + "".join(f"- {item}\n" for item in _LIMITATIONS)
        ).encode("utf-8")
        payloads = [
            ("README.md", readme),
            ("report.json", _json_bytes(report)),
            ("events.jsonl", b"".join(chunks)),
            *additional,
        ]
        total = sum(len(payload) for _, payload in payloads)
        if total + MAX_MANIFEST_BYTES > MAX_EXPORT_BYTES:
            raise WizardDiagnosticExportError("export exceeds its total byte budget")
        with self._lock:
            if self._root_identity is None:
                raise WizardDiagnosticExportError(
                    "call prepare() explicitly before exporting"
                )
            with _directory_guard(self.export_root):
                if _identity(self.export_root) != self._root_identity:
                    raise WizardDiagnosticExportError(
                        "assigned export directory identity changed; review and prepare again"
                    )
                destination = self.export_root / name
                try:
                    destination.mkdir(exist_ok=False)
                    with _directory_guard(destination):
                        files = [
                            _write_new(destination / filename, payload)
                            for filename, payload in payloads
                        ]
                        manifest = {
                            "schema": EXPORT_SCHEMA,
                            "export_id": name,
                            "complete": True,
                            "kind": "DIAGNOSTIC_ONLY",
                            "physical_authority": "NONE",
                            "created_at": created_at,
                            "provenance": provenance,
                            "total_payload_bytes": total,
                            "files": files,
                        }
                        manifest["manifest_sha256"] = _sha256(_json_bytes(manifest))
                        manifest_bytes = _json_bytes(manifest)
                        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
                            raise WizardDiagnosticExportError(
                                "manifest exceeds its byte budget"
                            )
                        manifest_file = _write_new(
                            destination / "manifest.json", manifest_bytes
                        )
                        verified = verify_export(destination)
                        if not verified["valid"]:
                            raise WizardDiagnosticExportError(
                                "completed export failed verification; retain it for inspection"
                            )
                except OSError as exc:
                    raise WizardDiagnosticExportError(
                        "export could not finish; no overwrite, deletion or retry was attempted"
                    ) from exc
        return {
            "status": "EXPORTED_DIAGNOSTICS",
            "valid": True,
            "path": str(destination),
            "export_root": str(self.export_root),
            "export_id": name,
            "files": [*files, manifest_file],
            "total_bytes": total + len(manifest_bytes),
            "manifest_sha256": manifest["manifest_sha256"],
            "physical_authority": "NONE",
            "provenance": provenance,
            "limitations": list(_LIMITATIONS),
        }


def _read(path: Path, maximum: int) -> bytes:
    try:
        return read_bounded_regular_file(
            path, maximum_bytes=maximum, label="wizard diagnostic file"
        )
    except (OSError, PhysicalOnboardingDurabilityError) as exc:
        raise WizardDiagnosticExportError(
            "diagnostic file is missing, linked, unreadable or oversized"
        ) from exc


def verify_export(path: Path) -> dict[str, Any]:
    """Read and check one manifest-bounded export; never trust it as authority."""
    try:
        _absolute_directory(path)
        with _directory_guard(path):
            manifest = _parse_json(_read(path / "manifest.json", MAX_MANIFEST_BYTES))
            required = {
                "schema",
                "export_id",
                "complete",
                "kind",
                "physical_authority",
                "created_at",
                "provenance",
                "total_payload_bytes",
                "files",
                "manifest_sha256",
            }
            if (
                not isinstance(manifest, dict)
                or set(manifest) != required
                or manifest["schema"] != EXPORT_SCHEMA
                or manifest["complete"] is not True
                or manifest["kind"] != "DIAGNOSTIC_ONLY"
                or manifest["physical_authority"] != "NONE"
                or manifest["export_id"] != path.name
                or _EXPORT_NAME.fullmatch(path.name) is None
            ):
                raise WizardDiagnosticExportError(
                    "manifest schema, identity or diagnostic scope is invalid"
                )
            core = {
                key: value
                for key, value in manifest.items()
                if key != "manifest_sha256"
            }
            if _sha256(_json_bytes(core)) != manifest["manifest_sha256"]:
                raise WizardDiagnosticExportError("manifest self hash does not match")
            descriptors = manifest["files"]
            if (
                not isinstance(descriptors, list)
                or not 3 <= len(descriptors) <= 3 + MAX_ATTACHMENTS
            ):
                raise WizardDiagnosticExportError("manifest file count is invalid")
            expected: set[str] = set()
            total = 0
            report = None
            observed_event_count = 0
            for entry in descriptors:
                if not isinstance(entry, dict) or set(entry) != {
                    "name",
                    "bytes",
                    "sha256",
                }:
                    raise WizardDiagnosticExportError(
                        "manifest file descriptor is invalid"
                    )
                filename = entry["name"]
                if type(filename) is not str:
                    raise WizardDiagnosticExportError(
                        "manifest filename is not a string"
                    )
                _safe_component(filename, filename=True)
                if filename.casefold() in {item.casefold() for item in expected} or (
                    filename not in {"README.md", "report.json", "events.jsonl"}
                    and not filename.startswith("attachment-")
                ):
                    raise WizardDiagnosticExportError(
                        "manifest has a duplicate or unrecognized filename"
                    )
                if (
                    type(entry["bytes"]) is not int
                    or not 0 <= entry["bytes"] <= MAX_EXPORT_BYTES
                    or type(entry["sha256"]) is not str
                    or _HASH.fullmatch(entry["sha256"]) is None
                ):
                    raise WizardDiagnosticExportError(
                        "manifest byte/hash values are invalid"
                    )
                total += entry["bytes"]
                if total + MAX_MANIFEST_BYTES > MAX_EXPORT_BYTES:
                    raise WizardDiagnosticExportError(
                        "manifest exceeds the export byte budget"
                    )
                payload = _read(path / filename, max(1, entry["bytes"]))
                if (
                    len(payload) != entry["bytes"]
                    or _sha256(payload) != entry["sha256"]
                ):
                    raise WizardDiagnosticExportError(
                        "export file bytes/hash do not match the manifest"
                    )
                expected.add(filename)
                if filename == "report.json":
                    report = _parse_json(payload)
                elif filename == "events.jsonl":
                    lines = payload.splitlines()
                    if len(lines) > MAX_EVENTS:
                        raise WizardDiagnosticExportError(
                            "export event count exceeds its budget"
                        )
                    for line in lines:
                        if len(line) > MAX_RECORD_BYTES or not isinstance(
                            _parse_json(line), dict
                        ):
                            raise WizardDiagnosticExportError(
                                "export events are malformed"
                            )
                    observed_event_count = len(lines)
                elif filename.startswith("attachment-"):
                    _attachment(filename[len("attachment-") :], payload)
            if not {"README.md", "report.json", "events.jsonl"}.issubset(expected):
                raise WizardDiagnosticExportError("export is missing required files")
            # A bounded scandir stops before traversing any unexpected child.
            with os.scandir(path) as listing:
                seen = set()
                for index, item in enumerate(listing):
                    if index >= 4 + MAX_ATTACHMENTS:
                        raise WizardDiagnosticExportError(
                            "export contains unexpected extra files"
                        )
                    seen.add(item.name)
            if seen != expected | {"manifest.json"}:
                raise WizardDiagnosticExportError(
                    "export contains unmanifested or missing files"
                )
            if (
                not isinstance(report, dict)
                or report.get("schema") != EXPORT_SCHEMA
                or report.get("export_id") != path.name
                or report.get("kind") != "DIAGNOSTIC_ONLY"
                or report.get("physical_authority") != "NONE"
                or report.get("provenance") != manifest["provenance"]
                or report.get("created_at") != manifest["created_at"]
                or type(report.get("event_count")) is not int
                or report.get("event_count") != observed_event_count
                or type(manifest["total_payload_bytes"]) is not int
                or manifest["total_payload_bytes"] != total
            ):
                raise WizardDiagnosticExportError(
                    "report and manifest metadata/counts disagree"
                )
        return {
            "valid": True,
            "status": "VERIFIED_DIAGNOSTIC_EXPORT",
            "path": str(path),
            "export_id": path.name,
            "files": descriptors,
            "total_payload_bytes": total,
            "manifest_sha256": manifest["manifest_sha256"],
            "provenance": manifest["provenance"],
            "physical_authority": "NONE",
            "reasons": [],
        }
    except (WizardDiagnosticExportError, OSError, TypeError) as exc:
        return {
            "valid": False,
            "status": "INVALID_DIAGNOSTIC_EXPORT",
            "path": str(path),
            "physical_authority": "NONE",
            "reasons": [str(exc)],
        }
