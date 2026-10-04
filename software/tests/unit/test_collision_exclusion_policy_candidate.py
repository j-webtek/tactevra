from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.simulation.exclusion_policy import (
    CollisionExclusionPolicyCandidateError,
    load_collision_exclusion_policy_candidate,
)


BASE = "1" * 64
MODEL = "2" * 64
GEOMETRY = "3" * 64
SOURCES = {
    "upstream_srdf": "4" * 64,
    "selected_geometry_candidate": GEOMETRY,
    "selected_replay": "5" * 64,
    "adjacent_policy_review": "6" * 64,
    "never_pair_review": "7" * 64,
}
BODIES = ("robot:base_link", "robot:link1", "robot:link2")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _document() -> dict:
    value = {
        "schema": "rocell.collision_exclusion_policy_candidate.v1",
        "policy_id": "unit-test-candidate",
        "installation_state": "CANDIDATE_UNINSTALLED",
        "default_pair_disposition": "CHECK_COLLISION",
        "base_contract_sha256": BASE,
        "robot_model_sha256": MODEL,
        "geometry_candidate_sha256": GEOMETRY,
        "source_bindings": dict(SOURCES),
        "proposed_exclusions": [
            {
                "body_pair": ["robot:base_link", "robot:link1"],
                "upstream_reason": "UPSTREAM_SRDF_ADJACENT",
                "supporting_evidence_sha256": SOURCES["adjacent_policy_review"],
            },
            {
                "body_pair": ["robot:link1", "robot:link2"],
                "upstream_reason": "UPSTREAM_SRDF_NEVER",
                "supporting_evidence_sha256": SOURCES["never_pair_review"],
            },
        ],
        "effective_exclusions": [],
        "authority": {
            "collision_query": False,
            "clearance_replay": False,
            "controller": False,
            "execution_permit": False,
            "transport": False,
            "physical": False,
        },
    }
    value["content_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _write(tmp_path: Path, value: dict) -> tuple[Path, str]:
    payload = _canonical(value)
    path = tmp_path / "candidate.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _load(path: Path, file_hash: str, *, sources=SOURCES):
    return load_collision_exclusion_policy_candidate(
        path,
        file_hash,
        expected_base_contract_sha256=BASE,
        expected_robot_model_sha256=MODEL,
        expected_geometry_candidate_sha256=GEOMETRY,
        expected_source_bindings=sources,
        known_body_ids=BODIES,
    )


def _rehash(value: dict) -> None:
    value.pop("content_sha256", None)
    value["content_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()


def test_loads_hash_bound_candidate_with_no_effective_exclusions(tmp_path: Path) -> None:
    path, file_hash = _write(tmp_path, _document())
    candidate = _load(path, file_hash)
    assert len(candidate.proposed_exclusions) == 2
    assert candidate.effective_exclusions == ()
    assert candidate.to_dict()["authority"] == {
        "collision_query": False,
        "clearance_replay": False,
        "controller": False,
        "execution_permit": False,
        "transport": False,
        "physical": False,
    }


def test_rejects_wrong_file_hash_before_decode(tmp_path: Path) -> None:
    path, _ = _write(tmp_path, _document())
    with pytest.raises(CollisionExclusionPolicyCandidateError, match="file hash"):
        _load(path, "0" * 64)


def test_rejects_content_tamper_even_when_file_hash_is_current(tmp_path: Path) -> None:
    value = _document()
    value["policy_id"] = "tampered"
    path, file_hash = _write(tmp_path, value)
    with pytest.raises(CollisionExclusionPolicyCandidateError, match="content hash"):
        _load(path, file_hash)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["effective_exclusions"].append(
                ["robot:base_link", "robot:link1"]
            ),
            "effective_exclusions must be an empty array",
        ),
        (
            lambda value: value["authority"].update(controller=True),
            "cannot grant authority",
        ),
        (
            lambda value: value["proposed_exclusions"][0].update(
                body_pair=["robot:link1", "robot:base_link"]
            ),
            "canonical order",
        ),
        (
            lambda value: value["proposed_exclusions"][0].update(
                supporting_evidence_sha256=SOURCES["never_pair_review"]
            ),
            "evidence does not match",
        ),
        (
            lambda value: value["proposed_exclusions"][0].update(
                body_pair=["robot:base_link", "robot:unknown"]
            ),
            "unknown body",
        ),
    ],
)
def test_rejects_authority_and_invalid_proposals(
    tmp_path: Path, mutation, message: str
) -> None:
    value = _document()
    mutation(value)
    _rehash(value)
    path, file_hash = _write(tmp_path, value)
    with pytest.raises(CollisionExclusionPolicyCandidateError, match=message):
        _load(path, file_hash)


def test_rejects_expected_source_binding_drift(tmp_path: Path) -> None:
    path, file_hash = _write(tmp_path, _document())
    changed = dict(SOURCES, selected_replay="8" * 64)
    with pytest.raises(CollisionExclusionPolicyCandidateError, match="source bindings mismatch"):
        _load(path, file_hash, sources=changed)


def test_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    payload = b'{"schema":"x","schema":"y"}'
    path = tmp_path / "duplicate.json"
    path.write_bytes(payload)
    with pytest.raises(CollisionExclusionPolicyCandidateError, match="duplicate JSON field"):
        _load(path, hashlib.sha256(payload).hexdigest())
