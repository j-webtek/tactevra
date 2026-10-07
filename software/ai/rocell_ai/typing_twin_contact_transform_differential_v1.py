"""CPU-only exact-contact differential across two source-bound transforms."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from rocell.application.trajectory_simulation import TrajectorySimulationPolicy
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.models import Point3Mm
from rocell.simulation.virtual_profile import load_virtual_commissioning_profile

from .typing_twin_120mm_exact_contact_v1 import (
    _profile_clearances,
    _sequential_profile,
)
from .typing_twin_hover_binding_audit_v1 import (
    _load_fixture as _load_hover_fixture,
    _solver,
)
from .typing_twin_ik_collision_v1 import SCOPE
from .typing_twin_ik_endpoint_manifold_study_v1 import _point_summary
from .typing_twin_ik_route_study_v1 import _build_pipeline


SCHEMA = "tactevra.typing_twin_contact_transform_differential_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_contact_transform_differential_fixture.v1"


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
        raise ValueError("contact-transform differential fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected contact-transform differential fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    if tuple(document["transform_cases"]) != (
        "NOMINAL_SYSTEM_MANIFEST",
        "PROMOTED_VIRTUAL_COMMISSIONING_OVERLAY",
    ):
        raise ValueError("transform case set differs from the frozen fixture")
    return document


def _transform_payload(transform: Any) -> dict[str, Any]:
    return {
        "parent_frame": transform.parent_frame,
        "child_frame": transform.child_frame,
        "rotation_matrix_row_major": list(transform.rotation.matrix),
        "translation_mm": [
            transform.translation_mm.x,
            transform.translation_mm.y,
            transform.translation_mm.z,
        ],
    }


def _evaluate_case(
    *,
    case_id: str,
    transform: Any,
    context: Any,
    contact: Point3Mm,
    clearances: tuple[float, ...],
    tool_length_mm: float,
    ready_values: Mapping[str, float],
    policy: TrajectorySimulationPolicy,
    source_check_id: str,
) -> dict[str, Any]:
    solver = _solver(
        context,
        SimpleNamespace(board_T_vendor_world=transform),
        tool_length_mm,
    )
    pointwise = []
    for clearance in clearances:
        summary = _point_summary(
            goal=contact,
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
        source_check_id=source_check_id,
    )
    if not exact_contact["point_accepted"]:
        decision = "BLOCKED_EXACT_CONTACT"
    elif not sequential["all_points_accepted"]:
        decision = "BLOCKED_VERTICAL_PROFILE"
    else:
        decision = "EXPLORATORY_EXACT_CONTACT_AND_VERTICAL_PROFILE_ADMISSIBLE"
    transform_payload = _transform_payload(transform)
    return {
        "case_id": case_id,
        "board_T_vendor_world": transform_payload,
        "board_T_vendor_world_sha256": _sha(transform_payload),
        "pointwise_profile": pointwise,
        "exact_contact": exact_contact,
        "sequential_vertical_profile": sequential,
        "decision": decision,
    }


def run_contact_transform_differential(
    fixture_path: Path, *, workspace: Path
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    parent_path = workspace / fixture["parent_fixture"]["path"]
    parent = _load_hover_fixture(parent_path, workspace)
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent hover-binding fixture identity changed")
    from .typing_twin_ik_collision_v1 import _load_fixture as _load_collision_fixture

    collision_parent = _load_collision_fixture(
        workspace / parent["parent_fixture"]["path"], workspace
    )
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

    profile = load_virtual_commissioning_profile(context)
    expected_profile = fixture["promoted_profile"]
    if (
        profile.profile_id != expected_profile["profile_id"]
        or profile.study_input.study_input_id != expected_profile["study_input_id"]
        or profile.source_sha256 != expected_profile["source_sha256"]
    ):
        raise ValueError("promoted virtual profile identity changed")
    reconstruction = fixture["reconstruction"]
    tool_length_mm = reconstruction["tool_length_mm"]
    if profile.study_input.keyboard_tool_length_mm != tool_length_mm:
        raise ValueError("promoted profile keyboard tool length differs from fixture")
    clearances = _profile_clearances(
        reconstruction["maximum_hover_clearance_mm"],
        reconstruction["vertical_step_mm"],
    )
    if len(clearances) != fixture["decision_rules"]["profile_point_count_exact"]:
        raise ValueError("vertical profile point count differs from frozen fixture")

    contact = execution.actions[0].contact_point
    ready_values = {
        name: context.scenario.ready_arm_joint_positions_rad[name].value
        for name in ARM_JOINT_NAMES
    }
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=reconstruction["vertical_step_mm"],
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=fixture["resource_limits"]["maximum_ik_solves_per_case"],
        maximum_total_ik_solves=fixture["resource_limits"]["maximum_ik_solves_per_case"],
        maximum_route_targets=1,
    )
    transforms = (
        ("NOMINAL_SYSTEM_MANIFEST", snapshot.board_T_vendor_world),
        (
            "PROMOTED_VIRTUAL_COMMISSIONING_OVERLAY",
            profile.study_input.board_T_vendor_world,
        ),
    )
    cases = [
        _evaluate_case(
            case_id=case_id,
            transform=transform,
            context=context,
            contact=contact,
            clearances=clearances,
            tool_length_mm=tool_length_mm,
            ready_values=ready_values,
            policy=policy,
            source_check_id=f"{fixture['fixture_sha256']}:{case_id}",
        )
        for case_id, transform in transforms
    ]
    promoted = cases[1]
    if promoted["exact_contact"]["point_accepted"] and promoted[
        "sequential_vertical_profile"
    ]["all_points_accepted"]:
        decision = "PROMOTED_TRANSFORM_EXPLORATORY_PROFILE_ADMISSIBLE"
        next_dependency = "FROZEN_FULL_ROUTE_RECONSTRUCTION_WITH_PROMOTED_PROFILE"
    elif promoted["exact_contact"]["point_accepted"]:
        decision = "PROMOTED_TRANSFORM_BLOCKED_VERTICAL_PROFILE"
        next_dependency = "SOURCE_BOUND_GEOMETRY_REVIEW"
    else:
        decision = "BOTH_SOURCE_BOUND_TRANSFORMS_BLOCK_EXACT_CONTACT"
        next_dependency = "SOURCE_BOUND_GEOMETRY_REVIEW"
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
        "promoted_profile": {
            "profile_id": profile.profile_id,
            "study_input_id": profile.study_input.study_input_id,
            "source_sha256": profile.source_sha256,
            "status": profile.status,
            "simulation_only": profile.simulation_only,
            "physical_release_effect": profile.physical_release_effect,
        },
        "tool_length_mm": tool_length_mm,
        "contact_point_board_mm": [contact.x, contact.y, contact.z],
        "profile_clearances_above_contact_mm": list(clearances),
        "cases": cases,
        "decision": decision,
        "next_dependency": next_dependency,
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
        "limitations": fixture["limitations"],
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_contact_transform_differential(
        args.fixture, workspace=args.workspace
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "case_decisions": {
                    case["case_id"]: case["decision"] for case in result["cases"]
                },
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
