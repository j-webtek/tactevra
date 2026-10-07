"""Strictly admit C02 evidence and summarize robust simulated recipe families."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

from ai.sim import c02_campaign_supervisor as supervisor
from ai.sim import contact_boundary_refinement as refinement
from ai.sim import run_ws2_c02_supervised_campaign as runner
from ai.sim import run_ws2_stage_a_vectorized_throughput as throughput
from ai.sim import stage_a_campaign_supervisor as policy
from ai.sim import stage_a_long_run_ops as ops
from integrations.mujoco_warp import key_press_physics_probe as probe


ROOT = Path(__file__).resolve().parents[3]
SCOPE = supervisor.SCOPE


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if ops.value_sha(fixture) != claimed:
        raise ValueError("C02 final-admission fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("C02 final admission must remain zero authority")
    if any(int(value) != 0 for value in fixture["counters"].values()):
        raise ValueError("C02 final-admission counters must remain zero")
    for name, binding in fixture["bindings"].items():
        source = _resolve(binding["path"])
        if _file_sha(source) != binding["sha256"]:
            raise ValueError(f"C02 final-admission binding changed: {name}")
    return fixture


def _validate_campaign_result(path: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    core = dict(result)
    claimed = core.pop("receipt_sha256")
    if ops.value_sha(core) != claimed:
        raise ValueError("C02 campaign-result receipt mismatch")
    if result["status"] != "COMPLETE_SIMULATION_ONLY_REQUIRES_FINAL_ADMISSION":
        raise ValueError("C02 campaign did not complete")
    if result["manifest_sha256"] != fixture["manifest_sha256"]:
        raise ValueError("C02 campaign-result manifest mismatch")
    if result["shards_done"] != fixture["population"]["shard_count"]:
        raise ValueError("C02 campaign-result shard count mismatch")
    if result["world_count"] != fixture["population"]["world_count"]:
        raise ValueError("C02 campaign-result world count mismatch")
    return result


def _recipe_table(campaign_fixture: dict[str, Any]) -> dict[int, dict[str, Any]]:
    bound = throughput.load_fixture(
        ROOT / campaign_fixture["bindings"]["throughput_fixture"]["path"]
    )
    physics, _, _, _, _ = throughput.load_bound(bound)
    return {int(row["recipe_index"]): row for row in probe.recipe_rows(physics)}


def summarize_families(
    shard_results: Iterable[dict[str, Any]],
    *,
    manifest: dict[str, Any],
    recipe_table: dict[int, dict[str, Any]],
    required_scenarios: list[str],
    landing_count: int,
    minimum_hold_ms: float,
    maximum_hold_ms: float,
) -> dict[str, Any]:
    expected_scenarios = set(required_scenarios)
    expected_landings = set(range(landing_count))
    family_rows: dict[tuple[str, str, str, str, int], list[dict[str, Any]]] = {}
    historical: Counter[str] = Counter()
    directional: Counter[str] = Counter()
    target_shards: Counter[str] = Counter()
    shard_count = 0
    world_count = 0
    for result in shard_results:
        shard_count += 1
        shard = result["shard"]
        target_shards[str(shard["target_id"])] += 1
        rows = result["rows"]
        if len(rows) != int(shard["world_count"]):
            raise ValueError(f"C02 row count mismatch for {shard['shard_id']}")
        row_ids = [str(row["row_id"]) for row in rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError(f"C02 duplicate row identity in {shard['shard_id']}")
        recomputed = Counter(probe.primary_failure(row) for row in rows)
        if dict(sorted(recomputed.items())) != result["primary_failure_counts"]:
            raise ValueError(f"C02 primary-failure mismatch for {shard['shard_id']}")
        historical.update(recomputed)
        for row in rows:
            directional_failure = refinement.primary_failure_v2(
                row,
                minimum_hold_ms=minimum_hold_ms,
                maximum_hold_ms=maximum_hold_ms,
            )
            directional[directional_failure] += 1
            key = (
                str(row["target_id"]),
                str(shard["profile_id"]),
                str(shard["tip_id"]),
                str(row["compliance_id"]),
                int(row["recipe_index"]),
            )
            family_rows.setdefault(key, []).append(
                {**row, "directional_failure": directional_failure}
            )
        world_count += len(rows)

    if shard_count != manifest["population"]["shard_count"]:
        raise ValueError("C02 admitted shard count changed")
    if world_count != manifest["population"]["world_count"]:
        raise ValueError("C02 admitted world count changed")
    if len(family_rows) != manifest["population"]["recipe_family_count"]:
        raise ValueError("C02 recipe family count changed")

    target_stats: dict[str, dict[str, Any]] = {}
    robust: list[dict[str, Any]] = []
    signature_targets: dict[tuple[str, str, str, int], set[str]] = defaultdict(set)
    scenario_cell_count = 0
    scenario_cell_pass_count = 0
    for key, rows in sorted(family_rows.items()):
        observed = {
            (str(row["scenario_id"]), int(row["landing_sample_index"]))
            for row in rows
        }
        expected = {
            (scenario, landing)
            for scenario in expected_scenarios
            for landing in expected_landings
        }
        if len(rows) != len(expected) or observed != expected:
            raise ValueError(f"incomplete C02 family {key}")
        target_id, profile_id, tip_id, compliance_id, recipe_index = key
        recipe = recipe_table[recipe_index]
        passing = sum(row["directional_failure"] == "ADMITTED" for row in rows)
        scenario_passes = 0
        for scenario in required_scenarios:
            scenario_cell_count += 1
            selected = [row for row in rows if row["scenario_id"] == scenario]
            if all(row["directional_failure"] == "ADMITTED" for row in selected):
                scenario_cell_pass_count += 1
                scenario_passes += 1
        minimum_depth_margin = min(
            float(row["minimum_depth_margin_mm"]) for row in rows
        )
        minimum_force_margin = min(
            float(recipe["available_press_force_n"])
            - float(row["peak_required_force_n"])
            for row in rows
        )
        motion_time_ms = 1000.0 * (
            float(recipe["press_depth_mm"]) / float(recipe["approach_mm_s"])
            + float(recipe["dwell_ms"]) / 1000.0
            + float(recipe["press_depth_mm"]) / float(recipe["release_mm_s"])
        )
        candidate = {
            "target_id": target_id,
            "profile_id": profile_id,
            "tip_id": tip_id,
            "compliance_id": compliance_id,
            "recipe_index": recipe_index,
            "passing_rows": passing,
            "required_rows": len(expected),
            "passing_scenarios": scenario_passes,
            "minimum_depth_margin_mm": minimum_depth_margin,
            "minimum_force_margin_n": minimum_force_margin,
            "motion_time_ms": motion_time_ms,
            "recipe": recipe,
        }
        target = target_stats.setdefault(
            target_id,
            {
                "target_id": target_id,
                "family_count": 0,
                "robust_family_count": 0,
                "best_candidate": None,
            },
        )
        target["family_count"] += 1
        ranking = (
            passing,
            minimum_depth_margin,
            minimum_force_margin,
            -motion_time_ms,
            -recipe_index,
        )
        current = target["best_candidate"]
        current_ranking = (
            (-1, -math.inf, -math.inf, -math.inf, 0)
            if current is None
            else (
                current["passing_rows"],
                current["minimum_depth_margin_mm"],
                current["minimum_force_margin_n"],
                -current["motion_time_ms"],
                -current["recipe_index"],
            )
        )
        if ranking > current_ranking:
            target["best_candidate"] = candidate
        if passing == len(expected):
            robust.append(candidate)
            target["robust_family_count"] += 1
            signature_targets[(profile_id, tip_id, compliance_id, recipe_index)].add(
                target_id
            )

    targets = [target_stats[key] for key in sorted(target_stats)]
    target_ids = {row["target_id"] for row in targets}
    universal = []
    for signature, covered in sorted(signature_targets.items()):
        if covered == target_ids:
            profile_id, tip_id, compliance_id, recipe_index = signature
            matching = [
                row
                for row in robust
                if (
                    row["profile_id"],
                    row["tip_id"],
                    row["compliance_id"],
                    row["recipe_index"],
                )
                == signature
            ]
            universal.append(
                {
                    "profile_id": profile_id,
                    "tip_id": tip_id,
                    "compliance_id": compliance_id,
                    "recipe_index": recipe_index,
                    "target_count": len(covered),
                    "minimum_depth_margin_mm": min(
                        row["minimum_depth_margin_mm"] for row in matching
                    ),
                    "minimum_force_margin_n": min(
                        row["minimum_force_margin_n"] for row in matching
                    ),
                    "motion_time_ms": matching[0]["motion_time_ms"],
                    "recipe": recipe_table[recipe_index],
                }
            )
    universal.sort(
        key=lambda row: (
            row["minimum_depth_margin_mm"],
            row["minimum_force_margin_n"],
            -row["motion_time_ms"],
        ),
        reverse=True,
    )
    return {
        "shard_count": shard_count,
        "world_count": world_count,
        "historical_primary_failure_counts": dict(sorted(historical.items())),
        "directional_primary_failure_counts": dict(sorted(directional.items())),
        "recipe_family_count": len(family_rows),
        "robust_family_count": len(robust),
        "scenario_cell_count": scenario_cell_count,
        "scenario_cell_pass_count": scenario_cell_pass_count,
        "target_count": len(targets),
        "targets_with_robust_family": sum(
            row["robust_family_count"] > 0 for row in targets
        ),
        "universal_family_count": len(universal),
        "universal_families": universal,
        "target_summaries": targets,
        "robust_family_examples": robust[:200],
        "target_shard_counts": dict(sorted(target_shards.items())),
    }


def finalize(fixture_path: Path, output: Path) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    operations = supervisor.load_fixture(
        _resolve(fixture["bindings"]["operations_fixture"]["path"])
    )
    campaign_fixture, plan, manifest = supervisor.load_bound_campaign(operations)
    authorization = runner.load_authorization(
        _resolve(fixture["bindings"]["authorization_fixture"]["path"])
    )
    if authorization["manifest_sha256"] != fixture["manifest_sha256"]:
        raise ValueError("C02 final authorization manifest changed")
    campaign_result = _validate_campaign_result(
        _resolve(fixture["bindings"]["campaign_result"]["path"]), fixture
    )
    local_root = Path(fixture["custody"]["local_root"])
    backup_root = Path(fixture["custody"]["backup_root"])
    expected = {row["shard_id"]: row for row in manifest["shards"]}
    ordinary_local = {
        path.stem: path
        for path in local_root.glob("*.json")
        if not path.name.endswith(".cross.json") and ".attempt-" not in path.name
    }
    ordinary_backup = {
        path.stem: path
        for path in backup_root.glob("*.json")
        if not path.name.endswith(".cross.json") and ".attempt-" not in path.name
    }
    if set(ordinary_local) != set(expected) or set(ordinary_backup) != set(expected):
        raise ValueError("C02 ordinary custody set mismatch")
    cross_modulus = int(operations["integrity"]["cross_gpu_sample_modulus"])
    cross_expected = {
        shard_id
        for shard_id in expected
        if int(shard_id[:8], 16) % cross_modulus == 0
    }
    cross_local = {
        path.name.removesuffix(".cross.json"): path
        for path in local_root.glob("*.cross.json")
    }
    cross_backup = {
        path.name.removesuffix(".cross.json"): path
        for path in backup_root.glob("*.cross.json")
    }
    if set(cross_local) != cross_expected or set(cross_backup) != cross_expected:
        raise ValueError("C02 cross-GPU custody set mismatch")

    def admitted_results() -> Iterable[dict[str, Any]]:
        for shard_id in sorted(expected):
            local = ordinary_local[shard_id]
            backup = ordinary_backup[shard_id]
            if _file_sha(local) != _file_sha(backup):
                raise ValueError(f"C02 backup mismatch for {shard_id}")
            result = supervisor.load_valid_result(
                local, shard_id=shard_id, fixture=operations
            )
            if result["shard"] != expected[shard_id]:
                raise ValueError(f"C02 manifest shard mismatch for {shard_id}")
            if shard_id in cross_expected:
                left = cross_local[shard_id]
                right = cross_backup[shard_id]
                if _file_sha(left) != _file_sha(right):
                    raise ValueError(f"C02 cross backup mismatch for {shard_id}")
                other = supervisor.load_valid_result(
                    left, shard_id=shard_id, fixture=operations
                )
                comparison = supervisor.compare_cross_gpu(operations, result, other)
                if comparison["status"] != "AGREE":
                    raise ValueError(
                        f"C02 cross-GPU disagreement for {shard_id}: {comparison['reason']}"
                    )
            yield result

    summary = summarize_families(
        admitted_results(),
        manifest=manifest,
        recipe_table=_recipe_table(campaign_fixture),
        required_scenarios=list(campaign_fixture["population"]["required_scenario_ids"]),
        landing_count=int(campaign_fixture["population"]["landing_count"]),
        minimum_hold_ms=float(campaign_fixture["decision"]["hold_window_ms"]["minimum"]),
        maximum_hold_ms=float(campaign_fixture["decision"]["hold_window_ms"]["maximum"]),
    )
    if summary["universal_family_count"]:
        decision = "COMPLETE_ROBUST_UNIVERSAL_SIMULATION_ONLY"
    elif summary["targets_with_robust_family"] == summary["target_count"]:
        decision = "COMPLETE_ROBUST_ASSORTMENT_SIMULATION_ONLY"
    else:
        decision = "COMPLETE_INFEASIBLE_FOR_UNCOVERED_TARGETS_SIMULATION_ONLY"
    result = {
        "schema": "tactevra.ws2_c02_final_admission.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "campaign_receipt_sha256": campaign_result["receipt_sha256"],
        "candidate_plan_sha256": plan["plan_sha256"],
        "decision": decision,
        "custody": {
            "ordinary_shard_count": len(expected),
            "cross_gpu_shard_count": len(cross_expected),
            "local_backup_byte_identical": True,
        },
        "summary": summary,
        "limitations": fixture["limitations"],
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["result_sha256"] = ops.value_sha(result)
    _atomic_json(output, result)
    backup_output = Path(fixture["custody"]["final_backup_path"])
    policy.copy_verified(output, backup_output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = finalize(args.fixture, args.output)
    print(
        json.dumps(
            {
                "status": result["decision"],
                "result_sha256": result["result_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
