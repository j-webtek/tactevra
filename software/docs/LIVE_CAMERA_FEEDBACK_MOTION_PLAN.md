# Live camera feedback and motion integration plan

## Scope and present state

This plan joins the newly connected, keyboard-facing camera to the existing
vision, intent-to-hover, attachment-profile, motion-admission, and telemetry
contracts. It records the state reported on 2026-10-15 and defines the work
needed before camera observations may influence physical movement.

The camera is identified as an Arducam B0477 at persistent Windows PnP
identity `USB\VID_04B4&PID_0477&MI_00\8&257B140A&0&0000`. Bounded capture
verified `1920x1080`, approximately 60 fps, YUY2, stable settings across reopen,
and unique retained frames. Installed intrinsics, a camera-to-board transform,
and synchronized exposure timestamps remain open gates.

The arm remains in the `BARE_JAW` configuration. Its current verified state is
`KEYBOARD_FORWARD_CAL_1`, with measured servo positions
`[2052, 2149, 1956, 2550, 2227, 2041, 2042]`. This is the first existing pose
on the recorded reverse chain where the camera decoded all six installed tags
in one frame. Ruler photographs support a provisional rigid-jaw clearance of
`20 +/- 2 mm` above the key surface. The observed physical arrangement is
accepted for this workcell epoch. No key contact or keypress has been performed.

The machine-readable snapshot is
`software/config/live_camera_feedback_session_20261015.json`. The two ruler
photos remain external to the repository; the snapshot records their names,
sizes, and SHA-256 digests without adding large media to source archives.

## Existing interfaces to reuse

The repository already has the required component boundaries. The integration
must compose them rather than create an unrelated camera-to-serial shortcut.

| Stage | Existing interface | Intended use |
|---|---|---|
| Physical capture | `rocell.vision.usb_opencv.UsbOpenCvCamera` | Open one reviewed persistent device, request an exact mode, read back the negotiated mode, and acquire bounded frames. |
| Camera onboarding | UVC inventory, camera receipt, physical capture workflow, and B0477 profile contracts | Bind physical identity, mode, manual controls, reconnect behavior, and retained evidence. |
| Pixel interpretation | Existing AprilTag detector records and `PlanarAprilTagBoardPoseEstimator` | Produce typed detections and a camera-to-board pose with residual and uncertainty evidence. |
| Target geometry | Keyboard target catalog and `KeyboardCompiler` | Resolve a semantic key to one board-frame target under one catalog hash. |
| Model proposal | `ModelMotionProposalV2` and `intent_to_hover` | Bind frame/image/model/calibration evidence to a hover-only target proposal. |
| Tool separation | `CalibratedActionRegistry` and `AttachmentProfile` | Require the exact active attachment; prevent bare-jaw/stylus pose inheritance. |
| Motion boundary | Reviewed request, first-motion admission, transport gate, and named pose controller | Admit one bounded command only after all predecessor evidence is current. |
| Feedback | `TelemetryStream` plus post-motion camera capture | Verify settled joint state and independently observed spatial outcome. |

Historical camera manifests still describe older eye-on-arm candidates. The
active route is the external static-camera architecture introduced by the
commercial-tripod migration. The connected device must be identified before it
is associated with the B0477 profile or any other camera profile.

## Closed-loop architecture

The first live implementation must use **stop, settle, observe, decide, then
move once**. Host receipt timestamps are insufficient for in-motion correction,
so continuous visual servoing stays out of scope until exposure and controller
timestamps are independently synchronized.

```text
reviewed camera identity + locked mode/controls
                    |
             finite frame capture
                    |
       decode -> rectify -> detect fiducials
                    |
       camera-to-board pose + uncertainty
                    |
       keyboard target in board coordinates
                    |
 hover-only proposal bound to frame/calibration hashes
                    |
 attachment-profile + freshness + collision/simulation gates
                    |
          one reviewed noncontact command
                    |
        settle telemetry + later verification frame
                    |
      accept result or stop for human review
```

No image-processing component receives serial transport authority. No motion
component may silently acquire a fresher image, replace calibration, change the
tool profile, retry a rejected proposal, or promote `HOVER` to `CONTACT`.

## Implementation sequence

### 1. Freeze the physical configuration

- Preserve the accepted physical arrangement for the current workcell epoch.
- Keep the base, board, keyboard, fiducials, camera support, focus, aperture,
  cable routing, and lighting fixed.
- Assign a workcell epoch. Any change creates a new epoch and invalidates the
  camera-to-board registration and previously compiled trajectories.
- Photograph the camera/support, full board coverage, secured jaw cable, and
  ruler reference. Retain files outside Git and record content hashes.

Exit: a reviewed physical-state manifest with zero movement.

### 2. Identify and qualify the camera connection

- Enumerate the persistent USB identity and all reported modes without using a
  numeric camera index as identity.
- Record manufacturer/model markings, serial or persistent path, host bus,
  cable, support, and whether the device actually matches the B0477 profile.
- Select one finite capture mode, read back width, height, frame rate, FOURCC,
  and manual controls, then repeat after close/reopen.
- Capture a small bounded set of frames; reject stale, duplicate, truncated,
  unexpectedly converted, or auto-control-drifting frames.

Exit: exact identity/settings receipts and finite snapshots. Arm motion remains
disabled.

### 3. Lock optics and field of view

- Lock focus, aperture, exposure, gain, white balance, resolution, pixel format,
  and orientation.
- Verify the keyboard and all six registration fiducials remain visible with
  margin through normal lighting, glare, and arm-occlusion cases.
- Record working distance, support pose, cable load, image orientation, and the
  selected native and working pixel spaces.

Exit: reviewed optics/coverage report. One attractive image is insufficient.

### 4. Measure the installed board-plane registration

- Use the already installed 610 by 457 mm board and its six tag36h11 markers;
  no additional printed target is required for this planar mapping.
- Bind the 40 mm detection edge, measured tag centers, common +Y/rear marker
  orientation, camera identity, operational stream settings, workcell epoch,
  capture receipt, and every retained frame hash.
- Fit IDs `0-3` as the perimeter anchors. Reserve interior IDs `4-5` as checks
  so registration error is observed independently of the fit.
- Recompute with `software/scripts/measure_fixed_board_registration.py`. The
  2026-10-16 result uses seven fit-eligible frames and 112 perimeter corners;
  its fit RMSE is 5.3948 px. Twenty held-out center checks have 4.8330 mm mean
  and 7.4937 mm maximum error. Mapped-center repeatability is at most 0.6474 mm.
- Bind the resulting image-to-board and board-to-image matrices to the fixed
  epoch. Any camera, support, board, keyboard, or fiducial movement invalidates
  them.

Exit: a reproducible, read-only board-plane mapping with measured held-out
residuals. It supports keyboard projection work but does not establish full
intrinsics, distortion, off-plane Z, board-to-robot registration, or motion
authority. Full lens characterization can be added later if its residual budget
is required; it is not a prerequisite for using the measured fixed plane.

### 5. Prove camera-only keyboard localization

- The retained `reopen-01-frame-04.jpg` housing outline was reviewed against
  the known 315 by 147 by 21 mm PERIBOARD-409 candidate dimensions. The fitted
  image quadrilateral establishes the keyboard plane. All 43 alphanumeric
  keycap centers plus Tab, Enter, and Space are individually reviewed in the
  retained image. This removes the one-key horizontal offset produced by the
  earlier endpoint-only interpolation and corrects the synthetic catalog's
  14.5794 mm mean and 20.0384 mm maximum center offset. The source annotation,
  housing lines, 46 key centers, frame hash, and 3 px annotation tolerance are versioned in
  `software/config/b0477_keyboard_overlay_annotation_20261016.json`.
- Directly applying the board-plane homography to the elevated keyboard makes
  the housing appear 333.9-337.4 mm wide and 170.0-171.4 mm deep. Constraining
  that observation to the known housing size gives a provisional front-left
  board position of `(69.367, 86.447) mm` and yaw of `0.2932 deg`. The maximum
  housing-corner residual is 16.8566 mm, which records the visible parallax
  rather than hiding it.
- The 30 mm board-XY study margin covers the additive 25.7953 mm review bound:
  7.4937 mm held-out board-mapping error, 16.8566 mm housing-fit residual, and
  1.4450 mm conservative conversion of the pixel annotation tolerance.
- Phase correlation over the keyboard ROI across all ten retained frames shows
  at most 0.0616 px radial shift. This proves the saved fixed-frame overlay is
  repeatable for offline review. The least-squares row pitches range from
  18.7339 to 19.1062 mm, and the largest individually reviewed center residual
  from its row fit is 0.2699 mm. These are image-derived centers rather than
  product metrology.
- Recompute the result with
  `software/scripts/measure_fixed_camera_keyboard_overlay.py`. The compact
  numeric evidence is
  `software/ai/eval/b0477_keyboard_overlay_20261016.json`; an optional preview
  can be written outside Git with `--preview`.

Exit: the fixed-frame keyboard overlay is complete for retained-image review.
No robot command was generated, the camera was not reopened, and the result has
no motion authority.

### 6. Join observation to a dry-run hover proposal

- Create a coordinator that accepts an already retained frame receipt,
  calibration hashes, workcell epoch, target catalog, and explicit attachment
  profile.
- Compile only `HOVER` proposals. Bind the image, detector, pose, calibration,
  target catalog, tool profile, and planner/simulation results by SHA-256.
- Reuse the consolidated intent-to-hover and collision rehearsals to generate
  an unsent command package.
- Exercise wrong device, wrong model, old frame, changed camera pose, changed
  keyboard, changed tool, missing tag, excess residual, and target-outside-frame
  failures.

Exit: deterministic dry-run receipts. Serial writes remain zero.

Completed for the retained `H` target on 2026-10-16. The maintained
`model_motion_bridge` retained-target mode verifies the exact workcell epoch,
retained-frame, annotation, board-registration, overlay, target-catalog, and
tool-profile hashes before it creates a proposal. It accepts `HOVER` only and
requires the explicit `BARE_JAW` profile. The resulting proposal resolves the
reviewed image center to board surface coordinates
`(212.951, 149.210, 21.000) mm` and records a provisional hover destination at
`(212.951, 149.210, 48.7953) mm`. The clearance is the recorded 25.7953 mm
overlay review bound plus the 2.0 mm jaw-clearance uncertainty.

The receipt is embedded under `retained_hover_draft` in
`software/config/live_camera_feedback_session_20261015.json`. Its status is
`UNSENT_RETAINED_EVIDENCE_HOVER_DRAFT_BLOCKED_FROM_INGRESS`; observation
confidence remains `0.0`, controller commands are empty, and transport writes,
hardware access, physical authority, descent, contact, and autonomous retry are
all zero or false. Reproduce it without opening the camera or robot transport:

```powershell
$env:PYTHONPATH='software/src'
python -m rocell.application.model_motion_bridge `
  --workspace . `
  --retained-keyboard-target H `
  --workcell-epoch-id keyboard-bare-jaw-camera-intake-20261015
```

The retained frame has no current freshness lease, the planar mapping has no
qualified Z calibration, and the board-to-arm transform and bare-jaw TCP remain
uncommissioned for this target. Those blockers intentionally prevent this
artifact from entering the contact-only typing ingress or any controller path.

### 7. Observe the stationary arm

- With motion still disabled, capture the arm at its current named pose.
- Compare camera-derived geometry with recorded joint telemetry and the expected
  bare-jaw envelope.
- Establish whether the arm occludes required tags and whether the secured cable
  remains outside the planned swept envelope.

Exit: stationary observation agreement and visibility evidence.

### 8. Separately release one high noncontact move

This stage requires a new reviewed physical-motion request. Begin from a known
named pose and command one high hover with clearance greater than the combined
registration, arm, tool, keyboard-height, and cable uncertainty budget.

After the arm settles, capture telemetry and a new camera frame. Compare planned,
reported, and observed endpoints. Do not automatically correct or retry.

Exit: one reviewed noncontact result or a stopped failure record.

### 9. Add bounded stop-and-look correction

Only after repeated high-hover results pass may a later increment compute one
small correction from the post-settle frame. Bound translation, rotation,
velocity, total attempts, and cumulative displacement. Every correction is a
new proposal and a new one-use authorization. Any disagreement stops the run.

Contact, pressing, continuous visual servoing, and unattended retries remain
separate future qualifications.

## Mandatory gates for every camera-guided proposal

1. Exact persistent camera identity, mode, controls, and orientation.
2. Current workcell epoch and unchanged support/keyboard/fiducial state.
3. Installed intrinsics and camera-to-board transform hashes.
4. Frame freshness, uniqueness, complete required tags, residual, and
   uncertainty acceptance.
5. Exact keyboard target catalog and coordinate-frame conversion.
6. Explicit `BARE_JAW` attachment profile; stylus remains blocked.
7. Hover-only interaction and positive clearance above the full uncertainty
   budget.
8. Current collision, route, controller, and telemetry checks.
9. One reviewed command, no autonomous retry, and retained pre/post evidence.
10. Post-settle telemetry and camera verification before another command.

## Evidence package per attempt

Retain a manifest-last package containing camera identity/settings, raw frame
hashes, decoded/rectified image hashes, detections, pose and uncertainty,
calibration and target-catalog hashes, attachment profile, proposal, simulated
trajectory, reviewed command, telemetry, post-frame assessment, timestamps,
operator/reviewer identities, and explicit camera-frame, arm-write, movement,
and contact counts.

Large images remain in the reviewed external evidence store. Git retains the
canonical manifest, compact numeric results, and content hashes.

## Planned change sets

| Increment | Deliverable | Physical authority |
|---|---|---|
| A | This baseline and integration plan | None |
| B | Read-only camera identity, exact mode/control probe, finite capture receipt | Camera capture only after explicit operator action; arm disabled |
| C | Physical intrinsics and static-registration dataset/assessment | Camera capture; arm disabled |
| D | Observation-to-hover dry-run coordinator and fault tests (complete for retained `H`) | None; unsent commands only |
| E | Stationary-arm camera/telemetry comparison | Read-only camera and arm telemetry |
| F | Separately reviewed single high-hover validation | One bounded noncontact command |
| G | Stop-and-look correction qualification | One newly authorized bounded correction at a time |
| H | Stylus TCP, geometry, and new trajectories | Blocked pending installed stylus measurements |

## Immediate next review

Increment D now binds the retained `KEYBOARD_FORWARD_CAL_1` frame, measured
board registration, reviewed 46-target keyboard overlay, target catalog,
workcell epoch, and explicit `BARE_JAW` profile into one deterministic unsent
`HOVER` draft. Fault coverage rejects stale epochs, changed overlay or frame
hashes, missing targets, attachment-profile changes, and contact requests.

The stationary-arm observation is now complete. The next increment is
calibrated route screening. It must add a current scene lease, qualified Z evidence,
board-to-arm correlation, bare-jaw TCP qualification, IK, joint-limit and
collision screening, and controller/telemetry checks before any separately
reviewed noncontact movement can be proposed. The recorded draft itself remains
non-executable and requires no target printing or arm movement.

## 2026-10-16 stationary observation checkpoint

Two new five-frame camera-only captures bracketed one guarded arm-telemetry
preflight while the arm remained untouched at the recorded
`KEYBOARD_FORWARD_CAL_1` context. Both captures retained the exact B0477 device
identity, `1920x1080` YUY2 mode, and settings hash. Every frame hash was unique.
The first capture decoded all six installed tags in four frames; the second did
so in three. Every tag supplied at least three samples.

`measure_fixed_board_registration.py` now has a no-refit stationary-observation
mode. It maps fresh tag centers through the retained fixed-epoch homography and
compares them with the retained per-tag means. The declared bound is 2.0 mm.
The two observed maxima were 1.3973 mm and 1.3109 mm, so both camera scenes agree
with the retained camera/board epoch. This is a scene-stability result only.

The corrected transport path verified that installed r120 is USB serial-only,
then used the owned one-shot feedback worker. It opened the exact CP210x unit on
COM4 once, wrote the exact 10-byte T105 request once, received one 142-byte
T1051 line, and closed cleanly. The controller reported
`KEYBOARD_FORWARD_CAL_1`, positions
`[2052, 2149, 1956, 2550, 2227, 2041, 2042]`, `motion_active=false`, and
`trajectory_progress_permille=1000`. Those fields match the retained last
verified pose and establish stationary arm agreement for this checkpoint.

The worker initially classified the response as incomplete because it expected
the vendor Cartesian response fields. The exact retained line was reclassified
offline after adding a strict r120 named-pose schema. No second T105 request was
sent. This establishes a stationary observation, not calibrated joint angles,
board-to-arm geometry, route safety, or motion authority.

Reproduce either camera assessment without opening a camera or robot transport:

```powershell
.\.venv-vision\Scripts\python.exe `
  software/scripts/measure_fixed_board_registration.py `
  --frames-directory <finite-capture-directory> `
  --reference-registration `
  software/ai/eval/b0477_fixed_board_registration_20261016.json `
  --maximum-reference-center-shift-mm 2.0 `
  --minimum-samples-per-tag 3 `
  --output <ignored-runtime-observation.json>
```

The compact hashes and verdicts are retained in
`software/config/live_camera_feedback_session_20261015.json`; the raw frames and
reports remain ignored runtime evidence. The next gate is offline board-to-arm,
bare-jaw TCP, IK, joint-limit, and collision screening against a fresh scene
lease. No high hover is admitted by this checkpoint.

## 2026-10-16 current planar observation handoff

`observe_current_planar_keyboard.py` closes the read-only handoff from a fresh
camera capture to the existing model-motion draft. It accepts a finite capture
only after the no-refit stationary comparison agrees with the retained epoch.
It then fits a current board homography from world tag IDs 0-3, uses IDs 4-5 as
independent station checks, and projects all 46 reviewed keyboard targets into
one hash-bound saved frame. The rendered overlay is adjusted to the current
view instead of copying reference-frame pixels.

The model-motion bridge can bind that artifact with
`--current-planar-observation`. The result includes the selected target's
current pixel center and region alongside the existing board-frame hover draft.
It still emits no controller commands and cannot enter motion ingress. Current
arm telemetry, physical intrinsics for off-plane use, board-to-arm calibration,
bare-jaw TCP, IK, joint-limit, and collision screening remain required.

The first live use retained ten unique frames in ignored runtime directory
`live-camera-planar-feedback-20261016-03`. Three frames decoded all six tags and
every tag supplied at least three samples. The no-refit comparison measured a
maximum 1.5494 mm reference-center shift, inside the established 2.0 mm scene
bound. The selected six-tag frame produced a 6.9298 px world-corner RMSE; held
out station checks were 4.855 px for ID 4 and 14.324 px for ID 5. All 46 target
regions were rendered. The current `H` center is `(706.572, 670.911)` px and
maps to the retained board target `(212.951, 149.210, 21.000)` mm. The resulting
draft contains one unsent hover destination and no controller commands. The
capture receipt, stationary comparison, current observation, rendered overlay,
and `H` draft are hash-bound in that ignored runtime directory.

Reproduce the observation from a bounded saved capture:

```powershell
.\.venv-vision\Scripts\python.exe `
  software/scripts/observe_current_planar_keyboard.py `
  --frames-directory <finite-capture-directory> `
  --stationary-observation <stationary-observation.json> `
  --output <current-planar-observation.json> `
  --render <current-planar-overlay.jpg>

$env:PYTHONPATH = "software/src"
.\.venv-vision\Scripts\python.exe -m rocell.application.model_motion_bridge `
  --workspace . `
  --retained-keyboard-target H `
  --workcell-epoch-id keyboard-bare-jaw-camera-intake-20261015 `
  --current-planar-observation <current-planar-observation.json>
```

## 2026-10-16 current bare-jaw route-screening intake

`build_current_bare_jaw_route_intake.py` now joins the current planar
observation, its unsent `H` hover draft, and the retained bare-jaw route audit.
The join is strict: all three artifacts must have valid embedded digests, one
workcell epoch, the explicit `BARE_JAW` profile, the same saved frame, the same
pixel target, and the same board target. The current frame must contain IDs
`0-5` and all 46 reviewed keyboard targets.

The first live intake used the ignored runtime evidence in
`live-camera-planar-feedback-20261016-03`. It bound current `H` pixel center
`(706.572, 670.911)` to surface point
`(212.951, 149.210, 21.000)` mm and hover point
`(212.951, 149.210, 48.7953)` mm. Its deterministic status is
`BLOCKED_ARM_SPACE_CALIBRATION_REQUIRED`. Current planar camera localization is
complete for the saved frame, while the arm start is still the retained settled
register sample and is not synchronized to that frame. Board-to-arm projection,
IK, route, and collision screening did not run.

Reproduce the join without opening either device:

```powershell
$env:PYTHONPATH = "software/src"
python software/scripts/build_current_bare_jaw_route_intake.py `
  --current-observation <current-planar-observation.json> `
  --hover-draft <current-h-hover-draft.json> `
  --output <current-bare-jaw-route-intake.json>
```

The output records the remaining arm-space requirements explicitly: a current
telemetry binding, measured robot joint reference, controller-to-model
correlation, board-to-arm transform, qualified keyboard Z/normal/travel,
bare-jaw TCP, and installed collision geometry. The formal static-camera graph
also retains its full physical camera-chain requirement; this does not undo the
completed current board-plane localization or grant off-plane calibration.
Changing to the stylus invalidates this intake and starts its separate profile
and trajectory family.

## 2026-10-16 bare-jaw route-readiness audit

The deterministic zero-dispatch audit at
`software/ai/eval/bare_jaw_route_readiness_20261016.json` reconciles the
retained physical session with the earlier Issue 190 reachability studies. It
reuses the measured 610 x 457 mm board, the six installed 40 mm tags and their
recorded centers, the dimension-constrained 315 x 147 x 21 mm keyboard, all 46
reviewed target centers, the H surface point `[212.951, 149.210, 21.000]` mm,
the H hover point `[212.951, 149.210, 48.795]` mm, and the settled r120 register
sample `[2052, 2149, 1956, 2550, 2227, 2041, 2042]`.

The register sample is retained as controller registers, not relabeled as
model joint radians. The earlier blocked 100/110/120 mm studies and the passing
120 mm promoted-transform study remain sensitivity bounds because their tool,
transform, and start state were nominal or synthetic. They therefore do not
support an installed-workcell unreachable conclusion.

The audit now consumes the additive
`static-overhead-b0477-phase1.v1` calibration graph. That graph matches the
retained `STATIC_EXTERNAL_CAMERA` architecture and leaves the historical
eye-on-arm graph unchanged. The keyboard TCP route closure contains eleven
ordered physical artifacts: camera identity, mode, settings, intrinsics,
measured tag map, static extrinsic, robot reference, controller correlation,
arm-to-board transform, keyboard target map, and keyboard TCP. Independent
keyboard outcome observation is the twelfth artifact in the full contact
closure; it is recorded separately because this audit stops at hover-route
screening.

All eleven route artifacts are currently missing from the physical calibration
registry. The retained board, tag, and keyboard measurements remain reusable
inputs, but they do not silently populate those authenticated artifact slots.
The installed collision intake also reports missing robot link geometry and
unqualified attachment/base bodies. Once those inputs are populated, the
existing measured trajectory and collision pipeline can rerun against the
retained H target. The attachment policy remains explicit: changing from
`BARE_JAW` to `STYLUS` invalidates the trajectory, starts a new configuration
epoch, and permits no pose or contact authority inheritance. The audit opens no
device, emits no command, and grants no physical authority.

### Retained-evidence coverage

`software/ai/eval/static_phase1_retained_evidence_coverage_20261016.json`
now maps every retained measurement and observation to the twelve-artifact
static keyboard closure. The mapping records reusable facts and the exact
evidence still needed for acceptance without creating a calibration artifact
or writing the physical registry.

Nine of the eleven hover-route artifacts have partial retained candidates.
They reuse the exact B0477 identity and negotiated mode, six installed tag
centers on the 610 x 457 mm board, fixed planar registration, 46 reviewed key
centers, the `KEYBOARD_FORWARD_CAL_1` controller-register observation, the
active `BARE_JAW` profile, and the ruler-photo clearance receipts. The two
hover-route artifacts with no retained candidate are
`phase1_static_intrinsics` and `phase1_arm_board`. The separate
`phase1_keyboard_outcome_observer` contact dependency also has no retained
candidate.

This coverage record requests no repeated measurement. Future collection can
start with the named remaining acceptance evidence in prerequisite order. A
change to `STYLUS` uses a separate attachment profile and configuration epoch,
so its TCP, collision geometry, trajectory, and contact qualification are
collected independently.

### Physical intrinsics intake

`software/ai/eval/static_phase1_intrinsics_intake_plan_20261016.json` turns the
first missing route artifact into a deterministic, zero-capture collection
plan. It binds the retained installed mode exactly: `1920x1080`, YUY2, at
`60.000240000960005` fps, with settings SHA-256
`68de0820caeb41a79508ffe613f438dc06fa2303422676fa6a9f1d2943cb0c15`.
The purchased camera profile confirms that this mode is supported and the two
retained open cycles report the same mode and settings identity.

The existing synthetic intrinsics rehearsal remains useful for testing the
software path, but its `5472x3648`, 9 fps fixture is ineligible as physical
intrinsics for this installed runtime. The physical dataset must use the
retained runtime mode, precommit its fit and held-out split, retain immutable
source hashes and regional coverage, and report the selected distortion model,
camera matrix, fit residuals, held-out residuals, ROI/crop, undistortion map,
and stability evidence.

No new target print or repeated board/tag-center measurement is requested. An
existing target may be used once its scale and metric definition are verified.
Capture remains held until the received optical-stack identity and locked
manual-control readback are complete. The plan opens no camera, writes no
registry entry, sends no robot command, and grants no physical authority.

The target reconciliation artifact
`software/ai/eval/static_intrinsics_target_reconciliation_20261016.json`
preserves the completed board metrology as an input rather than treating it as
missing: the board is `610 x 457` mm, the installed family is `tag36h11`, the
detection edge is `40` mm, the tile edge is `55` mm, and the six measured tag
centers remain bound exactly. Those measurements continue to support the fixed
image-to-board planar registration and do not need to be repeated.

That fixed camera/fixed board epoch contains one plane pose, so it cannot by
itself constrain focal length and lens distortion. The remaining input is one
existing movable planar target. The intake accepts either a ChArUco target with
its dictionary and metric square/marker definition or an AprilTag grid with
ordered IDs and metric corner coordinates. Its identity, two-axis scale, flat
backing, and unchanged use across the precommitted views must be retained before
slot 01 is captured. The camera, installed board, and arm remain fixed while
only that target is presented at the scheduled poses.

## 2026-10-15 read-only intake result

The explicit camera-only intake identified one present Windows Camera-class
device named `Arducam B0477 (USB3 20MP)` with PnP instance ID
`USB\\VID_04B4&PID_0477&MI_00\\8&257B140A&0&0000`. The maintained command
`software/scripts/live_camera_read_only_intake.py` requested `1920x1080`,
`60 fps`, `YUY2` through DirectShow. Two open/capture/close cycles read back
the same mode and settings hash. All four retained frames had distinct SHA-256
digests, and the adapter released the camera after each cycle.

The frames are visibly illuminated and show the keyboard and all six installed
tag tiles. A second pixel review found that the original default-only detector
under-reported coverage. Combining the default profile with a bounded
AprilTag-refinement profile produces valid tag36h11 decodes for IDs `0, 1, 2,
3, 5` across the retained set. Two retained frames contain all four world-pose
tags `T0-T3` in the same exposure, and station-check tag `P0` is decoded in the
set.

The remaining tag-4/K0 tile is physically present, but its encoded square lies
behind the stationary arm near the board center; only a partial edge is exposed
in the camera pixels. It therefore cannot supply the independent K0 decode
required by the six-tag policy. The separate `5472x3648` YUY2 check does not
resolve an occluded code. Registration, camera-guided motion, robot transport,
descent, and contact remain false.

The reviewed external receipt is
`software/runs/wizard-exports/live-camera-intake-20261015-04-maintained/receipt.json`
with SHA-256
`e724228e117ea1423540094a5709b5f041d238c43729165d70a1958033132bda`.
The runtime directory is intentionally ignored by Git; the machine-readable
session snapshot retains its path and digest.

Reproduce the bounded capture from the repository root with the vision
environment:

```powershell
.\.venv-vision\Scripts\python.exe software/scripts/live_camera_read_only_intake.py `
  --pnp-instance-id "USB\VID_04B4&PID_0477&MI_00\8&257B140A&0&0000" `
  --friendly-name "Arducam B0477 (USB3 20MP)" `
  --selector 0 --width 1920 --height 1080 --fps 60 --fourcc YUY2 `
  --reopen-count 2 --frames-per-open 2 `
  --output-directory software/runs/wizard-exports/<new-directory> `
  --confirm-camera-only-capture
```

The recorded adjacent reverse chain established
`KEYBOARD_FORWARD_CAL_1` as the neutral bare-jaw camera observation pose. At
that pose, five of ten frames decoded all six tags; the remaining five decoded
IDs `1-5`. The retained receipt is
`software/runs/wizard-exports/live-camera-observation-forward-cal-1-20261015-01/receipt.json`
with SHA-256
`9560ea22b6b9281fa6f8494ccac948f0306764142c30e45d4f937b035067f8cb`.
Any camera, support, focus, board, keyboard, fiducial, or attachment change
starts a new workcell or optics epoch. Electronic control readback and exact
DirectShow endpoint binding remain open qualification items.

The repeat external receipt is
`software/runs/wizard-exports/live-camera-observation-forward-cal-1-repeat-20261015-02/receipt.json`
with SHA-256
`32a7348c78aee8ba437ec14a82daa8e1a1a0679d8d237b165e9a0fa5123b6db8`.
Eight of ten retained frames decoded IDs `0-5`; the other two decoded IDs
`1-5`. All frame hashes were unique and the negotiated settings hash was
unchanged across both reopen cycles. Robot transport remained unopened.

## 2026-10-16 locked electronic-control checkpoint

The installed B0477 is bound to the exact PnP identity above and DirectShow
endpoint recorded in
`software/ai/eval/b0477_locked_controls_qualification_20261016.json`. The
qualified manual values are brightness `0`, contrast `10`, saturation `10`,
white balance `4500`, gain `500`, and exposure `-3`. Two camera reopen cycles
produced six unique `1920x1080` YUY2 frames with an unchanged settings hash.
Mean luma stayed from `108.1087` to `109.1030`; Laplacian variance stayed from
`71.8410` to `72.6440`; highlight clipping remained below `0.000017`. Four of
six frames decoded every required tag and the full set decoded IDs `0-5`.

The earlier dark manual-control trials were restored before this retained
qualification and are not treated as accepted settings. Focus and aperture do
not expose electronic DirectShow controls, so their mechanical identity and
witness marks remain open. Reopen persistence does not establish persistence
through a physical reconnect or host reboot.

The next physical-intrinsics step uses an existing scale-verified target and a
precommitted multi-view fit/held-out manifest. A fixed overhead view of one
coplanar tag arrangement establishes visibility and stability, but does not
independently solve intrinsics. The target must be presented at varied center,
edge, corner, distance, and tilt views while the camera and board remain fixed.
No new target print or repeated board/tag-center measurement is required.

### Precommitted multi-view dataset

`software/ai/eval/static_intrinsics_multiview_capture_contract_20261016.json`
freezes 32 capture slots before physical calibration: 24 training and 8 held
out. The schedule covers nine image regions, three tilt bands, four rotation
bands, and two apparent-area bands. A minimum of 20 training and 6 held-out
views must remain after review. Fixed-pose duplicates are ineligible, rejected
slots cannot change split, and every accepted image must retain its source hash
and observed target geometry before fitting.

During this collection the installed camera and board remain fixed; only the
existing target moves. Capture remains blocked until that target's immutable
identity, metric feature definition, two-axis scale measurements, and rigid
flat backing are recorded. This contract requests no new print and opens no
camera or robot transport.
