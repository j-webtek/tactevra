# RC03 fixed-camera elevated key-plane validation

## Result

The 46 two-frame keycap-edge candidates were evaluated in the rectified
315 x 147 mm keyboard housing plane, before any projection onto the RC03 Z=0
board plane. One rigid layout was fitted per frame against the unchanged nominal
key geometry.

**All 46 keys** remain inside the 7 mm individual-key study limit in both
frames. The reference fit has 1.692 mm RMS and 3.100 mm maximum residual. The
repeat fit has 1.719 mm RMS and 3.328 mm maximum residual. `SPACE`, which failed
the Z=0 board-plane audit, has 2.889 mm reference and 1.238 mm repeat residuals
in the elevated plane. The compact result is
[`rc03_int_r1_fixed_camera_elevated_key_plane_validation_2026-10-17.json`](../config/calibration_candidates/rc03_int_r1_fixed_camera_elevated_key_plane_validation_2026-10-17.json).

## Interpretation

The complete local-plane result shows that the observed key layout, including
`SPACE`, is coherent with the nominal keyboard geometry. The earlier `SPACE`
failure is introduced when elevated observations are projected through the
board's Z=0 homography.

This closes the elevated key-layout coherence question. It does not establish
the elevated plane's absolute board-frame translation because the available
intrinsic calibration was rejected as ill conditioned and no independent
physical key-center measurement exists. The result therefore emits no
board-space target and grants no motion or contact authority.

The result applies only to `no_attachment`. The separate
`stylus_attachment` profile still requires its own TCP, clearance, and
trajectory qualification.

## Next evidence

1. Establish the absolute keyboard-plane-to-board transform using a valid
   camera model or independent board-frame measurements.
2. Commission the board-to-robot transform.
3. Validate installed clearances separately for `no_attachment` and
   `stylus_attachment` before any noncontact motion.
