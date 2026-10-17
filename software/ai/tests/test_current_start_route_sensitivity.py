"""Tests for retained-register comparison with the passing H route."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

import pytest


AI_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = AI_DIR.parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

import rocell_ai.current_start_route_sensitivity as subject  # noqa: E402


def _intake() -> dict:
    core = {
        "schema": "rocell.current_bare_jaw_route_screening_intake.v1",
        "arm_start_evidence": {
            "classification": "OBSERVED_CONTROLLER_REGISTERS_NOT_MODEL_JOINT_RADIANS",
            "motion_active": False,
            "named_pose": "KEYBOARD_FORWARD_CAL_1",
            "servo_register_positions": [2052, 2149, 1956, 2550, 2227, 2041, 2042],
            "trajectory_progress_permille": 1000,
            "freshness": "RETAINED_NOT_SYNCHRONIZED_TO_CURRENT_CAMERA_FRAME",
            "current_camera_synchronized": False,
        },
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**core, "intake_sha256": digest}


def _route(solution: dict[str, float]) -> dict:
    return {
        "status": "DENSE_SAMPLES_PASS_NOT_EXECUTABLE",
        "all_waypoints_accepted": True,
        "policy": {"maximum_joint_step_rad": 0.35},
        "round": {
            "joint_results": [
                {
                    "waypoint_sequence": 0,
                    "phase": "PARK",
                    "semantic_target": None,
                    "accepted": True,
                    "solution_arm_joint_positions_rad": solution,
                }
            ]
        },
    }


def _seeded_route(solution: dict[str, float]) -> tuple[dict, dict]:
    route = _route(solution)
    route["status"] = "DENSE_ROUTE_FAILED"
    route["all_waypoints_accepted"] = False
    route["round"]["evaluated_waypoint_count"] = 1
    first = route["round"]["joint_results"][0]
    first.update(
        {
            "accepted": False,
            "previous_solution_seed_supplied": True,
            "maximum_joint_delta_rad": 1.688447331924208,
            "failure_reason": "MAXIMUM_ADJACENT_JOINT_DELTA_EXCEEDED",
        }
    )
    return {}, route


def test_reference_projection_and_outside_step_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    solution = {
        "base_link_to_link1": 0.0817809840033888,
        "link1_to_link2": 1.0217261781881184,
        "link2_to_link3": 0.6524073503892807,
        "link3_to_link4": -0.10333354262067762,
        "link4_to_link5": 0.0,
    }
    monkeypatch.setattr(
        subject,
        "run_with_route_evidence",
        lambda *args, **kwargs: (
            {
                "report_sha256": "a" * 64,
                "derived_contact_proposal": {"schema": "test"},
            },
            _route(solution),
        ),
    )
    monkeypatch.setattr(
        subject,
        "run_seeded_model_motion",
        lambda *args, **kwargs: _seeded_route(solution),
    )
    report = subject.run(
        _intake(),
        workspace=WORKSPACE,
        profile_path=WORKSPACE / "software/config/virtual_commissioning_profile.json",
    )
    projected = report["reference_projection"]["arm_joint_positions_rad"]
    assert projected == pytest.approx(
        {
            "base_link_to_link1": -4 * 2 * math.pi / 4096,
            "link1_to_link2": 101 * 2 * math.pi / 4096,
            "link2_to_link3": 1526 * 2 * math.pi / 4096,
            "link3_to_link4": 179 * 2 * math.pi / 4096,
            "link4_to_link5": 7 * 2 * math.pi / 4096,
        }
    )
    assert report["status"] == "REFERENCE_START_OUTSIDE_FIRST_ROUTE_JOINT_STEP"
    assert report["first_route_transition"]["within_route_joint_step"] is False
    assert report["first_route_transition"][
        "maximum_absolute_joint_delta_rad"
    ] == pytest.approx(1.688447331924208)
    assert report["seeded_entry_route"]["all_waypoints_accepted"] is False
    assert report["seeded_entry_route"]["first_waypoint"]["failure_reason"] == (
        "MAXIMUM_ADJACENT_JOINT_DELTA_EXCEEDED"
    )
    assert report["physical_execution_authorized"] is False
    assert report["controller_commands"] == []
    assert report["transport_writes"] == 0


def test_reference_start_contract_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "run_with_route_evidence",
        lambda *args, **kwargs: pytest.fail("route must not run for invalid input"),
    )
    intake = _intake()
    intake["arm_start_evidence"]["current_camera_synchronized"] = True
    with pytest.raises(ValueError, match="cannot claim camera synchronization"):
        subject.run(
            intake,
            workspace=WORKSPACE,
            profile_path=WORKSPACE
            / "software/config/virtual_commissioning_profile.json",
        )
