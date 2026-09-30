from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.actual_emitter_mixed_queue_campaign_v1 as campaign

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/actual_emitter_mixed_queue_campaign_v1.schema.json").read_text()))
RETAINED = ROOT / "software/ai/eval/actual_emitter_mixed_queue_campaign_v1.json"
RETAINED_FILE_SHA256 = "9e4d60617131f4d05db455dd0d85200595d43582bb801fb542367b79c5dcee32"
RETAINED_CAMPAIGN_SHA256 = "0ca85b439959f3f5078f6b038efd63340affb7ae3596373f2726e0a5718f47a2"
RETAINED_SOURCE_COMMIT = "c6cb76900d5b91394377291b9514a8db4fff23a3"


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T05:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_actual_emitter_mixed_queue_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core); return core


def _round(label):
    warm = label == "WARM"; durations = [100, 200, 300, 400, 500] if not warm else [10, 20, 30, 40, 50]
    counters = ({"lookups": 186, "hits": 26, "misses": 160, "stores": 160, "capacity_skips": 0} if not warm else {"lookups": 186, "hits": 186, "misses": 0, "stores": 0, "capacity_skips": 0})
    return {"round": label, "request_ids": [f"{label}-{i}" for i in range(5)], "payload_sha256": [f"{i + 1:x}" * 64 for i in range(5)], "receipt_statuses": ["SHADOW_COMPLETED"] * 5, "duration_ns": durations, "p50_duration_ns": 300 if not warm else 30, "p95_duration_ns": 500 if not warm else 50, "cache_delta": counters}


def test_campaign_round_trip_percentiles_and_zero_authority():
    value = campaign.build_actual_emitter_mixed_queue_campaign_v1(
        [_round("COLD"), _round("WARM")], campaign_id="campaign",
        environment=_environment(), request_order_preserved=True)
    VALIDATOR.validate(value)
    assert campaign.parse_actual_emitter_mixed_queue_campaign_v1(value) == value
    assert value["warm_p50_improved_observed"] is True
    assert value["warm_p95_improved_observed"] is True
    assert value["timing_used_for_admission"] is value["physical_authority"] is False


def test_campaign_rejects_bad_percentile_warm_miss_and_hash():
    rounds = [_round("COLD"), _round("WARM")]; rounds[0]["p95_duration_ns"] = 499
    with pytest.raises(campaign.ActualEmitterMixedQueueCampaignV1Error, match="latency"):
        campaign.build_actual_emitter_mixed_queue_campaign_v1(
            rounds, campaign_id="campaign", environment=_environment(),
            request_order_preserved=True)
    rounds = [_round("COLD"), _round("WARM")]; rounds[1]["cache_delta"]["misses"] = 1
    with pytest.raises(campaign.ActualEmitterMixedQueueCampaignV1Error):
        campaign.build_actual_emitter_mixed_queue_campaign_v1(
            rounds, campaign_id="campaign", environment=_environment(),
            request_order_preserved=True)
    value = campaign.build_actual_emitter_mixed_queue_campaign_v1(
        [_round("COLD"), _round("WARM")], campaign_id="campaign",
        environment=_environment(), request_order_preserved=True)
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.ActualEmitterMixedQueueCampaignV1Error, match="hash"):
        campaign.parse_actual_emitter_mixed_queue_campaign_v1(changed)


def test_retained_campaign_is_pinned_clean_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_actual_emitter_mixed_queue_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert value["environment"]["repository_dirty"] is False
    assert value["request_order_preserved"] is True
    assert value["rounds"][0]["cache_delta"] == {
        "capacity_skips": 0, "hits": 138, "lookups": 186,
        "misses": 48, "stores": 48,
    }
    assert value["rounds"][1]["cache_delta"] == {
        "capacity_skips": 0, "hits": 186, "lookups": 186,
        "misses": 0, "stores": 0,
    }
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is value["timing_used_for_admission"] is False
