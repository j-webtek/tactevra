"""Golden zero-I/O composition of the optimized typing planning boundaries."""

from __future__ import annotations

import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.models import ActionPlan, decode_model_motion_batch_v2_json

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
from .typing_planner_preparation_v1 import PreparedTypingPlannerV1
from .typing_ik_effort_telemetry_v1 import TypingIkEffortRecorderV1
from .typing_exact_ik_result_cache_v1 import ExactTypingIkResultCacheV1
from .typing_endpoint_atlas_observer_v1 import TypingEndpointAtlasRecorderV1
from .typing_endpoint_reuse_verifier_v1 import TypingEndpointReuseVerifierV1
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


SCHEMA = "rocell.typing_shadow_pipeline.v1"
STATUS = "BLOCKED_AT_HONEST_COLLISION_EVIDENCE_BOUNDARY"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
STAGE_HASH_KEYS = (
    "payload_sha256",
    "batch_sha256",
    "ingress_sha256",
    "freshness_sha256",
    "typing_execution_plan_sha256",
    "typing_trajectory_plan_sha256",
    "typing_trajectory_ik_screen_sha256",
    "typing_joint_schedule_sha256",
    "typing_collision_intake_sha256",
)
TERMINAL_BLOCKERS = (
    "INSTALLED_COLLISION_PROFILE_REQUIRED",
    "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
)


class TypingShadowPipelineV1Error(ValueError):
    """A stage failed before the golden zero-I/O receipt could be composed."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingShadowPipelineV1Error("stage output is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TypingShadowPipelineV1Error(f"{label} must be a SHA-256 digest")
    return value


def parse_typing_shadow_pipeline_v1(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Verify and freeze one exact PC2 zero-authority terminal receipt."""

    if not isinstance(document, Mapping):
        raise TypingShadowPipelineV1Error("shadow receipt must be an object")
    expected = {
        "schema",
        "status",
        "request_id",
        "ordered_target_ids",
        "action_count",
        "stage_hashes",
        "terminal_stage",
        "terminal_stage_status",
        "terminal_blockers",
        "controller_commands",
        "hardware_commands_generated",
        "hardware_access",
        "physical_authority",
        "typing_shadow_pipeline_sha256",
    }
    if set(document) != expected:
        raise TypingShadowPipelineV1Error(
            "shadow receipt fields differ from the canonical contract"
        )
    claimed = _digest(
        document["typing_shadow_pipeline_sha256"],
        "typing_shadow_pipeline_sha256",
    )
    unsigned = dict(document)
    unsigned.pop("typing_shadow_pipeline_sha256")
    if _sha256(unsigned) != claimed:
        raise TypingShadowPipelineV1Error("shadow receipt hash is invalid")
    if document["schema"] != SCHEMA or document["status"] != STATUS:
        raise TypingShadowPipelineV1Error("shadow receipt status or schema is invalid")
    request_id = document["request_id"]
    if (
        not isinstance(request_id, str)
        or not request_id
        or request_id != request_id.strip()
        or len(request_id) > 128
    ):
        raise TypingShadowPipelineV1Error("request_id is invalid")
    targets = document["ordered_target_ids"]
    if (
        not isinstance(targets, list)
        or not 1 <= len(targets) <= 64
        or any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or len(item) > 128
            for item in targets
        )
        or document["action_count"] != len(targets)
    ):
        raise TypingShadowPipelineV1Error("ordered targets or action count is invalid")
    hashes = document["stage_hashes"]
    if not isinstance(hashes, Mapping) or set(hashes) != set(STAGE_HASH_KEYS):
        raise TypingShadowPipelineV1Error(
            "stage hashes must use the exact canonical stage keys"
        )
    for key in STAGE_HASH_KEYS:
        _digest(hashes[key], f"stage_hashes.{key}")
    if (
        document["terminal_stage"] != "COLLISION_EVIDENCE_INTAKE"
        or document["terminal_stage_status"]
        != "BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED"
        or tuple(document["terminal_blockers"]) != TERMINAL_BLOCKERS
    ):
        raise TypingShadowPipelineV1Error("terminal blocker lineage is invalid")
    if (
        document["controller_commands"] != []
        or document["hardware_commands_generated"] != 0
        or document["hardware_access"] is not False
        or document["physical_authority"] is not False
    ):
        raise TypingShadowPipelineV1Error("shadow receipt violates zero authority")
    frozen = dict(document)
    frozen["ordered_target_ids"] = tuple(targets)
    frozen["stage_hashes"] = MappingProxyType(
        {key: hashes[key] for key in STAGE_HASH_KEYS}
    )
    frozen["terminal_blockers"] = tuple(document["terminal_blockers"])
    frozen["controller_commands"] = ()
    return MappingProxyType(frozen)


def run_typing_shadow_pipeline_v1(
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
    ik_policy: TrajectorySimulationPolicy | None = None,
    installed_collision_profile: InstalledCollisionGeometryProfile | None = None,
    collision_sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    context_lifecycle: SimulationContextLifecycleV1 | None = None,
    prepared_planner: PreparedTypingPlannerV1 | None = None,
    ik_effort_recorder: TypingIkEffortRecorderV1 | None = None,
    endpoint_atlas_recorder: TypingEndpointAtlasRecorderV1 | None = None,
    endpoint_reuse_verifier: TypingEndpointReuseVerifierV1 | None = None,
    exact_ik_result_cache: ExactTypingIkResultCacheV1 | None = None,
    materialization_recorder: Any | None = None,
) -> dict[str, Any]:
    """Run exact production boundaries through their honest offline blocker.

    The function has no transport dependency and exposes no callback capable of
    writing to hardware.  A successful receipt means composition succeeded; it
    does not mean collision evidence, fresh state, or physical authority exists.
    """

    if (context_lifecycle is None) != (prepared_planner is None):
        raise TypingShadowPipelineV1Error(
            "context lifecycle and prepared planner must be supplied together"
        )
    batch = decode_model_motion_batch_v2_json(payload)
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
    execution = compile_typing_execution_plan_v1(
        batch,
        ingress,
        config=execution_config,
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution,
        policy=trajectory_policy,
    )
    ik = screen_typing_trajectory_ik_v1(
        execution,
        trajectory,
        context,
        calibration_snapshot,
        ik_seed,
        policy=ik_policy,
        prepared_planner=prepared_planner,
        context_lifecycle=context_lifecycle,
        effort_recorder=ik_effort_recorder,
        endpoint_atlas_recorder=endpoint_atlas_recorder,
        endpoint_reuse_verifier=endpoint_reuse_verifier,
        exact_result_cache=exact_ik_result_cache,
    )
    if ik.get("status") != IK_READY_STATUS:
        raise TypingShadowPipelineV1Error(
            "golden shadow route did not reach the accepted offline IK boundary"
        )
    schedule = compile_typing_joint_schedule_v1(
        trajectory,
        ik,
        joint_dynamics_profile,
    )
    collision = prepare_typing_collision_intake_v1(
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
    if materialization_recorder is not None:
        from .typing_shadow_materialization_v1 import (
            TypingShadowMaterializationRecorderV1,
        )
        if not isinstance(
            materialization_recorder, TypingShadowMaterializationRecorderV1
        ):
            raise TypingShadowPipelineV1Error(
                "materialization recorder type differs"
            )
        materialization_recorder.capture(
            request_id=batch.request_id, execution=execution,
            trajectory=trajectory, ik=ik, schedule=schedule,
            collision=collision,
        )
    ordered_targets = [action.target_id for action in execution.actions]
    if ordered_targets != [proposal.target_id for proposal in batch.proposals]:
        raise TypingShadowPipelineV1Error("action order changed during composition")
    stage_hashes: Mapping[str, str] = {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": _sha256(freshness),
        "typing_execution_plan_sha256": execution.plan_sha256,
        "typing_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "typing_trajectory_ik_screen_sha256": ik[
            "typing_trajectory_ik_screen_sha256"
        ],
        "typing_joint_schedule_sha256": schedule.schedule_sha256,
        "typing_collision_intake_sha256": collision[
            "typing_collision_intake_sha256"
        ],
    }
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": batch.request_id,
        "ordered_target_ids": ordered_targets,
        "action_count": len(ordered_targets),
        "stage_hashes": dict(stage_hashes),
        "terminal_stage": "COLLISION_EVIDENCE_INTAKE",
        "terminal_stage_status": collision["status"],
        "terminal_blockers": collision["blockers"],
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**receipt, "typing_shadow_pipeline_sha256": _sha256(receipt)}


__all__ = [
    "SCHEMA",
    "STATUS",
    "TypingShadowPipelineV1Error",
    "parse_typing_shadow_pipeline_v1",
    "run_typing_shadow_pipeline_v1",
]
