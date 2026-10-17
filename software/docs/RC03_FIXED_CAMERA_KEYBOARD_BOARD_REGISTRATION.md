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
