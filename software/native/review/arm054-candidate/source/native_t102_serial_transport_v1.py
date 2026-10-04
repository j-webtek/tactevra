"""One-shot Windows serial adapter for the ARM-053 production boundary.

Importing or constructing this adapter performs no hardware access.  The
default pyserial backend is loaded lazily by ``open_once``.  Inventory is used
only to verify the explicitly pinned COM identity; it can never select a port.
The adapter has no fallback, reopen, resend, purge, reset, torque, or startup
command operation.

This is a source-level production candidate.  Shipping it does not qualify a
controller, authorize physical use, or compose it with the external-authority
boundary.
"""

from __future__ import annotations

import importlib
import threading
import time
from typing import Any, Callable, Iterable

from rocell.application.native_t102_production_transport_v1 import (
    NativeT102ControllerCaptureV1,
    NativeT102FeedbackSampleV1,
    NativeT102ProductionTransportError,
    NativeT102ProductionTransportV1,
    PinnedNativeT102EndpointV1,
)
from rocell.arm.all_joint_command import JOINT_FIELDS, all_joint_command
from rocell.arm.feedback_wire import (
    require_quiescent_receive_buffer,
    validate_feedback_response_line,
)
from rocell.arm.protocol import decode_line, encode_line, feedback_request


MAX_CAPTURE_LINE_BYTES = 2048
FEEDBACK_SAMPLE_COUNT = 2


class WindowsNativeT102SerialTransportError(
    NativeT102ProductionTransportError
):
    """The one-shot native serial lifecycle failed closed."""


def _positive_timeout(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WindowsNativeT102SerialTransportError(
            f"{label} must be a positive bounded number")
    result = float(value)
    if not 0 < result <= 10:
        raise WindowsNativeT102SerialTransportError(
            f"{label} must be in (0, 10]")
    return result


def _load_default_backend() -> tuple[Callable[[], Any], Callable[[], Iterable[Any]]]:
    """Load pyserial only at the explicit opening boundary."""

    try:
        serial = importlib.import_module("serial")
        list_ports = importlib.import_module("serial.tools.list_ports")
    except ImportError as exc:
        raise WindowsNativeT102SerialTransportError(
            "pyserial is required for the explicit Windows serial opening") from exc
    factory = getattr(serial, "Serial", None)
    inventory = getattr(list_ports, "comports", None)
    if not callable(factory) or not callable(inventory):
        raise WindowsNativeT102SerialTransportError(
            "pyserial backend lacks Serial or comports")
    return factory, inventory


def _identity_from_inventory(
    inventory: Callable[[], Iterable[Any]],
    endpoint: PinnedNativeT102EndpointV1,
) -> PinnedNativeT102EndpointV1:
    """Resolve only the pinned COM name and require its exact USB identity."""

    try:
        records = tuple(
            item for item in inventory()
            if isinstance(getattr(item, "device", None), str)
            and item.device.upper() == endpoint.port_name
        )
    except Exception as exc:
        raise WindowsNativeT102SerialTransportError(
            "exact endpoint identity inventory failed") from exc
    if len(records) != 1:
        raise WindowsNativeT102SerialTransportError(
            "pinned COM endpoint must resolve to exactly one inventory record")
    record = records[0]
    vid = getattr(record, "vid", None)
    pid = getattr(record, "pid", None)
    serial_number = getattr(record, "serial_number", None)
    if isinstance(vid, bool) or not isinstance(vid, int) \
            or isinstance(pid, bool) or not isinstance(pid, int) \
            or not 0 <= vid <= 0xFFFF or not 0 <= pid <= 0xFFFF \
            or not isinstance(serial_number, str):
        raise WindowsNativeT102SerialTransportError(
            "pinned endpoint inventory lacks exact USB identity")
    observed = PinnedNativeT102EndpointV1(
        port_name=endpoint.port_name,
        usb_vid=f"{vid:04X}",
        usb_pid=f"{pid:04X}",
        usb_serial_number=serial_number,
    )
    if observed.endpoint_sha256 != endpoint.endpoint_sha256:
        raise WindowsNativeT102SerialTransportError(
            "pinned endpoint identity differs from inventory")
    return observed


def _validate_t102(payload: bytes) -> None:
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= 512:
        raise WindowsNativeT102SerialTransportError(
            "T=102 payload must be bounded bytes")
    try:
        message = decode_line(payload)
        if tuple(message) != ("T", *JOINT_FIELDS, "spd", "acc") \
                or message.get("T") != 102:
            raise ValueError("unexpected T=102 fields")
        rebuilt = all_joint_command(
            [message[name] for name in JOINT_FIELDS],
            speed=message["spd"], acceleration=message["acc"],
        )
        if rebuilt != message or encode_line(rebuilt) != payload:
            raise ValueError("noncanonical T=102 payload")
    except Exception as exc:
        raise WindowsNativeT102SerialTransportError(
            "payload is not the exact canonical T=102 command") from exc


def _read_bounded_line(connection: Any) -> bytes:
    try:
        line = connection.readline(MAX_CAPTURE_LINE_BYTES + 1)
    except Exception as exc:
        raise WindowsNativeT102SerialTransportError(
            "bounded controller read failed") from exc
    if not isinstance(line, bytes) or not line:
        raise WindowsNativeT102SerialTransportError(
            "bounded controller read timed out")
    if len(line) > MAX_CAPTURE_LINE_BYTES or not line.endswith(b"\n"):
        raise WindowsNativeT102SerialTransportError(
            "controller response is overlong or truncated")
    return line


class WindowsNativeT102SerialTransportV1(NativeT102ProductionTransportV1):
    """Exactly one Windows COM lifecycle with no retry or fallback path."""

    def __init__(
        self, *, read_timeout_s: float = 1.0, write_timeout_s: float = 1.0,
        serial_factory: Callable[[], Any] | None = None,
        port_inventory: Callable[[], Iterable[Any]] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._read_timeout_s = _positive_timeout(
            read_timeout_s, "read_timeout_s")
        self._write_timeout_s = _positive_timeout(
            write_timeout_s, "write_timeout_s")
        if serial_factory is not None and not callable(serial_factory):
            raise TypeError("serial_factory must be callable")
        if port_inventory is not None and not callable(port_inventory):
            raise TypeError("port_inventory must be callable")
        if not callable(monotonic_ns):
            raise TypeError("monotonic_ns must be callable")
        if (serial_factory is None) != (port_inventory is None):
            raise WindowsNativeT102SerialTransportError(
                "serial_factory and port_inventory must be supplied together")
        self._serial_factory = serial_factory
        self._port_inventory = port_inventory
        self._monotonic_ns = monotonic_ns
        self._connection: Any = None
        self._endpoint: PinnedNativeT102EndpointV1 | None = None
        self._open_attempts = 0
        self._write_attempts = 0
        self._capture_attempts = 0
        self._close_attempts = 0
        self._full_t102_write = False
        self._lock = threading.RLock()

    @property
    def open_attempts(self) -> int:
        return self._open_attempts

    @property
    def write_attempts(self) -> int:
        return self._write_attempts

    @property
    def capture_attempts(self) -> int:
        return self._capture_attempts

    @property
    def close_attempts(self) -> int:
        return self._close_attempts

    def open_once(
        self, endpoint: PinnedNativeT102EndpointV1,
    ) -> PinnedNativeT102EndpointV1:
        with self._lock:
            if self._open_attempts:
                raise WindowsNativeT102SerialTransportError(
                    "serial endpoint cannot be reopened")
            self._open_attempts = 1
            if not isinstance(endpoint, PinnedNativeT102EndpointV1):
                raise TypeError("endpoint must be PinnedNativeT102EndpointV1")
            factory = self._serial_factory
            inventory = self._port_inventory
            if factory is None or inventory is None:
                factory, inventory = _load_default_backend()
            # Pre-open resolution forbids an unpinned or changed target.  The
            # same identity is read again after Windows grants exclusive access.
            _identity_from_inventory(inventory, endpoint)
            connection = factory()
            try:
                if bool(getattr(connection, "is_open", False)):
                    raise WindowsNativeT102SerialTransportError(
                        "serial factory must return a closed connection")
                connection.port = endpoint.port_name
                connection.baudrate = 115200
                connection.bytesize = 8
                connection.parity = "N"
                connection.stopbits = 1
                connection.timeout = self._read_timeout_s
                connection.write_timeout = self._write_timeout_s
                connection.xonxoff = False
                connection.rtscts = False
                connection.dsrdtr = False
                connection.dtr = False
                connection.rts = False
                connection.open()
                if not bool(getattr(connection, "is_open", False)):
                    raise WindowsNativeT102SerialTransportError(
                        "serial endpoint did not report open")
                observed = _identity_from_inventory(inventory, endpoint)
                require_quiescent_receive_buffer(connection)
            except Exception:
                try:
                    connection.close()
                except Exception:
                    pass
                raise
            self._connection = connection
            self._endpoint = observed
            return observed

    def _opened_connection(self) -> Any:
        connection = self._connection
        if connection is None or not bool(getattr(connection, "is_open", False)):
            raise WindowsNativeT102SerialTransportError(
                "serial endpoint is not open")
        return connection

    @staticmethod
    def _write_exactly_once(connection: Any, payload: bytes) -> int:
        try:
            count = connection.write(payload)
        except Exception as exc:
            raise WindowsNativeT102SerialTransportError(
                "bounded serial write failed") from exc
        if isinstance(count, bool) or not isinstance(count, int):
            raise WindowsNativeT102SerialTransportError(
                "serial backend returned an invalid write count")
        return count

    def write_once(self, payload: bytes) -> int:
        with self._lock:
            if self._write_attempts:
                raise WindowsNativeT102SerialTransportError(
                    "T=102 command cannot be resent")
            self._write_attempts = 1
            _validate_t102(payload)
            connection = self._opened_connection()
            require_quiescent_receive_buffer(connection)
            count = self._write_exactly_once(connection, payload)
            self._full_t102_write = count == len(payload)
            return count

    def capture_once(self) -> NativeT102ControllerCaptureV1:
        with self._lock:
            if self._capture_attempts:
                raise WindowsNativeT102SerialTransportError(
                    "controller evidence cannot be recaptured")
            self._capture_attempts = 1
            if not self._full_t102_write:
                raise WindowsNativeT102SerialTransportError(
                    "capture requires one complete T=102 write")
            connection = self._opened_connection()
            acknowledgment = _read_bounded_line(connection)
            # Decode here to reject banners and malformed/non-T=1021 lines at
            # the native edge.  Exact ordinal/status validation remains bound
            # to the RuntimeCommandFrame in ARM-053.
            try:
                if decode_line(acknowledgment).get("T") != 1021:
                    raise ValueError("wrong acknowledgment type")
            except Exception as exc:
                raise WindowsNativeT102SerialTransportError(
                    "controller did not return a bounded T=1021 acknowledgment") from exc

            request = encode_line(feedback_request())
            samples: list[NativeT102FeedbackSampleV1] = []
            for _ in range(FEEDBACK_SAMPLE_COUNT):
                require_quiescent_receive_buffer(connection)
                count = self._write_exactly_once(connection, request)
                if count != len(request):
                    raise WindowsNativeT102SerialTransportError(
                        "T=105 feedback request write is uncertain")
                response = _read_bounded_line(connection)
                validate_feedback_response_line(
                    response, max_line_bytes=MAX_CAPTURE_LINE_BYTES)
                captured_ns = self._monotonic_ns()
                if isinstance(captured_ns, bool) or not isinstance(captured_ns, int) \
                        or captured_ns <= 0:
                    raise WindowsNativeT102SerialTransportError(
                        "monotonic capture time is invalid")
                samples.append(NativeT102FeedbackSampleV1(
                    captured_monotonic_ns=captured_ns,
                    response_bytes=response,
                ))
            return NativeT102ControllerCaptureV1(
                acknowledgment_bytes=acknowledgment,
                feedback_samples=tuple(samples),
            )

    def close_once(self) -> None:
        with self._lock:
            if self._close_attempts:
                return
            self._close_attempts = 1
            connection = self._connection
            self._connection = None
            self._endpoint = None
            if connection is not None:
                connection.close()


__all__ = [
    "FEEDBACK_SAMPLE_COUNT", "MAX_CAPTURE_LINE_BYTES",
    "WindowsNativeT102SerialTransportError",
    "WindowsNativeT102SerialTransportV1",
]
