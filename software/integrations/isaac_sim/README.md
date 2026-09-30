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
