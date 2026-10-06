from __future__ import annotations

from dataclasses import replace
import hashlib
import math
from pathlib import Path

import pytest

from rocell.geometry import (
    JointPosition,
    Point3Mm,
    RigidTransform,
    Rotation3,
    UrdfModel,
    Vec3,
    parse_urdf,
)
from rocell.kinematics import (
    ARM_JOINT_NAMES,
    GRIPPER_JOINT_NAME,
    MAX_TASK_JACOBIAN_FK_EVALUATIONS,
    BoardToolTipTarget,
    IkContractError,
    IkOptions,
    IkStatus,
    RoArmM3NumericalIk,
)


PINNED_URDF = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "roarm_m3"
    / "roarm_m3_kinematic_40dbd84.urdf"
)
TOOL_OFFSET_MM = -100.0
GRIPPER_POSITION = JointPosition.radians(0.2)
REACHABLE_ARM_STATE_RAD = (0.4, 0.5, 1.0, 0.0707963267948966, 0.0)


def _model() -> UrdfModel:
    return UrdfModel.from_file(PINNED_URDF)


def _board_T_world() -> RigidTransform:
    # The nominal RC03 orientation and translation, retained here as an
    # explicit transform rather than an implicit identity-frame assumption.
    return RigidTransform(
        parent_frame="board",
        child_frame="world",
        rotation=Rotation3((0, 1, 0, -1, 0, 0, 0, 0, 1)),
        translation_mm=Vec3(305, 457, 0),
    )


def _solver(*, options: IkOptions | None = None) -> RoArmM3NumericalIk:
    return RoArmM3NumericalIk(
        model=_model(),
        board_T_world=_board_T_world(),
        hand_tcp_to_tip_z_mm=TOOL_OFFSET_MM,
        fixed_gripper_position=GRIPPER_POSITION,
        options=options or IkOptions(max_attempts=6, max_iterations_per_attempt=100),
    )


@pytest.mark.parametrize(
    ("arm_positions", "expected_translation_mm"),
    [
        ((0.0, 0.0, 0.0, 0.0, 0.0), (45.147706, -0.000166, 672.541110)),
        ((0.0, 0.0, math.pi / 2.0, 0.0, 0.0), (343.668130, -0.001262, 343.727534)),
        ((0.0, 0.0, 2.618, -1.0472, 0.0), (271.374308, -0.000997, 218.511322)),
    ],
)
def test_pinned_vendor_model_hash_and_golden_fk(
    arm_positions: tuple[float, ...],
    expected_translation_mm: tuple[float, float, float],
) -> None:
    assert hashlib.sha256(PINNED_URDF.read_bytes()).hexdigest() == (
        "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
    )
    state = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, arm_positions)
    }
    state[GRIPPER_JOINT_NAME] = JointPosition.radians(0.0)
    translation = _model().forward_kinematics(state)["hand_tcp"].translation_mm

    assert (translation.x, translation.y, translation.z) == pytest.approx(
        expected_translation_mm,
        abs=0.002,
    )


def _reachable_target(model: UrdfModel) -> BoardToolTipTarget:
    state = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }
    state[GRIPPER_JOINT_NAME] = GRIPPER_POSITION
    world_T_hand = model.forward_kinematics(state)["hand_tcp"]
    hand_T_tip = RigidTransform(
        parent_frame="hand_tcp",
        child_frame="tool_tip",
        rotation=Rotation3.identity(),
        translation_mm=Vec3(0, 0, TOOL_OFFSET_MM),
    )
    board_T_tip = _board_T_world().compose(world_T_hand).compose(hand_T_tip)
    hand_z_board = _board_T_world().rotation.compose(world_T_hand.rotation).apply(Vec3(0, 0, 1))
    assert math.acos(max(-1.0, min(1.0, hand_z_board.z))) < 1e-4
    return BoardToolTipTarget(
        Point3Mm(
            "board",
            board_T_tip.translation_mm.x,
            board_T_tip.translation_mm.y,
            board_T_tip.translation_mm.z,
        )
    )


def test_pinned_m3_reachable_target_converges_with_exact_limits_and_labels() -> None:
    model = _model()
    solver = _solver()
    result = solver.solve(_reachable_target(model))

    assert result.status is IkStatus.CONVERGED
    assert result.converged is True
    assert result.simulation_only is True
    assert result.live_motion_authorized is False
    assert result.hardware_commands_generated == 0
    assert result.residual.position_error_mm <= solver.options.position_tolerance_mm
    assert result.residual.alignment_error_rad <= solver.options.alignment_tolerance_rad
    assert len(result.attempts) == solver.options.max_attempts
    assert len(result.solution_arm_joint_positions) == 5
    assert result.fixed_gripper_position.name == GRIPPER_JOINT_NAME
    assert result.fixed_gripper_position.position == GRIPPER_POSITION

    for solved in result.solution_arm_joint_positions:
        limit = model.joint(solved.name).limit
        assert limit is not None and limit.lower is not None and limit.upper is not None
        assert limit.lower.value <= solved.position.value <= limit.upper.value

    record = result.to_dict()
    assert record["schema"] == "rocell.simulation.ik.v1"
    assert record["hardware_commands_generated"] == 0
    assert "solution_arm_joint_positions_rad" in record
    assert "command" not in record


def test_unreachable_target_fails_closed_without_exposing_joint_solution() -> None:
    solver = _solver(options=IkOptions(max_attempts=4, max_iterations_per_attempt=45))
    target = BoardToolTipTarget(Point3Mm("board", 5000, -5000, 5000))

    result = solver.solve(target)

    assert result.status is IkStatus.NO_CONVERGED_SOLUTION
    assert result.converged is False
    assert result.solution_arm_joint_positions == ()
    assert result.residual.position_error_mm > 1000
    assert result.simulation_only is True
    assert result.live_motion_authorized is False
    assert all(not attempt.converged for attempt in result.attempts)


def test_solver_is_repeatable_for_same_model_transform_target_and_seeds() -> None:
    model = _model()
    solver = _solver(options=IkOptions(max_attempts=5, max_iterations_per_attempt=80))
    target = _reachable_target(model)

    first = solver.solve(target)
    second = solver.solve(target)

    assert first.to_dict() == second.to_dict()


def test_evaluate_and_seed_inputs_require_complete_typed_radian_arm_state() -> None:
    solver = _solver()
    target = _reachable_target(solver.model)
    typed_seed = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }
    residual = solver.evaluate(target, typed_seed)
    assert residual.position_error_mm < 1e-9
    assert residual.alignment_error_rad < 1e-4

    raw_seed = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }
    raw_seed[ARM_JOINT_NAMES[0]] = 0.4  # type: ignore[assignment]

    with pytest.raises(IkContractError, match="must be a JointPosition"):
        solver.evaluate(target, raw_seed)  # type: ignore[arg-type]

    incomplete = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES[:-1], REACHABLE_ARM_STATE_RAD[:-1])
    }
    with pytest.raises(IkContractError, match="joint mismatch"):
        solver.solve(target, seed_joint_positions=(incomplete,))


def test_weighted_task_jacobian_is_bounded_repeatable_and_non_authoritative() -> None:
    solver = _solver()
    target = _reachable_target(solver.model)
    state = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }

    first = solver.diagnose_weighted_task_jacobian(target, state)
    second = solver.diagnose_weighted_task_jacobian(target, state)

    assert first == second
    assert first.full_column_rank is True
    assert first.numerical_rank == 5
    assert first.singular_values_solver_weighted_mm_per_rad == pytest.approx(
        (591.380387, 464.400530, 182.476945, 78.065112, 19.621977),
        rel=2e-6,
    )
    assert first.normalized_minimum_singular_value == pytest.approx(
        0.0331799582,
        rel=2e-6,
    )
    assert first.condition_number == pytest.approx(30.1386757, rel=2e-6)
    assert first.finite_difference_fk_evaluations == (
        MAX_TASK_JACOBIAN_FK_EVALUATIONS
    )
    document = first.to_dict()
    assert document["metric_scope"] == (
        "LOCAL_SOLVER_WEIGHTED_FIVE_CONSTRAINT_TASK_ONLY"
    )
    assert document["physical_singularity_acceptance"] is False
    assert document["collision_evaluated"] is False
    assert document["live_motion_authorized"] is False
    assert document["hardware_commands_generated"] == 0
    assert document["rank_relative_tolerance"] == 1e-7
    assert document["rank_cutoff_interpretation"] == (
        "CONSERVATIVE_NUMERICAL_FLOOR_AFTER_GRAM_EIGENDECOMPOSITION"
    )


def test_weighted_task_jacobian_detects_exact_local_rank_loss() -> None:
    solver = _solver()
    target = _reachable_target(solver.model)
    values = (0.0, 0.0, 0.0, 0.0, -math.pi / 2.0)
    state = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, values)
    }

    report = solver.diagnose_weighted_task_jacobian(target, state)

    assert report.full_column_rank is False
    assert report.numerical_rank == 4
    assert report.normalized_minimum_singular_value == 0.0
    assert report.condition_number is None
    assert report.singular_values_solver_weighted_mm_per_rad[-1] == 0.0

    with pytest.raises(IkContractError, match="numerical rank disagrees"):
        replace(report, numerical_rank=5)
    with pytest.raises(IkContractError, match="singular value is inconsistent"):
        replace(report, normalized_minimum_singular_value=0.1)


def test_weighted_task_jacobian_conservatively_rejects_gram_roundoff_false_rank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact rank-four factorization must not acquire a fifth task DOF.

    Under the former 1e-8 cutoff, the bounded J.T*J eigensolver retained a
    roundoff singular-value ratio of about 1.28e-8 for this deterministic
    integer matrix and incorrectly reported full column rank.
    """

    left = (
        (0, 3, 4, -5),
        (-1, -3, -2, -1),
        (-4, -2, 3, -5),
        (4, -2, 3, -5),
        (3, 0, 2, -3),
        (0, 5, -3, -5),
    )
    right = (
        (0, 4, -5, 1, 5),
        (4, -2, -3, 0, 1),
        (2, -4, 5, -5, -2),
        (4, -3, -3, -2, 3),
    )
    exact_rank_at_most_four = tuple(
        tuple(
            sum(left[row][inner] * right[inner][column] for inner in range(4))
            for column in range(5)
        )
        for row in range(6)
    )
    monkeypatch.setattr(
        RoArmM3NumericalIk,
        "_finite_difference_jacobian",
        lambda self, target, values, centre: exact_rank_at_most_four,
    )
    solver = _solver()
    target = _reachable_target(solver.model)
    state = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }

    report = solver.diagnose_weighted_task_jacobian(target, state)

    assert report.numerical_rank == 4
    assert report.full_column_rank is False
    assert report.singular_values_solver_weighted_mm_per_rad[-1] == 0.0
    assert report.condition_number is None


def test_weighted_task_jacobian_rank_floor_boundary_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    solver = _solver()
    target = _reachable_target(solver.model)
    state = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }

    def diagonal_jacobian(minimum_ratio: float) -> tuple[tuple[float, ...], ...]:
        diagonal = (1.0, 1.0, 1.0, 1.0, minimum_ratio)
        return tuple(
            tuple(
                diagonal[row] if row == column else 0.0
                for column in range(5)
            )
            for row in range(6)
        )

    monkeypatch.setattr(
        RoArmM3NumericalIk,
        "_finite_difference_jacobian",
        lambda self, target, values, centre: diagonal_jacobian(1e-7),
    )
    at_floor = solver.diagnose_weighted_task_jacobian(target, state)
    assert at_floor.numerical_rank == 4
    assert at_floor.full_column_rank is False

    monkeypatch.setattr(
        RoArmM3NumericalIk,
        "_finite_difference_jacobian",
        lambda self, target, values, centre: diagonal_jacobian(1.001e-7),
    )
    above_floor = solver.diagnose_weighted_task_jacobian(target, state)
    assert above_floor.numerical_rank == 5
    assert above_floor.full_column_rank is True
    assert above_floor.condition_number is not None


def test_weighted_task_jacobian_rejects_forged_condition_number() -> None:
    solver = _solver()
    target = _reachable_target(solver.model)
    state = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }
    report = solver.diagnose_weighted_task_jacobian(target, state)

    with pytest.raises(IkContractError, match="condition number is inconsistent"):
        replace(report, condition_number=report.condition_number + 1.0)  # type: ignore[operator]


def test_model_frame_tool_direction_and_gripper_contracts_fail_closed() -> None:
    model = _model()
    with pytest.raises(IkContractError, match="child frame"):
        RoArmM3NumericalIk(
            model=model,
            board_T_world=RigidTransform(
                "board",
                "not_world",
                Rotation3.identity(),
                Vec3.zero(),
            ),
            hand_tcp_to_tip_z_mm=-100,
            fixed_gripper_position=GRIPPER_POSITION,
        )
    with pytest.raises(IkContractError, match="zero or negative"):
        RoArmM3NumericalIk(
            model=model,
            board_T_world=_board_T_world(),
            hand_tcp_to_tip_z_mm=100,
            fixed_gripper_position=GRIPPER_POSITION,
        )
    with pytest.raises(IkContractError, match="Invalid fixed gripper"):
        RoArmM3NumericalIk(
            model=model,
            board_T_world=_board_T_world(),
            hand_tcp_to_tip_z_mm=-100,
            fixed_gripper_position=JointPosition.radians(2.0),
        )

    wrong_model = parse_urdf('<robot name="not_m3"><link name="world"/></robot>')
    with pytest.raises(IkContractError, match="Expected URDF robot"):
        RoArmM3NumericalIk(
            model=wrong_model,
            board_T_world=_board_T_world(),
            hand_tcp_to_tip_z_mm=-100,
            fixed_gripper_position=GRIPPER_POSITION,
        )


def test_target_frame_mismatch_is_rejected_before_numerical_work() -> None:
    solver = _solver()
    wrong_frame = BoardToolTipTarget(Point3Mm("camera", 0, 0, 0))
    with pytest.raises(IkContractError, match="expected board frame"):
        solver.solve(wrong_frame)


def test_solver_enforces_caller_joint_bounds_inside_urdf() -> None:
    model = _model()
    bounds = {
        name: (
            model.joint(name).limit.lower.value,  # type: ignore[union-attr]
            model.joint(name).limit.upper.value,  # type: ignore[union-attr]
        )
        for name in ARM_JOINT_NAMES
    }
    bounds[ARM_JOINT_NAMES[0]] = (0.0, 0.2)
    solver = RoArmM3NumericalIk(
        model=model,
        board_T_world=_board_T_world(),
        hand_tcp_to_tip_z_mm=TOOL_OFFSET_MM,
        fixed_gripper_position=GRIPPER_POSITION,
        joint_bounds_rad=bounds,
    )
    seed = {
        name: JointPosition.radians(value)
        for name, value in zip(ARM_JOINT_NAMES, REACHABLE_ARM_STATE_RAD)
    }
    with pytest.raises(IkContractError, match="outside"):
        solver.solve(_reachable_target(model), seed_joint_positions=(seed,))

    bounds[ARM_JOINT_NAMES[0]] = (-4.0, 0.2)
    with pytest.raises(IkContractError, match="inside URDF"):
        RoArmM3NumericalIk(
            model=model,
            board_T_world=_board_T_world(),
            hand_tcp_to_tip_z_mm=TOOL_OFFSET_MM,
            fixed_gripper_position=GRIPPER_POSITION,
            joint_bounds_rad=bounds,
        )

    with pytest.raises(IkContractError, match="subset of the URDF gripper range"):
        RoArmM3NumericalIk(
            model=model,
            board_T_world=_board_T_world(),
            hand_tcp_to_tip_z_mm=TOOL_OFFSET_MM,
            fixed_gripper_position=GRIPPER_POSITION,
            gripper_bounds_rad=(-1.0, 1.5),
        )
