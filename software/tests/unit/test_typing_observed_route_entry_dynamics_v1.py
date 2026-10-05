from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rocell.application.bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
)
from rocell.application.typing_observed_route_entry_collision_v1 import (
    qualify_typing_observed_route_entry_collision_v1,
)
from rocell.application.typing_observed_route_entry_dynamics_v1 import (
    MeasuredTypingJointDynamicsProfileV1,
    REQUIRED_NEXT_EVIDENCE,
    STATUS,
    TypingObservedRouteEntryDynamicsV1Error,
    parse_typing_observed_route_entry_dynamics_v1,
    qualify_typing_observed_route_entry_dynamics_v1,
    schedule_bounded_joint_samples_v1,
)
from rocell.application.typing_observed_route_entry_sweep_v1 import (
    qualify_typing_observed_route_entry_sweep_v1,
)
from rocell.kinematics import ARM_JOINT_NAMES

from test_fk_collision_pose_adapter import bindings, sweep_envelopes
from test_typing_observed_route_entry_collision_v1 import _inputs
from test_typing_observed_route_entry_sweep_v1 import _plan


def _limits(value):
    return {name: value for name in ARM_JOINT_NAMES}


def _profile(context, entry, **changes):
    values = {
        "profile_id": "fixture-installed-entry-dynamics",
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "controller_session_id": entry["controller_session_id"],
        "qualification_evidence_sha256": "9" * 64,
        "qualified_monotonic_ns": 1_000_000,
        "valid_until_monotonic_ns": 2_000_000,
        "maximum_velocity_rad_s": _limits(100.0),
        "maximum_acceleration_rad_s2": _limits(1_000.0),
        "maximum_jerk_rad_s3": _limits(10_000.0),
        "maximum_time_scale_factor": 1_000.0,
        "minimum_segment_duration_ns": 1_000_000_000,
        "controller_update_period_ns": 1_000_000,
        "settle_position_tolerance_rad": _limits(0.01),
        "settle_velocity_tolerance_rad_s": _limits(0.05),
        "settle_dwell_ns": 200_000_000,
    }
    values.update(changes)
    return MeasuredTypingJointDynamicsProfileV1(**values)


def _qualified():
    context, measured, installed, entry, configuration = _inputs()
    collision = qualify_typing_observed_route_entry_collision_v1(
        entry, context, measured, installed, bindings(), configuration
    )
    sweep = qualify_typing_observed_route_entry_sweep_v1(
        entry,
        collision,
        context,
        installed,
        bindings(),
        sweep_envelopes(_plan(entry)),
    )
    profile = _profile(context, entry)
    report = qualify_typing_observed_route_entry_dynamics_v1(
        entry, sweep, context, profile, evaluated_monotonic_ns=1_500_000
    )
    return context, entry, sweep, profile, report


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("observed_route_entry_dynamics_sha256")
    value["observed_route_entry_dynamics_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def test_measured_limit_schedule_is_reproducible_and_retains_execution_gates():
    _context, _entry, _sweep, profile, report = _qualified()
    assert parse_typing_observed_route_entry_dynamics_v1(report) == report
    assert report["status"] == STATUS
    assert report["dynamics_profile_sha256"] == profile.profile_sha256
    assert report["planned_dynamics_within_measured_limits"] is True
    assert report["controller_tracking_qualified"] is False
    assert report["settling_observed"] is False
    assert report["continuous_collision_proven"] is False
    assert report["required_next_evidence"] == list(REQUIRED_NEXT_EVIDENCE)
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False
    period = profile.controller_update_period_ns
    assert all(
        item["time_from_start_ns"] % period == 0
        for item in report["schedule"]["samples"]
    )


def test_rejects_stale_cross_session_and_over_limit_schedules():
    context, entry, sweep, profile, _report = _qualified()
    with pytest.raises(TypingObservedRouteEntryDynamicsV1Error, match="stale"):
        qualify_typing_observed_route_entry_dynamics_v1(
            entry,
            sweep,
            context,
            profile,
            evaluated_monotonic_ns=2_000_001,
        )
    crossed = _profile(
        context, entry, controller_session_id="crossed-session"
    )
    with pytest.raises(TypingObservedRouteEntryDynamicsV1Error, match="lineage"):
        qualify_typing_observed_route_entry_dynamics_v1(
            entry, sweep, context, crossed, evaluated_monotonic_ns=1_500_000
        )

    positions = _limits(0.0)
    moved = _limits(0.0)
    moved[ARM_JOINT_NAMES[0]] = 1.0
    plan = (
        BoundedJointConfigurationSample(0, 0, 0, 1, 0.0, positions),
        BoundedJointConfigurationSample(1, 0, 1, 1, 1.0, moved),
    )
    constrained = _profile(
        context,
        entry,
        maximum_velocity_rad_s=_limits(0.001),
        maximum_acceleration_rad_s2=_limits(0.001),
        maximum_jerk_rad_s3=_limits(0.001),
        maximum_time_scale_factor=1.0,
        minimum_segment_duration_ns=1_000_000,
    )
    with pytest.raises(TypingObservedRouteEntryDynamicsV1Error, match="exceeds"):
        schedule_bounded_joint_samples_v1(plan, constrained)


def test_rejects_resealed_schedule_and_authority_tamper():
    _context, _entry, _sweep, _profile_value, report = _qualified()
    changed = copy.deepcopy(report)
    changed["schedule"]["segments"][0]["duration_ns"] += 1
    schedule_unsigned = dict(changed["schedule"])
    schedule_unsigned.pop("schedule_sha256")
    schedule_hash = hashlib.sha256(json.dumps(
        schedule_unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    changed["schedule"]["schedule_sha256"] = schedule_hash
    changed["schedule_sha256"] = schedule_hash
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryDynamicsV1Error, match="reproduce"):
        parse_typing_observed_route_entry_dynamics_v1(changed)

    changed = copy.deepcopy(report)
    changed["eligible_for_executor"] = True
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryDynamicsV1Error, match="authority"):
        parse_typing_observed_route_entry_dynamics_v1(changed)
