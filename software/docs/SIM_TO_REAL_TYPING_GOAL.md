# Simulation-to-real robotic typing goal

Updated: 2026-11-10

This is the durable product and engineering objective for the RoCell typing
workstream. It supersedes older immediate-next-action language that deferred
camera registration, attachment calibration, contact mechanics, or Isaac Sim.
Historical diagnostics and trial evidence remain valid only for the scope they
actually measured.

## Objective

Develop and validate an accurate, reproducible simulation-to-real robotic
typing system that uses the calibrated RoCell workcell, camera feedback,
attachment-specific profiles, and physics-based planning to type intended
keyboard inputs reliably in simulation first, then transfers through explicitly
authorized, safety-gated physical validation until the real arm can type
successfully without unsafe contact or unverified motion.

## Definition of success

The system is complete only when a requested text sequence can be converted
into verified real keyboard events while the system:

1. localizes the board, keyboard, and requested keys from current evidence;
2. selects the exact installed arm, camera, keyboard, and tool profile;
3. plans a collision-screened approach, press, and retract for each key;
4. executes within declared joint, velocity, acceleration, clearance, contact,
   and uncertainty limits;
5. confirms the intended key event and rejects adjacent or missing events;
6. stops safely when calibration, feedback, authority, or confidence is stale;
7. retains enough inputs, hashes, telemetry, and results to reproduce and audit
   the decision; and
8. demonstrates the required success rate across held-out placements, keys,
   sequences, and environmental variation.

A rendered scene, reachable IK target, decreasing policy loss, isolated key
contact, or one successful physical press is progress, not completion.

## System contract

### Coordinate frames and uncertainty

Every action must use one versioned transform graph:

```text
camera -> calibration board -> keyboard -> key surface
arm base -> joints -> wrist -> installed attachment -> tool center point
```

Each edge records its source, units, timestamp or immutable design identity,
uncertainty, and validity conditions. Camera observations may update the board
or keyboard pose, but they must not silently alter arm geometry or an attachment
TCP. Missing or incompatible edges fail closed.

### Attachment-separated profiles

`no_attachment`, `stylus_attachment`, and every later tool remain separate
profiles. Each profile owns its TCP transform, collision envelope, mass and
inertia assumptions, approach orientation, clearance, contact point, permitted
travel, and uncertainty. A route qualified for one profile cannot be promoted
to another by changing only a tool-length constant.

### Digital-twin parameter classes

Every simulation parameter is labeled:

- `DESIGN`: sourced from controlled BOM, CAD, or manufacturer data;
- `MEASURED`: bound to retained physical metrology and its method;
- `FITTED`: estimated from authorized physical traces and validated on held-out
  traces;
- `PROVISIONAL`: conservative simulation-only prior with explicit bounds; or
- `UNKNOWN`: unavailable and therefore unusable for a dependent qualification.

The twin covers geometry, joint axes and limits, link and tool collision shapes,
mass and inertia, servo response, backlash/compliance, keyboard/key geometry,
key travel and resistance, contact/friction parameters, camera calibration, and
controller/simulation timing. Simulation truth is never relabeled as physical
measurement.

### Planning, learning, and feedback

Deterministic geometry, IK, collision, limits, authorization, and stop rules
form the non-bypassable safety envelope. Learning may rank routes, adapt timing,
predict residuals, propose corrections, or supply a bounded policy inside that
envelope. It may not grant authority, widen limits after observing a failure,
invent missing geometry, or replace independent verification.

The operational loop is:

```text
observe -> localize -> plan -> qualify -> authorize -> execute once
        -> verify -> retain evidence -> update the model
```

Physical execution is always a separately authorized step. Simulation and
offline work never imply hardware authority.

## Qualification ladder

Progress in order. A failed rung remains evidence and does not trigger an
automatic retry.

1. **Reproducible static twin.** Rebuild the scene and transform graph from
   controlled inputs; reproduce known poses and camera projections.
2. **Mechanics and clearance.** Regenerate canonical IK, prove continuous
   collision clearance, verify fixture/root stability, and retain determinate
   tool/key metrics for a noncontact route.
3. **Single-key simulated contact.** Qualify one `SPACE` approach, controlled
   descent, actuation, and retract under native physics.
4. **Representative simulated keys.** Cover separated keys, rows, edges, and
   difficult reaches with the same evidence contract.
5. **Sequence simulation.** Type short fixed strings with rolling-horizon
   replanning, event verification, recovery, and no adjacent-key activation.
6. **Randomized simulation.** Vary measured placement, camera, TCP, mechanics,
   friction, latency, and observation noise within declared distributions.
7. **Physical noncontact correlation.** Under separate authority, compare
   predicted and observed TCP/joint behavior without keyboard contact.
8. **Physical single-key correlation.** Progress from guarded hover to one
   press/release, retaining video/vision, feedback, event, and residual data.
9. **Physical multi-key typing.** Qualify representative keys, short strings,
   placement variation, and finally requested text.

Each rung has a frozen test definition, independent review where required, and
an explicit promotion decision. Evidence from a higher-risk rung cannot be
inferred from a lower-risk or simulation-only result.

## Quantitative evidence

Before a campaign, freeze at least:

- target localization error and confidence limits;
- TCP position/orientation and joint residual limits;
- continuous environment and self-clearance margins;
- maximum approach, contact, and retract speed/acceleration;
- permitted key travel, force/torque proxy, and dwell time;
- neighboring-key exclusion criteria;
- root/fixture drift limits;
- trial count, placement distribution, and random seeds;
- per-key and per-sequence success requirements; and
- stop, timeout, stale-feedback, and no-retry behavior.

Reports distinguish simulation qualification, provisional physical correlation,
and validated physical typing. Aggregate success never conceals a key, posture,
attachment, or placement class that fails its own gate.

## Reproducibility and evidence package

Every admitted simulation or physical attempt retains:

- source commit and immutable input hashes;
- model, scene, calibration, keyboard, and attachment profile identities;
- requested text, selected keys, target poses, route, and policy identity;
- authorization and single-use claim lineage when applicable;
- simulator/runtime versions, random seeds, and parameter samples;
- commanded and observed trajectory data;
- collision, clearance, contact, key-event, and stop verdicts; and
- terminal success or unchanged failure evidence.

An output is not accepted when its inputs cannot be reopened and independently
checked.

## Current baseline and immediate path

The repository already contains calibrated board/camera evidence, keyboard and
workcell priors, attachment-separated contracts, canonical planning and native
Isaac mechanics components, a governed one-attempt worker, and retained
authorization/preflight lineage. These are substantial foundations, but they do
not yet prove a successful native route-physics attempt or real typing.

ARM-284 first exposed and retained the fast-shutdown terminalization defect.
ARM-287/ARM-288 corrected and reviewed that lifecycle. ARM-289 then proved
terminal retention while exposing a missing native link inventory;
ARM-294 confirmed the corrected inventory without motion. ARM-295 exposed
missing canonical solver construction inputs, ARM-296 proved their correction,
and ARM-297 exposed and corrected a canonical route start-boundary mismatch.
ARM-298 consumed the next fresh EULA- and memory-gated native `SPACE`
authorization on 2026-11-13. Isaac reached backend execution and failed closed
because the restricted articulation wrapper omitted its wrapped Isaac
articulation's valid `set_dof_positions` method. The immutable outcomes include
[ARM_284_ATTEMPT_POSTMORTEM.md](ARM_284_ATTEMPT_POSTMORTEM.md),
[ARM_289_ATTEMPT_POSTMORTEM.md](ARM_289_ATTEMPT_POSTMORTEM.md),
[ARM_295_ATTEMPT_POSTMORTEM.md](ARM_295_ATTEMPT_POSTMORTEM.md), and
[the ARM-298 attempt postmortem](../integrations/isaac_sim/README.md#arm-298-attempt-postmortem).
The ARM-298
authorization is consumed; the adapter correction is local code awaiting a new
reviewed lineage, not permission to rerun.

The immediate path is:

1. retain ARM-298 and its exact preflight/terminal hashes as immutable consumed
   evidence; never replay it;
2. merge and independently review the narrow articulation-setter delegation and
   its fail-closed regression tests;
3. build a newly numbered inert lineage that pins the corrected adapter, the
   accepted ARM-298 ancestry, the fixed `SPACE` episode, and fresh absent
   attempt/EULA/memory outputs;
4. independently reproduce that lineage and review its claimant and executable
   launch boundary without starting Isaac;
5. require a new exact one-use authorization before any later simulator launch;
6. diagnose any failed acceptance metric and correct the digital twin or route
   through another reviewed increment rather than replaying an attempt;
7. on a passing result, freeze the single-key simulation benchmark and expand
   to a representative multi-key set;
8. add vision-conditioned localization and rolling-horizon sequence planning;
9. qualify randomized simulation coverage; and
10. design separately authorized physical correlation campaigns only after the
   corresponding simulation gates pass.

ARM-294 has since passed its zero-motion inventory purpose, and ARM-295 was
executed once. ARM-295 passed its fresh launch gates but terminalized before
route evaluation because the concrete binding omitted required canonical IK
inputs. That defect is corrected by deriving the model, frame transform, tool
offset, gripper state, ready pose, bounds, and IK policy from the locked
simulation context. ARM-296 now constructs the real solver, four production
runtime adapters, and complete shared-solver composition around inert protocol
sentinels, proving the correction crosses ARM-295's former constructor failure
with no Isaac launch, physics, runtime call, target, trajectory, hardware, or
physical authority. ARM-295 remains immutable; the next route-physics test must
be a newly numbered, newly pinned, independently reviewed, and separately
authorized increment.

That increment is now ARM-297. Its inert plan and independent reviewer bind the
accepted ARM-296 evidence to the corrected runtime, worker, and backend sources
and reserve fresh, absent attempt/EULA/memory outputs. This advances the
simulation connection without claiming an attempt: the next required layer is
a single-use ARM-297 claimant plus independent review, followed only then by a
fresh exact one-attempt authorization. No simulated typing success or physical
typing success is claimed yet.

The ARM-297 single-use claimant and its independent review are now also
materialized without collecting gates or claiming the attempt. They enforce
exact external authorization, fresh EULA and memory receipts, unchanged source
hashes, one worker delegation, and failure terminalization. The remaining
pre-attempt binding is now materialized and independently accepted. It pins the
merged revision, qualified interpreter, claimant/review evidence, ten runtime
sources, exact authorization text, governed outputs, fresh-gate order, and
terminalization/no-retry behavior.
The executable launcher and its independent review were implemented and
accepted as an inert boundary. The launcher rejected old authorization, wrong
interpreter or repository lineage, changed source/evidence, and non-fresh
outputs before constructing a deferred backend; it delegated exactly once to
the claimant, which retained ownership of fresh gates.

The separately authorized ARM-297 attempt is now terminal and consumed. Both
fresh preflights passed and Isaac loaded the governed USD, but canonical IK row
654 failed the 0.05 rad continuity gate because the raw row-653 boundary was
not on the solver's aligned branch. The retained failure is not a simulated
typing success. Offline reproduction proved the corrected contract:
canonicalize row 653 as initialization, then evaluate rows 654-940 from that
boundary. All 287 governed rows satisfy the unchanged limit, with a 0.04581
rad worst step. The correction must be merged, newly pinned, independently
reviewed, and assigned a fresh lineage before another simulation attempt.

That full-window qualification is now retained as the first ARM-298
checkpoint. The production solver and an independent reproduction both
canonicalized row 653 and passed all 287 governed rows with an identical
canonical-row digest. The maximum adjacent step was `0.045805 rad` at row 670,
below the unchanged `0.05 rad` limit. This is stronger evidence that the
specific ARM-297 failure is corrected, but it remains offline kinematic
evidence—not collision, physics, key-contact, or typing success. The next safe
increment is an inert ARM-298 lineage plan binding this accepted evidence and
fresh absent attempt/preflight outputs; a simulation still requires separate
exact one-use authorization.

That inert ARM-298 lineage plan and independent review are now retained. They
pin the exact continuity evidence, merged correction commit, qualified Isaac
interpreter, 13 production sources, and fresh absent attempt/EULA/memory
outputs. No claimant was constructed and no authorization, simulator, physics,
target, trajectory, contact, hardware, or physical authority was exercised.
The single-use ARM-298 claimant and independent review are now also retained.
They bind the accepted lineage to one fresh-gated worker delegation and prove
that exact authorization, source checks, EULA, memory, exclusive receipt
retention, and single-use consumption occur in order. Building and reviewing
them observed no authorization, claimed no attempt, and started no simulator;
the governed attempt and both live-preflight paths remain absent. The next safe
increment is a reproducible ARM-298 launch binding and executable-launch review
before requesting a fresh exact one-attempt authorization.

That reproducible ARM-298 launch binding and independent review are now
retained. They pin the merged claimant commit, qualified interpreter, exact
claimant/review evidence, all 13 production sources, governed outputs, and the
fresh-gate/terminalization order. They observed no authorization and invoked
nothing. The next safe increment is the import-inert executable launcher and
independent launch review; only after acceptance may a fresh exact ARM-298
one-attempt authorization be requested.

The ARM-298 executable launcher and independent static review are now also
retained. They bind the accepted launch evidence to one fail-closed claimant
delegation and prove that exact authorization, interpreter/ancestry/source
checks, and governed-output absence all precede backend construction. This
work invoked no claimant, simulator, physics, target, contact, hardware, or
physical authority. A fresh exact ARM-298 authorization is still required for
the first corrected route-physics attempt.

That single ARM-298 authorization was subsequently consumed exactly once. Its
fresh EULA and memory preflights passed, but the governed native session
stopped before physics execution because the repository wrapper did not expose
the underlying articulation's valid `set_dof_positions` method. The retained
status is `FAILED_RETAINED_NO_RETRY`; it is not typing success and cannot be
retried or reclassified. The wrapper now delegates that call to the native
Isaac articulation, with focused regression coverage merged in commit
`f84c69dc`.

The next increment is ARM-299. Its import-inert lineage builder and independent
review bind the exact ARM-298 terminal status, merged wrapper correction,
qualified Isaac interpreter, eight runtime sources, and three distinct absent
future outputs. This stage intentionally does not construct a claimant,
observe authorization, import Isaac, step physics, submit a joint position or
target, or consume an attempt. After the lineage is independently retained,
the remaining order is claimant construction and review, reproducible launch
binding and review, executable-launch review, then a new exact one-attempt
ARM-299 authorization. No ARM-299 simulation is authorized by this plan.

The ARM-299 single-use claimant and its independent reviewer are now
implemented as the next guarded layer. The claimant clones the retained
fail-closed worker onto ARM-299's fresh output, rejects the consumed ARM-298
statement and any changed source before gate collection, requires passing EULA
and memory preflights, retains both receipts before marking itself used, and
delegates exactly once. Focused tests exercise that ordering and the actual
worker with a synthetic no-Isaac backend. Building or reviewing the claimant
does not observe authorization, collect live gates, claim an attempt, start
Isaac, step physics, submit positions or targets, contact a key, or grant
hardware or physical authority. A reproducible launch binding and executable
launch review remain required before requesting ARM-299 simulation authority.

The reproducible ARM-299 launch binding and its independent reviewer are now
implemented. They pin the retained claimant/review bytes, qualified Isaac
interpreter, merged claimant commit, all eight runtime sources, fresh-gate
order, single delegation, and terminal-status-before-shutdown policy. Static
review proves the binding is builder-only and contains no simulator, motion,
or transport execution path. This stage still observes no authorization,
collects no live gate, claims no attempt, and starts no simulator. The next
guarded increment is the executable ARM-299 launcher and independent review;
only after that chain is retained should a fresh exact authorization be used.

The executable ARM-299 launcher and independent static reviewer are now
implemented as the next zero-authority layer. The launcher is import-inert and
revalidates the retained binding/review, qualified interpreter, repository
ancestry, claimant bytes, all eight runtime sources, fresh output exclusivity,
and exact future authorization before constructing the deferred backend and
delegating once. The reviewer proves that ordering and rejects retry-capable
loops. Implementing and testing this layer does not collect live gates, claim
or consume ARM-299, start Isaac, step physics, play a trajectory, or authorize
hardware. Its retained review remains required before any exact one-attempt
ARM-299 authorization can be acted upon.

## Governance

- No simulation authorization grants hardware or physical authority.
- No physical setup statement is standing authorization for later movement.
- Exact one-attempt authorizations are single-use and never automatically
  retried or transferred to a replacement request.
- EULA, host readiness, source identity, calibration freshness, and output
  exclusivity are checked before consuming an attempt.
- Unexpected motion, contact, stale feedback, mismatched profiles, or uncertain
  delivery stops the affected sequence and preserves the evidence unchanged.
- Firmware, torque, PID, or controller-configuration changes require their own
  reviewed decision and validation path.

## Related maintained plans

- [ISAAC_SIM_LEARNED_MOTION_GENERATION_PLAN.md](ISAAC_SIM_LEARNED_MOTION_GENERATION_PLAN.md)
  owns the simulation, dataset, policy, and system-identification progression.
- [PRACTICAL_PATH_TO_TYPING_AND_TAPPING.md](PRACTICAL_PATH_TO_TYPING_AND_TAPPING.md)
  retains the broader staged product path.
- [CURRENT_TYPING_AND_TAPPING_GOAL.md](CURRENT_TYPING_AND_TAPPING_GOAL.md)
  retains historical command/servo diagnostic evidence and points here for the
  current durable objective.
