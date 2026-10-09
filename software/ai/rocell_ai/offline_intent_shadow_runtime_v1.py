"""Disconnected intent-to-semantic-action shadow runtime with zero authority."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib import request as urllib_request

from .end_to_end_typing_twin import (
    VirtualKeyboardStateError,
    compile_virtual_phone,
    compile_virtual_us_sticky_keys,
)
from .offline_intent_contract_v1 import (
    PROMPT_SHA256,
    SYSTEM_PROMPT,
    classifier_model_observation_v1,
    compose_public_intent_v1,
    deterministic_device_ambiguity_classification_v1,
    deterministic_freshness_classification_v1,
    deterministic_phone_state_classification_v1,
    deterministic_text_ambiguity_classification_v1,
    parse_classification_v1,
    parse_public_intent_v1,
)


SCHEMA = "tactevra.offline_intent_shadow_runtime.v1"
SCOPE = "DISCONNECTED_SEMANTIC_SHADOW_ZERO_AUTHORITY"
OLLAMA_URL = "http://127.0.0.1:11434"
_DIGEST = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_COUNTERS = {
    "model_motion_batches": 0,
    "motion_adapter_calls": 0,
    "controller_commands": 0,
    "hardware_writes": 0,
    "physical_movements": 0,
}


class IntentShadowRuntimeV1Error(ValueError):
    """The disconnected classifier or semantic compiler failed closed."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntentShadowRuntimeV1Error(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _strict_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_strict_object)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise IntentShadowRuntimeV1Error(f"{label} must be a lowercase SHA-256")
    return value


def _validate_input(
    request_id: str, request_text: str, observation: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(request_id, str) or _IDENTIFIER.fullmatch(request_id) is None:
        raise IntentShadowRuntimeV1Error("request_id is invalid")
    if not isinstance(request_text, str) or not request_text or len(request_text) > 8192:
        raise IntentShadowRuntimeV1Error("request must contain 1 through 8192 characters")
    if not isinstance(observation, Mapping):
        raise IntentShadowRuntimeV1Error("observation must be an object")
    normalized = dict(observation)
    try:
        encoded = _canonical(normalized)
    except (TypeError, ValueError) as exc:
        raise IntentShadowRuntimeV1Error("observation is not canonical JSON") from exc
    if len(encoded) > 16384:
        raise IntentShadowRuntimeV1Error("observation exceeds 16384 canonical bytes")
    try:
        deterministic_freshness_classification_v1(normalized)
    except ValueError as exc:
        raise IntentShadowRuntimeV1Error(str(exc)) from exc
    return normalized


def _compile_actions(intent: Mapping[str, str], observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    if intent["intent_type"] != "TYPE_TEXT":
        return []
    text = intent["text"]
    try:
        if intent["device"] == "KEYBOARD":
            targets = compile_virtual_us_sticky_keys(text)
            return [
                {"ordinal": ordinal, "kind": "PRESS_TARGET", "target_id": target}
                for ordinal, target in enumerate(targets)
            ]
        if observation.get("phone_state") != "KEYBOARD_LOWER":
            raise IntentShadowRuntimeV1Error(
                "phone TYPE_TEXT requires an explicitly verified KEYBOARD_LOWER state"
            )
        return [
            {"ordinal": ordinal, **action}
            for ordinal, action in enumerate(compile_virtual_phone(text))
        ]
    except (ValueError, VirtualKeyboardStateError) as exc:
        if isinstance(exc, IntentShadowRuntimeV1Error):
            raise
        raise IntentShadowRuntimeV1Error(f"semantic compilation failed: {exc}") from exc


def run_intent_shadow_runtime_v1(
    *,
    request_id: str,
    request_text: str,
    observation: Mapping[str, Any],
    model: str,
    expected_model_digest: str,
    decoder_schema_sha256: str,
    generate: Callable[[dict[str, Any]], str],
    resolve_model_digest: Callable[[str], str],
) -> dict[str, Any]:
    """Classify and compile semantic actions without importing a motion adapter."""

    normalized_observation = _validate_input(request_id, request_text, observation)
    expected_digest = _validate_digest(expected_model_digest, "expected_model_digest")
    schema_digest = _validate_digest(decoder_schema_sha256, "decoder_schema_sha256")
    installed_digest = _validate_digest(resolve_model_digest(model), "installed_model_digest")
    if installed_digest != expected_digest:
        raise IntentShadowRuntimeV1Error("installed model digest differs from expected identity")

    gated = deterministic_freshness_classification_v1(normalized_observation)
    source = "DETERMINISTIC_FRESHNESS_GATE"
    if gated is None:
        gated = deterministic_phone_state_classification_v1(
            request_text, normalized_observation,
        )
        source = "DETERMINISTIC_PHONE_STATE_GATE"
    if gated is None:
        gated = deterministic_text_ambiguity_classification_v1(request_text)
        source = "DETERMINISTIC_TEXT_AMBIGUITY_GATE"
    if gated is None:
        gated = deterministic_device_ambiguity_classification_v1(request_text)
        source = "DETERMINISTIC_DEVICE_AMBIGUITY_GATE"
    model_calls = 0
    if gated is None:
        model_observation = classifier_model_observation_v1(normalized_observation)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"request": request_text, "observation": model_observation},
                        ensure_ascii=False,
                    ),
                },
            ],
            "stream": False,
            "options": {"temperature": 0, "seed": 1, "num_predict": 96, "num_ctx": 4096},
        }
        raw = generate(payload)
        model_calls = 1
        source = "LOCAL_MODEL"
    else:
        raw = _canonical(gated).decode("ascii")
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 4096:
        raise IntentShadowRuntimeV1Error("classifier response is not a bounded string")
    try:
        classification = parse_classification_v1(_strict_json(raw))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise IntentShadowRuntimeV1Error(f"classifier response is invalid: {exc}") from exc
    composed = compose_public_intent_v1(classification, request_text)
    actions = _compile_actions(composed, normalized_observation)
    if _validate_digest(resolve_model_digest(model), "final_model_digest") != installed_digest:
        raise IntentShadowRuntimeV1Error("model identity changed during the shadow run")

    core = {
        "schema": SCHEMA,
        "status": "SHADOW_ACTIONS_COMPILED" if actions else "SHADOW_NON_ACTIONABLE",
        "scope": SCOPE,
        "request_id": request_id,
        "request_sha256": hashlib.sha256(request_text.encode("utf-8")).hexdigest(),
        "observation_sha256": _sha(normalized_observation),
        "model_observation_sha256": _sha(
            classifier_model_observation_v1(normalized_observation)
        ),
        "model": model,
        "model_digest": installed_digest,
        "prompt_sha256": PROMPT_SHA256,
        "decoder_schema_sha256": schema_digest,
        "implementation_sha256": _file_sha(Path(__file__)),
        "classification_source": source,
        "classifier_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "classification": classification,
        "composed_intent": composed,
        "compiled_semantic_actions": actions,
        "semantic_action_count": len(actions),
        "model_call_count": model_calls,
        "authority_counters": dict(_COUNTERS),
        "physical_authority": False,
    }
    result = {**core, "receipt_sha256": _sha(core)}
    parse_intent_shadow_receipt_v1(result)
    return result


def parse_intent_shadow_receipt_v1(document: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly validate the hash-bound zero-authority shadow receipt."""

    fields = {
        "schema", "status", "scope", "request_id", "request_sha256",
        "observation_sha256", "model_observation_sha256", "model", "model_digest", "prompt_sha256",
        "decoder_schema_sha256", "implementation_sha256", "classification_source",
        "classifier_response_sha256", "classification", "composed_intent",
        "compiled_semantic_actions", "semantic_action_count", "model_call_count",
        "authority_counters", "physical_authority", "receipt_sha256",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise IntentShadowRuntimeV1Error("receipt fields differ from contract")
    unsigned = {key: value for key, value in document.items() if key != "receipt_sha256"}
    if _validate_digest(document["receipt_sha256"], "receipt_sha256") != _sha(unsigned):
        raise IntentShadowRuntimeV1Error("receipt hash changed")
    if document["schema"] != SCHEMA or document["scope"] != SCOPE:
        raise IntentShadowRuntimeV1Error("receipt identity changed")
    classification = parse_classification_v1(document["classification"])
    try:
        composed = parse_public_intent_v1(document["composed_intent"])
    except ValueError as exc:
        raise IntentShadowRuntimeV1Error(str(exc)) from exc
    actions = document["compiled_semantic_actions"]
    if not isinstance(actions, list) or document["semantic_action_count"] != len(actions):
        raise IntentShadowRuntimeV1Error("semantic action count changed")
    if [item.get("ordinal") for item in actions] != list(range(len(actions))):
        raise IntentShadowRuntimeV1Error("semantic action order changed")
    actionable = composed["intent_type"] == "TYPE_TEXT"
    expected_status = "SHADOW_ACTIONS_COMPILED" if actions else "SHADOW_NON_ACTIONABLE"
    if document["status"] != expected_status or actionable != bool(actions):
        raise IntentShadowRuntimeV1Error("receipt actionability changed")
    source_calls = {
        "LOCAL_MODEL": 1,
        "DETERMINISTIC_FRESHNESS_GATE": 0,
        "DETERMINISTIC_PHONE_STATE_GATE": 0,
        "DETERMINISTIC_TEXT_AMBIGUITY_GATE": 0,
        "DETERMINISTIC_DEVICE_AMBIGUITY_GATE": 0,
    }
    if document["classification_source"] not in source_calls:
        raise IntentShadowRuntimeV1Error("classification source changed")
    if document["model_call_count"] != source_calls[document["classification_source"]]:
        raise IntentShadowRuntimeV1Error("model call count changed")
    if document["classification_source"] == "DETERMINISTIC_FRESHNESS_GATE" and (
        classification.get("reason") != "stale_observation"
    ):
        raise IntentShadowRuntimeV1Error("freshness gate classification changed")
    if document["classification_source"] == "DETERMINISTIC_PHONE_STATE_GATE" and (
        classification.get("reason") != "phone_state_unverified"
    ):
        raise IntentShadowRuntimeV1Error("phone-state gate classification changed")
    if document["classification_source"] == "DETERMINISTIC_TEXT_AMBIGUITY_GATE" and (
        classification.get("question") != "text_ambiguous"
    ):
        raise IntentShadowRuntimeV1Error("text-ambiguity gate classification changed")
    if document["classification_source"] == "DETERMINISTIC_DEVICE_AMBIGUITY_GATE" and (
        classification.get("question") != "device_ambiguous"
    ):
        raise IntentShadowRuntimeV1Error("device-ambiguity gate classification changed")
    if classification["intent_type"] != "TYPE_TEXT" and composed != {
        **classification,
        "schema": "rocell.offline_typing_intent.v1",
    }:
        raise IntentShadowRuntimeV1Error("classification and public intent differ")
    if actionable:
        expected_actions = _compile_actions(
            composed,
            {"phone_state": "KEYBOARD_LOWER"},
        )
        if actions != expected_actions:
            raise IntentShadowRuntimeV1Error("semantic actions differ from public intent")
    if document["authority_counters"] != _COUNTERS or document["physical_authority"] is not False:
        raise IntentShadowRuntimeV1Error("receipt violates zero-authority boundary")
    for field in (
        "request_sha256", "observation_sha256", "model_observation_sha256", "model_digest", "prompt_sha256",
        "decoder_schema_sha256", "implementation_sha256", "classifier_response_sha256",
    ):
        _validate_digest(document[field], field)
    return dict(document)


def _installed_model_digest(model: str) -> str:
    with urllib_request.urlopen(OLLAMA_URL + "/api/tags", timeout=10) as response:
        models = json.load(response).get("models", [])
    matches = [item["digest"] for item in models if item.get("name") == model]
    if len(matches) != 1:
        raise IntentShadowRuntimeV1Error("model must match one installed Ollama identity")
    return matches[0]


def _ollama_generate(decoder_schema: dict[str, Any]) -> Callable[[dict[str, Any]], str]:
    def generate(payload: dict[str, Any]) -> str:
        body = {**payload, "format": decoder_schema}
        req = urllib_request.Request(
            OLLAMA_URL + "/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib_request.urlopen(req, timeout=120) as response:
            result = json.load(response)
        return result.get("message", {}).get("content", "")

    return generate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-digest", required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    input_document = _strict_json(args.input.read_text(encoding="utf-8"))
    if not isinstance(input_document, dict) or set(input_document) != {
        "request_id", "request", "observation",
    }:
        raise IntentShadowRuntimeV1Error("input fields differ from contract")
    schema_bytes = args.schema.read_bytes()
    decoder_schema = _strict_json(schema_bytes.decode("utf-8"))
    result = run_intent_shadow_runtime_v1(
        request_id=input_document["request_id"],
        request_text=input_document["request"],
        observation=input_document["observation"],
        model=args.model,
        expected_model_digest=args.model_digest,
        decoder_schema_sha256=hashlib.sha256(schema_bytes).hexdigest(),
        generate=_ollama_generate(decoder_schema),
        resolve_model_digest=_installed_model_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "classification_source": result["classification_source"],
        "semantic_action_count": result["semantic_action_count"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "IntentShadowRuntimeV1Error",
    "parse_intent_shadow_receipt_v1",
    "run_intent_shadow_runtime_v1",
]
