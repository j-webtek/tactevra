# Step 13 — Finish This Step and Continue

Do not continue unless every mandatory acceptance item is PASS and there is no unresolved HOLD.

## Required handoff results

- Required result: The hash-bound intake records received identities, mount stack, support geometry, installed pose, stability, qualification results, and retained evidence.
- Required result: B0477 identity, runtime mode, controls, orientation, calibration, and hashes are locked.
- Required result: All six fiducials and every complete model crop footprint are visible at the qualified pose.
- Required result: Installed tripod and cable collision geometry pass every approved swept-volume screen, and all wrong-model injections block descent.
- Required result: Authority remains explicitly false pending the separate robot-power, motion, and contact approval process.
- Required result: Installed items, returned tools, accepted spares, quarantined parts, and affected downstream datums are recorded in the build-ID folder.
- Required result: The responsible operator ran `python scripts/sign_off_step.py --step 13 --status PASS --operator "OPERATOR_NAME"`; the helper validated and completed `signoff.json`.

Raw signoff JSON editing is an advanced recovery fallback only. Use `--status HOLD --hold "REASON"` instead of forcing PASS when any requirement is incomplete.

After PASS, follow [02 - HOW TO SAVE MEASUREMENTS AND PHOTOS.md](<../02 - HOW TO SAVE MEASUREMENTS AND PHOTOS.md>) section 8: regenerate, run `python scripts/build_step_packages.py --check`, reopen the refreshed state, and confirm this step is `COMPLETE` before any handoff.

## Next step remains locked

Step 14 cannot be opened from this handoff until Step 13 is computed `COMPLETE`.
