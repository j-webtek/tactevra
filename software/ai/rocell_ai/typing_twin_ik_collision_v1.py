"""CPU-only bridge from the main-bound typing twin to IK and collision intake.

The installed collision profile remains mandatory.  A separately labelled
origin-sphere candidate model is evaluated only as an exploratory diagnostic;
it cannot satisfy or replace installed measured geometry.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Mapping

from rocell.application._pinned_model import load_pinned_urdf
from rocell.application.context import load_simulation_context
from rocell.application.typing_collision_intake_v1 import (
    PROFILE_REQUIRED_STATUS,
    prepare_typing_collision_intake_v1,
)
from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    READY_STATUS as IK_READY_STATUS,
    TypingTrajectoryIkSeedV1,
    screen_typing_trajectory_ik_v1,
)
from rocell.application.typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from rocell.application.trajectory_simulation import TrajectorySimulationPolicy
from rocell.calibration import PlannerCalibrationSnapshot, required_planner_artifact_ids
from rocell.geometry import (
    JointPosition,
    Point3Mm as GeometryPoint3Mm,
    RigidTransform,
    Rotation3,
    Vec3,
)
from rocell.kinematics import (
    ARM_JOINT_NAMES,
    BoardToolTipTarget,
    IkOptions,
    RoArmM3NumericalIk,
)
from rocell.models import Point3Mm, SpeedClass, decode_model_motion_batch_v2_json
from rocell.simulation.collision import (
    CapsuleMm,
    CollisionBindingMode,
    CollisionBody,
    CollisionBodyRequirement,
    CollisionBodyRole,
    CollisionClearanceEvidenceState,
    CollisionClearancePolicy,
    CollisionEvaluationPolicy,
    CollisionEvidenceState,
    CollisionExclusionEvidenceState,
    CollisionExclusionScope,
    CollisionGeometryContract,
    CollisionPairExclusion,
    CollisionPose,
    SphereMm,
    audit_collision_geometry,
    build_roarm_m3_prehardware_collision_contract,
    evaluate_collision_pose,
)

from .actual_output_compatibility_v1 import (
    _plan,
    _registry_for_batch,
    build_actual_emitter_payload,
)
from rocell.application.model_motion_registry_v2 import (
    ingest_with_trusted_registry_v2,
    revalidate_with_trusted_registry_v2,
)


SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
SCHEMA = "tactevra.typing_twin_ik_collision_receipt.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("IK/collision fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != "tactevra.typing_twin_ik_collision_fixture.v1":
        raise ValueError("unexpected IK/collision fixture schema")
    if document.get("scope") != SCOPE or any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _synthetic_snapshot(context: Any) -> PlannerCalibrationSnapshot:
    scenario = context.scenario
    bounds = [scenario.controller_joint_intersection_rad[name]
              for name in ARM_JOINT_NAMES]
    gripper = scenario.controller_gripper_intersection_rad
    return PlannerCalibrationSnapshot(
        device="keyboard",
        manifest_id=context.snapshot.manifest_id,
        active_build_id=context.snapshot.active_build_id,
        artifact_hashes={item: "a" * 64
                         for item in required_planner_artifact_ids("keyboard")},
        board_T_vendor_world=RigidTransform(
            "B", "Wv", scenario.board_T_world.rotation,
            scenario.board_T_world.translation_mm),
        board_T_device=RigidTransform(
            "B", "keyboard", Rotation3.identity(), Vec3(85.0, 85.0, 21.0)),
        hand_T_tool=RigidTransform(
            "G", "T", Rotation3.identity(),
            Vec3(0.0, 0.0, scenario.hand_tcp_to_tip_z_mm)),
        robot_reference_identity={
            "arm_identity_hash": "1" * 64,
            "controller_identity_hash": "2" * 64,
            "firmware_identity_hash": "3" * 64,
        },
        joint_zero_offsets_rad=(0.0,) * 6,
        joint_lower_rad=tuple(pair[0] for pair in bounds) + (gripper[0],),
        joint_upper_rad=tuple(pair[1] for pair in bounds) + (gripper[1],),
        joint_signs=(1,) * 6,
        controller_correlation={"model": "synthetic-offline-test"},
        target_map_sha256=context.targets.content_sha256,
    )


def _synthetic_ready_tip(context: Any,
                         snapshot: PlannerCalibrationSnapshot) -> GeometryPoint3Mm:
    """Derive the route origin from the exact seed and pinned kinematic model."""
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256).model
    bounds = {name: context.scenario.controller_joint_intersection_rad[name]
              for name in ARM_JOINT_NAMES}
    solver = RoArmM3NumericalIk(
        model=model,
        board_T_world=RigidTransform(
            "board", "world", snapshot.board_T_vendor_world.rotation,
            snapshot.board_T_vendor_world.translation_mm),
        hand_tcp_to_tip_z_mm=snapshot.hand_T_tool.translation_mm.z,
        fixed_gripper_position=context.scenario.fixed_gripper_position,
        ready_arm_joint_positions=context.scenario.ready_arm_joint_positions_rad,
        gripper_bounds_rad=context.scenario.controller_gripper_intersection_rad,
        options=IkOptions(), joint_bounds_rad=bounds)
    seed = {name: JointPosition.radians(
        context.scenario.ready_arm_joint_positions_rad[name].value)
        for name in ARM_JOINT_NAMES}
    return solver.evaluate(
        BoardToolTipTarget(GeometryPoint3Mm("board", 0.0, 0.0, 0.0)),
        seed).tip_position_board_mm


def _candidate_contract(context: Any, model: Any, *, link_radius_mm: float,
                        tool_length_mm: float, tip_radius_mm: float) -> CollisionGeometryContract:
    base = build_roarm_m3_prehardware_collision_contract(model, context.scene)
    robot_requirements = [item for item in base.requirements
                          if item.role is CollisionBodyRole.ROBOT_LINK]
    bodies = [
        CollisionBody(
            item.body_id, item.parent_frame, item.role,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (SphereMm(Vec3.zero(), link_radius_mm),),
            CollisionBindingMode.RIGID_FRAME,
            "declared origin-sphere range; not a link envelope",
        ) for item in robot_requirements
    ]
    tool_requirement = CollisionBodyRequirement(
        "attachment:contact_tool", "hand_tcp", CollisionBodyRole.TOOL,
        CollisionBindingMode.RIGID_FRAME,
        "passive stylus candidate only")
    bodies.append(CollisionBody(
        tool_requirement.body_id, tool_requirement.parent_frame,
        tool_requirement.role, CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
        (CapsuleMm(Vec3.zero(), Vec3(0.0, 0.0, -tool_length_mm),
                   tip_radius_mm),),
        CollisionBindingMode.RIGID_FRAME,
        "declared passive-stylus length/radius range; not installed geometry"))
    static_requirements = [item for item in base.requirements
                           if item.role is CollisionBodyRole.STATIC_ENVIRONMENT]
    static_ids = {item.body_id for item in static_requirements}
    bodies.extend(item for item in base.bodies if item.body_id in static_ids)
    present = {item.body_id for item in bodies}
    exclusions = [item for item in base.pair_exclusions
                  if set(item.pair) <= present]
    hand_body = next((item.body_id for item in robot_requirements
                      if item.parent_frame == "hand_tcp"), None)
    if hand_body is not None:
        exclusions.append(CollisionPairExclusion(
            hand_body, tool_requirement.body_id,
            CollisionExclusionScope.SYNTHETIC_TEST_ONLY,
            CollisionExclusionEvidenceState.SYNTHETIC_TEST_ONLY,
            "synthetic tool is rigidly attached at hand_tcp",
            "exploratory candidate fixture"))
    return CollisionGeometryContract(
        contract_id=(f"TYPING-TWIN-ORIGIN-SPHERE-R{link_radius_mm:g}-"
                     f"L{tool_length_mm:g}-T{tip_radius_mm:g}"),
        root_frame="board",
        requirements=tuple([*robot_requirements, tool_requirement,
                            *static_requirements]),
        bodies=tuple(bodies), pair_exclusions=tuple(exclusions))


def _pose_for_result(context: Any, snapshot: PlannerCalibrationSnapshot,
                     model: Any, contract: CollisionGeometryContract,
                     index: int, result: Mapping[str, Any]) -> CollisionPose:
    solution = result["solution_arm_joint_positions_rad"]
    joints = {name: JointPosition.radians(float(solution[name]))
              for name in ARM_JOINT_NAMES}
    non_arm = set(model.movable_joint_names) - set(ARM_JOINT_NAMES)
    if len(non_arm) != 1:
        raise ValueError("pinned URDF must expose one movable gripper joint")
    joints[next(iter(non_arm))] = context.scenario.fixed_gripper_position
    world = model.forward_kinematics(joints)
    board_t_world = RigidTransform(
        "board", model.root_link, snapshot.board_T_vendor_world.rotation,
        snapshot.board_T_vendor_world.translation_mm)
    required_frames = {body.parent_frame for body in contract.bodies
                       if body.binding_mode is CollisionBindingMode.RIGID_FRAME}
    transforms = {frame: board_t_world.compose(world[frame])
                  for frame in required_frames}
    return CollisionPose(f"typing-sample-{index:04d}", "board", transforms)


def _candidate_diagnostic(fixture: Mapping[str, Any], context: Any,
                          snapshot: PlannerCalibrationSnapshot,
                          ik: Mapping[str, Any]) -> dict[str, Any]:
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256).model
    ranges = fixture["candidate_collision_ranges"]
    axes = (ranges["link_origin_sphere_radius_mm"],
            ranges["tool_length_mm"], ranges["tip_radius_mm"],
            ranges["minimum_separation_mm"],
            ranges["geometry_uncertainty_mm_per_body"],
            ranges["pose_uncertainty_mm_per_body"])
    profiles = []
    for values in itertools.product(*axes):
        link_radius, tool_length, tip_radius, separation, geometry_u, pose_u = values
        contract = _candidate_contract(
            context, model, link_radius_mm=link_radius,
            tool_length_mm=tool_length, tip_radius_mm=tip_radius)
        audit = audit_collision_geometry(contract)
        policy = CollisionEvaluationPolicy(clearance_policy=CollisionClearancePolicy(
            minimum_separation_mm=separation,
            geometry_uncertainty_mm_per_body=geometry_u,
            pose_uncertainty_mm_per_body=pose_u,
            evidence_state=CollisionClearanceEvidenceState.SYNTHETIC_TEST_ONLY,
            source_reference="declared exploratory range endpoints"))
        pair_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for index, result in enumerate(ik["joint_results"]):
            evaluated = evaluate_collision_pose(
                contract,
                _pose_for_result(context, snapshot, model, contract, index, result),
                policy)
            status_counts[evaluated.status.value] = (
                status_counts.get(evaluated.status.value, 0) + 1)
            for collision in evaluated.collisions:
                pair = "/".join(
                    (collision.first_body_id, collision.second_body_id)
                )
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
        profile = {
            "parameters": {
                "link_origin_sphere_radius_mm": link_radius,
                "tool_length_mm": tool_length,
                "tip_radius_mm": tip_radius,
                "minimum_separation_mm": separation,
                "geometry_uncertainty_mm_per_body": geometry_u,
                "pose_uncertainty_mm_per_body": pose_u,
            },
            "contract_sha256": contract.content_hash,
            "diagnostic_ready": audit.diagnostic_ready,
            "physical_geometry_complete": audit.physical_geometry_complete,
            "sample_count": len(ik["joint_results"]),
            "status_counts": status_counts,
            "collision_pair_counts": dict(sorted(pair_counts.items())),
            "collision_sample_count": status_counts.get("COLLISION_DETECTED", 0),
        }
        profile["profile_receipt_sha256"] = _sha(profile)
        profiles.append(profile)
    return {
        "classification": "EXPLORATORY_INCOMPLETE_CANDIDATE_DIAGNOSTIC",
        "profile_count": len(profiles),
        "profiles": profiles,
        "modeled_body_scope": (
            "URDF link-origin spheres, passive stylus capsule, and pinned nominal "
            "workcell AABBs only"),
        "unmodeled_installed_bodies": [
            "base_and_factory_clamp", "camera_holder", "camera_module",
            "camera_connector"],
        "moving_cable_present": False,
        "can_clear_installed_collision_gate": False,
    }


def run_typing_ik_collision(fixture_path: Path, *, workspace: Path) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    case = fixture["case"]
    targets = tuple(case["expected_targets"])
    payload = build_actual_emitter_payload(
        workspace, text=case["text"], targets=targets,
        batch_id=case["batch_id"], request_id=case["request_id"])
    batch = decode_model_motion_batch_v2_json(payload)
    plan = _plan(case["text"], targets)
    registry = _registry_for_batch(context, batch)
    ingress = ingest_with_trusted_registry_v2(
        batch, plan, context, registry=registry,
        current_time_epoch_ms=batch.evidence.evaluated_at_epoch_ms,
        current_monotonic_ns=9_000_000_000)
    fresh = revalidate_with_trusted_registry_v2(
        ingress, registry=registry, current_monotonic_ns=10_000_000_000)
    snapshot = _synthetic_snapshot(context)
    route = fixture["route"]
    if route.get("route_reference_point_mode") == "SYNTHETIC_READY_TIP":
        ready_tip = _synthetic_ready_tip(context, snapshot)
        route_reference = Point3Mm("board", ready_tip.x, ready_tip.y, ready_tip.z)
    elif route.get("route_reference_point_mode") == "FIXED_BOARD_POINT":
        route_reference = Point3Mm("board", *route["route_reference_point_mm"])
    else:
        raise ValueError("unsupported route_reference_point_mode")
    execution = compile_typing_execution_plan_v1(
        batch, ingress,
        config=TypingExecutionConfigV1(
            config_id=route["config_id"],
            calibration_snapshot_sha256=snapshot.snapshot_sha256,
            tool_profile_sha256=route["tool_profile_sha256"],
            dynamics_profile_sha256=route["dynamics_profile_sha256"],
            route_reference_point=route_reference,
            hover_clearance_mm=route["hover_clearance_mm"],
            settle_position_tolerance_mm=route["settle_position_tolerance_mm"],
            settle_velocity_tolerance_mm_s=route["settle_velocity_tolerance_mm_s"],
            settle_hold_ms=route["settle_hold_ms"], preview_horizon=1,
            speed_class=SpeedClass.SLOW))
    trajectory = compile_typing_trajectory_plan_v1(
        execution, policy=TypingTrajectoryPolicyV1(
            policy_id=route["trajectory_policy_id"],
            maximum_cartesian_step_mm=route["maximum_cartesian_step_mm"],
            maximum_velocity_mm_s=route["maximum_velocity_mm_s"],
            maximum_acceleration_mm_s2=route["maximum_acceleration_mm_s2"],
            maximum_jerk_mm_s3=route["maximum_jerk_mm_s3"],
            hover_settle_ms=route["hover_settle_ms"],
            contact_dwell_ms=route["contact_dwell_ms"]))
    seed = TypingTrajectoryIkSeedV1(
        seed_id="typing-twin-synthetic-ready-v1",
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        build_snapshot_sha256=context.snapshot.snapshot_hash,
        joint_positions_rad={name: context.scenario.ready_arm_joint_positions_rad[name].value
                             for name in ARM_JOINT_NAMES})
    ik = screen_typing_trajectory_ik_v1(
        execution, trajectory, context, snapshot, seed,
        policy=TrajectorySimulationPolicy(
            maximum_cartesian_step_mm=route["maximum_cartesian_step_mm"],
            maximum_refinement_rounds=0,
            maximum_waypoints_per_round=fixture["resource_limits"]["maximum_ik_samples"],
            maximum_total_ik_solves=fixture["resource_limits"]["maximum_ik_samples"],
            maximum_route_targets=len(targets)))
    ik_ready = ik["status"] == IK_READY_STATUS
    if ik_ready:
        intake = prepare_typing_collision_intake_v1(
            execution, trajectory, ik, context, snapshot, installed_profile=None)
        if intake["status"] != PROFILE_REQUIRED_STATUS:
            raise ValueError("installed collision intake did not remain fail closed")
        diagnostic_input = ik
        decision = "PASS_IK_RETAIN_INSTALLED_COLLISION_BLOCKER"
    else:
        accepted_prefix = []
        for result in ik["joint_results"]:
            if result["accepted"] is not True:
                break
            accepted_prefix.append(result)
        if not accepted_prefix:
            raise ValueError("canonical IK blocked before any candidate prefix existed")
        intake = {
            "status": "NOT_REACHED_CANONICAL_IK_BLOCKED",
            "blockers": [
                *ik["blockers"],
                "INSTALLED_COLLISION_PROFILE_REQUIRED_DOWNSTREAM",
                "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
            ],
            "installed_geometry_collision_screening_executed": False,
            "continuous_collision_proven": False,
            "physical_authority": False,
        }
        diagnostic_input = {**ik, "joint_results": accepted_prefix}
        decision = "BLOCKED_CANONICAL_IK_PREFIX_DIAGNOSTIC_ONLY"
    diagnostic = _candidate_diagnostic(
        fixture, context, snapshot, diagnostic_input)
    if diagnostic["profile_count"] != fixture["resource_limits"][
            "expected_candidate_profile_count"]:
        raise ValueError("candidate diagnostic profile count differs from fixture")
    core = {
        "schema": SCHEMA, "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "ordered_targets": list(targets),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": fresh["preplanner_gate_sha256"],
        "execution_plan_sha256": execution.plan_sha256,
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "trajectory_sample_count": len(trajectory.screening_samples),
        "ik_screen": ik,
        "installed_collision_intake": intake,
        "candidate_collision_diagnostic": diagnostic,
        "canonical_ik_route_accepted": ik_ready,
        "candidate_diagnostic_sample_scope": (
            "FULL_ROUTE" if ik_ready else "ACCEPTED_PREFIX_ONLY"),
        "installed_collision_gate_cleared": False,
        "controller_commands": [], "hardware_commands_generated": 0,
        "hardware_access": False, "hardware_writes": 0,
        "physical_movements": 0, "physical_authority": False,
        "decision": decision,
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_typing_ik_collision(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"decision": result["decision"],
                      "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
