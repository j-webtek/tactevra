"""Inspect pinned official link meshes without admitting collision geometry.

The probe reads immutable Git blobs at the governed upstream commit, verifies
the Xacro's visual/collision link bindings, transforms the referenced STL
meshes through the governed home pose, and compares their union envelope with
the independently converted official STEP assembly.  It does not install raw
triangle meshes as collision shapes or grant simulation or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


UPSTREAM_COMMIT = "40dbd84b553695212fab713e8465f817ba95454d"
UPSTREAM_TREE_OID_SHA1 = "3a1d24388e15b318ba0c5305a94b5140b5b239bd"
XACRO_PATH = "src/roarm_main/roarm_description/urdf/roarm_m3/roarm_m3.xacro"
MESH_DIRECTORY = "src/roarm_main/roarm_description/meshes/roarm_m3"
EXPECTED_XACRO_SHA256 = "b6333849d0e377008eee0a87a5b8cdcf44f7a73edf3d7600e95506a023a234b6"
EXPECTED_STEP_RECEIPT_SHA256 = "b51c20e34c3b3edfa4ba40b88d04299aa346803b43b12909dade7c41c44cf967"
EXPECTED_POSE_RECEIPT_SHA256 = "3817f28d9171ee3cb33d024f3f31e57495b02fb383ba60277953f6148ba00f3f"
EXPECTED_URDF_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
LINKS = ("base_link", "link1", "link2", "link3", "link4", "link5", "gripper_link")
JOINT_ORDER = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)
HOME = (0.0, 0.0, 1.5707963267948966, 0.0, 0.0, 0.0)
MAX_UNION_BOUND_RESIDUAL_MM = 2.0


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _git(repo: Path, *arguments: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=text,
        encoding="utf-8" if text else None,
    )
    return completed.stdout


def _blob(repo: Path, path: str) -> bytes:
    value = _git(repo, "show", f"{UPSTREAM_COMMIT}:{path}", text=False)
    assert isinstance(value, bytes)
    return value


def _triplet(value: str) -> list[float]:
    return [float(item) for item in value.split()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--step-receipt", type=Path, required=True)
    parser.add_argument("--pose-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        workspace = args.workspace.resolve(strict=True)
        upstream_repo = args.upstream_repo.resolve(strict=True)
        step_receipt_path = args.step_receipt.resolve(strict=True)
        pose_receipt_path = args.pose_receipt.resolve(strict=True)
        commit = str(_git(upstream_repo, "rev-parse", UPSTREAM_COMMIT)).strip()
        tree = str(_git(upstream_repo, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}")).strip()
        if commit != UPSTREAM_COMMIT or tree != UPSTREAM_TREE_OID_SHA1:
            raise ValueError("upstream Git object identity mismatch")

        xacro_bytes = _blob(upstream_repo, XACRO_PATH)
        if digest_bytes(xacro_bytes) != EXPECTED_XACRO_SHA256:
            raise ValueError("upstream Xacro blob hash mismatch")
        step_receipt = json.loads(step_receipt_path.read_text(encoding="utf-8"))
        pose_receipt = json.loads(pose_receipt_path.read_text(encoding="utf-8"))
        if step_receipt["receipt_sha256"] != EXPECTED_STEP_RECEIPT_SHA256:
            raise ValueError("STEP receipt identity mismatch")
        if pose_receipt["receipt_sha256"] != EXPECTED_POSE_RECEIPT_SHA256:
            raise ValueError("pose receipt identity mismatch")

        root = ET.fromstring(xacro_bytes)
        references = {}
        for link_name in LINKS:
            link = root.find(f"./link[@name='{link_name}']")
            if link is None:
                raise RuntimeError(f"upstream Xacro is missing {link_name!r}")
            role_rows = {}
            for role in ("visual", "collision"):
                element = link.find(role)
                mesh = link.find(f"{role}/geometry/mesh")
                origin = link.find(f"{role}/origin")
                if element is None or mesh is None or origin is None:
                    raise RuntimeError(f"{link_name} lacks a complete {role} mesh binding")
                role_rows[role] = {
                    "filename": mesh.attrib["filename"],
                    "basename": Path(mesh.attrib["filename"]).name,
                    "scale": _triplet(mesh.attrib.get("scale", "1 1 1")),
                    "origin_xyz": _triplet(origin.attrib["xyz"]),
                    "origin_rpy": _triplet(origin.attrib["rpy"]),
                }
            if role_rows["visual"] != role_rows["collision"]:
                raise RuntimeError(f"{link_name} visual/collision mesh bindings differ")
            if role_rows["visual"]["scale"] != [0.001, 0.001, 0.001]:
                raise RuntimeError(f"{link_name} has unexpected mesh scale")
            if role_rows["visual"]["origin_xyz"] != [0.0, 0.0, 0.0]:
                raise RuntimeError(f"{link_name} has nonzero mesh origin")
            if role_rows["visual"]["origin_rpy"] != [0.0, 0.0, 0.0]:
                raise RuntimeError(f"{link_name} has nonzero mesh rotation")
            references[link_name] = role_rows["visual"]

        sys.path.insert(0, str(workspace / "software/src"))
        import numpy as np
        import trimesh
        from rocell.geometry.urdf import JointPosition, UrdfModel

        urdf_path = workspace / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
        if digest_bytes(urdf_path.read_bytes()) != EXPECTED_URDF_SHA256:
            raise ValueError("governed URDF hash mismatch")
        model = UrdfModel.from_file(urdf_path)
        transforms = model.forward_kinematics({
            name: JointPosition.radians(value) for name, value in zip(JOINT_ORDER, HOME)
        })
        offset = np.asarray(pose_receipt["cad_T_urdf_world"]["translation_mm"], dtype=float)

        mesh_rows = []
        world_vertices = []
        for link_name in LINKS:
            basename = references[link_name]["basename"]
            blob_path = f"{MESH_DIRECTORY}/{basename}"
            mesh_bytes = _blob(upstream_repo, blob_path)
            mesh = trimesh.load_mesh(io.BytesIO(mesh_bytes), file_type="stl", process=True)
            transform = transforms[link_name]
            rotation = np.asarray(transform.rotation.matrix, dtype=float).reshape(3, 3)
            translation = np.asarray([
                transform.translation_mm.x,
                transform.translation_mm.y,
                transform.translation_mm.z,
            ]) + offset
            vertices = np.asarray(mesh.vertices) @ rotation.T + translation
            world_vertices.append(vertices)
            mesh_rows.append({
                "link_name": link_name,
                "git_path": blob_path,
                "sha256": digest_bytes(mesh_bytes),
                "byte_count": len(mesh_bytes),
                "processed_vertex_count": int(len(mesh.vertices)),
                "triangle_count": int(len(mesh.faces)),
                "connected_body_count": int(mesh.body_count),
                "watertight": bool(mesh.is_watertight),
                "winding_consistent": bool(mesh.is_winding_consistent),
                "is_volume": bool(mesh.is_volume),
                "local_bounds_mm": np.asarray(mesh.bounds).round(6).tolist(),
                "home_pose_bounds_cad_mm": [
                    vertices.min(axis=0).round(6).tolist(),
                    vertices.max(axis=0).round(6).tolist(),
                ],
            })

        union_vertices = np.vstack(world_vertices)
        mesh_union_bounds = [
            union_vertices.min(axis=0).round(6).tolist(),
            union_vertices.max(axis=0).round(6).tolist(),
        ]
        step_bounds = step_receipt["stage"]["assembly_bounds_mm"]
        step_bounds_list = [step_bounds["minimum"], step_bounds["maximum"]]
        residuals = [
            [
                round(mesh_union_bounds[bound][axis] - step_bounds_list[bound][axis], 6)
                for axis in range(3)
            ]
            for bound in range(2)
        ]
        max_residual = max(abs(value) for row in residuals for value in row)
        if max_residual > MAX_UNION_BOUND_RESIDUAL_MM:
            raise RuntimeError("official link-mesh union does not match the STEP assembly envelope")

        listed_mesh_paths = str(_git(
            upstream_repo, "ls-tree", "-r", "--name-only", UPSTREAM_COMMIT, MESH_DIRECTORY
        )).splitlines()
        unreferenced = sorted(set(listed_mesh_paths) - {row["git_path"] for row in mesh_rows})
        blockers = [
            "RAW_VISUAL_TRIANGLE_MESHES_ARE_NOT_REDUCED_COLLISION_SHAPES",
            "LINK1_AND_LINK5_MESHES_ARE_NOT_WATERTIGHT",
            "GRIPPER_LEFT_MESH_IS_UNREFERENCED_BY_XACRO",
            "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
            "TOOL_GEOMETRY_MISSING",
            "CAMERA_SUPPORT_GEOMETRY_MISSING",
            "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_upstream_link_meshes.v1",
            "evidence_class": "UPSTREAM_LINK_MESH_GROUPING_ONLY",
            "source_bindings": {
                "upstream_repository": "https://github.com/waveshareteam/roarm_ws",
                "upstream_commit": UPSTREAM_COMMIT,
                "upstream_tree_oid_sha1": tree,
                "xacro_git_path": XACRO_PATH,
                "xacro_sha256": digest_bytes(xacro_bytes),
                "governed_urdf_sha256": digest_bytes(urdf_path.read_bytes()),
                "step_receipt_file_sha256": digest_bytes(step_receipt_path.read_bytes()),
                "step_receipt_sha256": step_receipt["receipt_sha256"],
                "pose_receipt_file_sha256": digest_bytes(pose_receipt_path.read_bytes()),
                "pose_receipt_sha256": pose_receipt["receipt_sha256"],
            },
            "xacro_binding": {
                "link_count": len(LINKS),
                "visual_and_collision_references_identical": True,
                "mesh_scale": [0.001, 0.001, 0.001],
                "mesh_origin_xyz": [0.0, 0.0, 0.0],
                "mesh_origin_rpy": [0.0, 0.0, 0.0],
                "link_mesh_grouping_supported": True,
            },
            "mesh_inventory": mesh_rows,
            "mesh_totals": {
                "referenced_mesh_count": len(mesh_rows),
                "processed_vertex_count": sum(row["processed_vertex_count"] for row in mesh_rows),
                "triangle_count": sum(row["triangle_count"] for row in mesh_rows),
                "connected_body_count": sum(row["connected_body_count"] for row in mesh_rows),
                "watertight_mesh_count": sum(bool(row["watertight"]) for row in mesh_rows),
                "non_watertight_mesh_count": sum(not bool(row["watertight"]) for row in mesh_rows),
                "unreferenced_mesh_paths": unreferenced,
            },
            "home_pose_step_envelope_comparison": {
                "mesh_union_bounds_cad_mm": mesh_union_bounds,
                "step_assembly_bounds_cad_mm": step_bounds_list,
                "mesh_minus_step_bound_residuals_mm": residuals,
                "maximum_absolute_bound_residual_mm": round(max_residual, 6),
                "threshold_mm": MAX_UNION_BOUND_RESIDUAL_MM,
                "pass": True,
            },
            "step_product_mapping_admissible": False,
            "raw_mesh_collision_admissible": False,
            "reduced_collision_geometry_admissible": False,
            "clearance_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "global_envelope_agreement_does_not_prove_surface_or_link_local_equivalence",
                "xacro_reuses_high_detail_visual_meshes_as_collision_meshes",
                "no_convex_reduction_self_collision_differential_or_clearance_validation",
                "no_tool_camera_support_measured_placement_dynamics_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            "referenced_mesh_count": len(mesh_rows),
            "triangle_count": receipt["mesh_totals"]["triangle_count"],
            "non_watertight_mesh_count": receipt["mesh_totals"]["non_watertight_mesh_count"],
            "maximum_absolute_bound_residual_mm": round(max_residual, 6),
            "blockers": blockers,
        }, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
