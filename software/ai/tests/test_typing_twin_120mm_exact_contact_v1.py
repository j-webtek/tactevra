from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.typing_twin_120mm_exact_contact_v1 import (  # noqa: E402
    _load_fixture,
    _profile_clearances,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
FIXTURE = ROOT / "ai/sim/evidence/typing_twin_120mm_exact_contact_fixture_v1.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def test_fixture_is_frozen_bounded_and_zero_authority() -> None:
    fixture = _load_fixture(FIXTURE, WORKSPACE)
    assert not any(fixture["counters"].values())
    assert fixture["reconstruction"] == {
        "maximum_hover_clearance_mm": 25.0,
        "tool_length_mm": 120.0,
        "vertical_step_mm": 1.0,
    }
    assert fixture["decision_rules"]["profile_point_count_exact"] == 26
    assert fixture["decision_rules"]["contact_point_change_count_maximum"] == 0
    assert fixture["decision_rules"]["ik_threshold_change_count_maximum"] == 0
    assert fixture["decision_rules"]["continuity_threshold_change_count_maximum"] == 0


def test_profile_includes_frozen_hover_and_exact_contact_once() -> None:
    profile = _profile_clearances(25.0, 1.0)
    assert profile == tuple(float(value) for value in range(25, -1, -1))
    assert len(profile) == 26
    with pytest.raises(ValueError, match="terminate exactly"):
        _profile_clearances(25.0, 3.0)


def test_fixture_tampering_fails_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["reconstruction"]["vertical_step_mm"] = 2.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash"):
        _load_fixture(changed, WORKSPACE)

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document.pop("fixture_sha256")
    document["input_bindings"]["implementation"]["sha256"] = "0" * 64
    document["fixture_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    rebound = tmp_path / "rebound.json"
    rebound.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="bound source hash changed"):
        _load_fixture(rebound, WORKSPACE)
