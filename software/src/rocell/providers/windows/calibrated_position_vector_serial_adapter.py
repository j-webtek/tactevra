"""One-shot Windows serial adapter for calibrated position-vector feedback.

The adapter accepts only the closed request emitted by
``calibrated_position_vector_feedback_execution``.  It journals intent before
creating or opening a transport, writes the fixed T=105 line once, accepts one
installed position-vector T=1051 line, closes, and returns the exact exchange
evidence consumed by the application boundary.

There is deliberately no CLI and no retry path.  A production caller must
construct the already-reviewed non-purging connection behind ``transport``.
Tests use a hardware-incapable transport with the same narrow surface.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping, Protocol

from rocell.arm.feedback_profile import (
    Feedback1051Profile,
    classify_feedback_1051_profile,
)
from rocell.arm.feedback_wire import FeedbackWireError, validate_feedback_response_line
from rocell.calibration.position_vector_campaign import (
    CALIBRATED_FEEDBACK_REQUEST_CONTRACT,
)
from rocell.application.calibrated_position_vector_feedback_execution import (
    EXCHANGE_EVIDENCE_SCHEMA,
)


JOURNAL_SCHEMA = "rocell.position_vector_feedback_serial_attempt_journal.v1"
RESULT_SCHEMA = "rocell.position_vector_feedback_serial_attempt_result.v1"
REQUEST_SCHEMA = "rocell.position_vector_calibration_qualified_feedback_request.v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "attempt_id",
        "runtime_session_id",
        "request_execution_approval_receipt_sha256",
        "execution_prerequisites_sha256",
        "request_contract",
    }
)
_REQUEST_BYTES = CALIBRATED_FEEDBACK_REQUEST_CONTRACT["request_line_utf8"].encode(
    "utf-8"
)


class PositionVectorSerialAdapterError(RuntimeError):
    """The one-shot exchange failed and its journal is terminal."""

    def __init__(self, code: str, journal_directory: Path) -> None:
        super().__init__(code)
        self.code = code
        self.journal_directory = journal_directory


class PositionVectorSerialTransport(Protocol):
    """Narrow surface implemented by the reviewed non-purging connection."""

    def open(self) -> None: ...

    @property
    def in_waiting(self) -> int: ...

    def read(self, size: int, *, timeout_ms: int) -> bytes: ...

    def write(self, payload: bytes) -> int: ...

    def close(self) -> None: ...

    def status(self) -> Mapping[str, Any]: ...


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("clock must return an aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_new(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _append_sync(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    with os.fdopen(descriptor, "ab", closefd=True) as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_request(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REQUEST_FIELDS:
        raise ValueError("position-vector exchange request fields are invalid")
    request = dict(value)
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError("position-vector exchange request schema is invalid")
    for name in ("attempt_id", "runtime_session_id"):
        item = request[name]
        if not isinstance(item, str) or _IDENTIFIER.fullmatch(item) is None:
            raise ValueError(f"{name} is not a bounded identifier")
    for name in (
        "request_execution_approval_receipt_sha256",
        "execution_prerequisites_sha256",
    ):
        item = request[name]
        if not isinstance(item, str) or _DIGEST.fullmatch(item) is None:
            raise ValueError(f"{name} is not a lowercase SHA-256")
    if request["request_contract"] != CALIBRATED_FEEDBACK_REQUEST_CONTRACT:
        raise ValueError("position-vector request contract is not exact")
    return request


@dataclass(slots=True)
class _AttemptJournal:
    directory: Path
    request_sha256: str
    clock: Callable[[], datetime]
    ordinal: int = 0
    head_sha256: str = "0" * 64

    @classmethod
    def begin(
        cls,
        root: Path,
        request: Mapping[str, Any],
        clock: Callable[[], datetime],
    ) -> "_AttemptJournal":
        base = Path(root)
        if base.is_symlink() or not base.is_dir():
            raise ValueError("journal root must be an existing nonsymlink directory")
        base = base.resolve()
        directory = base / f"position-vector-feedback-{request['attempt_id']}"
        directory.mkdir()
        _fsync_directory(base)
        request_sha256 = hashlib.sha256(_canonical(request)).hexdigest()
        header = {
            "schema": JOURNAL_SCHEMA,
            "attempt_id": request["attempt_id"],
            "runtime_session_id": request["runtime_session_id"],
            "request_sha256": request_sha256,
            "request_line_sha256": hashlib.sha256(_REQUEST_BYTES).hexdigest(),
            "automatic_retry_allowed": False,
            "motion_command_count_limit": 0,
            "recovery_disposition": "RETRY_FORBIDDEN_IF_NOT_TERMINAL",
        }
        _write_new(directory / "header.json", _canonical(header) + b"\n")
        _write_new(directory / "events.jsonl", b"")
        _fsync_directory(directory)
        journal = cls(directory, request_sha256, clock)
        journal.event("INTENT_COMMITTED", {})
        return journal

    def event(self, stage: str, details: Mapping[str, Any]) -> None:
        core = {
            "schema": JOURNAL_SCHEMA + ".event",
            "ordinal": self.ordinal,
            "stage": stage,
            "recorded_at": _utc_text(self.clock()),
            "request_sha256": self.request_sha256,
            "previous_event_sha256": self.head_sha256,
            "details": dict(details),
        }
        digest = hashlib.sha256(_canonical(core)).hexdigest()
        _append_sync(
            self.directory / "events.jsonl",
            _canonical({**core, "event_sha256": digest}) + b"\n",
        )
        self.ordinal += 1
        self.head_sha256 = digest

    def finish(self, result: Mapping[str, Any]) -> None:
        document = {
            "schema": RESULT_SCHEMA,
            "request_sha256": self.request_sha256,
            "event_count": self.ordinal,
            "event_head_sha256": self.head_sha256,
            "automatic_retry_allowed": False,
            "result": dict(result),
        }
        _write_new(self.directory / "result.json", _canonical(document) + b"\n")
        _fsync_directory(self.directory)


def load_position_vector_serial_attempt(directory: Path) -> dict[str, Any]:
    """Load and verify a closed or interrupted attempt without replaying it."""

    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("attempt journal directory is unavailable")
    entries = {item.name for item in root.iterdir()}
    if entries not in (
        {"header.json", "events.jsonl"},
        {"header.json", "events.jsonl", "result.json"},
    ):
        raise ValueError("attempt journal entries are not exact")
    header = json.loads((root / "header.json").read_text(encoding="utf-8"))
    if header.get("schema") != JOURNAL_SCHEMA:
        raise ValueError("attempt journal header is invalid")
    previous = "0" * 64
    events = []
    for ordinal, raw in enumerate((root / "events.jsonl").read_bytes().splitlines()):
        event = json.loads(raw)
        digest = event.pop("event_sha256", None)
        if (
            event.get("ordinal") != ordinal
            or event.get("request_sha256") != header.get("request_sha256")
            or event.get("previous_event_sha256") != previous
            or digest != hashlib.sha256(_canonical(event)).hexdigest()
        ):
            raise ValueError("attempt journal event chain is invalid")
        previous = digest
        events.append({**event, "event_sha256": digest})
    result = None
    if "result.json" in entries:
        result = json.loads((root / "result.json").read_text(encoding="utf-8"))
        if (
            result.get("schema") != RESULT_SCHEMA
            or result.get("request_sha256") != header.get("request_sha256")
            or result.get("event_count") != len(events)
            or result.get("event_head_sha256") != previous
            or result.get("automatic_retry_allowed") is not False
        ):
            raise ValueError("attempt journal terminal result is invalid")
    return {
        "header": header,
        "events": events,
        "result": result,
        "recovery_disposition": (
            "TERMINAL_NO_REPLAY" if result is not None
            else "RETRY_FORBIDDEN_EXECUTION_UNCERTAIN"
        ),
    }


def execute_position_vector_serial_exchange(
    request: Mapping[str, Any],
    *,
    journal_root: Path,
    transport_factory: Callable[[], PositionVectorSerialTransport],
    clock: Callable[[], datetime] = _utc_now,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Perform one fixed exchange and return application exchange evidence.

    Every failure after journal creation is terminal.  The function never calls
    ``transport_factory`` twice, never reopens, and never submits a remainder
    after a short write.
    """

    validated = _validate_request(request)
    if not callable(transport_factory):
        raise TypeError("transport_factory must be callable")
    started_at = _utc_text(clock())
    journal = _AttemptJournal.begin(journal_root, validated, clock)
    transport: PositionVectorSerialTransport | None = None
    opened = False
    write_attempt_count = 0
    confirmed_write_bytes = 0
    response_count = 0
    cleanup_confirmed = False
    response_line = b""
    error_code: str | None = None
    try:
        journal.event("TRANSPORT_FACTORY_COMMITTED", {})
        transport = transport_factory()
        journal.event("OPEN_ATTEMPT_COMMITTED", {"open_attempt_count": 1})
        transport.open()
        opened = True
        journal.event("OPEN_CONFIRMED", {"open_count": 1})

        quiet_deadline = monotonic() + 0.25
        while True:
            waiting = transport.in_waiting
            if type(waiting) is not int or waiting < 0:
                raise RuntimeError("INVALID_INPUT_QUEUE_COUNT")
            if waiting:
                observed = transport.read(min(waiting, 2048), timeout_ms=100)
                journal.event(
                    "STARTUP_INPUT_OBSERVED",
                    {
                        "bytes": len(observed),
                        "sha256": hashlib.sha256(observed).hexdigest(),
                    },
                )
                raise RuntimeError("PREEXISTING_INPUT")
            now = monotonic()
            if now >= quiet_deadline:
                break
            sleep(min(0.01, quiet_deadline - now))
        journal.event("QUIET_INPUT_CONFIRMED", {"quiet_interval_ms": 250})

        write_attempt_count = 1
        journal.event(
            "WRITE_ATTEMPT_COMMITTED",
            {
                "write_attempt_count": 1,
                "request_bytes": len(_REQUEST_BYTES),
                "request_sha256": hashlib.sha256(_REQUEST_BYTES).hexdigest(),
            },
        )
        confirmed_write_bytes = transport.write(_REQUEST_BYTES)
        if type(confirmed_write_bytes) is not int or not (
            0 <= confirmed_write_bytes <= len(_REQUEST_BYTES)
        ):
            raise RuntimeError("INVALID_CONFIRMED_WRITE_COUNT")
        journal.event(
            "WRITE_COMPLETED",
            {"confirmed_write_bytes": confirmed_write_bytes},
        )
        if confirmed_write_bytes != len(_REQUEST_BYTES):
            raise RuntimeError("SHORT_WRITE_NO_RETRY")

        response_deadline = monotonic() + 1.0
        maximum = int(
            CALIBRATED_FEEDBACK_REQUEST_CONTRACT["maximum_response_line_bytes"]
        )
        buffer = bytearray()
        while not buffer.endswith(b"\n"):
            waiting = transport.in_waiting
            if type(waiting) is not int or waiting < 0:
                raise RuntimeError("INVALID_INPUT_QUEUE_COUNT")
            if waiting:
                block = transport.read(
                    min(waiting, maximum + 1 - len(buffer)), timeout_ms=100
                )
                if not isinstance(block, bytes):
                    raise RuntimeError("INVALID_RESPONSE_BYTES")
                buffer.extend(block)
                if buffer.count(b"\n") > 1 or len(buffer) > maximum:
                    raise RuntimeError("AMBIGUOUS_OR_OVERSIZED_RESPONSE")
            elif monotonic() >= response_deadline:
                raise RuntimeError("RESPONSE_TIMEOUT_NO_RETRY")
            else:
                sleep(0.01)
        if transport.in_waiting:
            raise RuntimeError("EXTRA_RESPONSE_INPUT")
        response_line = bytes(buffer)
        message = validate_feedback_response_line(
            response_line, max_line_bytes=maximum
        )
        if classify_feedback_1051_profile(message) is not (
            Feedback1051Profile.POSITION_VECTOR_NAMED_POSE
        ):
            raise RuntimeError("POSITION_VECTOR_PROFILE_REQUIRED")
        response_quiet_deadline = monotonic() + 0.25
        while True:
            waiting = transport.in_waiting
            if type(waiting) is not int or waiting < 0:
                raise RuntimeError("INVALID_INPUT_QUEUE_COUNT")
            if waiting:
                raise RuntimeError("EXTRA_RESPONSE_INPUT")
            now = monotonic()
            if now >= response_quiet_deadline:
                break
            sleep(min(0.01, response_quiet_deadline - now))
        response_count = 1
        journal.event(
            "POSITION_VECTOR_RESPONSE_CONFIRMED",
            {
                "response_count": 1,
                "response_bytes": len(response_line),
                "response_sha256": hashlib.sha256(response_line).hexdigest(),
                "post_response_quiet_interval_ms": 250,
            },
        )
    except FeedbackWireError:
        error_code = "INVALID_FEEDBACK_RESPONSE"
    except Exception as exc:
        error_code = str(exc) if type(exc) is RuntimeError else type(exc).__name__
    finally:
        if transport is not None and opened:
            journal.event("CLOSE_ATTEMPT_COMMITTED", {"close_attempt_count": 1})
            try:
                transport.close()
            except Exception:
                error_code = error_code or "CLOSE_FAILED"
        if transport is not None:
            try:
                status = transport.status()
                if isinstance(status, Mapping):
                    observed = status.get("confirmed_write_bytes")
                    if type(observed) is int and 0 <= observed <= len(_REQUEST_BYTES):
                        confirmed_write_bytes = max(confirmed_write_bytes, observed)
                    cleanup_confirmed = status.get("cleanup_confirmed") is True
            except Exception:
                cleanup_confirmed = False
        if opened and not cleanup_confirmed:
            error_code = error_code or "CLEANUP_UNKNOWN"

    finished_at = _utc_text(clock())
    if error_code is None:
        journal.event("TERMINAL_SUCCESS", {"cleanup_confirmed": True})
        evidence = {
            "schema": EXCHANGE_EVIDENCE_SCHEMA,
            "attempt_id": validated["attempt_id"],
            "status": "RESPONSE_OBSERVED_CLOSED",
            "request_line_utf8": _REQUEST_BYTES.decode("utf-8"),
            "response_line_utf8": response_line.decode("utf-8"),
            "request_count": 1,
            "write_attempt_count": write_attempt_count,
            "confirmed_write_bytes": confirmed_write_bytes,
            "automatic_retry_count": 0,
            "response_count": response_count,
            "cleanup_confirmed": cleanup_confirmed,
            "motion_command_count": 0,
            "started_at": started_at,
            "finished_at": finished_at,
            "errors": [],
        }
        journal.finish({"status": "SUCCEEDED", "exchange_evidence": evidence})
        return evidence

    journal.event(
        "TERMINAL_FAILURE",
        {
            "code": error_code,
            "write_attempt_count": write_attempt_count,
            "confirmed_write_bytes": confirmed_write_bytes,
            "response_count": response_count,
            "cleanup_confirmed": cleanup_confirmed,
        },
    )
    journal.finish(
        {
            "status": "FAILED_NO_RETRY",
            "error": error_code,
            "write_attempt_count": write_attempt_count,
            "confirmed_write_bytes": confirmed_write_bytes,
            "response_count": response_count,
            "cleanup_confirmed": cleanup_confirmed,
        }
    )
    raise PositionVectorSerialAdapterError(error_code, journal.directory)


__all__ = [
    "JOURNAL_SCHEMA",
    "PositionVectorSerialAdapterError",
    "PositionVectorSerialTransport",
    "execute_position_vector_serial_exchange",
    "load_position_vector_serial_attempt",
]
