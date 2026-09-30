"""Replay a source-bound arm joint schedule in an in-memory Isaac articulation.

Samples are teleported into the simulator for independent FK comparison.  The
probe does not step physics, generate controller commands, or access hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any


SCHEMA = "tactevra.isaac_joint_schedule_replay.v1"
EXPECTED_DOFS = [
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
]
HAND_TCP_PATH = "/roarm_m3/Geometry/world/base_link/link1/link2/link3/link4/link5/hand_tcp"
TIP_ERROR_LIMIT_MM = 0.25
JOINT_TRACKING_LIMIT_RAD = 1e-6


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _matrix_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3)]
        for row in range(3)
    ]


def _matrix_vector(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(matrix[row][column] * vector[column] for column in range(3)) for row in range(3)]


def _quaternion_xyzw_matrix(value: list[float]) -> list[list[float]]:
    x, y, z, w = value
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def _driver_version() -> str:
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    versions = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    if len(versions) != 1:
        raise RuntimeError("nvidia-smi returned inconsistent driver versions")
    return versions.pop()


def _validate_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("schema") not in {
        "tactevra.arm_joint_schedule_replay_bundle.v1",
        "tactevra.arm_joint_schedule_replay_bundle.v2",
    }:
        raise ValueError("unsupported replay bundle schema")
    claimed = bundle.get("bundle_sha256")
    unsigned = dict(bundle)
    unsigned.pop("bundle_sha256", None)
    if claimed != _digest(_canonical(unsigned)):
        raise ValueError("replay bundle digest mismatch")
    if bundle.get("scope") != "SYNTHETIC_OFFLINE_ISAAC_REPLAY_ONLY" \
            or bundle.get("hardware_access") is not False \
            or bundle.get("physical_authority") is not False \
            or bundle.get("controller_commands") != [] \
            or bundle.get("hardware_writes") != 0 \
            or bundle.get("physical_movements") != 0:
        raise ValueError("replay bundle crossed the zero-authority boundary")
    samples = bundle.get("samples")
    if not isinstance(samples, list) or len(samples) != bundle.get("sample_count"):
        raise ValueError("replay sample count mismatch")
    if [sample.get("sequence") for sample in samples] != list(range(len(samples))):
        raise ValueError("replay sample sequence is not contiguous")
    contacts = [
        item.get("target_id") for item in samples
        if item.get("phase") == "CONTACT" and item.get("phase_endpoint") is True
    ]
    if contacts != bundle.get("ordered_target_ids"):
        raise ValueError("contact order or repeated targets changed")
    if bundle["schema"].endswith(".v2"):
        producer = bundle.get("producer")
        if not isinstance(producer, dict) or producer != {
            "kind": "ACTUAL_SHARED_EMITTER",
            "input_sha256": producer.get("input_sha256") if isinstance(producer, dict) else None,
            "payload_sha256": bundle.get("source", {}).get("batch_sha256"),
            "synthetic_observations": True,
            "deployment_qualification_claimed": False,
        }:
            raise ValueError("actual-emitter producer lineage is invalid")
        if not isinstance(producer["input_sha256"], str) \
                or len(producer["input_sha256"]) != 64:
            raise ValueError("actual-emitter input digest is invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", type=Path, required=True)
    parser.add_argument("--import-receipt", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--virtual-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        usd = args.usd.resolve(strict=True)
        receipt_raw = args.import_receipt.resolve(strict=True).read_bytes()
        import_receipt = json.loads(receipt_raw)
        bundle_raw = args.bundle.resolve(strict=True).read_bytes()
        bundle = json.loads(bundle_raw)
        profile_raw = args.virtual_profile.resolve(strict=True).read_bytes()
        profile = json.loads(profile_raw)
        _validate_bundle(bundle)
        if import_receipt["external_files"][0]["sha256"] != _digest(usd.read_bytes()):
            raise ValueError("robot USD differs from its import receipt")
        if bundle["source"]["virtual_profile_sha256"] != _digest(profile_raw):
            raise ValueError("virtual geometry profile differs from the arm schedule source")
        if profile.get("status") != "UNMEASURED_SENSITIVITY_OVERLAY" \
                or profile.get("simulation_only") is not True \
                or profile.get("physical_release_effect") != "NONE":
            raise ValueError("virtual profile is not a simulation-only sensitivity overlay")

        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import UsdGeom

        if not omni.usd.get_context().open_stage(str(usd)):
            raise RuntimeError("Isaac could not open the governed robot USD")
        for _ in range(5):
            app.update()
        articulation = Articulation("/roarm_m3")
        if list(articulation.dof_names) != EXPECTED_DOFS:
            raise RuntimeError("Isaac articulation DOF order differs from the arm schedule")
        SimulationManager.initialize_physics()
        for _ in range(10):
            app.update()
        if not articulation.is_physics_tensor_entity_valid():
            raise RuntimeError("Isaac physics articulation view is unavailable")

        stage = omni.usd.get_context().get_stage()
        hand_tcp = stage.GetPrimAtPath(HAND_TCP_PATH)
        if not hand_tcp.IsValid():
            raise RuntimeError("hand_tcp prim is unavailable")
        local = UsdGeom.Xformable(hand_tcp).GetLocalTransformation()
        hand_local_translation = [float(local[3][index]) for index in range(3)]
        hand_local_rotation = [
            [float(local[column][row]) for column in range(3)] for row in range(3)
        ]
        link5_index = list(articulation.link_names).index("link5")
        physical = profile["study_input"]["physical_placement_input"]
        matrix = physical["matrix_row_major"]
        base_translation = [matrix[3] / 1000.0, matrix[7] / 1000.0, matrix[11] / 1000.0]
        yaw = physical["base_yaw_board_rad"]
        base_quaternion_wxyz = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]
        tool_length_m = profile["study_input"]["route_tool_lengths_mm"]["keyboard"] / 1000.0

        replay_samples = []
        for sample in bundle["samples"]:
            desired = [sample["joint_positions_rad"][name] for name in EXPECTED_DOFS[:5]] + [0.0]
            articulation.set_world_poses([base_translation], [base_quaternion_wxyz])
            articulation.set_dof_positions([desired])
            observed = articulation.get_dof_positions().numpy().tolist()[0]
            transforms = articulation._physics_articulation_view.get_link_transforms().numpy().tolist()[0]
            link5 = transforms[link5_index]
            link5_translation = [float(value) for value in link5[:3]]
            link5_rotation = _quaternion_xyzw_matrix([float(value) for value in link5[3:]])
            hand_rotation = _matrix_multiply(link5_rotation, hand_local_rotation)
            hand_offset = _matrix_vector(link5_rotation, hand_local_translation)
            hand_translation = [link5_translation[i] + hand_offset[i] for i in range(3)]
            tip_offset = _matrix_vector(hand_rotation, [0.0, 0.0, -tool_length_m])
            tip_mm = [1000.0 * (hand_translation[i] + tip_offset[i]) for i in range(3)]
            expected_mm = sample["expected_tool_tip_board_mm"]
            tip_error = math.dist(tip_mm, expected_mm)
            joint_error = max(abs(observed[i] - desired[i]) for i in range(6))
            replay_samples.append({
                "sequence": sample["sequence"],
                "time_from_start_ns": sample["time_from_start_ns"],
                "phase": sample["phase"],
                "phase_endpoint": sample["phase_endpoint"],
                "action_index": sample["action_index"],
                "target_id": sample["target_id"],
                "expected_tool_tip_board_mm": expected_mm,
                "isaac_tool_tip_board_mm": tip_mm,
                "tool_tip_error_mm": tip_error,
                "maximum_joint_tracking_error_rad": joint_error,
            })

        contact_samples = [
            item for item in replay_samples
            if item["phase"] == "CONTACT" and item["phase_endpoint"]
        ]
        max_tip_error = max(item["tool_tip_error_mm"] for item in replay_samples)
        max_joint_error = max(item["maximum_joint_tracking_error_rad"] for item in replay_samples)
        replay_pass = max_tip_error <= TIP_ERROR_LIMIT_MM \
            and max_joint_error <= JOINT_TRACKING_LIMIT_RAD
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "evidence_class": "KINEMATIC_SCHEDULE_REPLAY_DIAGNOSTIC_ONLY",
            "driver_version": _driver_version(),
            "source_bindings": {
                "bundle_file_sha256": _digest(bundle_raw),
                "bundle_sha256": bundle["bundle_sha256"],
                "arm_commit": bundle["source"]["arm_commit"],
                "arm_report_sha256": bundle["source"]["arm_report_sha256"],
                "robot_usd_sha256": _digest(usd.read_bytes()),
                "robot_import_receipt_file_sha256": _digest(receipt_raw),
                "virtual_profile_sha256": _digest(profile_raw),
            },
            "sample_count": len(replay_samples),
            "ordered_contact_target_ids": [item["target_id"] for item in contact_samples],
            "contact_events": contact_samples,
            "thresholds": {
                "maximum_tool_tip_error_mm": TIP_ERROR_LIMIT_MM,
                "maximum_joint_tracking_error_rad": JOINT_TRACKING_LIMIT_RAD,
            },
            "maximum_tool_tip_error_mm": max_tip_error,
            "maximum_joint_tracking_error_rad": max_joint_error,
            "all_samples_pass": replay_pass,
            "physics_steps": 0,
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "remaining_blockers": bundle["remaining_arm_blockers"],
            "limitations": [
                "unmeasured_simulation_only_robot_layout_and_tool_length",
                "joint_teleport_fk_replay_without_dynamics_or_controller_tracking",
                "installed_geometry_collision_screening_not_executed",
                "invalid_imported_mass_and_inertia_placeholders",
                "no_contact_force_key_travel_or_physical_qualification",
            ],
        }
        result["receipt_sha256"] = _digest(_canonical(result))
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "PASS" if replay_pass else "BLOCKED_PARITY_ERROR",
            "receipt_sha256": result["receipt_sha256"],
            "sample_count": len(replay_samples),
            "maximum_tool_tip_error_mm": max_tip_error,
        }, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
