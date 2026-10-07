"""Reconstruct the ordered typing route for the exact C03 tool and target catalog."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Mapping

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
from rocell.geometry import RigidTransform, Rotation3, Vec3
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.models import Point3Mm, SpeedClass, decode_model_motion_batch_v2_json
from rocell.targets.nominal import load_nominal_target_catalog
from rocell.workcell.alignment import validate_placemat_alignment

from .actual_output_compatibility_v1 import (
    _baseline_parts,
    _plan,
    _registry_for_batch,
)
from .batch_emitter_v2 import TargetObservationV2, assemble
from .c03_arm_route_reconciliation_v1 import (
    canonical_hash,
    file_hash,
    load_strict_json,
)
from .typing_twin_ik_collision_v1 import _synthetic_ready_tip, _synthetic_snapshot
from .typing_twin_promoted_full_route_v1 import _load_fixture as load_parent_fixture


FIXTURE_SCHEMA = "tactevra.c03_exact_route_reconstruction_fixture.v1"
RESULT_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def _resolve(path_text: str, workspace: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else workspace / path


def _verify_receipt(document: Mapping[str, Any], expected: str, name: str) -> None:
    claimed = document.get("receipt_sha256")
    if claimed != expected or canonical_hash(
        {key: value for key, value in document.items() if key != "receipt_sha256"}
    ) != claimed:
        raise ValueError(f"{name} receipt changed")


def load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    fixture = load_strict_json(path)
    claimed = fixture.pop("fixture_sha256", None)
    if claimed != canonical_hash(fixture):
        raise ValueError("C03 exact-route fixture hash changed")
    fixture["fixture_sha256"] = claimed
    if fixture.get("schema") != FIXTURE_SCHEMA or fixture.get("scope") != SCOPE:
        raise ValueError("unexpected C03 exact-route fixture identity")
    if fixture.get("physical_authority") is not False or any(
        fixture["counters"].values()
    ):
        raise ValueError("C03 exact-route fixture violates zero authority")
    for name, binding in fixture["bindings"].items():
        source = _resolve(binding["path"], workspace)
        if not source.is_file() or file_hash(source) != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {name}")
    return fixture


def _bound_document(
    fixture: Mapping[str, Any], name: str, workspace: Path
) -> dict[str, Any]:
    binding = fixture["bindings"][name]
    document = load_strict_json(_resolve(binding["path"], workspace))
    if document.get("schema") != binding["schema"]:
        raise ValueError(f"bound source schema changed: {name}")
    if "receipt_sha256" in binding:
        _verify_receipt(document, binding["receipt_sha256"], name)
    return document


def _selected_pose_bundle(
    pose_family: Mapping[str, Any], tool_configuration_sha256: str
) -> dict[str, Any]:
    matches = [
        profile for profile in pose_family["profiles"]
        if profile["tool_configuration_sha256"] == tool_configuration_sha256
    ]
    if len(matches) != 1:
        raise ValueError("selected C03 pose profile is not unique")
    return matches[0]["pose_bundle"]


def run_c03_exact_route(fixture_path: Path, *, workspace: Path) -> dict[str, Any]:
    fixture = load_fixture(fixture_path, workspace)
    parent_binding = fixture["bindings"]["parent_route_fixture"]
    parent = load_parent_fixture(
        _resolve(parent_binding["path"], workspace), workspace
    )
    if parent["fixture_sha256"] != fixture["parent_fixture_sha256"]:
        raise ValueError("parent route fixture identity changed")

    recipe = _bound_document(fixture, "c03_recipe_envelope", workspace)
    pose_family = _bound_document(fixture, "c03_pose_family", workspace)
    if recipe["decision"] != "PASS_EXPLORATORY_WS2_RECIPE_ENVELOPE":
        raise ValueError("C03 recipe is not admitted")
    expected_tool = fixture["c03_tool"]
    if recipe["tool_length_mm"] != expected_tool["total_length_mm"]:
        raise ValueError("C03 tool length changed")
    if recipe["tool_geometry"] != expected_tool["geometry"]:
        raise ValueError("C03 tool geometry changed")
    pose_bundle = _selected_pose_bundle(
        pose_family, expected_tool["tool_configuration_sha256"]
    )
    configuration = pose_bundle["tool_configuration"]
    if (
        configuration["total_hand_tcp_to_tip_length_mm"]
        != expected_tool["total_length_mm"]
        or configuration["distal_tip_exposed_length_mm"]
        != expected_tool["geometry"]["exposed_length_mm"]
        or configuration["distal_tip_radius_mm"]
        != expected_tool["geometry"]["radius_mm"]
    ):
        raise ValueError("selected C03 pose configuration changed")

    base_context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json"
    )
    catalog_path = _resolve(
        fixture["bindings"]["c03_candidate_target_catalog"]["path"], workspace
    )
    candidate_targets = load_nominal_target_catalog(workspace, catalog_path)
    if candidate_targets.content_sha256 != configuration["target_catalog_sha256"]:
        raise ValueError("C03 pose and candidate target catalog differ")
    candidate_alignment = validate_placemat_alignment(
        base_context.hardware_profile,
        base_context.scenario,
        base_context.scene,
        candidate_targets,
    )
    context = replace(
        base_context, targets=candidate_targets, alignment=candidate_alignment
    )

    route_order = tuple(fixture["route"]["ordered_targets"])
    text = fixture["route"]["text"]
    parts = _baseline_parts(context, route_order)
    observations = {
        target_id: TargetObservationV2(
            context.targets.resolve("keyboard", target_id).center, 0.93
        )
        for target_id in dict.fromkeys(route_order)
    }
    payload = assemble(
        _plan(text, route_order),
        batch_id=fixture["route"]["batch_id"],
        request_id=fixture["route"]["request_id"],
        observations=observations,
        **parts,
    )
    if payload is None:
        raise ValueError("C03 candidate batch assembler abstained")
    batch = decode_model_motion_batch_v2_json(payload)
    registry = _registry_for_batch(context, batch)
    plan = _plan(text, route_order)
    ingress = ingest_with_trusted_registry_v2(
        batch,
        plan,
        context,
        registry=registry,
        current_time_epoch_ms=batch.evidence.evaluated_at_epoch_ms,
        current_monotonic_ns=9_000_000_000,
    )
    fresh = revalidate_with_trusted_registry_v2(
        ingress, registry=registry, current_monotonic_ns=10_000_000_000
    )

    promoted_profile = parent["promoted_profile"]
    from rocell.simulation.virtual_profile import load_virtual_commissioning_profile

    profile = load_virtual_commissioning_profile(base_context)
    if (
        profile.profile_id != promoted_profile["profile_id"]
        or profile.study_input.study_input_id != promoted_profile["study_input_id"]
        or profile.source_sha256 != promoted_profile["source_sha256"]
    ):
        raise ValueError("promoted placement profile changed")
    tool_length = float(expected_tool["total_length_mm"])
    snapshot = replace(
        _synthetic_snapshot(context),
        board_T_vendor_world=profile.study_input.board_T_vendor_world,
        hand_T_tool=RigidTransform(
            "G", "T", Rotation3.identity(), Vec3(0.0, 0.0, -tool_length)
        ),
    )
    ready_tip = _synthetic_ready_tip(context, snapshot)
    route_policy = parent["route"]
    execution = compile_typing_execution_plan_v1(
        batch,
        ingress,
        config=TypingExecutionConfigV1(
            config_id=fixture["route"]["config_id"],
            calibration_snapshot_sha256=snapshot.snapshot_sha256,
            tool_profile_sha256=expected_tool["tool_configuration_sha256"],
            dynamics_profile_sha256=route_policy["dynamics_profile_sha256"],
            route_reference_point=Point3Mm(
                "board", ready_tip.x, ready_tip.y, ready_tip.z
            ),
            hover_clearance_mm=float(fixture["route"]["hover_clearance_mm"]),
            settle_position_tolerance_mm=route_policy[
                "settle_position_tolerance_mm"
            ],
            settle_velocity_tolerance_mm_s=route_policy[
                "settle_velocity_tolerance_mm_s"
            ],
            settle_hold_ms=route_policy["settle_hold_ms"],
            preview_horizon=1,
            speed_class=SpeedClass.SLOW,
        ),
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution,
        policy=TypingTrajectoryPolicyV1(
            policy_id=fixture["route"]["trajectory_policy_id"],
            maximum_cartesian_step_mm=route_policy["maximum_cartesian_step_mm"],
            maximum_velocity_mm_s=route_policy["maximum_velocity_mm_s"],
            maximum_acceleration_mm_s2=route_policy["maximum_acceleration_mm_s2"],
            maximum_jerk_mm_s3=route_policy["maximum_jerk_mm_s3"],
            hover_settle_ms=route_policy["hover_settle_ms"],
            contact_dwell_ms=route_policy["contact_dwell_ms"],
        ),
    )
    if [action.target_id for action in execution.actions] != list(route_order):
        raise ValueError("C03 route changed semantic target order")
    pose_by_target = {
        pose["target_id"]: pose for pose in pose_bundle["poses"]
    }
    for target_id in dict.fromkeys(route_order):
        center = context.targets.resolve("keyboard", target_id).center
        expected_center = pose_by_target[target_id]["contact_target_board_mm"]
        if any(
            abs(actual - expected_center[axis]) > 1e-9
            for actual, axis in zip(
                (center.x, center.y, center.z), ("x", "y", "z"), strict=True
            )
        ):
            raise ValueError(f"C03 pose and route target differ: {target_id}")

    seed = TypingTrajectoryIkSeedV1(
        seed_id="c03-110mm-candidate-catalog-synthetic-ready-v1",
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        build_snapshot_sha256=context.snapshot.snapshot_hash,
        joint_positions_rad={
            name: context.scenario.ready_arm_joint_positions_rad[name].value
            for name in ARM_JOINT_NAMES
        },
    )
    maximum_samples = fixture["resource_limits"]["maximum_ik_samples"]
    ik = screen_typing_trajectory_ik_v1(
        execution,
        trajectory,
        context,
        snapshot,
        seed,
        policy=TrajectorySimulationPolicy(
            maximum_cartesian_step_mm=route_policy["maximum_cartesian_step_mm"],
            maximum_refinement_rounds=0,
            maximum_waypoints_per_round=maximum_samples,
            maximum_total_ik_solves=maximum_samples,
            maximum_route_targets=len(route_order),
        ),
    )
    accepted = [item for item in ik["joint_results"] if item["accepted"]]
    route_accepted = ik["status"] == READY_STATUS
    decision = (
        "PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY"
        if route_accepted
        else "BLOCKED_C03_110MM_CANDIDATE_ROUTE_IK_OR_CONTINUITY"
    )
    core = {
        "schema": RESULT_SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "parent_fixture_sha256": parent["fixture_sha256"],
        "recipe_receipt_sha256": recipe["receipt_sha256"],
        "pose_family_receipt_sha256": pose_family["receipt_sha256"],
        "tool_configuration_sha256": expected_tool["tool_configuration_sha256"],
        "tool_total_length_mm": tool_length,
        "target_catalog_sha256": candidate_targets.content_sha256,
        "ordered_targets": list(route_order),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": fresh["preplanner_gate_sha256"],
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "execution_plan_sha256": execution.plan_sha256,
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "trajectory_sample_count": len(trajectory.screening_samples),
        "ik_screen": ik,
        "ik_accepted_sample_count": len(accepted),
        "minimum_normalized_arm_joint_margin": (
            min(item["minimum_normalized_arm_joint_margin"] for item in accepted)
            if accepted else None
        ),
        "maximum_adjacent_joint_delta_rad": (
            max(item["maximum_joint_delta_rad"] for item in accepted)
            if accepted else None
        ),
        "canonical_ik_route_accepted": route_accepted,
        "canonical_joint_continuity_accepted": route_accepted,
        "collision_screen_executed": False,
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
    return {**core, "receipt_sha256": canonical_hash(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_c03_exact_route(args.fixture, workspace=args.workspace.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "decision": result["decision"],
        "trajectory_sample_count": result["trajectory_sample_count"],
        "ik_accepted_sample_count": result["ik_accepted_sample_count"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
