from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_collision_differential_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_differential_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "OFFLINE_THREE_POSE_COLLISION_DIFFERENTIAL_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_differential_binds_current_source_receipts_and_fcl_wheel() -> None:
    bindings = _load()["source_bindings"]
    mesh = (
        WORKSPACE / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_upstream_link_meshes_20260929.json"
    )
    reduction = (
        WORKSPACE / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_link_mesh_reduction_20260929.json"
    )
    assert bindings["mesh_receipt_file_sha256"] == _digest(mesh)
    assert bindings["reduction_receipt_file_sha256"] == _digest(reduction)
    assert bindings["reduction_receipt_sha256"] == (
        "e714a88c01b567f54b2e8c91b8f1144fcc35db38d2953dfe2c6f31e1d576adab"
    )
    assert bindings["python_fcl_version"] == "0.7.0.11"
    assert bindings["python_fcl_wheel_sha256"] == (
        "63c662c8ff30eeb78913624a4ac56209a6061248ed97066c3b744255d943299f"
    )


def test_three_pose_pair_corpus_has_no_candidate_false_negatives() -> None:
    receipt = _load()
    assert [item["pose_name"] for item in receipt["poses"]] == ["zero", "home", "ready"]
    assert all(len(item["pairs"]) == 21 for item in receipt["poses"])
    assert receipt["summary"] == {
        "agreement_collision": 3,
        "agreement_free": 48,
        "candidate_false_negative": 0,
        "candidate_false_positive": 12,
        "pair_cases": 63,
    }


def test_all_observed_false_positives_are_kinematically_adjacent() -> None:
    false_positives = [
        pair
        for pose in _load()["poses"]
        for pair in pose["pairs"]
        if pair["outcome"] == "CANDIDATE_FALSE_POSITIVE"
    ]
    assert len(false_positives) == 12
    assert all(pair["kinematically_adjacent"] for pair in false_positives)
    assert {tuple(pair["body_pair"]) for pair in false_positives} == {
        ("link1", "link2"),
        ("link2", "link3"),
        ("link3", "link4"),
        ("link5", "gripper_link"),
    }


def test_differential_does_not_admit_collision_queries() -> None:
    receipt = _load()
    assert receipt["candidate_profile_installable"] is False
    assert receipt["collision_query_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert {
        "CANDIDATE_FALSE_POSITIVE_COLLISIONS_OBSERVED",
        "THREE_POSE_CORPUS_IS_NOT_WORKSPACE_COVERAGE",
        "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
    } <= set(receipt["blockers"])
