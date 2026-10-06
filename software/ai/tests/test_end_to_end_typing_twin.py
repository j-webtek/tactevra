from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.end_to_end_typing_twin import (  # noqa: E402
    VirtualKeyboardStateError,
    classify_verification_effect,
    compile_virtual_phone,
    compile_virtual_us_sticky_keys,
    generate_random_cases,
    load_fixture,
    replay_virtual_phone,
    replay_virtual_us_sticky_keys,
    run_recovery_handoff,
    run_semantic_twin,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "ai/sim/evidence/end_to_end_typing_twin_main_v1_1.json"
RECOVERY_FIXTURE = ROOT / "ai/sim/evidence/workstream_4_recovery_portable_v1.json"


def test_fixture_is_hash_source_and_zero_authority_bound() -> None:
    fixture = load_fixture(FIXTURE)
    assert fixture["fixture_sha256"] == (
        "d1f42a38f0bf190311976c65b6b9964ae45b948b0a5d38003c63b436d32e8a1c")
    assert fixture["motion"]["controller_commands"] == []
    assert fixture["motion"]["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_fixture_rejects_tampering(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["scenario_generation"]["ci_keyboard_seed"] += 1
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture_sha256"):
        load_fixture(changed, verify_sources=False)


def test_seeded_populations_are_exact_and_repeatable() -> None:
    fixture = load_fixture(FIXTURE, verify_sources=False)
    for device in ("keyboard", "phone"):
        first = generate_random_cases(fixture, device, "ci")
        second = generate_random_cases(fixture, device, "ci")
        assert first == second
        assert len(first) == 128
        assert {len(item) for item in first} == {1, 2, 4, 8, 16, 32, 64, 128}


@pytest.mark.parametrize("text", [
    "Hello 2026!", "AA", "!!", "aA", "A A", "[]{}\\|`~",
])
def test_virtual_keyboard_and_phone_replay_exact_text(text: str) -> None:
    keyboard = replay_virtual_us_sticky_keys(
        compile_virtual_us_sticky_keys(text),
        five_shift_shortcut_disabled=True,
        turn_off_on_two_keys_disabled=True,
    )
    phone = replay_virtual_phone(compile_virtual_phone(text))
    assert keyboard["text"] == text
    assert keyboard["final_modifier_state"] == "OFF"
    assert phone["accepted"] is True and phone["text"] == text
    assert all(
        row["observed_state"] == row["expected_state"]
        for row in phone["readback_log"])


def test_keyboard_state_hazards_and_phone_configuration_fail_closed() -> None:
    with pytest.raises(VirtualKeyboardStateError, match="locked state"):
        replay_virtual_us_sticky_keys(
            ("SHIFT", "SHIFT", "A"),
            five_shift_shortcut_disabled=True,
            turn_off_on_two_keys_disabled=True,
        )
    with pytest.raises(VirtualKeyboardStateError, match="five-Shift"):
        replay_virtual_us_sticky_keys(
            ("A",), five_shift_shortcut_disabled=False,
            turn_off_on_two_keys_disabled=True)
    actions = compile_virtual_phone("hello")
    assert replay_virtual_phone(actions, autocorrect=True)["status"] == (
        "COMMISSIONING_CONFIGURATION_MISMATCH")
    assert replay_virtual_phone(actions, predictive_text=True)["status"] == (
        "COMMISSIONING_CONFIGURATION_MISMATCH")


@pytest.mark.parametrize(("observed", "known", "expected"), [
    ("ab", True, "SINGLE_MISSED_PRESS"),
    ("abcc", True, "SINGLE_DOUBLE_PRESS"),
    ("ab?", True, "SINGLE_WRONG_PRESS"),
    (None, False, "UNKNOWN_COMMITTED_TEXT"),
    ("abc", True, "NONE"),
])
def test_verification_effect_classifier(
    observed: str | None, known: bool, expected: str,
) -> None:
    assert classify_verification_effect(
        "abc", observed, readback_known=known) == expected


def test_ci_semantic_core_is_exact_deterministic_and_zero_authority() -> None:
    first = run_semantic_twin(FIXTURE, mode="ci")
    second = run_semantic_twin(FIXTURE, mode="ci")
    assert first["core_receipt_sha256"] == second["core_receipt_sha256"]
    assert first["semantic_exact_text_success_rate"] == 1.0
    assert first["fault_detection_rate"] == 1.0
    assert first["workstream_decision"] == (
        "PARTIAL_SEMANTIC_AND_DEVICE_STATE_CORE_ONLY")
    assert first["controller_commands"] == []
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_actual_virtual_readback_faults_feed_portable_recovery() -> None:
    first = run_recovery_handoff(
        FIXTURE, RECOVERY_FIXTURE, workspace=ROOT.parent)
    second = run_recovery_handoff(
        FIXTURE, RECOVERY_FIXTURE, workspace=ROOT.parent)
    assert first == second
    assert first["case_count"] == 8
    assert first["classification_mismatch_count"] == 0
    assert first["terminal_mismatch_count"] == 0
    assert {row["terminal_state"] for row in first["rows"]} == {"COMPLETE", "ABORT"}
    assert first["controller_commands"] == []
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False
