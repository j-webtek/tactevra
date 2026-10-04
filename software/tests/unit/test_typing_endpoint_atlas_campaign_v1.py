from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_endpoint_atlas_campaign_v1 as campaign


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/typing_endpoint_atlas_campaign_v1.json"
RETAINED_FILE_SHA256 = (
    "af8702f0e4b8470fb4957a567baba596028f3ea6c9f084d75ca56b65ef5cce77"
)
RETAINED_CAMPAIGN_SHA256 = (
    "ac623147c7bf7e257f7c6892919ec21d632ab18b9455caa32cd039d86f9450a4"
)
RETAINED_SOURCE_COMMIT = "9b9bd0a71f72d2a61fc2e607843383c8657cf944"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_endpoint_atlas_campaign_v1.schema.json"
).read_text(encoding="utf-8")))


def _runner_module():
    path = ROOT / "software/scripts/run_typing_endpoint_atlas_campaign_v1.py"
    spec = importlib.util.spec_from_file_location("endpoint_atlas_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _environment() -> dict:
    core = {
        "schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-29T20:00:00Z",
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
            "software/scripts/run_typing_endpoint_atlas_campaign_v1.py"
        ),
    }
    from rocell.application.operational_latency_reference_v1 import _sha
    return {**core, "environment_sha256": _sha(core)}


@pytest.fixture(scope="module")
def report() -> dict:
    runner = _runner_module()
    return campaign.build_typing_endpoint_atlas_campaign_v1(
        runner._campaign_cases(),
        campaign_id="test-typing-endpoint-atlas",
        environment=_environment(),
    )


def _rehash(value: dict) -> None:
    unsigned = dict(value)
    unsigned.pop("campaign_sha256", None)
    value["campaign_sha256"] = campaign._sha(unsigned)


def test_campaign_schema_derivation_and_zero_authority(report: dict) -> None:
    VALIDATOR.validate(report)
    assert campaign.parse_typing_endpoint_atlas_campaign_v1(report) == report
    assert [case["case_id"] for case in report["cases"]] == list(
        campaign.CASE_IDS
    )
    assert all(
        case["target_ids"] == list(campaign.CASE_TARGETS[case["case_id"]])
        for case in report["cases"]
    )
    assert all(
        case["reference_receipt_sha256"]
        == case["observed_receipt_sha256"]
        for case in report["cases"]
    )
    aggregate = report["aggregate"]
    assert aggregate["route_count"] == 5
    assert aggregate["endpoint_observation_count"] == sum(
        case["observation"]["endpoint_observation_count"]
        for case in report["cases"]
    )
    assert (
        aggregate["stable_endpoint_count"]
        + aggregate["variable_endpoint_count"]
        == aggregate["unique_endpoint_count"]
    )
    assert (
        aggregate["stable_reuse_candidate_count"]
        + aggregate["variable_reuse_candidate_count"]
        == aggregate["repeated_endpoint_identity_count"]
    )
    assert report["decision_hashes_unchanged"] is True
    assert report["atlas_use_authorized"] is False
    assert report["warm_start_authorized"] is False
    assert report["diagnostics_used_for_admission"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


@pytest.mark.parametrize("mutation,match", (
    ("case-order", "case order"),
    ("targets", "case targets"),
    ("receipt", "decision receipt"),
    ("observation", "observation hash"),
    ("aggregate", "derivation"),
    ("authority", "derivation"),
))
def test_rehashed_campaign_mutations_fail_closed(
    report: dict, mutation: str, match: str,
) -> None:
    candidate = copy.deepcopy(report)
    if mutation == "case-order":
        candidate["cases"][0], candidate["cases"][1] = (
            candidate["cases"][1], candidate["cases"][0]
        )
    elif mutation == "targets":
        candidate["cases"][0]["target_ids"] = ["H", "H"]
    elif mutation == "receipt":
        candidate["cases"][0]["observed_receipt_sha256"] = "f" * 64
    elif mutation == "observation":
        candidate["cases"][0]["observation"][
            "observed_sample_count"
        ] += 1
    elif mutation == "aggregate":
        candidate["aggregate"]["stable_endpoint_count"] += 1
    else:
        candidate["warm_start_authorized"] = True
    _rehash(candidate)
    with pytest.raises(campaign.TypingEndpointAtlasCampaignV1Error, match=match):
        campaign.parse_typing_endpoint_atlas_campaign_v1(candidate)


def test_retained_campaign_identity_when_installed() -> None:
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    value = json.loads(raw)
    assert value["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert value["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    VALIDATOR.validate(value)
    campaign.parse_typing_endpoint_atlas_campaign_v1(value)
