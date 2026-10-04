"""Estimate scene-level v4.2 binary-error ICC from consumed development data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import torch

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "eval"))
sys.path.insert(0, str(AI_ROOT / "train"))

from admit_residual_obstruction_v4_2_shards import canonical, digest  # noqa: E402
from prepare_residual_obstruction_v4_2_gates import (  # noqa: E402
    _load_report,
    load_complete_campaign,
)
from run_residual_obstruction_v4_2_memorization import spatial_model  # noqa: E402
from train_residual_obstruction_v4_2_cnn import load_arrays, predict  # noqa: E402

SCHEMA = AI_ROOT / "schemas/residual_obstruction_v4_2_scene_icc_v1.schema.json"
CNN_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_cnn_development.v1"
ROBUSTNESS_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_robustness.v1"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binary_one_way_icc(errors: np.ndarray, groups: list[str]) -> dict[str, Any]:
    values = np.asarray(errors, dtype=np.float64)
    if values.ndim != 1 or len(values) != len(groups):
        raise ValueError("errors and groups must be aligned vectors")
    unique = sorted(set(groups))
    selected = [values[np.asarray([group == item for group in groups])] for item in unique]
    sizes = {len(item) for item in selected}
    if len(unique) < 3 or len(sizes) != 1 or next(iter(sizes)) < 2:
        raise ValueError("ICC requires at least three equal nontrivial clusters")
    n = next(iter(sizes))
    means = np.asarray([item.mean() for item in selected])
    grand = values.mean()
    ms_between = n * float(np.sum((means - grand) ** 2)) / (len(unique) - 1)
    ms_within = float(sum(np.sum((item - item.mean()) ** 2) for item in selected)) / (
        len(values) - len(unique)
    )
    denominator = ms_between + (n - 1) * ms_within
    raw = (ms_between - ms_within) / denominator if denominator > 0 else 0.0
    return {
        "scene_count": len(unique),
        "rows_per_scene": n,
        "error_count": int(values.sum()),
        "error_rate": float(grand),
        "scene_error_counts": {item: int(cluster.sum()) for item, cluster in zip(unique, selected)},
        "scene_error_rates": {item: float(cluster.mean()) for item, cluster in zip(unique, selected)},
        "ms_between": ms_between,
        "ms_within": ms_within,
        "icc_raw": raw,
        "icc_nonnegative_for_planning": max(0.0, raw),
    }


def with_delete_one_sensitivity(errors: np.ndarray, groups: list[str]) -> dict[str, Any]:
    point = binary_one_way_icc(errors, groups)
    delete_one = []
    for omitted in sorted(set(groups)):
        keep = np.asarray([group != omitted for group in groups])
        result = binary_one_way_icc(errors[keep], [group for group in groups if group != omitted])
        delete_one.append({"omitted_scene_id": omitted, "icc_raw": result["icc_raw"]})
    values = [row["icc_raw"] for row in delete_one]
    return {
        **point,
        "delete_one_scene": delete_one,
        "delete_one_minimum": min(values),
        "delete_one_maximum": max(values),
    }


def run(
    *, source_commit: str, fixture_path: Path, admission_path: Path,
    cnn_report_path: Path, robustness_path: Path, checkpoint_path: Path,
    allowlist_path: Path, v5_4_path: Path, smoke_a_manifest: Path,
    smoke_b_manifest: Path, renderer_path: Path, threshold: float,
) -> dict[str, Any]:
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    shard_dirs = [Path(row["path"]) for row in allowlist["shards"]]
    fixture, admission, entries = load_complete_campaign(
        fixture_path, admission_path, shard_dirs
    )
    cnn, _ = _load_report(cnn_report_path, CNN_SCHEMA)
    robustness, _ = _load_report(robustness_path, ROBUSTNESS_SCHEMA)
    checkpoint_bytes = checkpoint_path.resolve(strict=True).read_bytes()
    checkpoint_sha = hashlib.sha256(checkpoint_bytes).hexdigest()
    if checkpoint_sha != cnn["checkpoint_sha256"] or checkpoint_sha != robustness["checkpoint_sha256"]:
        raise ValueError("checkpoint binding mismatch")
    development = [row for row in entries if row["split"] == "development"]
    arrays, _ = load_arrays(development, cnn["selected_normalization"], "scene ICC")
    model = spatial_model(torch).cuda() if torch.cuda.is_available() else spatial_model(torch)
    checkpoint = torch.load(
        checkpoint_path, map_location=next(model.parameters()).device, weights_only=True
    )
    model.load_state_dict(checkpoint["state_dict"])
    probabilities = predict(model, arrays, int(fixture["training_plan"]["batch_size"]))
    probability_sha = hashlib.sha256(probabilities.astype("<f4").tobytes()).hexdigest()
    if probability_sha != robustness["development_probability_sha256"]:
        raise ValueError("reconstructed probability hash mismatch")
    labels = np.asarray([
        row["expected_decision"] == "ABSTAIN" for row in development
    ], dtype=bool)
    scenes = [row["scene_id"] for row in development]
    endpoints = {}
    masks = {
        "pooled_obstruction_miss": labels,
        "cable_family_miss": np.asarray([
            row["variant_family"] == "CABLE" for row in development
        ]),
        "dark_cable_proxy_rubber_miss": np.asarray([
            row["variant_id"] == "cable_rubber" for row in development
        ]),
        "visible_false_stop": ~labels,
    }
    for endpoint, mask in masks.items():
        endpoint_probabilities = probabilities[mask]
        if endpoint == "visible_false_stop":
            errors = endpoint_probabilities >= threshold
        else:
            errors = endpoint_probabilities < threshold
        endpoints[endpoint] = with_delete_one_sensitivity(
            errors.astype(np.float64), [scene for scene, keep in zip(scenes, mask) if keep]
        )
    v5_4 = json.loads(v5_4_path.read_text(encoding="utf-8"))
    smoke_a = json.loads(smoke_a_manifest.read_text(encoding="utf-8"))
    smoke_b = json.loads(smoke_b_manifest.read_text(encoding="utf-8"))
    if smoke_a["fixture_bundle_sha256"] != v5_4["bundle_sha256"] or smoke_b["fixture_bundle_sha256"] != v5_4["bundle_sha256"]:
        raise ValueError("renderer smoke does not bind v5.4")
    core = {
        "schema": "tactevra.ai_residual_obstruction_v4_2_scene_icc.v1",
        "scope": "CONSUMED_SYNTHETIC_DEVELOPMENT_ICC_ESTIMATE_AND_V5_PRE_RESULTS_AMENDMENT",
        "status": "COMPLETE_ESTIMATE_RECONFIRM_WITH_V5_DEVELOPMENT_BEFORE_EVALUATION_RENDER",
        "source_commit": source_commit,
        "source": {
            "fixture_file_sha256": file_hash(fixture_path),
            "fixture_bundle_sha256": fixture["bundle_sha256"],
            "admission_file_sha256": file_hash(admission_path),
            "admission_report_sha256": admission["report_sha256"],
            "cnn_report_file_sha256": file_hash(cnn_report_path),
            "cnn_report_sha256": cnn["report_sha256"],
            "robustness_file_sha256": file_hash(robustness_path),
            "robustness_report_sha256": robustness["report_sha256"],
            "allowlist_file_sha256": file_hash(allowlist_path),
            "checkpoint_sha256": checkpoint_sha,
            "reconstructed_development_probability_sha256": probability_sha,
        },
        "threshold": threshold,
        "threshold_role": "V4_2_LEAST_BAD_REJECTED_DEVELOPMENT_THRESHOLD_NOT_CHANGED",
        "endpoint_icc": endpoints,
        "planning_recommendation": {
            "v4_2_estimate_is_transfer_prior_only": True,
            "reestimate_from_v5_development": True,
            "evaluation_resize_permitted_before_pixels": True,
            "safety_gates_may_change": False,
            "evaluation_pixels_opened": False,
        },
        "renderer_pre_results_amendment": {
            "amendment_date": "2026-10-03",
            "reason": "SMOKE_A_VISUAL_AUDIT_FOUND_COMMON_BLOCK_PRIMITIVES_UNREALISTIC",
            "smoke_a_manifest_file_sha256": file_hash(smoke_a_manifest),
            "smoke_a_dataset_sha256": smoke_a["dataset_sha256"],
            "smoke_b_manifest_file_sha256": file_hash(smoke_b_manifest),
            "smoke_b_dataset_sha256": smoke_b["dataset_sha256"],
            "renderer_file_sha256": file_hash(renderer_path),
            "change": "FAMILY_MATCHED_ROUNDED_CABLE_ELLIPSOID_HAND_FOREIGN_AND_SPLIT_SPECIFIC_PROCEDURAL_GEOMETRY",
            "made_before_v5_training_or_development_results": True,
            "fixture_gates_rotation_and_identities_changed": False,
            "failed_smoke_a_preserved": True,
        },
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Only eight consumed v4.2 development scenes inform each ICC estimate, so delete-one sensitivity is material.",
            "V4.2 asset and scene structure differs from v5; these estimates are transfer priors, not fixed v5 correlations.",
            "Binary-error ICC depends on the retained rejected threshold and endpoint definition.",
            "No evaluation image, physical image, qualification, or execution authority is introduced.",
        ],
    }
    result = {**core, "report_sha256": digest(canonical(core))}
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(result), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        raise ValueError(f"schema validation failed at {list(error.path)}: {error.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("fixture", "admission", "cnn_report", "robustness", "checkpoint", "allowlist", "v5_4", "smoke_a_manifest", "smoke_b_manifest", "renderer", "output"):
        parser.add_argument("--" + name.replace("_", "-"), dest=name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--threshold", type=float, default=0.55)
    args = parser.parse_args()
    result = run(
        source_commit=args.source_commit, fixture_path=args.fixture,
        admission_path=args.admission, cnn_report_path=args.cnn_report,
        robustness_path=args.robustness, checkpoint_path=args.checkpoint,
        allowlist_path=args.allowlist, v5_4_path=args.v5_4,
        smoke_a_manifest=args.smoke_a_manifest, smoke_b_manifest=args.smoke_b_manifest,
        renderer_path=args.renderer, threshold=args.threshold,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"report_sha256": result["report_sha256"], "endpoint_icc": result["endpoint_icc"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
