#!/usr/bin/env python3
"""Build a read-only keyboard overlay from retained fixed-camera evidence.

The board homography is valid on the board plane. The keyboard is 21 mm above
that plane, so this tool reports both the raw board-plane projection and a
dimension-constrained housing pose. Key centers are projected directly through
the visible keyboard quadrilateral for image review. Nothing in this script
opens a camera, robot transport, or motion interface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATION = (
    ROOT / "software/config/b0477_keyboard_overlay_annotation_20261016.json"
)
DEFAULT_REGISTRATION = (
    ROOT / "software/ai/eval/b0477_fixed_board_registration_20261016.json"
)
DEFAULT_PROFILE = ROOT / "software/config/static_nominal_target_profiles.json"
DEFAULT_OUTPUT = ROOT / "software/ai/eval/b0477_keyboard_overlay_20261016.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _round_vector(vector: Any, digits: int = 4) -> list[float]:
    return [round(float(value), digits) for value in vector]


def _round_matrix(matrix: Any, digits: int = 12) -> list[list[float]]:
    return [[round(float(value), digits) for value in row] for row in matrix]


def _fit_edge(segments: list[list[float]], *, vertical: bool) -> tuple[float, float]:
    """Fit y=m*x+b, or x=m*y+b for a predominantly vertical edge."""
    import numpy as np

    points = np.asarray(
        [[segment[index], segment[index + 1]] for segment in segments for index in (0, 2)],
        dtype=float,
    )
    independent = points[:, 1] if vertical else points[:, 0]
    dependent = points[:, 0] if vertical else points[:, 1]
    design = np.column_stack((independent, np.ones(len(points))))
    slope, intercept = np.linalg.lstsq(design, dependent, rcond=None)[0]
    return float(slope), float(intercept)


def _intersection(horizontal: tuple[float, float], vertical: tuple[float, float]) -> list[float]:
    """Intersect y=hm*x+hb with x=vm*y+vb."""
    hm, hb = horizontal
    vm, vb = vertical
    denominator = 1.0 - hm * vm
    if abs(denominator) < 1e-9:
        raise ValueError("Keyboard housing edges do not form a bounded corner")
    y = (hm * vb + hb) / denominator
    return [vm * y + vb, y]


def _transform(points: Any, matrix: Any) -> Any:
    import cv2
    import numpy as np

    values = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(values, matrix).reshape(-1, 2)


def _target_layout(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    import numpy as np

    default_extent = profile["key_half_extent_mm"]
    result: dict[str, dict[str, Any]] = {}
    for row in profile["rows"]:
        first = np.asarray(row["first_center_xy_mm"], dtype=float)
        step = np.asarray(row["step_xy_mm"], dtype=float)
        for index, name in enumerate(row["key_ids"]):
            result[name] = {
                "center_xy_mm": (first + index * step).tolist(),
                "half_extent_mm": default_extent,
            }
    for name, item in profile["explicit_targets"].items():
        result[name] = {
            "center_xy_mm": item["center_xy_mm"],
            "half_extent_mm": item["half_extent_mm"],
        }
    if len(result) != 46:
        raise ValueError(f"Expected 46 keyboard targets, found {len(result)}")
    return result


def _image_fitted_target_layout(
    profile: dict[str, Any], anchors: dict[str, Any], image_to_keyboard: Any
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fit the catalog identities to reviewed visible row endpoints."""
    import numpy as np

    nominal = _target_layout(profile)
    fitted: dict[str, dict[str, Any]] = {}
    row_names = ("number_row", "q_row", "a_row", "z_row")
    row_summaries = {}
    for row_name, row in zip(row_names, profile["rows"], strict=True):
        anchor = anchors[row_name]
        names = row["key_ids"]
        if anchor["first"]["id"] != names[0] or anchor["last"]["id"] != names[-1]:
            raise ValueError(f"Target anchors do not match {row_name} identities")
        endpoint_pixels = np.asarray(
            [anchor["first"]["xy"], anchor["last"]["xy"]], dtype=float
        )
        endpoint_local = _transform(endpoint_pixels, image_to_keyboard)
        step = (endpoint_local[1] - endpoint_local[0]) / (len(names) - 1)
        for index, name in enumerate(names):
            fitted[name] = {
                "center_xy_mm": (endpoint_local[0] + index * step).tolist(),
                "half_extent_mm": nominal[name]["half_extent_mm"],
                "nominal_center_xy_mm": nominal[name]["center_xy_mm"],
            }
        row_summaries[row_name] = {
            "first_center_keyboard_xy_mm": _round_vector(endpoint_local[0], 3),
            "last_center_keyboard_xy_mm": _round_vector(endpoint_local[1], 3),
            "fitted_step_xy_mm": _round_vector(step, 4),
            "fitted_pitch_mm": round(float(np.linalg.norm(step)), 4),
        }
    explicit = anchors["explicit_targets"]
    if set(explicit) != set(profile["explicit_targets"]):
        raise ValueError("Explicit target anchors differ from the target profile")
    for name, pixel in explicit.items():
        local = _transform([pixel], image_to_keyboard)[0]
        fitted[name] = {
            "center_xy_mm": local.tolist(),
            "half_extent_mm": nominal[name]["half_extent_mm"],
            "nominal_center_xy_mm": nominal[name]["center_xy_mm"],
        }
    if set(fitted) != set(nominal):
        raise ValueError("Image-fitted target identities differ from nominal catalog")
    corrections = [
        np.asarray(item["center_xy_mm"]) - np.asarray(item["nominal_center_xy_mm"])
        for item in fitted.values()
    ]
    correction_norms = [float(np.linalg.norm(value)) for value in corrections]
    return fitted, {
        "rows": row_summaries,
        "mean_nominal_to_image_fitted_correction_mm": round(
            float(np.mean(correction_norms)), 4
        ),
        "maximum_nominal_to_image_fitted_correction_mm": round(
            max(correction_norms), 4
        ),
    }


def _frame_repeatability(frames_directory: Path, reference_path: Path, roi: list[int]) -> dict[str, Any]:
    import cv2
    import numpy as np

    x0, y0, x1, y1 = roi
    reference_image = cv2.imread(str(reference_path), cv2.IMREAD_GRAYSCALE)
    if reference_image is None:
        raise ValueError(f"Could not read reference image: {reference_path}")
    reference = reference_image[y0:y1, x0:x1].astype(np.float32)
    window = cv2.createHanningWindow((reference.shape[1], reference.shape[0]), cv2.CV_32F)
    baseline, _ = cv2.phaseCorrelate(reference, reference, window)
    rows = []
    radial = []
    for path in sorted(frames_directory.glob("*.jpg")):
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None or image.shape != reference_image.shape:
            raise ValueError(f"Frame size differs from reference: {path.name}")
        shift, response = cv2.phaseCorrelate(
            reference, image[y0:y1, x0:x1].astype(np.float32), window
        )
        relative = [shift[0] - baseline[0], shift[1] - baseline[1]]
        radial.append(math.hypot(*relative))
        rows.append(
            {
                "file_name": path.name,
                "sha256": sha256_file(path),
                "relative_shift_px": _round_vector(relative, 4),
                "phase_correlation_response": round(float(response), 6),
            }
        )
    return {
        "roi_px": roi,
        "frame_count": len(rows),
        "maximum_radial_shift_px": round(max(radial), 4),
        "frames": rows,
    }


def build_report(
    annotation_path: Path,
    registration_path: Path,
    profile_path: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    import cv2
    import numpy as np

    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    if (
        annotation.get("schema") != "rocell.fixed_camera_keyboard_annotation.v1"
        or annotation.get("status") != "MANUALLY_REVIEWED_IMAGE_FEATURES_READ_ONLY"
        or registration.get("schema") != "rocell.fixed_apriltag_board_registration.v1"
        or registration.get("status") != "MEASURED_FIXED_EPOCH_PLANAR_MAPPING"
    ):
        raise ValueError("Unexpected keyboard annotation or board registration contract")
    epoch = annotation["workcell_epoch_id"]
    if registration["epoch_binding"]["epoch_id"] != epoch:
        raise ValueError("Keyboard annotation and board registration epochs differ")

    frame_record = annotation["reference_frame"]
    reference_path = ROOT / frame_record["path"]
    if sha256_file(reference_path) != frame_record["sha256"]:
        raise ValueError("Reference frame hash changed")
    reference = cv2.imread(str(reference_path), cv2.IMREAD_GRAYSCALE)
    if reference is None or [reference.shape[1], reference.shape[0]] != frame_record["image_size_px"]:
        raise ValueError("Reference frame dimensions changed")

    keyboard = annotation["keyboard"]
    profile = profiles["keyboard"]
    dimensions = [float(value) for value in keyboard["housing_dimensions_mm"]]
    if dimensions != [float(value) for value in profile["device_size_mm"]]:
        raise ValueError("Annotated housing dimensions differ from target profile")
    width, depth, height = dimensions
    edges = keyboard["edge_feature_segments_px"]
    front = _fit_edge(edges["front"], vertical=False)
    right = _fit_edge(edges["right"], vertical=True)
    rear = _fit_edge(edges["rear"], vertical=False)
    left = _fit_edge(edges["left"], vertical=True)
    corners = np.asarray(
        [
            _intersection(front, left),
            _intersection(front, right),
            _intersection(rear, right),
            _intersection(rear, left),
        ],
        dtype=np.float64,
    )
    image_width, image_height = frame_record["image_size_px"]
    if (
        np.any(corners < 0)
        or np.any(corners[:, 0] >= image_width)
        or np.any(corners[:, 1] >= image_height)
    ):
        raise ValueError("Fitted keyboard corner leaves the reference image")

    footprint = np.asarray([[0, 0], [width, 0], [width, depth], [0, depth]], dtype=float)
    keyboard_to_image = cv2.getPerspectiveTransform(
        footprint.astype(np.float32), corners.astype(np.float32)
    )
    keyboard_to_image /= keyboard_to_image[2, 2]
    image_to_keyboard = np.linalg.inv(keyboard_to_image)
    image_to_keyboard /= image_to_keyboard[2, 2]
    image_to_board = np.asarray(registration["mapping"]["image_to_board_homography"])
    observed_board = _transform(corners, image_to_board)
    raw_widths = [
        float(np.linalg.norm(observed_board[1] - observed_board[0])),
        float(np.linalg.norm(observed_board[2] - observed_board[3])),
    ]
    raw_depths = [
        float(np.linalg.norm(observed_board[3] - observed_board[0])),
        float(np.linalg.norm(observed_board[2] - observed_board[1])),
    ]

    centered_footprint = footprint - footprint.mean(axis=0)
    centered_observed = observed_board - observed_board.mean(axis=0)
    left_svd, _values, right_svd = np.linalg.svd(centered_footprint.T @ centered_observed)
    rotation = left_svd @ right_svd
    if np.linalg.det(rotation) < 0:
        left_svd[:, -1] *= -1
        rotation = left_svd @ right_svd
    translation = observed_board.mean(axis=0) - footprint.mean(axis=0) @ rotation
    fitted_board = footprint @ rotation + translation
    housing_residuals = np.linalg.norm(fitted_board - observed_board, axis=1)
    yaw_deg = math.degrees(math.atan2(rotation[0, 1], rotation[0, 0]))

    target_layout, target_fit = _image_fitted_target_layout(
        profile, keyboard["target_anchor_centers_px"], image_to_keyboard
    )
    projected_targets = {}
    for name, item in target_layout.items():
        center = np.asarray(item["center_xy_mm"], dtype=float)
        half = np.asarray(item["half_extent_mm"], dtype=float)
        local_corners = np.asarray(
            [center + [-half[0], -half[1]], center + [half[0], -half[1]],
             center + [half[0], half[1]], center + [-half[0], half[1]]]
        )
        projected_targets[name] = {
            "nominal_center_keyboard_xy_mm": _round_vector(
                item["nominal_center_xy_mm"], 3
            ),
            "image_fitted_center_keyboard_xy_mm": _round_vector(center, 3),
            "nominal_to_image_fitted_delta_mm": _round_vector(
                center - np.asarray(item["nominal_center_xy_mm"], dtype=float), 3
            ),
            "nominal_half_extent_mm": _round_vector(half, 3),
            "center_px": _round_vector(_transform([center], keyboard_to_image)[0], 3),
            "region_corners_px": [
                _round_vector(point, 3)
                for point in _transform(local_corners, keyboard_to_image)
            ],
        }

    scale = registration["mapping"]["local_scale_at_board_center_px_per_mm"]
    pixel_tolerance_mm = float(keyboard["pixel_annotation_tolerance_px"]) / min(
        float(scale["x"]), float(scale["y"])
    )
    held_out_max = float(
        registration["validation"]["held_out_station_center_max_error_mm"]
    )
    additive_review_bound = held_out_max + float(np.max(housing_residuals)) + pixel_tolerance_mm
    study_margin = float(keyboard["board_xy_study_margin_mm"])
    if study_margin < additive_review_bound:
        raise ValueError("Declared board XY study margin is smaller than the additive review bound")

    receipt_path = reference_path.parent / "receipt.json"
    repeatability = _frame_repeatability(
        reference_path.parent, reference_path, annotation["repeatability_roi_px"]
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected_hashes = {
        frame["file_name"]: frame["sha256"]
        for cycle in receipt["reopen_cycles"]
        for frame in cycle["frames"]
    }
    if {row["file_name"]: row["sha256"] for row in repeatability["frames"]} != expected_hashes:
        raise ValueError("Retained frame set differs from its capture receipt")

    return {
        "schema": "rocell.fixed_camera_keyboard_overlay.v1",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "status": "READ_ONLY_IMAGE_OVERLAY_REVIEWED_NOT_MOTION_AUTHORITY",
        "workcell_epoch_id": epoch,
        "inputs": {
            "annotation_path": annotation_path.relative_to(ROOT).as_posix(),
            "annotation_sha256": sha256_file(annotation_path),
            "board_registration_path": registration_path.relative_to(ROOT).as_posix(),
            "board_registration_sha256": sha256_file(registration_path),
            "target_profile_path": profile_path.relative_to(ROOT).as_posix(),
            "target_profile_sha256": sha256_file(profile_path),
            "capture_receipt_path": receipt_path.relative_to(ROOT).as_posix(),
            "capture_receipt_sha256": sha256_file(receipt_path),
            "reference_frame": frame_record,
        },
        "keyboard_geometry": {
            "device_model": keyboard["device_model"],
            "housing_dimensions_mm": dimensions,
            "target_pitch_mm": float(profile["pitch_mm"]),
            "target_count": len(projected_targets),
            "target_geometry_status": "IMAGE_FITTED_FROM_REVIEWED_KEY_CENTER_ANCHORS_NOT_PRODUCT_METROLOGY",
            "housing_corners_px": {
                name: _round_vector(point, 3)
                for name, point in zip(keyboard["corner_order"], corners, strict=True)
            },
            "keyboard_to_image_homography": _round_matrix(keyboard_to_image),
            "image_to_keyboard_homography": _round_matrix(image_to_keyboard),
            "target_fit_summary": target_fit,
            "projected_targets": projected_targets,
        },
        "board_plane_interpretation": {
            "raw_projected_housing_corners_xy_mm": {
                name: _round_vector(point, 3)
                for name, point in zip(keyboard["corner_order"], observed_board, strict=True)
            },
            "raw_apparent_widths_mm": _round_vector(raw_widths, 3),
            "raw_apparent_depths_mm": _round_vector(raw_depths, 3),
            "dimension_constrained_front_left_xy_mm": _round_vector(translation, 3),
            "dimension_constrained_yaw_deg": round(yaw_deg, 4),
            "dimension_constrained_corners_xy_mm": [
                _round_vector(point, 3) for point in fitted_board
            ],
            "housing_fit_corner_residuals_mm": _round_vector(housing_residuals, 3),
            "housing_fit_max_corner_residual_mm": round(float(np.max(housing_residuals)), 4),
            "keyboard_height_above_board_mm": height,
            "interpretation": "Raw board-plane dimensions are enlarged by keyboard height/parallax; the known 315 x 147 mm housing constrains the provisional board pose.",
        },
        "uncertainty_review": {
            "board_mapping_held_out_max_error_mm": held_out_max,
            "housing_model_max_corner_residual_mm": round(float(np.max(housing_residuals)), 4),
            "annotation_tolerance_px": float(keyboard["pixel_annotation_tolerance_px"]),
            "annotation_tolerance_conservative_mm": round(pixel_tolerance_mm, 4),
            "additive_review_bound_mm": round(additive_review_bound, 4),
            "declared_board_xy_study_margin_mm": study_margin,
            "margin_covers_additive_review_bound": study_margin >= additive_review_bound,
        },
        "retained_frame_repeatability": repeatability,
        "limitations": annotation["limitations"],
        "use": {
            "permitted": [
                "review the keyboard housing and 46 nominal key targets in retained B0477 frames",
                "measure fixed-frame image repeatability without opening the camera",
                "prepare dry-run observation and target-selection integration",
            ],
            "not_established": [
                "measured physical key-center metrology",
                "camera intrinsics, distortion, or off-plane reconstruction",
                "board-to-robot transform or tool-center-point geometry",
                "hover, descent, contact, or camera-guided motion authority",
            ],
        },
        "authority": {
            "hardware_writes": 0,
            "camera_opened": False,
            "robot_transport_opened": False,
            "robot_motion": False,
            "camera_guided_motion": False,
            "contact": False,
            "physical_authority": False,
        },
    }


def render_overlay(report: dict[str, Any], output_path: Path) -> None:
    import cv2
    import numpy as np

    reference = ROOT / report["inputs"]["reference_frame"]["path"]
    image = cv2.imread(str(reference), cv2.IMREAD_COLOR)
    corners = np.asarray(
        list(report["keyboard_geometry"]["housing_corners_px"].values()), dtype=int
    )
    cv2.polylines(image, [corners], True, (0, 255, 255), 3, cv2.LINE_AA)
    for name, target in report["keyboard_geometry"]["projected_targets"].items():
        region = np.asarray(target["region_corners_px"], dtype=int)
        center = tuple(round(value) for value in target["center_px"])
        cv2.polylines(image, [region], True, (0, 180, 0), 1, cv2.LINE_AA)
        cv2.circle(image, center, 4, (0, 255, 0), -1, cv2.LINE_AA)
        cv2.putText(image, name, (center[0] + 5, center[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 255, 0), 1, cv2.LINE_AA)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise ValueError(f"Could not write overlay preview: {output_path}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Measure a retained fixed-camera keyboard overlay.")
    result.add_argument("--annotation", type=Path, default=DEFAULT_ANNOTATION)
    result.add_argument("--board-registration", type=Path, default=DEFAULT_REGISTRATION)
    result.add_argument("--target-profile", type=Path, default=DEFAULT_PROFILE)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--preview", type=Path)
    result.add_argument("--created-at", help="Optional stable ISO-8601 evidence timestamp")
    return result


def main() -> int:
    args = parser().parse_args()
    report = build_report(
        args.annotation.resolve(strict=True),
        args.board_registration.resolve(strict=True),
        args.target_profile.resolve(strict=True),
        created_at=args.created_at,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    if args.preview:
        render_overlay(report, args.preview.resolve())
    print(json.dumps({
        "target_count": report["keyboard_geometry"]["target_count"],
        "dimension_constrained_front_left_xy_mm": report["board_plane_interpretation"]["dimension_constrained_front_left_xy_mm"],
        "dimension_constrained_yaw_deg": report["board_plane_interpretation"]["dimension_constrained_yaw_deg"],
        "additive_review_bound_mm": report["uncertainty_review"]["additive_review_bound_mm"],
        "maximum_retained_frame_shift_px": report["retained_frame_repeatability"]["maximum_radial_shift_px"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
