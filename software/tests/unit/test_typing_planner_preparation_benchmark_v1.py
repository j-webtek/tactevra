from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_planner_preparation_benchmark_v1 as benchmark


ROOT = Path(__file__).resolve().parents[3]
RETAINED = (
    ROOT / "software/ai/eval/typing_planner_preparation_benchmark_v1.json"
)
RETAINED_FILE_SHA256 = (
    "1dc24c0232422e1693f6165cc10e57e1422a4de599e189307e8e641f09039318"
)
RETAINED_REPORT_SHA256 = (
    "b9650cc66a0171b2d8902e8568d17ae84df3d7276f9d9c853debd7bf0cf4fca2"
)
RETAINED_SOURCE_COMMIT = "781cb1d34697d93476f7944b55b04c024003dbf4"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT
    / "software/ai/schemas/typing_planner_preparation_benchmark_v1.schema.json"
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
        "benchmark_entrypoint": (
            "software/scripts/run_typing_planner_preparation_benchmark_v1.py"
        ),
    }
    from rocell.application.operational_latency_reference_v1 import _sha
    return {**core, "environment_sha256": _sha(core)}


def _samples() -> list[dict]:
    receipt = _digest("same-receipt")
    stages = _digest("same-stage-hashes")
    samples = []
    for path in benchmark.PATHS:
        for index in range(20):
            samples.append({
                "sequence": len(samples),
                "path": path,
                "duration_ns": (
                    40_000_000 if path == benchmark.PATHS[0] else 35_000_000
                ) + index,
                "receipt_sha256": receipt,
                "stage_hashes_sha256": stages,
            })
    return samples


def _invalidations() -> list[dict]:
    return [
        {"case": case, "status": "BLOCKED"}
        for case in benchmark.INVALIDATION_CASES
    ]


def _report() -> dict:
    return benchmark.build_typing_planner_preparation_benchmark_v1(
        _samples(),
        report_id="e1-preparation-benchmark-fixture",
        environment=_environment(),
        context_epoch_sha256=_digest("epoch"),
        lease_sha256=_digest("lease"),
        preparation_sha256=_digest("preparation"),
        model_sha256=_digest("model"),
        preparation_duration_ns=1_000_000,
        invalidation_results=_invalidations(),
    )


def _rehash(report: dict) -> None:
    unsigned = {
        key: value for key, value in report.items() if key != "report_sha256"
    }
    report["report_sha256"] = benchmark._sha(unsigned)


def test_benchmark_is_schema_valid_equivalent_and_zero_authority():
    report = _report()
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(
        benchmark.parse_typing_planner_preparation_benchmark_v1(report)
    ) == report
    assert report["semantic_equivalence"]["all_outputs_identical"] is True
    assert report["summaries"]["p50_reduction_ns"] > 0
    assert report["invalidation_results"] == _invalidations()
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is False
    assert report["physical_authority"] is False
    assert report["controller_commands"] == []


def test_retained_clean_commit_benchmark_is_exact_and_fail_closed():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(
        benchmark.parse_typing_planner_preparation_benchmark_v1(report)
    ) == report
    assert report["report_sha256"] == RETAINED_REPORT_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert report["environment"]["repository_dirty"] is False
    assert report["preparation_duration_ns"] == 1_189_800
    assert len(report["samples"]) == 40
    assert report["semantic_equivalence"]["all_outputs_identical"] is True
    assert report["invalidation_results"] == _invalidations()
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is False
    assert report["physical_authority"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0


@pytest.mark.parametrize("mutation,match", (
    ("decision", "decisions differ"),
    ("stage", "decisions differ"),
    ("invalidation", "invalidation coverage"),
    ("summary", "derivation"),
    ("preparation", "preparation duration"),
    ("authority", "authority"),
))
def test_rehashed_semantic_mutations_fail_closed(mutation: str, match: str):
    report = copy.deepcopy(_report())
    if mutation == "decision":
        report["samples"][-1]["receipt_sha256"] = _digest("different")
    elif mutation == "stage":
        report["samples"][-1]["stage_hashes_sha256"] = _digest("different")
    elif mutation == "invalidation":
        report["invalidation_results"][-1]["status"] = "PASSED"
    elif mutation == "summary":
        report["summaries"]["p95_reduction_ns"] += 1
    elif mutation == "preparation":
        report["preparation_duration_ns"] = -1
    else:
        report["physical_authority"] = True
    _rehash(report)
    with pytest.raises(
        benchmark.TypingPlannerPreparationBenchmarkV1Error, match=match
    ):
        benchmark.parse_typing_planner_preparation_benchmark_v1(report)
