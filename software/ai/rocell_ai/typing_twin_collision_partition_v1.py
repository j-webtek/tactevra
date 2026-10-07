"""Freeze and audit exact bounded-collision partitions for a long typing route."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.partitioned_bounded_segment_collision_v1 import (
    build_partitioned_bounded_joint_sample_plans_from_results,
)
from rocell.kinematics import ARM_JOINT_NAMES


SCHEMA = "tactevra.typing_twin_collision_partition_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_collision_partition_fixture.v1"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("collision partition fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected collision partition fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def _maximum_joint_difference(
    left: dict[str, float], right: dict[str, float]
) -> float:
    return max(abs(float(left[name]) - float(right[name])) for name in ARM_JOINT_NAMES)


def run_collision_partition_study(
    fixture_path: Path, *, workspace: Path
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    source = json.loads(
        (workspace / fixture["source_result"]["path"]).read_text(encoding="utf-8")
    )
    if (
        source.get("receipt_sha256")
        != fixture["source_result"]["receipt_sha256"]
        or source.get("decision")
        != "PASS_IK_CONTINUITY_RETAIN_INSTALLED_COLLISION_BLOCKER"
        or source.get("canonical_ik_route_accepted") is not True
        or source.get("canonical_joint_continuity_accepted") is not True
    ):
        raise ValueError("source full-route result is not the admitted result")
    ik = source["ik_screen"]
    results = ik["joint_results"]
    seed = ik["seed"]
    policy_document = fixture["sampling_policy"]
    policy = BoundedSegmentSamplingPolicy(
        maximum_joint_step_rad=policy_document["maximum_joint_step_rad"],
        maximum_samples=policy_document["maximum_samples"],
    )
    partitions = build_partitioned_bounded_joint_sample_plans_from_results(
        seed["joint_positions_rad"],
        results,
        policy,
        maximum_partitions=fixture["resource_limits"]["maximum_partitions"],
    )

    expected = fixture["expected_partition_shape"]
    result_counts = [partition.source_result_count for partition in partitions]
    sample_counts = [len(partition.samples) for partition in partitions]
    ranges = [
        [
            partition.source_result_start_index,
            partition.source_result_end_index_exclusive,
        ]
        for partition in partitions
    ]
    if (
        result_counts != expected["source_result_counts"]
        or sample_counts != expected["sample_counts"]
        or ranges != expected["source_result_ranges"]
    ):
        raise ValueError("partition shape differs from the frozen expectation")
    covered = [
        index
        for partition in partitions
        for index in range(
            partition.source_result_start_index,
            partition.source_result_end_index_exclusive,
        )
    ]
    if covered != list(range(len(results))):
        raise ValueError("source result coverage is not exact and ordered")

    boundary_checks: list[dict[str, Any]] = []
    for previous, successor in zip(partitions, partitions[1:], strict=False):
        prior_terminal = previous.samples[-1].joint_positions_rad
        successor_start = successor.start_joint_positions_rad
        successor_recheck = successor.samples[0].joint_positions_rad
        start_difference = _maximum_joint_difference(
            dict(prior_terminal), dict(successor_start)
        )
        recheck_difference = _maximum_joint_difference(
            dict(successor_start), dict(successor_recheck)
        )
        if start_difference != 0.0 or recheck_difference != 0.0:
            raise ValueError("partition boundary state is not exact")
        boundary_checks.append(
            {
                "left_partition_index": previous.partition_index,
                "right_partition_index": successor.partition_index,
                "source_boundary_result_index": (
                    successor.source_result_start_index - 1
                ),
                "terminal_to_successor_start_maximum_difference_rad": (
                    start_difference
                ),
                "successor_start_to_recheck_maximum_difference_rad": (
                    recheck_difference
                ),
                "successor_boundary_sample_sha256": (
                    successor.samples[0].content_sha256
                ),
            }
        )

    summaries = [
        {
            "partition_index": partition.partition_index,
            "source_result_start_index": partition.source_result_start_index,
            "source_result_end_index_exclusive": (
                partition.source_result_end_index_exclusive
            ),
            "source_result_count": partition.source_result_count,
            "sample_count": len(partition.samples),
            "first_sample_sha256": partition.samples[0].content_sha256,
            "terminal_sample_sha256": partition.samples[-1].content_sha256,
            "partition_sha256": partition.content_sha256,
        }
        for partition in partitions
    ]
    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "source_result_receipt_sha256": source["receipt_sha256"],
        "source_ik_screen_sha256": ik["typing_trajectory_ik_screen_sha256"],
        "sampling_policy": {
            **policy.to_dict(),
            "sampling_policy_sha256": policy.content_sha256,
        },
        "source_result_count": len(results),
        "source_result_coverage_count": len(covered),
        "source_result_coverage_sha256": _sha(covered),
        "partition_count": len(partitions),
        "partition_summaries": summaries,
        "partition_plan_sha256": _sha(
            [partition.content_sha256 for partition in partitions]
        ),
        "total_partition_sample_count": sum(sample_counts),
        "conservative_boundary_recheck_count": len(boundary_checks),
        "boundary_checks": boundary_checks,
        "source_endpoint_duplicated_count": 0,
        "source_endpoint_omitted_count": 0,
        "installed_collision_intake_status": source[
            "installed_collision_intake"
        ]["status"],
        "installed_collision_blockers": source["installed_collision_intake"][
            "blockers"
        ],
        "installed_geometry_collision_screening_executed": False,
        "continuous_collision_proven": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "decision": "PASS_EXACT_PARTITION_COVERAGE_RETAIN_COLLISION_BLOCKERS",
        "limitations": fixture["limitations"],
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_collision_partition_study(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "partition_count": result["partition_count"],
                "source_result_count": result["source_result_count"],
                "total_partition_sample_count": result[
                    "total_partition_sample_count"
                ],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
