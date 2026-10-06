"""CPU-only candidate-park geometry attribution for the typing twin."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Mapping

from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import READY_STATUS
from rocell.application.typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from rocell.application.trajectory_simulation import TrajectorySimulationError
from rocell.geometry import JointPosition, Point3Mm as GeometryPoint3Mm
from rocell.kinematics import ARM_JOINT_NAMES, BoardToolTipTarget, IkStatus
from rocell.models import Point3Mm, SpeedClass

from .typing_twin_ik_collision_v1 import SCOPE, _load_fixture as _load_parent_fixture
from .typing_twin_ik_route_study_v1 import (
    _build_pipeline,
    _screen_candidate,
    _solver_for_seed,
)


SCHEMA = "tactevra.typing_twin_ik_route_geometry_study_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_ik_route_geometry_study_fixture.v1"


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
        raise ValueError("route-geometry fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected route-geometry fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source changed: {binding['path']}")
    return document


def _candidate_plan(
    parent: Mapping[str, Any], batch: Any, ingress: Mapping[str, Any], snapshot: Any,
    park: Point3Mm,
) -> tuple[Any, Any]:
    route = parent["route"]
    execution = compile_typing_execution_plan_v1(
        batch,
        ingress,
        config=TypingExecutionConfigV1(
            config_id=f"{route['config_id']}-candidate-park",
            calibration_snapshot_sha256=snapshot.snapshot_sha256,
            tool_profile_sha256=route["tool_profile_sha256"],
            dynamics_profile_sha256=route["dynamics_profile_sha256"],
            route_reference_point=park,
            hover_clearance_mm=route["hover_clearance_mm"],
            settle_position_tolerance_mm=route["settle_position_tolerance_mm"],
            settle_velocity_tolerance_mm_s=route["settle_velocity_tolerance_mm_s"],
            settle_hold_ms=route["settle_hold_ms"], preview_horizon=1,
            speed_class=SpeedClass.SLOW,
        ),
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution,
        policy=TypingTrajectoryPolicyV1(
            policy_id=f"{route['trajectory_policy_id']}-candidate-park",
            maximum_cartesian_step_mm=route["maximum_cartesian_step_mm"],
            maximum_velocity_mm_s=route["maximum_velocity_mm_s"],
            maximum_acceleration_mm_s2=route["maximum_acceleration_mm_s2"],
            maximum_jerk_mm_s3=route["maximum_jerk_mm_s3"],
            hover_settle_ms=route["hover_settle_ms"],
            contact_dwell_ms=route["contact_dwell_ms"],
        ),
    )
    return execution, trajectory


def run_route_geometry_study(fixture_path: Path, *, workspace: Path) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    search = fixture["search"]
    combinations = list(itertools.product(
        search["x_offset_from_first_hover_mm"],
        search["y_offset_from_first_hover_mm"],
        search["z_above_first_hover_mm"],
    ))
    if len(combinations) != fixture["decision_rules"]["candidate_count_exact"]:
        raise ValueError("candidate park grid differs from frozen count")
    parent_path = workspace / fixture["parent_fixture"]["path"]
    parent = _load_parent_fixture(parent_path, workspace)
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent fixture canonical identity changed")
    (
        context, snapshot, _ready_tip, targets, batch, ingress, fresh,
        baseline_execution, baseline_trajectory,
    ) = _build_pipeline(parent, workspace)
    ready_values = {
        name: context.scenario.ready_arm_joint_positions_rad[name].value
        for name in ARM_JOINT_NAMES
    }
    maximum_samples = fixture["resource_limits"]["maximum_ik_samples_per_candidate"]
    baseline_summary, _ = _screen_candidate(
        "baseline-synthetic-ready", ready_values, context=context, snapshot=snapshot,
        execution=baseline_execution, trajectory=baseline_trajectory,
        maximum_samples=maximum_samples,
    )
    first_hover = baseline_execution.actions[0].hover_point
    summaries: list[dict[str, Any]] = []
    generation: list[dict[str, Any]] = []
    passing_reports: dict[str, dict[str, Any]] = {}
    candidate_points: dict[str, dict[str, float]] = {}
    for ordinal, (x_offset, y_offset, z_above) in enumerate(combinations, start=1):
        candidate_id = f"park-grid-{ordinal:03d}"
        park = Point3Mm(
            "board", first_hover.x + x_offset, first_hover.y + y_offset,
            first_hover.z + z_above,
        )
        solved = _solver_for_seed(context, snapshot, ready_values).solve(
            BoardToolTipTarget(
                GeometryPoint3Mm("board", park.x, park.y, park.z)
            ),
            seed_joint_positions=({
                name: JointPosition.radians(value)
                for name, value in ready_values.items()
            },),
        )
        item = {
            "candidate_id": candidate_id,
            "park_point_board_mm": {"x": park.x, "y": park.y, "z": park.z},
            "park_point_sha256": _sha({
                "frame": park.frame, "x": park.x, "y": park.y, "z": park.z,
            }),
            "park_ik_status": solved.status.value,
            "park_selected_attempt_index": solved.selected_attempt_index,
        }
        if solved.status is not IkStatus.CONVERGED:
            item["route_screen_executed"] = False
            item["generation_sha256"] = _sha(item)
            generation.append(item)
            continue
        seed_values = {
            position.name: position.position.value
            for position in solved.solution_arm_joint_positions
        }
        execution, trajectory = _candidate_plan(parent, batch, ingress, snapshot, park)
        try:
            summary, report = _screen_candidate(
                candidate_id, seed_values, context=context, snapshot=snapshot,
                execution=execution, trajectory=trajectory,
                maximum_samples=maximum_samples,
            )
        except TrajectorySimulationError as error:
            if str(error) != "IK solution must use the exact canonical arm-joint order":
                raise
            summary = {
                "candidate_id": candidate_id,
                "seed_sha256": _sha(seed_values),
                "status": "BLOCKED_CANONICAL_IK_NO_SOLUTION_EXCEPTION",
                "evaluated_sample_count": None,
                "accepted_sample_count": None,
                "failure_reason": "CANONICAL_IK_RETURNED_NO_ORDERED_SOLUTION",
                "minimum_normalized_arm_joint_margin": None,
                "maximum_joint_delta_rad": None,
                "screen_sha256": None,
            }
            report = None
        summary["trajectory_sample_count"] = len(trajectory.screening_samples)
        summary["trajectory_plan_sha256"] = trajectory.trajectory_plan_sha256
        summary["candidate_summary_sha256"] = _sha({
            key: value for key, value in summary.items()
            if key != "candidate_summary_sha256"
        })
        item["route_screen_executed"] = True
        item["resolved_seed_sha256"] = _sha(seed_values)
        item["generation_sha256"] = _sha(item)
        generation.append(item)
        summaries.append(summary)
        candidate_points[candidate_id] = item["park_point_board_mm"]
        if report is not None and report["status"] == READY_STATUS:
            passing_reports[candidate_id] = report

    passing = [item for item in summaries if item["status"] == READY_STATUS]
    selected = None
    selected_report = None
    if passing:
        selected = min(
            passing,
            key=lambda item: (
                -item["minimum_normalized_arm_joint_margin"],
                item["maximum_joint_delta_rad"], item["candidate_id"],
            ),
        )
        selected = {**selected, "park_point_board_mm": candidate_points[selected["candidate_id"]]}
        selected_report = passing_reports[selected["candidate_id"]]
    decision = (
        "PASS_FULL_ROUTE_CANDIDATE_PARK_FOUND" if selected is not None
        else "BLOCKED_NO_FULL_ROUTE_CANDIDATE_PARK"
    )
    core = {
        "schema": SCHEMA, "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "parent_fixture_sha256": parent["fixture_sha256"],
        "ordered_targets": list(targets),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": fresh["preplanner_gate_sha256"],
        "baseline_control": baseline_summary,
        "candidate_generation": generation,
        "candidate_summaries": summaries,
        "passing_candidate_count": len(passing),
        "selected_candidate": selected,
        "selected_full_ik_screen": selected_report,
        "candidate_park_installed": False,
        "camera_clearance_evaluated": False,
        "collision_gate_cleared": False,
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
    result = run_route_geometry_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": result["decision"],
        "passing_candidate_count": result["passing_candidate_count"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
