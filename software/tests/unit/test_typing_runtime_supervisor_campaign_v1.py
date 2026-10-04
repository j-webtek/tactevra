from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_runtime_supervisor_campaign_v1 as campaign
from rocell.application.typing_runtime_supervisor_v1 import FULL_SOLVE_ONLY, REQUALIFICATION_REQUIRED, WARM

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_runtime_supervisor_campaign_v1.schema.json").read_text()))
RETAINED = ROOT / "software/ai/eval/typing_runtime_supervisor_campaign_v1.json"
RETAINED_FILE_SHA256 = "7425d80e772a3111ec4570dd05199e092b1cb71440d9da85f0960aea287f3668"
RETAINED_CAMPAIGN_SHA256 = "6cfc3e51d8ee016ab901d12123c1366c6b6ad456dfb4acd85f8bd2927f234334"
RETAINED_SOURCE_COMMIT = "72bdfe8643a934773312b61e6f61c9121e269fbd"


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T08:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_typing_runtime_supervisor_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core); return core


def _cases(reference="a" * 64):
    states = [(WARM, "QUALIFIED_PROFILE", True, True, None),
              (FULL_SOLVE_ONLY, "STARTUP_PROFILE_MISMATCH", True, False, "SHADOW_COMPLETED"),
              (REQUALIFICATION_REQUIRED, "SOURCES_RELOADED", True, False, "STALE_GENERATION_REJECTED"),
              (REQUALIFICATION_REQUIRED, "SERVICE_RESTARTED", True, False, "STALE_GENERATION_REJECTED"),
              (FULL_SOLVE_ONLY, "EXPLICIT_FULL_SOLVE_CONTINUATION", True, False, "SHADOW_COMPLETED"),
              (WARM, "QUALIFIED_PROFILE", True, True, "SHADOW_COMPLETED"),
              (REQUALIFICATION_REQUIRED, "INVALIDATED", False, False, None)]
    zero = {"lookups": 0, "hits": 0, "misses": 0, "stores": 0, "capacity_skips": 0}
    result = []
    for name, (state, reason, active, reuse, status) in zip(campaign.CASES, states):
        match = name in {"STARTUP_MISMATCH_FULL_SOLVE", "QUALIFIED_REPLACEMENT_WARM"}
        reject = name in {"RELOAD_REQUIRES_REQUALIFICATION", "RESTART_REQUIRES_REQUALIFICATION", "INVALIDATION_TERMINAL"}
        result.append({"case": name, "state": state, "state_reason": reason,
                       "active": active, "exact_reuse_enabled": reuse, "status": status,
                       "submission_rejection": "blocked" if reject else None,
                       "cache_counters": dict(zero), "reference_equivalent": match,
                       "shadow_receipt_sha256": reference if match else None,
                       "automatic_retries": 0, "snapshot_sha256": "b" * 64})
    return result


def test_supervisor_campaign_round_trip_and_zero_authority():
    reference = "a" * 64
    value = campaign.build_typing_runtime_supervisor_campaign_v1(
        _cases(reference), campaign_id="campaign", environment=_environment(),
        reference_shadow_receipt_sha256=reference)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_runtime_supervisor_campaign_v1(value) == value
    assert value["new_work_blocked_while_requalification_required"] is True
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_supervisor_campaign_rejects_state_retry_and_hash_drift():
    cases = _cases(); cases[2]["state"] = WARM
    with pytest.raises(campaign.TypingRuntimeSupervisorCampaignV1Error, match="outcome"):
        campaign.build_typing_runtime_supervisor_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_shadow_receipt_sha256="a" * 64)
    cases = _cases(); cases[4]["automatic_retries"] = 1
    with pytest.raises(campaign.TypingRuntimeSupervisorCampaignV1Error, match="evidence"):
        campaign.build_typing_runtime_supervisor_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_shadow_receipt_sha256="a" * 64)
    value = campaign.build_typing_runtime_supervisor_campaign_v1(
        _cases(), campaign_id="campaign", environment=_environment(),
        reference_shadow_receipt_sha256="a" * 64)
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingRuntimeSupervisorCampaignV1Error, match="hash"):
        campaign.parse_typing_runtime_supervisor_campaign_v1(changed)


def test_retained_supervisor_campaign_is_pinned_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_runtime_supervisor_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert value["environment"]["repository_dirty"] is False
    indexed = {item["case"]: item for item in value["cases"]}
    assert indexed["QUALIFIED_WARM_START"]["state"] == WARM
    assert indexed["STARTUP_MISMATCH_FULL_SOLVE"]["state"] == FULL_SOLVE_ONLY
    assert indexed["RELOAD_REQUIRES_REQUALIFICATION"]["state"] == REQUALIFICATION_REQUIRED
    assert indexed["RESTART_REQUIRES_REQUALIFICATION"]["state"] == REQUALIFICATION_REQUIRED
    assert indexed["QUALIFIED_REPLACEMENT_WARM"]["reference_equivalent"] is True
    assert all(item["automatic_retries"] == 0 for item in value["cases"])
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is False
