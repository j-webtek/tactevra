"""Read-only compatibility adapter to RoCell's semantic text compilers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import string
from typing import Any

from rocell.typing import PhoneStateError, UnsupportedCharacterError, compile_development_text

from .contract import validate_proposal, validate_result


_DESKTOP_SHIFTED_CHARACTERS = frozenset(
    string.ascii_uppercase + '~!@#$%^&*()_+{}|:"<>?'
)
_PHONE_LAYERED_CHARACTERS = frozenset(
    string.ascii_uppercase + string.digits + string.punctuation
)
_US_SHIFTED_TO_BASE = {
    "~": "GRAVE",
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "MINUS",
    "+": "EQUAL",
    "{": "LEFT_BRACKET",
    "}": "RIGHT_BRACKET",
    "|": "BACKSLASH",
    ":": "SEMICOLON",
    '"': "APOSTROPHE",
    "<": "COMMA",
    ">": "PERIOD",
    "?": "SLASH",
}
_US_UNSHIFTED_TO_KEY = {
    "`": "GRAVE",
    "-": "MINUS",
    "=": "EQUAL",
    "[": "LEFT_BRACKET",
    "]": "RIGHT_BRACKET",
    "\\": "BACKSLASH",
    ";": "SEMICOLON",
    "'": "APOSTROPHE",
    ",": "COMMA",
    ".": "PERIOD",
    "/": "SLASH",
    " ": "SPACE",
}
US_PRINTABLE_BASE_KEY_IDS = tuple(sorted(
    set(string.ascii_uppercase)
    | set(string.digits)
    | set(_US_SHIFTED_TO_BASE.values())
    | set(_US_UNSHIFTED_TO_KEY.values())
))

_TARGET_EXTENSION_SEEDS = {
    "SHIFT": {
        "presentation_center_xy_mm": [20.0, 48.0],
        "presentation_width_mm": 37.0,
        "proposed_press_point_xy_mm": [20.0, 48.0],
        "proposed_safe_half_extent_mm": [7.0, 7.0],
        "source_literal": '("SHIFT", ox + 20.0, oy + 48.0, 37.0)',
        "press_point_rule": (
            "EXPLICIT_MAXIMUM_EDGE_CLEARANCE_POINT_WITH_CONSERVATIVE_14_BY_14_MM_PATCH_"
            "NOT_FULL_WIDE_KEY_CENTER_DEFAULT"
        ),
    },
    "LEFT_BRACKET": {
        "presentation_center_xy_mm": [231.5, 90.0],
        "presentation_width_mm": 15.6,
        "proposed_press_point_xy_mm": [231.5, 90.0],
        "proposed_safe_half_extent_mm": [7.0, 7.0],
        "source_literal": '("[", ox + 231.5, oy + 90.0, 15.6)',
        "press_point_rule": "EXPLICIT_MAXIMUM_EDGE_CLEARANCE_POINT",
    },
    "RIGHT_BRACKET": {
        "presentation_center_xy_mm": [250.5, 90.0],
        "presentation_width_mm": 15.6,
        "proposed_press_point_xy_mm": [250.5, 90.0],
        "proposed_safe_half_extent_mm": [7.0, 7.0],
        "source_literal": '("]", ox + 250.5, oy + 90.0, 15.6)',
        "press_point_rule": "EXPLICIT_MAXIMUM_EDGE_CLEARANCE_POINT",
    },
    "BACKSLASH": {
        "presentation_center_xy_mm": [269.5, 90.0],
        "presentation_width_mm": 15.6,
        "proposed_press_point_xy_mm": [269.5, 90.0],
        "proposed_safe_half_extent_mm": [7.0, 7.0],
        "source_literal": '("\\\\", ox + 269.5, oy + 90.0, 15.6)',
        "press_point_rule": "EXPLICIT_MAXIMUM_EDGE_CLEARANCE_POINT",
    },
}

_GRAVE_MEASUREMENT_METHOD = {
    "schema": "rocell.keyboard_relative_key_measurement_method.v1",
    "instrument": "DIGITAL_CALIPER_RESOLUTION_AT_MOST_0_1_MM",
    "keyboard_condition": "POWER_ISOLATED_ARM_CLEAR_KEYBOARD_FIXED_IN_WORKCELL_JOINTS",
    "reference_target_id": "1",
    "reference_catalog_center_xy_mm": [22.0, 111.0],
    "coordinate_signs": "POSITIVE_X_RIGHT_POSITIVE_Y_AWAY_FROM_DEVICE_FRONT",
    "measurement_surface": {
        "surface": "KEYCAP_TOP_PRESS_SURFACE",
        "exclude": ["KEYCAP_TAPERED_SIDEWALL", "KEYCAP_BASE", "SWITCH_HOUSING"],
        "reason": "THE_CAMERA_OBSERVES_AND_THE_TOOL_CONTACTS_THE_KEYCAP_TOP_SURFACE",
        "edge_definition": "VISIBLE_TOP_SURFACE_EDGE_AT_THE_PRESS_PLANE",
    },
    "required_signed_measurements_mm": {
        "grave_top_left_edge_minus_reference_top_left_edge_x": 3,
        "grave_top_front_edge_minus_reference_top_front_edge_y": 3,
        "grave_top_width_x": 3,
        "grave_top_height_y": 3,
        "reference_top_width_x": 3,
        "reference_top_height_y": 3,
    },
    "caliper_checks": {
        "zero_before_mm_absolute_max": 0.1,
        "zero_after_mm_absolute_max": 0.1,
        "maximum_repeat_range_mm": 0.3,
    },
    "center_derivation": {
        "x": "reference_center_x + mean(top_left_edge_delta_x) + (mean(grave_top_width) - mean(reference_top_width)) / 2",
        "y": "reference_center_y + mean(top_front_edge_delta_y) + (mean(grave_top_height) - mean(reference_top_height)) / 2",
    },
    "safe_region_derivation": {
        "center": "derived_key_center",
        "edge_inset_mm": 1.0,
        "maximum_half_extent_mm": [7.0, 7.0],
        "half_extent_x": "min(7.0, mean(grave_top_width) / 2 - 1.0)",
        "half_extent_y": "min(7.0, mean(grave_top_height) / 2 - 1.0)",
    },
    "required_record_bindings": [
        "operator",
        "utc_timestamp",
        "keyboard_serial_or_stable_identity",
        "instrument_make_model",
        "instrument_serial",
        "instrument_resolution_mm",
        "raw_readings",
        "source_catalog_sha256",
    ],
    "decision": "FAIL_CLOSED_IF_ANY_BINDING_CHECK_OR_REPEATABILITY_LIMIT_FAILS",
}


class StickyKeysReplayError(ValueError):
    """A sequence violates the commissioned one-shot modifier contract."""


def compile_virtual_us_sticky_keys(
    text: str, *, commissioned_key_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """Compile printable ASCII only when every emitted key is commissioned."""

    commissioned = frozenset(commissioned_key_ids)
    sequence: list[str] = []
    for index, character in enumerate(text):
        keys: tuple[str, ...]
        if "a" <= character <= "z":
            keys = (character.upper(),)
        elif "A" <= character <= "Z":
            keys = ("SHIFT", character)
        elif character in string.digits:
            keys = (character,)
        elif character in _US_SHIFTED_TO_BASE:
            keys = ("SHIFT", _US_SHIFTED_TO_BASE[character])
        elif character in _US_UNSHIFTED_TO_KEY:
            keys = (_US_UNSHIFTED_TO_KEY[character],)
        else:
            raise StickyKeysReplayError(
                f"unsupported virtual US character {character!r} at index {index}"
            )
        missing = tuple(key_id for key_id in keys if key_id not in commissioned)
        if missing:
            raise StickyKeysReplayError(
                f"uncommissioned key(s) {missing!r} for character {character!r} at index {index}"
            )
        sequence.extend(keys)
    if any(left == right == "SHIFT" for left, right in zip(sequence, sequence[1:])):
        raise StickyKeysReplayError("compiler emitted consecutive Shift presses")
    return tuple(sequence)


def replay_virtual_us_sticky_keys(
    sequence: tuple[str, ...],
    *,
    five_shift_shortcut_disabled: bool,
    turn_off_on_two_keys_disabled: bool,
) -> dict[str, Any]:
    """Replay the Windows one-shot latch semantics without OS or device access."""

    if not five_shift_shortcut_disabled:
        raise StickyKeysReplayError("five-Shift shortcut is not disabled")
    if not turn_off_on_two_keys_disabled:
        raise StickyKeysReplayError("two-key disable behavior is not disabled")
    reverse_unshifted = {key: value for value, key in _US_UNSHIFTED_TO_KEY.items()}
    reverse_shifted = {key: value for value, key in _US_SHIFTED_TO_BASE.items()}
    state = "OFF"
    consecutive_shifts = 0
    output: list[str] = []
    verification: list[dict[str, str]] = []
    for index, key_id in enumerate(sequence):
        if key_id == "SHIFT":
            consecutive_shifts += 1
            if consecutive_shifts >= 2:
                raise StickyKeysReplayError(
                    f"consecutive Shift at action {index} would enter locked state"
                )
            state = "LATCHED"
            verification.append({"key": "SHIFT", "expected_modifier_state": "LATCHED"})
            continue
        consecutive_shifts = 0
        if len(key_id) == 1 and "A" <= key_id <= "Z":
            character = key_id if state == "LATCHED" else key_id.lower()
        elif key_id in string.digits:
            character = reverse_shifted[key_id] if state == "LATCHED" else key_id
        elif state == "LATCHED" and key_id in reverse_shifted:
            character = reverse_shifted[key_id]
        elif state == "OFF" and key_id in reverse_unshifted:
            character = reverse_unshifted[key_id]
        else:
            raise StickyKeysReplayError(
                f"key {key_id!r} is invalid in modifier state {state} at action {index}"
            )
        output.append(character)
        state = "OFF"
        verification.append({"key": key_id, "expected_modifier_state": "OFF"})
    if state != "OFF":
        raise StickyKeysReplayError("sequence ends with a latched modifier")
    return {
        "text": "".join(output),
        "final_modifier_state": state,
        "keystroke_log_expectations": verification,
        "dialog_triggered": False,
        "sticky_keys_disabled": False,
    }


def run_seeded_sticky_keys_replay(
    *, seed: int, string_count: int, maximum_length: int
) -> dict[str, Any]:
    """Replay fixed edge cases and seeded printable-ASCII strings deterministically."""

    if type(seed) is not int or type(string_count) is not int or string_count < 1:
        raise ValueError("seed must be an integer and string_count must be positive")
    if type(maximum_length) is not int or maximum_length < 1:
        raise ValueError("maximum_length must be positive")
    alphabet = "".join(chr(value) for value in range(32, 127))
    fixed_cases = ("AA", "!!", "aA", "A", " A")
    generator = random.Random(seed)
    random_cases = tuple(
        "".join(generator.choice(alphabet) for _ in range(generator.randint(1, maximum_length)))
        for _ in range(string_count)
    )
    cases = fixed_cases + random_cases
    commissioned = tuple((*US_PRINTABLE_BASE_KEY_IDS, "SHIFT"))
    total_characters = 0
    total_actions = 0
    total_shift_presses = 0
    for text in cases:
        sequence = compile_virtual_us_sticky_keys(
            text, commissioned_key_ids=commissioned
        )
        replay = replay_virtual_us_sticky_keys(
            sequence,
            five_shift_shortcut_disabled=True,
            turn_off_on_two_keys_disabled=True,
        )
        if replay["text"] != text:
            raise StickyKeysReplayError("seeded replay changed requested text")
        total_characters += len(text)
        total_actions += len(sequence)
        total_shift_presses += sequence.count("SHIFT")
    case_bytes = json.dumps(cases, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return {
        "seed": seed,
        "fixed_cases": list(fixed_cases),
        "random_string_count": string_count,
        "total_string_count": len(cases),
        "maximum_length": maximum_length,
        "total_characters": total_characters,
        "total_actions": total_actions,
        "total_shift_presses": total_shift_presses,
        "failures": 0,
        "cases_sha256": hashlib.sha256(case_bytes).hexdigest(),
    }


def planner_capability_contract(
    *,
    keyboard_target_ids: tuple[str, ...] = (),
    sticky_keys_verified: bool = False,
    phone_target_ids: tuple[str, ...] = (),
    adb_layer_verification: bool = False,
) -> dict[str, Any]:
    """Describe the commissioned prerequisites for sequential shifted input.

    This is a capability audit, not a target map or execution permit.  The
    language model never supplies these target identities or capability facts.
    """

    keyboard_targets = frozenset(keyboard_target_ids)
    phone_targets = frozenset(phone_target_ids)
    missing_base_keys = tuple(sorted(set(US_PRINTABLE_BASE_KEY_IDS) - keyboard_targets))
    missing_modifier_keys = () if "SHIFT" in keyboard_targets else ("SHIFT",)
    keyboard_ready = (
        not missing_base_keys
        and not missing_modifier_keys
        and sticky_keys_verified is True
    )
    required_phone_targets = frozenset({"key_shift", "key_symbols", "key_letters"})
    phone_ready = required_phone_targets <= phone_targets and adb_layer_verification is True
    core: dict[str, Any] = {
        "schema": "rocell.ai_planner_capability_contract.v1",
        "keyboard": {
            "strategy": "STICKY_KEYS_SEQUENTIAL_MODIFIER",
            "simultaneous_chord_supported": False,
            "caps_lock_optimization_enabled": False,
            "required_target_ids": ["SHIFT"],
            "required_base_key_ids": list(US_PRINTABLE_BASE_KEY_IDS),
            "required_base_key_count": len(US_PRINTABLE_BASE_KEY_IDS),
            "missing_base_key_ids": list(missing_base_keys),
            "missing_modifier_key_ids": list(missing_modifier_keys),
            "sticky_keys_commissioning_evidence_required": True,
            "required_configuration": {
                "sticky_keys_enabled": True,
                "one_shot_shift_latch": True,
                "five_shift_shortcut_disabled": True,
                "turn_off_when_two_keys_pressed_disabled": True,
            },
            "verification_source": "HOST_KEYSTROKE_AND_MODIFIER_STATE_LOG",
            "ready": keyboard_ready,
            "blocked_reason": None if keyboard_ready else "keyboard_modifier_uncommissioned",
        },
        "phone": {
            "strategy": "VERIFIED_LAYER_STATE_MACHINE",
            "states": ["KEYBOARD_LOWER", "KEYBOARD_UPPER", "SYMBOLS_1"],
            "required_transition_target_ids": sorted(required_phone_targets),
            "adb_verification_before_every_press": True,
            "ready": phone_ready,
            "blocked_reason": None if phone_ready else "phone_layer_uncommissioned",
        },
        "language_model_may_emit_target_ids": False,
        "coordinates_present": False,
        "hardware_commands_generated": 0,
        "physical_authority": False,
    }
    encoded = json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return {**core, "contract_sha256": hashlib.sha256(encoded).hexdigest()}


def build_planner_capability_audit(
    target_catalog_path: Path, source_commit: str
) -> dict[str, Any]:
    """Audit the current nominal catalog against the frozen capability contract."""

    source = json.loads(target_catalog_path.read_text(encoding="utf-8"))

    def target_ids(section: dict[str, Any]) -> tuple[str, ...]:
        values: list[str] = []
        for row in section["rows"]:
            values.extend(row.get("key_ids", row.get("target_ids", ())))
        values.extend(section["explicit_targets"])
        return tuple(values)

    keyboard_ids = target_ids(source["keyboard"])
    phone_ids = target_ids(source["phone"])
    core: dict[str, Any] = {
        "schema": "rocell.ai_planner_capability_audit.v1",
        "source_commit": source_commit,
        "target_catalog_file": target_catalog_path.as_posix(),
        "target_catalog_file_sha256": hashlib.sha256(
            target_catalog_path.read_bytes()
        ).hexdigest(),
        "contract": planner_capability_contract(
            keyboard_target_ids=keyboard_ids,
            sticky_keys_verified=False,
            phone_target_ids=phone_ids,
            adb_layer_verification=False,
        ),
        "keyboard_target_count": len(keyboard_ids),
        "phone_target_count": len(phone_ids),
        "seeded_replay": run_seeded_sticky_keys_replay(
            seed=190055, string_count=5000, maximum_length=64
        ),
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    encoded = json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return {**core, "audit_sha256": hashlib.sha256(encoded).hexdigest()}


def build_keyboard_target_extension_proposal(
    target_catalog_path: Path,
    geometry_source_path: Path,
    source_commit: str,
    *,
    photo_geometry_study_path: Path | None = None,
    photo_source_path: Path | None = None,
    measurement_session_path: Path | None = None,
    rejected_photo_candidate_path: Path | None = None,
) -> dict[str, Any]:
    """Propose missing keyboard targets without installing unqualified geometry."""

    catalog = json.loads(target_catalog_path.read_text(encoding="utf-8"))
    geometry_source = geometry_source_path.read_text(encoding="utf-8")
    if "Presentation-only outer modifiers" not in geometry_source:
        raise ValueError("geometry source is not explicitly presentation-only")
    for target_id, seed in _TARGET_EXTENSION_SEEDS.items():
        if seed["source_literal"] not in geometry_source:
            raise ValueError(f"geometry source no longer contains exact {target_id} seed")

    existing_ids = {
        key_id
        for row in catalog["keyboard"]["rows"]
        for key_id in row["key_ids"]
    } | set(catalog["keyboard"]["explicit_targets"])
    required = ("SHIFT", "BACKSLASH", "GRAVE", "LEFT_BRACKET", "RIGHT_BRACKET")
    if existing_ids.intersection(required):
        raise ValueError("proposal target already exists in active keyboard catalog")

    photo_study: dict[str, Any] | None = None
    photo_study_binding: dict[str, Any] | None = None
    if photo_geometry_study_path is not None or photo_source_path is not None:
        if photo_geometry_study_path is None or photo_source_path is None:
            raise ValueError("photo study and source image must be supplied together")
        photo_study = json.loads(photo_geometry_study_path.read_text(encoding="utf-8"))
        if photo_study.get("schema") != "rocell.keyboard_photo_geometry_study.v1":
            raise ValueError("unexpected photo geometry study schema")
        if photo_study.get("status") != "PHOTO_DERIVED_SIMULATION_ONLY_NOMINAL":
            raise ValueError("photo geometry study is not simulation-only nominal")
        if photo_study.get("physical_release_effect") != "NONE":
            raise ValueError("photo geometry study claims physical release effect")
        for count_field in (
            "hardware_write_count", "physical_movement_count", "measurement_reading_count"
        ):
            if photo_study.get(count_field) != 0:
                raise ValueError(f"photo geometry study has nonzero {count_field}")
        source_sha256 = hashlib.sha256(photo_source_path.read_bytes()).hexdigest()
        if photo_study.get("source", {}).get("sha256") != source_sha256:
            raise ValueError("photo geometry study source hash mismatch")
        fit = photo_study.get("fit", {})
        for field in (
            "median_reprojection_error_px", "max_reprojection_error_px",
            "mean_reprojection_error_px",
        ):
            value = fit.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid photo geometry fit metric {field}")
        inferred = photo_study.get("inferred_targets")
        needed_photo_ids = set(required) | {
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"
        }
        if not isinstance(inferred, dict) or set(inferred) != needed_photo_ids:
            raise ValueError("photo geometry study target coverage mismatch")
        for target_id, row in inferred.items():
            point = row.get("inferred_local_xy_mm") if isinstance(row, dict) else None
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in point)
            ):
                raise ValueError(f"invalid photo geometry point for {target_id}")
        photo_study_binding = {
            "path": photo_geometry_study_path.as_posix(),
            "file_sha256": hashlib.sha256(photo_geometry_study_path.read_bytes()).hexdigest(),
            "source_image_path": photo_source_path.as_posix(),
            "source_image_sha256": source_sha256,
            "status": photo_study["status"],
            "fit_diagnostics_only": fit,
            "physical_release_effect": "NONE",
        }

    measurement_session: dict[str, Any] | None = None
    measurement_binding: dict[str, Any] | None = None
    measured_targets: dict[str, dict[str, Any]] = {}
    measured_existing: dict[str, list[float]] = {}
    rejection_binding: dict[str, Any] | None = None
    if measurement_session_path is not None:
        if photo_study is not None:
            raise ValueError("photo study and physical measurement session cannot be combined")
        measurement_session = json.loads(
            measurement_session_path.read_text(encoding="utf-8")
        )
        if measurement_session.get("schema") != "rocell.keyboard_physical_measurement_session.v1":
            raise ValueError("unexpected keyboard measurement session schema")
        if measurement_session.get("status") != "SUFFICIENT_FOR_SIMULATION_GEOMETRY_FIT":
            raise ValueError("keyboard measurement session is not sufficient for simulation fit")
        if measurement_session.get("coordinate_surface") != "KEYCAP_TOP_PRESS_SURFACE":
            raise ValueError("keyboard measurement session uses the wrong surface")
        if measurement_session.get("physical_authority") is not False:
            raise ValueError("keyboard measurement session claims physical authority")
        for count_field in ("hardware_write_count", "physical_movement_count"):
            if measurement_session.get(count_field) != 0:
                raise ValueError(f"keyboard measurement session has nonzero {count_field}")
        rows = measurement_session.get("measurements")
        if not isinstance(rows, list):
            raise ValueError("keyboard measurement session measurements must be an array")
        by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("measurement_id"), str):
                raise ValueError("invalid keyboard measurement row")
            measurement_id = row["measurement_id"]
            if measurement_id in by_id:
                raise ValueError(f"duplicate keyboard measurement {measurement_id}")
            value = row.get("value_mm")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"invalid keyboard measurement value {measurement_id}")
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"invalid keyboard measurement value {measurement_id}")
            if row.get("admission_status") == "REJECTED_FOR_HORIZONTAL_OFFSET":
                continue
            photo_path = row.get("photo_path")
            if photo_path is not None:
                bound_photo = Path(photo_path)
                if not bound_photo.is_file():
                    raise ValueError(f"keyboard measurement photo missing for {measurement_id}")
                photo_bytes = bound_photo.read_bytes()
                if hashlib.sha256(photo_bytes).hexdigest() != row.get("photo_sha256"):
                    raise ValueError(f"keyboard measurement photo hash mismatch for {measurement_id}")
                if len(photo_bytes) != row.get("photo_bytes"):
                    raise ValueError(f"keyboard measurement photo size mismatch for {measurement_id}")
            by_id[measurement_id] = row

        required_measurements = {
            "grave_top_width_x", "grave_top_height_y",
            "reference_1_top_width_x", "reference_1_top_height_y",
            "grave_left_edge_to_1_left_edge_x",
            "grave_front_edge_minus_1_front_edge_y",
            "1_left_edge_to_6_left_edge_x", "6_left_edge_to_equal_left_edge_x",
            "housing_left_to_q_left_top_edge_x",
            "housing_left_to_1_left_top_edge_x",
            "housing_left_to_grave_left_top_edge_x",
            "housing_front_to_1_front_top_edge_y",
            "housing_front_to_q_front_top_edge_y",
            "shift_top_width_x", "shift_top_height_y",
            "housing_left_to_shift_left_top_edge_x",
            "housing_front_to_shift_front_top_edge_y",
            "left_bracket_top_width_x", "left_bracket_top_height_y",
            "right_bracket_top_width_x", "right_bracket_top_height_y",
            "backslash_top_width_x", "backslash_top_height_y",
        }
        missing_measurements = required_measurements - set(by_id)
        if missing_measurements:
            raise ValueError(
                "keyboard measurement session missing required rows: "
                + ", ".join(sorted(missing_measurements))
            )

        def mm(measurement_id: str) -> float:
            return float(by_id[measurement_id]["value_mm"])

        def point(x: float, y: float) -> list[float]:
            return [round(x, 6), round(y, 6)]

        pitch = (
            mm("1_left_edge_to_6_left_edge_x")
            + mm("6_left_edge_to_equal_left_edge_x")
        ) / 11.0
        standard_width = mm("grave_top_width_x")
        standard_height = mm("grave_top_height_y")
        if any(
            not math.isclose(mm(measurement_id), expected, abs_tol=1e-9)
            for measurement_id, expected in (
                ("reference_1_top_width_x", standard_width),
                ("reference_1_top_height_y", standard_height),
                ("left_bracket_top_width_x", standard_width),
                ("left_bracket_top_height_y", standard_height),
                ("right_bracket_top_width_x", standard_width),
                ("right_bracket_top_height_y", standard_height),
                ("backslash_top_width_x", standard_width),
                ("backslash_top_height_y", standard_height),
            )
        ):
            raise ValueError("operator-confirmed standard key dimensions disagree")
        one_center = point(
            mm("housing_left_to_1_left_top_edge_x") + standard_width / 2.0,
            mm("housing_front_to_1_front_top_edge_y") + standard_height / 2.0,
        )
        q_center = point(
            mm("housing_left_to_q_left_top_edge_x") + standard_width / 2.0,
            mm("housing_front_to_q_front_top_edge_y") + standard_height / 2.0,
        )
        grave_center = point(
            mm("housing_left_to_grave_left_top_edge_x") + standard_width / 2.0,
            one_center[1] + mm("grave_front_edge_minus_1_front_edge_y"),
        )
        shift_center = point(
            mm("housing_left_to_shift_left_top_edge_x")
            + mm("shift_top_width_x") / 2.0,
            mm("housing_front_to_shift_front_top_edge_y")
            + mm("shift_top_height_y") / 2.0,
        )
        standard_half_extent = [
            min(7.0, standard_width / 2.0 - 1.0),
            min(7.0, standard_height / 2.0 - 1.0),
        ]
        shift_half_extent = [
            min(7.0, mm("shift_top_width_x") / 2.0 - 1.0),
            min(7.0, mm("shift_top_height_y") / 2.0 - 1.0),
        ]
        measured_targets = {
            "SHIFT": {
                "center": shift_center,
                "half_extent": shift_half_extent,
                "derivation": "DIRECT_HOUSING_ANCHORS_AND_MEASURED_TOP_SIZE",
                "coordinate_class": "MEASURED",
                "coordinate_provenance": {
                    "x": "MEASURED_HOUSING_LEFT_TO_KEY_LEFT_EDGE_PLUS_MEASURED_HALF_WIDTH",
                    "y": "MEASURED_HOUSING_FRONT_TO_KEY_FRONT_EDGE_PLUS_MEASURED_HALF_HEIGHT",
                    "size": "MEASURED_KEYCAP_TOP_WIDTH_AND_HEIGHT",
                },
            },
            "GRAVE": {
                "center": grave_center,
                "half_extent": standard_half_extent,
                "derivation": "DIRECT_HOUSING_ANCHOR_AND_MEASURED_TOP_SIZE",
                "coordinate_class": "MEASURED",
                "coordinate_provenance": {
                    "x": "MEASURED_HOUSING_LEFT_TO_KEY_LEFT_EDGE_PLUS_MEASURED_HALF_WIDTH",
                    "y": "MEASURED_1_ROW_ANCHOR_PLUS_OPERATOR_CONFIRMED_ZERO_ROW_OFFSET",
                    "size": "MEASURED_KEYCAP_TOP_WIDTH_AND_HEIGHT",
                },
            },
            "LEFT_BRACKET": {
                "center": point(q_center[0] + 10.0 * pitch, q_center[1]),
                "half_extent": standard_half_extent,
                "derivation": "Q_HOUSING_ANCHOR_PLUS_TEN_MEASURED_PITCHES",
                "coordinate_class": "MIXED_MEASURED_ANCHOR_TOPOLOGY_INFERRED",
                "coordinate_provenance": {
                    "x": "INFERRED_FROM_MEASURED_Q_ANCHOR_PLUS_TEN_MEASURED_PITCHES",
                    "y": "MEASURED_Q_ROW_HOUSING_FRONT_ANCHOR",
                    "size": "OPERATOR_CONFIRMED_EQUAL_TO_MEASURED_STANDARD_KEY_TOP",
                },
            },
            "RIGHT_BRACKET": {
                "center": point(q_center[0] + 11.0 * pitch, q_center[1]),
                "half_extent": standard_half_extent,
                "derivation": "Q_HOUSING_ANCHOR_PLUS_ELEVEN_MEASURED_PITCHES",
                "coordinate_class": "MIXED_MEASURED_ANCHOR_TOPOLOGY_INFERRED",
                "coordinate_provenance": {
                    "x": "INFERRED_FROM_MEASURED_Q_ANCHOR_PLUS_ELEVEN_MEASURED_PITCHES",
                    "y": "MEASURED_Q_ROW_HOUSING_FRONT_ANCHOR",
                    "size": "OPERATOR_CONFIRMED_EQUAL_TO_MEASURED_STANDARD_KEY_TOP",
                },
            },
            "BACKSLASH": {
                "center": point(q_center[0] + 12.0 * pitch, q_center[1]),
                "half_extent": standard_half_extent,
                "derivation": "Q_HOUSING_ANCHOR_PLUS_TWELVE_MEASURED_PITCHES",
                "coordinate_class": "MIXED_MEASURED_ANCHOR_TOPOLOGY_INFERRED",
                "coordinate_provenance": {
                    "x": "INFERRED_FROM_MEASURED_Q_ANCHOR_PLUS_TWELVE_MEASURED_PITCHES",
                    "y": "MEASURED_Q_ROW_HOUSING_FRONT_ANCHOR",
                    "size": "OPERATOR_CONFIRMED_EQUAL_TO_MEASURED_STANDARD_KEY_TOP",
                },
            },
        }
        measured_existing = {"1": one_center, "Q": q_center}
        for index, target_id in enumerate(
            ("2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"),
            start=1,
        ):
            measured_existing[target_id] = point(
                one_center[0] + index * pitch,
                one_center[1],
            )
        for index, target_id in enumerate(
            ("W", "E", "R", "T", "Y", "U", "I", "O", "P"), start=1
        ):
            measured_existing[target_id] = point(
                q_center[0] + index * pitch,
                q_center[1],
            )

        if rejected_photo_candidate_path is None:
            raise ValueError("rejected photo candidate receipt is required")
        rejected = json.loads(rejected_photo_candidate_path.read_text(encoding="utf-8"))
        if rejected.get("schema") != "rocell.photo_catalog_candidate_rejection.v1":
            raise ValueError("unexpected rejected photo candidate receipt schema")
        if rejected.get("status") != "REJECTED_BY_PHYSICAL_MEASUREMENT":
            raise ValueError("photo candidate receipt does not preserve rejection")
        if rejected.get("active_repository_catalog_changed") is not False:
            raise ValueError("rejected photo candidate receipt claims catalog change")
        rejection_binding = {
            "path": rejected_photo_candidate_path.as_posix(),
            "file_sha256": hashlib.sha256(
                rejected_photo_candidate_path.read_bytes()
            ).hexdigest(),
            "candidate_file_sha256": rejected["candidate_file_sha256"],
            "status": rejected["status"],
        }
        measurement_binding = {
            "path": measurement_session_path.as_posix(),
            "file_sha256": hashlib.sha256(measurement_session_path.read_bytes()).hexdigest(),
            "keyboard_identity": measurement_session["keyboard_identity"],
            "measurement_count": len(rows),
            "pitch_mm": pitch,
            "standard_key_top_mm": [standard_width, standard_height],
            "single_reading_limit_applies": True,
            "scope": "SIMULATION_GEOMETRY_FIT_NOT_PHYSICAL_COMMISSIONING",
        }

    targets: list[dict[str, Any]] = []
    for target_id in required:
        seed = _TARGET_EXTENSION_SEEDS.get(target_id)
        if seed is None and photo_study is None and measurement_session is None:
            targets.append({
                "target_id": target_id,
                "proposal_status": "BLOCKED_AWAITING_DIRECT_CALIPER_MEASUREMENT",
                "press_point_xy_mm": None,
                "safe_half_extent_mm": None,
                "geometry_source": None,
                "geometry_limitation": (
                    "No repository source defines the Grave key. Direct relative-key measurement "
                    "is required by the bound method. Pitch extrapolation is rejected: "
                    "one 19.05 mm pitch left of key 1 gives x=2.95 mm, which cannot contain the "
                    "ordinary 7 mm half-width inside the 315 mm device boundary."
                ),
                "simulated_camera_visibility": "NOT_TESTABLE_WITHOUT_GEOMETRY",
                "arm_runtime_ik": "NOT_TESTABLE_WITHOUT_GEOMETRY_SHARED_WITH_ARM_RUNTIME",
                "simulated_parked_arm_self_occlusion": "NOT_TESTABLE_WITHOUT_GEOMETRY",
                "physical_camera_visibility": "COMMISSIONING_ONLY_NOT_RENDER_GATE",
                "physical_parked_arm_self_occlusion": "COMMISSIONING_ONLY_NOT_RENDER_GATE",
            })
            continue
        measured = measured_targets.get(target_id)
        photo_point = (
            photo_study["inferred_targets"][target_id]["inferred_local_xy_mm"]
            if photo_study is not None
            else None
        )
        targets.append({
            "target_id": target_id,
            "proposal_status": (
                "MEASUREMENT_DERIVED_SIMULATION_ONLY_PENDING_SHARED_REVIEW"
                if measured is not None
                else
                "PHOTO_DERIVED_SIMULATION_ONLY_PENDING_SHARED_REVIEW"
                if photo_study is not None
                else "PROVISIONAL_SIMULATION_ONLY_PENDING_SHARED_REVIEW"
            ),
            "press_point_xy_mm": (
                measured["center"] if measured is not None
                else photo_point or seed["proposed_press_point_xy_mm"]
            ),
            "safe_half_extent_mm": (
                measured["half_extent"] if measured is not None
                else [7.0, 7.0] if seed is None
                else seed["proposed_safe_half_extent_mm"]
            ),
            "press_point_rule": (
                measured["derivation"] if measured is not None
                else
                "MANUALLY_ANNOTATED_KEY_CENTER_PROJECTED_INTO_NOMINAL_KEYBOARD_FRAME"
                if photo_study is not None
                else seed["press_point_rule"]
            ),
            "coordinate_class": (
                measured["coordinate_class"] if measured is not None else None
            ),
            "coordinate_provenance": (
                measured["coordinate_provenance"] if measured is not None else None
            ),
            "presentation_key_center_xy_mm": (
                None if seed is None else seed["presentation_center_xy_mm"]
            ),
            "presentation_key_width_mm": (
                None if seed is None else seed["presentation_width_mm"]
            ),
            "geometry_source": {
                "path": geometry_source_path.as_posix(),
                "file_sha256": hashlib.sha256(geometry_source_path.read_bytes()).hexdigest(),
                "source_state": "PRESENTATION_ONLY_NOT_CONTROL_OR_COMMISSIONING_AUTHORITY",
                "photo_study": photo_study_binding,
                "physical_measurement_session": measurement_binding,
            },
            "geometry_limitation": (
                "The measurements use single readings; bracket and backslash centers are inferred "
                "from the measured pitch and existing topology. The proposed region may seed "
                "synthetic/shared review only."
                if measured is not None
                else "The source is a visual presentation model and, when present, a single "
                "manually annotated angled photograph. Neither is a product drawing or "
                "measurement. The proposed region may seed synthetic/shared review only."
            ),
            "simulated_camera_visibility": "PENDING_SIMULATED_PARKED_CAMERA_CHECK",
            "arm_runtime_ik": "PENDING_ARM_LANE_READ_ONLY_IK_CHECK",
            "simulated_parked_arm_self_occlusion": "PENDING_SIMULATED_PARKED_ARM_PROJECTION_CHECK",
            "physical_camera_visibility": "COMMISSIONING_ONLY_NOT_RENDER_GATE",
            "physical_parked_arm_self_occlusion": "COMMISSIONING_ONLY_NOT_RENDER_GATE",
        })

    render_blockers = [
        *([] if photo_study is not None or measurement_session is not None
          else ["GRAVE_DIRECT_CALIPER_MEASUREMENT_PENDING"]),
        *(["PHOTO_DERIVED_GEOMETRY_NOT_INSTALLED_IN_SHARED_CATALOG"] if photo_study is not None else []),
        *(["MEASUREMENT_DERIVED_GEOMETRY_NOT_INSTALLED_IN_SHARED_CATALOG"]
          if measurement_session is not None else []),
        "FIVE_TARGETS_NOT_INSTALLED_IN_SHARED_CATALOG",
        "SIMULATED_PARKED_CAMERA_VISIBILITY_NOT_PROVEN",
        "SIMULATED_PARKED_ARM_NON_OCCLUSION_NOT_PROVEN",
        "ARM_RUNTIME_IK_REACHABILITY_NOT_PROVEN",
        "ARM_RUNTIME_REACH_OPTIMIZER_CURRENTLY_LOCKED_TO_75_TARGETS",
        "TARGET_CATALOG_HASH_NOT_REFROZEN",
        "V5_5_IDENTITIES_NOT_AMENDED_TO_80_TARGETS",
        "V5_5_POWER_CHECK_NOT_RERUN",
    ]
    existing_target_corrections: list[dict[str, Any]] = []
    if photo_study is not None:
        for target_id in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"):
            row = photo_study["current_number_row_comparison"][target_id]
            existing_target_corrections.append({
                "target_id": target_id,
                "current_press_point_xy_mm": row["current_local_xy_mm"],
                "photo_derived_press_point_xy_mm": row["photo_inferred_local_xy_mm"],
                "delta_mm": row["delta_mm"],
                "status": "SIMULATION_ONLY_CORRECTION_PENDING_SHARED_REVIEW",
            })
    elif measurement_session is not None:
        current_centers = {
            target_id: [22.0 + index * 19.05, 111.0]
            for index, target_id in enumerate(
                ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL")
            )
        }
        current_centers.update({
            target_id: [31.5 + index * 19.05, 90.0]
            for index, target_id in enumerate(("Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"))
        })
        for target_id, measured_center in measured_existing.items():
            current = current_centers[target_id]
            existing_target_corrections.append({
                "target_id": target_id,
                "current_press_point_xy_mm": current,
                "measurement_derived_press_point_xy_mm": measured_center,
                "delta_mm": [
                    measured_center[0] - current[0],
                    measured_center[1] - current[1],
                ],
                "status": "SIMULATION_ONLY_CORRECTION_PENDING_SHARED_REVIEW",
            })
    measurement_encoded = json.dumps(
        _GRAVE_MEASUREMENT_METHOD,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    core: dict[str, Any] = {
        "schema": "rocell.ai_keyboard_target_extension_proposal.v1",
        "scope": "SYNTHETIC_SHARED_CATALOG_PROPOSAL_NO_COMMISSIONING_OR_PHYSICAL_AUTHORITY",
        "source_commit": source_commit,
        "active_catalog": {
            "path": target_catalog_path.as_posix(),
            "file_sha256": hashlib.sha256(target_catalog_path.read_bytes()).hexdigest(),
            "keyboard_target_count": len(existing_ids),
            "total_target_count": len(existing_ids) + 29,
            "unchanged": True,
        },
        "targets": targets,
        "existing_target_corrections": existing_target_corrections,
        "photo_geometry_study": photo_study_binding,
        "physical_measurement_session": measurement_binding,
        "rejected_photo_candidate": rejection_binding,
        "shared_catalog_install_authorized": False,
        "compiler_expansion_authorized": False,
        "grave_measurement": {
            "status": (
                "MEASURED_SINGLE_READING_SIMULATION_FIT_ONLY"
                if measurement_session is not None
                else "AWAITING_DIRECT_PHYSICAL_READINGS"
            ),
            "method": _GRAVE_MEASUREMENT_METHOD,
            "method_sha256": hashlib.sha256(measurement_encoded).hexdigest(),
            "derived_geometry": measured_targets.get("GRAVE"),
            "simulation_photo_nominal": (
                None if photo_study is None else photo_study["inferred_targets"]["GRAVE"]
            ),
        },
        "v5_5_render_gate": {
            "evidence_scope": "SIMULATION_AND_OFFLINE_ARM_RUNTIME_ONLY",
            "required_total_target_count_after_admission": 80,
            "render_authorized": False,
            "evaluation_remains_unrendered": True,
            "blockers": render_blockers,
            "physical_camera_evidence_required": False,
        },
        "arm_lane_catalog_contract": {
            "required_behavior": "VALIDATE_LOADED_FROZEN_CATALOG_HASH_THEN_ENUMERATE_ITS_CONTENTS",
            "prohibited_behavior": "HARDCODE_EXPECTED_TOTAL_OR_PER_DEVICE_TARGET_COUNTS",
            "required_checks": [
                "LOADED_CATALOG_HASH_EQUALS_ACTIVE_FROZEN_CATALOG_HASH",
                "EVERY_ENUMERATED_TARGET_HAS_VALID_DEVICE_ID_CENTER_SAFE_REGION_AND_SOURCE_STATE",
                "EVERY_ENUMERATED_TARGET_IS_SCREENED_EXACTLY_ONCE",
                "REPORT_BINDS_CATALOG_HASH_AND_ORDERED_TARGET_IDENTITIES",
                "CATALOG_MUTATION_OR_DUPLICATE_TARGET_ID_FAILS_CLOSED",
            ],
            "arm_lane_status_changed": False,
        },
        "physical_commissioning_gate": {
            "hardware_use_authorized": False,
            "required_checks": [
                "COMMISSIONED_CAMERA_VISIBILITY_FOR_ALL_FIVE_TARGETS",
                "COMMISSIONED_PARKED_ARM_NON_OCCLUSION_FOR_ALL_FIVE_TARGETS",
                "MEASURED_TARGET_GEOMETRY_BOUND_TO_ACTIVE_CATALOG",
            ],
            "blocks_synthetic_render": False,
        },
        "ownership": {
            "ai_lane": "PROPOSAL_SOURCE_BINDING_AND_SYNTHETIC_CORPUS_ADMISSION",
            "arm_lane": "READ_ONLY_IK_REACHABILITY_DECISION",
            "shared_commissioning": "PHYSICAL_CAMERA_VISIBILITY_AND_PARKED_ARM_OCCLUSION_BEFORE_HARDWARE_USE",
        },
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    encoded = json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return {**core, "proposal_sha256": hashlib.sha256(encoded).hexdigest()}


def inspect(proposal: dict[str, str], observation: dict[str, Any]) -> dict[str, Any]:
    """Compile a supported proposal without camera, controller, or arm access."""

    validate_proposal(proposal)
    if not isinstance(observation, dict) or observation.get("ref") != proposal["observation_ref"]:
        raise ValueError("observation reference mismatch")

    base = {
        "schema": "rocell.ai_plan_result.v0",
        "request_id": proposal["request_id"],
        "observation_ref": proposal["observation_ref"],
    }

    def blocked(reason: str) -> dict[str, Any]:
        result = {**base, "status": "blocked", "reason": reason}
        validate_result(result)
        return result

    if observation.get("fresh") is not True:
        return blocked("stale_observation")
    if proposal["decision"] != "type_text":
        return blocked(proposal["reason"])
    if proposal["device"] == "phone" and observation.get("phone_state") != "KEYBOARD_LOWER":
        return blocked("phone_state_unverified")
    if proposal["device"] == "keyboard" and any(
        character in _DESKTOP_SHIFTED_CHARACTERS for character in proposal["text"]
    ):
        return blocked("keyboard_modifier_uncommissioned")
    if proposal["device"] == "phone" and any(
        character in _PHONE_LAYERED_CHARACTERS
        and character not in {".", "\n"}
        for character in proposal["text"]
    ):
        return blocked("phone_layer_uncommissioned")
    try:
        plan = compile_development_text(proposal["device"], proposal["text"])
    except UnsupportedCharacterError:
        return blocked("unsupported_by_profile")
    except PhoneStateError:
        return blocked("phone_state_unverified")
    result = {
        **base,
        "status": "accepted",
        "profile_id": plan.profile_id,
        "plan_hash": plan.plan_hash,
        "action_plan": plan.to_dict(),
    }
    validate_result(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-catalog", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-extension-geometry-source", type=Path)
    parser.add_argument("--photo-geometry-study", type=Path)
    parser.add_argument("--photo-source", type=Path)
    parser.add_argument("--measurement-session", type=Path)
    parser.add_argument("--rejected-photo-candidate", type=Path)
    args = parser.parse_args()
    if args.target_extension_geometry_source is None:
        result = build_planner_capability_audit(args.target_catalog, args.source_commit)
    else:
        result = build_keyboard_target_extension_proposal(
            args.target_catalog,
            args.target_extension_geometry_source,
            args.source_commit,
            photo_geometry_study_path=args.photo_geometry_study,
            photo_source_path=args.photo_source,
            measurement_session_path=args.measurement_session,
            rejected_photo_candidate_path=args.rejected_photo_candidate,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
