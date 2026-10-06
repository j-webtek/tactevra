"""Refine the link2 and gripper collision boxes without granting authority."""

from __future__ import annotations

import argparse
import copy
import io
import json
from pathlib import Path

from collision_differential_probe import UPSTREAM_COMMIT, _blob, canonical_sha256, digest_bytes


EXPECTED_BASE_REDUCTION_SHA256 = (
    "ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178"
)
TARGET_LINKS = ("link2", "gripper_link")
PADDING_MM = 2e-6


def _round(values, digits: int) -> list[float]:
    return [round(float(value), digits) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--base-reduction", type=Path, required=True)
    parser.add_argument(
        "--target-links",
        default=",".join(TARGET_LINKS),
        help="Comma-separated subset of link2,gripper_link",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np
        import trimesh

        upstream = args.upstream_repo.resolve(strict=True)
        mesh_path = args.mesh_receipt.resolve(strict=True)
        base_path = args.base_reduction.resolve(strict=True)
        mesh_receipt = json.loads(mesh_path.read_text(encoding="utf-8"))
        base = json.loads(base_path.read_text(encoding="utf-8"))
        targets = tuple(item.strip() for item in args.target_links.split(",") if item.strip())
        if not targets or len(set(targets)) != len(targets) or not set(targets) <= set(TARGET_LINKS):
            raise ValueError("target-links must be a unique nonempty subset of link2,gripper_link")
        if base["receipt_sha256"] != EXPECTED_BASE_REDUCTION_SHA256:
            raise ValueError("base reduction receipt identity mismatch")
        refined_links = copy.deepcopy(base["links"])
        inventory = {item["link_name"]: item for item in mesh_receipt["mesh_inventory"]}
        target_metrics = []
        for link in refined_links:
            name = link["link_name"]
            if name not in targets:
                continue
            source = inventory[name]
            payload = _blob(upstream, source["git_path"])
            if digest_bytes(payload) != source["sha256"]:
                raise ValueError(f"{name} mesh hash mismatch")
            mesh = trimesh.load_mesh(io.BytesIO(payload), file_type="stl", process=True)
            components = list(mesh.split(only_watertight=False))
            components.sort(key=lambda item: tuple(np.asarray(item.bounds).reshape(-1).tolist()))
            if len(components) != len(link["components"]):
                raise RuntimeError(f"{name} component count changed")
            ratios = []
            for row, component in zip(link["components"], components):
                to_box, extents = trimesh.bounds.oriented_bounds(
                    component, angle_digits=1, ordered=True
                )
                box_to_link = np.linalg.inv(to_box)
                center = np.round(box_to_link[:3, 3], 9)
                rotation = np.round(box_to_link[:3, :3], 12)
                half_extents = np.round(extents / 2.0 + PADDING_MM, 9)
                vertices = np.asarray(component.vertices, dtype=float)
                local = (vertices - center) @ rotation
                overflow = max(0.0, float((np.abs(local) - half_extents).max()))
                if overflow > 1e-9:
                    raise RuntimeError(f"serialized {name} OBB does not contain its vertices")
                old_volume = float(row["candidate_box_volume_mm3"])
                new_volume = float(np.prod(2.0 * half_extents))
                source_volume = row["source_absolute_volume_mm3"]
                ratio = new_volume / source_volume if source_volume else None
                row["candidate_primitive"] = {
                    "kind": "oriented_box",
                    "center_mm": _round(center, 9),
                    "half_extents_mm": _round(half_extents, 9),
                    "rotation_row_major": _round(rotation.reshape(-1), 12),
                }
                row["candidate_box_volume_mm3"] = round(new_volume, 6)
                row["box_to_source_volume_ratio"] = round(ratio, 6) if ratio else None
                row["maximum_vertex_overflow_mm"] = round(overflow, 12)
                row["refinement"] = "TRIMESH_ORIENTED_BOUNDS_ANGLE_DIGITS_1"
                if ratio:
                    ratios.append(ratio)
                target_metrics.append({
                    "link_name": name,
                    "component_index": row["component_index"],
                    "old_box_volume_mm3": round(old_volume, 6),
                    "new_box_volume_mm3": round(new_volume, 6),
                    "new_to_old_volume_ratio": round(new_volume / old_volume, 6),
                    "maximum_vertex_overflow_mm": round(overflow, 12),
                })
            link["partition_mode"] = "TARGETED_ORIENTED_BOX_PER_COMPONENT"
            link["maximum_watertight_volume_ratio"] = round(max(ratios), 6) if ratios else None
        all_ratios = [
            component["box_to_source_volume_ratio"]
            for link in refined_links for component in link["components"]
            if component["box_to_source_volume_ratio"] is not None
        ]
        blockers = [
            "JOINT_SPACE_REPLAY_REQUIRED",
            "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
            "NON_WATERTIGHT_SOURCE_COMPONENTS",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_targeted_obb_refinement.v1",
            "evidence_class": "TARGETED_ORIENTED_BOX_CANDIDATES_ONLY",
            "source_bindings": {
                "upstream_commit": UPSTREAM_COMMIT,
                "mesh_receipt_file_sha256": digest_bytes(mesh_path.read_bytes()),
                "mesh_receipt_sha256": mesh_receipt["receipt_sha256"],
                "base_reduction_file_sha256": digest_bytes(base_path.read_bytes()),
                "base_reduction_sha256": base["receipt_sha256"],
                "trimesh_version": trimesh.__version__,
            },
            "method": {
                "target_links": list(targets),
                "algorithm": "trimesh.bounds.oriented_bounds",
                "angle_digits": 1,
                "serialized_center_digits": 9,
                "serialized_rotation_digits": 12,
                "serialization_containment_padding_mm": PADDING_MM,
            },
            "target_metrics": target_metrics,
            "links": refined_links,
            "summary": {
                "link_count": len(refined_links),
                "candidate_primitive_count": sum(len(item["components"]) for item in refined_links),
                "refined_primitive_count": len(target_metrics),
                "maximum_vertex_overflow_mm": max(
                    component["maximum_vertex_overflow_mm"]
                    for link in refined_links for component in link["components"]
                ),
                "maximum_watertight_volume_ratio": round(max(all_ratios), 6),
                "median_watertight_volume_ratio": round(float(np.median(all_ratios)), 6),
            },
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
                "targeted_obb_reduction_has_not_passed_the_governed_joint_space_replay",
                "oriented_bounds_are_bound_to_the_recorded_trimesh_version",
                "no_pair_exclusions_profile_installation_or_collision_authority",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        args.status_output.write_bytes((json.dumps({
            "status": "PASS_WITH_BLOCKERS", "receipt_sha256": receipt["receipt_sha256"],
            **receipt["summary"], "blockers": blockers,
        }, sort_keys=True) + "\n").encode())
    except BaseException as exc:
        args.status_output.write_bytes((json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n").encode("utf-8"))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
