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
