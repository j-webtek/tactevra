import ctypes
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from rocell.application.physical_connection_contracts import (
    EvidenceOrigin,
    RoArmUsbSerialIdentity,
    UsbDriverIdentity,
)
from rocell.calibration.position_vector_campaign import (
    CALIBRATED_FEEDBACK_REQUEST_CONTRACT,
)
from rocell.providers.windows.arm_feedback_worker import ReviewedControllerBinding
from rocell.providers.windows.calibrated_position_vector_binding import (
    CalibratedPositionVectorBinding,
)
from rocell.providers.windows.calibrated_position_vector_native_composition import (
    EXPORT_SCHEMA,
    build_calibrated_position_vector_connection,
    export_position_vector_serial_attempt,
)
from rocell.providers.windows.calibrated_position_vector_serial_adapter import (
    execute_position_vector_serial_exchange,
)
from rocell.providers.windows.calibrated_position_vector_serial_api import (
    WindowsCalibratedPositionVectorSerialApi,
)


FIRMWARE_SHA = "3" * 64
RUNTIME_SHA = "6" * 64
RESPONSE = (
    b'{"T":1051,"p":[2050,2147,1958,2550,2227,2041,2042],'
    b'"pose":"KEYBOARD_FORWARD_CAL_1","motion_active":false,'
    b'"trajectory_progress_permille":1000}\n'
)


def identity(port="COM404"):
    return RoArmUsbSerialIdentity(
        "10c4",
        "ea60",
        "52E4E1E8337FEF119E92181CEDD322A4",
        "USB\\VID_10C4&PID_EA60\\52E4E1E8337FEF119E92181CEDD322A4",
        "usb-unit:10c4:ea60:52E4E1E8337FEF119E92181CEDD322A4",
        port,
        UsbDriverIdentity("Silicon Labs", "silabser", "11.3.0", "silabser.inf"),
    )


def request(attempt_id="calibrated-native-01"):
    return {
        "schema": "rocell.position_vector_calibration_qualified_feedback_request.v1",
        "attempt_id": attempt_id,
        "runtime_session_id": "calibrated-runtime-01",
        "request_execution_approval_receipt_sha256": "a" * 64,
        "execution_prerequisites_sha256": "b" * 64,
        "request_contract": dict(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
    }


def reviewed(value=None):
    return ReviewedControllerBinding(
        identity() if value is None else value,
        "1" * 64,
        "2" * 64,
        FIRMWARE_SHA,
        "4" * 64,
        "5" * 64,
        EvidenceOrigin.PHYSICAL_OBSERVATION,
    )


def binding(**changes):
    values = {
        "reviewed_controller": reviewed(),
        "fresh_identity": identity(),
        "request": request(),
        "controller_binding": {
            "vid": "10c4",
            "pid": "ea60",
            "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
            "firmware_sha256": FIRMWARE_SHA,
        },
        "installed_firmware_sha256": FIRMWARE_SHA,
        "runtime_sha256": RUNTIME_SHA,
        "expires_monotonic_ns": 2_000_000_000,
    }
    values.update(changes)
    return CalibratedPositionVectorBinding(**values)


@pytest.fixture(autouse=True)
def forbid_native_loading(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("binding and construction must not load a native DLL")

    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)
    monkeypatch.setattr(ctypes, "CDLL", forbidden)


def test_binding_and_owned_connection_are_inert_and_exact():
    value = binding()
    owner = build_calibrated_position_vector_connection(
        value,
        current_runtime_sha256=RUNTIME_SHA,
        owned_process_id=os.getpid(),
        clock_ns=lambda: 1_000_000_000,
    )

    report = owner.status()
    assert report["phase"] == "CLOSED_UNOPENED"
    assert report["composition"] == "WINDOWS_CALIBRATED_POSITION_VECTOR_ENGINEERING"
    assert report["physical_hold"] == "CALIBRATED_FEEDBACK_REQUEST_ONLY"
    assert report["hardware_accessed_by_status"] is False
    assert report["cleanup_confirmed"] is True
    assert report["binding_sha256"] == value.binding_sha256


@pytest.mark.parametrize(
    "changes,match",
    [
        (
            {"fresh_identity": identity("COM405")},
            "fresh controller identity",
        ),
        (
            {
                "controller_binding": {
                    "vid": "ffff",
                    "pid": "ea60",
                    "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
                    "firmware_sha256": FIRMWARE_SHA,
                }
            },
            "reviewed controller",
        ),
        (
            {
                "controller_binding": {
                    "vid": "10c4",
                    "pid": "ea60",
                    "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
                    "firmware_sha256": "9" * 64,
                }
            },
            "installed firmware",
        ),
        ({"installed_firmware_sha256": "9" * 64}, "installed firmware"),
        ({"request": {**request(), "request_contract": {}}}, "contract"),
    ],
)
def test_binding_rejects_controller_request_or_firmware_drift(changes, match):
    with pytest.raises(ValueError, match=match):
        binding(**changes)


@pytest.mark.parametrize(
    "runtime,pid,now,match",
    [
        ("7" * 64, os.getpid(), 1_000_000_000, "runtime changed"),
        (RUNTIME_SHA, os.getpid() + 1, 1_000_000_000, "process identity"),
        (RUNTIME_SHA, os.getpid(), 2_000_000_000, "expired"),
    ],
)
def test_api_admission_rejects_runtime_pid_and_deadline_drift(runtime, pid, now, match):
    with pytest.raises(ValueError, match=match):
        WindowsCalibratedPositionVectorSerialApi.from_owned_process(
            binding(),
            current_runtime_sha256=runtime,
            owned_process_id=pid,
            clock_ns=lambda: now,
        )


class Clock:
    def __init__(self):
        self.wall = datetime(2026, 10, 25, 20, 30, tzinfo=timezone.utc)
        self.mono = 10.0

    def now(self):
        value = self.wall
        self.wall += timedelta(milliseconds=1)
        return value

    def monotonic(self):
        return self.mono

    def sleep(self, seconds):
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)


class MemoryTransport:
    def __init__(self):
        self.response = RESPONSE
        self.written = False
        self.closed = False

    def open(self):
        return None

    @property
    def in_waiting(self):
        return len(self.response) if self.written else 0

    def read(self, size, *, timeout_ms):
        del timeout_ms
        result, self.response = self.response[:size], self.response[size:]
        return result

    def write(self, payload):
        assert payload == b'{"T":105}\n'
        self.written = True
        return len(payload)

    def close(self):
        self.closed = True

    def status(self):
        return {"confirmed_write_bytes": 10, "cleanup_confirmed": self.closed}


def test_verified_journal_export_is_byte_exact_and_immutable(tmp_path):
    journal_root = tmp_path / "journals"
    export_root = tmp_path / "exports"
    journal_root.mkdir()
    export_root.mkdir()
    clock = Clock()
    execute_position_vector_serial_exchange(
        request(),
        journal_root=journal_root,
        transport_factory=MemoryTransport,
        clock=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    source = journal_root / "position-vector-feedback-calibrated-native-01"

    exported = export_position_vector_serial_attempt(source, export_root=export_root)

    assert exported["schema"] == EXPORT_SCHEMA
    assert exported["recovery_disposition"] == "TERMINAL_NO_REPLAY"
    assert exported["automatic_retry_allowed"] is False
    target = export_root / (source.name + "-export")
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest == {key: value for key, value in exported.items() if key != "export_directory"}
    for entry in manifest["files"]:
        assert (target / entry["name"]).read_bytes() == (source / entry["name"]).read_bytes()
    with pytest.raises(FileExistsError):
        export_position_vector_serial_attempt(source, export_root=export_root)


def test_export_rejects_tampered_journal_before_creating_directory(tmp_path):
    journal_root = tmp_path / "journals"
    export_root = tmp_path / "exports"
    journal_root.mkdir()
    export_root.mkdir()
    clock = Clock()
    execute_position_vector_serial_exchange(
        request(), journal_root=journal_root, transport_factory=MemoryTransport,
        clock=clock.now, monotonic=clock.monotonic, sleep=clock.sleep,
    )
    source = journal_root / "position-vector-feedback-calibrated-native-01"
    result = json.loads((source / "result.json").read_text())
    result["event_count"] += 1
    (source / "result.json").write_text(json.dumps(result) + "\n")

    with pytest.raises(ValueError, match="terminal result"):
        export_position_vector_serial_attempt(source, export_root=export_root)
    assert list(export_root.iterdir()) == []
