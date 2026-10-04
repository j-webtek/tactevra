from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.build_residual_obstruction_successor_v3 import build  # noqa: E402


SOURCE = REPO_ROOT / "software" / "integrations" / "isaac_sim" / "evidence" / "fixed_fixture_practice_v1" / "manifest.json"
DIAGNOSTIC = AI_ROOT / "eval" / "residual_obstruction_v2_diagnostic_v1.json"
FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v3.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_successor_fixture_v3.schema.json"


def test_v3_is_deterministic_scene_isolated_and_zero_authority():
    first = build(SOURCE, DIAGNOSTIC)
    assert first == build(SOURCE, DIAGNOSTIC)
    training = {row["scene_id"] for row in first["base_scenes"] if row["split"] == "training"}
    development = {row["scene_id"] for row in first["base_scenes"] if row["split"] == "development"}
    assert len(training) == 8
    assert len(development) == 4
    assert training.isdisjoint(development)
    assert all(row["fresh_render_required"] for row in first["base_scenes"])
    assert first["split_policy"]["evaluation_observation_count"] == 0
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_v3_addresses_diagnostic_with_3d_and_invariance_contracts():
    result = build(SOURCE, DIAGNOSTIC)
    admission = result["render_admission"]
    assert admission["renderer"] == "ISAAC_SIM_3D"
    assert admission["source_image_warp_prohibited"] is True
    assert admission["mesh_geometry_required_for_physical_obstructions"] is True
    assert admission["depth_prohibited_as_model_input"] is True
    cable = next(row for row in result["variants"] if row["variant_id"] == "cable_translucent")
    assert cable["geometry"]["opacity"] == [0.45, 0.8]
    assert result["training_plan"]["losses"]["appearance_consistency"] == "PAIRED_LOGIT_HUBER"
    assert result["development_gate"]["every_target_margin_must_be_strictly_positive"] is True


def test_retained_v3_fixture_matches_schema_and_builder():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(FIXTURE.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == build(SOURCE, DIAGNOSTIC)


def test_altered_diagnostic_is_rejected(tmp_path):
    payload = json.loads(DIAGNOSTIC.read_text(encoding="utf-8"))
    payload["checkpoint_changed"] = True
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
