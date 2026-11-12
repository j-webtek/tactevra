# ARM-297 route-physics lineage plan

## Purpose

ARM-295 is terminal and immutable. ARM-296 proved, without starting Isaac, that
the corrected runtime now crosses ARM-295's former `construct_runtime` failure
and received independent acceptance. ARM-297 is therefore a new lineage, not a
retry or continuation of ARM-295.

The ARM-297 plan builder binds:

- the exact retained ARM-296 constructor receipt and independent review;
- the corrected concrete binding and every production source needed by the
  runtime, worker, and backend;
- the `SPACE` episode `episode-ef340d0ad2740c118d87`;
- three absent future outputs for the attempt, fresh EULA receipt, and fresh
  memory receipt; and
- a new, exact, non-reusable ARM-297 authorization statement.

An independent reviewer re-hashes every bound file, statically rejects Isaac,
transport, backend, runtime, physics, target, and attempt call surfaces in the
plan builder, and proves the three governed outputs remain absent.

## Authority boundary

The plan and review do not construct a claimant, observe authorization, collect
live preflights, claim or consume an attempt, import or start Isaac, load a
scene, step physics, invoke a runtime method or backend, submit a joint target,
play a trajectory, contact a key, access hardware, or grant physical authority.
They cannot replay ARM-295 and do not authorize ARM-297.

## Reproduction

From the repository root in PowerShell, with the retained external evidence at
`C:\IsaacSim\artifacts\issue190`:

```powershell
$root = 'C:/IsaacSim/artifacts/issue190'
$src = 'software/integrations/isaac_sim'
$planOut = "$root/arm297-route-physics-lineage-plan-001/plan.json"

python "$src/nominal_route_arm297_lineage_plan.py" `
  --gate-receipt "$root/arm296-constructor-completeness-gate-001/receipt.json" `
  --gate-review "$root/arm296-constructor-completeness-gate-review-001/review.json" `
  --runtime-source complete_runtime_composition "$src/nominal_route_complete_runtime_composition.py" `
  --runtime-source concrete_native_attempt_binding "$src/nominal_route_concrete_native_attempt_binding.py" `
  --runtime-source constructor_completeness_gate "$src/nominal_route_constructor_completeness_gate.py" `
  --runtime-source constructor_completeness_gate_review "$src/nominal_route_constructor_completeness_gate_review.py" `
  --runtime-source native_root_path_correction "$src/nominal_route_native_root_path_correction.py" `
  --runtime-source native_runtime_factory "$src/nominal_route_native_runtime_factory.py" `
  --runtime-source native_runtime_worker_integration "$src/nominal_route_native_runtime_worker_integration.py" `
  --runtime-source native_sweep_binding "$src/nominal_route_native_sweep_binding.py" `
  --runtime-source physics_backend "$src/nominal_route_physics_backend.py" `
  --runtime-source physics_worker "$src/nominal_route_physics_worker.py" `
  --proposed-attempt-directory "$root/arm297-nominal-route-physics-attempt-001" `
  --proposed-eula-receipt "$root/arm297-nominal-route-physics-eula-preflight-001/receipt.json" `
  --proposed-memory-receipt "$root/arm297-nominal-route-physics-memory-preflight-001/receipt.json" `
  --output $planOut

python "$src/nominal_route_arm297_lineage_plan_review.py" `
  --plan $planOut `
  --plan-source "$src/nominal_route_arm297_lineage_plan.py" `
  --gate-receipt "$root/arm296-constructor-completeness-gate-001/receipt.json" `
  --gate-review "$root/arm296-constructor-completeness-gate-review-001/review.json" `
  --runtime-source complete_runtime_composition "$src/nominal_route_complete_runtime_composition.py" `
  --runtime-source concrete_native_attempt_binding "$src/nominal_route_concrete_native_attempt_binding.py" `
  --runtime-source constructor_completeness_gate "$src/nominal_route_constructor_completeness_gate.py" `
  --runtime-source constructor_completeness_gate_review "$src/nominal_route_constructor_completeness_gate_review.py" `
  --runtime-source native_root_path_correction "$src/nominal_route_native_root_path_correction.py" `
  --runtime-source native_runtime_factory "$src/nominal_route_native_runtime_factory.py" `
  --runtime-source native_runtime_worker_integration "$src/nominal_route_native_runtime_worker_integration.py" `
  --runtime-source native_sweep_binding "$src/nominal_route_native_sweep_binding.py" `
  --runtime-source physics_backend "$src/nominal_route_physics_backend.py" `
  --runtime-source physics_worker "$src/nominal_route_physics_worker.py" `
  --output "$root/arm297-route-physics-lineage-plan-review-001/review.json"
```

Both commands are single-write and refuse an existing output. A passing review
allows only the next inert step: construction and independent review of a
single-use ARM-297 claimant. It does not permit a simulation attempt.

## Retained result

The inert plan and review produced the following external evidence:

| Artifact | File SHA-256 | Canonical document SHA-256 |
| --- | --- | --- |
| `arm297-route-physics-lineage-plan-001/plan.json` | `7e56553efcf4a3c74fcae84d78408db6962271f12d746c28742dc87f64d3089b` | `d478be447bb6a1dbb6dd377d29aa22519cf334d98a286cd1e958378bba28e341` |
| `arm297-route-physics-lineage-plan-review-001/review.json` | `d494ce802c6934c1f20c3ce6f01e2a178b9452a23cd0333908a66c7ba976cfbe` | `84ec855a97f0c2e08a5f072ee5509bd01de553f5ec18a71676e237d827af7215` |

The plan status is `READY_FOR_INDEPENDENT_ARM297_LINEAGE_PLAN_REVIEW`; the
review status is `ACCEPTED_ARM297_LINEAGE_FOR_CLAIMANT_CONSTRUCTION`. The
attempt and both live-preflight directories remain absent. No authorization was
observed and no attempt, Isaac, physics, runtime, target, trajectory, contact,
hardware, or physical authority was exercised.

## Single-use claimant

The next inert layer constructs a fresh claimant around the retained ARM-254
fail-closed worker. It clones the worker for ARM-297 while keeping the old
ARM-253 statement only as an internal compatibility token; that token is not
external authority. The claimant runtime requires, in order:

1. the exact new ARM-297 authorization statement;
2. unchanged plan, review, claimant, runtime, worker, and backend sources;
3. a fresh passing EULA preflight retained before attempt claim;
4. a fresh passing memory preflight retained before attempt claim;
5. exclusive creation of both receipts; and
6. exactly one delegation to the fail-closed worker.

The independent static reviewer proves that ordering and rejects direct
simulator, motion, or transport calls. Building and reviewing the claimant do
not collect either live preflight and do not invoke its `run` method.

```powershell
$root = 'C:/IsaacSim/artifacts/issue190'
$src = 'software/integrations/isaac_sim'

python "$src/nominal_route_arm297_claimant.py" `
  --plan "$root/arm297-route-physics-lineage-plan-001/plan.json" `
  --plan-review "$root/arm297-route-physics-lineage-plan-review-001/review.json" `
  --base-worker "$root/arm254-nominal-route-physics-worker-001/worker.json" `
  --claimant-source "$src/nominal_route_arm297_claimant.py" `
  --claimant-review-source "$src/nominal_route_arm297_claimant_review.py" `
  --eula-preflight-source "$src/nominal_route_isaac_eula_preflight.py" `
  --memory-preflight-source "$src/nominal_route_memory_preflight.py" `
  --worker-source "$src/nominal_route_physics_worker.py" `
  --output "$root/arm297-route-physics-claimant-001/claimant.json"

python "$src/nominal_route_arm297_claimant_review.py" `
  --claimant "$root/arm297-route-physics-claimant-001/claimant.json" `
  --claimant-source "$src/nominal_route_arm297_claimant.py" `
  --plan "$root/arm297-route-physics-lineage-plan-001/plan.json" `
  --plan-review "$root/arm297-route-physics-lineage-plan-review-001/review.json" `
  --base-worker "$root/arm254-nominal-route-physics-worker-001/worker.json" `
  --claimant-review-source "$src/nominal_route_arm297_claimant_review.py" `
  --eula-preflight-source "$src/nominal_route_isaac_eula_preflight.py" `
  --memory-preflight-source "$src/nominal_route_memory_preflight.py" `
  --worker-source "$src/nominal_route_physics_worker.py" `
  --output "$root/arm297-route-physics-claimant-review-001/review.json"
```

| Artifact | File SHA-256 | Canonical document SHA-256 |
| --- | --- | --- |
| `arm297-route-physics-claimant-001/claimant.json` | `ecfe03421730c6bca646842e433226aa0fe3c71b59af744c3ae78d313adb7e83` | `f77d3dfe2e756f764821f01ef7937ddcd1364819a065fa3acbc0d4f0caada72b` |
| `arm297-route-physics-claimant-review-001/review.json` | `f92d9b0163e79eabe2817ef18caf9e43bfbf82acec1ddac61d2c5311d84aa309` | `b09ebc79bd0796f50c757bda2336bc8985ffe2f27679f05e9a66591abd61df0e` |

The accepted claimant still grants no authorization. Before any attempt, a
reproducible launch binding must pin the qualified Isaac interpreter, merged
source identities, claimant/review hashes, fresh-gate outputs, terminalization
behavior, and the exact external statement. Until then, do not invoke the
claimant runtime.
