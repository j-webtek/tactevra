# Camera Arrival-Day Checklist V1

## Purpose and authority

This checklist turns the final fixed-camera arrival into a bounded evidence
collection session. It coordinates files and reviews; it does not authorize arm
movement, controller startup, contact, or deployment qualification.

The canonical dry-run map is
`software/ai/eval/camera_arrival_kit_dry_run_v1.json`. It contains 15 required
evidence slots and intentionally contains no measured hashes. Never edit that
file into a physical record. Create physical originals under an owner-selected
external evidence root and bind each with a sidecar conforming to
`software/ai/schemas/camera_arrival_original_v1.schema.json`.

## Before connecting the camera

- [ ] Final camera housing and support revision are identified.
- [ ] Camera is rigidly secured in its intended fixed-overview position.
- [ ] Safety tether, fasteners, witness marks, cable routing, and strain relief
  are visible and ready to document.
- [ ] Arm is disabled or held outside the capture volume.
- [ ] No camera capture is combined with a motion test.
- [ ] Board, robot base, keyboard, tool, lighting, and allowed placement domain
  are frozen for this configuration epoch.
- [ ] An external evidence root exists outside Git with restricted ownership.
- [ ] System clock, operator identity, session ID, and configuration-epoch ID
  are available for every sidecar.

Stop immediately if the support is not rigid, the cable can enter the arm
sweep, an identity is ambiguous, or any physical component moves after the
session begins.

## Verify the software kit

From a clean checkout, run the focused zero-I/O checks:

```powershell
cd software
python -m pytest `
  tests/unit/test_camera_arrival_kit_v1.py `
  tests/unit/test_camera_arrival_original_schema_v1.py `
  tests/integration/test_retained_camera_arrival_kit_v1.py `
  ai/tests/test_physical_camera_localization_campaign.py `
  ai/tests/test_physical_camera_localization_evaluator.py `
  tests/unit/test_camera_support_optics_epoch_intake_v1.py -q
```

The retained dry run must report zero measured slots, camera opens, controller
starts, writes, movements, and physical authority. A synthetic result never
advances the measured configuration epoch or deployment registry.

Before and after each collection block, inventory the external evidence root
with the read-only structural preflight:

```powershell
python -m rocell.application.camera_arrival_evidence_preflight_v1 `
  --workspace . `
  --evidence-root <external-root>
```

The source-checkout wrapper remains available at
`software/scripts/preflight_camera_arrival_evidence_v1.py`; the installed-module
command and wrapper use the same application entry point.

An incomplete root exits nonzero and names each missing or invalid slot. A
complete result says only `READY_FOR_OFFLINE_QUALIFICATION_REVIEW`; it does not
accept calibration, advance an epoch, update a registry, open either device, or
authorize movement.

After that structural result is complete, bind every original to the exact
consumer source, downstream schema, and field binding in the current checkout:

```powershell
python -m rocell.application.camera_arrival_consumer_handoff_v1 `
  --workspace . `
  --evidence-root <external-root>
```

The source wrapper is
`software/scripts/route_camera_arrival_consumers_v1.py`. A successful result
says only `READY_FOR_OFFLINE_CONSUMER_VALIDATION`. It proves that the intact
15-slot epoch can be routed to the current repository dependencies; it does not
invoke those consumers, complete their validation, install qualification, or
grant physical admission.

Each downstream consumer must emit a receipt conforming to
`software/ai/schemas/camera_arrival_consumer_validation_receipt_v1.schema.json`.
The receipt must bind the handoff, original source/sidecar hashes, consumer
source/schema hashes, exact field binding, validator identity/version, and
consumer output. Failed validation is retained as `BLOCKED`; it is never
rewritten as a missing receipt. The aggregate contract in
`rocell.application.camera_arrival_consumer_validation_v1` accepts all 15
receipts only when they match the handoff exactly. Its strongest result,
`CONSUMER_VALIDATION_COMPLETE_FOR_OFFLINE_REVIEW`, still does not commission the
epoch, update the deployment registry, install qualification, or authorize
physical execution.

The first domain adapters live in
`rocell.application.camera_arrival_consumer_emitters_v1`. They translate the
existing camera/support assessment (four routes), campaign preflight (two
routes), held-out localization evaluation (two routes), typed planner snapshot
(five routes), and typed installed collision profile (two routes) into the
common receipt without weakening their native pass/block semantics. They accept
only a ready, matching handoff, preserve native failure blockers and output
hashes, and bind the validator version to the mapped consumer-source hash.
Route coverage alone is not completion: incomplete installed geometry or a
configuration-sampled cable envelope remains `BLOCKED` even when every route
has emitted a receipt.

The same three stages can be composed into one read-only command. Before any
consumer receipts exist, omit `--receipt-root`; after consumers have written
their exact canonical receipts, point it at that separate directory:

```powershell
python -m rocell.application.camera_arrival_commissioning_orchestrator_v1 `
  --workspace . `
  --evidence-root <external-root> `
  --receipt-root <external-receipt-root>
```

The source wrapper is
`software/scripts/run_camera_arrival_commissioning_v1.py`. Its possible normal
states are structural evidence blocked, consumer validation pending, consumer
validation blocked, and complete for offline review. Even its strongest state
keeps epoch advance, registry update, qualification installation, camera and
transport opens, controller startup, commands, writes, movements, and physical
authority at zero. Receipt filenames are exactly `<artifact_id>.json`; extra,
symlinked, oversized, malformed, crossed, or authority-bearing entries reject.

Before arrival day, reproduce the frozen PC12 fault campaign:

```powershell
python -m rocell.application.camera_arrival_fault_campaign_v1 --workspace .
```

The result must match
`software/ai/eval/camera_arrival_fault_campaign_v1.json`: 18 of 18 synthetic
cases pass, with zero camera or transport opens, controller starts, commands,
writes, movements, or authority. A fault-campaign pass qualifies the offline
intake behavior only; it says nothing about the future camera or measurements.

After a mapping-based native consumer has produced and retained its own output,
emit its common receipt with:

```powershell
python -m rocell.application.camera_arrival_consumer_operator_v1 `
  --handoff <handoff.json> `
  --artifact-id <artifact-id> `
  --native-output <native-output.json> `
  --validated-at-utc <UTC-timestamp> `
  --output-root <external-receipt-root>
```

The wrapper never overwrites `<artifact-id>.json`. Planner snapshots and
installed collision profiles stay typed objects and use
`write_camera_arrival_consumer_operator_receipt_v1` from their native Python
consumer; they are intentionally not reconstructed through the generic JSON
CLI. Both paths call the same existing domain emitters and preserve native
blockers, output hashes, and zero-authority semantics.

## Collect the four camera/support originals

Use the existing explicitly authorized camera onboarding workflow to collect
and retain, in order:

1. `camera_receipt`
2. `camera_identity`
3. `camera_mode_controls`
4. `support_witnesses`

For every source file:

- [ ] Keep the original bytes unchanged.
- [ ] Record its external-root-relative path, byte size, and lowercase SHA-256.
- [ ] Record capture time and configuration-epoch ID.
- [ ] Complete the independent review fields.
- [ ] Reject rather than repair an incomplete or mismatched original.

Close and reopen the camera using the commissioned path and verify that
persistent identity, resolution, frame rate, pixel format, orientation, focus,
exposure, gain, and white balance remain unchanged. Drift ends the epoch.

## Collect calibration originals

Commission and retain independent evidence for:

- [ ] Camera intrinsics and distortion.
- [ ] Camera-to-board transform.
- [ ] Board-to-robot transform.
- [ ] Keyboard-to-board transform.
- [ ] Tool-to-joint/TCP transform.

Every calibration record must declare units, method, uncertainty, source-file
hashes, held-out validation evidence, and configuration epoch. Nominal CAD,
photographic estimates, model predictions, and manually adjusted predictions
are not measured calibration.

Stop if a required uncertainty is missing, a held-out residual fails its bound,
or any calibrated object moves.

## Collect installed-workcell originals

- [ ] Installed robot, base, clamp, board, camera/support, keyboard, tool, and
  nearby fixtures are represented in the installed geometry record.
- [ ] Cable envelope covers every allowed arm posture and cable-routing state.
- [ ] Keyboard profile binds physical dimensions and the exact target catalog.
- [ ] Tool profile binds dimensions, effective tip, mass/center-of-gravity where
  required, and the tool-to-joint calibration.
- [ ] Every record has an accepted review sidecar and immutable source hash.

Incomplete geometry remains unbounded. It cannot be replaced with an increased
software clearance guess.

## Run the localization campaign

Follow
`software/ai/docs/PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md`. Keep calibration
and held-out sessions disjoint, preserve failed and obstructed images, and use
independently surveyed truth.

Run preflight only after all external files exist:

```powershell
python software/ai/eval/preflight_physical_camera_campaign.py `
  --campaign <external-root>\localization\campaign.json `
  --evidence-root <external-root> `
  --output <external-root>\localization\preflight.json
```

Then run the frozen evaluator exactly once on the held-out split as documented
in the campaign runbook. An offline `QUALIFICATION_RECOMMENDED` result remains
a review recommendation; it does not install qualification or authorize motion.

## Mandatory stop conditions

Stop and retain the failure evidence on any of these conditions:

- Camera identity, mode, controls, focus, crop, or orientation drifts.
- Camera support, board, robot base, keyboard, tool, or cable routing moves.
- A source byte count or SHA-256 differs from its sidecar.
- A physical original is missing, unreviewed, or rejected.
- Calibration and held-out splits overlap by image, truth, session, or capture.
- Required uncertainty is absent or exceeds a target safe-region margin.
- Installed collision geometry or cable envelope is incomplete.
- Any workflow unexpectedly opens the controller, writes hardware, moves the
  arm, advances an epoch, or updates a deployment registry.

## Arrival-day completion record

The evidence-collection session is complete only when every one of the 15
arrival-kit slots has a separately retained physical original, valid sidecar,
accepted review, immutable hash, and downstream-consumer receipt. Completion
means the evidence is ready for offline qualification review. It does not mean
the arm may move or type.

Continue from that offline-review boundary using
[Camera-to-First-Key Commissioning Runbook V1](CAMERA_TO_FIRST_KEY_COMMISSIONING_RUNBOOK_V1.md).
Its machine-readable fixture-replacement registry connects the camera-arrival
evidence to the ARM-149-ARM-155 observed-pose, collision, dynamics, tracking,
settling, and telemetry-coverage chain. Camera-arrival completion alone cannot
substitute for any of those installed physical qualifications.

## Retain and resume one arrival session

Create the manifest once with caller-selected candidate identities and a new
output path:

```powershell
python software/scripts/build_camera_arrival_session_manifest_v1.py `
  --workspace . `
  --evidence-root <external-root> `
  --receipt-root <external-receipt-root> `
  --session-id <safe-session-id> `
  --configuration-epoch-candidate <candidate-id> `
  --camera-profile-id <camera-profile-id> `
  --camera-profile-sha256 <64-lowercase-hex> `
  --tool-profile-id <tool-profile-id> `
  --tool-profile-sha256 <64-lowercase-hex> `
  --output <new-session-manifest.json>
```

The create command uses exclusive creation and never overwrites an earlier
manifest. A nonzero exit while collection is incomplete or validation remains
blocked is expected; retain its manifest and blockers.

After a restart, verify the retained session against the same evidence and
receipt roots:

```powershell
python software/scripts/verify_camera_arrival_session_manifest_v1.py `
  --workspace . `
  --evidence-root <external-root> `
  --receipt-root <external-receipt-root> `
  --manifest <retained-session-manifest.json>
```

Verification re-runs the PC11 boundary and requires the complete rebuilt
manifest to equal the retained manifest. Any source, route, receipt, state, or
profile/epoch binding difference stops the resume. Selecting a different epoch
or profile intentionally creates a different manifest and therefore a new
session; it cannot replace the retained session during verification. Even the
offline-review-complete state keeps measured commissioning held and grants no
camera, controller, transport, command, write, movement, or installation
authority.
