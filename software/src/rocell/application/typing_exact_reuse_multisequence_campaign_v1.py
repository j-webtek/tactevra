"""Strict five-sequence qualification of exact-input IK substitution."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.typing_exact_reuse_multisequence_campaign.v1"
CASES = (
    "HOME_TRANSITION", "WORD_ROBOT", "REPEAT_NUMBER_PUNCTUATION",
    "ALPHABETIC_EXTREMES", "NUMBER_SPACE_ENTER",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_COUNTERS = ("lookups", "hits", "misses", "stores", "capacity_skips")
_FIELDS = {
    "schema", "campaign_id", "evidence_class", "environment", "case_count",
    "cases", "all_receipts_identical", "all_stage_hashes_identical",
    "total_samples", "total_cold_hits", "total_warm_hits",
    "endpoint_only_substitution_authorized", "exact_input_substitution_mode",
    "complete_solve_fallback_required", "timing_used_for_admission",
    "performance_authority", "controller_opened", "transport_opened",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "campaign_sha256",
}
_CASE_FIELDS = {
    "case", "target_ids", "status", "sample_count", "reference_duration_ns",
    "cold_duration_ns", "warm_duration_ns", "reference_receipt_sha256",
    "cold_receipt_sha256", "warm_receipt_sha256", "reference_stage_sha256",
    "cold_stage_sha256", "warm_stage_sha256", "cold_counters", "warm_counters",
}


class TypingExactReuseMultisequenceCampaignV1Error(ValueError):
    """Exact-input substitution evidence is incomplete or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingExactReuseMultisequenceCampaignV1Error(f"{label} differs")
    return value


def _counters(value: object, *, warm: bool, sample_count: int) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(_COUNTERS):
        raise TypingExactReuseMultisequenceCampaignV1Error("cache counters differ")
    result = {}
    for field in _COUNTERS:
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingExactReuseMultisequenceCampaignV1Error("cache counters differ")
        result[field] = item
    if result["lookups"] != sample_count or result["hits"] + result["misses"] != sample_count:
        raise TypingExactReuseMultisequenceCampaignV1Error("cache lookup derivation differs")
    if warm:
        if result != {"lookups": sample_count, "hits": sample_count, "misses": 0,
                      "stores": 0, "capacity_skips": 0}:
            raise TypingExactReuseMultisequenceCampaignV1Error("warm substitution differs")
    elif (result["misses"] < 1 or result["stores"] != result["misses"]
          or result["capacity_skips"] != 0):
        raise TypingExactReuseMultisequenceCampaignV1Error("cold fallback differs")
    return result


def build_typing_exact_reuse_multisequence_campaign_v1(
    cases: Sequence[Mapping[str, Any]], *, campaign_id: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    if len(cases) != len(CASES):
        raise TypingExactReuseMultisequenceCampaignV1Error("case count differs")
    normalized = []
    for index, item in enumerate(cases):
        if not isinstance(item, Mapping) or set(item) != _CASE_FIELDS:
            raise TypingExactReuseMultisequenceCampaignV1Error("case fields differ")
        if item.get("case") != CASES[index] or item.get("status") != "PASS":
            raise TypingExactReuseMultisequenceCampaignV1Error("case order or status differs")
        targets = item.get("target_ids")
        count = item.get("sample_count")
        if (not isinstance(targets, list) or not targets
                or any(not isinstance(v, str) or not v for v in targets)
                or isinstance(count, bool) or not isinstance(count, int) or count < 1):
            raise TypingExactReuseMultisequenceCampaignV1Error("case identity differs")
        durations = {}
        for field in ("reference_duration_ns", "cold_duration_ns", "warm_duration_ns"):
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypingExactReuseMultisequenceCampaignV1Error("duration differs")
            durations[field] = value
        receipts = [_digest(item.get(field), field) for field in (
            "reference_receipt_sha256", "cold_receipt_sha256", "warm_receipt_sha256")]
        stages = [_digest(item.get(field), field) for field in (
            "reference_stage_sha256", "cold_stage_sha256", "warm_stage_sha256")]
        if len(set(receipts)) != 1 or len(set(stages)) != 1:
            raise TypingExactReuseMultisequenceCampaignV1Error("substitution changed decisions")
        cold = _counters(item.get("cold_counters"), warm=False, sample_count=count)
        warm = _counters(item.get("warm_counters"), warm=True, sample_count=count)
        normalized.append({"case": CASES[index], "target_ids": list(targets),
            "status": "PASS", "sample_count": count, **durations,
            "reference_receipt_sha256": receipts[0], "cold_receipt_sha256": receipts[1],
            "warm_receipt_sha256": receipts[2], "reference_stage_sha256": stages[0],
            "cold_stage_sha256": stages[1], "warm_stage_sha256": stages[2],
            "cold_counters": cold, "warm_counters": warm})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "case_count": len(normalized), "cases": normalized,
        "all_receipts_identical": True, "all_stage_hashes_identical": True,
        "total_samples": sum(item["sample_count"] for item in normalized),
        "total_cold_hits": sum(item["cold_counters"]["hits"] for item in normalized),
        "total_warm_hits": sum(item["warm_counters"]["hits"] for item in normalized),
        "endpoint_only_substitution_authorized": False,
        "exact_input_substitution_mode": "EXPERIMENTAL_SHADOW_ONLY",
        "complete_solve_fallback_required": True,
        "timing_used_for_admission": False, "performance_authority": False,
        "controller_opened": False, "transport_opened": False,
        "controller_commands": [], "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_exact_reuse_multisequence_campaign_v1(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingExactReuseMultisequenceCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingExactReuseMultisequenceCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_exact_reuse_multisequence_campaign_v1(
        value.get("cases"), campaign_id=value.get("campaign_id"),
        environment=value.get("environment"))
    if rebuilt != dict(value):
        raise TypingExactReuseMultisequenceCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "SCHEMA", "TypingExactReuseMultisequenceCampaignV1Error",
           "build_typing_exact_reuse_multisequence_campaign_v1",
           "parse_typing_exact_reuse_multisequence_campaign_v1"]
