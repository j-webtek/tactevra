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

## Executable launcher review

`nominal_route_arm298_launch.py` is now the import-inert executable consumer.
Before constructing its deferred backend, it requires the exact ARM-298
statement and revalidates the qualified interpreter, repository ancestry,
claimant and binding evidence, all 13 production sources, its own independent
review, and absence of the governed attempt and both fresh preflight outputs.
It contains no retry loop and delegates exactly once to `Arm298Claimant`.

The independent review is retained at
`C:\IsaacSim\artifacts\issue190\arm298-route-physics-launcher-review-001\review.json`:

- file SHA-256:
  `16ac1278217a6bcdf3dc680924fc999d8e3b132074a19860088f20258230b515`;
- canonical review SHA-256:
  `6c02413ad99169259f2cb345bb68c4969dabe0515e0df4623426f7292ff94e9b`;
- launcher source SHA-256:
  `cd3cc1f4523be74c7d403f87d2308c832cdeb1e7da903cc686f72e9ccbeb0a4f`;
- status: `ACCEPTED_FOR_EXACT_ARM298_ONE_ATTEMPT_AUTHORIZATION`.

This review used static analysis and exact-byte checks only. It observed no
authorization, invoked no claimant or backend, started no simulator, stepped
no physics, created none of the governed attempt/EULA/memory outputs, and
granted no hardware or physical authority. A fresh exact ARM-298 authorization
is still required before the launcher may execute.
