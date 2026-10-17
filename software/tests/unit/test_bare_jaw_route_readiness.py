from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from rocell.application.bare_jaw_route_readiness import (
    BareJawRouteReadinessError,
    assess_bare_jaw_route_readiness,
)


@pytest.fixture
def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_retained_bare_jaw_route_audit_is_deterministic_and_zero_dispatch(
    workspace_root: Path,
) -> None:
    first = assess_bare_jaw_route_readiness(workspace_root)
    second = assess_bare_jaw_route_readiness(workspace_root)

    assert first == second
    assert first["status"] == "BLOCKED_CALIBRATION_COMPONENTS_REQUIRED"
    assert first["reusable_measured_geometry"]["board_size_xy_mm"] == [610.0, 457.0]
    assert first["reusable_measured_geometry"]["tag_detection_edge_mm"] == 40.0
    assert len(first["reusable_measured_geometry"]["tag_centers_xy_mm"]) == 6
    assert first["reusable_measured_geometry"]["reviewed_target_count"] == 46
    assert first["reusable_measured_geometry"]["selected_target"] == {
        "id": "H",
        "surface_board_mm": {
            "x": pytest.approx(212.95070610888823),
            "y": pytest.approx(149.20958023724344),
            "z": pytest.approx(21.0),
        },
    }
    assert first["observed_start"]["servo_register_positions"] == [
        2052, 2149, 1956, 2550, 2227, 2041, 2042,
    ]
    assert first["observed_start"]["classification"] == (
        "OBSERVED_CONTROLLER_REGISTERS_NOT_MODEL_JOINT_RADIANS"
    )
    assert first["attachment_profiles"] == {
        "active": "BARE_JAW",
        "active_profile_id": "bare-jaw-live-calibration-v1",
        "stylus_profile_id": "stylus-pending-calibration-v1",
        "trajectory_invalidated_on_attachment_change": True,
        "pose_inheritance_allowed": False,
    }
    assert first["screening"]["ik_executed"] is False
    assert first["screening"]["unreachable_claim_supported_for_installed_workcell"] is False
    assert first["static_phase1_calibration_intake"]["status"] == (
        "SYNTHETIC_PHASE1_GRAPH_VERIFIED_PHYSICAL_REGISTRY_BLOCKED"
    )
    assert first["static_phase1_calibration_intake"]["route_artifact_ids"] == [
        "phase1_b0477_identity",
        "phase1_b0477_mode",
        "phase1_b0477_settings",
        "phase1_static_intrinsics",
        "phase1_measured_tag_map",
        "phase1_static_extrinsic",
        "phase1_robot_reference",
        "phase1_controller_correlation",
        "phase1_arm_board",
        "phase1_keyboard_target_map",
        "phase1_keyboard_tcp",
    ]
    assert first["static_phase1_calibration_intake"]["complete_keyboard_requirement_order"] == [
        "phase1_b0477_identity",
        "phase1_b0477_mode",
        "phase1_b0477_settings",
        "phase1_static_intrinsics",
        "phase1_measured_tag_map",
        "phase1_static_extrinsic",
        "phase1_robot_reference",
        "phase1_controller_correlation",
        "phase1_arm_board",
        "phase1_keyboard_target_map",
        "phase1_keyboard_tcp",
        "phase1_keyboard_outcome_observer",
    ]
    assert first["static_phase1_calibration_intake"]["camera_architecture"] == {
        "retained_live_session": "STATIC_EXTERNAL_CAMERA",
        "selected_graph": "RIGID_STATIC_OVERHEAD_EYE_TO_HAND",
        "historical_eye_on_arm_graph_reinterpreted": False,
        "aligned": True,
    }
    assert first["installed_collision_intake"]["diagnostic_ready"] is False
    assert first["installed_collision_intake"]["missing_required_body_ids"] == [
        "robot:base_link",
        "robot:gripper",
        "robot:link1",
        "robot:link2",
        "robot:link3",
        "robot:link4",
        "robot:link5",
    ]
    assert first["installed_collision_intake"]["unknown_required_body_ids"] == [
        "attachment:camera_connector",
        "attachment:camera_holder",
        "attachment:camera_module",
        "attachment:contact_tool",
        "attachment:moving_camera_cable",
        "installation:base_and_factory_clamp",
    ]
    assert first["retained_evidence_coverage"]["summary"] == {
        "physically_complete_artifact_count": 0,
        "repeated_measurement_requested": False,
        "route_artifact_count": 11,
        "route_missing_candidate_count": 2,
        "route_partial_candidate_count": 9,
    }
    assert first["retained_evidence_coverage"]["route_no_candidate_ids"] == [
        "phase1_static_intrinsics",
        "phase1_arm_board",
    ]
    assert len(
        first["retained_evidence_coverage"]["route_reusable_candidate_ids"]
    ) == 9
    intrinsics = first["physical_intrinsics_intake"]
    assert intrinsics["status"] == "BLOCKED_PHYSICAL_INTRINSICS_INPUTS_REQUIRED"
    assert intrinsics["retained_runtime_binding"]["mode"] == {
        "width_px": 1920,
        "height_px": 1080,
        "fps": pytest.approx(60.000240000960005),
        "pixel_format": "YUY2",
    }
    assert intrinsics["legacy_rehearsal_comparison"][
        "eligible_as_physical_intrinsics"
    ] is False
    assert intrinsics["collection_policy"]["new_target_print_requested"] is False
    assert intrinsics["collection_policy"][
        "repeat_board_or_tag_center_measurements"
    ] is False
    reconciliation = intrinsics["target_reconciliation"]
    assert reconciliation["completed_fixed_board_evidence"][
        "repeat_board_or_tag_measurements_required"
    ] is False
    assert reconciliation["intrinsics_observability_decision"][
        "existing_board_measurements_are_rejected"
    ] is False
    assert reconciliation["collection_policy"]["new_target_print_requested"] is False
    assert intrinsics["capture_ready"] is False
    assert "MEASURED_STATIC_CAMERA_CHAIN_REQUIRED" in first["blockers"]
    assert "PLANNER_CAMERA_ARCHITECTURE_RECONCILIATION_REQUIRED" not in first[
        "blockers"
    ]
    assert first["controller_commands"] == []
    assert first["transport_writes"] == 0
    assert first["hardware_access"] is first["physical_authority"] is False
    assert len(first["readiness_sha256"]) == 64


def _copy_inputs(source: Path, destination: Path) -> None:
    paths = [
        "software/config/live_camera_feedback_session_20261015.json",
        "software/config/tool_attachment_profiles.json",
        "software/ai/eval/b0477_fixed_board_registration_20261016.json",
        "software/ai/eval/b0477_keyboard_overlay_20261016.json",
        "software/ai/eval/physical_installed_apriltag_xy_working_v1.json",
        "software/ai/eval/static_phase1_retained_evidence_coverage_20261016.json",
        "software/ai/eval/static_phase1_intrinsics_intake_plan_20261016.json",
        "software/ai/eval/static_intrinsics_multiview_capture_contract_20261016.json",
        "software/ai/eval/static_intrinsics_target_reconciliation_20261016.json",
        "software/ai/eval/b0477_locked_controls_qualification_20261016.json",
        "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
        "software/tests/fixtures/camera/b0477_synthetic_intrinsics_rehearsal.json",
    ]
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)


def test_route_audit_rejects_feedback_that_no_longer_matches_retained_pose(
    workspace_root: Path, tmp_path: Path,
) -> None:
    _copy_inputs(workspace_root, tmp_path)
    path = tmp_path / "software/config/live_camera_feedback_session_20261015.json"
    session = json.loads(path.read_text(encoding="utf-8"))
    session["stationary_observation_20261016"]["active_feedback"]["feedback"]["p"][0] += 1
    path.write_text(json.dumps(session), encoding="utf-8")

    with pytest.raises(BareJawRouteReadinessError, match="registers differ"):
        assess_bare_jaw_route_readiness(tmp_path)


def test_route_audit_rejects_attachment_profile_inheritance(
    workspace_root: Path, tmp_path: Path,
) -> None:
    _copy_inputs(workspace_root, tmp_path)
    path = tmp_path / "software/config/tool_attachment_profiles.json"
    profiles = json.loads(path.read_text(encoding="utf-8"))
    profiles["switching_policy"]["allow_pose_inheritance_between_profiles"] = True
    path.write_text(json.dumps(profiles), encoding="utf-8")

    with pytest.raises(BareJawRouteReadinessError, match="profile separation"):
        assess_bare_jaw_route_readiness(tmp_path)
