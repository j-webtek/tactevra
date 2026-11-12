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

## Executable launcher review

The executable launcher and its independent reviewer are now implemented. The
launcher is import-inert and accepts only the exact ARM-297 statement. Before
constructing the deferred backend it verifies the qualified interpreter,
requires the binding's commit to remain in current ancestry, re-hashes all ten
runtime sources plus claimant, worker, route, and runtime-binding inputs,
reopens this binding and review, validates its own review, and rejects any
pre-existing governed output. It then delegates once to `Arm297Claimant`, which
owns fresh EULA then memory gates and receipt retention; the existing worker
owns atomic attempt claim and terminalization before shutdown.

The independent launcher review is retained at
`C:\IsaacSim\artifacts\issue190\arm297-route-physics-launcher-review-001\review.json`:

- file SHA-256:
  `a036ba62fc388336f458e3106fc5eab783c06582521e7987605d06a5c7249c7a`;
- canonical review SHA-256:
  `80578e3ea4569b5ff52398f1141ea7f0c718a4695a4954d4408c2fa7204ece39`;
- status: `ACCEPTED_FOR_EXACT_ARM297_ONE_ATTEMPT_AUTHORIZATION`.

The review used static analysis and exact-byte checks only. It observed no
authorization, invoked no claimant or backend, started no simulator, stepped
no physics, and created none of the attempt/EULA/memory outputs. The next step
is a separately supplied exact ARM-297 one-attempt authorization. ARM-295 or
any earlier authorization is rejected and cannot satisfy this boundary.
