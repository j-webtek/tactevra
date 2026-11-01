"""Run a physics-stepped PARK-to-H-hover Isaac diagnostic with zero hardware authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA = "tactevra.isaac_lm0_drive_controlled_hover.v1"
EXPECTED_DOFS = [
    "base_link_to_link1", "link1_to_link2", "link2_to_link3",
    "link3_to_link4", "link4_to_link5", "link5_to_gripper_link",
]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_profile(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if value.get("schema") != "tactevra.isaac_lm0_dynamic_profile.v1":
        raise ValueError("unsupported LM0 profile")
    if value.get("status") != "PROVISIONAL_SIMULATION_ONLY" or value.get("simulation_only") is not True:
        raise ValueError("LM0 profile must remain provisional and simulation-only")
    if value.get("physical_authority") is not False or value.get("gravity_m_s2") != 0.0:
        raise ValueError("LM0A profile crossed its zero-authority gravity-off boundary")
    masses = value.get("rigid_body_mass_kg")
    if not isinstance(masses, dict) or not math.isclose(sum(masses.values()), 1.021, abs_tol=1e-9):
        raise ValueError("LM0A provisional masses must total 1.021 kg")
    return value, raw


def select_endpoints(bundle: dict[str, Any]) -> tuple[list[float], list[float]]:
    samples = bundle.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("replay bundle has no samples")
    park = samples[0]
    hover = next((s for s in samples if s.get("target_id") == "H" and s.get("phase") == "HOVER" and s.get("phase_endpoint") is True), None)
    if park.get("phase") != "PARK" or hover is None:
        raise ValueError("replay bundle lacks PARK or H-hover endpoint")
    def vector(sample: dict[str, Any]) -> list[float]:
        joints = sample["joint_positions_rad"]
        return [float(joints[name]) for name in EXPECTED_DOFS[:5]] + [0.0]
    return vector(park), vector(hover)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
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
        park, hover = select_endpoints(bundle)

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
        inertia = Gf.Vec3f(*profile["diagonal_inertia_kg_m2"])
        for prim_path, mass in profile["rigid_body_mass_kg"].items():
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                raise RuntimeError(f"missing rigid body {prim_path}")
            api = UsdPhysics.MassAPI.Apply(prim)
            api.CreateMassAttr().Set(mass)
            api.CreateCenterOfMassAttr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
            api.CreateDiagonalInertiaAttr().Set(inertia)
            api.CreatePrincipalAxesAttr().Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))

        SimulationManager.set_physics_dt(profile["physics_dt_s"])
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

        # One initialization placement is allowed; no state teleport occurs afterward.
        articulation.set_world_poses([[0.0, 0.0, 0.0]], [[1.0, 0.0, 0.0, 0.0]])
        articulation.set_dof_positions([park])
        articulation.set_dof_velocities([[0.0] * 6])
        articulation.set_dof_position_targets([park])
        SimulationManager.step(steps=profile["initial_settle_steps"])
        articulation.set_dof_position_targets([hover])
        trace = []
        for step in range(1, profile["target_steps"] + 1):
            SimulationManager.step(steps=1)
            if step % 20 == 0 or step == profile["target_steps"]:
                observed = articulation.get_dof_positions().numpy().tolist()[0]
                trace.append({"step": step, "maximum_joint_error_rad": max(abs(observed[i] - hover[i]) for i in range(6))})
        final = articulation.get_dof_positions().numpy().tolist()[0]
        max_error = max(abs(final[i] - hover[i]) for i in range(6))
        passed = max_error <= profile["maximum_final_joint_error_rad"]
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "status": "PASS" if passed else "BLOCKED_TRACKING_ERROR",
            "evidence_class": "PROVISIONAL_GRAVITY_OFF_DRIVE_CONTROL_DIAGNOSTIC",
            "source_bindings": {"usd_sha256": _digest(usd.read_bytes()), "bundle_file_sha256": _digest(bundle_raw), "profile_file_sha256": _digest(profile_raw)},
            "physics_steps": profile["initial_settle_steps"] + profile["target_steps"],
            "state_teleports_after_initialization": 0,
            "target": hover,
            "final": final,
            "maximum_final_joint_error_rad": max_error,
            "threshold_rad": profile["maximum_final_joint_error_rad"],
            "trace": trace,
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": ["gravity_disabled", "provisional_mass_inertia_and_drive_parameters", "no_collision_or_contact_geometry", "not_physical_timing_torque_or_safety_evidence"],
        }
        result["receipt_sha256"] = _digest(_canonical(result))
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({"status": result["status"], "receipt_sha256": result["receipt_sha256"]}, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if passed else 2
    except BaseException as exc:
        args.status_output.write_text(json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
