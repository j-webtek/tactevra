from __future__ import annotations

import json
from pathlib import Path

import pytest

from rocell_ai.first_motion_consolidated import (
    _require_configuration,
    load_consolidated_fixture,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_consolidated_v1.json"


def test_fixture_binds_the_converged_zero_authority_configuration() -> None:
    fixture = load_consolidated_fixture(FIXTURE, workspace=ROOT)
    configuration = fixture["configuration"]
    assert configuration["tool_length_mm"] == 110.0
    assert configuration["tip_radius_mm"] == 3.0
    assert configuration["moving_cable_present"] is False
    assert configuration["park_pose_id"] == "halton-0573"
    assert configuration["path_pattern"] == ["RISE", "TRANSIT", "DESCEND"]
    assert configuration["station_geometry"] == "CONTROLLED_REAL_STATION_CAD"
    assert configuration["stage_d_mode"] == (
        "TRAY_REPLACES_KEYBOARD_AND_NEIGHBOR_STATIONS")
    assert configuration["stage_ef_target_count"] == 51
    assert not any(fixture["counters"].values())
    assert fixture["physical_authority"] is False


def test_fixture_rejects_tampering(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["configuration"]["tip_radius_mm"] = 4.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash mismatch"):
        load_consolidated_fixture(changed, workspace=ROOT)


def test_every_stage_rejects_a_configuration_mismatch() -> None:
    fixture = load_consolidated_fixture(FIXTURE, workspace=ROOT)
    expected = fixture["configuration"]["section_sha256"]
    for stage in "ABCDEF":
        _require_configuration(
            {"stage": stage, "configuration_sha256": expected}, expected)
        with pytest.raises(ValueError, match="stage configuration mismatch"):
            _require_configuration(
                {"stage": stage, "configuration_sha256": "0" * 64}, expected)
