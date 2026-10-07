from __future__ import annotations

import itertools

import pytest

from rocell.application.partitioned_bounded_segment_collision_v1 import (
    PartitionedBoundedSegmentCollisionError,
    build_partitioned_bounded_joint_sample_plans_from_results,
)
from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.kinematics import ARM_JOINT_NAMES


def _joints(value: float) -> dict[str, float]:
    return {name: value if index == 0 else 0.0 for index, name in enumerate(ARM_JOINT_NAMES)}


def _results(count: int, *, step: float = 0.001) -> list[dict[str, object]]:
    return [
        {
            "waypoint_sequence": index,
            "accepted": True,
            "solution_arm_joint_positions_rad": _joints((index + 1) * step),
        }
        for index in range(count)
    ]


def test_long_route_is_exactly_covered_with_one_conservative_boundary_recheck() -> None:
    source = _results(328)
    partitions = build_partitioned_bounded_joint_sample_plans_from_results(
        _joints(0.0), source
    )

    assert len(partitions) == 2
    assert [item.source_result_count for item in partitions] == [255, 73]
    assert [len(item.samples) for item in partitions] == [256, 74]
    assert [
        (item.source_result_start_index, item.source_result_end_index_exclusive)
        for item in partitions
    ] == [(0, 255), (255, 328)]
    assert partitions[1].start_joint_positions_rad == source[254][
        "solution_arm_joint_positions_rad"
    ]
    assert partitions[1].samples[0].joint_positions_rad == partitions[
        1
    ].start_joint_positions_rad
    assert partitions[1].samples[0].source_segment_index == 255
    assert partitions[1].samples[0].subdivision_index == 0
    assert partitions[0].samples[-1].joint_positions_rad == partitions[
        1
    ].samples[0].joint_positions_rad
    assert partitions == build_partitioned_bounded_joint_sample_plans_from_results(
        _joints(0.0), source
    )


def test_partitioning_rejects_reordered_or_unaccepted_source_results() -> None:
    reordered = _results(3)
    reordered[1]["waypoint_sequence"] = 2
    with pytest.raises(
        PartitionedBoundedSegmentCollisionError,
        match="source result 1 is not an accepted canonical endpoint",
    ):
        build_partitioned_bounded_joint_sample_plans_from_results(
            _joints(0.0), reordered
        )

    rejected = _results(3)
    rejected[1]["accepted"] = False
    with pytest.raises(
        PartitionedBoundedSegmentCollisionError,
        match="source result 1 is not an accepted canonical endpoint",
    ):
        build_partitioned_bounded_joint_sample_plans_from_results(
            _joints(0.0), rejected
        )


def test_partitioning_rejects_a_segment_larger_than_one_partition() -> None:
    with pytest.raises(
        PartitionedBoundedSegmentCollisionError,
        match="source segment 0 cannot fit one bounded partition",
    ):
        build_partitioned_bounded_joint_sample_plans_from_results(
            _joints(0.0),
            _results(1, step=0.2),
            BoundedSegmentSamplingPolicy(
                maximum_joint_step_rad=0.05,
                maximum_samples=2,
            ),
        )


def test_partitioning_is_bounded_against_unending_input() -> None:
    result = _results(1)[0]
    with pytest.raises(
        PartitionedBoundedSegmentCollisionError,
        match="joint result count exceeds partitioned route maximum",
    ):
        build_partitioned_bounded_joint_sample_plans_from_results(
            _joints(0.0), itertools.repeat(result)  # type: ignore[arg-type]
        )
