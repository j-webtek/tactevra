# Isaac Sim integration boundary

- **Document status:** Active implementation reference
- **Audience:** Runtime and simulation contributors
- **Authority:** Software-test guidance only; this integration grants no
  hardware, motion, contact, or release authority.

This directory documents the optional NVIDIA Isaac Sim runner. Executable,
packaged contracts live in
`software/src/rocell/integrations/isaac_sim/`; versioned JSON schemas live in
`software/schemas/`.

The implementation began with WP0 contracts and now also retains bounded
runner, asset, kinematic, scene, schedule-replay, and collision-development
evidence. The portable contract foundation provides:

- canonical v1 request and receipt envelopes;
- exact-field, unit, frame, joint-order, timing, digest, and zero-authority
  validation;
- a hardware-free fake adapter for lifecycle and evidence tests;
- a fail-closed external toolchain lock; and
- compact valid and invalid fixtures.

The fake adapter itself does **not** import Isaac Sim, load a USD scene, use a
GPU, run physics, or produce clearance/contact evidence. A fake-adapter `PASS`
has evidence class `CONTRACT_TEST_ONLY` and expressly establishes only contract
behavior. Later sections distinguish that portable layer from the retained
external Isaac runs; none grants hardware authority.

The WP3 selected-profile handoff is wrapped by the exact route-bound entry
handoff in `rocell.application.route_bound_entry_isaac_replay_handoff_v1`.
Native intake requires its
`READY_ROUTE_BOUND_NATIVE_ISAAC_REPLAY_ZERO_AUTHORITY` result and the current
authoritative toolchain lock. It revalidates the outer collision and fresh-entry
lineage before independently parsing the nested replay handoff, all 329 route
configurations, 328 segments, attachment-profile separation, zero-authority
fields, and exact Isaac installation, extension, and settings identities.
Synthetic unit fixtures exercise this boundary but are not native replay
evidence. A real passing ICQ-8 receipt and accepted installed collision profile
remain prerequisites for the WP3 acceptance run.

The existing `joint_schedule_isaac_replay_probe.py` also exposes an
`--admission-only` mode for this handoff. It reads and validates every input,
then writes a sealed `NATIVE_ISAAC_ADMISSION_ONLY` receipt and exits before the
`isaacsim` import. The boundary additionally binds the governed robot USD to
its sealed import receipt, verifies the expected six-DOF articulation order,
and requires the profiled route's five arm joints in that exact order. This
receipt authorizes only a later native process start; it is not replay,
physics, clearance, tracking, settle, contact, or repeatability evidence.

```powershell
$env:PYTHONPATH = "software/src"
python software/integrations/isaac_sim/joint_schedule_isaac_replay_probe.py `
  --admission-only `
  --usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --import-receipt software/integrations/isaac_sim/evidence/roarm_m3_urdf_import_20260929.json `
  --route-bound-handoff C:\IsaacSim\requests\route-bound-entry-handoff.json `
  --toolchain-lock software/config/isaac_sim_toolchain_lock.json `
  --output C:\IsaacSim\evidence\profiled-native-admission.json `
  --status-output C:\IsaacSim\evidence\profiled-native-admission.status.json
```

The command is intentionally unusable until the real retained ICQ-8 handoff
exists. It must not be substituted with a synthetic fixture for operational
admission.

For a reader-oriented explanation of how Isaac Sim relates to Tactevra's
deterministic simulators and the proposed MuJoCo Warp lane, see the
[simulation overview](../../../docs/SIMULATION.md).

The ScheduleGen-inspired path from drive-controlled physics through automated
demonstration generation and bounded imitation learning is maintained in the
[learned motion generation plan](../../docs/ISAAC_SIM_LEARNED_MOTION_GENERATION_PLAN.md).

The LM0A executable baseline is
[`drive_controlled_hover_probe.py`](drive_controlled_hover_probe.py), driven by
[`../../config/isaac_lm0_dynamic_profile.json`](../../config/isaac_lm0_dynamic_profile.json).
It performs a gravity-off, physics-stepped PARK-to-`H`-hover diagnostic with
explicit provisional mass, inertia, and drive parameters. It never accesses
hardware and is not evidence for physical timing, torque, contact, or safety.

Independent LM0A receipts are checked and summarized by
[`drive_controlled_hover_campaign.py`](drive_controlled_hover_campaign.py).
The retained three-process campaign requires intact receipt digests, identical
asset/schedule/profile bindings, zero post-initialization teleports, zero
hardware authority, passing per-run tracking, and final-error spread no greater
than `1e-9 rad`. This closes only the gravity-off control-path repeatability
slice; it does not qualify the provisional dynamics or the physical robot.

After independently producing at least three native receipts, seal the
campaign with ordinary Python (this command does not import Isaac or access
hardware):

```powershell
python software/integrations/isaac_sim/drive_controlled_hover_campaign.py `
  C:\IsaacSim\evidence\lm0-repeat-1.json `
  C:\IsaacSim\evidence\lm0-repeat-2.json `
  C:\IsaacSim\evidence\lm0-repeat-3.json `
  --maximum-error-spread-rad 1e-9 `
  --output C:\IsaacSim\evidence\lm0-campaign.json `
  --status-output C:\IsaacSim\evidence\lm0-campaign.status.json
```

The same probe accepts the separately bound
[`../../config/isaac_lm0b_gravity_characterization_profile.json`](../../config/isaac_lm0b_gravity_characterization_profile.json)
to exercise the noncontact hover at standard gravity. Its retained result is a
control-path characterization only: the profile deliberately marks every
center of mass as a link-origin placeholder. A lower tracking error than LM0A
does not imply a better physical model. Geometry-derived mass properties and
measured physical traces are required before parameter fitting.

[`link_mass_property_prior_probe.py`](link_mass_property_prior_probe.py)
replaces the link-origin center-of-mass placeholders with a deterministic
geometry prior. It reads the seven exact meshes from the pinned upstream Git
commit, uses source volume for the five watertight meshes and labelled convex
hulls for open `link1` and `link5`, scales each inertia tensor to the existing
provisional link mass, and emits principal-axis properties. The retained
gravity-on replay passes, but the geometry omits internal servo, electronics,
and fastener mass distribution, so this remains a simulation prior rather than
physical identification.

```powershell
C:\IsaacSim\env_6_1_0\Scripts\python.exe `
  software\integrations\isaac_sim\link_mass_property_prior_probe.py `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_mesh_binding_20261004.json `
  --base-profile software\config\isaac_lm0b_gravity_characterization_profile.json `
  --profile-output C:\IsaacSim\evidence\isaac_lm0b_geometry_prior_profile.json `
  --receipt-output C:\IsaacSim\evidence\link_mass_property_prior.json `
  --status-output C:\IsaacSim\evidence\link_mass_property_prior.status.json
```

[`multi_pose_sysid_trajectory_probe.py`](multi_pose_sysid_trajectory_probe.py)
extends that gravity-on model through the governed `PARK`, `H`, `1`, and
`PERIOD` endpoints without a post-initialization state teleport. It records 960
physics samples of positions, velocities, commands, explicitly applied
actuation force, and projected joint force. The compact SysID CSV uses the
installed Isaac Sim 6.1 loader's supported
`time,q1..q6,dq1..dq6,cmd1..cmd6` layout; a native loader readback confirms six
joints, 960 samples, and a 7.991666666666666-second duration. The richer CSV
preserves channel semantics that the compact loader does not carry. A second
independent native process produced byte-identical rich CSV, compact CSV, and
receipt outputs.

The retained run passes all four final-pose checks at a worst error of
`2.2587313047051083e-05` rad. Its applied-actuation-force channel is zero
because the motion is produced by internal position drives; it must not be
misreported as drive output torque. Projected joint force is nonzero and is the
useful simulation load-side reference. Neither channel calibrates the
controller's raw T1051 load fields, and this sim-to-sim trajectory cannot prove
physical parameters or physical fit quality.

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
C:\IsaacSim\env_6_1_0\Scripts\python.exe `
  software\integrations\isaac_sim\multi_pose_sysid_trajectory_probe.py `
  --usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --bundle software\integrations\isaac_sim\evidence\actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --profile software\config\isaac_lm0b_geometry_prior_profile.json `
  --telemetry-output C:\IsaacSim\evidence\geometry_prior_multi_pose_telemetry.csv `
  --sysid-output C:\IsaacSim\evidence\geometry_prior_multi_pose_sysid.csv `
  --output C:\IsaacSim\evidence\geometry_prior_multi_pose_sysid_trajectory.json `
  --status-output C:\IsaacSim\evidence\geometry_prior_multi_pose_sysid_trajectory.status.json
```

The imported USD itself still contains invalid importer placeholders for mass
and zero-valued authored drives. Passing that raw stage to the SysID quick-start
made all 100 default parameters unidentifiable. Use
[`sysid_stage_prior_probe.py`](sysid_stage_prior_probe.py) to create a separate
derived stage with the seven geometry-prior mass properties and six nonzero
drive priors authored into USD. The probe refuses to overwrite the imported
source and hashes both inputs and the derived output.

A scratch NVIDIA preflight against the derived stage improved the default
100-parameter report to 8 identifiable, 4 weak, and 88 unidentifiable. This is
diagnostic progress, not permission to run the broad optimizer: joints 5 and 6
remain weakly excited, no validation chunk is configured, inertial fitting has
no measured link-side torque, and the default parameter set is unnecessarily
broad. The next run spec must select only the excited joint stiffness/damping
terms and reserve a validation segment.

```powershell
C:\IsaacSim\env_6_1_0\Scripts\python.exe `
  software\integrations\isaac_sim\sysid_stage_prior_probe.py `
  --input-usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --profile software\config\isaac_lm0b_geometry_prior_profile.json `
  --output-usd C:\IsaacSim\artifacts\issue190\lm0b-sysid-prior-001\roarm_m3_sysid_prior.usda `
  --receipt C:\IsaacSim\evidence\sysid_stage_prior.json `
  --status-output C:\IsaacSim\evidence\sysid_stage_prior.status.json
```

## Initial Windows runner candidate installed 2026-09-29

The designated host now has a dedicated `C:\IsaacSim\env_6_1_0` environment
containing CPython 3.12, `torch==2.11.0+cu130`, and
`isaacsim[all,extscache]==6.1.0.0`. Torch enumerates both installed NVIDIA
GeForce RTX 3090 GPUs. The compact
[`host probe`](evidence/windows_dual_rtx3090_candidate_20260929.json) binds 26
Isaac/Torch distributions through their installed `METADATA` and `RECORD`
hashes and records zero hardware writes and zero physical movements.

This is a blocked candidate, not a selected runner. Isaac Sim has not been
launched, no NVIDIA terms were accepted by automation, and the settings
profile remains unavailable. NVIDIA documents driver 595.97 as tested for
Isaac Sim 6.1.0 on Windows; the host currently reports 591.86. The RTX 3090 is
also outside NVIDIA's documented minimum GPU set for 6.1.0 even though each
card has 24 GiB VRAM and RT capability. Compatibility must therefore be
measured after a reviewed driver and license decision.

The initial candidate report is retained as historical prelaunch evidence. The
driver and launch blockers in that report were subsequently addressed as
described below. The exact package installation commands were:

```powershell
py -3.12 -m venv C:\IsaacSim\env_6_1_0
C:\IsaacSim\env_6_1_0\Scripts\python.exe -m pip install --upgrade pip
C:\IsaacSim\env_6_1_0\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu130
C:\IsaacSim\env_6_1_0\Scripts\python.exe -m pip install "isaacsim[all,extscache]==6.1.0.0" --extra-index-url https://pypi.nvidia.com
```

Reproduce the non-launching probe from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path 'software/src').Path
C:\IsaacSim\env_6_1_0\Scripts\python.exe -m rocell.integrations.isaac_sim.host_probe `
  --output software/integrations/isaac_sim/evidence/windows_dual_rtx3090_candidate_20260929.json
```

The probe imports neither Isaac Sim nor Torch. It cannot accept a license,
start a simulator, open robot transport, or generate wire commands.

## Driver-qualified compatibility launch

The project owner authorized NVIDIA's terms for internal use and installation
of the tested Windows driver. The signed NVIDIA 595.97 installer has SHA-256
`979ed00fea181c786f608967377d6d83ac82e6368275994a4182ec79d97b3122`.
The outer self-extractor failed once with Windows access denied; extracting the
same signed archive and running its signed `setup.exe -s -n Display.Driver`
succeeded. Both GPUs then reported driver 595.97 and Torch retained CUDA access.

[`first_launch_probe.py`](first_launch_probe.py) subsequently started Isaac Sim
headlessly and shut it down without creating a scene. The retained
[`launch receipt`](evidence/windows_dual_rtx3090_first_launch_20260929.json)
binds:

- Isaac Sim distribution 6.1.0.0 and Kit application 6.1.0;
- the exact 26-distribution installation digest;
- driver 595.97 and both 24 GiB RTX 3090 identities;
- 303 live enabled extensions and their canonical digest;
- the five-field headless launch profile and its canonical digest; and
- zero hardware writes, movements, wire commands, or physical authority.

Reproduce the compatibility launch only in the installed external environment:

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\first_launch_probe.py `
  --output C:\IsaacSim\evidence\first_launch_receipt_6_1_0.json `
  --status-output C:\IsaacSim\evidence\first_launch_receipt_6_1_0.status.json `
  --installation-sha256 ccb196b9c987865ee86918301f00705b1dd5a42449c3119f2119aeb2adf51258 `
  --installer-sha256 979ed00fea181c786f608967377d6d83ac82e6368275994a4182ec79d97b3122
```

The compatibility launch passes. The exact runner was subsequently selected
for internal integration in the reviewed
[`toolchain lock`](../../config/isaac_sim_toolchain_lock.json).
The RTX 3090 remains outside NVIDIA's documented 6.1.0 minimum GPU set, so the
selection is an empirical compatibility exception and does not claim official
NVIDIA support. The launch also reported PCIe device 0 at width x4 versus its x16
maximum, no CUDA peer access between the GPUs, a stale localhost Omniverse
proxy setting, and an OpenUSD asset-converter build warning. WP1 must resolve
or explicitly isolate the OpenUSD importer warning and prove import/FK parity
before relying on imported kinematics; that bounded parity evidence is now
retained. Dynamics, contact, rendering, and physical behavior remain
unqualified.

## Governed RoArm URDF import

[`urdf_import_probe.py`](urdf_import_probe.py) imports the pinned, meshless
RoArm-M3 kinematic URDF into a caller-supplied external directory. The compact
[`import receipt`](evidence/roarm_m3_urdf_import_20260929.json) binds the exact
source URDF, importer configuration, generated USD manifest, all nine source
links, six movable USD Physics joints, and the two source fixed joints that the
Isaac importer represents as nested transforms.

The generated USD is deliberately retained outside Git at
`C:\IsaacSim\artifacts\issue190\wp1-import-003`. Its manifest is committed,
but the stage itself is not. The receipt is kinematic import evidence only: it
contains no trajectory, wire command, hardware access, physical authority,
dynamics qualification, or FK parity claim.

Reproduce the bounded import on the designated runner from the repository root:

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\urdf_import_probe.py `
  --urdf software\models\roarm_m3\roarm_m3_kinematic_40dbd84.urdf `
  --output-dir C:\IsaacSim\artifacts\issue190\wp1-import-003 `
  --receipt C:\IsaacSim\evidence\urdf_import_003.json `
  --status-output C:\IsaacSim\evidence\urdf_import_003.status.json
```

The importer promotes `base_link` to the USD articulation root after Isaac's
fixed-joint collapse. This preserves all six source movable joints in the live
articulation DOF view. The original unnormalized import and its missing-base-DOF
diagnostic remain retained evidence.

[`fk_parity_probe.py`](fk_parity_probe.py) teleports only the live in-memory
articulation through the governed zero, home, and ready corpus and reads the
`link5` physics transform plus the imported fixed `hand_tcp` transform. The
retained [`FK receipt`](evidence/roarm_m3_fk_parity_20260929.json) exposes the
complete six-DOF order and passes all three cases at a worst translation error
below 0.00013 mm. This is kinematic parity only. The imported model has invalid
mass and inertia placeholders, and no dynamics, collision, contact, rendering,
hardware, or physical qualification follows from this result.

## Nominal RC03 rigid scene

[`rc03_scene_probe.py`](rc03_scene_probe.py) consumes the existing strict RC03
scene loader and composes an external metre-based USD stage containing the
governed board, keyboard and phone envelopes, three conservative station
proxies, six nominal fiducials, the nominal `H` target marker, and a reference
to the normalized robot USD at the frozen nominal board transform. The compact
[`scene receipt`](evidence/rc03_nominal_rigid_scene_20260929.json) binds every
source file, the external stage, six static collision prims, and the six
composed robot joints.

This is scene-composition evidence only. Collision queries and hover replay
remain explicitly inadmissible because robot-link and tool collision geometry,
valid inertial properties, camera-support solids, controlled fixture heights,
measured robot placement, and a selected Isaac toolchain lock are unavailable.
The probe does not accept or derive a trajectory.

Reproduce it on the designated runner from the repository root:

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\rc03_scene_probe.py `
  --workspace . `
  --rc03-root active-project\RoCell_v0_3 `
  --robot-usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --robot-import-receipt software\integrations\isaac_sim\evidence\roarm_m3_urdf_import_20260929.json `
  --output-dir C:\IsaacSim\artifacts\issue190\wp2-scene-002 `
  --receipt C:\IsaacSim\evidence\rc03_scene_002.json `
  --status-output C:\IsaacSim\evidence\rc03_scene_002.status.json
```

## Model-motion command overlay

[`model_motion_scene_overlay_probe.py`](model_motion_scene_overlay_probe.py)
strictly decodes an actual AI-produced `ModelMotionBatchV2`, binds it to the
retained RC03 scene and nominal target source, preserves requested order and
repeated targets, and authors proposal centers, inferred placed key regions,
and uncertainty disks into an external Isaac USD. The retained
[`overlay receipt`](evidence/model_motion_scene_overlay_20260929.json) evaluates
`H, H, 1, PERIOD`. All proposal centers share one synthetic rigid placement to
numerical precision, but the 14.400834977 mm localization disk exceeds every
7 mm key-edge margin. The rehearsal therefore stops at
`BLOCKED_UNCERTAINTY_CROSSES_INFERRED_SAFE_REGIONS` before any joint schedule.

The inferred placement is a visualization transform reconstructed from the
synthetic batch; it is not runtime calibration. The probe changes zero
articulation positions, takes zero physics steps, emits no controller or wire
commands, and grants no hardware or physical authority. Its next input must be
a source-bound joint schedule from the arm typing pipeline. That later replay
must compare the simulated TCP at each contact sample with the same ordered
batch targets rather than using separately invented points.

Reproduce the overlay on the designated runner from the repository root:

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\model_motion_scene_overlay_probe.py `
  --workspace . `
  --scene-usd C:\IsaacSim\artifacts\issue190\wp2-scene-002\rc03_nominal_rigid_scene.usda `
  --scene-receipt software\integrations\isaac_sim\evidence\rc03_nominal_rigid_scene_20260929.json `
  --batch software\ai\eval\precision_adapter_batch_v2_contract_fixture.json `
  --batch-metadata software\ai\eval\precision_adapter_batch_v2_contract_fixture_metadata.json `
  --output-dir C:\IsaacSim\artifacts\issue190\wp2-command-overlay-001 `
  --receipt C:\IsaacSim\evidence\model_motion_overlay_001.json `
  --status-output C:\IsaacSim\evidence\model_motion_overlay_001.status.json
```

## Official per-link mesh binding

[`upstream_link_mesh_binding_probe.py`](upstream_link_mesh_binding_probe.py)
reads immutable blobs from the pinned Waveshare `roarm_ws` commit. The retained
[`binding receipt`](evidence/roarm_m3_upstream_link_mesh_binding_20261004.json)
proves that seven named Xacro links use seven exact STL blobs, with identical
visual and collision references, zero local origin offsets, and the declared
`0.001` scale. It records 38,344 triangles across 19 connected bodies; `link1`
and `link5` are not watertight, and one left-gripper mesh is not referenced by
the Xacro.

This is source-provenance evidence, not collision qualification. It does not
prove mesh-to-robot-frame alignment, install collision shapes, select a
self-collision pair policy, run Isaac, or admit a clearance result. Raw mesh,
reduced geometry, and clearance replay remain explicitly inadmissible.

Reproduce the inspection from a local checkout containing the pinned commit:

```powershell
python software\integrations\isaac_sim\upstream_link_mesh_binding_probe.py `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --output C:\IsaacSim\evidence\upstream_link_mesh_binding_001.json `
  --status-output C:\IsaacSim\evidence\upstream_link_mesh_binding_001.status.json
```

## Conservative link-local box candidates

[`link_mesh_reduction_probe.py`](link_mesh_reduction_probe.py) derives one
deterministic, link-local identity-oriented box per processed connected mesh
component. `link5` has 114 processed fragments, so the generator applies its
declared 64-primitives-per-body limit and emits one whole-link envelope instead.
The retained
[`reduction receipt`](evidence/roarm_m3_link_mesh_reduction_20261004.json)
contains 14 candidate boxes across seven links and proves zero source-vertex
overflow after serialization.

These boxes are conservative candidates, not an installed collision profile.
The largest box/source volume ratio among watertight components is 21.141, two
source components are not watertight, and false-positive collision behavior and
self-collision pair policy remain unqualified. The receipt therefore denies
candidate installation, collision admission, and clearance replay.

Reproduce the candidate reduction without installing a profile:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\link_mesh_reduction_probe.py `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_mesh_binding_20261004.json `
  --output C:\IsaacSim\evidence\link_mesh_reduction_003.json `
  --status-output C:\IsaacSim\evidence\link_mesh_reduction_003.status.json
```

## Three-pose link-collision differential

[`collision_differential_probe.py`](collision_differential_probe.py) compares
the 14 conservative box candidates with the exact source-bound meshes for all
21 unordered link pairs at the governed zero, home, and ready poses. The
retained
[`differential receipt`](evidence/roarm_m3_collision_differential_20261004.json)
records 63 pair-pose cases: 48 free-space agreements, three collision
agreements, 12 candidate false positives, and zero observed candidate false
negatives. Every observed false positive is between kinematically adjacent
links, but adjacent pairs are deliberately measured rather than filtered.

This small corpus does not establish workspace coverage or authorize an
exclusion policy. The probe pins the exact `python-fcl 0.7.0.11` CPython 3.12
wheel by SHA-256 and remains offline, zero-write, and non-installing. Candidate
installation, collision admission, and clearance replay remain denied until
the self-collision pair policy is reviewed.

Reproduce the comparison from an isolated Python 3.12 environment containing
the exact pinned wheel and `trimesh 4.11.1`:

```powershell
python software\integrations\isaac_sim\collision_differential_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_mesh_binding_20261004.json `
  --reduction-receipt software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20261004.json `
  --fcl-wheel C:\IsaacSim\sources\python-fcl-0.7.0.11\python_fcl-0.7.0.11-cp312-cp312-win_amd64.whl `
  --output C:\IsaacSim\evidence\collision_differential_004.json `
  --status-output C:\IsaacSim\evidence\collision_differential_004.status.json
```

## Governed joint-space collision differential

[`collision_joint_space_probe.py`](collision_joint_space_probe.py) expands the
same source-mesh-versus-box comparison to a deterministic 49-pose corpus. The
corpus contains the three governed anchors, lower/upper/midpoint limit anchors,
12 single-joint limit poses, and 32 Halton interior samples derived from the
governed URDF limits. The retained
[`joint-space receipt`](evidence/roarm_m3_collision_joint_space_20261004.json)
records 1,029 pair-pose cases: 780 free-space agreements, 57 collision
agreements, 192 candidate false positives, and zero observed candidate false
negatives.

The result isolates 191 false positives to adjacent links and one to the
nonadjacent `link2/gripper_link` pair. That makes the larger corpus useful for
targeted refinement, but it does not justify installing the candidates or
silently excluding any pair. Finite sampling is not continuous workspace
coverage, the source includes non-watertight meshes, and tool, camera, support,
and environment geometry are still absent. Collision admission and clearance
replay therefore remain denied.

Reproduce the summary from the same isolated Python 3.12 environment used by
the three-pose comparison:

```powershell
python software\integrations\isaac_sim\collision_joint_space_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_mesh_binding_20261004.json `
  --reduction-receipt software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20261004.json `
  --fcl-wheel C:\IsaacSim\sources\python-fcl-0.7.0.11\python_fcl-0.7.0.11-cp312-cp312-win_amd64.whl `
  --output C:\IsaacSim\evidence\collision_joint_space_detailed_005.json `
  --summary-output C:\IsaacSim\evidence\collision_joint_space_summary_005.json `
  --status-output C:\IsaacSim\evidence\collision_joint_space_005.status.json
```

## Targeted `link2` refinement and pair-policy stress

The original 49-pose differential contained one nonadjacent false positive for
`link2` against `gripper_link`. An oriented-box attempt is retained as failed
evidence: its exact replay remains at 192 false positives, including that same
nonadjacent witness. The successor
[`triangle_partition_refinement_probe.py`](triangle_partition_refinement_probe.py)
partitions the implicated `link2` component into 16 complete-triangle groups.
Its [candidate](evidence/roarm_m3_triangle_partition_link2_20261005.json) has
zero serialized vertex overflow and remains below the 64-primitive body limit.

The corresponding
[49-pose replay](evidence/roarm_m3_collision_joint_space_triangle_partition_20261005.json)
preserves 57 collision agreements, introduces zero observed false negatives,
reduces false positives from 192 to 165, and removes the sole nonadjacent false
positive. All remaining false positives occur on four directly connected link
pairs.

[`self_collision_policy_review_probe.py`](self_collision_policy_review_probe.py)
shows that the upstream SRDF's six `Adjacent` entries exactly match the six
governed direct-joint pairs. The separate
[`srdf_never_pair_review_probe.py`](srdf_never_pair_review_probe.py) records
free-space agreement for all six `Never` pairs across the same finite corpus.
Neither review installs or authorizes an exclusion.

A held-out replay covers 256 Halton poses at indices 1001 through 1256. Its
[assessment](evidence/roarm_m3_collision_policy_stress_assessment_20261005.json)
finds zero observed false negatives and no contradiction of the six `Never`
pairs, while preserving 13 false positives across six retained pairs. The
candidate remains counterfactual: effective exclusions stay empty, every pair
defaults to `CHECK_COLLISION`, and collision and clearance admission remain
false. Finite samples do not establish continuous workspace safety, and the
installed tool, camera support, and measured environment geometry remain open.

Reproduce the candidate and selected replay with the pinned CPU geometry stack:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\triangle_partition_refinement_probe.py `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_mesh_binding_20261004.json `
  --base-reduction software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20261004.json `
  --band-count 16 --strategy recursive-longest-centroid-axis `
  --output C:\IsaacSim\evidence\triangle_partition_link2.json `
  --status-output C:\IsaacSim\evidence\triangle_partition_link2.status.json

C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\collision_joint_space_probe.py `
  --workspace . --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_mesh_binding_20261004.json `
  --reduction-receipt C:\IsaacSim\evidence\triangle_partition_link2.json `
  --expected-reduction-sha256 cf887206e9afdadb46a20263db56406eabfe90a78c3f9d1e5ad0e8dc3fbc6469 `
  --fcl-wheel C:\IsaacSim\sources\python-fcl-0.7.0.11\python_fcl-0.7.0.11-cp312-cp312-win_amd64.whl `
  --output C:\IsaacSim\evidence\triangle_replay.detailed.json `
  --summary-output C:\IsaacSim\evidence\triangle_replay.summary.json `
  --status-output C:\IsaacSim\evidence\triangle_replay.status.json
```

## Verify WP0

From `software/`:

```powershell
python -m pytest tests/unit/test_isaac_sim_contracts.py -q
```

From the repository root:

```powershell
python scripts/ci/check_docs.py
```

## Selected external runner

The committed
[`isaac_sim_toolchain_lock.json`](../../config/isaac_sim_toolchain_lock.json)
selects the exact Isaac Sim 6.1.0.0 installation from the retained compatibility
launch. The retained launch receipt and evidence ledger bind the installation,
extensions, settings, installer, internal-use authorization,
nonredistribution disposition, and the RTX 3090 compatibility exception.
NVIDIA runtime files and generated NVIDIA assets stay external to Git.

This reviewed record supersedes the earlier `UNSELECTED` placeholder. Historical
receipts that name that blocker remain immutable and do not describe the current
lock state.

For any replacement runner:

1. install or pull one exact Isaac Sim release using an NVIDIA-supported path;
2. retain the exact installer/container identity and calculate its SHA-256;
3. export the enabled extension set and settings profile as canonical files;
4. hash both files;
5. record the runner platform and deterministic launch method;
6. review the exact selected version's license terms for the intended internal
   integration; and
7. change `selection_status` to `SELECTED` only in the same reviewed change
   that supplies all required identities.

`IsaacSimToolchainLock.load(...)` rejects unselected or partial records,
unreviewed licensing, invalid digests, added fields, or any attempt to add
hardware authority.

## Next implementation boundary

The real adapter may begin only after the exact lock is selected. Its first
operation is asset import and kinematic parity (WP1), not trajectory execution:

1. start the locked application in standalone/headless mode;
2. confirm the live version and enabled extensions against the lock;
3. import the governed RoArm-M3 source;
4. emit the complete joint/link/axis/unit mapping report;
5. run the fixed FK parity corpus; and
6. stop without creating controller commands or hardware access.

See the full [integration plan](../../docs/ISAAC_SIM_INTEGRATION_PLAN.md) for
work packages, acceptance gates, ownership, evidence, and limitations.

## Retained first noncontact H hover

The retained actual-emitter schedule and Isaac receipt are intentionally kept
as evidence rather than regenerated from unavailable external artifacts:

- [`actual_emitter_joint_schedule_bundle_9e5c878_20260929.json`](evidence/actual_emitter_joint_schedule_bundle_9e5c878_20260929.json)
  binds 133 ordered arm samples to the actual shared-emitter payload from arm
  commit `9e5c878852da6a6e8509598bce9ce43f218efc70`;
- [`actual_emitter_joint_schedule_isaac_replay_9e5c878_20260929.json`](evidence/actual_emitter_joint_schedule_isaac_replay_9e5c878_20260929.json)
  binds that exact bundle to the governed robot USD and records a passing
  zero-physics-step kinematic replay; and
- [`first_noncontact_h_hover_proof_20261004.json`](evidence/first_noncontact_h_hover_proof_20261004.json)
  derives the contiguous samples `0..34`, ending at the first `H` hover at
  board `[216.55, 154.0, 26.0]` mm, and proves that no contact sample occurs in
  that prefix.

Reproduce the derived proof with ordinary Python; Isaac is not started:

```powershell
python software/integrations/isaac_sim/first_noncontact_hover_proof.py `
  --bundle software/integrations/isaac_sim/evidence/actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --replay software/integrations/isaac_sim/evidence/actual_emitter_joint_schedule_isaac_replay_9e5c878_20260929.json `
  --output software/integrations/isaac_sim/evidence/first_noncontact_h_hover_proof_20261004.json
```

`PASS_KINEMATIC_HOVER_WITH_BLOCKERS` means only that the retained Isaac run
included the hash-bound noncontact prefix and that the full-route maximums
conservatively bound every prefix sample. The schedule used synthetic
observations, the joints were teleported without dynamics, and the retained
14.400834977 mm localization uncertainty still exceeds the 7 mm safe-region
margin. This evidence grants no camera, collision, controller, hardware, or
physical authority.

## Bounded LM0B SysID rehearsal

The retained multi-pose trajectory now feeds a validation-aware, deliberately
bounded NVIDIA SysID rehearsal. The generated run specification selects only
joint stiffness and damping for DOF indices `0..3` (eight terms total), trains
on the `H` and `1` segments, and holds out `PERIOD` for validation. The
stationary `PARK` segment and weakly excited DOF indices `4..5` are excluded.
Raw torque has zero residual weight because the dataset has no calibrated
link-side torque channel.

[`bounded_sysid_run_spec_20261101.json`](evidence/bounded_sysid_run_spec_20261101.json)
is validated and round-tripped by Isaac Sim's installed schema API. The compact
[`bounded_sysid_solve_rehearsal_20261101.json`](evidence/bounded_sysid_solve_rehearsal_20261101.json)
records the first three-iteration solve: all eight selected terms were reported
identifiable, one candidate was accepted, one validation chunk was evaluated,
and neither the stage nor its parameters were written. The retained status is
`PASS_BOUNDED_SYSID_REHEARSAL_WITH_WARNINGS`; it is not a physical parameter
identification claim because the telemetry is simulated, stiffness/damping are
correlated, wrist excitation is weak, and calibrated link-side torque is absent.

Regenerate the run spec and both receipts with Isaac Sim Python after producing
the verbose NVIDIA solve report externally:

```powershell
$env:OMNI_KIT_ACCEPT_EULA='YES'
& 'C:\IsaacSim\env_6_1_0\Scripts\python.exe' `
  software\integrations\isaac_sim\bounded_sysid_run_spec.py `
  --stage C:\IsaacSim\artifacts\issue190\lm0b-sysid-prior-001\roarm_m3_sysid_prior.usda `
  --telemetry software\integrations\isaac_sim\evidence\geometry_prior_multi_pose_sysid_20261101.csv `
  --output software\integrations\isaac_sim\evidence\bounded_sysid_run_spec_20261101.json `
  --receipt software\integrations\isaac_sim\evidence\bounded_sysid_run_spec_receipt_20261101.json `
  --solve-result tmp\bounded_sysid_solve_result.json `
  --solve-receipt software\integrations\isaac_sim\evidence\bounded_sysid_solve_rehearsal_20261101.json `
  --status-output tmp\bounded_sysid_run_spec_status.json
```

## Independent six-joint excitation

The bounded rehearsal exposed weak excitation on DOF indices `4..5`, so the
same drive-controlled probe now supports `--trajectory independent-sine`.
This mode holds the arm around the governed noncontact `H` pose and excites one
joint at a time, including a gripper-centered waveform that remains above its
zero lower limit. Each segment ends with a fixed settling interval.

The retained native run records 2,160 samples across six segments. Isaac's
telemetry-quality API reports no weakly excited joints, no nonfinite channels,
and more than `0.38 rad` observed range on every joint. The arm settles below
the existing `0.001 rad` threshold after every segment. The same report detects
an approximately `83 ms` common command/response lag and a large residual lag
on DOF index `4`; these are inputs to the next alignment/actuator-model step,
not values silently folded into damping. The run remains simulation-only and
does not promote any fitted parameter.

Retained artifacts:

- [`independent_joint_excitation_20261101.json`](evidence/independent_joint_excitation_20261101.json)
- [`independent_joint_excitation_sysid_20261101.csv`](evidence/independent_joint_excitation_sysid_20261101.csv)
- [`independent_joint_excitation_telemetry_20261101.csv`](evidence/independent_joint_excitation_telemetry_20261101.csv)

The fixed-frequency campaign's large DOF-4 residual was subsequently tested
with a smooth, independently windowed chirp on every joint. In the retained
2,880-sample chirp run, all six command/response correlations exceed `0.999`.
The inferred common lag is `0.0866067950984508 s`, while the maximum residual
spread falls from about 100 samples to `0.24795217120968438` samples. This
demonstrates that the earlier one-cycle wrist offset was a periodic correlation
alias rather than evidence of a one-second wrist actuator delay.

The expanded bounded fit now loads
[`independent_joint_chirp_sysid_20261101.csv`](evidence/independent_joint_chirp_sysid_20261101.csv)
with `telemetry.command_alignment_seconds = 0.0866067950984508`. It selects
stiffness and damping for all six joints (12 terms), trains on the first five
independent chirps, and holds out the sixth. All 12 terms pass the installed
identifiability check and no joint is weakly excited. The accepted candidate's
training normalized cost is `0.028078358620405197`; its held-out normalized
cost is `0.0036708096663157145`, with `0.031947098672389984 rad` position RMSE.
No parameter or USD was written. The assessment remains `warn` because chirp
is still the only excitation family and the evidence is simulation-generated,
so this candidate is retained for comparison rather than promoted.

Retained expanded-fit artifacts:

- [`aligned_chirp_sysid_run_spec_20261101.json`](evidence/aligned_chirp_sysid_run_spec_20261101.json)
- [`aligned_chirp_sysid_run_spec_receipt_20261101.json`](evidence/aligned_chirp_sysid_run_spec_receipt_20261101.json)
- [`aligned_chirp_sysid_solve_rehearsal_20261101.json`](evidence/aligned_chirp_sysid_solve_rehearsal_20261101.json)

Actuator-delay identification, if later enabled, must operate only on the
small per-joint residual after the common alignment. The retained chirp receipt
is [`independent_joint_chirp_20261101.json`](evidence/independent_joint_chirp_20261101.json).

The next validation campaign deliberately changes excitation family. The
deterministic composer binds and concatenates the 2,880-sample chirp trace for
training with the 2,160-sample independent-sine trace for validation. The
result has continuous 120 Hz timestamps and exact hashes for both sources.
The official run spec trains on all six chirp chunks and validates on all six
sine chunks. Both bounded optimizer updates were rejected, so the selected
result is the unchanged 12-value baseline rather than a claimed fit. That
baseline records `0.024019965901970863` training normalized cost and
`0.028266899857992005` validation normalized cost, a ratio of
`1.176808492291518`; sine validation position RMSE is
`0.14005315893640122 rad`. Excitation coverage, telemetry quality, and all 12
identifiability checks pass. The result is useful evidence that the baseline
generalizes across these simulated waveforms, but it does not justify parameter
promotion or a physical-model claim.

Retained cross-excitation artifacts:

- [`cross_excitation_sysid_20261101.csv`](evidence/cross_excitation_sysid_20261101.csv)
- [`cross_excitation_sysid_20261101.json`](evidence/cross_excitation_sysid_20261101.json)
- [`cross_excitation_sysid_run_spec_20261101.json`](evidence/cross_excitation_sysid_run_spec_20261101.json)
- [`cross_excitation_sysid_run_spec_receipt_20261101.json`](evidence/cross_excitation_sysid_run_spec_receipt_20261101.json)
- [`cross_excitation_sysid_validation_20261101.json`](evidence/cross_excitation_sysid_validation_20261101.json)

## Provisional representative-key mechanics contract

[`representative_key_mechanics.py`](representative_key_mechanics.py) starts LM1
with a deterministic contract for `H`, `1`, `SPACE`, `ENTER`, and `PERIOD`.
It derives board-frame key geometry from the governed nominal target profile
rather than duplicating measurements. All keyboard regions remain explicitly
`SIMULATION_ONLY_NOMINAL_UNMEASURED`.

The evaluator resolves the contacted key from tip geometry and compression; it
does not accept a requested key name as evidence of activation. A key activates
only on a rising crossing of the provisional activation depth and re-arms only
after reaching the release depth. Center safety, neighboring-key contact,
travel, spring/damping force estimates, double activation, and complete release
are evaluated separately. The deterministic campaign accepts one centered
press on each representative key and distinctly rejects shallow, off-center,
excessive-travel, double, neighboring-key, and incomplete-release cases.

All mechanics values are bounded synthetic priors, not Perixx specifications or
measurements. The contract and native replay grant no hardware, motion,
controller, or physical-keyboard authority.

ARM-187 starts the robot-TCP binding without hiding a trajectory mismatch. The
retained actual-emitter bundle places both `H` CONTACT endpoints at board
`z=21.0 mm`, exactly the representative key's rest surface, and therefore
schedules `0.0 mm` compression. The ARM-186 native replay accepted a `2.7 mm`
press. The zero-authority binding contract consequently derives the next
governed IK input as `[216.55, 154.0, 18.3] mm`, blocks the retained
surface-only schedule, and requires schedule regeneration, IK qualification,
and native replay. It does not invent replacement joint angles.

Run that boundary check with:

```powershell
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-robot-tcp-binding-001'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --robot-tcp-bundle software\integrations\isaac_sim\evidence\actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --output "$artifactDir\receipt.json" `
  --status-output "$artifactDir\status.json"
```

Exit code `2` with `BLOCKED_CONTACT_ENDPOINT_REQUIRES_OVERTRAVEL` is expected
for the retained bundle. It is a useful fail-closed planning result, not an
Isaac or infrastructure failure.

ARM-188 converts that governed target into a fresh Cartesian schedule request.
The request preserves all 133 source samples, their timestamps, semantic
phases, action indices, and target order. Only the two `H` CONTACT endpoints
(sequences `35` and `38`) change to `[216.55, 154.0, 18.3] mm`. Source joint
positions are intentionally omitted because they solve the old `21.0 mm`
surface endpoint. The external request at
`C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001` has SHA-256
`0237336223feca90f830c4162cb6cac1606f0438636802e8aa082f65c08601f7` and
status `READY_FOR_IK_QUALIFICATION`. It is not an IK, collision, or contact
pass.

Reproduce it with:

```powershell
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --robot-tcp-bundle software\integrations\isaac_sim\evidence\actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --regenerate-cartesian-schedule `
  --output "$artifactDir\request.json" `
  --status-output "$artifactDir\status.json"
```

Run its focused tests with:

```powershell
python -m pytest software/tests/unit/test_ghost_keyboard.py -q
```

### Native H-key contact replay

ARM-186 implements the first native Isaac contact slice with the same governed
`H` region and acceptance contract. The headless scene contains a single
prismatic key with bounded mass, travel, stiffness, and damping priors plus a
kinematic spherical virtual tip. The tip follows a smooth 600-sample
settle/press/hold/retract path at 120 Hz. After initialization, it advances only
through PhysX kinematic targets; the key moves only through contact, its joint,
and physics stepping.

The retained passing artifact is external because the repository source archive
is at its tracked-file ceiling:

- path: `C:\IsaacSim\artifacts\issue190\lm1-native-h-key-005\native_h_key_replay.json`
- receipt SHA-256: `9583a62f8c89220f7211acff3d449c9def6f21ac87146f309ad843c9cbc88768`
- result: one `H` activation, `2.69999820739031 mm` maximum compression,
  `1.48828043602407 N` maximum estimated force, and complete release
- contact observation: 259 of 600 trace samples
- authority: zero hardware access, writes, physical movement, and motion authority

The diagnostic lineage is intentionally retained beside it. Run `002` exposed
gravity sag to the lower travel stop, run `003` stabilized the preloaded key
mechanism, and run `004` proved that pose teleportation did not transfer contact
force. Run `005` replaced post-initialization teleports with solver-consumed
kinematic targets and passed without weakening the shared acceptance criteria.

Reproduce the passing probe with:

```powershell
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-native-h-key-005'
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
& 'C:\IsaacSim\env_6_1_0\Scripts\python.exe' `
  software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --native-h-probe `
  --output "$artifactDir\native_h_key_replay.json" `
  --status-output "$artifactDir\status.json"
```

This is an isolated virtual tip and representative key, not yet the full robot
contact path. Gravity is disabled for the one-dimensional key mechanism to
represent a preloaded keyboard return pending measured preload data. The next
LM1 boundary is to replace the virtual tip with the drive-controlled robot TCP
while retaining this exact mechanism-state evaluator and zero-authority receipt.
