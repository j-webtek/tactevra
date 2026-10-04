"""Retained qualification record for profile-gated shadow-service composition."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.typing_profiled_shadow_service_campaign.v1"
CASES = (
    "QUALIFIED_CACHE_PATH", "CALIBRATION_FULL_SOLVE_PATH",
    "EVIDENCE_FULL_SOLVE_PATH", "RELOAD_RETIRES_PROFILE",
    "RESTART_RETIRES_PROFILE",
)
EXPECTED_DECISIONS = (
    "EXACT_INPUT_REUSE_SHADOW_ELIGIBLE", "FULL_SOLVE_ONLY",
    "FULL_SOLVE_ONLY", "FULL_SOLVE_ONLY", "FULL_SOLVE_ONLY",
)


class TypingProfiledShadowServiceCampaignV1Error(ValueError):
    """The service-composition campaign differs from its fixed matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_profiled_shadow_service_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_receipts_equivalent: bool,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingProfiledShadowServiceCampaignV1Error("campaign id differs")
    if reference_receipts_equivalent is not True or len(cases) != len(CASES):
        raise TypingProfiledShadowServiceCampaignV1Error("campaign result differs")
    normalized = []
    for index, item in enumerate(cases):
        fields = {"case", "status", "profile_decision", "exact_reuse_enabled", "cache_counters"}
        if not isinstance(item, Mapping) or set(item) != fields:
            raise TypingProfiledShadowServiceCampaignV1Error("case fields differ")
        counters = item["cache_counters"]
        if not isinstance(counters, Mapping) or set(counters) != {
            "lookups", "hits", "misses", "stores", "capacity_skips"
        } or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counters.values()):
            raise TypingProfiledShadowServiceCampaignV1Error("cache counters differ")
        expected_enabled = index == 0
        if (item["case"] != CASES[index] or item["status"] != "SHADOW_COMPLETED"
                or item["profile_decision"] != EXPECTED_DECISIONS[index]
                or item["exact_reuse_enabled"] is not expected_enabled):
            raise TypingProfiledShadowServiceCampaignV1Error("case result differs")
        if expected_enabled:
            if counters["lookups"] < 1 or counters["stores"] < 1:
                raise TypingProfiledShadowServiceCampaignV1Error("qualified cache path was unused")
        elif any(counters.values()):
            raise TypingProfiledShadowServiceCampaignV1Error("fallback path touched cache")
        normalized.append({**dict(item), "cache_counters": dict(counters)})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "case_count": len(normalized), "cases": normalized,
        "reference_receipts_equivalent": True,
        "complete_solve_fallback_required": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_profiled_shadow_service_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "case_count", "cases", "reference_receipts_equivalent",
              "complete_solve_fallback_required", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "campaign_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingProfiledShadowServiceCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingProfiledShadowServiceCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_profiled_shadow_service_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_receipts_equivalent=value["reference_receipts_equivalent"])
    if rebuilt != dict(value):
        raise TypingProfiledShadowServiceCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "EXPECTED_DECISIONS", "SCHEMA",
           "TypingProfiledShadowServiceCampaignV1Error",
           "build_typing_profiled_shadow_service_campaign_v1",
           "parse_typing_profiled_shadow_service_campaign_v1"]
