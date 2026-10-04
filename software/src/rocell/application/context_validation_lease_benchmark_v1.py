"""Strict retained benchmark for full versus leased context validation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)


SCHEMA = "rocell.context_validation_lease_benchmark.v1"
PATHS = ("FULL_SOURCE_REVALIDATION", "EPOCH_BOUND_LEASE")
MINIMUM_SAMPLES_PER_PATH = 20
INVALIDATION_CASES = (
    "CONTEXT_EPOCH_CHANGED",
    "SERVICE_INSTANCE_RESTARTED",
    "SERVICE_GENERATION_CHANGED",
    "CONTEXT_OBJECT_REPLACED",
    "LEASE_CONTENT_MUTATED",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema", "report_id", "evidence_class", "environment",
    "context_epoch_sha256", "lease_sha256", "sample_count", "samples",
    "summaries", "semantic_equivalence", "invalidation_results",
    "decision_hashes_unchanged", "timing_used_for_admission",
    "performance_authority", "controller_opened", "transport_opened",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "report_sha256",
}
_SAMPLE_FIELDS = {"sequence", "path", "duration_ns", "ingress_sha256"}


class ContextValidationLeaseBenchmarkV1Error(ValueError):
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
        raise ContextValidationLeaseBenchmarkV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise ContextValidationLeaseBenchmarkV1Error(
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


def build_context_validation_lease_benchmark_v1(
    samples: Sequence[Mapping[str, Any]], *, report_id: str,
    environment: Mapping[str, Any], context_epoch_sha256: str,
    lease_sha256: str, invalidation_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build benchmark evidence only when semantics and invalidations agree."""

    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise ContextValidationLeaseBenchmarkV1Error("samples are not a sequence")
    if len(samples) < 2 * MINIMUM_SAMPLES_PER_PATH or len(samples) > 2000:
        raise ContextValidationLeaseBenchmarkV1Error("sample count is outside its bound")
    normalized = []
    for sequence, sample in enumerate(samples):
        if not isinstance(sample, Mapping) or set(sample) != _SAMPLE_FIELDS:
            raise ContextValidationLeaseBenchmarkV1Error("sample fields differ")
        if sample.get("sequence") != sequence or sample.get("path") not in PATHS:
            raise ContextValidationLeaseBenchmarkV1Error("sample sequence or path differs")
        duration = sample.get("duration_ns")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
            raise ContextValidationLeaseBenchmarkV1Error("sample duration differs")
        normalized.append({
            "sequence": sequence,
            "path": sample["path"],
            "duration_ns": duration,
            "ingress_sha256": _digest(sample.get("ingress_sha256"), "ingress"),
        })
    grouped = {
        path: [sample for sample in normalized if sample["path"] == path]
        for path in PATHS
    }
    if any(len(values) < MINIMUM_SAMPLES_PER_PATH for values in grouped.values()):
        raise ContextValidationLeaseBenchmarkV1Error("path coverage is incomplete")
    decisions = {sample["ingress_sha256"] for sample in normalized}
    if len(decisions) != 1:
        raise ContextValidationLeaseBenchmarkV1Error(
            "full and leased admission decisions differ"
        )
    if not isinstance(invalidation_results, Sequence) or isinstance(
        invalidation_results, (str, bytes)
    ):
        raise ContextValidationLeaseBenchmarkV1Error(
            "invalidation results are not a sequence"
        )
    expected_results = [
        {"case": case, "status": "BLOCKED"} for case in INVALIDATION_CASES
    ]
    if list(invalidation_results) != expected_results:
        raise ContextValidationLeaseBenchmarkV1Error(
            "invalidation coverage differs"
        )
    full = _summary(grouped["FULL_SOURCE_REVALIDATION"])
    leased = _summary(grouped["EPOCH_BOUND_LEASE"])
    core = {
        "schema": SCHEMA,
        "report_id": _identifier(report_id, "report_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "context_epoch_sha256": _digest(context_epoch_sha256, "context epoch"),
        "lease_sha256": _digest(lease_sha256, "lease"),
        "sample_count": len(normalized),
        "samples": normalized,
        "summaries": {
            "FULL_SOURCE_REVALIDATION": full,
            "EPOCH_BOUND_LEASE": leased,
            "p50_reduction_ns": full["p50_ns"] - leased["p50_ns"],
            "p95_reduction_ns": full["p95_ns"] - leased["p95_ns"],
        },
        "semantic_equivalence": {
            "ingress_sha256": next(iter(decisions)),
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


def parse_context_validation_lease_benchmark_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise ContextValidationLeaseBenchmarkV1Error("benchmark report fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("report_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise ContextValidationLeaseBenchmarkV1Error("benchmark report hash mismatch")
    rebuilt = build_context_validation_lease_benchmark_v1(
        value.get("samples"), report_id=value.get("report_id"),
        environment=value.get("environment"),
        context_epoch_sha256=value.get("context_epoch_sha256"),
        lease_sha256=value.get("lease_sha256"),
        invalidation_results=value.get("invalidation_results"),
    )
    if rebuilt != dict(value):
        raise ContextValidationLeaseBenchmarkV1Error(
            "benchmark derivation or authority fields differ"
        )
    return value


__all__ = [
    "INVALIDATION_CASES", "MINIMUM_SAMPLES_PER_PATH", "PATHS", "SCHEMA",
    "ContextValidationLeaseBenchmarkV1Error",
    "build_context_validation_lease_benchmark_v1",
    "parse_context_validation_lease_benchmark_v1",
]
