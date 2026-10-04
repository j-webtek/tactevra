from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_collision_joint_space_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_joint_space_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "OFFLINE_GOVERNED_LIMIT_COLLISION_DIFFERENTIAL_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_joint_space_corpus_is_deterministic_and_governed() -> None:
    receipt = _load()
    assert receipt["pose_count"] == 49
    assert receipt["method"]["halton_bases"] == [2, 3, 5, 7, 11, 13]
    assert receipt["method"]["halton_sample_count"] == 32
    assert len(receipt["method"]["joint_limits"]) == 6
    assert receipt["source_bindings"]["governed_urdf_sha256"] == (
        "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
    )
    assert receipt["source_bindings"]["detailed_receipt_file_sha256"] == (
        "f1226994510a3489820494021445ba50f4b17bbafaacb5605114b77ef8988f50"
    )


def test_joint_space_summary_has_no_false_negatives() -> None:
    assert _load()["summary"] == {
        "AGREEMENT_COLLISION": 57,
        "AGREEMENT_FREE": 780,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 192,
        "PAIR_CASES": 1029,
    }


def test_joint_space_separates_adjacent_and_nonadjacent_results() -> None:
    scopes = _load()["adjacency_scope_summary"]
    assert scopes["ADJACENT"] == {
        "AGREEMENT_COLLISION": 54,
        "AGREEMENT_FREE": 49,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 191,
    }
    assert scopes["NONADJACENT"] == {
        "AGREEMENT_COLLISION": 3,
        "AGREEMENT_FREE": 731,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 1,
    }
    pairs = {tuple(row["body_pair"]): row for row in _load()["pair_summary"]}
    assert pairs[("link2", "gripper_link")]["counts"]["CANDIDATE_FALSE_POSITIVE"] == 1
    assert pairs[("link2", "gripper_link")]["kinematically_adjacent"] is False


def test_joint_space_result_does_not_select_exclusions_or_admit_queries() -> None:
    receipt = _load()
    assert receipt["candidate_profile_installable"] is False
    assert receipt["collision_query_admissible"] is False
    assert receipt["pair_exclusions_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert {
        "NONADJACENT_FALSE_POSITIVE_OBSERVED",
        "FINITE_CORPUS_IS_NOT_CONTINUOUS_WORKSPACE_COVERAGE",
        "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
    } <= set(receipt["blockers"])
