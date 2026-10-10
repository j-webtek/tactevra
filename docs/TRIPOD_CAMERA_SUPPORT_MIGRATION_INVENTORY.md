# Commercial Tripod Camera Support Migration Inventory

## Decision

Phase 1 retains the fixed overhead eye-to-hand camera architecture and replaces
the planned printed portal, paired mast, and arm-mounted holder routes with an
independent commercial floor tripod. The selected candidate is Amazon ASIN
`B0CSYB4YQ2`. The candidate is selected for engineering integration but is not
physically qualified, commissioned, or authorized for motion.

The support is independent of the robot and work board. It must carry the
Arducam B0477 above the workcell with a downward optical axis, remain outside
all robot swept volumes, and retain a measured pose after settling. No printed
part may be the primary load-bearing camera support or the sole camera
retention feature.

## Product facts and open questions

The short product link resolves to ASIN `B0CSYB4YQ2`. Third-party listings
describe a Victiv floor tripod with a flexible overhead neck and a universal
1/4-inch camera screw. Listing titles conflict on maximum height, describing
both 70-inch and 88-inch variants. These are supplier claims, not received-unit
measurements.

The following remain open until the delivered tripod and B0477 are inspected:

- delivered manufacturer, model, revision, and maximum usable height;
- B0477 housing thread type, thread depth, adapter stack, and anti-rotation;
- rated and measured payload with the camera, lens, adapter, and USB cable;
- static sag, settle time, vibration, and 24-hour pose drift;
- floor footprint, overturning margin, ballast need, and leg locking;
- gooseneck or head lock repeatability and removal/reinstallation repeatability;
- camera-to-board reach at 700, 850, and 1000 mm above the tag plane;
- USB strain relief and whether cable forces move the camera;
- installed collision geometry and clearance from people and robot motion.

## Active route changes

| Area | Current active assumption | Required migration | Treatment |
|---|---|---|---|
| Camera architecture | Rigid static overhead gantry or crossbar | Independent commercial floor tripod | Replace active support contract; keep static eye-to-hand optical frame |
| Support candidate | Paired 2020 mast or commercial bench boom | ASIN `B0CSYB4YQ2` | Select unqualified candidate; qualify received unit |
| Printable portal | Jobs `00G` and `08A` through `08D` | No longer part of the active build | Preserve files and mark `SUPERSEDED_DO_NOT_PRINT` |
| Legacy RC03 mast | Jobs `03C3`, `06`, `07A`, and `07B` | No longer part of the active build | Preserve files and remove from active route/readiness |
| Arm camera holder | Moving-link primary camera in old manifests | Phase 1 remains fixed overhead | Preserve historical freeze; prohibit automatic fallback |
| Camera retention | Printed cage/keeper/plate | Commercial metal interface or measured adapter | Do not assume direct 1/4-inch compatibility before inspection |
| Collision model | Gantry, crossbar, plate, cable | Tripod legs, column, head, camera, adapter, and cable | Replace candidate geometry; re-run swept-volume screens |
| Commissioning witness | Gantry/plate fastener witness | Leg locks, column locks, head locks, adapter, camera, floor registration | Add witness marks and before-action pose checks |
| Simulation | Fixed nadir camera with portal geometry assumptions | Same optical model with tripod support envelope | Keep 700/850/1000 mm studies exploratory; add tripod body/keepout |
| Physical release | Open blockers | Still blocked | No change to authority or readiness |

## Files that must change

### Authoritative configuration and runtime validation

- `software/config/camera_architecture_plan.json`: name the independent
  commercial tripod as the selected unqualified support and replace gantry
  acceptance, invalidation, collision, and blocker language.
- `software/src/rocell/workcell/camera_architecture.py` and
  `software/tests/unit/test_camera_architecture_plan.py`: validate the tripod
  route without weakening fixed-camera, all-tag, freshness, or zero-authority
  rules.
- `hardware/static_overhead_camera/config/support_design.json` or its explicit
  successor: bind the tripod candidate and its measured installation instead of
  the portal geometry.
- `software/src/rocell/workcell/static_camera_support.py` and focused tests:
  validate the selected support identity, measurements, and fail-closed gates.
- `software/config/simulation_hardware_profile.json`: remove the old
  eye-on-arm primary assumption and represent an external static support.

### Active build and onboarding

- `active-project/RoCell_v0_3/config/camera_architecture_decision.json` and
  `v1_prehardware_configuration.json`: select the fixed overhead tripod route.
- Active project generators, measurement records, build gates, instructions,
  BOMs, job cards, Step 13 package, readiness outputs, PDFs, checksums, and
  their tests: remove camera mast and printed portal jobs from the current
  route; add tripod receipt, inspection, placement, witness, tether, and
  qualification records.
- Camera support intake/onboarding: require received product photos, model
  label, dimensions, mount thread/depth, installed camera stack, and pose tests.

### Simulation and safety geometry

- Replace portal/crossbar collision bodies with conservative tripod legs,
  column, head, camera, adapter, cable, and floor footprint.
- Re-run camera coverage, 48 mm crop-footprint coverage, parked-arm clearance,
  and all route swept-volume screens for the installed height and XY position.
- Re-run wrong-model drills for camera height, lateral displacement, tilt,
  support sag, and cable pull. Consequential changes must abstain.

### Maintained documentation

- `README.md`, `STATIC_OVERHEAD_CAMERA_ARCHITECTURE_PLAN.md`,
  `BUILD_ALIGNMENT_FREEZE.md`, `ROBOT_TYPING_SYSTEM_MASTER_PLAN.md`, camera
  integration hold/readiness documents, and operator procedures must describe
  the tripod route and the same qualification gates.
- The shared workplan and evidence ledger must retain the exact migration
  commits, commands, tests, limitations, hardware-write count, and
  physical-movement count.

## Files retained as historical evidence

The following are not active fabrication instructions after migration, but are
not deleted or rewritten:

- `hardware/static_overhead_camera/config/printable_frame_design.json`;
- `hardware/static_overhead_camera/PRINTABLE_FRAME_BUILD_GUIDE.md` and
  `PRINTABLE_FRAME_INTEGRATION_MAP.md`;
- portal CAD generators, drawings, generated geometry, slicer profiles, BOMs,
  and jobs `00G` and `08A` through `08D`;
- RC03 mast jobs `03C3`, `06`, `07A`, and `07B`;
- frozen manifests, prior readiness outputs, and evidence entries that describe
  arm-mounted, paired-mast, gantry, or printable-portal work.

Each active index that links to one of these files must label it
`SUPERSEDED_DO_NOT_PRINT` or historical. Historical hashes remain valid.

## Tripod qualification gates

1. Record received manufacturer, model, ASIN, label photos, and all included
   head/adapter parts.
2. Measure minimum/maximum usable optical height and the floor footprint.
3. Measure the B0477 housing thread, available depth, adapter engagement, and
   a positive anti-rotation method. Install an independent safety tether.
4. Weigh the camera, lens, adapter, cable load, and any light carried by the
   support. Compare with the received tripod rating.
5. At the selected installation, measure camera pose before load, after load,
   after cable routing, after a deliberate small disturbance, after settling,
   after remove/reinstall, and after 24 hours.
6. Freeze leg, column, neck, head, adapter, focus, and cable witness marks.
7. Capture exact runtime-mode images and prove all six fiducials plus every
   complete model crop footprint are inside the frame at the qualified height.
8. Add conservative installed support geometry and pass robot swept-volume
   screening with the support, cable, operator keepout, and floor footprint.
9. Measure frame stability, blur, latency, and pose residuals while the robot
   moves. The support must not inherit floor or cable vibration that exceeds
   the vision error budget.
10. Run stale frame, tag loss, support shift, camera tilt, cable pull, and
    witness mismatch injections. Every consequential fault must block descent.

## Migration sequence

1. Freeze this inventory and the non-authorizing tripod candidate contract.
2. Migrate the authoritative camera architecture and strict tests.
3. Migrate active build routes and remove obsolete print jobs from generated
   operator packages while retaining their sources as historical.
4. Replace support geometry in simulation and re-run coverage, visibility,
   collision, and wrong-model checks.
5. Receive and measure the tripod and B0477 interface; bind measurements to a
   new support qualification record.
6. Regenerate active manifests, BOMs, job cards, readiness outputs, PDFs, and
   checksums atomically.
7. Keep physical motion blocked until the installed support passes every gate
   and the normal first-motion approval process is completed.
