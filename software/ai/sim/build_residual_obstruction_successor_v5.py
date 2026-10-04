"""Freeze the synthetic-only residual-obstruction v5 research campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = AI_ROOT / "schemas/residual_obstruction_successor_fixture_v5.schema.json"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    rendered = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _identities(prefix: str, count: int) -> list[str]:
    return [f"{prefix}_{index:02d}" for index in range(1, count + 1)]


def build(
    *, source_commit: str, remedy_path: Path, robustness_path: Path, v4_2_path: Path,
) -> dict[str, Any]:
    remedy = load_json(remedy_path)
    robustness = load_json(robustness_path)
    v4_2 = load_json(v4_2_path)
    if remedy.get("status") != "PHYSICAL_PILOT_REQUIRED_BEFORE_SUCCESSOR_SELECTION":
        raise ValueError("unexpected remedy decision")
    if robustness.get("status") != "FAILED_DEVELOPMENT_GATES":
        raise ValueError("v4.2 failure must remain preserved")
    if robustness.get("selected_threshold") is not None or robustness.get("evaluation_opened"):
        raise ValueError("v4.2 threshold/evaluation state changed")
    if v4_2.get("bundle_sha256") != robustness.get("fixture_bundle_sha256"):
        raise ValueError("v4.2 fixture binding mismatch")

    assets = {
        "training": _identities("v5_train_dark_cable", 4)
        + _identities("v5_train_translucent_cable", 3)
        + _identities("v5_train_hand", 3)
        + _identities("v5_train_tool_foreign", 4),
        "development": _identities("v5_dev_dark_cable", 3)
        + _identities("v5_dev_translucent_cable", 2)
        + _identities("v5_dev_hand", 2)
        + _identities("v5_dev_tool_foreign", 3),
        "evaluation": _identities("v5_eval_dark_cable", 3)
        + _identities("v5_eval_translucent_cable", 2)
        + _identities("v5_eval_hand", 2)
        + _identities("v5_eval_tool_foreign", 3),
    }
    scenes = {
        "training": _identities("v5_training_scene", 16),
        "development": _identities("v5_development_scene", 8),
        "evaluation": _identities("v5_evaluation_scene", 8),
    }
    lighting = {
        "training": _identities("v5_training_light", 3),
        "development": _identities("v5_development_light", 3),
        "evaluation": _identities("v5_evaluation_light", 3),
    }
    variants = [
        {"variant_id": "clear", "family": "NONE", "decision": "VISIBLE"},
        {"variant_id": "adjacent_left", "family": "DISTRACTOR", "decision": "VISIBLE"},
        {"variant_id": "adjacent_right", "family": "DISTRACTOR", "decision": "VISIBLE"},
        {"variant_id": "dark_cable_10", "family": "CABLE", "decision": "VISIBLE", "coverage": 0.10},
        {"variant_id": "dark_cable_30", "family": "CABLE", "decision": "ABSTAIN", "coverage": 0.30},
        {"variant_id": "dark_cable_60", "family": "CABLE", "decision": "ABSTAIN", "coverage": 0.60},
        {"variant_id": "translucent_cable_30", "family": "CABLE", "decision": "ABSTAIN", "coverage": 0.30},
        {"variant_id": "translucent_cable_60", "family": "CABLE", "decision": "ABSTAIN", "coverage": 0.60},
        {"variant_id": "hand_30", "family": "HAND", "decision": "ABSTAIN", "coverage": 0.30},
        {"variant_id": "hand_60", "family": "HAND", "decision": "ABSTAIN", "coverage": 0.60},
        {"variant_id": "tool_40", "family": "TOOL", "decision": "ABSTAIN", "coverage": 0.40},
        {"variant_id": "foreign_40", "family": "FOREIGN_OBJECT", "decision": "ABSTAIN", "coverage": 0.40},
    ]
    core = {
        "schema": "tactevra.ai_residual_obstruction_successor_fixture.v5",
        "scope": "SYNTHETIC_ISAAC_V5_PREDECLARATION_NO_QUALIFICATION",
        "status": "FROZEN_BEFORE_RENDER",
        "source_commit": source_commit,
        "source": {
            "remedy_file_sha256": file_hash(remedy_path),
            "remedy_report_sha256": remedy["report_sha256"],
            "robustness_file_sha256": file_hash(robustness_path),
            "robustness_report_sha256": robustness["report_sha256"],
            "v4_2_fixture_file_sha256": file_hash(v4_2_path),
            "v4_2_fixture_bundle_sha256": v4_2["bundle_sha256"],
            "target_catalog_sha256": v4_2["source"]["target_catalog_sha256"],
        },
        "sequence_amendment": {
            "previous_rule": "PHYSICAL_PILOT_REQUIRED_BEFORE_SUCCESSOR_SELECTION",
            "owner_direction": "CONTINUE_SIMULATION_ROBUSTNESS_RESEARCH_WHILE_PHYSICAL_INPUTS_BLOCKED",
            "allowed_effect": "SELECT_SYNTHETIC_RESEARCH_CANDIDATES_ONLY",
            "physical_pilot_still_required_for": [
                "RUNTIME_LIGHTING_ENVELOPE", "SIM_TO_REAL_TRANSFER", "PHYSICAL_QUALIFICATION",
            ],
            "v4_2_rejection_preserved": True,
            "evaluation_remains_unrendered": True,
        },
        "split_identities": {
            "scenes": scenes,
            "lighting": lighting,
            "obstruction_assets": assets,
            "pairwise_disjoint_required": True,
            "procedural_seed_ranges": {
                "training": [51000, 51999],
                "development": [52000, 52999],
                "evaluation": [53000, 53999],
            },
        },
        "variants": variants,
        "render_contract": {
            "targets": 75,
            "appearances_per_scene": 3,
            "variants_per_target": 12,
            "training_observations": 43200,
            "development_observations": 21600,
            "evaluation_observation_identities": 21600,
            "evaluation_images_generated": 0,
            "commissioned_reference_per_target_scene_lighting": True,
            "same_obstruction_mesh_or_material_across_splits_prohibited": True,
            "asset_geometry_material_texture_hashes_required": True,
            "arm_mask_from_perturbed_measured_state_not_ground_truth_mask": True,
            "camera_translation_jitter_mm": [3.0, 3.0, 1.5],
            "camera_rotation_jitter_deg": [0.8, 0.8, 1.0],
            "joint_measurement_noise_and_backlash_required": True,
            "capture_timestamp_offset_ms": [-150, 150],
            "lighting_scope": "BROAD_SYNTHETIC_RESEARCH_RANGE_NOT_RUNTIME_ADMISSION",
        },
        "candidate_models": [
            {
                "candidate_id": "V5_EDGE_TEXTURE_96",
                "local_size_px": 96,
                "context_size_px": None,
                "channels": [
                    "CURRENT_RGB", "REFERENCE_RGB", "ABS_RGB_DIFFERENCE",
                    "SOBEL_MAGNITUDE_DIFFERENCE", "LOCAL_TEXTURE_DIFFERENCE", "SAFE_REGION_MASK",
                ],
                "spatial_feature_map": [6, 6],
                "maximum_trainable_parameters": 2000000,
            },
            {
                "candidate_id": "V5_EDGE_TEXTURE_MULTISCALE_96_192",
                "local_size_px": 96,
                "context_size_px": 192,
                "channels": [
                    "CURRENT_RGB", "REFERENCE_RGB", "ABS_RGB_DIFFERENCE",
                    "SOBEL_MAGNITUDE_DIFFERENCE", "LOCAL_TEXTURE_DIFFERENCE", "SAFE_REGION_MASK",
                    "WIDE_CONTEXT_RGB_DIFFERENCE",
                ],
                "spatial_feature_map": [6, 6],
                "maximum_trainable_parameters": 3000000,
            },
        ],
        "training_contract": {
            "offline_capable": True,
            "selected_normalization": "SELF_CROP_P05_P95",
            "unchanged_training_free_baseline_required": True,
            "unchanged_v4_2_checkpoint_comparison_required": True,
            "balanced_by": ["TARGET", "DECISION", "VARIANT_FAMILY", "SCENE", "LIGHTING"],
            "memorization_rows": 500,
            "minimum_memorization_accuracy": 0.995,
            "random_seed": 55001,
            "thresholds": [round(index * 0.05, 2) for index in range(1, 20)],
            "model_output_semantics": "UNCALIBRATED_RANKING_SCORE_NOT_CONFIDENCE",
        },
        "development_gates": {
            "maximum_pooled_missed_obstruction_rate": 0.02,
            "maximum_pooled_visible_false_stop_rate": 0.10,
            "maximum_scene_cluster_missed_upper_95": 0.02,
            "maximum_scene_cluster_false_stop_upper_95": 0.10,
            "maximum_cable_family_missed_rate": 0.02,
            "maximum_dark_cable_30_60_missed_rate": 0.02,
            "maximum_visible_false_stop_rate": 0.10,
            "minimum_every_target_auc": 0.95,
            "minimum_linear_q05_target_auc": 0.98,
            "minimum_linear_q05_target_quantile_margin": 0.05,
            "v4_2_no_regression_metrics": ["EVERY_TARGET_AUC", "LINEAR_Q05_TARGET_AUC"],
            "hard_case_reports_required": [
                "DARK_ON_DARK_BOUNDARY_ALIGNED_CABLE", "THIN_CABLE", "REFLECTIVE_CABLE",
                "ADJACENT_OBJECT", "LIGHTING_PLUS_CAMERA_JITTER", "PERTURBED_ARM_MASK",
            ],
            "selection_rule": "LOWEST_PARAMETER_CANDIDATE_PASSING_EVERY_GATE",
            "no_passing_candidate_result": "REJECT_ALL_KEEP_EVALUATION_CLOSED",
        },
        "end_to_end_follow_on": {
            "required_after_development_pass": True,
            "actual_model_motion_batch_v2_output_required": True,
            "simulated_missions": [
                "TYPE_HELLO", "TYPE_REPEATED_KEYS", "TYPE_NUMBERS_AND_PUNCTUATION",
                "ABSTAIN_ON_OBSTRUCTION", "ABSTAIN_ON_STALE_EVIDENCE", "ABSTAIN_ON_UNCERTAINTY",
            ],
            "wrong_target_contacts_allowed": 0,
            "hardware_authority": False,
        },
        "images_generated": False,
        "training_started": False,
        "development_opened": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This selects synthetic research candidates before physical pilot data under the owner's explicit direction; it does not select a deployment model.",
            "Lighting ranges remain synthetic research conditions and cannot set runtime reference-validity limits.",
            "Rendered obstruction assets remain approximations even though their identities are split-disjoint.",
            "No image, checkpoint, threshold, evaluation result, physical qualification, or execution authority exists.",
        ],
    }
    result = {**core, "bundle_sha256": canonical_hash(core)}
    errors = sorted(
        Draft202012Validator(load_json(SCHEMA)).iter_errors(result), key=lambda e: list(e.path),
    )
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--remedy", type=Path, required=True)
    parser.add_argument("--robustness", type=Path, required=True)
    parser.add_argument("--v4-2-fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        source_commit=args.source_commit,
        remedy_path=args.remedy,
        robustness_path=args.robustness,
        v4_2_path=args.v4_2_fixture,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
