"""Bind official RoArm link meshes without admitting collision geometry.

The probe reads immutable blobs from the pinned Waveshare ``roarm_ws`` Git
commit.  It verifies the Xacro's visual/collision mesh references and records
mesh identity and topology facts.  It does not align the meshes to the STEP
assembly, create collision shapes, start Isaac Sim, or grant physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


UPSTREAM_COMMIT = "40dbd84b553695212fab713e8465f817ba95454d"
UPSTREAM_TREE_OID_SHA1 = "3a1d24388e15b318ba0c5305a94b5140b5b239bd"
XACRO_PATH = "src/roarm_main/roarm_description/urdf/roarm_m3/roarm_m3.xacro"
MESH_DIRECTORY = "src/roarm_main/roarm_description/meshes/roarm_m3"
EXPECTED_XACRO_SHA256 = "b6333849d0e377008eee0a87a5b8cdcf44f7a73edf3d7600e95506a023a234b6"
LINKS = ("base_link", "link1", "link2", "link3", "link4", "link5", "gripper_link")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return digest_bytes(encoded)


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
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)

    try:
        upstream_repo = args.upstream_repo.resolve(strict=True)
        commit = str(_git(upstream_repo, "rev-parse", UPSTREAM_COMMIT)).strip()
        tree = str(_git(upstream_repo, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}"))
        tree = tree.strip()
        if commit != UPSTREAM_COMMIT or tree != UPSTREAM_TREE_OID_SHA1:
            raise ValueError("upstream Git object identity mismatch")

        xacro_bytes = _blob(upstream_repo, XACRO_PATH)
        if digest_bytes(xacro_bytes) != EXPECTED_XACRO_SHA256:
            raise ValueError("upstream Xacro blob hash mismatch")

        root = ET.fromstring(xacro_bytes)
        references: dict[str, dict[str, object]] = {}
        for link_name in LINKS:
            link = root.find(f"./link[@name='{link_name}']")
            if link is None:
                raise RuntimeError(f"upstream Xacro is missing {link_name!r}")
            roles: dict[str, dict[str, object]] = {}
            for role in ("visual", "collision"):
                mesh = link.find(f"{role}/geometry/mesh")
                origin = link.find(f"{role}/origin")
                if mesh is None or origin is None:
                    raise RuntimeError(f"{link_name} lacks a complete {role} mesh binding")
                roles[role] = {
                    "filename": mesh.attrib["filename"],
                    "basename": Path(mesh.attrib["filename"]).name,
                    "scale": _triplet(mesh.attrib.get("scale", "1 1 1")),
                    "origin_xyz": _triplet(origin.attrib["xyz"]),
                    "origin_rpy": _triplet(origin.attrib["rpy"]),
                }
            if roles["visual"] != roles["collision"]:
                raise RuntimeError(f"{link_name} visual/collision mesh bindings differ")
            if roles["visual"]["scale"] != [0.001, 0.001, 0.001]:
                raise RuntimeError(f"{link_name} has unexpected mesh scale")
            if roles["visual"]["origin_xyz"] != [0.0, 0.0, 0.0]:
                raise RuntimeError(f"{link_name} has nonzero mesh origin")
            if roles["visual"]["origin_rpy"] != [0.0, 0.0, 0.0]:
                raise RuntimeError(f"{link_name} has nonzero mesh rotation")
            references[link_name] = roles["visual"]

        import numpy as np
        import trimesh

        mesh_rows: list[dict[str, object]] = []
        for link_name in LINKS:
            blob_path = f"{MESH_DIRECTORY}/{references[link_name]['basename']}"
            mesh_bytes = _blob(upstream_repo, blob_path)
            mesh = trimesh.load_mesh(io.BytesIO(mesh_bytes), file_type="stl", process=True)
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
                "local_bounds_source_units": np.asarray(mesh.bounds).round(6).tolist(),
            })

        listed_paths = str(
            _git(upstream_repo, "ls-tree", "-r", "--name-only", UPSTREAM_COMMIT, MESH_DIRECTORY)
        ).splitlines()
        referenced_paths = {str(row["git_path"]) for row in mesh_rows}
        unreferenced = sorted(set(listed_paths) - referenced_paths)
        blockers = [
            "RAW_VISUAL_TRIANGLE_MESHES_ARE_NOT_REDUCED_COLLISION_SHAPES",
            "LINK1_AND_LINK5_MESHES_ARE_NOT_WATERTIGHT",
            "GRIPPER_LEFT_MESH_IS_UNREFERENCED_BY_XACRO",
            "MESH_TO_GOVERNED_ROBOT_FRAME_NOT_PROVEN_HERE",
            "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
            "TOOL_GEOMETRY_MISSING",
            "CAMERA_SUPPORT_GEOMETRY_MISSING",
            "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_upstream_link_mesh_binding.v1",
            "evidence_class": "UPSTREAM_LINK_MESH_BINDING_ONLY",
            "source_bindings": {
                "upstream_repository": "https://github.com/waveshareteam/roarm_ws",
                "upstream_commit": UPSTREAM_COMMIT,
                "upstream_tree_oid_sha1": tree,
                "xacro_git_path": XACRO_PATH,
                "xacro_sha256": digest_bytes(xacro_bytes),
            },
            "xacro_binding": {
                "link_count": len(LINKS),
                "visual_and_collision_references_identical": True,
                "mesh_scale": [0.001, 0.001, 0.001],
                "mesh_origin_xyz": [0.0, 0.0, 0.0],
                "mesh_origin_rpy": [0.0, 0.0, 0.0],
            },
            "mesh_inventory": mesh_rows,
            "mesh_totals": {
                "referenced_mesh_count": len(mesh_rows),
                "processed_vertex_count": sum(int(row["processed_vertex_count"]) for row in mesh_rows),
                "triangle_count": sum(int(row["triangle_count"]) for row in mesh_rows),
                "connected_body_count": sum(int(row["connected_body_count"]) for row in mesh_rows),
                "watertight_mesh_count": sum(bool(row["watertight"]) for row in mesh_rows),
                "non_watertight_mesh_count": sum(not bool(row["watertight"]) for row in mesh_rows),
                "unreferenced_mesh_paths": unreferenced,
            },
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
                "mesh_binding_does_not_prove_frame_alignment_or_surface_equivalence",
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
