from __future__ import annotations

from pathlib import Path
import json
import sys

import numpy as np
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from train.train_residual_obstruction_v2 import (  # noqa: E402
    RESULT_SCHEMA,
    balanced_epoch_indices,
    canonical,
    load_bound,
    score_thresholds,
    sha256_bytes,
)


REPORT = AI_ROOT / "eval" / "residual_obstruction_development_v2.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_development_v2.schema.json"


def _entries():
    rows = []
    for label, variants in (("VISIBLE", ("clear", "adjacent")), ("ABSTAIN", ("cable", "tool"))):
        for variant in variants:
            for index in range(4):
                rows.append({
                    "expected_decision": label,
                    "variant_id": variant,
                    "observation_id": f"{label}-{variant}-{index}",
                })
    return rows


def test_balanced_sampling_is_deterministic_and_balances_label_and_variant():
    entries = _entries()
    first = balanced_epoch_indices(entries, 16, 19018)
    second = balanced_epoch_indices(entries, 16, 19018)
    assert np.array_equal(first, second)
    selected = [entries[index] for index in first]
    assert sum(row["expected_decision"] == "VISIBLE" for row in selected) == 8
    assert sum(row["expected_decision"] == "ABSTAIN" for row in selected) == 8
    assert {variant: sum(row["variant_id"] == variant for row in selected) for variant in ("clear", "adjacent", "cable", "tool")} == {
        "clear": 4, "adjacent": 4, "cable": 4, "tool": 4,
    }


def test_view_cluster_and_appearance_gate_passes_perfect_separation():
    labels = np.asarray([1, 1, 0, 0] * 3, dtype=np.int8)
    probabilities = np.asarray([0.9, 0.8, 0.2, 0.1] * 3, dtype=np.float32)
    views = [value for value in ("v1", "v2", "v3") for _ in range(4)]
    appearances = ["a1", "a2", "a1", "a2"] * 3
    gate = {
        "view_cluster_bootstrap_seed": 19018,
        "view_cluster_bootstrap_resamples": 200,
        "missed_obstruction_rate_upper": 0.02,
        "visible_false_stop_rate_upper": 0.06,
    }
    first = score_thresholds(labels, probabilities, views, appearances, [0.5], gate)
    second = score_thresholds(labels, probabilities, views, appearances, [0.5], gate)
    assert first == second
    assert first[0]["gate_met"] is True
    assert first[0]["missed_obstruction_view_cluster_upper"] == 0
    assert first[0]["visible_false_stop_view_cluster_upper"] == 0


def test_worst_appearance_failure_blocks_gate():
    labels = np.asarray([1, 1, 0, 0, 1, 1, 0, 0], dtype=np.int8)
    probabilities = np.asarray([0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1], dtype=np.float32)
    gate = {
        "view_cluster_bootstrap_seed": 19018,
        "view_cluster_bootstrap_resamples": 200,
        "missed_obstruction_rate_upper": 0.02,
        "visible_false_stop_rate_upper": 0.06,
    }
    result = score_thresholds(labels, probabilities, ["v1"] * 4 + ["v2"] * 4, ["good"] * 4 + ["bad"] * 4, [0.5], gate)[0]
    assert result["gate_met"] is False
    assert result["maximum_appearance_missed_obstruction_rate"] == 1.0


def test_retained_failed_result_is_strict_bound_and_zero_authority():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report = load_bound(REPORT, RESULT_SCHEMA, "result_sha256")
    Draft202012Validator(schema).validate(report)
    core = {key: value for key, value in report.items() if key != "result_sha256"}
    assert report["result_sha256"] == sha256_bytes(canonical(core))
    assert report["status"] == "FAILED_DEVELOPMENT_GATE"
    assert report["selected_threshold"] is None
    assert not any(row["gate_met"] for row in report["threshold_measurements"])
    assert report["evaluation_count"] == 0
    assert report["evaluation_opened"] is False
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False
