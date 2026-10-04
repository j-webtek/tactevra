"""Freeze the residual-obstruction v3 Isaac campaign before rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_SCHEMA = "rocell.fixed_fixture_practice_corpus.v1"
DIAGNOSTIC_SCHEMA = "tactevra.ai_residual_obstruction_v2_diagnostic.v1"
OUTPUT_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v3"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_bound(path: Path, schema: str, hash_field: str) -> tuple[dict[str, Any], bytes]:
    payload_bytes = path.resolve(strict=True).read_bytes()
    payload = json.loads(payload_bytes)
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise ValueError(f"unsupported schema: {path}")
    claimed = payload.get(hash_field)
    core = {key: value for key, value in payload.items() if key != hash_field}
    if claimed != sha256_bytes(canonical(core)):
        raise ValueError(f"canonical hash mismatch: {path}")
    return payload, payload_bytes


def _scenes(split: str, count: int, seed_start: int) -> list[dict[str, Any]]:
    return [
        {
            "scene_id": f"residual_{split}_scene_{index + 1:02d}",
            "split": split,
            "isaac_seed": seed_start + index,
            "fresh_render_required": True,
            "source_image_reuse_prohibited": True,
            "camera_pose_jitter_mm": [6.0, 6.0, 3.0],
            "camera_rotation_jitter_deg": [1.5, 1.5, 2.0],
            "fixture_surface_randomization": "BOUNDED_PHYSICALLY_BASED",
        }
        for index in range(count)
    ]


def build(source_manifest_path: Path, diagnostic_path: Path) -> dict[str, Any]:
    source, source_bytes = load_bound(source_manifest_path, SOURCE_SCHEMA, "corpus_sha256")
    diagnostic, diagnostic_bytes = load_bound(diagnostic_path, DIAGNOSTIC_SCHEMA, "report_sha256")
    authority = source.get("authority", {})
    if (
        authority.get("hardware_write_count") != 0
        or authority.get("physical_movement_count") != 0
        or authority.get("can_release_physical_gates") is not False
    ):
        raise ValueError("source corpus claims effects or authority")
    if source.get("camera_state") != "SYNTHETIC_UNMEASURED_ARM_CAMERA":
        raise ValueError("source camera state mismatch")
    if (
        diagnostic.get("checkpoint_changed") is not False
        or diagnostic.get("threshold_changed") is not False
        or diagnostic.get("evaluation_opened") is not False
    ):
        raise ValueError("diagnostic changed the rejected experiment")
    target_separation = diagnostic.get("target_separation", {})
    if target_separation.get("nonseparable_count") != 75:
        raise ValueError("successor requires exact catalog-wide overlap evidence")
    findings = {row.get("finding_id") for row in diagnostic.get("findings", [])}
    required_findings = {
        "appearance_transfer_failure",
        "weak_cable_tool_compression_separation",
        "catalog_wide_overlap",
    }
    if not required_findings <= findings:
        raise ValueError("successor requires all frozen v2 findings")

    training_scenes = _scenes("training", 8, 19030)
    development_scenes = _scenes("development", 4, 19130)
    variants = [
        {"variant_id": "clear", "decision": "VISIBLE", "family": "NONE", "geometry": {"kind": "NONE"}},
        {"variant_id": "adjacent_left", "decision": "VISIBLE", "family": "DISTRACTOR", "geometry": {"kind": "MESH_DISTRACTOR", "side": "LEFT", "safe_overlap": 0.0}},
        {"variant_id": "adjacent_right", "decision": "VISIBLE", "family": "DISTRACTOR", "geometry": {"kind": "MESH_DISTRACTOR", "side": "RIGHT", "safe_overlap": 0.0}},
        {"variant_id": "cable_rubber", "decision": "ABSTAIN", "family": "CABLE", "geometry": {"kind": "SWEPT_CURVE_MESH", "material": "RUBBER_MATTE", "diameter_mm": [2.0, 7.0], "depth_offset_mm": [-8.0, 18.0], "safe_overlap": [0.2, 0.75]}},
        {"variant_id": "cable_translucent", "decision": "ABSTAIN", "family": "CABLE", "geometry": {"kind": "SWEPT_CURVE_MESH", "material": "POLYMER_TRANSLUCENT", "opacity": [0.45, 0.8], "diameter_mm": [2.0, 7.0], "depth_offset_mm": [-8.0, 18.0], "safe_overlap": [0.2, 0.75]}},
        {"variant_id": "tool_matte_edge", "decision": "ABSTAIN", "family": "TOOL", "geometry": {"kind": "BEVELED_TOOL_MESH", "material": "METAL_MATTE", "placement": "EDGE", "depth_offset_mm": [-12.0, 20.0], "safe_overlap": [0.25, 0.5]}},
        {"variant_id": "tool_gloss_center", "decision": "ABSTAIN", "family": "TOOL", "geometry": {"kind": "BEVELED_TOOL_MESH", "material": "METAL_GLOSS", "placement": "CENTER", "depth_offset_mm": [-12.0, 20.0], "safe_overlap": [0.5, 0.8]}},
        {"variant_id": "foreign_object", "decision": "ABSTAIN", "family": "FOREIGN_OBJECT", "geometry": {"kind": "ROUNDED_SOLID_MESH", "material_set": ["PLASTIC_MATTE", "FABRIC", "METAL_GLOSS"], "depth_offset_mm": [-10.0, 22.0], "safe_overlap": [0.35, 0.7]}},
        {"variant_id": "glare", "decision": "ABSTAIN", "family": "IMAGE_QUALITY", "geometry": {"kind": "AREA_LIGHT_REFLECTION", "roughness": [0.05, 0.35], "safe_overlap": [0.3, 0.8]}},
        {"variant_id": "defocus", "decision": "ABSTAIN", "family": "IMAGE_QUALITY", "geometry": {"kind": "CAMERA_DEFOCUS", "focus_error_mm": [12.0, 35.0]}},
        {"variant_id": "motion_blur", "decision": "ABSTAIN", "family": "IMAGE_QUALITY", "geometry": {"kind": "EXPOSURE_MOTION", "pixel_extent": [7.0, 15.0]}},
        {"variant_id": "compression", "decision": "ABSTAIN", "family": "IMAGE_QUALITY", "geometry": {"kind": "ENCODE_ROUNDTRIP", "quality": [18, 42]}},
    ]
    appearances = [
        {"appearance_id": "neutral", "kind": "PHYSICALLY_BASED_LIGHTING", "paired_across_variants": True},
        {"appearance_id": "low_key", "kind": "PHYSICALLY_BASED_LIGHTING", "paired_across_variants": True},
        {"appearance_id": "high_key", "kind": "PHYSICALLY_BASED_LIGHTING", "paired_across_variants": True},
        {"appearance_id": "cool_sensor", "kind": "PHYSICALLY_BASED_LIGHTING_AND_SENSOR", "paired_across_variants": True},
    ]
    target_count = 75
    train_count = len(training_scenes) * len(appearances) * target_count * len(variants)
    dev_count = len(development_scenes) * len(appearances) * target_count * len(variants)
    core = {
        "schema": OUTPUT_SCHEMA,
        "scope": "SYNTHETIC_ISAAC_PREDECLARATION_NO_QUALIFICATION",
        "source": {
            "practice_manifest_file_sha256": sha256_bytes(source_bytes),
            "practice_corpus_sha256": source["corpus_sha256"],
            "target_catalog_sha256": source["target_catalog_sha256"],
            "diagnostic_file_sha256": sha256_bytes(diagnostic_bytes),
            "diagnostic_report_sha256": diagnostic["report_sha256"],
            "rejected_model_sha256": diagnostic["model_sha256"],
        },
        "base_scenes": training_scenes + development_scenes,
        "appearances": appearances,
        "variants": variants,
        "split_policy": {
            "base_scene_ids_disjoint": True,
            "minimum_independent_training_scenes": 8,
            "minimum_independent_development_scenes": 4,
            "training_observation_count": train_count,
            "development_observation_count": dev_count,
            "evaluation_observation_count": 0,
            "evaluation_group_present": False,
        },
        "render_admission": {
            "renderer": "ISAAC_SIM_3D",
            "fresh_full_frame_required_per_base_scene": True,
            "source_image_warp_prohibited": True,
            "rgb_is_only_model_input": True,
            "truth_masks_retained_for_labels_only": True,
            "truth_masks_prohibited_as_model_input": True,
            "depth_retained_for_admission_only": True,
            "depth_prohibited_as_model_input": True,
            "physically_based_material_required": True,
            "mesh_geometry_required_for_physical_obstructions": True,
            "safe_region_overlap_must_match_declared_range": True,
            "fail_on_duplicate_observation_bytes": True,
        },
        "training_plan": {
            "algorithm": "target_crop_residual_cnn_v3",
            "input_channels": ["RGB"],
            "input_size_px": [96, 96],
            "convolution_channels": [24, 48, 64],
            "normalization": "GROUP_NORM",
            "epochs": 24,
            "batch_size": 128,
            "optimizer": "ADAMW",
            "learning_rate": 0.0003,
            "weight_decay": 0.0001,
            "seed": 19030,
            "losses": {"classification": "BINARY_CROSS_ENTROPY", "appearance_consistency": "PAIRED_LOGIT_HUBER", "appearance_consistency_weight": 0.2},
            "sampling": "TARGET_LABEL_VARIANT_AND_BASE_SCENE_BALANCED",
            "threshold_candidates": [round(index / 100, 2) for index in range(5, 100, 5)],
        },
        "development_gate": {
            "missed_obstruction_rate_upper": 0.02,
            "visible_false_stop_rate_upper": 0.06,
            "confidence_level": 0.95,
            "base_scene_cluster_bootstrap_resamples": 4000,
            "base_scene_cluster_bootstrap_seed": 19030,
            "worst_appearance_must_pass": True,
            "worst_variant_family_must_pass": True,
            "minimum_target_local_separation_margin": 0.0,
            "every_target_margin_must_be_strictly_positive": True,
            "point_and_cluster_upper_bounds_must_pass": True,
            "evaluation_must_remain_unopened": True,
        },
        "images_generated": False,
        "training_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This fixture predeclares synthetic Isaac work and is not physical or deployment qualification",
            "The camera, materials, and obstruction meshes remain unmeasured until physical originals exist",
            "The consumed v2 development diagnosis may motivate this design but cannot evaluate or select v3",
            "No evaluation source, controller command, motion policy, permit, transport, or physical authority is included",
        ],
    }
    return {**core, "bundle_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source_manifest, args.diagnostic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({
        "schema": result["schema"],
        "bundle_sha256": result["bundle_sha256"],
        "training_observations": result["split_policy"]["training_observation_count"],
        "development_observations": result["split_policy"]["development_observation_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
