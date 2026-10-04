from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.operational_latency_reference_v1 as reference
from rocell.application.operational_latency_trace_v1 import (
    build_operational_latency_trace_v1,
)


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/operational_latency_reference_v1.json"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/operational_latency_reference_v1.schema.json"
).read_text(encoding="utf-8")))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _environment() -> dict:
    core = {
        "schema": reference.ENVIRONMENT_SCHEMA,
        "captured_at_utc": "2026-09-29T18:00:00Z",
        "repository_commit": "a" * 40,
        "repository_dirty": False,
        "python_version": "3.13.7",
        "python_implementation": "CPython",
        "platform_system": "Windows",
        "platform_release": "11",
        "platform_machine": "AMD64",
        "logical_cpu_count": 16,
        "perf_counter_resolution_ns": 100,
        "benchmark_entrypoint": "software/scripts/run_operational_latency_reference_v1.py",
    }
    return {**core, "environment_sha256": reference._sha(core)}


def _trace(run_class: str, index: int) -> dict:
    milestones = [
        {"milestone_id": milestone, "monotonic_ns": index * 1_000_000 + offset * 10_000}
        for offset, milestone in enumerate((
            "T0_REQUEST_RECEIVED", "T1_INTENT_SEALED", "T2_PERCEPTION_SEALED",
            "T3_BATCH_EMITTED", "T4_BATCH_ADMITTED", "T5_FIRST_PLAN_READY",
        ))
    ]
    return build_operational_latency_trace_v1(
        milestones, trace_id=f"fixture-{run_class.lower()}-{index:03d}",
        evidence_class="HOST_MEASURED_OFFLINE", run_class=run_class,
        cache_outcome="NOT_APPLICABLE", outcome="BLOCKED", action_count=5,
        blocker_codes=["PERMIT_NOT_REQUESTED_OFFLINE_REFERENCE"],
        correlation={
            "request_sha256": _digest("request"),
            "session_sha256": _digest(f"{run_class}-{index}"),
            "ai_batch_sha256": _digest("batch"),
            "plan_sha256": _digest("plan"),
            "configuration_epoch_sha256": None,
            "controller_session_sha256": None,
            "result_sha256": _digest("result"),
        },
        resource_counts={
            "artifact_bytes": 1000, "ik_solve_count": 0,
            "screening_sample_count": 100, "controller_command_count": 0,
            "hardware_write_count": 0, "physical_movement_count": 0,
        },
        decision_sha256=_digest("decision"),
    )


def _report() -> dict:
    traces = [
        _trace(run_class, index)
        for run_class in ("COLD", "WARM")
        for index in range(reference.MINIMUM_RUNS_PER_CLASS)
    ]
    return reference.build_operational_latency_reference_v1(
        traces, report_id="e0-reference-fixture", environment=_environment(),
    )


def _rehash(report: dict) -> None:
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    report["report_sha256"] = reference._sha(unsigned)


def test_reference_is_schema_valid_complete_and_zero_authority():
    report = _report()
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(reference.parse_operational_latency_reference_v1(report)) == report
    assert report["trace_count"] == 40
    assert report["summaries"]["COLD"]["trace_count"] == 20
    assert report["summaries"]["WARM"]["trace_count"] == 20
    assert report["summaries"]["ALL"]["durations_ns"]["batch_to_admission_ns"]["p95"] == 10_000
    assert report["terminal_scope"] == "T5_FIRST_PLAN_READY_NO_PERMIT_REQUESTED"
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_retained_reference_binds_clean_source_and_real_host_measurements():
    report = json.loads(RETAINED.read_text(encoding="utf-8"))
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(reference.parse_operational_latency_reference_v1(report)) == report
    assert report["report_sha256"] == (
        "0c9e960bd00a8336ff32d7b099be7e21835e9c559e5a47894805a5b1157d9416"
    )
    assert report["environment"]["repository_commit"] == (
        "c633c04fb17d42de5d7466319307db4e536b1120"
    )
    assert report["environment"]["repository_dirty"] is False
    assert report["trace_count"] == 40
    assert all(
        trace["terminal_milestone"] == "T5_FIRST_PLAN_READY"
        and trace["resource_counts"]["ik_solve_count"] == 0
        and trace["resource_counts"]["controller_command_count"] == 0
        and trace["resource_counts"]["hardware_write_count"] == 0
        and trace["resource_counts"]["physical_movement_count"] == 0
        for trace in report["traces"]
    )


@pytest.mark.parametrize("mutation,match", (
    ("authority", "authority"),
    ("summary", "derivation"),
    ("environment", "environment hash"),
    ("duplicate", "duplicated"),
    ("coverage", "trace count|coverage"),
))
def test_rehashed_semantic_mutations_fail_closed(mutation: str, match: str):
    report = copy.deepcopy(_report())
    if mutation == "authority":
        report["physical_authority"] = True
    elif mutation == "summary":
        report["summaries"]["WARM"]["durations_ns"]["batch_to_admission_ns"]["p95"] += 1
    elif mutation == "environment":
        report["environment"]["python_version"] = "different"
    elif mutation == "duplicate":
        report["traces"][1]["trace_id"] = report["traces"][0]["trace_id"]
        unsigned = {key: value for key, value in report["traces"][1].items() if key != "trace_sha256"}
        report["traces"][1]["trace_sha256"] = reference._sha(unsigned)
    else:
        report["traces"] = [trace for trace in report["traces"] if trace["run_class"] == "COLD"]
        report["trace_count"] = len(report["traces"])
    _rehash(report)
    with pytest.raises(reference.OperationalLatencyReferenceV1Error, match=match):
        reference.parse_operational_latency_reference_v1(report)


def test_plain_report_hash_tampering_rejects():
    report = _report()
    report["trace_count"] -= 1
    with pytest.raises(reference.OperationalLatencyReferenceV1Error, match="hash mismatch"):
        reference.parse_operational_latency_reference_v1(report)


def test_malformed_trace_collection_fails_closed():
    report = _report()
    report["traces"] = None
    _rehash(report)
    with pytest.raises(reference.OperationalLatencyReferenceV1Error, match="sequence"):
        reference.parse_operational_latency_reference_v1(report)
