# Pre-camera arm integration completion plan

- **Document status:** Active implementation plan; no hardware authority
- **Owners:** Arm/runtime lane, with shared AI/arm contract review
- **Audience:** Runtime, planning, controller, test, and AI-integration contributors
- **Reviewed:** 2026-09-29 against the PC10 closure and ARM-100 through
  ARM-103 camera-arrival consumer boundaries
- **Authority:** Normative for pre-camera implementation order and evidence;
  explanatory only for later physical qualification

## Purpose

Complete the valuable arm-side integration work that does not require the final
camera, measured keyboard localization, or new physical movement. The result
should accept a strictly admitted AI motion batch, preserve its intended order,
produce a smooth and dynamically bounded arm-owned schedule, rehearse safe
one-action execution, and explain every acceptance or rejection through durable
evidence.

This plan operationalizes T2 through T4 of the
[optimized typing execution plan](OPTIMIZED_TYPING_EXECUTION_PLAN.md). It does
not replace the [shared AI/arm workplan](../ai/docs/SHARED_AI_ARM_WORKPLAN.md),
which remains the cross-workstream status authority.

## Starting point

The repository already provides:

- strict, hash-bound `ModelMotionBatchV2` admission;
- ordered `TypingExecutionPlanV1` compilation, including repeated targets;
- Cartesian quintic shaping and bounded screening samples;
- deterministic IK, joint-bound, margin, Jacobian-rank, and continuity checks;
- a collision-evidence intake that names the installed evidence it still needs;
- controller encoding previews, one-action permit and lifecycle rehearsals, and
  durable no-replay receipts; and
- zero-write controller contract tests.

PC0 through PC10 are complete. ARM-100 through ARM-103 additionally provide a
hash-bound 15-slot arrival preflight, consumer handoff, exact validation receipt
contract, and typed offline receipt emitters. The remaining pre-camera work is
operational composition: make those tools runnable as one zero-authority
workflow, rehearse failures, standardize operator-facing wrappers and session
state, exercise geometry/cable intake, replay immutable captures, expose timing,
and prove compatibility with actual AI-produced batches.

## Required end state

At the pre-camera completion gate, the repository must deterministically take a
fixture such as `type robot` through:

```text
canonical AI bytes
  -> strict admission
  -> ordered typing plan
  -> Cartesian trajectory
  -> exact-sample IK
  -> joint-space time scaling
  -> collision-evidence decision
  -> rolling-horizon preview
  -> one-action execution envelope
  -> exact zero-write controller encoding
  -> correlated lifecycle receipt
```

For the current unmeasured workcell, the normal final result is an exact,
machine-readable blocker such as `MEASURED_INSTALLED_PROFILE_REQUIRED`, not a
fabricated pass. Synthetic fixtures may exercise later stages only when every
artifact remains explicitly labeled `SYNTHETIC_OFFLINE` and grants no physical
authority.

## Operating rules

1. The AI proposes ordered task intent and target evidence; the arm owns IK,
   dynamics, collision policy, timing, encoding, permits, and retry policy.
2. The commit horizon is one action. Preview and cache artifacts have zero
   authority.
3. No test may silently replace measured calibration, geometry, feedback, or
   camera evidence with a nominal value.
4. Repeated targets remain repeated actions; no optimization may reorder or
   deduplicate user intent.
5. An ambiguous dispatch or possible contact is terminal and never
   automatically retried.
6. Cache hits may reduce computation only. They may not bypass fresh-state,
   IK, collision, dynamics, or permit checks.
7. Simulation timing is not physical typing speed. Controller feedback is not
   proof that the intended key appeared.
8. Every artifact is canonical, content-addressed, versioned, resource-bounded,
   and traceable to its inputs.
9. This plan authorizes no controller startup, transport access, command write,
   torque change, movement, or firmware installation.

## Delivery sequence

Work proceeds in the order below. A stage may begin in a feature branch before
the prior stage merges, but it cannot be marked complete until all dependencies
and its evidence gate pass.

| ID | Deliverable | Depends on | Camera needed | Physical I/O | Initial status |
| --- | --- | --- | ---: | ---: | --- |
| PC0 | Freeze fixtures, profiles, metrics, and status vocabulary | Existing T1/T2 artifacts | No | None | COMPLETE |
| PC1 | Joint-space dynamics and deterministic time scaling | PC0, T2B-IK | No | None | COMPLETE |
| PC2 | Golden end-to-end shadow pipeline | PC1, collision intake | No | None | COMPLETE |
| PC3 | Rolling-horizon rebinding and restart safety | PC2 | No | None | COMPLETE |
| PC4 | Typing-specific zero-write controller bridge | PC2, PC3 | No | None | COMPLETE |
| PC5 | Fault injection and property testing | PC1-PC4 | No | None | COMPLETE |
| PC6 | Unified trace journal and deterministic replay | PC2-PC5 | No | None | COMPLETE |
| PC7 | Safe transition cache in shadow mode | PC3, PC6 | No | None | COMPLETE |
| PC8 | Performance benchmark and readiness report | PC1-PC7 | No | None | COMPLETE |
| PC9 | Camera-arrival evidence tooling and dry run | PC6 | No for tooling | None before arrival | COMPLETE |
| PC10 | Pre-camera integration closure | PC0-PC9 | No | None | COMPLETE |
| PC11 | One-command zero-authority commissioning orchestrator | PC9-PC10, ARM-100-103 | No | None | COMPLETE |
| PC12 | Full synthetic arrival and fault campaign | PC11 | No | None | COMPLETE |
| PC13 | Domain-consumer operator wrappers | PC11, ARM-103 | No | None | COMPLETE |
| PC14 | Arrival-session manifest and state machine | PC11-PC13 | No | None | COMPLETE |
| PC15 | Installed-geometry and cable-envelope intake rehearsal | PC13-PC14 | No | None | COMPLETE |
| PC16 | Immutable camera-replay runner | PC11-PC14 | No live camera | None | COMPLETE |
| PC17 | Timing and observability report | PC11-PC16 | No | None | COMPLETE |
| PC18 | Actual AI-output compatibility corpus and gate | PC11, shared AI producer | No | None | COMPLETE |

## PC0 — Freeze the qualification basis

**Completed 2026-09-28:** the retained
`pre_camera_typing_qualification_basis_v1.json` now pins the canonical source
files, fixture sequences, synthetic-only calibration/dynamics/controller
identities, Cartesian policy, stable terminal vocabulary, resource ceilings,
and benchmark requirements. A strict bounded loader rejects duplicate JSON
members, authority promotion, reordered fixtures, crossed identity hashes,
unsafe paths, source drift, non-finite dynamics, and physical claims. Ten
focused tests and eighteen existing T1/T2 regression tests pass with no
hardware access. This completion freezes the offline test basis only; none of
its synthetic values are installed-workcell measurements.

### Deliverables

- Select canonical fixtures for `robot`, `book`, `qaz`, `plm`, `H,H,1,PERIOD`,
  space, enter, and same-key repetition.
- Pin the schema, target catalog, arm model, calibration-fixture identity,
  planner policy, synthetic dynamics profile, and controller encoding profile
  used by offline tests.
- Define stable outcome codes for every planned gate.
- Define benchmark measurements and ceilings before optimization begins.
- Record that the pinned profiles are test fixtures, not installed workcell
  qualifications.

### Gate

Repeated compilation produces identical bytes and hashes on supported Python
versions. Crossed identity, reordered action, unsupported character, and
unbounded input fixtures fail closed. No test fixture is labeled measured.

## PC1 — Joint-space dynamics and deterministic time scaling

**Completed 2026-09-28:** the PC1 boundary consumes
the exact hash-valid T2B-IK sample order, explicitly maps the semantic PC0
joint order onto the canonical URDF joint order, applies deterministic bounded
time scaling, emits strictly monotonic nanosecond timestamps, reports whole-
schedule and per-segment velocity/acceleration/jerk demand and margin, and retains explicit
installed-dynamics, controller-tracking, collision, and fresh-state blockers.
The canonical parser revalidates artifact and profile hashes, exact fields,
sample/segment lineage, and timestamp consistency. Focused tests exercise all
three limiting dimensions at just-inside and just-outside rescale bounds,
stationary and reversal behavior, crossed order and source lineage, non-finite
limits, and deterministic reconstruction. This gate is synthetic and offline;
it produces no controller command or physical authority and does not qualify
installed dynamics or tracking.

### Deliverables

- Add a typed, canonical joint schedule artifact consuming the exact ordered IK
  sample results without route regeneration.
- Pin per-joint velocity, acceleration, and jerk ceilings in an arm-owned
  dynamics profile.
- Calculate segment durations and time-scale the route until every sampled
  joint stays within those ceilings.
- Preserve semantic dwell and phase boundaries while distinguishing collision
  samples from commanded stop points.
- Report demand, limit, margin, rescale factor, duration, and limiting joint for
  every segment and for the complete action.
- Reject non-finite values, non-monotonic time, discontinuity, missing joints,
  excessive rescaling, resource overflow, and crossed lineage.

### Tests

- Exact limit, just-inside, and just-outside cases for each dynamic dimension.
- Stationary repeated-key segment and direction reversal.
- Very short and long transitions.
- Mutation tests for sample order, timestamp, joint order, profile hash, and
  source hash.
- Determinism across repeated runs and supported platforms.

### Gate

Every passing schedule proves its pinned synthetic joint limits with positive
reported margin. Every violation rejects deterministically. The artifact still
states that controller tracking and settling are physically unqualified.

## PC2 — Golden end-to-end shadow pipeline

**Completed 2026-09-28:** one zero-I/O orchestration boundary composes the
real strict V2 decoder, trusted-registry admission and freshness recheck, T1
typing compiler, T2A Cartesian planner, T2B-IK screen, PC1 joint schedule, and
collision-evidence intake. Retained golden receipts for `robot` and
`H,H,1,PERIOD` preserve repeated targets and all nine stage hashes before
stopping at the honest installed-profile/fresh-state blocker. The retained
schema and parser revalidate the outer receipt hash, exact field and stage-hash
sets, ordered targets, terminal blocker lineage, and zero-authority assertions.
Eight stage-input mutations reject at the strict decoder, ingress, freshness,
IK lineage, or dynamics owner; five independently rehashed receipt mutations
reject at their owning receipt rule. This gate remains synthetic and grants no
transport, controller command, permit, or physical authority.

### Deliverables

- Compose the real AI V2 decoder, typing compiler, Cartesian planner, IK screen,
  joint dynamics gate, and collision-evidence intake behind one zero-I/O entry
  point.
- Retain one golden `type robot` trace and the punctuation/repetition fixture
  `H,H,1,PERIOD`.
- Store canonical stage hashes, ordered action identities, terminal status, and
  exact blocker lineage.
- Add mutation fixtures that change one field at a time and verify rejection at
  the owning boundary.

### Gate

The same input produces the same ordered stage hashes and terminal receipt. A
crossed or mutated input fails at the earliest responsible gate. The real
unmeasured path stops at its honest evidence blocker; the synthetic path cannot
gain permits, transport, or deployment status.

## PC3 — Rolling-horizon rebinding and restart safety

**Completed 2026-09-28:** `typing_rolling_horizon_v1` now retains exactly one
current action and at most one zero-authority preview. Each horizon is bound to
the exact observed start state, feedback receipt, controller session,
configuration epoch, calibration, tool profile, dynamics profile, freshness
limit, plan, and deadline. Revalidation deterministically invalidates and
discards both slots when any bound identity drifts or evidence expires.
Pre-dispatch restart reconstructs intent without replay; once a dispatch intent
has been retained, restart terminates `OUTCOME_UNCERTAIN` with automatic retry
forbidden. A strict parser and JSON Schema reject crossed indices, epochs,
hashes, roles, or authority fields. Twenty-four focused tests and fifty-four
affected lifecycle/planning tests pass with zero hardware access. This is
offline orchestration evidence only; it issues no permit or controller command.

### Deliverables

- Implement a state machine with a one-action commit horizon and one-action
  preview horizon.
- Bind the current action to an observed-state identity and configuration epoch.
- Preview the next action with zero authority while the current action remains
  pending.
- Invalidate preview on state drift, calibration/tool/profile change, stale
  evidence, controller-session change, cancellation, or expired deadline.
- Reconcile restarts from durable state without replaying a possibly completed
  action.

### Gate

Preview never creates a permit. Every forced invalidation discards or replans
the preview. Pre-dispatch restart may safely reconstruct intent; post-dispatch
or ambiguous restart terminates `OUTCOME_UNCERTAIN` with retry forbidden.

## PC4 — Typing-specific zero-write controller bridge

**Completed 2026-09-28:** `typing_controller_bridge_v1` now selects only the
PC3 current action from the exact arm-owned timed joint schedule, cross-checks
its semantics against the bound trajectory, and encodes deterministic pinned
Waveshare T=102 bytes. The sealed preview binds the action, schedule, dynamics,
configuration epoch, observed state, controller session, collision
qualification, execution envelope, single-use permit identity, and encoding
profile. It records bounded T=105/T=1051 feedback requirements but neither
consumes the physical permit nor opens a transport. Frozen golden bytes cover
ordinary motion, while focused tests cover repeated-target identity,
controller-setting boundaries, crossed lineages, expiry, feedback deadlines,
and independently rehashed mutations. Fifteen focused tests and eighty-three
affected protocol/planning tests pass with zero writes. PC5 fault campaigns may
now begin; installed-workcell qualification and physical authority remain
blocked.

### Deliverables

- Convert one qualified timed joint action into the existing pinned Waveshare
  command representation without opening a transport.
- Keep joint order, unit conversion, speed, acceleration, timing, and command
  policy arm-owned.
- Bind exact encoded bytes to the action, schedule, dynamics profile,
  configuration epoch, observed state, execution envelope, and single-use
  permit identity.
- Produce expected acknowledgement and feedback requirements plus bounded
  deadlines and terminal receipt fields.
- Add golden-byte fixtures for ordinary movement, repetition, boundary values,
  and invalid inputs.

### Gate

Exact controller bytes are deterministic and match the pinned protocol tests.
One action maps to one sealed dispatch intent. No AI field can directly inject
controller JSON, arbitrary dynamics, a port, retry behavior, or authority.

## PC5 — Fault injection and property testing

**Completed 2026-09-28:** a bounded, canonical campaign contract freezes
all 35 required cases across the six fault families below. Every observation
must carry its stable reason and terminal disposition and prove zero escaped
exception, authority leak, automatic retry, reorder, silent fallback, or
unbounded allocation. The strict report parser independently reconstructs the
campaign summary and hash. In parallel, the live V2 decoder gained a 32-level
JSON-depth ceiling and stable recursion rejection; rolling horizons now cap at
64 actions; and controller previews cap command count and per-command payload
bytes while normalizing malformed protocol payloads. The completion tranche
drives all declared planning, transport/feedback, sequence, restart, identity,
order, cache, deadline, cancellation, and resource cases through their actual
zero-hardware owning boundaries. A separately hash-bound, 64-entry observation
cache rejects corruption, crossed qualification identity, malformed contents,
duplicates, and overflow without carrying commands or authority. Twenty-nine
focused campaign tests and the 145-test affected boundary suite pass with zero
physical I/O. PC6 deterministic trace-journal work is ready.

### Required fault families

- malformed, duplicate, missing, oversized, NaN, infinity, and deeply nested
  model inputs;
- stale observation, crossed calibration/catalog/model/profile identities, and
  reordered or duplicated action indices;
- unreachable IK, joint-limit loss, singularity, discontinuity, dynamics
  overflow, collision-evidence absence, and clearance loss;
- late acknowledgement, missing or malformed feedback, partial write,
  disconnect, controller restart, sequence mismatch, and ambiguous completion;
- process crash before intent, after durable intent, during dispatch, after
  possible contact, and before effect verification; and
- cache corruption, cache identity crossing, deadline expiry, cancellation, and
  bounded-resource exhaustion.

### Gate

Property and mutation campaigns produce no uncaught exception, authority leak,
automatic retry, reorder, silent fallback, unbounded allocation, or inconsistent
terminal outcome. Every rejected case has a stable machine-readable reason.

## PC6 — Unified trace journal and deterministic replay

**Checkpoint 2026-09-28:** the first replay-only backbone now seals an exact
14-stage lineage from request and AI batch through ingress, execution plan,
trajectory, IK, joint schedule, collision screening, controller preview,
permit policy, encoding, dispatch rehearsal, feedback rehearsal, and the
effect-verification placeholder. Each bounded artifact is represented only by
its byte count and SHA-256 digest in a stage-order hash chain; raw payloads are
not copied into the journal. Deterministic replay detects missing, mutated,
empty/truncated, extra, reordered, and correlation/request-crossed artifacts.
The seven focused tests and 99-test affected journal/planning suite pass with
zero hardware access or authority. The next checkpoint adds the real PC2-PC5
adapter: it validates the strict batch, shadow receipt, rolling horizon,
controller preview, and fault-campaign contracts; rejects crossed request,
action, horizon, or schedule lineage; and derives the exact replay artifacts
and explicit not-observed effect placeholder. The combined 103-test suite
passes. ARM-088 adds the contained package and CLI: canonical
manifest/journal files plus 14 exact artifact files live beneath a
caller-selected nonsymlink evidence root; package identifiers cannot contain
paths; every file is bounded and hash-checked; and sensitive keys, absolute
paths, symlinks, noncanonical JSON, deletion, mutation, and unexpected entries
reject. `replay-typing-trace` verifies byte identity only and reports zero
authority. Twelve package tests, two CLI tests, and the 117-test affected suite
pass. PC6 remains in progress only until one actual adapter-produced golden
package is retained and replayed from a clean checkout. ARM-089 completes the
gate with an adapter-generated retained package containing the exact 14-stage
trace. The adapter regenerates every retained byte identically, and the
checked-in package replays through the CLI from an isolated workspace with
zero hardware authority. The expanded affected suite passes 119 tests.

### Deliverables

- Define one correlation lineage from request and AI batch through plan,
  trajectory, IK, dynamics, collision, preview, permit, encoding, dispatch
  rehearsal, feedback rehearsal, and effect-verification placeholder.
- Journal intent durably before any future dispatch boundary.
- Record canonical hashes and references rather than copying large or sensitive
  payloads unnecessarily.
- Provide a replay command that reconstructs decisions without hardware and
  detects missing or mutated artifacts.
- Redact ports, host identity, credentials, and private captures according to
  repository evidence policy.

### Gate

A clean checkout can replay the retained synthetic traces to the same decisions
and hashes. Mutation, deletion, truncation, or lineage crossing is detected and
cannot be reported as a pass.

## PC7 — Safe transition cache in shadow mode

**Checkpoint 2026-09-28:** ARM-090 adds the first bounded, deterministic
transition cache. Its exact directional key binds source and destination
targets, calibration, catalog, tool, arm model, dynamics, planner policy, and
device-pose epoch. Entries retain only canonical joint seed positions, a route
duration estimate, a planning-time-saved estimate, and the prior schedule hash.
Every hit requires fresh matching start state plus explicit IK, collision,
dynamics, and permit-policy validation; the returned hint still requires fresh
planning and full safety screening and carries no command, permit, or authority.
FIFO eviction, identity invalidation, corruption discard, and hit/miss/
validation/discard/time-saved metrics are deterministic. Fourteen focused tests
pass, including an actual cached-versus-uncached PC2 pipeline comparison, and
the affected PC2-PC7 suite passes 133 tests. ARM-091 completes the broader
campaign across every canonical PC0 typing fixture plus explicit reverse
travel, repeated keys, number/punctuation, and single-key routes. All seven
bound identity dimensions invalidate stale entries, and a seeded 128-operation
capacity campaign is deterministic and bounded. Thirty-one focused tests and
the 150-test affected suite pass. Cached and uncached receipts and schedule
hashes remain identical, satisfying the PC7 gate.

### Deliverables

- Cache only planning seeds and timing estimates for directional target pairs.
- Key entries by source/destination target, calibration, catalog, tool, arm
  model, dynamics, planner policy, device-pose epoch, and direction.
- Revalidate start state, IK, collision evidence, dynamics, and permit on every
  use.
- Track hit, miss, validation, discard, corruption, and time-saved metrics.
- Bound cache size and provide deterministic eviction and invalidation.

### Gate

Cached and uncached planning produce equivalent admitted schedules within the
declared deterministic contract. A cache hit never changes safety disposition
or creates authority. Crossed or stale entries are rejected rather than used.

## PC8 — Performance benchmark and readiness report

**Checkpoint 2026-09-28:** ARM-092 adds the bounded performance-report
contract. It requires at least 50 unique samples for cold cache, warm cache,
long strings, repeated keys, punctuation, keyboard extremes, forced rejection,
direct hover, and park-between-key baseline scenarios. Every sample accounts
for the nine declared CPU stages, total CPU, action and screening-sample counts,
serialized bytes, peak process memory, predicted route duration, cache result,
and estimated time saved. The report computes deterministic nearest-rank
p50/p95/p99 statistics, enforces all retained PC0 ceilings, and permanently
labels simulated duration as not being measured typing speed. Eight focused
tests and the 158-test affected suite pass. PC8 remains in progress pending an
instrumented pipeline runner, retained report, and bottleneck/readiness review.
ARM-093 adds the instrumented runner over the actual PC2 decoding, static
validation, planning, IK, time-scaling, collision-intake, and receipt boundaries.
It records process CPU, peak working set, screening samples, serialized receipt
bytes, predicted schedule duration, and declared cache estimates while keeping
preview and encoding at zero where the honest collision-evidence blocker stops
the route. Profiled and ordinary receipts are byte-equivalent. Ten focused
runner/report tests and the 160-test affected suite pass. A retained 50-sample-
per-scenario campaign and readiness analysis remain.

**Completion 2026-09-28:** ARM-094 retains the complete 450-observation
campaign: 50 iterations for every required scenario, including 50/50 forced
rejections. All PC0 resource ceilings pass; peak working set is 72.99 MiB,
maximum action count is 16, maximum collision sampling is 178, and maximum
serialized receipt size is 1,522 bytes. IK is the dominant measured software
bottleneck at 8.953 seconds p95 process CPU. For the identical synthetic
`ROBOT` route, direct-hover predicted duration is 8.98 percent shorter than the
park-between-keys baseline. This comparison remains a simulation prediction,
not physical typing speed. The exact retained file and embedded content hashes
are regression-tested, and the expanded affected suite passes 162 tests with
zero hardware access, controller commands, or physical authority. The
[readiness report](TYPING_PERFORMANCE_READINESS_REPORT_V1.md) records the
bottleneck, optimization order, and unchanged operational blockers.

### Deliverables

- Benchmark p50, p95, and p99 where sample counts support them for decode,
  static validation, planning, IK, time scaling, collision intake, preview
  validation, encoding, and receipt creation.
- Measure total CPU time, peak bounded sample count, serialized artifact size,
  memory ceiling, cache behavior, and predicted route duration.
- Compare direct hover transitions with park-between-key baselines using the
  same route and safety policies.
- Run cold-cache, warm-cache, long-string, repeated-key, punctuation, keyboard
  extreme, and forced-rejection suites.
- Publish bottlenecks and budgets without presenting predicted duration as
  measured typing speed.

### Gate

The pipeline remains within declared resource ceilings, preserves every safety
margin, and shows a reproducible latency benefit or clearly documents why an
optimization was rejected. The report contains zero physical-performance
claims.

## PC9 — Camera-arrival evidence tooling and dry run

**Checkpoint 2026-09-28:** ARM-095 adds a canonical 15-slot arrival kit spanning
the four camera/support originals, five calibration originals, installed
geometry, cable envelope, keyboard/tool profiles, and localization campaign and
evaluation records. Every slot binds an external destination, one strict
physical-original sidecar schema, units/uncertainty requirements, review
fields, and downstream consumers. The retained synthetic dry run has zero
measured hashes and cannot advance an epoch, update a registry, install a
qualification, open a camera, start a controller, write hardware, or move the
arm. Mutation tests reject every attempted synthetic escalation. Thirty-three
combined arrival-kit, schema, campaign, evaluator, and camera/support-intake
tests pass. The arrival-day checklist records collection order and stop
conditions. PC9 remains in progress pending consolidated dry runs for the
remaining installed-geometry and calibration intake consumers.

**Completion 2026-09-28:** ARM-096 binds all 15 arrival slots to their actual
camera-support, planner-calibration, installed-collision, campaign-preflight,
or localization-evaluator consumer source and aggregate schema. Every dependency
is resolved and SHA-256-bound in the retained consumer map. The consolidated
225-test PC9 matrix covers arrival templates, schema mutations, exact retained
files, capture datasets/checksums, receipts, camera profiles, calibration
decoding, installed geometry, support/optics epoch intake, campaign preflight,
and evaluation. No measured original is consumed; every physical-admission
flag remains false. PC9 is complete as tooling and dry-run evidence only. The
physical-camera hold and all measured commissioning gates remain active.

### Deliverables

- Prepare bounded commands and templates for original image capture, file
  hashing, persistent camera identity, mode/control readback, and retention.
- Prepare calibration inputs for camera-to-board, board-to-robot,
  keyboard-to-board, and tool-to-joint transforms with units and uncertainty.
- Prepare installed geometry, rigid attachment, cable-envelope, keyboard, and
  tool profile intake templates.
- Prepare real-capture localization evaluation and containment reports.
- Dry-run every tool with synthetic fixtures while ensuring that synthetic
  results cannot populate measured qualification slots.
- Provide an arrival-day checklist with explicit stop conditions and no
  implicit movement authority.

### Gate

Every required physical original has a documented destination, schema, hash,
review field, and downstream consumer. A synthetic dry run cannot advance the
measured configuration epoch or deployment registry.

## PC10 — Pre-camera integration closure

### Completion record — 2026-09-28

PC10 is complete against clean-checkout implementation commit
`baa5745a966284bb94204307f1d37994e4e5bf3c`. The controlled rebind advanced
the PC0 source pin from FREEZE-012 to FREEZE-013 without changing robot
numerics, targets, optics, kinematics, semantic bindings, or physical-authority
flags. Deterministic downstream shadow, trace, and retained performance
evidence was regenerated under the new lineage.

The exact detached clean checkout passed:

- the governed portable offline matrix: 507 tests;
- the explicit PC0-PC9 gate matrix: 194 tests;
- repository-policy unit tests: 115 tests; and
- documentation, public-record, evidence-scope, repository-artifact,
  repository-health, source-archive-footprint, and release-integrity policy
  checks.

The repository-wide raw `pytest` discovery command is not the clean-checkout
boundary because it intentionally includes tests for ignored retained/private
evidence that is absent from a fresh clone. The maintained portable test list
and the explicit PC0-PC9 matrix are the governed reproducible boundaries.
GitHub CI remains the cross-platform confirmation path; the recorded local
clean-checkout execution used Windows and Python 3.10.10.

No controller was started, no transport was opened, no command was written,
and no torque or movement authority was exercised during this closure.

### Closure evidence

- All PC0-PC9 gates pass on a clean checkout.
- The full offline test matrix passes on the supported Windows and Ubuntu CI
  environments and supported Python versions.
- The `robot` and `H,H,1,PERIOD` golden traces replay deterministically.
- The live-path rehearsal stops exactly at missing measured evidence.
- The synthetic full-depth rehearsal reaches a zero-write terminal receipt with
  all synthetic labels intact.
- Fault injection proves bounded, deterministic failure and no automatic replay.
- Documentation, schema, dependency, repository, and audit checks pass.
- The shared workplan and evidence ledger receive exact commit, test, and
  limitation records.

### Exit status

Successful PC10 closure means:

> The arm software is ready to ingest final-camera measurements and begin
> separately authorized physical qualification.

It does **not** mean the camera, workcell, installed controller, collision
profile, contact behavior, outcome verification, physical typing speed, or
autonomous typing capability is qualified.

## Post-closure pre-camera continuation

PC11 through PC18 improve commissioning readiness without weakening the PC10
closure or consuming physical authority. They remain offline, fail closed, and
cannot advance a measured configuration epoch, install a collision profile,
open a camera or transport, issue a controller command, or authorize movement.

## PC11 — One-command zero-authority commissioning orchestrator

**Completed 2026-09-29:** ARM-104 composes the real 15-slot structural
preflight, repository-bound consumer handoff, strict canonical receipt loader,
and aggregate validation assessment behind one library/CLI boundary. Empty,
pending, blocked-consumer, and all-pass states remain distinct. The receipt
root accepts only the 15 canonical filenames and rejects extra entries,
symlinks, oversize, duplicate JSON members, crossed filenames, malformed
contracts, and authority-bearing receipts. The strongest result is only
`COMPLETE_FOR_OFFLINE_REVIEW`; every epoch, registry, qualification, camera,
transport, controller, command, write, movement, and authority field remains
false or zero. Commit `80502168aeac035e016d2872e462503ec1160619`
passed 554 governed tests, 115 repository-policy tests, and all maintained
audits from a detached clean checkout using the current Python environment.

### Objective

Compose the existing 15-slot evidence preflight, hash-bound consumer handoff,
strict receipt loading, and validation aggregation behind one deterministic
operator command. The command reports the earliest blocker and all exact stage
hashes without invoking hardware or manufacturing a pass.

### Deliverables

- One library entry point and one thin CLI wrapper.
- A strict canonical report schema and parser binding the preflight, handoff,
  receipt assessment, evidence root, and optional receipt root.
- Bounded receipt discovery using canonical artifact filenames only, with
  symlink, traversal, duplicate, oversized, malformed, and unexpected input
  rejection.
- Stable outcomes for missing originals, awaiting validation receipts,
  blocked consumer results, and complete offline review.
- Explicit zero-authority fields proving no epoch advance, registry update,
  camera/transport access, controller command, or movement.

### Gate

An empty arrival root blocks deterministically; a structurally complete
synthetic root with no receipts reports `AWAITING_CONSUMER_VALIDATION`; and the
same root with all 15 exact synthetic receipts reaches only
`COMPLETE_FOR_OFFLINE_REVIEW`. Repeated runs reproduce identical bytes and
hashes. Every mutation fails at its owning boundary.

## PC12 — Full synthetic arrival and fault campaign

**Completed 2026-09-29:** ARM-105 freezes and reproduces 18 synthetic cases
through the actual PC11 boundary. They cover empty, pending, all-pass,
consumer-blocked, and one-missing-receipt sessions; corrupted sources, rejected
review, mixed epochs, missing/duplicate/oversized sidecars; and unexpected,
unsafe, duplicate-member, crossed-name, authority-bearing, oversized, and
truncated receipts. All 18 reach the exact expected owner and disposition. The
campaign exposed and fixed two real defects: external sidecars previously lacked
duplicate-member and byte-size enforcement, and the handoff parser omitted the
global epoch-ready state when validating blocked routes. Commit
`f98ad366c19a960a07aea43e2612d21a304afe79` passed 560 governed tests, 115
repository-policy tests, and all maintained audits from a detached clean
checkout. The retained campaign is synthetic, opens no device or transport,
and grants no authority.

### Objective

Exercise the complete PC11 workflow under normal, partial, adversarial, and
resource-bound arrival conditions before the physical camera exists.

### Deliverables

- A frozen matrix covering absent files, wrong hashes, duplicate JSON members,
  mixed epochs, stale records, rejected review fields, crossed consumer routes,
  missing/duplicate receipts, blocked receipts, symlinks, unexpected files,
  truncation, oversize, and depth/resource ceilings.
- Deterministic campaign observations with stable reason codes and no escaped
  exception, fallback, retry, authority promotion, or unbounded allocation.
- Retained synthetic pass, pending, and blocked examples clearly labeled
  `SYNTHETIC_OFFLINE`.

### Gate

Every declared fault is rejected or blocked by the intended owner, and the
campaign report reconstructs to identical bytes and hashes in a clean checkout.

## PC13 — Domain-consumer operator wrappers

**Completed 2026-09-29:** ARM-106 provides one uniform dispatch and exclusive
receipt-write boundary for all 15 routes across the five native consumer
families. Mapping-based support, campaign, and localization outputs use the CLI;
typed planner snapshots and installed collision profiles use the same Python
operator without unsafe JSON reconstruction. The wrapper preserves every native
output hash and blocker, writes exactly `<artifact_id>.json`, rejects overwrite,
and never changes domain semantics. The full synthetic assembly remains 13
passes and two honest geometry/cable blockers. Commit
`0543b421104ae479c7a1f3ce56bd6f098e84a927` passed 564 governed tests, 115
repository-policy tests, and all maintained audits from a detached clean
checkout. It invokes no camera, transport, controller, command, or movement.

### Objective

Give operators one consistent offline interface for the five native consumer
families: camera/support, planner calibration, campaign preflight, localization
evaluation, and installed collision geometry.

### Deliverables

- Thin wrappers that consume exact handoff routes and already-produced native
  consumer outputs, then write canonical ARM-101 receipts into a caller-selected
  contained output root while retaining the native output hash.
- Consistent exit codes, diagnostics, overwrite protection, input/output hash
  display, resource limits, and zero-authority declarations.
- No alternate consumer logic: wrappers call the existing typed boundaries.

### Gate

All 15 routes can be invoked through the common wrapper contract with exact
artifact identity preserved. Crossed route, consumer, schema, input hash, or
output hash rejects without partial promotion.

## PC14 — Arrival-session manifest and state machine

**Completed 2026-09-29:** ARM-107 binds all 15 original summaries, handoff
routes, receipt summaries, candidate epoch, camera profile, tool profile, and
the complete PC11 report into one canonical hash-sealed manifest. The state
machine distinguishes collection incomplete, structurally complete, validation
pending, validation blocked, and offline-review complete while measured
commissioning remains held. Creation is exclusive; restart verification loads
a bounded duplicate-safe regular file, reruns PC11, and requires the entire
rebuilt manifest to equal the retained manifest. Changed evidence invalidates
resume; deliberately changing a candidate identity creates a distinct session
rather than corrupting or silently modifying the retained one. Commit
`0327035e2e77b37301f0fc9568146b37f14f55f9` passed 575 governed tests, 115
repository-policy tests, and all maintained audits from a detached clean
checkout. It invokes no camera, transport, controller, command, or movement.

### Objective

Make one camera-arrival session resumable, auditable, and resistant to mixed
configuration evidence.

### Deliverables

- A canonical session manifest binding expected slots, consumer routes,
  receipt paths, configuration-epoch candidate, tool/profile identities, and
  immutable source hashes.
- Explicit states for collection, structurally complete, validation pending,
  validation blocked, offline-review complete, and measured commissioning held.
- Restart-safe reconstruction from retained artifacts with no silent replay or
  overwriting of originals.

### Gate

Restart reconstructs the same state and hashes. Any changed original, route,
receipt, epoch, or profile invalidates the dependent state and cannot retain a
previous pass.

## PC15 — Installed-geometry and cable-envelope intake rehearsal

**Completed 2026-09-29:** ARM-108 added the first typed cable-envelope intake
boundary. It binds a bounded ordered posture set and every adjacent swept
envelope to the exact installed-collision profile and one accepted profile
source hash. The deterministic template is explicitly
`SYNTHETIC_OFFLINE_ONLY`; it installs no qualification and grants no physical
authority. The existing collision receipt emitter accepts this typed evidence
only for `cable_envelope`; it cannot satisfy `installed_geometry`. Missing
sweeps, crossed posture lineage, unknown source hashes, and route misuse reject.
Commit `4f23b638b4dd126caea7397d633502acec21c1b9` passed 579 governed tests,
115 repository-policy tests, and all maintained audits in a detached clean
checkout.

ARM-109 completes the stage with a hash-sealed eight-case campaign using the
real typed collision consumers. Complete rigid/attachment and sampled-cable
templates pass only the synthetic route rehearsal; a missing camera-holder
binding and unknown attachment evidence block with exact body-specific
diagnostics. The 64-posture boundary passes, while missing sweeps, crossed
posture lineage, unknown source hashes, and cable/rigid route misuse reject.
The retained report, strict parser, and schema all preserve zero authority.
Commit `e11f99394fea2c17aa28d37b6f659890e64edf98` passed 586 governed tests,
115 repository-policy tests, and all maintained audits in a detached clean
checkout. No camera, transport, controller, hardware write, or physical
movement occurred.

### Objective

Remove avoidable friction from the two currently blocked collision consumers
without pretending that measured installed geometry already exists.

### Deliverables

- Completed synthetic templates for rigid geometry, attachment evidence, cable
  swept envelope, uncertainty, provenance, review, and containment assumptions.
- Positive, negative, boundary, and crossed-lineage fixtures through the real
  typed collision-profile consumer and receipt emitter.
- Operator diagnostics that identify the precise missing or unsafe measurement.

### Gate

Complete synthetic inputs exercise the consumer to a synthetic-only pass;
incomplete or crossed inputs retain exact blockers. No synthetic profile can be
installed or used as physical collision qualification.

## PC16 — Immutable camera-replay runner

**Completed 2026-09-29:** ARM-110 adds a bounded immutable replay manifest,
strict parser, replay runner, report, two JSON Schemas, and a command-line
entry point. Each manifest binds one to 64 frozen images and metadata records,
the camera and support profiles, model, calibration, PC11 handoff, retained
campaign/localization outputs, and the exact receipt decisions expected from
the existing consumers. Identical files reproduce identical decisions. Changed
image, metadata, campaign output, localization output, model, calibration,
receipt, handoff, or authority fields reject. Source provenance is retained as
`ORIGINAL_CAPTURE` or `SYNTHETIC_FIXTURE`, while every execution is separately
labeled `IMMUTABLE_REPLAY`, so replay cannot masquerade as a fresh capture.
Commit `22715d3ff6d4eebf9782175f93d73b3cc2dfa36b` passed 597 governed tests,
115 repository-policy tests, and all maintained audits in a detached clean
checkout. No camera, model runtime, transport, controller, hardware write, or
physical movement occurred.

### Objective

Prepare the vision-facing arm workflow to rerun frozen image bytes and metadata
without requiring a live camera or allowing a replay to masquerade as a new
capture.

### Deliverables

- A bounded replay manifest binding original image bytes, capture metadata,
  camera/support profile, model identity, calibration identity, and expected
  consumer outputs.
- Deterministic replay into the existing campaign and localization consumers.
- Explicit distinction among original capture, immutable replay, and synthetic
  fixture evidence.

### Gate

Identical frozen inputs reproduce identical decisions; modified image bytes,
metadata, model/profile identities, or expected outputs reject. Replay grants no
live-camera, measured-epoch, or movement authority.

The runner revalidates retained campaign and localization outputs through the
real consumer receipt emitters; model inference remains AI-lane work and is not
performed by this arm-owned replay boundary.

## PC17 — Timing and observability report

**Increment 1 completed 2026-09-29:** ARM-111 adds the strict
`rocell.pre_camera_observability_report.v1` contract, parser, schema, CLI, and
governed mutation tests. It accepts only bounded PC11-PC16 samples with exact
monotonic durations, stable decision/blocker codes, cold/warm and
pass/block/pending coverage, cache outcomes, artifact/count ceilings, and
non-path correlation identifiers. Every sample binds identical pre/post
decision hashes; a changed decision rejects rather than becoming telemetry.
Percentiles are emitted only at supported sample counts (p50 at two, p95 at
20, and p99 at 100 observations). Reports explicitly carry zero performance,
physical-speed, camera, transport, controller, write, movement, or physical
authority. This increment defines and validates the reporting boundary; PC17
continued to a retained host-measured benchmark in ARM-112.

**Completed 2026-09-29:** ARM-112 executes the real offline PC11-PC16
boundaries 20 times per stage: ten freshly materialized artifact-tree runs and
ten retained-tree runs. The 120-sample report contains 61 pass, 33 blocked,
and 26 pending decisions. Every timed decision exactly matches a separate
verification execution. Per-stage p95 latency on the recorded Windows/Python
3.10 host was 93.564 ms (PC11), 1,333.4719 ms (PC12), 0.236 ms (PC13),
0.8717 ms (PC14), 256.4344 ms (PC15), and 2.1538 ms (PC16). These values
locate software bottlenecks; they are not admission thresholds, cross-host
benchmarks, model inference latency, controller timing, or physical typing
speed. The retained report hash is
`fb893be0f4c7915e6028a069b195145b77b92937023cc623f19737bae3f96a96`.

### Objective

Measure software latency and expose bottlenecks across commissioning and future
typing intake while keeping safety decisions independent of performance goals.

### Deliverables

- Per-stage monotonic timing, bounded counts, artifact sizes, cache outcomes,
  and stable blocker/decision codes for PC11-PC16.
- Correlation identifiers linking AI batch, target, plan, consumer, receipt,
  and session without recording credentials or private absolute paths.
- Retained cold/warm and pass/block/pending benchmarks with p50/p95/p99 where
  sample counts support them.

### Gate

Instrumentation does not change canonical safety decisions or hashes, exceed
declared resource ceilings, or turn predicted/replayed duration into a physical
speed claim.

## PC18 — Actual AI-output compatibility corpus and gate

**Completed 2026-09-29:** the retained PC18 corpus now binds exact bytes from
the actual shared batch emitter, the actual precision-adapter H,H,1,PERIOD
fixture, and the retained localization-abstention record. Seven cases reproduce
the expected producer or arm-owned disposition. The supported H,H,I case
preserves repetition and order through strict decode, registry admission,
preplanner revalidation, execution compilation, and trajectory compilation.
The real precision output preserves repetition, digit, and punctuation order
but stops at arm ingress because its 14.400834977 mm model bound plus placement
error leaves measured key-safe regions. Unsupported phone input, uncalibrated
localization, exact expiry, crossed image identity, and low confidence all fail
closed at their declared owner. The content-addressed report contains no
controller commands, hardware access, physical authority, installation,
startup, execution, or automatic-retry permission.

**Refined at ARM-114 / PC18.1:** the retained corpus now also includes an
actual-emitter 15-action mixed phrase with repeated letters, Space, digits,
period, and Enter, plus one actual-emitter batch covering all 46 named keyboard
targets. Both preserve exact target/contact order through offline trajectory
compilation. Strict decoding now records exact blockers for authority
injection, duplicate JSON members, non-finite coordinates, and reordered
actions derived from the retained H,H,I bytes. The report records the canonical
64-proposal and 1 MiB input ceilings; the largest retained case uses 46
proposals and 15,022 bytes. This is broader software-contract evidence, not
physical route or localization qualification.

### Objective

Continuously prove that the real AI producer and the arm runtime agree on the
same strict contract, including order, repetition, punctuation, abstention,
identity, confidence, uncertainty, and freshness behavior.

### Deliverables

- A retained corpus produced by the actual AI adapter, including ordinary
  strings, repeated keys, digits, punctuation, unsupported requests,
  localization abstention, stale observations, and crossed identities.
- Exact decode, admission, compilation, planning, and expected-blocker results
  against the arm-owned runtime.
- A shared compatibility report usable by both workstreams without giving the
  AI controller JSON, joint commands, port selection, retries, or authority.

### Gate

Every supported AI fixture reaches the expected arm-owned stage with exact
order preserved; every unsupported, stale, uncertain, or crossed fixture fails
closed at the declared owner. The corpus and report reproduce in a clean
checkout.

## Camera-dependent continuation

After PC11-PC18 and camera arrival, work resumes at the existing shared gates:

1. collect and retain the final-camera originals;
2. run the read-only 15-slot arrival-evidence preflight and resolve every
   missing, malformed, hash-mismatched, rejected, or mixed-epoch record;
3. commission the measured configuration epoch;
4. evaluate localization and uncertainty on disjoint real captures;
5. populate and screen the installed geometry and cable profile;
6. obtain a fresh observed arm state;
7. qualify one non-contact hover at the lowest speed class;
8. qualify one independently verified key action; and
9. expand to held-out short strings before performance tuning.

The [camera integration hold](../../docs/CAMERA_INTEGRATION_HOLD.md) remains in
force until its physical prerequisites are satisfied.

## Work and evidence procedure

For every PC increment:

1. implement one bounded deliverable;
2. add positive, negative, mutation, and resource-bound tests;
3. run focused tests, shared-boundary tests, documentation checks, and the
   relevant audit checks;
4. record exact commands, counts, commit identity, evidence class, result, and
   remaining blocker;
5. update this stage table and the shared workplan only after the gate passes;
6. preserve failed evidence rather than rewriting it; and
7. merge without modifying unrelated user-owned worktree changes.

## Completion checklist

- [x] PC0 qualification basis frozen
- [x] PC1 joint dynamics and time scaling complete
- [x] PC2 golden shadow pipeline complete
- [x] PC3 rolling horizon and restart safety complete
- [x] PC4 zero-write typing controller bridge complete
- [x] PC5 fault and property campaigns complete
- [x] PC6 trace journal and replay complete
- [x] PC7 transition cache shadow qualification complete
- [x] PC8 performance report complete
- [x] PC9 camera-arrival tools dry-run complete
- [x] PC10 clean-checkout pre-camera closure recorded
- [x] PC11 one-command zero-authority commissioning orchestrator complete
- [x] PC12 full synthetic arrival and fault campaign complete
- [x] PC13 domain-consumer operator wrappers complete
- [x] PC14 arrival-session manifest and state machine complete
- [x] PC15 installed-geometry and cable-envelope rehearsal complete
- [x] PC16 immutable camera-replay runner complete
- [x] PC17 timing and observability report complete
- [x] PC18 actual AI-output compatibility corpus and gate complete

## Related documents

- [Optimized typing execution plan](OPTIMIZED_TYPING_EXECUTION_PLAN.md)
- [Typing performance readiness report](TYPING_PERFORMANCE_READINESS_REPORT_V1.md)
- [Camera arrival-day checklist](CAMERA_ARRIVAL_DAY_CHECKLIST_V1.md)
- [Shared AI/arm workplan](../ai/docs/SHARED_AI_ARM_WORKPLAN.md)
- [Model command runtime implementation plan](../ai/docs/MODEL_COMMAND_RUNTIME_IMPLEMENTATION_PLAN.md)
- [Camera integration hold](../../docs/CAMERA_INTEGRATION_HOLD.md)
- [Evidence ledger](../ai/docs/EVIDENCE_LEDGER.md)
- [Documentation standard](../../docs/DOCUMENTATION_STANDARD.md)
