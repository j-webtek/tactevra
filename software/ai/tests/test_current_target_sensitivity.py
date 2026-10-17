"""Tests for current-camera target replay under an unmeasured layout hypothesis."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest


AI_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = AI_DIR.parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

import rocell_ai.current_target_sensitivity as subject  # noqa: E402


def _intake() -> dict:
    core = {
        "schema": "rocell.current_bare_jaw_route_screening_intake.v1",
        "bindings": {
            "workcell_epoch_id": "camera-epoch-001",
            "selected_frame_sha256": "a" * 64,
            "attachment_profile": "BARE_JAW",
        },
        "selected_target": {
            "device": "keyboard",
            "target_id": "H",
            "interaction": "HOVER",
            "surface_board_mm": {
                "x": 212.95070610888823,
                "y": 149.20958023724344,
                "z": 21.0,
            },
            "hover_board_mm": {
                "frame": "board",
                "x": 212.95070610888823,
                "y": 149.20958023724344,
                "z": 48.7953,
            },
        },
        "blockers": ["MEASURED_BOARD_TO_ARM_TRANSFORM_REQUIRED"],
        "controller_commands": [],
        "transport_writes": 0,
        "hardware_access": False,
        "physical_authority": False,
        "descent_authorized": False,
        "contact_authorized": False,
    }
    digest = hashlib.sha256(
        json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    return {**core, "intake_sha256": digest}


def _passing_simulation(proposal: dict, **kwargs: object) -> dict:
    assert proposal["coordinate_frame"] == "board"
    assert proposal["target_mm"] == pytest.approx(
        {"x": 212.95070610888823, "y": 149.20958023724344, "z": 21.0}
    )
    assert proposal["approach_clearance_mm"] == pytest.approx(27.7953)
    assert kwargs["park_xy_board_mm"] == (290.0, 10.0)
    return {
        "dense_route_all_waypoints_accepted": True,
        "evaluated_waypoint_count": 32,
        "simulation_target_overlay": {
            "center_board_mm": [212.95070610888823, 149.20958023724344, 21.0]
        },
    }


def test_current_h_passes_only_as_unmeasured_sensitivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "run_model_motion", _passing_simulation)
    report = subject.run(
        _intake(),
        workspace=WORKSPACE,
        profile_path=WORKSPACE / "software/config/virtual_commissioning_profile.json",
    )
    assert report["status"] == "CURRENT_H_PASSES_UNMEASURED_LAYOUT_SENSITIVITY"
    assert report["simulation"]["dense_route_all_waypoints_accepted"] is True
    assert report["simulation"]["evaluated_waypoint_count"] == 32
    assert report["simulation"]["simulation_target_overlay"][
        "center_board_mm"
    ] == pytest.approx([212.95070610888823, 149.20958023724344, 21.0])
    assert report["frozen_hypothesis"]["installed_position_verified"] is False
    assert report["physical_execution_authorized"] is False
    assert report["controller_commands"] == []
    assert report["transport_writes"] == 0


def test_intake_tampering_and_profile_change_fail_closed() -> None:
    intake = _intake()
    changed = copy.deepcopy(intake)
    changed["selected_target"]["surface_board_mm"]["x"] += 1.0
    with pytest.raises(ValueError, match="digest mismatch"):
        subject.run(
            changed,
            workspace=WORKSPACE,
            profile_path=WORKSPACE
            / "software/config/virtual_commissioning_profile.json",
        )
    changed = _intake()
    changed["physical_authority"] = True
    core = {key: value for key, value in changed.items() if key != "intake_sha256"}
    changed["intake_sha256"] = hashlib.sha256(
        json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="cannot assert physical_authority"):
        subject.run(
            changed,
            workspace=WORKSPACE,
            profile_path=WORKSPACE
            / "software/config/virtual_commissioning_profile.json",
        )
