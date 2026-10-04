"""Measure frozen v5.4 evaluation power at a 1% true miss rate."""

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

from eval.amend_residual_v5_pre_render import _wilson_upper, canonical_hash, load_json  # noqa: E402

SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_4_power_sensitivity_v1.schema.json"
SCENES = 224
TARGETS_PER_SCENE = 12
ROWS_PER_TARGET_SCENE = {
    "pooled_all_obstruction_miss": 24,
    "cable_family_miss": 12,
    "dark_cable_30_60_miss": 6,
    "visible_false_stop": 12,
}
ENDPOINTS = {
    "pooled_all_obstruction_miss": (0.01, 0.02),
    "cable_family_miss": (0.01, 0.02),
    "dark_cable_30_60_miss": (0.01, 0.02),
    "visible_false_stop": (0.03, 0.06),
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scenario(*, scenario_id: str, rho: float, trials: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    powers: dict[str, float] = {}
    for endpoint, (design_rate, gate_rate) in ENDPOINTS.items():
        rows_per_scene = TARGETS_PER_SCENE * ROWS_PER_TARGET_SCENE[endpoint]
        concentration = 1.0 / rho - 1.0
        latent = rng.beta(
            design_rate * concentration,
            (1.0 - design_rate) * concentration,
            size=(trials, SCENES),
        )
        failures = rng.binomial(rows_per_scene, latent).sum(axis=1)
        observations = SCENES * rows_per_scene
        effective_n = observations / (1.0 + (rows_per_scene - 1.0) * rho)
        powers[endpoint] = round(float(np.mean(
            _wilson_upper(failures, observations, effective_n) <= gate_rate
        )), 6)
    bonferroni = max(0.0, sum(powers.values()) - (len(powers) - 1.0))
    return {
        "scenario_id": scenario_id,
        "intracluster_correlation": rho,
        "marginal_power": powers,
        "limiting_marginal_power": min(powers.values()),
        "bonferroni_joint_lower_bound": round(bonferroni, 6),
    }


def build(
    *, source_commit: str, fixture_path: Path, audit_path: Path,
    v5_3_path: Path, trials: int, seed: int,
) -> dict[str, Any]:
    fixture = load_json(fixture_path)
    audit = load_json(audit_path)
    v5_3 = load_json(v5_3_path)
    if fixture.get("schema") != "tactevra.ai_residual_obstruction_successor_fixture.v5_4":
        raise ValueError("v5.4 fixture is required")
    if audit.get("fixture_bundle_sha256") != fixture.get("bundle_sha256"):
        raise ValueError("audit does not bind fixture")
    if not audit.get("training_development_renderer_implementation_may_begin"):
        raise ValueError("fixture audit does not permit renderer implementation")
    if v5_3.get("evaluation_rotation", {}).get("recommended_scene_count") != SCENES:
        raise ValueError("v5.3 does not bind the frozen scene count")
    if trials < 5000:
        raise ValueError("at least 5000 trials required")
    scenarios = [
        scenario(scenario_id="MODERATE_ICC_0_05", rho=0.05, trials=trials, seed=seed),
        scenario(scenario_id="PESSIMISTIC_ICC_0_30", rho=0.30, trials=trials, seed=seed + 1),
    ]
    pessimistic = scenarios[1]
    interpretation = (
        "MODERATE_IMPROVEMENT_CAN_PROVE_BOUNDS_UNDER_MODERATE_CLUSTERING_"
        "BUT_FROZEN_EVALUATION_IS_EFFECTIVELY_LARGE_IMPROVEMENT_OR_REJECTION_"
        "UNDER_PESSIMISTIC_CLUSTERING"
    )
    core = {
        "schema": "tactevra.ai_residual_obstruction_v5_4_power_sensitivity.v1",
        "scope": "SYNTHETIC_POWER_SENSITIVITY_NO_RENDER_NO_GATE_CHANGE",
        "status": "COMPLETE_FROZEN_ROTATION_UNCHANGED",
        "source_commit": source_commit,
        "fixture_file_sha256": file_hash(fixture_path),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "audit_file_sha256": file_hash(audit_path),
        "audit_report_sha256": audit["report_sha256"],
        "v5_3_file_sha256": file_hash(v5_3_path),
        "v5_3_report_sha256": v5_3["report_sha256"],
        "simulation": {
            "trials": trials,
            "seed": seed,
            "scene_count": SCENES,
            "targets_per_scene": TARGETS_PER_SCENE,
            "evaluation_observations": SCENES * TARGETS_PER_SCENE * 36,
            "assumed_true_miss_rate": 0.01,
            "assumed_true_visible_false_stop_rate": 0.03,
            "miss_gate_rate": 0.02,
            "visible_false_stop_gate_rate": 0.06,
            "joint_lower_bound": "BONFERRONI_WITHOUT_GATE_INDEPENDENCE_ASSUMPTION",
            "scenarios": scenarios,
        },
        "interpretation": interpretation,
        "pessimistic_joint_lower_bound": pessimistic["bonferroni_joint_lower_bound"],
        "fixture_or_gate_changed": False,
        "evaluation_render_authorized": False,
        "images_generated": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The 1% miss rate and 3% false-stop rate are hypothetical true rates, not predictions of v5 performance.",
            "The result estimates ability to prove the frozen bounds, not the probability that a trained candidate achieves the assumed rates.",
            "The pessimistic ICC scenario has a dependence-free joint lower bound below the 0.90 power target.",
            "No synthetic result establishes physical-camera transfer or deployment qualification.",
        ],
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    errors = sorted(
        Draft202012Validator(load_json(SCHEMA)).iter_errors(result),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        raise ValueError(f"schema validation failed at {list(error.path)}: {error.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--v5-3", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=55401)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        source_commit=args.source_commit, fixture_path=args.fixture, audit_path=args.audit,
        v5_3_path=args.v5_3, trials=args.trials, seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
