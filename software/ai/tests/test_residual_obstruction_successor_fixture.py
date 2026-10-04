from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.build_residual_obstruction_successor_fixture import build  # noqa: E402


SOURCE = REPO_ROOT / "software" / "integrations" / "isaac_sim" / "evidence" / "fixed_fixture_practice_v1" / "manifest.json"
DIAGNOSTIC = AI_ROOT / "eval" / "residual_obstruction_development_diagnostic_v1.json"
FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v2.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_successor_fixture_v2.schema.json"


def test_successor_fixture_is_deterministic_group_isolated_and_zero_authority():
    first = build(SOURCE, DIAGNOSTIC)
    second = build(SOURCE, DIAGNOSTIC)
    assert first == second
    policy = first["split_policy"]
    assert policy["training_observation_count"] == 27000
    assert policy["development_observation_count"] == 10125
    assert policy["evaluation_observation_count"] == 0
    training_views = {row["view_id"] for row in first["view_groups"] if row["split"] == "training"}
    development_views = {row["view_id"] for row in first["view_groups"] if row["split"] == "development"}
    training_appearances = {row["appearance_id"] for row in first["appearance_groups"] if row["split"] == "training"}
    development_appearances = {row["appearance_id"] for row in first["appearance_groups"] if row["split"] == "development"}
    assert training_views.isdisjoint(development_views)
    assert training_appearances.isdisjoint(development_appearances)
    assert first["evaluation_group_present"] is False
    assert first["images_generated"] is False
    assert first["training_started"] is False
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_successor_fixes_distractor_contract_and_broadens_failed_variants():
    result = build(SOURCE, DIAGNOSTIC)
    admission = result["render_admission"]
    assert admission["adjacent_distractor_must_differ_from_clear"] is True
    assert admission["adjacent_distractor_minimum_changed_pixels"] == 64
    assert admission["adjacent_distractor_safe_region_overlap"] == 0.0
    variants = {row["variant_id"] for row in result["variants"]}
    assert {"adjacent_distractor_left", "adjacent_distractor_right"} <= variants
    assert {"cable_thin", "cable_medium", "cable_thick"} <= variants
    assert {"tool_edge", "tool_center"} <= variants
    assert {"degraded_blur_light", "degraded_blur_heavy", "degraded_compression", "degraded_motion"} <= variants
    assert result["training_plan"]["input_channels"] == ["RGB"]
    assert result["development_gate"]["visible_false_stop_rate_upper"] == 0.06


def test_retained_fixture_matches_schema_and_builder():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(FIXTURE.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == build(SOURCE, DIAGNOSTIC)


def test_altered_diagnostic_is_rejected(tmp_path):
    payload = json.loads(DIAGNOSTIC.read_text(encoding="utf-8"))
    payload["dataset_identity_diagnostics"]["byte_identical_clear_adjacent_pair_count"] = 74
    path = tmp_path / "diagnostic.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build(SOURCE, path)


def test_altered_source_authority_is_rejected(tmp_path):
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload["authority"]["hardware_write_count"] = 1
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build(path, DIAGNOSTIC)
