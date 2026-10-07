from __future__ import annotations

import copy
from pathlib import Path

import pytest

from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.context import load_simulation_context
from rocell.application.partitioned_typing_collision_intake_v1 import (
    PROFILE_REQUIRED_STATUS,
    READY_STATUS,
    PartitionedTypingCollisionIntakeV1Error,
    prepare_partitioned_typing_collision_intake_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    screen_typing_trajectory_ik_v1,
)

from test_typing_trajectory_ik_screen_v1 import (
    _installed_profile,
    _seed,
    _snapshot,
    _trajectory,
)


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def _inputs(sim_context):
    snapshot = _snapshot(sim_context)
    execution, trajectory = _trajectory(sim_context, snapshot)
    ik = screen_typing_trajectory_ik_v1(
        execution,
        trajectory,
        sim_context,
        snapshot,
        _seed(sim_context, snapshot),
    )
    return snapshot, execution, trajectory, ik


def test_partitioned_intake_binds_profile_and_owns_every_route_segment(sim_context):
    snapshot, execution, trajectory, ik = _inputs(sim_context)
    profile = _installed_profile(sim_context)

    report = prepare_partitioned_typing_collision_intake_v1(
        ik,
        sim_context,
        expected_execution_plan_sha256=execution.plan_sha256,
        expected_trajectory_plan_sha256=trajectory.trajectory_plan_sha256,
        expected_calibration_snapshot_sha256=snapshot.snapshot_sha256,
        installed_profile=profile,
        sampling_policy=BoundedSegmentSamplingPolicy(
            maximum_joint_step_rad=0.25,
            maximum_samples=4,
        ),
    )

    assert report["status"] == READY_STATUS
    assert len(report["partitions"]) > 1
    assert all(
        item["installed_collision_profile_sha256"] == profile.content_sha256
        for item in report["partitions"]
    )
    slots = report["required_evidence_slots"]
    assert slots["route_segment_count"] == len(ik["joint_results"])
    assert slots["partition_owned_adjacent_sample_segment_count"] == len(
        ik["joint_results"]
    )
    assert slots["conservative_boundary_recheck_count"] == (
        len(report["partitions"]) - 1
    )
    assert all(
        item["maximum_joint_difference_rad"] == 0.0
        and item["boundary_recheck_required"] is True
        and item["extra_zero_length_sweep_envelope_required"] is False
        for item in report["boundary_lineage"]
    )
    assert report["installed_geometry_collision_screening_executed"] is False
    assert report["continuous_collision_proven"] is False
    assert report["installed_collision_gate_cleared"] is False
    assert report["controller_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_partitioned_intake_retains_missing_profile_blocker(sim_context):
    snapshot, execution, trajectory, ik = _inputs(sim_context)

    report = prepare_partitioned_typing_collision_intake_v1(
        ik,
        sim_context,
        expected_execution_plan_sha256=execution.plan_sha256,
        expected_trajectory_plan_sha256=trajectory.trajectory_plan_sha256,
        expected_calibration_snapshot_sha256=snapshot.snapshot_sha256,
    )

    assert report["status"] == PROFILE_REQUIRED_STATUS
    assert report["installed_collision_profile_sha256"] is None
    assert report["blockers"] == [
        "INSTALLED_COLLISION_PROFILE_REQUIRED",
        "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
    ]


def test_partitioned_intake_rejects_crossed_lineage_and_mutated_ik(sim_context):
    snapshot, execution, trajectory, ik = _inputs(sim_context)
    kwargs = {
        "expected_execution_plan_sha256": execution.plan_sha256,
        "expected_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "expected_calibration_snapshot_sha256": snapshot.snapshot_sha256,
    }

    with pytest.raises(
        PartitionedTypingCollisionIntakeV1Error, match="lineage differs"
    ):
        prepare_partitioned_typing_collision_intake_v1(
            ik,
            sim_context,
            **{**kwargs, "expected_execution_plan_sha256": "f" * 64},
        )

    changed = copy.deepcopy(ik)
    changed["sample_count"] += 1
    with pytest.raises(PartitionedTypingCollisionIntakeV1Error, match="hash"):
        prepare_partitioned_typing_collision_intake_v1(
            changed, sim_context, **kwargs
        )
