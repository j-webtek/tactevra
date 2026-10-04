"""Bounded PC8 synthetic performance-report contract.

This module aggregates caller-supplied offline measurements.  It cannot open a
transport, execute a controller command, or turn predicted route duration into
a physical typing-speed claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .pre_camera_typing_qualification_basis_v1 import (
    PreCameraTypingQualificationBasisV1,
)


SCHEMA = "rocell.typing_performance_report.v1"
STATUS = "PASS_SYNTHETIC_OFFLINE"
STAGES = (
    "decode",
    "static_validation",
    "planning",
    "ik",
    "time_scaling",
    "collision_intake",
    "preview_validation",
    "encoding",
    "receipt_creation",
)
REQUIRED_SCENARIOS = (
    "COLD_CACHE",
    "WARM_CACHE",
    "LONG_STRING",
    "REPEATED_KEY",
    "PUNCTUATION",
    "KEYBOARD_EXTREME",
    "FORCED_REJECTION",
    "DIRECT_HOVER",
    "PARK_BASELINE",
)
_CACHE_STATES = frozenset({"COLD", "WARM", "NOT_APPLICABLE"})
_CACHE_RESULTS = frozenset({"MISS", "HIT_REVALIDATED", "NOT_APPLICABLE"})
_OUTCOMES = frozenset({"ADMITTED", "REJECTED"})


class TypingPerformanceReportV1Error(ValueError):
    """Benchmark input is incomplete, unbounded, or physically misleading."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingPerformanceReportV1Error(
            "benchmark value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
    ):
        raise TypingPerformanceReportV1Error(
            f"{label} must be bounded nonempty unpadded text")
    return value


def _positive_int(value: object, label: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise TypingPerformanceReportV1Error(
            f"{label} must be an integer in [1, {maximum}]")
    return value


def _nonnegative_int(value: object, label: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        raise TypingPerformanceReportV1Error(
            f"{label} must be an integer in [0, {maximum}]")
    return value


@dataclass(frozen=True, slots=True)
class TypingBenchmarkPolicyV1:
    minimum_iterations: int
    maximum_actions_per_batch: int
    maximum_screening_samples: int
    maximum_serialized_artifact_bytes: int
    maximum_peak_process_memory_mib: int
    planning_cpu_p95_ms_ceiling: int

    def __post_init__(self) -> None:
        _positive_int(self.minimum_iterations, "minimum_iterations", 100_000)
        _positive_int(
            self.maximum_actions_per_batch, "maximum_actions_per_batch", 10_000)
        _positive_int(
            self.maximum_screening_samples, "maximum_screening_samples", 1_000_000)
        _positive_int(
            self.maximum_serialized_artifact_bytes,
            "maximum_serialized_artifact_bytes", 1_000_000_000)
        _positive_int(
            self.maximum_peak_process_memory_mib,
            "maximum_peak_process_memory_mib", 1_000_000)
        _positive_int(
            self.planning_cpu_p95_ms_ceiling,
            "planning_cpu_p95_ms_ceiling", 10_000_000)

    @classmethod
    def from_pc0_basis(
        cls, basis: PreCameraTypingQualificationBasisV1,
    ) -> "TypingBenchmarkPolicyV1":
        if not isinstance(basis, PreCameraTypingQualificationBasisV1):
            raise TypeError("basis must be a PreCameraTypingQualificationBasisV1")
        policy = basis.document["benchmark_policy"]
        return cls(**{
            field: policy[field]
            for field in cls.__dataclass_fields__
        })

    def to_dict(self) -> dict[str, int]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class TypingBenchmarkSampleV1:
    scenario: str
    iteration: int
    action_count: int
    cache_state: str
    cache_result: str
    outcome: str
    stage_cpu_ns: Mapping[str, int]
    total_cpu_ns: int
    peak_screening_samples: int
    serialized_artifact_bytes: int
    peak_process_memory_bytes: int
    predicted_route_duration_ns: int
    estimated_cache_time_saved_ns: int

    def __post_init__(self) -> None:
        if self.scenario not in REQUIRED_SCENARIOS:
            raise TypingPerformanceReportV1Error("scenario is not canonical")
        _nonnegative_int(self.iteration, "iteration", 1_000_000)
        _positive_int(self.action_count, "action_count", 1_000_000)
        if self.cache_state not in _CACHE_STATES:
            raise TypingPerformanceReportV1Error("cache_state is invalid")
        if self.cache_result not in _CACHE_RESULTS:
            raise TypingPerformanceReportV1Error("cache_result is invalid")
        if self.outcome not in _OUTCOMES:
            raise TypingPerformanceReportV1Error("outcome is invalid")
        if not isinstance(self.stage_cpu_ns, Mapping) or tuple(
            self.stage_cpu_ns) != STAGES:
            raise TypingPerformanceReportV1Error(
                "stage_cpu_ns must use exact canonical stage order")
        parsed = {
            stage: _nonnegative_int(
                self.stage_cpu_ns[stage], f"stage_cpu_ns.{stage}", 10**18)
            for stage in STAGES
        }
        object.__setattr__(self, "stage_cpu_ns", MappingProxyType(parsed))
        for field in (
            "total_cpu_ns", "peak_screening_samples",
            "serialized_artifact_bytes", "peak_process_memory_bytes",
            "predicted_route_duration_ns", "estimated_cache_time_saved_ns",
        ):
            _nonnegative_int(getattr(self, field), field, 10**18)
        if self.total_cpu_ns < sum(parsed.values()):
            raise TypingPerformanceReportV1Error(
                "total_cpu_ns cannot be less than measured stage CPU")
        if self.scenario == "COLD_CACHE" and self.cache_state != "COLD":
            raise TypingPerformanceReportV1Error(
                "cold-cache scenario must declare COLD state")
        if self.scenario == "WARM_CACHE" and self.cache_state != "WARM":
            raise TypingPerformanceReportV1Error(
                "warm-cache scenario must declare WARM state")
        if self.scenario == "FORCED_REJECTION" and self.outcome != "REJECTED":
            raise TypingPerformanceReportV1Error(
                "forced-rejection scenario must reject")


def _percentile(values: Sequence[int], percentile: int) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100.0) * len(ordered)) - 1)
    return ordered[index]


def _distribution(values: Sequence[int]) -> dict[str, int]:
    return {
        "count": len(values),
        "minimum": min(values),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "p99": _percentile(values, 99),
        "maximum": max(values),
    }


def build_typing_performance_report_v1(
    samples: Sequence[TypingBenchmarkSampleV1],
    *,
    policy: TypingBenchmarkPolicyV1,
    qualification_basis_sha256: str,
) -> dict[str, Any]:
    """Aggregate complete bounded samples into a synthetic-only PC8 report."""

    if not isinstance(policy, TypingBenchmarkPolicyV1):
        raise TypeError("policy must be a TypingBenchmarkPolicyV1")
    _identifier(qualification_basis_sha256, "qualification_basis_sha256")
    if len(qualification_basis_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in qualification_basis_sha256
    ):
        raise TypingPerformanceReportV1Error(
            "qualification_basis_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(samples, Sequence) or not samples:
        raise TypingPerformanceReportV1Error("samples must be nonempty")
    grouped: dict[str, list[TypingBenchmarkSampleV1]] = {
        scenario: [] for scenario in REQUIRED_SCENARIOS}
    seen: set[tuple[str, int]] = set()
    for sample in samples:
        if not isinstance(sample, TypingBenchmarkSampleV1):
            raise TypingPerformanceReportV1Error("sample type is invalid")
        identity = (sample.scenario, sample.iteration)
        if identity in seen:
            raise TypingPerformanceReportV1Error("sample identity is duplicated")
        seen.add(identity)
        grouped[sample.scenario].append(sample)
    for scenario, values in grouped.items():
        if len(values) < policy.minimum_iterations:
            raise TypingPerformanceReportV1Error(
                f"{scenario} has fewer than minimum iterations")

    stage_statistics = {
        stage: _distribution([
            sample.stage_cpu_ns[stage] for sample in samples
        ])
        for stage in STAGES
    }
    scenarios = {}
    for name in REQUIRED_SCENARIOS:
        values = grouped[name]
        scenarios[name] = {
            "iterations": len(values),
            "total_cpu_ns": _distribution([
                sample.total_cpu_ns for sample in values]),
            "predicted_route_duration_ns": _distribution([
                sample.predicted_route_duration_ns for sample in values]),
            "admitted": sum(sample.outcome == "ADMITTED" for sample in values),
            "rejected": sum(sample.outcome == "REJECTED" for sample in values),
        }
    maximum_actions = max(sample.action_count for sample in samples)
    maximum_screening = max(sample.peak_screening_samples for sample in samples)
    maximum_artifact = max(sample.serialized_artifact_bytes for sample in samples)
    maximum_memory = max(sample.peak_process_memory_bytes for sample in samples)
    planning_p95 = stage_statistics["planning"]["p95"]
    memory_ceiling = policy.maximum_peak_process_memory_mib * 1024 * 1024
    ceilings = {
        "action_count": maximum_actions <= policy.maximum_actions_per_batch,
        "screening_samples": maximum_screening <= policy.maximum_screening_samples,
        "serialized_artifact_bytes": (
            maximum_artifact <= policy.maximum_serialized_artifact_bytes),
        "peak_process_memory_bytes": maximum_memory <= memory_ceiling,
        "planning_cpu_p95_ns": (
            planning_p95 <= policy.planning_cpu_p95_ms_ceiling * 1_000_000),
    }
    if not all(ceilings.values()):
        raise TypingPerformanceReportV1Error(
            "one or more PC0 benchmark ceilings were exceeded")
    cold = grouped["COLD_CACHE"]
    warm = grouped["WARM_CACHE"]
    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_class": "SYNTHETIC_OFFLINE_ONLY",
        "qualification_basis_sha256": qualification_basis_sha256,
        "policy": policy.to_dict(),
        "sample_count": len(samples),
        "scenario_order": list(REQUIRED_SCENARIOS),
        "scenarios": scenarios,
        "stage_cpu_ns": stage_statistics,
        "total_cpu_ns": _distribution([
            sample.total_cpu_ns for sample in samples]),
        "resources": {
            "maximum_action_count": maximum_actions,
            "maximum_screening_samples": maximum_screening,
            "maximum_serialized_artifact_bytes": maximum_artifact,
            "maximum_peak_process_memory_bytes": maximum_memory,
            "ceilings_passed": ceilings,
        },
        "cache": {
            "cold_misses": sum(
                sample.cache_result == "MISS" for sample in cold),
            "warm_hits": sum(
                sample.cache_result == "HIT_REVALIDATED" for sample in warm),
            "estimated_time_saved_ns": sum(
                sample.estimated_cache_time_saved_ns for sample in samples),
        },
        "route_comparison": {
            "direct_hover_predicted_p50_ns": scenarios[
                "DIRECT_HOVER"]["predicted_route_duration_ns"]["p50"],
            "park_baseline_predicted_p50_ns": scenarios[
                "PARK_BASELINE"]["predicted_route_duration_ns"]["p50"],
        },
        "simulation_timing_is_physical_claim": False,
        "measured_typing_speed_claimed": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "typing_performance_report_sha256": _sha256(core)}


__all__ = [
    "REQUIRED_SCENARIOS", "SCHEMA", "STAGES", "STATUS",
    "TypingBenchmarkPolicyV1", "TypingBenchmarkSampleV1",
    "TypingPerformanceReportV1Error", "build_typing_performance_report_v1",
]
