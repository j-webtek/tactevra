from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from rocell.application.physical_connection_contracts import (
    EvidenceOrigin,
    RoArmUsbSerialIdentity,
    UsbDriverIdentity,
)
from rocell.calibration.position_vector_campaign import CALIBRATED_FEEDBACK_REQUEST_CONTRACT
from rocell.providers.windows.arm_feedback_worker import ReviewedControllerBinding
from rocell.providers.windows import calibrated_position_vector_native_package as package
from rocell.providers.windows.calibrated_position_vector_native_registration import (
    validate_registration,
)
from rocell.providers.windows.calibrated_position_vector_native_composition import (
    export_position_vector_serial_attempt,
)
from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
    decode_request,
    encode_result,
    validate_result,
    verify_exported_journal,
)
from rocell.providers.windows.calibrated_position_vector_owned_supervisor import (
    stage_calibrated_position_vector_worker,
)
from rocell.providers.windows.calibrated_position_vector_serial_adapter import (
    PositionVectorSerialAdapterError,
    execute_position_vector_serial_exchange,
)
from rocell.providers.windows.owned_worker_process import OwnedWindowsWorker


FIRMWARE_SHA = "3" * 64
SOURCE_SHA = "7" * 64
RESPONSE = (
    b'{"T":1051,"p":[2050,2147,1958,2550,2227,2041,2042],'
    b'"pose":"KEYBOARD_FORWARD_CAL_1","motion_active":false,'
    b'"trajectory_progress_permille":1000}\n'
)


def identity() -> RoArmUsbSerialIdentity:
    return RoArmUsbSerialIdentity(
        "10c4", "ea60", "52E4E1E8337FEF119E92181CEDD322A4",
        "USB\\VID_10C4&PID_EA60\\52E4E1E8337FEF119E92181CEDD322A4",
        "usb-unit:10c4:ea60:52E4E1E8337FEF119E92181CEDD322A4", "COM404",
        UsbDriverIdentity("Silicon Labs", "silabser", "11.3.0", "silabser.inf"),
    )


def reviewed() -> ReviewedControllerBinding:
    return ReviewedControllerBinding(
        identity(), "1" * 64, "2" * 64, FIRMWARE_SHA, "4" * 64, "5" * 64,
        EvidenceOrigin.PHYSICAL_OBSERVATION,
    )


def request() -> dict:
    return {
        "schema": "rocell.position_vector_calibration_qualified_feedback_request.v1",
        "attempt_id": "calibrated-owned-01",
        "runtime_session_id": "calibrated-runtime-01",
        "request_execution_approval_receipt_sha256": "a" * 64,
        "execution_prerequisites_sha256": "b" * 64,
        "request_contract": dict(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
    }


def staged(tmp_path, *, expires=2_000_000_000):
    return stage_calibrated_position_vector_worker(
        tmp_path.resolve(),
        reviewed_controller=reviewed(),
        fresh_identity=identity(),
        request=request(),
        controller_binding={
            "vid": "10c4", "pid": "ea60",
            "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
            "firmware_sha256": FIRMWARE_SHA,
        },
        installed_firmware_sha256=FIRMWARE_SHA,
        source_sha256=SOURCE_SHA,
        expires_monotonic_ns=expires,
    )


def test_staging_is_inert_and_registration_and_wire_are_exact(tmp_path):
    value = staged(tmp_path)
    payload = validate_registration(value.registration, value.request)
    wire = decode_request(value.wire)

    assert payload["binding"]["binding_sha256"] == value.binding.binding_sha256
    assert wire["request_sha256"] == hashlib.sha256(
        json.dumps(
            {key: item for key, item in wire.items() if key != "request_sha256"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()
    assert list((value.working_directory / "journals").iterdir()) == []
    assert list((value.working_directory / "exports").iterdir()) == []


@pytest.mark.parametrize("change", ["command", "budget", "archive"])
def test_registration_drift_fails_before_dispatch(tmp_path, change):
    value = staged(tmp_path)
    registration = value.registration
    if change == "command":
        registration = replace(registration, argv=registration.argv[:-1] + ("other",))
    elif change == "budget":
        registration = replace(registration, budget=replace(registration.budget, process_count=2))
    else:
        registration = replace(
            registration,
            package_files=(registration.package_files[0], replace(registration.package_files[1], sha256="8" * 64)),
        )
    with pytest.raises(ValueError):
        validate_registration(registration, value.request)


def test_owned_supervisor_recognizes_protocol_and_holds_short_lifetime_before_process(tmp_path):
    value = staged(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("insufficient lifetime must fail before authority or process creation")

    result = OwnedWindowsWorker(
        value.registration,
        authorizer=forbidden,
        _backend_factory=forbidden,
    ).run(
        value.request,
        cancellation=threading.Event(),
        deadline_ns=value.request.expires_at_ns,
    )
    assert result.primary_error == "LIFETIME_BUDGET_DOES_NOT_FIT"
    assert result.process_created is False


def test_source_archive_is_deterministic_and_import_audit_is_hardware_incapable(tmp_path):
    raw = package.expected_archive()
    assert raw == package.expected_archive()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set(archive.namelist())
    assert "rocell/providers/windows/calibrated_position_vector_owned_protocol.py" in names
    assert "rocell/providers/windows/calibrated_position_vector_serial_api.py" in names
    path = package.prepare(tmp_path)
    result = subprocess.run(
        [
            str(Path(getattr(sys, "_base_executable", sys.executable))),
            "-I", "-S", str(package.CHILD), str(path),
            hashlib.sha256(path.read_bytes()).hexdigest(), "check-imports",
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    report = json.loads(result.stdout)
    assert report["status"] == "IMPORTS_OK_NOT_HARDWARE_TESTED"
    assert report["connected"] is report["motion_authorized"] is False


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


def test_parent_reconstructs_result_and_verifies_byte_exact_export(tmp_path):
    value = staged(tmp_path)
    clock = Clock()
    evidence = execute_position_vector_serial_exchange(
        value.binding.request,
        journal_root=value.working_directory / "journals",
        transport_factory=MemoryTransport,
        clock=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    attempt = value.working_directory / "journals" / "position-vector-feedback-calibrated-owned-01"
    exported = export_position_vector_serial_attempt(
        attempt, export_root=value.working_directory / "exports"
    )
    wire = decode_request(value.wire)
    child = {
        "schema": "rocell.calibrated_position_vector_native_child_result.v1",
        "status": "SUCCEEDED",
        "error": None,
        "binding_sha256": value.binding.binding_sha256,
        "exchange_evidence": evidence,
        "journal_export": exported,
        "physical_authority": False,
        "motion_authorized": False,
        "automatic_retry_allowed": False,
        "connected": False,
    }
    result = json.loads(encode_result(child, wire=wire))

    assert validate_result(result, wire=wire) == result
    assert verify_exported_journal(
        result, wire=wire, working_directory=value.working_directory
    ) == result
    (Path(exported["export_directory"]) / "events.jsonl").write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="manifest"):
        verify_exported_journal(result, wire=wire, working_directory=value.working_directory)


def test_owned_process_supervision_accepts_only_associated_export(tmp_path):
    expires = time.monotonic_ns() + 30_000_000_000
    value = staged(tmp_path, expires=expires)
    clock = Clock()
    evidence = execute_position_vector_serial_exchange(
        value.binding.request,
        journal_root=value.working_directory / "journals",
        transport_factory=MemoryTransport,
        clock=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    attempt = value.working_directory / "journals" / "position-vector-feedback-calibrated-owned-01"
    exported = export_position_vector_serial_attempt(
        attempt, export_root=value.working_directory / "exports"
    )
    wire = decode_request(value.wire)
    child = {
        "schema": "rocell.calibrated_position_vector_native_child_result.v1",
        "status": "SUCCEEDED",
        "error": None,
        "binding_sha256": value.binding.binding_sha256,
        "exchange_evidence": evidence,
        "journal_export": exported,
        "physical_authority": False,
        "motion_authorized": False,
        "automatic_retry_allowed": False,
        "connected": False,
    }
    output = encode_result(child, wire=wire)

    class Backend:
        created = False
        pid = 4242
        resumed = False
        tree_exited = False
        returncode = 0
        written = 0
        peak_handles = 3
        peak_processes = 1
        stdout = output
        stderr = b""

        def pin(self, registration):
            assert registration == value.registration

        def start(self, registration, request_wire, *, check):
            assert registration == value.registration
            assert request_wire == value.wire
            check()
            self.created = self.resumed = True
            self.written = len(request_wire)

        def poll(self, budget):
            assert budget == value.registration.budget
            self.tree_exited = True
            return True

        def cleanup(self, deadline):
            assert deadline > 0
            return ()

    authority_calls = []

    def authorize(registration, outer, digest):
        authority_calls.append((registration, outer, digest))

    result = OwnedWindowsWorker(
        value.registration,
        authorizer=authorize,
        _backend_factory=Backend,
    ).run(
        value.request,
        cancellation=threading.Event(),
        deadline_ns=expires,
    )
    assert result.status == "SUCCEEDED", result.to_dict()
    assert result.parsed_result == json.loads(output)
    assert result.process_created and result.tree_exit_confirmed
    assert len(authority_calls) == 1


def test_terminal_failure_is_exported_and_associated_without_retry(tmp_path):
    value = staged(tmp_path)
    clock = Clock()

    class ShortWriteTransport(MemoryTransport):
        def write(self, payload):
            self.written = True
            return len(payload) - 1

    with pytest.raises(PositionVectorSerialAdapterError) as raised:
        execute_position_vector_serial_exchange(
            value.binding.request,
            journal_root=value.working_directory / "journals",
            transport_factory=ShortWriteTransport,
            clock=clock.now,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
    exported = export_position_vector_serial_attempt(
        raised.value.journal_directory,
        export_root=value.working_directory / "exports",
    )
    wire = decode_request(value.wire)
    child = {
        "schema": "rocell.calibrated_position_vector_native_child_result.v1",
        "status": "FAILED_NO_RETRY",
        "error": raised.value.code,
        "binding_sha256": value.binding.binding_sha256,
        "exchange_evidence": None,
        "journal_export": exported,
        "physical_authority": False,
        "motion_authorized": False,
        "automatic_retry_allowed": False,
        "connected": False,
    }
    result = json.loads(encode_result(child, wire=wire))
    assert verify_exported_journal(
        result, wire=wire, working_directory=value.working_directory
    ) == result
    assert result["child_result"]["error"] == "SHORT_WRITE_NO_RETRY"
