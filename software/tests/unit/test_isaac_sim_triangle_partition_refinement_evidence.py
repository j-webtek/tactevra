from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
EVIDENCE = WORKSPACE / "software/integrations/isaac_sim/evidence"
CANDIDATE = EVIDENCE / "roarm_m3_triangle_partition_link2_20260929.json"
REPLAY = EVIDENCE / "roarm_m3_collision_joint_space_triangle_partition_20260929.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_triangle_partition_receipts_are_canonical_and_zero_authority() -> None:
    for path in (CANDIDATE, REPLAY):
        receipt = _load(path)
        claimed = receipt.pop("receipt_sha256")
        assert canonical_sha256(receipt) == claimed
        assert receipt["hardware_access"] is receipt["physical_authority"] is False
        assert receipt["wire_commands"] == []
        assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_partition_assigns_every_source_triangle_once_and_contains_vertices() -> None:
    receipt = _load(CANDIDATE)
    metrics = receipt["target_metrics"]
    assert metrics["source_triangle_count"] == 9216
    assert metrics["assigned_triangle_count"] == 9216
    assert metrics["unique_assigned_triangle_count"] == 9216
    assert metrics["maximum_vertex_overflow_mm"] == 0.0
    assert receipt["method"]["containment"] == (
        "ALL_VERTICES_OF_EVERY_ASSIGNED_TRIANGLE"
    )


def test_partition_stays_within_body_primitive_budget() -> None:
    receipt = _load(CANDIDATE)
    link2 = next(row for row in receipt["links"] if row["link_name"] == "link2")
    assert receipt["method"]["requested_band_count"] == 16
    assert receipt["summary"]["partition_primitive_count"] == 16
    assert link2["component_count"] == 17
    assert link2["component_count"] <= receipt["method"]["maximum_primitives_per_body"]
    assert receipt["summary"]["candidate_primitive_count"] == 29


def test_partition_replay_removes_nonadjacent_witness_without_false_negatives() -> None:
    baseline = _load(EVIDENCE / "roarm_m3_collision_joint_space_20260929.json")
    replay = _load(REPLAY)
    assert baseline["summary"]["CANDIDATE_FALSE_POSITIVE"] == 192
    assert replay["summary"] == {
        "AGREEMENT_COLLISION": 57,
        "AGREEMENT_FREE": 807,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 165,
        "PAIR_CASES": 1029,
    }
    assert replay["adjacency_scope_summary"]["NONADJACENT"] == {
        "AGREEMENT_COLLISION": 3,
        "AGREEMENT_FREE": 732,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 0,
    }


def test_partition_clears_link2_gripper_pair_but_remains_uninstalled() -> None:
    candidate = _load(CANDIDATE)
    replay = _load(REPLAY)
    pairs = {tuple(row["body_pair"]): row for row in replay["pair_summary"]}
    witness = pairs[("link2", "gripper_link")]
    assert witness["counts"]["CANDIDATE_FALSE_POSITIVE"] == 0
    assert witness["minimum_candidate_box_signed_distance_mm"] == 13.421512
    assert witness["minimum_raw_mesh_signed_distance_mm"] == 13.607432
    assert candidate["candidate_profile_installable"] is False
    assert candidate["collision_query_admissible"] is False
    assert replay["candidate_profile_installable"] is False
    assert replay["collision_query_admissible"] is False
    assert replay["pair_exclusions_admissible"] is False
