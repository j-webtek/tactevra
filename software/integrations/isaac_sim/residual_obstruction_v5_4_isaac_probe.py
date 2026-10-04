"""Render a sharded residual-obstruction v5.4 edge/texture reference-pair campaign in Isaac Sim.

This runner creates fresh target-local 3D renders.  Truth segmentation and
depth are retained for admission only; model inputs are RGB JPEG files.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from typing import Any


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v5_4"
V5_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v5"
MANIFEST_SCHEMA = "tactevra.ai_residual_obstruction_v5_4_shard_manifest.v1"
RESOLUTION = (192, 192)
LOCAL_SLICE = (slice(48, 144), slice(48, 144))
LINK_RADIUS_MM = {
    "base_link": 32.0, "link1": 27.0, "link2": 25.0, "link3": 23.0,
    "link4": 21.0, "link5": 19.0, "gripper_link": 24.0, "hand_tcp": 10.0,
}


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


def _rotate_vector(
    vector: tuple[float, float, float], euler_deg: tuple[float, float, float]
) -> tuple[float, float, float]:
    x, y, z = vector
    rx, ry, rz = (math.radians(value) for value in euler_deg)
    cy, sy = math.cos(rx), math.sin(rx)
    y, z = y * cy - z * sy, y * sy + z * cy
    cx, sx = math.cos(ry), math.sin(ry)
    x, z = x * cx + z * sx, -x * sx + z * cx
    cx, sx = math.cos(rz), math.sin(rz)
    x, y = x * cx - y * sx, x * sx + y * cx
    return x, y, z


def sample_camera_contract(
    scene: dict[str, Any], target: Any, height_mm: float, rng: random.Random
) -> dict[str, list[float]]:
    position_limits = scene["camera_pose_jitter_mm"]
    rotation_limits = scene["camera_rotation_jitter_deg"]
    position_jitter = [rng.uniform(-limit, limit) for limit in position_limits]
    rotation_jitter = [rng.uniform(-limit, limit) for limit in rotation_limits]
    position = [
        target.center.x + position_jitter[0],
        target.center.y + position_jitter[1],
        target.center.z + height_mm + position_jitter[2],
    ]
    nominal = [target.center.x - position[0], target.center.y - position[1], target.center.z - position[2]]
    length = math.sqrt(sum(value * value for value in nominal))
    forward = _rotate_vector(tuple(value / length for value in nominal), tuple(rotation_jitter))
    up = _rotate_vector((0.0, 1.0, 0.0), tuple(rotation_jitter))
    look_at = [position[index] + forward[index] * height_mm for index in range(3)]
    return {
        "camera_position_mm": position,
        "camera_look_at_mm": look_at,
        "camera_up_axis": list(up),
        "camera_position_jitter_mm": position_jitter,
        "camera_rotation_jitter_deg": rotation_jitter,
    }


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
    if payload["evaluation_opened"] is not False:
        raise ValueError("evaluation must remain absent")
    v5_path = path.with_name("residual_obstruction_successor_v5.json")
    v5_bytes = v5_path.resolve(strict=True).read_bytes()
    if sha256_bytes(v5_bytes) != payload["source"]["v5_file_sha256"]:
        raise ValueError("v5 source file hash mismatch")
    v5 = json.loads(v5_bytes)
    if v5.get("schema") != V5_SCHEMA or v5.get("bundle_sha256") != payload["source"]["v5_bundle_sha256"]:
        raise ValueError("v5 source fixture mismatch")
    v5_core = {key: value for key, value in v5.items() if key != "bundle_sha256"}
    if v5["bundle_sha256"] != sha256_bytes(canonical(v5_core)):
        raise ValueError("v5 source canonical hash mismatch")
    if v5["render_contract"]["evaluation_images_generated"] != 0:
        raise ValueError("v5 source must keep evaluation pixel-free")
    merged = dict(payload)
    merged["variants"] = v5["variants"]
    merged["render_contract"] = v5["render_contract"]
    merged["candidate_models"] = v5["candidate_models"]
    merged["base_scenes"] = []
    for split, lower in (("training", 51000), ("development", 52000)):
        for index, scene_id in enumerate(v5["split_identities"]["scenes"][split]):
            merged["base_scenes"].append({
                "split": split,
                "scene_id": scene_id,
                "isaac_seed": lower + index,
                "camera_pose_jitter_mm": v5["render_contract"]["camera_translation_jitter_mm"],
                "camera_rotation_jitter_deg": v5["render_contract"]["camera_rotation_jitter_deg"],
            })
    families = ("NEUTRAL", "WARM_SIDE", "DIM_AMBIENT")
    merged["appearances"] = [
        {"split": split, "appearance_id": appearance_id, "family": families[index]}
        for split in ("training", "development")
        for index, appearance_id in enumerate(v5["split_identities"]["lighting"][split])
    ]
    merged["obstruction_assets"] = v5["split_identities"]["obstruction_assets"]
    merged["v5_file_sha256"] = sha256_bytes(v5_bytes)
    return merged, payload_bytes


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


def _cylinder(stage: Any, path: str, center_mm: tuple[float, float, float],
              length_mm: float, radius_mm: float, color: tuple[float, float, float],
              opacity: float, label: str, Gf: Any, UsdGeom: Any, add_labels: Any) -> Any:
    cylinder = UsdGeom.Cylinder.Define(stage, path)
    cylinder.GetRadiusAttr().Set(1.0)
    cylinder.GetHeightAttr().Set(2.0)
    xform = UsdGeom.Xformable(cylinder)
    xform.AddTranslateOp().Set(Gf.Vec3d(*(value / 1000.0 for value in center_mm)))
    xform.AddRotateYOp().Set(90.0)
    xform.AddScaleOp().Set(Gf.Vec3d(
        radius_mm / 1000.0, radius_mm / 1000.0, length_mm / 2000.0,
    ))
    cylinder.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    cylinder.CreateDisplayOpacityAttr([opacity])
    add_labels(cylinder.GetPrim(), labels=[label], taxonomy="class")
    return cylinder


def _family_assets(fixture: dict[str, Any], split: str, variant_id: str) -> list[str]:
    assets = fixture["obstruction_assets"][split]
    token = (
        "dark_cable" if variant_id.startswith("dark_cable")
        else "translucent_cable" if variant_id.startswith("translucent_cable")
        else "hand" if variant_id.startswith("hand")
        else "tool_foreign"
    )
    selected = [asset_id for asset_id in assets if token in asset_id]
    if not selected:
        raise ValueError(f"no {split} assets for {variant_id}")
    return selected


def obstruction_render_descriptor(
    asset_id: str, variant_id: str, width_mm: float, height_mm: float, coverage: float
) -> dict[str, Any]:
    """Return the exact values used to author one procedural obstruction prim."""
    if not asset_id or width_mm <= 0 or height_mm <= 0 or not 0 < coverage <= 1:
        raise ValueError("invalid procedural obstruction inputs")
    asset_seed = int(sha256_bytes(asset_id.encode())[:8], 16)
    width_scale = 1.03 + (asset_seed % 17) / 100.0
    color = [0.025, 0.025, 0.03]
    opacity = 1.0
    if variant_id.startswith("translucent"):
        color, opacity = [0.38, 0.52, 0.62], 0.62
    elif variant_id.startswith("hand"):
        color = [0.52, 0.25, 0.16]
    elif variant_id.startswith("tool"):
        color = [0.28, 0.3, 0.34]
    elif variant_id.startswith("foreign"):
        color = [0.15, 0.37, 0.19]
    if "cable" in variant_id:
        geometry = {
            "primitive": "UsdGeom.Cylinder", "length_mm": width_mm * width_scale,
            "radius_mm": height_mm * coverage / 2.0, "rotate_y_deg": 90.0,
        }
    elif variant_id.startswith(("hand", "foreign")):
        scale = 0.54 + (asset_seed % 7) / 100.0 if variant_id.startswith("hand") else 0.45 + (asset_seed % 9) / 100.0
        x_radius = width_mm * scale
        geometry = {
            "primitive": "UsdGeom.SphereEllipsoid", "x_radius_mm": x_radius,
            "y_radius_mm": height_mm * coverage / (math.pi * (x_radius / width_mm)),
            "z_radius_mm": 4.0,
        }
    else:
        geometry = {
            "primitive": "UsdGeom.Cube", "size_mm": [width_mm * width_scale, height_mm * coverage, 6.0],
        }
    return {
        "schema": "tactevra.synthetic_obstruction_render_descriptor.v1",
        "asset_id": asset_id, "variant_id": variant_id, "geometry": geometry,
        "material": {"display_color_rgb": color, "display_opacity": opacity},
        "texture": {"kind": "NONE_PROCEDURAL_SOLID_DISPLAY_COLOR"},
    }


def project_capsule_mask(
    camera_contract: dict[str, list[float]], segments: list[dict[str, Any]],
    Image: Any, ImageDraw: Any,
) -> tuple[bytes, dict[str, Any]]:
    """Project FK capsule proxies analytically, without simulator segmentation truth."""
    import numpy as np

    position = np.asarray(camera_contract["camera_position_mm"], dtype=np.float64)
    look_at = np.asarray(camera_contract["camera_look_at_mm"], dtype=np.float64)
    up_hint = np.asarray(camera_contract["camera_up_axis"], dtype=np.float64)
    forward = look_at - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up_hint)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    focal_px = 24.0 / 20.0 * RESOLUTION[0]

    def project(point: list[float]) -> tuple[float, float, float] | None:
        relative = np.asarray(point, dtype=np.float64) - position
        depth = float(np.dot(relative, forward))
        if depth <= 1.0:
            return None
        return (
            RESOLUTION[0] / 2.0 + focal_px * float(np.dot(relative, right)) / depth,
            RESOLUTION[1] / 2.0 - focal_px * float(np.dot(relative, up)) / depth,
            depth,
        )

    image = Image.new("L", RESOLUTION, 0)
    draw = ImageDraw.Draw(image)
    projected = []
    for segment in segments:
        start, end = project(segment["start_board_mm"]), project(segment["end_board_mm"])
        if start is None or end is None:
            continue
        radius_px = max(1, round(focal_px * segment["radius_mm"] / min(start[2], end[2])))
        width = radius_px * 2
        points = ((round(start[0]), round(start[1])), (round(end[0]), round(end[1])))
        draw.line((*points[0], *points[1]), fill=255, width=width)
        for x, y in points:
            draw.ellipse((x - radius_px, y - radius_px, x + radius_px, y + radius_px), fill=255)
        projected.append({
            "link": segment["link"], "start_px": [start[0], start[1]],
            "end_px": [end[0], end[1]], "radius_px": radius_px,
        })
    output = BytesIO()
    image.save(output, "PNG", optimize=False, compress_level=9)
    payload = output.getvalue()
    return payload, {
        "projection_model": "ANALYTIC_PINHOLE_FK_CAPSULES_NO_SIMULATOR_MASK",
        "focal_length_mm": 24.0, "horizontal_aperture_mm": 20.0,
        "resolution_px": list(RESOLUTION), "projected_segments": projected,
        "projected_segment_count": len(projected),
    }


def perturbed_fk_capsules(
    context: Any, model: Any, joint_noise_deg: float, backlash_deg: float,
    capture_offset_ms: float, JointPosition: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive board-frame capsule proxies from a perturbed measured-state surrogate."""
    joints = {}
    perturbations = {}
    settled_drift_deg = max(-0.05, min(0.05, capture_offset_ms / 3000.0))
    for index, (name, position) in enumerate(sorted(context.scenario.ready_arm_joint_positions_rad.items())):
        sign = -1.0 if index % 2 else 1.0
        perturbation_deg = sign * (joint_noise_deg + backlash_deg + settled_drift_deg)
        joints[name] = JointPosition.radians(position.value + math.radians(perturbation_deg))
        perturbations[name] = perturbation_deg
    joints["link5_to_gripper_link"] = context.scenario.fixed_gripper_position
    transforms = model.forward_kinematics(joints)
    board_points = {
        link: context.scenario.board_T_world.compose(transform).translation_mm
        for link, transform in transforms.items()
    }
    segments = []
    for joint in model.joints:
        start, end = board_points[joint.parent_link], board_points[joint.child_link]
        segments.append({
            "link": joint.child_link,
            "start_board_mm": [start.x, start.y, start.z],
            "end_board_mm": [end.x, end.y, end.z],
            "radius_mm": LINK_RADIUS_MM.get(joint.child_link, 18.0),
        })
    return segments, {
        "source": "PERTURBED_READY_MEASURED_STATE_SURROGATE_NOT_SIMULATOR_TRUTH",
        "joint_measurement_noise_deg": joint_noise_deg,
        "backlash_deg": backlash_deg,
        "capture_timestamp_offset_ms": capture_offset_ms,
        "settled_capture_drift_proxy_deg": settled_drift_deg,
        "per_joint_perturbation_deg": perturbations,
        "joint_values_emitted_to_model": False,
    }


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


def _encode_mask_png(mask: Any, Image: Any, np: Any) -> bytes:
    output = BytesIO()
    Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(output, "PNG")
    return output.getvalue()


def _apply_sensor_effect_array(rgb: Any, variant_id: str, appearance_id: str,
                               seed: int, np: Any, Image: Any, ImageFilter: Any) -> Any:
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
    if "cool_sensor" in appearance_id:
        source = np.asarray(image, dtype=np.int16)
        noise = np.random.default_rng(seed).normal(0.0, 3.0, source.shape).astype(np.int16)
        source = np.clip(source + noise, 0, 255).astype(np.uint8)
        image = Image.fromarray(source, mode="RGB")
    return np.asarray(image)


def _apply_sensor_effect(rgb: Any, variant_id: str, appearance_id: str,
                         seed: int, np: Any, Image: Any, ImageFilter: Any) -> bytes:
    array = _apply_sensor_effect_array(
        rgb, variant_id, appearance_id, seed, np, Image, ImageFilter
    )
    quality = 30 if variant_id == "compression" else 92
    return _encode_jpeg(array, Image, quality=quality)


def normalization_difference_metrics(reference: Any, observation: Any, np: Any) -> dict[str, float]:
    """Compare self-crop and surrounding-context photometric normalization."""
    reference = reference.astype(np.float32) / 255.0
    observation = observation.astype(np.float32) / 255.0
    context = np.ones(reference.shape[:2], dtype=bool)
    context[24:72, 24:72] = False

    def self_normalize(value: Any, mask: Any) -> Any:
        samples = value[mask]
        low = np.quantile(samples, 0.05, axis=0)
        high = np.quantile(samples, 0.95, axis=0)
        return np.clip((value - low) / np.maximum(high - low, 0.05), 0.0, 1.0)

    reference_context_white = np.quantile(reference[context], 0.95, axis=0)

    def reference_context_normalize(value: Any) -> Any:
        return np.clip(value / np.maximum(reference_context_white, 0.05), 0.0, 1.0)

    raw = float(np.mean(np.abs(reference - observation)))
    crop = float(np.mean(np.abs(self_normalize(reference, np.ones(context.shape, bool)) - self_normalize(
        observation, np.ones(context.shape, bool)
    ))))
    contextual = float(np.mean(np.abs(
        reference_context_normalize(reference) - reference_context_normalize(observation)
    )))
    return {
        "raw_mean_absolute_difference": raw,
        "self_crop_normalized_mean_absolute_difference": crop,
        "context_normalized_mean_absolute_difference": contextual,
        "self_to_context_signal_ratio": crop / contextual if contextual > 0.0 else 1.0,
    }


def admit_variant_measurement(
    fixture: dict[str, Any], variant_id: str, safe_overlap: float, adjacent_overlap: float
) -> None:
    variant = next(row for row in fixture["variants"] if row["variant_id"] == variant_id)
    coverage = variant.get("coverage")
    bounds = None if coverage is None else (max(0.0, coverage - 0.12), min(1.0, coverage + 0.12))
    if bounds is not None and not (bounds[0] <= safe_overlap <= bounds[1]):
        raise RuntimeError(
            f"{variant_id} safe overlap {safe_overlap} outside [{bounds[0]}, {bounds[1]}]"
        )
    if variant_id in {"clear", "adjacent_left", "adjacent_right"} and safe_overlap != 0.0:
        raise RuntimeError(f"{variant_id} unexpectedly overlaps the safe region")
    if variant_id in {"adjacent_left", "adjacent_right"} and adjacent_overlap != 0.0:
        raise RuntimeError(f"{variant_id} distractor overlaps the safe region")


def render(workspace: Path, fixture_path: Path, output_dir: Path, status_output: Path,
           split: str, scene_start: int = 0, scene_count: int | None = None,
           target_start: int = 0, target_count: int = 75,
           *, scene_indices: list[int] | None = None,
           target_indices: list[int] | None = None,
           variant_ids: list[str] | None = None,
           retain_raw_rgb: bool = False) -> dict[str, Any]:
    fixture, fixture_bytes = load_fixture(fixture_path)
    if split not in {"training", "development"}:
        raise ValueError("only training and development rendering is permitted")
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(workspace.resolve(strict=True) / "software/src"))
    from rocell.application.bootstrap import bootstrap_virtual_workcell
    from rocell.geometry import JointPosition, UrdfModel

    context = bootstrap_virtual_workcell(workspace).context
    arm_model = UrdfModel.from_file(context.scenario.model_path)
    targets = sorted(
        [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()],
        key=lambda item: (item.device, item.target_id),
    )
    if len(targets) != 75 or context.targets.content_sha256 != fixture["source"]["target_catalog_sha256"]:
        raise ValueError("target catalog mismatch")
    if target_indices is None:
        if target_start < 0 or target_count < 1 or target_start + target_count > len(targets):
            raise ValueError("target shard is outside the catalog")
        selected_targets = list(enumerate(targets))[target_start:target_start + target_count]
    else:
        if len(target_indices) != len(set(target_indices)) or not target_indices:
            raise ValueError("target indices must be nonempty and unique")
        if any(index < 0 or index >= len(targets) for index in target_indices):
            raise ValueError("target index is outside the catalog")
        selected_targets = [(index, targets[index]) for index in target_indices]
    selected_variants = [
        row for row in fixture["variants"]
        if variant_ids is None or row["variant_id"] in set(variant_ids)
    ]
    if variant_ids is not None and {
        row["variant_id"] for row in selected_variants
    } != set(variant_ids):
        raise ValueError("unknown or duplicate variant selection")

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "multi_gpu": False})
    try:
        import carb.settings
        import numpy as np
        import omni.replicator.core as rep
        import omni.usd
        from isaacsim.core.experimental.utils.semantics import add_labels
        from PIL import Image, ImageDraw, ImageFilter
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

        split_scenes = [row for row in fixture["base_scenes"] if row["split"] == split]
        if scene_indices is None:
            if scene_start < 0 or scene_start >= len(split_scenes):
                raise ValueError("scene start is outside the selected split")
            end = len(split_scenes) if scene_count is None else scene_start + scene_count
            if scene_count is not None and scene_count < 1:
                raise ValueError("scene count must be positive")
            if end > len(split_scenes):
                raise ValueError("scene shard is outside the selected split")
            scenes = split_scenes[scene_start:end]
        else:
            if len(scene_indices) != len(set(scene_indices)) or not scene_indices:
                raise ValueError("scene indices must be nonempty and unique")
            if any(index < 0 or index >= len(split_scenes) for index in scene_indices):
                raise ValueError("scene index is outside the selected split")
            scenes = [split_scenes[index] for index in scene_indices]
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
            camera_contracts = []
            for target_index, target in selected_targets:
                left, front, right, rear = target.safe_rectangle_board_mm
                camera_height = camera_height_mm(right - left, rear - front)
                camera_contract = sample_camera_contract(scene, target, camera_height, rng)
                camera = rep.functional.create.camera(
                    position=tuple(value / 1000.0 for value in camera_contract["camera_position_mm"]),
                    look_at=tuple(value / 1000.0 for value in camera_contract["camera_look_at_mm"]),
                    look_at_up_axis=tuple(camera_contract["camera_up_axis"]),
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
                camera_contracts.append(camera_contract)

            obstruction_prims: list[dict[str, Any]] = []
            obstruction_descriptors: list[dict[str, dict[str, Any]]] = []
            adjacent_left_prims: list[Any] = []
            adjacent_right_prims: list[Any] = []
            for target_index, target in selected_targets:
                left, front, right, rear = target.safe_rectangle_board_mm
                width, height = right - left, rear - front
                z = target.center.z + 4.0
                adjacent_left_prims.append(_cube(stage, f"{scene_dynamic_root}/AdjacentLeft/A{target_index:03d}",
                    (left - width * 0.42, target.center.y, z), (width * 0.45, height * 0.7, 5.0),
                    (0.52, 0.18, 0.12), "adjacent_distractor", Gf, UsdGeom, add_labels).GetPrim())
                adjacent_right_prims.append(_cube(stage, f"{scene_dynamic_root}/AdjacentRight/A{target_index:03d}",
                    (right + width * 0.42, target.center.y, z), (width * 0.45, height * 0.7, 5.0),
                    (0.12, 0.22, 0.54), "adjacent_distractor", Gf, UsdGeom, add_labels).GetPrim())
                per_variant: dict[str, Any] = {}
                per_variant_descriptors: dict[str, dict[str, Any]] = {}
                for variant in selected_variants:
                    variant_id = variant["variant_id"]
                    coverage = variant.get("coverage")
                    if coverage is None:
                        continue
                    asset_ids = _family_assets(fixture, split, variant_id)
                    asset_id = asset_ids[(target_index + len(per_variant)) % len(asset_ids)]
                    descriptor = obstruction_render_descriptor(
                        asset_id, variant_id, width, height, coverage
                    )
                    geometry = descriptor["geometry"]
                    material = descriptor["material"]
                    color = tuple(material["display_color_rgb"])
                    geometry_path = f"{scene_dynamic_root}/Obstructions/T{target_index:03d}_{variant_id}"
                    if geometry["primitive"] == "UsdGeom.Cylinder":
                        prim = _cylinder(
                            stage, geometry_path, (target.center.x, target.center.y, z),
                            geometry["length_mm"], geometry["radius_mm"], color,
                            material["display_opacity"],
                            "residual_obstruction", Gf, UsdGeom, add_labels,
                        ).GetPrim()
                    elif geometry["primitive"] == "UsdGeom.SphereEllipsoid":
                        prim = _ellipsoid(
                            stage, geometry_path, (target.center.x, target.center.y, z),
                            (geometry["x_radius_mm"], geometry["y_radius_mm"]), color,
                            "residual_obstruction",
                            Gf, UsdGeom, add_labels,
                        ).GetPrim()
                    else:
                        prim = _cube(
                            stage, geometry_path, (target.center.x, target.center.y, z),
                            tuple(geometry["size_mm"]), color,
                            "residual_obstruction", Gf, UsdGeom, add_labels,
                        ).GetPrim()
                    per_variant[variant_id] = prim
                    per_variant_descriptors[variant_id] = descriptor
                obstruction_prims.append(per_variant)
                obstruction_descriptors.append(per_variant_descriptors)
            adjacent_prims = adjacent_left_prims + adjacent_right_prims
            all_dynamic = adjacent_prims + [
                prim for mapping in obstruction_prims for prim in mapping.values()
            ]
            for prim in all_dynamic:
                UsdGeom.Imageable(prim).MakeInvisible()
            for appearance_index, appearance in enumerate(row for row in fixture["appearances"] if row["split"] == split):
                appearance_id = appearance["appearance_id"]
                light = {
                    "NEUTRAL": (1600.0, (1.0, 1.0, 1.0)),
                    "WARM_SIDE": (900.0, (1.0, 0.82, 0.68)),
                    "DIM_AMBIENT": (500.0, (0.88, 0.9, 1.0)),
                    "COOL_SENSOR": (1450.0, (0.72, 0.86, 1.0)),
                }[appearance["family"]]
                distant.GetIntensityAttr().Set(light[0])
                distant.GetColorAttr().Set(Gf.Vec3f(*light[1]))
                for prim in all_dynamic:
                    UsdGeom.Imageable(prim).MakeInvisible()
                app.update()
                rep.orchestrator.step(delta_time=0.0, rt_subframes=2)
                safe_masks: dict[int, Any] = {}
                reference_images: dict[int, Any] = {}
                reference_records: dict[int, dict[str, Any]] = {}
                for local_index, (target_index, target) in enumerate(selected_targets):
                    reference_context = np.asarray(
                        rgb_annotators[local_index].get_data()
                    )[..., :3].astype(np.uint8)
                    reference_local = reference_context[LOCAL_SLICE]
                    reference_jpeg = _encode_jpeg(reference_local, Image, quality=92)
                    reference_context_jpeg = _encode_jpeg(reference_context, Image, quality=92)
                    reference_relative = Path("reference") / scene["scene_id"] / appearance_id / f"{target_index:03d}_local.jpg"
                    reference_context_relative = Path("reference") / scene["scene_id"] / appearance_id / f"{target_index:03d}_context.jpg"
                    for relative, content in (
                        (reference_relative, reference_jpeg),
                        (reference_context_relative, reference_context_jpeg),
                    ):
                        path = output_dir / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(content)
                    reference_raw_relative = None
                    if retain_raw_rgb:
                        reference_raw_relative = Path("raw") / "reference" / scene["scene_id"] / appearance_id / f"{target_index:03d}_local.png"
                        raw_path = output_dir / reference_raw_relative
                        raw_path.parent.mkdir(parents=True, exist_ok=True)
                        Image.fromarray(reference_local, mode="RGB").save(raw_path, "PNG")
                    semantic, info = _semantic_array(
                        semantic_annotators[local_index].get_data(), np
                    )
                    target_ids = _ids_for_label(info, f"target_{target_index:03d}")
                    safe_mask = np.isin(semantic, tuple(target_ids))
                    if not safe_mask.any():
                        raise RuntimeError(f"missing reference safe-region mask for {target.target_id}")
                    safe_masks[local_index] = safe_mask
                    reference_images[local_index] = reference_local
                    reference_records[local_index] = {
                        "reference_id": f"{scene['scene_id']}:{appearance_id}:{target.device}:{target.target_id}",
                        "reference_rgb_path": reference_relative.as_posix(),
                        "reference_rgb_sha256": sha256_bytes(reference_jpeg),
                        "reference_rgb_bytes": len(reference_jpeg),
                        "reference_context_rgb_path": reference_context_relative.as_posix(),
                        "reference_context_rgb_sha256": sha256_bytes(reference_context_jpeg),
                        "reference_raw_rgb_path": (
                            reference_raw_relative.as_posix() if reference_raw_relative else None
                        ),
                        "reference_light_intensity": light[0],
                        "reference_light_color": list(light[1]),
                        **camera_contracts[local_index],
                    }
                for variant_index, variant in enumerate(selected_variants):
                    variant_id = variant["variant_id"]
                    for local_index, (target_index, target) in enumerate(selected_targets):
                        for prim in all_dynamic:
                            UsdGeom.Imageable(prim).MakeInvisible()
                        if variant_id == "adjacent_left":
                            UsdGeom.Imageable(adjacent_left_prims[local_index]).MakeVisible()
                        elif variant_id == "adjacent_right":
                            UsdGeom.Imageable(adjacent_right_prims[local_index]).MakeVisible()
                        elif variant_id in obstruction_prims[local_index]:
                            UsdGeom.Imageable(obstruction_prims[local_index][variant_id]).MakeVisible()
                        app.update()
                        rep.orchestrator.step(delta_time=0.0, rt_subframes=2)
                        rgb = np.asarray(rgb_annotators[local_index].get_data())[..., :3].astype(np.uint8)
                        semantic, info = _semantic_array(semantic_annotators[local_index].get_data(), np)
                        obstruction_ids = _ids_for_label(info, "residual_obstruction")
                        adjacent_ids = _ids_for_label(info, "adjacent_distractor")
                        obstruction_mask = np.isin(semantic, tuple(obstruction_ids))
                        adjacent_mask = np.isin(semantic, tuple(adjacent_ids))
                        safe_mask = safe_masks.get(local_index)
                        if safe_mask is None or not safe_mask.any():
                            raise RuntimeError(f"missing clear safe-region mask for {target.target_id}")
                        safe_area = int(np.count_nonzero(safe_mask))
                        overlap = int(np.count_nonzero(obstruction_mask & safe_mask)) / safe_area
                        adjacent_overlap = int(np.count_nonzero(adjacent_mask & safe_mask)) / safe_area
                        admit_variant_measurement(fixture, variant_id, overlap, adjacent_overlap)
                        seed = scene["isaac_seed"] * 100000 + appearance_index * 10000 + variant_index * 100 + target_index
                        raw_observation_context = _apply_sensor_effect_array(
                            rgb, variant_id, appearance_id, seed, np, Image, ImageFilter
                        )
                        quality = 30 if variant_id == "compression" else 92
                        context_jpeg = _encode_jpeg(
                            raw_observation_context, Image, quality=quality
                        )
                        observation_context = np.asarray(
                            Image.open(BytesIO(context_jpeg)).convert("RGB"), dtype=np.uint8
                        )
                        observation_image = observation_context[LOCAL_SLICE]
                        raw_observation_image = raw_observation_context[LOCAL_SLICE]
                        jpeg = _encode_jpeg(observation_image, Image, quality=92)
                        difference_metrics = normalization_difference_metrics(
                            reference_images[local_index], observation_image, np
                        )
                        relative = Path(scene["split"]) / scene["scene_id"] / appearance_id / variant_id / f"{target_index:03d}_local.jpg"
                        context_relative = Path(scene["split"]) / scene["scene_id"] / appearance_id / variant_id / f"{target_index:03d}_context.jpg"
                        mask_relative = Path(scene["split"]) / scene["scene_id"] / appearance_id / variant_id / f"{target_index:03d}_safe.png"
                        path = output_dir / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(jpeg)
                        (output_dir / context_relative).write_bytes(context_jpeg)
                        raw_relative = None
                        if retain_raw_rgb:
                            raw_relative = Path("raw") / scene["scene_id"] / appearance_id / variant_id / f"{target_index:03d}_local.png"
                            raw_path = output_dir / raw_relative
                            raw_path.parent.mkdir(parents=True, exist_ok=True)
                            Image.fromarray(raw_observation_image, mode="RGB").save(
                                raw_path, "PNG"
                            )
                        mask_bytes = _encode_mask_png(safe_mask[LOCAL_SLICE], Image, np)
                        (output_dir / mask_relative).write_bytes(mask_bytes)
                        digest = sha256_bytes(jpeg)
                        if digest in image_hashes:
                            raise RuntimeError(f"duplicate observation bytes: {relative}")
                        image_hashes.add(digest)
                        depth_raw = depth_annotators[local_index].get_data()
                        depth = np.asarray(depth_raw["data"] if isinstance(depth_raw, dict) else depth_raw)
                        finite = depth[np.isfinite(depth)]
                        asset_id = None
                        render_descriptor = None
                        if variant.get("coverage") is not None:
                            render_descriptor = obstruction_descriptors[local_index][variant_id]
                            asset_id = render_descriptor["asset_id"]
                        joint_noise_deg = round(rng.uniform(-0.35, 0.35), 6)
                        backlash_deg = round(rng.uniform(-0.55, 0.55), 6)
                        capture_offset_ms = round(rng.uniform(-150.0, 150.0), 6)
                        capsules, arm_projection_input = perturbed_fk_capsules(
                            context, arm_model, joint_noise_deg, backlash_deg,
                            capture_offset_ms, JointPosition,
                        )
                        arm_mask_bytes, arm_projection = project_capsule_mask(
                            camera_contracts[local_index], capsules, Image, ImageDraw,
                        )
                        arm_mask_relative = Path(scene["split"]) / scene["scene_id"] / appearance_id / variant_id / f"{target_index:03d}_arm_projection.png"
                        (output_dir / arm_mask_relative).write_bytes(arm_mask_bytes)
                        rows.append({
                            **reference_records[local_index],
                            "observation_id": f"{scene['scene_id']}:{appearance_id}:{variant_id}:{target.device}:{target.target_id}",
                            "split": scene["split"], "scene_id": scene["scene_id"],
                            "appearance_id": appearance_id, "variant_id": variant_id,
                            "variant_family": variant["family"],
                            "target_id": target.target_id, "device": target.device,
                            "expected_decision": variant["decision"],
                            "rgb_path": relative.as_posix(), "rgb_sha256": digest,
                            "rgb_bytes": len(jpeg), "safe_overlap_fraction": overlap,
                            "raw_rgb_path": raw_relative.as_posix() if raw_relative else None,
                            "context_rgb_path": context_relative.as_posix(),
                            "context_rgb_sha256": sha256_bytes(context_jpeg),
                            "safe_region_mask_path": mask_relative.as_posix(),
                            "safe_region_mask_sha256": sha256_bytes(mask_bytes),
                            "obstruction_asset_id": asset_id,
                            "obstruction_asset_signature_sha256": (
                                sha256_bytes(canonical(render_descriptor)) if render_descriptor else None
                            ),
                            "obstruction_render_descriptor": render_descriptor,
                            "arm_projection_input": arm_projection_input,
                            "arm_projection": arm_projection,
                            "arm_projection_mask_path": arm_mask_relative.as_posix(),
                            "arm_projection_mask_sha256": sha256_bytes(arm_mask_bytes),
                            "arm_projection_mask_bytes": len(arm_mask_bytes),
                            "adjacent_overlap_fraction": adjacent_overlap,
                            "depth_min_mm": float(finite.min() * 1000.0) if finite.size else None,
                            "depth_max_mm": float(finite.max() * 1000.0) if finite.size else None,
                            "difference_metrics": difference_metrics,
                        })
            for annotator in [*rgb_annotators, *semantic_annotators, *depth_annotators]:
                annotator.detach()
            for product in products:
                product.destroy()
            stage.RemovePrim(scene_dynamic_root)

        split_counts = {split: sum(row["split"] == split for row in rows) for split in ("training", "development")}
        expected_observation_count = len(scenes) * len(selected_targets) * 3 * len(selected_variants)
        if len(rows) != expected_observation_count:
            raise RuntimeError("shard observation inventory mismatch")
        normalization_summary = {}
        for variant_id in sorted({row["variant_id"] for row in rows}):
            selected = [row["difference_metrics"] for row in rows if row["variant_id"] == variant_id]
            normalization_summary[variant_id] = {
                "count": len(selected),
                "median_self_crop_difference": float(np.median([
                    row["self_crop_normalized_mean_absolute_difference"] for row in selected
                ])),
                "median_context_difference": float(np.median([
                    row["context_normalized_mean_absolute_difference"] for row in selected
                ])),
                "minimum_self_to_context_signal_ratio": min(
                    row["self_to_context_signal_ratio"] for row in selected
                ),
            }
        core = {
            "schema": MANIFEST_SCHEMA,
            "scope": "SYNTHETIC_ISAAC_REFERENCE_PAIR_SHARD_NO_QUALIFICATION",
            "fixture_file_sha256": sha256_bytes(fixture_bytes),
            "fixture_bundle_sha256": fixture["bundle_sha256"],
            "v5_file_sha256": fixture["v5_file_sha256"],
            "complete_campaign": False,
            "split": split,
            "scene_count": len(scenes), "observation_count": len(rows),
            "reference_count": len(scenes) * len(selected_targets) * 3,
            "scene_shard": {"start": scene_start, "count": len(scenes)},
            "target_shard": {"start": target_start, "count": len(selected_targets)},
            "selected_scene_indices": scene_indices,
            "selected_target_indices": target_indices,
            "selected_variant_ids": variant_ids,
            "raw_rgb_retained": retain_raw_rgb,
            "split_counts": split_counts, "observations": rows,
            "normalization_summary": normalization_summary,
            "candidate_input_contract": {
                "local_resolution": [96, 96],
                "context_resolution": [192, 192],
                "rgb_truth_masks_excluded_from_model_inputs": True,
                "safe_region_mask_is_calibrated_target_geometry_projection": True,
                "arm_projection_source": "PERTURBED_READY_MEASURED_STATE_SURROGATE_NOT_SIMULATOR_TRUTH",
                "arm_projection_masks_are_analytic_fk_capsules": True,
                "simulator_truth_arm_masks_excluded": True,
            },
            "evaluation_observation_count": 0,
            "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
            "limitations": [
                "Synthetic Isaac renders do not establish physical or deployment qualification",
                "Image-quality sensor effects are deterministic render postprocesses over fresh Isaac frames",
                "This shard is incomplete until exact independent campaign admission",
                "No model was trained and evaluation remains absent",
                "Arm masks are analytic FK capsule projections from perturbed synthetic ready-state telemetry, not simulator segmentation truth or physical calibration",
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
    parser.add_argument("--split", choices=("training", "development"), required=True)
    parser.add_argument("--scene-start", type=int, default=0)
    parser.add_argument("--scene-count", type=int)
    parser.add_argument("--target-start", type=int, default=0)
    parser.add_argument("--target-count", type=int, default=75)
    parser.add_argument("--scene-index", type=int, action="append")
    parser.add_argument("--target-index", type=int, action="append")
    parser.add_argument("--variant-id", action="append")
    parser.add_argument("--retain-raw-rgb", action="store_true")
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = render(
            args.workspace, args.fixture, args.output_dir, args.status_output,
            args.split, args.scene_start, args.scene_count, args.target_start, args.target_count,
            scene_indices=args.scene_index, target_indices=args.target_index,
            variant_ids=args.variant_id, retain_raw_rgb=args.retain_raw_rgb,
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
