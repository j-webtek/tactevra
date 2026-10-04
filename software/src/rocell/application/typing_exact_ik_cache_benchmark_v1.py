"""Strict retained benchmark for the lifecycle-bound exact IK cache."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)


SCHEMA = "rocell.typing_exact_ik_cache_benchmark.v1"
PATHS = (
    "CACHE_DISABLED",
    "CACHE_COLD",
    "CACHE_WARM",
    "CACHE_CAPACITY_ONE",
)
MINIMUM_SAMPLES_PER_PATH = 10
INVALIDATION_CASES = (
    "EXPLICIT_INVALIDATION",
    "CONTEXT_RELOAD",
    "SERVICE_RESTART",
    "CROSSED_CONTEXT",
    "INTEGRITY_CORRUPTION",
    "UNMANAGED_CACHE",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema", "report_id", "evidence_class", "environment", "sample_count",
    "samples", "summaries", "cache_totals", "semantic_equivalence",
    "invalidation_results", "decision_hashes_unchanged",
    "cache_used_for_admission", "timing_used_for_admission",
    "performance_authority", "controller_opened", "transport_opened",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "report_sha256",
}
_SAMPLE_FIELDS = {
    "sequence", "path", "duration_ns", "receipt_sha256",
    "stage_hashes_sha256", "lookups", "hits", "misses", "stores",
    "capacity_skips",
}
_COUNTERS = ("lookups", "hits", "misses", "stores", "capacity_skips")


class TypingExactIkCacheBenchmarkV1Error(ValueError):
    """Benchmark evidence is incomplete, inconsistent, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingExactIkCacheBenchmarkV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingExactIkCacheBenchmarkV1Error(
            f"{label} is invalid or path-like"
        )
    return value


def _nearest_rank(values: Sequence[int], probability: float) -> int:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(probability * len(ordered))) - 1]


def _summary(samples: Sequence[Mapping[str, Any]]) -> dict[str, int | None]:
    values = [sample["duration_ns"] for sample in samples]
    return {
        "count": len(values),
        "minimum_ns": min(values),
        "p50_ns": _nearest_rank(values, 0.50),
        "p95_ns": _nearest_rank(values, 0.95),
        "p99_ns": _nearest_rank(values, 0.99) if len(values) >= 100 else None,
        "maximum_ns": max(values),
    }


def _validate_path_counters(
    path: str, samples: Sequence[Mapping[str, Any]],
) -> None:
    if path == "CACHE_DISABLED":
        if any(any(sample[field] != 0 for field in _COUNTERS) for sample in samples):
            raise TypingExactIkCacheBenchmarkV1Error(
                "disabled cache counters are nonzero"
            )
    elif path == "CACHE_COLD":
        if any(
            sample["lookups"] <= 0 or sample["misses"] <= 0
            or sample["stores"] != sample["misses"]
            or sample["capacity_skips"] != 0
            for sample in samples
        ):
            raise TypingExactIkCacheBenchmarkV1Error(
                "cold cache behavior differs"
            )
    elif path == "CACHE_WARM":
        if any(
            sample["lookups"] <= 0 or sample["hits"] != sample["lookups"]
            or sample["misses"] != 0 or sample["stores"] != 0
            or sample["capacity_skips"] != 0
            for sample in samples
        ):
            raise TypingExactIkCacheBenchmarkV1Error(
                "warm cache behavior differs"
            )
    elif any(
        sample["lookups"] <= 0 or sample["misses"] <= 0
        or sample["stores"] != 1 or sample["capacity_skips"] <= 0
        for sample in samples
    ):
        raise TypingExactIkCacheBenchmarkV1Error(
            "capacity-one cache behavior differs"
        )


def build_typing_exact_ik_cache_benchmark_v1(
    samples: Sequence[Mapping[str, Any]], *, report_id: str,
    environment: Mapping[str, Any],
    invalidation_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise TypingExactIkCacheBenchmarkV1Error("samples are not a sequence")
    if (
        len(samples) < len(PATHS) * MINIMUM_SAMPLES_PER_PATH
        or len(samples) > 4000
    ):
        raise TypingExactIkCacheBenchmarkV1Error(
            "sample count is outside its bound"
        )
    normalized = []
    for sequence, sample in enumerate(samples):
        if not isinstance(sample, Mapping) or set(sample) != _SAMPLE_FIELDS:
            raise TypingExactIkCacheBenchmarkV1Error("sample fields differ")
        if sample.get("sequence") != sequence or sample.get("path") not in PATHS:
            raise TypingExactIkCacheBenchmarkV1Error(
                "sample sequence or path differs"
            )
        duration = sample.get("duration_ns")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
            raise TypingExactIkCacheBenchmarkV1Error("sample duration differs")
        counters = {}
        for field in _COUNTERS:
            item = sample.get(field)
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise TypingExactIkCacheBenchmarkV1Error(
                    f"sample {field} differs"
                )
            counters[field] = item
        if counters["lookups"] != counters["hits"] + counters["misses"]:
            raise TypingExactIkCacheBenchmarkV1Error(
                "sample cache counters differ"
            )
        normalized.append({
            "sequence": sequence,
            "path": sample["path"],
            "duration_ns": duration,
            "receipt_sha256": _digest(sample.get("receipt_sha256"), "receipt"),
            "stage_hashes_sha256": _digest(
                sample.get("stage_hashes_sha256"), "stage hashes"
            ),
            **counters,
        })
    grouped = {
        path: [sample for sample in normalized if sample["path"] == path]
        for path in PATHS
    }
    if any(
        len(values) < MINIMUM_SAMPLES_PER_PATH for values in grouped.values()
    ):
        raise TypingExactIkCacheBenchmarkV1Error("path coverage is incomplete")
    if len({len(values) for values in grouped.values()}) != 1:
        raise TypingExactIkCacheBenchmarkV1Error("path sample counts differ")
    for path, values in grouped.items():
        _validate_path_counters(path, values)
    receipts = {sample["receipt_sha256"] for sample in normalized}
    stages = {sample["stage_hashes_sha256"] for sample in normalized}
    if len(receipts) != 1 or len(stages) != 1:
        raise TypingExactIkCacheBenchmarkV1Error(
            "cache paths changed canonical decisions"
        )
    expected_invalidations = [
        {"case": case, "status": "BLOCKED"} for case in INVALIDATION_CASES
    ]
    if list(invalidation_results) != expected_invalidations:
        raise TypingExactIkCacheBenchmarkV1Error(
            "invalidation coverage differs"
        )
    distributions = {path: _summary(values) for path, values in grouped.items()}
    reference = distributions["CACHE_DISABLED"]
    summaries = {
        **distributions,
        "warm_p50_reduction_ns": (
            reference["p50_ns"] - distributions["CACHE_WARM"]["p50_ns"]
        ),
        "warm_p95_reduction_ns": (
            reference["p95_ns"] - distributions["CACHE_WARM"]["p95_ns"]
        ),
        "cold_p50_change_ns": (
            distributions["CACHE_COLD"]["p50_ns"] - reference["p50_ns"]
        ),
        "capacity_one_p50_change_ns": (
            distributions["CACHE_CAPACITY_ONE"]["p50_ns"]
            - reference["p50_ns"]
        ),
    }
    cache_totals = {
        path: {
            field: sum(sample[field] for sample in values)
            for field in _COUNTERS
        }
        for path, values in grouped.items()
    }
    core = {
        "schema": SCHEMA,
        "report_id": _identifier(report_id, "report_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "sample_count": len(normalized),
        "samples": normalized,
        "summaries": summaries,
        "cache_totals": cache_totals,
        "semantic_equivalence": {
            "receipt_sha256": next(iter(receipts)),
            "stage_hashes_sha256": next(iter(stages)),
            "all_outputs_identical": True,
        },
        "invalidation_results": expected_invalidations,
        "decision_hashes_unchanged": True,
        "cache_used_for_admission": False,
        "timing_used_for_admission": False,
        "performance_authority": False,
        "controller_opened": False,
        "transport_opened": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "report_sha256": _sha(core)}


def parse_typing_exact_ik_cache_benchmark_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise TypingExactIkCacheBenchmarkV1Error("benchmark report fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("report_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingExactIkCacheBenchmarkV1Error("benchmark report hash differs")
    rebuilt = build_typing_exact_ik_cache_benchmark_v1(
        value.get("samples"), report_id=value.get("report_id"),
        environment=value.get("environment"),
        invalidation_results=value.get("invalidation_results"),
    )
    if rebuilt != dict(value):
        raise TypingExactIkCacheBenchmarkV1Error(
            "benchmark derivation or authority fields differ"
        )
    return value


__all__ = [
    "INVALIDATION_CASES", "MINIMUM_SAMPLES_PER_PATH", "PATHS", "SCHEMA",
    "TypingExactIkCacheBenchmarkV1Error",
    "build_typing_exact_ik_cache_benchmark_v1",
    "parse_typing_exact_ik_cache_benchmark_v1",
]
