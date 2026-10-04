from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.analyze_residual_v5_power_attribution import build  # noqa: E402

V5 = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5.json"
V5_1 = AI_ROOT / "eval/residual_obstruction_v5_1_pre_render_v1.json"
RESULT = AI_ROOT / "eval/residual_obstruction_v5_2_power_attribution_v1.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_2_power_attribution_v1.schema.json"
COMMIT = "d8c3103169663a6dcc3e611261834afbea64df56"


def _build() -> dict:
    return build(source_commit=COMMIT, v5_path=V5, v5_1_path=V5_1, trials=5000, seed=55201)


def test_attribution_finds_limiting_and_unmodeled_gates() -> None:
    result = _build()
    moderate = result["original_eight_scene_attribution"]["MODERATE_ICC_0_05"]
    assert moderate["limiting_gates"] == ["every_target_auc"]
    statuses = {row["gate"]: row["power_status"] for row in result["gate_inventory"]}
    assert statuses["linear_q05_target_auc_ge_0_98"] == "UNMODELED_ZERO_DECLARED_EFFECT_SLACK"
    assert statuses["linear_q05_target_quantile_margin_ge_0_05"] == "UNMODELED_MISSING_MARGIN_EFFECT_AND_VARIANCE"
    assert result["assumed_true_performance"]["target_auc_slack_above_q05_gate"] == 0.0


def test_balanced_rotation_reduces_rows_without_authorizing_render() -> None:
    result = _build()
    pessimistic = next(row for row in result["balanced_rotation_analysis"]["designs_by_scenario"] if row["scenario_id"] == "PESSIMISTIC_ICC_0_30")
    sparse = next(row for row in pessimistic["designs"] if row["targets_per_scene"] == 24)
    assert sparse["development_observations"] == 221184
    assert sparse["minimum_target_scene_exposures"] == 81
    assert sparse["modeled_gate_power"]["limiting_modeled_marginal_power"] >= 0.90
    assert sparse["modeled_gate_power"]["bonferroni_joint_lower_bound"] == 0.897144
    assert result["balanced_rotation_analysis"]["observation_reduction_fraction"] == 0.68
    assert result["status"] == "BLOCKED_GATE_MODEL_AND_FIXTURE_REVISION_REQUIRED"
    assert result["images_generated"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0


def test_retained_attribution_is_deterministic_and_schema_valid() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(RESULT.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == _build()
