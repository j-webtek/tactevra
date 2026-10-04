"""Compile text into named physical-key actions without generating poses."""

from __future__ import annotations

from rocell.models.actions import (
    ActionPlan, Device, PressKey, MAX_PLAN_TEXT_CHARS,
    MAX_PLAN_TEXT_BYTES, MAX_SEMANTIC_ACTIONS,
)
from rocell.models.profiles import KeyboardProfile

from .unicode_support import UnsupportedCharacterError, normalize_line_endings


class KeyboardCompiler:
    def compile(self, text: str, profile: KeyboardProfile) -> ActionPlan:
        """Translate text to named key presses while preserving no coordinates."""

        if not isinstance(profile, KeyboardProfile):
            raise TypeError("profile must be a KeyboardProfile")
        if len(text) > MAX_PLAN_TEXT_CHARS or len(text.encode("utf-8")) > MAX_PLAN_TEXT_BYTES:
            raise ValueError("text exceeds keyboard compilation input limit")
        normalized = normalize_line_endings(text)
        actions: list[PressKey] = []
        for index, character in enumerate(normalized):
            key_sequence = profile.character_keys.get(character)
            if key_sequence is None:
                raise UnsupportedCharacterError(character, index, profile.profile_id)
            if len(actions) + len(key_sequence) > MAX_SEMANTIC_ACTIONS:
                raise ValueError("keyboard compilation exceeds semantic action limit")
            actions.extend(PressKey(key_id) for key_id in key_sequence)
        return ActionPlan.from_text(
            device=Device.KEYBOARD,
            profile_id=profile.profile_id,
            text=normalized,
            actions=tuple(actions),
            required_calibrations=profile.required_calibrations,
        )
