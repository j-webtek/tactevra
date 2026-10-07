from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.typing_twin_contact_transform_differential_v1 import (  # noqa: E402
    _load_fixture,
    run_contact_transform_differential,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
FIXTURE = (
    ROOT
    / "ai/sim/evidence/typing_twin_contact_transform_differential_fixture_v1.json"
)
RESULT = (
    ROOT
    / "ai/sim/evidence/typing_twin_contact_transform_differential_result_v1.json"
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def test_fixture_freezes_exact_two_case_zero_authority_differential() -> None:
    fixture = _load_fixture(FIXTURE, WORKSPACE)
    assert fixture["claim_commit"] == "88b6107afc23d935d6eca85c3462e3ab1e6d7750"
    assert not any(fixture["counters"].values())
    assert fixture["transform_cases"] == [
        "NOMINAL_SYSTEM_MANIFEST",
        "PROMOTED_VIRTUAL_COMMISSIONING_OVERLAY",
    ]
    assert fixture["reconstruction"] == {
        "maximum_hover_clearance_mm": 25.0,
        "tool_length_mm": 120.0,
        "vertical_step_mm": 1.0,
    }
    assert fixture["decision_rules"]["profile_point_count_exact"] == 26
    assert fixture["decision_rules"]["full_route_runs_only_after_promoted_pass"]


def test_fixture_binds_promoted_profile_identity_and_bytes() -> None:
    fixture = _load_fixture(FIXTURE, WORKSPACE)
    assert fixture["promoted_profile"] == {
        "profile_id": "ROCELL-VIRTUAL-COMMISSIONING-RANK1-001",
        "source_sha256": "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634",
        "study_input_id": "reach-944d7463f4c67905",
    }


def test_fixture_tampering_fails_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["reconstruction"]["tool_length_mm"] = 130.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash"):
        _load_fixture(changed, WORKSPACE)

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document.pop("fixture_sha256")
    document["input_bindings"]["virtual_commissioning_profile"]["sha256"] = "0" * 64
    document["fixture_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    rebound = tmp_path / "rebound.json"
    rebound.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="bound source hash changed"):
        _load_fixture(rebound, WORKSPACE)


def test_result_reproduces_exactly_when_present() -> None:
    if not RESULT.is_file():
        pytest.skip("result remains unopened during fixture freeze")
    retained = json.loads(RESULT.read_text(encoding="utf-8"))
    replayed = run_contact_transform_differential(FIXTURE, workspace=WORKSPACE)
    assert replayed == retained
    assert [case["case_id"] for case in replayed["cases"]] == [
        "NOMINAL_SYSTEM_MANIFEST",
        "PROMOTED_VIRTUAL_COMMISSIONING_OVERLAY",
    ]
    assert replayed["hardware_writes"] == replayed["physical_movements"] == 0
    assert replayed["physical_authority"] is False
