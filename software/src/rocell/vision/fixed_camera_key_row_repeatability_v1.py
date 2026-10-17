"""Compare keyboard-row image features across a distinct fixed-camera frame."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from rocell.vision.fixed_camera_key_feedback_roi_v1 import (
    estimate_files as estimate_roi_files,
)
from rocell.vision.fixed_camera_key_row_observability_v1 import (
    FixedCameraKeyRowObservabilityError,
    assess_rectified_luminance,
    estimate_files as estimate_observability_files,
    rectify_luminance,
)


MAX_JSON_BYTES = 256 * 1024
MAX_FRAME_BYTES = 20 * 1024 * 1024
MAX_TEMPORAL_ROW_FEATURE_DELTA_MM = 2.0


class FixedCameraKeyRowRepeatabilityError(ValueError):
    """The distinct-frame row comparison is invalid or incomplete."""


def _read_bytes(path: Path, maximum: int, label: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise FixedCameraKeyRowRepeatabilityError(f"{label} must be a regular file")
    if path.stat().st_size > maximum:
        raise FixedCameraKeyRowRepeatabilityError(f"{label} exceeds its byte limit")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FixedCameraKeyRowRepeatabilityError(
            f"could not read {label}: {exc}") from exc


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_bytes(path, MAX_JSON_BYTES, label)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyRowRepeatabilityError(
            f"could not decode {label}: {exc}") from exc
    if type(value) is not dict:
        raise FixedCameraKeyRowRepeatabilityError(f"{label} must be an object")
    return value, payload


def compare_rows(
    reference_rows: Sequence[Mapping[str, Any]],
    repeat_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compare like-for-like row features under a bounded study threshold."""
    if len(reference_rows) != 4 or len(repeat_rows) != 4:
        raise FixedCameraKeyRowRepeatabilityError("exactly four rows are required")
    comparisons = []
    for reference, repeat in zip(reference_rows, repeat_rows):
        identity = (reference.get("row_index"), reference.get("first_key"),
                    reference.get("last_key"), reference.get("key_count"))
        if identity != (repeat.get("row_index"), repeat.get("first_key"),
                        repeat.get("last_key"), repeat.get("key_count")):
            raise FixedCameraKeyRowRepeatabilityError("row identities differ")
        contrast_delta = (float(repeat["contrast_band_offset_mm"])
                          - float(reference["contrast_band_offset_mm"]))
        phase_delta = (float(repeat["repeated_gap_phase_offset_mm"])
                       - float(reference["repeated_gap_phase_offset_mm"]))
        passed = (bool(reference.get("observable"))
                  and bool(repeat.get("observable"))
                  and abs(contrast_delta) <= MAX_TEMPORAL_ROW_FEATURE_DELTA_MM
                  and abs(phase_delta) <= MAX_TEMPORAL_ROW_FEATURE_DELTA_MM)
        comparisons.append({
            "row_index": identity[0],
            "first_key": identity[1],
            "last_key": identity[2],
            "reference_contrast_band_offset_mm": reference[
                "contrast_band_offset_mm"],
            "repeat_contrast_band_offset_mm": repeat[
                "contrast_band_offset_mm"],
            "contrast_band_temporal_delta_mm": round(contrast_delta, 3),
            "reference_gap_phase_offset_mm": reference[
                "repeated_gap_phase_offset_mm"],
            "repeat_gap_phase_offset_mm": repeat[
                "repeated_gap_phase_offset_mm"],
            "gap_phase_temporal_delta_mm": round(phase_delta, 3),
            "repeat_observable": bool(repeat.get("observable")),
            "repeatability_passed": passed,
        })
    return comparisons


def estimate_files(
    reference_result_path: Path, registration_path: Path,
    calibration_path: Path, profile_path: Path, reference_frame_path: Path,
    repeat_frame_path: Path, repeat_capture_path: Path,
) -> dict[str, Any]:
    reference, reference_bytes = _load_json(
        reference_result_path, "reference result")
    capture, capture_bytes = _load_json(repeat_capture_path, "capture record")
    try:
        reproduced = estimate_observability_files(
            registration_path, calibration_path, profile_path,
            reference_frame_path)
    except FixedCameraKeyRowObservabilityError as exc:
        raise FixedCameraKeyRowRepeatabilityError(str(exc)) from exc
    if reference != reproduced:
        raise FixedCameraKeyRowRepeatabilityError(
            "reference observability result does not reproduce")

    repeat_bytes = _read_bytes(repeat_frame_path, MAX_FRAME_BYTES, "repeat frame")
    repeat_sha = hashlib.sha256(repeat_bytes).hexdigest()
    frame_record = capture.get("frame")
    readback = capture.get("readback")
    if (capture.get("schema") != "tactevra.local.fixed_camera_repeat_capture.v1"
            or capture.get("backend") != "DSHOW"
            or capture.get("motion_or_contact_authority") is not False
            or not isinstance(frame_record, Mapping)
            or not isinstance(readback, Mapping)
            or frame_record.get("sha256") != repeat_sha
            or frame_record.get("bytes") != len(repeat_bytes)
            or frame_record.get("width_px") != 1920
            or frame_record.get("height_px") != 1080
            or readback.get("width_px") != 1920
            or readback.get("height_px") != 1080
            or readback.get("pixel_format") != "YUY2"
            or abs(float(readback.get("fps", 0)) - 60.0) > 0.01):
        raise FixedCameraKeyRowRepeatabilityError(
            "repeat capture record does not bind the accepted camera mode")

    roi = estimate_roi_files(
        registration_path, calibration_path, profile_path,
        source_frame_path=reference_frame_path)
    profile, _ = _load_json(profile_path, "target profile")
    keyboard = profile.get("keyboard")
    if not isinstance(keyboard, Mapping):
        raise FixedCameraKeyRowRepeatabilityError("keyboard profile is missing")
    dimensions = keyboard.get("device_size_mm")
    if not isinstance(dimensions, list) or len(dimensions) != 3:
        raise FixedCameraKeyRowRepeatabilityError("keyboard dimensions are missing")
    try:
        with Image.open(repeat_frame_path) as image:
            image.load()
            if image.size != (1920, 1080):
                raise FixedCameraKeyRowRepeatabilityError(
                    "repeat frame dimensions are not 1920x1080")
            luminance = rectify_luminance(
                image, roi["local_keyboard_to_pixel_homography"],
                float(dimensions[0]), float(dimensions[1]))
    except (OSError, ValueError) as exc:
        raise FixedCameraKeyRowRepeatabilityError(
            f"could not decode repeat frame: {exc}") from exc
    repeat_rows = assess_rectified_luminance(luminance, keyboard)
    comparisons = compare_rows(
        reference["standard_row_observations"], repeat_rows)
    ready = all(row["repeatability_passed"] for row in comparisons)
    blockers = ["INDIVIDUAL_KEY_CENTERS_NOT_OBSERVED"]
    if not ready:
        blockers.append("ROW_FEATURE_TEMPORAL_REPEATABILITY_FAILED")
    return {
        "schema": "rocell.fixed_camera_key_row_repeatability.v1",
        "status": "DISTINCT_FRAME_ROW_REPEATABILITY_ONLY_NOT_KEY_CENTERS",
        "reference_result_sha256": hashlib.sha256(reference_bytes).hexdigest(),
        "reference_frame_sha256": reference["source_frame_sha256"],
        "repeat_capture_record_sha256": hashlib.sha256(capture_bytes).hexdigest(),
        "repeat_frame_sha256": repeat_sha,
        "repeat_frame_bytes_verified": True,
        "camera_mode_verified": True,
        "maximum_temporal_row_feature_delta_mm": (
            MAX_TEMPORAL_ROW_FEATURE_DELTA_MM),
        "row_comparisons": comparisons,
        "row_feature_temporal_repeatability_ready": ready,
        "independent_key_center_observations_present": False,
        "individual_key_localization_ready": False,
        "board_space_motion_targets_emitted": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "blockers": blockers,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference_result", "registration", "calibration", "targets",
                 "reference_frame", "repeat_frame", "repeat_capture"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = estimate_files(
        args.reference_result, args.registration, args.calibration, args.targets,
        args.reference_frame, args.repeat_frame, args.repeat_capture)
    encoded = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    if args.output:
        args.output.write_bytes(encoded)
    else:
        print(encoded.decode(), end="")
    return 0 if result["row_feature_temporal_repeatability_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
