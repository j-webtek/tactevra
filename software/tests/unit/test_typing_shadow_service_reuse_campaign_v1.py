from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_shadow_service_reuse_campaign_v1 as campaign
from rocell.application.operational_latency_reference_v1 import _sha as environment_sha

ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/typing_shadow_service_reuse_campaign_v1.json"
RETAINED_FILE_SHA256 = "da0277885671a24de19a94b6b627759c3ce80726cf4eb530a5718ce16597c4a0"
RETAINED_CAMPAIGN_SHA256 = "62aa3c107cdf2c432001bc7566a9643bf5050255e3b7310432d00d69f3c32cfe"
RETAINED_SOURCE_COMMIT = "ba9930ea248cec85f043a182a9b047d443aa377a"
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_shadow_service_reuse_campaign_v1.schema.json").read_text(encoding="utf-8")))


def _runner():
    path = ROOT / "software/scripts/run_typing_shadow_service_reuse_campaign_v1.py"
    spec = importlib.util.spec_from_file_location("shadow_service_reuse_runner", path)
    module = importlib.util.module_from_spec(spec); assert spec.loader is not None
    spec.loader.exec_module(module); return module


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-29T23:45:00Z", "repository_commit": "a" * 40,
        "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython",
        "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64",
        "logical_cpu_count": 24, "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": "software/scripts/run_typing_shadow_service_reuse_campaign_v1.py"}
    return {**core, "environment_sha256": environment_sha(core)}


@pytest.fixture(scope="module")
def report():
    return campaign.build_typing_shadow_service_reuse_campaign_v1(
        _runner()._campaign_cases(1000), campaign_id="service-reuse-test",
        environment=_environment())


def _rehash(value):
    unsigned = dict(value); unsigned.pop("campaign_sha256", None)
    value["campaign_sha256"] = campaign._sha(unsigned)


def test_service_reuse_campaign_is_ordered_bounded_and_zero_authority(report):
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_shadow_service_reuse_campaign_v1(report)) == report
    mixed = report["cases"][0]
    assert mixed["cache_delta"] == {"lookups": 186, "hits": 138, "misses": 48,
                                      "stores": 48, "capacity_skips": 0}
    assert report["cases"][1]["owner_runs_delta"] == 0
    assert report["automatic_retry_allowed"] is False
    assert report["controller_commands"] == [] and report["physical_authority"] is False


def test_retained_service_reuse_campaign_is_exact_when_installed():
    raw = RETAINED.read_bytes(); assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw); assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_shadow_service_reuse_campaign_v1(report)) == report
    assert report["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT


@pytest.mark.parametrize("mutation,match", (("order", "case order"),
    ("status", "service outcome"), ("cache", "mixed reuse"),
    ("retry", "derivation"), ("authority", "derivation")))
def test_rehashed_service_campaign_mutations_fail_closed(report, mutation, match):
    changed = copy.deepcopy(report)
    if mutation == "order": changed["cases"][0], changed["cases"][1] = changed["cases"][1], changed["cases"][0]
    elif mutation == "status": changed["cases"][1]["receipt_statuses"] = ["SHADOW_COMPLETED"]
    elif mutation == "cache": changed["cases"][0]["cache_delta"]["hits"] -= 1; changed["cases"][0]["cache_delta"]["misses"] += 1
    elif mutation == "retry": changed["automatic_retry_allowed"] = True
    else: changed["physical_authority"] = True
    _rehash(changed)
    with pytest.raises(campaign.TypingShadowServiceReuseCampaignV1Error, match=match):
        campaign.parse_typing_shadow_service_reuse_campaign_v1(changed)
