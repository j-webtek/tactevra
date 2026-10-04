"""Classify v5 safety gates and power a balanced evaluation rotation."""

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
    _wilson_upper,
    canonical_hash,
    load_json,
)

SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_3_safety_gate_amendment_v1.schema.json"
SCENE_CANDIDATES = (128, 160, 192, 208, 216, 224, 240, 256)
TARGETS_PER_SCENE = 12
TARGET_COUNT = 75
ROWS_PER_TARGET_SCENE = {
    "pooled_all_obstruction_miss": 24,
    "cable_family_miss": 12,
    "dark_cable_30_60_miss": 6,
    "visible_false_stop": 12,
}
ENDPOINTS = {
    "pooled_all_obstruction_miss": (0.005, 0.02),
    "cable_family_miss": (0.005, 0.02),
    "dark_cable_30_60_miss": (0.005, 0.02),
    "visible_false_stop": (0.03, 0.06),
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scenario(*, scenario_id: str, rho: float, trials: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    max_scenes = max(SCENE_CANDIDATES)
    cumulative_failures: dict[str, np.ndarray] = {}
    for endpoint, (design_rate, _) in ENDPOINTS.items():
        rows_per_scene = TARGETS_PER_SCENE * ROWS_PER_TARGET_SCENE[endpoint]
        concentration = 1.0 / rho - 1.0
        latent = rng.beta(
            design_rate * concentration,
            (1.0 - design_rate) * concentration,
            size=(trials, max_scenes),
        )
        draws = rng.binomial(rows_per_scene, latent)
        cumulative_failures[endpoint] = np.cumsum(draws, axis=1)

    rows = []
    for scenes in SCENE_CANDIDATES:
        powers: dict[str, float] = {}
        for endpoint, (_, gate_rate) in ENDPOINTS.items():
            rows_per_scene = TARGETS_PER_SCENE * ROWS_PER_TARGET_SCENE[endpoint]
            observations = scenes * rows_per_scene
            effective_n = observations / (1.0 + (rows_per_scene - 1.0) * rho)
            failures = cumulative_failures[endpoint][:, scenes - 1]
            powers[endpoint] = round(float(np.mean(
                _wilson_upper(failures, observations, effective_n) <= gate_rate,
            )), 6)
        bonferroni = max(0.0, sum(powers.values()) - (len(powers) - 1.0))
        assignments = scenes * TARGETS_PER_SCENE
        rows.append({
            "scene_count": scenes,
            "evaluation_observations": scenes * TARGETS_PER_SCENE * 36,
            "minimum_target_scene_exposures": assignments // TARGET_COUNT,
            "maximum_target_scene_exposures": (assignments + TARGET_COUNT - 1) // TARGET_COUNT,
            "marginal_power": powers,
            "limiting_marginal_power": min(powers.values()),
            "bonferroni_joint_lower_bound": round(bonferroni, 6),
        })
    return {
        "scenario_id": scenario_id,
        "intracluster_correlation": rho,
        "candidates": rows,
    }


def build(*, source_commit: str, v5_path: Path, v5_2_path: Path, trials: int, seed: int) -> dict[str, Any]:
    v5 = load_json(v5_path)
    v5_2 = load_json(v5_2_path)
    if v5.get("bundle_sha256") != v5_2.get("v5_bundle_sha256"):
        raise ValueError("v5.2 does not bind the supplied v5 fixture")
    if v5_2.get("status") != "BLOCKED_GATE_MODEL_AND_FIXTURE_REVISION_REQUIRED":
        raise ValueError("v5.2 blocker is required")
    if trials < 5000:
        raise ValueError("at least 5000 trials required")
    scenarios = [
        _scenario(scenario_id="MODERATE_ICC_0_05", rho=0.05, trials=trials, seed=seed),
        _scenario(scenario_id="PESSIMISTIC_ICC_0_30", rho=0.30, trials=trials, seed=seed + 1),
    ]
    recommendation = next((
        scenes for scenes in SCENE_CANDIDATES
        if all(
            next(row for row in scenario["candidates"] if row["scene_count"] == scenes)["bonferroni_joint_lower_bound"] >= 0.93
            for scenario in scenarios
        )
    ), None)
    if recommendation is None:
        raise ValueError("no tested scene count powers all safety gates")
    assignments = recommendation * TARGETS_PER_SCENE

    core = {
        "schema": "tactevra.ai_residual_obstruction_v5_3_safety_gate_amendment.v1",
        "scope": "SYNTHETIC_GATE_ROLE_AND_COMPLETE_SAFETY_POWER_NO_RENDER",
        "status": "READY_FOR_FIXTURE_REVISION_RENDER_STILL_BLOCKED",
        "source_commit": source_commit,
        "v5_file_sha256": file_hash(v5_path),
        "v5_bundle_sha256": v5["bundle_sha256"],
        "v5_2_file_sha256": file_hash(v5_2_path),
        "v5_2_report_sha256": v5_2["report_sha256"],
        "gate_roles": {
            "development_candidate_selection": {
                "point_estimate_safety_checks": {
                    "maximum_pooled_all_obstruction_miss_rate": 0.02,
                    "maximum_cable_family_miss_rate": 0.02,
                    "maximum_dark_cable_30_60_miss_rate": 0.02,
                    "maximum_visible_false_stop_rate": 0.06,
                },
                "diagnostic_floors": {
                    "minimum_every_target_auc": 0.90,
                    "minimum_linear_q05_target_auc": 0.95,
                },
                "reported_not_powered": [
                    "LINEAR_Q05_TARGET_QUANTILE_MARGIN",
                    "PER_TARGET_ERROR_TABLE",
                    "HARD_CASE_FAMILY_TABLE",
                    "BASELINE_UPLIFT",
                ],
                "selection_rule": "LOWEST_PARAMETER_CANDIDATE_PASSING_POINT_SAFETY_CHECKS_AND_DIAGNOSTIC_FLOORS",
            },
            "single_use_evaluation_safety_gates": {
                "confidence": "ONE_SIDED_95_PERCENT_UPPER_BOUND",
                "maximum_pooled_all_obstruction_miss_upper": 0.02,
                "maximum_cable_family_miss_upper": 0.02,
                "maximum_dark_cable_30_60_miss_upper": 0.02,
                "maximum_visible_false_stop_upper": 0.06,
                "all_gates_required": True,
                "failure_result": "REJECT_FROZEN_CANDIDATE_NO_RETUNING_ON_EVALUATION",
            },
        },
        "power_assumptions": {
            "trials": trials,
            "seed": seed,
            "power_target": 0.90,
            "planning_selection_joint_lower_bound_target": 0.93,
            "pooled_all_obstruction_miss_design_rate": 0.005,
            "cable_family_miss_design_rate": 0.005,
            "dark_cable_30_60_miss_design_rate": 0.005,
            "visible_false_stop_design_rate": 0.03,
            "rationale": "Miss alternatives are one quarter of the 2% safety ceiling; false-stop alternative is half of the 6% usability ceiling; the selected design uses a 0.93 joint lower-bound planning cushion above the 0.90 requirement.",
            "joint_lower_bound": "BONFERRONI_WITHOUT_GATE_INDEPENDENCE_ASSUMPTION",
        },
        "evaluation_rotation": {
            "targets_per_scene": TARGETS_PER_SCENE,
            "target_count": TARGET_COUNT,
            "rows_per_target_scene": 36,
            "family_rows_per_target_scene": ROWS_PER_TARGET_SCENE,
            "scenarios": scenarios,
            "recommended_scene_count": recommendation,
            "recommended_evaluation_observations": recommendation * TARGETS_PER_SCENE * 36,
            "minimum_target_scene_exposures": assignments // TARGET_COUNT,
            "maximum_target_scene_exposures": (assignments + TARGET_COUNT - 1) // TARGET_COUNT,
            "exact_rotation_frozen": False,
            "render_authorized": False,
        },
        "development_role": {
            "scene_count": len(v5["split_identities"]["scenes"]["development"]),
            "observation_count": v5["render_contract"]["development_observations"],
            "powered_confidence_claim": False,
            "purpose": "CANDIDATE_SELECTION_POINT_ESTIMATES_DIAGNOSTICS_AND_THRESHOLD_FREEZE",
        },
        "evaluation_role": {
            "purpose": "ONE_SINGLE_USE_POWERED_SAFETY_CLAIM_AFTER_CANDIDATE_AND_THRESHOLD_FREEZE",
            "candidate_count": 1,
            "retuning_after_open": False,
        },
        "limitations": [
            "Design rates are planning alternatives, not observed v5 performance.",
            "The exact 12-target rotation and expanded evaluation scene identities remain unfrozen.",
            "Synthetic lighting and obstruction properties remain provisional until the physical pilot.",
            "Per-target AUC diagnostics detect broken targets but are not deployment safety claims.",
            "This amendment does not revise the v5 fixture or authorize rendering.",
        ],
        "images_generated": False,
        "training_started": False,
        "development_opened": False,
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
    parser.add_argument("--v5-2", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=55301)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(source_commit=args.source_commit, v5_path=args.v5, v5_2_path=args.v5_2, trials=args.trials, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
