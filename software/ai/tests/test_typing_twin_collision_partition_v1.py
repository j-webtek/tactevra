from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.typing_twin_collision_partition_v1 import (  # noqa: E402
    _load_fixture,
    run_collision_partition_study,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
FIXTURE = ROOT / "ai/sim/evidence/typing_twin_collision_partition_fixture_v1.json"
RESULT = ROOT / "ai/sim/evidence/typing_twin_collision_partition_result_v1.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def test_fixture_freezes_exact_coverage_without_authority() -> None:
    fixture = _load_fixture(FIXTURE, WORKSPACE)
    assert not any(fixture["counters"].values())
    assert fixture["sampling_policy"] == {
        "maximum_joint_step_rad": 0.05,
        "maximum_samples": 256,
    }
    assert fixture["expected_partition_shape"] == {
        "sample_counts": [256, 74],
        "source_result_counts": [255, 73],
        "source_result_ranges": [[0, 255], [255, 328]],
    }
    rules = fixture["decision_rules"]
    assert rules["source_endpoint_duplicated_count_maximum"] == 0
    assert rules["source_endpoint_omitted_count_maximum"] == 0
    assert rules["boundary_maximum_joint_difference_rad"] == 0.0
    assert rules["installed_collision_gate_cleared_must_be"] is False


def test_fixture_tampering_fails_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["sampling_policy"]["maximum_samples"] = 255
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash"):
        _load_fixture(changed, WORKSPACE)

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document.pop("fixture_sha256")
    document["input_bindings"]["partition_contract"]["sha256"] = "0" * 64
    document["fixture_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    rebound = tmp_path / "rebound.json"
    rebound.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="bound source hash changed"):
        _load_fixture(rebound, WORKSPACE)


def test_frozen_partition_study_reproduces_result() -> None:
    if not RESULT.is_file():
        pytest.skip("frozen execution result has not been generated yet")
    retained = json.loads(RESULT.read_text(encoding="utf-8"))
    replayed = run_collision_partition_study(FIXTURE, workspace=WORKSPACE)
    assert replayed == retained
    assert replayed["decision"] == (
        "PASS_EXACT_PARTITION_COVERAGE_RETAIN_COLLISION_BLOCKERS"
    )
    assert replayed["source_result_count"] == 328
    assert replayed["partition_count"] == 2
    assert replayed["total_partition_sample_count"] == 330
    assert replayed["conservative_boundary_recheck_count"] == 1
    assert replayed["source_endpoint_duplicated_count"] == 0
    assert replayed["source_endpoint_omitted_count"] == 0
    assert replayed["installed_collision_gate_cleared"] is False
    assert replayed["continuous_collision_proven"] is False
    assert replayed["hardware_writes"] == replayed["physical_movements"] == 0
    assert replayed["physical_authority"] is False
