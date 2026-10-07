"""CPU-only bounded first-H descent-corridor reconstruction."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Mapping

from rocell.application.context import load_simulation_context
from rocell.application.model_motion_registry_v2 import ingest_with_trusted_registry_v2
from rocell.application.trajectory_simulation import TrajectorySimulationPolicy
from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_trajectory_plan_v1 import (
    TypingPhaseWaypointV1,
    TypingTrajectoryMetricsV1,
    TypingTrajectoryPlanV1,
    TypingTrajectoryPolicyV1,
    _evidence_float,
    _park_baseline_points,
    _screening_samples,
    _time_for_points,
    _timings_for_endpoints,
    compile_typing_trajectory_plan_v1,
)
from rocell.application.trajectory_simulation import evaluate_joint_trajectory_solution
from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
from rocell.kinematics import ARM_JOINT_NAMES, BoardToolTipTarget
from rocell.models import Point3Mm, SpeedClass, decode_model_motion_batch_v2_json
from rocell.motion.primitives import MotionPhase

from .actual_output_compatibility_v1 import (
    _plan,
    _registry_for_batch,
    build_actual_emitter_payload,
)
from .typing_twin_110mm_full_route_v1 import (
    _load_fixture as _load_reconstruction_fixture,
)
from .typing_twin_ik_collision_v1 import SCOPE, _synthetic_ready_tip, _synthetic_snapshot
from .typing_twin_ik_endpoint_manifold_study_v1 import _point_summary
from .typing_twin_ik_route_study_v1 import _solver_for_seed


SCHEMA = "tactevra.typing_twin_first_h_descent_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_first_h_descent_fixture.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("first-H descent fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected first-H descent fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _pipeline(fixture: Mapping[str, Any], workspace: Path) -> tuple[Any, ...]:
    parent_path = workspace / fixture["parent_fixture"]["path"]
    parent = _load_reconstruction_fixture(parent_path, workspace)
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent reconstruction fixture identity changed")
    collision_parent_path = workspace / parent["parent_fixture"]["path"]
    collision_parent = json.loads(collision_parent_path.read_text(encoding="utf-8"))
    context = load_simulation_context(workspace, workspace / "software/config/system_manifest.json")
    case = collision_parent["case"]
    targets = tuple(case["expected_targets"])
    payload = build_actual_emitter_payload(
        workspace, text=case["text"], targets=targets,
        batch_id=case["batch_id"], request_id=case["request_id"],
    )
    batch = decode_model_motion_batch_v2_json(payload)
    semantic_plan = _plan(case["text"], targets)
    registry = _registry_for_batch(context, batch)
    ingress = ingest_with_trusted_registry_v2(
        batch, semantic_plan, context, registry=registry,
        current_time_epoch_ms=batch.evidence.evaluated_at_epoch_ms,
        current_monotonic_ns=9_000_000_000,
    )
    snapshot = replace(
        _synthetic_snapshot(context),
        hand_T_tool=RigidTransform("G", "T", Rotation3.identity(), Vec3(0.0, 0.0, -110.0)),
    )
    ready = _synthetic_ready_tip(context, snapshot)
    route = collision_parent["route"]
    execution = compile_typing_execution_plan_v1(
        batch, ingress,
        config=TypingExecutionConfigV1(
            config_id="typing-twin-first-h-descent-v1",
            calibration_snapshot_sha256=snapshot.snapshot_sha256,
            tool_profile_sha256="4" * 64,
            dynamics_profile_sha256=route["dynamics_profile_sha256"],
            route_reference_point=Point3Mm("board", ready.x, ready.y, ready.z),
            hover_clearance_mm=25.0,
            settle_position_tolerance_mm=route["settle_position_tolerance_mm"],
            settle_velocity_tolerance_mm_s=route["settle_velocity_tolerance_mm_s"],
            settle_hold_ms=route["settle_hold_ms"], preview_horizon=1,
            speed_class=SpeedClass.SLOW,
        ),
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution,
        policy=TypingTrajectoryPolicyV1(
            policy_id="typing-twin-first-h-descent-quintic-v1",
            maximum_cartesian_step_mm=route["maximum_cartesian_step_mm"],
            maximum_velocity_mm_s=route["maximum_velocity_mm_s"],
            maximum_acceleration_mm_s2=route["maximum_acceleration_mm_s2"],
            maximum_jerk_mm_s3=route["maximum_jerk_mm_s3"],
            hover_settle_ms=route["hover_settle_ms"],
            contact_dwell_ms=route["contact_dwell_ms"],
        ),
    )
    return context, snapshot, targets, batch, ingress, execution, trajectory


def _candidate_trajectory(
    baseline: TypingTrajectoryPlanV1,
    execution: Any,
    *,
    offset_xy_mm: tuple[float, float],
    precontact_height_mm: float,
) -> TypingTrajectoryPlanV1:
    endpoints = list(baseline.phase_waypoints)
    if offset_xy_mm != (0.0, 0.0):
        hover = endpoints[1]
        contact = endpoints[2]
        lateral = Point3Mm("board", hover.point.x + offset_xy_mm[0],
                          hover.point.y + offset_xy_mm[1], hover.point.z)
        precontact = Point3Mm("board", contact.point.x + offset_xy_mm[0],
                             contact.point.y + offset_xy_mm[1],
                             contact.point.z + precontact_height_mm)
        inserted = [
            endpoints[0], endpoints[1],
            TypingPhaseWaypointV1(2, MotionPhase.TRANSIT, 0, "H", lateral),
            TypingPhaseWaypointV1(3, MotionPhase.APPROACH, 0, "H", precontact),
        ]
        inserted.extend(endpoints[2:])
        endpoints = [
            TypingPhaseWaypointV1(index, item.phase, item.action_index,
                                  item.target_id, item.point)
            for index, item in enumerate(inserted)
        ]
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
        estimated_time_reduction_fraction=_evidence_float(saved / park_ms if park_ms else 0.0),
    )
    return TypingTrajectoryPlanV1(
        source_plan_sha256=execution.plan_sha256, policy=policy,
        phase_waypoints=endpoint_tuple, screening_samples=samples,
        timing_segments=timings, metrics=metrics,
    )


def _screen(trajectory: TypingTrajectoryPlanV1, context: Any, snapshot: Any,
            maximum_samples: int) -> dict[str, Any]:
    solver = _solver_for_seed(
        context, snapshot,
        {name: context.scenario.ready_arm_joint_positions_rad[name].value for name in ARM_JOINT_NAMES},
    )
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=trajectory.policy.maximum_cartesian_step_mm,
        maximum_refinement_rounds=0, maximum_waypoints_per_round=maximum_samples,
        maximum_total_ik_solves=maximum_samples, maximum_route_targets=16,
    )
    previous = {name: context.scenario.ready_arm_joint_positions_rad[name].value
                for name in ARM_JOINT_NAMES}
    results = []
    from rocell_ai.typing_twin_ik_branch_selection_study_v1 import _waypoints
    waypoints = _waypoints(trajectory)
    for waypoint in waypoints:
        solved = solver.solve(
            BoardToolTipTarget(waypoint.point_board),
            seed_joint_positions=({name: JointPosition.radians(previous[name])
                                   for name in ARM_JOINT_NAMES},),
        )
        result = evaluate_joint_trajectory_solution(
            waypoint, solved, solver, context.scenario.controller_joint_intersection_rad,
            previous, policy,
        )
        results.append(result)
        if not result.accepted:
            break
        previous = dict(result.solution_arm_joint_positions_rad)
    accepted = [item for item in results if item.accepted]
    return {
        "route_sample_count": len(waypoints),
        "evaluated_sample_count": len(results),
        "accepted_sample_count": len(accepted),
        "all_samples_accepted": len(accepted) == len(waypoints),
        "failure_reason": None if len(accepted) == len(waypoints) else results[-1].failure_reason,
        "failure_waypoint": None if len(accepted) == len(waypoints) else results[-1].to_dict(),
        "minimum_accepted_margin": min((item.minimum_normalized_arm_joint_margin for item in accepted), default=None),
        "maximum_accepted_joint_delta_rad": max((item.maximum_joint_delta_rad for item in accepted), default=None),
        "joint_results": [item.to_dict() for item in results],
    }


def run_descent_study(fixture_path: Path, *, workspace: Path) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    context, snapshot, targets, batch, ingress, execution, baseline = _pipeline(fixture, workspace)
    search = fixture["search"]
    offsets = [(0.0, 0.0)]
    for radius in search["offset_radius_mm"]:
        offsets.extend((radius * dx, radius * dy) for dx, dy in search["directions"])
    candidates = [(offset, 0.0) for offset in offsets[:1]]
    candidates.extend(itertools.product(offsets[1:], search["precontact_height_mm"]))
    if len(candidates) != fixture["decision_rules"]["candidate_count_exact"]:
        raise ValueError("descent candidate count differs from frozen fixture")
    ready_values = {name: context.scenario.ready_arm_joint_positions_rad[name].value
                    for name in ARM_JOINT_NAMES}
    solver = _solver_for_seed(context, snapshot, ready_values)
    point_policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=baseline.policy.maximum_cartesian_step_mm,
        maximum_refinement_rounds=0, maximum_waypoints_per_round=512,
        maximum_total_ik_solves=512, maximum_route_targets=len(targets),
    )
    contact = execution.actions[0].contact_point
    exact_contact = _point_summary(
        goal=contact, offset=(0.0, 0.0, 0.0), solver=solver,
        ready_values=ready_values,
        bounds=context.scenario.controller_joint_intersection_rad, policy=point_policy,
    )
    rows = []
    for offset, height in candidates:
        trajectory = _candidate_trajectory(
            baseline, execution, offset_xy_mm=tuple(offset),
            precontact_height_mm=float(height),
        )
        screened = _screen(trajectory, context, snapshot,
                           fixture["resource_limits"]["maximum_route_samples"])
        row = {
            "candidate_id": f"dx-{offset[0]:g}-dy-{offset[1]:g}-h-{height:g}",
            "offset_xy_mm": list(offset), "precontact_height_mm": height,
            "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
            **screened,
        }
        row["candidate_sha256"] = _sha(row)
        rows.append(row)
    passing = [row for row in rows if row["all_samples_accepted"]]
    best = max(rows, key=lambda row: (row["accepted_sample_count"],
                                      row["minimum_accepted_margin"] or -math.inf,
                                      -row["route_sample_count"]))
    decision = "PASS_BOUNDED_DESCENT_CORRIDOR_FOUND" if passing else "BLOCKED_NO_BOUNDED_DESCENT_CORRIDOR"
    core = {
        "schema": SCHEMA, "scope": SCOPE, "fixture_sha256": fixture["fixture_sha256"],
        "ordered_targets": list(targets), "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "exact_contact_point": exact_contact,
        "candidate_count": len(rows), "passing_candidate_count": len(passing),
        "best_candidate": best, "candidates": rows,
        "installed_collision_gate_cleared": False,
        "continuous_collision_proven": False,
        "controller_commands": [], "hardware_commands_generated": 0,
        "hardware_access": False, "hardware_writes": 0,
        "physical_movements": 0, "physical_authority": False,
        "decision": decision, "limitations": fixture["limitations"],
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_descent_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": result["decision"],
                      "passing_candidate_count": result["passing_candidate_count"],
                      "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
