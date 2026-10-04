"""Attribute v5 development power and compare balanced sparse render designs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.amend_residual_v5_pre_render import (  # noqa: E402
    _auc_joint_power,
    _wilson_upper,
    canonical_hash,
    load_json,
)

SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_2_power_attribution_v1.schema.json"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _endpoint_power(*, scenes: int, targets_per_scene: int, rho: float, trials: int, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    result: dict[str, float] = {}
    for name, design_rate, gate_rate, rows_per_target in (
        ("pooled_all_obstruction_miss", 0.005, 0.02, 24),
        ("visible_false_stop", 0.03, 0.06, 12),
    ):
        rows_per_scene = targets_per_scene * rows_per_target
        concentration = 1.0 / rho - 1.0
        latent = rng.beta(
            design_rate * concentration,
            (1.0 - design_rate) * concentration,
            size=(trials, scenes),
        )
        failures = rng.binomial(rows_per_scene, latent).sum(axis=1)
        observations = scenes * rows_per_scene
        effective_n = observations / (1.0 + (rows_per_scene - 1.0) * rho)
        result[name] = round(float(np.mean(
            _wilson_upper(failures, observations, effective_n) <= gate_rate,
        )), 6)
    return result


def _design(*, design_id: str, scenes: int, targets_per_scene: int, rho: float, trials: int, seed: int) -> dict[str, Any]:
    target_assignments = scenes * targets_per_scene
    minimum_target_scene_exposures = target_assignments // 75
    maximum_target_scene_exposures = (target_assignments + 74) // 75
    endpoint = _endpoint_power(
        scenes=scenes,
        targets_per_scene=targets_per_scene,
        rho=rho,
        trials=trials,
        seed=seed,
    )
    every_target_auc = round(_auc_joint_power(
        scenes=minimum_target_scene_exposures,
        rho=rho,
    ), 6)
    modeled = [*endpoint.values(), every_target_auc]
    bonferroni = max(0.0, sum(modeled) - (len(modeled) - 1.0))
    return {
        "design_id": design_id,
        "scene_count": scenes,
        "targets_per_scene": targets_per_scene,
        "development_observations": scenes * targets_per_scene * 36,
        "minimum_target_scene_exposures": minimum_target_scene_exposures,
        "maximum_target_scene_exposures": maximum_target_scene_exposures,
        "modeled_gate_power": {
            **endpoint,
            "every_target_auc": every_target_auc,
            "limiting_modeled_marginal_power": min(modeled),
            "bonferroni_joint_lower_bound": round(bonferroni, 6),
        },
    }


def build(*, source_commit: str, v5_path: Path, v5_1_path: Path, trials: int, seed: int) -> dict[str, Any]:
    v5 = load_json(v5_path)
    v5_1 = load_json(v5_1_path)
    if v5.get("bundle_sha256") != v5_1.get("v5_bundle_sha256"):
        raise ValueError("v5.1 does not bind the supplied v5 fixture")
    if v5_1.get("status") != "BLOCKED_RENDER_PENDING_POWERED_FIXTURE_REVISION":
        raise ValueError("v5.1 blocker is required")
    if trials < 1000:
        raise ValueError("at least 1000 trials required")

    gate_inventory = [
        {"gate": "pooled_all_obstruction_miss_rate_le_0_02", "power_status": "MODELED"},
        {"gate": "visible_false_stop_rate_le_0_06", "power_status": "MODELED"},
        {"gate": "scene_cluster_miss_upper_95_le_0_02", "power_status": "PARTIAL_ICC_APPROXIMATION_ONLY"},
        {"gate": "scene_cluster_false_stop_upper_95_le_0_06", "power_status": "PARTIAL_ICC_APPROXIMATION_ONLY"},
        {"gate": "cable_family_miss_rate_le_0_02", "power_status": "UNMODELED_MISSING_FAMILY_EFFECT"},
        {"gate": "dark_cable_30_60_miss_rate_le_0_02", "power_status": "UNMODELED_MISSING_FAMILY_EFFECT"},
        {"gate": "every_target_auc_ge_0_95", "power_status": "MODELED"},
        {"gate": "linear_q05_target_auc_ge_0_98", "power_status": "UNMODELED_ZERO_DECLARED_EFFECT_SLACK"},
        {"gate": "linear_q05_target_quantile_margin_ge_0_05", "power_status": "UNMODELED_MISSING_MARGIN_EFFECT_AND_VARIANCE"},
    ]

    original = {}
    for scenario in v5_1["scenarios"]:
        first = next(row for row in scenario["candidates"] if row["scene_count"] == 8)
        powers = {
            "pooled_all_obstruction_miss": first["pooled_miss_power"],
            "visible_false_stop": first["visible_false_stop_power"],
            "every_target_auc": first["all_75_target_auc_power"],
        }
        minimum = min(powers.values())
        original[scenario["scenario_id"]] = {
            "individual_gate_power": powers,
            "limiting_gates": sorted(k for k, value in powers.items() if value == minimum),
            "limiting_modeled_marginal_power": first["conservative_joint_power"],
            "bonferroni_joint_lower_bound": round(max(0.0, sum(powers.values()) - 2.0), 6),
        }

    designs = []
    for scenario_id, rho, offset in (
        ("MODERATE_ICC_0_05", 0.05, 0),
        ("PESSIMISTIC_ICC_0_30", 0.30, 1000),
    ):
        designs.append({
            "scenario_id": scenario_id,
            "intracluster_correlation": rho,
            "designs": [
                _design(design_id="FULL_GRID_256_SCENES_75_TARGETS", scenes=256, targets_per_scene=75, rho=rho, trials=trials, seed=seed + offset),
                _design(design_id="BALANCED_ROTATION_256_SCENES_24_TARGETS", scenes=256, targets_per_scene=24, rho=rho, trials=trials, seed=seed + offset),
            ],
        })

    core = {
        "schema": "tactevra.ai_residual_obstruction_v5_2_power_attribution.v1",
        "scope": "SYNTHETIC_POWER_ATTRIBUTION_AND_RENDER_EFFICIENCY_NO_FIXTURE_CHANGE",
        "status": "BLOCKED_GATE_MODEL_AND_FIXTURE_REVISION_REQUIRED",
        "source_commit": source_commit,
        "v5_file_sha256": file_hash(v5_path),
        "v5_bundle_sha256": v5["bundle_sha256"],
        "v5_1_file_sha256": file_hash(v5_1_path),
        "v5_1_report_sha256": v5_1["report_sha256"],
        "joint_power_semantics": "MINIMUM_IS_LIMITING_MARGINAL_POWER_NOT_JOINT_POWER_BONFERRONI_IS_DEPENDENCE_FREE_LOWER_BOUND",
        "assumed_true_performance": {
            "pooled_all_obstruction_miss_rate": 0.005,
            "visible_false_stop_rate": 0.03,
            "homogeneous_target_auc": 0.98,
            "target_auc_slack_above_every_target_gate": 0.03,
            "target_auc_slack_above_q05_gate": 0.0,
            "target_quantile_margin": None,
        },
        "gate_inventory": gate_inventory,
        "original_eight_scene_attribution": original,
        "balanced_rotation_analysis": {
            "trials": trials,
            "seed": seed,
            "rows_per_target_scene": 36,
            "designs_by_scenario": designs,
            "observation_reduction_fraction": round(1.0 - (256 * 24 * 36) / (256 * 75 * 36), 6),
            "interpretation": "Rotation spends independent scene diversity across balanced target subsets. It powers only the three modeled gates and does not authorize rendering.",
        },
        "split_role_options": [
            {
                "option": "POWERED_DEVELOPMENT_AND_POWERED_EVALUATION",
                "cost": "DUPLICATES_STATISTICAL_BURDEN",
                "selection_risk": "LOWER",
                "status": "NOT_SELECTED",
            },
            {
                "option": "DEVELOPMENT_POINT_ESTIMATES_AND_DIAGNOSTICS_THEN_POWERED_EVALUATION",
                "cost": "LOWER_RENDER_COST",
                "selection_risk": "HIGHER_REQUIRES_FROZEN_SELECTION_AND_SINGLE_EVALUATION_OPEN",
                "status": "PREFERRED_FOR_FIXTURE_REVISION_NOT_ENACTED",
            },
        ],
        "findings": [
            "At moderate correlation, the every-target AUC floor is the limiting modeled gate for the original eight-scene plan.",
            "At pessimistic correlation, eight scenes are insufficient for both pooled error endpoints as well as every-target AUC.",
            "V5.1 did not power cable-family misses, dark-cable misses, q05 target AUC, or q05 target margin.",
            "The assumed homogeneous target AUC equals the q05 gate, leaving zero design effect and preventing a defensible high-power claim for that gate.",
            "A 256-scene balanced 24-target rotation reduces observations by 68 percent and retains at least 81 scene exposures per target, but remains only a partial-gate planning candidate.",
        ],
        "next_requirements": [
            "Declare realistic alternative effect sizes for q05 target AUC, q05 target margin, cable misses, and dark-cable misses.",
            "Choose development-selection versus evaluation-proof responsibilities before revising the fixture.",
            "Freeze an exact balanced target rotation and re-run complete gate power before any render.",
            "Use the physical pilot to replace provisional lighting and real-obstruction assumptions before hardware remedy selection.",
        ],
        "images_generated": False,
        "training_started": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    schema = load_json(SCHEMA)
    errors = sorted(Draft202012Validator(schema).iter_errors(result), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--v5-1", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=55201)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(source_commit=args.source_commit, v5_path=args.v5, v5_1_path=args.v5_1, trials=args.trials, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
