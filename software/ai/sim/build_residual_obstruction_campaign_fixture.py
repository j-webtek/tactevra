"""Freeze a synthetic residual-obstruction crop campaign before generation.

The fixture consumes retained fixed-camera practice bytes but emits only image
and target identities plus deterministic rendering instructions.  It carries no
joint positions and creates no images, model, qualification, or authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SOURCE_SCHEMA = "rocell.fixed_fixture_practice_corpus.v1"
OUTPUT_SCHEMA = "tactevra.ai_residual_obstruction_campaign_fixture.v1"
VARIANTS = (
    ("none_clear", "NONE", "VISIBLE", 0.0),
    ("none_adjacent_distractor", "NONE", "VISIBLE", 0.0),
    ("cable_crossing", "CABLE", "ABSTAIN", 0.35),
    ("tool_intrusion", "TOOL", "ABSTAIN", 0.55),
    ("hand_intrusion", "HAND", "ABSTAIN", 0.65),
    ("foreign_object", "FOREIGN_OBJECT", "ABSTAIN", 0.45),
    ("localized_glare", "GLARE", "ABSTAIN", 0.60),
    ("image_degraded", "IMAGE_DEGRADED", "ABSTAIN", 1.0),
)
POSE_SPLITS = {"hover_t": "training", "hover_e": "development"}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _finite_pair(value: object, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be a two-value array")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must be finite")
    return result


def _seed_values(identity: str) -> tuple[float, float, float]:
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    return tuple(int.from_bytes(digest[index:index + 2], "big") / 65535 for index in (0, 2, 4))  # type: ignore[return-value]


def _render_spec(sample_id: str, variant_id: str, coverage: float) -> dict[str, Any]:
    first, second, third = _seed_values(sample_id)
    if variant_id == "none_clear":
        return {"kind": "IDENTITY", "target_overlap_fraction": 0.0}
    if variant_id == "none_adjacent_distractor":
        return {
            "kind": "ADJACENT_DISTRACTOR",
            "target_overlap_fraction": 0.0,
            "offset_target_widths": [1.25 + first * 0.75, -1.25 - second * 0.75],
            "rotation_deg": -35.0 + third * 70.0,
        }
    common = {
        "target_overlap_fraction": coverage,
        "anchor_uv": [0.30 + first * 0.40, 0.30 + second * 0.40],
        "rotation_deg": -55.0 + third * 110.0,
    }
    if variant_id == "cable_crossing":
        return {"kind": "CURVED_CABLE", **common, "width_fraction": 0.16}
    if variant_id == "tool_intrusion":
        return {"kind": "DARK_TOOL_POLYGON", **common, "width_fraction": 0.55}
    if variant_id == "hand_intrusion":
        return {"kind": "ARTICULATED_HAND_PROXY", **common, "width_fraction": 0.75}
    if variant_id == "foreign_object":
        return {"kind": "FOREIGN_OBJECT_POLYGON", **common, "width_fraction": 0.62}
    if variant_id == "localized_glare":
        return {"kind": "LOCALIZED_GLARE", **common, "alpha": 190}
    if variant_id == "image_degraded":
        return {"kind": "LOCAL_DEFOCUS_AND_COMPRESSION", **common, "blur_radius_px": 4.0, "jpeg_quality": 35}
    raise ValueError(f"unknown variant: {variant_id}")


def build(source_manifest_path: Path) -> dict[str, Any]:
    source_manifest_path = source_manifest_path.resolve(strict=True)
    payload = source_manifest_path.read_bytes()
    source = json.loads(payload)
    if not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unsupported practice corpus")
    claimed = source.get("corpus_sha256")
    core = {key: value for key, value in source.items() if key != "corpus_sha256"}
    if claimed != _sha256(_canonical(core)):
        raise ValueError("practice corpus canonical hash mismatch")
    if source.get("scope") != "SYNTHETIC_FIXED_FIXTURE_PRACTICE_ONLY":
        raise ValueError("practice corpus scope mismatch")
    authority = source.get("authority", {})
    if (
        authority.get("hardware_accessed") is not False
        or authority.get("hardware_write_count") != 0
        or authority.get("physical_movement_count") != 0
        or authority.get("can_release_physical_gates") is not False
    ):
        raise ValueError("practice corpus claims authority or physical effects")

    samples = source.get("samples")
    if not isinstance(samples, list):
        raise ValueError("practice corpus samples are missing")
    bases: dict[str, dict[str, Any]] = {}
    for sample in samples:
        if sample.get("sample_id") == f"{sample.get('pose_id')}__nominal" and sample.get("pose_id") in POSE_SPLITS:
            bases[sample["pose_id"]] = sample
    if set(bases) != set(POSE_SPLITS):
        raise ValueError("both frozen nominal source poses are required")

    target_ids: list[tuple[str, str]] | None = None
    rows: list[dict[str, Any]] = []
    split_counts: dict[str, dict[str, int]] = {}
    for pose_id, split in POSE_SPLITS.items():
        base = bases[pose_id]
        image_path = (source_manifest_path.parent / base["image_path"]).resolve(strict=True)
        if _sha256(image_path.read_bytes()) != base.get("image_sha256"):
            raise ValueError(f"base image hash mismatch: {pose_id}")
        targets = base.get("targets")
        if not isinstance(targets, list):
            raise ValueError("base sample targets are missing")
        current_ids = [(target["device"], target["target_id"]) for target in targets]
        if len(current_ids) != len(set(current_ids)):
            raise ValueError("base sample contains duplicate targets")
        if target_ids is None:
            target_ids = current_ids
        elif current_ids != target_ids:
            raise ValueError("source poses have different ordered target catalogs")
        counts = {"total": 0, "visible": 0, "abstain": 0}
        for target in targets:
            center = _finite_pair(target.get("center_px"), "target center")
            polygon = target.get("safe_polygon_px")
            if not isinstance(polygon, list) or len(polygon) < 3:
                raise ValueError("target polygon is malformed")
            polygon = [_finite_pair(point, "target polygon point") for point in polygon]
            for variant_id, obstruction, label, coverage in VARIANTS:
                observation_id = f"residual-{split}-{pose_id}-{target['device']}-{target['target_id']}-{variant_id}"
                rows.append({
                    "observation_id": observation_id,
                    "split": split,
                    "source_pose_id": pose_id,
                    "base_image_path": base["image_path"],
                    "base_image_sha256": base["image_sha256"],
                    "device": target["device"],
                    "target_id": target["target_id"],
                    "target_center_px": center,
                    "target_safe_polygon_px": polygon,
                    "crop_size_px": [96, 96],
                    "crop_margin_fraction": 1.5,
                    "variant_id": variant_id,
                    "residual_obstruction": obstruction,
                    "expected_decision": label,
                    "render_spec": _render_spec(observation_id, variant_id, coverage),
                    "truth_mask_used_as_model_input": False,
                    "runtime_geometry_mask_used_as_model_input": False,
                })
                counts["total"] += 1
                counts["abstain" if label == "ABSTAIN" else "visible"] += 1
        split_counts[split] = counts

    assert target_ids is not None
    training = [row for row in rows if row["split"] == "training"]
    development = [row for row in rows if row["split"] == "development"]
    core = {
        "schema": OUTPUT_SCHEMA,
        "scope": "SYNTHETIC_PRETRAINING_FREEZE_NO_QUALIFICATION",
        "source": {
            "manifest_file_sha256": _sha256(payload),
            "corpus_sha256": source["corpus_sha256"],
            "generator_sha256": source["generator_sha256"],
            "target_catalog_sha256": source["target_catalog_sha256"],
            "camera_state": source["camera_state"],
        },
        "split_policy": {
            "training_pose_ids": ["hover_t"],
            "development_pose_ids": ["hover_e"],
            "evaluation_pose_ids": [],
            "pose_ids_disjoint": True,
            "target_count_per_split": len(target_ids),
            "variants": [variant for variant, _, _, _ in VARIANTS],
            "split_counts": split_counts,
        },
        "observations": training + development,
        "training_plan": {
            "algorithm": "target_crop_residual_cnn_v1",
            "input_size_px": [96, 96],
            "input_channels": ["RGB", "TARGET_ID_EMBEDDING"],
            "convolution_channels": [16, 32, 64],
            "epochs": 12,
            "batch_size": 64,
            "learning_rate": 0.0005,
            "weight_decay": 0.0001,
            "positive_class_weight": 1.0,
            "seed": 19017,
            "threshold_candidates": [round(index / 100, 2) for index in range(5, 100, 5)],
        },
        "development_gate": {
            "missed_obstruction_rate_upper": 0.02,
            "visible_false_stop_rate_upper": 0.10,
            "confidence_level": 0.95,
            "target_cluster_bootstrap_resamples": 2000,
            "target_cluster_bootstrap_seed": 19017,
            "point_and_cluster_upper_bounds_must_pass": True,
            "evaluation_must_remain_unopened": True,
        },
        "evaluation_group_present": False,
        "images_generated": False,
        "training_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The two base images are correlated synthetic practice views with simplified device surfaces and an unmeasured camera",
            "Procedural obstruction masks are labels only and are prohibited as model inputs",
            "Pose-separated synthetic development is a pretraining gate, not physical or deployment qualification",
            "No evaluation source is included; a separately frozen untouched set is required after development passes",
        ],
    }
    return {**core, "bundle_sha256": _sha256(_canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical(result) + b"\n")
    print(json.dumps({
        "schema": result["schema"],
        "bundle_sha256": result["bundle_sha256"],
        "training_count": result["split_policy"]["split_counts"]["training"]["total"],
        "development_count": result["split_policy"]["split_counts"]["development"]["total"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
