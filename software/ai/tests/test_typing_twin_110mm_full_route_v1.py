from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.typing_twin_110mm_full_route_v1 import (  # noqa: E402
    _load_fixture,
    run_full_route,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
FIXTURE = ROOT / "ai/sim/evidence/typing_twin_110mm_full_route_fixture_v1.json"
RESULT = ROOT / "ai/sim/evidence/typing_twin_110mm_full_route_result_v1.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()


def test_fixture_is_frozen_and_zero_authority() -> None:
    fixture = _load_fixture(FIXTURE, WORKSPACE)
    assert not any(fixture["counters"].values())
    assert fixture["reconstruction"] == {
        "hover_clearance_mm": 25.0,
        "tool_length_mm": 110.0,
    }
    assert fixture["decision_rules"]["ik_threshold_change_count_maximum"] == 0
    assert fixture["decision_rules"]["continuity_threshold_change_count_maximum"] == 0
    assert fixture["decision_rules"]["installed_collision_gate_must_remain_blocked"]


def test_fixture_tampering_fails_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["reconstruction"]["hover_clearance_mm"] = 24.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash"):
        _load_fixture(changed, WORKSPACE)

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document.pop("fixture_sha256")
    document["input_bindings"]["canonical_ik"]["sha256"] = "0" * 64
    document["fixture_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    rebound = tmp_path / "rebound.json"
    rebound.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="bound source hash changed"):
        _load_fixture(rebound, WORKSPACE)


def test_frozen_full_route_reproduces_the_retained_blocker() -> None:
    retained = json.loads(RESULT.read_text(encoding="utf-8"))
    replayed = run_full_route(FIXTURE, workspace=WORKSPACE)
    assert replayed == retained
    assert replayed["decision"] == "BLOCKED_CANONICAL_IK_OR_CONTINUITY"
    assert replayed["trajectory_sample_count"] == 314
    assert replayed["ik_accepted_sample_count"] == 24
    assert replayed["ik_screen"]["evaluated_sample_count"] == 25
    assert replayed["ik_screen"]["joint_results"][-1]["waypoint_sequence"] == 24
    assert replayed["ik_screen"]["joint_results"][-1]["semantic_target"] == "H"
    assert replayed["ik_screen"]["joint_results"][-1]["failure_reason"] == (
        "MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED"
    )
    assert replayed["candidate_collision_sample_scope"] == "ACCEPTED_PREFIX_ONLY"
    assert replayed["candidate_continuous_collision_proven"] is False
    assert replayed["installed_collision_gate_cleared"] is False
    assert replayed["hardware_writes"] == replayed["physical_movements"] == 0
    assert replayed["physical_authority"] is False
