# Isaac Sim integration boundary

- **Document status:** Active implementation reference
- **Audience:** Runtime and simulation contributors
- **Authority:** Software-test guidance only; this integration grants no
  hardware, motion, contact, or release authority.

This directory documents the optional NVIDIA Isaac Sim runner. Executable,
packaged contracts live in
`software/src/rocell/integrations/isaac_sim/`; versioned JSON schemas live in
`software/schemas/`.

The current WP0 implementation provides:

- canonical v1 request and receipt envelopes;
- exact-field, unit, frame, joint-order, timing, digest, and zero-authority
  validation;
- a hardware-free fake adapter for lifecycle and evidence tests;
- a fail-closed external toolchain lock; and
- compact valid and invalid fixtures.

It does **not** import Isaac Sim, load a USD scene, use a GPU, run physics, or
produce clearance/contact evidence. A fake-adapter `PASS` has evidence class
`CONTRACT_TEST_ONLY` and expressly establishes only contract behavior.

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

The compatibility launch passes, but the repository toolchain lock remains
`UNSELECTED`. The RTX 3090 remains outside NVIDIA's documented 6.1.0 minimum
GPU set. The launch also reported PCIe device 0 at width x4 versus its x16
maximum, no CUDA peer access between the GPUs, a stale localhost Omniverse
proxy setting, and an OpenUSD asset-converter build warning. WP1 must resolve
or explicitly isolate the OpenUSD importer warning and prove import/FK parity
before a runner-selection change can be reviewed.

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

## Source-bound joint-schedule replay

[`joint_schedule_replay_bundle.py`](joint_schedule_replay_bundle.py) converts a
full arm-lane shadow-pipeline report into a bounded replay bundle. It requires
accepted IK at every sample, a dynamics-screened joint schedule, exact semantic
agreement between the Cartesian and joint samples, preserved contact order and
repetitions, and zero controller or physical authority. The retained
[`bundle`](evidence/representative_joint_schedule_bundle_5072_20260929.json)
contains 133 samples for `H, H, 1, PERIOD` from arm commit
`5072c163152848bd8d78fa3fbc024e32177ac98d`.

[`joint_schedule_isaac_replay_probe.py`](joint_schedule_isaac_replay_probe.py)
teleports that exact schedule through the governed Isaac articulation and
independently recomputes the 120 mm tool-tip pose at every sample. The retained
[`replay receipt`](evidence/joint_schedule_isaac_replay_5072_20260929.json)
passes all 133 samples with maximum full-route tool-tip disagreement
`0.07684842940066568` mm and maximum joint readback disagreement
`5.923525581152944e-08` rad. Contact endpoints preserve `H, H, 1, PERIOD`;
their individual tool-tip disagreements are all below `0.00019` mm.

This result uses the repository's `UNMEASURED_SENSITIVITY_OVERLAY`, a synthetic
park-state seed, and a representative synthetic batch. It takes zero physics
steps. It does not execute collision geometry, dynamics, controller tracking,
key travel, contact force, camera localization, or physical qualification.

The follow-up v2
[`actual-emitter bundle`](evidence/actual_emitter_joint_schedule_bundle_9e5c878_20260929.json)
binds the retained batch bytes to the actual shared emitter on arm commit
`9e5c878852da6a6e8509598bce9ce43f218efc70`. The bundle marks its observations
as synthetic and denies deployment qualification. Its independent
[`Isaac receipt`](evidence/actual_emitter_joint_schedule_isaac_replay_9e5c878_20260929.json)
preserves the same 133 samples, contact order, and error metrics as the earlier
fixture-origin replay. This isolates producer substitution: routing the same
observations through the actual emitter does not change the downstream motion.

Reproduce the retained bundle and Isaac replay from the repository root:

```powershell
python software\integrations\isaac_sim\joint_schedule_replay_bundle.py `
  --arm-report C:\IsaacSim\evidence\representative_schedule_promoted_5072.json `
  --arm-commit 5072c163152848bd8d78fa3fbc024e32177ac98d `
  --output C:\IsaacSim\evidence\representative_joint_schedule_bundle_5072.json

python software\integrations\isaac_sim\joint_schedule_replay_bundle.py `
  --arm-report C:\IsaacSim\evidence\actual_emitter_representative_schedule_9e5c878.json `
  --arm-commit 9e5c878852da6a6e8509598bce9ce43f218efc70 `
  --require-actual-emitter `
  --output C:\IsaacSim\evidence\actual_emitter_joint_schedule_bundle_9e5c878.json

$env:OMNI_KIT_ACCEPT_EULA = 'YES'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\joint_schedule_isaac_replay_probe.py `
  --usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda `
  --import-receipt software\integrations\isaac_sim\evidence\roarm_m3_urdf_import_20260929.json `
  --bundle C:\IsaacSim\evidence\representative_joint_schedule_bundle_5072.json `
  --virtual-profile software\config\virtual_commissioning_profile.json `
  --output C:\IsaacSim\evidence\joint_schedule_isaac_replay_5072.json `
  --status-output C:\IsaacSim\evidence\joint_schedule_isaac_replay_5072.status.json
```

Add `--retain-all-samples` to emit the opt-in v2 receipt used by the MW2FI
four-backend differential. It preserves every ordered Isaac tool-tip row while
leaving the default v1 output and retained evidence unchanged. Compare it with
the exact MW2F CUDA receipt using
`software/integrations/mujoco_warp/four_backend_fk_admission.py`. This remains
teleport-only kinematic evidence and takes zero physics steps.

## Official STEP inspection

[`step_inspection_probe.py`](step_inspection_probe.py) verifies the pinned
official Waveshare assembly archive and its sole STEP member byte for byte,
converts it with the installed Isaac HOOPS backend, and retains a compact
[`inspection receipt`](evidence/roarm_m3_step_inspection_20260929.json). The
generated 26.9 MB USD remains external because the upstream redistribution
scope is unconfirmed. Two separate conversions produced the same USD SHA-256.

The inspection establishes millimetre units, Z-up orientation, the whole
assembly bound, 770 meshes, and exact bounds for four named upstream aluminum
components. Those components remain collision *seeds*: the STEP assembly pose
is not bound to a governed URDF joint state, and the components have no
reviewed dynamic-link assignments or reduced shapes. The receipt therefore
denies dynamic-link assignment, collision geometry, and clearance replay.

[`step_pose_binding_probe.py`](step_pose_binding_probe.py) performs the next
bounded classification. It derives the CAD-to-URDF world translation from the
paired shoulder-servo envelopes and assembly floor, then tests the governed
zero, home, and ready states against six named CAD component envelopes. The
retained [`pose receipt`](evidence/roarm_m3_step_pose_binding_20260929.json)
selects the `home` hypothesis: all six witnesses lie within 2.216 mm, while
the nearest alternative misses by 133.238 mm. This supports the assembly-pose
hypothesis only. Axis-exact correspondence, CAD-product membership per moving
link, and reduced collision shapes remain unreviewed and blocked.

[`step_link_membership_probe.py`](step_link_membership_probe.py) then covers
every direct component of the fixed-pose STEP assembly and ranks two candidate
governed links from each component envelope's distance to the home-pose link
skeleton. The retained
[`candidate receipt`](evidence/roarm_m3_step_link_membership_candidates_20260929.json)
covers all 770 meshes through 162 direct component instances. It finds 114
ambiguous instances and 19 groups whose bounds cross a governed joint origin.
All reviewed assignments remain null: the fixed STEP has no reviewed joint or
mate graph, and one static pose cannot separate coincident rigid groups.

[`upstream_link_mesh_probe.py`](upstream_link_mesh_probe.py) follows the
independent official ROS description at its pinned Git commit. The Xacro binds
seven link-specific STL files identically as visual and collision geometry.
After the governed home-pose transforms, their union envelope matches the
independently converted STEP assembly within 1.911 mm. This supports the
upstream per-link grouping, while the retained
[`mesh receipt`](evidence/roarm_m3_upstream_link_meshes_20260929.json) still
denies collision use: the raw visual meshes contain 38,344 triangles, `link1`
and `link5` are not watertight, an extra left-gripper mesh is unreferenced, and
no convex reduction or self-collision policy has been reviewed.

[`link_mesh_reduction_probe.py`](link_mesh_reduction_probe.py) derives a
deterministic conservative candidate set from those pinned meshes. It emits
one link-local identity-oriented box per processed connected component, except
that `link5` exceeds the runtime contract's 64-primitives-per-body limit and
therefore uses one declared whole-link envelope. The retained
[`reduction receipt`](evidence/roarm_m3_link_mesh_reduction_20260929.json)
contains 14 boxes across seven links and records zero source-vertex overflow.
These remain uninstalled candidates: the largest measured box/source volume
ratio among watertight components is 21.141, two candidate sources are not
watertight, and neither false-positive collision behavior nor self-collision
pair policy has been qualified.

[`collision_differential_probe.py`](collision_differential_probe.py) compares
those candidates with the pinned raw meshes through an identity-bound
python-fcl wheel. Across all 21 unordered link pairs at the governed zero,
home, and ready poses, the retained
[`differential receipt`](evidence/roarm_m3_collision_differential_20260929.json)
records 48 free-space agreements, three collision agreements, 12 box false
positives, and zero box false negatives. Every observed false positive is an
adjacent-link pair. This is a bounded three-pose diagnostic; it does not select
pair exclusions, cover continuous joint space, or admit collision queries.

[`collision_joint_space_probe.py`](collision_joint_space_probe.py) expands the
same differential to 49 deterministic poses derived from the governed URDF
limits: three governed anchors, whole-limit and midpoint anchors, single-joint
limits, and 32 six-dimensional Halton samples. The compact retained
[`joint-space summary`](evidence/roarm_m3_collision_joint_space_20260929.json)
binds an external detailed receipt containing all 1,029 pair-pose cases. It
records zero false negatives, 191 adjacent false positives, and one
nonadjacent `link2`/`gripper_link` false positive at Halton sample 19. Finite
sampling remains diagnostic and no pair exclusion is selected.

[`targeted_obb_refinement_probe.py`](targeted_obb_refinement_probe.py) isolates
oriented-box alternatives for the `link2` and gripper candidates implicated by
the nonadjacent witness. Exact 1,029-case replays apply each serialized box
rotation. The
retained [`link2-only candidate`](evidence/roarm_m3_targeted_obb_link2_20260929.json)
reduces one component's volume and preserves zero false negatives, but all
three variants retain the baseline's 192 false positives, as recorded by its
[`replay summary`](evidence/roarm_m3_collision_joint_space_link2_20260929.json).
No OBB variant demonstrates collision-classification improvement, so none is
installed or preferred for runtime use.

[`triangle_partition_refinement_probe.py`](triangle_partition_refinement_probe.py)
targets the exact baseline witness: `link2` component 0 against the sole
gripper component at Halton sample 19. It recursively assigns every source
triangle to one of 16 groups by centroid and bounds every group's complete
triangle vertices. The retained
[`partition candidate`](evidence/roarm_m3_triangle_partition_link2_20260929.json)
contains all 9,216 source triangles exactly once with zero serialized vertex
overflow and keeps `link2` at 17 primitives, below the 64-primitive body
limit. Its exact 1,029-case
[`replay summary`](evidence/roarm_m3_collision_joint_space_triangle_partition_20260929.json)
removes the only nonadjacent false positive, reduces total false positives
from 192 to 165, preserves all 57 collision agreements, and introduces zero
false negatives. Requests for 2, 4, and 8 groups do not improve the baseline;
32 groups do not improve on 16. This finite diagnostic remains uninstalled
and does not admit collision or clearance queries.

[`self_collision_policy_review_probe.py`](self_collision_policy_review_probe.py)
binds the selected replay to the pinned upstream RoArm-M3 SRDF and the governed
URDF topology. The retained
[`policy review`](evidence/roarm_m3_self_collision_policy_review_20260929.json)
shows that the SRDF's six `Adjacent` exclusions exactly match all six governed
direct-joint pairs. Every one of the remaining 165 false-positive cases belongs
to four of those explicitly supported pairs. An adjacent-only counterfactual
removes 294 pair-pose cases and leaves 735 nonadjacent cases with three
collision agreements, 732 free agreements, and no false classifications. The
review does not install exclusions. The six separate SRDF `Never` pairs are
reviewed below, and the resulting local document remains an inert candidate
with zero effective exclusions.

[`srdf_never_pair_review_probe.py`](srdf_never_pair_review_probe.py) reviews
the SRDF's six separate `Never` pairs without promoting them into a local
policy. The retained
[`Never-pair review`](evidence/roarm_m3_srdf_never_pair_review_20260929.json)
records raw/candidate free-space agreement for all 294 tested pair-pose cases,
with positive recorded minima for both representations. It also preserves the
three nonexcluded nonadjacent pairs that each collide once in the finite corpus.
This supports the upstream labels only within the 49 sampled poses; it is not
a continuous-workspace proof and does not make the exclusions installable.

[`exclusion_policy_candidate_probe.py`](exclusion_policy_candidate_probe.py)
turns those reviews into the strict shared candidate boundary described by
[`collision_exclusion_policy_candidate_v1.schema.json`](../../ai/schemas/collision_exclusion_policy_candidate_v1.schema.json).
The retained
[`candidate document`](evidence/roarm_m3_collision_exclusion_policy_candidate_20260929.json)
binds the exact base collision contract, governed robot model, selected
geometry, replay, upstream SRDF, adjacent review, and `Never` review. It lists
all twelve SRDF pairs as proposals while requiring an empty
`effective_exclusions` array, defaulting every pair to `CHECK_COLLISION`, and
setting collision, clearance, controller, execution-permit, transport, and
physical authority to false. The strict loader has no method that applies a
proposal to a collision contract.

The retained held-out stress replay and policy assessment use 256 Halton poses
at indices 1001 through 1256, disjoint from the original 1-through-32 Halton
corpus. All six proposed `Never` pairs remain free and the selected geometry
again records zero false negatives. The broader corpus also restores 13 false
positives across six nonproposed pairs. That result is retained as a blocker:
the candidate remains uninstalled and cannot admit collision queries.

Reproduce it on the designated runner from the repository root:

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\step_inspection_probe.py `
  --archive C:\IsaacSim\sources\roarm-m3-step-260310\RoArm-M3_STEP_260310.zip `
  --step C:\IsaacSim\sources\roarm-m3-step-260310\extracted\RoArm-M3_STEP\RoArm-M3.step `
  --output-dir C:\IsaacSim\artifacts\issue190\wp2-cad-004 `
  --receipt C:\IsaacSim\evidence\step_inspection_004.json `
  --status-output C:\IsaacSim\evidence\step_inspection_004.status.json
```

Reproduce the pose classification with the generated USD still external:

```powershell
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\step_pose_binding_probe.py `
  --workspace . `
  --cad-usd C:\IsaacSim\artifacts\issue190\wp2-cad-004\roarm_m3_official.usda `
  --step-receipt software\integrations\isaac_sim\evidence\roarm_m3_step_inspection_20260929.json `
  --output C:\IsaacSim\evidence\step_pose_binding_001.json `
  --status-output C:\IsaacSim\evidence\step_pose_binding_001.status.json
```

Reproduce the complete candidate inventory without promoting any assignment:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\step_link_membership_probe.py `
  --workspace . `
  --cad-usd C:\IsaacSim\artifacts\issue190\wp2-cad-004\roarm_m3_official.usda `
  --pose-receipt software\integrations\isaac_sim\evidence\roarm_m3_step_pose_binding_20260929.json `
  --output C:\IsaacSim\evidence\step_link_membership_001.json `
  --status-output C:\IsaacSim\evidence\step_link_membership_001.status.json
```

Reproduce the pinned upstream link-mesh inspection:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\upstream_link_mesh_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --step-receipt software\integrations\isaac_sim\evidence\roarm_m3_step_inspection_20260929.json `
  --pose-receipt software\integrations\isaac_sim\evidence\roarm_m3_step_pose_binding_20260929.json `
  --output C:\IsaacSim\evidence\upstream_link_meshes_001.json `
  --status-output C:\IsaacSim\evidence\upstream_link_meshes_001.status.json
```

Reproduce the conservative candidate reduction without installing a profile:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\link_mesh_reduction_probe.py `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_meshes_20260929.json `
  --output C:\IsaacSim\evidence\link_mesh_reduction_003.json `
  --status-output C:\IsaacSim\evidence\link_mesh_reduction_003.status.json
```

Reproduce the raw-mesh versus candidate-box differential:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\collision_differential_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_meshes_20260929.json `
  --reduction-receipt software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20260929.json `
  --fcl-wheel C:\IsaacSim\sources\python-fcl-0.7.0.11\python_fcl-0.7.0.11-cp312-cp312-win_amd64.whl `
  --output C:\IsaacSim\evidence\collision_differential_002.json `
  --status-output C:\IsaacSim\evidence\collision_differential_002.status.json
```

Reproduce the governed-limit joint-space expansion while keeping its detailed
case ledger external:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\collision_joint_space_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_meshes_20260929.json `
  --reduction-receipt software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20260929.json `
  --fcl-wheel C:\IsaacSim\sources\python-fcl-0.7.0.11\python_fcl-0.7.0.11-cp312-cp312-win_amd64.whl `
  --output C:\IsaacSim\evidence\collision_joint_space_003.detailed.json `
  --summary-output C:\IsaacSim\evidence\collision_joint_space_003.summary.json `
  --status-output C:\IsaacSim\evidence\collision_joint_space_003.status.json
```

Reproduce the retained diagnostic `link2`-only OBB refinement, then pass its
exact receipt hash to the same joint-space probe:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\targeted_obb_refinement_probe.py `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_meshes_20260929.json `
  --base-reduction software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20260929.json `
  --target-links link2 `
  --output C:\IsaacSim\evidence\targeted_obb_refinement_002_link2.json `
  --status-output C:\IsaacSim\evidence\targeted_obb_refinement_002_link2.status.json
```

Reproduce the bounded 16-group triangle partition candidate. Pass the emitted
`receipt_sha256` to `collision_joint_space_probe.py` with
`--expected-reduction-sha256` for its exact replay:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\triangle_partition_refinement_probe.py `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_meshes_20260929.json `
  --base-reduction software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20260929.json `
  --band-count 16 `
  --strategy recursive-longest-centroid-axis `
  --output C:\IsaacSim\evidence\triangle_partition_final_16.candidate.json `
  --status-output C:\IsaacSim\evidence\triangle_partition_final_16.candidate.status.json
```

Reproduce the pinned SRDF policy review against that selected replay:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\self_collision_policy_review_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --replay-summary software\integrations\isaac_sim\evidence\roarm_m3_collision_joint_space_triangle_partition_20260929.json `
  --output C:\IsaacSim\evidence\self_collision_policy_review_001.json `
  --status-output C:\IsaacSim\evidence\self_collision_policy_review_001.status.json
```

Reproduce the bounded review of the six SRDF `Never` pairs:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\srdf_never_pair_review_probe.py `
  --policy-review software\integrations\isaac_sim\evidence\roarm_m3_self_collision_policy_review_20260929.json `
  --replay-summary software\integrations\isaac_sim\evidence\roarm_m3_collision_joint_space_triangle_partition_20260929.json `
  --output C:\IsaacSim\evidence\srdf_never_pair_review_001.json `
  --status-output C:\IsaacSim\evidence\srdf_never_pair_review_001.status.json
```

Reproduce the inert, hash-bound exclusion candidate:

```powershell
$env:PYTHONUTF8='1'
python software\integrations\isaac_sim\exclusion_policy_candidate_probe.py `
  --workspace . `
  --geometry-candidate software\integrations\isaac_sim\evidence\roarm_m3_triangle_partition_link2_20260929.json `
  --replay-summary software\integrations\isaac_sim\evidence\roarm_m3_collision_joint_space_triangle_partition_20260929.json `
  --policy-review software\integrations\isaac_sim\evidence\roarm_m3_self_collision_policy_review_20260929.json `
  --never-review software\integrations\isaac_sim\evidence\roarm_m3_srdf_never_pair_review_20260929.json `
  --output C:\IsaacSim\evidence\collision_exclusion_policy_candidate_001.json `
  --status-output C:\IsaacSim\evidence\collision_exclusion_policy_candidate_001.status.json
```

Reproduce the held-out stress replay and inert candidate assessment:

```powershell
$env:PYTHONUTF8='1'
C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\collision_joint_space_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_meshes_20260929.json `
  --reduction-receipt software\integrations\isaac_sim\evidence\roarm_m3_triangle_partition_link2_20260929.json `
  --expected-reduction-sha256 0568f7ba269cf190ca4b9d6bc41ac17c90c72c3489fad433bb064ca2239e5fc6 `
  --fcl-wheel C:\IsaacSim\sources\python-fcl-0.7.0.11\python_fcl-0.7.0.11-cp312-cp312-win_amd64.whl `
  --halton-start 1001 --halton-count 256 --halton-only `
  --output C:\IsaacSim\evidence\collision_policy_stress_001.detailed.json `
  --summary-output C:\IsaacSim\evidence\collision_policy_stress_001.summary.json `
  --status-output C:\IsaacSim\evidence\collision_policy_stress_001.replay.status.json

python software\integrations\isaac_sim\collision_policy_stress_probe.py `
  --workspace . `
  --candidate software\integrations\isaac_sim\evidence\roarm_m3_collision_exclusion_policy_candidate_20260929.json `
  --stress-replay C:\IsaacSim\evidence\collision_policy_stress_001.summary.json `
  --output C:\IsaacSim\evidence\collision_policy_stress_002.assessment.json `
  --status-output C:\IsaacSim\evidence\collision_policy_stress_002.assessment.status.json
```

## Generate the fixed-fixture practice-image corpus

The synthetic practice corpus exercises the existing plan-blind virtual
arm-camera JPEG path at two achieved arm poses. It projects all 46 keyboard and
29 phone target regions into each view, renders simplified target surfaces, and
applies eight deterministic lighting, blur, glare, and foreground-obstruction
cases. Every image is accompanied by metric board coordinates, pixel polygons,
the exact pixel transformation, source hashes, and zero-authority declarations.

The committed corpus is deliberately synthetic. Its unmeasured camera model,
pixel-domain lighting, simplified device appearance, and image-space arm proxy
do not qualify the physical camera, placement, localization error, or collision
geometry.

From the repository root:

```powershell
New-Item -ItemType Directory -Force software/runs | Out-Null
$env:PYTHONPATH = (Resolve-Path 'software/src').Path
python software/integrations/isaac_sim/fixed_fixture_practice_corpus.py `
  --output-dir C:\IsaacSim\artifacts\issue190\fixed-fixture-practice-v1
```

The retained reproducible output is under
`software/integrations/isaac_sim/evidence/fixed_fixture_practice_v1/`.

### Fixed-overview robot masks and depth

The next corpus keeps the synthetic overview camera and board transform fixed
while changing only the robot joint state. URDF forward kinematics projects a
declared capsule proxy for each link into the camera. Each of three poses emits
a semantic link-label PNG, a uint16 robot-depth PNG in millimetres, and one RGB
atlas containing five lighting variants with exact crop rectangles. The manifest records per-target safe-region overlap with the
robot mask so an AI pipeline can learn or test abstention under obstruction.

```powershell
New-Item -ItemType Directory -Force software/runs | Out-Null
$env:PYTHONPATH = (Resolve-Path 'software/src').Path
python software/integrations/isaac_sim/fixed_overview_segmentation_corpus.py `
  --output-dir C:\IsaacSim\artifacts\issue190\fixed-overview-segmentation-v1
```

The retained output is under
`software/integrations/isaac_sim/evidence/fixed_overview_segmentation_v1/`.
The capsules are pose-bound kinematic proxies. They are not robot CAD, a
triangle-level depth render, or installed collision evidence.

### Compare capsules with official visual meshes

The installed Isaac runner can render the seven official upstream visual
meshes at 21 predeclared fixed-camera poses. The original three poses retain
their capsule comparison. Eighteen additional poses are selected by sequence
from the retained zero-authority actual-emitter schedule. All nine previously
consumed endpoint poses form training geometry, six unused outbound/return
transit poses form development geometry, and six unused inter-key transit poses
form untouched evaluation geometry. The probe pins the
upstream Git commit, schedule, and mesh hashes, bakes the governed URDF forward
kinematics into the USD scene, and emits RGB, binary robot-mask, and uint16
metric-depth atlases. It performs no physics steps and has no hardware or
physical authority.

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
$env:PYTHONPATH = (Resolve-Path 'software/src').Path
C:\IsaacSim\env_6_1_0\Scripts\python.exe `
  software/integrations/isaac_sim/isaac_fixed_overview_mesh_render_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software/integrations/isaac_sim/evidence/roarm_m3_upstream_link_meshes_20260929.json `
  --capsule-manifest software/integrations/isaac_sim/evidence/fixed_overview_segmentation_v1/manifest.json `
  --schedule-bundle software/integrations/isaac_sim/evidence/actual_emitter_joint_schedule_bundle_9e5c878_20260929.json `
  --output-dir C:\IsaacSim\artifacts\issue190\fixed-overview-official-mesh `
  --receipt C:\IsaacSim\evidence\fixed_overview_official_mesh.json `
  --status-output C:\IsaacSim\evidence\fixed_overview_official_mesh.status.json
```

The retained compact output is under
`software/integrations/isaac_sim/evidence/fixed_overview_official_mesh_v1/`.
These high-detail meshes are perception geometry. The comparison does not
qualify them as collision geometry or establish physical clearance.

## Verify WP0

From `software/`:

```powershell
python -m pytest tests/unit/test_isaac_sim_contracts.py -q
```

From the repository root:

```powershell
python scripts/ci/check_docs.py
```

## Select the external runner

The committed
[`isaac_sim_toolchain_lock.json`](../../config/isaac_sim_toolchain_lock.json)
is deliberately `UNSELECTED`. Do not replace its null fields with guessed
values. On the designated compute runner:

1. install or pull one exact Isaac Sim release using an NVIDIA-supported path;
2. retain the exact installer/container identity and calculate its SHA-256;
3. export the enabled extension set and settings profile as canonical files;
4. hash both files;
5. record the runner platform and deterministic launch method;
6. review the exact selected version's license terms for the intended internal
   integration; and
7. change `selection_status` to `SELECTED` only in the same reviewed change
   that supplies all required identities.

`IsaacSimToolchainLock.load(...)` rejects the repository placeholder, partial
selections, unreviewed licensing, invalid digests, added fields, or any attempt
to add hardware authority.

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
