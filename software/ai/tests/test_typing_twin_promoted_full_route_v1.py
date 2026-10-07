from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.typing_twin_promoted_full_route_v1 import (  # noqa: E402
    _load_fixture,
    run_promoted_full_route,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
FIXTURE = ROOT / "ai/sim/evidence/typing_twin_promoted_full_route_fixture_v1_1.json"
RESULT = ROOT / "ai/sim/evidence/typing_twin_promoted_full_route_result_v1_1.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def test_fixture_is_frozen_source_bound_and_zero_authority() -> None:
    fixture = _load_fixture(FIXTURE, WORKSPACE)
    assert not any(fixture["counters"].values())
    assert fixture["reconstruction"] == {
        "hover_clearance_mm": 25.0,
        "tool_length_mm": 120.0,
    }
    assert fixture["promoted_profile"] == {
        "profile_id": "ROCELL-VIRTUAL-COMMISSIONING-RANK1-001",
        "source_sha256": (
            "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634"
        ),
        "study_input_id": "reach-944d7463f4c67905",
    }
    assert fixture["admission_result"]["receipt_sha256"] == (
        "cb921499b8bd3441cfd631a780bbe2346d17478d475b1c047fcf64839de5de67"
    )
    assert fixture["decision_rules"]["ik_threshold_change_count_maximum"] == 0
    assert fixture["decision_rules"][
        "continuity_threshold_change_count_maximum"
    ] == 0
    assert fixture["decision_rules"][
        "installed_collision_gate_must_remain_blocked"
    ]


def test_fixture_tampering_fails_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["reconstruction"]["hover_clearance_mm"] = 24.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash"):
        _load_fixture(changed, WORKSPACE)

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document.pop("fixture_sha256")
    document["input_bindings"]["promoted_profile"]["sha256"] = "0" * 64
    document["fixture_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    rebound = tmp_path / "rebound.json"
    rebound.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="bound source hash changed"):
        _load_fixture(rebound, WORKSPACE)


def test_frozen_promoted_full_route_reproduces_result() -> None:
    if not RESULT.is_file():
        pytest.skip("frozen execution result has not been generated yet")
    retained = json.loads(RESULT.read_text(encoding="utf-8"))
    replayed = run_promoted_full_route(FIXTURE, workspace=WORKSPACE)
    assert replayed == retained
    assert replayed["promoted_profile"]["simulation_only"] is True
    assert replayed["installed_collision_gate_cleared"] is False
    assert replayed["candidate_continuous_collision_proven"] is False
    assert replayed["hardware_writes"] == replayed["physical_movements"] == 0
    assert replayed["physical_authority"] is False
