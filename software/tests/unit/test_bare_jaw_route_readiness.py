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
