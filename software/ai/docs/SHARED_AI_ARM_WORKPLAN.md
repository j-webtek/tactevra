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

The arm lane's ordered, camera-independent implementation backlog is maintained
in the
[pre-camera arm integration completion plan](../../docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md).
It operationalizes the arm-side portions of S2, S4, and S7 without changing the
shared stage gates or granting physical authority.

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
plan—not repeating this request.
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
ARM-077 freezes the PC0 pre-camera typing qualification basis. The retained
artifact pins canonical typing sequences, source hashes, synthetic-only
calibration/dynamics/controller identities, Cartesian policy, status codes,
resource ceilings, and benchmark requirements. A strict loader verifies those
sources and rejects authority promotion, reordered fixtures, crossed identities,
unsafe paths, non-finite limits, and physical claims. This establishes the
repeatable offline basis for PC1 joint-space timing; it does not qualify any
installed dynamics, controller timing, camera, collision profile, or movement.
ARM-078 begins PC1 with a typed canonical joint-schedule boundary over the exact
accepted T2B-IK samples. It closes the semantic-PC0-to-URDF joint-name seam,
preserves sample/action order, generates strictly monotonic host timestamps,
and deterministically rescales the route until synthetic velocity,
acceleration, and jerk ceilings are satisfied or the bounded scale is rejected.
The receipt remains zero-authority and explicitly blocks on measured installed
dynamics, controller tracking, installed collision evidence, and a fresh
observed start. PC1 is still in progress pending per-segment reporting and the
remaining boundary/reversal/duration qualification matrix.
ARM-079 completes the synthetic offline PC1 gate. The schedule now retains a
diagnostic record for every adjacent joint sample, including duration,
velocity, acceleration, jerk, remaining margin, and limiting joint/constraint.
A strict parser reconstructs the typed artifact and rejects crossed profile
hashes, timestamps, segment lineage, or unsupported fields. Tests cover every
dynamic dimension at bounded just-inside/just-outside scale limits plus
stationary and direction-reversal cases. PC2 shadow-pipeline composition may
begin, but measured installed dynamics, controller tracking, collision
evidence, fresh state, and all physical authority remain blocked.
ARM-080 begins PC2 by composing the actual V2 decoder and every existing
optimized typing boundary through collision-evidence intake behind one
zero-I/O API. Golden `robot` and `H,H,1,PERIOD` receipts bind nine stage hashes,
preserve repeats and action order, and deterministically stop at the missing
installed collision profile and fresh-state requirements. The checkpoint has
no transport or writer surface. PC2 remains in progress pending a canonical
receipt parser/schema and the full field-by-field owner-boundary mutation set.
ARM-081 completes PC2 with a strict canonical receipt schema/parser and an
owner-boundary mutation matrix. Independently rehashed changes to stage order,
terminal lineage, action count, authority, or field set still reject, while
duplicate JSON, crossed batch/intent/calibration/seed identities, stale
admission, expired freshness, and dynamics overflow fail at their earliest real
stage. PC3 rolling-horizon/restart work is ready; no physical blocker changes.
ARM-082 completes PC3 with a one-action current slot and one zero-authority
preview slot bound to observed state, feedback, controller session,
configuration epoch, calibration, tool, dynamics, freshness, and deadline.
Any drift discards the horizon. Pre-dispatch restart reconstructs intent without
replay; restart after retained dispatch intent becomes `OUTCOME_UNCERTAIN` with
retry forbidden. PC4 zero-write controller encoding is now ready; measured
workcell evidence and physical authority remain unchanged.
ARM-083 completes PC4. One PC3 current action is selected from the exact timed
joint schedule, checked against its trajectory semantics, and encoded into
pinned deterministic T=102 bytes with arm-owned joint order, firmware settings,
timing, and gripper policy. The receipt binds all execution identities and
requires bounded correlated T=1051 feedback, but opens no transport, consumes
no physical permit, and grants no authority. PC5 adversarial campaigns are now
ready; camera and installed-workcell blockers are unchanged.
ARM-084 begins PC5 with a canonical six-family, 35-case fault-campaign receipt
and stricter resource boundaries at AI V2 ingress, rolling-horizon parsing, and
controller-preview reconstruction. Malformed, duplicate, missing, oversized,
non-finite, and deeply nested model inputs now have bounded rejection tests;
campaign observations cannot record authority, retries, reordering, fallback,
or escaped exceptions. PC5 remains in progress while the planner, transport,
process-crash, and cache cases are connected to their actual owning boundaries.
This checkpoint performs no hardware I/O and changes no physical qualification.
ARM-085 completes PC5 by driving all 35 declared cases through the actual
decoder, lineage/order, IK, joint-limit, Jacobian, trajectory, dynamics,
collision-intake, clearance, transaction, protocol-emulator, sequence,
restart-reconciliation, rolling-horizon, and bounded-cache owner boundaries.
The hash-bound observation cache is capped at 64 entries and rejects corruption,
identity crossing, malformed contents, duplicates, and exhaustion. The 145-test
affected suite passes with no physical transport, permit, movement, retry, or
authority. PC6 unified journaling and deterministic replay may now begin; all
measured-workcell and camera qualification blockers remain unchanged.
ARM-086 begins PC6 with a canonical, replay-only trace manifest. Fourteen exact
stages are bounded and hash-chained from request/AI input through planning,
controller rehearsal, feedback rehearsal, and the effect-verification
placeholder. The journal retains only identifiers, sizes, and hashes; replay
detects missing, changed, truncated, extra, reordered, and identity-crossed
artifacts without parsing them into commands or exposing any execution surface.
PC6 remains in progress pending adapters for retained PC2-PC5 artifacts, a
clean-checkout replay command, and path-containment/redaction qualification.
ARM-087 connects that backbone to the actual strict PC2-PC5 contracts. The
adapter parses and cross-binds the V2 batch, golden shadow receipt, rolling
horizon, zero-write controller preview, and completed fault campaign before it
derives replay artifacts. Crossed request, target order, horizon, or schedule
identity rejects before journal creation. The journal still retains hashes and
sizes only and the effect stage remains explicitly not observed. PC6 now waits
on the contained clean-checkout replay command and redaction/path qualification.
ARM-088 adds that contained package and `replay-typing-trace` CLI. Packages are
confined beneath an explicit nonsymlink evidence root, use fixed filenames and
bounded canonical JSON, and reject path escape, symlinks, sensitive keys,
absolute paths, mutation, deletion, or unexpected entries. Replay compares
bytes and hashes only; it never decodes retained material into an execution
request. PC6 now waits only on retaining and replaying one actual
adapter-produced golden package from a clean checkout.
ARM-089 retains that package and completes PC6. It is produced through the
actual ARM-087 PC2-PC5 adapter, contains the exact 14-stage trace, and is
regenerated byte-for-byte in test. The checked-in package also replays through
the CLI from an isolated workspace as `IDENTICAL` while reporting zero
hardware authority. The affected 119-test suite passes. PC7 safe transition
cache work is now unblocked; camera and measured-workcell gates are unchanged.
ARM-090 begins PC7 with a bounded shadow-only directional transition cache.
The key binds source/destination, direction, calibration, target catalog, tool,
arm model, dynamics, planner policy, and device-pose epoch. A hit returns only
a planning seed and timing estimate after fresh start-state, IK, collision,
dynamics, and permit-policy validation; fresh planning and all safety gates
remain mandatory. No command, permit, admission, or physical authority is
cached. The focused 14-test and affected 133-test suites pass. Broader pair,
repeat, identity-churn, and randomized equivalence testing remains for PC7.
ARM-091 completes PC7. Equivalence now covers all canonical PC0 typing
fixtures, reverse travel, repeats, number/punctuation, and single-key routes.
Every bound identity dimension is invalidation-tested, and a seeded
128-operation capacity campaign remains deterministic and bounded. The 31
focused and 150 affected tests pass with identical cached-versus-uncached
receipts and schedule hashes and zero authority. PC8 performance benchmarking
may now begin.
ARM-092 begins PC8 with the shared bounded performance-report contract. Nine
required scenarios each need at least 50 samples; reports include exact stage
CPU distributions, resource maxima, cache behavior, route-duration prediction,
and direct-versus-park comparison. PC0 ceilings reject rather than being
silently exceeded, and simulated timing can never be labeled measured typing
speed. Eight focused and 158 affected tests pass. The instrumented runner and
retained readiness report remain outstanding.
ARM-093 adds the actual zero-I/O PC2 instrumentation runner. It measures the
existing decode-through-collision path, process CPU, peak working set, screening
samples, receipt bytes, predicted route duration, and cache estimates without
changing the ordinary receipt. Preview and encoding remain measured as zero
when the honest collision-evidence blocker prevents those stages. Ten focused
and 160 affected tests pass. PC8 still needs the retained multi-scenario run and
readiness interpretation.
ARM-094 completes PC8 with the retained 450-observation campaign and readiness
interpretation. All nine required scenarios contain 50 samples, every PC0
resource ceiling passes, and 50/50 malformed batches reject. IK is the dominant
measured CPU bottleneck at 8.953 seconds p95. The same synthetic `ROBOT` route
predicts an 8.98 percent shorter direct-hover duration than park-between-keys;
this is not measured physical speed. Exact retained hashes, 12 focused tests,
and 162 affected tests pass with zero hardware access or physical authority.
PC9 camera-arrival evidence tooling is now the next pre-camera plan stage.
ARM-095 begins PC9 with a shared 15-slot arrival map. Each required physical
original has an external destination, strict sidecar schema, review fields,
units/uncertainty requirements, and named downstream consumers. The exact
synthetic dry run retains blank measured slots and rejects any attempt to imply
epoch advancement, registry update, qualification, camera access, controller
access, writes, movement, or authority. Thirty-three combined cross-lane tests
pass. The arrival-day checklist is ready; remaining calibration and installed-
geometry consumer dry runs keep PC9 in progress.
ARM-096 completes PC9 by resolving and hash-binding every arrival slot to its
actual downstream consumer and aggregate schema. The consolidated 225-test
matrix covers capture originals through localization evaluation. Zero measured
originals are consumed, no physical-admission flag becomes true, and the
camera hold remains active. PC10 clean-checkout closure is the next pre-camera
stage.
ARM-097 completes PC10 against detached clean-checkout implementation commit
`baa5745a966284bb94204307f1d37994e4e5bf3c`. The controlled FREEZE-013 rebind
preserves the reconciled AI/arm geometry and authority boundary while updating
the dependent deterministic evidence lineage. The clean Windows/Python 3.10.10
checkout passes 507 governed portable tests, 194 explicit PC0-PC9 tests, 115
repository-policy tests, and all maintained policy audits. No camera,
controller, transport, torque, or movement authority was used. The next shared
dependency is final-camera commissioning under the existing physical hold.
ARM-098 adds a deterministic read-only inventory between physical collection
and offline qualification. It validates all 15 canonical sidecars and their
source bytes, rejected reviews, and configuration-epoch consistency without
opening either device or mutating any registry. A structurally complete result
is only ready for offline qualification review; it grants no perception,
controller, contact, or movement authority. The governed offline matrix passes
514 tests.
ARM-099 freezes the preflight output schema and a hash-verifying downstream
parser, and exposes the same implementation as an installed Python module. The
installed-package smoke test produced the expected blocked 15-slot report with
zero authority. Rehashed semantic mutations reject, package metadata remains
unchanged, and the governed offline matrix passes 518 tests.
ARM-100 joins that verified preflight to the repository-bound 15-slot consumer
map. Each route now carries the original sidecar/source hashes, shared epoch,
consumer source/schema hashes, and exact consumer binding. A complete set is
ready only for offline consumer validation: no consumer has run, no
qualification is installed, and no physical-admission or execution authority
is created. The governed offline matrix passes 527 tests.
ARM-101 defines the return path from those consumers. Exact hash-bound PASS or
BLOCKED receipts now aggregate without losing failures or accepting duplicate,
wrong-route, or authority-bearing records. All 15 routes must pass before the
assessment becomes complete for offline review, and even that state cannot
commission an epoch, install qualification, or authorize hardware. The
governed offline matrix passes 534 tests.
ARM-102 adds domain adapters for the existing camera/support assessment,
physical-camera campaign preflight, and held-out localization evaluator. Their
eight routes now preserve native output hashes and failures in the shared
receipt format. The remaining planner-calibration and installed-collision/cable
routes stay pending, so partial adapter coverage cannot complete the aggregate.
The governed offline matrix passes 540 tests.
ARM-103 adds the typed planner-snapshot and installed-collision/cable emitters,
covering all 15 route identities. Planner receipts require a keyboard
`PlannerCalibrationSnapshot`; geometry receipts require an
`InstalledCollisionGeometryProfile`. The cable route requires physical
geometry completeness rather than diagnostic readiness, so the current sampled
cable evidence stays blocked. Full route accounting therefore cannot be
mistaken for full validation. The governed offline matrix passes 543 tests.
The AI precision lane now has a mainline-compatible pose-output adapter and v2
batch producer. It preserves repeated targets and abstains on qualification,
domain, freshness, identity, confidence, or containment failure. Its retained
held-out evidence is still `SYNTHETIC_OFFLINE_ONLY`: the 14.400834977 mm bound
crosses ordinary key safe regions, so no deployment qualification is installed
and the operational-readiness perception gate remains blocked.

## Stage definitions

### S0 — Freeze the shared v1 seam

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

### S1 — Contract v2: freshness, uncertainty, and capability

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
- Require the entire uncertainty region—not only its center—to fit the measured
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

### S2 — Full zero-hardware text-to-envelope shadow path

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

### S3 — Measured localization and planning readiness

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

### S4 — Zero-write controller adapter and correlated receipts

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

### S5 — One independently verified physical key action

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

### S6 — Ordered multi-action keyboard missions

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

### S7 — Performance and operational qualification

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

### P1 — Separate phone capability track

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
#### E-YYYYMMDD-AI|ARM|INT-NNN — short title

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

| Worker/lane | Stage | Paths expected to change | Branch/commit | State |
|---|---|---|---|---|
| Unclaimed | S2/S3 | physical-camera deployment qualification and safe-region-fit precision evidence | — | AVAILABLE |
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
   output—not a hand-authored substitute—and append an `INT` evidence row.
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

The arm lane's current offline sequence is PC11 through PC18 in the
[pre-camera arm integration completion plan](../../docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md).
It begins with one-command arrival orchestration, then proceeds through a
synthetic fault campaign, domain wrappers, resumable session state,
geometry/cable rehearsal, immutable capture replay, observability, and an
actual AI-producer compatibility corpus. These stages do not replace the
camera-dependent S2/S3 and S4 gates and cannot create physical authority.
PC14 is complete at ARM-107: retained arrival sessions now reconstruct exactly
or stop. PC15 is complete at ARM-109: the typed sampled-cable contract,
rigid/attachment templates, exact missing-measurement diagnostics, boundary
fixtures, and retained zero-authority campaign now pass the real collision
consumer boundary. PC16 is complete at ARM-110: frozen image/metadata bytes,
camera/support/model/calibration identities, retained AI outputs, and expected
consumer decisions now replay identically or reject, while original,
synthetic, and replay provenance remain distinct. The runner deliberately does
not execute the vision model; AI-lane inference produces the retained outputs.
PC17 is complete at ARM-112. ARM-111 froze the decision-neutral observation
contract; ARM-112 retained 120 host-measured observations across the real
offline PC11-PC16 boundaries, split evenly between fresh and retained artifact
trees and covering pass, blocked, and pending outcomes. Every timed decision
matched an independent verification hash. The measurements expose software
bottlenecks but cannot influence admission or claim model, controller, or
physical typing performance. PC18 is complete at ARM-113. Its retained corpus
binds exact output bytes from the actual shared emitter, precision adapter, and
localization-abstention path. H,H,I reaches zero-authority trajectory
compilation in exact order; the actual H,H,1,PERIOD precision fixture is
decoded in exact order but correctly blocked because its 14.400834977 mm bound
does not fit measured key-safe regions. Unsupported, stale, crossed-identity,
low-confidence, and uncalibrated cases stop at their declared owner. This
proves contract compatibility, not localization accuracy or physical typing.
ARM-114 refines PC18 with retained actual-emitter outputs for a 15-action mixed
phrase and all 46 named keyboard targets, exact strict-decoder dispositions for
four hostile mutations, and explicit input-resource ceilings. Exact order is
preserved through offline trajectory compilation for both new accepted cases.
The refinement remains zero-authority and does not turn catalog coverage into
IK, collision, calibration, contact, or physical typing evidence.

The arm-owned operational-efficiency lane is current through ARM-132. ARM-128's
clean-commit representative endpoint atlas covers the five established typing
patterns and preserves every reference shadow receipt. The corpus contains 40
unique endpoint identities; seven recur and all seven have one observed solved
joint-state hash. That supports a bounded exact-reuse experiment but does not
authorize atlas use, warm starts, controller access, or physical motion.
ARM-129 supplies a decision-neutral, lifecycle-bound verifier that compares
endpoint candidates against complete canonical solves. Its focused tests cover
equivalence, integrity, capacity, reload, restart, crossed context, decision
context, and deliberate conflicts, while candidates remain excluded from the
decision path. ARM-130 retains the clean-commit qualification: all five
representative patterns preserve their canonical receipts across 186 samples,
40 unique endpoints, and 18 exact recurrence matches, with zero conflicts. Its
ten-case fault matrix bounds capacity and rejects sample exhaustion,
invalidation, corruption, conflict, changed decision context, reload, restart,
crossed context, and unmanaged use. This evidence still authorizes neither
candidate substitution nor a performance behavior change.
ARM-131 then qualifies the existing exact solver-input cache across the same
five patterns rather than creating an unsafe endpoint-only decision cache.
Reference, cold, and warm receipts and stage hashes remain identical over 186
lookups; cold runs reuse 26 exact inputs and warm runs reuse all 186. Every miss
still falls back to the complete solve. The retained timing is host-only and
grants no controller or physical authority.
ARM-132 retains the corresponding shadow-service lifecycle campaign. Five
mixed requests complete in FIFO order with 138 exact hits and 48 full-solve
misses. Cancellation causes no cache work; reload and restart reject stale
queued work and begin the replacement generation cold. Automatic retry,
executor attachment, controller access, and physical authority remain absent.
ARM-133 converts that evidence into a frozen, zero-authority runtime profile
gate rather than enabling reuse by default. Exact-input reuse is shadow-eligible
only when the active lifecycle generation, build snapshot, kinematic model,
calibration snapshot, four retained evidence files, 256-entry bound,
complete-solve fallback, and no-retry policy match exactly. Evidence or
calibration drift falls back to the complete solver; unsafe settings and stale
reload/restart objects are rejected. The retained six-case campaign passes and
still grants no admission, controller, transport, or physical authority.
ARM-134 integrates that decision at a new shadow-service composition boundary.
An eligible generation passes the existing exact cache to the unchanged
pipeline; calibration or evidence drift passes no cache and therefore performs
the complete solve. Reload and restart retire the frozen profile and keep the
replacement generation on complete solves until a new composition is
explicitly qualified. Its retained five-case campaign preserves the same
reference receipt across qualified and fallback paths, records 24 qualified
lookups with 1 hit and 23 full-solve misses, and records zero cache activity on
all four fallback paths. It adds no executor, retry, controller, or motion path.
ARM-135 connects the actual shared AI `assemble()` emitter to that profiled
service using consumer-owned synthetic integration fixtures. The retained
`R,O,B,O,T` campaign preserves exact order. Its cold request records 57 IK
lookups, 11 within-request exact hits, and 46 complete solves; the next request
records 57/57 warm hits. On the measured host, that single warm observation was
0.3004444 s versus 2.3158146 s cold. Calibration/evidence fallback and
reload/restart complete through the full solver with zero cache activity, while
pre-admission cancellation performs no solver work. Timing is diagnostic only,
and the synthetic fixture grants no camera, deployment, controller, or motion
qualification.

1. **S1 software boundary — complete for zero authority:** v2 producer bytes,
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
