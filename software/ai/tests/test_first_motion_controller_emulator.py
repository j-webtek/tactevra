from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from rocell.arm.all_joint_command import all_joint_command
from rocell_ai.first_motion_controller_emulator import (
    InMemoryT102Controller,
    ServoRangeSample,
    load_emulator_fixture,
    run_controller_emulator,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_controller_emulator_v1.json"
SOURCE = ROOT / "software/ai/rocell_ai/first_motion_controller_emulator.py"


def _sample() -> ServoRangeSample:
    return ServoRangeSample("test", 5, 25, 100, 1, 0.004, 0.001, 20, 1)


def test_fixture_is_hash_bound_and_zero_authority() -> None:
    fixture = load_emulator_fixture(FIXTURE)
    assert fixture["scope"] == "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
    assert not any(fixture["counters"].values())
    assert fixture["controller_emulator"]["protocol"]["command_family"] == "T102_ALL_JOINT_ABSOLUTE"
    assert "no T101/T102 production send adapter" in fixture["controller_emulator"]["protocol"]["production_transport_gap"]


def test_full_roundtrip_covers_ids_directions_ranges_and_faults() -> None:
    result = run_controller_emulator(load_emulator_fixture(FIXTURE))
    assert result["decision"] == "PARTIAL_PASS_PROTOCOL_EMULATION_RUNTIME_PATH_GAP_RETAINED"
    assert result["sample_count"] == 14
    assert result["roundtrip_case_count"] == 182
    assert result["all_direction_correct"] is True
    assert result["all_logical_joint_ids"] == [1, 2, 3, 4, 5, 6]
    assert result["all_servo_ids"] == [11, 12, 13, 14, 15, 16, 17]
    assert result["non_echo_case_count"] == result["roundtrip_case_count"]
    assert result["fault_detection_rate"] == 1.0
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
