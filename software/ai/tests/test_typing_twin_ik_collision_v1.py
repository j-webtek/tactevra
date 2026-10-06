from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.typing_twin_ik_collision_v1 import (  # noqa: E402
    _load_fixture,
    run_typing_ik_collision,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
FIXTURE = ROOT / "ai/sim/evidence/typing_twin_ik_collision_fixture_v1_4.json"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def test_fixture_is_frozen_ranged_and_zero_authority() -> None:
    fixture = _load_fixture(FIXTURE, WORKSPACE)
    assert fixture["fixture_sha256"] == (
        "da3dfb4c9eb580af81c3ff7dab95bb8d77b6d8b622bf32c3d8a111834c950308"
    )
    assert not any(fixture["counters"].values())
    assert fixture["resource_limits"]["expected_candidate_profile_count"] == 64
    for values in fixture["candidate_collision_ranges"].values():
        assert len(values) == 2
        assert values[0] < values[1]


def test_blocked_route_and_prefix_diagnostic_are_repeatable() -> None:
    first = run_typing_ik_collision(FIXTURE, workspace=WORKSPACE)
    second = run_typing_ik_collision(FIXTURE, workspace=WORKSPACE)
    assert first == second
    assert first["receipt_sha256"] == (
        "e45cc5c652cc8ae1bdc2ee74e9beee0de13c763ebc7fba9a5bebfe9f358734c1"
    )
    assert first["decision"] == "BLOCKED_CANONICAL_IK_PREFIX_DIAGNOSTIC_ONLY"
    assert first["ordered_targets"] == [
        "H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6",
    ]
    assert first["trajectory_sample_count"] == 260
    assert first["ik_screen"]["evaluated_sample_count"] == 16
    assert first["ik_screen"]["ik_all_samples_accepted"] is False
    assert first["ik_screen"]["blockers"] == [
        "IK_ROUTE_REJECTED:MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED"
    ]
    assert first["candidate_diagnostic_sample_scope"] == "ACCEPTED_PREFIX_ONLY"
    diagnostic = first["candidate_collision_diagnostic"]
    assert diagnostic["profile_count"] == 64
    assert {item["sample_count"] for item in diagnostic["profiles"]} == {15}
    assert sum(item["collision_sample_count"] > 0
               for item in diagnostic["profiles"]) == 32
    assert {
        pair for item in diagnostic["profiles"]
        for pair in item["collision_pair_counts"]
    } == {"robot:base_link/robot:link2"}
    assert diagnostic["can_clear_installed_collision_gate"] is False
    assert first["installed_collision_intake"]["status"] == (
        "NOT_REACHED_CANONICAL_IK_BLOCKED")
    assert first["installed_collision_gate_cleared"] is False
    assert first["controller_commands"] == []
    assert first["hardware_commands_generated"] == 0
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_fixture_and_bound_source_tampering_fail_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["resource_limits"]["expected_candidate_profile_count"] = 63
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
