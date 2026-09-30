from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.actual_emitter_stability_campaign_v1 as campaign

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/actual_emitter_stability_campaign_v1.schema.json").read_text()))


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T06:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_actual_emitter_stability_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core); return core


def _cycles():
    result = []
    for index in range(1, 21):
        hashes = [str(item) * 64 for item in range(1, 6)]
        result.append({"cycle": index, "cold_duration_ns": [100, 200, 300, 400, 500],
                       "warm_duration_ns": [10, 20, 30, 40, 50],
                       "cold_cache_delta": {"lookups": 186, "hits": 138, "misses": 48, "stores": 48, "capacity_skips": 0},
                       "warm_cache_delta": {"lookups": 186, "hits": 186, "misses": 0, "stores": 0, "capacity_skips": 0},
                       "cold_shadow_receipt_sha256": hashes,
                       "warm_shadow_receipt_sha256": list(hashes),
                       "receipts_equivalent": True,
                       "cold_invalidated": True, "warm_invalidated": True})
    return result


def test_stability_campaign_round_trip_and_percentiles():
    value = campaign.build_actual_emitter_stability_campaign_v1(
        _cycles(), campaign_id="campaign", environment=_environment(),
        request_order_preserved=True)
    VALIDATOR.validate(value)
    assert campaign.parse_actual_emitter_stability_campaign_v1(value) == value
    assert value["samples_per_lane"] == 100
    assert value["cold_latency"] == {"p50_duration_ns": 300, "p95_duration_ns": 500,
                                      "p99_duration_ns": 500, "max_duration_ns": 500}
    assert value["physical_authority"] is value["timing_used_for_admission"] is False


def test_stability_campaign_rejects_receipt_cache_and_hash_drift():
    cycles = _cycles(); cycles[3]["warm_shadow_receipt_sha256"][0] = "f" * 64
    with pytest.raises(campaign.ActualEmitterStabilityCampaignV1Error, match="cycle result"):
        campaign.build_actual_emitter_stability_campaign_v1(
            cycles, campaign_id="campaign", environment=_environment(),
            request_order_preserved=True)
    cycles = _cycles(); cycles[4]["warm_cache_delta"]["hits"] = 185
    with pytest.raises(campaign.ActualEmitterStabilityCampaignV1Error, match="warm counters"):
        campaign.build_actual_emitter_stability_campaign_v1(
            cycles, campaign_id="campaign", environment=_environment(),
            request_order_preserved=True)
    value = campaign.build_actual_emitter_stability_campaign_v1(
        _cycles(), campaign_id="campaign", environment=_environment(),
        request_order_preserved=True)
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.ActualEmitterStabilityCampaignV1Error, match="hash"):
        campaign.parse_actual_emitter_stability_campaign_v1(changed)
