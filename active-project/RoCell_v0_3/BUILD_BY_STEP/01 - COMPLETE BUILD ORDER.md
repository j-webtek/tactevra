# RoCell RC03 — Complete Build Order

Follow these folders in numeric order. Step 00 produces and accepts the printed parts; Steps 01-15 assemble and prove the cell. Never skip a LOCKED state, HOLD, or STOP condition.

**Current physical state:** UNRELEASED. Digital completion does not itself authorize physical release.

**Current sequence status:** 0/16 steps COMPLETE; Step 00 is the first non-complete step and is **HOLD**.

**Active build ID:** `2026-09-01_CELL-A`. Set it before recording any evidence.

Safe path: choose routes and one build ID → measure real hardware → print diagnostics → record results → regenerate and validate → print only READY jobs → inspect and kit → assemble Steps 01-15 in order.

Read [how to save measurements and photos](<02 - HOW TO SAVE MEASUREMENTS AND PHOTOS.md>) and [part names and technical terms](<03 - PART NAMES AND TECHNICAL TERMS.md>) before beginning.

## Step 00 — Measure Hardware and Print Approved Parts

**Goal:** Measure the real hardware, qualify each exact material/profile, print only released jobs, and stage accepted parts before touching the finished board.

**Done when:** All required coupons, first articles, production parts, hardware kits, and native QIDI Studio records are accepted and traceable.

**Step-00 qualification/production STL copies:** 32; use only through a READY job.

Open: [00 — Start Here](<00 - Measure Hardware and Print Approved Parts/00 - START HERE.md>)

> **STOP:** Do not fabricate the board or install a station while any required core job is WAITING, any first article is unaccepted, any actual-device measurement is missing, or any independently selected coupon value is not represented by its dedicated CAD parameter.

## Step 01 — Seal Mark and Drill the Board

**Goal:** Create the flat, sealed, accurately indexed structural board using only a 1:1 paper template, hand drill, guides, and depth stops.

**Done when:** A cured 610 x 457 x 18 mm board with four blind locator interfaces and nine qualified M4 anchor interfaces, all inspected and labeled.

**Traceability-only STL copies:** 12; do not print during this assembly step.

Open: [01 — Start Here](<01 - Seal Mark and Drill the Board/00 - START HERE.md>)

> **STOP:** Stop before center transfer or drilling if the board misses any released cut-size, thickness, opposite-edge, diagonal, flatness, or bow limit; any X/Y scale control is wrong; a Letter tile is butted instead of overlapped by 12 mm; registration or edge checks disagree; a station first article is unaccepted; a locator cannot meet both 15.00 +/- 0.20 mm depth and 2.00 mm minimum floor; or any anchor lacks a completed qualified FASTENER_MAP row and scrap-board proof.

## Step 02 — Reinforce Board and Clamp Robot Arm

**Goal:** Spread the factory RoArm clamp load with measured precut metal while keeping the factory clamp as the load-bearing interface.

**Done when:** The board remains flat and stable under the factory clamp, with reinforcement, feet, anchors, and motion volume clear of one another.

**STL requirement:** none for this step.

Open: [02 — Start Here](<02 - Reinforce Board and Clamp Robot Arm/00 - START HERE.md>)

> **STOP:** The clamp illustration is schematic and there is no released plate CAD. Do not fabricate from the picture; use the measured physical clamp footprint and stop if the board bows or any anchor is obstructed.

## Step 03 — Install Left Keyboard Base

**Goal:** Establish the keyboard coordinate system from the left/master station's round and radial locator pair.

**Done when:** The left station is squarely seated on two pins and three board interfaces, with its padded slider captured, parked fully rearward, and not loading a keyboard.

**Traceability-only STL copies:** 6; do not print during this assembly step.

Open: [03 — Start Here](<03 - Install Left Keyboard Base/00 - START HERE.md>)

> **STOP:** Do not force either locator, omit the slider from the shared stack, or tighten the shared screw as a device clamp before the keyboard is loaded.

## Step 04 — Install Right Keyboard Base

**Goal:** Extend the keyboard support from the master seam without creating a second, conflicting locator system.

**Done when:** The right/slave station is seam-located, held by three relieved board interfaces, flush with the master, and free of rocking.

**Traceability-only STL copies:** 7; do not print during this assembly step.

Open: [04 — Start Here](<04 - Install Right Keyboard Base/00 - START HERE.md>)

> **STOP:** Do not drill or add right-side locator pins. If the seam does not seat by hand, remove the slave and find the interference instead of pulling it together with screws.

## Step 05 — Place and Secure Keyboard

**Goal:** Seat the keyboard directly on the finished board and use the two guided sliders only for gentle retention.

**Done when:** The keyboard rests without rock or case distortion, both pads touch gently, and the cable remains clear.

**Traceability-only STL copies:** 3; do not print during this assembly step.

Open: [05 — Start Here](<05 - Place and Secure Keyboard/00 - START HERE.md>)

> **STOP:** The sliders are retainers, not force clamps. Stop immediately if the keyboard bows, a foot lifts, a cable is pinched, or either slider binds.

## Step 06 — Install Phone and Tool Station

**Goal:** Establish the phone/TCP coordinate system from its round and radial locator pair before the shared service rail is added.

**Done when:** The combined station is seated on two pins with only the TCP-side retainer installed; both rail-side interfaces remain open.

**Traceability-only STL copies:** 7; do not print during this assembly step.

Open: [06 — Start Here](<06 - Install Phone and Tool Station/00 - START HERE.md>)

> **STOP:** Do not install either rail-side board screw before the rail is fully seated. Do not heat-set inserts while the station is mounted on the finished board.

## Step 07 — Fit Phone Rail and Tool Cartridge

**Goal:** Locate the replaceable phone rail on its keys and place the keyed TCP cartridge before any shared or cartridge fastener is installed.

**Done when:** The rail lies flat on both keys and the cartridge is fully seated in its only valid orientation, with all holes aligned.

**Traceability-only STL copies:** 11; do not print during this assembly step.

Open: [07 — Start Here](<07 - Fit Phone Rail and Tool Cartridge/00 - START HERE.md>)

> **STOP:** Do not install shared rail screws or cartridge screws until both parts sit fully flush by hand. Never pull a misaligned part into place with hardware.

## Step 08 — Secure Phone Rail and Tool Cartridge

**Goal:** Lock the already seated rail and cartridge with the correct shared board, clamp-nut, and TCP fastener sequence.

**Done when:** All three station anchors, both clamp nuts, and both TCP screws are installed without lifting the rail or distorting the cartridge datum.

**Traceability-only STL copies:** 3; do not print during this assembly step.

Open: [08 — Start Here](<08 - Secure Phone Rail and Tool Cartridge/00 - START HERE.md>)

> **STOP:** Stop if a shared M4 stack lifts the rail, a clamp nut spins or cracks its tower, or an M3 screw changes cartridge height or flushness.

## Step 09 — Place Phone and Route USB Cable

**Goal:** Seat the measured phone/case, retain the USB lead with a relaxed bend, and advance only accepted soft clamp tips.

**Done when:** The phone is repeatably seated, the USB connector is unstressed, the cable exits forward through the saddle, and the soft tips touch safe case regions.

**Traceability-only STL copies:** 12; do not print during this assembly step.

Open: [09 — Start Here](<09 - Place Phone and Route USB Cable/00 - START HERE.md>)

> **STOP:** Stop if the connector carries load, the tie changes the bend radius, a tip approaches glass or a side feature, or clamp pressure shifts the phone.

## Step 10 — Check Phone Clearances

**Goal:** Prove the actual clamp and cable positions clear the screen edge, camera bump, side buttons, and USB connector envelope.

**Done when:** Measured keepout margins are recorded for the real phone/case, and both clamp axes and the cable route remain outside all no-go zones.

**Traceability-only STL copies:** 3; do not print during this assembly step.

Open: [10 — Start Here](<10 - Check Phone Clearances/00 - START HERE.md>)

> **STOP:** The red regions in the illustration are not released dimensions. Stop and revise the measured clamp centers or cable route if any actual feature lacks a positive recorded margin.

## Step 11 — Mark AprilTag Locations

**Goal:** Use the verified paper template only to transfer six centers and orientation marks onto the cured board.

**Done when:** All six tag centers and +Y/rear orientation marks are visible on the board, and all paper has been removed before adhesive work.

**Traceability-only STL copies:** 1; do not print during this assembly step.

Open: [11 — Start Here](<11 - Mark AprilTag Locations/00 - START HERE.md>)

> **STOP:** Do not glue through the paper. Stop if the guide route/path/hash differs from Step 00, either scale bar is wrong, a Letter tile uses pages 1-3 or is butted instead of overlapped by 12 mm with matching IDs, the full-size page is cropped/scaled, the template is stretched, FRONT/+Y is ambiguous, or any transferred center cannot be reconciled to the coordinate CSV.

## Step 12 — Attach and Measure AprilTags

**Goal:** Apply IDs 0-5 directly to the cured board with full-surface matte adhesive and measure their installed optical geometry.

**Done when:** Six correctly oriented tags are flat and physically measured, and a measured-installation runtime map is generated for Step 13; the application frame is removed and stored.

**Traceability-only STL copies:** 1; do not print during this assembly step.

Open: [12 — Start Here](<12 - Attach and Measure AprilTags/00 - START HERE.md>)

> **STOP:** Stop if a tile is glossy, scaled, damaged, rotated, misidentified, only spot-taped, or outside placement limits. Do not leave the printed application frame on the board.

## Step 13 — Mount and Calibrate Camera

**Goal:** Receive, measure, install, calibrate, and qualify the Arducam B0477 on the selected independent commercial floor tripod while preserving zero motion and contact authority.

**Done when:** The hash-bound tripod intake contains the received support identity, mount stack, support envelope, installed pose, stability results, visibility results, collision screen, and wrong-model checks; the camera is calibrated at locked settings and remains outside approved swept volumes.

**Traceability-only STL copies:** 6; do not print during this assembly step.

Open: [13 — Start Here](<13 - Mount and Calibrate Camera/00 - START HERE.md>)

> **STOP:** Stop before installation if the received tripod, B0477, adapter, thread, or support geometry is unidentified. Stop before robot power or motion while any intake measurement is missing, any authority field is false, any collision screen is incomplete, or any consequential fault fails to block descent.

## Step 14 — Assemble and Test Spring-Loaded Tool

**Goal:** Build and qualify every selected contact-tool route around the shared compliant body, one configuration at a time, and verify travel, force, retention, function, and TCP repeatability.

**Done when:** Each selected rod/TPU and/or stylus configuration has smooth controlled travel, returns freely, remains retained, functions correctly, and has a recorded calibrated TCP.

**Traceability-only STL copies:** 13; do not print during this assembly step.

Open: [14 — Start Here](<14 - Assemble and Test Spring-Loaded Tool/00 - START HERE.md>)

> **STOP:** This is a contact tool, not a hard stop. Stop if travel binds, the spring coil-binds, the cap distorts, the adapter slips, or the selected contact route is not explicitly recorded.

## Step 15 — Final Safety Test and Release

**Goal:** Prove the assembled cell mechanically, visually, and functionally before any automatic contact with the keyboard or phone.

**Done when:** Every acceptance gate has measured evidence, the cell passes empty motion and controlled first contact, and a responsible person signs the physical release decision.

**STL requirement:** none for this step.

Open: [15 — Start Here](<15 - Final Safety Test and Release/00 - START HERE.md>)

> **STOP:** Digital PASS is not physical release. Do not enable automatic device contact until every measured gate is in limit, evidence is archived, the E-stop works, and the physical release decision is signed.

