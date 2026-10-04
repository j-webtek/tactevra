from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_exact_reuse_multisequence_campaign_v1 as campaign
from rocell.application.operational_latency_reference_v1 import _sha as environment_sha

ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/typing_exact_reuse_multisequence_campaign_v1.json"
RETAINED_FILE_SHA256 = "692b621a6910928507cb5a5f5b3dcfae92d7279a66c7537d3fe0a10752746f22"
RETAINED_CAMPAIGN_SHA256 = "b9caa7e7c2f75ef43de26b19d848ad71ceb6bd96d7d1666d42bce1904883bd14"
RETAINED_SOURCE_COMMIT = "0e3982335717974fe3dafe58faf8805ebd83022c"
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_exact_reuse_multisequence_campaign_v1.schema.json").read_text(encoding="utf-8")))


def _runner():
    path = ROOT / "software/scripts/run_typing_exact_reuse_multisequence_campaign_v1.py"
    spec = importlib.util.spec_from_file_location("exact_reuse_multisequence_runner", path)
    module = importlib.util.module_from_spec(spec); assert spec.loader is not None
    spec.loader.exec_module(module); return module


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-29T23:30:00Z", "repository_commit": "a" * 40,
        "repository_dirty": False, "python_version": "3.10.10",
        "python_implementation": "CPython", "platform_system": "Windows",
        "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24,
        "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": "software/scripts/run_typing_exact_reuse_multisequence_campaign_v1.py"}
    return {**core, "environment_sha256": environment_sha(core)}


@pytest.fixture(scope="module")
def report():
    return campaign.build_typing_exact_reuse_multisequence_campaign_v1(
        _runner()._cases(1000), campaign_id="exact-reuse-test", environment=_environment())


def _rehash(value):
    unsigned = dict(value); unsigned.pop("campaign_sha256", None)
    value["campaign_sha256"] = campaign._sha(unsigned)


def test_multisequence_exact_reuse_is_equivalent_bounded_and_zero_authority(report):
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_exact_reuse_multisequence_campaign_v1(report)) == report
    assert report["total_samples"] == 186
    assert report["total_warm_hits"] == 186
    assert report["total_cold_hits"] > 0
    assert report["endpoint_only_substitution_authorized"] is False
    assert report["complete_solve_fallback_required"] is True
    assert report["controller_commands"] == [] and report["physical_authority"] is False


def test_retained_multisequence_campaign_is_exact_when_installed():
    raw = RETAINED.read_bytes(); assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw); assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_exact_reuse_multisequence_campaign_v1(report)) == report
    assert report["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT


@pytest.mark.parametrize("mutation,match", (("order", "case order"),
    ("receipt", "changed decisions"), ("warm", "warm substitution"),
    ("fallback", "derivation"), ("authority", "derivation")))
def test_rehashed_mutations_fail_closed(report, mutation, match):
    changed = copy.deepcopy(report)
    if mutation == "order": changed["cases"][0], changed["cases"][1] = changed["cases"][1], changed["cases"][0]
    elif mutation == "receipt": changed["cases"][0]["warm_receipt_sha256"] = "f" * 64
    elif mutation == "warm":
        changed["cases"][0]["warm_counters"]["hits"] -= 1
        changed["cases"][0]["warm_counters"]["misses"] += 1
    elif mutation == "fallback": changed["complete_solve_fallback_required"] = False
    else: changed["physical_authority"] = True
    _rehash(changed)
    with pytest.raises(campaign.TypingExactReuseMultisequenceCampaignV1Error, match=match):
        campaign.parse_typing_exact_reuse_multisequence_campaign_v1(changed)
