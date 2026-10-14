# Static overhead camera architecture plan

> **Commercial-tripod direction selected October 10, 2026:** Phase 1 remains a
> fixed overhead eye-to-hand camera, but the active support candidate is now an
> independent commercial floor tripod, Amazon ASIN `B0CSYB4YQ2`. The printed
> portal, paired 2020 mast, and RC03 camera-plate/mast jobs are superseded build
> routes and remain only as historical evidence. The tripod is
> `SELECTED_UNQUALIFIED`: delivered identity, camera interface, loaded height,
> stability, sag, drift, vibration, cable effects, floor footprint, collision
> geometry, and installed pose are unmeasured. This decision grants no physical
> authority. See the
> [migration inventory](docs/TRIPOD_CAMERA_SUPPORT_MIGRATION_INVENTORY.md).

> **Historical printable-frame direction selected 2026-09-06:** The builder requested a
> completely 3D-printable camera holder and structural frame, with ordinary
> metal bolts, nuts, washers, and a safety tether permitted. The additive
> prototype branch is a sectional ABS Rapido, bench-bearing front portal with
> reversible front-corner board clamps. Its CAD and builder package live under
> [`hardware/static_overhead_camera`](hardware/static_overhead_camera). This
> direction does not retroactively release fabrication or robot motion; the
> assembled printed frame must pass fit, load, creep, disturbance, cable,
> collision, and optical qualification before controlled integration.

**Decision date:** 2026-09-05  
**Decision:** A rigid static overhead eye-to-hand camera is the required Phase 1 primary vision source.  
**Camera state:** `PURCHASED_PENDING_RECEIPT_INSPECTION`  
**Architecture state:** fixed overhead camera selected; commercial tripod candidate selected but unqualified; atomic source-contract migration and physical qualification remain open
**Physical authority:** None. Robot power, motion, descent, and contact remain blocked.  
**Machine-readable plan:** [`software/config/camera_architecture_plan.json`](software/config/camera_architecture_plan.json)  
**Current support migration:** [`docs/TRIPOD_CAMERA_SUPPORT_MIGRATION_INVENTORY.md`](docs/TRIPOD_CAMERA_SUPPORT_MIGRATION_INVENTORY.md), with the selected unqualified tripod candidate, exact update inventory, historical-retention rules, and physical qualification gates

## 1. Why this plan exists

Freeze 009 records the earlier choice of a camera on the RoArm upper arm and
keeps a fixed 2020 mast only as an unselected fallback. The builder subsequently
selected the opposite production direction: fixed overhead vision is primary,
and an arm camera is optional later. The active Freeze 012 adds the B0477
preparation/support path while deliberately retaining the legacy canonical
arm-camera fields under `CAMERA_ARCHITECTURE_ALIGNMENT_HOLD`.

This is a controlled architecture change. It is not safe to rename the old
fallback, reuse its calibration, or declare its printed parts released. The
historical Freeze-009 artifacts remain immutable provenance. A superseding
controlled freeze is still required to replace the retained legacy canonical
camera bindings across configuration, geometry, instructions, tests, generated
files, and hashes together.

The active build remains safe during this transition because Step 13, camera-
guided motion, and contact are already blocked. No completed keyboard, phone,
tool, or Job 00A evidence is invalidated merely by selecting static vision.

## 2. Architecture decision

Phase 1 shall use one camera held by an independently registered commercial
floor tripod and never attached to a moving robot link or loaded through the
work board. The installed support pose must be measured and witnessed; the
product listing and nominal simulation pose are not calibration evidence.

```text
                           fixed workcell
                                 |
                         C_overhead_optical
                                 |
              image -> undistort -> AprilTags/device features
                                 |
                    C_overhead_optical_T_B(i)
                                 |
 Wv_T_C_overhead_optical --------+----------> Wv_T_B(i)
                                 |
                semantic target in B -> checked robot route
                                 |
                 observe -> approach/contact -> retract
                                 |
                independent keyboard/Android outcome
```

The primary camera owns:

- full-board and station localization;
- detection of board or device displacement;
- the observation required before every autonomous descent;
- optional observation of a top-visible tool marker above clearance; and
- post-retract visual checks.

The optional Phase 2 arm camera may later provide local inspection or bounded
refinement. It may not automatically replace a failed overhead camera, grant
contact by itself, or override a disagreement with the primary.

## 3. What improves and what remains hard

Static vision removes these Phase 1 dependencies:

- the upper-arm carrier transform and rail position;
- camera pose recomputation from every joint state;
- exposure-to-joint synchronization for board localization;
- moving camera payload and USB service-loop effects; and
- pose-dependent global field of view.

It does **not** remove:

- robot-to-board registration;
- controller-frame correlation;
- TCP, compliance, contact-force, and surface-height calibration;
- keyboard and phone target maps;
- full-body collision qualification;
- the RoArm's physical endpoint uncertainty; or
- independent verification of the key or tap outcome.

A fixed camera knows where the board is in camera coordinates. It does not
magically know where the robot thinks it is.

## 4. Frame and transform contract

The primary optical frame is `C_overhead_optical`. The board remains `B`, the
reviewed vendor-model world remains `Wv`, and controller Cartesian commands
remain in the separately qualified `R_ctrl` frame.

Each accepted image estimates:

```text
C_overhead_optical_T_B(i)
```

Live robot-frame board registration requires the separately commissioned
static eye-to-hand extrinsic:

```text
Wv_T_B(i) = Wv_T_C_overhead_optical * C_overhead_optical_T_B(i)
```

If `Wv_T_C_overhead_optical` is unavailable, the image is useful for
board-relative device localization only. It cannot authorize robot-frame
correction. Commissioning must establish that static extrinsic and validate its
derived `B_T_Wv` against independent robot/board datums; `R_ctrl` correlation
remains a separate requirement.

Board tags alone cannot distinguish a bumped camera from a shifted board. The
mount should therefore be rigidly related to the robot/base reference, and the
design should include either a visible robot-base/static-support witness or a
fail-closed comparison against the commissioned installation transform.

The existing `camera_overview_optical` simulation spelling may remain as a
legacy test fixture during migration. It must not be silently aliased to the
commissioned frame without an explicit schema transition.

## 5. Runtime observation and contact sequence

Every physical action shall use a stop-and-look sequence:

1. Verify camera identity, native mode, settings, calibration hashes, support
   witness, robot state, and outcome observer.
2. Move only to the prequalified primary observation posture.
3. Wait for measured settling and flush a bounded number of buffered frames.
4. Capture a uniquely fresh frame.
5. Detect all six tags in every Phase 1 pre-descent observation. Use T0-T3 for
   the board pose and K0/P0 as independent held-out station checks.
6. Verify the installed keyboard or phone, its seating/orientation, and its
   target-map identity.
7. Bind the accepted observation and calibration hashes to the exact action
   occurrence and checked trajectory suffix.
8. If required, observe a top-visible tool marker and correct the hover only
   above a proven clearance plane.
9. Execute the short qualified approach and contact. Do not require the target
   to remain visible when the tip occludes it.
10. Retract to a clear observation posture.
11. Reacquire vision and verify the effect through an independent desktop or
    Android observer.

If the primary posture is occluded, the only automatic recovery is a
prequalified retreat to a second clear observation posture. Missing, stale,
ambiguous, or weak observations never permit blind continuation.

## 6. Mechanical planning contract

The preferred support is a rigid two-post gantry or equivalently stiff
crossbar, with the camera near the board center and its optical axis close to
normal. The final design shall:

- sit outside every approved robot, tool, and cable swept volume;
- use a positive-retention camera plate and non-bottoming fasteners;
- lock all post, crossbar, angle, focus, and cable-adjustment degrees of
  freedom after commissioning;
- provide strain relief without transmitting cable load into the camera;
- use mechanical witness marks or datums for disturbance detection;
- support controlled diffuse lighting without phone-screen glare; and
- be represented as static collision geometry.

The earlier paired 2020 mast, 700 mm posts, universal plate, and commercial
boom are rejected as the default support for the selected architecture. The
700 mm height is below Waveshare's published 798 mm vertical-workspace screen
before the camera, bracket, cable, lighting, or hard clearance is included.

The detailed-screening baseline is now a bench-anchored front portal on a
rear-open, forward-footed metal frame. It uses nominal front post axes
`B=(-60,-100)` and `B=(670,-100) mm`, an overhead camera axis at
`B=(305,228.5) mm`, 1200 mm 4040 upright stock, an 800 mm 4040 front
crossbar, two 400 mm high-level booms, and a 200 mm camera bridge. Low base
members stay at or forward of `Y=-100 mm`; no low side rail is allowed to run
rearward beside the board without an independent full collision acceptance.

The camera entrance pupil targets `Z=1000 mm` with a `950..1050 mm`
qualification range. Any camera, bridge, boom, brace, light, cable, connector,
or fastener whose XY projection enters the robot operating footprint stays at
or above a provisional `Z=920 mm` floor. Against the published 798 mm number,
that leaves 122 mm total and 22 mm after a provisional 100 mm clearance
allocation. This is screening only: the 920 mm plane is accepted only if the
measured full-arm/tool/cable sweep plus uncertainty is no greater than 820 mm.

The placemat is located to the same bench datum by reversible 3-2-1 vertical-
edge stops and opposed low-profile clamps. The plywood carries no portal load,
the current board receives no new holes, and the rear-center
`X=225..385 mm` factory-clamp region remains open. Exact locator and anchor
brackets remain blocked on received board/bench/arm measurements and common-
assembly interference CAD.

The full robot swept volume selects the safe camera height first. Lens choice
comes afterward. Designing the lens first risks either a collision or a large
loss of useful pixels.

## 7. Optical design contract

The placemat is 610 x 457 mm and nearly matches a native 4:3 image. A native
4:3 mode remains optically efficient, but the selected detailed-screening
camera uses a full native 3:2 frame with sufficient calculated view margin. No
silent 16:9 crop, rescale, or undocumented region of interest is allowed.

For screening, use a 670 x 517 mm required view: the board plus 30 mm on every
edge. For a centered, perpendicular pinhole view, the minimum FOV is:

| Lens height above tag plane | Minimum horizontal FOV | Minimum vertical FOV |
| ---: | ---: | ---: |
| 500 mm | 67.6 degrees | 54.7 degrees |
| 600 mm | 58.4 degrees | 46.6 degrees |
| 700 mm | 51.2 degrees | 40.5 degrees |
| 800 mm | 45.4 degrees | 35.8 degrees |
| 900 mm | 40.8 degrees | 32.1 degrees |
| 1000 mm | 37.0 degrees | 29.0 degrees |

These are screening minima, not acceptance values. The final calculation must
use measured entrance-pupil height, true H/V FOV, native crop, calibrated
distortion, camera tilt, support tolerances, and full tag-tile border margin.

The user-confirmed purchased catalog configuration is the Arducam B0477: a
20 MP Sony IMX283
USB 3 UVC camera in a metal enclosure with an included 16 mm manual-focus
C-mount lens. Arducam publishes `5472 x 3648` YUY2 at 9 fps and
`49 degrees H x 38 degrees V`. At 1000 mm those independent published FOV
values imply about `911.45 x 688.66 mm` coverage. Conservatively deriving the
vertical FOV from the native 3:2 frame and published horizontal FOV gives
`33.799 degrees V` and `911.45 x 607.64 mm`; this still covers the required
`670 x 517 mm` screen. The same conservative calculation at the 950 mm lower
adjustment bound gives `865.88 x 577.25 mm`.

The purchase listing's `120 fps` headline is not the full-resolution operating
point. This plan continues to screen the supplier-published `5472 x 3648` YUY2
mode at `9 fps`; no physical mode is commissioned until the received camera
enumerates and repeatedly reopens with the exact recorded tuple.

Purchase fixes the intended catalog configuration for simulation and carriage
design; it does not verify the delivered unit or release physical work. The
vendor's published H/V pair is not pinhole-consistent with the full-native 3:2
aspect and the supplied lens is shipped with a distant default focus. On
receipt, record the label, model, serial, USB descriptors, lens markings,
contents, dimensions, mass, and condition before assembly. Then confirm
one-metre focus and lockability, the exact enclosure STEP/mount, delivered
C-versus-CS interface, controls, and full-native USB mode while preserving the
return path. Physical qualification must measure usable undistorted FOV, crop,
distortion, depth of field, corner illumination, and persistent UVC behavior.

The previous B0459/LN024 combination remains a lower-cost alternate only after
Arducam confirms back-focus and enclosure clearance. The earlier wide-angle
LN069 and the pictured B0627 stock 125-degree lens waste too much resolution
at a one-metre static height for the primary precision view.

The final optical choice must prove:

- sufficient pixels across the worst-corner 40 mm AprilTag;
- sufficient local sampling for the smallest accepted phone/key safe region;
- lockable focus at the installed height;
- manual and persistent exposure, gain, and white balance;
- distortion behavior supported by the calibrated software model;
- acceptable depth of field across board, keys, phone screen, and tool marker;
- stable USB identity and exact native mode; and
- usable images under the complete lighting and phone-display envelope.

## 8. Calibration chain

Commission the following as distinct, dependency-bound artifacts:

1. Exact camera, sensor, lens, focus, aperture, native mode, pixel format,
   driver, crop, exposure, gain, white balance, and persistent USB identity.
2. Camera intrinsics and distortion from varied ChArUco images at those exact
   settings, with a precommitted held-out set.
3. Measured corners, Z plane, installation state, and uncertainty for all six
   board AprilTags.
4. `Wv_T_C_overhead_optical`, solved from a robot-held target or derived by
   combining an independently measured `Wv_T_B` with the simultaneous
   `B_T_C_overhead_optical`, with a robot-base/support witness and held-out
   validation.
5. Robot reference and the independent `R_ctrl` to `Wv` correlation.
6. Installed keyboard pose, key polygons, key surface Z, and conservative safe
   insets.
7. Installed phone pose, screen plane, screen homography, orientation, UI
   profile, and conservative safe insets.
8. Route-specific tool TCP, compliance, travel, force, and contact limits.
9. Held-out end-to-end keyboard and phone validation.

The current single TCP puck is a useful held-out check, not a complete
six-dimensional board-to-robot solve. Use at least three non-collinear
controlled datums or a qualified static eye-to-hand robot-held-target dataset.

Pixel-to-board conversion must intersect the correct physical plane. A board-
plane homography must never be applied blindly to raised keycaps, the phone
screen, or a tool marker at hover height.

## 9. Tool-marker decision

The static camera simplifies global registration but does not remove the arm's
endpoint uncertainty. If the measured repeatability budget does not fit inside
phone or keyboard safe regions, add a top-visible marker frame `M` rigidly
related to the tool tip `T` through calibrated `M_T_T`.

Marker-guided correction shall:

- occur only above a proven collision-clear height;
- observe board tags and the marker in the same fresh frame;
- correct a bounded hover, then stop visual correction before final descent;
- retain an independently calibrated TCP/compliance model for Z contact; and
- fail closed when the marker, board, or two estimates disagree.

The marker is conditional until simulation and physical repeatability data show
that it is required. Phone QWERTY is the route most likely to require it.

## 10. Simulation work before hardware

The existing fixed-overview JPEG/tag/planar-pose path becomes the production-
aligned topology, but it is not yet a physical implementation. The additive
B0477 path now has the purchase profile, nominal one-metre projection,
provider-neutral fake UVC inventory, sealed 32-view synthetic ChArUco contract,
normal/tag-loss pixel pair, and a cross-artifact coherence gate. Continue with:

- the purchased B0477 catalog configuration's `950..1050 mm` height range, published and aspect-
  conservative H/V FOV, full-native 3:2 resolution, distortion, and calibrated
  usable crop;
- camera-height, XY aim, roll/pitch/yaw, focal-length, and support-tolerance
  sweeps;
- arm, gripper, tool, and cable occlusion at every target's primary and
  recovery observation postures;
- a top-visible marker and pixel-to-tip error propagation;
- support drift, cable pull, camera bump, and robot-base witness faults;
- estimator separation in which only T0-T3 may fit board pose and K0/P0 are
  excluded from fitting and evaluated afterward as independent residual checks;
- focus, blur, exposure, glare, shadow, screen-PWM, and lighting faults;
- stale/buffered frames, identity/mode/settings drift, disconnect/reconnect,
  and duplicate frames;
- board, keyboard, phone, and tag displacement;
- correct board/key/screen/marker plane intersection; and
- complete keyboard and Android flows through observation, correction,
  contact, retract, and independent outcome verification.

Synthetic truth may score a simulator but may never be used by the production
quality gate. Operational acceptance must rely on tag identity/distribution,
residuals, covariance, multi-frame agreement, freshness, settings/calibration
identity, plausibility, and the support/base witness.

## 11. Software migration plan

Implemented in this planning revision:

- Active Freeze 012 retains the Freeze-009-derived arm-camera fields under
  `CAMERA_ARCHITECTURE_ALIGNMENT_HOLD`; historical eye-on-arm reports remain
  unchanged and are not reinterpreted as B0477 evidence.
- `software/config/camera_architecture_plan.json` records the decision with zero
  physical authority.
- `software/config/camera_profiles/arducam_b0477_imx283_16mm.json` records the
  exact purchased catalog configuration, published modes, an explicitly
  nominal half-scale simulation projection, and all still-open receipt and
  commissioning fields. The static-support contract pins its exact file hash.
- `rocell.workcell.load_camera_architecture_plan` strictly validates the
  document, rejects schema/authority/route/FOV drift, and has focused unit tests.
- Governing and software architecture documents identify fixed overview as the
  Phase 1 migration target and eye-on-arm as optional Phase 2 research.
- `rocell.vision.uvc_inventory` defines a provider-neutral inventory boundary;
  the deterministic fake provider rehearses persistent selection, exact native
  USB3/YUY2 mode, manual controls, and reopen stability without device access.
- `rocell.calibration.static_camera_intrinsics` validates a sealed 32-view
  synthetic ChArUco artifact with 24 training and 8 held-out views. It binds
  the UVC fixture's synthetic persistent identity and settings hashes, but
  explicitly cannot represent physical calibration.
- `rocell.application.b0477_stack_coherence` rejects drift across the profile,
  support, commissioning, UVC, intrinsics, and optional normal/tag-loss pixel
  pair. The recommended `rehearse-b0477-stack --require-pass` currently reports
  `SYNTHETIC_B0477_STACK_COHERENT` with 10/10 checks and zero hardware, capture,
  motion, contact, or physical-release authority. `--skip-pixel-vision` is only
  a faster core-artifact development loop.

Next controlled work:

1. Create a superseding controlled freeze around the strict static architecture
   schema, replacing rather than relabeling the legacy camera bindings.
2. Rename the production routes to `camera_overhead_primary` and
   `camera_arm_secondary`; deprecate `camera_mast_optional` without silently
   changing its old meaning.
3. Promote fixed-overview simulation from legacy gate to the primary
   production-aligned vision model. The current implementation fits all six
   tags; promotion requires a T0-T3-only solve with K0/P0 held out.
4. Add a camera-neutral physical vision service:
   capture -> undistort -> detect -> estimate -> quality -> evidence.
5. Add `StaticCameraBoardMeasurement` and a camera-neutral
   `BoardRegistrationObserver` so replanning does not depend on arm-camera
   feedback types.
6. Replace the Phase 1 `eye_on_arm_extrinsic` dependency with the static
   `overhead_camera_extrinsic`; retain the former only for Phase 2.
7. Implement the real OS provider behind the existing UVC inventory contract;
   observe persistent identity, exact FOURCC/mode, manual controls, and readback
   on the received unit, then add warm-up, bounded buffer flushing,
   sequence/freshness evidence, reconnect/reboot trials, and physical promotion.
8. Add static gantry/camera/cable/lighting collision bodies and route-specific
   visibility policies.
9. Update the active RC03 source configuration, Step 13, BOM, job routing,
    readiness reports, manuals, diagrams, PDFs, manifests, and checksums in one
    controlled regeneration.

Eye-on-arm solver, capture-bundle, moving-camera simulation, and fault tests
remain valuable optional-secondary research. They should be relabeled rather
than deleted.

## 12. Acceptance gates to close with hardware

The superseding freeze shall define exact numeric limits from the smallest target-safe
region and measured robot/tool uncertainty. At minimum, physical commissioning
must prove:

- persistent camera identity and exact mode after reopen and reboot;
- no silent crop, scale, rotation, autofocus, autoexposure, or white-balance
  change;
- at least 20 accepted varied ChArUco views with held-out evidence;
- calibrated coverage of all tag tiles and device regions at both observation
  postures;
- all-six-tag startup and route trials under the qualified lighting envelope;
- independent K0/P0 held-out residual checks;
- bounded frame freshness, buffering, capture latency, settle time, pose
  covariance, and repeated-frame dispersion;
- gantry/camera/cable/lighting clearance from every approved path;
- warm-up, arm-cycle, cable-disturbance, remove/reinstall, and 24-hour drift
  behavior inside the allocated vision budget;
- a primary and recovery observation for every supported keyboard and phone
  target; and
- zero descent/contact permits for camera loss, stale replay, wrong settings,
  tag loss/outliers, support movement, board movement, or primary/secondary
  disagreement.

Current synthetic thresholds and marketing FOV values are design inputs only.
They cannot become physical acceptance evidence.

## 13. Invalidation rules

- Camera, lens, focus, aperture, native mode, pixel format, crop, driver, or
  orientation change invalidates intrinsics and dependent vision evidence.
- Gantry, crossbar, plate, fastener, camera, cable strain, or aim disturbance
  invalidates the static extrinsic, visibility atlas, and support baseline.
- Tag movement, damage, replacement, lamination, or board warp invalidates the
  measured tag map.
- Arm clamp, base, robot reference, servo, firmware, or controller mapping
  change invalidates robot registration and controller correlation.
- Device removal/reseat, station, case/protector, orientation, OS layout, or UI
  change invalidates the affected target map.
- Tool, tip, spring, cartridge, gripper seating, or compliance change
  invalidates the affected TCP/contact calibration.
- Any unexplained pose/residual drift, settings mismatch, collision, E-stop, or
  support disturbance immediately blocks autonomous descent pending review.

## 14. Controlled transition boundary

Until the superseding freeze exists:

- do not buy a lens solely for the earlier 320-350 mm arm-camera geometry;
- do not treat the purchase listing as received-unit identity, dimensional,
  focus, mode, mounting, calibration, or suitability evidence;
- preserve the seller's return path until one-metre focus, delivered mount
  configuration, enclosure geometry, and host USB 3 feasibility are tested;
- do not print or install the old mast merely because overhead vision is now
  selected;
- do not treat the synthetic fixed camera as physically calibrated;
- do not delete or reinterpret Freeze 009 evidence;
- do not enable camera-guided motion or contact; and
- continue software-only simulation and architecture-neutral refactoring.

The additive hardware package supplies the compact support and B0477 optical
baseline for detailed CAD and simulation. The next physical decisions remain
the measured collision-safe support envelope and the received optical system
matched to it. Calibration and runtime profiles follow those acceptances, in
that order.
