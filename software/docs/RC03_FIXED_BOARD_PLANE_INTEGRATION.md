# RC03 fixed board-plane integration

## Recorded state

The installed overhead camera currently provides a DirectShow 1920 × 1080
YUY2 stream at 60 fps. With the camera and RC03 board fixed, world AprilTags 1,
2, and 3 produced a pixel-to-board homography over the 610 × 457 mm board. The
fit has 3.53 mm RMS and 5.65 mm maximum residual across 12 tag corners.

The controlled candidate is
[`rc03_int_r1_fixed_board_plane_2026-10-17.json`](../config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json).
Its [manifest](../config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.manifest.json)
records the hashes and sizes of the externally retained source frames, overlay,
report, and rejected intrinsic result. Large physical images remain outside the
repository under the physical-evidence retention boundary.

## What the candidate can do

`rocell.vision.fixed_board_plane_calibration_v1` validates the artifact before
use, enforces the exact camera mode, checks the residual policy, projects a
pixel onto board Z=0, and separates tool profiles. It produces an assessment
with no motion or contact authority.

From `software/`, reproduce the present bare-jaw assessment with:

```powershell
$env:PYTHONPATH = "src"
python -m rocell.vision.fixed_board_plane_calibration_v1 `
  config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json `
  --profile no_attachment `
  --camera-and-board-fixed
```

A successful result means the map can feed guarded visual localization. Every
target still needs fresh image feedback before descent. Moving the camera or
board, or changing backend, dimensions, pixel format, or frame rate, blocks the
candidate and requires a new mapping.

## Profile separation

| Profile | Board map | Tool state | Current use |
| --- | --- | --- | --- |
| `no_attachment` | Current fixed-plane map | Existing bare-jaw geometry | Guarded localization candidate |
| `stylus_attachment` | Same map while camera/board stay fixed | TCP, clearance, and contact limits missing | Blocked |

Adding the stylus changes the tool geometry and trajectories, not the camera's
board coordinate system. The stylus profile must therefore receive a separate
TCP calibration and approach/contact qualification. The loader rejects any
artifact that promotes the stylus profile before those measurements exist.

## Next integration sequence

1. Feed detected target pixels through `project_pixel()` and retain the source
   frame hash, calibration hash, projected board coordinate, and uncertainty.
2. Register the keyboard in board coordinates and validate several held-out key
   centers against camera feedback.
3. Convert the verified board target into an approach waypoint through the
   existing measured planner. Keep descent and contact blocked.
4. Run noncontact hover trials with repeated visual correction and measure the
   residual at the target.
5. Calibrate the stylus TCP as a distinct tool profile, then qualify its
   clearance and contact trajectory before enabling any stylus descent.

The rejected ChArUco intrinsic result is retained as negative evidence. This
planar candidate does not replace camera intrinsics, a 3-D camera-to-board
transform, board-to-robot calibration, tool calibration, collision evidence,
or outcome verification.
