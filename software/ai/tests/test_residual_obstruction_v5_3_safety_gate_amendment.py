from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.build_residual_v5_safety_gate_amendment import build  # noqa: E402

V5 = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5.json"
V5_2 = AI_ROOT / "eval/residual_obstruction_v5_2_power_attribution_v1.json"
RESULT = AI_ROOT / "eval/residual_obstruction_v5_3_safety_gate_amendment_v1.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_3_safety_gate_amendment_v1.schema.json"
COMMIT = "c8a9e4d0ffd89e035087afe783deb6cfdc8dfcd6"


def _build() -> dict:
    return build(source_commit=COMMIT, v5_path=V5, v5_2_path=V5_2, trials=20000, seed=55301)


def test_safety_gates_and_diagnostics_have_separate_roles() -> None:
    result = _build()
    roles = result["gate_roles"]
    safety = roles["single_use_evaluation_safety_gates"]
    assert safety["maximum_pooled_all_obstruction_miss_upper"] == 0.02
    assert safety["maximum_cable_family_miss_upper"] == 0.02
    assert safety["maximum_dark_cable_30_60_miss_upper"] == 0.02
    assert safety["maximum_visible_false_stop_upper"] == 0.06
    diagnostics = roles["development_candidate_selection"]
    assert diagnostics["diagnostic_floors"] == {
        "minimum_every_target_auc": 0.90,
        "minimum_linear_q05_target_auc": 0.95,
    }
    assert "LINEAR_Q05_TARGET_QUANTILE_MARGIN" in diagnostics["reported_not_powered"]


def test_balanced_rotation_powers_all_four_safety_gates_with_cushion() -> None:
    result = _build()
    rotation = result["evaluation_rotation"]
    assert rotation["recommended_scene_count"] == 224
    assert rotation["recommended_evaluation_observations"] == 96768
    assert rotation["minimum_target_scene_exposures"] == 35
    pessimistic = next(row for row in rotation["scenarios"] if row["scenario_id"] == "PESSIMISTIC_ICC_0_30")
    chosen = next(row for row in pessimistic["candidates"] if row["scene_count"] == 224)
    assert chosen["bonferroni_joint_lower_bound"] == 0.93055
    assert set(chosen["marginal_power"]) == {
        "pooled_all_obstruction_miss",
        "cable_family_miss",
        "dark_cable_30_60_miss",
        "visible_false_stop",
    }
    assert rotation["render_authorized"] is False
    assert rotation["exact_rotation_frozen"] is False


def test_retained_safety_amendment_is_deterministic_and_valid() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(RESULT.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == _build()
