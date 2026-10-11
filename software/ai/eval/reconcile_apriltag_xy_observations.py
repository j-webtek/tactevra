#!/usr/bin/env python3
"""Reconcile working installed-tag XY observations with a visibility probe.

The four world-tag centers define an exploratory planar homography for each
image. Station-tag centers are held out as checks. This produces no camera,
tag-map, or physical qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Check working AprilTag XY observations against image detections."
    )
    result.add_argument("--visibility-probe", required=True, type=Path)
    result.add_argument("--xy-observations", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        import cv2
        import numpy as np
    except Exception as exc:  # pragma: no cover - environment-dependent message
        raise SystemExit(f"OpenCV/NumPy unavailable: {exc}") from None

    probe_path = args.visibility_probe.resolve(strict=True)
    observation_path = args.xy_observations.resolve(strict=True)
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    observations = json.loads(observation_path.read_text(encoding="utf-8"))
    mapped = {
        int(item["id"]): {
            "name": name,
            "role": item["role"],
            "xy_mm": [float(value) for value in item["working_detection_center_xy_mm"]],
        }
        for name, item in observations["tags"].items()
    }
    if set(mapped) != set(range(6)):
        raise SystemExit(f"Expected tag IDs 0-5, found {sorted(mapped)}")
    world_ids = sorted(tag_id for tag_id, item in mapped.items() if item["role"] == "world")
    station_ids = sorted(
        tag_id for tag_id, item in mapped.items() if item["role"] == "station_check"
    )
    if world_ids != [0, 1, 2, 3] or station_ids != [4, 5]:
        raise SystemExit(
            f"Expected world IDs 0-3 and station IDs 4-5; found {world_ids} and {station_ids}"
        )

    image_results: list[dict[str, Any]] = []
    residuals_by_id: dict[int, list[float]] = {tag_id: [] for tag_id in station_ids}
    for image in probe["images"]:
        detections = {int(item["id"]): item for item in image["detections"]}
        if not set(world_ids).issubset(detections):
            image_results.append(
                {
                    "file_name": image["file_name"],
                    "status": "NOT_COMPUTED_MISSING_WORLD_TAG",
                    "missing_world_ids": sorted(set(world_ids) - set(detections)),
                }
            )
            continue
        board_points = np.asarray(
            [mapped[tag_id]["xy_mm"] for tag_id in world_ids], dtype=np.float32
        )
        image_points = np.asarray(
            [detections[tag_id]["center_px"] for tag_id in world_ids], dtype=np.float32
        )
        board_to_image = cv2.getPerspectiveTransform(board_points, image_points)
        image_to_board = np.linalg.inv(board_to_image)
        checks: list[dict[str, Any]] = []
        for tag_id in station_ids:
            if tag_id not in detections:
                continue
            center = np.asarray([*detections[tag_id]["center_px"], 1.0])
            estimate_h = image_to_board @ center
            estimate = estimate_h[:2] / estimate_h[2]
            observed = np.asarray(mapped[tag_id]["xy_mm"])
            delta = estimate - observed
            residual = float(np.linalg.norm(delta))
            residuals_by_id[tag_id].append(residual)
            checks.append(
                {
                    "name": mapped[tag_id]["name"],
                    "id": tag_id,
                    "homography_estimated_board_xy_mm": [
                        round(float(value), 3) for value in estimate
                    ],
                    "working_observed_board_xy_mm": mapped[tag_id]["xy_mm"],
                    "delta_xy_mm": [round(float(value), 3) for value in delta],
                    "planar_residual_mm": round(residual, 3),
                }
            )
        image_results.append(
            {
                "file_name": image["file_name"],
                "status": "COMPUTED_EXPLORATORY",
                "world_anchor_ids": world_ids,
                "station_checks": checks,
            }
        )

    station_summary = {}
    for tag_id in station_ids:
        values = residuals_by_id[tag_id]
        station_summary[mapped[tag_id]["name"]] = {
            "id": tag_id,
            "check_count": len(values),
            "mean_planar_residual_mm": (
                round(float(np.mean(values)), 3) if values else None
            ),
            "max_planar_residual_mm": round(max(values), 3) if values else None,
        }
    all_residuals = [value for values in residuals_by_id.values() for value in values]
    report = {
        "schema": "rocell.apriltag_xy_observation_reconciliation.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "exploratory_working_xy_consistency_only",
        "method": "four_working_world_tag_center_homography_with_station_tags_held_out",
        "inputs": {
            "visibility_probe_path": str(args.visibility_probe),
            "visibility_probe_sha256": sha256_file(probe_path),
            "xy_observations_path": str(args.xy_observations),
            "xy_observations_sha256": sha256_file(observation_path),
            "coordinate_source": observations.get("coordinate_source"),
        },
        "images": image_results,
        "summary": {
            "computed_image_count": sum(
                item["status"] == "COMPUTED_EXPLORATORY" for item in image_results
            ),
            "station_checks": station_summary,
            "maximum_station_planar_residual_mm": (
                round(max(all_residuals), 3) if all_residuals else None
            ),
        },
        "interpretation": (
            "The working installed XY observations substantially reduce the nominal-map "
            "station disagreements in these phone images. Remaining residuals combine "
            "hand measurement error, tag-center extraction, lens distortion, and the "
            "planar homography approximation."
        ),
        "qualification": {
            "canonical_tag_map_updated": False,
            "tag_plane_placement_measured": False,
            "camera_calibrated": False,
            "deployment_qualification": False,
            "physical_authority": False,
        },
        "limitations": [
            "The XY observations are working, unqualified operator measurements.",
            "Phone-camera intrinsics, distortion, focus, exposure, and pose are unbound.",
            "A four-point planar homography fits its world anchors exactly and is used only to check held-out station tags.",
            "This result cannot establish Z, yaw, uncertainty, metric localization accuracy, or motion authority."
        ],
        "hardware_writes": 0,
        "physical_movements_by_analysis": 0,
        "physical_authority": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    return 0 if all_residuals else 2


if __name__ == "__main__":
    raise SystemExit(main())
