"""Inspect the pinned official RoArm STEP assembly as zero-authority evidence.

The generated USD is an external CAD inspection artifact.  This probe does
not assign CAD components to moving URDF links, author collision shapes,
accept trajectories, step physics, or grant clearance or physical authority.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import zipfile


EXPECTED_ARCHIVE_SHA256 = "1e2111145276aac14e521f47990fc41de87e2e735623d115a39cc176c9762da2"
EXPECTED_ARCHIVE_URL = "https://files.waveshare.com/wiki/RoArm-M3/RoArm-M3_STEP_260310.zip"
EXPECTED_STEP_MEMBER = "RoArm-M3_STEP/RoArm-M3.step"
EXPECTED_STEP_SHA256 = "728eb52f0bdd32dc0b907c9bb983d3d0b8adf7a5ea945949785a6e496f5089ff"
EXPECTED_COMPONENTS = ("AL-BASE", "AL-SHOULDER", "AL-ELBOW-A", "AL-ELBOW-B")
PRODUCT_ID_ATTRIBUTE = "omni:hoops:metadata:__STEP:ProductID"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _aligned_bounds_mm(cache: object, prim: object) -> dict[str, list[float]]:
    aligned = cache.ComputeWorldBound(prim).ComputeAlignedBox()
    return {
        "minimum": [round(float(value), 6) for value in aligned.GetMin()],
        "maximum": [round(float(value), 6) for value in aligned.GetMax()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--step", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        archive = args.archive.resolve(strict=True)
        step = args.step.resolve(strict=True)
        archive_bytes = archive.read_bytes()
        step_bytes = step.read_bytes()
        if digest_bytes(archive_bytes) != EXPECTED_ARCHIVE_SHA256:
            raise ValueError("official STEP archive hash mismatch")
        if digest_bytes(step_bytes) != EXPECTED_STEP_SHA256:
            raise ValueError("extracted STEP hash mismatch")
        with zipfile.ZipFile(archive) as source_zip:
            members = [name for name in source_zip.namelist() if not name.endswith("/")]
            if members != [EXPECTED_STEP_MEMBER]:
                raise ValueError("official STEP archive member set changed")
            if source_zip.read(EXPECTED_STEP_MEMBER) != step_bytes:
                raise ValueError("extracted STEP does not equal the pinned archive member")

        output_dir = args.output_dir.resolve()
        if output_dir.exists():
            if any(output_dir.iterdir()):
                raise ValueError("external output directory must be empty")
        else:
            output_dir.mkdir(parents=True)

        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.kit.app

        manager = omni.kit.app.get_app().get_extension_manager()
        manager.set_extension_enabled_immediate("omni.kit.converter.hoops_core", True)
        for _ in range(20):
            app.update()
        import omni.converter.hoops
        from omni.kit.converter.hoops_core import HoopsOptions, get_instance
        from pxr import Usd, UsdGeom, UsdPhysics

        converter = get_instance()
        if converter is None:
            raise RuntimeError("HOOPS core converter is not loaded")
        options = HoopsOptions()
        options.instancingStyle = omni.converter.hoops.InstancingStyle.eNone
        options.compositionStyle = omni.converter.hoops.CompositionStyle.eNone
        options.filterStyle = omni.converter.hoops.FilterStyle.eOmit
        options.tessLOD = 1
        options.useMaterials = False
        options.convertMetadata = True
        options.convertPhysicsData = False
        converter_identity = options.creator
        option_receipt = {
            "accurate_surface_curvatures": True,
            "accurate_tessellation": False,
            "composition_style": "NONE",
            "convert_metadata": True,
            "convert_physics_data": False,
            "filter_style": "OMIT",
            "instancing_style": "NONE",
            "tessellation_lod": 1,
            "use_materials": False,
            "use_normals": True,
        }
        usd_path = output_dir / "roarm_m3_official.usda"

        async def convert() -> tuple[str, object]:
            return await converter.create_converter_task(
                str(step), str(usd_path), options.toArgs()
            )

        output_url, status = asyncio.run(convert())
        if status.error_code != 0 or not output_url:
            raise RuntimeError(f"STEP conversion failed: {status.error_code}: {status.error_msg}")
        if Path(output_url).resolve() != usd_path.resolve():
            raise RuntimeError("STEP converter returned an unexpected output path")

        stage = Usd.Stage.Open(str(usd_path))
        if stage is None:
            raise RuntimeError("converted STEP USD could not be reopened")
        default_prim = stage.GetDefaultPrim()
        if not default_prim.IsValid():
            raise RuntimeError("converted STEP USD has no default prim")
        meters_per_unit = UsdGeom.GetStageMetersPerUnit(stage)
        if meters_per_unit != 0.001:
            raise RuntimeError("converted STEP USD is not authored in millimetres")
        if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
            raise RuntimeError("converted STEP USD is not Z-up")

        cache = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), ["default", "render"],
            useExtentsHint=True,
        )
        product_prims: dict[str, list[object]] = {}
        prim_count = 0
        mesh_count = 0
        collision_prim_count = 0
        for prim in stage.Traverse():
            prim_count += 1
            if prim.IsA(UsdGeom.Mesh):
                mesh_count += 1
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                collision_prim_count += 1
            attribute = prim.GetAttribute(PRODUCT_ID_ATTRIBUTE)
            if attribute.IsValid():
                value = attribute.Get()
                if value:
                    product_prims.setdefault(str(value), []).append(prim)

        candidate_components = []
        for product_id in EXPECTED_COMPONENTS:
            matches = product_prims.get(product_id, [])
            if len(matches) != 1:
                raise RuntimeError(
                    f"expected exactly one {product_id!r} product, observed {len(matches)}"
                )
            prim = matches[0]
            candidate_components.append({
                "product_id": product_id,
                "prim_path": str(prim.GetPath()),
                "bounds_mm_in_cad_assembly_pose": _aligned_bounds_mm(cache, prim),
                "provenance": "upstream_step_assembly_component",
                "dynamic_link_assignment": None,
                "status": "INSPECTION_ONLY_UNASSIGNED_TO_DYNAMIC_LINK",
            })

        usd_bytes = usd_path.read_bytes()
        files = [{
            "path": usd_path.relative_to(output_dir).as_posix(),
            "size_bytes": len(usd_bytes),
            "sha256": digest_bytes(usd_bytes),
        }]
        blockers = [
            "CAD_ASSEMBLY_POSE_NOT_BOUND_TO_URDF_JOINT_STATE",
            "CAD_COMPONENTS_NOT_ASSIGNED_TO_DYNAMIC_LINKS",
            "COLLISION_REDUCTION_NOT_REVIEWED",
            "TOOL_GEOMETRY_MISSING",
            "CAMERA_SUPPORT_GEOMETRY_MISSING",
            "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_step_inspection.v1",
            "evidence_class": "PINNED_CAD_INSPECTION_ONLY",
            "source": {
                "archive_url": EXPECTED_ARCHIVE_URL,
                "archive_name": archive.name,
                "archive_sha256": digest_bytes(archive_bytes),
                "archive_size_bytes": len(archive_bytes),
                "step_member": EXPECTED_STEP_MEMBER,
                "step_sha256": digest_bytes(step_bytes),
                "step_size_bytes": len(step_bytes),
                "redistribution": "external_only_license_scope_unconfirmed",
            },
            "converter": {
                "identity": converter_identity,
                "extension_name": converter.get_ext_name(),
                "extension_version": converter.get_ext_version(),
                "options": option_receipt,
            },
            "stage": {
                "default_prim": str(default_prim.GetPath()),
                "meters_per_unit": meters_per_unit,
                "up_axis": "Z",
                "assembly_bounds_mm": _aligned_bounds_mm(cache, default_prim),
                "prim_count": prim_count,
                "mesh_count": mesh_count,
                "collision_prim_count": collision_prim_count,
                "named_product_count": sum(len(prims) for prims in product_prims.values()),
                "unique_product_id_count": len(product_prims),
            },
            "candidate_collision_seed_components": candidate_components,
            "external_files": files,
            "external_files_manifest_sha256": canonical_sha256(files),
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
                "cad_assembly_pose_is_not_a_governed_robot_joint_state",
                "selected_structural_components_are_incomplete_collision_seeds",
                "no_dynamic_link_local_transforms_or_reduced_shapes",
                "no_inertia_dynamics_trajectory_clearance_contact_or_render_claim",
                "generated_cad_asset_remains_external_due_to_unconfirmed_license_scope",
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
