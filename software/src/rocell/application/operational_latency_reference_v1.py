"""Host-measured, zero-authority T0-T5 operational latency reference."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.models import ActionPlan, decode_model_motion_batch_v2_json

from .context import SimulationContext
from .model_motion_registry_v2 import (
    TrustedMotionRegistryV2,
    ingest_with_trusted_registry_v2,
    revalidate_with_trusted_registry_v2,
)
from .operational_latency_trace_v1 import (
    OperationalLatencyTraceV1Error,
    build_operational_latency_trace_v1,
    parse_operational_latency_trace_v1,
)
from .typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from .typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)


SCHEMA = "rocell.operational_latency_reference.v1"
ENVIRONMENT_SCHEMA = "rocell.operational_benchmark_environment.v1"
MINIMUM_RUNS_PER_CLASS = 20
MAXIMUM_TRACES = 4096
RUN_CLASSES = ("COLD", "WARM")
MEASURED_DURATIONS = (
    "request_to_intent_ns",
    "request_to_batch_ns",
    "batch_to_admission_ns",
    "admission_to_first_plan_ns",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_ENVIRONMENT_FIELDS = {
    "schema", "captured_at_utc", "repository_commit", "repository_dirty",
    "python_version", "python_implementation", "platform_system",
    "platform_release", "platform_machine", "logical_cpu_count",
    "perf_counter_resolution_ns", "benchmark_entrypoint", "environment_sha256",
}
_REPORT_FIELDS = {
    "schema", "report_id", "evidence_class", "upstream_input_mode",
    "terminal_scope", "run_class_definitions", "environment", "trace_count",
    "traces", "summaries", "decision_hashes_unchanged",
    "timing_used_for_admission", "performance_authority",
    "controller_opened", "transport_opened", "controller_commands",
    "hardware_writes", "physical_movements", "physical_authority",
    "report_sha256",
}


class OperationalLatencyReferenceV1Error(ValueError):
    """A benchmark reference is incomplete, misleading, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise OperationalLatencyReferenceV1Error(f"{label} is not a SHA-256 digest")
    return value


def _revision(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None
    ):
        raise OperationalLatencyReferenceV1Error(
            f"{label} is not a supported Git object identity"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise OperationalLatencyReferenceV1Error(f"{label} is invalid or path-like")
    return value


def _decision(
    payload: bytes, intent_plan: ActionPlan, context: SimulationContext, *,
    registry: TrustedMotionRegistryV2, current_time_epoch_ms: int,
    ingress_monotonic_ns: int, preplanner_monotonic_ns: int,
    execution_config: TypingExecutionConfigV1,
    trajectory_policy: TypingTrajectoryPolicyV1,
) -> tuple[dict[str, Any], Any, Any, Any, Any]:
    batch = decode_model_motion_batch_v2_json(payload)
    ingress = ingest_with_trusted_registry_v2(
        batch, intent_plan, context, registry=registry,
        current_time_epoch_ms=current_time_epoch_ms,
        current_monotonic_ns=ingress_monotonic_ns,
    )
    freshness = revalidate_with_trusted_registry_v2(
        ingress, registry=registry, current_monotonic_ns=preplanner_monotonic_ns,
    )
    execution = compile_typing_execution_plan_v1(
        batch, ingress, config=execution_config,
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution, policy=trajectory_policy,
    )
    core = {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": _sha(freshness),
        "typing_execution_plan_sha256": execution.plan_sha256,
        "typing_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "ordered_target_ids": [action.target_id for action in execution.actions],
    }
    return core, batch, ingress, execution, trajectory


def measure_operational_planning_trace_v1(
    payload: bytes, intent_plan: ActionPlan, context: SimulationContext, *,
    registry: TrustedMotionRegistryV2, current_time_epoch_ms: int,
    ingress_monotonic_ns: int, preplanner_monotonic_ns: int,
    execution_config: TypingExecutionConfigV1,
    trajectory_policy: TypingTrajectoryPolicyV1,
    trace_id: str, run_class: str,
) -> dict[str, Any]:
    """Measure real arm-side planning boundaries and stop before permission."""

    if not isinstance(payload, bytes) or not payload:
        raise OperationalLatencyReferenceV1Error("payload must be nonempty bytes")
    t0 = time.perf_counter_ns()
    milestones = [{"milestone_id": "T0_REQUEST_RECEIVED", "monotonic_ns": t0}]
    _sha(intent_plan.to_dict())
    milestones.append({"milestone_id": "T1_INTENT_SEALED", "monotonic_ns": time.perf_counter_ns()})
    _sha({"registry": registry.precision_observation_sha256,
          "qualification": registry.qualification.qualification_sha256})
    milestones.append({"milestone_id": "T2_PERCEPTION_SEALED", "monotonic_ns": time.perf_counter_ns()})
    hashlib.sha256(payload).hexdigest()
    milestones.append({"milestone_id": "T3_BATCH_EMITTED", "monotonic_ns": time.perf_counter_ns()})

    batch = decode_model_motion_batch_v2_json(payload)
    ingress = ingest_with_trusted_registry_v2(
        batch, intent_plan, context, registry=registry,
        current_time_epoch_ms=current_time_epoch_ms,
        current_monotonic_ns=ingress_monotonic_ns,
    )
    freshness = revalidate_with_trusted_registry_v2(
        ingress, registry=registry, current_monotonic_ns=preplanner_monotonic_ns,
    )
    milestones.append({"milestone_id": "T4_BATCH_ADMITTED", "monotonic_ns": time.perf_counter_ns()})
    execution = compile_typing_execution_plan_v1(
        batch, ingress, config=execution_config,
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution, policy=trajectory_policy,
    )
    milestones.append({"milestone_id": "T5_FIRST_PLAN_READY", "monotonic_ns": time.perf_counter_ns()})
    decision = {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": _sha(freshness),
        "typing_execution_plan_sha256": execution.plan_sha256,
        "typing_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "ordered_target_ids": [action.target_id for action in execution.actions],
    }
    verification, *_ = _decision(
        payload, intent_plan, context, registry=registry,
        current_time_epoch_ms=current_time_epoch_ms,
        ingress_monotonic_ns=ingress_monotonic_ns,
        preplanner_monotonic_ns=preplanner_monotonic_ns,
        execution_config=execution_config, trajectory_policy=trajectory_policy,
    )
    if verification != decision:
        raise OperationalLatencyReferenceV1Error(
            "planning decision changed during instrumentation"
        )
    decision_sha256 = _sha(decision)
    trace = build_operational_latency_trace_v1(
        milestones, trace_id=trace_id,
        evidence_class="HOST_MEASURED_OFFLINE", run_class=run_class,
        cache_outcome="NOT_APPLICABLE", outcome="BLOCKED",
        action_count=len(execution.actions),
        blocker_codes=["PERMIT_NOT_REQUESTED_OFFLINE_REFERENCE"],
        correlation={
            "request_sha256": hashlib.sha256(payload).hexdigest(),
            "session_sha256": _sha({"trace_id": trace_id, "class": run_class}),
            "ai_batch_sha256": batch.batch_sha256,
            "plan_sha256": trajectory.trajectory_plan_sha256,
            "configuration_epoch_sha256": None,
            "controller_session_sha256": None,
            "result_sha256": decision_sha256,
        },
        resource_counts={
            "artifact_bytes": len(payload) + len(_canonical(decision)),
            "ik_solve_count": 0,
            "screening_sample_count": len(trajectory.screening_samples),
            "controller_command_count": 0,
            "hardware_write_count": 0,
            "physical_movement_count": 0,
        },
        decision_sha256=decision_sha256,
    )
    return dict(parse_operational_latency_trace_v1(trace))


def capture_operational_benchmark_environment_v1(
    workspace: Path, *, captured_at_utc: str,
    benchmark_entrypoint: str = "software/scripts/run_operational_latency_reference_v1.py",
) -> dict[str, Any]:
    """Capture bounded host identity without paths, credentials, or raw environment."""

    workspace = workspace.resolve(strict=True)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=workspace, text=True,
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=workspace, text=True,
        ).strip())
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OperationalLatencyReferenceV1Error(
            "repository identity is unavailable"
        ) from exc
    _revision(commit, "repository commit")
    clock = time.get_clock_info("perf_counter")
    core = {
        "schema": ENVIRONMENT_SCHEMA,
        "captured_at_utc": _identifier(captured_at_utc, "captured_at_utc"),
        "repository_commit": commit,
        "repository_dirty": dirty,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_system": platform.system() or "UNKNOWN",
        "platform_release": platform.release() or "UNKNOWN",
        "platform_machine": platform.machine() or "UNKNOWN",
        "logical_cpu_count": os.cpu_count() or 1,
        "perf_counter_resolution_ns": max(1, round(clock.resolution * 1_000_000_000)),
        "benchmark_entrypoint": _identifier(
            benchmark_entrypoint, "benchmark_entrypoint"
        ),
    }
    return {**core, "environment_sha256": _sha(core)}


def validate_operational_benchmark_environment_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ENVIRONMENT_FIELDS:
        raise OperationalLatencyReferenceV1Error("environment fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("environment_sha256")
    if _sha(unsigned) != digest:
        raise OperationalLatencyReferenceV1Error("environment hash mismatch")
    if value.get("schema") != ENVIRONMENT_SCHEMA:
        raise OperationalLatencyReferenceV1Error("environment schema differs")
    _revision(value.get("repository_commit"), "repository commit")
    if value.get("repository_dirty") is not False:
        raise OperationalLatencyReferenceV1Error(
            "retained reference requires a clean source commit"
        )
    for field in (
        "captured_at_utc", "python_version", "python_implementation",
        "platform_system", "platform_release", "platform_machine",
        "benchmark_entrypoint",
    ):
        _identifier(value.get(field), field)
    for field in ("logical_cpu_count", "perf_counter_resolution_ns"):
        candidate = value.get(field)
        if isinstance(candidate, bool) or not isinstance(candidate, int) or candidate <= 0:
            raise OperationalLatencyReferenceV1Error(f"{field} is invalid")
    return dict(value)


def _nearest_rank(values: Sequence[int], probability: float) -> int:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(probability * len(ordered))) - 1]


def _summary(traces: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    durations = {
        field: [trace["durations_ns"][field] for trace in traces]
        for field in MEASURED_DURATIONS
    }
    return {
        "trace_count": len(traces),
        "durations_ns": {
            field: {
                "minimum": min(values),
                "p50": _nearest_rank(values, 0.50),
                "p95": _nearest_rank(values, 0.95),
                "p99": _nearest_rank(values, 0.99) if len(values) >= 100 else None,
                "maximum": max(values),
            }
            for field, values in durations.items()
        },
    }


def build_operational_latency_reference_v1(
    traces: Sequence[Mapping[str, Any]], *, report_id: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate cold/warm host traces without making a physical speed claim."""

    if not isinstance(traces, Sequence) or isinstance(traces, (str, bytes)):
        raise OperationalLatencyReferenceV1Error("traces are not a sequence")
    if not 2 * MINIMUM_RUNS_PER_CLASS <= len(traces) <= MAXIMUM_TRACES:
        raise OperationalLatencyReferenceV1Error("trace count is outside its bound")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for trace in traces:
        try:
            normalized = dict(parse_operational_latency_trace_v1(trace))
        except OperationalLatencyTraceV1Error as exc:
            raise OperationalLatencyReferenceV1Error("trace is invalid") from exc
        if normalized["trace_id"] in seen:
            raise OperationalLatencyReferenceV1Error("trace identity is duplicated")
        seen.add(normalized["trace_id"])
        if (
            normalized["evidence_class"] != "HOST_MEASURED_OFFLINE"
            or normalized["terminal_milestone"] != "T5_FIRST_PLAN_READY"
            or normalized["outcome"] != "BLOCKED"
            or normalized["blocker_codes"] != ["PERMIT_NOT_REQUESTED_OFFLINE_REFERENCE"]
            or normalized["resource_counts"]["controller_command_count"] != 0
            or normalized["resource_counts"]["hardware_write_count"] != 0
            or normalized["resource_counts"]["physical_movement_count"] != 0
        ):
            raise OperationalLatencyReferenceV1Error("trace scope differs")
        parsed.append(normalized)
    grouped = {
        run_class: [trace for trace in parsed if trace["run_class"] == run_class]
        for run_class in RUN_CLASSES
    }
    if any(len(values) < MINIMUM_RUNS_PER_CLASS for values in grouped.values()):
        raise OperationalLatencyReferenceV1Error("cold and warm coverage is incomplete")
    normalized_environment = validate_operational_benchmark_environment_v1(environment)
    core = {
        "schema": SCHEMA,
        "report_id": _identifier(report_id, "report_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "upstream_input_mode": "PRESEALED_SYNTHETIC_FIXTURE",
        "terminal_scope": "T5_FIRST_PLAN_READY_NO_PERMIT_REQUESTED",
        "run_class_definitions": {
            "COLD": "fresh logical input and trusted-registry objects in a warm Python process",
            "WARM": "reused immutable input and trusted-registry objects in the same Python process",
        },
        "environment": normalized_environment,
        "trace_count": len(parsed),
        "traces": parsed,
        "summaries": {
            "COLD": _summary(grouped["COLD"]),
            "WARM": _summary(grouped["WARM"]),
            "ALL": _summary(parsed),
        },
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


def parse_operational_latency_reference_v1(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise OperationalLatencyReferenceV1Error("reference report fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("report_sha256")
    if not isinstance(digest, str) or _sha(unsigned) != digest:
        raise OperationalLatencyReferenceV1Error("reference report hash mismatch")
    rebuilt = build_operational_latency_reference_v1(
        value.get("traces"), report_id=value.get("report_id"),
        environment=value.get("environment"),
    )
    if rebuilt != dict(value):
        raise OperationalLatencyReferenceV1Error(
            "reference derivation or authority fields differ"
        )
    return value


__all__ = [
    "ENVIRONMENT_SCHEMA", "MEASURED_DURATIONS", "MINIMUM_RUNS_PER_CLASS",
    "SCHEMA", "OperationalLatencyReferenceV1Error",
    "build_operational_latency_reference_v1",
    "capture_operational_benchmark_environment_v1",
    "measure_operational_planning_trace_v1",
    "parse_operational_latency_reference_v1",
    "validate_operational_benchmark_environment_v1",
]
