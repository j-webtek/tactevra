"""Overlay an actual ModelMotionBatchV2 on the governed RC03 Isaac scene.

The probe checks command order, repeated targets, source identities, and each
proposal's uncertainty disk against the simulation-only nominal key safe
region.  It authors visualization geometry but never changes the robot
articulation, steps physics, encodes a controller command, or accesses hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA = "tactevra.isaac_sim_model_motion_overlay.v1"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def assess_batch_against_nominal_regions(batch: Any, catalog: Any) -> dict[str, Any]:
    """Return a deterministic geometry assessment with no simulator imports."""
    radius = batch.uncertainty.error_bound_mm
    unique: dict[str, tuple[Any, Any]] = {}
    for proposal in batch.proposals:
        unique.setdefault(
            proposal.target_id,
            (catalog.resolve(batch.device.value, proposal.target_id), proposal.target),
        )
    if len(unique) < 2:
        raise ValueError("at least two unique targets are required to infer fixture placement")
    nominal_x = sum(item[0].center.x for item in unique.values()) / len(unique)
    nominal_y = sum(item[0].center.y for item in unique.values()) / len(unique)
    placed_x = sum(item[1].x for item in unique.values()) / len(unique)
    placed_y = sum(item[1].y for item in unique.values()) / len(unique)
    dot = cross = 0.0
    for region, target in unique.values():
        nx, ny = region.center.x - nominal_x, region.center.y - nominal_y
        px, py = target.x - placed_x, target.y - placed_y
        dot += nx * px + ny * py
        cross += nx * py - ny * px
    yaw = math.atan2(cross, dot)
    cosine, sine = math.cos(yaw), math.sin(yaw)
    tx = placed_x - (cosine * nominal_x - sine * nominal_y)
    ty = placed_y - (sine * nominal_x + cosine * nominal_y)
    residuals = []
    for region, target in unique.values():
        expected_x = cosine * region.center.x - sine * region.center.y + tx
        expected_y = sine * region.center.x + cosine * region.center.y + ty
        residuals.append(math.hypot(target.x - expected_x, target.y - expected_y))
    actions = []
    for proposal in batch.proposals:
        region = catalog.resolve(batch.device.value, proposal.target_id)
        target = proposal.target
        # Evaluate in the nominal key-local axes after undoing the inferred
        # rigid placement. This keeps displacement/yaw separate from accuracy.
        dx, dy = target.x - tx, target.y - ty
        local_x = cosine * dx + sine * dy
        local_y = -sine * dx + cosine * dy
        margins = {
            "left": local_x - (region.center.x - region.half_extent_x_mm),
            "right": (region.center.x + region.half_extent_x_mm) - local_x,
            "front": local_y - (region.center.y - region.half_extent_y_mm),
            "rear": (region.center.y + region.half_extent_y_mm) - local_y,
        }
        center_inside = min(margins.values()) >= 0.0
        uncertainty_fits = min(margins.values()) >= radius
        actions.append({
            "action_index": proposal.action_index,
            "target_id": proposal.target_id,
            "proposal_sha256": proposal.proposal_sha256,
            "proposal_center_board_mm": [target.x, target.y, target.z],
            "nominal_center_board_mm": [
                region.center.x, region.center.y, region.center.z,
            ],
            "placed_safe_region": {
                "center_board_mm": [target.x, target.y, region.center.z],
                "half_extent_mm": [region.half_extent_x_mm, region.half_extent_y_mm],
                "yaw_rad": yaw,
                "source": "RIGID_FIT_FROM_SYNTHETIC_BATCH_TARGETS",
            },
            "proposal_center_inside_inferred_placed_safe_region": center_inside,
            "uncertainty_disk_fits_inferred_placed_safe_region": uncertainty_fits,
            "signed_edge_margins_mm": margins,
        })
    ordered = [item["target_id"] for item in actions]
    repeats = [
        index for index in range(1, len(ordered))
        if ordered[index] == ordered[index - 1]
    ]
    all_centers_inside = all(
        item["proposal_center_inside_inferred_placed_safe_region"] for item in actions
    )
    all_disks_fit = all(
        item["uncertainty_disk_fits_inferred_placed_safe_region"] for item in actions
    )
    return {
        "ordered_target_ids": ordered,
        "adjacent_repeat_action_indexes": repeats,
        "action_count": len(actions),
        "uncertainty_bound_type": batch.uncertainty.bound_type.value,
        "uncertainty_error_bound_mm": radius,
        "inferred_synthetic_placement": {
            "translation_board_xy_mm": [tx, ty],
            "yaw_rad": yaw,
            "unique_target_count": len(unique),
            "maximum_fit_residual_mm": max(residuals),
            "runtime_calibration": False,
        },
        "all_proposal_centers_inside_inferred_placed_safe_regions": all_centers_inside,
        "all_uncertainty_disks_fit_inferred_placed_safe_regions": all_disks_fit,
        "actions": actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scene-usd", type=Path, required=True)
    parser.add_argument("--scene-receipt", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--batch-metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        workspace = args.workspace.resolve(strict=True)
        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.models import decode_model_motion_batch_v2_json
        from rocell.targets.static_nominal import (
            GEOMETRY_SOURCE_SHA256,
            load_static_nominal_target_catalog,
        )

        scene_usd = args.scene_usd.resolve(strict=True)
        scene_receipt_path = args.scene_receipt.resolve(strict=True)
        batch_path = args.batch.resolve(strict=True)
        metadata_path = args.batch_metadata.resolve(strict=True)
        output_dir = args.output_dir.resolve()
        if output_dir.exists():
            if any(output_dir.iterdir()):
                raise ValueError("external output directory must be empty")
        else:
            output_dir.mkdir(parents=True)

        scene_bytes = scene_usd.read_bytes()
        scene_receipt_bytes = scene_receipt_path.read_bytes()
        batch_bytes = batch_path.read_bytes()
        metadata_bytes = metadata_path.read_bytes()
        scene_receipt = json.loads(scene_receipt_bytes)
        metadata = json.loads(metadata_bytes)
        batch = decode_model_motion_batch_v2_json(batch_bytes)
        catalog = load_static_nominal_target_catalog(workspace)

        if scene_receipt["schema"] != "tactevra.isaac_sim_rc03_scene.v1":
            raise ValueError("scene receipt has the wrong schema")
        expected_scene_file = scene_receipt["external_files"][0]
        if expected_scene_file["sha256"] != _digest(scene_bytes):
            raise ValueError("scene USD differs from its retained receipt")
        if scene_receipt["source_bindings"]["nominal_target_profiles_sha256"] \
                != GEOMETRY_SOURCE_SHA256:
            raise ValueError("scene and batch do not share the governed target source")
        if batch.geometry.target_catalog_sha256 != GEOMETRY_SOURCE_SHA256:
            raise ValueError("batch target catalog differs from the governed target source")
        if metadata.get("batch_file_sha256") != _digest(batch_bytes):
            raise ValueError("batch metadata does not bind the batch bytes")
        requested_order = metadata.get("requested_target_order")
        observed_order = [item.target_id for item in batch.proposals]
        if requested_order != observed_order:
            raise ValueError("batch changed requested target order or repetitions")
        if metadata.get("scope") != "SYNTHETIC_CONTRACT_FIXTURE_ONLY":
            raise ValueError("batch metadata scope is not synthetic-only")

        assessment = assess_batch_against_nominal_regions(batch, catalog)

        from isaacsim import SimulationApp
        app = SimulationApp({"headless": True, "multi_gpu": False})
        from pxr import Gf, Sdf, Usd, UsdGeom

        source_stage = Usd.Stage.Open(str(scene_usd))
        if source_stage is None:
            raise RuntimeError("governed RC03 stage could not be opened")
        output_path = output_dir / "rc03_model_motion_overlay.usda"
        if not source_stage.GetRootLayer().Export(str(output_path)):
            raise RuntimeError("RC03 stage export failed")
        stage = Usd.Stage.Open(str(output_path))
        root_path = "/RC03/CommandRehearsal"
        UsdGeom.Xform.Define(stage, root_path)
        for action in assessment["actions"]:
            index = action["action_index"]
            target_id = action["target_id"]
            path = f"{root_path}/action_{index:03d}_{_safe(target_id)}"
            root = UsdGeom.Xform.Define(stage, path)
            root.GetPrim().CreateAttribute(
                "tactevra:actionIndex", Sdf.ValueTypeNames.Int
            ).Set(index)
            root.GetPrim().CreateAttribute(
                "tactevra:targetId", Sdf.ValueTypeNames.String
            ).Set(target_id)
            x, y, z = action["proposal_center_board_mm"]
            marker = UsdGeom.Sphere.Define(stage, f"{path}/ProposalCenter")
            marker.GetRadiusAttr().Set(0.0015)
            UsdGeom.Xformable(marker).AddTranslateOp().Set(
                Gf.Vec3d(x / 1000.0, y / 1000.0, z / 1000.0)
            )
            disk = UsdGeom.Cylinder.Define(stage, f"{path}/UncertaintyDisk")
            disk.GetRadiusAttr().Set(assessment["uncertainty_error_bound_mm"] / 1000.0)
            disk.GetHeightAttr().Set(0.0002)
            UsdGeom.Xformable(disk).AddTranslateOp().Set(
                Gf.Vec3d(x / 1000.0, y / 1000.0, z / 1000.0)
            )
            placed_region = action["placed_safe_region"]
            half_x, half_y = placed_region["half_extent_mm"]
            safe = UsdGeom.Cube.Define(stage, f"{path}/NominalSafeRegion")
            safe.GetSizeAttr().Set(1.0)
            safe_xform = UsdGeom.Xformable(safe)
            safe_xform.AddTranslateOp().Set(Gf.Vec3d(
                placed_region["center_board_mm"][0] / 1000.0,
                placed_region["center_board_mm"][1] / 1000.0,
                z / 1000.0,
            ))
            safe_xform.AddRotateZOp().Set(math.degrees(placed_region["yaw_rad"]))
            safe_xform.AddScaleOp().Set(Gf.Vec3d(
                2.0 * half_x / 1000.0,
                2.0 * half_y / 1000.0,
                0.0001,
            ))
        stage.GetRootLayer().Save()

        reopened = Usd.Stage.Open(str(output_path))
        if reopened is None:
            raise RuntimeError("overlay stage could not be reopened")
        authored = []
        for action in assessment["actions"]:
            path = (
                f"{root_path}/action_{action['action_index']:03d}_"
                f"{_safe(action['target_id'])}"
            )
            for suffix in ("ProposalCenter", "UncertaintyDisk", "NominalSafeRegion"):
                prim_path = f"{path}/{suffix}"
                if not reopened.GetPrimAtPath(prim_path).IsValid():
                    raise RuntimeError(f"overlay prim is missing: {prim_path}")
                authored.append(prim_path)

        output_bytes = output_path.read_bytes()
        if assessment["inferred_synthetic_placement"]["maximum_fit_residual_mm"] > 1e-6:
            status = "BLOCKED_BATCH_TARGETS_DO_NOT_SHARE_RIGID_PLACEMENT"
        elif not assessment["all_proposal_centers_inside_inferred_placed_safe_regions"]:
            status = "BLOCKED_PROPOSAL_CENTERS_MISS_INFERRED_SAFE_REGIONS"
        elif not assessment["all_uncertainty_disks_fit_inferred_placed_safe_regions"]:
            status = "BLOCKED_UNCERTAINTY_CROSSES_INFERRED_SAFE_REGIONS"
        else:
            status = "READY_FOR_ZERO_WRITE_JOINT_SCHEDULE_REPLAY"
        receipt: dict[str, Any] = {
            "schema": SCHEMA,
            "status": status,
            "evidence_class": "SYNTHETIC_COMMAND_SCENE_OVERLAY_ONLY",
            "source_bindings": {
                "scene_usd_sha256": _digest(scene_bytes),
                "scene_receipt_file_sha256": _digest(scene_receipt_bytes),
                "scene_receipt_sha256": scene_receipt["receipt_sha256"],
                "batch_file_sha256": _digest(batch_bytes),
                "batch_sha256": batch.batch_sha256,
                "batch_metadata_sha256": _digest(metadata_bytes),
                "nominal_target_geometry_source_sha256": GEOMETRY_SOURCE_SHA256,
                "static_target_catalog_sha256": catalog.content_sha256,
            },
            "batch_scope": metadata["scope"],
            "assessment": assessment,
            "authored_prim_paths": authored,
            "external_files": [{
                "path": output_path.relative_to(output_dir).as_posix(),
                "size_bytes": len(output_bytes),
                "sha256": _digest(output_bytes),
            }],
            "articulation_positions_changed": 0,
            "physics_steps": 0,
            "controller_commands": [],
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "hardware_access": False,
            "physical_authority": False,
            "limitations": [
                "The batch is a synthetic contract fixture, not deployment-qualified perception.",
                "Nominal key regions are design-time simulation geometry, not measured installed safe regions.",
                "The overlay visualizes proposals and uncertainty; it does not replay a joint schedule.",
                "No physics contact, collision clearance, controller encoding, or task effect was evaluated.",
            ],
            "next_dependency": (
                "Replay a source-bound zero-write joint schedule from the arm typing pipeline "
                "against this exact scene and compare simulated TCP contact to ordered targets."
            ),
        }
        receipt["receipt_sha256"] = _digest(_canonical(receipt))
        args.receipt.write_bytes(
            json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        status_doc = {
            "schema": f"{SCHEMA}.status",
            "status": status,
            "receipt_sha256": receipt["receipt_sha256"],
            "hardware_writes": 0,
            "physical_movements": 0,
        }
        args.status_output.write_bytes(
            json.dumps(status_doc, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        print(json.dumps(status_doc, sort_keys=True))
        return 0
    except Exception as exc:
        failure = {
            "schema": f"{SCHEMA}.status",
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "hardware_writes": 0,
            "physical_movements": 0,
        }
        args.status_output.write_bytes(
            json.dumps(failure, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
