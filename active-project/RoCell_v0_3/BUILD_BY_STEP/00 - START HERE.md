# RoCell RC03 — Start Here

This is the operator-facing sequence for `RC03-INT-R1`. The CAD, configuration, ledgers, drawings, and print controls remain canonical in their original project folders. Each step contains direct links/hashes plus hash-verified STL convenience copies so operators can work by step without creating a second manufacturing master.

**Physical state:** `UNRELEASED`  
**Active build ID:** `2026-09-01_CELL-A`  
**Print readiness:** 5 READY / 15 WAITING / 4 NOT_SELECTED  
**Package definition hash:** `5f18f598920dc04d0066e1a233f9f313ae48121094868790a4489995069d5313`  
**Canonical snapshot hash:** `3a3d1894c12af5f94fa453250f0ddb884f3cdda1febb53707d1a1395cb7f9adf`  
**Selected routes:** phone stylus=True, keyboard rod=True, fixed-mast camera fallback=False (selection is not release)

## How to use this folder

1. Read [the complete build order](<01 - COMPLETE BUILD ORDER.md>), then open Step 00 as the first non-complete step (a new build starts at Step 00).
2. In each step, open `00 - START HERE.md` and follow its numbered file map.
3. Follow [how to save measurements and photos](<02 - HOW TO SAVE MEASUREMENTS AND PHOTOS.md>), set one active build ID, and initialize only a step that is `READY TO START`.
4. Use the exact usage label in each step's `03 - STL MODELS` folder. Canonical project-level `stl/` files remain authoritative.
5. Open manufacturing controls only through `99 - TECHNICAL RECORDS - DO NOT EDIT/OPEN CONTROLLED FILES.md`; do not create editable forks.
6. Print jobs are produced only in Step 00. Later assembly steps consume accepted, labeled parts and include STL/job files for recovery and traceability.
7. Record raw measurements and original evidence. A checkmark without an in-limit value is not PASS.
8. Use [part names and technical terms](<03 - PART NAMES AND TECHNICAL TERMS.md>) whenever a term is unfamiliar.
9. If a source or local STL hash changes, regenerate and revalidate before continuing.

## Persistent orientation

- Origin: front-left corner of the finished board top.
- +X is right, +Y is rear/toward the arm, and +Z is up.
- Blue denotes locators/controlled geometry, orange denotes hardware/action, and red denotes STOP/no-go conditions.

## Sequence dashboard

| Step | State | Title | Prerequisites | Print-job references | Next |
| --- | --- | --- | --- | --- | --- |
| [00](<00 - Measure Hardware and Print Approved Parts/00 - START HERE.md>) | **HOLD** | Measure Hardware and Print Approved Parts | — | 00A, 00B, 00C, 00D, 00E, 00F, 01, 02, 03A, 03B, 03C1, 03C2, 03C3, 03D, 04A, 04B, 04C, 05A, 05B, 05C, 05D, 06, 07A, 07B | 01 |
| [01](<01 - Seal Mark and Drill the Board/00 - START HERE.md>) | **LOCKED** | Seal Mark and Drill the Board | 00 | 00A, 00B, 01, 02, 03A | 02 |
| [02](<02 - Reinforce Board and Clamp Robot Arm/00 - START HERE.md>) | **LOCKED** | Reinforce Board and Clamp Robot Arm | 01 | — | 03 |
| [03](<03 - Install Left Keyboard Base/00 - START HERE.md>) | **LOCKED** | Install Left Keyboard Base | 02 | 00A, 01, 03B | 04 |
| [04](<04 - Install Right Keyboard Base/00 - START HERE.md>) | **LOCKED** | Install Right Keyboard Base | 03 | 00A, 01, 02, 03B | 05 |
| [05](<05 - Place and Secure Keyboard/00 - START HERE.md>) | **LOCKED** | Place and Secure Keyboard | 04 | 01, 02, 03B | 06 |
| [06](<06 - Install Phone and Tool Station/00 - START HERE.md>) | **LOCKED** | Install Phone and Tool Station | 05 | 00B, 03A | 07 |
| [07](<07 - Fit Phone Rail and Tool Cartridge/00 - START HERE.md>) | **LOCKED** | Fit Phone Rail and Tool Cartridge | 06 | 00B, 00F, 03A, 03C1, 03D | 08 |
| [08](<08 - Secure Phone Rail and Tool Cartridge/00 - START HERE.md>) | **LOCKED** | Secure Phone Rail and Tool Cartridge | 07 | 03A, 03C1, 03D | 09 |
| [09](<09 - Place Phone and Route USB Cable/00 - START HERE.md>) | **LOCKED** | Place Phone and Route USB Cable | 08 | 00B, 00E, 03A, 03C1, 05A, 05B | 10 |
| [10](<10 - Check Phone Clearances/00 - START HERE.md>) | **LOCKED** | Check Phone Clearances | 09 | 03A, 03C1, 05A, 05B | 11 |
| [11](<11 - Mark AprilTag Locations/00 - START HERE.md>) | **LOCKED** | Mark AprilTag Locations | 10 | 03C2 | 12 |
| [12](<12 - Attach and Measure AprilTags/00 - START HERE.md>) | **LOCKED** | Attach and Measure AprilTags | 11 | 03C2 | 13 |
| [13](<13 - Mount and Calibrate Camera/00 - START HERE.md>) | **LOCKED** | Mount and Calibrate Camera | 12 | 00E | 14 |
| [14](<14 - Assemble and Test Spring-Loaded Tool/00 - START HERE.md>) | **LOCKED** | Assemble and Test Spring-Loaded Tool | 13 | 00C, 00D, 00E, 04A, 04B, 04C, 05C, 05D | 15 |
| [15](<15 - Final Safety Test and Release/00 - START HERE.md>) | **LOCKED** | Final Safety Test and Release | 14 | — | archive |

## Canonical controls

- [Illustrated assembly guide](<../output/pdf/RC03_ILLUSTRATED_ASSEMBLY_GUIDE.pdf>)
- [Detailed assembly manual](<../ASSEMBLY_MANUAL.pdf>)
- [Print readiness](<../PRINT_READINESS.md>)
- [Build tracker](<../BUILD_TRACKER.md>)
- [BOM](<../BOM.csv>)
- [Fastener map](<../FASTENER_MAP.csv>)
- [Job kits](<../JOB_KITS.csv>)

## Open decisions and controlled change triggers

- Supply and measure the exact arm-mounted camera/interface specification before Step 13; the separate fixed mast is a selected but unqualified fallback only.
- Complete the blank selected-length, anchor-type, and final-board-bore fields in FASTENER_MAP.csv from physical cutoff tests before final board drilling.
- Select and document a rated E-stop implementation and board-to-bench anti-shift method before Step 15 commissioning.
- Transfer every accepted coupon value through its dedicated key in `user_overrides.example.json`, then regenerate and prove the geometry-parameter mapping before production.
- Store diagnostic native QIDI projects in the build-ID evidence folder; the canonical `--qidi-job` gate records non-diagnostic release jobs only.

`tmp/` is scratch/QA output and is never build evidence.
