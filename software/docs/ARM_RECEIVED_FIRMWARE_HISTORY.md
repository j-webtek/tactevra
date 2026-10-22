# Received arm firmware history

Operator: Jack. Recorded from the current conversation on 2026-09-12.

Operator statement: “unchanged since delivery, proceed with best next steps”.

Applies to the operator-identified Waveshare RoArm-M3 Pro in this project.
Previously reported controller MAC: FC:E8:C0:F8:D5:38. These identifiers are
historical reports, not new device observations from this recording.

Interpretation: the operator has not flashed or modified the delivered firmware.
Installed firmware version and binary SHA-256 remain unknown; no factory image
hash, current USB connection, power state or calibration is inferred.

This resolves the outstanding firmware-change-history question. The initial
compatibility basis is the operator's report plus Waveshare's documented T105
feedback semantics, not verification of the installed binary. Separate current
setup confirmation and completion of the supervised native integration remain
necessary before one feedback query. This record authorizes no motion.

## 2026-10-22 Stage A readback attempt

The operator confirmed USB-only Stage A conditions and authorized exactly one
ROM-bootloader session on COM4. The expected CP210x endpoint was present and the
session reached ESP32 flash identification, but returned capacity code `0xff`.
The attempt stopped before any flash bytes were read. It performed no retry,
flasher-stub upload, persistent device write, erase, motion command, reset-on-exit
or application restart.

Offline inspection found that the direct one-use script omitted esptool 4.6's
volatile default-SPI attach command required by its ROM-only path. The corrected
procedure is prepared but has not been executed. The installed firmware version
and binary SHA-256 therefore remain unknown. See the retained local sanitized
checkpoint at
`software/runs/operational-checkpoints/issue190-stage-a-readback-20261022.json`;
the run directory is intentionally excluded from version control.
A new attempt requires fresh Stage A setup confirmation and exact one-session
approval; the consumed authorization must not be reused.

The operator subsequently granted one corrected ROM-only session. It verified an
ESP32-D0WD-V3 revision 3.1 with the expected MAC, flash ID `0x164020`, 4 MB flash,
disabled flash encryption and disabled secure boot. The first full read stopped on
a ROM transport CRC/checksum error before returning a complete buffer; no dump or
installed binary hash was produced, no retry occurred and the second read did not
start. The installed firmware SHA-256 therefore remains unknown. The next reviewed
method uses esptool's temporary RAM helper and requires a new exact authorization
because it uploads and executes volatile code.
