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
ARM-287/ARM-288 corrected and reviewed that lifecycle, and ARM-289 then consumed
one fresh EULA- and memory-gated native `SPACE` authorization. Isaac loaded the
pinned scene and initialized PhysX; runtime construction failed closed because
the articulation adapter did not expose native `link_names`. Unlike ARM-284,
ARM-289 retained the exact terminal failure before shutdown. The immutable
outcomes are documented in
[ARM_284_ATTEMPT_POSTMORTEM.md](ARM_284_ATTEMPT_POSTMORTEM.md) and
[ARM_289_ATTEMPT_POSTMORTEM.md](ARM_289_ATTEMPT_POSTMORTEM.md). The adapter and
integration correction is merged; a zero-motion native confirmation remains
required before another route-physics lineage is justified.

The immediate path is:

1. retain ARM-289 as the consumed terminal failure that exposed the missing
   native link inventory; never replay it;
2. preserve the merged adapter/binding correction and its cross-platform test
   evidence;
3. merge and reproduce the inert ARM-292 exact-inventory request and ARM-293
   independent zero-motion review;
4. execute one separately authorized ARM-294 native inventory diagnostic with
   zero physics steps, retaining success or failure before shutdown;
5. independently review the retained ARM-294 receipt, requiring the exact
   seven-link order, one seven-transform batch, zero motion authority, and an
   absent ARM-295 directory;
6. only after that accepted receipt review, build and independently review an
   inert ARM-295 lineage plan that pins the corrected runtime sources, ARM-289
   terminal evidence, and still-absent attempt/EULA/memory outputs;
7. construct a separately reviewed ARM-295 claimant whose fresh EULA and memory
   gates must pass before it can claim the attempt directory, and require a new
   exact one-use authorization before any simulator launch;
8. diagnose any failed acceptance metric and correct the digital twin or route
   through another reviewed increment rather than replaying the attempt;
9. on a passing result, freeze the single-key simulation benchmark and expand
   to a representative multi-key set;
10. add vision-conditioned localization and rolling-horizon sequence planning;
11. qualify randomized simulation coverage; and
12. design separately authorized physical correlation campaigns only after the
   corresponding simulation gates pass.

ARM-294 has since passed its zero-motion inventory purpose, and ARM-295 was
executed once. ARM-295 passed its fresh launch gates but terminalized before
route evaluation because the concrete binding omitted required canonical IK
inputs. That defect is corrected by deriving the model, frame transform, tool
offset, gripper state, ready pose, bounds, and IK policy from the locked
simulation context. ARM-295 remains immutable; the next route-physics test must
be a newly numbered and independently authorized increment.

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
