"""Quantify whether residual-v4 per-target binary gates are supportable."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


SCHEMA = "tactevra.ai_residual_v4_gate_power.v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def binomial_cdf(k: int, n: int, probability: float) -> float:
    return sum(
        math.comb(n, value) * probability**value * (1.0 - probability) ** (n - value)
        for value in range(k + 1)
    )


def clopper_pearson_upper(k: int, n: int, alpha: float = 0.05) -> float:
    if k == n:
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(80):
        middle = (low + high) / 2.0
        if binomial_cdf(k, n, middle) > alpha:
            low = middle
        else:
            high = middle
    return high


def auc_standard_error(auc: float, positives: int, negatives: int) -> float:
    q1 = auc / (2.0 - auc)
    q2 = 2.0 * auc * auc / (1.0 + auc)
    variance = (
        auc * (1.0 - auc)
        + (positives - 1) * (q1 - auc * auc)
        + (negatives - 1) * (q2 - auc * auc)
    ) / (positives * negatives)
    return math.sqrt(variance)


def build(fixture_path: Path) -> dict:
    fixture_bytes = fixture_path.resolve(strict=True).read_bytes()
    fixture = json.loads(fixture_bytes)
    if fixture.get("schema") != "tactevra.ai_residual_obstruction_successor_fixture.v4":
        raise ValueError("unsupported fixture")
    target_count = 75
    scenes = fixture["split_policy"]["development_scene_count"]
    appearances = 4
    visible_variants, obstruction_variants = 3, 9
    visible = scenes * appearances * visible_variants
    obstruction = scenes * appearances * obstruction_variants
    miss_limit = fixture["development_gate"]["missed_obstruction_rate_upper"]
    false_limit = fixture["development_gate"]["visible_false_stop_rate_upper"]

    def gate_rows(n: int, limit: float) -> dict:
        point_max = math.floor(n * limit)
        upper_max = max(
            (k for k in range(point_max + 1) if clopper_pearson_upper(k, n) <= limit),
            default=-1,
        )
        probability_at_limit = binomial_cdf(point_max, n, limit)
        return {
            "sample_count_per_target": n,
            "rate_limit": limit,
            "maximum_point_pass_failures": point_max,
            "maximum_95pct_upper_bound_pass_failures": upper_max,
            "single_target_point_pass_probability_at_true_limit": probability_at_limit,
            "all_75_targets_point_pass_probability_at_true_limit": probability_at_limit**target_count,
        }

    auc_se = auc_standard_error(0.95, obstruction, visible)
    core = {
        "schema": SCHEMA,
        "scope": "SYNTHETIC_GATE_POWER_PLANNING_NO_QUALIFICATION",
        "fixture_file_sha256": sha256(fixture_bytes),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "target_count": target_count,
        "per_target_obstruction_gate": gate_rows(obstruction, miss_limit),
        "per_target_visible_gate": gate_rows(visible, false_limit),
        "auc_precision": {
            "assumed_auc": 0.95,
            "positive_count": obstruction,
            "negative_count": visible,
            "hanley_mcneil_standard_error": auc_se,
            "approximate_95pct_interval": [max(0.0, 0.95 - 1.96 * auc_se), min(1.0, 0.95 + 1.96 * auc_se)],
        },
        "decision": "POOL_BINARY_RATES_KEEP_ROBUST_PER_TARGET_RANKING",
        "recommended_gate": {
            "pooled_cluster_missed_obstruction_rate_upper": 0.02,
            "pooled_cluster_visible_false_stop_rate_upper": 0.06,
            "minimum_per_target_auc": 0.90,
            "per_target_auc_q05_minimum": 0.95,
            "per_target_quantile_margin_quantile": 0.05,
            "per_target_quantile_margin_q05_minimum": 0.05,
            "strict_extreme_margin_is_diagnostic_only": True,
            "per_target_binary_error_gate": False,
        },
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Binomial calculations do not replace the frozen base-scene cluster bootstrap",
            "The AUC interval is an analytic approximation and ignores scene correlation",
            "This receipt plans synthetic development gates and does not qualify a model",
        ],
    }
    return {**core, "receipt_sha256": sha256(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.fixture)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
