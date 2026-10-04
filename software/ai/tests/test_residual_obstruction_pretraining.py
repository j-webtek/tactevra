from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))

from train.build_residual_obstruction_pretraining import (  # noqa: E402
    RESULT_SCHEMA,
    load_bound,
    materialize,
    score_thresholds,
    verify_dataset,
)


FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_pretraining_v1.json"
SOURCE = REPO_ROOT / "software" / "integrations" / "isaac_sim" / "evidence" / "fixed_fixture_practice_v1" / "manifest.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_development_v1.schema.json"
REPORT = AI_ROOT / "eval" / "residual_obstruction_development_v1.json"


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    output = tmp_path_factory.mktemp("residual-data") / "dataset"
    manifest = materialize(FIXTURE, SOURCE, output)
    return output, manifest


def test_materialized_dataset_is_exact_and_zero_authority(dataset):
    output, first = dataset
    verified = verify_dataset(FIXTURE, output)
    assert verified == first
    assert verified["file_count"] == 1200
    assert {entry["split"] for entry in verified["files"]} == {"training", "development"}
    assert verified["evaluation_group_present"] is False
    assert verified["hardware_writes"] == 0
    assert verified["physical_movements"] == 0
    assert verified["physical_authority"] is False


def test_materialization_is_byte_deterministic(tmp_path, dataset):
    _, first = dataset
    second_dir = tmp_path / "second"
    second = materialize(FIXTURE, SOURCE, second_dir)
    assert second == first
    first_hashes = [entry["sha256"] for entry in first["files"]]
    second_hashes = [entry["sha256"] for entry in second["files"]]
    assert second_hashes == first_hashes


def test_changed_or_extra_dataset_file_is_rejected(dataset):
    output, manifest = dataset
    changed = output / manifest["files"][0]["path"]
    original = changed.read_bytes()
    try:
        changed.write_bytes(original + b"changed")
        with pytest.raises(ValueError, match="dataset file changed"):
            verify_dataset(FIXTURE, output)
    finally:
        changed.write_bytes(original)
    extra = output / "extra.png"
    try:
        extra.write_bytes(b"extra")
        with pytest.raises(ValueError, match="missing or extra"):
            verify_dataset(FIXTURE, output)
    finally:
        extra.unlink()


def test_target_cluster_scoring_is_seeded_and_conservative():
    labels = np.asarray([1, 1, 0, 0] * 4, dtype=np.float32)
    probabilities = np.asarray([0.99, 0.98, 0.02, 0.01] * 4, dtype=np.float32)
    targets = [target for target in ("A", "B", "C", "D") for _ in range(4)]
    first = score_thresholds(labels, probabilities, targets, [0.5], 200, 19017)
    second = score_thresholds(labels, probabilities, targets, [0.5], 200, 19017)
    assert first == second
    assert first[0]["gate_met"] is True
    assert first[0]["missed_obstruction_cluster_upper"] == 0
    assert first[0]["visible_false_stop_cluster_upper"] == 0


def test_retained_report_is_strict_and_has_no_authority():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report = load_bound(REPORT, RESULT_SCHEMA, "result_sha256")
    Draft202012Validator(schema).validate(report)
    assert report["evaluation_count"] == 0
    assert report["evaluation_opened"] is False
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False
