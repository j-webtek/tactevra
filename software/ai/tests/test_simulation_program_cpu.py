from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from rocell_ai.simulation_program_cpu import (
    CANDIDATE_MODE,
    calibration_budget,
    calibration_attribution,
    candidate_catalog_semantic_check,
    continuous_policy_smoke,
    collision_candidate,
    phase0_collision_intake,
    landing_sensor_comparison,
    gpu_readiness,
    load_program_fixture,
    mid_motion_mask_smoke,
    recovery_sweep,
    run_all,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/simulation_program_cpu_fixtures_v1.json"
WS2_FIXTURE = ROOT / "software/ai/sim/evidence/workstream_2_key_press_physics_v1.json"
WS2_EXECUTION = (
    ROOT / "software/ai/sim/evidence/workstream_2_key_press_execution_v1.json"
)
WS2_FIXTURE_V2 = (
    ROOT / "software/ai/sim/evidence/workstream_2_key_press_physics_v2.json"
)
WS2_EXECUTION_V2 = (
    ROOT / "software/ai/sim/evidence/workstream_2_key_press_execution_v2.json"
)
WS2_STAGED = ROOT / "software/ai/sim/evidence/workstream_2_staged_search_v1.json"
WS2_STAGED_V2 = ROOT / "software/ai/sim/evidence/workstream_2_staged_search_v2.json"
WS2_STAGED_V3 = ROOT / "software/ai/sim/evidence/workstream_2_staged_search_v3.json"
WS2_MECHANISMS = (
    ROOT / "software/ai/sim/evidence/workstream_2_keyboard_mechanisms_v1.json"
)
WS2_VECTOR_FIXTURE = (
    ROOT
    / "software/ai/sim/evidence/workstream_2_stage_a_vectorized_throughput_v2_1.json"
)
WS2_VECTOR_SPEC = importlib.util.spec_from_file_location(
    "run_ws2_stage_a_vectorized_throughput",
    ROOT / "software/ai/sim/run_ws2_stage_a_vectorized_throughput.py",
)
assert WS2_VECTOR_SPEC and WS2_VECTOR_SPEC.loader
WS2_VECTOR_RUNNER = importlib.util.module_from_spec(WS2_VECTOR_SPEC)
WS2_VECTOR_SPEC.loader.exec_module(WS2_VECTOR_RUNNER)
WS2_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_key_press_physics_probe",
    ROOT / "software/integrations/mujoco_warp/key_press_physics_probe.py",
)
WS2_PROBE = importlib.util.module_from_spec(WS2_SPEC)
assert WS2_SPEC.loader is not None
WS2_SPEC.loader.exec_module(WS2_PROBE)
WS2_EVENT_FIXTURE = (
    ROOT / "software/ai/sim/evidence/ws2_event_terminated_press_v1_4.json"
)
WS2_EVENT_SPEC = importlib.util.spec_from_file_location(
    "run_ws2_event_terminated_press",
    ROOT / "software/ai/sim/run_ws2_event_terminated_press.py",
)
assert WS2_EVENT_SPEC and WS2_EVENT_SPEC.loader
WS2_EVENT_RUNNER = importlib.util.module_from_spec(WS2_EVENT_SPEC)
WS2_EVENT_SPEC.loader.exec_module(WS2_EVENT_RUNNER)
WS2_EVENT_CONTROL_FIXTURE = (
    ROOT / "software/ai/sim/evidence/ws2_event_hard_limit_control_v1.json"
)
WS2_EVENT_CONTROL_SPEC = importlib.util.spec_from_file_location(
    "run_ws2_event_hard_limit_control",
    ROOT / "software/ai/sim/run_ws2_event_hard_limit_control.py",
)
assert WS2_EVENT_CONTROL_SPEC and WS2_EVENT_CONTROL_SPEC.loader
WS2_EVENT_CONTROL_RUNNER = importlib.util.module_from_spec(WS2_EVENT_CONTROL_SPEC)
WS2_EVENT_CONTROL_SPEC.loader.exec_module(WS2_EVENT_CONTROL_RUNNER)
WS2_EVENT_CONTROL_FIXTURE_V2 = (
    ROOT / "software/ai/sim/evidence/ws2_event_hard_limit_control_v2.json"
)
WS2_EVENT_CONTROL_SPEC_V2 = importlib.util.spec_from_file_location(
    "run_ws2_event_hard_limit_control_v2",
    ROOT / "software/ai/sim/run_ws2_event_hard_limit_control_v2.py",
)
assert WS2_EVENT_CONTROL_SPEC_V2 and WS2_EVENT_CONTROL_SPEC_V2.loader
WS2_EVENT_CONTROL_RUNNER_V2 = importlib.util.module_from_spec(WS2_EVENT_CONTROL_SPEC_V2)
WS2_EVENT_CONTROL_SPEC_V2.loader.exec_module(WS2_EVENT_CONTROL_RUNNER_V2)


def test_fixture_is_section_hashed_and_zero_authority():
    fixture = load_program_fixture(FIXTURE)
    assert fixture["gpu_execution_authorized"] is False
    assert fixture["runtime_stack"]["nvidia_driver"] == "595.97"
    assert fixture["runtime_stack"]["warp"] == "1.17.0"
    assert set(fixture["counters"].values()) == {0}
    assert set(fixture["sections"]) == {
        "workstream_1_cpu",
        "workstream_2",
        "workstream_3",
        "workstream_4",
        "workstream_5",
        "workstream_6",
        "workstream_5_attribution",
        "collision_candidate",
        "phase0_collision_mode",
        "phase0_landing_sensors",
    }


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
    assert policy["ordered_pair_count"] == 51**2
    assert policy["recommended_policy"] is None
    masks = mid_motion_mask_smoke(fixture)
    assert masks["positive_arm_mask_overlap"] is True
    assert masks["decisions"]["covered"] == "ABSTAIN_ARM_COVERED"
    assert masks["physical_mid_motion_use"] == "BLOCKED"


def test_ws5_attribution_and_collision_candidate_remain_exploratory():
    fixture = load_program_fixture(FIXTURE)
    attribution = calibration_attribution(fixture)
    assert attribution["insufficient_cell_count"] == 15
    assert attribution["factor_ranking"][0] in {
        "noise_mm",
        "initial_bias_mm",
        "target_fraction",
    }
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
    assert (
        gpu_readiness(load_program_fixture(FIXTURE))["gpu_execution_authorized"]
        is False
    )
    assert not any(first["counters"].values())
    json.dumps(first, allow_nan=False)


def test_phase0_sensor_comparison_is_deterministic_and_selects_nothing():
    fixture = load_program_fixture(FIXTURE)
    first = landing_sensor_comparison(fixture)
    assert first == landing_sensor_comparison(fixture)
    assert first["selected_option"] is None
    assert first["target_count"] == 51
    assert len(first["options"]) == 3
    assert first["overhead_camera_contact_visibility"].startswith("OCCLUDED")
    assert first["hardware_write_count"] == first["physical_movement_count"] == 0


def test_phase0_collision_candidate_runs_but_cannot_release_gates():
    result = phase0_collision_intake(load_program_fixture(FIXTURE), workspace=ROOT)
    assert result["mode"] == "EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE"
    assert result["installed_profile_eligible"] is False
    assert result["variant_count"] > 10
    assert result["pose_count_per_variant"] == 46
    assert result["decision"] == "STOP"
    assert result["status_counts"].get("BLOCKED_INCOMPLETE_POSE", 0) == 0
    assert result["status_counts"].get("COLLISION_DETECTED", 0) > 0
    assert result["hardware_write_count"] == result["physical_movement_count"] == 0


def test_ws2_executable_manifest_is_exact_and_zero_authority():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION, workspace=ROOT, parent=fixture
    )
    staged = WS2_PROBE.load_staged_fixture(
        WS2_STAGED, workspace=ROOT, parent=fixture, execution=execution
    )
    first = WS2_PROBE.build_manifest(fixture, workspace=ROOT)
    second = WS2_PROBE.build_manifest(fixture, workspace=ROOT)
    assert first == second
    assert first["target_count"] == 51
    assert first["physical_profile_count"] == 19
    assert first["tip_geometry_count"] == 12
    assert first["recipe_count"] == 96
    assert first["landing_scenario_count"] == 4
    assert first["physics_world_count"] == 285_769_728
    assert first["physical_authority"] is False
    assert not first["real_commands"]
    assert execution["smoke"]["expected_world_count"] == 64
    assert execution["smoke"]["devices"] == ["cuda:0", "cuda:1"]
    assert staged["stage_a_coarse"]["expected_worlds"] == 4_465_152
    assert WS2_PROBE.coarse_recipe_indices(fixture, staged) == [
        0,
        17,
        90,
        47,
        82,
        89,
        6,
        33,
        34,
        71,
        41,
        49,
    ]


def test_event_terminated_speed_limit_and_failure_paths():
    assert WS2_PROBE.event_terminated_speed_limit_mm_s(
        actuation_mm=1.8,
        bottom_out_mm=3.0,
        latency_ms=40.0,
        reserved_margin_mm=0.2,
    ) == pytest.approx(25.0)
    assert WS2_PROBE.event_terminated_speed_limit_mm_s(
        actuation_mm=1.8,
        bottom_out_mm=3.0,
        latency_ms=5.0,
        reserved_margin_mm=0.2,
    ) == pytest.approx(200.0)
    with pytest.raises(ValueError, match="reserved margin consumes"):
        WS2_PROBE.event_terminated_speed_limit_mm_s(
            actuation_mm=1.8,
            bottom_out_mm=3.0,
            latency_ms=40.0,
            reserved_margin_mm=1.2,
        )
    assert (
        WS2_PROBE.primary_failure(
            {"partial_press": True, "no_event_before_hard_limit": True}
        )
        == "NO_EVENT_BEFORE_HARD_LIMIT"
    )
    assert (
        WS2_PROBE.primary_failure(
            {"no_event_before_hard_limit": True, "late_event_ignored": True}
        )
        == "LATE_EVENT_IGNORED"
    )
    assert (
        WS2_PROBE.primary_failure({"wrong_key_event": True, "neighbor_contact": False})
        == "WRONG_KEY_EVENT"
    )


def test_event_terminated_fixture_and_control_are_fail_closed():
    fixture = WS2_EVENT_RUNNER.load_fixture(WS2_EVENT_FIXTURE)
    assert fixture["design"]["latency_ms_range"] == [5.0, 40.0]
    assert fixture["design"]["initial_target_ids"] == ["GRAVE", "EQUAL"]
    assert set(fixture["counters"].values()) == {0}
    campaign, _, physical = WS2_EVENT_RUNNER.load_bound(fixture)
    control = WS2_EVENT_RUNNER._control(
        fixture,
        physical=physical,
        target_id="GRAVE",
        profile_id="travel_mm__LOW",
        scenario_id="MID_SOURCE_MID_RESIDUAL",
        latency_ms=40.0,
        mode="MATCHING",
        approach_mm_s=20.0,
    )["control"]
    assert control["physical_keycap_half_extent_mm"] == [7.0, 7.0]
    assert control["event_termination"] == {
        "source": "MODELED_HOST_KEYSTROKE_EVENT",
        "mode": "MATCHING",
        "latency_ms": 40.0,
        "expected_target_id": "GRAVE",
        "reported_target_id": "GRAVE",
        "hard_depth_limit_mm": 5.0703125,
        "reserved_bottom_out_margin_mm": 0.2,
        "no_retry": True,
        "may_only_shorten_motion": True,
    }
    profile = next(
        row
        for row in WS2_PROBE.physical_profiles(campaign)
        if row["profile_id"] == "travel_mm__LOW"
    )
    limit, selected = WS2_EVENT_RUNNER._event_speed(fixture, profile, 40.0)
    assert limit == pytest.approx(5.0)
    assert selected == pytest.approx(4.0)


def test_event_hard_limit_control_is_inside_compliant_window():
    fixture = WS2_EVENT_CONTROL_RUNNER.load_fixture(WS2_EVENT_CONTROL_FIXTURE)
    design = fixture["design"]
    assert design["actuation_plus_tool_compression_mm"] == pytest.approx(
        3.3272727272727276
    )
    assert design["bottom_out_plus_tool_compression_mm"] == pytest.approx(
        5.545454545454546
    )
    assert (
        design["actuation_plus_tool_compression_mm"]
        < design["hard_depth_limit_mm"]
        < design["bottom_out_plus_tool_compression_mm"]
    )
    parent_fixture = WS2_EVENT_RUNNER.load_fixture(WS2_EVENT_FIXTURE)
    _, _, physical = WS2_EVENT_RUNNER.load_bound(parent_fixture)
    control = WS2_EVENT_CONTROL_RUNNER._control(fixture, parent_fixture, physical)[
        "control"
    ]
    assert control["recipe_override"]["approach_mm_s"] == pytest.approx(0.5)
    assert control["event_termination"]["hard_depth_limit_mm"] == pytest.approx(5.0)
    assert {row["vertical_origin_offset_mm"] for row in control["batch_rows"]} == {0.0}


def test_event_hard_limit_control_tampering_stops(tmp_path: Path):
    fixture = json.loads(WS2_EVENT_CONTROL_FIXTURE.read_text(encoding="utf-8"))
    fixture["design"]["hard_depth_limit_mm"] = 6.0
    fixture_without_hash = {
        key: value for key, value in fixture.items() if key != "fixture_sha256"
    }
    fixture["fixture_sha256"] = WS2_EVENT_CONTROL_RUNNER.value_sha(fixture_without_hash)
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="declared compliant window"):
        WS2_EVENT_CONTROL_RUNNER.load_fixture(path)


def test_deeper_event_mechanism_control_stays_below_compliant_bottom_out():
    fixture = WS2_EVENT_CONTROL_RUNNER_V2.load_fixture(WS2_EVENT_CONTROL_FIXTURE_V2)
    design = fixture["design"]
    assert design["nominal_simulated_press_depth_mm"] == pytest.approx(5.4)
    assert design["hard_depth_limit_mm"] < design["bottom_out_plus_tool_compression_mm"]
    parent_fixture = WS2_EVENT_RUNNER.load_fixture(WS2_EVENT_FIXTURE)
    _, _, physical = WS2_EVENT_RUNNER.load_bound(parent_fixture)
    control = WS2_EVENT_CONTROL_RUNNER_V2._control(fixture, parent_fixture, physical)[
        "control"
    ]
    assert control["recipe_override"]["press_depth_mm"] == pytest.approx(5.4)
    assert control["event_termination"]["hard_depth_limit_mm"] == pytest.approx(5.4)


def test_ws2_runtime_amendment_changes_only_stack_identity():
    original = WS2_PROBE.load_fixture(WS2_FIXTURE, workspace=ROOT)
    amended = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION_V2, workspace=ROOT, parent=amended
    )
    assert amended["runtime_stack"]["mujoco_warp"] == "3.14.0"
    assert amended["runtime_stack"]["warp"] == "1.18.0"
    assert amended["runtime_compatibility_amendment"]["status"] == (
        "PRE_RESULT_RUNTIME_ONLY_AMENDMENT"
    )
    for key in (
        "contact_model",
        "landing_model",
        "recipe_design",
        "decision",
        "metrics",
        "counters",
    ):
        assert amended[key] == original[key]
    assert execution["smoke"]["expected_world_count"] == 64
    assert execution["physical_authority"] is False
    assert not any(execution["counters"].values())


def test_ws2_compliant_stage_a_expands_every_identity_before_gpu_execution():
    original = WS2_PROBE.load_fixture(WS2_FIXTURE, workspace=ROOT)
    original_execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION, workspace=ROOT, parent=original
    )
    original_staged = WS2_PROBE.load_staged_fixture(
        WS2_STAGED, workspace=ROOT, parent=original, execution=original_execution
    )
    amended = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    amended_execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION_V2, workspace=ROOT, parent=amended
    )
    amended_staged = WS2_PROBE.load_staged_fixture(
        WS2_STAGED_V2,
        workspace=ROOT,
        parent=amended,
        execution=amended_execution,
    )
    for key in (
        "boundary_rule",
        "stop_and_fallback",
        "normalized_recipe_space",
        "throughput_decision",
        "counters",
    ):
        assert amended_staged[key] == original_staged[key]
    assert amended_staged["tool_compliance"]["combination_count"] == 6
    assert amended_staged["tool_compliance"]["stiffness_n_per_mm"] == [
        0.0715,
        0.143,
        0.286,
    ]
    assert amended_staged["tool_compliance"]["travel_mm"] == [3.0, 6.0]
    assert amended_staged["reference_superset"]["contact_worlds"] == (
        original_staged["reference_superset"]["contact_worlds"] * 6
    )
    assert amended_staged["reference_superset"]["scored_rows"] == (
        original_staged["reference_superset"]["scored_rows"] * 6
    )
    assert (
        amended_staged["stage_a_coarse"]["landing_sample_indices"]
        == (original_staged["stage_a_coarse"]["landing_sample_indices"])
    )
    assert (
        amended_staged["stage_a_coarse"]["recipe_selection"]
        == (original_staged["stage_a_coarse"]["recipe_selection"])
    )
    assert (
        amended_staged["stage_b_refinement"]["maximum_new_recipe_indices_per_boundary"]
        == original_staged["stage_b_refinement"][
            "maximum_new_recipe_indices_per_boundary"
        ]
    )
    assert (
        amended_staged["stage_c_confirmation"]["selection"]
        == (original_staged["stage_c_confirmation"]["selection"])
    )
    assert WS2_PROBE.coarse_recipe_indices(amended, amended_staged) == [
        0,
        17,
        90,
        47,
        82,
        89,
        6,
        33,
        34,
        71,
        41,
        49,
    ]
    assert amended_staged["stage_a_coarse"]["expected_worlds"] == 26_790_912


def test_ws2_debounce_successor_freezes_hold_and_throughput_populations():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION_V2, workspace=ROOT, parent=fixture
    )
    staged = WS2_PROBE.load_staged_fixture(
        WS2_STAGED_V3, workspace=ROOT, parent=fixture, execution=execution
    )
    registration = staged["switch_closure"]
    assert registration["minimum_duration_ms_samples"] == [5.0, 15.0, 30.0]
    samples = registration["minimum_duration_ms_samples"]
    maximum = registration["maximum_duration_ms"]
    assert not WS2_PROBE.keyboard_hold_window_admitted(
        29.999, debounce_samples_ms=samples, maximum_hold_ms=maximum
    )
    assert WS2_PROBE.keyboard_hold_window_admitted(
        30.0, debounce_samples_ms=samples, maximum_hold_ms=maximum
    )
    assert WS2_PROBE.keyboard_hold_window_admitted(
        150.0, debounce_samples_ms=samples, maximum_hold_ms=maximum
    )
    assert not WS2_PROBE.keyboard_hold_window_admitted(
        150.001, debounce_samples_ms=samples, maximum_hold_ms=maximum
    )
    row = {
        "finite": True,
        "overflow_zero": True,
        "neighbor_contact": False,
        "bottom_out_overflow": False,
        "auto_repeat_count": 0,
        "double_actuation": False,
        "actuation_count": 1,
        "partial_press": False,
        "debounce_hold_complete": False,
        "release_complete": True,
        "force_within_available": True,
    }
    assert WS2_PROBE.primary_failure(row) == "DEBOUNCE_TOO_SHORT"
    row["actuation_count"] = 0
    row["partial_press"] = True
    assert WS2_PROBE.primary_failure(row) == "PARTIAL_PRESS"
    throughput = staged["throughput_decision"]
    assert (
        throughput["full_grid_if"][
            "projected_two_gpu_wall_hours_at_median_smoke_rate_lte"
        ]
        == 12.0
    )
    population = staged["stage_a_coarse"]["throughput_selected_compliance"]
    assert population["inside_budget"] == [
        "k0.0715_t3",
        "k0.0715_t6",
        "k0.143_t3",
        "k0.143_t6",
        "k0.286_t3",
        "k0.286_t6",
    ]
    assert staged["stage_a_coarse"]["full_compliance_expected_worlds"] == 26_790_912
    assert population["over_budget"] == [
        "k0.0715_t3",
        "k0.0715_t6",
        "k0.286_t3",
        "k0.286_t6",
    ]
    assert staged["stage_a_coarse"]["coarse_compliance_expected_worlds"] == 17_860_608
    assert staged["stage_b_refinement"]["compliance_refinement_if_stage_a_over_budget"][
        "omitted_stage_a_combinations"
    ] == ["k0.143_t3", "k0.143_t6"]
    assert population["selection_made_only_from_frozen_smoke_throughput"] is True
    assert staged["physical_authority"] is False
    assert not any(staged["counters"].values())


def test_ws2_stage_a_batches_are_homogeneous_and_exact():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION_V2, workspace=ROOT, parent=fixture
    )
    staged = WS2_PROBE.load_staged_fixture(
        WS2_STAGED_V3, workspace=ROOT, parent=fixture, execution=execution
    )
    batches = WS2_PROBE.stage_a_homogeneous_batches(fixture, staged, workspace=ROOT)
    assert len(batches) == 65_664
    assert sum(row["world_count"] for row in batches) == 17_860_608
    assert sorted({row["world_count"] for row in batches}) == [32, 672, 832]
    assert {row["tool_compliance"]["compliance_id"] for row in batches} == {
        "k0.0715_t3",
        "k0.0715_t6",
        "k0.286_t3",
        "k0.286_t6",
    }
    assert all(
        len({tuple(row["half_extent_mm"])}) == 1
        and row["world_count"] == len(row["rows"])
        for row in batches
    )
    assert (
        abs(
            sum(row["world_count"] for row in batches if row["device"] == "cuda:0")
            - sum(row["world_count"] for row in batches if row["device"] == "cuda:1")
        )
        <= 832
    )


def test_ws2_key_mechanisms_separate_safe_regions_from_physical_geometry():
    fixture = json.loads(WS2_MECHANISMS.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    assert WS2_PROBE._sha_value(fixture) == claimed
    fixture["fixture_sha256"] = claimed
    for binding in fixture["bindings"].values():
        path = Path(binding["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
    semantics = fixture["geometry_semantics"]
    assert semantics["catalog_half_extent"] == (
        "PRESS_SAFE_REGION_ONLY_NOT_KEYCAP_COLLISION_GEOMETRY"
    )
    stabilized = fixture["mechanism_classes"]["STABILIZED_UNMEASURED"]
    assert stabilized["target_ids"] == ["SHIFT", "ENTER", "SPACE"]
    assert stabilized["prospective_target_ids"] == ["BACKSPACE"]
    assert fixture["known_physical_keycap_top_mm"]["SHIFT"]["value"] == [37.76, 14.8]
    assert fixture["known_physical_keycap_top_mm"]["ENTER"]["value"] is None
    assert fixture["known_physical_keycap_top_mm"]["SPACE"]["value"] is None
    assert fixture["mechanism_classes"]["WIDE_UNSTABILIZED_GEOMETRY_UNMEASURED"][
        "target_ids"
    ] == ["TAB"]
    assert fixture["stage_a_partition"]["missing_physical_geometry"] == "STOP"
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_ws2_vectorized_ordinary_batch_keeps_mechanism_compiled():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION_V2, workspace=ROOT, parent=fixture
    )
    staged = WS2_PROBE.load_staged_fixture(
        WS2_STAGED_V3, workspace=ROOT, parent=fixture, execution=execution
    )
    rows = WS2_PROBE.stage_a_vectorized_ordinary_batch_rows(
        fixture, staged, target_id="G"
    )
    assert len(rows) == 1_536
    assert {row["target_id"] for row in rows} == {"G"}
    assert len({row["scenario_id"] for row in rows}) == 4
    assert len({row["landing_sample_index"] for row in rows}) == 8
    assert len({row["recipe_index"] for row in rows}) == 12
    assert {row["compliance_id"] for row in rows} == {
        "k0.0715_t3",
        "k0.0715_t6",
        "k0.286_t3",
        "k0.286_t6",
    }
    assert len({WS2_PROBE._sha_value(row) for row in rows}) == len(rows)


def test_ws2_vectorized_throughput_fixture_stays_non_authorizing():
    fixture = WS2_VECTOR_RUNNER.load_fixture(WS2_VECTOR_FIXTURE)
    assert fixture["population"]["worlds_per_compiled_batch"] == 1_536
    assert fixture["population"]["ordinary_compiled_batch_count"] == 10_260
    assert fixture["population"]["ordinary_world_count"] == 26_790_912
    assert fixture["population"]["physical_neighborhood_signature_count"] == 45
    assert fixture["population"]["blocked_special_targets"] == []
    left = {
        "device": "cuda:0",
        "fixture_sha256": fixture["fixture_sha256"],
        "wall_elapsed_seconds": 1.0,
        "status": "PASS_VECTORIZED_ORDINARY_DEVICE_SMOKE",
        "receipt_sha256": "a" * 64,
    }
    right = {
        **left,
        "device": "cuda:1",
        "receipt_sha256": "b" * 64,
    }
    result = WS2_VECTOR_RUNNER.compare(fixture, left, right)
    assert result["status"] == "PASS_ORDINARY_VECTORIZED_THROUGHPUT"
    assert result["stage_a_launch_authorized"] is False
    assert result["physical_authority"] is False


def test_ws2_positive_control_is_hash_bound_and_between_key_events(tmp_path: Path):
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION_V2, workspace=ROOT, parent=fixture
    )
    control = {
        "schema": "tactevra.ws2_positive_control_fixture.v1",
        "scope": "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY",
        "bindings": {
            "campaign_fixture": {
                "path": str(WS2_FIXTURE_V2),
                "sha256": WS2_PROBE._sha_file(WS2_FIXTURE_V2),
                "fixture_sha256": fixture["fixture_sha256"],
            },
            "execution_fixture": {
                "path": str(WS2_EXECUTION_V2),
                "sha256": WS2_PROBE._sha_file(WS2_EXECUTION_V2),
                "fixture_sha256": execution["fixture_sha256"],
            },
        },
        "control": {
            "control_id": "ACTUATION_REFERENCE_2P4MM",
            "target_id": "GRAVE",
            "profile_id": "BASELINE",
            "tip_id": "sphere-r1",
            "scenario_id": "HIGH_SOURCE_LOW_RESIDUAL",
            "base_recipe_index": 0,
            "landing_sample_indices": list(range(64)),
            "recipe_override": {"press_depth_mm": 2.4},
        },
        "counters": {
            "hardware_writes": 0,
            "physical_movements": 0,
            "real_commands": 0,
            "permits": 0,
            "transport_operations": 0,
        },
        "physical_authority": False,
    }
    control["fixture_sha256"] = WS2_PROBE._sha_value(control)
    path = tmp_path / "positive_control.json"
    path.write_text(json.dumps(control), encoding="utf-8")
    loaded = WS2_PROBE.load_positive_control_fixture(
        path, workspace=ROOT, parent=fixture, execution=execution
    )
    assert loaded["control"]["recipe_override"]["press_depth_mm"] == 2.4

    control.pop("fixture_sha256")
    control["control"]["recipe_override"]["press_depth_mm"] = 3.0
    control["fixture_sha256"] = WS2_PROBE._sha_value(control)
    path.write_text(json.dumps(control), encoding="utf-8")
    try:
        WS2_PROBE.load_positive_control_fixture(
            path, workspace=ROOT, parent=fixture, execution=execution
        )
    except ValueError as exc:
        assert "between actuation and bottom-out" in str(exc)
    else:
        raise AssertionError("bottom-out positive control was admitted")


def test_ws2_release_control_requires_long_settle_and_scores_both_depth_margins(
    tmp_path: Path,
):
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION_V2, workspace=ROOT, parent=fixture
    )
    control = {
        "schema": "tactevra.ws2_release_control_fixture.v1",
        "scope": "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY",
        "bindings": {
            "campaign_fixture": {
                "path": str(WS2_FIXTURE_V2),
                "sha256": WS2_PROBE._sha_file(WS2_FIXTURE_V2),
                "fixture_sha256": fixture["fixture_sha256"],
            },
            "execution_fixture": {
                "path": str(WS2_EXECUTION_V2),
                "sha256": WS2_PROBE._sha_file(WS2_EXECUTION_V2),
                "fixture_sha256": execution["fixture_sha256"],
            },
        },
        "control": {
            "control_id": "RELEASE_REFERENCE_FULL_RETRACT_2S",
            "control_kind": "RELEASE",
            "target_id": "GRAVE",
            "profile_id": "BASELINE",
            "tip_id": "sphere-r1",
            "scenario_id": "HIGH_SOURCE_LOW_RESIDUAL",
            "base_recipe_index": 0,
            "landing_sample_indices": list(range(64)),
            "recipe_override": {"press_depth_mm": 2.4},
            "release_protocol_override": {
                "additional_settle_seconds": 2.0,
                "position_error_limit_mm": 0.05,
                "velocity_limit_mm_s": 0.05,
            },
        },
        "counters": {
            "hardware_writes": 0,
            "physical_movements": 0,
            "real_commands": 0,
            "permits": 0,
            "transport_operations": 0,
        },
        "physical_authority": False,
    }
    control["fixture_sha256"] = WS2_PROBE._sha_value(control)
    path = tmp_path / "release_control.json"
    path.write_text(json.dumps(control), encoding="utf-8")
    loaded = WS2_PROBE.load_positive_control_fixture(
        path, workspace=ROOT, parent=fixture, execution=execution
    )
    assert loaded["control"]["control_kind"] == "RELEASE"

    margins = WS2_PROBE.depth_margin_metrics(2.4, 1.8, 3.0)
    assert margins == {
        "actuation_margin_mm": pytest.approx(0.6),
        "bottom_out_margin_mm": pytest.approx(0.6),
        "minimum_depth_margin_mm": pytest.approx(0.6),
        "midpoint_error_mm": pytest.approx(0.0),
    }

    control.pop("fixture_sha256")
    control["control"]["release_protocol_override"]["additional_settle_seconds"] = 0.5
    control["fixture_sha256"] = WS2_PROBE._sha_value(control)
    path.write_text(json.dumps(control), encoding="utf-8")
    with pytest.raises(ValueError, match="at least one second"):
        WS2_PROBE.load_positive_control_fixture(
            path, workspace=ROOT, parent=fixture, execution=execution
        )


def test_ws2_compliant_tool_topology_and_validation():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE_V2, workspace=ROOT)
    catalog = json.loads(
        (ROOT / fixture["bindings"]["candidate_catalog"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    profile = WS2_PROBE.physical_profiles(fixture)[0]
    tip = WS2_PROBE.tip_geometries(fixture)[0]
    target = next(
        row for row in WS2_PROBE._target_records(catalog) if row["target_id"] == "GRAVE"
    )
    compliance = {
        "stiffness_n_per_mm": 0.143,
        "damping_n_s_per_mm": 0.01,
        "travel_mm": 6.0,
    }
    xml = WS2_PROBE.build_contact_mjcf(
        fixture,
        profile,
        tip,
        target["half_extent_mm"],
        float(catalog["keyboard"]["pitch_mm"]),
        compliance,
    )
    assert 'joint name="tool_compliance"' in xml
    mujoco = pytest.importorskip("mujoco")
    model = mujoco.MjModel.from_xml_string(xml)
    assert model.nq == 10
    assert model.nmocap == 1
    assert model.joint("tool_compliance").qposadr[0] == 9
    with pytest.raises(ValueError, match="exact stiffness"):
        WS2_PROBE.build_contact_mjcf(
            fixture,
            profile,
            tip,
            target["half_extent_mm"],
            float(catalog["keyboard"]["pitch_mm"]),
            {"stiffness_n_per_mm": 0.143},
        )


def test_ws2_series_compliance_partitions_command_and_caps_travel():
    effective, compression, force = WS2_PROBE.series_compliance_displacement(
        2.4,
        key_stiffness_n_per_mm=1.3,
        tool_stiffness_n_per_mm=0.143,
        tool_travel_mm=6.0,
    )
    assert effective + compression == pytest.approx(2.4)
    assert force == pytest.approx(0.143 * compression)
    assert effective < compression

    effective, compression, force = WS2_PROBE.series_compliance_displacement(
        7.0,
        key_stiffness_n_per_mm=1.3,
        tool_stiffness_n_per_mm=0.143,
        tool_travel_mm=3.0,
    )
    assert compression == pytest.approx(3.0)
    assert effective == pytest.approx(4.0)
    assert force == pytest.approx(0.429)

    with pytest.raises(ValueError, match="physical domain"):
        WS2_PROBE.series_compliance_displacement(
            2.4,
            key_stiffness_n_per_mm=1.3,
            tool_stiffness_n_per_mm=0.0,
            tool_travel_mm=6.0,
        )


def test_ws2_tampering_and_cross_gpu_drift_stop():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE, workspace=ROOT)
    left = {
        "device": "cuda:0",
        "fixture_sha256": fixture["fixture_sha256"],
        "rows": [
            {
                "row_id": "sentinel",
                "actuation_count": 1,
                "auto_repeat_count": 0,
                "neighbor_contact": False,
                "bottom_out_overflow": False,
                "release_complete": True,
                "force_within_available": True,
                "peak_penetration_mm": 2.0,
                "peak_required_force_n": 0.5,
                "dwell_above_actuation_ms": 100.0,
                "actuation_margin_mm": 0.2,
                "bottom_out_margin_mm": 1.0,
                "minimum_depth_margin_mm": 0.2,
                "midpoint_error_mm": 0.4,
                "final_position_error_mm": 0.0,
                "final_velocity_mm_s": 0.0,
            }
        ],
    }
    right = deepcopy(left)
    right["device"] = "cuda:1"
    assert WS2_PROBE.compare_receipts(fixture, left, right)["row_count"] == 1
    right["rows"][0]["peak_required_force_n"] += 2e-6
    try:
        WS2_PROBE.compare_receipts(fixture, left, right)
    except ValueError as exc:
        assert "continuous disagreement" in str(exc)
    else:
        raise AssertionError("cross-GPU metric drift was admitted")


def test_ws2_phone_state_model_preserves_long_press_failures():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE, workspace=ROOT)
    rows = WS2_PROBE.phone_cells(fixture)
    assert len(rows) == 27
    assert any(row["admitted"] for row in rows)
    assert any(row["long_press"] and not row["admitted"] for row in rows)


def test_ws2_staged_refinement_is_deterministic_and_boundary_only():
    fixture = WS2_PROBE.load_fixture(WS2_FIXTURE, workspace=ROOT)
    execution = WS2_PROBE.load_execution_fixture(
        WS2_EXECUTION, workspace=ROOT, parent=fixture
    )
    staged = WS2_PROBE.load_staged_fixture(
        WS2_STAGED, workspace=ROOT, parent=fixture, execution=execution
    )
    coarse = WS2_PROBE.coarse_recipe_indices(fixture, staged)
    rows = []
    for recipe_index in coarse:
        for landing_index in staged["stage_a_coarse"]["landing_sample_indices"]:
            admitted = not (recipe_index == 0 and landing_index == 0)
            rows.append(
                {
                    "target_id": "GRAVE",
                    "profile_id": "BASELINE",
                    "tip_id": "sphere-r1",
                    "scenario_id": "HIGH_SOURCE_LOW_RESIDUAL",
                    "recipe_index": recipe_index,
                    "landing_sample_index": landing_index,
                    "admitted": admitted,
                    "actuation_count": int(admitted),
                    "partial_press": not admitted,
                    "auto_repeat_count": 0,
                    "neighbor_contact": False,
                    "bottom_out_overflow": False,
                    "release_complete": True,
                    "force_within_available": True,
                }
            )
    first = WS2_PROBE.refinement_plan(fixture, staged, rows)
    assert first == WS2_PROBE.refinement_plan(fixture, staged, rows)
    assert first["boundary_count"] > 0
    assert first["refinement_identity_count"] > 0
    assert all(
        row["recipe_index"] not in coarse for row in first["refinement_identities"]
    )
    assert first["physical_authority"] is False
