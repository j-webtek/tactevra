# Physical measurement plan

> **Measurement plan only — no motion authority**
>
> This document orders the measurements needed to replace exploratory ranges.
> It does not authorize energizing the arm, writing hardware, issuing a command,
> opening a transport, or performing a physical test. Each powered procedure
> requires its own reviewed preflight and explicit approval.

## Ordering rule

Measurements are ordered by how many simulation decisions they constrain and
how strongly they reduce uncertainty. Raw observations and failed trials remain
preserved. A measured artifact replaces a simulation range only after its
method, instrument identity, units, timestamps, configuration identity, raw
data hashes, and uncertainty calculation are recorded.

## Session 0 — measurements with arm power disconnected

This session precedes every powered stage. Disconnect and verify absence of
actuator power, mechanically support the arm against sag, and keep every arm
controller transport closed. Photograph the isolation state and record the
meter, operator, observer, tool, fixtures, and configuration hashes.

### 0.1 Landing-sensor noise and bias

1. Fasten the touch surface in the commissioning tray and mark a reproducible
   center plus edge/corner check points.
2. Clamp the passive stylus in a separate rigid bench fixture so the arm carries
   no load and cannot move it. Set the stylus vertically on the marked point.
3. Log a static coordinate burst without moving the stylus. Preserve missing,
   duplicated, and outlier reports.
4. Lift and replace the stylus with the bench fixture, then collect repeated
   manual taps at every marked point using a controlled stop. Do not use the arm.
5. Estimate random noise, spatial bias, repeatability, dropout rate, and drift
   separately. Keep at least one marked-point set untouched for confirmation.

Instrument: commissioning touch surface or phone coordinate readback, rigid
stylus fixture, marked dimensional overlay, synchronized host clock. This
replaces the WS5 landing-observation-noise range and sets the touch-observer
threshold; it does not qualify arm landing.

### 0.2 Fingertip dimensions and compliant-tool behavior

1. Measure tip radius/diameter at multiple orientations and tool length from the
   controlled mounting reference.
2. Measure collar/body dimensions and the installed axial transform.
3. In a separate load fixture, apply recorded forces across the intended range
   and measure displacement during loading and unloading.
4. Report stiffness, hysteresis, permanent set, and measurement uncertainty as
   ranges. Retain every trial.

Instrument: calibrated calipers or micrometer, force gauge, displacement
indicator, rigid load fixture. This replaces the nominal 110 mm/3 mm geometry
and synthetic series-compliance range.

### 0.3 Key travel, actuation, force, and return

1. Keep the keyboard disconnected from the arm and fixed in its station.
2. Use a manual instrumented stand to lower the measured tip onto representative
   ordinary and stabilized keys.
3. Record displacement and force at first contact, switch closure, bottom-out,
   release, and reset. Record hysteresis and off-center behavior.
4. With the keyboard connected only to the logging host, measure debounce,
   minimum reliable closure, and auto-repeat timing without arm motion.

Instrument: manual displacement stand, force gauge, logic analyzer or host event
logger. This replaces WS2 key travel, spring/force, debounce, bottom-out, return,
and repeat-delay ranges.

### 0.4 Keycap, board, and fixture geometry

1. Measure the board outline and fixed reference features.
2. Measure each keycap top size, height, pitch, row offset, and center relative
   to the board references, including `GRAVE`, `EQUAL`, `Z`, and `SHIFT`.
3. Measure station, tray, touch-surface, and locating-feature geometry and their
   repeatable installed transforms.
4. Produce a candidate installed catalog and collision-profile amendment; do
   not install either until independent review.

Instrument: calipers, steel rule, height gauge, gauge blocks, and the controlled
CAD revisions. This replaces nominal key boxes, safe-region assumptions, station
placement, tray placement, and candidate board transforms.

### 0.5 Passive force-metrology worksheet

This worksheet resolves the measurement dependency retained by
`E-20261009-SIM-WS2-STIFFNESS-SCALED-007`. It creates raw bench evidence only.
It does not set a force ceiling, select a press recipe, or authorize arm power.

#### Preconditions and instrument record

1. Disconnect arm actuator power and keep controller, serial, USB-servo, and
   network controller transports closed. Mechanically support the arm away from
   the bench setup.
2. Record the keyboard identity, tool revision, compliant-element revision,
   scale identity and resolution, caliper identity and resolution, host key
   logger identity, operator, date/time, and ambient notes.
3. Verify the unloaded scale returns to zero before and after each measurement
   group. Preserve drift, overload, unstable, and repeated readings rather than
   replacing them.
4. If the scale reports mass, preserve that raw reading and derive force using
   `force_N = mass_g * 0.00980665`. Never overwrite the mass column with the
   derived force.

#### A. Tool force, compression, hysteresis, and end stop

1. Install the exact tool and compliant element in a rigid vertical bench
   fixture. Record the unloaded reference length from the controlled mounting
   reference to the tool tip.
2. Place the tip perpendicular to the center of the tared scale. Increase
   compression in small monotonic steps, collecting at least eight nonzero
   points before the end stop when the available travel permits it.
3. At every point record raw scale reading, loaded tool length, calculated
   compression, derived force, and whether the end stop appears engaged.
4. Unload through the same approximate compression points. Repeat the complete
   loading/unloading sweep at least three times without discarding variation.
5. Continue only within the tool and scale limits until added load no longer
   produces resolvable additional compression. Record that transition as the
   observed end-stop interval; do not assign one exact value when instrument
   resolution supports only a range.
6. After full unloading, record permanent set. Report the loading curve,
   unloading curve, local stiffness between adjacent points, hysteresis,
   repeatability, compliant-travel interval, and end-stop interval with units
   and instrument-resolution uncertainty.

Raw columns:

`trial_id, direction, raw_mass_g, derived_force_N, unloaded_length_mm, loaded_length_mm, compression_mm, end_stop_observed, stable_reading, notes`

#### B. Keyboard actuation, bottom-out, and return force

1. Place the identified keyboard and its rigid support on the scale, connect
   the keyboard only to the logging host, and tare the complete stationary
   assembly. The arm remains isolated and unpowered.
2. Use the measured tool in the vertical manual fixture. Test at least `GRAVE`,
   `EQUAL`, one representative ordinary key, and the stabilized `SPACE` key.
   Record additional stabilized keys such as `ENTER` and `SHIFT` when the fixture
   can reach them without changing the measurement method.
3. For each key, approach slowly at the declared press point. Record scale and
   displacement at first contact, the first host-accepted key event, mechanical
   bottom-out, release/reset, and full return. Preserve missed, double, wrong-key,
   unstable, and no-return trials.
4. Repeat at least five complete loading/unloading trials per key. Repeat any
   deliberately off-center test as a separate labeled population rather than
   mixing it with center-press results.
5. Report per-key and mechanism-class ranges for actuation force, bottom-out
   force, actuation travel, total travel, reset force/travel, hysteresis, host
   event latency when observable, and repeatability. Ordinary and stabilized
   keys remain separate.

Raw columns:

`trial_id, key_id, mechanism_class, press_point, raw_mass_g, derived_force_N, displacement_mm, event_type, host_timestamp, bottom_out_observed, returned, notes`

#### C. Servo datasheet load calculation

1. Preserve the exact servo manufacturer, model, voltage, rated torque, stall
   torque, duty assumptions, and source-document revision. Rated and stall
   torque are separate fields.
2. Record the simulated pose and tool-tip force direction used for the
   conversion. Use the arm Jacobian for the pose: `tau = J_transpose * F`.
   For a one-joint sanity check only, `force_N = torque_Nm / perpendicular_arm_m`.
3. Compute the force at which each joint reaches rated torque and separately
   report the force corresponding to stall torque. The minimum joint-limited
   value is the pose-specific bound.
4. Do not treat stall torque as an allowable continuous contact load. Leave the
   operating derating factor and physical contact-load gate unset pending arm
   runtime review and later powered confirmation.

Recorded fields:

`servo_id, model, voltage_V, rated_torque_Nm, stall_torque_Nm, source_hash, pose_id, force_direction, jacobian_hash, rated_force_N, stall_force_N, derating_factor_unset`

#### Admission boundary

Hash-bind the raw tables, photographs, instrument record, derivation script,
and derived report. The simulation fixture may be amended only after an
independent review confirms units, tare handling, tool/keyboard identities,
uncertainty, repeat counts, and end-stop classification. A failed or incomplete
measurement remains evidence and does not authorize replacing the provisional
simulation inputs.

Session 0 passes only when all four raw datasets and manifests are hash-bound,
the arm remained unpowered, hardware writes and physical movements are zero,
and no unexplained discrepancy was discarded. A failure blocks Stage A.

| Priority | Measurement | Method | Instrument or evidence source | Simulation result or range replaced |
|---:|---|---|---|---|
| 1 | Landing-sensor noise and bias | Record repeated static landings and no-contact observations across the sensor area; estimate repeatability, spatial bias, missing reports, and drift without fitting on the held-out check positions. | Commissioning touch pad or phone touchscreen with raw ADB-style coordinate/readback log; rigid placement fixture; dimensional reference. | WS5 landing-observation noise range, touch-surface observer threshold, per-key correction sample count, and commissioning-time spread. |
| 2 | Servo repeatability, backlash, and settling | From reviewed interior poses, approach from both directions, return repeatedly, and compare measured joint telemetry plus independent pose observations. Separate random repeatability, direction-dependent backlash, constant offset, and settling time. | Controller measured-position telemetry; overhead calibrated camera or independent metrology target; timestamped acquisition clock. | MuJoCo random-joint-noise, backlash, residual-correction, settling, and telemetry-envelope ranges; open-loop landing feasibility map. |
| 3 | Fingertip geometry and compliant-tool stiffness | Measure radius and installed transform; load the tool through the expected force range and record deflection and hysteresis in both loading directions. | Calipers or micrometer; force gauge; displacement indicator; printed-tool revision identity. | 3 mm nominal tip assumption, series compliance range, commanded-depth versus key-travel model, and keyboard-versus-phone shared-tip analysis. |
| 4 | Key travel, actuation, return, force, debounce, and repeat timing | Instrument representative ordinary and stabilized keys; sweep depth and dwell only under a separately approved benchtop method; record switch closure, reset, bottom-out, and repeat timing. | Displacement indicator, force gauge, logic analyzer or host key-event timestamps, keyboard identity. | WS2 prismatic-key spring/travel/force ranges, minimum 30 ms conservative closure rule, release window, bottom-out limit, and auto-repeat range. |
| 5 | Installed robot and fixture geometry | Measure link reference dimensions, joint-zero references, base-to-board transform, 110 mm tool transform, keyboard/phone/tray placement, station placement, and clearances. | Calipers, steel rule, gauge blocks, ChArUco/AprilTag targets, controlled CAD revision, fixture locating features. | Candidate collision profile, shared-URDF physical accuracy gap, station CAD placement, tray replacement alignment, and the consolidated 27 mm/6 mm candidate clearances. |
| 6 | Camera intrinsics, extrinsics, focus, and distortion | Calibrate in the exact runtime resolution, sensor mode, focus, exposure, and white-balance settings using views across the image and held-out reprojection checks. | B0477 camera, measured ChArUco board, calipers for printed scale, direct USB port and production cable. | Synthetic nadir camera family, camera-to-board transform, silhouette projection, localization-error budget, and camera-clear park evidence. |
| 7 | Camera noise and admitted lighting drift | Capture repeated static frames at each locked exposure/gain and commissioned lighting level; estimate per-pixel luminance/chroma noise and the lighting envelope before opening held-out obstruction captures. | B0477 in runtime YUY2 mode, controlled light meter if available, timestamped raw frame capture. | Assumed sensor-noise profiles, YUY2 detectability floor, reference-validity lighting threshold, and future lossless-corpus load-time camera model. |
| 8 | Controller timing and feedback semantics | Measure command admission latency, telemetry capture time, sample cadence, dropped/delayed frames, overload signals, and whether positions are measured rather than echoed commands. | Controller logs, logic analyzer or synchronized host clock, read-only protocol capture. | Synthetic command latency, response constant, telemetry noise/freshness, and six predicted first-motion envelopes. |
| 9 | Phone capacitive registration | With the arm isolated, use controlled conductive coupons at the declared radii and contact areas; record tap registration, coordinates, duration, long-press transition, and screen state with autocorrect/prediction disabled. | Phone, ADB-style screen/event readback, conductive radius coupons, force/displacement fixture. | Analytic 3 mm contact-area boundary of 7.07–28.27 square mm and the unresolved one-tip-versus-two-tip decision. |
| 10 | Park repeatability and unpowered sag | Repeatedly establish the candidate parked pose under an approved procedure, then compare powered settled and isolated positions and silhouettes. | Measured joint telemetry, calibrated overhead camera, fixed silhouette reference. | `halton-0573` synthetic identity, park freshness tolerance, and observation-pose repeatability range. |
| 11 | Fixture and calibration drift rate | Repeat board, tool, camera, and landing checks over time and after controlled non-operating disturbances; estimate drift by configuration epoch. | Same instruments used for priorities 1, 3, 5, and 6; environmental log. | WS5 one-to-300-hour exploratory recalibration interval and reference-expiration policy. |
| 12 | Emergency stop and power-loss behavior | Under a dedicated approved safety procedure, verify isolation time, controller state, gravity sag, restart behavior, and evidence retention. | E-stop/power-isolation hardware, controller logs, independent video/pose observation. | Synthetic ESTOP and POWER_INTERRUPTION faults. This measurement is required for readiness but does not tune a motion model. |

## Measurement artifacts

Each completed measurement produces one manifest with:

- exact configuration and instrument serial or stable identity;
- calibration certificates or checks available for the instrument;
- exact procedure revision and operator-recorded deviations;
- raw data hashes plus a separate derived-result hash;
- units, sample count, uncertainty interval, exclusions, and failed samples;
- the simulation fixture section it replaces;
- hardware-write and physical-movement counts;
- an explicit statement of whether the result is exploratory, commissioned, or
  qualifying.

Landing-sensor noise and servo repeatability come first because together they
control calibration time, landing accuracy, observer sensitivity, and whether
the current 3 mm effective landing half-width is practical. Camera and contact
measurements follow in parallel where they do not require arm motion.
