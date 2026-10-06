# Tactevra Runtime software architecture

## Purpose and authority boundary

Tactevra Runtime turns keyboard or Android text into deterministic, reviewable software
artifacts for the RC03 placemat. The current runtime is a simulation and
commissioning foundation. It does not expose a live-motion command, produce
controller motion commands, press a key, or tap a screen.

The implementation retains the `rocell` Python, command, schema, and
configuration namespace for compatibility. Tactevra is the product name; see
the repository [glossary](../../docs/GLOSSARY.md).

The controlled baseline is manifest
`ROCELL-PHASE0-RC03-INT-R1-FREEZE-012`, design revision `RC03-INT-R1`, active
build `2026-09-01_CELL-A`. Both typing routes are selected. Physical release is
`UNRELEASED`; `safe_to_power_robot` and `contact_enabled` are false. Those
values are imported from the verified build snapshot and are never promoted by
a simulation report. The active measurement-gate counts are
`15 PASS / 63 NOT_TESTED / 4 NA / 2 FAIL`; Job 00A is `POSTPRINT_PASS` and
the two failed legacy Job 00B nut/tie gates are reassigned to Job 03C1.

## Camera architecture migration — 2026-09-05

The selected Phase-1 primary vision architecture is now a rigid, static
overhead (eye-to-hand) camera. The purchased catalog configuration is the
Arducam B0477 with its included 16 mm lens, and the source-locked support
candidate uses nominal entrance-pupil pose `B=(305,228.5,1000) mm`. Received
identity and dimensions, installed pose, support metrology, optics, lighting,
calibration, and physical qualification remain open. This selection has zero
physical authority: it does not change the existing release, power, motion, or
contact gates.

The implemented fixed-overview JPEG -> tag36h11 -> planar-pose path is the
software migration target because it models a stationary camera. Its fixture,
intrinsics, pixels, measurements, and acceptance results remain synthetic, so
it is not evidence that a physical camera, mount, field of view, calibration,
or observation policy is acceptable. Eye-on-arm components are retained only
as disabled, opt-in Phase-2 research. They are not an automatic fallback or
substitute for the Phase-1 primary and require independent qualification and a
controlled release before physical use.

References below to Freeze-009 arm-camera choices are retained as provenance
for that earlier direction and are explicitly historical or optional Phase 2.
They must not be read as current hardware instructions. Active Freeze 012
keeps the legacy canonical camera fields under
`CAMERA_ARCHITECTURE_ALIGNMENT_HOLD`; replacing them still requires a
synchronized superseding controlled freeze.

Freeze 006 recorded the seven-source Job 00A lifecycle/evidence transition in
the measurement record, step-package index/validation, release validation,
print readiness, build tracker, and prehardware readiness. Freeze 007 binds the
later evidence-only as-built traceability note for the pre-label-correction Job
00A coupons and the regenerated measurement/readiness derivatives. Freeze 008
then synchronizes operator-waived prototype Job 00A M4 functional-fit evidence
and regenerated dependents. That evidence moves
`tray_clearance_holes_coupon_pass` to `PASS` based on demonstrated passage
through the nominal `4.4 mm` hole and fit in the nominal `9.2 mm` washer recess;
the nominal M4 diameter of `4.0 mm` is explicitly assumed, not measured. This
is not dimensional metrology and has no physical-release effect. Freeze 009
then records the operator-confirmed
`keyboard_station_registration_coupon_pass` at the `6.2 mm` round/slot
selection, advances Job 00A from `PRINTED` to `POSTPRINT_PASS`, and regenerates
the same seven controlled derivatives. It does not release downstream print,
robot power, motion, or contact. None of these transitions renames the
unchanged Freeze-005-derived reach, park,
optimization, target-map, or report evidence; those provenance labels and
hashes remain historical inputs when cited below.

The core boundary is deliberately one-way:

```text
operator text
    |
    v
semantic profile/compiler -----> ActionPlan + plan hash
    |                                  |
    |                                  v
    +--------------------------> nominal target binding
                                       |
verified, hash-linked sources ---------+
    |                                  v
    +--> placemat alignment --> geometric tool-tip path
                                       |
                                       v
           sequential URDF IK + local numerical-rank gate
                                       |
            hover -> one of two plan-blind fresh-JPEG paths:
              Phase-1 target: fixed overview -> board registration
              Phase-2 research: achieved-FK moving C_arm -> correction
                                       |
                  optional full accepted suffix replacement
                                       |
                                       v
                  achieved tip XYZ + achieved tool axis
                                       |
                                       v
       board-frame contact event (position, normal, dwell, activation)
                                       |
                                       v
     virtual region/depth/normal/dwell/focus/UI truth -> ContactResult
                                       |
                                       v
                    ContactResult-only outcome observer
                                       |
                                       v
             outcome hash, final park, immutable record/replay

                     no serial, camera, motion, or contact I/O
```

The geometric path's `VERIFY` and `VISION_CORRECT` records remain physical
observer requirements. The replay-stable virtual session renders a real
fixed-overview JPEG, independently detects tag36h11 pixels, builds a typed
detection batch, estimates an explicit optical-camera-to-board pose, and gates
approach on a synthetic quality policy. A separate adaptive-schema runner
projects `C_arm` from achieved six-joint FK, renders its moving partial view,
recovers a candidate `Wv_T_board`, and either rejects, retains the current
registration, or atomically installs a completely re-solved suffix. Both
processors are plan-blind; action/target association happens afterward. These
are zero-authority software paths, not physical correction. See
[pixel vision simulation](PIXEL_VISION_SIMULATION.md) and
[arm-camera correction simulation](ARM_CAMERA_CORRECTION_SIMULATION.md).

Contact truth is now separated from the semantic plan more strongly. The
session converts each contact endpoint's accepted IK result into an achieved
board-frame tool-tip position and contact normal, then adds the declared
virtual dwell and fault-controlled activation count. The virtual keyboard or
Android model receives no planned target identifier or expected character; it
resolves polygon membership, depth, normal angle, dwell, focus, and UI state to
an immutable `ContactResult`. A separate observer consumes only those results,
exactly once, and exposes a redacted output hash and length. This removes the
previous expected-character shortcut but is still a deterministic model
agreement check, not independent physical device evidence.

Phone semantic plans make the same distinction: a tap's declared
`resulting_state` is only a prediction. A matching `VerifyPhoneState` must
observe that state before another tap may depend on it or the plan may finish.
This prevents a compiler or deserializer from silently converting expected UI
behavior into observation evidence.

## Runtime layers

| Layer | Current responsibility | Main modules |
| --- | --- | --- |
| CLI boundary | Parse commands, emit stable JSON/errors, load hardware adapters only behind a passed capability gate | `rocell/cli.py` |
| Build import and authority | Verify the manifest and controlled-source hashes; project digital, simulation, feedback, and contact capabilities | `rocell/rc03/` |
| Coherent context | Load one manifest-selected, hash-linked profile, scene, target catalog, model, camera binding, and alignment report | `rocell/application/context.py` |
| Virtual startup | Strictly assemble runtime policy, complete context, capability projection, calibration inventory, non-opening arm profile, synthetic overview health, and collision readiness | `rocell/application/bootstrap.py` |
| Hardware-neutral runtime contracts | Define immutable request/result envelopes and structural protocols for clock, arm lifecycle/execution/feedback, observation, contact, outcome, cancellation, and evidence; validate complete bundles and zero-authority declarations | `rocell/application/runtime_ports.py` |
| Ordered zero-authority authorization | Bind the exact device calibration closure, build/controller/session identities, collision-cleared command sequence, operator nonce, device state, plan/action occurrences, and advancing interlock evidence; consume only the next exact simulation command and remain incompatible with live transport | `rocell/safety/authorization_v2.py` |
| Synthetic authorization projection | Project the exact static Phase-1 `NOMINAL_ONLY` closure, build deterministic emulator/evidence identities, and advance one-command-at-a-time synthetic interlock continuity without live authority | `rocell/safety/synthetic_authorization.py` |
| Semantic typing | Compile supported characters into named key/tap actions without coordinates | `rocell/typing/`, `rocell/models/actions.py` |
| Semantic execution schedule | Preserve separate semantic-step and physical-contact occurrence ordinals; retain Android state checks as observation-only work with no contact, route command, authorization command, or journal | `rocell/application/semantic_step_schedule.py` |
| Placemat and target binding | Cross-check RC03 revision, envelopes, tags, route/profile bindings, nominal arm placement, camera identity, and physical holds | `rocell/workcell/`, `rocell/targets/` |
| Geometric simulation | Expand actions into transit, hover, correction placeholder, approach, contact, retract, and verification-placeholder phases; check tool-tip segments against nominal AABBs | `rocell/motion/geometric_sim.py` |
| Full-body collision foundation | Declare and audit bounded robot/attachment/environment envelopes; run zero-authority primitive pose and discrete-sweep diagnostics only after complete required-body coverage | `rocell/simulation/collision.py`, `rocell/application/collision_readiness.py` |
| Static B0477 route-collision diagnostic | Add an exact 26-body/nine-source static-camera contract; evaluate seven ordered phase endpoints and six caller-supplied midpoint-bearing adjacent segments with configuration-sampled arm-harness geometry and a CONTACT-local exact target allowance; remain diagnostic-only | `rocell/simulation/static_route_collision.py` |
| Dense static mission collision | Bind every final accepted trajectory endpoint and every incoming exact 0.5 joint midpoint to the command sequence; provide a separately named isolated-geometry fixture that exercises the software contract while permanently denying physical-clearance evidence | `rocell/simulation/static_mission_route.py`, `rocell/simulation/static_mission_fixture.py` |
| Kinematics and controller models | Load the pinned local URDF projection, perform FK/numerical IK, diagnose numerical rank/conditioning of the weighted five-constraint solver task, and provide a separate deterministic firmware-model emulator | `rocell/geometry/`, `rocell/kinematics/`, `rocell/simulation/controller.py` |
| Isaac Sim advisory oracle | Import and parity-check the governed articulation, compose the RC03 USD scene, visualize model proposals, replay source-bound schedules, and compare finite collision candidates; never re-interpret semantics, emit wire commands, or promote physical gates | [Isaac Sim implementation](../integrations/isaac_sim/README.md), [integration plan](ISAAC_SIM_INTEGRATION_PLAN.md) |
| MuJoCo Warp evaluation lane | Proposed high-throughput population physics for contact, mechanics, and recovery studies after version/asset pinning and parity; no MJWarp replay is currently merged | [Simulation overview](../../docs/SIMULATION.md) |
| Dense non-wire controller schedule | Map every accepted waypoint after the known initial park to an exact bounded T=104-shaped emulator target, with separate route and authorization ordinals; expose no encoder, transport, or live permit | `rocell/application/dense_route_schedule.py`, `rocell/simulation/t104_runtime.py` |
| Synthetic projection check | Project the six RC03 tags through a deterministic fixed overview fixture; this is not the live eye-on-arm session observer | `rocell/simulation/camera.py` |
| Synthetic pixel perception | Render a deterministic fixed-overview grayscale JPEG, independently decode released tag36h11 pixels, and estimate a planar board pose without receiving simulator pose/corner truth | `rocell/simulation/synthetic_raster.py`, `rocell/vision/apriltag_codebook.py`, `rocell/vision/pixel_detector.py`, `rocell/vision/planar_pose_estimator.py` |
| Canonical B0477 optical boundary | Preserve the published FOV as provenance, enforce one square-pixel aspect-consistent projection in `C_overhead_optical`, distort synthetic capture pixels, rectify detected corners into an explicitly named estimator space, and hash-bind the analytic map | `rocell/application/b0477_optical_contract.py`, `b0477_static_vision.py` |
| Per-contact B0477 mission evidence | Require one fresh accepted synthetic B0477 report at each contact's final HOVER and bind it to the exact route/auth ordinals and expected settled controller pose | `rocell/application/b0477_mission_observations.py` |
| Typed vision boundary | Bind frame identity/hash/settings/timing, detector and estimator identities/configurations, canonical marked-tag corners, inlier masks/residuals, explicit-frame poses, 6x6 covariance, and source hashes with zero authority | `rocell/vision/detections.py`, `rocell/vision/pose_estimation_records.py` |
| Virtual execution | Decode the locked sensitivity scenario; resolve explicit non-physical calibration substitutes; execute accepted joint waypoints; require plan-blind fixed-overview pixel/pose quality at each hover; derive achieved contact geometry; resolve device contact truth; and exercise one-use faults | `rocell/simulation/virtual_profile.py`, `virtual_workcell.py`, `rocell/application/virtual_calibrations.py`, `virtual_pixel_vision.py`, `virtual_session.py` |
| Optional Phase-2 adaptive arm-camera execution | Derive moving-camera pose from achieved feedback; render/decode/estimate without semantic input; classify board registration; re-solve and atomically replace a safe suffix; re-observe convergence; project fresh achieved FK into shared opaque truth for contact; verify output and park | `rocell/application/arm_camera_pose.py`, `virtual_board_truth.py`, `virtual_arm_camera.py`, `board_pose_correction.py`, `corrected_trajectory_suffix.py`, `actual_contact_geometry.py`, `adaptive_virtual_session.py` |
| Virtual outcome observation | Consume only immutable `ContactResult` records, exactly once, and expose redacted output hash/length evidence without receiving the plan, expected character, or planned target | `rocell/simulation/virtual_outcome.py` |
| Evidence and replay | Atomically write hash/byte-bound split artifacts including the redacted vision ledger, strictly reconstruct nested vision records/hashes, then rerun the planner/executor and compare every artifact | `rocell/evidence/virtual_session.py` |
| Raw sensor-session evidence | Record bounded synthetic transport bytes, raw/decoded/undistorted frames, camera identity/mode/controls, timing brackets, calibration/source hashes, detections, pose, and unsent feedback fixtures in an exact-file manifest-last package; verify and replay with zero authority | `rocell/evidence/sensor_session.py` |
| Crash-safe action journal | Give each semantic action occurrence a stable mission/plan/ordinal/action identity, persist state transitions before risky boundaries, hash-chain append-only records, and maintain a directory-synced high-water record that latches the first possible-contact event and exact tail; suffix loss/truncation fails closed and possible-contact recovery permits observation/retract/manual review but never automatic contact retry | `rocell/application/mission_journal.py` |
| Crash-aware multi-action kernel | Orchestrate complete virtual/replay runtime-port bundles with an exact journal-derived authorization suffix; bind per-command receipts and independent semantic outcomes; stop later contacts on failure; and preserve primary, cleanup, park, and final-validation accounting | `rocell/application/multi_action_mission.py` |
| Additive integrated mission V2 | Join the semantic schedule, mandatory chronological phone-state prerequisites, source-revalidated dense route, stateful settled-HOVER B0477 observations, endpoint/midpoint collision results, synthetic authorization, non-wire controller runtime, per-contact journals, geometry-resolved virtual contact, independent outcome, structured fault boundaries, full receipt replay, and final park | `rocell/application/multi_action_mission_v2.py`, `rocell/application/integrated_zero_hardware_mission.py` |
| Physical-shaped onboarding seam | Exercise fake-only provider protocols for receipt, persistent camera identity, exact settings, freshness/reopen, retained-install acquisition, arm-off identity, safety/power-event records, one T=105 exchange, and unconditional cleanup; expose no T=104, raw-write, motion, or contact method | `rocell/application/physical_shaped_onboarding.py` |
| Application reports | Coordinate simulation, exhaustive target screening, bounded reach-layout and park-pose studies, broader pre-hardware layout sensitivity, independent full-catalog route coverage, collision readiness, discrete sequential-IK diagnostics, virtual sessions, and read-only calibration dependency assessment | `rocell/application/` |
| Physical foundations | Model permit-consuming serial feedback, camera sources, safety preflight, permits, immutable calibration artifacts, an optional Phase-2 zero-authority offline eye-on-arm candidate solver, raw-feedback FK reproduction, and a strict raw-wire/image/detection/bracket capture bundle; not assembled into a motion executor | `rocell/arm/`, `rocell/vision/`, `rocell/safety/`, `rocell/calibration/` |

The runtime-port layer now has a zero-authority consumer:
`run_zero_authority_multi_action_mission` executes journaled virtual/replay
operations only when supplied an exact authorization-v2 cursor. The existing
geometry-rich `_SessionExecutor` has not yet been rewritten to consume that
kernel, however, and virtual-session replay still recomputes through the direct
application path.

The former zero-hardware assembler gap is closed by the additive V2 path. It
binds each exact semantic plan and dense route into one executable rehearsal.
For the locked acceptance pair, keyboard `test` has 47 commands and Android
`test.` has 60. V2 also binds fresh per-contact B0477 reports, endpoint and
joint-midpoint collision results, `NOMINAL_ONLY` calibration closure,
authorization-v2 sequence, journals, and the non-wire controller emulator.
V2 does not replace the V1 `MultiActionMissionSpec`; it preserves V1's stable
four-compound-operation contract and uses separate schemas.

V2 treats observation-only phone steps as hard ordering prerequisites. Motion,
camera, contact, tail, and fault-frontier evidence cannot skip them or an
unfinished intervening contact. Its B0477 fault schedule is sealed into the
assembly and enforced as a global execution boundary. Controller failures bind
the deterministic failed T104 trace. Capture-area failures deliberately share
the coarse causal label `SettledHoverObservationBoundary`; any nested typed
B0477 fault is explicitly unauthenticated diagnostic detail because report
hashes are consistency seals, not signatures or MACs.

Neither V2 nor the older paths are an integrated physical runtime. V2 runs
directly against a non-wire emulator, uses deliberately isolated stand-in
geometry with `physical_clearance_established=false`, and has no commissioned
`R_ctrl` correlation or physical provider. See
[pre-hardware runtime foundations](PREHARDWARE_RUNTIME_FOUNDATIONS.md).
Per-contact journals also do not persist a mission-global dispatch high-water
for transit/HOVER motion. Internal wrapper failure after an emulator attempt or
already-applied virtual contact terminalizes the journals but can raise before a
structured report is available. Both gaps must be closed with global dispatch
and partial-effect receipts before a physical adapter exists.

The simulation bundle lock binds the simulation profile, nominal target catalog,
arm-frame contract, camera manifest, local URDF, and virtual commissioning
profile by path and SHA-256. Context
loading also binds the selected system manifest, design revision, RC03 root,
workcell layout, AprilTag map, and semantic profile IDs. A missing, changed, or
cross-workspace source fails closed before planning geometry. Each application
service reconstructs that canonical context at its entry boundary and compares
every component, so an in-memory dataclass replacement cannot reuse old bundle
or alignment evidence.

The simulation, target-sweep, reach, park, broader-layout, mission-route,
trajectory, and collision-readiness services use one bounded exact-byte URDF
loader. They verify the expected digest before parsing the same captured bytes
and serialize the loaded digest and byte count in provenance; they do not hash
one read and parse a later filesystem read.

## Placemat-to-software contract

The RC03 layout is modeled by role, not by the JSON section in which a value
happens to appear. In particular, the TCP puck is listed under `devices` in
the controlled layout but is a point datum, not a third interactive device or
an obstacle with invented dimensions.

| Physical placemat element | Frozen nominal contract | Software use |
| --- | --- | --- |
| Board | 610 x 457 x 18 mm; front-left top is `B`; +x right, +y rear, +z up | Root frame and controlled board AABB |
| PERIBOARD-409 | Origin (85, 85) mm; 315 x 147 x 21 mm | Interactive `keyboard` envelope and 46 synthetic key regions |
| Galaxy A16 | Origin (499.2, 84.2) mm; 77.9 x 164.4 x 7.9 mm; nominal screen z 11.9 mm | Interactive `phone` envelope and 29 synthetic Android/Gboard regions |
| Replaceable TCP puck | Board point (441, 180, 10.5) mm; part `calibration_puck` | Typed `NominalCalibrationTarget`; alignment datum only, with no physical-contact authority |
| Indexed stations | Two keyboard station proxies and one phone/TCP station proxy | Conservative tool-tip keepouts; not measured solid geometry |
| AprilTags | T0-T3 world tags plus held-out K0/P0 station checks | Exact ID/family/role/centre/yaw validation and synthetic projection |
| Arm clamp/base seed | Rear-edge clamp x range 225-385 mm; nominal `B_T_Wv` translation (305, 457, 0) mm | Diagnostic reach/IK seed only; never a controller command transform |

The 17 placemat checks pin these relationships, target/profile semantics,
camera identity, required calibration dependencies, and physical-authority
holds before any geometric report can pass. These values remain nominal until
the installed device, puck, tags, arm base, camera, and TCP are measured.

## Command surfaces

| Command | What it proves | What it does not prove |
| --- | --- | --- |
| `status` | Controlled snapshot integrity and projected capabilities | Hardware health or calibration |
| `bootstrap-sim` | Runtime policy, complete source bundle, gate projection, calibration inventory, non-opening arm profile, synthetic overview, and collision inventory initialize coherently | Physical calibration, collision completeness, camera operation, robot health, or authority |
| `rehearse-first-power-on` | All 15 camera-first onboarding stages execute in canonical order through strict synthetic receipt/UVC/vision boundaries, a hardware-incapable typed RoArm protocol session, the complete 15-artifact static Phase-1 graph with 68 stale-edge probes, and keyboard/phone virtual missions bound to one shared latest Stage-8 B0477 context; nominal output exposes 109 virtual waypoints plus nine virtual contacts/observations, the regression matrix requires every pre-fault record to equal nominal plus an exact terminal stage/detail/check/count signature, checkpoints source-bind implementation/runtime/transitive inputs and replay their exact prefix, and stall cleanup proves no later contact; historical virtual pixels remain per-action, so no fresh B0477 frame per contact is claimed | Camera receipt, physical buffering/timing, OS enumeration, a live serial connection, physical power-on behavior, complete physical collision geometry, physical calibration, motion/contact authority, or a controlled supersession of the retained legacy camera bindings |
| `doctor --mode sim` | Digital planning and the complete virtual bootstrap are available without hardware imports | Physical readiness or hardware health |
| `plan` | Text can compile into hashable semantic actions | Coordinates, reach, collision, or execution |
| `dry-run` | Semantic action/phase trace is deterministic | Geometry, IK, calibration, vision, or execution |
| `workcell` | Cross-source nominal placemat alignment checks pass | Measured installation alignment |
| `simulate` | Required nominal alignment, coarse tool-tip geometry, and fixed-fixture synthetic tag checks; sampled IK is diagnostic | Full-link/cable collision, commissioned Phase-1 static vision, optional Phase-2 arm-mounted vision, controller equivalence, device outcomes, or motion |
| `sweep-targets` | Independent IK screening across selected nominal targets, phases, virtual tool cases, and required park | Branch-continuous paths, swept collision, measured reach, or controller commands |
| `optimize-layout` | Bounded comparison of RC03 rear-clamp/base/tool hypotheses, followed by full locked-catalog contact and route-park IK for finalists | Approach/hover/transit continuity, collision, singularity, measured installation geometry, or motion |
| `optimize-park` | Geometry-derived bounded XY search at the nominal transit Z, with independent pointwise IK for both selected route tools | A path from the installed state, swept/full-body collision, canonical geometry change, or motion authority |
| `simulate-trajectory` | Ordered park/transit/hover/approach/contact/retract endpoints, bounded densification, sequential IK, joint intersection/margin, solver-task numerical-rank, report-only conditioning, and adjacent sampled-joint delta diagnostics | Continuity between samples, full-body collision, physical 6D singularity/manipulability, dynamics, vision/outcome observation, measured geometry, or motion |
| `simulate-session` | Multi-action initialization, explicit virtual calibration closure, action-indexed accepted trajectory, a fresh plan-blind fixed-overview JPEG/tag/planar-pose gate at every physical-action hover, achieved-IK contact events, geometry/depth/normal/dwell/focus/UI device resolution, independent `ContactResult`-only output accumulation, fail-stop faults, final park, and optional report-v3/manifest-v2 evidence with `vision.json` | Runtime-port integration, measured contact/device behavior, installed geometry, physical eye-on-arm performance, robot-frame correction, a physical outcome observer, hardware validation, full collision/dynamics/contact safety, controller commands, or authority |
| `simulate-integrated-v2` | The additive dense acceptance route executes through semantic/contact scheduling, mandatory state-observation prefixes, one fresh stateful synthetic B0477 final-HOVER report per contact, endpoint and exact joint-midpoint collision bindings, ordered authorization-v2, persistent journals, a non-wire T104-shaped runtime, assembly-bound controller/camera fault schedules, virtual contact/outcome, full receipt replay, retract, and park | A sendable T=104, authenticated persisted causality, mission-global dispatch recovery, measured collision geometry or clearance, commissioned `R_ctrl`, physical camera freshness/calibration, a real outcome observer, or live authority |
| `simulate-adaptive-session` | Optional Phase-2 achieved-joint moving-camera FK, real JPEG/tag/pose recovery, pure board-registration decision, complete accepted suffix replacement, corrected-hover convergence, private-truth achieved contact, independent output, and final park; optional hidden-truth offsets perturb only simulation | Persisted/replayed adaptive evidence, measured mount/intrinsics/timing, controller correlation, physical collision/contact/outcome evidence, commands, or authority |
| `replay-session` | Exact package bytes are valid and every stored session artifact can be reproduced by the current locked sources and implementation | Physical repeatability, hardware capture authenticity, or safety release |
| `study-layout-hypotheses` | Staged, source-traceable sensitivity search over 243 coarse layout/tool hypotheses, bounded refinement, a top-eight full-catalog shortlist, and an explicit route-screen promotion gate | An exhaustive search of all regression passes, mechanically allowed dimensions, measured installation geometry, collision, or physical authority |
| `screen-mission-routes` | Exactly 46 keyboard and 29 phone targets evaluated as independent park-to-target-to-park routes through the canonical trajectory service | Arbitrary text sequence feasibility, joint-state continuity between targets, continuous collision freedom, measured reach, or execution |
| `collision-status` | Exact-source audit of all 19 required full-body collision records and their missing/unknown blockers | A pose/sweep query, measured geometry, continuous collision freedom, hardware motion, or contact authority |
| `calibration-status` | Ordered missing/stale artifact dependencies | Calibration capture or physical release |
| `solve-eye-on-arm-offline` | Optional Phase-2 hash-pinned, pre-split `A X C = Z` numerical candidate with observability and residual diagnostics | Trusted FK, qualified timing, physical calibration promotion, camera access, or arm access |
| `verify-eye-on-arm-fk-offline` | Optional Phase-2 exact-file-pinned raw T=1051 joint projection and `Wv_T_E` recomputation through the reviewed URDF | Authentic physical capture, qualified timing, correct measured registration, commissioning, artifact promotion, or hardware access |
| `verify-eye-on-arm-capture-bundle-offline` | Optional Phase-2 exact-file-pinned structural agreement among the dataset, decoded feedback evidence, raw T=1051 wire lines, JPEGs, normalized detections, and pre/exposure/post brackets | Device measurement time, qualified clock correlation, registry-resolved identities, raw tag corners/inliers/covariance, commissioning, or capture |
| `arm-feedback` | In a future released build, issue one T=105 request and parse its T=1051 snapshot from an explicitly commissioned port | Motion or contact; it is denied before port access in active Freeze 012 |

`--require-all` on `sweep-targets` and `screen-mission-routes`,
`--require-complete` on `optimize-layout`, `--require-both-routes` on
`optimize-park`, `--require-promotable` on `study-layout-hypotheses`,
`--require-diagnostic-ready` on `collision-status`, `--require-ready` on
`calibration-status`, `--require-diagnostic-pass` on the offline solver, and
`--require-pass` on the trajectory/FK/capture-bundle/session verifiers and
`--require-identical` on replay turn reported gaps or divergence into a nonzero
process exit. They do not grant authority when they pass.

`rehearse-first-power-on --scenario nominal --require-expected` ends at exact
status `SIMULATION_WORKFLOW_COMPLETE_PHYSICAL_ONBOARDING_NOT_STARTED`. See the
[operator-facing onboarding contract](FIRST_POWER_ON_ONBOARDING.md) for the
stage order, possible automatic RoArm startup-motion boundary, exact-prefix
checkpoint semantics, and physical evidence that must replace each synthetic
result. The nominal hardware-incapable emulator uses two scripted
open/query/close T=105 transactions to test framing and bounded exchange
accounting across reopen. Because T=1051 has no echoed host ID, the shared wire boundary also
requires an empty receive buffer before every request; the stale case rejects a
complete old reply before a second write. It cannot mint or consume a live
feedback permit. The first physical read-only
session remains one bounded, properly authorized T=105 transaction, followed
only by an approved non-motion firmware-readback method; neither operation
authorizes initialization or motion.

The hardware transport has no public raw `send` or `exchange` API. One T=105
request requires a short-lived, single-use `FeedbackPermit` minted by the
safety supervisor from an `ARM_FEEDBACK`-allowed immutable build snapshot. The
transport consumes the permit before its only serial write attempt. Its live
motion method is an unconditional software block: an exact-goal
`MotionPermit` proves message identity and freshness, but it does not prove a
calibrated workspace/orientation/gripper/speed envelope or bind that goal to a
checked path. Permit-gated T=104 recording therefore exists only in the
in-memory replay transport until that separate bounded executor authority is
implemented and validated.

Motion preflight reports are non-empty evaluator-issued values. A
`SafetySupervisor` accepts only its own most recent report, consumes it once,
and reruns the same capability/interlock/calibration checks at permit issuance
so a once-fresh condition cannot be replayed after it becomes stale. An empty
calibration resolution is explicitly invalid.

## Frames and model separation

The software keeps these frames distinct:

| Frame | Meaning |
| --- | --- |
| `B` | RC03 board frame: front-left finished top, +x right, +y rear, +z up |
| `Wv` | Vendor URDF world/root |
| `R_u` | Vendor URDF `base_link` |
| `R_ctrl` | Firmware T=104/T=1051 Cartesian frame |
| `C_overhead_optical` | Selected Phase-1 static overhead optical frame |
| `C_arm` | Optional, disabled Phase-2 arm-mounted optical frame |
| `E` / `holder` | Optional Phase-2 carrier and bundled-holder frames |
| `G` | Vendor `hand_tcp` planning/tool-holder frame |
| `T` | Route-specific physical contact-tool tip |

No equality is assumed between `R_ctrl`, `Wv`, or `R_u`; between the static
support, `C_overhead_optical`, and any robot frame; or between `G` and `T`. In
particular, a URDF pose cannot become a
T=104 request until installed-arm controller correlation and residual bounds
exist. T=1041 is not an allowed substitute.

The model is a kinematic seed pinned to official Waveshare ROS Xacro source and
projected locally to a strict URDF. It is not a validated dynamic twin. The
route simulator still checks only tool-tip segments against coarse
board/device/station/tag AABBs. A separate
[full-body collision foundation](COLLISION_FOUNDATION.md) now names robot,
static gantry, camera, lighting, cable, tool, clamp, and environment bodies
(plus optional arm-camera bodies), but its
current 19-body readiness audit is blocked by missing/unknown geometry and it
is not yet a route-level or hardware-authority check.

## Vision boundary

The selected Phase-1 architecture is the static overhead USB/UVC Arducam B0477
with its included 16 mm lens. A source-locked nominal front-portal support and
`B=(305,228.5,1000) mm` entrance-pupil pose are defined for simulation and
detailed screening; received identity/dimensions, installed pose and aim,
lighting, native-mode readback, controls, calibration, and qualification remain
open. The Waveshare IMX335-B and bundled holder are historical Freeze-009
arm-camera candidates retained under the active Freeze-011 alignment hold, not
current Phase-1 selections.

The synthetic fixed-overview fixture supports both the cheap bootstrap
projection check and the replay-stable session's real-JPEG detector/planar-pose
quality gate. Its topology now matches Phase 1, but its pose, intrinsics, pixels,
thresholds, and truth comparison are synthetic and are never converted into a
physical robot-frame correction. The separate adaptive path simulates optional
Phase-2 moving-camera equations using an explicitly unmeasured `link2_T_E`,
`E_T_C_arm`, and wide-FOV pinhole model plus strict synthetic two-sided feedback
timing. Physical static-camera coverage, distortion, support drift, occlusion,
freshness, `Wv_T_C_overhead_optical`, and controller correlation remain
`NOT_RUN` or `OPEN_BLOCKING` until measured and qualified.

The fixed-overview simulation now exercises the typed perception boundary with
real image bytes. A deterministic renderer emits a grayscale JPEG in a
`FramePacket` without embedding tag IDs, expected corners, or detection truth.
An independent bounded detector receives only that packet, detector policy,
and the released tag36h11 codebook. It returns an
`AprilTagDetectionBatch`; after resolving code rotation, every accepted corner
sequence retains the marked-tag canonical `TL, TR, BR, BL` identities rather
than being re-sorted by image position.

The planar estimator receives only that typed batch, explicit pinhole
intrinsics, an immutable board tag-corner map, and bounded estimator policy. It
fits a normalized homography and, in
`rocell.planar_apriltag_homography` version `1.1.0`, selects a unique
maximum-support tag consensus before monotonic refinement: refits may remove
an inlier but never re-admit an excluded tag. It then decomposes the result
using the pinhole matrix and returns an `AprilTagPoseObservation`. Because the
tag faces lie at the map's explicit
`tag_plane_z_board_mm`, it converts the recovered tag-plane translation to the
board origin with `t_board = t_plane - r3 * tag_plane_z_board_mm`. The output
preserves the exact optical frame from the intrinsics; the current fixture
therefore yields `camera_overview_optical_T_board`.

The current locked fixed-view regression fits all six detected tags. It is not
yet the Phase-1 estimator contract: production-aligned migration must fit pose
from T0-T3 only, exclude K0/P0 from that fit, and evaluate K0/P0 afterward as
independent residual checks.

The immutable records bind exact frame/JPEG/settings/timing data, detector and
estimator identities/configurations/implementation hashes, canonical corners,
per-tag residuals and inlier masks, exact intrinsics and tag-map hashes, an
explicit-frame pose, and a finite symmetric 6x6 diagnostic covariance. All
declare zero physical authority. In the combined development fixture, all six
released IDs were recovered with approximately 0.7063 px reprojection RMSE and
0.268 mm translation error. Those figures characterize one deterministic
fixed-camera simulation, not a selected or qualified physical camera/support.

The fixed-overview path now gates every physical-action hover in the virtual
session. Report schema v3 summarizes its sealed attempt ledger; manifest schema
v2 records the full redacted ledger in `vision.json`, and replay strictly
reconstructs and recomputes it. Camera-unavailable mode stops before a frame;
tag-loss mode changes the rendered pixels and is rejected naturally by the
detector/pose minimum. The path remains outside physical `VISION_CORRECT`,
physical `VERIFY`, and physical capture. It does not supply a static
`Wv_T_C_overhead_optical`, board-to-robot transform, controller correlation, or robot-frame
correction. A syntactically valid or low-residual observation does not
establish physical detector quality, covariance calibration, camera timing,
pose accuracy, or provenance. The complete boundary, corner convention, fault
cases, and remaining calibration work are specified in
[pixel vision simulation](PIXEL_VISION_SIMULATION.md).

## Calibration dependency graph

The physical calibration registry is intentionally empty. Nominal JSON, demo
intrinsics, or commanded poses are not commissioned evidence. The selected
Phase-1 graph is a new versioned static-overhead namespace; it does not
reinterpret the historical Freeze-009 eye-on-arm artifact IDs:

```text
B0477 identity -> mode -> settings -> static intrinsics ------+
measured tag map ----------------------------------------------+-> static extrinsic

robot reference -> controller correlation --------------------+
static extrinsic + tag map + robot reference + correlation ---+-> arm/board

intrinsics + tag map + static extrinsic -> keyboard target map -+-> keyboard outcome observer
arm/board + correlation + keyboard target map ------------------+-> keyboard TCP

intrinsics + tag map + static extrinsic -> phone target map ----+-> phone outcome observer
arm/board + correlation + phone target map ---------------------+-> phone TCP
```

Each accepted artifact must be immutable, content-addressed, tied to the system
manifest and active build, and invalidated when an upstream identity or hash
changes. `run_static_phase1_calibration_rehearsal` covers all 15 artifacts,
the complete 12-artifact closure for each device, 27 parent-artifact edges, and
41 context-source edges. The settings and intrinsics artifacts bind the retained
camera/support/light/cable stack directly. It constructs only in-memory
`NOMINAL_ONLY` artifacts,
reads but never writes the physical registry, and intentionally reports the 15
physical artifacts missing.

The implemented optional Phase-2 offline eye-on-arm commands stop before that
acceptance boundary. The solver consumes a strict, precommitted train/held-out dataset and
can produce only a diagnostic `NOMINAL_ONLY` candidate. The FK verifier
recomputes stored carrier poses from content-hashed decoded T=1051 fields,
explicit joint-reference rules, the supplied `link2_T_E`, and the reviewed
pinned URDF. The capture-bundle verifier then binds the exact raw T=1051 lines,
JPEG bytes, normalized detection bytes, and pre/exposure/post host brackets to
the same exact-file-pinned dataset/evidence pair and verified active context.

That capture pass is structural only. T=1051 carries no device measurement
timestamp, clock-correlation payloads and camera/artifact identities are not
independently registry-resolved, and its existing
`NormalizedDetectionEvidence` still does not preserve the original tag
corners, inliers, covariance, or detector logs. The typed vision schemas and
fixed-overview detector/pose implementation do not retroactively change that
bundle and are not yet emitted or consumed by the capture verifier.
Physical-camera adaptation and qualification, a measured target-fixture chain,
and an independent physical-validation/promotion boundary are still missing.
These are physical commissioning blockers, not optional report warnings.

## Implemented simulation acceptance

A `simulate` run is a required-simulation pass only when:

1. all cross-source placemat alignment checks pass;
2. all generated coarse geometric checks pass; and
3. all tags are visible in the fixed synthetic overview fixture.

Numerical IK is deliberately diagnostic while `B_T_Wv` and the route TCP are
nominal. A report can therefore say the required checks passed while also
reporting provisional IK gaps. That is a prompt to improve the model or
placement, never permission to move the arm.

The current exhaustive contact screen with the nominal -100 mm virtual tool
accepts 6/46 keyboard targets (`A`, `C`, `SPACE`, `TAB`, `X`, and `Z`) and
29/29 phone targets. Across all four tools and phases, 625/1,200 target poses
solve. The required `(305, 400, 70)` park pose converges only for the
no-extension `hand_tcp_only` case, at zero effective joint margin; all three
contact-tool lengths reject it. The keyboard and park results reject the present
assumed base/tool/layout combination as a typing solution. The phone result is only an
IK seed check: it does not cover measured screen targets, error margins,
optional Phase-2 eye-on-arm visibility, collision sweeps, touch activation, or
UI outcomes.

The corrected bounded placement study then compared 18 clamp/yaw/tool
hypotheses and fully evaluated two finalists. Its best balanced finalist used a
rear clamp contact/base-axis X of 385 mm, zero unmeasured X/Y offsets, base-link
Z 70.1 mm, yaw -82 degrees, and 100 mm tools. It accepted 20/46 keyboard and
18/29 phone contacts, but 0/2 required route parks; its worst accepted-pose arm
margin was only 0.0100156 against the 0.01 diagnostic floor. Status therefore
remains `CONTACT_AND_PARK_DIAGNOSTIC_NO_COMPLETE_FINALIST`; the final report
hash is intentionally omitted until the source-hardening verification rerun.
See [the study contract](REACH_LAYOUT_STUDY.md). This rejects the current
bounded hypotheses, not the physical arm; clamp-axis metrology, mechanically
justified route/park planning, collision, and perturbation testing remain
necessary.

The follow-on bounded park optimizer found board-frame point
`(290, 10, 70) mm`. Both 100 mm tools pass its independent IK screen with
`0.2704734350` worst normalized arm margin and 10 mm minimum modeled planar
point clearance. This is a simulation overlay only: it does not modify the
placemat or prove a route/full-body clearance. See
[the park-pose contract](PARK_OPTIMIZATION.md).

With `--use-optimized-park`, the keyboard `"a"` route now accepts 24/24
waypoints and reports
`DISCRETE_SEQUENTIAL_IK_WAYPOINT_DIAGNOSTIC_PASS_WITH_UNSUPPORTED_CHECKS`.
The phone `"a"` route stops at `APPROACH` because its normalized arm margin is
`0.000657824`, below `0.01`; both reach finalists also reject phone `key_a`
contact. Trajectory schema v2 additionally fail-closes on numerical rank loss
in the solver's weighted five-constraint task Jacobian while leaving normalized
conditioning report-only. It does not evaluate full six-dimensional physical
singularity/manipulability or any full-link/camera/cable collision. The current
base/tool/layout hypothesis therefore remains infeasible for the complete
mission. See [the trajectory contract](TRAJECTORY_SIMULATION.md).

The broader pre-hardware service now makes that conclusion quantitative without
changing the freeze. It screens 243 coarse sensitivity hypotheses, 34 bounded
refinements, and the top eight of 49 regression passes against the complete
contact catalog; 41 regression passes are explicitly omitted from the expensive
full-catalog stage. Six shortlisted candidates meet the promotion gate. Promoted
rank 1 (`reach-944d7463f4c67905`) is an unmeasured sensitivity overlay at
clamp/base X 385 mm, rear-axis Y 75 mm, yaw -105 degrees, 120 mm keyboard tool,
and 100 mm phone tool. It is not an installation or fabrication prescription.

The independent mission service then reports the frozen baseline at 38/75
accepted routes (keyboard 20/46, phone 18/29), while promoted rank 1 accepts
75/75 sampled single-target routes. Each route begins and ends at the same
nominal Cartesian park coordinate and carries no joint state into another
route. The pass therefore demonstrates coverage inside the declared sensitivity
envelope; it does not prove arbitrary multi-key sequences, physical dimensions,
collision clearance, dynamics, optional Phase-2 arm-camera performance,
contact, or outcomes.
See the [pre-hardware mission coverage contract](PREHARDWARE_MISSION_COVERAGE.md).

## Virtual commissioning checkpoint

The next software layer is now assembled around a sixth bundle artifact,
`virtual_commissioning_profile.json`. It preserves rank-1
`reach-944d7463f4c67905` and park `(290, 10, 70)` mm as an explicitly
unmeasured overlay. Startup validates the complete workcell before the session
can compile or plan.

The canonical trajectory output now retains each original physical action
index on every densified Cartesian waypoint and joint result. At a
`phase_endpoint` contact, the executor uses the accepted IK result's achieved
board-frame tool-tip position and opposite hand-TCP +Z axis to construct the
contact point and normal, then supplies only that geometry, a fixed virtual
dwell, activation count, and action index to the device. The device resolves
its immutable polygon/depth/normal/dwell/focus/UI model to `ContactResult`; it
does not receive the planned target or expected character. Repeated target
names therefore remain separate occurrences without deciding their own
output.

A distinct `VirtualTextOutcomeObserver` receives only `ContactResult` objects,
rejects duplicate or out-of-order consumption, and derives the redacted output
hash and length. The legacy virtual session executes 48 keyboard and 61 Android
waypoint moves and checks the phone's initial `KEYBOARD_LOWER` state. Both
geometry-resolved virtual outputs match by SHA-256 and length, return to the
locked park, close the plant, and produce zero hardware commands. This still
does not demonstrate physical feedback, contact mechanics, OS/ADB output, or
independence from the same synthetic region/output definitions.

Virtual calibration rows close the software dependency graph with named
software-model substitutes while retaining every same-named physical artifact
as a blocker. Declarative one-use faults exercise connection, observation,
contact, focus, and UI-state failures with no retry. Split run artifacts are
written under an atomic, manifest-last package. The vision artifact binds
redacted frame provenance, typed detections/pose, synthetic quality, freshness,
and post-processing action association without storing JPEG bytes. Replay
verifies exact bytes and recomputes every artifact rather than trusting status.
See [virtual commissioning](VIRTUAL_COMMISSIONING.md) for the operational
contract and limitations.

The additive V2 rehearsal uses the same accepted Cartesian/joint trajectory but
treats its initial park as a checked condition rather than a command. Keyboard
`test` therefore contains 48 route waypoints, 47 non-wire commands, and four
simulated contact occurrences; Android `test.` contains 61 route waypoints, 60 commands,
and five contacts. Android's state observation owns no contact, route command,
authorization entry, or journal. Every contact is bound to a fresh synthetic
B0477 report at its final hover and every command is bound to its endpoint and
incoming midpoint collision results. V2 commits the durable contact boundary
before the contact-producing emulator call and refuses automatic restart once
that journal state is no longer `INTENT_COMMITTED`.

The hardware-neutral `runtime_ports.py` protocols and complete-bundle validator
remain the intended replaceable seam for a later physical architecture. The
legacy virtual executor does not run through that seam, while V2 runs directly
through the non-wire T104-shaped emulator. The fixed-overview renderer,
detector, and pose estimator continue to feed the legacy schema-v3 evidence and
replay path separately. Neither direct virtual integration substitutes for a
commissioned runtime-port implementation or physical adapter.

## Physical execution architecture still missing

The eventual physical chain must add all of the following before any contact
workflow can be enabled:

```text
qualified hardware identities and serial ownership
    -> measured intrinsics/tag map/robot reference
    -> qualified pixel decoder, AprilTag detector, typed detection/pose records
    -> static Wv_T_C_overhead_optical and live C_overhead_optical_T_B
    -> independent held-out B_T_Wv validation and support/base witness
    -> R_ctrl correlation and bounded controller-model residuals
    -> measured device targets and route TCP/compliance
    -> full-link/self/gantry/camera/lighting/cable/fixture collision checking
    -> live E-stop, containment, anti-shift, contact, and freshness interlocks
    -> expiring single-use motion permit
    -> shared orchestrator over validated runtime ports
    -> bounded physical executor with deadlines/cancellation and no blind retry
    -> measured contact feedback and local contact guard
    -> independent keyboard/OS or Android/ADB outcome observer
    -> immutable run evidence and explicit recovery
```

The record types and structural port protocols mentioned in that chain exist;
their physical implementations and integration do not. None of the chain is
currently an operator command. See
[`KEYBOARD_RUNBOOK.md`](KEYBOARD_RUNBOOK.md) and
[`ANDROID_RUNBOOK.md`](ANDROID_RUNBOOK.md) for the current hardware-free
workflows and the commissioning handoff criteria.
