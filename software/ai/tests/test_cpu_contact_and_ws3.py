from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from rocell_ai.cpu_contact_and_ws3 import (
    _sha,
    assess_c02_ws3_recipe_compatibility,
    build_candidate51_pose_family,
    load_cpu_contact_fixture,
    prepare_ws3_transition_harness,
    run_stage_ef_contact_screen,
    run_phone_capacitive_matrix,
    run_ws3_transition_screen,
    validate_ws2_recipe_binding,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/cpu_contact_and_ws3_v1.json"
FIXTURE_V2 = ROOT / "software/ai/sim/evidence/cpu_contact_and_ws3_v2.json"


def _load():
    return load_cpu_contact_fixture(FIXTURE, workspace=ROOT)


def _load_v2():
    return load_cpu_contact_fixture(FIXTURE_V2, workspace=ROOT)


def _rehash_fixture(value):
    value = copy.deepcopy(value)
    value.pop("fixture_sha256", None)
    for section in value["sections"].values():
        section_copy = dict(section)
        section_copy.pop("section_sha256", None)
        section["section_sha256"] = _sha(section_copy)
    value["fixture_sha256"] = _sha(value)
    return value


def _write_c02_binding_inputs(tmp_path: Path, *, tip_id: str = "capsule-r6-m2"):
    final = {
        "schema": "tactevra.ws2_c02_final_admission.v1",
        "decision": "COMPLETE_ROBUST_UNIVERSAL_SIMULATION_ONLY",
        "campaign_receipt_sha256": "a" * 64,
        "summary": {
            "universal_families": [{
                "profile_id": "travel_mm__LOW",
                "tip_id": tip_id,
                "compliance_id": "k0.286_t6",
                "recipe_index": 80,
                "target_count": 51,
                "minimum_depth_margin_mm": 0.0408,
                "minimum_force_margin_n": 0.261,
                "motion_time_ms": 397.0,
                "recipe": {"recipe_index": 80},
            }],
        },
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    final["result_sha256"] = _sha(final)
    final_path = tmp_path / "c02-final.json"
    final_path.write_text(json.dumps(final), encoding="utf-8")
    physics = {
        "contact_model": {"tip_families": {"capsule": {
            "radius_samples_mm": [1, 3.5, 6],
            "half_length_radius_multiple_samples": [0.5, 1.25, 2],
        }}},
    }
    physics_path = tmp_path / "physics.json"
    physics_path.write_text(json.dumps(physics), encoding="utf-8")
    return final_path, physics_path


def test_c02_c03_binding_stops_on_six_vs_three_mm_tip(tmp_path):
    final_path, physics_path = _write_c02_binding_inputs(tmp_path)
    result = assess_c02_ws3_recipe_compatibility(
        c02_final_path=final_path,
        c02_final_sha256=hashlib.sha256(final_path.read_bytes()).hexdigest(),
        ws2_physics_path=physics_path,
        ws2_physics_sha256=hashlib.sha256(physics_path.read_bytes()).hexdigest(),
        c03_fixture=_load_v2(),
    )
    assert result["decision"] == "STOP_C02_C03_TOOL_IDENTITY_MISMATCH"
    assert result["c02_tip_geometry"]["radius_mm"] == 6.0
    assert result["c03_expected_tip_geometry"]["radius_mm"] == 3.0
    assert result["recipe_envelope_emitted"] is False
    assert result["all_pairs_screen_executed"] is False
    assert result["physical_authority"] is False


def test_c02_c03_binding_rejects_changed_final_bytes(tmp_path):
    final_path, physics_path = _write_c02_binding_inputs(tmp_path)
    with pytest.raises(ValueError, match="final-admission file hash mismatch"):
        assess_c02_ws3_recipe_compatibility(
            c02_final_path=final_path,
            c02_final_sha256="0" * 64,
            ws2_physics_path=physics_path,
            ws2_physics_sha256=hashlib.sha256(physics_path.read_bytes()).hexdigest(),
            c03_fixture=_load_v2(),
        )


def test_fixture_and_110mm_pose_bindings_load():
    fixture = _load()
    assert fixture["physical_authority"] is False
    assert fixture["runtime_manifest"]["execution_device"] == "CPU_ONLY"
    assert fixture["sections"]["stage_ef_contact"]["tool_length_mm"] == 110.0
    assert len(fixture["sections"]["stage_ef_contact"][
        "tool_configuration_sha256"
    ]) == 2


def test_candidate51_pose_successor_solves_every_target():
    result = build_candidate51_pose_family(_load_v2(), workspace=ROOT)
    assert result["decision"] == "PASS_EXPLORATORY_CANDIDATE51_110MM_POSES"
    assert result["reach_by_length_mm"]["110.0"]["solved_target_count"] == 51
    assert result["reach_by_length_mm"]["110.0"]["failed_target_ids"] == []
    for profile in result["profiles"]:
        bundle = profile["pose_bundle"]
        assert len(bundle["poses"]) == 51
        assert bundle["tool_configuration"]["target_catalog_sha256"] == (
            _load_v2()["bindings"]["candidate_catalog"]["sha256"]
        )
        assert {"SHIFT", "BACKSLASH", "GRAVE", "LEFT_BRACKET", "RIGHT_BRACKET"} <= {
            row["target_id"] for row in bundle["poses"]
        }


def test_corrected_contact_phone_and_ws3_counts():
    fixture = _load_v2()
    contact = run_stage_ef_contact_screen(fixture, workspace=ROOT)
    assert contact["target_count"] == 51
    assert contact["row_count"] == 2 * 51 * 2 * 2
    assert contact["pass_row_count"] == contact["row_count"]
    grave = [row for row in contact["rows"] if row["target_id"] == "GRAVE"]
    assert len(grave) == 8
    assert min(row["minimum_non_target_clearance_mm"] for row in grave) == pytest.approx(
        8.37
    )

    phone = run_phone_capacitive_matrix(fixture)
    assert phone["row_count"] == 4 * 3 * 5 * 4 * 3 * 3
    assert phone["by_radius"]["3.0"]["admitted_cell_count"] == 162
    assert phone["by_radius"]["3.0"]["minimum_effective_area_mm2"] == pytest.approx(
        math.pi * 9.0 * 0.25
    )
    assert phone["by_radius"]["3.0"]["maximum_effective_area_mm2"] == pytest.approx(
        math.pi * 9.0
    )

    ws3 = prepare_ws3_transition_harness(fixture, workspace=ROOT)
    assert ws3["target_count"] == 51
    assert ws3["ordered_pair_count"] == 51 * 51
    assert ws3["transition_scenario_count"] == 51 * 51 * 2 * 2 * 3
    assert ws3["policy_recommendation"] is None


def test_fixture_tamper_fails(tmp_path):
    document = json.loads(FIXTURE.read_text())
    document["sections"]["phone_capacitive"]["contact_radius_mm"].append(9.0)
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="fixture hash mismatch"):
        load_cpu_contact_fixture(path, workspace=ROOT)


def test_phone_matrix_covers_area_and_timing_ranges():
    result = run_phone_capacitive_matrix(_load())
    assert result["row_count"] == 3 * 3 * 5 * 4 * 3 * 3
    assert result["decision"] == "UNRESOLVED_PHYSICAL_MEASUREMENT_REQUIRED"
    assert result["by_radius"]["1.0"]["any_admitted"] is True
    assert result["by_radius"]["7.0"]["maximum_effective_area_mm2"] == pytest.approx(
        math.pi * 49.0
    )
    assert result["long_press_count"] > 0
    assert result["physical_authority"] is False


def test_stage_ef_full_frozen_population_passes_exact_screen():
    result = run_stage_ef_contact_screen(_load(), workspace=ROOT)
    assert result["row_count"] == 2 * 46 * 2 * 2
    assert result["pass_row_count"] == result["row_count"]
    assert result["global_minimum_non_target_clearance_mm"] == pytest.approx(7.5)
    assert result["decision"] == "PASS_EXPLORATORY_STAGE_EF_EXACT_CONTACT"


def test_ws3_preparation_enumerates_all_pairs_and_stops_without_recipe():
    result = prepare_ws3_transition_harness(_load(), workspace=ROOT)
    assert result["target_count"] == 46
    assert result["ordered_pair_count"] == 46 * 46
    assert result["includes_repeat_pairs"] is True
    assert result["transition_scenario_count"] == 46 * 46 * 2 * 2 * 3
    assert result["decision"] == "READY_COLLISION_HARNESS_BLOCKED_WS2_PRESS_RECIPE"
    assert result["policy_recommendation"] is None
    assert "not bound" in result["blocked_reason"]


def test_ws3_rejects_wrong_recipe_hash(tmp_path):
    fixture = _load()
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text("{}")
    fixture["sections"]["workstream_3"]["press_recipe_binding"] = {
        "path": str(recipe_path),
        "sha256": "0" * 64,
    }
    fixture = _rehash_fixture(fixture)
    with pytest.raises(ValueError, match="file hash mismatch"):
        validate_ws2_recipe_binding(fixture, workspace=ROOT)


def test_ws3_screen_stops_before_geometry_without_recipe():
    with pytest.raises(ValueError, match="not bound"):
        run_ws3_transition_screen(_load(), workspace=ROOT)


def test_ws3_rejects_nonpassing_recipe(tmp_path):
    fixture = _load()
    recipe = {
        "schema": "tactevra.ws2_press_recipe_envelope.v1",
        "decision": "STOP",
        "physical_authority": False,
        **{name: 0 for name in (
            "hardware_write_count", "physical_movement_count", "real_command_count",
            "permit_count", "transport_count")},
    }
    recipe["receipt_sha256"] = _sha(recipe)
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(json.dumps(recipe))
    fixture["sections"]["workstream_3"]["press_recipe_binding"] = {
        "path": str(recipe_path),
        "sha256": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
    }
    fixture = _rehash_fixture(fixture)
    with pytest.raises(ValueError, match="not admitted"):
        validate_ws2_recipe_binding(fixture, workspace=ROOT)
