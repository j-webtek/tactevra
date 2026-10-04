"""Test the pinned STEP assembly pose against governed URDF pose candidates.

This is a geometry-classification diagnostic.  It does not assign CAD product
groups to dynamic links, author collision shapes, accept trajectories, step
physics, or grant clearance or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


EXPECTED_CAD_USD_SHA256 = "cfcd4e6170350d948de1976164665ddde99cfad457b72730f7ffcbdd119496d3"
EXPECTED_STEP_RECEIPT_SHA256 = "b51c20e34c3b3edfa4ba40b88d04299aa346803b43b12909dade7c41c44cf967"
PRODUCT_ID_ATTRIBUTE = "omni:hoops:metadata:__STEP:ProductID"
JOINT_ORDER = (
    "base_link_to_link1", "link1_to_link2", "link2_to_link3",
    "link3_to_link4", "link4_to_link5", "link5_to_gripper_link",
)
WITNESSES = {
    "base_link": "ST3215",
    "link2": "AL-SHOULDER",
    "link3": "AL-ELBOW-A",
    "link4": "SCS215",
    "link5": "SCS215_1",
    "gripper_link": "ST3215_4",
}
POSES = {
    "zero": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "home": (0.0, 0.0, math.pi / 2.0, 0.0, 0.0, 0.0),
    "ready": (0.0, 0.0, 2.618, -1.0472, 0.0, 0.0),
}
MAX_SUPPORTED_RESIDUAL_MM = 2.25


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _bounds(cache: object, prim: object) -> tuple[list[float], list[float]]:
    aligned = cache.ComputeWorldBound(prim).ComputeAlignedBox()
    return ([float(value) for value in aligned.GetMin()], [float(value) for value in aligned.GetMax()])


def _point_to_aabb_distance(point: list[float], minimum: list[float], maximum: list[float]) -> float:
    outside = [max(minimum[i] - point[i], point[i] - maximum[i], 0.0) for i in range(3)]
    return math.sqrt(sum(value * value for value in outside))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cad-usd", type=Path, required=True)
    parser.add_argument("--step-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        workspace = args.workspace.resolve(strict=True)
        cad_usd = args.cad_usd.resolve(strict=True)
        step_receipt_path = args.step_receipt.resolve(strict=True)
        cad_sha256 = digest_bytes(cad_usd.read_bytes())
        if cad_sha256 != EXPECTED_CAD_USD_SHA256:
            raise ValueError("CAD USD hash mismatch")
        step_receipt = json.loads(step_receipt_path.read_text(encoding="utf-8"))
        if step_receipt["receipt_sha256"] != EXPECTED_STEP_RECEIPT_SHA256:
            raise ValueError("STEP inspection receipt identity mismatch")
        if step_receipt["external_files"][0]["sha256"] != cad_sha256:
            raise ValueError("STEP inspection receipt does not bind the CAD USD")

        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.geometry.urdf import JointPosition, UrdfModel
        from pxr import Usd, UsdGeom

        urdf_path = workspace / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
        model = UrdfModel.from_file(urdf_path)
        stage = Usd.Stage.Open(str(cad_usd))
        if stage is None:
            raise RuntimeError("CAD USD could not be opened")
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"], useExtentsHint=True)
        products: dict[str, list[object]] = {}
        for prim in stage.Traverse():
            attribute = prim.GetAttribute(PRODUCT_ID_ATTRIBUTE)
            if attribute.IsValid() and attribute.Get():
                products.setdefault(str(attribute.Get()), []).append(prim)

        required_products = set(WITNESSES.values()) | {"ST3215_1", "ST3215_2"}
        for product_id in sorted(required_products):
            if len(products.get(product_id, [])) != 1:
                raise RuntimeError(f"expected exactly one CAD product {product_id!r}")

        negative_shoulder_min, negative_shoulder_max = _bounds(cache, products["ST3215_1"][0])
        positive_shoulder_min, positive_shoulder_max = _bounds(cache, products["ST3215_2"][0])
        if negative_shoulder_max[1] >= positive_shoulder_min[1]:
            raise RuntimeError("shoulder servo pair no longer brackets the URDF center plane")
        assembly_minimum, _ = _bounds(cache, stage.GetDefaultPrim())
        x_centers = [
            (negative_shoulder_min[0] + negative_shoulder_max[0]) / 2.0,
            (positive_shoulder_min[0] + positive_shoulder_max[0]) / 2.0,
        ]
        cad_T_urdf_translation = [
            sum(x_centers) / 2.0,
            (negative_shoulder_max[1] + positive_shoulder_min[1]) / 2.0,
            assembly_minimum[2],
        ]
        anchor_derivation = {
            "x_mm": "mean X center of the ST3215_1/ST3215_2 shoulder-servo bounds",
            "y_mm": "midplane between the facing ST3215_1/ST3215_2 shoulder-servo bounds",
            "z_mm": "minimum Z of the complete CAD assembly bound",
        }

        witness_bounds = {}
        for link_name, product_id in WITNESSES.items():
            minimum, maximum = _bounds(cache, products[product_id][0])
            witness_bounds[link_name] = {
                "product_id": product_id,
                "prim_path": str(products[product_id][0].GetPath()),
                "minimum_cad_mm": [round(value, 6) for value in minimum],
                "maximum_cad_mm": [round(value, 6) for value in maximum],
            }

        candidates = []
        for pose_name, values in POSES.items():
            transforms = model.forward_kinematics({
                name: JointPosition.radians(value) for name, value in zip(JOINT_ORDER, values)
            })
            residuals = []
            for link_name, witness in witness_bounds.items():
                translation = transforms[link_name].translation_mm
                cad_point = [
                    translation.x + cad_T_urdf_translation[0],
                    translation.y + cad_T_urdf_translation[1],
                    translation.z + cad_T_urdf_translation[2],
                ]
                distance = _point_to_aabb_distance(
                    cad_point, witness["minimum_cad_mm"], witness["maximum_cad_mm"]
                )
                residuals.append({
                    "link_name": link_name,
                    "product_id": witness["product_id"],
                    "predicted_origin_cad_mm": [round(value, 6) for value in cad_point],
                    "distance_to_product_aabb_mm": round(distance, 6),
                })
            distances = [item["distance_to_product_aabb_mm"] for item in residuals]
            candidates.append({
                "pose_name": pose_name,
                "joint_positions_rad": list(values),
                "witness_residuals": residuals,
                "maximum_residual_mm": round(max(distances), 6),
                "rms_residual_mm": round(math.sqrt(sum(value * value for value in distances) / len(distances)), 6),
                "supported_witness_count": sum(value <= MAX_SUPPORTED_RESIDUAL_MM for value in distances),
            })

        ranked = sorted(candidates, key=lambda item: (item["maximum_residual_mm"], item["rms_residual_mm"]))
        winner = ranked[0]
        runner_up = ranked[1]
        supported = (
            winner["pose_name"] == "home"
            and winner["supported_witness_count"] == len(WITNESSES)
            and winner["maximum_residual_mm"] <= MAX_SUPPORTED_RESIDUAL_MM
            and runner_up["maximum_residual_mm"] > 100.0
        )
        if not supported:
            raise RuntimeError("official CAD assembly did not support the governed home-pose hypothesis")
        blockers = [
            "CAD_PRODUCT_GROUPS_NOT_ASSIGNED_TO_DYNAMIC_LINKS",
            "COLLISION_REDUCTION_NOT_REVIEWED",
            "TOOL_GEOMETRY_MISSING",
            "CAMERA_SUPPORT_GEOMETRY_MISSING",
            "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_step_pose_binding.v1",
            "evidence_class": "CAD_POSE_HYPOTHESIS_ONLY",
            "source_bindings": {
                "cad_usd_sha256": cad_sha256,
                "step_inspection_receipt_file_sha256": digest_bytes(step_receipt_path.read_bytes()),
                "step_inspection_receipt_sha256": step_receipt["receipt_sha256"],
                "urdf_sha256": digest_bytes(urdf_path.read_bytes()),
            },
            "cad_T_urdf_world": {
                "rotation_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                "translation_mm": [round(value, 6) for value in cad_T_urdf_translation],
                "derivation": anchor_derivation,
                "provenance": "derived_from_pinned_cad_bounds",
            },
            "maximum_supported_residual_mm": MAX_SUPPORTED_RESIDUAL_MM,
            "witness_bounds": witness_bounds,
            "candidates": candidates,
            "selected_pose_hypothesis": winner["pose_name"],
            "runner_up_pose": runner_up["pose_name"],
            "classification_margin_max_residual_mm": round(
                runner_up["maximum_residual_mm"] - winner["maximum_residual_mm"], 6
            ),
            "pose_hypothesis_supported": True,
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
                "aabb_witnesses_classify_pose_but_do_not_define_exact_joint_axes",
                "cad_product_membership_per_dynamic_link_remains_unreviewed",
                "no_reduced_collision_shapes_or_self_collision_validation",
                "no_inertia_dynamics_trajectory_clearance_contact_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
