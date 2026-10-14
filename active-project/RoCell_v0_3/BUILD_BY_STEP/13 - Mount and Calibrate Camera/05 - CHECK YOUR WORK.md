# Step 13 — Check Your Work

Save original files under `06 - SAVE MEASUREMENTS AND PHOTOS/<BUILD_ID>/`, then record every test with `python scripts/record_step_result.py --step 13 ...`. Each `--evidence` path must be relative to that build-ID folder, remain contained within it, and name an existing regular file; `measurement_record.json` and `signoff.json` cannot cite themselves. A visual check alone is not evidence when a measured value is required.

Command form: `python scripts/record_step_result.py --step 13 --test TEST_ID --value "VALUE_OR_OBSERVATION" --unit "UNIT_OR_NA" --instrument "TOOL_ID_OR_METHOD" --evidence "photos/EXISTING_FILE.jpg" --result PASS --operator "OPERATOR_NAME"`. Repeat `--evidence` as needed. Raw JSON editing is an advanced recovery fallback only.

| Test | What must be true | How to check | Pass limit | Reviewed gate | Evidence to save | Record result in |
| --- | --- | --- | --- | --- | --- | --- |
| `13-A` | Received tripod, B0477, and retention stack are fully identified and measured | Validate the hash-bound intake and inspect source photos plus mount measurements | Every received_hardware and measured_mount_interface field is populated; engagement is positive and non-bottoming; anti-rotation and independent tether are installed | `camera_mount_interface_measured` | Intake record, label photos, mount measurements, fastener stack, anti-rotation, and tether photos | `scripts/record_step_result.py` |
| `13-B` | Installed tripod pose and support stability | Measure pose, footprint, sag, settle, cable-pull displacement, remove/reinstall repeatability, 24-hour drift, and vibration | All fields are populated and accepted against the reviewed vision and collision budgets; witness marks match | `tag_direct_installation_pass` | Intake record, raw measurements, timed observations, before/after pose records, and witness photos | `scripts/record_step_result.py` |
| `13-C` | B0477 calibration and complete overview visibility | Run the active B0477 commissioning and calibration workflow, then evaluate all required fiducials and model crop footprints | Exact identity and mode are locked; calibration passes its controlled limits; all six fiducials and all complete model crop footprints remain visible | `tag_direct_installation_pass` | Camera identity/mode record, calibration report and hash, overview frames, tag reports, crop coverage report, and annotated images | `scripts/record_step_result.py` |
| `13-D` | Tripod collision envelope and fail-stop injections | Screen the installed support and cable against every approved swept volume and inject support shift, tilt, cable pull, tag loss, stale frame, and witness mismatch | Collision screen passes and every consequential injected fault blocks descent | `tag_direct_installation_pass` | Installed collision geometry, swept-volume reports, injection receipts, and no-descent results | `scripts/record_step_result.py` |

## Completion status

| Requirement | Current result |
| --- | --- |
| `tag_direct_installation_pass` | **NOT_TESTED** |
| active-build step signoff | **NOT_STARTED** |

## If a check fails

If source hashes or received identities differ, stop and revise the intake under change control. If pose, stability, visibility, collision, or an injection fails, keep motion and contact blocked, correct the installation, create a new evidence attempt, and repeat every affected check.

The step is PASS only when every test is in limit, all required reviewed gates are PASS, and `signoff.json` is signed PASS.
