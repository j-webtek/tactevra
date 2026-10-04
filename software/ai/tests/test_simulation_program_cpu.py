from __future__ import annotations

import json
from pathlib import Path

from rocell_ai.simulation_program_cpu import (
    CANDIDATE_MODE,
    calibration_budget,
    calibration_attribution,
    candidate_catalog_semantic_check,
    continuous_policy_smoke,
    collision_candidate,
    gpu_readiness,
    load_program_fixture,
    mid_motion_mask_smoke,
    recovery_sweep,
    run_all,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/simulation_program_cpu_fixtures_v1.json"


def test_fixture_is_section_hashed_and_zero_authority():
    fixture = load_program_fixture(FIXTURE)
    assert fixture["gpu_execution_authorized"] is False
    assert fixture["runtime_stack"]["nvidia_driver"] == "595.97"
    assert fixture["runtime_stack"]["warp"] == "1.17.0"
    assert set(fixture["counters"].values()) == {0}
    assert set(fixture["sections"]) == {"workstream_1_cpu", "workstream_2",
                                         "workstream_3", "workstream_4",
                                         "workstream_5", "workstream_6",
                                         "workstream_5_attribution", "collision_candidate"}


def test_candidate_mode_is_separate_and_installed_rejection_remains():
    result = candidate_catalog_semantic_check(load_program_fixture(FIXTURE))
    assert result["mode"] == CANDIDATE_MODE
    assert result["candidate_installed"] is False
    assert "SHIFT" in result["installed_expected_rejection"]
    assert result["cases"][0]["replayed_text"] == "Hello 2026!"
    assert any(case["text"] == "!!" for case in result["cases"])


def test_recovery_fails_closed_and_calibration_preserves_failures():
    fixture = load_program_fixture(FIXTURE)
    recovery = recovery_sweep(fixture)
    assert recovery["ambiguous_continuations"] == 0
    assert recovery["recoverable_success_rate"] == 1.0
    budget = calibration_budget(fixture)
    assert budget["status"] == "EXPLORATORY_CPU_COMPLETE"
    assert budget["admitted_rows"] > 0
    assert budget["failed_rows"] > 0


def test_continuous_pair_enumeration_and_mid_motion_mask_sentinels():
    fixture = load_program_fixture(FIXTURE)
    policy = continuous_policy_smoke(fixture)
    assert policy["ordered_pair_count"] == 51 ** 2
    assert policy["recommended_policy"] is None
    masks = mid_motion_mask_smoke(fixture)
    assert masks["positive_arm_mask_overlap"] is True
    assert masks["decisions"]["covered"] == "ABSTAIN_ARM_COVERED"
    assert masks["physical_mid_motion_use"] == "BLOCKED"


def test_ws5_attribution_and_collision_candidate_remain_exploratory():
    fixture = load_program_fixture(FIXTURE)
    attribution = calibration_attribution(fixture)
    assert attribution["insufficient_cell_count"] == 15
    assert attribution["factor_ranking"][0] in {"noise_mm", "initial_bias_mm", "target_fraction"}
    candidate = collision_candidate(fixture, workspace=ROOT)
    assert len(candidate["robot_bodies"]) == 7
    assert len(candidate["workcell_bodies"]) == 6
    assert candidate["installed_profile_eligible"] is False
    assert candidate["simulation_diagnostic_ready"] is False
    assert candidate["commands"] == []


def test_combined_receipt_is_deterministic_and_gpu_blocked():
    first = run_all(FIXTURE)
    second = run_all(FIXTURE)
    assert first == second
    assert gpu_readiness(load_program_fixture(FIXTURE))["gpu_execution_authorized"] is False
    assert not any(first["counters"].values())
    json.dumps(first, allow_nan=False)
