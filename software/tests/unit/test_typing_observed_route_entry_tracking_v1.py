from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rocell.application.typing_observed_route_entry_tracking_v1 import (
    InstalledJointTrackingObservationPolicyV1,
    REQUIRED_NEXT_EVIDENCE,
    STATUS,
    RetainedJointTrackingObservationV1,
    TypingObservedRouteEntryTrackingV1Error,
    parse_typing_observed_route_entry_tracking_v1,
    qualify_typing_observed_route_entry_tracking_v1,
)
from rocell.kinematics import ARM_JOINT_NAMES

from test_typing_observed_route_entry_dynamics_v1 import _qualified


def _limits(value):
    return {name: value for name in ARM_JOINT_NAMES}


def _policy(context, entry, **changes):
    values = {
        "policy_id": "fixture-installed-tracking-policy",
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "controller_session_id": entry["controller_session_id"],
        "qualification_evidence_sha256": "8" * 64,
        "maximum_tracking_error_rad": _limits(0.01),
        "maximum_timing_error_ns": 1_000_000,
        "minimum_settling_samples": 2,
    }
    values.update(changes)
    return InstalledJointTrackingObservationPolicyV1(**values)


def _observations(dynamics, *, offset=0.0, dwell_delta=0):
    samples = dynamics["schedule"]["samples"]
    base = 10_000_000_000
    result = []
    for item in samples:
        positions = dict(item["joint_positions_rad"])
        positions[ARM_JOINT_NAMES[0]] += offset
        result.append(RetainedJointTrackingObservationV1(
            phase="TRACKING",
            scheduled_sample_sequence=item["sample_sequence"],
            captured_monotonic_ns=base + item["time_from_start_ns"],
            schedule_elapsed_ns=item["time_from_start_ns"],
            joint_positions_rad=positions,
            joint_velocities_rad_s=_limits(0.0),
            source_record_sha256=f"{item['sample_sequence'] + 1:064x}",
        ))
    total = dynamics["schedule"]["total_motion_time_ns"]
    dwell = dynamics["dynamics_profile"]["settle_dwell_ns"] + dwell_delta
    endpoint = samples[-1]
    for index, elapsed in enumerate((total + 1, total + dwell + 1)):
        result.append(RetainedJointTrackingObservationV1(
            phase="SETTLING",
            scheduled_sample_sequence=endpoint["sample_sequence"],
            captured_monotonic_ns=base + elapsed,
            schedule_elapsed_ns=elapsed,
            joint_positions_rad=endpoint["joint_positions_rad"],
            joint_velocities_rad_s=_limits(0.0),
            source_record_sha256=f"{900 + index:064x}",
        ))
    return tuple(result)


def _report():
    context, entry, _sweep, _profile_value, dynamics = _qualified()
    policy = _policy(context, entry)
    observations = _observations(dynamics)
    report = qualify_typing_observed_route_entry_tracking_v1(
        dynamics,
        context,
        policy,
        observations,
        source_export_sha256="a" * 64,
        native_identity_sha256="b" * 64,
        acquisition_qualification_sha256="c" * 64,
    )
    return context, entry, dynamics, policy, observations, report


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("observed_route_entry_tracking_sha256")
    value["observed_route_entry_tracking_sha256"] = hashlib.sha256(json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_retained_sample_tracking_and_endpoint_settling_remain_zero_authority():
    _context, _entry, dynamics, _policy_value, observations, report = _report()
    assert parse_typing_observed_route_entry_tracking_v1(report) == report
    assert report["status"] == STATUS
    assert report["sampled_tracking_qualified"] is True
    assert report["endpoint_settling_observed"] is True
    assert report["continuous_controller_tracking_qualified"] is False
    assert report["continuous_collision_proven"] is False
    assert report["analysis"]["tracking_sample_count"] == dynamics["sample_count"]
    assert report["analysis"]["settling_sample_count"] == 2
    assert len(report["observations"]) == len(observations)
    assert report["required_next_evidence"] == list(REQUIRED_NEXT_EVIDENCE)
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_rejects_crossed_policy_tracking_error_and_short_settling_dwell():
    context, entry, _sweep, _profile_value, dynamics = _qualified()
    crossed = _policy(context, entry, controller_session_id="crossed-session")
    with pytest.raises(TypingObservedRouteEntryTrackingV1Error, match="lineage"):
        qualify_typing_observed_route_entry_tracking_v1(
            dynamics,
            context,
            crossed,
            _observations(dynamics),
            source_export_sha256="a" * 64,
            native_identity_sha256="b" * 64,
            acquisition_qualification_sha256="c" * 64,
        )
    policy = _policy(context, entry)
    with pytest.raises(TypingObservedRouteEntryTrackingV1Error, match="tracking"):
        qualify_typing_observed_route_entry_tracking_v1(
            dynamics,
            context,
            policy,
            _observations(dynamics, offset=0.02),
            source_export_sha256="a" * 64,
            native_identity_sha256="b" * 64,
            acquisition_qualification_sha256="c" * 64,
        )
    with pytest.raises(TypingObservedRouteEntryTrackingV1Error, match="dwell"):
        qualify_typing_observed_route_entry_tracking_v1(
            dynamics,
            context,
            policy,
            _observations(dynamics, dwell_delta=-1),
            source_export_sha256="a" * 64,
            native_identity_sha256="b" * 64,
            acquisition_qualification_sha256="c" * 64,
        )


def test_rejects_resealed_observation_and_authority_tamper():
    _context, _entry, _dynamics, _policy_value, _observations_value, report = (
        _report()
    )
    changed = copy.deepcopy(report)
    changed["observations"][0]["schedule_elapsed_ns"] += 1
    changed["observation_set_sha256"] = hashlib.sha256(json.dumps(
        changed["observations"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryTrackingV1Error, match="analysis"):
        parse_typing_observed_route_entry_tracking_v1(changed)

    changed = copy.deepcopy(report)
    changed["eligible_for_executor"] = True
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryTrackingV1Error, match="authority"):
        parse_typing_observed_route_entry_tracking_v1(changed)
