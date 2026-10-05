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
