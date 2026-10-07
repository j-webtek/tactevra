"""Successor-only C02 boundary extraction from immutable C01 results.

This module is deliberately separate from the hash-bound C01 physics probe.
It does not modify, reinterpret, or rescore C01 admission. It adds directional
failure attribution and retains compliance identity for the next campaign.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from ai.sim import run_ws2_stage_a_vectorized_throughput as throughput
from ai.sim import stage_a_campaign_supervisor as supervisor
from ai.sim import stage_a_long_run_ops as ops
from integrations.mujoco_warp import key_press_physics_probe as probe


SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def primary_failure_v2(
    row: dict[str, Any], *, minimum_hold_ms: float, maximum_hold_ms: float
) -> str:
    """Classify successor rows without rewriting the frozen C01 vocabulary."""
    if (
        not math.isfinite(minimum_hold_ms)
        or not math.isfinite(maximum_hold_ms)
        or minimum_hold_ms < 0.0
        or maximum_hold_ms <= minimum_hold_ms
    ):
        raise ValueError("invalid successor hold window")
    if not row.get("finite", True) or not row.get("overflow_zero", True):
        return "NONFINITE_OR_OVERFLOW"
    if row.get("neighbor_contact"):
        return "NEIGHBOR_CONTACT"
    if row.get("bottom_out_overflow"):
        return "BOTTOM_OUT"
    if row.get("auto_repeat_count", 0):
        return "AUTO_REPEAT"
    if row.get("double_actuation") or row.get("actuation_count", 0) > 1:
        return "DOUBLE_ACTUATION"
    if row.get("partial_press") or row.get("actuation_count", 0) == 0:
        return "PARTIAL_PRESS"
    hold_ms = float(row["dwell_above_actuation_ms"])
    if not math.isfinite(hold_ms):
        return "NONFINITE_OR_OVERFLOW"
    if hold_ms < minimum_hold_ms:
        return "HOLD_BELOW_MINIMUM"
    if hold_ms > maximum_hold_ms:
        return "HOLD_ABOVE_MAXIMUM"
    if row.get("debounce_hold_complete") is False:
        return "HOLD_WINDOW_INCONSISTENT"
    if not row.get("release_complete"):
        return "RELEASE_INCOMPLETE"
    if not row.get("force_within_available"):
        return "FORCE_EXCEEDED"
    return "ADMITTED"


def refinement_plan_v2(
    fixture: dict[str, Any],
    staged: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    c01_result_sha256: str,
) -> dict[str, Any]:
    """Build compliance-preserving C02 seeds from complete normalized C01 rows."""
    if len(c01_result_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in c01_result_sha256
    ):
        raise ValueError("completed C01 result SHA-256 required")
    coarse = probe.coarse_recipe_indices(fixture, staged)
    expected_landings = set(staged["stage_a_coarse"]["landing_sample_indices"])
    vectors = probe._normalized_recipe_vectors(fixture)
    switch = staged["switch_closure"]
    minimum_hold_ms = max(
        float(value) for value in switch["minimum_duration_ms_samples"]
    )
    maximum_hold_ms = float(switch["maximum_duration_ms"])
    identity_fields = (
        "target_id",
        "profile_id",
        "tip_id",
        "scenario_id",
        "compliance_id",
    )
    grouped: dict[tuple[str, ...], dict[int, list[dict[str, Any]]]] = {}
    for row in rows:
        key = tuple(str(row[field]) for field in identity_fields)
        grouped.setdefault(key, {}).setdefault(int(row["recipe_index"]), []).append(row)
    boundaries = []
    refine = []
    for key, recipes in sorted(grouped.items()):
        if set(recipes) != set(coarse):
            raise ValueError(f"coarse recipe population incomplete for {key}")
        for recipe_index, sample_rows in recipes.items():
            observed = {int(row["landing_sample_index"]) for row in sample_rows}
            if observed != expected_landings or len(sample_rows) != len(expected_landings):
                raise ValueError(
                    f"coarse landing population incomplete for {key} recipe {recipe_index}"
                )
        admission = {
            index: {bool(row["admitted"]) for row in sample_rows}
            for index, sample_rows in recipes.items()
        }
        failures = {
            index: {
                primary_failure_v2(
                    row,
                    minimum_hold_ms=minimum_hold_ms,
                    maximum_hold_ms=maximum_hold_ms,
                )
                for row in sample_rows
            }
            for index, sample_rows in recipes.items()
        }
        for index in coarse:
            nearest = sorted(
                (other for other in coarse if other != index),
                key=lambda other: (
                    probe._distance(vectors[index], vectors[other]),
                    other,
                ),
            )[:3]
            is_boundary = (
                len(admission[index]) > 1
                or any(admission[index] != admission[other] for other in nearest)
                or any(failures[index] != failures[other] for other in nearest)
            )
            if not is_boundary:
                continue
            boundary_id = {
                **dict(zip(identity_fields, key, strict=True)),
                "recipe_index": index,
                "failure_classes": sorted(failures[index]),
                "passing_landing_count": sum(
                    bool(row["admitted"]) for row in recipes[index]
                ),
            }
            boundaries.append(boundary_id)
            unrun = sorted(
                (candidate for candidate in vectors if candidate not in coarse),
                key=lambda candidate: (
                    probe._distance(vectors[index], vectors[candidate]),
                    candidate,
                ),
            )[: staged["stage_b_refinement"]["maximum_new_recipe_indices_per_boundary"]]
            refine.extend(
                {
                    **{field: boundary_id[field] for field in identity_fields},
                    "source_recipe_index": index,
                    "recipe_index": candidate,
                }
                for candidate in unrun
            )
    unique_fields = (*identity_fields, "source_recipe_index", "recipe_index")
    unique = {tuple(row[field] for field in unique_fields): row for row in refine}
    result = {
        "schema": "tactevra.ws2_refinement_plan.v2",
        "scope": SCOPE,
        "c01_result_sha256": c01_result_sha256,
        "campaign_fixture_sha256": fixture["fixture_sha256"],
        "staged_fixture_sha256": staged["fixture_sha256"],
        "coarse_recipe_indices": coarse,
        "hold_window_ms": {
            "minimum": minimum_hold_ms,
            "maximum": maximum_hold_ms,
        },
        "identity_fields": list(identity_fields),
        "group_count": len(grouped),
        "boundary_count": len(boundaries),
        "boundaries": boundaries,
        "refinement_identity_count": len(unique),
        "refinement_identities": [unique[key] for key in sorted(unique)],
        "population_status": "SEEDS_ONLY_PENDING_COMPLETE_C01_FINALIZATION",
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["plan_sha256"] = probe._sha_value(result)
    return result


def summarize_c01_results(
    shard_results: Any,
    *,
    scenario_ids: list[str],
    landing_sample_indices: list[int],
    minimum_hold_ms: float,
    maximum_hold_ms: float,
) -> dict[str, Any]:
    """Stream exact shard results into a compact, nonselecting C01 summary."""
    if len(scenario_ids) != len(set(scenario_ids)) or "FAILURE_CONTROL" not in scenario_ids:
        raise ValueError("exact C01 scenario identities required")
    required_scenarios = [
        scenario for scenario in scenario_ids if scenario != "FAILURE_CONTROL"
    ]
    expected_landings = set(landing_sample_indices)
    if len(expected_landings) != len(landing_sample_indices):
        raise ValueError("landing identities must be unique")
    historical_failures: Counter[str] = Counter()
    directional_failures: Counter[str] = Counter()
    target_stats: dict[str, dict[str, Any]] = {}
    shard_count = 0
    world_count = 0
    scenario_cell_count = 0
    scenario_cell_pass_count = 0
    robust_cell_count = 0
    robust_examples: list[dict[str, Any]] = []
    for result in shard_results:
        shard_count += 1
        shard = result["shard"]
        target_id = str(shard["target_id"])
        profile_id = str(shard["profile_id"])
        tip_id = str(shard["tip_id"])
        rows = result["rows"]
        if len(rows) != int(result["world_count"]):
            raise ValueError(f"row count mismatch for shard {shard['shard_id']}")
        row_ids = [str(row["row_id"]) for row in rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError(f"duplicate row identity in shard {shard['shard_id']}")
        world_count += len(rows)
        recomputed_historical = Counter(probe.primary_failure(row) for row in rows)
        if dict(sorted(recomputed_historical.items())) != result["primary_failure_counts"]:
            raise ValueError(f"historical failure count mismatch for {shard['shard_id']}")
        historical_failures.update(recomputed_historical)
        directional_failures.update(
            primary_failure_v2(
                row,
                minimum_hold_ms=minimum_hold_ms,
                maximum_hold_ms=maximum_hold_ms,
            )
            for row in rows
        )
        groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for row in rows:
            scenario_id = str(row["scenario_id"])
            if scenario_id not in scenario_ids:
                raise ValueError(f"unknown scenario in shard {shard['shard_id']}")
            groups.setdefault(
                (int(row["recipe_index"]), str(row["compliance_id"])), []
            ).append(row)
        target = target_stats.setdefault(
            target_id,
            {
                "target_id": target_id,
                "shard_count": 0,
                "scenario_cell_count": 0,
                "scenario_cell_pass_count": 0,
                "robust_cell_count": 0,
                "best_required_pass_count": -1,
                "required_rows_per_cell": len(required_scenarios)
                * len(expected_landings),
                "best_candidate": None,
            },
        )
        target["shard_count"] += 1
        for (recipe_index, compliance_id), cell_rows in sorted(groups.items()):
            observed = {
                (str(row["scenario_id"]), int(row["landing_sample_index"]))
                for row in cell_rows
            }
            expected = {
                (scenario_id, landing_index)
                for scenario_id in scenario_ids
                for landing_index in expected_landings
            }
            if observed != expected or len(cell_rows) != len(expected):
                raise ValueError(
                    f"incomplete scenario/landing cell in shard {shard['shard_id']}"
                )
            for scenario_id in scenario_ids:
                scenario_rows = [
                    row for row in cell_rows if row["scenario_id"] == scenario_id
                ]
                scenario_cell_count += 1
                target["scenario_cell_count"] += 1
                if all(bool(row["admitted"]) for row in scenario_rows):
                    scenario_cell_pass_count += 1
                    target["scenario_cell_pass_count"] += 1
            required_rows = [
                row for row in cell_rows if row["scenario_id"] in required_scenarios
            ]
            passing = sum(bool(row["admitted"]) for row in required_rows)
            margins = [float(row["minimum_depth_margin_mm"]) for row in required_rows]
            candidate = {
                "target_id": target_id,
                "profile_id": profile_id,
                "tip_id": tip_id,
                "recipe_index": recipe_index,
                "compliance_id": compliance_id,
                "passing_required_rows": passing,
                "required_rows": len(required_rows),
                "minimum_depth_margin_mm": min(margins),
            }
            ranking = (passing, min(margins), -recipe_index, compliance_id)
            current = target["best_candidate"]
            current_ranking = (
                (-1, -math.inf, 0, "")
                if current is None
                else (
                    current["passing_required_rows"],
                    current["minimum_depth_margin_mm"],
                    -current["recipe_index"],
                    current["compliance_id"],
                )
            )
            if ranking > current_ranking:
                target["best_required_pass_count"] = passing
                target["best_candidate"] = candidate
            if passing == len(required_rows):
                robust_cell_count += 1
                target["robust_cell_count"] += 1
                if len(robust_examples) < 100:
                    robust_examples.append(candidate)
    targets = [target_stats[key] for key in sorted(target_stats)]
    return {
        "shard_count": shard_count,
        "world_count": world_count,
        "scenario_ids": scenario_ids,
        "required_scenario_ids": required_scenarios,
        "landing_sample_indices": sorted(expected_landings),
        "historical_primary_failure_counts": dict(sorted(historical_failures.items())),
        "directional_primary_failure_counts": dict(sorted(directional_failures.items())),
        "scenario_cell_count": scenario_cell_count,
        "scenario_cell_pass_count": scenario_cell_pass_count,
        "robust_cell_count": robust_cell_count,
        "robust_cell_examples": robust_examples,
        "targets_with_robust_cell": sum(
            target["robust_cell_count"] > 0 for target in targets
        ),
        "target_summaries": targets,
    }


def finalize_c01(
    *,
    fixture_path: Path,
    results_root: Path,
    backup_root: Path,
    output: Path,
) -> dict[str, Any]:
    """Admit a complete C01 campaign and emit one immutable compact result."""
    fixture = ops.load_fixture(fixture_path)
    campaign_result_path = results_root / "campaign_result.json"
    if not campaign_result_path.exists():
        raise ValueError("C01 campaign_result.json is missing")
    campaign_result = json.loads(campaign_result_path.read_text(encoding="utf-8"))
    core = dict(campaign_result)
    claimed = core.pop("receipt_sha256")
    if ops.value_sha(core) != claimed:
        raise ValueError("C01 campaign result hash mismatch")
    if (
        campaign_result["status"] != "COMPLETE_SIMULATION_ONLY"
        or campaign_result["shards_done"] != fixture["population"]["shard_count"]
    ):
        raise ValueError("complete C01 campaign result required")
    shards = ops.build_shards(fixture)
    expected_ids = {row["shard_id"] for row in shards}
    local_ids = {path.stem for path in (results_root / "shards").glob("*.json")}
    backup_ids = {path.stem for path in (backup_root / "shards").glob("*.json")}
    missing_local = sorted(expected_ids - local_ids)
    missing_backup = sorted(expected_ids - backup_ids)
    if missing_local or missing_backup:
        raise ValueError(
            f"incomplete C01 shard set: local={len(missing_local)} backup={len(missing_backup)}"
        )
    accepted_fixture_sha256 = {
        fixture["fixture_sha256"],
        *fixture["integrity"].get("resume_compatible_fixture_sha256", []),
    }
    cross_modulus = int(fixture["integrity"]["cross_gpu_sample_modulus"])
    manifest = []

    def admitted_results() -> Any:
        for shard in shards:
            shard_id = shard["shard_id"]
            local = results_root / "shards" / f"{shard_id}.json"
            backup = backup_root / "shards" / local.name
            local_sha = _file_sha(local)
            if local_sha != _file_sha(backup):
                raise ValueError(f"C01 backup mismatch for {shard_id}")
            result = supervisor.load_valid_shard_result(
                local,
                shard_id,
                accepted_fixture_sha256=accepted_fixture_sha256,
            )
            cross_sha = None
            if int(shard_id[:8], 16) % cross_modulus == 0:
                cross = local.with_suffix(".cross.json")
                cross_backup = backup.with_suffix(".cross.json")
                if not cross.exists() or not cross_backup.exists():
                    raise ValueError(f"required C01 cross result missing for {shard_id}")
                cross_sha = _file_sha(cross)
                if cross_sha != _file_sha(cross_backup):
                    raise ValueError(f"C01 cross backup mismatch for {shard_id}")
                other = supervisor.load_valid_shard_result(
                    cross,
                    shard_id,
                    accepted_fixture_sha256=accepted_fixture_sha256,
                )
                comparison = supervisor.compare_cross_gpu_results(
                    fixture, result, other
                )
                if comparison["status"] != "AGREE":
                    raise ValueError(f"C01 cross-GPU disagreement for {shard_id}")
            manifest.append(
                {
                    "shard_id": shard_id,
                    "sha256": local_sha,
                    "rows_sha256": result["rows_sha256"],
                    "cross_sha256": cross_sha,
                }
            )
            yield result

    throughput_fixture = throughput.load_fixture(
        ops.ROOT / fixture["bindings"]["throughput_fixture"]["path"]
    )
    campaign, _, staged, _, _ = throughput.load_bound(throughput_fixture)
    scenario_ids = [row["id"] for row in campaign["landing_model"]["scenarios"]]
    switch = staged["switch_closure"]
    summary = summarize_c01_results(
        admitted_results(),
        scenario_ids=scenario_ids,
        landing_sample_indices=staged["stage_a_coarse"]["landing_sample_indices"],
        minimum_hold_ms=max(switch["minimum_duration_ms_samples"]),
        maximum_hold_ms=switch["maximum_duration_ms"],
    )
    manifest_sha256 = ops.value_sha(manifest)
    if summary["shard_count"] != fixture["population"]["shard_count"]:
        raise ValueError("final C01 shard count changed")
    if summary["world_count"] != fixture["population"]["world_count"]:
        raise ValueError("final C01 world count changed")
    decision = (
        "COMPLETE_EXPLORATORY_ENVELOPE"
        if summary["robust_cell_count"]
        else "COMPLETE_INFEASIBLE_NO_RANGE_CHANGE"
    )
    result = {
        "schema": "tactevra.ws2_c01_final_result.v1",
        "scope": SCOPE,
        "decision": decision,
        "fixture_sha256": fixture["fixture_sha256"],
        "campaign_result_sha256": claimed,
        "manifest_sha256": manifest_sha256,
        "manifest_entry_count": len(manifest),
        "ignored_local_json_count": len(local_ids - expected_ids),
        "ignored_backup_json_count": len(backup_ids - expected_ids),
        "summary": summary,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["result_sha256"] = ops.value_sha(result)
    _atomic_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = finalize_c01(
        fixture_path=args.fixture,
        results_root=args.results_root,
        backup_root=args.backup_root,
        output=args.output,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
