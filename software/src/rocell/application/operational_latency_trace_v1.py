"""Strict, decision-neutral end-to-end operational latency trace contract."""

from __future__ import annotations

import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA = "rocell.operational_latency_trace.v1"
MILESTONES = (
    "T0_REQUEST_RECEIVED",
    "T1_INTENT_SEALED",
    "T2_PERCEPTION_SEALED",
    "T3_BATCH_EMITTED",
    "T4_BATCH_ADMITTED",
    "T5_FIRST_PLAN_READY",
    "T6_FIRST_PERMIT_GRANTED",
    "T7_FIRST_WRITE",
    "T8_FIRST_SETTLED",
    "T9_FIRST_EFFECT_VERIFIED",
    "T10_REQUEST_COMPLETE",
)
OUTCOMES = {"COMPLETE", "BLOCKED", "FAILED", "OUTCOME_UNCERTAIN"}
RUN_CLASSES = {"COLD", "WARM"}
CACHE_OUTCOMES = {"HIT", "MISS", "DISCARDED", "NOT_APPLICABLE"}
EVIDENCE_CLASSES = {
    "SYNTHETIC_TIMING_FIXTURE",
    "HOST_MEASURED_OFFLINE",
    "CONTROLLER_REPORTED",
    "EXTERNALLY_MEASURED",
    "INDEPENDENTLY_VERIFIED",
}
MAX_COUNTER = 1_000_000
MAX_ACTIONS = 64
_HASH = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_TRACE_FIELDS = {
    "schema", "trace_id", "evidence_class", "run_class", "cache_outcome",
    "outcome", "terminal_milestone", "action_count", "blocker_codes",
    "milestone_catalog", "milestones", "durations_ns", "correlation",
    "resource_counts", "decision_sha256_before", "decision_sha256_after",
    "decision_hashes_unchanged", "timing_used_for_admission",
    "performance_authority", "physical_authority_conferred", "trace_sha256",
}
_MILESTONE_FIELDS = {"milestone_id", "monotonic_ns"}
_CORRELATION_FIELDS = {
    "request_sha256", "session_sha256", "ai_batch_sha256", "plan_sha256",
    "configuration_epoch_sha256", "controller_session_sha256", "result_sha256",
}
_RESOURCE_FIELDS = {
    "artifact_bytes", "ik_solve_count", "screening_sample_count",
    "controller_command_count", "hardware_write_count", "physical_movement_count",
}
_DURATION_PAIRS = {
    "request_to_intent_ns": ("T0_REQUEST_RECEIVED", "T1_INTENT_SEALED"),
    "request_to_batch_ns": ("T0_REQUEST_RECEIVED", "T3_BATCH_EMITTED"),
    "batch_to_admission_ns": ("T3_BATCH_EMITTED", "T4_BATCH_ADMITTED"),
    "admission_to_first_plan_ns": ("T4_BATCH_ADMITTED", "T5_FIRST_PLAN_READY"),
    "software_decision_latency_ns": ("T3_BATCH_EMITTED", "T6_FIRST_PERMIT_GRANTED"),
    "plan_to_permit_ns": ("T5_FIRST_PLAN_READY", "T6_FIRST_PERMIT_GRANTED"),
    "permit_to_first_write_ns": ("T6_FIRST_PERMIT_GRANTED", "T7_FIRST_WRITE"),
    "first_write_to_settled_ns": ("T7_FIRST_WRITE", "T8_FIRST_SETTLED"),
    "settled_to_effect_verified_ns": ("T8_FIRST_SETTLED", "T9_FIRST_EFFECT_VERIFIED"),
    "first_action_latency_ns": ("T0_REQUEST_RECEIVED", "T9_FIRST_EFFECT_VERIFIED"),
    "total_request_latency_ns": ("T0_REQUEST_RECEIVED", "T10_REQUEST_COMPLETE"),
}
_DURATION_FIELDS = set(_DURATION_PAIRS)


class OperationalLatencyTraceV1Error(ValueError):
    """A trace is ambiguous, mutable, or capable of influencing authority."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise OperationalLatencyTraceV1Error(f"{label} is not a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:@/-"
               for character in value)
        or ":\\" in value or "://" in value or value.startswith(("/", "\\"))
        or (len(value) >= 3 and value[0].isalpha() and value[1] == ":"
            and value[2] in "\\/")
    ):
        raise OperationalLatencyTraceV1Error(f"{label} is invalid or path-like")
    return value


def _integer(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise OperationalLatencyTraceV1Error(f"{label} is outside its bound")
    return value


def _normalize_blockers(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 64 or len(value) != len(set(value)):
        raise OperationalLatencyTraceV1Error("blocker codes differ")
    for blocker in value:
        if not isinstance(blocker, str) or _CODE.fullmatch(blocker) is None:
            raise OperationalLatencyTraceV1Error("blocker code is not stable")
    return list(value)


def _normalize_milestones(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise OperationalLatencyTraceV1Error("milestones are not a sequence")
    if not 1 <= len(value) <= len(MILESTONES):
        raise OperationalLatencyTraceV1Error("milestone count is outside its bound")
    normalized: list[dict[str, Any]] = []
    previous = -1
    for index, sample in enumerate(value):
        if not isinstance(sample, Mapping) or set(sample) != _MILESTONE_FIELDS:
            raise OperationalLatencyTraceV1Error(f"milestone {index} fields differ")
        if sample.get("milestone_id") != MILESTONES[index]:
            raise OperationalLatencyTraceV1Error("milestones are not the exact catalog prefix")
        timestamp = _integer(sample.get("monotonic_ns"), "monotonic time", 2**63 - 1)
        if timestamp < previous:
            raise OperationalLatencyTraceV1Error("milestone time moved backwards")
        previous = timestamp
        normalized.append({"milestone_id": MILESTONES[index], "monotonic_ns": timestamp})
    return normalized


def _durations(milestones: Sequence[Mapping[str, Any]]) -> dict[str, int | None]:
    times = {sample["milestone_id"]: sample["monotonic_ns"] for sample in milestones}
    return {
        name: times[end] - times[start] if start in times and end in times else None
        for name, (start, end) in _DURATION_PAIRS.items()
    }


def build_operational_latency_trace_v1(
    milestones: Sequence[Mapping[str, Any]], *, trace_id: str,
    evidence_class: str, run_class: str, cache_outcome: str, outcome: str,
    action_count: int, blocker_codes: Sequence[str],
    correlation: Mapping[str, Any], resource_counts: Mapping[str, Any],
    decision_sha256: str,
) -> dict[str, Any]:
    """Build an immutable trace whose timing cannot grant or alter authority."""

    normalized_milestones = _normalize_milestones(milestones)
    if evidence_class not in EVIDENCE_CLASSES:
        raise OperationalLatencyTraceV1Error("evidence class differs")
    if run_class not in RUN_CLASSES or cache_outcome not in CACHE_OUTCOMES:
        raise OperationalLatencyTraceV1Error("run or cache class differs")
    if outcome not in OUTCOMES:
        raise OperationalLatencyTraceV1Error("outcome differs")
    blockers = _normalize_blockers(list(blocker_codes))
    terminal = normalized_milestones[-1]["milestone_id"]
    if outcome == "COMPLETE":
        if terminal != MILESTONES[-1] or blockers:
            raise OperationalLatencyTraceV1Error("complete outcome contradicts terminal state")
    elif not blockers:
        raise OperationalLatencyTraceV1Error("non-complete outcome requires a blocker")
    if not isinstance(correlation, Mapping) or set(correlation) != _CORRELATION_FIELDS:
        raise OperationalLatencyTraceV1Error("correlation fields differ")
    normalized_correlation = {
        "request_sha256": _digest(correlation.get("request_sha256"), "request"),
        "session_sha256": _digest(correlation.get("session_sha256"), "session"),
        **{
            field: _digest(correlation.get(field), field, nullable=True)
            for field in sorted(_CORRELATION_FIELDS - {"request_sha256", "session_sha256"})
        },
    }
    if not isinstance(resource_counts, Mapping) or set(resource_counts) != _RESOURCE_FIELDS:
        raise OperationalLatencyTraceV1Error("resource count fields differ")
    normalized_resources = {
        field: _integer(resource_counts.get(field), field, MAX_COUNTER)
        for field in sorted(_RESOURCE_FIELDS)
    }
    decision = _digest(decision_sha256, "decision")
    core = {
        "schema": SCHEMA,
        "trace_id": _identifier(trace_id, "trace_id"),
        "evidence_class": evidence_class,
        "run_class": run_class,
        "cache_outcome": cache_outcome,
        "outcome": outcome,
        "terminal_milestone": terminal,
        "action_count": _integer(action_count, "action count", MAX_ACTIONS),
        "blocker_codes": blockers,
        "milestone_catalog": list(MILESTONES),
        "milestones": normalized_milestones,
        "durations_ns": _durations(normalized_milestones),
        "correlation": normalized_correlation,
        "resource_counts": normalized_resources,
        "decision_sha256_before": decision,
        "decision_sha256_after": decision,
        "decision_hashes_unchanged": True,
        "timing_used_for_admission": False,
        "performance_authority": False,
        "physical_authority_conferred": False,
    }
    return {**core, "trace_sha256": _sha(core)}


def parse_operational_latency_trace_v1(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate and rebuild every derived or fixed field in a trace."""

    if not isinstance(value, Mapping) or set(value) != _TRACE_FIELDS:
        raise OperationalLatencyTraceV1Error("trace fields differ")
    unsigned = dict(value)
    supplied_hash = unsigned.pop("trace_sha256")
    if not isinstance(supplied_hash, str) or _sha(unsigned) != supplied_hash:
        raise OperationalLatencyTraceV1Error("trace hash mismatch")
    durations = value.get("durations_ns")
    if not isinstance(durations, Mapping) or set(durations) != _DURATION_FIELDS:
        raise OperationalLatencyTraceV1Error("duration fields differ")
    milestones = value.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise OperationalLatencyTraceV1Error("milestones differ")
    last_milestone = milestones[-1]
    if not isinstance(last_milestone, Mapping):
        raise OperationalLatencyTraceV1Error("milestones differ")
    if value.get("terminal_milestone") != last_milestone.get("milestone_id"):
        raise OperationalLatencyTraceV1Error("terminal milestone differs")
    if value.get("decision_sha256_before") != value.get("decision_sha256_after"):
        raise OperationalLatencyTraceV1Error("instrumentation changed the decision")
    rebuilt = build_operational_latency_trace_v1(
        milestones, trace_id=value.get("trace_id"),
        evidence_class=value.get("evidence_class"), run_class=value.get("run_class"),
        cache_outcome=value.get("cache_outcome"), outcome=value.get("outcome"),
        action_count=value.get("action_count"), blocker_codes=value.get("blocker_codes"),
        correlation=value.get("correlation"), resource_counts=value.get("resource_counts"),
        decision_sha256=value.get("decision_sha256_before"),
    )
    if rebuilt != dict(value):
        raise OperationalLatencyTraceV1Error("trace derivation or authority fields differ")
    return MappingProxyType(dict(value))


__all__ = [
    "CACHE_OUTCOMES", "EVIDENCE_CLASSES", "MILESTONES", "OUTCOMES", "RUN_CLASSES",
    "SCHEMA", "OperationalLatencyTraceV1Error",
    "build_operational_latency_trace_v1", "parse_operational_latency_trace_v1",
]
