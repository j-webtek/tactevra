from __future__ import annotations

import json
from pathlib import Path

import pytest

from rocell_ai.first_motion_consolidated import (
    _require_configuration,
    load_consolidated_fixture,
    run_consolidated_rehearsal,
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


def test_consolidated_rehearsal_covers_a_to_f_and_retains_physical_block() -> None:
    result = run_consolidated_rehearsal(
        load_consolidated_fixture(FIXTURE, workspace=ROOT), workspace=ROOT)
    assert result["decision"] == "PASS_ALL_STAGES_SIMULATION_ONLY_PHYSICAL_BLOCKED"
    assert result["stages_satisfied_simulation_only"] == list("ABCDEF")
    assert result["first_stop_stage"] is None
    assert result["stage_c_exact_sweep"]["target_count"] == 51
    assert result["stage_c_exact_sweep"]["row_count"] == 102
    assert result["stage_c_exact_sweep"]["stop_count"] == 0
    assert result["stage_ef"]["row_count"] == 408
    assert result["stage_ef"]["pass_row_count"] == 408
    assert result["station_cad_contact_count"] == 0
    assert result["predicted_telemetry_sample_count"] == 198
    assert result["independent_observers"]["undetected_consequential_count"] == 0
    assert result["official_readiness"] == "NOT_READY_FOR_FIRST_POWERED_MOTION"
    assert result["hardware_write_count"] == result["physical_movement_count"] == 0
    assert result["real_command_count"] == result["transport_count"] == 0
    assert result["physical_authority"] is False
