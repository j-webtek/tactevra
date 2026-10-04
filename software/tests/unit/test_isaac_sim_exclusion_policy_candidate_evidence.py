from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.simulation.exclusion_policy import (
    load_collision_exclusion_policy_candidate,
)


WORKSPACE = Path(__file__).resolve().parents[3]
EVIDENCE = WORKSPACE / "software/integrations/isaac_sim/evidence"
CANDIDATE = EVIDENCE / "roarm_m3_collision_exclusion_policy_candidate_20260929.json"
SOURCES = {
    "upstream_srdf": "29f1daaeea91a490b85581a9a62dd07be9ab959d7817fad89836c466e8288499",
    "selected_geometry_candidate": "0568f7ba269cf190ca4b9d6bc41ac17c90c72c3489fad433bb064ca2239e5fc6",
    "selected_replay": "1cad314d6901c0f639c4771f7be79b235eeadf844eba600129d4f8bb45991b87",
    "adjacent_policy_review": "c6c1df0b304f7f8b36bd6b8e1015244d1b5e427b24476a85f84b846de5001423",
    "never_pair_review": "a2210f019e0dae09274be1e30b36dbaf69ffe3064b54030bb699568c9230c0e8",
}
BODIES = (
    "robot:base_link",
    "robot:link1",
    "robot:link2",
    "robot:link3",
    "robot:link4",
    "robot:link5",
    "robot:gripper",
)


def _load():
    payload = CANDIDATE.read_bytes()
    return load_collision_exclusion_policy_candidate(
        CANDIDATE,
        hashlib.sha256(payload).hexdigest(),
        expected_base_contract_sha256=(
            "d3238c0c95a1d2e7ff74fcb8dccc3eb0aadb0f897b2ea041319bbcd6442af5c3"
        ),
        expected_robot_model_sha256=(
            "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
        ),
        expected_geometry_candidate_sha256=SOURCES["selected_geometry_candidate"],
        expected_source_bindings=SOURCES,
        known_body_ids=BODIES,
    )


def test_retained_candidate_loads_with_exact_hash_bindings() -> None:
    candidate = _load()
    document = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    assert candidate.content_sha256 == document["content_sha256"]
    assert candidate.base_contract_sha256 == (
        "d3238c0c95a1d2e7ff74fcb8dccc3eb0aadb0f897b2ea041319bbcd6442af5c3"
    )
    assert dict(candidate.source_bindings) == SOURCES


def test_retained_candidate_proposes_all_srdf_pairs_but_effects_none() -> None:
    candidate = _load()
    reasons = [row.upstream_reason for row in candidate.proposed_exclusions]
    assert len(reasons) == 12
    assert reasons.count("UPSTREAM_SRDF_ADJACENT") == 6
    assert reasons.count("UPSTREAM_SRDF_NEVER") == 6
    assert candidate.effective_exclusions == ()


def test_retained_candidate_defaults_to_collision_checks_without_authority() -> None:
    document = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    assert document["installation_state"] == "CANDIDATE_UNINSTALLED"
    assert document["default_pair_disposition"] == "CHECK_COLLISION"
    assert document["effective_exclusions"] == []
    assert set(document["authority"].values()) == {False}


def test_proposal_evidence_matches_each_declared_reason() -> None:
    candidate = _load()
    for row in candidate.proposed_exclusions:
        expected = SOURCES[
            "adjacent_policy_review"
            if row.upstream_reason == "UPSTREAM_SRDF_ADJACENT"
            else "never_pair_review"
        ]
        assert row.supporting_evidence_sha256 == expected
