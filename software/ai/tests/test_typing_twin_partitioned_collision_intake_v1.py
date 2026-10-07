from __future__ import annotations

import json
from pathlib import Path

from rocell_ai.typing_twin_partitioned_collision_intake_v1 import (
    run_partitioned_collision_intake,
)


WORKSPACE = Path(__file__).resolve().parents[3]
FIXTURE = WORKSPACE / (
    "software/ai/sim/evidence/"
    "typing_twin_partitioned_collision_intake_fixture_v1.json"
)


def test_frozen_partitioned_collision_intake_is_deterministic_and_zero_authority():
    first = run_partitioned_collision_intake(FIXTURE, workspace=WORKSPACE)
    second = run_partitioned_collision_intake(FIXTURE, workspace=WORKSPACE)

    assert first == second
    assert first["decision"] == (
        "PASS_PARTITIONED_INTAKE_RETAIN_PROFILE_AND_COLLISION_BLOCKERS"
    )
    intake = first["partitioned_collision_intake"]
    assert [item["bounded_sample_count"] for item in intake["partitions"]] == [
        256,
        74,
    ]
    assert intake["required_evidence_slots"]["route_segment_count"] == 328
    assert (
        intake["required_evidence_slots"][
            "partition_owned_adjacent_sample_segment_count"
        ]
        == 328
    )
    assert intake["boundary_lineage"][0]["maximum_joint_difference_rad"] == 0.0
    assert first["installed_collision_profile_supplied"] is False
    assert first["installed_geometry_collision_screening_executed"] is False
    assert first["continuous_collision_proven"] is False
    assert first["installed_collision_gate_cleared"] is False
    assert first["controller_commands"] == []
    assert first["hardware_writes"] == first["physical_movements"] == 0
    json.dumps(first, sort_keys=True, allow_nan=False)
