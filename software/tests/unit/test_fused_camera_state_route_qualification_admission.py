from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rocell.application import fused_camera_state_route_qualification_admission as subject
from rocell.application.fixed_camera_keyboard_profiled_collision_partitions_v1 import (
    SCHEMA as PARTITIONS_SCHEMA,
    STATUS as PARTITIONS_STATUS,
    ZERO_AUTHORITY as PARTITIONS_ZERO_AUTHORITY,
)
from rocell.application.fixed_camera_keyboard_profiled_route_screen_v1 import (
    SCHEMA as ROUTE_SCREEN_SCHEMA,
    STATUS as ROUTE_SCREEN_STATUS,
    ZERO_AUTHORITY as ROUTE_SCREEN_ZERO_AUTHORITY,
)
from rocell.application.fixed_camera_keyboard_route_bound_collision_qualification_v1 import (
    SCHEMA as ROUTE_BOUND_SCHEMA,
    STATUS_READY as ROUTE_BOUND_READY,
    ZERO_AUTHORITY as ROUTE_BOUND_ZERO_AUTHORITY,
)
from rocell.application.fused_camera_state_planning_admission import (
    PLANNING_ADMISSION_RECEIPT_SCHEMA,
)
from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from rocell.models import (
    Interaction,
    ModelMotionBatchV2,
    ModelMotionProposalV2,
    MotionCapabilityV2,
    MotionEvidenceV2,
    MotionGeometryV2,
    MotionUncertaintyV2,
    Point3Mm,
    ProposalDevice,
    SpeedClass,
    UncertaintyBoundType,
)


PROFILES = ("no_attachment", "stylus_attachment")


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _execution_and_trajectory():
    proposal = ModelMotionProposalV2(
        proposal_id="proposal-k00",
        action_index=0,
        device=ProposalDevice.KEYBOARD,
        target_id="K00",
        target=Point3Mm("board", 10.0, 20.0, 2.0),
        interaction=Interaction.CONTACT,
        observation_confidence=0.99,
    )
    batch = ModelMotionBatchV2(
        batch_id="batch-k00",
        request_id="request-k00",
        intent_plan_sha256="1" * 64,
        device=ProposalDevice.KEYBOARD,
        capability=MotionCapabilityV2("keyboard-dev", "2" * 64),
        geometry=MotionGeometryV2(
            coordinate_profile="board_mm_xy_plane_v2",
            coordinate_units="mm",
            board_frame_definition_sha256="3" * 64,
            placement_observation_sha256="4" * 64,
            target_catalog_sha256="5" * 64,
        ),
        evidence=MotionEvidenceV2(
            capture_id="capture",
            frame_id="frame",
            image_sha256="6" * 64,
            camera_identity_sha256="7" * 64,
            capture_clock_domain_id="clock",
            model_id="model",
            model_sha256="8" * 64,
            scene_observation_sha256="9" * 64,
            precision_observation_sha256="a" * 64,
            fusion_decision_sha256="b" * 64,
            scene_lease_id="lease",
            scene_lease_issuer_id="issuer",
            scene_lease_sha256="c" * 64,
            captured_at_epoch_ms=1,
            evaluated_at_epoch_ms=2,
            expires_at_epoch_ms=10_000,
        ),
        uncertainty=MotionUncertaintyV2(
            bound_type=UncertaintyBoundType.PLANAR_L2_DISK,
            error_bound_mm=1.0,
            coverage_probability=0.99,
            qualification_sha256="d" * 64,
            evidence_method_sha256="e" * 64,
            domain_id="domain",
            covered_target_ids=("K00",),
        ),
        proposals=(proposal,),
    )
    ingress = {
        "schema": "rocell.model_motion_ingress.v2",
        "status": "ACCEPTED_V2_FOR_FRESH_SEQUENTIAL_PLANNER_GATES",
        "batch_sha256": batch.batch_sha256,
        "intent_plan_sha256": batch.intent_plan_sha256,
        "request_id": batch.request_id,
        "ordered_target_ids": ["K00"],
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    ingress["ingress_sha256"] = _sha(ingress)
    config = TypingExecutionConfigV1(
        config_id="keyboard-no-attachment",
        calibration_snapshot_sha256="f" * 64,
        tool_profile_sha256="0" * 64,
        dynamics_profile_sha256="1" * 64,
        route_reference_point=Point3Mm("board", -30.0, 0.0, 22.0),
        hover_clearance_mm=20.0,
        settle_position_tolerance_mm=0.5,
        settle_velocity_tolerance_mm_s=1.0,
        settle_hold_ms=100,
        preview_horizon=1,
        speed_class=SpeedClass.SLOW,
    )
    execution = compile_typing_execution_plan_v1(batch, ingress, config=config)
    policy = TypingTrajectoryPolicyV1(
        policy_id="keyboard-s0-quintic-v1",
        maximum_cartesian_step_mm=5.0,
        maximum_velocity_mm_s=80.0,
        maximum_acceleration_mm_s2=160.0,
        maximum_jerk_mm_s3=800.0,
        hover_settle_ms=100,
        contact_dwell_ms=60,
    )
    trajectory = compile_typing_trajectory_plan_v1(execution, policy=policy)
    return execution, trajectory


def _fixtures():
    execution, trajectory = _execution_and_trajectory()
    collision_hashes = {
        "no_attachment": "5" * 64,
        "stylus_attachment": "6" * 64,
    }
    planning = {
        "schema": PLANNING_ADMISSION_RECEIPT_SCHEMA,
        "status": "FUSED_CAMERA_STATE_PLANNING_ADMITTED",
        "planner_id": "keyboard-plan-candidate-01",
        "planning_context_sha256": "1" * 64,
        "fusion_receipt_sha256": "2" * 64,
        "board_registration_sha256": "3" * 64,
        "robot_localization_sha256": "4" * 64,
        "clearance_intake_sha256": "9" * 64,
        "attachment_profile": "no_attachment",
        "admitted_at": "2026-10-25T14:02:32-04:00",
        "valid_until": "2026-10-25T14:02:40-04:00",
        "plan_candidate": {
            "target_key_id": "K00",
            "attachment_profile": "no_attachment",
            "board_xy_mm": [10.0, 20.0],
            "robot_xyz_mm": [110.0, 220.0, 90.0],
            "requested_hover_clearance_mm": 20.0,
            "maximum_waypoint_count": 64,
            "installed_collision_profile_content_sha256": collision_hashes[
                "no_attachment"
            ],
            "clearance_policy_sha256": "7" * 64,
        },
        "calibrated_feedback": {"joint_positions_rad": [0.0] * 6},
        "camera_observation": {"board_pose": [0.0, 0.0, 1.0]},
        "next_required_gate": (
            "PROFILE_SPECIFIC_TRAJECTORY_CONSTRUCTION_AND_COLLISION_QUALIFICATION"
        ),
        "blockers": [
            "TRAJECTORY_NOT_CONSTRUCTED",
            "CONTINUOUS_COLLISION_NOT_QUALIFIED",
            "PHYSICAL_CLEARANCE_NOT_ESTABLISHED",
            "EXECUTION_ADMISSION_NOT_GRANTED",
        ],
        "limitations": ["zero authority"],
        "fused_camera_state_planning_admitted": True,
        "plan_candidate_emitted": True,
        "trajectory_generated": False,
        "collision_screening_executed": False,
        "continuous_clearance_verified": False,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }
    planning["planning_admission_id"] = "fused-camera-state-planning:" + _sha(
        {
            "fusion_receipt_sha256": planning["fusion_receipt_sha256"],
            "planning_context_sha256": planning["planning_context_sha256"],
            "plan_candidate": planning["plan_candidate"],
        }
    )
    route_profiles = {}
    partition_profiles = {}
    qualified_profiles = {}
    for index, profile in enumerate(PROFILES):
        plan_sha = execution.plan_sha256 if profile == "no_attachment" else str(index + 2) * 64
        trajectory_sha = (
            trajectory.trajectory_plan_sha256
            if profile == "no_attachment"
            else str(index + 3) * 64
        )
        partition_sha = str(index + 8) * 64
        route_profiles[profile] = {
            "profile": profile,
            "typing_execution_plan_sha256": plan_sha,
            "typing_trajectory_policy_sha256": (
                trajectory.policy.policy_sha256 if profile == "no_attachment" else "4" * 64
            ),
            "typing_trajectory_plan_sha256": trajectory_sha,
            "installed_collision_profile_content_sha256": collision_hashes[profile],
        }
        partition_profiles[profile] = {
            "profile": profile,
            "typing_execution_plan_sha256": plan_sha,
            "typing_trajectory_plan_sha256": trajectory_sha,
            "installed_collision_profile_content_sha256": collision_hashes[profile],
            "partitioned_typing_collision_intake_sha256": partition_sha,
        }
        qualified_profiles[profile] = {
            "profile": profile,
            "installed_collision_profile_sha256": collision_hashes[profile],
            "partitioned_typing_collision_intake_sha256": partition_sha,
            "completion_sha256": "b" * 64,
            "independent_review_sha256": "c" * 64,
            "route_envelope_binding_sha256": str(index + 1) * 64,
            "route_sample_count": 329,
            "route_segment_count": 328,
        }
    route_core = {
        "schema": ROUTE_SCREEN_SCHEMA,
        "status": ROUTE_SCREEN_STATUS,
        "profiles": route_profiles,
        "profile_separation_preserved": True,
        "authority": dict(ROUTE_SCREEN_ZERO_AUTHORITY),
    }
    route = {**route_core, "profiled_route_screen_manifest_sha256": _sha(route_core)}
    partition_core = {
        "schema": PARTITIONS_SCHEMA,
        "status": PARTITIONS_STATUS,
        "source_profiled_route_screen_manifest_sha256": route[
            "profiled_route_screen_manifest_sha256"
        ],
        "profiles": partition_profiles,
        "profile_separation_preserved": True,
        "authority": dict(PARTITIONS_ZERO_AUTHORITY),
    }
    partitions = {
        **partition_core,
        "profiled_collision_partitions_manifest_sha256": _sha(partition_core),
    }
    qualified_core = {
        "schema": ROUTE_BOUND_SCHEMA,
        "status": ROUTE_BOUND_READY,
        "profiles": qualified_profiles,
        "profile_separation_preserved": True,
        "exact_route_binding_verified_before_evaluation": True,
        "authority": dict(ROUTE_BOUND_ZERO_AUTHORITY),
    }
    qualified = {
        **qualified_core,
        "route_bound_collision_qualification_sha256": _sha(qualified_core),
    }
    return planning, execution.to_dict(), trajectory.to_dict(), route, partitions, qualified


def _admit(fixtures, **overrides):
    planning, execution, trajectory, route, partitions, qualified = fixtures
    values = {
        "planning_receipt_document": planning,
        "typing_execution_plan_document": execution,
        "typing_trajectory_plan_document": trajectory,
        "profiled_route_screen_manifest_document": route,
        "profiled_collision_partitions_manifest_document": partitions,
        "route_bound_collision_qualification_document": qualified,
        "current_attachment_profile": "no_attachment",
        "consumed_at": "2026-10-25T14:02:35-04:00",
    }
    values.update(overrides)
    return subject.admit_fused_camera_state_route_qualification(**values)


def _reseal(document, hash_field):
    core = dict(document)
    core.pop(hash_field)
    document[hash_field] = _sha(core)


def test_admits_fresh_camera_target_only_to_exact_qualified_profile_route():
    receipt = _admit(_fixtures())

    assert receipt["status"] == subject.STATUS
    assert receipt["target_key_id"] == "K00"
    assert receipt["target_action_indices"] == [0]
    assert receipt["exact_target_route_binding_verified"] is True
    assert receipt["next_required_gate"] == (
        "ROUTE_BOUND_FRESH_OBSERVED_ENTRY_QUALIFICATION"
    )
    assert receipt["authority"] == subject.ZERO_AUTHORITY
    core = dict(receipt)
    assert core.pop("route_qualification_admission_sha256") == _sha(core)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("expired", "not fresh"),
            ("candidate_identity", "planning admission identity differs"),
        ("coordinate", "board coordinates differ"),
        ("trajectory", "trajectory plan hash differs"),
        ("partition", "collision partition lineage differs"),
        ("collision", "qualified route differs"),
        ("profile", "active attachment profile differs"),
    ),
)
def test_rejects_stale_crossed_or_tampered_route_lineage(mutation, message):
    fixtures = list(copy.deepcopy(_fixtures()))
    overrides = {}
    if mutation == "expired":
        overrides["consumed_at"] = "2026-10-25T14:02:41-04:00"
    elif mutation in ("candidate_identity", "coordinate"):
        fixtures[0]["plan_candidate"]["board_xy_mm"] = [11.0, 20.0]
        if mutation == "coordinate":
            fixtures[0]["planning_admission_id"] = (
                "fused-camera-state-planning:"
                + _sha(
                    {
                        "fusion_receipt_sha256": fixtures[0][
                            "fusion_receipt_sha256"
                        ],
                        "planning_context_sha256": fixtures[0][
                            "planning_context_sha256"
                        ],
                        "plan_candidate": fixtures[0]["plan_candidate"],
                    }
                )
            )
    elif mutation == "trajectory":
        fixtures[2]["phase_waypoints"][2]["point"]["x"] = 11.0
    elif mutation == "partition":
        fixtures[4]["profiles"]["no_attachment"][
            "typing_trajectory_plan_sha256"
        ] = "f" * 64
        _reseal(fixtures[4], "profiled_collision_partitions_manifest_sha256")
    elif mutation == "collision":
        fixtures[5]["profiles"]["no_attachment"][
            "installed_collision_profile_sha256"
        ] = "f" * 64
        _reseal(fixtures[5], "route_bound_collision_qualification_sha256")
    else:
        overrides["current_attachment_profile"] = "stylus_attachment"

    with pytest.raises(
        subject.FusedCameraStateRouteQualificationAdmissionError,
        match=message,
    ):
        _admit(tuple(fixtures), **overrides)


def test_rejects_nonready_route_bound_collision_result():
    fixtures = list(_fixtures())
    fixtures[5]["status"] = "BLOCKED_ROUTE_BOUND_CLEARANCE_EVIDENCE_INCOMPLETE"
    _reseal(fixtures[5], "route_bound_collision_qualification_sha256")

    with pytest.raises(
        subject.FusedCameraStateRouteQualificationAdmissionError,
        match="not ready",
    ):
        _admit(tuple(fixtures))
