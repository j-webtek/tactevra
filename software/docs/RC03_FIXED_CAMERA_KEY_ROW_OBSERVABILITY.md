# RC03 fixed-camera key-row observability

## Result

The retained 1920 × 1080 fixed-camera frame was decoded and rectified through
the accepted keyboard image homography. All four standard key rows produced a
bounded contrast-band observation and a repeated inter-key gap phase inside
the expected row search area. The largest contrast-band displacement was
**5.0 mm**, within the declared 7 mm image-feature study limit.

This establishes that the current view contains usable row structure for the
next detector. It does not establish a physical key center: contrast bands can
come from legends or keycap surfaces, and gap phase is a repeated row feature.
The retained result therefore keeps individual-key localization, board-space
targets, motion, descent, and contact blocked.

The compact assessment is
[`rc03_int_r1_fixed_camera_key_row_observability_2026-10-17.json`](../config/calibration_candidates/rc03_int_r1_fixed_camera_key_row_observability_2026-10-17.json).
It binds the exact external source-frame SHA-256, registration input,
board-plane calibration, target profile, thresholds, and four row results.

## Observations

| Standard row | Contrast-band offset | Repeated-gap phase | Peak ratio |
| --- | ---: | ---: | ---: |
| `1` through `EQUAL` | +4.000 mm | -2.667 mm | 1.579 |
| `Q` through `P` | -5.000 mm | -1.333 mm | 3.839 |
| `A` through `APOSTROPHE` | -2.333 mm | -3.333 mm | 3.118 |
| `Z` through `SLASH` | -1.000 mm | -0.333 mm | 5.183 |

## Reproduce with the external frame

From the repository root:

```powershell
$env:PYTHONPATH = "software/src"
python -m rocell.vision.fixed_camera_key_row_observability_v1 `
  software/config/calibration_candidates/rc03_int_r1_fixed_camera_keyboard_2026-10-17.json `
  software/config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json `
  software/config/static_nominal_target_profiles.json `
  output/calibration/rc03-int-r1/2026-10-17/heldout-keyboard/heldout-001.png
```

The command refuses altered frame bytes before decoding. Repository tests use a
synthetic rectified keyboard to exercise the detector and validate the compact
physical result against its schema; the large source frame remains external.

## Next evidence

The distinct-frame requirement is now satisfied by the
[key-row repeatability result](RC03_FIXED_CAMERA_KEY_ROW_REPEATABILITY.md).
A later detector can use
the retained per-key windows and repeated row phases to fit explicit keycap
edges. Only independently fitted centers with recorded residuals can reconsider
the individual-key image-localization gate. Board-to-robot and clearance gates
remain separate after that.
