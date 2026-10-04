from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.diagnose_residual_obstruction_development import (  # noqa: E402
    OUTPUT_SCHEMA,
    analyze,
    load_model,
)
from train.build_residual_obstruction_pretraining import load_bound  # noqa: E402


SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_development_diagnostic_v1.schema.json"
REPORT = AI_ROOT / "eval" / "residual_obstruction_development_diagnostic_v1.json"


def test_retained_diagnostic_is_strict_and_bound():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report = load_bound(REPORT, OUTPUT_SCHEMA, "report_sha256")
    Draft202012Validator(schema).validate(report)
    assert report["development_count"] == 600
    assert report["target_separation"]["nonseparable_count"] == 75
    assert report["dataset_identity_diagnostics"]["byte_identical_clear_adjacent_pair_count"] == 75
    assert report["global_probability"]["pairwise_auc"] == pytest.approx(0.7585185185185185)
    assert report["highest_visible_variant"] == "none_adjacent_distractor"
    assert report["lowest_obstruction_variant"] == "image_degraded"


def test_diagnostic_has_zero_authority_and_preserves_candidate():
    report = load_bound(REPORT, OUTPUT_SCHEMA, "report_sha256")
    assert report["checkpoint_changed"] is False
    assert report["threshold_changed"] is False
    assert report["evaluation_opened"] is False
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_analysis_attributes_variants_and_targets_deterministically():
    rows = [
        {"variant_id": "clear", "target_id": "A", "expected_decision": "VISIBLE"},
        {"variant_id": "blocked", "target_id": "A", "expected_decision": "ABSTAIN"},
        {"variant_id": "clear", "target_id": "B", "expected_decision": "VISIBLE"},
        {"variant_id": "blocked", "target_id": "B", "expected_decision": "ABSTAIN"},
    ]
    probabilities = np.asarray([0.1, 0.9, 0.2, 0.8], dtype=np.float32)
    first = analyze(rows, probabilities)
    second = analyze(rows, probabilities)
    assert first == second
    assert first["global_probability"]["pairwise_auc"] == 1.0
    assert first["target_separation"]["locally_separable_count"] == 2


def test_model_loader_rejects_invalid_or_truncated_bytes(tmp_path):
    invalid = tmp_path / "invalid.bin"
    invalid.write_bytes(b"not-a-model")
    with pytest.raises(ValueError, match="magic mismatch"):
        load_model(invalid)
