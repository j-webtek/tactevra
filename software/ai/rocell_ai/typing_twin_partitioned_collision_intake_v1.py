"""Exercise the partition-aware collision intake on the frozen full route."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.context import load_simulation_context
from rocell.application.partitioned_typing_collision_intake_v1 import (
    PROFILE_REQUIRED_STATUS,
    prepare_partitioned_typing_collision_intake_v1,
)


SCHEMA = "tactevra.typing_twin_partitioned_collision_intake_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_partitioned_collision_intake_fixture.v1"
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
        raise ValueError("partitioned collision intake fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected partitioned collision intake fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def run_partitioned_collision_intake(
    fixture_path: Path, *, workspace: Path
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    source = json.loads(
        (workspace / fixture["source_result"]["path"]).read_text(encoding="utf-8")
    )
    if source.get("receipt_sha256") != fixture["source_result"]["receipt_sha256"]:
        raise ValueError("source full-route receipt differs")
    ik = source["ik_screen"]
    context = load_simulation_context(
        workspace, workspace / fixture["system_manifest"]["path"]
    )
    policy = BoundedSegmentSamplingPolicy(**fixture["sampling_policy"])
    intake = prepare_partitioned_typing_collision_intake_v1(
        ik,
        context,
        expected_execution_plan_sha256=ik["typing_execution_plan_sha256"],
        expected_trajectory_plan_sha256=ik["typing_trajectory_plan_sha256"],
        expected_calibration_snapshot_sha256=ik["calibration_snapshot_sha256"],
        sampling_policy=policy,
        maximum_partitions=fixture["resource_limits"]["maximum_partitions"],
    )
    expected = fixture["expected_result"]
    slots = intake["required_evidence_slots"]
    partition_shapes = [
        {
            "source_result_start_index": item["source_result_start_index"],
            "source_result_end_index_exclusive": item[
                "source_result_end_index_exclusive"
            ],
            "bounded_sample_count": item["bounded_sample_count"],
        }
        for item in intake["partitions"]
    ]
    if (
        intake["status"] != PROFILE_REQUIRED_STATUS
        or partition_shapes != expected["partition_shapes"]
        or slots["route_segment_count"] != expected["route_segment_count"]
        or slots["partition_owned_adjacent_sample_segment_count"]
        != expected["route_segment_count"]
        or len(intake["boundary_lineage"])
        != expected["boundary_lineage_count"]
        or any(
            item["maximum_joint_difference_rad"] != 0.0
            for item in intake["boundary_lineage"]
        )
    ):
        raise ValueError("partitioned intake differs from frozen decision rules")

    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "source_result_receipt_sha256": source["receipt_sha256"],
        "partitioned_collision_intake": intake,
        "partitioned_collision_intake_sha256": intake[
            "partitioned_typing_collision_intake_sha256"
        ],
        "installed_collision_profile_supplied": False,
        "installed_geometry_collision_screening_executed": False,
        "continuous_collision_proven": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "decision": "PASS_PARTITIONED_INTAKE_RETAIN_PROFILE_AND_COLLISION_BLOCKERS",
        "limitations": fixture["limitations"],
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_partitioned_collision_intake(
        args.fixture, workspace=args.workspace.resolve()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "partitioned_collision_intake_sha256": result[
                    "partitioned_collision_intake_sha256"
                ],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
