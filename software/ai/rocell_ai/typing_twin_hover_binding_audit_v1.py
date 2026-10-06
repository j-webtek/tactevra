"""Audit the synthetic bindings that construct the first keyboard hover."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from rocell.application._pinned_model import load_pinned_urdf
from rocell.application.trajectory_simulation import TrajectorySimulationPolicy
from rocell.geometry import RigidTransform
from rocell.kinematics import ARM_JOINT_NAMES, RoArmM3NumericalIk
from rocell.models import Point3Mm

from .typing_twin_ik_collision_v1 import SCOPE, _load_fixture as _load_parent_fixture
from .typing_twin_ik_endpoint_manifold_study_v1 import _point_summary
from .typing_twin_ik_route_study_v1 import _build_pipeline


SCHEMA = "tactevra.typing_twin_hover_binding_audit_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_hover_binding_audit_fixture.v1"


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
        raise ValueError("hover-binding fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected hover-binding fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _raw_keyboard_target(catalog: Mapping[str, Any], target_id: str) -> dict[str, Any]:
    keyboard = catalog["keyboard"]
    origin_x, origin_y = keyboard["device_origin_board_xy_mm"]
    for row_index, row in enumerate(keyboard["rows"]):
        if target_id not in row["key_ids"]:
            continue
        key_index = row["key_ids"].index(target_id)
        local_x = row["first_center_xy_mm"][0] + key_index * row["step_xy_mm"][0]
        local_y = row["first_center_xy_mm"][1] + key_index * row["step_xy_mm"][1]
        return {
            "target_id": target_id,
            "row_index": row_index,
            "key_index": key_index,
            "device_origin_board_xy_mm": [origin_x, origin_y],
            "local_center_xy_mm": [local_x, local_y],
            "derived_center_board_mm": [
                origin_x + local_x,
                origin_y + local_y,
                keyboard["target_plane_z_board_mm"],
            ],
            "source_state": keyboard["source_state"],
        }
    raise ValueError(f"target is absent from bound keyboard rows: {target_id}")


def _solver(context: Any, snapshot: Any, tool_length_mm: float) -> RoArmM3NumericalIk:
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    return RoArmM3NumericalIk(
        model=model,
        board_T_world=RigidTransform(
            "board", "world", snapshot.board_T_vendor_world.rotation,
            snapshot.board_T_vendor_world.translation_mm,
        ),
        hand_tcp_to_tip_z_mm=-tool_length_mm,
        fixed_gripper_position=context.scenario.fixed_gripper_position,
        ready_arm_joint_positions=context.scenario.ready_arm_joint_positions_rad,
        gripper_bounds_rad=context.scenario.controller_gripper_intersection_rad,
        joint_bounds_rad=context.scenario.controller_joint_intersection_rad,
    )


def run_hover_binding_audit(
    fixture_path: Path, *, workspace: Path,
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    parent_path = workspace / fixture["parent_fixture"]["path"]
    parent = _load_parent_fixture(parent_path, workspace)
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent fixture canonical identity changed")
    (
        context, snapshot, _ready_tip, targets, batch, ingress, fresh,
        execution, trajectory,
    ) = _build_pipeline(parent, workspace)
    if targets[0] != fixture["target"]["target_id"]:
        raise ValueError("first semantic target differs from frozen audit target")

    catalog_path = workspace / fixture["input_bindings"]["target_catalog"]["path"]
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    raw_target = _raw_keyboard_target(catalog, fixture["target"]["target_id"])
    runtime = context.targets.resolve("keyboard", fixture["target"]["target_id"])
    runtime_center = [runtime.center.x, runtime.center.y, runtime.center.z]
    action_contact = execution.actions[0].contact_point
    action_center = [action_contact.x, action_contact.y, action_contact.z]
    target_consistent = (
        raw_target["derived_center_board_mm"] == runtime_center == action_center
    )
    if fixture["decision_rules"]["require_exact_target_binding_match"] and not target_consistent:
        raise ValueError("target geometry binding differs across source, runtime, and plan")

    board = snapshot.board_T_vendor_world
    scenario_board = context.scenario.board_T_world
    board_consistent = (
        board.translation_mm == scenario_board.translation_mm
        and board.rotation == scenario_board.rotation
    )
    if fixture["decision_rules"]["require_exact_board_binding_match"] and not board_consistent:
        raise ValueError("board transform differs between scenario and snapshot")

    current_tool_length = -snapshot.hand_T_tool.translation_mm.z
    parent_hover = parent["route"]["hover_clearance_mm"]
    ready_values = {
        name: context.scenario.ready_arm_joint_positions_rad[name].value
        for name in ARM_JOINT_NAMES
    }
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=trajectory.policy.maximum_cartesian_step_mm,
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=fixture["resource_limits"]["maximum_ik_solves"],
        maximum_total_ik_solves=fixture["resource_limits"]["maximum_ik_solves"],
        maximum_route_targets=1,
    )
    rows = []
    for tool_length in fixture["sweep"]["tool_length_mm"]:
        solver = _solver(context, snapshot, tool_length)
        for hover in fixture["sweep"]["hover_clearance_mm"]:
            goal = Point3Mm(
                "board", runtime.center.x, runtime.center.y, runtime.center.z + hover
            )
            summary = _point_summary(
                goal=goal,
                offset=(0.0, 0.0, 0.0),
                solver=solver,
                ready_values=ready_values,
                bounds=context.scenario.controller_joint_intersection_rad,
                policy=policy,
            )
            rows.append({
                "tool_length_mm": tool_length,
                "hover_clearance_mm": hover,
                "is_parent_binding": (
                    tool_length == current_tool_length and hover == parent_hover
                ),
                "exact_hover_board_mm": summary["point_board_mm"],
                "converged_candidate_count": summary["converged_candidate_count"],
                "accepted_candidate_count": summary["accepted_candidate_count"],
                "exact_hover_margin_admissible": summary["point_accepted"],
                "best_candidate": summary["best_candidate"],
            })
    if len(rows) != fixture["decision_rules"]["combination_count_exact"]:
        raise ValueError("hover-binding combination count differs from fixture")
    feasible = [row for row in rows if row["exact_hover_margin_admissible"]]
    failures = Counter()
    for row in rows:
        best = row["best_candidate"]
        if not row["exact_hover_margin_admissible"]:
            failures["NO_CONVERGED_CANDIDATE" if best is None else best["failure_reason"]] += 1
    decision = (
        "EXPLORATORY_BINDING_MATRIX_CONTAINS_MARGIN_ADMISSIBLE_EXACT_HOVER"
        if feasible
        else "BLOCKED_BINDING_MATRIX_HAS_NO_MARGIN_ADMISSIBLE_EXACT_HOVER"
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
        "binding_audit": {
            "target": {
                **raw_target,
                "runtime_center_board_mm": runtime_center,
                "planned_contact_board_mm": action_center,
                "exact_match": target_consistent,
            },
            "board_transform": {
                "translation_mm": [
                    board.translation_mm.x, board.translation_mm.y,
                    board.translation_mm.z,
                ],
                "rotation_row_major": list(board.rotation.matrix),
                "state": context.scenario.board_T_world_state,
                "exact_match": board_consistent,
            },
            "parent_tool_length_mm": current_tool_length,
            "parent_hover_clearance_mm": parent_hover,
        },
        "combination_count": len(rows),
        "margin_admissible_combination_count": len(feasible),
        "failure_reason_counts": dict(sorted(failures.items())),
        "combinations": rows,
        "target_coordinate_change_count": 0,
        "board_transform_change_count": 0,
        "ik_threshold_change_count": 0,
        "diagnostic_installed": False,
        "planner_installed": False,
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
    result = run_hover_binding_audit(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "decision": result["decision"],
        "margin_admissible_combination_count": result[
            "margin_admissible_combination_count"
        ],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
