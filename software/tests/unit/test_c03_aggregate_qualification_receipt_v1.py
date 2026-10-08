from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.c03_aggregate_qualification_receipt_v1 import (
    BLOCKED,
    REJECT,
    C03AggregateQualificationReceiptV1Error,
    build_c03_aggregate_qualification_receipt_v1,
    parse_c03_aggregate_qualification_receipt_v1,
)
from rocell.application.c03_observed_route_entry_qualification_v1 import (
    COLLISION_STATUS,
)
from rocell.application.c03_partition_collision_evaluator_v1 import (
    CONTINUOUS_CLEAR_STATUS,
    CONTINUOUS_COLLISION_STATUS,
    CONTINUOUS_SCHEMA,
)
from rocell.application.c03_route_collision_handoff_v1 import (
    prepare_c03_route_collision_handoff_v1,
)
from rocell.application.context import load_simulation_context
from rocell.application.c03_cable_envelope_intake_v1 import (
    READY_STATUS as CABLE_READY,
    REPORT_SCHEMA as CABLE_SCHEMA,
)

from test_c03_observed_route_entry_qualification_v1 import _inputs, _qualify


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rehash(document, field):
    unsigned = {key: value for key, value in document.items() if key != field}
    document[field] = _sha(unsigned)


def _bundle(context, monkeypatch, *, colliding=False, stale=False):
    route, _observed, _measured, installed, policy, _configuration, _sweeps = _inputs(
        context, monkeypatch, colliding=colliding, stale=stale
    )
    entry = _qualify(context, monkeypatch, colliding=colliding, stale=stale)
    handoff = prepare_c03_route_collision_handoff_v1(
        route, context, installed_profile=installed, sampling_policy=policy
    )
    intake = handoff["collision_intake"]
    boundaries = [
        {
            "predecessor_partition_index": row["predecessor_partition_index"],
            "successor_partition_index": row["successor_partition_index"],
            "sample_sha256": row["predecessor_terminal_sample_sha256"],
            "inflated_geometry_sha256": str(index + 1) * 64,
            "exact_match": True,
        }
        for index, row in enumerate(intake["boundary_lineage"])
    ]
    cable = {
        "schema": CABLE_SCHEMA,
        "status": CABLE_READY,
        "partitioned_typing_collision_intake_sha256": intake[
            "partitioned_typing_collision_intake_sha256"
        ],
        "installed_collision_profile_content_sha256": intake[
            "installed_collision_profile_sha256"
        ],
        "collision_contract_sha256": intake["collision_contract_sha256"],
        "partition_count": len(intake["partitions"]),
        "owned_segment_count": sum(
            len(item["bounded_joint_sample_plan"]) - 1
            for item in intake["partitions"]
        ),
        "boundary_recheck_count": len(boundaries),
        "boundary_rechecks": boundaries,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    _rehash(cable, "c03_cable_envelope_intake_report_sha256")
    segments = []
    owned = 0
    for partition in intake["partitions"]:
        plan = partition["bounded_joint_sample_plan"]
        for segment_index, (start, end) in enumerate(zip(plan, plan[1:])):
            segments.append({
                "owned_segment_sequence": owned,
                "partition_index": partition["partition_index"],
                "segment_sequence": segment_index,
                "start_sample_sha256": _sha(start),
                "end_sample_sha256": _sha(end),
                "minimum_clearance_lower_bound_mm": 5.0 + owned,
                "limiting_body_pair": ["tool", "station"],
                "collision_free_diagnostic": True,
                "collisions": [],
            })
            owned += 1
    continuous = {
        "schema": CONTINUOUS_SCHEMA,
        "status": CONTINUOUS_CLEAR_STATUS,
        "continuous_method": {"method_id": "test", "content_sha256": "a" * 64},
        "c03_cable_envelope_intake_report_sha256": cable[
            "c03_cable_envelope_intake_report_sha256"
        ],
        "partition_collision_evaluation_sha256_values": [
            str(index + 2) * 64 for index in range(len(intake["partitions"]))
        ],
        "partition_count": len(intake["partitions"]),
        "owned_segment_count": len(segments),
        "segment_reports": segments,
        "all_owned_segments_assigned_exactly_once": True,
        "cross_partition_boundary_rechecks_reproduced": True,
        "continuous_collision_proven_for_bound_geometry": True,
        "installed_physical_qualification_complete": False,
        "blockers": ["INSTALLED_PHYSICAL_QUALIFICATION_REQUIRED"],
        "indeterminate_reason": None,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    _rehash(continuous, "c03_continuous_segment_qualification_sha256")
    return entry, handoff, cable, continuous


def test_clear_exact_chain_without_numeric_entry_margin_is_blocked(context, monkeypatch):
    bundle = _bundle(context, monkeypatch)
    first = build_c03_aggregate_qualification_receipt_v1(*bundle)
    second = build_c03_aggregate_qualification_receipt_v1(*bundle)
    assert first == second
    assert parse_c03_aggregate_qualification_receipt_v1(first) == first
    assert first["disposition"] == BLOCKED
    assert first["entry_to_route_maximum_joint_difference_rad"] == 0.0
    assert first["all_route_segments_covered_exactly_once"] is True
    assert first["controller_commands"] == first["wire_commands"] == []
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_entry_collision_dominates_route_clear_as_reject(context, monkeypatch):
    bundle = _bundle(context, monkeypatch, colliding=True)
    assert bundle[0]["status"] == COLLISION_STATUS
    result = build_c03_aggregate_qualification_receipt_v1(*bundle)
    assert result["disposition"] == REJECT
    assert result["clearance_summary"]["minimum_clearance_lower_bound_mm"] == 0.0


def test_route_collision_dominates_stale_entry_as_reject(context, monkeypatch):
    entry, handoff, cable, continuous = _bundle(
        context, monkeypatch, stale=True
    )
    continuous["status"] = CONTINUOUS_COLLISION_STATUS
    continuous["continuous_collision_proven_for_bound_geometry"] = False
    continuous["segment_reports"][0]["collision_free_diagnostic"] = False
    continuous["segment_reports"][0]["collisions"] = [{
        "first_body_id": "tool", "second_body_id": "station",
        "first_primitive_index": 0, "second_primitive_index": 0,
    }]
    _rehash(continuous, "c03_continuous_segment_qualification_sha256")
    result = build_c03_aggregate_qualification_receipt_v1(
        entry, handoff, cable, continuous
    )
    assert result["disposition"] == REJECT
    assert result["observation_fresh_at_evaluation"] is False


def test_stale_entry_with_clear_route_is_blocked(context, monkeypatch):
    result = build_c03_aggregate_qualification_receipt_v1(
        *_bundle(context, monkeypatch, stale=True)
    )
    assert result["disposition"] == BLOCKED


@pytest.mark.parametrize("mutation", ["entry_hash", "profile", "segment_order", "authority"])
def test_crossed_tampered_or_authority_evidence_fails_closed(
    context, monkeypatch, mutation
):
    entry, handoff, cable, continuous = copy.deepcopy(
        _bundle(context, monkeypatch)
    )
    if mutation == "entry_hash":
        entry["reason"] += " changed"
    elif mutation == "profile":
        cable["installed_collision_profile_content_sha256"] = "f" * 64
        _rehash(cable, "c03_cable_envelope_intake_report_sha256")
        continuous["c03_cable_envelope_intake_report_sha256"] = cable[
            "c03_cable_envelope_intake_report_sha256"
        ]
        _rehash(continuous, "c03_continuous_segment_qualification_sha256")
    elif mutation == "segment_order":
        continuous["segment_reports"][0], continuous["segment_reports"][1] = (
            continuous["segment_reports"][1], continuous["segment_reports"][0]
        )
        _rehash(continuous, "c03_continuous_segment_qualification_sha256")
    else:
        continuous["physical_authority"] = True
        _rehash(continuous, "c03_continuous_segment_qualification_sha256")
    with pytest.raises(C03AggregateQualificationReceiptV1Error):
        build_c03_aggregate_qualification_receipt_v1(
            entry, handoff, cable, continuous
        )


def test_missing_and_duplicate_segment_coverage_fails_closed(context, monkeypatch):
    for mode in ("missing", "duplicate"):
        entry, handoff, cable, continuous = copy.deepcopy(
            _bundle(context, monkeypatch)
        )
        if mode == "missing":
            continuous["segment_reports"].pop()
        else:
            continuous["segment_reports"].append(
                copy.deepcopy(continuous["segment_reports"][-1])
            )
        continuous["owned_segment_count"] = len(continuous["segment_reports"])
        _rehash(continuous, "c03_continuous_segment_qualification_sha256")
        with pytest.raises(
            C03AggregateQualificationReceiptV1Error, match="coverage"
        ):
            build_c03_aggregate_qualification_receipt_v1(
                entry, handoff, cable, continuous
            )
