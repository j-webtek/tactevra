from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.actual_emitter_disturbance_campaign_v1 as campaign

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/actual_emitter_disturbance_campaign_v1.schema.json").read_text()))
RETAINED = ROOT / "software/ai/eval/actual_emitter_disturbance_campaign_v1.json"
RETAINED_FILE_SHA256 = "904241adddcb218f314df6c4d27c9fcfa66e3ddc9c25d28a7d2d1e3671280ebf"
RETAINED_CAMPAIGN_SHA256 = "b47c01533b6fad040ed3ef0cd13efb22f49b11af2af2318d3880d02ae7d931f1"
RETAINED_SOURCE_COMMIT = "aacc219a008ebb4ae047fbf3f5774d198d1dd163"


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T07:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_actual_emitter_disturbance_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core); return core


def _cases(reference="a" * 64):
    zero = {"lookups": 0, "hits": 0, "misses": 0, "stores": 0, "capacity_skips": 0}
    warm = {"lookups": 57, "hits": 57, "misses": 0, "stores": 0, "capacity_skips": 0}
    status = {"WARM_BASELINE": ["SHADOW_COMPLETED"], "QUEUE_SATURATION": ["SHADOW_COMPLETED"] * 8,
              "CANCEL_PRESSURE": ["CANCELED_BEFORE_ADMISSION"] * 3 + ["SHADOW_COMPLETED"] * 5,
              "MALFORMED_REJECTION": [], "RELOAD_STALE_AND_FALLBACK": ["STALE_GENERATION_REJECTED"] * 3 + ["SHADOW_COMPLETED"],
              "RESTART_STALE_AND_FALLBACK": ["STALE_GENERATION_REJECTED"] * 2 + ["SHADOW_COMPLETED"],
              "QUALIFIED_REPLACEMENT_RECOVERY": ["SHADOW_COMPLETED"]}
    result = []
    for name in campaign.CASES:
        match = name in {"WARM_BASELINE", "QUALIFIED_REPLACEMENT_RECOVERY"}
        result.append({"case": name, "statuses": status[name], "request_order_preserved": True,
                       "rejection_messages": (["full"] if name == "QUEUE_SATURATION" else ["one", "two", "three"] if name == "MALFORMED_REJECTION" else []),
                       "cache_activity": dict(warm if name in {"WARM_BASELINE", "QUEUE_SATURATION", "CANCEL_PRESSURE", "QUALIFIED_REPLACEMENT_RECOVERY"} else zero),
                       "exact_reuse_enabled_after": name not in {"RELOAD_STALE_AND_FALLBACK", "RESTART_STALE_AND_FALLBACK"},
                       "automatic_retries": 0, "reference_equivalent": match,
                       "shadow_receipt_sha256": reference if match else None})
    return result


def test_disturbance_campaign_round_trip_and_zero_authority():
    reference = "a" * 64
    value = campaign.build_actual_emitter_disturbance_campaign_v1(
        _cases(reference), campaign_id="campaign", environment=_environment(),
        reference_shadow_receipt_sha256=reference)
    VALIDATOR.validate(value)
    assert campaign.parse_actual_emitter_disturbance_campaign_v1(value) == value
    assert value["decision_equivalence_preserved"] is True
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_disturbance_campaign_rejects_cache_retry_and_hash_drift():
    cases = _cases(); cases[1]["cache_activity"]["misses"] = 1
    with pytest.raises(campaign.ActualEmitterDisturbanceCampaignV1Error):
        campaign.build_actual_emitter_disturbance_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_shadow_receipt_sha256="a" * 64)
    cases = _cases(); cases[2]["automatic_retries"] = 1
    with pytest.raises(campaign.ActualEmitterDisturbanceCampaignV1Error, match="lifecycle"):
        campaign.build_actual_emitter_disturbance_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_shadow_receipt_sha256="a" * 64)
    value = campaign.build_actual_emitter_disturbance_campaign_v1(
        _cases(), campaign_id="campaign", environment=_environment(),
        reference_shadow_receipt_sha256="a" * 64)
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.ActualEmitterDisturbanceCampaignV1Error, match="hash"):
        campaign.parse_actual_emitter_disturbance_campaign_v1(changed)


def test_retained_disturbance_campaign_is_pinned_fail_closed_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_actual_emitter_disturbance_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert value["environment"]["repository_dirty"] is False
    indexed = {item["case"]: item for item in value["cases"]}
    assert indexed["QUEUE_SATURATION"]["cache_activity"]["hits"] == 313
    assert indexed["CANCEL_PRESSURE"]["cache_activity"]["hits"] == 175
    assert indexed["MALFORMED_REJECTION"]["cache_activity"]["lookups"] == 0
    assert indexed["RELOAD_STALE_AND_FALLBACK"]["exact_reuse_enabled_after"] is False
    assert indexed["RESTART_STALE_AND_FALLBACK"]["exact_reuse_enabled_after"] is False
    assert indexed["QUALIFIED_REPLACEMENT_RECOVERY"]["reference_equivalent"] is True
    assert all(item["automatic_retries"] == 0 for item in value["cases"])
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is False
