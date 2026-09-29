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
