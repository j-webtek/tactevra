"""Re-screen one retained typing trajectory from authenticated observed joints.

The canonical deterministic IK implementation is reused unchanged.  This
adapter binds its result back to the retained materialization and observed seed
while explicitly leaving route-entry, dynamics, collision, effect, review, and
execution gates closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from rocell.calibration import PlannerCalibrationSnapshot

from .context import SimulationContext
from .typing_execution_plan_v1 import (
    TypingExecutionPlanV1,
    TypingExecutionPlanV1Error,
)
from .typing_observed_ik_seed_v1 import TypingObservedIkSeedV1
from .typing_shadow_materialization_v1 import (
    TypingShadowMaterializationV1Error,
    parse_typing_shadow_materialization_v1,
)
from .typing_trajectory_ik_screen_v1 import (
    BLOCKED_STATUS as IK_BLOCKED_STATUS,
    READY_STATUS as IK_READY_STATUS,
    TypingTrajectoryIkScreenV1Error,
    screen_typing_trajectory_ik_v1,
)
from .typing_trajectory_plan_v1 import (
    TypingTrajectoryPlanV1Error,
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)


SCHEMA = "rocell.typing_observed_trajectory_ik.v1"
READY_STATUS = "READY_FOR_ROUTE_ENTRY_DYNAMICS_AND_COLLISION_QUALIFICATION"
BLOCKED_STATUS = "BLOCKED_OBSERVED_STATE_IK_SCREENING"
REQUIRED_NEXT_EVIDENCE = (
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
    "OBSERVED_START_TO_ROUTE_ENTRY_ENVELOPE_REQUIRED",
    "PHYSICALLY_QUALIFIED_DYNAMICS_REQUIRED",
    "INSTALLED_COLLISION_PROFILE_REQUIRED",
    "CONTINUOUS_COLLISION_QUALIFICATION_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "status", "request_id", "materialization_sha256",
    "observed_ik_seed_sha256", "observed_start_state_sha256",
    "canonical_ik_screen_sha256", "calibration_snapshot_sha256",
    "build_snapshot_sha256", "controller_session_id",
    "evaluated_monotonic_ns", "sample_count", "evaluated_sample_count",
    "ik_all_samples_accepted", "measured_start_state_applied",
    "route_entry_envelope_completed", "measured_dynamics_qualified",
    "collision_screening_executed", "continuous_collision_proven",
    "required_next_evidence", "canonical_ik_screen",
    "permit_review_ready", "eligible_for_executor", "automatic_retry_allowed",
    "controller_commands", "wire_commands", "hardware_commands_generated",
    "hardware_access", "physical_authority",
    "observed_trajectory_ik_sha256",
}


class TypingObservedTrajectoryIkV1Error(ValueError):
    """Observed-seed trajectory screening lineage or result differs."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedTrajectoryIkV1Error(
            "observed trajectory IK report is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _positive_ns(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypingObservedTrajectoryIkV1Error(
            "evaluated_monotonic_ns must be a positive integer"
        )
    return value


def _retained_plans(materialized: Mapping[str, Any]):
    try:
        source = TypingExecutionPlanV1.from_mapping(
            materialized["stage_artifacts"]["typing_execution_plan"]
        )
        retained = materialized["stage_artifacts"]["typing_trajectory_plan"]
        raw_policy = retained["policy"]
        policy = TypingTrajectoryPolicyV1(
            policy_id=raw_policy["policy_id"],
            maximum_cartesian_step_mm=raw_policy["maximum_cartesian_step_mm"],
            maximum_velocity_mm_s=raw_policy["maximum_velocity_mm_s"],
            maximum_acceleration_mm_s2=raw_policy["maximum_acceleration_mm_s2"],
            maximum_jerk_mm_s3=raw_policy["maximum_jerk_mm_s3"],
            hover_settle_ms=raw_policy["hover_settle_ms"],
            contact_dwell_ms=raw_policy["contact_dwell_ms"],
            schema=raw_policy["schema"],
        )
        trajectory = compile_typing_trajectory_plan_v1(source, policy=policy)
    except (KeyError, TypeError, TypingExecutionPlanV1Error,
            TypingTrajectoryPlanV1Error) as exc:
        raise TypingObservedTrajectoryIkV1Error(
            "retained typing plans cannot be reconstructed exactly"
        ) from exc
    if trajectory.to_dict() != retained:
        raise TypingObservedTrajectoryIkV1Error(
            "retained trajectory does not replay from its execution plan"
        )
    return source, trajectory


def screen_typing_observed_trajectory_ik_v1(
    materialization: Mapping[str, Any],
    seed: TypingObservedIkSeedV1,
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    *,
    evaluated_monotonic_ns: int,
) -> dict[str, Any]:
    """Run canonical IK from measured joints and retain all remaining gates."""

    if not isinstance(materialization, Mapping):
        raise TypeError("materialization must be a mapping")
    if not isinstance(seed, TypingObservedIkSeedV1):
        raise TypeError("seed must be a TypingObservedIkSeedV1")
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise TypeError("snapshot must be a PlannerCalibrationSnapshot")
    now = _positive_ns(evaluated_monotonic_ns)
    try:
        materialized = parse_typing_shadow_materialization_v1(materialization)
    except TypingShadowMaterializationV1Error as exc:
        raise TypingObservedTrajectoryIkV1Error(str(exc)) from exc
    if (
        seed.request_id != materialized["request_id"]
        or seed.materialization_sha256 != materialized["materialization_sha256"]
    ):
        raise TypingObservedTrajectoryIkV1Error(
            "observed IK seed belongs to a different materialization"
        )
    if not seed.available_monotonic_ns <= now <= seed.valid_until_monotonic_ns:
        raise TypingObservedTrajectoryIkV1Error(
            "observed IK seed is unavailable or stale"
        )
    if (
        seed.calibration_snapshot_sha256 != snapshot.snapshot_sha256
        or seed.build_snapshot_sha256 != context.snapshot.snapshot_hash
    ):
        raise TypingObservedTrajectoryIkV1Error(
            "observed seed differs from active calibration or build"
        )

    source, trajectory = _retained_plans(materialized)
    try:
        canonical_screen = screen_typing_trajectory_ik_v1(
            source, trajectory, context, snapshot, seed
        )
    except TypingTrajectoryIkScreenV1Error as exc:
        raise TypingObservedTrajectoryIkV1Error(str(exc)) from exc
    accepted = (
        canonical_screen["status"] == IK_READY_STATUS
        and canonical_screen["ik_all_samples_accepted"] is True
        and canonical_screen["evaluated_sample_count"]
        == canonical_screen["sample_count"]
    )
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": READY_STATUS if accepted else BLOCKED_STATUS,
        "request_id": materialized["request_id"],
        "materialization_sha256": materialized["materialization_sha256"],
        "observed_ik_seed_sha256": seed.observed_ik_seed_sha256,
        "observed_start_state_sha256": seed.observed_start_state_sha256,
        "canonical_ik_screen_sha256": canonical_screen[
            "typing_trajectory_ik_screen_sha256"
        ],
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "controller_session_id": seed.controller_session_id,
        "evaluated_monotonic_ns": now,
        "sample_count": canonical_screen["sample_count"],
        "evaluated_sample_count": canonical_screen["evaluated_sample_count"],
        "ik_all_samples_accepted": accepted,
        "measured_start_state_applied": True,
        "route_entry_envelope_completed": False,
        "measured_dynamics_qualified": False,
        "collision_screening_executed": False,
        "continuous_collision_proven": False,
        "required_next_evidence": list(REQUIRED_NEXT_EVIDENCE),
        "canonical_ik_screen": canonical_screen,
        "permit_review_ready": False,
        "eligible_for_executor": False,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "observed_trajectory_ik_sha256": _sha(core)}


def parse_typing_observed_trajectory_ik_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a sealed observed-state IK report without promoting authority."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedTrajectoryIkV1Error(
            "observed trajectory IK fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("observed_trajectory_ik_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedTrajectoryIkV1Error(
            "observed trajectory IK hash differs"
        )
    canonical_screen = value["canonical_ik_screen"]
    if not isinstance(canonical_screen, Mapping):
        raise TypingObservedTrajectoryIkV1Error("canonical IK screen is absent")
    canonical_seed = canonical_screen.get("seed")
    if not isinstance(canonical_seed, Mapping):
        raise TypingObservedTrajectoryIkV1Error(
            "canonical IK screen observed seed is absent"
        )
    screen_hash = canonical_screen.get("typing_trajectory_ik_screen_sha256")
    unsigned_screen = dict(canonical_screen)
    unsigned_screen.pop("typing_trajectory_ik_screen_sha256", None)
    accepted = value["ik_all_samples_accepted"]
    expected_status = READY_STATUS if accepted else BLOCKED_STATUS
    digest_fields = (
        "materialization_sha256", "observed_ik_seed_sha256",
        "observed_start_state_sha256", "canonical_ik_screen_sha256",
        "calibration_snapshot_sha256", "build_snapshot_sha256",
    )
    if (
        value["schema"] != SCHEMA
        or not isinstance(value["request_id"], str)
        or not value["request_id"]
        or not isinstance(value["controller_session_id"], str)
        or not value["controller_session_id"]
        or any(_SHA.fullmatch(value[field] or "") is None for field in digest_fields)
        or not isinstance(screen_hash, str)
        or _SHA.fullmatch(screen_hash) is None
        or screen_hash != _sha(unsigned_screen)
        or value["canonical_ik_screen_sha256"] != screen_hash
        or canonical_seed.get("source_kind") != "PHYSICAL_OBSERVED_STATE"
        or canonical_seed.get("request_id") != value["request_id"]
        or canonical_seed.get("materialization_sha256")
        != value["materialization_sha256"]
        or canonical_seed.get("observed_ik_seed_sha256")
        != value["observed_ik_seed_sha256"]
        or canonical_seed.get("seed_sha256")
        != value["observed_ik_seed_sha256"]
        or canonical_seed.get("observed_start_state_sha256")
        != value["observed_start_state_sha256"]
        or canonical_seed.get("calibration_snapshot_sha256")
        != value["calibration_snapshot_sha256"]
        or canonical_seed.get("build_snapshot_sha256")
        != value["build_snapshot_sha256"]
        or canonical_seed.get("controller_session_id")
        != value["controller_session_id"]
        or canonical_seed.get("controller_feedback_claimed") is not True
        or canonical_seed.get("physical_measurement_claimed") is not True
        or value["status"] != expected_status
        or not isinstance(value["sample_count"], int)
        or isinstance(value["sample_count"], bool)
        or value["sample_count"] < 1
        or not isinstance(value["evaluated_sample_count"], int)
        or isinstance(value["evaluated_sample_count"], bool)
        or not 0 <= value["evaluated_sample_count"] <= value["sample_count"]
        or canonical_screen.get("sample_count") != value["sample_count"]
        or canonical_screen.get("evaluated_sample_count")
        != value["evaluated_sample_count"]
        or canonical_screen.get("ik_all_samples_accepted") is not accepted
        or canonical_screen.get("status")
        != (IK_READY_STATUS if accepted else IK_BLOCKED_STATUS)
        or accepted is not (value["evaluated_sample_count"] == value["sample_count"])
        or not isinstance(value["evaluated_monotonic_ns"], int)
        or isinstance(value["evaluated_monotonic_ns"], bool)
        or value["evaluated_monotonic_ns"] <= 0
        or value["required_next_evidence"] != list(REQUIRED_NEXT_EVIDENCE)
        or value["measured_start_state_applied"] is not True
        or value["route_entry_envelope_completed"] is not False
        or value["measured_dynamics_qualified"] is not False
        or value["collision_screening_executed"] is not False
        or value["continuous_collision_proven"] is not False
        or value["permit_review_ready"] is not False
        or value["eligible_for_executor"] is not False
        or value["automatic_retry_allowed"] is not False
        or value["controller_commands"] != []
        or value["wire_commands"] != []
        or value["hardware_commands_generated"] != 0
        or value["hardware_access"] is not False
        or value["physical_authority"] is not False
        or canonical_screen.get("collision_screening_executed") is not False
        or canonical_screen.get("continuous_collision_proven") is not False
        or canonical_screen.get("controller_commands") != []
        or canonical_screen.get("hardware_commands_generated") != 0
        or canonical_screen.get("hardware_access") is not False
        or canonical_screen.get("physical_authority") is not False
    ):
        raise TypingObservedTrajectoryIkV1Error(
            "observed trajectory IK lineage, gates, or authority differs"
        )
    return dict(value)


__all__ = [
    "BLOCKED_STATUS", "READY_STATUS", "REQUIRED_NEXT_EVIDENCE", "SCHEMA",
    "TypingObservedTrajectoryIkV1Error",
    "parse_typing_observed_trajectory_ik_v1",
    "screen_typing_observed_trajectory_ik_v1",
]
