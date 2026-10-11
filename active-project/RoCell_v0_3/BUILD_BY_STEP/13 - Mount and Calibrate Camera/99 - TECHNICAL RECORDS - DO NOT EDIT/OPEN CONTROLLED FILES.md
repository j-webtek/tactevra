# Controlled files for this step

These are direct links to the single canonical files. They are intentionally not copied here.

| Action | Job | File | Role | SHA-256 |
| --- | --- | --- | --- | --- |
| reference_only | — | [ASSEMBLY_MANUAL.md](<../../../ASSEMBLY_MANUAL.md>) | controlled detailed-manual source | `5c77cf9c49e7…` |
| read | — | [ASSEMBLY_MANUAL.pdf](<../../../ASSEMBLY_MANUAL.pdf>) | controlled detailed manual | `3f82933f75bb…` |
| reference_only | — | [BOM.csv](<../../../BOM.csv>) | purchasing source | `c9362cf401ca…` |
| reference_only | — | [BUILD_TRACKER.json](<../../../BUILD_TRACKER.json>) | machine-readable lifecycle tracker | `0309256af313…` |
| verify | — | [BUILD_TRACKER.md](<../../../BUILD_TRACKER.md>) | lifecycle tracker | `17ecf32b45b5…` |
| edit_only_in_step_01_after_cutoff_tests | — | [FASTENER_MAP.csv](<../../../FASTENER_MAP.csv>) | board fastener source | `94b0af10da8e…` |
| reference_only | — | [JOB_KITS.csv](<../../../JOB_KITS.csv>) | kitting source | `2c93199c0703…` |
| reference_only | — | [PRINT_READINESS.json](<../../../PRINT_READINESS.json>) | machine-readable print readiness | `a8c75f05f727…` |
| verify | — | [PRINT_READINESS.md](<../../../PRINT_READINESS.md>) | current print readiness | `5be5234644cb…` |
| read | — | [README_FIRST.md](<../../../README_FIRST.md>) | release entry point | `6e3e5a4bf57b…` |
| read | — | [TRIPOD_CAMERA_INSTALLATION.md](<../../../TRIPOD_CAMERA_INSTALLATION.md>) | active tripod installation and qualification procedure, tripod installation and qualification procedure | `4fbfbc71cfa1…` |
| reference_only | 00E | [cad/step/hardware_fit_gauge.step](<../../../cad/step/hardware_fit_gauge.step>) | neutral CAD companion | `5c703f405245…` |
| reference_only | 00E | [cad/step/setup_hardware_fit_gauge.step](<../../../cad/step/setup_hardware_fit_gauge.step>) | neutral CAD companion | `717132c8838c…` |
| reference_only | 00E | [cad/step/tpu_tip_retention_gauge.step](<../../../cad/step/tpu_tip_retention_gauge.step>) | neutral CAD companion | `adb1b65263e6…` |
| reference_only | — | [config/assembly_steps.json](<../../../config/assembly_steps.json>) | canonical step-to-file relationship map | `115805cdd45e…` |
| verify_not_physical_release | — | [config/camera_architecture_decision.json](<../../../config/camera_architecture_decision.json>) | selected static-overhead tripod architecture | `a1f8a7b8f2f8…` |
| edit_only_with_controlled_workflow | — | [config/job_build_record.json](<../../../config/job_build_record.json>) | canonical job lifecycle record | `8ffbb767c577…` |
| edit_only_with_recording_script | — | [config/measurement_record.json](<../../../config/measurement_record.json>) | canonical measurement and gate record | `1fb400eae310…` |
| reference_only | — | [config/parameters.json](<../../../config/parameters.json>) | canonical CAD parameter set | `769808d90946…` |
| reference_only | — | [config/print_jobs.json](<../../../config/print_jobs.json>) | canonical print-job definitions | `ba82c6e18761…` |
| reference_only | — | [config/print_profiles.json](<../../../config/print_profiles.json>) | canonical print-profile definitions | `5886a55b3fbd…` |
| complete | — | [config/tripod_camera_installation_intake_v1.json](<../../../config/tripod_camera_installation_intake_v1.json>) | active hash-bound tripod installation intake, hash-bound tripod receipt, measurement, pose, stability, and qualification intake | `52ca6f331d2f…` |
| reference_only | — | [config/workcell_layout.json](<../../../config/workcell_layout.json>) | generated geometry/layout source | `e84db9aa7b88…` |
| use_with_helper | — | [fiducials/apriltag_map.json](<../../../fiducials/apriltag_map.json>) | runtime tag map | `81c867d28660…` |
| reference_only | — | [fiducials/charuco_5x7_square25_marker17_5.png](<../../../fiducials/charuco_5x7_square25_marker17_5.png>) | historical RC03 calibration artwork retained for traceability | `9ad313fe625f…` |
| reference_only | — | [fiducials/charuco_5x7_square25_marker17_5_1to1.pdf](<../../../fiducials/charuco_5x7_square25_marker17_5_1to1.pdf>) | historical RC03 calibration target retained for traceability; not the repository-authoritative B0477 production target | `dd2192e679f7…` |
| reference_only | — | [fiducials/charuco_board_definition.json](<../../../fiducials/charuco_board_definition.json>) | historical RC03 calibration definition retained for traceability | `ed7aa4bd9d82…` |
| consume_accepted_output | 00E | [job_cards/JOB-00E.md](<../../../job_cards/JOB-00E.md>) | controlled print traveler | `5e54fc90484f…` |
| view | — | [output/assembly_guide/images/13_mount_camera_and_check_fov.png](<../../../output/assembly_guide/images/13_mount_camera_and_check_fov.png>) | assembly-step illustration | `48df5f4db536…` |
| read | — | [output/pdf/RC03_ILLUSTRATED_ASSEMBLY_GUIDE.pdf](<../../../output/pdf/RC03_ILLUSTRATED_ASSEMBLY_GUIDE.pdf>) | complete illustrated guide | `1084103edb5f…` |
| consume_accepted_output | 00E | [print_plates_3mf/00E_ABS_general_setup_tests.3mf](<../../../print_plates_3mf/00E_ABS_general_setup_tests.3mf>) | geometry-only QIDI plate | `67073d37df50…` |
| consume_accepted_output | 00E | [print_plates_3mf/00E_ABS_general_setup_tests.PRINT_SETTINGS.md](<../../../print_plates_3mf/00E_ABS_general_setup_tests.PRINT_SETTINGS.md>) | exact operator print-settings sheet | `0a1da7fcba38…` |
| consume_accepted_output | 00E | [print_plates_3mf/00E_ABS_general_setup_tests.print.json](<../../../print_plates_3mf/00E_ABS_general_setup_tests.print.json>) | controlled plate/profile/hash sidecar | `cd64ea520ff1…` |
| reference_only | — | [scripts/build_illustrated_assembly_guide.py](<../../../scripts/build_illustrated_assembly_guide.py>) | illustrated-guide PDF generator | `6badf0daa975…` |
| reference_only | — | [scripts/build_manual_pdf.py](<../../../scripts/build_manual_pdf.py>) | controlled detailed-manual PDF renderer | `4baf08d28e35…` |
| run_from_project_root | — | [scripts/build_step_packages.py](<../../../scripts/build_step_packages.py>) | step-package generator and validator | `1b3328e85ad2…` |
| run_from_project_root | — | [scripts/generate_build_tracker.py](<../../../scripts/generate_build_tracker.py>) | job-lifecycle validator and tracker generator | `6090b47ff751…` |
| reference_only | — | [scripts/generate_job_cards.py](<../../../scripts/generate_job_cards.py>) | controlled print-traveler instruction generator | `520cf48d2263…` |
| run_before_each_step | — | [scripts/initialize_step_evidence.py](<../../../scripts/initialize_step_evidence.py>) | non-overwriting active-build evidence initializer | `0a940eabc2ab…` |
| run_after_each_completed_state | — | [scripts/record_job_lifecycle.py](<../../../scripts/record_job_lifecycle.py>) | sequential print-job lifecycle recorder | `440ca2e1b518…` |
| run_after_reviewing_raw_evidence | — | [scripts/record_print_measurement.py](<../../../scripts/record_print_measurement.py>) | canonical gate and route recorder | `5cac4945ed54…` |
| run_for_each_step_test | — | [scripts/record_step_result.py](<../../../scripts/record_step_result.py>) | non-destructive step-result recorder | `851e5b3761c2…` |
| reference_only | — | [scripts/render_assembly_guide.py](<../../../scripts/render_assembly_guide.py>) | assembly-panel source renderer | `8e7467e8eccc…` |
| run_before_recording_evidence | — | [scripts/set_active_build.py](<../../../scripts/set_active_build.py>) | active physical-build selector | `0f593f140437…` |
| run_after_step_tests | — | [scripts/sign_off_step.py](<../../../scripts/sign_off_step.py>) | validated step signoff recorder | `caed2f3b929d…` |
| run_for_standalone_export | — | [scripts/stage_hash_bound_artifacts.py](<../../../scripts/stage_hash_bound_artifacts.py>) | hash-bound canonical artifact staging and offline verification | `a18eb88d17b2…` |
| reference_only | — | [scripts/step_evidence_common.py](<../../../scripts/step_evidence_common.py>) | shared step-evidence containment and schema controls | `93fb598ee2de…` |
| run_from_project_root | — | [scripts/validate_print_readiness.py](<../../../scripts/validate_print_readiness.py>) | typed gate and print-readiness validator | `7dc6159c1582…` |
| run_from_project_root | — | [scripts/validate_release_package.py](<../../../scripts/validate_release_package.py>) | whole-package release validator | `0fc8994764e3…` |
| run_from_project_root | — | [scripts/validate_tripod_camera_intake.py](<../../../scripts/validate_tripod_camera_intake.py>) | tripod intake hash and zero-authority validator | `c301c91f876a…` |
| read | — | [slicer_profiles/QIDI_PLUS4/README.md](<../../../slicer_profiles/QIDI_PLUS4/README.md>) | QIDI process-preset import guide | `641631027fd7…` |
| consume_accepted_output | 00E | [slicer_profiles/QIDI_PLUS4/abs_rapido_general_0p4.process.json](<../../../slicer_profiles/QIDI_PLUS4/abs_rapido_general_0p4.process.json>) | importable QIDI Studio process preset | `756895e547ed…` |
| reference_only | — | [stl/camera_plate_universal.stl](<../../../stl/camera_plate_universal.stl>) | SUPERSEDED_DO_NOT_PRINT legacy mast camera plate | `7fb63205ddc3…` |
| reference_only | 00E | [stl/hardware_fit_gauge.stl](<../../../stl/hardware_fit_gauge.stl>) | canonical slicing mesh | `4a9a35b618a4…` |
| reference_only | — | [stl/mast_foot_2020.stl](<../../../stl/mast_foot_2020.stl>) | SUPERSEDED_DO_NOT_PRINT legacy mast foot | `2b6384b63a5b…` |
| reference_only | — | [stl/mast_socket_fit_test.stl](<../../../stl/mast_socket_fit_test.stl>) | SUPERSEDED_DO_NOT_PRINT legacy mast coupon | `3a8e939ae308…` |
| reference_only | 00E | [stl/setup_hardware_fit_gauge.stl](<../../../stl/setup_hardware_fit_gauge.stl>) | canonical slicing mesh | `e6394a26fe10…` |
| reference_only | 00E | [stl/tpu_tip_retention_gauge.stl](<../../../stl/tpu_tip_retention_gauge.stl>) | canonical slicing mesh | `0476c9c867a9…` |

## Control rules

- A `.3mf` is a geometry-only plate. Use its paired `.PRINT_SETTINGS.md`, `.print.json`, imported QIDI process preset, separate filament preset, and job card; then save a native QIDI Studio project in the build-ID evidence folder.
- STL is the canonical slicing mesh; STEP is its neutral CAD companion. Neither is edited inside this package.
- Files marked `DO_NOT_PRINT` or `reference_only` are never manufacturing masters.
- If any hash differs from `FILE INDEX.csv`, stop and regenerate this package before continuing.
