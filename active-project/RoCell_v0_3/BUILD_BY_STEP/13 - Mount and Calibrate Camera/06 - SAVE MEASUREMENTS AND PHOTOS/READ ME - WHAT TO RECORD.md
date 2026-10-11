# Save measurements and photos here

This is the only operator-writable area in this generated step package. Step-local records are the raw source record; they do **not** automatically update the reviewed project gates or print-job lifecycle.

1. At Step 00, choose one unique build ID such as `2026-08-31_CELL-A`; use exactly that folder name throughout the build.
2. Do not initialize this folder while the step is locked. When `00 - START HERE.md` reports `READY TO START`, follow the root `02 - HOW TO SAVE MEASUREMENTS AND PHOTOS.md` workflow exactly; the controlled initializer refuses to overwrite evidence.
3. Save each original photo, native QIDI project, calibration output, or report inside the copied build-ID folder before recording it. Every `--evidence` value must be relative to that build-ID folder, remain contained within it, and name a file that already exists. Neither `measurement_record.json` nor `signoff.json` may cite itself as physical evidence.
4. From the project root, record each pre-populated test with the controlled helper. Example: `python scripts/record_step_result.py --step 13 --test 13-A --value "REPLACE_WITH_VALUE_OR_OBSERVATION" --unit "REPLACE_WITH_UNIT_OR_NA" --instrument "REPLACE_WITH_TOOL_ID_OR_METHOD" --evidence "photos/13-A.jpg" --result PASS --operator "REPLACE_WITH_NAME"`. Repeat `--evidence` for additional files; use `--notes` for useful context.
5. Use `Measurements Checklist.md` to confirm that every required test ID was recorded. Then copy supported reviewed gate results into `config/measurement_record.json` with `scripts/record_print_measurement.py`; cite this build-ID evidence path. Do not mark a canonical gate PASS while any required value is blank.
6. For Step 00 print jobs, advance `config/job_build_record.json` only in lifecycle order and only after the matching state evidence exists; then regenerate the tracker and job cards.
7. Follow `Finish and Sign Off.md`. For PASS, run `python scripts/sign_off_step.py --step 13 --status PASS --operator "REPLACE_WITH_NAME"`; add `--witness "REPLACE_WITH_NAME"` when required. The helper derives accepted test IDs and refuses incomplete or invalid rows.
8. To stop with a documented hold, run `python scripts/sign_off_step.py --step 13 --status HOLD --operator "REPLACE_WITH_NAME" --hold "REPLACE_WITH_REASON"`; repeat `--hold` for separate reasons.
9. Raw edits to `measurement_record.json` or `signoff.json` are an advanced recovery fallback only. Normal recording and signoff use the helpers above so containment, schema, and completeness checks cannot be skipped.
10. Regeneration preserves actual build-ID folders but refreshes `BUILD_ID_TEMPLATE/` to the current package-definition and canonical-snapshot hashes.

See the root `02 - HOW TO SAVE MEASUREMENTS AND PHOTOS.md` for the exact synchronization sequence.
