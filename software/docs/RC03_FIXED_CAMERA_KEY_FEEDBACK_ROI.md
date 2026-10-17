# RC03 fixed-camera key feedback search windows

## Result

The accepted fixed-camera keyboard quadrilateral now produces 46 deterministic
image-space search windows. Each window contains a nominal pixel center, the
projected nominal key footprint, and a bounded rectangle for a later detector.
The mapping is bound to the same 1920 × 1080 source-frame identity, board-plane
calibration, camera mode, and nominal keyboard profile as the reviewed keyboard
registration.

This increment does not call the projected centers measurements. It emits no
board-space motion targets, does not clear the existing 7 mm individual-key
limit, and grants no motion, descent, or contact authority.

## Method

The four reviewed keyboard housing corners define a projective map from the
315 × 147 mm keyboard-local rectangle to the camera image. The nominal layout's
46 key footprints are passed through that map. Their pixel bounding rectangles
are expanded by 3 pixels and clipped to the retained camera dimensions. The
complete key set, finite geometry, frame bounds, evidence hashes, and upstream
registration gates are checked every time the artifact is built.

These regions reduce the next perception step from an unconstrained full-frame
search to 46 explicit image regions. The next detector must derive independent
key-center or row-feature observations inside them and retain residuals before
individual-key localization can be reconsidered.

## Reproduce

From `software/`:

```powershell
$env:PYTHONPATH = "src"
python -m rocell.vision.fixed_camera_key_feedback_roi_v1 `
  config/calibration_candidates/rc03_int_r1_fixed_camera_keyboard_2026-10-17.json `
  config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json `
  config/static_nominal_target_profiles.json `
  --profile no_attachment
```

Supplying the retained external frame with `--source-frame` additionally checks
its byte length and SHA-256 digest. The large source image remains outside the
repository.

## Profile and authority boundaries

| Profile | Image search windows | Observed key centers | Motion/contact |
| --- | --- | --- | --- |
| `no_attachment` | Ready | Missing | Blocked |
| `stylus_attachment` | Blocked pending its calibrated tool profile | Missing | Blocked |

The search-window result and future detector observations must stay separate
from board-space targets. After independent image evidence passes the declared
individual-key limit, a board-to-robot transform and clearance-screened
noncontact preview are still required before physical motion review.
