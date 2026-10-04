from __future__ import annotations

import pytest

from rocell.models.actions import (
    ActionPlan,
    Device,
    MAX_PLAN_TEXT_CHARS,
    MAX_SEMANTIC_ACTIONS,
    PressKey,
    TapPhoneTarget,
    VerifyPhoneState,
)
from rocell.models.profiles import KeyboardProfile, PhoneKeySpec, PhoneProfile
from rocell.models.units import Millimetres, Radians
from rocell.typing.keyboard_compiler import KeyboardCompiler
from rocell.typing.phone_compiler import PhoneCompiler, PhoneStateError
from rocell.typing.unicode_support import UnsupportedCharacterError


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


def test_keyboard_compiler_is_semantic_and_deterministic() -> None:
    profile = KeyboardProfile(
        "keyboard/test-us",
        {"a": ("KEY_A",), "\n": ("ENTER",)},
    )
    first = KeyboardCompiler().compile("a\r\n", profile)
    second = KeyboardCompiler().compile("a\n", profile)

    assert first.device is Device.KEYBOARD
    assert [action.key_id for action in first.actions] == ["KEY_A", "ENTER"]
    assert first.plan_hash == second.plan_hash
    document = first.to_dict()
    assert not _all_keys(document).intersection(
        {"x", "y", "z", "pose", "joints", "cartesian_target", "speed"}
    )
    assert "requested_text" not in document
    assert document["requested_text_sha256"] == first.requested_text_sha256


def test_keyboard_rejects_unsupported_character_with_index() -> None:
    profile = KeyboardProfile("keyboard/test", {"a": ("KEY_A",)})
    with pytest.raises(UnsupportedCharacterError) as caught:
        KeyboardCompiler().compile("ab", profile)
    assert caught.value.character == "b"
    assert caught.value.index == 1


def test_text_and_action_limits_reject_before_large_compilation() -> None:
    keyboard = KeyboardProfile("keyboard/test", {"a": ("KEY_A",)})
    with pytest.raises(ValueError, match="input limit"):
        KeyboardCompiler().compile("a" * (MAX_PLAN_TEXT_CHARS + 1), keyboard)
    phone = PhoneProfile(
        "phone/test", {"a": PhoneKeySpec("KEY_A", "KEYBOARD_LOWER", verify_after=True)},
    )
    with pytest.raises(ValueError, match="semantic action limit"):
        PhoneCompiler().compile("a" * MAX_PLAN_TEXT_CHARS, phone)
    with pytest.raises(ValueError, match="semantic action limit"):
        ActionPlan.from_text(
            device=Device.KEYBOARD, profile_id="keyboard/test", text="a",
            actions=(PressKey("KEY_A") for _ in range(MAX_SEMANTIC_ACTIONS + 1)),
            required_calibrations=(),
        )


def test_profile_mapping_is_immutable() -> None:
    source = {"a": ("KEY_A",)}
    profile = KeyboardProfile("keyboard/test", source)
    source["b"] = ("KEY_B",)
    assert "b" not in profile.character_keys
    with pytest.raises(TypeError):
        profile.character_keys["c"] = ("KEY_C",)  # type: ignore[index]


def test_phone_compiler_tracks_and_verifies_state() -> None:
    profile = PhoneProfile(
        "phone/test",
        {
            "a": PhoneKeySpec("KEY_A", "KEYBOARD_LOWER"),
            "!": PhoneKeySpec(
                "OPEN_SYMBOLS", "KEYBOARD_LOWER", "SYMBOLS_1", verify_after=True
            ),
        },
    )
    plan = PhoneCompiler().compile("a!", profile)
    action_types = [action.to_dict()["type"] for action in plan.actions]
    assert action_types == [
        "verify_phone_state",
        "tap_phone_target",
        "tap_phone_target",
        "verify_phone_state",
    ]
    assert plan.actions[-1].to_dict()["state"] == "SYMBOLS_1"


def test_phone_rejects_unmodelled_state_transition() -> None:
    profile = PhoneProfile(
        "phone/test",
        {"1": PhoneKeySpec("KEY_1", "SYMBOLS_1")},
    )
    with pytest.raises(PhoneStateError):
        PhoneCompiler().compile("1", profile)


def test_action_plan_rejects_cross_device_actions_and_unverified_phone_taps() -> None:
    with pytest.raises(ValueError, match="Keyboard action plans"):
        ActionPlan.from_text(
            device=Device.KEYBOARD,
            profile_id="keyboard/test",
            text="a",
            actions=(TapPhoneTarget("key_a", "KEYBOARD_LOWER"),),
            required_calibrations=(),
        )
    with pytest.raises(ValueError, match="Phone action plans"):
        ActionPlan.from_text(
            device=Device.PHONE,
            profile_id="phone/test",
            text="a",
            actions=(PressKey("A"),),
            required_calibrations=(),
        )
    with pytest.raises(ValueError, match="no preceding verified state"):
        ActionPlan.from_text(
            device=Device.PHONE,
            profile_id="phone/test",
            text="a",
            actions=(TapPhoneTarget("key_a", "KEYBOARD_LOWER"),),
            required_calibrations=(),
        )
    with pytest.raises(ValueError, match="requires 'SYMBOLS'"):
        ActionPlan.from_text(
            device=Device.PHONE,
            profile_id="phone/test",
            text="!",
            actions=(
                VerifyPhoneState("KEYBOARD_LOWER"),
                TapPhoneTarget("key_bang", "SYMBOLS"),
            ),
            required_calibrations=(),
        )


def test_action_plan_requires_observation_after_declared_phone_state_transition() -> None:
    with pytest.raises(ValueError, match="follows an unverified state transition"):
        ActionPlan.from_text(
            device=Device.PHONE,
            profile_id="phone/test",
            text="!1",
            actions=(
                VerifyPhoneState("KEYBOARD_LOWER"),
                TapPhoneTarget("open_symbols", "KEYBOARD_LOWER", "SYMBOLS_1"),
                TapPhoneTarget("key_1", "SYMBOLS_1"),
            ),
            required_calibrations=(),
        )

    with pytest.raises(ValueError, match="preceding tap declared resulting state"):
        ActionPlan.from_text(
            device=Device.PHONE,
            profile_id="phone/test",
            text="!",
            actions=(
                VerifyPhoneState("KEYBOARD_LOWER"),
                TapPhoneTarget("open_symbols", "KEYBOARD_LOWER", "SYMBOLS_1"),
                VerifyPhoneState("KEYBOARD_LOWER"),
            ),
            required_calibrations=(),
        )

    with pytest.raises(ValueError, match="ends with an unverified state transition"):
        ActionPlan.from_text(
            device=Device.PHONE,
            profile_id="phone/test",
            text="!",
            actions=(
                VerifyPhoneState("KEYBOARD_LOWER"),
                TapPhoneTarget("open_symbols", "KEYBOARD_LOWER", "SYMBOLS_1"),
            ),
            required_calibrations=(),
        )


def test_action_plan_accepts_explicitly_verified_phone_state_transition() -> None:
    plan = ActionPlan.from_text(
        device=Device.PHONE,
        profile_id="phone/test",
        text="!1",
        actions=(
            VerifyPhoneState("KEYBOARD_LOWER"),
            TapPhoneTarget("open_symbols", "KEYBOARD_LOWER", "SYMBOLS_1"),
            VerifyPhoneState("SYMBOLS_1"),
            TapPhoneTarget("key_1", "SYMBOLS_1"),
        ),
        required_calibrations=(),
    )

    assert len(plan.actions) == 4


@pytest.mark.parametrize("wrapper", [Millimetres, Radians])
def test_units_reject_nonfinite_values(wrapper: object) -> None:
    with pytest.raises(ValueError):
        wrapper(float("nan"))  # type: ignore[operator]
