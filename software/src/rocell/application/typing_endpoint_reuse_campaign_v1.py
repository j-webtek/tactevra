"""Strict retained qualification for decision-neutral endpoint reuse."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1
from .typing_endpoint_reuse_verifier_v1 import (
    TypingEndpointReuseVerifierV1Error,
    parse_typing_endpoint_reuse_verifier_snapshot_v1,
)


SCHEMA = "rocell.typing_endpoint_reuse_campaign.v1"
ROUTE_CASES = (
    "HOME_TRANSITION", "WORD_ROBOT", "REPEAT_NUMBER_PUNCTUATION",
    "ALPHABETIC_EXTREMES", "NUMBER_SPACE_ENTER",
)
FAULT_CASES = (
    "CAPACITY_BOUNDED", "SAMPLE_BOUND_REJECTED", "INVALIDATED_REJECTED",
    "CORRUPTION_REJECTED", "CONFLICT_REJECTED",
    "DECISION_CONTEXT_REJECTED", "RELOAD_STALE_REJECTED",
    "RESTART_STALE_REJECTED", "CROSSED_CONTEXT_REJECTED",
    "UNMANAGED_REJECTED",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema", "campaign_id", "evidence_class", "environment",
    "route_case_count", "route_cases", "final_verifier_snapshot",
    "fault_case_count", "fault_cases", "all_expected_outcomes",
    "decision_hashes_unchanged", "candidate_used_for_decision",
    "diagnostics_used_for_admission", "warm_start_authorized",
    "performance_authority", "controller_opened", "transport_opened",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "campaign_sha256",
}
_ROUTE_FIELDS = {
    "case", "target_ids", "status", "reference_receipt_sha256",
    "observed_receipt_sha256", "receipt_matches_reference",
    "after_verifier_snapshot",
}
_FAULT_FIELDS = {
    "case", "status", "outcome", "canonical_receipt_preserved",
}


class TypingEndpointReuseCampaignV1Error(ValueError):
    """Campaign evidence is incomplete, inconsistent, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingEndpointReuseCampaignV1Error(f"{label} is not a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 192
            or value != value.strip() or ":\\" in value or "://" in value
            or value.startswith(("/", "\\"))):
        raise TypingEndpointReuseCampaignV1Error(f"{label} is invalid or path-like")
    return value


def build_typing_endpoint_reuse_campaign_v1(
    route_cases: Sequence[Mapping[str, Any]],
    fault_cases: Sequence[Mapping[str, Any]], *, campaign_id: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    if len(route_cases) != len(ROUTE_CASES) or len(fault_cases) != len(FAULT_CASES):
        raise TypingEndpointReuseCampaignV1Error("campaign case count differs")
    routes = []
    for index, item in enumerate(route_cases):
        if not isinstance(item, Mapping) or set(item) != _ROUTE_FIELDS:
            raise TypingEndpointReuseCampaignV1Error("route case fields differ")
        if item.get("case") != ROUTE_CASES[index] or item.get("status") != "PASS":
            raise TypingEndpointReuseCampaignV1Error("route case order or status differs")
        targets = item.get("target_ids")
        if not isinstance(targets, list) or not targets or any(
            not isinstance(target, str) or not target for target in targets
        ):
            raise TypingEndpointReuseCampaignV1Error("route targets differ")
        reference = _digest(item.get("reference_receipt_sha256"), "reference receipt")
        observed = _digest(item.get("observed_receipt_sha256"), "observed receipt")
        if item.get("receipt_matches_reference") is not True or reference != observed:
            raise TypingEndpointReuseCampaignV1Error("route receipt differs")
        try:
            snapshot = dict(parse_typing_endpoint_reuse_verifier_snapshot_v1(
                item.get("after_verifier_snapshot")
            ))
        except TypingEndpointReuseVerifierV1Error as exc:
            raise TypingEndpointReuseCampaignV1Error(
                f"route verifier snapshot is invalid: {exc}"
            ) from exc
        routes.append({
            "case": ROUTE_CASES[index], "target_ids": list(targets),
            "status": "PASS", "reference_receipt_sha256": reference,
            "observed_receipt_sha256": observed,
            "receipt_matches_reference": True,
            "after_verifier_snapshot": snapshot,
        })
    final = dict(parse_typing_endpoint_reuse_verifier_snapshot_v1(
        routes[-1]["after_verifier_snapshot"]
    ))
    expected = {
        "observed_sample_count": 186, "endpoint_observation_count": 58,
        "entry_count": 40, "stores": 40, "hits": 18,
        "canonical_matches": 18, "canonical_conflicts": 0,
    }
    if any(final[field] != value for field, value in expected.items()):
        raise TypingEndpointReuseCampaignV1Error("final verifier totals differ")
    faults = []
    for index, item in enumerate(fault_cases):
        if not isinstance(item, Mapping) or set(item) != _FAULT_FIELDS:
            raise TypingEndpointReuseCampaignV1Error("fault case fields differ")
        case = FAULT_CASES[index]
        outcome = "BOUNDED" if case == "CAPACITY_BOUNDED" else "REJECTED"
        preserved = True if case == "CAPACITY_BOUNDED" else None
        if (item.get("case") != case or item.get("status") != "PASS"
                or item.get("outcome") != outcome
                or item.get("canonical_receipt_preserved") is not preserved):
            raise TypingEndpointReuseCampaignV1Error("fault outcome differs")
        faults.append({"case": case, "status": "PASS", "outcome": outcome,
                       "canonical_receipt_preserved": preserved})
    core = {
        "schema": SCHEMA, "campaign_id": _identifier(campaign_id, "campaign_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "route_case_count": len(routes), "route_cases": routes,
        "final_verifier_snapshot": final,
        "fault_case_count": len(faults), "fault_cases": faults,
        "all_expected_outcomes": True, "decision_hashes_unchanged": True,
        "candidate_used_for_decision": False,
        "diagnostics_used_for_admission": False, "warm_start_authorized": False,
        "performance_authority": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_endpoint_reuse_campaign_v1(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise TypingEndpointReuseCampaignV1Error("campaign fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingEndpointReuseCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_endpoint_reuse_campaign_v1(
        value.get("route_cases"), value.get("fault_cases"),
        campaign_id=value.get("campaign_id"), environment=value.get("environment"),
    )
    if rebuilt != dict(value):
        raise TypingEndpointReuseCampaignV1Error("campaign derivation differs")
    return value


__all__ = [
    "FAULT_CASES", "ROUTE_CASES", "SCHEMA", "TypingEndpointReuseCampaignV1Error",
    "build_typing_endpoint_reuse_campaign_v1", "parse_typing_endpoint_reuse_campaign_v1",
]
