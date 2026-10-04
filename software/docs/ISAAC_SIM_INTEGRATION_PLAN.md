# Tactevra Isaac Sim integration plan

- **Document status:** Active integration plan
- **Audience:** Runtime, simulation, AI, workcell, and repository contributors
- **Owner:** Runtime and simulation workstream, with AI and repository review
- **Reviewed:** 2026-09-29
- **Authority:** Planning and software-test guidance only. This plan grants no
  hardware, motion, contact, calibration, or release authority.

## Objective

Add NVIDIA Isaac Sim as a second, higher-fidelity simulation oracle for
Tactevra. The integration should replay the same admitted trajectory that the
runtime has already produced, observe the simulated robot and workcell, and
return a reproducible evidence receipt. It should help answer questions that
the current deterministic simulators intentionally simplify:

- Does full-body geometry remain clear throughout a smooth trajectory?
- Does the simulated articulation follow the requested joint schedule?
- Where and when does the tool or gripper contact a keyboard surface?
- How sensitive is a result to friction, damping, key travel, camera noise, or
  workcell placement?
- Can a synthetic camera campaign produce useful, truth-labeled inputs for the
  separately evaluated perception workstream?

The first integration target is a bare-gripper, noncontact keyboard hover. A
representative key-contact model follows only after transform and collision
parity pass. Full keyboard mechanics, ROS 2, MoveIt, learned control, and live
hardware dispatch are later options, not prerequisites.

## Non-goals

This work does not:

- make Isaac Sim the controller or safety authority;
- send AI model output directly to a simulated or physical articulation;
- treat a simulated pass as evidence of physical clearance, calibration,
  contact, input registration, or safety;
- replace the existing deterministic kinematics, route screening, controller
  emulator, replay, or evidence layers;
- train the language or vision models;
- require Isaac Sim or an NVIDIA GPU for ordinary unit tests, documentation
  checks, pull-request review, or a hardware-free newcomer walkthrough;
- vendor NVIDIA software, generated caches, or large USD assets into this
  repository by default.

## Architectural position

Isaac Sim is an advisory downstream consumer, not an alternate command path.

```text
user request + camera evidence
              |
              v
       Tactevra AI proposal
              |
              v
 schema/frame/calibration/admission checks
              |
              v
 Tactevra plan + IK + smooth trajectory + hashes
              |
       +------+------------------+
       |                         |
       v                         v
 current deterministic       Isaac adapter
 simulation/replay              |
                                 v
                       pinned USD workcell
                                 |
                                 v
                   collision/contact/tracking sensors
                                 |
                                 v
                    hash-bound advisory receipt
                                 |
                                 v
                   differential result and review

       no live transport, no physical permit, no gate promotion
```

The adapter accepts only canonical runtime records. It must not reinterpret
English, identify keys from their names, solve a different route silently, or
infer missing calibration. Missing or contradictory input fails closed.

### Relationship to MuJoCo Warp

Isaac remains the higher-fidelity visual reference. The planned
[MuJoCo Warp integration](MUJOCO_WARP_INTEGRATION_PLAN.md) is a separate
high-throughput secondary oracle that consumes the same admitted schedule.
MuJoCo Warp may accelerate batched geometry, placement, overflow, and later
contact-sensitivity work only after paired parity gates pass. Neither simulator
may promote the other, and disagreement is retained as evidence rather than
resolved by silently preferring one backend.

## Compute and execution assumption

The planned integration runner may use a workstation with two RTX 3090 GPUs.
That capacity removes the need to optimize the first implementation for a
small developer machine, but it is not a compatibility claim:

- initial acceptance requires one pinned, supported GPU execution path;
- no test may assume that one Isaac Sim process automatically combines both
  GPUs;
- independent shards may be assigned to separate GPUs only after a single-run
  result is deterministic and isolated;
- the receipt records the selected GPU, driver, renderer, physics backend, and
  application build;
- normal CI uses schemas, fixtures, and a fake adapter rather than Isaac Sim.

The first runner should use Isaac Sim's standalone Python/headless workflow.
Interactive GUI use is useful for inspection but is not the evidence-producing
path.

## Integration principles

1. **Pin the entire toolchain.** Record the exact Isaac Sim release, container
   or installation identity, extension versions, driver, scene asset hashes,
   and relevant settings. `latest` is never an accepted evidence identity.
2. **Import once, validate before use.** Convert the selected RoArm-M3 source
   to a governed USD asset, inspect the articulation, and retain a manifest
   tying the generated asset to its exact source.
3. **Use native articulation control first.** Direct joint-target replay is the
   shortest path to parity with Tactevra's existing planner. ROS 2 and MoveIt
   remain optional comparison layers until the native path passes.
4. **Keep core contracts simulator-neutral.** NVIDIA imports and APIs stay
   inside `software/integrations/isaac_sim/`; core planning code must not
   depend on Isaac modules.
5. **Make hidden defaults impossible.** Gravity, units, solver step, substeps,
   collision margins, material properties, drive stiffness/damping, key
   travel, camera settings, and random seeds are explicit inputs or the run is
   rejected.
6. **Separate modeled truth from observation.** AI evaluation receives rendered
   images and declared metadata, not simulator poses or semantic target truth.
   Ground truth is retained separately for scoring.
7. **Preserve zero authority.** The runner has no serial/network arm adapter,
   consumes no physical permit, emits no RoArm wire command, and cannot change
   controlled build or release gates.
8. **Test disagreement.** A result is useful when Isaac and the existing
   simulator agree and when they disagree. Differences must be classified,
   not hidden behind one aggregate pass/fail value.

## Planned repository boundary

WP0 established the simulator-neutral contract package, schemas, placeholder
lock, and fixtures. Simulator-dependent modules remain planned and are added
only when their work package begins.

```text
software/
  src/rocell/
    integrations/isaac_sim/
      contracts.py             # canonical request/receipt validation
      fake_adapter.py          # hardware-free lifecycle double
      toolchain_lock.py        # exact external-runner selection gate
  integrations/
    isaac_sim/
      README.md                 # setup, status, and contributor commands
  config/
    isaac_sim_toolchain_lock.json
  schemas/
    isaac_sim_run_request_v1.schema.json
    isaac_sim_run_receipt_v1.schema.json
  assets/
    isaac_sim/
      manifest.json             # identities only; large assets remain external
  tests/
    fixtures/isaac_sim/         # compact requests, receipts, and invalid cases
```

Planned NVIDIA-dependent modules (`bootstrap.py`, `asset_import.py`,
`trajectory_adapter.py`, and `observations.py`) belong beside the contract
package only after the exact external toolchain is selected.

Generated USD, textures, rendered datasets, shader caches, application data,
and simulator logs remain outside source control unless the artifact policy
explicitly admits a small review fixture. The manifest uses the repository's
[external artifact contract](../../docs/EXTERNAL_ARTIFACTS.md) for anything
stored elsewhere.

## Contract 1: run request

`rocell.isaac_sim_run_request.v1` will be the only accepted job envelope. At
minimum it binds:

| Field group | Required content |
| --- | --- |
| Identity | Schema, request ID, creation tool, canonical request hash |
| Toolchain | Exact Isaac Sim build, installation/container digest, extension lock, settings profile |
| System | Tactevra system-manifest ID/hash, model/profile/catalog hashes, source revision |
| Scene | USD scene and arm asset digests, meters-per-unit, up axis, physics settings, random seed |
| Frames | Named source/destination frames and complete transform identities; no anonymous XYZ |
| Articulation | Ordered joint names, initial positions, drive configuration, joint/velocity/effort bounds |
| Trajectory | Exact admitted trajectory hash and timestamped joint targets; semantic labels are optional metadata only |
| Observation | Required link transforms, clearances, collisions, contacts, effort, joint tracking, and cameras |
| Authority | `hardware_access=false`, `physical_authority=false`, and an empty transport/command capability set |

The request validator rejects unknown joint names, reordered joints, missing
units, unbound transforms, unselected toolchain fields, nonfinite values,
non-monotonic times, settings outside the locked profile, and hashes that do
not reproduce.

## Contract 2: run receipt

`rocell.isaac_sim_run_receipt.v1` records observations rather than authority.
It includes:

| Field group | Required content |
| --- | --- |
| Binding | Request ID/hash and every loaded toolchain/scene/asset digest |
| Execution | Start/end time, step count, fixed time step, substeps, seed, GPU, driver, renderer, physics backend |
| Import parity | Joint/link mapping, dropped or added degrees of freedom, units/up-axis result, FK comparison summary |
| Tracking | Per-joint maximum/RMS error, settle observations, saturation or limit events |
| Geometry | Minimum declared clearance, collision/contact event sequence, involved prim paths, timestamps |
| Contact | Position, normal, impulse/force/effort observations, dwell, penetration, key travel if modeled |
| Vision | Camera/intrinsic/extrinsic identity, frame count, frame digests, separately stored truth-manifest digest |
| Differential | Comparison against the deterministic simulator and categorized disagreements |
| Reproducibility | Canonical result signature and repeat-run comparison |
| Disposition | `PASS`, `REJECT`, or `ERROR` with explicit reason codes and limitations |
| Authority | `hardware_access=false`, `wire_commands=[]`, `physical_authority=false`, `gate_promotions=[]` |

A `PASS` means only that the requested simulation checks passed under the
exact modeled inputs. It cannot establish physical calibration, clearance,
contact force, keyboard activation, successful typing, or readiness to move.

## Asset strategy

### RoArm-M3

The current pinned URDF is a kinematic projection. It intentionally omits
visuals, collision geometry, inertials, transmissions, and dynamic parameters;
some limits are placeholders unsuitable for dynamic simulation. The Isaac
asset therefore needs an enrichment manifest rather than silent importer
defaults.

Each added property is labeled as one of:

- `upstream`: directly traceable to the selected upstream artifact;
- `measured`: tied to a retained physical measurement record;
- `derived`: calculated from a named source and method;
- `provisional`: an explicit sensitivity-study assumption; or
- `unknown`: blocks the affected acceptance claim.

The asset cannot leave import qualification while required link geometry,
joint axes, limits, mass/inertia, or drive parameters are unknown. Provisional
dynamics may be used for a labeled sensitivity run, never presented as a
validated digital twin.

### Workcell and keyboard

Build the device model in three stages:

1. **Rigid target surface:** keyboard envelope and per-key target regions for
   noncontact hover/collision checks. No activation claim.
2. **Representative mechanics:** model a small set spanning the intended
   workspace—initially `H`, `I`, `1`, `Space`, `Enter`, and one punctuation
   key—with explicit travel, spring/damping, activation, release, and geometry.
3. **Expanded keyboard:** add broader or full mechanics only after the
   representative set passes measurement and repeatability gates.

The board, robot base, camera, keyboard, phone, fixtures, cables, and tool are
separate versioned scene assets. Approximate cable envelopes may support
conservative screening, but cannot be represented as precise physical truth.

### Camera

The selected fixed-camera profile supplies the first render contract. The USD
camera must bind the same declared frame, intrinsics, distortion treatment,
resolution, exposure assumptions, and artifact identity used by Tactevra's
vision boundary. Simulated domain randomization records every varied parameter
and seed.

## Work packages and acceptance gates

### WP0 — decision and toolchain lock

**Current status:** Contract and fake-adapter foundation implemented. Exact
Isaac Sim installation selection, extension/settings export, and applicable
license review remain open on the designated compute runner.

**Deliverables**

- select one exact Isaac Sim build supported by the runner;
- record install/container digest, extensions, driver constraints, launch
  method, and license/redistribution disposition;
- create request/receipt schemas and invalid fixtures;
- document large-artifact storage and retention.

**Exit gate**

- a clean runner can reproduce the version report from the lock;
- unset, mismatched, or unsupported versions reject before scene load;
- schema/fake-adapter tests pass in ordinary CI;
- no NVIDIA package or generated asset is accidentally committed.

### WP1 — asset import and kinematic parity

**Deliverables**

- governed URDF-to-USD import;
- joint/link/axis/unit mapping report;
- deterministic pose corpus shared with Tactevra FK;
- enriched-asset manifest with property provenance.

**Exit gate**

- every expected joint and link maps exactly once, with no unreviewed DOF;
- joint zero, sign, axis, units, limits, and parentage agree;
- across the fixed corpus, link transforms remain within a predeclared parity
  tolerance initially targeted at `0.1 mm` translation and `0.05 degrees`
  rotation; any tolerance change is reviewed before rerunning the corpus;
- impossible or incomplete asset configurations fail closed.

### WP2 — rigid workcell and collision differential

**Deliverables**

- RC03 board, keyboard envelope, base, camera-support, and conservative fixture
  collision assets;
- existing deterministic route corpus translated without replanning;
- differential collision/clearance report.

**Exit gate**

- the same request produces the same trajectory hash in both paths;
- every collision disagreement identifies time, bodies, geometry sources, and
  which model lacks information;
- no collision is silently filtered by target identity;
- one bare-gripper keyboard hover completes with no contact claim.

### WP3 — smooth trajectory replay

**Deliverables**

- replay of the existing jerk-bounded joint schedule;
- joint-state, effort, limit, tracking, and settle observations;
- cancellation and timeout behavior;
- deterministic rerun signature.

**Exit gate**

- requested and observed samples use the same monotonic clock basis;
- no unexpected limit, saturation, or unreported contact event occurs;
- tracking thresholds are declared before the acceptance run;
- ten reruns preserve categorical outcomes and remain inside declared numeric
  drift bounds;
- interruption produces a receipt and never starts a later segment.

### WP4 — representative key contact

**Deliverables**

- measured/provisional key mechanism records for the representative set;
- approach, contact, dwell, release, and retract observations;
- sensitivity sweeps for key travel, stiffness, damping, friction, tool length,
  and placement uncertainty.

**Exit gate**

- activation is resolved from geometry and mechanism state, not a planned key
  name or expected character;
- off-center, shallow, excessive, double-contact, and neighboring-key cases
  reject distinctly;
- each result reports the assumed/measured provenance of its mechanics;
- results remain simulation evidence and cannot qualify physical contact.

### WP5 — camera and Replicator campaign

**Deliverables**

- fixed-camera render profile;
- parameterized lighting, blur, glare, occlusion, placement, and material
  variations;
- image manifests, separate ground truth, and deterministic splits;
- adapter feeding actual model predictions into the existing planning path.

**Exit gate**

- train/validation/test scene identities cannot overlap accidentally;
- inference receives pixels and allowed metadata only;
- ground truth is inaccessible to the model-facing process and used only for
  scoring;
- failures separate perception, admission, planning, and simulation causes;
- retained datasets comply with artifact and privacy policy.

### WP6 — repeatable GPU regression runner

**Deliverables**

- unattended pinned headless entry point;
- one-GPU baseline and optional independent multi-GPU sharding;
- resumable job manifest and per-case receipt verification;
- compact summary suitable for pull-request or nightly review.

**Exit gate**

- a stopped shard cannot be mistaken for a completed campaign;
- duplicate, missing, stale, or mixed-version receipts reject;
- rerunning an exact job produces the declared reproducibility result;
- failure logs identify the first contract, asset, simulation, or comparison
  boundary that failed.

### WP7 — optional ROS 2 and planner comparison

Only begin after WP3 passes. Use the Isaac ROS 2 bridge or in-process
`ros2_control` to compare external control and MoveIt/RMPflow planning without
changing the authoritative Tactevra request/receipt contracts.

**Exit gate**

- planner identity and configuration are explicit;
- any newly planned path is a separately identified candidate, not a replay of
  the original Tactevra trajectory;
- comparisons preserve equivalent start state, target, constraints, collision
  scene, and evaluation metrics;
- no ROS node exposes or receives live-arm credentials in the simulation job.

## Failure taxonomy

Every failed run should select at least one stable reason family:

| Family | Examples |
| --- | --- |
| `TOOLCHAIN` | Unpinned version, extension mismatch, unsupported driver |
| `REQUEST` | Invalid schema, hash mismatch, missing units, non-monotonic samples |
| `ASSET` | Missing prim, incomplete articulation, unknown required dynamics |
| `FRAME` | Axis/sign mismatch, unresolved transform, unit/up-axis disagreement |
| `TRACKING` | Limit, saturation, excessive error, failure to settle |
| `COLLISION` | Unexpected contact, insufficient clearance, penetration |
| `CONTACT` | Wrong region, ambiguous activation, excessive force/travel, double event |
| `VISION` | Invalid frame, hidden truth leak, failed render or model abstention |
| `NONDETERMINISM` | Repeat signatures or categorical outcomes disagree |
| `INFRASTRUCTURE` | GPU/process/storage failure or incomplete shard |

Unknown errors remain errors; they must not default to a pass or a generic
planner rejection.

## Ownership and cross-workstream handoff

| Workstream | Owns | Must not own |
| --- | --- | --- |
| Runtime | Canonical plan/trajectory export, schemas, validation, differential logic | Isaac scene truth or physical qualification |
| Simulation | USD assets, physics settings, sensors, runner, receipts | Semantic intent, AI confidence, hardware authority |
| AI/perception | Model inference from allowed images/data, abstention, scored predictions | Simulator ground truth or direct articulation control |
| Workcell | Measurements and their provenance | Editing simulation output to match expectations |
| Repository | Version locks, external-artifact manifest, CI, review, licensing records | Declaring modeled behavior physically proven |

Cross-workstream progress is logged in the
[shared AI/arm workplan](../ai/docs/SHARED_AI_ARM_WORKPLAN.md). Evidence is added
to the [AI/arm evidence ledger](../ai/docs/EVIDENCE_LEDGER.md) only after exact
inputs and limitations are reviewable.

## CI and evidence policy

Ordinary CI should validate:

- request and receipt schemas;
- canonical hashing and round trips;
- invalid/fail-closed fixtures;
- joint/frame mappings against compact manifests;
- fake-adapter lifecycle and cancellation;
- documentation and external-artifact links.

GPU integration runs should begin as manual, exact-revision jobs on the owned
runner. After the environment and receipts stabilize, add a scheduled or
manually dispatched workflow. Do not make an unavailable proprietary simulator
a required check for every pull request.

Commit compact requests, summaries, manifests, and receipts when appropriate.
Keep large USD files, renders, datasets, caches, and raw logs in governed
external storage with hashes, sizes, media types, retrieval instructions, and
license/redistribution notes.

## Risks and controls

| Risk | Control |
| --- | --- |
| Simulation-to-reality gap | Keep physical and simulated evidence classes separate; use measured inputs and sensitivity bounds |
| Incomplete kinematic URDF | Require enrichment provenance and block affected claims |
| Isaac API churn | Pin exact build/extensions; keep NVIDIA code behind one adapter; verify migrations explicitly |
| Experimental sensor behavior | Contract the observations Tactevra needs, test invalid/missing results, and pin API version |
| Nondeterministic physics/rendering | Fixed seeds/settings, repeat campaigns, categorical and numeric drift criteria |
| False confidence from detailed graphics | Acceptance is receipt- and provenance-based, never visual realism alone |
| Licensing/redistribution mistakes | Keep NVIDIA runtime external; record exact licenses for generated/imported assets before distribution |
| Multi-GPU assumptions | Establish single-GPU truth first; use dual GPUs only for independent validated shards |
| Keyboard model overfitting | Start with representative keys, vary properties, compare against measured mechanisms later |
| AI truth leakage | Separate render inputs from truth manifests and processes |

## First implementation increment

The first mergeable increment is intentionally small:

1. add the v1 request and receipt schemas plus Python dataclasses/validators;
2. add canonical hash and fail-closed fixture tests using a fake adapter;
3. select and lock one exact Isaac Sim runner after installation verification;
4. import the arm and emit a joint/link/unit mapping report;
5. run the fixed FK parity corpus;
6. replay one noncontact `H`-region hover without replanning;
7. retain the request, receipt, differential result, and explicit limitations;
8. review the result before beginning contact mechanics or dataset generation.

This increment is complete only when a clean environment can reproduce the
receipt and every unavailable input causes a named rejection.

## Plan completion criteria

This integration plan is complete when:

- WP0 through WP6 have merged implementation and exact evidence;
- the native articulation path replays admitted Tactevra trajectories without
  semantic shortcuts;
- FK, frames, assets, tracking, collision, representative contact, and camera
  campaign gates have reviewable receipts;
- deterministic and Isaac results are compared with categorized disagreement;
- the GPU runner is reproducible from its lock and large artifacts are governed;
- AI evaluation cannot consume simulator truth accidentally;
- documentation states exactly what simulation has and has not established;
- no simulator result can promote a physical hardware gate.

WP7 remains optional and does not block completion.

## Official NVIDIA references

The selected implementation must pin the documentation matching its exact
release. These current official entry points informed the plan:

- [Isaac Sim manipulator workflows](https://docs.isaacsim.omniverse.nvidia.com/latest/robot_setup_tutorials/tutorial_pickplace_example.html)
- [Isaac Sim development methods and standalone Python](https://docs.isaacsim.omniverse.nvidia.com/latest/introductory_tutorials/tutorial_intro_workflows.html)
- [URDF importer](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/ext_isaacsim_asset_importer_urdf.html)
- [Physics sensors](https://docs.isaacsim.omniverse.nvidia.com/latest/sensors/isaacsim_sensors_physics.html)
- [Replicator synthetic-data workflows](https://docs.isaacsim.omniverse.nvidia.com/latest/replicator_tutorials/index.html)
- [ROS 2 control](https://docs.isaacsim.omniverse.nvidia.com/latest/ros2_tutorials/tutorial_ros2_manipulation.html)
- [Isaac Sim license terms](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/)

External documentation is informative until the selected toolchain lock records
the exact tested version and applicable terms.
