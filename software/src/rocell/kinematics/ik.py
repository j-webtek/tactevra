"""Deterministic, simulation-only inverse kinematics for RoArm-M3.

The solver in this module cannot emit controller commands.  It operates only
on the pinned URDF projection through :class:`rocell.geometry.UrdfModel` and
returns reports that are explicitly marked as simulation-only.

The task has five constrained dimensions for the five arm joints:

* tool-tip position in the board frame (three dimensions), and
* alignment of ``hand_tcp`` +Z with board +Z (two dimensions).

Rotation about the aligned +Z axis is intentionally unconstrained.  The sixth
movable URDF joint is the gripper; callers must provide its fixed typed-radian
position, but it is never included in the IK search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Mapping, Sequence

from rocell.geometry import (
    JointPosition,
    JointPositionUnit,
    Point3Mm,
    RigidTransform,
    Rotation3,
    UrdfModel,
    Vec3,
)
from rocell.models.units import finite_real


ARM_JOINT_NAMES: tuple[str, ...] = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
)
GRIPPER_JOINT_NAME = "link5_to_gripper_link"
HAND_TCP_LINK_NAME = "hand_tcp"
_EXPECTED_MOVABLE_JOINTS = frozenset((*ARM_JOINT_NAMES, GRIPPER_JOINT_NAME))
MAX_TASK_JACOBIAN_FK_EVALUATIONS = 1 + 2 * len(ARM_JOINT_NAMES)
# The diagnostic forms J.T*J before the bounded eigendecomposition, which
# squares the condition number.  A 1e-8 singular-value floor proved too close
# to floating-point/eigensolver roundoff: exact rank-four integer-factor
# matrices could retain a spurious fifth singular value around 1.6e-8 of the
# maximum.  Keep the gate deliberately conservative at 1e-7.  Values below or
# equal to this floor are reported as zero; this is a fail-closed numerical-rank
# policy, not a physical singularity threshold.
_TASK_JACOBIAN_RANK_RELATIVE_TOLERANCE = 1e-7
_JACOBI_EIGEN_RELATIVE_TOLERANCE = 1e-14
_JACOBI_EIGEN_MAX_SWEEPS = 32
_EXPECTED_JOINT_GRAPH: dict[str, tuple[str, str, str]] = {
    "world_to_base_link": ("fixed", "world", "base_link"),
    "base_link_to_link1": ("revolute", "base_link", "link1"),
    "link1_to_link2": ("revolute", "link1", "link2"),
    "link2_to_link3": ("revolute", "link2", "link3"),
    "link3_to_link4": ("revolute", "link3", "link4"),
    "link4_to_link5": ("revolute", "link4", "link5"),
    "link5_to_gripper_link": ("revolute", "link5", "gripper_link"),
    "link5_to_hand_tcp": ("fixed", "link5", "hand_tcp"),
}
_BOARD_UP = Vec3(0.0, 0.0, 1.0)


class IkContractError(ValueError):
    """The model, frames, units, or requested seed violate the IK contract."""


class IkStatus(str, Enum):
    """Terminal status for a simulation-only IK request."""

    CONVERGED = "CONVERGED"
    NO_CONVERGED_SOLUTION = "NO_CONVERGED_SOLUTION"


@dataclass(frozen=True, slots=True)
class BoardToolTipTarget:
    """Tool-tip target in an explicitly labelled board frame.

    The desired direction is not a field because it is fixed by contract:
    ``hand_tcp`` +Z must align with the target point's frame +Z.  Rotation
    about that axis is free.
    """

    position_mm: Point3Mm

    def __post_init__(self) -> None:
        if not isinstance(self.position_mm, Point3Mm):
            raise TypeError("position_mm must be a frame-labelled Point3Mm")


@dataclass(frozen=True, slots=True)
class IkOptions:
    """Numerical controls, with all angular quantities expressed in radians."""

    max_attempts: int = 10
    max_iterations_per_attempt: int = 140
    position_tolerance_mm: float = 0.20
    alignment_tolerance_rad: float = 0.003
    orientation_weight_mm_per_rad: float = 80.0
    finite_difference_step_rad: float = 1e-5
    initial_damping: float = 1.0
    minimum_damping: float = 1e-4
    maximum_damping: float = 1e7
    max_joint_step_rad: float = 0.30
    line_search_steps: int = 9

    def __post_init__(self) -> None:
        for name in ("max_attempts", "max_iterations_per_attempt", "line_search_steps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_attempts < 2:
            raise ValueError("max_attempts must be at least two for deterministic multi-start IK")

        positive_fields = (
            "position_tolerance_mm",
            "alignment_tolerance_rad",
            "orientation_weight_mm_per_rad",
            "finite_difference_step_rad",
            "initial_damping",
            "minimum_damping",
            "maximum_damping",
            "max_joint_step_rad",
        )
        for name in positive_fields:
            value = finite_real(getattr(self, name), name=name)
            if value <= 0.0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if self.minimum_damping > self.initial_damping:
            raise ValueError("minimum_damping cannot exceed initial_damping")
        if self.initial_damping > self.maximum_damping:
            raise ValueError("initial_damping cannot exceed maximum_damping")


@dataclass(frozen=True, slots=True)
class NamedJointPosition:
    """One named, typed joint value in a deterministic sequence."""

    name: str
    position: JointPosition

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("joint name must be a non-empty string")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.position, JointPosition):
            raise TypeError("position must be a JointPosition")
        if self.position.unit is not JointPositionUnit.RADIAN:
            raise IkContractError(f"Joint {self.name!r} must be expressed in typed radians")


@dataclass(frozen=True, slots=True)
class PoseResidual:
    """Unweighted physical task error for one candidate joint state."""

    tip_position_board_mm: Point3Mm
    hand_tcp_z_axis_board: Vec3
    position_error_mm: float
    alignment_error_rad: float
    weighted_residual_norm_mm: float


@dataclass(frozen=True, slots=True)
class WeightedTaskJacobianConditioning:
    """Local conditioning of the solver's weighted five-constraint task.

    This is not a full six-dimensional geometric Jacobian or a physical
    singularity/manipulability certificate.  It differentiates the exact
    residual used by this simulation-only IK solver: three tool-tip position
    rows plus the three-component representation of a two-DOF direction
    alignment error, scaled by ``orientation_weight_mm_per_rad``.
    """

    target: BoardToolTipTarget
    arm_joint_positions: tuple[NamedJointPosition, ...]
    singular_values_solver_weighted_mm_per_rad: tuple[float, ...]
    numerical_rank: int
    rank_relative_tolerance: float
    normalized_minimum_singular_value: float
    condition_number: float | None
    finite_difference_step_rad: float
    orientation_weight_mm_per_rad: float
    finite_difference_fk_evaluations: int
    jacobi_eigen_sweeps: int
    simulation_only: bool = field(default=True, init=False)
    live_motion_authorized: bool = field(default=False, init=False)
    hardware_commands_generated: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.target, BoardToolTipTarget):
            raise TypeError("target must be a BoardToolTipTarget")
        positions = tuple(self.arm_joint_positions)
        if tuple(item.name for item in positions) != ARM_JOINT_NAMES:
            raise IkContractError(
                "Task-Jacobian state must use the exact arm-joint order"
            )
        object.__setattr__(self, "arm_joint_positions", positions)

        singular_values = tuple(
            finite_real(value, name="task Jacobian singular value")
            for value in self.singular_values_solver_weighted_mm_per_rad
        )
        if len(singular_values) != len(ARM_JOINT_NAMES):
            raise IkContractError("Task Jacobian must expose five singular values")
        if any(value < 0.0 for value in singular_values):
            raise IkContractError("Task Jacobian singular values must be non-negative")
        if any(
            left + 1e-12 < right
            for left, right in zip(singular_values, singular_values[1:])
        ):
            raise IkContractError("Task Jacobian singular values must be descending")
        object.__setattr__(
            self,
            "singular_values_solver_weighted_mm_per_rad",
            singular_values,
        )

        if (
            isinstance(self.numerical_rank, bool)
            or not isinstance(self.numerical_rank, int)
            or not 0 <= self.numerical_rank <= len(ARM_JOINT_NAMES)
        ):
            raise IkContractError("Task Jacobian numerical rank must be in [0, 5]")
        rank_tolerance = finite_real(
            self.rank_relative_tolerance,
            name="task Jacobian rank relative tolerance",
        )
        normalized = finite_real(
            self.normalized_minimum_singular_value,
            name="normalized minimum task Jacobian singular value",
        )
        if not 0.0 < rank_tolerance < 1.0:
            raise IkContractError("Task Jacobian rank tolerance must be in (0, 1)")
        if rank_tolerance != _TASK_JACOBIAN_RANK_RELATIVE_TOLERANCE:
            raise IkContractError(
                "Task Jacobian rank tolerance must equal the implementation constant"
            )
        if not 0.0 <= normalized <= 1.0 + 1e-12:
            raise IkContractError(
                "Normalized minimum task Jacobian singular value must be in [0, 1]"
            )
        expected_rank = sum(value > 0.0 for value in singular_values)
        if self.numerical_rank != expected_rank:
            raise IkContractError(
                "Task Jacobian numerical rank disagrees with its singular values"
            )
        maximum = singular_values[0]
        minimum = singular_values[-1]
        expected_normalized = 0.0 if maximum == 0.0 else minimum / maximum
        if not math.isclose(
            normalized,
            expected_normalized,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise IkContractError(
                "Normalized minimum task Jacobian singular value is inconsistent"
            )
        if self.condition_number is not None:
            condition = finite_real(
                self.condition_number,
                name="task Jacobian condition number",
            )
            if condition < 1.0:
                raise IkContractError("Task Jacobian condition number must be >= 1")
            if self.numerical_rank != len(ARM_JOINT_NAMES):
                raise IkContractError(
                    "Rank-deficient task Jacobian cannot claim a finite condition number"
                )
            expected_condition = maximum / minimum
            if not math.isclose(
                condition,
                expected_condition,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise IkContractError(
                    "Task Jacobian condition number is inconsistent"
                )
        elif self.numerical_rank == len(ARM_JOINT_NAMES):
            raise IkContractError(
                "Full-rank task Jacobian must expose a finite condition number"
            )
        for value, name in (
            (self.finite_difference_step_rad, "finite difference step"),
            (self.orientation_weight_mm_per_rad, "orientation weight"),
        ):
            if finite_real(value, name=name) <= 0.0:
                raise IkContractError(f"{name} must be positive")
        if (
            isinstance(self.finite_difference_fk_evaluations, bool)
            or not isinstance(self.finite_difference_fk_evaluations, int)
            or not 1
            <= self.finite_difference_fk_evaluations
            <= MAX_TASK_JACOBIAN_FK_EVALUATIONS
        ):
            raise IkContractError("Task Jacobian FK evaluation count is out of bounds")
        if (
            isinstance(self.jacobi_eigen_sweeps, bool)
            or not isinstance(self.jacobi_eigen_sweeps, int)
            or not 0 <= self.jacobi_eigen_sweeps <= _JACOBI_EIGEN_MAX_SWEEPS
        ):
            raise IkContractError("Task Jacobian eigen-solver sweep count is invalid")

    @property
    def full_column_rank(self) -> bool:
        return self.numerical_rank == len(ARM_JOINT_NAMES)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "rocell.simulation.solver_weighted_task_jacobian.v1",
            "metric_scope": "LOCAL_SOLVER_WEIGHTED_FIVE_CONSTRAINT_TASK_ONLY",
            "simulation_only": self.simulation_only,
            "live_motion_authorized": self.live_motion_authorized,
            "hardware_commands_generated": self.hardware_commands_generated,
            "physical_singularity_acceptance": False,
            "collision_evaluated": False,
            "target_tip_position_board_mm": {
                "frame": self.target.position_mm.frame,
                "x": self.target.position_mm.x,
                "y": self.target.position_mm.y,
                "z": self.target.position_mm.z,
            },
            "arm_joint_positions_rad": {
                item.name: item.position.value for item in self.arm_joint_positions
            },
            "task_shape": {"residual_rows": 6, "arm_joint_columns": 5},
            "tool_yaw_about_aligned_z_constrained": False,
            "singular_values_solver_weighted_mm_per_rad": list(
                self.singular_values_solver_weighted_mm_per_rad
            ),
            "numerical_rank": self.numerical_rank,
            "full_column_rank": self.full_column_rank,
            "rank_relative_tolerance": self.rank_relative_tolerance,
            "rank_cutoff_interpretation": (
                "CONSERVATIVE_NUMERICAL_FLOOR_AFTER_GRAM_EIGENDECOMPOSITION"
            ),
            "normalized_minimum_singular_value": (
                self.normalized_minimum_singular_value
            ),
            "condition_number": self.condition_number,
            "finite_difference_step_rad": self.finite_difference_step_rad,
            "orientation_weight_mm_per_rad": self.orientation_weight_mm_per_rad,
            "finite_difference_fk_evaluations": (
                self.finite_difference_fk_evaluations
            ),
            "jacobi_eigen_solver": {
                "algorithm": "BOUNDED_CYCLIC_SYMMETRIC_JACOBI_V1",
                "sweeps": self.jacobi_eigen_sweeps,
                "maximum_sweeps": _JACOBI_EIGEN_MAX_SWEEPS,
                "relative_tolerance": _JACOBI_EIGEN_RELATIVE_TOLERANCE,
            },
            "limitations": [
                "Residual-row scaling follows the pinned IK orientation weight.",
                "The metric is local to one nominal joint state and tool length.",
                "It is not a full 6D geometric manipulability, force, dynamics, or physical singularity certificate.",
            ],
        }


@dataclass(frozen=True, slots=True)
class IkAttemptReport:
    seed_index: int
    seed_joint_positions: tuple[NamedJointPosition, ...]
    iterations: int
    converged: bool
    termination_reason: str
    residual: PoseResidual


@dataclass(frozen=True, slots=True)
class IkResult:
    """Simulation-only result; a failed result never exposes joint solutions."""

    status: IkStatus
    target: BoardToolTipTarget
    solution_arm_joint_positions: tuple[NamedJointPosition, ...]
    fixed_gripper_position: NamedJointPosition
    residual: PoseResidual
    attempts: tuple[IkAttemptReport, ...]
    selected_attempt_index: int
    simulation_only: bool = field(default=True, init=False)
    live_motion_authorized: bool = field(default=False, init=False)
    hardware_commands_generated: int = field(default=0, init=False)

    @property
    def converged(self) -> bool:
        return self.status is IkStatus.CONVERGED

    def to_dict(self) -> dict[str, object]:
        """Return a stable diagnostic record, never a hardware command."""

        solution = {
            item.name: item.position.value for item in self.solution_arm_joint_positions
        }
        return {
            "schema": "rocell.simulation.ik.v1",
            "simulation_only": self.simulation_only,
            "live_motion_authorized": self.live_motion_authorized,
            "hardware_commands_generated": self.hardware_commands_generated,
            "status": self.status.value,
            "converged": self.converged,
            "target_tip_position_board_mm": {
                "frame": self.target.position_mm.frame,
                "x": self.target.position_mm.x,
                "y": self.target.position_mm.y,
                "z": self.target.position_mm.z,
            },
            "target_hand_tcp_z_axis_board": [0.0, 0.0, 1.0],
            "solution_arm_joint_positions_rad": solution,
            "fixed_gripper_position_rad": self.fixed_gripper_position.position.value,
            "selected_attempt_index": self.selected_attempt_index,
            "residual": _residual_dict(self.residual),
            "attempts": [
                {
                    "seed_index": attempt.seed_index,
                    "seed_joint_positions_rad": {
                        item.name: item.position.value for item in attempt.seed_joint_positions
                    },
                    "iterations": attempt.iterations,
                    "converged": attempt.converged,
                    "termination_reason": attempt.termination_reason,
                    "residual": _residual_dict(attempt.residual),
                }
                for attempt in self.attempts
            ],
        }


@dataclass(frozen=True, slots=True)
class _Evaluation:
    residual_vector: tuple[float, ...]
    report: PoseResidual

    @property
    def objective(self) -> float:
        return sum(value * value for value in self.residual_vector)


class RoArmM3NumericalIk:
    """Bounded damped-least-squares IK for the pinned RoArm-M3 model.

    ``board_T_world`` is mandatory.  Its child frame must be the URDF root and
    target points must use its parent frame.  ``hand_tcp_to_tip_z_mm`` is a
    translation along hand_tcp -Z; positive offsets are rejected.
    """

    def __init__(
        self,
        *,
        model: UrdfModel,
        board_T_world: RigidTransform,
        hand_tcp_to_tip_z_mm: object,
        fixed_gripper_position: JointPosition,
        ready_arm_joint_positions: Mapping[str, JointPosition] | None = None,
        gripper_bounds_rad: tuple[float, float] | None = None,
        options: IkOptions | None = None,
        joint_bounds_rad: Mapping[str, tuple[float, float]] | None = None,
    ) -> None:
        if not isinstance(model, UrdfModel):
            raise TypeError("model must be a UrdfModel")
        if not isinstance(board_T_world, RigidTransform):
            raise TypeError("board_T_world must be a RigidTransform")
        if not isinstance(fixed_gripper_position, JointPosition):
            raise TypeError("fixed_gripper_position must be a JointPosition")
        if options is not None and not isinstance(options, IkOptions):
            raise TypeError("options must be an IkOptions")

        self._validate_model(model)
        if board_T_world.child_frame != model.root_link:
            raise IkContractError(
                "board_T_world child frame must equal the URDF root "
                f"{model.root_link!r}, got {board_T_world.child_frame!r}"
            )
        if board_T_world.parent_frame == board_T_world.child_frame:
            raise IkContractError("board_T_world must connect distinct board and world frames")

        tip_offset = finite_real(hand_tcp_to_tip_z_mm, name="hand_tcp_to_tip_z_mm")
        if tip_offset > 0.0:
            raise IkContractError("hand_tcp_to_tip_z_mm must be zero or negative (hand_tcp -Z)")
        gripper = model.joint(GRIPPER_JOINT_NAME)
        assert gripper.limit is not None
        try:
            gripper.limit.validate(fixed_gripper_position, joint_name=GRIPPER_JOINT_NAME)
        except (TypeError, ValueError) as exc:
            raise IkContractError(f"Invalid fixed gripper position: {exc}") from exc
        if gripper_bounds_rad is not None:
            if not isinstance(gripper_bounds_rad, (tuple, list)) or len(gripper_bounds_rad) != 2:
                raise IkContractError("gripper_bounds_rad must contain lower and upper")
            gripper_lower = finite_real(gripper_bounds_rad[0], name="gripper lower bound")
            gripper_upper = finite_real(gripper_bounds_rad[1], name="gripper upper bound")
            assert gripper.limit.lower is not None and gripper.limit.upper is not None
            urdf_gripper_lower = gripper.limit.lower.value
            urdf_gripper_upper = gripper.limit.upper.value
            if (
                gripper_lower >= gripper_upper
                or gripper_lower < urdf_gripper_lower
                or gripper_upper > urdf_gripper_upper
            ):
                raise IkContractError(
                    "gripper_bounds_rad must be an ordered subset of the URDF gripper range"
                )
            if not gripper_lower <= fixed_gripper_position.value <= gripper_upper:
                raise IkContractError("Fixed gripper position leaves gripper_bounds_rad")

        self.model = model
        self.board_T_world = board_T_world
        self.hand_tcp_to_tip_z_mm = tip_offset
        self.fixed_gripper_position = fixed_gripper_position
        self.gripper_bounds_rad = gripper_bounds_rad
        self.options = options or IkOptions()
        urdf_bounds = {
            name: self._urdf_joint_bounds(name) for name in ARM_JOINT_NAMES
        }
        effective_bounds: dict[str, tuple[float, float]]
        if joint_bounds_rad is None:
            effective_bounds = dict(urdf_bounds)
        else:
            if not isinstance(joint_bounds_rad, Mapping):
                raise TypeError("joint_bounds_rad must be a mapping")
            if set(joint_bounds_rad) != set(ARM_JOINT_NAMES):
                missing = sorted(set(ARM_JOINT_NAMES) - set(joint_bounds_rad))
                extra = sorted(set(joint_bounds_rad) - set(ARM_JOINT_NAMES))
                raise IkContractError(
                    "joint_bounds_rad must cover the five arm joints; "
                    f"missing={missing}, extra={extra}"
                )
            effective_bounds = {}
            for name in ARM_JOINT_NAMES:
                raw = joint_bounds_rad[name]
                if not isinstance(raw, (tuple, list)) or len(raw) != 2:
                    raise IkContractError(
                        f"joint_bounds_rad[{name!r}] must contain lower and upper"
                    )
                lower = finite_real(raw[0], name=f"{name} lower bound")
                upper = finite_real(raw[1], name=f"{name} upper bound")
                urdf_lower, urdf_upper = urdf_bounds[name]
                if lower >= upper:
                    raise IkContractError(
                        f"joint_bounds_rad[{name!r}] lower must be below upper"
                    )
                if lower < urdf_lower or upper > urdf_upper:
                    raise IkContractError(
                        f"joint_bounds_rad[{name!r}] must remain inside URDF "
                        f"[{urdf_lower}, {urdf_upper}]"
                    )
                effective_bounds[name] = (lower, upper)
        self._bound_by_name = effective_bounds
        self._bounds = tuple(effective_bounds[name] for name in ARM_JOINT_NAMES)
        if ready_arm_joint_positions is None:
            published_ready = (0.0, 0.0, 2.618, -1.0472, 0.0)
            self._ready_seed = tuple(
                _clamp(value, lower, upper)
                for value, (lower, upper) in zip(published_ready, self._bounds)
            )
        else:
            self._ready_seed = self._validate_seed(
                ready_arm_joint_positions,
                label="ready_arm_joint_positions",
            )
        self._hand_tcp_T_tip = RigidTransform(
            parent_frame=HAND_TCP_LINK_NAME,
            child_frame="tool_tip",
            rotation=Rotation3.identity(),
            translation_mm=Vec3(0.0, 0.0, tip_offset),
        )

    @staticmethod
    def _validate_model(model: UrdfModel) -> None:
        if model.name != "roarm_m3":
            raise IkContractError(f"Expected URDF robot 'roarm_m3', got {model.name!r}")
        if model.root_link != "world":
            raise IkContractError(f"Expected URDF root 'world', got {model.root_link!r}")
        if HAND_TCP_LINK_NAME not in model.link_names:
            raise IkContractError("URDF is missing required planning link 'hand_tcp'")
        actual_joint_names = set(model.joint_names)
        expected_joint_names = set(_EXPECTED_JOINT_GRAPH)
        if actual_joint_names != expected_joint_names:
            missing = sorted(expected_joint_names - actual_joint_names)
            extra = sorted(actual_joint_names - expected_joint_names)
            raise IkContractError(
                f"RoArm-M3 joint-graph mismatch; missing={missing}, extra={extra}"
            )
        for name, expected in _EXPECTED_JOINT_GRAPH.items():
            joint = model.joint(name)
            actual = (joint.joint_type, joint.parent_link, joint.child_link)
            if actual != expected:
                raise IkContractError(
                    f"Joint {name!r} graph mismatch; expected={expected}, got={actual}"
                )
        movable = frozenset(model.movable_joint_names)
        if movable != _EXPECTED_MOVABLE_JOINTS:
            missing = sorted(_EXPECTED_MOVABLE_JOINTS - movable)
            extra = sorted(movable - _EXPECTED_MOVABLE_JOINTS)
            raise IkContractError(
                f"RoArm-M3 movable-joint mismatch; missing={missing}, extra={extra}"
            )
        for name in (*ARM_JOINT_NAMES, GRIPPER_JOINT_NAME):
            joint = model.joint(name)
            if joint.joint_type != "revolute":
                raise IkContractError(f"Joint {name!r} must be bounded revolute")
            if joint.limit is None or joint.limit.lower is None or joint.limit.upper is None:
                raise IkContractError(f"Joint {name!r} must have exact finite bounds")
            if joint.limit.position_unit is not JointPositionUnit.RADIAN:
                raise IkContractError(f"Joint {name!r} bounds must be radians")

        hand_joint = model.joint("link5_to_hand_tcp")
        if (
            hand_joint.joint_type != "fixed"
            or hand_joint.parent_link != "link5"
            or hand_joint.child_link != HAND_TCP_LINK_NAME
        ):
            raise IkContractError("URDF hand_tcp fixed-joint contract does not match RoArm-M3")

    def _urdf_joint_bounds(self, name: str) -> tuple[float, float]:
        limit = self.model.joint(name).limit
        assert limit is not None and limit.lower is not None and limit.upper is not None
        return (limit.lower.value, limit.upper.value)

    def solve(
        self,
        target: BoardToolTipTarget,
        *,
        seed_joint_positions: Sequence[Mapping[str, JointPosition]] = (),
    ) -> IkResult:
        """Solve a board-frame target with deterministic bounded multi-start DLS.

        Supplied seeds are validated strictly, tried first, and then augmented
        with deterministic model-bounded seeds up to ``max_attempts``.
        Every configured attempt is evaluated so reports are repeatable and do
        not depend on an early-success shortcut.
        """

        self._validate_target(target)
        seeds = self._build_seeds(seed_joint_positions, target)
        attempt_states: list[tuple[IkAttemptReport, tuple[float, ...]]] = []
        for seed_index, seed in enumerate(seeds):
            report, final_values = self._solve_attempt(target, seed_index, seed)
            attempt_states.append((report, final_values))

        selected_index = min(
            range(len(attempt_states)),
            key=lambda index: (
                0 if attempt_states[index][0].converged else 1,
                attempt_states[index][0].residual.weighted_residual_norm_mm,
                index,
            ),
        )
        selected_report, selected_values = attempt_states[selected_index]
        converged = selected_report.converged
        solution = self._named_positions(selected_values) if converged else ()
        return IkResult(
            status=IkStatus.CONVERGED if converged else IkStatus.NO_CONVERGED_SOLUTION,
            target=target,
            solution_arm_joint_positions=solution,
            fixed_gripper_position=NamedJointPosition(
                GRIPPER_JOINT_NAME,
                self.fixed_gripper_position,
            ),
            residual=selected_report.residual,
            attempts=tuple(report for report, _ in attempt_states),
            selected_attempt_index=selected_index,
        )

    def evaluate(
        self,
        target: BoardToolTipTarget,
        arm_joint_positions: Mapping[str, JointPosition],
    ) -> PoseResidual:
        """Evaluate one complete typed arm state without solving or commanding."""

        self._validate_target(target)
        values = self._validate_seed(arm_joint_positions, label="arm_joint_positions")
        return self._evaluate_values(target, values).report

    def diagnose_weighted_task_jacobian(
        self,
        target: BoardToolTipTarget,
        arm_joint_positions: Mapping[str, JointPosition],
    ) -> WeightedTaskJacobianConditioning:
        """Evaluate bounded local conditioning of the exact IK residual.

        The calculation uses at most eleven FK evaluations (one centre plus
        two per arm joint), followed by a fixed-size bounded Jacobi
        eigendecomposition of ``J.T * J``.  It neither checks collision nor
        grants physical singularity acceptance.
        """

        self._validate_target(target)
        values = self._validate_seed(
            arm_joint_positions,
            label="arm_joint_positions",
        )
        centre = self._evaluate_values(target, values)
        jacobian = self._finite_difference_jacobian(target, values, centre)
        finite_difference_evaluations = 1 + sum(
            2
            if upper - value >= self.options.finite_difference_step_rad
            and value - lower >= self.options.finite_difference_step_rad
            else 1
            for value, (lower, upper) in zip(values, self._bounds)
        )
        if finite_difference_evaluations > MAX_TASK_JACOBIAN_FK_EVALUATIONS:
            raise IkContractError("Task Jacobian exceeded its FK evaluation bound")

        gram = tuple(
            tuple(
                sum(row[left] * row[right] for row in jacobian)
                for right in range(len(ARM_JOINT_NAMES))
            )
            for left in range(len(ARM_JOINT_NAMES))
        )
        eigenvalues, sweeps = _symmetric_eigenvalues_jacobi(gram)
        largest_eigenvalue = max(eigenvalues, default=0.0)
        negative_tolerance = max(1e-12, largest_eigenvalue * 1e-12)
        if any(value < -negative_tolerance for value in eigenvalues):
            raise IkContractError("Task Jacobian Gram matrix is not positive semidefinite")
        raw_singular_values = tuple(
            math.sqrt(max(0.0, value)) for value in eigenvalues
        )
        maximum = raw_singular_values[0]
        rank_cutoff = maximum * _TASK_JACOBIAN_RANK_RELATIVE_TOLERANCE
        # Forming J.T*J squares the condition number. Values at or beneath this
        # serialized conservative numerical-rank floor are reported as zero
        # rather than as a misleading finite condition number dominated by
        # roundoff.  This is intentionally not a physical acceptance limit.
        singular_values = tuple(
            0.0 if value <= rank_cutoff else value
            for value in raw_singular_values
        )
        minimum = singular_values[-1]
        numerical_rank = sum(value > 0.0 for value in singular_values)
        normalized_minimum = 0.0 if maximum == 0.0 else minimum / maximum
        condition_number = (
            maximum / minimum
            if numerical_rank == len(ARM_JOINT_NAMES) and minimum > 0.0
            else None
        )
        return WeightedTaskJacobianConditioning(
            target=target,
            arm_joint_positions=self._named_positions(values),
            singular_values_solver_weighted_mm_per_rad=singular_values,
            numerical_rank=numerical_rank,
            rank_relative_tolerance=_TASK_JACOBIAN_RANK_RELATIVE_TOLERANCE,
            normalized_minimum_singular_value=normalized_minimum,
            condition_number=condition_number,
            finite_difference_step_rad=self.options.finite_difference_step_rad,
            orientation_weight_mm_per_rad=(
                self.options.orientation_weight_mm_per_rad
            ),
            finite_difference_fk_evaluations=finite_difference_evaluations,
            jacobi_eigen_sweeps=sweeps,
        )

    def _validate_target(self, target: BoardToolTipTarget) -> None:
        if not isinstance(target, BoardToolTipTarget):
            raise TypeError("target must be a BoardToolTipTarget")
        if target.position_mm.frame != self.board_T_world.parent_frame:
            raise IkContractError(
                f"Target is in frame {target.position_mm.frame!r}; expected board frame "
                f"{self.board_T_world.parent_frame!r}"
            )

    def _build_seeds(
        self,
        supplied: Sequence[Mapping[str, JointPosition]],
        target: BoardToolTipTarget,
    ) -> tuple[tuple[float, ...], ...]:
        if isinstance(supplied, (str, bytes)) or not isinstance(supplied, Sequence):
            raise TypeError("seed_joint_positions must be a sequence of mappings")

        candidates: list[tuple[float, ...]] = [
            self._validate_seed(seed, label=f"seed_joint_positions[{index}]")
            for index, seed in enumerate(supplied)
        ]
        candidates.extend(self._default_seeds(target))

        unique: list[tuple[float, ...]] = []
        seen: set[tuple[float, ...]] = set()
        for candidate in candidates:
            key = tuple(round(value, 12) for value in candidate)
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
            if len(unique) == self.options.max_attempts:
                break
        if len(unique) < 2:
            raise IkContractError("IK requires at least two distinct deterministic seeds")
        return tuple(unique)

    def _validate_seed(
        self,
        seed: Mapping[str, JointPosition],
        *,
        label: str,
    ) -> tuple[float, ...]:
        if not isinstance(seed, Mapping):
            raise TypeError(f"{label} must be a mapping")
        if any(not isinstance(name, str) for name in seed):
            raise IkContractError(f"{label} joint names must be strings")
        names = set(seed)
        expected = set(ARM_JOINT_NAMES)
        if names != expected:
            missing = sorted(expected - names)
            extra = sorted(names - expected)
            raise IkContractError(f"{label} joint mismatch; missing={missing}, extra={extra}")

        result: list[float] = []
        for name in ARM_JOINT_NAMES:
            value = seed[name]
            if not isinstance(value, JointPosition):
                raise IkContractError(f"{label} joint {name!r} must be a JointPosition")
            if value.unit is not JointPositionUnit.RADIAN:
                raise IkContractError(f"{label} joint {name!r} must use typed radians")
            lower, upper = self._bound_by_name[name]
            if value.value < lower or value.value > upper:
                raise IkContractError(
                    f"{label} joint {name!r} value {value.value} is outside [{lower}, {upper}]"
                )
            result.append(value.value)
        return tuple(result)

    def _default_seeds(self, target: BoardToolTipTarget) -> tuple[tuple[float, ...], ...]:
        midpoint = tuple((lower + upper) * 0.5 for lower, upper in self._bounds)
        zero = tuple(_clamp(0.0, lower, upper) for lower, upper in self._bounds)

        # The ready pose is a seed only; scenario loading and this constructor
        # both require it to remain inside the effective joint intersection.
        ready = self._ready_seed

        target_world = self.board_T_world.inverse().transform_point(target.position_mm)
        target_base_yaw = math.atan2(target_world.y, target_world.x)
        target_ready = list(ready)
        target_ready[0] = _clamp(target_base_yaw, *self._bounds[0])

        result: list[tuple[float, ...]] = [tuple(target_ready), ready, midpoint, zero]
        primes = (2, 3, 5, 7, 11)
        index = 1
        while len(result) < self.options.max_attempts + 4:
            fractions = tuple(_halton(index, prime) for prime in primes)
            result.append(
                tuple(
                    lower + fraction * (upper - lower)
                    for fraction, (lower, upper) in zip(fractions, self._bounds)
                )
            )
            index += 1
        return tuple(result)

    def _solve_attempt(
        self,
        target: BoardToolTipTarget,
        seed_index: int,
        seed: tuple[float, ...],
    ) -> tuple[IkAttemptReport, tuple[float, ...]]:
        values = seed
        evaluation = self._evaluate_values(target, values)
        damping = self.options.initial_damping
        iterations = 0
        termination = "MAX_ITERATIONS"

        if self._has_converged(evaluation.report):
            termination = "TOLERANCES_SATISFIED"
        else:
            for iteration in range(1, self.options.max_iterations_per_attempt + 1):
                iterations = iteration
                jacobian = self._finite_difference_jacobian(target, values, evaluation)
                accepted = False
                local_damping = damping

                while local_damping <= self.options.maximum_damping:
                    delta = _damped_least_squares_delta(
                        jacobian,
                        evaluation.residual_vector,
                        local_damping,
                    )
                    largest = max(abs(value) for value in delta)
                    if largest > self.options.max_joint_step_rad:
                        scale = self.options.max_joint_step_rad / largest
                        delta = tuple(value * scale for value in delta)
                    if max(abs(value) for value in delta) <= 1e-12:
                        local_damping *= 10.0
                        continue

                    for line_step in range(self.options.line_search_steps):
                        alpha = 0.5**line_step
                        candidate = tuple(
                            _clamp(value + alpha * step, lower, upper)
                            for value, step, (lower, upper) in zip(
                                values,
                                delta,
                                self._bounds,
                            )
                        )
                        if candidate == values:
                            continue
                        candidate_evaluation = self._evaluate_values(target, candidate)
                        improvement = evaluation.objective - candidate_evaluation.objective
                        if improvement > max(1e-12, evaluation.objective * 1e-12):
                            values = candidate
                            evaluation = candidate_evaluation
                            damping = max(self.options.minimum_damping, local_damping * 0.6)
                            accepted = True
                            break
                    if accepted:
                        break
                    local_damping *= 10.0

                if self._has_converged(evaluation.report):
                    termination = "TOLERANCES_SATISFIED"
                    break
                if not accepted:
                    termination = "STALLED_WITHIN_BOUNDS"
                    break

        converged = self._has_converged(evaluation.report)
        return (
            IkAttemptReport(
                seed_index=seed_index,
                seed_joint_positions=self._named_positions(seed),
                iterations=iterations,
                converged=converged,
                termination_reason=termination,
                residual=evaluation.report,
            ),
            values,
        )

    def _has_converged(self, residual: PoseResidual) -> bool:
        return (
            residual.position_error_mm <= self.options.position_tolerance_mm
            and residual.alignment_error_rad <= self.options.alignment_tolerance_rad
        )

    def _finite_difference_jacobian(
        self,
        target: BoardToolTipTarget,
        values: tuple[float, ...],
        centre: _Evaluation,
    ) -> tuple[tuple[float, ...], ...]:
        columns: list[tuple[float, ...]] = []
        nominal_step = self.options.finite_difference_step_rad
        for joint_index, (lower, upper) in enumerate(self._bounds):
            positive_room = upper - values[joint_index]
            negative_room = values[joint_index] - lower
            if positive_room >= nominal_step and negative_room >= nominal_step:
                plus = _replace(values, joint_index, values[joint_index] + nominal_step)
                minus = _replace(values, joint_index, values[joint_index] - nominal_step)
                plus_residual = self._evaluate_values(target, plus).residual_vector
                minus_residual = self._evaluate_values(target, minus).residual_vector
                denominator = 2.0 * nominal_step
                column = tuple(
                    (positive - negative) / denominator
                    for positive, negative in zip(plus_residual, minus_residual)
                )
            elif positive_room > 0.0:
                step = min(nominal_step, positive_room)
                plus = _replace(values, joint_index, values[joint_index] + step)
                plus_residual = self._evaluate_values(target, plus).residual_vector
                column = tuple(
                    (positive - current) / step
                    for positive, current in zip(plus_residual, centre.residual_vector)
                )
            elif negative_room > 0.0:
                step = min(nominal_step, negative_room)
                minus = _replace(values, joint_index, values[joint_index] - step)
                minus_residual = self._evaluate_values(target, minus).residual_vector
                column = tuple(
                    (current - negative) / step
                    for current, negative in zip(centre.residual_vector, minus_residual)
                )
            else:
                raise IkContractError(
                    f"Joint {ARM_JOINT_NAMES[joint_index]!r} has no numerical range"
                )
            columns.append(column)
        return tuple(tuple(column[row] for column in columns) for row in range(6))

    def _evaluate_values(
        self,
        target: BoardToolTipTarget,
        values: tuple[float, ...],
    ) -> _Evaluation:
        state = {
            name: JointPosition.radians(value)
            for name, value in zip(ARM_JOINT_NAMES, values)
        }
        state[GRIPPER_JOINT_NAME] = self.fixed_gripper_position
        root_T_hand = self.model.forward_kinematics(state)[HAND_TCP_LINK_NAME]
        board_T_hand = self.board_T_world.compose(root_T_hand)
        board_T_tip = board_T_hand.compose(self._hand_tcp_T_tip)

        current = board_T_tip.translation_mm
        target_position = target.position_mm
        position_error = Vec3(
            target_position.x - current.x,
            target_position.y - current.y,
            target_position.z - current.z,
        )
        hand_z_board = board_T_hand.rotation.apply(_BOARD_UP).normalized()
        alignment_vector = _direction_alignment_error(hand_z_board, _BOARD_UP)
        weighted_alignment = alignment_vector.scaled(
            self.options.orientation_weight_mm_per_rad
        )
        residual_vector = (
            position_error.x,
            position_error.y,
            position_error.z,
            weighted_alignment.x,
            weighted_alignment.y,
            weighted_alignment.z,
        )
        position_norm = position_error.norm
        alignment_angle = alignment_vector.norm
        return _Evaluation(
            residual_vector=residual_vector,
            report=PoseResidual(
                tip_position_board_mm=Point3Mm(
                    self.board_T_world.parent_frame,
                    current.x,
                    current.y,
                    current.z,
                ),
                hand_tcp_z_axis_board=hand_z_board,
                position_error_mm=position_norm,
                alignment_error_rad=alignment_angle,
                weighted_residual_norm_mm=math.sqrt(
                    sum(value * value for value in residual_vector)
                ),
            ),
        )

    @staticmethod
    def _named_positions(values: tuple[float, ...]) -> tuple[NamedJointPosition, ...]:
        return tuple(
            NamedJointPosition(name, JointPosition.radians(value))
            for name, value in zip(ARM_JOINT_NAMES, values)
        )


def _direction_alignment_error(current: Vec3, target: Vec3) -> Vec3:
    """Rotation vector that aligns one unit direction with another.

    This is the spherical logarithm.  Unlike a bare cross product it does not
    falsely report zero error for anti-parallel directions.
    """

    current_unit = current.normalized()
    target_unit = target.normalized()
    cross = current_unit.cross(target_unit)
    sine = cross.norm
    cosine = _clamp(current_unit.dot(target_unit), -1.0, 1.0)
    if sine > 1e-12:
        return cross.scaled(math.atan2(sine, cosine) / sine)
    if cosine >= 0.0:
        return Vec3.zero()

    # At exactly pi the shortest rotation axis is not unique.  Pick one
    # deterministically so the solver cannot misclassify anti-alignment as a
    # valid solution.
    reference = Vec3(1.0, 0.0, 0.0)
    if abs(current_unit.dot(reference)) > 0.9:
        reference = Vec3(0.0, 1.0, 0.0)
    axis = current_unit.cross(reference).normalized()
    return axis.scaled(math.pi)


def _symmetric_eigenvalues_jacobi(
    matrix: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], int]:
    """Return descending eigenvalues of one bounded small symmetric matrix."""

    size = len(matrix)
    if size != len(ARM_JOINT_NAMES) or any(len(row) != size for row in matrix):
        raise IkContractError("Task Jacobian Gram matrix must be exactly 5x5")
    work = [
        [finite_real(value, name="task Jacobian Gram entry") for value in row]
        for row in matrix
    ]
    for row in range(size):
        for column in range(row + 1, size):
            if not math.isclose(
                work[row][column],
                work[column][row],
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise IkContractError("Task Jacobian Gram matrix must be symmetric")
            symmetric = 0.5 * (work[row][column] + work[column][row])
            work[row][column] = symmetric
            work[column][row] = symmetric

    for sweep in range(_JACOBI_EIGEN_MAX_SWEEPS + 1):
        diagonal_scale = max(
            1.0,
            max(abs(work[index][index]) for index in range(size)),
        )
        largest_off_diagonal = max(
            abs(work[left][right])
            for left in range(size)
            for right in range(left + 1, size)
        )
        if (
            largest_off_diagonal
            <= _JACOBI_EIGEN_RELATIVE_TOLERANCE * diagonal_scale
        ):
            return (
                tuple(
                    sorted(
                        (work[index][index] for index in range(size)),
                        reverse=True,
                    )
                ),
                sweep,
            )
        if sweep == _JACOBI_EIGEN_MAX_SWEEPS:
            break

        for left in range(size - 1):
            for right in range(left + 1, size):
                off_diagonal = work[left][right]
                if (
                    abs(off_diagonal)
                    <= _JACOBI_EIGEN_RELATIVE_TOLERANCE * diagonal_scale
                ):
                    continue
                left_diagonal = work[left][left]
                right_diagonal = work[right][right]
                angle = 0.5 * math.atan2(
                    2.0 * off_diagonal,
                    right_diagonal - left_diagonal,
                )
                cosine = math.cos(angle)
                sine = math.sin(angle)
                for index in range(size):
                    if index in (left, right):
                        continue
                    old_left = work[index][left]
                    old_right = work[index][right]
                    new_left = cosine * old_left - sine * old_right
                    new_right = sine * old_left + cosine * old_right
                    work[index][left] = new_left
                    work[left][index] = new_left
                    work[index][right] = new_right
                    work[right][index] = new_right
                work[left][left] = (
                    cosine * cosine * left_diagonal
                    - 2.0 * sine * cosine * off_diagonal
                    + sine * sine * right_diagonal
                )
                work[right][right] = (
                    sine * sine * left_diagonal
                    + 2.0 * sine * cosine * off_diagonal
                    + cosine * cosine * right_diagonal
                )
                work[left][right] = 0.0
                work[right][left] = 0.0

    raise IkContractError(
        "Bounded task-Jacobian eigen solver did not converge"
    )


def _damped_least_squares_delta(
    jacobian: tuple[tuple[float, ...], ...],
    residual: tuple[float, ...],
    damping: float,
) -> tuple[float, ...]:
    columns = len(jacobian[0])
    normal = [
        [
            sum(row[left] * row[right] for row in jacobian)
            + (damping * damping if left == right else 0.0)
            for right in range(columns)
        ]
        for left in range(columns)
    ]
    right_hand_side = [
        -sum(row[column] * value for row, value in zip(jacobian, residual))
        for column in range(columns)
    ]
    return tuple(_solve_linear_system(normal, right_hand_side))


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a small dense system with deterministic partial pivoting."""

    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-18:
            raise IkContractError("Damped IK normal matrix is numerically singular")
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= pivot_value
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return [augmented[row][size] for row in range(size)]


def _replace(values: tuple[float, ...], index: int, value: float) -> tuple[float, ...]:
    result = list(values)
    result[index] = value
    return tuple(result)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _halton(index: int, base: int) -> float:
    result = 0.0
    factor = 1.0 / base
    remaining = index
    while remaining:
        result += factor * (remaining % base)
        remaining //= base
        factor /= base
    return result


def _residual_dict(residual: PoseResidual) -> dict[str, object]:
    return {
        "tip_position_board_mm": {
            "frame": residual.tip_position_board_mm.frame,
            "x": residual.tip_position_board_mm.x,
            "y": residual.tip_position_board_mm.y,
            "z": residual.tip_position_board_mm.z,
        },
        "hand_tcp_z_axis_board": [
            residual.hand_tcp_z_axis_board.x,
            residual.hand_tcp_z_axis_board.y,
            residual.hand_tcp_z_axis_board.z,
        ],
        "position_error_mm": residual.position_error_mm,
        "alignment_error_rad": residual.alignment_error_rad,
        "weighted_residual_norm_mm": residual.weighted_residual_norm_mm,
    }
