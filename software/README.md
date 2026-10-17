# Tactevra Runtime

- **Document status:** Current software reference
- **Audience:** Users and contributors working with the local runtime
- **Authority:** Explanatory; this page does not authorize hardware operation

## Start here

Tactevra Runtime provides the local rehearsal interface, semantic task compiler, simulation
tools, and arm command validation. For a first run, use the
[getting-started guide](../docs/GETTING_STARTED.md). For current capabilities and
limitations, use [project status](../PROJECT_STATUS.md).

The AI-to-arm v2 interface now includes an assembler, strict decoder, trusted
registry snapshot, and freshness checks before planning. Its shared tests use
synthetic evidence. This does not establish physical typing or a complete
camera-to-arm workflow. Integration work is tracked in the
[shared developer workplan](ai/docs/SHARED_AI_ARM_WORKPLAN.md).

The static-overhead collision intake can reproduce the current pending
measurement packet from the immutable FREEZE-013 workspace without opening
camera or robot transport:

```powershell
$env:PYTHONPATH = "software/src;software/ai"
python software/ai/run_static_overhead_collision_profile_intake.py `
  --workspace C:\path\to\freeze-013-checkout
```

The pending mode writes a manifest, validation report, and worksheet. It
returns a blocked result until every required conservative envelope, source
hash, uncertainty, exclusion, and measured clearance passes strict validation.

| Need | Current source |
| --- | --- |
| First installation and hardware-free walkthrough | [Getting started](../docs/GETTING_STARTED.md) |
| Evidence-backed capability summary | [Project status](../PROJECT_STATUS.md) |
| Component and authority boundaries | [Software architecture](docs/ARCHITECTURE.md) |
| AI/runtime coordination | [Shared AI-to-arm workplan](ai/docs/SHARED_AI_ARM_WORKPLAN.md) |
| Detailed test history | [AI/arm evidence ledger](ai/docs/EVIDENCE_LEDGER.md) |
| Older runtime, camera, USB, and onboarding checkpoints | [Runtime implementation history](RUNTIME_IMPLEMENTATION_HISTORY.md) |

## Implementation history

The detailed dated runtime, camera, USB, and onboarding checkpoints are retained
in the [Tactevra Runtime implementation history](RUNTIME_IMPLEMENTATION_HISTORY.md).
Those records preserve their original outcomes and terminology; use this page
and [project status](../PROJECT_STATUS.md) for current setup and capability
guidance.

## Documentation

- [Static-overhead camera architecture plan](../STATIC_OVERHEAD_CAMERA_ARCHITECTURE_PLAN.md)
- [Machine-readable camera architecture plan](config/camera_architecture_plan.json)
- [B0477 purchase profile and commissioning guide](docs/B0477_CAMERA_INTEGRATION.md)
- [First-power-on onboarding and resumable rehearsal](docs/FIRST_POWER_ON_ONBOARDING.md)
- [Physical onboarding automation and connection runbook](docs/PHYSICAL_ONBOARDING_AUTOMATION.md)
- [M1 qualified zero-hardware onboarding runtime](docs/M1_ZERO_HARDWARE_RUNTIME.md)
- [Reviewed physical onboarding wizard v2 implementation plan](docs/PHYSICAL_ONBOARDING_WIZARD_IMPLEMENTATION_PLAN.md)
- [Pre-hardware runtime foundations and hardware-substitution sequence](docs/PREHARDWARE_RUNTIME_FOUNDATIONS.md)
- [Placemat geometry sensitivity simulation](docs/PLACEMAT_GEOMETRY_SENSITIVITY.md)
- [Dimensioned static-camera hardware package](../hardware/static_overhead_camera/README.md)
- [Software architecture](docs/ARCHITECTURE.md)
- [Synthetic pixel-vision pipeline](docs/PIXEL_VISION_SIMULATION.md)
- [Arm-mounted camera correction simulation](docs/ARM_CAMERA_CORRECTION_SIMULATION.md)
- [Prehardware qualification and immutable replay](docs/PREHARDWARE_QUALIFICATION.md)
- [Adaptive stress and full-catalog campaigns](docs/ADAPTIVE_PREHARDWARE_STRESS.md)
- [Virtual commissioning and deterministic replay](docs/VIRTUAL_COMMISSIONING.md)
- [Keyboard typing runbook](docs/KEYBOARD_RUNBOOK.md)
- [Android phone tapping runbook](docs/ANDROID_RUNBOOK.md)
- [Pinned RoArm model and limitations](models/roarm_m3/README.md)
- [Reach-layout diagnostic](docs/REACH_LAYOUT_STUDY.md)
- [Bounded park-pose optimization](docs/PARK_OPTIMIZATION.md)
- [Discrete route trajectory simulation](docs/TRAJECTORY_SIMULATION.md)
- [Shadow telemetry replay qualification](docs/SHADOW_TELEMETRY_REPLAY.md)
- [Pre-hardware layout sensitivity and mission-route coverage](docs/PREHARDWARE_MISSION_COVERAGE.md)
- [Full-body collision foundation](docs/COLLISION_FOUNDATION.md)
- [Offline eye-on-arm calibration](docs/EYE_ON_ARM_CALIBRATION.md)
- [Offline eye-on-arm capture bundle](docs/EYE_ON_ARM_CAPTURE_BUNDLE.md)
- [Calibration artifact policy](calibrations/README.md)
- [Runtime evidence sharing policy](../CONTRIBUTING.md#export-sharing)

## Historical Freeze-009 camera facts

The standalone RoArm-M3-Pro includes Waveshare's upper-arm camera holder but no
camera. The arm product page does not explicitly recommend a camera model. The
Waveshare IMX335 5MP USB Camera (B), SKU 26719, was Freeze 009's
historical selected-unqualified arm-camera candidate because its published 21 x 13.5 mm
mounting-hole pattern geometrically matches the holder. It is not the selected
Phase 1 overhead camera. The B0477/16 mm combination is now the selected
detailed-screening overhead candidate; its exact received identity and physical
acceptance remain open under the machine-readable contracts above.

`usb_opencv` is the candidate backend. The ESP HTTP/MJPEG backend applies only
to a separately purchased and identified ESP camera; the arm controller's
ESP32 is not a camera. No physical camera is accessed by the commands below.

## Architecture at a glance

```text
verified manifest + locked simulation sources
                    |
          strict virtual-workcell bootstrap
                    |
operator text -> semantic ActionPlan -> action-indexed target/path projection
                                           |
             virtual calibration closure + bounded sequential IK
                                           |
 Phase 1 target: fixed overview -> JPEG -> tag decoder -> planar pose gate
                                            |
 Phase 2 research: achieved joints -> moving C_arm -> JPEG -> board registration
                                           |
                 NO_CHANGE or fully re-solved atomic suffix
                                           |
          fresh achieved FK -> private-truth TCP position/tool axis
                                           |
 virtual arm -> ContactEvent -> geometric device hit-test -> ContactResult
                                           |
            ContactResult-only observer -> outcome hash/length
                                           |
                 final park + immutable evidence

clock | arm | observation | contact | outcome | cancellation | evidence
  ^ deterministic zero-authority adapters + mission-through-ports rehearsal ^

additive dense V2:
semantic/contact schedule -> accepted route -> non-wire controller targets
  -> settled final-HOVER -> stateful per-contact B0477 replay capture
  -> endpoint/midpoint collision -> authorization-v2 + contact journals
  -> virtual contact/outcome -> final park -> full receipt replay
```

The simulation foundation includes:

- a versioned bundle lock for the profile, target catalog, frame contract,
  camera manifest, local URDF, and rank-1 virtual commissioning scenario;
- a strict, relocatable startup boundary that validates runtime policy, the
  complete locked context, gate projection, calibration inventory, non-opening
  arm profile, six-tag synthetic overview, and collision readiness;
- a service-entry coherence guard that reloads the canonical locked context and
  rejects altered in-memory snapshots, geometry, scenarios, targets, or reports;
- shared application-level runtime ports for clocks, arm lifecycle/execution/
  feedback, observations, opaque contact events, independent outcome
  observation, cancellation, and evidence, with correlated adapter identities
  and a default fail-closed zero-authority bundle validator;
- deterministic VIRTUAL/REPLAY implementations of every runtime port plus a
  bounded mission-through-ports state machine that validates cancellation and
  deadlines, uses fresh correlated non-echo achieved feedback, and always
  attempts stop, close, evidence finalization, and final bundle validation;
- an additive V2 semantic schedule that keeps semantic, contact-occurrence,
  route-waypoint, and authorization-command ordinals distinct; Android state
  observations receive no contact, route command, authorization entry, or
  journal;
- a dense accepted-route adapter and bounded T=104-shaped in-memory runtime
  that map every waypoint after the known initial park to one emulator target
  without exposing an encoder, transport, live permit, or wire payload;
- a single-use stateful B0477 replay-camera port that releases only the exact
  next synthetic observation after the contact's final HOVER reports its exact
  settled controller pose, refuses skip/reuse/reorder, and latches deterministic
  capture-failure, timeout, and stale-frame faults before approach;
- dense 26-body static-camera collision queries at every route endpoint and
  exact 0.5 joint midpoint, currently supplied by an explicitly isolated
  software fixture that permanently reports no physical-clearance evidence;
- a separate V2 assembler and runner that consume the ordered simulation
  permit, commit crash-conservative contact journals, execute geometry-resolved
  virtual contacts, observe outcomes independently, retract, and park while
  retaining full authorization/T104/camera/contact/journal receipt bodies and
  zero hardware counters;
- sealed structured fault receipts that attribute controller faults to the
  failed T104 trace and B0477 faults to the exact settled-hover capture request;
  free-form fault detail is explicitly descriptive rather than causal evidence;
- a local kinematic projection pinned to an official Waveshare ROS Xacro
  commit, typed rigid transforms, strict URDF loading, FK, and numerical IK;
- bounded exact-byte URDF capture shared by the simulation, target sweep,
  reach, park, broader-layout, mission-route, trajectory, and
  collision-readiness services: each hashes the same bytes it parses and
  serializes the loaded digest/byte count in provenance;
- a separate `R_ctrl` firmware model, gripper conversion, and deterministic
  T=104 interpolation emulator;
- the nominal RC03 board, two interactive devices, typed TCP calibration-puck
  datum, stations, tags, and coarse AABB tool-tip checks;
- synthetic PERIBOARD-409 and Galaxy A16/Gboard-like target seeds;
- a deterministic fixed-fixture grayscale JPEG renderer, an independent
  tag36h11 pixel decoder for released IDs 0-5, and a dependency-free planar
  board-pose estimator v1.1 whose monotonic consensus consumes only typed
  detections, intrinsics, and the frozen tag map;
- a separate opt-in arm-mounted-camera simulator whose view depends on achieved
  six-joint FK, whose real JPEG pixels are processed without target/action
  input, and whose quality-gated `Wv_T_board` candidate drives a pure
  `REJECT`/`NO_CHANGE`/`APPLY` registration decision;
- optional Phase-2 immutable one-based moving-camera fault schedules covering unavailable,
  tag-loss, blur, noise, timestamp, and stale-frame failures, including failure
  on corrected re-observation before contact;
- a bounded correction-suffix replanner that starts from typed virtual-plant
  feedback, checks current/correction-leg geometry, discards every old
  unexecuted joint result, re-solves all remaining Cartesian intent through
  park under the shared IK gates, and installs only a complete accepted queue;
- one opaque virtual board-truth source shared by the moving-camera renderer
  and a separate achieved-FK contact projector but never supplied to the
  planner, plus an adaptive keyboard/Android report with independent source,
  execution, and trajectory-revision identities;
- bounded sequential IK over complete nominal typing/tapping routes, with each
  result retaining the solver-achieved board-frame TCP position and hand-TCP
  +Z axis separately from the planned waypoint;
- original action-occurrence identity preserved through geometric steps,
  densified Cartesian waypoints, joint results, and contact events;
- a deterministic five-joint plant plus geometry-driven keyboard and Android
  truth models: achieved contact position, contact normal, dwell, activation
  count, target polygon/surface bounds, and Android UI state determine whether
  a key/tap event is emitted;
- a separate virtual outcome observer that consumes `ContactResult` values
  only, enforces exact-once ordered consumption, and exposes hash/length output
  evidence without receiving the planned target or expected character;
- declarative one-use faults and an append-only virtual event ledger;
- atomic split-artifact records using manifest schema v2 and report schema v3,
  including a separate redacted `vision.json` ledger, strict byte verification,
  and full planner/vision/executor recomputation;
- a separate manifest-last qualification evidence package whose six bounded
  canonical artifacts are strictly verified before full public-service replay;
- a staged 243-point coarse plus bounded-refinement base/yaw/tool sensitivity
  study, with named phone regressions and a ranked all-75-contact shortlist;
- one independently planned park-to-target-to-park route diagnostic for each of
  the 46 keyboard and 29 phone targets;
- one stronger optional Phase-2 adaptive coverage service that runs a fresh moving-camera,
  achieved-contact, outcome, and park session for each of those 75 targets,
  with a 128-execution ceiling per single-target route, plus signed/boundary
  and deterministic seeded perturbation campaigns;
- typed sphere/capsule/oriented-box collision primitives, evidence-bearing pair
  exclusions, bounded discrete sweeps, clearance/uncertainty policy, and a
  current-artifact readiness audit that blocks while required geometry is absent;
- a numerical-rank gate plus report-only conditioning for the solver-weighted
  five-constraint task Jacobian on trajectory waypoints;
- immutable, resource-bounded vision records for exact frame/JPEG identity,
  detector identity and settings, ordered AprilTag pixel corners and rejection
  reasons, pose-estimator identity, explicit-frame pose, covariance, residuals,
  inlier masks, and intrinsics/tag-map hashes; and
- raw T=1051 feedback-to-pinned-URDF FK reproduction plus strict raw-wire,
  JPEG, normalized-detection, and capture-bracket evidence binding.

On 2026-09-04, the v1.1 estimator and the full-catalog synthetic policy
(2.5 mm translation, 0.5 degree yaw/tilt, and 5 px maximum inlier RMSE)
accepted all 75 adaptive target sessions. The deterministic report SHA-256 is
`232dcdd5c7bb6cb7afb6e4dcac6001797991faa54587dd7e0979e67880d8d4e2`.
The perturbation campaign intentionally uses the stricter 1.5 mm,
0.25 degree, and 3 px policy. Its 2026-09-04 estimator-v1.1 rerun passed all
20/20 declared outcomes, including four expected safe rejections, with report
SHA-256
`9dda1bc28015ee6943d0e5017e16756dd30c6d0530d950a818161c28aa15dd20`.
Both services allow at most 128 executed virtual waypoints per single-target
route. These are synthetic, zero-authority regression contracts, not physical
accuracy or release limits.

The URDF is a kinematic seed, not a validated dynamic or collision twin.
`R_ctrl` is not equated with vendor URDF frames. Two rendered-camera paths now
coexist: the replay-stable session-v3 path keeps its fixed overview fixture as
the Phase 1 migration target, while a separate adaptive schema preserves the
historical/optional Phase 2 moving upper-arm camera. Its holder transform and
wide-FOV intrinsics are explicitly unmeasured
synthetic values. Achieved-pose contact, independent outcome, fixed-overview
vision, and adaptive arm-camera correction are executable software models, but
their geometry, contact limits, UI definitions, and timing remain synthetic.
No physical arm, camera, keyboard, Android, or controller adapter implements
the shared runtime ports yet. The generic V1 zero-authority orchestrator proves
that boundary and its cleanup semantics. The additive dense V2 path now closes
the former hardware-free assembler gap by joining the accepted route, B0477
observations, collision results, authorization, journals, non-wire controller
emulator, virtual contact, independent outcome, and final park. It does not
rewrite V1, refactor the legacy/adaptive executor onto commissioned ports, or
create a physical adapter. Consequently none of these checks is physical
`VERIFY`, collision-clearance, or `VISION_CORRECT` evidence.

## Install

Use Python 3.10 or newer. From `software/`:

```powershell
python -m pip install -e .
```

The base package uses Pillow for deterministic JPEG rendering/decoding; it does
not require NumPy or OpenCV. Install extras only when required:

```powershell
python -m pip install -e ".[test]"
python -m pip install -e ".[serial]"
python -m pip install -e ".[vision]"
```

Use a dedicated virtual environment for vision. Remove an old `opencv-python`
wheel before installing `opencv-contrib-python`; the contrib build supplies the
required ChArUco/ArUco functionality, and the two wheel families must not share
an environment.

Importing `rocell` or running simulation commands does not import `pyserial` or
OpenCV and does not enumerate or open hardware.

For the supported Windows arrival environment, run from the repository root:

```powershell
.\setup-rocell.ps1 -Profile hardware
.\rocell.ps1 host-doctor --profile hardware --require-pass --json
.\rocell.ps1 rehearse-physical-connections --require-expected --json
```

`setup-rocell.ps1` creates `.venv`, installs the selected extras, runs
`pip check`, and executes only hardware-free verification. The root launcher
anchors the workspace and manifest, isolates the workspace interpreter, and
requires that controlled environment for physical-onboarding and arm-feedback
commands. The connection rehearsal uses only deterministic incapable providers;
it performs zero OS device enumeration and zero physical I/O.

When the hardware-arrival record should be created, the combined safe starter
is:

```powershell
.\start-rocell-onboarding.ps1 -CellId CELL-A
```

This does not inventory a device, open a camera/port, apply arm power, or send
any command. It always repeats the incapable-provider camera/arm connection
rehearsal immediately before session creation, including when environment setup
is skipped. Continue only through the controlled
[physical onboarding runbook](docs/PHYSICAL_ONBOARDING_AUTOMATION.md).

## Commands

Run from the workspace root. From another directory, put
`--workspace C:\path\to\robot-arm-build` before the subcommand.

Freeze 006 first synchronized the seven-source RC03 Job 00A lifecycle/evidence
transition over Freeze 005: the measurement record, step-package index and
validation, release validation, print readiness, build tracker, and prehardware
readiness changed together. Freeze 007 then bound the subsequent
evidence-only as-built traceability note for the pre-label-correction Job 00A
coupons and the regenerated measurement/readiness derivatives. Freeze 008 then
synchronized the operator-waived prototype Job 00A M4 functional-fit evidence
and regenerated dependents: `tray_clearance_holes_coupon_pass` is `PASS`, the
M4 diameter is an explicitly assumed nominal `4.0 mm` rather than a metrology
result, and the demonstrated evidence is passage through the nominal `4.4 mm`
hole plus fit in the nominal `9.2 mm` washer recess. Freeze 009 synchronized
the operator-waived Job 00A keyboard locator functional-fit selection and
lifecycle: `keyboard_station_registration_coupon_pass` is `PASS`; the nominal,
not caliper-measured, 6 mm production dowel selected a 6.2 mm round socket,
6.2 mm radial-slot width, and controlled 10.0 mm slot length; and Job 00A's
recorded and effective state is `POSTPRINT_PASS`. All three mapped Job 00A
post-print gates—keyboard corner, keyboard station registration, and tray
clearance—are now `PASS`. The measurement-gate counts are
`11 PASS / 69 NOT_TESTED / 4 NA`; these waivers have no physical-release effect.
Freeze 010 then records the two failed legacy Job 00B nut/tie features and the
controlled Job 03C1 production-equivalent redesign, producing the current
`15 PASS / 63 NOT_TESTED / 4 NA / 2 FAIL` state without granting physical
release.
Geometry, the tag map, and Freeze-005-derived reach, park,
optimization, target-map, and report evidence retain their original
provenance. The RC03 package validators passed before the active manifest,
bindings, and simulation bundle were reissued. The alignment command reports
`ALIGNED_CAMERA_HOLD_CONTACT_BLOCKED`, so live hardware and contact remain
blocked.

The M1 commands below are the supported qualified-storage surface. Do not use a
direct module-call substitute or treat the legacy diagnostic session as an M1
store.

```powershell
rocell host-doctor --profile hardware --require-pass --json
rocell rehearse-physical-connections --require-expected --json
# Persistent arrival sessions are diagnostic-only; see the physical runbook.
rocell physical-onboard new --cell-id CELL-A --prepare-safe --json
# Separate M1 v2 storage path; all operations remain zero-hardware/zero-authority.
rocell physical-onboard init-v2-storage --cell-id CELL-A --json
rocell physical-onboard verify-v2-runtime --cell-id CELL-A --json
rocell physical-onboard new-v2 --cell-id CELL-A --session-id arrival-v2-local-001 --json
rocell physical-onboard verify-v2-runtime --cell-id CELL-A --session-id arrival-v2-local-001 --json
rocell status --json
rocell integration-readiness --json
rocell bootstrap-sim --json
rocell qualify-prehardware --profile quick --require-pass --json
rocell qualify-prehardware --profile standard --require-pass --json
rocell qualify-prehardware --profile quick --record --require-pass --json
rocell replay-prehardware-qualification --manifest software/runs/qualification-<report-prefix>/manifest.json --require-identical --json
rocell doctor --mode sim --json
rocell camera-profile --json
rocell rehearse-camera-commissioning --json
rocell rehearse-b0477-uvc-inventory --require-pass --json
rocell rehearse-b0477-intrinsics --json
rocell rehearse-b0477-stack --require-pass --json
# Fast five-artifact check; the complete milestone gate above also runs pixels.
rocell rehearse-b0477-stack --skip-pixel-vision --require-pass --json
rocell simulate-b0477-vision --mode normal --require-expected --json
rocell simulate-b0477-vision --mode tag-loss --require-expected --json
rocell rehearse-first-power-on --scenario nominal --require-expected --json
rocell workcell --json
# Default assumed bounds intentionally expose phone-target sensitivity gaps.
rocell stress-placemat-geometry --json
# Zero-bound control: all 75 nominal target centres must remain in-region.
rocell stress-placemat-geometry --zero-bounds --require-no-gaps --json

rocell plan --device keyboard --text "test 123" --json
rocell dry-run --device keyboard --text "test 123" --json
rocell simulate --device keyboard --text "test 123" --json

rocell plan --device phone --text "test." --json
rocell simulate --device phone --text "test." --json

rocell sweep-targets --device keyboard --phase contact --json
rocell sweep-targets --device phone --phase contact --json
rocell optimize-layout --json
rocell optimize-park --json
rocell study-layout-hypotheses --json
rocell screen-mission-routes --json
rocell screen-mission-routes --from-layout-study-rank 1 --json
# Optional Phase-2 moving-camera regression paths:
rocell stress-adaptive-session --seed 20260903 --generated-cases 8 --require-pass --json
rocell screen-adaptive-mission-routes --require-all --json
rocell collision-status --json
rocell simulate-trajectory --device keyboard --text "a" --use-optimized-park --json
rocell simulate-trajectory --device phone --text "a" --use-optimized-park --json
rocell simulate-session --device keyboard --text "test" --require-pass --json
rocell simulate-session --device phone --text "test." --require-pass --json
rocell simulate-session --device keyboard --text "test" --record --require-pass --json
# Each initial V2 run requires a new, nonexistent persistent journal root.
rocell --workspace . simulate-integrated-v2 --device keyboard --text "test" --journal-root .\software\runs\integrated-v2-keyboard-local-001 --require-pass --json
rocell --workspace . simulate-integrated-v2 --device phone --text "test." --journal-root .\software\runs\integrated-v2-phone-local-001 --require-pass --json
# Expected fail-closed camera-fault rehearsal; --require-pass returns nonzero.
rocell --workspace . simulate-integrated-v2 --device keyboard --text "test" --journal-root .\software\runs\integrated-v2-camera-fault-local-001 --camera-fault-kind stale-frame --camera-fault-contact-ordinal 0 --require-pass --json
# Optional Phase-2 moving-camera regression paths:
rocell simulate-adaptive-session --device keyboard --text "a" --truth-offset-x-mm 12 --require-pass --json
rocell simulate-adaptive-session --device phone --text "a" --truth-offset-x-mm 8 --require-pass --json
rocell replay-session --manifest software/runs/virtual-<report-prefix>/manifest.json --require-identical --json
rocell calibration-status --device keyboard --json
rocell calibration-status --device phone --json
# Optional Phase-2 eye-on-arm offline diagnostics:
rocell solve-eye-on-arm-offline --dataset .\capture.json --expected-sha256 <sha256> --json
rocell verify-eye-on-arm-fk-offline --dataset .\capture.json --dataset-sha256 <sha256> --evidence .\raw-feedback.json --evidence-sha256 <sha256> --json
rocell verify-eye-on-arm-capture-bundle-offline --dataset .\capture.json --dataset-sha256 <sha256> --evidence .\raw-feedback.json --evidence-sha256 <sha256> --bundle .\capture-bundle.json --bundle-sha256 <sha256> --json
```

| Command | Current scope |
| --- | --- |
| `host-doctor` | Verify the selected source tree, controlled environment, dependency metadata/origins, conflicting OpenCV wheels, and `pip check` without enumerating or opening devices |
| `rehearse-physical-connections` | Exercise the exact host/B0477/RoArm connection lifecycle and named fail-stop cases with constructor-fixed incapable providers; no OS inventory, physical open, T=104, power, motion, or contact path exists |
| `physical-onboard` | Maintain the legacy source-bound diagnostic arrival session and its explicitly requested metadata-only inventory; the M1 v2 subcommands separately initialize/verify qualified Windows storage and create blank v2 sessions with global attempt/quarantine state. Neither path can pass a reviewed physical stage or grant physical authority |
| `status` | Verify and inspect the immutable build snapshot and capabilities |
| `bootstrap-sim` | Strictly initialize the complete zero-I/O virtual workcell and report declared physical/model gaps |
| `qualify-prehardware` | Run the locked aggregate startup/correction/contact/outcome/fault/determinism campaign; `standard` also requires a fresh 75/75 independent-route screen, while every result remains physically unready and zero-authority |
| `replay-prehardware-qualification` | Strictly verify the dedicated six-artifact qualification package, reconstruct its locked policy, and recompute the complete quick/standard campaign before comparing every artifact |
| `doctor --mode sim` | Side-effect-free diagnostics backed by the complete virtual bootstrap |
| `integration-readiness` | Compose retained AI/arm evidence into one content-bound blocker report without opening a camera or controller; add `--require-ready` for a fail-closed automation gate |
| `camera-profile` | Validate and report the exact B0477 purchase-time profile and its bounded synthetic projection without enumerating or opening hardware |
| `rehearse-camera-commissioning` | Exercise synthetic persistent identity, full-native USB3/YUY2 mode, manual-control, and close/reopen gates; a pass never commissions a camera |
| `rehearse-b0477-uvc-inventory` | Parse a bounded UVC inventory through a provider-neutral interface and deterministic fake provider; require persistent identity, exact native USB3/YUY2 negotiation, manual controls, and reopen stability without enumerating hardware |
| `rehearse-b0477-intrinsics` | Validate the sealed 32-view synthetic ChArUco artifact, its 24/8 precommitted split, source hashes, UVC identity/settings bindings, solution/crop/map structure, and held-out gate logic; it is not a physical calibration |
| `rehearse-b0477-stack` | Cross-check the purchase profile, support, commissioning, fake UVC, and intrinsics contracts; by default also require the normal-accept/tag-loss-reject pixel pair, while `--skip-pixel-vision` provides a faster core-only check |
| `simulate-b0477-vision` | Run the selected static camera's exact half-scale synthetic JPEG -> tag decoder -> planar-pose path, including an expected natural tag-loss rejection mode |
| `rehearse-first-power-on` | Run the 15-stage camera-first onboarding state machine with built-in fake camera/arm boundaries, exact-signature fail-stop scenarios, source-bound exact-prefix checkpoint replay, and bounded keyboard/phone virtual mission plus cleanup checks; nominal completion leaves physical onboarding unstarted, incomplete physical collision geometry blocked, and all authority false |
| `plan` | Compile text to semantic key/tap actions; no coordinates |
| `dry-run` | Trace semantic phases; no geometry, IK, calibration, or vision |
| `workcell` | Validate cross-source nominal placemat alignment |
| `stress-placemat-geometry` | Run a source-bound 59-case sensitivity matrix over board registration, device placement, local target maps, and TCP; `--zero-bounds --require-no-gaps` is the nominal control, while default phone-target gaps are diagnostic rather than a physical failure |
| `simulate` | Run nominal alignment, coarse tool-tip geometry, diagnostic sampled IK, and fixed synthetic tag checks |
| `sweep-targets` | Independently screen selected nominal targets/phases plus required initial/final park through IK |
| `optimize-layout` | Compare a bounded set of physical base/tool hypotheses, then fully screen the 46 keyboard and 29 phone contact targets for two finalists plus route parks |
| `optimize-park` | Reproduce the retained Freeze-005-derived bounded, geometry-filtered park overlay and independently screen both selected route tools through IK |
| `study-layout-hypotheses` | Run the wider staged, sensitivity-only base/yaw/tool search; screen named regressions and the ranked top-eight shortlist against all 75 contacts, then identify candidates eligible for a separate route screen |
| `screen-mission-routes` | Run one independent park-to-target-to-park trajectory diagnostic for every locked target; optionally consume only a promoted staged-study rank |
| `stress-adaptive-session` | Run optional Phase-2 fixed signed/boundary plus SHA-256-seeded combined board-pose perturbations through the complete adaptive camera/contact path without serializing private transforms |
| `screen-adaptive-mission-routes` | Run all 46 keyboard and 29 phone targets as independent complete optional Phase-2 moving-camera/contact/outcome/park sessions; slower and stronger than trajectory-only route coverage, but still synthetic |
| `collision-status` | Audit the exact locked URDF and required robot/attachment/environment body coverage; report missing and unknown geometry without claiming that a pose or sweep was checked |
| `simulate-trajectory` | Expand a typed route through park/transit/hover/approach/contact/retract, densify it, and run bounded sequential IK with margin, solver-task numerical-rank, report-only conditioning, sampled joint-delta checks, and explicit achieved TCP position/tool-axis records |
| `simulate-session` | Run the locked multi-action scenario through initialization, virtual calibration closure, trajectory, a fresh fixed-overview JPEG/tag/planar-pose gate at every physical-action hover, achieved-pose contact hit-testing, separate `ContactResult` outcome observation, final park, natural camera/device fault handling, and optional report-v3/manifest-v2 recording with `vision.json` |
| `simulate-integrated-v2` | Assemble and execute the additive dense zero-hardware path through semantic/contact scheduling, mandatory chronological phone-state prerequisites, stateful settled-HOVER B0477 replay, isolated endpoint/midpoint collision queries, authorization-v2, persistent contact journals, the non-wire T104 runtime, geometry-resolved virtual contact, independent outcome, final park, and full receipt replay; controller faults bind the failed trace, camera fault schedules are assembly-sealed global boundaries, and capture-area faults use one coarse causal boundary with optional unauthenticated B0477 diagnostics; `--open-existing` never retries a progressed contact journal; current missions are bounded to eight physical targets |
| `simulate-adaptive-session` | Run the separate optional Phase-2 moving arm-camera rehearsal from achieved six-joint FK through real JPEG/tag pose, board-registration decision, complete accepted suffix replacement, re-observation, truth-derived keyboard/Android contact, independent outcome, and park; hidden-truth offset/yaw controls perturb only the opaque virtual plant and are never serialized as a transform |
| `replay-session` | Verify a session package and recompute its semantic plan, trajectory, pixel-vision ledger, events, contact outcome, and complete report rather than trusting the stored result |
| `calibration-status` | Report ordered missing/stale mission artifacts without capture |
| `solve-eye-on-arm-offline` | Solve an optional Phase-2 strict, pre-split, hash-pinned eye-on-arm dataset and emit a zero-authority diagnostic candidate report |
| `verify-eye-on-arm-fk-offline` | For optional Phase 2, bind exact dataset/evidence bytes to the verified active manifest/build/model and recompute every stored carrier pose from raw T=1051 fields; no commissioning or artifact promotion |
| `verify-eye-on-arm-capture-bundle-offline` | For optional Phase 2, structurally bind exact dataset/evidence/bundle files, raw T=1051 lines, JPEGs, normalized detections, and capture brackets; physical timing and commissioning remain unqualified |
| `arm-feedback` | Future gated one-shot T=105 request/T=1051 response; a single-use build capability is consumed at the serial boundary, and active Freeze 012 denies it before port access |

`simulate-integrated-v2` writes durable journals and therefore requires a new,
nonexistent `--journal-root` for an initial run. Reopening the exact same
assembly with `--open-existing` is deliberately fail-closed: once any journal
has advanced beyond `INTENT_COMMITTED`, automatic execution is refused. This
durably covers contact intent/boundary/outcome/retraction/park state. A
mission-global write-ahead dispatch ledger for every transit/HOVER command is
not implemented yet, so abrupt process recovery after a non-contact command
remains a physical-executor design blocker. The in-memory emulator itself has
no hardware side effect. Internal failure while wrapping a lower-level
controller attempt or already-applied virtual contact can close all journals
and then raise without returning a structured report. Regression tests require
that these cases remain terminal and non-retryable. A physical adapter therefore
also needs durable partial-effect receipts at those two boundaries. Integrated
receipt hashes are consistency evidence, not signatures or MACs; nested B0477
fault detail is explicitly diagnostic rather than authenticated causality.

`sweep-targets --tool-case all --phase all` expands the screening matrix.
`--require-all` makes any rejected point a nonzero exit. Likewise,
`calibration-status --require-ready` returns nonzero until every dependency is
valid. `optimize-layout --require-complete` requires all locked contact targets
and both route parks. `optimize-park --require-both-routes` requires the best
pointwise candidate to accept both route tools. `study-layout-hypotheses
--require-promotable` requires at least one top-eight full-catalog candidate to
be eligible for the separate route screen. `screen-mission-routes --require-all`
requires all 75 independent trajectories. `screen-adaptive-mission-routes
--require-all` separately requires all 75 complete adaptive sessions, and
`stress-adaptive-session --require-pass` requires every expected completion or
safe rejection to match. `collision-status
--require-diagnostic-ready` returns nonzero while required geometry is
incomplete. The trajectory verifier's
`--require-pass` requires every sampled route waypoint,
`solve-eye-on-arm-offline --require-diagnostic-pass`
requires its numerical residual gates, and
`verify-eye-on-arm-fk-offline --require-pass` requires exact FK reproduction
for every supplied sample. The capture-bundle verifier's `--require-pass`
option requires every supplied byte/bracket relationship to pass its structural
policy. None of these options authorizes hardware.

`simulate-session --require-pass` returns nonzero unless every required
fixed-overview pixel/pose attempt passes, the virtual outcome matches, and the
route ends at park. `simulate-adaptive-session --require-pass` additionally
requires correction convergence, accepted truth-derived contacts, independent
output verification, and final park. `replay-session --require-identical` returns nonzero on
source, vision-ledger, or result divergence.
`replay-prehardware-qualification --require-identical` applies the same rule to
the schema-separated aggregate package. None of these options changes a
physical capability or calibration artifact.

`qualify-prehardware --require-pass` keys only off the selected campaign's
software assertions. Its [qualification report](docs/PREHARDWARE_QUALIFICATION.md)
separately exposes whether route coverage ran, whether every route passed, and
`physical_ready: false`. The quick profile is the bounded development loop; the
default standard profile adds all deterministic legacy fault families and the
multi-minute 75-route recomputation. `--record` writes its dedicated
manifest-last qualification schema; replay verifies it and recomputes the
campaign. It is never silently stored in the legacy session package, and the
inner v1 report retains its legacy hash semantics.

The reach optimizer is intentionally narrower than full motion feasibility: it
checks independent contact and park IK with a positive joint-margin gate. The
[park optimizer](docs/PARK_OPTIMIZATION.md) is narrower still: pointwise park
IK plus nominal planar tool-tip clearance. Its selected `(290, 10, 70) mm`
overlay passes both 100 mm tools with `0.2704734350` worst normalized arm
margin and 10 mm modeled clearance, without changing canonical geometry. The
[trajectory diagnostic](docs/TRAJECTORY_SIMULATION.md) adds all nominal motion
phases, Cartesian densification, previous-solution seeding, sampled
joint-delta/margin checks, and a solver-weighted five-constraint
numerical-rank gate. Normalized conditioning is report-only; continuous
full-body collision-free motion, full physical 6D singularity/manipulability,
dynamics, installed transforms, and contact safety remain unproven.

With the optimized park, keyboard `"a"` accepts 24/24 waypoints. Phone `"a"`
fails at `APPROACH` because its normalized arm margin is `0.000657824`, below
`0.01`, and both reach finalists reject phone `key_a` contact. Complete
independent route coverage of this retained Freeze-005-derived baseline accepts
38/75 routes: 20/46 keyboard and 18/29 phone.

The broader study is deliberately a different evidence tier. It screened 243
coarse and 34 refinement hypotheses, found 49 regression passes, ran the full
75-contact screen on the ranked top eight, and promoted six for external route
screening. Rank 1, `reach-944d7463f4c67905`, is the unmeasured sensitivity
overlay rear-clamp X=385 mm, rear-edge-to-axis Y=75 mm, yaw=-105 degrees,
base Z=70.1 mm, clamp-to-axis X=0 mm, and 120/100 mm keyboard/phone
virtual tools. At the fixed `(290, 10, 70) mm` park probe it accepts 75/75
independent routes (2,066 IK solves, 22,726 Jacobian FK evaluations, and 2,424
waypoint records). This does not promote the overlay into the frozen build: the
Y/yaw/tool values are sensitivity-only and no installed geometry, calibration,
collision, dynamics, physical vision, device outcome, or authority is supplied.

The locked virtual commissioning profile now uses that exact overlay to test
multi-target orchestration. Keyboard `test` completes 48 virtual joint
waypoints, requires four fresh six-tag fixed-overview pixel/pose passes,
geometrically resolves four achieved-pose contact events, and verifies their
independently observed output; Android `test.` completes 61 waypoints, checks
the initial UI state, requires five pixel/pose passes, and geometrically
resolves and observes five taps. Both finish at park, close the virtual plant,
and emit zero hardware commands. This is an implemented synthetic closed-loop
sequence test, not eye-on-arm or physical sequence feasibility. See
[the virtual commissioning contract](docs/VIRTUAL_COMMISSIONING.md).

The collision foundation likewise fails closed rather than filling those gaps
with assumed dimensions. `collision-status` binds 19/19 required bodies but
reports seven missing robot envelopes and six unknown installed
base/clamp/holder/camera/connector/cable/tool envelopes, so current full-body
pose and sweep diagnostics remain blocked. The optional Phase-2 offline eye-on-arm dataset,
raw-feedback FK verification, strict structural capture bundle, equations,
policy, and commissioning blockers are defined in [the calibration
foundation](docs/EYE_ON_ARM_CALIBRATION.md).

`SerialTransport` intentionally has no raw `send`/`exchange` surface. Its only
write-capable operation is a one-shot T=105 query requiring a
`SafetySupervisor`-issued feedback permit. Live T=104 motion is hard-blocked
even with an exact-goal permit because calibrated goal bounds and checked-plan
linkage do not yet exist. Permit-gated motion recording remains available only
through the in-memory replay transport for tests.

## How to interpret simulation output

Every successful `simulate --json` report retains:

- `simulation_only: true`;
- `execution_authorized: false`;
- `hardware_accessed: false`;
- `hardware_commands_generated: 0`; and
- the unchanged physical-release state.

Required nominal checks are placemat alignment, coarse tool-tip geometry, and
fixed-fixture tag visibility. Sampled IK is diagnostic while the installed
board-to-robot transform and route TCP remain nominal, so a required-check pass
may still report provisional IK gaps. Virtual sessions feed each solver-achieved
TCP position and tool axis into a synthetic geometric contact model; a separate
observer consumes only the resulting `ContactResult` stream and verifies its
output hash and length. That separation detects simulated misses, neighboring
regions, invalid contact geometry, duplicate activation, ordering errors, and
Android UI-state mismatches without copying the planner's expected character
into the observer.

The additive V2 acceptance pair uses the same locked, unmeasured rank-1 route
and park overlay while making command accounting explicit. Keyboard `test` has
48 accepted route waypoints, 47 non-wire emulator commands, and four
contact-requesting semantic occurrences. Android `test.` has 61 waypoints, 60 commands, and five
contacts; its semantic state observation has no contact, command,
authorization entry, or journal. Every command is joined to its collision
endpoint and incoming midpoint, and every contact is joined to a fresh
synthetic B0477 final-HOVER report. This proves deterministic software
sequencing only.

This is still model evidence. Contact-region dimensions and activation policy
are synthetic. The pixel pipeline renders the fixed-overview fixture, decodes
tag pixels without scene/corner oracle inputs, and estimates
`camera_overview_optical_T_board`; that topology matches the Phase 1 direction,
but it does not capture a physical overhead image or apply a qualified
robot-frame correction. Physical runtime-port adapters, measured static-camera
intrinsics/distortion and `Wv_T_C_overhead_optical`, support/visibility tests,
full-link/gantry/camera/cable collision, `R_ctrl` correlation, and real
keyboard/Android outcome observation are not implemented or performed.

Any manifest, bundle-lock, or source-hash mismatch fails closed. Do not repair a
hash in isolation; reconcile the controlled source and regenerate its approved
projections together.

## Development typing profiles

The keyboard profile supports lowercase letters, digits, space, Enter, Tab,
and unshifted `. , - = / ; '`. The phone profile supports lowercase letters,
space, period, and Enter in required state `KEYBOARD_LOWER`. Unsupported text
fails during planning. These profiles and their nominal target coordinates are
development seeds, not calibrated physical device profiles.

The CLI argument can remain in shell history even though reports retain only a
hash of requested text. Use non-sensitive test strings.

## Source layout

```text
src/rocell/
  application/   coherent context, hardware-neutral runtime ports, orchestration, trajectory/achieved-pose records, studies and readiness
  typing/        semantic keyboard and phone compilers
  workcell/      cross-source placemat alignment
  targets/       nominal target catalog and semantic-profile binding
  motion/        semantic and geometric dry-run engines
  geometry/      frames, transforms, URDF loading, FK
  kinematics/    numerical IK
  simulation/    hardware/scenario projection, synthetic vision/controller, geometric contact truth, independent outcome observation, collision kernels
  calibration/   immutable artifacts plus optional Phase-2 offline eye-on-arm dataset/solver/FK/capture-bundle checks
  safety/        preflight, interlocks, permits, supervisor
  arm/           gated serial transport and RoArm feedback client
  vision/        USB/ESP/mock sources, synchronization, bounded tag36h11 pixel detection, planar pose estimation, immutable records, and calibration foundations
```

## Tests

The static-overhead candidate source coverage audit can be reproduced against
the immutable FREEZE-013 checkout and the retained pending manifest:

```powershell
$env:PYTHONPATH='software/src;software/ai'
python software/ai/run_static_overhead_collision_source_audit.py `
  --contract-workspace <freeze-013-checkout> `
  --source-workspace <current-checkout> `
  --measurement-manifest software/ai/eval/static_overhead_installed_collision_measurements_pending_20261017.json `
  --measurement-manifest-sha256 5ca32f47d65c138c3916361232d608f7ef4f5c40b98edf8d380794e6115d9702 `
  --source-revision 57b21fdda076b9d540e5c825cc5ecf598c90d053 `
  --output software/ai/eval/static_overhead_collision_source_audit_20261017.json
```

Exit code 2 is the expected fail-closed result until installed envelopes,
placements, and uncertainties are qualified. The audit performs no camera or
robot I/O and grants no physical authority.

Build the ordered qualification work order from that retained audit:

```powershell
$env:PYTHONPATH='software/src;software/ai'
python software/ai/run_static_overhead_collision_qualification_work_order.py `
  --source-audit software/ai/eval/static_overhead_collision_source_audit_20261017.json `
  --source-audit-sha256 0b499d9493648d0a9286decc237b979e74a119ad20755c3870beea9b68da4dfc `
  --output software/ai/eval/static_overhead_collision_qualification_work_order_20261017.json
```

The work order reuses retained dimensions, requests no repeated dimension
measurement, and keeps every body pending until envelope, placement, and
uncertainty evidence is accepted.

Derive the next offline candidate-envelope stage from the retained work order:

```powershell
$env:PYTHONPATH='software/src;software/ai'
python software/ai/run_static_overhead_collision_candidate_envelopes.py `
  --workspace . `
  --work-order software/ai/eval/static_overhead_collision_qualification_work_order_20261017.json `
  --work-order-sha256 7778833cd1cbab12a1559de5900fa053843a062b9e2dc4565968a2ea913b9d2b `
  --output software/ai/eval/static_overhead_collision_candidate_envelopes_20261017.json
```

This dependency-free pass reads the controlled STL, layout, support, camera
generator, and robot reduction sources and binds every source hash into the
result. It derives 16 candidate envelopes and nine candidate board-frame
placements. The camera module and revised USB keeper placement are recovered
from the controlled printable-frame CAD contract. The base and factory clamp,
fixed flexible cable, and bare-jaw absence declaration remain without
geometry; all 19 bodies still require accepted uncertainty. It does not create
an installed profile or execute collision screening.

From the workspace root:

```powershell
python -m pytest software/tests
```

Or from `software/`:

```powershell
python -m pytest tests
```
