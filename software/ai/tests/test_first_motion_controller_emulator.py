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

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_controller_emulator_v1.json"
SOURCE = ROOT / "software/ai/rocell_ai/first_motion_controller_emulator.py"
READINESS_FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_readiness_v1.json"


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
