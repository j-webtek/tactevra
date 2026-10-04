"""Retained cold/warm mixed-queue campaign for actual shared-emitter bytes."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.actual_emitter_mixed_queue_campaign.v1"
PATTERNS = (
    ("HOME_TRANSITION", ("H", "I")),
    ("WORD_ROBOT", ("R", "O", "B", "O", "T")),
    ("REPEAT_NUMBER_PUNCTUATION", ("H", "H", "1", "PERIOD")),
    ("ALPHABETIC_EXTREMES", ("A", "Z")),
    ("NUMBER_SPACE_ENTER", ("1", "SPACE", "ENTER")),
)
ROUNDS = ("COLD", "WARM")


class ActualEmitterMixedQueueCampaignV1Error(ValueError):
    """Mixed-queue evidence differs from the frozen campaign."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def percentile_nearest_rank_v1(values: Sequence[int], percentile: float) -> int:
    if (not values or not 0.0 < percentile <= 1.0
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values)):
        raise ActualEmitterMixedQueueCampaignV1Error("latency samples differ")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def build_actual_emitter_mixed_queue_campaign_v1(
    rounds: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], request_order_preserved: bool,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise ActualEmitterMixedQueueCampaignV1Error("campaign id differs")
    if request_order_preserved is not True or len(rounds) != 2:
        raise ActualEmitterMixedQueueCampaignV1Error("campaign result differs")
    normalized = []
    for index, item in enumerate(rounds):
        fields = {"round", "request_ids", "payload_sha256", "receipt_statuses",
                  "duration_ns", "p50_duration_ns", "p95_duration_ns", "cache_delta"}
        if not isinstance(item, Mapping) or set(item) != fields:
            raise ActualEmitterMixedQueueCampaignV1Error("round fields differ")
        request_ids = item["request_ids"]; payloads = item["payload_sha256"]
        statuses = item["receipt_statuses"]; durations = item["duration_ns"]
        if (item["round"] != ROUNDS[index] or not isinstance(request_ids, list)
                or len(request_ids) != len(PATTERNS) or len(set(request_ids)) != len(request_ids)
                or not isinstance(payloads, list) or len(payloads) != len(PATTERNS)
                or any(not isinstance(v, str) or len(v) != 64 for v in payloads)
                or statuses != ["SHADOW_COMPLETED"] * len(PATTERNS)
                or not isinstance(durations, list) or len(durations) != len(PATTERNS)):
            raise ActualEmitterMixedQueueCampaignV1Error("round result differs")
        if item["p50_duration_ns"] != percentile_nearest_rank_v1(durations, 0.50) \
                or item["p95_duration_ns"] != percentile_nearest_rank_v1(durations, 0.95):
            raise ActualEmitterMixedQueueCampaignV1Error("latency derivation differs")
        counters = item["cache_delta"]
        if not isinstance(counters, Mapping) or set(counters) != {
            "lookups", "hits", "misses", "stores", "capacity_skips"
        } or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counters.values()):
            raise ActualEmitterMixedQueueCampaignV1Error("cache counters differ")
        if counters["lookups"] != counters["hits"] + counters["misses"]:
            raise ActualEmitterMixedQueueCampaignV1Error("cache derivation differs")
        if index == 0:
            if counters["misses"] < 1 or counters["stores"] != counters["misses"] or counters["capacity_skips"] != 0:
                raise ActualEmitterMixedQueueCampaignV1Error("cold cache result differs")
        elif counters["hits"] != counters["lookups"] or counters["misses"] != 0 or counters["stores"] != 0 or counters["capacity_skips"] != 0:
            raise ActualEmitterMixedQueueCampaignV1Error("warm cache result differs")
        normalized.append({**dict(item), "cache_delta": dict(counters)})
    cold, warm = normalized
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "fixture_scope": "SYNTHETIC_INTEGRATION_ONLY",
        "patterns": [{"pattern_id": name, "target_ids": list(targets)}
                     for name, targets in PATTERNS],
        "round_count": 2, "rounds": normalized,
        "request_order_preserved": True,
        "warm_p50_improved_observed": warm["p50_duration_ns"] < cold["p50_duration_ns"],
        "warm_p95_improved_observed": warm["p95_duration_ns"] < cold["p95_duration_ns"],
        "timing_used_for_admission": False,
        "complete_solve_fallback_required": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_actual_emitter_mixed_queue_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "actual_shared_emitter_used", "fixture_scope", "patterns",
              "round_count", "rounds", "request_order_preserved",
              "warm_p50_improved_observed", "warm_p95_improved_observed",
              "timing_used_for_admission", "complete_solve_fallback_required",
              "automatic_retry_allowed", "executor_attached", "controller_opened",
              "transport_opened", "controller_commands", "hardware_writes",
              "physical_movements", "physical_authority", "campaign_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ActualEmitterMixedQueueCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise ActualEmitterMixedQueueCampaignV1Error("campaign hash differs")
    expected_patterns = [{"pattern_id": name, "target_ids": list(targets)} for name, targets in PATTERNS]
    if value["patterns"] != expected_patterns or value["round_count"] != 2:
        raise ActualEmitterMixedQueueCampaignV1Error("pattern matrix differs")
    rebuilt = build_actual_emitter_mixed_queue_campaign_v1(
        value["rounds"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        request_order_preserved=value["request_order_preserved"])
    if rebuilt != dict(value):
        raise ActualEmitterMixedQueueCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["PATTERNS", "ROUNDS", "SCHEMA",
           "ActualEmitterMixedQueueCampaignV1Error",
           "build_actual_emitter_mixed_queue_campaign_v1",
           "parse_actual_emitter_mixed_queue_campaign_v1",
           "percentile_nearest_rank_v1"]
