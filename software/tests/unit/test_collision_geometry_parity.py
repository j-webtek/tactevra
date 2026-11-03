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
