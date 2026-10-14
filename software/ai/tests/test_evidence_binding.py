from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rocell_ai.evidence_binding import (
    load_compatible_emulator_fixture,
    load_compatible_first_motion_fixture,
    resolve_hash_bound_source,
)

ROOT = Path(__file__).resolve().parents[3]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_uses_hash_matching_active_source(tmp_path: Path) -> None:
    source = tmp_path / "software" / "config" / "profile.json"
    source.parent.mkdir(parents=True)
    source.write_text("active", encoding="utf-8")
    binding = {"path": "software/config/profile.json", "sha256": _sha(source)}

    assert resolve_hash_bound_source(tmp_path, binding) == source


def test_finds_exact_historical_config_in_freeze(tmp_path: Path) -> None:
    active = tmp_path / "software" / "config" / "profile.json"
    frozen = tmp_path / "software" / "freezes" / "FREEZE-001" / "profile.json"
    active.parent.mkdir(parents=True)
    frozen.parent.mkdir(parents=True)
    active.write_text("new", encoding="utf-8")
    frozen.write_text("old", encoding="utf-8")
    binding = {"path": "software/config/profile.json", "sha256": _sha(frozen)}

    assert resolve_hash_bound_source(tmp_path, binding) == frozen


def test_rejects_unmatched_or_non_config_binding(tmp_path: Path) -> None:
    source = tmp_path / "evidence.json"
    source.write_text("changed", encoding="utf-8")
    binding = {"path": "evidence.json", "sha256": "0" * 64}

    with pytest.raises(ValueError, match="bound source changed"):
        resolve_hash_bound_source(tmp_path, binding)


def test_compatible_emulator_loader_uses_frozen_config(tmp_path: Path) -> None:
    fixture = ROOT / "software/ai/sim/evidence/first_motion_controller_emulator_v1.json"
    loaded = load_compatible_emulator_fixture(fixture, workspace=ROOT)

    assert loaded["scope"] == "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
    assert loaded["fixture_sha256"]


def test_compatible_first_motion_loader_uses_frozen_config() -> None:
    fixture = ROOT / "software/ai/sim/evidence/first_motion_readiness_v1.json"
    loaded = load_compatible_first_motion_fixture(fixture, workspace=ROOT)

    assert loaded["scope"] == "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
    assert loaded["fixture_sha256"]
