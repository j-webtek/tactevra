from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.plan_residual_v4_gate_power import build as build_power  # noqa: E402
from sim.build_residual_obstruction_successor_v4_1 import build  # noqa: E402


V4 = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v4.json"
DIAGNOSTIC = AI_ROOT / "eval" / "residual_v3_memorization_diagnostic_v1.json"
POWER = AI_ROOT / "eval" / "residual_v4_gate_power_v1.json"
FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v4_1.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_successor_fixture_v4_1.schema.json"


def test_power_receipt_rejects_per_target_binary_error_gates():
    result = build_power(V4)
    assert result == json.loads(POWER.read_text())
    assert result["per_target_obstruction_gate"]["maximum_95pct_upper_bound_pass_failures"] == 1
    assert result["per_target_visible_gate"]["maximum_95pct_upper_bound_pass_failures"] == 1
    assert result["recommended_gate"]["per_target_binary_error_gate"] is False


def test_v4_1_corrects_lighting_difference_and_outlier_gates():
    result = build(V4, DIAGNOSTIC, POWER)
    assert result == build(V4, DIAGNOSTIC, POWER)
    reference = result["reference_contract"]
    assert reference["reference_lighting_seed_independent_of_observation"] is True
    assert reference["reference_observation_lighting_mismatch_required_in_training"] is True
    assert reference["photometric_normalization_precedes_difference"] is True
    normalization = result["training_plan"]["photometric_normalization"]
    assert normalization["raw_difference_channel_prohibited"] is True
    assert result["development_gate"]["strict_extreme_margin_is_diagnostic_only"] is True
    assert result["development_gate"]["per_target_binary_error_gate"] is False


def test_retained_v4_1_matches_schema_and_builder():
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    retained = json.loads(FIXTURE.read_text())
    Draft202012Validator(schema).validate(retained)
    assert retained == build(V4, DIAGNOSTIC, POWER)
    assert retained["hardware_writes"] == retained["physical_movements"] == 0
    assert retained["physical_authority"] is False
