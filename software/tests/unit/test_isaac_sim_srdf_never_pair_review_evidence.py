from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
EVIDENCE = WORKSPACE / "software/integrations/isaac_sim/evidence"
REVIEW = EVIDENCE / "roarm_m3_srdf_never_pair_review_20260929.json"


def _load() -> dict:
    return json.loads(REVIEW.read_text(encoding="utf-8"))


def test_never_pair_review_is_canonical_and_source_bound() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    bindings = receipt["source_bindings"]
    assert bindings["policy_review_sha256"] == (
        "c6c1df0b304f7f8b36bd6b8e1015244d1b5e427b24476a85f84b846de5001423"
    )
    assert bindings["replay_summary_sha256"] == (
        "1cad314d6901c0f639c4771f7be79b235eeadf844eba600129d4f8bb45991b87"
    )


def test_all_six_never_pairs_are_free_in_all_finite_cases() -> None:
    receipt = _load()
    summary = receipt["summary"]
    assert summary["never_pair_count"] == 6
    assert summary["never_pair_case_count"] == 294
    assert summary["supported_never_pair_count"] == 6
    assert summary["contradicted_never_pair_count"] == 0
    assert summary["all_never_pair_cases_agreement_free"] is True
    for row in receipt["never_pair_reviews"]:
        assert row["case_count"] == 49
        assert row["counts"] == {
            "AGREEMENT_COLLISION": 0,
            "AGREEMENT_FREE": 49,
            "CANDIDATE_FALSE_NEGATIVE": 0,
            "CANDIDATE_FALSE_POSITIVE": 0,
        }
        assert row["minimum_raw_mesh_signed_distance_mm"] > 0.0
        assert row["minimum_candidate_box_signed_distance_mm"] > 0.0
        assert row["finite_replay_supports_never_reason"] is True


def test_nonexcluded_nonadjacent_collisions_remain_visible() -> None:
    receipt = _load()
    summary = receipt["summary"]
    assert summary["retained_nonexcluded_nonadjacent_collision_pair_count"] == 3
    assert summary["retained_nonexcluded_nonadjacent_collision_case_count"] == 3
    assert {
        tuple(row["body_pair"])
        for row in receipt["retained_nonexcluded_nonadjacent_collisions"]
    } == {
        ("gripper_link", "link1"),
        ("link2", "link4"),
        ("link2", "link5"),
    }


def test_never_support_is_explicitly_finite_not_continuous() -> None:
    receipt = _load()
    assert receipt["method"]["scope"] == "COMMITTED_49_POSE_PAIR_SUMMARY"
    assert receipt["method"]["continuous_workspace_claimed"] is False
    assert "FINITE_CORPUS_DOES_NOT_PROVE_NEVER_COLLISION" in receipt["blockers"]


def test_never_review_does_not_install_or_admit_exclusions() -> None:
    receipt = _load()
    assert receipt["never_exclusions_installable"] is False
    assert receipt["pair_exclusions_admissible"] is False
    assert receipt["collision_query_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0
