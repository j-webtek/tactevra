from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_endpoint_reuse_campaign_v1 as campaign
from rocell.application.operational_latency_reference_v1 import _sha as environment_sha


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/typing_endpoint_reuse_campaign_v1.json"
RETAINED_FILE_SHA256 = "34bbc8fc3882c0057f43332b5f365241aa12ed58bc6dab4453c13edffc05d913"
RETAINED_CAMPAIGN_SHA256 = "4f662d46cd09bcf69552f23cf63c7b1ecfc54ca65447076d9dbf8b8e756bb2fc"
RETAINED_SOURCE_COMMIT = "9833ed964fb889bb0e8bd5ef00e2e85fd475e89d"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_endpoint_reuse_campaign_v1.schema.json"
).read_text(encoding="utf-8")))


def _runner():
    path = ROOT / "software/scripts/run_typing_endpoint_reuse_campaign_v1.py"
    spec = importlib.util.spec_from_file_location("endpoint_reuse_campaign_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _environment():
    core = {
        "schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-29T23:00:00Z", "repository_commit": "a" * 40,
        "repository_dirty": False, "python_version": "3.10.10",
        "python_implementation": "CPython", "platform_system": "Windows",
        "platform_release": "10", "platform_machine": "AMD64",
        "logical_cpu_count": 24, "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": "software/scripts/run_typing_endpoint_reuse_campaign_v1.py",
    }
    return {**core, "environment_sha256": environment_sha(core)}


@pytest.fixture(scope="module")
def report():
    runner = _runner()
    return campaign.build_typing_endpoint_reuse_campaign_v1(
        runner._route_cases(1000), runner._fault_cases(1000),
        campaign_id="endpoint-reuse-test", environment=_environment())


def _rehash(report):
    unsigned = dict(report); unsigned.pop("campaign_sha256", None)
    report["campaign_sha256"] = campaign._sha(unsigned)


def test_campaign_is_complete_exact_and_zero_authority(report):
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_endpoint_reuse_campaign_v1(report)) == report
    final = report["final_verifier_snapshot"]
    assert (final["observed_sample_count"], final["endpoint_observation_count"],
            final["entry_count"], final["canonical_matches"]) == (186, 58, 40, 18)
    assert all(case["receipt_matches_reference"] for case in report["route_cases"])
    assert report["candidate_used_for_decision"] is False
    assert report["controller_commands"] == []
    assert report["physical_authority"] is False


def test_retained_campaign_is_exact_when_installed():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_endpoint_reuse_campaign_v1(report)) == report
    assert report["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT


@pytest.mark.parametrize("mutation,match", (
    ("route", "route case order"), ("receipt", "route receipt"),
    ("snapshot", "final verifier totals"), ("fault", "fault outcome"),
    ("authority", "derivation"),
))
def test_rehashed_mutations_fail_closed(report, mutation, match):
    changed = copy.deepcopy(report)
    if mutation == "route":
        changed["route_cases"][0], changed["route_cases"][1] = changed["route_cases"][1], changed["route_cases"][0]
    elif mutation == "receipt":
        changed["route_cases"][0]["observed_receipt_sha256"] = "f" * 64
    elif mutation == "snapshot":
        snap = changed["route_cases"][-1]["after_verifier_snapshot"]
        snap["observed_sample_count"] -= 1
        unsigned = dict(snap); unsigned.pop("verifier_snapshot_sha256")
        snap["verifier_snapshot_sha256"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        changed["final_verifier_snapshot"] = copy.deepcopy(snap)
    elif mutation == "fault":
        changed["fault_cases"][1]["outcome"] = "BOUNDED"
    else:
        changed["physical_authority"] = True
    _rehash(changed)
    with pytest.raises(campaign.TypingEndpointReuseCampaignV1Error, match=match):
        campaign.parse_typing_endpoint_reuse_campaign_v1(changed)
