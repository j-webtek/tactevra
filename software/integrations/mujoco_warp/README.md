# MuJoCo Warp external integration

This optional integration is a zero-authority secondary simulation oracle. It
does not replace RoCell planning, Isaac visual evidence, physical qualification,
or the `ModelMotionBatch` boundary.

## MW0 rebuild

Use Python 3.12 and keep all packages, wheels, kernels, and run evidence outside
the repository:

```powershell
py -3.12 -m venv C:\MuJoCoWarp\env_3_13_0
C:\MuJoCoWarp\env_3_13_0\Scripts\python.exe -m pip download --dest C:\MuJoCoWarp\wheels\3.13.0 mujoco-warp==3.13.0
C:\MuJoCoWarp\env_3_13_0\Scripts\python.exe -m pip install --no-index --find-links C:\MuJoCoWarp\wheels\3.13.0 mujoco-warp==3.13.0
```

Verify every wheel against
[`mujoco_warp_toolchain_lock.json`](../../config/mujoco_warp_toolchain_lock.json),
then run the pre-import host gate:

```powershell
C:\MuJoCoWarp\env_3_13_0\Scripts\python.exe software\integrations\mujoco_warp\host_probe.py `
  --lock software\config\mujoco_warp_toolchain_lock.json `
  --output C:\MuJoCoWarp\evidence\mw0\host_probe.json
```

The probe uses package metadata and `nvidia-smi`; it deliberately does not
import MuJoCo, MuJoCo Warp, or Warp. Any mismatch returns exit code 2 before a
model load can be attempted. The selected candidate resolves MuJoCo Warp 3.13.0
with MuJoCo 3.14.0, as allowed by the package's `mujoco>=3.12.0` dependency.
Later parity gates must still validate that exact pair.

## Persistent research campaigns

`persistent_campaign_probe.py` creates a compact, deterministic scenario
manifest and executes its two device shards either sequentially or concurrently.
Each worker loads the kinematic research model once and reuses one 16,384-world
allocation across every shard. Receipts bind every seed and initial/final state
hash, making a failed or interesting population replayable without storing a
large state tensor in Git. This remains an offline research facility and grants
no contact, rendering, planner, controller, transport, or execution authority.

`resumable_queue_probe.py` keeps one atomically promoted receipt per shard. It
validates existing receipts before reuse, quarantines invalid bytes, executes
only missing work, and admits a campaign only with the exact manifest allowlist.
This permits long independent GPU research queues to resume after interruption
without treating partial or altered output as completed evidence.

`scenario_profile_probe.py` compiles a strict six-joint uncertainty profile
into deterministic resumable shards. The profile and every generated seed are
bound to an external source artifact carrying the exact ranges. Synthetic or
assumed sources remain exploratory; qualifying candidates require matching
physical-measurement content with a positive sample count. The compiler does
not infer missing ranges or physical properties.

## Removal

Delete `C:\MuJoCoWarp\env_3_13_0`, `C:\MuJoCoWarp\wheels\3.13.0`, and the
external Warp cache. No project environment or repository file is installed by
the external setup. Preserve `C:\MuJoCoWarp\evidence\mw0` according to the
project evidence-retention policy before removal.
