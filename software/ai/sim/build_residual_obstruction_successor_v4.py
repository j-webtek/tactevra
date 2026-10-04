"""Freeze the reference-comparison residual-v4 campaign before rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_SCHEMA = "rocell.fixed_fixture_practice_corpus.v1"
AUDIT_SCHEMA = "tactevra.ai_residual_obstruction_v3_training_audit.v1"
REVIEW_SCHEMA = "tactevra.ai_residual_obstruction_v3_training_visual_review.v1"
OUTPUT_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v4"


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


def _scenes(split: str, count: int, seed_start: int, render_phase: str) -> list[dict[str, Any]]:
    return [
        {
            "scene_id": f"residual_v4_{split}_scene_{index + 1:02d}",
            "split": split,
            "isaac_seed": seed_start + index,
            "render_phase": render_phase,
            "fresh_render_required": True,
            "source_image_reuse_prohibited": True,
            "commissioned_park_pose": "PARKED_OBSERVATION_POSE_V1",
            "camera_pose_jitter_mm": [3.0, 3.0, 1.5],
            "camera_rotation_jitter_deg": [0.8, 0.8, 1.0],
            "fixture_surface_randomization": "BOUNDED_PHYSICALLY_BASED",
        }
        for index in range(count)
    ]


def _appearances(split: str, seed_start: int) -> list[dict[str, Any]]:
    profiles = [
        ("neutral", [4200, 5000], [450.0, 650.0], [0.8, 1.2]),
        ("warm_side", [3000, 3900], [300.0, 520.0], [1.1, 1.8]),
        ("dim_ambient", [3600, 5200], [120.0, 280.0], [0.7, 1.4]),
        ("cool_sensor", [5600, 7200], [350.0, 600.0], [0.9, 1.5]),
    ]
    return [
        {
            "appearance_id": f"v4_{split}_{name}_{index + 1:02d}",
            "split": split,
            "lighting_seed": seed_start + index,
            "family": name.upper(),
            "color_temperature_k": temperature,
            "illuminance_lux": illuminance,
            "exposure_multiplier": exposure,
            "paired_across_variants": True,
        }
        for index, (name, temperature, illuminance, exposure) in enumerate(profiles)
    ]


def _variants() -> list[dict[str, Any]]:
    return [
        {"variant_id": "clear", "decision": "VISIBLE", "family": "NONE"},
        {"variant_id": "adjacent_left", "decision": "VISIBLE", "family": "DISTRACTOR"},
        {"variant_id": "adjacent_right", "decision": "VISIBLE", "family": "DISTRACTOR"},
        {"variant_id": "cable_rubber", "decision": "ABSTAIN", "family": "CABLE"},
        {"variant_id": "cable_translucent", "decision": "ABSTAIN", "family": "CABLE"},
        {"variant_id": "tool_matte_edge", "decision": "ABSTAIN", "family": "TOOL"},
        {"variant_id": "tool_gloss_center", "decision": "ABSTAIN", "family": "TOOL"},
        {"variant_id": "foreign_object", "decision": "ABSTAIN", "family": "FOREIGN_OBJECT"},
        {"variant_id": "glare", "decision": "ABSTAIN", "family": "IMAGE_QUALITY"},
        {"variant_id": "defocus", "decision": "ABSTAIN", "family": "IMAGE_QUALITY"},
        {"variant_id": "motion_blur", "decision": "ABSTAIN", "family": "IMAGE_QUALITY"},
        {"variant_id": "compression", "decision": "ABSTAIN", "family": "IMAGE_QUALITY"},
    ]


def build(source_path: Path, audit_path: Path, review_path: Path) -> dict[str, Any]:
    source, source_bytes = load_bound(source_path, SOURCE_SCHEMA, "corpus_sha256")
    audit, audit_bytes = load_bound(audit_path, AUDIT_SCHEMA, "report_sha256")
    review, review_bytes = load_bound(review_path, REVIEW_SCHEMA, "review_sha256")
    authority = source.get("authority", {})
    if (
        authority.get("hardware_write_count") != 0
        or authority.get("physical_movement_count") != 0
        or authority.get("can_release_physical_gates") is not False
    ):
        raise ValueError("source corpus claims effects or authority")
    if audit["identity_geometry_baseline"]["pooled_training_auc"] != 0.5:
        raise ValueError("v4 requires the retained chance identity baseline")
    model = audit["model_training_diagnostics"]
    if model["locally_separable_target_count"] != 0 or model["target_count"] != 75:
        raise ValueError("v4 requires catalog-wide strict-margin failure")
    if audit["memorization_test"]["near_zero_loss_met"] is not False:
        raise ValueError("v4 requires the retained memorization failure")
    if review["source_report_sha256"] != audit["report_sha256"]:
        raise ValueError("visual review is not bound to the audit")
    if review["status"] != "PASS_WITH_LIMITATIONS":
        raise ValueError("v4 requires completed crop/label review")

    training_scenes = _scenes("training", 12, 19200, "TRAIN_AND_DEVELOPMENT_RENDER")
    development_scenes = _scenes("development", 8, 19300, "TRAIN_AND_DEVELOPMENT_RENDER")
    evaluation_scenes = _scenes("evaluation", 8, 19400, "AFTER_DEVELOPMENT_PASS_ONLY")
    appearances = [
        *_appearances("training", 19250),
        *_appearances("development", 19350),
        *_appearances("evaluation", 19450),
    ]
    variants = _variants()
    scenes_per_split = {"training": 12, "development": 8, "evaluation": 8}
    appearances_per_split = 4
    target_count = 75

    core = {
        "schema": OUTPUT_SCHEMA,
        "scope": "SYNTHETIC_ISAAC_REFERENCE_COMPARISON_PREDECLARATION_NO_QUALIFICATION",
        "source": {
            "practice_manifest_file_sha256": sha256_bytes(source_bytes),
            "practice_corpus_sha256": source["corpus_sha256"],
            "target_catalog_sha256": source["target_catalog_sha256"],
            "training_audit_file_sha256": sha256_bytes(audit_bytes),
            "training_audit_report_sha256": audit["report_sha256"],
            "visual_review_file_sha256": sha256_bytes(review_bytes),
            "visual_review_sha256": review["review_sha256"],
            "rejected_model_sha256": audit["model_file_sha256"],
        },
        "base_scenes": training_scenes + development_scenes + evaluation_scenes,
        "appearances": appearances,
        "variants": variants,
        "reference_contract": {
            "reference_kind": "CLEAR_TARGET_CROP_AT_COMMISSIONED_PARK_POSE",
            "one_reference_per_scene_and_target": True,
            "reference_variant": "clear",
            "reference_appearance": "SCENE_COMMISSIONING_NEUTRAL",
            "reference_must_precede_observation": True,
            "reference_and_observation_camera_transform_identical": True,
            "reference_rgb_reuse_within_scene_target_is_intentional": True,
            "observation_rgb_must_be_unique": True,
            "runtime_reference_source": "COMMISSIONING_CAPTURE_NOT_MODEL_GENERATED",
            "missing_or_stale_reference_decision": "ABSTAIN",
        },
        "split_policy": {
            "scene_ids_disjoint": True,
            "appearance_ids_disjoint": True,
            "lighting_seeds_disjoint": True,
            "reference_ids_disjoint": True,
            "training_scene_count": 12,
            "development_scene_count": 8,
            "evaluation_scene_count": 8,
            "training_pair_count": scenes_per_split["training"] * appearances_per_split * target_count * len(variants),
            "development_pair_count": scenes_per_split["development"] * appearances_per_split * target_count * len(variants),
            "planned_evaluation_pair_count": scenes_per_split["evaluation"] * appearances_per_split * target_count * len(variants),
            "evaluation_pairs_rendered": 0,
            "evaluation_render_requires_development_pass": True,
            "evaluation_is_single_use": True,
        },
        "render_admission": {
            "renderer": "ISAAC_SIM_3D",
            "fresh_full_frame_required_per_scene": True,
            "source_image_warp_prohibited": True,
            "truth_masks_retained_for_labels_only": True,
            "truth_masks_prohibited_as_model_input": True,
            "depth_retained_for_admission_only": True,
            "depth_prohibited_as_model_input": True,
            "fail_on_duplicate_observation_bytes": True,
            "allow_only_declared_reference_reuse": True,
            "exact_reference_observation_transform_binding_required": True,
        },
        "training_plan": {
            "algorithm": "spatial_reference_difference_cnn_v4",
            "model_inputs": ["REFERENCE_RGB", "OBSERVATION_RGB", "ABSOLUTE_RGB_DIFFERENCE"],
            "input_channels": 9,
            "input_size_px": [96, 96],
            "convolution_channels": [24, 48, 64],
            "spatial_pool_output": [6, 6],
            "global_average_pooling_prohibited": True,
            "normalization": "PER_TARGET_TRAINING_CLEAR_REFERENCE_STATISTICS_ONLY",
            "development_or_evaluation_statistics_prohibited": True,
            "epochs": 30,
            "batch_size": 128,
            "optimizer": "ADAMW",
            "learning_rate": 0.0003,
            "weight_decay": 0.0001,
            "seed": 19200,
            "sampling": "TARGET_LABEL_VARIANT_SCENE_AND_APPEARANCE_BALANCED",
            "threshold_candidates": [round(index / 100, 2) for index in range(5, 100, 5)],
        },
        "pretraining_gates": {
            "identity_geometry_baseline_auc_maximum": 0.55,
            "memorization_subset_count": 500,
            "memorization_loss_maximum": 0.01,
            "memorization_accuracy_minimum": 0.995,
            "full_training_prohibited_until_memorization_passes": True,
        },
        "development_gate": {
            "missed_obstruction_rate_upper": 0.02,
            "visible_false_stop_rate_upper": 0.06,
            "confidence_level": 0.95,
            "base_scene_cluster_bootstrap_resamples": 5000,
            "base_scene_cluster_bootstrap_seed": 19200,
            "minimum_per_target_auc": 0.95,
            "minimum_per_target_strict_margin": 0.05,
            "every_target_must_pass_auc_and_margin": True,
            "worst_appearance_must_pass": True,
            "worst_variant_family_must_pass": True,
            "point_and_cluster_upper_bounds_must_pass": True,
            "evaluation_must_remain_unopened": True,
        },
        "images_generated": False,
        "training_started": False,
        "development_opened": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This is a synthetic predeclaration and not physical or deployment qualification",
            "Synthetic clear references approximate a later retained commissioning capture",
            "The consumed v3 evidence motivates this design but cannot evaluate or select v4",
            "Evaluation identities are frozen now but their pixels remain unrendered until a development pass",
            "No controller command, motion policy, permit, transport, or physical authority is included",
        ],
    }
    return {**core, "bundle_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--training-audit", type=Path, required=True)
    parser.add_argument("--visual-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source_manifest, args.training_audit, args.visual_review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({
        "schema": result["schema"],
        "bundle_sha256": result["bundle_sha256"],
        "training_pairs": result["split_policy"]["training_pair_count"],
        "development_pairs": result["split_policy"]["development_pair_count"],
        "planned_evaluation_pairs": result["split_policy"]["planned_evaluation_pair_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
