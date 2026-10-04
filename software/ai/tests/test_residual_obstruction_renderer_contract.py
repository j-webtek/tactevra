from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.build_residual_obstruction_renderer_contract import build  # noqa: E402


FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v2.json"
SOURCE = REPO_ROOT / "software" / "integrations" / "isaac_sim" / "evidence" / "fixed_fixture_practice_v1" / "manifest.json"
CONTRACT = AI_ROOT / "sim" / "evidence" / "residual_obstruction_renderer_contract_v1.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_renderer_contract_v1.schema.json"


def test_renderer_contract_is_deterministic_exact_and_zero_authority():
    first = build(FIXTURE, SOURCE)
    second = build(FIXTURE, SOURCE)
    assert first == second
    assert first["base_scene"]["sample_id"] == "hover_t__nominal"
    assert first["base_scene"]["target_count"] == 75
    assert first["warp_policy"]["target_geometry_uses_same_affine"] is True
    assert first["admission"]["adjacent_distractor_must_differ_from_clear"] is True
    assert first["evaluation_group_present"] is False
    assert first["images_generated"] is False
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_retained_renderer_contract_matches_schema_and_builder():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(CONTRACT.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == build(FIXTURE, SOURCE)


def test_altered_fixture_is_rejected(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["images_generated"] = True
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build(path, SOURCE)


def test_altered_source_image_is_rejected(tmp_path):
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    sample = next(item for item in source["samples"] if item["sample_id"] == "hover_t__nominal")
    sample["image_sha256"] = "0" * 64
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build(FIXTURE, path)
