from __future__ import annotations

from pathlib import Path
import hashlib
import json

import pytest

from rocell.models import Point3Mm

from rocell_ai.typing_twin_ik_cartesian_corridor_study_v1 import (
    FIXTURE_SCHEMA,
    _candidate_trajectory,
    _corridor_points,
    _load_fixture,
)
from rocell_ai.typing_twin_ik_collision_v1 import _load_fixture as _load_parent_fixture
from rocell_ai.typing_twin_ik_route_study_v1 import _build_pipeline


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    ROOT
    / "software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_fixture_v1_1.json"
)
PRESERVED_FIXTURE = (
    ROOT / "software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_fixture_v1.json"
)
PRESERVED_FAILURE = (
    ROOT
    / "software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_failed_attempt_v1.json"
)


def test_frozen_fixture_is_hash_bound_and_zero_authority() -> None:
    document = _load_fixture(FIXTURE, ROOT)

    assert document["schema"] == FIXTURE_SCHEMA
    assert document["search"]["height_above_start_mm"] == [0.0, 20.0, 40.0]
    assert document["search"]["planar_orders"] == [
        "DIAGONAL",
        "X_THEN_Y",
        "Y_THEN_X",
    ]
    assert document["decision_rules"]["candidate_count_exact"] == 9
    assert all(value == 0 for value in document["counters"].values())


def test_fixture_rejects_mutation(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["height_above_start_mm"] = [0.0]
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture hash changed"):
        _load_fixture(altered, ROOT)


def test_bound_inputs_match_exact_bytes() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for binding in document["input_bindings"].values():
        source = ROOT / binding["path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == binding["sha256"]


def test_amendment_preserves_pre_result_failure() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    amendment = document["preexecution_amendment"]

    assert amendment["results_seen_before_amendment"] is False
    assert PRESERVED_FIXTURE.is_file()
    assert PRESERVED_FAILURE.is_file()


def test_corridor_families_preserve_endpoints() -> None:
    start = Point3Mm("board", 305.0, 185.0, 118.5)
    hover = Point3Mm("board", 216.5, 154.0, 31.0)

    for order in ("DIAGONAL", "X_THEN_Y", "Y_THEN_X"):
        points = _corridor_points(
            start,
            hover,
            height_above_start_mm=20.0,
            planar_order=order,
        )
        assert points[0] == start
        assert points[-1] == hover
        assert all(point.frame == "board" for point in points)


def test_axis_order_changes_only_planar_transit() -> None:
    start = Point3Mm("board", 305.0, 185.0, 118.5)
    hover = Point3Mm("board", 216.5, 154.0, 31.0)
    x_then_y = _corridor_points(
        start, hover, height_above_start_mm=40.0, planar_order="X_THEN_Y"
    )
    y_then_x = _corridor_points(
        start, hover, height_above_start_mm=40.0, planar_order="Y_THEN_X"
    )

    assert x_then_y[2] == Point3Mm("board", hover.x, start.y, start.z + 40.0)
    assert y_then_x[2] == Point3Mm("board", start.x, hover.y, start.z + 40.0)
    assert x_then_y[-2] == y_then_x[-2]


def test_zero_height_avoids_duplicate_start() -> None:
    start = Point3Mm("board", 305.0, 185.0, 118.5)
    hover = Point3Mm("board", 216.5, 154.0, 31.0)
    points = _corridor_points(
        start, hover, height_above_start_mm=0.0, planar_order="DIAGONAL"
    )

    assert points == (
        start,
        Point3Mm("board", hover.x, hover.y, start.z),
        hover,
    )


def test_candidate_rejoins_exact_baseline_after_first_hover() -> None:
    parent_path = (
        ROOT / "software/ai/sim/evidence/typing_twin_ik_collision_fixture_v1_4.json"
    )
    parent = _load_parent_fixture(parent_path, ROOT)
    *_, execution, baseline = _build_pipeline(parent, ROOT)
    candidate = _candidate_trajectory(
        baseline,
        execution,
        height_above_start_mm=20.0,
        planar_order="X_THEN_Y",
    )
    candidate_first_hover = next(
        index
        for index, waypoint in enumerate(candidate.phase_waypoints)
        if waypoint.phase.value == "HOVER" and waypoint.target_id == "H"
    )

    assert candidate.phase_waypoints[candidate_first_hover].point == (
        baseline.phase_waypoints[1].point
    )
    assert [
        (item.phase, item.action_index, item.target_id, item.point)
        for item in candidate.phase_waypoints[candidate_first_hover:]
    ] == [
        (item.phase, item.action_index, item.target_id, item.point)
        for item in baseline.phase_waypoints[1:]
    ]
    assert (
        max(
            (
                (left.point.x - right.point.x) ** 2
                + (left.point.y - right.point.y) ** 2
                + (left.point.z - right.point.z) ** 2
            )
            ** 0.5
            for left, right in zip(
                candidate.screening_samples, candidate.screening_samples[1:]
            )
        )
        <= baseline.policy.maximum_cartesian_step_mm + 1e-6
    )
