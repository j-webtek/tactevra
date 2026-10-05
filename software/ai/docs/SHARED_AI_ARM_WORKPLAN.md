# Shared AI-to-arm workplan

**Status:** active coordination document  
**Owners:** AI/model workstream and arm/runtime workstream  
**Started:** 2026-09-26  
**Repository:** `j-webtek/tactevra`
**Current capability baseline:** protected `main` at `a8bf36f` through merged
PR #152 (physical-camera localization evaluator) and PR #151 (Torch 2.13 test
dependency update)
**Authority:** this document coordinates development; it grants no hardware authority

## Paused baseline and next test campaign

The final-camera dependency is now recorded as an explicit targeted hold in
[`CAMERA_INTEGRATION_HOLD.md`](../../../docs/CAMERA_INTEGRATION_HOLD.md). Work on
contracts, zero-write paths, deterministic runtime behavior, campaign tooling,
evidence, documentation, and distribution may continue. Real-camera
calibration, localization qualification, perception-driven hover, contact, and
typing claims remain deferred until the fixed camera installation satisfies the
documented resume conditions.

The software wire contract is ready, but operational readiness remains blocked
on qualified perception, retained camera/support evidence, a complete measured
configuration epoch, commissioned planner calibration, and installed runtime
qualification. The current synthetic precision candidate measured 0.9975
coverage at a declared 0.99 with a 14.400834977 mm conservative planar bound.
Because that disk crosses ordinary key safe regions, it is retained as research
evidence and is not installed for deployment.

When physical testing resumes, the highest-value sequence is:

1. Freeze the final camera mount, arm base, board, keyboard, tool, cables, and
   lighting as one measured configuration epoch.
2. Collect and owner-AI review the four ARM-070 camera/support originals.
3. Commission camera-to-board, board-to-robot, keyboard-to-board, and
   tool-to-joint transforms with repeatability observations.
4. Evaluate the merged precision adapter on disjoint final-camera calibration
   and held-out captures, including glare, blur, obstruction, and placement
   changes that remain inside the declared domain.
5. Run zero-movement shadow batches through ingress, planning, and rejection
   gates before any sparse noncontact hover grid.
6. Attempt one independently verified contact only after the combined error
   budget fits inside the selected target safe region.

The governing criterion is
`perception + calibration + tracking/settling + tool-tip uncertainty < target safe-region margin`.
Additional broad ghost routines do not advance this baseline by themselves.

The AI S2/S3 physical-camera campaign is prepared in
[`PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md`](PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md).
Its strict external-evidence manifest and read-only preflight freeze split
separation, required lighting/occlusion/placement cases, independent surveyed
ground truth, file identities, and zero authority before model evaluation. This
preparation does not satisfy any missing physical-original or calibration gate.

## Purpose

This is the common working backbone for two independently advancing workstreams:

1. **AI/model lane:** understand the user's request, assess the scene, localize
   named targets, quantify uncertainty, and emit an ordered proposal batch.
2. **Arm/runtime lane:** admit that batch, bind it to measured state and
   calibration, plan a smooth safe trajectory, execute through one controlled
   writer, and independently verify the result.

The lanes may develop and test independently. Neither lane may declare an
integration stage complete by itself. A stage completes only when the AI lane,
the arm lane, and the shared integration gate each have committed evidence.

This document is intentionally shared and focused on current coordination.
Workers update only their owned lane fields, append results to the separate
[evidence ledger](EVIDENCE_LEDGER.md), and use the integration gate to expose
contract drift early.

## Common product objective

Given a supported user instruction and fresh observations, produce the intended
physical device interaction efficiently, repeatably, and safely, while preserving
the distinction between:

- what the user requested;
- what the AI inferred and proposed;
- what deterministic planning admitted;
- what bytes the controller received;
- what the arm reported doing; and
- what an independent observer verified actually happened.

The target architecture is:

```text
User request
  -> grounded semantic intent
  -> deterministic ActionPlan
  -> scene and target observations
  -> qualified ModelMotionBatch
  -> strict deterministic ingress
  -> fresh observed arm state
  -> measured reprojection, IK, limits, and collision screening
  -> sealed TrajectoryExecutionEnvelope
  -> single-use execution permit
  -> sole controller writer and correlated receipt
  -> settle verification
  -> independent task outcome verification
  -> next action, completion, or explicit stop
```

## Non-negotiable shared invariants

These rules apply to both lanes and may not be weakened to improve benchmark
scores or latency:

1. The AI/model boundary ends at `ModelMotionBatch`. A model never emits joint
   angles, PWM, Waveshare protocol JSON, serial bytes, permits, or write authority.
2. User text is compiled into a deterministic `ActionPlan`; every motion batch
   binds the exact `plan_hash` and preserves action order and repetitions.
3. Every coordinate declares its frame and metric units. No implicit frame,
   pixel-to-millimetre assumption, or undocumented axis convention is accepted.
4. Perception uncertainty and observation confidence are distinct values.
   Qualification coverage is not silently reused as per-observation confidence.
5. Image, scene, calibration, build, configuration, target-map, controller
   session, and tool/TCP identities are content-bound where applicable.
6. Every physical action begins from a fresh authenticated arm-state read.
   Action N+1 is not planned from action N's old starting state.
7. Deterministic arm code owns IK, limits, collision screening, motion timing,
   speed, acceleration, jerk, settling, contact policy, and controller encoding.
8. One process owns the writable controller transport. Every accepted execution
   has a unique correlation ID and a durable pre-dispatch boundary.
9. An ambiguous dispatch or outcome is never retried automatically.
10. Servo arrival does not prove task success. Independent device outcome
    evidence is required before advancing a multi-action task.
11. A passing synthetic study, simulation, schema test, or shadow encoding is
    identified as such and never described as physical qualification.
12. Phone state-changing actions require new scene evidence after each action.
    Keyboard batch reuse requires a still-valid scene lease and fixed-device
    evidence.

## Ownership boundary

| Artifact or decision | AI/model lane owns | Arm/runtime lane owns | Shared gate checks |
|---|---|---|---|
| Raw text interpretation | Proposed intent and abstention | Supported capability lookup | Exact intent survives compilation |
| `ActionPlan` | Consumes compiler output | Deterministic compiler/profile | Plan hash and ordered actions |
| Scene assessment | Visibility, obstruction, quality | Required evidence policy | Freshness and domain identity |
| Target localization | Named target, coordinate, uncertainty | Measured frame validation | Target bound fits safe region |
| `ModelMotionBatch` | Produces canonical batch | Strict decode and admission | Round-trip bytes and hash equality |
| Motion policy | May provide bounded intent hints only | Clearance, timing, dynamics, contact | Hints cannot weaken arm policy |
| Calibration and tool | References required capability | Owns measured transforms and TCP | Exact identity is commissioned |
| Joint trajectory | No ownership | Owns planning and screening | Exact envelope is evidence-bound |
| Controller protocol | No ownership | Owns sole encoder/writer | Correlation and receipt integrity |
| Outcome | May consume verified result | Collects independent evidence | Requested versus observed effect |

## Status vocabulary

Use exactly these status values in the stage table:

- `NOT_STARTED`
- `IN_PROGRESS`
- `READY_FOR_INTEGRATION`
- `BLOCKED`
- `COMPLETE`

`READY_FOR_INTEGRATION` means one lane has finished its own acceptance criteria.
Only the shared integration gate may change a stage's overall status to
`COMPLETE`.

## Master stage board

| Stage | Deliverable | AI lane | Arm lane | Integration gate | Overall |
|---|---|---:|---:|---:|---:|
| S0 | Shared v1 seam and baseline | COMPLETE | COMPLETE | COMPLETE | COMPLETE |
| S1 | Contract v2: freshness, uncertainty, capability | IN_PROGRESS | READY_FOR_INTEGRATION | COMPLETE | IN_PROGRESS |
| S2 | Full zero-hardware text-to-envelope shadow path | NOT_STARTED | READY_FOR_INTEGRATION | IN_PROGRESS | IN_PROGRESS |
| S3 | Measured localization and planning readiness | IN_PROGRESS | BLOCKED | NOT_STARTED | BLOCKED |
| S4 | Zero-write Waveshare adapter and receipts | READY_FOR_INTEGRATION | IN_PROGRESS | NOT_STARTED | IN_PROGRESS |
| S5 | One independently verified physical key action | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED |
| S6 | Ordered multi-action keyboard missions | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED |
| S7 | Performance and operational qualification | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED |
| P1 | Phone capability track | BLOCKED | BLOCKED | NOT_STARTED | BLOCKED |

The S0 status is supported by the shared v1 batch, strict ingress, sequence
coordinator, journal, and focused boundary tests. S2 integration is in progress:
a raw request now traverses the grounded parser, deterministic compiler, actual
v2 emitter, and arm shadow path when given an explicitly scoped synthetic
integration fixture. Qualified perception has not yet supplied that fixture, so
this is not the complete S2 path. S3 remains blocked
from integration because no deployment localization qualification is installed
and the measured planner does not yet reach physical execution admission. S4
lists AI as ready because no new AI authority is required. The zero-write
adapter and reviewed native-shaped T=102 bridge now share the controller's
ordered joint encoding, but authentic native transport, independently acquired
receipts, and physical qualification remain unfinished. A durable native T=102
handoff now commits an exclusive writer claim before any future transport open;
restart after that claim is retry-forbidden even though native open authority is
still absent. The claimed handoff now also reaches a hardware-incapable native
executor rehearsal: fresh claim-bound authority is consumed exactly once, an
exactly typed in-memory transport records one open/write/close lifecycle, and a
closed receipt distinguishes requested and confirmed bytes from authentic
controller receipt or movement. A real serial transport and physical authority
remain absent and require independent review. The executor lifecycle now also
has a durable terminal receipt journal: a content-bound `started.json` is
committed before the rehearsal transport may open, so pre-terminal restart is
always retry-forbidden, and a separately flushed `terminal.json` seals the
exact byte-accounted receipt with terminal no-replay semantics.
ARM-053 now defines the production-shaped seam outside that incapable executor:
an exact COM/USB identity, detached externally issued single-use authority,
external verifier interface, one-open/one-T=102-write/one-capture/one-close
abstract transport, exact T=1021 and settled T=1051 validation, and its own
durable pre-open/terminal attempt journal. No concrete transport, authority
issuer, verifier keyring, port discovery, or controller process is included,
so all current ARM-053 capture evidence remains scripted and explicitly
unqualified. ARM-054 now supplies a separately isolated Windows serial adapter
candidate with exact pre/post-open USB identity checks, finite read/write
timeouts, one
canonical T=102 write, bounded T=1021 capture, and exactly two T=105/T=1051
feedback exchanges. It is not connected to a CLI, authority issuer, controller
startup, or automatic runtime composition. The next dependency is independent
source review followed by separately authorized endpoint and physical
qualification, not further model-contract expansion.
ARM-055 now freezes that exact merged candidate into a deterministic,
content-addressed review packet and exercises the real adapter class through
ARM-053 using memory-only serial and inventory fixtures. The composition audit
shows crossed external authority is durably started and rejected before adapter
open, while a successful scripted path retains terminal no-replay evidence and
cannot promote controller provenance, movement qualification, or follow-on
authority. Packet status remains `AWAITING_EXTERNAL_INDEPENDENT_REVIEW`; this
repository has not performed or impersonated that review. The next dependency
is an external decision bound to the packet SHA-256, followed only under
separate authorization by read-only endpoint qualification.
ARM-056 now defines the closed return path for that outside decision. It binds
the exact packet, manifest, candidate commit, adapter source, ordered
adapter/composition checklist, reviewer declarations, findings, disposition,
and explicit validity window. Synthetic, future, expired, rejected,
packet-crossed, source-crossed, incomplete, author-conflicted, or open-finding
decisions cannot become endpoint-qualification-intake ready. Even a valid
external decision keeps endpoint open, controller start, execution, hardware,
and physical authority false. No independent review is yet present; the next
dependency remains a real outside decision and separately authorized read-only
endpoint qualification.
ARM-057 now makes the external exchange operational without crossing that
boundary. A deterministic builder emits the immutable packet, decision/report
schemas, reviewer procedure, and a content-addressed exchange manifest with no
decision included. A separate strict intake reads one returned regular JSON
file, rejects duplicate fields, oversize, symlinks, mutation, and overwrite,
then retains a normalized decision, assessment report, and raw-document hash.
Blocked reviews remain retained and non-authorizing. This tooling performs no
hardware access and does not solve reviewer identity or custody; those remain
external prerequisites.
ARM-058 adds an automated zero-write command/telemetry replay seam. It consumes
the exact Waveshare T=102 preview receipt and typed synthetic or retained-export
T=1051 samples, binds correlation/session/waypoint identity and timing, and
requires consecutive six-joint arrival plus stability at every previewed
waypoint. Crossed, stale, non-monotonic, malformed, incomplete, unstable, and
out-of-tolerance cases cannot become a replay PASS. Even PASS keeps physical
arrival, visual outcome, transport access, execution, and physical authority
false. This improves automated S4/S7 rehearsal coverage but does not satisfy
the pending ARM-054 independent-review or read-only endpoint prerequisites.
ARM-059 records the project owner's explicit acceptance of the exact internal
AI technical review as the adapter source-review prerequisite, while preserving
that no human review or external independence is claimed. The hash-bound owner
acceptance makes the next read-only endpoint-qualification intake eligible for
design and later separate authorization. It does not authorize endpoint open,
controller startup, any transport write, execution, hardware access, or
physical movement. Under this owner-defined policy the adapter review milestone
is complete with caveat; the next arm-lane dependency is the closed read-only
endpoint-qualification intake and its separately authorized physical run.
ARM-060 now defines that closed intake. It binds the exact ARM-059 acceptance,
one explicit host, one pinned COM/USB identity, and a finite passive-read plan.
The proposed run may open and close that endpoint once but permits zero writes,
zero active requests, zero movement or torque commands, no purge, no fallback,
no retry, and no DTR/RTS assertion. The implementation performs no discovery,
port open, or I/O. A valid record is only
`READY_FOR_SEPARATE_READ_ONLY_AUTHORIZATION`; every endpoint, controller,
transport, execution, hardware, and physical authority remains false. No real
intake is retained until the actual host and endpoint identity are established
without guessing. The next dependency is a separately authorized creation of
that exact intake and then a separately bounded passive qualification run.
ARM-061 now retains the first exact intake after a fresh Windows PnP-only
identity check found the historically documented CP210x controller on COM7 and
distinguished it from the host's Bluetooth serial endpoints. The host name is
represented by a SHA-256-derived pseudonymous identifier. Strict tests validate
the retained artifact against the closed schema and recomputed endpoint/intake
hashes. No serial open occurred. The next boundary is unchanged: a separate,
explicit authorization must name intake
`2d88fa8874088ce47b778343ea0ed07994bafb64267b8cd121765c52536ce1d9`
before the one-open, zero-write passive qualification may run.
ARM-062 completed that separately authorized passive run exactly once. PnP
identity matched before and after open; the endpoint opened and closed once;
the close was confirmed; and no bytes, requests, movement, torque action,
retry, purge, or DTR/RTS assertion occurred. The one-second window contained no
unsolicited complete or partial lines. This qualifies only the pinned endpoint
lifecycle under the passive zero-write policy. It does not qualify controller
protocol or firmware identity. ARM-063 now freezes the next active, non-moving
feedback proposal: one exact ten-byte `T=105` request, one bounded `T=1051`
response, and one open/write/read/close lifecycle, with no T=102, movement,
torque, retry, purge, fallback, startup, or DTR/RTS assertion. Its retained
intake hash is
`3b44d5e011d8c44afda1bb6deb1cc479b1fc0c45e59e39308d285cde416b8fcc`.
Only a fake endpoint has exercised the contract. The intake grants no live
open or write authority; the physical exchange requires a separate explicit
owner authorization naming that hash.
Neither passive evidence nor the fake rehearsal qualifies installed firmware,
physical telemetry accuracy, actuation, or model-command execution. The next
arm-lane dependency is the separately authorized ARM-063 exchange, not another
passive retry.
ARM-064 consumed that authorization exactly once. COM7 opened and closed once,
the pre-request buffer was empty, and the exact T=105 bytes were written once.
The installed surface returned `FAULT:NOT_READY\r\n` instead of T=1051. No
retry, movement, T=102, torque action, startup, purge, fallback, or DTR/RTS
assertion occurred. The exact fault exists in the finite ghost-typing source,
so the result is consistent with the known diagnostic surface but does not
attest installed firmware identity. The generic feedback seam and observed
planner start state remain blocked. The next dependency is resolving the
installed-runtime mismatch under a separate reviewed installation/startup
planâ€”not repeating this request.
ARM-065 now reconciles that terminal result with the sealed r97 candidate. The
assessment binds the ARM-064 receipt and response digests to the exact r97
packet, manifest, and app hashes and remains `BLOCKED`. The installed surface
is diagnostic-consistent but not attested as r97; independent r97 review and
all eight measured epoch components are absent; and r97 still reports a null
epoch. No installation intake is ready, and no installation, startup,
transport, execution, hardware, or physical authority was created. The shared
next dependency is external r97 review plus the measured configuration epoch,
followed by a separately reviewed hash-bound installation proposal.
ARM-066 verified the ignored seven-member r97 packet directly from the retained
compiled inputs; its SHA-256 remains
`987cbe86d98440734d8336c704f1ecd89692675a9cb1620cb674e4132957b416`.
It also adds the missing owner-side intake CLI for a returned external decision.
That CLI strictly parses, normalizes, assesses, and immutably retains one
decision while keeping every physical authority false. This makes the external
review handoff operational without pretending that repository code can perform
the independent review. The dependency is unchanged: a genuinely independent
reviewer must return the decision, then all eight measured epoch components
must be collected and reviewed.
ARM-067 records the owner's decision that no human reviewer will be used. The
exact r97 AI technical review is accepted through a hash-bound governance
override that explicitly sets `human_review_claimed=false` and
`external_independence_claimed=false`. External review is now optional rather
than blocking. The next active dependency is an owner-governed configuration
epoch containing retained physical evidence and AI review records for all
eight controlled workcell components. This override creates no installation,
startup, transport, execution, hardware, or physical authority.
ARM-068 implements that next boundary without rewriting the historical
independent-review epoch contract. Its owner-governed draft accepts zero through
eight components, requires the policy-defined binding set for each component,
and reports missing, stale, synthetic, or unreviewed evidence separately. A
confirmed-not-installed station may be represented, but still requires retained
physical evidence and owner-AI review. The retained initial assessment is
correctly `BLOCKED`: all eight components and their 32 required bindings are
missing. No configuration-epoch hash exists until the complete draft passes.
The next work is evidence population, beginning with the reproducible
`software_build` component; no controller operation is needed for that step.
ARM-069 closes that first component from retained original software inputs. It
binds the exact r97 app, packet, manifest, compile profile, source baseline,
dependency declaration, protocol encoder, and joint mapping into four
content-addressed binding records, then records a closed owner-AI review. The
partial epoch assessment advances only `software_build`; the other seven
components remain explicitly `MISSING`, the configuration-epoch hash remains
null, and every hardware authority remains false. The next ARM dependency is
the retained camera/support/optics evidence bundle, not another software-build
or controller test.
ARM-070 implements that camera/support/optics intake and evaluates the actual
repository baseline. The purchased profile still says
`PURCHASED_PENDING_RECEIPT`; received-unit, USB identity, commissioned mode,
control-readback, and qualified support evidence are absent, and all 55 hardware
intake rows remain unresolved. The retained result therefore keeps all four
camera bindings missing and does not alter the ARM-069 epoch. The next step is
physical-original collection through the existing onboarding workflow, not a
synthetic substitution or another controller test.
ARM-073 closes the software-only gap between those retained originals and the
ARM-070 binding slots. It accepts only four canonical owner-AI review records,
performs bounded substitution-aware reads beneath one safe root, verifies the
exact original and review hashes, and emits typed bindings plus zero-authority
receipts. It does not create evidence, perform a review, decide freshness,
advance the epoch, open a camera, or authorize hardware. The physical collection
dependency remains unchanged; once those originals exist, this adapter removes
manual transcription from their ARM-070 intake.
ARM-075 begins the offline T2B typing optimization gate without changing that
physical dependency. It consumes the exact T2A Cartesian screening samples,
binds them to the pinned build and calibration identities plus an explicitly
synthetic offline joint seed, and applies the canonical deterministic IK,
joint-margin, Jacobian-rank, and adjacent-joint continuity gates. Passing
samples advance only to `READY_FOR_INSTALLED_GEOMETRY_COLLISION_SCREENING`;
installed collision geometry, cable evidence, conservative segment sweeps,
controller access, and all physical authority remain absent.
ARM-076 adds the next zero-authority intake seam. It validates the exact
T1/T2A/IK lineage, preserves the synthetic start-state label, and produces the
bounded joint-sample plan plus exact installed-profile evidence slots needed by
the existing FK/collision/sweep pipeline. It refuses to substitute nominal
geometry for a measured installed profile and never presents its synthetic seed
as observed feedback. Physical evidence population and a fresh observed start
state remain the next dependencies.
The AI precision lane now has a mainline-compatible pose-output adapter and v2
batch producer. It preserves repeated targets and abstains on qualification,
domain, freshness, identity, confidence, or containment failure. Its retained
held-out evidence is still `SYNTHETIC_OFFLINE_ONLY`: the 14.400834977 mm bound
crosses ordinary key safe regions, so no deployment qualification is installed
and the operational-readiness perception gate remains blocked.

## Stage definitions

### S0 â€” Freeze the shared v1 seam

**Goal:** prove both lanes use one ordered, hash-bound model-to-planner contract.

AI lane completion:

- Emit the core `ModelMotionBatch`, not a duplicate AI-only command schema.
- Preserve action order and repeated targets.
- Bind intent, scene, precision, fusion, model, frame, and image identities.
- Emit no controller command or physical authority.

Arm lane completion:

- Strictly decode the same batch type.
- Compare device, plan hash, target order, evidence hashes, confidence, target
  containment, and interaction type.
- Require fresh observed joint state per admitted action.
- Stop before transport access.

Integration evidence:

- Actual emitter output round-trips through shared decoding and ingress.
- Repeated `H`, `H`, `I` remains ordered and unique by proposal ID.
- Current focused boundary suite passes.

**Status:** complete at baseline. Future schema changes must preserve a v1
compatibility fixture or record an explicit migration.

### S1 â€” Contract v2: freshness, uncertainty, and capability

**Goal:** remove semantic ambiguity before either lane approaches live execution.

AI lane objectives:

- Separate `observation_confidence` from localization qualification coverage.
- Emit a structured uncertainty object containing at least bound type, bound in
  millimetres, coverage probability, qualification hash, and domain ID.
- Bind capture identity and time, evaluation time, expiry/scene lease, model
  identity, target-map identity, and capability profile.
- Bind keyboard placement/orientation through independently evidenced geometry;
  never validate a predicted point against a target rectangle centered from that
  same prediction.
- Keep action coordinates, interaction intent, and target IDs; do not add servo
  or protocol fields.
- Define keyboard frame output as one explicit producer profile. If board-frame
  output remains selected, document how it was derived from image evidence.

Arm lane objectives:

- Strictly decode and validate the new fields without trusting the producer's
  acceptance decision.
- Enforce expiry at ingress and again immediately before planning.
- Validate qualification/domain/capability registries independently.
- Require the entire uncertainty regionâ€”not only its centerâ€”to fit the measured
  target safe region.
- Treat model speed and clearance as non-authoritative hints, or remove them and
  derive policy entirely from the arm configuration.
- Preserve a migration decoder for frozen v1 fixtures; never guess absent v2
  semantics for live work.

Shared integration gate:

- Canonical AI fixture validates under the published schema and Python decoder.
- Mutations of timestamp, qualification, uncertainty, frame, plan, capability,
  and target-map identities are rejected one at a time.
- Schema validation and runtime validation agree on numeric and index bounds.
- A v2 compatibility matrix is committed with producer and consumer versions.

Completion evidence:

- Contract/schema paths and SHA-256 hashes.
- Exact test command and results.
- Migration behavior for v1.
- Limitations and explicit non-authority statement.

### S2 â€” Full zero-hardware text-to-envelope shadow path

**Goal:** exercise the real components in order without writing to hardware.

AI lane objectives:

- Accept a raw supported text request through the grounded parser/reference
  interpreter.
- Compile it using the deterministic keyboard compiler.
- Run the selected scene and precision components, including abstention.
- Emit the exact batch consumed by the arm lane.
- Preserve unsupported and clarification outcomes rather than forcing a plan.

Arm lane objectives:

- Decode and admit the actual emitted bytes.
- Create the sequence coordinator and consume a fresh observed-state fixture.
- Run measured reprojection, IK, limits, and route/collision screening.
- Produce a sealed `TrajectoryExecutionEnvelope` when all gates pass, or one
  exact blocker when they do not.
- Generate no Waveshare bytes and perform zero writes.

Shared integration gate:

- One command runs the complete shadow path and emits one trace bundle.
- Trace links raw request hash, plan hash, observation hashes, batch hash,
  ingress hash, planner hash, observed-state hash, and envelope hash.
- Supported, ambiguous, stale, obstructed, out-of-bound, and unsupported cases
  all reach their expected terminal states.
- No test substitutes a hand-authored batch for the actual AI emitter output.

Completion evidence:

- Reproducible command and committed sanitized fixture set.
- End-to-end trace manifest.
- Cross-lane negative test matrix.
- Confirmation of zero hardware access and zero generated wire commands.

### S3 â€” Measured localization and planning readiness

**Goal:** replace synthetic assumptions with measured deployment evidence.

AI lane objectives:

- Freeze the final camera/domain definition and independent train,
  calibration, and held-out evaluation splits.
- Measure per-target localization error, abstention, obstruction detection, and
  scene-quality rejection from the actual camera geometry.
- Install a qualification only when its declared coverage and target-fit gates
  pass on held-out deployment data.
- Record domains and targets not covered by the qualification.

Arm lane objectives:

- Commission camera, board, device placement, robot base, and tool/TCP
  transforms with validity and expiry.
- Complete installed geometry, cable, keyboard, board, and exclusion-volume
  models needed for continuous collision screening.
- Demonstrate the planner's reserved ready status from fresh measured state,
  without encoding or transmitting commands.
- Measure joint limits and conservative velocity, acceleration, jerk, and
  settling limits.

Shared integration gate:

- Actual held-out camera observations produce v2 batches whose uncertainty
  regions fit named targets after measured reprojection.
- Those exact batches reach sealed trajectory envelopes from fresh state.
- Deliberately moved keyboard, stale calibration, wrong tool, occlusion, and
  out-of-domain images fail closed.
- Qualification and calibration artifacts remain separately identifiable.

Completion evidence:

- Qualification and calibration artifact hashes.
- Held-out scorecards and target coverage list.
- Planner-ready trace with zero hardware writes.
- Failure evidence for every required negative case.

### S4 â€” Zero-write controller adapter and correlated receipts

**Goal:** prove exact protocol encoding and execution lifecycle without sending.

AI lane objectives:

- Keep the batch contract stable and consume arm capability information only
  through the supported capability profile.
- Add no controller-specific fields.
- Verify model-side tests still pass against the adapter's supported action set.

Arm lane objectives:

- Implement a zero-write Waveshare encoder that accepts only a sealed,
  unexpired `TrajectoryExecutionEnvelope` plus a separate single-use permit.
- Define how timed waypoints map to the controller's actual command semantics.
- Define fixed-gripper/tool behavior explicitly.
- Reject stale sessions, duplicate correlation IDs, expired deadlines, altered
  envelopes, unsupported interpolation, and unmeasured limits.
- Build a sole-writer lifecycle and a content-bound receipt format covering
  submitted bytes, acknowledgements, feedback, timeouts, and closure.

Shared integration gate:

- Golden byte fixtures are deterministic and reviewable.
- Decode/encode units and joint ordering agree with the commissioned controller.
- Duplicate, stale, altered, partial-write, timeout, and restart cases fail
  without automatic resend.
- Test instrumentation proves transport write count remains zero.

Completion evidence:

- Encoder source and golden fixtures.
- Controller protocol/version citation or pinned vendor artifact.
- Receipt and permit schemas.
- Fault-injection results with zero physical writes.

### S5 â€” One independently verified physical key action

**Goal:** demonstrate one admitted model-originated key interaction end to end.

AI lane objectives:

- Produce one qualified target proposal from a fresh deployment observation.
- Abstain when any required scene, domain, confidence, or uncertainty condition
  is not satisfied.
- Retain the exact user request and plan lineage.

Arm lane objectives:

- Execute exactly one admitted envelope through the sole writer.
- Monitor tracking, limits, deadline, and settling throughout the action.
- Retract safely and preserve torque policy.
- Produce one execution receipt and independent keyboard outcome observation.
- Never retry an uncertain dispatch or outcome.

Shared integration gate:

- Requested key, proposed target, transmitted command, feedback, and observed
  character are separately recorded and agree.
- A failed or uncertain outcome terminates without a second press.
- Physical test approval, cleared workspace, build identity, and stop reason are
  recorded outside this plan in the run evidence.

Completion evidence:

- Sanitized physical run manifest and receipt hashes.
- Independent outcome artifact.
- Tracking/settling metrics and discrepancies.
- Explicit count of physical writes and movements.

### S6 â€” Ordered multi-action keyboard missions

**Goal:** execute supported strings smoothly while preserving per-action safety.

AI lane objectives:

- Preserve exact text, action order, repetitions, punctuation, and unsupported
  character handling.
- Define when a fixed-keyboard scene lease may span multiple actions and when a
  new observation is mandatory.
- Never repair or reorder a plan based on convenient geometry.

Arm lane objectives:

- Advance only after verified completion of the preceding action.
- Read fresh arm state for each action while caching only immutable geometry.
- Optimize safe hover-to-hover transitions, planner warm-up, and settled motion
  without bypassing ingress or outcome checks.
- Recover from restart through the durable journal without replaying an
  uncertain action.

Shared integration gate:

- Held-out strings cover repeated keys, rows, numbers, punctuation, space, and
  enter within the supported profile.
- Requested and independently observed output match exactly.
- Fault injection covers device movement, stale lease, dropped feedback,
  process restart, and ambiguous outcome.

Completion evidence:

- Mission corpus and held-out definition.
- Exact-match outcome scorecard.
- Per-action lineage and latency breakdown.
- Restart and fault-injection reports.

### S7 â€” Performance and operational qualification

**Goal:** improve speed only after correctness and recovery are demonstrated.

The arm-side implementation sequence, rolling-horizon boundary, motion-shaping
rules, and speed ladder are defined in the
[optimized typing execution plan](../../docs/OPTIMIZED_TYPING_EXECUTION_PLAN.md).
That plan retains a one-action commit horizon: preview and transition-cache work
may reduce latency, but neither grants physical authority.

AI lane objectives:

- Measure intent, scene, precision, fusion, and emission latency separately.
- Reduce inference latency without changing qualification semantics.
- Track abstention, false acceptance, coordinate error, and domain drift.

Arm lane objectives:

- Measure ingress, planning, encoding, dispatch, travel, settling, observation,
  and total action latency separately.
- Tune trajectories under measured limits and tracking error budgets.
- Add watchdog, cancellation, operator stop, and bounded resource behavior.

Shared integration gate:

- Publish p50/p95/p99 latency, exact outcome rate, tracking error, abstention,
  transport fault, and recovery metrics on held-out missions.
- Demonstrate that performance changes do not reduce safety-gate coverage.
- Freeze supported device/task/camera/tool profiles for the qualified release.

Completion evidence:

- Qualification report and release commit.
- Reproducible benchmark commands and environment identity.
- Regression thresholds enforced in CI.
- Remaining limitations and unsupported capabilities.

### P1 â€” Separate phone capability track

Phone work does not inherit keyboard readiness automatically. It requires:

- named screen states and legal transitions;
- a fresh observation after every state-changing tap;
- screen-local coordinates and measured screen placement;
- independent state verification before the next tap;
- explicit support for dialer navigation, number entry, call initiation, and
  cancellation; and
- its own held-out perception, planning, execution, and outcome qualification.

Until those gates exist, phone requests remain `unsupported_by_profile` or
blocked at the batch emitter.

## Shared contract-v2 design record

S1 owns the exact schema, but both workers must design against these semantics:

```text
ModelMotionBatchV2
  identity:
    batch_id, request_id, plan_hash, device, capability_profile
  evidence:
    frame_id, image_hash, capture_time, evaluation_time, expiry/scene_lease
    scene_hash, precision_hash, fusion_hash, model_id
  qualification:
    domain_id, qualification_hash, target_map_hash
    coverage_probability, error_bound_mm, bound_type
  actions[]:
    proposal_id, target_id, coordinate_frame, target_mm, interaction
    observation_confidence
  prohibited:
    joint targets, PWM, controller JSON, serial bytes, transport identity,
    execution permit, physical authority
```

This block is a semantic design target, not yet the authoritative schema.
Committed schema and decoder changes must link their evidence below.

## Required shared test matrix

Every contract or runtime change must preserve tests for:

| Category | Required cases |
|---|---|
| Intent | supported literal, ambiguity, extra operation, unsupported character, wrong device |
| Ordering | repeated key, punctuation, multi-row sequence, altered order, missing action |
| Provenance | altered plan, image, model, scene, precision, fusion, target map, qualification |
| Freshness | fresh, expired, future timestamp, moved device, changed scene lease |
| Geometry | center, safe-edge bound, uncertainty crossing edge, wrong frame, wrong plane |
| Capability | unsupported profile, wrong tool/TCP, phone through keyboard-only path |
| Arm state | fresh state, stale state, reused state, wrong controller session |
| Trajectory | joint limit, velocity, acceleration, jerk, collision, deadline, settling |
| Transport | duplicate correlation, partial write, timeout, stale session, restart |
| Outcome | verified, failed before dispatch, ambiguous after dispatch, mismatched character |
| Authority | no model servo fields, no wire bytes before permit, no automatic retry |

## Evidence ledger rules

1. Evidence rows are append-only. Never edit an old failure into a pass.
2. Corrections receive a new evidence ID and reference the superseded row.
3. Every row names one repository commit and one exact test/evaluation command.
4. Store large or structured artifacts in the appropriate committed evidence or
   evaluation directory; link them here rather than pasting raw output.
5. Mark `hardware_writes` and `physical_movements` explicitly, including zero.
6. Do not commit credentials, private settings, raw authorization material, or
   unsanitized user data.
7. A lane may set itself to `READY_FOR_INTEGRATION` after its acceptance criteria
   pass. Only a cross-lane evidence row may complete the integration gate.

### Evidence row template

Copy this row and fill every field:

```markdown
#### E-YYYYMMDD-AI|ARM|INT-NNN â€” short title

- Stage: S#
- Lane: AI | ARM | INTEGRATION
- Commit: full SHA
- Change: concise description
- Inputs/fixtures: paths and hashes
- Command: exact reproducible command
- Result: PASS | FAIL | BLOCKED, with counts/metrics
- Artifacts: repository-relative links
- Hardware writes: integer
- Physical movements: integer
- Limitations: explicit scope and unresolved issues
- Supersedes: evidence ID or `none`
- Next dependency: exact other-lane artifact or gate
```

## Evidence ledger

Detailed, append-only AI, arm, and integration results are kept in the
[Tactevra AI/arm evidence ledger](EVIDENCE_LEDGER.md). Keep this workplan focused
on current stages, ownership, dependencies, and operating rules. Add new results
to the ledger using the template above; do not rewrite an earlier result.

## Active work claims

The current zero-authority integration baseline is
[`model_arm_conformance_profile_v1.json`](../../config/model_arm_conformance_profile_v1.json),
SHA-256 `2430ec5f8362aae76e8250d2d9da292f85375d93750addd944a969b1bc2e4dbd`.
It binds the reviewed arm and AI commits, freezes the implemented v2 boundary,
and provides shared accepted/rejected cases without advancing operational readiness.

The pose-keyloss research checkpoint is now represented by the focused external-
artifact package in
[`POSE_KEYLOSS_EXTERNAL_ARTIFACT.md`](POSE_KEYLOSS_EXTERNAL_ARTIFACT.md) and
evidence `E-20260927-AI-410`. Its clean-clone state is explicitly unavailable,
its separately present bytes are identity-verified, and neither result installs
localization qualification or changes the AI-to-arm authority boundary.

AI work and test documentation is maintained through the
[`AI work and evidence handbook`](AI_WORK_AND_EVIDENCE_HANDBOOK.md), the
machine-checked [`AI work registry`](AI_WORK_REGISTRY.json), and evidence
`E-20260927-AI-419`. The registry assigns every tracked AI test module to one
workstream and binds its source, governing documents, retained evidence,
limitations, and next gate. This documentation baseline changes no lane or
integration status.

The post-preflight physical-camera evaluator is implemented at evidence
`E-20260927-AI-422`. It revalidates retained campaign bytes, binds every
prediction to image/model/preprocessing identities, derives an empirical bound
from calibration only, scores held-out coverage and unsafe-scene acceptance,
and checks a conservatively composed bound against the frozen target map. It
emits only an offline review recommendation and installs no qualification.

Workers add a short row before beginning a potentially overlapping change and
remove it only in the same commit that appends the resulting evidence row.

The latest completed SIM/WP2 increments are evidence `E-20260929-INT-445`
through `E-20260929-INT-449`. They retain a bounded triangle-preserving
`link2` partition candidate, bind all 165 remaining false positives to pinned
upstream `Adjacent` policy evidence, verify that all six separate SRDF `Never`
pairs remain free in the exact 49-pose corpus while preserving three
nonexcluded nonadjacent collision witnesses, and encode all twelve upstream
pairs in a strict hash-bound candidate document. The candidate is explicitly
uninstalled, defaults every pair to collision checking, has zero effective
exclusions, and grants no collision, clearance, controller, permit, transport,
or physical authority.

The held-out stress campaign in `E-20260929-INT-449` expands the selected
geometry and inert candidate to 256 disjoint Halton poses and 5,376 pair cases.
All six proposed `Never` pairs remain free and no false negative appears, but
13 false positives reappear across six nonproposed pairs. This prevents any
collision-query or exclusion-policy promotion and directs the next geometry
work toward those exact retained-pair witnesses.

The process-alignment overlay in `E-20260929-INT-450` returns WP2 to the actual
AI-to-arm seam. It binds an AI-produced `ModelMotionBatchV2` carrying ordered
`H, H, 1, PERIOD` proposals to the governed RC03 Isaac scene and authors the
proposal centers, inferred synthetic placement, key regions, and uncertainty
disks. The target centers share one rigid placement within numerical precision,
but the 14.400834977 mm localization disk exceeds each 7 mm key-edge margin.
The replay therefore stops before a joint schedule. The next simulation input
is the exact zero-write schedule from the arm typing pipeline, after its source
batch uses this same representative target geometry and passes the safe-region
uncertainty gate.

The source-bound schedule replay in `E-20260929-INT-451` consumes arm commit
`5072c163152848bd8d78fa3fbc024e32177ac98d` through the strict v2 ingress,
trajectory, IK, and joint-dynamics stages for representative ordered targets
`H, H, 1, PERIOD`. The nominal geometry fails the arm-margin gate, and the
simulation overlay with the nominal ready seed fails continuity; both failures
remain retained. With the existing simulation-only layout, 120 mm keyboard
tool, and a synthetic seed at the declared park pose, all 133 samples reach the
installed-geometry collision gate and replay in Isaac with maximum tool-tip
disagreement `0.07684842940066568` mm. This validates the offline coordinate,
ordering, IK, scheduling, and independent-FK seam only. It does not replace the
blocked safe-region AI evidence, execute collision screening, or change any
lane or integration-gate status. The arm branch subsequently advanced to
`7f22378613bc9866b14912e667882af9201fd52c` with profiled-service routing for
the shared emitter; the retained replay remains honestly bound to its exact
`5072c163152848bd8d78fa3fbc024e32177ac98d` source and should be repeated from
the newer service path when safe-region-qualified producer output exists.

The actual-emitter replay in `E-20260929-INT-452` closes that producer
substitution question for the synthetic representative case. It binds arm
commit `9e5c878852da6a6e8509598bce9ce43f218efc70`, the actual shared emitter's
canonical batch bytes, strict v2 admission, 133-sample schedule, and independent
Isaac FK replay. `H, H, 1, PERIOD` and every replay metric remain identical to
the fixture-origin run. The evidence explicitly marks the supplied observations
as synthetic and claims no deployment qualification. The remaining priority is
therefore qualified physical-camera localization and installed collision
geometry, not another synthetic producer substitution.

The fixed-fixture practice corpus in `E-20260929-INT-453` adds 16 deterministic
JPEGs from the existing plan-blind virtual arm-camera boundary: two achieved
camera poses crossed with nominal, dim, bright, warm, glare, blur, and two
foreground arm/tool-obstruction cases. Every sample binds the frozen 46-key and
29-phone target catalog in board millimetres and projected pixels, the exact
pixel transformation, source image identities, and zero authority. This is a
repeatable pretraining and data-pipeline fixture for a keyboard and phone that
remain fixed on the board. The device surfaces, lighting, obstruction, and
camera are synthetic approximations, so the corpus does not change S2/S3 lane
status, install localization qualification, or reduce the physical-camera and
installed-collision dependencies.

The fixed-overview segmentation corpus in `E-20260930-INT-454` aligns the
synthetic data flow more closely with the intended installation: one camera and
board transform remain fixed while three URDF joint states move a pose-bound
robot obstruction. It retains 15 RGB practice samples in three deterministic
atlases, plus per-pose semantic link masks, approximate millimetre depth maps,
and per-target obstruction overlap for all 75 targets. A repository-footprint
failure from the initial separate-image layout is retained; packing the RGB
samples into crop-addressed atlases brought the tracked archive back within its
governed ceiling. The link shapes remain capsule proxies rather than CAD meshes,
so this increment advances data-pipeline and abstention rehearsal only and does
not change any lane or integration status.

The official-mesh comparison in `E-20260930-INT-455` replaces the capsule
shape only for a bounded perception experiment. Seven visual meshes from the
pinned Waveshare source are placed by the governed URDF FK and rasterized in
Isaac from the identical fixed camera at `ready`, `hover_t`, and `hover_e`.
Capsule-to-mesh mask IoU is only `0.596819` to `0.709856`, and the capsule
misses `9,908` to `30,058` mesh pixels. The capsule corpus remains useful for
obstruction rehearsal, but this result rejects treating it as a conservative
robot silhouette. The official meshes are visual geometry only; no collision,
clearance, localization, lane, or integration status changes.

The target-bound extension in `E-20260930-INT-456` projects the frozen catalog
of 46 keyboard and 29 phone targets into each official-mesh render and records
center occlusion plus safe-region overlap. The official geometry obscures
`1/14/14` centers and overlaps `5/17/18` safe regions at
`ready/hover_t/hover_e`. These labels are now suitable for offline abstention
training and evaluation fixtures. Their camera and placement remain nominal,
so they install no physical qualification or authority.

The AI data builder in `E-20260930-AI-457` converts those target-bound renders
into 450 training and 225 held-out evaluation rows. Training uses `ready` and
`hover_t` with nominal, dim, and bright images; evaluation holds out both the
`hover_e` pose and warm, glare, and blur transformations. It labels only
`target_visible` or `abstain` under a predeclared 0.20 safe-region-overlap
threshold. This is a reproducible synthetic development dataset, with no
deployment qualification or change to the `ModelMotionBatchV2` boundary.

The first small occlusion baseline in `E-20260930-AI-458` demonstrates why the
held-out grouping matters. A class-weighted logistic model reaches 99.3%
training accuracy but only 66.7% on the held-out pose and lighting families,
with 13 missed abstentions, 62 false abstentions, Brier score `0.3274`, and
ten-bin calibration error `0.3329`. It remains blocked. The consumed synthetic
evaluation split cannot now be used to tune a replacement; new pose groups
must be declared before the next model experiment.

The predeclared pose expansion in `E-20260930-AI-459` now provides that new
geometry without consuming its final evaluation role. Nine official-mesh poses
are partitioned as three previously observed training poses, two new `H`
development poses, and four untouched `1`/`PERIOD` evaluation poses. The six
new states are selected by sequence from the hash-bound zero-authority actual-
emitter schedule. All masks are pose-distinct. These external synthetic bytes
still omit measured tool and camera-support geometry and cannot qualify physical
visibility, localization, collision clearance, or execution.

The three-way dataset in `E-20260930-AI-460` materializes 675 training, 450
development, and 900 reserved evaluation target crops across 27 distinct
images. Pose groups and lighting families are pairwise disjoint, and two
independent builds are byte-identical. The evaluation bytes exist for identity
and leakage checks but remain unscored; the next candidate must be selected
using training and development only before that group is evaluated once.

The compact selection experiment in `E-20260930-AI-461` selected brightness-
normalized chromatic/edge features at threshold `0.25` using development only,
then consumed the reserved evaluation once. Although evaluation accuracy is
94.0%, the model misses 52 of 129 required abstentions. That 40.3% miss rate is
unsafe for occlusion admission, so the checkpoint remains blocked and this
evaluation group is unavailable for further selection or tuning.

The transit-geometry expansion in `E-20260930-AI-462` adds twelve unused
actual-emitter schedule states while folding all consumed endpoint poses into
training. Six outbound/return states form development and six inter-key states
remain untouched evaluation geometry. All 21 official-mesh masks are distinct;
the reserved inter-key group contains materially more occlusion than the
development group. No model has consumed or scored the new evaluation group.

The deterministic dataset in `E-20260930-AI-463` expands the 21-pose source to
6,075 training, 1,350 development, and 1,350 reserved evaluation rows across
117 distinct images. Previously consumed lighting is confined to training;
development and evaluation use new pairwise-disjoint lighting families. Two
independent builds are byte-identical, and the evaluation group remains
unscored and unavailable during the next candidate-selection step.

The tiny spatial candidate in `E-20260930-AI-464` meets its predeclared
development missed-abstention preference and then misses only 2 of 276
occlusions on the fresh transit evaluation. It also falsely abstains on 433 of
1,074 visible targets, so it is substantially safer than the prior crop model
on its own fresh test but too conservative for useful typing cadence. The
checkpoint remains synthetic-only and blocked; its evaluation split is now
consumed and cannot be used to tune the false-abstention rate.

The fresh specificity campaign in `E-20260930-AI-465` freezes twelve unused
actual-emitter schedule poses and six new lighting families before rendering.
Its tiny spatial candidate reduces held-out false abstentions to 28 of 1,239
visible targets, but misses 15 of 111 required abstentions. The result is
reproducible and substantially more usable, while the higher dangerous miss
rate blocks promotion. Its evaluation is consumed and cannot be used for
threshold or architecture tuning.

The deterministic video bundle in `E-20260930-AI-466` turns the exact AI-465
source frames and frozen predictions into two hash-bound H.264 review artifacts.
One records all 33 official-mesh poses with ground-truth safe-region overlays;
the other records all 18 held-out pose/lighting images with per-target model
outcomes, including every false stop and missed abstention. Independent exports
are byte-identical. The videos add reviewable progression evidence only: they
do not add temporal physics, new evaluation data, runtime authority, or physical
qualification, and the AI-465 candidate remains blocked.

The target-aware experiment in `E-20260930-AI-468` predeclares twelve unused
actual-emitter schedule poses and six new lighting families, then gives the
tiny RGB crop model one additional catalog-derived safe-region channel. The
simulator robot mask remains label-only. On a fresh held-out synthetic group,
missed abstentions fall to 5 of 165 and false abstentions remain 27 of 1,185;
two complete builds are byte-identical. This is the first candidate in this
sequence to hold both synthetic error rates below 5% on its own fresh split.
It remains blocked because exact target alignment is assumed and neither final-
camera localization uncertainty nor physical support/tool geometry is present.
The consumed evaluation may not tune another candidate.

The deterministic v2 video bundle in `E-20260930-AI-469` binds the exact
four-channel AI-468 checkpoint to 45 official-mesh pose frames and all 18
consumed evaluation images. Two independent exports are byte-identical and the
evaluation overlays reproduce the frozen 160/1,158/27/5 confusion counts. The
manifest explicitly identifies the known-target safe-region channel and the
absence of simulator robot-mask input. This adds reviewable evidence only; it
does not qualify target alignment, add temporal physics, or change the model's
blocked status.

The development-only perturbation study in `E-20260930-AI-470` renders six
previously unused arm states and measures the frozen AI-468 checkpoint under
33 predeclared joint crop/mask offsets. No training or evaluation group is
present. The nominal fresh-pose result already misses 9 of 108 abstentions.
At 1 mm, false stops range from 35 to 62 of 1,242 visible targets; at 2 mm the
worst direction reaches 272; and selected 4â€“8 mm directions cause near-total
stopping. This confirms that exact target alignment was a material assumption.
Future inference must bind calibrated localization uncertainty and abstain when
the safe-region fit is not supported; these synthetic offsets do not establish
a deployable millimetre bound.

The offset-augmented candidate in `E-20260930-AI-471` assigns one deterministic
nominal, 1 mm, or 2 mm translation to every v5 training row, then freezes its
threshold and uncertainty policy on the v6 development-only corpus. Nominal
misses improve from 9 to 3 of 108 while false stops rise from 35 to 44 of 1,242.
The worst 1 mm direction still misses 6 abstentions, so no nonzero bound meets
both 5% limits. The policy consequently supports only 0 mm and must abstain on
any nonzero localization uncertainty. Evaluation remains unopened. This is a
real safety improvement and an explicit fail-closed policy, but the zero bound
is operationally too strict and blocks a fresh evaluation campaign.

The frozen-weight policy refreeze in `E-20260930-AI-472` corrects the original
0.05 threshold-grid blind spot without retraining or opening evaluation. A
predeclared 0.001 grid selects threshold `0.093`. Across nominal and all eight
1 mm directions, the worst missed-abstention count is `4/108` and the worst
visible false-stop count is `62/1242`, both below 5%. The source and repeated
checkpoint state dictionaries are identical, and two complete policy outputs
are byte-identical. The resulting synthetic uncertainty bound is 1 mm;
anything larger must return `abstain_localization_uncertain`. The 2 mm ring
fails, and this result remains synthetic development evidence rather than
physical-camera calibration or deployment qualification. A fresh untouched
evaluation campaign may now be predeclared against the frozen policy.

The one-time fresh synthetic evaluation in `E-20260930-AI-473` interleaves six
previously unused actual-emitter schedule poses between earlier transit
samples and holds out three new lighting families. Its 1,350 rows contain 270
required abstentions and 1,080 visible targets. The frozen E-472 checkpoint
keeps the worst missed-abstention rate to `3/270 = 1.11%`, but nominal false
stops are already `83/1080 = 7.69%` and the worst 1 mm direction reaches
`96/1080 = 8.89%`. The synthetic evaluation gate therefore fails and the
checkpoint remains blocked. The consumed v7 group cannot tune a successor.
Failure concentration on persistent keyboard hard negatives, especially
`ENTER`, `EQUAL`, `MINUS`, and `0`, directs the next work toward a separately
predeclared development corpus and improved target-specific specificity while
preserving the low missed-occlusion rate.

The fresh development-only hard-negative campaign in `E-20260930-AI-474`
reproduces the v7 specificity failure without reusing evaluation images or
performing selection. Six new interleaved schedule poses and three related but
distinct lighting transforms produce 1,350 rows with 261 abstentions and 1,089
visible targets. At the frozen `0.093` threshold, the worst missed-abstention
rate remains `5/261 = 1.92%`, while the worst false-stop rate reaches
`110/1089 = 10.10%`. `ENTER`, `EQUAL`, and `MINUS` are false stops in every
nominal development image. This supports a specific next model change: add
explicit target identity or target-geometry features using separately declared
training data, select against v8 development only, and preserve the 5% missed-
occlusion ceiling. Any successor still needs a new untouched evaluation group.

The explicit target-identity experiment in `E-20260930-AI-475` retains that
next evaluation group unopened and records a failed architecture rather than
promoting it. Twelve fresh training-only arm poses crossed with three new
lighting transforms produce 2,700 rows. A 1,800-parameter model combines the
four-channel target crop with a 75-target one-hot identity and four normalized
catalog-geometry values, then selects only against v8 development. At threshold
`0.25`, nominal missed abstentions remain below 5% at `9/261`, but false stops
rise to `407/1089`; the worst 1 mm direction reaches `425/1089`. The selector
therefore returns a 0 mm bound and the candidate is blocked. This disproves the
idea that appending a fixed target descriptor to the current pooled visual
representation is sufficient. The next candidate should preserve local spatial
detail through target-conditioned feature fusion or attention and must continue
using v8 only for development before any new evaluation group is declared.

The target-conditioned spatial-fusion experiment in `E-20260930-AI-476`
implements that next architecture while keeping the next evaluation group
uncreated and unopened. It freezes the E-472 four-channel visual backbone and
classifier, then applies a 2,560-parameter FiLM conditioner to the local feature
map before spatial pooling. The conditioner receives the same frozen 75-target
identity and four catalog-geometry values used by E-475. Training uses only v9
and policy selection uses only v8. Two independent runs are byte-identical. At
threshold `0.107`, nominal development records `44/1089 = 4.04%` false stops
and `3/261 = 1.15%` missed abstentions; every predeclared 1 mm direction remains
below 5%, with worst rates `52/1089 = 4.78%` and `6/261 = 2.30%`. The synthetic
development gate therefore passes with a 1 mm bound. This is a model improvement
over E-475, but it is not evaluation, physical calibration, or deployment
qualification. The frozen candidate remains
`BLOCKED_AWAITING_FRESH_EVALUATION` until a new untouched synthetic campaign is
predeclared and consumed once.

The frozen one-time v10 evaluation in `E-20260930-AI-477` uses six schedule
poses and three lighting transforms absent from every v1-v9 campaign. Its
1,350 rows contain 249 required abstentions and 1,101 visible targets. The
exact E-476 checkpoint and threshold preserve the improved specificity: the
worst visible-target false-stop rate is `50/1101 = 4.54%`. Occlusion recall
narrowly fails the fixed ceiling: nominal misses are `12/249 = 4.82%`, while
the -1 mm x/0 mm y direction reaches `15/249 = 6.02%`. The synthetic gate
therefore fails and the candidate remains blocked. These v10 bytes are now
consumed evaluation evidence and cannot tune a successor. The result directs
future work toward a separately declared training/development campaign that
improves occlusion recall while retaining the demonstrated specificity; any
successor requires another untouched evaluation group.

The first frozen v11 render attempt failed closed before a receipt was created:
schedule samples 36, 37, and 39 carry identical joint states, so their official
mesh masks were not pose-distinct. The preserved status artifact has SHA-256
`7e09cfc4626774afd78ae160eed61ea30be1c91fe58ac7fcdcde09579231a3ec`, reports
zero hardware writes and zero physical movements, and is not admissible as a
dataset. The corrected campaign replaces duplicate development samples 37 and
39 with previously unused H-transit samples 30 and 32; every selected schedule
sample now carries a distinct joint state. The failed evidence remains part of
the ledger and is not rewritten by the correction.

The corrected v11 campaign and conditioner-only recall successor are recorded
in `E-20261001-AI-478`. Independent dataset and training builds are byte
identical. The frozen successor selects threshold `0.162`; nominal development
records `31/1104 = 2.81%` false stops and `11/246 = 4.47%` missed abstentions.
At +1 mm x/0 mm y, misses reach `13/246 = 5.28%`, so the candidate earns only a
0 mm synthetic uncertainty bound. It remains
`BLOCKED_AWAITING_FRESH_EVALUATION`; v10 was not reused, no evaluation group was
created or opened, and no arm or integration status changes.

The one-time v12 evaluation in `E-20261001-AI-479` preserves a narrow failed
specificity result for the exact E-478 checkpoint. Nominal alignment has zero
missed abstentions across 219 occluded targets, but false stops are
`57/1131 = 5.04%`, one case above the fixed 5% ceiling. Across the 1 mm stress
ring, missed-abstention rates remain at or below 2.28%, while false stops range
from 5.13% to 6.54%. V12 is now consumed evaluation evidence and cannot tune a
successor. No arm or integration status changes.

The v13 specificity-balanced successor was claimed in
`978b4ea184023c987b74db4f94c72172aad406a7` before implementation or rendering.
It reserves all thirteen remaining unused, pose-distinct schedule states: eight
for training and five for development. It creates no evaluation group. Six new
lighting transforms, exact E-478 seeding, conditioner-only optimization, twelve
epochs, learning rate `0.00025`, ordinary binary cross entropy, and development
only threshold and uncertainty selection are frozen before image generation.
The campaign identities and objective are independent of the identities inside
the consumed v12 evaluation; no v12 byte, label, pose, or lighting transform is
admissible for training or selection.

Evidence `E-20261001-AI-480` records byte-identical dataset and training
repeats. Threshold `0.406` passes fresh synthetic development at nominal
alignment with `9/204 = 4.41%` missed abstentions and `11/921 = 1.19%` false
stops. All eight directions at 1 mm and 2 mm remain below both fixed 5%
ceilings; the worst 2 mm rates are `9/204 = 4.41%` missed abstentions and
`36/921 = 3.91%` false stops. The 4 mm ring fails, so the selected synthetic
bound is 2 mm. The result remains `BLOCKED_AWAITING_FRESH_EVALUATION`, carries
no physical calibration or authority, and does not change arm or integration
status.

The AI lane predeclares v14 under claim commit
`1c8e31c334dac2983d039301fe1703bb658c1077`. Six evaluation-only static visual
poses are frozen at rational fractions `2/19`, `5/19`, `8/19`, `11/19`,
`14/19`, and `17/19` of the exact zero-authority source schedule. The retained
fixture file SHA-256 is
`638e17a18feb79aa15864078ff80df37e69ebe6889710de08d98ed709013fb69` and
its canonical bundle SHA-256 is
`93b77619af1bb90a3261b36cdbd7a209c3ac5bddf3b8a26b05fa2ae2b4625985`.
The three evaluation lighting identities are `neutral_edge_soft`,
`amber_lower_falloff`, and `cross_smear_cool`. Evaluation is bound to the exact
E-480 model SHA-256
`b20a02990d47ee87d97383d130052c4517391442d517ea94b5b5e78749a7525d`,
canonical scorecard SHA-256
`d11a71c67e2f7072e52a4a28d9c2bdbf5f6da308c5704bfe47a379c79cad9f00`,
threshold `0.406`, and declared synthetic 2 mm bound. The 4 mm ring is stress
evidence only. Rendering cannot begin until this policy is committed. V14
allows no training, selection, threshold change, model mutation, bound
expansion, arm authority, or physical qualification; its data is consumed by
the single evaluation.

Evidence `E-20261001-AI-481` records the untouched v14 failure. The render
contains six poses and the evaluation contains 1,350 rows: 219 expected
abstentions and 1,131 visible targets. Nominal missed abstentions are
`24/219 = 10.96%`, while nominal visible false abstentions are
`21/1131 = 1.86%`. Within the declared 2 mm envelope, the maxima are
`31/219 = 14.16%` missed abstentions and `62/1131 = 5.48%` false abstentions,
so the fixed 5% synthetic gate fails. The 4 mm stress ring also fails. Both
dataset builds and both evaluation reports are byte identical. V14 is now
consumed and cannot tune a successor. The result grants no deployment,
integration, or physical authority and leaves arm-lane status unchanged. The
next AI dependency is a newly predeclared train/development campaign designed
for pose generalization; it must exclude all v14 images, labels, probabilities,
threshold outcomes, pose identities, and lighting identities from selection.

### Pose-diverse v15 successor result

Evidence `E-20261001-AI-489` records the frozen v15 training/development
campaign. Ninety-six fresh static visual states were generated from the
governed zero-authority schedule, partitioned into 72 training poses and 24
development poses. Six new lighting identities were used, v14 bytes and pose
fractions remained excluded, and the evaluation split remained empty. Two
independent 292-file dataset trees and two independent model/scorecard builds
are byte identical.

The learned target-visibility candidate improved nominal development behavior:
at threshold `0.141`, missed abstentions are `5/786 = 0.64%` and visible false
abstentions are `146/4614 = 3.16%`. Point estimates pass the predeclared 2% miss
and 10% false-stop limits through the 1 mm synthetic offset ring. The
authoritative seeded whole-pose bootstrap does not pass: worst missed-abstention
one-sided 95% UCB is `3.2491%`, above the 2% ceiling; worst false-abstention UCB
is `7.1350%`, below 10%. Status is `FAILED_DEVELOPMENT_GATE`. The internal
point selector's 1 mm result is not an installable uncertainty qualification
because the cluster gate failed. No evaluation set was opened or consumed.

This result improves the evidence base. Raw misses are lower on v15 development
than on the differently constructed v14 evaluation, but that is not a
controlled head-to-head improvement claim. The learned model remains
unreliable across pose clusters. The geometry-first architecture is unchanged:
deterministic synchronized self-occlusion
projection remains the primary path, with learned perception reserved for
residual obstructions and image failures. Localization remains separately
blocked by its retained `14.400834977 mm` synthetic bound. Arm-lane status and
all integration gates remain unchanged.

### V15 pose-cluster development diagnostic

Evidence `E-20261001-AI-490` attributes the failed clustered gate using only the
consumed v15 development rows and scorecard. Across the nine offsets inside the
selected 1 mm ring, the scorecard contains 58 missed abstentions. Seven of 24
pose clusters contain any miss, across eight pose-target pairs. One pair,
`pose_diverse_development_016` and `MINUS`, contributes 27 misses (`46.55%`)
and repeats under all three development lighting transforms. The two highest
miss poses contribute `70.69%` of all in-bound misses. The worst clustered
offset remains `(-1,+1) mm`, with missed-abstention UCB `3.2491%`.

This concentration explains why row-level results looked good while the
whole-pose bound failed. It does not prove that repairing those two poses will
generalize. V15 development is consumed design evidence and cannot select or
evaluate v16. A successor must use fresh train/development identities, group
nearby source intervals into the same split, cover fresh neighborhoods around
the failed intervals, balance the observed failed target identities, and
freeze its architecture, split, training, bootstrap seed, and gates before
rendering. The v15 threshold and checkpoint remain unchanged and rejected. No
evaluation source was opened, no render was started, and deterministic geometry
projection remains the primary known-self-occlusion path.

### V16 grouped-neighborhood successor predeclaration

The v16 design is frozen before Isaac rendering. Fixture file SHA-256
`0e0f30a801a38720f0dc6ddc5b769c8447dda09a67a8577ddf37fd7fffb5abae`
and canonical bundle SHA-256
`21af4a14ed154d2cecd07cc995ea6c497fd356ef85d9181cf012885f924b2fa5`
bind 256 training and 64 development poses. Three-interval source blocks are
kept wholly within one split, and a one-block buffer separates every training
block from every development block. The seven blocks implicated by the
consumed v15 diagnostic are training-only. Exact v15 pose fractions are
excluded. There is no evaluation split.

The fresh training lighting identities are `grouped_neutral_drift`,
`grouped_left_warm_falloff`, and `grouped_right_cool_occluder`. Development
uses `grouped_overhead_low`, `grouped_side_glare`, and `grouped_soft_focus`.
They are deterministic and disjoint from v15. The successor will seed exact
v15 model SHA-256
`9e09a13fae22cbbc75d2b15d9fe2e9cfbf76638d61220d635dd31272e298cfbb`,
train `conv2`, `conditioner`, and `classifier` for 12 CPU epochs at learning
rate `0.00015`, positive abstention weight `1.75`, and weight decay `0.0001`,
and retain `conv1` frozen. Rows for `MINUS`, `U`, `7`, `1`, `0`, `PERIOD`, and
`6` receive a fixed `2.0` target emphasis. These choices cannot be revised
after render evidence is observed.

Development policy selection retains the 2% missed-abstention and 10%
visible-target false-abstention ceilings, nine declared offsets through the
selected synthetic uncertainty ring, and a 2,000-resample whole-pose
one-sided 95% bootstrap with seed `19016`. Both point and clustered gates must
pass. V14 evaluation and v15 development remain consumed design evidence and
cannot select or evaluate v16. A pass would remain synthetic research, with
zero controller authority, zero hardware writes, and zero physical movement.

The committed implementation evaluates every declared offset inside the
selected ring: nine offsets at 1 mm or 17 offsets at 2 mm. The earlier phrase
"nine declared offsets" described the 1 mm case too narrowly; it did not alter
the committed selector. V16 selected 2 mm and therefore conservatively scored
all 17 offsets.

V16 is complete and rejected. The inert Isaac run retained 320 poses and 60
chunked atlas artifacts. Two independent 964-file dataset builds are byte
identical, with 57,600 training rows, 14,400 development rows, and no
evaluation rows. At threshold `0.138`, nominal development has 12 misses among
2,118 abstention rows (`0.5666%`) and 233 false stops among 12,282 visible rows
(`1.8971%`). Point estimates pass through the selected 2 mm ring. The
authoritative 64-pose bootstrap reports worst missed-abstention UCB `2.8216%`
and worst false-abstention UCB `7.8025%`. The miss bound remains above 2%, so
`development_gate_met=false` and status is `FAILED_DEVELOPMENT_GATE`. This is
directionally lower than v15's `3.2491%` clustered miss bound, but the datasets
are different and do not support a controlled improvement claim. No evaluation
source was opened and no runtime qualification or authority changed.

### V16 grouped-neighborhood development diagnostic

The rejected v16 development split now has a deterministic, read-only failure
diagnostic. Across the 17 offsets inside the frozen 2 mm ring it records 348
missed abstentions and 6,243 false abstentions. Misses occur in 28 of 64 poses,
46 pose-target pairs, eight source blocks, 13 targets, and all three lighting
identities. The largest pose-target pair (`grouped_development_064` / `P`)
accounts for only 41 misses (`11.7816%`), while the three largest source blocks
account for 264 of 348 (`75.8621%`). The worst clustered miss offset remains
`(-2 mm, 0 mm)`, with missed-abstention UCB `2.8216%` and visible-target
false-abstention UCB `1.9722%` at that offset.

This distribution is broader than the concentrated v15 failure and does not
support patching one target or changing the threshold. It directs any learned
successor toward a fresh, predeclared pose-geometry design while synchronized
deterministic geometry projection remains the primary known-self-occlusion
path. The diagnostic used only the consumed development rows and scorecard: it
loaded no images, ran no inference or training, opened no evaluation source,
and grants no qualification, controller authority, or physical authority.

### V16 geometry-first fusion replay

The consumed v16 development set now has a deterministic geometry-first replay.
It independently reloads and hashes all four development robot-mask atlases,
recomputes center coverage and safe-region overlap for 4,800 pose-target pairs,
reconciles all 14,400 lighting rows, reconstructs the frozen learned decisions,
and applies conservative geometry OR learned abstention across all 17 offsets in
the selected 2 mm ring. The replay contains 54 ambiguity-band rows. At nominal
offset the learned path's 12 misses become zero after fusion, with 233 strict
false stops (`1.8971%`) and 218 when either ambiguity-band answer is accepted
(`1.7750%`). Across the ring the worst fused result is zero misses and 881
strict false stops (`7.1731%`), or 866 (`7.0510%`) with the frozen ambiguity
scoring rule.

This result validates the intended architecture seam: deterministic known-robot
geometry can conservatively cover self-occlusion misses while the learned path
remains a second abstention source. It is not an independent accuracy result.
The same Isaac semantic mask produced both the replay geometry and the synthetic
label, no measured dilation was applied, and no synchronized measured-feedback
projector or projection qualification is installed. V16 remains rejected as a
learned checkpoint. The next meaningful evidence must use commissioned camera
geometry, exposure-time measured feedback, measured dilation, and residual
obstruction cases that are independent of the geometry label.

### Frozen parked residual-obstruction pretraining campaign

The residual learned path now has a deterministic pretraining contract before
any crop generation or training. It binds the exact retained fixed-camera
practice manifest, corpus, target catalog, and source image hashes, then defines
1,200 target-centered 96 by 96 crop specifications over all 75 keyboard targets.
Training uses only `hover_t`; development uses only `hover_e`; evaluation is
empty. Each split has 600 specifications: two visible cases per target (clear
and adjacent distractor) and six abstention cases per target (cable, tool, hand,
foreign object, localized glare, and image degradation). The retained fixture
contains procedural render specifications, not generated crops.

The frozen offline model is `target_crop_residual_cnn_v1` with convolution
channels `[16, 32, 64]`, 12 epochs, batch size 64, learning rate `0.0005`,
weight decay `0.0001`, and seed `19017`. Development selection must use the
predeclared threshold grid from `0.05` through `0.95` and pass both point and
2,000-resample target-cluster bounds: missed-abstention upper bound at most 2%
and visible-target false-stop upper bound at most 10%. Truth masks and runtime
geometry masks are prohibited as model inputs. A second build was byte
identical; canonical fixture SHA-256 is
`06f3972c71fa4132083cd963285824d49577eaf933cab4e411da84224a2ebfef`.

This is a frozen synthetic design, not evidence that the residual detector
works. The two source views are correlated, surfaces are simplified, and the
camera remains synthetic and unmeasured. No images, model, training,
development result, evaluation source, qualification, controller field,
hardware write, physical movement, or execution authority was produced. The
next increment must generate the exact declared crops, independently inventory
them, train the declared model, and apply the target-cluster development gate
without opening evaluation.

### First residual-obstruction development result

The frozen campaign was executed without changing its variants, splits, model,
training parameters, threshold grid, or gates. Two independent materializations
produced the same 1,200-file inventory and dataset SHA-256
`a6188e5ae191e2bfc71dae37ee26f174d5a056d3d4958ae7c2f472ef9bff2830`.
Independent verification reopened every declared file, checked its hash, size,
metadata, dimensions, containment, and exact no-extra-file inventory. The crop
trees and model weights remain external artifacts; the strict development
scorecard is retained in the repository.

Two deterministic CPU training runs produced identical 95,797-byte model
artifacts with SHA-256
`90d32245902a20653e829627772d78604bd8c11880bc5be1c54bf14343831946`.
The candidate failed the frozen development gate, so no threshold was selected.
At threshold `0.75`, it misses 126 of 450 obstruction rows (`28.0%`) and falsely
stops 40 of 150 visible rows (`26.67%`); target-cluster upper bounds are
`32.67%` and `36.0%`. At `0.80`, false stops fall to 2 of 150 (`1.33%`, 4.0%
upper bound), while misses rise to 363 of 450 (`80.67%`, 85.56% upper bound).
No threshold in the declared grid satisfies both the 2% missed-obstruction and
10% visible-false-stop limits.

This is useful failed evidence: the first model does not transfer obstruction
separation from `hover_t` to `hover_e`, and threshold adjustment cannot repair
the overlap. The checkpoint remains rejected; evaluation stays unopened. The
next increment should diagnose the consumed development probabilities by
variant and target, then predeclare a fresh pose- and appearance-diverse
successor rather than modifying this candidate after observing its result.

### First residual-obstruction failure diagnostic

The exact rejected model was decoded from its deterministic binary artifact and
rerun against the consumed development crops. Reconstructed probability and
identity hashes match the retained scorecard. The aggregate pairwise AUC is
`0.7585185`. Visible probabilities span `0.7144125` to `0.8022025`; obstruction
probabilities span `0.6787802` to `0.9071497`. All 75 targets are locally
nonseparable: each target's lowest obstruction probability is below its highest
visible probability. Separation margins range from `-0.0380050` to
`-0.0008761`, so this is not one bad target or keyboard region.

The diagnostic also exposed a dataset construction defect. All 75 development
`none_adjacent_distractor` PNGs are byte identical to their corresponding
`none_clear` PNGs; their probabilities are consequently identical. The planned
distractor fell outside the generated crop and provided no negative example.
Among obstruction variants, `image_degraded` has the lowest mean probability
(`0.7340675`) and only 17 of 75 rows abstain at threshold `0.75`; none abstain at
`0.80`. Cable and tool cases also overlap substantially, while localized glare
is the only obstruction family with all 75 rows abstaining at `0.75`.

This diagnosis uses consumed development evidence and cannot select or evaluate
a successor. It does show what the next predeclaration must fix: prove every
adjacent distractor changes pixels while preserving zero target overlap; add
multiple group-separated source poses and appearances; and broaden degradation,
cable, and tool severity. The rejected checkpoint and threshold grid remain
unchanged, and evaluation remains closed.

### Residual-obstruction successor v2 freeze

Successor v2 is frozen before rendering. It defines six training and three
development parked-camera perturbation groups with disjoint identities, crossed
with four training and three development appearance groups whose identities are
also disjoint. Fifteen variants cover clear, left/right adjacent distractors,
three cable widths, two tool placements, hand, foreign object, glare, two blur
levels, compression, and motion degradation. Across the retained 75-target
catalog this yields 27,000 training and 10,125 development observations;
evaluation remains empty.

The renderer must reject a campaign unless every adjacent distractor differs
from its paired clear crop by at least 64 pixels while retaining exactly zero
safe-region overlap. Declared obstruction masks must satisfy their frozen
overlap bands, every variant must appear in every view, and duplicate
observation bytes fail admission. Truth and geometry masks are retained only
for labels and cannot enter the model. The crop margin increases from 1.5 to
2.5 so an adjacent distractor can remain visible without touching the target.

The successor remains small and offline: RGB-only
`target_crop_residual_cnn_v2`, channels `[16, 32, 64]`, 18 epochs, batch size
128, deterministic label/variant balancing, learning rate `0.0003`, weight
decay `0.0001`, and seed `19018`. Development must pass both point and
2,000-resample whole-view clustered upper bounds, including the maximum across
development appearances: at most 2% misses and 6% residual-path false stops.
This unrendered synthetic design has no measured performance, camera
qualification, deployment status, or physical authority.

### Geometry-first occlusion revision after v14

The next campaign treats known robot self-occlusion as a deterministic
projection problem. Measured joint feedback synchronized to the frame exposure,
a commissioned camera model, the camera-to-board transform, and pinned official
visual meshes produce a conservative image-space robot silhouette. The frame
binds its exposure timestamp and clock identity to measured-feedback samples
that bracket exposure and to a qualified interpolation rule. Latest telemetry,
commanded positions, an unsynchronized clock, or a sample gap outside the
qualified limit cannot substitute and requires abstention. The projection is
evaluated against the requested target's safe region across the installed joint
and calibration uncertainty envelope. This output is perception evidence only
and cannot claim collision clearance, reachability, a trajectory, a permit, or
physical authority.

The learned model becomes a residual obstruction detector for evidence that
the robot geometry cannot predict, including cables, hands, glare, foreign
objects, and image degradation. The fusion rule is conservative OR: abstain if
the deterministic projection or learned detector says abstain, or if either
input is stale or unqualified. Simulator truth masks are labels only.
Runtime-like model features must be projected from telemetry and estimated
calibration while training and evaluation perturb joint feedback, intrinsics,
distortion, and extrinsics within predeclared ranges.

Projection dilation is measured rather than guessed. Qualification propagates
ChArUco reprojection residuals, measured joint-feedback resolution and noise,
and observed directional backlash and parked-pose repeatability through the
same mesh projection. It freezes the resulting conservative image-space bound,
source-artifact hashes, and applicable camera/robot domain. A hand-selected
pixel margin is not qualifying evidence.

For existing synthetic evidence, `sufficiently visible` means the official
rendered robot does not cover the target center and covers no more than `0.20`
of the target safe-region area. Coverage above `0.20` or center coverage is an
abstention label. This historical boundary remains attached to E-457 through
E-481. The successor freezes `[0.18, 0.22]` as a narrow overlap ambiguity band
before generation. Center coverage always requires abstention. For an uncovered
center inside the band, either decision is accepted for binary classification
scoring, but the row remains in dataset totals, pose-cluster resampling, and
reports. Every band row is reported with pose, target, lighting identity,
overlap, label, and decision, together with the band count and fraction. The
band cannot be widened after data is observed or remove any outside-band error.

Future qualification gates use pose clusters rather than treating target and
lighting rows from one pose as independent. The fused-system synthetic research
gate is asymmetric:

- the one-sided 95% upper confidence bound for missed abstentions must be at
  most `0.02`;
- the one-sided 95% upper confidence bound for visible-target false abstentions
  must be at most `0.10`;
- on that same set, the geometric path's false-abstention upper bound must be at
  most `0.04` and the residual path's must be at most `0.06`; because both may
  stop the same row, these shares constrain contributors but do not replace or
  arithmetically prove the authoritative fused `0.10` gate;
- a deterministic, seeded pose-level cluster bootstrap resamples complete poses
  and computes the maximum rate across every tested offset inside the declared
  error envelope on each replicate, providing simultaneous worst-offset
  coverage rather than separate uncorrected tests; and
- point estimates remain reported but cannot pass the gate by themselves.

The next broad-pose evaluation budget is frozen before generation. Sixty-four
independent pose clusters is a planning floor, not an assertion of adequate
power. The power tool first estimates intra-pose correlation from grouped
v13/v14 diagnostics without exposing their target, pose, lighting, probability,
or failure identities to candidate selection. It runs both the empirical
one-sided 95% upper correlation bound and a pessimistic correlation equal to the
larger of that bound and `0.30`. Pose count increases above 64 until a frozen
design has at least 90% simulated probability of passing both fused upper-bound
gates at predeclared design rates of 1% misses and 6% false stops. The set also
contains at least 800 abstention-labeled observations and 3,200 visible
observations, with pose and lighting identities disjoint from training and
development. The exact power code, assumptions, sample-size curve, random seed,
perturbation ranges, and one unrendered escrow family are frozen before
rendering. One primary set is opened once for one frozen candidate. A failed
primary set is consumed and cannot tune that candidate or a successor.

Physical calibration begins in parallel rather than after synthetic model
selection. Initial work captures ChArUco observations for intrinsics,
distortion, and camera-to-board pose, plus a small measured lighting survey and
parked-pose image set. These artifacts inform perturbation ranges and lighting
augmentation but do not install deployment qualification by themselves. The
first physical interaction protocol parks and settles the arm before each
capture, admits at most one action from that evidence, then retracts and
recaptures. Keyboard host events and development-mode phone ADB state are
independent outcome labels when available, not movement authority.

The first milestone has a separate parked-pose qualification set. Synthetic
variants span the measured calibration and lighting envelopes around the exact
park state. Physical evidence contains at least 30 independent completed park
and settle cycles across at least three sessions, with measured repeatability,
per-session ChArUco drift, residual tool/cable obstruction, every fused decision,
exact binomial confidence bounds, and false stops reported. It accepts no known
self-occlusion and abstains on every labeled residual obstruction. This small
set supports only a supervised parked-observation milestone. It neither passes
the broad-pose research gate nor qualifies mid-motion observation, unattended
deployment, or physical authority. The correlation-sized broad-pose campaign
is retained as the later mid-motion gate.

Byte-identical builds and reports demonstrate deterministic pipeline behavior.
They do not establish that an observed failure rate is statistically stable.
Statistical claims require the clustered uncertainty analysis above.

The claimed correlation-aware planning tool is now implemented against the
retained v13 development and frozen v14 evaluation artifacts. It reconciles
their exact dataset, manifest, report, target-catalog, confusion, and failure
identities internally, then emits only aggregate hashes and statistics. Across
the 17 offsets inside the component-wise 2 mm envelope, the maximum seeded
pose-bootstrap 95th-percentile ICC is `0.767574770` for missed abstentions and
`0.024507274` for visible false stops. The pessimistic scenario therefore uses
`0.767574770` and `0.30`. At the frozen 1%/6% design rates and fused 2%/10%
limits, the 64-pose floor has zero joint planning power in both scenarios. The
first tested size reaching at least 90% joint planning power in both is 2,048
poses (`0.936` empirical and `0.927` pessimistic). This is a broad synthetic
mid-motion planning result; it neither opens a new evaluation set nor replaces
the separate parked-pose synthetic and physical qualification.

The parked-pose protocol is now structurally implemented without fabricating a
campaign. Its strict campaign binds the commissioned park identity, camera and
board geometry, projection qualification, residual model, fusion policy,
repeatability and ChArUco qualifications, runtime-like synthetic projections,
and authorized physical collection effects. Physical completion requires at
least 30 settled park cycles across at least three sessions plus visible, known
self-occlusion, cable, and tool cases. Both geometric and residual paths must
detect their assigned hazards, and conservative OR fusion is rederived rather
than trusted. The evaluator reports exact two-sided 95% Clopper-Pearson bounds.
The retained receipt remains `INCOMPLETE` with `campaign_not_collected`; it has
no campaign identity, writes, movements, authority, or deployment claim.

The file-backed parked-pose preflight is also implemented. It derives the exact
artifact set from the campaign instead of trusting an index-provided list, then
requires one unique contained regular file for every configuration, policy,
model, image, projection, truth label, exposure binding, measured-feedback
bracket, residual observation, ChArUco capture, repeatability record, drift
record, collection authorization, and custody review. SHA-256, size, artifact
type, and declared custody must all match. Extra, missing, duplicate, altered,
traversing, or symlinked artifacts fail closed, including nested symlinks. The
retained preflight remains `BLOCKED` by `campaign_package_not_retained` and
contains no invented campaign or custody identity.

The deterministic retained-package index builder is also implemented. It takes
one frozen campaign, one separately authored and self-hashed custody-declaration
document, and an exact evidence directory. It rejects missing, extra, empty,
duplicate-content, changing, non-regular, or symlinked files, verifies exact
campaign and custody coverage, and emits the same strict index consumed by the
preflight. The builder derives artifact types from the campaign but never
creates evidence bytes or assigns custody. Declaration and custody-review
authenticity remain external owner responsibilities.

The residual v2 crop campaign is now rendered under a contract committed before
generation. The contract binds the exact `hover_t__nominal` image, ordered 75
target identities, deterministic planar affine camera approximation, raster
rules, and fail-closed admission. Two independent external builds each produced
37,125 crops plus one manifest, used 329,046,332 bytes, and yielded identical
manifest file SHA-256 `8ab18548adb510943bcb39e8d16653334f17710ae6d4780ae2bc4ca6fbec9f84`
and canonical dataset SHA-256
`0328262ed2eaffb56895f39a9b975044c84f9be4d7a5b8006981601ebce43d0a`.
All 37,125 crop hashes are unique. Adjacent distractors change at least 793
pixels while retaining zero safe-region overlap, and every obstruction overlap
falls inside its predeclared range. This proves deterministic synthetic dataset
construction and admission only. It provides no model metric, physical realism,
camera qualification, deployment qualification, or execution authority.

The frozen RGB residual CNN v2 has now been trained twice against that corpus.
Both deterministic CUDA runs produced model SHA-256
`0f5982b6af2761ce367837c35094647cfa5711f1fd042ede36650ba9306a1367`
and scorecard SHA-256
`a82755040aec805a68aea263c86d24c07ce03657c6756999041c4977beac548a`.
Training loss fell from `0.690973293` to `0.413303573`, but every frozen
threshold failed development. At threshold `0.20`, the overall missed-
obstruction rate is `6.9877%` and visible false-stop rate is `37.4321%`;
worst-appearance rates are `18.7037%` and `54.2222%`. No threshold was
selected, evaluation remains absent, and the candidate is rejected.

The consumed residual v2 development split has now been diagnosed without
changing the checkpoint or threshold. Exact CUDA reconstruction reproduces the
frozen probability hash. Overall pairwise AUC is `0.897529706`, but all 75
targets have overlapping visible and obstruction score ranges: the best local
separation margin is still negative at `-0.202038795` and the worst is
`-0.785702050`. At threshold `0.20`, cool appearance supplies 505 of 566 missed
obstructions, while shadow and sensor-noise appearances supply 366 and 282 of
758 visible false stops. Clear crops supply 537 visible false stops;
compression, cable, and tool variants supply most obstruction misses. The
evidence supports a fresh design with independent base scenes, explicit
appearance-invariance training, and physically shaped obstruction variation.
It does not support threshold adjustment, evaluation opening, or promotion.

Residual v3 is now frozen before rendering. It requires 12 fresh Isaac 3D base
scenes with disjoint 8-scene training and 4-scene development groups; source
image warping is prohibited. Twelve target-crop variants cover visible cases,
mesh cables, matte/gloss tools, foreign objects, optical glare, defocus, motion
blur, and compression across four paired physically based appearances. The
small offline RGB model plan adds paired-logit appearance consistency, while
the development gate retains asymmetric error ceilings and adds worst-family,
worst-appearance, clustered-scene, and strictly positive per-target separation
requirements. This is a synthetic predeclaration: no v3 image, model, metric,
evaluation source, or qualification exists yet.

The first residual v3 renderer increment now translates that frozen contract
into target-local Isaac Sim render products with bounded target sharding and
measured semantic/depth overlap admission. A deliberately small smoke rendered
192 unique RGB observations for one frozen scene, four targets, four paired
appearances, and 12 variants. All declared overlap bands passed. This is only a
renderer and admission smoke: 11 scenes and 71 targets remain unrendered, the
43,200-observation corpus has not been independently merged or admitted, and no
v3 training or evaluation has begun.

Independent shard admission now rereads the frozen fixture and target catalog,
recomputes every manifest and image hash, checks exact scene/appearance/variant/
target identities, validates depth and overlap evidence, rejects duplicate bytes
and extra files, and requires all 43,200 combinations before setting
`campaign_admitted=true`. Applied to the smoke, it correctly returns `PARTIAL`:
192 combinations verified and 43,008 missing. Its default complete-campaign mode
rejects that same input, so partial render evidence cannot unlock training.

The first attempt to extend the renderer across all 12 scenes exposed and
preserved a duplicate USD transform failure at the scene boundary. Dynamic
obstruction prims are now scoped and removed per scene, and the status receipt
is flushed before Isaac shutdown. The repaired target 0â€“3 shard completed all
12 scenes and independently verified 2,304 unique observations. This advances
the corpus to one complete target shard while the overall campaign remains
`PARTIAL` with 40,896 combinations missing.

The next shard exposed a target-aspect-ratio defect before admission: the round
foreign object covered only 0.3092 of the wide `ENTER` safe region, below the
frozen 0.35 minimum. The renderer now scales a rounded ellipsoid to both target
dimensions. A fresh four-target smoke measured `ENTER` at 0.5342 and the other
targets at 0.5425â€“0.545, all inside the unchanged 0.35â€“0.70 band. The failed
shard remains preserved and is excluded from admission.

Wide-target rendering then failed closed on `SPACE`: the fixed 82 mm camera
height clipped its 96 mm safe region, making a nominal partial tool appear to
cover 100%. Camera height now grows deterministically with the larger target
dimension while retaining the original height for standard keys. A fresh
four-target smoke measured `SPACE` tool overlap at 0.7179 and foreign-object
overlap at 0.5192, both inside the unchanged contract bands.

The first phone-key shard then failed closed because the 6Ã—11 mm `key_a`
quantized a matte edge tool to 0.5455 overlap. Small-target camera height and
both tool footprints now normalize to target dimensions with margin inside the
original bands. A fresh mixed keyboard/phone smoke measured matte-edge overlap
at 0.38â€“0.455, centered-tool overlap at 0.70â€“0.727, and rounded-object overlap
at 0.54â€“0.568. No admission limit was widened.

The 6Ã—10 mm `key_period` then exposed the remaining centered-tool pixel margin:
0.8333 against the frozen 0.80 maximum. Reducing centered-tool width from 65%
to 55% produced 0.583â€“0.636 centered overlap, 0.333â€“0.455 edge overlap, and
0.55â€“0.573 rounded-object overlap across a fresh four-phone-key smoke. The
failed shard remains excluded and the original acceptance bands remain fixed.

The complete residual v3 corpus now passes independent exact-set admission. All
43,200 frozen observations are present and byte-unique across 19 retained
shards: 28,800 training, 14,400 development, and zero evaluation observations.
The retained lineage binds every shard manifest to the renderer commit that
produced it. This completes synthetic rendering and admission only; training
has not started and no physical or deployment qualification follows from it.

The bounded residual v4.1 reference-pair smoke now verifies 192 unique training
observations for keyboard targets F, G, H, and I against four independently lit
clear references. On this shard, independent self-crop normalization has pooled
AUC 0.8038194444 and the current reference-context transform has 0.7743055556.
The result does not select preprocessing; both channels remain candidates for
fresh development evidence. Commissioned-reference validity now abstains on
age, camera-calibration, fixture-pose, target-map, or lighting mismatch, and the
first real clear/cable/hand reference-pair collection is documented. No model
training or evaluation access occurred.

Residual v4.2 now freezes the campaign decision before development rendering.
Both self-crop P05/P95 and reference-context white-point normalization retain a
zero-parameter mean-absolute-difference baseline. The higher linear q05 target
AUC selects normalization; differences within 0.005 choose self-crop by a fixed
simpler-runtime tie break. Two otherwise identical CNNs must first pass the
500-row memorization gate. The selected CNN must improve both pooled AUC and
q05 target AUC by at least 0.02 over its corresponding baseline, in addition to
all existing development safety gates. Evaluation remains unrendered.

The v4.2 sharded Isaac renderer and independent admission path now pass a
one-scene, four-target training smoke. All 192 unique observations and four
references reconcile with the frozen fixture and overlap bounds. Admission is
correctly `PARTIAL`, with 43,008 training and 28,800 development observations
missing, so it cannot unlock training. Evaluation remains absent.

An early visual and contract audit stopped the first full render attempt before
development admission: the renderer used ±6 mm X/Y camera jitter while the
fixture freezes ±3 mm and omitted explicit Z/rotation sampling. The completed
2,304-row shard and two partial directories are retained but excluded. Visual
review confirmed all reference/observation lighting pairs differ and cables,
edge/center tools, foreign objects, glare, defocus, motion blur, and compression
affect the intended pixels. The corrected renderer samples and records all three
position and rotation axes; a fresh 192-row smoke passes independent admission.

The first corrected complete training shard and the first disjoint development
shard have now passed independent partial admission and visual review. They add
2,304/48 and 1,536/32 observation/reference rows respectively, with unique RGB
content, reference-consistent camera bindings, bounded six-axis jitter, and the
declared effects visible in both commissioned-reference and same-light
difference sheets. Two queue-script range mistakes are retained as failed
external evidence. The repaired two-GPU queue reuses the two valid training
shards and writes every remaining shard to fresh `camera04` paths. Complete
admission, training, normalization selection, and development scoring remain
pending; evaluation remains absent.

**2026-10-02 pre-result amendment:** the v4.2 fixture and its frozen camera
bounds did not change. The renderer implementation was corrected to conform to
those already-frozen bounds before any development metric, normalization
selection, or model result was observed. Final admission uses an explicit
38-shard allowlist. Each allowed path must match its split, scene shard, target
shard, renderer receipt, dataset SHA-256, and manifest file SHA-256 before the
ordinary row/image hash admission runs. Preserved `camera02` and failed
`camera03` paths are absent from that allowlist.

Post-admission gate tooling is now frozen while rendering continues. Complete
admission must reproduce the exact manifest inventory before a deterministic
500-row, label-balanced, target-round-robin training subset can be emitted.
The same 6x6 spatial CNN is then memorized separately for both frozen
normalizations. Development baseline scoring refuses to open its rows unless
both memorization gates pass and bind to that exact preparation receipt. The
training-free baseline uses the renderer-bound difference metrics, linear
fifth-percentile per-target AUC, the frozen 0.005 tie band, and the frozen
self-crop tie break. Evaluation remains inaccessible.

**2026-10-03 post-render decision:** both render queues and the independent
exact-allowlist admission pass. The admitted corpus contains 64,800 unique
observations and 5,400 references, split as 43,200 training and 21,600
development rows, with evaluation still unopened. The separately frozen
144-pair raw/JPEG/YUY2 comparison fails without changing its limits. JPEG
preserves contrast ranking but exceeds the median, q95, and worst-row
codec-distortion-to-signal ceilings; YUY2 exceeds its q95 and worst-row
ceilings. The corpus is therefore retained as exploratory evidence and v5.4
candidate training is blocked. The next synthetic increment must predeclare a
lossless or camera-format-aware replacement corpus; physical camera capture
remains required before any transfer or deployment claim.

**2026-10-03 post-failure attribution:** the frozen codec failure remains
unchanged, but its cause is now separated from camera-domain detectability.
The worst YUY2 distortion ratio comes from a 10% coverage row labeled visible
whose raw RGB difference is only 0.531 intensity levels; YUY2 retains 110.3%
of that RGB difference and 101.7% of its edge difference. Across the 96
safety-relevant 30%/60% abstention rows, YUY2 retains every measured signal,
but three delivered RGB differences remain below two intensity levels and five
remain below three. The replacement must train from lossless renders converted
to simulated YUY2 and evaluate detectability in that delivered domain. It must
report near-zero signals separately and cannot invent a physical detectability
floor before the real-camera cable pilot.

**2026-10-03 delivered-frame noise amendment:** the replacement camera-domain
pipeline must also represent physical sensor noise. The de-energized B0477
pilot now freezes 32 retained full-native YUY2 frames after eight discarded
settling frames at each measured low, nominal, and high lighting condition,
with the scene, pose, optics, exposure, gain, and white balance fixed within
each burst. It reports per-pixel temporal Y/U/V standard deviation and robust
sigma, spatial maps, empirical residuals, adjacent-frame differences, dropped
or duplicate frames, and clipped pixels. The next synthetic corpus must begin
with lossless renders, contain no JPEG intermediate, and reproduce measured
delivered-YUY2 noise while preserving observed spatial and chroma dependence.
No signal floor, noise multiplier, or sub-floor decision is selected before
the physical measurements are reviewed. This is a predeclaration only: camera
captures, hardware writes, physical movements, training runs, and evaluation
images remain zero.

**2026-10-03 planner modifier decision:** the deterministic planner selects
commissioned Sticky Keys as the first physical-keyboard strategy. The arm will
press `SHIFT` and the base key sequentially and will never attempt a
simultaneous chord. The current 46-target keyboard catalog contains neither a
`SHIFT` nor `CAPS_LOCK` target, so uppercase and shifted symbols remain blocked
until a Shift target and host Sticky Keys evidence are commissioned. The
current 29-target phone catalog contains only the lowercase layer, so uppercase
and symbol input remains blocked until transition targets and ADB verification
before every press are commissioned. The language model remains limited to
intent and exact text; it cannot provide targets, layer state, coordinates, or
authority.

**2026-10-03 Sticky Keys state-machine amendment:** the selected desktop
strategy now has an executable virtual replay rather than a simple “Shift
first” assumption. One Shift press latches exactly the next base key; two
consecutive Shift presses are rejected because they would lock the modifier;
and the sequence must end in `OFF`. Commissioning must disable the five-Shift
shortcut dialog and the setting that disables Sticky Keys after a simultaneous
two-key press. Exhaustive replay reproduces every printable ASCII character,
emits no consecutive Shift presses, and defines host log expectations of
`LATCHED` after Shift and `OFF` after the base key. This remains zero-authority
virtual evidence while the physical Shift target and host receipt are absent.

**2026-10-03 commissioned-key and seeded-replay amendment:** printable US
ASCII requires 48 base keys, of which the current 46-target catalog supplies
44. `BACKSLASH`, `GRAVE`, `LEFT_BRACKET`, and `RIGHT_BRACKET` are missing, and
`SHIFT` remains separately absent. Compilation now receives the commissioned
key set and rejects any character whose base or modifier target is absent. A
seeded population of 5,005 strings, including `AA`, `!!`, `aA`, a trailing
capital, and a capital after a space, replays 160,925 characters with zero
changes under the complete virtual audit catalog. This validates inter-character
state handling while preserving the physical-catalog blocker.

**2026-10-03 measured-keyboard geometry amendment:** the operator-guided
PERIBOARD-409 session supplies 24 hash-bound records on the keycap top press
surface. It rejects the earlier photo-derived catalog candidate: physical
housing anchors place `Q` 8.39 mm right of `1`, while the manual photo
annotation placed it on the opposite side. The corrected external candidate
uses a measured 19.133636 mm pitch for explicit number- and Q-row coordinates,
direct housing anchors for `GRAVE` and `SHIFT`, and pitch-derived bracket and
backslash centers. It strict-loads as 51 keyboard plus 29 phone targets, and
all five added safe polygons are inside the nominal simulated camera frame.
The active 75-target catalog remains unchanged. Single readings, inferred
centers, physical visibility, board placement, arm reachability, Sticky Keys
commissioning, rendering, and physical authority remain blocked.

| Worker/lane | Stage | Paths expected to change | Branch/commit | State |
|---|---|---|---|---|
| AI/model + simulation | S3-S4 selected-tool cable-assumption correction | bind the controlled passive-stylus collar/tool CAD and selected static-overhead camera architecture; remove the inapplicable moving attachment cable only from the selected Phase-1 simulation profile; preserve prior cable results as wrong-configuration evidence; rerun the keycap-height pad screen without changing installed geometry or optional future arm-camera modeling | `issue/190-isaac-sim-host` / claim `496ea6d528c9a1945aedf221d53f9b95cd5a13fc`; freeze pending | ACTIVE — source audit confirms the stylus is mechanically retained and passive, while moving-cable requirements belong to an optional arm-mounted camera route. Evaluation remains closed. No arm-lane status, integration gate, hardware write, physical movement, command, permit, transport, or physical authority changes. |
| AI/model + simulation | S2-S4 v1.4 development-root guard and keycap-height pad follow-up | bind development scoring to the exact v1.4 admission and two admitted manifest hashes; reject every resolved input outside the v1.4 root; preserve the stale v1.3 queue failure; freeze and screen a 20 mm keycap-matched pad surface against the retained first-contact semantics | `issue/190-isaac-sim-host` / claim `296671f1dc4f8a4fce352f0235f649e8ddad24af`; guard `61e1af20`; pad freeze `6d6b6425`; result `ac265c34d0c2c3910e9d8fe172e48075dfa4ff49` | COMPLETE WITH RETAINED STOP — the exact-root guard passes all 69,120 admitted v1.4 development paths and 22 contract tests. High-noise training completed and guarded development scoring is active; evaluation stays closed. Fixing the pad surface to the common simulated 20 mm keycap height removes all 29,088 prior tool-board contacts and lowers tray-mode concerning samples from 95,904 to 68,640, but cable-link4 and other cable contacts keep `STOP`. Cable clip/carrier design is the next simulation dependency. No arm-lane status, integration gate, hardware write, physical movement, command, permit, transport, or physical authority changes. |
| AI/model + simulation | S2-S4 post-GPU corpus integrity and Phase 10 remedy audit | resolve the queued development admission failure without opening evaluation; reverify every current v1.4 training/development byte; account for all three frozen noise-profile training pairs; jointly screen `halton-0573` camera clearance and route feasibility; then freeze and test first-contact pad phases plus fixed-wrist/cable-clip Stage C descent remedies | `issue/190-isaac-sim-host` / claim `c3057d389f7b3ff4059679d405933938ed9ffee9`; freeze `0b99938c17d54591befab39d810ff9af88c07ad8`; result `16d1b0efdd55549c4b8d64681446502d5b66bdda` | ACTIVE — corpus integrity is resolved and Phase 10 remedies are complete. All 115,200 current v1.4 training/development files pass exact re-verification; evaluation stays closed. `halton-0573` passes all 80 targets and 48 mm crops across the exact nadir height/distortion family while retaining 46/46 routes. First-contact semantics are contiguous, but both pad modes stop; removing neighboring stations lowers concerning samples from 203,644 to 95,904. Fixed wrist pitch clears cable-link4 only with 168-216 mm endpoint error, while fixed roll keeps accuracy and the collision. The high-noise training profile remains active; development scoring stays queued. E-641 through E-643 record the increments. No arm-lane status, integration gate, hardware write, physical movement, command, permit, transport, or physical authority changes. |
| AI/model + simulation | S3-S4 Workstream 7 clearance-waypoint and swappable-pad study | freeze a simulation-only arm-runtime-owned planning prototype: rise/transit/descend Cartesian waypoints for B/C, route feasibility in exploratory park scoring, cable collision attribution by stage and motion phase, and a locating-pin pad that replaces the keyboard with target- and phase-bounded intended contact; retain straight-interpolation and all new failures | `issue/190-isaac-sim-host` / claim `83bc24bbe9270e65f1bb501fd88d46a7fa1491f0`; fixture `cd60b28463e920f65dae9eeff4121e8f06969161`; implementation `9153d3fb961f6b8e5616721fb2fa066d747c0b64` | COMPLETE WITH RETAINED STOPS — reference screening finds 46/46 feasible key routes from `halton-0573`, 45/46 from `halton-0258`, and 0/46 from the old camera-first `halton-0299`. Robust cable/tool endpoint screens still stop B/C; cable-link4 is isolated to 156 C-descend findings. All 13 keyboard-replacement pad variants stop because contact begins before PRESS, both neighboring station envelopes are struck, and cable/workcell conflicts remain. Production planning remains arm-runtime owned and unimplemented; official readiness is unchanged. E-640 records the result. |
| AI/model + simulation | S3-S4 evidence-ledger append protection | add a Git-history-aware policy check that permits byte-identical or append-only ledger updates while rejecting deletion, rewriting, and reordering; wire it into maintained policy, CI, and clean-checkout verification before further simulation evidence is produced | `issue/190-isaac-sim-host` / claim `8202093d02738e5bbb83d2bfcc47cf771409f3f5`; implementation `11d56f503c3f64c0ad289c1d1cefa17a79f16f3b` | COMPLETE — Git-history prefix comparison now protects the ledger in maintained policy, pull-request CI, preview review, and clean-checkout verification. Five regression tests prove identical and appended ledgers pass while truncation, rewriting, and reordering fail. E-639 records the result. No arm-lane status, integration gate, hardware write, physical movement, command, permit, transport, or physical authority changed. |
| AI/model + simulation | S3 simulation program Phase 0 follow-ups | freeze and implement `EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE` screening for WS1/WS3 without constructing an installed profile; freeze and compare ADB touchscreen, temporary touch-surface, and retracted marking-tip camera landing-observation ranges; preserve collision blockers and every infeasible sensor cell | `issue/190-isaac-sim-host` / claim `71e7031f6c8683625723027b803f8660cd993c78`; fixture `2f4d550a12b8c6d0cd857595d43ba4a404e73916`; implementation `dedaf2dd154e664c01687a0e8f5dd3eb5a4f234b`; correction `db98a51dff8efff5f9c14c21a80c1b5c9abe8963` | COMPLETE WITH EXPECTED BLOCKERS — the candidate contract is diagnostically complete across 29 one-factor-at-a-time variants and 46 target poses, but no variant clears: 1,288 evaluations detect collisions and the zero-clearance endpoint is explicitly blocked. This is expected while self/attachment exclusions remain unreviewed. The landing-sensor comparison preserves every infeasible cell and selects no physical option; the temporary touch surface has the broadest feasible range (8/16 cells). PID 64620 remained uninterrupted and no GPU work launched. E-620 and E-621 record the results. |
| AI/model + simulation | S3-S4 simulation program Workstream 7 plan amendment | freeze First-motion readiness objectives, inputs, outputs, metrics, staged no-go rules, controller-emulator requirements, wrong-model drills, scenario regression, and readiness-checklist dependencies before any Phase 2 implementation | `issue/190-isaac-sim-host` / claim `cc114a0e684906159bdde5cdc86acb1af7ad5461`; bound claim `60da6d2d8eb8a46c0a924285ee9e1833c118859f`; plan `c5fdd5e9d6fcad3d1700907ae36012d472b2b975` | COMPLETE — Workstream 7 now freezes controller emulation, stages A-F, wrong-model drills, scenario regression, and the readiness checklist before Phase 2. PID 64620 remained uninterrupted; no GPU work, controller emulation, transport, hardware write, movement, command, permit, or physical authority. E-622 records the plan amendment. |
| AI/model + simulation | S3-S4 Workstream 7 Phase 2 controller emulator | derive exact protocol bindings from the repository encoder and controller contract; freeze exploratory servo ranges and fault identities; implement an in-memory measured-position emulator behind the real runtime path; prove emulator mode cannot open serial, socket, device, or real controller transport; round-trip every joint and the all-joint message | `issue/190-isaac-sim-host` / claim `06ec419fa679d01c371e53965846b8c73b4623a1`; initial fixture `05d199b8664116728d11f58fa3b5596a0f373e3d`; corrected runtime audit `356c38a0a7949a7f37a81a835ac287a9e25e47e3`; corrected implementation `47d7d70b96258976921b5026f927b5487194cd77` | COMPLETE — all 182 frozen range probes and six injected faults traverse `ProductionControllerRuntimeContractV1` with exact T102, T1021, T105, and T1051 bytes. Every path closes terminal with retry disabled; telemetry is independently simulated; all logical IDs 1-6 and servo IDs 11-17 are covered. The first receipt remains preserved as a failed runtime-inventory audit. Hardware writes, physical movements, real commands, permits, real transports, and physical authority remain zero. PID 64620 remained uninterrupted and no GPU work launched. E-623 records the result. |
| AI/model + simulation | S3-S4 Workstream 7 Phases 3-5 staged rehearsal and regression | freeze A-F telemetry-envelope ranges, ordered no-go progression, wrong-model drills, scenario identities, and decision rules in one compact manifest; execute Stage A onward only until the first no-go; preserve every later stage as `NOT_RUN_UPSTREAM_BLOCKED`; then run wrong-model and scenario analysis without weakening the frozen gates | `issue/190-isaac-sim-host` / claim `389ca3e017ae93bdf4434e04c024596b5d2aa9cc`; fixture `df899d8df06f720057a1e8386ea733ce9e78765d`; pre-result binding amendment `e9f1d36ac046234a8e08e7a06562fa2360795d6c`; Phase 3 `b9b77d6a061c9b9b0bda83a1861e1e913e504307`; Phase 4 `f1061183d78f4a7ce37145eacb5a0d74c3b703b3`; Phase 5 `dbfd4d1602878a9ff8b240a76d20ea6cf144ba76` | COMPLETE WITH NO-GO AND RETAINED GAPS — Stage A remains a collision no-go with B-F blocked. Wrong-model analysis detects 30/63 cases and retains 33 external-geometry gaps. The 84-entry scenario catalog passes all nominal, boundary, controller-fault, environment, and human cases; wrong-model is 30/63, so nightly is 51/84 and CI is 6/7 with false acceptance retained. No threshold changed and the universal collision stop receives zero unrelated detection credit. No hardware writes, movements, real commands, permits, transports, authority, or GPU launches. E-624 through E-626 record results. |
| AI/model + simulation | S3-S4 Workstream 7 Phase 6 first-motion readiness checklist | write the non-authorizing A-F checklist with exact simulation artifact hashes, required physical measurements, no-go and abort criteria, human approval, and honest satisfied/blocked status | `issue/190-isaac-sim-host` / claim `848a81a1f83281e54361aa2d3f827813e7f09aad`; bound claim `21189163c603a8dbf96a076a8b032a621c92e310` | COMPLETE AS CHECKLIST; ALL PHYSICAL STAGES BLOCKED — `software/docs/FIRST_MOTION_READINESS.md` binds the Phase 0 and Phase 2-5 evidence, lists measurements and approvals per A-F stage, and records `NOT_READY_FOR_FIRST_POWERED_MOTION`. Stage A lacks a collision-clear corridor; B-F inherit that block and add park, perception, contact, target, and recovery prerequisites. The checklist creates no authority. E-627 records the artifact. |
| AI/model + simulation | S3-S4 Workstream 7 independent-observation extension | freeze and simulate overhead arm-silhouette and touch-surface landing observers for the 33 retained geometry gaps; classify each gap by simulated press consequence and require zero undetected consequential cases; separately exercise stages A-F with the uninstalled candidate collision profile while preserving the official Stage A stop and `NOT_READY` status | `issue/190-isaac-sim-host` / claim `b280b873884ea29b276af98fbfdc9813b9f72838`; fixture `62ee7954d23abcddde5559ed0c0475bc985c4282`; implementation `ef2ee0e9d7efa4b6acc30aa46660b1d7dbbc4133` | COMPLETE IN SIMULATION; PHYSICAL OBSERVERS UNQUALIFIED — 16/33 retained gaps are consequential for at least part of the frozen 3–7 mm safe-region range; the conservative OR fusion leaves 0 consequential gaps undetected. Seventeen are harmless across the range. The separate candidate shadow rehearsal emits 198 predicted samples across A-F while retaining collision `STOP`, official Stage A no-go, and `NOT_READY_FOR_FIRST_POWERED_MOTION`. The original 33-gap evidence is unchanged. E-635 records the result. |
| AI/model + simulation | S3-S4 Workstream 7 candidate-collision attribution | attribute the candidate `STOP` to exact body pairs and applicable A-F stages; classify structural/attachment contacts separately from potentially consequential workcell contacts; test a predeclared most-favorable endpoint family without changing installed status, exclusions, or official readiness | `issue/190-isaac-sim-host` / claim `80eb6ef071c35b705013a278eef53f5a4c1a4804`; fixture `dab860bdb4f4e373c8f2d2b948d87953ebf3e62b`; correction `b688da3fcdf2392fc4d003a32deffaa4db58bc1d`; implementation `ca849b164c7d249511f7b506b548528b1f9446c9` | COMPLETE WITH RANGE-SENSITIVE E/F ROUTE — the original `STOP` is dominated by expected-but-unreviewed structural/attachment pairs. Under favorable size endpoints, 14/40 route configurations have zero potentially consequential contacts across all 46 keyboard poses; all remaining consequential pairs involve the moving cable. A-D remain unevaluated because their trajectories/test pad are absent. Official collision `STOP` and readiness are unchanged. E-636 records the result. |
| AI/model + simulation | S3-S4 Workstream 7 collision-design closure | convert the clear cable family into a candidate design requirement; generate and collision-screen Stage A-C trajectories; add a ranged temporary touch-pad model and Stage D approach/contact/retract; classify robot/tool/cable collision pairs as always, sometimes, or never touching over the expanded pose corpus; emit exclusion candidates for human review without installing them | `issue/190-isaac-sim-host` / claim `5a952e2233721718715629addf4f21b3ac639667`; fixture `b1ff70f3cc5bca5e3ed68260f4f1a5af7e5b91df`; binding amendment `4a82c91828f5f84cc10898216067d8d1076a5a95`; implementation `5ef87177373ba3a01d05e0852b178e908d71d97b` | COMPLETE WITH FAILED DESIGN-RANGE SCREEN — Stage A clears 4,224/4,224 discrete evaluations. B-F stop: the camera-silhouette park candidate and direct joint interpolations create nonadjacent self/workcell contacts; the pad family overlaps the current keyboard/right-station region; E/F need target-aware intended-contact semantics and still retain cable-link4 collisions. All C/D IK converges. The 343-pose structural audit finds 10 always-touching review candidates, 11 sometimes-touching pairs that remain active, and 24 never-touching pairs. No exclusion is installed. E-637 records the result. |
| AI/model + simulation | S3 WS5 attribution and collision-candidate preparation | predeclare and run CPU-only variance attribution over the frozen WS5 calibration receipt; characterize the 15 insufficient cells; build and audit a separately labelled, uninstalled collision candidate from exact official robot/workcell sources without satisfying installed-profile evidence or changing collision authority | `issue/190-isaac-sim-host` / claim `da65564e30654b41f039a18b499aa04267ca15a6`; fixture `5cb4493410ed884b8ae724f76f4f49df689bfdeb`; result `59769c4ac195e349bdf7bd8321fe12fd2a012920` | COMPLETE WITH COLLISION BLOCKERS — noise explains 47.13% of the one-way WS5 outcome variance, initial bias 26.61%, and residual target 4.80%. All 15 insufficient cells have high noise-to-bias ratios. The candidate binds seven official-mesh-derived robot bodies, six nominal workcell bodies, and exact static-camera CAD bounds, but remains uninstalled and incomplete because clamp, cable, tool variant, old arm-camera frames, and self-collision exclusions are unresolved. Both GPUs remain owned by the residual-training PID; WS2 did not launch. E-618 and E-619 record the result. |
| AI/model + simulation | S3 simulation program Workstreams 2-6 CPU preparation | freeze one compact, section-hashed CPU fixture manifest for key-press physics, continuous typing, drift recovery, calibration budgeting, and mid-motion observation; implement zero-authority CPU harnesses and smoke tests; execute only the CPU calibration budget and recovery tests; leave every Warp/Isaac GPU run queued until the active 96/192 comparison completes | `issue/190-isaac-sim-host` / claim `b4b6e58f57efa40b8b652f03b31c54079aea7e1b`; fixture `a2ecda2d615946d1c02c9826b6271610818d2476`; runtime-stack amendment `90b30023237c909bdde35db06abf1e0ec2e82f65`; harness `d1da156a45684242bc936b5fd524b77a0bf109da`; final CPU sentinels `8aded647d8845688b8e9429a5f48147662dd5a47`; evidence `be42b34d553a7332e2d36535abcf183a1888ac9d` | CPU PREPARATION COMPLETE — WS2 analytic actuation smoke, WS3 complete 2,601-pair enumeration, WS4 fail-closed recovery tests, WS5 full CPU calibration grid, and WS6 positive-mask-overlap sentinel pass under the frozen exploratory ranges. WS2/3/6 GPU execution remains queued, WS4 optional Warp replay waits on WS2, and no GPU launch, hardware write, physical movement, command, permit, transport, or physical authority occurred. E-615 and E-617 record the results. |
| AI/model + simulation | S2-S4 simulation program Workstream 1 | freeze and implement a deterministic, zero-authority end-to-end typing digital twin under `software/ai/sim/`, its compact fixture/schema and tests; compose existing exact-text, Sticky Keys, phone-layer, ModelMotionBatchV2, ingress, IK/screening, kinematic replay, simulated actuation, event/readback, and verification contracts; run analytic CPU scenarios first and schedule the bounded Isaac subset only after the active 96/192 comparison finishes | `issue/190-isaac-sim-host` / claim `b499f9da5f6999e65629a75bfc0165aa5637579e`; semantic fixture `6eb25f0f9f471c40dcad3cb591c23b7dc85bac33`; semantic CI `7988cfbaa6343f3f38614acfee5244506f8ceb73`; full semantic `d3589001ea290e1ee4b75a10c1572ceb700d7bce`; boundary fixture `acca9463e06df9ac23095771cec4bcd4ccb18702`; boundary result `8a2e9e1b3eb70ae2c108698ac143d37be54209f8`; CPU harness `d1da156a45684242bc936b5fd524b77a0bf109da` | ACTIVE — canonical IK passes the bounded offline trajectory and collision intake stops correctly at the missing installed geometry profile. Standard MuJoCo CPU replay is finite and deterministic across 46 poses. The installed catalog still rejects `Hello 2026!` at missing `SHIFT`; the separately labelled, uninstalled 80-target candidate reproduces it and all frozen shift-transition cases, and all 12 required candidate targets converge only after binding the frozen exploratory layout overlay. The bounded Isaac subset remains queued behind the active 96/192 job. E-612 through E-616 record the results. |
| AI/model + simulation | S3 Workstream 2 executable key-press physics preparation | while the paired 96/192 moderate/high comparison retains GPU priority, freeze the exact MuJoCo Warp key/phone contact population, scoring, sharding, cross-GPU agreement, and compact evidence contract; implement a transport-incapable runner and CPU contract tests without launching Warp or changing any frozen range after results | `issue/190-isaac-sim-host` / claim `f2cfc51f5f0360913607daf8431e716b9a18d058`; initial freeze `024c92a4d1ca42c47812027409b405bc91cbd52d`; line-ending correction `d38f2bd83a0ef15c059fce9d94557f9f47a0170b`; pre-result axis correction `d358d877038991f7a93c8dc7a3dc20f02b694346`; implementation/evidence `ec5b31450951f10b6396622a2c6007541e8374af`; landing prepass `3024e7f99f6a34da0f94c14e7f67a061eeb26852`; smoke freeze `15e8d0b9aa32e145bce0a680454a905ae8a33125`; smoke worker `83075a5d2a8753cb7541349a30684a5b24e60f39` | ACTIVE — BOUNDED DUAL-GPU SMOKE READY, EXECUTION DEFERRED. The 285,769,728-world campaign contract and 13,056 landing inputs are ready. A frozen 64-world `GRAVE` smoke now has an executable Warp stepping/event worker with settle, prescribed contact trajectory, partial/double/repeat/neighbor/bottom-out/release/required-force metrics, exact stack identity, and strict comparison. CPU contract tests pass. No GPU dynamics, recipe selection, campaign result, or provisional tool choice exists. PID 50020 retains both GPUs. E-631 through E-633 record the preparation. |
| AI/model + simulation | S3 Workstream 2 staged-search amendment | before any Warp contact result exists, preserve the 285,769,728-world population as the exact reference superset and predeclare a throughput decision plus coarse-to-boundary refinement that cannot select cells from favorable outcomes; bind coarse identities, transition definitions, fixed neighbor expansion, minimum coverage, full-grid fallback, and unchanged contact gates | `issue/190-isaac-sim-host` / claim `76cc43a399bb3539855571408b85836828f50bde`; bound claim `31475b53582d27b9df4661f6042923109e266da1`; fixture `586cdd23f46e2d444c7799c567253ea6b5d3d2e8`; implementation/evidence `164783c3ee77db6a14fbe7d8737178d8b8b7f91e` | COMPLETE — PRE-RESULT STAGED SEARCH FROZEN. The original 285,769,728 worlds remain the exact reference superset. Smoke throughput selects the full grid only when projected two-GPU wall time is at most 12 hours and memory is at most 70%; otherwise Stage A covers every target/profile/tip/scenario using 12 deterministic maximin recipes and eight landings for 4,465,152 worlds. Stage B adds four fixed nearest unrun recipes around every mixed/nearest-neighbor outcome boundary using all 64 landings. Only up to eight Stage C recipes that pass exhaustive 51-by-19-by-12-by-4-by-64 confirmation may be called robust over sampled ranges. Twelve CPU tests pass; PID 50020 remains uninterrupted. E-634 records the contract. |
| AI/model + simulation | S3 Workstream 1 bounded Isaac subset runner | while the frozen moderate/high paired comparison retains GPU priority, audit and implement the CPU-side executable contract for the already planned small Isaac perception subset; freeze exact scenario identities, simulator/version bindings, metrics, cross-GPU agreement, stop rules, compact receipt, and zero-authority guards before launch; do not execute any GPU work until the paired comparison releases both GPUs | `issue/190-isaac-sim-host` / claim `86509b763a7d554377c14dd8ab9cb92a716f58ad`; bound claim `7c205f1e70016c949336634f4b3ed42114331cbf`; fixture `66516a0233ee66f498ef18d98a749ea92c134923`; implementation `ef6c08849aaa4a760938788b799a3ab9964cb281` | ACTIVE — GPU READY, EXECUTION DEFERRED. The zero-authority runner expands all 162 frozen scenario/render identities, authors candidate target surfaces and the deterministic occluder, records Isaac/Warp/driver/GPU/Git identities, emits external RGB/mask evidence, and compares exact identities across GPU 0 and GPU 1. CPU tests prove fixture tampering, authority claims, identity drift, and RGB drift stop. The moderate/high paired comparison retains GPU priority; no Isaac launch, render, GPU queue competition, hardware write, movement, command, permit, transport, or authority change occurred. E-629 and E-630 record the fixture and implementation. |
| AI/model + simulation planning | S2-S6 prioritized simulation automation program | create one governed program plan covering the end-to-end typing twin, key-press physics, continuous motion policy, drift recovery, calibration budget, and mid-motion Isaac observation; freeze objectives, inputs, unmeasured ranges, outputs, metrics, pass/stop rules, dependencies, compute estimates, evidence backup, archive discipline, and the active 96/192 run as a no-preemption prerequisite before Workstream 1 | `issue/190-isaac-sim-host` / claim `891c993a45b38a3e7ef066738af494c26c979b77`; plan freeze `3a9db56d7b96276492fcffd51b4c39c0891bf1db` | COMPLETE — Step 0 plan SHA-256 `9077457d6e14c50a74d3af01cdd1d9debf126bd72027b48a7f396bc8bd529c28` freezes all six workstreams and their order before Workstream 1. The running 96/192 comparison remains the explicit no-preemption prerequisite for new GPU work. No simulator launch, training, rendering, hardware write, physical movement, command, permit, transport, or authority change occurred in this increment. E-611 records the result. |
| AI/model + simulation | S2 exploratory paired-height training pipeline | implement exact manifest-backed native-crop loading, the frozen training-free baseline, deterministic 500-row training-only memorization, six parity-controlled 96/192 runs, identity-cluster development scoring, and the frozen cross-noise decision; retain outputs externally; keep evaluation unopened and prohibit qualifying/deployment claims or physical authority | `issue/190-isaac-sim-host` / claim `ae3e23dfa658493a903d0a4d55b8c9da84d8ba2b`; features `68df26e5666875656315e912927eeba10a981334`; memorization implementation `87b2bf03b4572a7ece08af43cfc98cf95b34f6f1`; deterministic-pool correction `d396854a146d7dca0652f7118d6f30c54783f1c7`; compact expansion `f6664de9a455cffb789a687122c4fd49777a7878`; exact cache correction `3e8236b53de2c06b2b571740702d9b52ed48d5b6`; scorer freeze `9b03cbd0da26639a5992df3aa803d840b1dc1e90` | IN_PROGRESS — all pretraining controls and the plain-difference baseline are complete. Low and moderate paired runs have each completed all 18 epochs over 46,080 rows, with exact report and checkpoint validation. Moderate final losses are 0.00121587 at 96 and 0.00013004 at 192. High-noise training is now running under the unchanged frozen contract. These are convergence results only; development remains unopened until high noise finishes, and evaluation remains unopened. E-609 through E-612 record the implementation and completed full runs |
| AI/model + simulation | S2 exploratory 96/192 assumed-noise comparison | predeclare low/moderate/high synthetic camera profiles, six paired resolution runs, training-only memorization, exact repeated-height cluster scoring, and a cross-noise decision rule before training; bind admitted v1.4 train/development receipts; prohibit qualifying/deployment claims and keep evaluation unopened | `issue/190-isaac-sim-host` / claim `72c2d5c56c9c8e68f46df71e8f4eb9eca750b89d` | PREDECLARED — amended canonical experiment bundle `7d7905d8d34d35e525b3192e77bf8f57f55f50d2b4024c1c8fecb44d8a0dbf6b` freezes the three profiles, paired architecture, pooling, isolated statistics, memorization selection, plain baseline, and safe-region-mask intersection with the visible 48 mm crop for wide targets. Six runs, identity-cluster gates, and the global rule remain unchanged. Every amendment precedes results; evaluation is unopened and no receipt or training result exists |
| AI/model + simulation | S2 v1.4 paired-height development corpus | bind the existing repeated-height development design to the exact admitted v1.4 fixture and corrected fixed center; keep whole scene identities on one worker; require full-frame bounds before rendering and exact 69,120-row admission; use only disjoint development lighting and obstruction assets; keep evaluation unopened and retain zero commands, permits, transport, movement, or authority | `issue/190-isaac-sim-host` / claim `45d8e234e9e5ac3483b0e3b58cd72cdb99619c5b`; plan freeze `d18bf795fa8c9986a769be5a9f696513ae7e0bb1` | COMPLETE — DEVELOPMENT CORPUS ADMITTED. Two disjoint whole-scene workers rendered 34,560 rows each across all eight development scenes and all three heights. Exact repository admission verifies all 69,120 lossless PNGs, hashes, dimensions, full-frame bounds, YUY2 alignment, identities, and allowlists. Repeated-height inference remains clustered by frozen key `SCENE_APPEARANCE_TARGET_VARIANT_WITH_HEIGHT_REPEATED`. Combined result SHA-256 `4556ad59559691f4019502710b56a9ec65b01d3168a9f34c6eb0294aa54e3b67`; evaluation remains unopened. Next dependency is the frozen 96/192 loader, memorization, baseline, training, and paired development comparison sequence |
| AI/model + simulation | S2 v1.4 full-context camera-center correction | supersede rejected v1.3 before any new pixels; require full containment of the same model-consumed 48 mm native crop used by both the 96- and 192-pixel candidates at 700/850/1000 mm; select one fixed exact-nadir center through a frozen maximin screen; convert limiting pixel clearance to a synthetic mounting tolerance; rerun target coverage plus parked-arm capsule and official-mesh checks; require a four-phone-target 700 mm smoke; mandate a complete training rerender with no v1.3 row reuse; keep development/evaluation unopened and retain zero commands, permits, transport, movement, or authority | `issue/190-isaac-sim-host` / claim `fe2698edc06142921b17391cca4af85f89b6fa01`; render freeze `09c254ae39ec72ffe9288c76b8585a048cda6760`; finalizer freeze `09ffaf7b70e49a19eb93fa4ea8cee0daf3e768ff` | COMPLETE — CORRECTED TRAINING CORPUS ADMITTED. All crop, capsule, official-mesh, and phone-edge smoke gates pass at `[333.504403, 228.5] mm`. Two disjoint fresh workers rendered 23,040 rows each; exact repository admission verifies all 46,080 lossless PNGs, all 16 scenes, hashes, sizes, full-frame bounds, YUY2 alignment, identities, and allowlists. Combined result SHA-256 `02e07a3e5c2ba7aa3253b96b26a8562c785f4a38ca3497cee0033d8e95c4ee47`. Development/evaluation remain unopened; next dependency is a v1.4-bound development renderer and gate sequence |
| AI/model + simulation | S2 v1.3 development render queue | while the admitted training render continues, prepare a separate restartable development renderer for all eight frozen development scenes, all three discrete heights, all 80 targets, three disjoint development appearances, and twelve frozen variants; split whole scenes across two GPUs so repeated-height identities stay together; queue launch only after both training shards complete and pass exact v1.3 admission; preserve identity clustering, exact receipts, failures, and custody; keep evaluation unopened and retain zero commands, permits, transport, movement, or authority | `issue/190-isaac-sim-host` / claim `3da63d572190f625023aa008f96363388d60dfa0`; external renderer SHA-256 `5f22c9ec7ee6e06efe2ab07713a6c409efebebe24bb6b417ded282b7d33b6add`; queue SHA-256 `ee2cb45bc456889e07f7be2351b341795f23477b4143aaad78fbaaa27e912c33` | COMPLETE — BLOCKED AS DESIGNED. The queue independently rejected training admission because 864 rows have clipped 700 mm phone crops whose stored dimensions differ from the frozen 48 mm context contract. Failure receipt SHA-256 is `677251d7fba8220810fc65a2cf83d4e7c9d01146ec2bc39bf3c4834d6cd965cb`. No development worker launched; development and evaluation remain unopened. E-594 preserves the failure |
| AI/model + simulation | S2 v1.3 full training render | after the cross-height/cross-plane smoke passes, implement restartable exact training shards over all 16 frozen scenes and 80 targets; prevent target-neighbor obstruction contamination; verify every shard through v1.3 exact admission; record throughput, storage, failures, and custody; keep development and evaluation unopened until all training shards admit and the memorization gate is ready; retain zero commands, permits, transport, movement, or authority | `issue/190-isaac-sim-host` / claim `40d12f41a36d946a0080f24f2b6fe65c7483d2aa`; external runner SHA-256 `9d647990bd99008c42bba25d69ed953c9b88745fe94d3637715a808e73b197cf` | COMPLETE — FAILED EXACT ADMISSION. Both workers completed all 3,192 frame groups and wrote 23,040 PNGs plus exact manifests apiece. Admission found 864 systematic dimension mismatches, all at 700 mm for phone `key_o`, `key_p`, `key_l`, and `key_enter`, because the requested fixed 48 mm context extends beyond the right sensor edge. No model training or development access occurred. E-594 records the failure; the next AI dependency is a pre-result camera-axis/context-containment correction, followed by the affected coverage and parked-arm gates before rerendering |
| AI/model + simulation | S2 v1.3 cross-height and target-plane smoke | render exact training rows for scenes 01/02/03 at their frozen 700/850/1000 mm assignments, keyboard `GRAVE`, and phone `key_w`; retain lossless native crops; require exact admission; verify decreasing native support with height, even YUY2 alignment, crop centering, focus diagnostics, and dark-cable ordering on both physical planes; preserve failures; keep development/evaluation unopened and retain zero commands, permits, transport, movement, or authority | `issue/190-isaac-sim-host` / claim `11dcc4f4b30b55f1637a0d66dbed6988e15aed34` | COMPLETE — after two preserved semantic-path failures, the RGB-only run produces and exactly admits all 216 native rows. Keyboard support shrinks 472/388/328 px and phone support 468/384/326 px across 700/850/1000 mm; all bounds satisfy even-pair admission; maximum analytic centering error is 0.851 px; the minimum synthetic Laplacian variance is 28.387; visual review finds both planes centered and sharp; and all 18 dark-cable ordering checks pass. Development/evaluation access, training, hardware writes, movement, and authority remain zero. E-591 records the result |
| AI/model + simulation | S2 paired-height v1.3 training smoke | render one exact training-only shard for keyboard `GRAVE` at its assigned 700 mm nadir height; retain one lossless native sensor-aligned crop for every frozen appearance/variant identity; admit only the exact manifest against v1.3; derive 96/192 audit views with an explicitly exploratory assumed camera profile; preserve every failure; do not access development or evaluation, train or select a model, install the external catalog, change arm/integration status, or add commands, permits, transport, movement, or authority | `issue/190-isaac-sim-host` / claim `14c428d802cd059bf4ff8dc3a299a8d05c35749f` | COMPLETE — the exact 36-row training shard passes v1.3 admission with 36 lossless 472 by 472 native crops. All three appearances preserve increasing exploratory 192-pixel difference for 10/30/60% dark cables, every non-clear family changes pixels, and visual review confirms correct target-relative placement. The 72 derived views are exploratory, assumed-profile audits outside the model-input allowlist. Development/evaluation access, training, selection, hardware writes, movement, and authority remain zero. E-590 records the result; broader rendering remains blocked on a reproducible shard runner and storage review |
| AI/model + simulation | S2 measured tone and spatial-noise amendment | before rendering, extend the B0477 profile with a locked-exposure response curve and neighboring-pixel noise-correlation kernel; separate renderer sRGB decoding from measured camera tone encoding; bind denoise/sharpen disable attempts and settings receipts; reject absent, malformed, or unmeasured response/correlation evidence in qualifying mode; preserve prior fixtures and zero authority | `issue/190-isaac-sim-host` / amendment claim `c81ff955f9feafca727b645380d7a0ee08b7482d`; result `a1f25cca35c0e5adaaeab1cf46065cebda6864f7` | COMPLETE — v1.3 binds separate renderer-source sRGB decoding and measured B0477 tone encoding, exposure-sweep and static-burst hashes, a brightness-dependent linear noise curve, an RMS-normalized spatial correlation kernel, and denoise/sharpen disable-attempt receipts. Tests prove the measured tone changes output and a nontrivial kernel spreads noise to neighbors while preserving RMS. No images were rendered or models trained. E-589 records the result; the training-only Isaac smoke is next |
| AI/model + simulation | S2 linear-light camera-model amendment | before rendering, supersede the RGB8 native-loader order with an explicit stored-encoding contract: decode stored sRGB to linear light, apply exposure and a measured brightness-dependent noise curve, quantize in linear sensor space, apply white balance and tone encoding, then YUY2, aligned crop, and 96/192 resampling; reject missing or malformed measured curves in qualifying mode; preserve prior fixtures and zero authority | `issue/190-isaac-sim-host` / amendment claim `2e4dc25dae6d875ad5dc20edb134a832a2b68634`; implementation `80931d89733d33b22a61a5a625526167a660dc2a`; validation `36931cbcb783d21bed00f134a7aef37b4fb67799` | COMPLETE — v1.2 explicitly records native storage as 8-bit sRGB, decodes to linear light, applies exposure and a piecewise brightness-dependent noise curve, quantizes at the declared sensor depth, applies white balance and sRGB tone encoding, then performs YUY2, aligned cropping, and resizing. Qualifying mode requires a hash-bound measured B0477 locked-settings profile. The planned burst analysis bins variance against per-pixel mean after YUY2 decode and sRGB linearization. No images were rendered or models trained. E-588 records the result |
| AI/model + simulation | S2 paired-height native-crop storage amendment | before any corpus pixels exist, replace stored 96/192 resamples with one lossless sensor-aligned native crop per identity; require the load-time order native exposure/noise/quantization/YUY2, aligned crop, then 96/192 resampling; preserve exact pairing through one source hash and seed; cluster development statistics by cross-height identity; reserve intermediate heights for a later unopened evaluation fixture; do not render, train, select, install the catalog, or add commands, permits, transport, movement, or authority | `issue/190-isaac-sim-host` / amendment claim `1c44e376304e0ef364d09c3b8e56912ac9e72a8c`; implementation `c99b52dc5b22e7a92dfe149aada132b0950d4f57`; camera-order corrections `82103e333c8ee47357562afd4d7fbe4b3d87c91a`, `80931d89733d33b22a61a5a625526167a660dc2a` | COMPLETE — v1 and v1.1 remain preserved as pre-render rejected designs. Hash-bound v1.2 stores one 320–480 px sensor-aligned native PNG per identity and applies the complete declared linear-light camera order before floating crop alignment and 96/192 resampling. It rejects qualifying loads without a measured brightness-dependent B0477 profile, clusters repeated-height development statistics by identity, and reserves 775/925 mm probes for later unopened evaluation. No pixels were rendered and no model was trained. E-587 and E-588 record the corrections |
| AI/model + simulation | S2 paired 96/192 lossless height-diverse corpus | freeze a new synthetic-only train/development corpus derived from the admitted 700/850/1000 mm exact-nadir family; bind identical scene, target, obstruction, appearance, and noise seeds across 96/192 candidates; retain a lossless full-native source and deterministic fixed-physical crop derivation; keep evaluation identities absent and v5.4 immutable; implement exact allowlist admission and a small training-only smoke before broader rendering; do not select a model, install the external catalog, claim camera transfer, or add commands, permits, transport, physical movement, or authority | `issue/190-isaac-sim-host` / claim `70acc510a5b3b53c1b51905d05317344756fea39`; initial contract `a7b2bbdaa29ef9948f6a3de197022d0a559eb909`; final pre-render fixture `a1f25cca35c0e5adaaeab1cf46065cebda6864f7` | IN_PROGRESS — v1.3 freezes 46,080 training and 69,120 development source rows while storing 115,200 native sensor-aligned lossless crops. Both resolutions are derived after linear-light, measured-tone, brightness-dependent, spatially correlated camera effects. Training balances one admitted height per scene; development repeats every identity at all three heights and requires identity-clustered statistics. Strict admission covers identity, source binding, PNG, native dimensions, YUY2-pair alignment, and allowlists. Evaluation remains absent. The exact training-only smoke passes; broader rendering and paired training remain pending. E-586 through E-590 record the contract corrections and smoke |
| AI/model + simulation | S2 paired 96/192 spatial-model preparation | preserve the released 96-pixel path while adding a parameter-matched 192-pixel spatial reference-difference variant; make reference-context normalization scale with input dimensions; verify identical output shape and parameter count at 96/192; do not train, select, open evaluation, render new corpus pixels, install the catalog, or add commands, permits, transport, physical movement, or authority | `issue/190-isaac-sim-host` / claim `59522d96737da35841ee6d4d7d4fcd23d66d9c1c`; result `6dbd71332bda6c7dd24f874deb399ce5a6689bcd` | COMPLETE — the released 96-pixel architecture remains unchanged. A separate adaptive 6×6 successor accepts only 96 or 192, produces one logit at both sizes, and holds capacity fixed at 42,673 parameters. Reference-context normalization now derives its center exclusion from input dimensions while reproducing the original 24:72 region at 96. Eleven focused tests pass; no pixels were rendered and no model was trained or selected. E-585 records the evidence |
| AI/model + simulation | S2 nadir height admission and input-resolution comparison | bind 700/850/1000 mm coverage and parked-arm clearance before height augmentation; add an asymmetric OpenCV/YUY2 real-camera orientation sentinel; then compare 96 and 192 fixed-physical inputs on only admitted heights using identical identities and seeds; preserve failed heights and orientation attempts; prohibit evaluation access, production selection, catalog installation, commands, permits, transport, physical movement, or authority | `issue/190-isaac-sim-host` / claim `2c5007ce5bb8d6afbdfc08ed1266741efee4373c`; result `7fdbd4d5509ab991840d60e8206278bea67a9c9a` | COMPLETE WITH BLOCKERS — the ready pose fails all frozen capsule height checks. Candidate `halton-0157` passes all 80 capsule checks and the predeclared official-visual-mesh gate at 700/850/1000 mm with zero target overlap, admitting these heights only for exploratory synthetic augmentation. An OpenCV commissioning sentinel now accepts top-left BGR and rejects vertical/horizontal/180-degree transforms plus RGB/BGR swaps. The full-native paired smoke passes all 24 ordinal checks; 192 px modestly reduces average and worst height variation but slightly weakens the worst cable separations, so both 96 and 192 advance to broader development with no smoke selection. Physical stability, measured camera commissioning/noise, collision/rest geometry, and a powered paired model comparison remain open. E-584 records the evidence |
| AI/model + simulation | S2 exact-nadir height-robustness smoke | freeze a small exploratory, lossless, zero-authority smoke at 700, 850, and 1000 mm with camera angle and center fixed; bind representative edge, joint-margin, ordinary-key, and phone targets plus clear/dark-cable variants; implement fixed-physical-area crop metadata and deterministic resampling; compare the same target/obstruction identities across height; preserve failures; do not render evaluation identities, train or select a production model, install the external catalog, select a physical operating height, or change arm/integration status | `issue/190-isaac-sim-host` / claim `bb7d2e2661684af93871aba08fc886a365338b13`; implementation `0e5994fd5b958461e60178b63903b0454d61ae49` | COMPLETE WITH BLOCKERS — v1 is preserved failed because an unbound image-axis convention cropped mirrored board-Y locations. Its hash-bound v2 successor explicitly binds Isaac's vertical sign and passes all 12 per-target/per-height ordinal checks across 36 lossless/YUY2-proxy observations. Fixed physical extent and native support are now explicit, but cross-height score ranges remain substantial, no model was trained, and the result is synthetic exploratory evidence only. E-583 records the result |
| AI/model + simulation | S2 fixed-nadir height-family analytic screen | freeze the repository-authoritative 500–1000 mm support range, purchased nominal 16 mm lens, published 2.4 µm IMX283 pixel pitch, full-native 5472×3648 YUY2 mode, 30 mm board border, exact nadir orientation, exploratory Brown-Conrady stress profiles, physical-plane diagnostics, unchanged safety gates, and zero authority before screening; bind the exact external 80-target candidate; analytically report coverage, ground sample distance, key/cable pixel support, exploratory thin-lens blur, and arm frame containment; preserve failed centered and incomplete-axis screens; select one fixed principal-axis intersection only after every fixed trunk capsule through `link2` is included; then vary height only with fixed-physical-area crops and held-out in-range heights; do not render, train, install the catalog, select a physical operating envelope, or change arm/integration status | `issue/190-isaac-sim-host` / claim `c05ef8ff2a483342361cd124c1ecaa72456a1ff0`; amendments `0e0a49633d2a37071977bf97787aae968c6bbe09`, `99aeb524e18cc1f9a83f3876d9a4f614f50505d1`; implementation `0c5525a91969423cf0ecf5d00ad86427a6676a35` | COMPLETE WITH BLOCKERS — all 80 safe regions remain covered under every frozen stress profile from 700–1000 mm, supporting height-diverse target-local model inputs. The 30 mm board envelope passes only at 1000 mm. The centered camera contains no candidate park pose. A base-only axis selection was rejected after its omitted fixed stem was found. The corrected trunk-aware ±15 mm search has zero passing axes: its best exact-nadir axis is `[310.0, 242.5] mm`, where nominal and existing-stress borders remain positive but the unmeasured mirrored-stress board border is `-6.52 px`. No mesh finalist, render, training run, physical envelope, or authority is claimed. E-582 records the result and preserved failures |
| AI/model + simulation | S2 parked-pose/camera joint search and predecessor-corpus audit | determine whether v4.2/v5.4 clear-reference conclusions contain or omit the ready-arm silhouette; preserve those scope limits; bind the exact external 51-key candidate and governed kinematics; search candidate camera positions and zero-write park joint states by maximizing worst safe-region-to-arm clearance; report joint margins and a clearly labeled gravity-moment proxy because measured link masses/inertias are absent; require an official-mesh rerender and later de-energized physical stability/rest check before accepting a pose | `issue/190-isaac-sim-host` / claim `0221f0b229abbaa96ab0450821822e1f2f3e7204`, implementation `729dfd670b1746221e83e80ceac2e9787741807d` | COMPLETE WITH BLOCKERS — v4.2 omitted the arm rather than embedding contaminated arm pixels; only 8/100 reported hard cases use the six old-catalog targets blocked by the nominal ready mask. v5.4 generated separate analytic masks only for F–I and did not composite them into RGB. The 24,633-pair capsule screen found a camera-only ready-pose option at 96.23 px minimum nominal clearance and alternate folds at 466.05 px, but measured gravity properties, rest geometry, collision screening, and official-mesh confirmation remain absent. E-581 records the evidence |
| AI/model + simulation | S2 exact 51-key parked-arm non-occlusion check | bind the exact external 51-key candidate, nominal overview camera contract, ready joint state, governed URDF, and retained Isaac official-visual-mesh ready mask; recompute center and safe-region overlap for all 51 keyboard targets; exercise a deliberate positive-overlap control; preserve any failure; report nominal pixel clearance without inventing a physical dilation tolerance; prohibit catalog installation, physical qualification, commands, permits, transport, or authority | `issue/190-isaac-sim-host` / claim `d9a959f9284ea31ddbd9e150f02ca203977e085a`, implementation `84ecedf396141e4cde776c5215b405506a28f4ef` | COMPLETE — FAILED RENDER GATE: the exact nominal ready silhouette overlaps eight candidate safe regions (`0`, `APOSTROPHE`, `ENTER`, `EQUAL`, `LEFT_BRACKET`, `MINUS`, `P`, `RIGHT_BRACKET`), including center coverage at `0`, `EQUAL`, and `MINUS`. The positive-overlap control is detected. No physical dilation is invented, the candidate remains uninstalled, and physical/shared gates are unchanged. E-580 records the evidence |
| AI/model + simulation | S2 exact 51-key measured-candidate MW2UC rerun | preserve the original 46-target and five-key extension evidence; generate one catalog-ordered, zero-authority pose bundle from the exact external 51-keyboard/29-phone candidate; replay the unchanged frozen MW2UC seed, source magnitudes, random levels, residual fractions, Wilson/p01 scoring, and 4 mm comparison on both GPUs; report `EQUAL`, `Z`, and every target without installing the catalog or changing physical gates | `issue/190-isaac-sim-host` / claim `d9c43b60f866dbf70294bb69407f1e915d80a4a0`, implementation `2684a4c9146db14f9b73443727e61d39a92ad4c8` | COMPLETE WITH BLOCKERS — all 51 exact-candidate routes pass and both GPUs agree across the unchanged 4 mm grid. The three original comparison cells pass with zero misses; `GRAVE` has the tightest p01 landing margin, while `EQUAL` has the tightest modeled joint-limit margin. The candidate remains external and uninstalled; physical and shared integration gates are unchanged. E-579 records the evidence |
| AI/model + simulation | S2 MW2UC five-target measured-catalog extension | add explicit coordinate provenance for each proposed key; preserve MW2UC and its original 46-target result; derive zero-authority contact poses for only `SHIFT`, `BACKSLASH`, `GRAVE`, `LEFT_BRACKET`, and `RIGHT_BRACKET` from the external measured candidate; replay the exact frozen MW2UC seed, source magnitudes, random levels, residual fractions, Wilson/p01 scoring, and 4 mm comparison on both GPUs; prohibit threshold changes, catalog installation, physical qualification, commands, permits, transport, or authority | `issue/190-isaac-sim-host` / claim `a531d94a01a0197066eea459bccca95df6dc16c2`, implementation `f4b7584de755f42717aa3422cd1ad5dfa82c4cbf` | COMPLETE WITH BLOCKERS — all five targets pass the original 46-target MW2UC comparison cells at 4 mm on both GPUs with zero misses and identical numerical content. `GRAVE` and `SHIFT` are explicitly measured; brackets and backslash retain visible mixed measured/inferred provenance. The external 80-target candidate remains uninstalled, and physical gates remain unchanged. E-578 records the evidence |
| AI/model + simulation | S1 measured-keyboard geometry reconciliation | preserve the failed photo-derived candidate; hash-bind the operator-guided PERIBOARD-409 keycap measurements; derive a simulation-only five-target geometry fit from measured pitch, housing anchors, and existing catalog topology; reject altered or incomplete sessions; validate printable-key compiler coverage; keep physical camera visibility, board placement, arm reachability, catalog installation, rendering, and authority blocked | `issue/190-isaac-sim-host` / claim `9722040b567872772785b0526832bac2d47a789f`, implementation `c29a61455d30b10454df6f8b775ee39a59ff49c1` | COMPLETE WITH BLOCKERS — 24 measurement records reject the off-by-one photo candidate. The corrected external candidate strict-loads as 51 keyboard plus 29 phone targets; all five added safe polygons pass nominal analytic frame coverage, and printable-key coverage has no missing base or modifier targets. The active 75-target catalog is unchanged. Physical visibility, board placement, arm-owned IK, Sticky Keys commissioning, catalog installation, v5.5 amendment, rendering, and authority remain blocked. E-577 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2UC fixed-approach calibrated-residual study | preserve MW2UF; replace press-varying backlash signs with one deterministic approach sign per target; model per-key Cartesian correction with swept residual fractions; combine corrected constant bias with random press noise; score only `3–4 mm` effective half-widths; close further synthetic sensitivity expansion after this result and prohibit physical qualification or authority | `issue/190-isaac-sim-host` / claim `d5582108808d8cdd87df3fab4e716baa49e53bbe`, implementation/result `d561103a52c6787b85eaeabb84f48086347ccbb4` | COMPLETE — the 4 mm region supports the design path: at `0.0015 rad` random noise it passes with 25% residual from `0.004 rad` fixed sources and 10% residual from `0.008 rad` fixed sources. The 3 mm region is marginal and tail-sensitive. Further synthetic sensitivity expansion stops here; physical measurements are next. E-576 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2UF effective-safe-region and combined-source feasibility map | preserve MW2U/MW2UR; sweep symmetric effective safe half-widths from `1` through `7 mm`; score random noise against width without assigning a physical safe region; jointly propagate random noise, sampled-sign backlash, and campaign-constant offsets; publish only exploratory open-loop feasibility cells and prohibit physical qualification, commands, permits, transport, or authority | `issue/190-isaac-sim-host` / claim `9a4b959ab498d4470cea07a83fd3745e5018a899`, implementation/result `27b3b1341f4ea81325b2d6b6ccb9b511cc133a30` | COMPLETE — two GPUs agree across 65,945,600 worlds each and 2,450 width/scenario cells. Random-only `0.0015 rad` needs `3 mm` half-width; adding `0.002 rad` backlash and systematic sources raises this to `5 mm`. Random `0.002` plus `0.004` backlash and systematic fails even at `7 mm`. Safe width remains a sensitivity axis, not a physical claim. E-575 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2UR absolute-scoring audit and threshold refinement | preserve MW2U; prove constant translations are scored against the target center rather than recentered; report absolute target-center displacement and remaining safe-region margin; refine random noise between `0.002` and `0.004 rad`; extend backlash and systematic grids until each fails; retain nominal point-tool, synthetic, zero-authority scope | `issue/190-isaac-sim-host` / claim `867677aa324145857388e17c66ad0fab25a8f1e9`, implementation/result `b5ea96ff95c396e4fe3c3552468e5f1c2c1048fe` | COMPLETE — absolute center scoring and a constant-translation sentinel reject recentering; two GPUs agree across 4,898,816 worlds each; random noise brackets at `0.0035` pass/`0.00375 rad` fail, while backlash and systematic offsets both bracket at `0.008` pass/`0.01 rad` fail. Nominal 7 mm half extents and a zero-radius tool remain optimistic synthetic assumptions. E-574 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2U nominal-target uncertainty sensitivity | bind a catalog-wide exploratory pose source; score nominal keycap-rectangle misses and remaining margin; separate random joint noise, sampled approach-direction backlash, and campaign-constant systematic offsets; compare small-noise Monte Carlo spread with a local finite-difference Jacobian; derive only provisional synthetic planning values and prohibit physical qualification, commands, permits, transport, or authority | `issue/190-isaac-sim-host` / claim `7f744191d59a11540493ae6de5f202ab950b18a0`, implementation/result `0c7436e1bf5490c9d89a823a083725409ecf9032` | COMPLETE — `PASS_EXPLORATORY_SENSITIVITY`. The rank-1 route configuration yields 46 exact target poses. Two GPUs agree across 3,391,488 worlds. Random-noise transition is bracketed at `0.002` pass/`0.004 rad` fail; backlash and systematic thresholds remain right-censored above the tested `0.008 rad`. Jacobian RMS ratios are `0.9834`–`1.0162`. This is nominal point-tool planning only, not a physical requirement. E-571 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2G schedule-gap attribution | bind the retained 133-row schedule, promoted arm report, and MW2F FK receipt; prove whether the schedule/reference gap is accepted IK residual, serialization rounding, or model divergence; report reach/Jacobian/phase relationships as diagnostics; state that four-backend parity proves implementation consistency rather than physical-arm accuracy; prohibit uncertainty qualification, dynamics, contact, hardware writes, movements, permits, transport, and authority | `issue/190-isaac-sim-host` / claim `9d707d3dd3574994894efbb34007d2798e2cf655`, implementation/result `aaf7a38e5db3410d596fb837eecea27352f6bef4` | COMPLETE — `CONFIRMED_ACCEPTED_IK_RESIDUAL`. Exact desired waypoints reconcile at zero, serialized joints reproduce the original achieved FK within `1.17e-13 mm`, and recomputed residuals reconcile within `1.39e-17 mm`; the `0.076911 mm` maximum is an admitted transit IK residual. Parity remains a consistency result; physical accuracy is untested. E-570 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2FI full-sample Isaac closure | preserve v1; add opt-in v2 retaining all 133 Isaac tip rows; bind exact schedule/USD/import/profile/tool identities; strictly compare every row with MW2F RoCell/MuJoCo/Warp output; reuse frozen backend gates; require same-stack canonical receipt identity; prohibit dynamics, contact, rendering claims, hardware writes, movements, permits, transport, and authority | `issue/190-isaac-sim-host` / claim `d61bd9c1471204890c1fe9f43ade6d703c8362fd`, frozen implementation `209157effd07609bcf3497f8fc4bf6d510724c0f`, literal correction `7d3a49a6c1e62f220f331e01c5bdd61530bf3c6f`, result `498b1cfa6cd5b9a836fc5b1866696fbb83ec5f62` | COMPLETE — `PASS_KINEMATIC_ONLY`. Two full-sample Isaac receipts are byte identical. All 133 direct rows pass; Isaac/RoCell and Isaac/MuJoCo maxima are `0.000271 mm`, Isaac/Warp is `0.000280 mm`. One pre-comparison attempt failed on a truncated hash literal and remains preserved. No physical, dynamic, collision, contact, rendering, or authority claim changed. E-569 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2F schedule-scale FK differential | freeze and replay the exact retained 133-state schedule through the runtime reference, standard MuJoCo, and MuJoCo Warp; bind the retained Isaac receipt and exact URDF/MJCF identities; reuse existing 0.1/0.01/0.25 mm tolerances; record driver, GPU, Warp, MuJoCo Warp, MuJoCo, Python, and OS; require same-stack byte reproducibility and cross-stack tolerance semantics; prohibit uncertainty qualification, dynamics, contact, rendering, hardware writes, movements, permits, transport, and authority | `issue/190-isaac-sim-host` / claim `1e0ca222bfc80b865573ec102107fb4797151969`, implementation/evidence `b89da2ae562d8233484bb8c53e04bc239b8456fb` | COMPLETE — `PASS_KINEMATIC_ONLY`. All 133 states pass. MuJoCo/RoCell maximum is `3.18e-13 mm`, Warp/MuJoCo maximum is `0.000152 mm`, retained Isaac/reference maximum is `0.076849 mm`, same-stack CUDA 0 receipts are byte identical, and cross-device tool-tip delta is zero. The retained Isaac v1 receipt lacks non-contact per-sample coordinates, so direct all-sample four-backend rows remain pending. No physical, dynamic, collision, contact, rendering, or authority claim changed. E-568 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2P provenanced kinematic scenario profiles | define a strict versioned six-joint uncertainty profile; bind the governed MJCF and an exact source artifact; derive deterministic shard seeds from the profile hash; reject altered, missing, synthetic-as-qualifying, assumed, out-of-limit, nonfinite, extra-field, and authority-bearing inputs; carry profile/source identity through MW2Q atomic receipts; prove only an explicitly exploratory synthetic rehearsal and clean resume | `issue/190-isaac-sim-host` / claim `1a32d4ecb84c2a61e77e61975c2333ed55061534`, implementation `4918d91a8d2d5f75b1208a9e4cfd37718baeb0c7`, CLI correction `a03bf71581b082f6e45b79e12d0c5f8361fb3a54` | COMPLETE — `ADMIT_EXPLORATORY_PROFILE_PIPELINE`. Synthetic source/profile compilation is byte deterministic, derives sixteen unique seeds, remains `EXPLORATORY_ONLY`, executes and assembles sixteen profile-bound receipts, and cleanly skips all work on resume. Synthetic qualifying and seed-tampered manifests reject without output or GPU work. No physical profile, qualification, camera/catalog/planner overlap, arm status, integration gate, write, movement, permit, transport, or authority changed. E-567 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2Q resumable independent GPU queues | retain the exact MW2S manifest; write one atomic hash-bound receipt per shard; validate before reuse; quarantine invalid bytes; assemble only exact allowlisted coverage; prove a clean all-skip resume and a copied one-corruption recovery that reruns exactly one shard while retaining seven byte-identical receipts; prohibit rendering, training, contact claims, hardware, transport, permits, and authority | `issue/190-isaac-sim-host` / claim `a7f14a938d9b8b7dc5b4f925ad6fb7b7c0693400`, implementation `47536d809f6ec579c4f3f0387b81d5da0e92edaa` | COMPLETE — `ADMIT_RESUMABLE_RESEARCH_QUEUE`. All sixteen exact receipts assemble; a clean rerun skips sixteen with zero loads/allocations; an altered copied receipt is hash-preserved in quarantine, exactly one shard reruns, and seven remain byte identical. This admits recovery mechanics only and changes no MW2/MW2R/MW2S decision, arm-lane status, integration gate, rendering, training, contact claim, hardware write, movement, permit, or authority. E-566 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2S persistent deterministic campaign sharding | freeze compact hash-bound manifests for disjoint eight-shard campaigns at 16,384 worlds; reuse one model load and allocation per persistent GPU worker; measure complete sequential and concurrent wall time including launch and receipt writes; require exact identity/coverage, disjoint seeds and state hashes, finite state, zero overflow, deterministic replay, and at least 1.70x concurrent scaling; preserve all MW2/MW2R results and prohibit rendering, training, contact claims, writes, movement, and authority | `issue/190-isaac-sim-host` / claim `1b539984cc2e80521a7464ec576ed77bc14796d4`, implementation `67c8d55f1f698dbf25d20f41c40e6a69fc43f027` | COMPLETE — `RESEARCH_ONLY`. All sixteen deterministic 16,384-world shards pass manifest, identity, disjoint-state, safety, repeatability, receipt, and sequential/concurrent state-parity gates. Each worker loads and allocates once. Concurrent wall scaling is 1.537x against the frozen 1.70x gate, so the performance gate remains failed. The replayable manifest/receipt mechanism is retained for research; no earlier result, arm-lane status, integration gate, rendering, training, contact claim, write, movement, or authority changed. E-565 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2R large-batch research specialization | preserve the failed general-purpose MW2 result; separately predeclare diverse-world 4,096/8,192/16,384 scaling, deterministic per-world pose seeds, independent GPU shards, concurrent two-GPU orchestration, overflow/finite/repeatability/memory gates, and a large-batch-only adoption decision; no rendering, contact claim, model promotion, or authority | `issue/190-isaac-sim-host` / claim `54098f4dca76630054005d717512a960133b4277`, implementation `0ce44c9cc665509b2ad070ba70cd386c1398df20` | COMPLETE — `RESEARCH_ONLY` with large-batch capacity confirmed. Both GPUs pass all single-device gates through 16,384 distinct poses and reach 5.225M/4.773M world-steps/s. Concurrent 4,096-world shards are safe but scale 1.665x against the frozen 1.70x gate, so large-batch adoption remains research-only and the failed MW2 result is unchanged. No rendering, training, contact claim, arm-lane status, integration gate, write, movement, or authority changed. E-564 records the evidence |
| AI/model + simulation | S2 MuJoCo Warp MW2 batch throughput, overflow, and repeatability | freeze 1/32/256/1,024/4,096-world matrices, CPU comparison, repeatability tolerances, performance gate, and memory/overflow inspection before results; benchmark each RTX 3090 independently; retain separate device shards; prohibit rendering, training, contact claims, hardware writes, and authority | `issue/190-isaac-sim-host` / claim `d085610481aa512f395fe633411a399665cb38b1`, implementation `082c69ad3ae0fd96e22b919f7cf1e356b4c43590` | COMPLETE — `RESEARCH_ONLY`. Both GPUs pass finite-state, world-preservation, zero-overflow, numerical-repeatability, and timing-CV gates. Both exceed 3x CPU throughput at 4,096 worlds, but achieve only 0.64x and 0.60x at 1,024 worlds against the frozen 3x requirement. The adoption gate remains failed and unchanged. No dual-GPU aggregation, rendering, training, arm-lane status, integration-gate change, hardware write, movement, or authority occurred. E-563 records the evidence |
| AI/model + simulation | S1/S2 MuJoCo Warp MW1 asset inventory and fixed-pose FK parity | hash-bind the governed URDF and referenced meshes; load through standard MuJoCo without actuator or contact claims; enumerate joint/link/axis/limit mappings and importer defaults; replay the existing governed fixed-pose corpus through standard MuJoCo and MuJoCo Warp; compare against retained RoCell/Isaac transforms; stop before rendering, contact, batching, or training | `issue/190-isaac-sim-host` / claim `e1188bdc8f8159c451d0256e2d4ab198a5875fa9`, implementation `02b5afd66a668946c6ba58f580bc4e759c986dab` | COMPLETE — direct load failed on intentionally absent inertia and is retained. The governed kinematic-only conversion explicitly marks placeholder inertia and blocks dynamics/contact. Six joints and eight links map exactly once; all three frozen poses pass RoCell/Isaac/standard-MuJoCo/MuJoCo-Warp hand-point parity, with zero hardware access or authority. E-562 records the evidence |
| AI/model + simulation | S1/S2 MuJoCo Warp MW0 isolated toolchain and host smoke | install the pinned external toolchain outside the repository; hash-bind resolved wheels and license metadata; run one minimal world on CPU and independently on each RTX 3090; inspect finite state and overflow; stop before RoArm asset import, rendering, training, or any authority change | `issue/190-isaac-sim-host` / claim `f8ba211f8c9231bc4886f4ec887730f19596405c`, implementation `e8acf8eda331a3ceaaa03db44d577098f1f8d2fa` | COMPLETE — the exact external candidate and all resolved wheels are hash-bound; the pre-import host lock passes; hardware-free mismatch tests reject before simulator import or model load; one 16-step world passes on CPU and both RTX 3090s with finite changed state and zero overflow. No RoArm asset, rendering, training, arm-lane status, integration gate, hardware write, physical movement, or authority changed. E-561 records the evidence |
| AI/model | S1 commissioned-key admission and seeded Sticky Keys replay | compare all printable-US base keys with the exact catalog; reject uncommissioned base/modifier keys; freeze and replay thousands of seeded strings including inter-character latch cases | `issue/190-isaac-sim-host` / implementation `253419cae37785578df71b17b2e28ec74ffd9b1c` | COMPLETE — 48 base keys are required; the current catalog covers 44 and lacks `BACKSLASH`, `GRAVE`, `LEFT_BRACKET`, and `RIGHT_BRACKET`, while `SHIFT` is separately missing. Lowercase `a` compiles against the current catalog; backtick and uppercase `A` fail closed on their exact absent targets. Seed `190055` plus five fixed edge cases produces 5,005 strings, 160,925 characters, 240,468 virtual actions, and 79,543 Shift presses with zero replay failures. Physical shifted capability remains blocked. E-555 records the evidence |
| AI/model | S1 five-key shared-catalog proposal and pre-render admission gate | hash-bind available geometry sources for `SHIFT`, `BACKSLASH`, `GRAVE`, `LEFT_BRACKET`, and `RIGHT_BRACKET`; distinguish provisional geometry from missing geometry; require camera visibility, parked-arm occlusion, and arm-runtime IK evidence before catalog installation; block v5.5 rendering until the shared catalog is complete and re-frozen | `issue/190-isaac-sim-host` / claim `c092f82b50a8b1bb79c985ab0cc99f0c2a251171`, implementation `6463c90f4d1b62e29f97a230cc7c443732fa37c4` | COMPLETE WITH BLOCKERS — four targets have hash-bound presentation-only seed geometry and remain uninstalled. `GRAVE` is blocked because the repository has no geometry source; extrapolating one pitch left of `1` would put a 14 mm safe region outside the keyboard. Camera visibility, parked-arm non-occlusion, and arm-runtime IK are pending. The 75-target catalog, compiler capability, and v5.5 identities remain unchanged; the render gate requires an admitted and re-frozen 80-target catalog plus a rerun power check. E-556 records the evidence |
| AI/model | S1 v5.5 simulation/commissioning gate separation, Grave measurement protocol, and archive containment correction | keep real-camera evidence out of the synthetic render critical path; require simulated parked-camera visibility, simulated parked-arm non-occlusion, and offline arm-runtime IK for rendering; retain physical visibility/non-occlusion as a hardware-use commissioning gate; freeze a direct-caliper Grave procedure; reconcile the four reviewed files above the archive ceiling | `issue/190-isaac-sim-host` / claim `cb4292356fadde26f97d6d05e3860d99584e35ef`, implementation `374c918bb97e221cede9d91a17070f3fc75cd92d` | COMPLETE WITH BLOCKERS — the render gate now contains only simulated camera, simulated parked-arm, offline IK, catalog, identity, and power evidence; physical camera checks block hardware use only. A hash-bound six-measurement-family, three-repeat caliper method awaits Grave readings. The arm runtime refuses an altered target source and its optimizer is explicitly locked to 46+29=75 targets, so its lane must accept the future re-frozen 80-target catalog before offline IK can run. The four reviewed v5.4 evidence files are named in source-distribution policy and the deliberate 6,311 ceiling now passes. No target or v5.5 identity changed. E-557 records the evidence |
| AI/model + simulation planning | S1/S2 MuJoCo Warp secondary-oracle integration architecture | define a governed, simulator-neutral advisory boundary; preserve Isaac as the visual reference; stage isolated toolchain, asset/FK parity, batch/overflow, paired-render, contact-differential, and optional training gates; prohibit command, permit, transport, and physical authority | `issue/190-isaac-sim-host` / claim `d06705e7c1929e88e90587552e6510cd083768d2`, implementation `7f0d1b7d2243162a0eee06508418d0cf17cca6b0` | COMPLETE — the new plan positions MuJoCo Warp downstream of the admitted schedule as a high-throughput secondary oracle, retains Isaac as visual reference, freezes MW0–MW6 scope and exit gates, requires overflow inspection and statistical repeatability instead of byte determinism, and keeps current v5.5, catalog, camera, runtime, arm-lane, and integration-gate state unchanged. No package was installed or simulator run. E-558 records the evidence |
| AI/model | S1 Grave top-surface measurement clarification and catalog-driven arm handoff | bind all Grave readings to the keycap top surface seen by the camera and contacted by the tool; require the arm lane to validate the loaded frozen catalog hash and enumerate its contents rather than encode target cardinality | `issue/190-isaac-sim-host` / claim `319e875f619d87af34d32b96d142a8312cef3b37`, implementation `46a189bf4b462c2412e578412a814c6a910f4ffc` | COMPLETE WITH MEASUREMENT PENDING — all six measurement families explicitly use the keycap top press surface and exclude the tapered wall, base, and switch housing. The arm handoff requires exact frozen-catalog hash validation, content validation, one screening result per ordered target, and report binding; hard-coded total or per-device counts are prohibited. Grave readings remain unset and no arm-lane status changed. E-558 records the evidence |
| AI/model | S1 guided Grave measurement and photo-derived simulation geometry | preserve the unfinished caliper session; separately estimate relative keyboard geometry from the admitted overview for simulation review only; hash-bind annotations and method; prohibit the photo estimate from satisfying physical measurement, placement, visibility, reachability, commissioning, or hardware-use gates | `issue/190-isaac-sim-host` / claim `45709ae8c1e3b60ceb203f5cefebbcf42e987f35`, implementation `15d6c5b306aab4c66b96333b4a9cae0496932235` | COMPLETE WITH BLOCKERS — a 31-anchor projective fit has 0.678 px median and 2.318 px maximum reprojection error. It proposes all five missing targets and exposes a mean +17.671 mm X / -6.708 mm Y displacement in the existing 12-key number row. A separate external 80-target candidate loads through the strict target-catalog parser with 51 keyboard and 29 phone targets. Under the current nominal 1920x1080 overview camera, all five added centers and complete safe polygons project in frame. The active 75-target catalog remains unchanged. The keyboard is outside the workcell fixture in the source image, measurement-reading count remains zero, and physical geometry, placement, visibility, reachability, commissioning, and hardware use remain blocked. Parked-arm non-occlusion, shared catalog installation/refreeze, offline IK, identity amendment, and power rerun remain dependencies. E-572 and E-573 record the evidence |
| AI/model | S1 Sticky Keys state-machine replay and commissioning checklist | model one-shot latch, lock hazard, shortcut-dialog hazard, disable-on-chord setting, final-state recovery, and host log evidence; exhaustively replay printable ASCII without enabling uncommissioned targets | `issue/190-isaac-sim-host` / implementation `4f0e4e58054908de7ca83f016940ca63ee83abf5` | COMPLETE — printable ASCII compiles to named virtual US key sequences and replays byte-for-character exactly under one-shot Sticky Keys semantics. Every uppercase or shifted symbol receives one Shift immediately followed by one base key; consecutive Shifts, a trailing latch, enabled five-Shift shortcut, and enabled two-key disable behavior are rejected. The capability receipt requires Sticky Keys enabled, one-shot latch, both hazardous settings disabled, plus host keystroke/modifier-state evidence. Current physical capability remains blocked because `SHIFT` is absent. E-554 records the evidence |
| AI/model | S1 deterministic planner modifier and phone-layer capability | select a one-arm shifted-character strategy; audit current catalogs; fail closed until required targets and commissioning evidence exist; keep target IDs and device state out of language-model output | `issue/190-isaac-sim-host` / implementation `78421d7a6f0c77aec7f4017ab0e61958b47a4922` | COMPLETE — Sticky Keys sequential modifier presses are selected for the first desktop milestone; simultaneous chords and Caps Lock optimization are disabled. The current catalog audit finds 46 keyboard targets without `SHIFT` and 29 phone targets without `key_shift`, `key_symbols`, or `key_letters`, so shifted keyboard and layered phone requests receive explicit uncommissioned-capability blockers while current lowercase requests remain accepted. The phone contract requires ADB verification before every future press. The capability contract is hash-bound, creates no coordinates or commands, and grants no authority. E-553 records the evidence |
| AI/model | S2/S3 B0477 delivered-YUY2 sensor-noise amendment | preserve physical-pilot v1/v1.1; freeze repeated static clear-scene bursts at measured low/nominal/high lighting; analyze temporal Y/U/V noise without assuming a distribution; require measured noise in the replacement synthetic camera path; leave the detection floor unset | `issue/190-isaac-sim-host` / implementation `21f7742d5fbcf1551200b986d47a48f2dda07076` | COMPLETE — the v1.2 pilot retains 32 full-native YUY2 frames after eight discarded settling frames at each lighting level with fixed camera, scene, device, settled park pose, optics, and manual controls. Original bytes, timestamps, hashes, dropped/duplicate-frame counts, lighting, and pose bindings are required. Per-pixel temporal Y/U/V mean, sample standard deviation, median, robust sigma, spatial maps, empirical residuals, adjacent-frame differences, and clipped counts are retained. Future simulation starts losslessly, prohibits a JPEG intermediate, and uses the measured delivered-domain profile. No camera frame exists yet; the signal floor and noise multiplier remain unset; escrow, arm-lane status, integration gates, hardware writes, physical movements, and physical authority are unchanged. E-552 records the exact artifact and validation evidence |
| AI/model | S2/S3 residual v5.4 multi-axis dependence and training renderer | preserve the audited v5.4 fixture; measure error dependence by scene, target, actual obstruction asset, lighting appearance, and target-by-asset interaction before evaluation sizing; render and admit only frozen training/development identities; keep evaluation identities pixel-free; require positive arm-mask overlap validation before mid-motion observation | `issue/190-isaac-sim-host` / claim `d5119e64b62e8afb891644fc3b0e8f97916c372b` | ACTIVE — exact reconstruction of all 28,800 rejected v4.2 development predictions matches the retained probability hash. Scene-only dependence understates the retained transfer evidence: pooled-miss ICC is 0.000338 by scene, 0.006591 by target, 0.001374 by lighting, and 0.035001 by obstruction-variant proxy; cable-miss ICC is 0.001362 by scene and 0.026432 by target; dark-rubber-cable miss ICC is 0.001751 by scene and 0.048116 by target; visible false-stop ICC is 0.000895 by scene and 0.055843 by target. V4.2 lacks actual per-asset identities, so cable asset dependence is unestimable rather than assumed independent. Before evaluation rendering, v5 must compute one-way clustered upper bounds for every safety gate by scene, device/target, actual descriptor signature, and appearance. When target and asset axes both apply, it must also compute a two-way multiway cluster-bootstrap bound by resampling target and asset separately. Evaluation sizing and reporting use the maximum applicable one-way or two-way bound, with ICC 0.30 when an applicable axis is unestimable. Safety gates remain frozen and evaluation resizing is allowed only while pixels remain unopened. Smoke C hash-binds exact procedural descriptors and analytic perturbed-FK capsule masks; its empty parked-pose masks authorize only the parked workflow. Mid-motion observation remains unauthorized until held-out positive-overlap poses compare the analytic mask with simulator truth used only as an audit label and freeze acceptance thresholds. Campaign03 preserved two valid 2,304-row PASS shards but both wrappers then failed because `Get-FileHash` was unavailable. Campaign04 is complete: both queues PASS, the exact 38-shard allowlist admits 64,800 byte-unique observations and 5,400 references, with 43,200 training, 21,600 development, and zero evaluation rows. JPEG audit E-547 finds the extra local encode negligible but raw-to-first-JPEG loss unmeasured. E-548 freezes a training-only, 144-pair raw/JPEG/YUY2 population and independent pass/fail rules before comparison: JPEG failure blocks candidate training; YUY2 failure blocks sim-to-real interpretation; neither outcome is physical qualification. E-549 adds a hash-verified mid-campaign checkpoint on a separate USB physical disk. E-550 records complete admission plus the frozen 144-pair fidelity result: JPEG fails all three distortion-to-signal limits and YUY2 fails its q95 and worst-row distortion limits, so candidate training and synthetic YUY2 transfer interpretation are blocked without changing a limit. E-551 attributes the YUY2 ratio failure primarily to near-zero visible-boundary denominators while retaining three sub-two-level and five sub-three-level safety-row delivered signals as unresolved detectability evidence; it selects no replacement threshold. Evaluation remains unopened; no model, threshold, arm status, integration gate, hardware write, physical movement, or physical authority changed |
| AI/model | S2/S3 residual v5.4 exact rotation and development-support audit | freeze 224 evaluation scene identities and deterministic 12-target assignments; preserve evaluation as identity-only; independently audit balance, split isolation, hashes, power interpretation, and development cable/dark-cable support before renderer work | `issue/190-isaac-sim-host` / source `1d717b246932ce4b3230ecc8f20df886f26caf00` | COMPLETE — all 224 unique evaluation scenes and seeds carry 12 unique targets, include both devices, and produce 96,768 unopened identities. Sixty-three targets appear in 36 scenes and twelve in 35. Development retains the same 21,600 rows for both candidates; per target it supplies 96 visible, 192 obstruction, 96 cable-abstain, 48 dark-cable-abstain, and 24 dark-boundary-visible rows across eight scenes and three appearances. The independent audit passes and permits training/development renderer implementation only. Evaluation rendering remains prohibited until one candidate and threshold are frozen after development. Power summaries explicitly state that 0.5% miss and 3% false-stop rates are assumptions required to demonstrate the bounds, not predictions that v5 will pass. No images, training, threshold, evaluation access, arm status, integration gate, hardware write, physical movement, or authority changed |
| AI/model | S2/S3 residual v5.3 safety-gate role and complete power amendment | preserve v5/v5.1/v5.2; classify pooled, cable-family, dark-cable, and visible false-stop confidence bounds as evaluation safety gates; retain per-target AUC and margins as development diagnostics with a loose broken-target floor; and size an exact balanced rotation against every safety gate before any render | `issue/190-isaac-sim-host` / claim `c8a9e4d0ffd89e035087afe783deb6cfdc8dfcd6` | COMPLETE — development selects with point safety rates plus legacy diagnostic floors of 0.90 minimum target AUC and 0.95 q05 target AUC; q05 margin is reported rather than powered. Single-use evaluation alone requires one-sided 95% upper bounds no greater than 2% for pooled, cable, and dark-cable misses and 6% for visible false stops. With miss alternatives 0.5%, false-stop alternative 3%, ICC 0.05/0.30, and a 0.93 planning cushion above the 0.90 requirement, the first tested balanced design is 224 scenes × 12 targets = 96,768 rows, 35–36 scene exposures per target, and pessimistic Bonferroni joint lower bound 0.93055. V5.4 now freezes and audits the exact rotation while keeping evaluation unopened. No images, training, threshold, evaluation access, arm status, integration gate, hardware write, physical movement, or authority changed |
| AI/model | S2/S3 residual v5.2 power attribution and render-efficiency analysis | preserve the v5/v5.1 blocker; report power by individual gate including every-target and q05 AUC; disclose the assumed true performance; compare complete-grid rendering with balanced scene/target rotation; and analyze development-selection versus evaluation-proof roles without changing a gate or rendering data | `issue/190-isaac-sim-host` / claim `d8c3103169663a6dcc3e611261834afbea64df56` | COMPLETE — v5.1 used the minimum modeled-gate power, not a product or true joint probability. At ICC 0.05 the eight-scene result is limited by every-target AUC power 0.000033; at ICC 0.30 all three modeled gates fail. Cable-family, dark-cable, q05 AUC, and q05 margin gates were not powered, and the assumed AUC 0.98 has zero slack above the q05 0.98 gate. A 256-scene/24-target balanced rotation reduces rows 68% to 221,184 and gives at least 81 scene exposures per target, with limiting marginal power 0.910544 but a dependence-free Bonferroni joint lower bound 0.897144 across only the three modeled gates. It remains blocked pending complete effect-size and gate modeling plus a fixture decision about development selection versus evaluation proof. No fixture, gate, image, training, evaluation access, arm status, integration gate, hardware write, physical movement, or authority changed |
| AI/model | S2/S3 residual v5.1 pre-render gate and power correction | preserve v5; restore the 6% visible false-stop gate, explicitly retain the 2% pooled all-obstruction miss gate, label all synthetic lighting provisional, prohibit a simulation pass from selecting a hardware remedy before the physical pilot, and run correlation-aware power analysis at 21,600 development rows before renderer work | `issue/190-isaac-sim-host` / claim `aacbda9aeeb2e808d167b9fbba0aeeb98c424cd3` | COMPLETE — v5 remains byte-identical, its silently loosened 10% visible false-stop ceiling is corrected to the frozen 6%, and its 2% pooled all-obstruction miss ceiling is confirmed. The original eight-scene/21,600-row development plan has conservative joint power 0.000033 at ICC 0.05 and 0 at ICC 0.30, so rendering is blocked. The minimum tested plan reaching at least 0.90 power in both scenarios is 256 scenes/691,200 rows, but that is a planning result and is not authorized for rendering. Lighting remains provisional and no simulation pass may select a hardware remedy before the physical pilot. No images, training, evaluation access, arm status, integration gate, hardware write, physical movement, or authority changed |
| AI/model | S2/S3 residual v5 synthetic research predeclaration | preserve the rejected v4.2 result and unchanged RGB baseline; explicitly amend the earlier physical-pilot-before-successor sequence under the owner's instruction to continue simulation-only robustness research; freeze edge/texture and multi-scale inputs, obstruction-identity-disjoint train/development/evaluation assets, realistic calibration/pose perturbations, hard-case families, clustered gates, and unopened evaluation before rendering | `issue/190-isaac-sim-host` / claim `8944f6a02534b414858777b050113c8b8ced1e86` | COMPLETE — two offline candidates are frozen: edge/texture at 96 px and a 96/192 px multi-scale version, capped at 2M/3M parameters. Sixteen/eight/eight scene identities, three lighting identities per split, and 14/10/10 obstruction assets are pairwise disjoint; evaluation retains 21,600 identities and zero images. Training/development plan 43,200/21,600 rows with unchanged baseline and v4.2 comparisons, a 99.5% memorization gate, cable/dark-cable miss ceilings, target-local AUC/margin gates, perturbed arm masks, and required hard-case reports. A development pass must feed actual ModelMotionBatchV2 outputs into six simulated missions with zero wrong-target contacts. The physical pilot remains required for runtime lighting, transfer, and qualification. No render, model, threshold, evaluation access, arm status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 B0477 exact-mode, optics/control, and print-scale commissioning amendment | bind the repository-authoritative 5472x3648 YUY2 9 fps mode; require fixed focus, exposure, gain, and white balance; require separate calibration for any mode whose crop/bin/scale transform is not proven; freeze distributed X/Y caliper measurements without inventing a tolerance; preserve the earlier 4 fps blocked receipt as failed evidence | `issue/190-isaac-sim-host` / claim `d5e26be9ca2a3e03cd10d49460d32db367da73be` | COMPLETE — three authoritative repository bindings agree on full-native 5472x3648 YUY2 at 9 fps. Any alternate crop/bin/scale/MJPG mode requires separate calibration unless its transform is measured and reviewed. Manual focus/aperture and exposure/gain/white balance must be locked with automatic controls disabled and hash-bound. Board scale requires at least four distributed X and four distributed Y calibrated-caliper measurements across opposite extents; the tolerance remains unset. The earlier 4 fps receipt is preserved as failed evidence. No camera was opened, no physical value was guessed, and no arm status, integration gate, installed calibration, model evaluation, or physical authority changed |
| AI/model | S2/S3 physical ChArUco camera probe and calibration capture | identify the actual Windows camera without assuming an index; probe read-only frames; retain a blocked receipt if no camera or board is available; otherwise capture broad frame coverage and report train/held-out reprojection evidence | `issue/190-isaac-sim-host` / claim `b13e492636178e54ad502dfb7bfa9c8df1084c79` | BLOCKED — Windows reports zero connected Camera/Image-class devices. The isolated OpenCV 5.0 environment passes a 24-corner detection smoke against the retained 5x7 board, but that board is tooling-only and does not satisfy the production 12x9, 30/22 mm, DICT_5X5_1000 rigid-board contract. Capture count, calibration count, hardware writes, and physical movements are zero. E-532 corrects the preserved probe's erroneous 4 fps field: connect and identify the B0477, verify its full-native 5472x3648 YUY2 9 fps mode, lock optics and image controls, and retain/print/measure the required rigid board before 24 training plus 8 held-out views are captured. Approximately 0.5 px remains a diagnostic target rather than an automatic qualification threshold. No arm status, integration gate, model evaluation, installed calibration, or physical authority changed |
| AI/model | S2/S3 post-isolation pose and escrow-scope amendment | require settled-pose evidence after servo-power isolation and constrain the single escrow session to a non-statistical real-world sanity check | `issue/190-isaac-sim-host` / claim `09303487afcf6abe840d727efdcb245971e2010a` | COMPLETE — post-isolation pose evidence now requires at least two stable silhouette frames against the commissioned park profile before every capture group and at session end; passive measured joints are optional and commanded state is prohibited. Every image binds the pose-evidence hash, while failed checks or capture-phase repositioning invalidate but retain the row. The unopened one-session escrow is a real-world sanity check only and cannot estimate a 2% miss rate or qualify deployment; powered real evaluation requires a separate authorized capture. No pixels were captured, no lighting or silhouette tolerance was guessed, and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 physical pilot label, custody, and energy-state predeclaration | freeze safe-region coverage labels and ambiguity scoring, dual real-label measurement, measurement-versus-escrow use, and de-energized capture before the first physical session | `issue/190-isaac-sim-host` / claim `579ca70f1fe95bcafd4cd94e447fbbf0c95fecef` | COMPLETE — 10% coverage is clearly visible, 20% is a retained and separately scored boundary probe, and 30%/60% are clearly obstructed. Coverage requires a measured placement template plus an independent score-blind hand mask; disagreement above 0.05 becomes retained `LABEL_UNRESOLVED`. Two sessions may select a remedy but cannot train; one session is unopened escrow until checkpoint and threshold freeze. Every capture requires verified servo-power isolation and controller disconnection, with zero capture-phase writes or movements. V4.2 remains rejected, no lighting limit or v5 is selected, evaluation remains unopened, and no arm-lane status, integration gate, or execution authority changed |
| AI/model | S2/S3 residual v4.2 remedy classification and physical evidence handoff | classify the preserved failure across model input, data, and workcell controls; define a bounded real-camera reference/cable/hand and admitted-lighting survey before any v5 predeclaration; keep cable detection as a backstop | `issue/190-isaac-sim-host` / claim `80d4804c250f4a822c717e6c4bc2b87048d0079e` | COMPLETE — the strict classification binds both retained v4.2 reports, preserves its rejection, keeps cable detection required, and selects no v5. A three-session physical pilot covers keyboard `EQUAL/F/G/H/I`, phone `key_a/key_b/key_c/key_period`, clear/dark-cable/translucent-cable/hand cases, 20/40/60% dark-cable coverage, and measured low/nominal/high lighting. Edge/texture input is the first candidate, resolution second, and weighting third. The lighting limit remains unset until measured real-camera samples define the runtime-admitted envelope. Evaluation remains unopened and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual v4.2 threshold and robustness gates | select a threshold using only the consumed synthetic development rows; measure scene-cluster error bounds, worst appearance/family behavior, and robust per-target margins before any evaluation render | `issue/190-isaac-sim-host` / renderer `3eff71ec2162edd56f9d3998fc043f60f6b75c5a`, gate tools `4ee2e0a68f70aa2f86138706c5771c741bb43e6c`, CNN runner `f9b5ebdc60f9b18b0aeeebc5f0a6d295e03c4bd5`, uplift evidence `d5719adc1cee473ecea1b73ba3b3fe663bed5dda`, frozen scorer `a57896506f9997858e047fbc77707f1100e88e4e` | COMPLETE — all 19 frozen thresholds fail on consumed synthetic development despite strong AUC. The least-bad threshold, 0.55, has 3.0% cable misses against 2.0% and 8.72% warm-side false stops against 6.0%; the target quantile-margin gate is -0.06177 against +0.05. The candidate is rejected, its output remains an uncalibrated ranking score, and evaluation stays unopened. Next work must attribute the failure to model input, data, or a workcell rule before a successor is designed. Real-camera clear references plus cable/hand captures remain required. No arm-lane status, integration gate, hardware write, physical movement, or execution authority change |
| AI/model | S2/S3 residual v4.1 reference-pair smoke and validity | render a bounded training-only reference/observation pair smoke; compare self-crop versus surrounding-context normalization under heavy coverage; add fail-closed commissioned-reference age, camera, fixture, target-map, and lighting validity; freeze initial real-reference pair collection handoff | `issue/190-isaac-sim-host` / implementation `693153ef3a0ada0ca6c7efe0d61a1177d2b0b9f7`, registry correction `02544ca0` | COMPLETE — 192 independently verified training observations bind four clear references to F/G/H/I; independent self-crop normalization ranks labels better than the current reference-context transform on this small shard, so both remain candidates; reference freshness fails closed on age, camera, fixture, target-map, and lighting changes; evaluation remains unrendered and no model training, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual v4.1 diagnostic and predeclaration correction | explain the 500-row memorization failure with opposite-label similarity, error attribution, and a spatial control; run per-target gate power analysis; freeze independent reference lighting, photometric normalization, robust quantile separation, and powered pooled/per-target gates under a new schema before rendering | `issue/190-isaac-sim-host` / claim `e329e22c19b86071e9e1a8ae0fd84485ad472b0f`, diagnostic `9ecb306ba95c1d68af811307d871a1732872a2eb`, deterministic-pool fix `62248aceb79ce5a58904f1f587d3724b7667660b`, v4.1 `13ced61a755d36cd4c7cdfd40d2b1d323626d36a` | COMPLETE — no opposite-label duplicates exist; legacy global pooling again reaches only 0.834 accuracy, while the identical spatial 6x6 control reaches 1.0 accuracy and 0.00963 loss; power analysis rejects per-target binary gates; v4.1 independently varies reference lighting, normalizes photometry before differencing, uses pooled cluster error gates plus robust per-target AUC/quantile margins, and preserves zero rendered evaluation pixels and zero authority |
| AI/model | S2/S3 residual v4 reference-comparison predeclaration | freeze clear-reference pairing, spatial difference representation, per-target training normalization, fresh mutually disjoint scene and lighting identities for training/development/evaluation, memorization and per-target gates, and empty evaluation before rendering | `issue/190-isaac-sim-host` / claim `a787628496fb4d798506427b84510d3f52450f81`, implementation/evidence `b61cc1dbfee7cc939dc29274d3ecb105f634f938` | COMPLETE — 12 training, 8 development, and 8 single-use evaluation scene identities plus 4 disjoint lighting identities per split are frozen; training/development contain 43,200/28,800 planned pairs, 28,800 evaluation pairs are identities only and unrendered; clear-reference RGB, observation RGB, absolute difference, spatial pooling, training-only per-target normalization, a mandatory 500-row memorization pass, and every-target AUC/margin gates are frozen; no render, training, development access, evaluation access, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual v3 training-only causal audit | identity-plus-geometry baseline, training per-target AUC/margins, 500-example memorization, target-G crop/label review, variant attribution, and split identity isolation using only admitted training bytes plus read-only development metadata | `issue/190-isaac-sim-host` / claim `81f7d7a17fb5816a7bf4642eaa9176f636334a21`, implementation `3c3681e95c5bee2bc7eab9666e61b54093179723`, outlier revision/evidence `ad1b9bed6ba46560ac51e4628dcbdb9b496e108a` | COMPLETE — identity plus geometry is exactly chance at 0.500 AUC; the CNN ranks within every training target (AUC 0.841–0.991, median 0.960) but has zero strict positive margins, fails to memorize the balanced 500-row control (0.834 accuracy, 0.4417 loss), and shows lighting/scene outliers for G; scene identities are disjoint but all four appearance identities overlap; development pixels and evaluation remain unopened, and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 rejected residual v3 development diagnostic | reconstruct unchanged rejected-model probabilities from exact external bytes; bind model, scorecard, admission, lineage, fixture, and target catalog; attribute consumed development failure by scene, appearance, variant, family, and target; recommend only a fresh successor; no threshold change or evaluation access | `issue/190-isaac-sim-host` / claim `9598c58a1d11224f0d46a4cc32347241852faba3`, implementation `b535cf7297acba80845f7b7b98ef086a31b95555`, inference fix `ba63176d3e84084149629914d6a1b9245f825280`, evidence `7147e51bf5a37c1eb89e4fa16dfd6ca181e9116e` | COMPLETE â€” exact development probabilities reproduce; AUC is 0.946, but zero scenes, appearances, or targets are locally separable, clear observations overlap obstruction families, and keyboard G has the worst -0.8240 margin; checkpoint and threshold remain unchanged, evaluation is absent, and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual v3 frozen training and development gate | consume only the exact admitted 43,200-observation corpus and renderer lineage; implement the frozen RGB target-crop CNN, target/label/variant/base-scene balanced sampling, paired-appearance consistency loss, scene-cluster bootstrap, worst-appearance and worst-family gates, and target-local separation; retain model and scorecard externally; evaluation remains absent | `issue/190-isaac-sim-host` / claim `7080f9ef1c65714d1fa45d67b3052376f3cfb765`, implementation `164f4c35e11dd831995975cc9767b453dabb3f1a`, evidence `c670f2c90319a3b9ae396e7c37ad518e92f39ad4` | COMPLETE â€” two byte-identical frozen runs reduced combined loss from 0.5640 to 0.3170 but all 19 thresholds failed; zero of 75 targets are locally separable and worst margin is -0.8240, so the model is rejected, evaluation remains absent, and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual v3 Isaac renderer and admission | implement the exact fresh-scene 3D renderer plus independent verifier/receipt; render all frozen training/development scenes, paired appearances, targets, and variants externally; reject split leakage, source reuse, duplicate bytes, and geometry/material/depth/overlap drift; no training or evaluation | `issue/190-isaac-sim-host` / `14c3d2ff0cffd6bad1a7bb96194f6efa98c9348c`, `04d333b7db120d10e6e5b818128fcbfd04cdd90c`, `8300b4a639ca9542c74a6e8d0baf04322bd4f4c9`, `20616baf8bc258ceb0247f6938009c66d0727375`, `6ba49ffaaf99d7782f3f1527482a63eb9094fdc7`, `7361d84e45e9e4fb8af66ba0cdf87ff2761c111d`, `e0be81c8186682172e55005e3fbdc9bd028d4da6`, `a2de66b02eec84eccf305893716b367975b6aac3`, `57a9ce498ba24850a666ea2d0fe0e09ff743cd88` | COMPLETE â€” all 43,200 frozen observations across 75 targets pass exact independent admission with 43,200 unique RGB hashes, 28,800 training and 14,400 development rows, zero evaluation rows, explicit per-shard renderer lineage, and no training, arm-lane status, integration gate, hardware write, physical movement, or execution authority change |
| AI/model | S2/S3 residual v3 independent-scene predeclaration | freeze disjoint Isaac base-scene identities, 3D obstruction geometry/material/depth/transparency ranges, paired appearance-invariance training, target-local positive-margin development gates, and empty evaluation before rendering; no authority fields | `issue/190-isaac-sim-host` / `a0aec0a58ccc1f939f4ca48945397d8b550d5d1b`, `29025a142f6d2eca0e67d95d85663e029dc3dc0d` | COMPLETE â€” 8 training and 4 development base scenes, four paired appearances, 12 variants, exact RGB-only training plan, and clustered/local-margin gates are frozen before rendering; images, training, and evaluation remain absent, with no arm-lane status, integration gate, hardware write, physical movement, or execution authority change |
| AI/model | S2/S3 rejected residual v2 development diagnostic | verify the exact fixture, renderer contract, admitted dataset, rejected model, and scorecard; reconstruct development probabilities; attribute separation and errors by variant, appearance, view, and target; recommend only a fresh successor design; no retraining, threshold change, or evaluation opening | `issue/190-isaac-sim-host` / `6419340feaf3abb0050a93bffa54482aff5dc608`, `cc2d6b0ddea32359e8fc6c3cd957b14e336450c5` | COMPLETE â€” exact probabilities reproduce; AUC is 0.8975, all 75 targets are locally nonseparable, and appearance plus cable/tool/compression weaknesses explain the failed gate; checkpoint and threshold are unchanged, evaluation is closed, and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual v2 loader, frozen training, and development gate | verify the admitted external manifest and every crop; materialize exact train/development rows with view and appearance identities; implement only the frozen RGB CNN v2, balanced sampling, threshold grid, and whole-view bootstrap; retain model/scorecard externally and an aggregate repository receipt; evaluation remains absent | `issue/190-isaac-sim-host` / `454d5e76b816c271561d8a77d1b89f6692e295c0`, `e6de99167656734f86d60abfd76593a1f156f4bc` | COMPLETE â€” two runs are byte identical, loss decreased, but all 19 thresholds fail the frozen point, whole-view, or worst-appearance limits; the model is rejected, evaluation remains absent, and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual v2 renderer contract and admitted crop campaign | preserve the v2 fixture; bind the exact base scene and deterministic camera-warp rule in a separately frozen renderer contract before generation; implement external crop rendering and fail-closed admission for split/identity/pixel/overlap/duplicate rules; exact inventory; no training or evaluation | `issue/190-isaac-sim-host` / `4dcadad59c64195d09986782dbee2793b89c3c2e`, `0a307a2f51f3ce82db240312542e5cb02cd8ca0c` | COMPLETE â€” the contract preceded image generation; two independent 37,125-crop builds are byte identical and globally unique, all admission rules pass, evaluation remains empty, and no model metric, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual successor v2 predeclaration | freeze fresh group-isolated source-pose and appearance identities; prove adjacent distractors change retained pixels while preserving zero target overlap; broaden cable/tool/degradation severity; freeze model, threshold, clustered development gates, and empty evaluation before generation | `issue/190-isaac-sim-host` / `d754434045bac59b177be107925ac2a27aba7bda` | COMPLETE â€” 27,000 training and 10,125 development observations are frozen across disjoint parked views/appearances and 15 variants; renderer admission prevents the v1 duplicate-distractor defect; no image, model, training, evaluation access, qualification, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 rejected residual-candidate diagnostic | read-only reconstruction of the retained candidate's consumed development probabilities; per-variant and per-target attribution; exact source/model/dataset binding; successor-design recommendation without checkpoint, threshold, evaluation, or authority changes | `issue/190-isaac-sim-host` / `343b4b548bb9b92745af71bd6d7cf4cd50c607cd`, `60fcebe9513f449f6c93c8e3dd44b96e12506312` | COMPLETE â€” exact probabilities reproduce; AUC is 0.7585, all 75 targets are nonseparable, all adjacent-distractor crops duplicate clear crops, and degradation/cable/tool cases overlap; checkpoint and threshold are unchanged, evaluation is closed, and no arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 residual-obstruction crop materialization and development gate | materialize only the frozen 1,200 crop specifications; exact independent inventory; train only `target_crop_residual_cnn_v1` with the frozen seed and hyperparameters; target-cluster development scoring; preserve failures; evaluation remains empty and no authority is created | `issue/190-isaac-sim-host` / `cf7aa8613876ae1b4c70f73b8322cf8007b4367e` | COMPLETE â€” two crop builds, inventories, models, and scorecards are byte identical; no threshold passes both frozen development limits, so the candidate is rejected and no evaluation access, qualification, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 parked residual-obstruction pretraining freeze | deterministic synthetic crop-campaign fixture from retained fixed-camera practice bytes; target-balanced clear/distractor/cable/tool/hand/foreign-object/glare/degradation cases; pose-separated train/development identities; frozen small offline model plan and asymmetric development gates; no evaluation source, training, render, or authority | `issue/190-isaac-sim-host` / `7e0509d0828a557c04a38aef47fc51c49dea70c8` | COMPLETE â€” 1,200 procedural crop specifications cover 75 targets with pose-separated train/development identities and a frozen offline model/gate plan; no crop images, model, training, development metric, evaluation access, qualification, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 v16 geometry-first fusion replay | independently recompute development target overlap from retained Isaac robot-mask atlases, reconcile frozen labels and learned decisions, conservatively replay geometry/learned OR fusion with explicit ambiguity accounting, strict report/schema/tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `a576f6658acf7ccab6da067fcce4f6ee152ac962` | COMPLETE â€” all 4,800 pose-target overlaps and 14,400 rows reconcile; fused misses are zero at all 17 offsets and worst strict false stops are 881, but the mask also generated the label, no measured dilation or projection qualification exists, v16 remains rejected, and no evaluation access, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 v16 grouped-neighborhood development diagnostic | read-only attribution of the consumed v16 development failures by source block, pose, target, lighting, and offset; strict schema, deterministic aggregate report, tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `bc880ad9087d18b99becf7c4db765d8b77edb026` | COMPLETE â€” 348 misses span 28 poses, 46 pose-target pairs, eight source blocks, 13 targets, and all three lighting identities; the dominant pose-target contributes only 11.78%, so v16 remains rejected and no threshold, evaluation access, promotion, arm-lane status, integration gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 v16 grouped-neighborhood successor | frozen fresh pose generator with source-interval group isolation, failed-neighborhood coverage, fresh lighting identities, separately frozen train/development split, target-aware training revision, clustered development gate, Isaac campaign, tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `ce6172b8b43a22613d3eaf128cc80873423e076a` | COMPLETE â€” point gate passed through 2 mm, but the 64-pose missed-abstention UCB is 2.8216% against the frozen 2% ceiling, so v16 is rejected; v14 evaluation and v15 development remain consumed, no evaluation source opened, and no arm-lane status, integration-gate, hardware write, physical movement, or execution authority changed |
| AI/model | S2/S3 v15 pose-cluster development diagnostic | development-only failure attribution by pose, target, lighting, and offset; frozen diagnostic schema and deterministic report; v16 design recommendation without evaluation access or candidate promotion; tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `048bb41acd2cbe6350672e82f402bc54d096cc12` | COMPLETE â€” 58 in-bound misses occur in seven poses/eight pose-target pairs; one pose/MINUS pair contributes 46.55% and the top two poses 70.69%; v15 remains rejected and consumed; no evaluation access, render, threshold change, promotion, arm-lane status, integration-gate change, hardware write, or physical movement |
| AI/model | S2/S3 pose-diverse Isaac successor | frozen zero-authority static training/development pose fixture derived from the governed schedule; new v15 Isaac campaign and lighting identities excluding v14; deterministic dataset build; target-conditioned successor training and development-only selection; tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `ba1ea9bf43098eb37e6d17c4785d428023cc1aab` | COMPLETE â€” reproducible `FAILED_DEVELOPMENT_GATE`; point estimates pass at 1 mm but missed-abstention pose-cluster UCB is 3.2491% above the frozen 2% ceiling; no evaluation opening, localization qualification, arm-lane status, integration-gate change, hardware write, or physical movement |
| AI/model | S2/S3 deterministic retained-package index builder | read-only custody-declaration schema and builder; exact regular-file inventory; campaign/digest/path/custody binding; deterministic evidence-index output; missing/extra/duplicate/symlink/changed-file rejection; tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `e7b16c2de470a1c01040fab0be17e22b44cdfcdc` | COMPLETE â€” inventories only already retained files and externally declared custody; no evidence generation, collection, qualification, arm-lane status, integration-gate change, hardware write, or physical movement |
| AI/model | S2/S3 parked-pose file-backed preflight | strict evidence index and preflight receipt schemas; contained regular-file/hash/size/type/custody reconciliation for every campaign binding; missing/altered/duplicate/symlink/extra-artifact rejection; explicit no-campaign blocked receipt, tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `ad2c8ce9aeee11e0b6fcfddcda1e0c5a6afa72ed` | COMPLETE â€” retained preflight is blocked because no campaign package exists; custody labels remain claims pending owner review; no collection, qualification, arm-lane status, integration-gate change, hardware write, or physical movement |
| AI/model | S2/S3 parked-pose qualification protocol | strict synthetic/physical campaign manifests and observation records; completed-park/session independence checks; ChArUco drift and repeatability bindings; residual obstruction and fused-decision scoring; exact binomial bounds; explicit incomplete receipt, tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `9dc1f7fa6642b6468bb5df85d0a6bed33e0fa592` | COMPLETE â€” retained receipt is explicitly incomplete because no campaign was collected; no model qualification, deployment claim, arm-lane status, integration-gate change, hardware write, or physical movement |
| AI/model | S2/S3 correlation-aware evaluation power tool | grouped v13/v14 intra-pose-correlation estimation; empirical upper-bound and pessimistic-correlation scenarios; deterministic pose-cluster simulation and sample-size recommendation; synthetic planning receipt, tests, registry, shared workplan, and evidence ledger | `issue/190-isaac-sim-host` / `3fe8e57eca77dcd369be79e188d6ae2b0724d39a` | COMPLETE â€” aggregate synthetic planning only; 2,048-pose broad-campaign recommendation; no candidate selection, new render compute, arm-lane status, or integration-gate change |
| Unclaimed | S2/S3 | physical-camera deployment qualification and safe-region-fit precision evidence | â€” | AVAILABLE |
| ARM | S4 | collect four physical-original `camera_support_optics` bindings through onboarding, then run the ARM-070 intake; no synthetic promotion | ARM-071 | WAITING_FOR_ORIGINALS |

## Worker update procedure

Each worker follows this process for every increment:

1. Pull/fetch current repository state and read this document, `CONTRACT.md`,
   and `MODEL_COMMAND_RUNTIME_IMPLEMENTATION_PLAN.md`.
2. Confirm the selected stage and the other lane's latest evidence.
3. Add or update one active work claim. Do not claim broad directories when a
   narrower path is sufficient.
4. Work on a feature branch or otherwise coordinate before editing shared files.
5. Make one bounded change. Do not mix model training, schema migration,
   controller behavior, and physical testing in one unreviewable increment.
6. Run lane tests plus the shared boundary suite affected by the change.
7. Append an evidence row. Update only the worker's owned lane status.
8. If both lanes are ready, run the shared integration gate using actual producer
   outputâ€”not a hand-authored substituteâ€”and append an `INT` evidence row.
9. Review diff, run the repository audit, commit, and push or open a pull request
   according to the repository contribution process.
10. Leave failed evidence visible and name the precise next dependency.

## Merge and conflict rules

- AI workers primarily own `software/ai/rocell_ai`, training/evaluation assets,
  AI tests, and the AI-lane portions of this plan.
- Arm workers primarily own `software/src/rocell`, arm/runtime tests, controller
  adapters, and the arm-lane portions of this plan.
- Shared schemas, shared model types, this stage board, and integration tests
  require cross-lane review.
- Do not silently change a field's meaning while retaining its schema version.
- Do not loosen a consumer because a producer emitted invalid data; correct the
  producer or perform a documented schema migration.
- Resolve concurrent ledger edits by retaining both evidence rows in chronological
  order. Never discard another worker's evidence to resolve a Git conflict.

## Immediate coordinated work order

1. **S1 software boundary â€” complete for zero authority:** v2 producer bytes,
   strict decoding, trusted registry, freshness, mutation rejection, and ordered
   `H,H,I` ingress are covered by the shared conformance profile.
2. **AI S2/S3:** qualify the implemented precision adapter from final-camera
   physical originals and reduce or bound localization uncertainty inside the
   applicable key safe regions. The current 14.400834977 mm synthetic bound is
   retained evidence but may not populate deployment qualification.
3. **Arm S4:** collect the four physical-original camera/support/optics bindings
   already named by ARM-070; do not synthesize the trusted registry from model output.
4. **Integration S2:** rerun the conformance profile using actual qualified AI
   output and physical-original registry records, beginning with one keyboard target.
5. Continue measured planning and controller qualification independently. Speed,
   clearance, dynamics, encoding, transport, and retry remain arm-owned. Use the
   [optimized typing execution plan](../../docs/OPTIMIZED_TYPING_EXECUTION_PLAN.md)
   for the ordered T1-T6 implementation and qualification gates.
6. Require independent device-effect verification before expanding from one key
   to strings or phone workflows.
7. Rebuild `arm072_model_arm_operational_readiness.json` after any retained
   source advances. Do not begin a single-action review unless all six stage
   assessments are READY; the report itself never grants dispatch authority.

## Definition of shared completion

The shared program is not complete merely because the model predicts plausible
coordinates or the arm follows manually supplied commands. Completion requires:

- supported user text produces the intended deterministic plan;
- fresh qualified perception produces a correctly bounded named target;
- the exact batch survives strict arm admission;
- measured planning produces a smooth collision-screened trajectory;
- one controlled writer executes it without ambiguous retry;
- independent evidence confirms the intended device effect; and
- held-out missions meet declared correctness, recovery, and latency thresholds.

Until then, every artifact remains a scoped research, simulation, shadow,
commissioning, or bounded physical result with its limitations intact.
