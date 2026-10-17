"""Bind a fresh fixed-camera frame to the retained keyboard target overlay.

The module reads saved camera evidence only.  It fits the board plane from the
four perimeter AprilTags, projects the 46 reviewed keyboard targets into one
current frame, and emits a review artifact.  It never opens a camera or robot
transport and grants no motion authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


class CurrentPlanarObservationError(ValueError):
    """Current camera evidence cannot be bound to the retained overlay."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise CurrentPlanarObservationError(f"{path} must contain an object")
    return value


def _transform(points: Any, matrix: Any) -> Any:
    import cv2
    import numpy as np

    values = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(values, matrix).reshape(-1, 2)


def _tag_board_corners(center: list[float], edge_mm: float) -> Any:
    import numpy as np

    x, y = center
    half = edge_mm / 2.0
    return np.asarray(
        [
            [x - half, y + half],
            [x + half, y + half],
            [x + half, y - half],
            [x - half, y - half],
        ],
        dtype=np.float64,
    )


def _detect(path: Path) -> tuple[dict[int, Any], list[int]]:
    import cv2

    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise CurrentPlanarObservationError(f"cannot decode {path}")
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    profiles = [cv2.aruco.DetectorParameters()]
    refined = cv2.aruco.DetectorParameters()
    refined.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
    refined.aprilTagQuadDecimate = 1.0
    refined.aprilTagMinClusterPixels = 3
    refined.minMarkerPerimeterRate = 0.005
    refined.maxMarkerPerimeterRate = 6.0
    refined.errorCorrectionRate = 0.8
    profiles.append(refined)
    detections: dict[int, Any] = {}
    for parameters in profiles:
        corners, ids, _rejected = cv2.aruco.ArucoDetector(
            dictionary, parameters
        ).detectMarkers(image)
        if ids is None:
            continue
        for item, tag_id in zip(corners, ids.flatten(), strict=True):
            detections[int(tag_id)] = item.reshape(4, 2).astype("float64")
    return detections, [int(image.shape[1]), int(image.shape[0])]


def _marker_center(corners: Any) -> Any:
    import cv2
    import numpy as np

    unit = np.asarray(
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32
    )
    square_to_image = cv2.getPerspectiveTransform(
        unit, np.asarray(corners, dtype=np.float32)
    )
    return _transform([[0.5, 0.5]], square_to_image)[0]


def _rounded(point: Any, digits: int = 3) -> list[float]:
    return [round(float(value), digits) for value in point]


def build_current_planar_observation(
    workspace: Path,
    frames_directory: Path,
    stationary_observation_path: Path,
    registration_path: Path,
    overlay_path: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Project retained target geometry into the best current saved frame."""

    import cv2
    import numpy as np

    root = workspace.resolve()
    frames = frames_directory.resolve(strict=True)
    stationary_path = stationary_observation_path.resolve(strict=True)
    registration_path = registration_path.resolve(strict=True)
    overlay_path = overlay_path.resolve(strict=True)
    stationary = _read(stationary_path)
    registration = _read(registration_path)
    overlay = _read(overlay_path)

    if stationary.get("schema") != "rocell.fixed_board_stationary_observation.v1":
        raise CurrentPlanarObservationError("unsupported stationary observation")
    assessment = stationary.get("assessment")
    if not isinstance(assessment, Mapping) or not assessment.get("camera_scene_agrees"):
        raise CurrentPlanarObservationError("current camera scene does not agree")
    inputs = stationary.get("inputs")
    if not isinstance(inputs, Mapping):
        raise CurrentPlanarObservationError("stationary observation inputs are missing")
    if inputs.get("registration_sha256") != _sha256(registration_path):
        raise CurrentPlanarObservationError("stationary registration binding is stale")
    if overlay.get("schema") != "rocell.fixed_camera_keyboard_overlay.v1":
        raise CurrentPlanarObservationError("unsupported keyboard overlay")
    overlay_inputs = overlay.get("inputs")
    if not isinstance(overlay_inputs, Mapping):
        raise CurrentPlanarObservationError("overlay inputs are missing")
    if overlay_inputs.get("board_registration_sha256") != _sha256(registration_path):
        raise CurrentPlanarObservationError("overlay registration binding is stale")

    receipt_path = frames / "receipt.json"
    if inputs.get("receipt_sha256") != _sha256(receipt_path):
        raise CurrentPlanarObservationError("capture receipt binding is stale")
    receipt = _read(receipt_path)
    receipt_frames = {
        row["file_name"]: row
        for cycle in receipt.get("reopen_cycles", [])
        for row in cycle.get("frames", [])
    }
    candidates: list[tuple[int, float, str, Path, dict[int, Any], list[int]]] = []
    for frame_name, record in sorted(receipt_frames.items()):
        path = frames / frame_name
        if not path.is_file() or record.get("sha256") != _sha256(path):
            raise CurrentPlanarObservationError(f"missing or changed frame {frame_name}")
        detections, image_size = _detect(path)
        world_count = len(set(detections).intersection(range(4)))
        scene = record.get("scene_assessment")
        sharpness = (
            float(scene.get("laplacian_variance", 0.0))
            if isinstance(scene, Mapping)
            else 0.0
        )
        candidates.append(
            (world_count, sharpness, path.name, path, detections, image_size)
        )
    eligible = [row for row in candidates if row[0] == 4]
    if not eligible:
        raise CurrentPlanarObservationError("no frame contains all four world tags")
    selected = max(eligible, key=lambda row: (len(row[4]), row[1], row[2]))
    _count, _sharpness, _name, frame_path, detections, image_size = selected

    registration_inputs = registration.get("inputs")
    if not isinstance(registration_inputs, Mapping):
        raise CurrentPlanarObservationError("registration inputs are missing")
    centers = registration_inputs.get("tag_centers_xy_mm")
    if not isinstance(centers, Mapping):
        raise CurrentPlanarObservationError("tag centers are missing")
    edge_mm = float(registration_inputs.get("tag_detection_edge_mm"))
    board_points = []
    image_points = []
    for tag_id in range(4):
        board_points.extend(_tag_board_corners(list(centers[f"T{tag_id}"]), edge_mm))
        image_points.extend(detections[tag_id])
    board_array = np.asarray(board_points, dtype=np.float64)
    image_array = np.asarray(image_points, dtype=np.float64)
    board_to_image, _mask = cv2.findHomography(board_array, image_array, method=0)
    if board_to_image is None:
        raise CurrentPlanarObservationError("current board homography fit failed")
    board_to_image /= board_to_image[2, 2]
    residuals = np.linalg.norm(
        _transform(board_array, board_to_image) - image_array, axis=1
    )

    board_view = overlay.get("board_plane_interpretation")
    geometry = overlay.get("keyboard_geometry")
    if not isinstance(board_view, Mapping) or not isinstance(geometry, Mapping):
        raise CurrentPlanarObservationError("overlay geometry is missing")
    translation = np.asarray(
        board_view["dimension_constrained_front_left_xy_mm"], dtype=np.float64
    )
    yaw = math.radians(float(board_view["dimension_constrained_yaw_deg"]))
    rotation = np.asarray(
        [[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]],
        dtype=np.float64,
    )
    targets = geometry.get("projected_targets")
    if not isinstance(targets, Mapping) or len(targets) != 46:
        raise CurrentPlanarObservationError("overlay must contain 46 targets")
    projected: dict[str, Any] = {}
    for target_id, value in targets.items():
        if not isinstance(value, Mapping):
            raise CurrentPlanarObservationError(f"invalid target {target_id}")
        local = np.asarray(
            value["image_fitted_center_keyboard_xy_mm"], dtype=np.float64
        )
        half = np.asarray(value["nominal_half_extent_mm"], dtype=np.float64)
        local_corners = np.asarray(
            [
                local + [-half[0], -half[1]],
                local + [half[0], -half[1]],
                local + [half[0], half[1]],
                local + [-half[0], half[1]],
            ]
        )
        board_center = translation + rotation @ local
        board_corners = translation + local_corners @ rotation.T
        projected[target_id] = {
            "board_center_xy_mm": _rounded(board_center),
            "current_center_px": _rounded(
                _transform([board_center], board_to_image)[0]
            ),
            "current_region_corners_px": [
                _rounded(point) for point in _transform(board_corners, board_to_image)
            ],
        }

    held_out = {}
    for tag_id, key in ((4, "K0"), (5, "P0")):
        if tag_id not in detections:
            held_out[str(tag_id)] = {"detected": False}
            continue
        center_px = _marker_center(detections[tag_id])
        expected_px = _transform([centers[key]], board_to_image)[0]
        held_out[str(tag_id)] = {
            "detected": True,
            "current_center_px": _rounded(center_px),
            "expected_center_px": _rounded(expected_px),
            "error_px": round(float(np.linalg.norm(center_px - expected_px)), 3),
        }

    report: dict[str, Any] = {
        "schema": "rocell.current_planar_keyboard_observation.v1",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "status": "CURRENT_PLANAR_KEYBOARD_OBSERVATION_READ_ONLY",
        "workcell_epoch_id": overlay.get("workcell_epoch_id"),
        "inputs": {
            "frames_directory": frames.relative_to(root).as_posix(),
            "receipt_path": receipt_path.relative_to(root).as_posix(),
            "receipt_sha256": _sha256(receipt_path),
            "stationary_observation_path": stationary_path.relative_to(root).as_posix(),
            "stationary_observation_sha256": _sha256(stationary_path),
            "registration_path": registration_path.relative_to(root).as_posix(),
            "registration_sha256": _sha256(registration_path),
            "overlay_path": overlay_path.relative_to(root).as_posix(),
            "overlay_sha256": _sha256(overlay_path),
            "selected_frame_path": frame_path.relative_to(root).as_posix(),
            "selected_frame_sha256": _sha256(frame_path),
        },
        "current_frame": {
            "image_size_px": image_size,
            "detected_tag_ids": sorted(detections),
            "board_to_image_homography": [
                [round(float(value), 12) for value in row] for row in board_to_image
            ],
            "world_corner_fit_rmse_px": round(
                float(np.sqrt(np.mean(np.square(residuals)))), 4
            ),
            "world_corner_fit_max_px": round(float(np.max(residuals)), 4),
            "held_out_station_checks": held_out,
        },
        "targets": projected,
        "target_count": len(projected),
        "scene_binding": {
            "scope": "SELECTED_SAVED_FRAME_ONLY",
            "camera_scene_agrees_with_retained_epoch": True,
            "maximum_reference_center_shift_mm": assessment.get(
                "maximum_reference_center_shift_mm"
            ),
            "invalidated_by": [
                "camera movement",
                "board movement",
                "keyboard movement",
                "image-size or camera-settings change",
            ],
        },
        "next_required_gate": "CALIBRATED_BARE_JAW_ROUTE_SCREENING_WITHOUT_DISPATCH",
        "authority": {
            "camera_opened": False,
            "robot_transport_opened": False,
            "robot_motion": False,
            "camera_guided_motion": False,
            "physical_authority": False,
            "descent": False,
            "contact": False,
        },
    }
    return {
        **report,
        "observation_sha256": hashlib.sha256(
            json.dumps(
                report, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest(),
    }


def render_current_overlay(
    report: Mapping[str, Any], output_path: Path, *, workspace: Path
) -> None:
    """Render the target polygons over the selected saved frame."""

    import cv2
    import numpy as np

    root = workspace.resolve()
    frame_path = root / report["inputs"]["selected_frame_path"]
    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if image is None:
        raise CurrentPlanarObservationError("selected frame cannot be rendered")
    for target_id, value in report["targets"].items():
        polygon = np.rint(value["current_region_corners_px"]).astype(np.int32)
        center = tuple(np.rint(value["current_center_px"]).astype(int))
        cv2.polylines(image, [polygon], True, (0, 220, 0), 1, cv2.LINE_AA)
        cv2.circle(image, center, 3, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.putText(
            image,
            str(target_id),
            (center[0] + 3, center[1] - 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise CurrentPlanarObservationError("overlay image could not be written")
