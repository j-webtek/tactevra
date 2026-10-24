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

For the final governed assessment, place the retained facts in a
`rocell.position_vector_calibration_readiness_evidence.v1` manifest and run
`assess-reviewed`. The manifest binds the controller identity, exact installed
firmware digest and its evidence digest, an independent firmware verifier, and
one unique truth-procedure digest plus independent reviewer for every pose.
The command emits the ordinary readiness report and a receipt hashing both the
reviewed evidence and derived readiness result:

```powershell
python -m rocell.calibration.position_vector_campaign assess-reviewed `
  --evidence position-vector-reviewed-evidence.json `
  --readiness-output position-vector-readiness.json `
  --receipt-output position-vector-readiness-receipt.json
```

The producer cannot serve as firmware verifier or pose reviewer, and truth
procedure hashes cannot be reused across poses. This records provenance; it
does not manufacture missing physical evidence.

Before freezing a plan, run the offline `assess` command against retained facts.
It produces a deterministic
`rocell.position_vector_calibration_collection_readiness.v1` report and never
opens the controller or camera. Missing installed-firmware identity remains an
explicit `INSTALLED_FIRMWARE_SHA256_UNVERIFIED` blocker; the vendor archive
hash must not be used as a substitute. The assessment also requires at least
eight unique pose labels so the default five training and three held-out slots
can remain disjoint.

The 2026-10-24 Stage A readback resolved the installed-firmware identity. Two
matching 4 MiB reads have SHA-256
`c800a24409d4e57f65d431b8341c872a8684144a9ed1c7a4af9c96e79a7d4cec`;
the selected app0 image has SHA-256
`1b0589fa323a2714777f5c70453eeec6daa94bd8c92a481701689da82ce93fdc`.
The readiness binding uses the full installed-flash digest. The original A/B
catalog still contains only six unique labels (`A_CLEAR`, `A_HOVER`, `A_DOWN`,
`B_CLEAR`, `B_HOVER`, `B_DOWN`), so that six-label assessment remains blocked
on pose count alone.

```powershell
python -m rocell.calibration.position_vector_campaign assess `
  --vid 10c4 --pid ea60 `
  --unit-serial 52E4E1E8337FEF119E92181CEDD322A4 `
  --firmware-sha256 c800a24409d4e57f65d431b8341c872a8684144a9ed1c7a4af9c96e79a7d4cec `
  --attachment-profile no_attachment `
  --truth-method link_fiducial_pose `
  --retained-pose A_CLEAR --retained-pose A_HOVER --retained-pose A_DOWN `
  --retained-pose B_CLEAR --retained-pose B_HOVER --retained-pose B_DOWN `
  --output position-vector-readiness.json
```

The firmware argument above is supported by the verified readback checkpoint.
Add two or more unique reviewed pose labels only after those physical
configurations and their independent truth procedure are defined. A
`READY_TO_PREPARE` report means the inputs can be partitioned into a plan; it
grants no physical authority.

## Candidate-pose coverage audit

Historical repository evidence contains more than the six A/B labels. The
recorded bare-jaw reverse chain has eight named goals from
`KEYBOARD_FORWARD_CAL_1` through `KEYBOARD_FIELD_APPROACH_38`. Those names and
goal counts are retained in
`software/config/position_vector_candidate_pose_inventory_20261024.json`.
They are candidates only: planned goals are not stationary observations and do
not provide independent joint-angle truth.

Run the pure offline audit before assigning training and held-out slots:

```powershell
python -m rocell.calibration.position_vector_campaign audit-candidates `
  --inventory config/position_vector_candidate_pose_inventory_20261024.json `
  --output config/calibration_candidates/position_vector_candidate_coverage_20261024.json
```

The audit maps the seven-position vector to the six primary joints and tests
the largest possible span across the entire candidate catalog. If the complete
catalog cannot reach the minimum span, no five-pose training subset can reach
it either. It does not open hardware and cannot authorize collection or motion.

The current eight-pose reverse chain is blocked despite satisfying the pose
count:

- base span is 127 counts, one count below the 128-count minimum;
- wrist-roll span is zero because every historical goal holds servo 16 at 2040;
- gripper span is zero because every historical goal holds servo 17 at 2047;
- shoulder, elbow and wrist-pitch candidate spans exceed 128.

Therefore these eight poses must not be frozen as the final campaign merely to
clear the label-count gate. A future reviewed catalog needs safely qualified
configurations that expand base, wrist-roll and gripper coverage.
Every selected pose still needs its own independent truth procedure and all six
measured canonical joint angles. The physical selection and collection require
fresh authorization; this audit requests no movement.

Derive the exact algebraic ranges that would close the full-catalog gaps:

```powershell
python -m rocell.calibration.position_vector_campaign plan-candidate-augmentation `
  --inventory config/position_vector_candidate_pose_inventory_20261024.json `
  --output config/calibration_candidates/position_vector_candidate_augmentation_20261024.json
```

The retained augmentation plan is bound to the inventory and coverage-report
hashes. It shows that one additional candidate is the algebraic lower bound,
provided that candidate can safely and physically meet one listed range for
each deficient joint:

- base: at most 2046 counts or at least 2175 counts;
- wrist roll: at most 1912 counts or at least 2168 counts; and
- gripper: at most 1919 counts or at least 2175 counts.

These are count-range requirements, not a pose or movement command. The plan
does not choose a direction, assert reachability, assess collision or cable
clearance, or establish independent joint truth. A future physical session must
first qualify a mechanically feasible configuration and attachment profile.
After adding candidates, rerun the audit and verify that an exact five-pose
training subset, rather than only the full catalog, spans every primary joint.

Before any proposed candidate is considered for mechanical review, bind its
seven-count vector to the exact inventory hash in a
`rocell.position_vector_calibration_candidate_proposal.v1` record and run the
offline preflight:

```powershell
python -m rocell.calibration.position_vector_campaign preflight-candidate-augmentation `
  --inventory config/position_vector_candidate_pose_inventory_20261024.json `
  --candidate proposed-position-vector-candidate.json `
  --output proposed-position-vector-preflight.json
```

The proposal also names its attachment profile, so a bare-jaw candidate cannot
be evaluated against a stylus inventory. The preflight recomputes the
augmentation requirements, evaluates each deficient count index, appends the
proposal only in memory, and reruns the full-catalog coverage audit. It refuses
crossed inventory hashes, crossed attachment profiles, duplicate labels,
malformed counts, and existing output files.

Keep an unevaluated proposal outside the retained calibration-candidate
inventory. Add it to a governed inventory only after the separate mechanical
and evidence reviews accept that exact attachment-specific configuration.

`COUNT_VECTOR_CLOSES_CATALOG_GAPS` means only that the proposed numbers close
the algebraic full-catalog spans. It does not prove reachability, joint limits,
collision clearance, cable or attachment clearance, independent joint truth,
or five-pose training-subset coverage. The command imports no hardware layer,
opens no controller or camera, and grants no collection or motion authority.

For a proposal with that exact passing result, freeze the next review boundary
as a qualification plan:

```powershell
python -m rocell.calibration.position_vector_campaign prepare-candidate-qualification `
  --inventory config/position_vector_candidate_pose_inventory_20261024.json `
  --candidate proposed-position-vector-candidate.json `
  --preflight proposed-position-vector-preflight.json `
  --output proposed-position-vector-qualification-plan.json
```

The command recomputes the preflight and rejects a stale, edited, crossed, or
gap-leaving result. Its plan is bound to the inventory, candidate, attachment
profile, and preflight hashes. It deliberately marks every evidence slot
missing. The listed gates cover the calibrated count-to-joint mapping,
kinematic reachability and joint limits, installed collision geometry, cable
clearance, attachment and tool-center-point geometry, continuous swept-path
screening, independent joint truth procedure, and independent engineering
review.

`QUALIFICATION_EVIDENCE_REQUIRED` is a blocker state. The plan is a checklist,
not a reachability or safety assessment, and it cannot accept evidence or
authorize hardware access, collection, or motion. The installed collision and
cable geometry must come from the exact physical attachment profile; hashes or
reviews from a different profile cannot satisfy those future gates.

As reviewed artifacts become available, record them in a
`rocell.position_vector_calibration_candidate_qualification_evidence.v1`
manifest. The manifest binds the exact qualification-plan, inventory,
candidate, and attachment-profile hashes. Each supplied gate names its evidence
SHA-256, reviewer, and `ACCEPT` or `REJECT` decision. The reviewer must differ
from the manifest producer. A partial manifest is valid and preserves every
unsupplied gate as an explicit blocker.

Assess that chain without opening hardware:

```powershell
python -m rocell.calibration.position_vector_campaign assess-candidate-qualification `
  --inventory config/position_vector_candidate_pose_inventory_20261024.json `
  --candidate proposed-position-vector-candidate.json `
  --preflight proposed-position-vector-preflight.json `
  --plan proposed-position-vector-qualification-plan.json `
  --evidence proposed-position-vector-qualification-evidence.json `
  --output proposed-position-vector-qualification-assessment.json
```

The assessor reproduces the entire proposal, preflight, and plan chain. It
rejects crossed bindings, unknown or duplicate gates, malformed hashes,
unsupported decisions, and a reviewer who is also the evidence producer.
Missing evidence produces `<GATE>_EVIDENCE_REQUIRED`; rejected evidence
produces `<GATE>_EVIDENCE_REJECTED`.

`EVIDENCE_CHAIN_COMPLETE` means all eight declared evidence records have an
independent `ACCEPT` decision. The assessor validates the manifest and hashes;
it does not inspect the referenced files or independently prove their physical
claims. Completion therefore remains observation-only and grants no hardware,
collection, or motion authority.

Once the exact assessment is complete, create the compact downstream handoff:

```powershell
python -m rocell.calibration.position_vector_campaign create-candidate-qualification-handoff `
  --inventory config/position_vector_candidate_pose_inventory_20261024.json `
  --candidate proposed-position-vector-candidate.json `
  --preflight proposed-position-vector-preflight.json `
  --plan proposed-position-vector-qualification-plan.json `
  --evidence proposed-position-vector-qualification-evidence.json `
  --assessment proposed-position-vector-qualification-assessment.json `
  --output proposed-position-vector-qualification-handoff.json
```

The command reproduces the proposal, preflight, plan, evidence assessment, and
all bindings. It refuses a blocked or edited assessment. The resulting
`rocell.position_vector_calibration_candidate_qualification_handoff.v1` receipt
records the candidate, attachment profile, upstream hashes, evidence producer,
and all eight accepted evidence hashes and reviewers in plan order. This lets a
later inventory or campaign step verify one small receipt while retaining the
full chain for audit.

`QUALIFICATION_HANDOFF_READY` describes artifact transfer only. It does not add
the proposal to the governed inventory, inspect the evidence files, establish
physical correctness, or authorize hardware access, collection, or motion.

To prepare a reviewable inventory revision from that handoff, run:

```powershell
python -m rocell.calibration.position_vector_campaign admit-qualified-candidate `
  --inventory config/position_vector_candidate_pose_inventory_20261024.json `
  --candidate proposed-position-vector-candidate.json `
  --preflight proposed-position-vector-preflight.json `
  --plan proposed-position-vector-qualification-plan.json `
  --evidence proposed-position-vector-qualification-evidence.json `
  --assessment proposed-position-vector-qualification-assessment.json `
  --handoff proposed-position-vector-qualification-handoff.json `
  --inventory-id bare-jaw-keyboard-chain-qualified-20261024 `
  --inventory-output proposed-qualified-candidate-inventory.json `
  --receipt-output proposed-qualified-candidate-admission-receipt.json
```

The command reproduces the complete chain and handoff, requires a fresh
inventory identity, appends exactly one candidate in plan order, and reruns the
coverage audit. It emits the proposed inventory and a
`rocell.position_vector_calibration_candidate_inventory_admission_receipt.v1`
record binding the source inventory, admitted inventory, candidate, handoff,
attachment profile, and passing coverage report by canonical SHA-256. Existing
or aliased output paths are refused.

`QUALIFIED_CANDIDATE_INVENTORY_READY` means the proposed inventory artifact is
ready for repository review. The appended entry remains a `PLANNED_GOAL`; it is
not a stationary controller readback or independent joint-truth observation.
The command does not replace the retained inventory automatically and grants no
hardware, collection, or motion authority.

Before preparing a collection campaign, verify that a bounded training subset
can satisfy count-span policy while reserving held-out poses:

```powershell
python -m rocell.calibration.position_vector_campaign plan-qualified-candidate-split `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --output proposed-position-vector-training-split.json
```

The planner strictly validates the admission receipt against the inventory and
its recomputed coverage report. It then enumerates pose combinations in stable
inventory order, starting at the policy minimum training count, and chooses the
first subset whose count span meets policy for every primary joint. Every
remaining pose becomes held out, so the two lists are disjoint and partition
the full admitted inventory. The default policy seeks at least five training
and three held-out poses with at least 128 counts of training span per joint.

`TRAINING_SPLIT_READY` means such a count-feasible partition exists.
`TRAINING_SPLIT_BLOCKED` retains
`NO_TRAINING_SUBSET_MEETS_COUNT_SPAN_POLICY` when the full inventory passes but
no bounded training subset does. This combinatorial result does not optimize
conditioning, geometry, clearance, or measurement quality; the pose entries
remain planned goals, and the command grants no hardware, collection, or motion
authority.

Freeze that exact qualified split into the existing collection-plan contract
before gathering reviewed readiness evidence:

```powershell
python -m rocell.calibration.position_vector_campaign prepare-qualified-candidate-collection `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --dataset-id bare-jaw-position-vector-campaign-01 `
  --producer-id calibration-producer-01 `
  --truth-method link_fiducial_pose `
  --plan-output proposed-position-vector-collection-plan.json `
  --observations-output proposed-position-vector-observations.json `
  --receipt-output proposed-position-vector-qualified-preparation-receipt.json
```

The command reproduces the admission-bound split instead of trusting copied
pose lists. It emits the established collection plan with five training and
four held-out slots, its plan-hash-bound empty observation template, and a
`rocell.position_vector_calibration_qualified_collection_preparation_receipt.v1`
record binding the inventory, admission receipt, split, plan, and template by
canonical SHA-256. Existing or aliased outputs are refused.

`QUALIFIED_COLLECTION_PACKAGE_PREPARED` is an offline planning state. The
receipt names `REVIEWED_COLLECTION_READINESS` as the next required gate. The
planned counts are still goals rather than readbacks, the observation slots are
empty, and the package does not establish installed firmware, camera, board,
attachment, or independent truth-procedure readiness. It grants no hardware,
collection, or motion authority.

Turn that exact prepared package into a finite reviewed-readiness checklist:

```powershell
python -m rocell.calibration.position_vector_campaign plan-qualified-collection-readiness `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations proposed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --output proposed-position-vector-collection-readiness-plan.json
```

The command reproduces the entire package and rejects crossed plans, templates,
or receipts. Its
`rocell.position_vector_calibration_qualified_collection_readiness_plan.v1`
output binds the controller, attachment profile, truth method, ordered pose
catalog, and every upstream artifact hash. It creates eight missing evidence
slots: installed-firmware binding, fixed-camera intrinsics, camera-to-board
registration, board geometry, attachment-profile geometry, collection collision
envelope, independent truth procedures, and collection-operator review.

`QUALIFIED_COLLECTION_READINESS_EVIDENCE_REQUIRED` is intentionally blocked.
The checklist records what must be reviewed next; it neither accepts evidence
nor treats a phone photograph or unrelated camera mode as fixed-camera evidence.
It grants no hardware, collection, or motion authority.

Use `prepare-reviewed` for the governed handoff. It recomputes the reviewed
evidence assessment, requires the supplied readiness report and readiness
receipt to reproduce exactly, and derives the dataset and producer identities
from that reviewed evidence. It also requires the training and held-out labels
to partition the same retained pose catalog and creates three offline records
before any physical collection begins:

- `rocell.position_vector_calibration_collection_plan.v1` freezes the exact
  controller and firmware binding, attachment profile, truth method, policy,
  ordered training and held-out pose labels, and sample IDs. Its authority
  block proves that no controller or camera was opened and no command or motion
  authority was issued.
- `rocell.position_vector_calibration_observations.v1` is a plan-hash-bound
  template with one empty evidence slot for every planned sample.
- `rocell.position_vector_calibration_reviewed_preparation_receipt.v1` binds
  the reviewed evidence, readiness-evidence receipt, readiness report,
  assessed-preparation derivation, plan, and observation template by canonical
  SHA-256. It also repeats the zero-authority declaration.

Pose labels are campaign identities, not movement instructions. Preparing a
plan cannot move the arm. Use distinct labels for every independently chosen
stationary configuration and reserve the held-out labels before fitting.

For example, from the `software` directory:

The example assumes `position-vector-readiness.json` is a passing report whose
retained pose catalog is exactly the eight labels partitioned below.

```powershell
python -m rocell.calibration.position_vector_campaign prepare-reviewed `
  --evidence position-vector-reviewed-evidence.json `
  --readiness position-vector-readiness.json `
  --readiness-receipt position-vector-readiness-receipt.json `
  --training-pose CAL_TRAIN_01 --training-pose CAL_TRAIN_02 `
  --training-pose CAL_TRAIN_03 --training-pose CAL_TRAIN_04 `
  --training-pose CAL_TRAIN_05 `
  --held-out-pose CAL_HOLDOUT_01 --held-out-pose CAL_HOLDOUT_02 `
  --held-out-pose CAL_HOLDOUT_03 `
  --plan-output position-vector-plan.json `
  --observations-output position-vector-observations.json `
  --receipt-output position-vector-preparation-receipt.json
```

The lower-level `prepare` and `prepare-assessed` commands remain available for
compatibility and controlled test construction. Operational preparation should
use `prepare-reviewed` so independent provenance, controller, firmware,
attachment, truth-method, producer, campaign, and pose facts cannot drift
between review, assessment, and plan creation. Every path is offline and
refuses to replace existing outputs.

Populate each observation slot only from its named stationary sample. Each slot
requires seven retained raw counts, all six independent joint angles, a unique
truth-evidence hash, `stationary: true`, `motion_active: false`, and
`trajectory_progress_permille: 1000`. Then use `compile-reviewed` to reproduce
the complete reviewed preparation chain before compiling the plan-bound
observations:

```powershell
python -m rocell.calibration.position_vector_campaign compile-reviewed `
  --evidence position-vector-reviewed-evidence.json `
  --readiness position-vector-readiness.json `
  --readiness-receipt position-vector-readiness-receipt.json `
  --preparation-receipt position-vector-preparation-receipt.json `
  --plan position-vector-plan.json `
  --observations position-vector-observations.json `
  --output position-vector-dataset.json `
  --receipt-output position-vector-compilation-receipt.json
```

Compilation fails if the reviewed evidence, readiness result, readiness
receipt, preparation receipt, plan, or observation set crosses another
campaign or attachment profile. It also fails if a slot is missing, reordered,
renamed, bound to another plan, or incomplete. The generated
`rocell.position_vector_calibration_reviewed_compilation_receipt.v1` record
binds every reviewed-preparation hash plus the filled observations and strict
dataset hash while repeating the zero-authority declaration. The generated
dataset is passed through the same strict validator used by `fit`.

The lower-level `compile` command remains available for compatibility and
controlled test construction. Operational compilation should use
`compile-reviewed` so the filled observations cannot be detached from their
reviewed preparation chain. Both commands are offline and refuse to replace
existing output files.

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
