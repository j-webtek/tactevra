# Received arm firmware history

Operator: Jack. Recorded from the current conversation on 2026-09-12.

Operator statement: “unchanged since delivery, proceed with best next steps”.

Applies to the operator-identified Waveshare RoArm-M3 Pro in this project.
Previously reported controller MAC: FC:E8:C0:F8:D5:38. These identifiers are
historical reports, not new device observations from this recording.

Interpretation at the time: the operator had not flashed or modified the delivered
firmware. A later 2026-10-24 verified readback now records the installed full-flash
and app0 hashes below. The historical statement alone inferred no factory image
hash, current USB connection, power state or calibration.

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

## 2026-10-24 verified Stage A readback

With external 12 V motor power removed, the arm supported and stationary, and
USB retained, the operator authorized exactly one COM4 bootloader session using
esptool 4.6's temporary RAM helper. The expected controller was verified as an
ESP32-D0WD-V3 revision 3.1 with MAC `FC:E8:C0:F8:D5:38`, flash ID `0x164020`,
4 MB flash, disabled flash encryption and disabled secure boot.

Two independent 4,194,304-byte reads completed in the same bounded session and
matched at SHA-256
`c800a24409d4e57f65d431b8341c872a8684144a9ed1c7a4af9c96e79a7d4cec`.
There was no retry, persistent write, erase, motion command, reset or application
restart. The raw copies remain only in the restricted local backup directory; the
repository retains sanitized metadata at
`software/runs/operational-checkpoints/issue190-stage-a-readback-verified-20261024.json`.

Offline parsing confirmed the installed NVS, OTA, dual-app, SPIFFS and coredump
layout documented in the native diagnostics playbook. Pinned esptool 4.6
validated the installed bootloader and app0 checksums and appended hashes. Exact
bootloader image SHA-256 is
`b22f373e6194a62505034bbcd2828ab5eaa0fba62f3e4198fb7ae677c1d2f6f7`;
exact app0 image SHA-256 is
`1b0589fa323a2714777f5c70453eeec6daa94bd8c92a481701689da82ce93fdc`.
App0 identifies version `769c168`, project `arduino-lib-builder`, IDF
`v5.1.4-972-g632e0c2a9f-dirty`, built `Oct 22 2024 21:30:11`. This establishes
the installed snapshot and recovery evidence; it does not by itself authorize or
prove deployment compatibility, runtime behavior, calibration or motion safety.
