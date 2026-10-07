# Installed collision qualification implementation plan

- **Document status:** Active implementation plan
- **Audience:** Arm runtime, simulation, workcell, AI integration, and evidence reviewers
- **Owner:** Arm runtime and simulation workstream, with workcell measurement support
- **Reviewed:** 2026-10-07 against `main` commit `00d38a080b69f7236386efac7404b24766e220a9`
- **Authority:** Normative development and evidence guidance only. This plan grants no hardware, movement, contact, controller, or release authority.

## Objective

Convert the accepted, partitioned typing route into reproducible collision
evidence for the exact installed workcell. The result must show what geometry
was measured, how uncertainty was applied, which configurations and route
segments were screened, where clearance is smallest, and why the route is
accepted or rejected.

This work begins after semantic target ordering, planning, inverse kinematics,
and bounded route partitioning. It does not change AI output semantics, target
coordinates, joint limits, or the accepted route to make a collision result
pass.

The immediate target is the promoted 328-segment typing route retained by
PRs #231-#233. The implementation must remain usable for later routes without
hard-coding this route's target string or sample count.

## Current baseline

The following capabilities are already merged to `main` and are inputs to this
plan rather than work to repeat:

| Capability | Current evidence |
| --- | --- |
| Strict model-to-arm target ingestion | Semantic target order enters the strict `ModelMotionBatchV2` boundary |
| Complete accepted route | 328/328 canonical route samples pass the unchanged IK and adjacent-joint continuity gates |
| Bounded route partitions | The route is covered by two bounded partitions with an exact boundary recheck |
| Partition-aware collision intake | Every route configuration and route segment has a declared evidence slot bound to one collision-contract identity |
| Installed geometry loader | `rocell.installed_collision_geometry_profile.v1` accepts only exact measured sources and fails closed on crossed identities |
| Cable evidence intake | Configuration samples and adjacent swept cable envelopes have a typed, zero-authority boundary |
| Observed route entry | A fresh observed start can be bound to a bounded entry route and sampled collision evidence |

The remaining gap is not whether software can enumerate the route. It is
whether the exact installed robot, attachments, cables, fixtures, board, and
clearance policy are represented with adequate measured evidence and remain
clear over every required configuration and segment.

## Non-goals

This plan does not:

- authorize movement or create controller commands;
- treat a photo estimate, nominal CAD model, synthetic fixture, or vendor render
  as accepted installed geometry;
- weaken the canonical IK margin, joint limits, sampling bounds, or collision
  policy to obtain a passing result;
- silently omit a camera support, cable, tool, clamp, keyboard, board edge, or
  nearby fixed obstruction;
- interpret language-model output, infer key identity, or modify target order;
- claim continuous physical safety from discrete samples alone;
- treat an Isaac Sim result as a physical permit; or
- merge the long-lived `issue/190-isaac-sim-host` or
  `issue/190-contact-boundary-repair` histories wholesale.

## Target evidence flow

```text
accepted ModelMotionBatchV2
        |
        v
accepted execution plan and 328-segment IK route
        |
        v
partitioned collision intake
        |
        +-------------------------------+
        |                               |
        v                               v
measured installed profile       fresh observed start
        |                               |
        v                               v
rigid attachment bindings        observed-to-route entry samples
        |
        v
configuration-sampled cable geometry and sweep envelopes
        |
        v
partition configuration checks + conservative segment sweeps
        |
        v
cross-partition reconstruction and minimum-clearance report
        |
        v
PASS, REJECT, or BLOCKED evidence receipt

No commands, transport, permit, automatic retry, or physical authority
```

## Development rules

1. Every pull request starts from current `main` and advances one bounded gate.
2. Branch names use the work outcome, for example
   `feature/installed-collision-profile-v1`; do not use tool or worker names.
3. Inputs are immutable, content-addressed, and checked before evaluation.
4. Unknown or absent measurements produce a named `BLOCKED_*` result.
5. A result is never edited after it is observed. Corrections require a new
   fixture, result, and lineage record that preserves the failed attempt.
6. Synthetic fixtures may prove software behavior but cannot satisfy an
   installed-geometry or physical-clearance gate.
7. No stage may generate controller JSON, open a transport, assert DTR/RTS,
   alter torque, move the arm, or promote a hardware gate.
8. Each result states hardware writes, physical movements, GPU jobs, and
   authority explicitly.

## Work packages

### ICQ-0 — Baseline and issue alignment

**Purpose:** Make the repository and issue tracker name the same current
dependency.

**Deliverables:**

- Link this plan from the documentation index and issue #190.
- Replace issue #190's stale next increment with the post-PR-233 sequence.
- Record that the 328-segment route and partitioned intake are complete while
  installed screening remains open.
- State that the long-lived research branches are extraction sources only.

**Acceptance:**

- The issue body and this plan agree on the next mergeable increment.
- No completed work package is reopened or overstated.

### ICQ-1 — Measurement manifest and capture worksheet

**Purpose:** Define every physical input before creating an installed profile.

**Deliverables:**

- A versioned measurement-manifest schema and example with explicit units,
  coordinate frames, measurement method, device identity, uncertainty, source
  artifact hash, and capture time.
- A CLI that validates the manifest without converting incomplete records into
  geometry.
- A human-readable capture worksheet generated from the required-body inventory.
- Negative fixtures for missing units, anonymous frames, duplicate bodies,
  stale/crossed sources, nonfinite values, and unsupported measurement methods.

**Required inventory:**

| Group | Required content |
| --- | --- |
| Robot | Base and every moving link envelope, joint/link frame identity, model/source hash |
| Installation | Factory base/clamp, board edges and thickness, robot-to-board placement |
| End effector | Gripper body and jaw state; tool geometry only when a tool is installed |
| Target devices | Keyboard and phone envelopes, placement transforms, support surfaces |
| Camera system | Camera body, lens/connector, mount/support/lighting geometry; explicitly absent only for a configuration that physically has none |
| Cables | Fixed cable anchors plus moving cable/harness body IDs and capture method |
| Environment | Nearby fixtures or obstructions inside the declared workcell boundary |
| Uncertainty | Geometry, pose, placement, repeatability, and required minimum separation sources |

**Acceptance:**

- The worksheet accounts for every required collision-contract body.
- Missing values remain missing; no default dimensions are invented.
- The validator produces no collision profile and no authority.

### ICQ-2 — Installed profile builder

**Purpose:** Convert a complete, reviewed measurement manifest into the existing
`rocell.installed_collision_geometry_profile.v1` contract.

**Deliverables:**

- A deterministic profile builder using spheres, capsules, and oriented boxes.
- Conservative primitive fitting with an explicit rule per source type.
- Exact source, manifest, build, robot model, base-contract, and clearance-policy
  bindings.
- A difference report showing every measured dimension and the conservative
  envelope derived from it.
- A strict profile audit and canonical content hash.

**Acceptance:**

- Every required body is present exactly once and marked `ACCEPTED_MEASURED`.
- Configuration-sampled bodies are declared but not falsely satisfied by static
  primitives.
- Every global pair exclusion is explicit, engineering-reviewed, source-bound,
  and narrower than an omission of body geometry.
- Positive minimum separation and nonnegative geometry/pose uncertainty are
  evidence-backed.
- Rebuilding from identical inputs is byte-identical.

**Rejection examples:**

- `BLOCKED_REQUIRED_BODY_MEASUREMENT_MISSING`
- `BLOCKED_PROFILE_SOURCE_IDENTITY_MISMATCH`
- `BLOCKED_CLEARANCE_POLICY_UNSUPPORTED`
- `BLOCKED_PAIR_EXCLUSION_NOT_ENGINEERING_ACCEPTED`

### ICQ-3 — Rigid attachment and placement binding

**Purpose:** Bind non-robot rigid bodies to exact workcell frames for the route.

**Deliverables:**

- Measured bindings for gripper/tool attachments, camera support, keyboard,
  phone, clamp, board, and fixed nearby geometry.
- A transform-chain audit from each body to the collision-contract root.
- Round-trip and frame-direction tests that detect swapped source/destination
  frames, millimetre/metre errors, and reflected rotations.
- A stale-placement rejection when a device or fixture moves after capture.

**Acceptance:**

- Every rigid attachment frame requested by each partition intake is supplied.
- All transforms share the same calibration/build/profile identities.
- No anonymous XYZ value enters collision evaluation.

### ICQ-4 — Configuration-sampled cable and harness evidence

**Purpose:** Represent moving cables conservatively at every required route
configuration and between adjacent configurations.

**Deliverables:**

- A capture/import adapter for capsule-chain cable envelopes at each bounded
  route sample.
- Conservative swept envelopes for every adjacent route segment.
- Exact sample and segment lineage across both partitions.
- Uncertainty inflation for capture noise, cable thickness, and unobserved
  deformation.
- A boundary test proving the successor partition's recheck matches the
  predecessor terminal configuration exactly.

**Acceptance:**

- Every configuration-sampled body has geometry at every declared sample.
- Every adjacent route segment has a sweep envelope for every sampled body.
- Cable evidence cannot be reused across a different posture, segment, profile,
  or route hash.
- A static endpoint interpolation alone is rejected as insufficient.

### ICQ-5 — Partition collision evaluator

**Purpose:** Execute full-body collision checks over every bounded partition
without losing global route lineage.

**Deliverables:**

- A profile-bound evaluator consuming one partition, rigid bindings,
  configuration geometry, and sweep envelopes.
- Per-sample and per-segment results including tested pairs, excluded pairs,
  minimum clearance, limiting body pair, uncertainty inflation, and blockers.
- A resource-bounded failure mode for oversized evidence.
- A partition receipt with no commands and no authority.

**Acceptance:**

- Every declared evidence slot is consumed exactly once.
- Collisions, missing evidence, and evaluator errors remain distinct outcomes.
- A clear discrete sample is never labeled continuous proof.
- Repeated evaluation of identical inputs is byte-identical.

### ICQ-6 — Conservative continuous-segment qualification

**Purpose:** Close the gap between sampled configurations over every route
segment.

**Deliverables:**

- A documented conservative method: validated continuous-distance solver,
  adaptive subdivision with a provable motion bound, or an equivalent reviewed
  swept-envelope technique.
- Body-motion bounds derived from joint deltas and body radii.
- A per-segment clearance lower bound after geometry and pose uncertainty.
- Adversarial tests containing between-sample collisions that endpoint-only
  checks miss.
- A named `INDETERMINATE` result when the method cannot prove a segment.

**Acceptance:**

- All 328 source route segments are assigned exactly once.
- No segment is inferred clear solely from clear endpoints.
- Cross-partition continuity and the shared-boundary recheck reproduce.
- The final receipt distinguishes `CLEAR`, `COLLISION`, and `INDETERMINATE`.

### ICQ-7 — Fresh observed start and entry qualification

**Purpose:** Prove the arm can enter the qualified route from its actual current
state without assuming the synthetic route seed.

**Deliverables:**

- One fresh, authenticated, read-only joint-state observation contract.
- Tolerance and freshness checks bound to controller session, build,
  calibration, model, and profile identities.
- A bounded observed-to-route-entry path with IK, configuration geometry,
  collision samples, and continuous-segment evidence.
- A mismatch result that requires replanning rather than silently snapping to
  the nominal start.

**Acceptance:**

- Synthetic or stale start states remain execution-ineligible.
- A route is not reusable after the observed state, installed placement, tool,
  cable, or profile identity changes.
- No automatic retry or movement is authorized by this evidence.

### ICQ-8 — Route reconstruction and qualification receipt

**Purpose:** Reassemble the complete route result from bounded partition and
entry evidence.

**Deliverables:**

- A reconstruction validator proving exact coverage, order, hashes, and
  boundary continuity.
- One summary containing the minimum clearance and limiting body pair across
  entry plus all 328 route segments.
- Explicit `PASS`, `REJECT`, or `BLOCKED` disposition and complete limitations.
- Independent replay from retained compact artifacts.

**Acceptance:**

- Every configuration and segment traces to the accepted route and installed
  profile.
- A missing, duplicate, crossed, or stale partition fails closed.
- A passing receipt still has `controller_commands=[]`, hardware writes `0`,
  physical movements `0`, and `physical_authority=false`.

### ICQ-9 — WP3 handoff: native trajectory replay

**Purpose:** Hand a collision-qualified route to the next simulation work
package without changing its authority.

**Deliverables:**

- An Isaac request adapter that consumes the exact accepted trajectory and ICQ
  receipt without replanning.
- Tracking, settle, repeatability, and categorized disagreement evidence.
- Exact toolchain, scene, asset, driver, settings, seed, and GPU identities.

**Entry gate:**

- ICQ-8 is complete for the exact route and installed profile.
- WP0 has an accepted exact runner lock and license/redistribution disposition.

**Acceptance:**

- Native replay is deterministic within declared tolerances.
- A simulator pass remains advisory and cannot promote a physical gate.

## Parallel WP0 work

The exact Isaac Sim runner and license review are independent of ICQ-1 through
ICQ-8 and should proceed in parallel:

1. Select one exact installed Isaac Sim build and runner identity.
2. Freeze extensions, settings, driver, scene/asset hashes, and launch method.
3. Record exact-version licensing and redistribution disposition.
4. Change the authoritative lock from `UNSELECTED` only after the complete
   record is reviewable.

WP0 does not block writing or testing the portable installed-collision
contracts. It blocks claims that depend on an authoritative Isaac execution.

## Recommended pull-request sequence

| Increment | Scope | Can start before camera installation? | Completion evidence |
| --- | --- | --- | --- |
| PR-A | ICQ-0 plan/index/issue alignment | Yes | Documentation checks and issue update |
| PR-B | ICQ-1 measurement manifest, worksheet, validator | Yes | Schema, fixtures, unit tests |
| PR-C | ICQ-2 deterministic profile builder | Yes, using synthetic rejection fixtures only | Byte-stability and fail-closed tests |
| PR-D | ICQ-3 rigid-binding validator | Yes | Transform and stale-binding tests |
| PR-E | ICQ-4 cable evidence adapter | Partly; real evidence waits for installation | Coverage, lineage, adversarial tests |
| PR-F | ICQ-5 partition evaluator | Yes | Synthetic clear/collision/incomplete fixtures |
| PR-G | ICQ-6 continuous method | Yes | Between-sample collision controls and proof limits |
| PR-H | Populate measured installed profile | Requires installed measurements | Accepted profile and audit receipt |
| PR-I | Populate route cable/attachment evidence | Requires final installed configuration | Complete configuration and sweep coverage |
| PR-J | ICQ-7 observed-start entry | Requires a fresh read-only observation | Entry qualification receipt |
| PR-K | ICQ-8 full reconstruction | Requires PR-H through PR-J | Reproducible PASS/REJECT/BLOCKED receipt |
| PR-L | ICQ-9 WP3 replay | Requires PR-K and WP0 | Native replay receipt |

Each PR uses `Advances #190`. None uses `Closes #190` until the complete issue
acceptance boundary is satisfied.

## Test strategy

### Unit and schema tests

- canonical hash and byte-stability tests;
- unknown-field and missing-field rejection;
- crossed manifest/build/model/profile/route identities;
- unit and coordinate-frame mistakes;
- nonfinite and out-of-range geometry;
- missing required bodies and primitive limits;
- unjustified pair exclusions;
- stale observed starts and placements;
- duplicate, omitted, reordered, or crossed partition samples;
- missing cable geometry or segment sweep envelopes; and
- explicit zero-command and zero-authority assertions.

### Geometry controls

- known-clear configuration;
- known-colliding configuration;
- tangency under uncertainty inflation;
- collision occurring only between endpoints;
- collision introduced only by a cable envelope;
- collision introduced only by a rigid attachment;
- exact shared-boundary reproduction; and
- minimum-clearance tie handling with deterministic ordering.

### Repository validation

From `software/`, run the focused tests for the changed package. From the
repository root, every increment runs:

```powershell
python scripts/ci/check_docs.py
python scripts/maintain_repository.py verify
python scripts/maintain_repository.py verify --full
```

The full offline CI matrix remains required before merge. GPU or hardware
execution is never substituted for portable contract tests.

## Evidence package

Every result package records:

- base and result commit identities;
- request, route, partition, profile, calibration, build, model, policy, and
  source hashes;
- exact commands, exit codes, dependency versions, and runtime identity;
- predeclared thresholds and resource bounds;
- complete sample/segment counts and coverage;
- minimum clearance, limiting pair, and categorized blockers;
- failed attempts and amendments without rewriting history;
- retained compact artifact paths and external-artifact references;
- limitations and the next unmet dependency; and
- `hardware_access=false`, `controller_commands=[]`, `wire_commands=[]`,
  hardware writes `0`, physical movements `0`, and
  `physical_authority=false`.

## Stop conditions

Stop with a named blocked or rejected result when:

- a required installed body or transform is missing;
- a source is nominal, photo-estimated, synthetic, stale, or identity-crossed;
- uncertainty or minimum separation lacks an accepted source;
- a configuration-sampled body lacks any sample or segment envelope;
- a route sample or segment cannot be assigned exactly once;
- a pair exclusion is broader than its engineering evidence;
- a continuous method cannot establish a conservative bound;
- the observed start is stale, synthetic, or outside tolerance;
- a collision is detected or clearance is below the accepted bound;
- a tool, camera support, cable routing, fixture, board, or device moves after
  qualification;
- an evaluator would exceed its bounded resource limits; or
- any proposed change introduces controller access, physical authority, or an
  automatic retry.

## Completion criteria

This plan is complete only when all of the following are true for one exact
installed configuration and one exact accepted typing route:

- [ ] Every required body has accepted measured geometry and source lineage.
- [ ] Every rigid attachment and workcell placement is measured and bound.
- [ ] Every configuration-sampled body covers every route sample.
- [ ] Every route segment has a conservative continuous-clearance result.
- [ ] Both bounded partitions and their shared boundary reconstruct exactly.
- [ ] A fresh observed start and observed-to-route entry are qualified.
- [ ] The complete result is independently reproducible from retained evidence.
- [ ] The receipt reports `PASS`, `REJECT`, or `BLOCKED` without ambiguity.
- [ ] No controller command, movement, contact, permit, or physical authority
  was produced by the qualification process.
- [ ] WP0 is complete before any authoritative Isaac WP3 replay claim.

Completing these criteria establishes a reproducible installed collision
qualification result. It does not by itself authorize physical movement.

## First implementation increment

Begin with **ICQ-1**, not additional route search:

1. Enumerate the required installed-body inventory from the active collision
   contract.
2. Freeze the measurement-manifest schema and negative fixtures.
3. Implement a read-only validator and worksheet generator.
4. Prove that incomplete measurements cannot create an installed profile.
5. Retain a compact zero-authority result and name ICQ-2 as the next dependency.

This is the highest-value pre-camera increment because it lets the workcell
owner collect the correct measurements once, using a contract the software can
validate directly.
