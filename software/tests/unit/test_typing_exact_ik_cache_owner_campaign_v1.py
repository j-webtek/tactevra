from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_exact_ik_cache_owner_campaign_v1 as campaign


ROOT = Path(__file__).resolve().parents[3]
RETAINED = (
    ROOT / "software/ai/eval/typing_exact_ik_cache_owner_campaign_v1.json"
)
RETAINED_FILE_SHA256 = (
    "a644c5b46d6c15d70a3d9a207530620d3e89deb4058baa5937fc3672a016553a"
)
RETAINED_CAMPAIGN_SHA256 = (
    "1f9b14fcd4fd76f068902efcf6ac3944435b051aed1b828f4ba3eec82e5200eb"
)
RETAINED_SOURCE_COMMIT = "a07ca2730f04dfccb5f072e210f8413e5c64e198"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT
    / "software/ai/schemas/typing_exact_ik_cache_owner_campaign_v1.schema.json"
).read_text(encoding="utf-8")))


def _environment() -> dict:
    core = {
        "schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-29T23:00:00Z",
        "repository_commit": "a" * 40,
        "repository_dirty": False,
        "python_version": "3.10.10",
        "python_implementation": "CPython",
        "platform_system": "Windows",
        "platform_release": "10",
        "platform_machine": "AMD64",
        "logical_cpu_count": 24,
        "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": (
            "software/scripts/run_typing_exact_ik_cache_owner_campaign_v1.py"
        ),
    }
    from rocell.application.operational_latency_reference_v1 import _sha
    return {**core, "environment_sha256": _sha(core)}


def _snapshot(case: str) -> dict:
    expected = campaign._EXPECTED[case]
    cache_core = {
        "schema": "rocell.typing_exact_ik_result_cache_snapshot.v1",
        "context_epoch_sha256": hashlib.sha256(case.encode()).hexdigest(),
        "service_instance_id": f"campaign-{case.lower()}",
        "generation": 0,
        "maximum_entries": 256,
        "entry_count": 0,
        "active": expected["cache"],
        "lookups": 0,
        "hits": 0,
        "misses": 0,
        "stores": 0,
        "capacity_skips": 0,
        "decision_input": False,
        "timing_used_for_admission": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    from rocell.application.typing_exact_ik_result_cache_v1 import _sha as cache_sha
    cache = {**cache_core, "cache_snapshot_sha256": cache_sha(cache_core)}
    owner_core = {
        "schema": "rocell.typing_exact_ik_cache_owner_snapshot.v1",
        "context_epoch_sha256": cache_core["context_epoch_sha256"],
        "service_instance_id": cache_core["service_instance_id"],
        "generation": 0,
        "maximum_entries": 256,
        "active": expected["active"],
        "ready": expected["ready"],
        "runs": 2 if expected["execution"] == "PASSED" else 1,
        "run_failures": 0,
        "reloads": expected["reloads"],
        "restarts": expected["restarts"],
        "retired_caches": int(expected["retired"]),
        "invalidations": expected["invalidations"],
        "refresh_failures": expected["refresh_failures"],
        "cache": cache,
        "decision_input": False,
        "timing_used_for_admission": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    from rocell.application.typing_exact_ik_cache_owner_v1 import _sha as owner_sha
    return {**owner_core, "owner_snapshot_sha256": owner_sha(owner_core)}


def _cases() -> list[dict]:
    receipt = hashlib.sha256(b"same-receipt").hexdigest()
    result = []
    for case in campaign.CASES:
        expected = campaign._EXPECTED[case]
        result.append({
            "case": case,
            "status": "PASS",
            "transition": expected["transition"],
            "old_cache_retired": expected["retired"],
            "execution_status": expected["execution"],
            "receipt_sha256": receipt if expected["receipt"] else None,
            "receipt_matches_reference": expected["receipt"],
            "after_owner_snapshot": _snapshot(case),
        })
    return result


def _report() -> dict:
    return campaign.build_typing_exact_ik_cache_owner_campaign_v1(
        _cases(), campaign_id="owner-campaign-fixture",
        environment=_environment(),
    )


def _rehash(report: dict) -> None:
    unsigned = {
        key: value for key, value in report.items() if key != "campaign_sha256"
    }
    report["campaign_sha256"] = campaign._sha(unsigned)


def test_owner_campaign_is_schema_valid_complete_and_zero_authority():
    report = _report()
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(
        campaign.parse_typing_exact_ik_cache_owner_campaign_v1(report)
    ) == report
    assert [item["case"] for item in report["cases"]] == list(campaign.CASES)
    assert report["all_expected_outcomes"] is True
    assert report["diagnostics_used_for_admission"] is False
    assert report["controller_commands"] == []
    assert report["physical_authority"] is False


def test_retained_owner_campaign_is_exact_complete_and_fail_closed():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(
        campaign.parse_typing_exact_ik_cache_owner_campaign_v1(report)
    ) == report
    assert report["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert report["environment"]["repository_dirty"] is False
    assert [item["case"] for item in report["cases"]] == list(campaign.CASES)
    assert all(item["status"] == "PASS" for item in report["cases"])
    assert report["cases"][0]["after_owner_snapshot"]["runs"] == 2
    assert report["cases"][1]["after_owner_snapshot"]["reloads"] == 1
    assert report["cases"][2]["after_owner_snapshot"]["restarts"] == 1
    assert report["cases"][3]["after_owner_snapshot"]["invalidations"] == 1
    assert report["cases"][4]["after_owner_snapshot"]["refresh_failures"] == 1
    assert report["cases"][5]["after_owner_snapshot"]["refresh_failures"] == 1
    assert report["diagnostics_used_for_admission"] is False
    assert report["controller_opened"] is False
    assert report["transport_opened"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False


@pytest.mark.parametrize("mutation,match", (
    ("order", "case order"),
    ("retirement", "outcome differs"),
    ("execution", "outcome differs"),
    ("snapshot", "owner snapshot is invalid"),
    ("receipt", "successful case receipts differ"),
    ("authority", "authority"),
))
def test_rehashed_owner_campaign_mutations_fail_closed(mutation: str, match: str):
    report = copy.deepcopy(_report())
    if mutation == "order":
        report["cases"][0], report["cases"][1] = (
            report["cases"][1], report["cases"][0]
        )
    elif mutation == "retirement":
        report["cases"][1]["old_cache_retired"] = False
    elif mutation == "execution":
        report["cases"][3]["execution_status"] = "PASSED"
    elif mutation == "snapshot":
        item = report["cases"][1]["after_owner_snapshot"]
        item["reloads"] = 0
        from rocell.application.typing_exact_ik_cache_owner_v1 import _sha
        core = {key: value for key, value in item.items() if key != "owner_snapshot_sha256"}
        item["owner_snapshot_sha256"] = _sha(core)
    elif mutation == "receipt":
        report["cases"][1]["receipt_sha256"] = hashlib.sha256(b"other").hexdigest()
    else:
        report["physical_authority"] = True
    _rehash(report)
    with pytest.raises(
        campaign.TypingExactIkCacheOwnerCampaignV1Error, match=match
    ):
        campaign.parse_typing_exact_ik_cache_owner_campaign_v1(report)
