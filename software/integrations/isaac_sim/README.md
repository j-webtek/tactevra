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

ARM-189 passes that exact request through the canonical numerical arm IK and
public trajectory-acceptance gates using the request's retained virtual-board
lineage and `120 mm` keyboard tool. All 133 samples pass. The two modified
`H` contacts (sequences `35` and `38`) each solve with `0.000119 mm` position
error, `0.153653` minimum normalized joint margin, `0.037258 rad` maximum
adjacent-joint delta, and full local solver-weighted Jacobian column rank. The
whole route's maximum position error is `0.076911 mm` and maximum adjacent
joint delta is `0.092435 rad`. The external receipt at
`C:\IsaacSim\artifacts\issue190\lm1-h-ik-screen-001` has SHA-256
`278ef3ff6d5ca94150e4e2423e68ed9dd736300713a471621bf6b4badcd678f2` and
status `READY_FOR_COLLISION_QUALIFICATION`.

This proves virtual reachability and discrete joint continuity for the deeper
contact schedule; it does not prove collision clearance, continuous-segment
safety, native robot/key contact, or physical execution. Reproduce it with:

```powershell
$env:PYTHONPATH = 'software/src'
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-h-ik-screen-001'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --cartesian-request C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001\request.json `
  --ik-source-bundle software\integrations\isaac_sim\evidence\actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --workspace . `
  --output "$artifactDir\receipt.json" `
  --status-output "$artifactDir\status.json"
```

If the ARM-188 input request is not already present, reproduce it with:

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

ARM-190 begins collision qualification without misclassifying the retained
exploratory geometry as an installed profile. It binds the exact ARM-189
receipt, the selected Isaac 6.1 toolchain lock, and the external simulation
collision candidate into one zero-authority replay request. The 133 accepted IK
endpoints expand to 149 deterministic configurations with a maximum per-joint
step of `0.05 rad`. The external request is retained at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-request-001\request.json` with
SHA-256 `4288f11667ac1713536ca808e1608150f2241ca7dfdaea41b75c307d14344dbd`.

The request status is `READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC`, not a
clearance pass. The candidate remains uninstalled and explicitly retains its
missing clamp, moving-cable, contact-tool range, and arm-camera-frame blockers.
Bounded sampling is also not a continuous swept-volume proof. Any native
diagnostic must report pair identities and geometry provenance, and cannot
authorize contact replay or promote an installed/physical gate.

Reproduce the request with:

```powershell
$env:PYTHONPATH = 'software/src'
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-h-collision-request-001'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --ik-receipt C:\IsaacSim\artifacts\issue190\lm1-h-ik-screen-001\receipt.json `
  --collision-candidate C:\IsaacSim\evidence\issue190\simulation_program\collision_candidate_v1.json `
  --toolchain-lock software\config\isaac_sim_toolchain_lock.json `
  --output "$artifactDir\request.json" `
  --status-output "$artifactDir\status.json"
```

ARM-191 consumes that request in the selected Isaac 6.1 runtime. Before Isaac
starts, a deterministic admission step revalidates the request, accepted IK
receipt, exploratory candidate, virtual placement profile, robot import
receipt, robot USD, articulation order, and all zero-authority fields. The
native stage then attaches the candidate boxes to their robot-link frames,
authors the static workcell boxes in board coordinates, and performs discrete
PhysX overlap queries at all 149 bounded configurations.

The retained external receipt is
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-diagnostic-002\receipt.json`.
Its canonical receipt SHA-256 is
`68ba26f6b99c7a5b4a2167f1227324eef8fb7d11422b0521f07d6c3954aee59c`.
All 149 configurations were queried; all contained at least one overlap, and 18
unique body pairs were retained. Five adjacent robot pairs persist in every
sample, as expected before a reviewed self-collision exclusion policy. The
remaining workcell overlaps vary by configuration and identify where the
conservative candidate/profile must be corrected. This is not a clearance
pass: the candidate remains uninstalled, overlap queries do not measure
clearance distance, and discrete samples do not prove continuous motion.

Reproduce the native diagnostic with:

```powershell
$env:PYTHONPATH = 'C:\icq7\software\src'
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-h-collision-diagnostic-002'
& 'C:\IsaacSim\env_6_1_0\Scripts\python.exe' `
  software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --workspace C:\icq7 `
  --run-collision-diagnostic `
  --collision-request C:\IsaacSim\artifacts\issue190\lm1-h-collision-request-001\request.json `
  --ik-receipt C:\IsaacSim\artifacts\issue190\lm1-h-ik-screen-001\receipt.json `
  --collision-candidate C:\IsaacSim\evidence\issue190\simulation_program\collision_candidate_v1.json `
  --virtual-profile software\config\virtual_commissioning_profile.json `
  --robot-usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --import-receipt C:\IsaacSim\evidence\urdf_import_003.json `
  --output "$artifactDir\receipt.json" `
  --status-output "$artifactDir\status.json"
```

The next collision step is evidence-driven: review and codify only the five
kinematically adjacent self-collision exclusions, then separate true robot-to-
workcell geometry from overlapping station/safe-region envelopes. Missing
clamp, cable, ranged tool, and arm-camera bodies remain blockers throughout.

ARM-192 turns those observations into an explicit, unapplied review proposal.
The external proposal at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-proposal-001\proposal.json`
has canonical SHA-256
`c9665938e0ab5d138079203fc5665333ec137a796ad7c2369070cc8c22793e61`.
It classifies all 18 observed pairs: five directly connected robot pairs are
proposed kinematic-neighbor exclusions, seven robot-to-board/device pairs stay
physical-solid collision observations, and six robot-to-station pairs stay
planning-envelope route blockers. `policy_applied` and
`installed_profile_eligible` remain false. The proposal cannot suppress an
observation until reviewed and hash-bound into a later diagnostic request.

Reproduce the proposal with:

```powershell
$env:PYTHONPATH = 'software/src'
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-proposal-001'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --propose-collision-pair-policy `
  --collision-diagnostic-receipt C:\IsaacSim\artifacts\issue190\lm1-h-collision-diagnostic-002\receipt.json `
  --collision-candidate C:\IsaacSim\evidence\issue190\simulation_program\collision_candidate_v1.json `
  --output "$artifactDir\proposal.json" `
  --status-output "$artifactDir\status.json"
```

Run its focused tests with:

```powershell
python -m pytest software/tests/unit/test_ghost_keyboard.py -q
```

ARM-193 accepts only the five reviewed directly connected robot-body pairs for
zero-authority diagnostic reporting. The accepted policy is retained at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-001\policy.json`
with canonical SHA-256
`ede8b946a85e754eec1698365bd16bec3b332d5d6cb8c9ef4634a9b61abeca87`.
The policy excludes no physical solid or station envelope, is ineligible for an
installed profile, and grants no contact or physical authority. Its hash-bound
v2 request is retained at
`C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-request-001\request.json`
with canonical SHA-256
`0eff9c8170d9ddf78af3bd96880acc43c8d96a4f875b35199aa3950ccb13e83b`.

The selected Isaac 6.1 rerun preserves all 18 raw overlap pairs across the 149
samples and applies the accepted policy only to blocker classification. The v2
receipt at
`C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-diagnostic-001\receipt.json`
has canonical SHA-256
`8e511e3203984fea32b9726d5cd37c465369b0ecc8d632f60fd71b0b1e327b4d`
and file SHA-256
`a0bda5a2732babead28a72f9c64c35f463ab95c2e06f40c697f52cebb87b377f`.
It reports five accepted adjacent-link reporting exclusions, seven
physical-solid blockers, six planning-envelope route blockers, and zero
unreviewed pairs. Status `DIAGNOSTIC_BLOCKERS_OBSERVED` is intentionally not a
clearance pass.

Reproduce acceptance, binding, and the policy-bound diagnostic with:

```powershell
$env:PYTHONPATH = 'software/src'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --accept-collision-pair-policy `
  --collision-pair-policy-proposal C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-proposal-001\proposal.json `
  --output C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-001\policy.json `
  --status-output C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-001\status.json
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --bind-collision-pair-policy `
  --collision-request C:\IsaacSim\artifacts\issue190\lm1-h-collision-request-001\request.json `
  --accepted-collision-pair-policy C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-001\policy.json `
  --output C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-request-001\request.json `
  --status-output C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-request-001\status.json
$env:PYTHONPATH = 'C:\icq7\software\src'
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
& 'C:\IsaacSim\env_6_1_0\Scripts\python.exe' `
  software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --run-collision-diagnostic `
  --collision-request C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-request-001\request.json `
  --accepted-collision-pair-policy C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-001\policy.json `
  --ik-receipt C:\IsaacSim\artifacts\issue190\lm1-h-ik-screen-001\receipt.json `
  --collision-candidate C:\IsaacSim\evidence\issue190\simulation_program\collision_candidate_v1.json `
  --virtual-profile software\config\virtual_commissioning_profile.json `
  --robot-usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --import-receipt C:\IsaacSim\evidence\urdf_import_003.json `
  --output C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-diagnostic-001\receipt.json `
  --status-output C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-diagnostic-001\status.json
```

ARM-194 localizes every remaining blocker back to the exact bounded replay
sample and its source Cartesian phase, action, target, and expected TCP pose.
The unapplied report at
`C:\IsaacSim\artifacts\issue190\lm1-h-collision-blocker-localization-001\proposal.json`
has canonical SHA-256
`8a3c8bb8df99c22383efb618d43f9d0e32b9f8aec443ce9525ef5393f2a0198b`.
It covers all 149 bounded samples and all 13 blockers: seven physical-solid
pairs involving the gripper and links 2 through 5, and six station-envelope
pairs involving the gripper, link 4, link 5, and the left/right keyboard
regions. No blocker is unreviewed. Most observations occur during `TRANSIT`;
station-envelope blockers are concentrated around the `H` and `1` portions,
while board-solid blockers continue into the later `1` and `PERIOD` portions.

This is a diagnosis, not a clearance result. It changes no collision geometry,
route, pair policy, or authority. The next correction must keep the two classes
separate: refine the conservative robot-link geometry for physical-solid
overlaps, and move station envelopes out of PhysX solid semantics while adding
an explicit route predicate for them. Both changes then require a fresh native
diagnostic with the same lineage checks.

Reproduce the localization report without starting Isaac or touching hardware:

```powershell
$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-h-collision-blocker-localization-001'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --localize-collision-blockers `
  --collision-diagnostic-receipt C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-diagnostic-001\receipt.json `
  --collision-request C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-request-001\request.json `
  --cartesian-request C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001\request.json `
  --output "$artifactDir\proposal.json" `
  --status-output "$artifactDir\status.json"
```

ARM-195 adds primitive-level attribution without changing the accepted pair
policy, trajectory, collision geometry, or body-level result. The native Isaac
6.1 v3 receipt at
`C:\IsaacSim\artifacts\issue190\lm1-h-primitive-attributed-collision-diagnostic-001\receipt.json`
has canonical SHA-256
`7f3941b7e6538d57bdb8cdfd2fa74da05973eb8649901a746f0ca0f2f44a3741`
and file SHA-256
`b637848377a9b234eef42052104479f023094f023c5ccd669dfda32c146b68ce`.
It retains the same 149 samples, 18 raw body pairs, five accepted adjacent-link
reporting exclusions, seven physical-solid blockers, six planning-envelope
route blockers, and zero unreviewed pairs. It additionally identifies 27 raw
primitive pairs.

The corresponding unapplied localization report at
`C:\IsaacSim\artifacts\issue190\lm1-h-primitive-blocker-localization-001\proposal.json`
has canonical SHA-256
`c1050eea1c9f049629f7126a2d1d7b0371b4653edd53faa7ff31ad832e4325a7`
and file SHA-256
`b80122b2031c709227c95e8e67f4c67ba9f650dbc6fc8764d91808fbc1e616ca`.
It resolves the 13 blocker body pairs into 20 blocker primitive pairs with
exact sample ranges. Both boxes for link 2, all four boxes for link 3, both
boxes for link 4, and the single boxes for link 5 and the gripper participate
in at least one blocker. Therefore the evidence does not justify deleting an
isolated primitive. The next physical-geometry experiment must refine the
whole conservative representation while preserving source-mesh containment,
starting with link 5's whole-link fallback box. Moving station planning
envelopes out of PhysX-solid semantics remains a separate route-predicate
experiment.

Reproduce the primitive-attributed replay and localization with zero hardware
authority:

```powershell
$env:PYTHONPATH = 'C:\icq7\software\src'
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
& 'C:\IsaacSim\env_6_1_0\Scripts\python.exe' `
  software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --run-collision-diagnostic `
  --collision-request C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-request-001\request.json `
  --accepted-collision-pair-policy C:\IsaacSim\artifacts\issue190\lm1-h-collision-pair-policy-001\policy.json `
  --ik-receipt C:\IsaacSim\artifacts\issue190\lm1-h-ik-screen-001\receipt.json `
  --collision-candidate C:\IsaacSim\evidence\issue190\simulation_program\collision_candidate_v1.json `
  --virtual-profile software\config\virtual_commissioning_profile.json `
  --robot-usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --import-receipt C:\IsaacSim\evidence\urdf_import_003.json `
  --output C:\IsaacSim\artifacts\issue190\lm1-h-primitive-attributed-collision-diagnostic-001\receipt.json `
  --status-output C:\IsaacSim\artifacts\issue190\lm1-h-primitive-attributed-collision-diagnostic-001\status.json

$artifactDir = 'C:\IsaacSim\artifacts\issue190\lm1-h-primitive-blocker-localization-001'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --localize-collision-blockers `
  --collision-diagnostic-receipt C:\IsaacSim\artifacts\issue190\lm1-h-primitive-attributed-collision-diagnostic-001\receipt.json `
  --collision-request C:\IsaacSim\artifacts\issue190\lm1-h-policy-bound-collision-request-001\request.json `
  --cartesian-request C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001\request.json `
  --output "$artifactDir\proposal.json" `
  --status-output "$artifactDir\status.json"
```

ARM-196 tests whether link 5's whole-link fallback box causes those localized
route blockers. The generalized triangle partition probe preserves every
source triangle exactly once, supports deterministic connected-component
clustering, can bind the result into an unapplied collision candidate, and can
fit either axis-aligned or oriented boxes. Its historical link 2 default
remains byte-compatible at receipt SHA-256
`cf887206e9afdadb46a20263db56406eabfe90a78c3f9d1e5ad0e8dc3fbc6469`.

The selected 32-box oriented link 5 experiment is retained externally at
`C:\IsaacSim\artifacts\issue190\arm196-link5-components-obb-32`. Its
refinement receipt SHA-256 is
`b75da3fa395fd39fdf2cb026e3f4e54152ea33ccf66571f3916af37d44c9c95f`
and its unapplied candidate SHA-256 is
`c26fa2ff7920b29d5f24c7d79dcbb518b576b52f0ef02ba18e34b2775f7f3be5`.
All source triangles are covered with zero serialized vertex overflow. The
same 49-pose CPU differential reports zero observed false negatives, but it
does not improve the existing link 2/gripper false positive.

The native diagnostic now validates finite, orthonormal, right-handed box
rotations and authors them into USD. The 149-sample result at
`C:\IsaacSim\artifacts\issue190\arm196-link5-components-obb-native-32`
has canonical receipt SHA-256
`e1a6ddc7c52ec5acda2eee9e0ae628d705a44d85ca4f9db009a67b80a6e8b7b`
and file SHA-256
`578b9f8f18c4dd3d8e5524492869bb613e74cd3b7f0a539aeb542bc66feb83dc`.
It preserves all 18 body-level pairs and produces the same 130 link 5
primitive-pair observations as the axis-aligned component candidate. The
earlier whole-mesh centroid partition also preserved all body-level blockers
while increasing primitive overlap multiplicity.

These are retained negative results, not a promoted collision profile. They
show that further link 5 box subdivision is not the correction for this route.
No candidate in this experiment is installed or grants collision, contact,
controller, or physical authority.

ARM-197 implements the next boundary as a hash-bound station route predicate.
Contact endpoints must lie inside a station explicitly bound to their target;
transit occupancy is recorded but is not treated as contact. The native runner
admits that predicate only with the exact Cartesian request, collision
candidate, and an accepted adjacent-link diagnostic policy. When admitted, it
authors board, keyboard, and phone bodies as physical collision solids while
excluding `workcell:station:*` planning regions from PhysX.

The retained zero-authority run is at
`C:\IsaacSim\artifacts\issue190\arm197-station-route-predicate-001`. The
predicate SHA-256 is
`80a8091343ff4d297cc91e62440cb241107abe9aa0468433187266b606fd55f1`;
the native receipt SHA-256 is
`0c7a13f2dec6cda0d2a38274f7917eba6efab6670e5d140c5c903278d0ef35eb`.
Across the exact 149-sample route, the result contains zero station-envelope
blockers and seven physical blockers: five robot-link/board pairs plus
two keyboard pairs (`gripper/keyboard` and `link5/keyboard`), consolidated by
body pair. This proves that station semantics are no longer contaminating
the collision result; it does not prove the route collision-free. The next
experiment must correct measured board/keyboard placement or the route against
those physical solids, then separately satisfy continuous-geometry evidence.

ARM-198 turns that result into a hash-bound, zero-authority experiment plan
without changing the route or any collision solid. The planner verifies the
exact Cartesian request, collision candidate, native diagnostic, blocker
localization, and raw virtual-profile file hashes. It then separates implicated
`TRANSIT` samples from `CONTACT`, `HOVER`, and `RETRACT` endpoint blockers.

The retained plan is at
`C:\IsaacSim\artifacts\issue190\arm198-physical-blocker-experiment-plan-001`.
Its plan SHA-256 is
`a681306a075f79526d3296b1202b5f6726fa7718ad019b1b98f867632b09a096`.
The physical workcell top is `21 mm`; an explicit `49 mm` simulation margin
therefore proposes a `70 mm` transit-height hypothesis for 71 implicated
Cartesian sequences. All seven physical body pairs also occur at one or more
endpoint phases and remain assigned to separate placement/TCP/geometry work.
The source placement remains `UNMEASURED_SENSITIVITY_OVERLAY`; the plan applies
no route variant, changes no geometry, and grants no hardware or motion
authority.

Reproduce the experiment plan with:

```powershell
$artifactDir = 'C:\IsaacSim\artifacts\issue190\arm198-physical-blocker-experiment-plan-001'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --plan-physical-blocker-experiment `
  --cartesian-request C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001\request.json `
  --collision-candidate C:\IsaacSim\artifacts\issue190\arm196-link5-components-obb-32\collision_candidate.json `
  --collision-diagnostic-receipt C:\IsaacSim\artifacts\issue190\arm197-station-route-predicate-001\native_receipt.json `
  --blocker-localization C:\IsaacSim\artifacts\issue190\arm197-station-route-predicate-001\localization.json `
  --virtual-profile software\config\virtual_commissioning_profile.json `
  --clearance-margin-mm 49 `
  --output "$artifactDir\plan.json" `
  --status-output "$artifactDir\status.json"
```

The follow-on ARM-198 route-variant experiment applies that plan without
silently turning it into ordinary mechanics regeneration. The variant is
admitted only when the original Cartesian request and experiment plan both
reproduce their canonical digests. It changes Z to `70 mm` for exactly the 71
plan-selected `TRANSIT` samples; X/Y, timing, phases, targets, all endpoints,
and collision geometry remain unchanged.

The retained artifact is
`C:\IsaacSim\artifacts\issue190\arm198-transit-route-variant-001`. The variant
request SHA-256 is
`7f95dfb7d50d5b1f9789f8faf5d412ad34d254da8caf6c5bd473c5404d5d438d`.
Canonical IK accepts all 133 samples (receipt SHA-256
`e93569d4226a64c35c5c1045f1ae8d88d3c566666958fcbd99c8c4d347bb67f6`).
The policy-bound native diagnostic then evaluates 179 bounded configurations
and retains seven physical board/keyboard blocker pairs, zero station-envelope
blockers, and five policy-excluded adjacent-link pairs. Its receipt SHA-256 is
`f31a97dc341502199ddba7bd80ecad83d62cd49d8520382b1edaccb2e0c4be0b`;
the localization SHA-256 is
`f421afd8335f18533970861bb978bd141a44e24bfe75a23229d2c3c593472327`.

This is a useful negative result. The uniform tip-height lift is reachable, but
it changes rather than clears the full-link collision pattern. Endpoint phases
also remain blocked. The next route correction must jointly evaluate measured
placement/TCP hypotheses and full-link trajectories; it must not remove or
resize physical solids or treat a raised TCP as whole-arm clearance proof.

ARM-199 begins that attribution without inventing new dimensions after seeing
the collision result. Its hash-bound plan contains one retained ARM-198 control
plus the 81 keyboard-relevant combinations from the already documented
pre-hardware sensitivity grid: rear-clamp X `225/305/385 mm`, rear-axis Y
`0/50/100 mm`, base yaw `-105/-90/-75 degrees`, and keyboard TCP
`80/100/120 mm`. The retained `75 mm` rear-axis control remains separate from
the coarse grid. Candidate rejection recording and the ranking order are fixed
before screening, and no more than eight deterministically selected candidates
may enter native Isaac replay.

The retained plan is at
`C:\IsaacSim\artifacts\issue190\arm199-placement-tcp-search-plan-001`.
It contains 82 unique candidates and has plan SHA-256
`9053512e8b57e326368bb61eabb7af074c12e15658a66832d522e3a7280b91f7`.
Every candidate remains an unmeasured, simulation-only sensitivity hypothesis.
Board and keyboard solids, route shape, pair policy, station predicate, and
toolchain identity are unchanged; endpoint and continuous-clearance gates stay
separate.

Reproduce the plan with:

```powershell
$artifactDir = 'C:\IsaacSim\artifacts\issue190\arm199-placement-tcp-search-plan-001'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --plan-placement-tcp-search `
  --cartesian-request C:\IsaacSim\artifacts\issue190\arm198-transit-route-variant-001\request.json `
  --physical-blocker-experiment-plan C:\IsaacSim\artifacts\issue190\arm198-physical-blocker-experiment-plan-001\plan.json `
  --collision-diagnostic-receipt C:\IsaacSim\artifacts\issue190\arm198-transit-route-variant-001\native_receipt.json `
  --blocker-localization C:\IsaacSim\artifacts\issue190\arm198-transit-route-variant-001\localization.json `
  --virtual-profile software\config\virtual_commissioning_profile.json `
  --output "$artifactDir\plan.json" `
  --status-output "$artifactDir\status.json"
```

ARM-199 execution is now retained as a negative native result. Canonical IK
accepted only three of the 82 candidates. The deterministic shortlist was the
ARM-198 control (`385 mm`, `75 mm`, `-105 degrees`, `120 mm TCP`) and two
`305 mm` / `100 mm` / `80 mm TCP` hypotheses at `-90` and `-105 degrees`.
The native control exactly reproduced the ARM-198 collision baseline: all 179
bounded samples overlap and the same seven physical blocker pairs remain. The
two alternatives were worse: all `188/188` and `189/189` samples overlap and
each adds `robot:link4` / `workcell:keyboard` as an eighth physical blocker.

The offline exact-OBB screen reported no physical blockers for all three IK
survivors, while native PhysX reported seven or eight. That disagreement is
retained as an evaluator discrepancy; the offline result is not a clearance
claim. The native result selection therefore keeps the control, installs
nothing, promotes no gate, and records `NO_NATIVE_IMPROVEMENT_RETAINED`.

External evidence:

- offline screen:
  `C:\IsaacSim\artifacts\issue190\arm199-placement-tcp-offline-screen-001\screen.json`,
  SHA-256 `106aecaf8e187dec18a84b73d21f7c090203a8eb7a02f9ed500aac6f7568b15c`;
- native shortlist manifest:
  `C:\IsaacSim\artifacts\issue190\arm199-placement-tcp-native-shortlist-002\manifest.json`,
  SHA-256 `9aa01abeb0bd4bf078801ef7ee56b3ca54a506f1371b8821ac31c6ca54072866`;
- retained native selection:
  `C:\IsaacSim\artifacts\issue190\arm199-placement-tcp-native-selection-001\selection.json`,
  SHA-256 `3e05cd9f7073911ef33a2d9d453948f2305d1ae07ce256f92e4e0ab459f67611`.

The selection artifact preserves every native sample and raw collision pair.
Its next dependency is a separately planned, source-bound full-link route-shape
campaign; repeating this coarse placement/TCP grid is not justified by the
retained evidence.

ARM-200 fixes that route-shape campaign before any new candidate is screened.
The plan binds the exact ARM-199 search plan, its retained
`NO_NATIVE_IMPROVEMENT_RETAINED` selection, and the exact ARM-198 Cartesian
route. It preserves the selected control placement/TCP, physical board and
keyboard solids, collision-pair policy, station predicate, toolchain identity,
all 14 non-transit endpoints, sample count, and timing.

The campaign contains nine candidates: the exact direct/70 mm control plus the
remaining combinations of `DIRECT_LINEAR`, `X_THEN_Y`, and `Y_THEN_X` XY
corridors at `70/90/110 mm`. Variants use deterministic arc-length piecewise
linear resampling with symmetric 25% Z ramps over the existing 119 TRANSIT
sequences. Endpoint blockers are ranked separately and cannot be waived by a
transit improvement. No more than four deterministically ranked candidates may
enter native Isaac replay.

The retained plan is
`C:\IsaacSim\artifacts\issue190\arm200-route-shape-campaign-plan-001\plan.json`.
Its canonical plan SHA-256 is
`f759191e9bed351c0e374bf034526aa46a85196b641e1c13590c62a99fec2ac6`
and its file SHA-256 is
`07ae8eadfdab85d4bca0c5979847e5650278b917f491c28f4f65d36698cdd884`.

Reproduce the plan with:

```powershell
$artifactDir = 'C:\IsaacSim\artifacts\issue190\arm200-route-shape-campaign-plan-001'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --plan-route-shape-campaign `
  --placement-tcp-search-plan C:\IsaacSim\artifacts\issue190\arm199-placement-tcp-search-plan-001\plan.json `
  --placement-tcp-native-selection C:\IsaacSim\artifacts\issue190\arm199-placement-tcp-native-selection-001\selection.json `
  --cartesian-request C:\IsaacSim\artifacts\issue190\arm198-transit-route-variant-001\request.json `
  --output "$artifactDir\plan.json" `
  --status-output "$artifactDir\status.json"
```

ARM-201 executes the fixed portion of that plan. All nine Cartesian requests
were materialized exactly. Six candidates pass all 133 canonical IK and
discrete-continuity samples. The three `X_THEN_Y` routes reject with
`IK_NO_CONVERGED_SOLUTION` at their first unreachable samples (9, 7, and 6 for
70, 90, and 110 mm); those failed results retain empty joint solutions as the
IK contract requires rather than being lost to an evidence-shape exception.

The exact offline full-link OBB evaluator reports zero physical blocker pairs
in both the 119-sample TRANSIT domain and the 14 preserved endpoints for all
six IK survivors. That does **not** establish clearance: ARM-199 already showed
that this offline evaluator can report zero while native PhysX reports seven or
eight blocker pairs. The fixed ranking therefore creates only a native replay
shortlist, in order: `Y_THEN_X/110`, `DIRECT_LINEAR/110`, `Y_THEN_X/70`, and
`DIRECT_LINEAR/90`.

Retained ARM-201 evidence:

- materialized requests and IK receipts:
  `C:\IsaacSim\artifacts\issue190\arm201-route-shape-materialization-001`;
- aggregate screen:
  `C:\IsaacSim\artifacts\issue190\arm201-route-shape-screen-001\screen.json`,
  screen SHA-256
  `d1bee840796d434d3a69902a116219ab6fc3c30eee501368112ef2f1f848d511`;
- four-candidate native handoff:
  `C:\IsaacSim\artifacts\issue190\arm201-route-shape-native-shortlist-001\manifest.json`,
  manifest SHA-256
  `e7aff82d77e731e1ba7b1e11784cdceb209e3b32cb961bb11e60acb09c7eb9e6`.

ARM-202 preserves the first fixed native attempt exactly, including its setup
errors. The rank-one `Y_THEN_X/110` invocation stopped before Isaac admission
with `collision pair policy boundary changed`; no automatic retry occurred.
The remaining `DIRECT_LINEAR/110`, `Y_THEN_X/70`, and `DIRECT_LINEAR/90`
attempts completed as v3 primitive-attributed diagnostics. They omitted the
separate station-route-predicate argument, so they are not the complete v4
replay requested by ARM-201. Physical and planning pairs remain separately
reported: every bounded sample overlaps (`169/169`, `170/170`, and `165/165`),
and every completed attempt retains seven physical blocker pairs, six planning
envelope pairs, five policy exclusions, and zero unreviewed pairs. The physical
pair count therefore does not improve on the ARM-199 control.

The retained mixed-outcome selection is
`C:\IsaacSim\artifacts\issue190\arm202-route-shape-native-selection-001\selection.json`.
Its canonical selection SHA-256 is
`07d91503a2a6507dd4b997da5b19ff415f09644f4b0a2b04250560b0ac2a1858`
and its file SHA-256 is
`c87cf97120ced00cee40c6aa9e0b8026776b52acdf345a56c886ee315e11610a`.
Status `INCOMPLETE_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED` installs nothing,
promotes no gate, and grants no physical authority.

Reproduce the aggregate screen after materializing and IK-screening all nine
candidate directories:

```powershell
$root = 'C:\IsaacSim\artifacts\issue190'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --screen-route-shape-campaign `
  --route-shape-campaign-plan "$root\arm200-route-shape-campaign-plan-001\plan.json" `
  --route-shape-evidence-dir "$root\arm201-route-shape-materialization-001" `
  --cartesian-request "$root\arm198-transit-route-variant-001\request.json" `
  --collision-candidate "$root\arm196-link5-components-obb-32\collision_candidate.json" `
  --accepted-collision-pair-policy "$root\arm197-station-route-predicate-001\pair_policy.json" `
  --station-route-predicate "$root\arm198-transit-route-variant-001\station_route_predicate.json" `
  --workspace . `
  --output "$root\arm201-route-shape-screen-001\screen.json" `
  --status-output "$root\arm201-route-shape-screen-001\status.json"
```

A corrected separately planned v4 route-predicate replay and separate
continuous-clearance qualification remain required. No
ARM-201 artifact installs a route or grants physical authority.

ARM-203 performed that separately governed correction without changing or
retrying ARM-202. Each route shape received a station predicate generated from
its own Cartesian request. Two fixed attempts stopped before producing a
receipt: rank one retained the predicate-boundary error, and rank two retained
a legacy Isaac 4.2 initialization access violation. Neither was retried. The
remaining `Y_THEN_X/70` and `DIRECT_LINEAR/90` attempts completed in the
governed Isaac 6.1 runtime with v4 route-predicate receipts. All bounded samples
still overlap (`170/170` and `165/165`), and each result retains seven physical
solid blocker pairs, zero planning-envelope blocker pairs, and five
policy-excluded pairs. Neither improves on the seven-pair ARM-199 control.

The retained selection is
`C:\IsaacSim\artifacts\issue190\arm203-route-shape-v4-native-selection-001\selection.json`.
Its canonical selection SHA-256 is
`db4d0812f541fb9445b6cbf09d1f12425768a79598c9dd4d096f65495ae7d186`
and its file SHA-256 is
`fe055795d45d232ce40201e68c3a2ebba5a3f4fbbf81e3e60bdb49aba8f11b99`.
Status `INCOMPLETE_V4_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED` installs no
route, proves no continuous clearance, promotes no gate, and grants no
physical authority.

ARM-204 explains why the portable OBB screen and the retained v4 native
diagnostics disagreed before another route search is attempted. It fixes three
samples per completed ARM-203 candidate (first physical onset, peak physical
pair count, and first later physical-clear sample), captures every collision
primitive in board coordinates, and compares the native and portable poses
without changing geometry, placement, or route.

All 18 static workcell primitive comparisons match exactly. All 270 robot
primitive comparisons instead share a sample-specific rigid translation: X/Y
remain within `0.02 mm`, while native-minus-portable Z grows from roughly
`-120 mm` to `-343 mm`. The robot base primitive has the same displacement as
the distal links, so this is an articulation-root Z drift signature rather
than a local OBB approximation error. The capture also exposed a separate
Isaac `Gf` row/column rotation serialization convention that must be
canonicalized in the corrected replay.

The retained ARM-203 v4 collision conclusions are therefore not usable for a
fixed-base route comparison. They remain immutable diagnostic history, but
their seven physical blocker pairs must not drive more route or placement
search. The next bounded action is a corrected static-geometry native replay
with an explicitly fixed base, a per-sample root-pose invariant, canonical
rotation serialization, and fresh parity comparison. It grants no hardware or
motion authority.

Retained external ARM-204 evidence:

- plan:
  `C:\IsaacSim\artifacts\issue190\arm204-collision-geometry-parity-plan-001\plan.json`,
  canonical SHA-256
  `c4b6798d94b1a908d762b77812fdc96d06e1836e891fbfcaebf56690775a2e26`;
- merged native capture:
  `C:\IsaacSim\artifacts\issue190\arm204-collision-geometry-native-capture-001\capture.json`,
  canonical SHA-256
  `506071c41a4fb4cbc7c71022c41d754097869e8e41e1746d0041b1c7c8216703`;
- portable capture:
  `C:\IsaacSim\artifacts\issue190\arm204-collision-geometry-offline-capture-001\capture.json`,
  canonical SHA-256
  `6e51e2c75246db907cc01db10c9887e63247c4ffa9f8386b7665a5a2c494331f`;
- classified report:
  `C:\IsaacSim\artifacts\issue190\arm204-collision-geometry-parity-report-001\report.json`,
  canonical SHA-256
  `089d3f633d9103f7f7ae668f940e99f730b3d1450b89d5e1087869174aadf51e`.

ARM-205 implements the corrected replay instead of optimizing against the
moving-base v4 evidence. The v5 diagnostic authors a USD fixed joint from the
robot base to world before physics initialization, uses explicit matching
joint frames, canonicalizes Isaac `Gf` rotations, and checks the requested
root pose at admission and after every bounded sample. Five deterministic
physics updates and fixed solver iteration counts are retained in each
receipt. The root contract permits `0.05 mm` translation and `0.1 degree`
orientation error; the latter is above the observed single-precision
quaternion floor without masking meaningful base motion.

Both retained candidates completed: 165 and 170 samples, plus one admission
observation each. All 337 root observations pass. Maximum translation drift is
`0.006403 mm` and maximum orientation drift is `0.055953 degree`. Both v5
receipts retain zero physical-solid, planning-envelope, and unreviewed blocker
pairs; their five overlap pairs are all policy-excluded adjacent/mechanical
pairs. This corrects the prior seven-pair conclusion but still does not prove
continuous clearance or authorize hardware motion.

Retained external ARM-205 evidence:

- fixed-base plan:
  `C:\IsaacSim\artifacts\issue190\arm205-fixed-base-collision-replay-plan-001\plan.json`,
  canonical SHA-256
  `1975d066fbd644095e60bb21cfcd4a190b6fbdf72dfe4e33ce258e0868fbbada`;
- `route-shape-3261d2d2f56ade9a` v5 receipt SHA-256
  `c7ae522b75d4754cf62c6ebf89bd289771985a9c7c314a6523b24d0d7e705d1d`;
- `route-shape-89d6b94237805cfe` v5 receipt SHA-256
  `98aa5b517aa76fb170ff087dbacec5a74137cb9432c226a619999734dbe4d6ed`;
- retained result:
  `C:\IsaacSim\artifacts\issue190\arm205-fixed-base-collision-replay-001\result.json`,
  canonical SHA-256
  `c968eda779c07a16efe38172b828dff270c84f20b8790b15962a5d8743ff395d`.

ARM-206 performs that comparison without treating commanded kinematics as
drive/contact evidence. Both candidates reproduce the two governed centered
`H` actions at `2.7 mm` compression, complete release, and one activation per
action under the existing synthetic mechanics profile. Their projected key
outcomes are therefore equivalent. The fixed ranking then compares commanded
joint acceleration, adjacent-joint delta, total joint travel, velocity,
Cartesian path length, and IK error.

`route-shape-3261d2d2f56ade9a` (`DIRECT_LINEAR/90`) is selected as the
zero-authority simulation-learning baseline. Relative to `Y_THEN_X/70`, it
retains lower maximum commanded acceleration (`2.775694` versus `4.529937
rad/s^2`), lower maximum adjacent-joint delta (`0.072975` versus `0.118004
rad`), lower total joint travel (`9.962121` versus `11.551166 rad`), and a
shorter Cartesian path (`870.360394` versus `889.377367 mm`). Its slightly
higher maximum commanded velocity and IK error remain explicit. The external
selection is retained at
`C:\IsaacSim\artifacts\issue190\arm206-key-mechanics-learning-baseline-001\selection.json`,
canonical SHA-256
`36f5c7bdaaee9541ec2132f497285abcf3fd88b0722f91a9a4a4619dc063c050`.

Reproduce the comparison without starting Isaac or touching hardware:

```powershell
$root = 'C:\IsaacSim\artifacts\issue190'
python software\integrations\isaac_sim\collision_geometry_parity.py `
  --select-learning-baseline `
  --fixed-base-result "$root\arm205-fixed-base-collision-replay-001\result.json" `
  --fixed-base-receipt "$root\arm205-fixed-base-collision-replay-001\route-shape-3261d2d2f56ade9a\receipt.json" `
  --fixed-base-receipt "$root\arm205-fixed-base-collision-replay-001\route-shape-89d6b94237805cfe\receipt.json" `
  --cartesian-request "$root\arm201-route-shape-materialization-001\route-shape-3261d2d2f56ade9a\request.json" `
  --cartesian-request "$root\arm201-route-shape-materialization-001\route-shape-89d6b94237805cfe\request.json" `
  --ik-receipt "$root\arm201-route-shape-materialization-001\route-shape-3261d2d2f56ade9a\ik_receipt.json" `
  --ik-receipt "$root\arm201-route-shape-materialization-001\route-shape-89d6b94237805cfe\ik_receipt.json" `
  --layout software\config\nominal_target_profiles.json `
  --output "$root\arm206-key-mechanics-learning-baseline-001\selection.json"
```

The next bounded action is a drive-controlled native robot-to-`H` replay for
the selected baseline. ARM-206 does not prove native contact, continuous
clearance, installed collision qualification, or physical authority.

ARM-207 implements that boundary without changing the selected route or the
shared key acceptance contract. A strict compiler binds the ARM-206 selection,
133-sample Cartesian and IK evidence, ARM-205 fixed-base result, placement
selection, representative-key profile, passing isolated native-key receipt,
provisional drive profile, normalized import receipt, and exact robot USD. The
retained plan is
`C:\IsaacSim\artifacts\issue190\arm207-drive-controlled-robot-h-replay-plan-001\plan.json`
with canonical SHA-256
`04354ee380a73fcead903b24419d2d1ac44429e11eb4a04204a00b8ae087072b`.
It admits only `DIRECT_LINEAR/90`, preserves the two `H` endpoints at
sequences 35 and 38, permits one initialization placement, and requires all
subsequent robot motion to use articulation position targets.

The first native run retained a blocked tool-frame diagnostic. The corrected
hand-TCP-composed run is
`C:\IsaacSim\artifacts\issue190\arm207-drive-controlled-robot-h-replay-002\receipt.json`
with receipt SHA-256
`1da693f8a8ce79d6792cddb9d4bd17fd988f9e7c67892e57d0bcb0dee8cdaba7`.
The robot reaches and physically depresses the native `H` key, and all 133
fixed-root observations pass. The unchanged mechanics evaluator rejects the
route: provisional drive tracking overshoots to about `3.78 mm`, and the key
has not completed release before the immediate second action. This is a useful
drive/timing blocker, not a contact pass. No hardware access, controller
command, physical movement, gate promotion, or post-initialization state
teleport occurred. The next bounded action is to produce a simulation-only
drive/timing adaptation that adds a verified release dwell and limits contact
overshoot, then replay it through this same admission and evaluator.

ARM-208 performs exactly one feedback-derived adaptation without weakening the
mechanics evaluator. It binds the ARM-207 plan and blocked native receipt,
reduces only the two H contact targets, adds 240 physics steps (two seconds) of
hold at each retract target, and adds a `0.05 rad` maximum tracking-error gate.
The retained plan is
`C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-plan-001\plan.json`
with canonical SHA-256
`def0bc128bf7b61741d1d6fa96825039583eb723fe0e8e031d1eff43f73d5d1f`.

The native result remains blocked, but it localizes the next correction. The
receipt at
`C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-001\receipt.json`
has canonical SHA-256
`604592c27a58ac288d3f3b0b46bdbfe4ca54f266a8673f2a19289fb391755d9d`.
All 133 root checks pass and maximum joint tracking error is
`0.037722640842437705 rad`, below the new bound. Peak H compression falls from
about `3.78` to `3.66 mm`, but both actions still fail excessive-travel and
release checks. The trace explains why: sequence 34, the nominal H hover,
already moves the key from its `18 mm` rest center to about `15.39 mm`, and the
unchanged retract settles near `15.63 mm`. Extra dwell cannot release a key
whose nominal hover/retract geometry continues to hold it down. The next
bounded simulation action must derive and requalify a lifted H approach,
hover, and retract path from this trace; it must preserve the same mechanics
thresholds, fixed-root checks, tracking gate, and zero authority.

Reproduce the plan and native result with:

```powershell
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --build-feedback-adapted-robot-h-replay-plan `
  --replay-plan C:\IsaacSim\artifacts\issue190\arm207-drive-controlled-robot-h-replay-plan-001\plan.json `
  --source-replay-receipt C:\IsaacSim\artifacts\issue190\arm207-drive-controlled-robot-h-replay-002\receipt.json `
  --output C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-plan-001\plan.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-plan-001\status.json
$env:PYTHONPATH = 'C:\icq7\software\src'
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
& 'C:\IsaacSim\env_6_1_0\Scripts\python.exe' `
  software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --run-drive-controlled-robot-h-replay `
  --replay-plan C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-plan-001\plan.json `
  --drive-profile software\config\isaac_lm0b_geometry_prior_profile.json `
  --robot-usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --output C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-001\receipt.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-001\status.json
```

ARM-209 performs the trace-derived lift. It binds the exact ARM-208 plan and
blocked receipt and reuses sequence 33 as the H no-contact anchor because the
retained trace proves `0.9192380448754013 mm` minimum clearance and zero key
compression there. Hover/retract sequences 34, 36, 37, and 39 reuse that
qualified target; contact sequences 35 and 38 are bounded interpolations from
the anchor. The retained plan is
`C:\IsaacSim\artifacts\issue190\arm209-trace-lifted-robot-h-replay-plan-001\plan.json`
with canonical SHA-256
`27b72da14f3de704ec7bb191e3a11439f700c1540d725ec9bc3d8423db500f77`.

The native receipt in the same directory has canonical SHA-256
`09d0e3eeaa657747abf28abbd469551ee6c29adf8ccbcf031aa7587d94440ba5`.
Both H actions now activate exactly once and completely release, every one of
the 133 root checks passes, and maximum tracking error remains
`0.037722640842437705 rad`. The result stays blocked because peak compression
is about `3.542 mm`, roughly `0.043 mm` over the unchanged travel limit. The
next bounded action is contact-depth refinement from this receipt; release
timing and hover geometry are no longer the blocker.

Compile the retained ARM-209 plan with:

```powershell
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --build-trace-lifted-robot-h-replay-plan `
  --replay-plan C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-plan-001\plan.json `
  --source-replay-receipt C:\IsaacSim\artifacts\issue190\arm208-feedback-adapted-robot-h-replay-001\receipt.json `
  --output C:\IsaacSim\artifacts\issue190\arm209-trace-lifted-robot-h-replay-plan-001\plan.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm209-trace-lifted-robot-h-replay-plan-001\status.json
```

ARM-210 preserves that lifted release path and refines only contact sequences
35 and 38 from the ARM-209 receipt. The retained plan is
`C:\IsaacSim\artifacts\issue190\arm210-contact-refined-robot-h-replay-plan-001\plan.json`
with canonical SHA-256
`41f216b1828ed476679a49060368ca0bda4494856ad107659264ebe24aafa81f`.
Its bounded native replay passes the unchanged evaluator. Both actions activate
exactly once, peak at `2.744280733168125 mm` and `2.731158398091793 mm`, and
fully release. All 133 root checks pass, maximum tracking error remains
`0.037722640842437705 rad`, and the receipt canonical SHA-256 is
`618a7146b623c39650e5945ee774b2427d1333f7bb360e76746410abf7bf2e60`.
Hardware access, writes, physical motion, controller commands, and gate
promotions remain zero. This is a passing representative simulated H skill,
not continuous-clearance, installed-collision, generalized-keyboard, or
physical qualification.

Compile the ARM-210 plan with:

```powershell
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --build-contact-refined-robot-h-replay-plan `
  --replay-plan C:\IsaacSim\artifacts\issue190\arm209-trace-lifted-robot-h-replay-plan-001\plan.json `
  --source-replay-receipt C:\IsaacSim\artifacts\issue190\arm209-trace-lifted-robot-h-replay-001\receipt.json `
  --output C:\IsaacSim\artifacts\issue190\arm210-contact-refined-robot-h-replay-plan-001\plan.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm210-contact-refined-robot-h-replay-plan-001\status.json
```

ARM-211 retains the passing ARM-210 result as a governed LM2 adaptation seed.
The record binds the exact plan, native receipt, and mechanics-profile hashes;
keeps sequences 33 through 39 as the H source-skill window; and records the
two accepted native actions, all 133 fixed-root observations, and the
`0.037722640842437705 rad` maximum tracking error. It is deliberately not a
multi-key dataset. `1`, `SPACE`, `ENTER`, and `PERIOD` remain pending, and the
contract forbids reusing H joint angles for them. Each must start from its
governed board-frame geometry and pass fresh IK, collision/fixed-root, and
native key-mechanics qualification.

The retained external demonstration is
`C:\IsaacSim\artifacts\issue190\arm211-governed-h-demonstration-001\demonstration.json`
with canonical SHA-256
`27d7d77bac289b1e8f3081d7e2bac11e3279c7775c685c25e80e11a68e58d1ee`.
It grants no hardware, controller, physical-motion, or physical-keyboard
authority.

Reproduce it with:

```powershell
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --retain-governed-h-demonstration `
  --replay-plan C:\IsaacSim\artifacts\issue190\arm210-contact-refined-robot-h-replay-plan-001\plan.json `
  --source-replay-receipt C:\IsaacSim\artifacts\issue190\arm210-contact-refined-robot-h-replay-001\receipt.json `
  --output C:\IsaacSim\artifacts\issue190\arm211-governed-h-demonstration-001\demonstration.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm211-governed-h-demonstration-001\status.json
```

ARM-212 compiles that seed into four target-specific Cartesian skill requests.
The external campaign at
`C:\IsaacSim\artifacts\issue190\arm212-representative-key-adaptation-campaign-001\campaign.json`
has canonical SHA-256
`dc25b88b31c200f5e2b9105473a4fe36c820927f41fb7cecddbbe02c3ee16afe`.
Each request uses its governed board-frame key center, the transferred `2.7 mm`
contact policy, and the lifted anchor semantics. No H joint angle is copied.
All four requests still require a park-to-skill route connection, fresh IK,
collision/fixed-root qualification, and native mechanics replay.

```powershell
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --build-representative-key-adaptation-campaign `
  --governed-demonstration C:\IsaacSim\artifacts\issue190\arm211-governed-h-demonstration-001\demonstration.json `
  --cartesian-request C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001\request.json `
  --output C:\IsaacSim\artifacts\issue190\arm212-representative-key-adaptation-campaign-001\campaign.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm212-representative-key-adaptation-campaign-001\status.json
```

ARM-213 materializes those four park-to-skill connections. It preserves the
governed `[290, 10, 70] mm` park endpoint and each seven-sample ARM-212 skill,
inserting 32 target-specific samples under the selected ARM-206
`DIRECT_LINEAR` / `90 mm` corridor policy. The external campaign is
`C:\IsaacSim\artifacts\issue190\arm213-representative-key-park-route-campaign-001\campaign.json`
with canonical SHA-256
`9ae576abe4fe8d748602ad24c3744e6a0c982a9155e9d1c4f67c36d1ed4f106e`.
These requests contain no joint positions and still require fresh target IK,
collision/fixed-root checks, and native mechanics replay.

```powershell
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --build-representative-key-park-route-campaign `
  --representative-key-adaptation-campaign C:\IsaacSim\artifacts\issue190\arm212-representative-key-adaptation-campaign-001\campaign.json `
  --cartesian-request C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001\request.json `
  --learning-baseline-selection C:\IsaacSim\artifacts\issue190\arm206-key-mechanics-learning-baseline-001\selection.json `
  --output C:\IsaacSim\artifacts\issue190\arm213-representative-key-park-route-campaign-001\campaign.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm213-representative-key-park-route-campaign-001\status.json
```

ARM-214 runs fresh canonical IK and continuity qualification over every ARM-213
request. All 40 samples pass for all four targets. The campaign is retained at
`C:\IsaacSim\artifacts\issue190\arm214-representative-key-ik-campaign-001\campaign.json`
with canonical SHA-256
`81402e904b62e8edcaf82b5d68611e0212f3a4f43988c845824395b4e57e0e3d`.
The governed source bundle contributes only its initial joint seed and model
lineage; no H route joint solution is reused. Maximum Cartesian errors are
`0.055104`, `0.047272`, `0.076015`, and `0.061618 mm` for `1`, `SPACE`,
`ENTER`, and `PERIOD`, respectively. Collision/fixed-root and native contact
qualification remain separate required gates.

```powershell
$env:PYTHONPATH = 'software/src'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --qualify-representative-key-park-routes-ik `
  --representative-key-park-route-campaign C:\IsaacSim\artifacts\issue190\arm213-representative-key-park-route-campaign-001\campaign.json `
  --cartesian-request C:\IsaacSim\artifacts\issue190\lm1-h-cartesian-schedule-001\request.json `
  --ik-source-bundle software\integrations\isaac_sim\evidence\actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --workspace C:\icq7 `
  --output C:\IsaacSim\artifacts\issue190\arm214-representative-key-ik-campaign-001\campaign.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm214-representative-key-ik-campaign-001\status.json
```

ARM-215 converts those accepted joint routes into deterministic native replay
inputs without launching Isaac. The retained campaign contains `49`, `46`,
`58`, and `55` bounded configurations for `1`, `SPACE`, `ENTER`, and `PERIOD`,
respectively, plus the fixed-joint-to-world and per-sample root-pose invariant.
Its canonical SHA-256 is
`dfd20006fcd85958747b3b380d3912ca84f289b9cbbe354065d1261e891ddcf2`.

```powershell
$env:PYTHONPATH = 'software/src'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --build-representative-key-collision-replay-campaign `
  --representative-key-ik-campaign C:\IsaacSim\artifacts\issue190\arm214-representative-key-ik-campaign-001\campaign.json `
  --ik-source-bundle software\integrations\isaac_sim\evidence\actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --collision-candidate C:\IsaacSim\artifacts\issue190\arm196-link5-components-obb-32\collision_candidate.json `
  --toolchain-lock software\config\isaac_sim_toolchain_lock.json `
  --output C:\IsaacSim\artifacts\issue190\arm215-representative-key-collision-replay-campaign-001\campaign.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm215-representative-key-collision-replay-campaign-001\status.json
```

This campaign only makes the native work reproducible. It does not claim that
overlap queries ran, that any route has continuous clearance, or that contact
or physical execution is authorized.

ARM-216 closes that discrete native-collision step. It materializes one
policy-bound admission per representative target, derives the left/right
station region from each governed contact point, runs the existing fixed-base
Isaac/PhysX diagnostic, and aggregates the four hash-verified receipts. The
retained campaign covers all `208` bounded samples. Every per-sample root check
passes and the aggregate reports zero physical-solid, planning-envelope, and
unreviewed blocker pairs. Its canonical SHA-256 is
`e5a125adbbe5f0233ddf79323eaaeb2b519eee4503e12739581483cb4aedbedb`.

The aggregate remains diagnostic-only: the candidate geometry is uninstalled,
discrete overlap queries do not prove continuous clearance, and the four keys
still need the native mechanics evaluator before dataset admission. The
materializer and post-run aggregator are invoked with
`--materialize-representative-key-native-collision-inputs` and
`--aggregate-representative-key-native-collision-campaign`, respectively;
both use `--representative-native-output-dir` as the four-target artifact root.

ARM-217 closes the representative native-mechanics step. It compiles the
target-specific ARM-214 joint schedules and ARM-216 admissions into native key
replays for `1`, `SPACE`, `ENTER`, and `PERIOD`. The untouched baseline proves
correct target resolution and bounded tracking but is rejected for excessive
travel. The retained feedback path then derives a released anchor from each
native trace, preserves the target region and evaluator thresholds, and
refines only excessive contact endpoints. The final aggregate passes all eight
actions with complete release, fixed roots, and maximum joint tracking errors
between `0.037469` and `0.037922 rad`. Its canonical SHA-256 is
`3f8e7c9f70efddd7cc2495e1947ba6cafb900eddbab11c29f17ad4f50c1b1c30`.

The retained final artifact root is
`C:\IsaacSim\artifacts\issue190\arm217-representative-native-mechanics-refined-002`.
Use `--build-representative-key-native-mechanics-campaign` for the baseline,
`--build-feedback-adapted-representative-key-mechanics-campaign` for the
trace-derived release path, and
`--build-contact-refined-representative-key-mechanics-campaign` for bounded
contact-only iterations. `--aggregate-representative-key-native-mechanics-campaign`
admits only four hash-bound PASS receipts. This creates a provisional
zero-authority multi-key simulation dataset; it does not install collision
geometry, prove continuous clearance, or authorize physical motion.

ARM-218 starts the randomized LM3 dataset boundary by compiling the admitted
ARM-217 result into a deterministic `24`-episode manifest (`12` train, `8`
validation, `4` test). Seeds and scene identities are unique across all splits;
each episode binds its source plan and receipt and records declared provisional
mechanics and placement parameters. Its aggregator requires a complete receipt
for every attempted episode, including classified failures, so successful-only
filtering cannot change the denominator.

```powershell
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --build-randomized-demonstration-campaign `
  --source-result-campaign C:\IsaacSim\artifacts\issue190\arm217-representative-native-mechanics-refined-002\result_campaign.json `
  --source-artifact-root C:\IsaacSim\artifacts\issue190\arm217-representative-native-mechanics-refined-002 `
  --master-seed 218 `
  --output C:\IsaacSim\artifacts\issue190\arm218-randomized-demonstration-smoke-001\campaign.json `
  --status-output C:\IsaacSim\artifacts\issue190\arm218-randomized-demonstration-smoke-001\status.json
```

The retained manifest has canonical SHA-256
`6b38bbc2e0625e83283666c2d94b90ebe05ec5e442426f7b09c3245fc84c22f1`.
The bounded episode worker consumes exactly one manifest episode, verifies its
plan and prior native receipt, applies the precommitted key stiffness, damping,
mass, keyboard XY offset, and keyboard yaw to the existing native robot/key
replay, and writes a canonical JSONL trajectory plus one complete PASS/FAIL
receipt. It performs no automatic retry. An interrupted process therefore does
not create a completed receipt and cannot enter the strict aggregator.

```powershell
$campaignRoot = 'C:\IsaacSim\artifacts\issue190\arm218-randomized-demonstration-smoke-001'
$sourceRoot = 'C:\IsaacSim\artifacts\issue190\arm217-representative-native-mechanics-refined-002'
$episodeId = '<episode id from campaign.json>'
$target = '<lowercase target id from that episode>'
$episodeRoot = Join-Path $campaignRoot $episodeId
& 'C:\IsaacSim\env_6_1_0\Scripts\python.exe' `
  software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --run-randomized-demonstration-episode `
  --randomized-campaign "$campaignRoot\campaign.json" `
  --episode-id $episodeId `
  --replay-plan "$sourceRoot\$target\native_mechanics_plan.json" `
  --source-native-receipt "$sourceRoot\$target\native_mechanics_receipt.json" `
  --drive-profile <governed-drive-profile.json> `
  --robot-usd <governed-robot.usd> `
  --trajectory-output "$episodeRoot\trajectory.jsonl" `
  --output "$episodeRoot\episode_receipt.json" `
  --status-output "$episodeRoot\status.json"
```

After all workers have completed, reproduce the fail-closed aggregate with:

```powershell
$campaignRoot = 'C:\IsaacSim\artifacts\issue190\arm218-randomized-demonstration-smoke-001'
python software\integrations\isaac_sim\representative_key_mechanics.py `
  --layout software\config\nominal_target_profiles.json `
  --aggregate-randomized-demonstration-campaign `
  --randomized-campaign "$campaignRoot\campaign.json" `
  --randomized-receipt-root $campaignRoot `
  --output "$campaignRoot\result_campaign.json" `
  --status-output "$campaignRoot\result_status.json"
```

The retained smoke result is
`COMPLETE_RANDOMIZED_DEMONSTRATION_SMOKE`: all `24` attempted episodes completed
exactly once and retained `1,416` content-addressed native samples apiece. The
aggregate reports `18` passes and `6` completed `MECHANICS_REJECTION` failures.
The split results are `9` pass / `3` fail for train, `6` / `2` for validation,
and `3` / `1` for test. Four failures occur in the declared high-stiffness
region and two in the mid-stiffness region. No episode failed from execution,
fixed-root, tracking, IK, or collision infrastructure. The canonical result
SHA-256 is
`6966084caa88cd5397dc851c4892d4ffa4acc7b5923192756e01d0fdf9bc3e3f`.

The first retained failure, `episode-edda9b249c011866102b`, illustrates the
denominator rule. It completed with a passing fixed-root invariant and joint
tracking inside its `0.05 rad` limit, so its
`FAIL / MECHANICS_REJECTION` receipt and all samples remain part of the result
rather than being discarded or retried. Its episode-receipt SHA-256 is
`0e218e40400c159259acb38da81998de90ff76edbf07e1eb7f307671ef9751fa` and
trajectory SHA-256 is
`c461d4cb4a736a9b4a30917415e3b2a04a81708cc6590e1cfcd42b20ae5f673d`.
This closes only the small LM3 simulation smoke gate. It is not statistical
coverage, a trained policy, physical qualification, or hardware authority.

### LM4 state-policy trajectory capture

The completed ARM-218 artifacts remain valid LM3 mechanics evidence, but their
trajectory rows do not contain per-step joint observations and must not be used
as behavior-cloning input. ARM-219 adds the versioned
`tactevra.isaac_lm4_state_policy_trajectory_row.v1` capture contract to fresh
randomized native replays. Each physics-step row binds:

- observed six-joint positions and velocities;
- the commanded six-joint position target;
- governed joint order through the episode receipt;
- target, phase, action, sequence, and simulation time; and
- key center, tool-tip center, and tip/key separation.

This is a recorder prerequisite, not a trained policy. A fresh 24-episode
simulation-only corpus has now been regenerated under this schema: all `24`
episodes and `33,984` rows passed content, shape, ordering, receipt, and digest
validation. The result retains `18` passing episodes and `6` mechanics
rejections without retry or denominator filtering.

The LM4 dataset compiler emits
`tactevra.isaac_lm4_state_policy_dataset_manifest.v1`. It assigns only passing
`train` rows to `TRAINING`, passing `validation`/`test` rows to `EVALUATION`, and
all failed episodes to `REJECTION_EVIDENCE`. It fits its 23-feature
normalization exclusively on passing training rows, verifies the six-joint
order across every receipt, and binds every trajectory by SHA-256. The retained
smoke manifest contains `12,744` training rows and has dataset SHA-256
`a5870894ce6e734542ea2cef5bef079b8ee73a147c3a1d528eff5e0e521479f1`.
Existing ARM-218 evidence is not silently relabelled or inferred, and neither
the recorder nor compiler adds a hardware interface or physical authority.

The first bounded baseline uses deterministic closed-form ridge regression
with `ridge_lambda=0.001` and no stochastic operations. It encodes the 23
normalized numeric inputs plus fixed target, phase, and action-index context,
then predicts the six-joint position proposal. Repeated fits over the retained
corpus produce model SHA-256
`e281114e62fdaca603dbabbb8b0ca00891648bf6929c141fa100fe3919b5d45c`.
Training aggregate MAE/RMSE are `0.0002683071`/`0.0005495514 rad`; held-out
aggregate MAE/RMSE are `0.0143845465`/`0.0242957649 rad`. The held-out gap is
reported rather than concealed. The artifact is only
`READY_FOR_ZERO_AUTHORITY_STATE_POLICY_PROPOSAL_REPLAY`: collision, mechanics,
tracking, and fixed-root replay gates have not yet run.

The next boundary is retained as the zero-authority proposal-replay campaign
with SHA-256
`40399470984761de4677f3b65a398a648178bda14c83bf180c9840b4f4e182dd`.
It binds all `9` held-out episodes and `12,744` proposal rows to their source
dataset, model, receipts, and trajectories. The maximum learned/planner joint
target deviation is `0.0753160568 rad`. Its continuity diagnostic finds `78`
adjacent-step transitions above the `0.05 rad` bounded-collision sampling
step, with a `0.1055636794 rad` maximum. The source planner contains the same
schedule-boundary pattern and reaches `0.10115 rad`; these transitions require
bounded interpolation rather than silent direct replay. Campaign status is
therefore `READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_QUALIFICATION`.
Native replay remains blocked until that fresh screen passes.

The follow-on
`tactevra.isaac_lm4_state_policy_collision_request_campaign.v1` compiler
materializes fresh target-bound collision inputs without relabelling the
planner's earlier collision outcome as learned-policy evidence. The retained
campaign contains `523` bounded arm configurations across all nine episodes,
with `90` inserted interpolation samples, `40` to `75` samples per episode,
and a maximum adjacent arm-joint step of `0.0499945099 rad`. Its SHA-256 is
`d4216d68e351335a6611cfc4ea0796cb8578c7dd01bc846e5a793f9ddee13d4d`.
Each request binds the dataset, model, proposal campaign and trajectory, plus
the matching ARM-216 collision geometry, placement, pair-policy, fixed-root,
station-route, and toolchain lineage. The campaign is only
`READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION`: all nine requests
still require fresh Isaac diagnostics, and no native or physical replay is
authorized.

The runtime admission layer then reloads the exact LM4 dataset, model,
proposal campaign, request campaign, all nine requests, and the four ARM-216
source environments. It checks content hashes, complete denominators, bounded
sample provenance, fixed-root plans, station predicates, native receipts, and
the hashes that the runtime must reload. The retained campaign SHA-256 is
`5fd06ed3000934c49ac9b77e4db9bf8187e60dd96b2f88282d4a3553a1a3e883`.
Status
`READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_RUNTIME_INPUT_REVALIDATION`
does not start Isaac: the virtual profile, robot import receipt, robot USD, and
toolchain still require immediate file-level revalidation. The record therefore
contains nine admissions and 523 samples, but zero Isaac/GPU starts and zero
fresh collision diagnostics.

The file-level revalidation stage is now retained at
`C:\IsaacSim\artifacts\issue190\arm219-state-policy-collision-runtime-revalidation-001`.
Its campaign SHA-256 is
`36f6f1221666f1cbbf092fb2858623d61d60de007c7c2b41e20bd8d278b462da`.
It distinguishes raw-byte hashes for the virtual profile and USD from the
canonical document hashes used by the import receipt and toolchain lock, and
also proves that the USD byte length/hash matches the receipt's sole external
file. All nine admissions and `523` samples are preserved. The result is
`READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTIC_START`, with
`runtime_files_revalidated=true`, while `isaac_started`, `gpu_started`, and
the diagnostic count remain false/zero. No collision or replay authority is
implied.

ARM-220 then materializes each learned-policy request into a fresh fixed-base
native diagnostic input without copying the representative collision result.
The retained manifest at
`C:\IsaacSim\artifacts\issue190\arm220-state-policy-native-collision-001\manifest.json`
has SHA-256
`cd4b7a70632d84b1e28bf6cdce23d3013659dfbebbce1913e351154bd6eee85b`.
Nine separate Isaac/PhysX runs evaluate the complete `523`-sample denominator.
The aggregated campaign SHA-256 is
`01acc93bd8da33dfab4ca5a69ae20cec7459ed9f0d97fe5e730830960576d7ca`.
All samples contain only the five accepted adjacent-link diagnostic reporting
exclusions, with zero physical-solid, planning-envelope, or unreviewed blocker
pairs. Fixed-base root invariants pass for every episode. The result remains
zero hardware authority and explicitly leaves installed qualification,
continuous collision proof, contact replay, and physical replay blocked.

ARM-221 independently reviews that complete native result before mechanics
planning. The retained review is
`C:\IsaacSim\artifacts\issue190\arm221-state-policy-native-collision-review-001\review.json`
with SHA-256
`44d76e941161d94280e04abe2956fe45b17d3a0d78bab4f6c0d1cb0ffa99ccab`.
It reloads the ARM-220 manifest, campaign, and all nine receipts; verifies the
`9`-episode / `523`-sample denominator; checks every per-sample disposition; and
rechecks each fixed-base root invariant. The result admits only compilation of
zero-authority LM4 mechanics replay plans. Isaac/GPU start, mechanics execution,
installed clearance, continuous clearance, native replay, and physical motion
remain false or blocked.

Reproduce the non-starting review with:

```powershell
python software/integrations/isaac_sim/representative_key_mechanics.py `
  --layout software/config/ghost_keyboard_v1.json `
  --output C:/IsaacSim/artifacts/issue190/arm221-state-policy-native-collision-review-001/review.json `
  --status-output C:/IsaacSim/artifacts/issue190/arm221-state-policy-native-collision-review-001/status.json `
  --review-state-policy-native-collision-campaign `
  --state-policy-native-campaign C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001/campaign.json `
  --state-policy-native-manifest C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001/manifest.json `
  --state-policy-native-output-dir C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001
```

Recreate the non-starting native input manifest with:

```powershell
python software/integrations/isaac_sim/representative_key_mechanics.py `
  --layout software/config/ghost_keyboard_v1.json `
  --output C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001/manifest.json `
  --status-output C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001/status.json `
  --materialize-state-policy-native-collision-inputs `
  --state-policy-runtime-revalidation-campaign C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-runtime-revalidation-001/campaign.json `
  --state-policy-runtime-revalidation-root C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-runtime-revalidation-001 `
  --collision-request-output-dir C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-request-001 `
  --representative-native-admission-root C:/IsaacSim/artifacts/issue190/arm216-representative-native-admission-001 `
  --state-policy-native-output-dir C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001
```

After all nine entry-specific native receipts have been produced by the
existing `--run-collision-diagnostic` command, verify the exact denominator
with:

```powershell
python software/integrations/isaac_sim/representative_key_mechanics.py `
  --layout software/config/ghost_keyboard_v1.json `
  --output C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001/campaign.json `
  --status-output C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001/campaign_status.json `
  --aggregate-state-policy-native-collision-campaign `
  --state-policy-native-manifest C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001/manifest.json `
  --state-policy-native-output-dir C:/IsaacSim/artifacts/issue190/arm220-state-policy-native-collision-001
```

Reproduce the preceding ARM-219 non-starting boundary with:

```powershell
python software/integrations/isaac_sim/representative_key_mechanics.py `
  --layout software/config/ghost_keyboard_v1.json `
  --output C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-runtime-revalidation-001/campaign.json `
  --status-output C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-runtime-revalidation-001/status.json `
  --revalidate-state-policy-collision-runtime-inputs `
  --state-policy-runtime-admission-campaign C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-runtime-admission-001/campaign.json `
  --collision-runtime-admission-root C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-runtime-admission-001 `
  --collision-runtime-revalidation-output-dir C:/IsaacSim/artifacts/issue190/arm219-state-policy-collision-runtime-revalidation-001 `
  --virtual-profile software/config/virtual_commissioning_profile.json `
  --robot-usd C:/IsaacSim/artifacts/issue190/wp1-import-003/roarm_m3_kinematic_40dbd84/roarm_m3_kinematic_40dbd84.usda `
  --import-receipt C:/IsaacSim/evidence/urdf_import_003.json `
  --toolchain-lock software/config/isaac_sim_toolchain_lock.json
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
