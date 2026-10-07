"""Build and smoke-test the hash-bound C02 contact-boundary population."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ai.sim import run_ws2_stage_a_full_compliance_smoke as full_smoke
from ai.sim import run_ws2_stage_a_vectorized_throughput as throughput
from ai.sim import stage_a_long_run_ops as ops
from integrations.mujoco_warp import key_press_physics_probe as probe


ROOT = Path(__file__).resolve().parents[3]
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value_sha(value: Any) -> str:
    return ops.value_sha(value)


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if _value_sha(fixture) != claimed:
        raise ValueError("C02 campaign fixture hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("C02 campaign fixture must remain zero-authority simulation")
    if any(int(value) != 0 for value in fixture["counters"].values()):
        raise ValueError("C02 campaign fixture counters must remain zero")
    runner = fixture["bindings"]["runner"]
    if _file_sha(ROOT / runner["path"]) != runner["sha256"]:
        raise ValueError("C02 campaign runner hash mismatch")
    return fixture


def load_candidate_plan(fixture: dict[str, Any]) -> dict[str, Any]:
    binding = fixture["bindings"]["candidate_seed_plan"]
    path = Path(binding["path"])
    if _file_sha(path) != binding["sha256"]:
        raise ValueError("C02 candidate plan file hash mismatch")
    plan = json.loads(path.read_text(encoding="utf-8"))
    core = dict(plan)
    claimed = core.pop("plan_sha256")
    if _value_sha(core) != claimed or claimed != binding["plan_sha256"]:
        raise ValueError("C02 candidate plan value hash mismatch")
    if plan["population_status"] != "CANDIDATE_SEEDS_REQUIRES_SEPARATE_C02_FIXTURE":
        raise ValueError("C02 candidate plan status changed")
    return plan


def build_manifest(fixture: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    landing_count = int(fixture["population"]["landing_count"])
    if landing_count != int(plan["stage_b_landing_count"]):
        raise ValueError("C02 landing population changed")
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    family_scenarios: dict[tuple[str, str, str, str, int], set[str]] = {}
    execution_identities: set[tuple[Any, ...]] = set()
    for seed in plan["candidate_seeds"]:
        group_key = (
            str(seed["target_id"]),
            str(seed["profile_id"]),
            str(seed["tip_id"]),
        )
        grouped.setdefault(group_key, []).append(seed)
        family_key = (
            str(seed["target_id"]),
            str(seed["profile_id"]),
            str(seed["tip_id"]),
            str(seed["compliance_id"]),
            int(seed["recipe_index"]),
        )
        family_scenarios.setdefault(family_key, set()).add(str(seed["scenario_id"]))
        execution_identity = (*family_key, str(seed["scenario_id"]))
        if execution_identity in execution_identities:
            raise ValueError("duplicate C02 execution identity")
        execution_identities.add(execution_identity)
    required_scenarios = set(fixture["population"]["required_scenario_ids"])
    if any(scenarios != required_scenarios for scenarios in family_scenarios.values()):
        raise ValueError("C02 recipe family lacks a required scenario")

    shards = []
    for group_key, seeds in sorted(grouped.items()):
        seeds = sorted(
            seeds,
            key=lambda row: (
                row["scenario_id"],
                row["compliance_id"],
                int(row["recipe_index"]),
            ),
        )
        core = {
            "target_id": group_key[0],
            "profile_id": group_key[1],
            "tip_id": group_key[2],
            "candidate_seed_count": len(seeds),
            "world_count": len(seeds) * landing_count,
            "candidate_identity_sha256": _value_sha(seeds),
        }
        shards.append({"shard_id": _value_sha(core), **core})

    population = fixture["population"]
    observed = {
        "candidate_seed_count": len(execution_identities),
        "recipe_family_count": len(family_scenarios),
        "shard_count": len(shards),
        "world_count": len(execution_identities) * landing_count,
        "target_count": len({key[0] for key in grouped}),
        "maximum_worlds_per_shard": max(row["world_count"] for row in shards),
    }
    expected = {key: int(population[key]) for key in observed}
    if observed != expected:
        raise ValueError(f"C02 population changed: {observed}")
    result = {
        "schema": "tactevra.ws2_c02_manifest.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "candidate_plan_sha256": plan["plan_sha256"],
        "population": observed,
        "shards": shards,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["manifest_sha256"] = _value_sha(result)
    return result


def build_control(
    fixture: dict[str, Any], plan: dict[str, Any], shard_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = build_manifest(fixture, plan)
    shard = next(row for row in manifest["shards"] if row["shard_id"] == shard_id)
    throughput_fixture = throughput.load_fixture(
        ROOT / fixture["bindings"]["throughput_fixture"]["path"]
    )
    campaign, execution, staged, _, physical = throughput.load_bound(
        throughput_fixture
    )
    seeds = [
        row
        for row in plan["candidate_seeds"]
        if row["target_id"] == shard["target_id"]
        and row["profile_id"] == shard["profile_id"]
        and row["tip_id"] == shard["tip_id"]
    ]
    if _value_sha(
        sorted(
            seeds,
            key=lambda row: (
                row["scenario_id"],
                row["compliance_id"],
                int(row["recipe_index"]),
            ),
        )
    ) != shard["candidate_identity_sha256"]:
        raise ValueError("C02 shard candidate identity mismatch")
    landing_indices = range(int(fixture["population"]["landing_count"]))
    rows = [
        {
            "target_id": seed["target_id"],
            "scenario_id": seed["scenario_id"],
            "landing_sample_index": landing_index,
            "recipe_index": int(seed["recipe_index"]),
            "compliance_id": seed["compliance_id"],
        }
        for seed in seeds
        for landing_index in landing_indices
    ]
    if len(rows) != shard["world_count"] or len({_value_sha(row) for row in rows}) != len(rows):
        raise ValueError("C02 shard world identities changed")
    all_compliance = {
        row["compliance_id"]: row for row in full_smoke.full_compliance(staged)
    }
    compliance = [
        all_compliance[identity]
        for identity in sorted({row["compliance_id"] for row in rows})
    ]
    neighborhood = next(
        row
        for row in physical["neighborhoods"]
        if row["target_id"] == shard["target_id"]
    )
    target_member = neighborhood["members"][neighborhood["target_joint_index"]]
    control = {
        "fixture_sha256": throughput_fixture["fixture_sha256"],
        "control": {
            "control_id": f"c02-{shard_id}",
            "control_kind": "ACTUATION",
            "target_id": shard["target_id"],
            "profile_id": shard["profile_id"],
            "tip_id": shard["tip_id"],
            "scenario_id": rows[0]["scenario_id"],
            "base_recipe_index": rows[0]["recipe_index"],
            "landing_sample_indices": [row["landing_sample_index"] for row in rows],
            "batch_rows": rows,
            "vectorized_world_controls": True,
            "recipe_override": {},
            "tool_compliance_model": "SERIES_QUASISTATIC",
            "tool_compliance_options": compliance,
            "physical_keycap_half_extent_mm": [
                float(value) / 2.0 for value in target_member["size_xy_mm"]
            ],
            "physical_neighborhood": neighborhood["members"],
            "target_joint_index": neighborhood["target_joint_index"],
            "switch_closure_window_ms": throughput_fixture["smoke"][
                "switch_closure_window_ms"
            ],
        },
    }
    return shard, campaign, execution, control


def run_smoke(fixture_path: Path, device: str, output: Path) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    plan = load_candidate_plan(fixture)
    manifest = build_manifest(fixture, plan)
    shard_id = manifest["shards"][int(fixture["smoke"]["manifest_shard_index"])][
        "shard_id"
    ]
    shard, campaign, execution, control = build_control(fixture, plan, shard_id)
    receipt = probe.run_smoke_worker(
        campaign,
        execution,
        workspace=ROOT,
        device_name=device,
        control=control,
    )
    result = {
        "schema": "tactevra.ws2_c02_smoke.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "device": device,
        "shard": shard,
        "world_count": len(receipt["rows"]),
        "rows_sha256": _value_sha(receipt["rows"]),
        "settle_pass": receipt["settle_pass"],
        "finite": receipt["finite"],
        "overflow_zero": receipt["overflow_zero"],
        "wall_elapsed_seconds": receipt["wall_elapsed_seconds"],
        "status": "PASS"
        if receipt["settle_pass"] and receipt["finite"] and receipt["overflow_zero"]
        else "STOP",
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = _value_sha(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("manifest", "smoke"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture = load_fixture(args.fixture)
    plan = load_candidate_plan(fixture)
    if args.mode == "manifest":
        result = build_manifest(fixture, plan)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
    else:
        if args.device is None or args.output is None:
            parser.error("smoke requires --device and --output")
        result = run_smoke(args.fixture, args.device, args.output)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
