# RC03 fixed-camera keyboard registration

## Result

One new 1920 × 1080 frame from the installed DirectShow camera was captured
after the board-plane candidate was accepted. AprilTag centers 1, 2, and 3
projected to their known board centers with 0.664 mm maximum center residual.
The two stationary audit tags moved by at most 0.431 camera pixel from their
original observations. This is strong evidence that the camera and board did
not move between the calibration and keyboard capture.

The controlled registration input is
[`rc03_int_r1_fixed_camera_keyboard_2026-10-17.json`](../config/calibration_candidates/rc03_int_r1_fixed_camera_keyboard_2026-10-17.json).
It binds the external frame by SHA-256 and byte length, the accepted board map,
the exact nominal keyboard profile, detected tag centers, and four reviewed
keyboard housing corners. The 3.19 MiB source image remains in the external
physical-evidence store.

## Keyboard estimate

The observed housing corners were projected through the board-plane map and a
315 × 147 mm rigid footprint was fitted to reduce the effect of viewing the
21 mm-high housing through a Z=0 homography. The fit places the keyboard's
front-left origin at approximately **[110.29, 68.29] mm** in the RC03 board
frame with **2.480° yaw**. Its housing-corner residual is **10.532 mm RMS** and
**13.380 mm maximum**.

That result supports a reproducible keyboard region and nominal key overlay.
The residual is larger than the declared 7 mm individual-key limit, so the
current artifact does not claim that a particular key center is localized well
enough for a hover or press. The generated 46 key centers remain nominal layout
projections.

## Reproduce

From `software/`:

```powershell
$env:PYTHONPATH = "src"
python -m rocell.vision.fixed_camera_keyboard_registration_v1 `
  config/calibration_candidates/rc03_int_r1_fixed_camera_keyboard_2026-10-17.json `
  config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json `
  config/static_nominal_target_profiles.json `
  --profile no_attachment
```

Pass `--source-frame` with the retained external image to additionally verify
its bytes. The normal repository-only run leaves
`source_frame_bytes_verified=false` while still checking the recorded identity
and all repository bindings.

## Profile and authority boundaries

| Profile | Keyboard region | Individual keys | Motion/contact |
| --- | --- | --- | --- |
| `no_attachment` | Ready for guarded perception integration | Blocked by 13.38 mm housing fit and unmeasured key centers | Blocked |
| `stylus_attachment` | Blocked until its tool profile is calibrated | Blocked | Blocked |

The next perception increment should detect several visible key centers or key
row features in a fresh fixed-camera frame and refine the keyboard transform
below the 7 mm individual-key limit. After that, the board target still must be
connected to a verified board-to-robot transform and a clearance-screened
noncontact waypoint before any physical motion review.

The first part of that increment is now available as deterministic, bounded
[key feedback search windows](RC03_FIXED_CAMERA_KEY_FEEDBACK_ROI.md). They tell
a later detector where to look for all 46 keys while preserving the distinction
between nominal image geometry and independently observed key centers.
