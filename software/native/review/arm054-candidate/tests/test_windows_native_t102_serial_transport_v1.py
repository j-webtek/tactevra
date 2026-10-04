"""Offline qualification of the ARM-054 Windows serial adapter."""

from __future__ import annotations

from dataclasses import dataclass
import sys

import pytest

from rocell.application.native_t102_production_transport_v1 import (
    PinnedNativeT102EndpointV1,
)
from rocell.arm.all_joint_command import all_joint_command
from rocell.arm.protocol import encode_line
from rocell.providers.windows.native_t102_serial_transport_v1 import (
    WindowsNativeT102SerialTransportError,
    WindowsNativeT102SerialTransportV1,
)


@dataclass
class PortInfo:
    device: str = "COM7"
    vid: int = 0x10C4
    pid: int = 0xEA60
    serial_number: str = "ARM054UNIT001"


class FakeSerial:
    def __init__(self, lines=(), *, short_write_at=None, startup_bytes=0):
        self.is_open = False
        self.lines = list(lines)
        self.short_write_at = short_write_at
        self.in_waiting = startup_bytes
        self.writes = []
        self.opens = 0
        self.closes = 0

    def open(self):
        self.opens += 1
        self.is_open = True

    def close(self):
        self.closes += 1
        self.is_open = False

    def write(self, payload):
        self.writes.append(payload)
        if self.short_write_at == len(self.writes):
            return len(payload) - 1
        return len(payload)

    def readline(self, maximum):
        if not self.lines:
            return b""
        return self.lines.pop(0)[:maximum]


def endpoint(**changes):
    values = dict(
        port_name="COM7", usb_vid="10C4", usb_pid="EA60",
        usb_serial_number="ARM054UNIT001",
    )
    values.update(changes)
    return PinnedNativeT102EndpointV1(**values)


def command():
    return encode_line(all_joint_command(
        [.1, .2, .3, .4, .5, .6], speed=20, acceleration=1))


def lines(ordinal=1):
    feedback = encode_line({
        "T": 1051, "b": .1, "s": .2, "e": .3,
        "t": .4, "r": .5, "g": .6,
    })
    return [
        encode_line({"T": 1021, "status": "ACCEPTED_ONCE", "ordinal": ordinal}),
        feedback, feedback,
    ]


def adapter(serial, inventory=lambda: [PortInfo()]):
    ticks = iter((1_150, 1_160))
    return WindowsNativeT102SerialTransportV1(
        serial_factory=lambda: serial,
        port_inventory=inventory,
        monotonic_ns=lambda: next(ticks),
    )


def test_import_and_construction_do_not_load_pyserial_or_open_hardware():
    before = set(sys.modules)
    transport = WindowsNativeT102SerialTransportV1(
        serial_factory=lambda: (_ for _ in ()).throw(AssertionError("factory")),
        port_inventory=lambda: (_ for _ in ()).throw(AssertionError("inventory")),
    )
    assert transport.open_attempts == 0
    assert set(sys.modules) - before != {"serial"}


def test_exact_one_shot_lifecycle_captures_ack_and_two_feedback_samples():
    serial = FakeSerial(lines())
    transport = adapter(serial)
    observed = transport.open_once(endpoint())
    payload = command()
    assert observed == endpoint()
    assert serial.port == "COM7"
    assert (serial.baudrate, serial.bytesize, serial.parity, serial.stopbits) == (
        115200, 8, "N", 1)
    assert (serial.xonxoff, serial.rtscts, serial.dsrdtr) == (False, False, False)
    assert transport.write_once(payload) == len(payload)
    capture = transport.capture_once()
    transport.close_once()
    assert capture.acknowledgment_bytes == lines()[0]
    assert tuple(item.captured_monotonic_ns for item in capture.feedback_samples) \
        == (1_150, 1_160)
    assert serial.writes == [payload, b'{"T":105}\n', b'{"T":105}\n']
    assert (transport.open_attempts, transport.write_attempts,
            transport.capture_attempts, transport.close_attempts) == (1, 1, 1, 1)
    assert serial.opens == serial.closes == 1


@pytest.mark.parametrize("record", [
    PortInfo(device="COM8"),
    PortInfo(vid=0xFFFF),
    PortInfo(pid=0xFFFF),
    PortInfo(serial_number="OTHER"),
])
def test_endpoint_identity_mismatch_never_opens(record):
    serial = FakeSerial(lines())
    transport = adapter(serial, inventory=lambda: [record])
    with pytest.raises(WindowsNativeT102SerialTransportError):
        transport.open_once(endpoint())
    assert serial.opens == 0
    assert transport.write_attempts == 0


def test_identity_is_rechecked_after_exclusive_open():
    serial = FakeSerial(lines())
    inventories = iter(([PortInfo()], [PortInfo(serial_number="CHANGED")]))
    transport = adapter(serial, inventory=lambda: next(inventories))
    with pytest.raises(WindowsNativeT102SerialTransportError):
        transport.open_once(endpoint())
    assert serial.opens == 1
    assert serial.closes == 1
    assert transport.write_attempts == 0


def test_stale_startup_bytes_fail_without_purge_or_write():
    serial = FakeSerial(lines(), startup_bytes=4)
    transport = adapter(serial)
    with pytest.raises(Exception, match="receive buffer"):
        transport.open_once(endpoint())
    assert serial.closes == 1
    assert serial.writes == []


def test_no_reopen_resend_recapture_or_fallback():
    serial = FakeSerial(lines())
    transport = adapter(serial)
    transport.open_once(endpoint())
    with pytest.raises(WindowsNativeT102SerialTransportError, match="reopened"):
        transport.open_once(endpoint(port_name="COM8"))
    payload = command()
    transport.write_once(payload)
    with pytest.raises(WindowsNativeT102SerialTransportError, match="resent"):
        transport.write_once(payload)
    transport.capture_once()
    with pytest.raises(WindowsNativeT102SerialTransportError, match="recaptured"):
        transport.capture_once()
    transport.close_once()
    transport.close_once()
    assert serial.opens == serial.closes == 1


def test_noncanonical_or_non_t102_payload_is_never_written():
    serial = FakeSerial(lines())
    transport = adapter(serial)
    transport.open_once(endpoint())
    with pytest.raises(WindowsNativeT102SerialTransportError, match="canonical"):
        transport.write_once(b'{"T":105}\n')
    assert serial.writes == []


def test_short_t102_write_prevents_capture_and_retry():
    serial = FakeSerial(lines(), short_write_at=1)
    transport = adapter(serial)
    transport.open_once(endpoint())
    payload = command()
    assert transport.write_once(payload) == len(payload) - 1
    with pytest.raises(WindowsNativeT102SerialTransportError, match="complete"):
        transport.capture_once()
    assert serial.writes == [payload]


@pytest.mark.parametrize("bad_line", [
    b"ets reset banner\n",
    b'{"T":1051}\n',
    b'{"T":1021}',
    b"x" * 2049,
])
def test_bad_ack_is_terminal_capture_failure(bad_line):
    serial = FakeSerial([bad_line])
    transport = adapter(serial)
    transport.open_once(endpoint())
    transport.write_once(command())
    with pytest.raises(WindowsNativeT102SerialTransportError):
        transport.capture_once()
    assert len(serial.writes) == 1


def test_short_feedback_request_fails_without_second_request():
    serial = FakeSerial(lines(), short_write_at=2)
    transport = adapter(serial)
    transport.open_once(endpoint())
    transport.write_once(command())
    with pytest.raises(WindowsNativeT102SerialTransportError, match="uncertain"):
        transport.capture_once()
    assert len(serial.writes) == 2
