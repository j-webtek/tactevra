from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
import jsonschema

from rocell.application.pre_camera_typing_qualification_basis_v1 import (
    load_pre_camera_typing_qualification_basis_v1,
)
from rocell.application.typing_joint_schedule_v1 import (
    TypingJointDynamicsProfileV1,
    TypingJointScheduleV1Error,
    compile_typing_joint_schedule_v1,
    dynamics_profile_from_pc0_basis_v1,
    parse_typing_joint_schedule_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    READY_STATUS as IK_READY_STATUS,
)
from rocell.application.typing_trajectory_plan_v1 import (
    QuinticTimingSegmentV1,
    TimingConstraintV1,
    TypingPhaseWaypointV1,
    TypingScreeningSampleV1,
    TypingTrajectoryMetricsV1,
    TypingTrajectoryPlanV1,
    TypingTrajectoryPolicyV1,
)
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.models import Point3Mm
from rocell.motion.primitives import MotionPhase


WORKSPACE = Path(__file__).resolve().parents[3]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _plan() -> TypingTrajectoryPlanV1:
    policy = TypingTrajectoryPolicyV1(
        policy_id="pc1-test-cartesian",
        maximum_cartesian_step_mm=5.0,
        maximum_velocity_mm_s=80.0,
        maximum_acceleration_mm_s2=160.0,
        maximum_jerk_mm_s3=800.0,
        hover_settle_ms=100,
        contact_dwell_ms=60,
    )
    park = Point3Mm("board", 0.0, 0.0, 10.0)
    hover = Point3Mm("board", 10.0, 0.0, 10.0)
    contact = Point3Mm("board", 10.0, 0.0, 9.0)
    waypoints = (
        TypingPhaseWaypointV1(0, MotionPhase.PARK, None, None, park),
        TypingPhaseWaypointV1(1, MotionPhase.HOVER, 0, "H", hover),
        TypingPhaseWaypointV1(2, MotionPhase.CONTACT, 0, "H", contact),
    )
    samples = (
        TypingScreeningSampleV1(
            0, 0, MotionPhase.PARK, None, None, park, True
        ),
        TypingScreeningSampleV1(
            1,
            1,
            MotionPhase.TRANSIT,
            0,
            "H",
            Point3Mm("board", 5.0, 0.0, 10.0),
            False,
        ),
        TypingScreeningSampleV1(
            2, 1, MotionPhase.HOVER, 0, "H", hover, True
        ),
        TypingScreeningSampleV1(
            3, 2, MotionPhase.CONTACT, 0, "H", contact, True
        ),
    )
    timings = (
        QuinticTimingSegmentV1(
            0,
            0,
            1,
            10.0,
            100.0,
            100,
            TimingConstraintV1.VELOCITY,
            1.0,
            1.0,
            1.0,
        ),
        QuinticTimingSegmentV1(
            1,
            1,
            2,
            1.0,
            50.0,
            60,
            TimingConstraintV1.VELOCITY,
            1.0,
            1.0,
            1.0,
        ),
    )
    metrics = TypingTrajectoryMetricsV1(
        direct_distance_mm=11.0,
        park_baseline_distance_mm=21.0,
        direct_motion_time_ms=150.0,
        direct_dwell_time_ms=160,
        direct_estimated_time_ms=310.0,
        park_baseline_estimated_time_ms=400.0,
        estimated_time_saved_ms=90.0,
        estimated_time_reduction_fraction=0.225,
    )
    return TypingTrajectoryPlanV1(
        source_plan_sha256="a" * 64,
        policy=policy,
        phase_waypoints=waypoints,
        screening_samples=samples,
        timing_segments=timings,
        metrics=metrics,
    )


def _positions(sequence: int) -> dict[str, float]:
    fraction = (0.0, 0.2, 0.4, 0.45)[sequence]
    return {
        name: fraction / (index + 1)
        for index, name in enumerate(ARM_JOINT_NAMES)
    }


def _ik_report(plan: TypingTrajectoryPlanV1) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "rocell.typing_trajectory_ik_screen.v1",
        "status": IK_READY_STATUS,
        "typing_trajectory_plan_sha256": plan.trajectory_plan_sha256,
        "typing_execution_plan_sha256": plan.source_plan_sha256,
        "trajectory_policy_sha256": plan.policy.policy_sha256,
        "sample_count": len(plan.screening_samples),
        "evaluated_sample_count": len(plan.screening_samples),
        "ik_screening_executed": True,
        "ik_all_samples_accepted": True,
        "collision_screening_executed": False,
        "seed": {"source_kind": "SYNTHETIC_OFFLINE"},
        "joint_results": [
            {
                "waypoint_sequence": sample.sequence,
                "phase": sample.phase.value,
                "action_index": sample.action_index,
                "semantic_target": sample.target_id,
                "accepted": True,
                "solution_arm_joint_positions_rad": _positions(sample.sequence),
                "hardware_commands_generated": 0,
            }
            for sample in plan.screening_samples
        ],
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    report["typing_trajectory_ik_screen_sha256"] = hashlib.sha256(
        _canonical(report)
    ).hexdigest()
    return report


def _profile(**overrides: object) -> TypingJointDynamicsProfileV1:
    values: dict[str, object] = {
        "profile_id": "pc1-unit-synthetic",
        "source_kind": "SYNTHETIC_OFFLINE",
        "maximum_velocity_rad_s": {name: 0.5 for name in ARM_JOINT_NAMES},
        "maximum_acceleration_rad_s2": {
            name: 1.0 for name in ARM_JOINT_NAMES
        },
        "maximum_jerk_rad_s3": {name: 4.0 for name in ARM_JOINT_NAMES},
        "maximum_time_scale_factor": 20.0,
    }
    values.update(overrides)
    return TypingJointDynamicsProfileV1(**values)


def _rehash(report: dict[str, object]) -> None:
    report.pop("typing_trajectory_ik_screen_sha256", None)
    report["typing_trajectory_ik_screen_sha256"] = hashlib.sha256(
        _canonical(report)
    ).hexdigest()


def _rehash_schedule(document: dict[str, object]) -> None:
    document.pop("schedule_sha256", None)
    document["schedule_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()


def test_exact_ik_order_becomes_deterministic_zero_authority_schedule():
    plan = _plan()
    report = _ik_report(plan)
    first = compile_typing_joint_schedule_v1(plan, report, _profile())
    second = compile_typing_joint_schedule_v1(plan, report, _profile())

    assert first.to_dict() == second.to_dict()
    assert parse_typing_joint_schedule_v1(first.to_dict()).to_dict() == first.to_dict()
    assert first.time_scale_factor > 1.0
    assert [item.sequence for item in first.samples] == [0, 1, 2, 3]
    assert [item.phase for item in first.samples] == [
        "PARK",
        "TRANSIT",
        "HOVER",
        "CONTACT",
    ]
    assert [item.time_from_start_ns for item in first.samples] == sorted(
        item.time_from_start_ns for item in first.samples
    )
    assert len(first.segments) == len(first.samples) - 1
    assert [segment.destination_sample_sequence for segment in first.segments] == [
        1,
        2,
        3,
    ]
    assert all(
        segment.duration_ns
        == first.samples[index + 1].time_from_start_ns
        - first.samples[index].time_from_start_ns
        for index, segment in enumerate(first.segments)
    )
    assert all(
        margin >= 0.0
        for segment in first.segments
        for margins in (
            segment.velocity_margin_rad_s,
            segment.acceleration_margin_rad_s2,
            segment.jerk_margin_rad_s3,
        )
        for margin in margins.values()
    )
    assert first.to_dict()["controller_commands"] == []
    assert first.to_dict()["hardware_commands_generated"] == 0
    assert first.to_dict()["physical_authority"] is False
    schema = json.loads(
        (
            WORKSPACE / "software/ai/schemas/typing_joint_schedule_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(first.to_dict())
    assert all(
        first.peak_velocity_rad_s[name]
        <= first.profile.maximum_velocity_rad_s[name] + 1e-12
        for name in ARM_JOINT_NAMES
    )
    assert all(
        first.peak_acceleration_rad_s2[name]
        <= first.profile.maximum_acceleration_rad_s2[name] + 1e-12
        for name in ARM_JOINT_NAMES
    )
    assert all(
        first.peak_jerk_rad_s3[name]
        <= first.profile.maximum_jerk_rad_s3[name] + 1e-12
        for name in ARM_JOINT_NAMES
    )


def test_pc0_profile_is_loaded_with_synthetic_identity_and_no_qualification():
    basis = load_pre_camera_typing_qualification_basis_v1(WORKSPACE)
    profile = dynamics_profile_from_pc0_basis_v1(basis)

    assert profile.source_kind == "SYNTHETIC_OFFLINE"
    assert profile.physical_tracking_qualification is False
    assert tuple(profile.maximum_velocity_rad_s) == ARM_JOINT_NAMES
    assert profile.profile_sha256 == profile.profile_sha256


def test_report_hash_and_semantic_order_fail_closed():
    plan = _plan()
    mutated = _ik_report(plan)
    mutated["sample_count"] = 99
    with pytest.raises(TypingJointScheduleV1Error, match="hash is invalid"):
        compile_typing_joint_schedule_v1(plan, mutated, _profile())

    crossed = _ik_report(plan)
    crossed["joint_results"][1]["phase"] = "CONTACT"  # type: ignore[index]
    _rehash(crossed)
    with pytest.raises(TypingJointScheduleV1Error, match="semantic binding"):
        compile_typing_joint_schedule_v1(plan, crossed, _profile())


def test_nonfinite_limits_and_unbounded_required_scaling_are_rejected():
    with pytest.raises(TypingJointScheduleV1Error, match="must be finite"):
        _profile(
            maximum_velocity_rad_s={
                name: math.nan if index == 0 else 1.0
                for index, name in enumerate(ARM_JOINT_NAMES)
            }
        )

    plan = _plan()
    with pytest.raises(TypingJointScheduleV1Error, match="exceeds the profile"):
        compile_typing_joint_schedule_v1(
            plan,
            _ik_report(plan),
            _profile(maximum_time_scale_factor=1.01),
        )


def test_stationary_sample_and_direction_reversal_remain_explicit_and_bounded():
    plan = _plan()
    report = _ik_report(plan)
    results = report["joint_results"]  # type: ignore[assignment]
    results[2]["solution_arm_joint_positions_rad"] = dict(  # type: ignore[index]
        results[1]["solution_arm_joint_positions_rad"]  # type: ignore[index]
    )
    results[3]["solution_arm_joint_positions_rad"] = {  # type: ignore[index]
        name: -0.1 / (index + 1)
        for index, name in enumerate(ARM_JOINT_NAMES)
    }
    _rehash(report)

    schedule = compile_typing_joint_schedule_v1(plan, report, _profile())

    assert all(value == 0.0 for value in schedule.segments[1].velocity_rad_s.values())
    assert any(
        value > 0.0 for value in schedule.segments[2].acceleration_rad_s2.values()
    )
    assert all(
        value >= 0.0
        for segment in schedule.segments
        for value in segment.velocity_margin_rad_s.values()
    )


def test_crossed_joint_order_and_source_lineage_reject_after_valid_rehash():
    plan = _plan()
    crossed = _ik_report(plan)
    results = crossed["joint_results"]  # type: ignore[assignment]
    joint_values = results[1]["solution_arm_joint_positions_rad"]  # type: ignore[index]
    results[1]["solution_arm_joint_positions_rad"] = dict(  # type: ignore[index]
        reversed(tuple(joint_values.items()))  # type: ignore[union-attr]
    )
    _rehash(crossed)
    with pytest.raises(TypingJointScheduleV1Error, match="canonical arm-joint order"):
        compile_typing_joint_schedule_v1(plan, crossed, _profile())

    wrong_source = _ik_report(plan)
    wrong_source["typing_trajectory_plan_sha256"] = "f" * 64
    _rehash(wrong_source)
    with pytest.raises(TypingJointScheduleV1Error, match="exact accepted"):
        compile_typing_joint_schedule_v1(plan, wrong_source, _profile())


def test_schedule_parser_rejects_crossed_profile_hash_and_timestamp():
    schedule = compile_typing_joint_schedule_v1(
        _plan(), _ik_report(_plan()), _profile()
    ).to_dict()
    crossed_profile = json.loads(json.dumps(schedule))
    crossed_profile["profile_sha256"] = "f" * 64
    _rehash_schedule(crossed_profile)
    with pytest.raises(TypingJointScheduleV1Error, match="profile hash"):
        parse_typing_joint_schedule_v1(crossed_profile)

    crossed_time = json.loads(json.dumps(schedule))
    crossed_time["samples"][1]["time_from_start_ns"] += 1  # type: ignore[index]
    _rehash_schedule(crossed_time)
    with pytest.raises(TypingJointScheduleV1Error, match="segment/sample timing"):
        parse_typing_joint_schedule_v1(crossed_time)


@pytest.mark.parametrize(
    ("expected_constraint", "velocity", "acceleration", "jerk"),
    (
        ("VELOCITY", 0.1, 1_000.0, 10_000.0),
        ("ACCELERATION", 100.0, 0.1, 10_000.0),
        ("JERK", 100.0, 1_000.0, 0.1),
    ),
)
def test_each_dynamic_dimension_has_a_bounded_just_inside_and_outside_scale(
    expected_constraint: str,
    velocity: float,
    acceleration: float,
    jerk: float,
):
    plan = _plan()
    report = _ik_report(plan)
    wide = _profile(
        maximum_velocity_rad_s={name: velocity for name in ARM_JOINT_NAMES},
        maximum_acceleration_rad_s2={
            name: acceleration for name in ARM_JOINT_NAMES
        },
        maximum_jerk_rad_s3={name: jerk for name in ARM_JOINT_NAMES},
        maximum_time_scale_factor=1_000.0,
    )
    baseline = compile_typing_joint_schedule_v1(plan, report, wide)
    assert baseline.limiting_constraint == expected_constraint

    just_inside = _profile(
        maximum_velocity_rad_s=wide.maximum_velocity_rad_s,
        maximum_acceleration_rad_s2=wide.maximum_acceleration_rad_s2,
        maximum_jerk_rad_s3=wide.maximum_jerk_rad_s3,
        maximum_time_scale_factor=baseline.time_scale_factor * (1.0 + 1e-6),
    )
    accepted = compile_typing_joint_schedule_v1(plan, report, just_inside)
    assert accepted.time_scale_factor <= just_inside.maximum_time_scale_factor

    just_outside = _profile(
        maximum_velocity_rad_s=wide.maximum_velocity_rad_s,
        maximum_acceleration_rad_s2=wide.maximum_acceleration_rad_s2,
        maximum_jerk_rad_s3=wide.maximum_jerk_rad_s3,
        maximum_time_scale_factor=baseline.time_scale_factor * (1.0 - 1e-6),
    )
    with pytest.raises(TypingJointScheduleV1Error, match="exceeds the profile"):
        compile_typing_joint_schedule_v1(plan, report, just_outside)
