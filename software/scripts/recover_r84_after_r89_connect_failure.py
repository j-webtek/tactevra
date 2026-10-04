"""One startup reset after the exact pre-write r89 ROM sync failure; no flash or motion."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from rocell.application.first_motion_contract import canonical
from rocell.application.physical_onboarding_durability import publish_reservation_bytes
from rocell.application.wizard_diagnostic_export import WizardDiagnosticExporter, verify_export


JOURNAL_SHA = "3b4fdaddfbb3ea427d062a2e378f9c9eaa4e47ef2de16e2a0b5f5137b865f33a"
APP_SHA = "89c0d91334ab4362d392a3e3e66433c216d7e1740842dbba1b87881b722236b0"
RELEASE_SHA = "653729599a9ba29baed5095b3ed156810b38396065a0b6a3a06fe6c7dd74ab1a"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--one-recovery-startup", action="store_true", required=True)
    parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    exports = root / "runs/wizard-exports"
    journal = root / "private-backups/controller-20260918-session1/app-r89-deployment-events.jsonl"
    raw = journal.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    expected = dict(stage="RESERVED", app_sha256=APP_SHA, offset=65536,
                    bytes=1061360, release_sha256=RELEASE_SHA)
    if (hashlib.sha256(raw).hexdigest() != JOURNAL_SHA or len(rows) != 2
            or rows[0] != expected or rows[1].get("stage") != "STOPPED"
            or rows[1].get("retry") is not False
            or "getting no sync reply" not in rows[1].get("error", "")):
        raise ValueError("Not the pinned pre-write r89 failure; no reset")

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

    matches = [port for port in comports() if port.device == "COM7"
               and port.vid == 0x10C4 and port.pid == 0xEA60
               and port.serial_number == "52E4E1E8337FEF119E92181CEDD322A4"]
    if len(matches) != 1:
        raise ValueError("Expected USB adapter not identified")

    import esptool
    from esptool.reset import HardReset

    if esptool.__version__ != "4.6" or not Path(esptool.__file__).resolve().is_relative_to(pinned.resolve()):
        raise ValueError("Unexpected reset implementation")

    exporter = WizardDiagnosticExporter(exports)
    exporter.prepare(create=True)
    claim = "r89-prewrite-recovery-r84-startup.json"
    if (exports / claim).exists():
        raise ValueError("Recovery startup already attempted")
    report = dict(schema="rocell.r89_prewrite_recovery_r84_startup.v1",
                  status="PREPARED", failed_journal_sha256=JOURNAL_SHA,
                  servo_command_sent=False, flash_written=False,
                  settings_written=False, retry_allowed=False)

    def save() -> dict:
        result = exporter.export({"mode": "r89-prewrite-recovery-r84-startup"}, [],
                                 attachments={"recovery-startup.json": canonical(report)})
        if not verify_export(Path(result["path"]))["valid"]:
            raise ValueError("Recovery export failed")
        return result

    intent = save()
    publish_reservation_bytes(exports, claim,
                              canonical(dict(intent_export=Path(intent["path"]).name,
                                             authorized=True, retry_allowed=False)),
                              maximum_bytes=2048)
    port = serial.Serial(port=None, baudrate=115200, timeout=2, write_timeout=2)
    port.dtr = False
    port.rts = False
    port.port = "COM7"
    report["status"] = "RESET_UNCERTAIN"
    try:
        port.open()
        HardReset(port)()
        report["status"] = "ONE_RESET_SENT_STARTUP_NOT_YET_VERIFIED"
    finally:
        try:
            port.close()
        finally:
            result = save()
    print(canonical(dict(export_path=result["path"], status=report["status"])).decode())


if __name__ == "__main__":
    main()
