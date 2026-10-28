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

Assess a partial or complete evidence manifest against that exact checklist:

```powershell
python -m rocell.calibration.position_vector_campaign assess-qualified-collection-readiness `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations proposed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --evidence reviewed-position-vector-collection-readiness-evidence.json `
  --output proposed-position-vector-collection-readiness-assessment.json
```

The strict
`rocell.position_vector_calibration_qualified_collection_readiness_evidence.v1`
manifest binds the readiness plan, inventory, collection plan, preparation
receipt, and attachment profile. Each supplied gate names a retained evidence
SHA-256, an independent reviewer, and an `ACCEPT` or `REJECT` decision. Evidence
may be supplied incrementally; omitted gates stay `EVIDENCE_MISSING`, rejected
gates stay `EVIDENCE_REJECTED`, and both remain explicit blockers in plan order.

The assessment is
`QUALIFIED_COLLECTION_READINESS_COMPLETE` only when all eight gates have
accepted declarations. This validates artifact bindings, decisions, and
reviewer separation. It does not inspect the referenced evidence, prove the
physical setup, or authorize hardware access, collection, or motion.

Create the artifact-transfer boundary only after the assessment is complete:

```powershell
python -m rocell.calibration.position_vector_campaign create-qualified-collection-readiness-handoff `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations proposed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --evidence reviewed-position-vector-collection-readiness-evidence.json `
  --assessment proposed-position-vector-collection-readiness-assessment.json `
  --output proposed-position-vector-collection-readiness-handoff.json
```

The command reproduces the entire chain and refuses blocked, crossed, or edited
assessments. Its
`rocell.position_vector_calibration_qualified_collection_readiness_handoff.v1`
receipt binds the existing collection plan and empty observation template to
the eight accepted evidence declarations and their independent reviewers. It
preserves the ordered nine-pose catalog and identifies
`RETAINED_STATIONARY_OBSERVATION_COLLECTION` as the next required gate.

`QUALIFIED_COLLECTION_READINESS_HANDOFF_READY` describes artifact transfer.
The receipt does not inspect the referenced evidence or authorize controller,
camera, collection, or motion access. Physical collection remains subject to
the separate operator and safety controls for the installed system.

After an authorized physical session has retained one stationary pose, ingest
its artifacts into the exact planned slot without reopening any device:

```powershell
python -m rocell.calibration.position_vector_campaign ingest-qualified-stationary-observation `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations current-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --observation-evidence retained-position-vector-observation-evidence.json `
  --observations-output next-position-vector-observations.json `
  --receipt-output retained-position-vector-observation-ingestion-receipt.json
```

The strict observation-evidence record binds the readiness handoff, current
template hash, planned sample and pose, seven retained counts, all six canonical
joint angles, an independent truth reviewer, retained controller-feedback
evidence, a retained fixed-camera observation receipt, and joint-truth evidence.
It must declare `stationary: true`, `motion_active: false`, and
`trajectory_progress_permille: 1000`. A slot can be filled only once, truth
evidence cannot be reused, and existing filled slots must reproduce exactly.

The command writes a new observation document instead of replacing its input.
Its
`rocell.position_vector_calibration_qualified_stationary_observation_ingestion_receipt.v1`
receipt hash-chains the previous and resulting templates and records both the
filled and remaining sample counts. Repeat the command with the latest output
for each planned pose. The last receipt advances the next gate to
`QUALIFIED_OBSERVATION_SET_COMPILATION`; earlier receipts retain
`RETAINED_STATIONARY_OBSERVATION_COLLECTION`.

Ingestion validates retained declarations and hashes only. It does not open a
camera or controller, request feedback, capture an image, command motion, or
authorize physical collection.

After every planned slot is filled, verify the ordered ingestion-receipt chain
and compile the qualified dataset:

```powershell
python -m rocell.calibration.position_vector_campaign compile-qualified-observation-set `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --output qualified-position-vector-dataset.json `
  --receipt-output qualified-position-vector-compilation-receipt.json
```

Receipt arguments must follow ingestion order. The command reproduces the full
readiness handoff, requires exactly one receipt for every planned sample, starts
the hash chain at the original empty template, and requires every resulting
hash to become the next receipt's previous hash. It also checks planned pose and
split bindings, monotonic filled and remaining counts, independent truth review,
unique per-sample evidence, final truth hashes, and the final observation hash.

The
`rocell.position_vector_calibration_qualified_observation_set_compilation_receipt.v1`
record binds the complete receipt trace, final observations, strict dataset,
upstream qualification chain, and zero-authority declaration. Its next gate is
`DETERMINISTIC_CALIBRATION_FIT`. Compilation is an offline artifact operation;
it performs no capture, feedback request, command, or motion.

Run the qualified deterministic fit gate against those exact outputs:

```powershell
python -m rocell.calibration.position_vector_campaign assess-qualified-deterministic-fit `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --calibration-id installed-arm-count-fit-01 `
  --fit-report-output qualified-position-vector-fit-report.json `
  --assessment-output qualified-position-vector-fit-assessment.json
```

This command first reproduces the complete qualified compilation from its
upstream artifacts. The supplied dataset and compilation receipt must match
that reproduction exactly. It then runs the deterministic affine fit, checks
the training count span for every primary joint, evaluates every held-out
sample against the configured maximum error, and verifies the mirrored
shoulder residual. Policy overrides use the same flags as the lower-level
`fit` command and are recorded in both outputs.

The fit report retains the numerical model and all training and held-out
metrics. The
`rocell.position_vector_calibration_qualified_deterministic_fit_assessment.v1`
record binds the compilation receipt, dataset, fit report, policy, per-joint
held-out results, and shoulder-pair result. A passing assessment advances only
to `INDEPENDENT_CALIBRATION_REVIEW`. It does not accept or activate the
calibration and opens no controller or camera, requests no feedback, and sends
no command or motion.

After a separate reviewer inspects those exact outputs, retain a qualified
review record and accept it through the independent-review gate:

```powershell
python -m rocell.calibration.position_vector_campaign accept-qualified-independent-fit-review `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --output qualified-position-vector-independent-fit-review-receipt.json
```

The retained review has this strict shape:

```json
{
  "schema": "rocell.position_vector_calibration_qualified_independent_fit_review.v1",
  "dataset_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "compilation_receipt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "fit_report_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "fit_assessment_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "producer_id": "calibration-producer-01",
  "reviewer_id": "independent-fit-reviewer-03",
  "decision": "ACCEPT",
  "reviewed_at": "2026-10-24T14:00:00-04:00",
  "review_notes_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

The reviewer must differ from the dataset producer. The gate infers the fit
policy and calibration identity from the supplied fit report, reproduces the
entire qualified compilation and deterministic assessment, and requires all
four reviewed hashes to match. It rejects non-acceptance decisions, timestamps
without a UTC offset, invalid note hashes, and crossed or modified artifacts.

The resulting
`rocell.position_vector_calibration_qualified_independent_fit_review_receipt.v1`
record advances only to `QUALIFIED_CALIBRATION_ARTIFACT_BUILD`. It does not
build, install, select, or activate a calibration and grants no hardware,
command, or motion authority.

Build the uninstalled runtime artifact only from that accepted review chain:

```powershell
python -m rocell.calibration.position_vector_campaign build-qualified-calibration-artifact `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact-output qualified-position-vector-calibration.json `
  --receipt-output qualified-position-vector-artifact-build-receipt.json
```

The command reproduces the independent-review receipt from the complete
qualified chain and rejects a crossed or modified receipt. It then constructs
the strict `rocell.position_vector_calibration.v1` artifact using the reviewed
dataset and deterministic fit. The artifact evidence binds the exact dataset,
fit report, and qualified independent review. Both outputs are new files and
cannot alias or replace an existing path.

The
`rocell.position_vector_calibration_qualified_artifact_build_receipt.v1`
record additionally binds the compilation receipt, fit assessment, independent
review receipt, and resulting artifact. Its next gate is
`CALIBRATION_INSTALLATION_REVIEW`. Building the file does not install, select,
load, or activate it and grants no hardware, command, motion, installation, or
activation authority.

Review the exact artifact for a declared logical destination before any
installation work is considered:

```powershell
python -m rocell.calibration.position_vector_campaign accept-qualified-calibration-installation-review `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --output qualified-position-vector-installation-review-receipt.json
```

The retained installation review has this strict shape:

```json
{
  "schema": "rocell.position_vector_calibration_qualified_installation_review.v1",
  "artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "artifact_build_receipt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "calibration_id": "installed-arm-count-fit-01",
  "attachment_profile": "no_attachment",
  "controller_binding_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "installation_profile_id": "installed-arm-no-attachment",
  "destination_ref": "position-vector-calibration-primary",
  "reviewer_id": "installation-reviewer-04",
  "decision": "ACCEPT",
  "reviewed_at": "2026-10-24T15:00:00-04:00",
  "review_notes_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

`installation_profile_id` and `destination_ref` are bounded logical
identifiers. They declare the intended profile and destination without
granting a filesystem path or causing a copy. The installation reviewer must
differ from both the dataset producer and the independent fit reviewer.

The command reproduces the complete qualified build, requires the supplied
artifact and build receipt to match byte-for-byte canonical content, and binds
the artifact, build receipt, calibration, attachment profile, and controller
identity into the review. It rejects modified or crossed artifacts, invalid
destinations, non-independent reviewers, non-acceptance decisions, timestamps
without a UTC offset, and invalid note hashes.

The resulting
`rocell.position_vector_calibration_qualified_installation_review_receipt.v1`
record advances only to `CALIBRATION_INSTALLATION_EXECUTION_APPROVAL`. It does
not copy, install, select, load, or activate the artifact and grants no
hardware, command, motion, installation, or activation authority.

After another independent approver accepts that exact review, retain an
execution-approval record and verify it through the approval gate:

```powershell
python -m rocell.calibration.position_vector_campaign approve-qualified-calibration-installation-execution `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --installation-review-receipt qualified-position-vector-installation-review-receipt.json `
  --execution-approval qualified-position-vector-installation-execution-approval.json `
  --output qualified-position-vector-installation-execution-approval-receipt.json
```

The retained approval has this strict shape:

```json
{
  "schema": "rocell.position_vector_calibration_qualified_installation_execution_approval.v1",
  "artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "artifact_build_receipt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "installation_review_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "installation_review_receipt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "calibration_id": "installed-arm-count-fit-01",
  "attachment_profile": "no_attachment",
  "controller_binding_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "installation_profile_id": "installed-arm-no-attachment",
  "destination_ref": "position-vector-calibration-primary",
  "approver_id": "installation-approver-05",
  "decision": "APPROVE",
  "approved_at": "2026-10-24T16:00:00-04:00",
  "approval_notes_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

The approver must differ from the dataset producer, independent fit reviewer,
and installation reviewer. The command reproduces the complete installation
review chain, rejects a crossed or modified review receipt, and requires every
artifact, controller, attachment, profile, and destination binding to match.

The resulting
`rocell.position_vector_calibration_qualified_installation_execution_approval_receipt.v1`
authorizes a later file installation only for that exact tuple and advances to
`CALIBRATION_INSTALLATION_EXECUTION`. It does not perform the installation,
select or load the artifact, activate a calibration, open a controller or
camera, request feedback, send commands, or grant motion or physical authority.
Calibration activation remains explicitly unauthorized.

Once that exact approval receipt has been retained, an independent installer
may perform the bounded file installation:

```powershell
python -m rocell.calibration.position_vector_campaign execute-qualified-calibration-installation `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --installation-review-receipt qualified-position-vector-installation-review-receipt.json `
  --execution-approval qualified-position-vector-installation-execution-approval.json `
  --execution-approval-receipt qualified-position-vector-installation-execution-approval-receipt.json `
  --installation-root inactive-position-vector-calibrations `
  --installer-id installation-operator-06 `
  --installed-at 2026-10-24T17:00:00-04:00 `
  --receipt-output qualified-position-vector-installation-receipt.json
```

The command reproduces the entire evidence, fit, review, build, installation
review, and approval chain before writing anything. It derives the destination
only from the approved bounded identifiers and writes canonical artifact bytes
to:

```text
<installation-root>/<installation-profile-id>/<destination-ref>.json
```

The installer must differ from the execution approver. The installation root,
profile directory, and target cannot be symbolic links or escape the declared
root. An existing target is never replaced. A successful command rereads the
installed bytes, verifies their SHA-256, and emits a
`rocell.position_vector_calibration_qualified_installation_receipt.v1` record.

Keep each physical configuration in a separate approved installation profile.
For example, the retained `no_attachment` artifact belongs under its approved
no-attachment profile. A later stylus artifact must pass its own complete
qualification and approval chain and use its separately approved stylus
profile. The command does not infer offsets between those profiles.

This installation remains inactive. It does not select, load, or activate the
artifact, open a controller or camera, request feedback, send commands, or
grant motion or physical authority. The receipt advances only to
`CALIBRATION_ACTIVATION_REVIEW`; activation requires a later explicit gate.

For the activation review, retain a strict review record that binds the exact
installation receipt and installed payload hash, then run:

```powershell
python -m rocell.calibration.position_vector_campaign review-qualified-calibration-activation `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --installation-review-receipt qualified-position-vector-installation-review-receipt.json `
  --execution-approval qualified-position-vector-installation-execution-approval.json `
  --execution-approval-receipt qualified-position-vector-installation-execution-approval-receipt.json `
  --installation-receipt qualified-position-vector-installation-receipt.json `
  --installation-root inactive-position-vector-calibrations `
  --activation-review qualified-position-vector-activation-review.json `
  --output qualified-position-vector-activation-review-receipt.json
```

The activation review has schema
`rocell.position_vector_calibration_qualified_activation_review.v1` and contains
only the exact installation-receipt hash, installed-payload hash, artifact,
calibration, attachment, controller, profile and destination bindings, plus the
reviewer, `ACCEPT` decision, offset-aware review time, and notes hash.

This command replays the complete approval chain, resolves the installed path
from the approved profile and destination, and reads the inactive file without
creating or modifying it. The file must equal the canonical approved artifact
bytes exactly, and the supplied installation receipt must reproduce from those
verified bytes. The activation reviewer must differ from the dataset producer,
fit reviewer, installation reviewer, execution approver, and installer.

The resulting
`rocell.position_vector_calibration_qualified_activation_review_receipt.v1`
record advances only to `CALIBRATION_ACTIVATION_EXECUTION_APPROVAL`. Review
acceptance does not select, load, or activate the file and grants no controller,
camera, command, motion, activation, or physical authority.

For activation execution approval, retain a separate approval record and run:

```powershell
python -m rocell.calibration.position_vector_campaign approve-qualified-calibration-activation-execution `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --installation-review-receipt qualified-position-vector-installation-review-receipt.json `
  --execution-approval qualified-position-vector-installation-execution-approval.json `
  --execution-approval-receipt qualified-position-vector-installation-execution-approval-receipt.json `
  --installation-receipt qualified-position-vector-installation-receipt.json `
  --installation-root inactive-position-vector-calibrations `
  --activation-review qualified-position-vector-activation-review.json `
  --activation-review-receipt qualified-position-vector-activation-review-receipt.json `
  --activation-execution-approval qualified-position-vector-activation-execution-approval.json `
  --output qualified-position-vector-activation-execution-approval-receipt.json
```

The approval record has schema
`rocell.position_vector_calibration_qualified_activation_execution_approval.v1`.
It binds the exact activation review and review receipt, installation receipt,
installed payload, artifact, calibration, attachment profile, controller,
installation profile, and destination. It also contains the approver,
`APPROVE` decision, offset-aware approval time, and notes hash.

The command replays the complete chain and rereads the installed canonical
bytes before accepting the approval. The activation execution approver must
differ from the dataset producer, fit reviewer, installation reviewer,
installation execution approver, installer, and activation reviewer. The
resulting
`rocell.position_vector_calibration_qualified_activation_execution_approval_receipt.v1`
record advances to `CALIBRATION_ACTIVATION_EXECUTION` for that one exact
configuration. It does not select, load, or activate a calibration, access the
controller or camera, send a command, or grant motion or physical authority.
The no-attachment and stylus-attachment profiles require separate chains and
cannot be substituted for each other.

To execute that approval as an offline, profile-scoped selection, run:

```powershell
python -m rocell.calibration.position_vector_campaign execute-qualified-calibration-activation `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --installation-review-receipt qualified-position-vector-installation-review-receipt.json `
  --execution-approval qualified-position-vector-installation-execution-approval.json `
  --execution-approval-receipt qualified-position-vector-installation-execution-approval-receipt.json `
  --installation-receipt qualified-position-vector-installation-receipt.json `
  --installation-root inactive-position-vector-calibrations `
  --activation-review qualified-position-vector-activation-review.json `
  --activation-review-receipt qualified-position-vector-activation-review-receipt.json `
  --activation-execution-approval qualified-position-vector-activation-execution-approval.json `
  --activation-execution-approval-receipt qualified-position-vector-activation-execution-approval-receipt.json `
  --activation-root active-position-vector-calibrations `
  --activator-id activation-operator-09 `
  --activated-at 2026-10-24T20:00:00-04:00 `
  --receipt-output qualified-position-vector-activation-receipt.json
```

The command reproduces the complete approval chain and exact installed bytes
before it writes anything. The activator must differ from the activation
execution approver. It then publishes exactly one immutable
`active-position-vector-calibration.json` under the approved installation
profile in the separate activation root. The selection record binds the
installed relative path, installed payload hash, artifact, controller,
attachment profile, destination, approval receipt, activator, and activation
time. It does not copy or modify the installed artifact.

The activation root must remain outside the immutable installation root, the
receipt must remain outside both roots, and neither an existing receipt nor an
existing active selection is replaced. This makes activation additive and
reviewable. Replacing or rolling back an active calibration requires a later,
separately governed transition rather than an in-place edit.

The resulting
`rocell.position_vector_calibration_qualified_activation_receipt.v1` advances
to `CALIBRATED_POSITION_VECTOR_FEEDBACK_INTEGRATION_REVIEW`. Activation here
means that an exact calibration has become the selected file-backed candidate
for that profile. It does not open a controller or camera, load a runtime
session, request feedback, send a command, or authorize motion. Calibrated
feedback integration remains explicitly unauthorized until the next gate.
`no_attachment` and `stylus_attachment` selections live under different
profile directories and require independent evidence and activation chains.

To review one active selection for later calibrated feedback integration, retain
a separate review record and run:

```powershell
python -m rocell.calibration.position_vector_campaign review-qualified-calibrated-feedback-integration `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --installation-review-receipt qualified-position-vector-installation-review-receipt.json `
  --execution-approval qualified-position-vector-installation-execution-approval.json `
  --execution-approval-receipt qualified-position-vector-installation-execution-approval-receipt.json `
  --installation-receipt qualified-position-vector-installation-receipt.json `
  --installation-root inactive-position-vector-calibrations `
  --activation-review qualified-position-vector-activation-review.json `
  --activation-review-receipt qualified-position-vector-activation-review-receipt.json `
  --activation-execution-approval qualified-position-vector-activation-execution-approval.json `
  --activation-execution-approval-receipt qualified-position-vector-activation-execution-approval-receipt.json `
  --activation-root active-position-vector-calibrations `
  --active-selection active-position-vector-calibrations/installed-arm-no-attachment/active-position-vector-calibration.json `
  --activation-receipt qualified-position-vector-activation-receipt.json `
  --integration-review qualified-position-vector-feedback-integration-review.json `
  --output qualified-position-vector-feedback-integration-review-receipt.json
```

The integration review has schema
`rocell.position_vector_calibration_qualified_feedback_integration_review.v1`.
It binds the activation receipt, immutable active selection, installed artifact
bytes, controller, attachment profile, and the exact offline conversion
contract. That contract fixes the installed `POSITION_VECTOR_NAMED_POSE` input,
servo IDs 11 through 17, canonical six-joint output, exact controller match,
mirrored-shoulder runtime check, and zero motion or physical authority.

The command replays the complete qualification, installation, and activation
chain; rereads the active selection; validates the calibration artifact through
the strict runtime loader; and refuses a changed receipt, selection, payload,
profile, controller, destination, or contract hash. The reviewer must remain
independent of the producer and every prior reviewer, approver, installer, and
activator. Review output must remain outside both installation and activation
roots and existing output is never replaced.

The resulting
`rocell.position_vector_calibration_qualified_feedback_integration_review_receipt.v1`
advances to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_INTEGRATION_EXECUTION_APPROVAL`. It does
not load a runtime session, open the controller or camera, request feedback,
send commands, or authorize motion. Each attachment profile still requires its
own active selection and review chain.

To approve later execution of that exact reviewed integration, retain a
separate approval record and run:

```powershell
python -m rocell.calibration.position_vector_campaign approve-qualified-calibrated-feedback-integration-execution `
  --inventory proposed-qualified-candidate-inventory.json `
  --admission-receipt proposed-qualified-candidate-admission-receipt.json `
  --training-split proposed-position-vector-training-split.json `
  --collection-plan proposed-position-vector-collection-plan.json `
  --observations completed-position-vector-observations.json `
  --preparation-receipt proposed-position-vector-qualified-preparation-receipt.json `
  --readiness-plan proposed-position-vector-collection-readiness-plan.json `
  --readiness-evidence reviewed-position-vector-collection-readiness-evidence.json `
  --readiness-assessment proposed-position-vector-collection-readiness-assessment.json `
  --readiness-handoff proposed-position-vector-collection-readiness-handoff.json `
  --ingestion-receipt ingestion-receipt-01.json `
  --ingestion-receipt ingestion-receipt-02.json `
  --ingestion-receipt ingestion-receipt-03.json `
  --ingestion-receipt ingestion-receipt-04.json `
  --ingestion-receipt ingestion-receipt-05.json `
  --ingestion-receipt ingestion-receipt-06.json `
  --ingestion-receipt ingestion-receipt-07.json `
  --ingestion-receipt ingestion-receipt-08.json `
  --ingestion-receipt ingestion-receipt-09.json `
  --dataset qualified-position-vector-dataset.json `
  --compilation-receipt qualified-position-vector-compilation-receipt.json `
  --fit-report qualified-position-vector-fit-report.json `
  --fit-assessment qualified-position-vector-fit-assessment.json `
  --review qualified-position-vector-independent-fit-review.json `
  --review-receipt qualified-position-vector-independent-fit-review-receipt.json `
  --artifact qualified-position-vector-calibration.json `
  --artifact-build-receipt qualified-position-vector-artifact-build-receipt.json `
  --installation-review qualified-position-vector-installation-review.json `
  --installation-review-receipt qualified-position-vector-installation-review-receipt.json `
  --execution-approval qualified-position-vector-installation-execution-approval.json `
  --execution-approval-receipt qualified-position-vector-installation-execution-approval-receipt.json `
  --installation-receipt qualified-position-vector-installation-receipt.json `
  --installation-root inactive-position-vector-calibrations `
  --activation-review qualified-position-vector-activation-review.json `
  --activation-review-receipt qualified-position-vector-activation-review-receipt.json `
  --activation-execution-approval qualified-position-vector-activation-execution-approval.json `
  --activation-execution-approval-receipt qualified-position-vector-activation-execution-approval-receipt.json `
  --activation-root active-position-vector-calibrations `
  --active-selection active-position-vector-calibrations/installed-arm-no-attachment/active-position-vector-calibration.json `
  --activation-receipt qualified-position-vector-activation-receipt.json `
  --integration-review qualified-position-vector-feedback-integration-review.json `
  --integration-review-receipt qualified-position-vector-feedback-integration-review-receipt.json `
  --integration-execution-approval qualified-position-vector-feedback-integration-execution-approval.json `
  --output qualified-position-vector-feedback-integration-execution-approval-receipt.json
```

The approval record has schema
`rocell.position_vector_calibration_qualified_feedback_integration_execution_approval.v1`.
It binds the accepted integration review and receipt plus every activation,
selection, payload, controller, profile, destination, response profile, and
conversion contract identity. The approver must be independent of the producer
and every earlier reviewer, approver, installer, and activator.

The command reproduces the complete chain before emitting
`rocell.position_vector_calibration_qualified_feedback_integration_execution_approval_receipt.v1`.
The receipt advances to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_INTEGRATION_EXECUTION` and authorizes only
that later exact integration execution. It does not load a runtime session,
open the controller or camera, request feedback, send a command, or authorize
motion. Output remains outside the installation and activation roots and is
never replaced.

To execute that approval offline, invoke
`execute-qualified-calibrated-feedback-integration` with every complete-chain
input used by the approval command. Replace its `--output` option with these
execution-specific options:

```powershell
--integration-execution-approval-receipt qualified-position-vector-feedback-integration-execution-approval-receipt.json `
--integration-root calibrated-position-vector-feedback-integrations `
--integrator-id feedback-integration-operator-12 `
--integrated-at 2026-10-24T23:00:00-04:00 `
--receipt-output qualified-position-vector-feedback-integration-receipt.json
```

The command replays the full evidence, fit, installation, activation, review,
and approval chain before creating anything. The integrator must differ from
the integration execution approver. The integration root must remain outside
the installation and activation roots, and the receipt must remain outside all
three roots. Existing integration descriptors and receipts are never replaced.

The immutable descriptor has schema
`rocell.position_vector_calibration_qualified_feedback_integration.v1` and is
published under the approved installation profile as
`calibrated-position-vector-feedback-integration.json`. It binds the installed
artifact and active selection hashes, controller and attachment profile,
conversion contract, response profile, and stable strict loader and converter
references. This keeps `no_attachment` and `stylus_attachment` integrations in
separate profile directories.

The resulting
`rocell.position_vector_calibration_qualified_feedback_integration_receipt.v1`
advances to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_RUNTIME_ADMISSION_REVIEW`. It explicitly
leaves runtime loading unauthorized. This execution creates no runtime session,
opens no controller or camera, requests no feedback, sends no command, and
authorizes no motion or physical action.

To review the immutable integration for later runtime admission, retain a
separate review record with schema
`rocell.position_vector_calibration_qualified_feedback_runtime_admission_review.v1`.
Invoke `review-qualified-calibrated-feedback-runtime-admission` with every
complete-chain and execution-specific input above. Replace `--receipt-output`
with these review-specific options:

```powershell
--integration calibrated-position-vector-feedback-integrations/installed-arm-no-attachment/calibrated-position-vector-feedback-integration.json `
--integration-receipt qualified-position-vector-feedback-integration-receipt.json `
--runtime-admission-review qualified-position-vector-feedback-runtime-admission-review.json `
--output qualified-position-vector-feedback-runtime-admission-review-receipt.json
```

The review record binds the exact integration descriptor and receipt, the
descriptor bytes, conversion contract, artifact, installed payload, active
selection, controller, attachment profile, destination, response profile, and
stable loader and converter references. The reviewer must be independent of
the fit producer and every earlier reviewer, approver, installer, activator,
and integrator. The command replays the complete chain, rereads the immutable
descriptor from its profile directory, and requires all supplied documents and
stored bytes to reproduce exactly. The review output must remain outside the
installation, activation, and integration roots and is never replaced.

An accepted review emits
`rocell.position_vector_calibration_qualified_feedback_runtime_admission_review_receipt.v1`
and advances only to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_RUNTIME_LOAD_EXECUTION_APPROVAL`. Runtime
loading remains unauthorized. This gate creates no runtime session, opens no
controller or camera, requests no feedback, sends no command, and authorizes no
motion or physical action. Run the complete review independently for
`no_attachment` and `stylus_attachment`; hashes and profile directories cannot
cross between them.

To approve a later runtime-load execution, retain a separate approval record
with schema
`rocell.position_vector_calibration_qualified_feedback_runtime_load_execution_approval.v1`.
Invoke `approve-qualified-calibrated-feedback-runtime-load-execution` with
every complete-chain, integration-execution, and runtime-admission input above.
Replace the admission command's `--output` option with these approval-specific
options:

```powershell
--runtime-admission-review-receipt qualified-position-vector-feedback-runtime-admission-review-receipt.json `
--runtime-load-execution-approval qualified-position-vector-feedback-runtime-load-execution-approval.json `
--output qualified-position-vector-feedback-runtime-load-execution-approval-receipt.json
```

The approval binds the accepted admission review and receipt, immutable
integration descriptor and stored bytes, conversion contract, calibration
artifact, installed payload, active selection, controller, attachment profile,
destination, response profile, and strict loader and converter references. The
approver must be independent of the fit producer and every earlier reviewer,
approver, installer, activator, integrator, and admission reviewer. The command
replays the complete chain and requires the supplied admission receipt to
reproduce exactly. Its output remains outside the installation, activation,
and integration roots and is never replaced.

An accepted approval emits
`rocell.position_vector_calibration_qualified_feedback_runtime_load_execution_approval_receipt.v1`
and advances only to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_RUNTIME_LOAD_EXECUTION`. The receipt
authorizes a later exact load, while this approval command itself creates no
runtime session, opens no controller or camera, requests no feedback, sends no
command, and authorizes no motion or physical action. Approval chains remain
separate for `no_attachment` and `stylus_attachment`.

To perform that exact offline load, invoke
`execute-qualified-calibrated-feedback-runtime-load` with every complete-chain,
integration-execution, admission-review, and runtime-load approval input above.
Replace the approval command's `--output` option with these execution-specific
options:

```powershell
--runtime-load-execution-approval-receipt qualified-position-vector-feedback-runtime-load-execution-approval-receipt.json `
--runtime-root calibrated-position-vector-feedback-runtime `
--runtime-session-id runtime-session-no-attachment-15 `
--loader-id feedback-runtime-loader-15 `
--loaded-at 2026-10-25T11:00:00-04:00 `
--receipt-output qualified-position-vector-feedback-runtime-load-receipt.json
```

The execution replays the complete chain and requires the supplied approval
receipt to reproduce exactly. It rereads the profile-scoped installed artifact,
checks its stored bytes and hashes, requires the integration's loader and
converter references to name the strict position-vector functions, and invokes
`load_position_vector_calibration`. The loader must differ from the execution
approver. The runtime root must remain outside the installation, activation,
and integration roots, while the receipt must remain outside all four roots.
Existing runtime sessions and receipts are never replaced.

The immutable session has schema
`rocell.position_vector_calibration_qualified_feedback_runtime_session.v1` and
is stored under the approved installation profile as
`calibrated-position-vector-feedback-runtime-session.json`. Its receipt has
schema
`rocell.position_vector_calibration_qualified_feedback_runtime_load_receipt.v1`
and advances only to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_RUNTIME_SESSION_VALIDATION`. The load is
offline: it opens no controller or camera, consumes no feedback, invokes no
feedback converter, sends no command, and grants no motion or physical
authority. Feedback requests remain unauthorized. Execute a distinct chain and
runtime profile for `no_attachment` and `stylus_attachment`.

To validate the exact loaded session offline, invoke
`validate-qualified-calibrated-feedback-runtime-session` with every input used
by the runtime-load command. Remove that command's `--receipt-output` option
and add:

```powershell
--runtime-session calibrated-position-vector-feedback-runtime/installed-arm-no-attachment/calibrated-position-vector-feedback-runtime-session.json `
--runtime-load-receipt qualified-position-vector-feedback-runtime-load-receipt.json `
--validator-id feedback-runtime-validator-16 `
--validated-at 2026-10-25T11:30:00-04:00 `
--validation-output qualified-position-vector-feedback-runtime-session-validation.json `
--receipt-output qualified-position-vector-feedback-runtime-session-validation-receipt.json
```

The command replays the complete load chain, requires the immutable runtime
session and its load receipt to reproduce exactly, and requires a validator
independent of the loader. It then selects only the retained `HELD_OUT`
observations and passes each exact T=1051 position vector through
`convert_position_vector_feedback` with the artifact's exact controller
binding. Every converted joint must remain within that joint's accepted
absolute error, and every mirrored shoulder residual must remain within the
loaded runtime tolerance. The validation output retains one result hash per
held-out sample and the observed maximum for every joint.

Successful validation emits
`rocell.position_vector_calibration_qualified_feedback_runtime_session_validation.v1`
and
`rocell.position_vector_calibration_qualified_feedback_runtime_session_validation_receipt.v1`.
The receipt advances only to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_REQUEST_ADMISSION_REVIEW`. Validation
uses retained observations: it does not claim a fresh controller response or
the arm's current state. It opens no controller or camera, requests no
feedback, sends no command, and grants no motion or physical authority. Both
outputs remain outside the installation, activation, integration, and runtime
roots and are never replaced. Validate `no_attachment` and
`stylus_attachment` as separate profile chains.

To review admission of the first calibrated feedback request, retain a
separate record with schema
`rocell.position_vector_calibration_qualified_feedback_request_admission_review.v1`.
Invoke `review-qualified-calibrated-feedback-request-admission` with every
runtime-validation input above. Remove `--validation-output` and
`--receipt-output`, then add:

```powershell
--runtime-session-validation qualified-position-vector-feedback-runtime-session-validation.json `
--runtime-session-validation-receipt qualified-position-vector-feedback-runtime-session-validation-receipt.json `
--feedback-request-admission-review qualified-position-vector-feedback-request-admission-review.json `
--output qualified-position-vector-feedback-request-admission-review-receipt.json
```

The review must bind the exact validation and receipt, runtime session and load
receipt, dataset, installed artifact, active selection, integration, controller,
attachment profile, loader, and converter. It must reproduce the fixed request
contract exactly: one ten-byte `{"T":105}` line with LF, one bounded T=1051
response, one-second read and write timeouts, a 65,536-byte maximum response
line, at most one request, and zero automatic retries. The contract also lists
the operator-present, adapter-powered, USB-connected, arm-secured,
arm-stationary, clear-area, and unchanged-firmware prerequisites that a later
execution gate must freshly establish. The reviewer must differ from the
runtime validator and loader.

An accepted review emits
`rocell.position_vector_calibration_qualified_feedback_request_admission_review_receipt.v1`
and advances only to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_REQUEST_EXECUTION_APPROVAL`. It does not
claim that any listed physical prerequisite is currently true. It opens no
controller or camera, writes zero bytes, requests no feedback, permits no
retry, and grants no motion or physical authority. The output remains outside
the installation, activation, integration, and runtime roots and is never
replaced. Keep `no_attachment` and `stylus_attachment` admission chains
separate; a later attachment change requires the corresponding profile chain.

To approve execution of that reviewed request, retain a separate approval with
schema
`rocell.position_vector_calibration_qualified_feedback_request_execution_approval.v1`.
Invoke `approve-qualified-calibrated-feedback-request-execution` with every
request-admission input above. Remove the admission command's `--output` option
and add:

```powershell
--feedback-request-admission-review-receipt qualified-position-vector-feedback-request-admission-review-receipt.json `
--feedback-request-execution-approval qualified-position-vector-feedback-request-execution-approval.json `
--output qualified-position-vector-feedback-request-execution-approval-receipt.json
```

The approval must bind the exact admission review and receipt, runtime session,
offline validation, dataset, installed artifact, active selection, integration,
controller, attachment profile, loader, converter, and fixed request contract.
Its approver must be independent of the admission reviewer, runtime validator,
runtime loader, integrator, and every earlier campaign actor. The approved
contract still permits only one ten-byte `{"T":105}` line with LF, one bounded
T=1051 response, and zero automatic retries.

An accepted approval emits
`rocell.position_vector_calibration_qualified_feedback_request_execution_approval_receipt.v1`
and advances only to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_REQUEST_EXECUTION`. Approval does not
establish the live execution prerequisites: operator presence, adapter power,
USB connection, secured and stationary arm, clear area, and unchanged firmware
must be checked again at execution. This offline gate opens no controller or
camera, sends zero bytes, receives no response, and grants no motion or physical
authority. The output remains outside the installation, activation,
integration, and runtime roots and is never replaced. Approve `no_attachment`
and `stylus_attachment` through separate chains.

### One-shot calibrated feedback execution boundary

`application/calibrated_position_vector_feedback_execution.py` joins an exact
execution-approval receipt to one injected transport exchange. Before invoking
the exchange it reproduces the complete approval chain, reloads the installed
calibration artifact, and rechecks its controller binding. The caller must also
supply a fresh
`rocell.position_vector_calibration_qualified_feedback_request_execution_prerequisites.v1`
record. That record is valid for at most five minutes and requires the operator,
adapter power, USB connection, secured and stationary arm, clear area, and
unchanged firmware to be confirmed for the same runtime session.

The boundary calls the injected exchange exactly once with the fixed ten-byte
`{"T":105}` request contract. It accepts only immutable exchange evidence that
records one write, one response, zero retries, zero motion commands, successful
cleanup, and an installed `POSITION_VECTOR_NAMED_POSE` T=1051 response. It then
uses the approved calibration artifact to convert the seven raw counts into the
six bounded canonical joint observations.

Success emits
`rocell.position_vector_calibration_qualified_feedback_request_execution_receipt.v1`
and advances only to
`CALIBRATED_POSITION_VECTOR_FEEDBACK_REQUEST_EXECUTION_REVIEW`. The receipt
binds the approval, fresh prerequisites, exchange evidence, response bytes,
controller identity, attachment profile, and calibrated observation by
canonical SHA-256. It grants no motion, contact, retry, persistent connection,
or physical authority. Another feedback request requires another approval and
new physical prerequisites.

`providers/windows/calibrated_position_vector_serial_adapter.py` now supplies
the matching one-shot serial adapter without changing the older full-Waveshare
worker. It creates a unique attempt journal before constructing or opening the
transport, confirms a quiet receive buffer without purging it, commits the write
attempt before sending the fixed ten bytes, accepts only one installed
position-vector response, and records close/cleanup before returning the exact
exchange-evidence schema above. A short write, startup input, malformed or wrong
profile response, timeout, close uncertainty, interrupted journal, or reused
attempt is terminal and cannot be retried.

The adapter has no public CLI and this increment performs no live access. Its
transport is injected so the complete lifecycle can be tested against a sealed,
hardware-incapable implementation. The next integration boundary must compose
it with the already reviewed non-purging Windows connection and owned-process
supervisor, pin that composition to the calibrated approval and controller
identity, and retain the journal directory in the governed evidence export.
Only after that production composition is independently reviewed may a newly
confirmed physical attempt be considered.

The child-side production boundary is now installed. A
`CalibratedPositionVectorBinding` admits only an exact physical reviewed
controller, a freshly reproduced identical OS identity, the calibration's exact
VID/PID/unit/firmware binding, the closed application request, a pinned runtime
hash, the current child PID, and the original monotonic deadline. The admitted
Win32 facade remains inert until `open()` and can issue only the existing fixed
T105 payload through `NonPurgingSerialConnection`. Status performs no hardware
access and grants no motion authority.

Every terminal or interrupted adapter journal can now be verified and copied
byte-for-byte into a unique immutable evidence directory. Its canonical
manifest records each original file's byte count and SHA-256, request identity,
event count, recovery disposition, and explicit no-retry/no-motion authority.
Tampered journals fail before export; incomplete exports retain their partial
bytes and cannot be silently replaced.

This remains private child-side composition with no CLI and performed no live
access. The next dependency is the parent-side source-pinned archive,
registration, wire codec, and owned-process result validation that invokes this
boundary and retains its journal export.

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

## Owned native feedback supervisor (2026-10-25)

The calibrated position-vector adapter now has a private, source-pinned parent
and child process composition. Staging creates a deterministic dependency
archive, pins the exact Python executable and child entry, reconstructs the
reviewed controller and fresh identical USB identity, and binds the installed
firmware, closed request, runtime hash, and original monotonic deadline into a
single request. The generic Windows owner supplies the one-use dispatch lock,
bounded process, stdin/stdout limits, timeout, and cleanup receipt.

The child performs one fixed T105 feedback exchange and exports its durable
journal into its assigned directory. The parent accepts a result only when its
request and binding hashes match and every retained journal file reproduces the
child's immutable manifest. Both the result and export explicitly deny retry,
motion, connection, and physical authority. Import-audit and unit tests are
hardware-incapable, and no public live command was added.

## Owned application orchestration (2026-10-25)

The private application boundary now splits execution into preparation and
completion. Preparation reproduces the approval receipt, checks the fresh
physical-prerequisite interval, loads the selected calibration and controller
binding, and freezes the exact T105 request before any child may start. Staging
then creates an exclusive per-attempt directory and durable application claim;
that directory is never reused, including after a child or retention failure.

The host rechecks cancellation, context, and monotonic lifetime immediately
before its exact dispatch authorizer runs. It supervises the source-pinned
child once, verifies the child's request-associated immutable journal export,
and passes only a successful verified exchange into calibrated conversion.
Terminal child evidence is retained without a receipt or retry. No public live
command or hardware run was added by this increment.

The attempt directory also retains canonical `supervisor-request.json` and
`supervisor-result.json` documents with exclusive creation semantics. These
copies let a later process reproduce the request, result, and exported journal
associations without trusting process memory or reopening the controller.

## Independent calibrated execution review (2026-10-25)

The private review gate now loads those retained supervisor documents, the
exclusive application claim, and the child journal manifest. It reruns the
closed protocol and file-digest checks, matches the exact request and exchange
evidence to the execution receipt, reloads the selected calibration, and
reproduces the calibrated feedback from the retained response line. A review
record is accepted only when all six content bindings match and the reviewer
is distinct from the physical operator.

Both `ACCEPT` and `REJECT` decisions produce a deterministic review receipt.
Only acceptance carries the reproduced observation forward, and even then its
next required gate is
`CALIBRATED_POSITION_VECTOR_OBSERVATION_STATE_ADMISSION`. Rejection carries no
calibrated observation. Neither branch retries, opens hardware, or grants
motion, connection, contact, or physical authority. No public live command or
additional hardware run was added.

The next dependency is the observation state-admission gate: bind one accepted
review receipt to an explicit downstream consumer and freshness policy before
that consumer may use the calibrated observation. Any future physical use
still needs a new current operator and hardware-state confirmation.

## Calibrated observation state admission (2026-10-25)

The private state-admission gate now binds one accepted independent review back
to the exact execution receipt and its original observation time. Admission
also freezes the current calibration, controller binding, attachment profile,
attempt, runtime session, named consumer, and consumer-context digest. Crossed,
rejected, stale, differently configured, or incompletely bound evidence fails
closed.

Freshness is explicit and bounded twice: the observation age may be no more
than five minutes, and the issued consumer window may be no more than one
minute. The caller may choose tighter limits. A successful receipt carries the
reviewed calibrated feedback only to that named state consumer and requires
use before `valid_until`. It grants no retry, motion, connection, contact, or
physical authority, and any future physical use still requires a new current
operator and hardware-state confirmation. No hardware was opened and no live
command was added.

The next dependency is named-consumer redemption: verify the admitted receipt,
consumer context, and freshness again at use, then durably prevent a second
consumer use of the same admission.

## Named-consumer observation redemption (2026-10-25)

The private redemption gate now verifies the exact state-admission receipt,
named consumer, actual consumer-context digest, timestamp ordering, and both
freshness ceilings again at the instant of use. It derives a stable redemption
identity from the complete admission receipt and exclusively creates one
durable record before returning the calibrated observation. A concurrent or
later attempt for the same admission fails closed; an interrupted publication
also leaves that admission terminal rather than permitting an uncertain retry.

The redemption receipt is the observation handoff to the named consumer. It
preserves the execution, review, calibration, controller, attachment, and
consumer bindings and explicitly denies replay, automatic retry, motion,
connection, contact, and physical authority. This increment opens no hardware
and adds no live command.

The next dependency is idempotent named-consumer state ingestion. The consumer
state store must use `redemption_id` as its deduplication key, apply the
observation at most once, and make a repeated delivery return the original
state result without applying the observation again.

## Idempotent named-consumer state ingestion (2026-10-25)

The named consumer now has an immutable state-event store keyed by the exact
`redemption_id`. The first fresh delivery is written and synchronized before it
is returned. Simultaneous identical deliveries converge on one stored result,
and any later identical delivery returns that original receipt without applying
the observation again. A different payload that claims the same key, an altered
consumer context, unsafe storage, or a stale first delivery fails closed.

The stored event preserves the execution, review, admission, redemption,
calibration, controller, attachment profile, and consumer bindings. It remains
an observation record rather than a mutable current-state pointer and grants no
retry, motion, connection, contact, or physical authority. This increment opens
no hardware and adds no live command.

The next dependency is calibrated-state snapshot read admission. That boundary
must select a stored immutable event, recheck the named reader and current
profile context, and expose a typed snapshot to later camera-feedback and motion
planning without turning observation data into movement authority.

## Calibrated-state snapshot read admission (2026-10-25)

The stored calibrated state can now be selected for one separately named
read-only consumer. The admission gate reloads the canonical immutable event,
binds its digest to the exact reader context, and rechecks the current consumer
epoch, calibration, controller, and attachment profile before exposing the
typed snapshot. Changed, crossed, stale, noncanonical, missing, or tampered
state fails closed.

Snapshot age is bounded to five minutes and each read admission can remain valid
for no more than one minute; callers may choose tighter limits. The receipt
preserves the complete observation provenance while granting only the named
reader access to calibrated feedback. It grants no retry, controller write,
motion, connection, contact, or physical authority. This increment opens no
hardware and adds no live command.

The next dependency is camera-feedback state-fusion admission. It must bind one
camera observation, its camera calibration and board registration, and this
exact state snapshot before any fused estimate can reach planning.

## Camera-feedback state-fusion admission (2026-10-25)

One qualified fixed-camera board-pose observation can now be bound to one exact
calibrated-state snapshot for a separately named fusion consumer. The gate
rechecks the snapshot reader and fusion epoch, the observation quality and
zero-authority flags, camera-intrinsics binding, tag-map binding, keyboard-to-
board registration, and the active attachment profile. Every source document
is bound by its canonical SHA-256 digest.

Camera and arm-state timestamps may differ by no more than two seconds, and a
fusion receipt can remain valid for no more than thirty seconds; callers may
choose tighter limits. The receipt carries the qualified camera observation
and calibrated feedback together so later planning cannot silently combine
records from different captures, calibrations, tag maps, reader epochs, or
attachment profiles.

This is a read-only provenance and freshness gate. It does not estimate missing
geometry, certify clearance, emit a target or trajectory, authorize contact,
open hardware, retry an operation, or grant physical authority.

The next dependency is fused camera/state planning admission. That boundary
must select a target from the admitted observation, revalidate collision and
clearance evidence for the active attachment profile, and produce a bounded
plan candidate without granting execution authority.

## Fused camera/state planning admission (2026-10-25)

The fused camera and calibrated-state receipt can now be admitted to one named
planning context. The gate selects one exact key from the complete board-space
candidate set and joins it to the corresponding robot-frame localization
candidate. It requires matching target-profile lineage, the same active
attachment profile, and the exact camera/state fusion and board-registration
digests.

The selected profile must also reproduce the robot-localization candidate hash
carried by the reviewed installed-clearance intake. Bare-jaw and stylus inputs
remain separate. The receipt carries the installed collision-profile and
clearance-policy digests into the plan candidate, bounds requested hover
clearance and waypoint count, and expires within both fifteen seconds and the
source fusion lifetime.

This boundary deliberately stops before trajectory construction. Installed
collision evidence is accepted only as an input to the next screen; continuous
clearance remains unverified. The receipt emits no trajectory or controller
command and grants no retry, motion, contact, or physical authority.

The next dependency is profile-specific trajectory construction and collision
qualification. It must construct a bounded route from the admitted calibrated
start state through hover and target waypoints, then prove the exact route
against the selected installed collision profile before any execution review.

## Fused target exact-route qualification admission (2026-10-26)

The admitted fused-camera target can now be joined to the existing deterministic
typing trajectory and installed-geometry collision pipeline. The gate parses the
exact execution plan, verifies the selected key coordinates and requested hover
clearance, and confirms that every matching action has the expected hover,
contact, and retract waypoints in the sealed trajectory plan.

That target lineage must continue through the profile-separated route-screen and
collision-partition manifests into a ready route-bound collision qualification.
The active bare-jaw or stylus profile, trajectory hash, partition digest, route
envelope, and installed collision-profile digest must all agree. Crossed
profiles, stale planning receipts, altered coordinates, modified waypoints,
incomplete collision evidence, or rejected routes fail closed.

This reuses the reviewed route machinery instead of creating a second planner.
It proves that the camera-selected key belongs to the exact route that completed
offline IK and installed-geometry collision qualification. It does not claim
that the arm is currently at that route's entry state. The result contains no
controller command or physical authority.

The next dependency is route-bound fresh observed-entry qualification. A fresh
arm observation must be proven compatible with the exact qualified route before
any later execution review may consider movement.

## Fused state to route-entry admission (2026-10-26)

The fresh calibrated arm snapshot is now joined all the way to the existing
route-bound entry qualification. The gate verifies the immutable snapshot,
camera/state fusion, planning receipt, and exact-route admission digests in
order. All four stages must retain the same active bare-jaw or stylus profile,
remain within their original validity windows, and preserve zero authority.

The passing route-entry qualification must name the same route-bound collision
receipt, route envelope, installed collision profile, and observed-entry
document as the camera-selected route. The snapshot runtime session must also
match the observed entry's controller session. Finally, the six-joint
calibrated position vector is projected into the five canonical arm-planning
joints and compared exactly with the observed entry's retained start state.
This prevents a valid camera target and a separately valid route entry from
being combined when they came from different physical observations.

This completes the read-only camera/state-to-route-entry evidence chain. It
does not authorize motion or contact, emit a command, open hardware, or imply
that independent execution release gates have passed. A later execution review
must still consume this receipt and satisfy its own current operator,
freshness, dynamics, verifier, and per-action policy requirements before any
physical request can be considered.

## Fused route action-review admission (2026-10-26)

The fresh camera/state route-entry receipt can now select one exact action from
the camera-selected route and cross the final zero-authority seam into the
existing single-action execution-review pipeline. The adapter independently
rechecks the exact route and route-entry hashes, installed collision profile,
route envelope, attachment profile, runtime session, continuous entry and route
clearance, measured entry dynamics, and retained telemetry coverage. The route
entry must be consumed within five seconds, and the selected action index must
belong to the target action set sealed by the exact-route admission.

Admission additionally requires three separately sealed records. A current
operator confirmation is valid for at most thirty seconds and affirms operator
presence, reachable shutdown, a clear area, and a secured stationary arm. An
independently approved physical effect-verifier binding identifies the exact
expected result and remains valid for at most five minutes. A per-action policy
binds that verifier, expected effect, interaction, route, profile, and action
while requiring single-use review and prohibiting automatic retry.

The resulting receipt is ready only for
`single_action_execution_review_v1`. It does not create that review, issue or
consume a permit, encode a wire command, open hardware, authorize contact, or
grant physical authority. The existing review boundary must still authenticate
its controller, collision-policy, T102, contact-envelope, and configuration
inputs; the safety supervisor remains the only permit issuer.

## Fused admission to single-action execution review (2026-10-27)

The exact fused action admission can now create the existing single-use
execution review without reconstructing or bypassing its safety evidence. The
admission carries a sealed `valid_until` equal to the earliest expiry of the
fresh route entry, operator confirmation, and independent effect verifier. The
bridge rejects a delayed call and also rejects a review whose monotonic lifetime
would extend beyond the remaining admission window.

The camera-selected key, action index, interaction, controller session, and
installed collision profile must match the model proposal, measured trajectory,
contact envelope, and installed collision-policy qualification. The existing
review builder then independently rechecks batch/proposal/trajectory lineage,
continuous collision and contact policy, installed controller evidence, T102
target and settings, configuration epoch, session, and every evidence expiry.
Its resulting review digest includes the fused admission digest, preserving the
camera, operator, verifier, and route lineage through one-time consumption and
later supervisor consideration.

This is still a zero-authority boundary. It does not consume the review, issue a
permit, open hardware, encode or write a command, authorize contact, retry an
action, or move the arm. The safety supervisor remains the only permit issuer,
and the sole-writer and settlement lifecycle remain downstream requirements.

## Fused execution review to supervisor permit (2026-10-28)

The fused execution review now has one explicit runtime entry into the existing
safety-supervisor permit path. The session accepts only a review containing the
fused action-admission digest, derives keyboard-contact or hover capability from
the review, consumes it once, and evaluates current calibration, interlocks,
runtime health, and released build state at the same monotonic instant. Permit
expiry cannot extend beyond the review deadline.

The permit admission retains the fused action-admission digest and creates the
existing hash-chained action lifecycle in `ACCEPTED`. A process-independent
machine reservation keyed by review digest prevents a reconstructed review gate
from obtaining another permit through a newly timestamped receipt. Reservation
precedes supervisor evaluation, so a failed preflight burns the review and does
not create a retry path.

Only `SafetySupervisor` can create the short-lived exact-goal permit. This
orchestrator performs no serial access, command encoding, controller write,
movement, contact, settling check, or effect verification. Those physical and
outcome boundaries remain required after admission.

## Fused permit to sole-writer settlement rehearsal (2026-10-28)

The typed fused permit result can now enter the existing production-shaped
T=102 runtime rehearsal without callers separating or replacing its permit,
admission, and lifecycle. The exact decoded T=102 target must be one of the
reviewed goals, and its frame must match the sole writer, controller session,
configuration epoch, and encoding profile. The dispatch instant is also the
final permit-consumption instant, preventing a second caller-controlled clock
from widening the authority window.

The terminal report now exposes the fused action-admission digest and exact
review-consumption digest in addition to the permit binding. One modeled write,
one correlated accepted-once acknowledgment, and consecutive fresh T=1051
joint samples can close the lifecycle as settled. A crossed target rejects
before permit consumption or any write attempt. Zero, partial, disconnected,
unacknowledged, stale, or unsettled outcomes close as failed or uncertain and
never authorize retry or successor movement.

This remains a hardware-incapable contract rehearsal. Its byte sink cannot open
a port or reach the controller, its acknowledgment and feedback are supplied
test evidence, and its physical write count is always zero. Native sole-writer
transport, authenticated controller feedback, observed physical settling, and
independent keyboard-effect verification remain separate release gates.
