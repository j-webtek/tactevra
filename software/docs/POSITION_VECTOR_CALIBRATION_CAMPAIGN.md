# Position-vector calibration campaign

This workflow turns independently measured, stationary controller observations
into the existing `rocell.position_vector_calibration.v1` artifact. It is an
offline evidence and review process. It does not connect to hardware, command
motion, capture camera frames, or grant physical authority.

## Evidence chain

The campaign has four deliberately separate records:

1. A `rocell.position_vector_calibration_dataset.v1` dataset records the exact
   controller identity, attachment profile, raw servo counts, independent joint
   truth, and training or held-out assignment for every stationary sample.
2. A deterministic fit produces a
   `rocell.position_vector_calibration_fit_report.v1` report. The report includes
   affine coefficients, observed count ranges, held-out errors, and the mirrored
   shoulder residual.
3. A different person reviews the dataset and fit report and signs a
   `rocell.position_vector_calibration_review.v1` record by their exact hashes.
4. The builder recomputes the fit, verifies the review and hashes, and emits the
   strict `rocell.position_vector_calibration.v1` runtime artifact.

The generated artifact remains observation-only: `motion_authorized` and
`physical_authority` are always false.

## Dataset contract

The top-level JSON object contains:

- `schema`: `rocell.position_vector_calibration_dataset.v1`
- `dataset_id` and `producer_id`
- `attachment_profile`: `no_attachment` or `stylus_attachment`
- `controller_binding`: USB VID, PID, unit serial, and the exact firmware
  SHA-256 digest
- `position_order_servo_ids`: exactly `[11, 12, 13, 14, 15, 16, 17]`
- `joint_order`: exactly `base`, `shoulder`, `elbow`, `wrist_pitch`,
  `wrist_roll`, `gripper`, in that order
- `samples`: the stationary observations

Each sample must have a unique sample ID and unique truth-evidence SHA-256. It
must record seven raw counts, all six independently measured canonical joint
angles in radians, `motion_active: false`, `progress: 1000`, and either a
`TRAINING` or `HELD_OUT` split. Supported truth methods are:

- `encoder_reference_fixture`
- `link_fiducial_pose`
- `manufacturer_traceable_fixture`
- `mechanical_angle_fixture`

Camera localization of the keyboard and board does not by itself provide joint
truth. A camera-derived joint angle is acceptable only when link fiducials are
mechanically registered and the evidence is retained under
`link_fiducial_pose`.

## Default acceptance policy

The default policy requires:

- at least five training samples;
- at least three disjoint held-out samples;
- at least 128 counts of training span for every primary joint;
- no more than 0.035 radians absolute held-out error; and
- no more than 24 counts of mirrored-shoulder residual.

Samples should cover the intended operating range rather than cluster near one
pose. Held-out samples must not be reused to choose or tune the fit.

## Freeze the collection before capture

Before freezing a plan, run the offline `assess` command against retained facts.
It produces a deterministic
`rocell.position_vector_calibration_collection_readiness.v1` report and never
opens the controller or camera. Missing installed-firmware identity remains an
explicit `INSTALLED_FIRMWARE_SHA256_UNVERIFIED` blocker; the vendor archive
hash must not be used as a substitute. The assessment also requires at least
eight unique pose labels so the default five training and three held-out slots
can remain disjoint.

The current retained bare-jaw evidence is correctly `BLOCKED`: the exact
installed firmware SHA-256 is unverified, and the reviewed A/B catalog contains
only six unique poses (`A_CLEAR`, `A_HOVER`, `A_DOWN`, `B_CLEAR`, `B_HOVER`,
`B_DOWN`). This is a readiness result, not a request to move the arm.

```powershell
python -m rocell.calibration.position_vector_campaign assess `
  --vid 10c4 --pid ea60 `
  --unit-serial 52E4E1E8337FEF119E92181CEDD322A4 `
  --attachment-profile no_attachment `
  --truth-method link_fiducial_pose `
  --retained-pose A_CLEAR --retained-pose A_HOVER --retained-pose A_DOWN `
  --retained-pose B_CLEAR --retained-pose B_HOVER --retained-pose B_DOWN `
  --output position-vector-readiness.json
```

Add `--firmware-sha256` only after the exact installed image has independent
evidence. Add two or more unique reviewed pose labels only after those physical
configurations and their independent truth procedure are defined. A
`READY_TO_PREPARE` report means the inputs can be partitioned into a plan; it
grants no physical authority.

The `prepare` command creates two new offline records before any physical
collection begins:

- `rocell.position_vector_calibration_collection_plan.v1` freezes the exact
  controller and firmware binding, attachment profile, truth method, policy,
  ordered training and held-out pose labels, and sample IDs. Its authority
  block proves that no controller or camera was opened and no command or motion
  authority was issued.
- `rocell.position_vector_calibration_observations.v1` is a plan-hash-bound
  template with one empty evidence slot for every planned sample.

Pose labels are campaign identities, not movement instructions. Preparing a
plan cannot move the arm. Use distinct labels for every independently chosen
stationary configuration and reserve the held-out labels before fitting.

For example, from the `software` directory:

```powershell
python -m rocell.calibration.position_vector_campaign prepare `
  --dataset-id installed-arm-count-campaign-01 `
  --producer-id calibration-producer-01 `
  --vid 10c4 --pid ea60 `
  --unit-serial CONTROLLER_SERIAL `
  --firmware-sha256 EXACT_INSTALLED_FIRMWARE_SHA256 `
  --attachment-profile no_attachment `
  --truth-method link_fiducial_pose `
  --training-pose CAL_TRAIN_01 --training-pose CAL_TRAIN_02 `
  --training-pose CAL_TRAIN_03 --training-pose CAL_TRAIN_04 `
  --training-pose CAL_TRAIN_05 `
  --held-out-pose CAL_HOLDOUT_01 --held-out-pose CAL_HOLDOUT_02 `
  --held-out-pose CAL_HOLDOUT_03 `
  --plan-output position-vector-plan.json `
  --observations-output position-vector-observations.json
```

Populate each observation slot only from its named stationary sample. Each slot
requires seven retained raw counts, all six independent joint angles, a unique
truth-evidence hash, `stationary: true`, `motion_active: false`, and
`trajectory_progress_permille: 1000`. Then compile the plan-bound observations:

```powershell
python -m rocell.calibration.position_vector_campaign compile `
  --plan position-vector-plan.json `
  --observations position-vector-observations.json `
  --output position-vector-dataset.json
```

Compilation fails if a slot is missing, reordered, renamed, bound to another
plan, or incomplete. The generated dataset is passed through the same strict
dataset validator used by `fit`.

## Offline commands

From the `software` directory, create the deterministic fit report:

```powershell
python -m rocell.calibration.position_vector_campaign fit `
  --dataset position-vector-dataset.json `
  --calibration-id installed-arm-count-fit-01 `
  --output position-vector-fit-report.json
```

After independent review, build the runtime artifact:

```powershell
python -m rocell.calibration.position_vector_campaign build `
  --dataset position-vector-dataset.json `
  --fit-report position-vector-fit-report.json `
  --review position-vector-review.json `
  --output position-vector-calibration.json
```

The review record has the following shape:

```json
{
  "schema": "rocell.position_vector_calibration_review.v1",
  "producer_id": "calibration-producer-01",
  "reviewer_id": "independent-reviewer",
  "reviewed_at": "2026-10-21T12:00:00-04:00",
  "decision": "ACCEPT",
  "dataset_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "fit_report_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "review_notes_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

Use the exact hashes emitted by the fit workflow. Both commands refuse to
overwrite an existing output file.

## Attachment profiles

The count-to-joint calibration is bound to the controller, firmware, and arm
mechanics. The campaign also records the installed attachment so evidence can be
traced to the physical configuration used during collection.

Operational geometry must remain separated by attachment. `no_attachment` and
`stylus_attachment` require distinct tool-center-point transforms, collision
geometry, cable and clearance constraints, and validated trajectories. Adding
the stylus changes those operational profiles even when the underlying joint
count mapping remains valid. A controller, firmware, servo installation, or
mechanical linkage change invalidates the joint calibration and requires a new
campaign.

## Physical collection boundary

A future physical campaign requires fresh, explicit hardware authorization.
Begin from a secured neutral pose, freeze the collection plan, collect only
stationary observations, retain the independent truth evidence for every
sample, and keep training and held-out poses disjoint. Prepare separate plans
for `no_attachment` and `stylus_attachment`; observations cannot cross their
plan hashes. The current single T1051 response remains
`CALIBRATION_REQUIRED`; it is useful as retained evidence but cannot satisfy the
campaign on its own.
