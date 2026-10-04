"""Replay v16 development fusion from retained Isaac robot-mask geometry.

This is a synthetic, development-only architecture check.  It recomputes raw
target overlap from retained mask atlases, reconstructs the frozen learned
decisions from the scorecard, and applies conservative OR fusion.  The mask is
also the source of the synthetic label, so the result is agreement evidence,
not independent accuracy or projection qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SOURCE_SCHEMA = "tactevra.isaac_fixed_overview_mesh_render.v16"
DATASET_SCHEMA = "rocell.ai_official_mesh_occlusion_data.v16"
SCORECARD_SCHEMA = "rocell.ai_grouped_neighborhood_candidate.v1"
REPORT_SCHEMA = "rocell.ai_geometry_first_fusion_replay.v1"
VISIBLE_UPPER = 0.18
AMBIGUITY_UPPER = 0.22


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.resolve(strict=True).read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value, _sha256(payload)


def _claim(value: dict[str, Any], field: str, label: str) -> None:
    claimed = value.get(field)
    body = {key: item for key, item in value.items() if key != field}
    if claimed != _sha256(_canonical(body)):
        raise ValueError(f"{label} canonical hash mismatch")


def _load_rows(path: Path, expected_sha256: str, expected_count: int) -> list[dict[str, Any]]:
    payload = path.resolve(strict=True).read_bytes()
    if _sha256(payload) != expected_sha256:
        raise ValueError("development rows file hash mismatch")
    rows = [json.loads(line) for line in payload.splitlines() if line]
    if len(rows) != expected_count or any(not isinstance(row, dict) for row in rows):
        raise ValueError("development rows count or structure mismatch")
    if len({row.get("id") for row in rows}) != len(rows):
        raise ValueError("development rows contain duplicate ids")
    return rows


def _decision(center_covered: bool, overlap: float) -> str:
    if center_covered or overlap > AMBIGUITY_UPPER:
        return "ABSTAIN_SELF_OCCLUDED"
    if overlap >= VISIBLE_UPPER:
        return "ABSTAIN_AMBIGUOUS"
    return "VISIBLE"


def _confusion(expected_abstain: bool, predicted_abstain: bool) -> str:
    if expected_abstain:
        return "true_abstain" if predicted_abstain else "missed_abstain"
    return "false_abstain" if predicted_abstain else "true_visible"


def _empty_confusion() -> dict[str, int]:
    return {
        "true_abstain": 0,
        "missed_abstain": 0,
        "true_visible": 0,
        "false_abstain": 0,
    }


def _recompute_geometry(
    source: dict[str, Any], source_path: Path, development_pose_ids: set[str]
) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, str]]]:
    try:
        import numpy as np
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - environment failure
        raise RuntimeError("numpy and Pillow are required") from exc

    atlases = source.get("artifact_atlases")
    poses = source.get("pose_results")
    if not isinstance(atlases, dict) or not isinstance(poses, list):
        raise ValueError("source manifest omits atlas or pose records")
    atlas_cache: dict[str, Any] = {}
    atlas_inventory: list[dict[str, str]] = []
    geometry: dict[tuple[str, str], dict[str, Any]] = {}
    for pose in poses:
        if pose.get("pose_id") not in development_pose_ids:
            continue
        if pose.get("pose_group") != "development":
            raise ValueError("development pose group mismatch")
        rgb_key = pose.get("rgb_atlas_key")
        if not isinstance(rgb_key, str) or not rgb_key.startswith("rgb_"):
            raise ValueError("pose has no usable atlas key")
        mask_key = f"robot_mask_{rgb_key.removeprefix('rgb_')}"
        descriptor = atlases.get(mask_key)
        if not isinstance(descriptor, dict):
            raise ValueError(f"missing mask atlas {mask_key}")
        if mask_key not in atlas_cache:
            atlas_path = (source_path.parent / descriptor["path"]).resolve(strict=True)
            payload = atlas_path.read_bytes()
            if _sha256(payload) != descriptor.get("sha256"):
                raise ValueError(f"mask atlas hash mismatch: {mask_key}")
            atlas_cache[mask_key] = Image.open(atlas_path).convert("L")
            atlas_inventory.append({"atlas_key": mask_key, "sha256": descriptor["sha256"]})
        crop = atlas_cache[mask_key].crop(tuple(pose["atlas_crop_px"]))
        mask = np.asarray(crop) != 0
        height, width = mask.shape
        targets = pose.get("targets")
        if not isinstance(targets, list):
            raise ValueError("pose targets are missing")
        for target in targets:
            polygon = [(round(x), round(y)) for x, y in target["safe_polygon_px"]]
            region = Image.new("1", (width, height), 0)
            ImageDraw.Draw(region).polygon(polygon, fill=1)
            region_mask = np.asarray(region, dtype=bool)
            area = int(np.count_nonzero(region_mask))
            overlap = 0.0 if area == 0 else float(np.count_nonzero(region_mask & mask) / area)
            center = tuple(round(value) for value in target["center_px"])
            center_covered = bool(
                0 <= center[0] < width
                and 0 <= center[1] < height
                and mask[center[1], center[0]]
            )
            if center_covered != target.get("center_occluded_by_official_mesh"):
                raise ValueError("recomputed center coverage differs from source")
            source_overlap = target.get("safe_region_official_mesh_overlap_fraction")
            if not isinstance(source_overlap, (int, float)) or not math.isclose(
                overlap, float(source_overlap), rel_tol=0.0, abs_tol=1e-15
            ):
                raise ValueError("recomputed overlap differs from source")
            key = (pose["pose_id"], target["target_id"])
            if key in geometry:
                raise ValueError("duplicate pose-target geometry")
            geometry[key] = {
                "center_covered": center_covered,
                "overlap": overlap,
                "decision": _decision(center_covered, overlap),
            }
    if {pose_id for pose_id, _ in geometry} != development_pose_ids:
        raise ValueError("source manifest does not cover every development pose")
    return geometry, sorted(atlas_inventory, key=lambda item: item["atlas_key"])


def replay(
    *,
    source_manifest_path: Path,
    dataset_manifest_path: Path,
    development_rows_path: Path,
    scorecard_path: Path,
) -> dict[str, Any]:
    source, source_file_sha = _load(source_manifest_path)
    dataset, dataset_file_sha = _load(dataset_manifest_path)
    scorecard, scorecard_file_sha = _load(scorecard_path)
    if source.get("schema") != SOURCE_SCHEMA or source.get("campaign") != "grouped-neighborhood-training-v16":
        raise ValueError("unsupported source manifest")
    if dataset.get("schema") != DATASET_SCHEMA:
        raise ValueError("unsupported dataset manifest")
    if scorecard.get("schema") != SCORECARD_SCHEMA:
        raise ValueError("unsupported scorecard")
    _claim(source, "receipt_sha256", "source receipt")
    _claim(dataset, "dataset_sha256", "dataset")
    _claim(scorecard, "scorecard_sha256", "scorecard")
    if dataset.get("source_manifest_sha256") != source_file_sha:
        raise ValueError("dataset source-manifest hash mismatch")
    if dataset.get("source_receipt_sha256") != source.get("receipt_sha256"):
        raise ValueError("dataset source-receipt hash mismatch")
    if scorecard.get("dataset_manifest_sha256") != dataset_file_sha:
        raise ValueError("scorecard dataset-manifest hash mismatch")
    if scorecard.get("dataset_sha256") != dataset.get("dataset_sha256"):
        raise ValueError("scorecard dataset identity mismatch")
    if scorecard.get("target_catalog_sha256") != dataset.get("target_catalog_sha256"):
        raise ValueError("target catalog identity mismatch")
    if scorecard.get("promotion_status") != "FAILED_DEVELOPMENT_GATE" or scorecard.get("development_gate_met") is not False:
        raise ValueError("replay requires a rejected development candidate")
    if scorecard.get("evaluation_group_present") is not False:
        raise ValueError("evaluation access is prohibited")
    evaluation = dataset.get("splits", {}).get("evaluation", {})
    if evaluation.get("count") != 0:
        raise ValueError("dataset contains evaluation rows")
    for document in (source, scorecard):
        if document.get("hardware_writes") != 0 or document.get("physical_movements") != 0:
            raise ValueError("source claims a physical effect")
        if document.get("physical_authority") is not False:
            raise ValueError("source claims physical authority")
    authority = dataset.get("authority", {})
    if authority.get("hardware_write_count") != 0 or authority.get("physical_movement_count") != 0:
        raise ValueError("dataset claims a physical effect")

    split = dataset["splits"]["development"]
    rows = _load_rows(development_rows_path, split["sha256"], split["count"])
    if any(row.get("synthetic_only") is not True for row in rows):
        raise ValueError("development row is not synthetic-only")
    row_by_id = {row["id"]: row for row in rows}
    pose_ids = {row["pose_id"] for row in rows}
    geometry, atlas_inventory = _recompute_geometry(source, source_manifest_path, pose_ids)

    ambiguous_ids: list[str] = []
    for row in rows:
        item = geometry.get((row["pose_id"], row["target_id"]))
        if item is None:
            raise ValueError("row has no source geometry")
        if row.get("center_occluded") != item["center_covered"] or not math.isclose(
            float(row.get("safe_region_overlap_fraction")), item["overlap"], rel_tol=0.0, abs_tol=1e-15
        ):
            raise ValueError("development row geometry differs from recomputed mask")
        expected = item["center_covered"] or item["overlap"] > 0.20
        if (row.get("decision") == "abstain") != expected:
            raise ValueError("development label differs from frozen geometry rule")
        if item["decision"] == "ABSTAIN_AMBIGUOUS":
            ambiguous_ids.append(row["id"])

    measurements = []
    selected_bound = float(scorecard["maximum_supported_planar_error_mm"])
    for measurement in scorecard.get("development_measurements", []):
        offset = measurement.get("offset", {})
        if max(abs(float(offset.get("x_mm", math.inf))), abs(float(offset.get("y_mm", math.inf)))) > selected_bound:
            continue
        failures = measurement.get("metrics", {}).get("failures")
        if not isinstance(failures, list):
            raise ValueError("measurement failures are missing")
        failure_by_id: dict[str, dict[str, Any]] = {}
        for failure in failures:
            row = row_by_id.get(failure.get("id"))
            if row is None or failure["id"] in failure_by_id:
                raise ValueError("measurement failure identity is invalid")
            if failure.get("expected") != row["decision"]:
                raise ValueError("measurement expected decision mismatch")
            failure_by_id[failure["id"]] = failure

        geometry_confusion = _empty_confusion()
        learned_confusion = _empty_confusion()
        fused_confusion = _empty_confusion()
        adjusted_misses = 0
        adjusted_false = 0
        geometry_forced = 0
        model_forced = 0
        for row in rows:
            expected_abstain = row["decision"] == "abstain"
            failure = failure_by_id.get(row["id"])
            learned_abstain = expected_abstain if failure is None else failure["predicted"] == "abstain"
            geometry_decision = geometry[(row["pose_id"], row["target_id"])]["decision"]
            geometry_abstain = geometry_decision != "VISIBLE"
            fused_abstain = geometry_abstain or learned_abstain
            geometry_confusion[_confusion(expected_abstain, geometry_abstain)] += 1
            learned_confusion[_confusion(expected_abstain, learned_abstain)] += 1
            fused_result = _confusion(expected_abstain, fused_abstain)
            fused_confusion[fused_result] += 1
            geometry_forced += int(geometry_abstain)
            model_forced += int(learned_abstain)
            if geometry_decision != "ABSTAIN_AMBIGUOUS":
                adjusted_misses += int(fused_result == "missed_abstain")
                adjusted_false += int(fused_result == "false_abstain")

        recorded = measurement["metrics"].get("confusion")
        if learned_confusion != recorded:
            raise ValueError("reconstructed learned confusion differs from scorecard")
        measurements.append({
            "offset": offset,
            "geometry_confusion": geometry_confusion,
            "learned_confusion": learned_confusion,
            "fused_confusion": fused_confusion,
            "ambiguity_accepted_missed_abstain": adjusted_misses,
            "ambiguity_accepted_false_abstain": adjusted_false,
            "geometry_abstain_count": geometry_forced,
            "learned_abstain_count": model_forced,
        })
    if not measurements:
        raise ValueError("no in-bound measurements were replayed")

    core = {
        "schema": REPORT_SCHEMA,
        "scope": "SYNTHETIC_CONSUMED_DEVELOPMENT_ONLY_NO_QUALIFICATION",
        "source": {
            "source_manifest_file_sha256": source_file_sha,
            "source_receipt_sha256": source["receipt_sha256"],
            "dataset_manifest_file_sha256": dataset_file_sha,
            "dataset_sha256": dataset["dataset_sha256"],
            "development_rows_file_sha256": split["sha256"],
            "scorecard_file_sha256": scorecard_file_sha,
            "scorecard_sha256": scorecard["scorecard_sha256"],
            "model_sha256": scorecard["model_sha256"],
            "target_catalog_sha256": dataset["target_catalog_sha256"],
            "mask_atlases": atlas_inventory,
        },
        "policy": {
            "visible_overlap_upper": VISIBLE_UPPER,
            "ambiguity_overlap_upper": AMBIGUITY_UPPER,
            "ambiguity_operational_decision": "ABSTAIN",
            "fusion": "GEOMETRY_OR_LEARNED_ABSTAIN",
            "dilation_applied": False,
            "qualification_installed": False,
        },
        "analysis": {
            "development_pose_count": len(pose_ids),
            "development_row_count": len(rows),
            "recomputed_pose_target_count": len(geometry),
            "replayed_offset_count": len(measurements),
            "ambiguous_row_count": len(ambiguous_ids),
            "ambiguous_row_ids": sorted(ambiguous_ids),
            "measurements": measurements,
            "worst_strict_fused_missed_abstain": max(item["fused_confusion"]["missed_abstain"] for item in measurements),
            "worst_strict_fused_false_abstain": max(item["fused_confusion"]["false_abstain"] for item in measurements),
            "worst_ambiguity_accepted_fused_missed_abstain": max(item["ambiguity_accepted_missed_abstain"] for item in measurements),
            "worst_ambiguity_accepted_fused_false_abstain": max(item["ambiguity_accepted_false_abstain"] for item in measurements),
        },
        "evaluation_accessed": False,
        "render_started": False,
        "training_started": False,
        "candidate_promoted": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The retained Isaac mask is also the source of the synthetic occlusion label, so geometry agreement is circular rather than independent accuracy evidence",
            "No measured dilation, commissioned calibration, synchronized measured feedback, tool or support mesh, or projection qualification is installed",
            "The learned checkpoint was trained for synthetic self-occlusion rather than residual physical obstructions",
            "The report cannot qualify deployment, localization, collision safety, contact, controller transport, permits, or execution",
        ],
    }
    return {**core, "report_sha256": _sha256(_canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--development-rows", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(
        source_manifest_path=args.source_manifest,
        dataset_manifest_path=args.dataset_manifest,
        development_rows_path=args.development_rows,
        scorecard_path=args.scorecard,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical(result) + b"\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
