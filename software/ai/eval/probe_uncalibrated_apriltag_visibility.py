#!/usr/bin/env python3
"""Probe AprilTag visibility without estimating or qualifying camera pose.

This utility is deliberately limited to image-space detection. It can verify
that the expected tag identities are readable in commissioning photographs,
but it cannot produce calibration, localization, uncertainty, or authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_IDS = tuple(range(6))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Detect expected RC03 AprilTags without camera calibration."
    )
    result.add_argument("--image", action="append", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        import cv2
        import numpy as np
    except Exception as exc:  # pragma: no cover - environment-dependent message
        raise SystemExit(f"OpenCV/NumPy unavailable: {exc}") from None

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    image_results: list[dict[str, Any]] = []
    counts: Counter[int] = Counter()
    for image_path in args.image:
        image_path = image_path.resolve(strict=True)
        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise SystemExit(f"Unreadable image: {image_path}")
        corners, ids, rejected = detector.detectMarkers(frame)
        detections: list[dict[str, Any]] = []
        if ids is not None:
            for points, tag_id_value in zip(corners, ids.flatten(), strict=True):
                tag_id = int(tag_id_value)
                quad = points.reshape(4, 2)
                center = np.mean(quad, axis=0)
                detections.append(
                    {
                        "id": tag_id,
                        "center_px": [round(float(value), 3) for value in center],
                        "area_px2": round(
                            abs(float(cv2.contourArea(quad.astype(np.float32)))), 3
                        ),
                    }
                )
                counts[tag_id] += 1
        detections.sort(key=lambda item: item["id"])
        detected_ids = [item["id"] for item in detections]
        image_results.append(
            {
                "file_name": image_path.name,
                "sha256": sha256_file(image_path),
                "width_px": int(frame.shape[1]),
                "height_px": int(frame.shape[0]),
                "detected_ids": detected_ids,
                "missing_expected_ids": sorted(set(EXPECTED_IDS) - set(detected_ids)),
                "detections": detections,
                "rejected_candidates": len(rejected),
            }
        )

    expected = set(EXPECTED_IDS)
    union = set().union(*(set(item["detected_ids"]) for item in image_results))
    report = {
        "schema": "rocell.uncalibrated_apriltag_visibility_probe.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "exploratory_phone_photographs_only",
        "dictionary": "DICT_APRILTAG_36h11",
        "expected_ids": list(EXPECTED_IDS),
        "opencv_version": cv2.__version__,
        "images": image_results,
        "summary": {
            "image_count": len(image_results),
            "images_with_all_expected_ids": sum(
                set(item["detected_ids"]) == expected for item in image_results
            ),
            "union_detected_ids": sorted(union),
            "union_contains_all_expected_ids": union == expected,
            "per_id_detection_counts": {
                str(tag_id): counts[tag_id] for tag_id in EXPECTED_IDS
            },
        },
        "qualification": {
            "camera_intrinsics_available": False,
            "installed_tag_geometry_measured": False,
            "board_pose_estimated": False,
            "localization_error_mm_available": False,
            "deployment_qualification": False,
            "physical_authority": False,
        },
        "hardware_writes": 0,
        "physical_movements_by_probe": 0,
        "limitations": [
            "Phone camera identity, intrinsics, distortion, focus, exposure, and pose are unbound.",
            "Image-space tag visibility does not establish metric localization or uncertainty.",
            "The original photographs remain external and are bound here only by SHA-256.",
        ],
        "next_dependency": (
            "Capture one stationary overview with IDs 0-5 simultaneously visible, then "
            "repeat with the tripod-mounted B0477 and measured calibration/tag geometry."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["union_contains_all_expected_ids"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
