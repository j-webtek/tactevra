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

from build_pose_diverse_training_fixture import (  # noqa: E402
    CONSUMED_V14_FRACTIONS,
    EXPECTED_SOURCE_FILE_SHA256,
    TARGET_POSE_COUNT,
    build,
)


SOURCE = (
    ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
    / "actual_emitter_joint_schedule_bundle_9e5c878_20260929.json"
)


def _source() -> tuple[dict, bytes]:
    payload = SOURCE.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_SOURCE_FILE_SHA256
    return json.loads(payload), payload


def test_fixture_is_deterministic_distinct_and_excludes_consumed_v14():
    source, payload = _source()
    first = build(source, payload)
    second = build(source, payload)
    assert first == second
    assert first["sample_count"] == 96
    assert first["split_counts"] == {"training": 72, "development": 24}
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False
    fractions = {
        tuple(row["source_path_fraction"])
        for row in first["samples"]
    }
    assert len(fractions) == TARGET_POSE_COUNT
    assert not fractions.intersection(
        {(value.numerator, value.denominator) for value in CONSUMED_V14_FRACTIONS}
    )
    assert len({
        tuple(row["joint_positions_rad"].values()) for row in first["samples"]
    }) == first["sample_count"]


def test_fixture_rejects_authority_and_source_identity_changes():
    source, payload = _source()
    altered = deepcopy(source)
    altered["hardware_writes"] = 1
    with pytest.raises(ValueError, match="zero-authority"):
        build(altered, payload)
    with pytest.raises(ValueError, match="identity mismatch"):
        build(source, payload + b"\n")


def test_fixture_rejects_noncanonical_schedule_shape():
    source, payload = _source()
    altered = deepcopy(source)
    altered["samples"][0]["sequence"] = 99
    with pytest.raises(ValueError, match="sequence is not contiguous"):
        build(altered, payload)
