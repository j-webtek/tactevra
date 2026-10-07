"""Bundle-identity-rebound successor for the coherent C03 route."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .c03_arm_route_reconciliation_v1 import canonical_hash, file_hash, load_strict_json
from .c03_exact_route_reconstruction_v1 import run_c03_exact_route
from .c03_exact_route_reconstruction_v1_1 import _materialize, _resolve


FIXTURE_SCHEMA = "tactevra.c03_exact_route_reconstruction_fixture.v1_4"
RESULT_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1_4"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    fixture = load_strict_json(path)
    claimed = fixture.pop("fixture_sha256", None)
    if claimed != canonical_hash(fixture):
        raise ValueError("bundle-rebound C03 route fixture hash changed")
    fixture["fixture_sha256"] = claimed
    if fixture.get("schema") != FIXTURE_SCHEMA or fixture.get("scope") != SCOPE:
        raise ValueError("unexpected bundle-rebound C03 route fixture identity")
    if fixture.get("physical_authority") is not False or any(
        fixture["counters"].values()
    ):
        raise ValueError("bundle-rebound fixture violates zero authority")
    for name, binding in fixture["bindings"].items():
        source = _resolve(binding["path"], workspace)
        if not source.is_file() or file_hash(source) != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {name}")
    return fixture


def _rebind_route_fixtures(
    fixture: dict[str, Any], derived: Path
) -> dict[str, Any]:
    contract = fixture["fixture_rebinding"]
    changed_fields = [
        "parent.input_bindings.target_catalog.sha256",
        "predecessor.bindings.parent_route_fixture.sha256",
        "predecessor.parent_fixture_sha256",
    ]
    if contract["allowed_semantic_changes"] != changed_fields:
        raise ValueError("fixture rebinding allowlist changed")
    if contract["numerical_policy_change_count"] != 0:
        raise ValueError("fixture permits a numerical policy change")
    candidate_hash = fixture["bindings"]["c03_candidate_target_catalog"]["sha256"]
    parent_path = derived / contract["parent_route_fixture_path"]
    parent = load_strict_json(parent_path)
    old_parent_hash = parent["fixture_sha256"]
    if old_parent_hash != contract["source_parent_fixture_sha256"]:
        raise ValueError("source parent fixture identity changed")
    parent["input_bindings"]["target_catalog"]["sha256"] = candidate_hash
    parent.pop("fixture_sha256")
    parent["fixture_sha256"] = canonical_hash(parent)
    parent_path.write_text(
        json.dumps(parent, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    predecessor_path = derived / fixture["predecessor_fixture_path"]
    predecessor = load_strict_json(predecessor_path)
    old_predecessor_hash = predecessor["fixture_sha256"]
    if old_predecessor_hash != contract["source_predecessor_fixture_sha256"]:
        raise ValueError("source predecessor fixture identity changed")
    predecessor["bindings"]["parent_route_fixture"]["sha256"] = file_hash(parent_path)
    predecessor["parent_fixture_sha256"] = parent["fixture_sha256"]
    predecessor.pop("fixture_sha256")
    predecessor["fixture_sha256"] = canonical_hash(predecessor)
    predecessor_path.write_text(
        json.dumps(predecessor, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    receipt_core = {
        "schema": "tactevra.c03_route_fixture_rebinding_receipt.v1",
        "candidate_target_catalog_sha256": candidate_hash,
        "source_parent_fixture_sha256": old_parent_hash,
        "derived_parent_fixture_sha256": parent["fixture_sha256"],
        "derived_parent_fixture_file_sha256": file_hash(parent_path),
        "source_predecessor_fixture_sha256": old_predecessor_hash,
        "derived_predecessor_fixture_sha256": predecessor["fixture_sha256"],
        "derived_predecessor_fixture_file_sha256": file_hash(predecessor_path),
        "changed_semantic_fields": changed_fields,
        "numerical_policy_change_count": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**receipt_core, "receipt_sha256": canonical_hash(receipt_core)}


def _rebind_virtual_profile(
    fixture: dict[str, Any],
    derived: Path,
    workspace_receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = fixture["virtual_profile_rebinding"]
    changed_fields = [
        "virtual_profile.binding.simulation_bundle_id",
        "bundle.artifacts.virtual_commissioning_profile.sha256",
    ]
    if contract["allowed_semantic_changes"] != changed_fields:
        raise ValueError("virtual-profile rebinding allowlist changed")
    if contract["numerical_policy_change_count"] != 0:
        raise ValueError("virtual-profile rebinding permits a numerical policy change")

    profile_path = derived / contract["virtual_profile_path"]
    profile = load_strict_json(profile_path)
    if file_hash(profile_path) != contract["source_virtual_profile_sha256"]:
        raise ValueError("source virtual profile identity changed")
    binding = profile["binding"]
    if binding["simulation_bundle_id"] != contract["source_bundle_id"]:
        raise ValueError("source virtual profile bundle binding changed")
    derived_bundle_id = fixture["coherent_workspace"]["bundle_id"]
    binding["simulation_bundle_id"] = derived_bundle_id
    profile_path.write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    derived_profile_hash = file_hash(profile_path)

    lock_path = derived / "software/config/simulation_bundle_lock.json"
    lock = load_strict_json(lock_path)
    if lock["bundle_id"] != derived_bundle_id:
        raise ValueError("derived bundle identity changed")
    profile_artifact = lock["artifacts"]["virtual_commissioning_profile"]
    if profile_artifact["path"] != contract["virtual_profile_path"]:
        raise ValueError("virtual profile artifact path changed")
    profile_artifact["sha256"] = derived_profile_hash
    lock_path.write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    updated_workspace_core = {
        key: value
        for key, value in workspace_receipt.items()
        if key != "receipt_sha256"
    }
    updated_workspace_core["bundle_lock_sha256"] = file_hash(lock_path)
    updated_workspace_receipt = {
        **updated_workspace_core,
        "receipt_sha256": canonical_hash(updated_workspace_core),
    }
    (derived / "c03_coherent_workspace_receipt.json").write_text(
        json.dumps(updated_workspace_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    receipt_core = {
        "schema": "tactevra.c03_virtual_profile_rebinding_receipt.v1",
        "source_virtual_profile_sha256": contract["source_virtual_profile_sha256"],
        "derived_virtual_profile_sha256": derived_profile_hash,
        "source_bundle_id": contract["source_bundle_id"],
        "derived_bundle_id": derived_bundle_id,
        "derived_bundle_lock_sha256": updated_workspace_core["bundle_lock_sha256"],
        "changed_semantic_fields": changed_fields,
        "numerical_policy_change_count": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return (
        {**receipt_core, "receipt_sha256": canonical_hash(receipt_core)},
        updated_workspace_receipt,
    )


def run_bundle_rebound_c03_route(
    fixture_path: Path, *, workspace: Path
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path, workspace)
    derived, workspace_receipt = _materialize(fixture, workspace)
    profile_receipt, workspace_receipt = _rebind_virtual_profile(
        fixture, derived, workspace_receipt
    )
    rebinding_receipt = _rebind_route_fixtures(fixture, derived)
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
        "virtual_profile_rebinding_receipt": profile_receipt,
        "fixture_rebinding_receipt": rebinding_receipt,
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
    result = run_bundle_rebound_c03_route(
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
