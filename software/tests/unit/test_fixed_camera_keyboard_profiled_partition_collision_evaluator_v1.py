from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

import rocell.application.fixed_camera_keyboard_profiled_partition_collision_evaluator_v1 as subject
from rocell.application.bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
)
from rocell.application.fixed_camera_keyboard_profiled_collision_evidence_admission_v1 import (
    AdmittedProfileCollisionEvidenceV1,
)
from rocell.application.context import load_simulation_context
from rocell.application.partitioned_typing_collision_intake_v1 import (
    READY_STATUS,
    SCHEMA as PARTITION_SCHEMA,
)
from rocell.kinematics import ARM_JOINT_NAMES

from test_fk_collision_pose_adapter import profile, snapshot


PROFILES = ("no_attachment", "stylus_attachment")
WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def simulation_context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _fixtures(simulation_context):
    measured = snapshot(simulation_context)
    base = profile(simulation_context)
    installed = {
        "no_attachment": replace(base, profile_id="profile:no-attachment"),
        "stylus_attachment": replace(base, profile_id="profile:stylus-attachment"),
    }
    documents = {}
    admitted = {}
    for profile_name in PROFILES:
        joints = {
            name: simulation_context.scenario.ready_arm_joint_positions_rad[name].value
            for name in ARM_JOINT_NAMES
        }
        samples = (
            BoundedJointConfigurationSample(0, 0, 0, 1, 0.0, joints),
            BoundedJointConfigurationSample(1, 0, 1, 1, 1.0, joints),
        )
        partition_core = {
            "partition_index": 0,
            "partition_sha256": "1" * 64,
            "source_result_start_index": 0,
            "source_result_end_index_exclusive": 1,
            "source_result_count": 1,
            "installed_collision_profile_sha256": installed[
                profile_name
            ].content_sha256,
            "collision_contract_sha256": installed[profile_name].contract.content_hash,
            "first_sample_sha256": samples[0].content_sha256,
            "terminal_sample_sha256": samples[-1].content_sha256,
            "bounded_sample_count": 2,
            "bounded_joint_sample_plan": [item.to_dict() for item in samples],
            "required_evidence_slots": {
                "configuration_sample_count": 2,
                "configuration_body_count_per_sample": 0,
                "configuration_geometry_binding_count": 0,
                "adjacent_sample_segment_count": 1,
                "configuration_sweep_envelope_count": 0,
            },
        }
        partition = {
            **partition_core,
            "partition_intake_sha256": _sha(partition_core),
        }
        document_core = {
            "schema": PARTITION_SCHEMA,
            "status": READY_STATUS,
            "typing_execution_plan_sha256": "2" * 64,
            "typing_trajectory_plan_sha256": "3" * 64,
            "typing_trajectory_ik_screen_sha256": "4" * 64,
            "calibration_snapshot_sha256": measured.snapshot_sha256,
            "build_snapshot_sha256": simulation_context.snapshot.snapshot_hash,
            "kinematic_model_sha256": simulation_context.scenario.model_sha256,
            "start_state_source_kind": "SYNTHETIC_OFFLINE",
            "start_state_execution_eligible": False,
            "installed_collision_profile_sha256": installed[
                profile_name
            ].content_sha256,
            "collision_contract_sha256": installed[profile_name].contract.content_hash,
            "accepted_profile_source_sha256_values": ["4" * 64],
            "sampling_policy": {
                "maximum_joint_step_rad": 0.05,
                "maximum_samples": 256,
                "sampling_policy_sha256": "5" * 64,
            },
            "partitions": [partition],
            "boundary_lineage": [],
            "required_evidence_slots": {},
            "blockers": [],
            "next_required_stage": "SUPPLY_PARTITIONED_PROFILE_BOUND_COLLISION_EVIDENCE",
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }
        documents[profile_name] = {
            **document_core,
            "partitioned_typing_collision_intake_sha256": _sha(document_core),
        }
        admitted[profile_name] = AdmittedProfileCollisionEvidenceV1(
            profile_name,
            (),
            (({}, {}),),
            (({},),),
            "6" * 64,
            "7" * 64,
        )
    return measured, installed, documents, admitted


def _discrete(status: str) -> dict:
    return {
        "status": status,
        "collision_sequence": {
            "all_waypoints_collision_free_at_supplied_samples": status.startswith(
                "DISCRETE_WAYPOINTS_CLEAR"
            ),
            "sample_count": 2,
            "pose_reports": [{}, {}],
        },
    }


def test_evaluates_both_profiles_and_all_partitions_clear(
    simulation_context, monkeypatch
) -> None:
    measured, installed, documents, admitted = _fixtures(simulation_context)
    calls = []
    monkeypatch.setattr(
        subject,
        "_evaluate_discrete_partition",
        lambda *args: _discrete("DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED"),
    )

    def sweep(*args):
        calls.append(args)
        return {"status": "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"}

    monkeypatch.setattr(
        subject, "evaluate_conservative_segment_sweeps_from_plan", sweep
    )
    result = subject.evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
        simulation_context, measured, documents, admitted, installed
    )

    assert result["status"] == subject.STATUS_CLEAR
    assert result["all_profiled_partitions_clear"] is True
    assert set(result["profiles"]) == set(PROFILES)
    assert len(calls) == 2
    assert result["authority"] == subject.ZERO_AUTHORITY


def test_collision_stops_before_sweep_and_wins_aggregate(
    simulation_context, monkeypatch
) -> None:
    measured, installed, documents, admitted = _fixtures(simulation_context)
    monkeypatch.setattr(
        subject,
        "_evaluate_discrete_partition",
        lambda *args: _discrete("BLOCKED_COLLISION_DETECTED"),
    )
    monkeypatch.setattr(
        subject,
        "evaluate_conservative_segment_sweeps_from_plan",
        lambda *args: pytest.fail("sweep must not run after a discrete collision"),
    )

    result = subject.evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
        simulation_context, measured, documents, admitted, installed
    )

    assert result["status"] == subject.STATUS_COLLISION
    assert all(
        row["partitions"][0]["conservative_sweep_qualification"] is None
        for row in result["profiles"].values()
    )


def test_incomplete_discrete_evidence_remains_distinct(
    simulation_context, monkeypatch
) -> None:
    measured, installed, documents, admitted = _fixtures(simulation_context)
    monkeypatch.setattr(
        subject,
        "_evaluate_discrete_partition",
        lambda *args: _discrete("BLOCKED_INCOMPLETE_EVIDENCE"),
    )
    result = subject.evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
        simulation_context, measured, documents, admitted, installed
    )
    assert result["status"] == subject.STATUS_INCOMPLETE
    assert result["blockers"] == ["PROFILE_BOUND_COLLISION_EVIDENCE_INCOMPLETE"]


def test_conservative_sweep_collision_is_preserved(
    simulation_context, monkeypatch
) -> None:
    measured, installed, documents, admitted = _fixtures(simulation_context)
    monkeypatch.setattr(
        subject,
        "_evaluate_discrete_partition",
        lambda *args: _discrete("DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED"),
    )
    monkeypatch.setattr(
        subject,
        "evaluate_conservative_segment_sweeps_from_plan",
        lambda *args: {"status": "BLOCKED_CONSERVATIVE_SWEEP_COLLISION"},
    )
    result = subject.evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
        simulation_context, measured, documents, admitted, installed
    )
    assert result["status"] == subject.STATUS_COLLISION
    assert all(
        row["partitions"][0]["collision_detected"]
        for row in result["profiles"].values()
    )


def test_rejects_crossed_profile_lineage(simulation_context, monkeypatch) -> None:
    measured, installed, documents, admitted = _fixtures(simulation_context)
    admitted["stylus_attachment"] = admitted["no_attachment"]
    monkeypatch.setattr(
        subject,
        "_evaluate_discrete_partition",
        lambda *args: _discrete("BLOCKED_COLLISION_DETECTED"),
    )
    with pytest.raises(
        subject.FixedCameraKeyboardProfiledPartitionCollisionEvaluatorV1Error,
        match="lineage differs",
    ):
        subject.evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
            simulation_context, measured, documents, admitted, installed
        )


def test_accepts_distinct_boundary_sample_hashes_when_joint_recheck_is_exact(
    simulation_context, monkeypatch
) -> None:
    measured, installed, documents, admitted = _fixtures(simulation_context)
    for profile_name in PROFILES:
        document = documents[profile_name]
        first = document["partitions"][0]
        joints = first["bounded_joint_sample_plan"][-1]["joint_positions_rad"]
        successor_samples = (
            BoundedJointConfigurationSample(0, 1, 0, 1, 0.0, joints),
            BoundedJointConfigurationSample(1, 1, 1, 1, 1.0, joints),
        )
        successor_core = {
            **{
                key: value
                for key, value in first.items()
                if key != "partition_intake_sha256"
            },
            "partition_index": 1,
            "source_result_start_index": 1,
            "source_result_end_index_exclusive": 2,
            "first_sample_sha256": successor_samples[0].content_sha256,
            "terminal_sample_sha256": successor_samples[-1].content_sha256,
            "bounded_joint_sample_plan": [item.to_dict() for item in successor_samples],
        }
        successor = {
            **successor_core,
            "partition_intake_sha256": _sha(successor_core),
        }
        boundary_core = {
            "predecessor_partition_index": 0,
            "successor_partition_index": 1,
            "source_boundary_result_index": 0,
            "predecessor_terminal_sample_sha256": first["terminal_sample_sha256"],
            "successor_boundary_recheck_sample_sha256": successor[
                "first_sample_sha256"
            ],
            "maximum_joint_difference_rad": 0.0,
            "boundary_recheck_required": True,
            "extra_zero_length_sweep_envelope_required": False,
            "first_successor_route_segment_owned_by_partition": 1,
        }
        core = dict(document)
        core.pop("partitioned_typing_collision_intake_sha256")
        core["partitions"] = [first, successor]
        core["boundary_lineage"] = [
            {**boundary_core, "boundary_lineage_sha256": _sha(boundary_core)}
        ]
        documents[profile_name] = {
            **core,
            "partitioned_typing_collision_intake_sha256": _sha(core),
        }
        admitted[profile_name] = replace(
            admitted[profile_name],
            configuration_geometry_by_partition=(({}, {}), ({}, {})),
            sweep_envelopes_by_partition=(({},), ({},)),
        )

    monkeypatch.setattr(
        subject,
        "_evaluate_discrete_partition",
        lambda *args: _discrete("DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED"),
    )
    monkeypatch.setattr(
        subject,
        "evaluate_conservative_segment_sweeps_from_plan",
        lambda *args: {
            "status": "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"
        },
    )
    result = subject.evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
        simulation_context, measured, documents, admitted, installed
    )
    assert result["status"] == subject.STATUS_CLEAR
    assert all(item["partition_count"] == 2 for item in result["profiles"].values())
