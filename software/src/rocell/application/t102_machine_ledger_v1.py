"""Machine-pinned, process-independent one-use T102 authority ledger.

The installer provisions the directory and its ACL. This module never creates
or selects a caller-provided root. A reservation is never rolled back after a
failed preflight or uncertain transport outcome.
"""

from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class T102MachineLedgerError(ValueError):
    pass


def machine_root() -> Path:
    if os.name != "nt":
        return Path("/var/lib/rocell/t102-authority-ledger-v1")
    folder = (C.c_ubyte * 16).from_buffer_copy(bytes.fromhex(
        "825dab62c1fdc34da9dd070d1d495d97"))  # FOLDERID_ProgramData
    shell = C.WinDLL("shell32", use_last_error=True)
    ole = C.WinDLL("ole32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [
        C.c_void_p, W.DWORD, W.HANDLE, C.POINTER(C.c_void_p)]
    shell.SHGetKnownFolderPath.restype = C.c_long
    ole.CoTaskMemFree.argtypes = [C.c_void_p]
    ole.CoTaskMemFree.restype = None
    output = C.c_void_p()
    try:
        if shell.SHGetKnownFolderPath(
            C.byref(folder), 0, None, C.byref(output)
        ) != 0 or not output.value:
            raise T102MachineLedgerError("machine T102 ledger location is unavailable")
        return Path(C.wstring_at(output)) / "RoCell" / "t102-authority-ledger-v1"
    finally:
        if output.value:
            ole.CoTaskMemFree(output)


def _root() -> Path:
    path = machine_root()
    workspace = Path(__file__).resolve().parents[4]
    if (
        not path.is_absolute() or not path.is_dir() or path.is_symlink()
        or path == workspace or workspace in path.parents
    ):
        raise T102MachineLedgerError(
            "machine T102 authority ledger is not provisioned outside the workspace")
    return path.resolve(strict=True)


def _digest(value: str, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise T102MachineLedgerError(f"{name} must be a SHA-256 digest")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _write_new(path: Path, value: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise T102MachineLedgerError(
            "T102 review or authority was already spent or ledger is unavailable") from exc
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _read_exact(path: Path, expected: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        raise T102MachineLedgerError("T102 review reservation is unavailable")
    try:
        with path.open("rb") as stream:
            actual = stream.read(4097)
    except OSError as exc:
        raise T102MachineLedgerError("T102 review reservation is unavailable") from exc
    if len(actual) > 4096 or actual != _canonical(expected):
        raise T102MachineLedgerError("T102 review reservation differs")


def reserve_review(
    consumption_sha256: str, review_sha256: str, goal_sha256: str,
) -> None:
    consumption = _digest(consumption_sha256, "consumption_sha256")
    review = _digest(review_sha256, "review_sha256")
    goal = _digest(goal_sha256, "goal_sha256")
    _write_new(_root() / f"review-{consumption}.json", {
        "schema": "rocell.t102_machine_review_reservation.v1",
        "consumption_sha256": consumption,
        "review_sha256": review,
        "goal_sha256": goal,
    })


def spend_execution(
    consumption_sha256: str,
    review_sha256: str,
    goal_sha256: str,
    authority_id: str,
    issuer_key_id: str,
    signed_payload_sha256: str,
    claim_sha256: str,
) -> None:
    consumption = _digest(consumption_sha256, "consumption_sha256")
    review = _digest(review_sha256, "review_sha256")
    goal = _digest(goal_sha256, "goal_sha256")
    signed = _digest(signed_payload_sha256, "signed_payload_sha256")
    claim = _digest(claim_sha256, "claim_sha256")
    root = _root()
    _read_exact(root / f"review-{consumption}.json", {
        "schema": "rocell.t102_machine_review_reservation.v1",
        "consumption_sha256": consumption,
        "review_sha256": review,
        "goal_sha256": goal,
    })
    authority_key = hashlib.sha256(_canonical({
        "authority_id": authority_id, "issuer_key_id": issuer_key_id,
    })).hexdigest()
    core = {
        "schema": "rocell.t102_machine_execution_spent.v1",
        "consumption_sha256": consumption,
        "review_sha256": review,
        "goal_sha256": goal,
        "authority_sha256": signed,
        "claim_sha256": claim,
    }
    # Spend the global authority identity first. A crash before the review's
    # execution marker must not leave the same signed authority available to
    # a newly constructed consumption receipt for the same review.
    _write_new(root / f"authority-{authority_key}.json", core)
    _write_new(root / f"execution-{consumption}.json", core)
