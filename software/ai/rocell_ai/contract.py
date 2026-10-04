"""Runtime validation for the committed task proposal and adapter result schemas."""

from __future__ import annotations

import re
from typing import Any

from . import SCHEMA_ID
from rocell.models.actions import MAX_PLAN_TEXT_CHARS, MAX_PLAN_TEXT_BYTES


_SHARED = {"schema", "request_id", "observation_ref", "decision"}
_SHAPES = {
    "type_text": _SHARED | {"device", "text"},
    "clarify": _SHARED | {"reason"},
    "unsupported": _SHARED | {"reason"},
}
_REASONS = {
    "clarify": {"device_ambiguous", "text_ambiguous", "intent_ambiguous"},
    "unsupported": {"operation_not_available", "unsupported_by_profile", "stale_observation", "phone_state_unverified"},
}


def validate_proposal(value: Any) -> None:
    """Check the committed proposal schema without an extra dependency."""

    if not isinstance(value, dict):
        raise ValueError("proposal must be an object")
    decision = value.get("decision")
    if not isinstance(decision, str) or decision not in _SHAPES or set(value) != _SHAPES[decision]:
        raise ValueError("proposal has invalid fields")
    if value["schema"] != SCHEMA_ID:
        raise ValueError("proposal has invalid schema ID")
    for key in ("request_id", "observation_ref"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"{key} must be nonempty")
    if decision == "type_text":
        if not isinstance(value["device"], str) or value["device"] not in {"keyboard", "phone"}:
            raise ValueError("invalid device")
        if not isinstance(value["text"], str) or not value["text"]:
            raise ValueError("text must be nonempty")
        if (len(value["text"]) > MAX_PLAN_TEXT_CHARS
                or len(value["text"].encode("utf-8")) > MAX_PLAN_TEXT_BYTES):
            raise ValueError("text exceeds proposal input limit")
    elif not isinstance(value["reason"], str) or value["reason"] not in _REASONS[decision]:
        raise ValueError("invalid reason")


def validate_result(value: Any) -> None:
    if not isinstance(value, dict) or value.get("schema") != "rocell.ai_plan_result.v0":
        raise ValueError("invalid adapter result schema")
    if value.get("status") == "accepted":
        expected = {"schema", "request_id", "observation_ref", "status", "profile_id", "plan_hash", "action_plan"}
        if set(value) != expected or not isinstance(value["action_plan"], dict):
            raise ValueError("invalid accepted result")
        if not isinstance(value["profile_id"], str) or not value["profile_id"]:
            raise ValueError("invalid profile ID")
        if not isinstance(value["plan_hash"], str) or re.fullmatch(r"[0-9a-f]{64}", value["plan_hash"]) is None:
            raise ValueError("invalid plan hash")
        if value["action_plan"].get("schema") != "rocell.action_plan.v1":
            raise ValueError("invalid RoCell action plan")
    elif value.get("status") == "blocked":
        if set(value) != {"schema", "request_id", "observation_ref", "status", "reason"}:
            raise ValueError("invalid blocked result")
    else:
        raise ValueError("invalid adapter result status")
