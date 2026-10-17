"""Deterministic discrete-waypoint simulation for keyboard and phone routes.

The service in this module sits between independent-pose reach screening and a
future physical executor.  It constructs the existing nominal tool-tip route,
densifies every Cartesian segment, and solves the resulting waypoints in
sequence while feeding the previous selected joint state back as the first IK
seed.  Every selected state must satisfy the controller/URDF intersection, an
arm-joint margin, and a maximum adjacent sampled-joint delta.  This is not a
proof of continuity between those samples.

This is deliberately not a motion authority.  It cannot emit T=104 commands,
open a serial port, access a camera, or release any physical gate.  Tool-tip
centreline checks use nominal AABB proxies.  A bounded local solver-weighted
task-Jacobian rank diagnostic is evaluated at otherwise-valid selected joint
states.  Full physical singularity/manipulability acceptance, robot-link,
self, holder, camera, cable, tool-volume, dynamics, and force checks remain
explicitly unsupported physical blockers.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from rocell import __version__
from rocell.geometry import (
    JointPosition,
    Point3Mm,
    RigidTransform,
    Vec3,
)
from rocell.kinematics import (
    ARM_JOINT_NAMES,
    MAX_TASK_JACOBIAN_FK_EVALUATIONS,
    BoardToolTipTarget,
    IkContractError,
    IkOptions,
    IkResult,
    RoArmM3NumericalIk,
    WeightedTaskJacobianConditioning,
)
from rocell.models.actions import ActionPlan, PressKey, TapPhoneTarget
from rocell.models.units import finite_real
from rocell.motion import (
    GeometricDryRunEngine,
    GeometricPathCheck,
    GeometricPathStep,
    GeometricSimulationSettings,
    MotionPhase,
)

from .context import SimulationContext, revalidate_simulation_context
from ._pinned_model import (
    MAX_PINNED_URDF_BYTES,
    PinnedModelLoadError,
    load_pinned_urdf,
)
from .reach_optimizer import ReachStudyInput


_REQUIRED_MOTION_PHASES = frozenset(
    {
        MotionPhase.PARK,
        MotionPhase.TRANSIT,
        MotionPhase.HOVER,
        MotionPhase.APPROACH,
        MotionPhase.CONTACT,
        MotionPhase.RETRACT,
    }
)
_ARM_JOINT_COUNT = 5
_MAX_POLICY_WAYPOINTS = 512
_MAX_POLICY_IK_SOLVES = 1_024
_MAX_POLICY_ROUTE_TARGETS = 16
_MAX_POLICY_PLAN_ACTIONS = 2 * _MAX_POLICY_ROUTE_TARGETS + 1
_MAX_POLICY_REFINEMENTS = 3
_MAX_CANONICAL_IK_ATTEMPTS = 8
_MAX_CANONICAL_IK_ITERATIONS = 200
# The source-bound workbench now contains 637 modules. Keep a finite cap with
# growth room; the independent 20 MB aggregate and per-file limits still apply.
_MAX_IMPLEMENTATION_SOURCE_FILES = 2048
_MAX_IMPLEMENTATION_SOURCE_BYTES = 20_000_000
_MAX_IMPLEMENTATION_FILE_BYTES = 5_000_000
_CANONICAL_IK_SOLVER = RoArmM3NumericalIk
_CANONICAL_GEOMETRIC_ENGINE = GeometricDryRunEngine


class TrajectorySimulationError(ValueError):
    """A trajectory request violates a bounded simulation contract."""


def _stable_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _finite_vector3_tuple(
    value: object,
    label: str,
) -> tuple[float, float, float]:
    """Validate one immutable finite three-vector without losing tuple shape."""

    if not isinstance(value, tuple) or len(value) != 3:
        raise TrajectorySimulationError(
            f"{label} must be an immutable tuple of three finite numbers"
        )
    try:
        parsed = tuple(
            finite_real(component, name=f"{label}[{index}]")
            for index, component in enumerate(value)
        )
    except (TypeError, ValueError) as exc:
        raise TrajectorySimulationError(f"{label} must be finite") from exc
    return parsed[0], parsed[1], parsed[2]


def _hash_file_bounded(path: Path, maximum_bytes: int) -> tuple[str, int]:
    """Hash at most ``maximum_bytes`` actual bytes without stat/read TOCTOU."""

    digest = hashlib.sha256()
    actual_bytes = 0
    try:
        with path.open("rb") as stream:
            while True:
                remaining_with_sentinel = maximum_bytes - actual_bytes + 1
                chunk = stream.read(min(65_536, remaining_with_sentinel))
                if not chunk:
                    break
                actual_bytes += len(chunk)
                if actual_bytes > maximum_bytes:
                    raise TrajectorySimulationError(
                        f"implementation source exceeds {maximum_bytes} bytes"
                    )
                digest.update(chunk)
    except OSError as exc:
        raise TrajectorySimulationError(
            f"cannot bind implementation source {path}"
        ) from exc
    return digest.hexdigest(), actual_bytes


def _sha256_file(path: Path) -> str:
    digest, _ = _hash_file_bounded(path, _MAX_IMPLEMENTATION_FILE_BYTES)
    return digest


def _implementation_hashes(
    solver_class: type[Any],
    geometry_engine_class: type[Any],
    *,
    solver_mode: str,
) -> tuple[tuple[str, str], ...]:
    """Bind the loaded source-tree artifact, not only mutable version labels."""

    rocell_root = Path(__file__).resolve().parents[1]
    source_files: list[Path] = []
    for source in rocell_root.rglob("*.py"):
        source_files.append(source)
        if len(source_files) > _MAX_IMPLEMENTATION_SOURCE_FILES:
            raise TrajectorySimulationError(
                "rocell source tree exceeds the implementation file-count cap"
            )
    source_files.sort()
    if not source_files:
        raise TrajectorySimulationError("cannot bind an empty rocell source tree")
    tree_hasher = hashlib.sha256()
    total_source_bytes = 0
    source_digests: dict[Path, str] = {}
    for source in source_files:
        relative = source.relative_to(rocell_root).as_posix().encode("utf-8")
        tree_hasher.update(len(relative).to_bytes(4, "big"))
        tree_hasher.update(relative)
        remaining_tree_bytes = _MAX_IMPLEMENTATION_SOURCE_BYTES - total_source_bytes
        source_digest, actual_bytes = _hash_file_bounded(
            source,
            min(_MAX_IMPLEMENTATION_FILE_BYTES, remaining_tree_bytes),
        )
        total_source_bytes += actual_bytes
        source_digests[source.resolve()] = source_digest
        tree_hasher.update(actual_bytes.to_bytes(8, "big"))
        tree_hasher.update(bytes.fromhex(source_digest))
    solver_source = inspect.getsourcefile(solver_class)
    geometry_source = inspect.getsourcefile(geometry_engine_class)
    if solver_source is None or geometry_source is None:
        raise TrajectorySimulationError(
            "active simulation implementation has no bindable source file"
        )
    def bound_source(path: Path) -> str:
        resolved = path.resolve()
        return source_digests.get(resolved) or _sha256_file(resolved)

    hashes = {
        "trajectory_module_sha256": bound_source(Path(__file__)),
        "ik_module_sha256": bound_source(rocell_root / "kinematics" / "ik.py"),
        "geometric_engine_module_sha256": bound_source(
            rocell_root / "motion" / "geometric_sim.py"
        ),
        "active_ik_solver_source_sha256": bound_source(Path(solver_source)),
        "active_geometric_engine_source_sha256": bound_source(
            Path(geometry_source)
        ),
        "rocell_source_tree_sha256": tree_hasher.hexdigest(),
    }
    identity = {
        **hashes,
        "ik_solver_identity": f"{solver_class.__module__}.{solver_class.__qualname__}",
        "geometric_engine_identity": (
            f"{geometry_engine_class.__module__}.{geometry_engine_class.__qualname__}"
        ),
        "solver_mode": solver_mode,
    }
    identity["implementation_bundle_sha256"] = _stable_hash(identity)
    return tuple(sorted(identity.items()))


@dataclass(frozen=True, slots=True)
class TrajectorySimulationPolicy:
    """Numerical and resource bounds for one route study."""

    maximum_cartesian_step_mm: float = 30.0
    maximum_joint_step_rad: float = 0.35
    minimum_normalized_arm_joint_margin: float = 0.01
    maximum_refinement_rounds: int = 2
    maximum_waypoints_per_round: int = 256
    maximum_total_ik_solves: int = 512
    maximum_route_targets: int = 8
    park_xy_board_mm: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("maximum_cartesian_step_mm", 1.0, 100.0),
            ("maximum_joint_step_rad", 0.01, 1.0),
            ("minimum_normalized_arm_joint_margin", 1e-6, 0.49),
        ):
            value = finite_real(getattr(self, name), name=name)
            if not lower <= value <= upper:
                raise TrajectorySimulationError(
                    f"{name} must be in [{lower}, {upper}]"
                )
            object.__setattr__(self, name, value)
        for name, lower, upper in (
            ("maximum_refinement_rounds", 0, _MAX_POLICY_REFINEMENTS),
            ("maximum_waypoints_per_round", 8, _MAX_POLICY_WAYPOINTS),
            ("maximum_total_ik_solves", 8, _MAX_POLICY_IK_SOLVES),
            ("maximum_route_targets", 1, _MAX_POLICY_ROUTE_TARGETS),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise TrajectorySimulationError(
                    f"{name} must be an integer in [{lower}, {upper}]"
                )
        if self.park_xy_board_mm is not None:
            raw = self.park_xy_board_mm
            if not isinstance(raw, (tuple, list)) or len(raw) != 2:
                raise TrajectorySimulationError(
                    "park_xy_board_mm must contain x and y"
                )
            park = tuple(
                finite_real(value, name="park coordinate") for value in raw
            )
            object.__setattr__(self, "park_xy_board_mm", park)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": "BOUNDED_SEQUENTIAL_IK_REFINEMENT_V2",
            "maximum_cartesian_step_mm": self.maximum_cartesian_step_mm,
            "maximum_joint_step_rad": self.maximum_joint_step_rad,
            "minimum_normalized_arm_joint_margin": self.minimum_normalized_arm_joint_margin,
            "maximum_refinement_rounds": self.maximum_refinement_rounds,
            "maximum_waypoints_per_round": self.maximum_waypoints_per_round,
            "maximum_total_ik_solves": self.maximum_total_ik_solves,
            "maximum_route_targets": self.maximum_route_targets,
            "derived_maximum_plan_actions": 2 * self.maximum_route_targets + 1,
            "park_xy_board_mm": (
                None
                if self.park_xy_board_mm is None
                else list(self.park_xy_board_mm)
            ),
            "hard_implementation_caps": {
                "waypoints_per_round": _MAX_POLICY_WAYPOINTS,
                "total_ik_solves": _MAX_POLICY_IK_SOLVES,
                "route_targets": _MAX_POLICY_ROUTE_TARGETS,
                "plan_actions": _MAX_POLICY_PLAN_ACTIONS,
                "refinement_rounds": _MAX_POLICY_REFINEMENTS,
                "ik_attempts_per_solve": _MAX_CANONICAL_IK_ATTEMPTS,
                "ik_iterations_per_attempt": _MAX_CANONICAL_IK_ITERATIONS,
                "task_jacobian_fk_evaluations_per_evaluated_waypoint": (
                    MAX_TASK_JACOBIAN_FK_EVALUATIONS
                ),
                "kinematic_model_bytes": MAX_PINNED_URDF_BYTES,
                "implementation_source_files": _MAX_IMPLEMENTATION_SOURCE_FILES,
                "implementation_source_bytes": _MAX_IMPLEMENTATION_SOURCE_BYTES,
                "individual_implementation_file_bytes": _MAX_IMPLEMENTATION_FILE_BYTES,
            },
        }

    @property
    def policy_hash(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class CartesianRouteWaypoint:
    sequence: int
    phase: MotionPhase
    action_index: int | None
    semantic_target: str | None
    point_board: Point3Mm
    distance_from_previous_mm: float
    source_geometric_sequence: int
    source_check_id: str | None
    source_path_check_passed: bool
    inherited_collision_ids: tuple[str, ...]
    phase_endpoint: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "phase": self.phase.value,
            "action_index": self.action_index,
            "semantic_target": self.semantic_target,
            "point_board_mm": [
                self.point_board.x,
                self.point_board.y,
                self.point_board.z,
            ],
            "distance_from_previous_mm": self.distance_from_previous_mm,
            "source_geometric_sequence": self.source_geometric_sequence,
            "source_check_id": self.source_check_id,
            "source_path_check_passed": self.source_path_check_passed,
            "inherited_collision_ids": list(self.inherited_collision_ids),
            "phase_endpoint": self.phase_endpoint,
        }


@dataclass(frozen=True, slots=True)
class JointTrajectoryWaypointResult:
    waypoint_sequence: int
    phase: MotionPhase
    action_index: int | None
    semantic_target: str | None
    ik_status: str
    accepted: bool
    controller_intersection_passed: bool
    arm_margin_passed: bool
    solver_weighted_task_jacobian_numerical_rank_passed: bool | None
    adjacent_joint_delta_passed: bool
    position_error_mm: float
    alignment_error_rad: float
    achieved_tip_position_board_mm: tuple[float, float, float]
    achieved_hand_tcp_z_axis_board: tuple[float, float, float]
    minimum_arm_joint_margin_rad: float | None
    minimum_normalized_arm_joint_margin: float | None
    maximum_joint_delta_rad: float | None
    joint_deltas_rad: tuple[tuple[str, float], ...]
    solution_arm_joint_positions_rad: tuple[tuple[str, float], ...]
    solver_weighted_task_jacobian: WeightedTaskJacobianConditioning | None
    selected_attempt_index: int
    attempt_count: int
    previous_solution_seed_supplied: bool
    failure_reason: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "achieved_tip_position_board_mm",
            _finite_vector3_tuple(
                self.achieved_tip_position_board_mm,
                "achieved_tip_position_board_mm",
            ),
        )
        axis = _finite_vector3_tuple(
            self.achieved_hand_tcp_z_axis_board,
            "achieved_hand_tcp_z_axis_board",
        )
        norm = math.sqrt(sum(component * component for component in axis))
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise TrajectorySimulationError(
                "achieved_hand_tcp_z_axis_board must be a unit vector"
            )
        # Preserve the solver's achieved direction exactly after validation;
        # evidence must not silently substitute or normalize planned geometry.
        object.__setattr__(self, "achieved_hand_tcp_z_axis_board", axis)

    def to_dict(self) -> dict[str, Any]:
        return {
            "waypoint_sequence": self.waypoint_sequence,
            "phase": self.phase.value,
            "action_index": self.action_index,
            "semantic_target": self.semantic_target,
            "ik_status": self.ik_status,
            "accepted": self.accepted,
            "controller_intersection_passed": self.controller_intersection_passed,
            "arm_margin_passed": self.arm_margin_passed,
            "solver_weighted_task_jacobian_numerical_rank_passed": (
                self.solver_weighted_task_jacobian_numerical_rank_passed
            ),
            "adjacent_joint_delta_passed": self.adjacent_joint_delta_passed,
            "position_error_mm": self.position_error_mm,
            "alignment_error_rad": self.alignment_error_rad,
            "achieved_tip_position_board_mm": list(
                self.achieved_tip_position_board_mm
            ),
            "achieved_hand_tcp_z_axis_board": list(
                self.achieved_hand_tcp_z_axis_board
            ),
            "minimum_arm_joint_margin_rad": self.minimum_arm_joint_margin_rad,
            "minimum_normalized_arm_joint_margin": self.minimum_normalized_arm_joint_margin,
            "maximum_joint_delta_rad": self.maximum_joint_delta_rad,
            "joint_deltas_rad": dict(self.joint_deltas_rad),
            "solution_arm_joint_positions_rad": dict(
                self.solution_arm_joint_positions_rad
            ),
            "solver_weighted_task_jacobian": (
                None
                if self.solver_weighted_task_jacobian is None
                else self.solver_weighted_task_jacobian.to_dict()
            ),
            "selected_attempt_index": self.selected_attempt_index,
            "attempt_count": self.attempt_count,
            "previous_solution_seed_supplied": self.previous_solution_seed_supplied,
            "failure_reason": self.failure_reason,
            "hardware_commands_generated": 0,
        }


@dataclass(frozen=True, slots=True)
class TrajectorySearchRound:
    round_index: int
    maximum_cartesian_step_mm: float
    waypoints: tuple[CartesianRouteWaypoint, ...]
    joint_results: tuple[JointTrajectoryWaypointResult, ...]
    status: str
    failure_reason: str | None

    @property
    def all_waypoints_accepted(self) -> bool:
        return (
            len(self.joint_results) == len(self.waypoints)
            and bool(self.waypoints)
            and all(result.accepted for result in self.joint_results)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "maximum_cartesian_step_mm": self.maximum_cartesian_step_mm,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "waypoint_count": len(self.waypoints),
            "evaluated_waypoint_count": len(self.joint_results),
            "all_waypoints_accepted": self.all_waypoints_accepted,
            "waypoints": [waypoint.to_dict() for waypoint in self.waypoints],
            "joint_results": [result.to_dict() for result in self.joint_results],
        }


@dataclass(frozen=True, slots=True)
class TrajectorySimulationReport:
    source_provenance: tuple[tuple[str, Any], ...]
    policy: TrajectorySimulationPolicy
    study_input: ReachStudyInput
    device: str
    route_target_ids: tuple[str, ...]
    tool_length_mm: float
    park_xy_board_mm: tuple[float, float]
    transit_plane_z_mm: float
    geometry_report_hash: str
    geometry_all_checks_passed: bool
    geometry_check_count: int
    rounds: tuple[TrajectorySearchRound, ...]
    total_ik_solves: int
    termination_reason: str

    @property
    def final_round(self) -> TrajectorySearchRound | None:
        return self.rounds[-1] if self.rounds else None

    @property
    def status(self) -> str:
        if not self.geometry_all_checks_passed:
            return "BLOCKED_NOMINAL_TOOL_TIP_PATH_CHECKS"
        final = self.final_round
        if final is not None and final.all_waypoints_accepted:
            return (
                "DISCRETE_SEQUENTIAL_IK_WAYPOINT_DIAGNOSTIC_PASS_"
                "WITH_UNSUPPORTED_CHECKS"
            )
        return "DISCRETE_SEQUENTIAL_IK_WAYPOINT_DIAGNOSTIC_GAPS_REPORTED"

    @property
    def task_jacobian_evaluated_waypoint_count(self) -> int:
        """Count selected states that received the bounded local diagnostic."""

        return sum(
            result.solver_weighted_task_jacobian is not None
            for round_ in self.rounds
            for result in round_.joint_results
        )

    @property
    def total_task_jacobian_fk_evaluations(self) -> int:
        """Return the exact bounded FK cost of every serialized diagnostic."""

        return sum(
            result.solver_weighted_task_jacobian.finite_difference_fk_evaluations
            for round_ in self.rounds
            for result in round_.joint_results
            if result.solver_weighted_task_jacobian is not None
        )

    def to_dict(self) -> dict[str, Any]:
        phase_counts = {
            phase.value: sum(
                waypoint.phase is phase
                for waypoint in (self.final_round.waypoints if self.final_round else ())
            )
            for phase in sorted(_REQUIRED_MOTION_PHASES, key=lambda item: item.value)
        }
        provenance = dict(self.source_provenance)
        provenance["ik_options"] = dict(provenance["ik_options"])
        return {
            "schema": "rocell.discrete_sequential_ik_waypoint_simulation.v2",
            "status": self.status,
            "scope": "SEQUENTIAL_IK_OVER_NOMINAL_TOOL_TIP_CENTRELINE_ONLY",
            "simulation_only": True,
            "execution_authorized": False,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "physical_release_effect": "NONE",
            "source_provenance": provenance,
            "policy": {**self.policy.to_dict(), "policy_hash": self.policy.policy_hash},
            "study_input": self.study_input.to_dict(),
            "device": self.device,
            "route_target_ids": list(self.route_target_ids),
            "route_target_count": len(self.route_target_ids),
            "route_tool_length_mm": self.tool_length_mm,
            "effective_park_xy_board_mm": (
                list(self.park_xy_board_mm)
            ),
            "transit_plane_z_mm": self.transit_plane_z_mm,
            "geometry": {
                "report_hash": self.geometry_report_hash,
                "all_checks_passed": self.geometry_all_checks_passed,
                "check_count": self.geometry_check_count,
                "model": "nominal tool-tip centreline against RC03 AABB proxies",
            },
            "phase_waypoint_counts_final_round": phase_counts,
            "required_motion_phases_present": all(
                phase_counts[phase.value] > 0 for phase in _REQUIRED_MOTION_PHASES
            ),
            "search": {
                "round_count": len(self.rounds),
                "total_ik_solves": self.total_ik_solves,
                "task_jacobian_evaluated_waypoint_count": (
                    self.task_jacobian_evaluated_waypoint_count
                ),
                "total_task_jacobian_fk_evaluations": (
                    self.total_task_jacobian_fk_evaluations
                ),
                "termination_reason": self.termination_reason,
                "rounds": [round_.to_dict() for round_ in self.rounds],
            },
            "supported_diagnostics": [
                "nominal tool-tip centreline AABB segment checks",
                "bounded deterministic sequential IK",
                "previous selected joint state supplied as the first next-waypoint seed",
                "controller/URDF arm-joint intersection",
                "normalized arm-joint margin",
                "bounded local solver-weighted task-Jacobian numerical rank and conditioning",
                "adjacent sampled selected-joint delta bound",
                "bounded Cartesian waypoint spacing and refinement",
            ],
            "unsupported_diagnostics": [
                {
                    "id": "ROBOT_LINK_AND_SELF_COLLISION",
                    "status": "UNSUPPORTED_NOT_EVALUATED",
                    "release_effect": "BLOCKS_PHYSICAL_EXECUTION",
                },
                {
                    "id": "TOOL_CAMERA_HOLDER_AND_CABLE_VOLUMES",
                    "status": "UNSUPPORTED_NOT_EVALUATED",
                    "release_effect": "BLOCKS_PHYSICAL_EXECUTION",
                },
                {
                    "id": "FULL_6D_PHYSICAL_SINGULARITY_AND_MANIPULABILITY_ACCEPTANCE",
                    "status": "UNSUPPORTED_NOT_EVALUATED",
                    "release_effect": "BLOCKS_PHYSICAL_EXECUTION",
                },
                {
                    "id": "TIMING_VELOCITY_ACCELERATION_DYNAMICS_PAYLOAD_AND_FORCE",
                    "status": "UNSUPPORTED_NOT_EVALUATED",
                    "release_effect": "BLOCKS_PHYSICAL_EXECUTION",
                },
                {
                    "id": "CONTROLLER_CORRELATION_AND_T104_EXECUTION",
                    "status": "UNSUPPORTED_NOT_EVALUATED",
                    "release_effect": "BLOCKS_PHYSICAL_EXECUTION",
                },
                {
                    "id": "VISION_CORRECTION_AND_OUTCOME_OBSERVERS",
                    "status": "UNSUPPORTED_NOT_EVALUATED",
                    "release_effect": "BLOCKS_PHYSICAL_EXECUTION",
                },
            ],
            "limitations": [
                "Cartesian interpolation is linear in board-frame tool-tip position; tool yaw about aligned +Z remains unconstrained.",
                "Joint continuity is checked only between selected IK branches and does not prove continuous collision-free configuration-space motion.",
                "The first park solution is a simulated initial condition; no path from an installed arm's measured joint state to park is evaluated.",
                "No timestamps are assigned, so joint deltas are not velocity or acceleration limits.",
                "The fixed gripper is excluded from the five-arm-joint margin gate and remains a separate installed tool/grip qualification item.",
                "The task-Jacobian gate rejects only deterministic numerical rank loss in the solver's weighted five-constraint residual; normalized conditioning and condition number are report-only.",
                "The solver-weighted local task metric is not a full geometric Jacobian, physical manipulability certificate, force capability, or dynamics model.",
                "Nominal targets, device planes, base placement, TCP length, and AABB proxies remain unmeasured simulation inputs.",
                "A PASS is diagnostic evidence only and cannot authorize physical motion or contact.",
            ],
        }

    @property
    def report_hash(self) -> str:
        return _stable_hash(self.to_dict())


def _route_target_ids(plan: ActionPlan) -> tuple[str, ...]:
    identifiers: list[str] = []
    for action in plan.actions:
        if isinstance(action, PressKey):
            identifiers.append(action.key_id)
        elif isinstance(action, TapPhoneTarget):
            identifiers.append(action.target_id)
    return tuple(identifiers)


def _ik_options_dict(options: IkOptions) -> dict[str, int | float]:
    """Serialize every numerical solver control that selects an IK branch."""

    return {
        name: getattr(options, name)
        for name in (
            "max_attempts",
            "max_iterations_per_attempt",
            "position_tolerance_mm",
            "alignment_tolerance_rad",
            "orientation_weight_mm_per_rad",
            "finite_difference_step_rad",
            "initial_damping",
            "minimum_damping",
            "maximum_damping",
            "max_joint_step_rad",
            "line_search_steps",
        )
    }


def _canonical_source_provenance(
    context: SimulationContext,
    plan: ActionPlan,
    study_input: ReachStudyInput,
    policy: TrajectorySimulationPolicy,
    *,
    loaded_model_sha256: str,
    loaded_model_bytes: int,
    options: IkOptions,
) -> tuple[tuple[str, Any], ...]:
    """Build the exact production provenance closure for a trajectory report."""

    implementation_hashes = _implementation_hashes(
        _CANONICAL_IK_SOLVER,
        _CANONICAL_GEOMETRIC_ENGINE,
        solver_mode="CANONICAL_IN_PACKAGE_IMPLEMENTATION",
    )
    scenario = context.scenario
    return (
        ("snapshot_hash", context.snapshot.snapshot_hash),
        ("simulation_bundle_id", context.bundle_lock.bundle_id),
        ("simulation_bundle_sha256", context.bundle_lock.source_lock_sha256),
        ("hardware_profile_hash", context.hardware_profile.profile_hash),
        ("target_profile_sha256", context.targets.content_sha256),
        ("model_sha256", scenario.model_sha256),
        ("loaded_model_sha256", loaded_model_sha256),
        ("loaded_model_bytes", loaded_model_bytes),
        ("alignment_report_hash", context.alignment.report_hash),
        ("plan_hash", plan.plan_hash),
        ("plan_profile_id", plan.profile_id),
        ("study_input_id", study_input.study_input_id),
        (
            "ik_solver_implementation",
            f"{_CANONICAL_IK_SOLVER.__module__}.{_CANONICAL_IK_SOLVER.__qualname__}",
        ),
        ("ik_solver_algorithm_version", "DETERMINISTIC_BOUNDED_DLS_V1"),
        (
            "task_jacobian_conditioning_implementation",
            "rocell.kinematics.ik.RoArmM3NumericalIk."
            "diagnose_weighted_task_jacobian",
        ),
        (
            "task_jacobian_conditioning_algorithm_version",
            "SOLVER_WEIGHTED_RESIDUAL_FINITE_DIFFERENCE_GRAM_JACOBI_V2",
        ),
        (
            "task_jacobian_conditioning_solver_mode",
            "CANONICAL_IN_PACKAGE_IMPLEMENTATION",
        ),
        ("task_jacobian_conditioning_additional_ik_solves", 0),
        ("task_jacobian_numerical_rank_gate", "FULL_COLUMN_NUMERICAL_RANK_ONLY"),
        ("normalized_task_jacobian_conditioning_gate_enabled", False),
        *implementation_hashes,
        ("ik_options", tuple(sorted(_ik_options_dict(options).items()))),
        (
            "worst_case_solver_iteration_budget",
            policy.maximum_total_ik_solves
            * options.max_attempts
            * options.max_iterations_per_attempt,
        ),
        (
            "worst_case_task_jacobian_fk_evaluation_budget",
            policy.maximum_total_ik_solves
            * MAX_TASK_JACOBIAN_FK_EVALUATIONS,
        ),
        ("rocell_runtime_version", __version__),
        ("previous_solution_seed_policy", "FIRST_SEED_AT_EVERY_SUBSEQUENT_WAYPOINT"),
        (
            "controller_joint_intersection_rad",
            tuple(
                (name, tuple(bounds))
                for name, bounds in scenario.controller_joint_intersection_rad.items()
            ),
        ),
        ("fixed_gripper_position_rad", scenario.fixed_gripper_position.value),
        ("fixed_gripper_in_arm_margin_gate", False),
    )


def _validate_study_input(
    context: SimulationContext,
    study: ReachStudyInput,
    vendor_world_T_base_link: RigidTransform,
) -> None:
    if not isinstance(study, ReachStudyInput):
        raise TypeError("study_input must be a ReachStudyInput")
    board_rear_y = context.scene.board.maximum.y
    clamp_lower, clamp_upper = context.scene.arm_clamp_rear_edge_x_range_mm
    if not clamp_lower <= study.rear_clamp_contact_x_board_mm <= clamp_upper:
        raise TrajectorySimulationError("study clamp contact X leaves the RC03 zone")
    if not -100.0 <= study.clamp_to_base_axis_x_mm <= 100.0:
        raise TrajectorySimulationError("study clamp-to-base-axis X is outside its bounded envelope")
    if not 0.0 <= study.rear_edge_to_base_axis_y_mm <= 100.0:
        raise TrajectorySimulationError("study rear-edge-to-axis Y is outside its bounded envelope")
    expected_x = (
        study.rear_clamp_contact_x_board_mm + study.clamp_to_base_axis_x_mm
    )
    translation = study.board_T_base_link.translation_mm
    if not (
        math.isclose(study.base_axis_x_board_mm, expected_x, abs_tol=1e-9)
        and math.isclose(translation.x, expected_x, abs_tol=1e-9)
        and math.isclose(
            translation.y,
            board_rear_y + study.rear_edge_to_base_axis_y_mm,
            abs_tol=1e-9,
        )
        and math.isclose(translation.z, study.base_link_z_board_mm, abs_tol=1e-9)
    ):
        raise TrajectorySimulationError("study scalar placement fields disagree with B_T_Ru")
    expected_rotation = RigidTransform.from_rpy_translation_mm(
        "board",
        "base_link",
        translation_mm=translation,
        yaw_rad=study.base_yaw_board_rad,
    ).rotation
    if not study.board_T_base_link.rotation.almost_equal(expected_rotation):
        raise TrajectorySimulationError("study B_T_Ru is not the declared planar yaw")
    canonical_board_T_base_link = context.scenario.board_T_world.compose(
        vendor_world_T_base_link
    )
    canonical_yaw = math.atan2(
        canonical_board_T_base_link.rotation.matrix[3],
        canonical_board_T_base_link.rotation.matrix[0],
    )
    yaw_delta = math.atan2(
        math.sin(study.base_yaw_board_rad - canonical_yaw),
        math.cos(study.base_yaw_board_rad - canonical_yaw),
    )
    if abs(yaw_delta) > math.radians(15.0) + 1e-12:
        raise TrajectorySimulationError(
            "study base yaw leaves the reach-study +/-15 degree envelope"
        )
    if not math.isclose(
        study.base_link_z_board_mm,
        canonical_board_T_base_link.translation_mm.z,
        abs_tol=1e-9,
    ):
        raise TrajectorySimulationError(
            "study base-link Z must retain the pinned reach-study assumption"
        )
    derived = study.board_T_base_link.compose(vendor_world_T_base_link.inverse())
    if not derived.almost_equal(study.board_T_vendor_world):
        raise TrajectorySimulationError(
            "study B_T_Wv does not equal B_T_Ru * inverse(Wv_T_Ru)"
        )
    for name, length in (
        ("keyboard", study.keyboard_tool_length_mm),
        ("phone", study.phone_tool_length_mm),
    ):
        if not 0.0 <= length <= 150.0:
            raise TrajectorySimulationError(f"{name} tool length leaves [0, 150] mm")


def _motion_steps(
    steps: tuple[GeometricPathStep, ...],
    expected_semantic_targets: tuple[str, ...],
) -> tuple[GeometricPathStep, ...]:
    """Select motion endpoints and fail closed on per-target phase ordering."""

    selected = tuple(
        step
        for step in steps
        if step.phase in _REQUIRED_MOTION_PHASES and step.tip_point_board is not None
    )
    if not selected or selected[0].phase is not MotionPhase.PARK:
        raise TrajectorySimulationError("geometric route must begin at park")
    if selected[-1].phase is not MotionPhase.PARK:
        raise TrajectorySimulationError("geometric route must return to park")
    if not _REQUIRED_MOTION_PHASES.issubset({step.phase for step in selected}):
        raise TrajectorySimulationError("geometric route is missing a required motion phase")

    # The geometric engine inserts vision/verification records between these
    # endpoints.  Those non-motion records are intentionally omitted, while
    # every physical target occurrence must retain this ordered phase chain.
    cursor = 1
    target_phases = (
        MotionPhase.HOVER,
        MotionPhase.APPROACH,
        MotionPhase.CONTACT,
        MotionPhase.RETRACT,
    )
    for expected_target in expected_semantic_targets:
        transit_count = 0
        while (
            cursor < len(selected)
            and selected[cursor].phase is MotionPhase.TRANSIT
            and selected[cursor].semantic_target == expected_target
        ):
            transit_count += 1
            cursor += 1
        if transit_count == 0:
            raise TrajectorySimulationError(
                f"geometric route target {expected_target!r} lacks ordered transit"
            )
        for expected_phase in target_phases:
            if (
                cursor >= len(selected)
                or selected[cursor].phase is not expected_phase
                or selected[cursor].semantic_target != expected_target
            ):
                raise TrajectorySimulationError(
                    "geometric route target "
                    f"{expected_target!r} lacks ordered {expected_phase.value}"
                )
            cursor += 1

    final_transit_count = 0
    while (
        cursor < len(selected)
        and selected[cursor].phase is MotionPhase.TRANSIT
        and selected[cursor].semantic_target is None
    ):
        final_transit_count += 1
        cursor += 1
    if final_transit_count == 0:
        raise TrajectorySimulationError("geometric route lacks ordered return transit")
    if (
        cursor != len(selected) - 1
        or selected[cursor].phase is not MotionPhase.PARK
        or selected[cursor].semantic_target is not None
    ):
        raise TrajectorySimulationError(
            "geometric route does not end with one ordered return park"
        )
    return selected


def _validate_park_xy(context: SimulationContext, park_xy: tuple[float, float]) -> None:
    validate_scene_park_xy(context.scene, park_xy)


def validate_scene_park_xy(scene, park_xy: tuple[float, float]) -> None:
    """Retain the conservative on-board/outside-keepout RC03 park contract."""

    x, y = park_xy
    board = scene.board
    if not (
        board.minimum.x <= x <= board.maximum.x
        and board.minimum.y <= y <= board.maximum.y
    ):
        raise TrajectorySimulationError("park XY must remain on the RC03 board")
    for obstacle in scene.obstacles:
        if obstacle.obstacle_id == "board_solid":
            continue
        if (
            obstacle.minimum.x <= x <= obstacle.maximum.x
            and obstacle.minimum.y <= y <= obstacle.maximum.y
        ):
            raise TrajectorySimulationError(
                f"park XY aliases keepout {obstacle.obstacle_id}"
            )
    for tag in scene.fiducials:
        half = tag.tile_edge_mm / 2.0
        if (
            tag.center.x - half <= x <= tag.center.x + half
            and tag.center.y - half <= y <= tag.center.y + half
        ):
            raise TrajectorySimulationError(f"park XY aliases tag tile {tag.name}")


def _index_path_checks(
    checks: tuple[GeometricPathCheck, ...],
) -> dict[str, GeometricPathCheck]:
    identifiers = tuple(check.check_id for check in checks)
    if any(not identifier for identifier in identifiers):
        raise TrajectorySimulationError("geometric path check ID cannot be empty")
    if len(set(identifiers)) != len(identifiers):
        raise TrajectorySimulationError("geometric path check IDs must be unique")
    return {check.check_id: check for check in checks}


def _densify(
    steps: tuple[GeometricPathStep, ...],
    checks_by_id: Mapping[str, GeometricPathCheck],
    expected_semantic_targets: tuple[str, ...],
    maximum_step_mm: float,
    maximum_waypoints: int,
) -> tuple[CartesianRouteWaypoint, ...]:
    motion = _motion_steps(steps, expected_semantic_targets)
    first = motion[0]
    assert first.tip_point_board is not None
    waypoints: list[CartesianRouteWaypoint] = [
        CartesianRouteWaypoint(
            sequence=0,
            phase=first.phase,
            action_index=first.action_index,
            semantic_target=first.semantic_target,
            point_board=first.tip_point_board,
            distance_from_previous_mm=0.0,
            source_geometric_sequence=first.sequence,
            source_check_id=first.check_id,
            source_path_check_passed=True,
            inherited_collision_ids=(),
            phase_endpoint=True,
        )
    ]
    previous = first.tip_point_board
    for step in motion[1:]:
        assert step.tip_point_board is not None
        destination = step.tip_point_board
        delta = (
            destination.x - previous.x,
            destination.y - previous.y,
            destination.z - previous.z,
        )
        distance = math.sqrt(sum(value * value for value in delta))
        subdivisions = max(1, math.ceil(distance / maximum_step_mm))
        source_check = checks_by_id.get(step.check_id) if step.check_id else None
        if step.check_id is None and distance > 1e-9:
            raise TrajectorySimulationError(
                "non-zero geometric motion segment lacks a path check ID"
            )
        if step.check_id is not None and source_check is None:
            raise TrajectorySimulationError(
                f"geometric step references missing path check {step.check_id!r}"
            )
        check_passed = (
            True
            if source_check is None
            else getattr(source_check, "status", None) == "PASS"
        )
        collisions = (
            ()
            if source_check is None
            else tuple(getattr(source_check, "collisions", ()))
        )
        for subdivision in range(1, subdivisions + 1):
            ratio = subdivision / subdivisions
            point = Point3Mm(
                "board",
                previous.x + ratio * delta[0],
                previous.y + ratio * delta[1],
                previous.z + ratio * delta[2],
            )
            prior = waypoints[-1].point_board
            local_distance = math.sqrt(
                (point.x - prior.x) ** 2
                + (point.y - prior.y) ** 2
                + (point.z - prior.z) ** 2
            )
            if local_distance > maximum_step_mm + 1e-9:
                raise TrajectorySimulationError("Cartesian densification exceeded its step bound")
            waypoints.append(
                CartesianRouteWaypoint(
                    sequence=len(waypoints),
                    phase=step.phase,
                    action_index=step.action_index,
                    semantic_target=step.semantic_target,
                    point_board=point,
                    distance_from_previous_mm=local_distance,
                    source_geometric_sequence=step.sequence,
                    source_check_id=step.check_id,
                    source_path_check_passed=check_passed,
                    inherited_collision_ids=collisions,
                    phase_endpoint=subdivision == subdivisions,
                )
            )
            if len(waypoints) > maximum_waypoints:
                raise TrajectorySimulationError(
                    f"densified route exceeds {maximum_waypoints} waypoints"
                )
        previous = destination
    return tuple(waypoints)


def _evaluate_joint_trajectory_solution(
    waypoint: CartesianRouteWaypoint,
    solved: Any,
    conditioning_solver: RoArmM3NumericalIk,
    bounds: Mapping[str, tuple[float, float]],
    previous_solution: Mapping[str, float] | None,
    policy: TrajectorySimulationPolicy,
) -> JointTrajectoryWaypointResult:
    """Apply canonical post-IK gates after the caller validates its boundary.

    Kept separate so explicitly identified test solvers can exercise the
    nominal trajectory engine without pretending to be production IkResult
    instances.  External correction callers use the validated public wrapper
    below; both paths share this exact acceptance implementation.
    """

    try:
        achieved_tip = solved.residual.tip_position_board_mm
        achieved_axis = solved.residual.hand_tcp_z_axis_board
    except AttributeError as exc:
        raise TrajectorySimulationError(
            "IK residual must expose the achieved tip position and hand-TCP +Z axis"
        ) from exc
    if not isinstance(achieved_tip, Point3Mm):
        raise TrajectorySimulationError(
            "IK achieved tip position must be a frame-labelled Point3Mm"
        )
    if achieved_tip.frame != waypoint.point_board.frame:
        raise TrajectorySimulationError(
            "IK achieved tip position frame does not match the board waypoint frame"
        )
    if not isinstance(achieved_axis, Vec3):
        raise TrajectorySimulationError(
            "IK achieved hand-TCP +Z axis must be a finite Vec3"
        )
    achieved_tip_tuple = (achieved_tip.x, achieved_tip.y, achieved_tip.z)
    achieved_axis_tuple = (achieved_axis.x, achieved_axis.y, achieved_axis.z)
    solution = {
        item.name: item.position.value
        for item in solved.solution_arm_joint_positions
    }
    controller_ok = solved.converged and set(solution) == set(bounds) and all(
        lower <= solution[name] <= upper
        for name, (lower, upper) in bounds.items()
    )
    raw_margin = None
    normalized_margin = None
    if controller_ok:
        raw_margin = min(
            min(value - bounds[name][0], bounds[name][1] - value)
            for name, value in solution.items()
        )
        normalized_margin = min(
            min(value - bounds[name][0], bounds[name][1] - value)
            / (bounds[name][1] - bounds[name][0])
            for name, value in solution.items()
        )
    margin_ok = (
        controller_ok
        and normalized_margin is not None
        and normalized_margin >= policy.minimum_normalized_arm_joint_margin
    )
    conditioning: WeightedTaskJacobianConditioning | None = None
    conditioning_rank_ok: bool | None = None
    if margin_ok:
        typed_solution = {
            name: JointPosition.radians(solution[name]) for name in bounds
        }
        try:
            conditioning = conditioning_solver.diagnose_weighted_task_jacobian(
                BoardToolTipTarget(waypoint.point_board),
                typed_solution,
            )
        except IkContractError as exc:
            raise TrajectorySimulationError(
                "solver-weighted task-Jacobian diagnostic failed closed"
            ) from exc
        conditioning_rank_ok = conditioning.full_column_rank
    deltas: tuple[tuple[str, float], ...] = ()
    maximum_delta = None
    continuity_ok = previous_solution is None
    if controller_ok and previous_solution is not None:
        deltas = tuple(
            (name, abs(solution[name] - previous_solution[name]))
            for name in bounds
        )
        maximum_delta = max(value for _, value in deltas)
        continuity_ok = maximum_delta <= policy.maximum_joint_step_rad + 1e-12
    if not waypoint.source_path_check_passed:
        failure = "NOMINAL_TOOL_TIP_PATH_CHECK_FAILED"
    elif not solved.converged:
        failure = "IK_NO_CONVERGED_SOLUTION"
    elif not controller_ok:
        failure = "CONTROLLER_URDF_INTERSECTION_REJECTED"
    elif not margin_ok:
        failure = "MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED"
    elif conditioning_rank_ok is not True:
        failure = "SOLVER_WEIGHTED_TASK_JACOBIAN_NUMERICAL_RANK_DEFICIENT"
    elif not continuity_ok:
        failure = "MAXIMUM_ADJACENT_JOINT_DELTA_EXCEEDED"
    else:
        failure = None
    accepted = failure is None
    return JointTrajectoryWaypointResult(
        waypoint_sequence=waypoint.sequence,
        phase=waypoint.phase,
        action_index=waypoint.action_index,
        semantic_target=waypoint.semantic_target,
        ik_status=solved.status.value,
        accepted=accepted,
        controller_intersection_passed=bool(controller_ok),
        arm_margin_passed=bool(margin_ok),
        solver_weighted_task_jacobian_numerical_rank_passed=(
            conditioning_rank_ok
        ),
        adjacent_joint_delta_passed=bool(continuity_ok),
        position_error_mm=solved.residual.position_error_mm,
        alignment_error_rad=solved.residual.alignment_error_rad,
        achieved_tip_position_board_mm=achieved_tip_tuple,
        achieved_hand_tcp_z_axis_board=achieved_axis_tuple,
        minimum_arm_joint_margin_rad=raw_margin,
        minimum_normalized_arm_joint_margin=normalized_margin,
        maximum_joint_delta_rad=maximum_delta,
        joint_deltas_rad=deltas,
        solution_arm_joint_positions_rad=tuple(solution.items()),
        solver_weighted_task_jacobian=conditioning,
        selected_attempt_index=solved.selected_attempt_index,
        attempt_count=len(solved.attempts),
        previous_solution_seed_supplied=previous_solution is not None,
        failure_reason=failure,
    )


def _validated_arm_joint_values(
    value: object,
    *,
    label: str,
    bounds: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(ARM_JOINT_NAMES):
        raise TrajectorySimulationError(
            f"{label} must contain exactly the five canonical arm joints"
        )
    parsed: dict[str, float] = {}
    for name in ARM_JOINT_NAMES:
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TrajectorySimulationError(f"{label}.{name} must be numeric")
        number = float(item)
        if not math.isfinite(number):
            raise TrajectorySimulationError(f"{label}.{name} must be finite")
        if bounds is not None:
            lower, upper = bounds[name]
            if not lower <= number <= upper:
                raise TrajectorySimulationError(
                    f"{label}.{name} leaves the controller/URDF intersection"
                )
        parsed[name] = number
    return parsed


def _validated_arm_joint_bounds(
    value: object,
) -> dict[str, tuple[float, float]]:
    if not isinstance(value, Mapping) or set(value) != set(ARM_JOINT_NAMES):
        raise TrajectorySimulationError(
            "bounds must contain exactly the five canonical arm joints"
        )
    parsed: dict[str, tuple[float, float]] = {}
    for name in ARM_JOINT_NAMES:
        pair = value[name]
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise TrajectorySimulationError(f"bounds.{name} must be a pair")
        numbers: list[float] = []
        for index, item in enumerate(pair):
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise TrajectorySimulationError(
                    f"bounds.{name}[{index}] must be numeric"
                )
            number = float(item)
            if not math.isfinite(number):
                raise TrajectorySimulationError(
                    f"bounds.{name}[{index}] must be finite"
                )
            numbers.append(number)
        lower, upper = numbers
        if lower >= upper:
            raise TrajectorySimulationError(
                f"bounds.{name} must be strictly increasing"
            )
        parsed[name] = (lower, upper)
    return parsed


def evaluate_joint_trajectory_solution(
    waypoint: CartesianRouteWaypoint,
    solved: IkResult,
    conditioning_solver: RoArmM3NumericalIk,
    bounds: Mapping[str, tuple[float, float]],
    previous_solution: Mapping[str, float] | None,
    policy: TrajectorySimulationPolicy,
) -> JointTrajectoryWaypointResult:
    """Validate inputs, then apply the canonical post-IK acceptance gates.

    Correction replanning must use exactly the same controller intersection,
    joint-margin, local task-Jacobian rank, and adjacent-joint-delta gates as
    the initial nominal trajectory.  Keeping this evaluator public avoids a
    subtly different second implementation at that safety boundary.  It does
    not execute motion or grant authority.
    """
    if not isinstance(waypoint, CartesianRouteWaypoint):
        raise TypeError("waypoint must be CartesianRouteWaypoint")
    if not isinstance(solved, IkResult):
        raise TypeError("solved must be IkResult")
    if not isinstance(conditioning_solver, RoArmM3NumericalIk):
        raise TypeError("conditioning_solver must be RoArmM3NumericalIk")
    if not isinstance(policy, TrajectorySimulationPolicy):
        raise TypeError("policy must be TrajectorySimulationPolicy")
    if not isinstance(waypoint.point_board, Point3Mm) or (
        waypoint.point_board.frame != "board"
    ):
        raise TrajectorySimulationError(
            "waypoint must contain a board-frame Point3Mm"
        )
    if solved.target.position_mm != waypoint.point_board:
        raise TrajectorySimulationError(
            "IK result target differs from the evaluated waypoint"
        )
    parsed_bounds = _validated_arm_joint_bounds(bounds)
    parsed_previous = (
        None
        if previous_solution is None
        else _validated_arm_joint_values(
            previous_solution,
            label="previous_solution",
            bounds=parsed_bounds,
        )
    )
    solution_items = tuple(solved.solution_arm_joint_positions)
    if len(solution_items) != len(ARM_JOINT_NAMES) or tuple(
        item.name for item in solution_items
    ) != ARM_JOINT_NAMES:
        raise TrajectorySimulationError(
            "IK solution must use the exact canonical arm-joint order"
        )
    _validated_arm_joint_values(
        {item.name: item.position.value for item in solution_items},
        label="IK solution",
    )
    return _evaluate_joint_trajectory_solution(
        waypoint,
        solved,
        conditioning_solver,
        parsed_bounds,
        parsed_previous,
        policy,
    )


def screen_scenario_route(
    scenario,
    plan,
    geometry,
    *,
    initial_arm_joint_positions_rad=None,
):
    """One bounded dense pass for an already validated architecture context.

    Uses the canonical densifier, solver and joint/Jacobian checks. This lower
    level function grants no context validation or motion authority of its own.
    Stop at the first failed waypoint and retain the unevaluated remainder.
    """
    policy = TrajectorySimulationPolicy(maximum_cartesian_step_mm=15.,
        maximum_refinement_rounds=0, maximum_total_ik_solves=256)
    targets = _route_target_ids(plan)
    if not targets or len(targets) > policy.maximum_route_targets:
        raise TrajectorySimulationError('One to eight route targets required')
    if geometry.plan_hash != plan.plan_hash:
        raise TrajectorySimulationError('Geometry/plan identity mismatch')
    if not geometry.all_checks_pass:
        return dict(status='GEOMETRY_FAILED', all_waypoints_accepted=False,
                    policy=policy.to_dict(), round=None, hardware_commands_generated=0)
    waypoints = _densify(geometry.steps, _index_path_checks(geometry.checks),
        tuple(f'{plan.device.value}:{target}' for target in targets),
        policy.maximum_cartesian_step_mm, policy.maximum_waypoints_per_round)
    loaded = load_pinned_urdf(scenario.model_path, scenario.model_sha256)
    solver = RoArmM3NumericalIk(model=loaded.model,
        board_T_world=scenario.board_T_world,
        hand_tcp_to_tip_z_mm=scenario.hand_tcp_to_tip_z_mm,
        fixed_gripper_position=scenario.fixed_gripper_position,
        ready_arm_joint_positions=scenario.ready_arm_joint_positions_rad,
        gripper_bounds_rad=scenario.controller_gripper_intersection_rad,
        joint_bounds_rad=scenario.controller_joint_intersection_rad,
        options=IkOptions(max_attempts=scenario.ik_policy.max_attempts,
            max_iterations_per_attempt=scenario.ik_policy.max_iterations_per_attempt))
    previous = (
        None
        if initial_arm_joint_positions_rad is None
        else _validated_arm_joint_values(
            initial_arm_joint_positions_rad,
            label="initial_arm_joint_positions_rad",
            bounds=scenario.controller_joint_intersection_rad,
        )
    )
    results = []
    failure = None
    for waypoint in waypoints:
        seeds = () if previous is None else (
            {name: JointPosition.radians(value) for name, value in previous.items()},)
        solved = solver.solve(BoardToolTipTarget(waypoint.point_board), seed_joint_positions=seeds)
        result = _evaluate_joint_trajectory_solution(waypoint, solved, solver,
            scenario.controller_joint_intersection_rad, previous, policy)
        results.append(result)
        if not result.accepted:
            failure = result.failure_reason
            break
        previous = dict(result.solution_arm_joint_positions_rad)
    search = TrajectorySearchRound(0, policy.maximum_cartesian_step_mm, waypoints,
        tuple(results), 'PASS' if failure is None else 'FAIL', failure)
    return dict(status='DENSE_SAMPLES_PASS_NOT_EXECUTABLE' if search.all_waypoints_accepted
                else 'DENSE_ROUTE_FAILED', all_waypoints_accepted=search.all_waypoints_accepted,
                policy=policy.to_dict(), round=search.to_dict(),
                loaded_model_sha256=loaded.sha256, hardware_commands_generated=0,
                physical_authority=False, continuous_path_proven=False,
                full_arm_collision_checked=False)


def _run_trajectory_simulation_with_implementations(
    context: SimulationContext,
    plan: ActionPlan,
    study_input: ReachStudyInput,
    policy: TrajectorySimulationPolicy | None = None,
    *,
    solver_class: type[Any],
    geometry_engine_class: type[Any],
    solver_mode: str,
) -> TrajectorySimulationReport:
    """Core service with explicit, provenance-bound test dependency injection."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(plan, ActionPlan):
        raise TypeError("plan must be an ActionPlan")
    revalidate_simulation_context(context)
    if not context.alignment.all_checks_pass:
        raise TrajectorySimulationError("canonical placemat alignment must pass")
    selected_policy = policy or TrajectorySimulationPolicy()
    if not isinstance(selected_policy, TrajectorySimulationPolicy):
        raise TypeError("policy must be a TrajectorySimulationPolicy")
    maximum_plan_actions = 2 * selected_policy.maximum_route_targets + 1
    if len(plan.actions) > maximum_plan_actions:
        raise TrajectorySimulationError(
            f"plan has {len(plan.actions)} actions; derived policy maximum is "
            f"{maximum_plan_actions}"
        )
    route_targets = _route_target_ids(plan)
    if not route_targets:
        raise TrajectorySimulationError("route must contain at least one physical target")
    if len(route_targets) > selected_policy.maximum_route_targets:
        raise TrajectorySimulationError(
            f"route has {len(route_targets)} targets; policy maximum is "
            f"{selected_policy.maximum_route_targets}"
        )
    implementation_hashes = _implementation_hashes(
        solver_class,
        geometry_engine_class,
        solver_mode=solver_mode,
    )

    scenario = context.scenario
    if (
        scenario.ik_policy.max_attempts > _MAX_CANONICAL_IK_ATTEMPTS
        or scenario.ik_policy.max_iterations_per_attempt
        > _MAX_CANONICAL_IK_ITERATIONS
    ):
        raise TrajectorySimulationError("canonical IK effort exceeds trajectory caps")
    try:
        loaded_model = load_pinned_urdf(
            scenario.model_path,
            scenario.model_sha256,
        )
    except PinnedModelLoadError as exc:
        raise TrajectorySimulationError(
            f"could not load the pinned kinematic model: {exc}"
        ) from exc
    model = loaded_model.model
    fixed = model.joint("world_to_base_link")
    if (
        fixed.joint_type != "fixed"
        or fixed.parent_link != "world"
        or fixed.child_link != "base_link"
    ):
        raise TrajectorySimulationError("pinned URDF lost Wv_T_Ru contract")
    vendor_world_T_base_link = fixed.transform_at(None)
    _validate_study_input(context, study_input, vendor_world_T_base_link)

    default_path = scenario.path_policy
    selected_park = (
        selected_policy.park_xy_board_mm or default_path.park_xy_board_mm
    )
    park_xy = (float(selected_park[0]), float(selected_park[1]))
    _validate_park_xy(context, park_xy)
    geometry_settings = GeometricSimulationSettings(
        clearance_above_highest_obstacle_mm=(
            default_path.clearance_above_highest_obstacle_mm
        ),
        segment_clearance_mm=default_path.segment_clearance_mm,
        hover_height_mm=default_path.hover_height_mm,
        approach_height_mm=default_path.approach_height_mm,
        contact_overtravel_mm=default_path.contact_overtravel_mm,
        park_xy_board_mm=park_xy,
    )
    geometry = geometry_engine_class(geometry_settings).run(
        plan,
        context.snapshot,
        context.hardware_profile,
        context.scene,
        context.targets,
    )
    checks_by_id = _index_path_checks(geometry.checks)
    tool_length = (
        study_input.keyboard_tool_length_mm
        if plan.device.value == "keyboard"
        else study_input.phone_tool_length_mm
    )
    options = IkOptions(
        max_attempts=scenario.ik_policy.max_attempts,
        max_iterations_per_attempt=scenario.ik_policy.max_iterations_per_attempt,
    )
    solver_kwargs: dict[str, object] = {
        "model": model,
        "board_T_world": study_input.board_T_vendor_world,
        "hand_tcp_to_tip_z_mm": -tool_length,
        "fixed_gripper_position": scenario.fixed_gripper_position,
        "ready_arm_joint_positions": scenario.ready_arm_joint_positions_rad,
        "gripper_bounds_rad": scenario.controller_gripper_intersection_rad,
        "options": options,
        "joint_bounds_rad": scenario.controller_joint_intersection_rad,
    }
    solver = solver_class(**solver_kwargs)
    if solver_class is _CANONICAL_IK_SOLVER:
        if not isinstance(solver, RoArmM3NumericalIk):
            raise TrajectorySimulationError(
                "canonical IK constructor returned an unexpected implementation"
            )
        conditioning_solver = solver
    else:
        # Explicit test doubles may replace branch selection, but never the
        # canonical FK/Jacobian implementation or the evidence it serializes.
        conditioning_solver = _CANONICAL_IK_SOLVER(
            model=model,
            board_T_world=study_input.board_T_vendor_world,
            hand_tcp_to_tip_z_mm=-tool_length,
            fixed_gripper_position=scenario.fixed_gripper_position,
            ready_arm_joint_positions=scenario.ready_arm_joint_positions_rad,
            gripper_bounds_rad=scenario.controller_gripper_intersection_rad,
            options=options,
            joint_bounds_rad=scenario.controller_joint_intersection_rad,
        )

    rounds: list[TrajectorySearchRound] = []
    total_solves = 0
    termination = "NOMINAL_TOOL_TIP_PATH_CHECKS_FAILED"
    if geometry.all_checks_pass:
        for round_index in range(selected_policy.maximum_refinement_rounds + 1):
            maximum_step = selected_policy.maximum_cartesian_step_mm / (2**round_index)
            try:
                waypoints = _densify(
                    geometry.steps,
                    checks_by_id,
                    tuple(
                        f"{plan.device.value}:{target_id}"
                        for target_id in route_targets
                    ),
                    maximum_step,
                    selected_policy.maximum_waypoints_per_round,
                )
            except TrajectorySimulationError as exc:
                termination = f"BOUNDED_WAYPOINT_CONSTRUCTION_STOPPED: {exc}"
                break
            if total_solves + len(waypoints) > selected_policy.maximum_total_ik_solves:
                termination = "BOUNDED_TOTAL_IK_SOLVE_BUDGET_EXHAUSTED"
                break
            previous_solution: dict[str, float] | None = None
            results: list[JointTrajectoryWaypointResult] = []
            round_failure = None
            for waypoint in waypoints:
                seeds = (
                    ()
                    if previous_solution is None
                    else (
                        {
                            name: JointPosition.radians(value)
                            for name, value in previous_solution.items()
                        },
                    )
                )
                solved = solver.solve(
                    BoardToolTipTarget(waypoint.point_board),
                    seed_joint_positions=seeds,
                )
                total_solves += 1
                result = _evaluate_joint_trajectory_solution(
                    waypoint,
                    solved,
                    conditioning_solver,
                    scenario.controller_joint_intersection_rad,
                    previous_solution,
                    selected_policy,
                )
                results.append(result)
                if not result.accepted:
                    round_failure = result.failure_reason
                    break
                previous_solution = dict(result.solution_arm_joint_positions_rad)
            passed = len(results) == len(waypoints) and all(
                result.accepted for result in results
            )
            rounds.append(
                TrajectorySearchRound(
                    round_index=round_index,
                    maximum_cartesian_step_mm=maximum_step,
                    waypoints=waypoints,
                    joint_results=tuple(results),
                    status="PASS" if passed else "FAIL",
                    failure_reason=round_failure,
                )
            )
            if passed:
                termination = "ALL_DENSIFIED_WAYPOINTS_ACCEPTED"
                break
            if round_failure not in {
                "IK_NO_CONVERGED_SOLUTION",
                "MAXIMUM_ADJACENT_JOINT_DELTA_EXCEEDED",
            }:
                termination = f"NON_REFINABLE_FAILURE: {round_failure}"
                break
            if round_index == selected_policy.maximum_refinement_rounds:
                termination = "REFINEMENT_ROUND_LIMIT_EXHAUSTED"

    provenance = (
        ("snapshot_hash", context.snapshot.snapshot_hash),
        ("simulation_bundle_id", context.bundle_lock.bundle_id),
        ("simulation_bundle_sha256", context.bundle_lock.source_lock_sha256),
        ("hardware_profile_hash", context.hardware_profile.profile_hash),
        ("target_profile_sha256", context.targets.content_sha256),
        ("model_sha256", scenario.model_sha256),
        ("loaded_model_sha256", loaded_model.sha256),
        ("loaded_model_bytes", loaded_model.byte_count),
        ("alignment_report_hash", context.alignment.report_hash),
        ("plan_hash", plan.plan_hash),
        ("plan_profile_id", plan.profile_id),
        ("study_input_id", study_input.study_input_id),
        (
            "ik_solver_implementation",
            f"{solver_class.__module__}.{solver_class.__qualname__}",
        ),
        (
            "ik_solver_algorithm_version",
            (
                "DETERMINISTIC_BOUNDED_DLS_V1"
                if solver_class is _CANONICAL_IK_SOLVER
                else "EXPLICIT_TEST_DOUBLE"
            ),
        ),
        (
            "task_jacobian_conditioning_implementation",
            "rocell.kinematics.ik.RoArmM3NumericalIk."
            "diagnose_weighted_task_jacobian",
        ),
        (
            "task_jacobian_conditioning_algorithm_version",
            "SOLVER_WEIGHTED_RESIDUAL_FINITE_DIFFERENCE_GRAM_JACOBI_V2",
        ),
        (
            "task_jacobian_conditioning_solver_mode",
            "CANONICAL_IN_PACKAGE_IMPLEMENTATION",
        ),
        ("task_jacobian_conditioning_additional_ik_solves", 0),
        (
            "task_jacobian_numerical_rank_gate",
            "FULL_COLUMN_NUMERICAL_RANK_ONLY",
        ),
        ("normalized_task_jacobian_conditioning_gate_enabled", False),
        *implementation_hashes,
        ("ik_options", tuple(sorted(_ik_options_dict(options).items()))),
        (
            "worst_case_solver_iteration_budget",
            selected_policy.maximum_total_ik_solves
            * options.max_attempts
            * options.max_iterations_per_attempt,
        ),
        (
            "worst_case_task_jacobian_fk_evaluation_budget",
            selected_policy.maximum_total_ik_solves
            * MAX_TASK_JACOBIAN_FK_EVALUATIONS,
        ),
        ("rocell_runtime_version", __version__),
        ("previous_solution_seed_policy", "FIRST_SEED_AT_EVERY_SUBSEQUENT_WAYPOINT"),
        (
            "controller_joint_intersection_rad",
            tuple(
                (name, tuple(bounds))
                for name, bounds in scenario.controller_joint_intersection_rad.items()
            ),
        ),
        ("fixed_gripper_position_rad", scenario.fixed_gripper_position.value),
        ("fixed_gripper_in_arm_margin_gate", False),
    )
    return TrajectorySimulationReport(
        source_provenance=provenance,
        policy=selected_policy,
        study_input=study_input,
        device=plan.device.value,
        route_target_ids=route_targets,
        tool_length_mm=tool_length,
        park_xy_board_mm=park_xy,
        transit_plane_z_mm=geometry.transit_plane_z_mm,
        geometry_report_hash=geometry.report_hash,
        geometry_all_checks_passed=geometry.all_checks_pass,
        geometry_check_count=len(geometry.checks),
        rounds=tuple(rounds),
        total_ik_solves=total_solves,
        termination_reason=termination,
    )


def run_trajectory_simulation(
    context: SimulationContext,
    plan: ActionPlan,
    study_input: ReachStudyInput,
    policy: TrajectorySimulationPolicy | None = None,
) -> TrajectorySimulationReport:
    """Simulate a bounded keyboard or phone route without hardware access.

    Public calls always use the canonical in-package geometric engine and IK
    solver.  The private core's explicit injection seam exists only so unit
    tests can bind and label deterministic test doubles without misreporting
    them as the production implementation.
    """

    return _run_trajectory_simulation_with_implementations(
        context,
        plan,
        study_input,
        policy,
        solver_class=_CANONICAL_IK_SOLVER,
        geometry_engine_class=_CANONICAL_GEOMETRIC_ENGINE,
        solver_mode="CANONICAL_IN_PACKAGE_IMPLEMENTATION",
    )


def revalidate_trajectory_simulation_report(
    context: SimulationContext,
    plan: ActionPlan,
    report: TrajectorySimulationReport,
) -> TrajectorySimulationReport:
    """Independently attest one canonical trajectory report without solving IK.

    The validation reloads every locked simulation source, re-hashes the
    current implementation, reconstructs the pinned URDF model and nominal
    geometric route, and recomputes FK, task residuals, controller margins,
    adjacent selected-joint deltas, and the bounded weighted-task-Jacobian
    diagnostic from every serialized selected joint state.  It never invokes
    :meth:`RoArmM3NumericalIk.solve`, emits commands, opens transports, or
    grants motion authority.

    Reports created with an injected test solver are deliberately rejected:
    this is an attestation boundary for the canonical production simulation
    implementation, not a generic dataclass consistency check.
    """

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(plan, ActionPlan):
        raise TypeError("plan must be an ActionPlan")
    if not isinstance(report, TrajectorySimulationReport):
        raise TypeError("report must be a TrajectorySimulationReport")
    if not isinstance(report.policy, TrajectorySimulationPolicy):
        raise TypeError("report.policy must be a TrajectorySimulationPolicy")
    if not isinstance(report.study_input, ReachStudyInput):
        raise TypeError("report.study_input must be a ReachStudyInput")
    if not isinstance(report.rounds, tuple):
        raise TrajectorySimulationError("report rounds must be an immutable tuple")

    revalidate_simulation_context(context)
    if not context.alignment.all_checks_pass:
        raise TrajectorySimulationError("canonical placemat alignment must pass")

    scenario = context.scenario
    if (
        scenario.ik_policy.max_attempts > _MAX_CANONICAL_IK_ATTEMPTS
        or scenario.ik_policy.max_iterations_per_attempt
        > _MAX_CANONICAL_IK_ITERATIONS
    ):
        raise TrajectorySimulationError("canonical IK effort exceeds trajectory caps")
    try:
        loaded_model = load_pinned_urdf(
            scenario.model_path,
            scenario.model_sha256,
        )
    except PinnedModelLoadError as exc:
        raise TrajectorySimulationError(
            f"could not reload the pinned kinematic model: {exc}"
        ) from exc
    fixed = loaded_model.model.joint("world_to_base_link")
    if (
        fixed.joint_type != "fixed"
        or fixed.parent_link != "world"
        or fixed.child_link != "base_link"
    ):
        raise TrajectorySimulationError("pinned URDF lost Wv_T_Ru contract")
    _validate_study_input(
        context,
        report.study_input,
        fixed.transform_at(None),
    )

    route_targets = _route_target_ids(plan)
    if not route_targets:
        raise TrajectorySimulationError("route must contain at least one physical target")
    if len(route_targets) > report.policy.maximum_route_targets:
        raise TrajectorySimulationError("route exceeds the report policy target bound")
    maximum_plan_actions = 2 * report.policy.maximum_route_targets + 1
    if len(plan.actions) > maximum_plan_actions:
        raise TrajectorySimulationError("plan exceeds the report policy action bound")

    expected_park_source = (
        report.policy.park_xy_board_mm
        or scenario.path_policy.park_xy_board_mm
    )
    expected_park = (
        float(expected_park_source[0]),
        float(expected_park_source[1]),
    )
    _validate_park_xy(context, expected_park)
    expected_tool_length = (
        report.study_input.keyboard_tool_length_mm
        if plan.device.value == "keyboard"
        else report.study_input.phone_tool_length_mm
    )
    for actual, expected, label in (
        (report.device, plan.device.value, "device"),
        (report.route_target_ids, route_targets, "route targets"),
        (report.tool_length_mm, expected_tool_length, "tool length"),
        (report.park_xy_board_mm, expected_park, "park point"),
    ):
        if actual != expected:
            raise TrajectorySimulationError(
                f"trajectory report {label} differs from locked inputs"
            )

    options = IkOptions(
        max_attempts=scenario.ik_policy.max_attempts,
        max_iterations_per_attempt=scenario.ik_policy.max_iterations_per_attempt,
    )
    expected_provenance = _canonical_source_provenance(
        context,
        plan,
        report.study_input,
        report.policy,
        loaded_model_sha256=loaded_model.sha256,
        loaded_model_bytes=loaded_model.byte_count,
        options=options,
    )
    if report.source_provenance != expected_provenance:
        raise TrajectorySimulationError(
            "trajectory source provenance differs from locked inputs or current implementation"
        )

    path_policy = scenario.path_policy
    geometry_settings = GeometricSimulationSettings(
        clearance_above_highest_obstacle_mm=(
            path_policy.clearance_above_highest_obstacle_mm
        ),
        segment_clearance_mm=path_policy.segment_clearance_mm,
        hover_height_mm=path_policy.hover_height_mm,
        approach_height_mm=path_policy.approach_height_mm,
        contact_overtravel_mm=path_policy.contact_overtravel_mm,
        park_xy_board_mm=expected_park,
    )
    geometry = _CANONICAL_GEOMETRIC_ENGINE(geometry_settings).run(
        plan,
        context.snapshot,
        context.hardware_profile,
        context.scene,
        context.targets,
    )
    if (
        report.geometry_report_hash != geometry.report_hash
        or report.geometry_all_checks_passed is not geometry.all_checks_pass
        or report.geometry_check_count != len(geometry.checks)
        or report.transit_plane_z_mm != geometry.transit_plane_z_mm
    ):
        raise TrajectorySimulationError(
            "trajectory geometry evidence differs from a fresh canonical dry run"
        )
    if not geometry.all_checks_pass:
        if (
            report.rounds
            or report.total_ik_solves != 0
            or report.termination_reason != "NOMINAL_TOOL_TIP_PATH_CHECKS_FAILED"
        ):
            raise TrajectorySimulationError(
                "blocked geometry report contains inconsistent trajectory evidence"
            )
        return report

    if not report.rounds:
        raise TrajectorySimulationError(
            "passing canonical geometry report lacks trajectory rounds"
        )
    if len(report.rounds) > report.policy.maximum_refinement_rounds + 1:
        raise TrajectorySimulationError("trajectory report exceeds its refinement bound")

    checks_by_id = _index_path_checks(geometry.checks)
    expected_semantic_targets = tuple(
        f"{plan.device.value}:{target_id}" for target_id in route_targets
    )
    solver = _CANONICAL_IK_SOLVER(
        model=loaded_model.model,
        board_T_world=report.study_input.board_T_vendor_world,
        hand_tcp_to_tip_z_mm=-expected_tool_length,
        fixed_gripper_position=scenario.fixed_gripper_position,
        ready_arm_joint_positions=scenario.ready_arm_joint_positions_rad,
        gripper_bounds_rad=scenario.controller_gripper_intersection_rad,
        options=options,
        joint_bounds_rad=scenario.controller_joint_intersection_rad,
    )
    bounds = _validated_arm_joint_bounds(
        scenario.controller_joint_intersection_rad
    )
    recomputed_total_solves = 0
    for round_index, round_ in enumerate(report.rounds):
        if not isinstance(round_, TrajectorySearchRound):
            raise TypeError("report rounds must contain TrajectorySearchRound values")
        if not isinstance(round_.waypoints, tuple) or not isinstance(
            round_.joint_results, tuple
        ):
            raise TrajectorySimulationError(
                "trajectory round collections must be immutable tuples"
            )
        expected_step = report.policy.maximum_cartesian_step_mm / (2**round_index)
        if round_.round_index != round_index or round_.maximum_cartesian_step_mm != expected_step:
            raise TrajectorySimulationError("trajectory refinement round identity is inconsistent")
        expected_waypoints = _densify(
            geometry.steps,
            checks_by_id,
            expected_semantic_targets,
            expected_step,
            report.policy.maximum_waypoints_per_round,
        )
        if round_.waypoints != expected_waypoints:
            raise TrajectorySimulationError(
                "trajectory Cartesian waypoints differ from canonical densification"
            )
        if not 0 < len(round_.joint_results) <= len(round_.waypoints):
            raise TrajectorySimulationError(
                "trajectory round has invalid evaluated-waypoint coverage"
            )

        previous_solution: dict[str, float] | None = None
        for waypoint, result in zip(round_.waypoints, round_.joint_results):
            if not isinstance(result, JointTrajectoryWaypointResult):
                raise TypeError(
                    "trajectory joint results must be JointTrajectoryWaypointResult values"
                )
            if (
                result.waypoint_sequence != waypoint.sequence
                or result.phase is not waypoint.phase
                or result.action_index != waypoint.action_index
                or result.semantic_target != waypoint.semantic_target
            ):
                raise TrajectorySimulationError(
                    "trajectory joint result differs from its Cartesian waypoint"
                )
            solution_items = result.solution_arm_joint_positions_rad
            if not isinstance(solution_items, tuple) or tuple(
                name for name, _ in solution_items
            ) != ARM_JOINT_NAMES:
                raise TrajectorySimulationError(
                    "trajectory selected state must use the canonical arm-joint order"
                )
            solution = _validated_arm_joint_values(
                dict(solution_items),
                label="trajectory selected state",
                bounds=bounds,
            )
            if (
                isinstance(result.attempt_count, bool)
                or result.attempt_count != options.max_attempts
                or isinstance(result.selected_attempt_index, bool)
                or not 0 <= result.selected_attempt_index < result.attempt_count
            ):
                raise TrajectorySimulationError(
                    "trajectory IK attempt metadata is inconsistent with canonical options"
                )
            typed_solution = {
                name: JointPosition.radians(solution[name])
                for name in ARM_JOINT_NAMES
            }
            try:
                residual = solver.evaluate(
                    BoardToolTipTarget(waypoint.point_board),
                    typed_solution,
                )
            except IkContractError as exc:
                raise TrajectorySimulationError(
                    "trajectory selected state failed canonical FK evaluation"
                ) from exc
            solved_proxy = SimpleNamespace(
                converged=True,
                status=SimpleNamespace(value="CONVERGED"),
                solution_arm_joint_positions=tuple(
                    SimpleNamespace(
                        name=name,
                        position=SimpleNamespace(value=solution[name]),
                    )
                    for name in ARM_JOINT_NAMES
                ),
                residual=residual,
                selected_attempt_index=result.selected_attempt_index,
                attempts=(None,) * result.attempt_count,
            )
            expected_result = _evaluate_joint_trajectory_solution(
                waypoint,
                solved_proxy,
                solver,
                bounds,
                previous_solution,
                report.policy,
            )
            if result != expected_result:
                raise TrajectorySimulationError(
                    "trajectory joint/FK/residual/margin/continuity/conditioning evidence mismatch"
                )
            previous_solution = solution

        recomputed_total_solves += len(round_.joint_results)
        passed = len(round_.joint_results) == len(round_.waypoints) and all(
            result.accepted for result in round_.joint_results
        )
        expected_status = "PASS" if passed else "FAIL"
        expected_failure = None if passed else round_.joint_results[-1].failure_reason
        if round_.status != expected_status or round_.failure_reason != expected_failure:
            raise TrajectorySimulationError("trajectory round outcome is inconsistent")
        if passed and round_index != len(report.rounds) - 1:
            raise TrajectorySimulationError("trajectory search continued after a passing round")

    if report.total_ik_solves != recomputed_total_solves:
        raise TrajectorySimulationError("trajectory total IK solve count is inconsistent")
    if report.total_ik_solves > report.policy.maximum_total_ik_solves:
        raise TrajectorySimulationError("trajectory report exceeds its IK solve budget")
    final = report.rounds[-1]
    if final.all_waypoints_accepted:
        expected_termination = "ALL_DENSIFIED_WAYPOINTS_ACCEPTED"
    elif final.failure_reason not in {
        "IK_NO_CONVERGED_SOLUTION",
        "MAXIMUM_ADJACENT_JOINT_DELTA_EXCEEDED",
    }:
        expected_termination = f"NON_REFINABLE_FAILURE: {final.failure_reason}"
    elif final.round_index == report.policy.maximum_refinement_rounds:
        expected_termination = "REFINEMENT_ROUND_LIMIT_EXHAUSTED"
    else:
        raise TrajectorySimulationError(
            "trajectory report stopped before its required refinement round"
        )
    if report.termination_reason != expected_termination:
        raise TrajectorySimulationError("trajectory termination reason is inconsistent")
    return report


__all__ = [
    "CartesianRouteWaypoint",
    "JointTrajectoryWaypointResult",
    "TrajectorySimulationError",
    "TrajectorySimulationPolicy",
    "TrajectorySimulationReport",
    "evaluate_joint_trajectory_solution",
    "revalidate_trajectory_simulation_report",
    "run_trajectory_simulation",
]
