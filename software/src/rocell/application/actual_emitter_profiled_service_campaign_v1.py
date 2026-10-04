"""Qualification record for actual AI-emitter bytes through profiled service."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.actual_emitter_profiled_service_campaign.v1"
CASES = (
    "QUALIFIED_COLD", "QUALIFIED_WARM", "CALIBRATION_FALLBACK",
    "EVIDENCE_FALLBACK", "CANCEL_BEFORE_ADMISSION",
    "RELOAD_FALLBACK", "RESTART_FALLBACK",
)
EXPECTED_STATUS = (
    "SHADOW_COMPLETED", "SHADOW_COMPLETED", "SHADOW_COMPLETED",
    "SHADOW_COMPLETED", "CANCELED_BEFORE_ADMISSION",
    "SHADOW_COMPLETED", "SHADOW_COMPLETED",
)
EXPECTED_DECISION = (
    "EXACT_INPUT_REUSE_SHADOW_ELIGIBLE",
    "EXACT_INPUT_REUSE_SHADOW_ELIGIBLE", "FULL_SOLVE_ONLY",
    "FULL_SOLVE_ONLY", "EXACT_INPUT_REUSE_SHADOW_ELIGIBLE",
    "FULL_SOLVE_ONLY", "FULL_SOLVE_ONLY",
)


class ActualEmitterProfiledServiceCampaignV1Error(ValueError):
    """Actual-emitter service evidence differs from the fixed campaign."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_actual_emitter_profiled_service_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], ordered_targets: Sequence[str],
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise ActualEmitterProfiledServiceCampaignV1Error("campaign id differs")
    if list(ordered_targets) != ["R", "O", "B", "O", "T"] or len(cases) != len(CASES):
        raise ActualEmitterProfiledServiceCampaignV1Error("campaign scope differs")
    normalized = []
    for index, item in enumerate(cases):
        fields = {"case", "status", "profile_decision", "duration_ns",
                  "payload_sha256", "cache_delta"}
        if not isinstance(item, Mapping) or set(item) != fields:
            raise ActualEmitterProfiledServiceCampaignV1Error("case fields differ")
        counters = item["cache_delta"]
        if not isinstance(counters, Mapping) or set(counters) != {
            "lookups", "hits", "misses", "stores", "capacity_skips"
        } or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counters.values()):
            raise ActualEmitterProfiledServiceCampaignV1Error("cache counters differ")
        duration = item["duration_ns"]
        digest = item["payload_sha256"]
        if (item["case"] != CASES[index] or item["status"] != EXPECTED_STATUS[index]
                or item["profile_decision"] != EXPECTED_DECISION[index]
                or isinstance(duration, bool) or not isinstance(duration, int) or duration < 0
                or not isinstance(digest, str) or len(digest) != 64):
            raise ActualEmitterProfiledServiceCampaignV1Error("case result differs")
        if index == 0:
            if counters["lookups"] < 1 or counters["stores"] != counters["misses"]:
                raise ActualEmitterProfiledServiceCampaignV1Error("cold cache result differs")
        elif index == 1:
            if counters["lookups"] < 1 or counters["hits"] != counters["lookups"] or counters["misses"] != 0:
                raise ActualEmitterProfiledServiceCampaignV1Error("warm cache result differs")
        elif any(counters.values()):
            raise ActualEmitterProfiledServiceCampaignV1Error("non-executing or fallback path touched cache")
        normalized.append({**dict(item), "cache_delta": dict(counters)})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "fixture_scope": "SYNTHETIC_INTEGRATION_ONLY",
        "ordered_targets": list(ordered_targets),
        "case_count": len(normalized), "cases": normalized,
        "timing_used_for_admission": False,
        "complete_solve_fallback_required": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_actual_emitter_profiled_service_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "actual_shared_emitter_used", "fixture_scope", "ordered_targets",
              "case_count", "cases", "timing_used_for_admission",
              "complete_solve_fallback_required", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "campaign_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ActualEmitterProfiledServiceCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise ActualEmitterProfiledServiceCampaignV1Error("campaign hash differs")
    rebuilt = build_actual_emitter_profiled_service_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"], ordered_targets=value["ordered_targets"])
    if rebuilt != dict(value):
        raise ActualEmitterProfiledServiceCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "EXPECTED_DECISION", "EXPECTED_STATUS", "SCHEMA",
           "ActualEmitterProfiledServiceCampaignV1Error",
           "build_actual_emitter_profiled_service_campaign_v1",
           "parse_actual_emitter_profiled_service_campaign_v1"]
