"""CPU-only canonical IK branch study for the main-bound typing twin.

The study preserves the parent Cartesian route, semantic target order, target
coordinates, and every canonical IK threshold.  It varies only a bounded set
of deterministic synthetic joint seeds used to reproduce the same ready-tip
point.  Results are exploratory and carry no command or physical authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from rocell.application._pinned_model import load_pinned_urdf
from rocell.application.context import load_simulation_context
from rocell.application.model_motion_registry_v2 import (
    ingest_with_trusted_registry_v2,
    revalidate_with_trusted_registry_v2,
)
from rocell.application.trajectory_simulation import TrajectorySimulationPolicy
from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    READY_STATUS,
    TypingTrajectoryIkSeedV1,
    screen_typing_trajectory_ik_v1,
)
from rocell.application.typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from rocell.geometry import JointPosition, Point3Mm as GeometryPoint3Mm, RigidTransform
from rocell.kinematics import (
    ARM_JOINT_NAMES,
    BoardToolTipTarget,
    IkOptions,
    IkStatus,
    RoArmM3NumericalIk,
)
from rocell.models import Point3Mm, SpeedClass, decode_model_motion_batch_v2_json

from .actual_output_compatibility_v1 import (
    _plan,
    _registry_for_batch,
    build_actual_emitter_payload,
)
from .typing_twin_ik_collision_v1 import (
    SCOPE,
    _load_fixture as _load_parent_fixture,
    _synthetic_ready_tip,
    _synthetic_snapshot,
)


SCHEMA = "tactevra.typing_twin_ik_route_study_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_ik_route_study_fixture.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("IK route-study fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected IK route-study fixture identity")
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
    result = 0.0
    fraction = 1.0
    while index:
        fraction /= base
        index, remainder = divmod(index, base)
        result += remainder * fraction
    return result


def _candidate_seed(
    index: int,
    bounds: Mapping[str, tuple[float, float]],
    *,
    bases: tuple[int, ...],
    fraction_floor: float,
    fraction_ceiling: float,
) -> dict[str, float]:
    width = fraction_ceiling - fraction_floor
    return {
        name: lower + (fraction_floor + width * _halton(index, base)) * (upper - lower)
        for name, base in zip(ARM_JOINT_NAMES, bases, strict=True)
        for lower, upper in (bounds[name],)
    }


def _build_pipeline(parent: Mapping[str, Any], workspace: Path) -> tuple[Any, ...]:
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json"
    )
    case = parent["case"]
    targets = tuple(case["expected_targets"])
    payload = build_actual_emitter_payload(
        workspace, text=case["text"], targets=targets,
        batch_id=case["batch_id"], request_id=case["request_id"],
    )
    batch = decode_model_motion_batch_v2_json(payload)
    plan = _plan(case["text"], targets)
    registry = _registry_for_batch(context, batch)
    ingress = ingest_with_trusted_registry_v2(
        batch, plan, context, registry=registry,
        current_time_epoch_ms=batch.evidence.evaluated_at_epoch_ms,
        current_monotonic_ns=9_000_000_000,
    )
    fresh = revalidate_with_trusted_registry_v2(
        ingress, registry=registry, current_monotonic_ns=10_000_000_000
    )
    snapshot = _synthetic_snapshot(context)
    route = parent["route"]
    ready_tip = _synthetic_ready_tip(context, snapshot)
    route_reference = Point3Mm("board", ready_tip.x, ready_tip.y, ready_tip.z)
    execution = compile_typing_execution_plan_v1(
        batch,
        ingress,
        config=TypingExecutionConfigV1(
            config_id=route["config_id"],
            calibration_snapshot_sha256=snapshot.snapshot_sha256,
            tool_profile_sha256=route["tool_profile_sha256"],
            dynamics_profile_sha256=route["dynamics_profile_sha256"],
            route_reference_point=route_reference,
            hover_clearance_mm=route["hover_clearance_mm"],
            settle_position_tolerance_mm=route["settle_position_tolerance_mm"],
            settle_velocity_tolerance_mm_s=route["settle_velocity_tolerance_mm_s"],
            settle_hold_ms=route["settle_hold_ms"],
            preview_horizon=1,
            speed_class=SpeedClass.SLOW,
        ),
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution,
        policy=TypingTrajectoryPolicyV1(
            policy_id=route["trajectory_policy_id"],
            maximum_cartesian_step_mm=route["maximum_cartesian_step_mm"],
            maximum_velocity_mm_s=route["maximum_velocity_mm_s"],
            maximum_acceleration_mm_s2=route["maximum_acceleration_mm_s2"],
            maximum_jerk_mm_s3=route["maximum_jerk_mm_s3"],
            hover_settle_ms=route["hover_settle_ms"],
            contact_dwell_ms=route["contact_dwell_ms"],
        ),
    )
    return context, snapshot, ready_tip, targets, batch, ingress, fresh, execution, trajectory


def _solver_for_seed(context: Any, snapshot: Any, seed: Mapping[str, float]) -> RoArmM3NumericalIk:
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    bounds = {
        name: context.scenario.controller_joint_intersection_rad[name]
        for name in ARM_JOINT_NAMES
    }
    return RoArmM3NumericalIk(
        model=model,
        board_T_world=RigidTransform(
            "board", "world", snapshot.board_T_vendor_world.rotation,
            snapshot.board_T_vendor_world.translation_mm,
        ),
        hand_tcp_to_tip_z_mm=snapshot.hand_T_tool.translation_mm.z,
        fixed_gripper_position=context.scenario.fixed_gripper_position,
        ready_arm_joint_positions={
            name: JointPosition.radians(seed[name]) for name in ARM_JOINT_NAMES
        },
        gripper_bounds_rad=context.scenario.controller_gripper_intersection_rad,
        options=IkOptions(
            max_attempts=context.scenario.ik_policy.max_attempts,
            max_iterations_per_attempt=context.scenario.ik_policy.max_iterations_per_attempt,
        ),
        joint_bounds_rad=bounds,
    )


def _screen_candidate(
    candidate_id: str,
    candidate_seed: Mapping[str, float],
    *,
    context: Any,
    snapshot: Any,
    execution: Any,
    trajectory: Any,
    maximum_samples: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    seed = TypingTrajectoryIkSeedV1(
        seed_id=candidate_id,
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        build_snapshot_sha256=context.snapshot.snapshot_hash,
        joint_positions_rad=dict(candidate_seed),
    )
    report = screen_typing_trajectory_ik_v1(
        execution,
        trajectory,
        context,
        snapshot,
        seed,
        policy=TrajectorySimulationPolicy(
            maximum_cartesian_step_mm=trajectory.policy.maximum_cartesian_step_mm,
            maximum_refinement_rounds=0,
            maximum_waypoints_per_round=maximum_samples,
            maximum_total_ik_solves=maximum_samples,
            maximum_route_targets=len(execution.actions),
        ),
    )
    results = report["joint_results"]
    accepted = [item for item in results if item["accepted"]]
    summary = {
        "candidate_id": candidate_id,
        "seed_sha256": seed.seed_sha256,
        "status": report["status"],
        "evaluated_sample_count": report["evaluated_sample_count"],
        "accepted_sample_count": len(accepted),
        "failure_reason": None if report["ik_all_samples_accepted"] else results[-1]["failure_reason"],
        "minimum_normalized_arm_joint_margin": (
            min(item["minimum_normalized_arm_joint_margin"] for item in accepted)
            if accepted else None
        ),
        "maximum_joint_delta_rad": (
            max(item["maximum_joint_delta_rad"] for item in accepted)
            if accepted else None
        ),
        "screen_sha256": report["typing_trajectory_ik_screen_sha256"],
    }
    summary["candidate_summary_sha256"] = _sha(summary)
    return summary, report


def run_route_study(fixture_path: Path, *, workspace: Path) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    search = fixture["search"]
    candidate_count = search["halton_candidate_count"]
    if (
        candidate_count != fixture["decision_rules"]["candidate_count_exact"]
        or candidate_count != fixture["resource_limits"]["maximum_candidates"]
        or tuple(search["halton_bases"]) != (2, 3, 5, 7, 11)
    ):
        raise ValueError("candidate search bounds differ from the frozen fixture")
    floor, ceiling = search["normalized_joint_fraction_range"]
    if not 0.0 < floor < ceiling < 1.0:
        raise ValueError("candidate normalized joint range must remain strictly interior")
    parent_path = workspace / fixture["parent_fixture"]["path"]
    parent = _load_parent_fixture(parent_path, workspace)
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent fixture canonical identity changed")
    (
        context, snapshot, ready_tip, targets, batch, ingress, fresh, execution,
        trajectory,
    ) = _build_pipeline(parent, workspace)
    maximum_samples = fixture["resource_limits"]["maximum_ik_samples_per_candidate"]
    ready_values = {
        name: context.scenario.ready_arm_joint_positions_rad[name].value
        for name in ARM_JOINT_NAMES
    }
    baseline_summary, baseline_report = _screen_candidate(
        "baseline-synthetic-ready", ready_values, context=context, snapshot=snapshot,
        execution=execution, trajectory=trajectory, maximum_samples=maximum_samples,
    )
    expected = fixture["baseline_control"]
    if (
        baseline_summary["evaluated_sample_count"] != expected["evaluated_sample_count"]
        or baseline_summary["failure_reason"] != expected["failure_reason"]
    ):
        raise ValueError("baseline control no longer reproduces the frozen failure")

    bounds = {
        name: context.scenario.controller_joint_intersection_rad[name]
        for name in ARM_JOINT_NAMES
    }
    bases = tuple(search["halton_bases"])
    target = BoardToolTipTarget(
        GeometryPoint3Mm("board", ready_tip.x, ready_tip.y, ready_tip.z)
    )
    summaries: list[dict[str, Any]] = [baseline_summary]
    passing_reports: dict[str, dict[str, Any]] = {}
    branch_generation: list[dict[str, Any]] = []
    for index in range(
        search["halton_start_index"],
        search["halton_start_index"] + search["halton_candidate_count"],
    ):
        raw_seed = _candidate_seed(
            index, bounds, bases=bases, fraction_floor=floor,
            fraction_ceiling=ceiling,
        )
        solved = _solver_for_seed(context, snapshot, raw_seed).solve(
            target,
            seed_joint_positions=({
                name: JointPosition.radians(value) for name, value in raw_seed.items()
            },),
        )
        generation = {
            "candidate_id": f"halton-{index:04d}",
            "raw_seed_sha256": _sha(raw_seed),
            "ready_tip_ik_status": solved.status.value,
            "ready_tip_selected_attempt_index": solved.selected_attempt_index,
        }
        if solved.status is not IkStatus.CONVERGED:
            generation["route_screen_executed"] = False
            generation["generation_sha256"] = _sha(generation)
            branch_generation.append(generation)
            continue
        solution = {
            item.name: item.position.value for item in solved.solution_arm_joint_positions
        }
        candidate_id = generation["candidate_id"]
        summary, report = _screen_candidate(
            candidate_id, solution, context=context, snapshot=snapshot,
            execution=execution, trajectory=trajectory, maximum_samples=maximum_samples,
        )
        generation["route_screen_executed"] = True
        generation["resolved_seed_sha256"] = _sha(solution)
        generation["generation_sha256"] = _sha(generation)
        branch_generation.append(generation)
        summaries.append(summary)
        if report["status"] == READY_STATUS:
            passing_reports[candidate_id] = report

    if len(branch_generation) != candidate_count:
        raise ValueError("candidate generation count differs from the frozen fixture")

    passing = [item for item in summaries if item["status"] == READY_STATUS]
    selected = None
    selected_report = None
    if passing:
        selected = min(
            passing,
            key=lambda item: (
                -item["minimum_normalized_arm_joint_margin"],
                item["maximum_joint_delta_rad"],
                item["candidate_id"],
            ),
        )
        selected_report = passing_reports[selected["candidate_id"]]
    decision = (
        "PASS_FULL_ROUTE_SYNTHETIC_SEED_CANDIDATE_FOUND"
        if selected is not None else "BLOCKED_NO_FULL_ROUTE_SEED_CANDIDATE"
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
        "execution_plan_sha256": execution.plan_sha256,
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "trajectory_sample_count": len(trajectory.screening_samples),
        "baseline_control": baseline_summary,
        "candidate_generation": branch_generation,
        "candidate_summaries": summaries[1:],
        "passing_candidate_count": len(passing),
        "selected_candidate": selected,
        "selected_full_ik_screen": selected_report,
        "route_or_start_state_installed": False,
        "installed_collision_gate_cleared": False,
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
    result = run_route_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "decision": result["decision"],
        "passing_candidate_count": result["passing_candidate_count"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
