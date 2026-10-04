"""Render the frozen residual-obstruction v3 campaign in Isaac Sim.

This runner creates fresh target-local 3D renders.  Truth segmentation and
depth are retained for admission only; model inputs are RGB JPEG files.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v3"
MANIFEST_SCHEMA = "tactevra.ai_residual_obstruction_v3_isaac_manifest.v1"
RESOLUTION = (96, 96)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def dynamic_root(scene_index: int) -> str:
    if scene_index < 0:
        raise ValueError("scene index must be nonnegative")
    return f"/World/SceneDynamic{scene_index:02d}"


def foreign_object_radii(width_mm: float, height_mm: float) -> tuple[float, float]:
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("target dimensions must be positive")
    return width_mm * 0.42, height_mm * 0.42


def camera_height_mm(width_mm: float, height_mm: float) -> float:
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("target dimensions must be positive")
    largest = max(width_mm, height_mm)
    if largest <= 14.0:
        return max(45.0, 82.0 * largest / 14.0)
    return max(82.0, 1.5 * largest)


def centered_tool_size(width_mm: float, height_mm: float) -> tuple[float, float]:
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("target dimensions must be positive")
    return width_mm * 0.55, height_mm


def edge_tool_geometry(width_mm: float, height_mm: float) -> tuple[float, float, float]:
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("target dimensions must be positive")
    return width_mm * 0.15, width_mm * 0.45, height_mm


def load_fixture(path: Path) -> tuple[dict[str, Any], bytes]:
    payload_bytes = path.resolve(strict=True).read_bytes()
    payload = json.loads(payload_bytes)
    if payload.get("schema") != FIXTURE_SCHEMA:
        raise ValueError("unsupported fixture")
    core = {key: value for key, value in payload.items() if key != "bundle_sha256"}
    if payload.get("bundle_sha256") != sha256_bytes(canonical(core)):
        raise ValueError("fixture canonical hash mismatch")
    if payload["images_generated"] is not False or payload["training_started"] is not False:
        raise ValueError("fixture was not frozen before generation")
    if payload["split_policy"]["evaluation_observation_count"] != 0:
        raise ValueError("evaluation must remain absent")
    if payload["render_admission"]["renderer"] != "ISAAC_SIM_3D":
        raise ValueError("fixture does not require Isaac 3D")
    return payload, payload_bytes


def _cube(stage: Any, path: str, center_mm: tuple[float, float, float],
          size_mm: tuple[float, float, float], color: tuple[float, float, float],
          label: str | None, Gf: Any, UsdGeom: Any, add_labels: Any) -> Any:
    cube = UsdGeom.Cube.Define(stage, path)
    cube.GetSizeAttr().Set(1.0)
    xform = UsdGeom.Xformable(cube)
    xform.AddTranslateOp().Set(Gf.Vec3d(*(value / 1000.0 for value in center_mm)))
    xform.AddScaleOp().Set(Gf.Vec3d(*(value / 1000.0 for value in size_mm)))
    cube.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    cube.CreateDisplayOpacityAttr([1.0])
    if label:
        add_labels(cube.GetPrim(), labels=[label], taxonomy="class")
    return cube


def _ellipsoid(stage: Any, path: str, center_mm: tuple[float, float, float],
               radii_mm: tuple[float, float], color: tuple[float, float, float],
               label: str, Gf: Any, UsdGeom: Any, add_labels: Any) -> Any:
    sphere = UsdGeom.Sphere.Define(stage, path)
    sphere.GetRadiusAttr().Set(1.0)
    xform = UsdGeom.Xformable(sphere)
    xform.AddTranslateOp().Set(
        Gf.Vec3d(*(value / 1000.0 for value in center_mm))
    )
    xform.AddScaleOp().Set(Gf.Vec3d(
        radii_mm[0] / 1000.0, radii_mm[1] / 1000.0, 0.004,
    ))
    sphere.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    add_labels(sphere.GetPrim(), labels=[label], taxonomy="class")
    return sphere


def _semantic_array(raw: Any, np: Any) -> tuple[Any, dict[str, Any]]:
    data = np.asarray(raw["data"] if isinstance(raw, dict) else raw)
    info = raw.get("info", {}) if isinstance(raw, dict) else {}
    if data.ndim == 3 and data.shape[-1] == 1:
        data = data[..., 0]
    if data.shape != (RESOLUTION[1], RESOLUTION[0]):
        raise RuntimeError(f"unexpected semantic shape {data.shape}")
    return data.astype(np.uint32), json.loads(json.dumps(info, default=str))


def _ids_for_label(info: dict[str, Any], label: str) -> set[int]:
    labels = info.get("idToLabels")
    if not isinstance(labels, dict):
        return set()
    return {
        int(raw_id) for raw_id, value in labels.items()
        if isinstance(value, dict) and value.get("class") == label
    }


def _encode_jpeg(array: Any, Image: Any, *, quality: int = 92) -> bytes:
    output = BytesIO()
    Image.fromarray(array, mode="RGB").save(
        output, "JPEG", quality=quality, optimize=False,
        progressive=False, subsampling=0,
    )
    return output.getvalue()


def _apply_sensor_effect(rgb: Any, variant_id: str, appearance_id: str,
                         seed: int, np: Any, Image: Any, ImageFilter: Any) -> bytes:
    image = Image.fromarray(rgb, mode="RGB")
    if variant_id == "defocus":
        image = image.filter(ImageFilter.GaussianBlur(radius=2.2))
    elif variant_id == "motion_blur":
        source = np.asarray(image, dtype=np.float32)
        accum = np.zeros_like(source)
        for offset in range(-5, 6):
            accum += np.roll(source, offset, axis=1)
        image = Image.fromarray(np.clip(accum / 11.0, 0, 255).astype(np.uint8), mode="RGB")
    elif variant_id == "glare":
        source = np.asarray(image, dtype=np.float32)
        yy, xx = np.ogrid[:source.shape[0], :source.shape[1]]
        glow = np.exp(-(((xx - 52.0) / 22.0) ** 2 + ((yy - 43.0) / 13.0) ** 2))
        source = np.clip(source + glow[..., None] * 105.0, 0, 255).astype(np.uint8)
        image = Image.fromarray(source, mode="RGB")
    if appearance_id == "cool_sensor":
        source = np.asarray(image, dtype=np.int16)
        noise = np.random.default_rng(seed).normal(0.0, 3.0, source.shape).astype(np.int16)
        source = np.clip(source + noise, 0, 255).astype(np.uint8)
        image = Image.fromarray(source, mode="RGB")
    quality = 30 if variant_id == "compression" else 92
    return _encode_jpeg(np.asarray(image), Image, quality=quality)


def render(workspace: Path, fixture_path: Path, output_dir: Path, status_output: Path,
           scene_limit: int | None = None, target_start: int = 0,
           target_count: int = 75) -> dict[str, Any]:
    fixture, fixture_bytes = load_fixture(fixture_path)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(workspace.resolve(strict=True) / "software/src"))
    from rocell.application.bootstrap import bootstrap_virtual_workcell

    context = bootstrap_virtual_workcell(workspace).context
    targets = sorted(
        [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()],
        key=lambda item: (item.device, item.target_id),
    )
    if len(targets) != 75 or context.targets.content_sha256 != fixture["source"]["target_catalog_sha256"]:
        raise ValueError("target catalog mismatch")
    if target_start < 0 or target_count < 1 or target_start + target_count > len(targets):
        raise ValueError("target shard is outside the catalog")
    selected_targets = list(enumerate(targets))[target_start:target_start + target_count]

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "multi_gpu": False})
    try:
        import carb.settings
        import numpy as np
        import omni.replicator.core as rep
        import omni.usd
        from isaacsim.core.experimental.utils.semantics import add_labels
        from PIL import Image, ImageFilter
        from pxr import Gf, UsdGeom, UsdLux

        rep.orchestrator.set_capture_on_play(False)
        carb.settings.get_settings().set("rtx/post/dlss/execMode", 2)
        omni.usd.get_context().new_stage()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        root = UsdGeom.Xform.Define(stage, "/World").GetPrim()
        stage.SetDefaultPrim(root)

        board = context.scene.board
        board_prim = _cube(
            stage, "/World/Board",
            ((board.minimum.x + board.maximum.x) / 2,
             (board.minimum.y + board.maximum.y) / 2, board.minimum.z - 2.0),
            (board.maximum.x - board.minimum.x,
             board.maximum.y - board.minimum.y, 4.0),
            (0.55, 0.52, 0.47), None, Gf, UsdGeom, add_labels,
        )
        for index, target in enumerate(targets):
            left, front, right, rear = target.safe_rectangle_board_mm
            _cube(
                stage, f"/World/Targets/T{index:03d}",
                ((left + right) / 2, (front + rear) / 2, target.center.z + 0.8),
                (right - left, rear - front, 1.6),
                (0.12, 0.14, 0.18) if target.device == "keyboard" else (0.08, 0.09, 0.11),
                f"target_{index:03d}", Gf, UsdGeom, add_labels,
            )

        dome = UsdLux.DomeLight.Define(stage, "/World/Dome")
        dome.CreateIntensityAttr(800.0)
        distant = UsdLux.DistantLight.Define(stage, "/World/KeyLight")
        distant.CreateIntensityAttr(1600.0)
        distant.CreateAngleAttr(2.0)
        distant.CreateColorAttr(Gf.Vec3f(1.0, 1.0, 1.0))

        scenes = fixture["base_scenes"][:scene_limit]
        rows: list[dict[str, Any]] = []
        image_hashes: set[str] = set()
        for scene_index, scene in enumerate(scenes):
            scene_dynamic_root = dynamic_root(scene_index)
            rng = random.Random(scene["isaac_seed"])
            board_prim.GetDisplayColorAttr().Set([Gf.Vec3f(
                0.48 + rng.random() * 0.12,
                0.46 + rng.random() * 0.12,
                0.42 + rng.random() * 0.12,
            )])
            cameras = []
            products = []
            rgb_annotators = []
            semantic_annotators = []
            depth_annotators = []
            for target_index, target in selected_targets:
                left, front, right, rear = target.safe_rectangle_board_mm
                camera_height = camera_height_mm(right - left, rear - front)
                jitter_x = rng.uniform(-6.0, 6.0)
                jitter_y = rng.uniform(-6.0, 6.0)
                camera = rep.functional.create.camera(
                    position=((target.center.x + jitter_x) / 1000.0,
                              (target.center.y + jitter_y) / 1000.0,
                              (target.center.z + camera_height) / 1000.0),
                    look_at=(target.center.x / 1000.0, target.center.y / 1000.0,
                             target.center.z / 1000.0),
                    look_at_up_axis=(0.0, 1.0, 0.0),
                    focal_length=24.0, horizontal_aperture=20.0,
                    clipping_range=(0.01, 1.0),
                    name=f"Camera_{scene_index:02d}_{target_index:03d}",
                )
                product = rep.create.render_product(camera, RESOLUTION, name=f"rp_{scene_index:02d}_{target_index:03d}")
                rgb = rep.AnnotatorRegistry.get_annotator("rgb")
                semantic = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
                depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
                rgb.attach(product)
                semantic.attach(product)
                depth.attach(product)
                cameras.append(camera)
                products.append(product)
                rgb_annotators.append(rgb)
                semantic_annotators.append(semantic)
                depth_annotators.append(depth)

            obstruction_prims: list[Any] = []
            adjacent_left_prims: list[Any] = []
            adjacent_right_prims: list[Any] = []
            for target_index, target in selected_targets:
                left, front, right, rear = target.safe_rectangle_board_mm
                width, height = right - left, rear - front
                z = target.center.z + 4.0
                edge_offset, edge_width, edge_height = edge_tool_geometry(width, height)
                adjacent_left_prims.append(_cube(stage, f"{scene_dynamic_root}/AdjacentLeft/A{target_index:03d}",
                    (left - width * 0.42, target.center.y, z), (width * 0.45, height * 0.7, 5.0),
                    (0.52, 0.18, 0.12), "adjacent_distractor", Gf, UsdGeom, add_labels).GetPrim())
                adjacent_right_prims.append(_cube(stage, f"{scene_dynamic_root}/AdjacentRight/A{target_index:03d}",
                    (right + width * 0.42, target.center.y, z), (width * 0.45, height * 0.7, 5.0),
                    (0.12, 0.22, 0.54), "adjacent_distractor", Gf, UsdGeom, add_labels).GetPrim())
                obstruction_prims.extend([
                    _cube(stage, f"{scene_dynamic_root}/Obstructions/C{target_index:03d}", (target.center.x, target.center.y, z),
                          (width * 1.25, height * 0.55, 5.0), (0.03, 0.03, 0.035), "residual_obstruction", Gf, UsdGeom, add_labels).GetPrim(),
                    _cube(stage, f"{scene_dynamic_root}/Obstructions/TE{target_index:03d}", (left + edge_offset, target.center.y, z),
                          (edge_width, edge_height, 6.0), (0.22, 0.24, 0.27), "residual_obstruction", Gf, UsdGeom, add_labels).GetPrim(),
                    _cube(stage, f"{scene_dynamic_root}/Obstructions/TC{target_index:03d}", (target.center.x, target.center.y, z),
                          (*centered_tool_size(width, height), 6.0), (0.48, 0.5, 0.54), "residual_obstruction", Gf, UsdGeom, add_labels).GetPrim(),
                    _ellipsoid(stage, f"{scene_dynamic_root}/Obstructions/F{target_index:03d}", (target.center.x, target.center.y, z),
                               foreign_object_radii(width, height), (0.14, 0.35, 0.18), "residual_obstruction", Gf, UsdGeom, add_labels).GetPrim(),
                ])
            adjacent_prims = adjacent_left_prims + adjacent_right_prims
            all_dynamic = adjacent_prims + obstruction_prims
            for prim in all_dynamic:
                UsdGeom.Imageable(prim).MakeInvisible()
            safe_masks: dict[int, Any] = {}

            for appearance_index, appearance in enumerate(fixture["appearances"]):
                appearance_id = appearance["appearance_id"]
                light = {
                    "neutral": (1600.0, (1.0, 1.0, 1.0)),
                    "low_key": (700.0, (1.0, 0.86, 0.72)),
                    "high_key": (2700.0, (1.0, 0.98, 0.93)),
                    "cool_sensor": (1450.0, (0.72, 0.86, 1.0)),
                }[appearance_id]
                distant.GetIntensityAttr().Set(light[0])
                distant.GetColorAttr().Set(Gf.Vec3f(*light[1]))
                for variant_index, variant in enumerate(fixture["variants"]):
                    variant_id = variant["variant_id"]
                    for local_index, (target_index, target) in enumerate(selected_targets):
                        for prim in all_dynamic:
                            UsdGeom.Imageable(prim).MakeInvisible()
                        if variant_id == "adjacent_left":
                            UsdGeom.Imageable(adjacent_left_prims[local_index]).MakeVisible()
                        elif variant_id == "adjacent_right":
                            UsdGeom.Imageable(adjacent_right_prims[local_index]).MakeVisible()
                        elif variant_id.startswith("cable_"):
                            prim = obstruction_prims[local_index * 4]
                            cable = UsdGeom.Cube(prim)
                            if variant_id == "cable_translucent":
                                cable.GetDisplayColorAttr().Set([Gf.Vec3f(0.42, 0.56, 0.62)])
                                cable.GetDisplayOpacityAttr().Set([0.62])
                            else:
                                cable.GetDisplayColorAttr().Set([Gf.Vec3f(0.03, 0.03, 0.035)])
                                cable.GetDisplayOpacityAttr().Set([1.0])
                            UsdGeom.Imageable(prim).MakeVisible()
                        elif variant_id == "tool_matte_edge":
                            UsdGeom.Imageable(obstruction_prims[local_index * 4 + 1]).MakeVisible()
                        elif variant_id == "tool_gloss_center":
                            UsdGeom.Imageable(obstruction_prims[local_index * 4 + 2]).MakeVisible()
                        elif variant_id == "foreign_object":
                            UsdGeom.Imageable(obstruction_prims[local_index * 4 + 3]).MakeVisible()
                        app.update()
                        rep.orchestrator.step(delta_time=0.0, rt_subframes=2)
                        rgb = np.asarray(rgb_annotators[local_index].get_data())[..., :3].astype(np.uint8)
                        semantic, info = _semantic_array(semantic_annotators[local_index].get_data(), np)
                        target_ids = _ids_for_label(info, f"target_{target_index:03d}")
                        obstruction_ids = _ids_for_label(info, "residual_obstruction")
                        adjacent_ids = _ids_for_label(info, "adjacent_distractor")
                        target_mask = np.isin(semantic, tuple(target_ids))
                        obstruction_mask = np.isin(semantic, tuple(obstruction_ids))
                        adjacent_mask = np.isin(semantic, tuple(adjacent_ids))
                        if variant_id == "clear":
                            safe_masks[local_index] = target_mask.copy()
                        safe_mask = safe_masks.get(local_index)
                        if safe_mask is None or not safe_mask.any():
                            raise RuntimeError(f"missing clear safe-region mask for {target.target_id}")
                        safe_area = int(np.count_nonzero(safe_mask))
                        overlap = int(np.count_nonzero(obstruction_mask & safe_mask)) / safe_area
                        adjacent_overlap = int(np.count_nonzero(adjacent_mask & safe_mask)) / safe_area
                        declared_overlap = variant["geometry"].get("safe_overlap")
                        if variant["family"] not in {"IMAGE_QUALITY", "NONE"}:
                            measured = adjacent_overlap if variant["family"] == "DISTRACTOR" else overlap
                            if isinstance(declared_overlap, list):
                                if not declared_overlap[0] <= measured <= declared_overlap[1]:
                                    raise RuntimeError(
                                        f"safe overlap outside contract for {variant_id}/{target.target_id}: {measured}"
                                    )
                            elif declared_overlap is not None and measured != declared_overlap:
                                raise RuntimeError(
                                    f"safe overlap outside contract for {variant_id}/{target.target_id}: {measured}"
                                )
                        seed = scene["isaac_seed"] * 100000 + appearance_index * 10000 + variant_index * 100 + target_index
                        jpeg = _apply_sensor_effect(rgb, variant_id, appearance_id, seed, np, Image, ImageFilter)
                        relative = Path(scene["split"]) / scene["scene_id"] / appearance_id / variant_id / f"{target_index:03d}.jpg"
                        path = output_dir / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(jpeg)
                        digest = sha256_bytes(jpeg)
                        if digest in image_hashes:
                            raise RuntimeError(f"duplicate observation bytes: {relative}")
                        image_hashes.add(digest)
                        depth_raw = depth_annotators[local_index].get_data()
                        depth = np.asarray(depth_raw["data"] if isinstance(depth_raw, dict) else depth_raw)
                        finite = depth[np.isfinite(depth)]
                        rows.append({
                            "observation_id": f"{scene['scene_id']}:{appearance_id}:{variant_id}:{target.device}:{target.target_id}",
                            "split": scene["split"], "scene_id": scene["scene_id"],
                            "appearance_id": appearance_id, "variant_id": variant_id,
                            "target_id": target.target_id, "device": target.device,
                            "expected_decision": variant["decision"],
                            "rgb_path": relative.as_posix(), "rgb_sha256": digest,
                            "rgb_bytes": len(jpeg), "safe_overlap_fraction": overlap,
                            "adjacent_overlap_fraction": adjacent_overlap,
                            "depth_min_mm": float(finite.min() * 1000.0) if finite.size else None,
                            "depth_max_mm": float(finite.max() * 1000.0) if finite.size else None,
                        })
            for annotator in [*rgb_annotators, *semantic_annotators, *depth_annotators]:
                annotator.detach()
            for product in products:
                product.destroy()
            stage.RemovePrim(scene_dynamic_root)

        split_counts = {split: sum(row["split"] == split for row in rows) for split in ("training", "development")}
        core = {
            "schema": MANIFEST_SCHEMA,
            "scope": "SYNTHETIC_ISAAC_RENDER_NO_QUALIFICATION",
            "fixture_file_sha256": sha256_bytes(fixture_bytes),
            "fixture_bundle_sha256": fixture["bundle_sha256"],
            "complete_campaign": scene_limit is None and target_start == 0 and target_count == 75,
            "scene_count": len(scenes), "observation_count": len(rows),
            "target_shard": {"start": target_start, "count": target_count},
            "split_counts": split_counts, "observations": rows,
            "evaluation_observation_count": 0,
            "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
            "limitations": [
                "Synthetic Isaac renders do not establish physical or deployment qualification",
                "Image-quality sensor effects are deterministic render postprocesses over fresh Isaac frames",
                "No model was trained and evaluation remains absent",
            ],
        }
        result = {**core, "dataset_sha256": sha256_bytes(canonical(core))}
        (output_dir / "manifest.json").write_bytes(canonical(result) + b"\n")
        status_output.parent.mkdir(parents=True, exist_ok=True)
        status_output.write_text(json.dumps({
            "status": "PASS", "manifest_schema": result["schema"],
            "dataset_sha256": result["dataset_sha256"],
            "observation_count": result["observation_count"],
        }, indent=2) + "\n", encoding="utf-8")
        return result
    except Exception as exc:
        (output_dir / "failure.json").write_text(
            json.dumps({"error_type": type(exc).__name__, "error": str(exc)}, indent=2) + "\n",
            encoding="utf-8",
        )
        status_output.parent.mkdir(parents=True, exist_ok=True)
        status_output.write_text(json.dumps({
            "status": "FAIL", "error_type": type(exc).__name__, "error": str(exc),
        }, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        app.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scene-limit", type=int)
    parser.add_argument("--target-start", type=int, default=0)
    parser.add_argument("--target-count", type=int, default=75)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = render(
            args.workspace, args.fixture, args.output_dir, args.status_output,
            args.scene_limit, args.target_start, args.target_count,
        )
        status = {"status": "PASS", "manifest_schema": result["schema"], "dataset_sha256": result["dataset_sha256"], "observation_count": result["observation_count"]}
    except Exception as exc:
        status = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)}
        args.status_output.parent.mkdir(parents=True, exist_ok=True)
        args.status_output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        raise
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
