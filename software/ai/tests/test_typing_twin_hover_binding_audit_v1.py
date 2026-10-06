from __future__ import annotations

import json
from pathlib import Path

import pytest

from rocell_ai.typing_twin_hover_binding_audit_v1 import (
    _load_fixture,
    _raw_keyboard_target,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/typing_twin_hover_binding_fixture_v1.json"
RESULT = ROOT / "software/ai/sim/evidence/typing_twin_hover_binding_result_v1.json"


def test_raw_h_target_derivation_is_explicit() -> None:
    catalog = json.loads(
        (ROOT / "software/config/nominal_target_profiles.json").read_text()
    )
    target = _raw_keyboard_target(catalog, "H")

    assert target["row_index"] == 2
    assert target["key_index"] == 5
    assert target["local_center_xy_mm"] == [131.55, 69.0]
    assert target["derived_center_board_mm"] == [216.55, 154.0, 21.0]


def test_fixture_is_hash_bound_and_zero_authority() -> None:
    if not FIXTURE.exists():
        pytest.skip("fixture is committed in the pre-result increment")
    fixture = _load_fixture(FIXTURE, ROOT)

    assert fixture["decision_rules"]["combination_count_exact"] == 25
    assert fixture["sweep"]["tool_length_mm"] == [80.0, 90.0, 100.0, 110.0, 120.0]
    assert fixture["sweep"]["hover_clearance_mm"] == [5.0, 10.0, 15.0, 20.0, 25.0]
    assert all(value == 0 for value in fixture["counters"].values())


def test_fixture_rejects_mutation(tmp_path: Path) -> None:
    if not FIXTURE.exists():
        pytest.skip("fixture is committed in the pre-result increment")
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["sweep"]["tool_length_mm"] = [100.0]
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture hash changed"):
        _load_fixture(altered, ROOT)


def test_result_preserves_binding_and_zero_authority() -> None:
    if not RESULT.exists():
        pytest.skip("result is committed after the frozen audit")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert result["binding_audit"]["target"]["exact_match"] is True
    assert result["binding_audit"]["board_transform"]["exact_match"] is True
    assert result["target_coordinate_change_count"] == 0
    assert result["board_transform_change_count"] == 0
    assert result["hardware_writes"] == 0
    assert result["physical_movements"] == 0
    assert result["physical_authority"] is False
