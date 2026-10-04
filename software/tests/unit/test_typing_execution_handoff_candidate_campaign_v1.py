from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_execution_handoff_candidate_campaign_v1 as campaign
import rocell.application.typing_execution_handoff_candidate_v1 as handoff
from software.tests.unit.test_typing_execution_handoff_candidate_v1 import _evidence

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_execution_handoff_candidate_campaign_v1.schema.json").read_text()))
RETAINED = ROOT / "software/ai/eval/typing_execution_handoff_candidate_campaign_v1.json"
RETAINED_FILE_SHA256 = "79808f9e3b47f05677ca1cb34b652d4b8a181f29d0baa364e81fc4e2e9be5621"
RETAINED_CAMPAIGN_SHA256 = "720d2863ec75d333d44cb29ce41e13f19dfaa8ab640ae67f7c0d33b09bc40203"
RETAINED_SOURCE_COMMIT = "8ab089228c868b1bb4cf57c8840f9ec0e57778e1"


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T11:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_typing_execution_handoff_candidate_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core); return core


def _cases():
    session, admission, service, shadow = _evidence()
    candidate = handoff.build_typing_execution_handoff_candidate_v1(
        session, admission, service, shadow)
    result = []
    retained = {"VALID_COMPLETED_CHAIN", "DETERMINISTIC_REBUILD", "BLOCKERS_PRESERVED"}
    for name in campaign.CASES:
        result.append({"case": name, "observed": campaign.EXPECTED[name],
                       "candidate": candidate if name in retained else None,
                       "error": None if name in retained else "rejected",
                       "zero_authority_validated": True})
    return result, candidate["handoff_candidate_sha256"]


def test_campaign_round_trip_and_zero_authority():
    cases, reference = _cases()
    value = campaign.build_typing_execution_handoff_candidate_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_candidate_sha256=reference)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_execution_handoff_candidate_campaign_v1(value) == value
    assert value["eligible_for_executor"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_campaign_rejects_reference_and_hash_drift():
    cases, reference = _cases(); cases[0]["candidate"]["handoff_candidate_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingExecutionHandoffCandidateCampaignV1Error):
        campaign.build_typing_execution_handoff_candidate_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_candidate_sha256=reference)
    cases, reference = _cases()
    value = campaign.build_typing_execution_handoff_candidate_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_candidate_sha256=reference)
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingExecutionHandoffCandidateCampaignV1Error, match="hash"):
        campaign.parse_typing_execution_handoff_candidate_campaign_v1(changed)


def test_retained_campaign_is_pinned_blocked_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_execution_handoff_candidate_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert value["environment"]["repository_dirty"] is False
    indexed = {item["case"]: item for item in value["cases"]}
    valid = indexed["VALID_COMPLETED_CHAIN"]["candidate"]
    assert valid["status"] == handoff.STATUS
    assert valid["required_blockers"] == list(handoff.REQUIRED_BLOCKERS)
    assert indexed["DETERMINISTIC_REBUILD"]["candidate"] == valid
    assert indexed["NONCOMPLETED_SESSION_REJECTED"]["candidate"] is None
    assert indexed["AUTHORITY_TAMPER_REJECTED"]["candidate"] is None
    assert value["eligible_for_executor"] is False
    assert value["permit_issued"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is False
