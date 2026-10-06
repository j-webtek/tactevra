"""Bounded CPU-only branch-selection study for the canonical typing route."""
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
    JointTrajectoryWaypointResult,
    TrajectorySimulationPolicy,
    evaluate_joint_trajectory_solution,
)
from rocell.geometry import JointPosition
from rocell.kinematics import ARM_JOINT_NAMES, BoardToolTipTarget

from .typing_twin_ik_collision_v1 import SCOPE, _load_fixture as _load_parent_fixture
from .typing_twin_ik_route_study_v1 import (
    _build_pipeline,
    _screen_candidate,
    _solver_for_seed,
)


SCHEMA = "tactevra.typing_twin_ik_branch_selection_study_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_ik_branch_selection_study_fixture.v1"


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
        raise ValueError("branch-selection fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected branch-selection fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _waypoints(plan: Any) -> tuple[CartesianRouteWaypoint, ...]:
    rows: list[CartesianRouteWaypoint] = []
    for index, sample in enumerate(plan.screening_samples):
        distance = 0.0
        if index:
            previous = plan.screening_samples[index - 1].point
            distance = math.dist(
                (previous.x, previous.y, previous.z),
                (sample.point.x, sample.point.y, sample.point.z),
            )
        rows.append(
            CartesianRouteWaypoint(
                sequence=sample.sequence,
                phase=sample.phase,
                action_index=sample.action_index,
                semantic_target=sample.target_id,
                point_board=sample.point,
                distance_from_previous_mm=distance,
                source_geometric_sequence=sample.endpoint_sequence,
                source_check_id=plan.trajectory_plan_sha256,
                source_path_check_passed=True,
                inherited_collision_ids=(),
                phase_endpoint=sample.phase_endpoint,
            )
        )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class _Branch:
    solution: Mapping[str, float]
    results: tuple[JointTrajectoryWaypointResult, ...]
    minimum_margin: float
    maximum_delta: float
    residual_sum: float

    @property
    def identity(self) -> tuple[float, ...]:
        return tuple(round(self.solution[name], 9) for name in ARM_JOINT_NAMES)

    @property
    def rank(self) -> tuple[float, float, float, tuple[float, ...]]:
        return (
            -self.minimum_margin,
            self.maximum_delta,
            self.residual_sum,
            self.identity,
        )


def _run_beam(
    *,
    beam_width: int,
    solver: Any,
    conditioning_solver: Any,
    waypoints: tuple[CartesianRouteWaypoint, ...],
    bounds: Mapping[str, tuple[float, float]],
    policy: TrajectorySimulationPolicy,
    maximum_solver_calls: int,
    maximum_candidate_evaluations: int,
) -> dict[str, Any]:
    beam: tuple[_Branch, ...] = ()
    last_nonempty: tuple[_Branch, ...] = ()
    solver_calls = 0
    candidate_evaluations = 0
    maximum_observed_beam = 0
    first_failure: dict[str, Any] | None = None
    for waypoint in waypoints:
        parents: tuple[_Branch | None, ...] = beam if beam else (None,)
        expanded: list[_Branch] = []
        rejected_by_reason: dict[str, int] = {}
        for parent in parents:
            if solver_calls >= maximum_solver_calls:
                raise ValueError("branch-selection solver-call budget exhausted")
            previous = None if parent is None else parent.solution
            seeds = (
                ()
                if previous is None
                else (
                    {
                        name: JointPosition.radians(previous[name])
                        for name in ARM_JOINT_NAMES
                    },
                )
            )
            candidates = solver.solve_candidates(
                BoardToolTipTarget(waypoint.point_board),
                seed_joint_positions=seeds,
            )
            solver_calls += 1
            for solved in candidates:
                candidate_evaluations += 1
                if candidate_evaluations > maximum_candidate_evaluations:
                    raise ValueError("branch-selection candidate budget exhausted")
                result = evaluate_joint_trajectory_solution(
                    waypoint,
                    solved,
                    conditioning_solver,
                    bounds,
                    previous,
                    policy,
                )
                if not result.accepted:
                    reason = result.failure_reason or "UNKNOWN_REJECTION"
                    rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
                    continue
                solution = dict(result.solution_arm_joint_positions_rad)
                margin = result.minimum_normalized_arm_joint_margin
                if margin is None:
                    raise ValueError("accepted branch lacks normalized margin")
                expanded.append(
                    _Branch(
                        solution=solution,
                        results=(result,) if parent is None else (*parent.results, result),
                        minimum_margin=(
                            margin if parent is None else min(parent.minimum_margin, margin)
                        ),
                        maximum_delta=max(
                            0.0 if result.maximum_joint_delta_rad is None else result.maximum_joint_delta_rad,
                            0.0 if parent is None else parent.maximum_delta,
                        ),
                        residual_sum=(
                            solved.residual.weighted_residual_norm_mm
                            + (0.0 if parent is None else parent.residual_sum)
                        ),
                    )
                )
        unique: dict[tuple[float, ...], _Branch] = {}
        for branch in sorted(expanded, key=lambda item: item.rank):
            unique.setdefault(branch.identity, branch)
        beam = tuple(sorted(unique.values(), key=lambda item: item.rank)[:beam_width])
        maximum_observed_beam = max(maximum_observed_beam, len(beam))
        if not beam:
            first_failure = {
                "waypoint_sequence": waypoint.sequence,
                "phase": waypoint.phase.value,
                "semantic_target": waypoint.semantic_target,
                "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
            }
            break
        last_nonempty = beam
    selected = None if not last_nonempty else min(last_nonempty, key=lambda item: item.rank)
    core = {
        "beam_width": beam_width,
        "route_waypoint_count": len(waypoints),
        "accepted_waypoint_count": 0 if selected is None else len(selected.results),
        "full_route_accepted": selected is not None and len(selected.results) == len(waypoints),
        "solver_call_count": solver_calls,
        "candidate_evaluation_count": candidate_evaluations,
        "maximum_observed_beam_width": maximum_observed_beam,
        "first_failure": first_failure,
        "selected_minimum_normalized_arm_joint_margin": (
            None if selected is None else selected.minimum_margin
        ),
        "selected_maximum_adjacent_joint_delta_rad": (
            None if selected is None else selected.maximum_delta
        ),
        "selected_results": (
            None if selected is None else [item.to_dict() for item in selected.results]
        ),
    }
    return {**core, "beam_result_sha256": _sha(core)}


def run_branch_selection_study(
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
        maximum_samples=fixture["resource_limits"]["maximum_route_waypoints"],
    )
    expected = fixture["baseline_control"]
    if (
        baseline["evaluated_sample_count"] != expected["evaluated_sample_count"]
        or baseline["failure_reason"] != expected["failure_reason"]
    ):
        raise ValueError("baseline control no longer reproduces the frozen failure")
    solver = _solver_for_seed(context, snapshot, ready_values)
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=trajectory.policy.maximum_cartesian_step_mm,
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=fixture["resource_limits"]["maximum_route_waypoints"],
        maximum_total_ik_solves=fixture["resource_limits"]["maximum_route_waypoints"],
        maximum_route_targets=len(execution.actions),
    )
    route_waypoints = _waypoints(trajectory)
    if len(route_waypoints) != fixture["decision_rules"]["route_waypoint_count_exact"]:
        raise ValueError("route waypoint count differs from the frozen fixture")
    beams = [
        _run_beam(
            beam_width=width,
            solver=solver,
            conditioning_solver=solver,
            waypoints=route_waypoints,
            bounds=context.scenario.controller_joint_intersection_rad,
            policy=policy,
            maximum_solver_calls=fixture["resource_limits"]["maximum_solver_calls_per_beam"],
            maximum_candidate_evaluations=fixture["resource_limits"]["maximum_candidate_evaluations_per_beam"],
        )
        for width in fixture["search"]["beam_widths"]
    ]
    passing = [item for item in beams if item["full_route_accepted"]]
    selected = None if not passing else min(passing, key=lambda item: item["beam_width"])
    decision = (
        "PASS_BRANCH_SELECTION_FULL_ROUTE_FOUND"
        if selected is not None
        else "BLOCKED_NO_BRANCH_SELECTION_FULL_ROUTE"
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
        "beam_results": beams,
        "selected_beam_width": None if selected is None else selected["beam_width"],
        "branch_selection_policy_installed": False,
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
    result = run_branch_selection_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "selected_beam_width": result["selected_beam_width"],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
