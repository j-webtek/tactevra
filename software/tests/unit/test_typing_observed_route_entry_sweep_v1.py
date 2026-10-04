from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rocell.application.bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
)
from rocell.application.typing_observed_route_entry_sweep_v1 import (
    CLEAR_STATUS,
    REQUIRED_NEXT_EVIDENCE,
    TypingObservedRouteEntrySweepV1Error,
    parse_typing_observed_route_entry_sweep_v1,
    qualify_typing_observed_route_entry_sweep_v1,
)

from test_fk_collision_pose_adapter import bindings, sweep_envelopes
from test_typing_observed_route_entry_collision_v1 import _inputs
from rocell.application.typing_observed_route_entry_collision_v1 import (
    qualify_typing_observed_route_entry_collision_v1,
)


def _plan(entry):
    return tuple(
        BoundedJointConfigurationSample(
            item["sample_sequence"],
            item["source_segment_index"],
            item["subdivision_index"],
            item["subdivision_count"],
            item["interpolation_ratio"],
            item["joint_positions_rad"],
        )
        for item in entry["sample_plan"]
    )


def _qualified(*, colliding=False):
    context, measured, installed, entry, configuration = _inputs()
    collision = qualify_typing_observed_route_entry_collision_v1(
        entry, context, measured, installed, bindings(), configuration
    )
    report = qualify_typing_observed_route_entry_sweep_v1(
        entry,
        collision,
        context,
        installed,
        bindings(),
        sweep_envelopes(_plan(entry), colliding=colliding),
    )
    return entry, collision, report


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("observed_route_entry_sweep_sha256")
    value["observed_route_entry_sweep_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_clear_conservative_entry_sweeps_retain_dynamics_and_release_gates():
    entry, collision, report = _qualified()
    assert parse_typing_observed_route_entry_sweep_v1(report) == report
    assert report["status"] == CLEAR_STATUS
    assert report["observed_route_entry_sha256"] == (
        entry["observed_route_entry_sha256"]
    )
    assert report["observed_route_entry_collision_sha256"] == (
        collision["observed_route_entry_collision_sha256"]
    )
    assert report["segment_count"] == report["sample_count"] - 1
    assert report["all_entry_sweeps_clear"] is True
    assert report["continuous_collision_proven"] is False
    assert report["measured_dynamics_qualified"] is False
    assert report["required_next_evidence"] == list(REQUIRED_NEXT_EVIDENCE)
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_detects_conservative_entry_sweep_collision():
    _entry_report, _collision, report = _qualified(colliding=True)
    assert report["status"] == "BLOCKED_ENTRY_CONSERVATIVE_SWEEP_COLLISION"
    assert report["all_entry_sweeps_clear"] is False
    assert report["continuous_collision_proven"] is False
    assert parse_typing_observed_route_entry_sweep_v1(report) == report


def test_rejects_missing_crossed_and_resealed_authority_evidence():
    context, measured, installed, entry, configuration = _inputs()
    collision = qualify_typing_observed_route_entry_collision_v1(
        entry, context, measured, installed, bindings(), configuration
    )
    envelopes = list(sweep_envelopes(_plan(entry)))
    with pytest.raises(TypingObservedRouteEntrySweepV1Error, match="exactly one"):
        qualify_typing_observed_route_entry_sweep_v1(
            entry, collision, context, installed, bindings(), envelopes[:-1]
        )
    body_id = next(iter(envelopes[0]))
    crossed = copy.deepcopy(envelopes)
    crossed[0][body_id] = type(crossed[0][body_id])(
        0,
        "f" * 64,
        crossed[0][body_id].end_sample_sha256,
        body_id,
        crossed[0][body_id].geometry_root_frame,
        crossed[0][body_id].source_sha256,
    )
    with pytest.raises(TypingObservedRouteEntrySweepV1Error, match="bind"):
        qualify_typing_observed_route_entry_sweep_v1(
            entry, collision, context, installed, bindings(), crossed
        )

    _entry_report, _collision, report = _qualified()
    changed = copy.deepcopy(report)
    changed["eligible_for_executor"] = True
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntrySweepV1Error, match="authority"):
        parse_typing_observed_route_entry_sweep_v1(changed)
