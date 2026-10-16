# Live bare-jaw keyboard calibration

## Current state

The first live calibration campaign uses the unmodified RoArm-M3 jaw with no
stylus or compliant tool installed. The arm, plywood board, keyboard, camera,
and fiducials must remain fixed for these observations and joint-space
endpoints to remain meaningful.

The arm is verified idle at the previously recorded
`KEYBOARD_FORWARD_CAL_1` pose. The latest repeated servo readback is
`[2052, 2149, 1956, 2550, 2227, 2041, 2042]`. This is the first pose on the
existing reverse chain where the installed camera observed all six board tags
in one frame. The first retained capture decoded IDs `0-5` in five of ten
frames. A second bounded capture at the same stationary pose decoded IDs `0-5`
in eight of ten frames. No key contact or keypress was performed.

Firmware candidate r120 is installed. It preserves all recorded goals,
adjacent-only transitions, trajectory limits, and motion commands. It widens
the named-pose settle window from 16 to 20 servo counts and retains the
completed commanded pose while its readback stays inside that window. This
matches the repeatable physical settling observed during the reverse path.

The modeled near approach totals 38 mm from the field calibration pose. Ruler
photos captured on 2026-10-15 support a provisional rigid-jaw clearance of
`20 +/- 2 mm` above the key surface. The observed cable placement is accepted
for this session and recorded as part of the workcell epoch. These endpoints
remain **noncontact calibration poses**, not qualified contact poses.

## Recorded path

| Candidate | Forward | Reverse | Named endpoint | Planned joint goals | Increment |
|---|---:|---:|---|---|---:|
| r112 | 415 | 416 | `KEYBOARD_FIELD_APPROACH_10` | `[2174, 2271, 1825, 2362, 2277, 2040, 2047]` | 10 mm |
| r113 | 417 | 418 | `KEYBOARD_FIELD_APPROACH_20` | `[2174, 2293, 1803, 2383, 2234, 2040, 2047]` | 10 mm |
| r114 | 419 | 420 | `KEYBOARD_FIELD_APPROACH_25` | `[2174, 2305, 1791, 2393, 2213, 2040, 2047]` | 5 mm |
| r115/r116 | 421 | 422 | `KEYBOARD_FIELD_APPROACH_28` | `[2174, 2312, 1784, 2399, 2200, 2040, 2047]` | 3 mm |
| r117 | 423 | 424 | `KEYBOARD_FIELD_APPROACH_38` | `[2174, 2337, 1759, 2416, 2158, 2040, 2047]` | 10 mm |

The complete verified reverse chain is:

```text
APPROACH_38 -> APPROACH_28 -> APPROACH_25 -> APPROACH_20 -> APPROACH_10
-> FIELD_CAL_3 -> DIAGONAL_CAL_2 -> FORWARD_CAL_1
```

The runtime accepts only adjacent named-pose transitions and uses a
limit-derived quintic trajectory at 40 Hz with one synchronized servo write per
control step. Candidate r118 replaced ordered approach precedence with a
bounded nearest-endpoint classifier. Candidate r119 retained a completed
commanded approach endpoint. Candidate r120 applies the same bounded settle
behavior to every recorded named pose.

## Camera observation results

The fixed Arducam B0477 was captured at each existing pose during the reverse
chain. Every capture used `1920x1080`, approximately 60 fps, YUY2, two reopen
cycles, and the combined default and small-tag detector profiles.

| Pose | Frames | Decodable IDs | All six in one frame |
|---|---:|---|---|
| `APPROACH_25` | 6 | `0,1,2,3,5` | No |
| `APPROACH_20` | 10 | `0,1,2,3,5` | No |
| `APPROACH_10` | 10 | `0,1,2,3,5` | No |
| `FIELD_CAL_3` | 10 | `0,1,2,3,5` | No |
| `DIAGONAL_CAL_2` | 10 | `0,1,2,3,5` | No |
| `FORWARD_CAL_1` | 10 | `0,1,2,3,4,5` | Yes, 5 frames |

A repeat capture at `FORWARD_CAL_1` retained ten more unique frames across two
camera reopen cycles. Eight frames decoded all six tags, the remaining two
decoded IDs `1-5`, and the negotiated settings hash remained
`68de0820caeb41a79508ffe613f438dc06fa2303422676fa6a9f1d2943cb0c15`.
The repeat receipt is retained outside Git at
`software/runs/wizard-exports/live-camera-observation-forward-cal-1-repeat-20261015-02/receipt.json`
with SHA-256
`32a7348c78aee8ba437ec14a82daa8e1a1a0679d8d237b165e9a0fa5123b6db8`.

## Reproducible fixed-board registration

No additional target needs to be printed. The installed 610 by 457 mm board is
the measurement artifact. Its six tag36h11 detection squares are 40 mm wide;
their measured centers and common +Y/rear orientation are recorded in
`software/ai/eval/physical_installed_apriltag_xy_working_v1.json`.

Recompute the mapping from the retained camera frames with:

```powershell
.\.venv-vision\Scripts\python.exe software/scripts/measure_fixed_board_registration.py
```

The tool verifies every frame against its capture receipt, merges the default
and refined tag detectors, fits a consensus board-to-image homography from the
four perimeter tags, and holds the two interior tags out as independent checks.
It opens neither camera nor robot transport and performs no movement. The
compact result is
`software/ai/eval/b0477_fixed_board_registration_20261016.json`.

Seven of ten frames supplied all four perimeter tags to the fit. Across 112
perimeter-tag corner observations, reprojection RMSE is 5.3948 px. The 20
held-out interior-tag center checks have 4.8330 mm mean and 7.4937 mm maximum
planar error. Repeated mapped centers vary by at most 0.6474 mm in this capture,
showing that the static view is repeatable while the larger held-out residual
sets the present accuracy bound.

This result measures the board-plane mapping needed for keyboard overlays. A
single fixed coplanar view cannot separately determine lens intrinsics and
distortion, nor does it establish board-to-robot Z, TCP, contact, or motion
authority. Any movement of the camera, support, board, keyboard, or fiducials
invalidates it.

`KEYBOARD_FORWARD_CAL_1` is therefore the neutral camera observation pose for
the current bare-jaw workcell epoch. It establishes visibility only. Camera to
board registration, intrinsics, uncertainty limits, and camera-guided motion
remain separate gates.

## Attachment profile boundary

Calibration belongs to the exact physical end-effector configuration. The
tracked profile registry separates `BARE_JAW` from `STYLUS`:

- Every currently calibrated action requires `BARE_JAW` explicitly.
- Installing or removing an attachment starts a new configuration epoch and
  invalidates every precomputed trajectory.
- The stylus receives its own TCP, pose namespace, collision geometry,
  compliance limits, hover distances, and contact-depth limits.
- Bare-jaw poses and contact authority cannot be inherited by the stylus.
- The stylus profile remains blocked until its installed dimensions and
  behavior are physically measured and independently checked.

The machine-readable policy is in
`software/config/tool_attachment_profiles.json`. Profile mismatch is a hard
failure in the calibrated action registry.

## Next work

1. Retain `KEYBOARD_FORWARD_CAL_1` as the bare-jaw neutral observation pose.
2. Use the measured fixed-board mapping to project the keyboard outline and
   proposed key centers into the retained frames.
3. Review the overlays against the physical keyboard and keep the current
   7.4937 mm held-out maximum as the minimum planar uncertainty allowance until
   a stronger distortion model is independently measured.
4. Build the observation-to-hover dry-run coordinator using retained frame,
   detector, registration, target-catalog, and attachment-profile hashes.
5. Keep serial writes disabled until passive localization, uncertainty,
   stale-frame, missing-tag, and profile-mismatch tests pass.
6. When the stylus is installed, measure its TCP and collision envelope and
   create a separate observation pose and trajectory family. The fixed camera
   plane may be reused only if the camera and board epoch remains unchanged;
   every trajectory still requires the matching attachment profile.

The arm was intentionally left stationary at `KEYBOARD_FORWARD_CAL_1` when
this record was updated.
