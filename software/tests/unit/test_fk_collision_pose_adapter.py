from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.collision_readiness import assess_current_collision_readiness
from rocell.application._pinned_model import load_pinned_urdf
from rocell.application.context import load_simulation_context
from rocell.application.fk_collision_pose_adapter import (
    FkCollisionPoseAdapterError,
    MeasuredConfigurationGeometryBinding,
    MeasuredRigidAttachmentBinding,
    derive_and_evaluate_fk_waypoint_collisions,
)
from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentCollisionQualificationError,
    BoundedSegmentSamplingPolicy,
    MeasuredSegmentConfigurationSample,
    build_bounded_joint_sample_plan,
    qualify_bounded_segment_collisions,
)
from rocell.application.conservative_segment_sweep_qualification import (
    ConservativeSegmentSweepQualificationError,
    MeasuredConfigurationSweepEnvelopeBinding,
    qualify_conservative_segment_sweeps,
)
from rocell.application.installed_collision_geometry import (
    InstalledCollisionGeometryProfile,
)
from rocell.calibration import PlannerCalibrationSnapshot, required_planner_artifact_ids
from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.simulation.collision import (
    CapsuleMm,
    CollisionBindingMode,
    CollisionBody,
    CollisionClearanceEvidenceState,
    CollisionClearancePolicy,
    CollisionEvidenceState,
    CollisionGeometryContract,
    SampledCollisionGeometry,
    SphereMm,
)


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def snapshot(context) -> PlannerCalibrationSnapshot:
    scenario = context.scenario
    bounds = [
        scenario.controller_joint_intersection_rad[name] for name in ARM_JOINT_NAMES
    ]
    gripper = scenario.controller_gripper_intersection_rad
    return PlannerCalibrationSnapshot(
        device="keyboard",
        manifest_id=context.snapshot.manifest_id,
        active_build_id=context.snapshot.active_build_id,
        artifact_hashes={
            item: "a" * 64 for item in required_planner_artifact_ids("keyboard")
        },
        board_T_vendor_world=RigidTransform(
            "B",
            "Wv",
            scenario.board_T_world.rotation,
            scenario.board_T_world.translation_mm,
        ),
        board_T_device=RigidTransform(
            "B", "keyboard", Rotation3.identity(), Vec3(85.0, 85.0, 21.0)
        ),
        hand_T_tool=RigidTransform(
            "G",
            "T",
            Rotation3.identity(),
            Vec3(0.0, 0.0, scenario.hand_tcp_to_tip_z_mm),
        ),
        robot_reference_identity={
            "arm_identity_hash": "1" * 64,
            "controller_identity_hash": "2" * 64,
            "firmware_identity_hash": "3" * 64,
        },
        joint_zero_offsets_rad=(0.0,) * 6,
        joint_lower_rad=tuple(pair[0] for pair in bounds) + (gripper[0],),
        joint_upper_rad=tuple(pair[1] for pair in bounds) + (gripper[1],),
        joint_signs=(1,) * 6,
        controller_correlation={"model": "test"},
        target_map_sha256=context.targets.content_sha256,
    )


def profile(context) -> InstalledCollisionGeometryProfile:
    readiness = assess_current_collision_readiness(context)
    bodies = []
    for index, requirement in enumerate(readiness.contract.requirements):
        primitives = (
            ()
            if requirement.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
            else (SphereMm(Vec3(10_000.0 + index * 1_000.0, 0.0, 0.0), 0.1),)
        )
        bodies.append(
            CollisionBody(
                requirement.body_id,
                requirement.parent_frame,
                requirement.role,
                CollisionEvidenceState.ACCEPTED_MEASURED,
                primitives,
                requirement.binding_mode,
                "unit-test measured geometry",
            )
        )
    contract = CollisionGeometryContract(
        "fk-adapter-test",
        readiness.contract.root_frame,
        readiness.contract.requirements,
        tuple(bodies),
        readiness.contract.pair_exclusions,
    )
    clearance = CollisionClearancePolicy(
        0.1,
        0.05,
        0.05,
        CollisionClearanceEvidenceState.ACCEPTED_MEASURED,
        "unit-test measured clearance",
    )
    return InstalledCollisionGeometryProfile(
        "fk-adapter-profile",
        readiness.manifest_id,
        readiness.manifest_sha256,
        readiness.active_build_id,
        readiness.build_snapshot_hash,
        readiness.urdf_sha256,
        readiness.contract.content_hash,
        {"metrology": "4" * 64, "holder": "7" * 64, "camera": "8" * 64},
        contract,
        clearance,
        "5" * 64,
        "6" * 64,
    )


def trajectory(context, measured, installed, *, base_offset=0.0):
    joints = {
        name: context.scenario.ready_arm_joint_positions_rad[name].value
        for name in ARM_JOINT_NAMES
    }
    joints[ARM_JOINT_NAMES[0]] += base_offset
    waypoint = {"sequence": 0, "phase": "HOVER", "point_board": [1.0, 2.0, 3.0]}
    result = {
        "waypoint_sequence": 0,
        "accepted": True,
        "solution_arm_joint_positions_rad": joints,
    }
    report = {
        "schema": "rocell.measured_trajectory_screening.v2",
        "calibration_snapshot_sha256": measured.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "installed_collision_profile_sha256": installed.content_sha256,
        "collision_contract_sha256": installed.contract.content_hash,
        "ik_all_waypoints_accepted": True,
        "observed_start_joint_positions_rad": {
            name: context.scenario.ready_arm_joint_positions_rad[name].value
            for name in ARM_JOINT_NAMES
        },
        "waypoints": [waypoint],
        "joint_results": [result],
    }
    return {**report, "trajectory_screening_sha256": digest(report)}


def bindings():
    return (
        MeasuredRigidAttachmentBinding(
            "holder",
            "link2",
            RigidTransform(
                "link2", "holder", Rotation3.identity(), Vec3(1.0, 2.0, 3.0)
            ),
            "7" * 64,
            "measured holder transform",
        ),
        MeasuredRigidAttachmentBinding(
            "camera_module",
            "link2",
            RigidTransform(
                "link2",
                "camera_module",
                Rotation3.identity(),
                Vec3(4.0, 5.0, 6.0),
            ),
            "8" * 64,
            "measured camera transform",
        ),
    )


def cable(state=CollisionEvidenceState.ACCEPTED_MEASURED):
    return (
        {
            "attachment:moving_camera_cable": MeasuredConfigurationGeometryBinding(
                "attachment:moving_camera_cable",
                SampledCollisionGeometry(
                    (
                        CapsuleMm(
                            Vec3(50_000.0, 0.0, 0.0),
                            Vec3(50_010.0, 0.0, 0.0),
                            0.1,
                        ),
                    ),
                    state,
                    "configuration-correlated cable",
                ),
                "4" * 64,
            )
        },
    )


def test_robot_transforms_are_recomputed_and_discrete_gate_remains(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed)
    report = derive_and_evaluate_fk_waypoint_collisions(
        context, measured, installed, route, bindings(), cable()
    )

    assert report["status"] == "DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED"
    assert report["robot_link_transforms_recomputed_from_joint_results"] is True
    assert report["caller_robot_link_transform_overrides_accepted"] is False
    assert report["continuous_collision_proven"] is False
    assert report["hardware_commands_generated"] == 0
    pose = report["collision_sequence"]["pose_reports"][0]["sample"]["pose"]
    assert set(("base_link", "link1", "link2", "link3", "link4", "link5", "gripper_link", "hand_tcp")) <= set(pose["root_t_parent"])
    assert pose["root_t_parent"]["holder"]["child_frame"] == "holder"
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    ready = {
        name: context.scenario.ready_arm_joint_positions_rad[name]
        for name in ARM_JOINT_NAMES
    }
    ready["link5_to_gripper_link"] = JointPosition.radians(0.0)
    world_t_link2 = model.forward_kinematics(ready)["link2"]
    expected = RigidTransform(
        "board",
        "world",
        measured.board_T_vendor_world.rotation,
        measured.board_T_vendor_world.translation_mm,
    ).compose(world_t_link2)
    assert pose["root_t_parent"]["link2"]["translation_mm"] == [
        expected.translation_mm.x,
        expected.translation_mm.y,
        expected.translation_mm.z,
    ]
    assert report["derived_pose_records"][0]["attachment_binding_sha256_by_frame"] == {
        "camera_module": bindings()[1].content_sha256,
        "holder": bindings()[0].content_sha256,
    }
    schema = json.loads(
        (
            WORKSPACE
            / "software/ai/schemas/fk_derived_waypoint_collision_sequence_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(report)


def test_joint_change_changes_fk_pose_identity(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    first = derive_and_evaluate_fk_waypoint_collisions(
        context,
        measured,
        installed,
        trajectory(context, measured, installed),
        bindings(),
        cable(),
    )
    second = derive_and_evaluate_fk_waypoint_collisions(
        context,
        measured,
        installed,
        trajectory(context, measured, installed, base_offset=0.01),
        bindings(),
        cable(),
    )
    assert first["derived_pose_records"][0]["pose_sha256"] != second[
        "derived_pose_records"
    ][0]["pose_sha256"]


def test_attachment_coverage_and_override_attempts_reject(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed)
    with pytest.raises(FkCollisionPoseAdapterError, match="exactly cover"):
        derive_and_evaluate_fk_waypoint_collisions(
            context, measured, installed, route, bindings()[:1], cable()
        )
    override = MeasuredRigidAttachmentBinding(
        "link2",
        "link1",
        RigidTransform("link1", "link2", Rotation3.identity(), Vec3.zero()),
        "9" * 64,
        "invalid override",
    )
    with pytest.raises(FkCollisionPoseAdapterError, match="cannot override"):
        derive_and_evaluate_fk_waypoint_collisions(
            context, measured, installed, route, (*bindings(), override), cable()
        )


def test_non_measured_cable_and_crossed_calibration_reject(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed)
    with pytest.raises(FkCollisionPoseAdapterError, match="accepted measured"):
        derive_and_evaluate_fk_waypoint_collisions(
            context,
            measured,
            installed,
            route,
            bindings(),
            cable(CollisionEvidenceState.SYNTHETIC_TEST_ONLY),
        )
    unbound = replace(cable()[0]["attachment:moving_camera_cable"], source_sha256="f" * 64)
    with pytest.raises(FkCollisionPoseAdapterError, match="absent from installed profile"):
        derive_and_evaluate_fk_waypoint_collisions(
            context,
            measured,
            installed,
            route,
            bindings(),
            ({"attachment:moving_camera_cable": unbound},),
        )
    crossed = replace(measured, active_build_id="crossed")
    with pytest.raises(FkCollisionPoseAdapterError, match="lineage differ"):
        derive_and_evaluate_fk_waypoint_collisions(
            context, crossed, installed, route, bindings(), cable()
        )


def segment_cables(plan):
    return tuple(
        MeasuredSegmentConfigurationSample(
            item.sample_sequence, item.content_sha256, cable()[0]
        )
        for item in plan
    )


def test_bounded_segment_samples_recompute_fk_and_retain_sweep_gate(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed, base_offset=0.12)
    policy = BoundedSegmentSamplingPolicy(maximum_joint_step_rad=0.05)
    plan = build_bounded_joint_sample_plan(route, policy)

    assert len(plan) == 4
    assert plan[0].interpolation_ratio == 0.0
    assert plan[-1].interpolation_ratio == 1.0
    report = qualify_bounded_segment_collisions(
        context,
        measured,
        installed,
        route,
        bindings(),
        segment_cables(plan),
        policy=policy,
    )

    assert report["status"] == (
        "BOUNDED_SEGMENT_SAMPLES_CLEAR_CONSERVATIVE_SWEEP_REQUIRED"
    )
    assert report["sample_count"] == 4
    assert report["maximum_observed_joint_gap_rad"] <= 0.05
    assert report["all_bounded_samples_collision_free"] is True
    assert report["continuous_collision_proven"] is False
    assert report["controller_commands"] == []
    assert report["hardware_access"] is False
    assert len(report["fk_collision_qualification"]["derived_pose_records"]) == 4
    schema = json.loads(
        (
            WORKSPACE
            / "software/ai/schemas/bounded_segment_collision_qualification_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(report)


def test_bounded_segment_geometry_must_bind_exact_sample(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed, base_offset=0.08)
    plan = build_bounded_joint_sample_plan(route)
    evidence = list(segment_cables(plan))
    evidence[1] = replace(evidence[1], sample_plan_sha256="f" * 64)

    with pytest.raises(
        BoundedSegmentCollisionQualificationError, match="does not bind"
    ):
        qualify_bounded_segment_collisions(
            context, measured, installed, route, bindings(), evidence
        )


def test_bounded_segment_rejects_missing_start_and_resource_exhaustion(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed, base_offset=0.12)
    missing = dict(route)
    missing.pop("trajectory_screening_sha256")
    missing.pop("observed_start_joint_positions_rad")
    missing = {**missing, "trajectory_screening_sha256": digest(missing)}
    with pytest.raises(
        BoundedSegmentCollisionQualificationError, match="observed start"
    ):
        build_bounded_joint_sample_plan(missing)

    with pytest.raises(
        BoundedSegmentCollisionQualificationError, match="exceeds policy maximum"
    ):
        build_bounded_joint_sample_plan(
            route,
            BoundedSegmentSamplingPolicy(
                maximum_joint_step_rad=0.01, maximum_samples=2
            ),
        )


def sweep_envelopes(plan, *, colliding=False):
    result = []
    for sequence, (start, end) in enumerate(zip(plan, plan[1:])):
        primitives = (
            (SphereMm(Vec3.zero(), 1_000_000.0),)
            if colliding
            else (
                CapsuleMm(
                    Vec3(50_000.0, 0.0, 0.0),
                    Vec3(50_010.0, 0.0, 0.0),
                    0.1,
                ),
            )
        )
        result.append(
            {
                "attachment:moving_camera_cable": (
                    MeasuredConfigurationSweepEnvelopeBinding(
                        sequence,
                        start.content_sha256,
                        end.content_sha256,
                        "attachment:moving_camera_cable",
                        SampledCollisionGeometry(
                            primitives,
                            CollisionEvidenceState.ACCEPTED_MEASURED,
                            "measured conservative cable envelope",
                        ),
                        "4" * 64,
                    )
                )
            }
        )
    return tuple(result)


def test_conservative_segment_sweeps_clear_bound_geometry(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed, base_offset=0.001)
    policy = BoundedSegmentSamplingPolicy(maximum_joint_step_rad=0.05)
    plan = build_bounded_joint_sample_plan(route, policy)
    report = qualify_conservative_segment_sweeps(
        context,
        measured,
        installed,
        route,
        bindings(),
        segment_cables(plan),
        sweep_envelopes(plan),
        sampling_policy=policy,
    )

    assert report["status"] == "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"
    assert report["segment_count"] == len(plan) - 1
    assert report["all_conservative_segment_sweeps_clear"] is True
    assert report["all_pair_exclusions_physically_accepted"] is False
    assert report["continuous_collision_proven_for_bound_geometry"] is False
    assert "ACCEPTED_GLOBAL_PAIR_EXCLUSIONS_REQUIRED" in report["blockers"]
    assert report["physical_authority"] is False
    assert report["controller_commands"] == []
    assert all(
        item["collision_free_diagnostic"] for item in report["segment_reports"]
    )
    assert report["all_segment_clearance_bounds_determinate"] is True
    assert report["minimum_clearance_lower_bound_mm"] > 0.0
    assert report["limiting_segment_sequence"] == 0
    assert len(report["limiting_body_pair"]) == 2
    assert all(
        item["clearance_lower_bound_status"] == "CLEAR"
        and item["minimum_clearance_lower_bound_mm"] > 0.0
        and len(item["clearance_limiting_body_pair"]) == 2
        for item in report["segment_reports"]
    )
    schema = json.loads(
        (
            WORKSPACE
            / "software/ai/schemas/conservative_segment_sweep_qualification_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(report)


def test_conservative_segment_sweep_detects_envelope_collision(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed, base_offset=0.04)
    plan = build_bounded_joint_sample_plan(route)
    report = qualify_conservative_segment_sweeps(
        context,
        measured,
        installed,
        route,
        bindings(),
        segment_cables(plan),
        sweep_envelopes(plan, colliding=True),
    )

    assert report["status"] == "BLOCKED_CONSERVATIVE_SWEEP_COLLISION"
    assert report["all_conservative_segment_sweeps_clear"] is False
    assert report["continuous_collision_proven_for_bound_geometry"] is False
    assert report["minimum_clearance_lower_bound_mm"] == 0.0
    assert any(
        item["clearance_lower_bound_status"] == "COLLISION"
        for item in report["segment_reports"]
    )


def test_conservative_segment_sweep_rejects_crossed_envelope(context) -> None:
    measured = snapshot(context)
    installed = profile(context)
    route = trajectory(context, measured, installed, base_offset=0.08)
    plan = build_bounded_joint_sample_plan(route)
    envelope_sets = list(sweep_envelopes(plan))
    body_id = "attachment:moving_camera_cable"
    crossed = replace(
        envelope_sets[0][body_id], end_sample_sha256="f" * 64
    )
    envelope_sets[0] = {body_id: crossed}

    with pytest.raises(
        ConservativeSegmentSweepQualificationError, match="does not bind"
    ):
        qualify_conservative_segment_sweeps(
            context,
            measured,
            installed,
            route,
            bindings(),
            segment_cables(plan),
            envelope_sets,
        )
