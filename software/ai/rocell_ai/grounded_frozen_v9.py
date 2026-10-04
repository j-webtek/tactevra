"""Model-independent, read-only extraction of one grounded typing intent.

This is a narrow grammar for an offline alternative architecture. It never
selects coordinates, calls a controller, or treats a model prediction as
evidence of the requested text or target device.
"""

from __future__ import annotations

import re
from typing import Any

from rocell.typing import UnsupportedCharacterError, compile_development_text

from . import SCHEMA_ID
from .contract import validate_proposal


_QUOTED = re.compile(r'"([^"\r\n]*)"')
_PHONE_KEYBOARD = re.compile(
    r"\b(?:cell\s+)?phone(?:'s)?(?:\s+(?:screen's\s+text|ready))?\s+keyboard\b", re.I,
)
_DEVICE = re.compile(r"\b(?:keyboard|cell\s+phone|phone)\b", re.I)
_UNAVAILABLE = re.compile(
    r"\b(?:call|dial|send|open|launch|tap|swipe|delete|submit|press|save|share|search|navigate|click|run|execute|upload|post|publish)\b", re.I,
)
_SEQUENCE = re.compile(r"\b(?:and|or|then|after|before|both|either|also)\b", re.I)
_NEGATION = re.compile(r"\b(?:not|never|don't|cannot|can't|without)\b", re.I)
_TYPING = re.compile(r"\b(?:type|enter|write|put|place|copy|transcribe)\b", re.I)
_UNQUOTED_SUFFIX = re.compile(
    r"^(?:please\s+)?(?:type|enter|write|put)\s+([a-z0-9]+)\s+(?:on|into|in|using|with)\s+"
    r"(?:the\s+)?(?:(?:physical\s+)?keyboard|(?:cell\s+)?phone(?:\s+keyboard)?)\.?$", re.I,
)
_UNQUOTED_PREFIX = re.compile(
    r"^(?:on|in|using|with)\s+(?:the\s+)?(?:(?:physical\s+)?keyboard|(?:cell\s+)?phone(?:\s+keyboard)?)"
    r"\s*[,;:]\s*(?:please\s+)?(?:type|enter|write|put)\s+([a-z0-9]+)\.?$", re.I,
)
_ALLOWED_OUTSIDE = frozenset({
    "a", "an", "as", "box", "can", "cell", "chosen", "copy", "could", "current",
    "editor", "enter", "exact", "exactly", "field", "for", "focused", "i", "in",
    "input", "into", "is", "it", "keyboard", "keyboard's", "keys", "literal",
    "my", "of", "on", "only", "phone", "phone's", "physical", "phrase", "place",
    "please", "put", "ready", "receive", "screen's", "selected", "should", "string",
    "text", "that", "the", "there", "this", "to", "transcribe", "type", "typed",
    "typing", "use", "using", "want", "with", "write", "you", "your",
})
_UNRESOLVED_TEXT = frozenset({"it", "that", "this", "something", "anything", "whatever", "one", "word", "text", "phrase"})


def _proposal(request_id: str, observation_ref: str, decision: str, **fields: str) -> dict[str, str]:
    value = {"schema": SCHEMA_ID, "request_id": request_id,
             "observation_ref": observation_ref, "decision": decision, **fields}
    validate_proposal(value)
    return value


def _devices(outside: str) -> set[str]:
    normalized = _PHONE_KEYBOARD.sub("phone", outside)
    return {"phone" if "phone" in match.group().casefold() else "keyboard"
            for match in _DEVICE.finditer(normalized)}


def propose(*, request_id: str, request: str, observation: dict[str, Any]) -> dict[str, str]:
    """Extract a one-device, exact-text proposal from fixture input only."""

    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must be nonempty")
    if not isinstance(request, str) or not isinstance(observation, dict):
        raise TypeError("request and observation are required")
    observation_ref = observation.get("ref")
    if not isinstance(observation_ref, str) or not observation_ref.strip():
        raise ValueError("observation.ref must be nonempty")

    def clarify(reason: str) -> dict[str, str]:
        return _proposal(request_id, observation_ref, "clarify", reason=reason)

    def unsupported(reason: str) -> dict[str, str]:
        return _proposal(request_id, observation_ref, "unsupported", reason=reason)

    if observation.get("fresh") is not True:
        return unsupported("stale_observation")
    raw = request.strip()
    quotes = _QUOTED.findall(raw)
    outside = _QUOTED.sub(" ", raw)
    # An already open editor is context; asking to open one remains unavailable.
    outside = re.sub(r"\bopen\s+editor\b", "editor", outside, flags=re.I)
    if _UNAVAILABLE.search(outside):
        return unsupported("operation_not_available")
    if raw.count('"') != 2 * len(quotes) or len(quotes) > 1:
        return clarify("text_ambiguous")
    devices = _devices(outside)
    if len(devices) != 1:
        return clarify("device_ambiguous")
    device = next(iter(devices))
    typing_verbs = _TYPING.findall(outside)
    if len(typing_verbs) != 1:
        return clarify("intent_ambiguous")
    if _SEQUENCE.search(outside) or _NEGATION.search(outside):
        return clarify("intent_ambiguous")
    if quotes:
        text = quotes[0]
        words = re.findall(r"[a-z]+(?:'[a-z]+)?", outside.casefold())
        if (not text or re.search(r"[^A-Za-z\s.,;:?!']", outside)
                or any(word not in _ALLOWED_OUTSIDE for word in words)):
            return clarify("intent_ambiguous" if text else "text_ambiguous")
    else:
        match = _UNQUOTED_SUFFIX.fullmatch(raw) or _UNQUOTED_PREFIX.fullmatch(raw)
        if match is None:
            return clarify("text_ambiguous")
        text = match.group(1)
        if text.casefold() in _UNRESOLVED_TEXT:
            return clarify("text_ambiguous")
    if device == "phone" and observation.get("phone_state") != "KEYBOARD_LOWER":
        return unsupported("phone_state_unverified")
    try:
        compile_development_text(device, text)
    except UnsupportedCharacterError:
        return unsupported("unsupported_by_profile")
    return _proposal(request_id, observation_ref, "type_text", device=device, text=text)
