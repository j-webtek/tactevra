from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
AI_SIM = ROOT / "software" / "ai" / "sim"
sys.path.insert(0, str(AI_SIM))

from build_grouped_neighborhood_training_fixture import (  # noqa: E402
    DEVELOPMENT_BLOCKS,
    DIAGNOSED_TRAINING_BLOCKS,
    EXPECTED_SOURCE_FILE_SHA256,
    EXPECTED_V15_DIAGNOSTIC_FILE_SHA256,
    EXPECTED_V15_FIXTURE_FILE_SHA256,
    TRAINING_BLOCKS,
    build,
)


SOURCE = ROOT / "software/integrations/isaac_sim/evidence/actual_emitter_joint_schedule_bundle_9e5c878_20260929.json"
V15_FIXTURE = ROOT / "software/ai/sim/evidence/pose_diverse_training_development_v1.json"
V15_DIAGNOSTIC = ROOT / "software/ai/eval/pose_cluster_development_diagnostic_v1.json"


def _load(path: Path, expected: str) -> tuple[dict, bytes]:
    payload = path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == expected
    return json.loads(payload), payload


def _inputs():
    return (
        *_load(SOURCE, EXPECTED_SOURCE_FILE_SHA256),
        *_load(V15_FIXTURE, EXPECTED_V15_FIXTURE_FILE_SHA256),
        *_load(V15_DIAGNOSTIC, EXPECTED_V15_DIAGNOSTIC_FILE_SHA256),
    )


def test_grouped_fixture_is_deterministic_balanced_isolated_and_zero_authority():
    args = _inputs()
    fixture = build(*args)
    assert fixture == build(*args)
    assert fixture["sample_count"] == 320
    assert fixture["split_counts"] == {"training": 256, "development": 64}
    assert fixture["hardware_writes"] == fixture["physical_movements"] == 0
    assert fixture["physical_authority"] is False
    assert DIAGNOSED_TRAINING_BLOCKS.issubset(TRAINING_BLOCKS)
    assert all(abs(train - dev) >= 2 for train in TRAINING_BLOCKS for dev in DEVELOPMENT_BLOCKS)
    assert min(map(int, fixture["split_block_counts"]["training"].values())) >= 8
    assert min(map(int, fixture["split_block_counts"]["development"].values())) >= 4
    rows = fixture["samples"]
    assert [row["sequence"] for row in rows] == list(range(3001, 3321))
    assert len({tuple(row["source_path_fraction"]) for row in rows}) == 320
    consumed = {tuple(row["source_path_fraction"]) for row in args[2]["samples"]}
    assert not consumed.intersection(tuple(row["source_path_fraction"]) for row in rows)


def test_grouped_fixture_rejects_changed_identity_and_authority():
    args = _inputs()
    with pytest.raises(ValueError, match="identity mismatch"):
        build(args[0], args[1] + b"\n", *args[2:])
    altered = deepcopy(args[0])
    altered["hardware_writes"] = 1
    with pytest.raises(ValueError, match="zero-authority"):
        build(altered, args[1], *args[2:])


def test_grouped_fixture_rejects_changed_diagnostic_contract():
    args = _inputs()
    altered = deepcopy(args[4])
    altered["evaluation_accessed"] = True
    with pytest.raises(ValueError, match="diagnostic contract mismatch"):
        build(*args[:4], altered, args[5])
