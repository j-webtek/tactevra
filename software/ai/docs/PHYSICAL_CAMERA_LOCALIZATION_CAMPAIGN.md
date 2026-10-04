# Physical-camera localization qualification campaign

**Stage:** AI S2/S3 preparation

**State:** ready for data collection after physical commissioning inputs exist

**Authority:** read-only evidence preparation; no camera, controller, or movement authority

This runbook freezes what must be collected when the final overhead camera is
mounted and calibrated. It connects the arm lane's existing camera onboarding
records to the AI lane's held-out localization evaluation without treating a
camera image, model prediction, or synthetic label as calibration evidence.

## Start gate

Do not collect a qualification campaign until all of these are retained:

1. The four ARM-070 physical-original bindings are accepted:
   `camera_receipt`, `camera_identity`, `camera_mode_controls`, and
   `support_witnesses`.
2. The camera mount, arm base, board, keyboard, tool, cabling, optics, focus,
   exposure, gain, white balance, resolution, and pixel format are frozen as
   one configuration epoch.
   The current repository-authoritative B0477 mode is full-native 5472 by 3648
   YUY2 at 9 fps. A lower-resolution, MJPG, cropped, binned, or scaled mode needs
   its own calibration unless the sensor transform is measured and reviewed.
   Manual focus and aperture are fixed; autofocus, auto exposure, and auto white
   balance are disabled; exposure, gain, and white balance are locked and hash
   bound before calibration or lighting measurement.
3. Camera intrinsics, camera-to-board, keyboard-to-board, board-to-robot, and
   tool/TCP calibration artifacts have exact identities and current validation
   evidence.
4. The keyboard target map and model external-artifact manifest are pinned by
   SHA-256.
5. The arm is disabled or held outside the capture volume. Data collection is
   camera-only and may not be combined with a motion test.
6. The rigid 12 by 9 board's 30 mm squares and 22 mm markers are physically
   verified using calibrated calipers. Retain at least four distributed
   horizontal and four distributed vertical measurements, including opposite
   extents, with raw values and instrument identity. The axis-error tolerance
   remains unset until those physical measurements are reviewed.

The repository preflight does not open the camera. Authorized commissioning
software must create the physical originals and image files separately.

## Campaign layout

Keep bulk images and per-frame truth outside Git. A campaign JSON file conforming
to
[`physical_camera_localization_campaign_v1.schema.json`](../schemas/physical_camera_localization_campaign_v1.schema.json)
binds their relative paths, sizes, and SHA-256 identities.

```text
physical-camera-campaign/
  campaign.json
  images/
    calibration-*.png
    evaluation-*.png
  truth/
    calibration-*.json
    evaluation-*.json
  receipts/
```

Every ground-truth record must come from independently surveyed fiducial
geometry. Model predictions, nominal drawing rectangles, and hand-adjusted
predictions are not ground truth.

## Split and condition rules

- Collect at least 300 calibration captures and 300 held-out evaluation
  captures.
- Use disjoint capture sessions for the two splits. Reboot/reopen the capture
  service and repeat placement variation before starting held-out collection.
- Retain at least 20 held-out captures for each required condition:
  nominal, low light, high light, glare, blur, arm occlusion, tool occlusion,
  cable occlusion, placement translation, placement yaw, and device absent.
- Preserve every failed, blurred, obstructed, or absent-device original. Do not
  delete difficult frames after looking at model output.
- Record one immutable camera identity, mode-controls identity, and configuration
  epoch across the campaign. Drift ends the campaign and requires a new ID.
- Give every image and ground-truth record a unique SHA-256 identity.

The 300-frame held-out floor supports a one-sided 95% binomial lower bound near
0.99 only when there are no uncovered cases. Correlated frames can still make
that estimate optimistic, so session, placement, lighting, and obstruction
diversity remain mandatory.

## Preflight

From the repository root, after the external evidence directory exists:

```powershell
python software/ai/eval/preflight_physical_camera_campaign.py `
  --campaign D:\tactevra-evidence\physical-camera-campaign\campaign.json `
  --evidence-root D:\tactevra-evidence\physical-camera-campaign `
  --output D:\tactevra-evidence\physical-camera-campaign\receipts\preflight.json
```

`READY_FOR_OFFLINE_EVALUATION` means only that the manifest is strict, retained
files match their declared identities, capture/session identities do not cross
splits, and required condition counts exist. The receipt always records zero
camera opens, model loads, controller starts, hardware writes, and movements.
Receipt consumers validate it against
[`physical_camera_localization_preflight_receipt_v1.schema.json`](../schemas/physical_camera_localization_preflight_receipt_v1.schema.json).

## Evaluation and acceptance

After preflight passes:

1. Freeze the model, preprocessing, target catalog, and evaluation code before
   examining held-out outputs.
2. Use only the calibration split to select the uncertainty method and bound.
3. Run the frozen method once on the held-out split.
4. Report per-condition and per-target mean, p95, maximum error, abstentions,
   uncovered cases, and exact failure IDs.
5. Treat `device_absent` and unsafe obstruction cases as abstention tests, not
   coordinate-accuracy successes.
6. Compose perception, calibration, tracking/settling, and tool-tip uncertainty.
7. Require that the composed bound fits inside every target's declared safe
   region before proposing a deployment qualification.

The frozen inference producer writes an external evaluation-plan JSON document
conforming to
[`physical_camera_localization_evaluation_plan_v1.schema.json`](../schemas/physical_camera_localization_evaluation_plan_v1.schema.json).
Every prediction binds its capture, image, model, and preprocessing SHA-256.
The plan embeds the frozen keyboard target map and binds each additional
uncertainty component to its own evidence SHA-256. Ground-truth files conform
to
[`physical_camera_localization_ground_truth_v1.schema.json`](../schemas/physical_camera_localization_ground_truth_v1.schema.json).

Run the evaluator only after preflight and frozen inference are complete:

```powershell
python software/ai/eval/evaluate_physical_camera_localization.py `
  --campaign D:\tactevra-evidence\physical-camera-campaign\campaign.json `
  --preflight D:\tactevra-evidence\physical-camera-campaign\receipts\preflight.json `
  --plan D:\tactevra-evidence\physical-camera-campaign\evaluation-plan.json `
  --evidence-root D:\tactevra-evidence\physical-camera-campaign `
  --output D:\tactevra-evidence\physical-camera-campaign\receipts\evaluation.json
```

The evaluator replays preflight against the current retained bytes. It derives
the localization bound from calibration records, applies that unchanged bound
to held-out records, uses a conservative linear sum for the separately evidenced
camera/robot/tracking/tool components, and checks every frozen safe radius. Its
result validates against
[`physical_camera_localization_evaluation_result_v1.schema.json`](../schemas/physical_camera_localization_evaluation_result_v1.schema.json).
`QUALIFICATION_RECOMMENDED` is an offline review recommendation. The result
always keeps `qualification_installed`, `physical_deployment_qualified`, and
motion-batch emission false.

The campaign fails closed if any identity drifts, splits overlap, condition
coverage is incomplete, the declared 0.99 coverage is missed, an unsafe scene
is accepted, or the composed bound crosses a target safe region. A failed
campaign remains evidence and starts a new version; it is never rewritten.

## Required retained outputs

- Exact campaign manifest and preflight receipt
- External image and ground-truth roots with immutable hashes
- Frozen evaluator plan and source commit
- Calibration result and held-out result kept separate
- Per-condition and per-target compact scorecard
- Failure case IDs and abstention reasons
- Proposed qualification or explicit `qualification_installed: false`
- Hardware-write and physical-movement counts

Completion of this campaign can make the AI lane ready for S3 integration. It
does not complete the arm lane, authorize controller access, or permit contact.
