from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import rocell.application.physical_device_inventory as inventory_module
from rocell.application.physical_device_inventory import (
    MAX_COMMAND_STDOUT_BYTES,
    MAX_DEVICE_CANDIDATES,
    WINDOWS_CAMERA_PNP_ARGV,
    ArgvCommandResult,
    DeviceInventoryBatch,
    InventoryDeviceClass,
    InventorySource,
    NormalizedDeviceCandidate,
    PhysicalDeviceInventoryError,
    RawSerialPortObservation,
    SubprocessArgvCommandRunner,
    compose_physical_device_inventory_report,
    inventory_linux_video_cameras_from_sysfs,
    inventory_serial_ports_from_provider,
    inventory_serial_ports_with_pyserial,
    inventory_windows_pnp_cameras,
)


def _windows_record(
    *,
    name: str = "Arducam B0477",
    instance_id: str | None = "USB\\VID_52CB&PID_0477\\CAMERA-001",
    serial_number: str | None = "CAMERA-001",
    container_id: str | None = "{11111111-2222-3333-4444-555555555555}",
) -> dict[str, object]:
    return {
        "Status": "OK",
        "Class": "Camera",
        "FriendlyName": name,
        "InstanceId": instance_id,
        "Present": True,
        "Manufacturer": "Arducam",
        "Product": "20MP USB Camera",
        "Service": "usbvideo",
        "SerialNumber": serial_number,
        "ContainerId": container_id,
        "HardwareIds": ["USB\\VID_52CB&PID_0477&REV_0100"],
    }


class _RecordingRunner:
    def __init__(self, document: object, *, returncode: int = 0) -> None:
        self.document = document
        self.returncode = returncode
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def run(
        self, argv: tuple[str, ...], *, timeout_seconds: int
    ) -> ArgvCommandResult:
        self.calls.append((argv, timeout_seconds))
        return ArgvCommandResult(
            returncode=self.returncode,
            stdout=json.dumps(self.document).encode("utf-8"),
            stderr=b"",
        )


class _SerialEnumerator:
    def __init__(self, observations: tuple[RawSerialPortObservation, ...]) -> None:
        self.observations = observations
        self.calls = 0

    def enumerate_serial_ports(self) -> tuple[RawSerialPortObservation, ...]:
        self.calls += 1
        return self.observations


def _empty_serial_batch() -> DeviceInventoryBatch:
    return inventory_serial_ports_from_provider(_SerialEnumerator(()))


def test_windows_pnp_inventory_uses_only_fixed_argv_and_keeps_zero_authority() -> None:
    runner = _RecordingRunner([_windows_record()])

    cameras = inventory_windows_pnp_cameras(runner)
    report = compose_physical_device_inventory_report(
        platform_system="Windows",
        captured_at_unix_ns=123_456_789,
        camera_inventory=cameras,
        serial_inventory=_empty_serial_batch(),
    )

    assert runner.calls == [(WINDOWS_CAMERA_PNP_ARGV, 15)]
    assert Path(WINDOWS_CAMERA_PNP_ARGV[0]).is_absolute()
    assert Path(WINDOWS_CAMERA_PNP_ARGV[0]).name.lower() == "powershell.exe"
    assert "-NonInteractive" in WINDOWS_CAMERA_PNP_ARGV
    assert len(cameras.candidates) == 1
    candidate = cameras.candidates[0]
    assert candidate.vid == "52cb"
    assert candidate.pid == "0477"
    assert candidate.unit_serial == "CAMERA-001"
    assert candidate.ephemeral_locator is None
    assert "usb-unit:52cb:0477:CAMERA-001" in candidate.persistent_ids
    assert "CAMERA_USB3_TOPOLOGY_NOT_OBSERVED" in candidate.identity_blockers
    assert "CAMERA_NEGOTIATED_LINK_SPEED_NOT_OBSERVED" in candidate.identity_blockers
    assert report.to_dict()["authority"] == {
        "camera_opened": False,
        "serial_port_opened": False,
        "device_selected": False,
        "camera_qualified": False,
        "arm_qualified": False,
        "feedback_authorized": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_release_effect": "NONE",
    }
    assert report.report_sha256 == report.to_dict()["report_sha256"]
    assert len(report.report_sha256) == 64
    assert "INVENTORY_ONLY_NOT_DEVICE_QUALIFICATION" in report.blockers
    assert "CAMERA_SELECTION_NOT_PERFORMED_BY_DESIGN" in report.blockers


def test_windows_inventory_preserves_missing_identity_and_multiple_candidate_blocks() -> None:
    runner = _RecordingRunner(
        [
            _windows_record(
                name="Camera without serial",
                serial_number=None,
                container_id=None,
            ),
            _windows_record(
                name="Camera without instance",
                instance_id=None,
                serial_number=None,
                container_id=None,
            ),
        ]
    )
    cameras = inventory_windows_pnp_cameras(runner)
    report = compose_physical_device_inventory_report(
        platform_system="Windows",
        captured_at_unix_ns=1,
        camera_inventory=cameras,
        serial_inventory=_empty_serial_batch(),
    )

    assert len(cameras.candidates) == 2
    assert any(
        "CAMERA_UNIT_SERIAL_MISSING" in candidate.identity_blockers
        for candidate in cameras.candidates
    )
    assert any(
        "CAMERA_OS_INSTANCE_ID_MISSING" in candidate.identity_blockers
        for candidate in cameras.candidates
    )
    assert "CAMERA_CANDIDATE_SELECTION_UNRESOLVED" in report.blockers
    assert "CAMERA_IDENTITY_INCOMPLETE" in report.blockers


def test_windows_inventory_rejects_unbounded_or_malformed_provider_output() -> None:
    with pytest.raises(PhysicalDeviceInventoryError, match="stdout exceeded"):
        ArgvCommandResult(
            returncode=0,
            stdout=b"x" * (MAX_COMMAND_STDOUT_BYTES + 1),
            stderr=b"",
        )

    too_many = [_windows_record(name=f"camera-{index}") for index in range(MAX_DEVICE_CANDIDATES + 1)]
    batch = inventory_windows_pnp_cameras(_RecordingRunner(too_many))
    assert not batch.collection_complete
    assert batch.candidates == ()
    assert batch.collection_blockers == ("WINDOWS_PNP_CANDIDATE_LIMIT_EXCEEDED",)

    malformed = _windows_record()
    malformed["Unexpected"] = "field"
    with pytest.raises(PhysicalDeviceInventoryError, match="unexpected field set"):
        inventory_windows_pnp_cameras(_RecordingRunner([malformed]))


def test_windows_command_failure_is_a_blocker_and_never_retried() -> None:
    runner = _RecordingRunner([], returncode=1)
    result = inventory_windows_pnp_cameras(runner)

    assert len(runner.calls) == 1
    assert result.candidates == ()
    assert result.collection_blockers == ("WINDOWS_PNP_ENUMERATION_FAILED",)


def test_concrete_command_runner_passes_argv_with_shell_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    def fake_run(argv: object, **kwargs: object) -> object:
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"[]", stderr=b"")

    monkeypatch.setattr(inventory_module.subprocess, "run", fake_run)

    result = SubprocessArgvCommandRunner().run(
        WINDOWS_CAMERA_PNP_ARGV,
        timeout_seconds=15,
    )

    assert result.stdout == b"[]"
    assert calls[0][0] == list(WINDOWS_CAMERA_PNP_ARGV)
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["check"] is False
    assert calls[0][1]["env"]["PATH"] == str(Path(WINDOWS_CAMERA_PNP_ARGV[0]).parents[2])


def test_injected_serial_enumerator_never_opens_or_connects() -> None:
    provider = _SerialEnumerator(
        (
            RawSerialPortObservation(
                port_name="COM12",
                description="USB-SERIAL CH340",
                hwid="USB VID:PID=1A86:7523 SER=ROARM-001 LOCATION=1-4",
                vid=0x1A86,
                pid=0x7523,
                serial_number="ROARM-001",
                manufacturer="wch.cn",
                product="USB Serial",
                interface="usbser",
            ),
        )
    )

    ports = inventory_serial_ports_from_provider(provider)

    assert provider.calls == 1
    assert len(ports.candidates) == 1
    candidate = ports.candidates[0]
    assert candidate.ephemeral_locator == "COM12"
    assert "COM12" not in candidate.persistent_ids
    assert candidate.persistent_ids == ("usb-unit:1a86:7523:ROARM-001",)
    assert ports.device_ports_opened is False
    assert ports.selection_performed is False


def test_serial_missing_unit_identity_stays_blocked() -> None:
    provider = _SerialEnumerator(
        (
            RawSerialPortObservation(
                port_name="/dev/ttyUSB0",
                description="Unidentified USB serial adapter",
                hwid="USB VID:PID=1A86:7523 LOCATION=1-4",
            ),
        )
    )
    ports = inventory_serial_ports_from_provider(provider)
    candidate = ports.candidates[0]
    report = compose_physical_device_inventory_report(
        platform_system="Linux",
        captured_at_unix_ns=2,
        camera_inventory=DeviceInventoryBatch(
            device_class=InventoryDeviceClass.CAMERA,
            source=InventorySource.LINUX_SYSFS,
            candidates=(),
            collection_blockers=(),
            collection_complete=True,
        ),
        serial_inventory=ports,
    )

    assert "SERIAL_UNIT_SERIAL_MISSING" in candidate.identity_blockers
    assert "SERIAL_PERSISTENT_SELECTOR_MISSING" in candidate.identity_blockers
    assert "SERIAL_IDENTITY_INCOMPLETE" in report.blockers
    assert report.authority.serial_port_opened is False


def test_conflicting_identity_observations_are_not_silently_normalized() -> None:
    camera_record = _windows_record()
    camera_record["HardwareIds"] = [
        "USB\\VID_52CB&PID_0477",
        "USB\\VID_DEAD&PID_BEEF",
    ]
    cameras = inventory_windows_pnp_cameras(_RecordingRunner([camera_record]))
    assert cameras.candidates[0].vid is None
    assert "CAMERA_USB_IDENTITY_AMBIGUOUS" in cameras.candidates[0].identity_blockers

    ports = inventory_serial_ports_from_provider(
        _SerialEnumerator(
            (
                RawSerialPortObservation(
                    port_name="COM8",
                    hwid="USB VID:PID=303A:1001 SER=HWID-SERIAL",
                    vid=0x1234,
                    pid=0x5678,
                    serial_number="DIRECT-SERIAL",
                ),
            )
        )
    )
    blockers = ports.candidates[0].identity_blockers
    assert "SERIAL_USB_IDENTITY_AMBIGUOUS" in blockers
    assert "SERIAL_UNIT_SERIAL_AMBIGUOUS" in blockers


def test_pyserial_is_lazily_loaded_and_only_comports_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    port_info = SimpleNamespace(
        device="COM7",
        description="RoArm controller",
        hwid="USB VID:PID=303A:1001 SER=ESP32-001",
        vid=0x303A,
        pid=0x1001,
        serial_number="ESP32-001",
        location="1-2",
        manufacturer="Espressif",
        product="USB JTAG/serial debug unit",
        interface="usbser",
    )

    class _ListPortsModule:
        @staticmethod
        def comports() -> list[object]:
            calls.append("comports")
            return [port_info]

    def fake_import(name: str) -> object:
        calls.append(f"import:{name}")
        return _ListPortsModule()

    monkeypatch.setattr(inventory_module.importlib, "import_module", fake_import)

    result = inventory_serial_ports_with_pyserial()

    assert calls == ["import:serial.tools.list_ports", "comports"]
    assert result.source is InventorySource.PYSERIAL_LIST_PORTS
    assert result.candidates[0].unit_serial == "ESP32-001"
    assert result.device_ports_opened is False


def test_linux_sysfs_inventory_reads_metadata_but_never_device_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys_class_root = tmp_path / "sys" / "class" / "video4linux"
    video = sys_class_root / "video7"
    device = video / "device"
    driver = device / "driver" / "uvcvideo"
    driver.mkdir(parents=True)
    (video / "name").write_text("Arducam B0477\n", encoding="utf-8")
    (device / "idVendor").write_text("52cb\n", encoding="utf-8")
    (device / "idProduct").write_text("0477\n", encoding="utf-8")
    (device / "serial").write_text("CAMERA-LINUX-001\n", encoding="utf-8")
    (device / "manufacturer").write_text("Arducam\n", encoding="utf-8")
    (device / "product").write_text("20MP USB Camera\n", encoding="utf-8")
    dev_root = tmp_path / "dev"
    dev_root.mkdir()

    original_open = Path.open

    def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == dev_root / "video7":
            raise AssertionError("inventory attempted to open a video device node")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    result = inventory_linux_video_cameras_from_sysfs(
        sys_class_root=sys_class_root,
        dev_root=dev_root,
        by_id_root=None,
    )

    assert result.collection_complete
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.ephemeral_locator == str(dev_root / "video7")
    assert candidate.vid == "52cb"
    assert candidate.pid == "0477"
    assert candidate.unit_serial == "CAMERA-LINUX-001"
    assert candidate.device_class is InventoryDeviceClass.CAMERA
    assert "CAMERA_USB3_TOPOLOGY_NOT_OBSERVED" in candidate.identity_blockers


def test_bare_ephemeral_locators_cannot_be_persistent_identifiers() -> None:
    with pytest.raises(PhysicalDeviceInventoryError, match="not persistent"):
        NormalizedDeviceCandidate(
            device_class=InventoryDeviceClass.SERIAL,
            source=InventorySource.INJECTED_SERIAL_ENUMERATOR,
            display_name="unsafe selector",
            vid=None,
            pid=None,
            unit_serial=None,
            os_instance_id=None,
            persistent_ids=("COM5",),
            ephemeral_locator="COM5",
            manufacturer=None,
            product=None,
            driver_service=None,
            identity_blockers=("SERIAL_UNIT_SERIAL_MISSING",),
        )


def test_duplicate_persistent_identity_is_explicitly_ambiguous() -> None:
    observations = tuple(
        RawSerialPortObservation(
            port_name=f"COM{index}",
            description=f"duplicate-{index}",
            hwid=f"USB VID:PID=303A:1001 SER=ESP32-SAME LOCATION=1-{index}",
            serial_number="ESP32-SAME",
            vid=0x303A,
            pid=0x1001,
        )
        for index in (4, 5)
    )
    ports = inventory_serial_ports_from_provider(_SerialEnumerator(observations))
    report = compose_physical_device_inventory_report(
        platform_system="Windows",
        captured_at_unix_ns=3,
        camera_inventory=DeviceInventoryBatch(
            device_class=InventoryDeviceClass.CAMERA,
            source=InventorySource.WINDOWS_PNP,
            candidates=(),
            collection_blockers=(),
            collection_complete=True,
        ),
        serial_inventory=ports,
    )

    assert "SERIAL_PERSISTENT_ID_AMBIGUOUS" in report.blockers
    assert "SERIAL_CANDIDATE_SELECTION_UNRESOLVED" in report.blockers


def test_zero_authority_fields_cannot_be_tampered() -> None:
    cameras = inventory_windows_pnp_cameras(_RecordingRunner([_windows_record()]))
    report = compose_physical_device_inventory_report(
        platform_system="Windows",
        captured_at_unix_ns=4,
        camera_inventory=cameras,
        serial_inventory=_empty_serial_batch(),
    )

    with pytest.raises(PhysicalDeviceInventoryError, match="zero-authority"):
        replace(report.authority, camera_qualified=True)
