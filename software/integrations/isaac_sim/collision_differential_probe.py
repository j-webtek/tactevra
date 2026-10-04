"""Compare pinned raw link meshes with conservative box candidates offline."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys


UPSTREAM_COMMIT = "40dbd84b553695212fab713e8465f817ba95454d"
EXPECTED_MESH_RECEIPT_SHA256 = (
    "77b7c16e2d7c7a8ee0579b071d6a911516a8ba6d675188971e0c54e466b30954"
)
EXPECTED_REDUCTION_RECEIPT_SHA256 = (
    "e714a88c01b567f54b2e8c91b8f1144fcc35db38d2953dfe2c6f31e1d576adab"
)
EXPECTED_FCL_VERSION = "0.7.0.11"
EXPECTED_FCL_WHEEL_SHA256 = (
    "63c662c8ff30eeb78913624a4ac56209a6061248ed97066c3b744255d943299f"
)
JOINT_ORDER = (
    "base_link_to_link1", "link1_to_link2", "link2_to_link3",
    "link3_to_link4", "link4_to_link5", "link5_to_gripper_link",
)
POSES = {
    "zero": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "home": (0.0, 0.0, 1.5707963267948966, 0.0, 0.0, 0.0),
    "ready": (0.0, 0.0, 2.618, -1.0472, 0.0, 0.0),
}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _blob(repo: Path, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"{UPSTREAM_COMMIT}:{path}"],
        check=True, capture_output=True,
    ).stdout


def _matrix(transform, np):
    matrix = np.eye(4)
    matrix[:3, :3] = np.asarray(transform.rotation.matrix).reshape(3, 3)
    matrix[:3, 3] = [
        transform.translation_mm.x,
        transform.translation_mm.y,
        transform.translation_mm.z,
    ]
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--reduction-receipt", type=Path, required=True)
    parser.add_argument("--fcl-wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcl
        import numpy as np
        import trimesh

        if fcl.__version__ != EXPECTED_FCL_VERSION:
            raise ValueError("python-fcl version mismatch")
        workspace = args.workspace.resolve(strict=True)
        upstream = args.upstream_repo.resolve(strict=True)
        mesh_path = args.mesh_receipt.resolve(strict=True)
        reduction_path = args.reduction_receipt.resolve(strict=True)
        wheel_path = args.fcl_wheel.resolve(strict=True)
        if digest_bytes(wheel_path.read_bytes()) != EXPECTED_FCL_WHEEL_SHA256:
            raise ValueError("python-fcl wheel hash mismatch")
        mesh_receipt = json.loads(mesh_path.read_text(encoding="utf-8"))
        reduction = json.loads(reduction_path.read_text(encoding="utf-8"))
        if mesh_receipt["receipt_sha256"] != EXPECTED_MESH_RECEIPT_SHA256:
            raise ValueError("mesh receipt identity mismatch")
        if reduction["receipt_sha256"] != EXPECTED_REDUCTION_RECEIPT_SHA256:
            raise ValueError("reduction receipt identity mismatch")

        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.geometry.urdf import JointPosition, UrdfModel

        model = UrdfModel.from_file(
            workspace / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
        )
        link_order = [item["link_name"] for item in mesh_receipt["mesh_inventory"]]
        adjacent = {
            tuple(sorted(pair)) for pair in zip(link_order[:-1], link_order[1:])
        }
        local_meshes = {}
        for item in mesh_receipt["mesh_inventory"]:
            payload = _blob(upstream, item["git_path"])
            if digest_bytes(payload) != item["sha256"]:
                raise ValueError(f"{item['link_name']} mesh hash mismatch")
            local_meshes[item["link_name"]] = trimesh.load_mesh(
                io.BytesIO(payload), file_type="stl", process=True
            )
        box_rows = {item["link_name"]: item["components"] for item in reduction["links"]}

        pose_rows = []
        totals = {"pair_cases": 0, "agreement_collision": 0, "agreement_free": 0,
                  "candidate_false_positive": 0, "candidate_false_negative": 0}
        for pose_name, values in POSES.items():
            transforms = model.forward_kinematics({
                name: JointPosition.radians(value)
                for name, value in zip(JOINT_ORDER, values)
            })
            raw_managers = {}
            box_managers = {}
            for link_name in link_order:
                world = _matrix(transforms[link_name], np)
                raw = local_meshes[link_name].copy()
                raw.apply_transform(world)
                raw_manager = trimesh.collision.CollisionManager()
                raw_manager.add_object(link_name, raw)
                raw_managers[link_name] = raw_manager
                box_manager = trimesh.collision.CollisionManager()
                for index, component in enumerate(box_rows[link_name]):
                    primitive = component["candidate_primitive"]
                    local = np.eye(4)
                    local[:3, 3] = primitive["center_mm"]
                    box = trimesh.creation.box(
                        extents=2.0 * np.asarray(primitive["half_extents_mm"]),
                        transform=world @ local,
                    )
                    box_manager.add_object(f"{link_name}:{index}", box)
                box_managers[link_name] = box_manager

            pairs = []
            pose_counts = {key: 0 for key in totals if key != "pair_cases"}
            for first_index, first in enumerate(link_order):
                for second in link_order[first_index + 1:]:
                    raw_collision = bool(raw_managers[first].in_collision_other(raw_managers[second]))
                    box_collision = bool(box_managers[first].in_collision_other(box_managers[second]))
                    if raw_collision and box_collision:
                        outcome = "AGREEMENT_COLLISION"
                        key = "agreement_collision"
                    elif not raw_collision and not box_collision:
                        outcome = "AGREEMENT_FREE"
                        key = "agreement_free"
                    elif box_collision:
                        outcome = "CANDIDATE_FALSE_POSITIVE"
                        key = "candidate_false_positive"
                    else:
                        outcome = "CANDIDATE_FALSE_NEGATIVE"
                        key = "candidate_false_negative"
                    raw_distance = float(raw_managers[first].min_distance_other(raw_managers[second]))
                    box_distance = float(box_managers[first].min_distance_other(box_managers[second]))
                    pose_counts[key] += 1
                    totals[key] += 1
                    totals["pair_cases"] += 1
                    pairs.append({
                        "body_pair": [first, second],
                        "kinematically_adjacent": tuple(sorted((first, second))) in adjacent,
                        "raw_mesh_collision": raw_collision,
                        "candidate_box_collision": box_collision,
                        "raw_mesh_minimum_signed_distance_mm": round(raw_distance, 6),
                        "candidate_box_minimum_signed_distance_mm": round(box_distance, 6),
                        "outcome": outcome,
                    })
            pose_rows.append({
                "pose_name": pose_name,
                "joint_positions_rad": list(values),
                "counts": pose_counts,
                "pairs": pairs,
            })

        blockers = [
            "CANDIDATE_FALSE_POSITIVE_COLLISIONS_OBSERVED",
            "THREE_POSE_CORPUS_IS_NOT_WORKSPACE_COVERAGE",
            "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
            "NON_WATERTIGHT_RAW_MESHES",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_collision_differential.v1",
            "evidence_class": "OFFLINE_THREE_POSE_COLLISION_DIFFERENTIAL_ONLY",
            "source_bindings": {
                "upstream_commit": UPSTREAM_COMMIT,
                "mesh_receipt_file_sha256": digest_bytes(mesh_path.read_bytes()),
                "mesh_receipt_sha256": mesh_receipt["receipt_sha256"],
                "reduction_receipt_file_sha256": digest_bytes(reduction_path.read_bytes()),
                "reduction_receipt_sha256": reduction["receipt_sha256"],
                "python_fcl_version": fcl.__version__,
                "python_fcl_wheel_sha256": digest_bytes(wheel_path.read_bytes()),
                "trimesh_version": trimesh.__version__,
            },
            "method": {
                "collision_backend": "python-fcl via trimesh CollisionManager",
                "pair_scope": "ALL_21_UNORDERED_LINK_PAIRS",
                "pose_scope": list(POSES),
                "distance_unit": "mm",
                "distance_semantics": "FCL_SIGNED_DISTANCE_NONPOSITIVE_ON_COLLISION",
                "adjacent_pairs_are_measured_not_excluded": True,
            },
            "poses": pose_rows,
            "summary": totals,
            "candidate_profile_installable": False,
            "collision_query_admissible": False,
            "clearance_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "three_static_poses_do_not_cover_continuous_joint_space",
                "adjacent_contacts_are_reported_without_policy_exclusion",
                "raw_non_watertight_meshes_are_supported_by_fcl_but_not_repaired",
                "no_tool_camera_support_environment_clearance_or_contact_dynamics",
                "no_installed_profile_controller_hardware_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            **totals,
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
