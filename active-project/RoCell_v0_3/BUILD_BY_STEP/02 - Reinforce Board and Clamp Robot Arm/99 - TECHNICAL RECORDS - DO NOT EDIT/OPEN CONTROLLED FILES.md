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
| read | — | [RC03_INTEGRATED_BUILD_PLAN.md](<../../../RC03_INTEGRATED_BUILD_PLAN.md>) | engineering rationale | `c8cf80651860…` |
| read | — | [README_FIRST.md](<../../../README_FIRST.md>) | release entry point | `6e3e5a4bf57b…` |
| read | — | [TRIPOD_CAMERA_INSTALLATION.md](<../../../TRIPOD_CAMERA_INSTALLATION.md>) | tripod installation and qualification procedure | `4fbfbc71cfa1…` |
| reference_only | — | [cad/step/RoCell_RC03_INT_R1_full_assembly.step](<../../../cad/step/RoCell_RC03_INT_R1_full_assembly.step>) | assembly visualization | `940c6ac34802…` |
| reference_only | — | [config/assembly_steps.json](<../../../config/assembly_steps.json>) | canonical step-to-file relationship map | `115805cdd45e…` |
| edit_only_with_controlled_workflow | — | [config/job_build_record.json](<../../../config/job_build_record.json>) | canonical job lifecycle record | `8ffbb767c577…` |
| edit_only_with_recording_script | — | [config/measurement_record.json](<../../../config/measurement_record.json>) | canonical measurement and gate record | `1fb400eae310…` |
| reference_only | — | [config/parameters.json](<../../../config/parameters.json>) | canonical CAD parameter set | `769808d90946…` |
| reference_only | — | [config/print_jobs.json](<../../../config/print_jobs.json>) | canonical print-job definitions | `ba82c6e18761…` |
| reference_only | — | [config/print_profiles.json](<../../../config/print_profiles.json>) | canonical print-profile definitions | `5886a55b3fbd…` |
| complete | — | [config/tripod_camera_installation_intake_v1.json](<../../../config/tripod_camera_installation_intake_v1.json>) | hash-bound tripod receipt, measurement, pose, stability, and qualification intake | `52ca6f331d2f…` |
| reference_only | — | [config/workcell_layout.json](<../../../config/workcell_layout.json>) | generated geometry/layout source | `e84db9aa7b88…` |
| inspect | — | [images/assembly_isometric.png](<../../../images/assembly_isometric.png>) | visual reference | `41af485ccf75…` |
| view | — | [output/assembly_guide/images/02_reinforce_and_clamp_arm.png](<../../../output/assembly_guide/images/02_reinforce_and_clamp_arm.png>) | assembly-step illustration | `8d9b3fed7f93…` |
| read | — | [output/pdf/RC03_ILLUSTRATED_ASSEMBLY_GUIDE.pdf](<../../../output/pdf/RC03_ILLUSTRATED_ASSEMBLY_GUIDE.pdf>) | complete illustrated guide | `1084103edb5f…` |
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

## Control rules

- A `.3mf` is a geometry-only plate. Use its paired `.PRINT_SETTINGS.md`, `.print.json`, imported QIDI process preset, separate filament preset, and job card; then save a native QIDI Studio project in the build-ID evidence folder.
- STL is the canonical slicing mesh; STEP is its neutral CAD companion. Neither is edited inside this package.
- Files marked `DO_NOT_PRINT` or `reference_only` are never manufacturing masters.
- If any hash differs from `FILE INDEX.csv`, stop and regenerate this package before continuing.
