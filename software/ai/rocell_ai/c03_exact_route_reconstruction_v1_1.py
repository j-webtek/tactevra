"""Run the frozen C03 route inside a coherently relocked simulation workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from typing import Any, Mapping

from .c03_arm_route_reconciliation_v1 import (
    canonical_hash,
    file_hash,
    load_strict_json,
)
from .c03_exact_route_reconstruction_v1 import run_c03_exact_route


FIXTURE_SCHEMA = "tactevra.c03_exact_route_reconstruction_fixture.v1_1"
RESULT_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1_1"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def _resolve(path_text: str, workspace: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else workspace / path


def load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    fixture = load_strict_json(path)
    claimed = fixture.pop("fixture_sha256", None)
    if claimed != canonical_hash(fixture):
        raise ValueError("coherent C03 route fixture hash changed")
    fixture["fixture_sha256"] = claimed
    if fixture.get("schema") != FIXTURE_SCHEMA or fixture.get("scope") != SCOPE:
        raise ValueError("unexpected coherent C03 route fixture identity")
    if fixture.get("physical_authority") is not False or any(
        fixture["counters"].values()
    ):
        raise ValueError("coherent C03 route fixture violates zero authority")
    for name, binding in fixture["bindings"].items():
        source = _resolve(binding["path"], workspace)
        if not source.is_file() or file_hash(source) != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {name}")
    return fixture


def _git_output(workspace: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        check=True,
        capture_output=True,
    ).stdout


def _materialize(
    fixture: Mapping[str, Any], source_workspace: Path
) -> tuple[Path, dict[str, Any]]:
    contract = fixture["coherent_workspace"]
    destination = Path(contract["path"]).resolve()
    allowed_root = Path(contract["allowed_root"]).resolve()
    try:
        destination.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError("derived workspace escapes its evidence root") from exc
    if destination == allowed_root or destination == source_workspace.resolve():
        raise ValueError("derived workspace target is unsafe")
    source_commit = contract["source_tree_commit"]
    resolved_commit = _git_output(
        source_workspace, "rev-parse", f"{source_commit}^{{commit}}"
    ).decode().strip()
    if resolved_commit != source_commit:
        raise ValueError("source tree commit identity changed")
    tracked = [
        item for item in _git_output(
            source_workspace, "ls-tree", "-r", "--name-only", "-z", source_commit
        ).decode().split("\0")
        if item
    ]
    if len(tracked) != contract["expected_tracked_file_count"]:
        raise ValueError("source tree file population changed")

    staging = destination.with_name(destination.name + ".staging")
    for path in (staging, destination):
        if path.exists():
            shutil.rmtree(path)
    staging.mkdir(parents=True)
    archive = subprocess.Popen(
        ["git", "archive", "--format=tar", source_commit],
        cwd=source_workspace,
        stdout=subprocess.PIPE,
    )
    if archive.stdout is None:
        raise RuntimeError("git archive did not expose stdout")
    with tarfile.open(fileobj=archive.stdout, mode="r|") as stream:
        stream.extractall(staging, filter="data")
    if archive.wait() != 0:
        raise RuntimeError("git archive failed")

    candidate_source = _resolve(
        fixture["bindings"]["c03_candidate_target_catalog"]["path"],
        source_workspace,
    )
    candidate_target = staging / "software/config/nominal_target_profiles.json"
    candidate_target.write_bytes(candidate_source.read_bytes())
    if file_hash(candidate_target) != fixture["bindings"][
        "c03_candidate_target_catalog"
    ]["sha256"]:
        raise ValueError("materialized candidate catalog bytes changed")

    lock_path = staging / "software/config/simulation_bundle_lock.json"
    lock = load_strict_json(lock_path)
    lock["bundle_id"] = contract["bundle_id"]
    lock["artifacts"]["nominal_target_profiles"]["sha256"] = file_hash(
        candidate_target
    )
    lock_path.write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    staging.replace(destination)
    receipt_core = {
        "schema": "tactevra.c03_coherent_workspace_receipt.v1",
        "source_tree_commit": source_commit,
        "source_tracked_file_count": len(tracked),
        "bundle_id": lock["bundle_id"],
        "bundle_lock_sha256": file_hash(
            destination / "software/config/simulation_bundle_lock.json"
        ),
        "target_catalog_sha256": file_hash(
            destination / "software/config/nominal_target_profiles.json"
        ),
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    receipt = {**receipt_core, "receipt_sha256": canonical_hash(receipt_core)}
    (destination / "c03_coherent_workspace_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination, receipt


def run_coherent_c03_route(
    fixture_path: Path, *, workspace: Path
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path, workspace)
    derived, workspace_receipt = _materialize(fixture, workspace)
    predecessor_path = derived / fixture["predecessor_fixture_path"]
    route_result = run_c03_exact_route(predecessor_path, workspace=derived)
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
    result = run_coherent_c03_route(
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
