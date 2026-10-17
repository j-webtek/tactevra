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

The current increment establishes the capture and aggregation contract. Live
camera acquisition, the calibrated bare-jaw visual detector, retained robot
feedback acquisition, and collection of the five spatially separated samples
remain the next integration step. No manual board dimension, tag spacing,
keyboard size, or key-plane measurement needs to be repeated.

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
