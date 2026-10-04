from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


WORKSPACE = Path(__file__).resolve().parents[3]
INTEGRATION = WORKSPACE / "software/integrations/isaac_sim"
sys.path.insert(0, str(INTEGRATION))

import collision_joint_space_probe as joint_space  # noqa: E402
import collision_policy_stress_probe as stress  # noqa: E402


URDF = WORKSPACE / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"


def test_default_joint_space_corpus_remains_byte_reproduction_compatible() -> None:
    poses, limits = joint_space._pose_corpus(URDF)
    assert len(poses) == 49
    assert len(limits) == 6
    assert poses[-1]["pose_name"] == "halton_032"
    assert poses[-1]["family"] == "HALTON_INTERIOR"


def test_stress_corpus_is_disjoint_bounded_and_deterministic() -> None:
    first, limits = joint_space._pose_corpus(
        URDF, halton_start=1001, halton_count=256, include_anchors=False
    )
    second, _ = joint_space._pose_corpus(
        URDF, halton_start=1001, halton_count=256, include_anchors=False
    )
    assert first == second
    assert len(first) == 256
    assert first[0]["pose_name"] == "halton_1001"
    assert first[-1]["pose_name"] == "halton_1256"
    assert {row["family"] for row in first} == {"HALTON_INTERIOR"}
    original, _ = joint_space._pose_corpus(
        URDF, halton_start=1, halton_count=32, include_anchors=False
    )
    assert {row["pose_name"] for row in first}.isdisjoint(
        row["pose_name"] for row in original
    )
    for row in first:
        for value, limit in zip(row["joint_positions_rad"], limits):
            assert limit["lower_rad"] <= value <= limit["upper_rad"]


@pytest.mark.parametrize(
    ("start", "count"),
    [(0, 1), (1, 0), (1, joint_space.MAX_HALTON_SAMPLE_COUNT + 1)],
)
def test_stress_corpus_rejects_unbounded_requests(start: int, count: int) -> None:
    with pytest.raises(ValueError):
        joint_space._pose_corpus(
            URDF, halton_start=start, halton_count=count, include_anchors=False
        )


def _row(pair: tuple[str, str], **counts: int) -> dict:
    complete = {name: 0 for name in stress.OUTCOMES}
    complete.update(counts)
    return {
        "body_pair": list(pair),
        "counts": complete,
        "minimum_raw_mesh_signed_distance_mm": 4.0,
        "minimum_candidate_box_signed_distance_mm": 3.0,
    }


def test_assessment_separates_proposed_and_retained_pair_behavior() -> None:
    candidate = SimpleNamespace(proposed_exclusions=(
        SimpleNamespace(
            body_pair=("robot:base_link", "robot:link1"),
            upstream_reason="UPSTREAM_SRDF_ADJACENT",
        ),
        SimpleNamespace(
            body_pair=("robot:base_link", "robot:link2"),
            upstream_reason="UPSTREAM_SRDF_NEVER",
        ),
    ))
    replay = {
        "pose_count": 256,
        "summary": {"PAIR_CASES": 768},
        "pair_summary": [
            _row(("base_link", "link1"), CANDIDATE_FALSE_POSITIVE=256),
            _row(("base_link", "link2"), AGREEMENT_FREE=256),
            _row(
                ("link1", "link2"),
                AGREEMENT_FREE=255,
                CANDIDATE_FALSE_NEGATIVE=1,
            ),
        ],
    }
    result = stress._assess(candidate, replay)
    assert result["summary"] == {
        "stress_pose_count": 256,
        "stress_pair_case_count": 768,
        "proposed_pair_count": 2,
        "proposed_adjacent_pair_count": 1,
        "proposed_never_pair_count": 1,
        "supported_never_pair_count": 1,
        "contradicted_never_pair_count": 0,
        "retained_pair_count": 1,
        "retained_collision_pair_count": 0,
        "retained_false_positive_pair_count": 0,
        "retained_false_negative_pair_count": 1,
        "retained_pair_counts": {
            "AGREEMENT_COLLISION": 0,
            "AGREEMENT_FREE": 255,
            "CANDIDATE_FALSE_POSITIVE": 0,
            "CANDIDATE_FALSE_NEGATIVE": 1,
        },
    }
    assert result["retained_nonzero_pair_reviews"] == [{
        "body_pair": ["link1", "link2"],
        "counts": {
            "AGREEMENT_COLLISION": 0,
            "AGREEMENT_FREE": 255,
            "CANDIDATE_FALSE_POSITIVE": 0,
            "CANDIDATE_FALSE_NEGATIVE": 1,
        },
        "minimum_raw_mesh_signed_distance_mm": 4.0,
        "minimum_candidate_box_signed_distance_mm": 3.0,
    }]


def test_assessment_preserves_never_pair_contradiction() -> None:
    candidate = SimpleNamespace(proposed_exclusions=(SimpleNamespace(
        body_pair=("robot:base_link", "robot:link2"),
        upstream_reason="UPSTREAM_SRDF_NEVER",
    ),))
    replay = {
        "pose_count": 256,
        "summary": {"PAIR_CASES": 256},
        "pair_summary": [
            _row(
                ("base_link", "link2"),
                AGREEMENT_FREE=255,
                AGREEMENT_COLLISION=1,
            )
        ],
    }
    result = stress._assess(candidate, replay)
    assert result["summary"]["supported_never_pair_count"] == 0
    assert result["summary"]["contradicted_never_pair_count"] == 1
    assert result["proposed_pair_reviews"][0][
        "held_out_supports_never_reason"
    ] is False
