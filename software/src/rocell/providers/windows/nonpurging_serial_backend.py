"""One-owner, non-purging serial lifecycle for a future reviewed worker adapter.

This is NOT registered in ArmFeedbackWorker and grants no commissioning
authority. Only the sealed in-memory Win32 facade can currently open. The
default native facade is unconditionally held before its first Windows call.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from threading import RLock
from typing import Any

from rocell.application.physical_connection_contracts import EvidenceOrigin
from rocell.providers.windows.arm_feedback_worker import ReviewedControllerBinding
from rocell.providers.windows.nonpurging_serial_api import (
    CommTimeouts,
    DcbSettings,
    FIXED_QUERY,
    IncapableWin32SerialApi,
    IoCompletion,
    IoToken,
    MAX_IO_BYTES,
    NATIVE_HOLD,
    NativeSerialError,
    QueueStatus,
    Win32SerialApi,
    WindowsNativeSerialApi,
    _int,
)


MAX_READ_CALLS = 4096
MAX_QUEUE_CALLS = 4096
CANCEL_COMPLETION_MS = 250


@dataclass(frozen=True, slots=True)
class NativeLifecycleIssue:
    code: str
    operation: str
    winerror: int


class NonPurgingSerialConnection:
    """Closed, single-use handle owner with an intentionally small API.

    The existing campaign worker must still supply exact one-use admission,
    final identity resolution, quiet interval, wire parsing, timing evidence
    and qualified persistence. It is not sufficient to call this class from
    the UI. Physical passive access requires the separate live-claim admission;
    ordinary and feedback APIs remain held.
    """

    def __init__(
        self,
        binding: ReviewedControllerBinding,
        *,
        api: IncapableWin32SerialApi | WindowsNativeSerialApi | None = None,
    ) -> None:
        passive = False
        powered = False
        calibrated_position_vector = False
        if type(binding) is not ReviewedControllerBinding:
            # Lazy import preserves the closed legacy feedback child package.
            # A passive selection must never be disguised as firmware evidence.
            from .passive_serial_binding import PassiveSerialBinding

            if type(binding) is PassiveSerialBinding:
                passive = True
            else:
                from .powered_feedback_binding import PoweredFeedbackBinding

                powered = type(binding) is PoweredFeedbackBinding
                if not powered:
                    from .calibrated_position_vector_binding import (
                        CalibratedPositionVectorBinding,
                    )

                    calibrated_position_vector = (
                        type(binding) is CalibratedPositionVectorBinding
                    )
            if not passive and not powered and not calibrated_position_vector:
                raise NativeSerialError("REVIEWED_BINDING_REQUIRED", "construction")
            binding.__post_init__()
        allowed_apis = (IncapableWin32SerialApi, WindowsNativeSerialApi)
        if powered and type(api) is not IncapableWin32SerialApi:
            from .powered_feedback_serial_api import WindowsPoweredFeedbackSerialApi

            if (
                type(api) is not WindowsPoweredFeedbackSerialApi
                or api.admitted_request_sha256 != binding.intent.request_sha256
                or api.expected_path != "\\\\.\\" + binding.identity.port_name
            ):
                raise NativeSerialError(
                    "POWERED_FEEDBACK_PHYSICAL_HELD", "construction"
                )
            allowed_apis = (WindowsPoweredFeedbackSerialApi,)
        if calibrated_position_vector:
            from .calibrated_position_vector_serial_api import (
                WindowsCalibratedPositionVectorSerialApi,
            )

            if (
                type(api) is not WindowsCalibratedPositionVectorSerialApi
                or api.admitted_request_sha256
                != hashlib.sha256(
                    json.dumps(
                        dict(binding.request),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=True,
                        allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest()
                or api.expected_path != "\\\\.\\" + binding.identity.port_name
            ):
                raise NativeSerialError(
                    "CALIBRATED_POSITION_VECTOR_PHYSICAL_HELD", "construction"
                )
            allowed_apis = (WindowsCalibratedPositionVectorSerialApi,)
        if passive:
            from .passive_serial_api import WindowsPassiveSerialApi

            allowed_apis = (IncapableWin32SerialApi, WindowsPassiveSerialApi)
            if api is None:
                api = WindowsPassiveSerialApi(binding.identity.port_name)
            elif (
                type(api) is WindowsPassiveSerialApi
                and api.expected_path != "\\\\.\\" + binding.identity.port_name
            ):
                raise NativeSerialError("PASSIVE_ENDPOINT_CHANGED", "construction")
        if api is not None and type(api) not in allowed_apis:
            raise NativeSerialError("UNREGISTERED_NATIVE_API", "construction")
        incapable = type(api) is IncapableWin32SerialApi
        expected_origin = (
            EvidenceOrigin.SYNTHETIC_REHEARSAL
            if incapable
            else EvidenceOrigin.PHYSICAL_OBSERVATION
        )
        if binding.origin is not expected_origin:
            raise NativeSerialError("ORIGIN_MISMATCH", "construction")
        self._binding = binding
        self._passive = passive
        self._powered = powered
        self._calibrated_position_vector = calibrated_position_vector
        self._api: Win32SerialApi = WindowsNativeSerialApi() if api is None else api
        self._incapable = incapable
        self._lock = RLock()
        self._phase = "CLOSED_UNOPENED"
        self._open_consumed = False
        self._close_consumed = False
        self._write_consumed = False
        self._port: int | None = None
        self._events: dict[str, int] = {}
        self._owned: dict[int, str] = {}
        self._closed_handles = 0
        self._close_attempted: set[int] = set()
        self._pending: IoToken | None = None
        self._cancel_attempted = False
        self._calls: dict[str, int] = {}
        self._primary: NativeLifecycleIssue | None = None
        self._cleanup: list[NativeLifecycleIssue] = []
        self._startup_input_seen = False
        self._largest_prewrite_input = 0
        self._communication_errors = 0
        self._write_bytes = 0
        self._read_bytes = 0
        self._read_digest = hashlib.sha256()
        self._late_read_bytes = b""
        self._configured = False

    @property
    def is_open(self) -> bool:
        """Conservative ownership, not a fresh native API or device query."""
        with self._lock:
            return self._port is not None and self._port in self._owned

    @property
    def late_read_bytes(self) -> bytes:
        """Private evidence-writer input; never include these bytes in UI JSON."""
        with self._lock:
            return self._late_read_bytes

    def status(self) -> dict[str, Any]:
        with self._lock:
            passive_admitted = (
                self._passive
                and not self._incapable
                and self._api.status().get("passive_admission")
                == "LIVE_CHILD_CLAIM_CONSUMED"
            )
            powered_admitted = (
                self._powered
                and not self._incapable
                and self._api.status().get("powered_admission")
                == "LIVE_CHILD_CLAIM_CONSUMED"
            )
            calibrated_admitted = (
                self._calibrated_position_vector
                and not self._incapable
                and self._api.status().get("calibrated_position_vector_admission")
                == "OWNED_PROCESS_BINDING_MATCHED"
            )
            return {
                "schema": "rocell.nonpurging_serial_lifecycle.v1",
                "phase": self._phase,
                "composition": (
                    "HARDWARE_INCAPABLE_REHEARSAL"
                    if self._incapable
                    else (
                        "WINDOWS_CALIBRATED_POSITION_VECTOR_ENGINEERING"
                        if calibrated_admitted
                        else (
                            "WINDOWS_POWERED_FEEDBACK_ENGINEERING"
                            if powered_admitted
                            else (
                                "WINDOWS_PASSIVE_SERIAL_ENGINEERING"
                                if passive_admitted
                                else "WINDOWS_NONPURGING_SERIAL_PHYSICAL_HELD"
                            )
                        )
                    )
                ),
                "binding_sha256": self._binding.binding_sha256,
                "identity_sha256": self._binding.identity.identity_sha256,
                "physical_authority": False,
                "physical_hold": (
                    "COMMAND_COMMISSIONING_REQUIRED"
                    if passive_admitted or powered_admitted
                    else (
                        "CALIBRATED_FEEDBACK_REQUEST_ONLY"
                        if calibrated_admitted
                        else NATIVE_HOLD
                    )
                ),
                "hardware_accessed_by_status": False,
                "arm_connected": False,
                "native_settings_requested": asdict(DcbSettings()),
                "native_timeouts_requested": asdict(CommTimeouts()),
                "settings_readback_verified": self._configured,
                "open_consumed": self._open_consumed,
                "write_consumed": self._write_consumed,
                "close_consumed": self._close_consumed,
                "api_calls": dict(self._calls),
                "resource_counts": {
                    "acquired": len(self._owned) + self._closed_handles,
                    "close_attempted": len(self._close_attempted),
                    "close_confirmed": self._closed_handles,
                    "unresolved": len(self._owned),
                },
                "pending_io_unresolved": self._pending is not None,
                "cleanup_confirmed": not self._owned and self._pending is None,
                "startup_input_observed": self._startup_input_seen,
                "largest_prewrite_input_bytes": self._largest_prewrite_input,
                "communication_error_mask": self._communication_errors,
                "confirmed_write_bytes": self._write_bytes,
                "retained_read_bytes": self._read_bytes,
                "read_bytes_sha256": self._read_digest.hexdigest(),
                "late_read_bytes": len(self._late_read_bytes),
                "late_read_sha256": hashlib.sha256(self._late_read_bytes).hexdigest(),
                "primary_error": (
                    None if self._primary is None else asdict(self._primary)
                ),
                "cleanup_errors": [asdict(issue) for issue in self._cleanup],
                "actual_effect_counts": {
                    "device_opens": int(not self._incapable and self._port is not None),
                    "serial_transactions": 0,
                    "robot_commands_sent": 0,
                    "robot_power_operations": 0,
                },
                "final_power_state": "UNKNOWN_REQUIRES_SEPARATE_OBSERVATION",
                "limitations": [
                    "Native DLL and driver branch is not physically qualified or released.",
                    "No atomic proof ties the opened COM handle to the reviewed USB unit.",
                    "DCB is applied after CreateFile; pre-open RTS/DTR electrical behavior is unproved.",
                    "No buffer-clearing call exists; driver preservation still requires received-unit evidence.",
                    "Bounded waits cannot interrupt every driver open, configure or close call.",
                    "An independently reviewed isolated-process supervisor and coordinator are required.",
                    "Known API cleanup is not a final power observation or permission to retry.",
                ],
            }

    def _issue(
        self, error: Exception, operation: str, *, cleanup: bool = False
    ) -> NativeLifecycleIssue:
        if isinstance(error, NativeSerialError):
            issue = NativeLifecycleIssue(error.code, operation, error.winerror)
        else:
            issue = NativeLifecycleIssue("UNEXPECTED_API_FAILURE", operation, 0)
        if cleanup:
            if len(self._cleanup) < 8:
                self._cleanup.append(issue)
        elif self._primary is None:
            self._primary = issue
        return issue

    def _call(self, name: str, *args: Any) -> Any:
        self._calls[name] = self._calls.get(name, 0) + 1
        try:
            return getattr(self._api, name)(*args)
        except Exception as error:
            # Never expose driver exception messages or discard the original
            # primary error when a later cleanup operation also fails.
            if isinstance(error, NativeSerialError):
                raise
            raise NativeSerialError("UNEXPECTED_API_FAILURE", name) from None

    def _require_open(self) -> int:
        if self._phase != "OPEN" or self._port is None or self._pending is not None:
            raise NativeSerialError("CONNECTION_NOT_USABLE", "admission")
        return self._port

    def _own(self, handle: object, kind: str) -> int:
        value = _int(handle, 1, (1 << 64) - 2, "native_handle")
        if value in self._owned:
            raise NativeSerialError("DUPLICATE_HANDLE", "native_handle")
        self._owned[value] = kind
        return value

    def _queue(self) -> QueueStatus:
        if self._calls.get("queue_status", 0) >= MAX_QUEUE_CALLS:
            raise NativeSerialError("QUEUE_CALL_LIMIT", "queue_status")
        result = self._call("queue_status", self._port)
        if type(result) is not QueueStatus:
            raise NativeSerialError("INVALID_QUEUE_STATUS", "queue_status")
        for field in ("input_bytes", "output_bytes", "error_mask"):
            _int(getattr(result, field), 0, 0xFFFFFFFF, field)
        self._communication_errors |= result.error_mask
        if not self._write_consumed:
            self._startup_input_seen |= result.input_bytes > 0
            self._largest_prewrite_input = max(
                self._largest_prewrite_input, result.input_bytes
            )
        if result.error_mask:
            raise NativeSerialError(
                "COMMUNICATION_ERROR_OBSERVED", "queue_status", result.error_mask
            )
        if result.output_bytes:
            raise NativeSerialError("UNEXPECTED_PENDING_OUTPUT", "queue_status")
        return result

    def open(self) -> None:
        """Exactly one exclusive open, with no fallback/reopen or purge."""
        with self._lock:
            if self._open_consumed or self._close_consumed:
                raise NativeSerialError("ONE_USE_CONNECTION", "open")
            self._open_consumed = True
            self._phase = "OPENING"
            try:
                path = "\\\\.\\" + self._binding.identity.port_name
                self._port = self._own(self._call("create_file", path), "port")
                # Inspect before configuration too; a later read must never
                # erase the fact that startup input was observed here.
                self._queue()
                for kind in (("read",) if self._passive else ("read", "write")):
                    self._events[kind] = self._own(
                        self._call("create_event"), kind + "_event"
                    )
                if type(self._call("get_state", self._port)) is not DcbSettings:
                    raise NativeSerialError("INVALID_STATE_READBACK", "get_state")
                self._call("set_state", self._port, DcbSettings())
                if self._call("get_state", self._port) != DcbSettings():
                    raise NativeSerialError("SETTINGS_READBACK_MISMATCH", "get_state")
                if type(self._call("get_timeouts", self._port)) is not CommTimeouts:
                    raise NativeSerialError("INVALID_TIMEOUT_READBACK", "get_timeouts")
                self._call("set_timeouts", self._port, CommTimeouts())
                if self._call("get_timeouts", self._port) != CommTimeouts():
                    raise NativeSerialError("TIMEOUT_READBACK_MISMATCH", "get_timeouts")
                self._queue()
                self._configured = True
                self._phase = "OPEN"
            except Exception as error:
                self._issue(error, "open")
                self._phase = "FAILED"
                try:
                    self.close()
                except NativeSerialError:
                    pass
                raise

    @property
    def in_waiting(self) -> int:
        with self._lock:
            self._require_open()
            try:
                return self._queue().input_bytes
            except Exception as error:
                self._issue(error, "queue_status")
                self._phase = "FAILED"
                raise

    def _completion(self, token: IoToken, result: Any) -> IoCompletion:
        if type(result) is not IoCompletion or result.state not in {
            "COMPLETE",
            "PENDING",
            "ABORTED",
            "FAILED",
        }:
            raise NativeSerialError("INVALID_IO_COMPLETION", "completion")
        _int(result.transferred, 0, token.size, "completion_count")
        _int(result.winerror, 0, 0xFFFFFFFF, "completion_error")
        if type(result.data) is not bytes:
            raise NativeSerialError("INVALID_IO_COMPLETION", "completion_bytes")
        if result.state == "COMPLETE":
            if result.winerror or len(result.data) != (
                result.transferred if token.kind == "read" else 0
            ):
                raise NativeSerialError("INVALID_IO_COMPLETION", "completion_shape")
        elif result.transferred or result.data or not result.winerror:
            raise NativeSerialError("INVALID_IO_COMPLETION", "nonterminal_shape")
        if result.state != "PENDING":
            self._pending = None
            if result.state == "COMPLETE":
                if token.kind == "write":
                    self._write_bytes += result.transferred
                else:
                    self._read_bytes += result.transferred
                    self._read_digest.update(result.data)
                    if not self._write_consumed and result.transferred:
                        self._startup_input_seen = True
                        self._largest_prewrite_input = max(
                            self._largest_prewrite_input, result.transferred
                        )
        return result

    def _cancel_pending(self) -> None:
        token = self._pending
        if token is None or self._cancel_attempted:
            return
        self._cancel_attempted = True
        try:
            response = self._call("cancel_io", self._port, token)
            if response not in ("REQUESTED", "NOT_FOUND"):
                raise NativeSerialError("INVALID_CANCEL_RESULT", "cancel_io")
        except Exception as error:
            self._issue(error, "cancel_io", cleanup=True)
        # Even NOT_FOUND or a failed cancellation cannot replace this check.
        try:
            result = self._completion(
                token,
                self._call("complete_io", self._port, token, CANCEL_COMPLETION_MS),
            )
            if result.state == "COMPLETE" and token.kind == "read":
                self._late_read_bytes = result.data
            if result.state == "PENDING":
                raise NativeSerialError("CANCEL_COMPLETION_UNCONFIRMED", "complete_io")
            if result.state == "FAILED":
                raise NativeSerialError(
                    "CANCEL_COMPLETED_WITH_ERROR", "complete_io", result.winerror
                )
        except Exception as error:
            self._issue(error, "cancel_completion", cleanup=True)

    def _io(
        self, kind: str, size: int, payload: bytes, timeout_ms: int
    ) -> IoCompletion:
        if self._passive and kind != "read":
            raise NativeSerialError("PASSIVE_WRITES_FORBIDDEN", "io_admission")
        port = self._require_open()
        token = IoToken(self._events[kind], kind, size, payload)
        self._pending = token
        self._cancel_attempted = False
        try:
            result = self._completion(token, self._call("submit_io", port, token))
            if result.state == "PENDING":
                result = self._completion(
                    token, self._call("complete_io", port, token, timeout_ms)
                )
            if result.state == "PENDING":
                raise NativeSerialError("IO_DEADLINE_EXPIRED", kind)
            if result.state != "COMPLETE":
                raise NativeSerialError(
                    "IO_COMPLETED_WITH_ERROR", kind, result.winerror
                )
            return result
        except Exception as error:
            self._issue(error, kind)
            self._phase = "FAILED"
            if not token.submitted:
                self._pending = None
            self._cancel_pending()
            raise

    def write(self, payload: bytes) -> int:
        """Submit exactly the fixed feedback line once; never a remainder."""
        with self._lock:
            if self._passive:
                raise NativeSerialError("PASSIVE_WRITES_FORBIDDEN", "write")
            self._require_open()
            if self._write_consumed:
                raise NativeSerialError("ONE_WRITE_ONLY", "write")
            if type(payload) is not bytes or payload != FIXED_QUERY:
                raise NativeSerialError("FIXED_T105_ONLY", "write")
            try:
                self._queue()
                if self._startup_input_seen:
                    raise NativeSerialError("PREEXISTING_INPUT_OBSERVED", "write")
                self._write_consumed = True
                result = self._io("write", len(payload), payload, 1000)
                if result.transferred != len(FIXED_QUERY):
                    raise NativeSerialError("SHORT_WRITE_NO_RETRY", "write")
                return result.transferred
            except Exception as error:
                self._issue(error, "write")
                self._phase = "FAILED"
                raise

    def read(self, size: int, *, timeout_ms: int = 1000) -> bytes:
        with self._lock:
            self._require_open()
            _int(size, 1, 1024, "read_size")
            _int(timeout_ms, 1, 1000, "read_timeout_ms")
            if (
                self._calls.get("read_admissions", 0) >= MAX_READ_CALLS
                or self._read_bytes + size > MAX_IO_BYTES
            ):
                error = NativeSerialError("READ_BUDGET_EXHAUSTED", "read")
                self._issue(error, "read")
                self._phase = "FAILED"
                raise error
            self._calls["read_admissions"] = self._calls.get("read_admissions", 0) + 1
            return self._io("read", size, b"", timeout_ms).data

    def close(self) -> None:
        """Attempt each acquired handle's cleanup once; never hide failure."""
        with self._lock:
            if self._close_consumed:
                if self._owned or self._pending is not None:
                    raise NativeSerialError("CLEANUP_UNCONFIRMED", "close")
                return
            self._close_consumed = True
            self._cancel_pending()
            if self._pending is not None:
                self._issue(
                    NativeSerialError("PENDING_IO_RESOURCES_RETAINED", "close"),
                    "close",
                    cleanup=True,
                )
            else:
                # Do not restore prior DCB/timeouts/control lines or flush.
                for handle in reversed(tuple(self._owned)):
                    self._close_attempted.add(handle)
                    try:
                        self._call("close_handle", handle)
                        del self._owned[handle]
                        self._closed_handles += 1
                    except Exception as error:
                        self._issue(error, "close_handle", cleanup=True)
            if self._owned or self._pending is not None:
                self._phase = "CLEANUP_UNCONFIRMED"
                raise NativeSerialError("CLEANUP_UNCONFIRMED", "close")
            self._phase = (
                "CLOSED_FAILED" if self._primary or self._cleanup else "CLOSED"
            )
