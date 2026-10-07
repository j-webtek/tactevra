"""CPU-only 120 mm exact-contact and vertical-depth feasibility study."""
from __future__ import annotations

import argparse
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
from rocell.geometry import JointPosition
from rocell.kinematics import ARM_JOINT_NAMES, BoardToolTipTarget
from rocell.models import Point3Mm
from rocell.motion.primitives import MotionPhase

from .typing_twin_hover_binding_audit_v1 import (
    _load_fixture as _load_hover_fixture,
    _solver,
)
from .typing_twin_ik_endpoint_manifold_study_v1 import _point_summary
from .typing_twin_ik_route_study_v1 import _build_pipeline
from .typing_twin_ik_collision_v1 import SCOPE


SCHEMA = "tactevra.typing_twin_120mm_exact_contact_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_120mm_exact_contact_fixture.v1"


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
        raise ValueError("120 mm exact-contact fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected 120 mm exact-contact fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _profile_clearances(maximum_mm: float, step_mm: float) -> tuple[float, ...]:
    count = round(maximum_mm / step_mm)
    if not math.isclose(count * step_mm, maximum_mm, abs_tol=1e-9):
        raise ValueError("vertical profile must terminate exactly at contact")
    return tuple(round(maximum_mm - index * step_mm, 9) for index in range(count + 1))


def _sequential_profile(
    *,
    solver: Any,
    contact: Point3Mm,
    clearances: tuple[float, ...],
    ready_values: Mapping[str, float],
    bounds: Mapping[str, tuple[float, float]],
    policy: TrajectorySimulationPolicy,
    source_check_id: str,
) -> dict[str, Any]:
    hover_point = Point3Mm(
        "board", contact.x, contact.y, contact.z + clearances[0]
    )
    hover_solution = solver.solve(
        BoardToolTipTarget(hover_point),
        seed_joint_positions=(
            {
                name: JointPosition.radians(ready_values[name])
                for name in ARM_JOINT_NAMES
            },
        ),
    )
    if not hover_solution.converged:
        return {
            "bootstrap": {
                "accepted": False,
                "failure_reason": "NO_CONVERGED_HOVER_BOOTSTRAP",
                "clearance_above_contact_mm": clearances[0],
            },
            "profile_point_count": len(clearances),
            "evaluated_point_count": 0,
            "accepted_point_count": 0,
            "all_points_accepted": False,
            "failure_reason": "NO_CONVERGED_HOVER_BOOTSTRAP",
            "failure_waypoint": None,
            "minimum_accepted_margin": None,
            "maximum_accepted_joint_delta_rad": None,
            "joint_results": [],
        }
    previous = {
        item.name: item.position.value
        for item in hover_solution.solution_arm_joint_positions
    }
    results = []
    prior_point: Point3Mm | None = None
    for sequence, clearance in enumerate(clearances):
        point = Point3Mm("board", contact.x, contact.y, contact.z + clearance)
        waypoint = CartesianRouteWaypoint(
            sequence=sequence,
            phase=MotionPhase.APPROACH,
            action_index=0,
            semantic_target="H",
            point_board=point,
            distance_from_previous_mm=(
                0.0
                if prior_point is None
                else math.dist(
                    (prior_point.x, prior_point.y, prior_point.z),
                    (point.x, point.y, point.z),
                )
            ),
            source_geometric_sequence=sequence,
            source_check_id=source_check_id,
            source_path_check_passed=True,
            inherited_collision_ids=(),
            phase_endpoint=sequence in (0, len(clearances) - 1),
        )
        solved = (
            hover_solution
            if sequence == 0
            else solver.solve(
                BoardToolTipTarget(point),
                seed_joint_positions=(
                    {
                        name: JointPosition.radians(previous[name])
                        for name in ARM_JOINT_NAMES
                    },
                ),
            )
        )
        evaluated = evaluate_joint_trajectory_solution(
            waypoint,
            solved,
            solver,
            bounds,
            previous,
            policy,
        )
        results.append(evaluated)
        if not evaluated.accepted:
            break
        previous = dict(evaluated.solution_arm_joint_positions_rad)
        prior_point = point
    accepted = [item for item in results if item.accepted]
    complete = len(accepted) == len(clearances)
    return {
        "bootstrap": {
            "accepted": bool(results and results[0].accepted),
            "failure_reason": (
                None if results and results[0].accepted else results[0].failure_reason
            ),
            "clearance_above_contact_mm": clearances[0],
            "continuity_origin": "ACCEPTED_HOVER_SOLUTION_SELF_BASELINE",
        },
        "profile_point_count": len(clearances),
        "evaluated_point_count": len(results),
        "accepted_point_count": len(accepted),
        "all_points_accepted": complete,
        "failure_reason": None if complete else results[-1].failure_reason,
        "failure_waypoint": None if complete else results[-1].to_dict(),
        "minimum_accepted_margin": min(
            (item.minimum_normalized_arm_joint_margin for item in accepted),
            default=None,
        ),
        "maximum_accepted_joint_delta_rad": max(
            (item.maximum_joint_delta_rad for item in accepted),
            default=None,
        ),
        "joint_results": [item.to_dict() for item in results],
    }


def run_exact_contact_study(
    fixture_path: Path, *, workspace: Path,
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    parent_path = workspace / fixture["parent_fixture"]["path"]
    parent = _load_hover_fixture(parent_path, workspace)
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent hover-binding fixture identity changed")
    collision_parent_path = workspace / parent["parent_fixture"]["path"]
    from .typing_twin_ik_collision_v1 import _load_fixture as _load_collision_fixture

    collision_parent = _load_collision_fixture(collision_parent_path, workspace)
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
    ) = _build_pipeline(collision_parent, workspace)
    if targets[0] != fixture["target"]["target_id"]:
        raise ValueError("first semantic target differs from frozen target")
    reconstruction = fixture["reconstruction"]
    tool_length_mm = reconstruction["tool_length_mm"]
    clearances = _profile_clearances(
        reconstruction["maximum_hover_clearance_mm"],
        reconstruction["vertical_step_mm"],
    )
    if len(clearances) != fixture["decision_rules"]["profile_point_count_exact"]:
        raise ValueError("vertical profile point count differs from frozen fixture")
    contact = execution.actions[0].contact_point
    solver = _solver(context, snapshot, tool_length_mm)
    ready_values = {
        name: context.scenario.ready_arm_joint_positions_rad[name].value
        for name in ARM_JOINT_NAMES
    }
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=reconstruction["vertical_step_mm"],
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=fixture["resource_limits"]["maximum_ik_solves"],
        maximum_total_ik_solves=fixture["resource_limits"]["maximum_ik_solves"],
        maximum_route_targets=1,
    )
    pointwise = []
    for clearance in clearances:
        goal = Point3Mm("board", contact.x, contact.y, contact.z + clearance)
        summary = _point_summary(
            goal=goal,
            offset=(0.0, 0.0, clearance),
            solver=solver,
            ready_values=ready_values,
            bounds=context.scenario.controller_joint_intersection_rad,
            policy=policy,
        )
        pointwise.append({"clearance_above_contact_mm": clearance, **summary})
    exact_contact = pointwise[-1]
    sequential = _sequential_profile(
        solver=solver,
        contact=contact,
        clearances=clearances,
        ready_values=ready_values,
        bounds=context.scenario.controller_joint_intersection_rad,
        policy=policy,
        source_check_id=fixture["fixture_sha256"],
    )
    if not exact_contact["point_accepted"]:
        decision = "BLOCKED_120MM_EXACT_CONTACT"
    elif not sequential["all_points_accepted"]:
        decision = "BLOCKED_120MM_VERTICAL_PROFILE"
    else:
        decision = "EXPLORATORY_120MM_EXACT_CONTACT_AND_VERTICAL_PROFILE_ADMISSIBLE"
    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "parent_fixture_sha256": parent["fixture_sha256"],
        "ordered_targets": list(targets),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": fresh["preplanner_gate_sha256"],
        "parent_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "tool_length_mm": tool_length_mm,
        "contact_point_board_mm": [contact.x, contact.y, contact.z],
        "profile_clearances_above_contact_mm": list(clearances),
        "pointwise_profile": pointwise,
        "exact_contact": exact_contact,
        "sequential_vertical_profile": sequential,
        "target_coordinate_change_count": 0,
        "ik_threshold_change_count": 0,
        "continuity_threshold_change_count": 0,
        "full_route_reconstruction_run": False,
        "installed_collision_gate_cleared": False,
        "continuous_collision_proven": False,
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
    result = run_exact_contact_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "exact_contact_accepted": result["exact_contact"]["point_accepted"],
                "sequential_profile_accepted": result["sequential_vertical_profile"][
                    "all_points_accepted"
                ],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
