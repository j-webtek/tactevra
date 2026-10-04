from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.context_validation_lease_benchmark_v1 as benchmark


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/context_validation_lease_benchmark_v1.json"
RETAINED_FILE_SHA256 = (
    "9ecab492ee448327f16a7d234aedf041462377f5a7fca1f18deb5c278fc917de"
)
RETAINED_REPORT_SHA256 = (
    "859de0b38638c5f6e03dc3e78404c3776d713da6699862cb9597ebd86d915b1a"
)
RETAINED_SOURCE_COMMIT = "95d4385f6c68f07daa49dcb5d88c5221e5535a0c"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/context_validation_lease_benchmark_v1.schema.json"
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
            "software/scripts/run_context_validation_lease_benchmark_v1.py"
        ),
    }
    from rocell.application.operational_latency_reference_v1 import _sha
    return {**core, "environment_sha256": _sha(core)}


def _samples() -> list[dict]:
    ingress = _digest("same-decision")
    return [
        {
            "sequence": sequence,
            "path": path,
            "duration_ns": (30_000_000 if path == "FULL_SOURCE_REVALIDATION" else 100_000) + index,
            "ingress_sha256": ingress,
        }
        for path in benchmark.PATHS
        for index, sequence in enumerate(range(
            0 if path == benchmark.PATHS[0] else 20,
            20 if path == benchmark.PATHS[0] else 40,
        ))
    ]


def _invalidations() -> list[dict]:
    return [{"case": case, "status": "BLOCKED"} for case in benchmark.INVALIDATION_CASES]


def _report() -> dict:
    return benchmark.build_context_validation_lease_benchmark_v1(
        _samples(), report_id="e1-benchmark-fixture", environment=_environment(),
        context_epoch_sha256=_digest("epoch"), lease_sha256=_digest("lease"),
        invalidation_results=_invalidations(),
    )


def _rehash(report: dict) -> None:
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    report["report_sha256"] = benchmark._sha(unsigned)


def test_benchmark_is_schema_valid_equivalent_and_zero_authority():
    report = _report()
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(benchmark.parse_context_validation_lease_benchmark_v1(report)) == report
    assert report["semantic_equivalence"]["all_outputs_identical"] is True
    assert report["summaries"]["p50_reduction_ns"] > 0
    assert report["invalidation_results"] == _invalidations()
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is report["physical_authority"] is False
    assert report["controller_commands"] == []


def test_retained_clean_commit_benchmark_is_exact_and_fail_closed():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(benchmark.parse_context_validation_lease_benchmark_v1(report)) == report
    assert report["report_sha256"] == RETAINED_REPORT_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert report["environment"]["repository_dirty"] is False
    assert len(report["samples"]) == 40
    assert report["semantic_equivalence"]["all_outputs_identical"] is True
    assert report["invalidation_results"] == _invalidations()
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is report["physical_authority"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0


@pytest.mark.parametrize("mutation,match", (
    ("decision", "decisions differ"),
    ("invalidation", "invalidation coverage"),
    ("summary", "derivation"),
    ("authority", "authority"),
))
def test_rehashed_semantic_mutations_fail_closed(mutation: str, match: str):
    report = copy.deepcopy(_report())
    if mutation == "decision":
        report["samples"][-1]["ingress_sha256"] = _digest("different")
    elif mutation == "invalidation":
        report["invalidation_results"][-1]["status"] = "PASSED"
    elif mutation == "summary":
        report["summaries"]["p95_reduction_ns"] += 1
    else:
        report["physical_authority"] = True
    _rehash(report)
    with pytest.raises(benchmark.ContextValidationLeaseBenchmarkV1Error, match=match):
        benchmark.parse_context_validation_lease_benchmark_v1(report)
