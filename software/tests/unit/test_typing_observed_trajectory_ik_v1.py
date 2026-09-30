from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json

import pytest

from rocell.application.typing_observed_ik_seed_v1 import (
    build_typing_observed_ik_seed_v1,
)
from rocell.application.typing_observed_trajectory_ik_v1 import (
    READY_STATUS,
    REQUIRED_NEXT_EVIDENCE,
    TypingObservedTrajectoryIkV1Error,
    parse_typing_observed_trajectory_ik_v1,
    screen_typing_observed_trajectory_ik_v1,
)

from test_typing_observed_ik_seed_v1 import _inputs


def _screened():
    materialization, binding, observed, context, snapshot = _inputs()
    seed = build_typing_observed_ik_seed_v1(
        materialization, binding, observed, context, snapshot,
        evaluated_monotonic_ns=250,
    )
    report = screen_typing_observed_trajectory_ik_v1(
        materialization, seed, context, snapshot, evaluated_monotonic_ns=250
    )
    return materialization, seed, context, snapshot, report


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("observed_trajectory_ik_sha256")
    value["observed_trajectory_ik_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_rescreens_retained_route_from_observed_seed_without_authority():
    materialization, seed, _context, _snapshot, report = _screened()
    assert parse_typing_observed_trajectory_ik_v1(report) == report
    assert report["status"] == READY_STATUS
    assert report["materialization_sha256"] == materialization["materialization_sha256"]
    assert report["observed_ik_seed_sha256"] == seed.observed_ik_seed_sha256
    assert report["ik_all_samples_accepted"] is True
    assert report["evaluated_sample_count"] == report["sample_count"]
    assert report["canonical_ik_screen"]["seed"]["source_kind"] == (
        "PHYSICAL_OBSERVED_STATE"
    )
    assert report["measured_start_state_applied"] is True
    assert report["route_entry_envelope_completed"] is False
    assert report["measured_dynamics_qualified"] is False
    assert report["collision_screening_executed"] is False
    assert report["required_next_evidence"] == list(REQUIRED_NEXT_EVIDENCE)
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_rejects_stale_seed_and_crossed_materialization():
    materialization, seed, context, snapshot, _report = _screened()
    with pytest.raises(TypingObservedTrajectoryIkV1Error, match="stale"):
        screen_typing_observed_trajectory_ik_v1(
            materialization, seed, context, snapshot,
            evaluated_monotonic_ns=1_001,
        )
    crossed = replace(seed, materialization_sha256="f" * 64)
    with pytest.raises(TypingObservedTrajectoryIkV1Error, match="materialization"):
        screen_typing_observed_trajectory_ik_v1(
            materialization, crossed, context, snapshot,
            evaluated_monotonic_ns=250,
        )


def test_rejects_resealed_gate_or_nested_screen_tamper():
    _materialization, _seed, _context, _snapshot, report = _screened()
    changed = copy.deepcopy(report)
    changed["route_entry_envelope_completed"] = True
    _reseal(changed)
    with pytest.raises(TypingObservedTrajectoryIkV1Error, match="gates"):
        parse_typing_observed_trajectory_ik_v1(changed)

    changed = copy.deepcopy(report)
    changed["canonical_ik_screen"]["ik_all_samples_accepted"] = False
    _reseal(changed)
    with pytest.raises(TypingObservedTrajectoryIkV1Error, match="lineage"):
        parse_typing_observed_trajectory_ik_v1(changed)

    changed = copy.deepcopy(report)
    changed["ik_all_samples_accepted"] = False
    changed["status"] = "BLOCKED_OBSERVED_STATE_IK_SCREENING"
    _reseal(changed)
    with pytest.raises(TypingObservedTrajectoryIkV1Error, match="lineage"):
        parse_typing_observed_trajectory_ik_v1(changed)
