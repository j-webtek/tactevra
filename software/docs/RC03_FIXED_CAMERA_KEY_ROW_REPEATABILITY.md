# RC03 fixed-camera key-row repeatability

## Result

A second camera frame was captured without changing the fixed camera, board, or
keyboard arrangement. The capture read back DirectShow, 1920 × 1080, YUY2, and
60.00024 fps after 40 discarded warm-up frames. Its external PNG is bound by
SHA-256 `2eb7dde8db2c4c9ae4b40f05bc535c9271b14c63704ebf13f4ddce017e1b20a1`.

The frozen first-frame homography was applied without refitting. All four rows
remained observable. The largest contrast-band temporal change was **1.667 mm**
and every repeated-gap phase was unchanged at the 0.333 mm rectification sample
spacing. This passes the declared 2.0 mm row-feature study limit.

The compact result is
[`rc03_int_r1_fixed_camera_key_row_repeatability_2026-10-17.json`](../config/calibration_candidates/rc03_int_r1_fixed_camera_key_row_repeatability_2026-10-17.json).
It binds the first result, both external frame hashes, the external capture
record, and all row comparisons.

## Interpretation

This establishes temporal repeatability of coarse row structure in two distinct
frames. It does not identify physical key centers, refine the keyboard transform,
emit board-space targets, or authorize motion or contact. The next image step is
explicit keycap-edge or key-center fitting inside the 46 retained search windows,
with residuals reported separately for each key.
