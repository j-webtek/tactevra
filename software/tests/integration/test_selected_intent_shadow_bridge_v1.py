from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(ROOT / "software/ai"),
    str(ROOT / "software/src"),
    str(ROOT / "software/tests/unit"),
    str(ROOT / "software/tests/integration"),
]

import test_shared_shadow_runner_v2 as shared_runner  # noqa: E402
from rocell_ai.offline_intent_shadow_runtime_v1 import (  # noqa: E402
    IntentShadowRuntimeV1Error,
)
from rocell_ai.selected_intent_shadow_bridge_v1 import (  # noqa: E402
    run_selected_intent_shadow_bridge_v1,
)


DIGEST = "a" * 64
MODEL = "fixture-classifier:latest"
SCHEMA_PATH = ROOT / "software/ai/schemas/offline_intent_classification_v1.schema.json"
SCHEMA_DIGEST = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()


def _classification(device: str = "KEYBOARD") -> str:
    return json.dumps(
        {
            "schema": "rocell.offline_intent_classification.v1",
            "intent_type": "TYPE_TEXT",
            "device": device,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _run(
    *,
    request: str = 'Type "hhi" on the keyboard.',
    observation: dict[str, object] | None = None,
    response: str | None = None,
    inputs: bool = True,
    digest: str = DIGEST,
):
    context, fixture = shared_runner._inputs()
    return run_selected_intent_shadow_bridge_v1(
        request_id="selected-shadow-001",
        request_text=request,
        observation=(
            {"fresh": True, "ref": "selected-scene-001"}
            if observation is None
            else observation
        ),
        model=MODEL,
        expected_model_digest=DIGEST,
        decoder_schema_sha256=SCHEMA_DIGEST,
        generate=lambda _payload: response or _classification(),
        resolve_model_digest=lambda _model: digest,
        context=context,
        inputs=fixture if inputs else None,
    )


def test_selected_model_preserves_repeats_through_batch_and_arm_shadow() -> None:
    result = _run()

    assert result["status"] == "BLOCKED_CALIBRATION_MISSING_OR_STALE"
    assert result["ordered_target_ids"] == ["H", "H", "I"]
    assert result["model_motion_batch_count"] == 1
    assert result["model_motion_batch_sha256"] is not None
    assert result["arm_shadow_trace_sha256"] is not None
    assert result["classification_source"] == "LOCAL_MODEL"
    assert result["motion_adapter_call_count"] == 0
    assert result["controller_command_count"] == 0
    assert result["hardware_write_count"] == 0
    assert result["physical_movement_count"] == 0
    assert result["physical_authority"] is False


def test_missing_qualified_perception_stops_before_batch_emission() -> None:
    result = _run(inputs=False)

    assert result["status"] == "QUALIFIED_PERCEPTION_REQUIRED"
    assert result["model_motion_batch_count"] == 0
    assert result["ordered_target_ids"] == []
    assert result["arm_shadow_trace_sha256"] is None
    assert result["physical_authority"] is False


def test_stale_observation_bypasses_model_and_remains_non_actionable() -> None:
    calls: list[object] = []
    context, fixture = shared_runner._inputs()
    result = run_selected_intent_shadow_bridge_v1(
        request_id="selected-shadow-stale",
        request_text='Type "hhi" on the keyboard.',
        observation={"fresh": False, "ref": "stale-scene"},
        model=MODEL,
        expected_model_digest=DIGEST,
        decoder_schema_sha256=SCHEMA_DIGEST,
        generate=lambda payload: calls.append(payload) or _classification(),
        resolve_model_digest=lambda _model: DIGEST,
        context=context,
        inputs=fixture,
    )

    assert calls == []
    assert result["status"] == "SHADOW_NON_ACTIONABLE"
    assert result["classification_source"] == "DETERMINISTIC_FRESHNESS_GATE"
    assert result["model_motion_batch_count"] == 0


def test_phone_intent_stops_at_unavailable_motion_boundary() -> None:
    result = _run(
        request='Type "hhi" on the verified phone keyboard.',
        observation={
            "fresh": True,
            "ref": "phone-scene",
            "phone_state": "KEYBOARD_LOWER",
        },
        response=_classification("PHONE"),
    )

    assert result["status"] == "PHONE_MOTION_BOUNDARY_UNAVAILABLE"
    assert result["model_motion_batch_count"] == 0
    assert result["physical_authority"] is False


def test_wrong_selected_model_digest_fails_closed() -> None:
    with pytest.raises(IntentShadowRuntimeV1Error, match="differs from expected"):
        _run(digest="c" * 64)


def test_selection_manifest_pins_held_out_model_and_zero_authority() -> None:
    selected = json.loads(
        (ROOT / "software/ai/train/intent_classifier_v11_selected.json").read_text()
    )
    assert selected["model_digest"] == (
        "348514d04a26efc58552e1eb4395e298ca7bc6f1045fb1777a898acb8d75d207"
    )
    assert selected["scope"] == "OFFLINE_SHADOW_ONLY"
    assert selected["physical_authority"] is False
