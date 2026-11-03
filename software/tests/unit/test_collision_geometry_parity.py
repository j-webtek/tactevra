import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/integrations/isaac_sim/collision_geometry_parity.py"
SPEC = importlib.util.spec_from_file_location("collision_geometry_parity", SCRIPT)
assert SPEC and SPEC.loader
parity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parity)


def _sealed(document, field):
    result = deepcopy(document)
    result[field] = parity._canonical_sha256(result)
    return result


def _request(candidate_id):
    return _sealed(
        {
            "route_shape_candidate_id": candidate_id,
            "samples": [
                {"sequence": 0, "phase": "TRANSIT", "target_id": "H"},
                {"sequence": 1, "phase": "CONTACT", "target_id": "H"},
                {"sequence": 2, "phase": "RETRACT", "target_id": "H"},
            ],
            "authority": {
                "hardware": False,
                "motion": False,
                "physical_keyboard_qualification": False,
            },
            "hardware_access": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
        },
        "request_sha256",
    )


def _result(candidate_id, receipt_digest):
    robot_board = ["robot:link5", "workcell:board_solid"]
    robot_keyboard = ["robot:gripper", "workcell:keyboard"]
    return {
        "candidate_id": candidate_id,
        "bounded_sample_count": 3,
        "native_receipt_schema": "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v4",
        "native_receipt_sha256": receipt_digest,
        "station_route_predicate_applied": True,
        "raw_native_samples": [
            {
                "sample_sequence": 0,
                "sample_id": "sample-0",
                "source_segment_index": 0,
                "physical_solid_blocker_pairs": [robot_board],
                "raw_collision_primitive_pairs": [
                    {"body_pair": robot_board, "primitive_indices": [0, 0]}
                ],
            },
            {
                "sample_sequence": 1,
                "sample_id": "sample-1",
                "source_segment_index": 1,
                "physical_solid_blocker_pairs": [robot_board, robot_keyboard],
                "raw_collision_primitive_pairs": [
                    {"body_pair": robot_board, "primitive_indices": [0, 0]},
                    {"body_pair": robot_keyboard, "primitive_indices": [0, 0]},
                ],
            },
            {
                "sample_sequence": 2,
                "sample_id": "sample-2",
                "source_segment_index": 2,
                "physical_solid_blocker_pairs": [],
                "raw_collision_primitive_pairs": [],
            },
        ],
    }


def _selection():
    return _sealed(
        {
            "schema": parity.SELECTION_SCHEMA,
            "status": "INCOMPLETE_V4_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED",
            "native_improvement_over_control": False,
            "selected_candidate_id": None,
            "retained_results": [
                _result("candidate-a", "a" * 64),
                _result("candidate-b", "b" * 64),
            ],
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
        },
        "selection_sha256",
    )


def _collision_candidate():
    return _sealed(
        {
            "schema": "tactevra.simulation_collision_candidate.v1",
            "physical_authority": False,
            "commands": [],
            "hardware_write_count": 0,
            "physical_movement_count": 0,
        },
        "candidate_sha256",
    )


def _primitive(world_x=10.0):
    return {
        "body_id": "robot:link5",
        "primitive_index": 0,
        "kind": "oriented_box",
        "half_extents_mm": [1.0, 2.0, 3.0],
        "local_center_mm": [0.0, 0.0, 0.0],
        "local_rotation_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "world_matrix_row_major": [
            1.0,
            0.0,
            0.0,
            world_x,
            0.0,
            1.0,
            0.0,
            20.0,
            0.0,
            0.0,
            1.0,
            30.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ],
    }


def _capture(source, plan_hash, world_x=10.0):
    return _sealed(
        {
            "schema": parity.CAPTURE_SCHEMA,
            "source": source,
            "source_plan_sha256": plan_hash,
            "samples": [
                {
                    "candidate_id": "candidate-a",
                    "sample_sequence": 0,
                    "primitives": [_primitive(world_x)],
                }
            ],
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
        },
        "capture_sha256",
    )


def test_build_capture_plan_selects_onset_peak_and_clear_samples():
    requests = {
        candidate_id: _request(candidate_id)
        for candidate_id in ("candidate-a", "candidate-b")
    }
    plan = parity.build_capture_plan(
        _selection(), _collision_candidate(), requests
    )

    assert plan["status"] == "READY_FOR_ZERO_AUTHORITY_NATIVE_AND_OFFLINE_GEOMETRY_CAPTURE"
    assert len(plan["candidate_captures"]) == 2
    for candidate in plan["candidate_captures"]:
        samples = candidate["capture_samples"]
        assert [item["sample_sequence"] for item in samples] == [0, 1, 2]
        assert samples[0]["selection_roles"] == ["FIRST_PHYSICAL_ONSET"]
        assert samples[1]["selection_roles"] == ["PEAK_PHYSICAL_PAIR_COUNT"]
        assert samples[2]["selection_roles"] == ["FIRST_PHYSICAL_CLEAR_AFTER_ONSET"]
        assert samples[2]["physical_primitive_pairs"] == []


def test_compare_captures_classifies_translation_and_rejects_tampering():
    plan = parity.build_capture_plan(
        _selection(),
        _collision_candidate(),
        {candidate_id: _request(candidate_id) for candidate_id in ("candidate-a", "candidate-b")},
    )
    native = _capture("NATIVE_PHYSX", plan["plan_sha256"], world_x=11.0)
    offline = _capture("OFFLINE_OBB", plan["plan_sha256"], world_x=10.0)

    report = parity.compare_captures(plan, native, offline)
    assert report["status"] == "PARITY_DISCREPANCY_CLASSIFIED"
    assert report["mismatch_count"] == 1
    assert report["classifications"] == ["WORLD_TRANSLATION_MISMATCH"]
    assert report["comparisons"][0]["maximum_translation_delta_mm"] == 1.0

    native["samples"][0]["primitives"][0]["world_matrix_row_major"][3] = 12.0
    with pytest.raises(parity.ParityContractError, match="NATIVE_PHYSX capture hash mismatch"):
        parity.compare_captures(plan, native, offline)


def test_systematic_findings_classify_shared_robot_z_drift():
    comparisons = [
        {
            "candidate_id": "candidate-a",
            "sample_sequence": sequence,
            "body_id": body_id,
            "primitive_index": primitive_index,
            "classification": "WORLD_TRANSLATION_MISMATCH",
            "translation_offset_native_minus_offline_mm": [
                0.004 * primitive_index,
                -0.003 * primitive_index,
                z_offset - 0.002 * primitive_index,
            ],
        }
        for sequence, z_offset in ((4, -12.0), (8, -24.0))
        for body_id, primitive_index in (
            ("robot:base_link", 0),
            ("robot:link5", 1),
        )
    ]
    comparisons.extend(
        {
            "candidate_id": "candidate-a",
            "sample_sequence": sequence,
            "body_id": "workcell:keyboard",
            "primitive_index": 0,
            "classification": "MATCH",
        }
        for sequence in (4, 8)
    )

    findings, conclusion = parity._systematic_findings(comparisons)

    assert [item["classification"] for item in findings] == [
        "STATIC_WORKCELL_PARITY_CONFIRMED",
        "ROBOT_RIGID_TRANSLATION_OFFSET_BY_SAMPLE",
    ]
    assert conclusion == {
        "primary_classification": "NATIVE_ROBOT_ROOT_Z_DRIFT",
        "retained_native_collision_conclusion_usable_for_fixed_base_route_comparison": False,
        "required_next_action": "REPLAY_WITH_FIXED_BASE_AND_ROOT_POSE_INVARIANT",
    }


def test_build_fixed_base_plan_binds_v4_history_and_root_invariant():
    selection = _selection()
    parity_plan = parity.build_capture_plan(
        selection,
        _collision_candidate(),
        {
            candidate_id: _request(candidate_id)
            for candidate_id in ("candidate-a", "candidate-b")
        },
    )
    report = _sealed(
        {
            "schema": parity.REPORT_SCHEMA,
            "status": "PARITY_DISCREPANCY_CLASSIFIED",
            "source_plan_sha256": parity_plan["plan_sha256"],
            "diagnostic_conclusion": {
                "primary_classification": "NATIVE_ROBOT_ROOT_Z_DRIFT",
                "retained_native_collision_conclusion_usable_for_fixed_base_route_comparison": False,
                "required_next_action": "REPLAY_WITH_FIXED_BASE_AND_ROOT_POSE_INVARIANT",
            },
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
        },
        "report_sha256",
    )

    fixed = parity.build_fixed_base_replay_plan(
        selection, report, parity_plan
    )

    assert fixed["schema"] == parity.FIXED_BASE_PLAN_SCHEMA
    assert fixed["fixed_base_contract"]["mechanism"] == "USD_FIXED_JOINT_TO_WORLD"
    assert fixed["root_pose_invariant"]["required_after_every_sample"] is True
    assert fixed["root_pose_invariant"]["orientation_tolerance_deg"] == 0.1
    assert fixed["root_pose_invariant"]["failure_behavior"] == (
        "ERROR_NO_ACCEPTED_COLLISION_RECEIPT"
    )
    assert {item["source_request_sha256"] for item in fixed["candidates"]} == {
        _request("candidate-a")["request_sha256"],
        _request("candidate-b")["request_sha256"],
    }
    assert fixed["source_v4_receipts_mutated"] is False

    report["diagnostic_conclusion"]["primary_classification"] = "MATCH"
    with pytest.raises(parity.ParityContractError, match="parity report hash mismatch"):
        parity.build_fixed_base_replay_plan(selection, report, parity_plan)


def test_retain_fixed_base_results_requires_complete_invariant_passing_receipts():
    selection = _selection()
    parity_plan = parity.build_capture_plan(
        selection,
        _collision_candidate(),
        {
            candidate_id: _request(candidate_id)
            for candidate_id in ("candidate-a", "candidate-b")
        },
    )
    report = _sealed(
        {
            "schema": parity.REPORT_SCHEMA,
            "status": "PARITY_DISCREPANCY_CLASSIFIED",
            "source_plan_sha256": parity_plan["plan_sha256"],
            "diagnostic_conclusion": {
                "primary_classification": "NATIVE_ROBOT_ROOT_Z_DRIFT",
                "retained_native_collision_conclusion_usable_for_fixed_base_route_comparison": False,
                "required_next_action": "REPLAY_WITH_FIXED_BASE_AND_ROOT_POSE_INVARIANT",
            },
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
        },
        "report_sha256",
    )
    plan = parity.build_fixed_base_replay_plan(selection, report, parity_plan)

    def receipt(candidate):
        return _sealed(
            {
                "schema": parity.FIXED_BASE_RECEIPT_SCHEMA,
                "status": "DIAGNOSTIC_OVERLAPS_OBSERVED",
                "bounded_sample_count": candidate["source_v4_bounded_sample_count"],
                "fixed_base_replay_applied": True,
                "source_v4_native_receipt_sha256": candidate[
                    "source_v4_native_receipt_sha256"
                ],
                "source_v4_receipt_mutated": False,
                "source_bindings": {
                    "fixed_base_replay_plan_sha256": plan["plan_sha256"]
                },
                "root_pose_invariant": {
                    "status": "PASS",
                    "observation_count": candidate["source_v4_bounded_sample_count"] + 1,
                    "expected_observation_count": candidate[
                        "source_v4_bounded_sample_count"
                    ] + 1,
                    "maximum_translation_delta_mm": 0.006,
                    "maximum_orientation_delta_deg": 0.056,
                },
                "physical_solid_blocker_pair_count": 0,
                "planning_envelope_blocker_pair_count": 0,
                "unreviewed_blocker_pair_count": 0,
                "policy_excluded_pair_count": 5,
                "hardware_access": False,
                "physical_authority": False,
                "controller_commands": [],
                "hardware_writes": 0,
                "physical_movements": 0,
            },
            "receipt_sha256",
        )

    receipts = [receipt(candidate) for candidate in plan["candidates"]]
    result = parity.retain_fixed_base_replay_results(plan, receipts)

    assert result["schema"] == parity.FIXED_BASE_RESULT_SCHEMA
    assert result["status"] == (
        "FIXED_BASE_REPLAY_COMPLETE_NO_PHYSICAL_SOLID_BLOCKERS"
    )
    assert result["fixed_base_root_invariant_passed_for_all_candidates"] is True
    assert result["zero_physical_solid_blockers_for_all_candidates"] is True
    assert result["next_action"] == (
        "COMPARE_KEY_MECHANICS_AND_SELECT_LEARNING_BASELINE"
    )

    receipts[0]["root_pose_invariant"]["status"] = "FAIL"
    with pytest.raises(parity.ParityContractError, match="v5 receipt hash mismatch"):
        parity.retain_fixed_base_replay_results(plan, receipts)


def _learning_baseline_inputs():
    profile = _sealed(
        {
            "schema": parity.KEY_MECHANICS_PROFILE_SCHEMA,
            "target_plane_z_board_mm": 21.0,
            "regions": {
                "H": {
                    "center_board_xy_mm": [10.0, 20.0],
                    "half_extent_mm": [8.0, 8.0],
                }
            },
            "mechanics_prior": {
                "activation_mm": {"nominal": 2.0},
                "release_mm": {"nominal": 1.0},
                "travel_mm": {"nominal": 3.5},
                "stiffness_n_per_mm": {"nominal": 0.45},
                "damping_n_s_per_mm": {"nominal": 0.02},
                "center_margin_mm": 2.0,
            },
            "authority": {
                "hardware": False,
                "motion": False,
                "physical_keyboard_qualification": False,
            },
        },
        "profile_sha256",
    )
    candidate_ids = ("candidate-a", "candidate-b")
    requests = []
    ik_receipts = []
    v5_receipts = []
    retained = []
    phases = ("HOVER", "CONTACT", "RETRACT") * 2
    action_indices = (0, 0, 0, 1, 1, 1)
    z_values = (26.0, 18.3, 26.0, 26.0, 18.3, 26.0)
    for candidate_index, candidate_id in enumerate(candidate_ids, start=1):
        route = {
            "candidate_id": candidate_id,
            "xy_corridor_topology": "DIRECT_LINEAR" if candidate_index == 1 else "Y_THEN_X",
            "corridor_height_board_mm": 90.0 if candidate_index == 1 else 70.0,
        }
        samples = [
            {
                "sequence": sequence,
                "time_from_start_ns": sequence * 1_000_000_000,
                "target_id": "H",
                "action_index": action_indices[sequence],
                "phase": phases[sequence],
                "phase_endpoint": True,
                "expected_tool_tip_board_mm": [10.0, 20.0, z_values[sequence]],
            }
            for sequence in range(6)
        ]
        request = _sealed(
            {
                "schema": parity.CARTESIAN_REQUEST_SCHEMA,
                "status": "READY_FOR_IK_QUALIFICATION",
                "route_shape_materialized": True,
                "joint_positions_included": False,
                "route_shape_candidate_id": candidate_id,
                "route_shape_candidate": route,
                "samples": samples,
                "hardware_access": False,
                "physical_authority": False,
                "controller_commands": [],
                "hardware_writes": 0,
                "physical_movements": 0,
            },
            "request_sha256",
        )
        scale = 0.1 * candidate_index
        joint_results = []
        for sequence in range(6):
            joint_results.append(
                {
                    "waypoint_sequence": sequence,
                    "solution_arm_joint_positions_rad": {
                        name: scale * sequence if index == 0 else 0.0
                        for index, name in enumerate(parity.ARM_JOINT_ORDER)
                    },
                }
            )
        ik = _sealed(
            {
                "schema": parity.IK_RECEIPT_SCHEMA,
                "status": "READY_FOR_COLLISION_QUALIFICATION",
                "ik_all_samples_accepted": True,
                "route_shape_candidate_id": candidate_id,
                "route_shape_candidate": route,
                "source_request_sha256": request["request_sha256"],
                "joint_results": joint_results,
                "metrics": {
                    "maximum_adjacent_joint_delta_rad": scale,
                    "maximum_position_error_mm": 0.01 * candidate_index,
                    "minimum_normalized_arm_joint_margin": 0.2,
                },
                "hardware_access": False,
                "physical_authority": False,
                "controller_commands": [],
                "hardware_writes": 0,
                "physical_movements": 0,
            },
            "receipt_sha256",
        )
        v5 = _sealed(
            {
                "schema": parity.FIXED_BASE_RECEIPT_SCHEMA,
                "status": "DIAGNOSTIC_OVERLAPS_OBSERVED",
                "source_bindings": {"ik_receipt_sha256": ik["receipt_sha256"]},
                "root_pose_invariant": {"status": "PASS"},
                "hardware_access": False,
                "physical_authority": False,
                "controller_commands": [],
                "hardware_writes": 0,
                "physical_movements": 0,
            },
            "receipt_sha256",
        )
        requests.append(request)
        ik_receipts.append(ik)
        v5_receipts.append(v5)
        retained.append(
            {
                "candidate_id": candidate_id,
                "v5_receipt_sha256": v5["receipt_sha256"],
                "bounded_sample_count": 6,
                "maximum_root_translation_delta_mm": 0.006,
                "maximum_root_orientation_delta_deg": 0.056,
                "physical_solid_blocker_pair_count": 0,
                "planning_envelope_blocker_pair_count": 0,
                "unreviewed_blocker_pair_count": 0,
            }
        )
    fixed = _sealed(
        {
            "schema": parity.FIXED_BASE_RESULT_SCHEMA,
            "status": "FIXED_BASE_REPLAY_COMPLETE_NO_PHYSICAL_SOLID_BLOCKERS",
            "fixed_base_root_invariant_passed_for_all_candidates": True,
            "zero_physical_solid_blockers_for_all_candidates": True,
            "next_action": "COMPARE_KEY_MECHANICS_AND_SELECT_LEARNING_BASELINE",
            "retained_results": retained,
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
        },
        "result_sha256",
    )
    return fixed, v5_receipts, requests, ik_receipts, profile


def test_select_key_mechanics_learning_baseline_is_hash_bound_and_deterministic():
    inputs = _learning_baseline_inputs()

    result = parity.select_key_mechanics_learning_baseline(*inputs)

    assert result["schema"] == parity.LEARNING_BASELINE_SELECTION_SCHEMA
    assert result["selected_candidate_id"] == "candidate-a"
    assert result["key_mechanics_equivalent_across_candidates"] is True
    assert [item["learning_baseline_rank"] for item in result["ranked_candidates"]] == [1, 2]
    assert all(
        action["accepted"]
        for candidate in result["ranked_candidates"]
        for action in candidate["key_mechanics_actions"]
    )
    assert result["next_action"] == (
        "RUN_DRIVE_CONTROLLED_ROBOT_H_KEY_REPLAY_FOR_SELECTED_BASELINE"
    )
    assert result["physical_authority"] is False

    inputs[2][0]["samples"][1]["expected_tool_tip_board_mm"][2] = 21.0
    with pytest.raises(parity.ParityContractError, match="Cartesian request hash mismatch"):
        parity.select_key_mechanics_learning_baseline(*inputs)
