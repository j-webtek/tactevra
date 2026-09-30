from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_execution_handoff_assembler_campaign_v1 as campaign
from rocell.application.typing_execution_handoff_assembler_v1 import (
    assemble_typing_execution_handoff_candidate_v1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_execution_handoff_assembler_campaign_v1.schema.json"
).read_text(encoding="utf-8")))
RETAINED = ROOT / "software/ai/eval/typing_execution_handoff_assembler_campaign_v1.json"
RETAINED_FILE_SHA256 = "fd9c6135f059aceebc7f03e0c3ae9b9e35293fa0afaf36f63c4023415e528ada"
RETAINED_CAMPAIGN_SHA256 = "62ab46d572c303db03f8137d82a4e09087c8145e3eb28e524dd73fc11e18d18a"
RETAINED_SOURCE_COMMIT = "5fb4801956c800dba75c56722911acaf99493fb2"


def _environment():
    core = {
        "schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-30T13:00:00Z",
        "repository_commit": "a" * 40, "repository_dirty": False,
        "python_version": "3.10.10", "python_implementation": "CPython",
        "platform_system": "Windows", "platform_release": "10",
        "platform_machine": "AMD64", "logical_cpu_count": 24,
        "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": (
            "software/scripts/run_typing_execution_handoff_assembler_campaign_v1.py"
        ),
    }
    core["environment_sha256"] = campaign._sha(core)
    return core


def _cases():
    ledger, supervisor = runner._ledger()
    ledger.submit("mission-case", "case", runner._inputs(ledger, "case"))
    ledger.run_next_shadow()
    candidate = assemble_typing_execution_handoff_candidate_v1(ledger, "case")
    result = []
    accepted = {
        "COMPLETED_ASSEMBLY", "REPEAT_ASSEMBLY",
        "POST_INVALIDATION_AUDIT_ASSEMBLY",
    }
    for name in campaign.CASES:
        result.append({
            "case": name, "observed": campaign.EXPECTED[name],
            "candidate": candidate if name in accepted else None,
            "error": None if name in accepted else "rejected",
            "ledger_snapshot": ledger.snapshot(),
            "artifact_store_snapshot": ledger.artifact_store_snapshot(),
            "zero_authority_validated": True,
        })
    supervisor.invalidate()
    return result, candidate["handoff_candidate_sha256"]


def test_campaign_round_trip_and_zero_authority():
    cases, reference = _cases()
    value = campaign.build_typing_execution_handoff_assembler_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_candidate_sha256=reference,
    )
    VALIDATOR.validate(value)
    assert campaign.parse_typing_execution_handoff_assembler_campaign_v1(
        value
    ) == value
    assert value["planner_rerun_required_for_assembly"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_campaign_rejects_reference_and_hash_drift():
    cases, reference = _cases()
    cases[0]["candidate"]["handoff_candidate_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingExecutionHandoffAssemblerCampaignV1Error):
        campaign.build_typing_execution_handoff_assembler_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_candidate_sha256=reference,
        )
    cases, reference = _cases()
    value = campaign.build_typing_execution_handoff_assembler_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_candidate_sha256=reference,
    )
    changed = copy.deepcopy(value)
    changed["campaign_sha256"] = "f" * 64
    with pytest.raises(
        campaign.TypingExecutionHandoffAssemblerCampaignV1Error, match="hash"
    ):
        campaign.parse_typing_execution_handoff_assembler_campaign_v1(changed)


def test_retained_campaign_is_pinned_blocked_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_execution_handoff_assembler_campaign_v1(
        value
    ) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    indexed = {item["case"]: item for item in value["cases"]}
    reference = indexed["COMPLETED_ASSEMBLY"]["candidate"]
    assert indexed["REPEAT_ASSEMBLY"]["candidate"] == reference
    assert indexed["POST_INVALIDATION_AUDIT_ASSEMBLY"]["candidate"] == reference
    assert indexed["QUEUED_REJECTED"]["candidate"] is None
    assert indexed["UNKNOWN_REJECTED"]["candidate"] is None
    assert value["eligible_for_executor"] is value["permit_issued"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is False
