"""One-use r84→r89 app-only install; no provisioning or motion request.

Preflight never opens a port. Authorized mode performs one write, full app
readback, protected-region comparison and one startup reset. No retry.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from rocell.application.product_ghost_export_review import _read
from rocell.application.reviewed_hover_release_identity import verify_release_pair
from rocell.application.observed_pose_installation import review_observed_installation
from rocell.providers.windows.diagnostic_image_store import load_image
from rocell.application.wizard_diagnostic_export import verify_export


R89_EXPORT = "wizard-20260925T034728622941Z-f15a2f14fa5847df8340a884d9d53856"
R89_COMPILE = "wizard-20260925T034619289604Z-68658f0139aa430793f4b8ba5c5345b4"
R84_SHA = "d1e141a9b73d0b104ffb2ac1b07cae213c1321300a2251bd8cd3dcf0596f97cd"
R89_SHA = "89c0d91334ab4362d392a3e3e66433c216d7e1740842dbba1b87881b722236b0"
FS_SHA = "45320bab56ec1d8e889078a50e2aa0ef79d4d65c59e5dcb89c7a7880f08e7267"
BACKUP_SHA = "d9e3de5cf3738b18144697095534ec9a33e531a6cd5062f68b85b5a29f6df2b9"
PORT = "COM7"
USB_SERIAL = "52E4E1E8337FEF119E92181CEDD322A4"
MAC = "fc:e8:c0:f8:d5:38"
FAILED_JOURNAL_SHA = "3b4fdaddfbb3ea427d062a2e378f9c9eaa4e47ef2de16e2a0b5f5137b865f33a"
RECOVERY_EXPORT = "wizard-20260925T040058555862Z-6e5ccccf721446f78a4dd4e10771cd45"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preflight(root: Path, *, second_attempt: bool = False) -> dict:
    root = Path(root).resolve()
    exports = root / "runs/wizard-exports"
    record, _ = _read(exports, R89_EXPORT, "attachment-r89-reviewed-hover-release-review.json")
    compiled, _ = _read(exports, R89_COMPILE, "attachment-compile-review.json")
    image_path = (root / ".firmware-tools/build-configured-diagnostic-candidate-r89--default-4mb-no-psram"
                  / "RoArm-M3_example.ino.bin")
    prior_path = (root / ".firmware-tools/build-configured-diagnostic-candidate-r84--default-4mb-no-psram"
                  / "RoArm-M3_example.ino.bin")
    image, prior = image_path.read_bytes(), prior_path.read_bytes()
    if (_sha(image) != R89_SHA or _sha(prior) != R84_SHA or
            len(image) != 1061360 or len(prior) != 1204880):
        raise ValueError("Pinned app or predecessor differs")
    source_bytes = {name: (root / name).read_bytes() for name in record["source_hashes"]}
    checked = verify_release_pair(record, compile_report=compiled,
                                  source_bytes=source_bytes, app_image=image)
    if (checked["app_sha256"] != R89_SHA or
            record["deployment_authorized"] is not False or
            compiled["artifact_hashes"].get("RoArm-M3_example.ino.bin") != R89_SHA):
        raise ValueError("r89 release review differs")
    private = root / "private-backups/controller-20260918-session1"
    backup_a = (private / "flash-pair-a.bin").read_bytes()
    backup_b = (private / "flash-pair-b.bin").read_bytes()
    if (len(backup_a) != 0x400000 or _sha(backup_a) != BACKUP_SHA or
            backup_b != backup_a):
        raise ValueError("Original full-flash backup differs")
    review_observed_installation(root,
        stage_export="wizard-20260919T145415048349Z-1324830e574a4e9294c0302ecce85e39",
        installation_export="wizard-20260919T151102041680Z-273348d615584d5595ec7dcf92acd265")
    filesystem = load_image(private / "observed-pose-plus10-candidate.dpapi")
    if len(filesystem) != 0x160000 or _sha(filesystem) != FS_SHA:
        raise ValueError("Reviewed filesystem/settings snapshot differs")
    journal = private / "app-r89-deployment-events.jsonl"
    if second_attempt:
        raw = journal.read_bytes()
        rows = [json.loads(line) for line in raw.splitlines()]
        expected = dict(stage="RESERVED", app_sha256=R89_SHA, offset=0x10000,
                        bytes=len(image), release_sha256=checked["release_sha256"])
        if (_sha(raw) != FAILED_JOURNAL_SHA or len(rows) != 2 or
                rows[0] != expected or rows[1].get("stage") != "STOPPED" or
                rows[1].get("retry") is not False or
                "getting no sync reply" not in rows[1].get("error", "")):
            raise ValueError("First attempt not the pinned pre-write failure")
        recovery = exports / RECOVERY_EXPORT
        if not verify_export(recovery)["valid"] or not (exports / "r89-prewrite-recovery-r84-startup.json").exists():
            raise ValueError("One-use recovery evidence missing")
        journal = private / "app-r89-attempt2-deployment-events.jsonl"
    if journal.exists():
        raise ValueError("r89 attempt already reserved; never retry automatically")
    return dict(image=image, prior=prior, image_path=image_path,
                partition_md5=hashlib.md5(backup_a[0x8000:0x8c00]).hexdigest(),
                filesystem_md5=hashlib.md5(filesystem).hexdigest(),
                journal=journal, release_sha256=checked["release_sha256"])


def install(root: Path, prepared: dict) -> None:
    # Enumerate before the first controller reset. No alternate port fallback.
    pinned = root / ".firmware-tools/esptool-api-4.6"
    if not pinned.is_dir():
        raise ValueError("Pinned firmware dependency directory is unavailable")
    sys.path.insert(0, str(pinned))
    import serial
    from serial.tools import list_ports
    if (serial.__version__ != "3.5"
            or not Path(serial.__file__).resolve().is_relative_to(pinned.resolve())
            or not Path(list_ports.__file__).resolve().is_relative_to(pinned.resolve())):
        raise ValueError("Unexpected pyserial implementation")
    from serial.tools.list_ports import comports
    matches = [item for item in comports() if item.device == PORT and
               item.vid == 0x10c4 and item.pid == 0xea60 and
               item.serial_number == USB_SERIAL]
    if len(matches) != 1:
        raise ValueError("Expected USB adapter not identified")
    import esptool
    from esptool import cmds, loader
    from deploy_reviewed_diagnostic_app import longer_reset_rom
    if esptool.__version__ != "4.6" or not Path(esptool.__file__).resolve().is_relative_to(pinned.resolve()):
        raise ValueError("Unexpected esptool implementation")
    loader.WRITE_BLOCK_ATTEMPTS = 1
    image = prepared["image"]
    with prepared["journal"].open("x", encoding="utf-8") as journal:
        def event(stage: str, **fields) -> None:
            row = dict(stage=stage, **fields)
            journal.write(json.dumps(row) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
            print(json.dumps(row), flush=True)

        event("RESERVED", app_sha256=R89_SHA, offset=0x10000,
              bytes=len(image), release_sha256=prepared["release_sha256"])
        port = serial.Serial(port=None, baudrate=115200, timeout=3, write_timeout=10)
        port.dtr = False
        port.rts = False
        port.port = PORT
        try:
            port.open()
            esp = longer_reset_rom(esptool, port)
            esp.connect("default_reset", attempts=1)
            mac = ":".join(f"{value:02x}" for value in esp.read_mac())
            if mac != MAC or esp.secure_download_mode or esp.stub_is_disabled or \
                    esp.get_secure_boot_enabled() or esp.get_flash_encryption_enabled():
                raise ValueError("Controller identity/security state differs")
            stub = esp.run_stub()
            if stub.flash_id() != 0x164020:
                raise ValueError("Unexpected flash identity")
            if (stub.flash_md5sum(0x10000, len(prepared["prior"])) !=
                    hashlib.md5(prepared["prior"]).hexdigest() or
                    stub.flash_md5sum(0x8000, 3072) != prepared["partition_md5"] or
                    stub.flash_md5sum(0x290000, 0x160000) != prepared["filesystem_md5"]):
                raise ValueError("Installed predecessor or protected region differs")
            protected = [(0, 0x10000), (0x150000, 0x2b0000)]
            before = [stub.flash_md5sum(start, size) for start, size in protected]
            event("IDENTITY_AND_PREWRITE_VERIFIED", mac=mac)
            stream = io.BytesIO(image)
            stream.name = str(prepared["image_path"])
            args = SimpleNamespace(addr_filename=[(0x10000, stream)],
                compress=True, no_compress=False, no_stub=False, force=False,
                encrypt=False, encrypt_files=None, erase_all=False, verify=False,
                ignore_flash_encryption_efuse_setting=False,
                flash_size="keep", flash_mode="keep", flash_freq="keep")
            event("WRITE_ATTEMPT_STARTED")
            cmds.write_flash(stub, args)
            readback = stub.read_flash(0x10000, len(image))
            if readback != image or _sha(readback) != R89_SHA:
                raise ValueError("Application readback mismatch")
            after = [stub.flash_md5sum(start, size) for start, size in protected]
            if before != after:
                raise ValueError("Protected region changed")
            event("FLASH_VERIFIED", app_sha256=_sha(readback),
                  protected_regions_unchanged=True)
            event("ONE_STARTUP_ATTEMPT")
            stub.hard_reset()
            event("STARTUP_RESET_SENT", application_health_verified=False)
        except BaseException as error:
            event("STOPPED", error_type=type(error).__name__, error=str(error), retry=False)
            raise
        finally:
            port.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--authorized-app-only-and-startup", action="store_true")
    mode.add_argument("--preflight-second-attempt", action="store_true")
    mode.add_argument("--authorized-second-attempt-app-only-and-startup", action="store_true")
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    second_attempt = (options.preflight_second_attempt or
                      options.authorized_second_attempt_app_only_and_startup)
    prepared = preflight(root, second_attempt=second_attempt)
    if options.preflight_only or options.preflight_second_attempt:
        print(json.dumps(dict(status="LOCAL_PREFLIGHT_VERIFIED", app_sha256=R89_SHA,
            predecessor_sha256=R84_SHA, release_sha256=prepared["release_sha256"],
            hardware_access=False, firmware_uploaded=False, journal_reserved=False,
            second_attempt=second_attempt)))
        return
    install(root, prepared)


if __name__ == "__main__":
    main()
