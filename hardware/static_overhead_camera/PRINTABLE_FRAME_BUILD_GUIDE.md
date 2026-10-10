# Printable camera portal — exact prototype build guide

> **SUPERSEDED — DO NOT PRINT OR ASSEMBLE:** The current Phase 1 direction uses
> an independent commercial floor tripod rather than this printed portal. This
> guide is retained as historical engineering evidence and does not define the
> active build. See the
> [tripod migration inventory](../../docs/TRIPOD_CAMERA_SUPPORT_MIGRATION_INVENTORY.md).

**Design:** `ROCELL-PRINTABLE-CAMERA-PORTAL-PROTOTYPE-003`  
**Rigid material:** QIDI ABS Rapido  
**Printer:** QIDI X-Plus 4, 0.4 mm nozzle  
**State:** historical validated digital prototype; superseded and not released for fabrication, installation, overhead use, or robot motion

This guide covers only the camera support load path: the two board/bench
anchors, uprights, crossbar, booms, carriage, camera cage, keeper, and safety
tether. The board is a locating and overturning interface; portal dead load is
carried by the two `120 x 120 mm` saddle feet into the same bench plane as the
board.

## Use these files

### Remaining frame print pack — 2026-09-16

**S1 saddle correction:** load the `GROUNDED_v2` left/right saddles, not their
old `WELDED_v1` files. See [replacement saddle instructions](cad/output/revisions/SADDLES_GROUNDED_v2/PRINT_THIS_REVISION.md).
Permanent feet ground the diagonal braces; the upright pocket is cleared of
brace intrusion. Hardware interfaces and the structural ABS settings remain
unchanged. Re-slice the replacement model and inspect remaining warnings.

Use the [system print pack start sheet](cad/output/revisions/SYSTEM_PRINT_PACK_v1/START_HERE.md)
for the remaining frame. It provides repaired copies of 16 ABS frame plates
and a four-object TPU **board-pad-only** plate, plus a separate held carriage.
Start with the repaired `08A-S1` left saddle. Original numbered plates below
are retained for provenance, not the preferred print queue.

The pack also documents the conditionally checked socket-head M5 alternative:
one M5 metal flat washer (10 mm OD, up to 1.2 mm thick) beneath each socket
head, specified flanged nuts retained, original lengths unchanged. There are
48 final M5 head washers. Native slice inspection and actual thread engagement
remain required. This is not a load or overhead-operation qualification.

### Active replacement USB cover — 2026-09-16

Print **one replacement keeper only** from
[`08D-C2 USB-clearance cover`](cad/output/revisions/08D-C2_usb_keeper_v1/08D-C2_ABS_USB_clearance_keeper_v1.3mf).
Keep the existing cage and selected spacers: the user reports that the spacers
secure the camera. This supersedes only the keeper in the 08D-C1 plate below.
Its opening is extended 13.5 mm toward the USB-port edge (opposite the tether
wing) and widened from 29 to 34 mm in that region. Closure holes, counterbores,
leveling access, outside dimensions and 6 mm thickness remain unchanged.

Use the existing **Camera Holder Precision 0.16** ABS settings, flat as supplied,
counterbores upward, 100% scale, supports off. This is a geometry-only 3MF:
confirm one object and inspect the sliced opening before printing. An adjacent
STL is available as a fallback. No extra hardware is introduced.

The plug allowance is photo-informed, not an exact measured fit. On the bench,
orient the extended opening over the USB port, confirm full plug insertion and
locking-screw access without plastic contact, and recheck that the existing
spacers stay captured and prevent camera movement with the keeper fastened.
The larger opening changes the contact footprint, so the earlier spacer test
does not qualify retention with this revised cover. Do not tighten against the
plug or clamp the lens rings. If a spacer overlaps the plug, stop rather than
forcing it; the old unprinted 24 mm-window compression-pad design is not cleared
for this back-exiting connector.

**Full-frame cable routing is still open:** the received camera's connector
exits its back face opposite the lens; older side-exit instructions and proxy
validation are superseded. The 56 mm carriage opening must be reviewed for this
plug and cable at the chosen mounting index before printing/installing the
carriage. This cover revision is not full-assembly or overhead qualification.
Original master manifests/assembly exports are preserved and do not represent
this supplemental revision.

### Active final-shim revision — 2026-09-15

For the final cage/keeper print, use
[`08D-C1 with 1.0/1.1 mm final shims`](cad/output/revisions/08D-C1_final_shims_v1/08D-C1_ABS_camera_cage_keeper_SHIMS_1p0_1p1_v1.3mf)
and its adjacent `.print.json` instead of the original two-object 08D-C1.
This local revision contains six objects: the unchanged cage and keeper plus
two nominal 1.0 mm and two nominal 1.1 mm labelled breakaway shims. It also
welds the original cage/keeper mesh vertices without changing their surfaces.
The original plate and master generated manifest are preserved; their object
counts do not describe this supplemental plate. No additional hardware is needed.

The user reported 0.9 mm loose and a 0.9+0.3 mm stack too tight. No additional
coupon print is requested. Select the thinnest suitable new shim during final
bench assembly; do not force the camera or treat this update as a passed
retention/load test. Clip off both the label tab and connecting neck; only the
38 x 7 mm flat strip is a contact spacer. Keep it clear of lens and connectors.
The dimensions are CAD nominal: the 0.16 mm process quantizes printed thickness.
Inspect the shim layer preview for distinct thicknesses before printing; native
QIDI slicing of this revised plate remains pending. Keep all other physical
assembly and safety gates in this guide.

| File | Purpose |
| --- | --- |
| [`config/printable_frame_design.json`](config/printable_frame_design.json) | source dimensions, quantities, hardware, and prototype gates |
| [`cad/output/manifest.json`](cad/output/manifest.json) | generated file list and validation results; every status must be `PASS` |
| [`cad/output/assembly/printable_camera_portal_printed_parts_only.step`](cad/output/assembly/printable_camera_portal_printed_parts_only.step) | authoritative printed-part assembly orientation |
| [`cad/output/assembly/camera_cage_nominal_subassembly.step`](cad/output/assembly/camera_cage_nominal_subassembly.step) | camera/cage/keeper reference |
| [`cad/output/plates_3mf`](cad/output/plates_3mf) | exact, geometry-only print plates |
| [`print_jobs/printable_camera_frame_jobs.json`](print_jobs/printable_camera_frame_jobs.json) | plate-to-process mapping, hashes, counts, and native save names |
| [`BOM_PRINTABLE_FRAME.csv`](BOM_PRINTABLE_FRAME.csv) | exact printed-part and hardware quantities |

Do not slice either assembly STEP. Open the numbered 3MF and its same-base
`.print.json` sidecar. Keep the stored orientation and placement, scale at
`100%`, supports off, and fuzzy skin off.

## Print settings

| Parts | Process | Layer | Walls | Top/bottom | Infill | Brim |
| --- | --- | ---: | ---: | ---: | --- | --- |
| anchors, uprights, splices, crossbar, booms, root straps, carriage | `RoCell ABS Rapido Camera Frame Structural 0.20` | 0.20 mm | 6 | 7 / 7 | 40% gyroid | outer only, 10 mm, 0.05 mm gap |
| camera gauge, cage, keeper, shim ladder | `RoCell ABS Rapido Camera Holder Precision 0.16` | 0.16 mm | 5 | 7 / 7 | 45% gyroid | outer only, 6 mm, 0.05 mm gap |
| four board pads and one camera compression pad | `RoCell TPU 95A Camera Clamp Pads 0.16` | 0.16 mm | 3 | 5 / 5 | 100% rectilinear | outer only, 3 mm, 0.10 mm gap |

The exact process JSON files are in [`slicer_profiles/QIDI_PLUS4`](slicer_profiles/QIDI_PLUS4).
Select the separately installed filament preset named by the sidecar; the 3MF
contains geometry only.

Print in this order:

1. `00G-*`: fit coupons, sacrificial retainer, shims, and pads.
2. `08A-*`: left anchor and four left upright modules.
3. `08B-*`: right anchor and four right upright modules.
4. `08C-*`: four crossbar modules, both two-module booms, splice collars,
   four root straps, and carriage.
5. `08D-C1`: camera cage and planar four-bolt keeper.

There are 21 plates and 56 packaged print objects; 51 bodies are installed in
the final assembly. One `00G` retainer is sacrificial, and the remaining four
non-installed bodies are the fit gauge, two structural coupons, and the shim
ladder used to select breakaway shims. Do not install the sacrificial retainer
in a production saddle. All raised IDs and arrows face upward in the stored
print orientation.

## Exact hardware

- 4 × M6 x 25 external-hex flange-head bolts, 10 mm wrench size, head OD
  no greater than 13.5 mm
- 5 × M6 DIN 985 low-pattern nyloc nuts, 10 mm across flats, height no greater
  than 6.0 mm: 4 fresh final clamp nuts plus 1 sacrificial `00G` test nut
- 32 × M5 x 75 flange-head bolts
- 4 × M5 x 80 flange-head bolts
- 4 × M5 x 85 flange-head bolts
- 8 × M5 x 90 flange-head bolts
- 52 × M5 flanged nyloc nuts: 48 for final installed joints plus 4
  proof-test-only sacrificial carriage nuts
- 4 × M4 x 60 button-head bolts
- 3 × M4 x 70 button-head bolts
- 6 × M4 standard hex nuts: three captured nuts and three leveling jam nuts
- 4 × M4 nyloc nuts
- 14 × M4 washers
- 6 × cable ties no wider than 5.0 mm
- 1 × complete factory-terminated metal safety tether meeting the config:
  `500 ± 25 mm`, 1.5–2.0 mm 7×7 stainless cable, coated OD no greater than
  3.0 mm, laid-flat choker eye at least 130 mm, screw-lock connector, verified
  WLL at least 10 kg and MBL at least 50 kg

Required tools are two thin-wall 8 mm sockets/nut drivers, one thin-wall 10 mm
socket/nut driver, a 2.5 mm hex key, and a thin 7 mm open-end wrench no wider
than 18 mm and no thicker than 5.5 mm. Use hand tools only.

## 1 — Prepare and inspect

1. Confirm a single flat bench plane under the board and both feet. Required
   clear region in board coordinates is `X=-120..730`, `Y=-250..0` at
   `Z=-18 mm`.
2. Remove brims only. Reject cracks, layer separation, warped bearing faces,
   incomplete walls/webs, closed bores, or damaged nut-retainer latches.
3. Run the `00G` saddle/nut/retainer and splice fit checks with the received
   hardware. Use only the dedicated sacrificial M6 nyloc for the prevailing-
   torque check, then discard it. The splice coupon checks collar fit and M5
   bolt passage only; do not run a final M5 nyloc onto it. Do not drill, melt,
   globally scale, or force a failed interface.
4. Seat one received M6 head on a cap's raised 16 mm boss. It must bear flat
   and concentrically without overhang.
5. Fit the received camera in `00G-C1`; use only the thinnest 0.3/0.6/0.9 mm
   shim combination that removes side rattle without force.

## 2 — Build each four-module upright flat

Build a left and a right upright separately.

1. Lay four `UP 240` modules in a straight line with every open-U section and
   raised arrow oriented alike.
2. Center one `u_truss_splice` collar over each of the three butt joints. The
   collar opening and beam opening face the same direction; align the butt to
   the collar's exterior center witness rib.
3. At each splice install two M5 x 75 bolts—one through each adjoining member
   end—and two M5 flanged nylocs. Each upright therefore uses three collars,
   six bolts, and six nuts.
4. Seat the faces by alternating small hand turns. Stop before the printed
   walls visibly dish or crack.
5. Check straightness with a straightedge or taut cord and mark every head and
   nut with a witness line.

## 3 — Build the four-module crossbar flat

1. Lay four `CROSS 182.5` modules with all open-U sections oriented alike.
2. Use a `u_truss_splice_crossbar_2bolt` at each outer joint. Each uses two
   M5 x 75 bolts: one per adjoining module end.
3. Use the `u_truss_splice_center_4bolt` at the center joint. Install four
   M5 x 75 bolts in the two diagonal pairs: two per adjoining module end.
4. Align all three butts to the collars' center witness ribs, seat evenly, and
   add witness marks. The crossbar consumes eight M5 x 75 bolts total.

## 4 — Build the two booms flat

For each boom:

1. Put one `BOOM ROOT 164` module ahead of one `BOOM CAMERA 164` module with
   their openings and arrows alike. The camera module is the distal end.
2. Join them with one standard `u_truss_splice`, centered on the butt.
3. Install two M5 x 75 bolts and two flanged nylocs—one through each member
   end. Seat evenly and witness-mark.

Do not attach the carriage yet.

## 5 — Attach anchors and raise the empty portal

This is a two-person operation. Keep the robot powered off and unplugged.

1. Put the two saddle feet on the bench at the board's front corners. Slide
   each to its board hard stops; only the two narrow cap lips may overlap the
   board top.
2. Insert two fresh, unused M6 DIN 985 nylocs into each saddle through the side
   tunnels and snap in four fresh production retainers. Never install the
   sacrificial `00G` retainer or its discarded test nut.
3. Capture two TPU pads in each cap and set the caps over the board corners.
4. Install four M6 x 25 bolts from above. Alternate the two bolts at each
   corner until the hard stops seat and hand movement is removed. Do not bow
   the board or crush the pads.
5. Lower each completed upright into its open-top receiver until it bears on
   both internal ledges. Install two diagonally separated M5 x 80 bolts and
   two flanged nylocs per tower. The ledges carry gravity; the bolts register
   and resist rocking.
6. With one person controlling each upright, lift the crossbar into place.
   Install the matched front/back `portal_corner_node_left` pair at the left
   and the matched right pair at the right, using eight M5 x 75 bolts total.
   Use the printed-parts assembly STEP for the exact plate orientation; do not
   mirror or substitute a left/right plate.
7. Seat all corner faces evenly, check the portal is square, and witness-mark
   every fastener before either person releases it.

## 6 — Attach both booms with four-bolt sandwich roots

1. Place each boom root at the corresponding reinforced crossbar station shown
   in the assembly STEP. Both boom openings face upward and both distal camera
   ends project toward board rear.
2. At each root place one `boom_crossbar_node` strap above and one flipped
   strap below the crossbar/boom stack. The smooth bearing faces contact the
   members; raised markings remain visible outward.
3. Install four M5 x 90 bolts and four flanged nylocs per root through the
   reinforced full-height columns. Alternate in a cross pattern until all
   bearing faces seat; do not crush either open-U member.
4. Confirm the booms are parallel and their distal faces are even. Add witness
   marks to all eight root bolts.

## 7 — Qualify the empty portal and arms before handling the camera

Do this with a soft catch below and no real camera in the structure.

1. Select one carriage Y row for all four M5 fasteners. Use the rear/local-65 mm
   row as the nominal position; never mix rows.
2. Attach the empty carriage to both distal boom ends using all four M5 x 85
   bolts and the four proof-test-only flanged nylocs. Witness-mark the
   fasteners.
3. Securely catch a dummy mass greater than the final camera-module mass from
   the carriage. Do not rely on tape, a cable tie, or friction to retain it.
4. Record the dummy load, duration, vertical sag, lateral drift, witness-mark
   movement, cracks, and permanent set. Repeat the inspection after a 24-hour
   loaded creep hold.
5. Reject any crack, layer separation, fastener rotation, increasing sag,
   permanent twist, retainer opening, or board-anchor movement. Digital CAD
   checks do not establish a safe physical load rating.
6. Remove the dummy mass, then remove the empty carriage for the camera-module
   bench assembly. Discard the four proof-test nylocs; never use them in the
   final overhead joint. Inspect the four M5 x 85 bolts and reuse them only if
   their threads, heads, and shanks are undamaged. Do not leave the carriage
   overhead while installing the camera into its cage.

## 8 — Bench-assemble the camera module

Keep the camera and lens on a soft pad. The cage, camera, TPU pad, shims, and
keeper become one removable module before that module is attached to the
carriage.

1. Support the cage on two soft blocks so its lens opening and underside nut
   pockets remain unobstructed. Put the camera in the four-sided cage with
   `LENS DOWN` and its USB connector facing the open rear USB window.
2. Install the accepted side shims and TPU top-compression pad. The pad contacts
   only the camera case—not the lens, focus/iris controls, connector, or cable.
3. Set the flat keeper on all four cage walls. Install four M4 x 60 bolts
   downward, each with a washer under its fully recessed head. Under the cage
   base add one washer and one M4 nyloc per bolt.
4. Alternate the four keeper bolts until the pad removes rattle. Stop before
   the case distorts. This four-bolt keeper has no hooks, clip, or friction-only
   latch.
5. Load one standard M4 nut into each of the three underside cage pockets.
   Temporary low-tack tape may retain them only during bench assembly.
6. Put the carriage above the keeper. For the nominal position use the center
   hole at all three leveling stations; never mix left/center/right X indices.
7. Put a washer under each M4 x 70 head and insert the three bolts downward
   through the carriage. Below the carriage add one washer and one standard
   M4 jam nut to each bolt, then engage all three captured cage nuts by several
   full turns.
8. Remove every temporary tape strip and verify all three captured nuts remain
   seated. Set roughly equal engagement at the three points; leave the jam nuts
   loose for final leveling.

The four 5 mm carriage holes over the keeper bolts are driver-access holes for
installed torque checks. A keeper bolt head does not pass through them. Camera
replacement therefore means removing the three-point cage module from the
carriage and re-leveling it; do not enlarge those holes.

## 9 — Attach carriage and tether before releasing the camera

This is a two-person operation with a soft catch below. One person maintains
two-handed control until both primary and secondary retention are complete.

1. Choose one carriage Y row for all four M5 fasteners. The rear/local-65 mm
   row is the nominal camera position; the front/local-44 mm row moves the
   complete carriage 21 mm rearward. Never mix rows.
2. Attach the carriage to both distal boom ends with all four M5 x 85 bolts and
   four new, unused flanged nylocs reserved for the final joint. The fasteners
   pass through reinforced full-height boom columns.
3. Choke the verified factory-terminated tether around the exposed right
   distal boom at the marked station and close its screw-lock connector through
   the cage's tether wing. Adjust routing so measured installed slack is
   20–105 mm at the selected X/Y position.
4. Only after another person independently confirms all four carriage bolts,
   the three leveling bolts, all four keeper closures, and both locked tether
   terminations may the camera be released.
5. Route the USB lead through the cage and open-U members with the six specified
   ties. Ties are strain relief only, never primary or secondary camera retention.

## 10 — Level, lock, and perform the final physical checks

1. Adjust only the three M4 leveling screws. Approach the two front jam nuts
   from board front through their `-Y`-open keeper bays; approach the rear jam
   nut from board rear through its `+Y`-open bay. The modeled path accepts the
   specified thin 7 mm wrench between the booms.
2. Keep useful engagement in every captured nut and stay within the configured
   8 mm Z-adjustment range. Tighten each jam nut against its washer beneath the
   carriage, then witness-mark all three leveling points.
3. Verify every clamp, splice, corner, root, carriage, keeper, and tether
   witness mark. Confirm no printed wall is crushed and no cable carries load.
4. Independently verify the complete camera, portal, fasteners, tether, and
   cable remain outside every robot route. Do not power or move the robot until
   that physical collision review and the support qualification are accepted.

## Fastener count audit

- M5 x 75: 12 upright + 8 crossbar + 4 boom splices + 8 portal corners = 32
- M5 x 80: 4 tower receivers
- M5 x 85: 4 carriage-to-boom
- M5 x 90: 8 boom-root sandwich joints
- M5 nylocs: 52 total—48 in the final structure plus 4 discarded after the
  empty-carriage proof/creep test
- M4: 4 keeper bolts + 3 leveling bolts; 14 washers, 6 standard nuts, 4 nylocs
- M6: 4 board-clamp bolts + 5 DIN 985 nylocs—4 fresh final captured nuts plus
  1 discarded after the `00G` prevailing-torque test

If the build demands a different count, length, row, index, or direction, stop
and compare against the assembly STEP and generated manifest. Do not improvise
an extra hole or substitute a wood screw.
