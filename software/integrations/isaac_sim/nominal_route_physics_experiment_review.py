"""Independently review one ARM-251 nominal route-physics experiment.

ARM-252 reopens the experiment and every bound source.  It may admit exactly
one later simulation-only attempt, but it does not start Isaac, generate joint
targets, play a trajectory, or grant hardware or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_experiment_review.v1"
EXPERIMENT_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_experiment.v1"
PROFILE_SCHEMA = "tactevra.isaac_lm4_base_board_nominal_profile.v1"
ROUTE_SCHEMA = "tactevra.isaac_lm4_state_policy_native_mechanics_replay_plan.v2"
CORRECTION_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_transit_clearance_correction_plan.v1"
)
TOOLCHAIN_SCHEMA = "rocell.isaac_sim_toolchain_lock.v1"


class NominalRoutePhysicsExperimentReviewError(ValueError):
    """The reviewed contract changed or crossed its authority boundary."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NominalRoutePhysicsExperimentReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NominalRoutePhysicsExperimentReviewError(
            f"{path} is not a JSON object"
        )
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise NominalRoutePhysicsExperimentReviewError(f"{label} hash is missing")
    core = dict(document)
    core.pop(key, None)
    if _sha(core) != claimed:
        raise NominalRoutePhysicsExperimentReviewError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("hardware_writes", 0) == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements", 0) == 0
        and document.get("controller_commands", []) == []
        and document.get("wire_commands", []) == []
    )


def _review_source_identity(
    experiment: Mapping[str, Any],
    nominal_profile: Mapping[str, Any],
    route_plan: Mapping[str, Any],
    correction_plan: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
    source_files_sha256: Mapping[str, str],
) -> tuple[str, str, str]:
    expected_names = {
        "nominal_profile",
        "route_plan",
        "correction_plan",
        "toolchain_lock",
    }
    if set(source_files_sha256) != expected_names:
        raise NominalRoutePhysicsExperimentReviewError(
            "source file inventory changed"
        )
    if experiment.get("source_files_sha256") != dict(
        sorted(source_files_sha256.items())
    ):
        raise NominalRoutePhysicsExperimentReviewError(
            "experiment source file hashes changed"
        )

    profile_hash = _require_hash(
        nominal_profile, "profile_sha256", "ARM-250 nominal profile"
    )
    route_hash = _require_hash(route_plan, "plan_sha256", "ARM-231 route")
    correction_hash = _require_hash(
        correction_plan, "plan_sha256", "ARM-235 correction plan"
    )
    if experiment.get("source_bindings") != {
        "nominal_profile_sha256": profile_hash,
        "route_plan_sha256": route_hash,
        "correction_plan_sha256": correction_hash,
    }:
        raise NominalRoutePhysicsExperimentReviewError(
            "canonical source bindings changed"
        )
    return profile_hash, route_hash, correction_hash


def _review_source_semantics(
    nominal_profile: Mapping[str, Any],
    route_plan: Mapping[str, Any],
    correction_plan: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
) -> None:
    board = nominal_profile.get("board", {})
    base = nominal_profile.get("robot_base", {})
    clamp = nominal_profile.get("factory_clamp", {})
    window = correction_plan.get("correction_window", {})
    contract = correction_plan.get("materialization_contract", {})
    targets = route_plan.get("joint_targets")
    if (
        nominal_profile.get("schema") != PROFILE_SCHEMA
        or nominal_profile.get("status")
        != "READY_FOR_SIMULATION_ONLY_EXPERIMENTS"
        or nominal_profile.get("profile_class") != "NOMINAL_DESIGN_PRIOR"
        or nominal_profile.get("simulation_only") is not True
        or nominal_profile.get("installed_profile_compatible") is not False
        or board.get("minimum_B_mm") != [0.0, 0.0, -18.0]
        or board.get("maximum_B_mm") != [610.0, 457.0, 0.0]
        or board.get("flatness_or_bow_bound_mm") is not None
        or base.get("translation_B_mm") != [305.0, 457.0, 0.0]
        or base.get("rotation_row_major")
        != [0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        or clamp.get("rear_edge_x_range_B_mm") != [225.0, 385.0]
        or clamp.get("minimum_B_mm") is not None
        or clamp.get("maximum_B_mm") is not None
        or not _zero_authority(nominal_profile)
    ):
        raise NominalRoutePhysicsExperimentReviewError(
            "ARM-250 nominal profile semantics changed"
        )
    if (
        route_plan.get("schema") != ROUTE_SCHEMA
        or route_plan.get("status")
        != "READY_FOR_INDEPENDENT_FIXED_FIXTURE_CORRECTION_REVIEW"
        or route_plan.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or route_plan.get("target_id") != "SPACE"
        or route_plan.get("sample_count") != 1416
        or not isinstance(targets, list)
        or len(targets) != 1416
        or [row.get("sequence") for row in targets] != list(range(1416))
        or route_plan.get("contact_endpoint_sequences") != [1061, 1299]
        or route_plan.get("fixed_fixture_correction_applied") is not True
        or route_plan.get("native_replay_authorized") is not False
        or not _zero_authority(route_plan)
    ):
        raise NominalRoutePhysicsExperimentReviewError(
            "ARM-231 route semantics changed"
        )
    if (
        correction_plan.get("schema") != CORRECTION_SCHEMA
        or correction_plan.get("status")
        != "READY_FOR_OFFLINE_TRANSIT_CLEARANCE_CORRECTION_MATERIALIZATION"
        or correction_plan.get("source_corrected_plan_sha256")
        != route_plan.get("plan_sha256")
        or correction_plan.get("episode_id") != route_plan.get("episode_id")
        or correction_plan.get("target_id") != "SPACE"
        or correction_plan.get("source_sample_count") != 1416
        or window.get("first_sequence_to_regenerate") != 654
        or window.get("last_sequence_to_regenerate") != 940
        or window.get("first_preserved_contact_sequence") != 941
        or window.get("allowed_source_phases") != ["TRANSIT", "HOVER"]
        or contract.get("method")
        != "DETERMINISTIC_IK_REGENERATION_WITH_CONTINUOUS_CLEARANCE_SCREEN"
        or contract.get("minimum_noncontact_tool_key_clearance_mm") != 0.5
        or contract.get("maximum_noncontact_key_displacement_mm") != 0.05
        or contract.get("maximum_adjacent_joint_step_rad") != 0.05
        or correction_plan.get("trajectory_playback_authorized") is not False
        or correction_plan.get("native_replay_authorized") is not False
        or not _zero_authority(correction_plan)
    ):
        raise NominalRoutePhysicsExperimentReviewError(
            "ARM-235 correction semantics changed"
        )
    if (
        toolchain_lock.get("schema") != TOOLCHAIN_SCHEMA
        or toolchain_lock.get("selection_status") != "SELECTED"
        or toolchain_lock.get("isaac_sim_version") != "6.1.0.0"
        or toolchain_lock.get("hardware_access") is not False
        or toolchain_lock.get("physical_authority") is not False
        or toolchain_lock.get("wire_commands") != []
    ):
        raise NominalRoutePhysicsExperimentReviewError(
            "Isaac toolchain semantics changed"
        )


def _review_experiment_semantics(
    experiment: Mapping[str, Any],
    nominal_profile: Mapping[str, Any],
    route_plan: Mapping[str, Any],
    correction_plan: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
) -> str:
    experiment_hash = _require_hash(
        experiment, "experiment_sha256", "ARM-251 experiment"
    )
    fixture = experiment.get("fixture_binding", {})
    route = experiment.get("route_binding", {})
    acceptance = experiment.get("acceptance_contract", {})
    window = correction_plan["correction_window"]
    contract = correction_plan["materialization_contract"]
    expected_case = {
        "case_id": "nominal-fixture-baseline",
        "board_surface_z_offset_mm": 0.0,
        "robot_base_translation_offset_B_mm": [0.0, 0.0, 0.0],
        "robot_base_rotation_offset_deg": [0.0, 0.0, 0.0],
        "route_generation_method": contract["method"],
        "simulator_runs_requested": 1,
    }
    expected_outputs = [
        "regenerated_joint_target_rows_654_through_940",
        "per_row_canonical_ik_residual",
        "per_segment_continuous_clearance_and_colliding_body_pair",
        "per_row_tool_key_clearance_and_key_displacement",
        "root_translation_and_rotation_drift",
        "retained_source_and_output_hashes",
    ]
    runner = experiment.get("runner_binding", {})
    if (
        experiment.get("schema") != EXPERIMENT_SCHEMA
        or experiment.get("status")
        != "READY_FOR_NOMINAL_ROUTE_PHYSICS_EXPERIMENT_REVIEW"
        or experiment.get("experiment_id")
        != "space-transit-clearance-nominal-baseline-001"
        or experiment.get("evidence_class")
        != "NOMINAL_DESIGN_PRIOR_SIMULATION_ONLY"
        or experiment.get("experiment_matrix") != [expected_case]
        or fixture.get("profile_id") != nominal_profile.get("profile_id")
        or fixture.get("coordinate_frame") != "B"
        or fixture.get("board_minimum_B_mm")
        != nominal_profile["board"]["minimum_B_mm"]
        or fixture.get("board_maximum_B_mm")
        != nominal_profile["board"]["maximum_B_mm"]
        or fixture.get("robot_base_translation_B_mm")
        != nominal_profile["robot_base"]["translation_B_mm"]
        or fixture.get("robot_base_rotation_row_major")
        != nominal_profile["robot_base"]["rotation_row_major"]
        or fixture.get("rear_clamp_x_range_B_mm")
        != nominal_profile["factory_clamp"]["rear_edge_x_range_B_mm"]
        or fixture.get("board_collision_enabled") is not True
        or fixture.get("full_clamp_collision_enabled") is not False
        or fixture.get("fixed_fixture_configuration")
        != route_plan["fixed_fixture_configuration"]
        or route.get("episode_id") != route_plan["episode_id"]
        or route.get("target_id") != "SPACE"
        or route.get("source_sample_count") != 1416
        or route.get("preserved_contact_endpoint_sequences") != [1061, 1299]
        or route.get("regeneration_window")
        != {
            "first_sequence": window["first_sequence_to_regenerate"],
            "last_sequence": window["last_sequence_to_regenerate"],
            "allowed_source_phases": window["allowed_source_phases"],
        }
        or acceptance.get("minimum_noncontact_tool_key_clearance_mm")
        != contract["minimum_noncontact_tool_key_clearance_mm"]
        or acceptance.get("maximum_noncontact_key_displacement_mm")
        != contract["maximum_noncontact_key_displacement_mm"]
        or acceptance.get("maximum_adjacent_joint_step_rad")
        != contract["maximum_adjacent_joint_step_rad"]
        or acceptance.get("canonical_ik_required_for_every_regenerated_row")
        is not True
        or acceptance.get("continuous_clearance_required_for_every_adjacent_segment")
        is not True
        or acceptance.get("preserve_sample_count_timestamps_phases_and_contact_endpoints")
        is not True
        or acceptance.get("reject_indeterminate_collision_or_ik_results")
        is not True
        or experiment.get("required_outputs") != expected_outputs
        or runner.get("isaac_sim_version")
        != toolchain_lock.get("isaac_sim_version")
        or runner.get("installation_sha256")
        != toolchain_lock.get("installation_sha256")
        or runner.get("extension_lock_sha256")
        != toolchain_lock.get("extension_lock_sha256")
        or runner.get("settings_profile_sha256")
        != toolchain_lock.get("settings_profile_sha256")
        or runner.get("runner_platform") != toolchain_lock.get("runner_platform")
        or runner.get("launch_method") != toolchain_lock.get("launch_method")
        or experiment.get("deferred_unknowns")
        != [
            "installed_board_flatness_or_bow",
            "complete_factory_clamp_3d_envelope",
            "installed_robot_tool_workcell_collision_profile",
        ]
        or experiment.get("sensitivity_sweeps") != []
        or experiment.get("corrected_joint_targets_materialized") is not False
        or experiment.get("isaac_execution_authorized") is not False
        or experiment.get("isaac_started") is not False
        or experiment.get("gpu_started") is not False
        or experiment.get("trajectory_playback_authorized") is not False
        or experiment.get("native_replay_authorized") is not False
        or experiment.get("installed_profile_compatible") is not False
        or experiment.get("gate_promotions") != []
        or experiment.get("next_required_stage")
        != "INDEPENDENT_REVIEW_THEN_ONE_NOMINAL_SIMULATION_ATTEMPT"
        or not _zero_authority(experiment)
    ):
        raise NominalRoutePhysicsExperimentReviewError(
            "ARM-251 experiment semantics changed"
        )
    if experiment.get("truth_isolation") != {
        "simulator_truth_may_enter_model_input": False,
        "simulator_truth_may_train_or_score_policy_in_this_experiment": False,
        "simulator_result_may_promote_physical_gate": False,
    }:
        raise NominalRoutePhysicsExperimentReviewError(
            "simulator truth boundary changed"
        )
    return experiment_hash


def build_review(
    experiment: Mapping[str, Any],
    nominal_profile: Mapping[str, Any],
    route_plan: Mapping[str, Any],
    correction_plan: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
    *,
    source_files_sha256: Mapping[str, str],
    experiment_file_sha256: str,
) -> dict[str, Any]:
    """Build a signed review and one-attempt simulation-only admission."""

    _review_source_semantics(
        nominal_profile, route_plan, correction_plan, toolchain_lock
    )
    profile_hash, route_hash, correction_hash = _review_source_identity(
        experiment,
        nominal_profile,
        route_plan,
        correction_plan,
        toolchain_lock,
        source_files_sha256,
    )
    experiment_hash = _review_experiment_semantics(
        experiment,
        nominal_profile,
        route_plan,
        correction_plan,
        toolchain_lock,
    )
    if not isinstance(experiment_file_sha256, str) or len(
        experiment_file_sha256
    ) != 64:
        raise NominalRoutePhysicsExperimentReviewError(
            "experiment file hash is missing"
        )

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm252-space-nominal-route-physics-review-001",
        "status": (
            "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_NOMINAL_SIMULATION_ATTEMPT"
        ),
        "source_experiment_sha256": experiment_hash,
        "source_experiment_file_sha256": experiment_file_sha256,
        "reviewed_source_files_sha256": dict(sorted(source_files_sha256.items())),
        "reviewed_source_bindings": {
            "nominal_profile_sha256": profile_hash,
            "route_plan_sha256": route_hash,
            "correction_plan_sha256": correction_hash,
        },
        "review_findings": {
            "source_identity_and_canonical_hashes_verified": True,
            "nominal_fixture_scope_verified": True,
            "single_space_route_scope_verified": True,
            "regeneration_window_654_through_940_verified": True,
            "clearance_displacement_ik_and_joint_step_limits_verified": True,
            "truth_isolation_verified": True,
            "zero_hardware_and_physical_authority_verified": True,
        },
        "simulation_attempt_admission": {
            "case_id": "nominal-fixture-baseline",
            "episode_id": "episode-ef340d0ad2740c118d87",
            "target_id": "SPACE",
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "fresh_source_revalidation_required_at_launch": True,
            "launch_authorized_by_this_review": False,
            "hardware_or_physical_authority": False,
        },
        "automatic_typing_goal": {
            "current_stage": "SINGLE_KEY_SPACE_NOMINAL_ROUTE_REGENERATION",
            "evidence_contribution": (
                "qualify one reusable approach-traverse-descent primitive"
            ),
            "next_after_pass": (
                "EXPAND_THE_SAME_CONTRACT_TO_A_REPRESENTATIVE_MULTI_KEY_SET"
            ),
            "later_stage": (
                "VISION_CONDITIONED_KEY_LOCALIZATION_AND_ROLLING_HORIZON_TYPING"
            ),
            "physical_typing_requires_separate_installed_qualification": True,
        },
        "isaac_execution_authorized": False,
        "isaac_started": False,
        "gpu_started": False,
        "joint_targets_materialized": False,
        "trajectory_playback_authorized": False,
        "native_replay_authorized": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "ONE_NOMINAL_SIMULATION_ATTEMPT_AFTER_SEPARATE_LAUNCH_AUTHORIZATION"
        ),
        "limitations": [
            "review_does_not_start_isaac_or_generate_replacement_targets",
            "single_space_case_is_not_multi_key_automatic_typing",
            "nominal_fixture_is_not_installed_metrology",
            "full_clamp_collision_and_installed_uncertainty_remain_deferred",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--nominal-profile", type=Path, required=True)
    parser.add_argument("--route-plan", type=Path, required=True)
    parser.add_argument("--correction-plan", type=Path, required=True)
    parser.add_argument("--toolchain-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_paths = {
        "nominal_profile": args.nominal_profile.resolve(strict=True),
        "route_plan": args.route_plan.resolve(strict=True),
        "correction_plan": args.correction_plan.resolve(strict=True),
        "toolchain_lock": args.toolchain_lock.resolve(strict=True),
    }
    experiment_path = args.experiment.resolve(strict=True)
    result = build_review(
        experiment=_load_object(experiment_path),
        **{
            name: _load_object(path)
            for name, path in source_paths.items()
        },
        source_files_sha256={
            name: _file_sha(path) for name, path in source_paths.items()
        },
        experiment_file_sha256=_file_sha(experiment_path),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
