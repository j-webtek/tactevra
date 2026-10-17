"""Tests for the reference-only retained-start to PARK bridge."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


AI_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = AI_DIR.parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

import rocell_ai.current_start_entry_bridge as subject  # noqa: E402


JOINTS = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
)


def _start_report() -> dict:
    start = {name: 0.0 for name in JOINTS}
    park = {name: 0.0 for name in JOINTS}
    park[JOINTS[2]] = 1.0
    return {
        "status": "REFERENCE_START_OUTSIDE_FIRST_ROUTE_JOINT_STEP",
        "report_sha256": "a" * 64,
        "reference_projection": {
            "classification": "REFERENCE_ONLY_NOT_INSTALLED_CALIBRATION",
            "arm_joint_positions_rad": start,
        },
        "first_route_waypoint": {
            "solution_arm_joint_positions_rad": park,
        },
    }


def test_bridge_uses_canonical_bounded_sampling_and_remains_zero_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = SimpleNamespace(
        model_path=Path("model.urdf"),
        model_sha256="b" * 64,
        controller_joint_intersection_rad={name: (-2.0, 2.0) for name in JOINTS},
        tool_case_id="reference-tool",
        hand_tcp_to_tip_z_mm=-120.0,
    )
    monkeypatch.setattr(
        subject, "run_start_sensitivity", lambda *args, **kwargs: _start_report()
    )
    monkeypatch.setattr(
        subject, "load_static_simulation_context", lambda workspace: object()
    )
    monkeypatch.setattr(
        subject,
        "promoted_rank1_robot_layout",
        lambda context, profile: (scenario, {"overlay_sha256": "c" * 64}),
    )
    monkeypatch.setattr(
        subject,
        "load_pinned_urdf",
        lambda *args: SimpleNamespace(model=object(), sha256="d" * 64),
    )
    monkeypatch.setattr(
        subject,
        "_fk_sample",
        lambda model, selected, joints: {
            "hand_tcp_board_mm": [joints[JOINTS[2]], 0.0, 120.0],
            "tool_tip_board_mm": [joints[JOINTS[2]], 0.0, 0.0],
            "hand_tcp_z_axis_board": [0.0, 0.0, 1.0],
        },
    )

    report = subject.run(
        {"intake_sha256": "e" * 64},
        workspace=WORKSPACE,
        profile_path=WORKSPACE / "software/config/virtual_commissioning_profile.json",
    )

    assert report["sample_count"] == 21
    assert report["subdivision_count"] == 20
    assert report["maximum_observed_joint_gap_rad"] == pytest.approx(0.05)
    assert report["all_samples_in_controller_intersection"] is True
    assert report["samples"][0]["interpolation_ratio"] == 0.0
    assert report["samples"][-1]["interpolation_ratio"] == 1.0
    assert report["tool_tip_board_bounds_mm"]["x"] == pytest.approx([0.0, 1.0])
    assert report["collision_screening_executed"] is False
    assert report["continuous_path_proven"] is False
    assert report["controller_commands"] == []
    assert report["transport_writes"] == 0


def test_bridge_requires_reviewed_outside_step_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _start_report()
    report["status"] = "REFERENCE_START_WITHIN_FIRST_ROUTE_JOINT_STEP"
    monkeypatch.setattr(
        subject, "run_start_sensitivity", lambda *args, **kwargs: report
    )
    with pytest.raises(ValueError, match="outside-step"):
        subject.run(
            {},
            workspace=WORKSPACE,
            profile_path=WORKSPACE
            / "software/config/virtual_commissioning_profile.json",
        )
