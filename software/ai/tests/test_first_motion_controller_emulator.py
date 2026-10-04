from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from rocell.arm.all_joint_command import all_joint_command
from rocell.application.production_controller_runtime_contract_v1 import (
    ProductionControllerRuntimeContractError,
    ProductionControllerRuntimeContractV1,
)
from rocell_ai.first_motion_controller_emulator import (
    InMemoryT102Controller,
    ServoRangeSample,
    _runtime_frame,
    _runtime_manifest,
    load_emulator_fixture,
    load_first_motion_fixture,
    run_controller_emulator,
    run_staged_bringup_rehearsal,
)
from rocell_ai.first_motion_drills import (
    load_collision_attribution_fixture,
    load_independent_observation_fixture,
    run_candidate_collision_attribution,
    run_exploratory_candidate_staged_rehearsal,
    run_independent_observation_drills,
    run_scenario_regression,
    run_wrong_model_drills,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_controller_emulator_v1.json"
SOURCE = ROOT / "software/ai/rocell_ai/first_motion_controller_emulator.py"
READINESS_FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_readiness_v1.json"
OBSERVATION_FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_independent_observation_v1.json"
COLLISION_ATTRIBUTION_FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_candidate_collision_attribution_v1.json"


def _sample() -> ServoRangeSample:
    return ServoRangeSample("test", 5, 25, 100, 1, 0.004, 0.001, 20, 1)


def test_fixture_is_hash_bound_and_zero_authority() -> None:
    fixture = load_emulator_fixture(FIXTURE)
    assert fixture["scope"] == "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
    assert not any(fixture["counters"].values())
    assert fixture["controller_emulator"]["protocol"]["command_family"] == "T102_ALL_JOINT_ABSOLUTE"
    assert "Production T102 runtime" in fixture["controller_emulator"]["protocol"]["production_transport_gap"]
    assert fixture["amendments"][0]["timing"] == "PRE_CORRECTED_RESULT"


def test_full_roundtrip_covers_ids_directions_ranges_and_faults() -> None:
    result = run_controller_emulator(load_emulator_fixture(FIXTURE))
    assert result["decision"] == "PASS_STRICT_RUNTIME_CONTRACT_SIMULATED_PLANT_ONLY"
    assert result["sample_count"] == 14
    assert result["roundtrip_case_count"] == 182
    assert result["all_direction_correct"] is True
    assert result["all_logical_joint_ids"] == [1, 2, 3, 4, 5, 6]
    assert result["all_servo_ids"] == [11, 12, 13, 14, 15, 16, 17]
    assert result["non_echo_case_count"] == result["roundtrip_case_count"]
    assert result["fault_detection_rate"] == 1.0
    assert result["strict_runtime_path_case_count"] == 182
    assert result["strict_runtime_fault_case_count"] == 6
    assert result["all_runtime_cases_terminal_no_retry"] is True
    assert all(row["runtime_feedback_exchange_count"] == 33 for row in result["cases"])
    assert all(row["runtime_hardware_write_count"] == 0 for row in result["cases"])
    assert result["transport_isolation"] == {
        "real_transport_open_count": 0,
        "live_transport_import_present": False,
        "constructor_accepts_transport": False,
    }
    assert result["hardware_write_count"] == result["physical_movement_count"] == 0
    assert result["real_command_count"] == result["transport_count"] == 0


def test_emulator_requires_exact_existing_t102_encoder_output() -> None:
    controller = InMemoryT102Controller((0, 0, 1.4, 0, 0, 2.4), _sample(), seed=1)
    command = all_joint_command((0.02, 0, 1.4, 0, 0, 2.4), speed=20, acceleration=1)
    result = controller.execute(command)
    assert result["status"] == "COMPLETED_MEASURED"
    assert result["telemetry_is_command_echo"] is False
    assert controller.transport_open_count == 0

    tampered = dict(command)
    tampered["servo_id"] = 11
    with pytest.raises(ValueError, match="keys are not exact"):
        controller.execute(tampered)


@pytest.mark.parametrize("fault", (
    "DROPPED_MESSAGE", "DELAYED_TELEMETRY", "SERVO_NOT_RESPONDING",
    "STALL_OVERLOAD", "ESTOP", "POWER_INTERRUPTION",
))
def test_every_frozen_fault_fails_closed(fault: str) -> None:
    controller = InMemoryT102Controller((0, 0, 1.4, 0, 0, 2.4), _sample(), seed=2)
    command = all_joint_command((0.01, 0.01, 1.41, 0.01, 0.01, 2.41), speed=20, acceleration=1)
    result = controller.execute(command, fault=fault)
    assert result["status"] == f"FAULT_{fault}"
    assert result["hardware_write_count"] == result["physical_movement_count"] == 0
    assert result["real_transport_open_count"] == 0


def test_module_has_no_live_transport_import_or_open_surface() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name == "serial" or name == "socket" or "serial_transport" in name for name in imported)
    assert "transport" not in inspect.signature(InMemoryT102Controller).parameters
    assert not hasattr(InMemoryT102Controller, "connect")
    assert not hasattr(InMemoryT102Controller, "open")


def test_strict_runtime_rejects_wire_mutation_before_plant() -> None:
    fixture = load_emulator_fixture(FIXTURE)
    command = all_joint_command((0.02, 0, 1.4, 0, 0, 2.4), speed=20, acceleration=1)
    frame = _runtime_frame(fixture, command, case_id="mutation-test")
    mutated = type(frame)(
        sequence=frame.sequence,
        correlation_id=frame.correlation_id,
        writer_instance_id=frame.writer_instance_id,
        controller_session_id=frame.controller_session_id,
        configuration_epoch_sha256=frame.configuration_epoch_sha256,
        encoding_profile_sha256=frame.encoding_profile_sha256,
        issued_monotonic_ns=frame.issued_monotonic_ns,
        expires_monotonic_ns=frame.expires_monotonic_ns,
        wire_bytes=frame.wire_bytes.replace(b'"T":102', b'"T":105'),
    )
    runtime = ProductionControllerRuntimeContractV1(_runtime_manifest(fixture))
    runtime.claim_writer("simulation-writer")
    with pytest.raises(ProductionControllerRuntimeContractError):
        runtime.admit_t102(mutated, now_monotonic_ns=150)
    assert runtime.report()["status"] == "TERMINAL_NO_RETRY"
    assert runtime.report()["hardware_write_count"] == 0


def test_stage_rehearsal_prepares_envelope_then_stops_at_collision_no_go() -> None:
    readiness = load_first_motion_fixture(READINESS_FIXTURE)
    report = run_staged_bringup_rehearsal(
        readiness, load_emulator_fixture(FIXTURE))
    assert report["decision"] == "STOP_AT_STAGE_A_COLLISION_DIAGNOSTIC_NOT_CLEAR"
    assert report["first_no_go_stage"] == "A"
    assert report["predictive_runtime_rehearsals"] == 28
    assert report["staged_motion_executions"] == 0
    assert report["envelopes"][0]["prediction_count"] == 28
    assert len(report["envelopes"][0]["samples"]) == 33
    assert report["stage_results"][0]["status"] == "NO_GO"
    assert [row["status"] for row in report["stage_results"][1:]] == [
        "NOT_RUN_UPSTREAM_BLOCKED"] * 5
    assert report["hardware_write_count"] == report["physical_movement_count"] == 0
    assert report["real_command_count"] == report["permit_count"] == 0
    assert report["transport_count"] == 0


def test_first_motion_fixture_rejects_changed_external_collision_receipt(
        tmp_path: Path) -> None:
    fixture = json.loads(READINESS_FIXTURE.read_text(encoding="utf-8"))
    fixture["bindings"]["phase0_collision_receipt"]["sha256"] = "0" * 64
    claimed = fixture.pop("fixture_sha256")
    fixture["fixture_sha256"] = claimed
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError):
        load_first_motion_fixture(path)


def test_wrong_model_drills_retain_external_geometry_gaps() -> None:
    report = run_wrong_model_drills(load_first_motion_fixture(READINESS_FIXTURE))
    assert report["case_count"] == 63
    assert report["detected_count"] == report["precontact_detected_count"] == 30
    assert report["gap_count"] == 33
    assert report["collision_no_go_detection_credits"] == 0
    assert {row["injection"].get("type") for row in report["gaps"] if "type" in row["injection"]} == {
        "LINK_LENGTH", "JOINT_ZERO"}
    assert report["decision"] == "GAPS_RETAINED_NO_THRESHOLD_CHANGE"
    assert report["hardware_write_count"] == report["physical_movement_count"] == 0
    assert report["real_command_count"] == report["permit_count"] == 0
    assert report["transport_count"] == 0


def test_scenario_regression_exposes_wrong_model_false_acceptances() -> None:
    fixture = load_first_motion_fixture(READINESS_FIXTURE)
    report = run_scenario_regression(
        fixture, run_wrong_model_drills(fixture), workspace=ROOT)
    assert report["catalog"]["entries"]
    assert report["nightly"]["count"] == 84
    assert report["nightly"]["pass_count"] == 51
    assert report["nightly"]["false_acceptance_count"] == 33
    assert report["nightly"]["categories"]["WRONG_MODEL"] == {
        "count": 63, "pass_count": 30, "pass_rate": 30 / 63,
        "false_acceptance_count": 33,
    }
    assert report["ci"]["count"] == 7
    assert report["ci"]["pass_count"] == 6
    assert report["ci"]["false_acceptance_count"] == 1
    assert report["ws1_fault_hook_count"] == 18
    assert report["ws4_recovery_case_count"] == 6
    assert report["decision"] == "STOP_FALSE_ACCEPTANCE_GAPS_RETAINED"
    assert report["hardware_write_count"] == report["physical_movement_count"] == 0


def test_independent_observers_close_consequential_simulated_gaps_only() -> None:
    readiness = load_first_motion_fixture(READINESS_FIXTURE)
    fixture = load_independent_observation_fixture(OBSERVATION_FIXTURE)
    report = run_independent_observation_drills(
        fixture, run_wrong_model_drills(readiness))
    assert report["original_gap_count"] == 33
    assert report["consequential_some_or_all_count"] > 0
    assert report["undetected_consequential_count"] == 0
    assert report["decision"] == "PASS_ZERO_UNDETECTED_CONSEQUENTIAL_SIMULATION_ONLY"
    assert report["official_wrong_model_report_changed"] is False
    assert report["physical_observer_qualified"] is False
    assert report["hardware_write_count"] == report["physical_movement_count"] == 0
    assert report["real_command_count"] == report["permit_count"] == 0
    assert report["transport_count"] == 0


def test_candidate_shadow_exercises_a_to_f_without_changing_official_stop() -> None:
    readiness = load_first_motion_fixture(READINESS_FIXTURE)
    report = run_exploratory_candidate_staged_rehearsal(
        readiness, load_emulator_fixture(FIXTURE),
        load_independent_observation_fixture(OBSERVATION_FIXTURE))
    assert report["stages_exercised"] == list("ABCDEF")
    assert report["predicted_telemetry_sample_count"] == 6 * 33
    assert report["official_first_no_go_stage_unchanged"] == "A"
    assert report["official_readiness"] == "NOT_READY_FOR_FIRST_POWERED_MOTION"
    assert report["collision_installed"] is False
    assert report["collision_installed_profile_eligible"] is False
    assert report["candidate_collision_decision"] != "PASS"
    assert all(row["status"] == "EXERCISED_SHADOW_ONLY" for row in report["stage_results"])
    assert report["staged_motion_executions"] == 0
    assert report["hardware_write_count"] == report["physical_movement_count"] == 0
    assert report["real_command_count"] == report["permit_count"] == 0
    assert report["transport_count"] == 0


def test_candidate_collision_attribution_preserves_unknown_stages_and_authority() -> None:
    report = run_candidate_collision_attribution(
        load_collision_attribution_fixture(COLLISION_ATTRIBUTION_FIXTURE),
        workspace=ROOT)
    assert report["configuration_count"] == 40
    assert report["stage_mapping"]["A"] == "NOT_EVALUATED_NO_STAGE_TRAJECTORY"
    assert report["stage_mapping"]["D"] == "NOT_EVALUATED_TEST_PAD_ABSENT"
    assert report["stage_mapping"]["E"] == "EVALUATED_BY_46_KEYBOARD_TARGET_POSES"
    assert report["official_collision_decision_changed"] is False
    assert report["installed_exclusions_created"] == 0
    assert report["hardware_write_count"] == report["physical_movement_count"] == 0
    assert report["real_command_count"] == report["permit_count"] == 0
    assert report["transport_count"] == 0
