from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "software/ai/sim/build_static_evaluation_pose_fixture.py"
SOURCE = (
    ROOT / "software/integrations/isaac_sim/evidence"
    / "actual_emitter_joint_schedule_bundle_9e5c878_20260929.json"
)
FIXTURE = (
    ROOT / "software/ai/sim/evidence"
    / "static_interpolated_evaluation_poses_v1.json"
)


def _module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("static_pose_fixture", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retained_fixture_is_deterministic_fresh_and_zero_authority() -> None:
    module = _module()
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture == module.build(source, source_bytes)
    unsigned = dict(fixture)
    claimed = unsigned.pop("bundle_sha256")
    assert hashlib.sha256(module._canonical(unsigned)).hexdigest() == claimed
    assert fixture["sample_count"] == len(fixture["samples"]) == 6
    assert [row["source_path_fraction"] for row in fixture["samples"]] == [
        [2, 19], [5, 19], [8, 19], [11, 19], [14, 19], [17, 19],
    ]
    assert len({
        tuple(row["joint_positions_rad"].values()) for row in fixture["samples"]
    }) == 6
    assert fixture["controller_commands"] == []
    assert fixture["hardware_writes"] == fixture["physical_movements"] == 0
    assert fixture["hardware_access"] is fixture["physical_authority"] is False


def test_builder_rejects_changed_or_authoritative_source() -> None:
    module = _module()
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    with pytest.raises(ValueError, match="file identity mismatch"):
        module.build(source, source_bytes + b" ")

    source["physical_authority"] = True
    module.EXPECTED_SOURCE_FILE_SHA256 = hashlib.sha256(source_bytes).hexdigest()
    with pytest.raises(ValueError, match="zero-authority boundary"):
        module.build(source, source_bytes)
