# Step 13 — Measurements Checklist

Use the copy inside your active build-ID folder as a work aid; never edit this generated template.

Record authoritative results with `scripts/record_step_result.py`; it safely updates `measurement_record.json`. Raw JSON editing is an advanced recovery fallback only.

Every `--evidence` path must be relative to the build-ID folder, remain contained within that folder, and point to an existing regular file. Neither `measurement_record.json` nor `signoff.json` is physical evidence. Repeat `--evidence` when one test has multiple files.

Command form:

`python scripts/record_step_result.py --step 13 --test TEST_ID --value "VALUE_OR_OBSERVATION" --unit "UNIT_OR_NA" --instrument "TOOL_ID_OR_METHOD" --evidence "photos/EXISTING_FILE.jpg" --result PASS --operator "OPERATOR_NAME"`

## 13-A — Received tripod, B0477, and retention stack are fully identified and measured

- Method: Validate the hash-bound intake and inspect source photos plus mount measurements
- Pass limit: Every received_hardware and measured_mount_interface field is populated; engagement is positive and non-bottoming; anti-rotation and independent tether are installed
- Required evidence: Intake record, label photos, mount measurements, fastener stack, anti-rotation, and tether photos
- Required record: value or observation
- Required record: unit and instrument ID
- Required record: original evidence file path
- Required record: PASS or FAIL result

## 13-B — Installed tripod pose and support stability

- Method: Measure pose, footprint, sag, settle, cable-pull displacement, remove/reinstall repeatability, 24-hour drift, and vibration
- Pass limit: All fields are populated and accepted against the reviewed vision and collision budgets; witness marks match
- Required evidence: Intake record, raw measurements, timed observations, before/after pose records, and witness photos
- Required record: value or observation
- Required record: unit and instrument ID
- Required record: original evidence file path
- Required record: PASS or FAIL result

## 13-C — B0477 calibration and complete overview visibility

- Method: Run the active B0477 commissioning and calibration workflow, then evaluate all required fiducials and model crop footprints
- Pass limit: Exact identity and mode are locked; calibration passes its controlled limits; all six fiducials and all complete model crop footprints remain visible
- Required evidence: Camera identity/mode record, calibration report and hash, overview frames, tag reports, crop coverage report, and annotated images
- Required record: value or observation
- Required record: unit and instrument ID
- Required record: original evidence file path
- Required record: PASS or FAIL result

## 13-D — Tripod collision envelope and fail-stop injections

- Method: Screen the installed support and cable against every approved swept volume and inject support shift, tilt, cable pull, tag loss, stale frame, and witness mismatch
- Pass limit: Collision screen passes and every consequential injected fault blocks descent
- Required evidence: Installed collision geometry, swept-volume reports, injection receipts, and no-descent results
- Required record: value or observation
- Required record: unit and instrument ID
- Required record: original evidence file path
- Required record: PASS or FAIL result

