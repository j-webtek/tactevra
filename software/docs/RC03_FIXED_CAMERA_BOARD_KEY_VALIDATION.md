# RC03 fixed-camera board-plane key validation

## Result

The 46 two-frame keycap-edge candidates were projected back into source pixels
through the frozen keyboard homography and then into the provisional RC03 board
plane through the independently calibrated AprilTag map. One rigid keyboard
pose was fitted per frame and each key was compared with that common pose.

**45 of 46 keys** remain within the existing 7 mm individual-key study limit in
both frames. `SPACE` is the only failure, with **8.048 mm** reference-frame and
**8.144 mm** repeat-frame residuals. The largest board-observation temporal
change is **2.407 mm** on key `8`, so the failure is not explained by motion
between the two captures.

The fitted reference pose is [110.398, 64.261] mm at 1.973 degrees yaw with
4.336 mm RMS residual. The repeat pose is [110.048, 64.873] mm at 1.808 degrees
yaw with 4.329 mm RMS residual. The compact result is
[`rc03_int_r1_fixed_camera_board_key_validation_2026-10-17.json`](../config/calibration_candidates/rc03_int_r1_fixed_camera_board_key_validation_2026-10-17.json).

## Interpretation

This audit narrows the board-plane problem to the wide spacebar observation and
the elevated-plane projection model. It does not clear board-space validation:
the provisional board homography maps Z=0 while the keycaps are elevated, and
both key observations still originate from the retained camera views. An
independent physical key measurement is still absent.

The result therefore records `board_plane_key_validation_ready=false`, emits no
board-space motion target, and authorizes no motion or contact. It applies only
to `no_attachment`; `stylus_attachment` still requires its own TCP, clearance,
and trajectory qualification.

## Next evidence

The follow-on [elevated key-plane audit](RC03_FIXED_CAMERA_ELEVATED_KEY_PLANE_VALIDATION.md)
passes all 46 keys and reduces `SPACE` to 2.889 mm reference and 1.238 mm repeat
residuals. This isolates the board-plane failure to the Z=0 projection model.

1. Establish the absolute keyboard-plane-to-board transform using a valid
   camera model or independent board-frame measurements.
2. Commission the board-to-robot transform.
3. Validate installed clearance separately for each attachment profile.
