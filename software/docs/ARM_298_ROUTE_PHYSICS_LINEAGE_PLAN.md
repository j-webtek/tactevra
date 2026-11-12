# ARM-298 route-physics lineage plan

## Purpose

ARM-297 is terminal and immutable. ARM-298's production-solver qualification
and independent reproduction proved that the corrected canonical branch passes
all 287 governed `SPACE` route rows without relaxing the `0.05 rad` continuity
limit. The ARM-298 lineage plan turns that accepted offline evidence into a
new, reproducible simulation boundary rather than replaying ARM-297.

The inert plan and independent reviewer bind:

- the exact retained ARM-298 qualification and review documents;
- merged qualification commit `8541cef20a63967d44cad14885bdd01f927af8ab`;
- all 13 production model, context, solver, runtime, worker, and backend inputs;
- the qualified Isaac 6.1 Python binary and its exact hash;
- the `SPACE` episode `episode-ef340d0ad2740c118d87`;
- fresh absent attempt, EULA-preflight, and memory-preflight outputs; and
- a new, exact, non-reusable ARM-298 authorization statement.

The reviewer independently reopens every input, statically rejects Isaac,
transport, runtime, backend, motion, target, and attempt call surfaces in the
builder, and proves all three governed future outputs remain absent.

## Authority boundary

The plan and review do not construct a claimant, observe authorization, claim
or consume an attempt, collect live preflights, import or start Isaac, load a
scene, step physics, invoke a runtime or backend, submit a joint position or
target, play a trajectory, contact a key, access hardware, or grant physical
authority. ARM-297 cannot be replayed, and its authorization is not reusable.

## Retained evidence

The external evidence is retained under `C:\IsaacSim\artifacts\issue190`:

| Artifact | File SHA-256 | Canonical document SHA-256 |
| --- | --- | --- |
| `arm298-route-physics-lineage-plan-001/plan.json` | `3ac4957aa5bfe164b5b64a1427e90e46642677cc56d057c4c774a9b3fc9bcd4c` | `9e3f0707e5795a7dafcfd6be938ea272ab125de0353018acc1095876f60f7f1c` |
| `arm298-route-physics-lineage-plan-review-001/review.json` | `e82277b3f2189d8c5bd665a9aed482c08998b3b0a62ee862355e09a04ea4e0bf` | `45f41e5ce4ab41d88751a60bead1ed085c8fba4fc717a6093d0f1a3211b8cb88` |

The plan status is `READY_FOR_INDEPENDENT_ARM298_LINEAGE_PLAN_REVIEW`; the
review status is `ACCEPTED_ARM298_LINEAGE_FOR_CLAIMANT_CONSTRUCTION`. The
attempt and both live-preflight directories remain absent.

## Reproduction

From the repository root in PowerShell:

```powershell
$root = 'C:/IsaacSim/artifacts/issue190'
$src = 'software/integrations/isaac_sim'
$plan = "$root/arm298-route-physics-lineage-plan-001/plan.json"
$runtime = @(
  '--runtime-source', 'canonical_ik_adapter', "$src/nominal_route_canonical_ik_row_adapter.py",
  '--runtime-source', 'canonical_ik_solver', 'software/src/rocell/kinematics/ik.py',
  '--runtime-source', 'complete_runtime_composition', "$src/nominal_route_complete_runtime_composition.py",
  '--runtime-source', 'concrete_native_attempt_binding', "$src/nominal_route_concrete_native_attempt_binding.py",
  '--runtime-source', 'native_root_path_correction', "$src/nominal_route_native_root_path_correction.py",
  '--runtime-source', 'native_runtime_factory', "$src/nominal_route_native_runtime_factory.py",
  '--runtime-source', 'native_runtime_worker_integration', "$src/nominal_route_native_runtime_worker_integration.py",
  '--runtime-source', 'native_sweep_binding', "$src/nominal_route_native_sweep_binding.py",
  '--runtime-source', 'physics_backend', "$src/nominal_route_physics_backend.py",
  '--runtime-source', 'physics_worker', "$src/nominal_route_physics_worker.py",
  '--runtime-source', 'pinned_model_loader', 'software/src/rocell/application/_pinned_model.py',
  '--runtime-source', 'simulation_context', 'software/src/rocell/application/context.py',
  '--runtime-source', 'system_manifest', 'software/config/system_manifest.json'
)

$planArgs = @(
  "$src/nominal_route_arm298_lineage_plan.py",
  '--qualification', "$root/arm298-canonical-continuity-qualification-001/receipt.json",
  '--qualification-review', "$root/arm298-canonical-continuity-qualification-review-001/review.json"
) + $runtime + @(
  '--repository-commit', '8541cef20a63967d44cad14885bdd01f927af8ab',
  '--qualified-interpreter', 'C:/IsaacSim/env_6_1_0/Scripts/python.exe',
  '--proposed-attempt-directory', "$root/arm298-nominal-route-physics-attempt-001",
  '--proposed-eula-receipt', "$root/arm298-nominal-route-physics-eula-preflight-001/receipt.json",
  '--proposed-memory-receipt', "$root/arm298-nominal-route-physics-memory-preflight-001/receipt.json",
  '--output', $plan
)
python @planArgs

$reviewArgs = @(
  "$src/nominal_route_arm298_lineage_plan_review.py",
  '--plan', $plan,
  '--plan-source', "$src/nominal_route_arm298_lineage_plan.py",
  '--qualification', "$root/arm298-canonical-continuity-qualification-001/receipt.json",
  '--qualification-review', "$root/arm298-canonical-continuity-qualification-review-001/review.json"
) + $runtime + @(
  '--qualified-interpreter', 'C:/IsaacSim/env_6_1_0/Scripts/python.exe',
  '--output', "$root/arm298-route-physics-lineage-plan-review-001/review.json"
)
python @reviewArgs
```

Both commands are single-write and refuse existing outputs.

## Single-use claimant and independent review

The claimant pins the accepted lineage and review, the retained fail-closed
base worker, both fresh-preflight implementations, and the worker source. Its
future callable admits at most one delegation after the exact ARM-298
statement, unchanged sources, passing EULA and memory gates, and exclusive
retention of both receipts. Building the definition does not call that
runtime surface.

The independent reviewer reopens every exact byte and statically proves the
future ordering. The retained artifacts are:

| Artifact | File SHA-256 | Canonical document SHA-256 |
| --- | --- | --- |
| `arm298-route-physics-claimant-001/claimant.json` | `0a6649d4eb98081f193f5ede79fde2b01ec05a5ae6c54ced56c6eceb9ed6760c` | `a23ec05b51e3e14d3491be588ea3cb76fdf060f590c11adbd28315dcf1fbeaa4` |
| `arm298-route-physics-claimant-review-001/review.json` | `b8b4d40efe21ef98629444cc834e9f67cd9f96dcd3bf23739c88ee185e961547` | `dc1501b904a984be6ac2dd097e4709bafddce6556f65d4d520df925c78431896` |

The claimant status is `READY_FOR_INDEPENDENT_ARM298_CLAIMANT_REVIEW`;
the review status is `ACCEPTED_FOR_EXACT_ARM298_ONE_ATTEMPT_AUTHORIZATION`.
Authorization remains unobserved, the attempt remains unclaimed, Isaac remains
unstarted, and the attempt plus both live-preflight paths remain absent.

From the repository root in PowerShell:

```powershell
$root = 'C:/IsaacSim/artifacts/issue190'
$src = 'software/integrations/isaac_sim'

python "$src/nominal_route_arm298_claimant.py" `
  --plan "$root/arm298-route-physics-lineage-plan-001/plan.json" `
  --plan-review "$root/arm298-route-physics-lineage-plan-review-001/review.json" `
  --base-worker "$root/arm254-nominal-route-physics-worker-001/worker.json" `
  --claimant-source "$src/nominal_route_arm298_claimant.py" `
  --claimant-review-source "$src/nominal_route_arm298_claimant_review.py" `
  --eula-preflight-source "$src/nominal_route_isaac_eula_preflight.py" `
  --memory-preflight-source "$src/nominal_route_memory_preflight.py" `
  --worker-source "$src/nominal_route_physics_worker.py" `
  --output "$root/arm298-route-physics-claimant-001/claimant.json"

python "$src/nominal_route_arm298_claimant_review.py" `
  --claimant "$root/arm298-route-physics-claimant-001/claimant.json" `
  --claimant-source "$src/nominal_route_arm298_claimant.py" `
  --plan "$root/arm298-route-physics-lineage-plan-001/plan.json" `
  --plan-review "$root/arm298-route-physics-lineage-plan-review-001/review.json" `
  --base-worker "$root/arm254-nominal-route-physics-worker-001/worker.json" `
  --claimant-review-source "$src/nominal_route_arm298_claimant_review.py" `
  --eula-preflight-source "$src/nominal_route_isaac_eula_preflight.py" `
  --memory-preflight-source "$src/nominal_route_memory_preflight.py" `
  --worker-source "$src/nominal_route_physics_worker.py" `
  --output "$root/arm298-route-physics-claimant-review-001/review.json"
```

Both commands are single-write and refuse existing outputs. They do not
collect live preflights or invoke `Arm298Claimant.run`.

## Next boundary

Acceptance permits only construction and independent review of a reproducible
ARM-298 launch binding. A simulation may run only after that binding and the
executable launcher are independently accepted and a fresh exact ARM-298
authorization is supplied. The claimant review itself is not attempt authority.
