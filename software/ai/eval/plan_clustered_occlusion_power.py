"""Plan synthetic occlusion evaluation size without opening frozen identities.

The retained receipt contains hashes and aggregate statistics only.  Pose, target,
row, image, and failure identities are used transiently to reconstruct clustered
binary outcomes and are never emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import numpy as np


SCHEMA = "rocell.ai_clustered_occlusion_power_plan.v1"
SCOPE = "SYNTHETIC_STATISTICAL_PLANNING_ONLY"
ENDPOINTS = {
    "missed_abstention": ("abstain", "missed_abstain", "true_abstain", 0.01, 0.02),
    "visible_false_stop": ("target_visible", "false_abstain", "true_visible", 0.06, 0.10),
}
POSE_CANDIDATES = (64, 128, 256, 512, 768, 1024, 1536, 2048, 3072, 4096)
Z_ONE_SIDED_95 = 1.6448536269514722


class PowerPlanError(ValueError):
    """An input artifact is malformed or internally inconsistent."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PowerPlanError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise PowerPlanError(f"cannot load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PowerPlanError(f"expected JSON object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            value = json.loads(line, object_pairs_hook=_reject_duplicates)
            if not isinstance(value, dict):
                raise PowerPlanError(f"JSONL row {number} is not an object")
            rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise PowerPlanError(f"cannot load JSONL: {path}") from exc
    if not rows:
        raise PowerPlanError("dataset is empty")
    return rows


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _icc_one_way(clusters: Iterable[np.ndarray]) -> float:
    values = [np.asarray(cluster, dtype=float) for cluster in clusters]
    if len(values) < 2 or any(item.size == 0 for item in values):
        raise PowerPlanError("ICC requires at least two nonempty pose clusters")
    sizes = np.asarray([item.size for item in values], dtype=float)
    means = np.asarray([item.mean() for item in values])
    total = float(sizes.sum())
    grand = float(sum(item.sum() for item in values) / total)
    ms_between = float(np.sum(sizes * (means - grand) ** 2) / (len(values) - 1))
    within = float(sum(np.sum((item - item.mean()) ** 2) for item in values))
    ms_within = within / (total - len(values))
    n0 = (total - float(np.sum(sizes**2)) / total) / (len(values) - 1)
    denominator = ms_between + (n0 - 1.0) * ms_within
    if denominator <= 0:
        return 0.0
    return min(1.0, max(0.0, (ms_between - ms_within) / denominator))


def _bootstrap_icc_upper(clusters: list[np.ndarray], *, samples: int, seed: int) -> float:
    rng = np.random.default_rng(seed)
    estimates = np.empty(samples)
    for index in range(samples):
        selected = rng.integers(0, len(clusters), size=len(clusters))
        estimates[index] = _icc_one_way([clusters[item] for item in selected])
    return float(np.quantile(estimates, 0.95, method="higher"))


def _load_source(
    *, name: str, dataset_path: Path, manifest_path: Path, report_path: Path,
    measurements_key: str, bootstrap_samples: int, bootstrap_seed: int,
) -> tuple[dict[str, Any], dict[str, list[float]], dict[str, list[int]]]:
    rows = _jsonl(dataset_path)
    manifest = _json(manifest_path)
    report = _json(report_path)
    if manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise PowerPlanError(f"{name}: dataset is not synthetic-only")
    authority = manifest.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("hardware_accessed") is not False
        or authority.get("hardware_write_count") != 0
        or authority.get("physical_movement_count") != 0
        or authority.get("can_release_physical_gates") is not False
    ):
        raise PowerPlanError(f"{name}: dataset authority is not zero")
    if report.get("hardware_writes") != 0 or report.get("physical_movements") != 0 or report.get("physical_authority") is not False:
        raise PowerPlanError(f"{name}: report authority is not zero")
    manifest_core = {key: value for key, value in manifest.items() if key not in {"dataset_sha256", "manifest_sha256"}}
    if manifest.get("dataset_sha256") != _canonical_sha(manifest_core):
        raise PowerPlanError(f"{name}: dataset manifest content hash mismatch")
    if report.get("dataset_sha256") != manifest["dataset_sha256"]:
        raise PowerPlanError(f"{name}: report/dataset identity mismatch")
    if report.get("dataset_manifest_sha256") != _sha(manifest_path):
        raise PowerPlanError(f"{name}: report/manifest byte hash mismatch")
    if report.get("target_catalog_sha256") != manifest.get("target_catalog_sha256"):
        raise PowerPlanError(f"{name}: target catalog mismatch")
    report_hash_field = "scorecard_sha256" if "scorecard_sha256" in report else "report_sha256"
    report_core = {key: value for key, value in report.items() if key != report_hash_field}
    if report.get(report_hash_field) != _canonical_sha(report_core):
        raise PowerPlanError(f"{name}: report content hash mismatch")

    by_id: dict[str, dict[str, Any]] = {}
    poses: set[str] = set()
    for row in rows:
        row_id, pose_id, decision = row.get("id"), row.get("pose_id"), row.get("decision")
        if not isinstance(row_id, str) or row_id in by_id or not isinstance(pose_id, str):
            raise PowerPlanError(f"{name}: invalid or duplicate row identity")
        if decision not in {"abstain", "target_visible"} or row.get("synthetic_only") is not True:
            raise PowerPlanError(f"{name}: invalid decision or scope")
        by_id[row_id] = row
        poses.add(pose_id)

    measurements = report.get(measurements_key)
    if not isinstance(measurements, list):
        raise PowerPlanError(f"{name}: missing measurements")
    selected = [item for item in measurements if max(abs(float(item["offset"][axis])) for axis in ("x_mm", "y_mm")) <= 2.0]
    if not selected:
        raise PowerPlanError(f"{name}: no offsets in declared envelope")
    endpoint_uppers: dict[str, list[float]] = {key: [] for key in ENDPOINTS}
    counts: dict[str, list[int]] = {key: [] for key in ENDPOINTS}
    for measurement_index, measurement in enumerate(selected):
        metrics = measurement.get("metrics", {})
        failures = metrics.get("failures")
        confusion = metrics.get("confusion")
        if not isinstance(failures, list) or not isinstance(confusion, dict) or metrics.get("count") != len(rows):
            raise PowerPlanError(f"{name}: malformed measurement")
        seen: set[str] = set()
        failed_by_endpoint: dict[str, set[str]] = {key: set() for key in ENDPOINTS}
        for failure in failures:
            row_id = failure.get("id")
            if not isinstance(row_id, str) or row_id in seen or row_id not in by_id:
                raise PowerPlanError(f"{name}: invalid failure identity")
            seen.add(row_id)
            expected = failure.get("expected")
            predicted = failure.get("predicted")
            if expected != by_id[row_id]["decision"] or {expected, predicted} != {"abstain", "target_visible"}:
                raise PowerPlanError(f"{name}: failure label mismatch")
            endpoint = "missed_abstention" if expected == "abstain" else "visible_false_stop"
            failed_by_endpoint[endpoint].add(row_id)
        for endpoint, (expected, failure_key, success_key, _, _) in ENDPOINTS.items():
            eligible = [row for row in rows if row["decision"] == expected]
            if len(failed_by_endpoint[endpoint]) != confusion.get(failure_key):
                raise PowerPlanError(f"{name}: failure count mismatch")
            if len(eligible) != confusion.get(failure_key, -1) + confusion.get(success_key, -1):
                raise PowerPlanError(f"{name}: endpoint denominator mismatch")
            grouped: dict[str, list[float]] = {pose: [] for pose in poses}
            for row in eligible:
                grouped[row["pose_id"]].append(float(row["id"] in failed_by_endpoint[endpoint]))
            clusters = [np.asarray(grouped[pose]) for pose in sorted(grouped) if grouped[pose]]
            upper = _bootstrap_icc_upper(
                clusters, samples=bootstrap_samples,
                seed=bootstrap_seed + measurement_index * 101 + (0 if endpoint == "missed_abstention" else 1),
            )
            endpoint_uppers[endpoint].append(upper)
            counts[endpoint].extend(item.size for item in clusters)
    summary = {
        "source_id": name,
        "dataset_file_sha256": _sha(dataset_path),
        "manifest_file_sha256": _sha(manifest_path),
        "report_file_sha256": _sha(report_path),
        "dataset_content_sha256": manifest["dataset_sha256"],
        "report_content_sha256": report[report_hash_field],
        "target_catalog_sha256": manifest["target_catalog_sha256"],
        "pose_count": len(poses),
        "row_count": len(rows),
        "declared_envelope_offset_count": len(selected),
    }
    return summary, endpoint_uppers, counts


def _wilson_upper(failures: np.ndarray, observations: int, effective_n: float) -> np.ndarray:
    rate = failures / observations
    z = Z_ONE_SIDED_95
    denominator = 1.0 + z * z / effective_n
    center = rate + z * z / (2.0 * effective_n)
    radius = z * np.sqrt(rate * (1.0 - rate) / effective_n + z * z / (4.0 * effective_n**2))
    return (center + radius) / denominator


def _simulate_scenario(
    *, rho_by_endpoint: dict[str, float], rows_per_pose: dict[str, int], offset_count: int,
    trials: int, seed: int,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    max_poses = max(POSE_CANDIDATES)
    passes: dict[str, np.ndarray] = {}
    for endpoint, (_, _, _, design_rate, gate) in ENDPOINTS.items():
        rho = rho_by_endpoint[endpoint]
        if rho > 0:
            concentration = 1.0 / rho - 1.0
            alpha, beta = design_rate * concentration, (1.0 - design_rate) * concentration
        endpoint_pass = np.empty((trials, len(POSE_CANDIDATES)), dtype=bool)
        completed = 0
        while completed < trials:
            width = min(100, trials - completed)
            if rho > 0:
                latent = rng.beta(alpha, beta, size=(width, offset_count, max_poses))
            else:
                latent = np.full((width, offset_count, max_poses), design_rate)
            failures = rng.binomial(rows_per_pose[endpoint], latent)
            cumulative = np.cumsum(failures, axis=2)
            for candidate_index, poses in enumerate(POSE_CANDIDATES):
                observed = cumulative[:, :, poses - 1]
                n = poses * rows_per_pose[endpoint]
                effective_n = n / (1.0 + (rows_per_pose[endpoint] - 1.0) * rho)
                worst_upper = _wilson_upper(observed, n, effective_n).max(axis=1)
                endpoint_pass[completed:completed + width, candidate_index] = worst_upper <= gate
            completed += width
        passes[endpoint] = endpoint_pass
    joint = passes["missed_abstention"] & passes["visible_false_stop"]
    return [
        {
            "pose_count": poses,
            "missed_abstention_power": round(float(passes["missed_abstention"][:, index].mean()), 6),
            "visible_false_stop_power": round(float(passes["visible_false_stop"][:, index].mean()), 6),
            "joint_power": round(float(joint[:, index].mean()), 6),
        }
        for index, poses in enumerate(POSE_CANDIDATES)
    ]


def build_plan(
    *, sources: list[dict[str, Any]], bootstrap_samples: int = 5000,
    simulation_trials: int = 2000, seed: int = 190202609,
) -> dict[str, Any]:
    if bootstrap_samples < 1000 or simulation_trials < 1000:
        raise PowerPlanError("at least 1000 bootstrap samples and simulation trials are required")
    summaries, source_uppers, source_counts = [], [], []
    for index, source in enumerate(sources):
        summary, uppers, counts = _load_source(
            **source, bootstrap_samples=bootstrap_samples,
            bootstrap_seed=seed + index * 100_003,
        )
        summaries.append(summary)
        source_uppers.append(uppers)
        source_counts.append(counts)
    if len({item["target_catalog_sha256"] for item in summaries}) != 1:
        raise PowerPlanError("sources use different target catalogs")
    empirical = {
        endpoint: max(value for uppers in source_uppers for value in uppers[endpoint])
        for endpoint in ENDPOINTS
    }
    pessimistic = {endpoint: max(value, 0.30) for endpoint, value in empirical.items()}
    rows_per_pose = {
        endpoint: int(median([count for counts in source_counts for count in counts[endpoint]]))
        for endpoint in ENDPOINTS
    }
    offset_count = max(item["declared_envelope_offset_count"] for item in summaries)
    scenarios = []
    for index, (scenario_id, correlations) in enumerate((
        ("EMPIRICAL_UPPER_ICC", empirical), ("PESSIMISTIC_ICC_FLOOR_0_30", pessimistic),
    )):
        scenarios.append({
            "scenario_id": scenario_id,
            "correlations": {key: round(value, 9) for key, value in correlations.items()},
            "candidates": _simulate_scenario(
                rho_by_endpoint=correlations, rows_per_pose=rows_per_pose,
                offset_count=offset_count, trials=simulation_trials,
                seed=seed + 1_000_003 + index * 1_000_003,
            ),
        })
    recommendation = next((
        poses for poses in POSE_CANDIDATES
        if all(next(row for row in scenario["candidates"] if row["pose_count"] == poses)["joint_power"] >= 0.90 for scenario in scenarios)
    ), None)
    if recommendation is None:
        recommendation_status = "NO_TESTED_SIZE_REACHES_POWER_TARGET"
    else:
        recommendation_status = "PLANNING_TARGET_IDENTIFIED"
    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "sources": summaries,
        "method": {
            "declared_envelope_component_bound_mm": 2.0,
            "icc_estimator": "ONE_WAY_RANDOM_EFFECTS_UNEQUAL_CLUSTER_ANOVA_CLAMPED_0_1",
            "icc_upper_method": "SEEDED_POSE_CLUSTER_BOOTSTRAP_95TH_PERCENTILE_MAX_ACROSS_SOURCES_AND_OFFSETS",
            "bootstrap_samples": bootstrap_samples,
            "simulation_method": "SEEDED_BETA_BINOMIAL_POSE_EFFECT_WITH_DESIGN_EFFECT_WILSON_PLANNING_BOUND",
            "simulation_trials": simulation_trials,
            "simulation_seed": seed,
            "offset_count": offset_count,
            "rows_per_pose": rows_per_pose,
            "power_target": 0.90,
            "design_rates": {key: value[3] for key, value in ENDPOINTS.items()},
            "fused_system_gate_limits": {key: value[4] for key, value in ENDPOINTS.items()},
        },
        "scenarios": scenarios,
        "recommendation": {
            "status": recommendation_status,
            "minimum_tested_pose_count": recommendation,
            "sixty_four_pose_floor_passes": all(scenario["candidates"][0]["joint_power"] >= 0.90 for scenario in scenarios),
            "applies_to": "BROAD_SYNTHETIC_MID_MOTION_OCCLUSION_EVALUATION",
        },
        "actual_evaluation_requirement": "SEEDED_POSE_CLUSTER_BOOTSTRAP_UCB_WORST_ACROSS_DECLARED_OFFSETS",
        "identity_disclosure": {
            "pose_ids": 0, "target_ids": 0, "row_ids": 0, "image_paths": 0, "failure_identities": 0,
        },
        "controller_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "This is a synthetic statistical planning receipt, not deployment or physical qualification.",
            "The beta-binomial and design-effect Wilson calculation approximates planning power; it is not the final qualification estimator.",
            "The frozen v14 evaluation identities remain unavailable to candidate selection and are represented only by hashes and aggregate correlation.",
            "The broad mid-motion budget does not replace a separate parked-pose synthetic and physical qualification set.",
        ],
    }
    return {**core, "plan_sha256": _canonical_sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v13-dataset", type=Path, required=True)
    parser.add_argument("--v13-manifest", type=Path, required=True)
    parser.add_argument("--v13-report", type=Path, required=True)
    parser.add_argument("--v14-dataset", type=Path, required=True)
    parser.add_argument("--v14-manifest", type=Path, required=True)
    parser.add_argument("--v14-report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--simulation-trials", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=190202609)
    args = parser.parse_args()
    plan = build_plan(sources=[
        {"name": "V13_DEVELOPMENT", "dataset_path": args.v13_dataset, "manifest_path": args.v13_manifest, "report_path": args.v13_report, "measurements_key": "development_measurements"},
        {"name": "V14_FROZEN_EVALUATION", "dataset_path": args.v14_dataset, "manifest_path": args.v14_manifest, "report_path": args.v14_report, "measurements_key": "measurements"},
    ], bootstrap_samples=args.bootstrap_samples, simulation_trials=args.simulation_trials, seed=args.seed)
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered.encode("utf-8"))
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
