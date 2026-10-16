#!/usr/bin/env python3
"""Measure the fixed B0477 image-to-board mapping from installed AprilTags.

This is a read-only analysis tool. It opens saved images, detects the six
installed tag36h11 markers, fits the board plane from the four perimeter tags,
and reserves the two interior tags as independent checks. It does not open a
camera or robot transport and it does not grant motion authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FRAMES = (
    ROOT
    / "software/runs/wizard-exports/live-camera-observation-forward-cal-1-repeat-20261015-02"
)
DEFAULT_OBSERVATIONS = (
    ROOT / "software/ai/eval/physical_installed_apriltag_xy_working_v1.json"
)
DEFAULT_OUTPUT = ROOT / "software/ai/eval/b0477_fixed_board_registration_20261016.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tag_board_corners(center_xy_mm: list[float], edge_mm: float) -> "Any":
    """Return board corners matching OpenCV's TL, TR, BR, BL marker order."""
    import numpy as np

    x, y = center_xy_mm
    half = edge_mm / 2.0
    # Installed marker tops point toward board +Y (rear/toward the arm).
    return np.asarray(
        [
            [x - half, y + half],
            [x + half, y + half],
            [x + half, y - half],
            [x - half, y - half],
        ],
        dtype=np.float64,
    )


def transform_points(points: "Any", matrix: "Any") -> "Any":
    import cv2
    import numpy as np

    values = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(values, matrix).reshape(-1, 2)


def marker_projective_center(corners: "Any") -> "Any":
    """Return the projective center of an ordered marker quadrilateral."""
    import cv2
    import numpy as np

    unit_square = np.asarray(
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32
    )
    image_corners = np.asarray(corners, dtype=np.float32)
    square_to_image = cv2.getPerspectiveTransform(unit_square, image_corners)
    return transform_points([[0.5, 0.5]], square_to_image)[0]


def _detector_profiles() -> list[tuple[str, "Any"]]:
    import cv2

    default = cv2.aruco.DetectorParameters()
    refined = cv2.aruco.DetectorParameters()
    refined.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
    refined.adaptiveThreshWinSizeMin = 3
    refined.adaptiveThreshWinSizeMax = 53
    refined.adaptiveThreshWinSizeStep = 4
    return [("opencv_default", default), ("apriltag_refined", refined)]


def detect_tags(image_path: Path) -> tuple[dict[int, "Any"], dict[int, str], list[int]]:
    """Merge two detector profiles, preferring refined corners when present."""
    import cv2

    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detections: dict[int, Any] = {}
    sources: dict[int, str] = {}
    for profile_name, parameters in _detector_profiles():
        corners, ids, _rejected = cv2.aruco.ArucoDetector(
            dictionary, parameters
        ).detectMarkers(image)
        if ids is None:
            continue
        for corners_for_tag, tag_id in zip(corners, ids.flatten(), strict=True):
            numeric_id = int(tag_id)
            # The refined profile runs last and replaces default corners.
            detections[numeric_id] = corners_for_tag.reshape(4, 2).astype("float64")
            sources[numeric_id] = profile_name
    return detections, sources, [int(image.shape[1]), int(image.shape[0])]


def _round_matrix(matrix: "Any", digits: int = 12) -> list[list[float]]:
    return [[round(float(value), digits) for value in row] for row in matrix]


def _round_vector(vector: "Any", digits: int = 4) -> list[float]:
    return [round(float(value), digits) for value in vector]


def build_stationary_observation_report(
    frames_directory: Path,
    registration_path: Path,
    *,
    maximum_reference_center_shift_mm: float = 2.0,
    minimum_samples_per_tag: int = 3,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Compare a fresh finite capture with one retained fixed-epoch mapping.

    This deliberately evaluates camera/board scene stability only. Missing arm
    telemetry can therefore never be converted into stationary-arm agreement.
    """
    import numpy as np

    if maximum_reference_center_shift_mm <= 0:
        raise ValueError("maximum_reference_center_shift_mm must be positive")
    if minimum_samples_per_tag <= 0:
        raise ValueError("minimum_samples_per_tag must be positive")

    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    if registration.get("schema") != "rocell.fixed_apriltag_board_registration.v1":
        raise ValueError("Unsupported reference registration schema")
    reference = {
        int(item["id"]): np.asarray(item["mapped_mean_xy_mm"], dtype=np.float64)
        for item in registration["validation"]["mapped_center_repeatability"].values()
    }
    if set(reference) != set(range(6)):
        raise ValueError("Reference registration must contain tag IDs 0-5")

    receipt_path = frames_directory / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_frames = {
        frame["file_name"]: frame
        for cycle in receipt["reopen_cycles"]
        for frame in cycle["frames"]
    }
    image_to_board = np.asarray(
        registration["mapping"]["image_to_board_homography"], dtype=np.float64
    )
    observations: dict[int, list[Any]] = {tag_id: [] for tag_id in reference}
    frame_results = []
    all_hashes = []
    frame_paths = sorted(frames_directory.glob("*.jpg"))
    receipt_inventory_matches = {path.name for path in frame_paths} == set(
        receipt_frames
    )
    for frame_path in frame_paths:
        expected = receipt_frames.get(frame_path.name)
        actual_hash = sha256_file(frame_path)
        if expected is None or expected.get("sha256") != actual_hash:
            raise ValueError(
                f"Frame is absent from receipt or hash changed: {frame_path.name}"
            )
        detections, _sources, image_size = detect_tags(frame_path)
        detected_ids = sorted(tag_id for tag_id in detections if tag_id in reference)
        for tag_id in detected_ids:
            center = marker_projective_center(detections[tag_id])
            observations[tag_id].append(transform_points([center], image_to_board)[0])
        all_hashes.append(actual_hash)
        frame_results.append(
            {
                "file_name": frame_path.name,
                "sha256": actual_hash,
                "image_size_px": image_size,
                "detected_ids": detected_ids,
                "all_required_tags_visible": detected_ids == list(range(6)),
            }
        )
    if not frame_results:
        raise ValueError(f"No JPG frames found in {frames_directory}")

    by_tag = {}
    all_shifts = []
    for tag_id, values in observations.items():
        if values:
            array = np.asarray(values)
            deltas = array - reference[tag_id]
            radial = np.linalg.norm(deltas, axis=1)
            all_shifts.extend(float(value) for value in radial)
            by_tag[str(tag_id)] = {
                "sample_count": len(values),
                "reference_mapped_center_xy_mm": _round_vector(reference[tag_id], 4),
                "observed_mean_xy_mm": _round_vector(np.mean(array, axis=0), 4),
                "observed_mean_delta_xy_mm": _round_vector(
                    np.mean(array, axis=0) - reference[tag_id], 4
                ),
                "mean_radial_shift_mm": round(float(np.mean(radial)), 4),
                "maximum_radial_shift_mm": round(float(np.max(radial)), 4),
            }
        else:
            by_tag[str(tag_id)] = {"sample_count": 0}

    identity_matches = (
        receipt.get("persistent_device_identity")
        == registration["inputs"]["camera_identity"]
    )
    settings_hashes = {
        cycle["negotiated_mode"]["settings_sha256"]
        for cycle in receipt["reopen_cycles"]
    }
    settings_match = settings_hashes == {registration["inputs"]["settings_sha256"]}
    requested_mode_matches = (
        receipt.get("requested_mode") == registration["inputs"]["requested_mode"]
    )
    hashes_unique = len(all_hashes) == len(set(all_hashes))
    complete_frame_count = sum(
        frame["all_required_tags_visible"] for frame in frame_results
    )
    samples_sufficient = all(
        len(values) >= minimum_samples_per_tag for values in observations.values()
    )
    maximum_shift = max(all_shifts) if all_shifts else None
    camera_scene_agrees = all(
        (
            identity_matches,
            settings_match,
            requested_mode_matches,
            receipt_inventory_matches,
            hashes_unique,
            complete_frame_count > 0,
            samples_sufficient,
            maximum_shift is not None
            and maximum_shift <= maximum_reference_center_shift_mm,
        )
    )

    return {
        "schema": "rocell.fixed_board_stationary_observation.v1",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "status": (
            "CAMERA_SCENE_AGREES_TELEMETRY_REQUIRED"
            if camera_scene_agrees
            else "CAMERA_SCENE_DISAGREES"
        ),
        "inputs": {
            "frames_directory": frames_directory.relative_to(ROOT).as_posix(),
            "receipt_path": receipt_path.relative_to(ROOT).as_posix(),
            "receipt_sha256": sha256_file(receipt_path),
            "registration_path": registration_path.relative_to(ROOT).as_posix(),
            "registration_sha256": sha256_file(registration_path),
        },
        "policy": {
            "required_tag_ids": list(range(6)),
            "minimum_samples_per_tag": minimum_samples_per_tag,
            "maximum_reference_center_shift_mm": maximum_reference_center_shift_mm,
        },
        "assessment": {
            "camera_identity_matches": identity_matches,
            "camera_settings_match": settings_match,
            "requested_mode_matches": requested_mode_matches,
            "receipt_inventory_matches": receipt_inventory_matches,
            "all_frame_hashes_unique": hashes_unique,
            "frame_count": len(frame_results),
            "complete_six_tag_frame_count": complete_frame_count,
            "all_tags_have_minimum_samples": samples_sufficient,
            "maximum_reference_center_shift_mm": (
                round(maximum_shift, 4) if maximum_shift is not None else None
            ),
            "camera_scene_agrees": camera_scene_agrees,
            "arm_telemetry_available": False,
            "stationary_arm_agreement": False,
        },
        "mapped_center_comparison_by_tag": by_tag,
        "frames": frame_results,
        "limitations": [
            "Camera-scene agreement does not establish current arm joint state.",
            "Arm telemetry is required before stationary-arm agreement can pass.",
            "This planar comparison does not establish Z, TCP, route, collision, motion, descent, or contact authority.",
        ],
        "authority": {
            "hardware_writes": 0,
            "robot_transport_opened": False,
            "robot_motion": False,
            "camera_guided_motion": False,
            "physical_authority": False,
        },
    }


def build_report(
    frames_directory: Path,
    observations_path: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    import cv2
    import numpy as np

    observations = json.loads(observations_path.read_text(encoding="utf-8"))
    edge_mm = float(observations["installed_tag_geometry"]["detection_edge_mm"])
    tag_records = {
        int(record["id"]): {
            "name": name,
            "role": record["role"],
            "center": [
                float(value) for value in record["working_detection_center_xy_mm"]
            ],
        }
        for name, record in observations["tags"].items()
    }
    if set(tag_records) != set(range(6)):
        raise ValueError(f"Expected tag IDs 0-5, found {sorted(tag_records)}")
    world_ids = sorted(
        tag_id for tag_id, item in tag_records.items() if item["role"] == "world"
    )
    station_ids = sorted(
        tag_id
        for tag_id, item in tag_records.items()
        if item["role"] == "station_check"
    )
    if world_ids != [0, 1, 2, 3] or station_ids != [4, 5]:
        raise ValueError("Expected world IDs 0-3 and station-check IDs 4-5")

    receipt_path = frames_directory / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_frames = {
        frame["file_name"]: frame
        for cycle in receipt["reopen_cycles"]
        for frame in cycle["frames"]
    }
    frame_paths = sorted(frames_directory.glob("*.jpg"))
    if not frame_paths:
        raise ValueError(f"No JPG frames found in {frames_directory}")

    detected_frames: list[dict[str, Any]] = []
    for frame_path in frame_paths:
        expected = receipt_frames.get(frame_path.name)
        actual_hash = sha256_file(frame_path)
        if expected is None or expected.get("sha256") != actual_hash:
            raise ValueError(
                f"Frame is absent from receipt or hash changed: {frame_path.name}"
            )
        detections, sources, image_size = detect_tags(frame_path)
        detected_frames.append(
            {
                "path": frame_path,
                "sha256": actual_hash,
                "image_size_px": image_size,
                "detections": detections,
                "sources": sources,
            }
        )

    board_points: list[Any] = []
    image_points: list[Any] = []
    eligible_frames = []
    for frame in detected_frames:
        detections = frame["detections"]
        if not set(world_ids).issubset(detections):
            continue
        eligible_frames.append(frame)
        for tag_id in world_ids:
            board_points.extend(
                tag_board_corners(tag_records[tag_id]["center"], edge_mm)
            )
            image_points.extend(detections[tag_id])
    if not eligible_frames:
        raise ValueError("No frame contains all four perimeter world tags")

    board_array = np.asarray(board_points, dtype=np.float64)
    image_array = np.asarray(image_points, dtype=np.float64)
    board_to_image, _mask = cv2.findHomography(board_array, image_array, method=0)
    if board_to_image is None:
        raise ValueError("Could not solve board-to-image homography")
    board_to_image /= board_to_image[2, 2]
    image_to_board = np.linalg.inv(board_to_image)
    image_to_board /= image_to_board[2, 2]

    fitted_image_points = transform_points(board_array, board_to_image)
    fit_errors_px = np.linalg.norm(fitted_image_points - image_array, axis=1)
    station_errors: dict[int, list[float]] = {tag_id: [] for tag_id in station_ids}
    frame_results = []
    mapped_centers_by_id: dict[int, list[Any]] = {tag_id: [] for tag_id in tag_records}
    for frame in detected_frames:
        detections = frame["detections"]
        checks = []
        for tag_id, corners in sorted(detections.items()):
            if tag_id not in tag_records:
                continue
            image_center = marker_projective_center(corners)
            mapped_center = transform_points([image_center], image_to_board)[0]
            mapped_centers_by_id[tag_id].append(mapped_center)
            if tag_id in station_ids:
                expected_center = np.asarray(tag_records[tag_id]["center"])
                delta = mapped_center - expected_center
                error = float(np.linalg.norm(delta))
                station_errors[tag_id].append(error)
                checks.append(
                    {
                        "id": tag_id,
                        "name": tag_records[tag_id]["name"],
                        "mapped_center_xy_mm": _round_vector(mapped_center, 3),
                        "measured_center_xy_mm": _round_vector(expected_center, 3),
                        "delta_xy_mm": _round_vector(delta, 3),
                        "planar_error_mm": round(error, 3),
                    }
                )
        missing_world = sorted(set(world_ids) - set(detections))
        frame_results.append(
            {
                "file_name": frame["path"].name,
                "sha256": frame["sha256"],
                "image_size_px": frame["image_size_px"],
                "detected_ids": sorted(detections),
                "corner_source_by_id": {
                    str(tag_id): frame["sources"][tag_id]
                    for tag_id in sorted(detections)
                },
                "fit_eligible": not missing_world,
                "missing_world_ids": missing_world,
                "station_checks": checks,
            }
        )

    repeatability = {}
    for tag_id, values in mapped_centers_by_id.items():
        array = np.asarray(values)
        repeatability[tag_records[tag_id]["name"]] = {
            "id": tag_id,
            "sample_count": len(values),
            "mapped_mean_xy_mm": _round_vector(np.mean(array, axis=0), 4),
            "mapped_axis_stddev_mm": _round_vector(np.std(array, axis=0), 4),
            "maximum_radial_deviation_from_mean_mm": round(
                float(np.max(np.linalg.norm(array - np.mean(array, axis=0), axis=1))), 4
            ),
        }

    all_station_errors = [
        value for values in station_errors.values() for value in values
    ]
    board_width, board_height = [
        float(value) for value in observations["board"]["size_xy_mm"]
    ]
    board_corners = np.asarray(
        [
            [0.0, 0.0],
            [board_width, 0.0],
            [board_width, board_height],
            [0.0, board_height],
        ]
    )
    board_corners_px = transform_points(board_corners, board_to_image)
    keyboard_probe = np.asarray([[305.0, 230.0], [306.0, 230.0], [305.0, 231.0]])
    keyboard_probe_px = transform_points(keyboard_probe, board_to_image)
    scale_x = float(np.linalg.norm(keyboard_probe_px[1] - keyboard_probe_px[0]))
    scale_y = float(np.linalg.norm(keyboard_probe_px[2] - keyboard_probe_px[0]))

    return {
        "schema": "rocell.fixed_apriltag_board_registration.v1",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "status": "MEASURED_FIXED_EPOCH_PLANAR_MAPPING",
        "method": "consensus_homography_from_installed_tag36h11_ids_0_to_3_corners_with_ids_4_and_5_held_out",
        "inputs": {
            "frames_directory": frames_directory.relative_to(ROOT).as_posix(),
            "receipt_path": receipt_path.relative_to(ROOT).as_posix(),
            "receipt_sha256": sha256_file(receipt_path),
            "xy_observations_path": observations_path.relative_to(ROOT).as_posix(),
            "xy_observations_sha256": sha256_file(observations_path),
            "camera_identity": receipt["persistent_device_identity"],
            "settings_sha256": receipt["reopen_cycles"][0]["negotiated_mode"][
                "settings_sha256"
            ],
            "requested_mode": receipt["requested_mode"],
            "board_size_xy_mm": [board_width, board_height],
            "tag_detection_edge_mm": edge_mm,
            "tag_top_direction": "+Y/rear/toward arm",
            "tag_centers_xy_mm": {
                item["name"]: item["center"] for item in tag_records.values()
            },
        },
        "mapping": {
            "board_to_image_homography": _round_matrix(board_to_image),
            "image_to_board_homography": _round_matrix(image_to_board),
            "projected_board_corners_px": [
                _round_vector(point, 3) for point in board_corners_px
            ],
            "local_scale_at_board_center_px_per_mm": {
                "x": round(scale_x, 6),
                "y": round(scale_y, 6),
            },
        },
        "validation": {
            "source_frame_count": len(detected_frames),
            "fit_eligible_frame_count": len(eligible_frames),
            "world_corner_observation_count": len(board_array),
            "world_corner_fit_rmse_px": round(
                float(np.sqrt(np.mean(np.square(fit_errors_px)))), 4
            ),
            "world_corner_fit_max_px": round(float(np.max(fit_errors_px)), 4),
            "held_out_station_center_check_count": len(all_station_errors),
            "held_out_station_center_mean_error_mm": round(
                float(np.mean(all_station_errors)), 4
            ),
            "held_out_station_center_max_error_mm": round(
                float(np.max(all_station_errors)), 4
            ),
            "held_out_by_tag": {
                tag_records[tag_id]["name"]: {
                    "id": tag_id,
                    "check_count": len(values),
                    "mean_error_mm": round(float(np.mean(values)), 4),
                    "max_error_mm": round(float(np.max(values)), 4),
                }
                for tag_id, values in station_errors.items()
            },
            "mapped_center_repeatability": repeatability,
        },
        "frames": frame_results,
        "use": {
            "permitted": [
                "map saved B0477 image pixels to the measured board XY plane",
                "project measured board locations into the retained camera image",
                "prepare keyboard-region overlays and read-only targeting checks",
            ],
            "not_established": [
                "camera intrinsics or lens-distortion coefficients",
                "off-plane Z reconstruction",
                "board-to-robot transform",
                "tool-center-point offset or attachment trajectory",
                "contact or camera-guided motion authority",
            ],
        },
        "epoch_binding": {
            "epoch_id": "keyboard-bare-jaw-camera-intake-20261015",
            "camera_or_board_movement_invalidates_mapping": True,
            "tool_change_invalidates_trajectory_not_planar_mapping": True,
        },
        "authority": {
            "hardware_writes": 0,
            "robot_transport_opened": False,
            "robot_motion": False,
            "camera_guided_motion": False,
            "physical_authority": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Measure a fixed image-to-board mapping from installed AprilTags."
    )
    result.add_argument("--frames-directory", type=Path, default=DEFAULT_FRAMES)
    result.add_argument("--xy-observations", type=Path, default=DEFAULT_OBSERVATIONS)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument(
        "--reference-registration",
        type=Path,
        help="Assess fresh frames against an existing registration without refitting it",
    )
    result.add_argument(
        "--maximum-reference-center-shift-mm", type=float, default=2.0
    )
    result.add_argument("--minimum-samples-per-tag", type=int, default=3)
    result.add_argument(
        "--created-at", help="Optional stable ISO-8601 evidence timestamp"
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if args.reference_registration:
        report = build_stationary_observation_report(
            args.frames_directory.resolve(strict=True),
            args.reference_registration.resolve(strict=True),
            maximum_reference_center_shift_mm=args.maximum_reference_center_shift_mm,
            minimum_samples_per_tag=args.minimum_samples_per_tag,
            created_at=args.created_at,
        )
    else:
        report = build_report(
            args.frames_directory.resolve(strict=True),
            args.xy_observations.resolve(strict=True),
            created_at=args.created_at,
        )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report.get("validation", report.get("assessment")), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
