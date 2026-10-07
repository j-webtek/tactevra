"""Partition long accepted routes without weakening bounded collision sampling.

Each partition retains the existing ``BoundedSegmentSamplingPolicy`` ceiling.
The next partition starts from the exact terminal endpoint of the previous
partition, so the first sample of every successor partition conservatively
rechecks the shared boundary pose.  Source IK endpoints are never duplicated or
omitted.

This module prepares evidence only.  It performs no collision qualification,
creates no controller commands, and grants no physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from rocell.kinematics import ARM_JOINT_NAMES

from .bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
    BoundedSegmentSamplingPolicy,
    build_bounded_joint_sample_plan_from_results,
)


SCHEMA = "rocell.partitioned_bounded_segment_collision.v1"
MAX_PARTITIONED_ENDPOINT_RESULTS = 4096
MAX_BOUNDED_COLLISION_PARTITIONS = 64


class PartitionedBoundedSegmentCollisionError(ValueError):
    """A long route cannot form an exact sequence of bounded partitions."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _joint_map(value: object, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(ARM_JOINT_NAMES):
        raise PartitionedBoundedSegmentCollisionError(
            f"{label} must exactly cover arm joints"
        )
    result: dict[str, float] = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise PartitionedBoundedSegmentCollisionError(
                f"{label} joint {name} is not numeric"
            )
        number = float(raw)
        if not math.isfinite(number):
            raise PartitionedBoundedSegmentCollisionError(
                f"{label} joint {name} is not finite"
            )
        result[name] = number
    return result


@dataclass(frozen=True, slots=True)
class BoundedCollisionPartitionV1:
    """One exact source-result interval and its bounded sample plan."""

    partition_index: int
    source_result_start_index: int
    source_result_end_index_exclusive: int
    start_joint_positions_rad: Mapping[str, float]
    samples: tuple[BoundedJointConfigurationSample, ...]

    @property
    def source_result_count(self) -> int:
        return self.source_result_end_index_exclusive - self.source_result_start_index

    @property
    def content_sha256(self) -> str:
        return _sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "partition_index": self.partition_index,
            "source_result_start_index": self.source_result_start_index,
            "source_result_end_index_exclusive": self.source_result_end_index_exclusive,
            "source_result_count": self.source_result_count,
            "boundary_start_kind": (
                "ROUTE_SEED"
                if self.partition_index == 0
                else "PREVIOUS_PARTITION_TERMINAL_ENDPOINT"
            ),
            "start_joint_positions_rad": {
                name: self.start_joint_positions_rad[name] for name in ARM_JOINT_NAMES
            },
            "sample_count": len(self.samples),
            "sample_plan": [sample.to_dict() for sample in self.samples],
        }


def _bounded_results(value: object) -> tuple[Mapping[str, Any], ...]:
    try:
        iterator = iter(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("joint_results must be a finite sequence") from exc
    items: list[Mapping[str, Any]] = []
    for _ in range(MAX_PARTITIONED_ENDPOINT_RESULTS + 1):
        try:
            item = next(iterator)
        except StopIteration:
            break
        if not isinstance(item, Mapping):
            raise PartitionedBoundedSegmentCollisionError(
                "joint_results must contain objects"
            )
        items.append(item)
    if not items:
        raise PartitionedBoundedSegmentCollisionError(
            "at least one accepted joint result is required"
        )
    if len(items) > MAX_PARTITIONED_ENDPOINT_RESULTS:
        raise PartitionedBoundedSegmentCollisionError(
            "joint result count exceeds partitioned route maximum"
        )
    return tuple(items)


def build_partitioned_bounded_joint_sample_plans_from_results(
    start_joint_positions_rad: Mapping[str, float],
    joint_results: Sequence[Mapping[str, Any]],
    policy: BoundedSegmentSamplingPolicy | None = None,
    *,
    maximum_partitions: int = MAX_BOUNDED_COLLISION_PARTITIONS,
) -> tuple[BoundedCollisionPartitionV1, ...]:
    """Cover a long accepted route with exact, boundary-linked partitions."""

    selected = policy or BoundedSegmentSamplingPolicy()
    if not isinstance(selected, BoundedSegmentSamplingPolicy):
        raise TypeError("policy must be BoundedSegmentSamplingPolicy")
    if (
        isinstance(maximum_partitions, bool)
        or not isinstance(maximum_partitions, int)
        or not 1 <= maximum_partitions <= MAX_BOUNDED_COLLISION_PARTITIONS
    ):
        raise PartitionedBoundedSegmentCollisionError(
            "maximum_partitions must be an integer in [1, 64]"
        )
    route_start = _joint_map(start_joint_positions_rad, "route start state")
    results = _bounded_results(joint_results)
    endpoints: list[dict[str, float]] = []
    for index, result in enumerate(results):
        if result.get("waypoint_sequence") != index or result.get("accepted") is not True:
            raise PartitionedBoundedSegmentCollisionError(
                f"source result {index} is not an accepted canonical endpoint"
            )
        endpoints.append(
            _joint_map(
                result.get("solution_arm_joint_positions_rad"),
                f"source result {index} endpoint",
            )
        )

    partitions: list[BoundedCollisionPartitionV1] = []
    source_index = 0
    partition_start = route_start
    while source_index < len(results):
        if len(partitions) >= maximum_partitions:
            raise PartitionedBoundedSegmentCollisionError(
                "partition count exceeds configured maximum"
            )
        sample_count = 0
        previous = partition_start
        end_index = source_index
        while end_index < len(results):
            endpoint = endpoints[end_index]
            maximum_delta = max(
                abs(endpoint[name] - previous[name]) for name in ARM_JOINT_NAMES
            )
            subdivisions = max(
                1,
                math.ceil(
                    maximum_delta / float(selected.maximum_joint_step_rad)
                ),
            )
            contribution = subdivisions + 1 if end_index == source_index else subdivisions
            if sample_count + contribution > selected.maximum_samples:
                break
            sample_count += contribution
            previous = endpoint
            end_index += 1
        if end_index == source_index:
            raise PartitionedBoundedSegmentCollisionError(
                f"source segment {source_index} cannot fit one bounded partition"
            )

        local_results = []
        for local_index, result in enumerate(results[source_index:end_index]):
            local_results.append({**dict(result), "waypoint_sequence": local_index})
        local_samples = build_bounded_joint_sample_plan_from_results(
            partition_start,
            local_results,
            selected,
        )
        remapped = tuple(
            BoundedJointConfigurationSample(
                sample_sequence=sample.sample_sequence,
                source_segment_index=(
                    source_index + sample.source_segment_index
                ),
                subdivision_index=sample.subdivision_index,
                subdivision_count=sample.subdivision_count,
                interpolation_ratio=sample.interpolation_ratio,
                joint_positions_rad=sample.joint_positions_rad,
            )
            for sample in local_samples
        )
        partitions.append(
            BoundedCollisionPartitionV1(
                partition_index=len(partitions),
                source_result_start_index=source_index,
                source_result_end_index_exclusive=end_index,
                start_joint_positions_rad=partition_start,
                samples=remapped,
            )
        )
        partition_start = endpoints[end_index - 1]
        source_index = end_index

    return tuple(partitions)


__all__ = [
    "SCHEMA",
    "MAX_PARTITIONED_ENDPOINT_RESULTS",
    "MAX_BOUNDED_COLLISION_PARTITIONS",
    "PartitionedBoundedSegmentCollisionError",
    "BoundedCollisionPartitionV1",
    "build_partitioned_bounded_joint_sample_plans_from_results",
]
