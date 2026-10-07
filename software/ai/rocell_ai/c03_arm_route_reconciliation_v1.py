"""Fail-closed reconciliation of C03 contact evidence with the promoted arm route."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_strict_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verify_canonical_field(document: Mapping[str, Any], field: str) -> None:
    claimed = document.get(field)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError(f"missing or invalid {field}")
    core = {key: value for key, value in document.items() if key != field}
    if canonical_hash(core) != claimed:
        raise ValueError(f"{field} does not match canonical content")


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = load_strict_json(path)
    _verify_canonical_field(fixture, "fixture_sha256")
    if fixture.get("schema") != "tactevra.c03_arm_route_reconciliation_fixture.v1":
        raise ValueError("unexpected reconciliation fixture schema")
    if fixture.get("physical_authority") is not False:
        raise ValueError("fixture must retain zero physical authority")
    counters = fixture.get("counters")
    if not isinstance(counters, dict) or any(counters.get(name) != 0 for name in (
        "hardware_write_count", "physical_movement_count", "real_command_count",
        "transport_count", "permit_count",
    )):
        raise ValueError("fixture counters violate zero authority")
    return fixture


def _resolve(path_text: str, workspace: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else workspace / path


def _load_binding(fixture: Mapping[str, Any], name: str, workspace: Path) -> dict[str, Any]:
    binding = fixture["bindings"][name]
    path = _resolve(binding["path"], workspace)
    if not path.is_file():
        raise ValueError(f"missing bound artifact {name}: {path}")
    actual_file_hash = file_hash(path)
    if actual_file_hash != binding["sha256"]:
        raise ValueError(f"bound artifact hash mismatch: {name}")
    document = load_strict_json(path)
    _verify_canonical_field(document, "receipt_sha256")
    if document["receipt_sha256"] != binding["receipt_sha256"]:
        raise ValueError(f"bound artifact receipt mismatch: {name}")
    if document.get("schema") != binding["schema"]:
        raise ValueError(f"bound artifact schema mismatch: {name}")
    return document


def _require_zero_authority(document: Mapping[str, Any], *, count_suffix: str = "") -> None:
    if document.get("physical_authority") is not False:
        raise ValueError("source artifact claims physical authority")
    for base in ("hardware_write", "physical_movement"):
        field = f"{base}_{count_suffix}" if count_suffix else f"{base}s"
        if document.get(field) != 0:
            raise ValueError(f"source artifact violates zero authority: {field}")


def reconcile(fixture_path: Path, workspace: Path) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    envelope = _load_binding(fixture, "c03_recipe_envelope", workspace)
    clearance = _load_binding(fixture, "c03_key_clearance", workspace)
    promoted = _load_binding(fixture, "promoted_full_route", workspace)
    intake = _load_binding(fixture, "partitioned_collision_intake", workspace)

    _require_zero_authority(envelope, count_suffix="count")
    _require_zero_authority(clearance, count_suffix="count")
    if promoted.get("physical_authority") is not False or promoted.get("hardware_writes") != 0 \
            or promoted.get("physical_movements") != 0:
        raise ValueError("promoted route violates zero authority")
    if intake.get("hardware_access") is not False or intake.get("hardware_writes") != 0 \
            or intake.get("hardware_commands_generated") != 0:
        raise ValueError("collision intake violates zero authority")

    expected = fixture["expected"]
    if envelope.get("decision") != "PASS_EXPLORATORY_WS2_RECIPE_ENVELOPE":
        raise ValueError("C03 recipe envelope is not admitted")
    if clearance.get("decision") != "PASS_EXPLORATORY_WS3_EXACT_KEY_CLEARANCE":
        raise ValueError("C03 key-clearance screen is not admitted")
    if clearance.get("press_recipe_receipt_sha256") != envelope["receipt_sha256"]:
        raise ValueError("C03 clearance does not bind the recipe envelope")
    if envelope.get("tool_length_mm") != expected["c03_tool"]["total_length_mm"]:
        raise ValueError("C03 total tool length differs from fixture")
    geometry = envelope.get("tool_geometry")
    if geometry != expected["c03_tool"]["geometry"]:
        raise ValueError("C03 tip geometry differs from fixture")
    if promoted.get("trajectory_sample_count") != expected["promoted_route_sample_count"]:
        raise ValueError("promoted route sample count differs from fixture")
    promoted_length = promoted.get("reconstruction", {}).get("tool_length_mm")
    if promoted_length != expected["promoted_route_tool_length_mm"]:
        raise ValueError("promoted route tool length differs from fixture")
    if intake.get("installed_collision_gate_cleared") is not False \
            or intake.get("continuous_collision_proven") is not False:
        raise ValueError("collision intake unexpectedly claims a cleared gate")
    intake_blockers = intake.get("partitioned_collision_intake", {}).get("blockers")
    if intake_blockers != expected["intake_blockers"]:
        raise ValueError("collision intake blockers differ from fixture")

    c03_length = envelope["tool_length_mm"]
    if c03_length == promoted_length:
        raise ValueError("fixture expected a tool identity mismatch but lengths match")

    blockers = [
        "C03_PROMOTED_ROUTE_TOOL_IDENTITY_MISMATCH",
        "SOURCE_DESTINATION_ORIENTATION_TRANSITION_UNSCREENED",
        "FULL_ROBOT_AND_WORKCELL_CONTINUOUS_COLLISION_UNPROVEN",
        *intake_blockers,
    ]
    core = {
        "schema": "tactevra.c03_arm_route_reconciliation_result.v1",
        "scope": "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY",
        "decision": "STOP_C03_PROMOTED_ROUTE_TOOL_IDENTITY_MISMATCH",
        "fixture_sha256": fixture["fixture_sha256"],
        "source_receipts": {
            "c03_recipe_envelope": envelope["receipt_sha256"],
            "c03_key_clearance": clearance["receipt_sha256"],
            "promoted_full_route": promoted["receipt_sha256"],
            "partitioned_collision_intake": intake["receipt_sha256"],
        },
        "c03_candidate": {
            "tool_total_length_mm": c03_length,
            "tip_geometry": geometry,
            "screened_ordered_pair_count": clearance["row_count"] // 6,
            "screened_row_count": clearance["row_count"],
            "minimum_key_clearance_mm": clearance["minimum_key_clearance_mm"],
            "fixed_orientation_only": True,
        },
        "promoted_arm_route": {
            "tool_total_length_mm": promoted_length,
            "trajectory_sample_count": promoted["trajectory_sample_count"],
            "continuous_collision_proven": intake["continuous_collision_proven"],
            "installed_collision_gate_cleared": intake["installed_collision_gate_cleared"],
        },
        "tool_length_difference_mm": abs(promoted_length - c03_length),
        "blockers": blockers,
        "next_dependency": (
            "Reconstruct and screen the promoted full arm route with the exact admitted "
            "110 mm C03 tool identity, including orientation transitions, then bind an "
            "installed measured collision profile and fresh observed start state."
        ),
        "collision_screen_executed": False,
        "controller_commands": [],
        "hardware_access": False,
        "hardware_commands_generated": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "permits": 0,
        "physical_authority": False,
        "limitations": [
            "This result reconciles identities and blockers; it executes no collision simulation.",
            "The C03 pass covers key geometry only and omits source-to-destination orientation change.",
            "The promoted route was reconstructed for a different total tool length.",
            "No installed measured collision profile or fresh observed start state is supplied.",
            "No controller, transport, permit, hardware, or physical authority is granted.",
        ],
    }
    return {**core, "receipt_sha256": canonical_hash(core)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reconcile(args.fixture, args.workspace.resolve())
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
