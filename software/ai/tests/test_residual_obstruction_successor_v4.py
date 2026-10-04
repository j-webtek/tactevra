from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.build_residual_obstruction_successor_v4 import build  # noqa: E402


SOURCE = REPO_ROOT / "software" / "integrations" / "isaac_sim" / "evidence" / "fixed_fixture_practice_v1" / "manifest.json"
AUDIT = AI_ROOT / "eval" / "residual_obstruction_v3_training_audit_v1.json"
REVIEW = AI_ROOT / "eval" / "residual_obstruction_v3_training_visual_review_v1.json"
FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v4.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_successor_fixture_v4.schema.json"


def test_v4_is_deterministic_group_isolated_and_zero_authority():
    first = build(SOURCE, AUDIT, REVIEW)
    assert first == build(SOURCE, AUDIT, REVIEW)
    scenes = {
        split: {row["scene_id"] for row in first["base_scenes"] if row["split"] == split}
        for split in ("training", "development", "evaluation")
    }
    appearances = {
        split: {row["appearance_id"] for row in first["appearances"] if row["split"] == split}
        for split in ("training", "development", "evaluation")
    }
    assert [len(scenes[name]) for name in scenes] == [12, 8, 8]
    assert [len(appearances[name]) for name in appearances] == [4, 4, 4]
    assert scenes["training"].isdisjoint(scenes["development"] | scenes["evaluation"])
    assert scenes["development"].isdisjoint(scenes["evaluation"])
    assert appearances["training"].isdisjoint(appearances["development"] | appearances["evaluation"])
    assert first["split_policy"]["evaluation_pairs_rendered"] == 0
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_v4_freezes_reference_spatial_and_memorization_contracts():
    result = build(SOURCE, AUDIT, REVIEW)
    assert result["reference_contract"]["runtime_reference_source"] == "COMMISSIONING_CAPTURE_NOT_MODEL_GENERATED"
    assert result["reference_contract"]["missing_or_stale_reference_decision"] == "ABSTAIN"
    assert result["training_plan"]["model_inputs"] == [
        "REFERENCE_RGB", "OBSERVATION_RGB", "ABSOLUTE_RGB_DIFFERENCE"
    ]
    assert result["training_plan"]["global_average_pooling_prohibited"] is True
    assert result["training_plan"]["spatial_pool_output"] == [6, 6]
    assert result["pretraining_gates"]["full_training_prohibited_until_memorization_passes"] is True
    assert result["development_gate"]["minimum_per_target_auc"] == 0.95
    assert result["development_gate"]["minimum_per_target_strict_margin"] == 0.05


def test_retained_v4_fixture_matches_schema_and_builder():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(FIXTURE.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == build(SOURCE, AUDIT, REVIEW)


def test_altered_audit_and_review_are_rejected(tmp_path):
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit["identity_geometry_baseline"]["pooled_training_auc"] = 0.9
    altered_audit = tmp_path / "audit.json"
    altered_audit.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build(SOURCE, altered_audit, REVIEW)

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    review["status"] = "FAIL"
    altered_review = tmp_path / "review.json"
    altered_review.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build(SOURCE, AUDIT, altered_review)
