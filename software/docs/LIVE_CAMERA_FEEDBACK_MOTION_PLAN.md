# Live camera feedback and motion integration plan

## Scope and present state

This plan joins the newly connected, keyboard-facing camera to the existing
vision, intent-to-hover, attachment-profile, motion-admission, and telemetry
contracts. It records the state reported on 2026-10-15 and defines the work
needed before camera observations may influence physical movement.

The camera is identified as an Arducam B0477 at persistent Windows PnP
identity `USB\VID_04B4&PID_0477&MI_00\8&257B140A&0&0000`. Bounded capture
verified `1920x1080`, approximately 60 fps, YUY2, stable settings across reopen,
and unique retained frames. Installed intrinsics, a camera-to-board transform,
and synchronized exposure timestamps remain open gates.

The arm remains in the `BARE_JAW` configuration. Its current verified state is
`KEYBOARD_FORWARD_CAL_1`, with measured servo positions
`[2052, 2149, 1956, 2550, 2227, 2041, 2042]`. This is the first existing pose
on the recorded reverse chain where the camera decoded all six installed tags
in one frame. Ruler photographs support a provisional rigid-jaw clearance of
`20 +/- 2 mm` above the key surface. The observed physical arrangement is
accepted for this workcell epoch. No key contact or keypress has been performed.

The machine-readable snapshot is
`software/config/live_camera_feedback_session_20261015.json`. The two ruler
photos remain external to the repository; the snapshot records their names,
sizes, and SHA-256 digests without adding large media to source archives.

## Existing interfaces to reuse

The repository already has the required component boundaries. The integration
must compose them rather than create an unrelated camera-to-serial shortcut.

| Stage | Existing interface | Intended use |
|---|---|---|
| Physical capture | `rocell.vision.usb_opencv.UsbOpenCvCamera` | Open one reviewed persistent device, request an exact mode, read back the negotiated mode, and acquire bounded frames. |
| Camera onboarding | UVC inventory, camera receipt, physical capture workflow, and B0477 profile contracts | Bind physical identity, mode, manual controls, reconnect behavior, and retained evidence. |
| Pixel interpretation | Existing AprilTag detector records and `PlanarAprilTagBoardPoseEstimator` | Produce typed detections and a camera-to-board pose with residual and uncertainty evidence. |
| Target geometry | Keyboard target catalog and `KeyboardCompiler` | Resolve a semantic key to one board-frame target under one catalog hash. |
| Model proposal | `ModelMotionProposalV2` and `intent_to_hover` | Bind frame/image/model/calibration evidence to a hover-only target proposal. |
| Tool separation | `CalibratedActionRegistry` and `AttachmentProfile` | Require the exact active attachment; prevent bare-jaw/stylus pose inheritance. |
| Motion boundary | Reviewed request, first-motion admission, transport gate, and named pose controller | Admit one bounded command only after all predecessor evidence is current. |
| Feedback | `TelemetryStream` plus post-motion camera capture | Verify settled joint state and independently observed spatial outcome. |

Historical camera manifests still describe older eye-on-arm candidates. The
active route is the external static-camera architecture introduced by the
commercial-tripod migration. The connected device must be identified before it
is associated with the B0477 profile or any other camera profile.

## Closed-loop architecture

The first live implementation must use **stop, settle, observe, decide, then
move once**. Host receipt timestamps are insufficient for in-motion correction,
so continuous visual servoing stays out of scope until exposure and controller
timestamps are independently synchronized.

```text
reviewed camera identity + locked mode/controls
                    |
             finite frame capture
                    |
       decode -> rectify -> detect fiducials
                    |
       camera-to-board pose + uncertainty
                    |
       keyboard target in board coordinates
                    |
 hover-only proposal bound to frame/calibration hashes
                    |
 attachment-profile + freshness + collision/simulation gates
                    |
          one reviewed noncontact command
                    |
        settle telemetry + later verification frame
                    |
      accept result or stop for human review
```

No image-processing component receives serial transport authority. No motion
component may silently acquire a fresher image, replace calibration, change the
tool profile, retry a rejected proposal, or promote `HOVER` to `CONTACT`.

## Implementation sequence

### 1. Freeze the physical configuration

- Preserve the accepted physical arrangement for the current workcell epoch.
- Keep the base, board, keyboard, fiducials, camera support, focus, aperture,
  cable routing, and lighting fixed.
- Assign a workcell epoch. Any change creates a new epoch and invalidates the
  camera-to-board registration and previously compiled trajectories.
- Photograph the camera/support, full board coverage, secured jaw cable, and
  ruler reference. Retain files outside Git and record content hashes.

Exit: a reviewed physical-state manifest with zero movement.

### 2. Identify and qualify the camera connection

- Enumerate the persistent USB identity and all reported modes without using a
  numeric camera index as identity.
- Record manufacturer/model markings, serial or persistent path, host bus,
  cable, support, and whether the device actually matches the B0477 profile.
- Select one finite capture mode, read back width, height, frame rate, FOURCC,
  and manual controls, then repeat after close/reopen.
- Capture a small bounded set of frames; reject stale, duplicate, truncated,
  unexpectedly converted, or auto-control-drifting frames.

Exit: exact identity/settings receipts and finite snapshots. Arm motion remains
disabled.

### 3. Lock optics and field of view

- Lock focus, aperture, exposure, gain, white balance, resolution, pixel format,
  and orientation.
- Verify the keyboard and all six registration fiducials remain visible with
  margin through normal lighting, glare, and arm-occlusion cases.
- Record working distance, support pose, cable load, image orientation, and the
  selected native and working pixel spaces.

Exit: reviewed optics/coverage report. One attractive image is insufficient.

### 4. Solve installed intrinsics and static registration

- Use the generated A3 target at
  `output/pdf/b0477_charuco_12x9_30mm_22mm_a3.pdf`: 12 by 9 squares,
  30 mm squares, 22 mm markers, and `DICT_5X5_1000`.
- Print at 100% / actual size and mount to rigid backing. Before any dataset
  frame, bind the target-definition and PDF SHA-256 values and pass four
  distributed horizontal plus four distributed vertical caliper measurements.
  Each measurement must be within 0.25% of the defined board extent.
- Use `software/scripts/live_charuco_dataset_capture.py` to enforce the exact
  20-fit/6-holdout order and a minimum of 30 detected ChArUco corners per view.
  A rejected view ends that dataset epoch; it is retained with its reason.
- Capture scale-verified ChArUco images using a precommitted fit/holdout split.
- Solve physical intrinsics and distortion; retain per-view and held-out
  residuals and the exact undistortion-map hash.
- Detect the board tags and solve the static camera-to-board transform.
- Validate against held-out station tags and repeat after warm-up, cable load,
  and one controlled close/reopen cycle.

Exit: installed intrinsics and extrinsics with uncertainty, residual thresholds,
and configuration-epoch bindings. Nominal FOV geometry cannot substitute.

The installed operational stream (`1920x1080`, YUY2, approximately 60 fps) and
the full-native camera contract (`5472x3648`, YUY2, 9 fps) are distinct
calibration profiles. Intrinsics cannot cross that boundary unless the exact
crop, binning, and scale transform is measured and reviewed.

### 5. Prove camera-only keyboard localization

- Produce a passive visibility atlas for the full keyboard.
- Resolve each required key center in the board frame and overlay projections
  back onto retained images.
- Repeat captures while the arm remains stationary. Quantify jitter, drift,
  tag loss, occlusion, and wrong-calibration rejection.
- Abstain on stale frames, incomplete fiducials, excessive residuals,
  out-of-workspace targets, or uncertainty above the planned hover margin.

Exit: repeatable board-frame targets with no robot command generation.

### 6. Join observation to a dry-run hover proposal

- Create a coordinator that accepts an already retained frame receipt,
  calibration hashes, workcell epoch, target catalog, and explicit attachment
  profile.
- Compile only `HOVER` proposals. Bind the image, detector, pose, calibration,
  target catalog, tool profile, and planner/simulation results by SHA-256.
- Reuse the consolidated intent-to-hover and collision rehearsals to generate
  an unsent command package.
- Exercise wrong device, wrong model, old frame, changed camera pose, changed
  keyboard, changed tool, missing tag, excess residual, and target-outside-frame
  failures.

Exit: deterministic dry-run receipts. Serial writes remain zero.

### 7. Observe the stationary arm

- With motion still disabled, capture the arm at its current named pose.
- Compare camera-derived geometry with recorded joint telemetry and the expected
  bare-jaw envelope.
- Establish whether the arm occludes required tags and whether the secured cable
  remains outside the planned swept envelope.

Exit: stationary observation agreement and visibility evidence.

### 8. Separately release one high noncontact move

This stage requires a new reviewed physical-motion request. Begin from a known
named pose and command one high hover with clearance greater than the combined
registration, arm, tool, keyboard-height, and cable uncertainty budget.

After the arm settles, capture telemetry and a new camera frame. Compare planned,
reported, and observed endpoints. Do not automatically correct or retry.

Exit: one reviewed noncontact result or a stopped failure record.

### 9. Add bounded stop-and-look correction

Only after repeated high-hover results pass may a later increment compute one
small correction from the post-settle frame. Bound translation, rotation,
velocity, total attempts, and cumulative displacement. Every correction is a
new proposal and a new one-use authorization. Any disagreement stops the run.

Contact, pressing, continuous visual servoing, and unattended retries remain
separate future qualifications.

## Mandatory gates for every camera-guided proposal

1. Exact persistent camera identity, mode, controls, and orientation.
2. Current workcell epoch and unchanged support/keyboard/fiducial state.
3. Installed intrinsics and camera-to-board transform hashes.
4. Frame freshness, uniqueness, complete required tags, residual, and
   uncertainty acceptance.
5. Exact keyboard target catalog and coordinate-frame conversion.
6. Explicit `BARE_JAW` attachment profile; stylus remains blocked.
7. Hover-only interaction and positive clearance above the full uncertainty
   budget.
8. Current collision, route, controller, and telemetry checks.
9. One reviewed command, no autonomous retry, and retained pre/post evidence.
10. Post-settle telemetry and camera verification before another command.

## Evidence package per attempt

Retain a manifest-last package containing camera identity/settings, raw frame
hashes, decoded/rectified image hashes, detections, pose and uncertainty,
calibration and target-catalog hashes, attachment profile, proposal, simulated
trajectory, reviewed command, telemetry, post-frame assessment, timestamps,
operator/reviewer identities, and explicit camera-frame, arm-write, movement,
and contact counts.

Large images remain in the reviewed external evidence store. Git retains the
canonical manifest, compact numeric results, and content hashes.

## Planned change sets

| Increment | Deliverable | Physical authority |
|---|---|---|
| A | This baseline and integration plan | None |
| B | Read-only camera identity, exact mode/control probe, finite capture receipt | Camera capture only after explicit operator action; arm disabled |
| C | Physical intrinsics and static-registration dataset/assessment | Camera capture; arm disabled |
| D | Observation-to-hover dry-run coordinator and fault tests | None; unsent commands only |
| E | Stationary-arm camera/telemetry comparison | Read-only camera and arm telemetry |
| F | Separately reviewed single high-hover validation | One bounded noncontact command |
| G | Stop-and-look correction qualification | One newly authorized bounded correction at a time |
| H | Stylus TCP, geometry, and new trajectories | Blocked pending installed stylus measurements |

## Immediate next review

Increment B is complete for finite read-only capture. The repeat at
`KEYBOARD_FORWARD_CAL_1` retained ten unique frames across two reopen cycles;
eight frames decoded all six tags and the settings hash remained stable. The
tracked session record now precommits the 20-view fit and 6-view holdout
ChArUco acquisition sequence for increment C. The next physical work is to
scale-verify the calibration target and capture those 26 views in the declared
order. Do not use the full-tag visibility result itself as registration or
motion authority.

## 2026-10-15 read-only intake result

The explicit camera-only intake identified one present Windows Camera-class
device named `Arducam B0477 (USB3 20MP)` with PnP instance ID
`USB\\VID_04B4&PID_0477&MI_00\\8&257B140A&0&0000`. The maintained command
`software/scripts/live_camera_read_only_intake.py` requested `1920x1080`,
`60 fps`, `YUY2` through DirectShow. Two open/capture/close cycles read back
the same mode and settings hash. All four retained frames had distinct SHA-256
digests, and the adapter released the camera after each cycle.

The frames are visibly illuminated and show the keyboard and all six installed
tag tiles. A second pixel review found that the original default-only detector
under-reported coverage. Combining the default profile with a bounded
AprilTag-refinement profile produces valid tag36h11 decodes for IDs `0, 1, 2,
3, 5` across the retained set. Two retained frames contain all four world-pose
tags `T0-T3` in the same exposure, and station-check tag `P0` is decoded in the
set.

The remaining tag-4/K0 tile is physically present, but its encoded square lies
behind the stationary arm near the board center; only a partial edge is exposed
in the camera pixels. It therefore cannot supply the independent K0 decode
required by the six-tag policy. The separate `5472x3648` YUY2 check does not
resolve an occluded code. Registration, camera-guided motion, robot transport,
descent, and contact remain false.

The reviewed external receipt is
`software/runs/wizard-exports/live-camera-intake-20261015-04-maintained/receipt.json`
with SHA-256
`e724228e117ea1423540094a5709b5f041d238c43729165d70a1958033132bda`.
The runtime directory is intentionally ignored by Git; the machine-readable
session snapshot retains its path and digest.

Reproduce the bounded capture from the repository root with the vision
environment:

```powershell
.\.venv-vision\Scripts\python.exe software/scripts/live_camera_read_only_intake.py `
  --pnp-instance-id "USB\VID_04B4&PID_0477&MI_00\8&257B140A&0&0000" `
  --friendly-name "Arducam B0477 (USB3 20MP)" `
  --selector 0 --width 1920 --height 1080 --fps 60 --fourcc YUY2 `
  --reopen-count 2 --frames-per-open 2 `
  --output-directory software/runs/wizard-exports/<new-directory> `
  --confirm-camera-only-capture
```

The recorded adjacent reverse chain established
`KEYBOARD_FORWARD_CAL_1` as the neutral bare-jaw camera observation pose. At
that pose, five of ten frames decoded all six tags; the remaining five decoded
IDs `1-5`. The retained receipt is
`software/runs/wizard-exports/live-camera-observation-forward-cal-1-20261015-01/receipt.json`
with SHA-256
`9560ea22b6b9281fa6f8494ccac948f0306764142c30e45d4f937b035067f8cb`.
Any camera, support, focus, board, keyboard, fiducial, or attachment change
starts a new workcell or optics epoch. Electronic control readback and exact
DirectShow endpoint binding remain open qualification items.

The repeat external receipt is
`software/runs/wizard-exports/live-camera-observation-forward-cal-1-repeat-20261015-02/receipt.json`
with SHA-256
`32a7348c78aee8ba437ec14a82daa8e1a1a0679d8d237b165e9a0fa5123b6db8`.
Eight of ten retained frames decoded IDs `0-5`; the other two decoded IDs
`1-5`. All frame hashes were unique and the negotiated settings hash was
unchanged across both reopen cycles. Robot transport remained unopened.
