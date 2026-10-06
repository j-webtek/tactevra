from __future__ import annotations

from pathlib import Path
import json

import pytest

from rocell.models import Point3Mm

from rocell_ai.typing_twin_ik_margin_aware_planner_study_v1 import (
    _halton,
    _load_fixture,
    _route_bounds,
    _sample_point,
    _steer,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    ROOT
    / "software/ai/sim/evidence/typing_twin_ik_margin_aware_planner_fixture_v1.json"
)


def test_halton_sequence_is_deterministic() -> None:
    assert [_halton(index, 2) for index in range(1, 6)] == [
        0.5,
        0.25,
        0.75,
        0.125,
        0.625,
    ]


def test_sampling_stays_inside_frozen_bounds() -> None:
    bounds = {"x": (10.0, 20.0), "y": (-5.0, 5.0), "z": (30.0, 80.0)}
    for index in range(1, 100):
        point = _sample_point(index, bounds, (2, 3, 5))
        assert bounds["x"][0] <= point.x <= bounds["x"][1]
        assert bounds["y"][0] <= point.y <= bounds["y"][1]
        assert bounds["z"][0] <= point.z <= bounds["z"][1]


def test_steer_never_exceeds_step_and_reaches_near_target() -> None:
    start = Point3Mm("board", 0.0, 0.0, 0.0)
    far = Point3Mm("board", 30.0, 40.0, 0.0)
    near = Point3Mm("board", 3.0, 4.0, 0.0)

    stepped = _steer(start, far, 5.0)
    assert stepped == Point3Mm("board", 3.0, 4.0, 0.0)
    assert _steer(start, near, 5.0) == near


def test_route_bounds_cover_exact_endpoints() -> None:
    start = Point3Mm("board", 305.0, 185.0, 118.5)
    goal = Point3Mm("board", 216.5, 154.0, 31.0)
    bounds = _route_bounds(
        start,
        goal,
        xy_padding_mm=60.0,
        lower_z_padding_mm=20.0,
        upper_z_padding_mm=80.0,
    )

    for point in (start, goal):
        assert bounds["x"][0] <= point.x <= bounds["x"][1]
        assert bounds["y"][0] <= point.y <= bounds["y"][1]
        assert bounds["z"][0] <= point.z <= bounds["z"][1]


def test_frozen_fixture_is_hash_bound_and_zero_authority() -> None:
    if not FIXTURE.exists():
        pytest.skip("fixture is committed in the next pre-result increment")
    document = _load_fixture(FIXTURE, ROOT)
    assert document["search"]["goal_bias_periods"] == [5, 11, 23]
    assert all(value == 0 for value in document["counters"].values())


def test_fixture_rejects_mutation(tmp_path: Path) -> None:
    if not FIXTURE.exists():
        pytest.skip("fixture is committed in the next pre-result increment")
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["maximum_iterations"] = 1
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture hash changed"):
        _load_fixture(altered, ROOT)
