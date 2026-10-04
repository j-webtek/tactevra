"""Freeze residual-obstruction successor v2 before rendering or training."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SOURCE_SCHEMA = "rocell.fixed_fixture_practice_corpus.v1"
DIAGNOSTIC_SCHEMA = "tactevra.ai_residual_obstruction_development_diagnostic.v1"
OUTPUT_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v2"

TRAINING_VIEWS = (
    ("park_train_01", [-3.0, -2.0, 0.0], [0.4, -0.8, -1.2]),
    ("park_train_02", [3.0, -2.0, 1.0], [-0.4, 0.7, 1.1]),
    ("park_train_03", [-2.0, 2.0, -1.0], [0.8, 0.3, -0.6]),
    ("park_train_04", [2.0, 2.0, 0.0], [-0.7, -0.3, 0.7]),
    ("park_train_05", [0.0, -3.0, 2.0], [0.2, 1.0, 0.3]),
    ("park_train_06", [0.0, 3.0, -2.0], [-0.2, -1.0, -0.3]),
)
DEVELOPMENT_VIEWS = (
    ("park_development_01", [-4.0, 3.0, -1.0], [1.1, -0.5, -1.5]),
    ("park_development_02", [4.0, 3.0, 1.0], [-1.0, 0.6, 1.5]),
    ("park_development_03", [0.0, -4.0, 2.0], [0.5, 1.3, 0.0]),
)
TRAINING_APPEARANCES = (
    ("train_neutral", "NEUTRAL", {}),
    ("train_dim", "GAIN_GAMMA", {"gain": 0.62, "gamma": 1.08}),
    ("train_bright", "GAIN_GAMMA", {"gain": 1.32, "gamma": 0.94}),
    ("train_warm", "COLOR_MATRIX", {"rgb_gain": [1.12, 1.0, 0.82]}),
)
DEVELOPMENT_APPEARANCES = (
    ("development_cool", "COLOR_MATRIX", {"rgb_gain": [0.84, 1.0, 1.14]}),
    ("development_shadow", "DIRECTIONAL_FALLOFF", {"axis": "X", "minimum_gain": 0.58}),
    ("development_sensor_noise", "SEEDED_SENSOR_NOISE", {"sigma_8bit": 6.0}),
)
VARIANTS = (
    ("none_clear", "VISIBLE", "NONE", {"kind": "IDENTITY"}),
    ("adjacent_distractor_left", "VISIBLE", "NONE", {"kind": "ADJACENT_DISTRACTOR", "side": "LEFT", "safe_region_overlap": 0.0}),
    ("adjacent_distractor_right", "VISIBLE", "NONE", {"kind": "ADJACENT_DISTRACTOR", "side": "RIGHT", "safe_region_overlap": 0.0}),
    ("cable_thin", "ABSTAIN", "CABLE", {"kind": "CURVED_CABLE", "width_fraction": 0.08, "overlap_range": [0.20, 0.35]}),
    ("cable_medium", "ABSTAIN", "CABLE", {"kind": "CURVED_CABLE", "width_fraction": 0.14, "overlap_range": [0.35, 0.55]}),
    ("cable_thick", "ABSTAIN", "CABLE", {"kind": "CURVED_CABLE", "width_fraction": 0.22, "overlap_range": [0.55, 0.75]}),
    ("tool_edge", "ABSTAIN", "TOOL", {"kind": "DARK_TOOL_POLYGON", "placement": "EDGE", "overlap_range": [0.25, 0.45]}),
    ("tool_center", "ABSTAIN", "TOOL", {"kind": "DARK_TOOL_POLYGON", "placement": "CENTER", "overlap_range": [0.55, 0.80]}),
    ("hand_intrusion", "ABSTAIN", "HAND", {"kind": "ARTICULATED_HAND_PROXY", "overlap_range": [0.45, 0.75]}),
    ("foreign_object", "ABSTAIN", "FOREIGN_OBJECT", {"kind": "FOREIGN_OBJECT_POLYGON", "overlap_range": [0.35, 0.65]}),
    ("localized_glare", "ABSTAIN", "GLARE", {"kind": "LOCALIZED_GLARE", "alpha_range": [140, 220]}),
    ("degraded_blur_light", "ABSTAIN", "IMAGE_DEGRADED", {"kind": "DEFOCUS", "blur_radius_px": 2.5}),
    ("degraded_blur_heavy", "ABSTAIN", "IMAGE_DEGRADED", {"kind": "DEFOCUS", "blur_radius_px": 5.0}),
    ("degraded_compression", "ABSTAIN", "IMAGE_DEGRADED", {"kind": "JPEG_ROUNDTRIP", "quality": 24}),
    ("degraded_motion", "ABSTAIN", "IMAGE_DEGRADED", {"kind": "LINEAR_MOTION_BLUR", "length_px": 11}),
)


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


def _views(values: tuple[tuple[str, list[float], list[float]], ...], split: str) -> list[dict[str, Any]]:
    rows = []
    for identity, translation, rotation in values:
        if not all(math.isfinite(float(value)) for value in translation + rotation):
            raise ValueError("view perturbation must be finite")
        rows.append({
            "view_id": identity,
            "split": split,
            "camera_translation_mm": translation,
            "camera_rotation_rpy_deg": rotation,
            "parked_arm_state": "SYNTHETIC_PARKED_OBSERVATION_REFERENCE",
        })
    return rows


def _appearances(values: tuple[tuple[str, str, dict[str, Any]], ...], split: str) -> list[dict[str, Any]]:
    return [
        {"appearance_id": identity, "split": split, "transform": {"kind": kind, **parameters}}
        for identity, kind, parameters in values
    ]


def build(source_manifest_path: Path, diagnostic_path: Path) -> dict[str, Any]:
    source_manifest_path = source_manifest_path.resolve(strict=True)
    source_bytes = source_manifest_path.read_bytes()
    source = json.loads(source_bytes)
    if not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unsupported source corpus")
    source_core = {key: value for key, value in source.items() if key != "corpus_sha256"}
    if source.get("corpus_sha256") != sha256_bytes(canonical(source_core)):
        raise ValueError("source corpus canonical hash mismatch")
    authority = source.get("authority", {})
    if authority.get("hardware_write_count") != 0 or authority.get("physical_movement_count") != 0 or authority.get("can_release_physical_gates") is not False:
        raise ValueError("source corpus claims effects or authority")
    if source.get("target_catalog_sha256") is None or source.get("camera_state") != "SYNTHETIC_UNMEASURED_ARM_CAMERA":
        raise ValueError("source corpus identity mismatch")

    diagnostic_path = diagnostic_path.resolve(strict=True)
    diagnostic = load_bound(diagnostic_path, DIAGNOSTIC_SCHEMA, "report_sha256")
    if diagnostic.get("checkpoint_changed") is not False or diagnostic.get("threshold_changed") is not False or diagnostic.get("evaluation_opened") is not False:
        raise ValueError("diagnostic changed the rejected experiment")
    if diagnostic["target_separation"]["nonseparable_count"] != 75:
        raise ValueError("successor requires the exact 75-target failure evidence")
    if diagnostic["dataset_identity_diagnostics"]["byte_identical_clear_adjacent_pair_count"] != 75:
        raise ValueError("successor requires the exact duplicate-distractor evidence")

    views = _views(TRAINING_VIEWS, "training") + _views(DEVELOPMENT_VIEWS, "development")
    appearances = _appearances(TRAINING_APPEARANCES, "training") + _appearances(DEVELOPMENT_APPEARANCES, "development")
    view_ids = [row["view_id"] for row in views]
    appearance_ids = [row["appearance_id"] for row in appearances]
    if len(view_ids) != len(set(view_ids)) or len(appearance_ids) != len(set(appearance_ids)):
        raise ValueError("view and appearance identities must be unique")
    target_count = 75
    variant_count = len(VARIANTS)
    train_count = len(TRAINING_VIEWS) * len(TRAINING_APPEARANCES) * target_count * variant_count
    development_count = len(DEVELOPMENT_VIEWS) * len(DEVELOPMENT_APPEARANCES) * target_count * variant_count
    core = {
        "schema": OUTPUT_SCHEMA,
        "scope": "SYNTHETIC_SUCCESSOR_PREDECLARATION_NO_QUALIFICATION",
        "source": {
            "manifest_file_sha256": sha256_bytes(source_bytes),
            "corpus_sha256": source["corpus_sha256"],
            "generator_sha256": source["generator_sha256"],
            "target_catalog_sha256": source["target_catalog_sha256"],
            "camera_state": source["camera_state"],
            "diagnostic_file_sha256": sha256_bytes(diagnostic_path.read_bytes()),
            "diagnostic_report_sha256": diagnostic["report_sha256"],
        },
        "view_groups": views,
        "appearance_groups": appearances,
        "variants": [
            {"variant_id": identity, "expected_decision": decision, "residual_obstruction": obstruction, "render_spec": spec}
            for identity, decision, obstruction, spec in VARIANTS
        ],
        "split_policy": {
            "training_view_count": len(TRAINING_VIEWS),
            "development_view_count": len(DEVELOPMENT_VIEWS),
            "training_appearance_count": len(TRAINING_APPEARANCES),
            "development_appearance_count": len(DEVELOPMENT_APPEARANCES),
            "view_ids_disjoint": True,
            "appearance_ids_disjoint": True,
            "target_count_per_view": target_count,
            "variant_count_per_target": variant_count,
            "training_observation_count": train_count,
            "development_observation_count": development_count,
            "evaluation_observation_count": 0,
        },
        "render_admission": {
            "image_size_px": [1920, 1080],
            "target_crop_size_px": [96, 96],
            "crop_margin_fraction": 2.5,
            "adjacent_distractor_must_differ_from_clear": True,
            "adjacent_distractor_minimum_changed_pixels": 64,
            "adjacent_distractor_safe_region_overlap": 0.0,
            "obstruction_mask_overlap_must_match_declared_range": True,
            "truth_mask_retained_for_labels_only": True,
            "truth_mask_prohibited_as_model_input": True,
            "runtime_geometry_mask_prohibited_as_model_input": True,
            "fail_on_duplicate_observation_bytes": True,
        },
        "training_plan": {
            "algorithm": "target_crop_residual_cnn_v2",
            "input_size_px": [96, 96],
            "input_channels": ["RGB"],
            "convolution_channels": [16, 32, 64],
            "epochs": 18,
            "batch_size": 128,
            "learning_rate": 0.0003,
            "weight_decay": 0.0001,
            "sampling": "DETERMINISTIC_LABEL_AND_VARIANT_BALANCED",
            "loss": "BINARY_CROSS_ENTROPY",
            "seed": 19018,
            "threshold_candidates": [round(index / 100, 2) for index in range(5, 100, 5)],
        },
        "development_gate": {
            "missed_obstruction_rate_upper": 0.02,
            "visible_false_stop_rate_upper": 0.06,
            "confidence_level": 0.95,
            "view_cluster_bootstrap_resamples": 2000,
            "view_cluster_bootstrap_seed": 19018,
            "maximum_across_development_appearances": True,
            "point_and_cluster_upper_bounds_must_pass": True,
            "every_variant_family_must_be_present_in_every_view": True,
            "evaluation_must_remain_unopened": True,
        },
        "evaluation_group_present": False,
        "images_generated": False,
        "training_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Camera perturbations and appearances are synthetic and do not qualify physical calibration",
            "The source scene retains simplified device surfaces and an unmeasured camera",
            "The consumed v1 diagnostic informed this design and cannot evaluate v2",
            "No evaluation source, physical obstruction image, or deployment authority is included",
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
        "schema": result["schema"], "bundle_sha256": result["bundle_sha256"],
        "training_observations": result["split_policy"]["training_observation_count"],
        "development_observations": result["split_policy"]["development_observation_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
