"""Record a gravity-on, drive-controlled multi-pose trajectory in Isaac Sim.

The probe has no hardware authority.  It emits both a rich telemetry CSV and the
position/velocity/command CSV layout accepted by Isaac Sim's SysID extension.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from drive_controlled_hover_probe import EXPECTED_DOFS, _canonical, _digest, load_profile


SCHEMA = "tactevra.isaac_lm0b_multi_pose_sysid_trajectory.v1"
POSE_IDS = ("PARK", "H", "1", "PERIOD")


def select_pose_sequence(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Select one governed endpoint for each excitation pose."""
    samples = bundle.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("replay bundle has no samples")
    selected: list[dict[str, Any]] = []
    park = next(
        (sample for sample in samples if sample.get("phase") == "PARK" and sample.get("phase_endpoint") is True),
        None,
    )
    if park is None:
        raise ValueError("replay bundle lacks a PARK endpoint")
    selected.append({"pose_id": "PARK", "sample": park})
    for pose_id in POSE_IDS[1:]:
        sample = next(
            (
                row
                for row in samples
                if row.get("target_id") == pose_id
                and row.get("phase") == "HOVER"
                and row.get("phase_endpoint") is True
            ),
            None,
        )
        if sample is None:
            raise ValueError(f"replay bundle lacks a {pose_id}-hover endpoint")
        selected.append({"pose_id": pose_id, "sample": sample})

    result = []
    for item in selected:
        joints = item["sample"].get("joint_positions_rad")
        if not isinstance(joints, dict) or not all(name in joints for name in EXPECTED_DOFS[:5]):
            raise ValueError(f"{item['pose_id']} endpoint has incomplete joint positions")
        vector = [float(joints[name]) for name in EXPECTED_DOFS[:5]] + [0.0]
        if not all(math.isfinite(value) for value in vector):
            raise ValueError(f"{item['pose_id']} endpoint has non-finite joint positions")
        result.append({"pose_id": item["pose_id"], "target_rad": vector})
    return result


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path.read_bytes()


def _numbers(values: list[float]) -> list[str]:
    return [format(float(value), ".17g") for value in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--telemetry-output", type=Path, required=True)
    parser.add_argument("--sysid-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        usd = args.usd.resolve(strict=True)
        bundle_raw = args.bundle.resolve(strict=True).read_bytes()
        bundle = json.loads(bundle_raw)
        profile, profile_raw = load_profile(args.profile.resolve(strict=True))
        if profile["schema"] != "tactevra.isaac_lm0b_geometry_prior_profile.v1":
            raise ValueError("multi-pose telemetry requires the geometry-prior profile")
        poses = select_pose_sequence(bundle)

        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import Gf, UsdPhysics

        if not omni.usd.get_context().open_stage(str(usd)):
            raise RuntimeError("Isaac could not open the robot USD")
        for _ in range(5):
            app.update()
        stage = omni.usd.get_context().get_stage()
        scene = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
        scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        scene.CreateGravityMagnitudeAttr().Set(profile["gravity_m_s2"])
        for prim_path, row in profile["rigid_body_properties"].items():
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                raise RuntimeError(f"missing rigid body {prim_path}")
            api = UsdPhysics.MassAPI.Apply(prim)
            api.CreateMassAttr().Set(row["mass_kg"])
            api.CreateCenterOfMassAttr().Set(Gf.Vec3f(*row["center_of_mass_m"]))
            api.CreateDiagonalInertiaAttr().Set(Gf.Vec3f(*row["diagonal_inertia_kg_m2"]))
            axes = row["principal_axes_wxyz"]
            api.CreatePrincipalAxesAttr().Set(Gf.Quatf(axes[0], axes[1], axes[2], axes[3]))

        dt = float(profile["physics_dt_s"])
        SimulationManager.set_physics_dt(dt)
        SimulationManager.initialize_physics()
        articulation = Articulation("/roarm_m3")
        for _ in range(10):
            app.update()
        if list(articulation.dof_names) != EXPECTED_DOFS or not articulation.is_physics_tensor_entity_valid():
            raise RuntimeError("governed articulation identity is unavailable")
        dof = profile["dof"]
        articulation.set_dof_gains([[dof["stiffness"]] * 6], [[dof["damping"]] * 6])
        articulation.set_dof_max_efforts([[dof["maximum_effort"]] * 6])
        articulation.set_dof_max_velocities([[dof["maximum_velocity_rad_s"]] * 6])

        park = poses[0]["target_rad"]
        articulation.set_world_poses([[0.0, 0.0, 0.0]], [[1.0, 0.0, 0.0, 0.0]])
        articulation.set_dof_positions([park])
        articulation.set_dof_velocities([[0.0] * 6])
        articulation.set_dof_position_targets([park])
        SimulationManager.step(steps=profile["initial_settle_steps"])

        telemetry_rows: list[list[object]] = []
        sysid_rows: list[list[object]] = []
        summaries = []
        global_step = 0
        for pose in poses:
            target = pose["target_rad"]
            articulation.set_dof_position_targets([target])
            peak_effort = [0.0] * 6
            peak_projected = [0.0] * 6
            for local_step in range(1, profile["target_steps"] + 1):
                SimulationManager.step(steps=1)
                global_step += 1
                positions = articulation.get_dof_positions().numpy().tolist()[0]
                velocities = articulation.get_dof_velocities().numpy().tolist()[0]
                efforts = articulation.get_dof_efforts().numpy().tolist()[0]
                projected = articulation.get_dof_projected_joint_forces().numpy().tolist()[0]
                values = positions + velocities + efforts + projected
                if not all(math.isfinite(float(value)) for value in values):
                    raise RuntimeError(f"non-finite telemetry at physics step {global_step}")
                peak_effort = [max(peak_effort[i], abs(efforts[i])) for i in range(6)]
                peak_projected = [max(peak_projected[i], abs(projected[i])) for i in range(6)]
                time_s = global_step * dt
                telemetry_rows.append(
                    [format(time_s, ".17g"), pose["pose_id"], local_step]
                    + _numbers(positions + velocities + target + efforts + projected)
                )
                sysid_rows.append([format(time_s, ".17g")] + _numbers(positions + velocities + target))
            final = articulation.get_dof_positions().numpy().tolist()[0]
            summaries.append(
                {
                    "pose_id": pose["pose_id"],
                    "target_rad": target,
                    "final_rad": final,
                    "maximum_final_joint_error_rad": max(abs(final[i] - target[i]) for i in range(6)),
                    "peak_applied_actuation_force_nm": peak_effort,
                    "peak_projected_joint_force_nm": peak_projected,
                }
            )

        q = [f"q{i}" for i in range(1, 7)]
        dq = [f"dq{i}" for i in range(1, 7)]
        cmd = [f"cmd{i}" for i in range(1, 7)]
        effort = [f"applied_actuation_force_nm_{i}" for i in range(1, 7)]
        projected = [f"projected_joint_force_nm_{i}" for i in range(1, 7)]
        telemetry_raw = _write_csv(
            args.telemetry_output,
            ["time", "pose_id", "pose_step", *q, *dq, *cmd, *effort, *projected],
            telemetry_rows,
        )
        sysid_raw = _write_csv(args.sysid_output, ["time", *q, *dq, *cmd], sysid_rows)
        import omni.kit.app

        extension_name = "isaacsim.robot_setup.sysid"
        extension_manager = omni.kit.app.get_app().get_extension_manager()
        extension_manager.set_extension_enabled_immediate(extension_name, True)
        from isaacsim.robot_setup.sysid.trajectory_csv import load_sysid_trajectory_csv

        dataset = load_sysid_trajectory_csv(str(args.sysid_output.resolve()))
        if dataset.num_joints != 6 or len(dataset.times) != len(sysid_rows):
            raise RuntimeError("Isaac SysID loader readback shape mismatch")
        loader_readback = {
            "extension": extension_name,
            "num_joints": dataset.num_joints,
            "samples": len(dataset.times),
            "duration_s": dataset.duration,
            "positions_shape": list(dataset.positions.shape),
            "commands_shape": list(dataset.commands.shape),
        }
        maximum_error = max(row["maximum_final_joint_error_rad"] for row in summaries)
        passed = maximum_error <= profile["maximum_final_joint_error_rad"]
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "status": "PASS" if passed else "BLOCKED_TRACKING_ERROR",
            "evidence_class": "PROVISIONAL_SIM_TO_SIM_SYSID_TRAJECTORY",
            "profile_schema": profile["schema"],
            "source_bindings": {
                "usd_sha256": _digest(usd.read_bytes()),
                "bundle_file_sha256": _digest(bundle_raw),
                "profile_file_sha256": _digest(profile_raw),
            },
            "outputs": {
                "rich_telemetry_csv_sha256": _digest(telemetry_raw),
                "isaac_sysid_csv_sha256": _digest(sysid_raw),
                "isaac_sysid_csv_layout": "time,q1..q6,dq1..dq6,cmd1..cmd6",
                "isaac_sysid_loader_readback": loader_readback,
            },
            "pose_order": list(POSE_IDS),
            "samples": len(sysid_rows),
            "physics_dt_s": dt,
            "physics_steps": profile["initial_settle_steps"] + global_step,
            "state_teleports_after_initialization": 0,
            "maximum_final_joint_error_rad": maximum_error,
            "threshold_rad": profile["maximum_final_joint_error_rad"],
            "pose_summaries": summaries,
            "effort_semantics": {
                "applied_actuation_force_nm": "ISAAC_EXPLICIT_ACTUATION_FORCE_NOT_INTERNAL_DRIVE_OUTPUT",
                "projected_joint_force_nm": "ISAAC_LINK_INCOMING_FORCE_PROJECTED_ON_DOF",
                "physical_t1051_load": "NOT_CAPTURED_OR_CALIBRATED",
            },
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "geometry_derived_provisional_mass_properties",
                "provisional_mass_distribution_and_drive_parameters",
                "sim_to_sim_trajectory_does_not_validate_physical_parameters",
                "internal_position_drive_effort_is_not_exposed_by_applied_actuation_force_channel",
                "no_collision_or_contact_geometry",
                "t1051_raw_load_is_not_si_torque",
            ],
        }
        result["receipt_sha256"] = _digest(_canonical(result))
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(
            json.dumps({"status": result["status"], "receipt_sha256": result["receipt_sha256"]}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return 0 if passed else 2
    except BaseException as exc:
        args.status_output.write_text(
            json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
