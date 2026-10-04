"""Strict loader for inert, hash-bound collision exclusion-policy candidates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA = "rocell.collision_exclusion_policy_candidate.v1"
MAX_POLICY_BYTES = 262_144
MAX_PROPOSED_EXCLUSIONS = 64
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REASONS = {"UPSTREAM_SRDF_ADJACENT", "UPSTREAM_SRDF_NEVER"}
_SOURCE_KEYS = {
    "upstream_srdf",
    "selected_geometry_candidate",
    "selected_replay",
    "adjacent_policy_review",
    "never_pair_review",
}


class CollisionExclusionPolicyCandidateError(ValueError):
    """An exclusion candidate is malformed, stale, or attempts authority."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _exact(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CollisionExclusionPolicyCandidateError(f"{label} must be an object")
    actual = set(value)
    if actual != fields:
        raise CollisionExclusionPolicyCandidateError(
            f"{label} fields differ: missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)}"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollisionExclusionPolicyCandidateError(f"{label} must be nonempty text")
    return value.strip()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CollisionExclusionPolicyCandidateError(f"{label} must be a SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class ProposedCollisionPairExclusion:
    body_pair: tuple[str, str]
    upstream_reason: str
    supporting_evidence_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "body_pair": list(self.body_pair),
            "upstream_reason": self.upstream_reason,
            "supporting_evidence_sha256": self.supporting_evidence_sha256,
        }


@dataclass(frozen=True, slots=True)
class CollisionExclusionPolicyCandidate:
    policy_id: str
    base_contract_sha256: str
    robot_model_sha256: str
    geometry_candidate_sha256: str
    source_bindings: Mapping[str, str]
    proposed_exclusions: tuple[ProposedCollisionPairExclusion, ...]
    content_sha256: str
    file_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_bindings", MappingProxyType(dict(sorted(self.source_bindings.items())))
        )

    @property
    def effective_exclusions(self) -> tuple[tuple[str, str], ...]:
        """Candidates are inert by construction; no runtime pair is excluded."""

        return ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "policy_id": self.policy_id,
            "installation_state": "CANDIDATE_UNINSTALLED",
            "default_pair_disposition": "CHECK_COLLISION",
            "base_contract_sha256": self.base_contract_sha256,
            "robot_model_sha256": self.robot_model_sha256,
            "geometry_candidate_sha256": self.geometry_candidate_sha256,
            "source_bindings": dict(self.source_bindings),
            "proposed_exclusions": [row.to_dict() for row in self.proposed_exclusions],
            "effective_exclusions": [],
            "authority": {
                "collision_query": False,
                "clearance_replay": False,
                "controller": False,
                "execution_permit": False,
                "transport": False,
                "physical": False,
            },
            "content_sha256": self.content_sha256,
            "file_sha256": self.file_sha256,
        }


def load_collision_exclusion_policy_candidate(
    path: str | Path,
    expected_file_sha256: str,
    *,
    expected_base_contract_sha256: str,
    expected_robot_model_sha256: str,
    expected_geometry_candidate_sha256: str,
    expected_source_bindings: Mapping[str, str],
    known_body_ids: Sequence[str],
) -> CollisionExclusionPolicyCandidate:
    """Strictly decode one inert candidate and bind it to exact expected inputs."""

    expected_file = _digest(expected_file_sha256, "expected_file_sha256")
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise CollisionExclusionPolicyCandidateError(f"cannot read candidate {source}") from exc
    if len(payload) > MAX_POLICY_BYTES:
        raise CollisionExclusionPolicyCandidateError("candidate exceeds byte limit")
    file_sha256 = hashlib.sha256(payload).hexdigest()
    if file_sha256 != expected_file:
        raise CollisionExclusionPolicyCandidateError("candidate file hash mismatch")

    def reject_constant(value: str) -> None:
        raise CollisionExclusionPolicyCandidateError(f"non-finite JSON constant {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CollisionExclusionPolicyCandidateError(
                    f"duplicate JSON field {key!r}"
                )
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CollisionExclusionPolicyCandidateError(
            "candidate is not strict UTF-8 JSON"
        ) from exc

    root = _exact(
        document,
        {
            "schema", "policy_id", "installation_state", "default_pair_disposition",
            "base_contract_sha256", "robot_model_sha256", "geometry_candidate_sha256",
            "source_bindings", "proposed_exclusions", "effective_exclusions",
            "authority", "content_sha256",
        },
        "candidate",
    )
    if root["schema"] != SCHEMA:
        raise CollisionExclusionPolicyCandidateError("candidate schema mismatch")
    if root["installation_state"] != "CANDIDATE_UNINSTALLED":
        raise CollisionExclusionPolicyCandidateError("candidate must remain uninstalled")
    if root["default_pair_disposition"] != "CHECK_COLLISION":
        raise CollisionExclusionPolicyCandidateError("candidate must default to collision checks")

    base_hash = _digest(root["base_contract_sha256"], "base_contract_sha256")
    model_hash = _digest(root["robot_model_sha256"], "robot_model_sha256")
    geometry_hash = _digest(root["geometry_candidate_sha256"], "geometry_candidate_sha256")
    if (
        base_hash != _digest(expected_base_contract_sha256, "expected_base_contract_sha256")
        or model_hash != _digest(expected_robot_model_sha256, "expected_robot_model_sha256")
        or geometry_hash
        != _digest(expected_geometry_candidate_sha256, "expected_geometry_candidate_sha256")
    ):
        raise CollisionExclusionPolicyCandidateError(
            "candidate contract/model/geometry binding mismatch"
        )

    raw_sources = root["source_bindings"]
    if not isinstance(raw_sources, Mapping) or set(raw_sources) != _SOURCE_KEYS:
        raise CollisionExclusionPolicyCandidateError(
            "candidate source bindings must contain the exact required keys"
        )
    sources = {str(key): _digest(value, f"source binding {key}") for key, value in raw_sources.items()}
    expected_sources = {
        str(key): _digest(value, f"expected source binding {key}")
        for key, value in expected_source_bindings.items()
    }
    if set(expected_sources) != _SOURCE_KEYS or sources != expected_sources:
        raise CollisionExclusionPolicyCandidateError("candidate source bindings mismatch")

    raw_effective = root["effective_exclusions"]
    if not isinstance(raw_effective, list) or raw_effective:
        raise CollisionExclusionPolicyCandidateError(
            "uninstalled candidate effective_exclusions must be an empty array"
        )
    authority = _exact(
        root["authority"],
        {"collision_query", "clearance_replay", "controller", "execution_permit", "transport", "physical"},
        "candidate authority",
    )
    if any(value is not False for value in authority.values()):
        raise CollisionExclusionPolicyCandidateError("candidate cannot grant authority")

    known = {_text(value, "known_body_id") for value in known_body_ids}
    if len(known) != len(known_body_ids):
        raise CollisionExclusionPolicyCandidateError("known body ids must be unique")
    raw_proposed = root["proposed_exclusions"]
    if not isinstance(raw_proposed, list) or len(raw_proposed) > MAX_PROPOSED_EXCLUSIONS:
        raise CollisionExclusionPolicyCandidateError("proposed exclusions exceed bounds")
    proposed = []
    pairs_seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_proposed):
        item = _exact(
            raw,
            {"body_pair", "upstream_reason", "supporting_evidence_sha256"},
            f"proposed exclusion {index}",
        )
        pair_value = item["body_pair"]
        if (
            not isinstance(pair_value, list)
            or len(pair_value) != 2
            or any(not isinstance(value, str) or not value.strip() for value in pair_value)
        ):
            raise CollisionExclusionPolicyCandidateError("body_pair must contain two body ids")
        pair = tuple(sorted(value.strip() for value in pair_value))
        if pair[0] == pair[1] or pair != tuple(pair_value):
            raise CollisionExclusionPolicyCandidateError(
                "body_pair must contain two distinct ids in canonical order"
            )
        if pair in pairs_seen:
            raise CollisionExclusionPolicyCandidateError("proposed body pairs must be unique")
        if not set(pair) <= known:
            raise CollisionExclusionPolicyCandidateError("proposed pair references unknown body")
        reason = item["upstream_reason"]
        if reason not in _REASONS:
            raise CollisionExclusionPolicyCandidateError("unsupported upstream exclusion reason")
        evidence = _digest(
            item["supporting_evidence_sha256"],
            f"proposed exclusion {index} supporting evidence",
        )
        required_evidence = sources[
            "adjacent_policy_review"
            if reason == "UPSTREAM_SRDF_ADJACENT"
            else "never_pair_review"
        ]
        if evidence != required_evidence:
            raise CollisionExclusionPolicyCandidateError(
                "proposed exclusion evidence does not match its reason"
            )
        pairs_seen.add(pair)
        proposed.append(ProposedCollisionPairExclusion(pair, reason, evidence))
    if [item.body_pair for item in proposed] != sorted(item.body_pair for item in proposed):
        raise CollisionExclusionPolicyCandidateError("proposed exclusions must be sorted")

    claimed = _digest(root["content_sha256"], "content_sha256")
    unsigned = dict(root)
    del unsigned["content_sha256"]
    if hashlib.sha256(_canonical(unsigned)).hexdigest() != claimed:
        raise CollisionExclusionPolicyCandidateError("candidate content hash mismatch")
    return CollisionExclusionPolicyCandidate(
        _text(root["policy_id"], "policy_id"),
        base_hash,
        model_hash,
        geometry_hash,
        sources,
        tuple(proposed),
        claimed,
        file_sha256,
    )


__all__ = [
    "SCHEMA",
    "CollisionExclusionPolicyCandidate",
    "CollisionExclusionPolicyCandidateError",
    "ProposedCollisionPairExclusion",
    "load_collision_exclusion_policy_candidate",
]
