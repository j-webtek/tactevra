from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))

from rocell_ai.c03_arm_route_reconciliation_v1 import (  # noqa: E402
    canonical_hash,
    load_fixture,
    reconcile,
)
from rocell_ai.c03_exact_route_reconstruction_v1 import (  # noqa: E402
    load_fixture as load_route_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_1 import (  # noqa: E402
    load_fixture as load_coherent_route_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_2 import (  # noqa: E402
    load_fixture as load_short_path_route_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_3 import (  # noqa: E402
    load_fixture as load_rebound_route_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_4 import (  # noqa: E402
    load_fixture as load_bundle_rebound_route_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_5 import (  # noqa: E402
    load_fixture as load_parent_profile_route_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_6 import (  # noqa: E402
    load_fixture as load_locked_catalog_path_route_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_7 import (  # noqa: E402
    load_fixture as load_promoted_profile_source_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_8 import (  # noqa: E402
    load_fixture as load_inherited_route_policy_fixture,
)
from rocell_ai.c03_exact_route_reconstruction_v1_9 import (  # noqa: E402
    load_fixture as load_regenerated_pose_route_fixture,
)


FIXTURE = AI_ROOT / "sim" / "evidence" / "c03_arm_route_reconciliation_fixture_v1.json"
FIXTURE_V1_1 = (
    AI_ROOT / "sim" / "evidence" / "c03_arm_route_reconciliation_fixture_v1_1.json"
)
FIXTURE_V1_2 = (
    AI_ROOT / "sim" / "evidence" / "c03_arm_route_reconciliation_fixture_v1_2.json"
)
ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1.json"
)
COHERENT_ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_1.json"
)
SHORT_PATH_ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_2.json"
)
REBOUND_ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_3.json"
)
BUNDLE_REBOUND_ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_4.json"
)
PARENT_PROFILE_ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_5.json"
)
LOCKED_CATALOG_PATH_ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_6.json"
)
PROMOTED_PROFILE_SOURCE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_7.json"
)
INHERITED_ROUTE_POLICY_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_8.json"
)
POSE_REGENERATION_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_pose_family_regeneration_fixture_v1.json"
)
REGENERATED_POSE_ROUTE_FIXTURE = (
    AI_ROOT / "sim" / "evidence" / "c03_exact_route_reconstruction_fixture_v1_9.json"
)


def _write_fixture(tmp_path: Path, mutation) -> Path:
    value = load_fixture(FIXTURE)
    mutation(value)
    value.pop("fixture_sha256")
    value["fixture_sha256"] = canonical_hash(value)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_reconciliation_stops_on_exact_tool_identity_mismatch() -> None:
    result = reconcile(FIXTURE, WORKSPACE)
    assert result["decision"] == "STOP_C03_PROMOTED_ROUTE_TOOL_IDENTITY_MISMATCH"
    assert result["c03_candidate"]["tool_total_length_mm"] == 110.0
    assert result["promoted_arm_route"]["tool_total_length_mm"] == 120.0
    assert result["tool_length_difference_mm"] == 10.0
    assert result["c03_candidate"]["screened_ordered_pair_count"] == 2601
    assert result["c03_candidate"]["screened_row_count"] == 15606
    assert result["collision_screen_executed"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0
    assert result["controller_commands"] == []
    assert result["physical_authority"] is False
    receipt = result.pop("receipt_sha256")
    assert receipt == canonical_hash(result)


def test_altered_bound_file_hash_fails_closed(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        lambda value: value["bindings"]["promoted_full_route"].update({"sha256": "0" * 64}),
    )
    with pytest.raises(ValueError, match="bound artifact hash mismatch"):
        reconcile(fixture, WORKSPACE)


def test_wrong_promoted_tool_identity_fails_closed(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        lambda value: value["expected"].update({"promoted_route_tool_length_mm": 110.0}),
    )
    with pytest.raises(ValueError, match="promoted route tool length differs"):
        reconcile(fixture, WORKSPACE)


def test_fixture_zero_authority_is_strict(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        lambda value: value["counters"].update({"hardware_write_count": 1}),
    )
    with pytest.raises(ValueError, match="zero authority"):
        reconcile(fixture, WORKSPACE)


def test_duplicate_json_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    from rocell_ai.c03_arm_route_reconciliation_v1 import load_strict_json

    with pytest.raises(ValueError, match="duplicate JSON field"):
        load_strict_json(path)


def test_successor_also_stops_on_target_catalog_identity_mismatch() -> None:
    result = reconcile(FIXTURE_V1_1, WORKSPACE)
    assert result["decision"] == (
        "STOP_C03_PROMOTED_ROUTE_TOOL_AND_TARGET_CATALOG_IDENTITY_MISMATCH"
    )
    catalogs = result["target_catalog_reconciliation"]
    assert catalogs["identical"] is False
    assert catalogs["c03_candidate_target_catalog_sha256"] == "0fe3c013" + "a30c42e5b0bb663571f6a5b2996e353b0130c1a6905cb34101b011d8"
    assert catalogs["promoted_route_target_catalog_sha256"] == "6779213e" + "832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2"
    assert result["hardware_writes"] == result["physical_movements"] == 0


def test_route_coordinate_audit_preserves_order_and_repeats() -> None:
    result = reconcile(FIXTURE_V1_2, WORKSPACE)
    assert result["decision"] == "STOP_PROMOTED_ROUTE_COORDINATES_REQUIRE_C03_RECONSTRUCTION"
    audit = result["target_catalog_reconciliation"]["route_coordinate_audit"]
    assert audit["route_target_order"] == ["H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6"]
    assert audit["route_action_count"] == 10
    assert audit["moved_action_count"] == 6
    assert audit["moved_unique_target_ids"] == ["0", "2", "6", "E", "O"]
    assert audit["maximum_planar_delta_mm"] == pytest.approx(15.113581329295517)
    assert [row["target_id"] for row in audit["rows"]] == audit["route_target_order"]


def test_exact_route_fixture_is_frozen_and_zero_authority() -> None:
    fixture = load_route_fixture(ROUTE_FIXTURE, WORKSPACE)
    assert fixture["c03_tool"]["total_length_mm"] == 110.0
    assert fixture["c03_tool"]["tool_configuration_sha256"] == (
        "ba538b48bb9c6bc80c01ad4ae792b9784440de4825c5dea5781f3277b8ee4109"
    )
    assert fixture["route"]["ordered_targets"] == [
        "H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6",
    ]
    assert fixture["decision_rules"]["collision_screen_executed_must_be"] is False
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_coherent_route_successor_is_frozen_and_zero_authority() -> None:
    fixture = load_coherent_route_fixture(COHERENT_ROUTE_FIXTURE, WORKSPACE)
    assert fixture["coherent_workspace"]["source_tree_commit"] == (
        "fe80a94c26d564cd2e7233c6b85beef6909aab3c"
    )
    assert fixture["coherent_workspace"]["expected_tracked_file_count"] == 6480
    assert fixture["predecessor_fixture_path"].endswith(
        "c03_exact_route_reconstruction_fixture_v1.json"
    )
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_short_path_successor_changes_only_external_materialization_identity() -> None:
    prior = load_coherent_route_fixture(COHERENT_ROUTE_FIXTURE, WORKSPACE)
    fixture = load_short_path_route_fixture(SHORT_PATH_ROUTE_FIXTURE, WORKSPACE)
    assert fixture["coherent_workspace"]["path"] == "C:/MuJoCoWarp/c03cw1"
    assert fixture["coherent_workspace"]["source_tree_commit"] == (
        prior["coherent_workspace"]["source_tree_commit"]
    )
    assert fixture["coherent_workspace"]["expected_tracked_file_count"] == (
        prior["coherent_workspace"]["expected_tracked_file_count"]
    )
    assert fixture["bindings"]["c03_candidate_target_catalog"] == (
        prior["bindings"]["c03_candidate_target_catalog"]
    )
    assert fixture["predecessor_fixture_path"] == prior["predecessor_fixture_path"]
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_rebound_successor_freezes_only_catalog_identity_changes() -> None:
    fixture = load_rebound_route_fixture(REBOUND_ROUTE_FIXTURE, WORKSPACE)
    contract = fixture["fixture_rebinding"]
    assert contract["allowed_semantic_changes"] == [
        "parent.input_bindings.target_catalog.sha256",
        "predecessor.bindings.parent_route_fixture.sha256",
        "predecessor.parent_fixture_sha256",
    ]
    assert contract["numerical_policy_change_count"] == 0
    assert contract["source_parent_fixture_sha256"] == (
        "ee811e81ae69d36c3b7e19ec53cb6293fcbac510ce54c58a7d3f0e8ebcffdea0"
    )
    assert contract["source_predecessor_fixture_sha256"] == (
        "f48940215bfb211d8e7f1eebc42d04eda9d2a621291bfe2d8350eb86db7cb197"
    )
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_bundle_rebound_successor_freezes_only_identity_changes() -> None:
    fixture = load_bundle_rebound_route_fixture(
        BUNDLE_REBOUND_ROUTE_FIXTURE, WORKSPACE
    )
    contract = fixture["virtual_profile_rebinding"]
    assert contract["allowed_semantic_changes"] == [
        "virtual_profile.binding.simulation_bundle_id",
        "bundle.artifacts.virtual_commissioning_profile.sha256",
    ]
    assert contract["numerical_policy_change_count"] == 0
    assert contract["source_virtual_profile_sha256"] == (
        "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634"
    )
    assert fixture["fixture_rebinding"]["numerical_policy_change_count"] == 0
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_parent_profile_successor_adds_only_parent_profile_binding() -> None:
    fixture = load_parent_profile_route_fixture(
        PARENT_PROFILE_ROUTE_FIXTURE, WORKSPACE
    )
    assert fixture["fixture_rebinding"]["allowed_semantic_changes"] == [
        "parent.input_bindings.target_catalog.sha256",
        "parent.input_bindings.promoted_profile.sha256",
        "predecessor.bindings.parent_route_fixture.sha256",
        "predecessor.parent_fixture_sha256",
    ]
    assert fixture["fixture_rebinding"]["numerical_policy_change_count"] == 0
    assert fixture["virtual_profile_rebinding"]["numerical_policy_change_count"] == 0
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_locked_catalog_path_successor_preserves_candidate_hash() -> None:
    prior = load_parent_profile_route_fixture(PARENT_PROFILE_ROUTE_FIXTURE, WORKSPACE)
    fixture = load_locked_catalog_path_route_fixture(
        LOCKED_CATALOG_PATH_ROUTE_FIXTURE, WORKSPACE
    )
    contract = fixture["fixture_rebinding"]
    assert contract["derived_candidate_catalog_path"] == (
        "software/config/nominal_target_profiles.json"
    )
    assert contract["allowed_semantic_changes"] == [
        "parent.input_bindings.target_catalog.sha256",
        "parent.input_bindings.promoted_profile.sha256",
        "predecessor.bindings.c03_candidate_target_catalog.path",
        "predecessor.bindings.parent_route_fixture.sha256",
        "predecessor.parent_fixture_sha256",
    ]
    assert fixture["bindings"]["c03_candidate_target_catalog"]["sha256"] == (
        prior["bindings"]["c03_candidate_target_catalog"]["sha256"]
    )
    assert contract["numerical_policy_change_count"] == 0
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_promoted_profile_source_successor_adds_only_source_hash() -> None:
    fixture = load_promoted_profile_source_fixture(
        PROMOTED_PROFILE_SOURCE_FIXTURE, WORKSPACE
    )
    assert "parent.promoted_profile.source_sha256" in (
        fixture["fixture_rebinding"]["allowed_semantic_changes"]
    )
    assert fixture["fixture_rebinding"]["numerical_policy_change_count"] == 0
    assert fixture["virtual_profile_rebinding"]["numerical_policy_change_count"] == 0
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_inherited_route_policy_fields_are_explicit_and_untuned() -> None:
    fixture = load_inherited_route_policy_fixture(
        INHERITED_ROUTE_POLICY_FIXTURE, WORKSPACE
    )
    fields = fixture["fixture_rebinding"]["inherited_route_fields"]
    assert fields == [
        "dynamics_profile_sha256",
        "settle_position_tolerance_mm",
        "settle_velocity_tolerance_mm_s",
        "settle_hold_ms",
        "maximum_cartesian_step_mm",
        "maximum_velocity_mm_s",
        "maximum_acceleration_mm_s2",
        "maximum_jerk_mm_s3",
        "hover_settle_ms",
        "contact_dwell_ms",
    ]
    allowlist = fixture["fixture_rebinding"]["allowed_semantic_changes"]
    assert all(f"parent.route.{name}" in allowlist for name in fields)
    assert fixture["fixture_rebinding"]["numerical_policy_change_count"] == 0
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_pose_regeneration_fixture_binds_exact_21mm_source() -> None:
    fixture = json.loads(POSE_REGENERATION_FIXTURE.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    assert claimed == canonical_hash(fixture)
    assert fixture["claim_commit"] == (
        "13c44aedd3dbd04054d88665332a56e6e7d31bc1"
    )
    assert fixture["bindings"]["candidate51_pose_source"]["sha256"] == (
        "bd68f7d3e3065f0cc90b05d2ec1aa1dd2078fe14c81521a08a9417277e078bf0"
    )
    assert fixture["sections"]["pose_generation"]["contact_target_source"] == (
        "EXACT_CANDIDATE_CATALOG_CENTERS_Z_21MM"
    )
    assert fixture["amendment"]["recipe_and_tool_unchanged"] is True
    assert fixture["amendment"]["route_and_ik_gates_unchanged"] is True
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_route_successor_binds_admitted_21mm_pose_family() -> None:
    fixture = load_regenerated_pose_route_fixture(
        REGENERATED_POSE_ROUTE_FIXTURE, WORKSPACE
    )
    binding = fixture["bindings"]["regenerated_c03_pose_family"]
    assert binding["sha256"] == (
        "125a7ba8b10cd72341d9be129741682c5191ec93ba4a3186a355d325c0b8e504"
    )
    assert binding["receipt_sha256"] == (
        "b34970482ce60590574216f30f3ca99e63e2cffd925c65db019b0e4cd659f668"
    )
    allowlist = fixture["fixture_rebinding"]["allowed_semantic_changes"]
    assert "predecessor.bindings.c03_pose_family.path" in allowlist
    assert "predecessor.bindings.c03_pose_family.sha256" in allowlist
    assert "predecessor.bindings.c03_pose_family.receipt_sha256" in allowlist
    assert fixture["fixture_rebinding"]["numerical_policy_change_count"] == 0
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())
