# ARM-297 route-physics launch binding

ARM-297 now has an inert, independently accepted reproducible launch binding.
This checkpoint closes the gap between the reviewed single-use claimant and a
future executable launcher without starting Isaac or consuming an attempt.

The binding pins:

- merged repository commit `20ec4ce2d27da74b54e77741b08b4dd5422c7587`;
- qualified interpreter
  `C:\IsaacSim\env_6_1_0\Scripts\python.exe`, file SHA-256
  `d55736b9f3d6b4ca7985b82db8ce11edfa09994cf93ce31c6b506543b74f32eb`;
- the exact ARM-297 claimant and independent review bytes and canonical hashes;
- all ten corrected production runtime-source hashes;
- the absent attempt, EULA-receipt, and memory-receipt paths;
- the exact future ARM-297 authorization statement;
- EULA-then-memory ordering and retention of both receipts before claim;
- one claimant delegation, terminal status before shutdown, and no retry; and
- zero trajectory, hardware, or physical authority.

## Retained evidence

| Artifact | File SHA-256 | Canonical document SHA-256 |
| --- | --- | --- |
| `arm297-route-physics-launch-binding-001/binding.json` | `1c240f997ccafe1cd17426c3f5cd9c6d7d3fce1f2d659662d655d87bed9ba00a` | `ba890c24a14fad8b8537c8246fc8a97aefa08e3e680a2448e6fddb0eb22375f1` |
| `arm297-route-physics-launch-binding-review-001/review.json` | `ffd02afb5d24ee471012ba195a31e4b5fef58bffac974e2edf963794764b114d` | `bb01b94dd3bf4fcc39aa8df15dd7580844ff77048c7c6fba65b1c5e28df7aaf0` |

Both artifacts live under `C:\IsaacSim\artifacts\issue190`. The independent
review reopens every bound byte and statically rejects simulator, motion, and
transport execution in the builder.

## Authority and next boundary

The binding observed no authorization, evaluated no live gate, claimed no
attempt, imported no Isaac module, and stepped no physics. The ARM-295 attempt
remains consumed and immutable. The user statement that authorized ARM-295 is
not reusable for ARM-297.

Next, implement and independently review an executable ARM-297 launcher that
consumes this exact binding. Do not run that launcher, collect fresh gate
receipts, or request a new ARM-297 authorization until its source and tests are
merged and its review accepts the exact delegation and terminalization path.
