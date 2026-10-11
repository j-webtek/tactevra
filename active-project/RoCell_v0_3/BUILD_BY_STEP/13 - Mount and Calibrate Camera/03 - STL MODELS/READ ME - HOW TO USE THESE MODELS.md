# STL files for this step

Step 00 uses a governed mix of small generated convenience copies and hash-bound links to the authoritative project-level `stl/` files. Steps 01–15 use only hash-bound links and intentionally contain no duplicate STL bytes.

## Rules

- Print only when the step and job card explicitly say to print. Assembly Steps 01-15 normally consume parts already accepted in Step 00.
- Never globally scale or auto-repair a production STL without reopening the measurement, regeneration, and validation workflow.
- A file marked `DO_NOT_PRINT` is a visualization/reference body only.
- Compare against `STL MODEL LIST.csv`; any hash mismatch is a STOP.
- Return to Step 00 and its qualified ready-job workflow if an accepted part is missing.

| STL | Usage | Job reference | SHA-256 |
| --- | --- | --- | --- |
| [camera_plate_universal.stl](<../../../stl/camera_plate_universal.stl>) | **TRACEABILITY_ONLY_DO_NOT_PRINT** | reference only | `7fb63205ddc37b517ee452eda352893c7912cebe74086d977ef0beb8ec2d006f` |
| [hardware_fit_gauge.stl](<../../../stl/hardware_fit_gauge.stl>) | **TRACEABILITY_ONLY_DO_NOT_PRINT** | 00E | `4a9a35b618a420931b7e8b6b717aee4a3eb68f8948fff04e5a69fd65266e9e42` |
| [mast_foot_2020.stl](<../../../stl/mast_foot_2020.stl>) | **TRACEABILITY_ONLY_DO_NOT_PRINT** | reference only | `2b6384b63a5b191ef88ae5590b50ffb5cd0c64d2102b3145b8336b2fb901faa5` |
| [mast_socket_fit_test.stl](<../../../stl/mast_socket_fit_test.stl>) | **TRACEABILITY_ONLY_DO_NOT_PRINT** | reference only | `3a8e939ae308baa04fda3891dfc8851a0a3b2caa9e2a91148414255e1114905b` |
| [setup_hardware_fit_gauge.stl](<../../../stl/setup_hardware_fit_gauge.stl>) | **TRACEABILITY_ONLY_DO_NOT_PRINT** | 00E | `e6394a26fe104fb2af1b05df14865a5be2908bf6e99fab79c93aa034a2dc57b4` |
| [tpu_tip_retention_gauge.stl](<../../../stl/tpu_tip_retention_gauge.stl>) | **TRACEABILITY_ONLY_DO_NOT_PRINT** | 00E | `0476c9c867a9f28816c5df107f8bcff9e44b7e1ba79e8927501a8d1c6d32b777` |
