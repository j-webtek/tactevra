"""Bind the exact source image and warp rule for the frozen v2 campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v2"
SOURCE_SCHEMA = "rocell.fixed_fixture_practice_corpus.v1"
OUTPUT_SCHEMA = "tactevra.ai_residual_obstruction_renderer_contract.v1"
BASE_SAMPLE_ID = "hover_t__nominal"


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


def build(fixture_path: Path, source_manifest_path: Path) -> dict[str, Any]:
    fixture_path = fixture_path.resolve(strict=True)
    fixture = load_bound(fixture_path, FIXTURE_SCHEMA, "bundle_sha256")
    if fixture.get("images_generated") is not False or fixture.get("training_started") is not False or fixture.get("evaluation_group_present") is not False:
        raise ValueError("renderer contract requires the unopened v2 fixture")
    if fixture.get("hardware_writes") != 0 or fixture.get("physical_movements") != 0 or fixture.get("physical_authority") is not False:
        raise ValueError("v2 fixture claims effects or authority")

    source_manifest_path = source_manifest_path.resolve(strict=True)
    source_bytes = source_manifest_path.read_bytes()
    source = json.loads(source_bytes)
    if not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unsupported source corpus")
    source_core = {key: value for key, value in source.items() if key != "corpus_sha256"}
    if source.get("corpus_sha256") != sha256_bytes(canonical(source_core)):
        raise ValueError("source corpus canonical hash mismatch")
    if sha256_bytes(source_bytes) != fixture["source"]["manifest_file_sha256"] or source["corpus_sha256"] != fixture["source"]["corpus_sha256"]:
        raise ValueError("v2 fixture source binding mismatch")
    samples = [sample for sample in source.get("samples", []) if sample.get("sample_id") == BASE_SAMPLE_ID]
    if len(samples) != 1:
        raise ValueError("exact base scene sample is required")
    sample = samples[0]
    image_path = (source_manifest_path.parent / sample["image_path"]).resolve(strict=True)
    image_bytes = image_path.read_bytes()
    if sha256_bytes(image_bytes) != sample["image_sha256"]:
        raise ValueError("base scene image hash mismatch")
    ordered_targets = [(target["device"], target["target_id"]) for target in sample["targets"]]
    if len(ordered_targets) != fixture["split_policy"]["target_count_per_view"] or len(ordered_targets) != len(set(ordered_targets)):
        raise ValueError("base scene target catalog mismatch")

    core = {
        "schema": OUTPUT_SCHEMA,
        "scope": "SYNTHETIC_RENDERER_BINDING_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "source_manifest_file_sha256": sha256_bytes(source_bytes),
        "source_corpus_sha256": source["corpus_sha256"],
        "target_catalog_sha256": source["target_catalog_sha256"],
        "base_scene": {
            "sample_id": sample["sample_id"],
            "pose_id": sample["pose_id"],
            "image_path": sample["image_path"],
            "image_sha256": sample["image_sha256"],
            "image_bytes": sample["image_bytes"],
            "image_size_px": fixture["render_admission"]["image_size_px"],
            "ordered_target_identity_sha256": sha256_bytes(canonical(ordered_targets)),
            "target_count": len(ordered_targets),
        },
        "warp_policy": {
            "algorithm": "PLANAR_AFFINE_PRACTICE_V1",
            "center_px": [960.0, 540.0],
            "translation_px_per_mm_xy": [1.5, 1.5],
            "scale_per_mm_z": 0.0025,
            "image_rotation_from_rpy": {"roll_coefficient": 0.25, "pitch_coefficient": 0.0, "yaw_coefficient": 1.0},
            "translation_from_rpy_px": {"x_from_pitch": 0.75, "y_from_roll": -0.5},
            "resampling": "BICUBIC",
            "border_fill_rgb": [205, 205, 200],
            "target_geometry_uses_same_affine": True,
        },
        "raster_policy": {
            "output_format": "PNG",
            "png_compress_level": 9,
            "color_mode": "RGB",
            "mask_mode": "L",
            "safe_region_rasterization": "PIL_POLYGON_INTEGER_PIXEL_CENTER",
            "overlap_definition": "INTERSECTION_PIXELS_DIVIDED_BY_SAFE_REGION_PIXELS",
            "changed_pixel_definition": "ANY_RGB_CHANNEL_DIFFERS_FROM_PAIRED_CLEAR_CROP",
            "seed_derivation": "SHA256_OBSERVATION_ID_FIRST_64_BITS",
        },
        "admission": fixture["render_admission"],
        "evaluation_group_present": False,
        "images_generated": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The planar affine warp is a deterministic synthetic approximation, not a calibrated 3D camera render",
            "The exact source image has simplified target surfaces and an unmeasured camera",
            "Passing renderer admission cannot qualify the model, camera, deployment, or physical execution",
        ],
    }
    return {**core, "contract_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.fixture, args.source_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"schema": result["schema"], "contract_sha256": result["contract_sha256"], "base_sample": result["base_scene"]["sample_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
