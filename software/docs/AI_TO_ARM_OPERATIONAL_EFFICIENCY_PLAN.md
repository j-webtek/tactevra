# AI-to-arm operational efficiency optimization plan

- **Document status:** Active plan; implementation in progress through E1
- **Owners:** Shared AI/model, arm/runtime, perception, controller, and
  qualification workstreams
- **Audience:** Contributors optimizing request-to-verified-effect latency
- **Reviewed:** 2026-09-29 against `ModelMotionBatchV2`, ARM-118, and the
  FREEZE-013-bound PC8 performance report
- **Authority:** Normative planning guidance only; it grants no camera,
  controller, movement, contact, deployment, or release authority

## Outcome

Minimize the time from a user's supported request to a **verified correct
physical result** while preserving every identity, freshness, containment,
geometry, dynamics, transport, recovery, and outcome requirement.

The optimization objective is:

```text
maximize verified useful actions / elapsed minute
subject to exact intent, target containment, collision clearance,
tracking limits, single-writer execution, and verified outcomes
```

Raw model tokens per second, controller writes per second, predicted route
duration, or unverified key contacts are diagnostics. They are not successful
work.

This plan coordinates optimization across the whole system. The
[optimized typing execution plan](OPTIMIZED_TYPING_EXECUTION_PLAN.md) remains
the detailed arm-motion architecture; the
[shared AI/arm workplan](../ai/docs/SHARED_AI_ARM_WORKPLAN.md) remains the
cross-workstream readiness authority.

## Boundary and ownership

The model proposes intent and evidence. It never chooses servo bytes, permits,
unbounded speed, retry behavior, or safety policy.

```mermaid
flowchart LR
    A[User request] --> B[Intent and action proposal]
    C[Fresh camera evidence] --> D[Scene and target estimate]
    B --> E[ModelMotionBatchV2]
    D --> E
    E --> F[Static batch admission]
    F --> G[Ordered action queue]
    G --> H[Rolling zero-authority planning]
    H --> I[Fresh dynamic admission]
    I --> J[One-action permit]
    J --> K[Single-writer controller]
    K --> L[Tracking and settling]
    L --> M[Independent effect verification]
    M -->|verified| G
    M -->|failed or uncertain| N[Stop and preserve evidence]
```

| Owner | Optimizes | Must not own |
| --- | --- | --- |
| AI/model | Intent accuracy, structured emission, model warm-up, bounded inference latency | Servo fields, motion limits, permits, retries |
| Perception | Capture, scene health, localization, uncertainty, drift detection | Motion authority or unbounded confidence override |
| Runtime | Admission, transforms, IK, collision, scheduling, journaling | Invented measurements or silent policy relaxation |
| Controller | Exact encoding, sole-writer transport, correlated feedback | Semantic interpretation or autonomous retry |
| Verifier | Independent device-effect observation | Treating servo feedback as proof of a keypress |
| Qualification | Evidence thresholds, promotion, regression, release | Editing results to satisfy a target |

## Timing vocabulary

Every benchmark and production trace should use the same monotonic milestones:

| Milestone | Meaning |
| --- | --- |
| `T0_REQUEST_RECEIVED` | Complete supported user request received |
| `T1_INTENT_SEALED` | Ordered semantic action plan is canonical and hashed |
| `T2_PERCEPTION_SEALED` | Scene, target, uncertainty, and source image identities are sealed |
| `T3_BATCH_EMITTED` | Complete `ModelMotionBatchV2` bytes are available |
| `T4_BATCH_ADMITTED` | Immutable batch and configuration facts pass static admission |
| `T5_FIRST_PLAN_READY` | First candidate route is fully screened but has zero authority |
| `T6_FIRST_PERMIT_GRANTED` | Fresh state and exact one-action envelope have a single-use permit |
| `T7_FIRST_WRITE` | Sole writer submits the first correlated controller bytes |
| `T8_FIRST_SETTLED` | Arm feedback meets the admitted arrival and dwell criteria |
| `T9_FIRST_EFFECT_VERIFIED` | Independent observer verifies the requested device effect |
| `T10_REQUEST_COMPLETE` | Every ordered action has a verified result |

Required derived metrics are first-action latency (`T9-T0`), software
decision latency (`T6-T0` excluding model time when reported separately),
inter-action verified latency, total verified task latency, and verified useful
actions per minute. Report p50, p95, and p99 only with sufficient samples.

## Current evidence baseline

The current canonical PC8 report is
`software/ai/eval/typing_performance_report_v1.json` with file SHA-256
`024c5111810e9d0a5b67ea78389d2c7e5d19041ba31960fb3fcb495be98f74f6`
and embedded content SHA-256
`a43a25056cff135d8756fbe7b15160b7a9ad0b49964e21e0c16a6c5eb2df291c`.
It is `SYNTHETIC_OFFLINE_ONLY` and contains no physical speed claim.

| Stage or result | Retained observation | Meaning |
| --- | ---: | --- |
| Total planning-path CPU | 2.766 s p50 / 9.094 s p95 / 10.000 s p99 | Host computation, not motion |
| IK CPU | 2.641 s p50 / 8.953 s p95 / 9.859 s p99 | Dominant measured software bottleneck |
| Static validation | 31.25 ms p50 / 46.875 ms p95 | Safety validation is not the main delay |
| Collision intake | 78.125 ms p50 / 109.375 ms p95 | Evidence preparation, not installed collision execution |
| Predicted direct `ROBOT` route | 11.657 s | Synthetic trajectory estimate |
| Predicted park-return `ROBOT` route | 12.808 s | Synthetic comparison baseline |
| Direct-route reduction | 8.98% | Packaging improvement without gate removal |
| Gemma scene assessment | 1.692 s historical median | Ten positive setup photos; not a final-camera benchmark |
| Independent key-effect verification | Unmeasured | Required before physical throughput claims |

The direct five-action route corresponds to a diagnostic 25.7 actions/minute
before model, planning, dispatch, feedback, and verification time. Combining
the retained p95 planning value with the route prediction gives a conservative
synthetic 14.5 actions/minute for that short request. Neither number is a
qualified physical typing rate.

PC12 camera fault-campaign and PC15 installed-geometry rehearsal timing are
commissioning measurements. They must remain outside the per-action production
critical path.

## Non-negotiable invariants

No optimization may change these rules:

1. Model output is a proposal, never a controller command or permit.
2. Canonical decoding, exact ordering, provenance, and content hashes remain
   mandatory.
3. Camera, calibration, target catalog, tool, robot, controller, dynamics, and
   policy identities bind one coherent configuration epoch.
4. Target uncertainty plus all error budgets must remain inside the applicable
   safe region.
5. Every physical action begins from fresh authenticated arm state.
6. Exact planned motion must pass joint, dynamics, installed-geometry, tool,
   cable, and continuous-sweep policy.
7. The physical commit horizon remains one action until a separately qualified
   micro-batch mode exists.
8. Exactly one process owns controller writes and every write is correlation
   bound.
9. Feedback and settling are required before contact or successor motion.
10. Servo feedback does not prove the intended device effect.
11. Possible contact or ambiguous outcome is never retried automatically.
12. Timing telemetry cannot alter an admission decision.
13. A cache stores hints or immutable facts, never authority.
14. Faster behavior must reproduce the same decisions and safety evidence as
    its reference path.

## Critical-path strategy

### Work once per installation or configuration epoch

Preload and retain immutable, versioned state:

- robot model, joint topology, and solver structure;
- target catalog and keyboard layout;
- measured transforms and tool profile;
- installed static collision geometry and acceleration structures;
- qualified dynamics and controller profiles;
- policy, registry, and schema validators; and
- model weights, tokenizers, fixed prompt prefixes, and camera profiles.

Any relevant identity change invalidates dependent products before use.

### Work once per request batch

- Decode canonical AI bytes exactly once.
- Bind request, model, image, calibration, device, tool, target, and policy
  identities.
- Validate supported actions, exact order, uncertainty containment, and resource
  ceilings for the complete batch.
- Transform all admitted named targets into the commissioned planning frame.
- Create the immutable ordered queue and durable request header.
- Prepare zero-authority route candidates and cache lookups.

### Work for every action

- Read fresh arm and controller state.
- Confirm the configuration and device-pose epochs have not changed.
- Rebind or discard the candidate route using current state.
- Revalidate exact collision, dynamics, deadline, and permit policy.
- Durably record the pre-dispatch boundary.
- Dispatch once, observe feedback, verify settling, retract, and independently
  verify the effect.

Static facts must not be recomputed per action merely for convenience. Dynamic
facts must not be cached merely for speed.

## Parallelism and overlap map

Allowed concurrency reduces waiting without broadening authority:

| May overlap | Condition |
| --- | --- |
| Intent interpretation and scene assessment | Both bind the same request/session identities before fusion |
| Scene-quality assessment and precision localization | Both consume the exact retained image bytes |
| Static batch checks across proposals | Final ordered disposition remains deterministic |
| Next-action zero-authority planning and current-action travel | Preview cannot dispatch or create a permit |
| Durable noncritical evidence formatting and later computation | Minimum pre-dispatch and outcome records are already durable |
| General scene-health monitoring and controller feedback | Monitoring cannot replace correlated feedback or effect verification |

The following may not overlap in a way that advances authority:

- two physical actions;
- lateral travel before verified retract clearance;
- next contact before the prior effect is verified in the initial mode;
- current-state admission using a predicted future state;
- automatic retry while contact or outcome is uncertain; or
- two controller writers.

## Optimization workstreams

### O1 — Measurement and decision-neutral observability

Create one bounded `OperationalLatencyTraceV1` spanning `T0` through `T10`.
Each record should contain monotonic timestamps, stage outcome, cold/warm state,
cache disposition, action identity, relevant hashes, resource counts, and zero
credentials. Instrumentation must not change canonical decisions or hashes.

Separate CPU time, wall time, predicted motion time, measured motion time, and
verification time. Never add unlike durations into a physical-speed claim.

### O2 — AI intent and structured emission

- Keep supported deterministic parsing available as the reference path.
- Keep selected models resident rather than cold-loading per request.
- Cache tokenization and fixed prompt prefixes, not user decisions.
- Use grammar- or schema-constrained generation to eliminate repair passes.
- Emit the smallest complete `ModelMotionBatchV2`; do not transmit hidden
  reasoning or duplicate scene data.
- Validate incrementally while receiving bytes, then perform one canonical
  final decode.
- Measure cold load, warm inference, schema rejection, abstention, and emission
  separately.

The AI may become faster by choosing a smaller qualified model or deterministic
path. It may not become faster by omitting provenance, uncertainty, or
unsupported-action rejection.

### O3 — Camera, scene, and localization

- Maintain a persistent qualified camera session.
- Capture one image set per required observation epoch and share the exact
  bytes across scene and precision consumers.
- Crop deterministic device regions before expensive processing.
- Run scene health and localization concurrently when their evidence contracts
  allow it.
- Use a fast fiducial/device-drift sentinel between actions.
- Invoke full general scene assessment on initial admission, detected drift,
  obstruction, degraded image quality, periodic policy checkpoints, or
  ambiguous verification—not automatically for every key.
- Keep target uncertainty and abstention policy unchanged.

### O4 — Ingress and registry admission

- Parse and canonicalize the batch once.
- Build immutable in-memory indexes for trusted model, calibration, target,
  tool, device, and policy identities.
- Validate batch-wide facts once and action-specific facts only where needed.
- Avoid repeated file reads and repeated serialization inside the hot path.
- Preserve exact duplicate-member, nonfinite-number, depth, count, size, order,
  and authority-injection rejection.

The retained 46.875 ms static-validation p95 is already acceptable; optimize
this workstream only after measurement confirms it has become material.

### O5 — IK and route generation

This is the first software optimization priority.

- Keep the parsed URDF, transforms, joint bounds, solver workspace, and
  kinematic terms warm in one immutable planner context.
- Build a qualified endpoint atlas for named keyboard targets and standard
  hover/retract states.
- Connect the existing directional transition cache to the actual planning
  path; current PC8 warm-cache labels do not measure real cache reuse.
- Seed every solve from the previous verified joint state or the exact
  identity-bound directional transition hint.
- Measure iterations and convergence reason per screening sample.
- Evaluate an analytical or hybrid RoArm-M3 IK candidate generator, with the
  current numerical solver and all existing checks retained as validation.
- Reuse mathematical intermediates within one exact route rather than parsing
  models or rebuilding matrices for every sample.
- Profile compiled/vectorized numerical kernels only after algorithmic reuse is
  exhausted.
- Preserve the exact Cartesian screening path and joint/dynamics/collision
  dispositions during equivalence testing.

No cached endpoint, analytical candidate, or compiled result is executable
until rebound to fresh state and re-screened under the current epoch.

### O6 — Collision and cable screening

- Prebuild immutable broad-phase acceleration structures for fixed geometry.
- Separate static environment pairs from moving-link, tool, cable, and device
  pairs.
- Use conservative broad-phase rejection before exact narrow-phase checks.
- Cache only identity-bound geometry products and pair exclusions justified by
  the installed model.
- Keep continuous adjacent-sample sweep coverage; do not increase sample step
  merely to reduce CPU time.
- Recompute or invalidate on tool, cable routing, keyboard, camera support,
  robot-base, or configuration-epoch changes.

### O7 — Rolling horizon and scheduling

- Admit immutable batch facts once.
- Keep exactly one current action and at most one zero-authority preview.
- Plan action `N+1` while action `N` travels or is observed.
- At transition, compare fresh achieved state with the preview start envelope.
- Reuse only if start tolerance, epoch, target evidence, collision, dynamics,
  and deadlines still pass; otherwise discard and replan.
- Prefer screened retract-to-next-hover motion rather than global park returns.
- Keep park for startup, shutdown, recovery, and route-unavailable cases.

### O8 — Controller transport and feedback

- Maintain one qualified persistent serial session during a task.
- Keep one writable owner and an explicit bounded queue.
- Encode only a sealed, permitted trajectory envelope.
- Correlate request, action, envelope, submitted bytes, acknowledgement, and
  feedback in one receipt.
- Avoid controller startup, firmware restart, port rediscovery, or full
  configuration replay between keys.
- Use bounded reads and event-driven feedback rather than arbitrary sleeps.
- Preallocate buffers and reuse parser state where safe.
- Never resend after an ambiguous submission or outcome.

### O9 — Physical motion shaping

- Begin with the lowest physically qualified speed class.
- Tune transit, local transition, alignment, approach, contact, retract, and
  recovery separately.
- Reduce unnecessary hover height only after measured full-body, tool, cable,
  and keyboard clearance allows it.
- Reduce settle and contact dwell only from retained tracking, debounce, and
  exact-outcome evidence.
- Blend only non-contact segments whose combined swept volume and terminal
  conditions are screened.
- Select among prequalified parameter sets using route length, margin, current
  tracking residual, recent settling, controller health, and target type.
- Demote or stop on residual, clearance, feedback, transport, or verification
  degradation.

### O10 — Independent effect verification

- Prefer the lowest-latency observer that is independent of the command path.
- For keyboards, evaluate exact input-event observation or a bounded text-field
  observer before relying on general vision.
- For visual verification, use a small expected-change region and deterministic
  before/after comparison before escalating to OCR or a general vision model.
- Distinguish no effect, wrong effect, duplicate effect, reordered effect, and
  ambiguous effect.
- Keep per-action verification for the first physical release.
- Consider small verification windows only under a new schema and separate
  held-out proof that omissions, duplicates, and order changes remain
  unambiguous.

### O11 — Journaling, evidence, and recovery

- Durably persist the minimum exact pre-dispatch record before writing.
- Move formatting, compression, and noncritical export work off the critical
  path after durability is established.
- Batch filesystem synchronization only where crash analysis proves equivalent
  safety.
- Resume after restart only from a journal state that proves no uncertain
  contact; otherwise stop at `OUTCOME_UNCERTAIN`.
- Retain enough data to reproduce decisions without retaining credentials,
  absolute private paths, or unnecessary raw media.

## Provisional software latency goals

These are engineering targets for later qualification, not current claims or
admission thresholds:

| Component | Cold target | Warm target | Required guard |
| --- | ---: | ---: | --- |
| Structured AI intent output | Report separately | ≤250 ms p95 for supported narrow requests | Exact-plan score and abstention do not regress |
| Scene plus localization | Report separately | ≤500 ms p95 when full assessment is unnecessary | Same image identity and uncertainty disposition |
| Batch decode and static admission | ≤100 ms p95 | ≤50 ms p95 | Byte-identical accepted/rejected decisions |
| First screened route | ≤1,000 ms p95 | ≤250 ms p95 | Same path, schedule, margins, and blockers |
| Per-action dynamic revalidation | ≤100 ms p95 | ≤50 ms p95 | Fresh state and exact epoch required |
| Encode, journal, and dispatch preparation | ≤100 ms p95 | ≤50 ms p95 | Durable intent and one-use permit preserved |
| Independent effect verification | Device-specific | ≤250 ms p95 when exact lightweight observation exists | False acceptance remains below qualified bound |

No physical travel, settling, contact, or verified-throughput target should be
frozen until the final camera, installed geometry, tool, controller, keyboard,
and observer have measured evidence.

## Implementation stages

Only an explicit implementation checkpoint below establishes progress. A stage
is not complete merely because this plan exists.

### E0 — Freeze the baseline and trace contract

Deliver:

- current-report identity correction;
- `OperationalLatencyTraceV1` design;
- exact milestone and percentile rules;
- benchmark environment identity; and
- retained cold/warm reference runs.

Gate: instrumentation reproduces all reference decisions and hashes and adds no
camera, transport, command, or physical authority.

Implementation checkpoint (2026-09-29): E0 is complete. The strict
`rocell.operational_latency_trace.v1` contract now freezes the T0-T10 milestone
catalog, requires an exact ordered prefix for blocked traces, derives all stage
durations, binds request/session/batch/plan/configuration/controller/result
correlations, and rejects rehashed attempts to change decisions or grant timing,
performance, or physical authority. Its schema and mutation suite are included in
the governed offline checks.

The retained host reference is
`software/ai/eval/operational_latency_reference_v1.json`, report SHA-256
`0c9e960bd00a8336ff32d7b099be7e21835e9c559e5a47894805a5b1157d9416`.
It binds clean source commit `c633c04fb17d42de5d7466319307db4e536b1120`,
CPython 3.10.10 on Windows/AMD64, a 100 ns performance-counter resolution, and
20 cold plus 20 warm traces. Here `COLD` means fresh logical input and registry
objects in an already-running Python process; `WARM` means reuse of those immutable
objects. Inputs are presealed synthetic fixtures, so T0-T3 do not measure language
or vision inference.

The real arm-side planning reference stops honestly at T5: no IK solve, permit
request, controller open, transport open, command, write, or movement occurred.
Cold batch-admission latency was 33.987 ms p50 / 35.578 ms p95 and warm was
32.875 ms p50 / 33.545 ms p95. Cold admission-to-first-plan latency was
0.530 ms p50 / 0.666 ms p95 and warm was 0.517 ms p50 / 0.619 ms p95. P99 is
intentionally unavailable because exact nearest-rank rules require at least 100
observations. These values are reference observations, never admission thresholds
or physical-speed claims.

### E1 — Remove avoidable software setup from the hot path

Deliver:

- persistent model/camera/planner/controller-service lifecycle designs;
- batch-static versus action-dynamic validation split;
- in-memory immutable registry indexes;
- model, tokenizer, URDF, solver, and geometry warm-up benchmarks; and
- restart and invalidation tests.

Gate: cold and warm paths remain semantically identical and stale state cannot
survive an epoch change.

Implementation checkpoint (2026-09-29): E1 has begun with an immutable
`SimulationContextValidationLeaseV1`. Profiling showed that trusted batch
admission was dominated by reloading and hashing the complete locked simulation
context for every request. Lease issuance still performs that full source
validation once. Warm admission then requires the same in-memory context object,
content-derived context epoch, service instance, and generation, and it rechecks
the lease hash and zero-authority fields. Any epoch advance, service restart,
generation invalidation, context replacement, or lease mutation fails closed.

The retained clean-source comparison is
`software/ai/eval/context_validation_lease_benchmark_v1.json`, file SHA-256
`9ecab492ee448327f16a7d234aedf041462377f5a7fca1f18deb5c278fc917de`
and embedded report SHA-256
`859de0b38638c5f6e03dc3e78404c3776d713da6699862cb9597ebd86d915b1a`.
It binds source commit `95d4385f6c68f07daa49dcb5d88c5221e5535a0c` and contains 20 full-source plus
20 leased admissions. Every accepted ingress result had the same SHA-256. Full
source revalidation measured 37.185 ms p50 / 42.842 ms p95; leased validation
measured 0.115 ms p50 / 0.132 ms p95, reductions of 37.071 ms and 42.710 ms.
P99 is intentionally unavailable with fewer than 100 samples.

The retained invalidation matrix blocked changed context epoch, restarted
service identity, changed generation, replaced context object, and mutated lease
content. Timing never participates in admission, and the report contains zero
controller commands, transport access, writes, movement, or physical authority.
This closes only the retained context-validation benchmark slice of E1.
The subsequent runtime-owned `SimulationContextLifecycleV1` closes the matching
simulation-context lifecycle slice. It loads and validates the active context,
owns the service identity and monotonically advancing generation, issues the
lease, and holds one lifecycle lock across complete trusted-registry admission.
Source reload cannot interleave with an admitted batch. A successful reload
atomically installs a new context object and generation; a failed reload leaves
the previous active binding intact. Explicit invalidation and service restart
revoke the old lifecycle before a successor can be used. Callers cannot combine
lifecycle-managed admission with manually supplied lease identities.

Governed fault tests cover same-output admission, reload, failed reload,
invalidation, restart, stale-context rejection, manual-identity rejection, and
concurrent invalidation. This adds no filesystem watcher, controller process,
hardware access, or execution authority. Model/camera/planner/controller
lifecycle design beyond this simulation-context boundary, broader
static/dynamic validation separation, component warm-up campaigns, and their
restart matrices remain open.

The next E1 increment adds `PreparedTypingPlannerV1` beneath that lifecycle.
It parses and validates the exact hash-pinned URDF once per context generation,
then reuses only that immutable model and topology through trusted ingress, the
typing IK screen, and collision-evidence intake. The preparation is bound to
the context object, epoch, service identity, generation, model hash, byte count,
and a canonical preparation hash. Reload or restart makes it stale; mutation
and use outside lifecycle-managed scope fail closed.

The numerical solver itself is deliberately reconstructed for each request
from the current calibration, tool transform, joint bounds, policy, and start
seed. IK solves, trajectory continuity, installed collision evidence, and
dynamic admission remain uncached. Full-source and prepared end-to-end shadow
receipts are exactly identical in governed tests and in retained ARM-118 host
evidence. Across 20 runs per path, the full-source pipeline measured 1.667267 s
p50 / 1.705646 s p95 and the prepared pipeline measured 1.590753 s p50 /
1.604661 s p95. That is a measured 76.514 ms p50 / 100.985 ms p95 reduction,
with the separate cold preparation cost measured at 1.190 ms. These host
results are not physical-speed authority and are not admission thresholds.
They confirm that reuse helps modestly while numerical IK—not URDF parsing—
remains the dominant software cost.

### E2 — Accelerate IK and collision preparation

**Status:** in progress through ARM-132 shadow-service reuse qualification.

ARM-119 adds an opt-in, bounded `TypingIkEffortRecorderV1` side channel. It
records attempt and iteration counts only after each deterministic solve. The
canonical IK report, stage hashes, terminal receipt, admission rules, and
authority fields do not consume the telemetry and remain byte-identical with
or without it.

An initial non-retained `ROBOT` diagnostic observed 57 waypoints, 228 attempts,
and 660 iterations. The first/carry-forward seed converged at all 57 waypoints,
but the reference solver selected attempt zero only 4 times because it evaluates
every configured candidate and selects the lowest residual. This explicitly
rules out first-convergence early exit as an equivalence-preserving
optimization. The next retained campaign must measure representative sequences,
iteration distributions, selected-attempt behavior, and exact reusable input
keys before any warm-start or endpoint cache is proposed.

ARM-120 supplies that retained campaign across five representative sequences:
home-row transition, `ROBOT`, repeat/number/punctuation, alphabetic extremes,
and number/space/enter. Its 186 waypoint observations contained 744 attempts
and 2,393 iterations; selected attempts accounted for 872 iterations. All 186
first attempts converged, but only 15 were selected, confirming that early exit
is not equivalent. Content-addressed keys bound the active solver source,
build, model, calibration, target, incoming seed, joint bounds, gripper,
options, and algorithm. The campaign found 48 unique keys, 138 repeat
observations across 35 reusable identities, and a maximum recurrence of 11.
This justifies designing an exact-result cache experiment, but authorizes no
cache, decision change, controller operation, or physical execution.

ARM-121 implements that experiment as an opt-in, in-memory cache behind the
complete reference solver. A cache identity is the ARM-120 exact solver-input
hash, including the active solver source. Hits re-hash and integrity-check the
stored `IkResult`; misses always run the complete solver. The cache is bounded,
never evicts a result to make room, and stops storing when full. It is bound to
one exact simulation-context object, epoch, service instance, and lifecycle
generation; invalidation, reload, restart, crossed context, unmanaged use, or
integrity mismatch rejects closed. Governed integration tests prove that cold,
warm, capacity-limited, and disabled paths emit identical canonical shadow
receipts. Cache counters remain a zero-authority diagnostic side channel and
are never admission inputs. This establishes safe experimental mechanics, not
measured speed benefit, deployment qualification, or physical authority.

ARM-122 supplies the retained host evidence. Ten interleaved samples per path
compared the same prepared `ROBOT` pipeline with caching disabled, cold, fully
warm, and limited to one entry. Disabled p50/p95 measured 2.919988 s / 2.946670
s; warm p50/p95 measured 0.301630 s / 0.306846 s, reductions of 2.618358 s and
2.639824 s respectively. The cold path measured 2.312926 s p50 because 110 of
570 lookups reused exact inputs within the same sequences. The one-entry path
measured 2.778198 s p50 while recording 550 capacity skips. All 40 canonical
receipts and stage-hash sets were identical. Explicit invalidation, context
reload, service restart, crossed context, result corruption, and unmanaged use
all blocked. These are host/offline results, not physical throughput evidence
or permission to bypass any dynamic check.

ARM-123 converts the opt-in cache arguments into one explicit zero-authority
owner for the offline typing runtime. The owner alone pairs a context lifecycle,
prepared planner, and exact-result cache; callers cannot override any of those
three resources. It holds one lock across each shadow admission and owns reload,
restart, and explicit invalidation. A successful reload or restart retires the
old cache before the replacement becomes usable. A preparation failure leaves
the owner unready and fail-closed. Reloaded and restarted generations begin
with an empty cache, so no result crosses a context epoch or service instance.
Its hashed diagnostic snapshot exposes run/failure, generation-transition,
retirement, and nested cache counters, while remaining excluded from admission
and permanently reporting zero controller and physical authority.

ARM-124 retains the clean-commit owner campaign. Normal cold/warm reuse,
successful reload retirement, successful restart retirement, explicit
invalidation, forced reload-preparation failure, and forced
restart-preparation failure all passed their exact expected outcomes. Every
successful execution emitted the same terminal receipt. Every transition that
could not safely replace resources retired the old cache and left execution
blocked; neither failure path silently reused stale resources. The campaign
and nested owner/cache diagnostics remained outside admission with zero
controller, transport, hardware-write, movement, and physical authority.

ARM-125 wires that owner into a bounded, in-process shadow service without
adding an executor or physical capability. Submission freezes a content hash
over the canonical model payload, intent-plan identity, context epoch, service
instance, and lifecycle generation. A bounded FIFO and lifetime request limit
prevent unbounded work; request IDs cannot be reused; automatic retry is
forbidden. Cancellation is allowed only while queued and never runs the owner.
Reload and restart preserve queued evidence but cause the old generation to be
rejected before admission. Once admitted, the service lock holds the complete
shadow run, so a concurrent lifecycle transition waits and cannot create a
mixed-generation result. Explicit invalidation accounts for discarded queue
entries. Strictly parsed, hashed terminal receipts and service snapshots expose
only diagnostic counters and retain zero controller, transport, sole-writer,
hardware, and physical authority.

ARM-126 retains the service boundary on clean source commit
`4c2ae9db9e27079c93b26e34330248f2f8537b47`. Its eight cases cover normal FIFO
completion, cancellation before admission, reload-stale and restart-stale
rejection, queue saturation, explicit invalidation, unexpected shadow failure,
and an admitted-request/reload race. Every expected outcome passed. The race
proved the reload remained blocked until the admitted request completed, while
the completed reference and race cases preserved one identical shadow decision
hash. All other bounded or rejected paths performed zero owner runs. The
campaign grants no performance, controller, transport, movement, or physical
authority.

ARM-127 introduces a bounded observer at the canonical IK screen rather than a
cache or alternate solver path. After each accepted semantic phase endpoint,
it records hashes of the exact phase/target/board point, incoming joint state,
solved joint state, and solver input. Per-route aggregation reports repeated
endpoint identities, transition identities, and whether repeated endpoints
were observed with one or multiple solved joint states. Enabling the observer
leaves the complete shadow receipt byte-identical. The report is strictly
parsed, bounded to 4,096 samples, excluded from admission, and marks atlas use
unauthorized. It creates no controller commands or physical authority.

ARM-128 retains the clean-commit representative-corpus atlas. Five routes
preserved byte-identical reference shadow receipts while producing 186 sample
observations, 58 semantic endpoint observations, and 53 transition
observations. The aggregate contains 40 unique endpoint identities and 46
unique transition identities. Seven endpoint identities recur and five
transition identities recur. Every endpoint in this bounded corpus has exactly
one observed solved joint-state hash, so the seven repeated endpoints are
stable reuse candidates and none are observed variable. This narrows the next
experiment to exact endpoint-result reuse, but it does not establish stability
for unobserved incoming states. Both atlas use and warm starts remain
unauthorized, and the retained artifact has zero controller, transport,
hardware-write, movement, or physical authority.

ARM-129 implements a bounded endpoint-result verifier alongside the reference
solver. It does not return cached candidates to planning. Instead, it binds one
candidate map to the active context object, epoch, service instance,
generation, build, model, calibration, joint bounds, fixed gripper, IK options,
algorithm, solver implementation, and solver-source digest. Each repeated
semantic endpoint is integrity-checked and compared with the newly computed
canonical solution. Two `ROBOT` passes retain byte-identical reference receipts
while observing 34 endpoints: 13 stores and 21 matching candidate hits, with
zero conflicts. Tests cover bounded capacity and sample lifetime, corruption,
deliberate solution conflict, altered decision context, reload, restart,
crossed context, invalidation, and unmanaged use. Candidate use for decisions,
admission, and warm starts remains false. This verifies the comparison
mechanics; a clean-commit multi-sequence/fault campaign is still required
before proposing substitution or measuring any speed benefit.

ARM-130 completes that clean-commit qualification. The five representative
routes preserve byte-identical canonical receipts while the shared verifier
records 186 samples, 58 endpoint observations, 40 stores, 18 exact recurrence
matches, and zero conflicts. Capacity remains bounded with the reference
receipt preserved; nine reject-path cases cover sample exhaustion,
invalidation, corruption, deliberate conflict, changed decision context,
reload, restart, crossed context, and unmanaged use. The campaign authorizes no
candidate decision, admission input, warm start, controller action, or physical
movement. The next E2 increment must therefore be a separately gated
candidate-substitution design with complete-solve fallback and its own
equivalence proof, not silent activation of this verifier.

ARM-131 selects and qualifies the safer substitution boundary. It does not use
the 40-key endpoint map as a decision cache because an endpoint identity omits
the incoming joint state. Instead it reuses the existing exact solver-input
cache, whose key binds target, incoming seed, build, model, calibration, bounds,
gripper, IK options, algorithm, implementation, and solver source. Across all
five representative patterns, reference, cold-cache, and warm-cache receipts
and stage hashes were identical. Cold caches recorded 26 hits in 186 lookups;
warm caches recorded 186/186 hits. Aggregate host duration changed from
10.6446605 s reference to 8.8345029 s cold and 1.0399843 s warm. Misses still
require complete solves. Endpoint-only substitution remains unauthorized and
the timing remains offline, non-admissive, and non-physical.

ARM-132 carries exact-input reuse through the bounded shadow-service request
lifecycle. Five mixed requests retain FIFO completion and share one
generation-bound cache: 186 lookups resolve as 48 complete solves and 138 exact
hits. A canceled request performs no owner run or cache lookup. Reload and
restart reject previously queued work as stale, retire the former cache, and
force the first current-generation request through a cold cache. There is no
automatic retry and timing remains non-admissive. This closes the shadow
service integration prerequisite; it does not connect an executor or sole
writer and therefore creates no physical authority.

Deliver:

- endpoint-atlas and warm-start experiments;
- solver iteration telemetry;
- analytical/hybrid feasibility study;
- fixed-geometry broad-phase preparation; and
- before/after PC8-equivalent campaigns.

Gate: every accepted and rejected route, joint result, schedule hash, blocker,
margin, and resource ceiling matches the reference path unless a separately
reviewed contract revision explicitly explains the change.

### E3 — Qualify rolling-horizon shadow execution

Deliver:

- one-action preview overlap;
- fresh-state rebind and discard behavior;
- cache and preview invalidation matrix;
- cancellation, restart, drift, and ambiguous-outcome faults; and
- latency traces showing useful overlap.

Gate: previews never create authority; all forced invalidations discard; no
possibly completed action is replayed.

### E4 — Complete controller scheduling and verification adapters

Deliver:

- persistent sole-writer service;
- sealed-envelope encoder and correlated receipts;
- measured dispatch/feedback/settling timing;
- keyboard effect-verification candidates; and
- exact no-retry recovery behavior.

Gate: unambiguous actions dispatch exactly once; ambiguous submission or effect
stops without retry.

### E5 — Commission final-camera and installed-workcell evidence

Deliver:

- final-camera timing and localization benchmark;
- measured configuration epoch;
- installed collision and cable profile;
- device drift sentinel; and
- held-out non-contact localization-to-hover trials.

Gate: target uncertainty fits the applicable safe region and one slow
non-contact hover passes independent measurement.

### E6 — Physical speed ladder

Progress separately through non-contact hover, repeated hover, one verified
key, and short verified strings. Change one parameter family at a time.

Gate: each promotion improves or preserves verified useful throughput while
meeting tracking, clearance, exact outcome, stop, fault, and recovery bounds.

### E7 — Operational performance release

Deliver:

- frozen supported hardware/software/model profiles;
- held-out mission scorecard;
- p50/p95/p99 request-to-effect latency;
- verified useful actions/minute;
- exact outcome, abstention, tracking, fault, and recovery metrics;
- reproducible benchmark commands; and
- CI regression thresholds for software-only portions.

Gate: shared workplan S7 closes and the release report states all unsupported
devices, actions, configurations, and failure modes.

## Required benchmark matrix

At minimum, every optimization campaign should cover:

- `robot`, `book`, `qaz`, and `plm`;
- repeated same-key and alternating distant-key patterns;
- numbers, punctuation, space, and Enter;
- all 46 currently named keyboard targets;
- shortest, median, and longest supported batches;
- cold start, warm process, cache hit, cache miss, and forced invalidation;
- shifted device epoch, stale observation, wrong hash, wrong order, unsupported
  action, excessive uncertainty, and malformed input;
- planner failure, collision loss, slow settling, dropped feedback, transport
  timeout, cancellation, restart, and ambiguous effect; and
- independent verification success, wrong effect, duplicate, omission, and
  uncertainty.

Each result must name the exact commit, host, runtime, model, camera, workcell,
controller, device, tool, configuration epoch, policy, and evidence class that
support it.

## Optimization change protocol

Every implementation change should record:

1. the exact critical-path stage being changed;
2. the retained before/after benchmark identities;
3. p50/p95/p99 and resource deltas;
4. accepted/rejected decision equivalence;
5. path, schedule, blocker, margin, and receipt equivalence where applicable;
6. fault and invalidation results;
7. authority, hardware-access, and movement counts;
8. new risks and rollback method; and
9. whether the result is synthetic, host-measured, controller-reported,
   externally measured, or independently verified.

An optimization is rejected if it is faster only because it omits a required
check, changes an unexplained decision, widens a bound without qualification,
uses stale state, hides an ambiguous outcome, or makes evidence nonreproducible.

### Current exact-input reuse status (ARM-133)

The exact-input IK cache is now guarded by a frozen shadow-eligibility profile.
Eligibility requires exact active lifecycle, build, model, calibration, evidence,
capacity, fallback, and retry-policy identities. A benign qualification mismatch
selects the complete solver; structurally unsafe settings or stale lifecycle
objects are rejected. Endpoint-only substitution remains prohibited, and the
gate cannot admit motion or access the controller. The retained campaign is
[`typing_ik_reuse_profile_campaign_v1.json`](../ai/eval/typing_ik_reuse_profile_campaign_v1.json).

ARM-134 composes this gate with the FIFO shadow service. The runtime choice is
made once at the service boundary: eligible work receives the exact-input cache;
fallback work receives no cache and runs the same complete solver. Reload and
restart retire eligibility rather than silently requalifying changed state.
The retained [service-composition campaign](../ai/eval/typing_profiled_shadow_service_campaign_v1.json)
proves receipt equivalence and zero cache access on every fallback path.

ARM-135 closes the next software seam by regenerating canonical V2 bytes with
the actual shared AI assembler and submitting them to the profiled service.
The retained [`R,O,B,O,T` campaign](../ai/eval/actual_emitter_profiled_service_campaign_v1.json)
observed a 57/57-hit warm request after one cold population, while calibration
and evidence mismatch, reload, restart, and cancellation preserved their safe
fallback semantics. The measured durations are single-host diagnostics and are
not admission thresholds or physical typing-speed evidence.

ARM-136 exercises that same seam as a mixed sustained FIFO queue rather than a
single repeated word. Five representative actual-emitter batches cover home-row
travel, `robot`, repetition plus number and punctuation, alphabetic extremes,
and number/Space/Enter. The retained cold round performed 48 complete solves
among 186 lookups because identical solver inputs were already reusable within
and across requests; the immediate warm round hit 186/186. Observed p50/p95
changed from 0.2685515/1.3913187 seconds cold to 0.1982934/0.2997009 seconds
warm. This is a one-host, five-sample synthetic integration diagnostic. It is
not a latency threshold, physical-rate claim, or permission to skip checks.
The retained artifact is
[`actual_emitter_mixed_queue_campaign_v1.json`](../ai/eval/actual_emitter_mixed_queue_campaign_v1.json).

ARM-137 repeats the mixed queue through 20 isolated cold/prewarmed lifecycle
pairs, producing 100 measured samples per lane. Exact cold/warm shadow receipts
matched for every request, each replacement began cold, every measured warm
round hit the exact-input cache completely, and all services were retired after
measurement. Host p50/p95/p99 were 0.2736679/1.4014767/1.4241501 seconds cold
and 0.1959784/0.3044458/0.3157095 seconds warm, with zero capacity skips. The
campaign therefore supports keeping a qualified immutable service warm, while
also showing that lifecycle replacement must expect cold-tail cost. These
measurements remain diagnostic and cannot become admission limits until the
final deployment host and physical execution path are measured. Retained
evidence is
[`actual_emitter_stability_campaign_v1.json`](../ai/eval/actual_emitter_stability_campaign_v1.json).

ARM-138 tests whether the fast path stays fail-closed under bounded operational
disturbances. The service drains its full eight-request queue FIFO, rejects the
ninth request, handles three pre-admission cancellations without cache work,
and rejects malformed identity, forbidden owner input, and reused request IDs
before planning. Reload and restart reject already queued work as stale, retire
exact reuse, and use the complete solver without retry for new work. Fast reuse
returns only after a separately requalified replacement, whose measured output
matches the original reference receipt exactly. The retained
[`actual_emitter_disturbance_campaign_v1.json`](../ai/eval/actual_emitter_disturbance_campaign_v1.json)
contains seven passing cases and no controller or physical authority.

ARM-139 implements the operating policy implied by ARM-138. The new supervisor
publishes three mutually exclusive states: `WARM`, `FULL_SOLVE_ONLY`, and
`REQUALIFICATION_REQUIRED`. Only `WARM` exposes exact reuse. Known startup
profile mismatch can safely plan through the complete solver. Reload/restart
blocks new work until the caller explicitly accepts full-solve-only operation or
constructs a separately qualified replacement; neither path retries stale work.
The retained
[`typing_runtime_supervisor_campaign_v1.json`](../ai/eval/typing_runtime_supervisor_campaign_v1.json)
shows exact reference equivalence across fallback and replacement while keeping
all execution, transport, and physical authority absent.

## Completion definition

This plan is complete only when the supported AI path can produce an exact
ordered proposal, the arm runtime can admit and plan it within frozen latency
bounds, the controller can execute it under measured motion limits, and an
independent observer can verify the complete outcome at a published sustainable
rate.

The final score is verified useful work per elapsed minute. Safety checks stay
in place; efficiency comes from avoiding duplicated static work, warming
immutable services, reusing qualified planning hints, overlapping
zero-authority computation, shortening screened motion, and choosing the
lowest-latency independent verifier that proves the effect.

## Related documents

- [Typing performance readiness report](TYPING_PERFORMANCE_READINESS_REPORT_V1.md)
- [Optimized typing execution plan](OPTIMIZED_TYPING_EXECUTION_PLAN.md)
- [Pre-camera arm integration completion plan](PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md)
- [Model-command runtime implementation plan](../ai/docs/MODEL_COMMAND_RUNTIME_IMPLEMENTATION_PLAN.md)
- [Shared AI/arm workplan](../ai/docs/SHARED_AI_ARM_WORKPLAN.md)
- [Project status](../../PROJECT_STATUS.md)
