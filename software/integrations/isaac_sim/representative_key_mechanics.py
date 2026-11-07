"""Deterministic, provisional keyboard-mechanics contract for Isaac LM1.

This module deliberately contains no hardware or motion interface.  It turns a
time-ordered virtual tip trace into a geometry-derived key activation result.
All numeric mechanics are synthetic, bounded priors for simulation development;
they are not measurements or product specifications.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import product
import json
import math
from pathlib import Path
from typing import Any, Iterable


PROFILE_SCHEMA = "tactevra.isaac_lm1_representative_key_mechanics.v1"
RECEIPT_SCHEMA = "tactevra.isaac_lm1_key_mechanics_contract_receipt.v1"
NATIVE_RECEIPT_SCHEMA = "tactevra.isaac_lm1_native_h_key_replay.v1"
TCP_BINDING_SCHEMA = "tactevra.isaac_lm1_robot_tcp_key_binding.v1"
TCP_CARTESIAN_SCHEDULE_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_cartesian_schedule_request.v1"
)
TCP_IK_SCREEN_SCHEMA = "tactevra.isaac_lm1_robot_tcp_cartesian_ik_screen.v1"
TCP_COLLISION_REPLAY_REQUEST_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_replay_request.v1"
)
TCP_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v1"
)
TCP_POLICY_BOUND_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v2"
)
TCP_PRIMITIVE_ATTRIBUTED_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v3"
)
TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v4"
)
TCP_FIXED_BASE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v5"
)
FIXED_BASE_SETTLE_UPDATE_COUNT = 5
FIXED_BASE_SOLVER_POSITION_ITERATION_COUNT = 64
FIXED_BASE_SOLVER_VELOCITY_ITERATION_COUNT = 8
FIXED_BASE_COLLISION_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_fixed_base_collision_replay_plan.v1"
)
TCP_COLLISION_POLICY_SCHEMA = "tactevra.isaac_lm1_collision_pair_policy.v1"
TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_replay_request.v2"
)
TCP_COLLISION_BLOCKER_LOCALIZATION_SCHEMA = (
    "tactevra.isaac_lm1_collision_blocker_localization.v1"
)
STATION_ROUTE_PREDICATE_SCHEMA = (
    "tactevra.isaac_lm1_station_route_predicate.v1"
)
PHYSICAL_BLOCKER_EXPERIMENT_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_physical_blocker_experiment_plan.v1"
)
PLACEMENT_TCP_SEARCH_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_placement_tcp_search_plan.v1"
)
PLACEMENT_TCP_SEARCH_SCREEN_SCHEMA = (
    "tactevra.isaac_lm1_placement_tcp_search_screen.v1"
)
PLACEMENT_TCP_NATIVE_SELECTION_SCHEMA = (
    "tactevra.isaac_lm1_placement_tcp_native_selection.v1"
)
ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_route_shape_campaign_plan.v1"
)
ROUTE_SHAPE_CAMPAIGN_SCREEN_SCHEMA = (
    "tactevra.isaac_lm1_route_shape_campaign_screen.v1"
)
ROUTE_SHAPE_NATIVE_SHORTLIST_SCHEMA = (
    "tactevra.isaac_lm1_route_shape_native_shortlist.v1"
)
ROUTE_SHAPE_NATIVE_SELECTION_SCHEMA = (
    "tactevra.isaac_lm1_route_shape_native_selection.v1"
)
ROUTE_SHAPE_V4_NATIVE_SELECTION_SCHEMA = (
    "tactevra.isaac_lm1_route_shape_v4_native_selection.v1"
)
KEY_MECHANICS_LEARNING_BASELINE_SELECTION_SCHEMA = (
    "tactevra.isaac_lm1_key_mechanics_learning_baseline_selection.v1"
)
DRIVE_CONTROLLED_ROBOT_H_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_drive_controlled_robot_h_replay_plan.v1"
)
DRIVE_CONTROLLED_ROBOT_H_REPLAY_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_drive_controlled_robot_h_replay_receipt.v1"
)
FEEDBACK_ADAPTED_ROBOT_H_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_feedback_adapted_robot_h_replay_plan.v1"
)
FEEDBACK_ADAPTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_feedback_adapted_robot_h_replay_receipt.v1"
)
TRACE_LIFTED_ROBOT_H_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_trace_lifted_robot_h_replay_plan.v1"
)
TRACE_LIFTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_trace_lifted_robot_h_replay_receipt.v1"
)
CONTACT_REFINED_ROBOT_H_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_contact_refined_robot_h_replay_plan.v1"
)
CONTACT_REFINED_ROBOT_H_REPLAY_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_contact_refined_robot_h_replay_receipt.v1"
)
GOVERNED_H_DEMONSTRATION_SCHEMA = (
    "tactevra.isaac_lm2_governed_h_demonstration.v1"
)
REPRESENTATIVE_KEY_ADAPTATION_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_cartesian_adaptation_campaign.v1"
)
REPRESENTATIVE_KEY_PARK_ROUTE_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_park_route_campaign.v1"
)
REPRESENTATIVE_KEY_IK_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_ik_campaign.v1"
)
REPRESENTATIVE_KEY_COLLISION_REPLAY_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_collision_replay_campaign.v1"
)
REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_collision_replay_plan.v1"
)
REPRESENTATIVE_KEY_NATIVE_COLLISION_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_collision_receipt.v1"
)
REPRESENTATIVE_KEY_NATIVE_COLLISION_MANIFEST_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_collision_manifest.v1"
)
REPRESENTATIVE_KEY_NATIVE_COLLISION_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_collision_campaign.v1"
)
REPRESENTATIVE_KEY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_mechanics_replay_plan.v1"
)
REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_mechanics_receipt.v1"
)
REPRESENTATIVE_KEY_NATIVE_MECHANICS_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_mechanics_campaign.v1"
)
REPRESENTATIVE_KEY_NATIVE_MECHANICS_RESULT_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_native_mechanics_result_campaign.v1"
)
REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_feedback_adapted_mechanics_replay_plan.v1"
)
REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_feedback_adapted_mechanics_campaign.v1"
)
REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_contact_refined_mechanics_replay_plan.v1"
)
REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm2_representative_key_contact_refined_mechanics_campaign.v1"
)
RANDOMIZED_DEMONSTRATION_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm3_randomized_demonstration_campaign.v1"
)
RANDOMIZED_DEMONSTRATION_EPISODE_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm3_randomized_demonstration_episode_receipt.v1"
)
RANDOMIZED_DEMONSTRATION_RESULT_SCHEMA = (
    "tactevra.isaac_lm3_randomized_demonstration_result.v1"
)
STATE_POLICY_TRAJECTORY_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_trajectory_row.v1"
)
STATE_POLICY_DATASET_MANIFEST_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_dataset_manifest.v1"
)
STATE_POLICY_BASELINE_SCHEMA = "tactevra.isaac_lm4_state_policy_baseline.v1"
STATE_POLICY_PROPOSAL_ROW_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_proposal_row.v1"
)
STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_proposal_replay_campaign.v1"
)
STATE_POLICY_COLLISION_REQUEST_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_collision_request.v1"
)
STATE_POLICY_COLLISION_REQUEST_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_collision_request_campaign.v1"
)
STATE_POLICY_COLLISION_RUNTIME_ADMISSION_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_collision_runtime_admission.v1"
)
STATE_POLICY_COLLISION_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_collision_runtime_admission_campaign.v1"
)
STATE_POLICY_COLLISION_RUNTIME_REVALIDATION_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_collision_runtime_revalidation.v1"
)
STATE_POLICY_COLLISION_RUNTIME_REVALIDATION_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_collision_runtime_revalidation_campaign.v1"
)
STATE_POLICY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_collision_replay_plan.v1"
)
STATE_POLICY_NATIVE_COLLISION_MANIFEST_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_collision_manifest.v1"
)
STATE_POLICY_NATIVE_COLLISION_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_collision_receipt.v1"
)
STATE_POLICY_NATIVE_COLLISION_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_collision_campaign.v1"
)
STATE_POLICY_NATIVE_COLLISION_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_collision_review.v1"
)
STATE_POLICY_MECHANICS_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_mechanics_replay_plan.v1"
)
STATE_POLICY_MECHANICS_REPLAY_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_mechanics_replay_campaign.v1"
)
STATE_POLICY_MECHANICS_RUNTIME_ADMISSION_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_mechanics_runtime_admission.v1"
)
STATE_POLICY_MECHANICS_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_mechanics_runtime_admission_campaign.v1"
)
STATE_POLICY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_mechanics_replay_plan.v1"
)
STATE_POLICY_NATIVE_MECHANICS_MANIFEST_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_mechanics_manifest.v1"
)
STATE_POLICY_NATIVE_MECHANICS_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_mechanics_receipt.v1"
)
STATE_POLICY_PHASES = ("PARK", "TRANSIT", "HOVER", "CONTACT", "RETRACT")
STATE_POLICY_MAX_ADJACENT_STEP_RAD = 0.05
RANDOMIZED_DEMONSTRATION_SPLIT_REPETITIONS = {
    "train": 3,
    "validation": 2,
    "test": 1,
}
RANDOMIZED_DEMONSTRATION_FAILURE_REASONS = (
    "COLLISION_BLOCKER",
    "IK_OR_CONTINUITY",
    "MECHANICS_REJECTION",
    "ROOT_INVARIANT",
    "TRACKING_ERROR",
    "UNEXPECTED_RUNTIME_ERROR",
)
GEOMETRY_PRIOR_PROFILE_SCHEMA = "tactevra.isaac_lm0b_geometry_prior_profile.v1"
REPRESENTATIVE_KEYS = ("H", "1", "SPACE", "ENTER", "PERIOD")
PROVISIONAL_STATUS = "PROVISIONAL_SIMULATION_ONLY"
NATIVE_H_PRESS_DEPTH_MM = 2.7
DISPOSITIONS = (
    "ACCEPTED",
    "SHALLOW_PRESS",
    "OFF_CENTER_PRESS",
    "EXCESSIVE_TRAVEL",
    "DOUBLE_ACTIVATION",
    "NEIGHBORING_KEY_CONTACT",
    "INCOMPLETE_RELEASE",
)

MECHANICS_PRIOR = {
    "travel_mm": {"nominal": 3.5, "range": [3.0, 4.0]},
    "activation_mm": {"nominal": 2.0, "range": [1.6, 2.4]},
    "release_mm": {"nominal": 1.2, "range": [0.8, 1.6]},
    "stiffness_n_per_mm": {"nominal": 0.55, "range": [0.35, 0.8]},
    "damping_n_s_per_mm": {"nominal": 0.015, "range": [0.005, 0.03]},
    "keycap_mass_kg": {"nominal": 0.005, "range": [0.003, 0.009]},
    "center_margin_mm": 2.5,
    "tip_radius_mm": 1.0,
}


class MechanicsContractError(ValueError):
    """Raised when the layout or virtual trace violates the contract."""


def _require_canonical_hash(document: dict[str, Any], field: str, label: str) -> str:
    claimed = document.get(field)
    unsigned = dict(document)
    unsigned.pop(field, None)
    if not isinstance(claimed, str) or claimed != _canonical_sha256(unsigned):
        raise MechanicsContractError(f"{label} hash mismatch")
    return claimed


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MechanicsContractError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MechanicsContractError(f"{name} must be finite")
    return result


def build_drive_controlled_robot_h_replay_plan(
    selection: dict[str, Any],
    cartesian_request: dict[str, Any],
    ik_receipt: dict[str, Any],
    fixed_base_receipt: dict[str, Any],
    fixed_base_plan: dict[str, Any],
    placement_selection: dict[str, Any],
    mechanics_profile: dict[str, Any],
    native_h_receipt: dict[str, Any],
    drive_profile: dict[str, Any],
    drive_profile_bytes: bytes,
    robot_usd_bytes: bytes,
    import_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Compile the one selected ARM-206 route into a zero-authority replay plan."""

    selection_hash = _require_canonical_hash(
        selection, "selection_sha256", "learning-baseline selection"
    )
    request_hash = _require_canonical_hash(
        cartesian_request, "request_sha256", "Cartesian request"
    )
    ik_hash = _require_canonical_hash(ik_receipt, "receipt_sha256", "IK receipt")
    fixed_hash = _require_canonical_hash(
        fixed_base_receipt, "receipt_sha256", "fixed-base receipt"
    )
    fixed_plan_hash = _require_canonical_hash(
        fixed_base_plan, "plan_sha256", "fixed-base replay plan"
    )
    placement_hash = _require_canonical_hash(
        placement_selection, "selection_sha256", "placement selection"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    native_h_hash = _require_canonical_hash(
        native_h_receipt, "receipt_sha256", "native H receipt"
    )
    import_hash = _require_canonical_hash(
        import_receipt, "receipt_sha256", "robot import receipt"
    )

    candidate_id = selection.get("selected_candidate_id")
    ranked = selection.get("ranked_candidates")
    selected_rows = [
        row for row in ranked if row.get("candidate_id") == candidate_id
    ] if isinstance(ranked, list) else []
    if (
        selection.get("schema")
        != KEY_MECHANICS_LEARNING_BASELINE_SELECTION_SCHEMA
        or selection.get("status")
        != "SELECTED_ZERO_AUTHORITY_SIMULATION_LEARNING_BASELINE"
        or selection.get("selection_scope") != "SIMULATION_LEARNING_BASELINE_ONLY"
        or selection.get("next_action")
        != "RUN_DRIVE_CONTROLLED_ROBOT_H_KEY_REPLAY_FOR_SELECTED_BASELINE"
        or selection.get("selected_candidate_rank") != 1
        or len(selected_rows) != 1
        or any(selection.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError("learning-baseline selection boundary changed")
    selected = selected_rows[0]
    if (
        selected.get("learning_baseline_rank") != 1
        or selected.get("fixed_base_collision_passed") is not True
        or selected.get("key_mechanics_passed") is not True
        or selected.get("source_cartesian_request_sha256") != request_hash
        or selected.get("source_ik_receipt_sha256") != ik_hash
        or selected.get("source_fixed_base_v5_receipt_sha256") != fixed_hash
    ):
        raise MechanicsContractError("selected candidate lineage changed")

    samples = cartesian_request.get("samples")
    joint_results = ik_receipt.get("joint_results")
    if (
        cartesian_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or cartesian_request.get("status") not in {
            "READY_FOR_IK_QUALIFICATION",
            "READY_FOR_TARGET_SPECIFIC_IK_QUALIFICATION",
        }
        or cartesian_request.get("route_shape_candidate_id") != candidate_id
        or cartesian_request.get("profile_sha256") != profile_hash
        or not isinstance(samples, list)
        or cartesian_request.get("sample_count") != len(samples)
        or not samples
        or ik_receipt.get("schema") != TCP_IK_SCREEN_SCHEMA
        or ik_receipt.get("status") != "READY_FOR_COLLISION_QUALIFICATION"
        or ik_receipt.get("source_request_sha256") != request_hash
        or ik_receipt.get("route_shape_candidate_id") != candidate_id
        or ik_receipt.get("sample_count") != len(samples)
        or not isinstance(joint_results, list)
        or len(joint_results) != len(samples)
        or any(result.get("accepted") is not True for result in joint_results)
        or cartesian_request.get("authority") != {
            "hardware": False,
            "motion": False,
            "physical_keyboard_qualification": False,
        }
        or any(cartesian_request.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_movements",
            "controller_commands",
        ))
        or any(ik_receipt.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands",
        ))
    ):
        raise MechanicsContractError("selected request or IK boundary changed")

    fixed_sources = fixed_base_receipt.get("source_bindings", {})
    root_invariant = fixed_base_receipt.get("root_pose_invariant", {})
    fixed_candidates = fixed_base_plan.get("candidates", [])
    if (
        fixed_base_receipt.get("schema")
        != TCP_FIXED_BASE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
        or fixed_base_receipt.get("fixed_base_mechanism")
        != "USD_FIXED_JOINT_TO_WORLD"
        or fixed_sources.get("ik_receipt_sha256") != ik_hash
        or fixed_sources.get("fixed_base_replay_plan_sha256") != fixed_plan_hash
        or not isinstance(root_invariant, dict)
        or root_invariant.get("observation_count")
        != root_invariant.get("expected_observation_count")
        or root_invariant.get("observation_count")
        != len(root_invariant.get("observations", []))
        or any(not row.get("passed") for row in root_invariant.get("observations", []))
        or fixed_base_plan.get("schema") != FIXED_BASE_COLLISION_REPLAY_PLAN_SCHEMA
        or fixed_base_plan.get("status")
        != "READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY"
        or len([
            row for row in fixed_candidates
            if row.get("candidate_id") == candidate_id
            and row.get("source_request_sha256") == request_hash
        ]) != 1
        or any(fixed_base_receipt.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError("fixed-base evidence boundary changed")

    placement_id = ik_receipt.get("placement_tcp_candidate_id")
    if (
        placement_selection.get("schema") != PLACEMENT_TCP_NATIVE_SELECTION_SCHEMA
        or placement_selection.get("selected_candidate_id") != placement_id
        or placement_selection.get("control_candidate_id") != placement_id
        or placement_selection.get("hardware_access") is not False
        or placement_selection.get("physical_authority") is not False
    ):
        raise MechanicsContractError("placement selection boundary changed")
    if (
        mechanics_profile.get("schema") != PROFILE_SCHEMA
        or selection.get("source_key_mechanics_profile_sha256") != profile_hash
        or native_h_receipt.get("schema") != NATIVE_RECEIPT_SCHEMA
        or native_h_receipt.get("status") != "PASS"
        or native_h_receipt.get("profile_sha256") != profile_hash
        or native_h_receipt.get("assessment", {}).get("resolved_key") != "H"
        or native_h_receipt.get("assessment", {}).get("accepted") is not True
        or native_h_receipt.get("assessment", {}).get("native_contact_observed") is not True
    ):
        raise MechanicsContractError("native H mechanism boundary changed")

    robot_usd_hash = hashlib.sha256(robot_usd_bytes).hexdigest()
    external = import_receipt.get("external_files")
    normalization = import_receipt.get("articulation_root_normalization", {})
    joint_order = [
        "base_link_to_link1", "link1_to_link2", "link2_to_link3",
        "link3_to_link4", "link4_to_link5", "link5_to_gripper_link",
    ]
    if (
        drive_profile.get("schema") != GEOMETRY_PRIOR_PROFILE_SCHEMA
        or drive_profile.get("status") != "PROVISIONAL_SIMULATION_ONLY"
        or drive_profile.get("simulation_only") is not True
        or drive_profile.get("physical_authority") is not False
        or import_receipt.get("schema") != "tactevra.isaac_sim_urdf_import.v1"
        or not isinstance(external, list) or len(external) != 1
        or external[0].get("sha256") != robot_usd_hash
        or external[0].get("size_bytes") != len(robot_usd_bytes)
        or normalization.get("expected_live_dof_order") != joint_order
        or fixed_sources.get("robot_import_receipt_sha256") != import_hash
        or fixed_sources.get("robot_usd_sha256") != robot_usd_hash
    ):
        raise MechanicsContractError("drive profile or robot asset boundary changed")

    targets = []
    contact_endpoints = []
    for sample, result in zip(samples, joint_results):
        if result.get("phase") != sample.get("phase") \
                or result.get("action_index") != sample.get("action_index"):
            raise MechanicsContractError("IK result ordering changed")
        solution = result.get("solution_arm_joint_positions_rad", {})
        target = [_finite_number(solution.get(name), f"joint target {name}")
                  for name in joint_order[:5]] + [0.0]
        row = {
            "sequence": sample.get("sequence"),
            "time_from_start_ns": sample.get("time_from_start_ns"),
            "phase": sample.get("phase"),
            "target_id": sample.get("target_id"),
            "action_index": sample.get("action_index"),
            "phase_endpoint": sample.get("phase_endpoint"),
            "joint_position_target_rad": target,
        }
        targets.append(row)
        if row["target_id"] == "H" and row["phase"] == "CONTACT" \
                and row["phase_endpoint"] is True:
            contact_endpoints.append(row["sequence"])
    if len(contact_endpoints) != 2:
        raise MechanicsContractError("selected route must retain two H contact endpoints")

    plan: dict[str, Any] = {
        "schema": DRIVE_CONTROLLED_ROBOT_H_REPLAY_PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_NATIVE_ROBOT_H_REPLAY",
        "selected_candidate_id": candidate_id,
        "joint_order": joint_order,
        "sample_count": len(targets),
        "h_contact_endpoint_sequences": contact_endpoints,
        "joint_targets": targets,
        "robot_placement_matrix_row_major": ik_receipt.get(
            "robot_placement_matrix_row_major"
        ),
        "source_bindings": {
            "learning_baseline_selection_sha256": selection_hash,
            "cartesian_request_sha256": request_hash,
            "ik_receipt_sha256": ik_hash,
            "fixed_base_receipt_sha256": fixed_hash,
            "fixed_base_replay_plan_sha256": fixed_plan_hash,
            "placement_selection_sha256": placement_hash,
            "key_mechanics_profile_sha256": profile_hash,
            "native_h_receipt_sha256": native_h_hash,
            "drive_profile_file_sha256": hashlib.sha256(drive_profile_bytes).hexdigest(),
            "robot_import_receipt_sha256": import_hash,
            "robot_usd_sha256": robot_usd_hash,
        },
        "execution_contract": {
            "initial_joint_state_placement_count": 1,
            "post_initialization_state_teleports": 0,
            "subsequent_joint_commands": "ARTICULATION_POSITION_TARGETS_ONLY",
            "key_motion_source": "NATIVE_CONTACT_ONLY",
            "root_pose_invariant_required_after_every_sample": True,
        },
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "simulation_only_provisional_drive_and_mechanics_parameters",
            "no_continuous_collision_or_installed_profile_qualification",
            "no_hardware_motion_timing_torque_or_safety_authority",
        ],
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def build_feedback_adapted_robot_h_replay_plan(
    source_plan: dict[str, Any],
    source_receipt: dict[str, Any],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Adapt H contact depth and release dwell from the retained ARM-207 trace."""

    source_plan_hash = _require_canonical_hash(
        source_plan, "plan_sha256", "ARM-207 replay plan"
    )
    source_receipt_hash = _require_canonical_hash(
        source_receipt, "receipt_sha256", "ARM-207 replay receipt"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    assessments = source_receipt.get("action_assessments")
    targets = source_plan.get("joint_targets")
    if (
        source_plan.get("schema") != DRIVE_CONTROLLED_ROBOT_H_REPLAY_PLAN_SCHEMA
        or source_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_NATIVE_ROBOT_H_REPLAY"
        or source_plan.get("h_contact_endpoint_sequences") != [35, 38]
        or not isinstance(targets, list)
        or source_plan.get("sample_count") != len(targets)
        or source_plan.get("source_bindings", {}).get(
            "key_mechanics_profile_sha256"
        )
        != profile_hash
        or source_receipt.get("schema")
        != DRIVE_CONTROLLED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
        or source_receipt.get("status") != "BLOCKED_NATIVE_ROBOT_H_REPLAY"
        or source_receipt.get("source_plan_sha256") != source_plan_hash
        or source_receipt.get("state_teleports_after_initialization") != 0
        or not isinstance(assessments, list)
        or len(assessments) != 2
        or any(source_plan.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
        or any(source_receipt.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError("ARM-207 feedback boundary changed")

    by_action = {row.get("action_index"): row.get("assessment") for row in assessments}
    release_mm = mechanics_profile["mechanics_prior"]["release_mm"]["nominal"]
    if (
        set(by_action) != {0, 1}
        or any(not isinstance(row, dict) for row in by_action.values())
        or any(row.get("profile_sha256") != profile_hash for row in by_action.values())
        or any(row.get("disposition") != "EXCESSIVE_TRAVEL" for row in by_action.values())
        or any(row.get("native_contact_observed") is not True for row in by_action.values())
        or by_action[0].get("activation_count") != 1
        or by_action[1].get("activation_count") != 0
        or any(
            _finite_number(row.get("final_compression_mm"), "final compression")
            <= release_mm
            for row in by_action.values()
        )
    ):
        raise MechanicsContractError("ARM-207 failure evidence changed")

    source_depth_mm = NATIVE_H_PRESS_DEPTH_MM
    observed_max_mm = max(
        _finite_number(row.get("max_compression_mm"), "maximum compression")
        for row in by_action.values()
    )
    correction_mm = observed_max_mm - source_depth_mm
    adapted_depth_mm = source_depth_mm - correction_mm
    if correction_mm <= 0.0 or not 0.0 < adapted_depth_mm < source_depth_mm:
        raise MechanicsContractError("ARM-207 feedback does not support bounded adaptation")
    interpolation_ratio = adapted_depth_mm / source_depth_mm
    physics_dt_s = _finite_number(source_receipt.get("physics_dt_s"), "physics dt")
    if physics_dt_s <= 0.0:
        raise MechanicsContractError("ARM-207 physics dt is invalid")
    release_dwell_s = 2.0
    release_dwell_steps = math.ceil(release_dwell_s / physics_dt_s)

    adapted_targets = json.loads(json.dumps(targets))
    contact_sequences = set(source_plan["h_contact_endpoint_sequences"])
    adapted_contact_sequences = []
    release_sequences = []
    for sequence in contact_sequences:
        contact = adapted_targets[sequence]
        action_index = contact.get("action_index")
        hover_rows = [
            row for row in adapted_targets[:sequence]
            if row.get("action_index") == action_index
            and row.get("target_id") == "H"
            and row.get("phase") == "HOVER"
        ]
        retract_rows = [
            row for row in adapted_targets[sequence + 1:]
            if row.get("action_index") == action_index
            and row.get("target_id") == "H"
            and row.get("phase") == "RETRACT"
        ]
        if (
            contact.get("sequence") != sequence
            or contact.get("phase") != "CONTACT"
            or contact.get("target_id") != "H"
            or len(hover_rows) != 1
            or len(retract_rows) != 1
        ):
            raise MechanicsContractError("ARM-207 H phase ordering changed")
        hover = hover_rows[0]
        source_contact = contact["joint_position_target_rad"]
        hover_target = hover["joint_position_target_rad"]
        if len(source_contact) != 6 or len(hover_target) != 6:
            raise MechanicsContractError("ARM-207 H joint target changed")
        contact["joint_position_target_rad"] = [
            float(hover_target[index])
            + interpolation_ratio
            * (float(source_contact[index]) - float(hover_target[index]))
            for index in range(6)
        ]
        adapted_contact_sequences.append(sequence)
        retract = retract_rows[0]
        retract["additional_hold_steps"] = release_dwell_steps
        release_sequences.append(retract["sequence"])

    for row in adapted_targets:
        row.setdefault("additional_hold_steps", 0)
    if sorted(adapted_contact_sequences) != [35, 38] or sorted(release_sequences) != [36, 39]:
        raise MechanicsContractError("ARM-207 H adaptation coverage changed")

    plan = json.loads(json.dumps(source_plan))
    plan.pop("plan_sha256", None)
    plan.update({
        "schema": FEEDBACK_ADAPTED_ROBOT_H_REPLAY_PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_NATIVE_H_REPLAY",
        "joint_targets": adapted_targets,
        "source_bindings": {
            **source_plan["source_bindings"],
            "arm207_replay_plan_sha256": source_plan_hash,
            "arm207_replay_receipt_sha256": source_receipt_hash,
        },
        "feedback_adaptation": {
            "method": "ADDITIVE_COMPRESSION_ERROR_AND_RELEASE_DWELL",
            "source_commanded_depth_mm": source_depth_mm,
            "observed_max_compression_mm": observed_max_mm,
            "target_max_compression_mm": NATIVE_H_PRESS_DEPTH_MM,
            "compression_error_mm": correction_mm,
            "adapted_commanded_depth_mm": adapted_depth_mm,
            "contact_interpolation_ratio": interpolation_ratio,
            "adapted_contact_sequences": sorted(adapted_contact_sequences),
            "release_dwell_s": release_dwell_s,
            "release_dwell_steps": release_dwell_steps,
            "release_dwell_sequences": sorted(release_sequences),
            "maximum_joint_tracking_error_rad": 0.05,
            "spatial_route_changed": False,
            "mechanics_thresholds_changed": False,
        },
        "limitations": source_plan["limitations"] + [
            "feedback_adaptation_is_a_single_bounded_simulation_only_update",
            "contact_targets_are_interpolated_in_joint_space_on_the_selected_route",
        ],
    })
    plan["execution_contract"].update({
        "feedback_adaptation_applied": True,
        "additional_release_dwell_allowed_only_at_sequences": [36, 39],
        "maximum_joint_tracking_error_rad": 0.05,
    })
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def build_trace_lifted_robot_h_replay_plan(
    source_plan: dict[str, Any],
    source_receipt: dict[str, Any],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Lift the H hover/retract path from the retained ARM-208 native trace."""

    source_plan_hash = _require_canonical_hash(
        source_plan, "plan_sha256", "ARM-208 replay plan"
    )
    source_receipt_hash = _require_canonical_hash(
        source_receipt, "receipt_sha256", "ARM-208 replay receipt"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    targets = source_plan.get("joint_targets")
    assessments = source_receipt.get("action_assessments")
    native_trace = source_receipt.get("native_trace")
    if (
        source_plan.get("schema") != FEEDBACK_ADAPTED_ROBOT_H_REPLAY_PLAN_SCHEMA
        or source_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_NATIVE_H_REPLAY"
        or source_plan.get("h_contact_endpoint_sequences") != [35, 38]
        or not isinstance(targets, list)
        or len(targets) != source_plan.get("sample_count")
        or source_plan.get("source_bindings", {}).get(
            "key_mechanics_profile_sha256"
        )
        != profile_hash
        or source_plan.get("feedback_adaptation", {}).get("method")
        != "ADDITIVE_COMPRESSION_ERROR_AND_RELEASE_DWELL"
        or source_receipt.get("schema")
        != FEEDBACK_ADAPTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
        or source_receipt.get("status") != "BLOCKED_NATIVE_ROBOT_H_REPLAY"
        or source_receipt.get("source_plan_sha256") != source_plan_hash
        or source_receipt.get("state_teleports_after_initialization") != 0
        or not isinstance(assessments, list)
        or len(assessments) != 2
        or not isinstance(native_trace, list)
        or not native_trace
        or any(source_plan.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
        or any(source_receipt.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError("ARM-208 trace-lift boundary changed")

    by_action = {row.get("action_index"): row.get("assessment") for row in assessments}
    if (
        set(by_action) != {0, 1}
        or any(not isinstance(row, dict) for row in by_action.values())
        or any(row.get("profile_sha256") != profile_hash for row in by_action.values())
        or any(row.get("disposition") != "EXCESSIVE_TRAVEL" for row in by_action.values())
        or any(row.get("native_contact_observed") is not True for row in by_action.values())
    ):
        raise MechanicsContractError("ARM-208 blocked action evidence changed")

    anchor_sequence = 33
    anchor_trace = [
        row for row in native_trace if row.get("target_sequence") == anchor_sequence
    ]
    if not anchor_trace:
        raise MechanicsContractError("ARM-208 no-contact anchor trace is missing")
    rest_key_z_m = max(
        _finite_number(row.get("key_center_z_m"), "trace key center")
        for row in native_trace
    )
    anchor_max_compression_mm = max(
        (rest_key_z_m - _finite_number(row.get("key_center_z_m"), "anchor key center"))
        * 1000.0
        for row in anchor_trace
    )
    anchor_minimum_clearance_mm = min(
        _finite_number(row.get("tip_key_separation_m"), "anchor separation")
        * 1000.0
        for row in anchor_trace
    )
    required_clearance_mm = 0.5
    maximum_anchor_compression_mm = 0.05
    if (
        anchor_minimum_clearance_mm < required_clearance_mm
        or anchor_max_compression_mm > maximum_anchor_compression_mm
    ):
        raise MechanicsContractError("ARM-208 trace does not prove a no-contact anchor")

    observed_max_compression_mm = max(
        _finite_number(row.get("max_compression_mm"), "maximum compression")
        for row in by_action.values()
    )
    target_compression_mm = NATIVE_H_PRESS_DEPTH_MM
    contact_interpolation_ratio = target_compression_mm / observed_max_compression_mm
    if not 0.0 < contact_interpolation_ratio < 1.0:
        raise MechanicsContractError("ARM-208 trace does not support bounded contact interpolation")

    adapted_targets = json.loads(json.dumps(targets))
    if len(adapted_targets) <= 39 or adapted_targets[anchor_sequence].get("sequence") != anchor_sequence:
        raise MechanicsContractError("ARM-208 target ordering changed")
    anchor_target = adapted_targets[anchor_sequence].get("joint_position_target_rad")
    if not isinstance(anchor_target, list) or len(anchor_target) != 6:
        raise MechanicsContractError("ARM-208 no-contact anchor target changed")
    lifted_sequences = [34, 36, 37, 39]
    contact_sequences = [35, 38]
    expected_phases = {
        34: ("HOVER", 0), 35: ("CONTACT", 0), 36: ("RETRACT", 0),
        37: ("HOVER", 1), 38: ("CONTACT", 1), 39: ("RETRACT", 1),
    }
    for sequence, (phase, action_index) in expected_phases.items():
        row = adapted_targets[sequence]
        if (
            row.get("sequence") != sequence
            or row.get("phase") != phase
            or row.get("action_index") != action_index
            or row.get("target_id") != "H"
        ):
            raise MechanicsContractError("ARM-208 H phase ordering changed")
    for sequence in lifted_sequences:
        adapted_targets[sequence]["joint_position_target_rad"] = list(anchor_target)
    for sequence in contact_sequences:
        source_contact = adapted_targets[sequence].get("joint_position_target_rad")
        if not isinstance(source_contact, list) or len(source_contact) != 6:
            raise MechanicsContractError("ARM-208 H contact target changed")
        adapted_targets[sequence]["joint_position_target_rad"] = [
            float(anchor_target[index])
            + contact_interpolation_ratio
            * (float(source_contact[index]) - float(anchor_target[index]))
            for index in range(6)
        ]

    def maximum_adjacent_delta(rows: list[dict[str, Any]]) -> float:
        maximum = 0.0
        for previous, current in zip(rows, rows[1:]):
            left = previous.get("joint_position_target_rad")
            right = current.get("joint_position_target_rad")
            if not isinstance(left, list) or not isinstance(right, list) \
                    or len(left) != 6 or len(right) != 6:
                raise MechanicsContractError("ARM-208 joint target shape changed")
            maximum = max(maximum, *(
                abs(float(right[index]) - float(left[index])) for index in range(6)
            ))
        return maximum

    source_maximum_delta = maximum_adjacent_delta(targets)
    adapted_maximum_delta = maximum_adjacent_delta(adapted_targets)
    if adapted_maximum_delta > source_maximum_delta + 1e-12:
        raise MechanicsContractError("trace-lifted path exceeds source joint continuity")

    plan = json.loads(json.dumps(source_plan))
    plan.pop("plan_sha256", None)
    plan.update({
        "schema": TRACE_LIFTED_ROBOT_H_REPLAY_PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_TRACE_LIFTED_NATIVE_H_REPLAY",
        "joint_targets": adapted_targets,
        "source_bindings": {
            **source_plan["source_bindings"],
            "arm208_replay_plan_sha256": source_plan_hash,
            "arm208_replay_receipt_sha256": source_receipt_hash,
        },
        "trace_lift_adaptation": {
            "method": "TRACE_DERIVED_NO_CONTACT_ANCHOR_AND_COMPRESSION_INTERPOLATION",
            "no_contact_anchor_sequence": anchor_sequence,
            "anchor_minimum_clearance_mm": anchor_minimum_clearance_mm,
            "required_minimum_clearance_mm": required_clearance_mm,
            "anchor_maximum_compression_mm": anchor_max_compression_mm,
            "maximum_anchor_compression_mm": maximum_anchor_compression_mm,
            "observed_max_compression_mm": observed_max_compression_mm,
            "target_compression_mm": target_compression_mm,
            "contact_interpolation_ratio": contact_interpolation_ratio,
            "lifted_hover_retract_sequences": lifted_sequences,
            "adapted_contact_sequences": contact_sequences,
            "source_maximum_adjacent_joint_delta_rad": source_maximum_delta,
            "adapted_maximum_adjacent_joint_delta_rad": adapted_maximum_delta,
            "source_qualified_anchor_reused": True,
            "mechanics_thresholds_changed": False,
            "maximum_joint_tracking_error_rad": 0.05,
        },
        "limitations": source_plan["limitations"] + [
            "trace_lift_is_a_single_bounded_simulation_only_update",
            "no_contact_anchor_is_reused_from_the_canonical_qualified_route",
        ],
    })
    plan["execution_contract"].update({
        "trace_lift_adaptation_applied": True,
        "maximum_joint_tracking_error_rad": 0.05,
    })
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def build_contact_refined_robot_h_replay_plan(
    source_plan: dict[str, Any],
    source_receipt: dict[str, Any],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Refine only H contact depth from the retained ARM-209 native result."""

    source_plan_hash = _require_canonical_hash(
        source_plan, "plan_sha256", "ARM-209 replay plan"
    )
    source_receipt_hash = _require_canonical_hash(
        source_receipt, "receipt_sha256", "ARM-209 replay receipt"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    targets = source_plan.get("joint_targets")
    assessments = source_receipt.get("action_assessments")
    lift = source_plan.get("trace_lift_adaptation", {})
    if (
        source_plan.get("schema") != TRACE_LIFTED_ROBOT_H_REPLAY_PLAN_SCHEMA
        or source_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_TRACE_LIFTED_NATIVE_H_REPLAY"
        or source_plan.get("h_contact_endpoint_sequences") != [35, 38]
        or not isinstance(targets, list)
        or len(targets) != source_plan.get("sample_count")
        or source_plan.get("source_bindings", {}).get(
            "key_mechanics_profile_sha256"
        )
        != profile_hash
        or lift.get("method")
        != "TRACE_DERIVED_NO_CONTACT_ANCHOR_AND_COMPRESSION_INTERPOLATION"
        or lift.get("no_contact_anchor_sequence") != 33
        or lift.get("lifted_hover_retract_sequences") != [34, 36, 37, 39]
        or lift.get("adapted_contact_sequences") != [35, 38]
        or lift.get("mechanics_thresholds_changed") is not False
        or source_receipt.get("schema") != TRACE_LIFTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
        or source_receipt.get("status") != "BLOCKED_NATIVE_ROBOT_H_REPLAY"
        or source_receipt.get("source_plan_sha256") != source_plan_hash
        or source_receipt.get("state_teleports_after_initialization") != 0
        or not isinstance(assessments, list)
        or len(assessments) != 2
        or any(source_plan.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
        or any(source_receipt.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError("ARM-209 contact-refinement boundary changed")

    release_mm = _finite_number(
        mechanics_profile["mechanics_prior"]["release_mm"]["nominal"],
        "release threshold",
    )
    by_action = {row.get("action_index"): row.get("assessment") for row in assessments}
    if (
        set(by_action) != {0, 1}
        or any(not isinstance(row, dict) for row in by_action.values())
        or any(row.get("profile_sha256") != profile_hash for row in by_action.values())
        or any(row.get("disposition") != "EXCESSIVE_TRAVEL" for row in by_action.values())
        or any(row.get("native_contact_observed") is not True for row in by_action.values())
        or any(row.get("activation_count") != 1 for row in by_action.values())
        or any(
            _finite_number(row.get("final_compression_mm"), "final compression")
            > release_mm
            for row in by_action.values()
        )
    ):
        raise MechanicsContractError("ARM-209 contact-only failure evidence changed")

    anchor_sequence = 33
    lifted_sequences = [34, 36, 37, 39]
    contact_sequences = [35, 38]
    if len(targets) <= 39 or targets[anchor_sequence].get("sequence") != anchor_sequence:
        raise MechanicsContractError("ARM-209 target ordering changed")
    anchor_target = targets[anchor_sequence].get("joint_position_target_rad")
    if not isinstance(anchor_target, list) or len(anchor_target) != 6:
        raise MechanicsContractError("ARM-209 anchor target changed")
    if any(
        targets[sequence].get("joint_position_target_rad") != anchor_target
        for sequence in lifted_sequences
    ):
        raise MechanicsContractError("ARM-209 lifted release geometry changed")

    observed_max_compression_mm = max(
        _finite_number(row.get("max_compression_mm"), "maximum compression")
        for row in by_action.values()
    )
    target_compression_mm = NATIVE_H_PRESS_DEPTH_MM
    contact_refinement_ratio = target_compression_mm / observed_max_compression_mm
    if not 0.0 < contact_refinement_ratio < 1.0:
        raise MechanicsContractError("ARM-209 feedback does not support bounded refinement")

    adapted_targets = json.loads(json.dumps(targets))
    for sequence in contact_sequences:
        row = adapted_targets[sequence]
        source_contact = row.get("joint_position_target_rad")
        if (
            row.get("sequence") != sequence
            or row.get("phase") != "CONTACT"
            or row.get("target_id") != "H"
            or row.get("action_index") not in (0, 1)
            or not isinstance(source_contact, list)
            or len(source_contact) != 6
        ):
            raise MechanicsContractError("ARM-209 H contact target changed")
        row["joint_position_target_rad"] = [
            float(anchor_target[index])
            + contact_refinement_ratio
            * (float(source_contact[index]) - float(anchor_target[index]))
            for index in range(6)
        ]

    def maximum_adjacent_delta(rows: list[dict[str, Any]]) -> float:
        return max(
            abs(
                float(current["joint_position_target_rad"][index])
                - float(previous["joint_position_target_rad"][index])
            )
            for previous, current in zip(rows, rows[1:])
            for index in range(6)
        )

    source_maximum_delta = maximum_adjacent_delta(targets)
    adapted_maximum_delta = maximum_adjacent_delta(adapted_targets)
    if adapted_maximum_delta > source_maximum_delta + 1e-12:
        raise MechanicsContractError("contact-refined path exceeds source joint continuity")
    if any(
        adapted_targets[index] != targets[index]
        for index in range(len(targets))
        if index not in contact_sequences
    ):
        raise MechanicsContractError("contact refinement changed a non-contact target")

    plan = json.loads(json.dumps(source_plan))
    plan.pop("plan_sha256", None)
    plan.update({
        "schema": CONTACT_REFINED_ROBOT_H_REPLAY_PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_NATIVE_H_REPLAY",
        "joint_targets": adapted_targets,
        "source_bindings": {
            **source_plan["source_bindings"],
            "arm209_replay_plan_sha256": source_plan_hash,
            "arm209_replay_receipt_sha256": source_receipt_hash,
        },
        "contact_refinement": {
            "method": "MULTIPLICATIVE_CONTACT_ERROR_FROM_TRACE_LIFTED_ANCHOR",
            "no_contact_anchor_sequence": anchor_sequence,
            "preserved_hover_retract_sequences": lifted_sequences,
            "adapted_contact_sequences": contact_sequences,
            "observed_max_compression_mm": observed_max_compression_mm,
            "target_compression_mm": target_compression_mm,
            "contact_refinement_ratio": contact_refinement_ratio,
            "source_maximum_adjacent_joint_delta_rad": source_maximum_delta,
            "adapted_maximum_adjacent_joint_delta_rad": adapted_maximum_delta,
            "mechanics_thresholds_changed": False,
            "maximum_joint_tracking_error_rad": 0.05,
        },
        "limitations": source_plan["limitations"] + [
            "contact_refinement_is_a_single_bounded_simulation_only_update",
            "trace_lifted_hover_and_retract_geometry_is_preserved",
        ],
    })
    plan["execution_contract"].update({
        "contact_refinement_applied": True,
        "maximum_joint_tracking_error_rad": 0.05,
    })
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def retain_governed_h_demonstration(
    plan: dict[str, Any],
    receipt: dict[str, Any],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Retain the passing ARM-210 H skill without granting transfer authority.

    The demonstration is an LM2 adaptation seed, not a multi-key trajectory.
    Joint-space samples are retained only for the source H skill window.  Every
    other representative key must be solved again from board-frame geometry and
    pass the existing IK, collision, and native mechanics boundaries.
    """

    plan_hash = _require_canonical_hash(
        plan, "plan_sha256", "ARM-210 replay plan"
    )
    receipt_hash = _require_canonical_hash(
        receipt, "receipt_sha256", "ARM-210 replay receipt"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    zero_authority_fields = (
        "hardware_access", "hardware_writes", "physical_authority",
        "physical_movements", "controller_commands", "gate_promotions",
    )
    if (
        plan.get("schema") != CONTACT_REFINED_ROBOT_H_REPLAY_PLAN_SCHEMA
        or plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_NATIVE_H_REPLAY"
        or receipt.get("schema")
        != CONTACT_REFINED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
        or receipt.get("status") != "PASS"
        or receipt.get("evidence_class")
        != "PROVISIONAL_NATIVE_DRIVE_CONTROLLED_ROBOT_KEY_CONTACT"
        or receipt.get("source_plan_sha256") != plan_hash
        or plan.get("source_bindings", {}).get(
            "key_mechanics_profile_sha256"
        ) != profile_hash
        or receipt.get("state_teleports_after_initialization") != 0
        or any(plan.get(name) not in (False, 0, []) for name in zero_authority_fields)
        or any(
            receipt.get(name) not in (False, 0, [])
            for name in zero_authority_fields
        )
    ):
        raise MechanicsContractError("ARM-210 demonstration boundary changed")

    joint_order = plan.get("joint_order")
    targets = plan.get("joint_targets")
    if (
        not isinstance(joint_order, list)
        or len(joint_order) != 6
        or len(set(joint_order)) != 6
        or not all(isinstance(name, str) and name for name in joint_order)
        or not isinstance(targets, list)
        or len(targets) != plan.get("sample_count")
        or len(targets) <= 39
        or any(row.get("sequence") != index for index, row in enumerate(targets))
    ):
        raise MechanicsContractError("ARM-210 demonstration trajectory changed")

    skill_sequences = list(range(33, 40))
    expected_phases = [
        "TRANSIT", "HOVER", "CONTACT", "RETRACT", "HOVER", "CONTACT",
        "RETRACT",
    ]
    expected_actions = [0, 0, 0, 0, 1, 1, 1]
    skill_window = [json.loads(json.dumps(targets[index])) for index in skill_sequences]
    if any(
        row.get("target_id") != "H"
        or row.get("phase") != expected_phases[index]
        or row.get("action_index") != expected_actions[index]
        or not isinstance(row.get("joint_position_target_rad"), list)
        or len(row["joint_position_target_rad"]) != 6
        for index, row in enumerate(skill_window)
    ):
        raise MechanicsContractError("ARM-210 H skill window changed")

    assessments = receipt.get("action_assessments")
    if not isinstance(assessments, list) or len(assessments) != 2:
        raise MechanicsContractError("ARM-210 action evidence changed")
    by_action = {row.get("action_index"): row.get("assessment") for row in assessments}
    if set(by_action) != {0, 1} or any(
        not isinstance(row, dict) for row in by_action.values()
    ):
        raise MechanicsContractError("ARM-210 action evidence changed")
    for action_index, assessment in by_action.items():
        _require_canonical_hash(
            assessment, "result_sha256", f"ARM-210 action {action_index} result"
        )
    activation_mm = _finite_number(
        mechanics_profile["mechanics_prior"]["activation_mm"]["nominal"],
        "activation threshold",
    )
    release_mm = _finite_number(
        mechanics_profile["mechanics_prior"]["release_mm"]["nominal"],
        "release threshold",
    )
    travel_mm = _finite_number(
        mechanics_profile["mechanics_prior"]["travel_mm"]["nominal"],
        "travel threshold",
    )
    if (
        any(row.get("accepted") is not True for row in by_action.values())
        or any(row.get("disposition") != "ACCEPTED" for row in by_action.values())
        or any(row.get("resolved_key") != "H" for row in by_action.values())
        or any(row.get("native_contact_observed") is not True for row in by_action.values())
        or any(row.get("activation_count") != 1 for row in by_action.values())
        or any(row.get("profile_sha256") != profile_hash for row in by_action.values())
        or any(row.get("authority") != mechanics_profile["authority"] for row in by_action.values())
        or any(
            not activation_mm <= _finite_number(
                row.get("max_compression_mm"), "maximum compression"
            ) <= travel_mm
            for row in by_action.values()
        )
        or any(
            _finite_number(row.get("final_compression_mm"), "final compression")
            > release_mm
            for row in by_action.values()
        )
    ):
        raise MechanicsContractError("ARM-210 accepted H evidence changed")

    root = receipt.get("root_pose_invariant")
    tracking = receipt.get("joint_tracking")
    tracking_limit = _finite_number(
        receipt.get("maximum_joint_tracking_error_allowed_rad"),
        "tracking limit",
    )
    tracking_maximum = _finite_number(
        receipt.get("maximum_joint_tracking_error_rad"),
        "maximum tracking error",
    )
    if (
        not isinstance(root, dict)
        or root.get("all_passed") is not True
        or root.get("observation_count") != len(targets)
        or not isinstance(root.get("observations"), list)
        or len(root["observations"]) != len(targets)
        or not all(row.get("passed") is True for row in root["observations"])
        or not isinstance(tracking, list)
        or len(tracking) != len(targets)
        or any(row.get("sequence") != index for index, row in enumerate(tracking))
        or tracking_maximum > tracking_limit
        or abs(
            tracking_maximum
            - max(
                _finite_number(row.get("maximum_joint_error_rad"), "tracking error")
                for row in tracking
            )
        ) > 1e-12
    ):
        raise MechanicsContractError("ARM-210 native quality evidence changed")

    outcomes = []
    for action_index in (0, 1):
        assessment = by_action[action_index]
        outcomes.append({
            "action_index": action_index,
            "resolved_key": "H",
            "disposition": "ACCEPTED",
            "activation_count": 1,
            "max_compression_mm": _finite_number(
                assessment["max_compression_mm"], "maximum compression"
            ),
            "final_compression_mm": _finite_number(
                assessment["final_compression_mm"], "final compression"
            ),
            "result_sha256": assessment.get("result_sha256"),
        })

    demonstration = {
        "schema": GOVERNED_H_DEMONSTRATION_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_KEY_ADAPTATION",
        "demonstration_id": "arm210-native-contact-refined-h",
        "source_bindings": {
            "arm210_replay_plan_sha256": plan_hash,
            "arm210_replay_receipt_sha256": receipt_hash,
            "key_mechanics_profile_sha256": profile_hash,
        },
        "source_skill": {
            "target_id": "H",
            "coordinate_frame": "board",
            "joint_order": list(joint_order),
            "skill_window_sequences": skill_sequences,
            "joint_space_samples": skill_window,
            "native_outcomes": outcomes,
        },
        "quality_gate": {
            "all_root_pose_invariants_passed": True,
            "root_pose_observation_count": len(targets),
            "maximum_joint_tracking_error_rad": tracking_maximum,
            "maximum_joint_tracking_error_allowed_rad": tracking_limit,
            "accepted_native_action_count": 2,
            "complete_release_action_count": 2,
        },
        "transfer_contract": {
            "representative_targets": list(REPRESENTATIVE_KEYS),
            "native_qualified_targets": ["H"],
            "pending_targets": [key for key in REPRESENTATIVE_KEYS if key != "H"],
            "transferable_components": [
                "board_frame_approach_hover_contact_retract_semantics",
                "provisional_contact_depth_and_release_policy",
                "quality_gate_structure",
            ],
            "joint_space_reuse_for_other_keys_permitted": False,
            "required_per_pending_target": [
                "derive_target_from_governed_board_frame_geometry",
                "solve_and_screen_fresh_inverse_kinematics",
                "qualify_collision_and_fixed_root_invariants",
                "pass_native_key_mechanics_evaluation",
            ],
        },
        "dataset_eligibility": {
            "eligible_as_skill_adaptation_seed": True,
            "eligible_as_multi_key_dataset": False,
            "eligible_for_physical_execution": False,
        },
        "authority": {
            "hardware": False,
            "motion": False,
            "physical_keyboard_qualification": False,
        },
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "single_simulated_source_key_and_single_retained_workcell_configuration",
            "mechanics_values_remain_synthetic_bounded_priors",
            "no_other_representative_key_has_native_contact_qualification",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    demonstration["demonstration_sha256"] = _canonical_sha256(demonstration)
    return demonstration


def build_representative_key_adaptation_campaign(
    demonstration: dict[str, Any],
    source_request: dict[str, Any],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Translate the governed H skill into per-target Cartesian requests."""

    demonstration_hash = _require_canonical_hash(
        demonstration, "demonstration_sha256", "ARM-211 demonstration"
    )
    request_hash = _require_canonical_hash(
        source_request, "request_sha256", "H Cartesian source request"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    transfer = demonstration.get("transfer_contract", {})
    skill = demonstration.get("source_skill", {})
    if (
        demonstration.get("schema") != GOVERNED_H_DEMONSTRATION_SCHEMA
        or demonstration.get("status")
        != "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_KEY_ADAPTATION"
        or demonstration.get("source_bindings", {}).get(
            "key_mechanics_profile_sha256"
        ) != profile_hash
        or transfer.get("joint_space_reuse_for_other_keys_permitted") is not False
        or transfer.get("pending_targets") != ["1", "SPACE", "ENTER", "PERIOD"]
        or skill.get("target_id") != "H"
        or skill.get("skill_window_sequences") != list(range(33, 40))
        or source_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or source_request.get("status") != "READY_FOR_IK_QUALIFICATION"
        or source_request.get("key_id") != "H"
        or source_request.get("profile_sha256") != profile_hash
        or source_request.get("source_joint_positions_reused") is not False
    ):
        raise MechanicsContractError("representative adaptation source boundary changed")

    joint_samples = skill.get("joint_space_samples")
    cartesian_samples = source_request.get("samples")
    if (
        not isinstance(joint_samples, list)
        or len(joint_samples) != 7
        or not isinstance(cartesian_samples, list)
        or len(cartesian_samples) <= 39
    ):
        raise MechanicsContractError("representative adaptation skill window changed")
    by_sequence = {row.get("sequence"): row for row in cartesian_samples}
    anchor = by_sequence.get(33, {}).get("expected_tool_tip_board_mm")
    h_center = mechanics_profile["regions"]["H"]["center_board_xy_mm"]
    if not isinstance(anchor, list) or len(anchor) != 3:
        raise MechanicsContractError("H Cartesian anchor is missing")
    anchor = [_finite_number(value, "H anchor coordinate") for value in anchor]
    anchor_offset = [anchor[0] - h_center[0], anchor[1] - h_center[1]]
    anchor_joint = joint_samples[0].get("joint_position_target_rad")
    if any(
        row.get("sequence") != sequence
        or row.get("target_id") != "H"
        or (
            sequence in (34, 36, 37, 39)
            and row.get("joint_position_target_rad") != anchor_joint
        )
        for sequence, row in zip(range(33, 40), joint_samples)
    ):
        raise MechanicsContractError("lifted H skill semantics changed")

    first_time = _finite_number(joint_samples[0].get("time_from_start_ns"), "skill time")
    target_plane = mechanics_profile["target_plane_z_board_mm"]
    pending = transfer["pending_targets"]
    requests = []
    for target_id in pending:
        region = mechanics_profile["regions"][target_id]
        center = region["center_board_xy_mm"]
        samples = []
        for local_sequence, source in enumerate(joint_samples):
            phase = source["phase"]
            if phase == "CONTACT":
                point = [center[0], center[1], target_plane - NATIVE_H_PRESS_DEPTH_MM]
            else:
                point = [
                    center[0] + anchor_offset[0],
                    center[1] + anchor_offset[1],
                    anchor[2],
                ]
            samples.append({
                "sequence": local_sequence,
                "source_sequence": source["sequence"],
                "time_from_start_ns": int(
                    _finite_number(source["time_from_start_ns"], "skill time") - first_time
                ),
                "phase": phase,
                "phase_endpoint": source["phase_endpoint"],
                "action_index": source["action_index"],
                "target_id": target_id,
                "expected_tool_tip_board_mm": point,
            })
        request = {
            "target_id": target_id,
            "target_center_board_xy_mm": list(center),
            "target_half_extent_mm": list(region["half_extent_mm"]),
            "sample_count": len(samples),
            "samples": samples,
            "source_joint_positions_reused": False,
            "route_connection_required": True,
            "ik_qualification_required": True,
            "collision_and_fixed_root_qualification_required": True,
            "native_key_mechanics_qualification_required": True,
        }
        request["request_sha256"] = _canonical_sha256(request)
        requests.append(request)

    campaign = {
        "schema": REPRESENTATIVE_KEY_ADAPTATION_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_TARGET_SPECIFIC_IK_QUALIFICATION",
        "source_bindings": {
            "arm211_demonstration_sha256": demonstration_hash,
            "h_cartesian_source_request_sha256": request_hash,
            "key_mechanics_profile_sha256": profile_hash,
        },
        "coordinate_frame": "board",
        "source_target_id": "H",
        "pending_targets": list(pending),
        "contact_depth_mm": NATIVE_H_PRESS_DEPTH_MM,
        "lifted_anchor_offset_from_key_center_xy_mm": anchor_offset,
        "requests": requests,
        "multi_key_dataset_ready": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "requests_are_cartesian_skill_inputs_not_ik_solutions",
            "park_to_skill_route_connections_are_not_yet_generated",
            "collision_fixed_root_and_native_contact_are_not_yet_qualified",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def build_representative_key_park_route_campaign(
    adaptation_campaign: dict[str, Any],
    source_request: dict[str, Any],
    baseline_selection: dict[str, Any],
) -> dict[str, Any]:
    """Connect each ARM-212 Cartesian skill to the retained park endpoint."""

    adaptation_hash = _require_canonical_hash(
        adaptation_campaign, "campaign_sha256", "ARM-212 adaptation campaign"
    )
    source_hash = _require_canonical_hash(
        source_request, "request_sha256", "H Cartesian source request"
    )
    selection_hash = _require_canonical_hash(
        baseline_selection, "selection_sha256", "ARM-206 baseline selection"
    )
    selected_id = baseline_selection.get("selected_candidate_id")
    selected = [
        item
        for item in baseline_selection.get("ranked_candidates", [])
        if item.get("candidate_id") == selected_id
    ]
    if (
        adaptation_campaign.get("schema")
        != REPRESENTATIVE_KEY_ADAPTATION_CAMPAIGN_SCHEMA
        or adaptation_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_TARGET_SPECIFIC_IK_QUALIFICATION"
        or adaptation_campaign.get("source_bindings", {}).get(
            "h_cartesian_source_request_sha256"
        ) != source_hash
        or adaptation_campaign.get("pending_targets")
        != ["1", "SPACE", "ENTER", "PERIOD"]
        or baseline_selection.get("schema")
        != KEY_MECHANICS_LEARNING_BASELINE_SELECTION_SCHEMA
        or baseline_selection.get("status")
        != "SELECTED_ZERO_AUTHORITY_SIMULATION_LEARNING_BASELINE"
        or len(selected) != 1
    ):
        raise MechanicsContractError("representative park-route lineage changed")
    route_policy = selected[0].get("route_shape_candidate", {})
    if (
        route_policy.get("xy_corridor_topology") != "DIRECT_LINEAR"
        or route_policy.get("corridor_height_board_mm") != 90.0
        or route_policy.get("corridor_height_ramp_fraction") != 0.25
        or route_policy.get("transit_resampling")
        != "ARC_LENGTH_PIECEWISE_LINEAR_WITH_SYMMETRIC_Z_RAMPS"
    ):
        raise MechanicsContractError("retained park-route policy changed")
    for document, label in (
        (adaptation_campaign, "ARM-212 adaptation campaign"),
        (source_request, "H Cartesian source request"),
        (baseline_selection, "ARM-206 baseline selection"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    source_samples = source_request.get("samples")
    if (
        source_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or not isinstance(source_samples, list)
        or len(source_samples) <= 33
        or any(
            not isinstance(sample, dict) or sample.get("sequence") != sequence
            for sequence, sample in enumerate(source_samples)
        )
        or source_samples[0].get("phase") != "PARK"
        or any(source_samples[index].get("phase") != "TRANSIT" for index in range(1, 34))
    ):
        raise MechanicsContractError("governed park-to-H timing domain changed")
    park = source_samples[0].get("expected_tool_tip_board_mm")
    if not isinstance(park, list) or len(park) != 3:
        raise MechanicsContractError("governed park endpoint is missing")
    park = [_finite_number(value, "park endpoint coordinate") for value in park]
    anchor_time = int(
        _finite_number(source_samples[33].get("time_from_start_ns"), "anchor time")
    )

    connected_requests = []
    arm212_requests = adaptation_campaign.get("requests")
    if not isinstance(arm212_requests, list) or len(arm212_requests) != 4:
        raise MechanicsContractError("ARM-212 request inventory changed")
    for target_id, skill_request in zip(
        adaptation_campaign["pending_targets"], arm212_requests, strict=True
    ):
        skill_hash = _require_canonical_hash(
            skill_request, "request_sha256", f"ARM-212 {target_id} request"
        )
        skill_samples = skill_request.get("samples")
        if (
            skill_request.get("target_id") != target_id
            or skill_request.get("source_joint_positions_reused") is not False
            or not isinstance(skill_samples, list)
            or len(skill_samples) != 7
            or any(sample.get("sequence") != sequence for sequence, sample in enumerate(skill_samples))
            or skill_samples[0].get("phase") != "TRANSIT"
        ):
            raise MechanicsContractError(f"ARM-212 {target_id} skill changed")
        anchor = skill_samples[0].get("expected_tool_tip_board_mm")
        if not isinstance(anchor, list) or len(anchor) != 3:
            raise MechanicsContractError(f"ARM-212 {target_id} anchor is missing")
        anchor = [_finite_number(value, "target anchor coordinate") for value in anchor]

        samples = [json.loads(json.dumps(source_samples[0]))]
        for sequence in range(1, 33):
            progress = sequence / 33.0
            if progress <= 0.25:
                z = park[2] + progress / 0.25 * (90.0 - park[2])
            elif progress >= 0.75:
                z = 90.0 + (progress - 0.75) / 0.25 * (anchor[2] - 90.0)
            else:
                z = 90.0
            samples.append({
                "sequence": sequence,
                "source_sequence": sequence,
                "time_from_start_ns": source_samples[sequence]["time_from_start_ns"],
                "phase": "TRANSIT",
                "phase_endpoint": False,
                "action_index": 0,
                "target_id": target_id,
                "expected_tool_tip_board_mm": [
                    park[0] + progress * (anchor[0] - park[0]),
                    park[1] + progress * (anchor[1] - park[1]),
                    z,
                ],
            })
        for offset, sample in enumerate(skill_samples):
            connected = json.loads(json.dumps(sample))
            connected["sequence"] = 33 + offset
            connected["time_from_start_ns"] = anchor_time + int(
                _finite_number(sample["time_from_start_ns"], "skill time")
            )
            samples.append(connected)

        request = {
            "schema": TCP_CARTESIAN_SCHEDULE_SCHEMA,
            "status": "READY_FOR_TARGET_SPECIFIC_IK_QUALIFICATION",
            "key_id": target_id,
            "coordinate_frame": "board",
            "source_arm212_request_sha256": skill_hash,
            "source_h_cartesian_request_sha256": source_hash,
            "source_arm206_baseline_selection_sha256": selection_hash,
            "route_shape_candidate_id": selected_id,
            "route_shape_candidate": route_policy,
            "park_endpoint_preserved": True,
            "skill_samples_preserved": True,
            "route_connection_materialized": True,
            "source_joint_positions_reused": False,
            "joint_positions_included": False,
            "ik_qualification_required": True,
            "collision_and_fixed_root_qualification_required": True,
            "native_key_mechanics_qualification_required": True,
            "sample_count": len(samples),
            "total_time_ns": samples[-1]["time_from_start_ns"],
            "route_domain_sequences": list(range(1, 33)),
            "skill_domain_sequences": list(range(33, 40)),
            "samples": samples,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "gate_promotions": [],
            "limitations": [
                "connected_cartesian_request_is_not_an_ik_solution",
                "route_is_a_selected_policy_transfer_requiring_fresh_target_qualification",
                "continuous_collision_clearance_and_native_contact_are_not_proven",
                "no_hardware_motion_or_physical_keyboard_authority",
            ],
        }
        request["request_sha256"] = _canonical_sha256(request)
        connected_requests.append(request)

    campaign = {
        "schema": REPRESENTATIVE_KEY_PARK_ROUTE_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_ROUTE_IK_QUALIFICATION",
        "source_bindings": {
            "arm212_adaptation_campaign_sha256": adaptation_hash,
            "h_cartesian_source_request_sha256": source_hash,
            "arm206_baseline_selection_sha256": selection_hash,
        },
        "selected_route_policy": route_policy,
        "park_endpoint_board_mm": park,
        "pending_targets": list(adaptation_campaign["pending_targets"]),
        "requests": connected_requests,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "fresh_target_specific_ik_is_required",
            "fresh_collision_fixed_root_and_native_contact_qualification_are_required",
            "no_multi_key_dataset_or_physical_execution_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def qualify_representative_key_park_routes_ik(
    route_campaign: dict[str, Any],
    h_source_request: dict[str, Any],
    source_bundle: dict[str, Any],
    mechanics_profile: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    """Run fresh canonical IK for every ARM-213 target route."""

    campaign_hash = _require_canonical_hash(
        route_campaign, "campaign_sha256", "ARM-213 route campaign"
    )
    request_hash = _require_canonical_hash(
        h_source_request, "request_sha256", "H Cartesian source request"
    )
    bundle_hash = _require_canonical_hash(
        source_bundle, "bundle_sha256", "canonical IK source bundle"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    if (
        route_campaign.get("schema") != REPRESENTATIVE_KEY_PARK_ROUTE_CAMPAIGN_SCHEMA
        or route_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_ROUTE_IK_QUALIFICATION"
        or route_campaign.get("source_bindings", {}).get(
            "h_cartesian_source_request_sha256"
        ) != request_hash
        or h_source_request.get("profile_sha256") != profile_hash
        or route_campaign.get("pending_targets")
        != ["1", "SPACE", "ENTER", "PERIOD"]
    ):
        raise MechanicsContractError("representative IK campaign lineage changed")
    for document, label in (
        (route_campaign, "ARM-213 route campaign"),
        (h_source_request, "H Cartesian source request"),
        (source_bundle, "canonical IK source bundle"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    try:
        from rocell.application._pinned_model import load_pinned_urdf
        from rocell.application.context import load_simulation_context
        from rocell.application.trajectory_simulation import (
            CartesianRouteWaypoint,
            TrajectorySimulationPolicy,
            evaluate_joint_trajectory_solution,
        )
        from rocell.application.typing_trajectory_ik_screen_v1 import (
            canonicalize_typing_ik_evidence_v1,
        )
        from rocell.geometry import JointPosition, Point3Mm
        from rocell.kinematics import (
            ARM_JOINT_NAMES,
            BoardToolTipTarget,
            IkOptions,
            RoArmM3NumericalIk,
        )
        from rocell.motion import MotionPhase
        from rocell.simulation.virtual_profile import load_virtual_commissioning_profile
    except ImportError as exc:
        raise MechanicsContractError(
            "canonical IK runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    root = workspace.resolve(strict=True)
    context = load_simulation_context(
        root, root / "software/config/system_manifest.json"
    )
    virtual_profile = load_virtual_commissioning_profile(context)
    if (
        virtual_profile.source_sha256
        != source_bundle.get("source", {}).get("virtual_profile_sha256")
    ):
        raise MechanicsContractError("virtual commissioning profile lineage changed")
    scenario = context.scenario
    model = load_pinned_urdf(scenario.model_path, scenario.model_sha256).model
    source_samples = source_bundle.get("samples")
    initial_seed = (
        source_samples[0].get("joint_positions_rad")
        if isinstance(source_samples, list) and source_samples
        else None
    )
    if not isinstance(initial_seed, dict) or tuple(initial_seed) != ARM_JOINT_NAMES:
        raise MechanicsContractError("source bundle lacks the canonical initial joint seed")
    initial_seed = {
        name: _finite_number(initial_seed[name], f"initial seed {name}")
        for name in ARM_JOINT_NAMES
    }
    bounds = scenario.controller_joint_intersection_rad
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=30.0,
        maximum_joint_step_rad=0.35,
        minimum_normalized_arm_joint_margin=0.01,
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=256,
        maximum_total_ik_solves=256,
        maximum_route_targets=2,
    )

    results = []
    requests = route_campaign.get("requests")
    if not isinstance(requests, list) or len(requests) != 4:
        raise MechanicsContractError("representative route request inventory changed")
    for target_id, request in zip(
        route_campaign["pending_targets"], requests, strict=True
    ):
        claimed_request_hash = _require_canonical_hash(
            request, "request_sha256", f"ARM-213 {target_id} request"
        )
        samples = request.get("samples")
        if (
            request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
            or request.get("status") != "READY_FOR_TARGET_SPECIFIC_IK_QUALIFICATION"
            or request.get("key_id") != target_id
            or request.get("source_joint_positions_reused") is not False
            or request.get("joint_positions_included") is not False
            or request.get("hardware_access") is not False
            or request.get("hardware_writes") != 0
            or request.get("physical_movements") != 0
            or request.get("controller_commands") != []
            or not isinstance(samples, list)
            or len(samples) != 40
            or any(sample.get("sequence") != sequence for sequence, sample in enumerate(samples))
        ):
            raise MechanicsContractError(f"ARM-213 {target_id} request changed")

        previous = dict(initial_seed)
        solver = RoArmM3NumericalIk(
            model=model,
            board_T_world=virtual_profile.study_input.board_T_vendor_world,
            hand_tcp_to_tip_z_mm=-float(
                virtual_profile.study_input.keyboard_tool_length_mm
            ),
            fixed_gripper_position=scenario.fixed_gripper_position,
            ready_arm_joint_positions={
                name: JointPosition.radians(value)
                for name, value in previous.items()
            },
            gripper_bounds_rad=scenario.controller_gripper_intersection_rad,
            options=IkOptions(
                max_attempts=scenario.ik_policy.max_attempts,
                max_iterations_per_attempt=scenario.ik_policy.max_iterations_per_attempt,
            ),
            joint_bounds_rad=bounds,
        )
        joint_results = []
        previous_point = None
        for sample in samples:
            coordinates = sample.get("expected_tool_tip_board_mm")
            if not isinstance(coordinates, list) or len(coordinates) != 3:
                raise MechanicsContractError(
                    f"ARM-213 {target_id} request lacks a Cartesian point"
                )
            point = Point3Mm(
                "board",
                *[
                    _finite_number(value, "representative route coordinate")
                    for value in coordinates
                ],
            )
            distance = (
                0.0
                if previous_point is None
                else math.dist(
                    (previous_point.x, previous_point.y, previous_point.z),
                    (point.x, point.y, point.z),
                )
            )
            waypoint = CartesianRouteWaypoint(
                sequence=sample["sequence"],
                phase=MotionPhase(sample["phase"]),
                action_index=sample["action_index"],
                semantic_target=sample["target_id"],
                point_board=point,
                distance_from_previous_mm=distance,
                source_geometric_sequence=sample["sequence"],
                source_check_id=claimed_request_hash,
                source_path_check_passed=True,
                inherited_collision_ids=(),
                phase_endpoint=sample["phase_endpoint"],
            )
            solved = solver.solve(
                BoardToolTipTarget(point),
                seed_joint_positions=({
                    name: JointPosition.radians(value)
                    for name, value in previous.items()
                },),
            )
            evaluated = evaluate_joint_trajectory_solution(
                waypoint, solved, solver, bounds, previous, policy
            )
            canonical = canonicalize_typing_ik_evidence_v1(evaluated.to_dict())
            joint_results.append(canonical)
            if not evaluated.accepted:
                break
            previous = dict(evaluated.solution_arm_joint_positions_rad)
            previous_point = point

        all_accepted = len(joint_results) == len(samples) and all(
            row["accepted"] for row in joint_results
        )
        accepted = [row for row in joint_results if row["accepted"]]
        target_result = {
            "target_id": target_id,
            "source_request_sha256": claimed_request_hash,
            "status": (
                "READY_FOR_COLLISION_AND_FIXED_ROOT_QUALIFICATION"
                if all_accepted
                else "BLOCKED_CANONICAL_IK_OR_CONTINUITY"
            ),
            "sample_count": len(samples),
            "evaluated_sample_count": len(joint_results),
            "ik_all_samples_accepted": all_accepted,
            "first_rejected_sequence": next(
                (
                    row.get("sequence")
                    for row in joint_results
                    if not row.get("accepted")
                ),
                None,
            ),
            "joint_results": joint_results,
            "metrics": {
                "maximum_position_error_mm": max(
                    (row["position_error_mm"] for row in accepted), default=None
                ),
                "minimum_normalized_arm_joint_margin": min(
                    (
                        row["minimum_normalized_arm_joint_margin"]
                        for row in accepted
                    ),
                    default=None,
                ),
                "maximum_adjacent_joint_delta_rad": max(
                    (
                        row["maximum_joint_delta_rad"]
                        for row in accepted
                    ),
                    default=None,
                ),
            },
        }
        target_result["result_sha256"] = _canonical_sha256(target_result)
        results.append(target_result)

    all_accepted = all(result["ik_all_samples_accepted"] for result in results)
    campaign = {
        "schema": REPRESENTATIVE_KEY_IK_CAMPAIGN_SCHEMA,
        "status": (
            "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_COLLISION_QUALIFICATION"
            if all_accepted
            else "BLOCKED_REPRESENTATIVE_IK_OR_CONTINUITY"
        ),
        "source_bindings": {
            "arm213_route_campaign_sha256": campaign_hash,
            "h_cartesian_source_request_sha256": request_hash,
            "canonical_ik_source_bundle_sha256": bundle_hash,
            "key_mechanics_profile_sha256": profile_hash,
            "virtual_profile_sha256": virtual_profile.source_sha256,
            "kinematic_model_sha256": scenario.model_sha256,
        },
        "initial_seed_source": "SOURCE_BUNDLE_SAMPLE_0_ONLY",
        "source_h_joint_solutions_reused": False,
        "policy": policy.to_dict(),
        "target_count": len(results),
        "accepted_target_count": sum(
            result["ik_all_samples_accepted"] for result in results
        ),
        "results": results,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "ik_and_discrete_continuity_do_not_prove_collision_clearance",
            "collision_fixed_root_and_native_contact_qualification_remain_separate",
            "source_bundle_contributes_only_initial_seed_and_model_lineage",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def build_representative_key_collision_replay_campaign(
    ik_campaign: dict[str, Any],
    source_bundle: dict[str, Any],
    collision_candidate: dict[str, Any],
    toolchain_lock: dict[str, Any],
) -> dict[str, Any]:
    """Compile ARM-214 routes into bounded fixed-root collision replays."""

    campaign_hash = _require_canonical_hash(
        ik_campaign, "campaign_sha256", "ARM-214 IK campaign"
    )
    bundle_hash = _require_canonical_hash(
        source_bundle, "bundle_sha256", "canonical IK source bundle"
    )
    candidate_hash = _require_canonical_hash(
        collision_candidate, "candidate_sha256", "collision candidate"
    )
    toolchain_hash = _canonical_sha256(toolchain_lock)
    if (
        ik_campaign.get("schema") != REPRESENTATIVE_KEY_IK_CAMPAIGN_SCHEMA
        or ik_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_COLLISION_QUALIFICATION"
        or ik_campaign.get("accepted_target_count") != 4
        or ik_campaign.get("target_count") != 4
        or ik_campaign.get("source_h_joint_solutions_reused") is not False
        or ik_campaign.get("source_bindings", {}).get(
            "canonical_ik_source_bundle_sha256"
        )
        != bundle_hash
    ):
        raise MechanicsContractError("representative collision campaign lineage changed")
    if (
        collision_candidate.get("schema")
        != "tactevra.simulation_collision_candidate.v1"
        or collision_candidate.get("scope")
        != "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
    ):
        raise MechanicsContractError("collision candidate boundary changed")
    blockers = collision_candidate.get("blockers")
    robot_bodies = collision_candidate.get("robot_bodies")
    workcell_bodies = collision_candidate.get("workcell_bodies")
    if (
        not isinstance(blockers, list)
        or not blockers
        or not all(isinstance(item, str) and item for item in blockers)
        or not isinstance(robot_bodies, list)
        or not robot_bodies
        or not isinstance(workcell_bodies, list)
        or not workcell_bodies
    ):
        raise MechanicsContractError("collision candidate coverage is absent")
    if (
        toolchain_lock.get("schema") != "rocell.isaac_sim_toolchain_lock.v1"
        or toolchain_lock.get("selection_status") != "SELECTED"
        or toolchain_lock.get("hardware_access") is not False
        or toolchain_lock.get("physical_authority") is not False
        or toolchain_lock.get("wire_commands") != []
    ):
        raise MechanicsContractError("Isaac toolchain lock is not selected zero-authority")
    for document, label in (
        (ik_campaign, "ARM-214 IK campaign"),
        (source_bundle, "canonical IK source bundle"),
        (collision_candidate, "collision candidate"),
    ):
        if (
            document.get("hardware_access", False) is not False
            or document.get("physical_authority") is not False
            or document.get(
                "hardware_write_count", document.get("hardware_writes")
            )
            != 0
            or document.get(
                "physical_movement_count", document.get("physical_movements")
            )
            != 0
            or document.get("commands", document.get("controller_commands")) != []
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    try:
        from rocell.application.bounded_segment_collision_qualification import (
            BoundedSegmentSamplingPolicy,
            build_bounded_joint_sample_plan_from_results,
        )
        from rocell.kinematics import ARM_JOINT_NAMES
    except ImportError as exc:
        raise MechanicsContractError(
            "bounded collision runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    samples = source_bundle.get("samples")
    initial_seed = (
        samples[0].get("joint_positions_rad")
        if isinstance(samples, list) and samples
        else None
    )
    if not isinstance(initial_seed, dict) or tuple(initial_seed) != ARM_JOINT_NAMES:
        raise MechanicsContractError("source bundle lacks the canonical initial joint seed")
    initial_seed = {
        name: _finite_number(initial_seed[name], f"initial seed {name}")
        for name in ARM_JOINT_NAMES
    }
    policy = BoundedSegmentSamplingPolicy(
        maximum_joint_step_rad=0.05,
        maximum_samples=256,
    )
    fixed_base_contract = {
        "mechanism": "USD_FIXED_JOINT_TO_WORLD",
        "articulation_path": "/roarm_m3",
        "base_body_name": "base_link",
        "author_before_physics_initialization": True,
        "requested_placement_is_world_anchor": True,
    }
    root_pose_invariant = {
        "translation_tolerance_mm": 0.05,
        "orientation_tolerance_deg": 0.1,
        "required_at_admission": True,
        "required_after_every_sample": True,
        "failure_behavior": "ERROR_NO_ACCEPTED_COLLISION_RECEIPT",
    }
    results = ik_campaign.get("results")
    if not isinstance(results, list) or len(results) != 4:
        raise MechanicsContractError("representative IK target coverage changed")
    target_plans = []
    for expected_target, result in zip(
        ("1", "SPACE", "ENTER", "PERIOD"), results, strict=True
    ):
        result_hash = _require_canonical_hash(
            result, "result_sha256", f"ARM-214 {expected_target} result"
        )
        joint_results = result.get("joint_results")
        if (
            result.get("target_id") != expected_target
            or result.get("status")
            != "READY_FOR_COLLISION_AND_FIXED_ROOT_QUALIFICATION"
            or result.get("sample_count") != 40
            or result.get("evaluated_sample_count") != 40
            or result.get("ik_all_samples_accepted") is not True
            or not isinstance(joint_results, list)
            or len(joint_results) != 40
        ):
            raise MechanicsContractError(
                f"ARM-214 {expected_target} result is not collision-ready"
            )
        bounded = build_bounded_joint_sample_plan_from_results(
            initial_seed, joint_results, policy
        )
        target_plan = {
            "target_id": expected_target,
            "status": "READY_FOR_FIXED_ROOT_NATIVE_COLLISION_REPLAY",
            "source_ik_result_sha256": result_hash,
            "source_request_sha256": result["source_request_sha256"],
            "source_joint_result_count": len(joint_results),
            "joint_order": list(ARM_JOINT_NAMES),
            "bounded_sample_count": len(bounded),
            "bounded_samples": [item.to_dict() for item in bounded],
            "fixed_base_contract": dict(fixed_base_contract),
            "root_pose_invariant": dict(root_pose_invariant),
            "collision_scopes": [
                "ROBOT_SELF_COLLISION",
                "ROBOT_TO_WORKCELL",
                "ROBOT_TOOL_CAMERA_SUPPORT_DIAGNOSTIC_WHERE_BOUND",
            ],
            "diagnostic_only": True,
            "installed_collision_qualified": False,
            "continuous_collision_proven": False,
            "native_contact_replay_authorized": False,
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "gate_promotions": [],
        }
        target_plan["plan_sha256"] = _canonical_sha256(target_plan)
        target_plans.append(target_plan)

    campaign = {
        "schema": REPRESENTATIVE_KEY_COLLISION_REPLAY_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_FIXED_ROOT_NATIVE_COLLISION_REPLAY",
        "source_bindings": {
            "arm214_ik_campaign_sha256": campaign_hash,
            "canonical_ik_source_bundle_sha256": bundle_hash,
            "collision_candidate_sha256": candidate_hash,
            "isaac_toolchain_lock_sha256": toolchain_hash,
        },
        "bounded_sampling_policy": policy.to_dict(),
        "fixed_base_contract": fixed_base_contract,
        "root_pose_invariant": root_pose_invariant,
        "collision_candidate_blockers": list(blockers),
        "target_count": len(target_plans),
        "target_plans": target_plans,
        "native_replay_executed": False,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "campaign_compilation_does_not_execute_native_collision_queries",
            "bounded_sampling_is_not_continuous_swept_volume_proof",
            "exploratory_collision_candidate_is_uninstalled",
            "native_contact_and_physical_keyboard_authority_remain_separate",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def materialize_representative_key_native_collision_inputs(
    route_campaign: dict[str, Any],
    ik_campaign: dict[str, Any],
    collision_campaign: dict[str, Any],
    source_bundle: dict[str, Any],
    collision_candidate: dict[str, Any],
    toolchain_lock: dict[str, Any],
    accepted_pair_policy: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Materialize truthful per-target inputs for direct LM2 native replay."""

    route_hash = _require_canonical_hash(
        route_campaign, "campaign_sha256", "ARM-213 route campaign"
    )
    ik_hash = _require_canonical_hash(
        ik_campaign, "campaign_sha256", "ARM-214 IK campaign"
    )
    collision_hash = _require_canonical_hash(
        collision_campaign, "campaign_sha256", "ARM-215 collision campaign"
    )
    bundle_hash = _require_canonical_hash(
        source_bundle, "bundle_sha256", "canonical IK source bundle"
    )
    candidate_hash = _require_canonical_hash(
        collision_candidate, "candidate_sha256", "collision candidate"
    )
    policy_hash = _require_canonical_hash(
        accepted_pair_policy, "policy_sha256", "accepted collision pair policy"
    )
    toolchain_hash = _canonical_sha256(toolchain_lock)
    if (
        route_campaign.get("schema") != REPRESENTATIVE_KEY_PARK_ROUTE_CAMPAIGN_SCHEMA
        or ik_campaign.get("schema") != REPRESENTATIVE_KEY_IK_CAMPAIGN_SCHEMA
        or collision_campaign.get("schema")
        != REPRESENTATIVE_KEY_COLLISION_REPLAY_CAMPAIGN_SCHEMA
        or collision_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_FIXED_ROOT_NATIVE_COLLISION_REPLAY"
        or ik_campaign.get("source_bindings", {}).get(
            "arm213_route_campaign_sha256"
        )
        != route_hash
        or collision_campaign.get("source_bindings", {}).get(
            "arm214_ik_campaign_sha256"
        )
        != ik_hash
        or collision_campaign.get("source_bindings", {}).get(
            "canonical_ik_source_bundle_sha256"
        )
        != bundle_hash
        or collision_campaign.get("source_bindings", {}).get(
            "collision_candidate_sha256"
        )
        != candidate_hash
        or collision_campaign.get("source_bindings", {}).get(
            "isaac_toolchain_lock_sha256"
        )
        != toolchain_hash
        or accepted_pair_policy.get("collision_candidate_sha256") != candidate_hash
        or accepted_pair_policy.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY"
    ):
        raise MechanicsContractError("representative native admission lineage changed")
    for document, label in (
        (route_campaign, "ARM-213 route campaign"),
        (ik_campaign, "ARM-214 IK campaign"),
        (collision_campaign, "ARM-215 collision campaign"),
        (source_bundle, "canonical IK source bundle"),
        (accepted_pair_policy, "accepted pair policy"),
    ):
        if (
            document.get("hardware_access", False) is not False
            or document.get("physical_authority", False) is not False
            or document.get("hardware_writes", 0) != 0
            or document.get("physical_movements", 0) != 0
            or document.get("controller_commands", []) != []
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    source_samples = source_bundle.get("samples")
    initial_seed = (
        source_samples[0].get("joint_positions_rad")
        if isinstance(source_samples, list) and source_samples
        else None
    )
    if not isinstance(initial_seed, dict):
        raise MechanicsContractError("canonical IK source seed is absent")
    route_requests = route_campaign.get("requests")
    ik_results = ik_campaign.get("results")
    target_plans = collision_campaign.get("target_plans")
    if not all(isinstance(items, list) and len(items) == 4 for items in (
        route_requests, ik_results, target_plans
    )):
        raise MechanicsContractError("representative target coverage changed")

    station_bodies = [
        body for body in collision_candidate.get("workcell_bodies", [])
        if isinstance(body, dict)
        and str(body.get("body_id", "")).startswith("workcell:station:")
    ]
    if not station_bodies:
        raise MechanicsContractError("station planning regions are absent")
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for expected_target, cartesian, ik_result, target_plan in zip(
        ("1", "SPACE", "ENTER", "PERIOD"),
        route_requests,
        ik_results,
        target_plans,
        strict=True,
    ):
        request_hash = _require_canonical_hash(
            cartesian, "request_sha256", f"ARM-213 {expected_target} request"
        )
        result_hash = _require_canonical_hash(
            ik_result, "result_sha256", f"ARM-214 {expected_target} result"
        )
        plan_hash = _require_canonical_hash(
            target_plan, "plan_sha256", f"ARM-215 {expected_target} plan"
        )
        if (
            cartesian.get("key_id") != expected_target
            or ik_result.get("target_id") != expected_target
            or target_plan.get("target_id") != expected_target
            or ik_result.get("source_request_sha256") != request_hash
            or target_plan.get("source_request_sha256") != request_hash
            or target_plan.get("source_ik_result_sha256") != result_hash
            or target_plan.get("status")
            != "READY_FOR_FIXED_ROOT_NATIVE_COLLISION_REPLAY"
        ):
            raise MechanicsContractError(
                f"representative {expected_target} target lineage changed"
            )
        ik_receipt = {
            "schema": TCP_IK_SCREEN_SCHEMA,
            "status": "READY_FOR_COLLISION_QUALIFICATION",
            "source_request_sha256": request_hash,
            "source_bundle_sha256": bundle_hash,
            "virtual_profile_sha256": ik_campaign["source_bindings"][
                "virtual_profile_sha256"
            ],
            "initial_seed_joint_positions_rad": dict(initial_seed),
            "sample_count": ik_result["sample_count"],
            "evaluated_sample_count": ik_result["evaluated_sample_count"],
            "ik_all_samples_accepted": ik_result["ik_all_samples_accepted"],
            "joint_results": ik_result["joint_results"],
            "source_arm214_result_sha256": result_hash,
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "gate_promotions": [],
        }
        ik_receipt["receipt_sha256"] = _canonical_sha256(ik_receipt)
        raw_request = build_robot_tcp_collision_replay_request(
            ik_receipt, collision_candidate, toolchain_lock
        )
        if (
            raw_request.get("bounded_samples") != target_plan.get("bounded_samples")
            or raw_request.get("bounded_sample_count")
            != target_plan.get("bounded_sample_count")
        ):
            raise MechanicsContractError(
                f"representative {expected_target} bounded replay changed"
            )
        policy_request = bind_collision_pair_policy_request(
            raw_request, accepted_pair_policy
        )
        contact_samples = [
            sample for sample in cartesian.get("samples", [])
            if sample.get("phase") == "CONTACT"
            and sample.get("phase_endpoint") is True
        ]
        if not contact_samples:
            raise MechanicsContractError(
                f"representative {expected_target} contact endpoint is absent"
            )
        contact_point = contact_samples[0].get("expected_tool_tip_board_mm")
        occupied = [
            body["body_id"] for body in station_bodies
            if any(
                _point_inside_oriented_box(
                    contact_point,
                    primitive,
                    label=f"station region {body['body_id']}",
                )
                for primitive in body.get("primitives", [])
            )
        ]
        if len(occupied) != 1:
            raise MechanicsContractError(
                f"representative {expected_target} station binding is ambiguous"
            )
        station_predicate = build_station_route_predicate(
            cartesian, collision_candidate, {expected_target: occupied}
        )
        if station_predicate.get("status") != "PASS":
            raise MechanicsContractError(
                f"representative {expected_target} station predicate failed"
            )
        replay_plan = {
            "schema": REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA,
            "status": "READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY",
            "target_id": expected_target,
            "source_arm215_campaign_sha256": collision_hash,
            "source_arm215_target_plan_sha256": plan_hash,
            "source_request_sha256": request_hash,
            "source_ik_receipt_sha256": ik_receipt["receipt_sha256"],
            "source_collision_request_sha256": policy_request["request_sha256"],
            "source_station_route_predicate_sha256": station_predicate[
                "predicate_sha256"
            ],
            "source_bounded_sample_count": target_plan["bounded_sample_count"],
            "fixed_base_contract": target_plan["fixed_base_contract"],
            "root_pose_invariant": target_plan["root_pose_invariant"],
            "rotation_serialization": {
                "matrix_layout": "ROW_MAJOR_3X3",
                "semantics": "RIGHT_HANDED_ACTIVE_COLUMN_VECTOR",
                "gf_row_vector_storage_transposed": True,
            },
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "gate_promotions": [],
        }
        replay_plan["plan_sha256"] = _canonical_sha256(replay_plan)
        target_dir = root / expected_target.lower()
        target_dir.mkdir(parents=True, exist_ok=True)
        documents = {
            "cartesian_request.json": cartesian,
            "ik_receipt.json": ik_receipt,
            "collision_request.json": policy_request,
            "station_route_predicate.json": station_predicate,
            "fixed_base_replay_plan.json": replay_plan,
        }
        for name, document in documents.items():
            (target_dir / name).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        entries.append({
            "target_id": expected_target,
            "directory": expected_target.lower(),
            "source_arm215_target_plan_sha256": plan_hash,
            "document_hashes": {
                "cartesian_request.json": request_hash,
                "ik_receipt.json": ik_receipt["receipt_sha256"],
                "collision_request.json": policy_request["request_sha256"],
                "station_route_predicate.json": station_predicate[
                    "predicate_sha256"
                ],
                "fixed_base_replay_plan.json": replay_plan["plan_sha256"],
            },
            "bounded_sample_count": target_plan["bounded_sample_count"],
            "station_region_id": occupied[0],
        })
    manifest = {
        "schema": REPRESENTATIVE_KEY_NATIVE_COLLISION_MANIFEST_SCHEMA,
        "status": "READY_FOR_SELECTED_ZERO_AUTHORITY_NATIVE_REPLAY",
        "source_bindings": {
            "arm213_route_campaign_sha256": route_hash,
            "arm214_ik_campaign_sha256": ik_hash,
            "arm215_collision_campaign_sha256": collision_hash,
            "canonical_ik_source_bundle_sha256": bundle_hash,
            "collision_candidate_sha256": candidate_hash,
            "accepted_collision_pair_policy_sha256": policy_hash,
            "isaac_toolchain_lock_sha256": toolchain_hash,
        },
        "target_count": len(entries),
        "entries": entries,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def aggregate_representative_key_native_collision_campaign(
    manifest: dict[str, Any],
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify and aggregate all representative native collision receipts."""

    manifest_hash = _require_canonical_hash(
        manifest, "manifest_sha256", "representative native collision manifest"
    )
    entries = manifest.get("entries")
    if (
        manifest.get("schema") != REPRESENTATIVE_KEY_NATIVE_COLLISION_MANIFEST_SCHEMA
        or manifest.get("status") != "READY_FOR_SELECTED_ZERO_AUTHORITY_NATIVE_REPLAY"
        or manifest.get("target_count") != 4
        or not isinstance(entries, list)
        or len(entries) != 4
        or manifest.get("hardware_access") is not False
        or manifest.get("physical_authority") is not False
        or manifest.get("hardware_writes") != 0
        or manifest.get("physical_movements") != 0
        or manifest.get("controller_commands") != []
    ):
        raise MechanicsContractError("representative native manifest boundary changed")
    receipt_by_target = {
        receipt.get("representative_target_id"): receipt for receipt in receipts
    }
    expected_targets = ["1", "SPACE", "ENTER", "PERIOD"]
    if (
        len(receipts) != 4
        or len(receipt_by_target) != 4
        or list(receipt_by_target) != expected_targets
        or [entry.get("target_id") for entry in entries] != expected_targets
    ):
        raise MechanicsContractError("representative native receipt coverage changed")

    results = []
    total_samples = 0
    for entry in entries:
        target_id = entry["target_id"]
        receipt = receipt_by_target[target_id]
        receipt_hash = _require_canonical_hash(
            receipt, "receipt_sha256", f"representative {target_id} native receipt"
        )
        document_hashes = entry.get("document_hashes")
        root_invariant = receipt.get("root_pose_invariant")
        if (
            receipt.get("schema") != REPRESENTATIVE_KEY_NATIVE_COLLISION_RECEIPT_SCHEMA
            or receipt.get("status") != "DIAGNOSTIC_OVERLAPS_OBSERVED"
            or receipt.get("source_arm215_campaign_sha256")
            != manifest.get("source_bindings", {}).get(
                "arm215_collision_campaign_sha256"
            )
            or not isinstance(document_hashes, dict)
            or receipt.get("source_arm215_target_plan_sha256")
            != entry.get("source_arm215_target_plan_sha256")
            or receipt.get("source_representative_plan_mutated") is not False
            or receipt.get("bounded_sample_count")
            != entry.get("bounded_sample_count")
            or receipt.get("physical_solid_blocker_pair_count") != 0
            or receipt.get("planning_envelope_blocker_pair_count") != 0
            or receipt.get("unreviewed_blocker_pair_count") != 0
            or not isinstance(root_invariant, dict)
            or root_invariant.get("status") != "PASS"
            or root_invariant.get("observation_count")
            != receipt.get("bounded_sample_count") + 1
            or receipt.get("hardware_access") is not False
            or receipt.get("physical_authority") is not False
            or receipt.get("hardware_writes") != 0
            or receipt.get("physical_movements") != 0
            or receipt.get("controller_commands") != []
        ):
            raise MechanicsContractError(
                f"representative {target_id} native receipt boundary changed"
            )
        total_samples += receipt["bounded_sample_count"]
        results.append({
            "target_id": target_id,
            "receipt_sha256": receipt_hash,
            "source_arm215_target_plan_sha256": receipt[
                "source_arm215_target_plan_sha256"
            ],
            "bounded_sample_count": receipt["bounded_sample_count"],
            "unique_collision_pair_count": receipt["unique_collision_pair_count"],
            "policy_excluded_pair_count": receipt[
                "policy_excluded_pair_count"
            ],
            "physical_solid_blocker_pair_count": 0,
            "planning_envelope_blocker_pair_count": 0,
            "unreviewed_blocker_pair_count": 0,
            "root_pose_invariant_status": "PASS",
        })
    campaign = {
        "schema": REPRESENTATIVE_KEY_NATIVE_COLLISION_CAMPAIGN_SCHEMA,
        "status": "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_COLLISION_CAMPAIGN",
        "source_manifest_sha256": manifest_hash,
        "source_bindings": dict(manifest["source_bindings"]),
        "target_count": 4,
        "total_bounded_sample_count": total_samples,
        "results": results,
        "native_replay_executed": True,
        "fixed_root_invariant_passed": True,
        "physical_solid_blocker_pair_count": 0,
        "planning_envelope_blocker_pair_count": 0,
        "unreviewed_blocker_pair_count": 0,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "physical_keyboard_qualified": False,
        "limitations": [
            "discrete_replay_does_not_prove_continuous_clearance",
            "exploratory_collision_candidate_is_uninstalled",
            "simulation_does_not_authorize_physical_motion",
        ],
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def build_representative_key_native_mechanics_campaign(
    route_campaign: dict[str, Any],
    ik_campaign: dict[str, Any],
    native_collision_manifest: dict[str, Any],
    native_collision_receipts: list[dict[str, Any]],
    mechanics_profile: dict[str, Any],
    virtual_profile_bytes: bytes,
    drive_profile: dict[str, Any],
    drive_profile_bytes: bytes,
    robot_usd_bytes: bytes,
    import_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Compile four collision-admitted routes into native mechanics replays."""

    route_hash = _require_canonical_hash(
        route_campaign, "campaign_sha256", "ARM-213 route campaign"
    )
    ik_hash = _require_canonical_hash(
        ik_campaign, "campaign_sha256", "ARM-214 IK campaign"
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    import_hash = _require_canonical_hash(
        import_receipt, "receipt_sha256", "robot import receipt"
    )
    native_collision = aggregate_representative_key_native_collision_campaign(
        native_collision_manifest, native_collision_receipts
    )
    native_hash = native_collision["campaign_sha256"]
    manifest_hash = native_collision["source_manifest_sha256"]
    virtual_hash = hashlib.sha256(virtual_profile_bytes).hexdigest()
    drive_hash = hashlib.sha256(drive_profile_bytes).hexdigest()
    robot_hash = hashlib.sha256(robot_usd_bytes).hexdigest()
    bindings = native_collision_manifest.get("source_bindings", {})
    ik_bindings = ik_campaign.get("source_bindings", {})
    if (
        route_campaign.get("schema") != REPRESENTATIVE_KEY_PARK_ROUTE_CAMPAIGN_SCHEMA
        or route_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_ROUTE_IK_QUALIFICATION"
        or route_campaign.get("pending_targets") != ["1", "SPACE", "ENTER", "PERIOD"]
        or ik_campaign.get("schema") != REPRESENTATIVE_KEY_IK_CAMPAIGN_SCHEMA
        or ik_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_COLLISION_QUALIFICATION"
        or ik_campaign.get("accepted_target_count") != 4
        or ik_campaign.get("source_h_joint_solutions_reused") is not False
        or ik_bindings.get("arm213_route_campaign_sha256") != route_hash
        or ik_bindings.get("key_mechanics_profile_sha256") != profile_hash
        or ik_bindings.get("virtual_profile_sha256") != virtual_hash
        or bindings.get("arm213_route_campaign_sha256") != route_hash
        or bindings.get("arm214_ik_campaign_sha256") != ik_hash
        or native_collision.get("status")
        != "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_COLLISION_CAMPAIGN"
        or native_collision.get("fixed_root_invariant_passed") is not True
    ):
        raise MechanicsContractError("representative native mechanics lineage changed")
    for document, label in (
        (route_campaign, "ARM-213 route campaign"),
        (ik_campaign, "ARM-214 IK campaign"),
        (native_collision, "ARM-216 native collision campaign"),
        (mechanics_profile, "key-mechanics profile"),
    ):
        if (
            document.get("hardware_access", False) is not False
            or document.get("physical_authority", False) is not False
            or document.get("hardware_writes", 0) != 0
            or document.get("physical_movements", 0) != 0
            or document.get("controller_commands", []) != []
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    try:
        virtual_profile = json.loads(virtual_profile_bytes)
    except (TypeError, ValueError) as exc:
        raise MechanicsContractError("virtual profile is not valid JSON") from exc
    placement = virtual_profile.get("study_input", {}).get(
        "physical_placement_input", {}
    )
    placement_matrix = placement.get("matrix_row_major")
    if not isinstance(placement_matrix, list) or len(placement_matrix) != 16:
        raise MechanicsContractError("virtual profile lacks governed robot placement")
    placement_matrix = [
        _finite_number(value, "robot placement matrix value")
        for value in placement_matrix
    ]

    external = import_receipt.get("external_files")
    normalization = import_receipt.get("articulation_root_normalization", {})
    joint_order = [
        "base_link_to_link1",
        "link1_to_link2",
        "link2_to_link3",
        "link3_to_link4",
        "link4_to_link5",
        "link5_to_gripper_link",
    ]
    if (
        mechanics_profile.get("schema") != PROFILE_SCHEMA
        or drive_profile.get("schema") != GEOMETRY_PRIOR_PROFILE_SCHEMA
        or drive_profile.get("status") != "PROVISIONAL_SIMULATION_ONLY"
        or drive_profile.get("simulation_only") is not True
        or drive_profile.get("physical_authority") is not False
        or import_receipt.get("schema") != "tactevra.isaac_sim_urdf_import.v1"
        or not isinstance(external, list)
        or len(external) != 1
        or external[0].get("sha256") != robot_hash
        or external[0].get("size_bytes") != len(robot_usd_bytes)
        or normalization.get("expected_live_dof_order") != joint_order
    ):
        raise MechanicsContractError("native mechanics asset boundary changed")

    requests = route_campaign.get("requests")
    results = ik_campaign.get("results")
    manifest_entries = native_collision_manifest.get("entries")
    collision_results = native_collision.get("results")
    if not all(
        isinstance(rows, list) and len(rows) == 4
        for rows in (requests, results, manifest_entries, collision_results)
    ):
        raise MechanicsContractError("representative native mechanics coverage changed")

    plans = []
    for expected, request, result, entry, collision_result in zip(
        ("1", "SPACE", "ENTER", "PERIOD"),
        requests,
        results,
        manifest_entries,
        collision_results,
        strict=True,
    ):
        request_hash = _require_canonical_hash(
            request, "request_sha256", f"ARM-213 {expected} request"
        )
        result_hash = _require_canonical_hash(
            result, "result_sha256", f"ARM-214 {expected} result"
        )
        samples = request.get("samples")
        joint_results = result.get("joint_results")
        region = mechanics_profile.get("regions", {}).get(expected)
        if (
            request.get("key_id") != expected
            or result.get("target_id") != expected
            or result.get("source_request_sha256") != request_hash
            or result.get("status")
            != "READY_FOR_COLLISION_AND_FIXED_ROOT_QUALIFICATION"
            or result.get("ik_all_samples_accepted") is not True
            or entry.get("target_id") != expected
            or collision_result.get("target_id") != expected
            or collision_result.get("source_arm215_target_plan_sha256")
            != entry.get("source_arm215_target_plan_sha256")
            or collision_result.get("root_pose_invariant_status") != "PASS"
            or not isinstance(samples, list)
            or not isinstance(joint_results, list)
            or len(samples) != 40
            or len(joint_results) != len(samples)
            or not isinstance(region, dict)
        ):
            raise MechanicsContractError(
                f"representative {expected} mechanics source changed"
            )
        targets = []
        contact_endpoints = []
        action_indices = set()
        for sequence, (sample, joint_result) in enumerate(
            zip(samples, joint_results, strict=True)
        ):
            if (
                sample.get("sequence") != sequence
                or joint_result.get("waypoint_sequence") != sequence
                or joint_result.get("accepted") is not True
                or joint_result.get("phase") != sample.get("phase")
                or joint_result.get("action_index") != sample.get("action_index")
                or joint_result.get("semantic_target") != sample.get("target_id")
            ):
                raise MechanicsContractError(
                    f"representative {expected} joint schedule changed"
                )
            solution = joint_result.get("solution_arm_joint_positions_rad", {})
            targets.append({
                "sequence": sequence,
                "time_from_start_ns": int(_finite_number(
                    sample.get("time_from_start_ns"), "target time"
                )),
                "phase": sample.get("phase"),
                "target_id": expected,
                "action_index": sample.get("action_index"),
                "phase_endpoint": sample.get("phase_endpoint"),
                "joint_position_target_rad": [
                    *[
                        _finite_number(solution.get(name), f"joint target {name}")
                        for name in joint_order[:5]
                    ],
                    0.0,
                ],
            })
            if sample.get("action_index") is not None:
                action_indices.add(sample.get("action_index"))
            if sample.get("phase") == "CONTACT" and sample.get("phase_endpoint") is True:
                contact_endpoints.append(sequence)
        if len(contact_endpoints) != 2 or action_indices != {0, 1}:
            raise MechanicsContractError(
                f"representative {expected} action semantics changed"
            )
        plan = {
            "schema": REPRESENTATIVE_KEY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA,
            "status": "READY_FOR_ZERO_AUTHORITY_NATIVE_KEY_MECHANICS_REPLAY",
            "target_id": expected,
            "joint_order": joint_order,
            "sample_count": len(targets),
            "contact_endpoint_sequences": contact_endpoints,
            "joint_targets": targets,
            "target_region": {
                "center_board_xy_mm": list(region["center_board_xy_mm"]),
                "half_extent_mm": list(region["half_extent_mm"]),
            },
            "robot_placement_matrix_row_major": placement_matrix,
            "source_bindings": {
                "arm213_route_campaign_sha256": route_hash,
                "arm213_request_sha256": request_hash,
                "arm214_ik_campaign_sha256": ik_hash,
                "arm214_result_sha256": result_hash,
                "arm216_manifest_sha256": manifest_hash,
                "arm216_campaign_sha256": native_hash,
                "arm216_receipt_sha256": collision_result["receipt_sha256"],
                "key_mechanics_profile_sha256": profile_hash,
                "virtual_profile_sha256": virtual_hash,
                "drive_profile_file_sha256": drive_hash,
                "robot_import_receipt_sha256": import_hash,
                "robot_usd_sha256": robot_hash,
            },
            "execution_contract": {
                "initial_joint_state_placement_count": 1,
                "post_initialization_state_teleports": 0,
                "subsequent_joint_commands": "ARTICULATION_POSITION_TARGETS_ONLY",
                "key_motion_source": "NATIVE_CONTACT_ONLY",
                "root_pose_invariant_required_after_every_sample": True,
                "maximum_joint_tracking_error_rad": 0.05,
            },
            "limitations": [
                "simulation_only_provisional_drive_and_mechanics_parameters",
                "source_collision_admission_is_discrete_not_continuous_clearance",
                "no_hardware_motion_timing_torque_or_safety_authority",
            ],
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "gate_promotions": [],
        }
        plan["plan_sha256"] = _canonical_sha256(plan)
        plans.append(plan)

    campaign = {
        "schema": REPRESENTATIVE_KEY_NATIVE_MECHANICS_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_NATIVE_MECHANICS_REPLAY",
        "source_bindings": {
            "arm213_route_campaign_sha256": route_hash,
            "arm214_ik_campaign_sha256": ik_hash,
            "arm216_manifest_sha256": manifest_hash,
            "arm216_campaign_sha256": native_hash,
            "key_mechanics_profile_sha256": profile_hash,
            "virtual_profile_sha256": virtual_hash,
            "drive_profile_file_sha256": drive_hash,
            "robot_import_receipt_sha256": import_hash,
            "robot_usd_sha256": robot_hash,
        },
        "target_count": len(plans),
        "plans": plans,
        "native_mechanics_replay_executed": False,
        "multi_key_dataset_ready": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "compiled_campaign_does_not_execute_native_key_mechanics",
            "mechanics_and_drive_values_remain_provisional_simulation_priors",
            "collision_admission_is_discrete_not_continuous_clearance",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def aggregate_representative_key_native_mechanics_campaign(
    replay_campaign: dict[str, Any],
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify four native mechanics receipts as one simulation dataset."""

    campaign_hash = _require_canonical_hash(
        replay_campaign,
        "campaign_sha256",
        "representative native mechanics replay campaign",
    )
    plans = replay_campaign.get("plans")
    expected_targets = ["1", "SPACE", "ENTER", "PERIOD"]
    source_campaign = (
        replay_campaign.get("schema")
        == REPRESENTATIVE_KEY_NATIVE_MECHANICS_CAMPAIGN_SCHEMA
        and replay_campaign.get("status")
        == "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_NATIVE_MECHANICS_REPLAY"
    )
    adapted_campaign = (
        replay_campaign.get("schema")
        == REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_CAMPAIGN_SCHEMA
        and replay_campaign.get("status")
        == "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_MECHANICS_REPLAY"
    )
    refined_campaign = (
        replay_campaign.get("schema")
        == REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_CAMPAIGN_SCHEMA
        and replay_campaign.get("status")
        == "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_MECHANICS_REPLAY"
    )
    if (
        not (source_campaign or adapted_campaign or refined_campaign)
        or replay_campaign.get("target_count") != 4
        or not isinstance(plans, list)
        or len(plans) != 4
        or [plan.get("target_id") for plan in plans] != expected_targets
        or replay_campaign.get("native_mechanics_replay_executed") is not False
        or replay_campaign.get("hardware_access") is not False
        or replay_campaign.get("physical_authority") is not False
        or replay_campaign.get("hardware_writes") != 0
        or replay_campaign.get("physical_movements") != 0
        or replay_campaign.get("controller_commands") != []
    ):
        raise MechanicsContractError("native mechanics replay campaign boundary changed")
    receipt_by_target = {receipt.get("target_id"): receipt for receipt in receipts}
    if (
        len(receipts) != 4
        or len(receipt_by_target) != 4
        or list(receipt_by_target) != expected_targets
    ):
        raise MechanicsContractError("native mechanics receipt coverage changed")

    results = []
    total_samples = 0
    total_native_trace_samples = 0
    for plan in plans:
        target_id = plan["target_id"]
        plan_hash = _require_canonical_hash(
            plan, "plan_sha256", f"representative {target_id} mechanics plan"
        )
        receipt = receipt_by_target[target_id]
        receipt_hash = _require_canonical_hash(
            receipt,
            "receipt_sha256",
            f"representative {target_id} mechanics receipt",
        )
        assessments = receipt.get("action_assessments")
        root = receipt.get("root_pose_invariant")
        tracking_limit = plan.get("execution_contract", {}).get(
            "maximum_joint_tracking_error_rad"
        )
        if (
            receipt.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA
            or receipt.get("status") != "PASS"
            or receipt.get("source_plan_sha256") != plan_hash
            or receipt.get("source_arm216_receipt_sha256")
            != plan.get("source_bindings", {}).get("arm216_receipt_sha256")
            or receipt.get("state_teleports_after_initialization") != 0
            or not isinstance(assessments, list)
            or len(assessments) != 2
            or [item.get("action_index") for item in assessments] != [0, 1]
            or any(
                item.get("assessment", {}).get("accepted") is not True
                or item.get("assessment", {}).get("resolved_key") != target_id
                or item.get("assessment", {}).get("commanded_key") != target_id
                or item.get("assessment", {}).get("native_contact_observed") is not True
                for item in assessments
            )
            or not isinstance(root, dict)
            or root.get("all_passed") is not True
            or root.get("observation_count") != plan.get("sample_count")
            or receipt.get("maximum_joint_tracking_error_rad") is None
            or receipt.get("maximum_joint_tracking_error_rad") > tracking_limit
            or receipt.get("maximum_joint_tracking_error_allowed_rad") != tracking_limit
            or receipt.get("hardware_access") is not False
            or receipt.get("physical_authority") is not False
            or receipt.get("hardware_writes") != 0
            or receipt.get("physical_movements") != 0
            or receipt.get("controller_commands") != []
        ):
            raise MechanicsContractError(
                f"representative {target_id} mechanics receipt boundary changed"
            )
        native_trace = receipt.get("native_trace")
        if not isinstance(native_trace, list) or not native_trace:
            raise MechanicsContractError(
                f"representative {target_id} native trace is absent"
            )
        total_samples += plan["sample_count"]
        total_native_trace_samples += len(native_trace)
        results.append({
            "target_id": target_id,
            "plan_sha256": plan_hash,
            "receipt_sha256": receipt_hash,
            "action_count": 2,
            "native_trace_sample_count": len(native_trace),
            "maximum_joint_tracking_error_rad": receipt[
                "maximum_joint_tracking_error_rad"
            ],
            "root_pose_invariant_passed": True,
        })

    result = {
        "schema": REPRESENTATIVE_KEY_NATIVE_MECHANICS_RESULT_CAMPAIGN_SCHEMA,
        "status": "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_MECHANICS_CAMPAIGN",
        "source_replay_campaign_sha256": campaign_hash,
        "source_bindings": dict(replay_campaign["source_bindings"]),
        "target_count": 4,
        "accepted_action_count": 8,
        "total_joint_target_count": total_samples,
        "total_native_trace_sample_count": total_native_trace_samples,
        "results": results,
        "native_mechanics_replay_executed": True,
        "multi_key_dataset_ready": True,
        "dataset_scope": "ZERO_AUTHORITY_SIMULATION_LEARNING_ONLY",
        "continuous_collision_proven": False,
        "physical_keyboard_qualified": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "dataset_contains_provisional_simulated_mechanics_not_measurements",
            "collision_admission_is_discrete_not_continuous_clearance",
            "dataset_does_not_authorize_physical_motion",
        ],
    }
    result["campaign_sha256"] = _canonical_sha256(result)
    return result


def build_feedback_adapted_representative_key_mechanics_campaign(
    replay_campaign: dict[str, Any],
    receipts: list[dict[str, Any]],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Turn four blocked native traces into bounded target-specific replays."""

    campaign_hash = _require_canonical_hash(
        replay_campaign,
        "campaign_sha256",
        "representative native mechanics replay campaign",
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    plans = replay_campaign.get("plans")
    expected_targets = ["1", "SPACE", "ENTER", "PERIOD"]
    if (
        replay_campaign.get("schema")
        != REPRESENTATIVE_KEY_NATIVE_MECHANICS_CAMPAIGN_SCHEMA
        or replay_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_NATIVE_MECHANICS_REPLAY"
        or replay_campaign.get("target_count") != 4
        or not isinstance(plans, list)
        or [plan.get("target_id") for plan in plans] != expected_targets
        or replay_campaign.get("source_bindings", {}).get(
            "key_mechanics_profile_sha256"
        )
        != profile_hash
        or any(replay_campaign.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError(
            "representative feedback adaptation campaign boundary changed"
        )
    receipt_by_target = {receipt.get("target_id"): receipt for receipt in receipts}
    if (
        len(receipts) != 4
        or len(receipt_by_target) != 4
        or list(receipt_by_target) != expected_targets
    ):
        raise MechanicsContractError(
            "representative feedback receipt coverage changed"
        )

    release_anchor_sequence = 32
    lifted_sequences = [33, 34, 36, 37, 39]
    contact_sequences = [35, 38]
    target_compression_mm = NATIVE_H_PRESS_DEPTH_MM
    release_limit_mm = _finite_number(
        mechanics_profile["mechanics_prior"]["release_mm"]["nominal"],
        "release threshold",
    )
    adapted_plans = []
    for source_plan in plans:
        target_id = source_plan["target_id"]
        source_plan_hash = _require_canonical_hash(
            source_plan, "plan_sha256", f"representative {target_id} mechanics plan"
        )
        receipt = receipt_by_target[target_id]
        receipt_hash = _require_canonical_hash(
            receipt,
            "receipt_sha256",
            f"representative {target_id} mechanics receipt",
        )
        assessments = receipt.get("action_assessments")
        native_trace = receipt.get("native_trace")
        root = receipt.get("root_pose_invariant")
        tracking_limit = source_plan.get("execution_contract", {}).get(
            "maximum_joint_tracking_error_rad"
        )
        if (
            source_plan.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA
            or source_plan.get("status")
            != "READY_FOR_ZERO_AUTHORITY_NATIVE_KEY_MECHANICS_REPLAY"
            or source_plan.get("contact_endpoint_sequences") != contact_sequences
            or source_plan.get("sample_count") != 40
            or receipt.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA
            or receipt.get("status")
            != "BLOCKED_REPRESENTATIVE_NATIVE_KEY_MECHANICS_REPLAY"
            or receipt.get("source_plan_sha256") != source_plan_hash
            or receipt.get("target_id") != target_id
            or receipt.get("state_teleports_after_initialization") != 0
            or not isinstance(assessments, list)
            or len(assessments) != 2
            or not isinstance(native_trace, list)
            or not native_trace
            or not isinstance(root, dict)
            or root.get("all_passed") is not True
            or root.get("observation_count") != 40
            or receipt.get("maximum_joint_tracking_error_rad") is None
            or receipt.get("maximum_joint_tracking_error_rad") > tracking_limit
            or any(receipt.get(name) not in (False, 0, []) for name in (
                "hardware_access", "hardware_writes", "physical_authority",
                "physical_movements", "controller_commands", "gate_promotions",
            ))
        ):
            raise MechanicsContractError(
                f"representative {target_id} feedback boundary changed"
            )
        by_action = {
            row.get("action_index"): row.get("assessment") for row in assessments
        }
        if (
            set(by_action) != {0, 1}
            or any(not isinstance(row, dict) for row in by_action.values())
            or any(row.get("profile_sha256") != profile_hash for row in by_action.values())
            or any(row.get("disposition") != "EXCESSIVE_TRAVEL" for row in by_action.values())
            or any(row.get("native_contact_observed") is not True for row in by_action.values())
            or any(row.get("resolved_key") != target_id for row in by_action.values())
            or any(row.get("commanded_key") != target_id for row in by_action.values())
            or by_action[0].get("activation_count") != 1
        ):
            raise MechanicsContractError(
                f"representative {target_id} failure evidence changed"
            )

        anchor_trace = [
            row for row in native_trace
            if row.get("target_sequence") == release_anchor_sequence
        ]
        rest_key_z_m = max(
            _finite_number(row.get("key_center_z_m"), "trace key center")
            for row in native_trace
        )
        anchor_max_compression_mm = max(
            (rest_key_z_m - _finite_number(row.get("key_center_z_m"), "anchor key center"))
            * 1000.0
            for row in anchor_trace
        ) if anchor_trace else math.inf
        anchor_minimum_clearance_mm = min(
            _finite_number(row.get("tip_key_separation_m"), "anchor separation")
            * 1000.0
            for row in anchor_trace
        ) if anchor_trace else -math.inf
        if (
            anchor_minimum_clearance_mm < 0.0
            or anchor_max_compression_mm > release_limit_mm
        ):
            raise MechanicsContractError(
                f"representative {target_id} trace lacks a released anchor"
            )
        observed_max_compression_mm = max(
            _finite_number(row.get("max_compression_mm"), "maximum compression")
            for row in by_action.values()
        )
        contact_ratio = target_compression_mm / observed_max_compression_mm
        if not 0.0 < contact_ratio < 1.0:
            raise MechanicsContractError(
                f"representative {target_id} feedback does not support adaptation"
            )

        source_targets = source_plan.get("joint_targets")
        if (
            not isinstance(source_targets, list)
            or len(source_targets) != 40
            or source_targets[release_anchor_sequence].get("sequence")
            != release_anchor_sequence
        ):
            raise MechanicsContractError(
                f"representative {target_id} target ordering changed"
            )
        anchor_target = source_targets[release_anchor_sequence].get(
            "joint_position_target_rad"
        )
        if not isinstance(anchor_target, list) or len(anchor_target) != 6:
            raise MechanicsContractError(
                f"representative {target_id} release anchor changed"
            )
        adapted_targets = json.loads(json.dumps(source_targets))
        for sequence in lifted_sequences:
            adapted_targets[sequence]["joint_position_target_rad"] = list(anchor_target)
        for sequence in contact_sequences:
            row = adapted_targets[sequence]
            source_contact = row.get("joint_position_target_rad")
            if (
                row.get("sequence") != sequence
                or row.get("phase") != "CONTACT"
                or row.get("target_id") != target_id
                or row.get("action_index") not in (0, 1)
                or not isinstance(source_contact, list)
                or len(source_contact) != 6
            ):
                raise MechanicsContractError(
                    f"representative {target_id} contact target changed"
                )
            row["joint_position_target_rad"] = [
                float(anchor_target[index])
                + contact_ratio
                * (float(source_contact[index]) - float(anchor_target[index]))
                for index in range(6)
            ]

        adapted_maximum_delta = max(
            abs(
                float(current["joint_position_target_rad"][index])
                - float(previous["joint_position_target_rad"][index])
            )
            for previous, current in zip(adapted_targets, adapted_targets[1:])
            for index in range(6)
        )
        maximum_adapted_delta = 0.11
        if adapted_maximum_delta > maximum_adapted_delta:
            raise MechanicsContractError(
                f"representative {target_id} adaptation exceeds joint continuity bound"
            )

        plan = json.loads(json.dumps(source_plan))
        plan.pop("plan_sha256", None)
        plan.update({
            "schema": REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_REPLAY_PLAN_SCHEMA,
            "status": "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_KEY_MECHANICS_REPLAY",
            "joint_targets": adapted_targets,
            "source_bindings": {
                **source_plan["source_bindings"],
                "arm217_source_plan_sha256": source_plan_hash,
                "arm217_source_receipt_sha256": receipt_hash,
            },
            "feedback_adaptation": {
                "method": "TRACE_RELEASE_ANCHOR_AND_COMPRESSION_INTERPOLATION",
                "release_anchor_sequence": release_anchor_sequence,
                "anchor_minimum_clearance_mm": anchor_minimum_clearance_mm,
                "anchor_maximum_compression_mm": anchor_max_compression_mm,
                "release_threshold_mm": release_limit_mm,
                "observed_max_compression_mm": observed_max_compression_mm,
                "target_compression_mm": target_compression_mm,
                "contact_interpolation_ratio": contact_ratio,
                "lifted_hover_retract_sequences": lifted_sequences,
                "adapted_contact_sequences": contact_sequences,
                "adapted_maximum_adjacent_joint_delta_rad": adapted_maximum_delta,
                "maximum_adjacent_joint_delta_allowed_rad": maximum_adapted_delta,
                "mechanics_thresholds_changed": False,
                "target_region_changed": False,
            },
            "limitations": source_plan["limitations"] + [
                "feedback_adaptation_is_one_bounded_simulation_only_update",
                "release_anchor_and_contact_ratio_are_derived_from_native_trace",
            ],
        })
        plan["execution_contract"]["feedback_adaptation_applied"] = True
        plan["plan_sha256"] = _canonical_sha256(plan)
        adapted_plans.append(plan)

    campaign = {
        "schema": REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_MECHANICS_REPLAY",
        "source_replay_campaign_sha256": campaign_hash,
        "source_bindings": dict(replay_campaign["source_bindings"]),
        "target_count": 4,
        "plans": adapted_plans,
        "native_mechanics_replay_executed": False,
        "multi_key_dataset_ready": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "feedback_adaptation_remains_simulation_only",
            "mechanics_thresholds_and_target_regions_are_unchanged",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def build_contact_refined_representative_key_mechanics_campaign(
    adapted_campaign: dict[str, Any],
    receipts: list[dict[str, Any]],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Refine only contacts still excessive after the released-path replay."""

    campaign_hash = _require_canonical_hash(
        adapted_campaign,
        "campaign_sha256",
        "feedback-adapted representative mechanics campaign",
    )
    profile_hash = _require_canonical_hash(
        mechanics_profile, "profile_sha256", "key-mechanics profile"
    )
    plans = adapted_campaign.get("plans")
    expected_targets = ["1", "SPACE", "ENTER", "PERIOD"]
    source_is_adapted = (
        adapted_campaign.get("schema")
        == REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_CAMPAIGN_SCHEMA
        and adapted_campaign.get("status")
        == "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_MECHANICS_REPLAY"
    )
    source_is_refined = (
        adapted_campaign.get("schema")
        == REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_CAMPAIGN_SCHEMA
        and adapted_campaign.get("status")
        == "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_MECHANICS_REPLAY"
    )
    if (
        not (source_is_adapted or source_is_refined)
        or adapted_campaign.get("source_bindings", {}).get(
            "key_mechanics_profile_sha256"
        )
        != profile_hash
        or not isinstance(plans, list)
        or [plan.get("target_id") for plan in plans] != expected_targets
        or any(adapted_campaign.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError(
            "representative contact refinement campaign boundary changed"
        )
    receipt_by_target = {receipt.get("target_id"): receipt for receipt in receipts}
    if (
        len(receipts) != 4
        or len(receipt_by_target) != 4
        or list(receipt_by_target) != expected_targets
    ):
        raise MechanicsContractError(
            "representative contact refinement receipt coverage changed"
        )

    release_anchor_sequence = 32
    contact_sequences = [35, 38]
    release_limit_mm = _finite_number(
        mechanics_profile["mechanics_prior"]["release_mm"]["nominal"],
        "release threshold",
    )
    refined_plans = []
    preserved_targets = []
    refined_targets = []
    for source_plan in plans:
        target_id = source_plan["target_id"]
        source_plan_hash = _require_canonical_hash(
            source_plan, "plan_sha256", f"adapted {target_id} mechanics plan"
        )
        receipt = receipt_by_target[target_id]
        receipt_hash = _require_canonical_hash(
            receipt, "receipt_sha256", f"adapted {target_id} mechanics receipt"
        )
        assessments = receipt.get("action_assessments")
        root = receipt.get("root_pose_invariant")
        tracking_limit = source_plan.get("execution_contract", {}).get(
            "maximum_joint_tracking_error_rad"
        )
        source_plan_is_adapted = (
            source_plan.get("schema")
            == REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_REPLAY_PLAN_SCHEMA
            and source_plan.get("status")
            == "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_KEY_MECHANICS_REPLAY"
        )
        source_plan_is_refined = (
            source_plan.get("schema")
            == REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_REPLAY_PLAN_SCHEMA
            and source_plan.get("status")
            == "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_KEY_MECHANICS_REPLAY"
        )
        if (
            not (source_plan_is_adapted or source_plan_is_refined)
            or receipt.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA
            or receipt.get("source_plan_sha256") != source_plan_hash
            or receipt.get("target_id") != target_id
            or receipt.get("state_teleports_after_initialization") != 0
            or not isinstance(assessments, list)
            or len(assessments) != 2
            or not isinstance(root, dict)
            or root.get("all_passed") is not True
            or root.get("observation_count") != 40
            or receipt.get("maximum_joint_tracking_error_rad") is None
            or receipt.get("maximum_joint_tracking_error_rad") > tracking_limit
            or any(receipt.get(name) not in (False, 0, []) for name in (
                "hardware_access", "hardware_writes", "physical_authority",
                "physical_movements", "controller_commands", "gate_promotions",
            ))
        ):
            raise MechanicsContractError(
                f"representative {target_id} refinement boundary changed"
            )
        by_action = {
            row.get("action_index"): row.get("assessment") for row in assessments
        }
        if (
            set(by_action) != {0, 1}
            or any(not isinstance(row, dict) for row in by_action.values())
            or any(row.get("profile_sha256") != profile_hash for row in by_action.values())
            or any(row.get("resolved_key") != target_id for row in by_action.values())
            or any(row.get("commanded_key") != target_id for row in by_action.values())
            or any(row.get("native_contact_observed") is not True for row in by_action.values())
        ):
            raise MechanicsContractError(
                f"representative {target_id} refinement evidence changed"
            )
        if receipt.get("status") == "PASS":
            if any(
                row.get("accepted") is not True
                or row.get("disposition") != "ACCEPTED"
                for row in by_action.values()
            ):
                raise MechanicsContractError(
                    f"representative {target_id} passing evidence changed"
                )
            refined_plans.append(json.loads(json.dumps(source_plan)))
            preserved_targets.append(target_id)
            continue
        if (
            receipt.get("status")
            != "BLOCKED_REPRESENTATIVE_NATIVE_KEY_MECHANICS_REPLAY"
            or any(
                row.get("disposition") not in {"ACCEPTED", "EXCESSIVE_TRAVEL"}
                for row in by_action.values()
            )
            or not any(
                row.get("disposition") == "EXCESSIVE_TRAVEL"
                for row in by_action.values()
            )
            or any(row.get("activation_count") != 1 for row in by_action.values())
            or any(
                _finite_number(row.get("final_compression_mm"), "final compression")
                > release_limit_mm
                for row in by_action.values()
            )
        ):
            raise MechanicsContractError(
                f"representative {target_id} is not eligible for contact refinement"
            )
        observed_max_compression_mm = max(
            _finite_number(row.get("max_compression_mm"), "maximum compression")
            for row in by_action.values()
        )
        refinement_ratio = NATIVE_H_PRESS_DEPTH_MM / observed_max_compression_mm
        if not 0.0 < refinement_ratio < 1.0:
            raise MechanicsContractError(
                f"representative {target_id} feedback does not support refinement"
            )
        source_targets = source_plan.get("joint_targets")
        if not isinstance(source_targets, list) or len(source_targets) != 40:
            raise MechanicsContractError(
                f"representative {target_id} refined target schedule changed"
            )
        anchor_target = source_targets[release_anchor_sequence].get(
            "joint_position_target_rad"
        )
        if not isinstance(anchor_target, list) or len(anchor_target) != 6:
            raise MechanicsContractError(
                f"representative {target_id} refinement anchor changed"
            )
        refined_joint_targets = json.loads(json.dumps(source_targets))
        for sequence in contact_sequences:
            row = refined_joint_targets[sequence]
            source_contact = row.get("joint_position_target_rad")
            if (
                row.get("sequence") != sequence
                or row.get("phase") != "CONTACT"
                or row.get("target_id") != target_id
                or not isinstance(source_contact, list)
                or len(source_contact) != 6
            ):
                raise MechanicsContractError(
                    f"representative {target_id} refinement contact changed"
                )
            row["joint_position_target_rad"] = [
                float(anchor_target[index])
                + refinement_ratio
                * (float(source_contact[index]) - float(anchor_target[index]))
                for index in range(6)
            ]
        plan = json.loads(json.dumps(source_plan))
        plan.pop("plan_sha256", None)
        plan.update({
            "schema": REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_REPLAY_PLAN_SCHEMA,
            "status": "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_KEY_MECHANICS_REPLAY",
            "joint_targets": refined_joint_targets,
            "source_bindings": {
                **source_plan["source_bindings"],
                "arm217_prior_plan_sha256": source_plan_hash,
                "arm217_prior_receipt_sha256": receipt_hash,
            },
            "contact_refinement": {
                "method": "MULTIPLICATIVE_CONTACT_ERROR_FROM_RELEASED_ANCHOR",
                "release_anchor_sequence": release_anchor_sequence,
                "preserved_hover_retract_sequences": [33, 34, 36, 37, 39],
                "refined_contact_sequences": contact_sequences,
                "observed_max_compression_mm": observed_max_compression_mm,
                "target_compression_mm": NATIVE_H_PRESS_DEPTH_MM,
                "contact_refinement_ratio": refinement_ratio,
                "mechanics_thresholds_changed": False,
                "target_region_changed": False,
            },
            "limitations": source_plan["limitations"] + [
                "contact_refinement_is_one_bounded_simulation_only_update",
                "previously_learned_release_path_is_preserved",
            ],
        })
        plan["execution_contract"]["contact_refinement_applied"] = True
        plan["plan_sha256"] = _canonical_sha256(plan)
        refined_plans.append(plan)
        refined_targets.append(target_id)

    campaign = {
        "schema": REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_MECHANICS_REPLAY",
        "source_prior_campaign_sha256": campaign_hash,
        "source_bindings": dict(adapted_campaign["source_bindings"]),
        "target_count": 4,
        "plans": refined_plans,
        "preserved_passing_targets": preserved_targets,
        "contact_refined_targets": refined_targets,
        "native_mechanics_replay_executed": False,
        "multi_key_dataset_ready": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "contact_refinement_remains_simulation_only",
            "passing_target_plans_are_preserved_without_mutation",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def canonical_active_rotation_row_major_from_gf_rows(
    rows: list[list[float]],
) -> list[float]:
    """Convert Gf row-vector storage to active column-vector row-major form."""

    if (
        not isinstance(rows, list)
        or len(rows) != 3
        or any(not isinstance(row, list) or len(row) != 3 for row in rows)
    ):
        raise MechanicsContractError("Gf rotation rows must be a 3x3 matrix")
    values = [
        [_finite_number(value, "Gf rotation element") for value in row]
        for row in rows
    ]
    return [values[column][row] for row in range(3) for column in range(3)]


def evaluate_root_pose_invariant(
    expected_position_m: list[float],
    expected_quaternion_wxyz: list[float],
    observed_position_m: list[float],
    observed_quaternion_wxyz: list[float],
    *,
    translation_tolerance_mm: float,
    orientation_tolerance_deg: float,
) -> dict[str, Any]:
    """Return a deterministic, quaternion-sign-invariant fixed-root check."""

    vectors = (
        (expected_position_m, 3, "expected root position"),
        (expected_quaternion_wxyz, 4, "expected root quaternion"),
        (observed_position_m, 3, "observed root position"),
        (observed_quaternion_wxyz, 4, "observed root quaternion"),
    )
    normalized = []
    for vector, size, label in vectors:
        if not isinstance(vector, list) or len(vector) != size:
            raise MechanicsContractError(f"{label} is invalid")
        normalized.append([_finite_number(value, label) for value in vector])
    expected_position, expected_quaternion, observed_position, observed_quaternion = (
        normalized
    )
    expected_norm = math.sqrt(sum(value * value for value in expected_quaternion))
    observed_norm = math.sqrt(sum(value * value for value in observed_quaternion))
    if expected_norm <= 0.0 or observed_norm <= 0.0:
        raise MechanicsContractError("root quaternion norm must be positive")
    expected_quaternion = [value / expected_norm for value in expected_quaternion]
    observed_quaternion = [value / observed_norm for value in observed_quaternion]
    dot = abs(sum(
        first * second
        for first, second in zip(
            expected_quaternion, observed_quaternion, strict=True
        )
    ))
    orientation_delta_deg = math.degrees(2.0 * math.acos(min(1.0, dot)))
    translation_delta_mm = 1000.0 * math.sqrt(sum(
        (first - second) ** 2
        for first, second in zip(
            expected_position, observed_position, strict=True
        )
    ))
    translation_tolerance = _finite_number(
        translation_tolerance_mm, "root translation tolerance"
    )
    orientation_tolerance = _finite_number(
        orientation_tolerance_deg, "root orientation tolerance"
    )
    if translation_tolerance < 0.0 or orientation_tolerance < 0.0:
        raise MechanicsContractError("root-pose tolerances must be nonnegative")
    return {
        "translation_delta_mm": translation_delta_mm,
        "orientation_delta_deg": orientation_delta_deg,
        "translation_tolerance_mm": translation_tolerance,
        "orientation_tolerance_deg": orientation_tolerance,
        "passed": (
            translation_delta_mm <= translation_tolerance
            and orientation_delta_deg <= orientation_tolerance
        ),
    }


def _validated_collision_candidate_partition(
    collision_candidate: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate physical workcell solids from non-solid station regions."""
    claimed_hash = collision_candidate.get("candidate_sha256")
    unsigned = dict(collision_candidate)
    unsigned.pop("candidate_sha256", None)
    if claimed_hash != _canonical_sha256(unsigned):
        raise MechanicsContractError("collision candidate hash mismatch")
    if (
        collision_candidate.get("schema")
        != "tactevra.simulation_collision_candidate.v1"
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
        or collision_candidate.get("physical_authority") is not False
        or collision_candidate.get("hardware_write_count") != 0
        or collision_candidate.get("physical_movement_count") != 0
        or collision_candidate.get("commands") != []
    ):
        raise MechanicsContractError("collision candidate boundary changed")
    bodies = collision_candidate.get("workcell_bodies")
    if not isinstance(bodies, list) or not bodies:
        raise MechanicsContractError("collision candidate workcell bodies are absent")
    physical: list[dict[str, Any]] = []
    stations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for body in bodies:
        body_id = body.get("body_id") if isinstance(body, dict) else None
        if not isinstance(body_id, str) or not body_id or body_id in seen:
            raise MechanicsContractError("collision candidate workcell body id is invalid")
        seen.add(body_id)
        primitives = body.get("primitives")
        if not isinstance(primitives, list) or not primitives:
            raise MechanicsContractError("collision candidate workcell body lacks primitives")
        (stations if body_id.startswith("workcell:station:") else physical).append(body)
    required_physical = {
        "workcell:board_solid", "workcell:keyboard", "workcell:phone",
    }
    if not required_physical.issubset({body["body_id"] for body in physical}):
        raise MechanicsContractError("required physical workcell solids are absent")
    if not stations:
        raise MechanicsContractError("station planning regions are absent")
    return physical, stations


def _point_inside_oriented_box(
    point_mm: list[float], primitive: dict[str, Any], *, label: str,
) -> bool:
    if primitive.get("kind") != "oriented_box":
        raise MechanicsContractError(f"{label} must be an oriented box")
    center = primitive.get("center_mm")
    half = primitive.get("half_extents_mm")
    rotation = primitive.get("rotation_row_major")
    if (
        not isinstance(center, list) or len(center) != 3
        or not isinstance(half, list) or len(half) != 3
        or not isinstance(rotation, list) or len(rotation) != 9
    ):
        raise MechanicsContractError(
            f"{label} geometry is invalid: "
            f"center={type(center).__name__}/{len(center) if isinstance(center, list) else 'NA'}, "
            f"half={type(half).__name__}/{len(half) if isinstance(half, list) else 'NA'}, "
            f"rotation={type(rotation).__name__}/{len(rotation) if isinstance(rotation, list) else 'NA'}"
        )
    center_values = [_finite_number(value, f"{label} center") for value in center]
    half_values = [_finite_number(value, f"{label} half extent") for value in half]
    if min(half_values) <= 0.0:
        raise MechanicsContractError(f"{label} half extents must be positive")
    rotation_values = [
        _finite_number(value, f"{label} rotation") for value in rotation
    ]
    rows = [rotation_values[index:index + 3] for index in range(0, 9, 3)]
    for row_index, row in enumerate(rows):
        for other_index, other in enumerate(rows):
            dot = sum(left * right for left, right in zip(row, other))
            expected = 1.0 if row_index == other_index else 0.0
            if abs(dot - expected) > 1e-6:
                raise MechanicsContractError(f"{label} rotation must be orthonormal")
    determinant = (
        rotation_values[0]
        * (
            rotation_values[4] * rotation_values[8]
            - rotation_values[5] * rotation_values[7]
        )
        - rotation_values[1]
        * (
            rotation_values[3] * rotation_values[8]
            - rotation_values[5] * rotation_values[6]
        )
        + rotation_values[2]
        * (
            rotation_values[3] * rotation_values[7]
            - rotation_values[4] * rotation_values[6]
        )
    )
    if abs(determinant - 1.0) > 1e-6:
        raise MechanicsContractError(f"{label} rotation must be right-handed")
    offset = [point_mm[index] - center_values[index] for index in range(3)]
    local = [
        sum(
            rotation_values[row_index * 3 + axis] * offset[row_index]
            for row_index in range(3)
        )
        for axis in range(3)
    ]
    return all(abs(value) <= extent + 1e-9 for value, extent in zip(local, half_values))


def build_station_route_predicate(
    cartesian_request: dict[str, Any],
    collision_candidate: dict[str, Any],
    target_station_bindings: dict[str, list[str]],
) -> dict[str, Any]:
    """Evaluate station planning regions without treating them as PhysX solids."""
    claimed_request_hash = cartesian_request.get("request_sha256")
    unsigned_request = dict(cartesian_request)
    unsigned_request.pop("request_sha256", None)
    if claimed_request_hash != _canonical_sha256(unsigned_request):
        raise MechanicsContractError("Cartesian request hash mismatch")
    if (
        cartesian_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or cartesian_request.get("status") not in {
            "READY_FOR_IK_QUALIFICATION",
            "READY_FOR_TARGET_SPECIFIC_IK_QUALIFICATION",
        }
        or cartesian_request.get("hardware_access") is not False
        or cartesian_request.get("controller_commands") != []
        or cartesian_request.get("hardware_writes") != 0
        or cartesian_request.get("physical_movements") != 0
    ):
        raise MechanicsContractError("Cartesian request boundary changed")
    samples = cartesian_request.get("samples")
    if (
        not isinstance(samples, list) or not samples
        or cartesian_request.get("sample_count") != len(samples)
        or [sample.get("sequence") for sample in samples]
        != list(range(len(samples)))
    ):
        raise MechanicsContractError("Cartesian request samples are invalid")

    physical_bodies, station_bodies = _validated_collision_candidate_partition(
        collision_candidate
    )
    station_ids = {body["body_id"] for body in station_bodies}
    target_ids = {
        sample.get("target_id") for sample in samples
        if sample.get("target_id") is not None
    }
    if set(target_station_bindings) != target_ids:
        raise MechanicsContractError("target-to-station binding coverage differs")
    normalized_bindings: dict[str, list[str]] = {}
    for target_id in sorted(target_ids):
        if not isinstance(target_id, str) or not target_id:
            raise MechanicsContractError("Cartesian target id is invalid")
        bindings = target_station_bindings.get(target_id)
        if (
            not isinstance(bindings, list) or not bindings
            or not all(isinstance(item, str) and item in station_ids for item in bindings)
            or len(bindings) != len(set(bindings))
        ):
            raise MechanicsContractError("target-to-station binding is invalid")
        normalized_bindings[target_id] = sorted(bindings)

    evaluations = []
    violation_count = 0
    for sample in samples:
        point = sample.get("expected_tool_tip_board_mm")
        if not isinstance(point, list) or len(point) != 3:
            raise MechanicsContractError("Cartesian sample tool-tip point is invalid")
        point_values = [_finite_number(value, "Cartesian tool-tip point") for value in point]
        occupied = []
        for body in station_bodies:
            if any(
                _point_inside_oriented_box(
                    point_values,
                    primitive,
                    label=f"station region {body['body_id']}",
                )
                for primitive in body["primitives"]
            ):
                occupied.append(body["body_id"])
        target_id = sample.get("target_id")
        allowed = normalized_bindings.get(target_id, [])
        unexpected = sorted(set(occupied) - set(allowed))
        contact_missing_bound_station = (
            sample.get("phase") == "CONTACT"
            and sample.get("phase_endpoint") is True
            and not set(occupied).intersection(allowed)
        )
        violations = []
        if contact_missing_bound_station:
            violations.append("CONTACT_OUTSIDE_BOUND_STATION_REGION")
        violation_count += len(violations)
        evaluations.append({
            "sequence": sample["sequence"],
            "action_index": sample.get("action_index"),
            "phase": sample.get("phase"),
            "target_id": target_id,
            "tool_tip_board_mm": point_values,
            "allowed_station_regions": allowed,
            "occupied_station_regions": sorted(occupied),
            "unexpected_station_regions": unexpected,
            "violations": violations,
        })

    result: dict[str, Any] = {
        "schema": STATION_ROUTE_PREDICATE_SCHEMA,
        "status": "PASS" if violation_count == 0 else "FAIL",
        "source_cartesian_request_sha256": claimed_request_hash,
        "source_collision_candidate_sha256": collision_candidate["candidate_sha256"],
        "predicate_semantics": (
            "CONTACT_ENDPOINT_MUST_OCCUPY_A_TARGET_BOUND_STATION_REGION;"
            "NONCONTACT_REGION_OCCUPANCY_IS_RECORDED_NOT_REJECTED"
        ),
        "physical_workcell_body_ids": sorted(
            body["body_id"] for body in physical_bodies
        ),
        "physx_excluded_station_region_ids": sorted(station_ids),
        "target_station_bindings": normalized_bindings,
        "sample_count": len(evaluations),
        "violation_count": violation_count,
        "samples": evaluations,
        "installed_profile_eligible": False,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "discrete_tcp_point_predicate_is_not_continuous_swept_volume_proof",
            "physical_workcell_bodies_remain_collision_solids",
            "station_regions_are_planning_semantics_not_physical_clearance",
            "source_candidate_placement_requires_separate_measurement_qualification",
        ],
    }
    result["predicate_sha256"] = _canonical_sha256(result)
    return result


def build_physical_blocker_experiment_plan(
    cartesian_request: dict[str, Any],
    collision_candidate: dict[str, Any],
    diagnostic_receipt: dict[str, Any],
    localization: dict[str, Any],
    virtual_profile: dict[str, Any],
    *,
    clearance_margin_mm: float,
    virtual_profile_sha256: str,
) -> dict[str, Any]:
    """Classify physical blockers before generating a route or placement variant."""
    margin = _finite_number(clearance_margin_mm, "clearance margin")
    if margin <= 0.0 or margin > 150.0:
        raise MechanicsContractError("clearance margin must be within (0, 150] mm")
    documents = (
        (cartesian_request, "request_sha256", "Cartesian request"),
        (diagnostic_receipt, "receipt_sha256", "diagnostic receipt"),
        (localization, "proposal_sha256", "blocker localization"),
    )
    for document, hash_field, label in documents:
        claimed = document.get(hash_field)
        unsigned = dict(document)
        unsigned.pop(hash_field, None)
        if claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} hash mismatch")
    physical_bodies, _ = _validated_collision_candidate_partition(
        collision_candidate
    )
    if (
        not isinstance(virtual_profile_sha256, str)
        or len(virtual_profile_sha256) != 64
        or any(character not in "0123456789abcdef" for character in virtual_profile_sha256)
    ):
        raise MechanicsContractError("virtual profile SHA-256 is invalid")
    profile_hash = virtual_profile_sha256
    source_bindings = diagnostic_receipt.get("source_bindings", {})
    if (
        localization.get("source_cartesian_request_sha256")
        != cartesian_request.get("request_sha256")
        or localization.get("source_diagnostic_receipt_sha256")
        != diagnostic_receipt.get("receipt_sha256")
        or source_bindings.get("collision_candidate_sha256")
        != collision_candidate.get("candidate_sha256")
        or source_bindings.get("virtual_profile_sha256") != profile_hash
        or diagnostic_receipt.get("station_route_predicate_applied") is not True
        or localization.get("physical_solid_blocker_pair_count") <= 0
        or localization.get("planning_envelope_blocker_pair_count") != 0
        or localization.get("unreviewed_blocker_pair_count") != 0
    ):
        raise MechanicsContractError("physical blocker experiment lineage changed")
    for document, label in (
        (cartesian_request, "Cartesian request"),
        (diagnostic_receipt, "diagnostic receipt"),
        (localization, "blocker localization"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    physical_top_z_mm = -math.inf
    for body in physical_bodies:
        for primitive in body["primitives"]:
            if primitive.get("kind") != "oriented_box":
                raise MechanicsContractError("physical workcell primitive must be a box")
            center = primitive.get("center_mm")
            half = primitive.get("half_extents_mm")
            rotation = primitive.get("rotation_row_major")
            if (
                not isinstance(center, list)
                or len(center) != 3
                or not isinstance(half, list)
                or len(half) != 3
                or not isinstance(rotation, list)
                or len(rotation) != 9
            ):
                raise MechanicsContractError(
                    "physical workcell box geometry is invalid: "
                    f"center={type(center).__name__}/"
                    f"{len(center) if isinstance(center, list) else 'NA'}, "
                    f"half={type(half).__name__}/"
                    f"{len(half) if isinstance(half, list) else 'NA'}, "
                    f"rotation={type(rotation).__name__}/"
                    f"{len(rotation) if isinstance(rotation, list) else 'NA'}"
                )
            center_z = _finite_number(center[2], "physical box center z")
            half_values = [_finite_number(value, "physical box half extent") for value in half]
            rotation_values = [_finite_number(value, "physical box rotation") for value in rotation]
            world_z_extent = sum(
                abs(rotation_values[6 + axis]) * half_values[axis]
                for axis in range(3)
            )
            physical_top_z_mm = max(physical_top_z_mm, center_z + world_z_extent)

    transit_sequences: set[int] = set()
    endpoint_pairs: set[tuple[str, str]] = set()
    blocker_summaries = []
    for blocker in localization.get("blocker_localizations", []):
        pair = blocker.get("body_pair")
        samples = blocker.get("samples")
        if not isinstance(pair, list) or len(pair) != 2 or not isinstance(samples, list):
            raise MechanicsContractError("physical blocker localization is invalid")
        transit = sorted({
            sample["cartesian_sequence"] for sample in samples
            if sample.get("phase") == "TRANSIT"
        })
        endpoint_phases = sorted({
            sample.get("phase") for sample in samples
            if sample.get("phase") in {"CONTACT", "HOVER", "RETRACT"}
        })
        transit_sequences.update(transit)
        if endpoint_phases:
            endpoint_pairs.add((pair[0], pair[1]))
        blocker_summaries.append({
            "body_pair": pair,
            "sample_count": blocker.get("sample_count"),
            "transit_cartesian_sequences": transit,
            "endpoint_phases": endpoint_phases,
            "experiment_class": (
                "TRANSIT_LIFT_AND_ENDPOINT_GEOMETRY"
                if transit and endpoint_phases
                else "TRANSIT_LIFT_ONLY"
                if transit
                else "ENDPOINT_GEOMETRY_ONLY"
            ),
        })

    placement = virtual_profile.get("study_input", {}).get(
        "physical_placement_input", {}
    )
    result: dict[str, Any] = {
        "schema": PHYSICAL_BLOCKER_EXPERIMENT_PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_VARIANT_GENERATION",
        "source_cartesian_request_sha256": cartesian_request["request_sha256"],
        "source_collision_candidate_sha256": collision_candidate["candidate_sha256"],
        "source_diagnostic_receipt_sha256": diagnostic_receipt["receipt_sha256"],
        "source_localization_sha256": localization["proposal_sha256"],
        "source_virtual_profile_sha256": profile_hash,
        "source_placement_classification": virtual_profile.get("status"),
        "source_study_input_id": virtual_profile.get("study_input", {}).get(
            "study_input_id"
        ),
        "source_robot_placement_matrix_row_major": placement.get(
            "matrix_row_major"
        ),
        "physical_workcell_top_z_mm": physical_top_z_mm,
        "clearance_margin_mm": margin,
        "proposed_transit_z_mm": physical_top_z_mm + margin,
        "transit_lift_cartesian_sequences": sorted(transit_sequences),
        "endpoint_geometry_body_pairs": [list(pair) for pair in sorted(endpoint_pairs)],
        "blocker_experiments": blocker_summaries,
        "placement_hypothesis_required": True,
        "route_variant_applied": False,
        "collision_geometry_changed": False,
        "installed_profile_eligible": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "source_robot_placement_is_an_unmeasured_sensitivity_overlay",
            "clearance_margin_is_an_explicit_simulation_hypothesis_not_a_physical_allowance",
            "transit_lift_does_not_resolve_contact_hover_or_retract_geometry",
            "no_collision_solid_is_removed_or_resized",
        ],
    }
    result["plan_sha256"] = _canonical_sha256(result)
    return result


def build_physical_blocker_route_variant(
    cartesian_request: dict[str, Any],
    experiment_plan: dict[str, Any],
) -> dict[str, Any]:
    """Apply only the plan-bound transit-height hypothesis to a request."""
    claimed_request_hash = cartesian_request.get("request_sha256")
    unsigned_request = dict(cartesian_request)
    unsigned_request.pop("request_sha256", None)
    if claimed_request_hash != _canonical_sha256(unsigned_request):
        raise MechanicsContractError("source Cartesian request hash mismatch")
    claimed_plan_hash = experiment_plan.get("plan_sha256")
    unsigned_plan = dict(experiment_plan)
    unsigned_plan.pop("plan_sha256", None)
    if claimed_plan_hash != _canonical_sha256(unsigned_plan):
        raise MechanicsContractError("physical blocker experiment plan hash mismatch")
    if (
        cartesian_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or cartesian_request.get("status") != "READY_FOR_IK_QUALIFICATION"
        or experiment_plan.get("schema") != PHYSICAL_BLOCKER_EXPERIMENT_PLAN_SCHEMA
        or experiment_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_VARIANT_GENERATION"
        or experiment_plan.get("source_cartesian_request_sha256")
        != claimed_request_hash
    ):
        raise MechanicsContractError("physical blocker route-variant lineage changed")
    for document, label in (
        (cartesian_request, "source Cartesian request"),
        (experiment_plan, "physical blocker experiment plan"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed the zero-authority boundary")
    if (
        experiment_plan.get("physical_authority") is not False
        or experiment_plan.get("route_variant_applied") is not False
        or experiment_plan.get("collision_geometry_changed") is not False
    ):
        raise MechanicsContractError("physical blocker experiment boundary changed")

    samples = cartesian_request.get("samples")
    if (
        not isinstance(samples, list)
        or not samples
        or cartesian_request.get("sample_count") != len(samples)
        or [sample.get("sequence") for sample in samples]
        != list(range(len(samples)))
    ):
        raise MechanicsContractError("source Cartesian request samples are invalid")
    sequences = experiment_plan.get("transit_lift_cartesian_sequences")
    if (
        not isinstance(sequences, list)
        or not sequences
        or sequences != sorted(sequences)
        or len(sequences) != len(set(sequences))
        or any(
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
            or sequence >= len(samples)
            for sequence in sequences
        )
    ):
        raise MechanicsContractError("transit-lift sequence selection is invalid")
    proposed_z = _finite_number(
        experiment_plan.get("proposed_transit_z_mm"), "proposed transit z"
    )
    physical_top_z = _finite_number(
        experiment_plan.get("physical_workcell_top_z_mm"), "physical workcell top z"
    )
    if proposed_z <= physical_top_z:
        raise MechanicsContractError("proposed transit z does not clear the workcell top")

    selected = set(sequences)
    variant_samples: list[dict[str, Any]] = []
    for sequence, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise MechanicsContractError("source Cartesian sample is invalid")
        point = sample.get("expected_tool_tip_board_mm")
        if not isinstance(point, list) or len(point) != 3:
            raise MechanicsContractError("source Cartesian sample point is invalid")
        normalized_point = [
            _finite_number(value, f"sample {sequence} Cartesian coordinate")
            for value in point
        ]
        variant_sample = dict(sample)
        if sequence in selected:
            if sample.get("phase") != "TRANSIT" or sample.get("phase_endpoint") is not False:
                raise MechanicsContractError(
                    "transit-lift selection includes a non-transit endpoint"
                )
            if normalized_point[2] == proposed_z:
                raise MechanicsContractError(
                    "transit-lift selection includes an unchanged sample"
                )
            variant_sample["expected_tool_tip_board_mm"] = [
                point[0], point[1], proposed_z,
            ]
        variant_samples.append(variant_sample)

    result = dict(cartesian_request)
    result.pop("request_sha256", None)
    result.update({
        "source_cartesian_request_sha256": claimed_request_hash,
        "source_physical_blocker_experiment_plan_sha256": claimed_plan_hash,
        "route_variant_classification": (
            "ZERO_AUTHORITY_TRANSIT_HEIGHT_HYPOTHESIS"
        ),
        "modified_transit_sequences": sequences,
        "proposed_transit_z_mm": proposed_z,
        "route_variant_applied": True,
        "collision_geometry_changed": False,
        "installed_profile_eligible": False,
        "samples": variant_samples,
        "limitations": list(cartesian_request.get("limitations", [])) + [
            "transit_height_is_a_plan_bound_simulation_hypothesis",
            "contact_hover_and_retract_endpoints_are_unchanged",
            "route_variant_requires_fresh_ik_and_collision_qualification",
        ],
    })
    result["request_sha256"] = _canonical_sha256(result)
    return result


def build_placement_tcp_search_plan(
    experiment_plan: dict[str, Any],
    route_variant_request: dict[str, Any],
    diagnostic_receipt: dict[str, Any],
    localization: dict[str, Any],
    virtual_profile: dict[str, Any],
    *,
    virtual_profile_sha256: str,
) -> dict[str, Any]:
    """Plan a bounded placement/TCP attribution campaign without running it."""
    hashed_documents = (
        (experiment_plan, "plan_sha256", "physical blocker experiment plan"),
        (route_variant_request, "request_sha256", "route variant request"),
        (diagnostic_receipt, "receipt_sha256", "diagnostic receipt"),
        (localization, "proposal_sha256", "blocker localization"),
    )
    for document, hash_field, label in hashed_documents:
        claimed = document.get(hash_field)
        unsigned = dict(document)
        unsigned.pop(hash_field, None)
        if claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} hash mismatch")
    if (
        not isinstance(virtual_profile_sha256, str)
        or len(virtual_profile_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in virtual_profile_sha256
        )
    ):
        raise MechanicsContractError("virtual profile SHA-256 is invalid")

    source_bindings = diagnostic_receipt.get("source_bindings")
    if not isinstance(source_bindings, dict):
        raise MechanicsContractError("diagnostic source bindings are absent")
    if (
        experiment_plan.get("schema") != PHYSICAL_BLOCKER_EXPERIMENT_PLAN_SCHEMA
        or experiment_plan.get("source_virtual_profile_sha256")
        != virtual_profile_sha256
        or route_variant_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or route_variant_request.get("source_physical_blocker_experiment_plan_sha256")
        != experiment_plan.get("plan_sha256")
        or route_variant_request.get("route_variant_applied") is not True
        or route_variant_request.get("collision_geometry_changed") is not False
        or diagnostic_receipt.get("schema")
        != TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
        or diagnostic_receipt.get("status") != "DIAGNOSTIC_BLOCKERS_OBSERVED"
        or diagnostic_receipt.get("station_route_predicate_applied") is not True
        or diagnostic_receipt.get("collision_pair_policy_applied") is not True
        or source_bindings.get("virtual_profile_sha256")
        != virtual_profile_sha256
        or source_bindings.get("collision_candidate_sha256")
        != experiment_plan.get("source_collision_candidate_sha256")
        or localization.get("schema")
        != TCP_COLLISION_BLOCKER_LOCALIZATION_SCHEMA
        or localization.get("source_cartesian_request_sha256")
        != route_variant_request.get("request_sha256")
        or localization.get("source_diagnostic_receipt_sha256")
        != diagnostic_receipt.get("receipt_sha256")
        or localization.get("physical_solid_blocker_pair_count") != 7
        or localization.get("planning_envelope_blocker_pair_count") != 0
        or localization.get("unreviewed_blocker_pair_count") != 0
    ):
        raise MechanicsContractError("placement/TCP search-plan lineage changed")

    for document, label in (
        (experiment_plan, "physical blocker experiment plan"),
        (route_variant_request, "route variant request"),
        (diagnostic_receipt, "diagnostic receipt"),
        (localization, "blocker localization"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")
    if (
        diagnostic_receipt.get("physical_authority") is not False
        or diagnostic_receipt.get("gate_promotions") != []
        or localization.get("physical_authority") is not False
        or localization.get("gate_promotions") != []
    ):
        raise MechanicsContractError("placement/TCP source evidence gained authority")

    if (
        virtual_profile.get("schema") != "rocell.virtual_commissioning_profile.v1"
        or virtual_profile.get("status") != "UNMEASURED_SENSITIVITY_OVERLAY"
        or virtual_profile.get("simulation_only") is not True
        or virtual_profile.get("physical_release_effect") != "NONE"
    ):
        raise MechanicsContractError("virtual profile boundary changed")
    selection = virtual_profile.get("selection")
    mission_coverage_hash = (
        selection.get("source_mission_route_coverage_hash")
        if isinstance(selection, dict)
        else None
    )
    if (
        not isinstance(mission_coverage_hash, str)
        or len(mission_coverage_hash) != 64
        or any(
            character not in "0123456789abcdef"
            for character in mission_coverage_hash
        )
    ):
        raise MechanicsContractError("mission-route coverage hash is invalid")
    study = virtual_profile.get("study_input")
    placement = study.get("physical_placement_input") if isinstance(study, dict) else None
    tool_lengths = study.get("route_tool_lengths_mm") if isinstance(study, dict) else None
    if not isinstance(placement, dict) or not isinstance(tool_lengths, dict):
        raise MechanicsContractError("virtual profile placement/TCP inputs are absent")
    source_matrix = placement.get("matrix_row_major")
    if not isinstance(source_matrix, list) or len(source_matrix) != 16:
        raise MechanicsContractError("virtual profile placement matrix is invalid")
    source_matrix = [
        _finite_number(value, "virtual profile placement matrix")
        for value in source_matrix
    ]
    source_x = _finite_number(
        placement.get("rear_clamp_contact_x_board_mm"), "source rear clamp x"
    )
    clamp_to_axis_x = _finite_number(
        placement.get("clamp_to_base_axis_x_mm"), "source clamp-to-axis x"
    )
    source_y = _finite_number(
        placement.get("rear_edge_to_base_axis_y_mm"), "source rear-axis y"
    )
    source_z = _finite_number(
        placement.get("base_link_z_board_mm"), "source base z"
    )
    source_yaw_rad = _finite_number(
        placement.get("base_yaw_board_rad"), "source base yaw"
    )
    source_tcp = _finite_number(
        tool_lengths.get("keyboard"), "source keyboard TCP length"
    )
    board_rear_edge_y = source_matrix[7] - source_y
    if (
        abs(source_matrix[3] - (source_x + clamp_to_axis_x)) > 1e-9
        or abs(source_matrix[11] - source_z) > 1e-9
        or abs(source_matrix[0] - math.cos(source_yaw_rad)) > 1e-9
        or abs(source_matrix[1] + math.sin(source_yaw_rad)) > 1e-9
        or abs(source_matrix[4] - math.sin(source_yaw_rad)) > 1e-9
        or abs(source_matrix[5] - math.cos(source_yaw_rad)) > 1e-9
    ):
        raise MechanicsContractError("virtual profile placement fields disagree")

    coarse_axes = {
        "rear_clamp_contact_x_board_mm": [225.0, 305.0, 385.0],
        "rear_edge_to_base_axis_y_mm": [0.0, 50.0, 100.0],
        "base_yaw_board_deg": [-105.0, -90.0, -75.0],
        "keyboard_tcp_length_mm": [80.0, 100.0, 120.0],
    }

    def candidate(
        rear_clamp_x: float,
        rear_axis_y: float,
        yaw_deg: float,
        keyboard_tcp: float,
        *,
        candidate_classification: str,
    ) -> dict[str, Any]:
        yaw_rad = math.radians(yaw_deg)
        matrix = [
            math.cos(yaw_rad), -math.sin(yaw_rad), 0.0,
            rear_clamp_x + clamp_to_axis_x,
            math.sin(yaw_rad), math.cos(yaw_rad), 0.0,
            board_rear_edge_y + rear_axis_y,
            0.0, 0.0, 1.0, source_z,
            0.0, 0.0, 0.0, 1.0,
        ]
        hypothesis = {
            "candidate_classification": candidate_classification,
            "rear_clamp_contact_x_board_mm": rear_clamp_x,
            "rear_edge_to_base_axis_y_mm": rear_axis_y,
            "base_yaw_board_deg": yaw_deg,
            "keyboard_tcp_length_mm": keyboard_tcp,
            "robot_placement_matrix_row_major": matrix,
        }
        hypothesis["candidate_id"] = (
            f"placement-tcp-{_canonical_sha256(hypothesis)[:16]}"
        )
        return hypothesis

    control = candidate(
        source_x,
        source_y,
        math.degrees(source_yaw_rad),
        source_tcp,
        candidate_classification="RETAINED_ARM198_CONTROL",
    )
    control["robot_placement_matrix_row_major"] = source_matrix
    control_unsigned = {
        key: value for key, value in control.items() if key != "candidate_id"
    }
    control["candidate_id"] = (
        f"placement-tcp-{_canonical_sha256(control_unsigned)[:16]}"
    )
    coarse = [
        candidate(
            rear_clamp_x,
            rear_axis_y,
            yaw_deg,
            keyboard_tcp,
            candidate_classification="DOCUMENTED_COARSE_SENSITIVITY_HYPOTHESIS",
        )
        for rear_clamp_x, rear_axis_y, yaw_deg, keyboard_tcp in product(
            coarse_axes["rear_clamp_contact_x_board_mm"],
            coarse_axes["rear_edge_to_base_axis_y_mm"],
            coarse_axes["base_yaw_board_deg"],
            coarse_axes["keyboard_tcp_length_mm"],
        )
    ]
    candidates = [control, *coarse]
    if len({item["candidate_id"] for item in candidates}) != len(candidates):
        raise MechanicsContractError("placement/TCP candidate ids are not unique")

    blocker_pairs = sorted(
        localization.get("blocker_localizations", []),
        key=lambda item: tuple(item.get("body_pair", [])),
    )
    result: dict[str, Any] = {
        "schema": PLACEMENT_TCP_SEARCH_PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_PLACEMENT_TCP_SCREENING",
        "source_physical_blocker_experiment_plan_sha256": experiment_plan[
            "plan_sha256"
        ],
        "source_route_variant_request_sha256": route_variant_request[
            "request_sha256"
        ],
        "source_diagnostic_receipt_sha256": diagnostic_receipt["receipt_sha256"],
        "source_localization_sha256": localization["proposal_sha256"],
        "source_virtual_profile_sha256": virtual_profile_sha256,
        "source_collision_candidate_sha256": source_bindings[
            "collision_candidate_sha256"
        ],
        "source_collision_pair_policy_sha256": source_bindings[
            "collision_pair_policy_sha256"
        ],
        "source_station_route_predicate_sha256": source_bindings[
            "station_route_predicate_sha256"
        ],
        "source_toolchain_lock_sha256": source_bindings["toolchain_lock_sha256"],
        "source_mission_route_coverage_sha256": mission_coverage_hash,
        "hypothesis_source": (
            "PREHARDWARE_MISSION_COVERAGE_DOCUMENTED_SENSITIVITY_GRID"
        ),
        "coarse_axes": coarse_axes,
        "control_candidate_id": control["candidate_id"],
        "control_candidate_count": 1,
        "coarse_candidate_count": len(coarse),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "physical_blocker_pairs": [item["body_pair"] for item in blocker_pairs],
        "screening_stages": [
            "CANONICAL_IK_AND_DISCRETE_CONTINUITY",
            "EXACT_FULL_LINK_COLLISION_EVALUATOR",
            "DETERMINISTIC_SHORTLIST_SELECTION",
            "SELECTED_NATIVE_ISAAC_REPLAY",
        ],
        "candidate_rejection_recording_required": True,
        "ranking_order": [
            "physical_blocker_pair_count:ASC",
            "blocked_sample_count:ASC",
            "minimum_normalized_arm_joint_margin:DESC",
            "maximum_position_error_mm:ASC",
            "candidate_id:ASC",
        ],
        "maximum_native_shortlist_count": 8,
        "collision_geometry_changed": False,
        "route_shape_changed": False,
        "installed_profile_eligible": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "all_candidates_are_unmeasured_simulation_sensitivity_hypotheses",
            "candidate_values_are_not_installation_tolerances_or_allowances",
            "discrete_collision_screening_is_not_continuous_clearance_proof",
            "physical_board_and_keyboard_solids_are_preserved",
            "endpoint_and_route_shape_qualification_remain_separate",
        ],
    }
    result["plan_sha256"] = _canonical_sha256(result)
    return result


def build_route_shape_campaign_plan(
    placement_search_plan: dict[str, Any],
    native_selection: dict[str, Any],
    route_variant_request: dict[str, Any],
) -> dict[str, Any]:
    """Plan the bounded ARM-200 route-shape campaign without screening it."""
    for document, hash_field, label in (
        (placement_search_plan, "plan_sha256", "placement/TCP search plan"),
        (native_selection, "selection_sha256", "native selection"),
        (route_variant_request, "request_sha256", "route variant request"),
    ):
        claimed = document.get(hash_field)
        unsigned = dict(document)
        unsigned.pop(hash_field, None)
        if claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} hash mismatch")

    control_id = placement_search_plan.get("control_candidate_id")
    selected_id = native_selection.get("selected_candidate_id")
    candidates = placement_search_plan.get("candidates")
    retained = native_selection.get("retained_results")
    if (
        placement_search_plan.get("schema") != PLACEMENT_TCP_SEARCH_PLAN_SCHEMA
        or placement_search_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_PLACEMENT_TCP_SCREENING"
        or placement_search_plan.get("route_shape_changed") is not False
        or native_selection.get("schema") != PLACEMENT_TCP_NATIVE_SELECTION_SCHEMA
        or native_selection.get("status") != "NO_NATIVE_IMPROVEMENT_RETAINED"
        or native_selection.get("source_search_plan_sha256")
        != placement_search_plan.get("plan_sha256")
        or native_selection.get("native_improvement_over_control") is not False
        or selected_id != control_id
        or not isinstance(candidates, list)
        or not isinstance(retained, list)
        or route_variant_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or route_variant_request.get("request_sha256")
        != placement_search_plan.get("source_route_variant_request_sha256")
        or route_variant_request.get("route_variant_applied") is not True
        or route_variant_request.get("collision_geometry_changed") is not False
    ):
        raise MechanicsContractError("route-shape campaign lineage changed")

    selected_candidates = [
        item for item in candidates if item.get("candidate_id") == selected_id
    ]
    selected_results = [
        item for item in retained if item.get("candidate_id") == selected_id
    ]
    if (
        len(selected_candidates) != 1
        or len(selected_results) != 1
        or selected_candidates[0].get("candidate_classification")
        != "RETAINED_ARM198_CONTROL"
        or selected_results[0].get("physical_solid_blocker_pair_count") != 7
    ):
        raise MechanicsContractError("route-shape control evidence changed")

    for document, label in (
        (placement_search_plan, "placement/TCP search plan"),
        (native_selection, "native selection"),
        (route_variant_request, "route variant request"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")
    if (
        placement_search_plan.get("physical_authority") is not False
        or native_selection.get("physical_authority") is not False
        or placement_search_plan.get("gate_promotions") != []
        or native_selection.get("gate_promotions") != []
    ):
        raise MechanicsContractError("route-shape source evidence gained authority")

    samples = route_variant_request.get("samples")
    if not isinstance(samples, list) or not samples:
        raise MechanicsContractError("route-shape source samples are absent")
    if any(
        not isinstance(sample, dict) or sample.get("sequence") != sequence
        for sequence, sample in enumerate(samples)
    ):
        raise MechanicsContractError("route-shape source sequence is not contiguous")
    transit_sequences = [
        sample["sequence"] for sample in samples if sample.get("phase") == "TRANSIT"
    ]
    endpoint_sequences = [
        sample["sequence"] for sample in samples if sample.get("phase") != "TRANSIT"
    ]
    if not transit_sequences or not endpoint_sequences:
        raise MechanicsContractError("route-shape source lacks transit or endpoints")

    topologies = ["DIRECT_LINEAR", "X_THEN_Y", "Y_THEN_X"]
    corridor_heights = [70.0, 90.0, 110.0]

    def route_candidate(
        topology: str,
        corridor_height_mm: float,
        *,
        classification: str,
        source_request_reused: bool,
    ) -> dict[str, Any]:
        candidate: dict[str, Any] = {
            "candidate_classification": classification,
            "xy_corridor_topology": topology,
            "corridor_height_board_mm": corridor_height_mm,
            "corridor_height_ramp_fraction": (
                None if source_request_reused else 0.25
            ),
            "transit_resampling": (
                "SOURCE_REQUEST_EXACT"
                if source_request_reused
                else "ARC_LENGTH_PIECEWISE_LINEAR_WITH_SYMMETRIC_Z_RAMPS"
            ),
            "source_request_reused_exactly": source_request_reused,
            "non_transit_endpoints_changed": False,
            "sample_count_changed": False,
            "timing_changed": False,
        }
        candidate["candidate_id"] = (
            f"route-shape-{_canonical_sha256(candidate)[:16]}"
        )
        return candidate

    control = route_candidate(
        "DIRECT_LINEAR",
        70.0,
        classification="RETAINED_ARM198_ARM199_CONTROL",
        source_request_reused=True,
    )
    variants = [
        route_candidate(
            topology,
            height,
            classification="PREDECLARED_TRANSIT_CORRIDOR_HYPOTHESIS",
            source_request_reused=False,
        )
        for topology, height in product(topologies, corridor_heights)
        if not (topology == "DIRECT_LINEAR" and height == 70.0)
    ]
    route_candidates = [control, *variants]
    if len({item["candidate_id"] for item in route_candidates}) != 9:
        raise MechanicsContractError("route-shape candidate ids are not unique")

    result: dict[str, Any] = {
        "schema": ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_ROUTE_SHAPE_SCREENING",
        "source_placement_tcp_search_plan_sha256": placement_search_plan[
            "plan_sha256"
        ],
        "source_placement_tcp_native_selection_sha256": native_selection[
            "selection_sha256"
        ],
        "source_route_variant_request_sha256": route_variant_request[
            "request_sha256"
        ],
        "source_collision_candidate_sha256": placement_search_plan[
            "source_collision_candidate_sha256"
        ],
        "source_collision_pair_policy_sha256": placement_search_plan[
            "source_collision_pair_policy_sha256"
        ],
        "source_station_route_predicate_sha256": placement_search_plan[
            "source_station_route_predicate_sha256"
        ],
        "source_toolchain_lock_sha256": placement_search_plan[
            "source_toolchain_lock_sha256"
        ],
        "selected_placement_tcp_candidate": selected_candidates[0],
        "control_native_physical_blocker_pair_count": 7,
        "route_shape_axes": {
            "xy_corridor_topology": topologies,
            "corridor_height_board_mm": corridor_heights,
            "corridor_height_ramp_fraction": [0.25],
        },
        "control_candidate_id": control["candidate_id"],
        "control_candidate_count": 1,
        "variant_candidate_count": len(variants),
        "candidate_count": len(route_candidates),
        "candidates": route_candidates,
        "source_sample_count": len(samples),
        "source_transit_sequence_count": len(transit_sequences),
        "source_transit_sequences": transit_sequences,
        "preserved_endpoint_sequence_count": len(endpoint_sequences),
        "preserved_endpoint_sequences": endpoint_sequences,
        "endpoint_scoring_separate": True,
        "candidate_rejection_recording_required": True,
        "screening_stages": [
            "DETERMINISTIC_ROUTE_MATERIALIZATION",
            "CANONICAL_IK_AND_DISCRETE_CONTINUITY",
            "EXACT_FULL_LINK_COLLISION_EVALUATOR",
            "TRANSIT_AND_ENDPOINT_BLOCKER_SEPARATION",
            "DETERMINISTIC_SHORTLIST_SELECTION",
            "SELECTED_NATIVE_ISAAC_REPLAY",
        ],
        "ranking_order": [
            "transit_physical_blocker_pair_count:ASC",
            "transit_blocked_sample_count:ASC",
            "endpoint_physical_blocker_pair_count:ASC",
            "minimum_normalized_arm_joint_margin:DESC",
            "maximum_position_error_mm:ASC",
            "candidate_id:ASC",
        ],
        "maximum_native_shortlist_count": 4,
        "placement_tcp_changed": False,
        "collision_geometry_changed": False,
        "non_transit_endpoints_changed": False,
        "installed_profile_eligible": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "route_candidates_are_simulation_only_transit_hypotheses",
            "contact_hover_retract_and_park_endpoints_are_unchanged",
            "endpoint_blockers_are_reported_separately_not_waived",
            "physical_board_and_keyboard_solids_are_preserved",
            "discrete_collision_screening_is_not_continuous_clearance_proof",
            "no_candidate_grants_hardware_motion_or_contact_authority",
        ],
    }
    result["plan_sha256"] = _canonical_sha256(result)
    return result


def materialize_route_shape_candidate(
    campaign_plan: dict[str, Any],
    source_request: dict[str, Any],
    candidate_id: str,
) -> dict[str, Any]:
    """Materialize one predeclared ARM-200 route without changing endpoints."""
    for document, hash_field, label in (
        (campaign_plan, "plan_sha256", "route-shape campaign plan"),
        (source_request, "request_sha256", "source route request"),
    ):
        claimed = document.get(hash_field)
        unsigned = dict(document)
        unsigned.pop(hash_field, None)
        if claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} hash mismatch")
    candidates = campaign_plan.get("candidates")
    matches = [
        item for item in candidates or [] if item.get("candidate_id") == candidate_id
    ]
    if (
        campaign_plan.get("schema") != ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA
        or campaign_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_ROUTE_SHAPE_SCREENING"
        or campaign_plan.get("source_route_variant_request_sha256")
        != source_request.get("request_sha256")
        or len(matches) != 1
    ):
        raise MechanicsContractError("route-shape materialization lineage changed")
    for document, label in (
        (campaign_plan, "route-shape campaign plan"),
        (source_request, "source route request"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    candidate = matches[0]
    samples = source_request.get("samples")
    if not isinstance(samples, list) or len(samples) != campaign_plan.get(
        "source_sample_count"
    ):
        raise MechanicsContractError("route-shape source sample count changed")
    if any(
        not isinstance(sample, dict) or sample.get("sequence") != sequence
        for sequence, sample in enumerate(samples)
    ):
        raise MechanicsContractError("route-shape source sequence is not contiguous")

    materialized_samples = json.loads(json.dumps(samples))
    topology = candidate.get("xy_corridor_topology")
    corridor_z = _finite_number(
        candidate.get("corridor_height_board_mm"), "route corridor height"
    )
    source_exact = candidate.get("source_request_reused_exactly") is True
    if source_exact:
        if (
            candidate.get("transit_resampling") != "SOURCE_REQUEST_EXACT"
            or candidate.get("corridor_height_ramp_fraction") is not None
        ):
            raise MechanicsContractError("route-shape control definition changed")
    else:
        if (
            topology not in {"DIRECT_LINEAR", "X_THEN_Y", "Y_THEN_X"}
            or candidate.get("transit_resampling")
            != "ARC_LENGTH_PIECEWISE_LINEAR_WITH_SYMMETRIC_Z_RAMPS"
            or candidate.get("corridor_height_ramp_fraction") != 0.25
        ):
            raise MechanicsContractError("route-shape variant definition changed")

    def point(sample: dict[str, Any]) -> list[float]:
        value = sample.get("expected_tool_tip_board_mm")
        if not isinstance(value, list) or len(value) != 3:
            raise MechanicsContractError("route-shape sample lacks Cartesian point")
        return [_finite_number(item, "route coordinate") for item in value]

    def xy_at(start: list[float], end: list[float], progress: float) -> list[float]:
        if topology == "DIRECT_LINEAR":
            return [
                start[0] + progress * (end[0] - start[0]),
                start[1] + progress * (end[1] - start[1]),
            ]
        corner = (
            [end[0], start[1]]
            if topology == "X_THEN_Y"
            else [start[0], end[1]]
        )
        lengths = [
            math.hypot(corner[0] - start[0], corner[1] - start[1]),
            math.hypot(end[0] - corner[0], end[1] - corner[1]),
        ]
        total = sum(lengths)
        if total <= 0:
            return start[:2]
        distance = progress * total
        if distance <= lengths[0] and lengths[0] > 0:
            fraction = distance / lengths[0]
            return [
                start[0] + fraction * (corner[0] - start[0]),
                start[1] + fraction * (corner[1] - start[1]),
            ]
        if lengths[1] <= 0:
            return corner
        fraction = (distance - lengths[0]) / lengths[1]
        return [
            corner[0] + fraction * (end[0] - corner[0]),
            corner[1] + fraction * (end[1] - corner[1]),
        ]

    changed_sequences: list[int] = []
    if not source_exact:
        index = 0
        while index < len(samples):
            if samples[index].get("phase") != "TRANSIT":
                index += 1
                continue
            run_start = index
            while index < len(samples) and samples[index].get("phase") == "TRANSIT":
                index += 1
            run_end = index
            if run_start == 0 or run_end >= len(samples):
                raise MechanicsContractError("transit run lacks preserved endpoints")
            start = point(samples[run_start - 1])
            end = point(samples[run_end])
            count = run_end - run_start
            for offset, sequence in enumerate(range(run_start, run_end)):
                progress = (offset + 1) / (count + 1)
                xy = xy_at(start, end, progress)
                if progress <= 0.25:
                    z = start[2] + progress / 0.25 * (corridor_z - start[2])
                elif progress >= 0.75:
                    z = corridor_z + (progress - 0.75) / 0.25 * (
                        end[2] - corridor_z
                    )
                else:
                    z = corridor_z
                replacement = [xy[0], xy[1], z]
                if replacement != point(samples[sequence]):
                    changed_sequences.append(sequence)
                materialized_samples[sequence][
                    "expected_tool_tip_board_mm"
                ] = replacement

    endpoint_sequences = campaign_plan.get("preserved_endpoint_sequences")
    if any(
        materialized_samples[sequence] != samples[sequence]
        for sequence in endpoint_sequences
    ):
        raise MechanicsContractError("route-shape materialization changed an endpoint")
    if [
        sample["sequence"]
        for sample in materialized_samples
        if sample.get("phase") == "TRANSIT"
    ] != campaign_plan.get("source_transit_sequences"):
        raise MechanicsContractError("route-shape transit domain changed")

    result = dict(source_request)
    result.pop("request_sha256", None)
    result.update({
        "status": "READY_FOR_IK_QUALIFICATION",
        "source_route_shape_campaign_plan_sha256": campaign_plan["plan_sha256"],
        "route_shape_candidate_id": candidate_id,
        "route_shape_candidate": candidate,
        "source_route_variant_request_sha256": source_request["request_sha256"],
        "route_shape_materialized": True,
        "route_shape_domain_sequences": list(
            campaign_plan["source_transit_sequences"]
        ),
        "changed_cartesian_sequences": changed_sequences,
        "non_transit_endpoints_changed": False,
        "placement_tcp_changed": False,
        "collision_geometry_changed": False,
        "installed_profile_eligible": False,
        "samples": materialized_samples,
        "limitations": list(source_request.get("limitations", [])) + [
            "route_shape_is_a_plan_bound_simulation_hypothesis",
            "all_non_transit_endpoints_are_preserved_exactly",
            "fresh_ik_and_collision_qualification_are_required",
        ],
    })
    result["request_sha256"] = _canonical_sha256(result)
    return result


def screen_route_shape_campaign(
    campaign_plan: dict[str, Any],
    source_request: dict[str, Any],
    candidate_evidence: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    collision_candidate: dict[str, Any],
    collision_pair_policy: dict[str, Any],
    station_route_predicate: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    """Aggregate fixed ARM-200 IK evidence and exact full-link OBB scores."""
    plan_hash = campaign_plan.get("plan_sha256")
    unsigned_plan = dict(campaign_plan)
    unsigned_plan.pop("plan_sha256", None)
    candidates = campaign_plan.get("candidates")
    if (
        campaign_plan.get("schema") != ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA
        or campaign_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_ROUTE_SHAPE_SCREENING"
        or plan_hash != _canonical_sha256(unsigned_plan)
        or not isinstance(candidates, list)
        or len(candidates) != campaign_plan.get("candidate_count")
    ):
        raise MechanicsContractError("route-shape campaign plan is invalid")
    candidate_ids = [item.get("candidate_id") for item in candidates]
    if (
        any(not isinstance(item, str) for item in candidate_ids)
        or len(set(candidate_ids)) != len(candidate_ids)
        or set(candidate_evidence) != set(candidate_ids)
    ):
        raise MechanicsContractError("route-shape candidate evidence coverage changed")
    source_hash = source_request.get("request_sha256")
    unsigned_source = dict(source_request)
    unsigned_source.pop("request_sha256", None)
    if (
        source_hash != _canonical_sha256(unsigned_source)
        or source_hash != campaign_plan.get("source_route_variant_request_sha256")
    ):
        raise MechanicsContractError("route-shape source request lineage changed")

    candidate_hash = collision_candidate.get("candidate_sha256")
    candidate_unsigned = dict(collision_candidate)
    candidate_unsigned.pop("candidate_sha256", None)
    policy_hash = collision_pair_policy.get("policy_sha256")
    policy_unsigned = dict(collision_pair_policy)
    policy_unsigned.pop("policy_sha256", None)
    predicate_hash = station_route_predicate.get("predicate_sha256")
    predicate_unsigned = dict(station_route_predicate)
    predicate_unsigned.pop("predicate_sha256", None)
    if (
        candidate_hash != _canonical_sha256(candidate_unsigned)
        or policy_hash != _canonical_sha256(policy_unsigned)
        or predicate_hash != _canonical_sha256(predicate_unsigned)
        or candidate_hash != campaign_plan.get("source_collision_candidate_sha256")
        or policy_hash != campaign_plan.get("source_collision_pair_policy_sha256")
        or predicate_hash != campaign_plan.get("source_station_route_predicate_sha256")
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
        or collision_pair_policy.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY"
        or station_route_predicate.get("status") != "PASS"
    ):
        raise MechanicsContractError("route-shape collision lineage changed")
    for document, label in (
        (campaign_plan, "route-shape campaign plan"),
        (source_request, "route-shape source request"),
        (collision_candidate, "collision candidate"),
        (collision_pair_policy, "collision pair policy"),
        (station_route_predicate, "station route predicate"),
    ):
        if (
            document.get("physical_authority", False) is not False
            or document.get("hardware_access", False) is not False
            or document.get("controller_commands", []) != []
            or document.get("hardware_writes", 0) != 0
            or document.get("hardware_write_count", 0) != 0
            or document.get("physical_movements", 0) != 0
            or document.get("physical_movement_count", 0) != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    try:
        from rocell.application._pinned_model import load_pinned_urdf
        from rocell.application.context import load_simulation_context
        from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
        from rocell.kinematics import ARM_JOINT_NAMES
        from rocell.simulation.collision import (
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
            OrientedBoxMm,
            evaluate_collision_pose,
        )
    except ImportError as exc:
        raise MechanicsContractError(
            "offline collision runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    physical_ids = station_route_predicate.get("physical_workcell_body_ids")
    if not isinstance(physical_ids, list) or not physical_ids:
        raise MechanicsContractError("station predicate lacks physical workcell ids")
    physical_id_set = set(physical_ids)
    robot_documents = collision_candidate.get("robot_bodies")
    workcell_documents = collision_candidate.get("workcell_bodies")
    if not isinstance(robot_documents, list) or not isinstance(workcell_documents, list):
        raise MechanicsContractError("collision candidate body collections are invalid")
    selected_documents = [
        *robot_documents,
        *(
            item
            for item in workcell_documents
            if item.get("body_id") in physical_id_set
        ),
    ]
    selected_static_ids = {
        item.get("body_id")
        for item in selected_documents
        if item in workcell_documents
    }
    if selected_static_ids != physical_id_set:
        raise MechanicsContractError("physical workcell body coverage changed")

    def primitive(document: dict[str, Any]) -> OrientedBoxMm:
        if document.get("kind") != "oriented_box":
            raise MechanicsContractError("ARM-201 requires oriented-box primitives")
        return OrientedBoxMm(
            Vec3.from_iterable(document["center_mm"]),
            Vec3.from_iterable(document["half_extents_mm"]),
            Rotation3(tuple(document["rotation_row_major"])),
        )

    requirements = []
    bodies = []
    for document in selected_documents:
        is_static = document["body_id"] in physical_id_set
        role = (
            CollisionBodyRole.STATIC_ENVIRONMENT
            if is_static
            else CollisionBodyRole.ROBOT_LINK
        )
        mode = (
            CollisionBindingMode.STATIC_ROOT
            if is_static
            else CollisionBindingMode.RIGID_FRAME
        )
        requirements.append(
            CollisionBodyRequirement(
                document["body_id"],
                document["parent_frame"],
                role,
                mode,
                "ARM-201 exact exploratory full-link OBB screen",
            )
        )
        bodies.append(
            CollisionBody(
                document["body_id"],
                document["parent_frame"],
                role,
                CollisionEvidenceState.PINNED_DIGITAL,
                tuple(primitive(item) for item in document["primitives"]),
                mode,
                f"collision candidate {candidate_hash}",
            )
        )
    exclusions = tuple(
        CollisionPairExclusion(
            pair[0],
            pair[1],
            CollisionExclusionScope.URDF_ADJACENT_DIAGNOSTIC,
            CollisionExclusionEvidenceState.PINNED_KINEMATIC_DIAGNOSTIC,
            "accepted directly connected diagnostic pair",
            f"collision pair policy {policy_hash}",
        )
        for pair in collision_pair_policy.get("accepted_exclusion_pairs", [])
    )
    contract = CollisionGeometryContract(
        "TACTEVRA-ARM201-EXPLORATORY-OBB-V1",
        "board",
        tuple(requirements),
        tuple(bodies),
        exclusions,
    )
    clearance = CollisionClearancePolicy(
        1e-9,
        0.0,
        0.0,
        CollisionClearanceEvidenceState.PINNED_DIGITAL,
        "ARM-201 numerical touching threshold; not measured clearance",
    )
    evaluation_policy = CollisionEvaluationPolicy(clearance_policy=clearance)
    root = workspace.resolve(strict=True)
    context = load_simulation_context(
        root, root / "software/config/system_manifest.json"
    )
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    remaining = set(model.movable_joint_names) - set(ARM_JOINT_NAMES)
    if len(remaining) != 1:
        raise MechanicsContractError("pinned robot gripper joint topology changed")
    gripper_joint = next(iter(remaining))
    placement = campaign_plan.get("selected_placement_tcp_candidate")
    matrix = placement.get("robot_placement_matrix_row_major") if isinstance(
        placement, dict
    ) else None
    if not isinstance(matrix, list) or len(matrix) != 16:
        raise MechanicsContractError("route-shape placement/TCP candidate is invalid")
    board_t_base = RigidTransform(
        "board",
        "base_link",
        Rotation3(
            tuple(matrix[index] for index in (0, 1, 2, 4, 5, 6, 8, 9, 10))
        ),
        Vec3(matrix[3], matrix[7], matrix[11]),
    )
    fixed = model.joint("world_to_base_link")
    board_t_world = board_t_base.compose(fixed.transform_at(None).inverse())

    outcomes: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        request, ik = candidate_evidence[candidate_id]
        expected_request = materialize_route_shape_candidate(
            campaign_plan, source_request, candidate_id
        )
        if request != expected_request:
            raise MechanicsContractError(
                f"route-shape request {candidate_id} is not canonical"
            )
        receipt_hash = ik.get("receipt_sha256")
        unsigned_receipt = dict(ik)
        unsigned_receipt.pop("receipt_sha256", None)
        if (
            ik.get("schema") != TCP_IK_SCREEN_SCHEMA
            or receipt_hash != _canonical_sha256(unsigned_receipt)
            or ik.get("source_request_sha256") != request["request_sha256"]
            or ik.get("source_route_shape_campaign_plan_sha256") != plan_hash
            or ik.get("route_shape_candidate_id") != candidate_id
            or ik.get("hardware_access") is not False
            or ik.get("controller_commands") != []
            or ik.get("hardware_writes") != 0
            or ik.get("physical_movements") != 0
        ):
            raise MechanicsContractError(
                f"route-shape IK receipt {candidate_id} is invalid"
            )
        outcome: dict[str, Any] = {
            "candidate_id": candidate_id,
            "candidate_classification": candidate["candidate_classification"],
            "candidate": candidate,
            "request_sha256": request["request_sha256"],
            "ik_receipt_sha256": receipt_hash,
            "ik_status": ik["status"],
            "ik_all_samples_accepted": ik["ik_all_samples_accepted"],
            "evaluated_sample_count": ik["evaluated_sample_count"],
            "ik_metrics": ik["metrics"],
            "collision_screening_executed": False,
            "rejection_reasons": [],
        }
        if not ik["ik_all_samples_accepted"]:
            failure = ik["joint_results"][-1]
            outcome.update({
                "rejection_reasons": ["CANONICAL_IK_OR_CONTINUITY_REJECTED"],
                "first_rejected_sample_sequence": failure["waypoint_sequence"],
                "first_rejection_reason": failure["failure_reason"],
            })
            outcomes.append(outcome)
            continue
        if len(ik["joint_results"]) != len(request["samples"]):
            raise MechanicsContractError("accepted route-shape IK receipt is incomplete")

        transit_pairs: set[tuple[str, str]] = set()
        endpoint_pairs: set[tuple[str, str]] = set()
        all_pairs: set[tuple[str, str]] = set()
        transit_blocked = 0
        endpoint_blocked = 0
        sample_reports: list[dict[str, Any]] = []
        for sample, joint_result in zip(request["samples"], ik["joint_results"]):
            positions = {
                name: JointPosition.radians(
                    joint_result["solution_arm_joint_positions_rad"][name]
                )
                for name in ARM_JOINT_NAMES
            }
            positions[gripper_joint] = context.scenario.fixed_gripper_position
            base_transforms = model.forward_kinematics(positions)
            board_transforms = {
                frame: board_t_world.compose(transform)
                for frame, transform in base_transforms.items()
            }
            pose = CollisionPose(
                f"{candidate_id}-sample-{sample['sequence']:04d}",
                "board",
                {
                    body["parent_frame"]: board_transforms[body["parent_frame"]]
                    for body in robot_documents
                },
            )
            evaluated = evaluate_collision_pose(contract, pose, evaluation_policy)
            pairs = {
                tuple(sorted((item.first_body_id, item.second_body_id)))
                for item in evaluated.collisions
            }
            physical_pairs = {
                pair
                for pair in pairs
                if any(item in physical_id_set for item in pair)
            }
            is_transit = sample["phase"] == "TRANSIT"
            if is_transit:
                transit_pairs.update(physical_pairs)
                transit_blocked += int(bool(physical_pairs))
            else:
                endpoint_pairs.update(physical_pairs)
                endpoint_blocked += int(bool(physical_pairs))
            all_pairs.update(pairs)
            sample_reports.append({
                "sample_sequence": sample["sequence"],
                "phase": sample["phase"],
                "collision_report_sha256": evaluated.report_hash,
                "collision_pairs": [list(pair) for pair in sorted(pairs)],
                "physical_blocker_pairs": [
                    list(pair) for pair in sorted(physical_pairs)
                ],
            })
        outcome.update({
            "collision_screening_executed": True,
            "collision_contract_sha256": contract.content_hash,
            "collision_policy_sha256": evaluation_policy.content_hash,
            "transit_blocked_sample_count": transit_blocked,
            "transit_physical_blocker_pair_count": len(transit_pairs),
            "transit_physical_blocker_pairs": [
                list(pair) for pair in sorted(transit_pairs)
            ],
            "endpoint_blocked_sample_count": endpoint_blocked,
            "endpoint_physical_blocker_pair_count": len(endpoint_pairs),
            "endpoint_physical_blocker_pairs": [
                list(pair) for pair in sorted(endpoint_pairs)
            ],
            "all_collision_pair_count": len(all_pairs),
            "all_collision_pairs": [list(pair) for pair in sorted(all_pairs)],
            "sample_reports": sample_reports,
            "rejection_reasons": (
                ["DISCRETE_FULL_LINK_PHYSICAL_BLOCKERS_OBSERVED"]
                if transit_blocked or endpoint_blocked
                else []
            ),
        })
        outcomes.append(outcome)

    ranked = sorted(
        (item for item in outcomes if item["collision_screening_executed"]),
        key=_route_shape_candidate_rank_key,
    )
    shortlist_count = min(
        int(campaign_plan["maximum_native_shortlist_count"]), len(ranked)
    )
    shortlist = [item["candidate_id"] for item in ranked[:shortlist_count]]
    result: dict[str, Any] = {
        "schema": ROUTE_SHAPE_CAMPAIGN_SCREEN_SCHEMA,
        "status": (
            "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY"
            if shortlist
            else "BLOCKED_NO_IK_ACCEPTED_ROUTE_SHAPES"
        ),
        "source_campaign_plan_sha256": plan_hash,
        "source_route_variant_request_sha256": source_hash,
        "source_collision_candidate_sha256": candidate_hash,
        "source_collision_pair_policy_sha256": policy_hash,
        "source_station_route_predicate_sha256": predicate_hash,
        "candidate_count": len(candidates),
        "ik_accepted_candidate_count": len(ranked),
        "ik_rejected_candidate_count": len(candidates) - len(ranked),
        "collision_screened_candidate_count": len(ranked),
        "outcomes": outcomes,
        "ranked_candidate_ids": [item["candidate_id"] for item in ranked],
        "native_shortlist_candidate_ids": shortlist,
        "native_shortlist_count": len(shortlist),
        "maximum_native_shortlist_count": campaign_plan[
            "maximum_native_shortlist_count"
        ],
        "ranking_order": list(campaign_plan["ranking_order"]),
        "endpoint_scoring_separate": True,
        "exact_obb_collision_kernel_used": True,
        "placement_tcp_changed": False,
        "collision_geometry_changed": False,
        "non_transit_endpoints_changed": False,
        "installed_profile_eligible": False,
        "continuous_collision_proven": False,
        "native_isaac_replay_executed": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "exploratory_uninstalled_collision_candidate_only",
            "discrete_samples_do_not_prove_continuous_clearance",
            "one_picometre_touching_threshold_is_not_measured_clearance",
            "native_isaac_replay_is_limited_to_the_retained_shortlist",
            "no_candidate_grants_hardware_motion_or_contact_authority",
        ],
    }
    result["screen_sha256"] = _canonical_sha256(result)
    return result


def load_keyboard_layout(path: Path) -> dict[str, Any]:
    """Load the governed nominal profile and derive board-frame key regions."""
    raw = json.loads(path.read_bytes())
    if raw.get("schema") != "rocell.nominal_target_profiles.v1":
        raise MechanicsContractError("unexpected nominal-target schema")
    if raw.get("status") != "SIMULATION_ONLY_NOMINAL_UNMEASURED":
        raise MechanicsContractError("nominal profile status changed without review")
    keyboard = raw.get("keyboard")
    if not isinstance(keyboard, dict):
        raise MechanicsContractError("keyboard profile missing")
    origin = keyboard.get("device_origin_board_xy_mm")
    default_half = keyboard.get("key_half_extent_mm")
    if not isinstance(origin, list) or len(origin) != 2:
        raise MechanicsContractError("keyboard origin must contain two values")
    if not isinstance(default_half, list) or len(default_half) != 2:
        raise MechanicsContractError("key half extent must contain two values")
    origin_xy = [_finite_number(v, "keyboard origin") for v in origin]
    default_half_xy = [_finite_number(v, "key half extent") for v in default_half]
    if min(default_half_xy) <= 0:
        raise MechanicsContractError("key half extents must be positive")

    regions: dict[str, dict[str, list[float]]] = {}
    rows = keyboard.get("rows")
    if not isinstance(rows, list):
        raise MechanicsContractError("keyboard rows missing")
    for row in rows:
        ids = row.get("key_ids")
        first = row.get("first_center_xy_mm")
        step = row.get("step_xy_mm")
        if not isinstance(ids, list) or not isinstance(first, list) or not isinstance(step, list):
            raise MechanicsContractError("malformed keyboard row")
        if len(first) != 2 or len(step) != 2:
            raise MechanicsContractError("keyboard row coordinates must be two-dimensional")
        first_xy = [_finite_number(v, "row first center") for v in first]
        step_xy = [_finite_number(v, "row step") for v in step]
        for index, key_id in enumerate(ids):
            if not isinstance(key_id, str) or key_id in regions:
                raise MechanicsContractError("key identifiers must be unique strings")
            local = [first_xy[axis] + index * step_xy[axis] for axis in range(2)]
            regions[key_id] = {
                "center_board_xy_mm": [origin_xy[axis] + local[axis] for axis in range(2)],
                "half_extent_mm": list(default_half_xy),
            }

    explicit = keyboard.get("explicit_targets")
    if not isinstance(explicit, dict):
        raise MechanicsContractError("explicit keyboard targets missing")
    for key_id, target in explicit.items():
        center = target.get("center_xy_mm")
        half = target.get("half_extent_mm")
        if not isinstance(center, list) or len(center) != 2 or not isinstance(half, list) or len(half) != 2:
            raise MechanicsContractError(f"malformed explicit target {key_id}")
        center_xy = [_finite_number(v, f"{key_id} center") for v in center]
        half_xy = [_finite_number(v, f"{key_id} half extent") for v in half]
        if min(half_xy) <= 0:
            raise MechanicsContractError(f"{key_id} half extents must be positive")
        regions[key_id] = {
            "center_board_xy_mm": [origin_xy[axis] + center_xy[axis] for axis in range(2)],
            "half_extent_mm": half_xy,
        }

    missing = sorted(set(REPRESENTATIVE_KEYS) - regions.keys())
    if missing:
        raise MechanicsContractError(f"representative keys missing: {missing}")
    return {
        "source_profile_id": keyboard.get("profile_id"),
        "source_status": raw["status"],
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "target_plane_z_board_mm": _finite_number(
            keyboard.get("target_plane_z_board_mm"), "target plane"
        ),
        "representative_regions": {key: regions[key] for key in REPRESENTATIVE_KEYS},
        "guard_regions": regions,
    }


def build_profile(layout_path: Path) -> dict[str, Any]:
    layout = load_keyboard_layout(layout_path)
    profile = {
        "schema": PROFILE_SCHEMA,
        "status": PROVISIONAL_STATUS,
        "physical_release_effect": "NONE",
        "authority": {
            "hardware": False,
            "motion": False,
            "physical_keyboard_qualification": False,
        },
        "provenance": {
            "state": "SYNTHETIC_BOUNDED_PRIOR_NOT_PRODUCT_SPECIFICATION",
            "layout_profile_id": layout["source_profile_id"],
            "layout_status": layout["source_status"],
            "layout_sha256": layout["source_sha256"],
        },
        "coordinate_frame": "board",
        "target_plane_z_board_mm": layout["target_plane_z_board_mm"],
        "representative_keys": list(REPRESENTATIVE_KEYS),
        "regions": layout["representative_regions"],
        "guard_regions": layout["guard_regions"],
        "mechanics_prior": json.loads(json.dumps(MECHANICS_PRIOR)),
        "activation_rule": (
            "An activation is a rising compression crossing of activation_mm while armed; "
            "re-arming requires compression at or below release_mm."
        ),
        "accepted_rule": (
            "Exactly one geometry-derived activation, no neighbor or unsafe-center contact, "
            "no excessive travel, and final compression at or below release_mm."
        ),
        "dispositions": list(DISPOSITIONS),
    }
    profile["profile_sha256"] = _canonical_sha256(profile)
    return profile


def _intersects_region(x: float, y: float, radius: float, region: dict[str, Any]) -> bool:
    center = region["center_board_xy_mm"]
    half = region["half_extent_mm"]
    dx = max(abs(x - center[0]) - half[0], 0.0)
    dy = max(abs(y - center[1]) - half[1], 0.0)
    return dx * dx + dy * dy <= radius * radius


def _center_is_safe(x: float, y: float, region: dict[str, Any], margin: float) -> bool:
    center = region["center_board_xy_mm"]
    half = region["half_extent_mm"]
    safe_half = [half[0] - margin, half[1] - margin]
    return min(safe_half) > 0 and all(
        abs(value - midpoint) <= extent
        for value, midpoint, extent in zip((x, y), center, safe_half)
    )


def evaluate_trace(profile: dict[str, Any], samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a virtual tip trace without accepting a caller-supplied target name."""
    if profile.get("schema") != PROFILE_SCHEMA:
        raise MechanicsContractError("unexpected mechanics profile schema")
    expected_hash = profile.get("profile_sha256")
    unhashed = {key: value for key, value in profile.items() if key != "profile_sha256"}
    if expected_hash != _canonical_sha256(unhashed):
        raise MechanicsContractError("mechanics profile hash mismatch")

    trace = list(samples)
    if len(trace) < 2:
        raise MechanicsContractError("trace must contain at least two samples")
    prior = profile["mechanics_prior"]
    activation = prior["activation_mm"]["nominal"]
    release = prior["release_mm"]["nominal"]
    travel = prior["travel_mm"]["nominal"]
    stiffness = prior["stiffness_n_per_mm"]["nominal"]
    damping = prior["damping_n_s_per_mm"]["nominal"]
    radius = prior["tip_radius_mm"]
    margin = prior["center_margin_mm"]

    parsed: list[tuple[float, float, float, float]] = []
    for index, sample in enumerate(trace):
        if not isinstance(sample, dict):
            raise MechanicsContractError("trace samples must be objects")
        parsed.append(
            (
                _finite_number(sample.get("time_s"), f"sample {index} time"),
                _finite_number(sample.get("tip_x_board_mm"), f"sample {index} x"),
                _finite_number(sample.get("tip_y_board_mm"), f"sample {index} y"),
                _finite_number(sample.get("compression_mm"), f"sample {index} compression"),
            )
        )
        if parsed[-1][3] < 0:
            raise MechanicsContractError("compression cannot be negative")
        if index and parsed[-1][0] <= parsed[index - 1][0]:
            raise MechanicsContractError("trace time must increase strictly")

    resolved_key: str | None = None
    geometry_failure: str | None = None
    activation_count = 0
    armed = True
    max_compression = 0.0
    max_force = 0.0
    previous_time, _, _, previous_compression = parsed[0]
    for time_s, x, y, compression in parsed:
        max_compression = max(max_compression, compression)
        dt = time_s - previous_time
        velocity = 0.0 if dt <= 0 else (compression - previous_compression) / dt
        force = stiffness * compression + damping * max(velocity, 0.0)
        max_force = max(max_force, force)

        if compression > 0:
            contacts = sorted(
                key
                for key, region in profile["guard_regions"].items()
                if _intersects_region(x, y, radius, region)
            )
            if len(contacts) > 1:
                geometry_failure = geometry_failure or "NEIGHBORING_KEY_CONTACT"
            elif not contacts or contacts[0] not in profile["regions"]:
                geometry_failure = geometry_failure or "OFF_CENTER_PRESS"
            else:
                candidate = contacts[0]
                if resolved_key is not None and candidate != resolved_key:
                    geometry_failure = geometry_failure or "NEIGHBORING_KEY_CONTACT"
                resolved_key = resolved_key or candidate
                if not _center_is_safe(x, y, profile["regions"][candidate], margin):
                    geometry_failure = geometry_failure or "OFF_CENTER_PRESS"

        if compression <= release:
            armed = True
        if armed and previous_compression < activation <= compression:
            activation_count += 1
            armed = False
        previous_time, previous_compression = time_s, compression

    if geometry_failure:
        disposition = geometry_failure
    elif max_compression > travel:
        disposition = "EXCESSIVE_TRAVEL"
    elif activation_count == 0:
        disposition = "SHALLOW_PRESS"
    elif activation_count > 1:
        disposition = "DOUBLE_ACTIVATION"
    elif parsed[-1][3] > release:
        disposition = "INCOMPLETE_RELEASE"
    else:
        disposition = "ACCEPTED"

    result = {
        "disposition": disposition,
        "accepted": disposition == "ACCEPTED",
        "resolved_key": resolved_key,
        "activation_count": activation_count,
        "max_compression_mm": max_compression,
        "final_compression_mm": parsed[-1][3],
        "max_estimated_force_n": max_force,
        "sample_count": len(parsed),
        "profile_sha256": profile["profile_sha256"],
        "authority": dict(profile["authority"]),
    }
    result["result_sha256"] = _canonical_sha256(result)
    return result


def _trace(center: list[float], compressions: list[float], *, x_offset: float = 0.0) -> list[dict[str, float]]:
    return [
        {
            "time_s": index * 0.02,
            "tip_x_board_mm": center[0] + x_offset,
            "tip_y_board_mm": center[1],
            "compression_mm": compression,
        }
        for index, compression in enumerate(compressions)
    ]


def run_contract_campaign(layout_path: Path) -> dict[str, Any]:
    """Run deterministic positive and negative contract cases."""
    profile = build_profile(layout_path)
    regions = profile["regions"]
    cases: list[dict[str, Any]] = []

    def run(name: str, trace: list[dict[str, float]], expected: str, expected_key: str | None) -> None:
        result = evaluate_trace(profile, trace)
        cases.append(
            {
                "name": name,
                "expected_disposition": expected,
                "expected_resolved_key": expected_key,
                "passed": result["disposition"] == expected and result["resolved_key"] == expected_key,
                "result": result,
            }
        )

    nominal = [0.0, 1.0, 2.2, 3.0, 1.2, 0.0]
    for key in REPRESENTATIVE_KEYS:
        run(f"nominal_{key.lower()}", _trace(regions[key]["center_board_xy_mm"], nominal), "ACCEPTED", key)

    h_center = regions["H"]["center_board_xy_mm"]
    run("shallow_h", _trace(h_center, [0.0, 1.0, 1.9, 0.0]), "SHALLOW_PRESS", "H")
    run("off_center_h", _trace(h_center, nominal, x_offset=5.5), "OFF_CENTER_PRESS", "H")
    run("excessive_h", _trace(h_center, [0.0, 2.2, 3.6, 0.0]), "EXCESSIVE_TRAVEL", "H")
    run("double_h", _trace(h_center, [0.0, 2.2, 0.5, 2.3, 0.0]), "DOUBLE_ACTIVATION", "H")
    run("incomplete_release_h", _trace(h_center, [0.0, 2.2, 1.5]), "INCOMPLETE_RELEASE", "H")

    j_center = profile["guard_regions"]["J"]["center_board_xy_mm"]
    midpoint = [(h_center[axis] + j_center[axis]) / 2.0 for axis in range(2)]
    neighbor_trace = _trace(midpoint, nominal)
    neighbor_profile = json.loads(json.dumps(profile))
    neighbor_profile["mechanics_prior"]["tip_radius_mm"] = 3.0
    neighbor_profile.pop("profile_sha256")
    neighbor_profile["profile_sha256"] = _canonical_sha256(neighbor_profile)
    neighbor_result = evaluate_trace(neighbor_profile, neighbor_trace)
    cases.append(
        {
            "name": "neighbor_h_j",
            "expected_disposition": "NEIGHBORING_KEY_CONTACT",
            "expected_resolved_key": None,
            "passed": neighbor_result["disposition"] == "NEIGHBORING_KEY_CONTACT",
            "result": neighbor_result,
        }
    )

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS" if all(case["passed"] for case in cases) else "FAIL",
        "profile_sha256": profile["profile_sha256"],
        "case_count": len(cases),
        "passed_case_count": sum(case["passed"] for case in cases),
        "cases": cases,
        "limitations": [
            "Mechanics values are synthetic bounded priors, not measurements.",
            "The evaluator is deterministic contract logic, not native Isaac contact replay.",
            "No result grants hardware, motion, or physical keyboard authority.",
        ],
        "authority": dict(profile["authority"]),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def build_native_tip_trajectory(
    *, rest_top_z_m: float, tip_radius_m: float, dt: float
) -> list[dict[str, float]]:
    """Build a smooth settle/press/hold/retract trajectory for native replay."""
    if rest_top_z_m <= 0 or tip_radius_m <= 0 or dt <= 0:
        raise MechanicsContractError("native trajectory dimensions and time step must be positive")
    hover_z = rest_top_z_m + tip_radius_m + 0.002
    pressed_z = rest_top_z_m + tip_radius_m - NATIVE_H_PRESS_DEPTH_MM / 1000.0
    segments = ((60, hover_z, hover_z), (180, hover_z, pressed_z),
                (60, pressed_z, pressed_z), (180, pressed_z, hover_z),
                (120, hover_z, hover_z))
    result: list[dict[str, float]] = []
    step = 0
    for count, start, end in segments:
        for index in range(count):
            fraction = 1.0 if count == 1 else index / (count - 1)
            smooth = fraction * fraction * (3.0 - 2.0 * fraction)
            result.append({"step": step, "time_s": step * dt, "tip_z_m": start + (end - start) * smooth})
            step += 1
    return result


def bind_robot_tcp_contact_requirement(
    profile: dict[str, Any],
    bundle: dict[str, Any],
    *,
    key_id: str = "H",
    press_depth_mm: float = NATIVE_H_PRESS_DEPTH_MM,
) -> dict[str, Any]:
    """Bind a replay schedule endpoint to the proven key-mechanics stroke.

    This is deliberately a zero-authority planning contract.  It does not
    invent joint angles: an insufficient endpoint produces the corrected
    board-frame TCP target that the governed IK/schedule pipeline must solve
    and replay before native robot/key contact can be claimed.
    """
    if profile.get("schema") != PROFILE_SCHEMA:
        raise MechanicsContractError("unexpected mechanics profile schema")
    expected_profile_hash = profile.get("profile_sha256")
    unsigned_profile = {
        name: value for name, value in profile.items() if name != "profile_sha256"
    }
    if expected_profile_hash != _canonical_sha256(unsigned_profile):
        raise MechanicsContractError("mechanics profile hash mismatch")
    if key_id not in profile.get("regions", {}):
        raise MechanicsContractError("robot TCP binding requires a representative key")

    depth = _finite_number(press_depth_mm, "press depth")
    activation = _finite_number(
        profile["mechanics_prior"]["activation_mm"]["nominal"], "activation depth"
    )
    travel = _finite_number(
        profile["mechanics_prior"]["travel_mm"]["nominal"], "key travel"
    )
    if not activation <= depth <= travel:
        raise MechanicsContractError("press depth must be inside activation and travel bounds")

    if bundle.get("schema") not in {
        "tactevra.arm_joint_schedule_replay_bundle.v1",
        "tactevra.arm_joint_schedule_replay_bundle.v2",
    }:
        raise MechanicsContractError("unsupported replay bundle schema")
    claimed_bundle_hash = bundle.get("bundle_sha256")
    unsigned_bundle = dict(bundle)
    unsigned_bundle.pop("bundle_sha256", None)
    if claimed_bundle_hash != _canonical_sha256(unsigned_bundle):
        raise MechanicsContractError("replay bundle hash mismatch")
    if (
        bundle.get("hardware_access") is not False
        or bundle.get("physical_authority") is not False
        or bundle.get("controller_commands") != []
        or bundle.get("hardware_writes") != 0
        or bundle.get("physical_movements") != 0
    ):
        raise MechanicsContractError("replay bundle crossed the zero-authority boundary")

    endpoints = [
        item
        for item in bundle.get("samples", [])
        if item.get("target_id") == key_id
        and item.get("phase") == "CONTACT"
        and item.get("phase_endpoint") is True
    ]
    if not endpoints:
        raise MechanicsContractError("replay bundle lacks the requested contact endpoint")
    targets = [item.get("expected_tool_tip_board_mm") for item in endpoints]
    if any(not isinstance(target, list) or len(target) != 3 for target in targets):
        raise MechanicsContractError("contact endpoint lacks a board-frame TCP target")
    parsed_targets = [
        [_finite_number(value, "contact endpoint coordinate") for value in target]
        for target in targets
    ]
    if any(
        not math.isclose(value, parsed_targets[0][axis], abs_tol=1e-9)
        for target in parsed_targets[1:]
        for axis, value in enumerate(target)
    ):
        raise MechanicsContractError("repeated key contact endpoints disagree")

    center = profile["regions"][key_id]["center_board_xy_mm"]
    source_target = parsed_targets[0]
    if not all(
        math.isclose(source_target[axis], center[axis], abs_tol=1e-6)
        for axis in range(2)
    ):
        raise MechanicsContractError("contact endpoint is not centered on the selected key")
    target_plane = _finite_number(profile["target_plane_z_board_mm"], "target plane")
    scheduled_compression = max(0.0, target_plane - source_target[2])
    corrected_target = [center[0], center[1], target_plane - depth]
    sufficient = activation <= scheduled_compression <= travel
    result: dict[str, Any] = {
        "schema": TCP_BINDING_SCHEMA,
        "status": (
            "READY_FOR_DRIVE_CONTROLLED_NATIVE_REPLAY"
            if sufficient
            else "BLOCKED_CONTACT_ENDPOINT_REQUIRES_OVERTRAVEL"
        ),
        "key_id": key_id,
        "source_bundle_sha256": claimed_bundle_hash,
        "profile_sha256": expected_profile_hash,
        "source_contact_endpoint_count": len(endpoints),
        "source_contact_target_board_mm": source_target,
        "source_scheduled_compression_mm": scheduled_compression,
        "activation_depth_mm": activation,
        "travel_limit_mm": travel,
        "required_press_depth_mm": depth,
        "required_contact_target_board_mm": corrected_target,
        "joint_schedule_regeneration_required": not sufficient,
        "ik_qualification_required": True,
        "native_replay_required": True,
        "authority": dict(profile["authority"]),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "corrected_target_is_cartesian_input_not_an_ik_solution",
            "mechanics_are_synthetic_bounded_priors_not_physical_measurements",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    result["binding_sha256"] = _canonical_sha256(result)
    return result


def build_robot_tcp_cartesian_schedule_request(
    profile: dict[str, Any],
    bundle: dict[str, Any],
    *,
    key_id: str = "H",
    press_depth_mm: float = NATIVE_H_PRESS_DEPTH_MM,
) -> dict[str, Any]:
    """Regenerate Cartesian key-contact inputs without reusing stale IK.

    The retained replay bundle is useful for ordered semantics and timing, but
    its joint positions solve the old surface-only contact endpoint. This
    contract therefore copies only Cartesian samples, replaces each selected
    CONTACT endpoint with the mechanics-compatible target, and makes fresh IK
    and collision qualification mandatory.
    """
    binding = bind_robot_tcp_contact_requirement(
        profile, bundle, key_id=key_id, press_depth_mm=press_depth_mm
    )
    source_samples = bundle.get("samples")
    if not isinstance(source_samples, list) or not source_samples:
        raise MechanicsContractError("replay bundle samples are missing")

    regenerated_samples: list[dict[str, Any]] = []
    modified_sequences: list[int] = []
    for sequence, source in enumerate(source_samples):
        if not isinstance(source, dict) or source.get("sequence") != sequence:
            raise MechanicsContractError("replay bundle sample sequence is not contiguous")
        point = source.get("expected_tool_tip_board_mm")
        if not isinstance(point, list) or len(point) != 3:
            raise MechanicsContractError("replay bundle sample lacks a Cartesian target")
        target = [
            _finite_number(value, f"sample {sequence} Cartesian coordinate")
            for value in point
        ]
        if (
            source.get("target_id") == key_id
            and source.get("phase") == "CONTACT"
            and source.get("phase_endpoint") is True
        ):
            target = list(binding["required_contact_target_board_mm"])
            if target != point:
                modified_sequences.append(sequence)
        regenerated_samples.append({
            "sequence": sequence,
            "time_from_start_ns": source.get("time_from_start_ns"),
            "phase": source.get("phase"),
            "phase_endpoint": source.get("phase_endpoint"),
            "action_index": source.get("action_index"),
            "target_id": source.get("target_id"),
            "expected_tool_tip_board_mm": target,
        })

    if len(modified_sequences) != binding["source_contact_endpoint_count"]:
        raise MechanicsContractError(
            "Cartesian regeneration did not replace every selected contact endpoint"
        )
    contact_order = [
        sample["target_id"]
        for sample in regenerated_samples
        if sample["phase"] == "CONTACT" and sample["phase_endpoint"] is True
    ]
    if contact_order != bundle.get("ordered_target_ids"):
        raise MechanicsContractError("Cartesian regeneration changed target order or repetitions")

    result: dict[str, Any] = {
        "schema": TCP_CARTESIAN_SCHEDULE_SCHEMA,
        "status": "READY_FOR_IK_QUALIFICATION",
        "source_bundle_sha256": bundle["bundle_sha256"],
        "source_binding_sha256": binding["binding_sha256"],
        "profile_sha256": profile["profile_sha256"],
        "key_id": key_id,
        "sample_count": len(regenerated_samples),
        "total_time_ns": bundle.get("total_time_ns"),
        "ordered_target_ids": list(bundle.get("ordered_target_ids", [])),
        "modified_contact_sequences": modified_sequences,
        "required_contact_target_board_mm": list(
            binding["required_contact_target_board_mm"]
        ),
        "samples": regenerated_samples,
        "joint_positions_included": False,
        "source_joint_positions_reused": False,
        "ik_qualification_required": True,
        "collision_qualification_required": True,
        "native_replay_required": True,
        "authority": dict(profile["authority"]),
        "hardware_access": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "cartesian_schedule_is_not_an_ik_solution",
            "source_joint_positions_are_intentionally_excluded",
            "collision_and_native_contact_are_not_yet_qualified",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    result["request_sha256"] = _canonical_sha256(result)
    return result


def screen_robot_tcp_cartesian_schedule_ik(
    request: dict[str, Any],
    source_bundle: dict[str, Any],
    profile: dict[str, Any],
    *,
    workspace: Path,
    experiment_plan: dict[str, Any] | None = None,
    source_cartesian_request: dict[str, Any] | None = None,
    placement_tcp_candidate: dict[str, Any] | None = None,
    route_shape_plan: dict[str, Any] | None = None,
    route_shape_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Solve a regenerated Cartesian request with the canonical IK gates."""
    if request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA:
        raise MechanicsContractError("unexpected Cartesian schedule request schema")
    claimed_request_hash = request.get("request_sha256")
    unsigned_request = dict(request)
    unsigned_request.pop("request_sha256", None)
    if claimed_request_hash != _canonical_sha256(unsigned_request):
        raise MechanicsContractError("Cartesian schedule request hash mismatch")
    claimed_bundle_hash = source_bundle.get("bundle_sha256")
    unsigned_bundle = dict(source_bundle)
    unsigned_bundle.pop("bundle_sha256", None)
    if claimed_bundle_hash != _canonical_sha256(unsigned_bundle):
        raise MechanicsContractError("IK source bundle hash mismatch")
    if request.get("source_bundle_sha256") != claimed_bundle_hash:
        raise MechanicsContractError("Cartesian request and IK source bundle differ")
    governed_source_request = build_robot_tcp_cartesian_schedule_request(
        profile, source_bundle
    )
    if (experiment_plan is None) != (source_cartesian_request is None):
        raise MechanicsContractError(
            "route-variant IK requires both its experiment plan and source request"
        )
    route_variant = (
        experiment_plan is not None and source_cartesian_request is not None
    )
    if (route_shape_plan is None) != (route_shape_candidate is None):
        raise MechanicsContractError(
            "route-shape IK requires both its plan and candidate"
        )
    route_shape = route_shape_plan is not None and route_shape_candidate is not None
    if route_shape and not route_variant:
        raise MechanicsContractError("route-shape IK requires its governed route variant")
    if experiment_plan is not None and source_cartesian_request is not None:
        if (
            source_cartesian_request.get("request_sha256")
            != governed_source_request.get("request_sha256")
        ):
            raise MechanicsContractError(
                "route-variant source differs from governed mechanics regeneration"
            )
        expected_request = build_physical_blocker_route_variant(
            source_cartesian_request, experiment_plan
        )
    else:
        expected_request = governed_source_request
    if route_shape and route_shape_plan is not None and route_shape_candidate is not None:
        candidate_id = route_shape_candidate.get("candidate_id")
        expected_request = materialize_route_shape_candidate(
            route_shape_plan, expected_request, candidate_id
        )
        if expected_request.get("route_shape_candidate") != route_shape_candidate:
            raise MechanicsContractError("route-shape candidate differs from its plan")
    if expected_request.get("request_sha256") != claimed_request_hash:
        raise MechanicsContractError(
            "Cartesian request differs from its governed mechanics regeneration"
        )
    for document, label in ((request, "request"), (source_bundle, "source bundle")):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed the zero-authority boundary")

    samples = request.get("samples")
    source_samples = source_bundle.get("samples")
    if (
        not isinstance(samples, list)
        or not isinstance(source_samples, list)
        or not samples
        or len(samples) != len(source_samples)
        or len(samples) > 256
    ):
        raise MechanicsContractError("IK sample count is absent, crossed, or out of bounds")
    modified = request.get("modified_contact_sequences")
    if not isinstance(modified, list) or not modified:
        raise MechanicsContractError("IK request lacks modified contact sequences")
    modified_set = set(modified)
    if len(modified_set) != len(modified):
        raise MechanicsContractError("modified contact sequences are not unique")
    modified_transit = request.get("modified_transit_sequences", [])
    if not isinstance(modified_transit, list):
        raise MechanicsContractError("modified transit sequences are invalid")
    modified_transit_set = set(modified_transit)
    if len(modified_transit_set) != len(modified_transit):
        raise MechanicsContractError("modified transit sequences are not unique")
    if route_variant != bool(modified_transit):
        raise MechanicsContractError("route-variant transit selection is absent or unexpected")
    route_shape_domain = request.get("route_shape_domain_sequences", [])
    if not isinstance(route_shape_domain, list):
        raise MechanicsContractError("route-shape domain is invalid")
    route_shape_domain_set = set(route_shape_domain)
    if len(route_shape_domain_set) != len(route_shape_domain):
        raise MechanicsContractError("route-shape domain sequences are not unique")
    if route_shape != bool(route_shape_domain):
        raise MechanicsContractError("route-shape domain is absent or unexpected")
    changed_set = modified_set | modified_transit_set | route_shape_domain_set
    for sequence, (sample, source) in enumerate(zip(samples, source_samples)):
        if sample.get("sequence") != sequence or source.get("sequence") != sequence:
            raise MechanicsContractError("IK sample sequence is not contiguous")
        for field in (
            "time_from_start_ns", "phase", "phase_endpoint", "action_index", "target_id"
        ):
            if sample.get(field) != source.get(field):
                raise MechanicsContractError("Cartesian request changed source semantics")
        if sequence not in changed_set and (
            sample.get("expected_tool_tip_board_mm")
            != source.get("expected_tool_tip_board_mm")
        ):
            raise MechanicsContractError("Cartesian request changed an unselected endpoint")
        if sequence in modified_set and (
            sample.get("expected_tool_tip_board_mm")
            != request.get("required_contact_target_board_mm")
        ):
            raise MechanicsContractError("modified contact target differs from the request")
        if sequence in route_shape_domain_set:
            if sample.get("phase") != "TRANSIT" or sample.get("phase_endpoint") is not False:
                raise MechanicsContractError("route-shape domain contains a non-transit sample")
        elif sequence in modified_transit_set:
            source_point = source.get("expected_tool_tip_board_mm")
            point = sample.get("expected_tool_tip_board_mm")
            if (
                not isinstance(source_point, list)
                or len(source_point) != 3
                or not isinstance(point, list)
                or len(point) != 3
                or point[:2] != source_point[:2]
                or point[2] != request.get("proposed_transit_z_mm")
                or sample.get("phase") != "TRANSIT"
                or sample.get("phase_endpoint") is not False
            ):
                raise MechanicsContractError("modified transit sample changed beyond z")

    try:
        from rocell.application._pinned_model import load_pinned_urdf
        from rocell.application.context import load_simulation_context
        from rocell.application.trajectory_simulation import (
            CartesianRouteWaypoint,
            TrajectorySimulationPolicy,
            evaluate_joint_trajectory_solution,
        )
        from rocell.application.typing_trajectory_ik_screen_v1 import (
            canonicalize_typing_ik_evidence_v1,
        )
        from rocell.geometry import (
            JointPosition,
            Point3Mm,
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
        from rocell.motion import MotionPhase
        from rocell.simulation.virtual_profile import load_virtual_commissioning_profile
    except ImportError as exc:
        raise MechanicsContractError(
            "canonical IK runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    root = workspace.resolve(strict=True)
    context = load_simulation_context(
        root, root / "software/config/system_manifest.json"
    )
    virtual_profile = load_virtual_commissioning_profile(context)
    expected_virtual_hash = source_bundle.get("source", {}).get(
        "virtual_profile_sha256"
    )
    if virtual_profile.source_sha256 != expected_virtual_hash:
        raise MechanicsContractError("virtual commissioning profile lineage changed")
    tool_length_mm = float(virtual_profile.study_input.keyboard_tool_length_mm)
    board_t_world = virtual_profile.study_input.board_T_vendor_world
    if placement_tcp_candidate is not None:
        candidate_id = placement_tcp_candidate.get("candidate_id")
        matrix = placement_tcp_candidate.get("robot_placement_matrix_row_major")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id.startswith("placement-tcp-")
            or not isinstance(matrix, list)
            or len(matrix) != 16
        ):
            raise MechanicsContractError("placement/TCP candidate is invalid")
        matrix = [
            _finite_number(value, "placement/TCP candidate matrix")
            for value in matrix
        ]
        expected_matrix = [
            matrix[0], matrix[1], matrix[2], matrix[3],
            matrix[4], matrix[5], matrix[6], matrix[7],
            matrix[8], matrix[9], matrix[10], matrix[11],
            0.0, 0.0, 0.0, 1.0,
        ]
        if matrix != expected_matrix:
            raise MechanicsContractError(
                "placement/TCP candidate matrix is not a rigid affine matrix"
            )
        try:
            board_t_world = RigidTransform(
                "board",
                "base_link",
                Rotation3(tuple(
                    matrix[index]
                    for index in (0, 1, 2, 4, 5, 6, 8, 9, 10)
                )),
                Vec3(matrix[3], matrix[7], matrix[11]),
            )
        except (TypeError, ValueError) as exc:
            raise MechanicsContractError(
                "placement/TCP candidate matrix is not a rigid transform"
            ) from exc
        tool_length_mm = _finite_number(
            placement_tcp_candidate.get("keyboard_tcp_length_mm"),
            "placement/TCP keyboard tool length",
        )
        if tool_length_mm <= 0.0:
            raise MechanicsContractError(
                "placement/TCP keyboard tool length must be positive"
            )
    scenario = context.scenario
    model = load_pinned_urdf(scenario.model_path, scenario.model_sha256).model
    if placement_tcp_candidate is not None:
        fixed = model.joint("world_to_base_link")
        if (
            fixed.joint_type != "fixed"
            or fixed.parent_link != model.root_link
            or fixed.child_link != "base_link"
        ):
            raise MechanicsContractError(
                "pinned vendor world-to-base transform changed"
            )
        # The candidate matrix is B_T_Ru while the IK model is rooted at Wv.
        # Derive B_T_Wv exactly as the governed virtual-profile loader does.
        board_t_world = board_t_world.compose(fixed.transform_at(None).inverse())
    initial_seed = source_samples[0].get("joint_positions_rad")
    if not isinstance(initial_seed, dict) or tuple(initial_seed) != ARM_JOINT_NAMES:
        raise MechanicsContractError("source bundle lacks the canonical initial joint seed")
    previous = {
        name: _finite_number(initial_seed[name], f"initial seed {name}")
        for name in ARM_JOINT_NAMES
    }
    bounds = scenario.controller_joint_intersection_rad
    solver = RoArmM3NumericalIk(
        model=model,
        board_T_world=board_t_world,
        hand_tcp_to_tip_z_mm=-tool_length_mm,
        fixed_gripper_position=scenario.fixed_gripper_position,
        ready_arm_joint_positions={
            name: JointPosition.radians(value) for name, value in previous.items()
        },
        gripper_bounds_rad=scenario.controller_gripper_intersection_rad,
        options=IkOptions(
            max_attempts=scenario.ik_policy.max_attempts,
            max_iterations_per_attempt=scenario.ik_policy.max_iterations_per_attempt,
        ),
        joint_bounds_rad=bounds,
    )
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=30.0,
        maximum_joint_step_rad=0.35,
        minimum_normalized_arm_joint_margin=0.01,
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=256,
        maximum_total_ik_solves=256,
        maximum_route_targets=len(request["ordered_target_ids"]),
    )
    results: list[dict[str, Any]] = []
    previous_point = None
    for sample in samples:
        point = Point3Mm("board", *sample["expected_tool_tip_board_mm"])
        distance = (
            0.0
            if previous_point is None
            else math.dist(
                (previous_point.x, previous_point.y, previous_point.z),
                (point.x, point.y, point.z),
            )
        )
        waypoint = CartesianRouteWaypoint(
            sequence=sample["sequence"],
            phase=MotionPhase(sample["phase"]),
            action_index=sample["action_index"],
            semantic_target=sample["target_id"],
            point_board=point,
            distance_from_previous_mm=distance,
            source_geometric_sequence=sample["sequence"],
            source_check_id=claimed_request_hash,
            source_path_check_passed=True,
            inherited_collision_ids=(),
            phase_endpoint=sample["phase_endpoint"],
        )
        solved = solver.solve(
            BoardToolTipTarget(point),
            seed_joint_positions=({
                name: JointPosition.radians(value)
                for name, value in previous.items()
            },),
        )
        evaluated = evaluate_joint_trajectory_solution(
            waypoint, solved, solver, bounds, previous, policy
        )
        canonical = canonicalize_typing_ik_evidence_v1(evaluated.to_dict())
        results.append(canonical)
        if not evaluated.accepted:
            break
        previous = dict(evaluated.solution_arm_joint_positions_rad)
        previous_point = point

    all_accepted = len(results) == len(samples) and all(
        item["accepted"] for item in results
    )
    accepted = [item for item in results if item["accepted"]]
    result: dict[str, Any] = {
        "schema": TCP_IK_SCREEN_SCHEMA,
        "status": (
            "READY_FOR_COLLISION_QUALIFICATION"
            if all_accepted
            else "BLOCKED_CANONICAL_IK_OR_CONTINUITY"
        ),
        "source_request_sha256": claimed_request_hash,
        "source_bundle_sha256": claimed_bundle_hash,
        "virtual_profile_sha256": virtual_profile.source_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": scenario.model_sha256,
        "tool_length_mm": tool_length_mm,
        "initial_seed_source": "SOURCE_BUNDLE_SAMPLE_0_ONLY",
        "initial_seed_joint_positions_rad": {
            name: float(initial_seed[name]) for name in ARM_JOINT_NAMES
        },
        "policy": policy.to_dict(),
        "sample_count": len(samples),
        "evaluated_sample_count": len(results),
        "ik_all_samples_accepted": all_accepted,
        "joint_results": results,
        "modified_contact_results": [
            results[index] for index in modified if index < len(results)
        ],
        "modified_transit_results": [
            results[index] for index in modified_transit if index < len(results)
        ],
        "metrics": {
            "maximum_position_error_mm": max(
                (item["position_error_mm"] for item in accepted), default=None
            ),
            "minimum_normalized_arm_joint_margin": min(
                (
                    item["minimum_normalized_arm_joint_margin"]
                    for item in accepted
                ),
                default=None,
            ),
            "maximum_adjacent_joint_delta_rad": max(
                (item["maximum_joint_delta_rad"] for item in accepted), default=None
            ),
        },
        "collision_screening_executed": False,
        "continuous_collision_proven": False,
        "next_required_stage": (
            "SCREEN_EXACT_JOINT_RESULTS_AGAINST_COLLISION_GEOMETRY"
            if all_accepted
            else "CORRECT_IK_COMPATIBILITY_OR_ROUTE_CONTINUITY"
        ),
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "virtual_profile_is_an_unmeasured_simulation_only_overlay",
            "collision_and_native_contact_are_not_yet_qualified",
            "initial_seed_is_retained_source_evidence_not_controller_feedback",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    if route_variant:
        result.update({
            "source_cartesian_request_sha256": request[
                "source_cartesian_request_sha256"
            ],
            "source_physical_blocker_experiment_plan_sha256": request[
                "source_physical_blocker_experiment_plan_sha256"
            ],
            "route_variant_classification": request[
                "route_variant_classification"
            ],
        })
    if placement_tcp_candidate is not None:
        result.update({
            "placement_tcp_candidate_id": placement_tcp_candidate["candidate_id"],
            "robot_placement_matrix_row_major": list(
                placement_tcp_candidate["robot_placement_matrix_row_major"]
            ),
            "placement_tcp_candidate_classification": placement_tcp_candidate[
                "candidate_classification"
            ],
        })
    if route_shape and route_shape_plan is not None and route_shape_candidate is not None:
        result.update({
            "source_route_shape_campaign_plan_sha256": route_shape_plan[
                "plan_sha256"
            ],
            "route_shape_candidate_id": route_shape_candidate["candidate_id"],
            "route_shape_candidate": route_shape_candidate,
            "route_shape_domain_sequences": list(
                request["route_shape_domain_sequences"]
            ),
        })
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def _placement_tcp_candidate_rank_key(
    result: dict[str, Any],
) -> tuple[int, int, float, float, str]:
    """Return the exact predeclared ARM-199 deterministic ranking key."""
    metrics = result["ik_metrics"]
    return (
        int(result["physical_blocker_pair_count"]),
        int(result["blocked_sample_count"]),
        -float(metrics["minimum_normalized_arm_joint_margin"]),
        float(metrics["maximum_position_error_mm"]),
        str(result["candidate_id"]),
    )


def _route_shape_candidate_rank_key(
    result: dict[str, Any],
) -> tuple[int, int, int, float, float, str]:
    """Return the exact predeclared ARM-200 deterministic ranking key."""
    metrics = result["ik_metrics"]
    return (
        int(result["transit_physical_blocker_pair_count"]),
        int(result["transit_blocked_sample_count"]),
        int(result["endpoint_physical_blocker_pair_count"]),
        -float(metrics["minimum_normalized_arm_joint_margin"]),
        float(metrics["maximum_position_error_mm"]),
        str(result["candidate_id"]),
    )


def execute_placement_tcp_search(
    search_plan: dict[str, Any],
    route_variant_request: dict[str, Any],
    source_bundle: dict[str, Any],
    profile: dict[str, Any],
    experiment_plan: dict[str, Any],
    source_cartesian_request: dict[str, Any],
    collision_candidate: dict[str, Any],
    collision_pair_policy: dict[str, Any],
    station_route_predicate: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    """Run bounded canonical IK and exact OBB screening for every plan candidate.

    This is an exploratory, zero-authority screen.  It deliberately does not
    install the digital collision candidate, prove continuous clearance, run
    native Isaac, or create any controller command.
    """
    claimed_plan_hash = search_plan.get("plan_sha256")
    unsigned_plan = dict(search_plan)
    unsigned_plan.pop("plan_sha256", None)
    if (
        search_plan.get("schema") != PLACEMENT_TCP_SEARCH_PLAN_SCHEMA
        or search_plan.get("status")
        != "READY_FOR_ZERO_AUTHORITY_PLACEMENT_TCP_SCREENING"
        or claimed_plan_hash != _canonical_sha256(unsigned_plan)
    ):
        raise MechanicsContractError("placement/TCP search plan is invalid")
    candidates = search_plan.get("candidates")
    if (
        not isinstance(candidates, list)
        or not candidates
        or len(candidates) != search_plan.get("candidate_count")
        or len(candidates) > 128
    ):
        raise MechanicsContractError("placement/TCP candidate collection is invalid")
    if len({item.get("candidate_id") for item in candidates}) != len(candidates):
        raise MechanicsContractError("placement/TCP candidate ids are not unique")

    candidate_hash = collision_candidate.get("candidate_sha256")
    candidate_unsigned = dict(collision_candidate)
    candidate_unsigned.pop("candidate_sha256", None)
    policy_hash = collision_pair_policy.get("policy_sha256")
    policy_unsigned = dict(collision_pair_policy)
    policy_unsigned.pop("policy_sha256", None)
    predicate_hash = station_route_predicate.get("predicate_sha256")
    predicate_unsigned = dict(station_route_predicate)
    predicate_unsigned.pop("predicate_sha256", None)
    if (
        candidate_hash != _canonical_sha256(candidate_unsigned)
        or policy_hash != _canonical_sha256(policy_unsigned)
        or predicate_hash != _canonical_sha256(predicate_unsigned)
        or candidate_hash != search_plan.get("source_collision_candidate_sha256")
        or policy_hash != search_plan.get("source_collision_pair_policy_sha256")
        or predicate_hash != search_plan.get("source_station_route_predicate_sha256")
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
        or collision_pair_policy.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY"
        or station_route_predicate.get("status") != "PASS"
    ):
        raise MechanicsContractError("placement/TCP collision lineage changed")
    for document, label in (
        (search_plan, "search plan"),
        (route_variant_request, "route variant"),
        (experiment_plan, "experiment plan"),
        (collision_candidate, "collision candidate"),
        (collision_pair_policy, "collision pair policy"),
        (station_route_predicate, "station route predicate"),
    ):
        if (
            document.get("physical_authority", False) is not False
            or document.get("hardware_access", False) is not False
            or document.get("controller_commands", []) != []
            or document.get("hardware_writes", 0) != 0
            or document.get("hardware_write_count", 0) != 0
            or document.get("physical_movements", 0) != 0
            or document.get("physical_movement_count", 0) != 0
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    try:
        from rocell.application._pinned_model import load_pinned_urdf
        from rocell.application.context import load_simulation_context
        from rocell.application.trajectory_simulation import TrajectorySimulationError
        from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
        from rocell.kinematics import ARM_JOINT_NAMES
        from rocell.simulation.collision import (
            CollisionBindingMode,
            CollisionBody,
            CollisionBodyRequirement,
            CollisionBodyRole,
            CollisionClearanceEvidenceState,
            CollisionClearancePolicy,
            CollisionEvaluationPolicy,
            CollisionEvaluationStatus,
            CollisionEvidenceState,
            CollisionExclusionEvidenceState,
            CollisionExclusionScope,
            CollisionGeometryContract,
            CollisionPairExclusion,
            CollisionPose,
            OrientedBoxMm,
            evaluate_collision_pose,
        )
    except ImportError as exc:
        raise MechanicsContractError(
            "offline collision runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    physical_ids = station_route_predicate.get("physical_workcell_body_ids")
    if not isinstance(physical_ids, list) or not physical_ids:
        raise MechanicsContractError("station predicate lacks physical workcell ids")
    physical_id_set = set(physical_ids)
    robot_documents = collision_candidate.get("robot_bodies")
    workcell_documents = collision_candidate.get("workcell_bodies")
    if not isinstance(robot_documents, list) or not isinstance(workcell_documents, list):
        raise MechanicsContractError("collision candidate body collections are invalid")
    selected_documents = [
        *robot_documents,
        *(item for item in workcell_documents if item.get("body_id") in physical_id_set),
    ]
    if {item.get("body_id") for item in selected_documents if item in workcell_documents} != physical_id_set:
        raise MechanicsContractError("physical workcell body coverage changed")

    def primitive(document: dict[str, Any]) -> OrientedBoxMm:
        if document.get("kind") != "oriented_box":
            raise MechanicsContractError("ARM-199 requires oriented-box primitives")
        return OrientedBoxMm(
            Vec3.from_iterable(document["center_mm"]),
            Vec3.from_iterable(document["half_extents_mm"]),
            Rotation3(tuple(document["rotation_row_major"])),
        )

    requirements = []
    bodies = []
    for document in selected_documents:
        is_static = document["body_id"] in physical_id_set
        role = (
            CollisionBodyRole.STATIC_ENVIRONMENT
            if is_static else CollisionBodyRole.ROBOT_LINK
        )
        mode = (
            CollisionBindingMode.STATIC_ROOT
            if is_static else CollisionBindingMode.RIGID_FRAME
        )
        requirements.append(CollisionBodyRequirement(
            document["body_id"], document["parent_frame"], role, mode,
            "ARM-199 exact exploratory full-link OBB screen",
        ))
        bodies.append(CollisionBody(
            document["body_id"], document["parent_frame"], role,
            CollisionEvidenceState.PINNED_DIGITAL,
            tuple(primitive(item) for item in document["primitives"]),
            mode,
            f"collision candidate {candidate_hash}",
        ))
    exclusions = tuple(
        CollisionPairExclusion(
            pair[0], pair[1],
            CollisionExclusionScope.URDF_ADJACENT_DIAGNOSTIC,
            CollisionExclusionEvidenceState.PINNED_KINEMATIC_DIAGNOSTIC,
            "accepted directly connected diagnostic pair",
            f"collision pair policy {policy_hash}",
        )
        for pair in collision_pair_policy.get("accepted_exclusion_pairs", [])
    )
    contract = CollisionGeometryContract(
        "TACTEVRA-ARM199-EXPLORATORY-OBB-V1", "board",
        tuple(requirements), tuple(bodies), exclusions,
    )
    # The primitive kernel requires a positive policy.  One picometre is used
    # only to make touching count as blocked without claiming measured clearance.
    clearance = CollisionClearancePolicy(
        1e-9, 0.0, 0.0, CollisionClearanceEvidenceState.PINNED_DIGITAL,
        "ARM-199 numerical touching threshold; not measured clearance",
    )
    evaluation_policy = CollisionEvaluationPolicy(clearance_policy=clearance)
    root = workspace.resolve(strict=True)
    context = load_simulation_context(root, root / "software/config/system_manifest.json")
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    remaining = set(model.movable_joint_names) - set(ARM_JOINT_NAMES)
    if len(remaining) != 1:
        raise MechanicsContractError("pinned robot gripper joint topology changed")
    gripper_joint = next(iter(remaining))

    outcomes: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            ik = screen_robot_tcp_cartesian_schedule_ik(
                route_variant_request,
                source_bundle,
                profile,
                workspace=root,
                experiment_plan=experiment_plan,
                source_cartesian_request=source_cartesian_request,
                placement_tcp_candidate=candidate,
            )
        except TrajectorySimulationError as exc:
            outcomes.append({
                "candidate_id": candidate["candidate_id"],
                "candidate_classification": candidate["candidate_classification"],
                "candidate": candidate,
                "ik_receipt_sha256": None,
                "ik_status": "BLOCKED_CANONICAL_IK_OR_CONTINUITY",
                "ik_all_samples_accepted": False,
                "evaluated_sample_count": 0,
                "ik_metrics": {
                    "maximum_position_error_mm": None,
                    "minimum_normalized_arm_joint_margin": None,
                    "maximum_adjacent_joint_delta_rad": None,
                },
                "collision_screening_executed": False,
                "rejection_reasons": [
                    "CANONICAL_IK_EVIDENCE_SHAPE_REJECTED"
                ],
                "rejection_detail": str(exc),
            })
            continue
        outcome: dict[str, Any] = {
            "candidate_id": candidate["candidate_id"],
            "candidate_classification": candidate["candidate_classification"],
            "candidate": candidate,
            "ik_receipt_sha256": ik["receipt_sha256"],
            "ik_status": ik["status"],
            "ik_all_samples_accepted": ik["ik_all_samples_accepted"],
            "evaluated_sample_count": ik["evaluated_sample_count"],
            "ik_metrics": ik["metrics"],
            "collision_screening_executed": False,
            "rejection_reasons": [],
        }
        if not ik["ik_all_samples_accepted"]:
            outcome["rejection_reasons"] = ["CANONICAL_IK_OR_CONTINUITY_REJECTED"]
            outcomes.append(outcome)
            continue

        matrix = candidate["robot_placement_matrix_row_major"]
        board_t_base = RigidTransform(
            "board", "base_link",
            Rotation3(tuple(
                matrix[index] for index in (0, 1, 2, 4, 5, 6, 8, 9, 10)
            )),
            Vec3(matrix[3], matrix[7], matrix[11]),
        )
        fixed = model.joint("world_to_base_link")
        board_t_world = board_t_base.compose(fixed.transform_at(None).inverse())
        blocked_samples = 0
        physical_pairs: set[tuple[str, str]] = set()
        all_pairs: set[tuple[str, str]] = set()
        sample_reports: list[dict[str, Any]] = []
        for index, joint_result in enumerate(ik["joint_results"]):
            positions = {
                name: JointPosition.radians(
                    joint_result["solution_arm_joint_positions_rad"][name]
                ) for name in ARM_JOINT_NAMES
            }
            positions[gripper_joint] = context.scenario.fixed_gripper_position
            base_transforms = model.forward_kinematics(positions)
            board_transforms = {
                frame: board_t_world.compose(transform)
                for frame, transform in base_transforms.items()
            }
            pose = CollisionPose(
                f"{candidate['candidate_id']}-sample-{index:04d}",
                "board",
                {
                    body["parent_frame"]: board_transforms[body["parent_frame"]]
                    for body in robot_documents
                },
            )
            evaluated = evaluate_collision_pose(contract, pose, evaluation_policy)
            pairs = {
                tuple(sorted((item.first_body_id, item.second_body_id)))
                for item in evaluated.collisions
            }
            sample_physical = {
                pair for pair in pairs if any(item in physical_id_set for item in pair)
            }
            all_pairs.update(pairs)
            physical_pairs.update(sample_physical)
            if evaluated.status is CollisionEvaluationStatus.COLLISION_DETECTED:
                blocked_samples += 1
            sample_reports.append({
                "sample_sequence": index,
                "collision_report_sha256": evaluated.report_hash,
                "status": evaluated.status.value,
                "collision_pairs": [list(pair) for pair in sorted(pairs)],
                "physical_blocker_pairs": [
                    list(pair) for pair in sorted(sample_physical)
                ],
            })
        outcome.update({
            "collision_screening_executed": True,
            "collision_contract_sha256": contract.content_hash,
            "collision_policy_sha256": evaluation_policy.content_hash,
            "blocked_sample_count": blocked_samples,
            "physical_blocker_pair_count": len(physical_pairs),
            "physical_blocker_pairs": [list(pair) for pair in sorted(physical_pairs)],
            "all_collision_pair_count": len(all_pairs),
            "all_collision_pairs": [list(pair) for pair in sorted(all_pairs)],
            "sample_reports": sample_reports,
            "rejection_reasons": (
                ["DISCRETE_FULL_LINK_COLLISION_BLOCKED"]
                if blocked_samples else []
            ),
        })
        outcomes.append(outcome)

    ranked = sorted(
        (item for item in outcomes if item["collision_screening_executed"]),
        key=_placement_tcp_candidate_rank_key,
    )
    shortlist_count = min(
        int(search_plan["maximum_native_shortlist_count"]), len(ranked)
    )
    shortlist = [item["candidate_id"] for item in ranked[:shortlist_count]]
    result: dict[str, Any] = {
        "schema": PLACEMENT_TCP_SEARCH_SCREEN_SCHEMA,
        "status": (
            "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY"
            if shortlist else "BLOCKED_NO_IK_ACCEPTED_CANDIDATES"
        ),
        "source_search_plan_sha256": claimed_plan_hash,
        "source_route_variant_request_sha256": route_variant_request[
            "request_sha256"
        ],
        "source_collision_candidate_sha256": candidate_hash,
        "source_collision_pair_policy_sha256": policy_hash,
        "source_station_route_predicate_sha256": predicate_hash,
        "candidate_count": len(candidates),
        "ik_accepted_candidate_count": len(ranked),
        "ik_rejected_candidate_count": len(candidates) - len(ranked),
        "collision_screened_candidate_count": len(ranked),
        "outcomes": outcomes,
        "ranked_candidate_ids": [item["candidate_id"] for item in ranked],
        "native_shortlist_candidate_ids": shortlist,
        "native_shortlist_count": len(shortlist),
        "maximum_native_shortlist_count": search_plan[
            "maximum_native_shortlist_count"
        ],
        "ranking_order": list(search_plan["ranking_order"]),
        "exact_obb_collision_kernel_used": True,
        "collision_geometry_changed": False,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "native_isaac_replay_executed": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "exploratory_uninstalled_collision_candidate_only",
            "discrete_samples_do_not_prove_continuous_clearance",
            "one_picometre_touching_threshold_is_not_measured_clearance",
            "native_isaac_replay_is_limited_to_the_retained_shortlist",
        ],
    }
    result["screen_sha256"] = _canonical_sha256(result)
    return result


def materialize_placement_tcp_native_shortlist(
    search_plan: dict[str, Any],
    search_screen: dict[str, Any],
    route_variant_request: dict[str, Any],
    source_bundle: dict[str, Any],
    profile: dict[str, Any],
    experiment_plan: dict[str, Any],
    source_cartesian_request: dict[str, Any],
    collision_candidate: dict[str, Any],
    collision_pair_policy: dict[str, Any],
    toolchain_lock: dict[str, Any],
    *,
    workspace: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Reproduce and retain exact native inputs for the selected shortlist."""
    plan_hash = search_plan.get("plan_sha256")
    unsigned_plan = dict(search_plan)
    unsigned_plan.pop("plan_sha256", None)
    screen_hash = search_screen.get("screen_sha256")
    unsigned_screen = dict(search_screen)
    unsigned_screen.pop("screen_sha256", None)
    if (
        plan_hash != _canonical_sha256(unsigned_plan)
        or screen_hash != _canonical_sha256(unsigned_screen)
        or search_screen.get("schema") != PLACEMENT_TCP_SEARCH_SCREEN_SCHEMA
        or search_screen.get("source_search_plan_sha256") != plan_hash
        or search_screen.get("status")
        != "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY"
    ):
        raise MechanicsContractError("placement/TCP shortlist lineage is invalid")
    shortlist = search_screen.get("native_shortlist_candidate_ids")
    if (
        not isinstance(shortlist, list)
        or not shortlist
        or len(shortlist) > search_plan.get("maximum_native_shortlist_count", 0)
        or len(shortlist) != len(set(shortlist))
    ):
        raise MechanicsContractError("placement/TCP native shortlist is invalid")
    candidates = {
        item["candidate_id"]: item for item in search_plan.get("candidates", [])
    }
    outcomes = {
        item["candidate_id"]: item for item in search_screen.get("outcomes", [])
    }
    if any(item not in candidates or item not in outcomes for item in shortlist):
        raise MechanicsContractError("shortlist references an unknown candidate")

    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for rank, candidate_id in enumerate(shortlist, start=1):
        candidate = candidates[candidate_id]
        expected = outcomes[candidate_id]
        ik = screen_robot_tcp_cartesian_schedule_ik(
            route_variant_request,
            source_bundle,
            profile,
            workspace=workspace,
            experiment_plan=experiment_plan,
            source_cartesian_request=source_cartesian_request,
            placement_tcp_candidate=candidate,
        )
        if (
            ik.get("receipt_sha256") != expected.get("ik_receipt_sha256")
            or ik.get("ik_all_samples_accepted") is not True
        ):
            raise MechanicsContractError(
                f"shortlist candidate {candidate_id} did not reproduce exact IK"
            )
        raw_request = build_robot_tcp_collision_replay_request(
            ik, collision_candidate, toolchain_lock
        )
        bound_request = bind_collision_pair_policy_request(
            raw_request, collision_pair_policy
        )
        candidate_dir = root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        documents = (
            ("ik_receipt.json", ik, "receipt_sha256"),
            ("collision_request.json", raw_request, "request_sha256"),
            (
                "policy_bound_collision_request.json",
                bound_request,
                "request_sha256",
            ),
        )
        paths: dict[str, str] = {}
        hashes: dict[str, str] = {}
        for filename, document, hash_field in documents:
            path = candidate_dir / filename
            path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            paths[filename] = str(path)
            hashes[filename] = document[hash_field]
        entries.append({
            "rank": rank,
            "candidate_id": candidate_id,
            "candidate": candidate,
            "paths": paths,
            "document_hashes": hashes,
        })
    manifest: dict[str, Any] = {
        "schema": "tactevra.isaac_lm1_placement_tcp_native_shortlist.v1",
        "status": "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY",
        "source_search_plan_sha256": plan_hash,
        "source_search_screen_sha256": screen_hash,
        "shortlist_count": len(entries),
        "entries": entries,
        "native_isaac_replay_executed": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def materialize_route_shape_native_shortlist(
    campaign_plan: dict[str, Any],
    campaign_screen: dict[str, Any],
    candidate_evidence: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    collision_candidate: dict[str, Any],
    collision_pair_policy: dict[str, Any],
    toolchain_lock: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Retain exact native replay inputs for the ranked ARM-201 shortlist."""

    def verified(
        document: dict[str, Any], digest_field: str, label: str
    ) -> str:
        claimed = document.get(digest_field)
        unsigned = dict(document)
        unsigned.pop(digest_field, None)
        if not isinstance(claimed, str) or claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} digest is invalid")
        return claimed

    plan_hash = verified(campaign_plan, "plan_sha256", "route-shape plan")
    screen_hash = verified(
        campaign_screen, "screen_sha256", "route-shape screen"
    )
    if (
        campaign_plan.get("schema") != ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA
        or campaign_screen.get("schema") != ROUTE_SHAPE_CAMPAIGN_SCREEN_SCHEMA
        or campaign_screen.get("source_campaign_plan_sha256") != plan_hash
        or campaign_screen.get("status")
        != "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY"
    ):
        raise MechanicsContractError("route-shape shortlist lineage is invalid")
    for document, label in (
        (campaign_plan, "route-shape plan"),
        (campaign_screen, "route-shape screen"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("physical_authority") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
            or document.get("gate_promotions") != []
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")
    shortlist = campaign_screen.get("native_shortlist_candidate_ids")
    if (
        not isinstance(shortlist, list)
        or not shortlist
        or len(shortlist) > campaign_plan.get("maximum_native_shortlist_count", 0)
        or len(shortlist) != len(set(shortlist))
    ):
        raise MechanicsContractError("route-shape native shortlist is invalid")
    candidates = {
        item["candidate_id"]: item
        for item in campaign_plan.get("candidates", [])
    }
    outcomes = {
        item["candidate_id"]: item
        for item in campaign_screen.get("outcomes", [])
    }
    if any(
        candidate_id not in candidates
        or candidate_id not in outcomes
        or candidate_id not in candidate_evidence
        for candidate_id in shortlist
    ):
        raise MechanicsContractError("shortlist references an unknown candidate")

    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for rank, candidate_id in enumerate(shortlist, start=1):
        request, ik = candidate_evidence[candidate_id]
        outcome = outcomes[candidate_id]
        if (
            request.get("request_sha256") != outcome.get("request_sha256")
            or ik.get("receipt_sha256") != outcome.get("ik_receipt_sha256")
            or ik.get("ik_all_samples_accepted") is not True
            or ik.get("route_shape_candidate_id") != candidate_id
        ):
            raise MechanicsContractError(
                f"shortlist candidate {candidate_id} evidence changed"
            )
        verified(request, "request_sha256", f"{candidate_id} request")
        verified(ik, "receipt_sha256", f"{candidate_id} IK receipt")
        raw_request = build_robot_tcp_collision_replay_request(
            ik, collision_candidate, toolchain_lock
        )
        bound_request = bind_collision_pair_policy_request(
            raw_request, collision_pair_policy
        )
        candidate_dir = root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        documents = (
            ("cartesian_request.json", request, "request_sha256"),
            ("ik_receipt.json", ik, "receipt_sha256"),
            ("collision_request.json", raw_request, "request_sha256"),
            (
                "policy_bound_collision_request.json",
                bound_request,
                "request_sha256",
            ),
        )
        paths: dict[str, str] = {}
        hashes: dict[str, str] = {}
        for filename, document, hash_field in documents:
            path = candidate_dir / filename
            path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            paths[filename] = str(path)
            hashes[filename] = document[hash_field]
        entries.append({
            "rank": rank,
            "candidate_id": candidate_id,
            "candidate": candidates[candidate_id],
            "paths": paths,
            "document_hashes": hashes,
        })
    manifest: dict[str, Any] = {
        "schema": ROUTE_SHAPE_NATIVE_SHORTLIST_SCHEMA,
        "status": "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY",
        "source_campaign_plan_sha256": plan_hash,
        "source_campaign_screen_sha256": screen_hash,
        "source_collision_candidate_sha256": collision_candidate[
            "candidate_sha256"
        ],
        "source_collision_pair_policy_sha256": collision_pair_policy[
            "policy_sha256"
        ],
        "source_toolchain_lock_sha256": _canonical_sha256(toolchain_lock),
        "shortlist_count": len(entries),
        "entries": entries,
        "native_isaac_replay_executed": False,
        "installed_profile_eligible": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def retain_placement_tcp_native_results(
    search_plan: dict[str, Any],
    search_screen: dict[str, Any],
    shortlist_manifest: dict[str, Any],
    native_receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Retain and rank ARM-199 native results without granting authority.

    The retained evidence intentionally includes every native sample and raw
    collision pair.  A lower-ranked hypothesis is evidence too: it prevents a
    later campaign from presenting a known-worse placement as unexplored.
    """
    def verified(document: dict[str, Any], digest_field: str, label: str) -> str:
        claimed = document.get(digest_field)
        unsigned = dict(document)
        unsigned.pop(digest_field, None)
        if not isinstance(claimed, str) or claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} digest is invalid")
        return claimed

    plan_hash = verified(search_plan, "plan_sha256", "search plan")
    screen_hash = verified(search_screen, "screen_sha256", "search screen")
    manifest_hash = verified(
        shortlist_manifest, "manifest_sha256", "shortlist manifest"
    )
    if (
        search_plan.get("schema") != PLACEMENT_TCP_SEARCH_PLAN_SCHEMA
        or search_screen.get("schema") != PLACEMENT_TCP_SEARCH_SCREEN_SCHEMA
        or shortlist_manifest.get("schema")
        != "tactevra.isaac_lm1_placement_tcp_native_shortlist.v1"
        or search_screen.get("source_search_plan_sha256") != plan_hash
        or shortlist_manifest.get("source_search_plan_sha256") != plan_hash
        or shortlist_manifest.get("source_search_screen_sha256") != screen_hash
        or shortlist_manifest.get("status")
        != "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY"
    ):
        raise MechanicsContractError("native result selection lineage is invalid")
    for document, label in (
        (search_plan, "search plan"),
        (search_screen, "search screen"),
        (shortlist_manifest, "shortlist manifest"),
    ):
        if (
            document.get("hardware_access", False) is not False
            or document.get("physical_authority", False) is not False
            or document.get("controller_commands", []) != []
            or document.get("hardware_writes", 0) != 0
            or document.get("physical_movements", 0) != 0
            or document.get("gate_promotions", []) != []
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    manifest_entries = shortlist_manifest.get("entries")
    if not isinstance(manifest_entries, list) or not manifest_entries:
        raise MechanicsContractError("shortlist manifest has no entries")
    entry_ids = [item.get("candidate_id") for item in manifest_entries]
    if (
        len(entry_ids) != len(set(entry_ids))
        or set(entry_ids) != set(native_receipts)
        or entry_ids != search_screen.get("native_shortlist_candidate_ids")
    ):
        raise MechanicsContractError("native receipt candidate coverage changed")
    outcomes = {
        item.get("candidate_id"): item for item in search_screen.get("outcomes", [])
    }
    candidates = {
        item.get("candidate_id"): item for item in search_plan.get("candidates", [])
    }
    retained: list[dict[str, Any]] = []
    for entry in manifest_entries:
        candidate_id = entry["candidate_id"]
        receipt = native_receipts[candidate_id]
        receipt_hash = verified(receipt, "receipt_sha256", "native receipt")
        if (
            candidate_id not in outcomes
            or candidate_id not in candidates
            or receipt.get("schema")
            != TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
            or receipt.get("status")
            not in {"DIAGNOSTIC_BLOCKERS_OBSERVED", "DIAGNOSTIC_NO_OVERLAPS_OBSERVED"}
            or receipt.get("hardware_access") is not False
            or receipt.get("physical_authority") is not False
            or receipt.get("controller_commands") != []
            or receipt.get("hardware_writes") != 0
            or receipt.get("physical_movements") != 0
            or receipt.get("gate_promotions") != []
            or receipt.get("source_bindings", {}).get("ik_receipt_sha256")
            != entry.get("document_hashes", {}).get("ik_receipt.json")
            or receipt.get("source_bindings", {}).get("request_sha256")
            != entry.get("document_hashes", {}).get(
                "policy_bound_collision_request.json"
            )
            or not isinstance(receipt.get("samples"), list)
            or len(receipt["samples"]) != receipt.get("bounded_sample_count")
            or len(receipt.get("physical_solid_blocker_pairs", []))
            != receipt.get("physical_solid_blocker_pair_count")
        ):
            raise MechanicsContractError(
                f"native receipt {candidate_id} is not admissible"
            )
        metrics = outcomes[candidate_id].get("ik_metrics")
        if not isinstance(metrics, dict):
            raise MechanicsContractError(f"candidate {candidate_id} lacks IK metrics")
        retained.append({
            "candidate_id": candidate_id,
            "candidate": candidates[candidate_id],
            "native_receipt_sha256": receipt_hash,
            "native_status": receipt["status"],
            "bounded_sample_count": receipt["bounded_sample_count"],
            "samples_with_overlaps": receipt["samples_with_overlaps"],
            "physical_solid_blocker_pair_count": receipt[
                "physical_solid_blocker_pair_count"
            ],
            "physical_solid_blocker_pairs": receipt[
                "physical_solid_blocker_pairs"
            ],
            "ik_metrics": metrics,
            "raw_native_samples": receipt["samples"],
        })

    def native_rank(item: dict[str, Any]) -> tuple[int, int, float, float, str]:
        return (
            int(item["physical_solid_blocker_pair_count"]),
            int(item["samples_with_overlaps"]),
            -float(item["ik_metrics"]["minimum_normalized_arm_joint_margin"]),
            float(item["ik_metrics"]["maximum_position_error_mm"]),
            str(item["candidate_id"]),
        )

    retained.sort(key=native_rank)
    for rank, item in enumerate(retained, start=1):
        item["native_rank"] = rank
    control_id = search_plan.get("control_candidate_id")
    if control_id not in native_receipts:
        raise MechanicsContractError("native result selection lacks the control")
    selected_id = retained[0]["candidate_id"]
    improved = selected_id != control_id
    result: dict[str, Any] = {
        "schema": PLACEMENT_TCP_NATIVE_SELECTION_SCHEMA,
        "status": (
            "NATIVE_DIAGNOSTIC_IMPROVEMENT_RETAINED"
            if improved else "NO_NATIVE_IMPROVEMENT_RETAINED"
        ),
        "source_search_plan_sha256": plan_hash,
        "source_search_screen_sha256": screen_hash,
        "source_shortlist_manifest_sha256": manifest_hash,
        "control_candidate_id": control_id,
        "selected_candidate_id": selected_id,
        "native_improvement_over_control": improved,
        "rank_order": [item["candidate_id"] for item in retained],
        "ranking_rule": [
            "physical_solid_blocker_pair_count ASC",
            "samples_with_overlaps ASC",
            "minimum_normalized_arm_joint_margin DESC",
            "maximum_position_error_mm ASC",
            "candidate_id ASC",
        ],
        "retained_results": retained,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "Native results are diagnostic and do not establish continuous clearance.",
            "No placement or TCP candidate is installed by this selection.",
            "The native control remains blocked; ARM-199 does not authorize motion.",
        ],
    }
    result["selection_sha256"] = _canonical_sha256(result)
    return result


def retain_route_shape_native_results(
    campaign_plan: dict[str, Any],
    campaign_screen: dict[str, Any],
    shortlist_manifest: dict[str, Any],
    control_receipt: dict[str, Any],
    native_evidence: dict[str, dict[str, Any]],
    *,
    require_route_predicate_receipts: bool = False,
) -> dict[str, Any]:
    """Retain fixed native attempts, including explicit pre-receipt failures."""

    def verified(document: dict[str, Any], digest_field: str, label: str) -> str:
        claimed = document.get(digest_field)
        unsigned = dict(document)
        unsigned.pop(digest_field, None)
        if not isinstance(claimed, str) or claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} digest is invalid")
        return claimed

    plan_hash = verified(campaign_plan, "plan_sha256", "campaign plan")
    screen_hash = verified(campaign_screen, "screen_sha256", "campaign screen")
    manifest_hash = verified(
        shortlist_manifest, "manifest_sha256", "shortlist manifest"
    )
    control_hash = verified(control_receipt, "receipt_sha256", "control receipt")
    if (
        campaign_plan.get("schema") != ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA
        or campaign_screen.get("schema") != ROUTE_SHAPE_CAMPAIGN_SCREEN_SCHEMA
        or shortlist_manifest.get("schema") != ROUTE_SHAPE_NATIVE_SHORTLIST_SCHEMA
        or campaign_screen.get("source_campaign_plan_sha256") != plan_hash
        or shortlist_manifest.get("source_campaign_plan_sha256") != plan_hash
        or shortlist_manifest.get("source_campaign_screen_sha256") != screen_hash
        or shortlist_manifest.get("status")
        != "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY"
        or control_receipt.get("schema")
        != TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
    ):
        raise MechanicsContractError("route-shape native selection lineage is invalid")
    for document, label in (
        (campaign_plan, "campaign plan"),
        (campaign_screen, "campaign screen"),
        (shortlist_manifest, "shortlist manifest"),
        (control_receipt, "control receipt"),
    ):
        if (
            document.get("hardware_access", False) is not False
            or document.get("physical_authority", False) is not False
            or document.get("controller_commands", []) != []
            or document.get("hardware_writes", 0) != 0
            or document.get("physical_movements", 0) != 0
            or document.get("gate_promotions", []) != []
        ):
            raise MechanicsContractError(f"{label} crossed zero authority")

    entries = shortlist_manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise MechanicsContractError("route-shape shortlist manifest has no entries")
    entry_ids = [entry.get("candidate_id") for entry in entries]
    if (
        len(entry_ids) != len(set(entry_ids))
        or set(entry_ids) != set(native_evidence)
        or entry_ids != campaign_screen.get("native_shortlist_candidate_ids")
    ):
        raise MechanicsContractError("route-shape native attempt coverage changed")

    baseline_pairs = control_receipt.get("physical_solid_blocker_pairs")
    baseline_count = control_receipt.get("physical_solid_blocker_pair_count")
    if (
        control_receipt.get("status") != "DIAGNOSTIC_BLOCKERS_OBSERVED"
        or not isinstance(baseline_pairs, list)
        or len(baseline_pairs) != baseline_count
        or not isinstance(control_receipt.get("samples"), list)
    ):
        raise MechanicsContractError("ARM-199 native control is not admissible")

    retained: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for entry in entries:
        candidate_id = entry["candidate_id"]
        evidence = native_evidence[candidate_id]
        if evidence.get("status") == "ERROR":
            if (
                not isinstance(evidence.get("message"), str)
                or not isinstance(evidence.get("type"), str)
            ):
                raise MechanicsContractError(
                    f"native failure {candidate_id} is not explicit"
                )
            failures.append({
                "candidate_id": candidate_id,
                "rank": entry["rank"],
                "attempt_status": evidence.get(
                    "attempt_status", "PRE_ADMISSION_ERROR"
                ),
                "error_type": evidence["type"],
                "error_message": evidence["message"],
                "status_sha256": _canonical_sha256(evidence),
                "automatic_retry_performed": False,
            })
            continue

        receipt_hash = verified(evidence, "receipt_sha256", "native receipt")
        allowed_receipt_schemas = {
            TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
        } if require_route_predicate_receipts else {
            TCP_PRIMITIVE_ATTRIBUTED_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
            TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
        }
        if (
            evidence.get("schema") not in allowed_receipt_schemas
            or evidence.get("status")
            not in {"DIAGNOSTIC_BLOCKERS_OBSERVED", "DIAGNOSTIC_NO_OVERLAPS_OBSERVED"}
            or evidence.get("hardware_access") is not False
            or evidence.get("physical_authority") is not False
            or evidence.get("controller_commands") != []
            or evidence.get("hardware_writes") != 0
            or evidence.get("physical_movements") != 0
            or evidence.get("gate_promotions") != []
            or evidence.get("source_bindings", {}).get("ik_receipt_sha256")
            != entry.get("document_hashes", {}).get("ik_receipt.json")
            or evidence.get("source_bindings", {}).get("request_sha256")
            != entry.get("document_hashes", {}).get(
                "policy_bound_collision_request.json"
            )
            or not isinstance(evidence.get("samples"), list)
            or len(evidence["samples"]) != evidence.get("bounded_sample_count")
            or len(evidence.get("physical_solid_blocker_pairs", []))
            != evidence.get("physical_solid_blocker_pair_count")
        ):
            raise MechanicsContractError(
                f"route-shape native receipt {candidate_id} is not admissible"
            )
        physical_count = int(evidence["physical_solid_blocker_pair_count"])
        retained.append({
            "candidate_id": candidate_id,
            "candidate": entry["candidate"],
            "shortlist_rank": entry["rank"],
            "native_receipt_sha256": receipt_hash,
            "native_receipt_schema": evidence["schema"],
            "station_route_predicate_applied": evidence["schema"]
            == TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
            "native_status": evidence["status"],
            "bounded_sample_count": evidence["bounded_sample_count"],
            "samples_with_overlaps": evidence["samples_with_overlaps"],
            "physical_solid_blocker_pair_count": physical_count,
            "physical_solid_blocker_pairs": evidence[
                "physical_solid_blocker_pairs"
            ],
            "planning_envelope_blocker_pair_count": evidence[
                "planning_envelope_blocker_pair_count"
            ],
            "planning_envelope_blocker_pairs": evidence[
                "planning_envelope_blocker_pairs"
            ],
            "policy_excluded_pair_count": evidence["policy_excluded_pair_count"],
            "unreviewed_blocker_pair_count": evidence[
                "unreviewed_blocker_pair_count"
            ],
            "improves_physical_pair_count_over_control": physical_count
            < int(baseline_count),
            "raw_native_samples": evidence["samples"],
        })

    retained.sort(
        key=lambda item: (
            int(item["physical_solid_blocker_pair_count"]),
            float(item["samples_with_overlaps"])
            / float(item["bounded_sample_count"]),
            int(item["shortlist_rank"]),
            str(item["candidate_id"]),
        )
    )
    for rank, item in enumerate(retained, start=1):
        item["native_rank"] = rank
    improvements = [
        item for item in retained
        if item["improves_physical_pair_count_over_control"]
    ]
    selected_id = improvements[0]["candidate_id"] if improvements else None
    incomplete_status = (
        "INCOMPLETE_V4_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED"
        if require_route_predicate_receipts
        else "INCOMPLETE_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED"
    )
    result: dict[str, Any] = {
        "schema": (
            ROUTE_SHAPE_V4_NATIVE_SELECTION_SCHEMA
            if require_route_predicate_receipts
            else ROUTE_SHAPE_NATIVE_SELECTION_SCHEMA
        ),
        "status": (
            "NATIVE_ROUTE_SHAPE_IMPROVEMENT_RETAINED"
            if selected_id is not None
            else (
                incomplete_status
                if failures
                else "NO_NATIVE_ROUTE_SHAPE_IMPROVEMENT_RETAINED"
            )
        ),
        "source_campaign_plan_sha256": plan_hash,
        "source_campaign_screen_sha256": screen_hash,
        "source_shortlist_manifest_sha256": manifest_hash,
        "source_control_receipt_sha256": control_hash,
        "control_physical_solid_blocker_pair_count": baseline_count,
        "control_physical_solid_blocker_pairs": baseline_pairs,
        "attempted_candidate_count": len(entry_ids),
        "completed_native_replay_count": len(retained),
        "failed_pre_admission_count": len(failures),
        "native_improvement_over_control": selected_id is not None,
        "selected_candidate_id": selected_id,
        "rank_order": [item["candidate_id"] for item in retained],
        "ranking_rule": [
            "physical_solid_blocker_pair_count ASC",
            "samples_with_overlaps / bounded_sample_count ASC",
            "shortlist_rank ASC",
            "candidate_id ASC",
        ],
        "retained_results": retained,
        "failed_attempts": failures,
        "automatic_retries_performed": 0,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": (
            [
                f"{len(failures)} fixed candidates stopped before producing a receipt and were not retried.",
                "Completed attempts are v4 route-predicate diagnostics, but the fixed campaign is incomplete.",
                "Completed native replays remain diagnostic, not continuous-clearance proof.",
                "No route shape is installed and ARM-203 grants no physical authority.",
            ]
            if require_route_predicate_receipts
            else [
                "One fixed candidate stopped at pre-admission and was not retried.",
                "Completed attempts used v3 primitive-attributed diagnostics without "
                "the separate station-route-predicate input; physical and planning "
                "pairs remain separate, but route-predicate replay is incomplete.",
                "Completed native replays remain diagnostic, not continuous-clearance proof.",
                "No route shape is installed and ARM-202 grants no physical authority.",
            ]
        ),
    }
    result["selection_sha256"] = _canonical_sha256(result)
    return result


def build_robot_tcp_collision_replay_request(
    ik_receipt: dict[str, Any],
    collision_candidate: dict[str, Any],
    toolchain_lock: dict[str, Any],
) -> dict[str, Any]:
    """Bind accepted IK results to bounded zero-authority collision samples.

    The retained candidate geometry is deliberately simulation-only and
    uninstalled.  This request can drive an Isaac diagnostic, but cannot clear
    installed-geometry or physical-motion gates.
    """
    if ik_receipt.get("schema") != TCP_IK_SCREEN_SCHEMA:
        raise MechanicsContractError("unexpected IK receipt schema")
    claimed_ik_hash = ik_receipt.get("receipt_sha256")
    unsigned_ik = dict(ik_receipt)
    unsigned_ik.pop("receipt_sha256", None)
    if claimed_ik_hash != _canonical_sha256(unsigned_ik):
        raise MechanicsContractError("IK receipt hash mismatch")
    if (
        ik_receipt.get("status") != "READY_FOR_COLLISION_QUALIFICATION"
        or ik_receipt.get("ik_all_samples_accepted") is not True
        or ik_receipt.get("evaluated_sample_count") != ik_receipt.get("sample_count")
    ):
        raise MechanicsContractError("collision replay requires an all-accepted IK receipt")
    for document, label in ((ik_receipt, "IK receipt"), (collision_candidate, "collision candidate")):
        if (
            document.get("physical_authority") is not False
            or document.get("hardware_access", False) is not False
            or document.get("hardware_write_count", document.get("hardware_writes")) != 0
            or document.get("physical_movement_count", document.get("physical_movements")) != 0
            or document.get("commands", document.get("controller_commands")) != []
        ):
            raise MechanicsContractError(f"{label} crossed the zero-authority boundary")

    claimed_candidate_hash = collision_candidate.get("candidate_sha256")
    unsigned_candidate = dict(collision_candidate)
    unsigned_candidate.pop("candidate_sha256", None)
    if claimed_candidate_hash != _canonical_sha256(unsigned_candidate):
        raise MechanicsContractError("collision candidate hash mismatch")
    if (
        collision_candidate.get("schema")
        != "tactevra.simulation_collision_candidate.v1"
        or collision_candidate.get("scope")
        != "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
    ):
        raise MechanicsContractError("collision candidate boundary changed")

    if (
        toolchain_lock.get("schema") != "rocell.isaac_sim_toolchain_lock.v1"
        or toolchain_lock.get("selection_status") != "SELECTED"
        or toolchain_lock.get("hardware_access") is not False
        or toolchain_lock.get("physical_authority") is not False
        or toolchain_lock.get("wire_commands") != []
    ):
        raise MechanicsContractError("Isaac toolchain lock is not selected zero-authority")

    try:
        from rocell.application.bounded_segment_collision_qualification import (
            BoundedSegmentSamplingPolicy,
            build_bounded_joint_sample_plan_from_results,
        )
        from rocell.kinematics import ARM_JOINT_NAMES
    except ImportError as exc:
        raise MechanicsContractError(
            "bounded collision runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    joint_results = ik_receipt.get("joint_results")
    if not isinstance(joint_results, list):
        raise MechanicsContractError("IK receipt joint results are absent")
    policy = BoundedSegmentSamplingPolicy(
        maximum_joint_step_rad=0.05,
        maximum_samples=256,
    )
    plan = build_bounded_joint_sample_plan_from_results(
        ik_receipt.get("initial_seed_joint_positions_rad"),
        joint_results,
        policy,
    )
    candidate_blockers = collision_candidate.get("blockers")
    if (
        not isinstance(candidate_blockers, list)
        or not candidate_blockers
        or not all(isinstance(item, str) and item for item in candidate_blockers)
    ):
        raise MechanicsContractError("collision candidate blockers are absent")
    bodies = collision_candidate.get("robot_bodies")
    workcell = collision_candidate.get("workcell_bodies")
    if not isinstance(bodies, list) or not bodies or not isinstance(workcell, list) or not workcell:
        raise MechanicsContractError("collision candidate body coverage is absent")

    request: dict[str, Any] = {
        "schema": TCP_COLLISION_REPLAY_REQUEST_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC",
        "source_ik_receipt_sha256": claimed_ik_hash,
        "source_request_sha256": ik_receipt["source_request_sha256"],
        "source_bundle_sha256": ik_receipt["source_bundle_sha256"],
        "collision_candidate_sha256": claimed_candidate_hash,
        "collision_candidate_status": collision_candidate["status"],
        "collision_candidate_installed": False,
        "collision_candidate_blockers": list(candidate_blockers),
        "toolchain_lock_sha256": _canonical_sha256(toolchain_lock),
        "toolchain": {
            name: toolchain_lock[name]
            for name in (
                "isaac_sim_version", "installation_sha256",
                "extension_lock_sha256", "settings_profile_sha256",
                "runner_platform", "launch_method",
            )
        },
        "joint_order": list(ARM_JOINT_NAMES),
        "source_joint_result_count": len(joint_results),
        "bounded_sample_count": len(plan),
        "bounded_sampling_policy": policy.to_dict(),
        "bounded_samples": [item.to_dict() for item in plan],
        "collision_scopes": [
            "ROBOT_SELF_COLLISION",
            "ROBOT_TO_WORKCELL",
            "ROBOT_TOOL_CAMERA_SUPPORT_DIAGNOSTIC_WHERE_BOUND",
        ],
        "diagnostic_only": True,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "native_contact_replay_authorized": False,
        "next_required_stage": "RUN_SELECTED_ISAAC_COLLISION_DIAGNOSTIC_AND_RETAIN_PAIR_EVIDENCE",
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "exploratory_collision_candidate_is_uninstalled",
            "bounded_sampling_is_not_continuous_swept_volume_proof",
            "missing_candidate_bodies_remain_explicit_blockers",
            "diagnostic_result_cannot_promote_installed_or_physical_gates",
        ],
    }
    if "placement_tcp_candidate_id" in ik_receipt:
        matrix = ik_receipt.get("robot_placement_matrix_row_major")
        if not isinstance(matrix, list) or len(matrix) != 16:
            raise MechanicsContractError(
                "placement/TCP IK receipt lacks its placement matrix"
            )
        request.update({
            "placement_tcp_candidate_id": ik_receipt["placement_tcp_candidate_id"],
            "robot_placement_matrix_row_major": list(matrix),
            "keyboard_tcp_length_mm": ik_receipt["tool_length_mm"],
            "placement_tcp_candidate_classification": ik_receipt[
                "placement_tcp_candidate_classification"
            ],
        })
        request["limitations"].append(
            "candidate_placement_and_tcp_are_plan_bound_simulation_hypotheses"
        )
    request["request_sha256"] = _canonical_sha256(request)
    return request


def admit_robot_tcp_collision_diagnostic(
    request: dict[str, Any],
    ik_receipt: dict[str, Any],
    collision_candidate: dict[str, Any],
    virtual_profile_bytes: bytes,
    robot_usd_bytes: bytes,
    import_receipt: dict[str, Any],
    accepted_pair_policy: dict[str, Any] | None = None,
    station_route_predicate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate all native collision inputs before Isaac or a GPU can start."""
    claimed_request_hash = request.get("request_sha256")
    unsigned_request = dict(request)
    unsigned_request.pop("request_sha256", None)
    if claimed_request_hash != _canonical_sha256(unsigned_request):
        raise MechanicsContractError("collision diagnostic request hash mismatch")
    request_schema = request.get("schema")
    if (
        request_schema not in (
            TCP_COLLISION_REPLAY_REQUEST_SCHEMA,
            TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA,
        )
        or request.get("status") != "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC"
        or request.get("diagnostic_only") is not True
        or request.get("installed_collision_qualified") is not False
        or request.get("continuous_collision_proven") is not False
        or request.get("native_contact_replay_authorized") is not False
    ):
        raise MechanicsContractError("collision diagnostic request boundary changed")
    if request_schema == TCP_COLLISION_REPLAY_REQUEST_SCHEMA:
        if accepted_pair_policy is not None:
            raise MechanicsContractError("unbound collision request cannot use a pair policy")
    else:
        if accepted_pair_policy is None:
            raise MechanicsContractError("policy-bound collision request lacks its pair policy")
        claimed_policy_hash = accepted_pair_policy.get("policy_sha256")
        unsigned_policy = dict(accepted_pair_policy)
        unsigned_policy.pop("policy_sha256", None)
        if claimed_policy_hash != _canonical_sha256(unsigned_policy):
            raise MechanicsContractError("collision pair policy hash mismatch")
        expected_pairs = {
            tuple(sorted(pair)) for pair in (
                ("robot:base_link", "robot:link1"),
                ("robot:link1", "robot:link2"),
                ("robot:link2", "robot:link3"),
                ("robot:link3", "robot:link4"),
                ("robot:link5", "robot:gripper"),
            )
        }
        accepted_pairs = {
            tuple(sorted(pair))
            for pair in accepted_pair_policy.get("accepted_exclusion_pairs", [])
        }
        if (
            accepted_pair_policy.get("schema") != TCP_COLLISION_POLICY_SCHEMA
            or accepted_pair_policy.get("status")
            != "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY"
            or accepted_pair_policy.get("diagnostic_policy_active") is not True
            or accepted_pair_policy.get("installed_profile_active") is not False
            or accepted_pair_policy.get("installed_profile_eligible") is not False
            or accepted_pair_policy.get("physical_solid_pairs_excluded") != []
            or accepted_pair_policy.get("planning_envelope_pairs_excluded") != []
            or accepted_pair_policy.get("gate_promotions") != []
            or accepted_pairs != expected_pairs
            or accepted_pair_policy.get("accepted_exclusion_count") != len(expected_pairs)
            or request.get("collision_pair_policy_sha256") != claimed_policy_hash
            or request.get("collision_pair_policy_scope") != "DIAGNOSTIC_REPORTING_ONLY"
            or request.get("collision_candidate_sha256")
            != accepted_pair_policy.get("collision_candidate_sha256")
        ):
            raise MechanicsContractError("collision pair policy boundary changed")
        for field, expected in (
            ("hardware_access", False),
            ("physical_authority", False),
            ("hardware_writes", 0),
            ("physical_movements", 0),
        ):
            if accepted_pair_policy.get(field) != expected:
                raise MechanicsContractError("collision pair policy crossed zero authority")
    if station_route_predicate is not None and accepted_pair_policy is None:
        raise MechanicsContractError(
            "station route predicate requires the accepted diagnostic pair policy"
        )
    for document, label in (
        (request, "collision request"),
        (ik_receipt, "IK receipt"),
        (import_receipt, "robot import receipt"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("physical_authority") is not False
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed the zero-authority boundary")
    if (
        collision_candidate.get("physical_authority") is not False
        or collision_candidate.get("hardware_write_count") != 0
        or collision_candidate.get("physical_movement_count") != 0
        or collision_candidate.get("commands") != []
    ):
        raise MechanicsContractError("collision candidate crossed the zero-authority boundary")

    claimed_ik_hash = ik_receipt.get("receipt_sha256")
    unsigned_ik = dict(ik_receipt)
    unsigned_ik.pop("receipt_sha256", None)
    if claimed_ik_hash != _canonical_sha256(unsigned_ik):
        raise MechanicsContractError("collision diagnostic IK receipt hash mismatch")
    if (
        request.get("source_ik_receipt_sha256") != claimed_ik_hash
        or request.get("source_request_sha256") != ik_receipt.get("source_request_sha256")
        or request.get("source_bundle_sha256") != ik_receipt.get("source_bundle_sha256")
    ):
        raise MechanicsContractError("collision request and IK lineage differ")

    claimed_candidate_hash = collision_candidate.get("candidate_sha256")
    unsigned_candidate = dict(collision_candidate)
    unsigned_candidate.pop("candidate_sha256", None)
    if claimed_candidate_hash != _canonical_sha256(unsigned_candidate):
        raise MechanicsContractError("collision diagnostic candidate hash mismatch")
    if (
        request.get("collision_candidate_sha256") != claimed_candidate_hash
        or collision_candidate.get("schema") != "tactevra.simulation_collision_candidate.v1"
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
        or request.get("collision_candidate_blockers") != collision_candidate.get("blockers")
    ):
        raise MechanicsContractError("collision request and candidate boundary differ")

    samples = request.get("bounded_samples")
    joint_order = request.get("joint_order")
    if (
        not isinstance(samples, list)
        or not samples
        or len(samples) != request.get("bounded_sample_count")
        or len(samples) > 256
        or not isinstance(joint_order, list)
        or len(joint_order) != 5
        or [sample.get("sample_sequence") for sample in samples]
        != list(range(len(samples)))
    ):
        raise MechanicsContractError("bounded collision samples are invalid")
    for sample in samples:
        positions = sample.get("joint_positions_rad")
        if not isinstance(positions, dict) or list(positions) != joint_order:
            raise MechanicsContractError("bounded collision joint order changed")
        for name in joint_order:
            _finite_number(positions.get(name), f"bounded sample joint {name}")

    if hashlib.sha256(virtual_profile_bytes).hexdigest() != ik_receipt.get(
        "virtual_profile_sha256"
    ):
        raise MechanicsContractError("virtual profile differs from the accepted IK receipt")
    profile = json.loads(virtual_profile_bytes)
    placement = profile.get("study_input", {}).get("physical_placement_input")
    profile_matrix = (
        placement.get("matrix_row_major") if isinstance(placement, dict) else None
    )
    matrix = request.get("robot_placement_matrix_row_major", profile_matrix)
    if not isinstance(matrix, list) or len(matrix) != 16:
        raise MechanicsContractError("virtual profile lacks the governed robot placement")
    for value in matrix:
        _finite_number(value, "robot placement matrix value")
    candidate_id = request.get("placement_tcp_candidate_id")
    if candidate_id is not None and (
        not isinstance(candidate_id, str)
        or candidate_id != ik_receipt.get("placement_tcp_candidate_id")
        or matrix != ik_receipt.get("robot_placement_matrix_row_major")
        or request.get("keyboard_tcp_length_mm") != ik_receipt.get("tool_length_mm")
    ):
        raise MechanicsContractError(
            "collision request and placement/TCP IK evidence differ"
        )

    claimed_import_hash = import_receipt.get("receipt_sha256")
    unsigned_import = dict(import_receipt)
    unsigned_import.pop("receipt_sha256", None)
    if claimed_import_hash != _canonical_sha256(unsigned_import):
        raise MechanicsContractError("robot import receipt hash mismatch")
    external_files = import_receipt.get("external_files")
    robot_usd_hash = hashlib.sha256(robot_usd_bytes).hexdigest()
    if (
        import_receipt.get("schema") != "tactevra.isaac_sim_urdf_import.v1"
        or not isinstance(external_files, list)
        or len(external_files) != 1
        or external_files[0].get("sha256") != robot_usd_hash
        or external_files[0].get("size_bytes") != len(robot_usd_bytes)
    ):
        raise MechanicsContractError("robot USD differs from its governed import receipt")
    normalization = import_receipt.get("articulation_root_normalization")
    expected_dofs = joint_order + ["link5_to_gripper_link"]
    if not isinstance(normalization, dict) or normalization.get(
        "expected_live_dof_order"
    ) != expected_dofs:
        raise MechanicsContractError("robot import articulation order changed")

    robot_bodies = collision_candidate.get("robot_bodies")
    workcell_bodies = collision_candidate.get("workcell_bodies")
    if not isinstance(robot_bodies, list) or not robot_bodies \
            or not isinstance(workcell_bodies, list) or not workcell_bodies:
        raise MechanicsContractError("collision candidate body coverage is absent")
    for body in robot_bodies + workcell_bodies:
        primitives = body.get("primitives") if isinstance(body, dict) else None
        if not isinstance(primitives, list) or not primitives:
            raise MechanicsContractError("collision candidate body lacks primitives")
        for primitive in primitives:
            rotation = primitive.get("rotation_row_major")
            if (
                primitive.get("kind") != "oriented_box"
                or not isinstance(rotation, list)
                or len(rotation) != 9
                or len(primitive.get("center_mm", [])) != 3
                or len(primitive.get("half_extents_mm", [])) != 3
            ):
                raise MechanicsContractError(
                    "native diagnostic requires governed oriented-box primitives"
                )
            rotation = [
                _finite_number(value, "collision box rotation")
                for value in rotation
            ]
            rows = [rotation[index:index + 3] for index in range(0, 9, 3)]
            for row_index, row in enumerate(rows):
                for other_index, other in enumerate(rows):
                    dot = sum(left * right for left, right in zip(row, other))
                    expected = 1.0 if row_index == other_index else 0.0
                    if abs(dot - expected) > 1e-6:
                        raise MechanicsContractError(
                            "collision box rotation must be orthonormal"
                        )
            determinant = (
                rotation[0]
                * (rotation[4] * rotation[8] - rotation[5] * rotation[7])
                - rotation[1]
                * (rotation[3] * rotation[8] - rotation[5] * rotation[6])
                + rotation[2]
                * (rotation[3] * rotation[7] - rotation[4] * rotation[6])
            )
            if abs(determinant - 1.0) > 1e-6:
                raise MechanicsContractError(
                    "collision box rotation must be right-handed"
                )
            for value in primitive["center_mm"]:
                _finite_number(value, "collision box center")
            for value in primitive["half_extents_mm"]:
                if _finite_number(value, "collision box half extent") <= 0.0:
                    raise MechanicsContractError("collision box half extent must be positive")

    if station_route_predicate is not None:
        claimed_predicate_hash = station_route_predicate.get("predicate_sha256")
        unsigned_predicate = dict(station_route_predicate)
        unsigned_predicate.pop("predicate_sha256", None)
        if claimed_predicate_hash != _canonical_sha256(unsigned_predicate):
            raise MechanicsContractError("station route predicate hash mismatch")
        physical_bodies, station_bodies = _validated_collision_candidate_partition(
            collision_candidate
        )
        if (
            station_route_predicate.get("schema") != STATION_ROUTE_PREDICATE_SCHEMA
            or station_route_predicate.get("status") != "PASS"
            or station_route_predicate.get("violation_count") != 0
            or station_route_predicate.get("source_cartesian_request_sha256")
            != request.get("source_request_sha256")
            or station_route_predicate.get("source_collision_candidate_sha256")
            != claimed_candidate_hash
            or station_route_predicate.get("physical_workcell_body_ids")
            != sorted(body["body_id"] for body in physical_bodies)
            or station_route_predicate.get("physx_excluded_station_region_ids")
            != sorted(body["body_id"] for body in station_bodies)
            or station_route_predicate.get("installed_profile_eligible") is not False
            or station_route_predicate.get("installed_collision_qualified") is not False
            or station_route_predicate.get("continuous_collision_proven") is not False
            or station_route_predicate.get("hardware_access") is not False
            or station_route_predicate.get("physical_authority") is not False
            or station_route_predicate.get("controller_commands") != []
            or station_route_predicate.get("hardware_writes") != 0
            or station_route_predicate.get("physical_movements") != 0
            or station_route_predicate.get("gate_promotions") != []
        ):
            raise MechanicsContractError("station route predicate boundary changed")

    admission: dict[str, Any] = {
        "schema": "tactevra.isaac_lm1_robot_tcp_collision_admission.v1",
        "status": "READY_TO_START_SELECTED_ISAAC_COLLISION_DIAGNOSTIC",
        "request_sha256": claimed_request_hash,
        "ik_receipt_sha256": claimed_ik_hash,
        "collision_candidate_sha256": claimed_candidate_hash,
        "virtual_profile_sha256": hashlib.sha256(virtual_profile_bytes).hexdigest(),
        "robot_import_receipt_sha256": claimed_import_hash,
        "robot_usd_sha256": robot_usd_hash,
        "toolchain_lock_sha256": request.get("toolchain_lock_sha256"),
        "bounded_sample_count": len(samples),
        "robot_body_count": len(robot_bodies),
        "workcell_body_count": len(workcell_bodies),
        "robot_placement_matrix_row_major": matrix,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "exploratory_uninstalled_collision_candidate_only",
            "discrete_overlap_queries_are_not_continuous_collision_proof",
            "candidate_blockers_remain_unresolved",
            "no_native_contact_or_physical_authority",
        ],
    }
    if candidate_id is not None:
        admission["placement_tcp_candidate_id"] = candidate_id
        admission["keyboard_tcp_length_mm"] = request["keyboard_tcp_length_mm"]
    if accepted_pair_policy is not None:
        admission.update({
            "collision_pair_policy_sha256": accepted_pair_policy["policy_sha256"],
            "collision_pair_policy_scope": "DIAGNOSTIC_REPORTING_ONLY",
            "accepted_exclusion_pairs": accepted_pair_policy[
                "accepted_exclusion_pairs"
            ],
        })
        admission["limitations"].append(
            "pair_policy_changes_classification_only_and_preserves_raw_overlaps"
        )
    if station_route_predicate is not None:
        admission.update({
            "station_route_predicate_sha256": station_route_predicate[
                "predicate_sha256"
            ],
            "station_route_predicate_applied": True,
            "physx_excluded_station_region_ids": station_route_predicate[
                "physx_excluded_station_region_ids"
            ],
            "physical_workcell_body_ids": station_route_predicate[
                "physical_workcell_body_ids"
            ],
        })
        admission["limitations"].append(
            "station_route_predicate_is_discrete_and_zero_authority"
        )
    admission["admission_sha256"] = _canonical_sha256(admission)
    return admission


def run_robot_tcp_collision_diagnostic(
    *,
    request_path: Path,
    ik_receipt_path: Path,
    collision_candidate_path: Path,
    virtual_profile_path: Path,
    robot_usd_path: Path,
    import_receipt_path: Path,
    output_path: Path,
    status_path: Path,
    accepted_pair_policy_path: Path | None = None,
    station_route_predicate_path: Path | None = None,
    geometry_capture_plan_path: Path | None = None,
    geometry_capture_output_path: Path | None = None,
    fixed_base_replay_plan_path: Path | None = None,
) -> dict[str, Any]:
    """Run discrete Isaac overlap queries with no controller or hardware authority."""
    request = json.loads(request_path.resolve(strict=True).read_bytes())
    ik_receipt = json.loads(ik_receipt_path.resolve(strict=True).read_bytes())
    collision_candidate = json.loads(
        collision_candidate_path.resolve(strict=True).read_bytes()
    )
    virtual_profile_bytes = virtual_profile_path.resolve(strict=True).read_bytes()
    robot_usd = robot_usd_path.resolve(strict=True)
    robot_usd_bytes = robot_usd.read_bytes()
    import_receipt = json.loads(import_receipt_path.resolve(strict=True).read_bytes())
    accepted_pair_policy = (
        json.loads(accepted_pair_policy_path.resolve(strict=True).read_bytes())
        if accepted_pair_policy_path is not None
        else None
    )
    station_route_predicate = (
        json.loads(station_route_predicate_path.resolve(strict=True).read_bytes())
        if station_route_predicate_path is not None
        else None
    )
    if (geometry_capture_plan_path is None) != (geometry_capture_output_path is None):
        raise MechanicsContractError(
            "geometry capture plan and output must be supplied together"
        )
    admission = admit_robot_tcp_collision_diagnostic(
        request,
        ik_receipt,
        collision_candidate,
        virtual_profile_bytes,
        robot_usd_bytes,
        import_receipt,
        accepted_pair_policy,
        station_route_predicate,
    )
    geometry_capture_plan = None
    geometry_capture_candidate = None
    geometry_capture_sequences: set[int] = set()
    if geometry_capture_plan_path is not None:
        geometry_capture_plan = json.loads(
            geometry_capture_plan_path.resolve(strict=True).read_bytes()
        )
        claimed_plan_hash = geometry_capture_plan.get("plan_sha256")
        unsigned_plan = dict(geometry_capture_plan)
        unsigned_plan.pop("plan_sha256", None)
        if (
            geometry_capture_plan.get("schema")
            != "tactevra.isaac_lm1_collision_geometry_parity_plan.v1"
            or claimed_plan_hash != _canonical_sha256(unsigned_plan)
            or geometry_capture_plan.get("source_collision_candidate_sha256")
            != collision_candidate["candidate_sha256"]
            or geometry_capture_plan.get("hardware_access") is not False
            or geometry_capture_plan.get("physical_authority") is not False
            or geometry_capture_plan.get("controller_commands") != []
            or geometry_capture_plan.get("hardware_writes") != 0
            or geometry_capture_plan.get("physical_movements") != 0
        ):
            raise MechanicsContractError("collision geometry capture plan is invalid")
        matches = [
            item
            for item in geometry_capture_plan.get("candidate_captures", [])
            if item.get("request_sha256") == request.get("source_request_sha256")
        ]
        if len(matches) != 1:
            raise MechanicsContractError(
                "collision geometry capture request binding is invalid"
            )
        geometry_capture_candidate = matches[0]
        geometry_capture_sequences = {
            item["sample_sequence"]
            for item in geometry_capture_candidate.get("capture_samples", [])
        }
        if not geometry_capture_sequences:
            raise MechanicsContractError("collision geometry capture samples are absent")
    fixed_base_replay_plan = None
    fixed_base_candidate = None
    representative_fixed_base = False
    state_policy_fixed_base = False
    if fixed_base_replay_plan_path is not None:
        fixed_base_replay_plan = json.loads(
            fixed_base_replay_plan_path.resolve(strict=True).read_bytes()
        )
        claimed_plan_hash = fixed_base_replay_plan.get("plan_sha256")
        unsigned_plan = dict(fixed_base_replay_plan)
        unsigned_plan.pop("plan_sha256", None)
        fixed_contract = fixed_base_replay_plan.get("fixed_base_contract")
        root_contract = fixed_base_replay_plan.get("root_pose_invariant")
        plan_schema = fixed_base_replay_plan.get("schema")
        state_policy_fixed_base = (
            plan_schema == STATE_POLICY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA
        )
        representative_fixed_base = plan_schema in {
            REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA,
            STATE_POLICY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA,
        }
        if (
            plan_schema not in {
                FIXED_BASE_COLLISION_REPLAY_PLAN_SCHEMA,
                REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA,
                STATE_POLICY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA,
            }
            or claimed_plan_hash != _canonical_sha256(unsigned_plan)
            or fixed_base_replay_plan.get("status")
            != "READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY"
            or not isinstance(fixed_contract, dict)
            or fixed_contract.get("mechanism") != "USD_FIXED_JOINT_TO_WORLD"
            or fixed_contract.get("articulation_path") != "/roarm_m3"
            or fixed_contract.get("base_body_name") != "base_link"
            or not isinstance(root_contract, dict)
            or root_contract.get("required_at_admission") is not True
            or root_contract.get("required_after_every_sample") is not True
            or root_contract.get("failure_behavior")
            != "ERROR_NO_ACCEPTED_COLLISION_RECEIPT"
            or fixed_base_replay_plan.get("hardware_access") is not False
            or fixed_base_replay_plan.get("physical_authority") is not False
            or fixed_base_replay_plan.get("controller_commands") != []
            or fixed_base_replay_plan.get("hardware_writes") != 0
            or fixed_base_replay_plan.get("physical_movements") != 0
        ):
            raise MechanicsContractError("fixed-base collision replay plan is invalid")
        if representative_fixed_base:
            if (
                fixed_base_replay_plan.get("source_request_sha256")
                != request.get("source_request_sha256")
                or fixed_base_replay_plan.get("source_ik_receipt_sha256")
                != ik_receipt.get("receipt_sha256")
                or fixed_base_replay_plan.get("source_collision_request_sha256")
                != request.get("request_sha256")
                or fixed_base_replay_plan.get(
                    "source_station_route_predicate_sha256"
                )
                != (station_route_predicate or {}).get("predicate_sha256")
                or fixed_base_replay_plan.get("source_bounded_sample_count")
                != len(request.get("bounded_samples", []))
            ):
                raise MechanicsContractError(
                    "representative fixed-base replay binding changed"
                )
            if state_policy_fixed_base and (
                fixed_base_replay_plan.get("source_state_policy_request_sha256")
                != request.get("source_state_policy_request_sha256")
                or fixed_base_replay_plan.get(
                    "source_runtime_revalidation_receipt_sha256"
                )
                != request.get("source_runtime_revalidation_receipt_sha256")
            ):
                raise MechanicsContractError(
                    "state-policy fixed-base replay binding changed"
                )
            fixed_base_candidate = {
                "source_arm215_target_plan_sha256": fixed_base_replay_plan[
                    "source_arm215_target_plan_sha256"
                ]
            }
        else:
            matches = [
                item
                for item in fixed_base_replay_plan.get("candidates", [])
                if item.get("source_request_sha256")
                == request.get("source_request_sha256")
            ]
            if len(matches) != 1:
                raise MechanicsContractError("fixed-base candidate binding is invalid")
            fixed_base_candidate = matches[0]
            if fixed_base_candidate.get("source_v4_bounded_sample_count") != len(
                request.get("bounded_samples", [])
            ):
                raise MechanicsContractError("fixed-base replay source boundary changed")
        if accepted_pair_policy is None or station_route_predicate is None:
            raise MechanicsContractError("fixed-base replay source boundary changed")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.timeline
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.simulation_manager import SimulationManager
        from omni.physx import get_physx_scene_query_interface
        from pxr import Gf, PhysicsSchemaTools, PhysxSchema, UsdGeom, UsdPhysics

        if not omni.usd.get_context().open_stage(str(robot_usd)):
            raise RuntimeError("Isaac could not open the governed robot USD")
        for _ in range(5):
            app.update()
        stage = omni.usd.get_context().get_stage()

        prim_by_name: dict[str, Any] = {}
        for prim in stage.Traverse():
            prim_by_name.setdefault(prim.GetName(), prim)
        collision_path_to_primitive: dict[str, tuple[str, int]] = {}
        query_paths: list[tuple[str, str, int]] = []
        geometry_path_by_primitive: dict[tuple[str, int], str] = {}
        primitive_document_by_key: dict[tuple[str, int], dict[str, Any]] = {}

        def author_box(
            path: str,
            body_id: str,
            primitive_index: int,
            primitive: dict[str, Any],
        ) -> None:
            cube = UsdGeom.Cube.Define(stage, path)
            cube.CreateSizeAttr(1.0)
            xform = UsdGeom.Xformable(cube)
            center = primitive["center_mm"]
            half = primitive["half_extents_mm"]
            rotation = primitive["rotation_row_major"]
            xform.AddTranslateOp().Set(Gf.Vec3d(*(value / 1000.0 for value in center)))
            rotation_matrix = Gf.Matrix4d(1.0)
            rotation_matrix.SetRotateOnly(Gf.Matrix3d(*rotation))
            xform.AddOrientOp().Set(
                Gf.Quatf(rotation_matrix.ExtractRotationQuat())
            )
            xform.AddScaleOp().Set(Gf.Vec3d(*(2.0 * value / 1000.0 for value in half)))
            UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
            collision_path_to_primitive[path] = (body_id, primitive_index)
            geometry_path_by_primitive[(body_id, primitive_index)] = path
            primitive_document_by_key[(body_id, primitive_index)] = primitive

        for body_index, body in enumerate(collision_candidate["robot_bodies"]):
            parent = prim_by_name.get(body["parent_frame"])
            if parent is None or not parent.IsValid():
                raise RuntimeError(
                    f"robot collision parent frame is unavailable: {body['parent_frame']}"
                )
            root = f"{parent.GetPath()}/TactevraCollisionDiagnostic_{body_index:02d}"
            UsdGeom.Xform.Define(stage, root)
            for primitive_index, primitive in enumerate(body["primitives"]):
                path = f"{root}/box_{primitive_index:02d}"
                author_box(path, body["body_id"], primitive_index, primitive)
                query_paths.append((path, body["body_id"], primitive_index))

        workcell_root = "/TactevraCollisionDiagnostic/Workcell"
        UsdGeom.Xform.Define(stage, workcell_root)
        authored_workcell_bodies = (
            [
                body for body in collision_candidate["workcell_bodies"]
                if body["body_id"] in admission["physical_workcell_body_ids"]
            ]
            if station_route_predicate is not None
            else collision_candidate["workcell_bodies"]
        )
        for body_index, body in enumerate(authored_workcell_bodies):
            root = f"{workcell_root}/body_{body_index:02d}"
            UsdGeom.Xform.Define(stage, root)
            for primitive_index, primitive in enumerate(body["primitives"]):
                path = f"{root}/box_{primitive_index:02d}"
                author_box(path, body["body_id"], primitive_index, primitive)

        matrix = admission["robot_placement_matrix_row_major"]
        yaw = math.atan2(matrix[4], matrix[0])
        base_translation = [
            matrix[3] / 1000.0,
            matrix[7] / 1000.0,
            matrix[11] / 1000.0,
        ]
        base_quaternion_wxyz = [
            math.cos(yaw / 2.0),
            0.0,
            0.0,
            math.sin(yaw / 2.0),
        ]
        base_prim = prim_by_name.get("base_link")
        if base_prim is None or not base_prim.IsValid():
            raise RuntimeError("Isaac articulation base body is unavailable")
        if fixed_base_replay_plan is not None:
            articulation_root_prim = stage.GetPrimAtPath("/roarm_m3")
            if not articulation_root_prim.IsValid():
                raise RuntimeError("Isaac articulation root prim is unavailable")
            articulation_api = PhysxSchema.PhysxArticulationAPI.Apply(
                articulation_root_prim
            )
            articulation_api.CreateSolverPositionIterationCountAttr(
                FIXED_BASE_SOLVER_POSITION_ITERATION_COUNT
            )
            articulation_api.CreateSolverVelocityIterationCountAttr(
                FIXED_BASE_SOLVER_VELOCITY_ITERATION_COUNT
            )
            base_before = UsdGeom.Xformable(base_prim).ComputeLocalToWorldTransform(
                0.0
            )
            base_before_translation = base_before.ExtractTranslation()
            root_matrix = Gf.Matrix4d(1.0)
            root_matrix.SetRotate(
                Gf.Rotation(Gf.Vec3d(0.0, 0.0, 1.0), math.degrees(yaw))
            )
            root_matrix.SetTranslateOnly(Gf.Vec3d(
                base_translation[0] - float(base_before_translation[0]),
                base_translation[1] - float(base_before_translation[1]),
                base_translation[2] - float(base_before_translation[2]),
            ))
            UsdGeom.Xformable(articulation_root_prim).AddTransformOp().Set(
                root_matrix
            )
            fixed_joint = UsdPhysics.FixedJoint.Define(
                stage, "/roarm_m3/TactevraFixedBaseJoint"
            )
            fixed_joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*base_translation))
            fixed_joint.CreateLocalRot0Attr().Set(Gf.Quatf(
                base_quaternion_wxyz[0],
                Gf.Vec3f(*base_quaternion_wxyz[1:]),
            ))
            fixed_joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
            fixed_joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0))
            fixed_joint.CreateBody1Rel().SetTargets([base_prim.GetPath()])
            fixed_joint.CreateJointEnabledAttr().Set(True)

        SimulationManager.initialize_physics()
        for _ in range(10):
            app.update()
        articulation = Articulation("/roarm_m3")
        expected_dofs = request["joint_order"] + ["link5_to_gripper_link"]
        if list(articulation.dof_names) != expected_dofs:
            raise RuntimeError("Isaac articulation DOF order differs from the request")
        if not articulation.is_physics_tensor_entity_valid():
            raise RuntimeError("Isaac physics articulation view is unavailable")

        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        app.update()
        root_invariant_records = []
        root_contract = (
            fixed_base_replay_plan["root_pose_invariant"]
            if fixed_base_replay_plan is not None
            else None
        )

        def observe_root_invariant(label: str) -> dict[str, Any]:
            world = UsdGeom.Xformable(base_prim).ComputeLocalToWorldTransform(0.0)
            translation = world.ExtractTranslation()
            quaternion = world.RemoveScaleShear().ExtractRotationQuat()
            imaginary = quaternion.GetImaginary()
            observed_position = [float(translation[index]) for index in range(3)]
            observed_quaternion = [
                float(quaternion.GetReal()),
                float(imaginary[0]),
                float(imaginary[1]),
                float(imaginary[2]),
            ]
            result = evaluate_root_pose_invariant(
                base_translation,
                base_quaternion_wxyz,
                observed_position,
                observed_quaternion,
                translation_tolerance_mm=root_contract[
                    "translation_tolerance_mm"
                ],
                orientation_tolerance_deg=root_contract[
                    "orientation_tolerance_deg"
                ],
            )
            result.update({
                "observation": label,
                "observed_position_m": observed_position,
                "observed_quaternion_wxyz": observed_quaternion,
            })
            root_invariant_records.append(result)
            if not result["passed"]:
                raise RuntimeError(
                    "fixed-base root invariant failed at "
                    f"{label}: translation_delta_mm="
                    f"{result['translation_delta_mm']:.9f}, "
                    "orientation_delta_deg="
                    f"{result['orientation_delta_deg']:.9f}"
                )
            return result

        if fixed_base_replay_plan is not None:
            observe_root_invariant("ADMISSION")
        scene_query = get_physx_scene_query_interface()
        observed_samples = []
        geometry_capture_samples = []
        all_pairs: set[tuple[str, str]] = set()
        all_primitive_pairs: set[
            tuple[tuple[str, int], tuple[str, int]]
        ] = set()
        for sample in request["bounded_samples"]:
            desired = [
                sample["joint_positions_rad"][name] for name in request["joint_order"]
            ] + [0.0]
            if fixed_base_replay_plan is None:
                articulation.set_world_poses(
                    [base_translation], [base_quaternion_wxyz]
                )
            articulation.set_dof_positions([desired])
            update_count = (
                FIXED_BASE_SETTLE_UPDATE_COUNT
                if fixed_base_replay_plan is not None
                else 1
            )
            for _ in range(update_count):
                app.update()
            if fixed_base_replay_plan is not None:
                observe_root_invariant(
                    f"SAMPLE_{sample['sample_sequence']:04d}"
                )
            if sample["sample_sequence"] in geometry_capture_sequences:
                primitive_records = []
                for key in sorted(geometry_path_by_primitive):
                    path = geometry_path_by_primitive[key]
                    primitive = primitive_document_by_key[key]
                    world = UsdGeom.Xformable(
                        stage.GetPrimAtPath(path)
                    ).ComputeLocalToWorldTransform(0.0)
                    rigid_world = world.RemoveScaleShear()
                    translation = rigid_world.ExtractTranslation()
                    rotation = rigid_world.ExtractRotationMatrix()
                    canonical_rotation = canonical_active_rotation_row_major_from_gf_rows(
                        [
                            [float(rotation[row][column]) for column in range(3)]
                            for row in range(3)
                        ]
                    )
                    primitive_records.append({
                        "body_id": key[0],
                        "primitive_index": key[1],
                        "kind": primitive["kind"],
                        "half_extents_mm": primitive["half_extents_mm"],
                        "local_center_mm": primitive["center_mm"],
                        "local_rotation_row_major": primitive["rotation_row_major"],
                        "world_matrix_row_major": [
                            canonical_rotation[0],
                            canonical_rotation[1],
                            canonical_rotation[2],
                            float(translation[0]) * 1000.0,
                            canonical_rotation[3],
                            canonical_rotation[4],
                            canonical_rotation[5],
                            float(translation[1]) * 1000.0,
                            canonical_rotation[6],
                            canonical_rotation[7],
                            canonical_rotation[8],
                            float(translation[2]) * 1000.0,
                            0.0,
                            0.0,
                            0.0,
                            1.0,
                        ],
                    })
                geometry_capture_samples.append({
                    "candidate_id": geometry_capture_candidate["candidate_id"],
                    "sample_sequence": sample["sample_sequence"],
                    "sample_id": sample["sample_id"],
                    "primitives": primitive_records,
                })
            sample_pairs: set[tuple[str, str]] = set()
            sample_primitive_pairs: set[
                tuple[tuple[str, int], tuple[str, int]]
            ] = set()
            for query_path, query_body, query_primitive_index in query_paths:
                hits: list[tuple[str, int]] = []

                def report_hit(hit: Any) -> bool:
                    collision_path = str(getattr(hit, "collision", ""))
                    rigid_path = str(getattr(hit, "rigid_body", ""))
                    other = collision_path_to_primitive.get(collision_path)
                    if other is None:
                        other = collision_path_to_primitive.get(rigid_path)
                    if other is not None and other[0] != query_body:
                        hits.append(other)
                    return True

                encoded = PhysicsSchemaTools.encodeSdfPath(query_path)
                scene_query.overlap_shape(encoded[0], encoded[1], report_hit, False)
                for other_body, other_primitive_index in hits:
                    sample_pairs.add(tuple(sorted((query_body, other_body))))
                    sample_primitive_pairs.add(tuple(sorted((
                        (query_body, query_primitive_index),
                        (other_body, other_primitive_index),
                    ))))
            all_pairs.update(sample_pairs)
            all_primitive_pairs.update(sample_primitive_pairs)
            observed_samples.append({
                "sample_sequence": sample["sample_sequence"],
                "sample_id": sample["sample_id"],
                "source_segment_index": sample["source_segment_index"],
                "joint_positions_rad": sample["joint_positions_rad"],
                "collision_pair_count": len(sample_pairs),
                "collision_pairs": [list(pair) for pair in sorted(sample_pairs)],
                "collision_primitive_pair_count": len(sample_primitive_pairs),
                "collision_primitive_pairs": [
                    {
                        "body_pair": [item[0] for item in pair],
                        "primitive_indices": [item[1] for item in pair],
                    }
                    for pair in sorted(sample_primitive_pairs)
                ],
            })
        timeline.stop()

        adjacent_pairs = {
            tuple(sorted(pair)) for pair in (
                ("robot:base_link", "robot:link1"),
                ("robot:link1", "robot:link2"),
                ("robot:link2", "robot:link3"),
                ("robot:link3", "robot:link4"),
                ("robot:link5", "robot:gripper"),
            )
        }
        accepted_exclusion_pairs = (
            {
                tuple(sorted(pair))
                for pair in accepted_pair_policy["accepted_exclusion_pairs"]
            }
            if accepted_pair_policy is not None
            else set()
        )
        physical_solid_pairs = {
            pair for pair in all_pairs
            if pair not in accepted_exclusion_pairs
            and any(
                body.startswith("workcell:")
                and not body.startswith("workcell:station:")
                for body in pair
            )
        }
        planning_envelope_pairs = {
            pair for pair in all_pairs
            if pair not in accepted_exclusion_pairs
            and any(body.startswith("workcell:station:") for body in pair)
        }
        remaining_unreviewed_pairs = (
            all_pairs
            - accepted_exclusion_pairs
            - physical_solid_pairs
            - planning_envelope_pairs
        )
        if accepted_pair_policy is not None:
            for sample in observed_samples:
                raw_pairs = {tuple(pair) for pair in sample["collision_pairs"]}
                sample["raw_collision_pair_count"] = sample.pop(
                    "collision_pair_count"
                )
                sample["raw_collision_pairs"] = sample.pop("collision_pairs")
                sample["raw_collision_primitive_pair_count"] = sample.pop(
                    "collision_primitive_pair_count"
                )
                sample["raw_collision_primitive_pairs"] = sample.pop(
                    "collision_primitive_pairs"
                )
                sample["policy_excluded_pair_count"] = len(
                    raw_pairs & accepted_exclusion_pairs
                )
                sample["policy_excluded_pairs"] = [
                    list(pair) for pair in sorted(raw_pairs & accepted_exclusion_pairs)
                ]
                sample["physical_solid_blocker_pairs"] = [
                    list(pair) for pair in sorted(raw_pairs & physical_solid_pairs)
                ]
                sample["planning_envelope_blocker_pairs"] = [
                    list(pair) for pair in sorted(raw_pairs & planning_envelope_pairs)
                ]
                sample["unreviewed_blocker_pairs"] = [
                    list(pair) for pair in sorted(raw_pairs & remaining_unreviewed_pairs)
                ]
                sample["remaining_blocker_pair_count"] = len(
                    raw_pairs - accepted_exclusion_pairs
                )
        sample_pair_field = (
            "raw_collision_pairs"
            if accepted_pair_policy is not None
            else "collision_pairs"
        )
        pair_sample_counts = {
            pair: sum(pair in {
                tuple(item) for item in sample[sample_pair_field]
            } for sample in observed_samples)
            for pair in all_pairs
        }
        pair_observations = [
            {
                "body_pair": list(pair),
                "sample_count": pair_sample_counts[pair],
                "persistent_across_all_samples": (
                    pair_sample_counts[pair] == len(observed_samples)
                ),
                "classification": (
                    "KINEMATIC_NEIGHBOR_EXCLUSION_REVIEW_REQUIRED"
                    if accepted_pair_policy is None and pair in adjacent_pairs
                    else "UNREVIEWED_COLLISION_OBSERVATION"
                    if accepted_pair_policy is None
                    else "ACCEPTED_DIAGNOSTIC_KINEMATIC_NEIGHBOR_EXCLUSION"
                    if pair in accepted_exclusion_pairs
                    else "KINEMATIC_NEIGHBOR_EXCLUSION_REVIEW_REQUIRED"
                    if pair in adjacent_pairs
                    else "PHYSICAL_SOLID_COLLISION_BLOCKER"
                    if pair in physical_solid_pairs
                    else "PLANNING_ENVELOPE_ROUTE_BLOCKER"
                    if pair in planning_envelope_pairs
                    else "UNREVIEWED_COLLISION_BLOCKER"
                ),
            }
            for pair in sorted(all_pairs)
        ]
        primitive_pair_sample_counts = {
            pair: sum(
                any(
                    tuple(zip(
                        item["body_pair"], item["primitive_indices"], strict=True
                    )) == pair
                    for item in sample[
                        "raw_collision_primitive_pairs"
                        if accepted_pair_policy is not None
                        else "collision_primitive_pairs"
                    ]
                )
                for sample in observed_samples
            )
            for pair in all_primitive_pairs
        }
        primitive_pair_observations = [
            {
                "body_pair": [item[0] for item in pair],
                "primitive_indices": [item[1] for item in pair],
                "sample_count": primitive_pair_sample_counts[pair],
                "persistent_across_all_samples": (
                    primitive_pair_sample_counts[pair] == len(observed_samples)
                ),
            }
            for pair in sorted(all_primitive_pairs)
        ]

        receipt: dict[str, Any] = {
            "schema": (
                STATE_POLICY_NATIVE_COLLISION_RECEIPT_SCHEMA
                if state_policy_fixed_base
                else REPRESENTATIVE_KEY_NATIVE_COLLISION_RECEIPT_SCHEMA
                if representative_fixed_base
                else TCP_FIXED_BASE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
                if fixed_base_replay_plan is not None
                else TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
                if station_route_predicate is not None
                else TCP_PRIMITIVE_ATTRIBUTED_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
                if accepted_pair_policy is not None
                else TCP_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
            ),
            "status": (
                "DIAGNOSTIC_BLOCKERS_OBSERVED"
                if accepted_pair_policy is not None and (
                    physical_solid_pairs
                    or planning_envelope_pairs
                    or remaining_unreviewed_pairs
                )
                else "DIAGNOSTIC_OVERLAPS_OBSERVED"
                if all_pairs else "DIAGNOSTIC_NO_OVERLAPS_OBSERVED"
            ),
            "evidence_class": "NATIVE_ISAAC_EXPLORATORY_COLLISION_DIAGNOSTIC_ONLY",
            "admission_sha256": admission["admission_sha256"],
            "source_bindings": {
                key: admission[key] for key in (
                    "request_sha256",
                    "ik_receipt_sha256",
                    "collision_candidate_sha256",
                    "virtual_profile_sha256",
                    "robot_import_receipt_sha256",
                    "robot_usd_sha256",
                    "toolchain_lock_sha256",
                )
            },
            "bounded_sample_count": len(observed_samples),
            "samples_with_overlaps": sum(
                item[
                    "raw_collision_pair_count"
                    if accepted_pair_policy is not None
                    else "collision_pair_count"
                ] > 0
                for item in observed_samples
            ),
            "unique_collision_pair_count": len(all_pairs),
            "unique_collision_pairs": [list(pair) for pair in sorted(all_pairs)],
            "pair_observations": pair_observations,
            "unique_collision_primitive_pair_count": len(all_primitive_pairs),
            "unique_collision_primitive_pairs": [
                {
                    "body_pair": [item[0] for item in pair],
                    "primitive_indices": [item[1] for item in pair],
                }
                for pair in sorted(all_primitive_pairs)
            ],
            "primitive_pair_observations": primitive_pair_observations,
            "samples": observed_samples,
            "collision_screening_executed": True,
            "installed_collision_qualified": False,
            "continuous_collision_proven": False,
            "native_contact_replay_authorized": False,
            "candidate_blockers": collision_candidate["blockers"],
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "gate_promotions": [],
            "limitations": admission["limitations"] + [
                (
                    "accepted_adjacent_link_pairs_are_excluded_from_blocker_counts_only"
                    if accepted_pair_policy is not None
                    else "adjacent_link_pairs_are_retained_without_policy_exclusion"
                ),
                "overlap_results_do_not_measure_clearance_distance",
            ],
        }
        if accepted_pair_policy is not None:
            receipt["source_bindings"]["collision_pair_policy_sha256"] = admission[
                "collision_pair_policy_sha256"
            ]
            receipt.update({
                "collision_pair_policy_applied": True,
                "policy_excluded_pair_count": len(accepted_exclusion_pairs),
                "policy_excluded_pairs": [
                    list(pair) for pair in sorted(accepted_exclusion_pairs)
                ],
                "physical_solid_blocker_pair_count": len(physical_solid_pairs),
                "physical_solid_blocker_pairs": [
                    list(pair) for pair in sorted(physical_solid_pairs)
                ],
                "planning_envelope_blocker_pair_count": len(
                    planning_envelope_pairs
                ),
                "planning_envelope_blocker_pairs": [
                    list(pair) for pair in sorted(planning_envelope_pairs)
                ],
                "unreviewed_blocker_pair_count": len(remaining_unreviewed_pairs),
                "unreviewed_blocker_pairs": [
                    list(pair) for pair in sorted(remaining_unreviewed_pairs)
                ],
            })
        if station_route_predicate is not None:
            receipt["source_bindings"]["station_route_predicate_sha256"] = admission[
                "station_route_predicate_sha256"
            ]
            receipt.update({
                "station_route_predicate_applied": True,
                "physx_excluded_station_region_ids": admission[
                    "physx_excluded_station_region_ids"
                ],
                "physical_workcell_body_ids": admission[
                    "physical_workcell_body_ids"
                ],
            })
        if fixed_base_replay_plan is not None:
            receipt["source_bindings"]["fixed_base_replay_plan_sha256"] = (
                fixed_base_replay_plan["plan_sha256"]
            )
            receipt.update({
                "fixed_base_replay_applied": True,
                "fixed_base_mechanism": fixed_base_replay_plan[
                    "fixed_base_contract"
                ]["mechanism"],
                "fixed_base_settle_update_count": (
                    FIXED_BASE_SETTLE_UPDATE_COUNT
                ),
                "fixed_base_solver_position_iteration_count": (
                    FIXED_BASE_SOLVER_POSITION_ITERATION_COUNT
                ),
                "fixed_base_solver_velocity_iteration_count": (
                    FIXED_BASE_SOLVER_VELOCITY_ITERATION_COUNT
                ),
                "root_pose_invariant": {
                    "status": "PASS",
                    "observation_count": len(root_invariant_records),
                    "expected_observation_count": len(observed_samples) + 1,
                    "maximum_translation_delta_mm": max(
                        item["translation_delta_mm"]
                        for item in root_invariant_records
                    ),
                    "maximum_orientation_delta_deg": max(
                        item["orientation_delta_deg"]
                        for item in root_invariant_records
                    ),
                    "translation_tolerance_mm": root_contract[
                        "translation_tolerance_mm"
                    ],
                    "orientation_tolerance_deg": root_contract[
                        "orientation_tolerance_deg"
                    ],
                    "observations": root_invariant_records,
                },
                "rotation_serialization": fixed_base_replay_plan[
                    "rotation_serialization"
                ],
            })
            if representative_fixed_base:
                receipt.update({
                    "representative_target_id": fixed_base_replay_plan[
                        "target_id"
                    ],
                    "source_arm215_campaign_sha256": fixed_base_replay_plan[
                        "source_arm215_campaign_sha256"
                    ],
                    "source_arm215_target_plan_sha256": fixed_base_candidate[
                        "source_arm215_target_plan_sha256"
                    ],
                    "source_representative_plan_mutated": False,
                })
                if state_policy_fixed_base:
                    receipt.update({
                        "state_policy_episode_id": request[
                            "state_policy_episode_id"
                        ],
                        "state_policy_target_id": request[
                            "state_policy_target_id"
                        ],
                        "source_state_policy_request_sha256": request[
                            "source_state_policy_request_sha256"
                        ],
                        "source_runtime_revalidation_receipt_sha256": request[
                            "source_runtime_revalidation_receipt_sha256"
                        ],
                    })
            else:
                receipt.update({
                    "source_v4_native_receipt_sha256": fixed_base_candidate[
                        "source_v4_native_receipt_sha256"
                    ],
                    "source_v4_receipt_mutated": False,
                })
            if len(root_invariant_records) != len(observed_samples) + 1:
                raise RuntimeError("fixed-base root invariant coverage changed")
            receipt["limitations"].append(
                "fixed_base_discrete_overlap_replay_is_not_continuous_clearance_proof"
            )
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        if geometry_capture_plan is not None:
            if (
                receipt["receipt_sha256"]
                != geometry_capture_candidate["native_receipt_sha256"]
                or {item["sample_sequence"] for item in geometry_capture_samples}
                != geometry_capture_sequences
            ):
                raise MechanicsContractError(
                    "collision geometry capture does not reproduce the retained receipt"
                )
            geometry_capture: dict[str, Any] = {
                "schema": "tactevra.isaac_lm1_collision_geometry_capture.v1",
                "source": "NATIVE_PHYSX",
                "source_plan_sha256": geometry_capture_plan["plan_sha256"],
                "source_native_receipt_sha256": receipt["receipt_sha256"],
                "source_collision_candidate_sha256": collision_candidate[
                    "candidate_sha256"
                ],
                "samples": geometry_capture_samples,
                "hardware_access": False,
                "physical_authority": False,
                "controller_commands": [],
                "hardware_writes": 0,
                "physical_movements": 0,
            }
            geometry_capture["capture_sha256"] = _canonical_sha256(geometry_capture)
            geometry_capture_output_path.parent.mkdir(parents=True, exist_ok=True)
            geometry_capture_output_path.write_text(
                json.dumps(geometry_capture, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        output_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        status_path.write_text(json.dumps({
            "status": receipt["status"],
            "receipt_sha256": receipt["receipt_sha256"],
            "bounded_sample_count": receipt["bounded_sample_count"],
            "samples_with_overlaps": receipt["samples_with_overlaps"],
            "unique_collision_pair_count": receipt["unique_collision_pair_count"],
            "policy_excluded_pair_count": receipt.get("policy_excluded_pair_count", 0),
            "physical_solid_blocker_pair_count": receipt.get(
                "physical_solid_blocker_pair_count", 0
            ),
            "planning_envelope_blocker_pair_count": receipt.get(
                "planning_envelope_blocker_pair_count", 0
            ),
        }, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException as exc:
        status_path.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()


def build_collision_pair_policy_proposal(
    diagnostic_receipt: dict[str, Any],
    collision_candidate: dict[str, Any],
) -> dict[str, Any]:
    """Classify retained overlaps without applying an exclusion policy."""
    claimed_receipt_hash = diagnostic_receipt.get("receipt_sha256")
    unsigned_receipt = dict(diagnostic_receipt)
    unsigned_receipt.pop("receipt_sha256", None)
    if claimed_receipt_hash != _canonical_sha256(unsigned_receipt):
        raise MechanicsContractError("collision diagnostic receipt hash mismatch")
    if (
        diagnostic_receipt.get("schema") != TCP_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
        or diagnostic_receipt.get("status") != "DIAGNOSTIC_OVERLAPS_OBSERVED"
        or diagnostic_receipt.get("collision_screening_executed") is not True
        or diagnostic_receipt.get("installed_collision_qualified") is not False
        or diagnostic_receipt.get("continuous_collision_proven") is not False
        or diagnostic_receipt.get("gate_promotions") != []
    ):
        raise MechanicsContractError("collision diagnostic receipt boundary changed")
    claimed_candidate_hash = collision_candidate.get("candidate_sha256")
    unsigned_candidate = dict(collision_candidate)
    unsigned_candidate.pop("candidate_sha256", None)
    if claimed_candidate_hash != _canonical_sha256(unsigned_candidate):
        raise MechanicsContractError("pair-policy collision candidate hash mismatch")
    if (
        diagnostic_receipt.get("source_bindings", {}).get(
            "collision_candidate_sha256"
        ) != claimed_candidate_hash
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
    ):
        raise MechanicsContractError("diagnostic and collision candidate differ")

    observations = diagnostic_receipt.get("pair_observations")
    if (
        not isinstance(observations, list)
        or len(observations) != diagnostic_receipt.get("unique_collision_pair_count")
        or not observations
    ):
        raise MechanicsContractError("diagnostic pair observations are absent")
    adjacent_pairs = {
        tuple(sorted(pair)) for pair in (
            ("robot:base_link", "robot:link1"),
            ("robot:link1", "robot:link2"),
            ("robot:link2", "robot:link3"),
            ("robot:link3", "robot:link4"),
            ("robot:link5", "robot:gripper"),
        )
    }
    candidate_ids = {
        body["body_id"]
        for body in collision_candidate["robot_bodies"]
        + collision_candidate["workcell_bodies"]
    }
    classified = []
    seen: set[tuple[str, str]] = set()
    for observation in observations:
        body_pair = observation.get("body_pair")
        if not isinstance(body_pair, list) or len(body_pair) != 2:
            raise MechanicsContractError("diagnostic body pair is invalid")
        pair = tuple(sorted(body_pair))
        if pair in seen or any(body not in candidate_ids for body in pair):
            raise MechanicsContractError("diagnostic body pair coverage is invalid")
        seen.add(pair)
        sample_count = observation.get("sample_count")
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count < 1
            or sample_count > diagnostic_receipt["bounded_sample_count"]
        ):
            raise MechanicsContractError("diagnostic pair sample count is invalid")
        if pair in adjacent_pairs:
            disposition = "PROPOSED_KINEMATIC_NEIGHBOR_EXCLUSION"
            justification = "DIRECTLY_CONNECTED_URDF_BODIES"
        elif any(body.startswith("workcell:station:") for body in pair):
            disposition = "PLANNING_ENVELOPE_ROUTE_BLOCKER"
            justification = "STATION_AABB_IS_A_PLANNING_ENVELOPE_NOT_A_PHYSICAL_SOLID"
        elif any(body.startswith("workcell:") for body in pair):
            disposition = "PHYSICAL_SOLID_COLLISION_OBSERVATION"
            justification = "BOARD_DEVICE_OR_OTHER_PHYSICAL_WORKCELL_SOLID"
        else:
            disposition = "UNREVIEWED_SELF_COLLISION_OBSERVATION"
            justification = "NONADJACENT_ROBOT_PAIR_REQUIRES_GEOMETRY_REVIEW"
        classified.append({
            "body_pair": list(pair),
            "sample_count": sample_count,
            "persistent_across_all_samples": (
                sample_count == diagnostic_receipt["bounded_sample_count"]
            ),
            "proposed_disposition": disposition,
            "justification": justification,
        })
    if not adjacent_pairs.issubset(seen):
        raise MechanicsContractError("diagnostic lacks a required adjacent-link observation")

    proposal: dict[str, Any] = {
        "schema": "tactevra.isaac_lm1_collision_pair_policy_proposal.v1",
        "status": "REVIEW_REQUIRED_COLLISION_PAIR_POLICY",
        "source_diagnostic_receipt_sha256": claimed_receipt_hash,
        "collision_candidate_sha256": claimed_candidate_hash,
        "bounded_sample_count": diagnostic_receipt["bounded_sample_count"],
        "classified_pair_count": len(classified),
        "pair_classifications": sorted(classified, key=lambda item: item["body_pair"]),
        "proposed_exclusion_pairs": [
            list(pair) for pair in sorted(adjacent_pairs)
        ],
        "proposed_exclusion_count": len(adjacent_pairs),
        "policy_applied": False,
        "installed_profile_eligible": False,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "candidate_blockers": collision_candidate["blockers"],
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "next_required_stage": (
            "REVIEW_PAIR_DISPOSITIONS_THEN_RERUN_NATIVE_DIAGNOSTIC_WITH_HASH_BOUND_POLICY"
        ),
        "limitations": [
            "proposal_is_unapplied_and_cannot_suppress_any_collision_observation",
            "station_envelopes_remain_route_blockers_even_when_not_physical_solids",
            "physical_solid_observations_remain_collision_blockers",
            "missing_candidate_geometry_and_continuous_clearance_remain_blockers",
        ],
    }
    proposal["proposal_sha256"] = _canonical_sha256(proposal)
    return proposal


def accept_collision_pair_policy_proposal(
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Accept only the proposed directly connected pairs for diagnostics."""
    claimed_proposal_hash = proposal.get("proposal_sha256")
    unsigned_proposal = dict(proposal)
    unsigned_proposal.pop("proposal_sha256", None)
    if claimed_proposal_hash != _canonical_sha256(unsigned_proposal):
        raise MechanicsContractError("collision pair proposal hash mismatch")
    if (
        proposal.get("schema")
        != "tactevra.isaac_lm1_collision_pair_policy_proposal.v1"
        or proposal.get("status") != "REVIEW_REQUIRED_COLLISION_PAIR_POLICY"
        or proposal.get("policy_applied") is not False
        or proposal.get("installed_profile_eligible") is not False
        or proposal.get("gate_promotions") != []
    ):
        raise MechanicsContractError("collision pair proposal boundary changed")
    expected_pairs = {
        tuple(sorted(pair)) for pair in (
            ("robot:base_link", "robot:link1"),
            ("robot:link1", "robot:link2"),
            ("robot:link2", "robot:link3"),
            ("robot:link3", "robot:link4"),
            ("robot:link5", "robot:gripper"),
        )
    }
    proposed_pairs = {
        tuple(sorted(pair)) for pair in proposal.get("proposed_exclusion_pairs", [])
    }
    if proposed_pairs != expected_pairs or proposal.get(
        "proposed_exclusion_count"
    ) != len(expected_pairs):
        raise MechanicsContractError("proposal changed the direct-neighbor exclusion set")
    classifications = proposal.get("pair_classifications")
    if not isinstance(classifications, list) or len(classifications) != proposal.get(
        "classified_pair_count"
    ):
        raise MechanicsContractError("proposal pair classifications are absent")
    for row in classifications:
        pair = tuple(sorted(row.get("body_pair", [])))
        disposition = row.get("proposed_disposition")
        if pair in expected_pairs:
            if (
                disposition != "PROPOSED_KINEMATIC_NEIGHBOR_EXCLUSION"
                or row.get("justification") != "DIRECTLY_CONNECTED_URDF_BODIES"
                or row.get("persistent_across_all_samples") is not True
            ):
                raise MechanicsContractError("adjacent-pair proposal evidence changed")
        elif disposition == "PROPOSED_KINEMATIC_NEIGHBOR_EXCLUSION":
            raise MechanicsContractError("proposal attempts to exclude a nonadjacent pair")

    policy: dict[str, Any] = {
        "schema": TCP_COLLISION_POLICY_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY",
        "source_proposal_sha256": claimed_proposal_hash,
        "source_diagnostic_receipt_sha256": proposal[
            "source_diagnostic_receipt_sha256"
        ],
        "collision_candidate_sha256": proposal["collision_candidate_sha256"],
        "accepted_exclusion_pairs": [list(pair) for pair in sorted(expected_pairs)],
        "accepted_exclusion_count": len(expected_pairs),
        "acceptance_basis": (
            "USER_AUTHORIZED_NEXT_SIMULATION_STEPS_AFTER_REVIEW_SUMMARY"
        ),
        "diagnostic_policy_active": True,
        "installed_profile_active": False,
        "installed_profile_eligible": False,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "physical_solid_pairs_excluded": [],
        "planning_envelope_pairs_excluded": [],
        "candidate_blockers": proposal["candidate_blockers"],
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "accepted_exclusions_are_limited_to_directly_connected_robot_bodies",
            "policy_is_active_only_for_zero_authority_diagnostic_reporting",
            "physical_solid_and_planning_envelope_observations_remain_blockers",
            "policy_does_not_install_geometry_or_prove_continuous_clearance",
        ],
    }
    policy["policy_sha256"] = _canonical_sha256(policy)
    return policy


def bind_collision_pair_policy_request(
    request: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """Bind an accepted diagnostic-only pair policy to the exact sample request."""
    claimed_request_hash = request.get("request_sha256")
    unsigned_request = dict(request)
    unsigned_request.pop("request_sha256", None)
    if claimed_request_hash != _canonical_sha256(unsigned_request):
        raise MechanicsContractError("collision request hash mismatch")
    if (
        request.get("schema") != TCP_COLLISION_REPLAY_REQUEST_SCHEMA
        or request.get("status") != "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC"
        or request.get("diagnostic_only") is not True
        or request.get("installed_collision_qualified") is not False
    ):
        raise MechanicsContractError("collision request cannot accept a pair policy")
    claimed_policy_hash = policy.get("policy_sha256")
    unsigned_policy = dict(policy)
    unsigned_policy.pop("policy_sha256", None)
    if claimed_policy_hash != _canonical_sha256(unsigned_policy):
        raise MechanicsContractError("accepted collision pair policy hash mismatch")
    if (
        policy.get("schema") != TCP_COLLISION_POLICY_SCHEMA
        or policy.get("status") != "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY"
        or policy.get("diagnostic_policy_active") is not True
        or policy.get("installed_profile_active") is not False
        or policy.get("installed_profile_eligible") is not False
        or policy.get("physical_solid_pairs_excluded") != []
        or policy.get("planning_envelope_pairs_excluded") != []
        or policy.get("gate_promotions") != []
    ):
        raise MechanicsContractError("accepted pair policy boundary changed")
    if request.get("collision_candidate_sha256") != policy.get(
        "collision_candidate_sha256"
    ):
        raise MechanicsContractError("pair policy and collision candidate differ")

    bound = dict(unsigned_request)
    bound.update({
        "schema": TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA,
        "source_unfiltered_request_sha256": claimed_request_hash,
        "collision_pair_policy_sha256": claimed_policy_hash,
        "collision_pair_policy_scope": "DIAGNOSTIC_REPORTING_ONLY",
        "diagnostic_only": True,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "native_contact_replay_authorized": False,
        "next_required_stage": (
            "RUN_SELECTED_ISAAC_POLICY_BOUND_DIAGNOSTIC_AND_RETAIN_RAW_AND_FILTERED_PAIRS"
        ),
        "limitations": request["limitations"] + [
            "pair_policy_changes_diagnostic_classification_not_raw_overlap_observations",
            "physical_solid_and_planning_envelope_observations_remain_blockers",
        ],
    })
    bound["request_sha256"] = _canonical_sha256(bound)
    return bound


def _contiguous_integer_ranges(values: Iterable[int]) -> list[dict[str, int]]:
    ordered = sorted(set(values))
    if not ordered:
        return []
    ranges: list[dict[str, int]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value != previous + 1:
            ranges.append({"start": start, "end": previous})
            start = value
        previous = value
    ranges.append({"start": start, "end": previous})
    return ranges


def build_collision_blocker_localization(
    diagnostic_receipt: dict[str, Any],
    collision_request: dict[str, Any],
    cartesian_request: dict[str, Any],
) -> dict[str, Any]:
    """Bind remaining collision blockers to their exact trajectory context."""
    documents = (
        (diagnostic_receipt, "receipt_sha256", "collision diagnostic receipt"),
        (collision_request, "request_sha256", "collision request"),
        (cartesian_request, "request_sha256", "Cartesian request"),
    )
    claimed_hashes: dict[str, str] = {}
    for document, hash_field, label in documents:
        claimed = document.get(hash_field)
        unsigned = dict(document)
        unsigned.pop(hash_field, None)
        if claimed != _canonical_sha256(unsigned):
            raise MechanicsContractError(f"{label} hash mismatch")
        claimed_hashes[label] = claimed
    if (
        diagnostic_receipt.get("schema") not in {
            TCP_POLICY_BOUND_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
            TCP_PRIMITIVE_ATTRIBUTED_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
            TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
        }
        or diagnostic_receipt.get("status") != "DIAGNOSTIC_BLOCKERS_OBSERVED"
        or diagnostic_receipt.get("collision_pair_policy_applied") is not True
        or diagnostic_receipt.get("installed_collision_qualified") is not False
        or diagnostic_receipt.get("continuous_collision_proven") is not False
        or diagnostic_receipt.get("gate_promotions") != []
    ):
        raise MechanicsContractError("collision diagnostic localization boundary changed")
    if (
        collision_request.get("schema") != TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA
        or collision_request.get("status")
        != "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC"
        or collision_request.get("diagnostic_only") is not True
        or collision_request.get("installed_collision_qualified") is not False
        or collision_request.get("continuous_collision_proven") is not False
        or diagnostic_receipt.get("source_bindings", {}).get("request_sha256")
        != claimed_hashes["collision request"]
    ):
        raise MechanicsContractError("diagnostic and collision request differ")
    if (
        cartesian_request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA
        or cartesian_request.get("status") != "READY_FOR_IK_QUALIFICATION"
        or collision_request.get("source_request_sha256")
        != claimed_hashes["Cartesian request"]
        or cartesian_request.get("hardware_access") is not False
        or cartesian_request.get("hardware_writes") != 0
        or cartesian_request.get("physical_movements") != 0
    ):
        raise MechanicsContractError("collision and Cartesian request lineage differs")

    bounded_samples = collision_request.get("bounded_samples")
    observed_samples = diagnostic_receipt.get("samples")
    cartesian_samples = cartesian_request.get("samples")
    if (
        not isinstance(bounded_samples, list)
        or not isinstance(observed_samples, list)
        or not isinstance(cartesian_samples, list)
        or len(bounded_samples) != collision_request.get("bounded_sample_count")
        or len(observed_samples) != diagnostic_receipt.get("bounded_sample_count")
        or len(bounded_samples) != len(observed_samples)
        or len(cartesian_samples) != cartesian_request.get("sample_count")
    ):
        raise MechanicsContractError("collision localization sample coverage differs")

    pair_samples: dict[tuple[str, str], list[dict[str, Any]]] = {}
    pair_classes: dict[tuple[str, str], str] = {}
    primitive_attribution = (
        diagnostic_receipt["schema"]
        == TCP_PRIMITIVE_ATTRIBUTED_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA
    )
    pair_primitive_samples: dict[
        tuple[str, str], dict[tuple[int, int], list[int]]
    ] = {}
    for sequence, (bounded, observed) in enumerate(zip(
        bounded_samples, observed_samples, strict=True
    )):
        if (
            bounded.get("sample_sequence") != sequence
            or observed.get("sample_sequence") != sequence
            or observed.get("sample_id") != bounded.get("sample_id")
            or observed.get("source_segment_index")
            != bounded.get("source_segment_index")
            or observed.get("joint_positions_rad")
            != bounded.get("joint_positions_rad")
        ):
            raise MechanicsContractError("diagnostic sample lineage differs")
        segment_index = bounded.get("source_segment_index")
        if (
            not isinstance(segment_index, int)
            or isinstance(segment_index, bool)
            or segment_index < 0
            or segment_index >= len(cartesian_samples)
        ):
            raise MechanicsContractError("collision source segment is invalid")
        context = cartesian_samples[segment_index]
        for field in ("sequence", "phase", "expected_tool_tip_board_mm"):
            if field not in context:
                raise MechanicsContractError("Cartesian sample context is incomplete")
        if context["sequence"] != segment_index:
            raise MechanicsContractError("Cartesian sample sequence differs")
        if primitive_attribution:
            primitive_pairs = observed.get("raw_collision_primitive_pairs")
            raw_body_pairs = observed.get("raw_collision_pairs")
            if (
                not isinstance(primitive_pairs, list)
                or observed.get("raw_collision_primitive_pair_count")
                != len(primitive_pairs)
                or not isinstance(raw_body_pairs, list)
            ):
                raise MechanicsContractError(
                    "diagnostic primitive attribution coverage differs"
                )
            seen_primitive_pairs: set[
                tuple[tuple[str, str], tuple[int, int]]
            ] = set()
            for primitive_pair in primitive_pairs:
                body_pair = primitive_pair.get("body_pair")
                indices = primitive_pair.get("primitive_indices")
                if (
                    not isinstance(body_pair, list)
                    or len(body_pair) != 2
                    or body_pair != sorted(body_pair)
                    or not isinstance(indices, list)
                    or len(indices) != 2
                    or any(
                        not isinstance(value, int)
                        or isinstance(value, bool)
                        or value < 0
                        for value in indices
                    )
                ):
                    raise MechanicsContractError(
                        "diagnostic primitive attribution is invalid"
                    )
                key = (tuple(body_pair), tuple(indices))
                if body_pair not in raw_body_pairs:
                    raise MechanicsContractError(
                        "primitive attribution lacks its body-pair observation"
                    )
                if key in seen_primitive_pairs:
                    raise MechanicsContractError(
                        "diagnostic sample duplicates a primitive pair"
                    )
                seen_primitive_pairs.add(key)
                pair_primitive_samples.setdefault(tuple(body_pair), {}).setdefault(
                    tuple(indices), []
                ).append(sequence)
        for field, blocker_class in (
            ("physical_solid_blocker_pairs", "PHYSICAL_SOLID_COLLISION_BLOCKER"),
            ("planning_envelope_blocker_pairs", "PLANNING_ENVELOPE_ROUTE_BLOCKER"),
            ("unreviewed_blocker_pairs", "UNREVIEWED_COLLISION_BLOCKER"),
        ):
            pairs = observed.get(field)
            if not isinstance(pairs, list):
                raise MechanicsContractError("diagnostic blocker sample field is absent")
            seen_sample_pairs: set[tuple[str, str]] = set()
            for body_pair in pairs:
                if not isinstance(body_pair, list) or len(body_pair) != 2:
                    raise MechanicsContractError("diagnostic blocker pair is invalid")
                pair = tuple(sorted(body_pair))
                if pair in seen_sample_pairs:
                    raise MechanicsContractError("diagnostic sample duplicates a blocker pair")
                seen_sample_pairs.add(pair)
                previous_class = pair_classes.setdefault(pair, blocker_class)
                if previous_class != blocker_class:
                    raise MechanicsContractError("diagnostic blocker class changed by sample")
                pair_samples.setdefault(pair, []).append({
                    "sample_sequence": sequence,
                    "sample_id": bounded["sample_id"],
                    "source_segment_index": segment_index,
                    "interpolation_ratio": bounded["interpolation_ratio"],
                    "cartesian_sequence": context["sequence"],
                    "action_index": context.get("action_index"),
                    "phase": context["phase"],
                    "target_id": context.get("target_id"),
                    "phase_endpoint": context.get("phase_endpoint"),
                    "expected_tool_tip_board_mm": context[
                        "expected_tool_tip_board_mm"
                    ],
                })

    expected_pairs: dict[tuple[str, str], str] = {}
    for field, blocker_class in (
        ("physical_solid_blocker_pairs", "PHYSICAL_SOLID_COLLISION_BLOCKER"),
        ("planning_envelope_blocker_pairs", "PLANNING_ENVELOPE_ROUTE_BLOCKER"),
        ("unreviewed_blocker_pairs", "UNREVIEWED_COLLISION_BLOCKER"),
    ):
        pairs = diagnostic_receipt.get(field)
        if not isinstance(pairs, list):
            raise MechanicsContractError("diagnostic blocker summary is absent")
        for body_pair in pairs:
            pair = tuple(sorted(body_pair))
            if pair in expected_pairs:
                raise MechanicsContractError("diagnostic blocker summary duplicates a pair")
            expected_pairs[pair] = blocker_class
        count_field = field.removesuffix("_pairs") + "_pair_count"
        if diagnostic_receipt.get(count_field) != len(pairs):
            raise MechanicsContractError("diagnostic blocker summary count differs")
    if expected_pairs != pair_classes or not pair_samples:
        raise MechanicsContractError("diagnostic blocker summary and samples differ")
    if primitive_attribution:
        unique_primitive_pairs = diagnostic_receipt.get(
            "unique_collision_primitive_pairs"
        )
        primitive_observations = diagnostic_receipt.get(
            "primitive_pair_observations"
        )
        if (
            not isinstance(unique_primitive_pairs, list)
            or diagnostic_receipt.get("unique_collision_primitive_pair_count")
            != len(unique_primitive_pairs)
            or not isinstance(primitive_observations, list)
        ):
            raise MechanicsContractError(
                "diagnostic primitive attribution summary differs"
            )

        def primitive_key(item: dict[str, Any]) -> tuple[tuple[str, str], tuple[int, int]]:
            body_pair = item.get("body_pair")
            indices = item.get("primitive_indices")
            if (
                not isinstance(body_pair, list)
                or len(body_pair) != 2
                or body_pair != sorted(body_pair)
                or not isinstance(indices, list)
                or len(indices) != 2
                or any(
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 0
                    for value in indices
                )
            ):
                raise MechanicsContractError(
                    "diagnostic primitive attribution summary is invalid"
                )
            return tuple(body_pair), tuple(indices)

        derived_primitive_counts = {
            (body_pair, indices): len(sample_sequences)
            for body_pair, index_rows in pair_primitive_samples.items()
            for indices, sample_sequences in index_rows.items()
        }
        summary_keys = [primitive_key(item) for item in unique_primitive_pairs]
        observation_counts = {
            primitive_key(item): item.get("sample_count")
            for item in primitive_observations
        }
        if (
            len(set(summary_keys)) != len(summary_keys)
            or set(summary_keys) != set(derived_primitive_counts)
            or observation_counts != derived_primitive_counts
        ):
            raise MechanicsContractError(
                "diagnostic primitive attribution and samples differ"
            )

    localizations = []
    for pair in sorted(pair_samples):
        rows = pair_samples[pair]
        phase_counts: dict[str, int] = {}
        target_counts: dict[str, int] = {}
        for row in rows:
            phase = row["phase"]
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            target = row["target_id"] if row["target_id"] is not None else "NONE"
            target_counts[target] = target_counts.get(target, 0) + 1
        blocker_class = pair_classes[pair]
        primitive_localizations = [
            {
                "primitive_indices": list(indices),
                "sample_count": len(sample_sequences),
                "sample_sequence_ranges": _contiguous_integer_ranges(
                    sample_sequences
                ),
            }
            for indices, sample_sequences in sorted(
                pair_primitive_samples.get(pair, {}).items()
            )
        ]
        if primitive_attribution and not primitive_localizations:
            raise MechanicsContractError(
                "blocker lacks diagnostic primitive attribution"
            )
        localization = {
            "body_pair": list(pair),
            "blocker_class": blocker_class,
            "sample_count": len(rows),
            "sample_sequence_ranges": _contiguous_integer_ranges(
                row["sample_sequence"] for row in rows
            ),
            "source_segment_ranges": _contiguous_integer_ranges(
                row["source_segment_index"] for row in rows
            ),
            "phase_counts": dict(sorted(phase_counts.items())),
            "target_counts": dict(sorted(target_counts.items())),
            "samples": rows,
            "proposed_remediation": (
                "REFINE_CONSERVATIVE_ROBOT_GEOMETRY_THEN_REPLAN_IF_OVERLAP_PERSISTS"
                if blocker_class == "PHYSICAL_SOLID_COLLISION_BLOCKER"
                else "SEPARATE_PLANNING_REGION_FROM_PHYSX_SOLIDS_AND_ADD_ROUTE_PREDICATE"
                if blocker_class == "PLANNING_ENVELOPE_ROUTE_BLOCKER"
                else "REVIEW_BODY_SEMANTICS_AND_GEOMETRY_BEFORE_RERUN"
            ),
        }
        if primitive_attribution:
            localization["primitive_localizations"] = primitive_localizations
        localizations.append(localization)

    physical_robot_bodies = sorted({
        body for pair, blocker_class in pair_classes.items()
        if blocker_class == "PHYSICAL_SOLID_COLLISION_BLOCKER"
        for body in pair if body.startswith("robot:")
    })
    planning_regions = sorted({
        body for pair, blocker_class in pair_classes.items()
        if blocker_class == "PLANNING_ENVELOPE_ROUTE_BLOCKER"
        for body in pair if body.startswith("workcell:station:")
    })
    proposal: dict[str, Any] = {
        "schema": TCP_COLLISION_BLOCKER_LOCALIZATION_SCHEMA,
        "status": "REVIEW_REQUIRED_COLLISION_BLOCKER_REMEDIATION",
        "source_diagnostic_receipt_sha256": claimed_hashes[
            "collision diagnostic receipt"
        ],
        "source_collision_request_sha256": claimed_hashes["collision request"],
        "source_cartesian_request_sha256": claimed_hashes["Cartesian request"],
        "bounded_sample_count": len(observed_samples),
        "localized_blocker_pair_count": len(localizations),
        "physical_solid_blocker_pair_count": sum(
            item["blocker_class"] == "PHYSICAL_SOLID_COLLISION_BLOCKER"
            for item in localizations
        ),
        "planning_envelope_blocker_pair_count": sum(
            item["blocker_class"] == "PLANNING_ENVELOPE_ROUTE_BLOCKER"
            for item in localizations
        ),
        "unreviewed_blocker_pair_count": sum(
            item["blocker_class"] == "UNREVIEWED_COLLISION_BLOCKER"
            for item in localizations
        ),
        "physical_geometry_refinement_robot_bodies": physical_robot_bodies,
        "planning_region_bodies": planning_regions,
        "blocker_localizations": localizations,
        "proposal_applied": False,
        "installed_profile_eligible": False,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "next_required_stage": (
            "REVIEW_GEOMETRY_REFINEMENT_AND_PLANNING_REGION_SEPARATION_THEN_RERUN"
        ),
        "limitations": [
            "localization_uses_discrete_overlap_samples_not_continuous_clearance",
            "physical_overlap_may_reflect_conservative_axis_aligned_robot_boxes",
            "planning_regions_are_not_yet_evaluated_by_a_route_predicate",
            "proposal_does_not_change_geometry_route_or_collision_results",
        ],
    }
    if primitive_attribution:
        proposal.update({
            "source_collision_candidate_sha256": diagnostic_receipt[
                "source_bindings"
            ].get("collision_candidate_sha256"),
            "primitive_attribution_available": True,
            "localized_blocker_primitive_pair_count": sum(
                len(item["primitive_localizations"]) for item in localizations
            ),
        })
    proposal["proposal_sha256"] = _canonical_sha256(proposal)
    return proposal


def assess_native_key_trace(
    profile: dict[str, Any],
    native_samples: Iterable[dict[str, Any]],
    *,
    rest_key_z_m: float | None = None,
    target_id: str = "H",
) -> dict[str, Any]:
    """Convert native key displacement into the shared mechanism-state contract."""
    rows = list(native_samples)
    if len(rows) < 2:
        raise MechanicsContractError("native trace must contain at least two samples")
    regions = profile.get("regions", {})
    if target_id not in regions:
        raise MechanicsContractError(f"native trace target {target_id!r} is unavailable")
    rest_z = _finite_number(
        rows[0].get("key_center_z_m") if rest_key_z_m is None else rest_key_z_m,
        "native rest key z",
    )
    target_center = regions[target_id]["center_board_xy_mm"]
    contract_trace = []
    native_contact_steps = 0
    for index, row in enumerate(rows):
        key_z = _finite_number(row.get("key_center_z_m"), f"native sample {index} key z")
        separation = _finite_number(row.get("tip_key_separation_m"), f"native sample {index} separation")
        if separation <= 0.00005:
            native_contact_steps += 1
        contract_trace.append({
            "time_s": _finite_number(row.get("time_s"), f"native sample {index} time"),
            "tip_x_board_mm": target_center[0],
            "tip_y_board_mm": target_center[1],
            "compression_mm": max(0.0, (rest_z - key_z) * 1000.0),
        })
    result = evaluate_trace(profile, contract_trace)
    result["commanded_key"] = target_id
    result["native_contact_step_count"] = native_contact_steps
    result["native_contact_observed"] = native_contact_steps > 0
    result["native_trace_sample_count"] = len(rows)
    result["result_sha256"] = _canonical_sha256(
        {key: value for key, value in result.items() if key != "result_sha256"}
    )
    return result


def run_native_h_probe(
    layout_path: Path, *, output_path: Path | None = None, status_path: Path | None = None
) -> dict[str, Any]:
    """Run a zero-authority native Isaac prismatic-key contact replay."""
    profile = build_profile(layout_path)
    h_region = profile["regions"]["H"]
    prior = profile["mechanics_prior"]
    dt = 1.0 / 120.0
    key_half_x_m = h_region["half_extent_mm"][0] / 1000.0
    key_half_y_m = h_region["half_extent_mm"][1] / 1000.0
    key_half_z_m = 0.003
    key_top_z_m = profile["target_plane_z_board_mm"] / 1000.0
    key_center_z_m = key_top_z_m - key_half_z_m
    tip_radius_m = prior["tip_radius_mm"] / 1000.0
    trajectory = build_native_tip_trajectory(
        rest_top_z_m=key_top_z_m, tip_radius_m=tip_radius_m, dt=dt
    )
    app = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.usd
        import warp as wp
        from isaacsim.core.experimental.prims import RigidPrim
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import Gf, Sdf, UsdGeom, UsdPhysics

        omni.usd.get_context().new_stage()
        for _ in range(5):
            app.update()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        scene = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
        scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        # The provisional key mechanism represents the keyboard's preloaded
        # dome/scissor return, not a free keycap.  Isolate that one-dimensional
        # response from gravity until measured preload data is available.
        scene.CreateGravityMagnitudeAttr().Set(0.0)

        key_path = "/World/HKey"
        key_geom = UsdGeom.Cube.Define(stage, key_path)
        key_geom.CreateSizeAttr(2.0)
        key_xform = UsdGeom.Xformable(key_geom.GetPrim())
        key_xform.AddTranslateOp().Set(Gf.Vec3d(
            h_region["center_board_xy_mm"][0] / 1000.0,
            h_region["center_board_xy_mm"][1] / 1000.0,
            key_center_z_m,
        ))
        key_xform.AddScaleOp().Set(Gf.Vec3f(key_half_x_m, key_half_y_m, key_half_z_m))
        key_prim = key_geom.GetPrim()
        UsdPhysics.CollisionAPI.Apply(key_prim)
        UsdPhysics.RigidBodyAPI.Apply(key_prim)
        mass = UsdPhysics.MassAPI.Apply(key_prim)
        mass.CreateMassAttr().Set(prior["keycap_mass_kg"]["nominal"])

        joint = UsdPhysics.PrismaticJoint.Define(stage, "/World/HKeyJoint")
        joint.CreateBody1Rel().SetTargets([Sdf.Path(key_path)])
        joint.CreateAxisAttr().Set(UsdPhysics.Tokens.z)
        joint.CreateLocalPos0Attr().Set(Gf.Vec3f(
            h_region["center_board_xy_mm"][0] / 1000.0,
            h_region["center_board_xy_mm"][1] / 1000.0,
            key_center_z_m,
        ))
        joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
        joint.CreateLowerLimitAttr().Set(-prior["travel_mm"]["nominal"] / 1000.0)
        joint.CreateUpperLimitAttr().Set(0.0)
        drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "linear")
        drive.CreateTypeAttr().Set("force")
        drive.CreateTargetPositionAttr().Set(0.0)
        drive.CreateStiffnessAttr().Set(prior["stiffness_n_per_mm"]["nominal"] * 1000.0)
        drive.CreateDampingAttr().Set(prior["damping_n_s_per_mm"]["nominal"] * 1000.0)

        tip_path = "/World/VirtualTip"
        tip_geom = UsdGeom.Sphere.Define(stage, tip_path)
        tip_geom.CreateRadiusAttr().Set(tip_radius_m)
        tip_prim = tip_geom.GetPrim()
        UsdPhysics.CollisionAPI.Apply(tip_prim)
        tip_body = UsdPhysics.RigidBodyAPI.Apply(tip_prim)
        tip_body.CreateKinematicEnabledAttr().Set(True)
        UsdPhysics.MassAPI.Apply(tip_prim).CreateMassAttr().Set(0.02)

        SimulationManager.set_physics_dt(dt)
        SimulationManager.initialize_physics()
        key_view = RigidPrim(key_path)
        tip_view = RigidPrim(tip_path)
        x_m = h_region["center_board_xy_mm"][0] / 1000.0
        y_m = h_region["center_board_xy_mm"][1] / 1000.0
        tip_view.set_world_poses([[x_m, y_m, trajectory[0]["tip_z_m"]]], [[1.0, 0.0, 0.0, 0.0]])
        SimulationManager.step(steps=30)
        settled_z = float(key_view.get_world_poses()[0].numpy().tolist()[0][2])
        tip_device = tip_view._physics_rigid_body_view.get_transforms().device  # noqa: SLF001
        tip_indices = wp.array([0], dtype=wp.uint32, device=tip_device)

        native_samples = []
        for command in trajectory:
            # A kinematic target is consumed by the solver and therefore
            # transfers contact force.  set_world_poses would teleport the
            # sphere and can overlap the key without producing an impulse.
            tip_targets = wp.array(
                [[x_m, y_m, command["tip_z_m"], 0.0, 0.0, 0.0, 1.0]],
                dtype=wp.float32,
                device=tip_device,
            )
            tip_view._physics_rigid_body_view.set_kinematic_targets(  # noqa: SLF001
                tip_targets, tip_indices
            )
            SimulationManager.step(steps=1)
            observed_key_z = float(key_view.get_world_poses()[0].numpy().tolist()[0][2])
            key_top = observed_key_z + key_half_z_m
            tip_bottom = command["tip_z_m"] - tip_radius_m
            native_samples.append({
                "step": command["step"],
                "time_s": command["time_s"],
                "tip_center_z_m": command["tip_z_m"],
                "key_center_z_m": observed_key_z,
                "tip_key_separation_m": tip_bottom - key_top,
            })
        assessment = assess_native_key_trace(
            profile, native_samples, rest_key_z_m=settled_z
        )
        passed = assessment["accepted"] and assessment["resolved_key"] == "H" and assessment["native_contact_observed"]
        receipt: dict[str, Any] = {
            "schema": NATIVE_RECEIPT_SCHEMA,
            "status": "PASS" if passed else "BLOCKED_NATIVE_KEY_MECHANICS",
            "evidence_class": "PROVISIONAL_NATIVE_ISAAC_KEY_MECHANICS",
            "profile_sha256": profile["profile_sha256"],
            "layout_sha256": profile["provenance"]["layout_sha256"],
            "physics_dt_s": dt,
            "physics_steps": 30 + len(native_samples),
            "state_teleports_after_initialization": 0,
            "commanded_key": "H",
            "assessment": assessment,
            "native_trace": native_samples,
            "authority": dict(profile["authority"]),
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "isolated_native_key_and_virtual_tip_not_full_robot_contact",
                "gravity_disabled_to_model_preloaded_keyboard_return_mechanism",
                "synthetic_bounded_mechanics_priors_not_product_measurements",
                "no_physical_keyboard_controller_timing_torque_or_safety_authority",
            ],
        }
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        if output_path is not None:
            output_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if status_path is not None:
            status_path.write_text(json.dumps({
                "status": receipt["status"],
                "receipt_sha256": receipt["receipt_sha256"],
            }, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException as exc:
        if status_path is not None:
            status_path.write_text(json.dumps({
                "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
            }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()


def _validate_randomized_replay_parameters(value: object) -> dict[str, float]:
    expected = {
        "key_stiffness_n_per_m",
        "key_damping_n_s_per_m",
        "key_mass_kg",
        "keyboard_offset_x_mm",
        "keyboard_offset_y_mm",
        "keyboard_yaw_deg",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise MechanicsContractError(
            "randomized replay parameters differ from the LM3 contract"
        )
    return {
        name: _finite_number(value[name], f"randomized parameter {name}")
        for name in sorted(expected)
    }


def _randomized_keyboard_point_mm(
    point_xy_mm: list[float],
    *,
    offset_x_mm: float,
    offset_y_mm: float,
    yaw_deg: float,
) -> list[float]:
    """Apply the precommitted keyboard pose about the board-frame origin."""
    if len(point_xy_mm) != 2:
        raise MechanicsContractError("keyboard point must contain x and y")
    x = _finite_number(point_xy_mm[0], "keyboard point x")
    y = _finite_number(point_xy_mm[1], "keyboard point y")
    angle = math.radians(_finite_number(yaw_deg, "keyboard yaw"))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        cosine * x - sine * y + _finite_number(offset_x_mm, "keyboard x offset"),
        sine * x + cosine * y + _finite_number(offset_y_mm, "keyboard y offset"),
    ]


def _state_policy_trajectory_row(
    *,
    time_s: float,
    target: dict[str, Any],
    observed_joint_positions_rad: list[float],
    observed_joint_velocities_rad_s: list[float],
    key_center_z_m: float,
    tip_center_z_m: float,
    tip_key_separation_m: float,
) -> dict[str, Any]:
    """Build one self-describing LM4-ready simulation state/action row."""
    desired = target.get("joint_position_target_rad")
    if any(
        not isinstance(values, list) or len(values) != 6
        for values in (
            desired,
            observed_joint_positions_rad,
            observed_joint_velocities_rad_s,
        )
    ):
        raise MechanicsContractError(
            "state-policy rows require six commanded, observed, and velocity joints"
        )
    phase = target.get("phase")
    target_id = target.get("target_id")
    if not isinstance(phase, str) or not phase:
        raise MechanicsContractError("state-policy row phase is missing")
    if target_id not in REPRESENTATIVE_KEYS:
        raise MechanicsContractError("state-policy row target is undeclared")
    return {
        "schema": STATE_POLICY_TRAJECTORY_SCHEMA,
        "time_s": float(time_s),
        "target_id": target_id,
        "phase": phase,
        "action_index": target.get("action_index"),
        "target_sequence": target.get("sequence"),
        "joint_position_observed_rad": [
            float(value) for value in observed_joint_positions_rad
        ],
        "joint_velocity_observed_rad_s": [
            float(value) for value in observed_joint_velocities_rad_s
        ],
        "joint_position_target_rad": [float(value) for value in desired],
        "key_center_z_m": float(key_center_z_m),
        "tip_center_z_m": float(tip_center_z_m),
        "tip_key_separation_m": float(tip_key_separation_m),
    }


def validate_state_policy_native_mechanics_episode(
    manifest: dict[str, Any],
    plan: dict[str, Any],
    episode_id: str,
) -> dict[str, Any]:
    """Admit one ARM-224 plan for one fresh, zero-authority Isaac attempt."""
    _verify_lm3_digest(manifest, "manifest_sha256", "native mechanics manifest")
    _verify_lm3_digest(plan, "plan_sha256", "native mechanics plan")
    _require_lm3_zero_authority(manifest, "native mechanics manifest")
    _require_lm3_zero_authority(plan, "native mechanics plan")
    entries = manifest.get("entries")
    if (
        manifest.get("schema") != STATE_POLICY_NATIVE_MECHANICS_MANIFEST_SCHEMA
        or manifest.get("status")
        != "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_STATE_POLICY_MECHANICS_REPLAYS"
        or manifest.get("runtime_files_revalidated") is not True
        or manifest.get("isaac_started") is not False
        or manifest.get("gpu_started") is not False
        or manifest.get("mechanics_replays_executed") != 0
        or manifest.get("prior_mechanics_results_reused") is not False
        or not isinstance(entries, list)
        or not entries
        or len(entries) != manifest.get("episode_count")
    ):
        raise MechanicsContractError("state-policy mechanics manifest boundary changed")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("episode_id") == episode_id
    ]
    if len(matches) != 1:
        raise MechanicsContractError(
            "state-policy mechanics episode is absent or duplicated"
        )
    entry = matches[0]
    targets = plan.get("joint_targets")
    endpoints = plan.get("contact_endpoint_sequences")
    if (
        plan.get("schema") != STATE_POLICY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA
        or plan.get("status")
        != "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_STATE_POLICY_MECHANICS_REPLAY"
        or plan.get("episode_id") != episode_id
        or plan.get("target_id") != entry.get("target_id")
        or plan.get("plan_sha256") != entry.get("native_mechanics_plan_sha256")
        or plan.get("source_mechanics_plan_sha256")
        != entry.get("source_mechanics_plan_sha256")
        or plan.get("source_runtime_admission_receipt_sha256")
        != entry.get("runtime_admission_receipt_sha256")
        or plan.get("source_runtime_admission_campaign_sha256")
        != manifest.get("source_runtime_admission_campaign_sha256")
        or plan.get("sample_count") != entry.get("joint_target_count")
        or plan.get("collision_screened_bounded_sample_count")
        != entry.get("collision_screened_bounded_sample_count")
        or plan.get("runtime_files") != manifest.get("runtime_files")
        or plan.get("runtime_files_revalidated") is not True
        or plan.get("runtime_admission_required") is not False
        or plan.get("prior_mechanics_result_reused") is not False
        or plan.get("native_mechanics_replay_executed") is not False
        or plan.get("native_replay_authorized") is not False
        or not isinstance(targets, list)
        or len(targets) != plan.get("sample_count")
        or not isinstance(endpoints, list)
        or endpoints != entry.get("contact_endpoint_sequences")
        or len(endpoints) != 2
    ):
        raise MechanicsContractError("state-policy native mechanics lineage changed")
    return entry


def build_state_policy_native_mechanics_failure_receipt(
    *,
    manifest_sha256: str,
    plan: dict[str, Any],
    error_type: str,
    error_message: str,
) -> dict[str, Any]:
    """Retain a truthful signed receipt when one native episode stops early.

    This receipt deliberately does not claim that an in-memory trace survived
    the simulator exception.  It records only the governed input lineage and
    the observed execution error, which is enough to preserve the one-attempt
    result without fabricating mechanics evidence or authorizing a retry.
    """
    plan_hash = _require_canonical_hash(
        plan, "plan_sha256", "state-policy native mechanics plan"
    )
    if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
        raise MechanicsContractError("state-policy manifest hash is invalid")
    stopped_at_sequence = None
    prefix = "root invariant failed at sequence "
    if error_message.lower().startswith(prefix):
        candidate = error_message[len(prefix) :]
        if candidate.isdigit():
            stopped_at_sequence = int(candidate)
    stopped_target = next(
        (
            target
            for target in plan.get("joint_targets", [])
            if target.get("sequence") == stopped_at_sequence
        ),
        None,
    )
    failure_reason = (
        "ROOT_INVARIANT"
        if stopped_at_sequence is not None
        else "UNEXPECTED_RUNTIME_ERROR"
    )
    receipt: dict[str, Any] = {
        "schema": STATE_POLICY_NATIVE_MECHANICS_RECEIPT_SCHEMA,
        "status": "BLOCKED_STATE_POLICY_NATIVE_MECHANICS_REPLAY",
        "evidence_class": "PROVISIONAL_NATIVE_EXECUTION_FAILURE_ONLY",
        "complete": False,
        "failure_reason": failure_reason,
        "execution_error": {"type": error_type, "message": error_message},
        "stopped_at_sequence": stopped_at_sequence,
        "stopped_phase": (
            stopped_target.get("phase") if isinstance(stopped_target, dict) else None
        ),
        "stopped_action_index": (
            stopped_target.get("action_index")
            if isinstance(stopped_target, dict)
            else None
        ),
        "episode_id": plan.get("episode_id"),
        "partition": plan.get("partition"),
        "seed": plan.get("seed"),
        "scene_id": plan.get("scene_id"),
        "target_id": plan.get("target_id"),
        "source_manifest_sha256": manifest_sha256,
        "source_plan_sha256": plan_hash,
        "source_mechanics_plan_sha256": plan.get(
            "source_mechanics_plan_sha256"
        ),
        "source_runtime_admission_campaign_sha256": plan.get(
            "source_runtime_admission_campaign_sha256"
        ),
        "source_runtime_admission_receipt_sha256": plan.get(
            "source_runtime_admission_receipt_sha256"
        ),
        "planned_joint_target_count": plan.get("sample_count"),
        "collision_screened_bounded_sample_count": plan.get(
            "collision_screened_bounded_sample_count"
        ),
        "contact_endpoint_sequences": list(
            plan.get("contact_endpoint_sequences", [])
        ),
        "native_trace_retained": False,
        "action_assessments": [],
        "fresh_mechanics_replay": True,
        "prior_mechanics_result_reused": False,
        "automatic_retry_performed": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": list(plan.get("limitations", []))
        + [
            "execution_stopped_before_complete_native_mechanics_assessment",
            "in_memory_native_trace_not_retained_after_runtime_exception",
            "failure_receipt_does_not_authorize_retry",
        ],
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def build_state_policy_native_execution_progress(
    *,
    plan: dict[str, Any],
    attempted_joint_target_count: int,
    native_trace_row_count: int,
    failure_reason: str | None = None,
    stopped_target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe a complete run or a fail-closed run with retained telemetry."""

    targets = plan.get("joint_targets")
    planned_count = plan.get("sample_count")
    if (
        not isinstance(targets, list)
        or not isinstance(planned_count, int)
        or isinstance(planned_count, bool)
        or planned_count != len(targets)
    ):
        raise MechanicsContractError("state-policy target denominator is invalid")
    for value, label in (
        (attempted_joint_target_count, "attempted joint target count"),
        (native_trace_row_count, "native trace row count"),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise MechanicsContractError(f"{label} is invalid")
    if attempted_joint_target_count > planned_count:
        raise MechanicsContractError("attempted target count exceeds plan")
    if failure_reason is None:
        if stopped_target is not None or attempted_joint_target_count != planned_count:
            raise MechanicsContractError("complete execution progress is inconsistent")
        return {
            "complete": True,
            "failure_reason": None,
            "stopped_at_sequence": None,
            "stopped_phase": None,
            "stopped_action_index": None,
            "planned_joint_target_count": planned_count,
            "attempted_joint_target_count": attempted_joint_target_count,
            "native_trace_row_count": native_trace_row_count,
            "native_trace_retained": True,
            "automatic_retry_performed": False,
        }
    if failure_reason != "ROOT_INVARIANT" or not isinstance(stopped_target, dict):
        raise MechanicsContractError("retained execution failure is unsupported")
    if stopped_target not in targets or attempted_joint_target_count == 0:
        raise MechanicsContractError("stopped target is inconsistent with the plan")
    return {
        "complete": False,
        "failure_reason": failure_reason,
        "stopped_at_sequence": stopped_target.get("sequence"),
        "stopped_phase": stopped_target.get("phase"),
        "stopped_action_index": stopped_target.get("action_index"),
        "planned_joint_target_count": planned_count,
        "attempted_joint_target_count": attempted_joint_target_count,
        "native_trace_row_count": native_trace_row_count,
        "native_trace_retained": True,
        "automatic_retry_performed": False,
    }


def run_drive_controlled_robot_h_replay(
    *,
    replay_plan_path: Path,
    layout_path: Path,
    drive_profile_path: Path,
    robot_usd_path: Path,
    output_path: Path,
    status_path: Path,
    randomized_episode: dict[str, Any] | None = None,
    randomized_campaign_sha256: str | None = None,
    randomized_source_receipt_sha256: str | None = None,
    randomized_trajectory_path: Path | None = None,
    state_policy_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Replay selected joint targets against one native key in Isaac."""

    plan = json.loads(replay_plan_path.resolve(strict=True).read_bytes())
    plan_hash = _require_canonical_hash(plan, "plan_sha256", "robot H replay plan")
    profile = build_profile(layout_path.resolve(strict=True))
    drive_raw = drive_profile_path.resolve(strict=True).read_bytes()
    drive_profile = json.loads(drive_raw)
    robot_usd = robot_usd_path.resolve(strict=True)
    robot_usd_bytes = robot_usd.read_bytes()
    bindings = plan.get("source_bindings", {})
    source_plan = (
        plan.get("schema") == DRIVE_CONTROLLED_ROBOT_H_REPLAY_PLAN_SCHEMA
        and plan.get("status") == "READY_FOR_ZERO_AUTHORITY_NATIVE_ROBOT_H_REPLAY"
    )
    adapted_plan = (
        plan.get("schema") == FEEDBACK_ADAPTED_ROBOT_H_REPLAY_PLAN_SCHEMA
        and plan.get("status")
        == "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_NATIVE_H_REPLAY"
    )
    trace_lifted_plan = (
        plan.get("schema") == TRACE_LIFTED_ROBOT_H_REPLAY_PLAN_SCHEMA
        and plan.get("status")
        == "READY_FOR_ZERO_AUTHORITY_TRACE_LIFTED_NATIVE_H_REPLAY"
    )
    contact_refined_plan = (
        plan.get("schema") == CONTACT_REFINED_ROBOT_H_REPLAY_PLAN_SCHEMA
        and plan.get("status")
        == "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_NATIVE_H_REPLAY"
    )
    representative_plan = (
        plan.get("schema") == REPRESENTATIVE_KEY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA
        and plan.get("status")
        == "READY_FOR_ZERO_AUTHORITY_NATIVE_KEY_MECHANICS_REPLAY"
    )
    representative_adapted_plan = (
        plan.get("schema")
        == REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_REPLAY_PLAN_SCHEMA
        and plan.get("status")
        == "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_KEY_MECHANICS_REPLAY"
    )
    representative_refined_plan = (
        plan.get("schema")
        == REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_REPLAY_PLAN_SCHEMA
        and plan.get("status")
        == "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_KEY_MECHANICS_REPLAY"
    )
    state_policy_plan = (
        plan.get("schema") == STATE_POLICY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA
        and plan.get("status")
        == "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_STATE_POLICY_MECHANICS_REPLAY"
    )
    target_id = (
        plan.get("target_id")
        if (
            representative_plan
            or representative_adapted_plan
            or representative_refined_plan
            or state_policy_plan
        )
        else "H"
    )
    randomized_parameters = (
        _validate_randomized_replay_parameters(plan.get("randomized_parameters"))
        if state_policy_plan
        else None
    )
    if randomized_episode is not None:
        if randomized_episode.get("target_id") != target_id:
            raise MechanicsContractError(
                "randomized episode target differs from replay plan"
            )
        randomized_parameters = _validate_randomized_replay_parameters(
            randomized_episode.get("randomized_parameters")
        )
        if (
            not isinstance(randomized_campaign_sha256, str)
            or len(randomized_campaign_sha256) != 64
            or randomized_source_receipt_sha256
            != randomized_episode.get("source_receipt_sha256")
            or randomized_trajectory_path is None
        ):
            raise MechanicsContractError(
                "randomized replay lacks its campaign, receipt, or trajectory binding"
            )
    contact_endpoint_sequences = (
        plan.get("contact_endpoint_sequences")
        if (
            representative_plan
            or representative_adapted_plan
            or representative_refined_plan
            or state_policy_plan
        )
        else plan.get("h_contact_endpoint_sequences")
    )
    target_region = profile.get("regions", {}).get(target_id)
    if (
        not (
            source_plan
            or adapted_plan
            or trace_lifted_plan
            or contact_refined_plan
            or representative_plan
            or representative_adapted_plan
            or representative_refined_plan
            or state_policy_plan
        )
        or plan.get("sample_count") != len(plan.get("joint_targets", []))
        or not isinstance(contact_endpoint_sequences, list)
        or len(contact_endpoint_sequences) != 2
        or not isinstance(target_region, dict)
        or bindings.get("key_mechanics_profile_sha256") != profile["profile_sha256"]
        or bindings.get("drive_profile_file_sha256")
        != hashlib.sha256(drive_raw).hexdigest()
        or bindings.get("robot_usd_sha256")
        != hashlib.sha256(robot_usd_bytes).hexdigest()
        or plan.get("execution_contract", {}).get("post_initialization_state_teleports") != 0
        or plan.get("execution_contract", {}).get("subsequent_joint_commands")
        != "ARTICULATION_POSITION_TARGETS_ONLY"
        or any(plan.get(name) not in (False, 0, []) for name in (
            "hardware_access", "hardware_writes", "physical_authority",
            "physical_movements", "controller_commands", "gate_promotions",
        ))
    ):
        raise MechanicsContractError("robot H replay plan boundary changed")
    if representative_plan or representative_adapted_plan or representative_refined_plan:
        derived_contact_endpoints = [
            row.get("sequence")
            for row in plan["joint_targets"]
            if row.get("target_id") == target_id
            and row.get("phase") == "CONTACT"
            and row.get("phase_endpoint") is True
        ]
        if (
            target_id not in {"1", "SPACE", "ENTER", "PERIOD"}
            or plan.get("sample_count") != 40
            or contact_endpoint_sequences != derived_contact_endpoints
            or plan.get("target_region") != {
                "center_board_xy_mm": list(target_region["center_board_xy_mm"]),
                "half_extent_mm": list(target_region["half_extent_mm"]),
            }
            or plan.get("execution_contract", {}).get(
                "maximum_joint_tracking_error_rad"
            ) != 0.05
        ):
            raise MechanicsContractError(
                "representative native mechanics replay boundary changed"
            )
    if state_policy_plan:
        derived_contact_endpoints = [
            row.get("sequence")
            for row in plan["joint_targets"]
            if row.get("target_id") == target_id
            and row.get("phase") == "CONTACT"
            and row.get("phase_endpoint") is True
        ]
        expected_randomized_center = _randomized_keyboard_point_mm(
            list(target_region["center_board_xy_mm"]),
            offset_x_mm=randomized_parameters["keyboard_offset_x_mm"],
            offset_y_mm=randomized_parameters["keyboard_offset_y_mm"],
            yaw_deg=randomized_parameters["keyboard_yaw_deg"],
        )
        if (
            target_id not in {"1", "SPACE", "ENTER", "PERIOD"}
            or not isinstance(state_policy_manifest_sha256, str)
            or len(state_policy_manifest_sha256) != 64
            or contact_endpoint_sequences != derived_contact_endpoints
            or plan.get("target_region") != {
                "center_board_xy_mm": list(target_region["center_board_xy_mm"]),
                "half_extent_mm": list(target_region["half_extent_mm"]),
            }
            or plan.get("randomized_key_center_board_xy_mm")
            != expected_randomized_center
            or plan.get("execution_contract", {}).get(
                "maximum_joint_tracking_error_rad"
            )
            != 0.05
            or plan.get("execution_contract", {}).get(
                "randomized_key_mechanics_required"
            )
            is not True
        ):
            raise MechanicsContractError(
                "state-policy native mechanics replay boundary changed"
            )
    if representative_adapted_plan:
        adaptation = plan.get("feedback_adaptation", {})
        if (
            adaptation.get("method")
            != "TRACE_RELEASE_ANCHOR_AND_COMPRESSION_INTERPOLATION"
            or adaptation.get("release_anchor_sequence") != 32
            or adaptation.get("lifted_hover_retract_sequences")
            != [33, 34, 36, 37, 39]
            or adaptation.get("adapted_contact_sequences") != [35, 38]
            or adaptation.get("mechanics_thresholds_changed") is not False
            or adaptation.get("target_region_changed") is not False
            or plan.get("execution_contract", {}).get(
                "feedback_adaptation_applied"
            ) is not True
        ):
            raise MechanicsContractError(
                "representative feedback adaptation boundary changed"
            )
    if representative_refined_plan:
        refinement = plan.get("contact_refinement", {})
        if (
            refinement.get("method")
            != "MULTIPLICATIVE_CONTACT_ERROR_FROM_RELEASED_ANCHOR"
            or refinement.get("release_anchor_sequence") != 32
            or refinement.get("preserved_hover_retract_sequences")
            != [33, 34, 36, 37, 39]
            or refinement.get("refined_contact_sequences") != [35, 38]
            or refinement.get("mechanics_thresholds_changed") is not False
            or refinement.get("target_region_changed") is not False
            or plan.get("execution_contract", {}).get(
                "contact_refinement_applied"
            ) is not True
        ):
            raise MechanicsContractError(
                "representative contact refinement boundary changed"
            )
    if adapted_plan:
        feedback = plan.get("feedback_adaptation", {})
        allowed_dwell = plan.get("execution_contract", {}).get(
            "additional_release_dwell_allowed_only_at_sequences"
        )
        targets = plan["joint_targets"]
        dwell_rows = [
            row for row in targets if row.get("additional_hold_steps", 0) != 0
        ]
        if (
            feedback.get("method")
            != "ADDITIVE_COMPRESSION_ERROR_AND_RELEASE_DWELL"
            or feedback.get("adapted_contact_sequences") != [35, 38]
            or feedback.get("release_dwell_sequences") != [36, 39]
            or feedback.get("spatial_route_changed") is not False
            or feedback.get("mechanics_thresholds_changed") is not False
            or allowed_dwell != [36, 39]
            or [row.get("sequence") for row in dwell_rows] != allowed_dwell
            or any(
                not isinstance(row.get("additional_hold_steps"), int)
                or isinstance(row.get("additional_hold_steps"), bool)
                or row.get("additional_hold_steps") < 0
                for row in targets
            )
        ):
            raise MechanicsContractError("feedback adaptation boundary changed")
    if trace_lifted_plan:
        lift = plan.get("trace_lift_adaptation", {})
        if (
            lift.get("method")
            != "TRACE_DERIVED_NO_CONTACT_ANCHOR_AND_COMPRESSION_INTERPOLATION"
            or lift.get("no_contact_anchor_sequence") != 33
            or lift.get("lifted_hover_retract_sequences") != [34, 36, 37, 39]
            or lift.get("adapted_contact_sequences") != [35, 38]
            or lift.get("source_qualified_anchor_reused") is not True
            or lift.get("mechanics_thresholds_changed") is not False
            or plan.get("execution_contract", {}).get(
                "trace_lift_adaptation_applied"
            ) is not True
        ):
            raise MechanicsContractError("trace-lift adaptation boundary changed")
    if contact_refined_plan:
        refinement = plan.get("contact_refinement", {})
        if (
            refinement.get("method")
            != "MULTIPLICATIVE_CONTACT_ERROR_FROM_TRACE_LIFTED_ANCHOR"
            or refinement.get("no_contact_anchor_sequence") != 33
            or refinement.get("preserved_hover_retract_sequences")
            != [34, 36, 37, 39]
            or refinement.get("adapted_contact_sequences") != [35, 38]
            or refinement.get("mechanics_thresholds_changed") is not False
            or plan.get("execution_contract", {}).get(
                "contact_refinement_applied"
            ) is not True
        ):
            raise MechanicsContractError("contact refinement boundary changed")
    dt = _finite_number(drive_profile.get("physics_dt_s"), "physics dt")
    if (
        drive_profile.get("schema") != GEOMETRY_PRIOR_PROFILE_SCHEMA
        or drive_profile.get("simulation_only") is not True
        or drive_profile.get("physical_authority") is not False
        or dt <= 0.0
    ):
        raise MechanicsContractError("drive profile boundary changed")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.timeline
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation, RigidPrim
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdPhysics

        if not omni.usd.get_context().open_stage(str(robot_usd)):
            raise RuntimeError("Isaac could not open the governed robot USD")
        for _ in range(5):
            app.update()
        stage = omni.usd.get_context().get_stage()
        scene = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
        scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        scene.CreateGravityMagnitudeAttr().Set(drive_profile["gravity_m_s2"])

        for prim_path, row in drive_profile["rigid_body_properties"].items():
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                raise RuntimeError(f"missing governed rigid body {prim_path}")
            mass = UsdPhysics.MassAPI.Apply(prim)
            mass.CreateMassAttr().Set(row["mass_kg"])
            mass.CreateCenterOfMassAttr().Set(Gf.Vec3f(*row["center_of_mass_m"]))
            mass.CreateDiagonalInertiaAttr().Set(Gf.Vec3f(*row["diagonal_inertia_kg_m2"]))
            axes = row["principal_axes_wxyz"]
            mass.CreatePrincipalAxesAttr().Set(
                Gf.Quatf(axes[0], Gf.Vec3f(*axes[1:]))
            )

        base_prim = stage.GetPrimAtPath("/roarm_m3/Geometry/world/base_link")
        root_prim = stage.GetPrimAtPath("/roarm_m3")
        if not base_prim.IsValid() or not root_prim.IsValid():
            raise RuntimeError("governed articulation root is unavailable")
        matrix = plan["robot_placement_matrix_row_major"]
        yaw = math.atan2(matrix[4], matrix[0])
        base_translation = [matrix[3] / 1000.0, matrix[7] / 1000.0, matrix[11] / 1000.0]
        base_quaternion = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]
        before = UsdGeom.Xformable(base_prim).ComputeLocalToWorldTransform(0.0)
        before_t = before.ExtractTranslation()
        root_matrix = Gf.Matrix4d(1.0)
        root_matrix.SetRotate(Gf.Rotation(Gf.Vec3d(0.0, 0.0, 1.0), math.degrees(yaw)))
        root_matrix.SetTranslateOnly(Gf.Vec3d(*[
            base_translation[index] - float(before_t[index]) for index in range(3)
        ]))
        UsdGeom.Xformable(root_prim).AddTransformOp().Set(root_matrix)
        fixed = UsdPhysics.FixedJoint.Define(stage, "/roarm_m3/TactevraFixedBaseJoint")
        fixed.CreateLocalPos0Attr().Set(Gf.Vec3f(*base_translation))
        fixed.CreateLocalRot0Attr().Set(Gf.Quatf(base_quaternion[0], Gf.Vec3f(*base_quaternion[1:])))
        fixed.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0))
        fixed.CreateLocalRot1Attr().Set(Gf.Quatf(1.0))
        fixed.CreateBody1Rel().SetTargets([base_prim.GetPath()])
        PhysxSchema.PhysxArticulationAPI.Apply(root_prim).CreateSolverPositionIterationCountAttr(
            FIXED_BASE_SOLVER_POSITION_ITERATION_COUNT
        )

        key_region = profile["regions"][target_id]
        prior = profile["mechanics_prior"]
        key_center_xy_mm = list(key_region["center_board_xy_mm"])
        if randomized_parameters is not None:
            key_center_xy_mm = _randomized_keyboard_point_mm(
                key_center_xy_mm,
                offset_x_mm=randomized_parameters["keyboard_offset_x_mm"],
                offset_y_mm=randomized_parameters["keyboard_offset_y_mm"],
                yaw_deg=randomized_parameters["keyboard_yaw_deg"],
            )
        key_half_z = 0.003
        key_top = profile["target_plane_z_board_mm"] / 1000.0
        key_center = key_top - key_half_z
        key_path = "/World/TargetKey"
        key = UsdGeom.Cube.Define(stage, key_path)
        key.CreateSizeAttr(2.0)
        key_xform = UsdGeom.Xformable(key.GetPrim())
        key_xform.AddTranslateOp().Set(Gf.Vec3d(
            key_center_xy_mm[0] / 1000.0,
            key_center_xy_mm[1] / 1000.0,
            key_center,
        ))
        key_xform.AddScaleOp().Set(Gf.Vec3f(
            key_region["half_extent_mm"][0] / 1000.0,
            key_region["half_extent_mm"][1] / 1000.0,
            key_half_z,
        ))
        UsdPhysics.CollisionAPI.Apply(key.GetPrim())
        UsdPhysics.RigidBodyAPI.Apply(key.GetPrim())
        UsdPhysics.MassAPI.Apply(key.GetPrim()).CreateMassAttr().Set(
            (
                randomized_parameters["key_mass_kg"]
                if randomized_parameters is not None
                else prior["keycap_mass_kg"]["nominal"]
            )
        )
        PhysxSchema.PhysxRigidBodyAPI.Apply(key.GetPrim()).CreateDisableGravityAttr(True)
        key_joint = UsdPhysics.PrismaticJoint.Define(stage, "/World/TargetKeyJoint")
        key_joint.CreateBody1Rel().SetTargets([Sdf.Path(key_path)])
        key_joint.CreateAxisAttr().Set(UsdPhysics.Tokens.z)
        key_joint.CreateLocalPos0Attr().Set(Gf.Vec3f(
            key_center_xy_mm[0] / 1000.0,
            key_center_xy_mm[1] / 1000.0,
            key_center,
        ))
        key_joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0))
        key_joint.CreateLowerLimitAttr().Set(-prior["travel_mm"]["nominal"] / 1000.0)
        key_joint.CreateUpperLimitAttr().Set(0.0)
        key_drive = UsdPhysics.DriveAPI.Apply(key_joint.GetPrim(), "linear")
        key_drive.CreateTypeAttr().Set("force")
        key_drive.CreateTargetPositionAttr().Set(0.0)
        key_drive.CreateStiffnessAttr().Set(
            randomized_parameters["key_stiffness_n_per_m"]
            if randomized_parameters is not None
            else prior["stiffness_n_per_mm"]["nominal"] * 1000.0
        )
        key_drive.CreateDampingAttr().Set(
            randomized_parameters["key_damping_n_s_per_m"]
            if randomized_parameters is not None
            else prior["damping_n_s_per_mm"]["nominal"] * 1000.0
        )

        link5_path = "/roarm_m3/Geometry/world/base_link/link1/link2/link3/link4/link5"
        tip_path = f"{link5_path}/TactevraToolTip"
        tip = UsdGeom.Sphere.Define(stage, tip_path)
        tip.CreateRadiusAttr().Set(prior["tip_radius_mm"] / 1000.0)
        # The governed IK tool is hand_tcp_T_tip=(0, 0, -120 mm), not a
        # link-5 +Z offset.  The imported hand_tcp transform maps that axis
        # almost exactly to link-5 +Y.  Place the sphere center one radius
        # back from the governed tip point so its surface is the IK endpoint.
        hand_tcp = stage.GetPrimAtPath(f"{link5_path}/hand_tcp")
        if not hand_tcp.IsValid():
            raise RuntimeError("governed hand_tcp site is unavailable")
        hand_matrix = UsdGeom.Xformable(hand_tcp).GetLocalTransformation()
        center_in_hand = Gf.Vec3d(
            0.0, 0.0, -(120.0 - prior["tip_radius_mm"]) / 1000.0
        )
        center_in_link5 = hand_matrix.Transform(center_in_hand)
        UsdGeom.Xformable(tip.GetPrim()).AddTranslateOp().Set(center_in_link5)
        UsdPhysics.CollisionAPI.Apply(tip.GetPrim())

        SimulationManager.set_physics_dt(dt)
        SimulationManager.initialize_physics()
        for _ in range(10):
            app.update()
        articulation = Articulation("/roarm_m3")
        if list(articulation.dof_names) != plan["joint_order"]:
            raise RuntimeError("governed articulation DOF order changed")
        dof = drive_profile["dof"]
        articulation.set_dof_gains([[dof["stiffness"]] * 6], [[dof["damping"]] * 6])
        articulation.set_dof_max_efforts([[dof["maximum_effort"]] * 6])
        articulation.set_dof_max_velocities([[dof["maximum_velocity_rad_s"]] * 6])
        targets = plan["joint_targets"]
        initial = targets[0]["joint_position_target_rad"]
        articulation.set_dof_positions([initial])
        articulation.set_dof_velocities([[0.0] * 6])
        articulation.set_dof_position_targets([initial])
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        SimulationManager.step(steps=drive_profile["initial_settle_steps"])
        key_view = RigidPrim(key_path)
        settled_z = float(key_view.get_world_poses()[0].numpy().tolist()[0][2])

        root_records = []
        tracking = []
        native_trace = []
        runtime_failure_reason = None
        stopped_target = None
        previous_ns = int(targets[0]["time_from_start_ns"])
        elapsed_steps = 0
        for target in targets:
            desired = target["joint_position_target_rad"]
            articulation.set_dof_position_targets([desired])
            target_ns = int(target["time_from_start_ns"])
            scheduled_steps = max(1, round((target_ns - previous_ns) / 1e9 / dt))
            additional_hold_steps = target.get("additional_hold_steps", 0)
            if (
                not isinstance(additional_hold_steps, int)
                or isinstance(additional_hold_steps, bool)
                or additional_hold_steps < 0
            ):
                raise MechanicsContractError("additional hold steps are invalid")
            steps = scheduled_steps + additional_hold_steps
            previous_ns = target_ns
            for _ in range(steps):
                SimulationManager.step(steps=1)
                elapsed_steps += 1
                observed_key_z = float(key_view.get_world_poses()[0].numpy().tolist()[0][2])
                tip_world = UsdGeom.Xformable(tip.GetPrim()).ComputeLocalToWorldTransform(0.0)
                tip_center_z = float(tip_world.ExtractTranslation()[2])
                separation = tip_center_z - prior["tip_radius_mm"] / 1000.0 - (observed_key_z + key_half_z)
                observed_positions = [
                    float(value)
                    for value in articulation.get_dof_positions().numpy().tolist()[0]
                ]
                observed_velocities = [
                    float(value)
                    for value in articulation.get_dof_velocities().numpy().tolist()[0]
                ]
                native_trace.append(
                    _state_policy_trajectory_row(
                        time_s=elapsed_steps * dt,
                        target=target,
                        observed_joint_positions_rad=observed_positions,
                        observed_joint_velocities_rad_s=observed_velocities,
                        key_center_z_m=observed_key_z,
                        tip_center_z_m=tip_center_z,
                        tip_key_separation_m=separation,
                    )
                )
            observed = articulation.get_dof_positions().numpy().tolist()[0]
            tracking.append({
                "sequence": target["sequence"],
                "maximum_joint_error_rad": max(
                    abs(observed[index] - desired[index]) for index in range(6)
                ),
            })
            world = UsdGeom.Xformable(base_prim).ComputeLocalToWorldTransform(0.0)
            observed_t = world.ExtractTranslation()
            observed_q = world.RemoveScaleShear().ExtractRotationQuat()
            imaginary = observed_q.GetImaginary()
            root = evaluate_root_pose_invariant(
                base_translation, base_quaternion,
                [float(observed_t[index]) for index in range(3)],
                [float(observed_q.GetReal()), float(imaginary[0]), float(imaginary[1]), float(imaginary[2])],
                translation_tolerance_mm=0.05, orientation_tolerance_deg=0.1,
            )
            root["sequence"] = target["sequence"]
            root_records.append(root)
            if not root["passed"]:
                if state_policy_plan:
                    runtime_failure_reason = "ROOT_INVARIANT"
                    stopped_target = target
                    break
                raise RuntimeError(f"root invariant failed at sequence {target['sequence']}")
        timeline.stop()

        action_assessments = []
        if runtime_failure_reason is None:
            for action_index in (0, 1):
                rows = [row for row in native_trace if row["action_index"] == action_index]
                assessment = assess_native_key_trace(
                    profile,
                    rows,
                    rest_key_z_m=settled_z,
                    target_id=target_id,
                )
                action_assessments.append({"action_index": action_index, "assessment": assessment})
        maximum_tracking_error = max(
            (row["maximum_joint_error_rad"] for row in tracking), default=0.0
        )
        maximum_tracking_error_allowed = (
            _finite_number(
                plan["execution_contract"].get("maximum_joint_tracking_error_rad"),
                "maximum joint tracking error",
            )
            if (
                adapted_plan
                or trace_lifted_plan
                or contact_refined_plan
                or representative_plan
                or representative_adapted_plan
                or representative_refined_plan
                or state_policy_plan
            )
            else None
        )
        passed = (
            runtime_failure_reason is None
            and all(item["assessment"]["accepted"] for item in action_assessments)
            and all(
                item["assessment"]["resolved_key"] == target_id
                for item in action_assessments
            )
            and all(item["assessment"]["native_contact_observed"] for item in action_assessments)
            and all(item["passed"] for item in root_records)
            and (
                maximum_tracking_error_allowed is None
                or maximum_tracking_error <= maximum_tracking_error_allowed
            )
        )
        receipt: dict[str, Any] = {
            "schema": (
                STATE_POLICY_NATIVE_MECHANICS_RECEIPT_SCHEMA
                if state_policy_plan
                else (
                    REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA
                    if (
                        representative_plan
                        or representative_adapted_plan
                        or representative_refined_plan
                    )
                    else (
                        CONTACT_REFINED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
                        if contact_refined_plan
                        else (
                            TRACE_LIFTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
                            if trace_lifted_plan
                            else (
                                FEEDBACK_ADAPTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
                                if adapted_plan
                                else DRIVE_CONTROLLED_ROBOT_H_REPLAY_RECEIPT_SCHEMA
                            )
                        )
                    )
                )
            ),
            "status": (
                "PASS"
                if passed
                else (
                    "BLOCKED_STATE_POLICY_NATIVE_MECHANICS_REPLAY"
                    if state_policy_plan
                    else (
                        "BLOCKED_REPRESENTATIVE_NATIVE_KEY_MECHANICS_REPLAY"
                        if (
                            representative_plan
                            or representative_adapted_plan
                            or representative_refined_plan
                        )
                        else "BLOCKED_NATIVE_ROBOT_H_REPLAY"
                    )
                )
            ),
            "evidence_class": (
                "PROVISIONAL_NATIVE_EXECUTION_FAILURE_WITH_PARTIAL_TRACE"
                if runtime_failure_reason is not None
                else "PROVISIONAL_NATIVE_DRIVE_CONTROLLED_ROBOT_KEY_CONTACT"
            ),
            "source_plan_sha256": plan_hash,
            "target_id": target_id,
            "physics_dt_s": dt,
            "physics_steps": drive_profile["initial_settle_steps"] + elapsed_steps,
            "joint_order": list(plan["joint_order"]),
            "trajectory_schema": STATE_POLICY_TRAJECTORY_SCHEMA,
            "state_teleports_after_initialization": 0,
            "action_assessments": action_assessments,
            "maximum_joint_tracking_error_rad": maximum_tracking_error,
            "joint_tracking": tracking,
            "root_pose_invariant": {
                "observation_count": len(root_records),
                "all_passed": all(item["passed"] for item in root_records),
                "observations": root_records,
            },
            "native_trace": native_trace,
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "gate_promotions": [],
            "limitations": plan["limitations"] + [
                (
                    "single_target_key_mechanism_per_replay"
                    if (
                        representative_plan
                        or representative_adapted_plan
                        or representative_refined_plan
                        or state_policy_plan
                    )
                    else "single_representative_H_key_only"
                ),
                "tool_tip_collision_surface_is_governed_hand_tcp_minus_120_mm_endpoint",
            ],
        }
        if (
            representative_plan
            or representative_adapted_plan
            or representative_refined_plan
        ):
            receipt["maximum_joint_tracking_error_allowed_rad"] = (
                maximum_tracking_error_allowed
            )
            receipt["source_arm216_receipt_sha256"] = bindings[
                "arm216_receipt_sha256"
            ]
        if state_policy_plan:
            receipt.update({
                "episode_id": plan["episode_id"],
                "partition": plan["partition"],
                "seed": plan["seed"],
                "scene_id": plan["scene_id"],
                "source_manifest_sha256": state_policy_manifest_sha256,
                "source_mechanics_plan_sha256": plan[
                    "source_mechanics_plan_sha256"
                ],
                "source_runtime_admission_campaign_sha256": plan[
                    "source_runtime_admission_campaign_sha256"
                ],
                "source_runtime_admission_receipt_sha256": plan[
                    "source_runtime_admission_receipt_sha256"
                ],
                "collision_screened_bounded_sample_count": plan[
                    "collision_screened_bounded_sample_count"
                ],
                "contact_endpoint_sequences": list(contact_endpoint_sequences),
                "maximum_joint_tracking_error_allowed_rad": (
                    maximum_tracking_error_allowed
                ),
                "randomized_parameters": dict(randomized_parameters),
                "randomized_key_center_board_xy_mm": list(key_center_xy_mm),
                "fresh_mechanics_replay": True,
                "prior_mechanics_result_reused": False,
            })
            receipt.update(
                build_state_policy_native_execution_progress(
                    plan=plan,
                    attempted_joint_target_count=len(tracking),
                    native_trace_row_count=len(native_trace),
                    failure_reason=runtime_failure_reason,
                    stopped_target=stopped_target,
                )
            )
            if runtime_failure_reason is not None:
                receipt["limitations"] += [
                    "execution_stopped_before_complete_native_mechanics_assessment",
                    "partial_trace_contains_only_steps_observed_before_fail_closed_stop",
                    "failure_receipt_does_not_authorize_retry",
                ]
        if randomized_episode is not None:
            receipt["randomized_episode_id"] = randomized_episode["episode_id"]
            receipt["randomized_parameters"] = dict(randomized_parameters)
            receipt["randomized_key_center_board_xy_mm"] = key_center_xy_mm
        if representative_adapted_plan:
            receipt["feedback_adaptation"] = plan["feedback_adaptation"]
        if representative_refined_plan:
            receipt["contact_refinement"] = plan["contact_refinement"]
        if adapted_plan:
            receipt["maximum_joint_tracking_error_allowed_rad"] = (
                maximum_tracking_error_allowed
            )
            receipt["feedback_adaptation"] = plan["feedback_adaptation"]
        if trace_lifted_plan:
            receipt["maximum_joint_tracking_error_allowed_rad"] = (
                maximum_tracking_error_allowed
            )
            receipt["trace_lift_adaptation"] = plan["trace_lift_adaptation"]
        if contact_refined_plan:
            receipt["maximum_joint_tracking_error_allowed_rad"] = (
                maximum_tracking_error_allowed
            )
            receipt["contact_refinement"] = plan["contact_refinement"]
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        if randomized_episode is not None:
            trajectory_sha256 = _write_randomized_trajectory(
                randomized_trajectory_path, receipt["native_trace"]
            )
            receipt = _build_randomized_episode_receipt(
                campaign_sha256=randomized_campaign_sha256,
                episode=randomized_episode,
                trajectory_sha256=trajectory_sha256,
                native_receipt=receipt,
                failure_reason=(
                    None
                    if receipt["status"] == "PASS"
                    else _randomized_native_failure_reason(receipt)
                ),
            )
        output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status_path.write_text(json.dumps({
            "status": receipt.get("status", receipt.get("disposition")),
            "receipt_sha256": receipt["receipt_sha256"],
        }, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException as exc:
        if (
            state_policy_plan
            and not isinstance(
                exc, (MechanicsContractError, KeyboardInterrupt, SystemExit)
            )
        ):
            receipt = build_state_policy_native_mechanics_failure_receipt(
                manifest_sha256=state_policy_manifest_sha256,
                plan=plan,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            output_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            status_path.write_text(
                json.dumps(
                    {
                        "status": receipt["status"],
                        "receipt_sha256": receipt["receipt_sha256"],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return receipt
        if (
            randomized_episode is not None
            and not isinstance(exc, (MechanicsContractError, KeyboardInterrupt, SystemExit))
        ):
            trajectory_sha256 = _write_randomized_trajectory(
                randomized_trajectory_path, []
            )
            receipt = _build_randomized_episode_receipt(
                campaign_sha256=randomized_campaign_sha256,
                episode=randomized_episode,
                trajectory_sha256=trajectory_sha256,
                native_receipt=None,
                failure_reason=(
                    "ROOT_INVARIANT"
                    if "root invariant failed" in str(exc).lower()
                    else "UNEXPECTED_RUNTIME_ERROR"
                ),
                execution_error={"type": type(exc).__name__, "message": str(exc)},
            )
            output_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            status_path.write_text(
                json.dumps(
                    {
                        "status": receipt["disposition"],
                        "receipt_sha256": receipt["receipt_sha256"],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return receipt
        status_path.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()


def run_state_policy_native_mechanics_episode(
    *,
    manifest_path: Path,
    episode_id: str,
    replay_plan_path: Path,
    layout_path: Path,
    drive_profile_path: Path,
    robot_usd_path: Path,
    output_path: Path,
    status_path: Path,
) -> dict[str, Any]:
    """Execute one precommitted ARM-224 episode with no automatic retry."""
    manifest = json.loads(manifest_path.resolve(strict=True).read_bytes())
    plan = json.loads(replay_plan_path.resolve(strict=True).read_bytes())
    validate_state_policy_native_mechanics_episode(manifest, plan, episode_id)
    receipt = run_drive_controlled_robot_h_replay(
        replay_plan_path=replay_plan_path,
        layout_path=layout_path,
        drive_profile_path=drive_profile_path,
        robot_usd_path=robot_usd_path,
        output_path=output_path,
        status_path=status_path,
        state_policy_manifest_sha256=manifest["manifest_sha256"],
    )
    if (
        receipt.get("schema") != STATE_POLICY_NATIVE_MECHANICS_RECEIPT_SCHEMA
        or receipt.get("episode_id") != episode_id
        or receipt.get("source_manifest_sha256") != manifest["manifest_sha256"]
        or receipt.get("source_plan_sha256") != plan["plan_sha256"]
    ):
        raise MechanicsContractError(
            "state-policy native mechanics receipt boundary changed"
        )
    return receipt


def _write_randomized_trajectory(
    trajectory_path: Path, rows: list[dict[str, Any]]
) -> str:
    payload = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode("utf-8")
    trajectory_path.parent.mkdir(parents=True, exist_ok=True)
    trajectory_path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _randomized_native_failure_reason(native_receipt: dict[str, Any]) -> str:
    if native_receipt.get("root_pose_invariant", {}).get("all_passed") is not True:
        return "ROOT_INVARIANT"
    observed = native_receipt.get("maximum_joint_tracking_error_rad")
    allowed = native_receipt.get("maximum_joint_tracking_error_allowed_rad")
    if (
        isinstance(observed, (int, float))
        and not isinstance(observed, bool)
        and isinstance(allowed, (int, float))
        and not isinstance(allowed, bool)
        and observed > allowed
    ):
        return "TRACKING_ERROR"
    return "MECHANICS_REJECTION"


def _build_randomized_episode_receipt(
    *,
    campaign_sha256: str,
    episode: dict[str, Any],
    trajectory_sha256: str,
    native_receipt: dict[str, Any] | None,
    failure_reason: str | None,
    execution_error: dict[str, str] | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": RANDOMIZED_DEMONSTRATION_EPISODE_RECEIPT_SCHEMA,
        "source_campaign_sha256": campaign_sha256,
        "episode_id": episode["episode_id"],
        "partition": episode["partition"],
        "seed": episode["seed"],
        "scene_id": episode["scene_id"],
        "target_id": episode["target_id"],
        "parameter_region": episode["parameter_region"],
        "randomized_parameters": episode["randomized_parameters"],
        "source_plan_sha256": episode["source_plan_sha256"],
        "source_receipt_sha256": episode["source_receipt_sha256"],
        "complete": True,
        "disposition": "PASS" if failure_reason is None else "FAIL",
        "failure_reason": failure_reason,
        "trajectory_sha256": trajectory_sha256,
        "native_receipt_sha256": (
            native_receipt.get("receipt_sha256")
            if native_receipt is not None
            else None
        ),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
    }
    if native_receipt is not None:
        receipt["native_status"] = native_receipt.get("status")
        receipt["native_trace_sample_count"] = len(
            native_receipt.get("native_trace", [])
        )
        receipt["trajectory_schema"] = native_receipt.get("trajectory_schema")
        receipt["joint_order"] = native_receipt.get("joint_order")
        receipt["action_assessments"] = native_receipt.get(
            "action_assessments", []
        )
        receipt["maximum_joint_tracking_error_rad"] = native_receipt.get(
            "maximum_joint_tracking_error_rad"
        )
        receipt["root_pose_invariant_all_passed"] = native_receipt.get(
            "root_pose_invariant", {}
        ).get("all_passed")
        receipt["randomized_key_center_board_xy_mm"] = native_receipt.get(
            "randomized_key_center_board_xy_mm"
        )
    if execution_error is not None:
        receipt["execution_error"] = execution_error
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def run_randomized_demonstration_episode(
    *,
    campaign_path: Path,
    episode_id: str,
    replay_plan_path: Path,
    source_receipt_path: Path,
    layout_path: Path,
    drive_profile_path: Path,
    robot_usd_path: Path,
    output_path: Path,
    trajectory_path: Path,
    status_path: Path,
) -> dict[str, Any]:
    """Execute exactly one precommitted LM3 episode without retry."""
    campaign = json.loads(campaign_path.resolve(strict=True).read_bytes())
    validate_randomized_demonstration_campaign(campaign)
    matches = [
        row for row in campaign["episodes"] if row.get("episode_id") == episode_id
    ]
    if len(matches) != 1:
        raise MechanicsContractError("episode id is not unique in the campaign")
    episode = matches[0]
    plan = json.loads(replay_plan_path.resolve(strict=True).read_bytes())
    source_receipt = json.loads(source_receipt_path.resolve(strict=True).read_bytes())
    _verify_lm3_digest(plan, "plan_sha256", "randomized source plan")
    _verify_lm3_digest(
        source_receipt, "receipt_sha256", "randomized source receipt"
    )
    _require_lm3_zero_authority(plan, "randomized source plan")
    _require_lm3_zero_authority(source_receipt, "randomized source receipt")
    if (
        episode.get("source_plan_sha256") != plan["plan_sha256"]
        or episode.get("source_receipt_sha256")
        != source_receipt["receipt_sha256"]
        or episode.get("target_id") != plan.get("target_id")
        or source_receipt.get("source_plan_sha256") != plan["plan_sha256"]
        or source_receipt.get("target_id") != episode.get("target_id")
    ):
        raise MechanicsContractError(
            "randomized episode, plan, and source receipt lineage differ"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    native_receipt: dict[str, Any] | None = None
    execution_error: dict[str, str] | None = None
    try:
        native_receipt = run_drive_controlled_robot_h_replay(
            replay_plan_path=replay_plan_path,
            layout_path=layout_path,
            drive_profile_path=drive_profile_path,
            robot_usd_path=robot_usd_path,
            output_path=output_path,
            status_path=status_path,
            randomized_episode=episode,
            randomized_campaign_sha256=campaign["campaign_sha256"],
            randomized_source_receipt_sha256=source_receipt["receipt_sha256"],
            randomized_trajectory_path=trajectory_path,
        )
        if (
            native_receipt.get("schema")
            == RANDOMIZED_DEMONSTRATION_EPISODE_RECEIPT_SCHEMA
        ):
            return native_receipt
        rows = native_receipt.get("native_trace")
        if not isinstance(rows, list):
            raise MechanicsContractError("native replay did not retain a trajectory")
        trajectory_sha256 = _write_randomized_trajectory(trajectory_path, rows)
        passed = native_receipt.get("status") == "PASS"
        failure_reason = (
            None if passed else _randomized_native_failure_reason(native_receipt)
        )
    except MechanicsContractError:
        raise
    except Exception as exc:
        trajectory_sha256 = _write_randomized_trajectory(trajectory_path, [])
        passed = False
        failure_reason = (
            "ROOT_INVARIANT"
            if "root invariant failed" in str(exc).lower()
            else "UNEXPECTED_RUNTIME_ERROR"
        )
        execution_error = {"type": type(exc).__name__, "message": str(exc)}

    receipt = _build_randomized_episode_receipt(
        campaign_sha256=campaign["campaign_sha256"],
        episode=episode,
        trajectory_sha256=trajectory_sha256,
        native_receipt=native_receipt,
        failure_reason=failure_reason,
        execution_error=execution_error,
    )
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    status_path.write_text(
        json.dumps(
            {
                "status": receipt["disposition"],
                "receipt_sha256": receipt["receipt_sha256"],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return receipt


def _verify_lm3_digest(
    document: dict[str, Any], digest_field: str, label: str
) -> None:
    digest = document.get(digest_field)
    unsigned = {key: value for key, value in document.items() if key != digest_field}
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or digest != _canonical_sha256(unsigned)
    ):
        raise MechanicsContractError(f"{label} {digest_field} mismatch")


def _require_lm3_zero_authority(document: dict[str, Any], label: str) -> None:
    expected = {
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
    }
    for field, value in expected.items():
        if field in document and document[field] != value:
            raise MechanicsContractError(
                f"{label} escalates zero-authority field {field}"
            )


def _derive_lm3_bytes(master_seed: int, *parts: object) -> bytes:
    material = ":".join((str(master_seed), *(str(part) for part in parts)))
    return hashlib.sha256(material.encode("ascii")).digest()


def _lm3_uniform(raw: bytes, offset: int, low: float, high: float) -> float:
    integer = int.from_bytes(raw[offset : offset + 8], "big")
    ratio = integer / ((1 << 64) - 1)
    return round(low + ratio * (high - low), 9)


def _lm3_region(value: float, low: float, high: float) -> str:
    third = (high - low) / 3
    if value < low + third:
        return "LOW"
    if value < low + 2 * third:
        return "MID"
    return "HIGH"


def _validate_lm3_source(
    source: dict[str, Any],
    plans: dict[str, dict[str, Any]],
    receipts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if (
        source.get("schema")
        != REPRESENTATIVE_KEY_NATIVE_MECHANICS_RESULT_CAMPAIGN_SCHEMA
        or source.get("status")
        != "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_MECHANICS_CAMPAIGN"
    ):
        raise MechanicsContractError(
            "source campaign is not an admitted ARM-217 result"
        )
    _verify_lm3_digest(source, "campaign_sha256", "source campaign")
    _require_lm3_zero_authority(source, "source campaign")
    results = source.get("results")
    expected_targets = set(REPRESENTATIVE_KEYS[1:])
    if not isinstance(results, list) or len(results) != len(expected_targets):
        raise MechanicsContractError("source campaign must contain four results")
    indexed = {}
    for result in results:
        target = result.get("target_id")
        if target not in expected_targets or target in indexed:
            raise MechanicsContractError("source targets are incomplete or duplicated")
        if result.get("root_pose_invariant_passed") is not True:
            raise MechanicsContractError(f"source target {target} failed root invariant")
        plan = plans.get(target)
        receipt = receipts.get(target)
        if plan is None or receipt is None:
            raise MechanicsContractError(f"source target {target} lacks plan or receipt")
        _verify_lm3_digest(plan, "plan_sha256", f"{target} plan")
        _verify_lm3_digest(receipt, "receipt_sha256", f"{target} receipt")
        _require_lm3_zero_authority(plan, f"{target} plan")
        _require_lm3_zero_authority(receipt, f"{target} receipt")
        if result.get("plan_sha256") != plan["plan_sha256"]:
            raise MechanicsContractError(f"source target {target} plan binding mismatch")
        if result.get("receipt_sha256") != receipt["receipt_sha256"]:
            raise MechanicsContractError(
                f"source target {target} receipt binding mismatch"
            )
        indexed[target] = result
    if set(indexed) != expected_targets:
        raise MechanicsContractError("source campaign target set is incomplete")
    return indexed


def build_randomized_demonstration_campaign(
    source: dict[str, Any],
    plans: dict[str, dict[str, Any]],
    receipts: dict[str, dict[str, Any]],
    *,
    master_seed: int,
) -> dict[str, Any]:
    """Precommit the deterministic 24-episode ARM-218 LM3 smoke campaign."""
    if not isinstance(master_seed, int) or not 0 <= master_seed < 1 << 64:
        raise MechanicsContractError(
            "master_seed must be an unsigned 64-bit integer"
        )
    indexed = _validate_lm3_source(source, plans, receipts)
    ranges = {
        "key_stiffness_n_per_m": {"min": 450.0, "max": 650.0},
        "key_damping_n_s_per_m": {"min": 2.0, "max": 4.0},
        "key_mass_kg": {"min": 0.008, "max": 0.014},
        "keyboard_offset_x_mm": {"min": -1.5, "max": 1.5},
        "keyboard_offset_y_mm": {"min": -1.5, "max": 1.5},
        "keyboard_yaw_deg": {"min": -0.5, "max": 0.5},
    }
    episodes = []
    targets = REPRESENTATIVE_KEYS[1:]
    for partition, repetitions in RANDOMIZED_DEMONSTRATION_SPLIT_REPETITIONS.items():
        for target in targets:
            for repetition in range(repetitions):
                raw = _derive_lm3_bytes(master_seed, partition, target, repetition)
                seed = int.from_bytes(raw[:8], "big")
                scene_id = hashlib.sha256(b"scene:" + raw).hexdigest()[:24]
                values = {
                    name: _lm3_uniform(
                        raw, (index * 4) % 24, bounds["min"], bounds["max"]
                    )
                    for index, (name, bounds) in enumerate(ranges.items())
                }
                region = "STIFFNESS_" + _lm3_region(
                    values["key_stiffness_n_per_m"], 450.0, 650.0
                )
                identity = {
                    "partition": partition,
                    "target_id": target,
                    "repetition": repetition,
                    "seed": seed,
                    "scene_id": scene_id,
                }
                episodes.append({
                    "episode_id": "episode-" + _canonical_sha256(identity)[:20],
                    **identity,
                    "parameter_region": region,
                    "randomized_parameters": values,
                    "source_plan_sha256": plans[target]["plan_sha256"],
                    "source_receipt_sha256": receipts[target]["receipt_sha256"],
                    "source_native_trace_sample_count": indexed[target][
                        "native_trace_sample_count"
                    ],
                    "expected_external_artifacts": [
                        "episode_receipt.json",
                        "trajectory.jsonl",
                    ],
                })
    seeds = [episode["seed"] for episode in episodes]
    scenes = [episode["scene_id"] for episode in episodes]
    if len(seeds) != len(set(seeds)) or len(scenes) != len(set(scenes)):
        raise MechanicsContractError("derived seeds or scene identities collide")
    campaign = {
        "schema": RANDOMIZED_DEMONSTRATION_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_RANDOMIZED_DEMONSTRATION_SMOKE",
        "master_seed": master_seed,
        "source_campaign_sha256": source["campaign_sha256"],
        "randomization_contract": {
            "provenance": "PROVISIONAL_RANGE",
            "sampler": "SHA256_DERIVED_UNIFORM_V1",
            "ranges": ranges,
        },
        "partition_counts": {
            partition: len(targets) * count
            for partition, count in RANDOMIZED_DEMONSTRATION_SPLIT_REPETITIONS.items()
        },
        "attempted_episode_count": len(episodes),
        "episodes": episodes,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "small_simulation_only_smoke_not_statistical_coverage",
            "randomization_ranges_are_provisional_not_measured_distributions",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def validate_randomized_demonstration_campaign(campaign: dict[str, Any]) -> None:
    if campaign.get("schema") != RANDOMIZED_DEMONSTRATION_CAMPAIGN_SCHEMA:
        raise MechanicsContractError("campaign schema mismatch")
    _verify_lm3_digest(campaign, "campaign_sha256", "campaign")
    _require_lm3_zero_authority(campaign, "campaign")
    episodes = campaign.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 24:
        raise MechanicsContractError("campaign must precommit exactly 24 episodes")
    if campaign.get("attempted_episode_count") != len(episodes):
        raise MechanicsContractError("attempted denominator mismatch")
    identifiers = (
        [episode.get("episode_id") for episode in episodes],
        [episode.get("seed") for episode in episodes],
        [episode.get("scene_id") for episode in episodes],
    )
    if any(len(values) != len(set(values)) for values in identifiers):
        raise MechanicsContractError("duplicate episode, seed, or scene identity")
    partition_counts = Counter(episode.get("partition") for episode in episodes)
    if dict(partition_counts) != campaign.get("partition_counts"):
        raise MechanicsContractError("partition counts do not match episodes")
    ranges = campaign.get("randomization_contract", {}).get("ranges")
    if not isinstance(ranges, dict) or not ranges:
        raise MechanicsContractError("campaign lacks declared randomization ranges")
    coverage = Counter()
    targets = set(REPRESENTATIVE_KEYS[1:])
    for episode in episodes:
        partition = episode.get("partition")
        target = episode.get("target_id")
        if (
            partition not in RANDOMIZED_DEMONSTRATION_SPLIT_REPETITIONS
            or target not in targets
        ):
            raise MechanicsContractError("episode has undeclared partition or target")
        coverage[(partition, target)] += 1
        parameters = episode.get("randomized_parameters")
        if not isinstance(parameters, dict) or set(parameters) != set(ranges):
            raise MechanicsContractError(
                "episode parameters do not match declared randomization ranges"
            )
        for name, bounds in ranges.items():
            value = parameters[name]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not bounds["min"] <= value <= bounds["max"]
            ):
                raise MechanicsContractError(
                    f"episode parameter {name} is outside its declared range"
                )
        identity = {
            field: episode[field]
            for field in ("partition", "target_id", "repetition", "seed", "scene_id")
        }
        if episode.get("episode_id") != "episode-" + _canonical_sha256(identity)[:20]:
            raise MechanicsContractError("episode identity is not canonical")
    required_coverage = Counter({
        (partition, target): repetitions
        for partition, repetitions in RANDOMIZED_DEMONSTRATION_SPLIT_REPETITIONS.items()
        for target in targets
    })
    if coverage != required_coverage:
        raise MechanicsContractError("partition target coverage is incomplete")


def aggregate_randomized_demonstration_campaign(
    campaign: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate one complete receipt per attempted episode, including failures."""
    validate_randomized_demonstration_campaign(campaign)
    episodes = {episode["episode_id"]: episode for episode in campaign["episodes"]}
    if set(receipts) != set(episodes):
        missing = sorted(set(episodes) - set(receipts))
        extra = sorted(set(receipts) - set(episodes))
        raise MechanicsContractError(
            f"receipt set must equal attempted denominator; missing={missing}, extra={extra}"
        )
    retained = []
    failures = Counter()
    failure_regions = Counter()
    partition_results = {
        partition: Counter()
        for partition in RANDOMIZED_DEMONSTRATION_SPLIT_REPETITIONS
    }
    for episode_id, episode in episodes.items():
        receipt = receipts[episode_id]
        if receipt.get("schema") != RANDOMIZED_DEMONSTRATION_EPISODE_RECEIPT_SCHEMA:
            raise MechanicsContractError(f"{episode_id} receipt schema mismatch")
        _verify_lm3_digest(receipt, "receipt_sha256", f"{episode_id} receipt")
        _require_lm3_zero_authority(receipt, f"{episode_id} receipt")
        bindings = {
            "source_campaign_sha256": campaign["campaign_sha256"],
            "episode_id": episode_id,
            "partition": episode["partition"],
            "seed": episode["seed"],
            "scene_id": episode["scene_id"],
            "target_id": episode["target_id"],
            "parameter_region": episode["parameter_region"],
            "randomized_parameters": episode["randomized_parameters"],
            "source_plan_sha256": episode["source_plan_sha256"],
            "source_receipt_sha256": episode["source_receipt_sha256"],
        }
        for field, expected in bindings.items():
            if receipt.get(field) != expected:
                raise MechanicsContractError(
                    f"{episode_id} receipt binding mismatch for {field}"
                )
        disposition = receipt.get("disposition")
        if disposition not in {"PASS", "FAIL"} or receipt.get("complete") is not True:
            raise MechanicsContractError(f"{episode_id} receipt is incomplete")
        reason = receipt.get("failure_reason")
        if disposition == "PASS" and reason is not None:
            raise MechanicsContractError(f"{episode_id} passing receipt has failure")
        if (
            disposition == "FAIL"
            and reason not in RANDOMIZED_DEMONSTRATION_FAILURE_REASONS
        ):
            raise MechanicsContractError(f"{episode_id} failure reason is undeclared")
        trajectory_sha256 = receipt.get("trajectory_sha256")
        if not isinstance(trajectory_sha256, str) or len(trajectory_sha256) != 64:
            raise MechanicsContractError(
                f"{episode_id} lacks content-addressed trajectory"
            )
        partition_results[episode["partition"]][disposition] += 1
        if disposition == "FAIL":
            failures[reason] += 1
            failure_regions[f"{reason}:{episode['parameter_region']}"] += 1
        retained.append({
            "episode_id": episode_id,
            "disposition": disposition,
            "failure_reason": reason,
            "receipt_sha256": receipt["receipt_sha256"],
            "trajectory_sha256": trajectory_sha256,
        })
    passed = sum(item["disposition"] == "PASS" for item in retained)
    result = {
        "schema": RANDOMIZED_DEMONSTRATION_RESULT_SCHEMA,
        "status": "COMPLETE_RANDOMIZED_DEMONSTRATION_SMOKE",
        "source_campaign_sha256": campaign["campaign_sha256"],
        "attempted_episode_count": len(episodes),
        "completed_episode_count": len(retained),
        "passed_episode_count": passed,
        "failed_episode_count": len(retained) - passed,
        "partition_results": {
            partition: dict(counts)
            for partition, counts in partition_results.items()
        },
        "failure_counts_by_reason": dict(sorted(failures.items())),
        "failure_counts_by_reason_and_region": dict(sorted(failure_regions.items())),
        "retained_episodes": retained,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
    }
    result["result_sha256"] = _canonical_sha256(result)
    return result


def build_state_policy_dataset_manifest(
    campaign: dict[str, Any],
    result: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
    trajectory_payloads: dict[str, bytes],
) -> dict[str, Any]:
    """Compile a deterministic, leakage-safe LM4 state-policy dataset manifest."""
    validate_randomized_demonstration_campaign(campaign)
    _verify_lm3_digest(result, "result_sha256", "randomized result")
    _require_lm3_zero_authority(result, "randomized result")
    if (
        result.get("schema") != RANDOMIZED_DEMONSTRATION_RESULT_SCHEMA
        or result.get("status") != "COMPLETE_RANDOMIZED_DEMONSTRATION_SMOKE"
        or result.get("source_campaign_sha256") != campaign["campaign_sha256"]
    ):
        raise MechanicsContractError(
            "randomized result is not a complete result for the supplied campaign"
        )
    recomputed_result = aggregate_randomized_demonstration_campaign(
        campaign, receipts
    )
    if recomputed_result != result:
        raise MechanicsContractError(
            "randomized result does not reproduce from the supplied receipts"
        )
    episodes = {episode["episode_id"]: episode for episode in campaign["episodes"]}
    if set(trajectory_payloads) != set(episodes):
        missing = sorted(set(episodes) - set(trajectory_payloads))
        extra = sorted(set(trajectory_payloads) - set(episodes))
        raise MechanicsContractError(
            "trajectory set must equal attempted denominator; "
            f"missing={missing}, extra={extra}"
        )

    parameter_names = sorted(
        campaign["randomization_contract"]["ranges"]
    )
    joint_order: list[str] | None = None
    input_feature_names = [
        *[f"joint_position_observed_rad[{index}]" for index in range(6)],
        *[f"joint_velocity_observed_rad_s[{index}]" for index in range(6)],
        "key_center_z_m",
        "tip_center_z_m",
        "tip_key_separation_m",
        *[f"randomized_parameters.{name}" for name in parameter_names],
        "randomized_key_center_board_xy_mm[0]",
        "randomized_key_center_board_xy_mm[1]",
    ]
    training_feature_columns = [[] for _ in input_feature_names]
    episode_entries = []
    role_counts: Counter[str] = Counter()
    partition_counts: dict[str, Counter[str]] = {
        partition: Counter()
        for partition in RANDOMIZED_DEMONSTRATION_SPLIT_REPETITIONS
    }
    total_row_count = 0

    for episode_id, episode in episodes.items():
        receipt = receipts[episode_id]
        payload = trajectory_payloads[episode_id]
        if not isinstance(payload, bytes):
            raise MechanicsContractError(
                f"{episode_id} trajectory payload must be bytes"
            )
        if hashlib.sha256(payload).hexdigest() != receipt["trajectory_sha256"]:
            raise MechanicsContractError(
                f"{episode_id} trajectory digest does not match receipt"
            )
        if receipt.get("trajectory_schema") != STATE_POLICY_TRAJECTORY_SCHEMA:
            raise MechanicsContractError(
                f"{episode_id} trajectory is not an LM4 state-policy trajectory"
            )
        receipt_joint_order = receipt.get("joint_order")
        if (
            not isinstance(receipt_joint_order, list)
            or len(receipt_joint_order) != 6
            or not all(isinstance(item, str) and item for item in receipt_joint_order)
        ):
            raise MechanicsContractError(
                f"{episode_id} receipt must declare six ordered joints"
            )
        if joint_order is None:
            joint_order = list(receipt_joint_order)
        elif receipt_joint_order != joint_order:
            raise MechanicsContractError(
                f"{episode_id} joint order differs from the dataset contract"
            )
        key_center_xy = receipt.get("randomized_key_center_board_xy_mm")
        if not isinstance(key_center_xy, list) or len(key_center_xy) != 2:
            raise MechanicsContractError(
                f"{episode_id} receipt lacks randomized key-center geometry"
            )
        key_center_xy = [
            _finite_number(value, f"{episode_id} key-center coordinate")
            for value in key_center_xy
        ]

        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MechanicsContractError(
                f"{episode_id} trajectory is not UTF-8 JSONL"
            ) from exc
        lines = text.splitlines()
        if not lines or any(not line.strip() for line in lines):
            raise MechanicsContractError(
                f"{episode_id} trajectory contains no rows or blank rows"
            )
        if receipt.get("native_trace_sample_count") != len(lines):
            raise MechanicsContractError(
                f"{episode_id} trajectory row count does not match receipt"
            )
        disposition = receipt["disposition"]
        partition = episode["partition"]
        role = (
            "TRAINING"
            if disposition == "PASS" and partition == "train"
            else "EVALUATION"
            if disposition == "PASS"
            else "REJECTION_EVIDENCE"
        )
        previous_time = -math.inf
        for row_index, line in enumerate(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MechanicsContractError(
                    f"{episode_id} trajectory row {row_index} is invalid JSON"
                ) from exc
            if not isinstance(row, dict) or row.get("schema") != STATE_POLICY_TRAJECTORY_SCHEMA:
                raise MechanicsContractError(
                    f"{episode_id} trajectory row {row_index} schema mismatch"
                )
            if row.get("target_id") != episode["target_id"]:
                raise MechanicsContractError(
                    f"{episode_id} trajectory row {row_index} target mismatch"
                )
            if not isinstance(row.get("phase"), str) or not row["phase"]:
                raise MechanicsContractError(
                    f"{episode_id} trajectory row {row_index} lacks phase"
                )
            if row.get("action_index") is not None and not isinstance(
                row["action_index"], int
            ):
                raise MechanicsContractError(
                    f"{episode_id} trajectory row {row_index} action index is invalid"
                )
            if not isinstance(row.get("target_sequence"), int):
                raise MechanicsContractError(
                    f"{episode_id} trajectory row {row_index} sequence is invalid"
                )
            time_s = _finite_number(
                row.get("time_s"), f"{episode_id} trajectory time"
            )
            if time_s <= previous_time:
                raise MechanicsContractError(
                    f"{episode_id} trajectory time must be strictly increasing"
                )
            previous_time = time_s
            vectors = []
            for field in (
                "joint_position_observed_rad",
                "joint_velocity_observed_rad_s",
                "joint_position_target_rad",
            ):
                values = row.get(field)
                if not isinstance(values, list) or len(values) != 6:
                    raise MechanicsContractError(
                        f"{episode_id} trajectory row {row_index} {field} must have six values"
                    )
                vectors.append([
                    _finite_number(
                        value, f"{episode_id} trajectory row {row_index} {field}"
                    )
                    for value in values
                ])
            geometry = [
                _finite_number(
                    row.get(field),
                    f"{episode_id} trajectory row {row_index} {field}",
                )
                for field in (
                    "key_center_z_m",
                    "tip_center_z_m",
                    "tip_key_separation_m",
                )
            ]
            parameters = [
                _finite_number(
                    episode["randomized_parameters"][name],
                    f"{episode_id} randomized parameter {name}",
                )
                for name in parameter_names
            ]
            features = [*vectors[0], *vectors[1], *geometry, *parameters, *key_center_xy]
            if role == "TRAINING":
                for column, value in zip(training_feature_columns, features, strict=True):
                    column.append(value)

        total_row_count += len(lines)
        role_counts[role] += 1
        partition_counts[partition][role] += 1
        episode_entries.append({
            "episode_id": episode_id,
            "partition": partition,
            "target_id": episode["target_id"],
            "seed": episode["seed"],
            "scene_id": episode["scene_id"],
            "randomized_parameters": episode["randomized_parameters"],
            "randomized_key_center_board_xy_mm": key_center_xy,
            "role": role,
            "disposition": disposition,
            "failure_reason": receipt["failure_reason"],
            "sample_count": len(lines),
            "receipt_sha256": receipt["receipt_sha256"],
            "trajectory_sha256": receipt["trajectory_sha256"],
        })

    training_row_count = len(training_feature_columns[0])
    if training_row_count == 0:
        raise MechanicsContractError("dataset has no passing training rows")
    normalization = []
    for name, values in zip(
        input_feature_names, training_feature_columns, strict=True
    ):
        mean = math.fsum(values) / training_row_count
        standard_deviation = math.sqrt(
            math.fsum((value - mean) ** 2 for value in values)
            / training_row_count
        )
        normalization.append({
            "feature": name,
            "mean": mean,
            "population_standard_deviation": standard_deviation,
            "scale": standard_deviation if standard_deviation > 0.0 else 1.0,
        })

    manifest = {
        "schema": STATE_POLICY_DATASET_MANIFEST_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_DATASET",
        "source_campaign_sha256": campaign["campaign_sha256"],
        "source_result_sha256": result["result_sha256"],
        "trajectory_schema": STATE_POLICY_TRAJECTORY_SCHEMA,
        "joint_order": joint_order,
        "feature_contract": {
            "numeric_inputs": input_feature_names,
            "categorical_context": ["target_id", "phase", "action_index"],
            "action_target": "joint_position_target_rad",
            "action_dimension": 6,
        },
        "normalization": {
            "source_partition": "train",
            "source_role": "TRAINING",
            "sample_count": training_row_count,
            "statistics": normalization,
        },
        "attempted_episode_count": len(episode_entries),
        "total_row_count": total_row_count,
        "training_row_count": training_row_count,
        "role_counts": dict(sorted(role_counts.items())),
        "partition_role_counts": {
            partition: dict(sorted(counts.items()))
            for partition, counts in partition_counts.items()
        },
        "episodes": episode_entries,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "simulation_only_behavior_cloning_dataset",
            "failed_episodes_are_rejection_evidence_not_imitation_targets",
            "normalization_is_fit_only_on_passing_training_rows",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    manifest["dataset_sha256"] = _canonical_sha256(manifest)
    return manifest


def _solve_state_policy_ridge(
    normal_matrix: list[list[float]],
    cross_products: list[list[float]],
    ridge_lambda: float,
) -> list[list[float]]:
    """Solve the small deterministic multi-output ridge system."""
    size = len(normal_matrix)
    outputs = len(cross_products[0])
    matrix = [
        [*row, *cross]
        for row, cross in zip(normal_matrix, cross_products, strict=True)
    ]
    for index in range(size):
        matrix[index][index] += ridge_lambda
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-12:
            raise MechanicsContractError("state-policy ridge system is singular")
        if pivot != column:
            matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        divisor = matrix[column][column]
        for item in range(column, size + outputs):
            matrix[column][item] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = matrix[row][column]
            if factor == 0.0:
                continue
            for item in range(column, size + outputs):
                matrix[row][item] -= factor * matrix[column][item]
    return [
        [round(matrix[feature][size + output], 15) for feature in range(size)]
        for output in range(outputs)
    ]


def fit_state_policy_baseline(
    manifest: dict[str, Any],
    trajectory_payloads: dict[str, bytes],
    *,
    ridge_lambda: float = 0.001,
) -> dict[str, Any]:
    """Fit a deterministic LM4 linear behavior-cloning proposal baseline."""
    _verify_lm3_digest(manifest, "dataset_sha256", "state-policy dataset")
    _require_lm3_zero_authority(manifest, "state-policy dataset")
    if (
        manifest.get("schema") != STATE_POLICY_DATASET_MANIFEST_SCHEMA
        or manifest.get("status") != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_DATASET"
        or manifest.get("trajectory_schema") != STATE_POLICY_TRAJECTORY_SCHEMA
    ):
        raise MechanicsContractError("state-policy dataset manifest is not admitted")
    ridge_lambda = _finite_number(ridge_lambda, "ridge lambda")
    if ridge_lambda <= 0.0:
        raise MechanicsContractError("ridge lambda must be positive")
    entries = manifest.get("episodes")
    if not isinstance(entries, list) or len(entries) != manifest.get(
        "attempted_episode_count"
    ):
        raise MechanicsContractError("state-policy dataset episode denominator is invalid")
    indexed = {entry.get("episode_id"): entry for entry in entries}
    if None in indexed or len(indexed) != len(entries):
        raise MechanicsContractError("state-policy dataset episode identities are invalid")
    if set(trajectory_payloads) != set(indexed):
        raise MechanicsContractError(
            "baseline trajectory set must equal the dataset denominator"
        )
    statistics = manifest.get("normalization", {}).get("statistics")
    numeric_names = manifest.get("feature_contract", {}).get("numeric_inputs")
    if (
        not isinstance(statistics, list)
        or not isinstance(numeric_names, list)
        or len(statistics) != len(numeric_names)
        or [item.get("feature") for item in statistics] != numeric_names
    ):
        raise MechanicsContractError("dataset normalization contract is inconsistent")
    means = [
        _finite_number(item.get("mean"), f"normalization mean {index}")
        for index, item in enumerate(statistics)
    ]
    scales = [
        _finite_number(item.get("scale"), f"normalization scale {index}")
        for index, item in enumerate(statistics)
    ]
    if any(scale <= 0.0 for scale in scales):
        raise MechanicsContractError("normalization scales must be positive")
    parameter_names = [
        name.removeprefix("randomized_parameters.")
        for name in numeric_names
        if name.startswith("randomized_parameters.")
    ]
    target_vocabulary = list(REPRESENTATIVE_KEYS[1:])
    action_vocabulary = (None, 0, 1)
    encoded_names = [
        "intercept",
        *numeric_names,
        *[f"target_id={value}" for value in target_vocabulary],
        *[f"phase={value}" for value in STATE_POLICY_PHASES],
        "action_index=null",
        "action_index=0",
        "action_index=1",
    ]
    records: dict[str, list[tuple[list[float], list[float]]]] = {
        "TRAINING": [],
        "EVALUATION": [],
        "REJECTION_EVIDENCE": [],
    }

    for episode_id, entry in indexed.items():
        role = entry.get("role")
        if role not in records:
            raise MechanicsContractError(f"{episode_id} has an undeclared dataset role")
        payload = trajectory_payloads[episode_id]
        if (
            not isinstance(payload, bytes)
            or hashlib.sha256(payload).hexdigest() != entry.get("trajectory_sha256")
        ):
            raise MechanicsContractError(
                f"{episode_id} baseline trajectory digest mismatch"
            )
        lines = payload.decode("utf-8").splitlines()
        if len(lines) != entry.get("sample_count"):
            raise MechanicsContractError(
                f"{episode_id} baseline trajectory row count mismatch"
            )
        parameters = entry.get("randomized_parameters")
        key_center_xy = entry.get("randomized_key_center_board_xy_mm")
        if (
            not isinstance(parameters, dict)
            or not isinstance(key_center_xy, list)
            or len(key_center_xy) != 2
        ):
            raise MechanicsContractError(
                f"{episode_id} lacks self-contained model feature context"
            )
        for row_index, line in enumerate(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MechanicsContractError(
                    f"{episode_id} baseline row {row_index} is invalid JSON"
                ) from exc
            target_id = row.get("target_id")
            phase = row.get("phase")
            action_index = row.get("action_index")
            if (
                row.get("schema") != STATE_POLICY_TRAJECTORY_SCHEMA
                or target_id != entry.get("target_id")
                or target_id not in target_vocabulary
                or phase not in STATE_POLICY_PHASES
                or action_index not in action_vocabulary
            ):
                raise MechanicsContractError(
                    f"{episode_id} baseline row {row_index} context mismatch"
                )
            raw_numeric = [
                *row.get("joint_position_observed_rad", []),
                *row.get("joint_velocity_observed_rad_s", []),
                row.get("key_center_z_m"),
                row.get("tip_center_z_m"),
                row.get("tip_key_separation_m"),
                *[parameters.get(name) for name in parameter_names],
                *key_center_xy,
            ]
            action = row.get("joint_position_target_rad")
            if len(raw_numeric) != len(numeric_names) or not isinstance(action, list) or len(action) != 6:
                raise MechanicsContractError(
                    f"{episode_id} baseline row {row_index} feature shape mismatch"
                )
            normalized = [
                (
                    _finite_number(value, f"{episode_id} baseline feature") - mean
                ) / scale
                for value, mean, scale in zip(
                    raw_numeric, means, scales, strict=True
                )
            ]
            encoded = [
                1.0,
                *normalized,
                *[float(target_id == value) for value in target_vocabulary],
                *[float(phase == value) for value in STATE_POLICY_PHASES],
                *[float(action_index == value) for value in action_vocabulary],
            ]
            records[role].append((encoded, [
                _finite_number(value, f"{episode_id} baseline action")
                for value in action
            ]))

    training = records["TRAINING"]
    if len(training) != manifest.get("training_row_count") or not training:
        raise MechanicsContractError("baseline training denominator mismatch")
    dimension = len(encoded_names)
    normal_matrix = [[0.0] * dimension for _ in range(dimension)]
    cross_products = [[0.0] * 6 for _ in range(dimension)]
    for features, action in training:
        for left in range(dimension):
            left_value = features[left]
            for right in range(left, dimension):
                value = left_value * features[right]
                normal_matrix[left][right] += value
                if left != right:
                    normal_matrix[right][left] += value
            for output in range(6):
                cross_products[left][output] += left_value * action[output]
    weights = _solve_state_policy_ridge(
        normal_matrix, cross_products, ridge_lambda
    )

    def metrics(rows: list[tuple[list[float], list[float]]]) -> dict[str, Any]:
        absolute = [0.0] * 6
        squared = [0.0] * 6
        maximum = [0.0] * 6
        for features, action in rows:
            prediction = [
                math.fsum(weight * value for weight, value in zip(output, features, strict=True))
                for output in weights
            ]
            for joint, (predicted, expected) in enumerate(
                zip(prediction, action, strict=True)
            ):
                error = abs(predicted - expected)
                absolute[joint] += error
                squared[joint] += error * error
                maximum[joint] = max(maximum[joint], error)
        count = len(rows)
        return {
            "sample_count": count,
            "mean_absolute_error_rad": [value / count for value in absolute],
            "root_mean_squared_error_rad": [
                math.sqrt(value / count) for value in squared
            ],
            "maximum_absolute_error_rad": maximum,
            "aggregate_mean_absolute_error_rad": math.fsum(absolute) / (count * 6),
            "aggregate_root_mean_squared_error_rad": math.sqrt(
                math.fsum(squared) / (count * 6)
            ),
        }

    model = {
        "schema": STATE_POLICY_BASELINE_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_PROPOSAL_REPLAY",
        "source_dataset_sha256": manifest["dataset_sha256"],
        "algorithm": "RIDGE_LINEAR_BEHAVIOR_CLONING_V1",
        "hyperparameters": {
            "ridge_lambda": ridge_lambda,
            "random_seed": None,
            "stochastic_operations": False,
        },
        "feature_encoding": {
            "encoded_features": encoded_names,
            "target_vocabulary": target_vocabulary,
            "phase_vocabulary": list(STATE_POLICY_PHASES),
            "action_index_vocabulary": [None, 0, 1],
        },
        "joint_order": manifest["joint_order"],
        "weights_by_output_joint": weights,
        "metrics": {
            "training": metrics(records["TRAINING"]),
            "held_out_evaluation": metrics(records["EVALUATION"]),
            "rejection_evidence_sample_count": len(
                records["REJECTION_EVIDENCE"]
            ),
        },
        "proposal_replay_status": "NOT_RUN",
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "simulation_only_linear_behavior_cloning_baseline",
            "held_out_action_imitation_is_not_physics_replay",
            "policy_proposals_have_not_passed_collision_or_mechanics_gates",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    model["model_sha256"] = _canonical_sha256(model)
    return model


def _predict_state_policy_action(
    manifest: dict[str, Any],
    model: dict[str, Any],
    episode: dict[str, Any],
    row: dict[str, Any],
) -> list[float]:
    statistics = manifest["normalization"]["statistics"]
    numeric_names = manifest["feature_contract"]["numeric_inputs"]
    parameter_names = [
        name.removeprefix("randomized_parameters.")
        for name in numeric_names
        if name.startswith("randomized_parameters.")
    ]
    raw_numeric = [
        *row.get("joint_position_observed_rad", []),
        *row.get("joint_velocity_observed_rad_s", []),
        row.get("key_center_z_m"),
        row.get("tip_center_z_m"),
        row.get("tip_key_separation_m"),
        *[episode["randomized_parameters"].get(name) for name in parameter_names],
        *episode["randomized_key_center_board_xy_mm"],
    ]
    if len(raw_numeric) != len(statistics):
        raise MechanicsContractError("proposal feature shape mismatch")
    normalized = [
        (
            _finite_number(value, "proposal numeric feature")
            - _finite_number(statistic["mean"], "proposal normalization mean")
        )
        / _finite_number(statistic["scale"], "proposal normalization scale")
        for value, statistic in zip(raw_numeric, statistics, strict=True)
    ]
    encoding = model["feature_encoding"]
    target_id = row.get("target_id")
    phase = row.get("phase")
    action_index = row.get("action_index")
    features = [
        1.0,
        *normalized,
        *[float(target_id == value) for value in encoding["target_vocabulary"]],
        *[float(phase == value) for value in encoding["phase_vocabulary"]],
        *[
            float(action_index == value)
            for value in encoding["action_index_vocabulary"]
        ],
    ]
    if len(features) != len(encoding["encoded_features"]):
        raise MechanicsContractError("proposal encoded feature shape mismatch")
    weights = model.get("weights_by_output_joint")
    if (
        not isinstance(weights, list)
        or len(weights) != 6
        or any(not isinstance(output, list) or len(output) != len(features) for output in weights)
    ):
        raise MechanicsContractError("proposal model weight shape mismatch")
    return [
        math.fsum(
            _finite_number(weight, "proposal weight") * value
            for weight, value in zip(output, features, strict=True)
        )
        for output in weights
    ]


def _state_policy_proposal_continuity(
    rows: list[dict[str, Any]],
    maximum_step_rad: float = STATE_POLICY_MAX_ADJACENT_STEP_RAD,
) -> dict[str, Any]:
    maximum_step_rad = _finite_number(maximum_step_rad, "proposal step bound")
    if maximum_step_rad <= 0.0:
        raise MechanicsContractError("proposal step bound must be positive")
    observed_maximum = 0.0
    violations = []
    for left_index, (left, right) in enumerate(zip(rows, rows[1:])):
        left_values = left.get("joint_position_proposal_rad")
        right_values = right.get("joint_position_proposal_rad")
        if (
            not isinstance(left_values, list)
            or not isinstance(right_values, list)
            or len(left_values) != 6
            or len(right_values) != 6
        ):
            raise MechanicsContractError("proposal continuity row shape mismatch")
        step = max(
            abs(
                _finite_number(right_value, "proposal right joint")
                - _finite_number(left_value, "proposal left joint")
            )
            for left_value, right_value in zip(
                left_values, right_values, strict=True
            )
        )
        observed_maximum = max(observed_maximum, step)
        if step > maximum_step_rad:
            violations.append({
                "left_row_index": left_index,
                "right_row_index": left_index + 1,
                "left_phase": left.get("phase"),
                "right_phase": right.get("phase"),
                "left_target_sequence": left.get("target_sequence"),
                "right_target_sequence": right.get("target_sequence"),
                "maximum_joint_step_rad": step,
            })
    return {
        "maximum_allowed_adjacent_joint_step_rad": maximum_step_rad,
        "maximum_observed_adjacent_joint_step_rad": observed_maximum,
        "violation_count": len(violations),
        "violations": violations,
    }


def build_state_policy_proposal_replay_campaign(
    manifest: dict[str, Any],
    model: dict[str, Any],
    trajectory_payloads: dict[str, bytes],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Precommit held-out LM4 policy proposals for native physics replay."""
    _verify_lm3_digest(manifest, "dataset_sha256", "state-policy dataset")
    _require_lm3_zero_authority(manifest, "state-policy dataset")
    _verify_lm3_digest(model, "model_sha256", "state-policy model")
    _require_lm3_zero_authority(model, "state-policy model")
    if (
        manifest.get("schema") != STATE_POLICY_DATASET_MANIFEST_SCHEMA
        or manifest.get("status") != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_DATASET"
        or model.get("schema") != STATE_POLICY_BASELINE_SCHEMA
        or model.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_PROPOSAL_REPLAY"
        or model.get("source_dataset_sha256") != manifest["dataset_sha256"]
        or model.get("proposal_replay_status") != "NOT_RUN"
    ):
        raise MechanicsContractError(
            "proposal replay sources are not an admitted dataset/model pair"
        )
    evaluation = [
        episode
        for episode in manifest.get("episodes", [])
        if episode.get("role") == "EVALUATION"
    ]
    expected_ids = {episode["episode_id"] for episode in evaluation}
    if set(trajectory_payloads) != expected_ids or not evaluation:
        raise MechanicsContractError(
            "proposal trajectories must equal the held-out evaluation denominator"
        )
    proposals = {}
    campaign_episodes = []
    total_rows = 0
    maximum_deviation = 0.0
    total_continuity_violations = 0
    maximum_adjacent_step = 0.0
    for episode in evaluation:
        episode_id = episode["episode_id"]
        source_payload = trajectory_payloads[episode_id]
        if hashlib.sha256(source_payload).hexdigest() != episode["trajectory_sha256"]:
            raise MechanicsContractError(
                f"{episode_id} proposal source trajectory digest mismatch"
            )
        source_lines = source_payload.decode("utf-8").splitlines()
        if len(source_lines) != episode["sample_count"]:
            raise MechanicsContractError(
                f"{episode_id} proposal source row count mismatch"
            )
        proposal_lines = []
        proposal_rows = []
        episode_maximum = 0.0
        for row_index, line in enumerate(source_lines):
            row = json.loads(line)
            if (
                row.get("schema") != STATE_POLICY_TRAJECTORY_SCHEMA
                or row.get("target_id") != episode["target_id"]
            ):
                raise MechanicsContractError(
                    f"{episode_id} proposal source row {row_index} context mismatch"
                )
            source_target = row.get("joint_position_target_rad")
            if not isinstance(source_target, list) or len(source_target) != 6:
                raise MechanicsContractError(
                    f"{episode_id} proposal source row {row_index} action mismatch"
                )
            predicted = _predict_state_policy_action(
                manifest, model, episode, row
            )
            deviation = max(
                abs(predicted_value - _finite_number(source_value, "source action"))
                for predicted_value, source_value in zip(
                    predicted, source_target, strict=True
                )
            )
            episode_maximum = max(episode_maximum, deviation)
            proposal_row = {
                "schema": STATE_POLICY_PROPOSAL_ROW_SCHEMA,
                "source_episode_id": episode_id,
                "source_row_index": row_index,
                "time_s": row["time_s"],
                "target_id": row["target_id"],
                "phase": row["phase"],
                "action_index": row["action_index"],
                "target_sequence": row["target_sequence"],
                "joint_position_proposal_rad": predicted,
                "source_planner_target_rad": source_target,
                "maximum_planner_deviation_rad": deviation,
            }
            proposal_rows.append(proposal_row)
            proposal_lines.append(
                json.dumps(proposal_row, sort_keys=True, separators=(",", ":"))
            )
        payload = ("\n".join(proposal_lines) + "\n").encode("utf-8")
        proposals[episode_id] = payload
        total_rows += len(proposal_lines)
        maximum_deviation = max(maximum_deviation, episode_maximum)
        continuity = _state_policy_proposal_continuity(proposal_rows)
        total_continuity_violations += continuity["violation_count"]
        maximum_adjacent_step = max(
            maximum_adjacent_step,
            continuity["maximum_observed_adjacent_joint_step_rad"],
        )
        campaign_episodes.append({
            "episode_id": episode_id,
            "partition": episode["partition"],
            "target_id": episode["target_id"],
            "seed": episode["seed"],
            "scene_id": episode["scene_id"],
            "source_receipt_sha256": episode["receipt_sha256"],
            "source_trajectory_sha256": episode["trajectory_sha256"],
            "proposal_trajectory_sha256": hashlib.sha256(payload).hexdigest(),
            "proposal_sample_count": len(proposal_lines),
            "maximum_planner_deviation_rad": episode_maximum,
            "continuity": continuity,
        })
    campaign = {
        "schema": STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_QUALIFICATION",
        "source_dataset_sha256": manifest["dataset_sha256"],
        "source_model_sha256": model["model_sha256"],
        "proposal_schema": STATE_POLICY_PROPOSAL_ROW_SCHEMA,
        "held_out_episode_count": len(campaign_episodes),
        "proposal_sample_count": total_rows,
        "maximum_planner_deviation_rad": maximum_deviation,
        "continuity_diagnostic": {
            "maximum_allowed_adjacent_joint_step_rad": (
                STATE_POLICY_MAX_ADJACENT_STEP_RAD
            ),
            "maximum_observed_adjacent_joint_step_rad": maximum_adjacent_step,
            "violation_count": total_continuity_violations,
            "requires_bounded_collision_interpolation": (
                total_continuity_violations > 0
            ),
            "admission_effect": "REQUIRES_FRESH_BOUNDED_COLLISION_QUALIFICATION",
        },
        "episodes": campaign_episodes,
        "required_replay_gates": [
            "FIXED_ROOT",
            "JOINT_TRACKING",
            "COLLISION",
            "CONTACT",
            "RELEASE",
            "SETTLING",
        ],
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "proposal_trajectories_are_precommitted_but_not_replayed",
            "planner_deviation_is_not_physics_acceptance",
            "adjacent_step_violations_require_bounded_collision_interpolation",
            "native_replay_remains_blocked_until_fresh_collision_qualification",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign, proposals


def _state_policy_bounded_collision_samples(
    rows: list[dict[str, Any]],
    *,
    maximum_step_rad: float = STATE_POLICY_MAX_ADJACENT_STEP_RAD,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compress one proposal trace while preserving bounded phase transitions."""
    from rocell.kinematics import ARM_JOINT_NAMES

    maximum_step_rad = _finite_number(maximum_step_rad, "collision sample step bound")
    if maximum_step_rad <= 0.0 or not rows:
        raise MechanicsContractError("collision sampling requires rows and a positive bound")

    arm_rows: list[list[float]] = []
    gripper_positions: list[float] = []
    for index, row in enumerate(rows):
        values = row.get("joint_position_proposal_rad")
        if (
            row.get("schema") != STATE_POLICY_PROPOSAL_ROW_SCHEMA
            or not isinstance(values, list)
            or len(values) != 6
        ):
            raise MechanicsContractError(
                f"proposal collision row {index} has an invalid action"
            )
        arm_rows.append([
            _finite_number(value, f"proposal collision row {index} arm joint")
            for value in values[:5]
        ])
        gripper_positions.append(
            _finite_number(values[5], f"proposal collision row {index} gripper")
        )
    if max(gripper_positions) - min(gripper_positions) > 1e-12:
        raise MechanicsContractError(
            "proposal collision compilation requires a fixed gripper position"
        )

    samples: list[dict[str, Any]] = []
    maximum_source_distance = 0.0
    interpolated_sample_count = 0
    preserved_phase_boundary_count = 0

    def append_sample(
        positions: list[float],
        *,
        left_index: int,
        right_index: int,
        ratio: float,
        subdivision_index: int,
        subdivision_count: int,
    ) -> None:
        nonlocal interpolated_sample_count
        sequence = len(samples)
        if 0.0 < ratio < 1.0:
            interpolated_sample_count += 1
        samples.append({
            "sample_id": f"proposal-sample-{sequence:04d}",
            "sample_sequence": sequence,
            "source_left_row_index": left_index,
            "source_right_row_index": right_index,
            "interpolation_ratio": ratio,
            "subdivision_index": subdivision_index,
            "subdivision_count": subdivision_count,
            "joint_positions_rad": {
                name: value
                for name, value in zip(ARM_JOINT_NAMES, positions, strict=True)
            },
        })

    append_sample(
        arm_rows[0],
        left_index=0,
        right_index=0,
        ratio=0.0,
        subdivision_index=0,
        subdivision_count=1,
    )
    last_exact_index = 0

    def append_exact(right_index: int, *, preserve_duplicate: bool = False) -> None:
        nonlocal last_exact_index
        left_positions = [
            samples[-1]["joint_positions_rad"][name] for name in ARM_JOINT_NAMES
        ]
        right_positions = arm_rows[right_index]
        maximum_delta = max(
            abs(right - left)
            for left, right in zip(left_positions, right_positions, strict=True)
        )
        if maximum_delta == 0.0 and not preserve_duplicate:
            last_exact_index = right_index
            return
        subdivision_count = max(1, math.ceil(maximum_delta / maximum_step_rad))
        source_left_index = last_exact_index
        for subdivision_index in range(1, subdivision_count + 1):
            ratio = subdivision_index / subdivision_count
            append_sample(
                [
                    left + (right - left) * ratio
                    for left, right in zip(
                        left_positions, right_positions, strict=True
                    )
                ],
                left_index=source_left_index,
                right_index=right_index,
                ratio=ratio,
                subdivision_index=subdivision_index,
                subdivision_count=subdivision_count,
            )
        last_exact_index = right_index

    for index in range(1, len(rows)):
        previous_bounded = [
            samples[-1]["joint_positions_rad"][name] for name in ARM_JOINT_NAMES
        ]
        distance = max(
            abs(value - bounded)
            for value, bounded in zip(arm_rows[index], previous_bounded, strict=True)
        )
        phase_changed = rows[index].get("phase") != rows[index - 1].get("phase")
        if distance <= maximum_step_rad and not phase_changed:
            maximum_source_distance = max(maximum_source_distance, distance)
            continue
        previous_index = index - 1
        if previous_index > last_exact_index:
            append_exact(previous_index)
        remaining = max(
            abs(
                arm_rows[index][joint_index]
                - samples[-1]["joint_positions_rad"][joint_name]
            )
            for joint_index, joint_name in enumerate(ARM_JOINT_NAMES)
        )
        if remaining > maximum_step_rad or phase_changed:
            append_exact(index, preserve_duplicate=phase_changed)
            if phase_changed:
                preserved_phase_boundary_count += 1
        retained_distance = max(
            abs(
                arm_rows[index][joint_index]
                - samples[-1]["joint_positions_rad"][joint_name]
            )
            for joint_index, joint_name in enumerate(ARM_JOINT_NAMES)
        )
        maximum_source_distance = max(maximum_source_distance, retained_distance)
    if last_exact_index != len(rows) - 1:
        append_exact(len(rows) - 1)

    maximum_bounded_step = max(
        (
            max(
                abs(
                    right["joint_positions_rad"][name]
                    - left["joint_positions_rad"][name]
                )
                for name in ARM_JOINT_NAMES
            )
            for left, right in zip(samples, samples[1:])
        ),
        default=0.0,
    )
    if (
        maximum_bounded_step > maximum_step_rad + 1e-12
        or maximum_source_distance > maximum_step_rad + 1e-12
        or len(samples) > 256
    ):
        raise MechanicsContractError(
            "proposal collision samples exceed the bounded diagnostic contract"
        )
    return samples, {
        "maximum_allowed_adjacent_joint_step_rad": maximum_step_rad,
        "maximum_observed_bounded_joint_step_rad": maximum_bounded_step,
        "maximum_source_row_distance_to_retained_sample_rad": (
            maximum_source_distance
        ),
        "source_sample_count": len(rows),
        "bounded_sample_count": len(samples),
        "interpolated_sample_count": interpolated_sample_count,
        "preserved_phase_boundary_count": preserved_phase_boundary_count,
        "fixed_gripper_position_rad": gripper_positions[0],
    }


def build_state_policy_collision_request_campaign(
    proposal_campaign: dict[str, Any],
    proposal_payloads: dict[str, bytes],
    representative_native_campaign: dict[str, Any],
    representative_native_inputs: dict[str, dict[str, dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compile model proposals into fresh, zero-authority collision requests."""
    from rocell.kinematics import ARM_JOINT_NAMES

    _verify_lm3_digest(proposal_campaign, "campaign_sha256", "proposal campaign")
    _require_lm3_zero_authority(proposal_campaign, "proposal campaign")
    _verify_lm3_digest(
        representative_native_campaign,
        "campaign_sha256",
        "representative native campaign",
    )
    _require_lm3_zero_authority(
        representative_native_campaign, "representative native campaign"
    )
    if (
        proposal_campaign.get("schema")
        != STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN_SCHEMA
        or proposal_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_QUALIFICATION"
        or representative_native_campaign.get("schema")
        != REPRESENTATIVE_KEY_NATIVE_COLLISION_CAMPAIGN_SCHEMA
        or representative_native_campaign.get("status")
        != "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_COLLISION_CAMPAIGN"
    ):
        raise MechanicsContractError(
            "state-policy collision sources are not admitted campaigns"
        )
    episode_rows = proposal_campaign.get("episodes")
    if not isinstance(episode_rows, list) or not episode_rows:
        raise MechanicsContractError("proposal campaign lacks episodes")
    expected_episode_ids = {row.get("episode_id") for row in episode_rows}
    if set(proposal_payloads) != expected_episode_ids:
        raise MechanicsContractError(
            "proposal collision payloads must equal the campaign denominator"
        )
    native_results = {
        row.get("target_id"): row
        for row in representative_native_campaign.get("results", [])
        if isinstance(row, dict)
    }
    expected_targets = {row.get("target_id") for row in episode_rows}
    if set(representative_native_inputs) != expected_targets:
        raise MechanicsContractError(
            "proposal collision inputs must equal the evaluated target set"
        )

    requests: dict[str, dict[str, Any]] = {}
    request_rows = []
    total_bounded_samples = 0
    total_interpolated_samples = 0
    maximum_bounded_step = 0.0
    for episode in episode_rows:
        episode_id = episode["episode_id"]
        target_id = episode["target_id"]
        payload = proposal_payloads[episode_id]
        if (
            hashlib.sha256(payload).hexdigest()
            != episode.get("proposal_trajectory_sha256")
        ):
            raise MechanicsContractError(
                f"{episode_id} proposal collision payload digest mismatch"
            )
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
        if len(rows) != episode.get("proposal_sample_count") or any(
            row.get("source_episode_id") != episode_id
            or row.get("target_id") != target_id
            or row.get("source_row_index") != index
            for index, row in enumerate(rows)
        ):
            raise MechanicsContractError(
                f"{episode_id} proposal collision row lineage changed"
            )
        target_inputs = representative_native_inputs[target_id]
        collision_request = target_inputs.get("collision_request")
        fixed_plan = target_inputs.get("fixed_base_replay_plan")
        route_predicate = target_inputs.get("station_route_predicate")
        if not all(
            isinstance(item, dict)
            for item in (collision_request, fixed_plan, route_predicate)
        ):
            raise MechanicsContractError(
                f"{target_id} representative collision inputs are incomplete"
            )
        for document, digest_key, label in (
            (collision_request, "request_sha256", "collision request"),
            (fixed_plan, "plan_sha256", "fixed-base replay plan"),
            (route_predicate, "predicate_sha256", "station route predicate"),
        ):
            _verify_lm3_digest(document, digest_key, f"{target_id} {label}")
            _require_lm3_zero_authority(document, f"{target_id} {label}")
        native_result = native_results.get(target_id)
        if (
            native_result is None
            or collision_request.get("schema")
            != TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA
            or collision_request.get("status")
            != "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC"
            or fixed_plan.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA
            or fixed_plan.get("status")
            != "READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY"
            or fixed_plan.get("target_id") != target_id
            or fixed_plan.get("source_collision_request_sha256")
            != collision_request["request_sha256"]
            or route_predicate.get("schema") != STATION_ROUTE_PREDICATE_SCHEMA
            or route_predicate.get("status") != "PASS"
            or route_predicate.get("source_cartesian_request_sha256")
            != collision_request.get("source_request_sha256")
            or native_result.get("source_arm215_target_plan_sha256")
            != fixed_plan.get("source_arm215_target_plan_sha256")
        ):
            raise MechanicsContractError(
                f"{target_id} representative collision lineage changed"
            )

        samples, sampling = _state_policy_bounded_collision_samples(rows)
        request: dict[str, Any] = {
            "schema": STATE_POLICY_COLLISION_REQUEST_SCHEMA,
            "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION",
            "episode_id": episode_id,
            "target_id": target_id,
            "source_dataset_sha256": proposal_campaign["source_dataset_sha256"],
            "source_model_sha256": proposal_campaign["source_model_sha256"],
            "source_proposal_campaign_sha256": proposal_campaign["campaign_sha256"],
            "source_proposal_trajectory_sha256": episode[
                "proposal_trajectory_sha256"
            ],
            "source_representative_native_campaign_sha256": (
                representative_native_campaign["campaign_sha256"]
            ),
            "source_collision_request_sha256": collision_request["request_sha256"],
            "source_fixed_base_replay_plan_sha256": fixed_plan["plan_sha256"],
            "source_station_route_predicate_sha256": route_predicate[
                "predicate_sha256"
            ],
            "source_collision_candidate_sha256": collision_request[
                "collision_candidate_sha256"
            ],
            "source_collision_pair_policy_sha256": collision_request[
                "collision_pair_policy_sha256"
            ],
            "source_toolchain_lock_sha256": collision_request[
                "toolchain_lock_sha256"
            ],
            "source_arm215_target_plan_sha256": fixed_plan[
                "source_arm215_target_plan_sha256"
            ],
            "joint_order": list(ARM_JOINT_NAMES),
            "bounded_sample_count": len(samples),
            "bounded_sampling_policy": sampling,
            "bounded_samples": samples,
            "geometry_reuse_scope": (
                "TARGET_COLLISION_GEOMETRY_PAIR_POLICY_PLACEMENT_AND_TOOLCHAIN_ONLY"
            ),
            "prior_collision_result_reused": False,
            "fresh_collision_diagnostic_required": True,
            "diagnostic_only": True,
            "installed_collision_qualified": False,
            "continuous_collision_proven": False,
            "native_replay_authorized": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "gate_promotions": [],
            "limitations": [
                "representative_geometry_lineage_is_reused_but_clearance_is_not",
                "bounded_samples_are_discrete_not_continuous_clearance_proof",
                "request_requires_fresh_model_proposal_collision_diagnostic",
                "native_and_physical_replay_remain_blocked",
            ],
        }
        request["request_sha256"] = _canonical_sha256(request)
        requests[episode_id] = request
        total_bounded_samples += len(samples)
        total_interpolated_samples += sampling["interpolated_sample_count"]
        maximum_bounded_step = max(
            maximum_bounded_step,
            sampling["maximum_observed_bounded_joint_step_rad"],
        )
        request_rows.append({
            "episode_id": episode_id,
            "target_id": target_id,
            "request_sha256": request["request_sha256"],
            "source_proposal_trajectory_sha256": episode[
                "proposal_trajectory_sha256"
            ],
            "bounded_sample_count": len(samples),
            "interpolated_sample_count": sampling["interpolated_sample_count"],
            "maximum_observed_bounded_joint_step_rad": sampling[
                "maximum_observed_bounded_joint_step_rad"
            ],
        })

    campaign: dict[str, Any] = {
        "schema": STATE_POLICY_COLLISION_REQUEST_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION",
        "source_dataset_sha256": proposal_campaign["source_dataset_sha256"],
        "source_model_sha256": proposal_campaign["source_model_sha256"],
        "source_proposal_campaign_sha256": proposal_campaign["campaign_sha256"],
        "source_representative_native_campaign_sha256": (
            representative_native_campaign["campaign_sha256"]
        ),
        "episode_count": len(request_rows),
        "total_bounded_sample_count": total_bounded_samples,
        "total_interpolated_sample_count": total_interpolated_samples,
        "maximum_observed_bounded_joint_step_rad": maximum_bounded_step,
        "requests": request_rows,
        "prior_collision_results_reused": False,
        "fresh_collision_diagnostics_required": len(request_rows),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "collision_requests_are_compiled_but_not_admitted_or_executed",
            "all_episodes_require_fresh_discrete_collision_diagnostics",
            "no_native_or_physical_replay_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign, requests


def admit_state_policy_collision_request_campaign(
    dataset_manifest: dict[str, Any],
    model: dict[str, Any],
    proposal_campaign: dict[str, Any],
    collision_request_campaign: dict[str, Any],
    collision_requests: dict[str, dict[str, Any]],
    representative_native_manifest: dict[str, Any],
    representative_native_campaign: dict[str, Any],
    representative_native_inputs: dict[str, dict[str, dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Admit LM4 collision requests up to runtime-file revalidation only."""
    from rocell.kinematics import ARM_JOINT_NAMES

    for document, digest_key, label in (
        (dataset_manifest, "dataset_sha256", "state-policy dataset"),
        (model, "model_sha256", "state-policy model"),
        (proposal_campaign, "campaign_sha256", "proposal campaign"),
        (
            collision_request_campaign,
            "campaign_sha256",
            "collision request campaign",
        ),
        (
            representative_native_manifest,
            "manifest_sha256",
            "representative native manifest",
        ),
        (
            representative_native_campaign,
            "campaign_sha256",
            "representative native campaign",
        ),
    ):
        _verify_lm3_digest(document, digest_key, label)
        _require_lm3_zero_authority(document, label)
    if (
        dataset_manifest.get("schema") != STATE_POLICY_DATASET_MANIFEST_SCHEMA
        or dataset_manifest.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_DATASET"
        or model.get("schema") != STATE_POLICY_BASELINE_SCHEMA
        or model.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_PROPOSAL_REPLAY"
        or model.get("source_dataset_sha256")
        != dataset_manifest["dataset_sha256"]
        or proposal_campaign.get("schema")
        != STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN_SCHEMA
        or proposal_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_QUALIFICATION"
        or proposal_campaign.get("source_dataset_sha256")
        != dataset_manifest["dataset_sha256"]
        or proposal_campaign.get("source_model_sha256") != model["model_sha256"]
        or collision_request_campaign.get("schema")
        != STATE_POLICY_COLLISION_REQUEST_CAMPAIGN_SCHEMA
        or collision_request_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION"
        or collision_request_campaign.get("source_dataset_sha256")
        != dataset_manifest["dataset_sha256"]
        or collision_request_campaign.get("source_model_sha256")
        != model["model_sha256"]
        or collision_request_campaign.get("source_proposal_campaign_sha256")
        != proposal_campaign["campaign_sha256"]
        or representative_native_manifest.get("schema")
        != REPRESENTATIVE_KEY_NATIVE_COLLISION_MANIFEST_SCHEMA
        or representative_native_manifest.get("status")
        != "READY_FOR_SELECTED_ZERO_AUTHORITY_NATIVE_REPLAY"
        or representative_native_campaign.get("schema")
        != REPRESENTATIVE_KEY_NATIVE_COLLISION_CAMPAIGN_SCHEMA
        or representative_native_campaign.get("status")
        != "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_COLLISION_CAMPAIGN"
        or representative_native_campaign.get("source_manifest_sha256")
        != representative_native_manifest["manifest_sha256"]
        or collision_request_campaign.get(
            "source_representative_native_campaign_sha256"
        )
        != representative_native_campaign["campaign_sha256"]
    ):
        raise MechanicsContractError("state-policy runtime admission lineage changed")
    campaign_rows = collision_request_campaign.get("requests")
    proposal_rows = proposal_campaign.get("episodes")
    if (
        not isinstance(campaign_rows, list)
        or not campaign_rows
        or not isinstance(proposal_rows, list)
        or len(campaign_rows) != collision_request_campaign.get("episode_count")
        or len(proposal_rows) != proposal_campaign.get("held_out_episode_count")
        or len(campaign_rows) != len(proposal_rows)
    ):
        raise MechanicsContractError("state-policy runtime admission denominator changed")
    request_rows = {row.get("episode_id"): row for row in campaign_rows}
    proposal_rows_by_id = {row.get("episode_id"): row for row in proposal_rows}
    if (
        None in request_rows
        or None in proposal_rows_by_id
        or set(collision_requests) != set(request_rows)
        or set(request_rows) != set(proposal_rows_by_id)
    ):
        raise MechanicsContractError("state-policy runtime request set changed")
    expected_targets = {row["target_id"] for row in proposal_rows}
    if set(representative_native_inputs) != expected_targets:
        raise MechanicsContractError("runtime native inputs do not cover all targets")
    native_manifest_rows = {
        row.get("target_id"): row
        for row in representative_native_manifest.get("entries", [])
        if isinstance(row, dict)
    }
    native_result_rows = {
        row.get("target_id"): row
        for row in representative_native_campaign.get("results", [])
        if isinstance(row, dict)
    }
    if not expected_targets.issubset(native_manifest_rows) or not expected_targets.issubset(
        native_result_rows
    ):
        raise MechanicsContractError("runtime native campaign target coverage changed")

    admissions: dict[str, dict[str, Any]] = {}
    admission_rows = []
    total_bounded_samples = 0
    runtime_hashes: set[tuple[str, str, str, str]] = set()
    for episode_id, campaign_row in request_rows.items():
        request = collision_requests[episode_id]
        proposal_row = proposal_rows_by_id[episode_id]
        _verify_lm3_digest(request, "request_sha256", f"{episode_id} collision request")
        _require_lm3_zero_authority(request, f"{episode_id} collision request")
        target_id = proposal_row["target_id"]
        if (
            request.get("schema") != STATE_POLICY_COLLISION_REQUEST_SCHEMA
            or request.get("status")
            != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION"
            or request.get("episode_id") != episode_id
            or request.get("target_id") != target_id
            or request.get("request_sha256") != campaign_row.get("request_sha256")
            or request.get("source_dataset_sha256")
            != dataset_manifest["dataset_sha256"]
            or request.get("source_model_sha256") != model["model_sha256"]
            or request.get("source_proposal_campaign_sha256")
            != proposal_campaign["campaign_sha256"]
            or request.get("source_proposal_trajectory_sha256")
            != proposal_row.get("proposal_trajectory_sha256")
            or request.get("source_representative_native_campaign_sha256")
            != representative_native_campaign["campaign_sha256"]
            or request.get("prior_collision_result_reused") is not False
            or request.get("fresh_collision_diagnostic_required") is not True
            or request.get("diagnostic_only") is not True
            or request.get("installed_collision_qualified") is not False
            or request.get("continuous_collision_proven") is not False
            or request.get("native_replay_authorized") is not False
        ):
            raise MechanicsContractError(
                f"{episode_id} state-policy collision request boundary changed"
            )
        samples = request.get("bounded_samples")
        joint_order = request.get("joint_order")
        policy = request.get("bounded_sampling_policy")
        if (
            not isinstance(samples, list)
            or not samples
            or len(samples) != request.get("bounded_sample_count")
            or len(samples) > 256
            or joint_order != list(ARM_JOINT_NAMES)
            or not isinstance(policy, dict)
            or policy.get("bounded_sample_count") != len(samples)
            or policy.get("source_sample_count")
            != proposal_row.get("proposal_sample_count")
            or policy.get("maximum_allowed_adjacent_joint_step_rad")
            != STATE_POLICY_MAX_ADJACENT_STEP_RAD
            or policy.get("maximum_observed_bounded_joint_step_rad")
            > STATE_POLICY_MAX_ADJACENT_STEP_RAD + 1e-12
            or policy.get("maximum_source_row_distance_to_retained_sample_rad")
            > STATE_POLICY_MAX_ADJACENT_STEP_RAD + 1e-12
            or [sample.get("sample_sequence") for sample in samples]
            != list(range(len(samples)))
        ):
            raise MechanicsContractError(
                f"{episode_id} state-policy bounded samples are invalid"
            )
        for sample in samples:
            positions = sample.get("joint_positions_rad")
            if not isinstance(positions, dict) or list(positions) != joint_order:
                raise MechanicsContractError(
                    f"{episode_id} state-policy collision joint order changed"
                )
            for name in joint_order:
                _finite_number(
                    positions.get(name),
                    f"{episode_id} collision sample joint {name}",
                )
            ratio = _finite_number(
                sample.get("interpolation_ratio"),
                f"{episode_id} collision interpolation ratio",
            )
            if (
                ratio < 0.0
                or ratio > 1.0
                or not isinstance(sample.get("source_left_row_index"), int)
                or not isinstance(sample.get("source_right_row_index"), int)
                or sample["source_left_row_index"] < 0
                or sample["source_right_row_index"]
                >= policy["source_sample_count"]
                or sample["source_left_row_index"]
                > sample["source_right_row_index"]
            ):
                raise MechanicsContractError(
                    f"{episode_id} collision sample provenance changed"
                )

        native_inputs = representative_native_inputs[target_id]
        source_request = native_inputs.get("collision_request")
        fixed_plan = native_inputs.get("fixed_base_replay_plan")
        route_predicate = native_inputs.get("station_route_predicate")
        native_receipt = native_inputs.get("native_receipt")
        if not all(
            isinstance(item, dict)
            for item in (
                source_request,
                fixed_plan,
                route_predicate,
                native_receipt,
            )
        ):
            raise MechanicsContractError(
                f"{target_id} runtime native evidence is incomplete"
            )
        for document, digest_key, label in (
            (source_request, "request_sha256", "source collision request"),
            (fixed_plan, "plan_sha256", "source fixed-base plan"),
            (route_predicate, "predicate_sha256", "source route predicate"),
            (native_receipt, "receipt_sha256", "source native receipt"),
        ):
            _verify_lm3_digest(document, digest_key, f"{target_id} {label}")
            _require_lm3_zero_authority(document, f"{target_id} {label}")
        manifest_row = native_manifest_rows[target_id]
        native_result = native_result_rows[target_id]
        document_hashes = manifest_row.get("document_hashes")
        source_bindings = native_receipt.get("source_bindings")
        root_invariant = native_receipt.get("root_pose_invariant")
        if (
            not isinstance(document_hashes, dict)
            or not isinstance(source_bindings, dict)
            or not isinstance(root_invariant, dict)
            or source_request.get("schema")
            != TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA
            or fixed_plan.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA
            or fixed_plan.get("target_id") != target_id
            or route_predicate.get("schema") != STATION_ROUTE_PREDICATE_SCHEMA
            or route_predicate.get("status") != "PASS"
            or native_receipt.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_COLLISION_RECEIPT_SCHEMA
            or native_receipt.get("representative_target_id") != target_id
            or native_receipt.get("collision_screening_executed") is not True
            or native_receipt.get("fixed_base_replay_applied") is not True
            or root_invariant.get("status") != "PASS"
            or native_result.get("receipt_sha256")
            != native_receipt["receipt_sha256"]
            or native_result.get("unreviewed_blocker_pair_count") != 0
            or native_result.get("physical_solid_blocker_pair_count") != 0
            or native_result.get("planning_envelope_blocker_pair_count") != 0
            or document_hashes.get("collision_request.json")
            != source_request["request_sha256"]
            or document_hashes.get("fixed_base_replay_plan.json")
            != fixed_plan["plan_sha256"]
            or document_hashes.get("station_route_predicate.json")
            != route_predicate["predicate_sha256"]
            or request.get("source_collision_request_sha256")
            != source_request["request_sha256"]
            or request.get("source_fixed_base_replay_plan_sha256")
            != fixed_plan["plan_sha256"]
            or request.get("source_station_route_predicate_sha256")
            != route_predicate["predicate_sha256"]
            or request.get("source_collision_candidate_sha256")
            != source_bindings.get("collision_candidate_sha256")
            or request.get("source_collision_pair_policy_sha256")
            != source_bindings.get("collision_pair_policy_sha256")
            or request.get("source_toolchain_lock_sha256")
            != source_bindings.get("toolchain_lock_sha256")
            or source_bindings.get("request_sha256")
            != source_request["request_sha256"]
            or source_bindings.get("fixed_base_replay_plan_sha256")
            != fixed_plan["plan_sha256"]
            or source_bindings.get("station_route_predicate_sha256")
            != route_predicate["predicate_sha256"]
        ):
            raise MechanicsContractError(
                f"{target_id} runtime environment lineage changed"
            )
        required_runtime_hashes = {
            key: source_bindings.get(key)
            for key in (
                "virtual_profile_sha256",
                "robot_import_receipt_sha256",
                "robot_usd_sha256",
                "toolchain_lock_sha256",
            )
        }
        if any(
            not isinstance(value, str) or len(value) != 64
            for value in required_runtime_hashes.values()
        ):
            raise MechanicsContractError(
                f"{target_id} runtime file hashes are incomplete"
            )
        runtime_hashes.add(tuple(required_runtime_hashes.values()))
        admission: dict[str, Any] = {
            "schema": STATE_POLICY_COLLISION_RUNTIME_ADMISSION_SCHEMA,
            "status": (
                "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_RUNTIME_INPUT_REVALIDATION"
            ),
            "episode_id": episode_id,
            "target_id": target_id,
            "request_sha256": request["request_sha256"],
            "source_collision_request_campaign_sha256": (
                collision_request_campaign["campaign_sha256"]
            ),
            "source_dataset_sha256": dataset_manifest["dataset_sha256"],
            "source_model_sha256": model["model_sha256"],
            "source_proposal_campaign_sha256": proposal_campaign[
                "campaign_sha256"
            ],
            "source_representative_native_manifest_sha256": (
                representative_native_manifest["manifest_sha256"]
            ),
            "source_representative_native_campaign_sha256": (
                representative_native_campaign["campaign_sha256"]
            ),
            "source_environment_receipt_sha256": native_receipt["receipt_sha256"],
            "bounded_sample_count": len(samples),
            "required_runtime_hashes": required_runtime_hashes,
            "runtime_files_revalidated": False,
            "isaac_started": False,
            "gpu_started": False,
            "collision_diagnostic_executed": False,
            "prior_collision_result_reused": False,
            "fresh_collision_diagnostic_required": True,
            "installed_collision_qualified": False,
            "continuous_collision_proven": False,
            "native_replay_authorized": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "gate_promotions": [],
            "limitations": [
                "source_receipt_validates_environment_lineage_not_model_clearance",
                "runtime_files_must_be_reloaded_and_rehashed_before_isaac_start",
                "fresh_model_proposal_collision_diagnostic_has_not_run",
                "native_and_physical_replay_remain_blocked",
            ],
        }
        admission["admission_sha256"] = _canonical_sha256(admission)
        admissions[episode_id] = admission
        total_bounded_samples += len(samples)
        admission_rows.append({
            "episode_id": episode_id,
            "target_id": target_id,
            "admission_sha256": admission["admission_sha256"],
            "request_sha256": request["request_sha256"],
            "bounded_sample_count": len(samples),
        })

    if (
        total_bounded_samples
        != collision_request_campaign.get("total_bounded_sample_count")
        or len(runtime_hashes) != 1
    ):
        raise MechanicsContractError(
            "state-policy runtime admission aggregate changed"
        )
    campaign: dict[str, Any] = {
        "schema": STATE_POLICY_COLLISION_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA,
        "status": (
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_RUNTIME_INPUT_REVALIDATION"
        ),
        "source_dataset_sha256": dataset_manifest["dataset_sha256"],
        "source_model_sha256": model["model_sha256"],
        "source_proposal_campaign_sha256": proposal_campaign["campaign_sha256"],
        "source_collision_request_campaign_sha256": (
            collision_request_campaign["campaign_sha256"]
        ),
        "source_representative_native_manifest_sha256": (
            representative_native_manifest["manifest_sha256"]
        ),
        "source_representative_native_campaign_sha256": (
            representative_native_campaign["campaign_sha256"]
        ),
        "admission_count": len(admission_rows),
        "target_environment_count": len(expected_targets),
        "total_bounded_sample_count": total_bounded_samples,
        "admissions": admission_rows,
        "runtime_files_revalidated": False,
        "isaac_started": False,
        "gpu_started": False,
        "collision_diagnostics_executed": 0,
        "prior_collision_results_reused": False,
        "fresh_collision_diagnostics_required": len(admission_rows),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "RELOAD_RUNTIME_FILES_VERIFY_HASHES_AND_START_FRESH_DIAGNOSTICS"
        ),
        "limitations": [
            "admission_stops_before_runtime_file_revalidation_and_isaac_start",
            "source_environment_receipts_are_not_model_proposal_clearance",
            "all_nine_fresh_collision_diagnostics_remain_pending",
            "no_native_or_physical_replay_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign, admissions


def revalidate_state_policy_collision_runtime_inputs(
    admission_campaign: dict[str, Any],
    runtime_admissions: dict[str, dict[str, Any]],
    virtual_profile_bytes: bytes,
    robot_import_receipt: dict[str, Any],
    robot_usd_bytes: bytes,
    toolchain_lock: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Reload and bind LM4 runtime files without starting Isaac or a GPU."""
    _verify_lm3_digest(admission_campaign, "campaign_sha256", "admission campaign")
    _require_lm3_zero_authority(admission_campaign, "admission campaign")
    if (
        admission_campaign.get("schema")
        != STATE_POLICY_COLLISION_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA
        or admission_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_RUNTIME_INPUT_REVALIDATION"
        or admission_campaign.get("runtime_files_revalidated") is not False
        or admission_campaign.get("isaac_started") is not False
        or admission_campaign.get("gpu_started") is not False
        or admission_campaign.get("collision_diagnostics_executed") != 0
        or admission_campaign.get("prior_collision_results_reused") is not False
    ):
        raise MechanicsContractError("runtime revalidation admission boundary changed")
    rows = admission_campaign.get("admissions")
    if (
        not isinstance(rows, list)
        or not rows
        or len(rows) != admission_campaign.get("admission_count")
        or len(rows) != admission_campaign.get("fresh_collision_diagnostics_required")
    ):
        raise MechanicsContractError("runtime revalidation denominator changed")
    rows_by_id = {row.get("episode_id"): row for row in rows if isinstance(row, dict)}
    if (
        None in rows_by_id
        or len(rows_by_id) != len(rows)
        or set(runtime_admissions) != set(rows_by_id)
    ):
        raise MechanicsContractError("runtime revalidation admission set changed")

    required_hash_sets: set[tuple[str, str, str, str]] = set()
    total_bounded_samples = 0
    for episode_id, row in rows_by_id.items():
        admission = runtime_admissions[episode_id]
        _verify_lm3_digest(admission, "admission_sha256", f"{episode_id} admission")
        _require_lm3_zero_authority(admission, f"{episode_id} admission")
        required = admission.get("required_runtime_hashes")
        if (
            admission.get("schema") != STATE_POLICY_COLLISION_RUNTIME_ADMISSION_SCHEMA
            or admission.get("status")
            != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_RUNTIME_INPUT_REVALIDATION"
            or admission.get("episode_id") != episode_id
            or admission.get("target_id") != row.get("target_id")
            or admission.get("request_sha256") != row.get("request_sha256")
            or admission.get("admission_sha256") != row.get("admission_sha256")
            or admission.get("bounded_sample_count") != row.get("bounded_sample_count")
            or admission.get("source_collision_request_campaign_sha256")
            != admission_campaign.get("source_collision_request_campaign_sha256")
            or admission.get("runtime_files_revalidated") is not False
            or admission.get("isaac_started") is not False
            or admission.get("gpu_started") is not False
            or admission.get("collision_diagnostic_executed") is not False
            or admission.get("fresh_collision_diagnostic_required") is not True
            or admission.get("prior_collision_result_reused") is not False
            or not isinstance(required, dict)
        ):
            raise MechanicsContractError(
                f"{episode_id} runtime revalidation admission changed"
            )
        required_tuple = tuple(
            required.get(key)
            for key in (
                "virtual_profile_sha256",
                "robot_import_receipt_sha256",
                "robot_usd_sha256",
                "toolchain_lock_sha256",
            )
        )
        if any(not isinstance(value, str) or len(value) != 64 for value in required_tuple):
            raise MechanicsContractError(
                f"{episode_id} runtime revalidation hashes are incomplete"
            )
        required_hash_sets.add(required_tuple)
        total_bounded_samples += admission["bounded_sample_count"]
    if (
        len(required_hash_sets) != 1
        or total_bounded_samples
        != admission_campaign.get("total_bounded_sample_count")
    ):
        raise MechanicsContractError("runtime revalidation aggregate changed")

    profile = json.loads(virtual_profile_bytes)
    if (
        profile.get("schema") != "rocell.virtual_commissioning_profile.v1"
        or profile.get("status") != "UNMEASURED_SENSITIVITY_OVERLAY"
        or profile.get("simulation_only") is not True
        or profile.get("physical_release_effect") != "NONE"
    ):
        raise MechanicsContractError("virtual profile boundary changed")
    _verify_lm3_digest(
        robot_import_receipt,
        "receipt_sha256",
        "robot import receipt",
    )
    _require_lm3_zero_authority(robot_import_receipt, "robot import receipt")
    robot_usd_hash = hashlib.sha256(robot_usd_bytes).hexdigest()
    external_files = robot_import_receipt.get("external_files")
    if (
        robot_import_receipt.get("schema") != "tactevra.isaac_sim_urdf_import.v1"
        or not isinstance(external_files, list)
        or len(external_files) != 1
        or external_files[0].get("sha256") != robot_usd_hash
        or external_files[0].get("size_bytes") != len(robot_usd_bytes)
    ):
        raise MechanicsContractError("robot USD differs from its import receipt")
    _require_lm3_zero_authority(toolchain_lock, "toolchain lock")
    if (
        toolchain_lock.get("schema") != "rocell.isaac_sim_toolchain_lock.v1"
        or toolchain_lock.get("selection_status") != "SELECTED"
        or toolchain_lock.get("hardware_access") is not False
        or toolchain_lock.get("physical_authority") is not False
        or toolchain_lock.get("wire_commands") != []
    ):
        raise MechanicsContractError("toolchain lock boundary changed")

    actual_hashes = {
        "virtual_profile_sha256": hashlib.sha256(virtual_profile_bytes).hexdigest(),
        "robot_import_receipt_sha256": robot_import_receipt["receipt_sha256"],
        "robot_usd_sha256": robot_usd_hash,
        "toolchain_lock_sha256": _canonical_sha256(toolchain_lock),
    }
    required_hashes = dict(zip(
        (
            "virtual_profile_sha256",
            "robot_import_receipt_sha256",
            "robot_usd_sha256",
            "toolchain_lock_sha256",
        ),
        next(iter(required_hash_sets)),
    ))
    if actual_hashes != required_hashes:
        changed = sorted(
            key for key in required_hashes if actual_hashes[key] != required_hashes[key]
        )
        raise MechanicsContractError(
            "runtime file hash mismatch: " + ", ".join(changed)
        )
    file_evidence = {
        "virtual_profile": {
            "sha256": actual_hashes["virtual_profile_sha256"],
            "hash_mode": "RAW_FILE_BYTES",
        },
        "robot_import_receipt": {
            "sha256": actual_hashes["robot_import_receipt_sha256"],
            "hash_mode": "CANONICAL_DOCUMENT_EXCLUDING_RECEIPT_SHA256",
        },
        "robot_usd": {
            "sha256": actual_hashes["robot_usd_sha256"],
            "hash_mode": "RAW_FILE_BYTES",
            "size_bytes": len(robot_usd_bytes),
        },
        "toolchain_lock": {
            "sha256": actual_hashes["toolchain_lock_sha256"],
            "hash_mode": "CANONICAL_JSON_DOCUMENT",
        },
    }
    receipts: dict[str, dict[str, Any]] = {}
    receipt_rows = []
    for episode_id, row in rows_by_id.items():
        receipt: dict[str, Any] = {
            "schema": STATE_POLICY_COLLISION_RUNTIME_REVALIDATION_SCHEMA,
            "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTIC_START",
            "episode_id": episode_id,
            "target_id": row["target_id"],
            "source_runtime_admission_campaign_sha256": admission_campaign[
                "campaign_sha256"
            ],
            "source_runtime_admission_sha256": row["admission_sha256"],
            "request_sha256": row["request_sha256"],
            "bounded_sample_count": row["bounded_sample_count"],
            "runtime_files": file_evidence,
            "runtime_files_revalidated": True,
            "revalidated_file_count": 4,
            "isaac_started": False,
            "gpu_started": False,
            "collision_diagnostic_executed": False,
            "prior_collision_result_reused": False,
            "fresh_collision_diagnostic_required": True,
            "installed_collision_qualified": False,
            "continuous_collision_proven": False,
            "native_replay_authorized": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "gate_promotions": [],
            "limitations": [
                "runtime_hash_match_does_not_prove_model_clearance",
                "isaac_and_gpu_have_not_started",
                "fresh_collision_diagnostic_remains_pending",
                "native_and_physical_replay_remain_blocked",
            ],
        }
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        receipts[episode_id] = receipt
        receipt_rows.append({
            "episode_id": episode_id,
            "target_id": row["target_id"],
            "receipt_sha256": receipt["receipt_sha256"],
            "source_runtime_admission_sha256": row["admission_sha256"],
            "bounded_sample_count": row["bounded_sample_count"],
        })

    campaign: dict[str, Any] = {
        "schema": STATE_POLICY_COLLISION_RUNTIME_REVALIDATION_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTIC_START",
        "source_runtime_admission_campaign_sha256": admission_campaign[
            "campaign_sha256"
        ],
        "source_dataset_sha256": admission_campaign["source_dataset_sha256"],
        "source_model_sha256": admission_campaign["source_model_sha256"],
        "source_proposal_campaign_sha256": admission_campaign[
            "source_proposal_campaign_sha256"
        ],
        "source_collision_request_campaign_sha256": admission_campaign[
            "source_collision_request_campaign_sha256"
        ],
        "revalidation_count": len(receipt_rows),
        "target_environment_count": admission_campaign["target_environment_count"],
        "total_bounded_sample_count": total_bounded_samples,
        "revalidations": receipt_rows,
        "runtime_files": file_evidence,
        "runtime_files_revalidated": True,
        "revalidated_file_count": 4,
        "isaac_started": False,
        "gpu_started": False,
        "collision_diagnostics_executed": 0,
        "prior_collision_results_reused": False,
        "fresh_collision_diagnostics_required": len(receipt_rows),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "START_FRESH_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTICS"
        ),
        "limitations": [
            "revalidation_stops_before_isaac_and_gpu_start",
            "runtime_hash_match_does_not_prove_model_clearance",
            "all_fresh_collision_diagnostics_remain_pending",
            "no_native_or_physical_replay_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign, receipts


def materialize_state_policy_native_collision_inputs(
    revalidation_campaign: dict[str, Any],
    revalidation_receipts: dict[str, dict[str, Any]],
    state_policy_requests: dict[str, dict[str, Any]],
    representative_inputs: dict[str, dict[str, dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, dict[str, dict[str, Any]]]]:
    """Bind learned-policy samples into the existing zero-authority Isaac runner."""
    _verify_lm3_digest(
        revalidation_campaign,
        "campaign_sha256",
        "runtime revalidation campaign",
    )
    _require_lm3_zero_authority(
        revalidation_campaign, "runtime revalidation campaign"
    )
    rows = revalidation_campaign.get("revalidations")
    if (
        revalidation_campaign.get("schema")
        != STATE_POLICY_COLLISION_RUNTIME_REVALIDATION_CAMPAIGN_SCHEMA
        or revalidation_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTIC_START"
        or revalidation_campaign.get("runtime_files_revalidated") is not True
        or revalidation_campaign.get("isaac_started") is not False
        or revalidation_campaign.get("gpu_started") is not False
        or revalidation_campaign.get("collision_diagnostics_executed") != 0
        or not isinstance(rows, list)
        or not rows
    ):
        raise MechanicsContractError("native collision start boundary changed")
    rows_by_id = {row.get("episode_id"): row for row in rows if isinstance(row, dict)}
    if (
        None in rows_by_id
        or len(rows_by_id) != len(rows)
        or set(revalidation_receipts) != set(rows_by_id)
        or set(state_policy_requests) != set(rows_by_id)
    ):
        raise MechanicsContractError("native collision denominator changed")

    bundles: dict[str, dict[str, dict[str, Any]]] = {}
    entries = []
    total_samples = 0
    for episode_id, row in rows_by_id.items():
        revalidation = revalidation_receipts[episode_id]
        state_request = state_policy_requests[episode_id]
        target_id = row.get("target_id")
        target_inputs = representative_inputs.get(target_id)
        if not isinstance(target_inputs, dict):
            raise MechanicsContractError(
                f"{episode_id} representative target inputs are absent"
            )
        source_request = target_inputs.get("collision_request")
        source_plan = target_inputs.get("fixed_base_replay_plan")
        route_predicate = target_inputs.get("station_route_predicate")
        for document, digest_key, label in (
            (revalidation, "receipt_sha256", "runtime revalidation"),
            (state_request, "request_sha256", "state-policy request"),
            (source_request, "request_sha256", "representative collision request"),
            (source_plan, "plan_sha256", "representative fixed-base plan"),
            (route_predicate, "predicate_sha256", "station route predicate"),
        ):
            if not isinstance(document, dict):
                raise MechanicsContractError(f"{episode_id} {label} is absent")
            _verify_lm3_digest(document, digest_key, f"{episode_id} {label}")
            _require_lm3_zero_authority(document, f"{episode_id} {label}")
        if (
            revalidation.get("schema")
            != STATE_POLICY_COLLISION_RUNTIME_REVALIDATION_SCHEMA
            or revalidation.get("status")
            != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTIC_START"
            or revalidation.get("receipt_sha256") != row.get("receipt_sha256")
            or revalidation.get("request_sha256") != state_request.get("request_sha256")
            or state_request.get("schema") != STATE_POLICY_COLLISION_REQUEST_SCHEMA
            or state_request.get("episode_id") != episode_id
            or state_request.get("target_id") != target_id
            or state_request.get("source_collision_request_sha256")
            != source_request.get("request_sha256")
            or state_request.get("source_fixed_base_replay_plan_sha256")
            != source_plan.get("plan_sha256")
            or state_request.get("source_station_route_predicate_sha256")
            != route_predicate.get("predicate_sha256")
            or source_request.get("schema") != TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA
            or source_plan.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA
        ):
            raise MechanicsContractError(
                f"{episode_id} native collision lineage changed"
            )
        state_samples = state_request.get("bounded_samples")
        if (
            not isinstance(state_samples, list)
            or not state_samples
            or len(state_samples) != state_request.get("bounded_sample_count")
            or len(state_samples) != revalidation.get("bounded_sample_count")
        ):
            raise MechanicsContractError(
                f"{episode_id} native collision samples changed"
            )
        native_samples = []
        for sequence, sample in enumerate(state_samples):
            if sample.get("sample_sequence") != sequence:
                raise MechanicsContractError(
                    f"{episode_id} native collision sample order changed"
                )
            native_sample = dict(sample)
            native_sample["source_segment_index"] = sample.get(
                "source_left_row_index", sequence
            )
            native_samples.append(native_sample)

        native_request = {
            key: value
            for key, value in source_request.items()
            if key != "request_sha256"
        }
        native_request.update({
            "bounded_sample_count": len(native_samples),
            "bounded_samples": native_samples,
            "bounded_sampling_policy": state_request["bounded_sampling_policy"],
            "state_policy_episode_id": episode_id,
            "state_policy_target_id": target_id,
            "source_state_policy_request_sha256": state_request["request_sha256"],
            "source_runtime_revalidation_receipt_sha256": revalidation[
                "receipt_sha256"
            ],
            "prior_collision_result_reused": False,
            "next_required_stage": "RUN_FRESH_ZERO_AUTHORITY_ISAAC_COLLISION_DIAGNOSTIC",
        })
        native_request["limitations"] = list(source_request.get("limitations", [])) + [
            "samples_are_fresh_learned_policy_proposals_not_representative_results",
            "native_result_cannot_authorize_contact_or_physical_motion",
        ]
        native_request["request_sha256"] = _canonical_sha256(native_request)

        native_plan = {
            key: value for key, value in source_plan.items() if key != "plan_sha256"
        }
        native_plan.update({
            "schema": STATE_POLICY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA,
            "source_collision_request_sha256": native_request["request_sha256"],
            "source_bounded_sample_count": len(native_samples),
            "source_state_policy_request_sha256": state_request["request_sha256"],
            "source_runtime_revalidation_campaign_sha256": revalidation_campaign[
                "campaign_sha256"
            ],
            "source_runtime_revalidation_receipt_sha256": revalidation[
                "receipt_sha256"
            ],
        })
        native_plan["plan_sha256"] = _canonical_sha256(native_plan)
        bundles[episode_id] = {
            "collision_request": native_request,
            "fixed_base_replay_plan": native_plan,
        }
        total_samples += len(native_samples)
        entries.append({
            "episode_id": episode_id,
            "target_id": target_id,
            "bounded_sample_count": len(native_samples),
            "state_policy_request_sha256": state_request["request_sha256"],
            "runtime_revalidation_receipt_sha256": revalidation["receipt_sha256"],
            "native_collision_request_sha256": native_request["request_sha256"],
            "native_fixed_base_replay_plan_sha256": native_plan["plan_sha256"],
        })
    if total_samples != revalidation_campaign.get("total_bounded_sample_count"):
        raise MechanicsContractError("native collision sample denominator changed")
    manifest: dict[str, Any] = {
        "schema": STATE_POLICY_NATIVE_COLLISION_MANIFEST_SCHEMA,
        "status": "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_COLLISION_DIAGNOSTICS",
        "source_runtime_revalidation_campaign_sha256": revalidation_campaign[
            "campaign_sha256"
        ],
        "source_dataset_sha256": revalidation_campaign["source_dataset_sha256"],
        "source_model_sha256": revalidation_campaign["source_model_sha256"],
        "episode_count": len(entries),
        "total_bounded_sample_count": total_samples,
        "entries": entries,
        "isaac_started": False,
        "gpu_started": False,
        "collision_diagnostics_executed": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "manifest_materialization_does_not_start_isaac_or_a_gpu",
            "all_nine_fresh_collision_diagnostics_remain_pending",
            "no_native_contact_or_physical_replay_authority",
        ],
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest, bundles


def aggregate_state_policy_native_collision_campaign(
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Verify and aggregate the complete learned-policy native diagnostic set."""
    _verify_lm3_digest(manifest, "manifest_sha256", "native collision manifest")
    _require_lm3_zero_authority(manifest, "native collision manifest")
    entries = manifest.get("entries")
    if (
        manifest.get("schema") != STATE_POLICY_NATIVE_COLLISION_MANIFEST_SCHEMA
        or manifest.get("status")
        != "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_COLLISION_DIAGNOSTICS"
        or not isinstance(entries, list)
        or not entries
    ):
        raise MechanicsContractError("native collision manifest boundary changed")
    entries_by_id = {
        entry.get("episode_id"): entry for entry in entries if isinstance(entry, dict)
    }
    if (
        None in entries_by_id
        or len(entries_by_id) != len(entries)
        or set(receipts) != set(entries_by_id)
    ):
        raise MechanicsContractError("native collision result denominator changed")
    results = []
    total_samples = 0
    total_samples_with_overlaps = 0
    blocker_episode_count = 0
    for episode_id, entry in entries_by_id.items():
        receipt = receipts[episode_id]
        _verify_lm3_digest(receipt, "receipt_sha256", f"{episode_id} native receipt")
        _require_lm3_zero_authority(receipt, f"{episode_id} native receipt")
        bindings = receipt.get("source_bindings")
        classification_counts = [
            receipt.get(key)
            for key in (
                "policy_excluded_pair_count",
                "physical_solid_blocker_pair_count",
                "planning_envelope_blocker_pair_count",
                "unreviewed_blocker_pair_count",
            )
        ]
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in classification_counts
        ):
            raise MechanicsContractError(
                f"{episode_id} native collision classification is incomplete"
            )
        blocker_count = sum(classification_counts[1:])
        root_invariant = receipt.get("root_pose_invariant")
        if not isinstance(root_invariant, dict):
            raise MechanicsContractError(
                f"{episode_id} native root invariant is absent"
            )
        root_translation = _finite_number(
            root_invariant.get("maximum_translation_delta_mm"),
            f"{episode_id} root translation delta",
        )
        root_orientation = _finite_number(
            root_invariant.get("maximum_orientation_delta_deg"),
            f"{episode_id} root orientation delta",
        )
        root_translation_tolerance = _finite_number(
            root_invariant.get("translation_tolerance_mm"),
            f"{episode_id} root translation tolerance",
        )
        root_orientation_tolerance = _finite_number(
            root_invariant.get("orientation_tolerance_deg"),
            f"{episode_id} root orientation tolerance",
        )
        if (
            receipt.get("schema") != STATE_POLICY_NATIVE_COLLISION_RECEIPT_SCHEMA
            or receipt.get("state_policy_episode_id") != episode_id
            or receipt.get("state_policy_target_id") != entry.get("target_id")
            or receipt.get("source_state_policy_request_sha256")
            != entry.get("state_policy_request_sha256")
            or receipt.get("source_runtime_revalidation_receipt_sha256")
            != entry.get("runtime_revalidation_receipt_sha256")
            or receipt.get("collision_screening_executed") is not True
            or receipt.get("fixed_base_replay_applied") is not True
            or root_invariant.get("status") != "PASS"
            or root_translation > root_translation_tolerance
            or root_orientation > root_orientation_tolerance
            or receipt.get("bounded_sample_count") != entry.get("bounded_sample_count")
            or receipt.get("status") not in {
                "DIAGNOSTIC_BLOCKERS_OBSERVED",
                "DIAGNOSTIC_OVERLAPS_OBSERVED",
                "DIAGNOSTIC_NO_OVERLAPS_OBSERVED",
            }
            or sum(classification_counts)
            != receipt.get("unique_collision_pair_count")
            or not isinstance(bindings, dict)
            or bindings.get("request_sha256")
            != entry.get("native_collision_request_sha256")
            or bindings.get("fixed_base_replay_plan_sha256")
            != entry.get("native_fixed_base_replay_plan_sha256")
        ):
            raise MechanicsContractError(f"{episode_id} native receipt boundary changed")
        total_samples += receipt["bounded_sample_count"]
        total_samples_with_overlaps += receipt["samples_with_overlaps"]
        blocker_episode_count += blocker_count > 0
        results.append({
            "episode_id": episode_id,
            "target_id": entry["target_id"],
            "receipt_sha256": receipt["receipt_sha256"],
            "status": receipt["status"],
            "bounded_sample_count": receipt["bounded_sample_count"],
            "samples_with_overlaps": receipt["samples_with_overlaps"],
            "blocker_pair_count": blocker_count,
        })
    if total_samples != manifest.get("total_bounded_sample_count"):
        raise MechanicsContractError("native collision result sample denominator changed")
    campaign: dict[str, Any] = {
        "schema": STATE_POLICY_NATIVE_COLLISION_CAMPAIGN_SCHEMA,
        "status": "COMPLETE_ZERO_AUTHORITY_COLLISION_DIAGNOSTICS_WITH_BLOCKERS"
        if blocker_episode_count
        else "COMPLETE_ZERO_AUTHORITY_COLLISION_DIAGNOSTICS_NO_BLOCKERS_OBSERVED",
        "source_manifest_sha256": manifest["manifest_sha256"],
        "source_runtime_revalidation_campaign_sha256": manifest[
            "source_runtime_revalidation_campaign_sha256"
        ],
        "source_dataset_sha256": manifest["source_dataset_sha256"],
        "source_model_sha256": manifest["source_model_sha256"],
        "episode_count": len(results),
        "collision_diagnostics_executed": len(results),
        "total_bounded_sample_count": total_samples,
        "total_samples_with_overlaps": total_samples_with_overlaps,
        "blocker_episode_count": blocker_episode_count,
        "results": results,
        "isaac_started": True,
        "gpu_started": True,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "native_replay_authorized": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "next_required_stage": "REVIEW_LM4_COLLISION_DIAGNOSTIC_RESULTS",
        "limitations": [
            "discrete_overlap_queries_are_not_continuous_collision_proof",
            "exploratory_uninstalled_geometry_cannot_promote_installed_clearance",
            "no_native_contact_or_physical_replay_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign


def review_state_policy_native_collision_campaign(
    campaign: dict[str, Any],
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Independently review ARM-220 before mechanics-plan compilation."""
    _verify_lm3_digest(campaign, "campaign_sha256", "native collision campaign")
    _verify_lm3_digest(manifest, "manifest_sha256", "native collision manifest")
    _require_lm3_zero_authority(campaign, "native collision campaign")
    _require_lm3_zero_authority(manifest, "native collision manifest")
    entries = manifest.get("entries")
    results = campaign.get("results")
    if (
        campaign.get("schema") != STATE_POLICY_NATIVE_COLLISION_CAMPAIGN_SCHEMA
        or campaign.get("status")
        != "COMPLETE_ZERO_AUTHORITY_COLLISION_DIAGNOSTICS_NO_BLOCKERS_OBSERVED"
        or campaign.get("next_required_stage")
        != "REVIEW_LM4_COLLISION_DIAGNOSTIC_RESULTS"
        or campaign.get("source_manifest_sha256") != manifest["manifest_sha256"]
        or campaign.get("blocker_episode_count") != 0
        or campaign.get("collision_diagnostics_executed")
        != campaign.get("episode_count")
        or campaign.get("installed_collision_qualified") is not False
        or campaign.get("continuous_collision_proven") is not False
        or campaign.get("native_replay_authorized") is not False
        or manifest.get("schema") != STATE_POLICY_NATIVE_COLLISION_MANIFEST_SCHEMA
        or manifest.get("status")
        != "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_COLLISION_DIAGNOSTICS"
        or campaign.get("episode_count") != manifest.get("episode_count")
        or campaign.get("total_bounded_sample_count")
        != manifest.get("total_bounded_sample_count")
        or campaign.get("source_runtime_revalidation_campaign_sha256")
        != manifest.get("source_runtime_revalidation_campaign_sha256")
        or campaign.get("source_dataset_sha256")
        != manifest.get("source_dataset_sha256")
        or campaign.get("source_model_sha256") != manifest.get("source_model_sha256")
        or not isinstance(entries, list)
        or not entries
        or not isinstance(results, list)
        or len(results) != len(entries)
    ):
        raise MechanicsContractError("LM4 collision review boundary changed")

    entries_by_id = {
        row.get("episode_id"): row for row in entries if isinstance(row, dict)
    }
    results_by_id = {
        row.get("episode_id"): row for row in results if isinstance(row, dict)
    }
    if (
        None in entries_by_id
        or None in results_by_id
        or len(entries_by_id) != len(entries)
        or len(results_by_id) != len(results)
        or set(entries_by_id) != set(results_by_id)
        or set(entries_by_id) != set(receipts)
    ):
        raise MechanicsContractError("LM4 collision review denominator changed")

    accepted_pairs = {
        ("robot:base_link", "robot:link1"),
        ("robot:gripper", "robot:link5"),
        ("robot:link1", "robot:link2"),
        ("robot:link2", "robot:link3"),
        ("robot:link3", "robot:link4"),
    }
    reviewed = []
    total_samples = 0
    total_overlap_samples = 0
    maximum_root_translation_delta_mm = 0.0
    maximum_root_orientation_delta_deg = 0.0
    target_episode_counts: Counter[str] = Counter()
    for episode_id, entry in entries_by_id.items():
        result = results_by_id[episode_id]
        receipt = receipts[episode_id]
        _verify_lm3_digest(receipt, "receipt_sha256", f"{episode_id} native receipt")
        _require_lm3_zero_authority(receipt, f"{episode_id} native receipt")
        root = receipt.get("root_pose_invariant")
        samples = receipt.get("samples")
        pair_observations = receipt.get("pair_observations")
        observed_pairs = {
            tuple(row.get("body_pair", []))
            for row in pair_observations or []
            if isinstance(row, dict)
        }
        if (
            result.get("target_id") != entry.get("target_id")
            or result.get("receipt_sha256") != receipt.get("receipt_sha256")
            or result.get("bounded_sample_count") != entry.get("bounded_sample_count")
            or result.get("bounded_sample_count") != receipt.get("bounded_sample_count")
            or result.get("samples_with_overlaps")
            != receipt.get("samples_with_overlaps")
            or result.get("blocker_pair_count") != 0
            or receipt.get("schema") != STATE_POLICY_NATIVE_COLLISION_RECEIPT_SCHEMA
            or receipt.get("state_policy_episode_id") != episode_id
            or receipt.get("state_policy_target_id") != entry.get("target_id")
            or receipt.get("source_state_policy_request_sha256")
            != entry.get("state_policy_request_sha256")
            or receipt.get("source_runtime_revalidation_receipt_sha256")
            != entry.get("runtime_revalidation_receipt_sha256")
            or receipt.get("collision_screening_executed") is not True
            or receipt.get("fixed_base_replay_applied") is not True
            or receipt.get("status") not in {
                "DIAGNOSTIC_OVERLAPS_OBSERVED",
                "DIAGNOSTIC_NO_OVERLAPS_OBSERVED",
            }
            or receipt.get("physical_solid_blocker_pair_count") != 0
            or receipt.get("planning_envelope_blocker_pair_count") != 0
            or receipt.get("unreviewed_blocker_pair_count") != 0
            or receipt.get("policy_excluded_pair_count") != len(accepted_pairs)
            or observed_pairs != accepted_pairs
            or any(
                row.get("classification")
                != "ACCEPTED_DIAGNOSTIC_KINEMATIC_NEIGHBOR_EXCLUSION"
                for row in pair_observations or []
            )
            or not isinstance(root, dict)
            or root.get("status") != "PASS"
            or not isinstance(samples, list)
            or len(samples) != entry.get("bounded_sample_count")
        ):
            raise MechanicsContractError(
                f"{episode_id} LM4 collision review evidence changed"
            )
        translation = _finite_number(
            root.get("maximum_translation_delta_mm"),
            f"{episode_id} review root translation",
        )
        orientation = _finite_number(
            root.get("maximum_orientation_delta_deg"),
            f"{episode_id} review root orientation",
        )
        if (
            translation
            > _finite_number(
                root.get("translation_tolerance_mm"),
                f"{episode_id} review translation tolerance",
            )
            or orientation
            > _finite_number(
                root.get("orientation_tolerance_deg"),
                f"{episode_id} review orientation tolerance",
            )
        ):
            raise MechanicsContractError(
                f"{episode_id} LM4 collision review root invariant changed"
            )
        for sequence, sample in enumerate(samples):
            raw_pairs = {tuple(pair) for pair in sample.get("raw_collision_pairs", [])}
            excluded_pairs = {
                tuple(pair) for pair in sample.get("policy_excluded_pairs", [])
            }
            if (
                sample.get("sample_sequence") != sequence
                or raw_pairs != accepted_pairs
                or excluded_pairs != accepted_pairs
                or sample.get("raw_collision_pair_count") != len(accepted_pairs)
                or sample.get("policy_excluded_pair_count") != len(accepted_pairs)
                or sample.get("physical_solid_blocker_pairs") != []
                or sample.get("planning_envelope_blocker_pairs") != []
                or sample.get("unreviewed_blocker_pairs") != []
                or sample.get("remaining_blocker_pair_count") != 0
            ):
                raise MechanicsContractError(
                    f"{episode_id} LM4 collision review sample {sequence} changed"
                )
        total_samples += len(samples)
        total_overlap_samples += receipt["samples_with_overlaps"]
        maximum_root_translation_delta_mm = max(
            maximum_root_translation_delta_mm, translation
        )
        maximum_root_orientation_delta_deg = max(
            maximum_root_orientation_delta_deg, orientation
        )
        target_episode_counts[str(entry["target_id"])] += 1
        reviewed.append({
            "episode_id": episode_id,
            "target_id": entry["target_id"],
            "bounded_sample_count": len(samples),
            "receipt_sha256": receipt["receipt_sha256"],
            "accepted_policy_excluded_pair_count": len(accepted_pairs),
            "blocker_pair_count": 0,
            "root_pose_invariant_status": "PASS",
        })
    if (
        total_samples != campaign.get("total_bounded_sample_count")
        or total_overlap_samples != campaign.get("total_samples_with_overlaps")
    ):
        raise MechanicsContractError("LM4 collision review sample denominator changed")

    review: dict[str, Any] = {
        "schema": STATE_POLICY_NATIVE_COLLISION_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_MECHANICS_PLAN_COMPILATION",
        "source_campaign_sha256": campaign["campaign_sha256"],
        "source_manifest_sha256": manifest["manifest_sha256"],
        "source_runtime_revalidation_campaign_sha256": campaign[
            "source_runtime_revalidation_campaign_sha256"
        ],
        "source_dataset_sha256": campaign["source_dataset_sha256"],
        "source_model_sha256": campaign["source_model_sha256"],
        "episode_count": len(reviewed),
        "total_bounded_sample_count": total_samples,
        "total_samples_with_accepted_exclusions": total_overlap_samples,
        "target_episode_counts": dict(sorted(target_episode_counts.items())),
        "accepted_policy_excluded_pairs": [
            list(pair) for pair in sorted(accepted_pairs)
        ],
        "maximum_root_translation_delta_mm": maximum_root_translation_delta_mm,
        "maximum_root_orientation_delta_deg": maximum_root_orientation_delta_deg,
        "reviewed_episodes": reviewed,
        "review_decision": {
            "collision_diagnostic_denominator_complete": True,
            "all_raw_pairs_exactly_accepted_exclusions": True,
            "physical_solid_blockers_absent": True,
            "planning_envelope_blockers_absent": True,
            "unreviewed_blockers_absent": True,
            "fixed_base_root_invariants_passed": True,
            "mechanics_plan_compilation_allowed": True,
            "mechanics_replay_execution_authorized": False,
        },
        "next_required_stage": "COMPILE_LM4_ZERO_AUTHORITY_MECHANICS_REPLAY_PLANS",
        "isaac_started": False,
        "gpu_started": False,
        "mechanics_replay_executed": False,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "native_replay_authorized": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "limitations": [
            "review_accepts_only_zero_authority_mechanics_plan_compilation",
            "discrete_overlap_queries_are_not_continuous_collision_proof",
            "exploratory_uninstalled_geometry_cannot_promote_installed_clearance",
            "mechanics_contact_tracking_settling_and_release_remain_unevaluated",
            "no_native_replay_or_physical_motion_authority",
        ],
    }
    review["review_sha256"] = _canonical_sha256(review)
    return review


def compile_state_policy_mechanics_replay_campaign(
    review: dict[str, Any],
    dataset_manifest: dict[str, Any],
    proposal_campaign: dict[str, Any],
    proposal_payloads: dict[str, bytes],
    collision_request_campaign: dict[str, Any],
    collision_requests: dict[str, dict[str, Any]],
    native_collision_manifest: dict[str, Any],
    source_mechanics_campaign: dict[str, Any],
    source_mechanics_result: dict[str, Any],
    source_mechanics_receipts: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compile collision-reviewed LM4 proposals into non-executing mechanics plans."""
    for document, digest_key, label in (
        (review, "review_sha256", "ARM-221 collision review"),
        (dataset_manifest, "dataset_sha256", "state-policy dataset"),
        (proposal_campaign, "campaign_sha256", "state-policy proposal campaign"),
        (
            collision_request_campaign,
            "campaign_sha256",
            "state-policy collision request campaign",
        ),
        (
            native_collision_manifest,
            "manifest_sha256",
            "state-policy native collision manifest",
        ),
        (
            source_mechanics_campaign,
            "campaign_sha256",
            "representative mechanics campaign",
        ),
        (
            source_mechanics_result,
            "campaign_sha256",
            "representative mechanics result",
        ),
    ):
        _verify_lm3_digest(document, digest_key, label)
        _require_lm3_zero_authority(document, label)
    if (
        review.get("schema") != STATE_POLICY_NATIVE_COLLISION_REVIEW_SCHEMA
        or review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_MECHANICS_PLAN_COMPILATION"
        or review.get("next_required_stage")
        != "COMPILE_LM4_ZERO_AUTHORITY_MECHANICS_REPLAY_PLANS"
        or review.get("review_decision", {}).get(
            "mechanics_plan_compilation_allowed"
        )
        is not True
        or review.get("review_decision", {}).get(
            "mechanics_replay_execution_authorized"
        )
        is not False
        or dataset_manifest.get("schema") != STATE_POLICY_DATASET_MANIFEST_SCHEMA
        or dataset_manifest.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_DATASET"
        or dataset_manifest.get("dataset_sha256")
        != review.get("source_dataset_sha256")
        or proposal_campaign.get("schema")
        != STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN_SCHEMA
        or proposal_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_QUALIFICATION"
        or proposal_campaign.get("source_dataset_sha256")
        != dataset_manifest.get("dataset_sha256")
        or proposal_campaign.get("source_model_sha256")
        != review.get("source_model_sha256")
        or collision_request_campaign.get("schema")
        != STATE_POLICY_COLLISION_REQUEST_CAMPAIGN_SCHEMA
        or collision_request_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION"
        or collision_request_campaign.get("source_dataset_sha256")
        != dataset_manifest.get("dataset_sha256")
        or collision_request_campaign.get("source_model_sha256")
        != proposal_campaign.get("source_model_sha256")
        or collision_request_campaign.get("source_proposal_campaign_sha256")
        != proposal_campaign.get("campaign_sha256")
        or native_collision_manifest.get("schema")
        != STATE_POLICY_NATIVE_COLLISION_MANIFEST_SCHEMA
        or native_collision_manifest.get("manifest_sha256")
        != review.get("source_manifest_sha256")
        or source_mechanics_campaign.get("schema")
        != REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_CAMPAIGN_SCHEMA
        or source_mechanics_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_MECHANICS_REPLAY"
        or source_mechanics_result.get("schema")
        != REPRESENTATIVE_KEY_NATIVE_MECHANICS_RESULT_CAMPAIGN_SCHEMA
        or source_mechanics_result.get("status")
        != "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_MECHANICS_CAMPAIGN"
        or source_mechanics_result.get("source_replay_campaign_sha256")
        != source_mechanics_campaign.get("campaign_sha256")
        or source_mechanics_result.get("accepted_action_count") != 8
    ):
        raise MechanicsContractError("LM4 mechanics compilation boundary changed")

    proposal_rows = proposal_campaign.get("episodes")
    request_rows = collision_request_campaign.get("requests")
    native_entries = native_collision_manifest.get("entries")
    review_rows = review.get("reviewed_episodes")
    dataset_rows = dataset_manifest.get("episodes")
    source_plans = source_mechanics_campaign.get("plans")
    source_results = source_mechanics_result.get("results")
    if not all(
        isinstance(rows, list) and rows
        for rows in (
            proposal_rows,
            request_rows,
            native_entries,
            review_rows,
            dataset_rows,
            source_plans,
            source_results,
        )
    ):
        raise MechanicsContractError("LM4 mechanics compilation sources are incomplete")

    def by_identity(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
        mapped = {
            row.get(key): row for row in rows if isinstance(row, dict)
        }
        if None in mapped or len(mapped) != len(rows):
            raise MechanicsContractError(f"{label} identities changed")
        return mapped

    proposals_by_id = by_identity(proposal_rows, "episode_id", "proposal episode")
    requests_by_id = by_identity(request_rows, "episode_id", "collision request")
    native_by_id = by_identity(native_entries, "episode_id", "native collision")
    review_by_id = by_identity(review_rows, "episode_id", "collision review")
    dataset_by_id = by_identity(dataset_rows, "episode_id", "dataset episode")
    source_plans_by_target = by_identity(
        source_plans, "target_id", "source mechanics plan"
    )
    source_results_by_target = by_identity(
        source_results, "target_id", "source mechanics result"
    )
    episode_ids = set(proposals_by_id)
    if (
        episode_ids != set(requests_by_id)
        or episode_ids != set(native_by_id)
        or episode_ids != set(review_by_id)
        or episode_ids != set(proposal_payloads)
        or episode_ids != set(collision_requests)
        or len(episode_ids) != review.get("episode_count")
        or len(episode_ids) != proposal_campaign.get("held_out_episode_count")
        or set(source_plans_by_target) != set(REPRESENTATIVE_KEYS[1:])
        or set(source_results_by_target) != set(REPRESENTATIVE_KEYS[1:])
        or set(source_mechanics_receipts) != set(REPRESENTATIVE_KEYS[1:])
    ):
        raise MechanicsContractError("LM4 mechanics compilation denominator changed")

    plans: dict[str, dict[str, Any]] = {}
    entries = []
    total_targets = 0
    target_episode_counts: Counter[str] = Counter()
    maximum_adjacent_step = 0.0
    for episode in proposal_rows:
        episode_id = episode["episode_id"]
        target_id = episode["target_id"]
        request_row = requests_by_id[episode_id]
        native_entry = native_by_id[episode_id]
        review_row = review_by_id[episode_id]
        dataset_row = dataset_by_id.get(episode_id)
        request = collision_requests[episode_id]
        source_plan = source_plans_by_target.get(target_id)
        source_result = source_results_by_target.get(target_id)
        source_receipt = source_mechanics_receipts.get(target_id)
        if not all(
            isinstance(item, dict)
            for item in (dataset_row, source_plan, source_result, source_receipt)
        ):
            raise MechanicsContractError(
                f"{episode_id} LM4 mechanics source evidence is absent"
            )
        for document, digest_key, label in (
            (request, "request_sha256", "state-policy collision request"),
            (source_plan, "plan_sha256", "source mechanics plan"),
            (source_receipt, "receipt_sha256", "source mechanics receipt"),
        ):
            _verify_lm3_digest(document, digest_key, f"{episode_id} {label}")
            _require_lm3_zero_authority(document, f"{episode_id} {label}")
        payload = proposal_payloads[episode_id]
        if hashlib.sha256(payload).hexdigest() != episode.get(
            "proposal_trajectory_sha256"
        ):
            raise MechanicsContractError(
                f"{episode_id} LM4 mechanics proposal digest changed"
            )
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
        if (
            target_id not in REPRESENTATIVE_KEYS
            or request_row.get("target_id") != target_id
            or native_entry.get("target_id") != target_id
            or review_row.get("target_id") != target_id
            or dataset_row.get("target_id") != target_id
            or dataset_row.get("role") != "EVALUATION"
            or dataset_row.get("disposition") != "PASS"
            or dataset_row.get("partition") != episode.get("partition")
            or dataset_row.get("scene_id") != episode.get("scene_id")
            or dataset_row.get("seed") != episode.get("seed")
            or dataset_row.get("receipt_sha256")
            != episode.get("source_receipt_sha256")
            or request.get("schema") != STATE_POLICY_COLLISION_REQUEST_SCHEMA
            or request.get("request_sha256") != request_row.get("request_sha256")
            or request.get("request_sha256")
            != native_entry.get("state_policy_request_sha256")
            or request.get("source_dataset_sha256")
            != dataset_manifest.get("dataset_sha256")
            or request.get("source_model_sha256")
            != proposal_campaign.get("source_model_sha256")
            or request.get("source_proposal_campaign_sha256")
            != proposal_campaign.get("campaign_sha256")
            or request.get("source_proposal_trajectory_sha256")
            != episode.get("proposal_trajectory_sha256")
            or (
                source_plan.get("schema"), source_plan.get("status")
            )
            not in {
                (
                    REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_REPLAY_PLAN_SCHEMA,
                    "READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_KEY_MECHANICS_REPLAY",
                ),
                (
                    REPRESENTATIVE_KEY_FEEDBACK_ADAPTED_MECHANICS_REPLAY_PLAN_SCHEMA,
                    "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_KEY_MECHANICS_REPLAY",
                ),
            }
            or source_receipt.get("schema")
            != REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA
            or source_receipt.get("status") != "PASS"
            or source_receipt.get("source_plan_sha256")
            != source_plan.get("plan_sha256")
            or source_result.get("plan_sha256") != source_plan.get("plan_sha256")
            or source_result.get("receipt_sha256")
            != source_receipt.get("receipt_sha256")
            or source_result.get("action_count") != 2
            or source_result.get("root_pose_invariant_passed") is not True
            or len(rows) != episode.get("proposal_sample_count")
            or len(rows) != dataset_row.get("sample_count")
        ):
            raise MechanicsContractError(
                f"{episode_id} LM4 mechanics lineage changed"
            )
        randomized_parameters = _validate_randomized_replay_parameters(
            dataset_row.get("randomized_parameters")
        )
        randomized_key_center = dataset_row.get("randomized_key_center_board_xy_mm")
        if (
            not isinstance(randomized_key_center, list)
            or len(randomized_key_center) != 2
        ):
            raise MechanicsContractError(
                f"{episode_id} LM4 randomized key center changed"
            )
        randomized_key_center = [
            _finite_number(value, f"{episode_id} randomized key center")
            for value in randomized_key_center
        ]

        previous_time = -math.inf
        previous_action: list[float] | None = None
        episode_maximum_step = 0.0
        contact_indices: dict[int, list[int]] = {0: [], 1: []}
        joint_targets = []
        for sequence, row in enumerate(rows):
            action = row.get("joint_position_proposal_rad")
            time_s = _finite_number(row.get("time_s"), f"{episode_id} proposal time")
            action_index = row.get("action_index")
            phase = row.get("phase")
            target_sequence = row.get("target_sequence")
            if (
                row.get("schema") != STATE_POLICY_PROPOSAL_ROW_SCHEMA
                or row.get("source_episode_id") != episode_id
                or row.get("source_row_index") != sequence
                or row.get("target_id") != target_id
                or phase not in STATE_POLICY_PHASES
                or action_index not in (None, 0, 1)
                or not isinstance(target_sequence, int)
                or isinstance(target_sequence, bool)
                or not isinstance(action, list)
                or len(action) != 6
                or time_s <= previous_time
            ):
                raise MechanicsContractError(
                    f"{episode_id} LM4 mechanics proposal row {sequence} changed"
                )
            action = [
                _finite_number(value, f"{episode_id} proposal joint")
                for value in action
            ]
            if previous_action is not None:
                episode_maximum_step = max(
                    episode_maximum_step,
                    max(
                        abs(right - left)
                        for left, right in zip(previous_action, action, strict=True)
                    ),
                )
            if phase == "CONTACT":
                if action_index not in (0, 1):
                    raise MechanicsContractError(
                        f"{episode_id} contact row lacks an action identity"
                    )
                contact_indices[action_index].append(sequence)
            joint_targets.append({
                "sequence": sequence,
                "time_from_start_ns": round(time_s * 1e9),
                "phase": phase,
                "target_id": target_id,
                "action_index": action_index,
                "source_target_sequence": target_sequence,
                "phase_endpoint": False,
                "joint_position_target_rad": action,
            })
            previous_time = time_s
            previous_action = action
        if any(not indices for indices in contact_indices.values()):
            raise MechanicsContractError(
                f"{episode_id} LM4 mechanics contact endpoints are incomplete"
            )
        contact_endpoints = [
            contact_indices[action_index][-1] for action_index in (0, 1)
        ]
        for endpoint in contact_endpoints:
            joint_targets[endpoint]["phase_endpoint"] = True

        source_bindings = source_plan.get("source_bindings")
        if (
            not isinstance(source_bindings, dict)
            or source_plan.get("joint_order") != dataset_manifest.get("joint_order")
            or source_plan.get("target_id") != target_id
            or not isinstance(source_plan.get("target_region"), dict)
            or not isinstance(source_plan.get("robot_placement_matrix_row_major"), list)
            or source_plan.get("execution_contract", {}).get(
                "maximum_joint_tracking_error_rad"
            )
            != 0.05
        ):
            raise MechanicsContractError(
                f"{episode_id} LM4 mechanics source contract changed"
            )
        plan: dict[str, Any] = {
            "schema": STATE_POLICY_MECHANICS_REPLAY_PLAN_SCHEMA,
            "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_RUNTIME_ADMISSION",
            "episode_id": episode_id,
            "target_id": target_id,
            "partition": episode["partition"],
            "scene_id": episode["scene_id"],
            "seed": episode["seed"],
            "joint_order": list(dataset_manifest["joint_order"]),
            "sample_count": len(joint_targets),
            "action_count": 2,
            "contact_endpoint_sequences": contact_endpoints,
            "joint_targets": joint_targets,
            "maximum_uninterpolated_adjacent_joint_step_rad": episode_maximum_step,
            "collision_screened_bounded_sample_count": request[
                "bounded_sample_count"
            ],
            "target_region": dict(source_plan["target_region"]),
            "robot_placement_matrix_row_major": list(
                source_plan["robot_placement_matrix_row_major"]
            ),
            "randomized_parameters": randomized_parameters,
            "randomized_key_center_board_xy_mm": randomized_key_center,
            "source_bindings": {
                "arm221_collision_review_sha256": review["review_sha256"],
                "arm220_native_manifest_sha256": native_collision_manifest[
                    "manifest_sha256"
                ],
                "arm220_native_receipt_sha256": review_row["receipt_sha256"],
                "state_policy_dataset_sha256": dataset_manifest["dataset_sha256"],
                "state_policy_model_sha256": proposal_campaign[
                    "source_model_sha256"
                ],
                "state_policy_proposal_campaign_sha256": proposal_campaign[
                    "campaign_sha256"
                ],
                "state_policy_proposal_trajectory_sha256": episode[
                    "proposal_trajectory_sha256"
                ],
                "state_policy_collision_request_sha256": request[
                    "request_sha256"
                ],
                "representative_mechanics_campaign_sha256": (
                    source_mechanics_campaign["campaign_sha256"]
                ),
                "representative_mechanics_result_sha256": source_mechanics_result[
                    "campaign_sha256"
                ],
                "representative_mechanics_plan_schema": source_plan["schema"],
                "representative_mechanics_plan_status": source_plan["status"],
                "representative_mechanics_plan_sha256": source_plan["plan_sha256"],
                "representative_mechanics_receipt_sha256": source_receipt[
                    "receipt_sha256"
                ],
                **{
                    key: source_bindings[key]
                    for key in (
                        "key_mechanics_profile_sha256",
                        "virtual_profile_sha256",
                        "drive_profile_file_sha256",
                        "robot_import_receipt_sha256",
                        "robot_usd_sha256",
                    )
                },
            },
            "proposal_semantics": {
                "proposal_targets_preserved_without_interpolation": True,
                "collision_interpolation_not_promoted_to_motion_commands": True,
                "source_contact_refinement_reapplied": False,
                "randomized_reset_preserved": True,
            },
            "execution_contract": {
                "initial_joint_state_placement_count": 1,
                "post_initialization_state_teleports": 0,
                "subsequent_joint_commands": "ARTICULATION_POSITION_TARGETS_ONLY",
                "key_motion_source": "NATIVE_CONTACT_ONLY",
                "root_pose_invariant_required_after_every_sample": True,
                "maximum_joint_tracking_error_rad": 0.05,
                "randomized_key_mechanics_required": True,
            },
            "runtime_admission_required": True,
            "native_mechanics_replay_executed": False,
            "native_replay_authorized": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "gate_promotions": [],
            "limitations": [
                "compiled_plan_does_not_start_isaac_or_a_gpu",
                "proposal_targets_require_fresh_runtime_file_revalidation",
                "contact_release_settling_tracking_and_abstention_are_unevaluated",
                "collision_screen_is_discrete_not_continuous_clearance_proof",
                "exploratory_uninstalled_geometry_cannot_authorize_physical_motion",
            ],
        }
        plan["plan_sha256"] = _canonical_sha256(plan)
        plans[episode_id] = plan
        total_targets += len(joint_targets)
        target_episode_counts[target_id] += 1
        maximum_adjacent_step = max(maximum_adjacent_step, episode_maximum_step)
        entries.append({
            "episode_id": episode_id,
            "target_id": target_id,
            "partition": episode["partition"],
            "scene_id": episode["scene_id"],
            "sample_count": len(joint_targets),
            "collision_screened_bounded_sample_count": request[
                "bounded_sample_count"
            ],
            "contact_endpoint_sequences": contact_endpoints,
            "maximum_uninterpolated_adjacent_joint_step_rad": episode_maximum_step,
            "proposal_trajectory_sha256": episode["proposal_trajectory_sha256"],
            "collision_request_sha256": request["request_sha256"],
            "mechanics_plan_sha256": plan["plan_sha256"],
        })
    if (
        total_targets != proposal_campaign.get("proposal_sample_count")
        or sum(
            row["collision_screened_bounded_sample_count"] for row in entries
        )
        != review.get("total_bounded_sample_count")
    ):
        raise MechanicsContractError("LM4 mechanics compiled sample denominator changed")
    campaign: dict[str, Any] = {
        "schema": STATE_POLICY_MECHANICS_REPLAY_CAMPAIGN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_RUNTIME_ADMISSION",
        "source_review_sha256": review["review_sha256"],
        "source_dataset_sha256": dataset_manifest["dataset_sha256"],
        "source_model_sha256": proposal_campaign["source_model_sha256"],
        "source_proposal_campaign_sha256": proposal_campaign["campaign_sha256"],
        "source_collision_request_campaign_sha256": collision_request_campaign[
            "campaign_sha256"
        ],
        "source_native_collision_manifest_sha256": native_collision_manifest[
            "manifest_sha256"
        ],
        "source_representative_mechanics_campaign_sha256": (
            source_mechanics_campaign["campaign_sha256"]
        ),
        "source_representative_mechanics_result_sha256": source_mechanics_result[
            "campaign_sha256"
        ],
        "episode_count": len(entries),
        "total_joint_target_count": total_targets,
        "total_collision_screened_bounded_sample_count": sum(
            row["collision_screened_bounded_sample_count"] for row in entries
        ),
        "target_episode_counts": dict(sorted(target_episode_counts.items())),
        "maximum_uninterpolated_adjacent_joint_step_rad": maximum_adjacent_step,
        "entries": entries,
        "runtime_admissions_completed": 0,
        "runtime_files_revalidated": False,
        "isaac_started": False,
        "gpu_started": False,
        "native_mechanics_replays_executed": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "next_required_stage": "ADMIT_AND_REVALIDATE_LM4_MECHANICS_RUNTIME_INPUTS",
        "limitations": [
            "plans_are_compiled_but_not_runtime_admitted_or_executed",
            "all_nine_mechanics_replays_remain_pending",
            "no_native_replay_or_physical_motion_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign, plans


def admit_state_policy_mechanics_runtime_inputs(
    mechanics_campaign: dict[str, Any],
    mechanics_plans: dict[str, dict[str, Any]],
    mechanics_profile: dict[str, Any],
    virtual_profile_bytes: bytes,
    drive_profile_bytes: bytes,
    robot_import_receipt: dict[str, Any],
    robot_usd_bytes: bytes,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Reload ARM-222 plans and runtime files without starting Isaac or a GPU."""
    _verify_lm3_digest(
        mechanics_campaign, "campaign_sha256", "mechanics replay campaign"
    )
    _require_lm3_zero_authority(mechanics_campaign, "mechanics replay campaign")
    entries = mechanics_campaign.get("entries")
    if (
        mechanics_campaign.get("schema")
        != STATE_POLICY_MECHANICS_REPLAY_CAMPAIGN_SCHEMA
        or mechanics_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_RUNTIME_ADMISSION"
        or mechanics_campaign.get("next_required_stage")
        != "ADMIT_AND_REVALIDATE_LM4_MECHANICS_RUNTIME_INPUTS"
        or mechanics_campaign.get("runtime_admissions_completed") != 0
        or mechanics_campaign.get("runtime_files_revalidated") is not False
        or mechanics_campaign.get("isaac_started") is not False
        or mechanics_campaign.get("gpu_started") is not False
        or mechanics_campaign.get("native_mechanics_replays_executed") != 0
        or not isinstance(entries, list)
        or not entries
        or len(entries) != mechanics_campaign.get("episode_count")
    ):
        raise MechanicsContractError("LM4 mechanics runtime admission boundary changed")
    entries_by_id = {
        row.get("episode_id"): row for row in entries if isinstance(row, dict)
    }
    if (
        None in entries_by_id
        or len(entries_by_id) != len(entries)
        or set(entries_by_id) != set(mechanics_plans)
    ):
        raise MechanicsContractError("LM4 mechanics runtime denominator changed")

    _verify_lm3_digest(mechanics_profile, "profile_sha256", "mechanics profile")
    _require_lm3_zero_authority(mechanics_profile, "mechanics profile")
    virtual_profile = json.loads(virtual_profile_bytes)
    drive_profile = json.loads(drive_profile_bytes)
    _verify_lm3_digest(
        robot_import_receipt, "receipt_sha256", "robot import receipt"
    )
    _require_lm3_zero_authority(robot_import_receipt, "robot import receipt")
    _require_lm3_zero_authority(drive_profile, "drive profile")
    robot_usd_sha256 = hashlib.sha256(robot_usd_bytes).hexdigest()
    external_files = robot_import_receipt.get("external_files")
    if (
        mechanics_profile.get("schema") != PROFILE_SCHEMA
        or virtual_profile.get("schema")
        != "rocell.virtual_commissioning_profile.v1"
        or virtual_profile.get("status") != "UNMEASURED_SENSITIVITY_OVERLAY"
        or virtual_profile.get("simulation_only") is not True
        or virtual_profile.get("physical_release_effect") != "NONE"
        or drive_profile.get("schema") != GEOMETRY_PRIOR_PROFILE_SCHEMA
        or drive_profile.get("status") != "PROVISIONAL_SIMULATION_ONLY"
        or drive_profile.get("simulation_only") is not True
        or drive_profile.get("physical_authority") is not False
        or robot_import_receipt.get("schema")
        != "tactevra.isaac_sim_urdf_import.v1"
        or not isinstance(external_files, list)
        or len(external_files) != 1
        or external_files[0].get("sha256") != robot_usd_sha256
        or external_files[0].get("size_bytes") != len(robot_usd_bytes)
    ):
        raise MechanicsContractError("LM4 mechanics runtime file boundary changed")
    actual_hashes = {
        "key_mechanics_profile_sha256": mechanics_profile["profile_sha256"],
        "virtual_profile_sha256": hashlib.sha256(virtual_profile_bytes).hexdigest(),
        "drive_profile_file_sha256": hashlib.sha256(drive_profile_bytes).hexdigest(),
        "robot_import_receipt_sha256": robot_import_receipt["receipt_sha256"],
        "robot_usd_sha256": robot_usd_sha256,
    }
    file_evidence = {
        "key_mechanics_profile": {
            "sha256": actual_hashes["key_mechanics_profile_sha256"],
            "hash_mode": "CANONICAL_DOCUMENT_EXCLUDING_PROFILE_SHA256",
        },
        "virtual_profile": {
            "sha256": actual_hashes["virtual_profile_sha256"],
            "hash_mode": "RAW_FILE_BYTES",
        },
        "drive_profile": {
            "sha256": actual_hashes["drive_profile_file_sha256"],
            "hash_mode": "RAW_FILE_BYTES",
        },
        "robot_import_receipt": {
            "sha256": actual_hashes["robot_import_receipt_sha256"],
            "hash_mode": "CANONICAL_DOCUMENT_EXCLUDING_RECEIPT_SHA256",
        },
        "robot_usd": {
            "sha256": actual_hashes["robot_usd_sha256"],
            "hash_mode": "RAW_FILE_BYTES",
            "size_bytes": len(robot_usd_bytes),
        },
    }

    receipts: dict[str, dict[str, Any]] = {}
    receipt_rows = []
    total_targets = 0
    total_collision_samples = 0
    for episode_id, entry in entries_by_id.items():
        plan = mechanics_plans[episode_id]
        _verify_lm3_digest(plan, "plan_sha256", f"{episode_id} mechanics plan")
        _require_lm3_zero_authority(plan, f"{episode_id} mechanics plan")
        bindings = plan.get("source_bindings")
        joint_targets = plan.get("joint_targets")
        endpoints = plan.get("contact_endpoint_sequences")
        changed_runtime_files = []
        if isinstance(bindings, dict):
            changed_runtime_files = sorted(
                key for key, value in actual_hashes.items()
                if bindings.get(key) != value
            )
        if (
            plan.get("schema") != STATE_POLICY_MECHANICS_REPLAY_PLAN_SCHEMA
            or plan.get("status")
            != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_RUNTIME_ADMISSION"
            or plan.get("episode_id") != episode_id
            or plan.get("target_id") != entry.get("target_id")
            or plan.get("plan_sha256") != entry.get("mechanics_plan_sha256")
            or plan.get("sample_count") != entry.get("sample_count")
            or plan.get("collision_screened_bounded_sample_count")
            != entry.get("collision_screened_bounded_sample_count")
            or plan.get("runtime_admission_required") is not True
            or plan.get("native_mechanics_replay_executed") is not False
            or plan.get("native_replay_authorized") is not False
            or not isinstance(joint_targets, list)
            or len(joint_targets) != plan.get("sample_count")
            or not isinstance(endpoints, list)
            or len(endpoints) != 2
            or any(
                not isinstance(endpoint, int)
                or endpoint < 0
                or endpoint >= len(joint_targets)
                or joint_targets[endpoint].get("phase") != "CONTACT"
                or joint_targets[endpoint].get("phase_endpoint") is not True
                for endpoint in endpoints
            )
            or not isinstance(bindings, dict)
            or changed_runtime_files
        ):
            suffix = (
                ": " + ", ".join(changed_runtime_files)
                if changed_runtime_files else ""
            )
            raise MechanicsContractError(
                f"{episode_id} LM4 mechanics runtime lineage changed{suffix}"
            )
        receipt: dict[str, Any] = {
            "schema": STATE_POLICY_MECHANICS_RUNTIME_ADMISSION_SCHEMA,
            "status": (
                "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_INPUT_MATERIALIZATION"
            ),
            "episode_id": episode_id,
            "target_id": plan["target_id"],
            "source_mechanics_campaign_sha256": mechanics_campaign[
                "campaign_sha256"
            ],
            "source_mechanics_plan_sha256": plan["plan_sha256"],
            "joint_target_count": plan["sample_count"],
            "collision_screened_bounded_sample_count": plan[
                "collision_screened_bounded_sample_count"
            ],
            "contact_endpoint_sequences": list(endpoints),
            "runtime_files": file_evidence,
            "runtime_files_revalidated": True,
            "revalidated_file_count": 5,
            "isaac_started": False,
            "gpu_started": False,
            "mechanics_replay_executed": False,
            "native_replay_authorized": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "gate_promotions": [],
            "limitations": [
                "runtime_hash_match_does_not_measure_mechanics_outcomes",
                "isaac_and_gpu_have_not_started",
                "fresh_mechanics_replay_remains_pending",
                "no_native_or_physical_replay_authority",
            ],
        }
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        receipts[episode_id] = receipt
        receipt_rows.append({
            "episode_id": episode_id,
            "target_id": plan["target_id"],
            "receipt_sha256": receipt["receipt_sha256"],
            "source_mechanics_plan_sha256": plan["plan_sha256"],
            "joint_target_count": plan["sample_count"],
            "collision_screened_bounded_sample_count": plan[
                "collision_screened_bounded_sample_count"
            ],
        })
        total_targets += plan["sample_count"]
        total_collision_samples += plan["collision_screened_bounded_sample_count"]
    if (
        total_targets != mechanics_campaign.get("total_joint_target_count")
        or total_collision_samples
        != mechanics_campaign.get("total_collision_screened_bounded_sample_count")
    ):
        raise MechanicsContractError("LM4 mechanics runtime aggregate changed")

    campaign: dict[str, Any] = {
        "schema": STATE_POLICY_MECHANICS_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA,
        "status": (
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_INPUT_MATERIALIZATION"
        ),
        "source_mechanics_campaign_sha256": mechanics_campaign["campaign_sha256"],
        "admission_count": len(receipt_rows),
        "total_joint_target_count": total_targets,
        "total_collision_screened_bounded_sample_count": total_collision_samples,
        "admissions": receipt_rows,
        "runtime_files": file_evidence,
        "runtime_files_revalidated": True,
        "revalidated_file_count": 5,
        "isaac_started": False,
        "gpu_started": False,
        "mechanics_replays_executed": 0,
        "fresh_mechanics_replays_required": len(receipt_rows),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "next_required_stage": "MATERIALIZE_FRESH_LM4_MECHANICS_REPLAY_INPUTS",
        "limitations": [
            "admission_stops_before_mechanics_input_materialization",
            "runtime_hash_match_does_not_measure_mechanics_outcomes",
            "all_nine_fresh_mechanics_replays_remain_pending",
            "no_native_or_physical_replay_authority",
        ],
    }
    campaign["campaign_sha256"] = _canonical_sha256(campaign)
    return campaign, receipts


def materialize_state_policy_native_mechanics_inputs(
    admission_campaign: dict[str, Any],
    admission_receipts: dict[str, dict[str, Any]],
    mechanics_campaign: dict[str, Any],
    mechanics_plans: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Create fresh, signed mechanics replay inputs without starting Isaac."""
    for document, digest_key, label in (
        (admission_campaign, "campaign_sha256", "mechanics admission campaign"),
        (mechanics_campaign, "campaign_sha256", "mechanics replay campaign"),
    ):
        _verify_lm3_digest(document, digest_key, label)
        _require_lm3_zero_authority(document, label)
    admission_rows = admission_campaign.get("admissions")
    mechanics_rows = mechanics_campaign.get("entries")
    if (
        admission_campaign.get("schema")
        != STATE_POLICY_MECHANICS_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA
        or admission_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_INPUT_MATERIALIZATION"
        or admission_campaign.get("next_required_stage")
        != "MATERIALIZE_FRESH_LM4_MECHANICS_REPLAY_INPUTS"
        or admission_campaign.get("runtime_files_revalidated") is not True
        or admission_campaign.get("revalidated_file_count") != 5
        or admission_campaign.get("isaac_started") is not False
        or admission_campaign.get("gpu_started") is not False
        or admission_campaign.get("mechanics_replays_executed") != 0
        or not isinstance(admission_rows, list)
        or not admission_rows
        or len(admission_rows) != admission_campaign.get("admission_count")
        or mechanics_campaign.get("schema")
        != STATE_POLICY_MECHANICS_REPLAY_CAMPAIGN_SCHEMA
        or mechanics_campaign.get("status")
        != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_RUNTIME_ADMISSION"
        or mechanics_campaign.get("campaign_sha256")
        != admission_campaign.get("source_mechanics_campaign_sha256")
        or not isinstance(mechanics_rows, list)
        or not mechanics_rows
    ):
        raise MechanicsContractError("native mechanics materialization boundary changed")
    admissions_by_id = {
        row.get("episode_id"): row
        for row in admission_rows
        if isinstance(row, dict)
    }
    mechanics_by_id = {
        row.get("episode_id"): row
        for row in mechanics_rows
        if isinstance(row, dict)
    }
    denominator = set(admissions_by_id)
    if (
        None in denominator
        or None in mechanics_by_id
        or len(admissions_by_id) != len(admission_rows)
        or len(mechanics_by_id) != len(mechanics_rows)
        or denominator != set(mechanics_by_id)
        or denominator != set(admission_receipts)
        or denominator != set(mechanics_plans)
    ):
        raise MechanicsContractError("native mechanics denominator changed")

    runtime_binding_keys = {
        "key_mechanics_profile": "key_mechanics_profile_sha256",
        "virtual_profile": "virtual_profile_sha256",
        "drive_profile": "drive_profile_file_sha256",
        "robot_import_receipt": "robot_import_receipt_sha256",
        "robot_usd": "robot_usd_sha256",
    }
    native_plans: dict[str, dict[str, Any]] = {}
    entries = []
    total_targets = 0
    total_collision_samples = 0
    for episode_id, admission_row in admissions_by_id.items():
        receipt = admission_receipts[episode_id]
        plan = mechanics_plans[episode_id]
        mechanics_row = mechanics_by_id[episode_id]
        for document, digest_key, label in (
            (receipt, "receipt_sha256", "runtime admission"),
            (plan, "plan_sha256", "mechanics plan"),
        ):
            _verify_lm3_digest(document, digest_key, f"{episode_id} {label}")
            _require_lm3_zero_authority(document, f"{episode_id} {label}")
        runtime_files = receipt.get("runtime_files")
        campaign_runtime_files = admission_campaign.get("runtime_files")
        bindings = plan.get("source_bindings")
        joint_targets = plan.get("joint_targets")
        endpoints = plan.get("contact_endpoint_sequences")
        runtime_lineage_matches = (
            isinstance(runtime_files, dict)
            and runtime_files == campaign_runtime_files
            and isinstance(bindings, dict)
            and all(
                isinstance(runtime_files.get(runtime_name), dict)
                and bindings.get(binding_name)
                == runtime_files[runtime_name].get("sha256")
                for runtime_name, binding_name in runtime_binding_keys.items()
            )
        )
        if (
            receipt.get("schema")
            != STATE_POLICY_MECHANICS_RUNTIME_ADMISSION_SCHEMA
            or receipt.get("status")
            != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_INPUT_MATERIALIZATION"
            or receipt.get("receipt_sha256") != admission_row.get("receipt_sha256")
            or receipt.get("source_mechanics_campaign_sha256")
            != mechanics_campaign["campaign_sha256"]
            or receipt.get("source_mechanics_plan_sha256") != plan.get("plan_sha256")
            or receipt.get("runtime_files_revalidated") is not True
            or receipt.get("revalidated_file_count") != 5
            or receipt.get("mechanics_replay_executed") is not False
            or plan.get("schema") != STATE_POLICY_MECHANICS_REPLAY_PLAN_SCHEMA
            or plan.get("status")
            != "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_RUNTIME_ADMISSION"
            or plan.get("plan_sha256") != mechanics_row.get("mechanics_plan_sha256")
            or plan.get("target_id") != admission_row.get("target_id")
            or plan.get("sample_count") != receipt.get("joint_target_count")
            or plan.get("sample_count") != admission_row.get("joint_target_count")
            or plan.get("collision_screened_bounded_sample_count")
            != receipt.get("collision_screened_bounded_sample_count")
            or plan.get("collision_screened_bounded_sample_count")
            != admission_row.get("collision_screened_bounded_sample_count")
            or not isinstance(joint_targets, list)
            or len(joint_targets) != plan.get("sample_count")
            or not isinstance(endpoints, list)
            or endpoints != receipt.get("contact_endpoint_sequences")
            or len(endpoints) != 2
            or not runtime_lineage_matches
        ):
            raise MechanicsContractError(
                f"{episode_id} native mechanics lineage changed"
            )

        native_plan = {
            key: value for key, value in plan.items() if key != "plan_sha256"
        }
        native_plan.update({
            "schema": STATE_POLICY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA,
            "status": "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_STATE_POLICY_MECHANICS_REPLAY",
            "source_mechanics_plan_sha256": plan["plan_sha256"],
            "source_runtime_admission_campaign_sha256": admission_campaign[
                "campaign_sha256"
            ],
            "source_runtime_admission_receipt_sha256": receipt["receipt_sha256"],
            "runtime_files": runtime_files,
            "runtime_files_revalidated": True,
            "runtime_admission_required": False,
            "prior_mechanics_result_reused": False,
            "next_required_stage": (
                "RUN_FRESH_ZERO_AUTHORITY_ISAAC_STATE_POLICY_MECHANICS_REPLAY"
            ),
        })
        native_plan["limitations"] = list(plan.get("limitations", [])) + [
            "materialization_does_not_start_isaac_or_a_gpu",
            "fresh_native_mechanics_result_remains_pending",
            "native_result_cannot_authorize_physical_motion",
        ]
        native_plan["plan_sha256"] = _canonical_sha256(native_plan)
        native_plans[episode_id] = native_plan
        target_count = plan["sample_count"]
        collision_count = plan["collision_screened_bounded_sample_count"]
        total_targets += target_count
        total_collision_samples += collision_count
        entries.append({
            "episode_id": episode_id,
            "target_id": plan["target_id"],
            "joint_target_count": target_count,
            "collision_screened_bounded_sample_count": collision_count,
            "contact_endpoint_sequences": list(endpoints),
            "source_mechanics_plan_sha256": plan["plan_sha256"],
            "runtime_admission_receipt_sha256": receipt["receipt_sha256"],
            "native_mechanics_plan_sha256": native_plan["plan_sha256"],
        })
    if (
        total_targets != admission_campaign.get("total_joint_target_count")
        or total_targets != mechanics_campaign.get("total_joint_target_count")
        or total_collision_samples
        != admission_campaign.get("total_collision_screened_bounded_sample_count")
        or total_collision_samples
        != mechanics_campaign.get("total_collision_screened_bounded_sample_count")
    ):
        raise MechanicsContractError("native mechanics aggregate changed")

    manifest: dict[str, Any] = {
        "schema": STATE_POLICY_NATIVE_MECHANICS_MANIFEST_SCHEMA,
        "status": "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_STATE_POLICY_MECHANICS_REPLAYS",
        "source_runtime_admission_campaign_sha256": admission_campaign[
            "campaign_sha256"
        ],
        "source_mechanics_campaign_sha256": mechanics_campaign["campaign_sha256"],
        "episode_count": len(entries),
        "total_joint_target_count": total_targets,
        "total_collision_screened_bounded_sample_count": total_collision_samples,
        "entries": entries,
        "runtime_files": admission_campaign["runtime_files"],
        "runtime_files_revalidated": True,
        "isaac_started": False,
        "gpu_started": False,
        "mechanics_replays_executed": 0,
        "prior_mechanics_results_reused": False,
        "fresh_mechanics_replays_required": len(entries),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "START_FRESH_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_REPLAYS"
        ),
        "limitations": [
            "manifest_materialization_does_not_start_isaac_or_a_gpu",
            "all_fresh_mechanics_replays_remain_pending",
            "no_native_or_physical_replay_authority",
        ],
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest, native_plans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--native-h-probe", action="store_true")
    parser.add_argument(
        "--robot-tcp-bundle",
        type=Path,
        help="audit a zero-authority replay bundle against the H-key mechanics stroke",
    )
    parser.add_argument(
        "--regenerate-cartesian-schedule",
        action="store_true",
        help="emit a mechanics-compatible Cartesian request for fresh IK qualification",
    )
    parser.add_argument(
        "--cartesian-request",
        type=Path,
        help="screen a regenerated Cartesian request through canonical IK gates",
    )
    parser.add_argument(
        "--ik-source-bundle",
        type=Path,
        help="retained bundle supplying lineage and the sample-0 synthetic seed",
    )
    parser.add_argument(
        "--ik-receipt",
        type=Path,
        help="emit a bounded collision-diagnostic request from accepted IK evidence",
    )
    parser.add_argument(
        "--collision-candidate",
        type=Path,
        help="simulation-only collision candidate for the bounded diagnostic",
    )
    parser.add_argument(
        "--toolchain-lock",
        type=Path,
        help="selected zero-authority Isaac runner lock for the diagnostic",
    )
    parser.add_argument(
        "--run-collision-diagnostic",
        action="store_true",
        help="run the bounded request through native Isaac overlap queries",
    )
    parser.add_argument("--collision-request", type=Path)
    parser.add_argument("--virtual-profile", type=Path)
    parser.add_argument("--robot-usd", type=Path)
    parser.add_argument("--import-receipt", type=Path)
    parser.add_argument(
        "--propose-collision-pair-policy",
        action="store_true",
        help="classify native overlap evidence into an unapplied review proposal",
    )
    parser.add_argument("--collision-diagnostic-receipt", type=Path)
    parser.add_argument(
        "--localize-collision-blockers",
        action="store_true",
        help=(
            "bind policy-bound collision blockers to retained Cartesian trajectory "
            "samples without changing geometry, routes, or authority"
        ),
    )
    parser.add_argument(
        "--build-station-route-predicate",
        action="store_true",
        help=(
            "evaluate explicit target-to-station route bindings while preserving "
            "physical workcell solids"
        ),
    )
    parser.add_argument(
        "--plan-physical-blocker-experiment",
        action="store_true",
        help="classify retained physical blockers before generating variants",
    )
    parser.add_argument(
        "--generate-physical-blocker-route-variant",
        action="store_true",
        help="apply a retained plan's transit-height hypothesis to its source request",
    )
    parser.add_argument(
        "--plan-placement-tcp-search",
        action="store_true",
        help=(
            "plan a bounded placement/yaw/keyboard-TCP blocker-attribution "
            "campaign"
        ),
    )
    parser.add_argument(
        "--run-placement-tcp-search",
        action="store_true",
        help="execute the plan-bound zero-authority IK and exact OBB screen",
    )
    parser.add_argument("--placement-tcp-search-plan", type=Path)
    parser.add_argument(
        "--materialize-placement-tcp-shortlist",
        action="store_true",
        help="reproduce and retain native replay inputs for the selected shortlist",
    )
    parser.add_argument("--placement-tcp-search-screen", type=Path)
    parser.add_argument("--shortlist-output-dir", type=Path)
    parser.add_argument(
        "--retain-placement-tcp-native-results",
        action="store_true",
        help="retain and deterministically rank completed ARM-199 native replays",
    )
    parser.add_argument("--placement-tcp-shortlist-manifest", type=Path)
    parser.add_argument(
        "--plan-route-shape-campaign",
        action="store_true",
        help="plan the source-bound ARM-200 full-link route-shape campaign",
    )
    parser.add_argument(
        "--materialize-route-shape-candidate",
        action="store_true",
        help="materialize one predeclared ARM-200 route candidate",
    )
    parser.add_argument(
        "--screen-route-shape-campaign",
        action="store_true",
        help="aggregate ARM-201 IK evidence and exact full-link OBB scores",
    )
    parser.add_argument(
        "--materialize-route-shape-shortlist",
        action="store_true",
        help="retain native replay inputs for the ARM-201 ranked shortlist",
    )
    parser.add_argument(
        "--retain-route-shape-native-results",
        action="store_true",
        help="retain fixed ARM-202 native results and explicit attempt failures",
    )
    parser.add_argument(
        "--require-route-predicate-receipts",
        action="store_true",
        help="require completed route-shape native receipts to use the v4 route-predicate schema",
    )
    parser.add_argument("--route-shape-campaign-plan", type=Path)
    parser.add_argument("--route-shape-campaign-screen", type=Path)
    parser.add_argument("--route-shape-candidate-id")
    parser.add_argument("--route-shape-evidence-dir", type=Path)
    parser.add_argument("--route-shape-shortlist-output-dir", type=Path)
    parser.add_argument("--route-shape-native-replay-dir", type=Path)
    parser.add_argument("--route-shape-native-control-receipt", type=Path)
    parser.add_argument("--placement-tcp-native-selection", type=Path)
    parser.add_argument("--physical-blocker-experiment-plan", type=Path)
    parser.add_argument(
        "--source-cartesian-request",
        type=Path,
        help="original governed request required to admit a route variant to IK",
    )
    parser.add_argument("--blocker-localization", type=Path)
    parser.add_argument("--clearance-margin-mm", type=float)
    parser.add_argument("--target-station-bindings", type=Path)
    parser.add_argument("--accept-collision-pair-policy", action="store_true")
    parser.add_argument("--collision-pair-policy-proposal", type=Path)
    parser.add_argument("--bind-collision-pair-policy", action="store_true")
    parser.add_argument("--accepted-collision-pair-policy", type=Path)
    parser.add_argument(
        "--station-route-predicate",
        type=Path,
        help=(
            "passing zero-authority station route predicate used to keep planning "
            "regions out of PhysX solid authoring"
        ),
    )
    parser.add_argument(
        "--geometry-capture-plan",
        type=Path,
        help="fixed ARM-204 parity capture plan for an unchanged native diagnostic",
    )
    parser.add_argument(
        "--geometry-capture-output",
        type=Path,
        help="zero-authority native primitive transform sidecar",
    )
    parser.add_argument(
        "--fixed-base-replay-plan",
        type=Path,
        help="ARM-205 fixed-base replay plan with per-sample root invariant",
    )
    parser.add_argument(
        "--build-drive-controlled-robot-h-replay-plan",
        action="store_true",
        help="compile the selected ARM-206 route into the strict ARM-207 replay plan",
    )
    parser.add_argument(
        "--build-feedback-adapted-robot-h-replay-plan",
        action="store_true",
        help="adapt ARM-207 H depth and release dwell from its retained native trace",
    )
    parser.add_argument(
        "--build-trace-lifted-robot-h-replay-plan",
        action="store_true",
        help="lift ARM-208 H hover/retract geometry from its retained native trace",
    )
    parser.add_argument(
        "--build-contact-refined-robot-h-replay-plan",
        action="store_true",
        help="refine ARM-209 H contact depth while preserving its lifted release path",
    )
    parser.add_argument(
        "--retain-governed-h-demonstration",
        action="store_true",
        help="retain the passing ARM-210 H skill as a zero-authority LM2 adaptation seed",
    )
    parser.add_argument(
        "--build-representative-key-adaptation-campaign",
        action="store_true",
        help="compile ARM-211 into target-specific zero-authority Cartesian requests",
    )
    parser.add_argument(
        "--build-representative-key-park-route-campaign",
        action="store_true",
        help="connect ARM-212 target skills to the selected zero-authority park route",
    )
    parser.add_argument("--representative-key-adaptation-campaign", type=Path)
    parser.add_argument(
        "--qualify-representative-key-park-routes-ik",
        action="store_true",
        help="run fresh canonical IK over every ARM-213 representative route",
    )
    parser.add_argument("--representative-key-park-route-campaign", type=Path)
    parser.add_argument(
        "--build-representative-key-collision-replay-campaign",
        action="store_true",
        help="compile ARM-214 routes into bounded fixed-root collision replays",
    )
    parser.add_argument("--representative-key-ik-campaign", type=Path)
    parser.add_argument(
        "--materialize-representative-key-native-collision-inputs",
        action="store_true",
        help="materialize truthful per-target ARM-216 native replay admissions",
    )
    parser.add_argument(
        "--aggregate-representative-key-native-collision-campaign",
        action="store_true",
        help="verify and aggregate the four completed ARM-216 native receipts",
    )
    parser.add_argument("--representative-key-collision-replay-campaign", type=Path)
    parser.add_argument("--representative-native-output-dir", type=Path)
    parser.add_argument(
        "--build-representative-key-native-mechanics-campaign",
        action="store_true",
        help="compile ARM-216 evidence into four target-specific native mechanics plans",
    )
    parser.add_argument(
        "--aggregate-representative-key-native-mechanics-campaign",
        action="store_true",
        help="aggregate four completed ARM-217 mechanics receipts",
    )
    parser.add_argument(
        "--build-feedback-adapted-representative-key-mechanics-campaign",
        action="store_true",
        help="adapt four blocked ARM-217 traces into bounded native replays",
    )
    parser.add_argument(
        "--build-contact-refined-representative-key-mechanics-campaign",
        action="store_true",
        help="refine excessive contacts while preserving passing ARM-217 plans",
    )
    parser.add_argument("--representative-native-mechanics-campaign", type=Path)
    parser.add_argument(
        "--representative-native-mechanics-result-campaign", type=Path
    )
    parser.add_argument("--representative-native-mechanics-output-dir", type=Path)
    parser.add_argument("--feedback-adapted-mechanics-output-dir", type=Path)
    parser.add_argument("--contact-refined-mechanics-output-dir", type=Path)
    parser.add_argument(
        "--build-randomized-demonstration-campaign",
        action="store_true",
        help="precommit the deterministic ARM-218 LM3 smoke manifest",
    )
    parser.add_argument(
        "--run-randomized-demonstration-episode",
        action="store_true",
        help="execute exactly one precommitted ARM-218 episode without retry",
    )
    parser.add_argument(
        "--aggregate-randomized-demonstration-campaign",
        action="store_true",
        help="aggregate the complete ARM-218 attempted denominator",
    )
    parser.add_argument(
        "--build-state-policy-dataset-manifest",
        action="store_true",
        help="compile the content-addressed ARM-219 LM4 dataset contract",
    )
    parser.add_argument(
        "--fit-state-policy-baseline",
        action="store_true",
        help="fit the deterministic ARM-219 LM4 ridge baseline",
    )
    parser.add_argument(
        "--build-state-policy-proposal-replay-campaign",
        action="store_true",
        help="precommit held-out LM4 policy proposals for native replay",
    )
    parser.add_argument(
        "--build-state-policy-collision-request-campaign",
        action="store_true",
        help="compile held-out LM4 proposals into fresh bounded collision requests",
    )
    parser.add_argument(
        "--admit-state-policy-collision-request-campaign",
        action="store_true",
        help="validate LM4 collision requests before runtime files or Isaac start",
    )
    parser.add_argument(
        "--revalidate-state-policy-collision-runtime-inputs",
        action="store_true",
        help="reload and hash LM4 runtime files without starting Isaac or a GPU",
    )
    parser.add_argument(
        "--materialize-state-policy-native-collision-inputs",
        action="store_true",
        help="bind LM4 samples into fresh fixed-base native diagnostic inputs",
    )
    parser.add_argument(
        "--aggregate-state-policy-native-collision-campaign",
        action="store_true",
        help="verify the complete LM4 native collision diagnostic denominator",
    )
    parser.add_argument(
        "--review-state-policy-native-collision-campaign",
        action="store_true",
        help="review ARM-220 evidence before LM4 mechanics-plan compilation",
    )
    parser.add_argument(
        "--compile-state-policy-mechanics-replay-campaign",
        action="store_true",
        help="compile reviewed LM4 proposals into non-executing mechanics plans",
    )
    parser.add_argument(
        "--admit-state-policy-mechanics-runtime-inputs",
        action="store_true",
        help=(
            "revalidate ARM-222 mechanics plans and their five runtime inputs "
            "without starting Isaac or a GPU"
        ),
    )
    parser.add_argument(
        "--materialize-state-policy-native-mechanics-inputs",
        action="store_true",
        help=(
            "bind admitted ARM-222 trajectories into fresh zero-authority "
            "native mechanics replay inputs"
        ),
    )
    parser.add_argument(
        "--run-state-policy-native-mechanics-episode",
        action="store_true",
        help=(
            "execute exactly one precommitted ARM-224 mechanics episode "
            "without retry or physical authority"
        ),
    )
    parser.add_argument("--randomized-campaign", type=Path)
    parser.add_argument("--randomized-result", type=Path)
    parser.add_argument("--randomized-receipt-root", type=Path)
    parser.add_argument("--state-policy-dataset-manifest", type=Path)
    parser.add_argument("--state-policy-model", type=Path)
    parser.add_argument("--state-policy-proposal-campaign", type=Path)
    parser.add_argument("--state-policy-collision-request-campaign", type=Path)
    parser.add_argument("--proposal-output-dir", type=Path)
    parser.add_argument("--representative-native-admission-root", type=Path)
    parser.add_argument("--collision-request-output-dir", type=Path)
    parser.add_argument("--collision-admission-output-dir", type=Path)
    parser.add_argument("--state-policy-runtime-admission-campaign", type=Path)
    parser.add_argument("--collision-runtime-admission-root", type=Path)
    parser.add_argument("--collision-runtime-revalidation-output-dir", type=Path)
    parser.add_argument("--state-policy-runtime-revalidation-campaign", type=Path)
    parser.add_argument("--state-policy-runtime-revalidation-root", type=Path)
    parser.add_argument("--state-policy-native-manifest", type=Path)
    parser.add_argument("--state-policy-native-campaign", type=Path)
    parser.add_argument("--state-policy-native-review", type=Path)
    parser.add_argument("--state-policy-native-output-dir", type=Path)
    parser.add_argument("--state-policy-mechanics-output-dir", type=Path)
    parser.add_argument("--state-policy-mechanics-campaign", type=Path)
    parser.add_argument("--state-policy-mechanics-runtime-output-dir", type=Path)
    parser.add_argument("--state-policy-mechanics-runtime-admission-campaign", type=Path)
    parser.add_argument("--state-policy-native-mechanics-output-dir", type=Path)
    parser.add_argument("--state-policy-native-mechanics-manifest", type=Path)
    parser.add_argument("--ridge-lambda", type=float, default=0.001)
    parser.add_argument("--episode-id")
    parser.add_argument("--source-native-receipt", type=Path)
    parser.add_argument("--trajectory-output", type=Path)
    parser.add_argument("--source-result-campaign", type=Path)
    parser.add_argument("--source-artifact-root", type=Path)
    parser.add_argument("--master-seed", type=int, default=218)
    parser.add_argument("--governed-demonstration", type=Path)
    parser.add_argument(
        "--run-drive-controlled-robot-h-replay",
        "--run-drive-controlled-key-replay",
        action="store_true",
        help="execute the strict ARM-207 plan in native Isaac physics",
    )
    parser.add_argument("--replay-plan", type=Path)
    parser.add_argument("--source-replay-receipt", type=Path)
    parser.add_argument("--learning-baseline-selection", type=Path)
    parser.add_argument("--fixed-base-receipt", type=Path)
    parser.add_argument("--native-h-receipt", type=Path)
    parser.add_argument("--drive-profile", type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if args.native_h_probe and args.robot_tcp_bundle is not None:
            raise MechanicsContractError(
                "native H probe and robot TCP binding audit are mutually exclusive"
            )
        if args.regenerate_cartesian_schedule and args.robot_tcp_bundle is None:
            raise MechanicsContractError(
                "Cartesian regeneration requires --robot-tcp-bundle"
            )
        if (
            not args.localize_collision_blockers
            and not args.build_station_route_predicate
            and not args.plan_physical_blocker_experiment
            and not args.generate_physical_blocker_route_variant
            and not args.plan_placement_tcp_search
            and not args.run_placement_tcp_search
            and not args.materialize_placement_tcp_shortlist
            and not args.retain_placement_tcp_native_results
            and not args.plan_route_shape_campaign
            and not args.materialize_route_shape_candidate
            and not args.screen_route_shape_campaign
            and not args.materialize_route_shape_shortlist
            and not args.retain_route_shape_native_results
            and not args.build_drive_controlled_robot_h_replay_plan
            and not args.build_feedback_adapted_robot_h_replay_plan
            and not args.build_trace_lifted_robot_h_replay_plan
            and not args.build_contact_refined_robot_h_replay_plan
            and not args.build_representative_key_adaptation_campaign
            and not args.build_representative_key_park_route_campaign
            and not args.qualify_representative_key_park_routes_ik
            and not args.build_representative_key_collision_replay_campaign
            and not args.materialize_representative_key_native_collision_inputs
            and (
                (args.cartesian_request is None)
                != (args.ik_source_bundle is None)
            )
        ):
            raise MechanicsContractError(
                "IK screening requires both --cartesian-request and --ik-source-bundle"
            )
        request_collision_arguments = (
            args.ik_receipt, args.collision_candidate, args.toolchain_lock
        )
        if (
            not args.run_collision_diagnostic
            and not args.revalidate_state_policy_collision_runtime_inputs
            and not args.propose_collision_pair_policy
            and not args.build_station_route_predicate
            and not args.plan_physical_blocker_experiment
            and not args.plan_placement_tcp_search
            and not args.run_placement_tcp_search
            and not args.materialize_placement_tcp_shortlist
            and not args.retain_placement_tcp_native_results
            and not args.plan_route_shape_campaign
            and not args.materialize_route_shape_candidate
            and not args.screen_route_shape_campaign
            and not args.materialize_route_shape_shortlist
            and not args.retain_route_shape_native_results
            and not args.build_drive_controlled_robot_h_replay_plan
            and not args.build_feedback_adapted_robot_h_replay_plan
            and not args.build_trace_lifted_robot_h_replay_plan
            and not args.build_contact_refined_robot_h_replay_plan
            and not args.build_representative_key_collision_replay_campaign
            and not args.materialize_representative_key_native_collision_inputs
            and any(item is not None for item in request_collision_arguments)
            and not all(item is not None for item in request_collision_arguments)
        ):
            raise MechanicsContractError(
                "collision request requires --ik-receipt, --collision-candidate, and --toolchain-lock"
            )
        if (
            not args.localize_collision_blockers
            and not args.build_drive_controlled_robot_h_replay_plan
            and not args.build_feedback_adapted_robot_h_replay_plan
            and not args.build_trace_lifted_robot_h_replay_plan
            and not args.build_contact_refined_robot_h_replay_plan
            and args.cartesian_request is not None
            and (
                args.native_h_probe
                or args.robot_tcp_bundle is not None
                or args.ik_receipt is not None
            )
        ):
            raise MechanicsContractError(
                "IK screening is mutually exclusive with native and binding modes"
            )
        if args.materialize_state_policy_native_mechanics_inputs:
            required = (
                args.state_policy_mechanics_runtime_admission_campaign,
                args.state_policy_mechanics_runtime_output_dir,
                args.state_policy_mechanics_campaign,
                args.state_policy_mechanics_output_dir,
                args.state_policy_native_mechanics_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-224 mechanics materialization requires the ARM-223 "
                    "campaign/admission root, ARM-222 campaign/plan root, and "
                    "native output root"
                )
            admission_campaign = json.loads(
                args.state_policy_mechanics_runtime_admission_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            admission_root = (
                args.state_policy_mechanics_runtime_output_dir.resolve(strict=True)
            )
            admission_receipts = {
                row["episode_id"]: json.loads((
                    admission_root
                    / row["episode_id"]
                    / "runtime_admission.json"
                ).resolve(strict=True).read_bytes())
                for row in admission_campaign.get("admissions", [])
            }
            mechanics_campaign = json.loads(
                args.state_policy_mechanics_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            mechanics_root = args.state_policy_mechanics_output_dir.resolve(
                strict=True
            )
            mechanics_plans = {
                row["episode_id"]: json.loads((
                    mechanics_root / row["episode_id"] / "mechanics_plan.json"
                ).resolve(strict=True).read_bytes())
                for row in mechanics_campaign.get("entries", [])
            }
            result, native_mechanics_plans = (
                materialize_state_policy_native_mechanics_inputs(
                    admission_campaign,
                    admission_receipts,
                    mechanics_campaign,
                    mechanics_plans,
                )
            )
            output_root = args.state_policy_native_mechanics_output_dir.resolve()
            output_root.mkdir(parents=True, exist_ok=True)
            for episode_id, plan in native_mechanics_plans.items():
                episode_root = output_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                (episode_root / "native_mechanics_plan.json").write_text(
                    json.dumps(plan, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.admit_state_policy_mechanics_runtime_inputs:
            required = (
                args.state_policy_mechanics_campaign,
                args.state_policy_mechanics_output_dir,
                args.state_policy_mechanics_runtime_output_dir,
                args.virtual_profile,
                args.drive_profile,
                args.import_receipt,
                args.robot_usd,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-223 mechanics runtime admission requires the ARM-222 "
                    "campaign/plan root, five runtime inputs, and admission "
                    "output root"
                )
            mechanics_campaign = json.loads(
                args.state_policy_mechanics_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            mechanics_root = args.state_policy_mechanics_output_dir.resolve(
                strict=True
            )
            mechanics_plans = {
                row["episode_id"]: json.loads((
                    mechanics_root
                    / row["episode_id"]
                    / "mechanics_plan.json"
                ).resolve(strict=True).read_bytes())
                for row in mechanics_campaign.get("entries", [])
            }
            result, runtime_admissions = (
                admit_state_policy_mechanics_runtime_inputs(
                    mechanics_campaign,
                    mechanics_plans,
                    build_profile(args.layout.resolve(strict=True)),
                    args.virtual_profile.resolve(strict=True).read_bytes(),
                    args.drive_profile.resolve(strict=True).read_bytes(),
                    json.loads(
                        args.import_receipt.resolve(strict=True).read_bytes()
                    ),
                    args.robot_usd.resolve(strict=True).read_bytes(),
                )
            )
            output_root = args.state_policy_mechanics_runtime_output_dir.resolve()
            output_root.mkdir(parents=True, exist_ok=True)
            for episode_id, admission in runtime_admissions.items():
                episode_root = output_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                (episode_root / "runtime_admission.json").write_text(
                    json.dumps(admission, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.compile_state_policy_mechanics_replay_campaign:
            required = (
                args.state_policy_native_review,
                args.state_policy_dataset_manifest,
                args.state_policy_proposal_campaign,
                args.proposal_output_dir,
                args.state_policy_collision_request_campaign,
                args.collision_request_output_dir,
                args.state_policy_native_manifest,
                args.representative_native_mechanics_campaign,
                args.representative_native_mechanics_result_campaign,
                args.representative_native_mechanics_output_dir,
                args.state_policy_mechanics_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-222 mechanics compilation requires the ARM-221 review, "
                    "dataset, proposals, collision requests, native manifest, "
                    "accepted representative mechanics sources, and output root"
                )
            review = json.loads(
                args.state_policy_native_review.resolve(strict=True).read_bytes()
            )
            dataset = json.loads(
                args.state_policy_dataset_manifest.resolve(strict=True).read_bytes()
            )
            proposals = json.loads(
                args.state_policy_proposal_campaign.resolve(strict=True).read_bytes()
            )
            proposal_root = args.proposal_output_dir.resolve(strict=True)
            proposal_payloads = {
                row["episode_id"]: (
                    proposal_root / row["episode_id"] / "policy_proposal.jsonl"
                ).resolve(strict=True).read_bytes()
                for row in proposals.get("episodes", [])
            }
            request_campaign = json.loads(
                args.state_policy_collision_request_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            request_root = args.collision_request_output_dir.resolve(strict=True)
            requests = {
                row["episode_id"]: json.loads((
                    request_root / row["episode_id"] / "collision_request.json"
                ).resolve(strict=True).read_bytes())
                for row in request_campaign.get("requests", [])
            }
            native_manifest = json.loads(
                args.state_policy_native_manifest.resolve(strict=True).read_bytes()
            )
            mechanics_campaign = json.loads(
                args.representative_native_mechanics_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            mechanics_result = json.loads(
                args.representative_native_mechanics_result_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            mechanics_root = (
                args.representative_native_mechanics_output_dir.resolve(strict=True)
            )
            mechanics_receipts = {
                plan["target_id"]: json.loads((
                    mechanics_root
                    / plan["target_id"].lower()
                    / "native_mechanics_receipt.json"
                ).resolve(strict=True).read_bytes())
                for plan in mechanics_campaign.get("plans", [])
            }
            result, mechanics_plans = compile_state_policy_mechanics_replay_campaign(
                review,
                dataset,
                proposals,
                proposal_payloads,
                request_campaign,
                requests,
                native_manifest,
                mechanics_campaign,
                mechanics_result,
                mechanics_receipts,
            )
            output_root = args.state_policy_mechanics_output_dir.resolve()
            output_root.mkdir(parents=True, exist_ok=True)
            for episode_id, plan in mechanics_plans.items():
                episode_root = output_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                (episode_root / "mechanics_plan.json").write_text(
                    json.dumps(plan, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.review_state_policy_native_collision_campaign:
            required = (
                args.state_policy_native_campaign,
                args.state_policy_native_manifest,
                args.state_policy_native_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-221 collision review requires the ARM-220 campaign, "
                    "manifest, and receipt root"
                )
            campaign = json.loads(
                args.state_policy_native_campaign.resolve(strict=True).read_bytes()
            )
            manifest = json.loads(
                args.state_policy_native_manifest.resolve(strict=True).read_bytes()
            )
            native_root = args.state_policy_native_output_dir.resolve(strict=True)
            receipts = {
                row["episode_id"]: json.loads((
                    native_root / row["episode_id"] / "native_receipt.json"
                ).resolve(strict=True).read_bytes())
                for row in manifest.get("entries", [])
            }
            result = review_state_policy_native_collision_campaign(
                campaign, manifest, receipts
            )
        elif args.materialize_state_policy_native_collision_inputs:
            required = (
                args.state_policy_runtime_revalidation_campaign,
                args.state_policy_runtime_revalidation_root,
                args.collision_request_output_dir,
                args.representative_native_admission_root,
                args.state_policy_native_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-220 native input materialization requires the runtime "
                    "revalidation campaign/root, state-policy request root, "
                    "representative native root, and native output directory"
                )
            revalidation_campaign = json.loads(
                args.state_policy_runtime_revalidation_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            revalidation_root = args.state_policy_runtime_revalidation_root.resolve(
                strict=True
            )
            request_root = args.collision_request_output_dir.resolve(strict=True)
            native_root = args.representative_native_admission_root.resolve(
                strict=True
            )
            revalidations = {
                row["episode_id"]: json.loads((
                    revalidation_root
                    / row["episode_id"]
                    / "runtime_revalidation.json"
                ).resolve(strict=True).read_bytes())
                for row in revalidation_campaign.get("revalidations", [])
            }
            state_requests = {
                row["episode_id"]: json.loads((
                    request_root / row["episode_id"] / "collision_request.json"
                ).resolve(strict=True).read_bytes())
                for row in revalidation_campaign.get("revalidations", [])
            }
            targets = {
                row["target_id"]
                for row in revalidation_campaign.get("revalidations", [])
            }
            representative_inputs = {}
            for target_id in targets:
                target_root = native_root / target_id.lower()
                representative_inputs[target_id] = {
                    "collision_request": json.loads((
                        target_root / "collision_request.json"
                    ).resolve(strict=True).read_bytes()),
                    "fixed_base_replay_plan": json.loads((
                        target_root / "fixed_base_replay_plan.json"
                    ).resolve(strict=True).read_bytes()),
                    "station_route_predicate": json.loads((
                        target_root / "station_route_predicate.json"
                    ).resolve(strict=True).read_bytes()),
                }
            result, native_bundles = materialize_state_policy_native_collision_inputs(
                revalidation_campaign,
                revalidations,
                state_requests,
                representative_inputs,
            )
            output_root = args.state_policy_native_output_dir.resolve()
            output_root.mkdir(parents=True, exist_ok=True)
            for episode_id, bundle in native_bundles.items():
                episode_root = output_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                for filename, document in (
                    ("native_collision_request.json", bundle["collision_request"]),
                    ("native_fixed_base_replay_plan.json", bundle[
                        "fixed_base_replay_plan"
                    ]),
                ):
                    (episode_root / filename).write_text(
                        json.dumps(document, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
        elif args.aggregate_state_policy_native_collision_campaign:
            required = (
                args.state_policy_native_manifest,
                args.state_policy_native_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-220 native aggregation requires its manifest and receipt root"
                )
            manifest = json.loads(
                args.state_policy_native_manifest.resolve(strict=True).read_bytes()
            )
            native_root = args.state_policy_native_output_dir.resolve(strict=True)
            receipts = {
                row["episode_id"]: json.loads((
                    native_root / row["episode_id"] / "native_receipt.json"
                ).resolve(strict=True).read_bytes())
                for row in manifest.get("entries", [])
            }
            result = aggregate_state_policy_native_collision_campaign(
                manifest, receipts
            )
        elif args.revalidate_state_policy_collision_runtime_inputs:
            required = (
                args.state_policy_runtime_admission_campaign,
                args.collision_runtime_admission_root,
                args.collision_runtime_revalidation_output_dir,
                args.virtual_profile,
                args.robot_usd,
                args.import_receipt,
                args.toolchain_lock,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-219 runtime revalidation requires its admission "
                    "campaign/root, four runtime files, and revalidation output "
                    "directory"
                )
            admission_campaign = json.loads(
                args.state_policy_runtime_admission_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            admission_root = args.collision_runtime_admission_root.resolve(
                strict=True
            )
            runtime_admissions = {
                row["episode_id"]: json.loads(
                    (
                        admission_root
                        / row["episode_id"]
                        / "runtime_admission.json"
                    ).resolve(strict=True).read_bytes()
                )
                for row in admission_campaign.get("admissions", [])
            }
            result, runtime_revalidations = (
                revalidate_state_policy_collision_runtime_inputs(
                    admission_campaign,
                    runtime_admissions,
                    args.virtual_profile.resolve(strict=True).read_bytes(),
                    json.loads(args.import_receipt.resolve(strict=True).read_bytes()),
                    args.robot_usd.resolve(strict=True).read_bytes(),
                    json.loads(args.toolchain_lock.resolve(strict=True).read_bytes()),
                )
            )
            revalidation_root = (
                args.collision_runtime_revalidation_output_dir.resolve()
            )
            revalidation_root.mkdir(parents=True, exist_ok=True)
            for episode_id, receipt in runtime_revalidations.items():
                episode_root = revalidation_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                (episode_root / "runtime_revalidation.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.admit_state_policy_collision_request_campaign:
            required = (
                args.state_policy_dataset_manifest,
                args.state_policy_model,
                args.state_policy_proposal_campaign,
                args.state_policy_collision_request_campaign,
                args.collision_request_output_dir,
                args.representative_native_admission_root,
                args.collision_admission_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-219 runtime admission requires its dataset, model, "
                    "proposal campaign, collision request campaign/root, "
                    "representative native root, and admission output directory"
                )
            dataset_manifest = json.loads(
                args.state_policy_dataset_manifest.resolve(strict=True).read_bytes()
            )
            model = json.loads(
                args.state_policy_model.resolve(strict=True).read_bytes()
            )
            proposal_campaign = json.loads(
                args.state_policy_proposal_campaign.resolve(strict=True).read_bytes()
            )
            request_campaign = json.loads(
                args.state_policy_collision_request_campaign
                .resolve(strict=True)
                .read_bytes()
            )
            request_root = args.collision_request_output_dir.resolve(strict=True)
            collision_requests = {
                row["episode_id"]: json.loads(
                    (
                        request_root
                        / row["episode_id"]
                        / "collision_request.json"
                    ).resolve(strict=True).read_bytes()
                )
                for row in request_campaign.get("requests", [])
            }
            native_root = args.representative_native_admission_root.resolve(
                strict=True
            )
            native_manifest = json.loads(
                (native_root / "manifest.json").resolve(strict=True).read_bytes()
            )
            native_campaign = json.loads(
                (native_root / "campaign.json").resolve(strict=True).read_bytes()
            )
            representative_inputs = {}
            for target_id in {
                episode["target_id"]
                for episode in proposal_campaign.get("episodes", [])
            }:
                target_root = native_root / target_id.lower()
                representative_inputs[target_id] = {
                    "collision_request": json.loads(
                        (target_root / "collision_request.json")
                        .resolve(strict=True)
                        .read_bytes()
                    ),
                    "fixed_base_replay_plan": json.loads(
                        (target_root / "fixed_base_replay_plan.json")
                        .resolve(strict=True)
                        .read_bytes()
                    ),
                    "station_route_predicate": json.loads(
                        (target_root / "station_route_predicate.json")
                        .resolve(strict=True)
                        .read_bytes()
                    ),
                    "native_receipt": json.loads(
                        (target_root / "native_receipt.json")
                        .resolve(strict=True)
                        .read_bytes()
                    ),
                }
            result, runtime_admissions = (
                admit_state_policy_collision_request_campaign(
                    dataset_manifest,
                    model,
                    proposal_campaign,
                    request_campaign,
                    collision_requests,
                    native_manifest,
                    native_campaign,
                    representative_inputs,
                )
            )
            admission_root = args.collision_admission_output_dir.resolve()
            admission_root.mkdir(parents=True, exist_ok=True)
            for episode_id, admission in runtime_admissions.items():
                episode_root = admission_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                (episode_root / "runtime_admission.json").write_text(
                    json.dumps(admission, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.build_state_policy_collision_request_campaign:
            required = (
                args.state_policy_proposal_campaign,
                args.proposal_output_dir,
                args.representative_native_admission_root,
                args.collision_request_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-219 collision request compilation requires its proposal "
                    "campaign, proposal root, representative native admission "
                    "root, and collision request output directory"
                )
            proposal_campaign = json.loads(
                args.state_policy_proposal_campaign.resolve(strict=True).read_bytes()
            )
            proposal_root = args.proposal_output_dir.resolve(strict=True)
            proposal_payloads = {
                episode["episode_id"]: (
                    proposal_root
                    / episode["episode_id"]
                    / "policy_proposal.jsonl"
                ).resolve(strict=True).read_bytes()
                for episode in proposal_campaign.get("episodes", [])
            }
            native_root = args.representative_native_admission_root.resolve(
                strict=True
            )
            native_campaign = json.loads(
                (native_root / "campaign.json").resolve(strict=True).read_bytes()
            )
            representative_inputs = {}
            for target_id in {
                episode["target_id"]
                for episode in proposal_campaign.get("episodes", [])
            }:
                target_root = native_root / target_id.lower()
                representative_inputs[target_id] = {
                    "collision_request": json.loads(
                        (target_root / "collision_request.json")
                        .resolve(strict=True)
                        .read_bytes()
                    ),
                    "fixed_base_replay_plan": json.loads(
                        (target_root / "fixed_base_replay_plan.json")
                        .resolve(strict=True)
                        .read_bytes()
                    ),
                    "station_route_predicate": json.loads(
                        (target_root / "station_route_predicate.json")
                        .resolve(strict=True)
                        .read_bytes()
                    ),
                }
            result, collision_requests = build_state_policy_collision_request_campaign(
                proposal_campaign,
                proposal_payloads,
                native_campaign,
                representative_inputs,
            )
            collision_root = args.collision_request_output_dir.resolve()
            collision_root.mkdir(parents=True, exist_ok=True)
            for episode_id, request in collision_requests.items():
                episode_root = collision_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                (episode_root / "collision_request.json").write_text(
                    json.dumps(request, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.build_state_policy_proposal_replay_campaign:
            required = (
                args.state_policy_dataset_manifest,
                args.state_policy_model,
                args.randomized_receipt_root,
                args.proposal_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-219 proposal compilation requires its dataset, model, "
                    "trajectory root, and proposal output directory"
                )
            manifest = json.loads(
                args.state_policy_dataset_manifest.resolve(strict=True).read_bytes()
            )
            model = json.loads(
                args.state_policy_model.resolve(strict=True).read_bytes()
            )
            receipt_root = args.randomized_receipt_root.resolve(strict=True)
            evaluation = [
                episode
                for episode in manifest.get("episodes", [])
                if episode.get("role") == "EVALUATION"
            ]
            trajectory_payloads = {
                episode["episode_id"]: (
                    receipt_root / episode["episode_id"] / "trajectory.jsonl"
                ).resolve(strict=True).read_bytes()
                for episode in evaluation
            }
            result, proposal_payloads = build_state_policy_proposal_replay_campaign(
                manifest, model, trajectory_payloads
            )
            proposal_root = args.proposal_output_dir.resolve()
            proposal_root.mkdir(parents=True, exist_ok=True)
            for episode_id, payload in proposal_payloads.items():
                episode_root = proposal_root / episode_id
                episode_root.mkdir(parents=True, exist_ok=True)
                (episode_root / "policy_proposal.jsonl").write_bytes(payload)
        elif args.fit_state_policy_baseline:
            required = (
                args.state_policy_dataset_manifest,
                args.randomized_receipt_root,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-219 baseline fitting requires its dataset manifest and "
                    "trajectory root"
                )
            manifest = json.loads(
                args.state_policy_dataset_manifest.resolve(strict=True).read_bytes()
            )
            receipt_root = args.randomized_receipt_root.resolve(strict=True)
            trajectory_payloads = {
                episode["episode_id"]: (
                    receipt_root / episode["episode_id"] / "trajectory.jsonl"
                ).resolve(strict=True).read_bytes()
                for episode in manifest.get("episodes", [])
            }
            result = fit_state_policy_baseline(
                manifest,
                trajectory_payloads,
                ridge_lambda=args.ridge_lambda,
            )
        elif args.build_state_policy_dataset_manifest:
            required = (
                args.randomized_campaign,
                args.randomized_result,
                args.randomized_receipt_root,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-219 dataset compilation requires its campaign, result, "
                    "and receipt root"
                )
            campaign = json.loads(
                args.randomized_campaign.resolve(strict=True).read_bytes()
            )
            randomized_result = json.loads(
                args.randomized_result.resolve(strict=True).read_bytes()
            )
            receipt_root = args.randomized_receipt_root.resolve(strict=True)
            receipts = {}
            trajectory_payloads = {}
            for episode in campaign.get("episodes", []):
                episode_id = episode["episode_id"]
                episode_root = receipt_root / episode_id
                receipts[episode_id] = json.loads(
                    (episode_root / "episode_receipt.json")
                    .resolve(strict=True)
                    .read_bytes()
                )
                trajectory_payloads[episode_id] = (
                    episode_root / "trajectory.jsonl"
                ).resolve(strict=True).read_bytes()
            result = build_state_policy_dataset_manifest(
                campaign, randomized_result, receipts, trajectory_payloads
            )
        elif args.build_randomized_demonstration_campaign:
            required = (args.source_result_campaign, args.source_artifact_root)
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-218 compilation requires its source result and artifact root"
                )
            source_root = args.source_artifact_root.resolve(strict=True)
            source = json.loads(
                args.source_result_campaign.resolve(strict=True).read_bytes()
            )
            plans = {}
            receipts = {}
            for target in REPRESENTATIVE_KEYS[1:]:
                target_root = source_root / target.lower()
                plans[target] = json.loads(
                    (target_root / "native_mechanics_plan.json")
                    .resolve(strict=True)
                    .read_bytes()
                )
                receipts[target] = json.loads(
                    (target_root / "native_mechanics_receipt.json")
                    .resolve(strict=True)
                    .read_bytes()
                )
            result = build_randomized_demonstration_campaign(
                source, plans, receipts, master_seed=args.master_seed
            )
        elif args.aggregate_randomized_demonstration_campaign:
            required = (args.randomized_campaign, args.randomized_receipt_root)
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-218 aggregation requires its campaign and receipt root"
                )
            campaign = json.loads(
                args.randomized_campaign.resolve(strict=True).read_bytes()
            )
            receipt_root = args.randomized_receipt_root.resolve(strict=True)
            receipts = {
                episode["episode_id"]: json.loads(
                    (
                        receipt_root
                        / episode["episode_id"]
                        / "episode_receipt.json"
                    ).resolve(strict=True).read_bytes()
                )
                for episode in campaign.get("episodes", [])
            }
            result = aggregate_randomized_demonstration_campaign(
                campaign, receipts
            )
        elif args.run_state_policy_native_mechanics_episode:
            required = (
                args.state_policy_native_mechanics_manifest,
                args.episode_id,
                args.replay_plan,
                args.drive_profile,
                args.robot_usd,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-225 episode execution requires its ARM-224 manifest, "
                    "episode id, replay plan, drive profile, and robot USD"
                )
            result = run_state_policy_native_mechanics_episode(
                manifest_path=args.state_policy_native_mechanics_manifest,
                episode_id=args.episode_id,
                replay_plan_path=args.replay_plan,
                layout_path=args.layout,
                drive_profile_path=args.drive_profile,
                robot_usd_path=args.robot_usd,
                output_path=args.output,
                status_path=args.status_output,
            )
        elif args.run_randomized_demonstration_episode:
            required = (
                args.randomized_campaign,
                args.episode_id,
                args.replay_plan,
                args.source_native_receipt,
                args.drive_profile,
                args.robot_usd,
                args.trajectory_output,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-218 episode execution requires its campaign, episode id, "
                    "plan, source receipt, drive profile, robot USD, and trajectory output"
                )
            result = run_randomized_demonstration_episode(
                campaign_path=args.randomized_campaign,
                episode_id=args.episode_id,
                replay_plan_path=args.replay_plan,
                source_receipt_path=args.source_native_receipt,
                layout_path=args.layout,
                drive_profile_path=args.drive_profile,
                robot_usd_path=args.robot_usd,
                output_path=args.output,
                trajectory_path=args.trajectory_output,
                status_path=args.status_output,
            )
        elif args.run_drive_controlled_robot_h_replay:
            required = (args.replay_plan, args.drive_profile, args.robot_usd)
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-207 execution requires --replay-plan, --drive-profile, and --robot-usd"
                )
            result = run_drive_controlled_robot_h_replay(
                replay_plan_path=args.replay_plan,
                layout_path=args.layout,
                drive_profile_path=args.drive_profile,
                robot_usd_path=args.robot_usd,
                output_path=args.output,
                status_path=args.status_output,
            )
        elif args.build_contact_refined_representative_key_mechanics_campaign:
            required = (
                args.representative_native_mechanics_campaign,
                args.representative_native_mechanics_output_dir,
                args.contact_refined_mechanics_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-217 contact refinement requires its campaign and output directory"
                )
            source_campaign = json.loads(
                args.representative_native_mechanics_campaign.resolve(
                    strict=True
                ).read_bytes()
            )
            source_root = args.representative_native_mechanics_output_dir.resolve(
                strict=True
            )
            source_receipts = [
                json.loads(
                    (
                        source_root
                        / plan["target_id"].lower()
                        / "native_mechanics_receipt.json"
                    ).resolve(strict=True).read_bytes()
                )
                for plan in source_campaign.get("plans", [])
            ]
            result = build_contact_refined_representative_key_mechanics_campaign(
                source_campaign,
                source_receipts,
                build_profile(args.layout.resolve(strict=True)),
            )
            refined_root = args.contact_refined_mechanics_output_dir.resolve()
            refined_root.mkdir(parents=True, exist_ok=True)
            for plan in result["plans"]:
                target_root = refined_root / plan["target_id"].lower()
                target_root.mkdir(parents=True, exist_ok=True)
                (target_root / "native_mechanics_plan.json").write_text(
                    json.dumps(plan, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.build_feedback_adapted_representative_key_mechanics_campaign:
            required = (
                args.representative_native_mechanics_campaign,
                args.representative_native_mechanics_output_dir,
                args.feedback_adapted_mechanics_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-217 feedback adaptation requires its campaign and output directory"
                )
            source_campaign = json.loads(
                args.representative_native_mechanics_campaign.resolve(
                    strict=True
                ).read_bytes()
            )
            source_root = args.representative_native_mechanics_output_dir.resolve(
                strict=True
            )
            source_receipts = [
                json.loads(
                    (
                        source_root
                        / plan["target_id"].lower()
                        / "native_mechanics_receipt.json"
                    ).resolve(strict=True).read_bytes()
                )
                for plan in source_campaign.get("plans", [])
            ]
            result = build_feedback_adapted_representative_key_mechanics_campaign(
                source_campaign,
                source_receipts,
                build_profile(args.layout.resolve(strict=True)),
            )
            adapted_root = args.feedback_adapted_mechanics_output_dir.resolve()
            adapted_root.mkdir(parents=True, exist_ok=True)
            for plan in result["plans"]:
                target_root = adapted_root / plan["target_id"].lower()
                target_root.mkdir(parents=True, exist_ok=True)
                (target_root / "native_mechanics_plan.json").write_text(
                    json.dumps(plan, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.aggregate_representative_key_native_mechanics_campaign:
            required = (
                args.representative_native_mechanics_campaign,
                args.representative_native_mechanics_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-217 aggregation requires its campaign and output directory"
                )
            mechanics_campaign = json.loads(
                args.representative_native_mechanics_campaign.resolve(
                    strict=True
                ).read_bytes()
            )
            mechanics_root = args.representative_native_mechanics_output_dir.resolve(
                strict=True
            )
            mechanics_receipts = [
                json.loads(
                    (
                        mechanics_root
                        / plan["target_id"].lower()
                        / "native_mechanics_receipt.json"
                    ).resolve(strict=True).read_bytes()
                )
                for plan in mechanics_campaign.get("plans", [])
            ]
            result = aggregate_representative_key_native_mechanics_campaign(
                mechanics_campaign, mechanics_receipts
            )
        elif args.build_representative_key_native_mechanics_campaign:
            required = (
                args.representative_key_park_route_campaign,
                args.representative_key_ik_campaign,
                args.representative_native_output_dir,
                args.virtual_profile,
                args.drive_profile,
                args.robot_usd,
                args.import_receipt,
                args.representative_native_mechanics_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-217 planning requires the ARM-213/214 campaigns, ARM-216 "
                    "output directory, virtual and mechanics profiles, drive profile, "
                    "robot USD, import receipt, and mechanics output directory"
                )
            native_root = args.representative_native_output_dir.resolve(strict=True)
            manifest = json.loads((native_root / "manifest.json").read_bytes())
            native_receipts = [
                json.loads(
                    (
                        native_root
                        / str(entry.get("directory"))
                        / "native_receipt.json"
                    ).resolve(strict=True).read_bytes()
                )
                for entry in manifest.get("entries", [])
            ]
            virtual_bytes = args.virtual_profile.resolve(strict=True).read_bytes()
            drive_bytes = args.drive_profile.resolve(strict=True).read_bytes()
            result = build_representative_key_native_mechanics_campaign(
                json.loads(
                    args.representative_key_park_route_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(
                    args.representative_key_ik_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                manifest,
                native_receipts,
                build_profile(args.layout.resolve(strict=True)),
                virtual_bytes,
                json.loads(drive_bytes),
                drive_bytes,
                args.robot_usd.resolve(strict=True).read_bytes(),
                json.loads(args.import_receipt.resolve(strict=True).read_bytes()),
            )
            mechanics_root = args.representative_native_mechanics_output_dir.resolve()
            mechanics_root.mkdir(parents=True, exist_ok=True)
            for plan in result["plans"]:
                target_root = mechanics_root / plan["target_id"].lower()
                target_root.mkdir(parents=True, exist_ok=True)
                (target_root / "native_mechanics_plan.json").write_text(
                    json.dumps(plan, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        elif args.aggregate_representative_key_native_collision_campaign:
            if args.representative_native_output_dir is None:
                raise MechanicsContractError(
                    "ARM-216 aggregation requires --representative-native-output-dir"
                )
            native_root = args.representative_native_output_dir.resolve(strict=True)
            manifest = json.loads(
                (native_root / "manifest.json").resolve(strict=True).read_bytes()
            )
            entries = manifest.get("entries")
            if not isinstance(entries, list):
                raise MechanicsContractError("ARM-216 manifest entries are absent")
            receipts = [
                json.loads(
                    (
                        native_root / str(entry.get("directory")) / "native_receipt.json"
                    ).resolve(strict=True).read_bytes()
                )
                for entry in entries
            ]
            result = aggregate_representative_key_native_collision_campaign(
                manifest, receipts
            )
        elif args.materialize_representative_key_native_collision_inputs:
            required = (
                args.representative_key_park_route_campaign,
                args.representative_key_ik_campaign,
                args.representative_key_collision_replay_campaign,
                args.ik_source_bundle,
                args.collision_candidate,
                args.toolchain_lock,
                args.accepted_collision_pair_policy,
                args.representative_native_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-216 requires the ARM-213/214/215 campaigns, source "
                    "bundle, collision candidate, toolchain lock, accepted pair "
                    "policy, and native output directory"
                )
            result = materialize_representative_key_native_collision_inputs(
                json.loads(
                    args.representative_key_park_route_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(
                    args.representative_key_ik_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(
                    args.representative_key_collision_replay_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.ik_source_bundle.resolve(strict=True).read_bytes()),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(args.toolchain_lock.resolve(strict=True).read_bytes()),
                json.loads(
                    args.accepted_collision_pair_policy.resolve(
                        strict=True
                    ).read_bytes()
                ),
                output_dir=args.representative_native_output_dir,
            )
        elif args.build_representative_key_collision_replay_campaign:
            required = (
                args.representative_key_ik_campaign,
                args.ik_source_bundle,
                args.collision_candidate,
                args.toolchain_lock,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-215 requires --representative-key-ik-campaign, "
                    "--ik-source-bundle, --collision-candidate, and --toolchain-lock"
                )
            result = build_representative_key_collision_replay_campaign(
                json.loads(
                    args.representative_key_ik_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.ik_source_bundle.resolve(strict=True).read_bytes()),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(args.toolchain_lock.resolve(strict=True).read_bytes()),
            )
        elif args.qualify_representative_key_park_routes_ik:
            required = (
                args.representative_key_park_route_campaign,
                args.cartesian_request,
                args.ik_source_bundle,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-214 requires --representative-key-park-route-campaign, "
                    "--cartesian-request, and --ik-source-bundle"
                )
            result = qualify_representative_key_park_routes_ik(
                json.loads(
                    args.representative_key_park_route_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.ik_source_bundle.resolve(strict=True).read_bytes()),
                build_profile(args.layout.resolve(strict=True)),
                workspace=args.workspace,
            )
        elif args.build_representative_key_park_route_campaign:
            required = (
                args.representative_key_adaptation_campaign,
                args.cartesian_request,
                args.learning_baseline_selection,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-213 requires --representative-key-adaptation-campaign, "
                    "--cartesian-request, and --learning-baseline-selection"
                )
            result = build_representative_key_park_route_campaign(
                json.loads(
                    args.representative_key_adaptation_campaign.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(
                    args.learning_baseline_selection.resolve(strict=True).read_bytes()
                ),
            )
        elif args.build_representative_key_adaptation_campaign:
            if args.governed_demonstration is None or args.cartesian_request is None:
                raise MechanicsContractError(
                    "ARM-212 requires --governed-demonstration and --cartesian-request"
                )
            result = build_representative_key_adaptation_campaign(
                json.loads(args.governed_demonstration.resolve(strict=True).read_bytes()),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                build_profile(args.layout.resolve(strict=True)),
            )
        elif args.retain_governed_h_demonstration:
            if args.replay_plan is None or args.source_replay_receipt is None:
                raise MechanicsContractError(
                    "ARM-211 retention requires --replay-plan and --source-replay-receipt"
                )
            result = retain_governed_h_demonstration(
                json.loads(args.replay_plan.resolve(strict=True).read_bytes()),
                json.loads(args.source_replay_receipt.resolve(strict=True).read_bytes()),
                build_profile(args.layout.resolve(strict=True)),
            )
        elif args.build_contact_refined_robot_h_replay_plan:
            if args.replay_plan is None or args.source_replay_receipt is None:
                raise MechanicsContractError(
                    "ARM-210 planning requires --replay-plan and --source-replay-receipt"
                )
            result = build_contact_refined_robot_h_replay_plan(
                json.loads(args.replay_plan.resolve(strict=True).read_bytes()),
                json.loads(args.source_replay_receipt.resolve(strict=True).read_bytes()),
                build_profile(args.layout.resolve(strict=True)),
            )
        elif args.build_trace_lifted_robot_h_replay_plan:
            if args.replay_plan is None or args.source_replay_receipt is None:
                raise MechanicsContractError(
                    "ARM-209 planning requires --replay-plan and --source-replay-receipt"
                )
            result = build_trace_lifted_robot_h_replay_plan(
                json.loads(args.replay_plan.resolve(strict=True).read_bytes()),
                json.loads(args.source_replay_receipt.resolve(strict=True).read_bytes()),
                build_profile(args.layout.resolve(strict=True)),
            )
        elif args.build_feedback_adapted_robot_h_replay_plan:
            if args.replay_plan is None or args.source_replay_receipt is None:
                raise MechanicsContractError(
                    "ARM-208 planning requires --replay-plan and --source-replay-receipt"
                )
            result = build_feedback_adapted_robot_h_replay_plan(
                json.loads(args.replay_plan.resolve(strict=True).read_bytes()),
                json.loads(args.source_replay_receipt.resolve(strict=True).read_bytes()),
                build_profile(args.layout.resolve(strict=True)),
            )
        elif args.build_drive_controlled_robot_h_replay_plan:
            required = (
                args.learning_baseline_selection,
                args.cartesian_request,
                args.ik_receipt,
                args.fixed_base_receipt,
                args.fixed_base_replay_plan,
                args.placement_tcp_native_selection,
                args.native_h_receipt,
                args.drive_profile,
                args.robot_usd,
                args.import_receipt,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "ARM-207 planning requires the selection, Cartesian and IK "
                    "evidence, fixed-base receipt and plan, placement selection, "
                    "native H receipt, drive profile, robot USD, and import receipt"
                )
            drive_profile_bytes = args.drive_profile.resolve(strict=True).read_bytes()
            result = build_drive_controlled_robot_h_replay_plan(
                json.loads(args.learning_baseline_selection.resolve(strict=True).read_bytes()),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.ik_receipt.resolve(strict=True).read_bytes()),
                json.loads(args.fixed_base_receipt.resolve(strict=True).read_bytes()),
                json.loads(args.fixed_base_replay_plan.resolve(strict=True).read_bytes()),
                json.loads(args.placement_tcp_native_selection.resolve(strict=True).read_bytes()),
                build_profile(args.layout.resolve(strict=True)),
                json.loads(args.native_h_receipt.resolve(strict=True).read_bytes()),
                json.loads(drive_profile_bytes),
                drive_profile_bytes,
                args.robot_usd.resolve(strict=True).read_bytes(),
                json.loads(args.import_receipt.resolve(strict=True).read_bytes()),
            )
        elif args.retain_route_shape_native_results:
            required = (
                args.route_shape_campaign_plan,
                args.route_shape_campaign_screen,
                args.route_shape_shortlist_output_dir,
                args.route_shape_native_replay_dir,
                args.route_shape_native_control_receipt,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "route-shape native retention requires its plan, screen, "
                    "shortlist manifest, replay directory, and control receipt"
                )
            campaign_plan = json.loads(
                args.route_shape_campaign_plan.resolve(strict=True).read_bytes()
            )
            campaign_screen = json.loads(
                args.route_shape_campaign_screen.resolve(strict=True).read_bytes()
            )
            shortlist_manifest = json.loads(
                (
                    args.route_shape_shortlist_output_dir.resolve(strict=True)
                    / "manifest.json"
                ).read_bytes()
            )
            replay_root = args.route_shape_native_replay_dir.resolve(strict=True)
            native_evidence: dict[str, dict[str, Any]] = {}
            for entry in shortlist_manifest.get("entries", []):
                candidate_dir = replay_root / entry["candidate_id"]
                receipt_path = candidate_dir / "receipt.json"
                native_receipt_path = candidate_dir / "native_receipt.json"
                status_path = candidate_dir / "status.json"
                evidence_path = (
                    receipt_path
                    if receipt_path.is_file()
                    else (
                        native_receipt_path
                        if native_receipt_path.is_file()
                        else status_path
                    )
                )
                native_evidence[entry["candidate_id"]] = json.loads(
                    evidence_path.resolve(strict=True).read_bytes()
                )
            result = retain_route_shape_native_results(
                campaign_plan,
                campaign_screen,
                shortlist_manifest,
                json.loads(
                    args.route_shape_native_control_receipt.resolve(
                        strict=True
                    ).read_bytes()
                ),
                native_evidence,
                require_route_predicate_receipts=(
                    args.require_route_predicate_receipts
                ),
            )
        elif args.materialize_route_shape_shortlist:
            required = (
                args.route_shape_campaign_plan,
                args.route_shape_campaign_screen,
                args.route_shape_evidence_dir,
                args.route_shape_shortlist_output_dir,
                args.collision_candidate,
                args.accepted_collision_pair_policy,
                args.toolchain_lock,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "route-shape shortlist materialization requires its plan, "
                    "screen, evidence and output directories, collision candidate, "
                    "accepted pair policy, and toolchain lock"
                )
            campaign_plan = json.loads(
                args.route_shape_campaign_plan.resolve(strict=True).read_bytes()
            )
            evidence_root = args.route_shape_evidence_dir.resolve(strict=True)
            candidate_evidence = {
                item["candidate_id"]: (
                    json.loads(
                        (
                            evidence_root / item["candidate_id"] / "request.json"
                        ).read_bytes()
                    ),
                    json.loads(
                        (
                            evidence_root
                            / item["candidate_id"]
                            / "ik_receipt.json"
                        ).read_bytes()
                    ),
                )
                for item in campaign_plan.get("candidates", [])
            }
            result = materialize_route_shape_native_shortlist(
                campaign_plan,
                json.loads(
                    args.route_shape_campaign_screen.resolve(
                        strict=True
                    ).read_bytes()
                ),
                candidate_evidence,
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(
                    args.accepted_collision_pair_policy.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.toolchain_lock.resolve(strict=True).read_bytes()),
                output_dir=args.route_shape_shortlist_output_dir,
            )
        elif args.screen_route_shape_campaign:
            required = (
                args.route_shape_campaign_plan,
                args.route_shape_evidence_dir,
                args.cartesian_request,
                args.collision_candidate,
                args.accepted_collision_pair_policy,
                args.station_route_predicate,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "route-shape screening requires its plan, evidence directory, "
                    "source route request, collision candidate, accepted pair "
                    "policy, and station predicate"
                )
            campaign_plan = json.loads(
                args.route_shape_campaign_plan.resolve(strict=True).read_bytes()
            )
            evidence_root = args.route_shape_evidence_dir.resolve(strict=True)
            candidate_evidence = {
                item["candidate_id"]: (
                    json.loads(
                        (
                            evidence_root / item["candidate_id"] / "request.json"
                        ).read_bytes()
                    ),
                    json.loads(
                        (
                            evidence_root
                            / item["candidate_id"]
                            / "ik_receipt.json"
                        ).read_bytes()
                    ),
                )
                for item in campaign_plan.get("candidates", [])
            }
            result = screen_route_shape_campaign(
                campaign_plan,
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                candidate_evidence,
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(
                    args.accepted_collision_pair_policy.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(
                    args.station_route_predicate.resolve(strict=True).read_bytes()
                ),
                workspace=args.workspace,
            )
        elif args.materialize_route_shape_candidate:
            if (
                args.route_shape_campaign_plan is None
                or args.cartesian_request is None
                or not args.route_shape_candidate_id
            ):
                raise MechanicsContractError(
                    "route-shape materialization requires its plan, source "
                    "Cartesian request, and candidate id"
                )
            result = materialize_route_shape_candidate(
                json.loads(
                    args.route_shape_campaign_plan.resolve(strict=True).read_bytes()
                ),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                args.route_shape_candidate_id,
            )
        elif args.plan_route_shape_campaign:
            required = (
                args.placement_tcp_search_plan,
                args.placement_tcp_native_selection,
                args.cartesian_request,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "route-shape planning requires the ARM-199 plan, native "
                    "selection, and route-variant request"
                )
            result = build_route_shape_campaign_plan(
                json.loads(
                    args.placement_tcp_search_plan.resolve(strict=True).read_bytes()
                ),
                json.loads(
                    args.placement_tcp_native_selection.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
            )
        elif args.retain_placement_tcp_native_results:
            required = (
                args.placement_tcp_search_plan,
                args.placement_tcp_search_screen,
                args.placement_tcp_shortlist_manifest,
                args.shortlist_output_dir,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "native result retention requires its plan, screen, shortlist "
                    "manifest, and shortlist directory"
                )
            search_plan = json.loads(
                args.placement_tcp_search_plan.resolve(strict=True).read_bytes()
            )
            search_screen = json.loads(
                args.placement_tcp_search_screen.resolve(strict=True).read_bytes()
            )
            shortlist_manifest = json.loads(
                args.placement_tcp_shortlist_manifest.resolve(strict=True).read_bytes()
            )
            native_receipts = {
                entry["candidate_id"]: json.loads(
                    (
                        args.shortlist_output_dir.resolve(strict=True)
                        / entry["candidate_id"]
                        / "native_receipt.json"
                    ).read_bytes()
                )
                for entry in shortlist_manifest.get("entries", [])
            }
            result = retain_placement_tcp_native_results(
                search_plan, search_screen, shortlist_manifest, native_receipts
            )
        elif args.materialize_placement_tcp_shortlist:
            required = (
                args.placement_tcp_search_plan,
                args.placement_tcp_search_screen,
                args.shortlist_output_dir,
                args.cartesian_request,
                args.ik_source_bundle,
                args.physical_blocker_experiment_plan,
                args.source_cartesian_request,
                args.collision_candidate,
                args.accepted_collision_pair_policy,
                args.toolchain_lock,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "shortlist materialization requires its plan, screen, output "
                    "directory, route and source inputs, collision candidate, pair "
                    "policy, and toolchain lock"
                )
            profile = build_profile(args.layout.resolve(strict=True))
            result = materialize_placement_tcp_native_shortlist(
                json.loads(
                    args.placement_tcp_search_plan.resolve(strict=True).read_bytes()
                ),
                json.loads(
                    args.placement_tcp_search_screen.resolve(strict=True).read_bytes()
                ),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.ik_source_bundle.resolve(strict=True).read_bytes()),
                profile,
                json.loads(
                    args.physical_blocker_experiment_plan.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(
                    args.source_cartesian_request.resolve(strict=True).read_bytes()
                ),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(
                    args.accepted_collision_pair_policy.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.toolchain_lock.resolve(strict=True).read_bytes()),
                workspace=args.workspace,
                output_dir=args.shortlist_output_dir,
            )
        elif args.run_placement_tcp_search:
            required = (
                args.placement_tcp_search_plan,
                args.cartesian_request,
                args.ik_source_bundle,
                args.physical_blocker_experiment_plan,
                args.source_cartesian_request,
                args.collision_candidate,
                args.accepted_collision_pair_policy,
                args.station_route_predicate,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "placement/TCP execution requires its plan, route variant, "
                    "IK source bundle, experiment plan, source Cartesian request, "
                    "collision candidate, accepted pair policy, and station predicate"
                )
            profile = build_profile(args.layout.resolve(strict=True))
            result = execute_placement_tcp_search(
                json.loads(
                    args.placement_tcp_search_plan.resolve(strict=True).read_bytes()
                ),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.ik_source_bundle.resolve(strict=True).read_bytes()),
                profile,
                json.loads(
                    args.physical_blocker_experiment_plan.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(
                    args.source_cartesian_request.resolve(strict=True).read_bytes()
                ),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(
                    args.accepted_collision_pair_policy.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(
                    args.station_route_predicate.resolve(strict=True).read_bytes()
                ),
                workspace=args.workspace,
            )
        elif args.plan_placement_tcp_search:
            required = (
                args.cartesian_request,
                args.physical_blocker_experiment_plan,
                args.collision_diagnostic_receipt,
                args.blocker_localization,
                args.virtual_profile,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "placement/TCP search planning requires --cartesian-request, "
                    "--physical-blocker-experiment-plan, "
                    "--collision-diagnostic-receipt, --blocker-localization, "
                    "and --virtual-profile"
                )
            if any((
                args.generate_physical_blocker_route_variant,
                args.plan_physical_blocker_experiment,
                args.build_station_route_predicate,
                args.localize_collision_blockers,
                args.accept_collision_pair_policy,
                args.bind_collision_pair_policy,
                args.propose_collision_pair_policy,
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.ik_receipt is not None,
                args.ik_source_bundle is not None,
                args.source_cartesian_request is not None,
            )):
                raise MechanicsContractError(
                    "placement/TCP search planning is mutually exclusive with "
                    "other modes"
                )
            virtual_profile_bytes = args.virtual_profile.resolve(
                strict=True
            ).read_bytes()
            result = build_placement_tcp_search_plan(
                json.loads(
                    args.physical_blocker_experiment_plan.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(
                    args.collision_diagnostic_receipt.resolve(
                        strict=True
                    ).read_bytes()
                ),
                json.loads(args.blocker_localization.resolve(strict=True).read_bytes()),
                json.loads(virtual_profile_bytes),
                virtual_profile_sha256=hashlib.sha256(
                    virtual_profile_bytes
                ).hexdigest(),
            )
        elif args.generate_physical_blocker_route_variant:
            if (
                args.cartesian_request is None
                or args.physical_blocker_experiment_plan is None
            ):
                raise MechanicsContractError(
                    "physical blocker route generation requires --cartesian-request "
                    "and --physical-blocker-experiment-plan"
                )
            if any((
                args.plan_physical_blocker_experiment,
                args.build_station_route_predicate,
                args.localize_collision_blockers,
                args.accept_collision_pair_policy,
                args.bind_collision_pair_policy,
                args.propose_collision_pair_policy,
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.ik_receipt is not None,
                args.ik_source_bundle is not None,
                args.source_cartesian_request is not None,
            )):
                raise MechanicsContractError(
                    "physical blocker route generation is mutually exclusive "
                    "with other modes"
                )
            result = build_physical_blocker_route_variant(
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(
                    args.physical_blocker_experiment_plan.resolve(
                        strict=True
                    ).read_bytes()
                ),
            )
        elif args.plan_physical_blocker_experiment:
            required = (
                args.cartesian_request,
                args.collision_candidate,
                args.collision_diagnostic_receipt,
                args.blocker_localization,
                args.virtual_profile,
                args.clearance_margin_mm,
            )
            if any(item is None for item in required):
                raise MechanicsContractError(
                    "physical blocker experiment planning requires --cartesian-request, "
                    "--collision-candidate, --collision-diagnostic-receipt, "
                    "--blocker-localization, --virtual-profile, and "
                    "--clearance-margin-mm"
                )
            if any((
                args.build_station_route_predicate,
                args.localize_collision_blockers,
                args.accept_collision_pair_policy,
                args.bind_collision_pair_policy,
                args.propose_collision_pair_policy,
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.ik_receipt is not None,
                args.ik_source_bundle is not None,
            )):
                raise MechanicsContractError(
                    "physical blocker experiment planning is mutually exclusive "
                    "with other modes"
                )
            virtual_profile_bytes = args.virtual_profile.resolve(strict=True).read_bytes()
            result = build_physical_blocker_experiment_plan(
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(
                    args.collision_diagnostic_receipt.resolve(strict=True).read_bytes()
                ),
                json.loads(args.blocker_localization.resolve(strict=True).read_bytes()),
                json.loads(virtual_profile_bytes),
                clearance_margin_mm=args.clearance_margin_mm,
                virtual_profile_sha256=hashlib.sha256(
                    virtual_profile_bytes
                ).hexdigest(),
            )
        elif args.build_station_route_predicate:
            if (
                args.cartesian_request is None
                or args.collision_candidate is None
                or args.target_station_bindings is None
            ):
                raise MechanicsContractError(
                    "station route predicate requires --cartesian-request, "
                    "--collision-candidate, and --target-station-bindings"
                )
            if any((
                args.localize_collision_blockers,
                args.accept_collision_pair_policy,
                args.bind_collision_pair_policy,
                args.propose_collision_pair_policy,
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.ik_receipt is not None,
                args.ik_source_bundle is not None,
            )):
                raise MechanicsContractError(
                    "station route predicate is mutually exclusive with other modes"
                )
            result = build_station_route_predicate(
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(
                    args.target_station_bindings.resolve(strict=True).read_bytes()
                ),
            )
        elif args.localize_collision_blockers:
            if (
                args.collision_diagnostic_receipt is None
                or args.collision_request is None
                or args.cartesian_request is None
            ):
                raise MechanicsContractError(
                    "blocker localization requires --collision-diagnostic-receipt, "
                    "--collision-request, and --cartesian-request"
                )
            if any((
                args.accept_collision_pair_policy,
                args.bind_collision_pair_policy,
                args.propose_collision_pair_policy,
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.regenerate_cartesian_schedule,
                args.ik_source_bundle is not None,
                args.ik_receipt is not None,
                args.collision_candidate is not None,
                args.toolchain_lock is not None,
                args.virtual_profile is not None,
                args.robot_usd is not None,
                args.import_receipt is not None,
                args.collision_pair_policy_proposal is not None,
                args.accepted_collision_pair_policy is not None,
            )):
                raise MechanicsContractError(
                    "blocker localization is mutually exclusive with generation, "
                    "execution, and policy-change modes"
                )
            result = build_collision_blocker_localization(
                json.loads(
                    args.collision_diagnostic_receipt.resolve(strict=True).read_bytes()
                ),
                json.loads(args.collision_request.resolve(strict=True).read_bytes()),
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
            )
        elif args.accept_collision_pair_policy:
            if args.collision_pair_policy_proposal is None:
                raise MechanicsContractError(
                    "policy acceptance requires --collision-pair-policy-proposal"
                )
            if any((
                args.propose_collision_pair_policy,
                args.bind_collision_pair_policy,
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.cartesian_request is not None,
                args.ik_receipt is not None,
                args.collision_candidate is not None,
            )):
                raise MechanicsContractError(
                    "policy acceptance is mutually exclusive with other modes"
                )
            result = accept_collision_pair_policy_proposal(json.loads(
                args.collision_pair_policy_proposal.resolve(strict=True).read_bytes()
            ))
        elif args.bind_collision_pair_policy:
            if (
                args.collision_request is None
                or args.accepted_collision_pair_policy is None
            ):
                raise MechanicsContractError(
                    "policy binding requires --collision-request and "
                    "--accepted-collision-pair-policy"
                )
            if any((
                args.propose_collision_pair_policy,
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.cartesian_request is not None,
                args.ik_receipt is not None,
                args.collision_candidate is not None,
            )):
                raise MechanicsContractError(
                    "policy binding is mutually exclusive with other modes"
                )
            result = bind_collision_pair_policy_request(
                json.loads(args.collision_request.resolve(strict=True).read_bytes()),
                json.loads(
                    args.accepted_collision_pair_policy.resolve(strict=True).read_bytes()
                ),
            )
        elif args.propose_collision_pair_policy:
            if (
                args.collision_diagnostic_receipt is None
                or args.collision_candidate is None
            ):
                raise MechanicsContractError(
                    "pair-policy proposal requires --collision-diagnostic-receipt "
                    "and --collision-candidate"
                )
            conflicting = (
                args.run_collision_diagnostic,
                args.native_h_probe,
                args.robot_tcp_bundle is not None,
                args.cartesian_request is not None,
                args.ik_receipt is not None,
                args.toolchain_lock is not None,
            )
            if any(conflicting):
                raise MechanicsContractError(
                    "pair-policy proposal is mutually exclusive with execution modes"
                )
            result = build_collision_pair_policy_proposal(
                json.loads(
                    args.collision_diagnostic_receipt.resolve(strict=True).read_bytes()
                ),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
            )
        elif args.run_collision_diagnostic:
            native_arguments = (
                args.collision_request,
                args.ik_receipt,
                args.collision_candidate,
                args.virtual_profile,
                args.robot_usd,
                args.import_receipt,
            )
            if not all(item is not None for item in native_arguments):
                raise MechanicsContractError(
                    "native collision diagnostic requires --collision-request, --ik-receipt, "
                    "--collision-candidate, --virtual-profile, --robot-usd, and --import-receipt"
                )
            if (
                args.toolchain_lock is not None
                or args.native_h_probe
                or args.robot_tcp_bundle is not None
                or args.cartesian_request is not None
            ):
                raise MechanicsContractError(
                    "native collision diagnostic is mutually exclusive with generation modes"
                )
            result = run_robot_tcp_collision_diagnostic(
                request_path=args.collision_request,
                ik_receipt_path=args.ik_receipt,
                collision_candidate_path=args.collision_candidate,
                virtual_profile_path=args.virtual_profile,
                robot_usd_path=args.robot_usd,
                import_receipt_path=args.import_receipt,
                output_path=args.output,
                status_path=args.status_output,
                accepted_pair_policy_path=args.accepted_collision_pair_policy,
                station_route_predicate_path=args.station_route_predicate,
                geometry_capture_plan_path=args.geometry_capture_plan,
                geometry_capture_output_path=args.geometry_capture_output,
                fixed_base_replay_plan_path=args.fixed_base_replay_plan,
            )
        elif args.ik_receipt is not None:
            if args.native_h_probe or args.robot_tcp_bundle is not None:
                raise MechanicsContractError(
                    "collision request is mutually exclusive with native and binding modes"
                )
            result = build_robot_tcp_collision_replay_request(
                json.loads(args.ik_receipt.resolve(strict=True).read_bytes()),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(args.toolchain_lock.resolve(strict=True).read_bytes()),
            )
        elif args.cartesian_request is not None:
            profile = build_profile(args.layout.resolve(strict=True))
            experiment_plan = (
                None
                if args.physical_blocker_experiment_plan is None
                else json.loads(
                    args.physical_blocker_experiment_plan.resolve(
                        strict=True
                    ).read_bytes()
                )
            )
            source_cartesian_request = (
                None
                if args.source_cartesian_request is None
                else json.loads(
                    args.source_cartesian_request.resolve(strict=True).read_bytes()
                )
            )
            route_shape_plan = (
                None
                if args.route_shape_campaign_plan is None
                else json.loads(
                    args.route_shape_campaign_plan.resolve(strict=True).read_bytes()
                )
            )
            route_shape_candidate = None
            placement_tcp_candidate = None
            if route_shape_plan is not None:
                route_shape_candidate = next(
                    (
                        item for item in route_shape_plan.get("candidates", [])
                        if item.get("candidate_id") == args.route_shape_candidate_id
                    ),
                    None,
                )
                if route_shape_candidate is None:
                    raise MechanicsContractError(
                        "route-shape IK candidate is absent from its plan"
                    )
                placement_tcp_candidate = route_shape_plan.get(
                    "selected_placement_tcp_candidate"
                )
            result = screen_robot_tcp_cartesian_schedule_ik(
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.ik_source_bundle.resolve(strict=True).read_bytes()),
                profile,
                workspace=args.workspace,
                experiment_plan=experiment_plan,
                source_cartesian_request=source_cartesian_request,
                placement_tcp_candidate=placement_tcp_candidate,
                route_shape_plan=route_shape_plan,
                route_shape_candidate=route_shape_candidate,
            )
        elif args.native_h_probe:
            result = run_native_h_probe(
                args.layout.resolve(strict=True),
                output_path=args.output,
                status_path=args.status_output,
            )
        elif args.robot_tcp_bundle is not None:
            profile = build_profile(args.layout.resolve(strict=True))
            bundle = json.loads(args.robot_tcp_bundle.resolve(strict=True).read_bytes())
            if args.regenerate_cartesian_schedule:
                result = build_robot_tcp_cartesian_schedule_request(profile, bundle)
            else:
                result = bind_robot_tcp_contact_requirement(profile, bundle)
        else:
            result = run_contract_campaign(args.layout.resolve(strict=True))
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        evidence_sha256 = result.get(
            "model_sha256",
            result.get(
                "dataset_sha256",
                result.get(
                    "result_sha256",
                    result.get(
                        "receipt_sha256",
                        result.get(
                            "binding_sha256",
                            result.get(
                                "request_sha256",
                                result.get(
                                    "proposal_sha256",
                                    result.get(
                                        "policy_sha256",
                                        result.get(
                                            "predicate_sha256",
                                            result.get(
                                                "plan_sha256",
                                                result.get(
                                                    "screen_sha256",
                                                    result.get(
                                                        "manifest_sha256",
                                                        result.get(
                                                            "selection_sha256",
                                                            result.get(
                                                                "demonstration_sha256",
                                                                result.get("campaign_sha256"),
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        if "review_sha256" in result:
            evidence_sha256 = result["review_sha256"]
        if not isinstance(evidence_sha256, str):
            raise MechanicsContractError("result lacks an evidence digest")
        status_record = {
            "status": result["status"],
            "receipt_sha256": evidence_sha256,
        }
        if "model_sha256" in result:
            status_record["model_sha256"] = result["model_sha256"]
        if "dataset_sha256" in result:
            status_record["dataset_sha256"] = result["dataset_sha256"]
        if "proposal_sha256" in result:
            status_record["proposal_sha256"] = result["proposal_sha256"]
        if "policy_sha256" in result:
            status_record["policy_sha256"] = result["policy_sha256"]
        if "predicate_sha256" in result:
            status_record["predicate_sha256"] = result["predicate_sha256"]
        if "plan_sha256" in result:
            status_record["plan_sha256"] = result["plan_sha256"]
        if "screen_sha256" in result:
            status_record["screen_sha256"] = result["screen_sha256"]
        if "manifest_sha256" in result:
            status_record["manifest_sha256"] = result["manifest_sha256"]
        if "selection_sha256" in result:
            status_record["selection_sha256"] = result["selection_sha256"]
        if "demonstration_sha256" in result:
            status_record["demonstration_sha256"] = result["demonstration_sha256"]
        if "campaign_sha256" in result:
            status_record["campaign_sha256"] = result["campaign_sha256"]
        if "review_sha256" in result:
            status_record["review_sha256"] = result["review_sha256"]
        args.status_output.write_text(
            json.dumps(status_record, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0 if result["status"] in {
            "PASS", "READY_FOR_DRIVE_CONTROLLED_NATIVE_REPLAY",
            "READY_FOR_IK_QUALIFICATION", "READY_FOR_COLLISION_QUALIFICATION",
            "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC",
            "DIAGNOSTIC_OVERLAPS_OBSERVED", "DIAGNOSTIC_NO_OVERLAPS_OBSERVED",
            "DIAGNOSTIC_BLOCKERS_OBSERVED",
            "REVIEW_REQUIRED_COLLISION_PAIR_POLICY",
            "REVIEW_REQUIRED_COLLISION_BLOCKER_REMEDIATION",
            "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY",
            "READY_FOR_ZERO_AUTHORITY_VARIANT_GENERATION",
            "READY_FOR_ZERO_AUTHORITY_PLACEMENT_TCP_SCREENING",
            "READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY",
            "READY_FOR_ZERO_AUTHORITY_NATIVE_ROBOT_H_REPLAY",
            "READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_NATIVE_H_REPLAY",
            "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_KEY_ADAPTATION",
            "READY_FOR_ZERO_AUTHORITY_TARGET_SPECIFIC_IK_QUALIFICATION",
            "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_ROUTE_IK_QUALIFICATION",
            "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_COLLISION_QUALIFICATION",
            "READY_FOR_ZERO_AUTHORITY_FIXED_ROOT_NATIVE_COLLISION_REPLAY",
            "READY_FOR_SELECTED_ZERO_AUTHORITY_NATIVE_REPLAY",
            "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_COLLISION_CAMPAIGN",
            "READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_NATIVE_MECHANICS_REPLAY",
            "PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_MECHANICS_CAMPAIGN",
            "COMPLETE_RANDOMIZED_DEMONSTRATION_SMOKE",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_DATASET",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_PROPOSAL_REPLAY",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_QUALIFICATION",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_RUNTIME_INPUT_REVALIDATION",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_DIAGNOSTIC_START",
            "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_COLLISION_DIAGNOSTICS",
            "COMPLETE_ZERO_AUTHORITY_COLLISION_DIAGNOSTICS_WITH_BLOCKERS",
            "COMPLETE_ZERO_AUTHORITY_COLLISION_DIAGNOSTICS_NO_BLOCKERS_OBSERVED",
            "ACCEPTED_FOR_ZERO_AUTHORITY_MECHANICS_PLAN_COMPILATION",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_RUNTIME_ADMISSION",
            "READY_FOR_ZERO_AUTHORITY_STATE_POLICY_MECHANICS_INPUT_MATERIALIZATION",
            "READY_FOR_FRESH_ZERO_AUTHORITY_ISAAC_STATE_POLICY_MECHANICS_REPLAYS",
            "NATIVE_DIAGNOSTIC_IMPROVEMENT_RETAINED",
            "NO_NATIVE_IMPROVEMENT_RETAINED",
        } else 2
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
