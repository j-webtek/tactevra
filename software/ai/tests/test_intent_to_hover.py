from __future__ import annotations

from pathlib import Path

import pytest

from rocell.application.context import load_simulation_context
from rocell_ai.intent_to_hover import (
    _sha, adapt_fiducial_observation, compile_hover_request, load_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "ai/sim/evidence/intent_to_hover_v1.json"
CONTEXT_ROOT = Path(r"C:\MuJoCoWarp\evidence\issue190\intent_to_hover\context")


def _receipt(fixture: dict, targets) -> dict:
    now = 1_770_000_000_000
    value = {
        "schema": "tactevra.intent_to_hover_isaac_observation.v1",
        "fixture_sha256": fixture["fixture_sha256"],
        "visible_fiducial_ids": ["T0", "T1", "T2", "T3", "K0"],
        "tray_shift_mm": 0.0, "calibrated_at_epoch_ms": now,
        "captured_at_epoch_ms": now, "frame_id": "test-frame",
        "capture_id": "test-capture", "image_sha256": "1" * 64,
        "camera_identity_sha256": "2" * 64,
        "scene_observation_sha256": "3" * 64,
        "residual_obstruction_sha256": "4" * 64,
        "residual_scores": {**{f"clear_{key}": 0.0 for key in targets}, "obstructed_H": 1.0},
        "target_projections": [],
    }
    value["receipt_sha256"] = _sha(value)
    return value


def test_hover_intent_is_bounded_and_preserves_named_target() -> None:
    context = load_simulation_context(
        CONTEXT_ROOT, CONTEXT_ROOT / "software/config/system_manifest.json"
    )
    proposal, plan = compile_hover_request(
        "Hover over H", request_id="r1", observation_ref="frame",
        commissioned_targets=context.targets.keyboard_targets,
        profile_id=context.targets.keyboard_semantic_profile_id,
    )
    assert proposal["decision"] == "hover_target"
    assert proposal["target_id"] == "H"
    assert plan.actions[0].key_id == "H"
    with pytest.raises(ValueError, match="unknown commissioned"):
        compile_hover_request(
            "Move to UNKNOWNKEY", request_id="r2", observation_ref="frame",
            commissioned_targets=context.targets.keyboard_targets,
            profile_id=context.targets.keyboard_semantic_profile_id,
        )


def test_fiducial_adapter_accepts_fresh_and_rejects_faults() -> None:
    fixture = load_fixture(FIXTURE, workspace=ROOT.parent)
    context = load_simulation_context(
        CONTEXT_ROOT, CONTEXT_ROOT / "software/config/system_manifest.json"
    )
    receipt = _receipt(fixture, context.targets.keyboard_targets)
    result = adapt_fiducial_observation(
        fixture, receipt, target_ids=("H",), catalog=context.targets,
        now_epoch_ms=receipt["captured_at_epoch_ms"] + 100,
    )
    assert result.qualification["scope"] == "SYNTHETIC_OFFLINE_ONLY"
    for field, replacement, error in (
        ("visible_fiducial_ids", ["T0", "T1", "T2", "K0"], "fiducial_occluded"),
        ("tray_shift_mm", 2.1, "tray_shifted"),
        ("calibrated_at_epoch_ms", receipt["captured_at_epoch_ms"] - 2001, "stale_calibration"),
    ):
        altered = {**receipt, field: replacement}
        altered.pop("receipt_sha256", None)
        altered["receipt_sha256"] = _sha(altered)
        with pytest.raises(ValueError, match=error):
            adapt_fiducial_observation(
                fixture, altered, target_ids=("H",), catalog=context.targets,
                now_epoch_ms=receipt["captured_at_epoch_ms"] + 100,
            )
