"""Strict retained multi-sequence typing IK effort campaign."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)
from .typing_ik_effort_telemetry_v1 import (
    TypingIkEffortTelemetryV1Error,
    parse_typing_ik_effort_telemetry_v1,
)


SCHEMA = "rocell.typing_ik_effort_campaign.v1"
MINIMUM_CASES = 5
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "campaign_id", "evidence_class", "environment", "case_count",
    "cases", "aggregate", "exact_reuse_analysis",
    "decision_hashes_unchanged", "telemetry_used_for_admission",
    "performance_authority", "controller_opened", "transport_opened",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "campaign_sha256",
}
_CASE_FIELDS = {
    "case_id", "target_ids", "receipt_sha256", "stage_hashes_sha256",
    "telemetry",
}


class TypingIkEffortCampaignV1Error(ValueError):
    """Campaign evidence is incomplete, inconsistent, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingIkEffortCampaignV1Error(f"{label} is not a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingIkEffortCampaignV1Error(f"{label} is invalid or path-like")
    return value


def build_typing_ik_effort_campaign_v1(
    cases: Sequence[Mapping[str, Any]], *, campaign_id: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise TypingIkEffortCampaignV1Error("cases are not a sequence")
    if not MINIMUM_CASES <= len(cases) <= 64:
        raise TypingIkEffortCampaignV1Error("case count is outside its bound")
    normalized = []
    case_ids = set()
    solver_inputs: list[str] = []
    for item in cases:
        if not isinstance(item, Mapping) or set(item) != _CASE_FIELDS:
            raise TypingIkEffortCampaignV1Error("case fields differ")
        case_id = _identifier(item.get("case_id"), "case_id")
        if case_id in case_ids:
            raise TypingIkEffortCampaignV1Error("case IDs must be unique")
        case_ids.add(case_id)
        target_ids = item.get("target_ids")
        if (
            not isinstance(target_ids, list)
            or not 1 <= len(target_ids) <= 64
            or any(
                not isinstance(target, str) or not target or len(target) > 128
                or target != target.strip()
                for target in target_ids
            )
        ):
            raise TypingIkEffortCampaignV1Error("target IDs are invalid")
        try:
            telemetry = dict(parse_typing_ik_effort_telemetry_v1(
                item.get("telemetry")
            ))
        except TypingIkEffortTelemetryV1Error as exc:
            raise TypingIkEffortCampaignV1Error(
                f"case telemetry is invalid: {exc}"
            ) from exc
        if telemetry["sample_count"] < len(target_ids):
            raise TypingIkEffortCampaignV1Error(
                "telemetry cannot contain fewer samples than targets"
            )
        solver_inputs.extend(
            sample["solver_input_sha256"] for sample in telemetry["samples"]
        )
        normalized.append({
            "case_id": case_id,
            "target_ids": list(target_ids),
            "receipt_sha256": _digest(
                item.get("receipt_sha256"), "receipt"
            ),
            "stage_hashes_sha256": _digest(
                item.get("stage_hashes_sha256"), "stage hashes"
            ),
            "telemetry": telemetry,
        })
    counters = Counter(solver_inputs)
    aggregate = {
        "waypoint_count": sum(
            case["telemetry"]["sample_count"] for case in normalized
        ),
        "attempt_count": sum(
            case["telemetry"]["totals"]["attempt_count"] for case in normalized
        ),
        "total_iterations": sum(
            case["telemetry"]["totals"]["total_iterations"] for case in normalized
        ),
        "selected_iterations": sum(
            case["telemetry"]["totals"]["selected_iterations"]
            for case in normalized
        ),
        "converged_attempt_count": sum(
            case["telemetry"]["totals"]["converged_attempt_count"]
            for case in normalized
        ),
        "first_attempt_converged_count": sum(
            case["telemetry"]["totals"]["first_attempt_converged_count"]
            for case in normalized
        ),
        "selected_first_attempt_count": sum(
            case["telemetry"]["totals"]["selected_first_attempt_count"]
            for case in normalized
        ),
    }
    reuse = {
        "solver_input_observation_count": len(solver_inputs),
        "unique_solver_input_count": len(counters),
        "repeated_observation_count": len(solver_inputs) - len(counters),
        "reused_identity_count": sum(1 for count in counters.values() if count > 1),
        "maximum_identity_occurrences": max(counters.values(), default=0),
        "first_convergence_early_exit_equivalent": (
            aggregate["selected_first_attempt_count"]
            == aggregate["waypoint_count"]
        ),
        "cache_authorized": False,
    }
    core = {
        "schema": SCHEMA,
        "campaign_id": _identifier(campaign_id, "campaign_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "case_count": len(normalized),
        "cases": normalized,
        "aggregate": aggregate,
        "exact_reuse_analysis": reuse,
        "decision_hashes_unchanged": True,
        "telemetry_used_for_admission": False,
        "performance_authority": False,
        "controller_opened": False,
        "transport_opened": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_ik_effort_campaign_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingIkEffortCampaignV1Error("campaign fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingIkEffortCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_ik_effort_campaign_v1(
        value.get("cases"), campaign_id=value.get("campaign_id"),
        environment=value.get("environment"),
    )
    if rebuilt != dict(value):
        raise TypingIkEffortCampaignV1Error(
            "campaign derivation or authority fields differ"
        )
    return value


__all__ = [
    "MINIMUM_CASES", "SCHEMA", "TypingIkEffortCampaignV1Error",
    "build_typing_ik_effort_campaign_v1",
    "parse_typing_ik_effort_campaign_v1",
]
