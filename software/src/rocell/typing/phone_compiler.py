"""Compile text against an explicit phone UI state contract."""

from __future__ import annotations

from rocell.models.actions import (
    ActionPlan, Device, TapPhoneTarget, VerifyPhoneState,
    MAX_PLAN_TEXT_CHARS, MAX_PLAN_TEXT_BYTES, MAX_SEMANTIC_ACTIONS,
)
from rocell.models.profiles import PhoneProfile

from .unicode_support import UnsupportedCharacterError, normalize_line_endings


class PhoneStateError(ValueError):
    """A profile would require an unmodelled phone UI state transition."""


class PhoneCompiler:
    def compile(self, text: str, profile: PhoneProfile) -> ActionPlan:
        """Translate text to state-guarded Android target taps."""

        if not isinstance(profile, PhoneProfile):
            raise TypeError("profile must be a PhoneProfile")
        if len(text) > MAX_PLAN_TEXT_CHARS or len(text.encode("utf-8")) > MAX_PLAN_TEXT_BYTES:
            raise ValueError("text exceeds phone compilation input limit")
        normalized = normalize_line_endings(text)
        state = profile.initial_state
        actions: list[TapPhoneTarget | VerifyPhoneState] = [VerifyPhoneState(state)]
        for index, character in enumerate(normalized):
            spec = profile.character_targets.get(character)
            if spec is None:
                raise UnsupportedCharacterError(character, index, profile.profile_id)
            if spec.required_state != state:
                raise PhoneStateError(
                    f"Character at normalized index {index} requires state "
                    f"{spec.required_state!r}, but the compiled state is {state!r}; "
                    "the profile must model the transition explicitly"
                )
            if len(actions) + 1 + int(spec.verify_after or spec.resulting_state is not None) > MAX_SEMANTIC_ACTIONS:
                raise ValueError("phone compilation exceeds semantic action limit")
            actions.append(
                TapPhoneTarget(
                    target_id=spec.target_id,
                    required_state=state,
                    resulting_state=spec.resulting_state,
                )
            )
            if spec.resulting_state is not None:
                state = spec.resulting_state
            if spec.verify_after or spec.resulting_state is not None:
                actions.append(VerifyPhoneState(state))
        return ActionPlan.from_text(
            device=Device.PHONE,
            profile_id=profile.profile_id,
            text=normalized,
            actions=tuple(actions),
            required_calibrations=profile.required_calibrations,
        )
