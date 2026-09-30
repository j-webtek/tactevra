from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_shadow_artifact_store_campaign_v1 as campaign
from rocell.application.typing_shadow_artifact_store_v1 import (
    TypingShadowArtifactStoreV1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_shadow_artifact_store_campaign_v1.schema.json"
).read_text(encoding="utf-8")))
RETAINED = ROOT / "software/ai/eval/typing_shadow_artifact_store_campaign_v1.json"
RETAINED_FILE_SHA256 = "ef2f445f811739715f2145a6f9fa5441791f7bcbd2c011616eea1c6970264de6"
RETAINED_CAMPAIGN_SHA256 = "944492b10f1218dd15b542570fb5d7d613deaeb34da37242aae5a2bbb0ecdba0"
RETAINED_SOURCE_COMMIT = "69ef09bab0b62cceb2ab78b35e4f3c733137fd8d"


def _environment():
    core = {
        "schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-30T12:00:00Z",
        "repository_commit": "a" * 40, "repository_dirty": False,
        "python_version": "3.10.10", "python_implementation": "CPython",
        "platform_system": "Windows", "platform_release": "10",
        "platform_machine": "AMD64", "logical_cpu_count": 24,
        "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": (
            "software/scripts/run_typing_shadow_artifact_store_campaign_v1.py"
        ),
    }
    core["environment_sha256"] = campaign._sha(core)
    return core


def _artifact():
    ledger, supervisor = runner._ledger()
    ledger.submit("mission-campaign", "campaign", runner._inputs(ledger, "campaign"))
    ledger.run_next_shadow()
    artifact = ledger.shadow_artifact("campaign")
    supervisor.invalidate()
    return artifact


def _cases():
    artifact = _artifact()
    store = TypingShadowArtifactStoreV1()
    store.put("campaign", artifact)
    result = []
    retained = {"RUNTIME_RETENTION", "REPEAT_RETRIEVAL"}
    for name in campaign.CASES:
        result.append({
            "case": name, "observed": campaign.EXPECTED[name],
            "artifact": artifact if name in retained else None,
            "error": None if name in retained else "rejected",
            "store_snapshot": store.snapshot(),
            "zero_authority_validated": True,
        })
    return result, artifact["typing_shadow_pipeline_sha256"]


def test_campaign_round_trip_and_zero_authority():
    cases, reference = _cases()
    value = campaign.build_typing_shadow_artifact_store_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_artifact_sha256=reference,
    )
    VALIDATOR.validate(value)
    assert campaign.parse_typing_shadow_artifact_store_campaign_v1(value) == value
    assert value["mutable_replacement_allowed"] is False
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_campaign_rejects_reference_and_hash_drift():
    cases, reference = _cases()
    cases[0]["artifact"]["typing_shadow_pipeline_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingShadowArtifactStoreCampaignV1Error):
        campaign.build_typing_shadow_artifact_store_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_artifact_sha256=reference,
        )
    cases, reference = _cases()
    value = campaign.build_typing_shadow_artifact_store_campaign_v1(
        cases, campaign_id="campaign", environment=_environment(),
        reference_artifact_sha256=reference,
    )
    changed = copy.deepcopy(value)
    changed["campaign_sha256"] = "f" * 64
    with pytest.raises(
        campaign.TypingShadowArtifactStoreCampaignV1Error, match="hash"
    ):
        campaign.parse_typing_shadow_artifact_store_campaign_v1(changed)


def test_retained_campaign_is_pinned_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_shadow_artifact_store_campaign_v1(value) == value
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert value["environment"]["repository_dirty"] is False
    indexed = {item["case"]: item for item in value["cases"]}
    retained = indexed["RUNTIME_RETENTION"]["artifact"]
    assert indexed["REPEAT_RETRIEVAL"]["artifact"] == retained
    assert indexed["WRONG_HASH_REJECTED"]["artifact"] is None
    assert indexed["CANCELED_HAS_NO_ARTIFACT"]["artifact"] is None
    assert value["hardware_writes"] == value["physical_movements"] == 0
    assert value["physical_authority"] is False
