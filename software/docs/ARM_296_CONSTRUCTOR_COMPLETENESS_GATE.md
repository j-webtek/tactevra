# ARM-296 constructor-completeness gate

## Purpose

ARM-295 is an immutable, consumed simulation attempt. It passed its fresh EULA
and memory gates and started Isaac Sim 6.1, then failed at `construct_runtime`
because the concrete binding supplied no canonical IK constructor inputs. The
binding correction is merged, but another simulator attempt is not justified
by input-loading tests alone.

ARM-296 closes that evidence gap without launching Isaac or exercising motion.
It loads the retained ARM-295 terminal status, the exact reviewed runtime
documents, and the locked repository simulation context. It then constructs:

- the real `RoArmM3NumericalIk` from all eight canonical inputs;
- the native clearance, canonical IK, tool/key metric, and root-drift adapters;
- the shared-solver complete runtime composition; and
- the discovered nested-root compatibility boundary.

The native articulation, scene-query, key-view, and root-view inputs are inert
protocol sentinels. Only the one key and one root baseline pose read required by
the reviewed factory are permitted. Any transform read, scene query, joint
submission, second baseline read, or retry fails the gate.

## Authority boundary

The gate and its reviewer import no Isaac module, create no simulator session,
claim no governed attempt, step no physics, call no runtime protocol method,
play no trajectory, submit no joint target, contact no key, and access no
hardware. They grant no physical authority. ARM-295 is never replayed.

## Acceptance

The independently reviewed receipt must show:

- the exact retained ARM-295 status hash;
- the exact corrected binding source hash;
- `former_failure_crossed: true` at `construct_runtime`;
- the production solver, four production adapters, and complete composition;
- one shared solver identity for IK and tool/key metrics;
- exactly one key and one root baseline read;
- zero articulation or scene-query protocol calls; and
- zero attempt, Isaac, physics, runtime, trajectory, target, contact, hardware,
  or physical authority.

After acceptance, the next simulator run must use a new attempt number, newly
pinned and independently reviewed lineage, and a fresh exact one-use
authorization. ARM-296 itself does not authorize that run.
