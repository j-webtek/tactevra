from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.analyze_residual_v5_4_power_sensitivity import build  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5_4.json"
AUDIT = AI_ROOT / "eval/residual_obstruction_v5_4_fixture_audit_v1.json"
V5_3 = AI_ROOT / "eval/residual_obstruction_v5_3_safety_gate_amendment_v1.json"


def test_power_sensitivity_is_bound_and_fail_closed() -> None:
    result = build(
        source_commit="1" * 40, fixture_path=FIXTURE, audit_path=AUDIT,
        v5_3_path=V5_3, trials=5000, seed=55401,
    )
    assert result["simulation"]["assumed_true_miss_rate"] == 0.01
    assert result["simulation"]["scene_count"] == 224
    assert result["pessimistic_joint_lower_bound"] < 0.90
    assert result["evaluation_render_authorized"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0


def test_wrong_fixture_binding_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["bundle_sha256"] = "0" * 64
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="audit does not bind fixture"):
        build(
            source_commit="1" * 40, fixture_path=altered, audit_path=AUDIT,
            v5_3_path=V5_3, trials=5000, seed=55401,
        )
