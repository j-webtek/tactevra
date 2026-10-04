"""Correct v5 gates and test clustered development power before rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np


AI_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_1_pre_render_v1.schema.json"
SCENE_CANDIDATES = (8, 16, 32, 64, 128, 256)
Z95 = 1.6448536269514722


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    rendered = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _wilson_upper(failures: np.ndarray, observations: int, effective_n: float) -> np.ndarray:
    rate = failures / observations
    denominator = 1.0 + Z95 * Z95 / effective_n
    center = rate + Z95 * Z95 / (2.0 * effective_n)
    radius = Z95 * np.sqrt(
        rate * (1.0 - rate) / effective_n + Z95 * Z95 / (4.0 * effective_n**2),
    )
    return (center + radius) / denominator


def _auc_joint_power(*, scenes: int, rho: float, design_auc: float = 0.98) -> float:
    positive_n = (scenes * 24) / (1.0 + 23.0 * rho)
    negative_n = (scenes * 12) / (1.0 + 11.0 * rho)
    q1 = design_auc / (2.0 - design_auc)
    q2 = 2.0 * design_auc * design_auc / (1.0 + design_auc)
    variance = (
        design_auc * (1.0 - design_auc)
        + (positive_n - 1.0) * (q1 - design_auc * design_auc)
        + (negative_n - 1.0) * (q2 - design_auc * design_auc)
    ) / (positive_n * negative_n)
    standard_error = math.sqrt(variance)
    required_estimate = 0.95 + Z95 * standard_error
    per_target = 1.0 - NormalDist().cdf((required_estimate - design_auc) / standard_error)
    return per_target**75


def _scenario(*, scenario_id: str, rho: float, trials: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    rows = []
    endpoints = (
        ("pooled_miss", 0.005, 0.02, 1800),
        ("visible_false_stop", 0.03, 0.06, 900),
    )
    max_scenes = max(SCENE_CANDIDATES)
    latent_by_endpoint = {}
    for endpoint, design_rate, _, _ in endpoints:
        concentration = 1.0 / rho - 1.0
        latent_by_endpoint[endpoint] = rng.beta(
            design_rate * concentration,
            (1.0 - design_rate) * concentration,
            size=(trials, max_scenes),
        )
    for scenes in SCENE_CANDIDATES:
        powers = {}
        for endpoint, _, gate, rows_per_scene in endpoints:
            latent = latent_by_endpoint[endpoint][:, :scenes]
            failures = rng.binomial(rows_per_scene, latent).sum(axis=1)
            observations = scenes * rows_per_scene
            effective_n = observations / (1.0 + (rows_per_scene - 1.0) * rho)
            powers[endpoint] = float(
                np.mean(_wilson_upper(failures, observations, effective_n) <= gate),
            )
        auc_power = _auc_joint_power(scenes=scenes, rho=rho)
        joint = min(powers["pooled_miss"], powers["visible_false_stop"], auc_power)
        rows.append({
            "scene_count": scenes,
            "development_observations": scenes * 75 * 12 * 3,
            "pooled_miss_power": round(powers["pooled_miss"], 6),
            "visible_false_stop_power": round(powers["visible_false_stop"], 6),
            "all_75_target_auc_power": round(auc_power, 6),
            "conservative_joint_power": round(joint, 6),
        })
    return {"scenario_id": scenario_id, "intracluster_correlation": rho, "candidates": rows}


def build(*, source_commit: str, v5_path: Path, trials: int = 5000, seed: int = 55101) -> dict[str, Any]:
    v5 = load_json(v5_path)
    if v5.get("status") != "FROZEN_BEFORE_RENDER":
        raise ValueError("v5 must be frozen before render")
    if any(v5.get(field) for field in ("images_generated", "training_started", "development_opened", "evaluation_opened")):
        raise ValueError("v5 has already consumed data")
    gates = v5["development_gates"]
    if gates.get("maximum_pooled_missed_obstruction_rate") != 0.02:
        raise ValueError("v5 pooled miss gate is missing")
    if gates.get("maximum_pooled_visible_false_stop_rate") != 0.10:
        raise ValueError("expected preserved v5 10% false-stop value")
    if trials < 1000:
        raise ValueError("at least 1000 trials required")
    scenarios = [
        _scenario(scenario_id="MODERATE_ICC_0_05", rho=0.05, trials=trials, seed=seed),
        _scenario(scenario_id="PESSIMISTIC_ICC_0_30", rho=0.30, trials=trials, seed=seed + 1),
    ]
    recommendation = next((
        scenes for scenes in SCENE_CANDIDATES
        if all(
            next(row for row in scenario["candidates"] if row["scene_count"] == scenes)["conservative_joint_power"] >= 0.90
            for scenario in scenarios
        )
    ), None)
    original_scenes = len(v5["split_identities"]["scenes"]["development"])
    core = {
        "schema": "tactevra.ai_residual_obstruction_v5_1_pre_render.v1",
        "scope": "SYNTHETIC_PRE_RENDER_GATE_CORRECTION_AND_POWER_NO_QUALIFICATION",
        "status": "BLOCKED_RENDER_PENDING_POWERED_FIXTURE_REVISION",
        "source_commit": source_commit,
        "v5_file_sha256": file_hash(v5_path),
        "v5_bundle_sha256": v5["bundle_sha256"],
        "preserved_v5": True,
        "gate_correction": {
            "maximum_pooled_all_obstruction_miss_rate": 0.02,
            "maximum_visible_false_stop_rate": 0.06,
            "v5_preserved_false_stop_rate": 0.10,
            "reason": "V4.2 failed 8.72% against the frozen 6% limit; v5 may not silently loosen that gate.",
        },
        "lighting_scope": {
            "status": "PROVISIONAL_SYNTHETIC_ONLY_UNMEASURED",
            "may_select_hardware_remedy": False,
            "may_set_runtime_reference_validity_envelope": False,
            "physical_pilot_required_before_hardware_selection": True,
        },
        "power_method": {
            "simulation": "SEEDED_BETA_BINOMIAL_SCENE_EFFECT_PLUS_WILSON_UCB_AND_HANLEY_MCNEIL_AUC_APPROXIMATION",
            "trials": trials,
            "seed": seed,
            "power_target": 0.90,
            "design_rates": {"pooled_miss": 0.005, "visible_false_stop": 0.03},
            "gate_rates": {"pooled_miss": 0.02, "visible_false_stop": 0.06},
            "target_auc_design": 0.98,
            "target_auc_gate": 0.95,
            "target_count": 75,
            "visible_rows_per_target_scene": 12,
            "obstructed_rows_per_target_scene": 24,
            "cluster_unit": "BASE_SCENE",
        },
        "scenarios": scenarios,
        "original_plan": {
            "development_scene_count": original_scenes,
            "development_observations": v5["render_contract"]["development_observations"],
            "passes_power_target": False,
        },
        "recommendation": {
            "minimum_tested_scene_count": recommendation,
            "minimum_development_observations": None if recommendation is None else recommendation * 75 * 12 * 3,
            "status": "FIXTURE_REVISION_REQUIRED_BEFORE_RENDER",
        },
        "images_generated": False,
        "training_started": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Power is a planning approximation using predeclared moderate and pessimistic scene correlations, not observed v5 data.",
            "The every-target AUC calculation is an analytic approximation and does not replace the frozen clustered development analysis.",
            "The recommended larger campaign is not authorized for rendering until a revised fixture controls compute and scene diversity.",
            "Physical measurements remain required before selecting a remedy for hardware.",
        ],
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    errors = sorted(
        Draft202012Validator(load_json(SCHEMA)).iter_errors(result), key=lambda e: list(e.path),
    )
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=55101)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(source_commit=args.source_commit, v5_path=args.v5, trials=args.trials, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
