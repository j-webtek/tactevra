"""Short-path successor for the coherent C03 route workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .c03_arm_route_reconciliation_v1 import canonical_hash, file_hash, load_strict_json
from .c03_exact_route_reconstruction_v1 import run_c03_exact_route
from .c03_exact_route_reconstruction_v1_1 import _materialize, _resolve


FIXTURE_SCHEMA = "tactevra.c03_exact_route_reconstruction_fixture.v1_2"
RESULT_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1_2"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    fixture = load_strict_json(path)
    claimed = fixture.pop("fixture_sha256", None)
    if claimed != canonical_hash(fixture):
        raise ValueError("short-path C03 route fixture hash changed")
    fixture["fixture_sha256"] = claimed
    if fixture.get("schema") != FIXTURE_SCHEMA or fixture.get("scope") != SCOPE:
        raise ValueError("unexpected short-path C03 route fixture identity")
    if fixture.get("physical_authority") is not False or any(
        fixture["counters"].values()
    ):
        raise ValueError("short-path C03 route fixture violates zero authority")
    for name, binding in fixture["bindings"].items():
        source = _resolve(binding["path"], workspace)
        if not source.is_file() or file_hash(source) != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {name}")
    return fixture


def run_short_path_c03_route(
    fixture_path: Path, *, workspace: Path
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path, workspace)
    derived, workspace_receipt = _materialize(fixture, workspace)
    route_result = run_c03_exact_route(
        derived / fixture["predecessor_fixture_path"], workspace=derived
    )
    if route_result["hardware_writes"] != 0 or route_result["physical_movements"] != 0:
        raise ValueError("predecessor route result violates zero authority")
    core = {
        "schema": RESULT_SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "coherent_workspace_receipt": workspace_receipt,
        "predecessor_fixture_sha256": route_result["fixture_sha256"],
        "route_result": route_result,
        "decision": route_result["decision"],
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": fixture["limitations"],
    }
    return {**core, "receipt_sha256": canonical_hash(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_short_path_c03_route(
        args.fixture, workspace=args.workspace.resolve()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    route = result["route_result"]
    print(json.dumps({
        "decision": result["decision"],
        "trajectory_sample_count": route["trajectory_sample_count"],
        "ik_accepted_sample_count": route["ik_accepted_sample_count"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
