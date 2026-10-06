"""Bounded CPU-only margin-aware first-H planner study."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from rocell.application.trajectory_simulation import (
    CartesianRouteWaypoint,
    TrajectorySimulationPolicy,
    evaluate_joint_trajectory_solution,
)
from rocell.application.typing_trajectory_plan_v1 import (
    TypingPhaseWaypointV1,
    TypingTrajectoryMetricsV1,
    TypingTrajectoryPlanV1,
    _evidence_float,
    _park_baseline_points,
    _screening_samples,
    _time_for_points,
    _timings_for_endpoints,
)
from rocell.geometry import JointPosition
from rocell.kinematics import ARM_JOINT_NAMES, BoardToolTipTarget
from rocell.models import Point3Mm
from rocell.motion.primitives import MotionPhase

from .typing_twin_ik_branch_selection_study_v1 import _solve_candidates
from .typing_twin_ik_cartesian_corridor_study_v1 import _screen_corridor_candidate
from .typing_twin_ik_collision_v1 import SCOPE, _load_fixture as _load_parent_fixture
from .typing_twin_ik_route_study_v1 import (
    _build_pipeline,
    _screen_candidate,
    _solver_for_seed,
)


SCHEMA = "tactevra.typing_twin_ik_margin_aware_planner_study_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_ik_margin_aware_planner_study_fixture.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("margin-aware planner fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected margin-aware planner fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _halton(index: int, base: int) -> float:
    if index < 1 or base < 2:
        raise ValueError("Halton index and base are out of range")
    factor = 1.0
    value = 0.0
    current = index
    while current:
        factor /= base
        value += factor * (current % base)
        current //= base
    return value


def _sample_point(
    index: int,
    bounds: Mapping[str, tuple[float, float]],
    bases: tuple[int, int, int],
) -> Point3Mm:
    coordinates = []
    for axis, base in zip(("x", "y", "z"), bases, strict=True):
        lower, upper = bounds[axis]
        coordinates.append(lower + _halton(index, base) * (upper - lower))
    return Point3Mm("board", *coordinates)


def _distance(left: Point3Mm, right: Point3Mm) -> float:
    return math.dist((left.x, left.y, left.z), (right.x, right.y, right.z))


def _steer(start: Point3Mm, target: Point3Mm, maximum_step_mm: float) -> Point3Mm:
    distance = _distance(start, target)
    if distance <= maximum_step_mm:
        return target
    ratio = maximum_step_mm / distance
    return Point3Mm(
        "board",
        start.x + ratio * (target.x - start.x),
        start.y + ratio * (target.y - start.y),
        start.z + ratio * (target.z - start.z),
    )


@dataclass(frozen=True, slots=True)
class _Node:
    point: Point3Mm
    solution: Mapping[str, float]
    parent: int | None
    minimum_margin: float
    maximum_delta: float


def _route_bounds(
    start: Point3Mm,
    goal: Point3Mm,
    *,
    xy_padding_mm: float,
    lower_z_padding_mm: float,
    upper_z_padding_mm: float,
) -> dict[str, tuple[float, float]]:
    return {
        "x": (min(start.x, goal.x) - xy_padding_mm, max(start.x, goal.x) + xy_padding_mm),
        "y": (min(start.y, goal.y) - xy_padding_mm, max(start.y, goal.y) + xy_padding_mm),
        "z": (
            max(0.0, min(start.z, goal.z) - lower_z_padding_mm),
            max(start.z, goal.z) + upper_z_padding_mm,
        ),
    }


def _candidate_trajectory(
    baseline: TypingTrajectoryPlanV1,
    execution: Any,
    points: tuple[Point3Mm, ...],
) -> TypingTrajectoryPlanV1:
    if points[0] != baseline.phase_waypoints[0].point:
        raise ValueError("planned route must start at the exact ready point")
    if points[-1] != baseline.phase_waypoints[1].point:
        raise ValueError("planned route must end at the exact first-H hover")
    endpoints = [TypingPhaseWaypointV1(0, MotionPhase.PARK, None, None, points[0])]
    for point in points[1:-1]:
        endpoints.append(
            TypingPhaseWaypointV1(len(endpoints), MotionPhase.TRANSIT, 0, "H", point)
        )
    for original in baseline.phase_waypoints[1:]:
        endpoints.append(
            TypingPhaseWaypointV1(
                len(endpoints),
                original.phase,
                original.action_index,
                original.target_id,
                original.point,
            )
        )
    endpoint_tuple = tuple(endpoints)
    policy = baseline.policy
    timings = _timings_for_endpoints(endpoint_tuple, policy)
    samples = _screening_samples(endpoint_tuple, policy.maximum_cartesian_step_mm)
    motion_ms = sum(item.duration_ms for item in timings)
    dwell_ms = sum(item.dwell_after_ms for item in timings)
    direct_ms = motion_ms + dwell_ms
    park_ms = _time_for_points(_park_baseline_points(execution), policy)
    saved = max(0.0, park_ms - direct_ms)
    metrics = TypingTrajectoryMetricsV1(
        direct_distance_mm=_evidence_float(sum(item.distance_mm for item in timings)),
        park_baseline_distance_mm=_evidence_float(execution.metrics.park_total_distance_mm),
        direct_motion_time_ms=_evidence_float(motion_ms),
        direct_dwell_time_ms=dwell_ms,
        direct_estimated_time_ms=_evidence_float(direct_ms),
        park_baseline_estimated_time_ms=_evidence_float(park_ms),
        estimated_time_saved_ms=_evidence_float(saved),
        estimated_time_reduction_fraction=_evidence_float(
            saved / park_ms if park_ms else 0.0
        ),
    )
    return TypingTrajectoryPlanV1(
        source_plan_sha256=execution.plan_sha256,
        policy=policy,
        phase_waypoints=endpoint_tuple,
        screening_samples=samples,
        timing_segments=timings,
        metrics=metrics,
    )


def _plan_first_hover(
    *,
    start: Point3Mm,
    goal: Point3Mm,
    ready_solution: Mapping[str, float],
    solver: Any,
    controller_bounds: Mapping[str, tuple[float, float]],
    policy: TrajectorySimulationPolicy,
    search: Mapping[str, Any],
    goal_bias_period: int,
) -> tuple[tuple[Point3Mm, ...] | None, dict[str, Any]]:
    route_bounds = _route_bounds(
        start,
        goal,
        xy_padding_mm=search["xy_padding_mm"],
        lower_z_padding_mm=search["lower_z_padding_mm"],
        upper_z_padding_mm=search["upper_z_padding_mm"],
    )
    root_margin = min(
        min(ready_solution[name] - controller_bounds[name][0], controller_bounds[name][1] - ready_solution[name])
        / (controller_bounds[name][1] - controller_bounds[name][0])
        for name in ARM_JOINT_NAMES
    )
    nodes = [_Node(start, dict(ready_solution), None, root_margin, 0.0)]
    rejected: dict[str, int] = {}
    solver_calls = 0
    candidate_evaluations = 0
    goal_index: int | None = None
    maximum_iterations = int(search["maximum_iterations"])
    maximum_nodes = int(search["maximum_nodes"])
    step = float(search["extension_step_mm"])
    bases = tuple(search["halton_bases"])
    for iteration in range(1, maximum_iterations + 1):
        sample = goal if iteration % goal_bias_period == 0 else _sample_point(iteration, route_bounds, bases)
        nearest_index = min(
            range(len(nodes)),
            key=lambda item: (_distance(nodes[item].point, sample), item),
        )
        parent = nodes[nearest_index]
        proposed = _steer(parent.point, sample, step)
        if any(_distance(node.point, proposed) < 1e-6 for node in nodes):
            continue
        waypoint = CartesianRouteWaypoint(
            sequence=iteration,
            phase=MotionPhase.TRANSIT,
            action_index=0,
            semantic_target="H",
            point_board=proposed,
            distance_from_previous_mm=_distance(parent.point, proposed),
            source_geometric_sequence=iteration,
            source_check_id="MARGIN_AWARE_EXPLORATORY_NODE",
            source_path_check_passed=True,
            inherited_collision_ids=(),
            phase_endpoint=proposed == goal,
        )
        seeds = ({name: JointPosition.radians(parent.solution[name]) for name in ARM_JOINT_NAMES},)
        solved_candidates = _solve_candidates(solver, BoardToolTipTarget(proposed), seeds)
        solver_calls += 1
        accepted = []
        for solved in solved_candidates:
            candidate_evaluations += 1
            result = evaluate_joint_trajectory_solution(
                waypoint,
                solved,
                solver,
                controller_bounds,
                parent.solution,
                policy,
            )
            if result.accepted:
                accepted.append((result, solved.residual.weighted_residual_norm_mm))
            else:
                reason = result.failure_reason or "UNKNOWN_REJECTION"
                rejected[reason] = rejected.get(reason, 0) + 1
        if not accepted:
            continue
        selected, _ = min(
            accepted,
            key=lambda item: (
                -float(item[0].minimum_normalized_arm_joint_margin),
                float(item[0].maximum_joint_delta_rad or 0.0),
                item[1],
                tuple(round(dict(item[0].solution_arm_joint_positions_rad)[name], 12) for name in ARM_JOINT_NAMES),
            ),
        )
        solution = dict(selected.solution_arm_joint_positions_rad)
        margin = float(selected.minimum_normalized_arm_joint_margin)
        node = _Node(
            proposed,
            solution,
            nearest_index,
            min(parent.minimum_margin, margin),
            max(parent.maximum_delta, float(selected.maximum_joint_delta_rad or 0.0)),
        )
        nodes.append(node)
        if proposed == goal:
            goal_index = len(nodes) - 1
            break
        if len(nodes) >= maximum_nodes:
            break
    points = None
    if goal_index is not None:
        reversed_points = []
        cursor: int | None = goal_index
        while cursor is not None:
            reversed_points.append(nodes[cursor].point)
            cursor = nodes[cursor].parent
        points = tuple(reversed(reversed_points))
    diagnostics = {
        "goal_bias_period": goal_bias_period,
        "iterations_evaluated": iteration,
        "accepted_node_count": len(nodes),
        "solver_call_count": solver_calls,
        "candidate_evaluation_count": candidate_evaluations,
        "rejected_by_reason": dict(sorted(rejected.items())),
        "route_found": points is not None,
        "route_point_count": 0 if points is None else len(points),
        "tree_minimum_normalized_margin": (
            None if goal_index is None else nodes[goal_index].minimum_margin
        ),
        "tree_maximum_joint_delta_rad": (
            None if goal_index is None else nodes[goal_index].maximum_delta
        ),
    }
    return points, diagnostics


def run_margin_aware_planner_study(
    fixture_path: Path,
    *,
    workspace: Path,
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    parent_path = workspace / fixture["parent_fixture"]["path"]
    parent = _load_parent_fixture(parent_path, workspace)
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent fixture canonical identity changed")
    (
        context,
        snapshot,
        _ready_tip,
        targets,
        batch,
        ingress,
        fresh,
        execution,
        baseline_trajectory,
    ) = _build_pipeline(parent, workspace)
    ready_values = {
        name: context.scenario.ready_arm_joint_positions_rad[name].value
        for name in ARM_JOINT_NAMES
    }
    baseline, _ = _screen_candidate(
        "baseline-synthetic-ready",
        ready_values,
        context=context,
        snapshot=snapshot,
        execution=execution,
        trajectory=baseline_trajectory,
        maximum_samples=fixture["resource_limits"]["maximum_full_route_samples"],
    )
    expected = fixture["baseline_control"]
    if baseline["evaluated_sample_count"] != expected["evaluated_sample_count"] or baseline["failure_reason"] != expected["failure_reason"]:
        raise ValueError("baseline control no longer reproduces the frozen failure")
    solver = _solver_for_seed(context, snapshot, ready_values)
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=fixture["search"]["extension_step_mm"],
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=fixture["resource_limits"]["maximum_full_route_samples"],
        maximum_total_ik_solves=fixture["resource_limits"]["maximum_full_route_samples"],
        maximum_route_targets=len(execution.actions),
    )
    start = baseline_trajectory.phase_waypoints[0].point
    goal = baseline_trajectory.phase_waypoints[1].point
    summaries = []
    passing_reports = {}
    for period in fixture["search"]["goal_bias_periods"]:
        candidate_id = f"margin-aware-goal-bias-{period:03d}"
        points, planner = _plan_first_hover(
            start=start,
            goal=goal,
            ready_solution=ready_values,
            solver=solver,
            controller_bounds=context.scenario.controller_joint_intersection_rad,
            policy=policy,
            search=fixture["search"],
            goal_bias_period=period,
        )
        summary: dict[str, Any] = {"candidate_id": candidate_id, "planner": planner}
        if points is None:
            summary.update({"status": "BLOCKED_NO_MARGIN_AWARE_PREFIX", "full_route_accepted": False})
        else:
            trajectory = _candidate_trajectory(baseline_trajectory, execution, points)
            screen_summary, report = _screen_corridor_candidate(
                candidate_id,
                ready_values,
                context=context,
                snapshot=snapshot,
                trajectory=trajectory,
                maximum_samples=fixture["resource_limits"]["maximum_full_route_samples"],
            )
            summary.update(screen_summary)
            summary["full_route_accepted"] = report["ik_all_samples_accepted"]
            summary["trajectory_sample_count"] = len(trajectory.screening_samples)
            summary["trajectory_plan_sha256"] = trajectory.trajectory_plan_sha256
            if report["ik_all_samples_accepted"]:
                passing_reports[candidate_id] = report
        summary["candidate_summary_sha256"] = _sha(
            {key: value for key, value in summary.items() if key != "candidate_summary_sha256"}
        )
        summaries.append(summary)
    passing = [item for item in summaries if item["candidate_id"] in passing_reports]
    selected = None if not passing else min(
        passing,
        key=lambda item: (
            -item["minimum_normalized_arm_joint_margin"],
            item["maximum_joint_delta_rad"],
            item["trajectory_sample_count"],
            item["candidate_id"],
        ),
    )
    decision = "PASS_MARGIN_AWARE_FULL_ROUTE_FOUND" if selected else "BLOCKED_NO_MARGIN_AWARE_FULL_ROUTE"
    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "parent_fixture_sha256": parent["fixture_sha256"],
        "ordered_targets": list(targets),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": fresh["preplanner_gate_sha256"],
        "baseline_control": baseline,
        "candidate_summaries": summaries,
        "passing_candidate_count": len(passing),
        "selected_candidate": selected,
        "selected_full_ik_screen": None if selected is None else passing_reports[selected["candidate_id"]],
        "planner_installed": False,
        "collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "decision": decision,
        "limitations": fixture["limitations"],
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_margin_aware_planner_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": result["decision"], "passing_candidate_count": result["passing_candidate_count"], "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
