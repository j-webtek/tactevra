from __future__ import annotations

import json
from pathlib import Path

import pytest

from rocell.kinematics import ARM_JOINT_NAMES

from rocell_ai.typing_twin_ik_endpoint_manifold_study_v1 import (
    _limiting_joints,
    _load_fixture,
    _normalized_margins,
    _offsets,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    ROOT
    / "software/ai/sim/evidence/typing_twin_ik_endpoint_manifold_fixture_v1.json"
)
RESULT = (
    ROOT
    / "software/ai/sim/evidence/typing_twin_ik_endpoint_manifold_result_v1.json"
)


def test_offset_grid_is_exact_and_contains_endpoint() -> None:
    axis = [-5.0, 0.0, 5.0]
    rows = _offsets(axis)

    assert len(rows) == 27
    assert len(set(rows)) == 27
    assert (0.0, 0.0, 0.0) in rows


def test_normalized_margin_and_limiting_joint_are_explicit() -> None:
    bounds = {name: (-1.0, 1.0) for name in ARM_JOINT_NAMES}
    solution = {name: 0.0 for name in ARM_JOINT_NAMES}
    solution[ARM_JOINT_NAMES[0]] = 0.9
    margins = _normalized_margins(solution, bounds)

    assert margins[ARM_JOINT_NAMES[0]] == pytest.approx(0.05)
    assert _limiting_joints(margins) == (ARM_JOINT_NAMES[0],)


def test_frozen_fixture_is_hash_bound_and_zero_authority() -> None:
    if not FIXTURE.exists():
        pytest.skip("fixture is committed in the next pre-result increment")
    document = _load_fixture(FIXTURE, ROOT)

    assert document["decision_rules"]["point_count_exact"] == 729
    assert document["search"]["axis_offsets_mm"] == [
        -20.0,
        -15.0,
        -10.0,
        -5.0,
        0.0,
        5.0,
        10.0,
        15.0,
        20.0,
    ]
    assert all(value == 0 for value in document["counters"].values())


def test_fixture_rejects_mutation(tmp_path: Path) -> None:
    if not FIXTURE.exists():
        pytest.skip("fixture is committed in the next pre-result increment")
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["axis_offsets_mm"] = [0.0]
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture hash changed"):
        _load_fixture(altered, ROOT)


def test_result_reports_endpoint_and_zero_authority() -> None:
    if not RESULT.exists():
        pytest.skip("result is committed after the frozen study")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert result["sampled_point_count"] == 729
    assert result["exact_hover"]["offset_mm"] == [0.0, 0.0, 0.0]
    assert result["hardware_writes"] == 0
    assert result["physical_movements"] == 0
    assert result["physical_authority"] is False
