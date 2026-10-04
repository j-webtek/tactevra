from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.amend_residual_v5_pre_render import build  # noqa: E402


V5 = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5.json"
RESULT = AI_ROOT / "eval/residual_obstruction_v5_1_pre_render_v1.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_1_pre_render_v1.schema.json"
COMMIT = "aacbda9aeeb2e808d167b9fbba0aeeb98c424cd3"


def _build() -> dict:
    return build(source_commit=COMMIT, v5_path=V5, trials=5000, seed=55101)


def test_v5_1_restores_gates_and_blocks_underpowered_render() -> None:
    result = _build()
    assert result["gate_correction"]["maximum_pooled_all_obstruction_miss_rate"] == 0.02
    assert result["gate_correction"]["maximum_visible_false_stop_rate"] == 0.06
    assert result["lighting_scope"]["status"] == "PROVISIONAL_SYNTHETIC_ONLY_UNMEASURED"
    assert result["lighting_scope"]["may_select_hardware_remedy"] is False
    assert result["original_plan"] == {
        "development_scene_count": 8,
        "development_observations": 21600,
        "passes_power_target": False,
    }
    assert result["recommendation"]["minimum_tested_scene_count"] == 256
    assert result["recommendation"]["minimum_development_observations"] == 691200
    assert result["status"] == "BLOCKED_RENDER_PENDING_POWERED_FIXTURE_REVISION"
    assert result["images_generated"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0


def test_retained_v5_1_is_deterministic_and_valid() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(RESULT.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == _build()
