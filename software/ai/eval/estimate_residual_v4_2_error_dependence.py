"""Estimate multi-axis v4.2 error dependence and freeze the v5 rule."""

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

SCHEMA = AI_ROOT / "schemas/residual_obstruction_v4_2_error_dependence_v1.schema.json"
CNN_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_cnn_development.v1"
ROBUSTNESS_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_robustness.v1"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_way_icc(errors: np.ndarray, groups: list[str]) -> dict[str, Any]:
    values = np.asarray(errors, dtype=np.float64)
    if values.ndim != 1 or len(values) != len(groups):
        raise ValueError("errors and groups must be aligned vectors")
    unique = sorted(set(groups))
    selected = [
        values[np.asarray([group == item for group in groups])] for item in unique
    ]
    if len(unique) < 3 or min(len(item) for item in selected) < 2:
        return {
            "status": "NOT_ESTIMABLE_FEWER_THAN_THREE_NONTRIVIAL_GROUPS",
            "group_count": len(unique),
            "group_sizes": {
                item: len(cluster) for item, cluster in zip(unique, selected)
            },
        }
    sizes = np.asarray([len(item) for item in selected], dtype=np.float64)
    means = np.asarray([item.mean() for item in selected])
    grand = values.mean()
    ms_between = float(np.sum(sizes * (means - grand) ** 2) / (len(unique) - 1))
    ms_within = float(sum(np.sum((item - item.mean()) ** 2) for item in selected)) / (
        len(values) - len(unique)
    )
    effective_n = float(
        (len(values) - np.sum(sizes**2) / len(values)) / (len(unique) - 1)
    )
    denominator = ms_between + (effective_n - 1.0) * ms_within
    raw = (ms_between - ms_within) / denominator if denominator > 0 else 0.0
    return {
        "status": "ESTIMATED",
        "group_count": len(unique),
        "minimum_group_size": int(sizes.min()),
        "maximum_group_size": int(sizes.max()),
        "error_count": int(values.sum()),
        "error_rate": float(grand),
        "ms_between": ms_between,
        "ms_within": ms_within,
        "effective_cluster_size": effective_n,
        "icc_raw": raw,
        "icc_nonnegative_for_planning": max(0.0, raw),
        "group_error_counts": {
            item: int(cluster.sum()) for item, cluster in zip(unique, selected)
        },
        "group_error_rates": {
            item: float(cluster.mean()) for item, cluster in zip(unique, selected)
        },
    }


def axis_estimates(
    errors: np.ndarray, rows: list[dict[str, Any]], endpoint: str
) -> dict[str, Any]:
    result = {
        "scene": one_way_icc(errors, [row["scene_id"] for row in rows]),
        "target": one_way_icc(
            errors, [f"{row['device']}:{row['target_id']}" for row in rows]
        ),
        "lighting_appearance": one_way_icc(
            errors, [row["appearance_id"] for row in rows]
        ),
    }
    if endpoint == "visible_false_stop":
        result["obstruction_identity_proxy"] = {
            "status": "NOT_APPLICABLE_VISIBLE_ROWS_HAVE_NO_OBSTRUCTION_IDENTITY",
            "group_count": 0,
        }
    else:
        result["obstruction_identity_proxy"] = one_way_icc(
            errors, [row["variant_id"] for row in rows]
        )
    return result


def run(
    *,
    source_commit: str,
    fixture_path: Path,
    admission_path: Path,
    cnn_report_path: Path,
    robustness_path: Path,
    checkpoint_path: Path,
    allowlist_path: Path,
    v5_4_path: Path,
    smoke_c_manifest: Path,
    smoke_c_audit_path: Path,
    renderer_path: Path,
    threshold: float,
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
    if (
        checkpoint_sha != cnn["checkpoint_sha256"]
        or checkpoint_sha != robustness["checkpoint_sha256"]
    ):
        raise ValueError("checkpoint binding mismatch")
    development = [row for row in entries if row["split"] == "development"]
    arrays, _ = load_arrays(development, cnn["selected_normalization"], "scene ICC")
    model = (
        spatial_model(torch).cuda()
        if torch.cuda.is_available()
        else spatial_model(torch)
    )
    checkpoint = torch.load(
        checkpoint_path, map_location=next(model.parameters()).device, weights_only=True
    )
    model.load_state_dict(checkpoint["state_dict"])
    probabilities = predict(model, arrays, int(fixture["training_plan"]["batch_size"]))
    probability_sha = hashlib.sha256(probabilities.astype("<f4").tobytes()).hexdigest()
    if probability_sha != robustness["development_probability_sha256"]:
        raise ValueError("reconstructed probability hash mismatch")
    labels = np.asarray(
        [row["expected_decision"] == "ABSTAIN" for row in development], dtype=bool
    )
    endpoints = {}
    masks = {
        "pooled_obstruction_miss": labels,
        "cable_family_miss": np.asarray(
            [row["variant_family"] == "CABLE" for row in development]
        ),
        "dark_cable_proxy_rubber_miss": np.asarray(
            [row["variant_id"] == "cable_rubber" for row in development]
        ),
        "visible_false_stop": ~labels,
    }
    for endpoint, mask in masks.items():
        endpoint_probabilities = probabilities[mask]
        if endpoint == "visible_false_stop":
            errors = endpoint_probabilities >= threshold
        else:
            errors = endpoint_probabilities < threshold
        selected_rows = [row for row, keep in zip(development, mask) if keep]
        endpoints[endpoint] = {
            "error_count": int(errors.sum()),
            "error_rate": float(errors.mean()),
            "axes": axis_estimates(errors.astype(np.float64), selected_rows, endpoint),
        }
    v5_4 = json.loads(v5_4_path.read_text(encoding="utf-8"))
    smoke_c = json.loads(smoke_c_manifest.read_text(encoding="utf-8"))
    smoke_audit = json.loads(smoke_c_audit_path.read_text(encoding="utf-8"))
    if smoke_c["fixture_bundle_sha256"] != v5_4["bundle_sha256"]:
        raise ValueError("renderer smoke does not bind v5.4")
    if (
        smoke_audit["external_manifest_dataset_sha256"] != smoke_c["dataset_sha256"]
        or smoke_audit["campaign_render_authorized"] is not True
    ):
        raise ValueError("authorized smoke audit does not bind manifest")
    core = {
        "schema": "tactevra.ai_residual_obstruction_v4_2_error_dependence.v1",
        "scope": "CONSUMED_V4_2_MULTI_AXIS_DEPENDENCE_AND_V5_PRE_EVALUATION_RULE",
        "status": "COMPLETE_TRANSFER_PRIOR_V5_MULTI_AXIS_REESTIMATE_REQUIRED",
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
            "v5_4_file_sha256": file_hash(v5_4_path),
            "v5_4_bundle_sha256": v5_4["bundle_sha256"],
            "smoke_c_manifest_file_sha256": file_hash(smoke_c_manifest),
            "smoke_c_dataset_sha256": smoke_c["dataset_sha256"],
            "smoke_c_audit_file_sha256": file_hash(smoke_c_audit_path),
            "smoke_c_audit_report_sha256": smoke_audit["report_sha256"],
        },
        "threshold": threshold,
        "threshold_role": "V4_2_LEAST_BAD_REJECTED_DEVELOPMENT_THRESHOLD_NOT_CHANGED",
        "endpoint_icc": endpoints,
        "v5_pre_evaluation_dependence_rule": {
            "required_axes": [
                "scene_id",
                "device_and_target_id",
                "obstruction_asset_signature_sha256",
                "appearance_id",
            ],
            "required_multiway_interactions": [
                "device_and_target_id_x_obstruction_asset_signature_sha256"
            ],
            "per_gate_rule": "COMPUTE_ONE_WAY_CLUSTER_BOOTSTRAP_UCB_FOR_EVERY_APPLICABLE_AXIS_AND_USE_THE_MAXIMUM",
            "multiway_rule": "WHEN_TARGET_AND_ASSET_AXES_ARE_APPLICABLE_AND_ESTIMABLE_COMPUTE_A_TWO_WAY_MULTIWAY_CLUSTER_BOOTSTRAP_UCB_RESAMPLING_TARGET_AND_ASSET_SEPARATELY_AND_INCLUDE_IT_IN_THE_MAXIMUM",
            "evaluation_sizing_rule": "RECONFIRM_POWER_AT_MAXIMUM_APPLICABLE_AXIS_DEPENDENCE_BEFORE_RENDERING_EVALUATION",
            "unestimable_axis_fallback_icc": 0.30,
            "safety_gates_may_change": False,
            "evaluation_resize_permitted_before_pixels": True,
            "evaluation_pixels_opened": False,
            "asset_axis_uses_actual_v5_descriptor_signature": True,
        },
        "mid_motion_arm_mask_gate": {
            "positive_arm_mask_overlap_tested": False,
            "mid_motion_observation_authorized": False,
            "required_evidence": "HELD_OUT_POSITIVE_OVERLAP_POSES_COMPARE_ANALYTIC_PERTURBED_FK_MASK_WITH_SIMULATOR_TRUTH_USED_ONLY_AS_AUDIT_LABEL",
            "thresholds_frozen": False,
            "parked_pose_scope_affected": False,
        },
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "V4.2 retains no per-asset identity, so variant ID is only an obstruction-identity proxy and some endpoint proxies are unestimable.",
            "V4.2 target, lighting, scene, and variant structures differ from v5; every estimate is a transfer prior.",
            "Binary-error ICC depends on the retained rejected threshold and endpoint definition.",
            "No evaluation image, physical image, qualification, or execution authority is introduced.",
        ],
    }
    result = {**core, "report_sha256": digest(canonical(core))}
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(result),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        raise ValueError(
            f"schema validation failed at {list(error.path)}: {error.message}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "fixture",
        "admission",
        "cnn_report",
        "robustness",
        "checkpoint",
        "allowlist",
        "v5_4",
        "smoke_c_manifest",
        "smoke_c_audit",
        "renderer",
        "output",
    ):
        parser.add_argument(
            "--" + name.replace("_", "-"), dest=name, type=Path, required=True
        )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--threshold", type=float, default=0.55)
    args = parser.parse_args()
    result = run(
        source_commit=args.source_commit,
        fixture_path=args.fixture,
        admission_path=args.admission,
        cnn_report_path=args.cnn_report,
        robustness_path=args.robustness,
        checkpoint_path=args.checkpoint,
        allowlist_path=args.allowlist,
        v5_4_path=args.v5_4,
        smoke_c_manifest=args.smoke_c_manifest,
        smoke_c_audit_path=args.smoke_c_audit,
        renderer_path=args.renderer,
        threshold=args.threshold,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "report_sha256": result["report_sha256"],
                "endpoint_icc": result["endpoint_icc"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
