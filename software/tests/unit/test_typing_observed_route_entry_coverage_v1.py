from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rocell.application.typing_observed_route_entry_coverage_v1 import (
    InstalledJointTelemetryCoveragePolicyV1,
    REQUIRED_NEXT_EVIDENCE,
    STATUS,
    RetainedDenseJointTelemetrySampleV1,
    TypingObservedRouteEntryCoverageV1Error,
    parse_typing_observed_route_entry_coverage_v1,
    qualify_typing_observed_route_entry_coverage_v1,
)
from rocell.kinematics import ARM_JOINT_NAMES

from test_typing_observed_route_entry_tracking_v1 import _report


def _limits(value):
    return {name: value for name in ARM_JOINT_NAMES}


def _policy(context, entry, tracking, **changes):
    segments = tracking["observed_route_entry_dynamics"]["schedule"]["segments"]
    maximum_gap = max(item["duration_ns"] for item in segments) // 4
    values = {
        "policy_id": "fixture-installed-telemetry-coverage",
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "controller_session_id": entry["controller_session_id"],
        "qualification_evidence_sha256": "7" * 64,
        "maximum_observation_gap_ns": maximum_gap,
        "maximum_interpolated_error_rad": _limits(0.01),
    }
    values.update(changes)
    return InstalledJointTelemetryCoveragePolicyV1(**values)


def _samples(tracking, *, offset=0.0):
    scheduled = tracking["observed_route_entry_dynamics"]["schedule"]["samples"]
    base = 20_000_000_000
    result = []
    sequence = 0
    for segment in range(len(scheduled) - 1):
        start = scheduled[segment]
        end = scheduled[segment + 1]
        span = end["time_from_start_ns"] - start["time_from_start_ns"]
        velocity = {
            name: (
                end["joint_positions_rad"][name]
                - start["joint_positions_rad"][name]
            ) / (span / 1e9)
            for name in ARM_JOINT_NAMES
        }
        for division in range(4):
            ratio = division / 4
            elapsed = start["time_from_start_ns"] + span * division // 4
            positions = {
                name: start["joint_positions_rad"][name] + ratio * (
                    end["joint_positions_rad"][name]
                    - start["joint_positions_rad"][name]
                )
                for name in ARM_JOINT_NAMES
            }
            positions[ARM_JOINT_NAMES[0]] += offset
            result.append(RetainedDenseJointTelemetrySampleV1(
                captured_monotonic_ns=base + elapsed,
                schedule_elapsed_ns=elapsed,
                joint_positions_rad=positions,
                joint_velocities_rad_s=velocity,
                source_record_sha256=f"{sequence + 1:064x}",
            ))
            sequence += 1
    endpoint = scheduled[-1]
    result.append(RetainedDenseJointTelemetrySampleV1(
        captured_monotonic_ns=base + endpoint["time_from_start_ns"],
        schedule_elapsed_ns=endpoint["time_from_start_ns"],
        joint_positions_rad=endpoint["joint_positions_rad"],
        joint_velocities_rad_s=_limits(0.0),
        source_record_sha256=f"{sequence + 1:064x}",
    ))
    return tuple(result)


def _coverage():
    context, entry, _dynamics, _tracking_policy, _observations, tracking = _report()
    policy = _policy(context, entry, tracking)
    samples = _samples(tracking)
    report = qualify_typing_observed_route_entry_coverage_v1(
        tracking,
        context,
        policy,
        samples,
        source_export_sha256="d" * 64,
        native_identity_sha256="e" * 64,
        acquisition_qualification_sha256="f" * 64,
    )
    return context, entry, tracking, policy, samples, report


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("observed_route_entry_coverage_sha256")
    value["observed_route_entry_coverage_sha256"] = hashlib.sha256(json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_dense_coverage_bounds_gaps_and_interpolation_without_authority():
    _context, _entry, _tracking, policy, samples, report = _coverage()
    assert parse_typing_observed_route_entry_coverage_v1(report) == report
    assert report["status"] == STATUS
    assert report["bounded_motion_telemetry_coverage_qualified"] is True
    assert report["bounded_interpolated_tracking_qualified"] is True
    assert report["continuous_controller_tracking_qualified"] is False
    assert report["continuous_collision_proven"] is False
    assert report["coverage_analysis"]["telemetry_sample_count"] == len(samples)
    assert report["coverage_analysis"]["maximum_observation_gap_ns"] <= (
        policy.maximum_observation_gap_ns
    )
    assert report["required_next_evidence"] == list(REQUIRED_NEXT_EVIDENCE)
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_rejects_crossed_policy_gap_and_interpolated_tracking_error():
    context, entry, _dynamics, _tracking_policy, _observations, tracking = _report()
    crossed = _policy(
        context, entry, tracking, controller_session_id="crossed-session"
    )
    with pytest.raises(TypingObservedRouteEntryCoverageV1Error, match="lineage"):
        qualify_typing_observed_route_entry_coverage_v1(
            tracking,
            context,
            crossed,
            _samples(tracking),
            source_export_sha256="d" * 64,
            native_identity_sha256="e" * 64,
            acquisition_qualification_sha256="f" * 64,
        )
    policy = _policy(context, entry, tracking)
    sparse = tuple(
        item for index, item in enumerate(_samples(tracking))
        if index % 4 in {0, 3}
    )
    with pytest.raises(TypingObservedRouteEntryCoverageV1Error, match="gap"):
        qualify_typing_observed_route_entry_coverage_v1(
            tracking,
            context,
            policy,
            sparse,
            source_export_sha256="d" * 64,
            native_identity_sha256="e" * 64,
            acquisition_qualification_sha256="f" * 64,
        )
    with pytest.raises(TypingObservedRouteEntryCoverageV1Error, match="tracking"):
        qualify_typing_observed_route_entry_coverage_v1(
            tracking,
            context,
            policy,
            _samples(tracking, offset=0.02),
            source_export_sha256="d" * 64,
            native_identity_sha256="e" * 64,
            acquisition_qualification_sha256="f" * 64,
        )


def test_rejects_resealed_dense_sample_and_authority_tamper():
    _context, _entry, _tracking, _policy_value, _samples_value, report = _coverage()
    changed = copy.deepcopy(report)
    changed["telemetry_samples"][1]["schedule_elapsed_ns"] += 1
    changed["telemetry_set_sha256"] = hashlib.sha256(json.dumps(
        changed["telemetry_samples"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    _reseal(changed)
    with pytest.raises(
        TypingObservedRouteEntryCoverageV1Error,
        match="telemetry|analysis",
    ):
        parse_typing_observed_route_entry_coverage_v1(changed)

    changed = copy.deepcopy(report)
    changed["eligible_for_executor"] = True
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryCoverageV1Error, match="authority"):
        parse_typing_observed_route_entry_coverage_v1(changed)
