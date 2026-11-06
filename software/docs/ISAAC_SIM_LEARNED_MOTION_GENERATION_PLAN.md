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
9. Expand only after each predecessor produces reviewable evidence.

## Completion criterion

This plan has achieved its purpose when Tactevra can reproducibly generate a
physics-validated demonstration dataset from measured/provisional workcell
inputs, train a bounded policy that improves or complements deterministic
planning on held-out simulation, and use separately authorized physical traces
to reduce—not conceal—the sim-to-real uncertainty. It is not complete merely
because an Isaac scene renders, a policy loss decreases, or one simulated key
activates.

