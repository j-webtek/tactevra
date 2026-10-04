from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from train.train_residual_obstruction_v3 import (  # noqa: E402
    RESULT_SCHEMA,
    canonical,
    group_epoch_order,
    load_bound,
    paired_groups,
    score_thresholds,
    sha256_bytes,
)


REPORT = AI_ROOT / "eval" / "residual_obstruction_development_v3.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_development_v3.schema.json"


def _gate() -> dict:
    return {
        "base_scene_cluster_bootstrap_resamples": 200,
        "base_scene_cluster_bootstrap_seed": 19030,
        "confidence_level": 0.95,
        "minimum_target_local_separation_margin": 0.0,
        "missed_obstruction_rate_upper": 0.02,
        "visible_false_stop_rate_upper": 0.06,
    }


def _perfect_development():
    labels = []
    probabilities = []
    scenes = []
    appearances = []
    families = []
    targets = []
    for scene in ("d1", "d2", "d3", "d4"):
        for target in ("keyboard:A", "phone:key_a"):
            for appearance in ("neutral", "low_key"):
                for label, probability, family in ((0, 0.1, "NONE"), (1, 0.9, "CABLE")):
                    labels.append(label)
                    probabilities.append(probability)
                    scenes.append(scene)
                    appearances.append(appearance)
                    families.append(family)
                    targets.append(target)
    return (
        np.asarray(labels, dtype=np.int8),
        np.asarray(probabilities, dtype=np.float32),
        scenes,
        appearances,
        families,
        targets,
    )


def test_paired_groups_preserve_complete_appearance_sets_and_deterministic_order():
    entries = []
    appearances = ["neutral", "low_key", "high_key", "cool_sensor"]
    for scene in ("s2", "s1"):
        for appearance in reversed(appearances):
            entries.append({
                "split": "training",
                "scene_id": scene,
                "device": "keyboard",
                "target_id": "A",
                "variant_id": "clear",
                "appearance_id": appearance,
            })
    groups = paired_groups(entries, "training", appearances)
    assert len(groups) == 2
    assert all([entries[index]["appearance_id"] for index in group] == appearances for group in groups)
    first = group_epoch_order(groups, 19030)
    second = group_epoch_order(groups, 19030)
    assert np.array_equal(first, second)
    assert len(first) == 8


def test_frozen_development_gates_pass_perfect_scene_family_and_target_separation():
    labels, probabilities, scenes, appearances, families, targets = _perfect_development()
    measurements, separations = score_thresholds(
        labels,
        probabilities,
        scenes,
        appearances,
        families,
        targets,
        [0.5],
        _gate(),
    )
    measurement = measurements[0]
    assert measurement["gate_met"] is True
    assert measurement["point_and_cluster_gate_met"] is True
    assert measurement["worst_appearance_gate_met"] is True
    assert measurement["worst_family_gate_met"] is True
    assert measurement["target_separation_gate_met"] is True
    assert all(row["separation_margin"] > 0 for row in separations)


def test_target_local_overlap_blocks_an_otherwise_perfect_threshold():
    labels, probabilities, scenes, appearances, families, targets = _perfect_development()
    selected = next(
        index
        for index, (label, target) in enumerate(zip(labels, targets, strict=True))
        if label == 1 and target == "phone:key_a"
    )
    probabilities[selected] = 0.05
    measurements, separations = score_thresholds(
        labels,
        probabilities,
        scenes,
        appearances,
        families,
        targets,
        [0.5],
        _gate(),
    )
    assert measurements[0]["gate_met"] is False
    assert measurements[0]["target_separation_gate_met"] is False
    phone = next(row for row in separations if row["target_id"] == "phone:key_a")
    assert phone["separation_margin"] < 0


def test_worst_family_failure_is_not_hidden_by_aggregate_rate():
    labels, probabilities, scenes, appearances, families, targets = _perfect_development()
    families[1] = "RARE_OBSTRUCTION"
    probabilities[1] = 0.1
    measurements, _ = score_thresholds(
        labels,
        probabilities,
        scenes,
        appearances,
        families,
        targets,
        [0.5],
        _gate(),
    )
    assert measurements[0]["maximum_family_missed_obstruction_rate"] == 1.0
    assert measurements[0]["worst_family_gate_met"] is False
    assert measurements[0]["gate_met"] is False


def test_retained_rejected_result_is_strict_bound_and_zero_authority():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report, _ = load_bound(REPORT, RESULT_SCHEMA, "result_sha256")
    Draft202012Validator(schema).validate(report)
    core = {key: value for key, value in report.items() if key != "result_sha256"}
    assert report["result_sha256"] == sha256_bytes(canonical(core))
    assert report["status"] == "FAILED_DEVELOPMENT_GATE"
    assert report["selected_threshold"] is None
    assert report["selected_measurement"] is None
    assert not any(row["gate_met"] for row in report["threshold_measurements"])
    assert not any(row["locally_separable"] for row in report["target_separation"])
    assert report["evaluation_count"] == 0
    assert report["evaluation_opened"] is False
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False
