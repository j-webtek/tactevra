from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from rocell.application.operational_latency_trace_v1 import (
    MILESTONES,
    OperationalLatencyTraceV1Error,
    build_operational_latency_trace_v1,
    parse_operational_latency_trace_v1,
)


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/operational_latency_trace_v1.schema.json"
).read_text(encoding="utf-8")))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _milestones(count: int = len(MILESTONES)) -> list[dict]:
    return [
        {"milestone_id": milestone, "monotonic_ns": 1_000_000 + index * 100_000}
        for index, milestone in enumerate(MILESTONES[:count])
    ]


def _correlation() -> dict:
    return {
        "request_sha256": _digest("request"),
        "session_sha256": _digest("session"),
        "ai_batch_sha256": _digest("batch"),
        "plan_sha256": _digest("plan"),
        "configuration_epoch_sha256": _digest("epoch"),
        "controller_session_sha256": _digest("controller"),
        "result_sha256": _digest("result"),
    }


def _resources() -> dict:
    return {
        "artifact_bytes": 4096,
        "ik_solve_count": 4,
        "screening_sample_count": 32,
        "controller_command_count": 4,
        "hardware_write_count": 4,
        "physical_movement_count": 4,
    }


def _build(**changes) -> dict:
    values = {
        "milestones": _milestones(),
        "trace_id": "latency-fixture-001",
        "evidence_class": "SYNTHETIC_TIMING_FIXTURE",
        "run_class": "WARM",
        "cache_outcome": "HIT",
        "outcome": "COMPLETE",
        "action_count": 4,
        "blocker_codes": [],
        "correlation": _correlation(),
        "resource_counts": _resources(),
        "decision_sha256": _digest("admission-decision"),
    }
    values.update(changes)
    return build_operational_latency_trace_v1(**values)


def _rehash(trace: dict) -> None:
    unsigned = {key: value for key, value in trace.items() if key != "trace_sha256"}
    trace["trace_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_complete_trace_is_schema_valid_derived_and_decision_neutral():
    trace = _build()
    assert list(SCHEMA.iter_errors(trace)) == []
    assert dict(parse_operational_latency_trace_v1(trace)) == trace
    assert trace["terminal_milestone"] == "T10_REQUEST_COMPLETE"
    assert trace["durations_ns"]["request_to_intent_ns"] == 100_000
    assert trace["durations_ns"]["software_decision_latency_ns"] == 300_000
    assert trace["durations_ns"]["first_action_latency_ns"] == 900_000
    assert trace["durations_ns"]["total_request_latency_ns"] == 1_000_000
    assert trace["decision_hashes_unchanged"] is True
    assert trace["timing_used_for_admission"] is False
    assert trace["performance_authority"] is False
    assert trace["physical_authority_conferred"] is False


def test_blocked_trace_is_exact_prefix_and_does_not_invent_future_times():
    trace = _build(
        milestones=_milestones(5), outcome="BLOCKED",
        blocker_codes=["PERCEPTION_UNCALIBRATED"], action_count=1,
    )
    assert list(SCHEMA.iter_errors(trace)) == []
    assert dict(parse_operational_latency_trace_v1(trace)) == trace
    assert trace["terminal_milestone"] == "T4_BATCH_ADMITTED"
    assert trace["durations_ns"]["batch_to_admission_ns"] == 100_000
    assert trace["durations_ns"]["admission_to_first_plan_ns"] is None
    assert trace["durations_ns"]["first_action_latency_ns"] is None
    assert trace["durations_ns"]["total_request_latency_ns"] is None


@pytest.mark.parametrize("mutation,match", (
    ("skip", "exact catalog prefix"),
    ("backwards", "moved backwards"),
    ("complete_prefix", "complete outcome contradicts"),
    ("blocked_without_reason", "requires a blocker"),
    ("path", "path-like"),
))
def test_ambiguous_or_inconsistent_input_rejects(mutation: str, match: str):
    arguments = {}
    if mutation == "skip":
        samples = _milestones()
        samples[3]["milestone_id"] = "T4_BATCH_ADMITTED"
        arguments["milestones"] = samples
    elif mutation == "backwards":
        samples = _milestones()
        samples[4]["monotonic_ns"] = samples[3]["monotonic_ns"] - 1
        arguments["milestones"] = samples
    elif mutation == "complete_prefix":
        arguments["milestones"] = _milestones(5)
    elif mutation == "blocked_without_reason":
        arguments.update(outcome="BLOCKED", milestones=_milestones(5))
    else:
        arguments["trace_id"] = "C:/private/trace"
    with pytest.raises(OperationalLatencyTraceV1Error, match=match):
        _build(**arguments)


@pytest.mark.parametrize("mutation,match", (
    ("duration", "derivation"),
    ("authority", "authority"),
    ("decision", "changed the decision"),
    ("terminal", "terminal milestone"),
))
def test_rehashed_derived_or_authority_mutations_still_reject(mutation: str, match: str):
    trace = copy.deepcopy(_build())
    if mutation == "duration":
        trace["durations_ns"]["first_action_latency_ns"] += 1
    elif mutation == "authority":
        trace["physical_authority_conferred"] = True
    elif mutation == "decision":
        trace["decision_sha256_after"] = _digest("different")
    else:
        trace["terminal_milestone"] = "T9_FIRST_EFFECT_VERIFIED"
    _rehash(trace)
    with pytest.raises(OperationalLatencyTraceV1Error, match=match):
        parse_operational_latency_trace_v1(trace)


def test_plain_hash_tampering_rejects_before_rebuild():
    trace = _build()
    trace["action_count"] = 3
    with pytest.raises(OperationalLatencyTraceV1Error, match="hash mismatch"):
        parse_operational_latency_trace_v1(trace)


@pytest.mark.parametrize("field,value,match", (
    ("milestones", [], "milestones differ"),
    ("durations_ns", None, "duration fields differ"),
))
def test_malformed_rehashed_collections_fail_closed(field: str, value, match: str):
    trace = _build()
    trace[field] = value
    _rehash(trace)
    with pytest.raises(OperationalLatencyTraceV1Error, match=match):
        parse_operational_latency_trace_v1(trace)
