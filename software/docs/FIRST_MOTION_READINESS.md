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

## Global prerequisites

All stages require these items. None is satisfied by the simulation program.

- [ ] The exact installed arm, base clamp, work surface, keyboard/phone fixtures,
  selected contact tool, moving cables, and static camera are measured and
  hash-bound in an accepted installed collision profile.
- [ ] Intended adjacent-link and rigid-attachment contacts have engineering
  review; every allowed collision exclusion has a written rationale.
- [ ] Controller protocol, servo identity, unit, sign, zero convention, joint
  limits, and feedback semantics are confirmed against the received controller.
- [ ] Servo repeatability, backlash, settling, telemetry latency, encoder
  behavior, overload reporting, and power-loss behavior are measured.
- [ ] An independently calibrated observation can detect tool-tip/link-pose
  disagreement before contact. This closes the 33 Phase 4 geometry and joint-zero
  gaps.
- [ ] Workcell clearance, energy isolation, emergency stop, speed/torque limits,
  and the deterministic stage script have a human preflight review.
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

**Current state: BLOCKED ON SIMULATION AND PHYSICAL MEASUREMENT.**

Required simulation evidence:

- [x] Strict T102 runtime framing and measured-position plant rehearsal:
  canonical receipt `94e67a752045f9a8a99483cf763a6fe8cec4c2aa6fd219584bd1246a751c3aa2`.
- [x] Exploratory 33-sample predicted joint/tool-tip envelope prepared from 28
  range cases in Phase 3.
- [ ] Collision-clear Stage A corridor. Phase 3 currently stops at
  `COLLISION_DIAGNOSTIC_CLEAR`.
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

**Current state: BLOCKED BY STAGE A AND PHYSICAL PARK IDENTITY.**

Required simulation evidence:

- [ ] Accepted Stage A result from the same configuration epoch.
- [ ] Numeric Stage B envelope. The current artifact is
  `BLOCKED_NO_NUMERIC_ENVELOPE`.
- [ ] Collision-clear route to the parked pose.

Required physical evidence:

- [ ] Commissioned parked-pose joint and independent visual identity.
- [ ] Measured multi-joint timing, settling, repeatability, and approach
  direction.
- [ ] Verified arm silhouette and fixture clearance at park.

Abort on any common no-go, unexpected joint coupling, or park identity mismatch.
Jack must explicitly approve Stage B after Stage A completes and the park identity
is commissioned.

## Stage C — hover above the keyboard with no contact

**Current state: BLOCKED BY STAGES A-B, COLLISION, AND CALIBRATION.**

Required simulation evidence:

- [ ] Accepted Stages A-B from the same configuration epoch.
- [ ] Numeric Stage C envelope across the frozen `5-30 mm` exploratory hover
  range.
- [ ] Collision-clear path and hover pose with the selected tool and cable route.
- [ ] Qualified fixture relocalization and tool/link-pose mismatch detection.

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

**Current state: BLOCKED BY STAGES A-C, WS2, AND CONTACT MEASUREMENTS.**

Required simulation evidence:

- [ ] Accepted Stages A-C from the same configuration epoch.
- [ ] WS2 key-press physics result selecting a provisional tool and a press
  recipe envelope. WS2 GPU execution is still queued.
- [ ] Regenerated collision candidate and route using the WS2-selected tool.
- [ ] Numeric Stage D telemetry, landing, contact, dwell, and retract envelope.

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

**Current state: BLOCKED BY STAGES A-D, TARGET COMMISSIONING, AND VERIFICATION.**

Required simulation evidence:

- [x] Semantic compiler and device-state replay cover single characters,
  modifiers, and fail-closed unsupported targets.
- [ ] Accepted Stages A-D and a zero-false-acceptance scenario regression.
- [ ] Numeric Stage E approach, press, retract, and verification envelope.

Required physical evidence:

- [ ] Commissioned key target, safe region, landing correction, reach, and
  collision clearance.
- [ ] Sticky Keys configuration and shortcut settings verified for the host.
- [ ] Independent host event log and fresh postpress observation.

Abort on any common no-go, wrong/missing/repeated key event, modifier-state
disagreement, or verification mismatch. Jack must explicitly approve Stage E
after one-pad contact evidence is accepted.

## Stage F — type a short string

**Current state: BLOCKED BY STAGES A-E AND RECOVERY QUALIFICATION.**

Required simulation evidence:

- [x] Exact semantic replay includes `Hello 2026!`, repeated keys, and every
  Shift transition under the candidate catalog.
- [x] WS4 defines stop, re-observe, relocalize, backspace-correct, or abort paths.
- [ ] Accepted Stages A-E and a zero-false-acceptance scenario regression.
- [ ] Numeric multi-key Stage F telemetry and verification envelope.

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

The closest stage, A, has a strict-runtime prediction envelope but no accepted
collision-clear corridor and no measured physical plant bounds. The scenario
regression also retains 33 geometry/zero false acceptances. No stage may advance
from this document alone.
