from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.offline_intent_shadow_runtime_v1 import (  # noqa: E402
    IntentShadowRuntimeV1Error,
    parse_intent_shadow_receipt_v1,
    run_intent_shadow_runtime_v1,
)


DIGEST = "a" * 64
SCHEMA_DIGEST = "b" * 64
MODEL = "fixture-classifier:latest"


def _classification(kind: str = "TYPE_TEXT", value: str = "KEYBOARD") -> str:
    payload = {"schema": "rocell.offline_intent_classification.v1", "intent_type": kind}
    payload[{"TYPE_TEXT": "device", "CLARIFY": "question", "REFUSE": "reason"}[kind]] = value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _run(
    *, request: str = 'Reproduce "Aa!!" unchanged using the attached hardware keyboard.',
    observation: dict[str, object] | None = None,
    response: str | None = None,
    resolver=None,
):
    calls: list[dict[str, object]] = []

    def generate(payload):
        calls.append(payload)
        return response if response is not None else _classification()

    result = run_intent_shadow_runtime_v1(
        request_id="shadow-001",
        request_text=request,
        observation=(
            {"fresh": True, "ref": "capture-001"}
            if observation is None
            else observation
        ),
        model=MODEL,
        expected_model_digest=DIGEST,
        decoder_schema_sha256=SCHEMA_DIGEST,
        generate=generate,
        resolve_model_digest=resolver or (lambda _model: DIGEST),
    )
    return result, calls


def test_keyboard_text_compiles_exact_order_repeats_and_punctuation() -> None:
    result, calls = _run()
    assert result["status"] == "SHADOW_ACTIONS_COMPILED"
    assert [row["target_id"] for row in result["compiled_semantic_actions"]] == [
        "SHIFT", "A", "A", "SHIFT", "1", "SHIFT", "1",
    ]
    assert result["composed_intent"]["text"] == "Aa!!"
    assert result["model_call_count"] == len(calls) == 1
    model_input = json.loads(calls[0]["messages"][1]["content"])
    assert model_input["observation"] == {"fresh": True}
    assert result["authority_counters"] == {
        "model_motion_batches": 0,
        "motion_adapter_calls": 0,
        "controller_commands": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    assert result["physical_authority"] is False
    assert parse_intent_shadow_receipt_v1(result) == result


def test_phone_text_compiles_only_from_verified_lower_state() -> None:
    result, _ = _run(
        request='Place "A!" exactly into the active phone text field.',
        observation={"fresh": True, "ref": "phone-1", "phone_state": "KEYBOARD_LOWER"},
        response=_classification(value="PHONE"),
    )
    assert result["semantic_action_count"] == 4
    assert result["compiled_semantic_actions"][0]["target_id"] == "key_shift"
    refused, calls = _run(
        request='Place "A!" exactly into the active phone text field.',
        observation={"fresh": True, "ref": "phone-2"},
        response=_classification(value="PHONE"),
    )
    assert calls == []
    assert refused["classification_source"] == "DETERMINISTIC_PHONE_STATE_GATE"
    assert refused["classification"]["reason"] == "phone_state_unverified"


def test_stale_observation_bypasses_model_and_is_non_actionable() -> None:
    result, calls = _run(observation={"fresh": False, "ref": "old"})
    assert calls == []
    assert result["classification_source"] == "DETERMINISTIC_FRESHNESS_GATE"
    assert result["classification"]["reason"] == "stale_observation"
    assert result["model_call_count"] == result["semantic_action_count"] == 0


def test_unverified_phone_typing_bypasses_model_and_is_non_actionable() -> None:
    result, calls = _run(
        request='Type "A!" on the phone before confirming its current key layer.',
        observation={"fresh": True, "ref": "phone-unverified"},
    )
    assert calls == []
    assert result["classification_source"] == "DETERMINISTIC_PHONE_STATE_GATE"
    assert result["classification"]["reason"] == "phone_state_unverified"
    assert result["model_call_count"] == result["semantic_action_count"] == 0
    assert parse_intent_shadow_receipt_v1(result) == result


def test_stale_phone_typing_uses_freshness_precedence() -> None:
    result, calls = _run(
        request='Enter "A!" using the active phone keyboard.',
        observation={"fresh": False, "ref": "stale-phone"},
    )
    assert calls == []
    assert result["classification_source"] == "DETERMINISTIC_FRESHNESS_GATE"
    assert result["classification"]["reason"] == "stale_observation"


def test_verified_phone_typing_still_uses_model() -> None:
    result, calls = _run(
        request='Enter "A!" using the active phone keyboard.',
        observation={"fresh": True, "ref": "phone-ok", "phone_state": "KEYBOARD_LOWER"},
        response=_classification(value="PHONE"),
    )
    assert len(calls) == result["model_call_count"] == 1
    assert result["classification_source"] == "LOCAL_MODEL"


@pytest.mark.parametrize("observation", [{}, {"fresh": "yes"}, {"fresh": 1}])
def test_missing_or_non_boolean_freshness_fails_closed(observation) -> None:
    with pytest.raises(IntentShadowRuntimeV1Error, match="explicit boolean"):
        _run(observation=observation)


def test_wrong_or_changing_model_identity_fails_closed() -> None:
    with pytest.raises(IntentShadowRuntimeV1Error, match="differs from expected"):
        _run(resolver=lambda _model: "c" * 64)
    identities = iter((DIGEST, "c" * 64))
    with pytest.raises(IntentShadowRuntimeV1Error, match="changed during"):
        _run(resolver=lambda _model: next(identities))


@pytest.mark.parametrize("response", ["not json", "{}", _classification("REFUSE", "unknown")])
def test_malformed_or_out_of_contract_classifier_output_fails_closed(response: str) -> None:
    with pytest.raises(IntentShadowRuntimeV1Error, match="classifier response is invalid"):
        _run(response=response)


def test_duplicate_classifier_field_fails_closed() -> None:
    response = (
        '{"schema":"rocell.offline_intent_classification.v1",'
        '"intent_type":"REFUSE","intent_type":"TYPE_TEXT","device":"KEYBOARD"}'
    )
    with pytest.raises(IntentShadowRuntimeV1Error, match="duplicate JSON field"):
        _run(response=response)


def test_ambiguous_text_never_compiles_even_if_model_says_actionable() -> None:
    result, _ = _run(request="Type something useful on the keyboard.")
    assert result["status"] == "SHADOW_NON_ACTIONABLE"
    assert result["composed_intent"]["question"] == "text_ambiguous"
    assert result["compiled_semantic_actions"] == []


def test_missing_or_mismatched_device_never_compiles_model_action() -> None:
    missing, _ = _run(request='Type "Aa!!" exactly.')
    assert missing["status"] == "SHADOW_NON_ACTIONABLE"
    assert missing["composed_intent"]["question"] == "device_ambiguous"
    assert missing["compiled_semantic_actions"] == []

    mismatched, _ = _run(
        request='Type "Aa!!" on the verified phone keyboard.',
        observation={"fresh": True, "ref": "phone-mismatch", "phone_state": "KEYBOARD_LOWER"},
        response=_classification(value="KEYBOARD"),
    )
    assert mismatched["status"] == "SHADOW_NON_ACTIONABLE"
    assert mismatched["composed_intent"]["question"] == "device_ambiguous"
    assert mismatched["compiled_semantic_actions"] == []


def test_unsupported_text_fails_before_any_motion_boundary() -> None:
    with pytest.raises(IntentShadowRuntimeV1Error, match="semantic compilation failed"):
        _run(request='Reproduce "snowman ☃" unchanged using the attached hardware keyboard.')


def test_non_actionable_classifier_output_has_no_semantic_actions() -> None:
    result, _ = _run(response=_classification("REFUSE", "operation_not_available"))
    assert result["status"] == "SHADOW_NON_ACTIONABLE"
    assert result["semantic_action_count"] == 0


def test_receipt_tampering_and_authority_changes_are_rejected() -> None:
    result, _ = _run()
    changed = copy.deepcopy(result)
    changed["compiled_semantic_actions"][0]["target_id"] = "B"
    with pytest.raises(IntentShadowRuntimeV1Error, match="receipt hash changed"):
        parse_intent_shadow_receipt_v1(changed)
    changed = copy.deepcopy(result)
    changed["authority_counters"]["hardware_writes"] = 1
    unsigned = {key: value for key, value in changed.items() if key != "receipt_sha256"}
    changed["receipt_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(IntentShadowRuntimeV1Error, match="zero-authority"):
        parse_intent_shadow_receipt_v1(changed)
    changed = copy.deepcopy(result)
    changed["classification_source"] = "DETERMINISTIC_PHONE_STATE_GATE"
    changed["model_call_count"] = 0
    unsigned = {key: value for key, value in changed.items() if key != "receipt_sha256"}
    changed["receipt_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(IntentShadowRuntimeV1Error, match="phone-state gate"):
        parse_intent_shadow_receipt_v1(changed)


def test_rehashed_semantic_action_tampering_is_rejected() -> None:
    result, _ = _run()
    changed = copy.deepcopy(result)
    changed["compiled_semantic_actions"][0]["target_id"] = "B"
    unsigned = {key: value for key, value in changed.items() if key != "receipt_sha256"}
    changed["receipt_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(IntentShadowRuntimeV1Error, match="differ from public intent"):
        parse_intent_shadow_receipt_v1(changed)


def test_runtime_source_has_no_motion_boundary_imports() -> None:
    source = (AI_DIR / "rocell_ai" / "offline_intent_shadow_runtime_v1.py").read_text()
    assert "offline_intent_to_motion" not in source
    assert "ModelMotionBatch" not in source
