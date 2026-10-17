"""Measure repeatable keyboard-row image features without creating targets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from rocell.vision.fixed_camera_key_feedback_roi_v1 import (
    FixedCameraKeyFeedbackRoiError,
    estimate_files as estimate_roi_files,
)
from rocell.vision.fixed_camera_keyboard_registration_v1 import (
    STYLUS_PROFILE,
    SUPPORTED_PROFILE,
)


RECTIFIED_PIXELS_PER_MM = 3
ROW_SEARCH_RADIUS_MM = 6.0
GAP_PHASE_SEARCH_RADIUS_MM = 6.0
MIN_ROW_FEATURE_CONTRAST = 15.0
MIN_GAP_PHASE_PEAK_RATIO = 1.4
MAX_FEATURE_OFFSET_MM = 7.0
MAX_JSON_BYTES = 256 * 1024


class FixedCameraKeyRowObservabilityError(ValueError):
    """The frame cannot provide the bounded row-feature assessment."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file() or path.is_symlink():
            raise FixedCameraKeyRowObservabilityError(
                "JSON input must be a regular file")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise FixedCameraKeyRowObservabilityError(
                "JSON input exceeds 256 KiB")
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyRowObservabilityError(
            f"could not read JSON input: {exc}") from exc
    if type(document) is not dict:
        raise FixedCameraKeyRowObservabilityError("JSON input must be an object")
    return document


def rectify_luminance(image: Image.Image, homography: object,
                      width_mm: float, depth_mm: float):
    import numpy as np

    rgb = np.asarray(image.convert("RGB"), dtype=float)
    matrix = np.asarray(homography, dtype=float)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise FixedCameraKeyRowObservabilityError("ROI homography is invalid")
    output_width = int(round(width_mm * RECTIFIED_PIXELS_PER_MM))
    output_height = int(round(depth_mm * RECTIFIED_PIXELS_PER_MM))
    rows, columns = np.mgrid[0:output_height, 0:output_width]
    local = np.stack([
        columns / RECTIFIED_PIXELS_PER_MM,
        rows / RECTIFIED_PIXELS_PER_MM,
        np.ones_like(columns),
    ], axis=-1)
    projected = local @ matrix.T
    denominators = projected[..., 2]
    if np.any(np.abs(denominators) < 1e-12):
        raise FixedCameraKeyRowObservabilityError("ROI homography is singular")
    x_values = projected[..., 0] / denominators
    y_values = projected[..., 1] / denominators
    if (np.any(x_values < 0) or np.any(y_values < 0)
            or np.any(x_values > rgb.shape[1] - 1)
            or np.any(y_values > rgb.shape[0] - 1)):
        raise FixedCameraKeyRowObservabilityError(
            "rectified keyboard samples leave the source frame")

    x0 = np.floor(x_values).astype(int)
    y0 = np.floor(y_values).astype(int)
    x1 = np.minimum(x0 + 1, rgb.shape[1] - 1)
    y1 = np.minimum(y0 + 1, rgb.shape[0] - 1)
    x_weight = (x_values - x0)[..., None]
    y_weight = (y_values - y0)[..., None]
    rectified = (
        rgb[y0, x0] * (1 - x_weight) * (1 - y_weight)
        + rgb[y0, x1] * x_weight * (1 - y_weight)
        + rgb[y1, x0] * (1 - x_weight) * y_weight
        + rgb[y1, x1] * x_weight * y_weight
    )
    return (0.2126 * rectified[..., 0]
            + 0.7152 * rectified[..., 1]
            + 0.0722 * rectified[..., 2])


def assess_rectified_luminance(
    luminance: object, keyboard: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Find one contrast band and a repeated gap phase for each standard row."""
    import numpy as np

    pixels = np.asarray(luminance, dtype=float)
    if pixels.ndim != 2 or not np.all(np.isfinite(pixels)):
        raise FixedCameraKeyRowObservabilityError(
            "rectified luminance must be a finite two-dimensional array")
    expected_shape = (
        int(round(float(keyboard["device_size_mm"][1])
                  * RECTIFIED_PIXELS_PER_MM)),
        int(round(float(keyboard["device_size_mm"][0])
                  * RECTIFIED_PIXELS_PER_MM)),
    )
    if pixels.shape != expected_shape:
        raise FixedCameraKeyRowObservabilityError(
            "rectified luminance dimensions differ from keyboard profile")
    rows = keyboard.get("rows")
    if not isinstance(rows, list) or len(rows) != 4:
        raise FixedCameraKeyRowObservabilityError(
            "exactly four standard keyboard rows are required")
    horizontal_gradient = np.abs(
        np.diff(pixels, axis=1, prepend=pixels[:, :1]))
    results: list[dict[str, Any]] = []
    scale = RECTIFIED_PIXELS_PER_MM
    search_px = int(round(ROW_SEARCH_RADIUS_MM * scale))
    phase_px = int(round(GAP_PHASE_SEARCH_RADIUS_MM * scale))

    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise FixedCameraKeyRowObservabilityError("keyboard row is invalid")
        names = row.get("key_ids")
        first = row.get("first_center_xy_mm")
        step = row.get("step_xy_mm")
        if (not isinstance(names, list) or len(names) < 2
                or not isinstance(first, list) or len(first) != 2
                or not isinstance(step, list) or len(step) != 2):
            raise FixedCameraKeyRowObservabilityError("keyboard row is incomplete")
        first_x, expected_y = map(float, first)
        step_x, step_y = map(float, step)
        if step_x <= 0 or step_y != 0:
            raise FixedCameraKeyRowObservabilityError(
                "keyboard rows must have a positive horizontal step")
        centers = [(first_x + index * step_x, expected_y)
                   for index in range(len(names))]
        x_low = max(0, int(round((centers[0][0] - 7.0) * scale)))
        x_high = min(pixels.shape[1],
                     int(round((centers[-1][0] + 7.0) * scale)) + 1)
        expected_y_px = int(round(expected_y * scale))
        y_low = expected_y_px - search_px
        y_high = expected_y_px + search_px + 1
        if y_low < 0 or y_high > pixels.shape[0] or x_low >= x_high:
            raise FixedCameraKeyRowObservabilityError(
                "keyboard row search band leaves the rectified image")
        brightness_profile = np.percentile(
            pixels[y_low:y_high, x_low:x_high], 90, axis=1)
        peak_index = int(np.argmax(brightness_profile))
        observed_y = (y_low + peak_index) / scale
        contrast = float(
            brightness_profile[peak_index] - np.median(brightness_profile))

        phase_scores: list[float] = []
        vertical_low = expected_y_px - search_px
        vertical_high = expected_y_px + search_px + 1
        for offset_px in range(-phase_px, phase_px + 1):
            samples: list[float] = []
            for left, right in zip(centers, centers[1:]):
                gap_x = int(round(((left[0] + right[0]) / 2) * scale))
                gap_x += offset_px
                if not 0 <= gap_x < pixels.shape[1]:
                    raise FixedCameraKeyRowObservabilityError(
                        "gap phase search leaves the rectified image")
                samples.extend(horizontal_gradient[
                    vertical_low:vertical_high, gap_x].tolist())
            phase_scores.append(float(np.mean(samples)))
        phase_index = int(np.argmax(phase_scores))
        phase_offset = (phase_index - phase_px) / scale
        phase_median = float(np.median(phase_scores))
        phase_peak = phase_scores[phase_index]
        if phase_median > 0:
            peak_ratio = phase_peak / phase_median
        elif phase_peak > 0:
            peak_ratio = 1_000_000_000.0
        else:
            peak_ratio = 0.0
        contrast_passed = contrast >= MIN_ROW_FEATURE_CONTRAST
        phase_passed = peak_ratio >= MIN_GAP_PHASE_PEAK_RATIO
        offset_passed = (abs(observed_y - expected_y) <= MAX_FEATURE_OFFSET_MM
                         and abs(phase_offset) <= MAX_FEATURE_OFFSET_MM)
        results.append({
            "row_index": row_index,
            "first_key": names[0],
            "last_key": names[-1],
            "key_count": len(names),
            "expected_row_y_mm": expected_y,
            "observed_contrast_band_y_mm": round(observed_y, 3),
            "contrast_band_offset_mm": round(observed_y - expected_y, 3),
            "contrast_above_band_median": round(contrast, 3),
            "repeated_gap_phase_offset_mm": round(phase_offset, 3),
            "gap_phase_peak_ratio": round(peak_ratio, 3),
            "contrast_passed": contrast_passed,
            "gap_phase_passed": phase_passed,
            "offset_limit_passed": offset_passed,
            "observable": contrast_passed and phase_passed and offset_passed,
        })
    return results


def estimate_files(
    registration_input_path: Path, calibration_path: Path,
    profile_path: Path, source_frame_path: Path, *,
    profile: str = SUPPORTED_PROFILE,
) -> dict[str, Any]:
    try:
        roi = estimate_roi_files(
            registration_input_path, calibration_path, profile_path,
            profile=profile, source_frame_path=source_frame_path)
    except FixedCameraKeyFeedbackRoiError as exc:
        raise FixedCameraKeyRowObservabilityError(str(exc)) from exc
    profile_document = _load_json(profile_path)
    keyboard = profile_document.get("keyboard")
    if not isinstance(keyboard, Mapping):
        raise FixedCameraKeyRowObservabilityError("keyboard profile is missing")
    try:
        with Image.open(source_frame_path) as image:
            image.load()
            if image.size != (roi["camera_width_px"], roi["camera_height_px"]):
                raise FixedCameraKeyRowObservabilityError(
                    "decoded frame dimensions differ from ROI contract")
            dimensions = keyboard.get("device_size_mm")
            if not isinstance(dimensions, list) or len(dimensions) != 3:
                raise FixedCameraKeyRowObservabilityError(
                    "keyboard dimensions are missing")
            luminance = rectify_luminance(
                image, roi["local_keyboard_to_pixel_homography"],
                float(dimensions[0]), float(dimensions[1]))
    except (OSError, ValueError) as exc:
        raise FixedCameraKeyRowObservabilityError(
            f"could not decode source frame: {exc}") from exc
    rows = assess_rectified_luminance(luminance, keyboard)
    rows_ready = all(row["observable"] for row in rows)
    profile_ready = profile == SUPPORTED_PROFILE and roi[
        "image_space_feedback_windows_ready"]
    blockers = ["INDIVIDUAL_KEY_CENTERS_NOT_OBSERVED"]
    if not rows_ready:
        blockers.append("STANDARD_KEY_ROW_FEATURES_INSUFFICIENT")
    if profile == STYLUS_PROFILE:
        blockers.append("STYLUS_TCP_AND_CONTACT_PROFILE_MISSING")
    return {
        "schema": "rocell.fixed_camera_key_row_observability.v1",
        "status": "ROW_FEATURE_EVIDENCE_ONLY_NOT_KEY_CENTERS",
        "registration_input_sha256": roi["registration_input_sha256"],
        "calibration_sha256": roi["calibration_sha256"],
        "profile_sha256": roi["profile_sha256"],
        "source_frame_sha256": roi["source_frame_sha256"],
        "source_frame_bytes_verified": roi["source_frame_bytes_verified"],
        "profile": profile,
        "rectified_pixels_per_mm": RECTIFIED_PIXELS_PER_MM,
        "thresholds": {
            "row_search_radius_mm": ROW_SEARCH_RADIUS_MM,
            "gap_phase_search_radius_mm": GAP_PHASE_SEARCH_RADIUS_MM,
            "minimum_row_feature_contrast": MIN_ROW_FEATURE_CONTRAST,
            "minimum_gap_phase_peak_ratio": MIN_GAP_PHASE_PEAK_RATIO,
            "maximum_feature_offset_mm": MAX_FEATURE_OFFSET_MM,
        },
        "standard_row_observations": rows,
        "standard_row_observation_count": len(rows),
        "image_feedback_observability_ready": rows_ready and profile_ready,
        "independent_key_center_observations_present": False,
        "individual_key_localization_ready": False,
        "board_space_motion_targets_emitted": False,
        "contact_authorized": False,
        "motion_authorized": False,
        "blockers": blockers,
        "limitations": [
            "The detected contrast bands and repeated gap phases establish image observability, not physical key centers.",
            "The assessment uses one hash-bound frame and does not establish temporal repeatability across a fresh capture.",
            "No board-space correction is derived from these row features.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assess standard keyboard row features in one retained frame")
    parser.add_argument("registration", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("targets", type=Path)
    parser.add_argument("source_frame", type=Path)
    parser.add_argument("--profile", choices=(SUPPORTED_PROFILE, STYLUS_PROFILE),
                        default=SUPPORTED_PROFILE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = estimate_files(
        args.registration, args.calibration, args.targets, args.source_frame,
        profile=args.profile)
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_bytes(encoded.encode("utf-8"))
    else:
        print(encoded, end="")
    return 0 if result["image_feedback_observability_ready"] else 2


__all__ = [
    "FixedCameraKeyRowObservabilityError", "assess_rectified_luminance",
    "estimate_files", "rectify_luminance",
]


if __name__ == "__main__":
    raise SystemExit(main())
