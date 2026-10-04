from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_exact_ik_cache_benchmark_v1 as benchmark


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/typing_exact_ik_cache_benchmark_v1.json"
RETAINED_FILE_SHA256 = (
    "6ad55c649fc37a9215264e124b9d7f10edf2bc405de0d559b7290de7de1bd7cf"
)
RETAINED_REPORT_SHA256 = (
    "ce869a13a01339fbf5a7fc5755740273d8fb8f6a4b9134d951bb5e26fc108e21"
)
RETAINED_SOURCE_COMMIT = "402e0d849cc41d694bebf8029644f0bfaa3fc3af"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_exact_ik_cache_benchmark_v1.schema.json"
).read_text(encoding="utf-8")))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _environment() -> dict:
    core = {
        "schema": "rocell.operational_benchmark_environment.v1",
        "captured_at_utc": "2026-09-29T22:00:00Z",
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
            "software/scripts/run_typing_exact_ik_cache_benchmark_v1.py"
        ),
    }
    from rocell.application.operational_latency_reference_v1 import _sha
    return {**core, "environment_sha256": _sha(core)}


def _counter_fixture(path: str) -> dict[str, int]:
    if path == "CACHE_DISABLED":
        return {field: 0 for field in (
            "lookups", "hits", "misses", "stores", "capacity_skips"
        )}
    if path == "CACHE_COLD":
        return {
            "lookups": 10, "hits": 2, "misses": 8, "stores": 8,
            "capacity_skips": 0,
        }
    if path == "CACHE_WARM":
        return {
            "lookups": 10, "hits": 10, "misses": 0, "stores": 0,
            "capacity_skips": 0,
        }
    return {
        "lookups": 10, "hits": 1, "misses": 9, "stores": 1,
        "capacity_skips": 8,
    }


def _samples() -> list[dict]:
    receipt = _digest("same-receipt")
    stages = _digest("same-stages")
    durations = {
        "CACHE_DISABLED": 100_000_000,
        "CACHE_COLD": 102_000_000,
        "CACHE_WARM": 20_000_000,
        "CACHE_CAPACITY_ONE": 95_000_000,
    }
    samples = []
    for index in range(10):
        for path in benchmark.PATHS:
            samples.append({
                "sequence": len(samples),
                "path": path,
                "duration_ns": durations[path] + index,
                "receipt_sha256": receipt,
                "stage_hashes_sha256": stages,
                **_counter_fixture(path),
            })
    return samples


def _invalidations() -> list[dict]:
    return [
        {"case": case, "status": "BLOCKED"}
        for case in benchmark.INVALIDATION_CASES
    ]


def _report() -> dict:
    return benchmark.build_typing_exact_ik_cache_benchmark_v1(
        _samples(),
        report_id="e2-cache-benchmark-fixture",
        environment=_environment(),
        invalidation_results=_invalidations(),
    )


def _rehash(report: dict) -> None:
    unsigned = {
        key: value for key, value in report.items() if key != "report_sha256"
    }
    report["report_sha256"] = benchmark._sha(unsigned)


def test_cache_benchmark_is_schema_valid_equivalent_and_zero_authority():
    report = _report()
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(benchmark.parse_typing_exact_ik_cache_benchmark_v1(report)) == report
    assert report["semantic_equivalence"]["all_outputs_identical"] is True
    assert report["summaries"]["warm_p50_reduction_ns"] > 0
    assert report["cache_totals"]["CACHE_DISABLED"]["lookups"] == 0
    assert report["cache_totals"]["CACHE_WARM"]["misses"] == 0
    assert report["invalidation_results"] == _invalidations()
    assert report["cache_used_for_admission"] is False
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is False
    assert report["controller_commands"] == []
    assert report["physical_authority"] is False


def test_retained_cache_benchmark_is_exact_and_fail_closed():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    report = json.loads(raw)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(benchmark.parse_typing_exact_ik_cache_benchmark_v1(report)) == report
    assert report["report_sha256"] == RETAINED_REPORT_SHA256
    assert report["environment"]["repository_commit"] == RETAINED_SOURCE_COMMIT
    assert report["environment"]["repository_dirty"] is False
    assert report["sample_count"] == 40
    assert report["semantic_equivalence"]["all_outputs_identical"] is True
    assert report["summaries"]["CACHE_DISABLED"]["p50_ns"] == 2_919_987_900
    assert report["summaries"]["CACHE_WARM"]["p50_ns"] == 301_629_900
    assert report["summaries"]["warm_p50_reduction_ns"] == 2_618_358_000
    assert report["summaries"]["warm_p95_reduction_ns"] == 2_639_823_900
    assert report["cache_totals"]["CACHE_COLD"]["hits"] == 110
    assert report["cache_totals"]["CACHE_WARM"]["hits"] == 570
    assert report["cache_totals"]["CACHE_WARM"]["misses"] == 0
    assert report["cache_totals"]["CACHE_CAPACITY_ONE"]["capacity_skips"] == 550
    assert report["invalidation_results"] == _invalidations()
    assert report["cache_used_for_admission"] is False
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False


@pytest.mark.parametrize("mutation,match", (
    ("decision", "canonical decisions"),
    ("stage", "canonical decisions"),
    ("cold", "cold cache behavior"),
    ("warm", "warm cache behavior"),
    ("capacity", "capacity-one cache behavior"),
    ("invalidation", "invalidation coverage"),
    ("summary", "derivation"),
    ("authority", "authority"),
))
def test_rehashed_semantic_mutations_fail_closed(mutation: str, match: str):
    report = copy.deepcopy(_report())
    if mutation == "decision":
        report["samples"][-1]["receipt_sha256"] = _digest("different")
    elif mutation == "stage":
        report["samples"][-1]["stage_hashes_sha256"] = _digest("different")
    elif mutation == "cold":
        sample = next(
            item for item in report["samples"] if item["path"] == "CACHE_COLD"
        )
        sample["stores"] -= 1
    elif mutation == "warm":
        sample = next(
            item for item in report["samples"] if item["path"] == "CACHE_WARM"
        )
        sample["hits"] -= 1
        sample["misses"] += 1
    elif mutation == "capacity":
        sample = next(
            item for item in report["samples"]
            if item["path"] == "CACHE_CAPACITY_ONE"
        )
        sample["capacity_skips"] = 0
    elif mutation == "invalidation":
        report["invalidation_results"][-1]["status"] = "PASSED"
    elif mutation == "summary":
        report["summaries"]["warm_p50_reduction_ns"] += 1
    else:
        report["physical_authority"] = True
    _rehash(report)
    with pytest.raises(
        benchmark.TypingExactIkCacheBenchmarkV1Error, match=match
    ):
        benchmark.parse_typing_exact_ik_cache_benchmark_v1(report)
