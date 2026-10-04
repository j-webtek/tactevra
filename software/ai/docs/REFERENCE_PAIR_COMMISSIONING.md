# Reference-pair commissioning and validity

The residual-obstruction model compares a current parked-pose target crop with
a retained clear reference from the same physical camera, fixture, target map,
and camera pose. A reference is evidence, not a model output. Missing or invalid
reference evidence yields `ABSTAIN` before a residual score is used.

## Freshness binding

Every commissioned reference records:

- reference and target identity;
- capture timestamp and an owner-approved maximum age;
- camera calibration SHA-256;
- fixture-pose SHA-256, covering keyboard and phone placement;
- target-map SHA-256;
- luminance, red/green ratio, and blue/green ratio at capture;
- an owner-approved maximum relative lighting drift.

`rocell_ai.reference_validity.evaluate_reference_validity` compares those fields
with the current frame. It returns `ABSTAIN` if the camera calibration, fixture
pose, or target map changed; the reference is older than its configured limit;
or measured lighting drift exceeds its configured limit. Camera bumps and device
movement are represented by new calibration or fixture-pose evidence, rather
than inferred by the residual model.

The age and lighting limits are commissioning-profile inputs. The smoke does
not choose deployment values. Reference validity joins frame and telemetry
freshness as a prerequisite for perception admission; it creates no command,
motion, permit, transport, or physical authority.

## First physical reference-pair collection

Collect this bounded set when the final camera and ChArUco procedure are ready:

1. Park the arm at the commissioned observation pose and record measured pose
   telemetry synchronized to each frame.
2. Capture the ChArUco board, camera calibration identity, fixture pose, target
   map identity, and lighting descriptor.
3. Capture at least one clear reference for every target intended for the first
   milestone. Retain original images and hashes.
4. Without changing the camera or fixture, capture paired observations with a
   dark cable, translucent cable, and hand crossing each selected safe region,
   plus clear repeats.
5. Repeat clear captures under the measured low, nominal, and high lighting
   envelope. Do not synthesize physical-original evidence.
6. Run the same reference-validity check and the frozen residual preprocessing
   variants. Report results as a sim-to-real diagnostic until a separately
   reviewed physical qualification passes.

The first collection should prioritize one keyboard cluster including `G` and
one phone-key cluster. It must retain failures and original bytes. A successful
small collection does not qualify all 75 targets or authorize execution.

### Camera-calibration readiness

The production calibration contract currently requires the intended Arducam
B0477 at its native 5472 by 3648 YUY2 mode at 9 fps and a rigidly backed 12 by
9 ChArUco board using `DICT_5X5_1000`, 30 mm squares, and 22 mm markers. The
older retained 5 by 7, 25/17.5 mm `DICT_5X5_100` board is useful for an OpenCV
tooling smoke only and must not be used to create production calibration.

Before physical capture, verify the camera's persistent identity and exact mode,
retain the production board asset, measure its printed square and marker scale,
and verify rigid backing. Capture 24 training views and 8 held-out views across
angles and positions, including image corners and edges where distortion is
strongest. Report training and held-out reprojection separately. Approximately
0.5 pixel reprojection error is a diagnostic target for this setup, not a
deployment threshold or automatic qualification decision.

Calibrate and operate in that exact full-native mode. Any lower-resolution,
MJPG, cropped, binned, or scaled mode requires a separate calibration unless
its sensor transform is measured and reviewed. Fix the manual focus and aperture
and disable autofocus, auto exposure, and auto white balance before calibration.
Retain the focus/aperture witness, exposure, gain, white-balance, controls
snapshot, and a hash binding those settings. Lighting measurements use the same
locked controls.

Verify print scale with calibrated calipers using at least four distributed
horizontal and four distributed vertical measurements, including opposite board
extents. Retain every raw measurement and the instrument identity. The allowed
axis-scale error remains unset until physical measurements are reviewed.

The current read-only probe is retained in
`physical_charuco_probe_blocked_v1.json`. It found no connected Windows Camera
or Image-class device. Its zero-capture result is a blocked readiness receipt,
not camera calibration evidence.

## Residual v4.2 remedy pilot

Residual v4.2 remains rejected. Its cable rows remain part of the required
detection scope. The commissioning rule that prohibits cable routing across an
interaction surface reduces the expected frequency of a cable obstruction; it
does not allow scoring without cables and does not replace the detector as the
backstop for a cable that slips, is dropped, or is routed incorrectly.

Before a v5 design is selected, collect the bounded pilot frozen in
`residual_obstruction_v4_2_remedy_classification_v1.json`. It covers the
keyboard `EQUAL/F/G/H/I` region and phone `key_a/key_b/key_c/key_period`, across
at least three sessions. Each session retains clear reference and repeat images,
dark and translucent cable images, and a hand image. E-529 amends the pending
coverage schedule before capture: 10% is clearly visible, 20% is an explicit
boundary probe, and 30% and 60% are clearly obstructed. The 20% rows accept
either decision in the primary pilot metric but remain retained, separately
reported, and scored under strict visible and strict abstain counterfactuals.
Every image retains its original bytes, reference and observation hashes,
ChArUco/fixture identities, settled park evidence, and luminance, red/green,
and blue/green descriptors.

Real coverage requires both a measured placement template and an independently
hand-annotated obstruction mask against the hash-bound target safe region. The
annotator remains blind to the model score. More than 5 percentage points of
absolute disagreement yields `LABEL_UNRESOLVED`; that row is retained and
reported but cannot enter a model metric. Target-center coverage forces an
abstain label.

Sessions `physical_pilot_measurement_01` and
`physical_pilot_measurement_02` may inform remedy selection but may not train a
model. `physical_pilot_escrow_01` is fixed before capture and its pixels remain
unopened until a candidate representation, checkpoint, and threshold are
frozen. It cannot select a remedy or train a model. Any real training data
requires a separate later collection.

The arm is de-energized for every capture. Servo power isolation and controller
channel disconnection are verified before entry into the work envelope. The
park pose is established before the capture phase, which performs zero robot
movements and zero hardware writes. An energized row is retained as invalid and
cannot be used, with the hand cases requiring explicit energy-isolation proof.

Because an unpowered arm can sag, pre-isolation pose evidence is insufficient.
After power isolation, bind the actual settled capture pose by comparing at
least two stable frames with the commissioned park silhouette. The allowed
silhouette deviation comes from the commissioned park profile and remains unset
until that profile exists. Passive measured joint feedback may be retained as a
secondary check; commanded joint state is prohibited. Refresh this evidence
before each capture group, bracket it at session end, and bind every image to
the applicable pose-evidence SHA-256. A failed check or manual reposition during
the capture phase makes the row invalid, retained, and unusable.

The single `physical_pilot_escrow_01` session is a real-world sanity check only.
It is not a statistical gate and cannot support a 2% miss-rate or deployment
claim. A future powered real evaluation requires a separately authorized,
statistically planned, and newly captured campaign; the pilot escrow cannot be
reused as that evaluation.

The physical observations determine which remedy is tested first. Edge or
texture difference channels are first because they directly address the
low-contrast cable boundary. Higher target-context resolution is second because
it tests whether thin cables occupy too few pixels at 96 by 96. Dark-obstructor
weighting is third because it can exchange fewer misses for more false stops.
Each option must be compared with the unchanged RGB-difference baseline.

The maximum admitted relative lighting drift remains unset until the low,
nominal, and high real-camera samples are measured. A successor's training and
test lighting mismatch must fit the same measured envelope admitted by runtime
reference validity. Values outside that envelope remain an upstream abstention
condition and cannot be used to relax the detector's frozen gates.

### Delivered-frame sensor-noise measurement

The B0477 pilot also measures the noise floor of the frames the model will
actually receive. At each measured low, nominal, and high lighting condition,
hold the clear scene, camera, fixture, device, settled parked pose, focus,
exposure, gain, and white balance fixed. Discard eight settling frames, then
retain one continuous burst of 32 full-native 5472 by 3648 YUY2 frames. Preserve
the original delivered bytes, hashes, monotonic timestamps, available driver
sequence or timestamps, dropped-frame counts, duplicate-byte counts, locked
control snapshot, lighting descriptor, and applicable pose-evidence hash.

Compute per-pixel temporal mean, sample standard deviation, median, and robust
sigma (`1.4826 × MAD`) separately for delivered Y, U, and V. Retain spatial
noise maps, empirical temporal residuals, adjacent-frame-difference summaries,
and median/q95/q99/maximum aggregates. Report clipped and saturated pixels
separately. Do not assume Gaussian, independent, or spatially uniform noise
before the measurements exist.

The next synthetic camera pipeline starts from a lossless render, has no JPEG
intermediate, and produces simulated delivered YUY2 4:2:2 input using the
measured profile. Empirical residual resampling is preferred because it can
retain spatial and chroma dependence; a fitted distribution requires a held-out
goodness-of-fit check. The profile is bound to the exact camera mode, controls,
lighting condition, port, and cable and expires when any of those bindings
change.

No numerical signal floor or noise multiplier is selected now. After capture,
obstruction signal is compared with the matching-lighting measured noise, and
any minimum-detectable-signal rule must be frozen in a new pre-results
amendment. A synthetic pass using measured noise remains simulation evidence,
not physical qualification. This amendment does not turn raw pilot pixels into
training data or alter the escrow rules.

## Current synthetic smoke finding

The bounded `F/G/H/I` Isaac smoke retained both independent self-crop and
reference-context normalization channels. Independent self-crop normalization
had the higher pooled label-ranking AUC (`0.8038194444` versus `0.7743055556`)
on 192 training observations. This is too small to select preprocessing. Both
channels remain candidates for the fresh v4.1 development campaign, and
evaluation pixels remain absent.
