"""Bind the nominal RC03 fixture to one governed route-physics experiment.

ARM-251 consumes the explicit ARM-250 design prior without treating it as
installed metrology.  It binds one corrected SPACE route and the ARM-235
regeneration contract to the selected Isaac runner, but does not start Isaac,
materialize joint targets, or grant controller or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


EXPERIMENT_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_experiment.v1"
NOMINAL_PROFILE_SCHEMA = "tactevra.isaac_lm4_base_board_nominal_profile.v1"
ROUTE_PLAN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_native_mechanics_replay_plan.v2"
)
CORRECTION_PLAN_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_transit_clearance_correction_plan.v1"
)
TOOLCHAIN_SCHEMA = "rocell.isaac_sim_toolchain_lock.v1"


class NominalRoutePhysicsExperimentError(ValueError):
    """A source changed or crossed the nominal simulation authority boundary."""


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
        raise NominalRoutePhysicsExperimentError(
            "experiment is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NominalRoutePhysicsExperimentError(f"{path} is not a JSON object")
    return value


def _require_canonical_hash(
    document: Mapping[str, Any], key: str, label: str
) -> str:
    claimed = document.get(key)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise NominalRoutePhysicsExperimentError(f"{label} hash is missing")
    core = dict(document)
    core.pop(key, None)
    if _sha(core) != claimed:
        raise NominalRoutePhysicsExperimentError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("hardware_writes", 0) == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements", 0) == 0
        and document.get("controller_commands", []) == []
    )


def _validate_nominal_profile(profile: Mapping[str, Any]) -> str:
    profile_hash = _require_canonical_hash(
        profile, "profile_sha256", "ARM-250 nominal profile"
    )
    board = profile.get("board", {})
    base = profile.get("robot_base", {})
    clamp = profile.get("factory_clamp", {})
    if (
        profile.get("schema") != NOMINAL_PROFILE_SCHEMA
        or profile.get("status") != "READY_FOR_SIMULATION_ONLY_EXPERIMENTS"
        or profile.get("profile_class") != "NOMINAL_DESIGN_PRIOR"
        or profile.get("simulation_only") is not True
        or profile.get("installed_profile_compatible") is not False
        or profile.get("physical_release_effect") != "NONE"
        or not _zero_authority(profile)
        or board.get("minimum_B_mm") != [0.0, 0.0, -18.0]
        or board.get("maximum_B_mm") != [610.0, 457.0, 0.0]
        or board.get("flatness_or_bow_bound_mm") is not None
        or base.get("translation_B_mm") != [305.0, 457.0, 0.0]
        or base.get("rotation_row_major")
        != [0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        or clamp.get("rear_edge_x_range_B_mm") != [225.0, 385.0]
        or clamp.get("minimum_B_mm") is not None
        or clamp.get("maximum_B_mm") is not None
    ):
        raise NominalRoutePhysicsExperimentError("ARM-250 nominal profile changed")
    return profile_hash


def _validate_route_plan(route: Mapping[str, Any]) -> str:
    route_hash = _require_canonical_hash(route, "plan_sha256", "ARM-231 route")
    targets = route.get("joint_targets")
    if (
        route.get("schema") != ROUTE_PLAN_SCHEMA
        or route.get("status")
        != "READY_FOR_INDEPENDENT_FIXED_FIXTURE_CORRECTION_REVIEW"
        or route.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or route.get("target_id") != "SPACE"
        or route.get("sample_count") != 1416
        or not isinstance(targets, list)
        or len(targets) != 1416
        or [row.get("sequence") for row in targets] != list(range(1416))
        or route.get("contact_endpoint_sequences") != [1061, 1299]
        or route.get("fixed_fixture_correction_applied") is not True
        or route.get("native_replay_authorized") is not False
        or not _zero_authority(route)
    ):
        raise NominalRoutePhysicsExperimentError("ARM-231 route changed")
    return route_hash


def _validate_correction_plan(
    correction: Mapping[str, Any], route_hash: str
) -> str:
    correction_hash = _require_canonical_hash(
        correction, "plan_sha256", "ARM-235 correction plan"
    )
    window = correction.get("correction_window", {})
    contract = correction.get("materialization_contract", {})
    if (
        correction.get("schema") != CORRECTION_PLAN_SCHEMA
        or correction.get("status")
        != "READY_FOR_OFFLINE_TRANSIT_CLEARANCE_CORRECTION_MATERIALIZATION"
        or correction.get("source_corrected_plan_sha256") != route_hash
        or correction.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or correction.get("target_id") != "SPACE"
        or correction.get("source_sample_count") != 1416
        or window.get("first_sequence_to_regenerate") != 654
        or window.get("last_sequence_to_regenerate") != 940
        or window.get("first_preserved_contact_sequence") != 941
        or contract.get("method")
        != "DETERMINISTIC_IK_REGENERATION_WITH_CONTINUOUS_CLEARANCE_SCREEN"
        or contract.get("minimum_noncontact_tool_key_clearance_mm") != 0.5
        or contract.get("maximum_noncontact_key_displacement_mm") != 0.05
        or contract.get("maximum_adjacent_joint_step_rad") != 0.05
        or correction.get("trajectory_playback_authorized") is not False
        or correction.get("native_replay_authorized") is not False
        or not _zero_authority(correction)
    ):
        raise NominalRoutePhysicsExperimentError("ARM-235 correction plan changed")
    return correction_hash


def _validate_toolchain(toolchain: Mapping[str, Any]) -> None:
    if (
        toolchain.get("schema") != TOOLCHAIN_SCHEMA
        or toolchain.get("selection_status") != "SELECTED"
        or toolchain.get("isaac_sim_version") != "6.1.0.0"
        or toolchain.get("launch_method")
        != "python-standalone-headless-portable-single-gpu-physics-cuda-device-0"
        or toolchain.get("license_review_status")
        != "REVIEWED_FOR_INTERNAL_INTEGRATION"
        or toolchain.get("hardware_access") is not False
        or toolchain.get("physical_authority") is not False
        or toolchain.get("wire_commands") != []
    ):
        raise NominalRoutePhysicsExperimentError("Isaac toolchain lock changed")


def build_experiment(
    nominal_profile: Mapping[str, Any],
    route_plan: Mapping[str, Any],
    correction_plan: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
    *,
    source_files_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Build one byte-stable nominal experiment contract without executing it."""

    profile_hash = _validate_nominal_profile(nominal_profile)
    route_hash = _validate_route_plan(route_plan)
    correction_hash = _validate_correction_plan(correction_plan, route_hash)
    _validate_toolchain(toolchain_lock)
    expected_sources = {
        "nominal_profile",
        "route_plan",
        "correction_plan",
        "toolchain_lock",
    }
    if set(source_files_sha256) != expected_sources or any(
        not isinstance(value, str) or len(value) != 64
        for value in source_files_sha256.values()
    ):
        raise NominalRoutePhysicsExperimentError("source hash inventory changed")

    window = correction_plan["correction_window"]
    contract = correction_plan["materialization_contract"]
    core: dict[str, Any] = {
        "schema": EXPERIMENT_SCHEMA,
        "experiment_id": "space-transit-clearance-nominal-baseline-001",
        "status": "READY_FOR_NOMINAL_ROUTE_PHYSICS_EXPERIMENT_REVIEW",
        "evidence_class": "NOMINAL_DESIGN_PRIOR_SIMULATION_ONLY",
        "source_files_sha256": dict(sorted(source_files_sha256.items())),
        "source_bindings": {
            "nominal_profile_sha256": profile_hash,
            "route_plan_sha256": route_hash,
            "correction_plan_sha256": correction_hash,
        },
        "runner_binding": {
            "isaac_sim_version": toolchain_lock["isaac_sim_version"],
            "installation_sha256": toolchain_lock["installation_sha256"],
            "extension_lock_sha256": toolchain_lock["extension_lock_sha256"],
            "settings_profile_sha256": toolchain_lock["settings_profile_sha256"],
            "runner_platform": toolchain_lock["runner_platform"],
            "launch_method": toolchain_lock["launch_method"],
        },
        "fixture_binding": {
            "profile_id": nominal_profile["profile_id"],
            "coordinate_frame": "B",
            "board_minimum_B_mm": nominal_profile["board"]["minimum_B_mm"],
            "board_maximum_B_mm": nominal_profile["board"]["maximum_B_mm"],
            "robot_base_translation_B_mm": nominal_profile["robot_base"][
                "translation_B_mm"
            ],
            "robot_base_rotation_row_major": nominal_profile["robot_base"][
                "rotation_row_major"
            ],
            "rear_clamp_x_range_B_mm": nominal_profile["factory_clamp"][
                "rear_edge_x_range_B_mm"
            ],
            "board_collision_enabled": True,
            "full_clamp_collision_enabled": False,
            "fixed_fixture_configuration": route_plan[
                "fixed_fixture_configuration"
            ],
        },
        "route_binding": {
            "episode_id": route_plan["episode_id"],
            "target_id": route_plan["target_id"],
            "scene_id": route_plan["scene_id"],
            "joint_order": route_plan["joint_order"],
            "source_sample_count": route_plan["sample_count"],
            "preserved_contact_endpoint_sequences": route_plan[
                "contact_endpoint_sequences"
            ],
            "regeneration_window": {
                "first_sequence": window["first_sequence_to_regenerate"],
                "last_sequence": window["last_sequence_to_regenerate"],
                "allowed_source_phases": window["allowed_source_phases"],
            },
        },
        "experiment_matrix": [
            {
                "case_id": "nominal-fixture-baseline",
                "board_surface_z_offset_mm": 0.0,
                "robot_base_translation_offset_B_mm": [0.0, 0.0, 0.0],
                "robot_base_rotation_offset_deg": [0.0, 0.0, 0.0],
                "route_generation_method": contract["method"],
                "simulator_runs_requested": 1,
            }
        ],
        "acceptance_contract": {
            "canonical_ik_required_for_every_regenerated_row": True,
            "minimum_noncontact_tool_key_clearance_mm": contract[
                "minimum_noncontact_tool_key_clearance_mm"
            ],
            "maximum_noncontact_key_displacement_mm": contract[
                "maximum_noncontact_key_displacement_mm"
            ],
            "maximum_adjacent_joint_step_rad": contract[
                "maximum_adjacent_joint_step_rad"
            ],
            "continuous_clearance_required_for_every_adjacent_segment": True,
            "preserve_sample_count_timestamps_phases_and_contact_endpoints": True,
            "reject_indeterminate_collision_or_ik_results": True,
        },
        "required_outputs": [
            "regenerated_joint_target_rows_654_through_940",
            "per_row_canonical_ik_residual",
            "per_segment_continuous_clearance_and_colliding_body_pair",
            "per_row_tool_key_clearance_and_key_displacement",
            "root_translation_and_rotation_drift",
            "retained_source_and_output_hashes",
        ],
        "truth_isolation": {
            "simulator_truth_may_enter_model_input": False,
            "simulator_truth_may_train_or_score_policy_in_this_experiment": False,
            "simulator_result_may_promote_physical_gate": False,
        },
        "deferred_unknowns": [
            "installed_board_flatness_or_bow",
            "complete_factory_clamp_3d_envelope",
            "installed_robot_tool_workcell_collision_profile",
        ],
        "sensitivity_sweeps": [],
        "corrected_joint_targets_materialized": False,
        "isaac_execution_authorized": False,
        "isaac_started": False,
        "gpu_started": False,
        "trajectory_playback_authorized": False,
        "native_replay_authorized": False,
        "installed_profile_compatible": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "INDEPENDENT_REVIEW_THEN_ONE_NOMINAL_SIMULATION_ATTEMPT"
        ),
        "limitations": [
            "nominal_fixture_is_not_installed_metrology",
            "baseline_case_does_not_bound_real_installation_uncertainty",
            "partial_clamp_span_is_not_enabled_as_collision_geometry",
            "experiment_contract_does_not_start_isaac_or_materialize_targets",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "experiment_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nominal-profile", type=Path, required=True)
    parser.add_argument("--route-plan", type=Path, required=True)
    parser.add_argument("--correction-plan", type=Path, required=True)
    parser.add_argument("--toolchain-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "nominal_profile": args.nominal_profile.resolve(strict=True),
        "route_plan": args.route_plan.resolve(strict=True),
        "correction_plan": args.correction_plan.resolve(strict=True),
        "toolchain_lock": args.toolchain_lock.resolve(strict=True),
    }
    result = build_experiment(
        **{name: _load_object(path) for name, path in paths.items()},
        source_files_sha256={name: _file_sha(path) for name, path in paths.items()},
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
