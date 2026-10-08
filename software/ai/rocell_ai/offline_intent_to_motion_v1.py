"""Admit a closed offline typing intent into the bounded motion planner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .c03_arm_route_reconciliation_v1 import canonical_hash, file_hash, load_strict_json
from .dynamic_intent_to_motion_v1 import (
    parse_dynamic_intent_to_motion_v1,
    run_dynamic_intent_to_motion_v1,
)


INTENT_SCHEMA = "rocell.offline_typing_intent.v1"
RESULT_SCHEMA = "tactevra.offline_intent_to_simulated_motion.v1"
STATUS = "PASS_OFFLINE_TYPE_TEXT_TO_SIMULATED_IK_RETAIN_BLOCKERS"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
_FIELDS = {
    "TYPE_TEXT": {"schema", "intent_type", "device", "text"},
    "PRESS_KEY": {"schema", "intent_type", "device", "key"},
    "CLARIFY": {"schema", "intent_type", "question"},
    "REFUSE": {"schema", "intent_type", "reason"},
}


class OfflineIntentToMotionV1Error(ValueError):
    """The closed intent or its zero-authority composition failed closed."""


def parse_offline_typing_intent_v1(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the closed intent union without accepting extension fields."""

    if not isinstance(document, Mapping) or document.get("schema") != INTENT_SCHEMA:
        raise OfflineIntentToMotionV1Error("offline intent schema is invalid")
    intent_type = document.get("intent_type")
    expected = _FIELDS.get(intent_type)
    if expected is None or set(document) != expected:
        raise OfflineIntentToMotionV1Error("offline intent fields differ from contract")
    if intent_type in {"TYPE_TEXT", "PRESS_KEY"}:
        if document.get("device") not in {"KEYBOARD", "PHONE"}:
            raise OfflineIntentToMotionV1Error("offline intent device is invalid")
        if intent_type == "PRESS_KEY" and document["device"] != "KEYBOARD":
            raise OfflineIntentToMotionV1Error("PRESS_KEY supports only KEYBOARD")
    value_field = {
        "TYPE_TEXT": "text",
        "PRESS_KEY": "key",
        "CLARIFY": "question",
        "REFUSE": "reason",
    }[intent_type]
    value = document[value_field]
    maximum = 256 if intent_type == "TYPE_TEXT" else 32 if intent_type == "PRESS_KEY" else 512
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise OfflineIntentToMotionV1Error(f"{value_field} is invalid")
    return dict(document)


def run_offline_intent_to_motion_v1(
    intent: Mapping[str, Any],
    *,
    fixture_path: Path,
    workspace: Path,
    derived_workspace: Path,
) -> dict[str, Any]:
    """Route only keyboard TYPE_TEXT to the ARM-520 dynamic planner."""

    admitted = parse_offline_typing_intent_v1(intent)
    if admitted["intent_type"] != "TYPE_TEXT":
        raise OfflineIntentToMotionV1Error("intent is non-actionable at this adapter")
    if admitted["device"] != "KEYBOARD":
        raise OfflineIntentToMotionV1Error("dynamic motion supports only KEYBOARD")
    dynamic = run_dynamic_intent_to_motion_v1(
        fixture_path,
        [admitted["text"]],
        workspace=workspace,
        derived_workspace=derived_workspace,
    )
    parse_dynamic_intent_to_motion_v1(dynamic)
    case = dynamic["cases"][0]
    if case["requested_text"] != admitted["text"]:
        raise OfflineIntentToMotionV1Error("intent text changed before planning")
    core = {
        "schema": RESULT_SCHEMA,
        "status": STATUS,
        "scope": SCOPE,
        "implementation_sha256": file_hash(Path(__file__)),
        "intent": admitted,
        "intent_sha256": canonical_hash(admitted),
        "dynamic_result": dynamic,
        "dynamic_result_receipt_sha256": dynamic["receipt_sha256"],
        "ordered_target_ids": case["ordered_target_ids"],
        "trajectory_sample_count": case["route_result"]["trajectory_sample_count"],
        "ik_accepted_sample_count": case["route_result"]["ik_accepted_sample_count"],
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "terminal_blockers": dynamic["terminal_blockers"],
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    result = {**core, "receipt_sha256": canonical_hash(core)}
    parse_offline_intent_to_motion_result_v1(result)
    return result


def parse_offline_intent_to_motion_result_v1(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an intent composition receipt and its nested ARM-520 receipt."""

    if not isinstance(document, Mapping):
        raise OfflineIntentToMotionV1Error("result must be an object")
    claimed = document.get("receipt_sha256")
    unsigned = {key: value for key, value in document.items() if key != "receipt_sha256"}
    if not isinstance(claimed, str) or canonical_hash(unsigned) != claimed:
        raise OfflineIntentToMotionV1Error("result receipt changed")
    if (
        document.get("schema") != RESULT_SCHEMA
        or document.get("status") != STATUS
        or document.get("scope") != SCOPE
    ):
        raise OfflineIntentToMotionV1Error("result identity changed")
    intent = parse_offline_typing_intent_v1(document.get("intent"))
    if intent["intent_type"] != "TYPE_TEXT" or intent["device"] != "KEYBOARD":
        raise OfflineIntentToMotionV1Error("result contains a non-actionable intent")
    if document.get("intent_sha256") != canonical_hash(intent):
        raise OfflineIntentToMotionV1Error("intent digest changed")
    dynamic = document.get("dynamic_result")
    if not isinstance(dynamic, Mapping):
        raise OfflineIntentToMotionV1Error("dynamic result is absent")
    parse_dynamic_intent_to_motion_v1(dynamic)
    if document.get("dynamic_result_receipt_sha256") != dynamic.get("receipt_sha256"):
        raise OfflineIntentToMotionV1Error("dynamic result binding changed")
    case = dynamic["cases"][0]
    if (
        len(dynamic["cases"]) != 1
        or case["requested_text"] != intent["text"]
        or document.get("ordered_target_ids") != case["ordered_target_ids"]
        or document.get("trajectory_sample_count")
        != case["route_result"]["trajectory_sample_count"]
        or document.get("ik_accepted_sample_count")
        != case["route_result"]["ik_accepted_sample_count"]
    ):
        raise OfflineIntentToMotionV1Error("intent-to-route binding changed")
    for field, expected in {
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }.items():
        if document.get(field) != expected:
            raise OfflineIntentToMotionV1Error(f"result violates boundary at {field}")
    if document.get("terminal_blockers") != dynamic.get("terminal_blockers"):
        raise OfflineIntentToMotionV1Error("terminal blockers changed")
    return dict(document)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Admit one closed offline typing intent to simulated motion"
    )
    parser.add_argument("intent", type=Path)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--derived-workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    intent = load_strict_json(args.intent)
    result = run_offline_intent_to_motion_v1(
        intent,
        fixture_path=args.fixture,
        workspace=args.workspace.resolve(),
        derived_workspace=args.derived_workspace.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": result["status"],
        "targets": result["ordered_target_ids"],
        "trajectory_sample_count": result["trajectory_sample_count"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OfflineIntentToMotionV1Error",
    "parse_offline_typing_intent_v1",
    "parse_offline_intent_to_motion_result_v1",
    "run_offline_intent_to_motion_v1",
]
