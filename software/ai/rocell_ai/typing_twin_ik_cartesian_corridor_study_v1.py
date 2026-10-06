"""CPU-only first-H Cartesian corridor study for the typing twin."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

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
from rocell.application.typing_trajectory_ik_screen_v1 import READY_STATUS
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.models import Point3Mm
from rocell.motion.primitives import MotionPhase

from .typing_twin_ik_collision_v1 import SCOPE, _load_fixture as _load_parent_fixture
from .typing_twin_ik_route_study_v1 import _build_pipeline, _screen_candidate


SCHEMA = "tactevra.typing_twin_ik_cartesian_corridor_study_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_ik_cartesian_corridor_study_fixture.v1"


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
        raise ValueError("Cartesian-corridor fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected Cartesian-corridor fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _append_distinct(points: list[Point3Mm], point: Point3Mm) -> None:
    if not points or points[-1] != point:
        points.append(point)


def _corridor_points(
    start: Point3Mm,
    first_hover: Point3Mm,
    *,
    height_above_start_mm: float,
    planar_order: str,
) -> tuple[Point3Mm, ...]:
    height = start.z + height_above_start_mm
    points: list[Point3Mm] = [start]
    _append_distinct(points, Point3Mm("board", start.x, start.y, height))
    if planar_order == "DIAGONAL":
        _append_distinct(
            points, Point3Mm("board", first_hover.x, first_hover.y, height)
        )
    elif planar_order == "X_THEN_Y":
        _append_distinct(points, Point3Mm("board", first_hover.x, start.y, height))
        _append_distinct(
            points, Point3Mm("board", first_hover.x, first_hover.y, height)
        )
    elif planar_order == "Y_THEN_X":
        _append_distinct(points, Point3Mm("board", start.x, first_hover.y, height))
        _append_distinct(
            points, Point3Mm("board", first_hover.x, first_hover.y, height)
        )
    else:
        raise ValueError(f"unsupported planar order: {planar_order}")
    _append_distinct(points, first_hover)
    return tuple(points)


def _candidate_trajectory(
    baseline: TypingTrajectoryPlanV1,
    execution: Any,
    *,
    height_above_start_mm: float,
    planar_order: str,
) -> TypingTrajectoryPlanV1:
    start = baseline.phase_waypoints[0].point
    first_hover = baseline.phase_waypoints[1].point
    corridor = _corridor_points(
        start,
        first_hover,
        height_above_start_mm=height_above_start_mm,
        planar_order=planar_order,
    )
    endpoints: list[TypingPhaseWaypointV1] = [
        TypingPhaseWaypointV1(0, MotionPhase.PARK, None, None, start)
    ]
    for point in corridor[1:-1]:
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
        park_baseline_distance_mm=_evidence_float(
            execution.metrics.park_total_distance_mm
        ),
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


def run_cartesian_corridor_study(
    fixture_path: Path,
    *,
    workspace: Path,
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    search = fixture["search"]
    candidates = [
        (height, order)
        for height in search["height_above_start_mm"]
        for order in search["planar_orders"]
    ]
    if len(candidates) != fixture["decision_rules"]["candidate_count_exact"]:
        raise ValueError("Cartesian-corridor search differs from frozen count")
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
    maximum_samples = fixture["resource_limits"]["maximum_ik_samples_per_candidate"]
    baseline, _ = _screen_candidate(
        "baseline-synthetic-ready",
        ready_values,
        context=context,
        snapshot=snapshot,
        execution=execution,
        trajectory=baseline_trajectory,
        maximum_samples=maximum_samples,
    )
    expected = fixture["baseline_control"]
    if (
        baseline["evaluated_sample_count"] != expected["evaluated_sample_count"]
        or baseline["failure_reason"] != expected["failure_reason"]
    ):
        raise ValueError("baseline control no longer reproduces the frozen failure")
    summaries: list[dict[str, Any]] = []
    passing_reports: dict[str, dict[str, Any]] = {}
    for height, order in candidates:
        candidate_id = f"corridor-{int(height):03d}-{order.lower().replace('_', '-')}"
        trajectory = _candidate_trajectory(
            baseline_trajectory,
            execution,
            height_above_start_mm=height,
            planar_order=order,
        )
        summary, report = _screen_candidate(
            candidate_id,
            ready_values,
            context=context,
            snapshot=snapshot,
            execution=execution,
            trajectory=trajectory,
            maximum_samples=maximum_samples,
        )
        summary.update(
            {
                "height_above_start_mm": height,
                "planar_order": order,
                "trajectory_sample_count": len(trajectory.screening_samples),
                "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
                "corridor_endpoint_count": len(trajectory.phase_waypoints)
                - len(baseline_trajectory.phase_waypoints),
            }
        )
        summary["candidate_summary_sha256"] = _sha(
            {
                key: value
                for key, value in summary.items()
                if key != "candidate_summary_sha256"
            }
        )
        summaries.append(summary)
        if report["status"] == READY_STATUS:
            passing_reports[candidate_id] = report
    passing = [item for item in summaries if item["candidate_id"] in passing_reports]
    selected = None
    selected_report = None
    if passing:
        selected = min(
            passing,
            key=lambda item: (
                -item["minimum_normalized_arm_joint_margin"],
                item["maximum_joint_delta_rad"],
                item["trajectory_sample_count"],
                item["candidate_id"],
            ),
        )
        selected_report = passing_reports[selected["candidate_id"]]
    decision = (
        "PASS_FULL_ROUTE_CARTESIAN_CORRIDOR_FOUND"
        if selected is not None
        else "BLOCKED_NO_FULL_ROUTE_CARTESIAN_CORRIDOR"
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
        "baseline_control": baseline,
        "candidate_summaries": summaries,
        "passing_candidate_count": len(passing),
        "selected_candidate": selected,
        "selected_full_ik_screen": selected_report,
        "candidate_corridor_installed": False,
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
    result = run_cartesian_corridor_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "passing_candidate_count": result["passing_candidate_count"],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
