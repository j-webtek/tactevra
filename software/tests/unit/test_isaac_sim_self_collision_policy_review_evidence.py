from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
EVIDENCE = WORKSPACE / "software/integrations/isaac_sim/evidence"
REVIEW = EVIDENCE / "roarm_m3_self_collision_policy_review_20260929.json"


def _load() -> dict:
    return json.loads(REVIEW.read_text(encoding="utf-8"))


def test_policy_review_is_canonical_and_bound_to_pinned_sources() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    bindings = receipt["source_bindings"]
    assert bindings["upstream_commit"] == "40dbd84b553695212fab713e8465f817ba95454d"
    assert bindings["upstream_srdf_sha256"] == (
        "29f1daaeea91a490b85581a9a62dd07be9ab959d7817fad89836c466e8288499"
    )
    assert bindings["replay_summary_sha256"] == (
        "1cad314d6901c0f639c4771f7be79b235eeadf844eba600129d4f8bb45991b87"
    )


def test_srdf_adjacent_pairs_exactly_match_governed_direct_joints() -> None:
    receipt = _load()
    summary = receipt["summary"]
    assert summary["srdf_exclusion_count"] == 12
    assert summary["srdf_adjacent_exclusion_count"] == 6
    assert summary["srdf_never_exclusion_count"] == 6
    assert summary["governed_direct_joint_pair_count"] == 6
    adjacent = {
        tuple(row["body_pair"])
        for row in receipt["srdf_exclusions"]
        if row["reason"] == "Adjacent"
    }
    assert adjacent == {
        ("base_link", "link1"),
        ("gripper_link", "link5"),
        ("link1", "link2"),
        ("link2", "link3"),
        ("link3", "link4"),
        ("link4", "link5"),
    }


def test_every_remaining_false_positive_has_explicit_adjacent_support() -> None:
    receipt = _load()
    summary = receipt["summary"]
    assert summary["false_positive_case_count"] == 165
    assert summary["false_positive_pair_count"] == 4
    assert summary["unsupported_false_positive_pair_count"] == 0
    assert all(
        row["governed_direct_joint_pair"]
        and row["srdf_reason"] == "Adjacent"
        and row["supported_by_adjacent_policy_evidence"]
        for row in receipt["false_positive_pair_review"]
    )


def test_adjacent_only_counterfactual_retains_clean_nonadjacent_cases() -> None:
    receipt = _load()
    counterfactual = receipt["adjacent_only_counterfactual"]
    assert counterfactual["excluded_pair_count"] == 6
    assert counterfactual["excluded_case_count"] == 294
    assert counterfactual["retained_case_count"] == 735
    assert counterfactual["retained_counts"] == {
        "AGREEMENT_COLLISION": 3,
        "AGREEMENT_FREE": 732,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 0,
    }
    assert counterfactual["excluded_counts"]["AGREEMENT_COLLISION"] == 54
    assert counterfactual["excluded_counts"]["CANDIDATE_FALSE_POSITIVE"] == 165


def test_review_does_not_install_or_admit_collision_policy() -> None:
    receipt = _load()
    assert receipt["exclusion_profile_installable"] is False
    assert receipt["pair_exclusions_admissible"] is False
    assert receipt["collision_query_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0
