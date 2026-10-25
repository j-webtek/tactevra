"""Private owned-child composition for calibrated position-vector feedback.

There is no command-line entry point.  The future pinned child calls this
module after its supervisor has reconstructed the exact binding and runtime.
The connection uses the existing non-purging owner and the serial attempt keeps
its own durable no-replay journal.  Evidence export copies the verified journal
byte-for-byte into a new immutable directory with a canonical manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping

from .calibrated_position_vector_binding import CalibratedPositionVectorBinding
from .calibrated_position_vector_serial_adapter import (
    execute_position_vector_serial_exchange,
    load_position_vector_serial_attempt,
)
from .calibrated_position_vector_serial_api import (
    WindowsCalibratedPositionVectorSerialApi,
)
from .nonpurging_serial_backend import NonPurgingSerialConnection


EXPORT_SCHEMA = "rocell.position_vector_feedback_serial_attempt_export.v1"
_FILES = ("header.json", "events.jsonl", "result.json")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb", closefd=True) as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def build_calibrated_position_vector_connection(
    binding: CalibratedPositionVectorBinding,
    *,
    current_runtime_sha256: str,
    owned_process_id: int,
    clock_ns: Callable[[], int] = time.monotonic_ns,
) -> NonPurgingSerialConnection:
    """Build the exact inert connection; the first native call occurs at open."""

    if type(binding) is not CalibratedPositionVectorBinding:
        raise ValueError("exact calibrated position-vector binding required")
    api = WindowsCalibratedPositionVectorSerialApi.from_owned_process(
        binding,
        current_runtime_sha256=current_runtime_sha256,
        owned_process_id=owned_process_id,
        clock_ns=clock_ns,
    )
    return NonPurgingSerialConnection(binding, api=api)


def execute_owned_calibrated_position_vector_exchange(
    binding: CalibratedPositionVectorBinding,
    *,
    journal_root: Path,
    current_runtime_sha256: str,
    owned_process_id: int,
    clock_ns: Callable[[], int] = time.monotonic_ns,
    **adapter_dependencies: Any,
) -> Mapping[str, Any]:
    """Run one adapter exchange through the exact admitted connection."""

    connection = build_calibrated_position_vector_connection(
        binding,
        current_runtime_sha256=current_runtime_sha256,
        owned_process_id=owned_process_id,
        clock_ns=clock_ns,
    )
    return execute_position_vector_serial_exchange(
        binding.request,
        journal_root=journal_root,
        transport_factory=lambda: connection,
        **adapter_dependencies,
    )


def export_position_vector_serial_attempt(
    attempt_directory: Path,
    *,
    export_root: Path,
) -> dict[str, Any]:
    """Verify then retain one terminal or interrupted journal without replay."""

    source = Path(attempt_directory)
    retained = load_position_vector_serial_attempt(source)
    root = Path(export_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("export root must be an existing nonsymlink directory")
    target = root.resolve() / (source.name + "-export")
    target.mkdir()
    files: list[dict[str, Any]] = []
    try:
        for name in _FILES:
            path = source / name
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError("attempt journal file is not a regular file")
            raw = path.read_bytes()
            _write_new(target / name, raw)
            files.append(
                {
                    "name": name,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        manifest = {
            "schema": EXPORT_SCHEMA,
            "attempt_directory_name": source.name,
            "recovery_disposition": retained["recovery_disposition"],
            "request_sha256": retained["header"]["request_sha256"],
            "event_count": len(retained["events"]),
            "files": files,
            "automatic_retry_allowed": False,
            "motion_authorized": False,
            "physical_authority": False,
        }
        _write_new(target / "manifest.json", _canonical(manifest) + b"\n")
        return {**manifest, "export_directory": str(target)}
    except Exception:
        # Never erase retained bytes after partial export. The unique directory
        # makes the failed export visible and prevents it being mistaken for a
        # complete manifest-bearing export or silently retried in place.
        raise


__all__ = [
    "EXPORT_SCHEMA",
    "build_calibrated_position_vector_connection",
    "execute_owned_calibrated_position_vector_exchange",
    "export_position_vector_serial_attempt",
]
