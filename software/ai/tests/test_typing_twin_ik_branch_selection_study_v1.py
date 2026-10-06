from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell_ai.typing_twin_ik_branch_selection_study_v1 import (
    FIXTURE_SCHEMA,
    _load_fixture,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/typing_twin_ik_branch_selection_fixture_v1_1.json"
PRESERVED_FIXTURE = (
    ROOT / "software/ai/sim/evidence/typing_twin_ik_branch_selection_fixture_v1.json"
)
PRESERVED_RESULT = (
    ROOT / "software/ai/sim/evidence/typing_twin_ik_branch_selection_result_v1.json"
)
REPRODUCED_RESULT = (
    ROOT / "software/ai/sim/evidence/typing_twin_ik_branch_selection_result_v1_1.json"
)


def test_frozen_fixture_is_hash_bound_and_zero_authority() -> None:
    document = _load_fixture(FIXTURE, ROOT)

    assert document["schema"] == FIXTURE_SCHEMA
    assert document["search"]["beam_widths"] == [2, 4, 8]
    assert document["decision_rules"]["route_waypoint_count_exact"] == 260
    assert all(value == 0 for value in document["counters"].values())
    assert document["decision_rules"]["authority_bearing_output_count_maximum"] == 0


def test_fixture_rejects_mutation(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["beam_widths"] = [1]
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture hash changed"):
        _load_fixture(altered, ROOT)


def test_bound_inputs_match_exact_bytes() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for binding in document["input_bindings"].values():
        source = ROOT / binding["path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == binding["sha256"]


def test_compatibility_reproduction_preserves_original_evidence() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    correction = document["compatibility_reproduction"]

    assert correction["results_seen_before_correction"] is True
    assert correction["rules_changed"] is False
    assert PRESERVED_FIXTURE.is_file()
    assert PRESERVED_RESULT.is_file()


def test_compatibility_reproduction_retains_decision_and_beam_metrics() -> None:
    original = json.loads(PRESERVED_RESULT.read_text(encoding="utf-8"))
    reproduced = json.loads(REPRODUCED_RESULT.read_text(encoding="utf-8"))
    metric_fields = (
        "beam_width",
        "accepted_waypoint_count",
        "solver_call_count",
        "candidate_evaluation_count",
        "first_failure",
        "selected_minimum_normalized_arm_joint_margin",
    )

    assert reproduced["decision"] == original["decision"]
    assert [
        {field: beam[field] for field in metric_fields}
        for beam in reproduced["beam_results"]
    ] == [
        {field: beam[field] for field in metric_fields}
        for beam in original["beam_results"]
    ]
    assert reproduced["hardware_writes"] == 0
    assert reproduced["physical_movements"] == 0
    assert reproduced["physical_authority"] is False
