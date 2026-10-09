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

The AI/model lane on `codex/intent-v11-shadow-integration` claims AI-553 from
merged AI-552 base `250cba61c76a34bb1679dc9e2b48a5a5be5e3422`. It may pin
the exact selected classifier-v11 digest and add a read-only composition layer
from the existing intent shadow receipt through deterministic keyboard target
compilation, qualified synthetic perception fixtures, `ModelMotionBatchV2`,
strict arm ingress, and the existing zero-hardware arm shadow planner. Missing
perception, non-actionable intent, unsupported phone motion, digest mismatch,
or any composition error must stop before planning. The layer may report batch
and shadow-trace hashes but may not emit joint, PWM, serial, Waveshare JSON,
permit, transport, controller-command, or execution-authority fields. It may
not change arm-lane status or declare an integration gate complete.

The AI/model lane on `codex/intent-classifier-v11-evaluation` claims AI-552
from merged AI-551 base `7295d8b0403cb343711f714405bb2f5c8857b446`. It may
open the frozen 250-row v22 evaluation exactly once using the unchanged local
classifier-v11 adapter digest
`348514d04a26efc58552e1eb4395e298ca7bc6f1045fb1777a898acb8d75d207`
and the frozen deterministic gates, observation policy, schema, prompt, and
promotion thresholds. Promotion requires 250/250 exact classification and
composition with zero schema-invalid, false-actionable, or altered-text
outputs. No retraining, prompt change, threshold change, development reuse, or
second v22 opening is allowed. Any miss rejects the candidate and must be
preserved. This increment may not construct ModelMotionBatch, invoke motion,
emit commands, change arm-lane status, or claim execution or physical
authority.
Evidence `E-20261009-AI-552` passes the one-time v22 evaluation at 250/250
exact classification and composition with zero schema-invalid,
false-actionable, altered-text, or deterministic-gate rows. The unchanged
classifier-v11 candidate is selected under the frozen synthetic language
contract. This is offline language evidence only and grants no motion or
hardware authority. The next AI dependency is a separately claimed read-only
shadow integration that pins this digest and exercises intent classification,
deterministic text compilation, and the existing ModelMotionBatch boundary
without execution.

The AI/model lane on `codex/intent-classifier-v11-training` claims AI-551 from
merged AI-550A base `70263b7d89f585a0d1b6a53ad13f5f2be923f540`. It may train
the single classifier-v11 candidate for exactly two epochs and open its 225-row
development split exactly once. Promotion requires 225/225 exact classification
and composition with zero schema-invalid, false-actionable, or altered-text
outputs. V22 may not be decoded in this increment. Any miss rejects the
candidate and must be preserved. This increment may not construct
ModelMotionBatch, invoke motion, emit commands, change arm-lane status, or
claim execution or physical authority.
Evidence `E-20261009-AI-551` passes the claimed development boundary. The
single two-epoch candidate completed 126 updates and achieved 225/225 exact
classification and composition with zero invalid, false-actionable,
altered-text, or deterministic-gate rows. V22 remains unopened. The next AI
dependency is a separate one-time v22 evaluation claim using the unchanged
candidate and gates.

The AI/model lane on `codex/intent-classifier-v11` claims AI-550 from merged
AI-549 base `6e1f848df545c6fb6fcf15cbc856165d2b97553b`. It may freeze one
fresh classifier-v11 corpus with the same five post-gate decision families and
a broader unquoted-keyboard paraphrase grammar informed by the preserved v21
failure. V21 is consumed evidence: its 250 requests join decoded historical
admission and may not be reused for selection. Training, development, and
sealed v22 full requests, payloads, IDs, and provenance must be disjoint from
all prior decoded requests; sealed v16 through v20 may be hash-verified only.
The freeze predeclares 200/45/50 rows per family, one candidate trained for
exactly two epochs, one development opening, and exact classification and
composition with hard zero schema-invalid, false-actionable, and altered-text
limits. V22 may open only after a committed development pass. This increment
may not construct ModelMotionBatch, invoke motion, emit commands, change
arm-lane status, or claim execution or physical authority.
Evidence `E-20261009-AI-550A` freezes the claimed successor corpus: 1,000
training, 225 development, and 250 sealed v22 rows. The training unquoted
grammar now contains the v21 failure structure while development and v22 use
disjoint supported structures. All 1,475 rows pass deterministic admission and
exact composition. Generation finds zero overlap with 11,575 requests from 25
decoded historical corpora, including consumed v21, while sealed v16 through
v20 are hash-verified only. V22 remains unopened. The next authorized step is
the one predeclared two-epoch candidate and one development opening.

The AI/model lane on `codex/intent-classifier-v10-evaluation` claims AI-549
from merged AI-548 base `1a47155f451bb244167c9086680ad1bdebb100a4`. It may
open the frozen 250-row v21 evaluation exactly once using the unchanged local
classifier-v10 adapter digest
`340ad8350945ff11952e0bfed04d0ff7be3d3bffdfde4e2c7ddc22ded8606afc`
and the already frozen deterministic gates, observation policy, schema, and
promotion thresholds. Promotion requires 250/250 exact classification and
composition with zero schema-invalid, false-actionable, or altered-text
outputs. No retraining, prompt change, threshold change, development reuse, or
second v21 opening is allowed. Any miss rejects the candidate and must be
preserved. This increment may not construct ModelMotionBatch, invoke motion,
emit commands, change arm-lane status, or claim execution or physical
authority.
Evidence `E-20261009-AI-549` rejects the unchanged candidate on its single v21
opening at 238/250 exact classification and composition. Quoted typing,
punctuation typing, verified phone typing, and unavailable-workflow refusal
each pass 50/50. Unquoted typing passes 38/50; all 12 misses share the held-out
`Produce <payload> using the attached keyboard` form and safely become
`REFUSE(operation_not_available)`. Schema-invalid, false-actionable, and
altered-text counts remain zero. V21 is consumed and may not be reopened. The
next AI dependency is a fresh successor corpus and sealed evaluation family
that broadens unquoted action paraphrases without reusing v21 for selection.

The AI/model lane on `codex/intent-classifier-v10-training` claims AI-548 from
merged AI-547A base `0cfd528bdce6c414f999d6fcf8380a7100032409`. It may train
the single predeclared classifier-v10 candidate for exactly two epochs from the
frozen 1,000-row training split, import that adapter into the local offline
Ollama runtime, and open the 225-row development split exactly once. Promotion
requires 225/225 exact classification and composition with zero schema-invalid,
false-actionable, or altered-text outputs. Any miss rejects the candidate and
must be preserved. Frozen v21 through v16 may be hash-verified only and may not
be decoded; v21 may open only after a committed development pass in a later
claim. This increment may not construct ModelMotionBatch, invoke motion, emit
commands, change arm-lane status, or claim execution or physical authority.
Evidence `E-20261009-AI-548` passes the claimed development boundary. The
single two-epoch candidate completed 126 optimizer updates and reached 225/225
exact classification and composition on the one authorized development
opening, with zero schema-invalid, false-actionable, altered-text, or
deterministic-gate rows. V21 through v16 remain unopened. The next AI
dependency is a separate held-out v21 evaluation claim using this unchanged
adapter and the already frozen exact gates.

The AI/model lane on `codex/intent-classifier-v10` claims AI-547 from merged
AI-546 base `36eaa5f5bda3fa47a578ac4e0317c20659b76954`. It may freeze one
fresh post-gate classifier corpus containing only five remaining model decision
families: quoted keyboard typing, punctuation keyboard typing, unquoted
keyboard typing, verified phone typing, and unavailable-workflow refusal.
Freshness, phone-state refusal, text ambiguity, and explicit device ambiguity
must intercept no generated row; every actionable request must still compose
through exact requested-device binding. Train, development, and unopened v21
evaluation wording, payloads, IDs, and provenance must be disjoint from all
prior decoded requests; sealed v16 through v20 may be hash-verified only and
may not be decoded. The freeze predeclares 200/45/50 rows per family, giving
1,000 training, 225 development, and 250 evaluation rows, one candidate trained
for exactly two epochs, one development opening, exact classification and
composition, and hard zero limits for schema-invalid, false-actionable, and
altered-text output. V21 may open only after a committed development pass. This
increment may not construct ModelMotionBatch, invoke motion, emit commands,
change arm-lane status, or claim execution or physical authority.
Evidence `E-20261009-AI-547A` freezes the claimed five-family corpus: 1,000
training, 225 development, and 250 sealed v21 rows. All 1,475 rows pass
freshness and requested-device composition and are intercepted by none of the
phone-state, text-ambiguity, or device-ambiguity gates. Generation found zero
case-insensitive request overlap with 10,100 requests from 22 decoded
historical corpora and hash-verified sealed v16 through v20 without decoding.
V21 remains unopened. The next authorized step is the one predeclared
two-epoch candidate followed by one development opening.

The AI/model lane on `codex/intent-device-ambiguity-gate` claims AI-546 from
merged AI-545 base `c702b9fa924d559fdbb32f6c6461c535ca3de590`. It may add a
narrow, motion-free explicit-device ambiguity gate before local model inference.
Only requests in the closed grammar that ask which destination device or input
surface should receive exactly one literal payload may become
`CLARIFY(device_ambiguous)` with zero model calls and zero semantic actions.
Freshness, unverified phone-state, and text-ambiguity decisions retain
precedence. Unavailable workflows must not be reclassified as device ambiguity.
Consumed classifier-v9 development may be replayed only as corrective boundary
evidence and may not be rescored for model selection. Frozen v20 through v16
remain unopened. This increment may not construct ModelMotionBatch, invoke
motion, emit commands, change arm-lane status, or claim execution or physical
authority.
Evidence `E-20261009-AI-546` completes the claimed boundary. The closed gate
matches all 200 v9 training and 45 v9 development device-clarification rows and
zero other-family rows. A corrective replay of the already opened v9
development scorecard moved exact classification and composition from 264/270
to 270/270, corrected all six prior misses, and retained the other 225 prior
model outputs. Workflow requests remain model decisions. This is boundary
evidence rather than model reselection; v20 through v16 remain unopened. The
next AI dependency is a fresh corpus containing only actionable typing and
unavailable-workflow decisions that remain after all deterministic gates.

The AI/model lane on `codex/intent-classifier-v9` claims AI-545 from merged
AI-544 base `c329ca12457b19fd35c4a23c0aa8a156a060f207`. It may freeze one
fresh post-gate classifier corpus containing only the six decision families
that remain after deterministic freshness, phone-state, and text-ambiguity
gates: quoted keyboard typing, punctuation keyboard typing, unquoted keyboard
typing, verified phone typing, device clarification, and unavailable-workflow
refusal. Text-ambiguity examples are excluded because that decision is now
deterministic. Every actionable request must retain exact requested-device
binding. Train, development, and unopened v20 evaluation wording, payloads,
IDs, and provenance must be disjoint from all prior decoded requests; sealed
v16 through v19 may be hash-verified only and may not be decoded. The freeze
predeclares 200/45/50 rows per family, giving 1,200 training, 270 development,
and 300 evaluation rows, one candidate trained for exactly two epochs, one
development opening, and hard zero limits for schema-invalid, false-actionable,
and altered-text output plus exact classification and composition. V20 may open
only after a committed development pass. This increment may not construct
ModelMotionBatch, invoke motion, emit commands, change arm-lane status, or claim
execution or physical authority.
Evidence `E-20261009-AI-545A` freezes the claimed post-gate corpus: 1,200
training, 270 development, and 300 sealed v20 rows. All 1,770 rows pass the
three pre-inference gates and exact requested-device composition; none belongs
to the deterministic text-ambiguity family. Generation found zero overlap with
8,630 requests from 20 decoded historical corpora and hash-verified sealed v16
through v19 without decoding. V20 remains unopened. The next authorized step is
the single predeclared two-epoch candidate followed by one development opening.
Evidence `E-20261009-AI-545B` rejects that candidate at 264/270 exact
classification and composition. Invalid, altered-text, and false-actionable
counts remain zero. Every miss is the same device-clarification template with
a literal payload ending in `&&` or `++`; those six rows became safe workflow
refusals rather than the exact required device clarification. V20 remains
unopened. The next increment should move explicit device-candidate ambiguity to
a narrow deterministic pre-inference gate, while preserving unavailable-
workflow refusal precedence, before freezing another model corpus.

The AI/model lane on `codex/intent-text-ambiguity` claims AI-544 from merged
AI-543 base `2a60e6b701a76241a3f4aa4ec68fea27f3619484`. It may add a
deterministic, motion-free text-candidate ambiguity gate before local model
inference. Requests containing multiple exact payload candidates under the
closed ambiguity grammar must become `CLARIFY(text_ambiguous)` with zero model
calls and zero semantic actions. Freshness and unverified phone-state refusals
retain precedence. Consumed classifier-v8 development may be replayed only as
corrective boundary evidence and may not be rescored for model selection.
Frozen v19, v18, v17, and v16 remain unopened. This increment may not construct
ModelMotionBatch, invoke motion, emit commands, change arm-lane status, or claim
execution or physical authority.
Evidence `E-20261009-AI-544` completes the claimed boundary. The gate recognizes
only the closed explicit competing-payload grammar, runs after freshness and
phone-state refusal, and produces `CLARIFY(text_ambiguous)` with zero model calls
and zero semantic actions. It identified all 200 v8 training and 45 v8
development `clarify_text` rows with zero hits in other families. A corrective
replay of the already opened v8 development scorecard moved exact classification
and composition from 299/315 to 315/315, corrected all 16 prior misses, and
retained the other 270 prior model outputs. This is boundary evidence rather
than model reselection; v19 through v16 remain unopened. The next AI dependency
is a fresh post-gate corpus containing only decisions that remain after all four
deterministic gates.

The AI/model lane on `codex/intent-classifier-v8` claims AI-543 from merged
AI-542 base `db6dae8d066e83d53c9d5c20ceab145a820e8c83`. It may freeze a
fresh classifier-v8 train/development family and unopened v19 evaluation for
decisions remaining after deterministic freshness, phone-state, and requested-
device binding. Every actionable request must identify exactly one supported
device and compose through the safe default; no legacy composition option is
allowed in the new corpus. Generation must hash-verify all decoded historical
classifier corpora, hash-verify sealed v16 through v18 without decoding, prove
zero case-insensitive request overlap, and preserve unique family-neutral
provenance. One candidate is predeclared for exactly two epochs from the same
cached 1B base, followed by one development opening with hard zero limits for
schema-invalid, false-actionable, and altered-text output. V19 may open only
after a passing development decision is committed. This increment may not
construct ModelMotionBatch, invoke motion, emit commands, change arm-lane
status, or claim execution or physical authority.
Evidence `E-20261009-AI-543A` freezes 1,400 training, 315 development, and 350
sealed v19 cases. All 2,065 rows compose through requested-device binding;
generation found zero overlap with 6,915 decoded historical requests and hash-
verified sealed v16 through v18 without decoding. Focused tests pass 54, Ruff
passes, and the deliberately advanced 6,591-file archive ceiling passes. V19
is unopened. The next authorized step is the single predeclared two-epoch local
candidate followed by one development opening.
Evidence `E-20261009-AI-543B` rejects that single candidate at 299/315 exact
classification and composition. Invalid, altered-text, and false-actionable
counts are all zero; every miss is in text ambiguity, where 14 cases became
device clarification and two became refusal. V19 remains unopened. The next
increment must address deterministic text-candidate ambiguity before any fresh
model campaign.

The AI/model lane on `codex/intent-device-binding` claims AI-542 from recorded
AI-541 rejection commit `6faebb30e74bb696604400f41ff871fe1c4d3e8c`. It may add a
deterministic requested-device binding at the motion-free composition boundary.
An actionable `TYPE_TEXT` classification may compose only when the request
identifies exactly one supported device and that device agrees with the model
classification; missing, conflicting, or mismatched device evidence must become
`CLARIFY(device_ambiguous)`. The consumed classifier-v7 development result may
be replayed only as a corrective boundary diagnostic and may not be rescored for
model selection. Frozen v18, v17, and v16 remain unopened. This increment may
not construct ModelMotionBatch, invoke motion, emit commands, change arm-lane
status, or claim execution or physical authority.
Evidence `E-20261009-AI-542` admits the deterministic requested-device binding
at the motion-free composition boundary. A consumed v7 development replay made
zero model calls, converted all seven false-actionable outputs to
`CLARIFY(device_ambiguous)`, and left frozen v18, v17, and v16 unopened. Nine
punctuation requests that never named a device also fail closed; this is an
intentional safety cost and leaves exact composition at 285/315. Focused tests
pass 74, Ruff passes, and the 6,585-file archive ceiling passes. The next model
corpus must make the destination device explicit in every actionable example.

The AI/model lane on `codex/intent-classifier-v7` claims AI-541 from merged
AI-540 base `4cf25879c4818a547a5bfd6717741d916b54fe75`. It may freeze a
fresh classifier-v7 train/development family and unopened v18 evaluation for
decisions remaining after deterministic freshness and phone-state admission.
Unverified phone typing is excluded from learned targets; verified phone
typing with exact `KEYBOARD_LOWER` observation becomes a positive learned
family. Keyboard typing, device ambiguity, text ambiguity, and unavailable
workflow families remain. Generation must hash-verify consumed classifier-v1
through classifier-v6 corpora, hash-verify sealed v16 and v17 without decoding,
prove zero case-insensitive request overlap with decoded history, admit every
deterministic composition, prove that no generated learned row is intercepted
by either deterministic gate, and preserve unique family-neutral provenance.
One candidate is predeclared for exactly two epochs from the same cached 1B
base, followed by one development opening under exact classification and
composition gates and hard zero limits for invalid, false-actionable, and
altered-text output. V18 may open only after a passing development decision is
committed. This increment may not construct ModelMotionBatch, invoke motion,
emit commands, change arm-lane status, or claim execution or physical
authority.
Evidence `E-20261009-AI-541` rejects the only classifier-v7 candidate on its
single development opening. Exact classification and composition reached
287/315, and verified phone typing passed 45/45, but seven device-ambiguity
cases became actionable keyboard typing. Schema-invalid and altered-text
counts stayed zero. V18, V17, and V16 remain unopened. The next increment must
bind actionable device selection deterministically before another model
campaign; no additional epoch or evaluation opening is authorized here.

The AI/model lane on `codex/intent-classifier-v6` claims AI-540 after recorded
AI-539 development rejection. It may add a deterministic, fail-closed phone
state precondition beside the existing freshness precondition. An explicit
phone typing request may reach model inference only when the observation binds
the exact verified `KEYBOARD_LOWER` state; otherwise it becomes
`REFUSE(phone_state_unverified)` with zero model calls and zero semantic
actions. Freshness refusal retains precedence. The gate must be implemented in
the shared motion-free intent contract, exercised by the disconnected shadow
runtime and evaluator, hash-bound in receipts, and covered for missing, wrong,
verified, stale, keyboard-only, and tampered cases. Consumed classifier-v6
development may be used only as failure evidence and may not be rescored for
selection. V17 and v16 remain unopened. This increment may not construct
ModelMotionBatch, invoke motion, emit commands, change arm-lane status, or
claim execution or physical authority.
Evidence `E-20261009-AI-540` admits the deterministic phone-state precondition
at the disconnected intent boundary. Against the consumed classifier-v6
development failure set, it refused all 35 explicit phone-typing cases with
missing state, gated none of the other 210 cases, and made zero model calls.
Focused contract and runtime tests pass missing, wrong, verified, stale,
keyboard-only, and tampered cases. This is a boundary diagnostic rather than a
classifier rescore; v17 and v16 remain unopened. The next model campaign may
learn only decisions left after deterministic freshness and phone-state gates.

The AI/model lane on `codex/intent-classifier-v6` claims AI-539 from merged
AI-538 base `6f393e5d24868e4800e7c23dff2c6a9501f6cb5f`. It may freeze a
fresh classifier-v6 train/development family and unopened v17 evaluation,
keeping the same seven intent decisions and the exact
`classifier_model_observation_v1` boundary. The corpus may broaden only
language structure and paraphrase diversity, with emphasis on punctuation
typing, quoted typing, text ambiguity, and phone-state refusal. Generation
must hash-verify classifier-v1 through classifier-v5 corpora, prove zero
case-insensitive request overlap, admit every deterministic composition, prove
fresh-only model observations, and prove unique family-neutral provenance
references. V16 remains unopened and excluded. One candidate is predeclared
for exactly two epochs from the same cached 1B base, followed by one
development selection under exact classification and composition gates and
hard zero limits for invalid output, false-actionable output, and altered
typing text. V17 may open only after a passing development decision is
committed. This increment may not invoke motion, construct ModelMotionBatch,
emit commands, change arm-lane status, or claim execution or physical
authority.
Evidence `E-20261009-AI-539` rejects the only classifier-v6 candidate on its
single development opening. Broader structures improved exact classification
and composition to 197/245, but seven phone-state refusal cases became
actionable keyboard typing, violating the zero false-actionable gate. Schema
invalid and altered-text counts remained zero. V17 and retained v16 remain
unopened. No additional epoch or evaluation opening is authorized from this
claim; the next increment must address the phone-state safety boundary before
another model campaign.

The AI/model lane on `codex/intent-classifier-v5` claims AI-538 after the
recorded AI-537 one-epoch development rejection. It may train one new candidate
from the same frozen classifier-v5 training split and same cached 1B base for
exactly two epochs, then score it once on the already-designated development
split with the unchanged sanitized observation policy and zero-error gates.
The one-epoch adapter and scorecard remain preserved as failed evidence. V16
remains unopened until the two-epoch development result and selection decision
are committed. No corpus, prompt, schema, optimizer, learning rate, gate, model
input, or runtime boundary may change in this increment, and it may not invoke
motion, construct ModelMotionBatch, emit commands, change arm-lane status, or
claim physical authority.
Evidence `E-20261009-AI-538` rejects the two-epoch candidate at 97/175 exact
development classifications and compositions, with zero invalid,
false-actionable, or altered-text outputs. The added epoch recovered all
unquoted typing and most quoted typing but did not distinguish text ambiguity,
phone-state refusal, or punctuation typing. V16 remains unopened. The next
campaign must broaden training-language diversity under the same sanitized
observation contract rather than add epochs to this consumed development
selection.

The AI/model lane on `codex/intent-classifier-v5` claims AI-537 from merged
AI-536 base `2724026b6385d99fb42840ffc8fa971ee72d5f18`. It may freeze
fresh classifier-v5 train/development data and an unopened v16 evaluation for
the same seven learned intent families, train one epoch from the cached 1B
base, select once on development, and open v16 only after that selection is
committed. Training, evaluation, and the shadow runtime must all use
`classifier_model_observation_v1`, which exposes only explicit freshness and
bounded phone state; provenance references remain hash-bound in corpus records
but never enter model tokens. Before bytes are written, generation must
hash-verify classifier-v1 through classifier-v4 corpora, prove zero request
overlap, admit every deterministic composition, prove every observation fresh,
and prove provenance identifiers contain no family label. Consumed v15 is
corrective evidence only. The increment may not weaken the shadow boundary,
open v16 before a committed development decision, invoke motion planning,
construct ModelMotionBatch, change arm-lane status, or emit commands, writes,
movement, or physical authority.

The AI/model lane on `codex/intent-shadow-runtime` claims AI-536 from merged
AI-535 base `0daed957605b49c02d5ef3caeb48f2929d73ca12`. It may add one
disconnected, zero-authority shadow runtime that validates an explicit
freshness bit, bypasses model inference for stale evidence, binds the exact
retained classifier-v4 Ollama digest, deterministically composes the public
intent, and compiles semantic keyboard or phone actions only when the composed
intent is actionable. Its receipt must hash-bind the request, observation,
model identity, classification source, composed intent, and compiled semantic
actions; record model-call, ModelMotionBatch, motion-adapter, controller,
hardware-write, and physical-movement counters; and reject tampering, missing
freshness, model-identity drift, malformed classifier output, unsupported text,
and non-actionable compilation. This increment may not import or invoke a
motion adapter, construct ModelMotionBatch, emit commands, change arm-lane
status, claim deployment qualification, or acquire physical authority.
Evidence `E-20261009-AI-536` rejects classifier-v4 for shadow use after the
runtime integration exposed observation-provenance leakage. The identical
workflow-refusal request was refused when its synthetic `ref` contained the
family name and became actionable under a neutral reference. A consumed-v15
diagnostic that removed provenance fields reduced exact classification from
210/210 to 90/210 and produced 90 false-actionable outputs. The shadow runtime
itself remains a useful zero-authority boundary and now exposes only explicit
freshness and bounded phone state to inference. The next classifier campaign
must train, select, and evaluate on this sanitized model-observation contract;
classifier-v4 may not enter shadow or motion composition.
Evidence `E-20261009-AI-537` rejects the one-epoch classifier-v5 candidate on
development at 69/175 exact classification and composition. It produced no
invalid, altered-text, or false-actionable output, but failed five of seven
families wholly or partly. Frozen v16 remains unopened. The next bounded
development candidate uses the same frozen data and configuration for exactly
two epochs under AI-538; this is continued development selection rather than a
new evaluation claim.

The AI/model lane on `codex/intent-classifier-v4` claims AI-534 from merged
AI-533 base `614b2e06b4032bcc96df1dff00bfeb318d0c1b05`. It may freeze
fresh classifier-v4 train/development data and an unopened v15 evaluation
family for the seven decisions that remain learned after deterministic
freshness gating, then train one epoch from the same cached 1B base. Every
generated observation must be explicitly fresh. Before writing corpus bytes,
the generator must hash-verify all classifier-v1 through classifier-v3 source
splits, prove zero case-insensitive request overlap with them, and prove exact
production composition for every new row. Consumed development and v14 may be
used only as historical failure evidence; frozen v11, v12, and v13 remain
unopened. V15 must remain unopened until a clean development decision is
committed. The increment may not change the public intent schema, weaken the
deterministic freshness gate, invoke motion planning, promote a model, change
arm-lane status, or emit commands, hardware writes, movement, or physical
authority.
Evidence `E-20261009-AI-534` selects the one-epoch freshness-separated
candidate to open frozen v15. The generator hash-verified nine historical
corpora, found zero overlap with 2,295 prior requests, admitted all 945 new
compositions, and proved every observation explicitly fresh. Development then
reached 175/175 exact classifications and public intents with zero invalid,
false actionable, altered-text, or freshness-bypass cases. This remains a
synthetic development-only result; the unchanged v15 run decides held-out
retention and cannot confer motion or physical authority.
Evidence `E-20261009-AI-535` retains the unchanged candidate for disconnected
shadow integration after a clean frozen v15 result: 210/210 exact
classifications and composed public intents, zero invalid schemas, false
actionable outputs, altered text, or freshness bypasses. This is narrow,
synthetic intent-contract evidence. The model remains upstream of and
disconnected from ModelMotionBatch, motion planning, and execution. The next
increment may build a shadow-only runtime assembly that records the model,
deterministic freshness gate, exact text composer, and deterministic keystroke
compiler outputs without invoking the motion adapter.

The AI/model lane on `codex/deterministic-intent-freshness` claims AI-533 from
merged AI-532 base `df8a4ddb10cea98a58e101d86ff07d6fda5d311f`. It may
add a fail-closed classifier pre-gate that maps an explicitly stale bound
observation directly to `REFUSE(stale_observation)` before local-model
inference, then rerun consumed v14 only as a diagnostic. It must preserve the
AI-532 rejection, report how many cases bypass inference, and leave every fresh
case to the unchanged model and deterministic text composer. It may not retrain
or promote a model, treat v14 as fresh selection evidence, invoke motion
planning, change arm-lane status, or emit commands, hardware writes, movement,
or physical authority.
Evidence `E-20261008-AI-533` shows the deterministic gate removes the complete
AI-532 stale-language failure class on consumed v14: 30 explicitly stale cases
bypass inference as `REFUSE(stale_observation)`, the unchanged model handles
the other 210 cases, and the composed diagnostic is exact on 240/240 with zero
invalid schemas, false actionable outputs, or altered text. This does not
promote the rejected checkpoint or turn v14 into fresh evidence. The next fresh
campaign should evaluate the model only on decisions that remain learned and
test stale evidence separately as a deterministic contract invariant.

The AI/model lane on `codex/intent-classifier-v3` claims AI-531 from merged
AI-530 base `a581b914f83b9d6cd378d9ba2aacda066c797161`. It may extend the
bounded extractor grammar before data generation, freeze fresh classifier-v3
train/development data and an unopened v14 evaluation family, and train one
epoch from the same cached 1B base. Before any new corpus bytes are written,
the generator must verify the exact hashes of all classifier-v1 and
classifier-v2 source splits, prove zero case-insensitive request-string overlap
with them, and prove every new row composes exactly through the production
deterministic composer. Consumed classifier-v1 and classifier-v2 development
may be used only as historical failure evidence; frozen v11, v12, and v13 must
remain unopened. Evaluation v14 must remain unopened until a clean development
decision is committed. The increment may not change the public closed intent
schema, invoke motion planning, promote a model, change arm-lane status, or
emit commands, hardware writes, movement, or physical authority.
Evidence `E-20261008-AI-531` selects the one-epoch candidate to open frozen v14.
Before generation, all six prior corpus hashes matched; all 1,080 new cases
were composition-exact and had zero request overlap with 1,215 historical
requests. Fresh development then reached 200/200 exact classifications and
200/200 exact composed public intents with zero invalid schemas, false
actionable outputs, or altered text. This is a development-only synthetic
result. The candidate remains unpromoted and disconnected from motion; only the
unchanged run on already frozen v14 can decide the held-out result.
Evidence `E-20261008-AI-532` rejects that unchanged candidate on v14. It matches
210/240 held-out cases with zero invalid schemas, false actionable outputs, or
altered text, but all 30 stale-observation requests are mislabeled
`operation_not_available` rather than `stale_observation`. The candidate is not
promoted. V14 is consumed; any successor needs a new claim and fresh splits and
may use this result only to broaden stale-evidence language before freeze.

The AI/model lane on `codex/intent-classifier-v2` claims AI-530 from merged
AI-529 base `d757695152f37bbf992f4ddbe8458440b287bca8`. It may extend the
deterministic extractor with a bounded unquoted-text grammar before generating
data, freeze fresh split-exclusive classifier-v2 train/development data and an
unopened v13 evaluation family, and train one epoch from the same cached 1B
base. The generator must fail before writing corpus bytes unless every row's
expected classification and request compose exactly to its expected public
intent through the production deterministic composer. Consumed classifier-v1
development may be used only as historical diagnostic evidence; frozen v11 and
v12 must remain unopened. Evaluation v13 must remain unopened until a clean
development decision is committed. The increment may not change the public
closed intent schema, invoke motion planning, promote a model, change arm-lane
status, or emit commands, hardware writes, movement, or physical authority.
Evidence `E-20261008-AI-530` rejects and invalidates this campaign before v13.
Generation-time composition admission succeeded for all 1,080 rows, closing
AI-529's grammar gap, but development reached only 182/200 exact classifications:
seventeen punctuation cases became `operation_not_available` refusals and one
became `CLARIFY(text_ambiguous)`. A post-result provenance audit also found that
the generator reused 560/640 training, 175/200 development, and 210/240
evaluation request strings from classifier-v1, contrary to the claim's fresh-
identity requirement. These results are retained as invalid/rejected evidence;
v13 remains unopened. The next generator must enforce both exact composition
and zero request-string overlap with every prior classifier campaign before it
writes corpus bytes.

The AI/model lane on `codex/intent-classifier-v1` claims AI-529 from merged
AI-528 base `038e7bd28b643f965ae7587634b8717d2011b5c0`. It may define
an internal classification-only JSON schema with no payload text, freeze fresh
split-exclusive train/development data and an unopened v12 evaluation family,
train one epoch from the same cached 1B base, and compose admitted classifier
outputs with AI-528 deterministic text extraction. The consumed v5 development
and v10 evidence may be used only as historical diagnostics; frozen v11 must
remain unopened. Evaluation v12 must remain unopened until a development
decision is committed. The increment may not change the public closed intent
schema, invoke motion planning, promote a model, change arm-lane status, or emit
commands, hardware writes, movement, or physical authority.
Evidence `E-20261008-AI-529` rejects the first classification-only campaign on
development while preserving its useful learned result. The one-epoch 1B
candidate classified all 200 cases exactly with zero invalid or false
actionable outputs, but deterministic composition matched only 175/200 because
all 25 fresh `type_unquoted` requests used wording outside the extractor's
closed grammar. This is a campaign-design failure: the generator admitted
actionable cases that the independently frozen deterministic boundary could not
compose. The consumed development split will not be rescored after a grammar
patch, and frozen v12 remains unopened. The next campaign must use fresh split
identities and must reject its generated corpus unless every expected intent
round-trips exactly through deterministic composition before any training.

The AI/model lane on `codex/deterministic-intent-payload` claims AI-528 from
merged AI-527 base `69f2e92479f85f3a905ace3fda21465991f5362b`. It may
add a fail-closed deterministic text extractor and diagnostic composer that
retains the local model's closed intent classification but never trusts
model-generated `TYPE_TEXT` bytes. It may rerun only the consumed v5 development
split to measure whether this removes altered-text failures. Frozen v11 must
remain unopened. The increment may not retrain or promote a model, weaken any
exact gate, invoke motion planning, change arm-lane status, or emit commands,
hardware writes, movement, or physical authority.
Evidence `E-20261008-AI-528` shows the hybrid boundary removes the byte-copy
failure class on consumed v5 development evidence: model-generated text had
three alterations, while deterministic request extraction produced zero
altered text and zero false actionable outputs, raising exact results from
141/160 to 144/160. The candidate remains rejected because twelve ambiguity
and four stale-observation classifications are wrong. Frozen v11 remains
unopened. The next model work can focus strictly on classification quality.

The AI/model lane on `codex/intent-schema-sft-v5` claims AI-527 from merged
AI-526 base `f0a4932d00faecb4d37667aa2fac6b1b421c4d6e`. It may freeze
new split-exclusive train/development data and an unopened v11 evaluation
family, with repeated-punctuation and exact-text stress added before any model
result. It may train one epoch from the same cached 1B base and apply the
unchanged exact-schema gates. The consumed v10 set may be referenced only as
historical evidence and may not select or tune this successor. Evaluation v11
must remain unopened until the training and development decision is committed.
It may not promote a model, invoke motion planning, change arm-lane status, or
emit commands, hardware writes, movement, or physical authority.
Evidence `E-20261008-AI-527` rejects the one-epoch successor on development, so
v11 remains unopened. Exact-schema validity is 160/160, but exact semantics are
141/160: three actionable payloads alter repeated punctuation, twelve
text-ambiguity cases are mislabeled as device ambiguity, and four stale cases
use the wrong refusal reason. No additional epoch or evaluation was run. The
next successor must be separately frozen and may use this development result
only as consumed diagnostic evidence.

The AI/model lane on `codex/intent-schema-sft-data` claims AI-525 from merged
AI-524 base `d81a2e6f46a09387a34b2366d1a693218fc8e854`. It may freeze
schema-specific train/development data and an unopened v10 evaluation family,
extend the existing offline LoRA trainer only enough to consume those exact
hash-bound bytes and the closed-schema prompt, and run a one-epoch development
pilot on the cached 1B base. The evaluation split must remain unopened until
the training and development decision is recorded. It may not promote a model,
change motion or arm status, invoke motion planning, or emit commands, hardware
writes, movement, or physical authority.
Evidence `E-20261008-AI-525` records the frozen corpus, one-epoch pilot, and
development decision. The cached 1B base reached training loss `0.224307` and
development loss `0.004635`; its exact-schema Ollama import then matched all
105 hash-bound development cases with zero invalid, false-actionable, or
altered-text outputs. The candidate is selected only to open the already frozen
140-case v10 evaluation next. It remains synthetic, offline, disconnected from
motion, and unpromoted.
Evidence `E-20261008-AI-526` rejects that unchanged candidate on frozen v10.
It matched 139/140 cases with zero schema failures, but one `TYPE_TEXT` result
dropped one of two trailing question marks. The hard zero altered-text and
false-actionable gates therefore fail. The model remains disconnected from
motion; the retained result may inform a separately frozen successor only.

The AI/model lane on `codex/offline-intent-schema-decoding` claims AI-524 from
merged AI-523 base `043e8e813929b218b4f52b55d2787da69c09f319`. It may
rerun the exact installed 1B model, frozen v9 benchmark, prompt, seed, and hard
promotion gates while changing only Ollama's response format from generic JSON
to the hash-bound closed intent v1 JSON Schema. It must preserve AI-523's failed
evidence, report structural and semantic results separately, and remain read-
only and zero-authority. It may not tune the prompt or model, alter the
benchmark, invoke motion planning, change lane status, or emit commands,
hardware writes, movement, or physical authority.
Evidence `E-20261008-AI-524` rejects the same model after exact-schema decoding.
Structural validity improves from 0/30 to 30/30, proving the decoder correction,
but exact semantics reach only 7/30, with 21 false actionable outputs and four
altered typing payloads. The model remains disconnected from motion. The next
dependency is schema-specific training data and a newly frozen evaluation set.

The AI/model lane on `codex/offline-intent-model-eval` claims AI-523 from
merged ARM-522 base `e20f9aec993aaab6558db33180ebe204556072f7`. It may add
a read-only Ollama evaluator that constrains one already-installed 1B local
model to the closed offline intent v1 schema and scores the frozen v9 benchmark
for schema validity, exact decision match, exact `TYPE_TEXT` payload retention,
and false actionable output. It may not train or promote a model, alter the
benchmark after results, invoke the motion adapter, change either lane's stage
status, or emit motion, controller, transport, hardware-write, movement, or
physical authority.
Evidence `E-20261008-AI-523` rejects the installed 1B decision model on the
closed intent boundary: zero of 30 frozen v9 cases matched exactly and all 30
outputs were invalid under the new schema. No invalid output reached the motion
adapter. Prompt-only migration is therefore insufficient; schema-constrained
decoding or schema-specific tuning is the next dependency.

The AI/integration lane completed ARM-522 from merged ARM-521 base
`711affb7e4d74d818701d8d8be543f9d3b966a77`. It adds the public compatibility,
migration, and rollback note required for the new additive upstream intent
schema. This documentation correction changes no contract bytes, runtime code,
gate, lane status, or authority. It preserves the failed PR #264 automation
result rather than rewriting it.

The AI/integration lane on `codex/intent-schema-to-motion` claims ARM-521 from
merged ARM-520 base `8e7570ee3b754906e3eceb919936cf2e1ba46296`. It may
define one closed offline intent schema for `TYPE_TEXT`, `PRESS_KEY`, `CLARIFY`,
and `REFUSE`, then connect only an admitted keyboard `TYPE_TEXT` intent to the
ARM-520 bounded dynamic planner. The adapter must preserve the payload text
byte-for-byte, reject extra fields and all non-actionable or unsupported intent
variants, bind the intent and nested result hashes, and retain every collision,
fresh-state, resource, and authority blocker. It may not change arm-lane or
AI-lane stage status, clear a gate, interpret free-form language, or emit joint,
PWM, serial, Waveshare, controller, permit, transport, execution, hardware-
write, movement, or physical authority.
Evidence `E-20261008-ARM-521` completes the claim. The closed intent
`TYPE_TEXT(KEYBOARD, "Move!")` preserves its exact payload, compiles to
`SHIFT,M,O,V,E,SHIFT,1`, creates a distinct v2 batch, passes strict ingress,
and admits all 261 simulated IK samples. Non-actionable intent variants, phone
text, and extension fields fail before workspace materialization. Installed
collision and fresh-state blockers remain active with zero physical authority.

The AI/integration lane on `codex/dynamic-intent-to-motion` claims ARM-520 from
merged ARM-519 base `6295df237c3de811ec66e7d02b9096366b197937`. It may
replace the single frozen phrase dependency with a bounded offline path that
accepts new supported keyboard text, compiles the exact text through the
existing Sticky Keys semantic compiler, derives a fresh route fixture with one
proposal per compiled target in exact order, and evaluates the resulting
`ModelMotionBatchV2`, strict ingress, Cartesian trajectory, and C03 IK lineage.
It must bind every semantic change explicitly, reject unsupported or uncovered
targets and oversized requests, preserve all inherited numerical policies and
gates, and retain the installed-collision and fresh-observed-state blockers. It
may not change AI-lane or arm-lane stage status, clear an integration or
physical gate, or emit controller, wire, joint, PWM, serial, Waveshare, permit,
transport, execution, hardware-write, movement, or physical authority.
Evidence `E-20261008-ARM-520` completes the bounded claim. Three fresh requests
(`robot`, `hh1.`, and `A!`) compile to 13 ordered semantic actions, including a
repeated key, punctuation, and two one-shot `SHIFT` actions. Each request creates
a distinct `ModelMotionBatchV2`, passes strict ingress, and reaches a complete
canonical IK route of 190, 162, and 155 samples respectively. The result remains
simulation-only, preserves both terminal blockers, and has zero controller
commands, hardware writes, physical movements, or physical authority.

The AI/integration lane on `codex/intent-to-motion-offline-pipeline` completed
ARM-519 from merged ARM-518 base
`497be7ff23459be08be90087da4a1051e2639419`. It may add one strict offline
operator path that accepts exact keyboard text, compiles it through the existing
Sticky Keys semantic compiler, binds the resulting ordered targets to the
retained C03 `ModelMotionBatchV2`/ingress/trajectory/IK result, and emits one
canonical zero-authority receipt. It must fail closed on text or target-order
differences, changed fixture or result bytes, invalid receipt lineage, incomplete
IK, collision claims, or nonzero authority counters. It may not add model-side
joint, PWM, serial, Waveshare, permit, transport, controller, or execution
fields; change arm-lane status; clear installed collision or physical gates; or
claim that a simulated joint plan moved hardware.
Evidence `E-20261008-ARM-519` binds exact request text `hello 2026` through the
existing semantic compiler to the retained C03 v2 batch, strict ingress,
trajectory, and canonical IK lineage. All ten ordered targets, including the
repeated `L` and repeated `2`, match; all 321 trajectory samples have accepted
IK results. The resulting receipt remains simulation-only and stops on the
missing installed collision profile and fresh observed start state, with zero
controller commands, hardware writes, physical movements, or physical
authority.

The current zero-authority integration baseline is
[`model_arm_conformance_profile_v1.json`](../../config/model_arm_conformance_profile_v1.json),
SHA-256 `2430ec5f8362aae76e8250d2d9da292f85375d93750addd944a969b1bc2e4dbd`.
It binds the reviewed arm and AI commits, freezes the implemented v2 boundary,
and provides shared accepted/rejected cases without advancing operational readiness.

The arm lane on `codex/c03-measurement-draft` completed the bounded ICQ-1 capture
draft increment from merged ARM-504 base
`66fa1854d06abdcdb6d15a9c70c1bc3f6e6a7c4a`. It may generate one canonical,
context-bound installed-collision measurement manifest with every required body
and the clearance policy explicitly `PENDING`. The draft must contain no
sources, geometry, uncertainty, or clearance values; validate as blocked; and
refuse to overwrite an existing file. It must not invent measurements, change
AI-lane status, clear ICQ-9, or emit controller, wire, joint, PWM, serial,
transport, retry, permit, or movement authority.
Evidence `E-20261008-ARM-505` records the fail-closed 19-body draft generator,
exclusive-create CLI behavior, and full offline regression result. The draft
contains no physical measurements and ICQ-9 remains blocked.

The arm lane on `codex/c03-geometry-source-inventory` completed the bounded ICQ-1
nominal-source inventory increment from merged ARM-505 base
`36d537ca227c57fef4c6c5e1ab80f76fb7ae5a`. It may map all 19 required
collision bodies to hash-bound existing URDF, CAD, layout, camera-profile, and
support-design sources; expose nominal placements already present in the
layout; and state the smallest remaining physical check for each body. Nominal
sources may support continued simulation but must remain explicitly unmeasured
and must not clear ICQ-1 or ICQ-9, change AI-lane status, or emit controller,
wire, joint, PWM, serial, transport, retry, permit, movement, or physical
authority.
Evidence `E-20261008-ARM-506` records the 19-body nominal-source inventory,
the six-body top-down capture scope, the retained external inventory artifact,
and the unchanged blocked physical-qualification state.

The arm lane on `codex/c03-nominal-envelope-audit` completed the bounded ICQ-1
digital-envelope audit from merged ARM-506 base
`c8337dca8db63f98b1dbf287d376967ac4090efb`. It may parse the retained binary
STLs without external geometry libraries, report exact nominal bounds, and
compare the three station XY footprints with their declared workcell
envelopes using a fixed digital-encoding tolerance. That tolerance must not be
used as an installed-part or clearance tolerance. The audit remains nominal,
offline, and zero-authority and may not clear ICQ-1 or ICQ-9.
Evidence `E-20261008-ARM-507` records the six-mesh bound audit, exact station
envelope comparison, retained external audit artifact, digital-only tolerance,
and unchanged blocked physical-qualification state.

The arm lane on `codex/c03-nominal-proxy-audit` completed the bounded ICQ-1 active
proxy comparison from merged ARM-507 base
`c0ddfd5e5a742a9e25c87e32663ceedbda6dae7d`. It may compare the six nominal
board/device/station solids with the exact AABBs used by the active simulation,
report under-bounds and conservative over-bounds, and identify sensitivity
work. It must not silently tighten a proxy, treat nominal containment as an
installed measurement, clear ICQ-1 or ICQ-9, or grant physical authority.
Evidence `E-20261008-ARM-508` records containment of all six nominal solids,
the three deliberate 35 mm station-height proxies, the retained audit, and the
decision to measure route sensitivity before changing any proxy.

The arm lane on `codex/c03-station-height-route-sensitivity` completed the bounded
ICQ-1 exact-route sensitivity increment from merged ARM-508 base
`b22a40e2a70f7ddc09d9adf69098849515e32d81`. It may admit the retained exact
321-waypoint C03 route, compare tool-tip-centreline segment decisions under the
unchanged 35 mm station proxies and bare station CAD heights at the existing
5 mm diagnostic clearance, and list every differing segment. The comparison
must preserve target-local ignore semantics, remain diagnostic, and must not
alter a proxy, claim full-body collision evaluation, clear ICQ-1 or ICQ-9, or
grant physical authority.
Evidence `E-20261008-ARM-509` records zero collision segments and zero decision
differences across all 320 adjacent exact-route segments under both station
height models, while retaining the full-body and installed-evidence blockers.

The arm lane on `codex/c03-full-body-route-geometry` completed ARM-510 from merged
ARM-509 base `1c8342678bc7413b762f9bc5b733ec80b5b16834`. It may bind the
retained official RoArm link-mesh and conservative-reduction identities to the
exact C03 route, enumerate the geometry available for every moving rigid body,
and fail closed on missing tool, clamp/base, rigid camera-support, placement,
or self-collision-policy evidence. It must not promote the retained candidate
boxes into an installed profile, claim a full-body collision pass, change
AI-lane status, clear ICQ-1 or ICQ-9, or grant physical authority.
Evidence `E-20261008-ARM-510` binds all seven official robot-link candidate
reductions and the six nominal containing workcell proxies to the exact route,
then retains eight explicit blockers for the remaining attachments, placement,
self-collision policy, candidate qualification, and installed clearance.

The arm lane on `codex/c03-nominal-tool-binding` completed ARM-511 from merged
ARM-510 base `41f38f0898105c6c88236a09585f51724558e2ae`. It may bind the exact
110 mm planning-tip transform and nominal compliant-tool mesh envelopes,
compare their identities, and enumerate every missing local transform,
rod/stylus, compliance-travel, and installed-fit input. It must fail closed if
those sources do not define one collision envelope, must not substitute the
planning tip for tool volume, clear ICQ-1 or ICQ-9, or grant authority.
Evidence `E-20261008-ARM-511` binds the exact 110 mm planning-tip identity and
the two nominal tool mesh envelopes, then retains six missing assembly inputs
and refuses to define or install a collision envelope.

The arm lane on `codex/c03-base-camera-geometry` completed ARM-512 from merged
ARM-511 base `3ab8f70a7b27e529d7b60f29878682fa3f809479`. It may compare the
active base/clamp and camera attachment requirements with the current nominal
layout, B0477 profile, and static-overhead support design; bind only compatible
nominal facts; and fail closed on missing base pose, clamp footprint, or camera
architecture mismatch. It must not install static-tower geometry as moving
arm geometry, clear ICQ-1/ICQ-9, or grant authority.
Evidence `E-20261008-ARM-512` retains the nominal base-axis XY and static portal
screening geometry, identifies four missing base/clamp inputs, and records that
the moving-camera collision requirements are incompatible with the selected
static-overhead camera architecture.

The arm lane on `codex/c03-static-camera-collision-contract` completed ARM-513 from
merged ARM-512 base `923f771502c4c625689c47b6bf344d77ad7f6fbc`. It may
add an explicit v2 static-overhead readiness path using the existing static
B0477 route-body catalog, prove the exact migration, and preserve the legacy
v1 entry point and reconstruction for retained evidence. It must keep the
portal, booms, lighting, enclosure, lens, connector, fixed USB route, arm
harness, base/clamp, tool, robot, board, keyboard, and phone requirements
explicit; may not install missing geometry or measurements; and must not clear
ICQ-1/ICQ-9, change AI-lane status, or grant controller, wire, joint, PWM,
serial, transport, retry, permit, movement, or physical authority.
Evidence `E-20261008-ARM-513` records the additive 32-body v2 readiness result,
the exact six-placeholder migration, fixed-versus-sampled cable semantics,
unchanged legacy-v1 serialization, and the remaining 7 missing plus 19 unknown
installed-body blockers.

The arm lane on `codex/c03-static-camera-source-migration` completed ARM-514 from
merged ARM-513 base `bbc4d503290f1535e2844fe7523afa21de2d81a9`. It may add
v2 nominal-source inventory and base/camera readiness consumers for the static
B0477 IDs while preserving every v1 entry point and retained result. Nominal
sources must remain explicitly unmeasured and may not satisfy installed-body
requirements, clear ICQ-1/ICQ-9, change AI-lane status, or grant controller,
wire, joint, PWM, serial, transport, retry, permit, movement, or physical
authority.
Evidence `E-20261008-ARM-514` records all 32 v2 bodies mapped to hash-bound
nominal sources with zero measured claims, confirms architecture compatibility,
and retains four base plus four static-camera/lighting physical input blockers.

The arm lane on `codex/c03-static-support-nominal-binding` completed ARM-515 from
merged ARM-514 base `6910168c617cc0fbc4c8463d2c1abd13dd8f32e8`. It may
reconcile the retained 4040-aluminum support concept with the newer printable
portal prototype, hash-bind their shared datums and candidate nominal
envelopes, and identify the controlled-source decision required before route
sensitivity. It must not combine the two implementations, select either as the
installed assembly, run collision screening, clear ICQ-1/ICQ-9, change AI-lane
status, or grant controller, wire, joint, PWM, serial, transport, retry,
permit, movement, or physical authority.
Evidence `E-20261008-ARM-515` records matching board-frame tower and camera
datums, four printable candidate support envelopes, and the incompatible
4040-aluminum versus printed-U-lattice structural implementations. It refuses
nominal collision binding until a controlled source selects one implementation;
installed transforms and lighting geometry remain missing.

The arm lane on `codex/c03-printable-support-selection` completed ARM-516 from merged
ARM-515 base `31d524a26fff92cbccc5e42fa4a894388e189beb`. It may select the
user-confirmed printable camera portal as the nominal support implementation by
exact design hash and migrate the v2 nominal inventory to its actual design,
manifest, assembly, carriage, and cage sources. It must preserve the prototype's
no-fabrication/no-installation/no-motion authority, leave lighting undefined,
leave installed transforms pending, preserve v1/v2 consumers and evidence, and
must not execute collision screening or clear ICQ-1/ICQ-9.
Evidence `E-20261008-ARM-516` selects printable prototype 003 by its exact
design hash for nominal simulation, replaces the obsolete aluminum-source
references for support/camera/fixed-cable bodies, and leaves all four lighting
bodies explicitly undefined. All 32 bodies remain unmeasured and the prototype
retains zero fabrication, installation, motion, and physical authority.

The arm lane on `codex/c03-ambient-light-static-contract` completed ARM-517
from merged ARM-516 base `e1a7a14120f13b37286363d08a97085de4f56346`.
It adds an ambient-light v3 collision contract and v4 nominal inventory for the
actual workcell architecture: variable ambient illumination with no dedicated
light or light-support hardware. It must preserve the earlier v2/v3 evidence,
retain ambient-light variation as a vision-domain condition, keep the factory
clamp collision requirement, and distinguish the nominal rear clamp zone from
the still-unmeasured installed clamp footprint and base transform. It may not
clear ICQ-1/ICQ-9, change AI-lane status, run hardware, or grant controller,
wire, joint, PWM, serial, transport, retry, permit, movement, or physical
authority.
Evidence `E-20261008-ARM-517` removes exactly four nonexistent fixed-light
bodies from new consumers, retains 28 ambient-architecture inventory rows, and
binds the factory clamp to the nominal 225–385 mm rear-edge zone. All 28 rows
remain unmeasured; installed collision qualification remains blocked.

The arm lane on `codex/c03-ambient-nominal-binding` completed ARM-518 from
merged ARM-517 base `540e259e22433c46b6b46ea0052f5b0eabc3e13a`. It may
derive diagnostic AABBs only from the selected printable portal datums and
nominal B0477 case dimensions, then screen the reconstructed C03 tool-tip
centreline at predeclared 0/5/10/20 mm clearances. It must keep this distinct
from a full-body or installed collision screen, retain every unbound clamp,
lens, connector, USB, harness, and tool-volume dependency, and grant no
controller, transport, permit, movement, or physical authority.
Evidence `E-20261008-ARM-518` records six nominal support/camera envelopes and
zero intersecting segments across all four diagnostic clearances for the
13-waypoint synthetic reconstructed route fixture. The result remains
simulation-only and cannot clear ICQ-1 or ICQ-9.

The arm lane on `codex/c03-physical-evidence-cli` completed the bounded operator
interface increment from merged ARM-502 base
`6cd647ec5cda9f5a1a40d63d79857e6b09d583e6`. It may add strict bounded loading
of the exact C03 route result and a command-line interface that emits the
ARM-502 JSON packet or read-only Markdown worksheet. Route and manifest bytes
must be caller hash-bound, duplicate JSON fields and changed bytes must fail
closed, and blocked readiness must return a nonzero status. It must not invent
measurements, change AI-lane status, clear ICQ-9, or emit controller, wire,
joint, PWM, serial, transport, retry, permit, or movement authority.
Evidence `E-20261008-ARM-503` records the strict route loader, operator CLI,
blocked exit semantics, and full offline regression result. Physical evidence
is still absent, so ICQ-9 remains blocked.
The bounded follow-up on `codex/c03-physical-evidence-cli-entry` may add only
the executable module guard and a subprocess help smoke. It changes no packet,
gate, evidence, or authority semantics.
Evidence `E-20261008-ARM-504` records the completed entrypoint smoke.

The arm lane on `codex/c03-physical-evidence-packet` completed the bounded ICQ
physical-evidence readiness increment from merged base
`985c9b4c4819c845ed097420cacdc7695fe37b20`. It may compose the existing ICQ-1
through ICQ-8 contracts into one deterministic, hash-bound capture packet that
lists installed-body measurements, rigid attachment transforms, cable sample
and sweep coverage, fresh observed-entry state, and the resulting aggregate
qualification dependency. Missing evidence must remain explicit and any
supplied artifact must pass its existing strict validator. The packet must not
invent physical measurements, reinterpret retained synthetic evidence, change
AI-lane status, clear ICQ-9, or emit controller, wire, joint, PWM, serial,
transport, retry, permit, or movement authority.
Evidence `E-20261008-ARM-502` records the deterministic packet, strict
dependency-order validation, exact capture counts, and zero-authority results.
The packet is preparation for physical collection only: ICQ-9 remains blocked
until real installed evidence produces an exact ICQ-8 `PASS`.

The arm lane on `codex/c03-entry-clearance-v2` completed ICQ-7.1 from the exact
merged ICQ-8 base `0b22610c433bea72d04b1e2c43df8541bdb20dc6`. It may add a
backward-compatible observed-entry clearance supplement that binds the sealed
ICQ-7 v1 receipt to conservative numeric clearance evidence for every owned
entry segment, then teach the aggregate qualifier to consume that supplement.
It must derive the bound from the same uncertainty-inflated collision geometry
and exact entry sample lineage already used by ICQ-7; caller-asserted margins,
missing segments, changed geometry, or crossed hashes must fail closed. The
increment may prove that a synthetic clear chain is structurally capable of an
ICQ-8 `PASS`, but it must not reinterpret the retained colliding rehearsal,
claim installed physical qualification, clear ICQ-9, or emit controller, wire,
joint, PWM, serial, transport, retry, permit, or movement authority.
Evidence `E-20261008-ARM-501` records the implementation and the synthetic
structural `PASS` fixture; the retained installed-profile rehearsal remains the
unchanged collision `REJECT` and ICQ-9 remains blocked on physical evidence.

The arm lane on `codex/c03-aggregate-qualification` completed ICQ-8 from the exact
merged ICQ-7 base `defafae746ee21189c82bd9d0009621961f1ae42`. It may
reconstruct one complete route qualification receipt from the exact ICQ-7
observed-entry receipt, C03 collision handoff and partition intake, cable
evidence receipt, and ICQ-6 continuous-route receipt. The validator must prove
exact hashes, shared lineage, route coverage and ordering, entry-to-route joint
continuity, partition boundary continuity, and one minimum-clearance/limiting-
body summary across the entry and every owned route segment. Missing,
duplicated, crossed, stale, mixed-profile, or authority-bearing evidence must
fail closed. The disposition is limited to `PASS`, `REJECT`, or `BLOCKED`;
synthetic inputs remain execution-ineligible even after `PASS`. The increment
must preserve the exact retained C03 route, remain zero authority, and emit no
controller, wire, joint, PWM, serial, transport, retry, permit, or movement
command. It must not change AI-lane status or clear an integration or physical-
authority gate. Evidence `E-20261008-ARM-500` records implementation commit
`f4c39379046eefeeb0c6692e71fd75e017760ba4` and the retained synthetic
`REJECT` rehearsal over 1 entry segment plus all 321 owned route segments.

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

The main-bound Workstream 1 semantic stream now reaches the strict v2 batch,
trusted registry ingress, deterministic execution-plan, and Cartesian
trajectory-preparation boundary at evidence `E-20261006-INT-461`. The repeated
targets in `hello 2026` remain ordered across 81 frozen range combinations,
while the installed-catalog `SHIFT` gap stops before batch creation. This is a
simulation-only zero-authority S2 increment; IK, collision admission, measured
configuration, controller transport, and physical use remain outside its claim.

Evidence `E-20261006-INT-462` advances that exact installed-subset stream into
the canonical IK boundary. The 5 mm route retains all 10 ordered targets and
260 Cartesian samples, but stops during the first `H` transit after 15 accepted
samples because normalized joint margin is `0.008368`, below the unchanged
`0.01` gate. A separately labelled 64-profile origin-sphere collision study ran
only on that accepted prefix; it cannot clear installed collision intake. The
full route, installed geometry, fresh observed start state, controller access,
and physical use remain blocked. The next shared dependency is an arm-owned,
hash-bound route or start-state correction that passes the existing margin gate,
followed by full-route collision evidence using reviewed candidate or installed
geometry.

Evidence `E-20261006-INT-463` rejects a seed-only correction. Sixty-four frozen
Halton interior seeds reproduced the same ready-tip point and replayed the exact
parent trajectory, but every candidate stopped at sample 15 with the same
normalized-arm-joint-margin rejection. Target order, target coordinates, the
260 Cartesian samples, and the `0.01` margin gate were unchanged. The next
bounded question is therefore route geometry or canonical branch-selection
policy, not additional start-seed sampling; no route correction is installed.

Evidence `E-20261006-INT-464` also rejects the frozen candidate-park grid. The
27 points covered offsets of `-20/0/20` mm in board X and Y around the first
target hover and `40/60/80` mm above it. Twenty-four candidates stopped on the
unchanged normalized-margin gate and three retained the canonical no-solution
condition as blocked. The best candidates accepted 13 samples, versus 15 for
the parent route. Further AI-side seed or park-grid sampling is not justified;
the dependency returns to an arm-owned waypoint-planner or canonical solver-
selection review, followed by a fresh frozen full-route study.

Evidence `E-20261006-INT-465` rejects canonical IK branch selection as the
missing route correction. Beam widths `2`, `4`, and `8` retained every distinct
converged solver attempt under the unchanged post-IK gates, but all three beams
again stopped at first-`H` transit waypoint 15. The width-8 beam evaluated 464
candidates through 116 bounded solver calls; all 32 candidates at the failing
waypoint violated the unchanged `0.01` normalized joint-margin gate. A first
result that temporarily extended the canonical solver is preserved. A second,
hash-bound compatibility reproduction moved enumeration into the exploratory
study, restored the canonical solver bytes required by older fixtures, and
reproduced every decision metric exactly. Neither candidate enumeration nor the
beam policy is installed. The next bounded arm question is explicit Cartesian
waypoint geometry that avoids the wrist-limit corridor while preserving target
order and every existing safety gate.

Evidence `E-20261006-INT-466` also rejects the first bounded Cartesian-corridor
family. Nine predeclared routes combined transit heights of 0, 20, and 40 mm
above the synthetic ready point with diagonal, X-then-Y, and Y-then-X planar
travel before descending to the exact first-`H` hover. Every candidate cleared
more samples than the direct parent route, then stopped during the common
descent for `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED`; zero candidates
accepted the full 260-waypoint semantic route. The original T1-wrapper rejection
is preserved separately: it occurred before candidate results because that
boundary correctly permits only byte-replayable compiler output. A pre-result
amendment retained all nine candidates and safety thresholds while using the
shared canonical post-IK waypoint evaluator. The study changes no installed
planner. The next arm-owned design question is a bounded margin-aware motion
planner rather than another manually enumerated height or axis-order grid.

Evidence `E-20261006-INT-467` rejects the first bounded margin-aware planner
family without changing the canonical `0.01` normalized joint-margin gate.
Three deterministic Cartesian RRT searches used the same Halton samples and
5 mm extension step with goal-bias periods `5`, `11`, and `23`. Each search
admitted the maximum 2,048 nodes, but none connected the synthetic ready point
to the exact first-`H` hover. All rejected expansions were rejected by the
unchanged normalized joint-margin gate. An invalid initial full-route sample
cap failed before candidate evaluation and remains preserved; the pre-result
amendment changed only that cap to the canonical maximum of 512. The result
does not prove global infeasibility, install a planner, or clear collision.
The next bounded question is a joint-specific endpoint/manifold diagnostic that
identifies the limiting joint and the closest admitted approach to the exact
hover before more planner volume is spent.

Evidence `E-20261006-INT-468` resolves that diagnostic question inside the
frozen synthetic model. The exact first-`H` hover produced zero converged
canonical IK candidates. Across a predeclared 729-point cube at 5 mm spacing,
69 nearby points passed the unchanged controller, `0.01` margin, and Jacobian-
rank gates. The closest admitted point was 18.71 mm from the exact hover at
offset `(-5, -10, +15)` mm. `link3_to_link4` was the limiting joint in all 138
margin-rejected candidate solutions. Planning cannot correct an endpoint with
no converged IK candidate; the next arm-owned task is to audit the synthetic
tool length, board transform, hover construction, and target geometry bindings
before changing any planner or target coordinate.

Evidence `E-20261006-INT-469` completes that binding audit without changing the
board transform or target coordinates. The target source, runtime catalog, and
execution plan all agree on `H` at `(216.55, 154.0, 21.0)` mm, and the nominal
board transform is propagated without alteration. The parent route is bound to
the unmeasured 100 mm tool and 10 mm hover combination, which again produced no
converged candidate. Four of 25 predeclared sensitivity cells were margin
admissible: 110 mm with 25 mm hover, and 120 mm with 15, 20, or 25 mm hover.
This localizes the synthetic blocker to the tool/hover combination. It does not
select a physical tool or install a route. The next bounded dependency is to
rebuild the full route from the converged 110 mm candidate configuration using
the 25 mm exploratory hover, then apply unchanged continuous collision and
route gates; physical use remains blocked on measurement and commissioning.

Evidence `E-20261006-INT-470` preserves the requested frozen 110 mm / 25 mm
reconstruction as a blocked full-route result. The exact first-`H` hover is
reachable, but the unchanged canonical screen rejects descent waypoint 24 at
`z=40.999267` mm because normalized joint margin falls to `0.000731`, below
the existing `0.01` gate. The reconstructed route accepted 24 samples versus
15 in the parent and contains 314 samples in total, but pointwise hover
feasibility did not imply a valid approach path. Candidate collision checks ran
only on the accepted prefix and remain sampled, incomplete geometry evidence;
the missing installed profile and continuous sweep proof remain blocked. The
next bounded dependency is an arm-owned descent-route reconstruction or a new
predeclared tool/hover candidate, with every existing margin and collision gate
retained.

Evidence `E-20261006-INT-471` rejects further bounded descent routing for the
110 mm tool. One direct control and 48 predeclared lateral/precontact corridors
all stopped on the unchanged normalized joint-margin gate. The best corridor
extended the accepted prefix to 29 samples, but an independent endpoint check
found zero converged IK candidates for the exact required `H` contact point at
`(216.55, 154.0, 21.0)` mm. Since every valid route must end there, additional
110 mm path search is not justified by this model. The next bounded candidate
is the previously hover-admitted 120 mm tool, beginning with exact-contact and
depth-profile checks before another full-route campaign.

Evidence `E-20261006-INT-472` rejects that 120 mm exact-contact candidate under
the same pinned synthetic geometry and unchanged post-IK gates. The corrected
vertical profile bootstrapped from the admitted 25 mm hover, accepted 12 of 26
one-millimetre profile points, and then failed at 13 mm above contact because
normalized joint margin was `0.009264`, below the unchanged `0.01` gate.
Independent point checks remained admissible down to 7 mm; 6 and 5 mm failed
margin, while 4 mm through the exact contact produced no converged candidate.
The first attempt, which incorrectly compared the hover against the unrelated
ready state, remains preserved. Since neither 110 mm nor 120 mm reaches exact
contact, no full-route or collision claim was run. The next dependency is an
arm-owned, predeclared synthetic geometry/configuration review; no margin,
target, or authority boundary may be relaxed.

Evidence `E-20261007-INT-473` compares that nominal transform with the already
governed promoted virtual commissioning overlay while retaining the exact `H`
contact, 120 mm tool, 25-to-0 mm profile, and unchanged post-IK gates. The
nominal case reproduces the blocked exact contact. The promoted case admits all
26 sequential profile points and four exact-contact candidates, with minimum
normalized joint margin `0.157771` and maximum adjacent delta `0.005227` rad.
This isolates the synthetic reach blocker to the source-bound transform choice.
The promoted profile remains an unmeasured, simulation-only sensitivity overlay
with zero physical release effect. The next bounded dependency is a frozen full
route reconstruction under that exact profile, followed by unchanged continuity
and collision gates; no physical transform, tool, or authority is installed.


Evidence `E-20261007-INT-474` completes that promoted-profile reconstruction.
All 328 route samples pass unchanged canonical IK and adjacent-joint
continuity, with minimum normalized arm-joint margin `0.050964` and maximum
adjacent delta `0.037773` rad. The first frozen run reached installed collision
intake and correctly failed its fixed 256-result bounded-sampling policy; that
attempt is retained in the successor fixture rather than rescored. The
successor records this resource refusal as an additional installed-collision
blocker and runs the already frozen candidate diagnostic over the full accepted
route. Every candidate profile reports sampled collisions, while its coarse
geometry and lack of continuous sweeps remain explicitly nonqualifying. The
installed collision gate remains closed, and the promoted profile retains zero
physical release effect. The next dependency is an arm-owned decision on how a
full accepted route is partitioned for bounded installed collision intake,
followed by measured installed geometry and continuous sweep evidence.


Evidence `E-20261007-INT-475` resolves the fixed 256-sample intake-size
blocker without raising that limit. The accepted 328-endpoint route is covered
by two partitions containing 255 and 73 unique source endpoints. Their bounded
plans contain 256 and 74 samples because the first plan includes the route seed
and the second deliberately rechecks the exact terminal pose of the first.
The boundary has zero joint-state difference, every source endpoint appears
once and in order, and no endpoint is omitted. This establishes a reusable
bounded partition contract; it does not perform installed-geometry or
continuous collision qualification. Those gates remain closed pending measured
profile-bound geometry, per-sample configuration evidence, and conservative
inter-sample sweep envelopes.

Evidence `E-20261007-INT-476` integrates those exact partitions into a
versioned collision-evidence intake. Each partition carries the same collision
contract identity, its bounded sample plan, and exact configuration and sweep
evidence-slot counts. All 328 route segments are owned exactly once across the
two partitions; the shared boundary is rechecked at zero joint-state difference
and requires no invented zero-length sweep envelope. The frozen run correctly
retains the missing installed-profile blocker and performs no collision screen.
Installed geometry, configuration evidence, conservative sweep envelopes, and
a fresh observed start state remain required before any collision or physical
gate can advance.

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

ARM-136 extends that same actual-emitter boundary from one word to a sustained
mixed FIFO queue: `H,I`; `R,O,B,O,T`; `H,H,1,PERIOD`; `A,Z`; and
`1,SPACE,ENTER`. Across each cold and warm round, all five shadow receipts
completed in order. The cold round made 186 exact solver-input lookups, reused
138 values shared within and across requests, and performed 48 complete solves;
the warm round reused all 186. On the recorded host, cold p50/p95 were
0.2685515/1.3913187 seconds and warm p50/p95 were 0.1982934/0.2997009 seconds.
These five-sample timing observations are diagnostic, not stable latency bounds,
admission criteria, controller timing, or physical typing-speed evidence. The
retained campaign used no transport, controller, executor, hardware write, or
physical movement.

ARM-137 replaces the five-sample timing indication with a repeated isolated
stability campaign. Twenty cycles each create a cold service and a separate
prewarmed service, measure the same five actual-emitter requests, compare exact
shadow-receipt hashes, and retire both lifecycles. All 100 cold and 100 warm
requests were FIFO-complete and decision-equivalent. Cold p50/p95/p99 were
0.2736679/1.4014767/1.4241501 seconds; warm values were
0.1959784/0.3044458/0.3157095 seconds. Every replacement began with the expected
48 complete solves, every measured warm lane hit 186/186 inputs, and no capacity
skip occurred under the frozen 256-entry, 8-queued, 16-request bounds. This is
still host-measured synthetic integration evidence: it neither fixes production
latency thresholds nor predicts controller, motion, contact, or device-effect
time.

ARM-138 qualifies bounded disturbance behavior around that warm service. A full
eight-request queue completed FIFO with 313/313 exact-input hits while a ninth
submission failed closed. Three of eight queued requests were canceled before
admission; the five survivors completed FIFO with 175/175 hits and no cache work
from canceled requests. Identity mismatch, owner-input override, and request-ID
reuse were rejected before any lookup. Reload and restart made queued work stale,
disabled exact reuse, and allowed only complete-solve fallback with no automatic
retry. A separately requalified replacement restored the warm path and produced
the exact reference shadow receipt. This retained campaign opened no controller
or transport and generated no hardware command or motion.

ARM-139 converts those observations into an explicit zero-authority runtime
supervisor. `WARM` is available only while the frozen profile remains eligible;
startup mismatch enters `FULL_SOLVE_ONLY`; reload or restart enters
`REQUALIFICATION_REQUIRED` and blocks new submissions while already queued work
is returned stale. Continuing without a new qualification requires an explicit
transition to `FULL_SOLVE_ONLY`, which cannot retain exact reuse. Returning to
`WARM` requires a separately qualified replacement. The retained seven-case
campaign preserves the reference plan through both startup full-solve fallback
and qualified replacement, permits no automatic retry, and remains detached
from the controller and executor.

ARM-140 connects the actual-emitter boundary to that supervisor through a
signed command-admission gateway. Valid canonical model bytes can be admitted
in `WARM` or `FULL_SOLVE_ONLY`; malformed or duplicate input, queue saturation,
request exhaustion, and requalification state each return a distinct signed
rejection. The retained eight-case campaign preserves the exact reference
shadow receipt across normal admission, startup fallback, and qualified
replacement, while every rejection remains nonretrying. This is the shared
AI/arm handoff for supervised shadow planning only: no executor, controller,
transport, command encoding, or physical authority is attached.

ARM-141 provides the shared request-lifecycle contract above ARM-140. A model
caller supplies a mission ID and request ID once; the ledger fingerprints the
canonical payload, chains the admission receipt to exactly one terminal shadow
receipt, and supports deterministic lookup. An identical duplicate returns the
same receipt without re-planning, while a changed duplicate fails closed.
Cancellation, stale lifecycle, admission rejection, and bounded-capacity
outcomes are explicit and nonretrying. The retained eight-case campaign uses
the actual shared emitter and grants no executor, controller, transport, or
physical authority.

ARM-142 defines the last zero-authority artifact before future physical
qualification: a deterministic execution-handoff candidate. It binds the
ARM-141 terminal session to its signed admission, terminal service receipt,
and full shadow-planning receipt, preserving the execution-plan, trajectory,
IK, schedule, and collision-intake hashes. The candidate is intentionally
blocked until installed collision evidence, fresh observed and controller
state, a one-use permit, and independent effect verification exist. An eight-
case campaign rejects noncompleted sessions, lineage substitution, and
authority tampering; no candidate is executor-eligible or physically
authoritative.

ARM-143 makes that detailed shadow receipt retrievable from the shared runtime
instead of requiring a caller to run the planner a second time. The service
stores the canonical artifact before declaring completion, addresses it by the
terminal receipt hash, and exposes it through the supervisor, gateway, and
session ledger. Storage is bounded and immutable: exact repeated retrieval is
allowed, but replacement, wrong content address, unknown request, and capacity
overflow fail closed. Canceled and stale requests cannot produce artifacts.
The retained eight-case campaign remains synthetic and zero-authority; it adds
no executor, permit, controller command, transport access, or physical motion.
Its immutable evidence is
[`typing_shadow_artifact_store_campaign_v1.json`](../eval/typing_shadow_artifact_store_campaign_v1.json),
generated from clean framework commit
`69ef09bab0b62cceb2ab78b35e4f3c733137fd8d`.

ARM-144 reduces the public handoff operation to `(ledger, request_id)`. The
assembler obtains all four exact ARM-142 inputs from the canonical ledger and
ARM-143 store, validates their lineage through the existing candidate builder,
and never re-runs planning. Incomplete, rejected, stale, and unknown sessions
cannot assemble a candidate. Completed evidence remains reconstructable after
runtime invalidation for audit, while every execution blocker and zero-
authority field remains unchanged.
The retained evidence is
[`typing_execution_handoff_assembler_campaign_v1.json`](../eval/typing_execution_handoff_assembler_campaign_v1.json),
generated from clean framework commit
`5fb4801956c800dba75c56722911acaf99493fb2`.

ARM-145 corrects an evidence-body gap before permit review. ARM-142 through
ARM-144 bound five planning stages by hash, but a future physical review must
also possess their canonical bodies to rerun collision and start-state checks.
The shadow service now captures and immutably retains the execution plan,
trajectory, IK screen, joint schedule, and collision intake, with every body
verified against the terminal receipt. The bundle is synthetic shadow evidence,
not a permit-review package, and it grants no controller or physical authority.
The retained
[`typing_shadow_materialization_campaign_v1.json`](../eval/typing_shadow_materialization_campaign_v1.json)
records eight lifecycle and integrity cases against clean framework commit
`81d25e1a06484b7c89f6048e5795c8372769dcbb`: exact five-stage retention,
deterministic repeat and post-invalidation retrieval, tamper rejection, and no
materialization for queued, canceled, stale, or unknown requests. All results
remain offline and zero-authority; the governed matrix passes 883 tests after
evidence pinning.

ARM-146 introduces
[`typing_permit_review_readiness_v1.py`](../../src/rocell/application/typing_permit_review_readiness_v1.py)
as the shared handoff map from retained shadow planning into the existing
physical review stack. It records the exact materialization and five stage
hashes, recognizes only the three planning-retention prerequisites already
proved, and assigns each remaining blocker to its required adapter. V1 is
deliberately blocked-only: model qualification, a measured trajectory envelope,
installed and continuous collision evidence, fresh observed and controller
state, an independent effect verifier, and per-action review binding must be
authenticated by typed adapters. No AI or arm worker may replace those inputs
with a Boolean readiness claim or an untyped digest.
The full governed offline matrix passes 887 tests at this boundary.

ARM-147 begins resolving the readiness map through typed evidence rather than
flags. `typing_state_prerequisite_binding_v1` requires an authenticated observed
planner state plus the existing independently approved installed-controller
evidence and its zero-write qualification report. It binds calibration digest,
freshness windows, evidence digest, and controller session, then removes exactly
the two state blockers. Deployment-qualified planning, measured trajectory,
installed/continuous collision, independent effect verification, and per-action
review binding remain mandatory and unresolved.
The full governed offline matrix passes 890 tests with this binding included.

ARM-148 adds the next non-authoritative bridge without prematurely certifying
collision. `typing_observed_ik_seed_v1` binds the retained materialization,
ARM-147 state binding, active build, calibration, controller session, freshness
window, and exact five-joint observed pose into one immutable
`PHYSICAL_OBSERVED_STATE` seed. It performs no IK or collision qualification and
cannot produce review, permit, controller, wire, or executor authority. This
ordering is intentional: the current collision intake was derived from the
synthetic shadow seed, so installed continuous-collision evidence must be built
only after the retained route is re-screened from this observed seed. The next
adapter must consume this exact seed and retained trajectory, produce a measured
IK/trajectory result, and continue to fail closed on installed geometry,
measured dynamics, continuous collision, and effect-verifier prerequisites.
The governed offline matrix passes 893 tests with this bridge included.

ARM-149 consumes that exact observed seed and replays the retained execution and
Cartesian trajectory bodies before invoking the canonical deterministic IK
screen. The output binds every evaluated joint result back to the retained
materialization, active build/calibration, controller session, observed state,
and seed. The original synthetic seed class remains distinct and supported;
only those two concrete typed seed classes can reach the shared solver.
Successful IK is deliberately not described as a measured trajectory envelope:
the observed physical pose may differ from the retained route's modeled PARK
entry. ARM-149 therefore leaves an explicit observed-start-to-route-entry
envelope, physically qualified dynamics, installed/continuous collision,
effect-verifier, and per-action review requirements closed. It produces no
controller or wire commands and grants no permit or execution authority.
The governed offline matrix passes 896 tests with this re-screen included.

ARM-150 consumes the exact ARM-149 report and ARM-148 observed seed to retain a
bounded joint-space envelope from the measured pose to the route's first PARK
solution. The shared sampler limits every adjacent joint step and the strict
decoder verifies sample order, interpolation, hashes, endpoints, policy limits,
and complete nested observed-state lineage. This gives both workstreams one
explicit route-entry artifact instead of an implicit jump from physical state
to modeled route. It remains an offline planning artifact: installed geometry,
continuous collision clearance, measured dynamics, effect verification,
per-action review, permit, and execution authority are still required. No
controller or wire commands are produced and no hardware is accessed.
The governed offline matrix passes 899 tests with this envelope included.

ARM-151 connects that envelope to the arm-owned installed-collision stack. It
recomputes robot-link transforms from every exact bounded joint sample and the
pinned URDF, admits only profile-bound measured attachment and
configuration-geometry evidence, and seals the nested collision result back to
the observed request/session lineage. This is the common handoff point at which
AI-owned targets remain unchanged while arm-owned geometry can reject an unsafe
entry. A clear discrete-sample result still cannot imply continuous clearance,
measured dynamics, verification, review, permit, or execution. The current
automated evidence uses accepted-measured fixtures and grants no deployment or
physical qualification.
The governed offline matrix passes 902 tests with this adapter included.

ARM-152 supplies the continuous-entry bridge after ARM-151. It evaluates every
adjacent bounded sample pair using URDF-derived rigid motion inflation and one
profile-bound measured envelope per deformable body. The AI target and ordered
typing plan remain untouched; the arm lane can now reject a route because its
inter-sample swept envelope is unsafe, not merely because an endpoint collides.
Even a clear result is limited to the bound geometry and retains global
pair-exclusion, phase-contact, installed physical, dynamics, verification,
review, permit, and execution gates. Automated evidence still uses measured-
classified fixtures and is not deployment qualification.
The governed offline matrix passes 905 tests with this sweep bridge included.

ARM-153 adds the arm-owned measured-dynamics bridge without changing AI target
coordinates or action ordering. It consumes the already cached entry samples
and ARM-152 clearance record, then creates a cadence-aligned schedule under a
fresh installed-limit profile for joint velocity, acceleration, jerk, and
settling policy. The strict decoder reconstructs both profile and schedule, so
resealing altered timing cannot create acceptable evidence. This is planned
dynamics evidence only: controller tracking and settling must still be observed
on the installed system, and all review, permit, execution, and effect gates
remain closed. Current passing evidence is a physical-qualified-class fixture,
not a physical qualification.
The governed offline matrix passes 908 tests with this dynamics bridge included.

ARM-154 adds the evidence contract needed to compare installed controller
feedback with ARM-153 without changing AI-owned target content. It requires an
observation at every scheduled entry sample plus an endpoint window long enough
to satisfy the pinned settling dwell, and it binds all samples to one build,
controller session, retained export, native identity, and acquisition
qualification. The result deliberately says sampled tracking rather than
continuous tracking. Independent task-effect verification and all review,
permit, and execution gates stay closed. Automated passing evidence remains a
physical-qualified-class fixture, not installed-controller evidence.
The governed offline matrix passes 911 tests with this tracking bridge included.

ARM-155 extends the arm-owned evidence lane from scheduled-point checks to
bounded coverage across the complete entry interval. A dense retained stream is
matched to interpolated ARM-153 joint targets, with exact motion boundaries and
a qualified maximum observation gap. AI target coordinates and ordering remain
unchanged; this stage only tests whether installed feedback stayed within the
arm-owned envelope at the retained sample times. The result cannot claim what
happened between samples, so continuous tracking, device effect, review, permit,
and execution remain separate gates. Passing CI evidence remains fixture-only.
The governed offline matrix passes 914 tests with this coverage bridge included.

ARM-156 provides the shared commissioning backbone after camera arrival. Its
ten-stage fixture-replacement registry connects the existing 15-slot arrival
orchestrator and physical localization evaluator to installed geometry and the
ARM-149-ARM-155 observed-entry chain, ending at independent single-key effect
verification. Each stage names its native schema, expected status, physical
replacement, and earlier dependencies, so AI and arm work cannot silently use
different evidence or promote fixtures. The companion runbook preserves the
AI/arm ownership split and requires exact build, epoch, session, and evidence
lineage. It remains a zero-authority pre-commissioning record.
The governed offline matrix passes 917 tests with ARM-156 included.
The process-alignment overlay in `E-20260929-INT-450` binds an AI-produced
`ModelMotionBatchV2` carrying ordered `H, H, 1, PERIOD` proposals to the
governed RC03 Isaac scene. Target centers share one rigid synthetic placement
within numerical precision, but the 14.400834977 mm localization disk exceeds
each 7 mm key-edge margin. The replay therefore stops before a joint schedule.
Its next simulation input is the exact zero-write schedule from the arm typing
pipeline after the source batch passes the safe-region uncertainty gate.

`E-20261004-INT-453` separately makes an older retained simulator result usable
without weakening that gate. It binds the actual-emitter schedule bundle to its
full-route Isaac receipt and derives the contiguous `0..34` prefix ending at
the first noncontact `H` hover. The prefix contains no contact sample and is
conservatively bounded by the passing full-route maximum of 0.07684843 mm.
This satisfies the issue's kinematic replay evidence milestone only. Its
synthetic observations, unmeasured layout/tool geometry, zero physics steps,
and unsafe 14.400834977 mm localization bound remain explicit blockers; the
derived proof cannot authorize deployment or physical motion.

`E-20261004-INT-454` begins the next WP2 collision-foundation increment by
binding the official Waveshare `roarm_ws` Xacro and seven per-link STL blobs to
one immutable upstream commit and tree. The Xacro uses identical visual and
collision references with zero local origins and a declared `0.001` scale. The
source meshes contain 38,344 triangles across 19 connected bodies; `link1` and
`link5` are not watertight, and one left-gripper mesh is unreferenced. This is
source provenance only. It deliberately does not prove robot-frame alignment,
install reduced collision geometry, choose self-collision pairs, run clearance
replay, or grant simulator, controller, hardware, or physical authority.

`E-20261004-INT-455` derives 14 deterministic link-local box candidates from
those exact source meshes. All 19,030 processed source vertices remain inside
their serialized candidate boxes. `link5` exceeds the runtime contract's
64-primitives-per-body limit with 114 processed fragments and therefore uses a
declared whole-link envelope. The largest box/source volume ratio among
watertight components is 21.140797, so these shapes are intentionally retained
as conservative candidates only. They are not installed, and false-positive
collision behavior, self-collision pair policy, clearance replay, tool/camera
support geometry, controller access, and physical authority remain blocked.

`E-20261004-INT-456` compares those candidates with the exact source-bound
meshes for every one of the 21 unordered link pairs at the governed zero,
home, and ready poses. Across 63 pair-pose cases it retains 48 free-space
agreements, three collision agreements, 12 conservative-candidate false
positives, and zero observed candidate false negatives. All 12 false positives
are kinematically adjacent pairs, but the probe does not silently exclude them.
Three poses are not continuous workspace coverage, so self-collision policy,
candidate installation, collision admission, clearance replay, tool/camera
support geometry, controller access, and physical authority remain blocked.

`E-20261004-INT-457` expands that differential to 49 deterministic governed
joint-space poses: the three existing anchors, lower/upper/midpoint limit
anchors, 12 single-joint limit poses, and 32 Halton interior samples. Across
1,029 pair-pose cases it retains 780 free-space agreements, 57 collision
agreements, 192 conservative-candidate false positives, and zero observed
candidate false negatives. Of the false positives, 191 are adjacent-link cases
and one is the nonadjacent `link2/gripper_link` pair. The corpus therefore
identifies a concrete refinement target without selecting exclusions or
installing a profile. Finite samples are not continuous coverage; collision
admission, clearance replay, tool/camera/support/environment geometry,
controller access, and physical authority remain blocked.

`E-20261005-INT-458` refines the sole nonadjacent witness with a 16-group
complete-triangle partition of `link2`. Its 49-pose replay removes the
nonadjacent false positive and retains zero observed false negatives; all 165
remaining false positives occur on directly connected pairs. A disjoint
256-pose stress replay supports all six upstream `Never` proposals without
contradiction, but the proposals remain counterfactual and effective exclusions
remain empty. The result advances review evidence only. Finite samples,
non-watertight source meshes, missing installed measured tool/support/workcell
geometry, continuous clearance, engineering acceptance, controller access, and
physical qualification remain explicit blockers.

`E-20261006-INT-459` ports the branch-only recovery state machine to a focused
CPU-only kernel on current `main`. Two byte-identical runs reproduce all 1,244
declared keyboard/phone recovery scenarios with zero false recoveries or
ambiguous continuations. The amendment explicitly labels this as post-result
portability reproduction, preserves the predecessor ranges and rules, and does
not claim a new selection result. The kernel still lacks a main-bound
Workstream 1 twin, measured perception and landing-sensor behavior, real device
effects, controller transport, hardware qualification, and physical authority.

`E-20261006-INT-460` restores the smallest main-bound Workstream 1 semantic and
device-state twin without importing the research branch's unrelated planner or
catalog history. The preserved first execution failed before metrics because of
a full-mode seed lookup bug; v1.1 fixes only that lookup and retains the same
ranges, populations, fault cases, metrics, and rules. Two full runs each replay
10,010 strings and 318,884 characters per device with zero text failures and the
same core receipt. Eight independently classified virtual readback effects feed
the portable recovery kernel with zero classification or terminal mismatches.
This composes virtual verification and recovery only. Perception, IK, collision,
contact physics, real host/ADB evidence, transport, hardware, and physical
authority remain outside the result.

The AI lane on `issue/190-c03-arm-reconciliation` owns the bounded C03-to-arm
identity reconciliation. Its frozen fixture compares the admitted C03 recipe
and exact key-clearance receipts with the current promoted full-route and
partitioned collision-intake receipts. It may report only a zero-authority
identity decision and retained blockers. It must not change arm-lane status,
clear an integration gate, execute collision screening, or reinterpret the C03
key-only result as full robot/workcell evidence. The pre-result fixture is
[`c03_arm_route_reconciliation_fixture_v1.json`](../sim/evidence/c03_arm_route_reconciliation_fixture_v1.json),
canonical SHA-256
`73bfa179c410ff83747b09c63272a999b2e627e0b66faed8bbe0688ed6b2562c`.
Evidence `E-20261007-AI-477` now preserves the resulting fail-closed decision:
the admitted C03 tool is 110 mm while the promoted route is bound to 120 mm.
No collision run was attempted across that mismatch. The next bounded AI-lane
dependency is a new full-route reconstruction for the exact admitted 110 mm
tool, including orientation transitions; installed collision profile and fresh
observed-state requirements remain arm-owned blockers.
Before route reconstruction, successor fixture
[`c03_arm_route_reconciliation_fixture_v1_1.json`](../sim/evidence/c03_arm_route_reconciliation_fixture_v1_1.json)
also binds the selected 30 mm-exposure C03 pose profile and both target-catalog
files. Its frozen canonical SHA-256 is
`f3f225eaac375d4f8f325c7c841dcc8546019f6ea9c0466465e338753a307d5f`.
This pre-result amendment checks whether target geometry can be composed; it
does not alter the preserved v1 tool-length STOP result.
Evidence `E-20261007-AI-478` preserves the successor result: the selected C03
pose family also binds candidate target catalog SHA-256 `0fe3c013...`, while
the promoted route binds main catalog file SHA-256 `6779213e...`. The next
route reconstruction must therefore bind both the exact 110 mm C03 tool and
the exact C03 candidate target geometry; changing only tool length would still
mix incompatible evidence.
The pre-result coordinate-audit fixture
[`c03_arm_route_reconciliation_fixture_v1_2.json`](../sim/evidence/c03_arm_route_reconciliation_fixture_v1_2.json),
canonical SHA-256
`1c7fccfb40b57a7633b752e03abfff2bd82fd38da425f9d08e4c6862fccc183c`,
freezes the ordered `H,E,L,L,O,SPACE,2,0,2,6` route. It will report every
main-versus-C03 center delta while preserving repeats; it cannot install the
candidate catalog, alter semantic order, run IK, or clear collision blockers.
Evidence `E-20261007-AI-479` reports that six of the ten ordered route actions
move under C03 geometry: `E`, `O`, `2`, `0`, repeated `2`, and `6`. The largest
planar shift is 15.11357334572232 mm. A 110 mm successor must therefore rebuild
the route from the C03 catalog rather than replace only the tool transform.
The AI lane now freezes that successor in
[`c03_exact_route_reconstruction_fixture_v1.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1.json),
canonical SHA-256
`f48940215bfb211d8e7f1eebc42d04eda9d2a621291bfe2d8350eb86db7cb197`.
It assembles the unchanged ordered semantic batch against the exact C03 catalog,
uses the admitted 110 mm/3 mm-radius/30 mm-exposure tool identity, and applies
the unchanged canonical IK and continuity gates. Collision execution, installed
profile admission, controller output, and all physical authority remain excluded.
The first frozen route attempt is preserved at evidence `E-20261007-AI-480`.
It failed before IK because the runtime coherence guard correctly rejected an
in-memory catalog replacement that differed from the locked bundle source.
The successor must materialize and hash-bind a coherent simulation bundle; the
guard and its comparison rules remain unchanged.
The coherent successor fixture
[`c03_exact_route_reconstruction_fixture_v1_1.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_1.json),
canonical SHA-256
`56f3fae5dcd48076dac619a3d49c12b1e0d58294007adb16af41fabdb180e107`,
freezes source tree `fe80a94c26d564cd2e7233c6b85beef6909aab3c`, its 6,480
tracked paths, the external derived-workspace root, and the catalog-specific
bundle identity. It reruns the unchanged predecessor route only after the normal
context loader and ingress coherence checks accept the relocked workspace.
The first coherent-workspace attempt is preserved at evidence
`E-20261007-AI-481`. It failed during Git-tree extraction because the frozen
external destination made an existing tracked build-record path exceed the
Windows path limit. No context, route, or IK evaluation occurred. A successor
may shorten only the external destination while preserving all identities and
gates.
The short-path correction is frozen in
[`c03_exact_route_reconstruction_fixture_v1_2.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_2.json),
canonical SHA-256
`b9fff9ef175be1c049040861afbe5c16fad3a240262a576485398cbc0dc431c1`.
Only the external materialization root and derived bundle ID change. Source
commit, tracked population, candidate catalog, predecessor fixture, route,
tool, and every decision gate remain identical.
The short-path run is preserved at evidence `E-20261007-AI-482`. Extraction
completed, but the historical promoted parent fixture correctly rejected the
candidate catalog because its input binding still pins the main catalog hash.
A successor must derive new catalog-bound fixture hashes while retaining every
numerical route and IK policy; historical fixtures remain immutable.
The catalog-rebound successor is frozen in
[`c03_exact_route_reconstruction_fixture_v1_3.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_3.json),
canonical SHA-256
`db7d824aef7d235b31f29848840e6c80aad5f4df327282562a8f42f73b6a6b02`.
Its allowlist changes only the parent target-catalog hash and the predecessor's
derived-parent file and canonical hashes. Its numerical policy change count is
zero; historical repository fixtures are never rewritten.
Evidence `E-20261007-AI-483` preserves the result. Source materialization and
both route-fixture rebindings succeeded, then the unchanged context loader
rejected the derived bundle because the virtual commissioning profile still
binds the historical bundle ID. A successor must derive that profile binding
and its bundle-lock artifact hash as an explicit identity-only change while
preserving all study values, authority fields, route policies, and repository
artifacts.
The bundle-identity successor is frozen in
[`c03_exact_route_reconstruction_fixture_v1_4.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_4.json),
canonical SHA-256
`7b5572298746451fed5e9ca773c60b708195a03cfed712dff72596726dfb39cb`.
It adds exactly two allowed semantic changes: the derived virtual profile's
simulation-bundle ID and the bundle lock's hash for those derived profile
bytes. Numerical policy change count remains zero. Study values, authority,
route fixtures, historical repository files, and every route gate are retained.
Evidence `E-20261007-AI-484` preserves its result: the coherent bundle loaded,
then the promoted-parent fixture independently rejected the derived virtual
profile's new file hash. The next successor must add that parent
`promoted_profile` binding to the explicit derived-fixture allowlist and
recompute the already allowed parent/predecessor identities. No numerical or
authority change is permitted.
The parent-profile-bound successor is frozen in
[`c03_exact_route_reconstruction_fixture_v1_5.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_5.json),
canonical SHA-256
`feef5909cd4ff82b7835eea8bbc654ace9c39830b6462fe6b6c3e1913190dc3b`.
It adds only `parent.input_bindings.promoted_profile.sha256` to the prior
derived-fixture allowlist. Both rebinding contracts retain zero numerical
policy changes and zero authority.
Evidence `E-20261007-AI-485` preserves the result. The run loaded the coherent
bundle and parent fixture and reached strict batch ingress. Revalidation then
rejected the candidate targets because the immutable predecessor loaded them
through the external evidence path rather than the bundle's internal locked
path. A successor may change only that predecessor binding path to
`software/config/nominal_target_profiles.json`; the candidate hash, numerical
policies, and authority remain unchanged.
The locked-catalog-path successor is frozen in
[`c03_exact_route_reconstruction_fixture_v1_6.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_6.json),
canonical SHA-256
`5facf1090988dc3add5373d3154fb585b8b320ceff9bc3a61d3f62e246ecee8d`.
It adds only the predecessor candidate-catalog path to the derived-fixture
allowlist. The candidate hash remains identical and both rebinding contracts
retain zero numerical policy changes and zero authority.
Evidence `E-20261007-AI-486` preserves the result. Strict batch ingress and
fresh-registry revalidation passed. Promoted placement validation then rejected
the parent fixture's historical `promoted_profile.source_sha256`. The next
successor may bind that field to the already derived profile hash while
retaining profile ID, study-input ID, numerical policies, and zero authority.
The promoted-profile-source successor is frozen in
[`c03_exact_route_reconstruction_fixture_v1_7.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_7.json),
canonical SHA-256
`9c2fcd728716fc6d7b703ce72a92875ba4b499fcd1064805e9ca1093655c8870`.
It adds only `parent.promoted_profile.source_sha256` to the derived-fixture
allowlist. Profile ID, study-input ID, candidate catalog, numerical policies,
and authority remain unchanged.
Evidence `E-20261007-AI-487` preserves the result. All identity and ingress
gates passed, then route compilation exposed that the promoted fixture's route
view omits numerical fields retained in its hash-bound IK/collision parent.
The next successor must predeclare the exact inherited field set and copy those
values byte-for-byte from that parent. It may not tune or invent a value.
The inherited-route-policy successor is frozen in
[`c03_exact_route_reconstruction_fixture_v1_8.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_8.json),
canonical SHA-256
`7a00f32fbea183abce7a44a64a5516b4b8c81b964dca748758c1604f46ea5a25`.
It enumerates all ten missing fields and copies them byte-for-byte from the
promoted fixture's existing hash-bound IK/collision parent. No value is tuned
or invented; numerical policy change count remains zero.
Evidence `E-20261007-AI-488` preserves the result. The exact route compiled and
reached pose-to-target validation, where every unique route target showed the
same 1.0 mm Z mismatch: candidate catalog centers are at 21.0 mm and admitted
C03 contact targets are at 20.0 mm. X and Y match. The route remains blocked;
the equality check and catalog are unchanged. The next AI-lane dependency is a
new C03 pose-family generation and admission run against the exact candidate
catalog and 110 mm tool before any IK or collision claim can continue.
The C03 pose-family regeneration is frozen in
[`c03_pose_family_regeneration_fixture_v1.json`](../sim/evidence/c03_pose_family_regeneration_fixture_v1.json),
canonical SHA-256
`1532890bde0bdabaa4a4b3bd21942edf24748399fc34754e1dbdeb49f9141325`.
It binds simulation implementation commit
`13c44aedd3dbd04054d88665332a56e6e7d31bc1`, implementation SHA-256
`4f73bfd7e980ef1554a8fa3972e4f3a9f226ba09bfa5f8f34305f77a68214f06`,
and a 51-target seed source whose contact points were replaced by the exact
candidate catalog centers. All 51 source contact targets are at 21.0 mm and
match the catalog byte-for-byte by target. Recipe, 110 mm tool, route gates,
IK gates, and authority remain unchanged. No pose result has been opened yet.
Evidence `E-20261007-AI-489` records the result:
`PASS_EXPLORATORY_CANDIDATE51_110MM_POSES`. All 51 targets solved for both
110 mm profiles, every contact target is at 21.0 mm, and maximum IK position
error is 0.006290654447909852 mm under the unchanged 0.01 mm gate. The result
and seed source are hash-verified on `C:` and `F:`. This is simulation-only pose
admission; the exact route and collision gates remain open.
The regenerated-pose route successor is frozen in
[`c03_exact_route_reconstruction_fixture_v1_9.json`](../sim/evidence/c03_exact_route_reconstruction_fixture_v1_9.json),
canonical SHA-256
`cab208fea68adbfc89894b6030c9607b6624d03ada0b8d0691d3c1e6fdbb3467`.
It changes only the derived predecessor's C03 pose-family path, file hash, and
receipt hash to `E-20261007-AI-489`. Every inherited route value, IK gate,
catalog binding, semantic action, repeated target, and authority rule remains
unchanged.
Evidence `E-20261007-AI-490` records
`PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY`: all 321 trajectory samples
passed canonical IK, minimum normalized arm-joint margin is 0.0261, and maximum
adjacent joint delta is 0.035543 rad. The exact ordered route including repeated
`L` and `2` is retained. This clears only the simulation IK and continuity
question. Collision was not executed, the installed collision gate remains
blocked, and the AI lane grants no controller or physical authority. The next
dependency is arm-lane installed-profile collision screening with fresh state.
Evidence `E-20261007-ARM-491` completes the strict handoff into the existing
partitioned collision intake. The exact route maps to 321 route segments across
two bounded partitions and 323 samples including one boundary recheck. It stops
correctly at `BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED`; fresh observed
state is also retained as a blocker. No collision check or authority was
created. The next arm increment requires the measured installed collision
profile and full configuration plus conservative sweep evidence.
Evidence `E-20261007-ARM-492` composes that exact handoff with the deterministic
installed-profile builder. The real retained route stops at
`BLOCKED_MEASUREMENT_MANIFEST_REQUIRED`, while focused synthetic fixtures prove
that incomplete measurements remain blocked and a complete hash-bound manifest
can enter the profile-bound partition intake without claiming collision
clearance. The next dependency is a real installed measurement manifest; the
software must not substitute test geometry. Configuration-sampled cable
geometry, conservative sweeps for all 321 segments, and fresh observed state
remain subsequent blockers.
Evidence `E-20261007-ARM-493` adds the ICQ-3 rigid attachment binding intake for
that profile-bound route. It requires exact, fresh, source-bound
`Wv_T_camera_module` and `Wv_T_holder` transforms, rejects reversed or reflected
frames and crossed identities, and proves deterministic behavior with a
synthetic-only rehearsal. No real transforms exist yet, so the physical
measurement blocker remains unchanged. Configuration-sampled moving-cable
geometry is the next software package and cannot be satisfied by these rigid
bindings.
Evidence `E-20261007-ARM-494` preserves the first ICQ-4 full-route rehearsal
failure: the retained synthetic rigid manifest referred to a different
qualification receipt, so the unchanged strict ICQ-3 boundary rejected it
before cable admission. Evidence `E-20261007-ARM-495` then adds the strict ICQ-4
adapter and a newly derived synthetic rigid manifest bound to the exact rebuilt
qualification. The synthetic-only rehearsal covers 323 partition samples, 321
owned adjacent segments, and one exact boundary recheck. It rejects
endpoint-only interpolation and inflates each cable radius by capture and
unobserved-deformation uncertainty. No installed cable capture exists and no
collision screening, command, hardware write, movement, or authority occurred.
Evidence `E-20261007-ARM-496` preserves the first ICQ-5 failure: the current
unit-test snapshot did not match the retained route's exact calibration hash,
so both partitions stopped before collision evaluation. Evidence
`E-20261007-ARM-497` reconstructs the exact retained snapshot and evaluates all
323 sample slots and all 321 partition-owned sweep slots exactly once. Both
partitions correctly report `BLOCKED_PARTITION_COLLISION_DETECTED` against the
synthetic contract-rehearsal profile. This is a useful negative result and no
clearance claim: every synthetic sample and envelope collided, ICQ-6 continuous
proof remains absent, and no command, write, movement, gate, or authority was
created.
Evidence `E-20261007-ARM-498` implements the ICQ-6 continuous receipt over the
reviewed path-radius and independently measured sweep-envelope method. The
receipt recomputes each rigid-body motion bound from exact joint deltas, body
path radius, and ancestor joints; rejects changed bounds; consumes all 321
current route segments once; reproduces the exact configuration-geometry
boundary recheck; and distinguishes `CLEAR`, `COLLISION`, and `INDETERMINATE`.
An adversarial fixture proves clear endpoints cannot hide a swept collision.
The retained full-route synthetic rehearsal remains `COLLISION` on all 321
segments. This is software and negative synthetic evidence only: real installed
geometry, fresh observed entry, command generation, and physical authority
remain blocked.
Evidence `E-20261007-ARM-499` implements ICQ-7 over the exact retained C03
route. It authenticates one read-only observed joint state and its controller
session, enforces monotonic freshness, interpolates from the observed joints to
exact C03 waypoint zero, and reuses the reviewed FK collision and conservative
sweep engines. Its receipt binds route, target catalog, tool, calibration,
build, model, installed profile, rigid placement, cable sample, and cable sweep
identities; stale or mismatched state requires replanning and no nominal-start
snap is permitted. The retained synthetic rehearsal evaluates two coincident
entry samples and one continuous entry segment and returns
`COLLISION_REPLAN_REQUIRED`, consistent with the already colliding synthetic
ICQ-5/6 profile. This is zero-authority contract evidence: the observation,
profile, placement, cables, and route remain synthetic and execution-ineligible.
Evidence `E-20261008-ARM-500` now reconstructs ICQ-7 entry evidence and ICQ-6
continuous evidence into one deterministic ICQ-8 receipt. The retained
synthetic chain proves exact zero-difference entry-to-route continuity, both
partition boundaries, and complete ownership of 321 route segments. Its
aggregate disposition is `REJECT` because collision evidence exists in both
the entry and route receipts. That is the expected honest result for the
synthetic installed fixture and grants no authority. ICQ-9 remains blocked on
an ICQ-8 `PASS`; real installed geometry, cable sweeps, and fresh physical
T=1051 feedback remain open.

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
