"""Strict retained evidence for repeated actual-emitter service stability."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .actual_emitter_mixed_queue_campaign_v1 import PATTERNS, percentile_nearest_rank_v1
from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.actual_emitter_stability_campaign.v1"
COUNTERS = frozenset({"lookups", "hits", "misses", "stores", "capacity_skips"})
EXPECTED_CYCLES = 20
SAMPLES_PER_LANE = EXPECTED_CYCLES * len(PATTERNS)


class ActualEmitterStabilityCampaignV1Error(ValueError):
    """Repeated stability evidence differs from the frozen campaign."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _latencies(values: Sequence[int]) -> dict[str, int]:
    if len(values) != SAMPLES_PER_LANE:
        raise ActualEmitterStabilityCampaignV1Error("latency sample count differs")
    return {
        "p50_duration_ns": percentile_nearest_rank_v1(values, 0.50),
        "p95_duration_ns": percentile_nearest_rank_v1(values, 0.95),
        "p99_duration_ns": percentile_nearest_rank_v1(values, 0.99),
        "max_duration_ns": max(values),
    }


def _counter(value: object, expected: Mapping[str, int], label: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != COUNTERS:
        raise ActualEmitterStabilityCampaignV1Error(f"{label} counters differ")
    result = dict(value)
    if result != dict(expected):
        raise ActualEmitterStabilityCampaignV1Error(f"{label} counters differ")
    return result


def build_actual_emitter_stability_campaign_v1(
    cycles: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], request_order_preserved: bool,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise ActualEmitterStabilityCampaignV1Error("campaign id differs")
    if request_order_preserved is not True or len(cycles) != EXPECTED_CYCLES:
        raise ActualEmitterStabilityCampaignV1Error("campaign result differs")
    normalized = []
    cold_samples: list[int] = []
    warm_samples: list[int] = []
    cold_expected = {"lookups": 186, "hits": 138, "misses": 48,
                     "stores": 48, "capacity_skips": 0}
    warm_expected = {"lookups": 186, "hits": 186, "misses": 0,
                     "stores": 0, "capacity_skips": 0}
    for index, item in enumerate(cycles, 1):
        fields = {"cycle", "cold_duration_ns", "warm_duration_ns",
                  "cold_cache_delta", "warm_cache_delta",
                  "cold_shadow_receipt_sha256", "warm_shadow_receipt_sha256",
                  "receipts_equivalent", "cold_invalidated", "warm_invalidated"}
        if not isinstance(item, Mapping) or set(item) != fields or item["cycle"] != index:
            raise ActualEmitterStabilityCampaignV1Error("cycle fields differ")
        cold = item["cold_duration_ns"]; warm = item["warm_duration_ns"]
        cold_hashes = item["cold_shadow_receipt_sha256"]
        warm_hashes = item["warm_shadow_receipt_sha256"]
        if (not isinstance(cold, list) or not isinstance(warm, list)
                or len(cold) != len(PATTERNS) or len(warm) != len(PATTERNS)
                or any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                       for v in cold + warm)
                or not isinstance(cold_hashes, list) or not isinstance(warm_hashes, list)
                or len(cold_hashes) != len(PATTERNS)
                or any(not isinstance(v, str) or len(v) != 64 for v in cold_hashes)
                or warm_hashes != cold_hashes or item["receipts_equivalent"] is not True
                or item["cold_invalidated"] is not True
                or item["warm_invalidated"] is not True):
            raise ActualEmitterStabilityCampaignV1Error("cycle result differs")
        cold_counter = _counter(item["cold_cache_delta"], cold_expected, "cold")
        warm_counter = _counter(item["warm_cache_delta"], warm_expected, "warm")
        cold_samples.extend(cold); warm_samples.extend(warm)
        normalized.append({**dict(item), "cold_cache_delta": cold_counter,
                           "warm_cache_delta": warm_counter})
    cold_latency = _latencies(cold_samples); warm_latency = _latencies(warm_samples)
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "fixture_scope": "SYNTHETIC_INTEGRATION_ONLY",
        "patterns": [{"pattern_id": name, "target_ids": list(targets)}
                     for name, targets in PATTERNS],
        "cycle_count": EXPECTED_CYCLES,
        "samples_per_lane": SAMPLES_PER_LANE,
        "cycles": normalized,
        "cold_latency": cold_latency, "warm_latency": warm_latency,
        "all_receipts_equivalent": True,
        "request_order_preserved": True,
        "lifecycle_replacement_cold_confirmed": True,
        "resource_bounds": {"maximum_entries": 256, "maximum_queued": 8,
                            "maximum_requests": 16,
                            "observed_capacity_skips": 0},
        "timing_used_for_admission": False,
        "complete_solve_fallback_required": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_actual_emitter_stability_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "actual_shared_emitter_used", "fixture_scope", "patterns",
              "cycle_count", "samples_per_lane", "cycles", "cold_latency",
              "warm_latency", "all_receipts_equivalent",
              "request_order_preserved", "lifecycle_replacement_cold_confirmed",
              "resource_bounds", "timing_used_for_admission",
              "complete_solve_fallback_required", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "campaign_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields or value.get("schema") != SCHEMA:
        raise ActualEmitterStabilityCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise ActualEmitterStabilityCampaignV1Error("campaign hash differs")
    rebuilt = build_actual_emitter_stability_campaign_v1(
        value["cycles"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        request_order_preserved=value["request_order_preserved"])
    if rebuilt != dict(value):
        raise ActualEmitterStabilityCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["EXPECTED_CYCLES", "SAMPLES_PER_LANE", "SCHEMA",
           "ActualEmitterStabilityCampaignV1Error",
           "build_actual_emitter_stability_campaign_v1",
           "parse_actual_emitter_stability_campaign_v1"]
