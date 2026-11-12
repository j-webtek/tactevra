# ARM-298 route-physics launch binding

ARM-298 now has an inert, independently accepted reproducible launch binding.
This checkpoint closes the gap between the reviewed single-use claimant and a
future executable launcher without starting Isaac or consuming an attempt.

The binding pins:

- merged claimant commit `84bb099e13b19c389095552ad0b267494cdb38c1`;
- qualified interpreter
  `C:\IsaacSim\env_6_1_0\Scripts\python.exe`, file SHA-256
  `d55736b9f3d6b4ca7985b82db8ce11edfa09994cf93ce31c6b506543b74f32eb`;
- the exact ARM-298 claimant and independent review bytes and canonical hashes;
- all 13 qualified model, solver, context, manifest, runtime, worker, and
  backend source hashes;
- the absent attempt, EULA-receipt, and memory-receipt paths;
- the exact future ARM-298 authorization statement;
- EULA-then-memory ordering and retention of both receipts before claim;
- one claimant delegation, terminal status before shutdown, and no retry; and
- zero trajectory, hardware, or physical authority.

## Retained evidence

| Artifact | File SHA-256 | Canonical document SHA-256 |
| --- | --- | --- |
| `arm298-route-physics-launch-binding-001/binding.json` | `a91365ba0e877732822bd3e99fb05bbebb78bad85272f9b30460e2f59aa62424` | `dceeb71e5c17def71a2744a91610961e3d676450c31544315402675c144567c5` |
| `arm298-route-physics-launch-binding-review-001/review.json` | `4af40b4d2ca0b76ef2ed593536a814f1e0b83148c7407c0f6f504fea4a81cbc0` | `69e7f3f2368740462add44f3d0359cad729e2848379fa005d38858815a87445d` |

Both artifacts live under `C:\IsaacSim\artifacts\issue190`. The independent
review reopens every bound byte and statically rejects simulator, motion, and
transport execution in the builder.

## Reproduction

From the repository root in PowerShell:

```powershell
$root = 'C:/IsaacSim/artifacts/issue190'
$src = 'software/integrations/isaac_sim'
$commit = '84bb099e13b19c389095552ad0b267494cdb38c1'

python "$src/nominal_route_arm298_launch_binding.py" `
  --claimant "$root/arm298-route-physics-claimant-001/claimant.json" `
  --claimant-review "$root/arm298-route-physics-claimant-review-001/review.json" `
  --interpreter 'C:/IsaacSim/env_6_1_0/Scripts/python.exe' `
  --repository-commit $commit `
  --repository-root . `
  --binding-source "$src/nominal_route_arm298_launch_binding.py" `
  --output "$root/arm298-route-physics-launch-binding-001/binding.json"

python "$src/nominal_route_arm298_launch_binding_review.py" `
  --binding "$root/arm298-route-physics-launch-binding-001/binding.json" `
  --claimant "$root/arm298-route-physics-claimant-001/claimant.json" `
  --claimant-review "$root/arm298-route-physics-claimant-review-001/review.json" `
  --binding-source "$src/nominal_route_arm298_launch_binding.py" `
  --interpreter 'C:/IsaacSim/env_6_1_0/Scripts/python.exe' `
  --repository-commit $commit `
  --repository-root . `
  --output "$root/arm298-route-physics-launch-binding-review-001/review.json"
```

Both commands are single-write and refuse existing outputs.

## Authority and next boundary

The binding and review observed no authorization, evaluated no live gate,
claimed no attempt, imported no Isaac module, and stepped no physics. They do
not grant hardware or physical authority. Their acceptance permits only
implementation and independent review of an import-inert ARM-298 executable
launcher. A simulation still requires that launcher review plus a fresh exact
single-use ARM-298 authorization.
