from __future__ import annotations

import json
from pathlib import Path

import pytest

from rocell_ai.tripod_support_screen import (
    load_tripod_screen_fixture,
    run_tripod_support_screen,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/tripod_support_screen_v1.json"


def test_fixture_is_hash_bound_and_zero_authority() -> None:
    fixture = load_tripod_screen_fixture(FIXTURE, workspace=ROOT)
    assert fixture["selected_support"]["candidate_id"] == "COMMERCIAL-TRIPOD-ASIN-B0CSYB4YQ2"
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_fixture_rejects_tampering(tmp_path: Path) -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["screen"]["required_clearance_mm"] = 0.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash mismatch"):
        load_tripod_screen_fixture(changed, workspace=ROOT)


def test_wrong_support_model_is_rejected(tmp_path: Path) -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value.pop("fixture_sha256")
    value["selected_support"]["support_type"] = "paired_2020_camera_mast"
    import hashlib
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode()
    value["fixture_sha256"] = hashlib.sha256(canonical).hexdigest()
    changed = tmp_path / "wrong-model.json"
    changed.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="wrong support model"):
        load_tripod_screen_fixture(changed, workspace=ROOT)


def test_screen_covers_all_support_bodies_and_retains_physical_block() -> None:
    result = run_tripod_support_screen(
        load_tripod_screen_fixture(FIXTURE, workspace=ROOT), workspace=ROOT)
    assert result["body_count"] == 11
    assert {"tripod:column", "tripod:overhead_neck", "tripod:head",
            "tripod:adapter", "tripod:b0477_camera",
            "tripod:usb_cable_service_loop", "tripod:operator_keepout",
            "tripod:floor_footprint"}.issubset(result["body_inventory"])
    assert result["nominal_height_result"]["decision"] == "PASS_SYNTHETIC_ONLY"
    assert result["height_results"][0]["decision"] == "STOP"
    assert result["decision"] == "PASS_NOMINAL_SYNTHETIC_SCREEN_PHYSICAL_BLOCKED"
    assert result["official_readiness"] == "NOT_READY_FOR_FIRST_POWERED_MOTION"
    assert result["physical_authority"] is False


def test_screen_is_deterministic() -> None:
    fixture = load_tripod_screen_fixture(FIXTURE, workspace=ROOT)
    first = run_tripod_support_screen(fixture, workspace=ROOT)
    second = run_tripod_support_screen(fixture, workspace=ROOT)
    assert first == second
