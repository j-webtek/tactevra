from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.build_residual_obstruction_successor_v5 import build  # noqa: E402


REMEDY = AI_ROOT / "eval/residual_obstruction_v4_2_remedy_classification_v1.json"
ROBUSTNESS = AI_ROOT / "eval/residual_obstruction_v4_2_robustness_v1.json"
V4_2 = AI_ROOT / "sim/evidence/residual_obstruction_successor_v4_2.json"
FIXTURE = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_successor_fixture_v5.schema.json"
COMMIT = "8944f6a02534b414858777b050113c8b8ced1e86"


def _build() -> dict:
    return build(
        source_commit=COMMIT,
        remedy_path=REMEDY,
        robustness_path=ROBUSTNESS,
        v4_2_path=V4_2,
    )


def test_v5_freezes_disjoint_assets_inputs_and_gates() -> None:
    result = _build()
    identities = result["split_identities"]
    for category in ("scenes", "lighting", "obstruction_assets"):
        groups = identities[category]
        assert set(groups["training"]).isdisjoint(groups["development"])
        assert set(groups["training"]).isdisjoint(groups["evaluation"])
        assert set(groups["development"]).isdisjoint(groups["evaluation"])
    assert result["render_contract"]["training_observations"] == 43200
    assert result["render_contract"]["development_observations"] == 21600
    assert result["render_contract"]["evaluation_images_generated"] == 0
    assert result["candidate_models"][0]["candidate_id"] == "V5_EDGE_TEXTURE_96"
    assert "SOBEL_MAGNITUDE_DIFFERENCE" in result["candidate_models"][0]["channels"]
    assert result["candidate_models"][1]["context_size_px"] == 192
    assert result["development_gates"]["maximum_cable_family_missed_rate"] == 0.02
    assert result["end_to_end_follow_on"]["wrong_target_contacts_allowed"] == 0
    assert result["evaluation_opened"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0
    assert result["physical_authority"] is False


def test_retained_v5_matches_schema_and_builder() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(FIXTURE.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    assert retained == _build()


def test_v5_rejects_rewritten_v4_2_failure(tmp_path: Path) -> None:
    changed = copy.deepcopy(json.loads(ROBUSTNESS.read_text(encoding="utf-8")))
    changed["selected_threshold"] = 0.55
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="threshold/evaluation state changed"):
        build(
            source_commit=COMMIT,
            remedy_path=REMEDY,
            robustness_path=path,
            v4_2_path=V4_2,
        )
