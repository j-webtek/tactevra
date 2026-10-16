"""One-attempt r119 to r120 app-slot install with no startup motion."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace


PORT = "COM4"
USB_SERIAL = "52E4E1E8337FEF119E92181CEDD322A4"
MAC = "fc:e8:c0:f8:d5:38"
PREVIOUS_SHA256 = "fcbec9eaf6917f2078297540b84069bcd59888fea142e858e292374e1594691e"
CURRENT_SHA256 = "1b0589fa323a2714777f5c70453eeec6daa94bd8c92a481701689da82ce93fdc"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(root: Path) -> dict:
    root = Path(root).resolve()
    tools = root / ".firmware-tools"
    previous_path = (
        tools
        / "build-configured-diagnostic-candidate-r119--default-4mb-no-psram"
        / "RoArm-M3_example.ino.bin"
    )
    image_path = (
        tools
        / "build-configured-diagnostic-candidate-r120--default-4mb-no-psram"
        / "RoArm-M3_example.ino.bin"
    )
    previous = previous_path.read_bytes()
    image = image_path.read_bytes()
    if _sha256(previous) != PREVIOUS_SHA256 or _sha256(image) != CURRENT_SHA256:
        raise ValueError("Pinned r119/r120 image differs")
    if not 0 < len(previous) <= 0x140000 or not 0 < len(image) <= 0x140000:
        raise ValueError("App image exceeds app slot")
    journal = root / "runs" / "live-controller" / "app-r120-deployment-events.jsonl"
    if journal.exists():
        raise ValueError("r120 install already attempted; no retry")
    return {
        "previous": previous,
        "image": image,
        "image_path": image_path,
        "journal": journal,
    }


def install(root: Path, prepared: dict) -> None:
    root = Path(root).resolve()
    current = prepare(root)
    if (
        prepared["previous"] != current["previous"]
        or prepared["image"] != current["image"]
        or prepared["image_path"] != current["image_path"]
        or prepared["journal"] != current["journal"]
    ):
        raise ValueError("Pinned r120 install inputs changed")
    pinned = root / ".firmware-tools" / "esptool-api-4.6"
    sys.path.insert(0, str(pinned))
    import serial
    from serial.tools.list_ports import comports
    import esptool
    from esptool import cmds, loader
    from esptool.reset import ClassicReset, DEFAULT_RESET_DELAY

    if (
        serial.__version__ != "3.5"
        or esptool.__version__ != "4.6"
        or not Path(serial.__file__).resolve().is_relative_to(pinned.resolve())
        or not Path(esptool.__file__).resolve().is_relative_to(pinned.resolve())
    ):
        raise ValueError("Unpinned installer runtime")
    matches = [
        item
        for item in comports()
        if item.device == PORT
        and item.vid == 0x10C4
        and item.pid == 0xEA60
        and item.serial_number == USB_SERIAL
    ]
    if len(matches) != 1:
        raise ValueError("Expected controller USB adapter absent")

    class LongerResetROM(esptool.ESP32ROM):
        def _connect_attempt(self, mode="default_reset", esp32r0_delay=False):
            if mode != "default_reset":
                return super()._connect_attempt(mode, esp32r0_delay)
            ClassicReset(self._port, DEFAULT_RESET_DELAY * 3.0)()
            self._port.reset_input_buffer()
            return self.sync()

    loader.WRITE_BLOCK_ATTEMPTS = 1
    current["journal"].parent.mkdir(parents=True, exist_ok=True)
    with current["journal"].open("x", encoding="utf-8") as journal:
        def event(stage: str, **fields) -> None:
            row = {"stage": stage, **fields}
            journal.write(json.dumps(row) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
            print(json.dumps(row), flush=True)

        event("RESERVED", app_sha256=CURRENT_SHA256, offset=0x10000, bytes=len(current["image"]))
        port = serial.Serial(port=None, baudrate=115200, timeout=3, write_timeout=10)
        port.dtr = False
        port.rts = False
        port.port = PORT
        try:
            port.open()
            esp = LongerResetROM(port, baud=115200)
            esp.connect("default_reset", attempts=1)
            mac = ":".join(f"{value:02x}" for value in esp.read_mac())
            if (
                mac != MAC
                or esp.secure_download_mode
                or esp.stub_is_disabled
                or esp.get_secure_boot_enabled()
                or esp.get_flash_encryption_enabled()
            ):
                raise ValueError("Controller identity/security differs")
            stub = esp.run_stub()
            if stub.flash_id() != 0x164020:
                raise ValueError("Flash identity differs")
            if stub.flash_md5sum(0x10000, len(current["previous"])) != hashlib.md5(
                current["previous"]
            ).hexdigest():
                raise ValueError("Installed predecessor is not pinned r119")
            protected = [(0, 0x10000), (0x150000, 0x2B0000)]
            before = [stub.flash_md5sum(start, size) for start, size in protected]
            event("IDENTITY_AND_PREWRITE_VERIFIED", mac=mac, predecessor_sha256=PREVIOUS_SHA256)
            stream = io.BytesIO(current["image"])
            stream.name = str(current["image_path"])
            args = SimpleNamespace(
                addr_filename=[(0x10000, stream)],
                compress=True,
                no_compress=False,
                no_stub=False,
                force=False,
                encrypt=False,
                encrypt_files=None,
                erase_all=False,
                verify=False,
                ignore_flash_encryption_efuse_setting=False,
                flash_size="keep",
                flash_mode="keep",
                flash_freq="keep",
            )
            event("WRITE_ATTEMPT_STARTED")
            cmds.write_flash(stub, args)
            readback = stub.read_flash(0x10000, len(current["image"]))
            if readback != current["image"] or _sha256(readback) != CURRENT_SHA256:
                raise ValueError("App readback mismatch")
            if before != [stub.flash_md5sum(start, size) for start, size in protected]:
                raise ValueError("Protected region changed")
            event("FLASH_VERIFIED", app_sha256=CURRENT_SHA256, protected_regions_unchanged=True)
            event("ONE_STARTUP_ATTEMPT")
            stub.hard_reset()
            event("STARTUP_RESET_SENT", application_health_verified=False)
        except BaseException as error:
            event("STOPPED", error_type=type(error).__name__, error=str(error), retry=False)
            raise
        finally:
            port.close()


if __name__ == "__main__":
    raise SystemExit("Import prepare(), review its result, then call install() once")
