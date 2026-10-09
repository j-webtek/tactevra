# Geometry-first localization and contact architecture

## Decision

The primary source of keyboard and phone target coordinates will be the
observed pose of the mechanically registered fixture plus a frozen measured
target catalog. AprilTag pose estimation establishes the board or fixture pose;
the catalog supplies target offsets in that frame. The retained learned
localizer does not silently adjust those coordinates. It remains useful as a
scene consistency and obstruction monitor that can force abstention.

This decision follows the retained model study's 14.400834977 mm conservative
planar bound. That bound is several times larger than the approximate 4 mm
landing budget exercised in simulation and therefore cannot support contact
admission.

```text
captured frame
  -> existing AprilTag detector and planar pose estimator
  -> hash-bound camera_T_board observation
  + frozen board-frame target catalog
  -> fiducial/catalog precision observation
  -> precision fusion and ModelMotionBatchV2 (later increment)

learned vision
  -> scene consistency / obstruction result
  -> may abstain
  -> may not move target coordinates or grant motion authority
```

## AI-555 adapter boundary

`fiducial_catalog_precision_v1` consumes the existing typed
`AprilTagPoseObservation` and `NominalTargetCatalog`. It binds the exact frame,
camera settings, detector, estimator, intrinsics, tag map, board-frame
definition, catalog, target order, fit diagnostics, qualification, and
freshness policy. It abstains when no qualification is installed or when any
identity or bound is inapplicable.

The initial qualification schema permits `SYNTHETIC_OFFLINE_ONLY` evidence.
The nominal catalog is explicitly simulation-only. A measured physical catalog
and a held-out physical fiducial qualification require a new reviewed schema;
neither can be created by relabeling this record. The adapter emits no joints,
servo values, controller JSON, transport data, permit, command, or physical
authority.

## Independent physical reference

The configuration freeze selects **caliper survey from the commissioning
tray's locating pins or machined datum edges to the top edges of each keycap**
as the primary independent reference instrument. Each target center is derived
from repeated left/right and front/rear edge measurements. The survey record
must include the caliper identity, calibration check, datum definition,
operator, repeated readings, derived center, spread, source photographs, and
hashes. A printed alignment overlay may be used as a secondary gross-error
check but is not the qualifying reference.

This method is independent of the camera and fiducial estimator being tested.
The held-out localization evaluation will compare fiducial-plus-catalog target
centers against these surveyed centers, with calibration and evaluation
captures kept separate.

## Event-terminated press successor

The retained exploratory WS2 fixed-depth recipe has a worst-case two-sided
depth margin of about 0.040832 mm. The next WS2 campaign will evaluate an
event-terminated press:

1. an already admitted trajectory descends slowly through the expected
   actuation interval;
2. a host keystroke event may end the press early after the required debounce
   hold, causing retraction;
3. measured tool compression or servo load may be evaluated as a secondary
   stop signal;
4. hard depth, force, and time limits remain unchanged bottom-out guards; and
5. absent, late, or contradictory verification can never start, deepen,
   extend, retry, or redirect motion.

The event therefore has only safe-direction authority: it may shorten an
already authorized press by causing retraction. Event latency and timestamp
quality must be measured during hover/contact commissioning before this can be
qualified. Until then, the fixed-depth recipe remains simulation evidence and
the event-terminated rule remains a predeclared successor experiment.

## Next gates

1. Produce a measured target catalog from the caliper survey.
2. Install camera intrinsics, tag map, fixed camera settings, and board-frame
   definition.
3. Capture separate fiducial calibration and held-out evaluation datasets.
4. Propose the physical qualification schema with coverage, conservative
   planar error, per-target failures, and abstentions.
5. Connect an admitted fiducial/catalog observation to the existing precision
   fusion and `ModelMotionBatchV2` producer in a later bounded increment.
6. Run the predeclared event-terminated WS2 comparison without changing the
   current fixed-depth evidence.
