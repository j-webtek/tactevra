"""Compose the governed nominal RC03 rigid scene as external USD evidence.

This probe creates simulator-only static geometry and a robot reference. It
does not accept trajectories, step physics, access hardware, or grant motion,
contact, collision, clearance, or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


EXPECTED_URDF_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
EXPECTED_DESIGN_REVISION = "RC03-INT-R1"
EXPECTED_ROBOT_JOINT_ORDER = [
    "base_link_to_link1", "link1_to_link2", "link2_to_link3",
    "link3_to_link4", "link4_to_link5", "link5_to_gripper_link",
]


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def _find_keyboard_target(profile: dict, target_id: str) -> tuple[float, float, float]:
    keyboard = profile["keyboard"]
    for row in keyboard["rows"]:
        if target_id in row["key_ids"]:
            index = row["key_ids"].index(target_id)
            first = row["first_center_xy_mm"]
            step = row["step_xy_mm"]
            local_x = first[0] + index * step[0]
            local_y = first[1] + index * step[1]
            origin = keyboard["device_origin_board_xy_mm"]
            return origin[0] + local_x, origin[1] + local_y, keyboard["target_plane_z_board_mm"]
    explicit = keyboard["explicit_targets"].get(target_id)
    if explicit is None:
        raise ValueError(f"keyboard target {target_id!r} is unavailable")
    origin = keyboard["device_origin_board_xy_mm"]
    return (
        origin[0] + explicit["center_xy_mm"][0],
        origin[1] + explicit["center_xy_mm"][1],
        keyboard["target_plane_z_board_mm"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rc03-root", type=Path, required=True)
    parser.add_argument("--robot-usd", type=Path, required=True)
    parser.add_argument("--robot-import-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        workspace = args.workspace.resolve(strict=True)
        software_src = workspace / "software/src"
        sys.path.insert(0, str(software_src))
        from rocell.simulation.scene import load_rc03_nominal_scene

        rc03_root = args.rc03_root.resolve(strict=True)
        robot_usd = args.robot_usd.resolve(strict=True)
        import_receipt_path = args.robot_import_receipt.resolve(strict=True)
        output_dir = args.output_dir.resolve()
        if output_dir.exists():
            if any(output_dir.iterdir()):
                raise ValueError("external output directory must be empty")
        else:
            output_dir.mkdir(parents=True)

        scene = load_rc03_nominal_scene(rc03_root)
        scene_document = scene.to_dict()
        if scene.design_revision != EXPECTED_DESIGN_REVISION:
            raise ValueError("RC03 scene revision is not governed")
        import_receipt_raw = import_receipt_path.read_bytes()
        import_receipt = json.loads(import_receipt_raw)
        robot_usd_sha256 = digest_bytes(robot_usd.read_bytes())
        if import_receipt["source"]["sha256"] != EXPECTED_URDF_SHA256:
            raise ValueError("robot import receipt does not bind the governed URDF")
        if import_receipt["external_files"][0]["sha256"] != robot_usd_sha256:
            raise ValueError("robot import receipt does not bind the supplied USD")
        if import_receipt["articulation_root_normalization"]["expected_live_dof_order"] != EXPECTED_ROBOT_JOINT_ORDER:
            raise ValueError("robot import receipt has the wrong live DOF order")

        target_profile_path = workspace / "software/config/nominal_target_profiles.json"
        hardware_profile_path = workspace / "software/config/simulation_hardware_profile.json"
        target_profile = _load_json(target_profile_path)
        hardware_profile = _load_json(hardware_profile_path)
        if target_profile["binding"]["design_revision"] != scene.design_revision:
            raise ValueError("target profile and RC03 scene revisions disagree")
        placement = hardware_profile["robot"]["nominal_board_T_robot_world"]
        if placement["state"] != "NOMINAL_ONLY_FROM_RC03_REACH_SCREENING":
            raise ValueError("robot placement state is not the governed nominal state")
        h_center_mm = _find_keyboard_target(target_profile, "H")

        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

        usd_path = output_dir / "rc03_nominal_rigid_scene.usda"
        stage = Usd.Stage.CreateNew(str(usd_path))
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        root = UsdGeom.Xform.Define(stage, "/RC03").GetPrim()
        stage.SetDefaultPrim(root)
        UsdPhysics.Scene.Define(stage, "/RC03/PhysicsScene")
        board_frame = UsdGeom.Xform.Define(stage, "/RC03/BoardFrame")

        authored_obstacles = []
        for obstacle in scene.obstacles:
            path = f"/RC03/BoardFrame/Obstacles/{_safe_name(obstacle.obstacle_id)}"
            cube = UsdGeom.Cube.Define(stage, path)
            cube.GetSizeAttr().Set(1.0)
            minimum = (obstacle.minimum.x, obstacle.minimum.y, obstacle.minimum.z)
            maximum = (obstacle.maximum.x, obstacle.maximum.y, obstacle.maximum.z)
            center_m = tuple((low + high) / 2000.0 for low, high in zip(minimum, maximum))
            size_m = tuple((high - low) / 1000.0 for low, high in zip(minimum, maximum))
            xform = UsdGeom.Xformable(cube)
            xform.AddTranslateOp().Set(Gf.Vec3d(*center_m))
            xform.AddScaleOp().Set(Gf.Vec3d(*size_m))
            UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
            cube.GetPrim().CreateAttribute("tactevra:source", Sdf.ValueTypeNames.String).Set(obstacle.source)
            cube.GetPrim().CreateAttribute("tactevra:kind", Sdf.ValueTypeNames.String).Set(obstacle.kind)
            cube.GetPrim().CreateAttribute("tactevra:conservativeProxy", Sdf.ValueTypeNames.Bool).Set(obstacle.conservative_proxy)
            authored_obstacles.append({
                "obstacle_id": obstacle.obstacle_id,
                "prim_path": path,
                "minimum_board_mm": list(minimum),
                "maximum_board_mm": list(maximum),
                "source": obstacle.source,
                "conservative_proxy": obstacle.conservative_proxy,
            })

        authored_fiducials = []
        for tag in scene.fiducials:
            path = f"/RC03/BoardFrame/Fiducials/{tag.name}"
            marker = UsdGeom.Cube.Define(stage, path)
            marker.GetSizeAttr().Set(1.0)
            xform = UsdGeom.Xformable(marker)
            xform.AddTranslateOp().Set(Gf.Vec3d(
                tag.center.x / 1000.0, tag.center.y / 1000.0, tag.center.z / 1000.0,
            ))
            xform.AddScaleOp().Set(Gf.Vec3d(
                tag.tile_edge_mm / 1000.0, tag.tile_edge_mm / 1000.0, 0.0002,
            ))
            marker.GetPrim().CreateAttribute("tactevra:tagId", Sdf.ValueTypeNames.Int).Set(tag.tag_id)
            authored_fiducials.append({"name": tag.name, "tag_id": tag.tag_id, "prim_path": path})

        h_path = "/RC03/BoardFrame/Targets/H"
        h_marker = UsdGeom.Xform.Define(stage, h_path)
        h_marker.AddTranslateOp().Set(Gf.Vec3d(*(value / 1000.0 for value in h_center_mm)))
        h_marker.GetPrim().CreateAttribute("tactevra:targetId", Sdf.ValueTypeNames.String).Set("H")
        h_marker.GetPrim().CreateAttribute("tactevra:nominalOnly", Sdf.ValueTypeNames.Bool).Set(True)

        robot_path = "/RC03/Robot"
        robot = UsdGeom.Xform.Define(stage, robot_path)
        robot.GetPrim().GetReferences().AddReference(str(robot_usd))
        rotation = placement["rotation_row_major"]
        translation = placement["translation_mm"]
        transform = Gf.Matrix4d(
            rotation[0], rotation[1], rotation[2], 0.0,
            rotation[3], rotation[4], rotation[5], 0.0,
            rotation[6], rotation[7], rotation[8], 0.0,
            translation[0] / 1000.0, translation[1] / 1000.0, translation[2] / 1000.0, 1.0,
        )
        robot.AddTransformOp().Set(transform)
        robot.GetPrim().CreateAttribute("tactevra:placementState", Sdf.ValueTypeNames.String).Set(placement["state"])
        stage.GetRootLayer().Save()

        stage_bytes = usd_path.read_bytes()
        verification_stage = Usd.Stage.Open(str(usd_path))
        if verification_stage is None:
            raise RuntimeError("generated RC03 stage could not be reopened")
        expected_collision_paths = {entry["prim_path"] for entry in authored_obstacles}
        observed_collision_paths = {
            str(prim.GetPath()) for prim in verification_stage.Traverse()
            if prim.HasAPI(UsdPhysics.CollisionAPI)
        }
        if observed_collision_paths != expected_collision_paths:
            raise RuntimeError("generated RC03 collision prim set is incomplete or altered")
        composed_joint_paths = [
            f"{robot_path}/Physics/{name}" for name in EXPECTED_ROBOT_JOINT_ORDER
        ]
        if any(not verification_stage.GetPrimAtPath(path).IsValid() for path in composed_joint_paths):
            raise RuntimeError("generated RC03 stage did not compose every robot joint")
        if not verification_stage.GetPrimAtPath(h_path).IsValid():
            raise RuntimeError("generated RC03 stage did not retain the H target marker")
        if UsdGeom.GetStageMetersPerUnit(verification_stage) != 1.0:
            raise RuntimeError("generated RC03 stage units changed")
        if UsdGeom.GetStageUpAxis(verification_stage) != UsdGeom.Tokens.z:
            raise RuntimeError("generated RC03 stage up axis changed")
        stage_validation = {
            "collision_prim_paths": sorted(observed_collision_paths),
            "composed_robot_joint_paths": composed_joint_paths,
            "composed_robot_joint_count": len(composed_joint_paths),
            "h_target_prim_valid": True,
            "physics_scene_prim": "/RC03/PhysicsScene",
        }
        files = [{
            "path": usd_path.relative_to(output_dir).as_posix(),
            "size_bytes": len(stage_bytes),
            "sha256": digest_bytes(stage_bytes),
        }]
        blockers = [
            "ARM_LINK_COLLISION_GEOMETRY_MISSING",
            "ARM_INERTIAL_PROPERTIES_INVALID",
            "CAMERA_SUPPORT_COLLISION_GEOMETRY_MISSING",
            "FIXTURE_SOLID_HEIGHTS_REPLACED_BY_35MM_PROXIES",
            "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
            "TOOL_COLLISION_GEOMETRY_MISSING",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_rc03_scene.v1",
            "evidence_class": "RIGID_SCENE_COMPOSITION_ONLY",
            "design_revision": scene.design_revision,
            "stage": {"meters_per_unit": 1.0, "up_axis": "Z", "default_prim": "/RC03"},
            "source_scene": scene_document,
            "source_bindings": {
                "nominal_target_profiles_sha256": digest_bytes(target_profile_path.read_bytes()),
                "simulation_hardware_profile_sha256": digest_bytes(hardware_profile_path.read_bytes()),
                "robot_import_receipt_file_sha256": digest_bytes(import_receipt_raw),
                "robot_import_receipt_sha256": import_receipt["receipt_sha256"],
                "robot_usd_sha256": robot_usd_sha256,
            },
            "robot_placement": placement,
            "robot_reference_prim": robot_path,
            "stage_validation": stage_validation,
            "obstacles": authored_obstacles,
            "fiducials": authored_fiducials,
            "nominal_h_target": {"prim_path": h_path, "center_board_mm": list(h_center_mm)},
            "external_files": files,
            "external_files_manifest_sha256": canonical_sha256(files),
            "collision_query_admissible": False,
            "hover_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "nominal_unmeasured_rc03_geometry",
                "static_rigid_envelopes_only",
                "no_arm_link_or_tool_collision_shapes",
                "no_dynamics_or_trajectory_replay",
                "no_clearance_contact_render_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            "blockers": blockers,
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
