from __future__ import annotations

import copy
from pathlib import Path

import pytest

import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.c03_route_collision_handoff_v1 import (
    C03FullBodyGeometryAuditV1Error,
    C03RouteCollisionHandoffV1Error,
    assess_c03_full_body_geometry_readiness_v1,
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
