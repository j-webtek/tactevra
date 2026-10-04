# Model-to-arm translation assurance

**Status:** governing AI integration process, 2026-09-25
**Applies to:** every worker changing intent models, vision models, target
resolution, trajectory planning, safety admission, controller encoding, or
outcome verification

## Decision

The model emits a semantic task proposal and scene classifications. It does
not emit executable arm commands. Deterministic, versioned RoCell components
translate an accepted semantic task into named targets, calibrated board-frame
coordinates, collision-screened joint trajectories, and finally controller
protocol messages.

This separation is the project definition of correct model-to-arm translation:

```text
user request
  -> grounded model/intent result
  -> RoCell semantic ActionPlan
  -> named device targets
  -> same-frame visual target observations
  -> calibrated board/tool coordinates
  -> inverse kinematics and full-route screening
  -> safety admission bound to exact hashes and epochs
  -> controller command encoding
  -> transmitted-command receipt and fresh feedback
  -> independent keyboard/phone outcome observation
```

A stage may accept, reject, or return uncertainty. Missing evidence always
stops progression. No later stage may reconstruct or assume a value rejected
or omitted by an earlier stage.

## Ownership by stage

| Stage | Accepted input | Output owner | Required result |
| --- | --- | --- | --- |
| Intent grounding | User text and fresh observation reference | AI adapter plus grounding policy | Operation, one device, exact literal payload, or explicit clarification/rejection |
| Semantic compilation | Grounded proposal | RoCell keyboard/phone compiler | `rocell.action_plan.v1` with named actions and a plan hash |
| Scene assessment | Exact image bytes | Local multimodal observer plus deterministic quality checks | Device/layout/state/visibility classifications bound to frame and image hashes |
| Self-occlusion assessment | Fresh measured joint state, commissioned camera/board calibration, and pinned official visual meshes | Deterministic projection service | Conservative robot silhouette and target safe-region overlap bound to telemetry, calibration, frame, and geometry hashes |
| Target localization | Same image and active target catalog | Precision perception and deterministic target resolver | Named targets in board millimetres with source, confidence, and error evidence |
| Calibration | Immutable configuration epoch | Calibration registry | Camera, board, base, device, and tool transforms with validation evidence |
| Planning | Named calibrated targets and fresh telemetry | Deterministic IK/trajectory planner | Ordered hover, approach, contact, retract, and clearance samples |
| Admission | Exact observation, calibration, plan, trajectory, and policy hashes | Safety supervisor | Rejection or a short-lived, single-use permit |
| Encoding and write | Unexpired permit and exact admitted trajectory | One verified execution adapter | Exact controller bytes/JSON and a correlated receipt |
| Verification | Fresh controller feedback and post-action image/device state | Independent outcome verifier | Observed success, observed failure, or uncertainty |

## Model output boundary

Permitted learned outputs:

- `type_text`, `clarify`, or `unsupported` intent decisions;
- keyboard or phone identity and visible state;
- image quality, obstruction, and target visibility classifications;
- a named target plus bounded device-local or board-coordinate hypothesis under
  `rocell.model_motion_proposal.v1`;
- other bounded perception hypotheses that deterministic geometry validates.

Coordinate hypotheses never become arm coordinates by themselves. The motion
bridge must verify the named target, frame, surface plane, safe region,
confidence, image provenance, and catalog identity before calibrated planning.

Robot self-occlusion is geometry first. The deterministic projection service
projects pinned official visual meshes from measured joint feedback synchronized
to the image exposure through the commissioned camera model. Commanded joint
positions and the latest value received after exposure are not substitutes for
measured feedback at capture time. The frame binds the exposure timestamp,
clock identity, feedback samples bracketing exposure, and the qualified
interpolation method; a missing bracket, excessive sample gap, unsynchronized
clock, or feedback without measured-position provenance requires abstention.
The service evaluates the requested target's safe-region overlap under the
installed joint and extrinsic uncertainty envelope. Its mask is a perception
artifact only: it provides no collision-clear claim, trajectory, permit, or
execution authority. A learned obstruction detector covers residual conditions
absent from the robot model, including cables, hands, glare, and unexpected
objects. Conservative OR fusion abstains when either source says abstain or
when either source is stale, unqualified, or unavailable.

Projection dilation is calibrated rather than selected as a convenient pixel
constant. The installed bound propagates ChArUco reprojection residuals,
measured joint-feedback resolution and noise, and observed directional backlash
and parked-pose repeatability through the same mesh projection. Qualification
freezes the conservative image-space quantile or bound, its source artifacts,
and its applicable camera and robot domain. A guessed dilation cannot qualify
the projection.

Simulator ground-truth masks may provide labels and scoring references. They
must not be supplied as model features or represented as runtime masks. Model
inputs that represent the predicted robot silhouette must be generated from
telemetry and calibration estimates, with predeclared perturbations of joint
state, intrinsics, distortion, and extrinsics. This keeps synthetic training
aligned with the uncertainty present at runtime.

Forbidden learned outputs:

- servo counts, joint angles, PWM values, speed or dwell parameters;
- controller JSON, serial bytes, network commands, or transport selection;
- execution permits, collision-clear claims, calibration identities, or
  success claims;
- automatic retries or corrections after failure or uncertainty.

If a model response contains a forbidden field, unknown field, invalid enum,
nonfinite number, changed text payload, or unbound coordinate, validation must
reject the complete response.

## Functional translation invariants

Every implementation and test must preserve these invariants:

1. **Literal intent:** the compiled text exactly matches the user-grounded
   payload. Its hash and action sequence are reproducible.
2. **Named-target continuity:** each semantic action resolves to the intended
   key or phone region. The model cannot replace a requested target.
3. **Frame continuity:** scene classification and target coordinates bind to
   the same frame ID and exact image SHA-256.
4. **Coordinate continuity:** pixels, board millimetres, arm-base coordinates,
   tool-tip coordinates, joint space, and controller units remain distinct and
   are connected only by active calibrated transforms.
5. **Configuration continuity:** camera, board, base, device, tool, arm,
   controller, software, and power epochs cannot change during an attempt.
6. **Trajectory continuity:** admission covers the complete ordered route,
   including hover, approach, contact, retract, transitions, and cable/body
   clearance. Endpoint reachability alone is insufficient.
7. **Command continuity:** encoded commands are derived from the exact admitted
   trajectory. The receipt records requested, encoded, transmitted,
   acknowledged, and measured values separately.
8. **Outcome independence:** command acceptance and servo arrival do not prove
   a key press or screen action. A fresh independent observation determines the
   outcome.
9. **Fail-closed uncertainty:** stale data, missing coordinates, weak
   confidence, obstruction, calibration gaps, collisions, transport faults,
   or ambiguous outcomes create no write and no retry.
10. **One writer:** AI, perception, dashboards, evaluators, and shadow tools
    cannot instantiate a writable arm transport.

## Required worker verification

Before merging a change that affects translation, the worker must provide a
trace covering every affected boundary:

1. user request and expected literal payload;
2. grounded proposal and rejection behavior for ambiguous variants;
3. compiler-produced semantic actions and plan hash;
4. frame, image, scene-observation, target-catalog, and precision-observation
   hashes;
5. calibration snapshot and complete configuration epoch vector;
6. named target through every coordinate frame with units;
7. route samples, selected IK branch, limits, continuity, and collision report;
8. safety decision and reason codes;
9. exact encoded command compared with the admitted trajectory;
10. receipt fields for sent data, acknowledgement, goal/readback, and outcome;
11. explicit counts for hardware writes, permits, retries, and commands.

For the first physical milestone, the default observation protocol retracts to
a commissioned parked pose, waits for the configured settling interval, and
then captures a fresh frame. Planning and contact use that frame for one action
only. After the action, the system retracts and obtains new evidence. Keyboard
host event logging and development-mode phone ADB state may provide independent
outcome observations when available; neither source authorizes a movement or
replaces fresh perception and arm-runtime admission.

The parked-pose milestone has its own narrow qualification set. Synthetic data
must vary measured calibration and lighting envelopes around the exact park
state. Physical data must contain at least 30 independently completed park and
settle cycles across at least three capture sessions, recording measured pose
repeatability, ChArUco drift, residual tool/cable obstruction, and every fusion
decision. It must have no accepted known self-occlusion and must abstain for
every labeled residual obstruction; exact binomial confidence bounds and all
false stops are reported. This is evidence for a supervised, parked-observation
milestone only. It does not satisfy the broad-pose statistical gate or qualify
mid-motion observation, unattended deployment, or physical authority.

Shadow and simulation work must report all four counts as zero. A physical
test must bind each nonzero count to an approved permit and reviewed receipt.

The current machine-checkable implementation is
[`translation_assurance.py`](../rocell_ai/translation_assurance.py), with its
versioned [JSON schema](../schemas/translation_assurance_v0.schema.json). Run
`python software/ai/run_offline.py assure-shadow --shadow shadow.json` to
validate stage ordering and produce a hash-bound assurance record. In v0,
exactly one stage blocks progression and all later stages must be `not_run`.

Model coordinate proposals use the companion
[`motion_assurance.py`](../rocell_ai/motion_assurance.py) bundle. Run
`python software/ai/run_offline.py assure-motion-proposal --proposal proposal.json`
to validate proposal structure, named-target agreement, coordinate-frame
conversion, candidate hashing, the physical-calibration blocker, and zero
downstream effects.

## Minimum test matrix

Each supported keyboard or phone capability needs tests for:

- one successful semantic mapping per supported character or target class;
- repeated characters and order-sensitive strings;
- unsupported characters, unknown device state, ambiguous text, and extra
  requested operations;
- stale image/telemetry, altered hashes, mismatched frames, and changed epochs;
- absent device, wrong layout, darkness, blur, glare, and arm/tool/cable
  obstruction;
- missing target, wrong-target substitution, low confidence, and coordinates
  outside the calibrated envelope;
- unreachable IK, joint-limit margin, discontinuity, collision, and incomplete
  route geometry;
- expired/reused permit, altered trajectory, encoding mismatch, partial write,
  disconnect, and controller restart;
- sent command with no observed effect, wrong observed effect, and ambiguous
  post-action state.

Tests must assert the specific rejection reason and confirm zero writes for
every rejected case. Held-out physical evaluation remains separate from
synthetic and agent-authored evaluation.

## Current implementation status

The repository currently implements grounded intent, semantic compilation,
hash-bound scene observations, a synthetic precision-coordinate contract,
fail-closed vision fusion, replayable zero-write shadow previews, and a strict
`rocell.model_motion_proposal.v1` bridge for bounded coordinate hypotheses.
That bridge checks the named target, coordinate frame, target envelope, plane,
confidence, and provenance; transforms approved device-local coordinates into
the board frame; and deliberately emits no controller command or physical
authority. The
provisional offline Gemma 3 4B observer supplies scene classifications. The
real-photo shadow example stops at `precision_observation_missing` because no
calibrated real-image coordinate observation exists.

The coordinate bridge now feeds a separate zero-write planner-admission gate.
That gate binds the candidate to the build snapshot, target catalog, kinematic
model, arm-frame contract, configuration-epoch policy, and device calibration
graph. With the current empty physical registry it reports explicit missing
calibrations and performs no IK, route screening, command encoding, or hardware
access.

When the graph becomes valid, the strict planner calibration decoder additionally
requires exact, hash-matched measured payloads for the installed robot reference,
`B_T_Wv`, separate `R_ctrl` correlation, device pose, and `G_T_T`. The model target
is then reprojected through measured device placement. The next route boundary
requires a fresh observed starting joint state, performs deterministic densified IK
and sampled joint-continuity checks, and remains blocked on incomplete full-body,
tool, and cable collision geometry. None of these artifacts carries authority.

The trajectory screener can now consume the strict installed measured-collision
profile rather than silently reverting to nominal readiness. It rechecks the
profile's manifest, build snapshot, robot model, and base-contract lineage and
records the installed profile, contract, and clearance-policy hashes in a v2
report. A complete installed profile removes only the
`FULL_COLLISION_GEOMETRY_INCOMPLETE` blocker. The report deliberately replaces
it with `CONTINUOUS_FULL_BODY_COLLISION_SWEEP_NOT_IMPLEMENTED`; no collision
clearance, envelope, command, or physical authority is inferred merely from
loading measured body envelopes.

A separate measured-waypoint collision boundary now binds that v2 trajectory
report and installed profile to exactly one collision pose per accepted planner
waypoint. Each pose must carry exact rigid-frame transforms and explicit
configuration-correlated geometry for every deformable body, including the
moving cable. The existing broad/narrow-phase kernel evaluates every supplied
full-body sample under the installed clearance policy; missing samples,
crossed hashes, collisions, and incomplete pose bindings fail closed. A clear
sequence is reported only as
`DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED`. It never promotes
sampled clearance into continuous clearance, commands, or physical authority.
The FK adapter now independently recomputes robot-link transforms from each
exact bound IK result using the hash-pinned URDF and measured `B_T_Wv`.
Callers cannot override those frames. Non-URDF rigid attachments are expressed
as measured fixed transforms from named URDF links, while every deformable
sample and attachment transform must carry a source digest already present in
the installed collision profile. The remaining collision gap is conservative
inter-waypoint rigid-body and cable coverage; clear waypoint samples still do
not prove the space between them.

The bounded-segment qualifier now subdivides every accepted joint-space segment
from the fresh observed start through each IK endpoint under an explicit maximum
joint-step policy. It recomputes FK through the trusted adapter at every
generated sample and requires exact, hash-bound configuration geometry for the
moving cable at each one. Sample omissions, crossed sample identities, malformed
start/end states, and resource-cap exhaustion reject. A clear result is only
`BOUNDED_SEGMENT_SAMPLES_CLEAR_CONSERVATIVE_SWEEP_REQUIRED`: finite sampling
reduces an evidence gap but does not prove the swept volume between samples.
No commands, hardware access, or physical authority are created.

The next conservative-sweep boundary encloses each rigid primitive over every
adjacent bounded sample pair. Its displacement margin is derived from the pinned
URDF serial-chain path radius and the exact ancestor-joint deltas; deformable
cable motion must instead arrive as a measured root-frame envelope bound to both
sample hashes and a source already installed in the collision profile. These
envelopes are evaluated under the installed clearance policy. Intersections,
missing envelopes, crossed endpoints, unsupported prismatic arm joints, and
unbound sources reject. Diagnostic-only global pair exclusions still prevent a
continuous-proof claim, and clear envelopes retain contact-policy and installed
physical-qualification blockers. No transport or execution authority is added.

The phase-local contact envelope gate now closes the next software seam without
weakening collision semantics. It verifies the conservative-sweep content hash,
the exact trajectory/profile lineage, accepted-engineering status for every
global exclusion, and the sealed v2 proposal/envelope identity. A contact
proposal must bind exactly one `CONTACT` waypoint to the proposal target and an
installed `TOOL`/device-body pair; a hover proposal may carry neither a contact
waypoint nor an allowance. The resulting artifact contains no controller or wire
commands, explicitly denies physical/contact authority, and continues to require
installed physical qualification.

The next command-management boundary is now explicit and remains fail closed.
`single_action_execution_review_v1` joins one indexed v2 proposal with its
sealed trajectory, phase-local collision/contact gate, independently reviewed
installed collision-policy evidence, and the existing installed-controller
qualification evidence/report. Controller session and configuration epoch must
match the trajectory exactly. The review expires, can be cancelled, and is
atomically consumable only once, including under concurrent callers. Its
consumption receipt still says `permit_issued: false` and contains no controller
or wire commands: only the safety supervisor may later mint physical authority.

The ARM-047 bridge now performs that handoff without bypassing the existing
authority. Device/interaction semantics determine the only acceptable safety
capability; the consumed review digest becomes the plan identity; and the
supervisor rechecks fresh calibration, interlocks, runtime status, operator
arming, build release, and safety state before issuing exact-goal authority.
Hash-chained lifecycle acknowledgements distinguish accepted, started,
completed, failed, and uncertain outcomes. Failure and uncertainty are terminal
and never imply retry or follow-on movement. Native writer and feedback binding
remain separate work.

ARM-048 now replaces the caller-authored `STARTED` acknowledgement with a
content-addressed dispatch receipt.  The hardware-incapable sole-writer
rehearsal consumes the exact supervisor permit immediately before one encoded
write attempt, records payload identity and confirmed byte count, and evaluates
ordered post-dispatch T=1051 samples against explicit arrival and settling
tolerances.  Zero writes fail; partial or completion-uncertain writes and stale,
missing, malformed, or unsettled feedback terminate as `UNCERTAIN`.  No path
retries or authorizes follow-on movement.  This qualifies the execution
semantics only: the implementation has no serial factory, port, callback,
socket, or device handle and therefore claims neither an authentic controller
receipt nor independent task outcome.

The S4 synthetic integration lane now proves the downstream identity plumbing
without relaxing that physical gate. A typed assessor requires the exact
synthetic r97 review decision and eight-component configuration epoch, the model
batch and indexed proposal, a sealed trajectory carrying that epoch digest, the
matching Waveshare profile, and its transport-free preview receipt. The
rehearsal succeeds only when the production epoch still reports
`FIRMWARE_REVIEW_DECISION_BLOCKED` and `COMPONENT_NOT_PHYSICAL_ORIGINAL`.
Consequently it can catch crossed model, epoch, trajectory, profile, or receipt
identities while remaining unusable as a dispatch permit.

The shared seam now also consumes the exact canonical bytes produced by the
real `rocell_ai.batch_emitter_v2` assembler. Those bytes are decoded by the arm
model, admitted through the registry, checked for freshness, and submitted to
the measured planner without substituting a hand-authored batch. The measured
planner correctly stops at `BLOCKED_CALIBRATION_MISSING_OR_STALE` and requests
`COMMISSION_REQUIRED_CALIBRATIONS`. Only after recording that independent
blocker does a separate synthetic planner-ready copy exercise the sealed
trajectory and zero-write encoder path. This proves producer/consumer wire and
lineage compatibility; it does not qualify the synthetic observation fixture,
the current learned models, a physical route, or controller execution.

The following are still required before functional arm-command qualification:

- fixed-camera real-image target labels and held-out evaluation;
- commissioned camera/board/base/device/tool calibration;
- precision confidence and error thresholds derived from physical data;
- complete full-body, tool, cable, and environment route screening;
- an execution adapter that consumes only a valid single-use permit;
- independent observation of the resulting key or phone action.

## Worker workflow

1. Read this document, the [AI contract](CONTRACT.md), and the
   [shadow execution plan](../../docs/AI_SHADOW_EXECUTION_IMPLEMENTATION_PLAN.md).
2. Identify the stage owned by the change and list its input/output contracts.
3. Implement the smallest change without crossing ownership boundaries.
4. Add positive, rejection, tamper, stale-data, and zero-write tests.
5. Run the AI suite and the relevant RoCell unit/integration suites.
6. Save a hash-bound shadow record and document remaining assumptions.
7. Update the status documentation without describing simulated evidence as
   physical evidence.

No worker may promote a learned output directly into controller space. New
capabilities extend semantic profiles, target catalogs, calibration evidence,
planning, admission, encoding, and verification in that order.

## Coordinate simulation evidence

The `simulate-motion-proposal` command produces a separate nominal rehearsal
report for a keyboard contact proposal. It checks geometry, sampled IK, and a
dense route without granting physical authority. The original physical assurance
trace still stops at missing calibration. The initial H fixture fails at the
nominal PARK waypoint; workers must preserve this result when studying improved
layout assumptions. See [the motion contract](MODEL_MOTION_PROPOSAL.md).
