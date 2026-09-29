"""Import the pinned RoArm URDF into external USD and retain a compact map.

This NVIDIA-dependent WP1 probe writes generated USD only to the caller's
external output directory. It neither accepts a trajectory nor exposes robot
transport or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


EXPECTED_URDF_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
EXPECTED_MOVABLE_JOINTS = {
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
}
EXPECTED_LINKS = {
    "world", "base_link", "link1", "link2", "link3", "link4", "link5",
    "gripper_link", "hand_tcp",
}
EXPECTED_FIXED_JOINT_CHILDREN = {
    "world_to_base_link": "base_link",
    "link5_to_hand_tcp": "hand_tcp",
}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _driver_version() -> str:
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    versions = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    if len(versions) != 1:
        raise RuntimeError("nvidia-smi returned inconsistent driver versions")
    return versions.pop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()

    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        urdf = args.urdf.resolve(strict=True)
        urdf_sha256 = digest_bytes(urdf.read_bytes())
        if urdf_sha256 != EXPECTED_URDF_SHA256:
            raise ValueError("URDF SHA-256 does not match the governed projection")
        output_dir = args.output_dir.resolve()
        if output_dir.exists():
            if any(output_dir.iterdir()):
                raise ValueError("external output directory must be empty")
        else:
            output_dir.mkdir(parents=True)

        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig
        from pxr import Usd, UsdGeom

        import_config = {
            "merge_fixed_joints": False,
            "merge_mesh": False,
            "debug_mode": False,
            "collision_from_visuals": False,
            "collision_type": "Convex Hull",
            "allow_self_collision": False,
            "ros_package_paths": [],
            "robot_type": "Default",
            "fix_base": None,
            "link_density": None,
            "joint_drive_type": None,
            "joint_target_type": None,
            "override_joint_stiffness": None,
            "override_joint_damping": None,
            "run_asset_transformer": False,
            "run_multi_physics_conversion": False,
        }
        config = URDFImporterConfig(
            urdf_path=str(urdf),
            usd_path=str(output_dir),
            **import_config,
        )
        usd_path = Path(URDFImporter(config).import_urdf()).resolve(strict=True)
        if not usd_path.is_relative_to(output_dir):
            raise RuntimeError("importer wrote outside the governed output directory")

        stage = Usd.Stage.Open(str(usd_path))
        if stage is None:
            raise RuntimeError("generated USD stage could not be opened")
        default_prim = stage.GetDefaultPrim()
        prims = []
        joints = []
        links = []
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            type_name = prim.GetTypeName()
            prims.append({"path": path, "type": type_name})
            if type_name == "Xform" and "/Geometry/" in path:
                matrix = UsdGeom.Xformable(prim).GetLocalTransformation()
                links.append({
                    "name": prim.GetName(),
                    "path": path,
                    "local_transform": [
                        [float(matrix[row][column]) for column in range(4)]
                        for row in range(4)
                    ],
                })
            if "Joint" not in type_name:
                continue
            attributes = {
                attribute.GetName(): _json_value(attribute.Get())
                for attribute in prim.GetAttributes()
                if attribute.HasAuthoredValueOpinion()
            }
            relationships = {
                relationship.GetName(): sorted(str(target) for target in relationship.GetTargets())
                for relationship in prim.GetRelationships()
                if relationship.HasAuthoredTargets()
            }
            joints.append({
                "name": prim.GetName(),
                "path": path,
                "type": type_name,
                "attributes": attributes,
                "relationships": relationships,
            })
        imported_joint_names = {joint["name"] for joint in joints}
        if imported_joint_names != EXPECTED_MOVABLE_JOINTS:
            raise RuntimeError(
                f"imported movable-joint mismatch: missing={sorted(EXPECTED_MOVABLE_JOINTS - imported_joint_names)}, "
                f"extra={sorted(imported_joint_names - EXPECTED_MOVABLE_JOINTS)}"
            )
        imported_link_names = {link["name"] for link in links}
        if imported_link_names != EXPECTED_LINKS:
            raise RuntimeError(
                f"imported link mismatch: missing={sorted(EXPECTED_LINKS - imported_link_names)}, "
                f"extra={sorted(imported_link_names - EXPECTED_LINKS)}"
            )
        link_by_name = {link["name"]: link for link in links}
        fixed_joint_resolution = [
            {
                "source_joint": source_joint,
                "source_child_link": child_link,
                "representation": "COLLAPSED_TO_NESTED_XFORM",
                "imported_child_path": link_by_name[child_link]["path"],
                "imported_child_local_transform": link_by_name[child_link]["local_transform"],
            }
            for source_joint, child_link in sorted(EXPECTED_FIXED_JOINT_CHILDREN.items())
        ]
        files = []
        for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
            files.append({
                "path": path.relative_to(output_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": digest_bytes(path.read_bytes()),
            })
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_urdf_import.v1",
            "evidence_class": "KINEMATIC_IMPORT_ONLY",
            "source": {
                "path": "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf",
                "sha256": urdf_sha256,
                "upstream_commit": "40dbd84b553695212fab713e8465f817ba95454d",
            },
            "import_config": import_config,
            "import_config_sha256": canonical_sha256(import_config),
            "driver_version": _driver_version(),
            "default_prim": str(default_prim.GetPath()),
            "prims": prims,
            "links": sorted(links, key=lambda value: str(value["name"])),
            "joints": sorted(joints, key=lambda value: str(value["name"])),
            "fixed_joint_resolution": fixed_joint_resolution,
            "external_files": files,
            "external_files_manifest_sha256": canonical_sha256(files),
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "meshless_kinematic_projection",
                "zero_effort_and_velocity_placeholders",
                "no_inertial_or_dynamic_qualification",
                "no_fk_parity_result",
                "no_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.receipt.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.status_output.write_text(
            json.dumps({"status": "PASS", "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except BaseException as exc:
        args.status_output.write_text(
            json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        if app is not None:
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
