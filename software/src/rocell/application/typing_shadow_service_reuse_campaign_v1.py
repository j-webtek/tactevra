"""Strict retained service-level exact-reuse and lifecycle campaign."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.typing_shadow_service_reuse_campaign.v1"
CASES = ("MIXED_FIFO_CACHE_REUSE", "CANCEL_NO_CACHE_EFFECT",
         "RELOAD_STALE_THEN_COLD", "RESTART_STALE_THEN_COLD")
COUNTERS = ("lookups", "hits", "misses", "stores", "capacity_skips")
_FIELDS = {"schema", "campaign_id", "evidence_class", "environment", "case_count",
    "cases", "request_order_preserved", "complete_solve_fallback_required",
    "automatic_retry_allowed", "endpoint_only_substitution_authorized",
    "timing_used_for_admission", "performance_authority", "controller_opened",
    "transport_opened", "controller_commands", "hardware_writes",
    "physical_movements", "physical_authority", "campaign_sha256"}
_CASE_FIELDS = {"case", "status", "request_ids", "receipt_statuses", "duration_ns",
                "owner_runs_delta", "cache_delta"}


class TypingShadowServiceReuseCampaignV1Error(ValueError):
    """Service reuse evidence is incomplete, inconsistent, or authoritative."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value): return hashlib.sha256(_canonical(value)).hexdigest()


def _counter_set(value):
    if not isinstance(value, Mapping) or set(value) != set(COUNTERS):
        raise TypingShadowServiceReuseCampaignV1Error("cache counters differ")
    result = {}
    for field in COUNTERS:
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingShadowServiceReuseCampaignV1Error("cache counters differ")
        result[field] = item
    if result["lookups"] != result["hits"] + result["misses"]:
        raise TypingShadowServiceReuseCampaignV1Error("cache derivation differs")
    return result


def build_typing_shadow_service_reuse_campaign_v1(cases: Sequence[Mapping[str, Any]],
        *, campaign_id: str, environment: Mapping[str, Any]):
    if len(cases) != len(CASES):
        raise TypingShadowServiceReuseCampaignV1Error("case count differs")
    normalized = []
    for index, item in enumerate(cases):
        if not isinstance(item, Mapping) or set(item) != _CASE_FIELDS:
            raise TypingShadowServiceReuseCampaignV1Error("case fields differ")
        case = CASES[index]
        if item.get("case") != case or item.get("status") != "PASS":
            raise TypingShadowServiceReuseCampaignV1Error("case order or status differs")
        request_ids, statuses, durations = (item.get("request_ids"),
                                            item.get("receipt_statuses"), item.get("duration_ns"))
        if (not isinstance(request_ids, list) or not request_ids
                or any(not isinstance(v, str) or not v for v in request_ids)
                or len(set(request_ids)) != len(request_ids)
                or not isinstance(statuses, list) or len(statuses) != len(request_ids)
                or not isinstance(durations, list) or len(durations) != len(request_ids)
                or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in durations)):
            raise TypingShadowServiceReuseCampaignV1Error("request evidence differs")
        runs = item.get("owner_runs_delta")
        if isinstance(runs, bool) or not isinstance(runs, int) or runs < 0:
            raise TypingShadowServiceReuseCampaignV1Error("owner runs differ")
        counters = _counter_set(item.get("cache_delta"))
        expected_statuses = {
            "MIXED_FIFO_CACHE_REUSE": ["SHADOW_COMPLETED"] * 5,
            "CANCEL_NO_CACHE_EFFECT": ["CANCELED_BEFORE_ADMISSION"],
            "RELOAD_STALE_THEN_COLD": ["STALE_GENERATION_REJECTED", "SHADOW_COMPLETED"],
            "RESTART_STALE_THEN_COLD": ["STALE_GENERATION_REJECTED", "SHADOW_COMPLETED"],
        }[case]
        expected_runs = 5 if case == "MIXED_FIFO_CACHE_REUSE" else (0 if case == "CANCEL_NO_CACHE_EFFECT" else 1)
        if statuses != expected_statuses or runs != expected_runs:
            raise TypingShadowServiceReuseCampaignV1Error("service outcome differs")
        if case == "MIXED_FIFO_CACHE_REUSE":
            if counters != {"lookups": 186, "hits": 138, "misses": 48,
                            "stores": 48, "capacity_skips": 0}:
                raise TypingShadowServiceReuseCampaignV1Error("mixed reuse totals differ")
        elif case == "CANCEL_NO_CACHE_EFFECT":
            if any(counters.values()):
                raise TypingShadowServiceReuseCampaignV1Error("cancellation changed cache")
        elif counters != {"lookups": 24, "hits": 1, "misses": 23,
                          "stores": 23, "capacity_skips": 0}:
            raise TypingShadowServiceReuseCampaignV1Error("transition cold-cache totals differ")
        normalized.append({"case": case, "status": "PASS", "request_ids": list(request_ids),
            "receipt_statuses": list(statuses), "duration_ns": list(durations),
            "owner_runs_delta": runs, "cache_delta": counters})
    core = {"schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "case_count": len(normalized), "cases": normalized,
        "request_order_preserved": True, "complete_solve_fallback_required": True,
        "automatic_retry_allowed": False, "endpoint_only_substitution_authorized": False,
        "timing_used_for_admission": False, "performance_authority": False,
        "controller_opened": False, "transport_opened": False,
        "controller_commands": [], "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False}
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_shadow_service_reuse_campaign_v1(value: Mapping[str, Any]):
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingShadowServiceReuseCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingShadowServiceReuseCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_shadow_service_reuse_campaign_v1(value.get("cases"),
        campaign_id=value.get("campaign_id"), environment=value.get("environment"))
    if rebuilt != dict(value):
        raise TypingShadowServiceReuseCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "COUNTERS", "SCHEMA", "TypingShadowServiceReuseCampaignV1Error",
           "build_typing_shadow_service_reuse_campaign_v1",
           "parse_typing_shadow_service_reuse_campaign_v1"]
