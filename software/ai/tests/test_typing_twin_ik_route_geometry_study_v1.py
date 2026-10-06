from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell_ai.typing_twin_ik_route_geometry_study_v1 import (
    _load_fixture,
    run_route_geometry_study,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/typing_twin_ik_route_geometry_fixture_v1_1.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_rehashed(path: Path, document: dict[str, object]) -> None:
    document.pop("fixture_sha256", None)
    document["fixture_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def test_fixture_rejects_unhashed_grid_change(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["z_above_first_hover_mm"] = [40.0]
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash changed"):
        _load_fixture(altered, ROOT)


def test_one_candidate_smoke_is_zero_authority(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["x_offset_from_first_hover_mm"] = [0.0]
    document["search"]["y_offset_from_first_hover_mm"] = [0.0]
    document["search"]["z_above_first_hover_mm"] = [40.0]
    document["decision_rules"]["candidate_count_exact"] = 1
    document["resource_limits"]["maximum_candidates"] = 1
    smoke = tmp_path / "smoke.json"
    _write_rehashed(smoke, document)

    result = run_route_geometry_study(smoke, workspace=ROOT)

    assert result["ordered_targets"] == ["H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6"]
    assert len(result["candidate_generation"]) == 1
    assert result["controller_commands"] == []
    assert result["hardware_commands_generated"] == 0
    assert result["hardware_writes"] == 0
    assert result["physical_movements"] == 0
    assert result["physical_authority"] is False
    assert result["camera_clearance_evaluated"] is False
    assert result["collision_gate_cleared"] is False


def test_rehashed_candidate_count_mismatch_fails_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["z_above_first_hover_mm"] = [40.0]
    mismatched = tmp_path / "mismatched.json"
    _write_rehashed(mismatched, document)
    with pytest.raises(ValueError, match="grid differs"):
        run_route_geometry_study(mismatched, workspace=ROOT)


def test_no_solution_candidate_is_retained_as_blocked(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["x_offset_from_first_hover_mm"] = [-20.0]
    document["search"]["y_offset_from_first_hover_mm"] = [-20.0]
    document["search"]["z_above_first_hover_mm"] = [40.0]
    document["decision_rules"]["candidate_count_exact"] = 1
    document["resource_limits"]["maximum_candidates"] = 1
    candidate = tmp_path / "no-solution.json"
    _write_rehashed(candidate, document)

    result = run_route_geometry_study(candidate, workspace=ROOT)

    assert result["candidate_summaries"][0]["status"] == (
        "BLOCKED_CANONICAL_IK_NO_SOLUTION_EXCEPTION"
    )
    assert result["passing_candidate_count"] == 0
