"""Deterministic, zero-authority IK screening for T2A typing samples.

This boundary consumes the exact Cartesian samples emitted by
``typing_trajectory_plan_v1``.  It deliberately does not infer installed
collision geometry, create controller commands, or grant physical authority.
An accepted report means only that every supplied sample passed the canonical
numerical-IK, calibrated-joint-bound, margin, Jacobian-rank, and adjacent-joint
continuity gates for the pinned offline context.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.geometry import JointPosition, Point3Mm, RigidTransform
from rocell.kinematics import (
    ARM_JOINT_NAMES,
    BoardToolTipTarget,
    IkOptions,
    RoArmM3NumericalIk,
)

from ._pinned_model import load_pinned_urdf
from .context import SimulationContext, revalidate_simulation_context
from .context_lifecycle_v1 import (
    SimulationContextLifecycleBindingV1,
    SimulationContextLifecycleV1,
)
from .measured_trajectory_screening import _compatibility_blockers, _planner_bounds
from .trajectory_simulation import (
    CartesianRouteWaypoint,
    TrajectorySimulationPolicy,
    evaluate_joint_trajectory_solution,
)
from .typing_execution_plan_v1 import TypingExecutionPlanV1
from .typing_trajectory_plan_v1 import TypingTrajectoryPlanV1
from .typing_trajectory_plan_v1 import compile_typing_trajectory_plan_v1
from .typing_planner_preparation_v1 import (
    PreparedTypingPlannerV1,
    validate_prepared_typing_planner_v1,
)
from .typing_ik_effort_telemetry_v1 import TypingIkEffortRecorderV1
from .typing_exact_ik_result_cache_v1 import ExactTypingIkResultCacheV1
from .typing_endpoint_atlas_observer_v1 import TypingEndpointAtlasRecorderV1
from .typing_endpoint_reuse_verifier_v1 import TypingEndpointReuseVerifierV1


SCHEMA = "rocell.typing_trajectory_ik_screen.v1"
SEED_SCHEMA = "rocell.typing_trajectory_ik_seed.v1"
READY_STATUS = "READY_FOR_INSTALLED_GEOMETRY_COLLISION_SCREENING"
BLOCKED_STATUS = "BLOCKED_DETERMINISTIC_IK_OR_CONTINUITY"
EVIDENCE_FLOAT_DECIMAL_PLACES = 6


class TypingTrajectoryIkScreenV1Error(ValueError):
    """The T2A plan and offline IK evidence cannot be screened exactly."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def canonicalize_typing_ik_evidence_v1(value: Any) -> Any:
    """Quantize numerical IK evidence at a platform-independent boundary.

    The bounded numerical solver can produce sub-micrometre or sub-microradian
    differences across otherwise equivalent Python/BLAS platforms.  Those
    differences are irrelevant to the safety decisions, but hashing the raw
    floats would give equivalent command plans different evidence identities.
    Six decimal places remains far finer than the installed arm can resolve
    while providing one stable representation for retained evidence.
    """

    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypingTrajectoryIkScreenV1Error(
                "IK evidence must contain only finite numbers"
            )
        quantized = round(value, EVIDENCE_FLOAT_DECIMAL_PLACES)
        return 0.0 if quantized == 0.0 else quantized
    if isinstance(value, Mapping):
        return {
            key: canonicalize_typing_ik_evidence_v1(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [canonicalize_typing_ik_evidence_v1(item) for item in value]
    raise TypingTrajectoryIkScreenV1Error(
        f"unsupported IK evidence value type: {type(value).__name__}"
    )


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TypingTrajectoryIkScreenV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


@dataclass(frozen=True, slots=True)
class TypingTrajectoryIkSeedV1:
    """Pinned joint seed for an explicitly offline screening attempt."""

    seed_id: str
    calibration_snapshot_sha256: str
    build_snapshot_sha256: str
    joint_positions_rad: Mapping[str, float]
    source_kind: str = "SYNTHETIC_OFFLINE"
    schema: str = SEED_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SEED_SCHEMA:
            raise TypingTrajectoryIkScreenV1Error("unsupported IK seed schema")
        if (
            not isinstance(self.seed_id, str)
            or not self.seed_id
            or self.seed_id != self.seed_id.strip()
            or len(self.seed_id) > 128
        ):
            raise TypingTrajectoryIkScreenV1Error(
                "seed_id must be bounded nonempty unpadded text"
            )
        if self.source_kind != "SYNTHETIC_OFFLINE":
            raise TypingTrajectoryIkScreenV1Error(
                "only an explicitly synthetic offline seed is accepted"
            )
        _digest(self.calibration_snapshot_sha256, "calibration_snapshot_sha256")
        _digest(self.build_snapshot_sha256, "build_snapshot_sha256")
        if set(self.joint_positions_rad) != set(ARM_JOINT_NAMES):
            raise TypingTrajectoryIkScreenV1Error(
                "joint_positions_rad must use the exact canonical arm-joint set"
            )
        parsed: dict[str, float] = {}
        for name in ARM_JOINT_NAMES:
            raw = self.joint_positions_rad[name]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise TypingTrajectoryIkScreenV1Error(
                    f"joint_positions_rad.{name} must be numeric"
                )
            number = float(raw)
            if not math.isfinite(number):
                raise TypingTrajectoryIkScreenV1Error(
                    f"joint_positions_rad.{name} must be finite"
                )
            parsed[name] = number
        object.__setattr__(
            self,
            "joint_positions_rad",
            MappingProxyType(parsed),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "seed_id": self.seed_id,
            "source_kind": self.source_kind,
            "calibration_snapshot_sha256": self.calibration_snapshot_sha256,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "joint_positions_rad": dict(self.joint_positions_rad),
            "controller_feedback_claimed": False,
            "physical_measurement_claimed": False,
        }

    @property
    def seed_sha256(self) -> str:
        return _sha256(self.to_dict())


def _waypoint(
    plan: TypingTrajectoryPlanV1,
    index: int,
) -> CartesianRouteWaypoint:
    sample = plan.screening_samples[index]
    point = Point3Mm("board", sample.point.x, sample.point.y, sample.point.z)
    if index == 0:
        distance = 0.0
    else:
        previous = plan.screening_samples[index - 1].point
        distance = math.dist(
            (previous.x, previous.y, previous.z),
            (sample.point.x, sample.point.y, sample.point.z),
        )
    return CartesianRouteWaypoint(
        sequence=sample.sequence,
        phase=sample.phase,
        action_index=sample.action_index,
        semantic_target=sample.target_id,
        point_board=point,
        distance_from_previous_mm=distance,
        source_geometric_sequence=sample.endpoint_sequence,
        source_check_id=plan.trajectory_plan_sha256,
        source_path_check_passed=True,
        inherited_collision_ids=(),
        phase_endpoint=sample.phase_endpoint,
    )


def screen_typing_trajectory_ik_v1(
    source_plan: TypingExecutionPlanV1,
    plan: TypingTrajectoryPlanV1,
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    seed: TypingTrajectoryIkSeedV1,
    *,
    policy: TrajectorySimulationPolicy | None = None,
    prepared_planner: PreparedTypingPlannerV1 | None = None,
    context_lifecycle: SimulationContextLifecycleV1 | None = None,
    effort_recorder: TypingIkEffortRecorderV1 | None = None,
    endpoint_atlas_recorder: TypingEndpointAtlasRecorderV1 | None = None,
    endpoint_reuse_verifier: TypingEndpointReuseVerifierV1 | None = None,
    exact_result_cache: ExactTypingIkResultCacheV1 | None = None,
    _lifecycle_binding: SimulationContextLifecycleBindingV1 | None = None,
) -> dict[str, Any]:
    """Run the canonical deterministic IK gates over every exact T2A sample."""

    if not isinstance(source_plan, TypingExecutionPlanV1):
        raise TypeError("source_plan must be a TypingExecutionPlanV1")
    if not isinstance(plan, TypingTrajectoryPlanV1):
        raise TypeError("plan must be a TypingTrajectoryPlanV1")
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise TypeError("snapshot must be a PlannerCalibrationSnapshot")
    if not isinstance(seed, TypingTrajectoryIkSeedV1):
        raise TypeError("seed must be a TypingTrajectoryIkSeedV1")
    if effort_recorder is not None and not isinstance(
        effort_recorder, TypingIkEffortRecorderV1
    ):
        raise TypeError("effort_recorder must be a TypingIkEffortRecorderV1")
    if endpoint_atlas_recorder is not None and not isinstance(
        endpoint_atlas_recorder, TypingEndpointAtlasRecorderV1
    ):
        raise TypeError(
            "endpoint_atlas_recorder must be a TypingEndpointAtlasRecorderV1"
        )
    if endpoint_reuse_verifier is not None and not isinstance(
        endpoint_reuse_verifier, TypingEndpointReuseVerifierV1
    ):
        raise TypeError(
            "endpoint_reuse_verifier must be a TypingEndpointReuseVerifierV1"
        )
    if exact_result_cache is not None and not isinstance(
        exact_result_cache, ExactTypingIkResultCacheV1
    ):
        raise TypeError("exact_result_cache must be an ExactTypingIkResultCacheV1")
    if (
        (exact_result_cache is not None or endpoint_reuse_verifier is not None)
        and context_lifecycle is None
        and _lifecycle_binding is None
    ):
        raise TypingTrajectoryIkScreenV1Error(
            "IK reuse experiments require lifecycle-managed admission"
        )
    if context_lifecycle is not None:
        if _lifecycle_binding is not None:
            raise TypingTrajectoryIkScreenV1Error(
                "nested context lifecycle binding is invalid"
            )
        if not isinstance(context_lifecycle, SimulationContextLifecycleV1):
            raise TypeError("context_lifecycle must be SimulationContextLifecycleV1")
        if not isinstance(prepared_planner, PreparedTypingPlannerV1):
            raise TypingTrajectoryIkScreenV1Error(
                "lifecycle-managed IK requires prepared planner resources"
            )
        with context_lifecycle.validation_scope(context) as binding:
            validate_prepared_typing_planner_v1(prepared_planner, binding)
            return screen_typing_trajectory_ik_v1(
                source_plan,
                plan,
                context,
                snapshot,
                seed,
                policy=policy,
                prepared_planner=prepared_planner,
                effort_recorder=effort_recorder,
                endpoint_atlas_recorder=endpoint_atlas_recorder,
                endpoint_reuse_verifier=endpoint_reuse_verifier,
                exact_result_cache=exact_result_cache,
                _lifecycle_binding=binding,
            )
    if _lifecycle_binding is None:
        if prepared_planner is not None:
            raise TypingTrajectoryIkScreenV1Error(
                "prepared planner requires lifecycle-managed admission"
            )
        revalidate_simulation_context(context)
    else:
        if not isinstance(prepared_planner, PreparedTypingPlannerV1):
            raise TypingTrajectoryIkScreenV1Error(
                "lifecycle binding requires prepared planner resources"
            )
        validate_prepared_typing_planner_v1(prepared_planner, _lifecycle_binding)
    if (
        source_plan.plan_sha256 != plan.source_plan_sha256
        or source_plan.config.calibration_snapshot_sha256 != snapshot.snapshot_sha256
        or snapshot.manifest_id != context.snapshot.manifest_id
        or snapshot.active_build_id != context.snapshot.active_build_id
        or seed.calibration_snapshot_sha256 != snapshot.snapshot_sha256
        or seed.build_snapshot_sha256 != context.snapshot.snapshot_hash
    ):
        raise TypingTrajectoryIkScreenV1Error(
            "source plan, seed, calibration, build, and active context identities differ"
        )
    replayed = compile_typing_trajectory_plan_v1(source_plan, policy=plan.policy)
    if replayed.to_bytes() != plan.to_bytes():
        raise TypingTrajectoryIkScreenV1Error(
            "trajectory plan does not replay from the exact T1 source plan"
        )

    selected_policy = policy or TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=max(
            1.0, plan.policy.maximum_cartesian_step_mm
        ),
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=256,
        maximum_total_ik_solves=256,
    )
    if not isinstance(selected_policy, TrajectorySimulationPolicy):
        raise TypeError("policy must be a TrajectorySimulationPolicy")
    samples = plan.screening_samples
    if not samples:
        raise TypingTrajectoryIkScreenV1Error("trajectory contains no screening samples")
    if (
        len(samples) > selected_policy.maximum_waypoints_per_round
        or len(samples) > selected_policy.maximum_total_ik_solves
    ):
        raise TypingTrajectoryIkScreenV1Error(
            "trajectory sample count exceeds the selected bounded IK policy"
        )
    if any(sample.sequence != index for index, sample in enumerate(samples)):
        raise TypingTrajectoryIkScreenV1Error(
            "trajectory screening samples are not canonically ordered"
        )
    if any(
        math.dist(
            (left.point.x, left.point.y, left.point.z),
            (right.point.x, right.point.y, right.point.z),
        ) > selected_policy.maximum_cartesian_step_mm + 1e-9
        for left, right in zip(samples, samples[1:])
    ):
        raise TypingTrajectoryIkScreenV1Error(
            "trajectory sample spacing exceeds the selected IK policy"
        )

    bounds = _planner_bounds(context, snapshot)
    previous: dict[str, float] = {}
    for name in ARM_JOINT_NAMES:
        value = seed.joint_positions_rad[name]
        lower, upper = bounds[name]
        if not lower <= value <= upper:
            raise TypingTrajectoryIkScreenV1Error(
                f"seed joint {name} leaves calibrated planner bounds"
            )
        previous[name] = value

    blockers = _compatibility_blockers(snapshot)
    results: list[dict[str, Any]] = []
    ik_executed = False
    if not blockers:
        model = (
            prepared_planner.loaded_model.model
            if prepared_planner is not None
            else load_pinned_urdf(
                context.scenario.model_path,
                context.scenario.model_sha256,
            ).model
        )
        solver = RoArmM3NumericalIk(
            model=model,
            board_T_world=RigidTransform(
                "board",
                "world",
                snapshot.board_T_vendor_world.rotation,
                snapshot.board_T_vendor_world.translation_mm,
            ),
            hand_tcp_to_tip_z_mm=snapshot.hand_T_tool.translation_mm.z,
            fixed_gripper_position=context.scenario.fixed_gripper_position,
            ready_arm_joint_positions={
                name: JointPosition.radians(value)
                for name, value in previous.items()
            },
            gripper_bounds_rad=context.scenario.controller_gripper_intersection_rad,
            options=IkOptions(
                max_attempts=context.scenario.ik_policy.max_attempts,
                max_iterations_per_attempt=(
                    context.scenario.ik_policy.max_iterations_per_attempt
                ),
            ),
            joint_bounds_rad=bounds,
        )
        solver_source_sha256 = None
        if (
            effort_recorder is not None
            or exact_result_cache is not None
            or endpoint_reuse_verifier is not None
        ):
            solver_source = inspect.getsourcefile(type(solver))
            if solver_source is None:
                raise TypingTrajectoryIkScreenV1Error(
                    "IK telemetry cannot bind the active solver source"
                )
            solver_source_path = Path(solver_source).resolve()
            if solver_source_path.stat().st_size > 2_000_000:
                raise TypingTrajectoryIkScreenV1Error(
                    "IK solver source exceeds its telemetry hash bound"
                )
            solver_source_sha256 = hashlib.sha256(
                solver_source_path.read_bytes()
            ).hexdigest()
        endpoint_reuse_context_sha256 = _sha256({
            "schema": "rocell.typing_endpoint_reuse_context.v1",
            "build_snapshot_sha256": context.snapshot.snapshot_hash,
            "kinematic_model_sha256": context.scenario.model_sha256,
            "calibration_snapshot_sha256": snapshot.snapshot_sha256,
            "joint_bounds_rad": {
                name: list(bounds[name]) for name in ARM_JOINT_NAMES
            },
            "fixed_gripper_position_rad": (
                context.scenario.fixed_gripper_position.value
            ),
            "ik_options": {
                "max_attempts": context.scenario.ik_policy.max_attempts,
                "max_iterations_per_attempt": (
                    context.scenario.ik_policy.max_iterations_per_attempt
                ),
            },
            "algorithm": "DETERMINISTIC_BOUNDED_DLS_V1",
            "solver_implementation": (
                f"{type(solver).__module__}.{type(solver).__qualname__}"
            ),
            "solver_source_sha256": solver_source_sha256,
        })
        ik_executed = True
        for index in range(len(samples)):
            waypoint = _waypoint(plan, index)
            solver_input_sha256 = _sha256({
                "schema": "rocell.typing_ik_solver_input.v1",
                "build_snapshot_sha256": context.snapshot.snapshot_hash,
                "kinematic_model_sha256": context.scenario.model_sha256,
                "calibration_snapshot_sha256": snapshot.snapshot_sha256,
                "target_board_mm": {
                    "frame": waypoint.point_board.frame,
                    "x": waypoint.point_board.x,
                    "y": waypoint.point_board.y,
                    "z": waypoint.point_board.z,
                },
                "incoming_seed_joint_positions_rad": {
                    name: previous[name] for name in ARM_JOINT_NAMES
                },
                "joint_bounds_rad": {
                    name: list(bounds[name]) for name in ARM_JOINT_NAMES
                },
                "fixed_gripper_position_rad": (
                    context.scenario.fixed_gripper_position.value
                ),
                "ik_options": {
                    "max_attempts": context.scenario.ik_policy.max_attempts,
                    "max_iterations_per_attempt": (
                        context.scenario.ik_policy.max_iterations_per_attempt
                    ),
                },
                "algorithm": "DETERMINISTIC_BOUNDED_DLS_V1",
                "solver_implementation": (
                    f"{type(solver).__module__}.{type(solver).__qualname__}"
                ),
                "solver_source_sha256": solver_source_sha256,
            })
            solved = None
            if exact_result_cache is not None:
                if _lifecycle_binding is None:
                    raise TypingTrajectoryIkScreenV1Error(
                        "exact IK cache lost its lifecycle binding"
                    )
                solved = exact_result_cache.lookup(
                    solver_input_sha256, _lifecycle_binding
                )
            if solved is None:
                solved = solver.solve(
                    BoardToolTipTarget(waypoint.point_board),
                    seed_joint_positions=(
                        {
                            name: JointPosition.radians(value)
                            for name, value in previous.items()
                        },
                    ),
                )
                if exact_result_cache is not None:
                    exact_result_cache.remember(
                        solver_input_sha256, solved, _lifecycle_binding
                    )
            if effort_recorder is not None:
                effort_recorder.observe(
                    index,
                    solved,
                    solver_input_sha256=solver_input_sha256,
                    previous_solution_seed_supplied=index > 0,
                )
            evaluated = evaluate_joint_trajectory_solution(
                waypoint,
                solved,
                solver,
                bounds,
                previous,
                selected_policy,
            )
            if endpoint_atlas_recorder is not None:
                endpoint_atlas_recorder.observe(
                    plan.screening_samples[index],
                    evaluated,
                    incoming_joint_positions_rad=previous,
                    solver_input_sha256=solver_input_sha256,
                )
            if endpoint_reuse_verifier is not None:
                if _lifecycle_binding is None:
                    raise TypingTrajectoryIkScreenV1Error(
                        "endpoint reuse verifier lost its lifecycle binding"
                    )
                endpoint_reuse_verifier.observe(
                    plan.screening_samples[index],
                    evaluated,
                    decision_context_sha256=endpoint_reuse_context_sha256,
                    binding=_lifecycle_binding,
                )
            canonical_result = canonicalize_typing_ik_evidence_v1(
                evaluated.to_dict()
            )
            results.append(canonical_result)
            if not evaluated.accepted:
                blockers.append(f"IK_ROUTE_REJECTED:{evaluated.failure_reason}")
                break
            # Keep full solver precision inside the current screening run.  The
            # canonicalized representation is an evidence boundary, not a new
            # numerical input or a change to endpoint-reuse behavior.
            previous = dict(evaluated.solution_arm_joint_positions_rad)

    all_accepted = (
        len(results) == len(samples)
        and bool(results)
        and all(item["accepted"] for item in results)
    )
    if all_accepted:
        status = READY_STATUS
        blockers.append("INSTALLED_GEOMETRY_COLLISION_SCREENING_REQUIRED")
        next_stage = "SCREEN_EXACT_JOINT_RESULTS_AGAINST_INSTALLED_GEOMETRY"
    else:
        status = BLOCKED_STATUS
        next_stage = "CORRECT_IK_COMPATIBILITY_OR_ROUTE_CONTINUITY"

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "typing_trajectory_plan_sha256": plan.trajectory_plan_sha256,
        "typing_execution_plan_sha256": plan.source_plan_sha256,
        "trajectory_policy_sha256": plan.policy.policy_sha256,
        "ik_policy": {
            **selected_policy.to_dict(),
            "policy_hash": selected_policy.policy_hash,
        },
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "seed": {**seed.to_dict(), "seed_sha256": seed.seed_sha256},
        "sample_count": len(samples),
        "evaluated_sample_count": len(results),
        "joint_results": results,
        "ik_screening_executed": ik_executed,
        "ik_all_samples_accepted": all_accepted,
        "joint_continuity_checked": ik_executed,
        "collision_screening_executed": False,
        "continuous_collision_proven": False,
        "blockers": list(dict.fromkeys(blockers)),
        "next_required_stage": next_stage,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**report, "typing_trajectory_ik_screen_sha256": _sha256(report)}


__all__ = [
    "SCHEMA",
    "SEED_SCHEMA",
    "READY_STATUS",
    "BLOCKED_STATUS",
    "EVIDENCE_FLOAT_DECIMAL_PLACES",
    "TypingTrajectoryIkScreenV1Error",
    "TypingTrajectoryIkSeedV1",
    "canonicalize_typing_ik_evidence_v1",
    "screen_typing_trajectory_ik_v1",
]
