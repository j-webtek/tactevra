from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell_ai.typing_twin_ik_route_study_v1 import (
    _candidate_seed,
    _load_fixture,
    run_route_study,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/typing_twin_ik_route_study_fixture_v1.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_rehashed(path: Path, document: dict[str, object]) -> None:
    document.pop("fixture_sha256", None)
    document["fixture_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def test_candidate_seed_is_deterministic_strictly_interior() -> None:
    bounds = {
        name: (-float(index + 1), float(index + 1))
        for index, name in enumerate(
            (
                "base_link_to_link1",
                "link1_to_link2",
                "link2_to_link3",
                "link3_to_link4",
                "link4_to_link5",
            )
        )
    }
    first = _candidate_seed(
        7, bounds, bases=(2, 3, 5, 7, 11),
        fraction_floor=0.05, fraction_ceiling=0.95,
    )
    repeated = _candidate_seed(
        7, bounds, bases=(2, 3, 5, 7, 11),
        fraction_floor=0.05, fraction_ceiling=0.95,
    )
    assert first == repeated
    assert all(bounds[name][0] < value < bounds[name][1] for name, value in first.items())


def test_fixture_rejects_unhashed_change(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["halton_candidate_count"] = 1
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash changed"):
        _load_fixture(altered, ROOT)


def test_one_candidate_smoke_preserves_route_and_zero_authority(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["halton_candidate_count"] = 1
    document["decision_rules"]["candidate_count_exact"] = 1
    document["resource_limits"]["maximum_candidates"] = 1
    smoke = tmp_path / "smoke.json"
    _write_rehashed(smoke, document)

    result = run_route_study(smoke, workspace=ROOT)

    assert result["ordered_targets"] == ["H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6"]
    assert result["trajectory_sample_count"] == 260
    assert result["baseline_control"]["evaluated_sample_count"] == 16
    assert result["baseline_control"]["failure_reason"] == "MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED"
    assert len(result["candidate_generation"]) == 1
    assert result["controller_commands"] == []
    assert result["hardware_commands_generated"] == 0
    assert result["hardware_writes"] == 0
    assert result["physical_movements"] == 0
    assert result["physical_authority"] is False


def test_rehashed_candidate_count_mismatch_fails_closed(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["search"]["halton_candidate_count"] = 1
    mismatched = tmp_path / "mismatched.json"
    _write_rehashed(mismatched, document)
    with pytest.raises(ValueError, match="search bounds differ"):
        run_route_study(mismatched, workspace=ROOT)
