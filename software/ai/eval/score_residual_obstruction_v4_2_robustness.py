"""Apply the frozen v4.2 threshold and robustness gates without opening evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import torch


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "train"))

from admit_residual_obstruction_v4_1_smoke import rank_auc  # noqa: E402
from admit_residual_obstruction_v4_2_shards import canonical, digest  # noqa: E402
from prepare_residual_obstruction_v4_2_gates import _load_report, load_complete_campaign  # noqa: E402
from run_residual_obstruction_v4_2_memorization import spatial_model  # noqa: E402
from train_residual_obstruction_v3 import _rate_rows, _rates  # noqa: E402
from train_residual_obstruction_v4_2_cnn import load_arrays, predict  # noqa: E402


CNN_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_cnn_development.v1"
REPORT_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_robustness.v1"


def target_metrics(
    labels: np.ndarray, probabilities: np.ndarray, target_ids: list[str], quantile: float
) -> dict[str, Any]:
    rows = []
    for target in sorted(set(target_ids)):
        selected = np.asarray([i for i, value in enumerate(target_ids) if value == target])
        target_labels = labels[selected]
        scores = probabilities[selected]
        visible = scores[target_labels == 0]
        obstructed = scores[target_labels == 1]
        visible_q = float(np.quantile(visible, 1.0 - quantile, method="linear"))
        obstructed_q = float(np.quantile(obstructed, quantile, method="linear"))
        rows.append({
            "target_id": target,
            "auc": rank_auc(target_labels.tolist(), scores.tolist()),
            "visible_q95": visible_q,
            "obstructed_q05": obstructed_q,
            "quantile_margin": obstructed_q - visible_q,
            "strict_extreme_margin": float(np.min(obstructed) - np.max(visible)),
        })
    aucs = np.asarray([row["auc"] for row in rows])
    margins = np.asarray([row["quantile_margin"] for row in rows])
    return {
        "targets": rows,
        "minimum_auc": float(np.min(aucs)),
        "q05_auc": float(np.quantile(aucs, 0.05, method="linear")),
        "q05_quantile_margin": float(np.quantile(margins, 0.05, method="linear")),
        "minimum_strict_extreme_margin_diagnostic": float(
            min(row["strict_extreme_margin"] for row in rows)
        ),
    }


def score_thresholds(
    rows: list[dict[str, Any]], probabilities: np.ndarray, fixture: dict[str, Any]
) -> dict[str, Any]:
    gate = fixture["development_gate"]
    plan = fixture["training_plan"]
    labels = np.asarray(
        [1 if row["expected_decision"] == "ABSTAIN" else 0 for row in rows],
        dtype=np.int8,
    )
    scenes = [row["scene_id"] for row in rows]
    unique_scenes = sorted(set(scenes))
    scene_groups = [
        np.asarray([i for i, value in enumerate(scenes) if value == scene])
        for scene in unique_scenes
    ]
    rng = np.random.default_rng(int(gate["base_scene_cluster_bootstrap_seed"]))
    samples = rng.integers(
        0,
        len(scene_groups),
        size=(int(gate["base_scene_cluster_bootstrap_resamples"]), len(scene_groups)),
    )
    quantile = float(gate["per_target_quantile_margin_quantile"])
    targets = target_metrics(
        labels,
        probabilities,
        [f"{row['device']}:{row['target_id']}" for row in rows],
        quantile,
    )
    target_gate = all((
        targets["minimum_auc"] >= float(gate["minimum_per_target_auc"]),
        targets["q05_auc"] >= float(gate["per_target_auc_q05_minimum"]),
        targets["q05_quantile_margin"]
        >= float(gate["per_target_quantile_margin_q05_minimum"]),
    ))
    miss_limit = float(gate["pooled_cluster_missed_obstruction_rate_upper"])
    false_limit = float(gate["pooled_cluster_visible_false_stop_rate_upper"])
    confidence = float(gate["confidence_level"])
    measurements = []
    for threshold in plan["threshold_candidates"]:
        threshold = float(threshold)
        misses, obstruction_count, false_stops, visible_count = _rates(
            labels, probabilities, threshold
        )
        grouped = np.asarray(
            [_rates(labels[index], probabilities[index], threshold) for index in scene_groups],
            dtype=np.int64,
        )
        selected = grouped[samples].sum(axis=1)
        miss_upper = float(
            np.quantile(selected[:, 0] / selected[:, 1], confidence, method="higher")
        )
        false_upper = float(
            np.quantile(selected[:, 2] / selected[:, 3], confidence, method="higher")
        )
        appearances = _rate_rows(
            labels,
            probabilities,
            [row["appearance_id"] for row in rows],
            threshold,
            "appearance_id",
        )
        families = _rate_rows(
            labels,
            probabilities,
            [row["variant_family"] for row in rows],
            threshold,
            "variant_family",
        )
        miss_rate = misses / obstruction_count
        false_rate = false_stops / visible_count
        max_appearance_miss = max(row["missed_obstruction_rate"] for row in appearances)
        max_appearance_false = max(row["visible_false_stop_rate"] for row in appearances)
        max_family_miss = max(
            row["missed_obstruction_rate"] for row in families if row["obstruction_count"]
        )
        max_family_false = max(
            row["visible_false_stop_rate"] for row in families if row["visible_count"]
        )
        point_cluster = all((
            miss_rate <= miss_limit,
            false_rate <= false_limit,
            miss_upper <= miss_limit,
            false_upper <= false_limit,
        ))
        appearance_gate = (
            max_appearance_miss <= miss_limit and max_appearance_false <= false_limit
        )
        family_gate = max_family_miss <= miss_limit and max_family_false <= false_limit
        measurements.append({
            "threshold": threshold,
            "missed_obstructions": misses,
            "obstruction_count": obstruction_count,
            "missed_obstruction_rate": miss_rate,
            "missed_obstruction_scene_cluster_upper": miss_upper,
            "visible_false_stops": false_stops,
            "visible_count": visible_count,
            "visible_false_stop_rate": false_rate,
            "visible_false_stop_scene_cluster_upper": false_upper,
            "maximum_appearance_missed_obstruction_rate": max_appearance_miss,
            "maximum_appearance_visible_false_stop_rate": max_appearance_false,
            "maximum_family_missed_obstruction_rate": max_family_miss,
            "maximum_family_visible_false_stop_rate": max_family_false,
            "point_and_cluster_gate_met": point_cluster,
            "worst_appearance_gate_met": appearance_gate,
            "worst_family_gate_met": family_gate,
            "target_auc_and_margin_gate_met": target_gate,
            "appearance_metrics": appearances,
            "family_metrics": families,
            "gate_met": point_cluster and appearance_gate and family_gate and target_gate,
        })
    passing = [row for row in measurements if row["gate_met"]]
    return {
        "selected_threshold": passing[0]["threshold"] if passing else None,
        "development_gate_met": bool(passing),
        "threshold_measurements": measurements,
        "target_metrics": targets,
        "target_auc_and_margin_gate_met": target_gate,
    }


def run(
    fixture_path: Path,
    admission_path: Path,
    cnn_report_path: Path,
    checkpoint_path: Path,
    shard_dirs: list[Path],
) -> dict[str, Any]:
    fixture, admission, entries = load_complete_campaign(
        fixture_path, admission_path, shard_dirs
    )
    cnn_report, _ = _load_report(cnn_report_path, CNN_SCHEMA)
    checkpoint_bytes = checkpoint_path.resolve(strict=True).read_bytes()
    checkpoint_sha = hashlib.sha256(checkpoint_bytes).hexdigest()
    if checkpoint_sha != cnn_report["checkpoint_sha256"]:
        raise ValueError("checkpoint hash differs from CNN report")
    if cnn_report.get("development_pass_in_simulation") is not True:
        raise ValueError("CNN uplift gate did not pass")
    if cnn_report.get("evaluation_opened") is not False:
        raise ValueError("CNN report claims evaluation access")
    development = [row for row in entries if row["split"] == "development"]
    arrays, _ = load_arrays(
        development, cnn_report["selected_normalization"], "robustness development"
    )
    model = spatial_model(torch).cuda() if torch.cuda.is_available() else spatial_model(torch)
    checkpoint = torch.load(
        checkpoint_path, map_location=next(model.parameters()).device, weights_only=True
    )
    model.load_state_dict(checkpoint["state_dict"])
    probabilities = predict(model, arrays, int(fixture["training_plan"]["batch_size"]))
    result = score_thresholds(development, probabilities, fixture)
    core = {
        "schema": REPORT_SCHEMA,
        "scope": "SYNTHETIC_CONSUMED_DEVELOPMENT_ROBUSTNESS_NO_QUALIFICATION",
        "status": (
            "PASSED_DEVELOPMENT_GATES"
            if result["development_gate_met"]
            else "FAILED_DEVELOPMENT_GATES"
        ),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_report_sha256": admission["report_sha256"],
        "cnn_report_sha256": cnn_report["report_sha256"],
        "checkpoint_sha256": checkpoint_sha,
        "development_probability_sha256": hashlib.sha256(
            probabilities.astype("<f4").tobytes()
        ).hexdigest(),
        "development_count": len(development),
        **result,
        "model_output_semantics": "UNCALIBRATED_RANKING_SCORE_NOT_CONFIDENCE",
        "candidate_workcell_mitigation": "PROHIBIT_CABLE_ROUTING_ACROSS_KEYBOARD_OR_PHONE_INTERACTION_SURFACES",
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Synthetic consumed-development scoring is not physical qualification",
            "Model scores are ranking values and are not calibrated confidence",
            "Frozen evaluation reuses procedural obstruction assets",
            "Real clear, cable, and hand captures remain required",
        ],
    }
    return {**core, "report_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--cnn-report", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.fixture,
        args.admission,
        args.cnn_report,
        args.checkpoint,
        args.shard,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({
        "report_sha256": result["report_sha256"],
        "status": result["status"],
        "selected_threshold": result["selected_threshold"],
        "target_metrics": {
            key: value for key, value in result["target_metrics"].items() if key != "targets"
        },
        "passing_threshold_count": sum(
            row["gate_met"] for row in result["threshold_measurements"]
        ),
    }, indent=2))
    return 0 if result["development_gate_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
