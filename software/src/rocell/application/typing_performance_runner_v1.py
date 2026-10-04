"""Instrument the existing zero-I/O typing shadow boundaries for PC8.

The runner invokes the same production planning functions as PC2 and records
process CPU plus bounded resource observations.  It stops at the honest
collision-evidence blocker and has no controller, transport, or permit surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import hashlib
import json
import os
import sys
import time
from typing import Any

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.models import (
    ActionPlan,
    ModelMotionBatchV2Error,
    decode_model_motion_batch_v2_json,
)

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .context import SimulationContext
from .context_lifecycle_v1 import SimulationContextLifecycleV1
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .model_motion_registry_v2 import (
    TrustedMotionRegistryV2,
    ingest_with_trusted_registry_v2,
    revalidate_with_trusted_registry_v2,
)
from .typing_collision_intake_v1 import prepare_typing_collision_intake_v1
from .typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from .typing_joint_schedule_v1 import (
    TypingJointDynamicsProfileV1,
    compile_typing_joint_schedule_v1,
)
from .typing_performance_report_v1 import (
    STAGES,
    TypingBenchmarkSampleV1,
)
from .typing_planner_preparation_v1 import PreparedTypingPlannerV1
from .typing_shadow_pipeline_v1 import (
    SCHEMA as RECEIPT_SCHEMA,
    STATUS as RECEIPT_STATUS,
    TERMINAL_BLOCKERS,
    TypingShadowPipelineV1Error,
)
from .typing_trajectory_ik_screen_v1 import (
    READY_STATUS as IK_READY_STATUS,
    TypingTrajectoryIkSeedV1,
    screen_typing_trajectory_ik_v1,
)
from .typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from .trajectory_simulation import TrajectorySimulationPolicy


@dataclass(frozen=True, slots=True)
class ProfiledTypingShadowRunV1:
    sample: TypingBenchmarkSampleV1
    receipt: dict[str, Any]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _peak_process_memory_bytes() -> int:
    """Return the process peak working set with a portable stdlib fallback."""

    if os.name == "nt":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = (
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            )

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        )
        get_memory.restype = wintypes.BOOL
        if not get_memory(get_process(), ctypes.byref(counters), counters.cb):
            raise TypingShadowPipelineV1Error(
                "peak process memory measurement failed")
        return int(counters.PeakWorkingSetSize)
    try:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return peak if sys.platform == "darwin" else peak * 1024
    except (ImportError, OSError, ValueError) as exc:
        raise TypingShadowPipelineV1Error(
            "peak process memory measurement is unavailable") from exc


def _measure(function, *args, **kwargs):
    started = time.process_time_ns()
    value = function(*args, **kwargs)
    return value, time.process_time_ns() - started


def profile_typing_shadow_pipeline_v1(
    payload: bytes,
    intent_plan: ActionPlan,
    context: SimulationContext,
    *,
    registry: TrustedMotionRegistryV2,
    current_time_epoch_ms: int,
    ingress_monotonic_ns: int,
    preplanner_monotonic_ns: int,
    execution_config: TypingExecutionConfigV1,
    trajectory_policy: TypingTrajectoryPolicyV1,
    calibration_snapshot: PlannerCalibrationSnapshot,
    ik_seed: TypingTrajectoryIkSeedV1,
    joint_dynamics_profile: TypingJointDynamicsProfileV1,
    scenario: str,
    iteration: int,
    cache_state: str,
    cache_result: str,
    estimated_cache_time_saved_ns: int,
    ik_policy: TrajectorySimulationPolicy | None = None,
    installed_collision_profile: InstalledCollisionGeometryProfile | None = None,
    collision_sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    context_lifecycle: SimulationContextLifecycleV1 | None = None,
    prepared_planner: PreparedTypingPlannerV1 | None = None,
) -> ProfiledTypingShadowRunV1:
    """Profile one admitted synthetic run through the honest PC2 blocker."""

    if (context_lifecycle is None) != (prepared_planner is None):
        raise TypingShadowPipelineV1Error(
            "context lifecycle and prepared planner must be supplied together"
        )
    total_started = time.process_time_ns()
    memory_before = _peak_process_memory_bytes()
    stage_cpu = {stage: 0 for stage in STAGES}

    batch, stage_cpu["decode"] = _measure(
        decode_model_motion_batch_v2_json, payload)

    static_started = time.process_time_ns()
    ingress = ingest_with_trusted_registry_v2(
        batch,
        intent_plan,
        context,
        registry=registry,
        current_time_epoch_ms=current_time_epoch_ms,
        current_monotonic_ns=ingress_monotonic_ns,
        context_lifecycle=context_lifecycle,
    )
    freshness = revalidate_with_trusted_registry_v2(
        ingress,
        registry=registry,
        current_monotonic_ns=preplanner_monotonic_ns,
    )
    stage_cpu["static_validation"] = time.process_time_ns() - static_started

    planning_started = time.process_time_ns()
    execution = compile_typing_execution_plan_v1(
        batch, ingress, config=execution_config)
    trajectory = compile_typing_trajectory_plan_v1(
        execution, policy=trajectory_policy)
    stage_cpu["planning"] = time.process_time_ns() - planning_started

    ik, stage_cpu["ik"] = _measure(
        screen_typing_trajectory_ik_v1,
        execution,
        trajectory,
        context,
        calibration_snapshot,
        ik_seed,
        policy=ik_policy,
        prepared_planner=prepared_planner,
        context_lifecycle=context_lifecycle,
    )
    if ik.get("status") != IK_READY_STATUS:
        raise TypingShadowPipelineV1Error(
            "profiled route did not reach the accepted offline IK boundary")

    schedule, stage_cpu["time_scaling"] = _measure(
        compile_typing_joint_schedule_v1,
        trajectory,
        ik,
        joint_dynamics_profile,
    )
    collision, stage_cpu["collision_intake"] = _measure(
        prepare_typing_collision_intake_v1,
        execution,
        trajectory,
        ik,
        context,
        calibration_snapshot,
        installed_collision_profile,
        sampling_policy=collision_sampling_policy,
        prepared_planner=prepared_planner,
        context_lifecycle=context_lifecycle,
    )
    ordered_targets = [action.target_id for action in execution.actions]
    if ordered_targets != [proposal.target_id for proposal in batch.proposals]:
        raise TypingShadowPipelineV1Error(
            "action order changed during profiling")

    receipt_started = time.process_time_ns()
    stage_hashes = {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": _sha256(freshness),
        "typing_execution_plan_sha256": execution.plan_sha256,
        "typing_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "typing_trajectory_ik_screen_sha256": ik[
            "typing_trajectory_ik_screen_sha256"],
        "typing_joint_schedule_sha256": schedule.schedule_sha256,
        "typing_collision_intake_sha256": collision[
            "typing_collision_intake_sha256"],
    }
    core = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS,
        "request_id": batch.request_id,
        "ordered_target_ids": ordered_targets,
        "action_count": len(ordered_targets),
        "stage_hashes": stage_hashes,
        "terminal_stage": "COLLISION_EVIDENCE_INTAKE",
        "terminal_stage_status": collision["status"],
        "terminal_blockers": collision["blockers"],
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    if tuple(core["terminal_blockers"]) != TERMINAL_BLOCKERS:
        raise TypingShadowPipelineV1Error(
            "profiled route changed the honest terminal blockers")
    receipt = {**core, "typing_shadow_pipeline_sha256": _sha256(core)}
    serialized_bytes = len(_canonical(receipt))
    stage_cpu["receipt_creation"] = time.process_time_ns() - receipt_started
    total_cpu = time.process_time_ns() - total_started
    peak_memory = max(memory_before, _peak_process_memory_bytes())
    if scenario == "DIRECT_HOVER":
        predicted_duration = round(
            trajectory.metrics.direct_estimated_time_ms * 1_000_000)
    elif scenario == "PARK_BASELINE":
        predicted_duration = round(
            trajectory.metrics.park_baseline_estimated_time_ms * 1_000_000)
    else:
        predicted_duration = schedule.samples[-1].time_from_start_ns
    sample = TypingBenchmarkSampleV1(
        scenario=scenario,
        iteration=iteration,
        action_count=len(ordered_targets),
        cache_state=cache_state,
        cache_result=cache_result,
        outcome="ADMITTED",
        stage_cpu_ns=stage_cpu,
        total_cpu_ns=total_cpu,
        peak_screening_samples=len(trajectory.screening_samples),
        serialized_artifact_bytes=serialized_bytes,
        peak_process_memory_bytes=peak_memory,
        predicted_route_duration_ns=predicted_duration,
        estimated_cache_time_saved_ns=estimated_cache_time_saved_ns,
    )
    return ProfiledTypingShadowRunV1(sample=sample, receipt=receipt)


def profile_forced_decode_rejection_v1(
    payload: bytes,
    *,
    iteration: int,
) -> TypingBenchmarkSampleV1:
    """Measure one canonical malformed-batch rejection without other stages."""

    total_started = time.process_time_ns()
    memory_before = _peak_process_memory_bytes()
    decode_started = time.process_time_ns()
    try:
        decode_model_motion_batch_v2_json(payload)
    except ModelMotionBatchV2Error:
        pass
    else:
        raise TypingShadowPipelineV1Error(
            "forced-rejection payload unexpectedly decoded")
    decode_cpu = time.process_time_ns() - decode_started
    total_cpu = time.process_time_ns() - total_started
    stages = {stage: 0 for stage in STAGES}
    stages["decode"] = decode_cpu
    return TypingBenchmarkSampleV1(
        scenario="FORCED_REJECTION",
        iteration=iteration,
        action_count=1,
        cache_state="NOT_APPLICABLE",
        cache_result="NOT_APPLICABLE",
        outcome="REJECTED",
        stage_cpu_ns=stages,
        total_cpu_ns=total_cpu,
        peak_screening_samples=0,
        serialized_artifact_bytes=len(payload),
        peak_process_memory_bytes=max(
            memory_before, _peak_process_memory_bytes()),
        predicted_route_duration_ns=0,
        estimated_cache_time_saved_ns=0,
    )


__all__ = [
    "ProfiledTypingShadowRunV1", "profile_forced_decode_rejection_v1",
    "profile_typing_shadow_pipeline_v1",
]
