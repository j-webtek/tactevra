from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
EVIDENCE = WORKSPACE / "software/integrations/isaac_sim/evidence"
REPLAY = EVIDENCE / "roarm_m3_collision_policy_stress_replay_20260929.json"
ASSESSMENT = EVIDENCE / "roarm_m3_collision_policy_stress_assessment_20260929.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_stress_replay_is_canonical_held_out_and_zero_authority() -> None:
    receipt = _load(REPLAY)
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed == (
        "199a8f77e6cdbc00154ae0f01aca490b4a074c56b6b28dcf0ace641390b8ffe8"
    )
    method = receipt["method"]
    assert method["halton_start_index"] == 1001
    assert method["halton_sample_count"] == 256
    assert method["anchors_included"] is False
    assert method["pose_families"] == ["HALTON_INTERIOR"]
    assert receipt["pose_results"][0]["pose_name"] == "halton_1001"
    assert receipt["pose_results"][-1]["pose_name"] == "halton_1256"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_stress_replay_preserves_full_differential_counts() -> None:
    assert _load(REPLAY)["summary"] == {
        "AGREEMENT_COLLISION": 334,
        "AGREEMENT_FREE": 4147,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 895,
        "PAIR_CASES": 5376,
    }


def test_assessment_binds_exact_candidate_geometry_and_replay() -> None:
    receipt = _load(ASSESSMENT)
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed == (
        "8b2662fb183022d93600d4dd72be815e2b0f3a0b0d77722bcd52f478e411bc9a"
    )
    assert receipt["source_bindings"] == {
        "base_contract_sha256": "d3238c0c95a1d2e7ff74fcb8dccc3eb0aadb0f897b2ea041319bbcd6442af5c3",
        "candidate_content_sha256": "651adee0ee18c4d11233e3ed37389a4811236e08b54c0f91a32fd6dfa436e75a",
        "candidate_file_sha256": "88e31c4b525ded8ca48d4bae7cf70faff396e2d9f92249296f2b2f3a9c1d3c3f",
        "geometry_candidate_sha256": "0568f7ba269cf190ca4b9d6bc41ac17c90c72c3489fad433bb064ca2239e5fc6",
        "robot_model_sha256": "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190",
        "stress_replay_file_sha256": "8b598c5b582f063a5989cd434ef2f4d2a842445c69aa8706becd7948681dc31b",
        "stress_replay_sha256": "199a8f77e6cdbc00154ae0f01aca490b4a074c56b6b28dcf0ace641390b8ffe8",
    }


def test_all_never_pairs_remain_free_but_retained_false_positives_reappear() -> None:
    receipt = _load(ASSESSMENT)
    summary = receipt["summary"]
    assert summary["supported_never_pair_count"] == 6
    assert summary["contradicted_never_pair_count"] == 0
    assert summary["retained_pair_counts"] == {
        "AGREEMENT_COLLISION": 36,
        "AGREEMENT_FREE": 2255,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 13,
    }
    assert summary["retained_false_positive_pair_count"] == 6
    false_positive_pairs = {
        tuple(row["body_pair"]): row["counts"]["CANDIDATE_FALSE_POSITIVE"]
        for row in receipt["retained_nonzero_pair_reviews"]
        if row["counts"]["CANDIDATE_FALSE_POSITIVE"]
    }
    assert false_positive_pairs == {
        ("base_link", "link4"): 1,
        ("base_link", "link5"): 2,
        ("base_link", "gripper_link"): 1,
        ("link1", "link5"): 3,
        ("gripper_link", "link1"): 5,
        ("gripper_link", "link2"): 1,
    }


def test_stress_assessment_keeps_candidate_inert_and_nonadmissible() -> None:
    receipt = _load(ASSESSMENT)
    assert receipt["installation_state"] == "CANDIDATE_UNINSTALLED"
    assert receipt["effective_exclusions"] == []
    assert receipt["default_pair_disposition"] == "CHECK_COLLISION"
    assert receipt["collision_query_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert receipt["controller_authority"] is False
    assert receipt["execution_permit_authority"] is False
    assert receipt["transport_authority"] is False
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0
