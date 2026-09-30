from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from rocell.application.installed_controller_qualification_v1 import (
    assess_installed_controller_qualification_v1,
)
from rocell.application.observed_planner_start_state import ObservedPlannerStartState
from rocell.application.typing_state_prerequisite_binding_v1 import (
    TypingStatePrerequisiteBindingV1Error,
    bind_typing_state_prerequisites_v1,
    parse_typing_state_prerequisite_binding_v1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner

import test_installed_controller_qualification_v1 as controller


def _inputs():
    ledger, _supervisor = runner._ledger()
    ledger.submit("mission-state", "state", runner._inputs(ledger, "state"))
    ledger.run_next_shadow()
    materialization = ledger.shadow_materialization("state")
    calibration = materialization["stage_artifacts"][
        "typing_trajectory_ik_screen"
    ]["calibration_snapshot_sha256"]
    profile = controller._profile()
    evidence = controller._evidence(profile)
    report = assess_installed_controller_qualification_v1(
        profile, evidence, evaluated_monotonic_ns=200
    )
    observed = ObservedPlannerStartState(
        run_id="run-state",
        arm_identity_sha256="1" * 64,
        controller_session_id=evidence.controller_session_id,
        request_context_sha256="2" * 64,
        feedback_receipt_sha256="3" * 64,
        calibration_snapshot_sha256=calibration,
        manifest_id="manifest",
        active_build_id="build",
        response_completed_monotonic_ns=100,
        available_monotonic_ns=110,
        valid_until_monotonic_ns=1_000,
        controller_joint_positions_rad={
            "b": 0.0, "s": 0.0, "e": 0.0,
            "t": 0.0, "r": 0.0, "g": 0.0,
        },
        model_joint_positions_rad={
            "b_base": 0.0, "s_shoulder": 0.0, "e_elbow": 0.0,
            "t_wrist_pitch": 0.0, "r_wrist_roll": 0.0, "g_gripper": 0.0,
        },
    )
    return materialization, observed, evidence, report


def test_binds_exact_fresh_state_and_removes_only_two_blockers():
    materialization, observed, evidence, report = _inputs()
    value = bind_typing_state_prerequisites_v1(
        materialization, observed, evidence, report, evaluated_monotonic_ns=200
    )
    assert parse_typing_state_prerequisite_binding_v1(value) == value
    assert value["resolved_blockers"] == [
        "FRESH_OBSERVED_START_STATE_REQUIRED",
        "FRESH_INSTALLED_CONTROLLER_QUALIFICATION_REQUIRED",
    ]
    assert value["remaining_blockers"] == [
        "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
        "MEASURED_TRAJECTORY_ENVELOPE_REQUIRED",
        "INSTALLED_COLLISION_PROFILE_REQUIRED",
        "CONTINUOUS_COLLISION_QUALIFICATION_REQUIRED",
        "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
        "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
    ]
    assert value["permit_review_ready"] is False
    assert value["controller_commands"] == value["wire_commands"] == []
    assert value["hardware_access"] is value["physical_authority"] is False


def test_rejects_stale_cross_session_and_cross_calibration_state():
    materialization, observed, evidence, report = _inputs()
    with pytest.raises(TypingStatePrerequisiteBindingV1Error, match="stale"):
        bind_typing_state_prerequisites_v1(
            materialization, observed, evidence, report,
            evaluated_monotonic_ns=1_001,
        )
    with pytest.raises(TypingStatePrerequisiteBindingV1Error, match="sessions"):
        bind_typing_state_prerequisites_v1(
            materialization,
            replace(observed, controller_session_id="other-session"),
            evidence,
            report,
            evaluated_monotonic_ns=200,
        )
    with pytest.raises(TypingStatePrerequisiteBindingV1Error, match="calibration"):
        bind_typing_state_prerequisites_v1(
            materialization,
            replace(observed, calibration_snapshot_sha256="f" * 64),
            evidence,
            report,
            evaluated_monotonic_ns=200,
        )


def test_rejects_crossed_controller_report_and_output_tamper():
    materialization, observed, evidence, report = _inputs()
    crossed = replace(report, qualification_evidence_sha256="f" * 64)
    with pytest.raises(TypingStatePrerequisiteBindingV1Error, match="crossed"):
        bind_typing_state_prerequisites_v1(
            materialization, observed, evidence, crossed,
            evaluated_monotonic_ns=200,
        )
    value = bind_typing_state_prerequisites_v1(
        materialization, observed, evidence, report, evaluated_monotonic_ns=200
    )
    changed = copy.deepcopy(value)
    changed["permit_review_ready"] = True
    with pytest.raises(TypingStatePrerequisiteBindingV1Error, match="hash"):
        parse_typing_state_prerequisite_binding_v1(changed)
