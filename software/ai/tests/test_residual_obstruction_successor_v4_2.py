from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.build_residual_obstruction_successor_v4_2 import build  # noqa: E402


V4_1 = AI_ROOT / "sim/evidence/residual_obstruction_successor_v4_1.json"
SMOKE = AI_ROOT / "eval/residual_obstruction_v4_1_smoke_admission_v1.json"
FIXTURE = AI_ROOT / "sim/evidence/residual_obstruction_successor_v4_2.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_successor_fixture_v4_2.schema.json"


def test_v4_2_freezes_training_free_selector_and_cnn_uplift() -> None:
    result = build(V4_1, SMOKE)
    plan = result["training_plan"]
    assert len(plan["photometric_normalization"]["candidates"]) == 2
    assert plan["training_free_baseline"]["model_parameters"] == 0
    selector = plan["normalization_selection_rule"]
    assert selector["primary_statistic"] == "LINEAR_INTERPOLATED_Q05_PER_TARGET_AUC"
    assert selector["practical_tie_band_absolute_auc"] == 0.005
    assert selector["tie_break_normalization_id"] == "SELF_CROP_P05_P95"
    uplift = plan["cnn_baseline_uplift_gate"]
    assert uplift["minimum_pooled_auc_improvement"] == 0.02
    assert uplift["minimum_q05_per_target_auc_improvement"] == 0.02
    assert result["render_admission"]["semantic_safe_overlap_bounds"]["tool_matte_edge"] == [0.25, 0.5]
    assert result["render_admission"]["exact_training_observation_count"] == 43200
    assert result["render_admission"]["evaluation_observation_count"] == 0
    assert result["evaluation_opened"] is False


def test_retained_v4_2_matches_schema_and_builder() -> None:
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    retained = json.loads(FIXTURE.read_text())
    Draft202012Validator(schema).validate(retained)
    assert retained == build(V4_1, SMOKE)
    assert retained["hardware_writes"] == retained["physical_movements"] == 0
    assert retained["physical_authority"] is False
