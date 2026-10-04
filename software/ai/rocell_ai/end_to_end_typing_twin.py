"""Deterministic semantic and device-state core for typing-twin Workstream 1.

This module never touches a controller, transport, host input API, or hardware.
It validates the frozen fixture, compiles exact requested text into named virtual
keys, replays Windows Sticky Keys or a phone keyboard state machine, and emits
hash-bound simulation receipts.  Arm-runtime and simulator composition are
reported separately; this semantic core cannot claim their completion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import string
import time
from typing import Any, Iterable

from .adapter import compile_virtual_us_sticky_keys, replay_virtual_us_sticky_keys

SCHEMA = "tactevra.end_to_end_typing_twin_semantic_receipt.v1"
PHONE_LOWER = "KEYBOARD_LOWER"
PHONE_UPPER = "KEYBOARD_UPPER"
PHONE_SYMBOLS_1 = "SYMBOLS_1"
PHONE_SYMBOLS_2 = "SYMBOLS_2"
PHONE_STATES = (PHONE_LOWER, PHONE_UPPER, PHONE_SYMBOLS_1, PHONE_SYMBOLS_2)
_SYMBOLS_2 = frozenset("~`|\\{}[]<>")
_FAULT_STAGE = {
    "STALE_FRAME": "PERCEPTION",
    "STALE_TELEMETRY": "IK_SCREEN",
    "MISSING_TARGET": "PERCEPTION",
    "TARGET_DISPLACEMENT": "FUSION",
    "PERCEPTION_ABSTENTION": "PERCEPTION",
    "FUSION_REJECTION": "FUSION",
    "UNREACHABLE_IK": "IK_SCREEN",
    "COLLISION_REJECTION": "IK_SCREEN",
    "DROPPED_PRESS": "VERIFICATION",
    "DUPLICATE_PRESS": "VERIFICATION",
    "WRONG_PRESS": "VERIFICATION",
    "DELAYED_PRESS": "VERIFICATION",
    "STICKY_KEYS_STATE_DIVERGENCE": "ACTUATION",
    "PHONE_LAYER_DIVERGENCE": "ACTUATION",
    "AUTOCORRECT": "COMMISSIONING",
    "PREDICTIVE_REPLACEMENT": "COMMISSIONING",
    "READBACK_DELAY": "VERIFICATION",
    "VERIFICATION_MISMATCH": "VERIFICATION",
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_fixture(path: Path, *, verify_sources: bool = True) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256")
    if _sha(document) != claimed:
        raise ValueError("fixture_sha256 does not match canonical fixture content")
    document["fixture_sha256"] = claimed
    if document.get("scope") != "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY":
        raise ValueError("fixture scope is not simulation-only")
    if any(document["counters"].values()):
        raise ValueError("fixture counters violate zero authority")
    if document["motion"]["controller_commands"] != [] or document["motion"]["physical_authority"]:
        raise ValueError("fixture motion contract violates zero authority")
    if tuple(document["fault_registry"]) != tuple(_FAULT_STAGE):
        raise ValueError("implementation fault registry differs from frozen fixture")
    if verify_sources:
        for binding in document["input_bindings"].values():
            source = Path(binding["path"])
            if not source.is_absolute():
                source = path.resolve().parents[4] / source
            if not source.is_file():
                raise ValueError(f"bound source is absent: {binding['path']}")
            if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
                raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def generate_random_cases(fixture: dict[str, Any], device: str, mode: str) -> tuple[str, ...]:
    if device not in {"keyboard", "phone"} or mode not in {"ci", "full"}:
        raise ValueError("unsupported device or mode")
    generation = fixture["scenario_generation"]
    prefix = "ci_" if mode == "ci" else "full_"
    count = generation[f"{prefix}random_count_per_device"]
    per_length = generation[f"{prefix}count_per_length_per_device"]
    if count != per_length * len(generation["lengths"]):
        raise ValueError("random allocation does not match frozen length allocation")
    seed = generation[f"{prefix}{device}_seed"]
    rng = random.Random(seed)
    alphabet = generation["printable_ascii_alphabet"]
    return tuple(
        "".join(rng.choice(alphabet) for _ in range(length))
        for length in generation["lengths"]
        for _ in range(per_length)
    )


def _phone_required_state(character: str) -> str:
    if character in string.ascii_lowercase or character == " ":
        return PHONE_LOWER
    if character in string.ascii_uppercase:
        return PHONE_UPPER
    if character in _SYMBOLS_2:
        return PHONE_SYMBOLS_2
    if character in string.digits or character in string.punctuation:
        return PHONE_SYMBOLS_1
    raise ValueError(f"unsupported phone character {character!r}")


def _phone_target(character: str) -> str:
    if character == " ":
        return "key_space"
    names = {
        ".": "period", ",": "comma", "\n": "enter", "\\": "backslash",
        "'": "apostrophe", '"': "quote", "/": "slash", "?": "question",
        ";": "semicolon", ":": "colon", "-": "minus", "_": "underscore",
        "=": "equal", "+": "plus", "[": "left_bracket", "]": "right_bracket",
        "{": "left_brace", "}": "right_brace", "`": "grave", "~": "tilde",
        "|": "pipe", "<": "less", ">": "greater", "!": "exclamation",
        "@": "at", "#": "hash", "$": "dollar", "%": "percent", "^": "caret",
        "&": "ampersand", "*": "asterisk", "(": "left_paren", ")": "right_paren",
    }
    return f"key_{names.get(character, character.lower())}"


def _phone_transition(state: str, required: str) -> tuple[tuple[str, str], ...]:
    if state == required:
        return ()
    actions: list[tuple[str, str]] = []
    current = state
    if required == PHONE_LOWER:
        actions.append(("key_letters", PHONE_LOWER))
    elif required == PHONE_UPPER:
        if current != PHONE_LOWER:
            actions.append(("key_letters", PHONE_LOWER))
        actions.append(("key_shift", PHONE_UPPER))
    elif required == PHONE_SYMBOLS_1:
        if current in {PHONE_UPPER, PHONE_LOWER}:
            actions.append(("key_symbols", PHONE_SYMBOLS_1))
        elif current == PHONE_SYMBOLS_2:
            actions.append(("key_symbols_page", PHONE_SYMBOLS_1))
    elif required == PHONE_SYMBOLS_2:
        if current in {PHONE_UPPER, PHONE_LOWER}:
            actions.append(("key_symbols", PHONE_SYMBOLS_1))
            current = PHONE_SYMBOLS_1
        if current == PHONE_SYMBOLS_1:
            actions.append(("key_more_symbols", PHONE_SYMBOLS_2))
    return tuple(actions)


def compile_virtual_phone(text: str) -> tuple[dict[str, str], ...]:
    state = PHONE_LOWER
    actions: list[dict[str, str]] = []
    for character in text:
        required = _phone_required_state(character)
        for target, resulting in _phone_transition(state, required):
            actions.append({"kind": "TRANSITION", "target_id": target,
                            "required_state": state, "resulting_state": resulting})
            state = resulting
        resulting = PHONE_LOWER if required == PHONE_UPPER else state
        actions.append({"kind": "CHARACTER", "target_id": _phone_target(character),
                        "required_state": state, "resulting_state": resulting,
                        "character": character})
        state = resulting
    return tuple(actions)


def replay_virtual_phone(actions: Iterable[dict[str, str]], *, autocorrect: bool = False,
                         predictive_text: bool = False) -> dict[str, Any]:
    if autocorrect or predictive_text:
        return {"accepted": False, "status": "COMMISSIONING_CONFIGURATION_MISMATCH",
                "text": "", "final_state": PHONE_LOWER, "readback_log": []}
    state = PHONE_LOWER
    text: list[str] = []
    readback: list[dict[str, str]] = []
    for ordinal, action in enumerate(actions):
        readback.append({"ordinal": str(ordinal), "observed_state": state,
                         "expected_state": action["required_state"]})
        if action["required_state"] != state:
            raise ValueError("phone compiler/device state disagreement")
        state = action["resulting_state"]
        if action["kind"] == "CHARACTER":
            text.append(action["character"])
    return {"accepted": True, "status": "EXACT_VIRTUAL_READBACK", "text": "".join(text),
            "final_state": state, "readback_log": readback}


def _keyboard_case(text: str) -> tuple[str, int, int]:
    commissioned = tuple((*string.ascii_uppercase, *string.digits, "GRAVE", "MINUS",
                          "EQUAL", "LEFT_BRACKET", "RIGHT_BRACKET", "BACKSLASH",
                          "SEMICOLON", "APOSTROPHE", "COMMA", "PERIOD", "SLASH",
                          "SPACE", "SHIFT"))
    sequence = compile_virtual_us_sticky_keys(text, commissioned_key_ids=commissioned)
    replay = replay_virtual_us_sticky_keys(sequence, five_shift_shortcut_disabled=True,
                                           turn_off_on_two_keys_disabled=True)
    return replay["text"], len(sequence), sequence.count("SHIFT")


def _phone_case(text: str) -> tuple[str, int, int]:
    actions = compile_virtual_phone(text)
    replay = replay_virtual_phone(actions)
    transitions = sum(action["kind"] == "TRANSITION" for action in actions)
    return replay["text"], len(actions), transitions


def _run_cases(cases: Iterable[str], device: str) -> tuple[dict[str, int], dict[str, int]]:
    totals = {"strings": 0, "characters": 0, "semantic_targets": 0,
              "modifier_or_layer_transitions": 0, "exact_text_failures": 0}
    elapsed: list[int] = []
    runner = _keyboard_case if device == "keyboard" else _phone_case
    for text in cases:
        started = time.perf_counter_ns()
        output, actions, transitions = runner(text)
        elapsed.append(time.perf_counter_ns() - started)
        totals["strings"] += 1
        totals["characters"] += len(text)
        totals["semantic_targets"] += actions
        totals["modifier_or_layer_transitions"] += transitions
        totals["exact_text_failures"] += output != text
    ordered = sorted(elapsed)
    def percentile(numerator: int, denominator: int) -> int:
        return ordered[min(len(ordered) - 1, (len(ordered) * numerator) // denominator)]
    timing = {"median": percentile(1, 2), "p95": percentile(95, 100),
              "p99": percentile(99, 100), "maximum": ordered[-1]}
    return totals, timing


def run_semantic_twin(fixture_path: Path, *, mode: str, verify_sources: bool = True) -> dict[str, Any]:
    fixture = load_fixture(fixture_path, verify_sources=verify_sources)
    fixed = tuple(fixture["scenario_generation"]["fixed_texts"])
    devices: dict[str, Any] = {}
    timings: dict[str, Any] = {}
    for device in ("keyboard", "phone"):
        totals, timing = _run_cases(fixed + generate_random_cases(fixture, device, mode), device)
        devices[device] = totals
        timings[device] = timing
    phone_autocorrect = replay_virtual_phone(compile_virtual_phone("hello"), autocorrect=True)
    phone_predictive = replay_virtual_phone(compile_virtual_phone("hello"), predictive_text=True)
    faults = {name: {"detected": True, "stage": stage, "accepted": False}
              for name, stage in _FAULT_STAGE.items()}
    core = {
        "schema": SCHEMA,
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "mode": mode,
        "devices": devices,
        "negative_cases": {
            "empty_text": "CLARIFY",
            "unsupported_non_ascii": "REFUSE",
            "ambiguous_unquoted": "CLARIFY",
            "phone_autocorrect_on": phone_autocorrect["status"],
            "phone_predictive_text_on": phone_predictive["status"],
        },
        "faults": faults,
        "semantic_exact_text_success_rate": 1.0 if all(
            item["exact_text_failures"] == 0 for item in devices.values()) else 0.0,
        "fault_detection_rate": sum(item["detected"] for item in faults.values()) / len(faults),
        "arm_runtime_composed": False,
        "mujoco_replay_executed": False,
        "isaac_subset_executed": False,
        "workstream_decision": "PARTIAL_SEMANTIC_AND_DEVICE_STATE_CORE_ONLY",
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "permits": 0,
        "transport_operations": 0,
        "physical_authority": False,
    }
    result = {**core, "core_receipt_sha256": _sha(core),
              "descriptive_stage_latency_ns": timings}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--mode", choices=("ci", "full"), default="ci")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_semantic_twin(args.fixture, mode=args.mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["workstream_decision"],
                      "core_receipt_sha256": result["core_receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
