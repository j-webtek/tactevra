"""Zero-authority controller-shaped replay for a retained photographed layout.

The photographs are qualitative context only.  Metric robot and keyboard poses
come from the hash-bound tripod-era compatibility fixture.  This module has no
transport or hardware adapter and executes only the in-memory T102 controller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.arm.all_joint_command import all_joint_command
from rocell_ai.cpu_contact_and_ws3 import _load_geometry, load_cpu_contact_fixture
from rocell_ai.first_motion_clearance_waypoints import (
    _clearance_route,
    _solve_seeded,
    _tip_xyz,
)
from rocell_ai.first_motion_consolidated import (
    _load_bound,
    _resolve,
    load_consolidated_fixture,
)
from rocell_ai.first_motion_controller_emulator import (
    InMemoryT102Controller,
    _baseline_joints,
    _execute_strict_runtime_path,
    _range_samples,
    load_emulator_fixture,
)

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
FAULTS = (
    "DROPPED_MESSAGE",
    "DELAYED_TELEMETRY",
    "SERVO_NOT_RESPONDING",
    "STALL_OVERLOAD",
    "ESTOP",
    "POWER_INTERRUPTION",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _six(values: tuple[float, ...], hand: float) -> tuple[float, ...]:
    if len(values) != 5:
        raise ValueError("arm waypoint must contain five joints")
    return (*values, hand)


def _phase_endpoints(
    rows: list[tuple[str, tuple[float, ...]]], expected: tuple[str, ...],
) -> list[tuple[str, tuple[float, ...]]]:
    endpoints: list[tuple[str, tuple[float, ...]]] = []
    for phase in expected:
        matching = [joints for row_phase, joints in rows if row_phase == phase]
        if not matching:
            raise ValueError(f"route omitted phase {phase}")
        endpoints.append((phase, matching[-1]))
    return endpoints


def run_captured_layout_sequence(
    fixture: dict[str, Any], *, workspace: Path, target_id: str = "G",
) -> dict[str, Any]:
    """Rehearse an approach, press, retract, return, and controller faults."""

    contact_path = _resolve(workspace, fixture["bindings"]["cpu_contact_fixture"]["path"])
    contact = load_cpu_contact_fixture(contact_path, workspace=workspace)
    contact = dict(contact)
    contact["bindings"] = dict(contact["bindings"])
    contact["bindings"]["kinematic_compatibility_context"] = fixture["bindings"][
        "kinematic_compatibility_context"
    ]
    _, pose_family, world = _load_geometry(contact, workspace=workspace)
    profile = next(
        row for row in pose_family["profiles"]
        if row["pose_bundle"]["tool_configuration"][
            "total_hand_tcp_to_tip_length_mm"] == 110.0
    )
    bundle = profile["pose_bundle"]
    target = next(row for row in bundle["poses"] if row["target_id"] == target_id)
    tool_length = 110.0
    contact_joints = tuple(float(value) for value in target["joint_positions_rad"])
    xyz = target["contact_target_board_mm"]
    contact_xyz = (float(xyz["x"]), float(xyz["y"]), float(xyz["z"]))
    hover_xyz = (*contact_xyz[:2], contact_xyz[2] + 30.0)
    hover = _solve_seeded(world, world.solver(tool_length), hover_xyz, contact_joints)
    if hover is None:
        raise ValueError("target hover inverse kinematics did not converge")

    park_screen = _load_bound(fixture["bindings"]["park_screen"], workspace)
    park_row = next(
        row for row in park_screen["top_candidates"]
        if row["pose_id"] == fixture["configuration"]["park_pose_id"]
    )
    park = tuple(
        float(park_row["joint_positions_rad"][name])
        for name in bundle["joint_order"]
    )
    emulator_path = _resolve(workspace, fixture["bindings"]["emulator_fixture"]["path"])
    emulator = load_emulator_fixture(emulator_path)
    baseline = _baseline_joints(emulator)
    sample = _range_samples(emulator["controller_emulator"])[0]

    park_xyz = _tip_xyz(world, park, tool_length)
    start_route, start_failure = _clearance_route(
        world, start=baseline[:5], end=park, end_xyz=park_xyz,
        tool_length=tool_length, transit_z=100.0, samples=3,
    )
    target_route, target_failure = _clearance_route(
        world, start=park, end=hover, end_xyz=hover_xyz,
        tool_length=tool_length, transit_z=100.0, samples=3,
    )
    return_route, return_failure = _clearance_route(
        world, start=hover, end=park, end_xyz=park_xyz,
        tool_length=tool_length, transit_z=100.0, samples=3,
    )
    failures = [value for value in (start_failure, target_failure, return_failure) if value]
    if failures:
        raise ValueError(f"command sequence route failed: {failures}")

    planned = [
        (f"START_{phase}", joints)
        for phase, joints in _phase_endpoints(
            start_route, ("ASCEND", "TRANSIT", "DESCEND"))
    ]
    planned.extend(
        (f"TARGET_{phase}", joints)
        for phase, joints in _phase_endpoints(
            target_route, ("ASCEND", "TRANSIT", "DESCEND"))
    )
    planned.extend((("PRESS", contact_joints), ("RETRACT", hover)))
    planned.extend(
        (f"RETURN_{phase}", joints)
        for phase, joints in _phase_endpoints(
            return_route, ("ASCEND", "TRANSIT", "DESCEND"))
    )

    controller = InMemoryT102Controller(baseline, sample, seed=1907112)
    commands = []
    for index, (phase, joints) in enumerate(planned, start=1):
        command = all_joint_command(
            _six(joints, baseline[5]), speed=sample.speed_setting,
            acceleration=sample.acceleration_setting,
        )
        plant, runtime, frame = _execute_strict_runtime_path(
            emulator, controller, command,
            case_id=f"captured-layout:{target_id}:{index}:{phase}",
        )
        commands.append({
            "ordinal": index,
            "phase": phase,
            "command": command,
            "wire_bytes_sha256": frame.wire_bytes_sha256,
            "runtime_status": runtime["runtime_status"],
            "runtime_terminal_reason": runtime["runtime_terminal_reason"],
            "feedback_exchange_count": runtime["runtime_feedback_exchange_count"],
            "telemetry_sample_count": len(plant["telemetry"]),
            "predicted_endpoint_joints_rad": plant["measured_joints_rad"],
            "hardware_write_count": plant["hardware_write_count"],
            "physical_movement_count": plant["physical_movement_count"],
            "real_transport_open_count": plant["real_transport_open_count"],
            "physical_authority": plant["physical_authority"],
        })

    press_command = all_joint_command(
        _six(contact_joints, baseline[5]), speed=sample.speed_setting,
        acceleration=sample.acceleration_setting,
    )
    faults = []
    for index, fault in enumerate(FAULTS):
        fault_controller = InMemoryT102Controller(
            _six(hover, baseline[5]), sample, seed=1907200 + index,
        )
        plant, runtime, frame = _execute_strict_runtime_path(
            emulator, fault_controller, press_command,
            case_id=f"captured-layout:{target_id}:fault:{fault}", fault=fault,
        )
        faults.append({
            "fault": fault,
            "plant_status": plant["status"],
            "wire_bytes_sha256": frame.wire_bytes_sha256,
            "runtime_status": runtime["runtime_status"],
            "runtime_terminal_reason": runtime["runtime_terminal_reason"],
            "hardware_write_count": plant["hardware_write_count"],
            "physical_movement_count": plant["physical_movement_count"],
            "real_transport_open_count": plant["real_transport_open_count"],
            "physical_authority": plant["physical_authority"],
        })

    consolidated = _load_bound({
        "path": "software/ai/sim/evidence/first_motion_consolidated_tripod_result_v2.json",
        "sha256": hashlib.sha256((
            workspace / "software/ai/sim/evidence/first_motion_consolidated_tripod_result_v2.json"
        ).read_bytes()).hexdigest(),
    }, workspace)
    clearance = next(
        row for row in consolidated["stage_c_exact_sweep"]["rows"]
        if row["target_id"] == target_id
        and row["tool_configuration_sha256"] == profile["tool_configuration_sha256"]
    )
    result = {
        "schema": "tactevra.captured_layout_command_sequence.v1",
        "scope": SCOPE,
        "source_bindings": {
            "consolidated_fixture_sha256": fixture["fixture_sha256"],
            "configuration_sha256": fixture["configuration"]["section_sha256"],
            "emulator_fixture": fixture["bindings"]["emulator_fixture"],
            "kinematic_compatibility_context": fixture["bindings"][
                "kinematic_compatibility_context"
            ],
            "pose_family": fixture["bindings"]["pose_family"],
            "consolidated_result": {
                "path": "software/ai/sim/evidence/first_motion_consolidated_tripod_result_v2.json",
                "sha256": hashlib.sha256((
                    workspace
                    / "software/ai/sim/evidence/first_motion_consolidated_tripod_result_v2.json"
                ).read_bytes()).hexdigest(),
                "receipt_sha256": consolidated["receipt_sha256"],
            },
        },
        "target_id": target_id,
        "scene_basis": (
            "retained hash-bound robot/workcell model corresponding to the "
            "photographed arm and keyboard layout; no image-derived 3D registration claim"
        ),
        "target_contact_board_mm": list(contact_xyz),
        "target_hover_board_mm": list(hover_xyz),
        "tool_length_mm": tool_length,
        "park_pose_id": fixture["configuration"]["park_pose_id"],
        "commands": commands,
        "command_count": len(commands),
        "all_nominal_commands_settled": all(
            row["runtime_terminal_reason"] == "COMMAND_SETTLED_REHEARSAL_COMPLETE"
            for row in commands
        ),
        "fault_rehearsals": faults,
        "fault_count": len(faults),
        "all_faults_terminal_no_retry": all(
            row["runtime_status"] == "TERMINAL_NO_RETRY" for row in faults
        ),
        "minimum_non_target_key_clearance_mm": clearance["minimum_key_clearance_mm"],
        "physical_accuracy_claim": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "transport_count": 0,
        "physical_authority": False,
        "official_readiness": "NOT_READY_FOR_FIRST_POWERED_MOTION",
        "limitations": [
            "Photographs do not provide calibrated camera intrinsics, camera extrinsics, depth, or current encoder state.",
            "The sequence uses the retained board and robot model rather than estimating a metric pose from handheld photographs.",
            "Predicted telemetry is synthetic and cannot establish installed-path clearance or physical accuracy.",
            "No result authorizes copying these commands to a physical controller.",
        ],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument(
        "--fixture", type=Path,
        default=Path("software/ai/sim/evidence/first_motion_consolidated_tripod_v2.json"),
    )
    parser.add_argument("--target", default="G")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    fixture_path = args.fixture if args.fixture.is_absolute() else workspace / args.fixture
    fixture = load_consolidated_fixture(fixture_path, workspace=workspace)
    result = run_captured_layout_sequence(
        fixture, workspace=workspace, target_id=args.target,
    )
    output = args.output if args.output.is_absolute() else workspace / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({
        "target_id": result["target_id"],
        "command_count": result["command_count"],
        "fault_count": result["fault_count"],
        "all_nominal_commands_settled": result["all_nominal_commands_settled"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
