from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json

import pytest

from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.typing_observed_route_entry_v1 import (
    REQUIRED_NEXT_EVIDENCE,
    STATUS,
    TypingObservedRouteEntryV1Error,
    build_typing_observed_route_entry_v1,
    parse_typing_observed_route_entry_v1,
)

from test_typing_observed_trajectory_ik_v1 import _screened


def _entry():
    _materialization, seed, _context, _snapshot, observed_ik = _screened()
    report = build_typing_observed_route_entry_v1(
        observed_ik, seed,
        policy=BoundedSegmentSamplingPolicy(
            maximum_joint_step_rad=0.05, maximum_samples=256
        ),
    )
    return seed, observed_ik, report


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("observed_route_entry_sha256")
    value["observed_route_entry_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_builds_bounded_observed_to_park_envelope_without_authority():
    seed, observed_ik, report = _entry()
    assert parse_typing_observed_route_entry_v1(report) == report
    assert report["status"] == STATUS
    assert report["observed_trajectory_ik_sha256"] == (
        observed_ik["observed_trajectory_ik_sha256"]
    )
    assert report["observed_ik_seed_sha256"] == seed.observed_ik_seed_sha256
    assert report["route_entry_phase"] == "PARK"
    assert report["route_entry_target_id"] is None
    assert report["sample_plan"][0]["interpolation_ratio"] == 0.0
    assert report["sample_plan"][-1]["interpolation_ratio"] == 1.0
    assert report["maximum_joint_gap_rad"] <= 0.05 + 1e-12
    assert report["route_entry_envelope_completed"] is True
    assert report["route_entry_collision_qualified"] is False
    assert report["measured_dynamics_qualified"] is False
    assert report["required_next_evidence"] == list(REQUIRED_NEXT_EVIDENCE)
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_rejects_crossed_seed_and_forged_outer_seed_lineage():
    seed, observed_ik, _report = _entry()
    with pytest.raises(TypingObservedRouteEntryV1Error, match="different seed"):
        build_typing_observed_route_entry_v1(
            observed_ik, replace(seed, observed_start_state_sha256="f" * 64)
        )
    distant = replace(
        seed,
        joint_positions_rad={name: value + 0.2 for name, value in seed.joint_positions_rad.items()},
    )
    crossed = copy.deepcopy(observed_ik)
    crossed["observed_ik_seed_sha256"] = distant.observed_ik_seed_sha256
    crossed["observed_start_state_sha256"] = distant.observed_start_state_sha256
    unsigned = dict(crossed)
    unsigned.pop("observed_trajectory_ik_sha256")
    crossed["observed_trajectory_ik_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    with pytest.raises(TypingObservedRouteEntryV1Error, match="lineage"):
        build_typing_observed_route_entry_v1(
            crossed, distant,
        )


def test_rejects_resealed_sample_and_authority_tamper():
    _seed, _observed_ik, report = _entry()
    changed = copy.deepcopy(report)
    changed["sample_plan"][0]["joint_positions_rad"][next(iter(changed["start_joint_positions_rad"]))] += 0.01
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryV1Error, match="sample"):
        parse_typing_observed_route_entry_v1(changed)

    changed = copy.deepcopy(report)
    changed["sample_plan"][0]["subdivision_count"] += 1
    sample = dict(changed["sample_plan"][0])
    sample.pop("sample_sha256")
    changed["sample_plan"][0]["sample_sha256"] = hashlib.sha256(json.dumps(
        sample, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryV1Error, match="sample"):
        parse_typing_observed_route_entry_v1(changed)

    changed = copy.deepcopy(report)
    changed["eligible_for_executor"] = True
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryV1Error, match="authority"):
        parse_typing_observed_route_entry_v1(changed)
