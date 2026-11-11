# Isaac Sim learned motion generation plan

The durable end-state, qualification ladder, evidence rules, and sim-to-real
promotion criteria are defined in
[SIM_TO_REAL_TYPING_GOAL.md](SIM_TO_REAL_TYPING_GOAL.md). This document owns the
detailed Isaac, dataset, policy, and system-identification progression toward
that objective.

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

ARM-207 binds that mechanism to the selected full robot route and proves native
contact, but fails on about `3.78 mm` peak compression and incomplete release.
ARM-208 then closes the first feedback loop: it derives smaller contact targets
from that receipt, adds a two-second retract hold, enforces a `0.05 rad`
tracking limit, and replays the unchanged evaluator. Tracking and every
fixed-root check pass, but peak compression remains about `3.66 mm` and release
still fails. The trace shows the missing model explicitly: the nominal H hover
already preloads the key by about `2.6 mm`, so timing cannot solve the geometry
error. The next LM1 increment must lift and requalify the H approach, hover,
and retract targets from the retained native trace before another contact
replay. It must not weaken mechanics limits or grant physical authority.

ARM-209 supplies that lifted path. It reuses sequence 33, where the retained
trace proves about `0.919 mm` of tool/key clearance and no compression, for the
H hover and retract geometry. Both native H actions now activate once and
release completely; all 133 root checks and the `0.05 rad` tracking gate pass.
The unchanged mechanics evaluator still blocks peaks near `3.542 mm`, about
`0.043 mm` beyond nominal travel. The next LM1 update is therefore a bounded
contact-depth refinement from the ARM-209 receipt, not another release-timing
or hover-geometry change.

ARM-210 applies that contact-only refinement and passes. The lifted geometry
is unchanged; only contact sequences 35 and 38 are interpolated from the
no-contact anchor. Both H actions activate exactly once, peak at about
`2.744` and `2.731 mm`, and fully release. All 133 fixed-root checks pass and
tracking remains below `0.05 rad`. This closes the representative H replay
loop in simulation. LM2 must now retain this skill as a governed demonstration
and generalize it to the representative target set without granting physical
authority or treating one-key success as installed qualification.

ARM-187 establishes the robot-TCP/mechanics handoff. The retained shared-emitter
schedule terminates `H` CONTACT at the `21.0 mm` key rest plane, so it commands
no mechanism compression. A hash-bound, zero-authority contract now rejects
that endpoint and derives the next governed Cartesian input:
`[216.55, 154.0, 18.3] mm`, corresponding to the `2.7 mm` stroke accepted by
the ARM-186 native replay. This does not qualify IK or contact. It makes those
missing steps explicit: regenerate the schedule, pass the existing IK and
collision gates, then replay the drive-controlled robot TCP against the same
native key and evaluator.

ARM-188 completes the Cartesian regeneration step without laundering the old
IK result. A hash-bound request preserves all 133 source timestamps and
semantic samples, changes only the two `H` CONTACT endpoints (sequences `35`
and `38`) to `[216.55, 154.0, 18.3] mm`, and excludes every source joint
position. The external request hash is
`0237336223feca90f830c4162cb6cac1606f0438636802e8aa082f65c08601f7`.
Its `READY_FOR_IK_QUALIFICATION` status means the canonical IK and collision
gates are now the next dependency; it does not claim reachability or contact.

ARM-189 completes the canonical IK and discrete-continuity screen for that
regenerated schedule. All 133 samples pass under the hash-bound retained
virtual-board transform and `120 mm` keyboard tool. The modified `H` contacts
at sequences `35` and `38` each reach `[216.55, 154.0, 18.3] mm` with
`0.000119 mm` position error, `0.153653` minimum normalized joint margin,
`0.037258 rad` maximum adjacent-joint delta, and full local solver-weighted
Jacobian column rank. The zero-authority external receipt is
`C:\IsaacSim\artifacts\issue190\lm1-h-ik-screen-001\receipt.json`, SHA-256
`278ef3ff6d5ca94150e4e2423e68ed9dd736300713a471621bf6b4badcd678f2`.
Its `READY_FOR_COLLISION_QUALIFICATION` status proves virtual reachability and
discrete continuity only. Exact joint results must next pass installed-geometry
collision screening before the drive-controlled robot TCP is replayed against
the native key mechanism.

ARM-190 now creates the exact native collision-diagnostic handoff. It binds the
ARM-189 receipt, the selected Isaac 6.1 runner, and the retained exploratory
collision candidate, then expands 133 IK endpoints to 149 configurations with
at most `0.05 rad` change per joint. The external request at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-request-001\request.json` has
SHA-256 `4288f11667ac1713536ca808e1608150f2241ca7dfdaea41b75c307d14344dbd`.
This closes the schedule-to-collision-request plumbing, not the collision gate:
the candidate is uninstalled, several attachment/environment bodies remain
unbound, and bounded samples do not prove continuous clearance. The next run
must retain per-sample pair evidence from the selected Isaac runner while
keeping native contact replay denied.

ARM-191 executes that handoff in the pinned Isaac 6.1 runtime without crossing
the zero-authority boundary. A pre-start admission binds the request, IK
receipt, exploratory geometry, virtual placement, import receipt, robot USD,
and articulation order. PhysX then evaluates all 149 bounded configurations
and retains each observed body pair. The canonical diagnostic receipt at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-diagnostic-002\receipt.json`
has SHA-256
`68ba26f6b99c7a5b4a2167f1227324eef8fb7d11422b0521f07d6c3954aee59c`.
It records overlaps in all 149 samples and 18 unique pairs. Five are persistent
adjacent-link pairs; the remaining configuration-dependent workcell pairs show
that the conservative uninstalled candidate and station-envelope vocabulary
cannot yet serve as clearance geometry. The next dependency is a reviewed
adjacent-pair policy plus separation of physical workcell solids from planning
envelopes, followed by a fresh diagnostic. Clamp, cable, ranged tool, and
arm-camera coverage still block installed collision qualification, and no
continuous or physical gate is promoted.

ARM-192 converts the 18 retained pairs into a hash-bound but unapplied policy
proposal. Its external artifact at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-proposal-001\proposal.json`
has canonical SHA-256
`c9665938e0ab5d138079203fc5665333ec137a796ad7c2369070cc8c22793e61`.
Five directly connected robot pairs are proposed for kinematic-neighbor
exclusion, seven board/device pairs remain physical collision observations,
and six station pairs remain planning-envelope route blockers. No pair is
silently discarded: the proposal is review-required, `policy_applied` is
false, and installed/continuous/physical gates remain denied. The next stage
must review this exact proposal, bind the accepted policy hash into a new
diagnostic request, and rerun the native overlap evidence.

ARM-193 completes that review-bound rerun without suppressing source evidence.
The accepted diagnostic-only policy SHA-256 is
`ede8b946a85e754eec1698365bd16bec3b332d5d6cb8c9ef4634a9b61abeca87`;
the policy-bound v2 request SHA-256 is
`0eff9c8170d9ddf78af3bd96880acc43c8d96a4f875b35199aa3950ccb13e83b`.
The selected Isaac 6.1 replay retains all 18 raw pairs at all 149 evaluated
configurations, classifies the five reviewed adjacent-link pairs as diagnostic
reporting exclusions, and leaves seven physical-solid plus six station-envelope
pairs as blockers. No pair remains unreviewed. The external v2 receipt at
`C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-diagnostic-001\receipt.json`
has canonical SHA-256
`8e511e3203984fea32b9726d5cd37c465369b0ecc8d632f60fd71b0b1e327b4d`
and status `DIAGNOSTIC_BLOCKERS_OBSERVED`. This establishes a trustworthy
classification baseline; it does not qualify collision clearance. The next
dependency is correcting the exploratory physical geometry and planning route,
then separately adding the missing installed bodies and continuous-segment
screening before robot/key contact replay.

ARM-194 turns that classified baseline into exact trajectory-localized repair
evidence. The external unapplied report at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-blocker-localization-001\proposal.json`
has canonical SHA-256
`8a3c8bb8df99c22383efb618d43f9d0e32b9f8aec443ce9525ef5393f2a0198b`.
It binds every one of the 13 remaining blocker pairs to the relevant subset of
the 149 bounded collision samples and, through each sample's source segment,
to the original Cartesian phase, action, target, and expected TCP pose. The
seven physical-solid pairs involve the gripper and links 2 through 5; the six
planning-envelope pairs involve the gripper, link 4, link 5, and the two
keyboard station regions. No pair is unreviewed. Most observations occur in
`TRANSIT`; station-envelope observations cluster around the `H` and `1`
portions, whereas board-solid observations extend through later `1` and
`PERIOD` portions.

The report applies no remediation and promotes no gate. It establishes two
separate next experiments: first refine the conservative physical robot-link
geometry and retest actual solid overlaps; separately remove station planning
envelopes from PhysX-solid semantics and enforce them through an explicit route
predicate. Only a fresh policy-bound native replay may show whether either
correction cleared its blocker class. Installed attachment coverage and
continuous-segment screening remain later prerequisites.

ARM-195 extends the exact same native replay with primitive-level attribution.
The external v3 receipt at
`C:\IsaacSim\artifacts\issue190\lm1-h-primitive-attributed-collision-diagnostic-001\receipt.json`
has canonical SHA-256
`7f3941b7e6538d57bdb8cdfd2fa74da05973eb8649901a746f0ca0f2f44a3741`.
It preserves the body-level result exactly: 149 samples, 18 raw pairs, five
accepted adjacent-link reporting exclusions, seven physical-solid blockers,
six planning-envelope blockers, and zero unreviewed pairs. Its additive v3
evidence identifies 27 raw primitive pairs. The derived unapplied report at
`C:\IsaacSim\artifacts\issue190\lm1-h-primitive-blocker-localization-001\proposal.json`
has canonical SHA-256
`c1050eea1c9f049629f7126a2d1d7b0371b4653edd53faa7ff31ad832e4325a7`
and attributes the 13 blocker body pairs to 20 blocker primitive pairs and
their exact sample ranges.

Every primitive belonging to an implicated multi-box robot body participates:
both link 2 boxes, all four link 3 boxes, and both link 4 boxes. Link 5 and the
gripper each currently have one box, and each participates as well. The
evidence therefore rejects a simple stray-primitive deletion. The next
physical-solid experiment must source-preservingly refine the entire
conservative body representation, beginning with link 5's whole-link fallback
box, then rerun the same hash-bound diagnostic. Station-envelope semantics
remain a separate explicit route-predicate change. ARM-195 changes no geometry,
route, policy, authority, or gate and grants no hardware action.

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

ARM-218 implements this boundary as a small simulation smoke contract. The compiler
consumes the hash-verified ARM-217 four-key result and emits `24` deterministic
episodes: `12` train, `8` validation, and `4` test. Every episode has a unique
seed and scene identity, binds one admitted plan and native receipt, and records
all provisional mechanics and placement parameters inside declared ranges.
The strict aggregator requires one complete receipt for every attempted
episode, retains failures, and reports them by reason and stiffness region.
Missing, extra, incomplete, relabelled, tampered, or undeclared inputs fail
closed. The retained pre-execution manifest is external at
`C:\IsaacSim\artifacts\issue190\arm218-randomized-demonstration-smoke-001\campaign.json`
with canonical SHA-256
`6b38bbc2e0625e83283666c2d94b90ebe05ec5e442426f7b09c3245fc84c22f1`.
It grants no hardware authority. A single-episode native worker validates
the selected episode against that campaign and its ARM-217 plan/receipt lineage,
reuses the existing drive-controlled robot/key replay, applies all six declared
mechanics and keyboard-pose perturbations, content-addresses the retained JSONL
trajectory, and emits one complete PASS/FAIL receipt without automatic retry.
Process interruption remains incomplete by construction.

All `24` precommitted episodes completed exactly once and retained `1,416`
native samples each. The strict aggregate is
`COMPLETE_RANDOMIZED_DEMONSTRATION_SMOKE`, with `18` passes and `6` completed
`MECHANICS_REJECTION` failures. Train reports `9` pass / `3` fail, validation
`6` / `2`, and test `3` / `1`. Four failures occur in the high-stiffness region
and two in the mid-stiffness region; none is an execution, fixed-root, tracking,
IK, or collision-infrastructure failure. The canonical result SHA-256 is
`6966084caa88cd5397dc851c4892d4ffa4acc7b5923192756e01d0fdf9bc3e3f`.

The first retained worker failure demonstrates why failures stay in the dataset.
`episode-edda9b249c011866102b` completed with `1,416` content-addressed native
samples, a passing fixed-root invariant, and acceptable joint tracking, but the
randomized target interaction failed unchanged mechanics acceptance. Its
`MECHANICS_REJECTION` receipt is therefore retained as a completed failed
attempt rather than discarded or retried. This closes the small LM3 smoke gate,
not statistical coverage, policy training, physical qualification, or hardware
authority. LM4 state-policy dataset assembly and baseline training are next.

### LM4 - state-policy training

Train a behavior-cloning baseline from joint/proprioceptive observations,
target pose, and phase. Compare it with the deterministic planner on identical
held-out resets.

The original ARM-218 smoke trajectories prove mechanics and denominator
handling, but their retained rows contain contact geometry rather than
per-step proprioception and must not be presented as behavior-cloning input.
ARM-219 therefore versions an LM4 trajectory row and records, at every physics
step, the observed six-joint positions and velocities, commanded six-joint
target, target identity, motion phase, action/sequence identity, and existing
tip/key contact geometry. The episode receipt binds that trajectory schema and
governed joint order.

The fresh state-policy corpus now contains all `24` attempted episodes and
`33,984` validated rows. Its deterministic dataset manifest keeps the `6`
failed episodes as rejection evidence, reserves passing validation/test rows
for evaluation, and fits 23-feature normalization only from the `12,744`
passing training rows. The manifest hash is
`a5870894ce6e734542ea2cef5bef079b8ee73a147c3a1d528eff5e0e521479f1`.
This closes dataset assembly only; it does not by itself establish a learned
baseline or held-out performance.

The first deterministic linear ridge baseline is now fit with
`ridge_lambda=0.001`, no random initialization, and no stochastic operations.
Two complete fits produced identical model SHA-256
`e281114e62fdaca603dbabbb8b0ca00891648bf6929c141fa100fe3919b5d45c`.
It reports `0.0002683071 rad` training aggregate MAE and `0.0143845465 rad`
held-out aggregate MAE across `12,744` rows in each role. This is an honest
action-imitation result, not a physics success claim: proposal replay through
the unchanged collision, mechanics, tracking, and fixed-root gates remains the
next boundary.

The held-out proposal campaign is now retained with campaign SHA-256
`40399470984761de4677f3b65a398a648178bda14c83bf180c9840b4f4e182dd`.
It contains all `9` evaluation episodes and `12,744` content-addressed proposal
rows; its maximum learned/planner joint-target deviation is `0.0753160568 rad`.
The continuity diagnostic finds `78` adjacent-step transitions and a maximum
`0.1055636794 rad` step above the existing `0.05 rad` bounded-collision sample
step. The source planner has the same schedule-boundary pattern and reaches
`0.10115 rad`, so the correct next boundary is fresh bounded interpolation and
collision qualification, not silent direct replay or rejection based only on
raw command adjacency. Native replay remains blocked until that screen passes.

The bounded collision-request compiler now turns those nine proposal traces
into `523` discrete arm configurations, including `90` inserted interpolation
samples. Each episode remains between `40` and `75` samples, below the existing
`256`-sample admission ceiling, and the maximum adjacent arm-joint step is
`0.0499945099 rad`. Campaign SHA-256
`d4216d68e351335a6611cfc4ea0796cb8578c7dd01bc846e5a793f9ddee13d4d`
binds every request to the model, dataset, proposal trajectory, and the
target-specific ARM-216 geometry, placement, pair-policy, fixed-root, route,
and toolchain lineage. It explicitly does not reuse the earlier collision
result. Status `READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION`
means fresh Isaac collision diagnostics are the next step; it is not collision
clearance or native replay authority.

The runtime-admission validator now reloads the exact dataset, model, proposal
campaign, nine collision requests, and four ARM-216 target environments. It
also revalidates each source manifest entry, collision request, fixed-root
plan, station predicate, native receipt, bounded sample, and required runtime
file hash. The retained admission campaign has SHA-256
`5fd06ed3000934c49ac9b77e4db9bf8187e60dd96b2f88282d4a3553a1a3e883`.
Its status
`READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_RUNTIME_INPUT_REVALIDATION`
is intentionally one gate short of execution: the virtual profile, robot USD,
import receipt, and toolchain must be reloaded and matched immediately before
Isaac starts. The campaign records zero runtime-file revalidations, Isaac/GPU
starts, and collision diagnostics, so no earlier planner result is presented
as learned-policy clearance.

The immediate runtime-file revalidation is now retained separately with
campaign SHA-256
`36f6f1221666f1cbbf092fb2858623d61d60de007c7c2b41e20bd8d278b462da`.
It reloads the virtual profile and robot USD as raw bytes, verifies the robot
USD against the canonical import receipt, and hashes the selected toolchain as
canonical JSON. All four hashes match every one of the nine admissions. The
artifact contains `9` per-episode receipts and preserves all `523` bounded
samples. Status
`READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTIC_START` means the
runtime inputs are exact and fresh enough to start the next diagnostic stage;
it is not collision clearance. The receipt explicitly records zero Isaac/GPU
starts, zero diagnostics, zero reused results, and no native or physical
authority.

The fresh ARM-220 native diagnostic campaign is now retained at
`C:\IsaacSim\artifacts\issue190\arm220-state-policy-native-collision-001`.
Its manifest SHA-256 is
`cd4b7a70632d84b1e28bf6cdce23d3013659dfbebbce1913e351154bd6eee85b`
and its completed campaign SHA-256 is
`01acc93bd8da33dfab4ca5a69ae20cec7459ed9f0d97fe5e730830960576d7ca`.
All `9` held-out episodes and all `523` bounded samples ran as fresh native
PhysX overlap diagnostics. Every fixed-base observation stayed within the
governed root invariant. All samples reported the same five raw adjacent-link
body pairs, and all five are the already accepted diagnostic-only reporting
exclusions; the campaign reports zero physical-solid, planning-envelope, or
unreviewed blocker pairs in every episode. This closes the discrete LM4
collision-diagnostic denominator, but it is not continuous collision proof,
installed-geometry qualification, contact replay authority, or physical
motion authority. The next stage is review of this LM4 result before any
mechanics replay is proposed.

ARM-221 now performs that review independently of the ARM-220 aggregation. The
retained review at
`C:\IsaacSim\artifacts\issue190\arm221-state-policy-native-collision-review-001`
has SHA-256
`44d76e941161d94280e04abe2956fe45b17d3a0d78bab4f6c0d1cb0ffa99ccab`.
It reopens the exact manifest, campaign, and all nine native receipts; verifies
the complete `523`-sample denominator; inspects every sample's raw and excluded
pair sets; and rechecks the fixed-base invariant. All `523` samples contain
exactly the five accepted adjacent-link diagnostic exclusions, with zero
physical-solid, planning-envelope, or unreviewed blockers. The maximum observed
root deltas are `0.0064012435 mm` and `0.0559529102 deg`, within their retained
tolerances. Status
`ACCEPTED_FOR_ZERO_AUTHORITY_MECHANICS_PLAN_COMPILATION` allows only compilation
of the next LM4 mechanics plans. It does not start Isaac, authorize mechanics
execution, prove continuous or installed clearance, or grant physical motion.

ARM-222 then compiles the exact learned-policy proposals into nine signed,
non-executing mechanics plans. The retained campaign covers all `12,744`
proposal targets and preserves the `523`-sample collision denominator as
lineage. It binds each episode to its accepted ARM-217 target mechanics source
and marks the two contact endpoints without inventing interpolation targets.

ARM-223 reopens those nine plans and revalidates their five runtime inputs:
the derived key-mechanics profile, virtual commissioning profile, drive
profile, robot import receipt, and imported robot USD. The retained campaign at
`C:\IsaacSim\artifacts\issue190\arm223-state-policy-mechanics-runtime-admission-001`
has SHA-256
`5f8e6d9120e6d6a4ec3f1e9389baad93f44d56b4208043ee6689a359572c07ca`.
All nine admissions and the full `12,744` / `523` denominator pass. This is an
identity and lineage gate only: it starts neither Isaac nor a GPU, executes no
mechanics replay, and grants no hardware or physical authority. The next stage
is materialization of fresh LM4 mechanics replay inputs.

ARM-224 completes that materialization. Its signed manifest at
`C:\IsaacSim\artifacts\issue190\arm224-state-policy-native-mechanics-inputs-001`
has SHA-256
`5f895d7dd14776ac6e44886367db0b13439a3d98a353d63a67cc72da5d85af3a`
and binds nine fresh replay plans to the admitted runtime hashes. The plans
preserve all `12,744` targets, `523` collision-screen samples, randomized
resets, mechanics parameters, placements, and contact endpoints. This stage
does not start Isaac/GPU, reuse a mechanics result, or grant physical
authority. Fresh zero-authority mechanics execution and outcome measurement
are next.

ARM-225 begins that fresh mechanics execution one precommitted episode at a
time. The first `SPACE` episode started Isaac 6.1 and the GPU, then stopped on
the unchanged fixed-base root invariant at sequence `723` in `TRANSIT`, before
either contact endpoint (`1061`, `1299`). It was not retried. A signed
error-only receipt retains the exact ARM-224 manifest/plan lineage and the
observed `ROOT_INVARIANT` result while explicitly declining to claim a retained
native trace, contact, release, settling, or action assessment. The execution
wrapper now preserves the same fail-closed receipt shape for future runtime
errors. The next bounded increment is root-drift diagnosis with retained step
telemetry; it is not permission to replay this episode automatically.

ARM-226 implements that retained-telemetry path without starting Isaac or
replaying the failed episode. A future separately authorized state-policy run
that crosses the fixed-base tolerance now stops cleanly and signs the partial
native trace, joint-tracking records, and root-pose observations through the
failing target. Its receipt records the planned and attempted denominators and
the exact stop sequence, phase, and action, remains blocked and incomplete,
skips incomplete action scoring, and records no automatic retry. The ARM-225
receipt remains unchanged and error-only; its discarded trace cannot be
recovered retroactively. This instrumentation makes the next failure
diagnosable but is not authority for another attempt.

ARM-227 turns that diagnosis boundary into a signed, non-executing plan. It
binds the exact ARM-224 manifest and `SPACE` plan to the ARM-225 blocked
receipt, preserving the stop at sequence `723` before first contact at `1061`.
The plan records the concrete fixture difference: the failed LM4 path authored
64 solver-position iterations but omitted the known-passing path's eight
solver-velocity iterations and explicit fixed-joint enable. Its proposed probe
uses the known-passing fixture and observes the root at four lifecycle
checkpoints through five settle updates, with no trajectory playback, joint
targets, key contact, retry, hardware access, or physical authority. Planning
does not start Isaac or a GPU; executing the diagnostic remains a separate
authorization boundary.

ARM-228 implements the corresponding one-attempt worker. Runtime admission
rebuilds the signed ARM-227 plan and revalidates the exact drive profile and
robot USD before starting Isaac. The worker authors only the known-passing
fixed fixture and observes root translation and rotation at the four planned
checkpoints. It creates no key, sends zero joint targets, does not play the
failed trajectory, performs no retry, and emits no physical authority. Both a
pass and an early stop produce a signed receipt for review.

The separately authorized `-002` ARM-228 probe passed all four checkpoints.
Maximum root translation drift was `0.0012960249 mm` against `0.05 mm`, and
maximum orientation drift was `0.0 deg` against `0.1 deg`. Receipt SHA-256 is
`d7e9e6a6a0815463c4d09ec6d829aeff75b2388359b6a221ebce82f00882be3e`.
ARM-230 independently reopens the receipt and its ARM-227/224/225 lineage,
verifies the full checkpoint denominator and zero-authority fields, and retains
review SHA-256
`3875242ec7b6826320e10a9e86468466dbefbc9f7bc648087cb3da27b3ff5940`.
The review admits only an offline state-policy fixture correction. Mechanics
replay, contact, hardware, and physical authority remain denied.

ARM-231 applies and independently reproduces that exact correction across all
nine state-policy episodes. The v2 manifest binds the ARM-230 review, retains
the unchanged trajectory samples, authors `64` solver-position iterations, `8`
solver-velocity iterations, and an explicitly enabled fixed joint, and replaces
every prior replay-plan hash. Corrected manifest SHA-256 is
`ff166283e37c35bc906668bacc8a37128bcdcd9c1a7b088675412dc5ae38bb28`;
independent review SHA-256 is
`faf67c3e4163b2c8bd40f0a3303fdcda31222f3e9196050f2588538f332e5916`.
Both operations were offline. The review permits only a later, separately
authorized zero-authority native attempt; it does not itself authorize one.

ARM-232 selects exactly one corrected `SPACE` episode from that reviewed
denominator and binds its corrected plan, manifest, review, fixed-fixture
configuration, runtime hashes, sample count, and contact endpoints into a
single-attempt request. The request forbids automatic retry, requires fresh
runtime-file revalidation immediately before a separately authorized launch,
and carries no hardware or physical authority. Request construction is an
offline planning action and starts neither Isaac nor a GPU. The retained
request SHA-256 is
`f2d1f9708dc361c3f592f07d78eccd029dab4ccf5333def5cddc8f145e7caa65`.

ARM-233 executed that request exactly once after fresh runtime revalidation.
The fixed-fixture correction removed the prior configuration ambiguity but did
not clear the governed root-orientation invariant. The replay stopped at
sequence 723 after 724 of 1,416 targets when orientation reached
`0.1046783125 deg` versus the `0.1 deg` limit; translation remained within its
limit. The signed failure receipt retains the 724-row partial trace and has
SHA-256
`b40dfc8946324883a2cfb907845ba4c79b57303b878a94f9cdc182fc5734dab6`.
This is evidence for offline diagnosis only. It grants neither retry authority
nor hardware or physical authority.

ARM-234 converts that partial trace into a deterministic offline review.
Material key displacement begins during `TRANSIT` at sequence 654; the first
root-orientation rise past `0.05 deg` follows at sequence 694, and the governed
stop remains sequence 723. The 40-sample ordering narrows the next investigation
to transit clearance and contact timing, but is not by itself proof of
causality. Review SHA-256 is
`ffab81579f296d6affc687fa774fd419f3db1e1e824520dfb5dd39666206227e`.
No simulation, retry, hardware access, or physical authority occurs in this
review.

ARM-235 binds ARM-234 and the unchanged corrected source plan into an offline
correction contract. Only the noncontact window from sequence 654 through 940
may later be regenerated; sequence 653, the first `CONTACT` row at 941, and
contact endpoints 1061/1299 remain bound. Materialization must prove `0.5 mm`
continuous noncontact clearance, at most `0.05 mm` noncontact key displacement,
IK validity, and the existing `0.05 rad` adjacent-joint limit. The plan contains
no replacement targets and grants no replay authority. SHA-256 is
`5dd11d86f30884e116ce8c0300af97100285cddaf4f90902b0e590e6ea59580d`.

ARM-236 independently audits the representative `SPACE` approach before any
replacement targets are generated. Source targets 29–31 remain separated, but
targets 32–34 fall to about `0.004 mm` sampled separation and move the key by
`0.164–0.205 mm`. The prior route is therefore not a valid seed for ARM-235.
The next materializer must generate a lifted board-frame
ascent/traverse/descent route and bind canonical IK to conservative swept
envelopes for every adjacent segment. Exact target-key and installed collision
geometry remain required; no simulation is started and no replay is authorized.
Review SHA-256 is
`e7d6de796cff936be7200d4e159d4b4a9654bf9a01530ba90683ef1a77f2d539`.

ARM-237 binds the usable geometry and route lineage without promoting nominal
data to installed evidence. It records the SPACE center `(224, 112) mm`, XY
half-extents `(48, 7) mm`, nominal `z=21 mm` plane, and source route anchors
29/34/35. It then retains the missing 3D key/depression envelope, uncertainty,
tool/attachment transform, clamp/camera/cable geometry, clearance policy, and
exclusion review as explicit blockers for the existing ICQ-1 manifest. No
Cartesian correction, IK, collision proof, replay, or physical action occurs.
Plan SHA-256 is
`2c7c099bdd285d922ad01dd56092c3c79bd42e53dfbc41caacdd9741c15b1f01`.

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
3. **LM1 collision:** native representative-key physics, Cartesian
   regeneration, canonical IK, the exact 149-sample diagnostic, reviewed
   adjacent-link policy, policy-bound rerun, and exact blocker localization are
   complete. The explicit station route predicate is also complete: contact
   endpoints are target-bound, planning regions are excluded from PhysX, and
   physical board/device solids remain active. The retained rerun has zero
   station-envelope blockers and seven physical board/keyboard body-pair
   blockers. A hash-bound ARM-198 experiment plan separates 71 implicated
   transit samples from endpoint geometry work and proposes a 70 mm
   zero-authority transit-height hypothesis. The exact variant now passes
   canonical IK for all 133 samples, but its 179-configuration native replay
   still retains all seven physical blocker pairs and zero station-envelope
   blockers. This rejects a uniform TCP-height lift as the complete route
   correction. ARM-199 fixed and executed the next experiment: one retained
   control plus 81 documented placement/yaw/keyboard-TCP hypotheses. Only three
   candidates passed canonical IK. Native replay reproduced seven blocker pairs
   at all 179 control samples; both alternatives were worse, adding an eighth
   blocker while overlapping at all 188 or 189 samples. The retained result is
   `NO_NATIVE_IMPROVEMENT_RETAINED`, so coarse placement/TCP sensitivity is not
   the next correction. ARM-200 now fixes the separately hash-bound full-link
   route-shape campaign before screening: one exact control plus eight
   predeclared direct/orthogonal XY corridor variants at bounded 70/90/110 mm
   heights. It preserves all 14 non-transit endpoints, physical solids,
   placement/TCP, timing, and policy/toolchain bindings, and limits native
   replay to four deterministic finalists. ARM-201 has now materialized all
   nine candidates: six pass all 133 canonical IK/continuity samples and all
   three `X_THEN_Y` variants retain explicit unreachable-IK rejections. The
   offline full-link evaluator reports zero transit and endpoint blockers for
   the six survivors, but the prior ARM-199 offline/native discrepancy prevents
   treating that as clearance. The fixed ranking retains four exact native
   replay inputs (`Y_THEN_X/110`, `DIRECT_LINEAR/110`, `Y_THEN_X/70`, and
   `DIRECT_LINEAR/90`). ARM-202 attempted that unchanged shortlist once in
   rank order. `Y_THEN_X/110` stopped before admission because the invocation
   selected a policy artifact whose boundary did not match the bound request;
   it was not retried. The other three v3 diagnostics completed without the
   separate station-route-predicate input and overlap at every one of their
   169/170/165 bounded samples. Each retains the same seven physical blocker
   pairs as the ARM-199 control, so no route-shape improvement is selected.
   ARM-203 then performed the separately governed v4 route-predicate replay;
   two candidates completed, but ARM-204 showed that their shared seven-pair
   result came from a growing native robot-root Z drift rather than route
   shape. ARM-205 now authors a fixed joint to world before physics and checks
   the root at admission and after every sample. Both retained candidates pass
   all 337 root observations and retain zero physical-solid,
   planning-envelope, or unreviewed blockers. Five pairs per candidate remain
   explicitly policy-excluded. ARM-206 then projects both candidates through
   the governed `H` mechanics contract: both retain two centered accepted
   `2.7 mm` presses with complete release. With mechanics outcomes equivalent,
   the predeclared kinematic ranking selects `DIRECT_LINEAR/90` as the
   simulation-learning baseline because it has lower commanded acceleration,
   adjacent-joint delta, total joint travel, and Cartesian path length than
   `Y_THEN_X/70`. This is a commanded-kinematics selection, not native robot/key
   contact evidence. Continuous-clearance and physical-contact qualification
   remain separate dependencies.
4. **LM1 robot/key replay:** after collision qualification, bind the
   drive-controlled robot TCP to the same native `H` mechanism and evaluator.
   ARM-207 now supplies the strict selected-route compiler and the first full
   drive-controlled robot/key replay. Native contact and fixed-root behavior
   are observed, but the retained run fails unchanged mechanics acceptance:
   the provisional drive response overshoots the key travel and the original
   timing does not allow complete release before the second `H` action. The
   ARM-208 applies that first feedback update and re-runs the same native
   boundary. It reduces peak compression to about `3.66 mm`, preserves the
   tracking and root invariants, and confirms that added dwell does not release
   the key because the H hover/retract target itself remains in contact. The
   next learning input is now more precise: derive a lifted approach/hover/
   retract geometry from the native trace, then replay without changing
   authority or weakening the evaluator. ARM-209 completes that lift and
   restores complete release plus one activation per action. Only a small
   contact-depth overtravel remains, so the next bounded update must preserve
   the lifted release geometry and refine the contact endpoint from retained
   feedback. ARM-210 completes that update and passes the unchanged evaluator.
   ARM-211 retains the exact passing H result as a canonical LM2 adaptation
   seed, with its plan/receipt/profile lineage and native quality gates intact.
   It explicitly forbids direct H joint-space reuse for other keys.
5. **LM2 generator:** adapt the `H` skill semantics and contact policy to the
   representative target set. `1`, `SPACE`, `ENTER`, and `PERIOD` each require
   target-specific board-frame geometry, fresh IK, collision/fixed-root
   qualification, and native mechanics acceptance before they can enter a
   multi-key dataset.
   ARM-212 now emits the four hash-bound Cartesian skill requests without joint
   reuse. ARM-213 connects each request to the governed park endpoint with the
   retained `DIRECT_LINEAR` / `90 mm` corridor policy while preserving every
   target skill sample. ARM-214 then solves all 40 samples for every target with
   fresh canonical IK and continuity gates, without reusing H joint solutions.
   ARM-215 compiles those accepted routes into bounded collision replay plans
   with `49`, `46`, `58`, and `55` joint configurations and the governed
   fixed-world root invariant. ARM-216 now materializes those four plans as
   direct, hash-bound native admissions and replays all `208` configurations
   through Isaac/PhysX. Every route passes its fixed-root invariant with zero
   physical-solid, planning-envelope, or unreviewed blocker pairs. The five
   raw overlap pairs observed on each route are the already reviewed
   diagnostic-only exclusions; they do not promote the uninstalled collision
   candidate. ARM-217 now carries `1`, `SPACE`, `ENTER`, and `PERIOD` through
   native key mechanics. Untouched schedules first expose excessive travel;
   trace-derived release anchors and bounded contact-only refinements then
   produce two accepted actions per target without changing regions,
   thresholds, fixed-root requirements, or authority. The final hash-bound
   aggregate contains eight accepted actions and `5,664` native trace samples,
   so the representative routes now form a provisional zero-authority
   multi-key simulation dataset.
6. **LM3 dataset smoke:** ARM-218 completed the reproducible `24`-episode
   manifest, bounded native execution, content-addressed trajectory retention,
   and fail-closed aggregation of all `18` passes and `6` failures without
   changing the attempted denominator.
7. **LM4 dataset:** ARM-219 regenerated all `24` episodes with per-step state
   and action capture, compiled `33,984` content-addressed rows without leakage,
   and retained failures separately from `12,744` passing training rows.
8. **LM4 baseline:** the first deterministic linear policy is fit and its
   train/held-out action-imitation error is retained. Replay its proposals on
   identical held-out resets through the unchanged simulation gates next.
9. **LM4 runtime admission:** all nine learned-policy collision requests are
   bound to their ARM-216 environments and the four governed runtime files are
   reloaded and rehashed. ARM-220 then completes all nine fresh native
   diagnostics over `523` samples with no blocker episode.
10. **LM4 collision review:** ARM-221 independently verifies the exact native
    evidence and admits only zero-authority mechanics-plan compilation. Contact,
    release, settling, tracking, and abstention evaluation remain pending.
11. **LM4 mechanics-plan compilation:** ARM-222 compiles all `12,744`
    learned-policy targets from the nine held-out episodes into hash-bound,
    non-executing mechanics plans. It preserves each randomized reset, marks
    both contact endpoints per episode, carries the accepted per-target ARM-217
    mechanics lineage, and retains the exact `523`-sample collision-screen
    denominator. Runtime admission and file revalidation are next; mechanics
    execution and its contact, release, settling, tracking, and abstention
    measurements have not occurred.
12. **LM4 mechanics runtime admission:** ARM-223 reopens all nine plans and
    revalidates the exact five runtime inputs. The signed campaign preserves
    all `12,744` targets and `523` collision-screen samples while recording
    zero Isaac/GPU starts, zero mechanics replays, and zero physical authority.
    Fresh mechanics-input materialization is next.
13. **LM4 mechanics input materialization:** ARM-224 emits nine signed native
    replay plans bound to the exact ARM-222 plans, ARM-223 admissions, and five
    runtime hashes. All `12,744` targets, `523` collision samples, randomized
    resets, placements, mechanics values, and contact endpoints are retained.
    Isaac/GPU and mechanics execution remain at zero; fresh replay is next.
14. **LM4 first mechanics episode:** ARM-225 attempts one exact `SPACE` episode
    without retry. Isaac/GPU start succeeds, but the replay stops at sequence
    `723` during `TRANSIT` on the fixed-base root invariant, before its contact
    endpoints. The signed blocked receipt retains input lineage and the error
    but not the discarded in-memory trace. Root-drift telemetry and diagnosis
    are required before another governed episode attempt.
15. **LM4 partial telemetry retention:** ARM-226 changes only the future
    state-policy failure path. A root-invariant stop now retains and signs the
    partial native trace, joint tracking, root observations, attempted target
    count, and exact stop location while remaining incomplete, blocked, and
    non-retrying. It does not rerun or alter the ARM-225 result.
16. **LM4 root-fixture diagnostic planning:** ARM-227 signs the exact failed
    episode lineage and the fixed-fixture delta, then defines a four-checkpoint
    static-root probe using the known-passing fixture configuration. Plan
    generation starts no simulator/GPU, emits no trajectory or joint command,
    and does not authorize the probe or another mechanics replay.
17. **LM4 root-fixture diagnostic worker:** ARM-228 revalidates every ARM-227
    source and runtime hash, executes only the four-checkpoint static fixture
    probe, and signs either a pass or blocked receipt. It has no trajectory,
    joint-command, contact, retry, hardware, or physical-motion path.
18. **LM4 diagnostic lifecycle correction:** the first separately authorized
    ARM-228 launch started Isaac once but produced no receipt because fast app
    shutdown occurred before the post-close writes. The attempt is unscored and
    was not retried. ARM-229 persists both receipt and status before app close;
    another diagnostic still requires separate authorization.
19. **LM4 root-fixture diagnostic review:** the separately authorized `-002`
    probe passes all four static checkpoints with `0.0012960249 mm` maximum
    translation drift and `0.0 deg` rotation drift. ARM-230 independently
    verifies the receipt and full source lineage, admitting only an offline
    correction to the state-policy fixed fixture. No mechanics replay or
    physical authority is granted.
20. **LM4 fixed-fixture correction:** ARM-231 changes the state-policy runner to
    match the proven static fixture, materializes nine review-bound v2 inputs,
    and independently reproduces every corrected hash without starting Isaac.
    The trajectory denominator is unchanged and replay authority remains false.
21. **LM4 single corrected replay request:** ARM-232 binds one reviewed
    corrected `SPACE` episode into a one-attempt, no-retry authorization
    request. It starts no simulator or GPU, performs no replay, and grants no
    native, hardware, or physical authority. Fresh runtime-file revalidation
    and an exact explicit authorization remain prerequisites to execution.
22. **LM4 single corrected replay execution:** ARM-233 consumes the exact
    authorization once and stops fail-closed at sequence `723` after retaining
    724 trace rows. The corrected fixture is active, no retry occurs, and the
    result remains blocked with no hardware or physical authority.
23. **LM4 premature transit-contact review:** ARM-234 confirms offline that
    material key displacement begins at sequence `654` during `TRANSIT`, 40
    samples before root orientation first exceeds `0.05 deg` and 69 samples
    before the governed stop. It narrows correction planning without claiming
    causality or authorizing another replay.
24. **LM4 transit-clearance correction planning:** ARM-235 binds the signed
    premature-contact review to a 654–940 noncontact correction window. It
    preserves source timing, phases, fixed fixture, first contact, and both
    contact endpoints while requiring continuous clearance and zero-contact
    evidence before a candidate may be retained. No targets are changed yet.
25. **LM4 correction-materialization readiness:** ARM-236 proves that the old
    representative route is not reusable under ARM-235: its last three
    noncontact targets already touch and displace the key. It requires a newly
    lifted board-frame route, canonical IK, exact installed collision geometry,
    and conservative evidence for every adjacent segment. It remains offline
    and grants no replay, hardware, or physical authority.
26. **LM4 installed-geometry intake:** ARM-237 binds all existing SPACE surface,
    route-anchor, and collision-candidate evidence, while refusing to infer an
    installed 3D key body or missing workcell geometry from nominal dimensions.
    It routes the exact remaining blockers into the hash-bound ICQ-1 installed
    measurement-manifest boundary and keeps route materialization disabled.
27. **LM4 installed-measurement inventory:** ARM-238 emits and validates the
    exact 19-body `stylus_attachment` ICQ-1 manifest while keeping all
    unsupported geometry and clearance values `PENDING`. It hash-binds 12
    supplied ruler/layout photos as reference-only evidence, preserves a
    distinct 18-body `no_attachment` contract in tests, and refuses to infer
    local-frame 3D envelopes or uncertainty from the images. No collision
    profile, route, replay, hardware access, or physical authority is created.
28. **LM4 installed-measurement gap audit:** ARM-239 hash-verifies the retained
    ARM-238 package and audits it against the frozen workcell layout, physical
    measurement gates, frame contract, model geometry, and 12 reference
    photos. It retains the configured board, keyboard, phone, station, robot,
    camera, cable, and tool facts as capture priors but promotes none of them
    into ICQ-1 measurements. All 19 bodies remain pending, with a reviewed
    body-specific list of missing local-frame primitives, uncertainty, pose,
    identity, target-key, or configuration-sweep evidence. This converts a
    generic measurement block into a deterministic capture backlog without
    creating a profile, route, replay, hardware access, or physical authority.
29. **LM4 robot-geometry review candidates:** ARM-240 binds ARM-239 to the
    retained upstream-mesh reduction and packages all `14` conservative
    link-local boxes for the seven robot bodies. The candidates retain exact
    mesh, upstream-commit, partition, containment, and non-watertight lineage,
    but remain `PENDING`: physical model identity, uncertainty, false-positive
    quality, and link5 whole-envelope review are still open. No ICQ-1 row is
    modified and no profile, collision screen, route, replay, hardware access,
    or physical authority is created.
30. **LM4 robot-geometry review gate:** ARM-241 binds the seven candidate rows
    to exact per-body hashes and a complete engineering-review contract. It
    requires accepted installed identity, positive geometry uncertainty, and
    conservative-candidate quality for every row, with extra findings for
    non-watertight sources and the ARM-196/link-5 negative result. The current
    request remains blocked because no engineering review is supplied. A future
    passing assessment can establish eligibility only for a separate ICQ-1
    robot-row build; it cannot modify the manifest, generate a collision
    profile, screen a route, start Isaac, or grant physical authority.
31. **LM4 non-robot capture packets:** ARM-242 preserves the ARM-239/241 split
    and converts all `12` remaining non-robot gaps into six hash-bound capture
    packets. Eleven bodies are explicitly shared across `no_attachment` and
    `stylus_attachment`; only the contact tool is stylus-only. Every exact
    missing acceptance field, prior identifier, binding mode, method, and
    common provenance requirement is retained. All packets remain pending and
    no measurement, manifest row, profile, route, replay, hardware access, or
    physical authority is created.
32. **LM4 capture submission gate:** ARM-243 materializes the six ARM-242
    packets as exact hash-bound templates and validates one independently
    completed packet at a time. Acceptance requires evidence hashes,
    instrument identity and resolution, coordinate frame, exact body coverage,
    every packet-specific field, positive uncertainty, valid local-frame
    envelope primitives, and measured reviewer acceptance. Success creates
    only eligibility for a later ICQ-1 fragment build; it cannot modify the
    manifest or profiles, run collision screening, start Isaac/GPU work,
    access hardware, or grant physical authority. The retained templates are
    intentionally uncompleted and remain blocked on real capture submissions.
33. **LM4 foundational capture work order:** ARM-244 selects the shared
    `base_board_installation` packet first because frame `B`, the installed
    board solid, and the base/clamp installation underpin every later static
    pose and require no commanded arm motion to measure. It binds exact
    ARM-242/243/frame-contract hashes and enumerates all ten missing acceptance
    values, provenance, instrument, review, and stop requirements without
    prefilling any observation. Existing photographs remain context rather
    than metric acceptance. The work order stays blocked on real metrology and
    independent review and creates no profile, collision result, simulation,
    hardware access, or physical authority.
34. **LM4 base/board prior reconciliation:** ARM-245 hash-binds the ARM-244
    work order to the maintained frame, fixed-plane, simulation-profile, and
    nominal-scene sources. It preserves the nominal board solid, reach-screening
    base pose, and partial clamp span as comparison targets but promotes none
    into installed metrology. It also prevents the camera-plane fit residual
    from being misused as board geometry uncertainty. Zero of ten acceptance
    fields are complete; the exact installed capture and independent review
    remain required. No manifest, profile, simulation, hardware access, or
    physical authority is created.
35. **LM4 base/board raw capture compiler:** ARM-246 binds the ARM-243 template
    and ARM-245 reconciliation into one minimal observation form. A completed
    form must carry retained evidence, instrument identity/resolution, measured
    board and base/clamp values, verified frame-B registration, positive
    uncertainties, and acceptance by a reviewer distinct from the observer.
    The compiler deterministically derives
    the exact ten ARM-243 fields and rejects malformed geometry or review. The
    retained form is deliberately blank and blocked; nominal comparison values
    cannot become measurements. It creates no manifest, profile, simulation,
    hardware access, command, or physical authority.
36. **LM4 base/board metrology session workbench:** ARM-249 converts the
    immutable ARM-248 protocol into its exact editable session schema and
    audits progress without compiling or inventing observations. It reports
    all missing capture fields, invalid fields, and independent-review blockers
    separately; counts the 63 required scalar readings; and checks numeric,
    clamp-order, and base-datum geometry before declaring the session ready for
    ARM-248 compilation. The retained blank session remains at `0/63` and
    blocked on physical readings, frame-B registration, and independent review.
    No camera, instrument, simulator, GPU, controller, or robot is accessed,
    and no hardware or physical authority is created.
37. **LM4 nominal base/board simulation profile:** ARM-250 hash-binds the
    controlled RC03 workcell layout, BOM, simulation-hardware profile, and
    nominal rigid scene into an explicit design-prior profile. It makes the
    610 x 457 x 18 mm board, nominal base transform, and partial rear-clamp
    span directly consumable by simulation-only route and physics experiments
    without representing them as installed measurements. Unknown board bow
    and full clamp bounds remain null; installed-profile compatibility,
    controller commands, hardware access, and physical authority remain false.
38. **LM4 nominal route-physics experiment binding:** ARM-251 binds the exact
    ARM-250 fixture prior, ARM-231 corrected `SPACE` route, ARM-235 regeneration
    window, and selected Isaac 6.1 toolchain into one reproducible baseline
    experiment. The board participates as nominal collision geometry, while
    the incomplete clamp volume, installed uncertainty sweeps, and physical
    conclusions remain excluded. The contract requests one future simulator
    case after independent review but starts no simulator or GPU, materializes
    no targets, and grants no controller, hardware, replay, or physical
    authority.
39. **LM4 nominal route-physics independent review:** ARM-252 independently
    reopens the ARM-251 experiment and its four sources, verifies every file and
    canonical binding, and preserves the exact one-case fixture, route, runner,
    truth-isolation, and acceptance limits. It accepts at most one later,
    separately authorized SPACE simulation attempt with no automatic retry.
    This is the first rung of the automatic-typing ladder: qualify one reusable
    approach/traverse/descent primitive, then expand the same contract to a
    representative multi-key set before vision-conditioned rolling-horizon
    typing. The review starts no simulator or GPU, generates no targets, and
    grants no hardware or physical authority.
40. **LM4 nominal route-physics attempt request:** ARM-253 freezes the accepted
    review, exact experiment and source-file identities, one-attempt/no-retry
    boundary, required retained outputs, and the exact authorization statement
    for a future fail-closed simulation worker. The request preserves the
    `SPACE`-first automatic-typing rung and explicitly hands a passing result to
    representative multi-key expansion. Building it starts no simulator or
    GPU, generates no joint targets, plays no trajectory, and grants no
    hardware or physical authority.
41. **LM4 nominal route-physics worker envelope:** ARM-254 implements the
    fail-closed orchestration boundary around that request. It freshly checks
    every request/review/experiment/source hash, requires the route-bound robot
    USD, import receipt, virtual profile, and key-mechanics profile identities,
    atomically claims one absent output directory, records the claim before any
    backend call, retains a terminal failure receipt, and permits no retry. The
    CLI only emits a byte-stable preparation for independent review; the pinned
    Isaac physics backend remains the next implementation and review boundary.
    No simulator or GPU starts, no targets are generated, and no hardware or
    physical authority is created.
42. **LM4 nominal route-physics backend core:** ARM-255 implements the exact
    deterministic result contract behind a separately reviewable Isaac runtime
    protocol. A passing result requires all 287 regenerated rows to carry
    accepted determinate canonical IK, all 288 boundary-inclusive adjacent
    segments to carry determinate continuous clearance (not sampled overlaps),
    all 287 noncontact rows to satisfy tool/key clearance and displacement
    limits, and one determinate root-drift observation. The definition CLI is
    non-starting and consumes no attempt. Independent review must next pin an
    actual Isaac adapter that satisfies this protocol before the ARM-253
    authorization can be consumed.
43. **LM4 Isaac runtime-capability gate:** ARM-256 launches only the selected
    zero-authority Isaac Sim 6.1 runtime and retains its actual PhysX scene-query
    surface. Shape, mesh, box, and sphere linear sweeps are available, but the
    API has no direct articulated joint-interpolation or signed minimum-distance
    query. Therefore native sweeps alone cannot satisfy ARM-255. The accepted
    implementation direction is a hash-pinned conservative bounding-sphere
    interval adapter that inflates the required clearance margin, bounds link
    center-path deviation and rotation, recursively subdivides indeterminate
    intervals, and separately checks moving self-collision pairs. This probe
    loads no scene or trajectory and consumes no authorized route attempt.
44. **LM4 conservative swept-envelope core:** ARM-257 implements the
    Isaac-import-free proof kernel selected by ARM-256. Runtime-certified link
    spheres are inflated by center-path deviation and the fixed 0.5 mm margin;
    conservative hits recursively subdivide, moving self-collision is checked
    separately with reviewed exclusions only, and invalid bounds or exhausted
    depth fail closed. This step loads no scene or trajectory and consumes no
    governed route attempt.
45. **LM4 native-binding proof-input preflight:** ARM-258 hash-binds the
    available native sweep API, governed URDF, ARM-255 through ARM-257 lineage,
    geometry prior, and current diagnostic pair policy. It fails closed because
    the repository does not yet contain a certified seven-link sphere profile
    or a continuous-clearance-scoped pair policy; the diagnostic policy is not
    silently promoted. No Isaac runtime is started and no attempt is consumed.
46. **LM4 native-binding proof-input proposals:** ARM-259 deterministically
    encloses each of the seven pinned upstream model-link mesh bounds with one
    conservative local sphere and derives exactly the six direct parent/child
    exclusions from the governed URDF. The results are proposals pending a
    separate source-and-arithmetic review; non-watertight meshes limit solid
    claims but not retained-vertex containment, and installed tool, clamp,
    cable, or camera geometry is not claimed.
47. **LM4 native-binding proof-input independent review:** ARM-260 reopens the
    ARM-259 artifact, retained mesh receipt, and governed URDF; independently
    recomputes seven centers, upward-rounded radii, and all 56 AABB corners;
    and rederives exactly six direct parent/child exclusions. It certifies only
    pinned simulation-model vertex containment and direct adjacency. It admits
    no native binding, Isaac launch, route attempt, or physical operation.
48. **LM4 certified-input native-binding readiness:** ARM-261 reruns the
    hash-bound ARM-258 gate with the ARM-260 review. It verifies the outer
    review identity, both nested certified-input identities, exact upstream
    source files, and the governed URDF before clearing the two proof-input
    blockers. The result authorizes only implementation and independent review
    of a hash-pinned native binding; it does not admit that binding, start
    Isaac, consume the reserved attempt, or grant physical authority.
49. **LM4 hash-pinned native conservative-sweep binding:** ARM-262 implements
    the ARM-257 runtime boundary over native articulation link transforms and
    environment-only PhysX sphere overlap/sweep queries. It derives
    conservative joint-path center bounds from the governed URDF and checks
    moving self-collision analytically with exactly the six certified
    exclusions. The import-safe definition is pending independent review and
    cannot launch Isaac or consume the governed attempt.
50. **LM4 native conservative-sweep binding independent review:** ARM-263
    reopens the exact ARM-262 artifact, implementation source, certified
    lineage, and governed URDF. It independently rederives every path bound and
    exercises transform mapping, metre conversion, endpoint overlap,
    continuous environment sweep, moving self-collision, exclusion integrity,
    and environment-only scene enforcement through non-Isaac doubles. The
    accepted receipt admits construction of this exact binding only inside a
    future separately admitted worker; it does not admit an Isaac launch,
    trajectory, joint targets, key contact, attempt, or physical operation.
51. **LM4 zero-authority native-binding integration preflight:** ARM-264
    hash-binds the ARM-255 backend protocol, ARM-257 proof core, ARM-262 native
    binding, ARM-263 acceptance receipt, and all three implementation sources.
    Static signature review confirms that the native binding supplies the
    exact three operations consumed by the recursive proof and that the proof
    can satisfy the backend's continuous-clearance method. The receipt fixes
    the composition order and next adapter boundary but does not implement or
    execute that adapter, construct Isaac objects, load a scene, submit joint
    targets, contact a key, consume the attempt, or grant physical authority.
52. **LM4 native-clearance composition adapter and independent review:**
    ARM-265 implements the backend's continuous-clearance method by composing
    the ARM-257 recursive proof with the reviewed ARM-262 native binding. The
    adapter fixes the 0.5 mm margin, six exclusions, depth-12 fail-closed
    refinement, and environment-only scene boundary. An independent reviewer
    reproduces the definition, inspects the source call surface, and exercises
    direct-clear and recursive-refinement paths with non-Isaac doubles. The
    receipt admits later zero-authority runtime composition only; canonical IK,
    tool/key metrics, and root drift remain separate dependencies, and no
    launch, attempt, trajectory, key contact, or physical authority is granted.
53. **LM4 nominal-route runtime-composition readiness:** ARM-266 pins the exact
    ARM-255 backend and accepted ARM-265 clearance adapter lineage, proves that
    continuous clearance is the one reviewed backend method, and orders the
    remaining adapters: canonical per-row IK regeneration, tool/key metrics,
    then terminal root drift. The gate remains fail-closed and constructs no
    runtime objects, starts no simulator, consumes no attempt, and grants no
    physical authority.
54. **LM4 canonical IK row adapter and review:** ARM-267 implements the
    backend's `regenerate_row` boundary without starting Isaac. For each row it
    reconstructs the source Cartesian tool-tip pose through the pinned model,
    invokes the canonical RoArm-M3 IK solver, and supplies the previous
    accepted row as the first continuity seed. Independent review reproduces
    the definition, inspects the FK-to-IK call surface, and exercises it with
    non-runtime doubles. Acceptance covers only per-row IK composition; tool/key
    metrics, root drift, complete runtime composition, and execution remain
    separate gates.
55. **LM4 tool/key metrics adapter and review:** ARM-268 implements the
    backend's `measure_tool_key` boundary without commanding an articulation.
    It derives the requested row's world-frame tool-tip surface point from the
    pinned FK model, reads the supplied native key pose, and computes both
    tool/key clearance and settled-baseline displacement. Independent review
    reproduces the definition, rejects joint-submission surfaces, and verifies
    the calculation with non-runtime doubles. Root drift, full runtime
    composition, native tracking, and execution remain separate gates.
56. **LM4 terminal root-drift adapter and review:** ARM-269 implements the
    backend's final read-only `root_drift` boundary. It samples the supplied
    native root view exactly once at the terminal checkpoint, compares it with
    the post-setup baseline, treats opposite quaternion signs as the same
    rotation, and rejects drift beyond 0.05 mm or 0.1 degree. Independent
    review reproduces the definition, inspects the operation surface, verifies
    the single-read calculation, and proves out-of-tolerance failure with
    non-runtime doubles. Complete runtime composition, native execution, and
    physical use remain separate gates.
57. **LM4 complete zero-authority runtime composition and review:** ARM-270
    binds the four accepted adapter objects behind the exact ARM-255 runtime
    protocol. The composition performs one-to-one delegation only; it does not
    construct native objects or call the backend. Independent review reproduces
    all pinned definitions and source hashes, inspects the four delegation
    surfaces, and verifies argument/result preservation with non-runtime
    doubles. Native runtime construction, backend execution, and any simulation
    attempt remain separate gates.
58. **LM4 native-runtime construction plan and review:** ARM-271 pins the
    already-initialized articulation, environment-only scene query, one-prim
    key and root views, and one canonical IK solver shared by the IK and
    metrics adapters. It fixes exact constructor arguments, one post-settle
    baseline read per view, and the construction order ending in an uncalled
    ARM-270 composition. Independent review reproduces the plan and verifies
    current constructor signatures and native evidence. Factory implementation,
    native object construction, backend execution, and any simulation attempt
    remain separate gates.
59. **LM4 zero-authority native-runtime factory and review:** ARM-272 implements
    the accepted ARM-271 assembly order over already-supplied initialized and
    settled objects. It captures one key and one root baseline, constructs one
    canonical solver shared by IK and metrics, assembles the four adapters, and
    returns the uncalled ARM-270 composition. Independent review exercises the
    factory with non-Isaac doubles and verifies construction order, baseline
    counts, shared identity, and the absence of protocol calls. Native-object
    creation, worker integration, backend execution, and simulation remain
    separate gates.
60. **LM4 native-runtime worker-integration plan and review:** ARM-273 pins the
    ARM-254 worker, ARM-255 backend, and ARM-272 factory lineage and specifies
    the future one-attempt call order. ARM-254 remains the sole output claim;
    scene settle precedes factory construction; one factory runtime is passed
    to one backend call; outputs precede shutdown; and every failure stops
    without retry. Independent review reproduces the plan, verifies the exact
    current call signatures, and retains the missing worker/backend review
    documents as explicit prerequisites. Integration implementation, launch,
    backend execution, and any simulation attempt remain separate gates.
61. **LM4 zero-authority worker integration and review:** ARM-274 implements the
    reviewed ARM-273 call order, materializes the worker/backend review inputs,
    and exposes one single-use backend callable over a deferred native session.
    Independent review accepts only later separately authorized one-attempt use;
    no session, simulator, trajectory, attempt, or physical operation starts.
62. **LM4 inert native-session smoke:** ARM-275 starts Isaac once without
    timeline playback or physics stepping, authors the nominal board and SPACE
    key, and verifies articulation, fixed-root, link, and scene-query surfaces.
    It identifies the native link-transform and nested root-prim bindings needed
    by the concrete session while consuming no governed attempt.
63. **LM4 pinned native mechanics profile:** ARM-276 applies and reads back the
    provisional seven-body mass, center-of-mass, inertia, gain, and limit profile
    without setting positions or targets. The result is a simulation prior, not
    physical system identification or contact qualification.
64. **LM4 corrected concrete native settle:** ARM-277 corrects the native root
    metadata and proves a 30-step settle-only session with bounded root drift,
    no route playback, no key contact, and no governed attempt consumption.
65. **LM4 concrete one-attempt binding:** ARM-278 binds the corrected session,
    route, mechanics profile, and reviewed ARM-262 through ARM-274 runtime stack
    behind the deferred ARM-254 worker. Its CLI remains a non-starting preflight
    and retains the exact authorization required for one future attempt.
66. **LM4 fail-closed memory preflight:** ARM-279 observes current Windows commit
    and physical-memory headroom before launch. An insufficient host fails before
    Isaac starts or an output is claimed and never grants a retry or authority.
67. **LM4 memory-recovery request:** ARM-280 binds the consumed memory-bootstrap
    failure to a passing retained preflight while requiring a distinct exact
    authorization and a fresh preflight at launch. The request is inert.
68. **LM4 memory-gated recovery claimant:** ARM-281 binds ARM-280 to a fresh
    ARM-254 preparation, collects and retains memory evidence before claim, then
    becomes single-use before its sole worker delegation. Definition is inert.
69. **LM4 recovery-claimant independent review:** ARM-282 independently verifies
    claimant lineage and the authorization -> memory -> receipt -> single-use ->
    worker order. Acceptance admits only a separately authorized simulation.
70. **LM4 fail-closed Isaac EULA preflight:** ARM-283 observes exact
    operator-provided `OMNI_KIT_ACCEPT_EULA=YES` without accepting terms or
    modifying the environment. Failure precedes attempt claim and Isaac start.
71. **LM4 EULA-ready recovery request:** ARM-284 binds the consumed ARM-280 EULA
    bootstrap failure to a passing ARM-283 receipt, a distinct output, and a new
    exact authorization. It requires fresh EULA and memory gates at execution.
72. **LM4 EULA- and memory-gated claimant:** ARM-285 rejects inexact authority,
    then requires and exclusively retains both fresh receipts before becoming
    single-use and delegating once to the reviewed worker. Build time is inert.
73. **LM4 EULA/memory claimant independent review:** ARM-286 reopens the exact
    claimant and worker lineage, statically verifies gate and consumption order,
    and rejects simulator, hardware, retry, or authority surfaces. A passing
    review admits only presentation of the separate ARM-284 authorization.
74. **LM4 first EULA-ready native attempt:** the exact ARM-284 authorization was
    consumed once. Fresh EULA and memory gates passed; Isaac started, opened the
    pinned USD, and created native PhysX views. A fast `SimulationApp.close()`
    path prevented the outer worker from terminalizing the pending claim. The
    incomplete attempt is retained unchanged and is not retryable.
75. **LM4 pre-shutdown terminalization correction (ARM-287):** retain atomic failure phase
    and exception evidence before session shutdown, including when shutdown
    does not return to Python.
76. **LM4 terminalization independent review (ARM-288):** statically require the
    terminal failure replacement to precede shutdown while continuing to reject
    attempt claims, simulator imports, joint commands, physics steps, retry, and
    hardware or physical authority. Rebuild the affected hash lineage after the
    review passes.
77. Expand only after a distinct, freshly gated and separately authorized
    recovery attempt produces reviewable terminal evidence.
78. **LM4 terminalized recovery request (ARM-289):** bind the immutable ARM-284
    pending claim, passing launch-gate receipts, Kit log, postmortem, and newly
    materialized ARM-287/ARM-288 correction lineage to a distinct output and
    authorization. Request construction is inert and cannot collect gates,
    claim an attempt, start Isaac, replay a trajectory, or grant hardware or
    physical authority.
79. The next implementation step is a single-use ARM-290 claimant and ARM-291
    independent review. Only that reviewed lineage may later accept the exact
    ARM-289 authorization with fresh EULA and memory gates.
80. **LM4 terminalized recovery claimant (ARM-290):** bind the ARM-289 request,
    worker, and ARM-287/ARM-288 correction lineage into a single-use adapter.
    Definition construction remains inert. Runtime admission requires an
    independent ARM-291 review, the exact ARM-289 authorization, and retained
    fresh passing EULA and memory receipts. Delegation consumes the callable
    before worker invocation, while failure terminalization remains required
    before simulator shutdown. The next step is ARM-291 independent review;
    no simulation, hardware, or physical authority is granted here.
81. **LM4 terminalized claimant independent review (ARM-291):** statically bind
    the ARM-290 definition and source while requiring exact authorization and
    source hashes, EULA-before-memory-before-receipt ordering, single-use
    consumption before worker delegation, terminal failure retention before
    simulator shutdown, and zero hardware or physical authority. Review
    construction consumes no attempt and starts no simulator. A future attempt
    still requires the separately supplied exact ARM-289 authorization and
    fresh passing gates against the merged, reproduced lineage.
82. **LM4 terminalized recovery result (ARM-289):** consume the authorization
    exactly once. EULA and memory gates passed, Isaac loaded the pinned scene
    and initialized physics, then runtime construction failed closed because
    the articulation adapter omitted the native `link_names` property. The
    failure was retained before shutdown with no route execution, targets,
    playback, contact, hardware access, or physical authority.
83. **Native link-inventory correction:** forward the real articulation's link
    ordering, pin the concrete binding to ARM-287 rather than ARM-274, add
    regression coverage, and merge only after the full cross-platform suite.
    ARM-289 remains consumed and cannot validate the correction by replay.
84. **Zero-motion inventory request and review (ARM-292/ARM-293):** bind the
    corrected source to the exact seven-link order and transform width. The
    independent review rejects physics stepping, settle, joint/trajectory,
    route-worker, transport, retry, and physical-authority surfaces. Request
    and review construction remain non-starting and consume no attempt.
85. **Completed runtime gate (ARM-294):** one separately authorized, no-retry
    native inventory observation passed on `2026-11-11`. It retained the exact
    seven-link order and one seven-transform batch with zero physics steps,
    targets, playback, contact, hardware access, or physical authority, then
    shut Isaac down. ARM-294 is consumed and cannot be replayed.
86. **Completed independent ARM-294 receipt review:** the non-starting reviewer
    rebound the retained receipt to ARM-292/ARM-293, verified every zero-motion
    and zero-authority field, and accepted the evidence while the ARM-295 output
    remained absent. Acceptance granted only fresh route-lineage construction.
87. **Completed fresh ARM-295 lineage plan:** the accepted receipt review now
    binds the exact corrected runtime sources, immutable ARM-289 terminal
    evidence, new attempt directory, and distinct fresh EULA and memory receipt
    locations. Construction started no runtime or backend.
88. **Completed independent ARM-295 lineage review:** the review re-hashed the
    receipt review, ARM-289 status, plan source, and every corrected runtime
    source, reconfirmed all governed outputs absent, and permitted only claimant
    construction without granting launch or physical authority.
89. **Completed fresh-gate ARM-295 claimant construction:** the claimant clones
    the reviewed one-attempt worker envelope to the new governed output while
    retaining the historical ARM-253 token only as an internal compatibility
    value. It has not collected gates or claimed an attempt.
90. **Completed independent ARM-295 claimant review:** the reviewer rebound the
    claimant to the plan/review, base worker, gate sources, and worker source,
    and verified the authorization-to-delegation order. It accepted only the
    simulation launch boundary; ARM-295, EULA, and memory outputs remain absent.
91. **Completed reproducible ARM-295 launch binding:** a dedicated entry point
    now re-hashes all eight corrected runtime sources, four worker inputs, and
    four route/runtime bindings before constructing the deferred native backend
    and delegating to the claimant. Import and validation remain inert; this
    layer adds no authority and has not created any ARM-295 output.
92. **Next runtime gate (ARM-295):** require a separate exact ARM-295 one-attempt
    authorization. At runtime, revalidate every corrected source, collect fresh
    passing EULA then memory evidence, retain both receipts exclusively, and
    delegate once to the terminalizing route-physics worker. Any mismatch or
    partial output fails closed with no retry. This gate remains simulation-only
    and grants no hardware or physical authority.

## Completion criterion

This plan has achieved its purpose when Tactevra can reproducibly generate a
physics-validated demonstration dataset from measured/provisional workcell
inputs, train a bounded policy that improves or complements deterministic
planning on held-out simulation, and use separately authorized physical traces
to reduce—not conceal—the sim-to-real uncertainty. It is not complete merely
because an Isaac scene renders, a policy loss decreases, or one simulated key
activates.

