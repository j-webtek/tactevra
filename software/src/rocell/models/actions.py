"""Semantic input actions that deliberately contain no robot coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from enum import Enum
import hashlib
import json
import re
from typing import Any, TypeAlias


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Device(str, Enum):
    KEYBOARD = "keyboard"
    PHONE = "phone"


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    result = value.strip()
    if any(ord(character) < 32 for character in result):
        raise ValueError(f"{name} contains a control character")
    return result


@dataclass(frozen=True, slots=True)
class PressKey:
    key_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", _identifier(self.key_id, "key_id"))

    def to_dict(self) -> dict[str, Any]:
        return {"type": "press_key", "key": self.key_id}


@dataclass(frozen=True, slots=True)
class TapPhoneTarget:
    target_id: str
    required_state: str
    resulting_state: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _identifier(self.target_id, "target_id"))
        object.__setattr__(self, "required_state", _identifier(self.required_state, "required_state"))
        if self.resulting_state is not None:
            object.__setattr__(
                self,
                "resulting_state",
                _identifier(self.resulting_state, "resulting_state"),
            )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "type": "tap_phone_target",
            "target": self.target_id,
            "required_state": self.required_state,
        }
        if self.resulting_state is not None:
            value["resulting_state"] = self.resulting_state
        return value


@dataclass(frozen=True, slots=True)
class VerifyPhoneState:
    state_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_id", _identifier(self.state_id, "state_id"))

    def to_dict(self) -> dict[str, Any]:
        return {"type": "verify_phone_state", "state": self.state_id}


SemanticAction: TypeAlias = PressKey | TapPhoneTarget | VerifyPhoneState
MAX_PLAN_TEXT_CHARS = 4096
MAX_PLAN_TEXT_BYTES = 16 * 1024
MAX_SEMANTIC_ACTIONS = 8192


@dataclass(frozen=True, slots=True)
class ActionPlan:
    device: Device
    profile_id: str
    requested_text_sha256: str
    actions: tuple[SemanticAction, ...]
    required_calibrations: tuple[str, ...]
    schema: str = "rocell.action_plan.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.device, Device):
            object.__setattr__(self, "device", Device(self.device))
        object.__setattr__(self, "profile_id", _identifier(self.profile_id, "profile_id"))
        if not isinstance(self.requested_text_sha256, str) or not _SHA256.fullmatch(
            self.requested_text_sha256
        ):
            raise ValueError("requested_text_sha256 must be a lowercase SHA-256 digest")
        actions = tuple(islice(self.actions, MAX_SEMANTIC_ACTIONS + 1))
        if len(actions) > MAX_SEMANTIC_ACTIONS:
            raise ValueError("action plan exceeds semantic action limit")
        for action in actions:
            if not isinstance(action, (PressKey, TapPhoneTarget, VerifyPhoneState)):
                raise TypeError(f"Unsupported semantic action {type(action).__name__}")
        if self.device is Device.KEYBOARD:
            invalid = tuple(
                type(action).__name__
                for action in actions
                if not isinstance(action, PressKey)
            )
            if invalid:
                raise ValueError(
                    "Keyboard action plans may contain only PressKey actions; "
                    f"found {invalid}"
                )
        else:
            invalid = tuple(
                type(action).__name__
                for action in actions
                if not isinstance(action, (TapPhoneTarget, VerifyPhoneState))
            )
            if invalid:
                raise ValueError(
                    "Phone action plans may contain only phone-state/tap actions; "
                    f"found {invalid}"
                )
            observed_state: str | None = None
            pending_state_verification: str | None = None
            for index, action in enumerate(actions):
                if isinstance(action, VerifyPhoneState):
                    if (
                        pending_state_verification is not None
                        and action.state_id != pending_state_verification
                    ):
                        raise ValueError(
                            f"Phone verification at action {index} observes "
                            f"{action.state_id!r}, but the preceding tap declared "
                            f"resulting state {pending_state_verification!r}"
                        )
                    observed_state = action.state_id
                    pending_state_verification = None
                    continue
                assert isinstance(action, TapPhoneTarget)
                if pending_state_verification is not None:
                    raise ValueError(
                        f"Phone tap at action {index} follows an unverified state "
                        f"transition to {pending_state_verification!r}"
                    )
                if observed_state is None:
                    raise ValueError(
                        f"Phone tap at action {index} has no preceding verified state"
                    )
                if action.required_state != observed_state:
                    raise ValueError(
                        f"Phone tap at action {index} requires {action.required_state!r}, "
                        f"but the verified/compiled state is {observed_state!r}"
                    )
                if action.resulting_state is not None:
                    # ``resulting_state`` is a prediction made by the semantic
                    # profile, not observation evidence.  Do not let a later
                    # tap rely on it until an explicit VerifyPhoneState action
                    # confirms the newly visible Android UI state.
                    observed_state = None
                    pending_state_verification = action.resulting_state
            if pending_state_verification is not None:
                raise ValueError(
                    "Phone action plan ends with an unverified state transition "
                    f"to {pending_state_verification!r}"
                )
        object.__setattr__(self, "actions", actions)
        calibrations = tuple(
            _identifier(value, "calibration id") for value in self.required_calibrations
        )
        if len(set(calibrations)) != len(calibrations):
            raise ValueError("required_calibrations contains duplicates")
        object.__setattr__(self, "required_calibrations", calibrations)
        if self.schema != "rocell.action_plan.v1":
            raise ValueError("Unsupported action-plan schema")

    @classmethod
    def from_text(
        cls,
        *,
        device: Device,
        profile_id: str,
        text: str,
        actions: tuple[SemanticAction, ...],
        required_calibrations: tuple[str, ...],
    ) -> "ActionPlan":
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if len(text) > MAX_PLAN_TEXT_CHARS or len(text.encode("utf-8")) > MAX_PLAN_TEXT_BYTES:
            raise ValueError("text exceeds action plan input limit")
        return cls(
            device=device,
            profile_id=profile_id,
            requested_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            actions=actions,
            required_calibrations=required_calibrations,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "device": self.device.value,
            "device_profile": self.profile_id,
            "requested_text_sha256": self.requested_text_sha256,
            "actions": [action.to_dict() for action in self.actions],
            "required_calibrations": list(self.required_calibrations),
        }

    @property
    def plan_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
