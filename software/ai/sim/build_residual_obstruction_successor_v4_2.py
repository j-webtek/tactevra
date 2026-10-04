"""Freeze dual-normalization selection and baseline-uplift rules before development."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v4_2"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bound(path: Path, schema: str, field: str) -> tuple[dict, bytes]:
    raw = path.resolve(strict=True).read_bytes()
    value = json.loads(raw)
    if value.get("schema") != schema:
        raise ValueError("schema mismatch")
    core = {key: item for key, item in value.items() if key != field}
    if value.get(field) != digest(canonical(core)):
        raise ValueError("canonical hash mismatch")
    return value, raw


def build(v4_1_path: Path, smoke_admission_path: Path) -> dict:
    v4_1, v4_1_bytes = _bound(
        v4_1_path,
        "tactevra.ai_residual_obstruction_successor_fixture.v4_1",
        "bundle_sha256",
    )
    smoke, smoke_bytes = _bound(
        smoke_admission_path,
        "tactevra.ai_residual_obstruction_v4_1_smoke_admission.v1",
        "report_sha256",
    )
    if any(v4_1[field] for field in ("images_generated", "training_started", "development_opened", "evaluation_opened")):
        raise ValueError("v4.1 was consumed")
    if smoke["status"] != "PASS_WITH_LIMITATIONS" or smoke["evaluation_observation_count"] != 0:
        raise ValueError("smoke evidence is not admissible")
    if smoke["target_ids"] != ["F", "G", "H", "I"] or smoke["observation_count"] != 192:
        raise ValueError("unexpected smoke scope")

    copied = {
        key: value
        for key, value in v4_1.items()
        if key not in {
            "schema", "bundle_sha256", "source", "render_admission", "training_plan",
            "pretraining_gates", "development_gate", "limitations",
        }
    }
    source = {
        **v4_1["source"],
        "superseded_v4_1_file_sha256": digest(v4_1_bytes),
        "superseded_v4_1_bundle_sha256": v4_1["bundle_sha256"],
        "v4_1_smoke_admission_file_sha256": digest(smoke_bytes),
        "v4_1_smoke_admission_report_sha256": smoke["report_sha256"],
    }
    candidates = [
        {
            "normalization_id": "SELF_CROP_P05_P95",
            "algorithm": "INDEPENDENT_PER_CROP_P05_P95_LUMINANCE_AND_CHANNEL_MEAN",
            "runtime_context_required": False,
        },
        {
            "normalization_id": "REFERENCE_CONTEXT_WHITEPOINT",
            "algorithm": "REFERENCE_CONTEXT_P95_CHANNEL_WHITEPOINT_APPLIED_TO_PAIR",
            "runtime_context_required": True,
            "context_region": "OUTER_24_PIXEL_BORDER_OF_96_PIXEL_TARGET_NEIGHBORHOOD",
        },
    ]
    selection = {
        "selection_split": "development",
        "score": "MEAN_ABSOLUTE_NORMALIZED_RGB_DIFFERENCE",
        "score_is_training_free": True,
        "per_target_auc_required_for_all_targets": True,
        "primary_statistic": "LINEAR_INTERPOLATED_Q05_PER_TARGET_AUC",
        "higher_is_better": True,
        "practical_tie_band_absolute_auc": 0.005,
        "tie_break_normalization_id": "SELF_CROP_P05_P95",
        "selection_made_once": True,
        "evaluation_statistics_prohibited": True,
    }
    baseline_uplift = {
        "comparison_split": "development",
        "same_rows_and_labels_required": True,
        "minimum_pooled_auc_improvement": 0.02,
        "minimum_q05_per_target_auc_improvement": 0.02,
        "selected_cnn_must_beat_selected_training_free_baseline": True,
        "failure_decision": "REJECT_CANDIDATE",
    }
    training = {
        **v4_1["training_plan"],
        "normalization": "DUAL_FROZEN_CANDIDATES_SELECTED_ON_DEVELOPMENT",
        "photometric_normalization": {
            "candidates": candidates,
            "absolute_difference_computed_after_normalization": True,
            "raw_difference_is_training_free_diagnostic_only": True,
        },
        "train_one_identical_cnn_per_normalization": True,
        "normalization_selection_rule": selection,
        "training_free_baseline": {
            "score": selection["score"],
            "model_parameters": 0,
            "fit_required": False,
            "reported_for_each_normalization": True,
        },
        "cnn_baseline_uplift_gate": baseline_uplift,
    }
    pretraining = {
        **v4_1["pretraining_gates"],
        "memorization_gate_applies_to_each_normalization": True,
        "development_prohibited_until_both_memorization_runs_pass": True,
    }
    development = {
        **v4_1["development_gate"],
        "normalization_selection_rule": selection,
        "cnn_baseline_uplift_gate": baseline_uplift,
    }
    render_admission = {
        **v4_1["render_admission"],
        "semantic_safe_overlap_bounds": {
            "cable_rubber": [0.2, 0.75],
            "cable_translucent": [0.2, 0.75],
            "tool_matte_edge": [0.25, 0.5],
            "tool_gloss_center": [0.5, 0.8],
            "foreign_object": [0.35, 0.7],
        },
        "zero_semantic_obstruction_overlap_variants": [
            "clear", "adjacent_left", "adjacent_right", "glare", "defocus",
            "motion_blur", "compression",
        ],
        "adjacent_variants_require_zero_safe_overlap": True,
        "one_reference_per_scene_target_required": True,
        "exact_training_observation_count": 43200,
        "exact_development_observation_count": 28800,
        "evaluation_observation_count": 0,
    }
    core = {
        "schema": SCHEMA,
        "source": source,
        **copied,
        "render_admission": render_admission,
        "training_plan": training,
        "pretraining_gates": pretraining,
        "development_gate": development,
        "limitations": [
            "This v4.2 fixture supersedes unrendered v4.1 and remains synthetic",
            "The bounded smoke motivated comparison but did not select normalization",
            "A 0.02 AUC uplift is a predeclared practical model-value gate, not a safety guarantee",
            "Evaluation identities remain frozen and unrendered until all development gates pass",
            "No controller command, motion policy, permit, transport, or physical authority is included",
        ],
    }
    return {**core, "bundle_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v4-1", type=Path, required=True)
    parser.add_argument("--smoke-admission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.v4_1, args.smoke_admission)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"bundle_sha256": result["bundle_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
