from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell.models import (  # noqa: E402
    ModelMotionBatchV2Error,
    decode_model_motion_batch_v2_json,
)
from rocell.application.context import load_simulation_context  # noqa: E402
from rocell_ai.actual_output_compatibility_v1 import (  # noqa: E402
    build_actual_emitter_payload,
)
from rocell_ai.typing_twin_boundary_v1 import (  # noqa: E402
    _compile_installed,
    _load_boundary_fixture,
    run_boundary_sweep,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "ai/sim/evidence/end_to_end_typing_twin_boundary_main_v1_1.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def test_fixture_is_frozen_and_zero_authority() -> None:
    fixture = _load_boundary_fixture(FIXTURE)
    assert fixture["fixture_sha256"] == (
        "44d504496063ccfc6103429dd56ad2dce5eb97fbf99eac0cb1c36b20ca54a964"
    )
    assert not any(fixture["counters"].values())
    assert fixture["limits"]["collision_screening_in_this_increment"] is False


def test_semantic_order_and_uncommissioned_shift_fail_closed() -> None:
    installed = tuple(load_simulation_context(
        ROOT.parent, ROOT / "config/system_manifest.json",
    ).targets.keyboard_targets)
    assert _compile_installed("hello 2026", installed) == (
        "H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6",
    )
    with pytest.raises(ValueError, match="SHIFT"):
        _compile_installed("Hello 2026!", installed)


def test_boundary_sweep_is_repeatable_ordered_and_zero_authority() -> None:
    first = run_boundary_sweep(FIXTURE, workspace=ROOT.parent)
    second = run_boundary_sweep(FIXTURE, workspace=ROOT.parent)
    assert first == second
    assert first["decision"] == "PASS_STRICT_BOUNDARY_AND_TRAJECTORY_PARTIAL_WORKSTREAM"
    assert first["combination_count"] == 81
    assert first["strict_decode_pass_count"] == 81
    assert first["trusted_registry_ingress_pass_count"] == 81
    assert first["trajectory_build_pass_count"] == 81
    assert first["target_order_difference_count"] == 0
    assert first["ordered_targets"] == [
        "H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6",
    ]
    assert first["blocked_missing_target"]["status"] == "BLOCK_BEFORE_BATCH"
    assert first["controller_commands"] == []
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False
    assert first["collision_screening_executed"] is False


def test_fixture_and_source_binding_tampering_are_rejected(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["expected_combination_count"] = 80
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash"):
        _load_boundary_fixture(changed)

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture.pop("fixture_sha256")
    fixture["input_bindings"]["system_manifest"]["sha256"] = "0" * 64
    fixture["fixture_sha256"] = hashlib.sha256(_canonical(fixture)).hexdigest()
    rebound = tmp_path / "rebound.json"
    rebound.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="bound source hash changed"):
        run_boundary_sweep(rebound, workspace=ROOT.parent)


def test_authority_field_injection_is_rejected_by_strict_decoder() -> None:
    payload = build_actual_emitter_payload(
        ROOT.parent,
        text="hello 2026",
        targets=("H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6"),
        batch_id="typing-twin-boundary-test",
        request_id="typing-twin-boundary-test",
    )
    document = json.loads(payload)
    document["hardware_access"] = True
    with pytest.raises(ModelMotionBatchV2Error, match="zero authority"):
        decode_model_motion_batch_v2_json(_canonical(document))
