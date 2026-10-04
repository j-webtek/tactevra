from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_command_session_ledger_campaign_v1 as campaign
import rocell.application.typing_command_session_ledger_v1 as ledger

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_command_session_ledger_campaign_v1.schema.json").read_text()))
RETAINED = ROOT / "software/ai/eval/typing_command_session_ledger_campaign_v1.json"
RETAINED_FILE_SHA256 = "dcd7ee9dac114c8d0b3fd1716c1e9ab73a842ac24293e027eb9a1581007690cb"
RETAINED_CAMPAIGN_SHA256 = "c7f77b605a400b1b502bbb999a2b82d8c8db4b65446f10c4be5da6e987ee52f0"
RETAINED_SOURCE_COMMIT = "3ead0cc33124ff464922019b08a01aad450a39d8"


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T10:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_typing_command_session_ledger_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core); return core


def _receipt(status, *, revision=0, previous=None):
    terminal = status != ledger.QUEUED
    service = "d" * 64 if revision else None
    completed = status == "SHADOW_COMPLETED"
    return ledger._receipt(
        mission_id="mission", request_id="request", status=status,
        terminal=terminal, revision=revision,
        ingress_fingerprint_sha256="a" * 64,
        request_sha256=None if status in {ledger.LEDGER_CAPACITY_REJECTED,
                                          ledger.ADMISSION_REJECTED} else "b" * 64,
        admission_receipt_sha256=None if status == ledger.LEDGER_CAPACITY_REJECTED else "c" * 64,
        service_receipt_sha256=service,
        shadow_receipt_sha256="e" * 64 if completed else None,
        blocker=(None if status in {ledger.QUEUED, "SHADOW_COMPLETED"} else
                 "LEDGER_CAPACITY_EXHAUSTED" if status == ledger.LEDGER_CAPACITY_REJECTED else "blocked"),
        previous_session_receipt_sha256=previous)


def _snapshot(*, retained=1, queued=0, terminal=1, replay=0, conflicts=0, capacity=0):
    core = {"schema": ledger.SNAPSHOT_SCHEMA, "maximum_sessions": 8,
            "retained_sessions": retained, "queued_sessions": queued,
            "terminal_sessions": terminal, "duplicate_replays": replay,
            "conflicting_duplicates": conflicts, "capacity_rejections": capacity,
            "request_ids": ["request"] if retained else [],
            "gateway_snapshot_sha256": "f" * 64,
            "automatic_retry_allowed": False, "executor_attached": False,
            "controller_opened": False, "transport_opened": False,
            "controller_commands": [], "hardware_commands_generated": 0,
            "hardware_access": False, "physical_authority": False}
    return {**core, "ledger_snapshot_sha256": ledger._sha(core)}


def _cases():
    result = []
    specifications = [
        ("SHADOW_COMPLETED", "TERMINAL_RECORDED"),
        (ledger.QUEUED, "IDENTICAL_RECEIPT_REPLAYED"),
        ("CANCELED_BEFORE_ADMISSION", "TERMINAL_RECORDED"),
        ("STALE_GENERATION_REJECTED", "TERMINAL_RECORDED"),
        (ledger.ADMISSION_REJECTED, "TERMINAL_RECORDED"),
        (ledger.LEDGER_CAPACITY_REJECTED, "TERMINAL_NOT_RETAINED"),
        (None, "CONFLICT_REJECTED"),
        ("SHADOW_COMPLETED", "IDENTICAL_RECEIPT_REPLAYED"),
    ]
    for name, (status, observed) in zip(campaign.CASES, specifications):
        initial_status = (ledger.ADMISSION_REJECTED if name == "ADMISSION_REJECTION"
                          else ledger.LEDGER_CAPACITY_REJECTED if name == "CAPACITY_REJECTION"
                          else ledger.QUEUED)
        initial = _receipt(initial_status)
        if status is None: outcome = None
        elif status == initial_status: outcome = initial
        else: outcome = _receipt(status, revision=1,
                                 previous=initial["session_receipt_sha256"])
        result.append({"case": name, "initial_receipt": initial,
                       "outcome_receipt": outcome, "observed": observed,
                       "ledger_snapshot": _snapshot(queued=int(initial_status == ledger.QUEUED and status in {ledger.QUEUED, None}), terminal=int(not (initial_status == ledger.QUEUED and status in {ledger.QUEUED, None}))),
                       "chain_validated": True})
    return result


def test_campaign_round_trip_and_zero_authority():
    value = campaign.build_typing_command_session_ledger_campaign_v1(
        _cases(), campaign_id="campaign", environment=_environment())
    VALIDATOR.validate(value)
    assert campaign.parse_typing_command_session_ledger_campaign_v1(value) == value
    assert value["admission_to_terminal_chain_preserved"] is True
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_campaign_rejects_chain_and_hash_drift():
    cases = _cases(); cases[0]["outcome_receipt"]["previous_session_receipt_sha256"] = "0" * 64
    with pytest.raises(campaign.TypingCommandSessionLedgerCampaignV1Error):
        campaign.build_typing_command_session_ledger_campaign_v1(
            cases, campaign_id="campaign", environment=_environment())
    value = campaign.build_typing_command_session_ledger_campaign_v1(
        _cases(), campaign_id="campaign", environment=_environment())
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingCommandSessionLedgerCampaignV1Error, match="hash"):
        campaign.parse_typing_command_session_ledger_campaign_v1(changed)


def test_retained_campaign_is_pinned_hash_chained_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_command_session_ledger_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert value["environment"]["repository_dirty"] is False
    indexed = {item["case"]: item for item in value["cases"]}
    assert indexed["COMPLETED_CHAIN"]["outcome_receipt"]["status"] == "SHADOW_COMPLETED"
    assert indexed["IDEMPOTENT_REPLAY"]["initial_receipt"] == indexed["IDEMPOTENT_REPLAY"]["outcome_receipt"]
    assert indexed["CANCELED_CHAIN"]["outcome_receipt"]["status"] == "CANCELED_BEFORE_ADMISSION"
    assert indexed["STALE_CHAIN"]["outcome_receipt"]["status"] == "STALE_GENERATION_REJECTED"
    assert indexed["CONFLICTING_DUPLICATE_REJECTION"]["outcome_receipt"] is None
    assert indexed["TERMINAL_LOOKUP_REPLAY"]["observed"] == "IDENTICAL_RECEIPT_REPLAYED"
    assert value["automatic_retry_allowed"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is False
