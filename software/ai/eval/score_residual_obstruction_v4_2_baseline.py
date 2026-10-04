"""Score the frozen training-free v4.2 baseline after both memorization gates pass."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "train"))

from prepare_residual_obstruction_v4_2_gates import (  # noqa: E402
    NORMALIZATION_METRICS,
    PREPARATION_SCHEMA,
    _load_report,
    load_complete_campaign,
)
from admit_residual_obstruction_v4_2_shards import canonical, digest  # noqa: E402
from admit_residual_obstruction_v4_1_smoke import rank_auc  # noqa: E402


MEMORIZATION_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_memorization.v1"
REPORT_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_training_free_baseline.v1"


def linear_q05(values: list[float]) -> float:
    if not values:
        raise ValueError("q05 requires values")
    return float(np.quantile(np.asarray(values, dtype=np.float64), 0.05, method="linear"))


def score_rows(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    labels = [row["expected_decision"] == "ABSTAIN" for row in rows]
    scores = [float(row["difference_metrics"][metric]) for row in rows]
    targets = sorted({f"{row['device']}:{row['target_id']}" for row in rows})
    per_target = {}
    for target in targets:
        selected = [row for row in rows if f"{row['device']}:{row['target_id']}" == target]
        per_target[target] = rank_auc(
            [row["expected_decision"] == "ABSTAIN" for row in selected],
            [float(row["difference_metrics"][metric]) for row in selected],
        )
    return {
        "pooled_auc": rank_auc(labels, scores),
        "per_target_auc": per_target,
        "q05_per_target_auc": linear_q05(list(per_target.values())),
        "minimum_per_target_auc": min(per_target.values()),
    }


def select_normalization(results: dict[str, dict[str, Any]], rule: dict[str, Any]) -> str:
    left = "SELF_CROP_P05_P95"
    right = "REFERENCE_CONTEXT_WHITEPOINT"
    difference = results[right]["q05_per_target_auc"] - results[left]["q05_per_target_auc"]
    if abs(difference) <= float(rule["practical_tie_band_absolute_auc"]):
        return str(rule["tie_break_normalization_id"])
    return right if difference > 0.0 else left


def score(
    fixture_path: Path,
    admission_path: Path,
    preparation_path: Path,
    memorization_path: Path,
    shard_dirs: list[Path],
) -> dict[str, Any]:
    fixture, admission, entries = load_complete_campaign(fixture_path, admission_path, shard_dirs)
    preparation, _ = _load_report(preparation_path, PREPARATION_SCHEMA)
    memorization, _ = _load_report(memorization_path, MEMORIZATION_SCHEMA)
    if preparation["admission_report_sha256"] != admission["report_sha256"]:
        raise ValueError("preparation admission binding mismatch")
    if memorization["preparation_report_sha256"] != preparation["report_sha256"]:
        raise ValueError("memorization preparation binding mismatch")
    expected = set(NORMALIZATION_METRICS)
    runs = memorization.get("runs", {})
    if set(runs) != expected or not all(runs[name]["gate_met"] is True for name in expected):
        raise ValueError("both memorization gates must pass before development opens")
    if memorization.get("development_pixels_opened") is not False:
        raise ValueError("memorization report claims development access")
    development = [row for row in entries if row["split"] == "development"]
    if len(development) != 28_800:
        raise ValueError("development row count mismatch")
    results = {
        normalization: score_rows(development, metric)
        for normalization, metric in NORMALIZATION_METRICS.items()
    }
    rule = fixture["training_plan"]["normalization_selection_rule"]
    selected = select_normalization(results, rule)
    core = {
        "schema": REPORT_SCHEMA,
        "scope": "SYNTHETIC_DEVELOPMENT_TRAINING_FREE_BASELINE_NO_QUALIFICATION",
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_report_sha256": admission["report_sha256"],
        "preparation_report_sha256": preparation["report_sha256"],
        "memorization_report_sha256": memorization["report_sha256"],
        "development_observation_count": len(development),
        "results": results,
        "selection_rule": rule,
        "selected_normalization": selected,
        "selection_made_once": True,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Synthetic development scoring is not physical or deployment qualification",
            "The selected training-free baseline still must be exceeded by the selected CNN",
            "Evaluation remains absent and unopened",
        ],
    }
    return {**core, "report_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--memorization", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = score(
        args.fixture, args.admission, args.preparation, args.memorization, args.shard
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "report_sha256": result["report_sha256"],
        "selected_normalization": result["selected_normalization"],
        "results": result["results"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
