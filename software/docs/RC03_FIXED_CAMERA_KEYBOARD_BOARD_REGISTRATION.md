# RC03 fixed-camera keyboard-to-board registration boundary

## Why this boundary is required

The fixed-camera evidence now shows that all 46 observed keys form a coherent
layout in the elevated 315 x 147 mm keyboard plane. The provisional Z=0 board
homography cannot determine that plane's absolute board translation. A
constrained model inferred from the same homography also fails the observed
housing corners at roughly 34 mm RMS and 47 mm maximum error, so it is not an
acceptable substitute for measured 3-D evidence.

`rocell.vision.fixed_camera_keyboard_board_registration_v1` implements the
next boundary. It accepts either:

- an accepted 3-D camera-model measurement artifact; or
- independently reviewed board-frame measurements.

The input must bind the elevated-plane result and target profile by SHA-256 and
provide at least three unique anchors whose local geometry spans both keyboard
axes. Anchors may identify any modeled key center or one of the four housing
corners. The fitter rejects collinear anchors, excessive RMS or individual
residuals, mismatched evidence kinds, changed prerequisite bytes, incomplete
key geometry, and any registered key outside the 610 x 457 mm board.

## Output and profile separation

An accepted fit emits 46 board-space **localization candidates**. It emits no
robot-base target and grants no motion or contact authority.

| Profile | Shared perception result | Remaining profile gates |
| --- | --- | --- |
| `no_attachment` | Absolute keyboard-to-board candidate | Board-to-robot transform and installed clearance |
| `stylus_attachment` | Same keyboard-to-board candidate | Board-to-robot transform, installed clearance, stylus TCP, and stylus trajectory qualification |

This keeps the camera/keyboard transform independent from tool geometry while
preserving the separate attachment trajectories requested for the workcell.

## Current state

The contract and rejection behavior are implemented and tested. No current
artifact satisfies its evidence input. The rejected ChArUco intrinsics and the
single-plane homography are retained as negative evidence and cannot be passed
off as either accepted source kind.

The next accepted evidence can come from a valid final-camera 3-D calibration
or independent board-frame anchors. No additional paper target is required if
an accepted camera model or independent anchors are obtained through another
qualified method.

## No-print anchor workflow

`rocell.vision.fixed_camera_keyboard_anchor_package_v1` prepares and consumes
the independent-anchor path. Create a local draft from the repository root:

```powershell
$env:PYTHONPATH = "software/src"
python -m rocell.vision.fixed_camera_keyboard_anchor_package_v1 `
  --write-template keyboard-anchors.json
```

Record board-frame X/Y in millimetres for at least three named housing corners.
The frame is `RC03_board`: X begins at the board's left edge and Y begins at its
front edge. Change the draft status to
`REVIEWED_INDEPENDENT_BOARD_FRAME_MEASUREMENTS`, record the reviewer and an
offset-bearing ISO-8601 review time, and then compile both profiles together:

```powershell
python -m rocell.vision.fixed_camera_keyboard_anchor_package_v1 `
  keyboard-anchors.json `
  software/config/calibration_candidates/rc03_int_r1_fixed_camera_elevated_key_plane_validation_2026-10-17.json `
  software/config/static_nominal_target_profiles.json `
  > keyboard-board-registration-package.json
```

The builder hashes the exact measurement, elevated-plane validation, target
profile, and generated registration input. It rejects drafts, missing review
metadata, changed board dimensions, non-millimetre coordinates, invalid anchor
geometry, out-of-board anchors, loosened 3 mm RMS or 5 mm individual-anchor
limits, or excessive fit residuals. The resulting package evaluates
`no_attachment` and `stylus_attachment` from the same keyboard transform while
retaining their separate downstream blockers. It cannot authorize motion or
contact.

## Board-to-robot handoff

`rocell.vision.fixed_camera_keyboard_robot_localization_v1` implements the
next fail-closed boundary. It consumes a ready keyboard registration package,
the exact bound target profile, and independently reviewed 3-D
`RC03_board`-to-`robot_base` correspondences. At least three fit points must
span both board axes, at least two separate held-out points are required, and
the unchanged-installation and reseat checks must pass. The governed limits are
3 mm fit RMS, 5 mm maximum fit residual, and 5 mm maximum held-out residual.

Create the local measurement draft without printing another target:

```powershell
$env:PYTHONPATH = "software/src"
python -m rocell.vision.fixed_camera_keyboard_robot_localization_v1 `
  --write-template board-to-robot-measurements.json
```

After the measurement contract has independent review, compose it with the
keyboard package and exact target profile:

```powershell
python -m rocell.vision.fixed_camera_keyboard_robot_localization_v1 `
  board-to-robot-measurements.json `
  keyboard-board-registration-package.json `
  software/config/static_nominal_target_profiles.json `
  > keyboard-robot-localization.json
```

A passing result maps all 46 key centres at the profile's 21 mm target plane
into `robot_base` as localization candidates. The result still emits no motion
target and cannot authorize motion or contact. Installed continuous clearance
remains open for both profiles; the stylus profile additionally retains its
own TCP and trajectory blockers.

## Passive camera and robot capture workflow

`rocell.calibration.fixed_camera_robot_calibration_capture_v1` prepares the
remaining board-to-robot measurements without asking for more ruler readings.
It consumes retained records only and performs no camera, robot, or filesystem
I/O. Each capture binds one exact fixed-camera frame to:

- a board pose fitted from RC03 tags `0` through `3`, with tags `4` and `5`
  retained as independent residual checks;
- a calibrated bare-jaw reference observation in `RC03_board` coordinates;
- raw T=1051 feedback immediately before and after the frame; and
- the pinned RoArm-M3 firmware kinematic reference.

The compiler requires the camera frame to fall inside the feedback bracket,
reproduces the robot endpoint from all six feedback joint fields, compares the
reproduced endpoint with the controller-reported XYZ, and rejects movement,
timing, identity, settings, intrinsics, tag-map, or detector drift. A campaign
requires at least three noncollinear fit captures and two held-out captures
from one unchanged installation epoch. Its output is an exact
`board_to_robot_measurements.v1` **draft** plus the hashes of every normalized
capture. The installation and review flags remain false so the existing
localization boundary cannot consume the draft until the evidence is reviewed.

This workflow uses `no_attachment` because the board-to-robot transform is
shared workcell geometry. Installing the stylus does not create a second board
transform. It requires a separate measured stylus TCP and installed-clearance
profile, which remain bound by the attachment-aware handoff below.

The capture and aggregation contracts are established. The bare-jaw observer
and audited landmark adapter are also implemented, but their physical rigid
landmark model and qualified landmark/pose source are not retained. Qualified
live camera acquisition, retained robot feedback acquisition, and collection
of the five spatially separated samples remain the next integration step. No
manual board dimension, tag spacing, keyboard size, or key-plane measurement
needs to be repeated.

Retained capture files can now be checked directly. A single record is compiled
with no hardware access as follows:

```powershell
$env:PYTHONPATH = "software/src"
python -m rocell.calibration.fixed_camera_robot_calibration_capture_v1 `
  capture-fit-a.json `
  --expected-sha256 <exact-file-sha256>
```

After collecting three spatially separated `FIT` records and two separate
`HOLDOUT` records, compile the campaign in one deterministic invocation:

```powershell
python -m rocell.calibration.fixed_camera_robot_calibration_capture_v1 `
  --campaign `
  capture-fit-a.json capture-fit-b.json capture-fit-c.json `
  capture-holdout-a.json capture-holdout-b.json
```

`--expected-sha256` may be repeated once per input, in the same order, to pin
the exact bytes. Files are bounded to 1 MiB, decoded as strict UTF-8 JSON, and
reject duplicate keys, non-finite values, malformed records, reused camera
frames, reused board-pose observations, and reused tool-reference
observations. The compiler still opens no camera or serial endpoint and emits
no robot command. Windows currently reports the intended installed devices as
Arducam B0477 and the RoArm CP210x bridge on COM4; this inventory is discovery
evidence only and does not qualify either endpoint.

### Read-only live acquisition boundary

`rocell.calibration.fixed_camera_robot_acquisition_v1` defines the missing
capture sequence used before the retained-file compiler. It accepts two narrow
provider surfaces: an already-open camera that can only be probed or captured,
and a feedback-only source that can only return one retained T=1051 sample. The
coordinator performs exactly:

1. one pre-frame T=1051 sample;
2. one camera frame with no retry; and
3. one post-frame T=1051 sample.

The reviewed permit binds the camera identity, settings, camera qualification,
feedback qualification, installation witness, and review record by SHA-256.
The complete camera request interval must lie inside the feedback timestamps on
one host clock and the full bracket must complete within one second. Joint,
forward-kinematic endpoint, and reported-XYZ drift use the same limits as the
passive compiler. The returned JPEG remains separate from its canonical bracket
so the owning application can retain the image without embedding it in JSON.

After board-pose and calibrated bare-jaw observations are computed from that
exact JPEG, `build_capture_input_v1` joins them to the bracket and runs the
existing passive compiler as the final compatibility check. This preserves one
validation source for fit tags 0–3, held-out tags 4–5, observation hashes,
timing, stationarity, and firmware kinematics.

The coordinator has no `open`, `close`, motion, torque, or contact operation and
is not registered with the current physical dispatcher. The active manifest
still represents the older moving-camera freeze, so
`SUPERSEDING_STATIC_CAMERA_FREEZE_NOT_PROMOTED` remains a deliberate blocker.
The installed B0477 identity and mode, feedback source, installation witness,
and review artifacts must be qualified before a physical application can create
the permit or call this boundary.

### Offline six-tag board-pose extraction

`rocell.vision.fixed_camera_board_pose_extractor_v1` supplies the missing
image-to-board-pose policy between the existing pixel detector and passive
capture compiler. It receives one immutable frame plus already configured
detector, rectifier, intrinsics, and the existing six-tag RC03 map. It opens no
camera and has no robot transport.

The extractor requires accepted `tag36h11` detections for all six station tags.
Tags `0` through `3` are copied into a separate pose-fit batch and all four must
remain inliers. Tags `4` and `5` are never supplied to the estimator; their
corners are projected through the completed pose and retained as independent
residual evidence. The default held-out maximum is 2 pixels. A result above
that limit remains inspectable but cannot produce the `board_pose` mapping
accepted by `fixed_camera_robot_calibration_capture_v1`.

The result binds the exact JPEG, full six-tag detection batch, rectified pixel
space, camera intrinsics, complete tag map, estimator configuration,
implementation, fit observation, and per-corner held-out residuals by SHA-256.
Later integration can capture at the camera's qualified native mode, rectify
detections into the calibrated pinhole space, and preserve the full board
breadth without repeating the board, keyboard, tag-spacing, or key-plane
measurements. This increment is deterministic offline software evidence; it
does not qualify the installed camera or promote the physical freeze.

### Retained six-tag detector and rectifier replay

`rocell.calibration.fixed_camera_tag_evidence_v1` supplies the retained-file
adapter for the board-pose extractor's two in-memory inputs. The caller pins
the exact JSON bytes. The record carries both the raw detector batch and the
reviewed rectified batch, along with source and destination pixel spaces and
the exact rectification configuration and implementation identities.

The loader requires both batches to bind the same complete frame metadata and
preserve every tag identity, acceptance decision, margin, hamming value, and
rejection reason. Rectification may change corner coordinates and detector
processing identity only. The returned object implements both `detect()` and
`rectify_detection_batch()`, but it replays only against the exact retained
`FramePacket` and exact retained raw batch. Its destination is fixed to
`UNDISTORTED_PINHOLE_PIXELS`, which is the pixel space required by the reviewed
native intrinsics.

This closes the retained six-tag integration seam in front of the existing
disjoint fit/holdout board-pose policy. It opens no device, emits no command,
and grants no motion, contact, calibration-review, or freeze-release authority.
The physical producer must still create the qualified native-frame detection
and rectification evidence.

### Native-frame observation composition

`rocell.calibration.fixed_camera_calibration_observation_v1` joins the retained
read-only bracket and image observations at one deterministic boundary. It
requires the complete B0477 `5472 x 3648` frame and a reviewed physical
intrinsics record bound to the same persistent camera identity, locked
settings, undistorted pinhole pixel space, rectification configuration, and
six-tag map. Cropped or resized Camera-app views are rejected; they remain
useful for operator framing but cannot become calibration evidence.

The coordinator runs the six-tag board-pose extractor, invokes an injected
offline calibrated bare-jaw observer on the same immutable frame, and delegates
the final record to `fixed_camera_robot_calibration_capture_v1`. This keeps the
fit/audit tag policy, feedback bracket, firmware kinematics, and residual limits
in their existing single sources of truth. The output is still an unreviewed
`no_attachment` correspondence. It cannot open either device, generate a
trajectory, or release `SUPERSEDING_STATIC_CAMERA_FREEZE_NOT_PROMOTED`.

The next physical prerequisite is therefore explicit: retain a native frame
from the qualified camera mode and produce the independently reviewed physical
intrinsics/rectification record plus calibrated bare-jaw detector evidence.
The established board dimensions, tag spacing, keyboard geometry, and 21 mm
key plane are reused and do not need to be measured again.

### Reviewed physical-intrinsics intake

`rocell.calibration.fixed_camera_physical_intrinsics_v1` closes the retained
file boundary in front of the native-frame coordinator. The caller must provide
the SHA-256 of the exact JSON bytes. The strict loader then binds:

- the persistent B0477 identity and locked settings;
- the exact `5472 x 3648 @ 9 fps YUY2` full-frame mode;
- the eight-coefficient OpenCV rational distortion solution;
- the rectified pinhole matrix and rectification configuration;
- the six-tag map, dataset manifest, and precommitted held-out split;
- the measured residuals and the reviewed acceptance limits; and
- distinct declared calibration-producer and reviewer identities, the
  offset-bearing review time, and independent review-record hash.

The record rejects failed residual limits, missing physical/native/full-frame
gates, a non-accept review decision, altered semantic integrity, or any camera,
robot, motion, contact, or release authority. A passing record is converted
directly into `ReviewedNativeIntrinsicsV1`, so the observation coordinator no
longer needs an application to assemble that binding from loose values.

The loader binds the declared reviewer and review record but cannot
authenticate the reviewer. The qualified calibration images, solver output,
and review still have to be produced and retained outside this zero-I/O
boundary. No additional board, tag, keyboard, or key-plane measurements are
required.

### Reviewed bare-jaw observer

`rocell.calibration.fixed_camera_bare_jaw_observer_v1` supplies the concrete
offline observer used by the native-frame coordinator. Its detector input is a
calibrated 3-D `bare_jaw_reference` point in the camera optical frame. The
observer deliberately refuses to manufacture depth from a single image pixel.
It applies the inverse `camera_optical_T_RC03_board` pose from the same frame
and returns the compiler's exact `CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE`
mapping.

The retained JSON calibration must be pinned by its exact file SHA-256 and
must bind the detector ID/version/configuration/implementation, reviewed
intrinsics, complete six-tag map, camera frame, bare-jaw reference model,
physical dataset, held-out millimetre metrics, uncertainty ceiling, and an
independent reviewer. The detector output repeats those bindings and the frame
hash. The observer adds the board-pose translation uncertainty conservatively
to the detector uncertainty and rejects a combined result above 3 mm or an
`X/Y` location outside the `610 x 457 mm` board.

`rocell.calibration.fixed_camera_bare_jaw_landmarks_v1` now supplies the
auditable adapter behind that detector contract. It requires the exact retained
jaw reference-model SHA-256 and a landmark/pose source whose detector,
configuration, and implementation identities match the reviewed calibration.
For every native frame it independently projects the rigid model through the
reviewed pinhole intrinsics. At least four predeclared `FIT` landmarks and two
separate `HOLDOUT` landmarks must be present; both groups must pass bounded
reprojection checks, every model landmark must appear exactly once, and every
point must remain in front of the camera and inside the full frame. Only then
does the adapter derive the camera-frame reference from the verified rigid
transform and emit `BareJawCameraObservationV1`.

`rocell.calibration.fixed_camera_bare_jaw_landmark_evidence_v1` supplies the
retained-file boundary in front of that adapter. The caller pins the exact file
SHA-256, and the strict loader rejects duplicate keys, nonfinite values,
unknown fields, altered semantic integrity, invalid transforms, and any
authority claim. The reconstructed pose source is usable only with the exact
capture ID, JPEG hash, camera settings, frame dimensions, camera frame, pixel
space, intrinsics hash, and reference-model hash recorded in the package. Its
receipt records those bindings and explicitly carries no release effect.

This package contains the complete rigid model and the same-frame landmark
estimate, so the future physical producer does not need an application-specific
in-memory bridge. An accepted record can build `AuditedBareJawLandmarkDetectorV1`
directly; that detector still performs all independent fit and holdout
reprojection checks before the reviewed observer can emit a board-frame point.

These boundaries close the evidence-verification and retention seams without
claiming the physical artifact exists or inventing jaw geometry from the
photographs. The remaining physical work is now narrower: produce and review
the exact rigid landmark model and detector calibration with disjoint views,
then retain each native-frame estimate in the strict package. The established
board, tag, keyboard, and key-plane dimensions do not need to be measured
again. None of these offline modules opens a camera, reads the robot, creates a
trajectory, or promotes the installation freeze.

## Attachment-aware clearance handoff

`rocell.application.fixed_camera_keyboard_clearance_intake_v1` connects a
passing robot-localization package to the existing installed collision and
typing-route pipeline. It requires two distinct measured installed collision
profiles: one reviewed as `BARE_JAW` for `no_attachment`, and one reviewed as
`STYLUS_INSTALLED` for `stylus_attachment`. The stylus binding also requires
the exact measured TCP artifact hash. Profile IDs and file hashes cannot be
reused across the two configurations.

Prepare the local binding worksheet after the robot-localization result exists:

```powershell
$env:PYTHONPATH = "software/src"
python -m rocell.application.fixed_camera_keyboard_clearance_intake_v1 `
  --write-template keyboard-clearance-profile-bindings.json `
  --robot-localization keyboard-robot-localization.json
```

The reviewed worksheet binds the exact localization bytes and both installed
profile files. The compiler then emits 46 profile-specific route-construction
inputs and names `typing_collision_intake_v1` as the downstream collision
evidence stage. It does not construct a trajectory or run a collision screen.
Continuous clearance, a fresh observed start state, and physical authority
remain false until their existing downstream gates pass.
