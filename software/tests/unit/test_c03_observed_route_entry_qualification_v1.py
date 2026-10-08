from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
    MeasuredSegmentConfigurationSample,
    build_bounded_joint_sample_plan_from_results,
)
from rocell.application.c03_observed_route_entry_qualification_v1 import (
    CLEAR_STATUS,
    COLLISION_STATUS,
    INDETERMINATE_STATUS,
    C03ObservedRouteEntryQualificationV1Error,
    parse_c03_observed_route_entry_qualification_v1,
    qualify_c03_observed_route_entry_v1,
)
from rocell.application.context import load_simulation_context
from rocell.application.observed_planner_start_state import ObservedPlannerStartState
from rocell.kinematics import ARM_JOINT_NAMES

from test_c03_route_collision_handoff_v1 import _result
from test_fk_collision_pose_adapter import bindings, cable, profile
from test_partitioned_typing_collision_intake_v1 import _inputs as route_inputs
from test_typing_observed_route_entry_sweep_v1 import sweep_envelopes


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _observed(measured, joints, *, valid_until=1_000):
    model = {
        "b_base": joints[ARM_JOINT_NAMES[0]],
        "s_shoulder": joints[ARM_JOINT_NAMES[1]],
        "e_elbow": joints[ARM_JOINT_NAMES[2]],
        "t_wrist_pitch": joints[ARM_JOINT_NAMES[3]],
        "r_wrist_roll": joints[ARM_JOINT_NAMES[4]],
        "g_gripper": 0.0,
    }
    return ObservedPlannerStartState(
        run_id="icq7-test-read",
        arm_identity_sha256=measured.robot_reference_identity["arm_identity_hash"],
        controller_session_id="controller-session-icq7",
        request_context_sha256="4" * 64,
        feedback_receipt_sha256="5" * 64,
        calibration_snapshot_sha256=measured.snapshot_sha256,
        manifest_id=measured.manifest_id,
        active_build_id=measured.active_build_id,
        response_completed_monotonic_ns=100,
        available_monotonic_ns=101,
        valid_until_monotonic_ns=valid_until,
        controller_joint_positions_rad={
            "b": model["b_base"], "s": model["s_shoulder"],
            "e": model["e_elbow"], "t": model["t_wrist_pitch"],
            "r": model["r_wrist_roll"], "g": 0.0,
        },
        model_joint_positions_rad=model,
    )


def _inputs(context, monkeypatch, *, colliding=False, stale=False):
    route_result = _result(context)
    route = route_result["route_result"]
    route["tool_configuration_sha256"] = "6" * 64
    route["target_catalog_sha256"] = "7" * 64
    unsigned = dict(route)
    unsigned.pop("receipt_sha256")
    route["receipt_sha256"] = handoff_module._sha256(unsigned)
    outer = dict(route_result)
    outer.pop("receipt_sha256")
    route_result["receipt_sha256"] = handoff_module._sha256(outer)
    monkeypatch.setattr(
        handoff_module, "EXPECTED_ROUTE_RECEIPT_SHA256", route["receipt_sha256"]
    )
    monkeypatch.setattr(
        handoff_module,
        "EXPECTED_RESULT_RECEIPT_SHA256",
        route_result["receipt_sha256"],
    )
    measured, _execution, _trajectory, _ik = route_inputs(context)
    endpoint = route["ik_screen"]["joint_results"][0][
        "solution_arm_joint_positions_rad"
    ]
    start = dict(endpoint)
    start[ARM_JOINT_NAMES[0]] -= 0.04
    observed = _observed(measured, start, valid_until=150 if stale else 1_000)
    policy = BoundedSegmentSamplingPolicy(maximum_joint_step_rad=0.02)
    endpoint_result = dict(route["ik_screen"]["joint_results"][0])
    endpoint_result["waypoint_sequence"] = 0
    plan = build_bounded_joint_sample_plan_from_results(
        start, (endpoint_result,), policy
    )
    configuration = tuple(
        MeasuredSegmentConfigurationSample(
            item.sample_sequence, item.content_sha256, cable()[0]
        )
        for item in plan
    )
    sweeps = sweep_envelopes(plan, colliding=colliding)
    return (
        route_result, observed, measured, profile(context), policy,
        configuration, sweeps,
    )


def _qualify(context, monkeypatch, *, colliding=False, stale=False):
    route, observed, measured, installed, policy, configuration, sweeps = _inputs(
        context, monkeypatch, colliding=colliding, stale=stale
    )
    return qualify_c03_observed_route_entry_v1(
        route, observed, context, measured, installed, bindings(),
        configuration if not stale else (), sweeps if not stale else (),
        evaluated_monotonic_ns=200, policy=policy,
    )


def test_clear_entry_binds_exact_route_observation_geometry_and_zero_authority(
    context, monkeypatch
):
    report = _qualify(context, monkeypatch)
    assert parse_c03_observed_route_entry_qualification_v1(report) == report
    assert report["status"] == CLEAR_STATUS
    assert report["sample_count"] == 3
    assert report["entry_samples_collision_free"] is True
    assert report["entry_continuous_sweep_clear"] is True
    assert report["synthetic_route_execution_eligible"] is False
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_stale_observation_fails_closed_and_requires_replanning(context, monkeypatch):
    report = _qualify(context, monkeypatch, stale=True)
    assert report["status"] == INDETERMINATE_STATUS
    assert report["sample_count"] == 0
    assert report["mismatch_requires_replanning"] is True
    assert report["bounded_collision_qualification"] is None
    assert parse_c03_observed_route_entry_qualification_v1(report) == report


def test_between_sample_collision_is_retained_as_collision(context, monkeypatch):
    report = _qualify(context, monkeypatch, colliding=True)
    assert report["status"] == COLLISION_STATUS
    assert report["collision_detected"] is True
    assert report["entry_continuous_sweep_clear"] is False
    assert parse_c03_observed_route_entry_qualification_v1(report) == report


def test_wrong_route_identity_and_resealed_authority_are_rejected(context, monkeypatch):
    route, observed, measured, installed, policy, configuration, sweeps = _inputs(
        context, monkeypatch
    )
    changed_route = copy.deepcopy(route)
    changed_route["route_result"]["tool_configuration_sha256"] = "8" * 64
    with pytest.raises(C03ObservedRouteEntryQualificationV1Error, match="invalid receipt"):
        qualify_c03_observed_route_entry_v1(
            changed_route, observed, context, measured, installed, bindings(),
            configuration, sweeps, evaluated_monotonic_ns=200, policy=policy,
        )

    report = _qualify(context, monkeypatch)
    changed = copy.deepcopy(report)
    changed["physical_authority"] = True
    unsigned = dict(changed)
    unsigned.pop("c03_observed_route_entry_qualification_sha256")
    changed["c03_observed_route_entry_qualification_sha256"] = hashlib.sha256(
        _canonical(unsigned)
    ).hexdigest()
    with pytest.raises(C03ObservedRouteEntryQualificationV1Error, match="authority"):
        parse_c03_observed_route_entry_qualification_v1(changed)

