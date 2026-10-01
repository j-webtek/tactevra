"""Explicit hardware-free CI stages; no discovery of live experiment scripts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PYTHON = (
    ROOT
    / ".venv-ci"
    / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
)
TESTS = (
    "hardware/static_overhead_camera/cad/test_stage_system_print_pack.py",
    "active-project/RoCell_v0_3/tests/test_stage_step_00_bundle.py",
    "software/tests/unit/test_snapshot_audit.py",
    "software/tests/unit/test_model_motion_ingress_v2.py",
    "software/tests/unit/test_model_motion_planner_gate.py",
    "software/tests/unit/test_typing_execution_plan_v1.py",
    "software/tests/unit/test_typing_trajectory_plan_v1.py",
    "software/tests/unit/test_measured_trajectory_screening.py",
    "software/tests/unit/test_measured_waypoint_collision_sequence.py",
    "software/tests/unit/test_fk_collision_pose_adapter.py",
    "software/tests/unit/test_phase_local_contact_envelope_gate.py",
    "software/tests/unit/test_single_action_execution_review_v1.py",
    "software/tests/unit/test_reviewed_motion_permit_bridge_v1.py",
    "software/tests/unit/test_reviewed_motion_sole_writer_v1.py",
    "software/tests/unit/test_reviewed_t102_runtime_bridge_v1.py",
    "software/tests/unit/test_native_t102_handoff_journal_v1.py",
    "software/tests/unit/test_native_t102_executor_rehearsal_v1.py",
    "software/tests/unit/test_native_t102_terminal_receipt_journal_v1.py",
    "software/tests/unit/test_native_t102_production_transport_v1.py",
    "software/tests/unit/test_t102_machine_ledger_v1.py",
    "software/tests/unit/test_windows_native_t102_serial_transport_v1.py",
    "software/tests/unit/test_native_t102_adapter_review_packet_v1.py",
    "software/tests/unit/test_native_t102_adapter_review_decision_v1.py",
    "software/tests/unit/test_arm054_adapter_review_exchange_cli.py",
    "software/tests/unit/test_native_t102_owner_ai_review_acceptance_v1.py",
    "software/tests/unit/test_native_t102_read_only_endpoint_intake_v1.py",
    "software/tests/unit/test_arm062_passive_read_only_qualification_script.py",
    "software/tests/unit/test_native_t105_active_feedback_intake_v1.py",
    "software/tests/unit/test_native_t105_active_feedback_rehearsal_v1.py",
    "software/tests/unit/test_arm064_active_feedback_qualification_script.py",
    "software/tests/unit/test_arm064_active_feedback_qualification_receipt.py",
    "software/tests/unit/test_r97_runtime_transition_assessment_v1.py",
    "software/tests/unit/test_r97_owner_ai_review_acceptance_v1.py",
    "software/tests/unit/test_owner_governed_configuration_epoch_v1.py",
    "software/tests/unit/test_software_build_epoch_evidence_v1.py",
    "software/tests/unit/test_camera_support_optics_epoch_intake_v1.py",
    "software/tests/unit/test_camera_support_binding_adapter_v1.py",
    "software/tests/unit/test_camera_arrival_evidence_preflight_v1.py",
    "software/tests/unit/test_camera_arrival_consumer_handoff_v1.py",
    "software/tests/unit/test_camera_arrival_consumer_validation_v1.py",
    "software/tests/unit/test_camera_arrival_consumer_emitters_v1.py",
    "software/tests/unit/test_camera_arrival_commissioning_orchestrator_v1.py",
    "software/tests/unit/test_camera_arrival_fault_campaign_v1.py",
    "software/tests/unit/test_camera_arrival_session_manifest_v1.py",
    "software/tests/unit/test_installed_geometry_cable_rehearsal_v1.py",
    "software/tests/unit/test_immutable_camera_replay_v1.py",
    "software/tests/unit/test_pre_camera_observability_v1.py",
    "software/tests/unit/test_operational_latency_trace_v1.py",
    "software/tests/unit/test_operational_latency_reference_v1.py",
    "software/tests/unit/test_context_validation_lease_v1.py",
    "software/tests/unit/test_context_lifecycle_v1.py",
    "software/tests/unit/test_context_validation_lease_benchmark_v1.py",
    "software/tests/unit/test_typing_planner_preparation_v1.py",
    "software/tests/unit/test_typing_planner_preparation_benchmark_v1.py",
    "software/tests/unit/test_typing_ik_effort_campaign_v1.py",
    "software/tests/unit/test_typing_exact_ik_cache_benchmark_v1.py",
    "software/tests/unit/test_typing_exact_ik_cache_owner_v1.py",
    "software/tests/unit/test_typing_exact_ik_cache_owner_campaign_v1.py",
    "software/tests/unit/test_typing_shadow_service_v1.py",
    "software/tests/unit/test_typing_shadow_service_campaign_v1.py",
    "software/tests/unit/test_typing_endpoint_atlas_observer_v1.py",
    "software/tests/unit/test_typing_endpoint_atlas_campaign_v1.py",
    "software/tests/unit/test_typing_endpoint_reuse_verifier_v1.py",
    "software/tests/unit/test_typing_endpoint_reuse_campaign_v1.py",
    "software/tests/unit/test_typing_exact_reuse_multisequence_campaign_v1.py",
    "software/tests/unit/test_typing_shadow_service_reuse_campaign_v1.py",
    "software/tests/unit/test_typing_ik_reuse_profile_gate_v1.py",
    "software/tests/unit/test_typing_ik_reuse_profile_campaign_v1.py",
    "software/tests/unit/test_typing_profiled_shadow_service_v1.py",
    "software/tests/unit/test_typing_profiled_shadow_service_campaign_v1.py",
    "software/tests/unit/test_actual_emitter_profiled_service_campaign_v1.py",
    "software/tests/unit/test_actual_emitter_mixed_queue_campaign_v1.py",
    "software/tests/unit/test_actual_emitter_stability_campaign_v1.py",
    "software/tests/unit/test_actual_emitter_disturbance_campaign_v1.py",
    "software/tests/unit/test_typing_runtime_supervisor_v1.py",
    "software/tests/unit/test_typing_runtime_supervisor_campaign_v1.py",
    "software/tests/unit/test_typing_supervised_command_gateway_v1.py",
    "software/tests/unit/test_typing_supervised_command_gateway_campaign_v1.py",
    "software/tests/unit/test_typing_command_session_ledger_v1.py",
    "software/tests/unit/test_typing_command_session_ledger_campaign_v1.py",
    "software/tests/unit/test_typing_execution_handoff_candidate_v1.py",
    "software/tests/unit/test_typing_execution_handoff_candidate_campaign_v1.py",
    "software/tests/unit/test_typing_shadow_artifact_store_v1.py",
    "software/tests/unit/test_typing_shadow_artifact_store_campaign_v1.py",
    "software/tests/unit/test_typing_execution_handoff_assembler_v1.py",
    "software/tests/unit/test_typing_execution_handoff_assembler_campaign_v1.py",
    "software/tests/unit/test_typing_shadow_materialization_v1.py",
    "software/tests/unit/test_typing_shadow_materialization_campaign_v1.py",
    "software/tests/unit/test_typing_permit_review_readiness_v1.py",
    "software/tests/unit/test_typing_state_prerequisite_binding_v1.py",
    "software/tests/unit/test_typing_observed_ik_seed_v1.py",
    "software/tests/unit/test_typing_observed_trajectory_ik_v1.py",
    "software/tests/unit/test_typing_observed_route_entry_v1.py",
    "software/tests/unit/test_typing_observed_route_entry_collision_v1.py",
    "software/tests/unit/test_typing_observed_route_entry_sweep_v1.py",
    "software/tests/unit/test_typing_observed_route_entry_dynamics_v1.py",
    "software/tests/unit/test_pre_camera_host_benchmark_v1.py",
    "software/tests/unit/test_assess_r97_external_review_decision.py",
    "software/tests/unit/test_model_motion_sequence_coordinator.py",
    "software/tests/unit/test_zero_write_waveshare_adapter_v1.py",
    "software/tests/unit/test_shadow_telemetry_replay_v1.py",
    "software/tests/unit/test_zero_write_sole_writer_v1.py",
    "software/tests/unit/test_installed_controller_qualification_v1.py",
    "software/tests/integration/test_zero_write_waveshare_contract_v1.py",
    "software/tests/integration/test_native_t102_windows_composition_v1.py",
    "software/tests/integration/test_model_motion_v2_shared_gate.py",
    "software/tests/integration/test_typing_shadow_pipeline_v1.py",
    "software/tests/integration/test_model_arm_conformance_profile_v1.py",
    "software/tests/integration/test_model_arm_operational_readiness_v1.py",
    "software/tests/integration/test_shared_shadow_runner_v2.py",
    "software/tests/integration/test_camera_arrival_evidence_preflight_cli_v1.py",
    "software/tests/integration/test_camera_arrival_consumer_handoff_cli_v1.py",
    "software/tests/integration/test_camera_arrival_commissioning_cli_v1.py",
    "software/tests/integration/test_camera_arrival_fault_campaign_cli_v1.py",
    "software/tests/integration/test_camera_arrival_consumer_operator_cli_v1.py",
    "software/tests/integration/test_camera_arrival_session_manifest_cli_v1.py",
    "software/tests/integration/test_installed_geometry_cable_rehearsal_cli_v1.py",
    "software/tests/integration/test_synthetic_epoch_model_arm_rehearsal_v1.py",
    "software/tests/integration/test_ai_emitted_epoch_model_arm_rehearsal_v1.py",
    "software/ai/tests/test_batch_emitter_v2.py",
    "software/ai/tests/test_capture_binding.py",
    "software/ai/tests/test_precision_binding_v2.py",
    "software/ai/tests/test_precision_adapter_v2.py",
    "software/ai/tests/test_precision_adapter_evaluation_bundle_v1.py",
    "software/ai/tests/test_actual_output_compatibility_v1.py",
    "software/ai/tests/test_profiled_service_ingress_v2.py",
    "software/ai/tests/test_confidence_metrics.py",
)


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PYTHON), *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
        timeout=600,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def smoke() -> None:
    # -I ignores PYTHONPATH and cwd: this must resolve the installed package.
    run(
        "-I",
        "-c",
        "import rocell; from importlib.metadata import version; print('Installed rocell', version('rocell'))",
    )
    results = {}
    for command in ("ground", "coordinate-preview"):
        results[command] = json.loads(
            run(
                "software/ai/run_offline.py",
                command,
                "--request",
                'Type "hi" on the keyboard',
                capture=True,
            ).stdout
        )
    ground = results["ground"]
    require(ground["inspection"]["status"] == "accepted", "Grounded request rejected")
    require(ground["proposal"]["text"] == "hi", "Literal text changed")
    require(
        [a["key"] for a in ground["inspection"]["action_plan"]["actions"]]
        == ["H", "I"],
        "Action order changed",
    )
    preview = results["coordinate-preview"]
    require(
        preview["execution_authorized"] is False, "Preview claims execution authority"
    )
    require(
        preview["controller_commands"] == [], "Preview contains controller commands"
    )
    require(
        preview["coordinate_source"] == "SIMULATION_ONLY_NOMINAL_UNMEASURED",
        "Preview no longer declares nominal geometry",
    )
    require(
        [t["target_id"] for t in preview["targets"]] == ["H", "I"],
        "Preview order changed",
    )
    print(
        "PASS: installed package, H/I ordering, nominal preview, no execution authority"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=("install-base", "install-tests", "smoke", "test", "environment"),
    )
    stage = parser.parse_args().stage
    require(PYTHON.is_file(), "Create .venv-ci with python -m venv .venv-ci first")
    if stage == "install-base":
        run("-m", "pip", "install", "./software")
        run("-m", "pip", "check")
    elif stage == "install-tests":
        run("-m", "pip", "install", "./software[test]")
        run("-m", "pip", "check")
    elif stage == "smoke":
        smoke()
    elif stage == "environment":
        run("scripts/ci/environment_report.py")
    else:
        run("-m", "pytest", "-q", *TESTS)


if __name__ == "__main__":
    main()
