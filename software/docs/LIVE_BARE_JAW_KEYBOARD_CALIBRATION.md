# Live bare-jaw keyboard calibration

## Current state

The first live calibration campaign uses the unmodified RoArm-M3 jaw with no
stylus or compliant tool installed. The arm, plywood board, and keyboard must
remain fixed for these joint-space endpoints to remain meaningful.

The latest verified state is `KEYBOARD_FIELD_APPROACH_38`, reached by command
`T423` under firmware candidate `r117`. Final measured servo positions were
`[2167, 2340, 1760, 2416, 2161, 2041, 2042]`. The controller reported the
trajectory complete and idle. No key contact or keypress was performed.

The modeled approach totals 38 mm from the field calibration pose. Ruler photos
are being used to establish the remaining absolute surface-height uncertainty.
The current endpoint is therefore a repeatable **noncontact calibration pose**,
not a qualified contact pose.

## Recorded path

| Candidate | Command | Named endpoint | Planned joint goals | Modeled incremental descent |
|---|---:|---|---|---:|
| r112 | 415 | `KEYBOARD_FIELD_APPROACH_10` | `[2174, 2271, 1825, 2362, 2277, 2040, 2047]` | 10 mm |
| r113 | 417 | `KEYBOARD_FIELD_APPROACH_20` | `[2174, 2293, 1803, 2383, 2234, 2040, 2047]` | 10 mm |
| r114 | 419 | `KEYBOARD_FIELD_APPROACH_25` | `[2174, 2305, 1791, 2393, 2213, 2040, 2047]` | 5 mm |
| r115/r116 | 421 | `KEYBOARD_FIELD_APPROACH_28` | `[2174, 2312, 1784, 2399, 2200, 2040, 2047]` | 3 mm |
| r117 | 423 | `KEYBOARD_FIELD_APPROACH_38` | `[2174, 2337, 1759, 2416, 2158, 2040, 2047]` | 10 mm |

Each endpoint has a paired reverse command. The runtime accepts only adjacent
named-pose transitions, uses a limit-derived quintic trajectory at 40 Hz, and
issues one synchronized servo write per control step. Candidate r116 corrected
classifier precedence where neighboring pose tolerance bands overlap. Candidate
r117 checks the closest pose first for the same reason.

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

## Remaining calibration work

1. Photograph the current endpoint with the ruler zero resting on the key
   surface and estimate the remaining clearance.
2. Establish a conservative bare-jaw hover endpoint and repeatability envelope.
3. Preserve a held-out return trial before qualifying wider keyboard motion.
4. Keep contact disabled until key travel, surface height, and reaction limits
   have their own reviewed evidence.
5. After installing the stylus, measure its TCP and collision envelope and
   generate a separate trajectory family from the same fixed workcell frame.

The arm was intentionally left stationary at `KEYBOARD_FIELD_APPROACH_38` when
this record was written.
