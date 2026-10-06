"""CPU-only first-H endpoint and nearby solution-manifold diagnostic."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Mapping

from rocell.application.trajectory_simulation import (
    CartesianRouteWaypoint,
    TrajectorySimulationPolicy,
    evaluate_joint_trajectory_solution,
)
from rocell.geometry import JointPosition
from rocell.kinematics import ARM_JOINT_NAMES, BoardToolTipTarget
from rocell.models import Point3Mm
from rocell.motion.primitives import MotionPhase

from .typing_twin_ik_branch_selection_study_v1 import _solve_candidates
from .typing_twin_ik_collision_v1 import SCOPE, _load_fixture as _load_parent_fixture
from .typing_twin_ik_route_study_v1 import (
    _build_pipeline,
    _screen_candidate,
    _solver_for_seed,
)


SCHEMA = "tactevra.typing_twin_ik_endpoint_manifold_study_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_ik_endpoint_manifold_study_fixture.v1"


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
        raise ValueError("endpoint-manifold fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected endpoint-manifold fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _offsets(axis_offsets_mm: list[float]) -> tuple[tuple[float, float, float], ...]:
    return tuple(itertools.product(axis_offsets_mm, repeat=3))


def _normalized_margins(
    solution: Mapping[str, float],
    bounds: Mapping[str, tuple[float, float]],
) -> dict[str, float]:
    return {
        name: min(
            solution[name] - bounds[name][0],
            bounds[name][1] - solution[name],
        )
        / (bounds[name][1] - bounds[name][0])
        for name in ARM_JOINT_NAMES
    }


def _limiting_joints(margins: Mapping[str, float]) -> tuple[str, ...]:
    minimum = min(margins.values())
    return tuple(
        name for name in ARM_JOINT_NAMES if abs(margins[name] - minimum) <= 1e-12
    )


def _point_summary(
    *,
    goal: Point3Mm,
    offset: tuple[float, float, float],
    solver: Any,
    ready_values: Mapping[str, float],
    bounds: Mapping[str, tuple[float, float]],
    policy: TrajectorySimulationPolicy,
) -> dict[str, Any]:
    point = Point3Mm(
        "board",
        goal.x + offset[0],
        goal.y + offset[1],
        goal.z + offset[2],
    )
    waypoint = CartesianRouteWaypoint(
        sequence=0,
        phase=MotionPhase.HOVER,
        action_index=0,
        semantic_target="H",
        point_board=point,
        distance_from_previous_mm=0.0,
        source_geometric_sequence=1,
        source_check_id="ENDPOINT_MANIFOLD_DIAGNOSTIC",
        source_path_check_passed=True,
        inherited_collision_ids=(),
        phase_endpoint=True,
    )
    seeds = (
        {
            name: JointPosition.radians(ready_values[name])
            for name in ARM_JOINT_NAMES
        },
    )
    candidates = _solve_candidates(solver, BoardToolTipTarget(point), seeds)
    rows = []
    for solved in candidates:
        result = evaluate_joint_trajectory_solution(
            waypoint,
            solved,
            solver,
            bounds,
            None,
            policy,
        )
        solution = dict(result.solution_arm_joint_positions_rad)
        margins = _normalized_margins(solution, bounds)
        rows.append(
            {
                "accepted": result.accepted,
                "failure_reason": result.failure_reason,
                "selected_attempt_index": result.selected_attempt_index,
                "position_error_mm": result.position_error_mm,
                "minimum_normalized_arm_joint_margin": min(margins.values()),
                "limiting_joints": list(_limiting_joints(margins)),
                "normalized_margin_by_joint": margins,
                "solver_weighted_task_jacobian_numerical_rank_passed": (
                    result.solver_weighted_task_jacobian_numerical_rank_passed
                ),
            }
        )
    accepted = [row for row in rows if row["accepted"]]
    best = None if not rows else max(
        rows,
        key=lambda row: (
            row["minimum_normalized_arm_joint_margin"],
            -row["position_error_mm"],
            -row["selected_attempt_index"],
        ),
    )
    return {
        "offset_mm": list(offset),
        "point_board_mm": [point.x, point.y, point.z],
        "distance_to_exact_hover_mm": math.dist(offset, (0.0, 0.0, 0.0)),
        "converged_candidate_count": len(rows),
        "accepted_candidate_count": len(accepted),
        "point_accepted": bool(accepted),
        "best_candidate": best,
        "candidate_summaries": rows,
    }


def run_endpoint_manifold_study(
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
        trajectory,
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
        trajectory=trajectory,
        maximum_samples=fixture["resource_limits"]["maximum_route_samples"],
    )
    expected = fixture["baseline_control"]
    if baseline["evaluated_sample_count"] != expected["evaluated_sample_count"] or baseline["failure_reason"] != expected["failure_reason"]:
        raise ValueError("baseline control no longer reproduces the frozen failure")
    axis_offsets = fixture["search"]["axis_offsets_mm"]
    offsets = _offsets(axis_offsets)
    if len(offsets) != fixture["decision_rules"]["point_count_exact"]:
        raise ValueError("endpoint-manifold point count differs from fixture")
    solver = _solver_for_seed(context, snapshot, ready_values)
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=trajectory.policy.maximum_cartesian_step_mm,
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=fixture["resource_limits"]["maximum_route_samples"],
        maximum_total_ik_solves=fixture["resource_limits"]["maximum_route_samples"],
        maximum_route_targets=len(execution.actions),
    )
    exact_goal = trajectory.phase_waypoints[1].point
    summaries = [
        _point_summary(
            goal=exact_goal,
            offset=offset,
            solver=solver,
            ready_values=ready_values,
            bounds=context.scenario.controller_joint_intersection_rad,
            policy=policy,
        )
        for offset in offsets
    ]
    exact = next(item for item in summaries if item["offset_mm"] == [0.0, 0.0, 0.0])
    accepted = [item for item in summaries if item["point_accepted"]]
    closest = None if not accepted else min(
        accepted,
        key=lambda item: (
            item["distance_to_exact_hover_mm"],
            -item["best_candidate"]["minimum_normalized_arm_joint_margin"],
            item["offset_mm"],
        ),
    )
    limiting = Counter()
    failure_reasons = Counter()
    for point in summaries:
        for candidate in point["candidate_summaries"]:
            if candidate["accepted"]:
                continue
            failure_reasons[candidate["failure_reason"] or "UNKNOWN_REJECTION"] += 1
            if candidate["failure_reason"] == "MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED":
                limiting.update(candidate["limiting_joints"])
    exact_feasible = exact["point_accepted"]
    decision = (
        "PASS_EXACT_HOVER_HAS_MARGIN_ADMISSIBLE_IK"
        if exact_feasible
        else "BLOCKED_EXACT_HOVER_HAS_NO_MARGIN_ADMISSIBLE_IK"
    )
    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "parent_fixture_sha256": parent["fixture_sha256"],
        "ordered_targets": list(targets),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": fresh["preplanner_gate_sha256"],
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "baseline_control": baseline,
        "exact_hover": exact,
        "exact_hover_margin_admissible": exact_feasible,
        "closest_margin_admissible_point": closest,
        "sampled_point_count": len(summaries),
        "margin_admissible_point_count": len(accepted),
        "limiting_joint_rejection_counts": dict(sorted(limiting.items())),
        "failure_reason_counts": dict(sorted(failure_reasons.items())),
        "point_summaries": summaries,
        "diagnostic_installed": False,
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
    result = run_endpoint_manifold_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "exact_hover_margin_admissible": result[
                    "exact_hover_margin_admissible"
                ],
                "margin_admissible_point_count": result[
                    "margin_admissible_point_count"
                ],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
