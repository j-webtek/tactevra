"""Read-only host inventory for cameras and USB serial devices.

This module is the deliberately weak first physical boundary in onboarding.  It
may inspect operating-system metadata, but it cannot open a camera, open a
serial port, select a numeric camera index, connect to a controller, or qualify
either device.  Inventory output is therefore useful for discovering stable
identities while remaining incapable of granting capture, feedback, motion, or
contact authority.

Windows camera discovery is performed by a fixed PowerShell query supplied to
an argv-only runner.  Linux camera discovery reads ``sysfs`` and optional
``/dev/v4l/by-id`` links; it never opens a ``/dev/video*`` node.  Serial
discovery accepts an injected enumeration provider.  The only function that
imports pyserial is :func:`inventory_serial_ports_with_pyserial`, whose sole
operation is ``serial.tools.list_ports.comports()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from rocell.application.physical_connection_contracts import canonical_sha256


PHYSICAL_DEVICE_INVENTORY_SCHEMA = "rocell.physical_device_inventory.v1"
DEVICE_INVENTORY_BATCH_SCHEMA = "rocell.physical_device_inventory_batch.v1"

# Bounds apply before data is admitted into a report.  They are defensive
# parser limits, not estimates of how many devices a workcell should contain.
MAX_COMMAND_STDOUT_BYTES = 512 * 1024
MAX_COMMAND_STDERR_BYTES = 64 * 1024
MAX_DEVICE_CANDIDATES = 128
MAX_PERSISTENT_IDS_PER_CANDIDATE = 8
MAX_TEXT_BYTES = 2 * 1024
MAX_SYSFS_FILE_BYTES = 8 * 1024
COMMAND_TIMEOUT_SECONDS = 15

_HEX4_RE = re.compile(r"[0-9a-f]{4}\Z")
_BLOCKER_RE = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")
_WINDOWS_USB_RE = re.compile(
    r"(?:VID_|VID:PID=)([0-9A-Fa-f]{4})(?:&PID_|:)([0-9A-Fa-f]{4})"
)
_SERIAL_IN_HWID_RE = re.compile(r"(?:^|\s)SER=([^\s]+)", re.IGNORECASE)
_FORBIDDEN_SELECTOR_RE = re.compile(
    r"(?:\d+|camera\s*[:#]?\s*\d+|index\s*[:#]?\s*\d+|COM\d+|/dev/video\d+)\Z",
    re.IGNORECASE,
)


class PhysicalDeviceInventoryError(ValueError):
    """Inventory input or provider output violates the read-only contract."""


class InventoryDeviceClass(str, Enum):
    CAMERA = "CAMERA"
    SERIAL = "SERIAL"


class InventorySource(str, Enum):
    WINDOWS_PNP = "WINDOWS_PNP"
    LINUX_SYSFS = "LINUX_SYSFS"
    INJECTED_SERIAL_ENUMERATOR = "INJECTED_SERIAL_ENUMERATOR"
    PYSERIAL_LIST_PORTS = "PYSERIAL_LIST_PORTS"


def _bounded_text(
    value: object,
    label: str,
    *,
    required: bool = True,
    maximum_bytes: int = MAX_TEXT_BYTES,
) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise PhysicalDeviceInventoryError(f"{label} must be text")
    normalized = value.strip()
    if required and not normalized:
        raise PhysicalDeviceInventoryError(f"{label} must be non-empty text")
    if not normalized:
        return None
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise PhysicalDeviceInventoryError(
            f"{label} exceeds {maximum_bytes} UTF-8 bytes"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise PhysicalDeviceInventoryError(f"{label} contains control characters")
    return normalized


def _optional_provider_text(value: object, label: str) -> str | None:
    """Normalize optional provider text without silently coercing its type."""

    return _bounded_text(value, label, required=False)


def _normalized_hex_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise PhysicalDeviceInventoryError(f"{label} must be a USB identifier")
    if isinstance(value, int):
        if not 0 <= value <= 0xFFFF:
            raise PhysicalDeviceInventoryError(f"{label} is outside 0000..ffff")
        return f"{value:04x}"
    if not isinstance(value, str):
        raise PhysicalDeviceInventoryError(f"{label} must be text or an integer")
    normalized = value.strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    if _HEX4_RE.fullmatch(normalized) is None:
        raise PhysicalDeviceInventoryError(
            f"{label} must contain exactly four hexadecimal digits"
        )
    return normalized


def _blockers(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if any(_BLOCKER_RE.fullmatch(value) is None for value in normalized):
        raise PhysicalDeviceInventoryError("blockers contain an invalid code")
    return normalized


def _persistent_ids(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if len(normalized) > MAX_PERSISTENT_IDS_PER_CANDIDATE:
        raise PhysicalDeviceInventoryError("too many persistent identifiers")
    for index, value in enumerate(normalized):
        checked = _bounded_text(value, f"persistent_ids[{index}]")
        assert checked is not None
        # A bare camera index, COM name, or /dev/video ordinal is an ephemeral
        # locator and can never be promoted into a persistent selector.
        if _FORBIDDEN_SELECTOR_RE.fullmatch(checked) is not None:
            raise PhysicalDeviceInventoryError(
                "numeric camera and ephemeral port ordinals are not persistent IDs"
            )
    return normalized


@dataclass(frozen=True, slots=True)
class NormalizedDeviceCandidate:
    """One observed device candidate; this record does not select a device."""

    device_class: InventoryDeviceClass
    source: InventorySource
    display_name: str
    vid: str | None
    pid: str | None
    unit_serial: str | None
    os_instance_id: str | None
    persistent_ids: tuple[str, ...]
    ephemeral_locator: str | None
    manufacturer: str | None
    product: str | None
    driver_service: str | None
    identity_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.device_class, InventoryDeviceClass):
            raise PhysicalDeviceInventoryError("device_class is invalid")
        if not isinstance(self.source, InventorySource):
            raise PhysicalDeviceInventoryError("source is invalid")
        object.__setattr__(
            self, "display_name", _bounded_text(self.display_name, "display_name")
        )
        object.__setattr__(self, "vid", _normalized_hex_id(self.vid, "vid"))
        object.__setattr__(self, "pid", _normalized_hex_id(self.pid, "pid"))
        for field_name in (
            "unit_serial",
            "os_instance_id",
            "ephemeral_locator",
            "manufacturer",
            "product",
            "driver_service",
        ):
            object.__setattr__(
                self,
                field_name,
                _bounded_text(getattr(self, field_name), field_name, required=False),
            )
        if not isinstance(self.persistent_ids, tuple):
            raise PhysicalDeviceInventoryError("persistent_ids must be a tuple")
        object.__setattr__(self, "persistent_ids", _persistent_ids(self.persistent_ids))
        if not isinstance(self.identity_blockers, tuple):
            raise PhysicalDeviceInventoryError("identity_blockers must be a tuple")
        object.__setattr__(
            self, "identity_blockers", _blockers(self.identity_blockers)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "device_class": self.device_class.value,
            "source": self.source.value,
            "display_name": self.display_name,
            "usb_identity": {
                "vid": self.vid,
                "pid": self.pid,
                "unit_serial": self.unit_serial,
            },
            "os_instance_id": self.os_instance_id,
            "persistent_ids": list(self.persistent_ids),
            "ephemeral_locator_observation": self.ephemeral_locator,
            "manufacturer": self.manufacturer,
            "product": self.product,
            "driver_service": self.driver_service,
            "identity_blockers": list(self.identity_blockers),
            "selection_performed": False,
            "qualified": False,
        }

    @property
    def candidate_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (
            self.os_instance_id or "",
            self.ephemeral_locator or "",
            self.candidate_sha256,
        )


@dataclass(frozen=True, slots=True)
class DeviceInventoryBatch:
    """Bounded candidates and collection blockers from one read-only source."""

    device_class: InventoryDeviceClass
    source: InventorySource
    candidates: tuple[NormalizedDeviceCandidate, ...]
    collection_blockers: tuple[str, ...]
    collection_complete: bool
    schema: str = DEVICE_INVENTORY_BATCH_SCHEMA
    device_ports_opened: bool = False
    selection_performed: bool = False

    def __post_init__(self) -> None:
        if self.schema != DEVICE_INVENTORY_BATCH_SCHEMA:
            raise PhysicalDeviceInventoryError("inventory batch schema is invalid")
        if not isinstance(self.device_class, InventoryDeviceClass):
            raise PhysicalDeviceInventoryError("batch device_class is invalid")
        if not isinstance(self.source, InventorySource):
            raise PhysicalDeviceInventoryError("batch source is invalid")
        if not isinstance(self.candidates, tuple):
            raise PhysicalDeviceInventoryError("batch candidates must be a tuple")
        if len(self.candidates) > MAX_DEVICE_CANDIDATES:
            raise PhysicalDeviceInventoryError("batch contains too many candidates")
        if any(
            not isinstance(candidate, NormalizedDeviceCandidate)
            or candidate.device_class is not self.device_class
            or candidate.source is not self.source
            for candidate in self.candidates
        ):
            raise PhysicalDeviceInventoryError(
                "batch candidates do not match the batch class/source"
            )
        expected_order = tuple(sorted(self.candidates, key=lambda item: item.sort_key))
        if self.candidates != expected_order:
            raise PhysicalDeviceInventoryError("batch candidates must be sorted")
        if not isinstance(self.collection_blockers, tuple):
            raise PhysicalDeviceInventoryError(
                "collection_blockers must be a tuple"
            )
        object.__setattr__(
            self, "collection_blockers", _blockers(self.collection_blockers)
        )
        if type(self.collection_complete) is not bool:
            raise PhysicalDeviceInventoryError("collection_complete must be boolean")
        if bool(self.collection_blockers) == self.collection_complete:
            raise PhysicalDeviceInventoryError(
                "collection_complete must be false exactly when blockers exist"
            )
        if self.device_ports_opened is not False or self.selection_performed is not False:
            raise PhysicalDeviceInventoryError(
                "inventory cannot open or select a device"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "device_class": self.device_class.value,
            "source": self.source.value,
            "collection_complete": self.collection_complete,
            "collection_blockers": list(self.collection_blockers),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "boundary": {
                "device_ports_opened": False,
                "selection_performed": False,
            },
        }

    @property
    def batch_sha256(self) -> str:
        return canonical_sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class InventoryAuthority:
    """An invariant rather than a capability: all inventory authority is false."""

    camera_opened: bool = False
    serial_port_opened: bool = False
    device_selected: bool = False
    camera_qualified: bool = False
    arm_qualified: bool = False
    feedback_authorized: bool = False
    motion_authorized: bool = False
    contact_authorized: bool = False
    physical_release_effect: str = "NONE"

    def __post_init__(self) -> None:
        values = (
            self.camera_opened,
            self.serial_port_opened,
            self.device_selected,
            self.camera_qualified,
            self.arm_qualified,
            self.feedback_authorized,
            self.motion_authorized,
            self.contact_authorized,
        )
        if any(value is not False for value in values):
            raise PhysicalDeviceInventoryError(
                "physical device inventory is permanently zero-authority"
            )
        if self.physical_release_effect != "NONE":
            raise PhysicalDeviceInventoryError(
                "physical inventory cannot have a release effect"
            )

    def to_dict(self) -> dict[str, object]:
        return {
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


@dataclass(frozen=True, slots=True)
class PhysicalDeviceInventoryReport:
    """Hash-bound camera/serial inventory that can never qualify hardware."""

    platform_system: str
    captured_at_unix_ns: int
    camera_inventory: DeviceInventoryBatch
    serial_inventory: DeviceInventoryBatch
    blockers: tuple[str, ...]
    authority: InventoryAuthority = InventoryAuthority()
    schema: str = PHYSICAL_DEVICE_INVENTORY_SCHEMA
    purpose: str = "READ_ONLY_PHYSICAL_DEVICE_DISCOVERY"

    def __post_init__(self) -> None:
        if self.schema != PHYSICAL_DEVICE_INVENTORY_SCHEMA:
            raise PhysicalDeviceInventoryError("inventory report schema is invalid")
        if self.purpose != "READ_ONLY_PHYSICAL_DEVICE_DISCOVERY":
            raise PhysicalDeviceInventoryError("inventory report purpose is invalid")
        platform_system = _bounded_text(self.platform_system, "platform_system")
        if platform_system not in {"Windows", "Linux"}:
            raise PhysicalDeviceInventoryError(
                "platform_system must be Windows or Linux"
            )
        object.__setattr__(self, "platform_system", platform_system)
        if (
            isinstance(self.captured_at_unix_ns, bool)
            or not isinstance(self.captured_at_unix_ns, int)
            or self.captured_at_unix_ns < 0
            or self.captured_at_unix_ns > (1 << 63) - 1
        ):
            raise PhysicalDeviceInventoryError(
                "captured_at_unix_ns must be a bounded non-negative integer"
            )
        if (
            not isinstance(self.camera_inventory, DeviceInventoryBatch)
            or self.camera_inventory.device_class is not InventoryDeviceClass.CAMERA
        ):
            raise PhysicalDeviceInventoryError("camera_inventory is invalid")
        if (
            not isinstance(self.serial_inventory, DeviceInventoryBatch)
            or self.serial_inventory.device_class is not InventoryDeviceClass.SERIAL
        ):
            raise PhysicalDeviceInventoryError("serial_inventory is invalid")
        expected_camera_source = (
            InventorySource.WINDOWS_PNP
            if platform_system == "Windows"
            else InventorySource.LINUX_SYSFS
        )
        if self.camera_inventory.source is not expected_camera_source:
            raise PhysicalDeviceInventoryError(
                "camera inventory source does not match platform_system"
            )
        if not isinstance(self.blockers, tuple):
            raise PhysicalDeviceInventoryError("report blockers must be a tuple")
        object.__setattr__(self, "blockers", _blockers(self.blockers))
        if not isinstance(self.authority, InventoryAuthority):
            raise PhysicalDeviceInventoryError("authority is invalid")

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": self.schema,
            "purpose": self.purpose,
            "platform_system": self.platform_system,
            "captured_at_unix_ns": self.captured_at_unix_ns,
            "camera_inventory": self.camera_inventory.to_dict(),
            "serial_inventory": self.serial_inventory.to_dict(),
            "blockers": list(self.blockers),
            "authority": self.authority.to_dict(),
        }
        if include_hash:
            value["report_sha256"] = self.report_sha256
        return value

    @property
    def report_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))


def _identity_blockers(
    *,
    device_class: InventoryDeviceClass,
    vid: str | None,
    pid: str | None,
    serial_number: str | None,
    os_instance_id: str | None,
    persistent_ids: Sequence[str],
) -> tuple[str, ...]:
    prefix = device_class.value
    values: list[str] = []
    if vid is None:
        values.append(f"{prefix}_VID_MISSING")
    if pid is None:
        values.append(f"{prefix}_PID_MISSING")
    if serial_number is None:
        values.append(f"{prefix}_UNIT_SERIAL_MISSING")
    if os_instance_id is None:
        values.append(f"{prefix}_OS_INSTANCE_ID_MISSING")
    if not persistent_ids:
        values.append(f"{prefix}_PERSISTENT_SELECTOR_MISSING")
    return _blockers(values)


def _empty_batch(
    device_class: InventoryDeviceClass,
    source: InventorySource,
    blocker: str,
) -> DeviceInventoryBatch:
    return DeviceInventoryBatch(
        device_class=device_class,
        source=source,
        candidates=(),
        collection_blockers=(blocker,),
        collection_complete=False,
    )


@dataclass(frozen=True, slots=True)
class ArgvCommandResult:
    """Bounded raw result returned by an argv-only command runner."""

    returncode: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or not isinstance(self.returncode, int):
            raise PhysicalDeviceInventoryError("command returncode must be an integer")
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise PhysicalDeviceInventoryError("command output must be bytes")
        if len(self.stdout) > MAX_COMMAND_STDOUT_BYTES:
            raise PhysicalDeviceInventoryError("command stdout exceeded its limit")
        if len(self.stderr) > MAX_COMMAND_STDERR_BYTES:
            raise PhysicalDeviceInventoryError("command stderr exceeded its limit")


@runtime_checkable
class ArgvCommandRunner(Protocol):
    """Runner seam with no string command and no shell option."""

    def run(
        self, argv: tuple[str, ...], *, timeout_seconds: int
    ) -> ArgvCommandResult: ...


class SubprocessArgvCommandRunner:
    """Execute an already-fixed argv directly, never through a shell."""

    def run(
        self, argv: tuple[str, ...], *, timeout_seconds: int
    ) -> ArgvCommandResult:
        if (
            not isinstance(argv, tuple)
            or not argv
            or any(not isinstance(item, str) or not item for item in argv)
        ):
            raise PhysicalDeviceInventoryError("argv must be a non-empty string tuple")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= COMMAND_TIMEOUT_SECONDS
        ):
            raise PhysicalDeviceInventoryError("command timeout is outside policy")
        environment = None
        if os.name == "nt" and argv == WINDOWS_CAMERA_PNP_ARGV:
            system32 = Path(argv[0]).parents[2]
            windows = system32.parent
            environment = {
                "SystemRoot": str(windows),
                "WINDIR": str(windows),
                "PATH": str(system32),
                "PSModulePath": str(
                    system32 / "WindowsPowerShell" / "v1.0" / "Modules"
                ),
            }
        completed = subprocess.run(  # noqa: S603 - fixed argv supplied by this module
            list(argv),
            check=False,
            shell=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        return ArgvCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


# This script reads PnP properties only.  It intentionally contains no camera
# API, stream operation, device enable/disable operation, or numeric selector.
_WINDOWS_CAMERA_PNP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Read-DeviceProperty($instanceId, $keyName) {
  $value = Get-PnpDeviceProperty -InstanceId $instanceId -KeyName $keyName -ErrorAction SilentlyContinue
  if ($null -eq $value) { return $null }
  return $value.Data
}
$devices = @(Get-PnpDevice -PresentOnly |
  Where-Object { $_.Class -in @('Camera', 'Image') } |
  Select-Object -First 129 |
  ForEach-Object {
    [pscustomobject]@{
      Status = $_.Status
      Class = $_.Class
      FriendlyName = $_.FriendlyName
      InstanceId = $_.InstanceId
      # Get-PnpDevice -PresentOnly is the source of this observation; the
      # returned object does not expose a Present property on every host.
      Present = $true
      Manufacturer = Read-DeviceProperty $_.InstanceId 'DEVPKEY_Device_Manufacturer'
      Product = Read-DeviceProperty $_.InstanceId 'DEVPKEY_Device_BusReportedDeviceDesc'
      Service = Read-DeviceProperty $_.InstanceId 'DEVPKEY_Device_Service'
      SerialNumber = Read-DeviceProperty $_.InstanceId 'DEVPKEY_Device_SerialNumber'
      ContainerId = Read-DeviceProperty $_.InstanceId 'DEVPKEY_Device_ContainerId'
      HardwareIds = Read-DeviceProperty $_.InstanceId 'DEVPKEY_Device_HardwareIds'
    }
  })
# Keep both boundaries array-shaped. An empty pipeline otherwise becomes null;
# piping an array into ConvertTo-Json unwraps a single camera into an object.
# Windows PowerShell 5.1 supports -InputObject but not the newer -AsArray switch.
ConvertTo-Json -InputObject $devices -Compress -Depth 4
""".strip()


def _trusted_windows_powershell() -> str:
    if os.name != "nt":
        return "powershell.exe"  # Only used by injected runners on non-Windows.
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise PhysicalDeviceInventoryError("Windows system directory is unavailable")
    path = Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not path.is_file():
        raise PhysicalDeviceInventoryError("trusted Windows PowerShell is unavailable")
    return str(path)


WINDOWS_CAMERA_PNP_ARGV = (
    _trusted_windows_powershell(),
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    _WINDOWS_CAMERA_PNP_SCRIPT,
)


def _strict_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PhysicalDeviceInventoryError(
                f"duplicate Windows PnP JSON field {key!r}"
            )
        result[key] = value
    return result


_WINDOWS_RECORD_FIELDS = frozenset(
    {
        "Status",
        "Class",
        "FriendlyName",
        "InstanceId",
        "Present",
        "Manufacturer",
        "Product",
        "Service",
        "SerialNumber",
        "ContainerId",
        "HardwareIds",
    }
)


def _hardware_id_strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        checked = _bounded_text(value, "HardwareIds", required=False)
        return () if checked is None else (checked,)
    if not isinstance(value, list) or len(value) > 32:
        raise PhysicalDeviceInventoryError("HardwareIds must be bounded text/list data")
    result: list[str] = []
    for index, item in enumerate(value):
        checked = _bounded_text(item, f"HardwareIds[{index}]", required=False)
        if checked is not None:
            result.append(checked)
    return tuple(result)


def _usb_ids_from_texts(
    values: Sequence[str],
) -> tuple[str | None, str | None, bool]:
    observed: set[tuple[str, str]] = set()
    for value in values:
        match = _WINDOWS_USB_RE.search(value)
        if match is not None:
            observed.add((match.group(1).lower(), match.group(2).lower()))
    if not observed:
        return None, None, False
    if len(observed) != 1:
        return None, None, True
    vid, pid = next(iter(observed))
    return vid, pid, False


def inventory_windows_pnp_cameras(
    runner: ArgvCommandRunner,
) -> DeviceInventoryBatch:
    """Enumerate Windows camera metadata through a fixed, read-only PnP query."""

    if not isinstance(runner, ArgvCommandRunner):
        raise PhysicalDeviceInventoryError("runner does not implement ArgvCommandRunner")
    try:
        result = runner.run(
            WINDOWS_CAMERA_PNP_ARGV,
            timeout_seconds=COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return _empty_batch(
            InventoryDeviceClass.CAMERA,
            InventorySource.WINDOWS_PNP,
            "WINDOWS_PNP_ENUMERATION_FAILED",
        )
    if not isinstance(result, ArgvCommandResult):
        raise PhysicalDeviceInventoryError("runner returned an invalid result type")
    if result.returncode != 0:
        return _empty_batch(
            InventoryDeviceClass.CAMERA,
            InventorySource.WINDOWS_PNP,
            "WINDOWS_PNP_ENUMERATION_FAILED",
        )
    try:
        decoded = result.stdout.decode("utf-8-sig")
        document = json.loads(decoded, object_pairs_hook=_strict_json_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PhysicalDeviceInventoryError(
            "Windows PnP output is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(document, list):
        raise PhysicalDeviceInventoryError("Windows PnP output root must be an array")
    if len(document) > MAX_DEVICE_CANDIDATES:
        return _empty_batch(
            InventoryDeviceClass.CAMERA,
            InventorySource.WINDOWS_PNP,
            "WINDOWS_PNP_CANDIDATE_LIMIT_EXCEEDED",
        )

    candidates: list[NormalizedDeviceCandidate] = []
    for index, raw in enumerate(document):
        if not isinstance(raw, Mapping) or frozenset(raw) != _WINDOWS_RECORD_FIELDS:
            raise PhysicalDeviceInventoryError(
                f"Windows PnP record {index} has an unexpected field set"
            )
        device_class = _optional_provider_text(raw["Class"], f"record[{index}].Class")
        if device_class not in {"Camera", "Image"}:
            raise PhysicalDeviceInventoryError(
                f"Windows PnP record {index} is not a camera class"
            )
        instance_id = _optional_provider_text(
            raw["InstanceId"], f"record[{index}].InstanceId"
        )
        hardware_ids = _hardware_id_strings(raw["HardwareIds"])
        vid, pid, usb_identity_ambiguous = _usb_ids_from_texts(
            (() if instance_id is None else (instance_id,)) + hardware_ids
        )
        serial_number = _optional_provider_text(
            raw["SerialNumber"], f"record[{index}].SerialNumber"
        )
        container_id = _optional_provider_text(
            raw["ContainerId"], f"record[{index}].ContainerId"
        )
        persistent_ids: list[str] = []
        if instance_id is not None:
            persistent_ids.append(f"windows-pnp-instance:{instance_id}")
        if container_id is not None:
            persistent_ids.append(f"windows-container:{container_id}")
        if vid is not None and pid is not None and serial_number is not None:
            persistent_ids.append(f"usb-unit:{vid}:{pid}:{serial_number}")

        blockers = list(
            _identity_blockers(
                device_class=InventoryDeviceClass.CAMERA,
                vid=vid,
                pid=pid,
                serial_number=serial_number,
                os_instance_id=instance_id,
                persistent_ids=persistent_ids,
            )
        )
        present = raw["Present"]
        if type(present) is not bool:
            raise PhysicalDeviceInventoryError(
                f"record[{index}].Present must be boolean"
            )
        if not present:
            blockers.append("CAMERA_NOT_PRESENT")
        status = _optional_provider_text(raw["Status"], f"record[{index}].Status")
        if status != "OK":
            blockers.append("CAMERA_PNP_STATUS_NOT_OK")
        if usb_identity_ambiguous:
            blockers.append("CAMERA_USB_IDENTITY_AMBIGUOUS")
        if serial_number is None:
            blockers.append("CAMERA_PERSISTENT_UNIT_SELECTOR_MISSING")
        # PnP identity does not observe the USB controller, port chain, link
        # generation, or negotiated speed.  Those fields must be proven later.
        blockers.extend(
            (
                "CAMERA_USB3_TOPOLOGY_NOT_OBSERVED",
                "CAMERA_NEGOTIATED_LINK_SPEED_NOT_OBSERVED",
            )
        )
        friendly_name = _optional_provider_text(
            raw["FriendlyName"], f"record[{index}].FriendlyName"
        )
        product = _optional_provider_text(raw["Product"], f"record[{index}].Product")
        candidates.append(
            NormalizedDeviceCandidate(
                device_class=InventoryDeviceClass.CAMERA,
                source=InventorySource.WINDOWS_PNP,
                display_name=friendly_name or product or "Unnamed Windows camera",
                vid=vid,
                pid=pid,
                unit_serial=serial_number,
                os_instance_id=instance_id,
                persistent_ids=tuple(persistent_ids),
                ephemeral_locator=None,
                manufacturer=_optional_provider_text(
                    raw["Manufacturer"], f"record[{index}].Manufacturer"
                ),
                product=product,
                driver_service=_optional_provider_text(
                    raw["Service"], f"record[{index}].Service"
                ),
                identity_blockers=tuple(blockers),
            )
        )
    ordered = tuple(sorted(candidates, key=lambda item: item.sort_key))
    return DeviceInventoryBatch(
        device_class=InventoryDeviceClass.CAMERA,
        source=InventorySource.WINDOWS_PNP,
        candidates=ordered,
        collection_blockers=(),
        collection_complete=True,
    )


def _bounded_directory_entries(path: Path) -> tuple[tuple[Path, ...], bool]:
    entries: list[Path] = []
    with os.scandir(path) as iterator:
        for entry in iterator:
            if len(entries) >= MAX_DEVICE_CANDIDATES:
                return tuple(sorted(entries)), True
            entries.append(Path(entry.path))
    return tuple(sorted(entries)), False


def _read_small_text(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_SYSFS_FILE_BYTES + 1)
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return None
    if len(raw) > MAX_SYSFS_FILE_BYTES:
        return None
    try:
        return _bounded_text(raw.decode("utf-8"), str(path), required=False)
    except (UnicodeError, PhysicalDeviceInventoryError):
        return None


def _first_ancestor_text(start: Path, filename: str) -> str | None:
    current = start
    for _ in range(32):
        value = _read_small_text(current / filename)
        if value is not None:
            return value
        if current.parent == current:
            break
        current = current.parent
    return None


def _linux_by_id_links(
    by_id_root: Path | None,
) -> tuple[tuple[tuple[Path, Path], ...], bool]:
    if by_id_root is None or not by_id_root.is_dir():
        return (), False
    try:
        entries, exceeded = _bounded_directory_entries(by_id_root)
    except OSError:
        return (), False
    links: list[tuple[Path, Path]] = []
    for entry in entries:
        try:
            if entry.is_symlink():
                links.append((entry, entry.resolve(strict=False)))
        except OSError:
            continue
    return tuple(links), exceeded


def inventory_linux_video_cameras_from_sysfs(
    *,
    sys_class_root: Path = Path("/sys/class/video4linux"),
    dev_root: Path = Path("/dev"),
    by_id_root: Path | None = Path("/dev/v4l/by-id"),
) -> DeviceInventoryBatch:
    """Read Linux video identity metadata without opening video device nodes."""

    source = InventorySource.LINUX_SYSFS
    root = Path(sys_class_root)
    if not root.is_dir():
        return _empty_batch(
            InventoryDeviceClass.CAMERA,
            source,
            "LINUX_VIDEO_SYSFS_UNAVAILABLE",
        )
    try:
        entries, entry_limit_exceeded = _bounded_directory_entries(root)
    except OSError:
        return _empty_batch(
            InventoryDeviceClass.CAMERA,
            source,
            "LINUX_VIDEO_SYSFS_ENUMERATION_FAILED",
        )
    by_id_links, by_id_limit_exceeded = _linux_by_id_links(by_id_root)

    candidates: list[NormalizedDeviceCandidate] = []
    for entry in entries:
        try:
            resolved_entry = entry.resolve(strict=True)
            device_path = (entry / "device").resolve(strict=True)
        except OSError:
            resolved_entry = entry.resolve(strict=False)
            device_path = resolved_entry
        vid_raw = _first_ancestor_text(device_path, "idVendor")
        pid_raw = _first_ancestor_text(device_path, "idProduct")
        try:
            vid = _normalized_hex_id(vid_raw, "linux idVendor")
        except PhysicalDeviceInventoryError:
            vid = None
        try:
            pid = _normalized_hex_id(pid_raw, "linux idProduct")
        except PhysicalDeviceInventoryError:
            pid = None
        serial_number = _first_ancestor_text(device_path, "serial")
        manufacturer = _first_ancestor_text(device_path, "manufacturer")
        product = _first_ancestor_text(device_path, "product")
        driver_service: str | None = None
        try:
            driver_link = entry / "device" / "driver"
            if driver_link.exists() or driver_link.is_symlink():
                driver_service = driver_link.resolve(strict=False).name
        except OSError:
            driver_service = None

        os_instance_id = str(device_path)
        ephemeral_node = Path(dev_root) / entry.name
        try:
            resolved_node = ephemeral_node.resolve(strict=False)
        except OSError:
            resolved_node = ephemeral_node
        all_matched_by_id = tuple(
            str(link)
            for link, target in by_id_links
            if target == resolved_node
        )
        maximum_by_id = MAX_PERSISTENT_IDS_PER_CANDIDATE - 2
        matched_by_id = all_matched_by_id[:maximum_by_id]
        persistent_ids = [f"linux-sysfs-instance:{os_instance_id}"]
        persistent_ids.extend(f"linux-v4l-by-id:{link}" for link in matched_by_id)
        if vid is not None and pid is not None and serial_number is not None:
            persistent_ids.append(f"usb-unit:{vid}:{pid}:{serial_number}")

        blockers = list(
            _identity_blockers(
                device_class=InventoryDeviceClass.CAMERA,
                vid=vid,
                pid=pid,
                serial_number=serial_number,
                os_instance_id=os_instance_id,
                persistent_ids=persistent_ids,
            )
        )
        if not matched_by_id and serial_number is None:
            blockers.append("CAMERA_PERSISTENT_UNIT_SELECTOR_MISSING")
        if len(all_matched_by_id) > maximum_by_id:
            blockers.append("CAMERA_PERSISTENT_ID_LIMIT_EXCEEDED")
        blockers.extend(
            (
                "CAMERA_USB3_TOPOLOGY_NOT_OBSERVED",
                "CAMERA_NEGOTIATED_LINK_SPEED_NOT_OBSERVED",
            )
        )
        candidates.append(
            NormalizedDeviceCandidate(
                device_class=InventoryDeviceClass.CAMERA,
                source=source,
                display_name=_read_small_text(entry / "name")
                or product
                or entry.name,
                vid=vid,
                pid=pid,
                unit_serial=serial_number,
                os_instance_id=os_instance_id,
                persistent_ids=tuple(persistent_ids),
                ephemeral_locator=str(ephemeral_node),
                manufacturer=manufacturer,
                product=product,
                driver_service=driver_service,
                identity_blockers=tuple(blockers),
            )
        )
    collection_blockers: list[str] = []
    if entry_limit_exceeded:
        collection_blockers.append("LINUX_VIDEO_CANDIDATE_LIMIT_EXCEEDED")
    if by_id_limit_exceeded:
        collection_blockers.append("LINUX_VIDEO_BY_ID_LIMIT_EXCEEDED")
    return DeviceInventoryBatch(
        device_class=InventoryDeviceClass.CAMERA,
        source=source,
        candidates=tuple(sorted(candidates, key=lambda item: item.sort_key)),
        collection_blockers=tuple(collection_blockers),
        collection_complete=not collection_blockers,
    )


@dataclass(frozen=True, slots=True)
class RawSerialPortObservation:
    """Metadata returned by a read-only serial enumerator, before normalization."""

    port_name: str | None
    description: str | None = None
    hwid: str | None = None
    vid: int | str | None = None
    pid: int | str | None = None
    serial_number: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    interface: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "port_name",
            "description",
            "hwid",
            "serial_number",
            "location",
            "manufacturer",
            "product",
            "interface",
        ):
            object.__setattr__(
                self,
                field_name,
                _bounded_text(getattr(self, field_name), field_name, required=False),
            )
        object.__setattr__(self, "vid", _normalized_hex_id(self.vid, "serial vid"))
        object.__setattr__(self, "pid", _normalized_hex_id(self.pid, "serial pid"))


@runtime_checkable
class ReadOnlySerialPortEnumerator(Protocol):
    """Provider seam whose only operation returns already-enumerated metadata."""

    def enumerate_serial_ports(self) -> Sequence[RawSerialPortObservation]: ...


def _serial_candidate(
    raw: RawSerialPortObservation,
    source: InventorySource,
) -> NormalizedDeviceCandidate:
    # RawSerialPortObservation normalizes these fields at construction; repeat
    # the narrow conversion here so the static type also reflects that fact.
    vid = _normalized_hex_id(raw.vid, "serial candidate vid")
    pid = _normalized_hex_id(raw.pid, "serial candidate pid")
    parsed_vid: str | None = None
    parsed_pid: str | None = None
    parsed_usb_ambiguous = False
    if raw.hwid is not None:
        parsed_vid, parsed_pid, parsed_usb_ambiguous = _usb_ids_from_texts((raw.hwid,))
    direct_usb_conflict = (
        (vid is not None and parsed_vid is not None and vid != parsed_vid)
        or (pid is not None and parsed_pid is not None and pid != parsed_pid)
    )
    if vid is None or pid is None:
        vid = vid or parsed_vid
        pid = pid or parsed_pid
    serial_number = raw.serial_number
    parsed_serial_number: str | None = None
    if serial_number is None and raw.hwid is not None:
        match = _SERIAL_IN_HWID_RE.search(raw.hwid)
        if match is not None:
            parsed_serial_number = _optional_provider_text(
                match.group(1), "serial number parsed from hwid"
            )
            serial_number = parsed_serial_number
    elif raw.hwid is not None:
        match = _SERIAL_IN_HWID_RE.search(raw.hwid)
        if match is not None:
            parsed_serial_number = _optional_provider_text(
                match.group(1), "serial number parsed from hwid"
            )

    os_instance_id = raw.hwid if raw.hwid not in {None, "n/a", "N/A"} else None
    persistent_ids: list[str] = []
    if vid is not None and pid is not None and serial_number is not None:
        persistent_ids.append(f"usb-unit:{vid}:{pid}:{serial_number}")
    if raw.port_name is not None and raw.port_name.startswith("/dev/serial/by-id/"):
        persistent_ids.append(f"linux-serial-by-id:{raw.port_name}")
    blockers = list(
        _identity_blockers(
            device_class=InventoryDeviceClass.SERIAL,
            vid=vid,
            pid=pid,
            serial_number=serial_number,
            os_instance_id=os_instance_id,
            persistent_ids=persistent_ids,
        )
    )
    if parsed_usb_ambiguous or direct_usb_conflict:
        blockers.append("SERIAL_USB_IDENTITY_AMBIGUOUS")
    if (
        raw.serial_number is not None
        and parsed_serial_number is not None
        and raw.serial_number != parsed_serial_number
    ):
        blockers.append("SERIAL_UNIT_SERIAL_AMBIGUOUS")
    if raw.port_name is None:
        blockers.append("SERIAL_EPHEMERAL_LOCATOR_MISSING")
    return NormalizedDeviceCandidate(
        device_class=InventoryDeviceClass.SERIAL,
        source=source,
        display_name=raw.description or raw.product or "Unnamed serial device",
        vid=vid,
        pid=pid,
        unit_serial=serial_number,
        os_instance_id=os_instance_id,
        persistent_ids=tuple(persistent_ids),
        ephemeral_locator=raw.port_name,
        manufacturer=raw.manufacturer,
        product=raw.product,
        driver_service=raw.interface,
        identity_blockers=tuple(blockers),
    )


def _inventory_serial_observations(
    observations: Sequence[RawSerialPortObservation],
    *,
    source: InventorySource,
) -> DeviceInventoryBatch:
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise PhysicalDeviceInventoryError(
            "serial enumerator must return a bounded Sequence"
        )
    if len(observations) > MAX_DEVICE_CANDIDATES:
        return _empty_batch(
            InventoryDeviceClass.SERIAL,
            source,
            "SERIAL_CANDIDATE_LIMIT_EXCEEDED",
        )
    if any(not isinstance(item, RawSerialPortObservation) for item in observations):
        raise PhysicalDeviceInventoryError(
            "serial enumerator returned an invalid observation"
        )
    candidates = tuple(
        sorted(
            (_serial_candidate(item, source) for item in observations),
            key=lambda item: item.sort_key,
        )
    )
    return DeviceInventoryBatch(
        device_class=InventoryDeviceClass.SERIAL,
        source=source,
        candidates=candidates,
        collection_blockers=(),
        collection_complete=True,
    )


def inventory_serial_ports_from_provider(
    provider: ReadOnlySerialPortEnumerator,
) -> DeviceInventoryBatch:
    """Normalize injected serial enumeration without opening any returned port."""

    if not isinstance(provider, ReadOnlySerialPortEnumerator):
        raise PhysicalDeviceInventoryError(
            "provider does not implement ReadOnlySerialPortEnumerator"
        )
    try:
        observations = provider.enumerate_serial_ports()
    except (OSError, RuntimeError):
        return _empty_batch(
            InventoryDeviceClass.SERIAL,
            InventorySource.INJECTED_SERIAL_ENUMERATOR,
            "SERIAL_ENUMERATION_FAILED",
        )
    return _inventory_serial_observations(
        observations,
        source=InventorySource.INJECTED_SERIAL_ENUMERATOR,
    )


def inventory_serial_ports_with_pyserial() -> DeviceInventoryBatch:
    """Inventory pyserial metadata only; never instantiate or open ``Serial``.

    Keeping the import inside this explicitly named function ensures importing
    the onboarding package cannot load pyserial or touch serial-device state.
    ``list_ports.comports`` reads OS enumeration metadata and does not open the
    returned port names.
    """

    source = InventorySource.PYSERIAL_LIST_PORTS
    try:
        list_ports = importlib.import_module("serial.tools.list_ports")
    except ImportError:
        return _empty_batch(
            InventoryDeviceClass.SERIAL,
            source,
            "PYSERIAL_NOT_AVAILABLE",
        )
    comports = getattr(list_ports, "comports", None)
    if not callable(comports):
        return _empty_batch(
            InventoryDeviceClass.SERIAL,
            source,
            "PYSERIAL_LIST_PORTS_UNAVAILABLE",
        )
    try:
        values = comports()
    except (OSError, RuntimeError):
        return _empty_batch(
            InventoryDeviceClass.SERIAL,
            source,
            "PYSERIAL_ENUMERATION_FAILED",
        )
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise PhysicalDeviceInventoryError(
            "pyserial comports() must return a bounded Sequence"
        )
    if len(values) > MAX_DEVICE_CANDIDATES:
        return _empty_batch(
            InventoryDeviceClass.SERIAL,
            source,
            "SERIAL_CANDIDATE_LIMIT_EXCEEDED",
        )
    observations: list[RawSerialPortObservation] = []
    for value in values:
        observations.append(
            RawSerialPortObservation(
                port_name=getattr(value, "device", None),
                description=getattr(value, "description", None),
                hwid=getattr(value, "hwid", None),
                vid=getattr(value, "vid", None),
                pid=getattr(value, "pid", None),
                serial_number=getattr(value, "serial_number", None),
                location=getattr(value, "location", None),
                manufacturer=getattr(value, "manufacturer", None),
                product=getattr(value, "product", None),
                interface=getattr(value, "interface", None),
            )
        )
    return _inventory_serial_observations(observations, source=source)


def _candidate_identity_is_incomplete(candidate: NormalizedDeviceCandidate) -> bool:
    return any(
        blocker.endswith(
            (
                "VID_MISSING",
                "PID_MISSING",
                "UNIT_SERIAL_MISSING",
                "OS_INSTANCE_ID_MISSING",
                "PERSISTENT_SELECTOR_MISSING",
                "PERSISTENT_UNIT_SELECTOR_MISSING",
                "IDENTITY_AMBIGUOUS",
                "SERIAL_AMBIGUOUS",
            )
        )
        for blocker in candidate.identity_blockers
    )


def _persistent_id_collides(candidates: Sequence[NormalizedDeviceCandidate]) -> bool:
    seen: set[str] = set()
    for candidate in candidates:
        for persistent_id in candidate.persistent_ids:
            if persistent_id in seen:
                return True
            seen.add(persistent_id)
    return False


def compose_physical_device_inventory_report(
    *,
    platform_system: str,
    captured_at_unix_ns: int,
    camera_inventory: DeviceInventoryBatch,
    serial_inventory: DeviceInventoryBatch,
) -> PhysicalDeviceInventoryReport:
    """Combine inventory batches while preserving every unresolved identity gate."""

    blockers: list[str] = []
    blockers.extend(camera_inventory.collection_blockers)
    blockers.extend(serial_inventory.collection_blockers)
    if not camera_inventory.candidates:
        blockers.append("CAMERA_CANDIDATE_NOT_OBSERVED")
    else:
        blockers.append("CAMERA_SELECTION_NOT_PERFORMED_BY_DESIGN")
    if len(camera_inventory.candidates) > 1:
        blockers.append("CAMERA_CANDIDATE_SELECTION_UNRESOLVED")
    if any(_candidate_identity_is_incomplete(item) for item in camera_inventory.candidates):
        blockers.append("CAMERA_IDENTITY_INCOMPLETE")
    if _persistent_id_collides(camera_inventory.candidates):
        blockers.append("CAMERA_PERSISTENT_ID_AMBIGUOUS")

    if not serial_inventory.candidates:
        blockers.append("SERIAL_CANDIDATE_NOT_OBSERVED")
    else:
        blockers.append("SERIAL_SELECTION_NOT_PERFORMED_BY_DESIGN")
    if len(serial_inventory.candidates) > 1:
        blockers.append("SERIAL_CANDIDATE_SELECTION_UNRESOLVED")
    if any(_candidate_identity_is_incomplete(item) for item in serial_inventory.candidates):
        blockers.append("SERIAL_IDENTITY_INCOMPLETE")
    if _persistent_id_collides(serial_inventory.candidates):
        blockers.append("SERIAL_PERSISTENT_ID_AMBIGUOUS")

    # These are permanent facts of this boundary, even with perfect identities.
    blockers.extend(
        (
            "INVENTORY_ONLY_NOT_DEVICE_QUALIFICATION",
            "CAMERA_STREAM_NOT_OPENED_BY_DESIGN",
            "CAMERA_USB3_TOPOLOGY_REQUIRES_SEPARATE_EVIDENCE",
            "SERIAL_PORT_NOT_OPENED_BY_DESIGN",
            "ROARM_IDENTITY_REQUIRES_SEPARATE_EVIDENCE",
        )
    )
    return PhysicalDeviceInventoryReport(
        platform_system=platform_system,
        captured_at_unix_ns=captured_at_unix_ns,
        camera_inventory=camera_inventory,
        serial_inventory=serial_inventory,
        blockers=tuple(blockers),
    )


__all__ = [
    "COMMAND_TIMEOUT_SECONDS",
    "DEVICE_INVENTORY_BATCH_SCHEMA",
    "MAX_COMMAND_STDERR_BYTES",
    "MAX_COMMAND_STDOUT_BYTES",
    "MAX_DEVICE_CANDIDATES",
    "PHYSICAL_DEVICE_INVENTORY_SCHEMA",
    "WINDOWS_CAMERA_PNP_ARGV",
    "ArgvCommandResult",
    "ArgvCommandRunner",
    "DeviceInventoryBatch",
    "InventoryAuthority",
    "InventoryDeviceClass",
    "InventorySource",
    "NormalizedDeviceCandidate",
    "PhysicalDeviceInventoryError",
    "PhysicalDeviceInventoryReport",
    "RawSerialPortObservation",
    "ReadOnlySerialPortEnumerator",
    "SubprocessArgvCommandRunner",
    "compose_physical_device_inventory_report",
    "inventory_linux_video_cameras_from_sysfs",
    "inventory_serial_ports_from_provider",
    "inventory_serial_ports_with_pyserial",
    "inventory_windows_pnp_cameras",
]
