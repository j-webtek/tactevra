# Native diagnostics: backup and first-run handoff

Status: two exact Stage A sessions authorized on 2026-10-22 were consumed and
failed closed. The first stopped at flash identification because the direct script
omitted the volatile default-SPI attach required by esptool 4.6's ROM-only path.
The corrected second session confirmed the expected ESP32 and MAC, 4 MB flash,
disabled flash encryption and disabled secure boot, then stopped during the first
ROM read on a transport CRC/checksum error. Neither session created a flash dump
or performed a retry, stub upload, persistent device write, erase, application
start or reset-on-exit. Another session requires fresh setup confirmation and
explicit approval. A RAM-helper session also requires approval for its temporary
code upload/execution. Firmware deployment and configuration/provisioning remain
separately gated.

## Current evidence

- The 2026-10-22 preflight PnP and Win32 serial inventories both reported the
  Silicon Labs CP210x USB to UART Bridge on COM4, VID 10C4 / PID EA60, unit serial
  `52E4E1E8337FEF119E92181CEDD322A4`, with status OK. The same endpoint remained
  enumerated after the stopped attempt. Adapter identity is not proof of installed
  firmware compatibility.
- Candidate FQBN: `esp32:esp32:esp32:PartitionScheme=huge_app,PSRAM=enabled`.
- Candidate app SHA-256:
  `b1cc73c97c7dadb626bd42701a547a3f2e275534d31ec859d864f53618ffb4db`
  (`configured-diagnostic-candidate-r2`, target-readback mismatch stop fix).
- esptool 4.6 `image_info` on the preceding local candidate app reports ESP32, five segments,
  valid checksum and validation hash. File length is 1087328 bytes. This is an
  offline image check, not installed-device verification.
- Candidate partition CSV: NVS 0x9000/0x5000; OTA data 0xe000/0x2000;
  app0 0x10000/0x300000; filesystem 0x310000/0xe0000;
  coredump 0x3f0000/0x10000. This spans 4 MB and is NOT the confirmed device layout.

## Stage A — separately authorized backup-only session

Both 2026-10-22 approvals were consumed by the retained failed attempts.
Bootloader entry resets/intercepts the controller and is not an ordinary feedback query.
Before another attempt, establish the Stage A setup and obtain a new exact
one-session approval. No firmware/configuration write or erase is implied.

1. Operator supports the arm against falling, removes external motor power, and
   leaves USB controller power connected. Do not force loaded joints. Keep the
   work area clear. Do not restore motor power during backup/identity inspection.
2. Re-enumerate COM4 and its PnP identity immediately before use. Do not silently
   select another COM port. Ensure no other process owns the controller connection.
3. Use the pinned esptool 4.6 tool at a conservative 115200 baud with finite
   connection attempts. Explicitly use `--after no_reset`; do not allow an implicit
   application reboot. Initially prefer ROM-only `--no-stub`. If that cannot read
   this chip's flash, stop and review RAM-helper requirements rather than silently
   loading code or changing persistent settings.
   For ESP32 ROM-only access, enable the default SPI flash connection before flash
   identification, matching esptool 4.6's reviewed `--no-stub` execution path.
4. Read chip/MAC and flash identification. Compare the controller MAC against the
   recorded FC:E8:C0:F8:D5:38, accounting explicitly for documented interface MAC
   differences rather than assuming an unrelated device is the arm. Record actual
   chip model/revision/flash size and any security/readout restriction.
5. Read the whole flash into a fresh restricted backup folder, never overwriting
   an earlier file. The pinned tool's `read_flash` supports address 0 and size ALL;
   no size guessed from the candidate is needed. Repeat the read without starting
   the application and require matching length and SHA-256 for the two copies.
6. Leave the controller in bootloader/USB-only state and report the result. Do not
   restore the application, reset, flash, erase, modify eFuses, or provision files
   as an automatic next step.

### Retained 2026-10-22 stopped attempt

- Local sanitized checkpoint (under the intentionally untracked run directory):
  `software/runs/operational-checkpoints/issue190-stage-a-readback-20261022.json`
- Tooling: isolated esptool 4.6 with pyserial 3.5, 115200 baud, one connection
  attempt, direct ESP32 ROM loader, no flasher stub.
- Result: ROM connection progressed through the ESP32 magic check and reached
  flash identification. The capacity byte was `0xff`, so the script stopped before
  allocating or reading a flash image.
- Cause established offline: the direct script omitted esptool 4.6's required
  volatile `flash_spi_attach(0)` step for ROM-only access.
- Effects: one bootloader-entry session; zero firmware bytes read; zero persistent
  controller writes; zero erases; zero motion commands; zero retries; port closed
  without reset or application restart.

### Retained 2026-10-22 corrected ROM-only attempt

- Local sanitized checkpoint (under the intentionally untracked run directory):
  `software/runs/operational-checkpoints/issue190-stage-a-readback-attempt-2-20261022.json`
- Tooling: esptool 4.6 with pyserial 3.5, 115200 baud, one connection attempt,
  direct ESP32 ROM loader, volatile default-SPI attach, no flasher stub.
- Verified identity: ESP32-D0WD-V3 revision 3.1; MAC
  `FC:E8:C0:F8:D5:38`; flash ID `0x164020`; 4 MB flash; flash encryption
  disabled; secure boot disabled.
- Result: the first 4 MB read stopped after about 7 minutes 49 seconds with
  `CRC or checksum was invalid`. No complete flash buffer was returned, so no dump
  file or installed-firmware SHA-256 was produced and the second read did not start.
- Effects: one bootloader-entry session; zero published firmware bytes; zero
  persistent controller writes; zero erases; zero motion commands; zero retries;
  port closed without reset or application restart.
- Next reviewed method: esptool's volatile RAM flasher helper can provide the
  supported block-read protocol. Uploading and executing it is a new physical
  effect and requires a fresh exact approval; it must still perform no persistent
  flash/eFuse write and no reset/application restart afterward.

Full flash may contain Wi-Fi credentials and private configuration. Keep raw dumps
out of ordinary wizard diagnostic exports. Export only nonsecret metadata, hashes
and the reviewed partition summary; never print credential-containing regions.

## Stage B — offline compatibility/recovery review

1. Parse the retained partition table and identify the actual app/filesystem/NVS
   ranges. Compare against the candidate; do not assume the CSV above is installed.
2. Establish flash/security settings, chip revision constraints and PSRAM support
   from authoritative evidence. A CP210x device name proves none of these.
3. Inspect the backed-up application identity where possible. Recheck candidate
   hashes and retain the original bootloader, partition table, NVS and filesystem.
4. Prefer a compatible app-only deployment that preserves existing layout/data.
   If the layout or board build is incompatible, rebuild and review; do not flash
   the merged binary just because it compiled.
5. Define recovery using the verified original backup and documented offsets. A
   backup hash is not a tested recovery procedure; explicitly label that gap.
6. Plan private random-key provisioning and reviewed policy placement while
   preserving existing filesystem content. No automatic filesystem formatting.

## Stage C — separate deployment approval, then USB-only verification

Present the exact image hash, offsets, configuration changes and recovery steps
for explicit approval. Backup approval does not authorize this stage. After an
approved deployment, verify boot/status/configuration and memory behavior without
motor power. No motion command is needed to prove discovery and file loading.

## Stage D — one instrumented physical command

After power/setup admission, acquire current baseline evidence and freeze one
bounded elbow target. Use the reviewed configuration, fresh boot challenge and
assigned export root. Persist/verify the plan and consume the challenge claim
before the one-use POST. Never resend after a missing reply.

Wait for the finite capture to finish, retrieve and independently assess the
receipt, actual target conversion/write result, target-register read and fresh
position samples. Export/replay all links. On invalid evidence, uncertain delivery
or export failure, stop the affected sequence and investigate retained data.

Only then select a reverse leg based on evidence. A new approved attempt/session
must not be implemented by automatic reboot or deletion of the prior claim.
Repeatable bidirectional cycles and ghost-key sequences remain future work;
camera/contact and physical stylus accuracy remain deferred.
