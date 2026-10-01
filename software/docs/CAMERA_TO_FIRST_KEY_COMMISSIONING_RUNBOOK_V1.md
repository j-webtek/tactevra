# Camera-to-First-Key Commissioning Runbook V1

## Purpose

This runbook joins the completed PC0-PC18 camera-arrival tooling to the newer
ARM-149-ARM-155 observed-pose and telemetry evidence chain. It is the controlled
path from installing the final fixed camera to reviewing one independently
verified key action.

It does not authorize camera access, controller startup, torque changes,
movement, contact, firmware installation, or automatic retry. Each physical
operation still requires its own bounded authorization and stop conditions.

The machine-readable companion is
`software/config/camera_to_first_key_fixture_replacement_v1.json`. It identifies
exactly which current fixture each physical result must replace. Never relabel a
fixture, photograph estimate, replay, or model prediction as physical evidence.

## Configuration freeze

Before collecting evidence, freeze and identify:

- camera, lens, housing, mount, controls, and cable routing;
- board, arm base, keyboard, fixtures, and lighting;
- bare gripper or installed tool geometry;
- software build, model build, target catalog, and controller identity;
- configuration epoch and external evidence roots.

Witness-mark rigid components. Any later movement, focus/crop/control drift,
tool change, cable reroute, controller restart, or software/configuration change
invalidates the dependent evidence. Start a new epoch rather than repairing the
old record.

## Phase 1 — Camera-arrival originals

Follow [Camera Arrival-Day Checklist V1](CAMERA_ARRIVAL_DAY_CHECKLIST_V1.md).
Collect the 15 physical originals and their immutable sidecars, route them to
the native consumers, retain every pass or blocker, and run the existing
commissioning orchestrator.

Required result:

```text
schema: rocell.camera_arrival_commissioning_orchestrator.v1
status: COMPLETE_FOR_OFFLINE_REVIEW
```

This result is structural and offline. It does not install qualification.

## Phase 2 — Measured epoch and localization

1. Bind the camera/support, board, base, keyboard, tool, controls, intrinsics,
   distortion, and transforms into one measured configuration epoch.
2. Keep calibration and held-out localization captures disjoint.
3. Include normal lighting, glare, blur, partial obstruction, and arm occlusion.
4. Use independently surveyed target truth; model predictions cannot label
   their own accuracy.
5. Retain uncertainty and abstention results, not just average error.

The physical localization evaluator may recommend qualification. Installation
still requires owner review and an epoch-bound registry update outside this
runbook.

## Phase 3 — Installed collision geometry

Replace the accepted-measured-class fixtures with reviewed installed evidence
for the arm, base, board, camera/support, keyboard, gripper/tool, nearby
fixtures, and cables. Capture cable envelopes throughout the allowed posture
domain. Record uncertainty, clearance policy, and every accepted global pair
exclusion.

Incomplete geometry is a blocker. Do not compensate for missing geometry by
increasing a software margin or moving faster through an unmeasured region.

## Phase 4 — Read-only observed pose

With the arm stationary and the movement area clear:

1. authenticate the exact build, calibration, epoch, controller identity, and
   controller session;
2. acquire a fresh read-only joint state;
3. take the bounded repeated snapshots required by the observed-state intake;
4. reject disagreement, restart, stale data, partial joints, or crossed session;
5. materialize ARM-149 and the bounded observed-to-PARK entry envelope.

No inferred photo pose substitutes for controller feedback. No movement occurs
in this phase.

## Phase 5 — Offline observed-entry qualification

Using the exact retained read-only state:

1. ARM-150 materializes bounded joint samples from observed pose to PARK.
2. ARM-151 checks every discrete sample against installed geometry.
3. ARM-152 checks conservative envelopes between adjacent samples.
4. ARM-153 time-scales the route against installed velocity, acceleration,
   jerk, cadence, and settling limits.

The result remains an offline plan. A clear schedule is not proof that the
controller will track it.

## Phase 6 — One bounded non-contact qualification

Only after a separate explicit physical authorization:

1. choose the lowest qualified speed class;
2. keep the bare gripper above the keyboard with a declared clearance;
3. execute one observed-to-PARK/non-contact target sequence without retry;
4. retain raw controller feedback and independent visual evidence;
5. stop on any unexpected direction, sound, cable motion, tracking deviation,
   telemetry gap, restart, or identity change;
6. do not automatically return after uncertainty.

ARM-154 must bind feedback to every scheduled sample and a dwell-spanning
endpoint settling window. ARM-155 must cover the exact motion interval with a
qualified maximum telemetry gap and bounded interpolated residuals. Neither
result proves behavior between samples.

## Phase 7 — One independently verified key

Contact is a new authorization and evidence class. Before contact, separately
qualify the tool/TCP, approach clearance, contact depth/force surrogate,
retract, keyboard support, and independent device observer.

Execute exactly one key action with no retry. Completion requires independent
evidence that:

- the intended key registered exactly once;
- no neighboring key registered;
- the input did not repeat;
- the arm retracted and settled as planned; and
- controller feedback, visual evidence, and device effect share the exact
  request, build, epoch, and session lineage.

A motion that looks correct without confirmed device effect is unverified.

## Phase 8 — Expansion

Expand only in this order:

1. repeated presses of the same key;
2. two separated letter keys;
3. one digit and one punctuation key;
4. a short held-out string;
5. broader keyboard coverage; and
6. speed optimization after correctness and recovery thresholds pass.

Each expansion uses held-out targets and retains failures. Do not tune on the
same captures or routes used for final qualification.

## Stop conditions

Stop and retain evidence if any of the following occurs:

- physical component, cable route, focus, crop, exposure, or controls change;
- software build, calibration, epoch, controller identity, or session differs;
- camera or telemetry timestamps are missing, non-monotonic, stale, or gapped;
- uncertainty exceeds the applicable safe target region;
- collision evidence, dynamics limits, or settling policy is incomplete;
- actual movement differs from planned direction or magnitude;
- a transport outcome is partial or uncertain;
- the intended device effect cannot be independently confirmed; or
- any workflow proposes an implicit retry, return, or torque release.

## Completion meaning

Replacing all ten registry stages with accepted physical evidence means the
system is ready for owner commissioning review of one action. It does not by
itself authorize general typing, continuous operation, autonomous retry, or
production deployment.
