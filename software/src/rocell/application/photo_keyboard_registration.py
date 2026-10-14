"""Reconstruct a provisional keyboard board pose from an annotated photo.

This is offline planar photogrammetry, not a robot motion or contact authority.
The board marks lie on paper; the keyboard housing lies above that plane, so a
dimension-constrained fit is preferable to treating raw projected corners as
exact. The resulting study margin is not a calibrated physical error bound.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from rocell.vision.camera import CameraCaptureError, jpeg_dimensions


MAX_PHOTO_BYTES = 25 * 1024 * 1024


def _xy(value, label: str) -> tuple[float, float]:
    if (not isinstance(value, list) or len(value) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError(f"{label} must be a finite XY pair")
    return float(value[0]), float(value[1])


def estimate(annotation: dict, profile: dict, *, profile_sha256: str) -> dict:
    import numpy as np

    if (annotation.get("schema") != "rocell.photo_keyboard_registration_input.v1" or
            annotation.get("status") != "MANUALLY_ANNOTATED_PHOTO_ESTIMATE_ONLY" or
            annotation.get("board_frame") != "RC03_B_FRONT_LEFT_X_RIGHT_Y_REAR_MM" or
            annotation.get("keyboard_local_orientation") !=
            "FRONT_LEFT_AT_BOARD_REAR_RIGHT_HALF_TURN"):
        raise ValueError("Unexpected photo registration contract")
    photo = annotation.get("photo")
    if (not isinstance(photo, dict) or
            type(photo.get("width_px")) is not int or
            type(photo.get("height_px")) is not int or
            photo["width_px"] <= 0 or photo["height_px"] <= 0 or
            not isinstance(photo.get("sha256"), str) or
            len(photo["sha256"]) != 64):
        raise ValueError("Photo identity or image size missing")
    width_px, height_px = photo["width_px"], photo["height_px"]
    fiducials = annotation.get("fiducials")
    if not isinstance(fiducials, list) or not 6 <= len(fiducials) <= 32:
        raise ValueError("At least six bounded fiducials required")
    ids = [row.get("id") for row in fiducials]
    if len(set(ids)) != len(ids) or any(not isinstance(id_, str) for id_ in ids):
        raise ValueError("Fiducial identities differ")
    pixels = np.array([_xy(row.get("pixel_xy"), "fiducial pixel")
                       for row in fiducials], dtype=float)
    board = np.array([_xy(row.get("board_xy_mm"), "fiducial board")
                      for row in fiducials], dtype=float)
    if (np.any(pixels < 0) or np.any(pixels[:, 0] >= width_px) or
            np.any(pixels[:, 1] >= height_px) or
            np.ptp(board[:, 0]) < 100 or np.ptp(board[:, 1]) < 80):
        raise ValueError("Fiducials do not span the board region")

    # Normalize both domains before DLT least squares for stable conditioning.
    pixel_center = np.array([width_px / 2, height_px / 2], dtype=float)
    pixel_scale = np.array([width_px, height_px], dtype=float)
    board_center = np.mean(board, axis=0)
    board_scale = np.array([300.0, 150.0])
    uv = (pixels - pixel_center) / pixel_scale
    xy = (board - board_center) / board_scale
    rows = []
    values = []
    for (u, v), (x, y) in zip(uv, xy):
        rows.extend(([u, v, 1, 0, 0, 0, -x*u, -x*v],
                     [0, 0, 0, u, v, 1, -y*u, -y*v]))
        values.extend((x, y))
    solution, _, rank, _ = np.linalg.lstsq(np.array(rows), np.array(values), rcond=None)
    if rank != 8:
        raise ValueError("Photo homography is rank deficient")

    def map_pixels(points):
        points = np.asarray(points, dtype=float)
        normalized = (points - pixel_center) / pixel_scale
        u, v = normalized[:, 0], normalized[:, 1]
        divisor = solution[6]*u + solution[7]*v + 1
        if np.any(np.abs(divisor) < 1e-8):
            raise ValueError("Photo homography has a singular mapped point")
        mapped = np.column_stack(((solution[0]*u+solution[1]*v+solution[2])/divisor,
                                  (solution[3]*u+solution[4]*v+solution[5])/divisor))
        return mapped * board_scale + board_center

    fiducial_residuals = np.linalg.norm(map_pixels(pixels) - board, axis=1)
    if float(np.max(fiducial_residuals)) > 6:
        raise ValueError("Photo fiducials do not support a coherent planar fit")

    corners = annotation.get("keyboard_corners_px")
    order = ("front_left", "front_right", "rear_right", "rear_left")
    if not isinstance(corners, dict) or set(corners) != set(order):
        raise ValueError("Four labeled keyboard corners required")
    corner_pixels = np.array([_xy(corners[name], name) for name in order])
    if (np.any(corner_pixels < 0) or
            np.any(corner_pixels[:, 0] >= width_px) or
            np.any(corner_pixels[:, 1] >= height_px)):
        raise ValueError("Keyboard corner outside source image")
    observed = map_pixels(corner_pixels)
    dimensions = annotation.get("housing_dimensions_mm")
    if (not isinstance(dimensions, list) or len(dimensions) != 3 or
            any(type(v) not in (int, float) or v <= 0 for v in dimensions) or
            list(map(float, dimensions)) != profile.get("device_size_mm")):
        raise ValueError("Known housing dimensions differ from profile")
    width, depth = float(dimensions[0]), float(dimensions[1])
    footprint = np.array([[0, 0], [width, 0], [width, depth], [0, depth]], dtype=float)
    centered_footprint = footprint - footprint.mean(axis=0)
    centered_observed = observed - observed.mean(axis=0)
    left, _, right = np.linalg.svd(centered_footprint.T @ centered_observed)
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    translation = observed.mean(axis=0) - footprint.mean(axis=0) @ rotation
    fitted = footprint @ rotation + translation
    corner_residuals = np.linalg.norm(fitted - observed, axis=1)
    yaw = math.degrees(math.atan2(rotation[0, 1], rotation[0, 0]))
    local_origin = np.array([width, depth]) @ rotation + translation
    local_yaw = (yaw + 180) % 360
    local_rotation = -rotation

    keys = {}
    for row in profile["rows"]:
        first = np.array(_xy(row["first_center_xy_mm"], "row first center"))
        step = np.array(_xy(row["step_xy_mm"], "row step"))
        for index, name in enumerate(row["key_ids"]):
            keys[name] = ((first + index*step) @ local_rotation + local_origin).tolist()
    for name, item in profile["explicit_targets"].items():
        local = np.array(_xy(item["center_xy_mm"], "explicit key center"))
        keys[name] = (local @ local_rotation + local_origin).tolist()
    if len(keys) != len(set(keys)) or len(keys) < 40:
        raise ValueError("Incomplete keyboard key layout")
    study_margin = annotation.get("study_xy_margin_mm")
    if type(study_margin) not in (int, float) or not 10 <= study_margin <= 50:
        raise ValueError("Explicit photo-estimate study margin required")
    if max(corner_residuals) > study_margin:
        raise ValueError("Housing fit exceeds declared study margin")
    return dict(schema="rocell.photo_keyboard_registration_estimate.v1",
                status="PHOTO_ESTIMATE_OFFLINE_NOT_MOTION_AUTHORITY",
                photo_sha256=photo["sha256"], profile_sha256=profile_sha256,
                source_photo_bytes_verified=False,
                board_frame=annotation["board_frame"],
                fiducial_count=len(fiducials),
                fiducial_rms_residual_mm=round(float(np.sqrt(np.mean(fiducial_residuals**2))), 3),
                fiducial_max_residual_mm=round(float(np.max(fiducial_residuals)), 3),
                observed_corners_board_xy_mm={name:[round(float(v), 2) for v in point]
                                              for name, point in zip(order, observed)},
                fitted_front_left_board_xy_mm=[round(float(v), 2) for v in translation],
                fitted_footprint_yaw_deg=round(yaw, 3),
                fitted_local_front_left_board_xy_mm=[round(float(v), 2) for v in local_origin],
                fitted_local_yaw_deg=round(local_yaw, 3),
                housing_corner_rms_residual_mm=round(float(np.sqrt(np.mean(corner_residuals**2))), 3),
                housing_corner_max_residual_mm=round(float(np.max(corner_residuals)), 3),
                study_xy_margin_mm=float(study_margin),
                nominal_key_centers_board_xy_mm={name:[round(float(v), 2) for v in point]
                                                 for name, point in keys.items()},
                keyboard_registered=False, arm_board_transform_verified=False,
                actual_key_centers_measured=False, tool_geometry_measured=False,
                physical_clearance_verified=False, motion_authorized=False,
                limitations=annotation["limitations"])


def estimate_files(annotation_path: Path, profile_path: Path, photo_path: Path) -> dict:
    annotation_path = Path(annotation_path).resolve(strict=True)
    profile_path = Path(profile_path).resolve(strict=True)
    photo_path = Path(photo_path).resolve(strict=True)
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    profile_bytes = profile_path.read_bytes()
    profile = json.loads(profile_bytes)["keyboard"]
    if not photo_path.is_file():
        raise ValueError("Source photograph must be a regular file")
    with photo_path.open("rb") as stream:
        photo_bytes = stream.read(MAX_PHOTO_BYTES + 1)
    if len(photo_bytes) > MAX_PHOTO_BYTES:
        raise ValueError("Source photograph exceeds the 25 MiB limit")
    photo_digest = hashlib.sha256(photo_bytes).hexdigest()
    if photo_digest != annotation["photo"]["sha256"]:
        raise ValueError("Annotated source photograph has changed")
    try:
        dimensions = jpeg_dimensions(photo_bytes)
    except CameraCaptureError as exc:
        raise ValueError(f"Annotated source photograph is not a valid JPEG: {exc}") from exc
    expected_dimensions = (annotation["photo"]["width_px"],
                           annotation["photo"]["height_px"])
    if dimensions != expected_dimensions:
        raise ValueError("Annotated source photograph dimensions have changed")
    result = estimate(annotation, profile,
                      profile_sha256=hashlib.sha256(profile_bytes).hexdigest())
    result["source_photo_bytes_verified"] = True
    result["source_photo_dimensions_verified"] = True
    return result
