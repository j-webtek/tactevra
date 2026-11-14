# ARM-301 component-OBB clearance correction plan

## Objective

Replace the whole-link sphere self-collision test that terminalized ARM-300
with a continuous, mesh-containing component-OBB proof. Keep the existing
sphere sweeps for robot-versus-environment clearance. Do not add an SRDF
`Never` exclusion, replay ARM-300, or weaken the 0.5 mm clearance margin.

This correction is simulation-only and zero-authority. It cannot authorize a
simulator launch, trajectory playback, hardware access, or physical movement.

## Why this is the correct correction

ARM-300 stopped on `base_link` against `link2`. The old representation places
one sphere around each complete link. `link2` is long and thin, so its
137.186 mm sphere occupies substantial empty space. The sphere overlaps the
73.546 mm base sphere even when the source meshes remain separated.

The retained triangle-partition receipt already provides 29 oriented boxes
that contain every assigned triangle vertex with zero serialized overflow:

- 2 component boxes for `base_link`;
- 17 boxes for `link2`, including its governed triangle partition;
- 10 boxes across the remaining five links.

The 49-pose differential reports zero false negatives for those boxes and
removes the only nonadjacent false positive in that corpus. Finite replay is
useful regression evidence but is not promoted as a continuous proof. The
continuous proof instead follows directly from box containment, SAT
separation, and conservative point-motion bounds.

## Continuous proof

For each adjacent joint interval:

1. Transform every retained local component OBB into world coordinates at the
   interval start using the public articulation link-transform protocol.
2. Compute a separating-axis gap for every nonexcluded component pair.
3. Bound the displacement of every point of each box over the full interval.
   Each ancestor-joint coefficient uses the local center reach plus the box
   circumradius and all upstream joint-origin reaches.
4. Subtract both point-motion bounds from the SAT gap.
5. Accept only when every residual exceeds the unchanged 0.5 mm margin.
6. Bisect an indeterminate interval and repeat, up to depth 12. Exhaustion
   fails closed.

Because each box contains its assigned source triangles, separating the boxes
separates those source mesh surfaces. Because the motion bound covers every
point for the complete interval, this separation is continuous rather than
sampled clearance. Surface separation alone does not rule out one closed solid
being wholly inside another: the partition has non-watertight bands and does
not establish solid-volume containment. Before this result can be treated as a
solid collision proof, independently establish the applicable source meshes'
solid semantics and initial non-nesting for every nonexcluded pair, or use a
conservative representation proven to contain their full solids. Until then,
the audit result is surface-clearance evidence, not a complete collision proof.

The implementation is split into:

- `nominal_route_component_obb_clearance.py`: Isaac-import-free proof core;
- `nominal_route_native_component_obb_binding.py`: reviewed public-transform
  binding and containment-profile builder.

The builder pins the governed URDF and triangle-partition receipt. It promotes
only containment facts. It explicitly does not promote the old finite replay
or any SRDF `Never` exclusions.

## Governed SPACE-window feasibility result

An offline audit evaluated the source SPACE route segments 653→654 through
940→941 with the governed URDF, retained 29-box profile, six direct-joint
exclusions, 0.5 mm margin, and the same depth-12 fail-closed rule.

- adjacent segments evaluated: 288;
- terminal proof intervals: 292;
- segments requiring bisection: 4;
- maximum subdivision depth: 1;
- exhausted or indeterminate segments: 0;
- worst certified residual before the 0.5 mm acceptance threshold:
  approximately 16.453 mm.

This establishes surface-clearance feasibility on the retained source route. It is
not an ARM-301 simulation result: the future backend regenerates canonical IK,
so the same proof must run on those regenerated intervals inside the admitted
runtime.

The audit can be reproduced with Python, SciPy, the pinned route file and a
fresh output path:

```text
python software/integrations/isaac_sim/arm301_source_route_obb_audit.py --route <native_mechanics_plan.json> --output <new-receipt.json>
```

The command refuses a different route digest or an existing output. Its
receipt binds the route, URDF, partition, binding, proof and audit sources.
Its locally constructed review record is a software-audit fixture, not an
independent review or permission to run the Isaac worker. The audit does not
check environment clearance or regenerated IK.

For an exploratory 14-box whole-component candidate, add `--whole-components`
to the command. This replaces link2's 16 surface bands with its two retained
whole-component boxes and pins the original reduction receipt. The offline
SPACE window again passed all 288 segments with a minimum residual of about
16.453 mm. Each axis-aligned box is convex and contains all vertices of its
assigned complete source component, or all link5 vertices for the whole-link
fallback; it therefore contains their convex hull. The whole-box result proves
separation for the checked nonadjacent pairs of this explicitly defined
convex-hull surrogate, including the chosen fills of the open meshes. The six
direct-joint pairs remain excluded. This does not prove that the physical robot,
attachments, or omitted geometry fit the surrogate, or that the mesh-to-robot
frame alignment is correct. A shared, source-hashed builder now reconstructs
the same 14 boxes for the audit and concrete-binding validation. The native
worker remains disabled by the solid-containment qualification guard.

A separate local check loaded the seven vendor STL files after verifying each
against its retained SHA-256, split their processed meshes into connected face
components, and verified that every component's vertices fit one of its link's
candidate boxes. The component face counts sum to each processed mesh's face
count. Link5 has 114 processed connected components, all inside its single
whole-link box. Receipt `664c030c00f5cda8efad8b90c18c571f6b2d27b79233defd86e0ca3d586ca9fc`
binds this check to candidate definition
`884a8881eb219bf94c1104ac733b1868e094eda72961326122ff836364416530`.
This verifies the modeled mesh containment, not missing hardware, native
frames, a human review, or a physical qualification.

Reproduce with the pinned vendor M3 STL directory, trimesh, and a new output:

```text
python software/integrations/isaac_sim/arm301_mesh_containment_audit.py --mesh-dir <vendor-m3-meshes> --output <new-receipt.json>
```

An offline comparison of the pinned vendor Xacro at commit `40dbd84` with the
governed URDF found matching parent, child, type, origin, and movable-axis
values for the seven joints from world through gripper. All seven vendor link
visual and collision meshes have zero local translation and rotation and use
the 0.001 mesh scale; their pinned mesh hashes match the retained inventory.
The local comparison receipt has canonical SHA-256
`1ac0e4c4616c49d54f0d706468efefd1ffd094aba2fe0c7df5d9e036f1e7e11a`.
This establishes agreement between declared vendor and governed link frames;
it does not check imported Isaac transforms, physical assembly, or omitted
geometry.

The pinned imported USD's six authored revolute joint relationships, parent
and child names, local poses, and axes were also compared with the governed
URDF using OpenUSD without starting Isaac. All six matched within 0.0001 mm and
0.000001 rad; child-side frames were identity. Receipt
`95b0f422a92ddef089b2ac59a65c4bab380dd37559619ee4bbd5c946c852174f`
binds the exact USD, URDF, and audit source. This checks authored joint frames;
it does not inspect live link poses, dynamics, or the physical robot.

```text
python software/integrations/isaac_sim/arm301_usd_joint_frame_audit.py --usd <pinned-imported-usd> --output <new-receipt.json>
```

For a previously captured snapshot, the offline comparator can retain a new
receipt:

```text
python software/integrations/isaac_sim/arm301_link_frame_parity.py --snapshot <snapshot.json> --output <new-receipt.json>
```

The command starts no Isaac session, refuses an existing output, and returns
exit code 2 for a valid snapshot whose link comparison fails. Snapshot provenance
is not verified.

The retained `roarm_m3_fk_parity_20260929.json` binds the same governed USD
and reports passing zero, home, and ready poses. Its Isaac probe reads the
native link5 transform and combines it with the imported hand TCP transform;
the worst reported TCP translation error is 0.000129 mm. This supports those
three end-frame comparisons only: it does not compare every intermediate link
frame, establish dynamics, or qualify the physical assembly.

`arm301_link_frame_parity.py` provides an offline comparator for a future
native snapshot: it checks all seven link poses against URDF forward kinematics
at the captured six-joint state, relative to the captured base pose. Synthetic
tests exercise translation, rotation, ordering, and invalid-quaternion errors.
No native snapshot has been captured by this comparator, and factoring out the
base means it cannot verify base placement in the workcell. A separately
authorized diagnostic and reviewed capture procedure are still needed.
The read-only snapshot helper brackets the link read with two joint-state
reads and rejects a change, but these separate reads are not atomic. The caller
must establish a stationary simulation session. The native session wrapper now
exposes read-only joint state; its source hash has changed, so previously pinned
session reviews cannot be reused as authority for this updated implementation.
An offline receipt builder also binds the snapshot, comparison, URDF, and
comparator source by hash and rechecks the two captured joint states. It does
not establish where a supplied snapshot came from; provenance and authorization
must be supplied by the eventual reviewed diagnostic.
The session-level helper consumes an already initialized session, requires zero
reported physics steps before and after the read, and never starts or steps the
session. Its simulated tests cover a step occurring during capture. It does not
itself authenticate the session or replace the future capture procedure.
`run_snapshot_diagnostic` prepares the zero-step session lifecycle around that
helper: it claims a fresh output directory, retains a result, attempts shutdown
even after startup failure, and refuses reuse of the claimed directory. It is
not a standalone authorization gate: the caller must provide an explicitly
authorized run and a source-pinned session. Tests use a fake session only.
The `--run-diagnostic` mode constructs the existing Isaac driver, which
validates its pinned robot USD, layout, route and mechanics profile, and passes
their hashes and the diagnostic and driver source hashes into the result. The
mode has not been run with Isaac and does not itself authenticate the runtime
environment, independently review its source, or grant authorization.

The concrete native binding now rejects the surface-partition definition even
when its review is otherwise valid: surface separation alone cannot rule out
nested solids. It cannot currently create a native worker, since its pinned
definition builder has no solid-containment certification. The 14-box candidate
must be independently validated before enabling this path; a
self-declared flag or the offline audit fixture is not sufficient.

## Acceptance sequence

The repository's offline CI selection includes the component clearance,
native binding, composed adapter, and link-frame parity test files. SciPy is a
test dependency so the parity and offline geometry checks run in that suite
rather than silently skipping for a missing package.

1. Unit-test SAT separation, point-motion reduction, recursive refinement,
   fail-closed exhaustion, source pinning, and the public-transform binding.
2. Independently review the component profile builder and native binding.
3. Compose component self-clearance with the existing environment sphere
   sweep; neither proof may suppress the other.
4. Run an offline route audit and retain a canonical receipt bound to the exact
   route, profile, URDF, and implementation hashes.
5. Qualify closed-solid semantics and non-nesting for every checked pair, or
   replace the surface envelope with a proven solid-containing envelope.
6. Independently review the composed runtime and an ARM-301 single-use launch
   chain.
7. Only then request a new, exact, one-attempt ARM-301 authorization.

Any failure remains fail-closed. ARM-300 stays immutable and no authorization
from ARM-300 transfers to ARM-301.
