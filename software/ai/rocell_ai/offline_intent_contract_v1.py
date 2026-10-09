"""Motion-free contracts for offline intent classification and composition."""

from __future__ import annotations

import hashlib
import re
from typing import Any


CLASSIFICATION_SCHEMA = "rocell.offline_intent_classification.v1"
PUBLIC_SCHEMA = "rocell.offline_typing_intent.v1"
SYSTEM_PROMPT = """Classify one request into exactly one JSON object. Do not reproduce or transform requested text. Return no commentary.

Allowed objects:
{"schema":"rocell.offline_intent_classification.v1","intent_type":"TYPE_TEXT","device":"KEYBOARD|PHONE"}
{"schema":"rocell.offline_intent_classification.v1","intent_type":"CLARIFY","question":"device_ambiguous|text_ambiguous|intent_ambiguous"}
{"schema":"rocell.offline_intent_classification.v1","intent_type":"REFUSE","reason":"operation_not_available|unsupported_by_profile|stale_observation|phone_state_unverified"}

Typing requires an identified device and unambiguous exact text. Stale observations are refused. Phone typing requires verified KEYBOARD_LOWER state. Calling, dialing, sending, opening apps, and multi-step workflows are refused. Never emit text, coordinates, keys, motion, joints, commands, or execution claims."""
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()

_UNQUOTED_TYPE_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"Type (?P<text>[!-~]+) on the keyboard\.",
    r"Enter (?P<text>[!-~]+) using the physical keyboard\.",
    r"The keyboard should receive the word (?P<text>[!-~]+)\.",
    r"Use the physical keys to write (?P<text>[!-~]+)\.",
    r"Write (?P<text>[!-~]+) with the physical keyboard\.",
    r"Use keyboard keys to enter (?P<text>[!-~]+)\.",
    r"Produce (?P<text>[!-~]+) using the attached keyboard\.",
    r"The attached physical keyboard should spell (?P<text>[!-~]+)\.",
    r"The hardware keys must enter (?P<text>[!-~]+)\.",
    r"Input (?P<text>[!-~]+) through the attached keyboard\.",
    r"The physical keyboard must enter (?P<text>[!-~]+)\.",
    r"Key in (?P<text>[!-~]+) on the attached keyboard\.",
    r"The attached keyboard must input (?P<text>[!-~]+)\.",
    r"On the physical keyboard, enter (?P<text>[!-~]+)\.",
    r"The hardware keyboard should input (?P<text>[!-~]+)\.",
    r"Enter token (?P<text>[!-~]+) through the hardware keyboard\.",
    r"Have the attached keys enter (?P<text>[!-~]+)\.",
    r"Input token (?P<text>[!-~]+) with the hardware keyboard\.",
    r"The physical keyboard should write (?P<text>[!-~]+)\.",
    r"Use the hardware keys to input (?P<text>[!-~]+)\."
))
_PHONE_TYPING_REQUEST = re.compile(
    r"(?:\b(?:type|typing|enter|input|put|place|write)\b.{0,160}"
    r"\b(?:phone|handset|on-screen keyboard)\b|"
    r"\b(?:phone|handset|on-screen keyboard)\b.{0,160}"
    r"\b(?:type|typing|enter|input|put|place|write)\b)",
    re.IGNORECASE,
)
_QUOTED_PAYLOAD = re.compile(r'"[^"\r\n]*"')
_PHONE_DEVICE = re.compile(r"\b(?:phone|handset|on-screen)\b", re.IGNORECASE)
_KEYBOARD_DEVICE = re.compile(
    r"\b(?:keyboard|keyboarding|physical[- ]keys?|hardware[- ]keys?|"
    r"attached keys?|connected keys?|the keys|key|keying)\b",
    re.IGNORECASE,
)
_EXPLICIT_PHYSICAL_KEYBOARD = re.compile(
    r"\b(?:physical|hardware|attached|connected)\s+keyboard\b|"
    r"\b(?:physical|hardware|attached|connected)[- ]keys?\b",
    re.IGNORECASE,
)
_AMBIGUOUS_TOKEN = r"[A-Za-z0-9][A-Za-z0-9._~!@#$%^&*+=:?/\\-]{0,255}"
_UNQUOTED_TEXT_AMBIGUITY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"\bbetween\s+(?P<a>{_AMBIGUOUS_TOKEN})\s+and\s+(?P<b>{_AMBIGUOUS_TOKEN})\b",
        rf"(?P<a>{_AMBIGUOUS_TOKEN})\s+versus\s+(?P<b>{_AMBIGUOUS_TOKEN})\b",
        rf"(?:clarify|confirm|resolve|unclear|intended|which exact|string is intended)"
        rf"[^\r\n]{{0,160}}?\b(?P<a>{_AMBIGUOUS_TOKEN})\s+or\s+"
        rf"(?P<b>{_AMBIGUOUS_TOKEN})\b",
        rf"candidate strings conflict:\s*(?P<a>{_AMBIGUOUS_TOKEN})\s*,\s*"
        rf"(?P<b>{_AMBIGUOUS_TOKEN})\b",
        rf"(?:conflicting[^\r\n]{{0,80}}strings were supplied,)\s*"
        rf"(?P<a>{_AMBIGUOUS_TOKEN})\s+and\s+"
        rf"(?P<b>{_AMBIGUOUS_TOKEN})\b",
        rf"\bcould be\s+(?P<a>{_AMBIGUOUS_TOKEN})\s*;[^\r\n]{{0,80}}?"
        rf"\binstead be\s+(?P<b>{_AMBIGUOUS_TOKEN})\b",
    )
)


def extract_requested_text_v1(request_text: str) -> str | None:
    """Extract exact text only from the closed, unambiguous request grammar."""

    if not isinstance(request_text, str):
        return None
    quoted = re.findall(r'"([^"\r\n]+)"', request_text)
    if len(quoted) == 1:
        return quoted[0]
    if quoted:
        return None
    for pattern in _UNQUOTED_TYPE_PATTERNS:
        match = pattern.fullmatch(request_text)
        if match is not None:
            return match.group("text")
    return None


def extract_requested_device_v1(request_text: str) -> str | None:
    """Bind one device from instruction bytes outside the requested payload."""

    if not isinstance(request_text, str):
        return None
    instruction = _QUOTED_PAYLOAD.sub('""', request_text)
    phone = _PHONE_DEVICE.search(instruction) is not None
    keyboard = _KEYBOARD_DEVICE.search(instruction) is not None
    if phone and not _EXPLICIT_PHYSICAL_KEYBOARD.search(instruction):
        # In phone requests, an unqualified "keyboard" names the on-screen
        # keyboard. Only an explicitly physical keyboard creates a conflict.
        keyboard = False
    if phone == keyboard:
        return None
    return "PHONE" if phone else "KEYBOARD"


def parse_classification_v1(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or value.get("schema") != CLASSIFICATION_SCHEMA:
        raise ValueError("invalid classification schema")
    kind = value.get("intent_type")
    variants = {
        "TYPE_TEXT": ({"schema", "intent_type", "device"}, "device", {"KEYBOARD", "PHONE"}),
        "CLARIFY": ({"schema", "intent_type", "question"}, "question", {"device_ambiguous", "text_ambiguous", "intent_ambiguous"}),
        "REFUSE": ({"schema", "intent_type", "reason"}, "reason", {"operation_not_available", "unsupported_by_profile", "stale_observation", "phone_state_unverified"}),
    }
    if kind not in variants:
        raise ValueError("invalid classification intent_type")
    fields, payload_field, allowed = variants[kind]
    if set(value) != fields or value[payload_field] not in allowed:
        raise ValueError("invalid classification fields")
    return dict(value)


def compose_public_intent_v1(
    classification: dict[str, str], request_text: str, *,
    require_requested_device: bool = True,
) -> dict[str, str]:
    parsed = parse_classification_v1(classification)
    kind = parsed["intent_type"]
    if kind == "TYPE_TEXT":
        text = extract_requested_text_v1(request_text)
        if text is None:
            return {
                "schema": PUBLIC_SCHEMA,
                "intent_type": "CLARIFY",
                "question": "text_ambiguous",
            }
        if require_requested_device:
            requested_device = extract_requested_device_v1(request_text)
            if requested_device is None or requested_device != parsed["device"]:
                return {
                    "schema": PUBLIC_SCHEMA,
                    "intent_type": "CLARIFY",
                    "question": "device_ambiguous",
                }
        return {
            "schema": PUBLIC_SCHEMA,
            "intent_type": kind,
            "device": parsed["device"],
            "text": text,
        }
    if kind == "CLARIFY":
        return {
            "schema": PUBLIC_SCHEMA,
            "intent_type": kind,
            "question": parsed["question"],
        }
    return {
        "schema": PUBLIC_SCHEMA,
        "intent_type": kind,
        "reason": parsed["reason"],
    }


def parse_public_intent_v1(value: Any) -> dict[str, str]:
    """Validate the closed public intent without importing the motion adapter."""

    if not isinstance(value, dict) or value.get("schema") != PUBLIC_SCHEMA:
        raise ValueError("invalid public intent schema")
    kind = value.get("intent_type")
    variants = {
        "TYPE_TEXT": ({"schema", "intent_type", "device", "text"}, "text"),
        "PRESS_KEY": ({"schema", "intent_type", "device", "key"}, "key"),
        "CLARIFY": ({"schema", "intent_type", "question"}, "question"),
        "REFUSE": ({"schema", "intent_type", "reason"}, "reason"),
    }
    if kind not in variants:
        raise ValueError("invalid public intent type")
    fields, payload = variants[kind]
    if set(value) != fields:
        raise ValueError("invalid public intent fields")
    if kind in {"TYPE_TEXT", "PRESS_KEY"} and value.get("device") not in {
        "KEYBOARD", "PHONE",
    }:
        raise ValueError("invalid public intent device")
    if kind == "PRESS_KEY" and value["device"] != "KEYBOARD":
        raise ValueError("PRESS_KEY supports only KEYBOARD")
    maximum = 256 if kind == "TYPE_TEXT" else 32 if kind == "PRESS_KEY" else 512
    if not isinstance(value[payload], str) or not value[payload] or len(value[payload]) > maximum:
        raise ValueError(f"invalid public intent {payload}")
    return dict(value)


def deterministic_freshness_classification_v1(
    observation: Any,
) -> dict[str, str] | None:
    """Refuse explicit stale evidence before model inference; validate the bit."""

    if not isinstance(observation, dict) or type(observation.get("fresh")) is not bool:
        raise ValueError("observation fresh must be an explicit boolean")
    if observation["fresh"]:
        return None
    return {
        "schema": CLASSIFICATION_SCHEMA,
        "intent_type": "REFUSE",
        "reason": "stale_observation",
    }


def deterministic_phone_state_classification_v1(
    request_text: Any, observation: Any,
) -> dict[str, str] | None:
    """Refuse explicit phone typing unless the bounded input state is verified."""

    deterministic_freshness_classification_v1(observation)
    if not isinstance(request_text, str):
        raise ValueError("request text must be a string")
    if _PHONE_TYPING_REQUEST.search(request_text) is None:
        return None
    if observation.get("phone_state") == "KEYBOARD_LOWER":
        return None
    return {
        "schema": CLASSIFICATION_SCHEMA,
        "intent_type": "REFUSE",
        "reason": "phone_state_unverified",
    }


def deterministic_text_ambiguity_classification_v1(
    request_text: Any,
) -> dict[str, str] | None:
    """Clarify requests that name two distinct payloads in the closed grammar."""

    if not isinstance(request_text, str):
        raise ValueError("request text must be a string")
    quoted = re.findall(r'"([^"\r\n]+)"', request_text)
    if quoted:
        ambiguous = len(set(quoted)) >= 2
    else:
        ambiguous = False
        for pattern in _UNQUOTED_TEXT_AMBIGUITY_PATTERNS:
            match = pattern.search(request_text)
            if match is not None and match.group("a") != match.group("b"):
                ambiguous = True
                break
    if not ambiguous:
        return None
    return {
        "schema": CLASSIFICATION_SCHEMA,
        "intent_type": "CLARIFY",
        "question": "text_ambiguous",
    }


def classifier_model_observation_v1(observation: Any) -> dict[str, Any]:
    """Expose only decision-relevant observation state to the language model."""

    deterministic_freshness_classification_v1(observation)
    sanitized: dict[str, Any] = {"fresh": observation["fresh"]}
    if "phone_state" in observation:
        phone_state = observation["phone_state"]
        if not isinstance(phone_state, str) or not phone_state or len(phone_state) > 64:
            raise ValueError("observation phone_state must be a bounded string")
        sanitized["phone_state"] = phone_state
    return sanitized


__all__ = [
    "CLASSIFICATION_SCHEMA",
    "PROMPT_SHA256",
    "PUBLIC_SCHEMA",
    "SYSTEM_PROMPT",
    "compose_public_intent_v1",
    "classifier_model_observation_v1",
    "deterministic_freshness_classification_v1",
    "deterministic_phone_state_classification_v1",
    "deterministic_text_ambiguity_classification_v1",
    "extract_requested_device_v1",
    "extract_requested_text_v1",
    "parse_classification_v1",
    "parse_public_intent_v1",
]
