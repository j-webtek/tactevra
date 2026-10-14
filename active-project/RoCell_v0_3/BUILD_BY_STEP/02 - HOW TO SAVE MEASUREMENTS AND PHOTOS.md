# Evidence and canonical-record workflow

Use one build ID from Step 00 through Step 15. The step folders hold raw evidence; the canonical configuration files hold reviewed gate and lifecycle state. They do not synchronize automatically.

## Two hashes with different jobs

- **Package definition hash:** `5f18f598920dc04d0066e1a233f9f313ae48121094868790a4489995069d5313`. This binds build evidence to the procedure, models, gate schema, job definitions, and acceptance logic. If it changes, affected evidence is stale and must be reviewed/repeated.
- **Canonical snapshot hash:** `3a3d1894c12af5f94fa453250f0ddb884f3cdda1febb53707d1a1395cb7f9adf`. This fingerprints the current complete canonical snapshot, including mutable reviewed gate and lifecycle values. It normally changes as valid evidence is synchronized; that change alone does not invalidate earlier evidence whose package definition hash still matches.
- Never rewrite immutable raw evidence merely to replace an older canonical snapshot hash. Preserve the original snapshot field and regenerate the package so dashboards show the current snapshot.

## 1. Record all three route decisions

Record an explicit `yes` or `no` for all three routes before releasing route-dependent jobs. Run exactly one command from each row; do not rely on a default value.

| Decision | Select this route | Do not select this route |
| --- | --- | --- |
| Phone stylus tool | `python scripts/record_print_measurement.py --route phone_stylus_route --selected yes` | `python scripts/record_print_measurement.py --route phone_stylus_route --selected no` |
| Keyboard rod tool | `python scripts/record_print_measurement.py --route keyboard_rod_route --selected yes` | `python scripts/record_print_measurement.py --route keyboard_rod_route --selected no` |
| Fixed-mast camera fallback only (not the arm-camera route) | `python scripts/record_print_measurement.py --route camera_mast_optional --selected yes` | `python scripts/record_print_measurement.py --route camera_mast_optional --selected no` |

At least one tool route—`phone_stylus_route` or `keyboard_rod_route`—must be `yes`. `camera_mast_optional` refers only to the independent fixed eye-to-hand fallback, never the intended arm-mounted camera. Its `yes` value records qualification scope only; it does not authorize printing. Jobs 03C3, 06, 07A, and 07B remain blocked until `fixed_camera_fallback_architecture_released` is PASS against the exact controlled camera-decision hash.

After recording all three decisions, regenerate and run `python scripts/build_step_packages.py --check` before initializing Step 00. If a route selection changes after evidence work begins, place the build on HOLD and start a new build ID after regeneration so conditional test rows cannot be lost.

## 2. Initialize the same build ID in every step

At Step 00, choose a unique name such as `2026-08-31_CELL-A`, select it explicitly, regenerate, verify the package, and then copy Step 00's refreshed template once:

```powershell
python scripts/set_active_build.py --build-id 2026-08-31_CELL-A
python scripts/build_step_packages.py
python scripts/build_step_packages.py --check
python scripts/initialize_step_evidence.py --step 00
```

For each later step, initialize only after the preceding signed step has been regenerated as `COMPLETE` and the next step is shown as `READY TO START`. The initializer uses the same active build ID, accepts only `READY_TO_START`, and refuses to overwrite an existing folder. Never pre-initialize route-dependent templates, reuse a build ID, or edit `BUILD_ID_TEMPLATE/`.

## 3. Capture and record raw evidence

Save photos, native QIDI projects, calibration outputs, and reports below the current build-ID folder before recording them. Every `--evidence` value must be relative to that build-ID folder, remain contained within it, and identify a regular file that already exists. Neither `measurement_record.json` nor `signoff.json` may cite itself. Repeat `--evidence` for multiple files; record corrections and retests without erasing a failed first result.

Use the controlled result helper once for every pre-populated test ID. Example:

```powershell
python scripts/record_step_result.py --step 03 --test 03-A --value "seats by hand; no rocking" --unit "N/A" --instrument "visual inspection" --evidence "photos/03-A.jpg" --result PASS --operator "NAME"
```

The helper safely updates the active build's `measurement_record.json`. Raw JSON editing is an advanced recovery fallback only and must never bypass containment, schema, or completeness validation.

## 4. Review before changing a canonical gate

Compare every result with the corresponding step limit. A canonical gate may be set to PASS only when all required values and context are populated, its evidence identifies this build ID, and no applicable row failed.

From the project root, use the controlled recorder for supported gate fields:

```powershell
python scripts/record_print_measurement.py --help
python scripts/record_print_measurement.py --context operator=NAME --context date=YYYY-MM-DD --context printer_serial=SERIAL --context measurement_tool_id=TOOL_ID --context evidence_directory=BUILD_ID_PATH --context qidi_studio_version=VERSION
python scripts/record_print_measurement.py --gate GATE_ID --status PASS --value FIELD=VALUE --evidence-note "BUILD_ID evidence path and summary"
```

Repeat `--value` for every field required by that gate. The recorder rejects PASS while required values or test context are blank. Diagnostic native QIDI projects stay in Step 00 evidence; `--qidi-job` is for non-diagnostic release jobs only.

## 5. Advance print-job and kit state only in order

For Step 00, validators derive `READY_TO_SLICE` automatically when a selected job's prerequisites pass; operators do not set it and there is no evidence slot for it. After a job is reported READY_TO_SLICE, advance exactly one manual state at a time with the controlled recorder:

```powershell
python scripts/record_job_lifecycle.py --job 00A --state SLICE_REVIEWED --operator "NAME" --evidence "BUILD_BY_STEP/00 - Measure Hardware and Print Approved Parts/06 - SAVE MEASUREMENTS AND PHOTOS/BUILD_ID/..."
```

Then advance sequentially through `PRINTED` → `POSTPRINT_PASS` → `KITTED` → `ASSEMBLY_PASS` → `IN_SERVICE`, running the command once per completed state. The recorder rejects skips, unselected jobs, unresolved prerequisites, and missing mapped gates. Reconcile `JOB_KITS.csv` counts, QA fields, evidence reference, and storage label before KITTED; never infer KITTED from a successful print alone.

## 6. Regenerate and verify after canonical updates

Run the applicable commands from the project root:

```powershell
python scripts/validate_print_readiness.py
python scripts/generate_build_tracker.py
python scripts/generate_job_cards.py
python scripts/sync_documentation.py
python scripts/validate_release_package.py
python scripts/build_step_packages.py
python scripts/build_step_packages.py --check
python scripts/update_checksums.py
```

If installed tag metrology changes, run `python scripts/generate_fiducials.py --map-only` before documentation sync and release validation.

## 7. Sign the step with the controlled helper

When all required test rows and reviewed gates pass, run:

```powershell
python scripts/sign_off_step.py --step 03 --status PASS --operator "NAME"
```

Add `--witness "NAME"` when required. The PASS helper derives accepted test IDs and refuses incomplete or invalid rows. To stop, use `python scripts/sign_off_step.py --step 03 --status HOLD --operator "NAME" --hold "reason"`; repeat `--hold` for multiple reasons. Raw `signoff.json` editing is an advanced recovery fallback only.

## 8. Regenerate, verify the handoff, then initialize the next step

Immediately after signoff, regenerate and check the package:

```powershell
python scripts/build_step_packages.py
python scripts/build_step_packages.py --check
```

Reopen `00 - START HERE.md` or inspect `INDEX.json`. Confirm that the step just signed is `COMPLETE` and its immediate next step is `READY TO START` for the same active build ID. Only after both results are visible may you run:

```powershell
python scripts/initialize_step_evidence.py --step NN
```

Do not initialize on `LOCKED`, `HOLD`, `IN PROGRESS`, `COMPLETE`, or stale package state. Step 15 has no next-step initialization; archive its signed release record after final validation.
