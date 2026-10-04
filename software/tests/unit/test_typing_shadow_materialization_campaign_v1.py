from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_shadow_materialization_campaign_v1 as campaign
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_shadow_materialization_campaign_v1.schema.json"
).read_text(encoding="utf-8")))
RETAINED = ROOT / "software/ai/eval/typing_shadow_materialization_campaign_v1.json"
RETAINED_FILE_SHA256 = "877d6cc106fcf8e6b855a1d54ac263ea72a1d7a70ec934831b3f47dc63f380f5"
RETAINED_CAMPAIGN_SHA256 = "6f79d08427d1182c1c4af1096ef192654bc24ccc918c0c309e0ca94fd7b5769d"
RETAINED_SOURCE_COMMIT = "81d25e1a06484b7c89f6048e5795c8372769dcbb"


def _environment():
    core = {
        "schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-30T14:00:00Z",
        "repository_commit": "a" * 40, "repository_dirty": False,
        "python_version": "3.10.10", "python_implementation": "CPython",
        "platform_system": "Windows", "platform_release": "10",
        "platform_machine": "AMD64", "logical_cpu_count": 24,
        "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": (
            "software/scripts/run_typing_shadow_materialization_campaign_v1.py"
        ),
    }
    core["environment_sha256"] = campaign._sha(core)
    return core


def _cases():
    ledger, supervisor = runner._ledger()
    ledger.submit("mission-case", "case", runner._inputs(ledger, "case"))
    ledger.run_next_shadow()
    bundle = ledger.shadow_materialization("case")
    accepted = {
        "COMPLETED_MATERIALIZATION", "REPEAT_RETRIEVAL",
        "POST_INVALIDATION_AUDIT_RETRIEVAL",
    }
    cases = [{
        "case": name, "observed": campaign.EXPECTED[name],
        "materialization": bundle if name in accepted else None,
        "error": None if name in accepted else "rejected",
        "ledger_snapshot": ledger.snapshot(),
        "zero_authority_validated": True,
    } for name in campaign.CASES]
    supervisor.invalidate()
    return cases, bundle["materialization_sha256"]


def test_campaign_round_trip_and_zero_authority():
    cases, reference = _cases()
    value = campaign.build_typing_shadow_materialization_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_materialization_sha256=reference,
    )
    VALIDATOR.validate(value)
    assert campaign.parse_typing_shadow_materialization_campaign_v1(value) == value
    assert value["stage_count"] == 5
    assert value["permit_review_ready"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_campaign_rejects_reference_and_hash_drift():
    cases, reference = _cases()
    cases[0]["materialization"]["materialization_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingShadowMaterializationCampaignV1Error):
        campaign.build_typing_shadow_materialization_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_materialization_sha256=reference,
        )
    cases, reference = _cases()
    value = campaign.build_typing_shadow_materialization_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_materialization_sha256=reference,
    )
    changed = copy.deepcopy(value)
    changed["campaign_sha256"] = "f" * 64
    with pytest.raises(
        campaign.TypingShadowMaterializationCampaignV1Error, match="hash"
    ):
        campaign.parse_typing_shadow_materialization_campaign_v1(changed)


@pytest.mark.skipif(RETAINED_SOURCE_COMMIT == "PENDING", reason="framework phase")
def test_retained_campaign_is_pinned_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_shadow_materialization_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    indexed = {item["case"]: item for item in value["cases"]}
    reference = indexed["COMPLETED_MATERIALIZATION"]["materialization"]
    assert indexed["REPEAT_RETRIEVAL"]["materialization"] == reference
    assert indexed["POST_INVALIDATION_AUDIT_RETRIEVAL"]["materialization"] == reference
    assert indexed["TAMPER_REJECTED"]["materialization"] is None
    assert indexed["STALE_HAS_NO_MATERIALIZATION"]["materialization"] is None
    assert value["permit_review_ready"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is False
