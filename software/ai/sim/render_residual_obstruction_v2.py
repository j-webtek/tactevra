"""Render and verify the frozen residual-obstruction v2 crop campaign."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import __version__ as PILLOW_VERSION
from PIL import Image, ImageDraw, ImageFilter


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v2"
CONTRACT_SCHEMA = "tactevra.ai_residual_obstruction_renderer_contract.v1"
SOURCE_SCHEMA = "rocell.fixed_fixture_practice_corpus.v1"
DATASET_SCHEMA = "tactevra.ai_residual_obstruction_rendered_dataset.v2"
RECEIPT_SCHEMA = "tactevra.ai_residual_obstruction_render_receipt.v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_bound(path: Path, schema: str, hash_field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise ValueError(f"unsupported schema: {path}")
    claimed = payload.get(hash_field)
    core = {key: value for key, value in payload.items() if key != hash_field}
    if claimed != sha256_bytes(canonical(core)):
        raise ValueError(f"canonical hash mismatch: {path}")
    return payload


def _seed(identity: str) -> int:
    return int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big")


def affine_matrix(view: dict[str, Any], policy: dict[str, Any]) -> np.ndarray:
    tx, ty, tz = (float(value) for value in view["camera_translation_mm"])
    roll, pitch, yaw = (float(value) for value in view["camera_rotation_rpy_deg"])
    center_x, center_y = (float(value) for value in policy["center_px"])
    px_x, px_y = (float(value) for value in policy["translation_px_per_mm_xy"])
    rotation_rule = policy["image_rotation_from_rpy"]
    angle = math.radians(
        roll * float(rotation_rule["roll_coefficient"])
        + pitch * float(rotation_rule["pitch_coefficient"])
        + yaw * float(rotation_rule["yaw_coefficient"])
    )
    scale = 1.0 + tz * float(policy["scale_per_mm_z"])
    rpy_translation = policy["translation_from_rpy_px"]
    destination_x = tx * px_x + pitch * float(rpy_translation["x_from_pitch"])
    destination_y = ty * px_y + roll * float(rpy_translation["y_from_roll"])
    cosine, sine = math.cos(angle) * scale, math.sin(angle) * scale
    to_origin = np.asarray([[1.0, 0.0, -center_x], [0.0, 1.0, -center_y], [0.0, 0.0, 1.0]])
    rotate = np.asarray([[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]])
    to_destination = np.asarray([[1.0, 0.0, center_x + destination_x], [0.0, 1.0, center_y + destination_y], [0.0, 0.0, 1.0]])
    return to_destination @ rotate @ to_origin


def transform_points(points: list[list[float]], matrix: np.ndarray) -> list[list[float]]:
    output = []
    for x, y in points:
        transformed = matrix @ np.asarray([float(x), float(y), 1.0])
        output.append([float(transformed[0]), float(transformed[1])])
    return output


def warp_image(image: Image.Image, matrix: np.ndarray, contract: dict[str, Any]) -> Image.Image:
    inverse = np.linalg.inv(matrix)
    coefficients = tuple(float(value) for value in inverse[:2, :].reshape(-1))
    size = tuple(int(value) for value in contract["base_scene"]["image_size_px"])
    fill = tuple(int(value) for value in contract["warp_policy"]["border_fill_rgb"])
    return image.transform(size, Image.Transform.AFFINE, coefficients, Image.Resampling.BICUBIC, fillcolor=fill)


def apply_appearance(image: Image.Image, appearance: dict[str, Any], identity: str) -> Image.Image:
    transform = appearance["transform"]
    kind = transform["kind"]
    if kind == "NEUTRAL":
        return image.copy()
    array = np.asarray(image, dtype=np.float32)
    if kind == "GAIN_GAMMA":
        normalized = np.clip(array / 255.0 * float(transform["gain"]), 0.0, 1.0)
        array = np.power(normalized, float(transform["gamma"])) * 255.0
    elif kind == "COLOR_MATRIX":
        array *= np.asarray(transform["rgb_gain"], dtype=np.float32)[None, None, :]
    elif kind == "DIRECTIONAL_FALLOFF":
        minimum = float(transform["minimum_gain"])
        if transform["axis"] == "X":
            gain = np.linspace(minimum, 1.0, array.shape[1], dtype=np.float32)[None, :, None]
        else:
            gain = np.linspace(minimum, 1.0, array.shape[0], dtype=np.float32)[:, None, None]
        array *= gain
    elif kind == "SEEDED_SENSOR_NOISE":
        rng = np.random.default_rng(_seed(identity))
        array += rng.normal(0.0, float(transform["sigma_8bit"]), size=array.shape)
    else:
        raise ValueError(f"unknown appearance transform: {kind}")
    return Image.fromarray(np.clip(np.rint(array), 0, 255).astype(np.uint8), mode="RGB")


def crop_target(image: Image.Image, polygon: list[list[float]], margin: float, size: tuple[int, int]) -> tuple[Image.Image, list[tuple[float, float]]]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    center_x, center_y = sum(xs) / len(xs), sum(ys) / len(ys)
    side = max(max(xs) - min(xs), max(ys) - min(ys), 1.0) * margin
    box = (center_x - side / 2, center_y - side / 2, center_x + side / 2, center_y + side / 2)
    crop = image.crop(box).resize(size, Image.Resampling.BICUBIC).convert("RGB")
    local = [
        ((x - box[0]) * size[0] / side, (y - box[1]) * size[1] / side)
        for x, y in polygon
    ]
    return crop, local


def polygon_mask(size: tuple[int, int], polygon: list[tuple[float, float]]) -> np.ndarray:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    return np.asarray(mask) > 0


def _exact_overlap_mask(target_mask: np.ndarray, fraction: float, identity: str, mode: str) -> np.ndarray:
    ys, xs = np.nonzero(target_mask)
    count = max(1, min(len(xs), round(len(xs) * fraction)))
    rng = np.random.default_rng(_seed(identity))
    angle = rng.uniform(-math.pi, math.pi)
    projection = xs * math.cos(angle) + ys * math.sin(angle)
    if mode == "CENTER":
        cx, cy = float(np.mean(xs)), float(np.mean(ys))
        order = np.argsort((xs - cx) ** 2 + (ys - cy) ** 2)
    elif mode == "RADIAL":
        anchor_x, anchor_y = rng.uniform(0, target_mask.shape[1]), rng.uniform(0, target_mask.shape[0])
        order = np.argsort((xs - anchor_x) ** 2 + (ys - anchor_y) ** 2)
    elif mode == "LINE":
        center = float(np.median(projection))
        order = np.argsort(np.abs(projection - center))
    else:
        order = np.argsort(projection)
    selected = order[:count]
    mask = np.zeros_like(target_mask)
    mask[ys[selected], xs[selected]] = True
    return mask


def _overlay_mask(crop: Image.Image, mask: np.ndarray, color: tuple[int, int, int]) -> Image.Image:
    array = np.asarray(crop).copy()
    array[mask] = np.asarray(color, dtype=np.uint8)
    return Image.fromarray(array, mode="RGB")


def render_variant(clear: Image.Image, target_mask: np.ndarray, variant: dict[str, Any], identity: str) -> tuple[Image.Image, np.ndarray | None]:
    kind = variant["render_spec"]["kind"]
    spec = variant["render_spec"]
    size = clear.size
    if kind == "IDENTITY":
        return clear.copy(), None
    if kind == "ADJACENT_DISTRACTOR":
        mask_image = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask_image)
        y0, y1 = round(size[1] * 0.30), round(size[1] * 0.70)
        if spec["side"] == "LEFT":
            box = (3, y0, 23, y1)
        else:
            box = (size[0] - 24, y0, size[0] - 4, y1)
        draw.rounded_rectangle(box, radius=4, fill=255)
        mask = np.asarray(mask_image) > 0
        if np.any(mask & target_mask):
            raise ValueError(f"adjacent distractor overlaps target: {identity}")
        shade = 30 + _seed(identity) % 35
        return _overlay_mask(clear, mask, (shade, shade + 6, shade + 12)), mask
    if "overlap_range" in spec:
        lower, upper = (float(value) for value in spec["overlap_range"])
        desired = (lower + upper) / 2
        if kind == "CURVED_CABLE":
            mask = _exact_overlap_mask(target_mask, desired, identity, "LINE")
            color = (18, 22, 27)
        elif kind == "DARK_TOOL_POLYGON":
            mask = _exact_overlap_mask(target_mask, desired, identity, "CENTER" if spec["placement"] == "CENTER" else "EDGE")
            color = (25, 28, 33)
        elif kind == "ARTICULATED_HAND_PROXY":
            mask = _exact_overlap_mask(target_mask, desired, identity, "RADIAL")
            color = (198, 139, 108)
        elif kind == "FOREIGN_OBJECT_POLYGON":
            mask = _exact_overlap_mask(target_mask, desired, identity, "RADIAL")
            color = (183, 66, 48)
        else:
            raise ValueError(f"overlap range on unsupported variant: {kind}")
        return _overlay_mask(clear, mask, color), mask
    if kind == "LOCALIZED_GLARE":
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        rng = np.random.default_rng(_seed(identity))
        alpha = int(rng.integers(int(spec["alpha_range"][0]), int(spec["alpha_range"][1]) + 1))
        draw.ellipse((18, 26, size[0] - 18, size[1] - 26), fill=(255, 255, 245, alpha))
        layer = layer.filter(ImageFilter.GaussianBlur(5))
        return Image.alpha_composite(clear.convert("RGBA"), layer).convert("RGB"), None
    if kind == "DEFOCUS":
        return clear.filter(ImageFilter.GaussianBlur(float(spec["blur_radius_px"]))), None
    if kind == "JPEG_ROUNDTRIP":
        buffer = io.BytesIO()
        clear.save(buffer, format="JPEG", quality=int(spec["quality"]), optimize=False, progressive=False)
        return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB"), None
    if kind == "LINEAR_MOTION_BLUR":
        length = int(spec["length_px"])
        shifted = [np.asarray(clear.transform(size, Image.Transform.AFFINE, (1, 0, offset, 0, 1, 0), Image.Resampling.BILINEAR), dtype=np.float32) for offset in range(-(length // 2), length // 2 + 1)]
        return Image.fromarray(np.rint(np.mean(shifted, axis=0)).astype(np.uint8), mode="RGB"), None
    raise ValueError(f"unknown variant kind: {kind}")


def render(fixture_path: Path, contract_path: Path, source_manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    fixture_path = fixture_path.resolve(strict=True)
    contract_path = contract_path.resolve(strict=True)
    source_manifest_path = source_manifest_path.resolve(strict=True)
    fixture = load_bound(fixture_path, FIXTURE_SCHEMA, "bundle_sha256")
    contract = load_bound(contract_path, CONTRACT_SCHEMA, "contract_sha256")
    if contract["fixture_file_sha256"] != sha256_bytes(fixture_path.read_bytes()) or contract["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
        raise ValueError("renderer contract fixture binding mismatch")
    source_bytes = source_manifest_path.read_bytes()
    if sha256_bytes(source_bytes) != contract["source_manifest_file_sha256"]:
        raise ValueError("renderer source manifest mismatch")
    source = json.loads(source_bytes)
    if source.get("schema") != SOURCE_SCHEMA or source.get("corpus_sha256") != contract["source_corpus_sha256"]:
        raise ValueError("renderer source corpus mismatch")
    sample = next((item for item in source["samples"] if item["sample_id"] == contract["base_scene"]["sample_id"]), None)
    if sample is None:
        raise ValueError("renderer base sample missing")
    base_path = (source_manifest_path.parent / sample["image_path"]).resolve(strict=True)
    if sha256_bytes(base_path.read_bytes()) != contract["base_scene"]["image_sha256"]:
        raise ValueError("renderer base image changed")
    if output_dir.exists():
        raise FileExistsError(f"refusing existing output directory: {output_dir}")
    output_dir.mkdir(parents=True)

    base = Image.open(base_path).convert("RGB")
    variants = fixture["variants"]
    appearances = {row["appearance_id"]: row for row in fixture["appearance_groups"]}
    entries: list[dict[str, Any]] = []
    observed_hashes: dict[str, str] = {}
    changed_pixel_minimum = int(contract["admission"]["adjacent_distractor_minimum_changed_pixels"])
    try:
        for view in fixture["view_groups"]:
            matrix = affine_matrix(view, contract["warp_policy"])
            warped = warp_image(base, matrix, contract)
            split_appearances = [row for row in appearances.values() if row["split"] == view["split"]]
            transformed_targets = [
                {**target, "safe_polygon_px": transform_points(target["safe_polygon_px"], matrix)}
                for target in sample["targets"]
            ]
            for appearance in split_appearances:
                image = apply_appearance(warped, appearance, f"{view['view_id']}:{appearance['appearance_id']}")
                for target in transformed_targets:
                    clear, local_polygon = crop_target(
                        image, target["safe_polygon_px"], float(contract["admission"]["crop_margin_fraction"]),
                        tuple(int(value) for value in contract["admission"]["target_crop_size_px"]),
                    )
                    target_mask = polygon_mask(clear.size, local_polygon)
                    if not np.any(target_mask):
                        raise ValueError("target safe region rasterized empty")
                    clear_array = np.asarray(clear)
                    group_hashes: set[str] = set()
                    for variant in variants:
                        identity = f"residual-v2-{view['view_id']}-{appearance['appearance_id']}-{target['device']}-{target['target_id']}-{variant['variant_id']}"
                        rendered, obstruction_mask = render_variant(clear, target_mask, variant, identity)
                        array = np.asarray(rendered)
                        changed_pixels = int(np.sum(np.any(array != clear_array, axis=2)))
                        overlap = None
                        if obstruction_mask is not None:
                            overlap = float(np.sum(obstruction_mask & target_mask) / np.sum(target_mask))
                        if variant["render_spec"]["kind"] == "ADJACENT_DISTRACTOR":
                            if changed_pixels < changed_pixel_minimum or overlap != 0.0:
                                raise ValueError(f"adjacent distractor admission failed: {identity}")
                        if "overlap_range" in variant["render_spec"]:
                            lower, upper = variant["render_spec"]["overlap_range"]
                            if overlap is None or not float(lower) <= overlap <= float(upper):
                                raise ValueError(f"obstruction overlap admission failed: {identity}")
                        relative = Path(view["split"]) / view["view_id"] / appearance["appearance_id"] / f"{identity}.png"
                        destination = output_dir / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        rendered.save(destination, format="PNG", compress_level=int(contract["raster_policy"]["png_compress_level"]), optimize=False)
                        payload = destination.read_bytes()
                        digest = sha256_bytes(payload)
                        if digest in group_hashes:
                            raise ValueError(f"duplicate bytes within target group: {identity}")
                        group_hashes.add(digest)
                        if digest in observed_hashes:
                            raise ValueError(
                                f"duplicate observation bytes: {identity} duplicates "
                                f"{observed_hashes[digest]}"
                            )
                        observed_hashes[digest] = identity
                        entries.append({
                            "path": relative.as_posix(), "sha256": digest, "bytes": len(payload),
                            "observation_id": identity, "split": view["split"], "view_id": view["view_id"],
                            "appearance_id": appearance["appearance_id"], "device": target["device"],
                            "target_id": target["target_id"], "variant_id": variant["variant_id"],
                            "expected_decision": variant["expected_decision"], "residual_obstruction": variant["residual_obstruction"],
                            "changed_pixels_from_clear": changed_pixels, "safe_region_overlap": overlap,
                            "truth_mask_used_as_model_input": False, "runtime_geometry_mask_used_as_model_input": False,
                        })
    finally:
        base.close()

    expected = fixture["split_policy"]["training_observation_count"] + fixture["split_policy"]["development_observation_count"]
    if len(entries) != expected:
        raise ValueError(f"rendered observation count mismatch: {len(entries)} != {expected}")
    core = {
        "schema": DATASET_SCHEMA,
        "scope": "SYNTHETIC_RENDERED_CROPS_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "contract_file_sha256": sha256_bytes(contract_path.read_bytes()),
        "contract_sha256": contract["contract_sha256"],
        "source_manifest_file_sha256": sha256_bytes(source_bytes),
        "base_image_sha256": contract["base_scene"]["image_sha256"],
        "files": entries,
        "file_count": len(entries),
        "training_count": sum(entry["split"] == "training" for entry in entries),
        "development_count": sum(entry["split"] == "development" for entry in entries),
        "evaluation_count": 0,
        "inventory_sha256": sha256_bytes(canonical(entries)),
        "unique_file_sha256_count": len({entry["sha256"] for entry in entries}),
        "renderer": {"pillow_version": PILLOW_VERSION, "numpy_version": np.__version__},
        "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
        "limitations": [
            "All crops derive from one simplified synthetic base scene through deterministic pixel-domain transformations",
            "Renderer admission proves internal contract conformance, not physical realism or model accuracy",
            "No evaluation images, physical evidence, or execution authority are present",
        ],
    }
    manifest = {**core, "dataset_sha256": sha256_bytes(canonical(core))}
    (output_dir / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    return manifest


def verify(fixture_path: Path, contract_path: Path, dataset_dir: Path) -> dict[str, Any]:
    fixture = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    contract = load_bound(contract_path.resolve(strict=True), CONTRACT_SCHEMA, "contract_sha256")
    manifest = load_bound(dataset_dir.resolve(strict=True) / "manifest.json", DATASET_SCHEMA, "dataset_sha256")
    if manifest["fixture_bundle_sha256"] != fixture["bundle_sha256"] or manifest["contract_sha256"] != contract["contract_sha256"]:
        raise ValueError("rendered dataset binding mismatch")
    if manifest.get("hardware_writes") != 0 or manifest.get("physical_movements") != 0 or manifest.get("physical_authority") is not False:
        raise ValueError("rendered dataset claims effects or authority")
    entries = manifest["files"]
    if manifest["file_count"] != len(entries) or manifest["inventory_sha256"] != sha256_bytes(canonical(entries)):
        raise ValueError("rendered dataset inventory mismatch")
    paths: set[str] = set()
    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in paths:
            raise ValueError("unsafe or duplicate rendered dataset path")
        paths.add(relative.as_posix())
        path = (dataset_dir / relative).resolve(strict=True)
        if dataset_dir.resolve() not in path.parents or path.is_symlink() or not path.is_file():
            raise ValueError("rendered dataset path is not a contained regular file")
        payload = path.read_bytes()
        if len(payload) != entry["bytes"] or sha256_bytes(payload) != entry["sha256"]:
            raise ValueError(f"rendered dataset file changed: {entry['path']}")
        with Image.open(path) as image:
            if image.size != tuple(contract["admission"]["target_crop_size_px"]) or image.mode != "RGB":
                raise ValueError("rendered dataset image contract mismatch")
        if entry["truth_mask_used_as_model_input"] is not False or entry["runtime_geometry_mask_used_as_model_input"] is not False:
            raise ValueError("rendered dataset exposes prohibited masks")
    actual = {path.relative_to(dataset_dir).as_posix() for path in dataset_dir.rglob("*") if path.is_file() and path.name != "manifest.json"}
    if actual != paths:
        raise ValueError("rendered dataset contains missing or extra files")
    return manifest


def build_receipt(fixture_path: Path, contract_path: Path, dataset_dir: Path) -> dict[str, Any]:
    manifest = verify(fixture_path, contract_path, dataset_dir)
    manifest_path = dataset_dir.resolve(strict=True) / "manifest.json"
    variants: list[dict[str, Any]] = []
    for variant_id in sorted({entry["variant_id"] for entry in manifest["files"]}):
        rows = [entry for entry in manifest["files"] if entry["variant_id"] == variant_id]
        overlaps = [float(entry["safe_region_overlap"]) for entry in rows if entry["safe_region_overlap"] is not None]
        variants.append({
            "variant_id": variant_id,
            "observation_count": len(rows),
            "changed_pixels_minimum": min(int(entry["changed_pixels_from_clear"]) for entry in rows),
            "changed_pixels_maximum": max(int(entry["changed_pixels_from_clear"]) for entry in rows),
            "safe_region_overlap_minimum": min(overlaps) if overlaps else None,
            "safe_region_overlap_maximum": max(overlaps) if overlaps else None,
        })
    core = {
        "schema": RECEIPT_SCHEMA,
        "scope": "SYNTHETIC_RENDERED_CROPS_NO_QUALIFICATION",
        "dataset_manifest_file_sha256": sha256_bytes(manifest_path.read_bytes()),
        "dataset_sha256": manifest["dataset_sha256"],
        "inventory_sha256": manifest["inventory_sha256"],
        "fixture_file_sha256": manifest["fixture_file_sha256"],
        "fixture_bundle_sha256": manifest["fixture_bundle_sha256"],
        "contract_file_sha256": manifest["contract_file_sha256"],
        "contract_sha256": manifest["contract_sha256"],
        "source_manifest_file_sha256": manifest["source_manifest_file_sha256"],
        "base_image_sha256": manifest["base_image_sha256"],
        "file_count": manifest["file_count"],
        "unique_file_sha256_count": manifest["unique_file_sha256_count"],
        "total_file_bytes": sum(int(entry["bytes"]) for entry in manifest["files"]),
        "training_count": manifest["training_count"],
        "development_count": manifest["development_count"],
        "evaluation_count": manifest["evaluation_count"],
        "expected_visible_count": sum(entry["expected_decision"] == "VISIBLE" for entry in manifest["files"]),
        "expected_abstain_count": sum(entry["expected_decision"] == "ABSTAIN" for entry in manifest["files"]),
        "variant_metrics": variants,
        "renderer": manifest["renderer"],
        "verification": {
            "all_files_present": True,
            "all_file_hashes_match": True,
            "all_images_match_contract": True,
            "no_extra_files": True,
            "no_prohibited_model_input_masks": True,
            "global_duplicate_file_count": manifest["file_count"] - manifest["unique_file_sha256_count"],
        },
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": manifest["limitations"],
    }
    return {**core, "receipt_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--fixture", type=Path, required=True)
    render_parser.add_argument("--contract", type=Path, required=True)
    render_parser.add_argument("--source-manifest", type=Path, required=True)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--fixture", type=Path, required=True)
    verify_parser.add_argument("--contract", type=Path, required=True)
    verify_parser.add_argument("--dataset-dir", type=Path, required=True)
    receipt_parser = subparsers.add_parser("receipt")
    receipt_parser.add_argument("--fixture", type=Path, required=True)
    receipt_parser.add_argument("--contract", type=Path, required=True)
    receipt_parser.add_argument("--dataset-dir", type=Path, required=True)
    receipt_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "render":
        result = render(args.fixture, args.contract, args.source_manifest, args.output_dir)
    elif args.command == "verify":
        result = verify(args.fixture, args.contract, args.dataset_dir)
    else:
        result = build_receipt(args.fixture, args.contract, args.dataset_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical(result) + b"\n")
    summary = {"schema": result["schema"]}
    for field in ("dataset_sha256", "receipt_sha256", "file_count", "unique_file_sha256_count"):
        if field in result:
            summary[field] = result[field]
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
