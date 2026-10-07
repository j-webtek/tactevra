from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))

from rocell_ai.c03_arm_route_reconciliation_v1 import (  # noqa: E402
    canonical_hash,
    load_fixture,
    reconcile,
)


FIXTURE = AI_ROOT / "sim" / "evidence" / "c03_arm_route_reconciliation_fixture_v1.json"


def _write_fixture(tmp_path: Path, mutation) -> Path:
    value = load_fixture(FIXTURE)
    mutation(value)
    value.pop("fixture_sha256")
    value["fixture_sha256"] = canonical_hash(value)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_reconciliation_stops_on_exact_tool_identity_mismatch() -> None:
    result = reconcile(FIXTURE, WORKSPACE)
    assert result["decision"] == "STOP_C03_PROMOTED_ROUTE_TOOL_IDENTITY_MISMATCH"
    assert result["c03_candidate"]["tool_total_length_mm"] == 110.0
    assert result["promoted_arm_route"]["tool_total_length_mm"] == 120.0
    assert result["tool_length_difference_mm"] == 10.0
    assert result["c03_candidate"]["screened_ordered_pair_count"] == 2601
    assert result["c03_candidate"]["screened_row_count"] == 15606
    assert result["collision_screen_executed"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0
    assert result["controller_commands"] == []
    assert result["physical_authority"] is False
    receipt = result.pop("receipt_sha256")
    assert receipt == canonical_hash(result)


def test_altered_bound_file_hash_fails_closed(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        lambda value: value["bindings"]["promoted_full_route"].update({"sha256": "0" * 64}),
    )
    with pytest.raises(ValueError, match="bound artifact hash mismatch"):
        reconcile(fixture, WORKSPACE)


def test_wrong_promoted_tool_identity_fails_closed(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        lambda value: value["expected"].update({"promoted_route_tool_length_mm": 110.0}),
    )
    with pytest.raises(ValueError, match="promoted route tool length differs"):
        reconcile(fixture, WORKSPACE)


def test_fixture_zero_authority_is_strict(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        lambda value: value["counters"].update({"hardware_write_count": 1}),
    )
    with pytest.raises(ValueError, match="zero authority"):
        reconcile(fixture, WORKSPACE)


def test_duplicate_json_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    from rocell_ai.c03_arm_route_reconciliation_v1 import load_strict_json

    with pytest.raises(ValueError, match="duplicate JSON field"):
        load_strict_json(path)
