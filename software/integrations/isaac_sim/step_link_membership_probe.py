"""Inventory link-membership candidates in the pinned fixed-pose STEP assembly.

The STEP conversion has no reviewed joint or mate graph.  This probe therefore
produces candidate evidence only: it covers every direct assembly component,
measures each component against the governed home-pose link skeleton, and
identifies groups whose bounds cross joint origins.  It does not assign CAD
geometry to dynamic links or admit collision, clearance, or physical use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


EXPECTED_CAD_USD_SHA256 = "cfcd4e6170350d948de1976164665ddde99cfad457b72730f7ffcbdd119496d3"
EXPECTED_POSE_RECEIPT_SHA256 = "3817f28d9171ee3cb33d024f3f31e57495b02fb383ba60277953f6148ba00f3f"
PRODUCT_ID_ATTRIBUTE = "omni:hoops:metadata:__STEP:ProductID"
JOINT_ORDER = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)
HOME = (0.0, 0.0, math.pi / 2.0, 0.0, 0.0, 0.0)
CANDIDATE_MARGIN_MM = 10.0
JOINT_ORIGIN_PADDING_MM = 2.25


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _bounds(cache: object, prim: object) -> tuple[list[float], list[float]]:
    aligned = cache.ComputeWorldBound(prim).ComputeAlignedBox()
    return ([float(value) for value in aligned.GetMin()], [float(value) for value in aligned.GetMax()])


def _point_segment_distance(point: list[float], start: list[float], end: list[float]) -> float:
    delta = [end[index] - start[index] for index in range(3)]
    relative = [point[index] - start[index] for index in range(3)]
    denominator = sum(value * value for value in delta)
    if denominator == 0.0:
        return math.sqrt(sum(value * value for value in relative))
    fraction = max(0.0, min(1.0, sum(relative[i] * delta[i] for i in range(3)) / denominator))
    nearest = [start[index] + fraction * delta[index] for index in range(3)]
    return math.sqrt(sum((point[index] - nearest[index]) ** 2 for index in range(3)))


def _contains(point: list[float], minimum: list[float], maximum: list[float]) -> bool:
    return all(
        minimum[index] - JOINT_ORIGIN_PADDING_MM
        <= point[index]
        <= maximum[index] + JOINT_ORIGIN_PADDING_MM
        for index in range(3)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cad-usd", type=Path, required=True)
    parser.add_argument("--pose-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        workspace = args.workspace.resolve(strict=True)
        cad_usd = args.cad_usd.resolve(strict=True)
        pose_receipt_path = args.pose_receipt.resolve(strict=True)
        cad_sha256 = digest_bytes(cad_usd.read_bytes())
        if cad_sha256 != EXPECTED_CAD_USD_SHA256:
            raise ValueError("CAD USD hash mismatch")
        pose_receipt = json.loads(pose_receipt_path.read_text(encoding="utf-8"))
        if pose_receipt["receipt_sha256"] != EXPECTED_POSE_RECEIPT_SHA256:
            raise ValueError("pose receipt identity mismatch")
        if pose_receipt["source_bindings"]["cad_usd_sha256"] != cad_sha256:
            raise ValueError("pose receipt does not bind the CAD USD")
        if pose_receipt["selected_pose_hypothesis"] != "home":
            raise ValueError("pose receipt does not retain the home hypothesis")

        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.geometry.urdf import JointPosition, UrdfModel
        from pxr import Usd, UsdGeom

        urdf_path = workspace / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
        model = UrdfModel.from_file(urdf_path)
        transforms = model.forward_kinematics({
            name: JointPosition.radians(value) for name, value in zip(JOINT_ORDER, HOME)
        })
        offset = pose_receipt["cad_T_urdf_world"]["translation_mm"]

        def cad_origin(link_name: str) -> list[float]:
            translation = transforms[link_name].translation_mm
            return [
                translation.x + offset[0],
                translation.y + offset[1],
                translation.z + offset[2],
            ]

        origins = {
            link_name: cad_origin(link_name)
            for link_name in (
                "base_link", "link1", "link2", "link3", "link4", "link5",
                "gripper_link", "hand_tcp",
            )
        }
        stage = Usd.Stage.Open(str(cad_usd))
        if stage is None:
            raise RuntimeError("CAD USD could not be opened")
        default_prim = stage.GetDefaultPrim()
        assembly_children = list(default_prim.GetChildren())
        if len(assembly_children) != 1:
            raise RuntimeError("expected one converted assembly below the default prim")
        assembly = assembly_children[0]
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"], useExtentsHint=True)
        assembly_minimum, _ = _bounds(cache, assembly)
        base_floor = [origins["base_link"][0], origins["base_link"][1], assembly_minimum[2]]
        support_segments = {
            "base_link": [base_floor, origins["base_link"]],
            "link1": [origins["link1"], origins["link2"]],
            "link2": [origins["link2"], origins["link3"]],
            "link3": [origins["link3"], origins["link4"]],
            "link4": [origins["link4"], origins["link5"]],
            "link5": [origins["link5"], origins["hand_tcp"]],
            "gripper_link": [origins["gripper_link"], origins["hand_tcp"]],
        }
        joint_origins = {
            "base_link_to_link1": origins["link1"],
            "link1_to_link2": origins["link2"],
            "link2_to_link3": origins["link3"],
            "link3_to_link4": origins["link4"],
            "link4_to_link5": origins["link5"],
            "link5_to_gripper_link": origins["gripper_link"],
        }

        direct_components = list(assembly.GetChildren())
        all_meshes = [prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
        component_rows = []
        covered_mesh_paths: set[str] = set()
        for component in direct_components:
            attribute = component.GetAttribute(PRODUCT_ID_ATTRIBUTE)
            product_id = str(attribute.Get()) if attribute.IsValid() and attribute.Get() else None
            minimum, maximum = _bounds(cache, component)
            centroid = [(minimum[index] + maximum[index]) / 2.0 for index in range(3)]
            meshes = [prim for prim in Usd.PrimRange(component) if prim.IsA(UsdGeom.Mesh)]
            covered_mesh_paths.update(str(prim.GetPath()) for prim in meshes)
            ranked = sorted(
                (
                    {
                        "link_name": link_name,
                        "centroid_to_support_segment_mm": round(
                            _point_segment_distance(centroid, segment[0], segment[1]), 6
                        ),
                    }
                    for link_name, segment in support_segments.items()
                ),
                key=lambda item: (item["centroid_to_support_segment_mm"], item["link_name"]),
            )
            margin = ranked[1]["centroid_to_support_segment_mm"] - ranked[0][
                "centroid_to_support_segment_mm"
            ]
            crossing = [
                name for name, point in joint_origins.items() if _contains(point, minimum, maximum)
            ]
            reasons = []
            if margin <= CANDIDATE_MARGIN_MM:
                reasons.append("NEAREST_LINK_MARGIN_AT_OR_BELOW_THRESHOLD")
            if crossing:
                reasons.append("COMPONENT_BOUNDS_CROSS_GOVERNED_JOINT_ORIGIN")
            if ranked[0]["link_name"] in {"link5", "gripper_link"}:
                reasons.append("DISTAL_LINK_SUPPORT_SEGMENTS_OVERLAP_IN_FIXED_POSE")
            component_rows.append({
                "instance_path": str(component.GetPath()),
                "product_id": product_id,
                "mesh_count": len(meshes),
                "minimum_cad_mm": [round(value, 6) for value in minimum],
                "maximum_cad_mm": [round(value, 6) for value in maximum],
                "centroid_cad_mm": [round(value, 6) for value in centroid],
                "nearest_candidates": ranked[:2],
                "candidate_margin_mm": round(margin, 6),
                "crossed_joint_origins": crossing,
                "ambiguous": bool(reasons),
                "ambiguity_reasons": reasons,
                "reviewed_dynamic_link_assignment": None,
            })

        all_mesh_paths = {str(prim.GetPath()) for prim in all_meshes}
        if covered_mesh_paths != all_mesh_paths:
            raise RuntimeError("direct component partition does not cover every mesh exactly")
        ambiguous_count = sum(bool(item["ambiguous"]) for item in component_rows)
        crossing_count = sum(bool(item["crossed_joint_origins"]) for item in component_rows)
        blockers = [
            "FIXED_POSE_STEP_HAS_NO_REVIEWED_JOINT_OR_MATE_GRAPH",
            "BASE_LINK_AND_LINK1_REQUIRE_MOTION_SEPARATION_EVIDENCE",
            "DISTAL_LINK5_AND_GRIPPER_REQUIRE_MOTION_SEPARATION_EVIDENCE",
            "JOINT_CROSSING_COMPONENT_GROUPS_REQUIRE_LEAF_LEVEL_REVIEW",
            "COLLISION_REDUCTION_NOT_REVIEWED",
            "TOOL_GEOMETRY_MISSING",
            "CAMERA_SUPPORT_GEOMETRY_MISSING",
            "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_step_link_membership_candidates.v1",
            "evidence_class": "CAD_LINK_MEMBERSHIP_CANDIDATES_ONLY",
            "source_bindings": {
                "cad_usd_sha256": cad_sha256,
                "pose_receipt_file_sha256": digest_bytes(pose_receipt_path.read_bytes()),
                "pose_receipt_sha256": pose_receipt["receipt_sha256"],
                "urdf_sha256": digest_bytes(urdf_path.read_bytes()),
            },
            "method": {
                "pose": "home",
                "component_partition": "direct_children_of_converted_step_assembly",
                "candidate_metric": "component_aabb_centroid_to_governed_link_support_segment",
                "candidate_margin_threshold_mm": CANDIDATE_MARGIN_MM,
                "joint_origin_padding_mm": JOINT_ORIGIN_PADDING_MM,
                "support_segments_cad_mm": support_segments,
                "joint_origins_cad_mm": joint_origins,
            },
            "inventory": {
                "direct_component_count": len(direct_components),
                "covered_mesh_count": len(covered_mesh_paths),
                "stage_mesh_count": len(all_mesh_paths),
                "complete_mesh_partition": covered_mesh_paths == all_mesh_paths,
                "ambiguous_component_count": ambiguous_count,
                "joint_crossing_component_count": crossing_count,
                "unambiguous_candidate_count": len(component_rows) - ambiguous_count,
                "reviewed_assignment_count": 0,
            },
            "components": component_rows,
            "dynamic_link_assignment_admissible": False,
            "collision_geometry_admissible": False,
            "clearance_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "nearest_support_segment_is_a_candidate_heuristic_not_rigid_membership_proof",
                "single_fixed_pose_cannot_separate_components_that_move_together_at_that_pose",
                "direct_component_subtrees_can_contain_parts_on_both_sides_of_a_joint",
                "no_link_local_shapes_inertia_dynamics_clearance_contact_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            "direct_component_count": len(direct_components),
            "ambiguous_component_count": ambiguous_count,
            "joint_crossing_component_count": crossing_count,
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
