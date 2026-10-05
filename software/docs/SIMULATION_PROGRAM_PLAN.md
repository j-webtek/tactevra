# Tactevra prioritized simulation program

- **Status:** Frozen program plan; simulation only
- **Branch:** `issue/190-isaac-sim-host`
- **Claim:** `891c993a45b38a3e7ef066738af494c26c979b77`
- **Date:** 2026-10-04
- **Owners:** AI/model and simulation lane, with arm/runtime contract review
- **Authority:** None. This plan cannot create a command, execution permit,
  transport payload, controller write, hardware write, or physical movement.

## Program objective

Build a reproducible digital-twin and fault-injection program that connects
intent, deterministic typing semantics, perception evidence, arm planning,
simulated motion and contact, device behavior, and independent effect
verification. The program answers which software contracts work in simulation,
which physical performance ranges appear feasible, and which measurements are
required before any physical claim.

The program does not qualify hardware. Every unmeasured physical quantity is a
declared sensitivity range. Results remain `EXPLORATORY_SIMULATION_ONLY` until
the corresponding physical source is measured and admitted through its own
procedure.

## Mandatory program controls

These controls apply to every workstream and override convenience or speed.

1. Hardware access, writes, movements, controller commands, execution permits,
   transport, and physical authority remain exactly zero.
2. Each workstream begins with a separate claim commit. Its fixture, identities,
   ranges, metrics, decision rules, random seeds, and stop rules are committed
   before execution.
3. Failed or superseded attempts remain hash-bound in external evidence and are
   summarized without rewriting their original outcome.
4. A workstream may not promote a single synthetic value as a measured physical
   constant. Ranges are reported with the sampling design that produced them.
5. Dual-GPU work records each GPU identity, driver, CUDA, Python, MuJoCo,
   MuJoCo Warp, Warp, Isaac, and operating-system version. Numerical payloads
   must match exactly where the same deterministic computation is expected;
   otherwise a predeclared tolerance and reason are required.
6. One compact, hash-bound repository summary and one external manifest are
   preferred per workstream. Raw frames, tensors, trajectories, and simulator
   caches remain external.
7. Every external manifest inventories exact relative paths, byte sizes, and
   SHA-256 values. Completion requires a verified second copy. The backup root
   must be supplied explicitly; if it is unavailable, the workstream reports
   `BLOCKED_BACKUP` rather than claiming completion.
8. Each workstream reports hardware-write count, physical-movement count,
   command count, permit count, transport count, render count, physics-step
   count, training-run count, and physical-authority state.
9. The source-archive check, maintained documentation check, focused tests, and
   `git diff --check` run before every result commit.
10. A later workstream may start early only when every dependency is satisfied,
    its fixture is frozen, and it does not compete for CPU, disk, or GPU capacity
    with a higher-priority run.

## Current no-preemption dependency

The paired 96-versus-192 residual-obstruction comparison was already active
when this program was requested. The observed process is:

```text
run_full_paired_training.py --profile ASSUMED_LOW --workers 8 --maximum-epochs 18
```

No program GPU process may start until that campaign finishes or fails and its
own owner records the outcome. Step 0 planning and CPU-only implementation may
proceed. This program must not terminate, reprioritize, alter, or reuse that
process or its outputs.

## Shared evidence and determinism contract

Each workstream freezes one manifest with:

- program, workstream, schema, commit, fixture, catalog, model, simulator asset,
  and source hashes;
- all random seeds and partition identities;
- physical sensitivity ranges and units;
- selected GPU UUID, driver, runtime, and simulator versions;
- expected output identities and admission rules;
- zero-authority counters; and
- backup source and destination receipts.

Randomized scenarios use a counter-based seed derived from the manifest hash,
scenario identity, and repetition index. CI subsets use a strict subset of the
same identities. Re-running a subset does not create new samples.

Timing is reported separately from correctness. Wall-clock timing is descriptive
unless a workstream explicitly freezes a performance gate. Simulator throughput
cannot be presented as expected hardware throughput.

## Dependency order

```mermaid
flowchart TD
    P[Step 0 frozen program plan] --> W1[WS1 end-to-end typing twin]
    W1 --> W2[WS2 key press physics]
    W1 --> W4[WS4 fixture drift and recovery]
    W2 --> W3[WS3 continuous typing policy]
    W2 --> W5[WS5 calibration budget]
    W4 --> W5
    W3 --> W6[WS6 mid-motion Isaac observation]
    W4 --> W6
    W1 --> W7[WS7 first-motion readiness]
    W4 --> W7
    W5 --> W7
    W2 -. selected tool .-> W7
```

Workstreams execute in numerical order. The graph identifies implementation
dependencies; it does not authorize out-of-order GPU execution.

## Workstream 1: end-to-end typing digital twin

### Objective

Create a deterministic, zero-authority closed-loop regression harness from
typed user intent through simulated device effect and independent verification.
It becomes the common fault-injection boundary for later workstreams.

### Questions answered

- Does a valid intent preserve the user's exact requested text?
- Does deterministic compilation preserve semantic target order, repeats,
  punctuation, numbers, and every modifier or phone-layer transition?
- Do perception, fusion, planning, simulated motion, device state, and effect
  verification agree on each committed character?
- Does the system detect an invalid Sticky Keys configuration, phone-layer
  mismatch, autocorrect, predictive text, missing event, duplicate event, wrong
  event, stale observation, or impossible target?
- Can a small CI subset reproduce the full harness semantics and receipt?

### Frozen inputs

- Closed intent schema: `TYPE_TEXT`, `PRESS_KEY`, `CLARIFY`, and `REFUSE`.
- The exact admitted simulation target catalog at workstream freeze. Catalog
  cardinality is never inferred from a renderer or planner output.
- Deterministic keyboard compiler and explicit Sticky Keys state machine.
- Deterministic phone layer machine with letters, shift, numbers, symbols,
  backspace, and enter/action transitions.
- `ModelMotionBatchV2` remains the AI-to-arm boundary. No joint, PWM, serial,
  Waveshare, permit, or transport field is added.
- Analytic target geometry is the default perception mode. A small exact
  allowlist of fixed strings and faults uses retained Isaac-rendered perception
  after the no-preemption dependency clears.
- Existing zero-authority arm-runtime IK and screening interfaces and the
  kinematically consistent MuJoCo model.

### Scenario fixture

The full fixture contains:

- `Hello 2026!` on keyboard and phone;
- every supported printable ASCII character;
- repeated keys, including repeated shifted symbols;
- all lower/upper, upper/upper, symbol/symbol, space-to-shift, trailing-capital,
  phone shift, phone numeric, and phone symbol-layer transitions;
- 10,000 seeded random text payloads for keyboard and 10,000 for phone;
- lengths sampled from the declared set `1, 2, 4, 8, 16, 32, 64, 128` with
  equal identity allocation, plus explicit empty and unsupported cases;
- exact quoted-text preservation cases and ambiguous unquoted requests; and
- an autocorrect/predictive-text-on phone case that must be detected.

The random alphabet is the compiler-supported printable set frozen in the
manifest. Unsupported characters are separate negative tests and may never be
silently substituted.

### Closed-loop stages

```text
intent JSON
  -> exact-text guard
  -> keystroke or phone-layer compiler
  -> ordered semantic targets
  -> analytic or allowlisted Isaac perception
  -> fusion and named-target admission
  -> zero-authority IK and collision screening
  -> MuJoCo kinematic motion receipt
  -> simulated keyboard/phone actuation
  -> simulated host event or screen-state log
  -> independent text/state verification
```

Sticky Keys models latch, lock, unlock, the five-press shortcut, and the
two-key-disable setting. The commissioned simulation profile requires the
five-press shortcut disabled and simultaneous-key disable off. Phone
commissioning requires autocorrect and predictive text off. The required
negative case turns them on and must produce a configuration mismatch rather
than an accepted exact-text result.

### Fault-injection hooks

Named hooks are frozen for: stale frame, stale telemetry, missing target,
target displacement, perception abstention, fusion rejection, unreachable IK,
collision rejection, dropped press, duplicate press, wrong press, delayed
press, Sticky Keys state divergence, phone-layer divergence, autocorrect,
predictive replacement, readback delay, and verification mismatch.

### Outputs

- One deterministic full-run receipt and one CI-subset receipt.
- Per-scenario ordered stage trace with no authority-bearing fields.
- Simulated keyboard event log and phone screen-state/readback log.
- Fault-injection registry consumed by Workstreams 4 and 6.
- Stage-latency distributions and exact failure attribution.

### Metrics

- exact-text success rate;
- schema validity and exact quoted-text preservation;
- semantic-target order and repeat preservation;
- compiler versus simulated OS/device-state disagreements;
- independent verification agreement;
- false acceptance of injected faults;
- per-stage median, p95, p99, and maximum latency; and
- full/CI deterministic receipt agreement on shared identities.

### Pass and stop rules

Pass requires 100% schema validity, zero altered quoted payloads, 100% exact text
for all supported no-fault scenarios, zero target-order differences, zero
compiler/device-state disagreements, 100% independent verification agreement,
and detection of every injected deterministic fault at its declared stage.
Autocorrect-on and predictive-text-on must fail commissioning and must not be
counted as typing failures after admission. Any silent substitution, accepted
state divergence, authority-bearing output, or non-deterministic shared receipt
stops the workstream. Latency is descriptive in WS1 and becomes a policy metric
in WS3.

### Dependencies and compute estimate

Step 0, admitted schemas/catalogs, existing compiler/runtime interfaces, and the
finished 96/192 job are required. CPU implementation and analytic runs are
estimated at 30â€“90 minutes. The exact Isaac subset is estimated at 15â€“45 GPU
minutes total. MuJoCo replay is estimated below 15 GPU minutes. The workstream
must benchmark a smoke before scheduling the full subset.

## Workstream 2: key press physics in MuJoCo Warp

### Objective

Build an exploratory contact model that maps landing error and press timing to
key actuation, neighbor contact, repeat behavior, phone tap, and long press.

### Questions answered

- Which press depth, dwell, approach speed, and release speed ranges actuate
  once without neighbor contact or repeat?
- How does fingertip radius change the per-key envelope?
- Which ranges fail first on `GRAVE`, `EQUAL`, `Z`, and `SHIFT`?
- Which phone contact-area and duration ranges separate tap from long press?

### Predeclared physical sensitivity ranges

All values are exploratory until measured:

| Parameter | Range |
|---|---:|
| keycap top width and height | 11â€“15 mm each |
| key travel | 1â€“5 mm |
| actuation depth | 30â€“90% of travel |
| bottom-out depth | 90â€“110% of declared travel |
| key spring rate | 0.1â€“2.5 N/mm |
| key damping | 0.001â€“0.2 NÂ·s/mm |
| compliant-plunger spring rate | 0.0715â€“0.286 N/mm, derived as 0.5xâ€“2x the unqualified published 0.143 N/mm candidate rate |
| actuation force | 0.2â€“3.0 N |
| fingertip sphere/capsule radius | 1â€“6 mm |
| commanded press depth | 0.5â€“7 mm |
| dwell | 10â€“750 ms |
| approach speed | 2â€“120 mm/s |
| release speed | 2â€“160 mm/s |
| OS repeat delay | 200â€“1,200 ms |
| OS repeat period | 20â€“250 ms |
| phone effective contact radius | 1â€“7 mm |
| phone accepted contact duration | 20â€“500 ms |
| phone long-press threshold | 250â€“1,200 ms |

Landing errors use the frozen MW2UC fixed-approach/calibrated-residual ranges,
including 3â€“4 mm effective regions, random noise `0.001â€“0.002 rad`, fixed-source
magnitude `0.002â€“0.008 rad`, and residual fractions `0â€“0.25` for focused runs.
Broader failure controls retain residual `0.5â€“1.0`.

### Model and outputs

Each keycap is a prismatic joint with explicit travel, spring, damping,
actuation surface, actuation threshold, and bottom-out. The fingertip is a
sphere and a capsule in separate frozen families. The shared compliant tool is
a spring-loaded plunger in series with the key: commanded depth is partitioned
between plunger compression and key travel under force equilibrium. The
unqualified Lee Spring candidate rate is sampled at 0.5x, 1x, and 2x rather
than treated as measured. Contact events drive a simulated OS repeat model;
they never create real host input.

The phone surface models effective contact area and contact duration only. It
does not claim electrostatic touchscreen accuracy.

Output is a per-key press-recipe envelope over depth, dwell, approach, release,
and fingertip radius, with highlighted limiting results for `GRAVE`, `EQUAL`,
`Z`, and `SHIFT`.

### Metrics

- single-actuation probability and confidence bound;
- partial-press, double-actuation, neighbor-contact, bottom-out, and auto-repeat
  rates;
- peak penetration, peak contact force, compliant-plunger compression, effective
  key travel, dwell above actuation, and release completion;
- phone tap, no-tap, multiple-tap, and long-press rates; and
- per-key robust-envelope volume across the declared physical range.

### Pass and stop rules

The exploratory envelope admits a cell only when every sampled landing has one
actuation, zero neighbor contact, zero double actuation, zero repeat, successful
release, finite state, and no solver overflow. Phone cells require exactly one
tap and no long press. A key with no admitted recipe is reported infeasible; its
range is not widened after results. Nonfinite contact state, penetration beyond
the declared bottom-out tolerance, or cross-GPU disagreement stops the run.

### Dependencies and compute estimate

WS1 actuation/event interfaces, MW2UC landing model, and a frozen contact asset
are required. A power smoke determines shard count. Expected compute is 1â€“4 GPU
hours across both RTX 3090s, plus 30â€“90 minutes for admission and summarization.

## Workstream 3: continuous typing motion policy

### Objective

Evaluate direct key-to-key motion without mandatory parking while preserving a
single approach direction, collision clearance, landing accuracy, and verified
device effect.

### Questions answered

- What speed/accuracy frontier is achievable for direct transitions?
- Which directed key pairs require parking or a higher hover?
- How does continuous typing compare with the parked closed loop?

### Inputs and ranges

- Exact simulation catalog frozen after WS1.
- WS2 press envelopes and fingertip families.
- Every ordered key-to-key pair, including repeated-key self transitions.
- Hover height `2â€“30 mm`.
- Cartesian transition speed `10â€“400 mm/s`.
- approach and release speed within the WS2 admitted envelope;
- dwell within the WS2 admitted envelope;
- random noise `0â€“0.002 rad`;
- constant approach-direction backlash `0â€“0.008 rad`; and
- per-key residual correction `0â€“0.25` of the fixed simulated bias.

### Outputs and metrics

Output is a speed-accuracy curve and a pair-policy table selecting direct,
higher-hover, or parked transition for each directed pair. Metrics are verified
characters per minute, miss rate, neighbor-contact rate, collision-screen
rejection rate, path length, transition latency, peak joint speed, and fraction
of pairs requiring park.

### Pass and stop rules

Every admitted transition must pass the existing arm-runtime joint-limit and
collision screens, preserve the single approach direction, remain inside the
selected WS2 landing envelope, and produce exactly one simulated event. No
aggregate rate may hide a failing pair. The recommended exploratory policy is
the fastest policy with zero sampled collision/neighbor contact and with the
predeclared per-pair miss upper bound no worse than the parked reference. If no
continuous class satisfies those rules, the result recommends parking.

### Dependencies and compute estimate

WS1 and WS2 must complete. Expected Warp compute is 2â€“8 GPU hours depending on
catalog cardinality and power analysis. CPU collision admission and summary are
estimated at 1â€“3 hours.

## Workstream 4: fixture drift and recovery

### Objective

Use WS1 fault hooks to measure detection and recovery for displaced fixtures
and incorrect simulated device effects.

### Questions answered

- How quickly does the closed loop detect drift or a wrong effect?
- How many incorrect characters can be committed first?
- Which faults can be corrected by re-observation or backspace, and which must
  abort?

### Inputs and ranges

- Keyboard and phone translations independently swept over `Â±1â€“10 mm` in X/Y.
- In-plane rotation `Â±0.25â€“5 degrees`.
- Single and burst missed presses, wrong keys, and double presses.
- Observation/readback delay `0â€“2 seconds`.
- Drift onset before planning, during travel, immediately before contact, and
  after effect verification.

### Recovery state machine

```text
OBSERVE -> PLAN -> SIMULATE_PRESS -> VERIFY
   |          |          |            |
   +--STOP----+----------+------------+
                     mismatch
                        |
          REOBSERVE -> RELOCALIZE
                        |
          unchanged? retry once : abort/replan
                        |
           wrong committed text -> verified backspace correction
```

Backspace correction is allowed only after readback identifies the exact wrong
effect and the correction itself is independently verified. Ambiguous state
aborts.

### Metrics and decision rules

Metrics are detection latency, committed wrong characters before detection,
relocalization success, correction success, abort correctness, attempts, and
total recovery time. Pass requires every injected deterministic fault to be
detected, no ambiguous state to continue, no more than one wrong character
before detection under per-character verification, and at least 99% recovery
success for faults declared recoverable by the frozen fixture. False recovery
or continuing after an ambiguous readback stops the workstream.

### Dependencies and compute estimate

WS1 must complete; WS2 recipes are used when available but are not required for
state-machine unit tests. Expected CPU time is 30â€“120 minutes and optional Warp
replay is 15â€“60 GPU minutes.

## Workstream 5: calibration procedure budget

### Objective

Estimate how many per-key probes are needed to reduce fixed landing bias to the
MW2UC 10â€“25% residual range and how frequently recalibration would be needed
under a declared drift range.

### Questions answered

- How many probes per key meet the residual target with conservative coverage?
- What total commissioning time follows from the selected probe count?
- Which drift rates imply hourly, daily, or session-based recalibration?

### Inputs and ranges

- Probe counts `1, 2, 3, 5, 8, 13, 21, 34` per key.
- Landing-observation noise `0.1â€“2.0 mm`.
- Outlier probability `0â€“5%` with bounded `1â€“5 mm` magnitude.
- Fixed landing bias corresponding to MW2UC source ranges.
- Linear translational drift `0.01â€“0.5 mm/hour`.
- rotational drift `0.01â€“0.25 degree/hour`.
- Session duration `0.25â€“8 hours`.
- Residual target `10%, 15%, 20%, 25%` of initial fixed landing bias.

### Outputs and metrics

Output is a probe-count table per target family, total commissioning-time range,
and recalibration policy indexed by measured drift. Metrics are residual-bias
coverage, confidence-interval width, outlier rejection, probe failures, total
press count, elapsed simulated commissioning time, and time until the selected
safe-region margin is consumed.

### Pass and stop rules

A probe count is admitted only when the predeclared confidence bound covers the
target residual for every key. The recalibration interval uses the earliest
time any key's conservative margin is exhausted. If no probe count through 34
meets the target, the workstream reports that physical calibration method as
insufficient. It does not relax the target or extrapolate beyond the grid.

### Dependencies and compute estimate

WS2 supplies contact-valid probes; WS4 supplies detection/relocalization
semantics. Expected compute is CPU dominated, 30â€“120 minutes, with less than 30
GPU minutes for optional Warp validation.

## Workstream 6: mid-motion observation in Isaac

### Objective

Render the arm along WS3 trajectories and determine whether target observation
can be admitted while the arm remains in view, without confusing arm-covered
regions with visible targets.

### Questions answered

- Does projected arm geometry conservatively cover the rendered arm mask?
- Which targets remain observable at each trajectory phase?
- Does 9 fps exposure blur invalidate the uncovered-region obstruction check?

### Inputs and ranges

- Frozen WS3 trajectories and pair-policy identities.
- Frozen exact-nadir camera family at 700, 850, and 1,000 mm.
- Frame rate fixed at 9 fps for the primary family.
- Exposure duration `1/120, 1/60, 1/30, 1/15, 1/9 second`.
- Joint-state/capture timestamp offset `0â€“111 ms`.
- Projection dilation derived only as a range from the unmeasured MW2UC joint
  profiles; it is never installed as a physical margin.
- Held-out simulator audit masks disjoint by trajectory, lighting appearance,
  and camera identity from any development tuning.

### Method and outputs

Isaac renders RGB, motion vectors, depth, semantic arm masks, and target masks.
The analytic arm silhouette uses capture-time joint state. Positive arm-mask
overlap is required in the fixture. The obstruction check runs only for target
safe-region pixels outside the dilated projected silhouette; covered targets
must abstain.

Output is a simulation-only mid-motion gate receipt, per-phase observable-target
map, mask-overlap diagnostics, and failure examples. Physical mid-motion use
remains blocked regardless of result.

### Metrics and pass/stop rules

Metrics are projected-mask recall and precision against held-out masks,
safe-region uncovered fraction, covered-target false-clear count, uncovered
obstruction miss/false-stop rates, blur-stratified results, and timestamp-offset
sensitivity. Pass requires positive overlap cases, zero covered-target false
clear, every tested target classified covered or evaluated, held-out projected
mask recall lower bound at least 99%, and the separately frozen residual
obstruction limits on uncovered pixels. Any skipped covered target, source-mask
leakage, or use of perfect simulator masks as runtime inputs stops the gate.

### Dependencies and compute estimate

WS3 trajectories and WS4 recovery behavior must be frozen. Estimated Isaac
render time is 3â€“10 GPU hours after a smoke-derived throughput estimate;
evaluation and mask scoring are estimated at 1â€“3 CPU hours. Isaac work never
runs while a higher-priority GPU campaign is active.

## Workstream 7: first-motion readiness

### Objective

Build a CPU-first rehearsal and evidence package for a future staged hardware
bring-up while preserving zero transport and zero physical authority. The
workstream exercises the exact controller encoding boundary against a guarded
software emulator, predicts telemetry envelopes for stages A-F, tests whether
wrong models and controller faults are detected before simulated contact, and
collects all results in a scenario regression library and human-controlled
readiness checklist.

Simulation results from this workstream cannot authorize a powered session.
The first powered motion requires Jack's explicit approval after the applicable
physical measurements and checklist items are complete.

### Questions answered

- Does the real runtime encoder round-trip the intended joint, sign, magnitude,
  unit, controller ID, and zero convention through an isolated emulator?
- Can emulator mode prove that serial and every other real transport are
  unreachable?
- What measured-position telemetry envelopes should stages A-F produce across
  predeclared latency, response, encoder, backlash, and noise ranges?
- Which wrong-model, controller, environment, and human-entry conditions stop
  before simulated contact, and which remain detection gaps?
- Which exact simulation artifacts and physical measurements are prerequisites
  for each future hardware stage?

### Frozen implementation phases

#### Phase 2 - controller emulator

The emulator accepts only bytes or typed messages emitted by the repository's
existing runtime encoder and controller contract. Servo IDs, message format,
units, direction, and zero convention are derived from those sources. An
undocumented field becomes a named assumption requiring later controller
confirmation; it is never silently guessed.

The real runtime path runs end to end with only the physical transport replaced
by a guarded in-memory transport. A hard guard plus a negative test must prove
that emulator mode cannot import, enumerate, or open a serial port, socket,
device file, or real controller transport.

Unmeasured servo properties remain sampled ranges: command latency, response
lag and settling, encoder resolution, direction-dependent backlash, measured
position noise, and overload or stall behavior. Telemetry reports simulated
measured position rather than echoing commanded position. Fault hooks cover a
dropped message, delayed telemetry, nonresponding servo, stall or overload,
e-stop, and power interruption.

#### Phase 3 - staged bring-up rehearsal

The deterministic stage sequence is:

1. A: one joint, small displacement, low speed;
2. B: all joints to the parked pose;
3. C: noncontact hover above the keyboard;
4. D: one simulated press on a test pad;
5. E: one simulated character; and
6. F: one simulated short string.

Each stage emits a hash-bound predicted telemetry envelope containing joint
position over time, measured-position uncertainty, tool-tip position, collision
and limit diagnostics, expected device effect, and verification result.
Exploratory tolerances are ranges fixed before rehearsal. A stage stops on
wrong direction, magnitude outside its envelope, pose mismatch, collision or
limit warning, landing outside its envelope, wrong simulated key, or any
verification disagreement.

#### Phase 4 - wrong-model drills

Drills inject one condition at a time and declared pairs: link-length error
`1-3 mm`, joint-zero error `0.5-2 degrees`, flipped joint sign, swapped servo
IDs, degree/radian confusion, keyboard translation `2-10 mm`, keyboard rotation
`1-3 degrees`, stale telemetry, dropped connection, and delayed telemetry.
Each receipt records whether detection occurred, the first detecting mechanism,
the first affected stage, and whether detection preceded simulated contact.
An undetected condition is retained as a gap with a proposed new detection
mechanism. No tolerance changes after drill results; any amendment starts a new
pre-result fixture revision.

#### Phase 5 - scenario library and regression runner

One scenario catalog gives every case an ID, category, preconditions, injected
condition, expected outcome (`PROCEED`, `ABSTAIN`, `RETRY`, or `STOP`), and
expected detection mechanism. Categories cover nominal long strings, repeats,
modifier and phone-layer transitions; `GRAVE`, `EQUAL`, `Z`, `SHIFT`, joint
limits, and reach extremes; all controller faults; fixture shift, obstruction,
lighting change, and stale references; hand entry; and every wrong-model drill.
The runner composes the WS1 fault hooks and WS4 recovery machine and exposes a
fixed fast CI subset plus a full nightly identity set.

#### Phase 6 - readiness checklist

`software/docs/FIRST_MOTION_READINESS.md` lists, for stages A-F, the required
simulation artifact hashes, physical measurements, no-go criteria, abort
procedure, and explicit human approval. Every item is labeled satisfied,
blocked on simulation, or blocked on physical measurement. The checklist
records status; it cannot create an execution permit or authorize transport.

### Inputs and parameter ranges

- Existing runtime command encoder, controller contract, joint map, unit and
  frame contracts, pinned URDF, collision kernel, and simulator-only transport.
- WS1 semantic twin and fault hooks; WS4 recovery state machine; WS5 calibration
  findings; candidate collision intake retained only as exploratory evidence.
- Servo latency, lag, settling, resolution, backlash, noise, speed, acceleration,
  and overload thresholds are fixture ranges derived from repository bounds or
  explicitly labeled assumptions. No range endpoint becomes a nominal hardware
  constant.
- Stage displacement, speed, duration, and telemetry tolerance are separately
  frozen ranges. Phase 2 does not begin until these ranges, protocol bindings,
  random seeds, fault identities, metrics, and stop rules are hash-bound.
- WS2 may later replace the provisional contact tool. Any replacement creates a
  new collision-candidate and telemetry-envelope revision rather than rewriting
  prior evidence.

### Outputs

- A transport-isolated controller emulator and exact encoder/decoder conformance
  receipt.
- Per-stage A-F scripts and predicted telemetry-envelope artifacts.
- A wrong-model drill matrix with precontact-detection results and retained gaps.
- A versioned scenario catalog, fast CI runner, full nightly runner, and
  category-level summary.
- `FIRST_MOTION_READINESS.md` with artifact hashes and physical dependencies.
- One compact external evidence manifest and verified backup inventory per
  phase, including zero-authority counters and exact environment versions.

### Metrics

- Exact command-byte acceptance and round-trip field agreement by joint.
- Servo-ID coverage, sign, magnitude, unit, and zero mismatches, plus false
  telemetry agreement between commanded and simulated measured state.
- Transport-open attempts, all of which must remain zero.
- Stage envelope coverage, limit or collision warnings, predicted landing error,
  device-effect agreement, and verification agreement.
- Fault and wrong-model detection rate, first-detection stage, precontact
  detection rate, and undetected-gap count.
- Scenario pass rate and false acceptance by category; recovery success and
  wrong characters committed before detection.
- Hardware writes, physical movements, real commands, permits, transports, and
  physical authority, all required to remain zero.

### Pass and stop rules

Phase 2 passes only with 100% exact protocol round-trip across every joint and
the all-joint message, correct measured-position telemetry semantics, detection
of every deterministic controller fault, and zero real-transport opens. Any
undocumented protocol detail is a blocker for the affected claim.

Phase 3 passes only when each stage remains inside every frozen envelope and
produces the expected independent simulated effect. A later stage cannot run
after an earlier no-go result. Phase 4 reports gaps rather than claiming pass
when any drill reaches simulated contact before detection. Phase 5 requires the
fixed CI and full identity sets to match their declared outcomes with zero false
acceptance. Phase 6 is complete only as a checklist artifact; every physical
measurement and human-approval row remains blocked until supplied outside this
simulation program.

Any serial, socket, or device open; real controller discovery; hardware write;
physical movement; command or permit creation; transport authorization; silent
protocol guess; post-result tolerance change; or physical-readiness claim stops
the workstream and preserves the attempt as failed evidence.

### Dependencies and compute estimate

Phases 2-5 are CPU-only and may proceed while the no-preemption residual job
runs. Phase 3 consumes Phase 2; Phase 4 consumes the unchanged Phase 3
envelopes; Phase 5 consumes Phases 2-4 plus WS1 and WS4 hooks; Phase 6 summarizes
all preceding evidence. WS2's later nominal tool selection triggers a bounded
artifact revision. Estimated CPU time is 1-3 hours for emulator implementation
and tests, 1-4 hours for staged and wrong-model sweeps, and under 1 hour for
catalog regression and checklist generation. No GPU allocation is required.

## Ordered successor amendment — 2026-10-05

Before any successor results, the immediate sequence is frozen as:

1. execute the explicit 110 mm total-length, 3 mm-radius keyboard profile;
2. run a bounded release-timing matrix with complete reset and an upper dwell
   limit below every sampled OS auto-repeat delay;
3. run WS2 Stage A and later refinement with compliant-plunger stiffness as a
   declared range, reporting keyboard outcomes by tool geometry;
4. report phone capacitive tap/long-press outcomes separately and use them only
   to decide whether one simulated contact geometry remains plausible;
5. continue to WS3 continuous typing; and
6. execute WS4 recovery tests.

The release matrix precedes the large search so an episode that is too short to
observe reset, or a dwell long enough to create OS repeat, cannot silently
distort Stage A. The existing failed short-release evidence remains unchanged.

The priority physical measurement queue is: servo repeatability/backlash; chosen
landing-sensor noise from the ADB touchscreen or tray touch pad; compliant tool
spring rate/force-travel behavior together with fingertip radius and compliance;
key travel/actuation force; phone minimum conductive contact area; and B0477
intrinsics, delivered-frame noise, lighting, and board/arm calibration.

## Program execution and reporting protocol

For each workstream:

1. verify higher-priority dependencies and GPU/CPU/disk availability;
2. add a narrow active claim and commit it;
3. commit the fixture, manifest schema, metrics, and rules before execution;
4. execute a bounded smoke and visually or numerically audit its semantics;
5. preserve failed smoke evidence and amend implementation only when the frozen
   contract was violated;
6. execute independent device shards without combining their raw identities;
7. admit exact allowlisted outputs, compare cross-GPU numerical payloads, and
   create the second verified backup;
8. append the evidence ledger and update only the simulation-lane workplan row;
9. run maintained checks, commit, and push; and
10. report:
   - what the workstream showed and why it matters;
   - key numbers;
   - preserved failures;
   - the resulting hardware-plan change; and
   - the next dependency.

If a required answer can only come from a physical measurement, the program
stops at that dependency and asks the operator before any physical procedure.

## Completion definition

The program completes when all seven workstreams have final simulation receipts,
all external evidence has two verified copies, failures remain visible, and the
shared workplan identifies every remaining physical dependency. Completion does
not authorize hardware use. It produces a prioritized measurement and design
plan for later commissioning.
