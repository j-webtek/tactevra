# First-motion readiness checklist

> **Status: SIMULATION RECORD ONLY — NO STAGE IS READY**
>
> This checklist records evidence and blockers. It creates no command, permit,
> transport capability, hardware write, physical movement, or physical
> authority. The first powered motion requires Jack's explicit approval after
> the applicable physical evidence is reviewed in a separate session.

## Evidence backbone

| Evidence | File SHA-256 | Canonical receipt SHA-256 | Current meaning |
|---|---|---|---|
| Phase 0 collision intake | `4cc5956e209c36001b9eb22739918e87cc1fbc8d063c9512dfab2813dca8a640` | `11bc5106c5b1b9e74be5b78300ba01bbacefecbb282f531aa46cb4b740075aae` | Exploratory candidate runs, but every complete case reports collision and exclusions are unreviewed. |
| Phase 2 controller emulator | `70ed11203d0fa0f603210815d01cf46d2200cc5667fe226e870a9da7b4ab2ef1` | `94e67a752045f9a8a99483cf763a6fe8cec4c2aa6fd219584bd1246a751c3aa2` | Exact strict-runtime framing passes against a synthetic measured-position plant. |
| Phase 3 staged rehearsal | `d94d3259aa5c852856346b421452f3b630c87e3facaf705679b3152c952d9d5e` | `7128ef369ec5de2194dcb928fc0fa46ca8fd182bf5b399fe0e9f66406ca7a352` | Stage A stops before simulated motion; B-F are upstream-blocked. |
| Phase 4 wrong-model drills | `36356eb981c694532033ddd22864738da7bba226a62cc1a001eb088faf85eb95` | `8b8d5341cf26fd5642c638b340353d53f863429ee3c661167f911c3d79e3d813` | 30/63 injections detected before contact; 33 geometry/zero cases remain gaps. |
| Phase 5 scenario regression | `4bc2d5e590db4acc908b49e2b5adf9c39e1929595a0923db634c45b58322906b` | `7ebd04c2da191971a623abee5715df231c937f764dfa575572f9977d26b42234` | CI 6/7 and nightly 51/84; 33 false acceptances remain visible. |
| Phase 7 independent-observer drill | `46a6610ae7842e7b68d5e38a9776800c358c8d0f3e91d9897fdac5b407bfe95d` | `b7e768d99bdd9da3c7db002629d29e0618498ef32a3f574282fe42b63a062448` | Under frozen synthetic ranges, 16/33 old gaps can be consequential and fused simulated observers leave zero consequential gaps undetected. No physical observer is qualified. |
| Phase 7 candidate A-F shadow | `d57688b29625cdb4409efe4604513a0709d923e5da5bd8cd8cbe2d835001a845` | `48d0f77011445be3e900d9323061248b6057789c2cbe9a3db3879dd58747c3e5` | A-F produce 198 predicted telemetry samples in a separate shadow path. Candidate collision remains `STOP`; the official Stage A stop is unchanged. |
| Phase 8 candidate collision attribution | `f8603f979cce8775658fa371ec768adcff9377a1879f2364b8bc7d75a38879c5` | `885667bd60df7ac8f4d27bab23d390a3dec30fa0e3997c18d33d3a9ddec20ce1` | Fourteen of 40 favorable-size route endpoints avoid consequential contacts on the 46 keyboard poses. Remaining consequential pairs are cable-related. A-D are unevaluated, and expected structural contacts remain unreviewed blockers. |
| Phase 9 staged collision design | `a46bb261afc6012233b3d90b222dbbebec6da749943d8a0ec588c33ab68736ed` | `3a67191eb9e19d3f3259c068047389cf4b21b58c3623ce81d0d355877c0ed73f` | Stage A clears its discrete screen. B-F stop under the frozen design ranges; C/D IK converges, isolating collision and route design as the blocker. Ten always-touching pairs are proposed only for human exclusion review; no exclusion is installed. |
| Phase 10 clearance waypoints and swappable pad | `645319b8b73222f398e9fe2734344fa3bef06cb24f479e9606238c289d4619b5` | `bf55993e846f8bacf22ab2b5ed5576f0bda54d331dcd6b00fa18ed9740189ae2` | Clearance waypoints make all 46 reference routes feasible from `halton-0573` and 45 from `halton-0258`; the former camera-first park remains 0/46. Robust B/C endpoint screens still stop. Cable-link4 is isolated to C descent. All 13 keyboard-replacement pad variants stop on early/adjacent contact and cable/workcell conflicts. |
| Phase 10 remedy audit | `5306615285e504afb2bb5c3e8fd7378eaac2c4ca902a851bb82c0cb522678306` | `cdb48413c1a4dc4cb2880d1e13700090812901e64121bd1563454a193023d1fd` | `halton-0573` clears all 80 targets across the frozen nadir family and retains 46/46 routes. Dynamic first-contact labeling is contiguous but both pad modes still stop. Fixed wrist pitch removes cable-link4 contact only by introducing 168-216 mm landing error; cable routing remains the remedy dependency. |
| Passive-tool first-motion rerun | `491420aa001477f3865dc944d2ab4371e514724bca3c38cba8db3b9b79d95c3d` | `d4c414ad25b64b80def169beaf195939202f2105fa652ef628edb5e5415781f9` | Under the selected passive stylus and static camera, A and the waypoint route to `halton-0573` clear every sample; the tray-replacement D result remains clear. C stops on 24/648 descent samples from tool contact with the keyboard/left station. E/F stop because coarse whole-keyboard/station geometry cannot admit target-specific contact. No cable finding remains. |
| Target/contact and station-CAD refinement | `24cfebe7141939a3011a63832abfb5937686f756b3c5ac4c00fb0dace9f7e15e` | `8c92b479f53b6048650d369b698a5676b10521d396c7030149353caf8ab7e1ad` | Controlled station CAD removes every old station collision. C retains distal-tip/own-key DESCEND boundary disagreements and four short-tool low-hover IK failures. E/F reveal that the existing target pose bundle is bound to the 120 mm tool and cannot validly score the 80 mm endpoint; length-specific IK remains required. |
| Converged first-motion rehearsal | `cc27d011101a62df2df5f0c0351f8db6770185cdbf29b70670b853b957620642` | `80a5d6ccb6af3555dc55f74473d5b8992b71bf6d056316a9559b6bb0e1f22041` | One configuration hash binds the 110 mm x 3 mm cable-free passive stylus, `halton-0573`, waypoint paths, station CAD, tray-replacement D mode, and all 51 E/F targets. A-F are satisfied in exploratory simulation; installed geometry, measured plant behavior, and physical observers remain blocked. |

The governing fixture is
[`first_motion_readiness_v1.json`](../ai/sim/evidence/first_motion_readiness_v1.json),
file SHA-256
`6bcfa546d39c5fb11b6231ee3fe79078fe5eaf34ff78e74bf7105d0005faf780`
and canonical fixture SHA-256
`50c7b0e6623f9a85168428aafe130982749ad30d85ef56a36257cfef35f3b167`.

The Phase 7 extension is governed by
[`first_motion_independent_observation_v1.json`](../ai/sim/evidence/first_motion_independent_observation_v1.json),
canonical fixture SHA-256
`638ebd2aa7837ade1090b506a702b569b9800e7b3fa444a7310bd30588261f5e`.
It does not revise the Phase 4 or Phase 5 failures. Its A-F rehearsal is a
shadow-coverage result using explicitly uninstalled candidate geometry.

## Procedure readiness

The documentation blockers are now addressed by
[`SAFETY_PROCEDURES.md`](SAFETY_PROCEDURES.md), the six
[`first_motion_sessions`](first_motion_sessions/README.md) scripts, and Session
0 in [`PHYSICAL_MEASUREMENT_PLAN.md`](PHYSICAL_MEASUREMENT_PLAN.md).

- [x] E-stop placement/function requirements and a pre-session test are written.
- [x] Workcell attendance, exclusion-zone, and per-stage table rules are written.
- [x] Conservative stage A-F speed and torque/current caps are written as upper
  fractions pending measured controller mapping.
- [x] Abort triggers, isolation actions, evidence retention, and no-retry rules
  are written.
- [x] A-F each have a setup checklist, exact CPU/emulator commands, envelope
  comparison, pass/no-go rules, logged evidence, and explicit approval record.
- [x] Approval scope and void conditions are written for Jack's future sign-off.
- [x] The power-off Session 0 measurement order and methods are written.
- [ ] The installed E-stop location, electrical isolation behavior, and test
  receipt are physically verified.
- [ ] Controller speed and torque/current mappings are measured and bound.
- [ ] Installed, single-action physical command packages are generated by the
  reviewed staging pipeline. The session documents intentionally contain none.
- [ ] Jack has signed the applicable one-attempt stage approval.

The checked items close documentation and procedure-definition blockers only.
They do not satisfy any physical measurement or approval row.

## Global prerequisites

All stages require these items. None is satisfied by the simulation program.

- [ ] The exact installed arm, base clamp, work surface, keyboard/phone fixtures,
  selected contact tool, fixed workcell cables, and static camera are measured
  and hash-bound in an accepted installed collision profile. A moving attachment
  cable is required only if an optional arm-mounted device is actually installed.
- [ ] Intended adjacent-link and rigid-attachment contacts have engineering
  review; every allowed collision exclusion has a written rationale.
- [ ] Controller protocol, servo identity, unit, sign, zero convention, joint
  limits, and feedback semantics are confirmed against the received controller.
- [ ] Servo repeatability, backlash, settling, telemetry latency, encoder
  behavior, overload reporting, and power-loss behavior are measured.
- [ ] An independently calibrated observation can detect tool-tip/link-pose
  disagreement before contact. This closes the 33 Phase 4 geometry and joint-zero
  gaps.
- [x] Workcell, E-stop, limit, abort, evidence, and deterministic stage-script
  requirements are documented for A-F.
- [ ] Their installed implementation and completed human preflight are verified.
- [ ] The applicable stage has Jack's explicit approval. Approval for one stage
  does not approve its successor.

## Common no-go and abort contract

Before any future stage, stop if evidence is missing, stale, hash-mismatched, or
belongs to another installation. During a future stage, abort on wrong direction,
magnitude outside the reviewed envelope, pose mismatch, any collision or limit
warning, stale/delayed telemetry, controller fault, connection uncertainty,
landing outside the reviewed envelope, wrong device event, or verification
disagreement.

The future human-run abort procedure is: stop issuing new work; do not retry the
controller write; activate the reviewed emergency-stop or power-isolation path;
keep hands outside the energized workspace; retain controller and observation
records; and return to physical preflight. Simulation does not test or authorize
that procedure.

## Stage A — one joint, small move, low speed

**Current state: SATISFIED IN THE CONVERGED SIMULATION; BLOCKED ON PHYSICAL MEASUREMENT AND OFFICIAL ACCEPTANCE.**

Required simulation evidence:

- [x] Strict T102 runtime framing and measured-position plant rehearsal:
  canonical receipt `94e67a752045f9a8a99483cf763a6fe8cec4c2aa6fd219584bd1246a751c3aa2`.
- [x] Exploratory 33-sample predicted joint/tool-tip envelope prepared from 28
  range cases in Phase 3.
- [x] Candidate passive-tool Stage A corridor clears all 264 frozen discrete
  samples. This is not an installed-geometry or continuous-clearance result.
- [x] The consolidated strict controller-emulator envelope is bound to the
  converged configuration and closes terminally without transport or retry.
- [x] The non-authorizing Stage A attended-session script is written.
- [ ] Phase 5 CI with zero false acceptance. Current result is 6/7.

Required physical evidence:

- [ ] Installed collision profile and reviewed exclusions.
- [ ] Fresh stable starting joint state and independent visual pose check.
- [ ] Measured one-joint direction, zero, allowable delta, speed, settling,
  telemetry freshness, and repeatability bounds.
- [ ] Verified emergency stop and energy-isolation procedure.

No-go criteria are the common criteria above plus any mismatch from the frozen
Stage A source joint, direction, delta, speed, or 33-sample envelope. Jack must
explicitly approve Stage A after reviewing the completed physical rows.

## Stage B — all joints to the parked pose

**Current state: SATISFIED IN THE CONVERGED SIMULATION; BLOCKED BY STAGE A AND PHYSICAL PARK IDENTITY.**

Required simulation evidence:

- [ ] Accepted Stage A result from the same configuration epoch.
- [x] Candidate numeric Stage B envelope: 324 discrete samples across every
  frozen tool endpoint and 60/100/140 mm transit height.
- [x] Candidate waypoint route to `halton-0573` clears 324/324 samples with no
  IK failure. Installed-geometry and physical park identity remain open.
- [x] The consolidated Stage B emulator envelope uses `halton-0573` under the
  same configuration hash as A and C-F.
- [x] The non-authorizing Stage B attended-session script is written.

Required physical evidence:

- [ ] Commissioned parked-pose joint and independent visual identity.
- [ ] Measured multi-joint timing, settling, repeatability, and approach
  direction.
- [ ] Verified arm silhouette and fixture clearance at park.

Abort on any common no-go, unexpected joint coupling, or park identity mismatch.
Jack must explicitly approve Stage B after Stage A completes and the park identity
is commissioned.

## Stage C — hover above the keyboard with no contact

**Current state: SATISFIED IN THE CONVERGED SIMULATION; BLOCKED BY STAGES A-B AND PHYSICAL CALIBRATION.**

Required simulation evidence:

- [ ] Accepted Stages A-B from the same configuration epoch.
- [x] Candidate numeric Stage C envelope covers 648 samples across the frozen
  `5-30 mm` hover range, four tool endpoints, and three transit heights.
- [x] The converged 110 mm x 3 mm configuration clears 102/102 continuous
  fixed-orientation GJK path rows across all 51 targets and both exposure
  profiles. Minimum key clearance is 27.0 mm; the bound real-station-CAD proof
  has zero station contacts. This remains candidate geometry.
- [ ] Qualified fixture relocalization and tool/link-pose mismatch detection.
- [x] The non-authorizing Stage C attended-session script is written.

Required physical evidence:

- [ ] Camera intrinsics and camera-to-board calibration in the exact runtime
  sensor mode.
- [ ] Installed keyboard pose, target catalog, selected tool geometry, and hover
  clearance.
- [ ] Independent confirmation that no tool, arm, cable, or fixture contact
  occurred.

Abort on any common no-go, fixture drift, or clearance loss. Jack must explicitly
approve Stage C after Stage B and the installed perception/collision evidence are
accepted.

## Stage D — single press on a test pad

**Current state: SATISFIED IN THE CONVERGED SIMULATION; BLOCKED BY STAGES A-C, WS2, AND CONTACT MEASUREMENTS.**

Required simulation evidence:

- [ ] Accepted Stages A-C from the same configuration epoch.
- [ ] WS2 key-press physics result selecting a provisional tool and a press
  recipe envelope. WS2 GPU execution is still queued.
- [ ] Regenerated collision candidate and route using the WS2-selected tool.
- [ ] Numeric Stage D telemetry, landing, contact, dwell, and retract envelope.
- [x] Candidate tray-replacement geometry clears all 22,464 discrete samples
  with 9,360 contiguous intended tool-pad contacts. It does not select the WS2
  press recipe or qualify physical contact.
- [x] The tray-replacement result and Stage D telemetry envelope are bound to
  the same converged configuration used by A-C and E-F.
- [x] The non-authorizing Stage D attended-session script is written.

Required physical evidence:

- [ ] Test-pad travel, actuation, force, bottom-out, neighbor-clearance, and
  repeat behavior.
- [ ] Selected fingertip dimensions and installed transform.
- [ ] Measured landing-observation noise and per-key correction residual.

Abort on any common no-go, unexpected contact, failure to actuate once, repeated
actuation, or landing outside the reviewed pad region. Jack must explicitly
approve this first contact stage after Stage C and all contact evidence are
accepted.

## Stage E — type one character

**Current state: SATISFIED IN THE CONVERGED SIMULATION; BLOCKED BY STAGES A-D, TARGET COMMISSIONING, AND VERIFICATION.**

Required simulation evidence:

- [x] Semantic compiler and device-state replay cover single characters,
  modifiers, and fail-closed unsupported targets.
- [ ] Accepted Stages A-D and a zero-false-acceptance scenario regression.
- [ ] Numeric Stage E approach, press, retract, and verification envelope.
- [x] The independently solved 110 mm pose family covers all 51 targets. All
  408 exact E/F rows pass own-target and neighbor-contact semantics; global
  minimum non-target clearance is 6.0 mm.
- [x] The non-authorizing Stage E attended-session script is written.

Required physical evidence:

- [ ] Commissioned key target, safe region, landing correction, reach, and
  collision clearance.
- [ ] Sticky Keys configuration and shortcut settings verified for the host.
- [ ] Independent host event log and fresh postpress observation.

Abort on any common no-go, wrong/missing/repeated key event, modifier-state
disagreement, or verification mismatch. Jack must explicitly approve Stage E
after one-pad contact evidence is accepted.

## Stage F — type a short string

**Current state: SATISFIED IN THE CONVERGED SIMULATION; BLOCKED BY STAGES A-E AND PHYSICAL RECOVERY QUALIFICATION.**

Required simulation evidence:

- [x] Exact semantic replay includes `Hello 2026!`, repeated keys, and every
  Shift transition under the candidate catalog.
- [x] WS4 defines stop, re-observe, relocalize, backspace-correct, or abort paths.
- [ ] Accepted Stages A-E and a zero-false-acceptance scenario regression.
- [ ] Numeric multi-key Stage F telemetry and verification envelope.
- [x] The Stage F emulator envelope and all 51 per-key contact identities share
  the converged configuration hash. The semantic replay evidence remains valid.
- [x] The non-authorizing Stage F attended-session script is written.

Required physical evidence:

- [ ] Per-character host event/readback agreement over a separately reviewed
  bounded string.
- [ ] Verified behavior for missed, wrong, and repeated key events without
  automatic controller-write retry.
- [ ] Fixture and reference validity throughout the string.

Abort on the first common no-go or text/readback disagreement. Preserve the
partial text and evidence; do not continue typing through an uncertain state.
Jack must explicitly approve Stage F after Stage E completes.

## Current decision

`NOT_READY_FOR_FIRST_POWERED_MOTION`

All A-F stages are now satisfied together in exploratory simulation under the
same configuration identity. The rehearsal covers the strict in-memory
controller path, 51-target continuous key clearance, tray-replacement contact,
per-key E/F semantics, six telemetry envelopes, and independent simulated
observers. This does not convert candidate geometry into an installed collision
profile or synthetic plant ranges into measured behavior. The physical rows,
the WS2 press recipe, emergency procedures, human approvals, and the existing
official scenario-regression requirements remain blocking. No stage may advance
from this document alone.
