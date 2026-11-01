# Isaac Sim learned motion generation plan

- **Document status:** Active implementation plan
- **Primary issue:** [#190 - pinned Isaac Sim simulation oracle](https://github.com/j-webtek/tactevra/issues/190)
- **Owners:** Simulation, arm/runtime, and AI/model workstreams
- **Started:** 2026-11-01
- **Method reference:** [ScheduleGen](https://arxiv.org/abs/2610.39429)
- **Authority:** Simulation and learning guidance only. This plan grants no
  controller, hardware, motion, contact, calibration, or release authority.

## Why this plan exists

Tactevra has accumulated substantial geometry, kinematic, collision, target,
camera, schedule, and execution-contract work. Its retained Isaac schedule
replay nevertheless uses joint teleportation and records zero physics steps.
That result is valuable FK evidence, but it does not test drives, inertia,
settling, contact, or realistic movement.

The next simulation phase therefore changes the emphasis from proving that a
candidate is well-formed to generating and improving physically simulated
motion. The immediate goal is not autonomous hardware control. It is a
reproducible physics-stepped environment that can:

1. replay Tactevra motion through drives rather than teleportation;
2. vary uncertain dynamics and installation parameters explicitly;
3. generate successful keyboard-motion demonstrations automatically;
4. train and evaluate bounded motion policies from those demonstrations; and
5. later fit simulator parameters from separately authorized physical traces.

## ScheduleGen adaptation

ScheduleGen generates imitation-learning data by preserving object-relative
contact skills, replanning connecting motions, enforcing temporal and collision
constraints, replaying candidates through simulation, and retaining successful
rollouts. Tactevra has one arm, so it does not initially need ScheduleGen's
multi-arm MILP. The useful abstraction is its separation between reusable
contact skills and newly planned free-space transitions.

For keyboard use, one contact action becomes this ordered skill schedule:

```text
OBSERVE
  -> MOVE_TO_SAFE_HOVER
  -> ALIGN
  -> DESCEND
  -> PRESS
  -> HOLD
  -> RELEASE
  -> RETREAT
  -> TRANSITION_TO_NEXT_KEY
```

The scheduler must preserve requested key order, require retreat before lateral
travel, prevent a new descent before the preceding key has released, and allow
timing optimization only inside those constraints. A later multi-arm system can
extend the same representation with ScheduleGen-style precedence,
synchronization, and disjunctive collision constraints.

## Inputs available now

The first implementation reuses current governed assets rather than requesting
another broad manual measurement campaign:

- selected Isaac Sim 6.1.0.0 headless runner and dual-RTX-3090 host profile;
- governed RoArm-M3 USD import and FK parity evidence;
- official-mesh collision-development artifacts;
- RC03 board, keyboard envelope, six fiducials, and per-key target geometry;
- fixed-camera and board layout records;
- attachment-separated bare-jaw and contact-tool profiles;
- the retained 133-sample `H, H, 1, PERIOD` schedule;
- deterministic IK, trajectory, collision, lifecycle, and command-preview code;
- 46 key regions and the elevated-keyboard-plane study.

These inputs are sufficient for provisional simulation campaigns. They are not
a validated dynamic twin and do not qualify physical movement.

## Evidence classes

Every campaign parameter must use exactly one provenance class:

| Class | Meaning | Permitted use |
| --- | --- | --- |
| `MEASURED` | Bound to a retained physical measurement and method | Simulation and later qualification review |
| `DERIVED` | Calculated from named measured or upstream sources | Simulation with derivation retained |
| `UPSTREAM` | Bound to a pinned manufacturer or model artifact | Simulation subject to upstream limitations |
| `PROVISIONAL_RANGE` | Explicit bounded assumption or sweep range | Sensitivity studies and domain randomization only |
| `UNKNOWN` | No usable source or justified range | Blocks affected rollout or success claim |

An uncertain value must not be collapsed into one falsely precise nominal.
Training campaigns sample `PROVISIONAL_RANGE` values and preserve the sampled
values and random seed in each rollout receipt.

## Two coupled learning loops

### Loop A - dynamic system identification

The simulator needs better drive and dynamic parameters. Initial campaigns use
bounded provisional ranges for:

- per-link mass, center of mass, and inertia;
- joint stiffness, damping, friction, armature, and command delay;
- controller update timing and simulation substeps;
- base, board, keyboard, and tool placement uncertainty;
- tool length, angular error, and compliance; and
- key travel, spring rate, damping, friction, and release behavior.

After a separately authorized physical noncontact campaign exists, the fitting
loop compares commanded targets, controller feedback, and camera-observed TCP
motion with simulator rollouts. It fits the smallest identifiable parameter set
first and validates it against held-out physical trajectories. Passive endpoint
identity evidence alone cannot identify dynamics; informative motion and
accurate timestamps are required.

The pinned 6.1 runner remains unchanged until a separate toolchain decision.
Newer Isaac system-identification tooling may inform the record and fitting
format, but it does not silently replace the selected runtime.

### Loop B - demonstration generation and imitation learning

For each sampled simulated workcell:

1. select a governed target or short ordered target sequence;
2. adapt the reusable hover/contact skill to each target frame;
3. plan collision-screened connecting motion;
4. build the phase schedule and timing constraints;
5. execute it through physics with a fixed seed and explicit settings;
6. classify contact, activation, release, collision, tracking, and settling;
7. reject failures with named reasons; and
8. retain successful observations and actions as a training demonstration.

The first learned policy is state based:

```text
joint state + target pose + skill phase
  -> bounded next joint target or trajectory residual
```

Only after the state policy passes held-out randomized simulation should a
vision policy consume fixed-camera pixels. Simulator truth remains outside the
model-facing observation process and is used only for labels and scoring.

The learned component is always a proposal generator. Deterministic target
containment, IK, joint limits, collision screening, attachment profiles,
trajectory sealing, and execution authority remain outside the policy.

## Work packages

### LM0 - drive-controlled physics baseline

Implementation status: the LM0A gravity-off control-path baseline is now
implemented by `drive_controlled_hover_probe.py` with its provisional dynamic
profile. A native Isaac 6.1 run completed 270 physics steps with zero
post-initialization teleports and settled the retained `H` hover below the
`1e-3 rad` joint-error threshold. Three independent native processes produced
byte-identical receipts at `0.00020575953078338927 rad` final maximum joint
error and zero observed drift. `drive_controlled_hover_campaign.py` now checks
and seals that repeatability result. The first LM0B gravity-on characterization
also reaches the same noncontact hover through 270 physics steps, but all
centers of mass remain placeholder link origins. It therefore validates only
the gravity-on execution path; geometry-derived mass properties and subsequent
physical-trace fitting remain required before any system-identification claim.
The next LM0B slice now replaces those origin placeholders with source-bound
centers and principal inertias derived from the official link meshes. Its
native gravity-on hover passes at `2.2443705648411694e-05 rad` maximum final
joint error. This is a stronger simulation prior, not a physical fit: internal
servo, electronics, and fastener mass distributions remain unmeasured.
That prior now also drives a retained four-pose trajectory through `PARK`,
`H`, `1`, and `PERIOD`. The run records 960 consecutive physics samples and
emits a CSV read back successfully by the installed Isaac Sim 6.1 SysID
loader. This establishes the simulation telemetry and optimizer-input path. It
does not identify physical mass, inertia, drive, or raw T1051 load semantics;
those remain later LM0B measurement and calibration work.
The imported USD's invalid mass placeholders and zero authored drive gains are
now replaced only in a hashed derived SysID stage. NVIDIA's default preflight
then reports 8 identifiable parameters instead of zero, exposing the remaining
work directly: narrow fitting to the excited stiffness/damping terms, define a
validation holdout, and add wrist/gripper excitation before broadening the
parameter space.
That narrow rehearsal is now implemented. The official Isaac schema generates
and round-trips a bounded eight-parameter run spec: stiffness and damping for
DOF indices `0..3`, trained on the `H` and `1` motion segments with `PERIOD`
held out for validation. A three-iteration native solve accepted one finite
candidate, reported all eight selected terms identifiable, hit no parameter
bounds, and evaluated the held-out segment. It intentionally wrote neither
parameters nor the stage. Its assessment remains `warn` because the simulated
trajectory has only one excitation family, stiffness/damping columns are
correlated, DOF indices `4..5` remain weakly excited, and no calibrated
link-side torque exists. The next LM0B experiment is therefore independent
wrist/gripper excitation and, separately, a physically calibrated torque
channel before inertial fitting; the provisional candidate is not promoted to
the simulator prior yet.
The independent-excitation follow-up now drives all six joints separately over
2,160 physics samples. Isaac's telemetry-quality report no longer identifies
any weak joint, so the wrist/gripper coverage blocker is cleared for the next
bounded preflight. The run also measures an approximately `83 ms` common lag
and an outlying DOF-4 residual lag. Command alignment and actuator-delay
separation must therefore precede the expanded solve; otherwise the optimizer
would incorrectly absorb timing error into drive gains.
The follow-up independent chirp resolves that ambiguity: every joint's
command/response correlation exceeds `0.999`, the common lag is
`0.0866067950984508 s`, and residual spread is below `0.25` sample. The earlier
DOF-4 one-cycle offset was therefore a fixed-frequency alias, not evidence of a
large wrist-specific delay. The next expanded preflight may apply the measured
common alignment while keeping per-joint actuator delay disabled.
That aligned expanded rehearsal is now complete. It fits stiffness and damping
for all six joints against five independent chirp chunks and validates on the
sixth. All 12 selected terms are identifiable, the telemetry-quality check has
no weak joints, and the accepted candidate reaches `0.028078358620405197`
training normalized cost and `0.0036708096663157145` held-out normalized cost.
The solve writes neither parameters nor USD. Its `warn` assessment and
simulation-only provenance deliberately prevent promotion: the next evidence
gain must come from a distinct validation excitation family and, later, a
calibrated physical trace rather than additional optimization on the same
chirp family.
The distinct-family check is now retained: all six chirp chunks train the
12-term model while all six independent-sine chunks are validation-only. The
two bounded optimizer updates were rejected and the unchanged baseline was
selected, preventing a false improvement claim. Its sine validation cost is
`0.028266899857992005` versus `0.024019965901970863` on chirp training
(`1.176808492291518` ratio), with no weak joints and two excitation families
recognized by Isaac. This clears the same-family validation limitation while
showing that further simulation-only optimizer iterations are not the next
information gain. The next identification improvement requires calibrated
physical command/feedback timing and telemetry; learning-policy work may use
the baseline as a domain-randomization center, not as a physical truth value.

Replay the retained schedule through articulation position targets and physics
steps. Initialization may set the starting configuration once; all subsequent
motion must result from drives and stepping.

First acceptance target: the existing noncontact `H` hover prefix.

Required receipt fields include:

- source schedule and asset identities;
- physics timestep, substeps, solver, seed, and device;
- complete dynamic-profile identity and provenance classes;
- desired and observed joint traces;
- velocity, effort, saturation, and limit observations;
- TCP tracking error and settling time;
- collision and contact event sequence; and
- explicit zero hardware access and zero wire commands.

**Exit gate**

- `physics_steps > 0`;
- no teleport after initialization;
- all controlled joints have exactly one control owner;
- the prefix reaches and settles at the `H` hover;
- no unintended contact or collision occurs;
- repeated identical runs preserve the categorical result and remain inside
  declared numeric drift bounds; and
- all provisional dynamics remain visibly provisional.

### LM1 - representative keyboard mechanics

Add explicit mechanics for `H`, `1`, `SPACE`, `ENTER`, and one punctuation
key. Model keycap geometry, travel, activation, release, spring/damping, and
neighboring-key contact.

The initial ARM-185 contract derives all five representative regions and their
neighbor guards from the governed nominal keyboard profile. It supplies bounded
synthetic travel, activation, release, stiffness, damping, and mass priors; a
geometry-derived activation state machine; and deterministic positive and
negative cases.

ARM-186 now clears the first native LM1 increment. A headless Isaac 6.1 scene
replayed a smooth 600-sample virtual-tip trajectory against a prismatic `H` key
at 120 Hz. Native mechanism state produced one accepted `H` activation at
`2.69999820739031 mm` maximum compression and returned to effectively zero
compression. The receipt hash is
`9583a62f8c89220f7211acff3d449c9def6f21ac87146f309ad843c9cbc88768`,
retained externally under
`C:\IsaacSim\artifacts\issue190\lm1-native-h-key-005`. No acceptance threshold
was relaxed. The replay remains provisional: it isolates a virtual tip and one
key, disables gravity to represent the keyboard's preloaded return mechanism,
and grants zero physical or motion authority. The next LM1 increment must bind
the same key and evaluator to the drive-controlled robot TCP.

**Exit gate**

- activation derives from simulated mechanism state, never target name;
- shallow, off-center, excessive, double, neighboring, and incomplete-release
  cases reject distinctly;
- every parameter has provenance and uncertainty bounds; and
- no result is described as physical key qualification.

### LM2 - skill and schedule generator

Represent the ordered keyboard phases as immutable object-relative skills.
Adapt them across target frames, insert planned transitions, and retain a
machine-checkable mapping from semantic action through every generated sample.

**Exit gate**

- requested character order and repetitions are preserved exactly;
- descent cannot begin outside the selected key region;
- lateral travel cannot begin before retreat and release;
- collision or IK failure rejects the candidate; and
- successful replay, not planner optimism, decides dataset admission.

### LM3 - randomized demonstration campaign

Generate parallel Isaac environments over declared installation and physics
ranges. Retain compact manifests in Git and large trajectory/image datasets
under the external-artifact policy.

**Exit gate**

- train, validation, and test seeds and scene identities are disjoint;
- interrupted or incomplete shards cannot be counted as successes;
- every retained demonstration can be replayed from its manifest;
- failure rates are reported by reason and parameter region; and
- a campaign cannot hide broad failure behind successful-sample filtering.

### LM4 - state-policy training

Train a behavior-cloning baseline from joint/proprioceptive observations,
target pose, and phase. Compare it with the deterministic planner on identical
held-out resets.

**Exit gate**

- the policy never emits wire commands or authority;
- held-out success, collision, contact, release, settling, and abstention rates
  are reported independently;
- the deterministic planner remains the fallback and safety boundary; and
- policy proposals that fail existing gates are rejected without retry.

### LM5 - vision-conditioned policy

Render the selected fixed-camera observation with lighting, blur, glare,
occlusion, placement, and optics variations. Train only on pixels and allowed
metadata; keep ground truth in a separate scoring process.

**Exit gate**

- no simulator-truth leakage reaches inference;
- evaluation uses held-out scene and randomization identities;
- vision failure is separated from planning or physics failure; and
- the policy abstains when target uncertainty exceeds the applicable safe
  region.

### LM6 - physical trace fitting and staged transfer

After separate authorization and existing commissioning gates, acquire a small
noncontact physical trace set, fit dynamic parameters, and validate against a
held-out trace. Contact fitting begins only after noncontact tracking and
clearance are accepted.

Transfer sequence:

1. shadow proposal only;
2. one supervised noncontact hover;
3. camera-measured TCP comparison;
4. one representative-key contact;
5. independent character-effect verification; and
6. expansion to short ordered strings only after reviewed repeatability.

## Metrics

Every generation or policy report includes at least:

- generation attempts and successful demonstrations;
- success rate before filtering;
- failure counts by IK, collision, contact, activation, release, tracking,
  settling, timeout, and infrastructure reason;
- minimum clearance and maximum penetration;
- maximum/RMS joint and TCP tracking error;
- peak effort and saturation counts;
- key-center and neighboring-key contact distances;
- completion time and path length;
- held-out policy success and abstention rates; and
- categorical and numeric repeatability across identical seeds.

Simulation success and learned-policy success remain separate metrics, as in
ScheduleGen. Neither is a physical success rate.

## Immediate implementation order

1. **ARM-173 / LM0 contract and runner:** add a bounded dynamic-profile and
   physics-replay receipt; implement drive-controlled `H` hover replay.
2. **LM0 retained run:** execute repeated headless Isaac runs and classify
   tracking, settling, and contact behavior.
3. **LM1 mechanics:** native representative-key physics and an isolated `H`
   press are complete; next integrate the drive-controlled robot TCP.
4. **LM2 generator:** adapt the `H` skill to the representative target set.
5. **LM3 dataset smoke:** generate a small, reproducible randomized dataset.
6. **LM4 baseline:** train and evaluate a state-based imitation policy.
7. Expand only after each predecessor produces reviewable evidence.

## Completion criterion

This plan has achieved its purpose when Tactevra can reproducibly generate a
physics-validated demonstration dataset from measured/provisional workcell
inputs, train a bounded policy that improves or complements deterministic
planning on held-out simulation, and use separately authorized physical traces
to reduce—not conceal—the sim-to-real uncertainty. It is not complete merely
because an Isaac scene renders, a policy loss decreases, or one simulated key
activates.

