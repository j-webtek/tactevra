from __future__ import annotations

import copy
from pathlib import Path

import pytest

import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.c03_route_collision_handoff_v1 import (
    C03FullBodyGeometryAuditV1Error,
    C03RouteCollisionHandoffV1Error,
    assess_c03_base_camera_geometry_readiness_v1,
    assess_c03_ambient_light_static_base_camera_geometry_readiness_v3,
    assess_c03_static_base_camera_geometry_readiness_v2,
    assess_c03_static_support_source_reconciliation_v1,
    assess_c03_full_body_geometry_readiness_v1,
    assess_c03_nominal_tool_binding_readiness_v1,
    assess_c03_station_height_route_sensitivity_v1,
    prepare_c03_route_collision_handoff_v1,
)
from rocell.application.context import load_simulation_context
from rocell.application.partitioned_typing_collision_intake_v1 import (
    PROFILE_REQUIRED_STATUS,
    READY_STATUS,
)

from test_partitioned_typing_collision_intake_v1 import _inputs
from test_typing_trajectory_ik_screen_v1 import _installed_profile


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"
MESH_BINDING = WORKSPACE / (
    "software/integrations/isaac_sim/evidence/"
    "roarm_m3_upstream_link_mesh_binding_20261004.json"
)
MESH_REDUCTION = WORKSPACE / (
    "software/integrations/isaac_sim/evidence/"
    "roarm_m3_link_mesh_reduction_20261004.json"
)
SUPPORT_DESIGN = (
    WORKSPACE / "hardware/static_overhead_camera/config/support_design.json"
)
PRINTABLE_FRAME_DESIGN = WORKSPACE / (
    "hardware/static_overhead_camera/config/printable_frame_design.json"
)


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def _result(sim_context):
    snapshot, execution, trajectory, ik = _inputs(sim_context)
    route = {
        "schema": "tactevra.c03_exact_route_reconstruction_result.v1",
        "scope": "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY",
        "decision": "PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY",
        "ordered_targets": [
            "H",
            "E",
            "L",
            "L",
            "O",
            "SPACE",
            "2",
            "0",
            "2",
            "6",
        ],
        "canonical_ik_route_accepted": True,
        "canonical_joint_continuity_accepted": True,
        "trajectory_sample_count": len(ik["joint_results"]),
        "ik_accepted_sample_count": len(ik["joint_results"]),
        "collision_screen_executed": False,
        "execution_plan_sha256": execution.plan_sha256,
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "ik_screen": ik,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    from rocell.application.c03_route_collision_handoff_v1 import _sha256

    route["receipt_sha256"] = _sha256(route)
    outer = {
        "schema": "tactevra.c03_exact_route_reconstruction_result.v1_9",
        "scope": "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY",
        "decision": route["decision"],
        "route_result": route,
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    outer["receipt_sha256"] = _sha256(outer)
    return outer


def _rehash(document):
    content = {key: value for key, value in document.items() if key != "receipt_sha256"}
    document["receipt_sha256"] = handoff_module._sha256(content)


def _json(path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def synthetic_result(sim_context, monkeypatch):
    result = _result(sim_context)
    monkeypatch.setattr(
        handoff_module,
        "EXPECTED_RESULT_RECEIPT_SHA256",
        result["receipt_sha256"],
    )
    monkeypatch.setattr(
        handoff_module,
        "EXPECTED_ROUTE_RECEIPT_SHA256",
        result["route_result"]["receipt_sha256"],
    )
    return result


def test_handoff_partitions_exact_route_and_retains_profile_blocker(
    sim_context, synthetic_result
):
    report = prepare_c03_route_collision_handoff_v1(synthetic_result, sim_context)
    assert report["collision_intake"]["status"] == PROFILE_REQUIRED_STATUS
    assert (
        report["collision_intake"]["required_evidence_slots"]["route_segment_count"] > 0
    )
    assert report["installed_collision_gate_cleared"] is False
    assert report["physical_authority"] is False


def test_full_body_geometry_audit_binds_candidates_and_fails_closed(
    sim_context, synthetic_result
):
    report = assess_c03_full_body_geometry_readiness_v1(
        synthetic_result,
        sim_context,
        mesh_binding=_json(MESH_BINDING),
        mesh_reduction=_json(MESH_REDUCTION),
    )
    assert report["required_body_count"] == 19
    assert report["candidate_robot_body_count"] == 7
    assert report["candidate_robot_primitive_count"] == 14
    assert len(report["nominal_static_proxy_body_ids"]) == 6
    assert report["configuration_sampled_missing_body_ids"] == [
        "attachment:moving_camera_cable"
    ]
    assert "attachment:contact_tool" in report["source_only_body_ids"]
    assert report["full_body_geometry_complete"] is False
    assert report["candidate_profile_installable"] is False
    assert report["collision_screen_executed"] is False
    assert report["physical_authority"] is False


def test_full_body_geometry_audit_rejects_altered_candidate_receipt(
    sim_context, synthetic_result
):
    reduction = _json(MESH_REDUCTION)
    reduction["summary"]["candidate_primitive_count"] = 15
    with pytest.raises(C03FullBodyGeometryAuditV1Error, match="identity differs"):
        assess_c03_full_body_geometry_readiness_v1(
            synthetic_result,
            sim_context,
            mesh_binding=_json(MESH_BINDING),
            mesh_reduction=reduction,
        )


def test_nominal_tool_binding_keeps_planning_tip_separate_from_volume(
    sim_context, synthetic_result
):
    synthetic_result["route_result"]["tool_total_length_mm"] = 110.0
    synthetic_result["route_result"]["tool_configuration_sha256"] = "a" * 64
    _rehash(synthetic_result["route_result"])
    _rehash(synthetic_result)
    handoff_module.EXPECTED_ROUTE_RECEIPT_SHA256 = synthetic_result["route_result"][
        "receipt_sha256"
    ]
    handoff_module.EXPECTED_RESULT_RECEIPT_SHA256 = synthetic_result["receipt_sha256"]
    report = assess_c03_nominal_tool_binding_readiness_v1(
        synthetic_result, sim_context
    )
    assert report["planning_tip_transform"]["translation_mm"] == [0.0, 0.0, -110.0]
    assert report["nominal_mesh_envelopes"]["compliant_tool_body"][
        "extents_mm"
    ] == [28.0, 24.0, 66.199997]
    assert len(report["missing_binding_inputs"]) == 6
    assert report["single_collision_envelope_defined"] is False
    assert report["collision_screen_executed"] is False
    assert report["physical_authority"] is False


def test_base_camera_audit_rejects_moving_contract_for_static_support(
    sim_context, synthetic_result
):
    report = assess_c03_base_camera_geometry_readiness_v1(
        synthetic_result,
        sim_context,
        support_design=_json(SUPPORT_DESIGN),
        support_design_file_sha256=(
            "2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b"
        ),
    )
    assert report["nominal_base_axis_xy_mm"] == [305.0, 457.0]
    assert len(report["base_missing_inputs"]) == 4
    assert report["support_topology"] == "front_portal_on_common_metal_u_frame"
    assert report["camera_architecture_compatible"] is False
    assert len(report["camera_missing_inputs"]) == 4
    assert report["installed_base_geometry_ready"] is False
    assert report["installed_camera_geometry_ready"] is False
    assert report["collision_screen_executed"] is False
    assert report["physical_authority"] is False


def test_static_base_camera_audit_accepts_architecture_but_keeps_geometry_blocked(
    sim_context, synthetic_result
):
    report = assess_c03_static_base_camera_geometry_readiness_v2(
        synthetic_result,
        sim_context,
        support_design=_json(SUPPORT_DESIGN),
        support_design_file_sha256=(
            "2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b"
        ),
    )
    ids = {row["body_id"] for row in report["static_camera_collision_requirements"]}

    assert report["camera_architecture_compatible"] is True
    assert report["camera_architecture_mismatch"] is None
    assert "cable:fixed_usb_route" in ids
    assert "attachment:moving_camera_cable" not in ids
    assert len(ids) == 12
    assert report["base_requirement_id"] == "installation:base_clamp"
    assert len(report["base_missing_inputs"]) == 4
    assert len(report["camera_missing_inputs"]) == 4
    assert report["installed_base_geometry_ready"] is False
    assert report["installed_camera_geometry_ready"] is False
    assert report["collision_screen_executed"] is False
    assert report["physical_authority"] is False


def test_ambient_light_audit_uses_factory_clamp_and_no_fixed_lights(
    sim_context, synthetic_result
):
    report = assess_c03_ambient_light_static_base_camera_geometry_readiness_v3(
        synthetic_result,
        sim_context,
        support_design=_json(SUPPORT_DESIGN),
        support_design_file_sha256=(
            "2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b"
        ),
    )
    ids = {row["body_id"] for row in report["static_camera_collision_requirements"]}

    assert len(ids) == 8
    assert all("lighting" not in body_id for body_id in ids)
    assert report["illumination_contract"]["mode"] == "VARIABLE_AMBIENT"
    assert report["arm_clamp_nominal_zone"]["rear_edge_x_range_mm"] == [
        225.0, 385.0,
    ]
    assert report["base_requirement_id"] == "installation:base_clamp"
    assert len(report["base_missing_inputs"]) == 4
    assert len(report["camera_missing_inputs"]) == 3
    assert report["installed_collision_gate_cleared"] is False
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_static_support_sources_match_datums_but_refuse_hybrid_binding(
    sim_context, synthetic_result
):
    report = assess_c03_static_support_source_reconciliation_v1(
        synthetic_result, sim_context,
        support_design=_json(SUPPORT_DESIGN),
        support_design_file_sha256=(
            "2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b"
        ),
        printable_frame_design=_json(PRINTABLE_FRAME_DESIGN),
        printable_frame_design_file_sha256=(
            "74ce3a823168ad3cfb54ed02db60863ed17253694993653d7b1e4bb6fa447bb3"
        ),
    )
    assert report["shared_datums_match"] is True
    assert report["shared_datums"]["camera_axis_xy_mm"] == [305.0, 228.5]
    assert report["source_selection_state"] == "AMBIGUOUS_CONTROLLED_SOURCE"
    assert report["candidate_envelope_body_count"] == 4
    assert report["nominal_collision_binding_allowed"] is False
    assert report["collision_screen_executed"] is False
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_static_support_reconciliation_rejects_changed_printable_source(
    sim_context, synthetic_result
):
    with pytest.raises(C03FullBodyGeometryAuditV1Error, match="identity differs"):
        assess_c03_static_support_source_reconciliation_v1(
            synthetic_result, sim_context,
            support_design=_json(SUPPORT_DESIGN),
            support_design_file_sha256=(
                "2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b"
            ),
            printable_frame_design=_json(PRINTABLE_FRAME_DESIGN),
            printable_frame_design_file_sha256="0" * 64,
        )


def test_handoff_accepts_matching_profile_but_does_not_clear_collision(
    sim_context, synthetic_result
):
    report = prepare_c03_route_collision_handoff_v1(
        synthetic_result,
        sim_context,
        installed_profile=_installed_profile(sim_context),
    )
    assert report["collision_intake"]["status"] == READY_STATUS
    assert report["collision_intake"]["continuous_collision_proven"] is False
    assert report["installed_collision_gate_cleared"] is False


def test_station_height_sensitivity_is_diagnostic_and_zero_authority(
    sim_context, synthetic_result
):
    report = assess_c03_station_height_route_sensitivity_v1(
        synthetic_result, sim_context
    )

    assert report["waypoint_count"] == len(
        synthetic_result["route_result"]["ik_screen"]["joint_results"]
    )
    assert report["segment_count"] == report["waypoint_count"] - 1
    assert report["scope"] == "TOOL_TIP_CENTRELINE_DIAGNOSTIC_ONLY"
    assert report["all_nominal_solids_contained"] is True
    assert report["proxy_change_authorized"] is False
    assert report["collision_screen_executed"] is False
    assert report["installed_collision_gate_cleared"] is False
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_station_height_sensitivity_rejects_unbounded_clearance(
    sim_context, synthetic_result
):
    with pytest.raises(
        C03RouteCollisionHandoffV1Error,
        match="segment clearance",
    ):
        assess_c03_station_height_route_sensitivity_v1(
            synthetic_result, sim_context, segment_clearance_mm=26.0
        )


def test_handoff_rejects_mutation_and_authority(sim_context, synthetic_result):
    changed = copy.deepcopy(synthetic_result)
    changed["physical_authority"] = True
    _rehash(changed)
    handoff_module.EXPECTED_RESULT_RECEIPT_SHA256 = changed["receipt_sha256"]
    with pytest.raises(C03RouteCollisionHandoffV1Error, match="zero-authority"):
        prepare_c03_route_collision_handoff_v1(changed, sim_context)


def test_handoff_rejects_nested_authority_even_with_valid_receipts(
    sim_context, synthetic_result
):
    changed = copy.deepcopy(synthetic_result)
    changed["route_result"]["hardware_access"] = True
    _rehash(changed["route_result"])
    _rehash(changed)
    handoff_module.EXPECTED_ROUTE_RECEIPT_SHA256 = changed["route_result"][
        "receipt_sha256"
    ]
    handoff_module.EXPECTED_RESULT_RECEIPT_SHA256 = changed["receipt_sha256"]
    with pytest.raises(C03RouteCollisionHandoffV1Error, match="zero-authority"):
        prepare_c03_route_collision_handoff_v1(changed, sim_context)


def test_handoff_rejects_self_consistent_but_unqualified_receipt(sim_context):
    with pytest.raises(C03RouteCollisionHandoffV1Error, match="receipt identity"):
        prepare_c03_route_collision_handoff_v1(_result(sim_context), sim_context)


def test_handoff_rejects_changed_schema_with_valid_receipts(
    sim_context, synthetic_result
):
    changed = copy.deepcopy(synthetic_result)
    changed["route_result"]["schema"] = "tactevra.c03.other.v1"
    _rehash(changed["route_result"])
    _rehash(changed)
    handoff_module.EXPECTED_ROUTE_RECEIPT_SHA256 = changed["route_result"][
        "receipt_sha256"
    ]
    handoff_module.EXPECTED_RESULT_RECEIPT_SHA256 = changed["receipt_sha256"]
    with pytest.raises(C03RouteCollisionHandoffV1Error, match="admission contract"):
        prepare_c03_route_collision_handoff_v1(changed, sim_context)
