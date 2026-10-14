from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG = (
    WORKSPACE
    / "hardware/static_overhead_camera/config/commercial_tripod_candidate.json"
)
SCHEMA = CONFIG.with_name("commercial_tripod_candidate.schema.json")


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads(CONFIG.read_text(encoding="utf-8")),
        json.loads(SCHEMA.read_text(encoding="utf-8")),
    )


def test_selected_tripod_is_strictly_non_authorizing_and_unqualified() -> None:
    candidate, schema = _documents()
    jsonschema.Draft202012Validator(schema).validate(candidate)

    assert candidate["decision_state"] == "SELECTED_UNQUALIFIED"
    assert candidate["product"]["asin"] == "B0CSYB4YQ2"
    assert candidate["architecture"]["support_type"] == (
        "independent_commercial_floor_tripod"
    )
    assert candidate["architecture"]["primary_load_bearing_printed_part_allowed"] is False
    assert candidate["study_pose"]["commissioned"] is False
    assert candidate["authority"] == {
        "planning": True,
        "simulation": True,
        "fabrication": False,
        "physical_installation": False,
        "motion": False,
        "contact": False,
    }


@pytest.mark.parametrize(
    ("section", "field", "unsafe_value"),
    [
        ("authority", "physical_installation", True),
        ("authority", "motion", True),
        ("authority", "contact", True),
        ("study_pose", "commissioned", True),
        ("architecture", "primary_load_bearing_printed_part_allowed", True),
    ],
)
def test_schema_rejects_unearned_authority(
    section: str, field: str, unsafe_value: object
) -> None:
    candidate, schema = _documents()
    changed = copy.deepcopy(candidate)
    changed[section][field] = unsafe_value

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(changed)


def test_candidate_preserves_measurement_and_historical_requirements() -> None:
    candidate, _ = _documents()
    measurements = candidate["required_measurements"]
    gates = candidate["qualification_gates"]
    retained = candidate["historical_retention"]

    assert any("mount thread" in item for item in measurements)
    assert any("sag" in item for item in measurements)
    assert any("swept volume" in item for item in gates)
    assert any("safety tether" in item for item in gates)
    assert any("byte-for-byte" in item for item in retained)
