"""Fit repeatable image-space keycap-center candidates without motion authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from rocell.vision.fixed_camera_key_feedback_roi_v1 import (
    EXPECTED_KEY_COUNT,
    estimate_files as estimate_roi_files,
)
from rocell.vision.fixed_camera_key_row_observability_v1 import (
    RECTIFIED_PIXELS_PER_MM,
    rectify_luminance,
)
from rocell.vision.fixed_camera_key_row_repeatability_v1 import (
    FixedCameraKeyRowRepeatabilityError,
    estimate_files as estimate_repeatability_files,
)


MAX_JSON_BYTES = 256 * 1024
MAX_KEY_CENTER_TEMPORAL_DELTA_MM = 3.1
ROW_SHIFT_SEARCH_MM = 7.0
ROW_RESIDUAL_SEARCH_MM = 2.0
EDGE_SEARCH_RADIUS_MM = 1.667
STANDARD_HALF_WIDTH_MIN_MM = 6.0
STANDARD_HALF_WIDTH_MAX_MM = 10.0
STANDARD_HALF_HEIGHT_MIN_MM = 4.0
STANDARD_HALF_HEIGHT_MAX_MM = 10.0
STANDARD_SPAN_MIN_MM = 15.0
STANDARD_SPAN_MAX_MM = 23.0


class FixedCameraKeyCenterCandidatesError(ValueError):
    """The two-frame keycap-center candidate assessment is invalid."""


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise FixedCameraKeyCenterCandidatesError(f"{label} must be a regular file")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise FixedCameraKeyCenterCandidatesError(f"{label} exceeds 256 KiB")
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyCenterCandidatesError(
            f"could not read {label}: {exc}") from exc
    if type(value) is not dict:
        raise FixedCameraKeyCenterCandidatesError(f"{label} must be an object")
    return value, payload


def _grid(low: float, high: float):
    import numpy as np

    step = 1.0 / RECTIFIED_PIXELS_PER_MM
    return np.arange(low, high + step / 2.0, step)


def _edge_sample(gradient: object, x_mm: float, y_mm: float, axis: str) -> float:
    import numpy as np

    pixels = np.asarray(gradient, dtype=float)
    x_px = int(round(x_mm * RECTIFIED_PIXELS_PER_MM))
    y_px = int(round(y_mm * RECTIFIED_PIXELS_PER_MM))
    if axis == "x":
        region = pixels[max(0, y_px - 15):min(pixels.shape[0], y_px + 16),
                        max(0, x_px - 1):min(pixels.shape[1], x_px + 2)]
    elif axis == "y":
        region = pixels[max(0, y_px - 1):min(pixels.shape[0], y_px + 2),
                        max(0, x_px - 15):min(pixels.shape[1], x_px + 16)]
    else:
        raise FixedCameraKeyCenterCandidatesError("edge axis must be x or y")
    if region.size == 0:
        raise FixedCameraKeyCenterCandidatesError("edge sample leaves rectified image")
    return float(np.mean(region))


def _peak(profile: object, expected_mm: float,
          radius_mm: float = EDGE_SEARCH_RADIUS_MM) -> tuple[float, float]:
    import numpy as np

    values = np.asarray(profile, dtype=float)
    low = max(1, int(round((expected_mm - radius_mm)
                           * RECTIFIED_PIXELS_PER_MM)))
    high = min(len(values) - 1, int(round((expected_mm + radius_mm)
                                          * RECTIFIED_PIXELS_PER_MM)) + 1)
    if low >= high:
        raise FixedCameraKeyCenterCandidatesError("edge peak search is empty")
    region = values[low:high]
    index = low + int(np.argmax(region))
    median = float(np.median(region))
    confidence = float(values[index] / (median + 1e-6))
    return index / RECTIFIED_PIXELS_PER_MM, confidence


def _gradients(luminance: object) -> tuple[object, object]:
    import numpy as np

    pixels = np.asarray(luminance, dtype=float)
    if pixels.ndim != 2 or not np.all(np.isfinite(pixels)):
        raise FixedCameraKeyCenterCandidatesError(
            "rectified luminance must be a finite two-dimensional array")
    return (
        np.abs(np.diff(pixels, axis=1, prepend=pixels[:, :1])),
        np.abs(np.diff(pixels, axis=0, prepend=pixels[:1, :])),
    )


def _fit_standard_geometry(x_gradient: object, y_gradient: object,
                           keyboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    import numpy as np

    rows = keyboard.get("rows")
    if not isinstance(rows, list) or len(rows) != 4:
        raise FixedCameraKeyCenterCandidatesError("exactly four standard rows required")
    half_extent = keyboard.get("key_half_extent_mm")
    if not isinstance(half_extent, list) or len(half_extent) != 2:
        raise FixedCameraKeyCenterCandidatesError("standard key extent is missing")

    y_candidates: list[tuple[float, float, float]] = []
    for shift in _grid(-ROW_SHIFT_SEARCH_MM, ROW_SHIFT_SEARCH_MM):
        for half_height in _grid(STANDARD_HALF_HEIGHT_MIN_MM,
                                 STANDARD_HALF_HEIGHT_MAX_MM):
            scores = []
            for row in rows:
                first_x, row_y = map(float, row["first_center_xy_mm"])
                pitch = float(row["step_xy_mm"][0])
                for index in range(len(row["key_ids"])):
                    x_value = first_x + index * pitch
                    scores.extend([
                        _edge_sample(y_gradient, x_value,
                                     row_y + shift - half_height, "y"),
                        _edge_sample(y_gradient, x_value,
                                     row_y + shift + half_height, "y"),
                    ])
            y_candidates.append((float(np.mean(scores)), float(shift),
                                 float(half_height)))
    _, global_y_shift, half_height = max(y_candidates)

    fitted_rows = []
    for row_index, row in enumerate(rows):
        names = list(row["key_ids"])
        first_x, row_y = map(float, row["first_center_xy_mm"])
        pitch = float(row["step_xy_mm"][0])
        residual_candidates = []
        for residual in _grid(-ROW_RESIDUAL_SEARCH_MM, ROW_RESIDUAL_SEARCH_MM):
            scores = []
            for index in range(len(names)):
                x_value = first_x + index * pitch
                scores.extend([
                    _edge_sample(y_gradient, x_value,
                                 row_y + global_y_shift + residual - half_height,
                                 "y"),
                    _edge_sample(y_gradient, x_value,
                                 row_y + global_y_shift + residual + half_height,
                                 "y"),
                ])
            residual_candidates.append((float(np.mean(scores)), float(residual)))
        _, row_y_residual = max(residual_candidates)
        fitted_y = row_y + global_y_shift + row_y_residual

        x_candidates = []
        for shift in _grid(-ROW_SHIFT_SEARCH_MM, ROW_SHIFT_SEARCH_MM):
            for half_width in _grid(STANDARD_HALF_WIDTH_MIN_MM,
                                    STANDARD_HALF_WIDTH_MAX_MM):
                scores = []
                for index in range(len(names)):
                    center = first_x + index * pitch + shift
                    scores.extend([
                        _edge_sample(x_gradient, center - half_width, fitted_y, "x"),
                        _edge_sample(x_gradient, center + half_width, fitted_y, "x"),
                    ])
                x_candidates.append((float(np.mean(scores)), float(shift),
                                     float(half_width)))
        _, x_shift, half_width = max(x_candidates)
        fitted_rows.append({
            "row_index": row_index,
            "first_key": names[0],
            "last_key": names[-1],
            "x_shift_mm": round(x_shift, 3),
            "y_shift_mm": round(global_y_shift + row_y_residual, 3),
            "half_width_mm": round(half_width, 3),
            "half_height_mm": round(half_height, 3),
        })
    return fitted_rows


def _candidate_from_edges(x_gradient: object, y_gradient: object, *,
                          center_x: float, center_y: float,
                          half_width: float, half_height: float,
                          x_radius: float = EDGE_SEARCH_RADIUS_MM) -> dict[str, Any]:
    import numpy as np

    y_low = max(0, int(round((center_y - half_height - 2.0)
                              * RECTIFIED_PIXELS_PER_MM)))
    y_high = min(np.asarray(x_gradient).shape[0],
                 int(round((center_y + half_height + 2.0)
                           * RECTIFIED_PIXELS_PER_MM)) + 1)
    x_low = max(0, int(round((center_x - half_width - 2.0)
                              * RECTIFIED_PIXELS_PER_MM)))
    x_high = min(np.asarray(y_gradient).shape[1],
                 int(round((center_x + half_width + 2.0)
                           * RECTIFIED_PIXELS_PER_MM)) + 1)
    x_profile = np.percentile(np.asarray(x_gradient)[y_low:y_high, :], 70, axis=0)
    y_profile = np.percentile(np.asarray(y_gradient)[:, x_low:x_high], 70, axis=1)
    left, left_confidence = _peak(x_profile, center_x - half_width, x_radius)
    right, right_confidence = _peak(x_profile, center_x + half_width, x_radius)
    front, front_confidence = _peak(y_profile, center_y - half_height)
    rear, rear_confidence = _peak(y_profile, center_y + half_height)
    return {
        "center_xy_mm": [round((left + right) / 2.0, 3),
                         round((front + rear) / 2.0, 3)],
        "edge_span_xy_mm": [round(right - left, 3), round(rear - front, 3)],
        "minimum_edge_peak_ratio": round(min(
            left_confidence, right_confidence,
            front_confidence, rear_confidence), 3),
    }


def fit_frame_candidates(luminance: object,
                         keyboard: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fit all 46 candidates from one rectified frame."""
    x_gradient, y_gradient = _gradients(luminance)
    fitted_rows = _fit_standard_geometry(x_gradient, y_gradient, keyboard)
    rows = keyboard["rows"]
    candidates: dict[str, Any] = {}
    for row_fit, row in zip(fitted_rows, rows):
        first_x, row_y = map(float, row["first_center_xy_mm"])
        pitch = float(row["step_xy_mm"][0])
        for index, name in enumerate(row["key_ids"]):
            candidates[name] = _candidate_from_edges(
                x_gradient, y_gradient,
                center_x=first_x + index * pitch + row_fit["x_shift_mm"],
                center_y=row_y + row_fit["y_shift_mm"],
                half_width=row_fit["half_width_mm"],
                half_height=row_fit["half_height_mm"],
            )

    explicit = keyboard.get("explicit_targets")
    if not isinstance(explicit, Mapping):
        raise FixedCameraKeyCenterCandidatesError("explicit targets are missing")
    row_by_key = {name: row_fit for row_fit, row in zip(fitted_rows, rows)
                  for name in row["key_ids"]}
    for name, anchor in (("TAB", "Q"), ("ENTER", "A")):
        target = explicit[name]
        row_fit = row_by_key[anchor]
        candidates[name] = _candidate_from_edges(
            x_gradient, y_gradient,
            center_x=float(target["center_xy_mm"][0]) + row_fit["x_shift_mm"],
            center_y=float(target["center_xy_mm"][1]) + row_fit["y_shift_mm"],
            half_width=float(target["half_extent_mm"][0]),
            half_height=row_fit["half_height_mm"],
        )
    space = explicit["SPACE"]
    mean_y_shift = sum(float(row["y_shift_mm"]) for row in fitted_rows) / 4.0
    candidates["SPACE"] = _candidate_from_edges(
        x_gradient, y_gradient,
        center_x=float(space["center_xy_mm"][0]),
        center_y=float(space["center_xy_mm"][1]) + mean_y_shift,
        half_width=float(space["half_extent_mm"][0]),
        half_height=fitted_rows[-1]["half_height_mm"],
    )
    if len(candidates) != EXPECTED_KEY_COUNT:
        raise FixedCameraKeyCenterCandidatesError(
            f"expected {EXPECTED_KEY_COUNT} candidates, got {len(candidates)}")
    return candidates, fitted_rows


def compare_candidates(reference: Mapping[str, Any], repeat: Mapping[str, Any],
                       keyboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Compare exact key identities and enforce temporal and span limits."""
    if set(reference) != set(repeat) or len(reference) != EXPECTED_KEY_COUNT:
        raise FixedCameraKeyCenterCandidatesError("candidate key identities differ")
    explicit = keyboard["explicit_targets"]
    results = []
    for key_id in reference:
        first = reference[key_id]
        second = repeat[key_id]
        first_center = [float(value) for value in first["center_xy_mm"]]
        second_center = [float(value) for value in second["center_xy_mm"]]
        delta = math.dist(first_center, second_center)
        spans = [float(value) for value in first["edge_span_xy_mm"]
                 + second["edge_span_xy_mm"]]
        if key_id in explicit:
            expected_x = 2.0 * float(explicit[key_id]["half_extent_mm"][0])
            span_passed = (all(15.0 <= value <= 24.0 for value in spans[1::2])
                           and all(expected_x - 5.0 <= value <= expected_x + 7.0
                                   for value in spans[0::2]))
        else:
            span_passed = all(STANDARD_SPAN_MIN_MM <= value <= STANDARD_SPAN_MAX_MM
                              for value in spans)
        passed = delta <= MAX_KEY_CENTER_TEMPORAL_DELTA_MM and span_passed
        results.append({
            "key_id": key_id,
            "reference_center_xy_mm": first["center_xy_mm"],
            "repeat_center_xy_mm": second["center_xy_mm"],
            "temporal_center_delta_mm": round(delta, 3),
            "reference_edge_span_xy_mm": first["edge_span_xy_mm"],
            "repeat_edge_span_xy_mm": second["edge_span_xy_mm"],
            "reference_minimum_edge_peak_ratio": first["minimum_edge_peak_ratio"],
            "repeat_minimum_edge_peak_ratio": second["minimum_edge_peak_ratio"],
            "span_plausibility_passed": span_passed,
            "candidate_repeatability_passed": passed,
        })
    return results


def _rectified_frame(path: Path, homography: object,
                     keyboard: Mapping[str, Any]):
    dimensions = keyboard["device_size_mm"]
    try:
        with Image.open(path) as image:
            image.load()
            if image.size != (1920, 1080):
                raise FixedCameraKeyCenterCandidatesError(
                    "source frame dimensions are not 1920x1080")
            return rectify_luminance(
                image, homography, float(dimensions[0]), float(dimensions[1]))
    except OSError as exc:
        raise FixedCameraKeyCenterCandidatesError(
            f"could not decode source frame: {exc}") from exc


def estimate_files(
    repeatability_result_path: Path, reference_result_path: Path,
    registration_path: Path, calibration_path: Path, profile_path: Path,
    reference_frame_path: Path, repeat_frame_path: Path,
    repeat_capture_path: Path,
) -> dict[str, Any]:
    stored_repeatability, repeatability_bytes = _read_json(
        repeatability_result_path, "repeatability result")
    try:
        reproduced = estimate_repeatability_files(
            reference_result_path, registration_path, calibration_path,
            profile_path, reference_frame_path, repeat_frame_path,
            repeat_capture_path)
    except FixedCameraKeyRowRepeatabilityError as exc:
        raise FixedCameraKeyCenterCandidatesError(str(exc)) from exc
    if stored_repeatability != reproduced:
        raise FixedCameraKeyCenterCandidatesError(
            "row repeatability result does not reproduce")
    if not stored_repeatability.get("row_feature_temporal_repeatability_ready"):
        raise FixedCameraKeyCenterCandidatesError(
            "row repeatability prerequisite is not ready")

    profile, _ = _read_json(profile_path, "target profile")
    keyboard = profile.get("keyboard")
    if not isinstance(keyboard, Mapping):
        raise FixedCameraKeyCenterCandidatesError("keyboard profile is missing")
    roi = estimate_roi_files(
        registration_path, calibration_path, profile_path,
        source_frame_path=reference_frame_path)
    reference_luminance = _rectified_frame(
        reference_frame_path, roi["local_keyboard_to_pixel_homography"], keyboard)
    repeat_luminance = _rectified_frame(
        repeat_frame_path, roi["local_keyboard_to_pixel_homography"], keyboard)
    reference, reference_rows = fit_frame_candidates(reference_luminance, keyboard)
    repeat, repeat_rows = fit_frame_candidates(repeat_luminance, keyboard)
    comparisons = compare_candidates(reference, repeat, keyboard)
    candidates_ready = all(item["candidate_repeatability_passed"]
                           for item in comparisons)
    return {
        "schema": "rocell.fixed_camera_key_center_candidates.v1",
        "status": "IMAGE_SPACE_KEY_CENTER_CANDIDATES_ONLY_NOT_MOTION_TARGETS",
        "profile": "no_attachment",
        "repeatability_result_sha256": hashlib.sha256(
            repeatability_bytes).hexdigest(),
        "reference_frame_sha256": stored_repeatability["reference_frame_sha256"],
        "repeat_frame_sha256": stored_repeatability["repeat_frame_sha256"],
        "rectified_pixels_per_mm": RECTIFIED_PIXELS_PER_MM,
        "maximum_key_center_temporal_delta_mm": (
            MAX_KEY_CENTER_TEMPORAL_DELTA_MM),
        "reference_row_fits": reference_rows,
        "repeat_row_fits": repeat_rows,
        "key_center_candidates": comparisons,
        "key_center_candidate_count": len(comparisons),
        "image_space_key_center_candidates_ready": candidates_ready,
        "independent_key_center_observations_present": True,
        "individual_key_localization_ready": False,
        "board_space_motion_targets_emitted": False,
        "board_to_robot_transform_verified": False,
        "physical_clearance_verified": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "blockers": [
            "BOARD_SPACE_KEY_CENTER_VALIDATION_MISSING",
            "BOARD_TO_ROBOT_TRANSFORM_UNVERIFIED",
            "PHYSICAL_CLEARANCE_UNVERIFIED",
        ],
        "limitations": [
            "Candidates are keycap-edge fits in the dimension-constrained keyboard rectification, not board-space contact targets.",
            "The same frozen housing homography is used for both frames; no board transform is refit from key edges.",
            "The no-attachment result does not apply to the separate stylus_attachment trajectory and TCP profile.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repeatability_result", "reference_result", "registration",
                 "calibration", "targets", "reference_frame", "repeat_frame",
                 "repeat_capture"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = estimate_files(
        args.repeatability_result, args.reference_result, args.registration,
        args.calibration, args.targets, args.reference_frame,
        args.repeat_frame, args.repeat_capture)
    encoded = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    if args.output:
        args.output.write_bytes(encoded)
    else:
        print(encoded.decode(), end="")
    return 0 if result["image_space_key_center_candidates_ready"] else 2


__all__ = [
    "FixedCameraKeyCenterCandidatesError", "compare_candidates",
    "estimate_files", "fit_frame_candidates",
]


if __name__ == "__main__":
    raise SystemExit(main())
