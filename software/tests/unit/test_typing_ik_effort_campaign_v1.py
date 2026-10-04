from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_ik_effort_campaign_v1 as campaign
from rocell.application.typing_ik_effort_telemetry_v1 import _sha as telemetry_sha


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/typing_ik_effort_campaign_v1.json"
RETAINED_FILE_SHA256 = (
    "876819e727cd40a78a6a368e886540053e30c2ab6e86b3522822b3c1a56096b0"
)
RETAINED_CAMPAIGN_SHA256 = (
    "8d0d31a76ea1c1b264e1aeff4260c5fbd9ea4bd42a097d440c882d8f48ccdd0d"
)
RETAINED_SOURCE_COMMIT = "99ea05af9377e082ff1d564ec210271ccc9caac1"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_ik_effort_campaign_v1.schema.json"
).read_text(encoding="utf-8")))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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
        "benchmark_entrypoint": "software/scripts/run_typing_ik_effort_campaign_v1.py",
    }
    from rocell.application.operational_latency_reference_v1 import _sha
    return {**core, "environment_sha256": _sha(core)}


def _telemetry(case_index: int) -> dict:
    solver_input = _digest("shared" if case_index < 2 else f"input-{case_index}")
    sample = {
        "sequence": 0,
        "solver_input_sha256": solver_input,
        "previous_solution_seed_supplied": False,
        "attempt_count": 4,
        "total_iterations": 12 + case_index,
        "selected_attempt_index": 1,
        "selected_iterations": 3,
        "converged_attempt_count": 4,
        "first_attempt_converged": True,
        "selected_first_attempt": False,
    }
    core = {
        "schema": "rocell.typing_ik_effort_telemetry.v1",
        "typing_trajectory_plan_sha256": _digest(f"plan-{case_index}"),
        "typing_trajectory_ik_screen_sha256": _digest(f"screen-{case_index}"),
        "sample_count": 1,
        "samples": [sample],
        "totals": {
            "attempt_count": 4,
            "total_iterations": 12 + case_index,
            "selected_iterations": 3,
            "converged_attempt_count": 4,
            "previous_solution_seed_supplied_count": 0,
            "first_attempt_converged_count": 1,
            "selected_first_attempt_count": 0,
        },
        "decision_input": False,
        "timing_used_for_admission": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "typing_ik_effort_telemetry_sha256": telemetry_sha(core)}


def _cases() -> list[dict]:
    return [
        {
            "case_id": f"case-{index}",
            "target_ids": [f"T{index}"],
            "receipt_sha256": _digest(f"receipt-{index}"),
            "stage_hashes_sha256": _digest(f"stages-{index}"),
            "telemetry": _telemetry(index),
        }
        for index in range(5)
    ]


def _report() -> dict:
    return campaign.build_typing_ik_effort_campaign_v1(
        _cases(), campaign_id="e2-fixture", environment=_environment()
    )


def _rehash(report: dict) -> None:
    unsigned = {key: value for key, value in report.items() if key != "campaign_sha256"}
    report["campaign_sha256"] = campaign._sha(unsigned)


def test_campaign_is_schema_valid_derived_and_zero_authority():
    report = _report()
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_ik_effort_campaign_v1(report)) == report
    assert report["aggregate"]["waypoint_count"] == 5
    assert report["exact_reuse_analysis"]["repeated_observation_count"] == 1
    assert report["exact_reuse_analysis"]["cache_authorized"] is False
    assert report["telemetry_used_for_admission"] is False
    assert report["physical_authority"] is False


def test_retained_campaign_is_exact_clean_and_zero_authority():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(campaign.parse_typing_ik_effort_campaign_v1(report)) == report
    assert report["campaign_sha256"] == RETAINED_CAMPAIGN_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert report["environment"]["repository_dirty"] is False
    assert report["case_count"] == 5
    assert report["aggregate"] == {
        "waypoint_count": 186,
        "attempt_count": 744,
        "total_iterations": 2393,
        "selected_iterations": 872,
        "converged_attempt_count": 744,
        "first_attempt_converged_count": 186,
        "selected_first_attempt_count": 15,
    }
    assert report["exact_reuse_analysis"] == {
        "solver_input_observation_count": 186,
        "unique_solver_input_count": 48,
        "repeated_observation_count": 138,
        "reused_identity_count": 35,
        "maximum_identity_occurrences": 11,
        "first_convergence_early_exit_equivalent": False,
        "cache_authorized": False,
    }
    assert report["telemetry_used_for_admission"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


@pytest.mark.parametrize("mutation,match", (
    ("telemetry", "telemetry hash"),
    ("aggregate", "derivation"),
    ("reuse", "derivation"),
    ("authority", "authority"),
))
def test_rehashed_campaign_mutations_fail_closed(mutation: str, match: str):
    report = copy.deepcopy(_report())
    if mutation == "telemetry":
        report["cases"][0]["telemetry"]["samples"][0]["total_iterations"] += 1
    elif mutation == "aggregate":
        report["aggregate"]["total_iterations"] += 1
    elif mutation == "reuse":
        report["exact_reuse_analysis"]["cache_authorized"] = True
    else:
        report["physical_authority"] = True
    _rehash(report)
    with pytest.raises(campaign.TypingIkEffortCampaignV1Error, match=match):
        campaign.parse_typing_ik_effort_campaign_v1(report)
