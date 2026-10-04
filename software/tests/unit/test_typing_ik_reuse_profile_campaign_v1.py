from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_ik_reuse_profile_campaign_v1 as campaign

ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/typing_ik_reuse_profile_campaign_v1.json"
RETAINED_FILE_SHA256 = "994ae13d3e0ebf2331972c142ed2aa473eecab4063a71eec6d3315498ac87aa3"
RETAINED_CAMPAIGN_SHA256 = "b8309defb43d62b5ebe2f0f63e432e1ff83e5af3cb900d273bf60a434a73d020"
RETAINED_SOURCE_COMMIT = "7c92709501f723a0e9e3ecec1e7db0e722076973"
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_ik_reuse_profile_campaign_v1.schema.json").read_text()))


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T02:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_typing_ik_reuse_profile_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core)
    return core


def _cases():
    return [{"case": name, "status": "PASS", "disposition": disposition, "detail": "bounded qualification result"} for name, disposition in zip(campaign.CASES, campaign.EXPECTED)]


def test_campaign_round_trip_and_schema():
    value = campaign.build_typing_ik_reuse_profile_campaign_v1(
        _cases(), campaign_id="campaign", environment=_environment(),
        qualified_profile_sha256="b" * 64)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_ik_reuse_profile_campaign_v1(value) == value
    assert value["physical_authority"] is False


def test_campaign_rejects_changed_disposition_and_hash():
    value = campaign.build_typing_ik_reuse_profile_campaign_v1(
        _cases(), campaign_id="campaign", environment=_environment(),
        qualified_profile_sha256="b" * 64)
    changed = copy.deepcopy(value); changed["cases"][0]["disposition"] = "FULL_SOLVE_ONLY"
    with pytest.raises(campaign.TypingIkReuseProfileCampaignV1Error):
        campaign.parse_typing_ik_reuse_profile_campaign_v1(changed)
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingIkReuseProfileCampaignV1Error, match="hash"):
        campaign.parse_typing_ik_reuse_profile_campaign_v1(changed)


def test_retained_campaign_is_pinned_to_clean_framework_commit():
    import hashlib
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_ik_reuse_profile_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert value["environment"]["repository_dirty"] is False
