from __future__ import annotations

import copy
import hashlib
import json
import pytest

from rocell.application.bounded_segment_collision_qualification import (
    MeasuredSegmentConfigurationSample,
)
from rocell.application.typing_observed_route_entry_v1 import (
    build_typing_observed_route_entry_v1,
)
from rocell.application.typing_observed_route_entry_collision_v1 import (
    CLEAR_STATUS,
    REQUIRED_NEXT_EVIDENCE,
    TypingObservedRouteEntryCollisionV1Error,
    parse_typing_observed_route_entry_collision_v1,
    qualify_typing_observed_route_entry_collision_v1,
)

from test_fk_collision_pose_adapter import bindings, cable, profile
from test_typing_observed_trajectory_ik_v1 import _screened


def _reseal(value):
    unsigned = dict(value)
    unsigned.pop("observed_route_entry_collision_sha256")
    value["observed_route_entry_collision_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def _inputs():
    _materialization, seed, context, measured, observed_ik = _screened()
    entry = build_typing_observed_route_entry_v1(observed_ik, seed)
    installed = profile(context)
    configuration = tuple(
        MeasuredSegmentConfigurationSample(
            sample["sample_sequence"], sample["sample_sha256"], cable()[0]
        )
        for sample in entry["sample_plan"]
    )
    return context, measured, installed, entry, configuration


def _qualified():
    context, measured, installed, entry, configuration = _inputs()
    report = qualify_typing_observed_route_entry_collision_v1(
        entry,
        context,
        measured,
        installed,
        bindings(),
        configuration,
    )
    return entry, report


def test_screens_every_entry_sample_and_retains_continuous_and_dynamics_gates():
    entry, report = _qualified()
    assert parse_typing_observed_route_entry_collision_v1(report) == report
    assert report["status"] == CLEAR_STATUS
    assert report["sample_count"] == entry["sample_count"]
    assert report["all_entry_samples_collision_free"] is True
    assert report["continuous_collision_proven"] is False
    assert report["measured_dynamics_qualified"] is False
    assert report["required_next_evidence"] == list(REQUIRED_NEXT_EVIDENCE)
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_rejects_missing_or_crossed_configuration_sample():
    context, measured, installed, entry, configuration = _inputs()
    with pytest.raises(TypingObservedRouteEntryCollisionV1Error, match="cover"):
        qualify_typing_observed_route_entry_collision_v1(
            entry, context, measured, installed, bindings(),
            configuration[:-1],
        )
    crossed = list(configuration)
    crossed[0] = MeasuredSegmentConfigurationSample(
        0, "f" * 64, cable()[0]
    )
    with pytest.raises(TypingObservedRouteEntryCollisionV1Error, match="bind"):
        qualify_typing_observed_route_entry_collision_v1(
            entry, context, measured, installed, bindings(), crossed,
        )


def test_rejects_resealed_nested_result_and_authority_tamper():
    _entry_report, report = _qualified()
    changed = copy.deepcopy(report)
    changed["fk_collision_qualification"]["hardware_access"] = True
    nested = dict(changed["fk_collision_qualification"])
    nested.pop("fk_collision_sequence_sha256")
    changed["fk_collision_qualification"]["fk_collision_sequence_sha256"] = (
        hashlib.sha256(json.dumps(
            nested, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode()).hexdigest()
    )
    changed["fk_collision_sequence_sha256"] = changed[
        "fk_collision_qualification"
    ]["fk_collision_sequence_sha256"]
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryCollisionV1Error, match="authority"):
        parse_typing_observed_route_entry_collision_v1(changed)

    changed = copy.deepcopy(report)
    changed["eligible_for_executor"] = True
    _reseal(changed)
    with pytest.raises(TypingObservedRouteEntryCollisionV1Error, match="authority"):
        parse_typing_observed_route_entry_collision_v1(changed)
