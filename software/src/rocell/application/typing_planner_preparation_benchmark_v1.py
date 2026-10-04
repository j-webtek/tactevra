"""Strict retained benchmark for full-source versus prepared typing planning."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)


SCHEMA = "rocell.typing_planner_preparation_benchmark.v1"
PATHS = ("FULL_SOURCE_PIPELINE", "EPOCH_PREPARED_PIPELINE")
MINIMUM_SAMPLES_PER_PATH = 20
INVALIDATION_CASES = (
    "CONTEXT_RELOAD",
    "SERVICE_RESTART",
    "PREPARATION_MUTATED",
    "UNMANAGED_PREPARATION",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema", "report_id", "evidence_class", "environment",
    "context_epoch_sha256", "lease_sha256", "preparation_sha256",
    "model_sha256", "preparation_duration_ns", "sample_count", "samples",
    "summaries", "semantic_equivalence", "invalidation_results",
    "decision_hashes_unchanged", "timing_used_for_admission",
    "performance_authority", "controller_opened", "transport_opened",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "report_sha256",
}
_SAMPLE_FIELDS = {
    "sequence", "path", "duration_ns", "receipt_sha256",
    "stage_hashes_sha256",
}


class TypingPlannerPreparationBenchmarkV1Error(ValueError):
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
        raise TypingPlannerPreparationBenchmarkV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingPlannerPreparationBenchmarkV1Error(
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


def build_typing_planner_preparation_benchmark_v1(
    samples: Sequence[Mapping[str, Any]], *, report_id: str,
    environment: Mapping[str, Any], context_epoch_sha256: str,
    lease_sha256: str, preparation_sha256: str, model_sha256: str,
    preparation_duration_ns: int,
    invalidation_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build evidence only for exact outputs and complete invalidation tests."""

    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise TypingPlannerPreparationBenchmarkV1Error("samples are not a sequence")
    if len(samples) < 2 * MINIMUM_SAMPLES_PER_PATH or len(samples) > 2000:
        raise TypingPlannerPreparationBenchmarkV1Error(
            "sample count is outside its bound"
        )
    if (
        isinstance(preparation_duration_ns, bool)
        or not isinstance(preparation_duration_ns, int)
        or preparation_duration_ns < 0
    ):
        raise TypingPlannerPreparationBenchmarkV1Error(
            "preparation duration differs"
        )
    normalized = []
    for sequence, sample in enumerate(samples):
        if not isinstance(sample, Mapping) or set(sample) != _SAMPLE_FIELDS:
            raise TypingPlannerPreparationBenchmarkV1Error("sample fields differ")
        if sample.get("sequence") != sequence or sample.get("path") not in PATHS:
            raise TypingPlannerPreparationBenchmarkV1Error(
                "sample sequence or path differs"
            )
        duration = sample.get("duration_ns")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
            raise TypingPlannerPreparationBenchmarkV1Error("sample duration differs")
        normalized.append({
            "sequence": sequence,
            "path": sample["path"],
            "duration_ns": duration,
            "receipt_sha256": _digest(sample.get("receipt_sha256"), "receipt"),
            "stage_hashes_sha256": _digest(
                sample.get("stage_hashes_sha256"), "stage hashes"
            ),
        })
    grouped = {
        path: [sample for sample in normalized if sample["path"] == path]
        for path in PATHS
    }
    if any(len(values) < MINIMUM_SAMPLES_PER_PATH for values in grouped.values()):
        raise TypingPlannerPreparationBenchmarkV1Error("path coverage is incomplete")
    receipts = {sample["receipt_sha256"] for sample in normalized}
    stages = {sample["stage_hashes_sha256"] for sample in normalized}
    if len(receipts) != 1 or len(stages) != 1:
        raise TypingPlannerPreparationBenchmarkV1Error(
            "full and prepared pipeline decisions differ"
        )
    expected_results = [
        {"case": case, "status": "BLOCKED"} for case in INVALIDATION_CASES
    ]
    if list(invalidation_results) != expected_results:
        raise TypingPlannerPreparationBenchmarkV1Error(
            "invalidation coverage differs"
        )
    full = _summary(grouped["FULL_SOURCE_PIPELINE"])
    prepared = _summary(grouped["EPOCH_PREPARED_PIPELINE"])
    core = {
        "schema": SCHEMA,
        "report_id": _identifier(report_id, "report_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "context_epoch_sha256": _digest(context_epoch_sha256, "context epoch"),
        "lease_sha256": _digest(lease_sha256, "lease"),
        "preparation_sha256": _digest(preparation_sha256, "preparation"),
        "model_sha256": _digest(model_sha256, "model"),
        "preparation_duration_ns": preparation_duration_ns,
        "sample_count": len(normalized),
        "samples": normalized,
        "summaries": {
            "FULL_SOURCE_PIPELINE": full,
            "EPOCH_PREPARED_PIPELINE": prepared,
            "p50_reduction_ns": full["p50_ns"] - prepared["p50_ns"],
            "p95_reduction_ns": full["p95_ns"] - prepared["p95_ns"],
        },
        "semantic_equivalence": {
            "receipt_sha256": next(iter(receipts)),
            "stage_hashes_sha256": next(iter(stages)),
            "all_outputs_identical": True,
        },
        "invalidation_results": expected_results,
        "decision_hashes_unchanged": True,
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


def parse_typing_planner_preparation_benchmark_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise TypingPlannerPreparationBenchmarkV1Error(
            "benchmark report fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("report_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingPlannerPreparationBenchmarkV1Error(
            "benchmark report hash mismatch"
        )
    rebuilt = build_typing_planner_preparation_benchmark_v1(
        value.get("samples"), report_id=value.get("report_id"),
        environment=value.get("environment"),
        context_epoch_sha256=value.get("context_epoch_sha256"),
        lease_sha256=value.get("lease_sha256"),
        preparation_sha256=value.get("preparation_sha256"),
        model_sha256=value.get("model_sha256"),
        preparation_duration_ns=value.get("preparation_duration_ns"),
        invalidation_results=value.get("invalidation_results"),
    )
    if rebuilt != dict(value):
        raise TypingPlannerPreparationBenchmarkV1Error(
            "benchmark derivation or authority fields differ"
        )
    return value


__all__ = [
    "INVALIDATION_CASES", "MINIMUM_SAMPLES_PER_PATH", "PATHS", "SCHEMA",
    "TypingPlannerPreparationBenchmarkV1Error",
    "build_typing_planner_preparation_benchmark_v1",
    "parse_typing_planner_preparation_benchmark_v1",
]
