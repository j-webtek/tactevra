from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = (
        ROOT
        / "software/integrations/isaac_sim/nominal_route_physics_experiment.py"
    )
    spec = importlib.util.spec_from_file_location("arm251_experiment", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _seal(value: dict, key: str) -> dict:
    value[key] = hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return value


def _inputs():
    route = _seal(
        {
            "schema": "tactevra.isaac_lm4_state_policy_native_mechanics_replay_plan.v2",
            "status": "READY_FOR_INDEPENDENT_FIXED_FIXTURE_CORRECTION_REVIEW",
            "episode_id": "episode-ef340d0ad2740c118d87",
            "target_id": "SPACE",
            "scene_id": "scene-001",
            "sample_count": 1416,
            "joint_targets": [{"sequence": sequence} for sequence in range(1416)],
            "joint_order": [
                "base_link_to_link1",
                "link1_to_link2",
                "link2_to_link3",
                "link3_to_link4",
                "link4_to_link5",
                "link5_to_gripper_link",
            ],
            "contact_endpoint_sequences": [1061, 1299],
            "fixed_fixture_correction_applied": True,
            "fixed_fixture_configuration": {
                "fixed_joint_enabled_explicitly": True,
                "solver_position_iteration_count": 64,
                "solver_velocity_iteration_count": 8,
            },
            "native_replay_authorized": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
        },
        "plan_sha256",
    )
    nominal = _seal(
        {
            "schema": "tactevra.isaac_lm4_base_board_nominal_profile.v1",
            "profile_id": "rc03-base-board-design-prior-001",
            "status": "READY_FOR_SIMULATION_ONLY_EXPERIMENTS",
            "profile_class": "NOMINAL_DESIGN_PRIOR",
            "simulation_only": True,
            "installed_profile_compatible": False,
            "physical_release_effect": "NONE",
            "board": {
                "minimum_B_mm": [0.0, 0.0, -18.0],
                "maximum_B_mm": [610.0, 457.0, 0.0],
                "flatness_or_bow_bound_mm": None,
            },
            "robot_base": {
                "translation_B_mm": [305.0, 457.0, 0.0],
                "rotation_row_major": [
                    0.0,
                    1.0,
                    0.0,
                    -1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                ],
            },
            "factory_clamp": {
                "rear_edge_x_range_B_mm": [225.0, 385.0],
                "minimum_B_mm": None,
                "maximum_B_mm": None,
            },
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
        },
        "profile_sha256",
    )
    correction = _seal(
        {
            "schema": (
                "tactevra.isaac_lm4_state_policy_transit_clearance_"
                "correction_plan.v1"
            ),
            "status": (
                "READY_FOR_OFFLINE_TRANSIT_CLEARANCE_CORRECTION_MATERIALIZATION"
            ),
            "source_corrected_plan_sha256": route["plan_sha256"],
            "episode_id": "episode-ef340d0ad2740c118d87",
            "target_id": "SPACE",
            "source_sample_count": 1416,
            "correction_window": {
                "first_sequence_to_regenerate": 654,
                "last_sequence_to_regenerate": 940,
                "first_preserved_contact_sequence": 941,
                "allowed_source_phases": ["TRANSIT", "HOVER"],
            },
            "materialization_contract": {
                "method": (
                    "DETERMINISTIC_IK_REGENERATION_WITH_CONTINUOUS_CLEARANCE_SCREEN"
                ),
                "minimum_noncontact_tool_key_clearance_mm": 0.5,
                "maximum_noncontact_key_displacement_mm": 0.05,
                "maximum_adjacent_joint_step_rad": 0.05,
            },
            "trajectory_playback_authorized": False,
            "native_replay_authorized": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
        },
        "plan_sha256",
    )
    return {
        "nominal_profile": nominal,
        "route_plan": route,
        "correction_plan": correction,
        "toolchain_lock": _load(
            ROOT / "software/config/isaac_sim_toolchain_lock.json"
        ),
    }


def _build():
    return _module().build_experiment(
        **_inputs(),
        source_files_sha256={
            "nominal_profile": "1" * 64,
            "route_plan": "2" * 64,
            "correction_plan": "3" * 64,
            "toolchain_lock": "4" * 64,
        },
    )


def test_arm251_binds_nominal_fixture_to_governed_space_route() -> None:
    result = _build()

    assert result["status"] == "READY_FOR_NOMINAL_ROUTE_PHYSICS_EXPERIMENT_REVIEW"
    assert result["fixture_binding"]["board_maximum_B_mm"] == [610.0, 457.0, 0.0]
    assert result["fixture_binding"]["robot_base_translation_B_mm"] == [
        305.0,
        457.0,
        0.0,
    ]
    assert result["route_binding"]["episode_id"] == "episode-ef340d0ad2740c118d87"
    assert result["route_binding"]["regeneration_window"] == {
        "first_sequence": 654,
        "last_sequence": 940,
        "allowed_source_phases": ["TRANSIT", "HOVER"],
    }


def test_arm251_makes_only_the_supported_nominal_case_executable_after_review() -> None:
    result = _build()

    assert result["experiment_matrix"] == [
        {
            "case_id": "nominal-fixture-baseline",
            "board_surface_z_offset_mm": 0.0,
            "robot_base_translation_offset_B_mm": [0.0, 0.0, 0.0],
            "robot_base_rotation_offset_deg": [0.0, 0.0, 0.0],
            "route_generation_method": (
                "DETERMINISTIC_IK_REGENERATION_WITH_CONTINUOUS_CLEARANCE_SCREEN"
            ),
            "simulator_runs_requested": 1,
        }
    ]
    assert result["fixture_binding"]["board_collision_enabled"] is True
    assert result["fixture_binding"]["full_clamp_collision_enabled"] is False
    assert result["sensitivity_sweeps"] == []


def test_arm251_preserves_truth_installed_and_physical_separation() -> None:
    result = _build()

    assert result["isaac_execution_authorized"] is False
    assert result["installed_profile_compatible"] is False
    assert result["truth_isolation"] == {
        "simulator_truth_may_enter_model_input": False,
        "simulator_truth_may_train_or_score_policy_in_this_experiment": False,
        "simulator_result_may_promote_physical_gate": False,
    }
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []
    assert result["wire_commands"] == []


@pytest.mark.parametrize(
    ("source", "mutate"),
    [
        ("nominal_profile", lambda value: value["board"].update(width_mm=609.0)),
        ("route_plan", lambda value: value.update(target_id="ENTER")),
        (
            "correction_plan",
            lambda value: value["correction_window"].update(
                first_sequence_to_regenerate=655
            ),
        ),
        ("toolchain_lock", lambda value: value.update(selection_status="UNSELECTED")),
    ],
)
def test_arm251_rejects_source_drift(source: str, mutate) -> None:
    module = _module()
    values = copy.deepcopy(_inputs())
    mutate(values[source])

    with pytest.raises(module.NominalRoutePhysicsExperimentError):
        module.build_experiment(
            **values,
            source_files_sha256={
                "nominal_profile": "1" * 64,
                "route_plan": "2" * 64,
                "correction_plan": "3" * 64,
                "toolchain_lock": "4" * 64,
            },
        )
