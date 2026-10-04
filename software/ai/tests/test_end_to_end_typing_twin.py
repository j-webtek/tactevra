from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.end_to_end_typing_twin import (  # noqa: E402
    compile_virtual_phone,
    generate_random_cases,
    load_fixture,
    replay_virtual_phone,
    run_semantic_twin,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "ai/sim/evidence/end_to_end_typing_twin_v1.json"


def test_fixture_is_hash_bound_zero_authority_and_source_bound():
    fixture = load_fixture(FIXTURE)
    assert fixture["fixture_sha256"] == "105df64d3c3878bed97caddb2623c9c577a820144909cc94105b529508233bac"
    assert fixture["motion"]["controller_commands"] == []
    assert fixture["motion"]["physical_authority"] is False
    assert not any(fixture["counters"].values())


def test_seeded_case_population_is_exact_and_repeatable():
    fixture = load_fixture(FIXTURE, verify_sources=False)
    first = generate_random_cases(fixture, "keyboard", "ci")
    second = generate_random_cases(fixture, "keyboard", "ci")
    assert first == second
    assert len(first) == 128
    assert {len(item) for item in first} == {1, 2, 4, 8, 16, 32, 64, 128}
    assert hashlib.sha256(json.dumps(first).encode()).hexdigest() == hashlib.sha256(
        json.dumps(second).encode()).hexdigest()


@pytest.mark.parametrize("text", ["Hello 2026!", "AA", "!!", "aA", "A A", "[]{}\\|`~"])
def test_phone_layer_machine_replays_exact_text(text: str):
    actions = compile_virtual_phone(text)
    replay = replay_virtual_phone(actions)
    assert replay["accepted"] is True
    assert replay["text"] == text
    assert all(row["observed_state"] == row["expected_state"] for row in replay["readback_log"])


def test_phone_commissioning_detects_autocorrect_and_predictive_text():
    actions = compile_virtual_phone("hello")
    assert replay_virtual_phone(actions, autocorrect=True)["status"] == (
        "COMMISSIONING_CONFIGURATION_MISMATCH")
    assert replay_virtual_phone(actions, predictive_text=True)["status"] == (
        "COMMISSIONING_CONFIGURATION_MISMATCH")


def test_ci_semantic_core_is_exact_deterministic_and_zero_authority():
    first = run_semantic_twin(FIXTURE, mode="ci")
    second = run_semantic_twin(FIXTURE, mode="ci")
    assert first["core_receipt_sha256"] == second["core_receipt_sha256"]
    assert first["semantic_exact_text_success_rate"] == 1.0
    assert first["fault_detection_rate"] == 1.0
    assert first["workstream_decision"] == "PARTIAL_SEMANTIC_AND_DEVICE_STATE_CORE_ONLY"
    assert first["arm_runtime_composed"] is False
    assert first["controller_commands"] == []
    assert first["hardware_commands_generated"] == 0
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False
    assert "descriptive_stage_latency_ns" in first
