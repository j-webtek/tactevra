# RC03 fixed-camera key-center candidates

## Result

The two hash-bound 1920 × 1080 fixed-camera frames were rectified through the
same frozen keyboard housing homography. A deterministic edge fitter then found
the repeated keycap lattice, searched the four local keycap boundaries inside
each retained key window, and produced **46 image-space center candidates** for
the `no_attachment` profile.

All 46 candidates passed their declared edge-span plausibility checks and the
3.1 mm two-frame study limit. The largest center change was **2.166 mm** on key
`8`; the median was **0.527 mm**. The standard row fits independently reproduced
the same row shifts in both frames, except for a 0.333 mm fitted half-width
difference on the `Q`–`P` row. The compact result is
[`rc03_int_r1_fixed_camera_key_center_candidates_2026-10-17.json`](../config/calibration_candidates/rc03_int_r1_fixed_camera_key_center_candidates_2026-10-17.json).

The fitter uses luminance gradients only. It does not use key legends as center
labels, refit the board or housing homography, or average the two frames into one
observation. Each frame supplies its own row lattice and local four-edge center;
the result records both centers, both edge spans, edge-peak ratios, and the
temporal distance for every key.

## Authority boundary

This closes the two-frame **image-space candidate** step. It does not establish
board-space key centers or contact targets because the dimension-constrained
housing rectification still needs an independently checked keyboard-to-board
mapping. The board-to-robot transform and installed clearance are also open.
Accordingly, the result emits no board-space target and authorizes no motion,
descent, or contact.

The result belongs only to `no_attachment`. A future `stylus_attachment` profile
must carry its own TCP, clearance envelope, and trajectory qualification; these
center candidates do not collapse those profiles.

## Next evidence

1. Validate the rectified candidate centers against board-space observations or
   another independent measurement source.
2. Bind accepted board-space centers to the keyboard-to-board transform and
   retain per-key residuals.
3. Qualify the board-to-robot transform and installed clearances separately for
   `no_attachment` and `stylus_attachment`.
4. Only then consider a sparse noncontact hover plan. Contact remains later.

The first board-plane projection audit is now recorded in
[`RC03_FIXED_CAMERA_BOARD_KEY_VALIDATION.md`](RC03_FIXED_CAMERA_BOARD_KEY_VALIDATION.md).
It passes 45 of 46 keys under the existing 7 mm study limit but leaves `SPACE`,
elevated-plane parallax, and independent physical validation unresolved.
The follow-on
[`RC03_FIXED_CAMERA_ELEVATED_KEY_PLANE_VALIDATION.md`](RC03_FIXED_CAMERA_ELEVATED_KEY_PLANE_VALIDATION.md)
evaluates the same observations before Z=0 projection and passes all 46 keys.
It resolves local layout coherence while leaving absolute board registration,
independent physical validation, and all physical authority blocked.
