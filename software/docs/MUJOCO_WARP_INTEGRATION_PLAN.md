# MuJoCo Warp secondary-oracle integration plan

- **Document status:** Active architecture plan; MW0 through MW2P completed,
  MW2F schedule-scale FK parity active
- **Audience:** Runtime, simulation, AI, workcell, and repository contributors
- **Owner:** Simulation workstream with AI and arm-runtime review
- **Reviewed:** 2026-10-03
- **Authority:** Planning and software-test guidance only. This plan grants no
  hardware, motion, contact, calibration, model-promotion, or release authority.

## Decision

Integrate MuJoCo Warp as an optional, high-throughput **secondary simulation
oracle** after a bounded pilot. Keep Isaac Sim as the higher-fidelity visual
reference and keep RoCell's deterministic kinematics, admission, collision,
sequencing, and evidence services authoritative for software decisions.

MuJoCo Warp is valuable when many independent worlds, cameras, placements, or
physics variations must be evaluated on NVIDIA GPUs. It is not a substitute
for physical camera measurements, controller/URDF correlation, calibrated
target geometry, measured robot dynamics, or hardware qualification.

The pilot must answer three questions before broader adoption:

1. Does the imported robot and workcell agree with RoCell and Isaac on frames,
   link transforms, target projections, and geometric masks?
2. Does batching materially increase admitted observations per hour without
   buffer overflow, hidden scene changes, or lost evidence identity?
3. Which outputs are trustworthy enough for geometry screening, synthetic data
   generation, or contact sensitivity studies?

## Current fit

The designated workstation has two RTX 3090 GPUs with 24 GiB each and Python
3.12. This is a strong candidate for MuJoCo Warp's NVIDIA-oriented parallel
execution, but it is not compatibility evidence. The exact candidate package,
Warp/CUDA requirements, driver, GPU, and operating system must pass MW0.

The current RoArm URDF is a governed kinematic projection. It lacks enough
validated collision, inertia, drive, compliance, backlash, cable, and contact
properties to be a physical dynamic twin. High throughput cannot repair those
unknowns; the integration must label every added property as upstream,
measured, derived, provisional, or unknown.

## Architectural position

MuJoCo Warp consumes an already admitted runtime artifact. It never interprets
English, identifies a target, changes action order, performs IK silently, emits
controller commands, or grants a permit.

```text
user intent + observed scene
            |
            v
     AI ModelMotionBatch
            |
            v
 strict ingress + catalog + calibration + fresh state
            |
            v
 deterministic plan + IK + collision/smoothness screening
            |
            v
 admitted, hash-bound simulation schedule
            |
       +----+----------------------+----------------------+
       |                           |                      |
       v                           v                      v
 deterministic RoCell       Isaac Sim oracle      MuJoCo Warp oracle
 checks                     visual reference       batched stress path
       |                           |                      |
       +---------------------------+----------------------+
                                   |
                                   v
                    differential advisory evidence

 no serial transport, no wire JSON, no execution permit, no physical authority
```

The existing `ModelMotionBatch` boundary does not change. MuJoCo Warp sits
downstream of deterministic runtime admission and receives no language-model
output directly.

## Division of responsibility

| Need | Primary system | MuJoCo Warp role |
| --- | --- | --- |
| Intent and exact-text preservation | AI intent parser and deterministic compiler | None |
| Target identity and calibrated geometry | Shared catalog and calibration | Consume exact hashes only |
| IK and runtime admission | RoCell arm runtime | Replay admitted states; compare only |
| High-fidelity visual reference | Isaac Sim plus physical B0477 evidence | Paired low-fidelity comparison |
| Large pose and placement sweeps | RoCell policy plus simulation workers | Batched accelerator candidate |
| Segmentation, depth, and occlusion masks | Isaac/analytic geometry | Batched secondary source after parity |
| Contact sensitivity | Measured mechanics plus differential simulation | Provisional sweeps after MW4 |
| Hardware qualification | Physical arm, camera, host outcome evidence | No role |

### Explicit simulator job descriptions

Isaac Sim is the perception simulator. It owns rendered camera evidence,
lighting, obstruction appearance, camera-format studies, and visual scene
variation. MuJoCo Warp does not duplicate that qualification path.

MuJoCo Warp is the batched kinematics and provisional physics simulator. Its
near-term job is to evaluate many admitted joint states and answer how joint
position uncertainty propagates to tool-tip landing error. Once its kinematic
model passes differential parity, those exploratory distributions may inform
tool-tip error budgets, analytic arm-silhouette dilation studies, and offline
stress screening of runtime IK/collision results. They do not install a
physical bound or replace the deterministic runtime.

Kinematics and dynamics are separate claims. The governed model can support
kinematic forward projection because its joint frames and limits are bound.
Servo tracking, backlash, friction, overshoot, contact force, and key travel
remain unknown. Dynamic or contact results remain exploratory until measured
servo step responses and installed mechanics are bound to the model.

The first powered repeatability capture is a future physical transition. It
requires a separately predeclared plan with the workcell cleared of the
keyboard, phone, and hands; reduced speed and torque; an accessible emergency
stop; poses well inside joint limits; and a deterministic script with no model
in the loop. This integration stage performs zero hardware writes and zero
physical movements.

## Simulator-neutral contract

The first implementation should define a compact simulator-neutral envelope
rather than passing Isaac USD fields into MuJoCo Warp or MuJoCo XML fields into
core runtime code.

### Request

`rocell.simulation_oracle_request.v1` should bind:

- source commit, system manifest, target catalog, camera, robot, tool, and
  workcell hashes;
- exact admitted schedule hash and ordered timestamped joint states;
- named frames, units, transforms, and requested observations;
- backend ID and a backend-specific lock hash;
- seed set, world count, camera count, precision mode, and buffer limits;
- explicit `hardware_access=false`, empty transport capability, and
  `physical_authority=false`.

The request contains semantic labels only as trace metadata. Neither simulator
may use them to replan or generate a different target sequence.

### Receipt

`rocell.simulation_oracle_receipt.v1` should bind:

- the exact request and backend lock;
- loaded robot, scene, mesh, texture, and compiled-model hashes;
- GPU, driver, CUDA, Warp, MuJoCo, MuJoCo Warp, renderer, and precision details;
- world/step/camera counts, wall time, compilation time, throughput, and peak
  device memory;
- every overflow bit, dropped world, invalid value, and warning;
- FK, projection, segmentation, depth, collision, tracking, or contact metrics
  that were requested;
- per-world seeds and artifact-manifest hashes;
- repeated-run comparison and known nondeterminism;
- `PASS`, `REJECT`, or `ERROR`, limitations, zero hardware operations, and no
  gate promotion.

GPU pixel or contact bytes need not be byte identical across runs. Input
manifests must be identical, and numerical/reported differences must remain
inside thresholds frozen before the comparison.

## Planned repository boundary

```text
software/
  src/rocell/integrations/
    simulation_oracle/          # backend-neutral request/receipt and diff rules
    mujoco_warp/                 # optional adapter contract; no eager dependency
  integrations/mujoco_warp/
    README.md                    # external environment and evidence commands
    host_probe.py                # imports/version/GPU only
    asset_parity_probe.py        # URDF/MJCF mapping and frozen-pose comparison
    batch_probe.py               # throughput, overflow, repeatability
    render_parity_probe.py       # paired RGB/depth/segmentation comparison
    contact_probe.py             # added only after MW4 prerequisites pass
  config/
    mujoco_warp_toolchain_lock.json
  schemas/
    simulation_oracle_request_v1.schema.json
    simulation_oracle_receipt_v1.schema.json
  tests/fixtures/mujoco_warp/    # compact hardware-free fixtures only
```

MuJoCo, MuJoCo Warp, Warp, CUDA caches, compiled kernels, converted assets,
rendered datasets, checkpoints, videos, and full logs remain outside Git. Only
small reviewed fixtures and hash manifests may enter the source tree.

Ordinary unit tests must run without importing MuJoCo Warp. The adapter uses a
lazy external-runner boundary like the Isaac integration.

## Work packages

### MW0 — governance and isolated toolchain

**Objective:** establish whether the host can run one pinned candidate without
changing the existing Isaac or project Python environments.

**Deliverables**

- Apache-2.0 license and redistribution record;
- exact package/version candidate, hashes, Python, CUDA/driver, Warp, MuJoCo,
  GPU, and operating-system receipt;
- isolated external environment, initially under `C:\MuJoCoWarp\`;
- CPU debug import and single-GPU CUDA import smoke;
- installation inventory and uninstall/rebuild instructions;
- hardware-free fake-adapter fixtures for CI.

**Exit gate**

- exact version and dependency hashes reproduce;
- both RTX 3090 devices enumerate independently;
- one minimal world steps on CPU and each GPU;
- a mismatched lock rejects before model load;
- no package, cache, or large generated file enters the repository;
- hardware writes and physical movements remain zero.

**MW0 result (2026-10-03): `PASS`.** The isolated candidate is MuJoCo Warp
3.13.0, MuJoCo 3.14.0, Warp 1.17.0, NumPy 2.5.3, and Python 3.12.0. One
16-step pendulum world passed on CPU, `cuda:0`, and `cuda:1`; every result had
finite state, changed state, and `overflow=[0]`. The exact lock and a
standard-library-only pre-import host validator are now repository controlled.
This advances only to MW1 asset/FK work. It does not validate RoArm import,
rendering, contact, throughput, training value, or physical transfer. Evidence
is `E-20261003-AI-561`.

### MW1 — asset import and kinematic parity

**Objective:** prove that the governed robot projection means the same thing in
RoCell, Isaac, standard MuJoCo, and MuJoCo Warp.

**Deliverables**

- exact URDF/mesh import or governed URDF-to-MJCF conversion receipt;
- joint/link/axis/limit/unit mapping;
- property-provenance inventory for collision, inertia, damping, actuator, and
  contact fields;
- replay of the existing frozen pose corpus;
- four-way transform and tool-point differential report.

**Exit gate**

- every expected joint and link maps exactly once;
- no importer default is accepted without being reported;
- fixed-pose link transforms satisfy the parity limits frozen for the Isaac
  import campaign, initially 0.1 mm translation and 0.05 degrees rotation;
- standard MuJoCo and MuJoCo Warp agree inside a separately frozen float32
  tolerance;
- any unknown property blocks its associated dynamic or contact claim.

**MW1 result (2026-10-03): `PASS_KINEMATIC_ONLY`.** Direct URDF load failed
because the governed projection intentionally omits inertia. A hash-bound
conversion therefore adds explicit placeholder inertia solely to compile FK;
dynamics and contact remain blocked. All six movable joints and eight non-world
links map exactly once. Across `zero`, `home`, and `ready`, standard MuJoCo
matches the governed RoCell hand point within `1.17e-13` mm and `2.96e-6`
degrees; MuJoCo Warp matches standard MuJoCo within `4.24e-5` mm and
`2.42e-6` degrees. The retained Isaac comparison also remains inside its frozen
limits. Evidence is `E-20261003-AI-562`. MW2 may test batch throughput, but MW1
does not authorize dynamics, collision, contact, rendering, or training use.

### MW2 — batch throughput, overflow, and repeatability

**Objective:** determine whether MuJoCo Warp provides enough acceleration to
justify maintaining the backend.

**Deliverables**

- fixed benchmark matrix at 1, 32, 256, 1,024, and 4,096 worlds, bounded by
  available memory;
- separate device-0, device-1, and explicitly sharded dual-GPU runs;
- compile time, steady-state steps/s, observations/hour, memory, transfer time,
  and overflow inventory;
- repeat runs with identical manifests and predeclared numerical tolerances;
- equivalent low-fidelity Isaac or CPU-MuJoCo comparison where meaningful.

**Exit gate**

- zero unhandled overflow bits, invalid values, lost worlds, or silent warnings;
- repeated aggregate metrics remain within frozen tolerances;
- the target workload achieves at least three times the admitted
  observations/hour of its comparison path after excluding one-time compile
  cost, or a documented capability unavailable from the comparison path;
- multi-GPU results remain separate evidence shards unless explicit aggregation
  rules pass.

Failure closes the acceleration path without affecting Isaac or RoCell.

**MW2 result (2026-10-03): `RESEARCH_ONLY`.** All 45 GPU runs across both
devices, five batch sizes, and three repeats preserved every world, remained
finite, reported zero overflow, and repeated numerically exactly within the
frozen summary. At 4,096 worlds, `cuda:0` reached 1,322,545 world-steps/s
(4.07x standard MuJoCo) and `cuda:1` reached 1,239,597 world-steps/s (3.81x).
At 1,024 worlds, speedup was only 0.64x and 0.60x, below the frozen 3x gate on
both devices. The gate was not changed after results. This closes the declared
acceleration-adoption path while retaining the backend for bounded research;
Isaac, RoCell, current training, and physical priorities are unchanged.
Evidence is `E-20261003-AI-563`.

**MW2R large-batch specialization (2026-10-03): `RESEARCH_ONLY`, capacity
confirmed.** Separate deterministic pose populations of 4,096, 8,192, and
16,384 worlds passed finite-state, world-preservation, zero-overflow, exact
repeatability, and timing gates on both GPUs. GPU 0 reached 5.225 million and
GPU 1 reached 4.773 million world-steps/s at 16,384 distinct poses. Concurrent
4,096-world shards were safe and delivered 2.189 million aggregate
world-steps/s, but scaled 1.665x against the separately frozen 1.70x gate. The
near miss is retained unchanged. It identifies concurrent host orchestration at
the smallest large batch as the next optimization target; it does not erase
the demonstrated 16,384-world capacity or alter the general MW2 rejection.
Evidence is `E-20261003-AI-564`.

### MW2S — persistent deterministic campaign sharding

**Result (2026-10-03): `RESEARCH_ONLY`; deterministic campaign sharding
validated, saturation gate failed.** This successor is
separate from MW2 and MW2R. It will freeze a compact, hash-bound manifest for
two disjoint eight-shard campaigns. Every shard contains 16,384 distinct joint
states generated from its recorded seed under the MW2R joint-limit contract.
Each GPU worker will load the exact MW1 model and allocate its world batch once,
then replay all eight shards in the same process. Sequential runs on each GPU
will establish the baseline before the unchanged manifest is run concurrently.

Frozen gates are: exact manifest and MJCF identity; disjoint shard identities,
seeds, and initial-state hashes; 16,384 unique initial poses per shard; finite
state; exact world count; zero overflow; deterministic replay within `1e-6`;
complete receipt coverage; and concurrent campaign wall-time scaling of at
least `1.70x` relative to the sum of the two sequential campaign wall times.
The wall-time metric includes child launch and receipt writing. Failure remains
evidence and cannot rewrite either earlier result. The scope remains kinematic
research only with zero rendering, training, contact, hardware writes, physical
movement, or execution authority.

The exact sixteen-shard manifest passed identity, disjoint-seed, unique-pose,
finite-state, world-count, zero-overflow, replay, receipt, and cross-mode state
parity checks. Each worker loaded the model once and reused one allocation for
all eight shards. Complete sequential wall time was 19.283 seconds; concurrent
wall time was 12.550 seconds, or 1.537x scaling against the frozen 1.70x gate.
The concurrent workers slowed to 10.54 and 10.26 seconds from sequential worker
times of 7.95 and 7.76 seconds, locating the remaining limit in shared host,
memory-transfer, or device-orchestration contention. The failed performance
gate is retained. The deterministic manifest and receipt machinery remain
useful for replayable offline research but do not constitute backend adoption.
Evidence is `E-20261003-AI-565`.

### MW2Q — resumable independent GPU queues

**Result (2026-10-03): `ADMIT_RESUMABLE_RESEARCH_QUEUE`.** This increment
retains the exact MW2S manifest and executes each device's eight shards as an
independent resumable queue. A completed shard is reusable only after strict
schema, manifest, MJCF, device, identity, seed, cardinality, safety,
repeatability, state-hash, authority, and canonical-receipt validation. New
receipts are written to a same-directory temporary file, flushed, and promoted
with atomic replacement. Invalid receipts are preserved under a quarantine
identity derived from their byte hash and the affected shard returns to the
pending queue.

Frozen gates are: exactly sixteen admitted shard receipts and no unallowlisted
files; atomic writes leave no temporary files; a clean second invocation skips
all sixteen shards without model load or allocation; and a copied recovery
rehearsal with one deliberately altered receipt quarantines that exact file,
reruns exactly one shard, and retains the other seven device receipts byte for
byte. Failure remains evidence. This provides restartability only and grants no
rendering, training, contact, hardware, transport, permit, or execution
authority.

The first run atomically produced and admitted all sixteen receipts in 14.881
seconds, with no temporary files left behind. An unchanged second invocation
finished in 0.106 seconds, skipped all sixteen shards, and performed zero model
loads or allocations. In a copied CUDA 0 queue, one deliberately altered `s03`
receipt failed both seed and canonical-hash validation, was retained under its
byte hash, and caused exactly one shard execution; the other seven receipts
remained byte identical. This admits restart and recovery mechanics only. It
does not alter the MW2/MW2R/MW2S performance decisions or qualify new physics.
Evidence is `E-20261003-AI-566`.

### MW2P — provenanced kinematic scenario profiles

**Result (2026-10-03): `ADMIT_EXPLORATORY_PROFILE_PIPELINE`.** A strict versioned
profile will describe only independent uniform joint-position and velocity
ranges, the exact governed MJCF, campaign cardinality, and a source artifact
identity. The compiler will derive every shard seed from the canonical profile
hash. Bounds must use the exact six-joint order, remain within governed joint
limits, and contain finite ordered values. Compiled manifests will carry their
profile and source identities into every resumable shard receipt.

An exploratory rehearsal may use an explicitly synthetic source artifact and
must remain `EXPLORATORY_ONLY`. Qualifying mode must reject synthetic sources,
missing artifacts, altered artifact bytes, assumed ranges, manifest changes,
and authority fields. Frozen gates are deterministic byte-identical compilation,
sixteen unique shard seeds, strict tamper rejection, successful exact assembly
through the MW2Q queue, and a clean all-skip resume. This does not supply or
infer physical uncertainty, dynamics, contacts, camera properties, catalog
geometry, planner output, permits, transport, or execution authority.

An explicitly synthetic source and profile compiled byte identically twice,
produced sixteen unique derived seeds, and remained stamped
`EXPLORATORY_ONLY`. The resumable queue executed and assembled all sixteen
profile-bound receipts, then skipped all sixteen on an unchanged rerun with
zero model loads or allocations. Synthetic qualifying mode failed closed. A
seed-altered manifest failed both derivation and manifest-hash validation before
GPU initialization. No physical profile was created or claimed. Evidence is
`E-20261003-AI-567`.

### MW2F — schedule-scale forward-kinematics differential

**Result (2026-10-03): `PASS_KINEMATIC_ONLY`.** The frozen increment reused the exact 133-state schedule
bundle from `E-20260929-INT-451`, its retained Isaac replay receipt, the
governed URDF, and the MW1 generated MJCF. Replay every ordered joint vector
through the arm-runtime reference, standard MuJoCo, and MuJoCo Warp. Compare
the retained Isaac result against the same runtime reference and, when a new
full-sample Isaac receipt is available, perform direct pairwise comparisons.

Frozen gates reuse established limits rather than thresholds selected from the
new result: standard MuJoCo versus runtime at most 0.1 mm; MuJoCo Warp versus
standard MuJoCo at most 0.01 mm; and retained Isaac versus runtime at most
0.25 mm. Every source and generated model must match its exact SHA-256, all 133
samples must preserve order and remain finite, and all authority fields must
remain empty/false.

Same-stack replay must be byte identical after excluding measured wall time.
Receipts record the operating system, Python, MuJoCo, MuJoCo Warp, Warp,
driver, and GPU identity. A future different driver/GPU/toolchain is expected
to reproduce within the frozen numerical tolerances rather than byte for byte.
This increment claims kinematic differential evidence only: no uncertainty
qualification, silhouette margin, collision validity, dynamics, contact,
rendering, hardware access, or physical authority.

All 133 ordered states passed. Standard MuJoCo agrees with RoCell's current
forward kinematics to `3.1776437161565096e-13 mm`; MuJoCo Warp agrees with
standard MuJoCo to `0.000151675112855002 mm`; and the retained Isaac replay
remains within `0.07684842940066568 mm` of the schedule reference. Two CUDA 0
receipts are byte identical, and CUDA 0 versus CUDA 1 tool-tip outputs are
identical. This expands MW1 from three fixed poses to a representative motion
schedule. The retained Isaac v1 receipt reports the all-sample maximum but
stores per-sample coordinates only for contact endpoints, so a new full-sample
Isaac receipt remains necessary for direct pairwise four-backend rows. Evidence
is `E-20261003-AI-568`.

### MW2FI — full-sample Isaac closure

**Result (2026-10-03): `PASS_KINEMATIC_ONLY`.** The retained Isaac v1
receipt and add an opt-in v2 output that retains all 133 ordered sample tips.
The v2 receipt must bind the same schedule, imported USD, import receipt,
virtual profile, joint order, tool length, and zero-authority fields. A strict
admission step will compare every Isaac tip against the exact RoCell, standard
MuJoCo, and MuJoCo Warp rows from MW2F.

Frozen thresholds remain unchanged: Isaac versus the schedule reference at
most `0.25 mm`, MuJoCo versus RoCell at most `0.1 mm`, and MuJoCo Warp versus
MuJoCo at most `0.01 mm`. The new direct pairwise Isaac comparisons are
reported without adding a post-result threshold. Same-stack Isaac repeats must
produce byte-identical canonical receipts. This remains teleport-only
kinematic evidence with zero physics steps, hardware writes, or movement.

Two independent v2 replays retain every ordered row and are byte identical.
Direct maxima across all 133 poses are `0.0002710608315793465 mm` for Isaac
versus RoCell, `0.00027106083166082413 mm` for Isaac versus standard MuJoCo,
and `0.0002801399314244456 mm` for Isaac versus MuJoCo Warp. All preexisting
backend gates pass. Evidence is `E-20261003-AI-569`.

### MW3 — camera and geometry parity

**Objective:** decide which rendered outputs can supplement the Isaac corpus.

**Deliverables**

- paired scene, pose, camera, target, light, mesh, and seed identities;
- RGB, depth, segmentation, safe-region, and parked-arm mask comparisons;
- target projection and mask-overlap error by target, camera, and scene;
- low-contrast cable/edge audit against lossless Isaac reference renders;
- renderer-domain label in every data row.

**Exit gate**

- camera transforms and target projections pass thresholds frozen before paired
  pixels are inspected;
- segmentation and depth differences are bounded and attributed;
- parked-arm occlusion decisions agree on the frozen target set;
- no RGB training use is allowed merely because geometric parity passes;
- visual-model use additionally passes the applicable lossless/YUY2
  detectability and measured camera-noise rules.

Isaac remains the visual reference if MuJoCo Warp's low-fidelity renderer cannot
preserve dark-cable, glare, material, or lighting signals.

### MW4 — collision and contact differential

**Objective:** use batched physics only after the modeled properties support the
claim being tested.

**Prerequisites**

- complete collision geometry for every required body;
- measured or explicitly provisional mass, inertia, damping, friction, drive,
  tool, key travel, spring, activation, and surface parameters;
- approved intended-contact policy and collision exclusions;
- MW1 parity and MW2 overflow gates passed.

**Deliverables**

- replay of already-admitted noncontact and representative contact schedules;
- MuJoCo CPU, MuJoCo Warp, Isaac, and deterministic-screen differential;
- parameter sensitivity ranges rather than one asserted value;
- contact order, penetration, impulse/force, travel, settle, and disagreement
  evidence.

**Exit gate**

- no prohibited contact is hidden by filtering;
- intended contacts occur only in declared phases and target regions;
- engine disagreements are reported per event;
- provisional parameters produce sensitivity evidence only;
- no simulation contact result authorizes hardware contact.

### MW5 — synthetic-data admission

**Objective:** admit only the MuJoCo Warp outputs that passed the relevant
parity gates.

**Permitted first uses**

- geometry masks and target visibility;
- placement and pose stress cases;
- collision-negative mining;
- balanced rare-case sampling for later Isaac rendering;
- exploratory depth/segmentation training with backend labels.

**Rules**

- train, development, and evaluation identities remain disjoint by scene,
  target, obstruction asset, lighting, and backend where applicable;
- the renderer family and exact lock are features in the manifest;
- a MuJoCo Warp frame cannot be relabeled as Isaac or physical data;
- the load-time camera model applies the same delivered-YUY2 conversion and
  measured noise contract when the model is meant to consume B0477-like input;
- existing v5.5 identities and gates do not change silently;
- synthetic success remains a simulation claim.

**Exit gate**

- independent admission reproduces every identity and source hash;
- no truth channel reaches model input;
- the candidate beats its frozen baseline and passes backend-specific hard-case
  diagnostics;
- physical transfer remains separately unopened or explicitly reported.

### MW6 — optional policy-learning research

Reinforcement learning or learned motion refinement is deferred until MW0-MW5,
physical calibration, measured dynamics, and a separate shared contract are
complete. A learned policy may propose bounded research outputs only. It may
not bypass `ModelMotionBatch`, deterministic planning, collision screening,
fresh-state checks, execution authorization, or hardware transport controls.

## Adoption decisions

After each work package, record one disposition:

- `ADOPT_FOR_DECLARED_SCOPE` — list the exact outputs and downstream consumers;
- `RESEARCH_ONLY` — retain results but prohibit qualification or selection use;
- `REJECT_BACKEND` — preserve failed evidence and stop dependent packages;
- `BLOCKED` — name the missing external evidence or upstream contract.

Scopes are cumulative only through explicit review. Passing FK parity does not
admit rendered RGB; passing renderer geometry does not admit contact physics;
passing synthetic model gates does not qualify physical transfer.

## Interaction with current priorities

The pilot runs in parallel with target-catalog completion and B0477 work. It
must not delay:

1. direct Grave measurement and the shared 80-target catalog;
2. v5.5 lossless Isaac rendering and load-time camera model;
3. physical camera calibration and measured noise;
4. deterministic planner/compiler and arm-runtime integration.

MW0 and MW1 are useful while physical measurements are pending. MW3 may inform
future corpus production, but the current v5.5 campaign remains on its existing
Isaac path unless a separate pre-render amendment is reviewed.

## Initial execution order

1. Record the candidate version and external-environment lock without installing
   into the repository environment.
2. Run host compatibility and minimal CPU/GPU smokes.
3. Convert/load the governed RoArm asset and compare frozen poses.
4. Benchmark batch sizes and inspect every overflow field.
5. Build a small paired Isaac/MuJoCo Warp geometry-render corpus.
6. Decide permitted scopes before adding contact models or training data.
7. Add contact sensitivity only after measured property prerequisites exist.

## Upstream references

- [MuJoCo Warp repository](https://github.com/google-deepmind/mujoco_warp)
- [MuJoCo Warp documentation](https://mujoco.readthedocs.io/en/latest/mjwarp/)
- [MuJoCo Warp API](https://mujoco.readthedocs.io/en/3.13.0/mjwarp/api.html)
- [Existing Isaac Sim integration plan](ISAAC_SIM_INTEGRATION_PLAN.md)
