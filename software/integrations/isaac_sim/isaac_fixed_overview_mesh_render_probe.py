"""Render pinned official per-link meshes from the fixed overview in Isaac.

The probe uses the seven visual meshes bound by the upstream Xacro and places
them with the governed URDF forward kinematics.  It exports RGB, semantic link
masks, robot-only metric depth, and mask comparison against the lightweight
capsule corpus.  Visual meshes are never promoted to collision geometry.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any


UPSTREAM_COMMIT = "40dbd84b553695212fab713e8465f817ba95454d"
EXPECTED_URDF_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
LINKS = ("base_link", "link1", "link2", "link3", "link4", "link5", "gripper_link")
REFERENCE_POSES = {
    "ready": None,
    "hover_t": (-0.23228866404719983, 0.63981053780154, 1.9887938075201332,
                -1.0578043436893252, 4.987262088921639e-10),
    "hover_e": (-0.31131621748840294, 0.6841707277884785, 1.8469265148292362,
                -0.9602972424740397, 4.2194931944696405e-10),
}
SCHEDULE_POSE_SEQUENCES = {
    "hover_h": 34,
    "contact_h": 35,
    "hover_1": 63,
    "contact_1": 64,
    "hover_period": 103,
    "contact_period": 104,
    "transit_outbound_08": 8,
    "transit_outbound_17": 17,
    "transit_outbound_26": 26,
    "transit_return_112": 112,
    "transit_return_120": 120,
    "transit_return_128": 128,
    "transit_h_to_1_44": 44,
    "transit_h_to_1_52": 52,
    "transit_h_to_1_60": 60,
    "transit_1_to_period_72": 72,
    "transit_1_to_period_84": 84,
    "transit_1_to_period_96": 96,
    "specificity_outbound_02": 2,
    "specificity_outbound_04": 4,
    "specificity_outbound_06": 6,
    "specificity_return_124": 124,
    "specificity_return_126": 126,
    "specificity_return_130": 130,
    "specificity_eval_outbound_10": 10,
    "specificity_eval_outbound_13": 13,
    "specificity_eval_outbound_20": 20,
    "specificity_eval_return_114": 114,
    "specificity_eval_return_118": 118,
    "specificity_eval_return_122": 122,
    "targetaware_dev_outbound_11": 11,
    "targetaware_dev_outbound_15": 15,
    "targetaware_dev_outbound_19": 19,
    "targetaware_dev_return_113": 113,
    "targetaware_dev_return_117": 117,
    "targetaware_dev_return_121": 121,
    "targetaware_eval_outbound_23": 23,
    "targetaware_eval_outbound_27": 27,
    "targetaware_eval_outbound_31": 31,
    "targetaware_eval_return_115": 115,
    "targetaware_eval_return_119": 119,
    "targetaware_eval_return_123": 123,
}
POSE_GROUPS = {
    "training": (
        "ready", "hover_t", "hover_e", "hover_h", "contact_h", "hover_1",
        "contact_1", "hover_period", "contact_period",
        "transit_outbound_08", "transit_outbound_17", "transit_outbound_26",
        "transit_return_112", "transit_return_120", "transit_return_128",
        "transit_h_to_1_44", "transit_h_to_1_52", "transit_h_to_1_60",
        "transit_1_to_period_72", "transit_1_to_period_84",
        "transit_1_to_period_96",
        "specificity_outbound_02", "specificity_outbound_04",
        "specificity_outbound_06", "specificity_return_124",
        "specificity_return_126", "specificity_return_130",
        "specificity_eval_outbound_10", "specificity_eval_outbound_13",
        "specificity_eval_outbound_20", "specificity_eval_return_114",
        "specificity_eval_return_118", "specificity_eval_return_122",
    ),
    "development": (
        "targetaware_dev_outbound_11", "targetaware_dev_outbound_15",
        "targetaware_dev_outbound_19", "targetaware_dev_return_113",
        "targetaware_dev_return_117", "targetaware_dev_return_121",
    ),
    "evaluation": (
        "targetaware_eval_outbound_23", "targetaware_eval_outbound_27",
        "targetaware_eval_outbound_31", "targetaware_eval_return_115",
        "targetaware_eval_return_119", "targetaware_eval_return_123",
    ),
}
PERTURBATION_SCHEDULE_POSE_SEQUENCES = {
    "maskoffset_dev_outbound_12": 12,
    "maskoffset_dev_outbound_16": 16,
    "maskoffset_dev_outbound_21": 21,
    "maskoffset_dev_return_116": 116,
    "maskoffset_dev_return_125": 125,
    "maskoffset_dev_return_129": 129,
}
PERTURBATION_POSE_GROUPS = {
    "training": (),
    "development": tuple(PERTURBATION_SCHEDULE_POSE_SEQUENCES),
    "evaluation": (),
}
POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES = {
    "policy_eval_h_to_1_40": 40,
    "policy_eval_h_to_1_48": 48,
    "policy_eval_h_to_1_56": 56,
    "policy_eval_1_to_period_76": 76,
    "policy_eval_1_to_period_88": 88,
    "policy_eval_1_to_period_100": 100,
}
POLICY_EVALUATION_POSE_GROUPS = {
    "training": (),
    "development": (),
    "evaluation": tuple(POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES),
}
HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES = {
    "hardneg_h_to_1_42": 42,
    "hardneg_h_to_1_50": 50,
    "hardneg_h_to_1_58": 58,
    "hardneg_1_to_period_78": 78,
    "hardneg_1_to_period_90": 90,
    "hardneg_1_to_period_98": 98,
}
HARD_NEGATIVE_POSE_GROUPS = {
    "training": (),
    "development": tuple(HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES),
    "evaluation": (),
}
TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES = {
    "targetid_h_to_1_41": 41,
    "targetid_h_to_1_43": 43,
    "targetid_h_to_1_45": 45,
    "targetid_h_to_1_47": 47,
    "targetid_h_to_1_49": 49,
    "targetid_h_to_1_51": 51,
    "targetid_1_to_period_77": 77,
    "targetid_1_to_period_79": 79,
    "targetid_1_to_period_81": 81,
    "targetid_1_to_period_83": 83,
    "targetid_1_to_period_85": 85,
    "targetid_1_to_period_87": 87,
}
TARGET_IDENTITY_TRAINING_POSE_GROUPS = {
    "training": tuple(TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES),
    "development": (),
    "evaluation": (),
}
FUSION_EVALUATION_SCHEDULE_POSE_SEQUENCES = {
    "fusion_eval_h_to_1_46": 46,
    "fusion_eval_h_to_1_54": 54,
    "fusion_eval_h_to_1_62": 62,
    "fusion_eval_1_to_period_80": 80,
    "fusion_eval_1_to_period_92": 92,
    "fusion_eval_1_to_period_102": 102,
}
FUSION_EVALUATION_POSE_GROUPS = {
    "training": (),
    "development": (),
    "evaluation": tuple(FUSION_EVALUATION_SCHEDULE_POSE_SEQUENCES),
}
OCCLUSION_RECALL_SCHEDULE_POSE_SEQUENCES = {
    "recall_train_h_retract_36": 36,
    "recall_train_h_contact_38": 38,
    "recall_train_h_to_1_53": 53,
    "recall_train_h_to_1_55": 55,
    "recall_train_h_to_1_57": 57,
    "recall_train_h_to_1_59": 59,
    "recall_train_h_to_1_61": 61,
    "recall_train_1_to_period_66": 66,
    "recall_train_1_to_period_68": 68,
    "recall_train_1_to_period_70": 70,
    "recall_train_return_106": 106,
    "recall_train_return_108": 108,
    "recall_dev_h_transit_30": 30,
    "recall_dev_h_transit_32": 32,
    "recall_dev_1_to_period_67": 67,
    "recall_dev_1_to_period_69": 69,
    "recall_dev_1_to_period_71": 71,
    "recall_dev_return_107": 107,
}
OCCLUSION_RECALL_POSE_GROUPS = {
    "training": tuple(
        pose_id for pose_id in OCCLUSION_RECALL_SCHEDULE_POSE_SEQUENCES
        if pose_id.startswith("recall_train_")
    ),
    "development": tuple(
        pose_id for pose_id in OCCLUSION_RECALL_SCHEDULE_POSE_SEQUENCES
        if pose_id.startswith("recall_dev_")
    ),
    "evaluation": (),
}
RECALL_EVALUATION_SCHEDULE_POSE_SEQUENCES = {
    "recall_eval_period_transit_73": 73,
    "recall_eval_period_transit_82": 82,
    "recall_eval_period_transit_91": 91,
    "recall_eval_period_transit_99": 99,
    "recall_eval_period_retract_105": 105,
    "recall_eval_return_transit_110": 110,
}
RECALL_EVALUATION_POSE_GROUPS = {
    "training": (),
    "development": (),
    "evaluation": tuple(RECALL_EVALUATION_SCHEDULE_POSE_SEQUENCES),
}
REBALANCE_EVALUATION_SCHEDULE_POSE_SEQUENCES = {
    "rebalance_eval_static_01": 1001,
    "rebalance_eval_static_02": 1002,
    "rebalance_eval_static_03": 1003,
    "rebalance_eval_static_04": 1004,
    "rebalance_eval_static_05": 1005,
    "rebalance_eval_static_06": 1006,
}
REBALANCE_EVALUATION_POSE_GROUPS = {
    "training": (),
    "development": (),
    "evaluation": tuple(REBALANCE_EVALUATION_SCHEDULE_POSE_SEQUENCES),
}
EXPECTED_POSE_DIVERSE_TRAINING_FILE_SHA256 = (
    "38e169e1b8b59d77785470b44e5feca8dad78fce18bc6dab8459ffa3f867ae0e"
)
EXPECTED_GROUPED_NEIGHBORHOOD_TRAINING_FILE_SHA256 = (
    "0e0f30a801a38720f0dc6ddc5b769c8447dda09a67a8577ddf37fd7fffb5abae"
)
SPECIFICITY_REBALANCE_SCHEDULE_POSE_SEQUENCES = {
    "rebalance_train_h_transit_33": 33,
    "rebalance_train_h_to_1_65": 65,
    "rebalance_train_period_transit_74": 74,
    "rebalance_train_period_transit_86": 86,
    "rebalance_train_period_transit_94": 94,
    "rebalance_train_period_transit_97": 97,
    "rebalance_train_return_transit_109": 109,
    "rebalance_train_return_transit_111": 111,
    "rebalance_dev_period_transit_75": 75,
    "rebalance_dev_period_transit_89": 89,
    "rebalance_dev_period_transit_93": 93,
    "rebalance_dev_period_transit_95": 95,
    "rebalance_dev_period_transit_101": 101,
}
SPECIFICITY_REBALANCE_POSE_GROUPS = {
    "training": tuple(
        pose_id for pose_id in SPECIFICITY_REBALANCE_SCHEDULE_POSE_SEQUENCES
        if pose_id.startswith("rebalance_train_")
    ),
    "development": tuple(
        pose_id for pose_id in SPECIFICITY_REBALANCE_SCHEDULE_POSE_SEQUENCES
        if pose_id.startswith("rebalance_dev_")
    ),
    "evaluation": (),
}
EXPECTED_SCHEDULE_FILE_SHA256 = "6a59ce143f5527c7a9ced09b08d5515644ea4fb859dd69691e08483eb020ee42"
EXPECTED_STATIC_EVALUATION_POSE_FILE_SHA256 = (
    "638e17a18feb79aa15864078ff80df37e69ebe6889710de08d98ed709013fb69"
)
WIDTH = 1920
HEIGHT = 1080
MAX_IMAGE_DIMENSION = 65_500
ATLAS_CHUNK_SIZE = 16


def _atlas_layout(item_count: int) -> tuple[int, int, tuple[tuple[int, int, int, int], ...]]:
    """Tile fixed-size renders without crossing Pillow's image dimension limit."""
    if item_count <= 0:
        raise ValueError("atlas requires at least one item")
    minimum_columns = max(1, (item_count * HEIGHT + MAX_IMAGE_DIMENSION - 1)
                          // MAX_IMAGE_DIMENSION)
    for columns in range(minimum_columns, item_count + 1):
        rows = (item_count + columns - 1) // columns
        if columns * WIDTH <= MAX_IMAGE_DIMENSION \
                and rows * HEIGHT <= MAX_IMAGE_DIMENSION:
            boxes = tuple(
                (
                    (index % columns) * WIDTH,
                    (index // columns) * HEIGHT,
                    (index % columns + 1) * WIDTH,
                    (index // columns + 1) * HEIGHT,
                )
                for index in range(item_count)
            )
            return columns, rows, boxes
    raise ValueError("atlas cannot fit within the image dimension limit")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=not binary,
    )
    return result.stdout


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _joint_positions(context: Any, order: tuple[str, ...], values: tuple[float, ...] | None) -> dict[str, Any]:
    from rocell.geometry import JointPosition

    if values is None:
        result = dict(context.scenario.ready_arm_joint_positions_rad)
    else:
        result = {name: JointPosition.radians(value) for name, value in zip(order[:-1], values)}
    result[order[-1]] = context.scenario.fixed_gripper_position
    return result


def _matrix_points(vertices: Any, transform: Any, np: Any) -> Any:
    rotation = np.asarray(transform.rotation.matrix, dtype=float).reshape(3, 3)
    translation = np.asarray([
        transform.translation_mm.x,
        transform.translation_mm.y,
        transform.translation_mm.z,
    ])
    return (np.asarray(vertices, dtype=float) @ rotation.T + translation) / 1000.0


def _cube(stage: Any, path: str, minimum_mm: tuple[float, float, float], maximum_mm: tuple[float, float, float], color: tuple[float, float, float], Gf: Any, UsdGeom: Any) -> None:
    cube = UsdGeom.Cube.Define(stage, path)
    cube.GetSizeAttr().Set(1.0)
    center = tuple((low + high) / 2000.0 for low, high in zip(minimum_mm, maximum_mm))
    size = tuple((high - low) / 1000.0 for low, high in zip(minimum_mm, maximum_mm))
    xform = UsdGeom.Xformable(cube)
    xform.AddTranslateOp().Set(Gf.Vec3d(*center))
    xform.AddScaleOp().Set(Gf.Vec3d(*size))
    cube.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])


def _semantic_array(value: Any, np: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(value, dict) and "data" in value:
        data = np.asarray(value["data"])
        info = value.get("info", {})
    else:
        data = np.asarray(value)
        info = {}
    if data.ndim == 3 and data.shape[-1] == 1:
        data = data[..., 0]
    if data.shape != (HEIGHT, WIDTH):
        raise RuntimeError(f"unexpected semantic shape {data.shape}")
    return data.astype(np.uint32), json.loads(json.dumps(info, default=str))


def _depth_array(value: Any, np: Any) -> Any:
    data = np.asarray(value["data"] if isinstance(value, dict) and "data" in value else value)
    if data.ndim == 3 and data.shape[-1] == 1:
        data = data[..., 0]
    if data.shape != (HEIGHT, WIDTH):
        raise RuntimeError(f"unexpected depth shape {data.shape}")
    return data.astype(np.float32)


def _robot_semantic_ids(info: dict[str, Any]) -> set[int]:
    id_to_labels = info.get("idToLabels")
    if not isinstance(id_to_labels, dict):
        raise RuntimeError("semantic output omitted idToLabels")
    robot_ids = {
        int(raw_id)
        for raw_id, labels in id_to_labels.items()
        if isinstance(labels, dict) and labels.get("class") in LINKS
    }
    if not robot_ids:
        raise RuntimeError("semantic output resolved no visible robot link IDs")
    return robot_ids


def _project_targets(context: Any, Point3Mm: Any) -> list[dict[str, object]]:
    camera = context.scenario.overview.camera
    camera_T_board = context.scenario.overview.camera_T_board
    targets = [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()]
    result = []
    for target in sorted(targets, key=lambda value: (value.device, value.target_id)):
        left, front, right, rear = target.safe_rectangle_board_mm
        polygon = []
        for x, y in ((left, rear), (right, rear), (right, front), (left, front)):
            pixel = camera.project(camera_T_board.transform_point(
                Point3Mm("board", x, y, target.center.z)
            ))
            polygon.append([pixel.u_px, pixel.v_px])
        center = camera.project(camera_T_board.transform_point(target.center))
        result.append({
            "device": target.device,
            "target_id": target.target_id,
            "center_board_mm": [target.center.x, target.center.y, target.center.z],
            "safe_rectangle_board_mm": [left, front, right, rear],
            "center_px": [center.u_px, center.v_px],
            "safe_polygon_px": polygon,
            "depth_mm": center.depth_mm,
            "in_frame": center.in_bounds,
        })
    return result


def _target_occlusion(target: dict[str, object], robot_mask: Any, Image: Any,
                      ImageDraw: Any, np: Any) -> tuple[bool, float]:
    diagnostic = _target_occlusion_diagnostic(
        target, robot_mask, Image, ImageDraw, np, measure_clearance=False,
    )
    return (
        bool(diagnostic["center_occluded"]),
        float(diagnostic["safe_region_overlap_fraction"]),
    )


def _target_occlusion_diagnostic(
    target: dict[str, object], robot_mask: Any, Image: Any,
    ImageDraw: Any, np: Any, *, measure_clearance: bool = True,
) -> dict[str, object]:
    """Measure nominal mask overlap and pixel clearance for one safe region.

    Pixel clearance is a simulation diagnostic, not a calibrated dilation
    bound.  A physical qualification must derive dilation from measured camera,
    feedback, and backlash evidence before using it for an admission decision.
    """
    polygon = [(round(x), round(y)) for x, y in target["safe_polygon_px"]]  # type: ignore[index]
    region = Image.new("1", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(region).polygon(polygon, fill=1)
    region_mask = np.asarray(region, dtype=bool)
    robot_mask = np.asarray(robot_mask, dtype=bool)
    if robot_mask.shape != region_mask.shape:
        raise ValueError("robot mask shape does not match overview camera")
    area = int(np.count_nonzero(region_mask))
    if area == 0:
        raise ValueError("target safe region rasterized to zero pixels")
    overlap = int(np.count_nonzero(region_mask & robot_mask))
    center = tuple(round(value) for value in target["center_px"])  # type: ignore[arg-type]
    center_occluded = (
        0 <= center[0] < WIDTH and 0 <= center[1] < HEIGHT
        and bool(robot_mask[center[1], center[0]])
    )
    clearance_px = 0.0
    if measure_clearance and overlap == 0 and bool(np.any(robot_mask)):
        from scipy.ndimage import distance_transform_edt

        distance_to_robot = distance_transform_edt(~robot_mask)
        clearance_px = float(np.min(distance_to_robot[region_mask]))
    return {
        "center_occluded": center_occluded,
        "safe_region_area_px": area,
        "safe_region_overlap_px": overlap,
        "safe_region_overlap_fraction": overlap / area,
        "nominal_clearance_px": clearance_px,
    }


def _project_board_point(
    point_mm: list[float] | tuple[float, float, float],
    camera_position_mm: list[float] | tuple[float, float, float],
    camera_look_at_mm: list[float] | tuple[float, float, float],
    camera_up_axis: list[float] | tuple[float, float, float],
    *,
    width_px: int = WIDTH,
    height_px: int = HEIGHT,
    focal_length_mm: float = 24.0,
    horizontal_aperture_mm: float = 46.08,
) -> tuple[float, float, float] | None:
    """Project one board-frame point through a declared pinhole camera."""
    import numpy as np

    position = np.asarray(camera_position_mm, dtype=np.float64)
    look_at = np.asarray(camera_look_at_mm, dtype=np.float64)
    up_hint = np.asarray(camera_up_axis, dtype=np.float64)
    forward = look_at - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up_hint)
    right_norm = np.linalg.norm(right)
    if right_norm <= 1e-12:
        raise ValueError("camera up axis is parallel to viewing direction")
    right /= right_norm
    up = np.cross(right, forward)
    relative = np.asarray(point_mm, dtype=np.float64) - position
    depth = float(np.dot(relative, forward))
    if depth <= 1.0:
        return None
    focal_px = focal_length_mm / horizontal_aperture_mm * width_px
    return (
        width_px / 2.0 + focal_px * float(np.dot(relative, right)) / depth,
        height_px / 2.0 - focal_px * float(np.dot(relative, up)) / depth,
        depth,
    )


def _native_sensor_intrinsics(
    width_px: int,
    height_px: int,
    pixel_pitch_um: float,
    focal_length_mm: float,
) -> dict[str, float]:
    """Derive centered native-mode pinhole intrinsics from physical sampling.

    The focal length and pixel pitch may be published rather than measured.
    Callers must retain that provenance; this helper creates no calibration.
    """
    if width_px <= 0 or height_px <= 0:
        raise ValueError("native sensor dimensions must be positive")
    if pixel_pitch_um <= 0.0 or focal_length_mm <= 0.0:
        raise ValueError("pixel pitch and focal length must be positive")
    pitch_mm = pixel_pitch_um / 1000.0
    focal_px = focal_length_mm / pitch_mm
    return {
        "fx_px": focal_px,
        "fy_px": focal_px,
        "cx_px": width_px / 2.0,
        "cy_px": height_px / 2.0,
        "sensor_mode_width_mm": width_px * pitch_mm,
        "sensor_mode_height_mm": height_px * pitch_mm,
    }


def _project_nadir_board_point(
    point_mm: list[float] | tuple[float, float, float],
    camera_center_xy_mm: list[float] | tuple[float, float],
    camera_height_board_mm: float,
    intrinsics: dict[str, float],
    distortion: dict[str, float] | None = None,
    *,
    width_px: int = 5472,
    height_px: int = 3648,
    board_y_to_image_v_sign: int = 1,
) -> tuple[float, float, float] | None:
    """Project a board point through a centered, straight-down camera.

    Board +X maps to image +u and board +Y maps to image +v.  Height is
    measured from the board plane to the optical center.  This intentionally
    excludes tilt, yaw, and XY variation for the fixed-nadir height family.
    """
    if board_y_to_image_v_sign not in {-1, 1}:
        raise ValueError("board-Y image-v sign must be -1 or 1")
    x_mm, y_mm, z_mm = (float(value) for value in point_mm)
    depth_mm = float(camera_height_board_mm) - z_mm
    if depth_mm <= 1.0:
        return None
    normalized_x = (x_mm - float(camera_center_xy_mm[0])) / depth_mm
    normalized_y = (y_mm - float(camera_center_xy_mm[1])) / depth_mm
    coefficients = distortion or {}
    k1 = float(coefficients.get("k1", 0.0))
    k2 = float(coefficients.get("k2", 0.0))
    p1 = float(coefficients.get("p1", 0.0))
    p2 = float(coefficients.get("p2", 0.0))
    k3 = float(coefficients.get("k3", 0.0))
    radius_squared = normalized_x * normalized_x + normalized_y * normalized_y
    radial = (
        1.0 + k1 * radius_squared + k2 * radius_squared**2
        + k3 * radius_squared**3
    )
    distorted_x = (
        normalized_x * radial + 2.0 * p1 * normalized_x * normalized_y
        + p2 * (radius_squared + 2.0 * normalized_x * normalized_x)
    )
    distorted_y = (
        normalized_y * radial + p1 * (radius_squared + 2.0 * normalized_y * normalized_y)
        + 2.0 * p2 * normalized_x * normalized_y
    )
    u_px = float(intrinsics["fx_px"]) * distorted_x + float(intrinsics["cx_px"])
    v_px = (
        board_y_to_image_v_sign * float(intrinsics["fy_px"]) * distorted_y
        + float(intrinsics["cy_px"])
    )
    if not math.isfinite(u_px) or not math.isfinite(v_px):
        raise ValueError("nadir projection produced a non-finite image point")
    return (u_px, v_px, depth_mm)


def _ground_sample_distance_mm_per_px(
    depth_mm: float, pixel_pitch_um: float, focal_length_mm: float,
) -> float:
    """Return paraxial object-plane millimetres represented by one pixel."""
    if depth_mm <= 0.0 or pixel_pitch_um <= 0.0 or focal_length_mm <= 0.0:
        raise ValueError("depth, pixel pitch, and focal length must be positive")
    return depth_mm * (pixel_pitch_um / 1000.0) / focal_length_mm


def _fixed_physical_crop_box(
    center_board_mm: list[float] | tuple[float, float, float],
    extent_xy_mm: list[float] | tuple[float, float],
    camera_center_xy_mm: list[float] | tuple[float, float],
    camera_height_board_mm: float,
    intrinsics: dict[str, float],
    distortion: dict[str, float] | None = None,
    *,
    width_px: int = 5472,
    height_px: int = 3648,
    board_y_to_image_v_sign: int = 1,
) -> dict[str, Any]:
    """Project a fixed board-plane rectangle and retain native pixel support.

    The returned floating-point box is suitable for subpixel resampling.  Its
    physical extent does not change with camera height; only native sampling
    density changes.  This keeps height augmentation from silently changing
    the amount of physical context presented to a model.
    """
    if len(extent_xy_mm) != 2 or any(float(value) <= 0.0 for value in extent_xy_mm):
        raise ValueError("physical crop extents must be two positive values")
    center_x, center_y, center_z = (float(value) for value in center_board_mm)
    half_x, half_y = float(extent_xy_mm[0]) / 2.0, float(extent_xy_mm[1]) / 2.0
    corners = [
        _project_nadir_board_point(
            (center_x + dx, center_y + dy, center_z),
            camera_center_xy_mm, camera_height_board_mm, intrinsics, distortion,
            width_px=width_px, height_px=height_px,
            board_y_to_image_v_sign=board_y_to_image_v_sign,
        )
        for dx, dy in ((-half_x, -half_y), (half_x, -half_y),
                       (half_x, half_y), (-half_x, half_y))
    ]
    if any(point is None for point in corners):
        raise ValueError("physical crop lies behind the camera")
    projected = [point for point in corners if point is not None]
    left = min(point[0] for point in projected)
    top = min(point[1] for point in projected)
    right = max(point[0] for point in projected)
    bottom = max(point[1] for point in projected)
    in_frame = left >= 0.0 and top >= 0.0 and right <= width_px and bottom <= height_px
    return {
        "physical_extent_xy_mm": [float(extent_xy_mm[0]), float(extent_xy_mm[1])],
        "native_box_ltrb_px": [left, top, right, bottom],
        "native_support_width_px": right - left,
        "native_support_height_px": bottom - top,
        "in_frame": in_frame,
        "depth_mm": projected[0][2],
        "board_y_to_image_v_sign": board_y_to_image_v_sign,
    }


def _resample_fixed_physical_crop(
    image: Any, crop: dict[str, Any], output_size_px: tuple[int, int], Image: Any,
) -> Any:
    """Resample a validated floating-point physical crop to a fixed tensor size."""
    if not crop.get("in_frame"):
        raise ValueError("fixed physical crop is not fully in frame")
    if len(output_size_px) != 2 or any(int(value) <= 0 for value in output_size_px):
        raise ValueError("output dimensions must be positive")
    return image.transform(
        tuple(int(value) for value in output_size_px),
        Image.Transform.EXTENT,
        tuple(float(value) for value in crop["native_box_ltrb_px"]),
        resample=Image.Resampling.BICUBIC,
    )


def _thin_lens_blur_diameter_px(
    object_distance_mm: float,
    focus_distance_mm: float,
    focal_length_mm: float,
    aperture_f_number: float,
    pixel_pitch_um: float,
) -> float:
    """Exploratory defocus diameter at a sensor focused at another plane."""
    values = (
        object_distance_mm, focus_distance_mm, focal_length_mm,
        aperture_f_number, pixel_pitch_um,
    )
    if any(value <= 0.0 for value in values):
        raise ValueError("thin-lens inputs must be positive")
    if object_distance_mm <= focal_length_mm or focus_distance_mm <= focal_length_mm:
        raise ValueError("object and focus distances must exceed focal length")
    image_distance = focal_length_mm * object_distance_mm / (
        object_distance_mm - focal_length_mm
    )
    focus_image_distance = focal_length_mm * focus_distance_mm / (
        focus_distance_mm - focal_length_mm
    )
    aperture_diameter_mm = focal_length_mm / aperture_f_number
    blur_mm = aperture_diameter_mm * abs(focus_image_distance - image_distance) / image_distance
    return blur_mm / (pixel_pitch_um / 1000.0)


def _capsule_polygon_clearance_px(
    start_px: tuple[float, float], end_px: tuple[float, float],
    radius_px: float, polygon_px: list[list[float]],
) -> float:
    """Signed 2-D clearance from a projected capsule to a target polygon."""
    def point_segment_distance(
        point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
    ) -> float:
        dx, dy = b[0] - a[0], b[1] - a[1]
        denominator = dx * dx + dy * dy
        if denominator <= 1e-18:
            return math.hypot(point[0] - a[0], point[1] - a[1])
        t = max(0.0, min(1.0, (
            (point[0] - a[0]) * dx + (point[1] - a[1]) * dy
        ) / denominator))
        return math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy))

    def orientation(a: tuple[float, float], b: tuple[float, float],
                    c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def intersects(a: tuple[float, float], b: tuple[float, float],
                   c: tuple[float, float], d: tuple[float, float]) -> bool:
        o1, o2 = orientation(a, b, c), orientation(a, b, d)
        o3, o4 = orientation(c, d, a), orientation(c, d, b)
        return o1 * o2 <= 0.0 and o3 * o4 <= 0.0

    polygon = [tuple(point) for point in polygon_px]
    distances = []
    for index, edge_start in enumerate(polygon):
        edge_end = polygon[(index + 1) % len(polygon)]
        if intersects(start_px, end_px, edge_start, edge_end):
            return -float(radius_px)
        distances.extend((
            point_segment_distance(start_px, edge_start, edge_end),
            point_segment_distance(end_px, edge_start, edge_end),
            point_segment_distance(edge_start, start_px, end_px),
            point_segment_distance(edge_end, start_px, end_px),
        ))
    return min(distances) - float(radius_px)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--capsule-manifest", type=Path, required=True)
    parser.add_argument("--schedule-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument(
        "--campaign",
        choices=(
            "target-aware-v5", "mask-perturbation-v6",
            "policy-evaluation-v7", "hard-negative-v8",
            "target-identity-training-v9", "fusion-evaluation-v10",
            "occlusion-recall-v11",
            "recall-evaluation-v12",
            "specificity-rebalance-v13",
            "rebalance-evaluation-v14",
            "pose-diverse-training-v15",
            "grouped-neighborhood-training-v16",
        ),
        default="target-aware-v5",
    )
    args = parser.parse_args()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        workspace = args.workspace.resolve(strict=True)
        upstream = args.upstream_repo.resolve(strict=True)
        mesh_receipt_path = args.mesh_receipt.resolve(strict=True)
        capsule_manifest_path = args.capsule_manifest.resolve(strict=True)
        schedule_bundle_path = args.schedule_bundle.resolve(strict=True)
        output_dir = args.output_dir.resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError("output directory must be empty")
        output_dir.mkdir(parents=True, exist_ok=True)

        if str(_git(upstream, "rev-parse", "HEAD")).strip() != UPSTREAM_COMMIT:
            raise ValueError("upstream checkout identity mismatch")
        mesh_receipt = _load(mesh_receipt_path)
        capsule_manifest = _load(capsule_manifest_path)
        expected_schedule_file_sha256 = {
            "rebalance-evaluation-v14": EXPECTED_STATIC_EVALUATION_POSE_FILE_SHA256,
            "pose-diverse-training-v15": EXPECTED_POSE_DIVERSE_TRAINING_FILE_SHA256,
            "grouped-neighborhood-training-v16": EXPECTED_GROUPED_NEIGHBORHOOD_TRAINING_FILE_SHA256,
        }.get(args.campaign, EXPECTED_SCHEDULE_FILE_SHA256)
        if _sha256(schedule_bundle_path.read_bytes()) != expected_schedule_file_sha256:
            raise ValueError("schedule bundle identity mismatch")
        schedule_bundle = _load(schedule_bundle_path)
        if (schedule_bundle.get("physical_authority") is not False
                or schedule_bundle.get("hardware_access") is not False
                or schedule_bundle.get("hardware_writes") != 0
                or schedule_bundle.get("physical_movements") != 0):
            raise ValueError("schedule bundle claims authority")
        if mesh_receipt["evidence_class"] != "UPSTREAM_LINK_MESH_GROUPING_ONLY":
            raise ValueError("mesh receipt has wrong evidence class")
        if capsule_manifest["schema"] != "rocell.fixed_overview_segmentation_corpus.v1":
            raise ValueError("capsule manifest schema mismatch")

        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.application.arm_camera_pose import ARM_CAMERA_JOINT_ORDER
        from rocell.application.bootstrap import bootstrap_virtual_workcell
        from rocell.geometry import Point3Mm, UrdfModel

        bootstrap = bootstrap_virtual_workcell(workspace)
        context = bootstrap.context
        schedule_by_sequence = {row["sequence"]: row for row in schedule_bundle["samples"]}
        if args.campaign == "grouped-neighborhood-training-v16":
            if schedule_bundle.get("schema") \
                    != "tactevra.ai_grouped_neighborhood_training_fixture.v1" \
                    or schedule_bundle.get("scope") \
                    != "SYNTHETIC_STATIC_PERCEPTION_TRAIN_DEVELOPMENT_ONLY" \
                    or schedule_bundle.get("sample_count") != 320 \
                    or schedule_bundle.get("split_counts") \
                    != {"training": 256, "development": 64}:
                raise ValueError("grouped-neighborhood fixture contract mismatch")
            schedule_pose_sequences = {
                row["pose_id"]: row["sequence"] for row in schedule_bundle["samples"]
            }
            pose_groups = {
                split: tuple(
                    row["pose_id"] for row in schedule_bundle["samples"]
                    if row["split"] == split
                )
                for split in ("training", "development")
            }
            pose_groups["evaluation"] = ()
            poses = {}
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v16"
        elif args.campaign == "pose-diverse-training-v15":
            if schedule_bundle.get("schema") \
                    != "tactevra.ai_pose_diverse_training_fixture.v1" \
                    or schedule_bundle.get("scope") \
                    != "SYNTHETIC_STATIC_PERCEPTION_TRAIN_DEVELOPMENT_ONLY" \
                    or schedule_bundle.get("sample_count") != 96 \
                    or schedule_bundle.get("split_counts") \
                    != {"training": 72, "development": 24}:
                raise ValueError("pose-diverse fixture contract mismatch")
            schedule_pose_sequences = {
                row["pose_id"]: row["sequence"]
                for row in schedule_bundle["samples"]
            }
            pose_groups = {
                split: tuple(
                    row["pose_id"] for row in schedule_bundle["samples"]
                    if row["split"] == split
                )
                for split in ("training", "development")
            }
            pose_groups["evaluation"] = ()
            poses = {}
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v15"
        elif args.campaign == "rebalance-evaluation-v14":
            poses = {}
            schedule_pose_sequences = REBALANCE_EVALUATION_SCHEDULE_POSE_SEQUENCES
            pose_groups = REBALANCE_EVALUATION_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v14"
        elif args.campaign == "specificity-rebalance-v13":
            poses = {}
            schedule_pose_sequences = SPECIFICITY_REBALANCE_SCHEDULE_POSE_SEQUENCES
            pose_groups = SPECIFICITY_REBALANCE_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v13"
        elif args.campaign == "recall-evaluation-v12":
            poses = {}
            schedule_pose_sequences = RECALL_EVALUATION_SCHEDULE_POSE_SEQUENCES
            pose_groups = RECALL_EVALUATION_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v12"
        elif args.campaign == "occlusion-recall-v11":
            poses = {}
            schedule_pose_sequences = OCCLUSION_RECALL_SCHEDULE_POSE_SEQUENCES
            pose_groups = OCCLUSION_RECALL_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v11"
        elif args.campaign == "fusion-evaluation-v10":
            poses = {}
            schedule_pose_sequences = FUSION_EVALUATION_SCHEDULE_POSE_SEQUENCES
            pose_groups = FUSION_EVALUATION_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v10"
        elif args.campaign == "target-identity-training-v9":
            poses = {}
            schedule_pose_sequences = TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES
            pose_groups = TARGET_IDENTITY_TRAINING_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v9"
        elif args.campaign == "hard-negative-v8":
            poses = {}
            schedule_pose_sequences = HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES
            pose_groups = HARD_NEGATIVE_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v8"
        elif args.campaign == "policy-evaluation-v7":
            poses = {}
            schedule_pose_sequences = POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES
            pose_groups = POLICY_EVALUATION_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v7"
        elif args.campaign == "mask-perturbation-v6":
            poses: dict[str, tuple[float, ...] | None] = {}
            schedule_pose_sequences = PERTURBATION_SCHEDULE_POSE_SEQUENCES
            pose_groups = PERTURBATION_POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v6"
        else:
            poses = dict(REFERENCE_POSES)
            schedule_pose_sequences = SCHEDULE_POSE_SEQUENCES
            pose_groups = POSE_GROUPS
            receipt_schema = "tactevra.isaac_fixed_overview_mesh_render.v5"
        for pose_id, sequence in schedule_pose_sequences.items():
            sample = schedule_by_sequence[sequence]
            poses[pose_id] = tuple(
                sample["joint_positions_rad"][name]
                for name in ARM_CAMERA_JOINT_ORDER[:-1]
            )
        declared_pose_ids = {pose_id for group in pose_groups.values() for pose_id in group}
        if declared_pose_ids != set(poses) or sum(map(len, pose_groups.values())) != len(poses):
            raise ValueError("pose groups must partition every rendered pose exactly once")
        model_path = context.scenario.model_path
        if _sha256(model_path.read_bytes()) != EXPECTED_URDF_SHA256:
            raise ValueError("governed URDF identity mismatch")
        if mesh_receipt["home_pose_step_envelope_comparison"]["pass"] is not True:
            raise ValueError("official link-mesh envelope comparison did not pass")
        inventory = {row["link_name"]: row for row in mesh_receipt["mesh_inventory"]}
        if set(inventory) != set(LINKS):
            raise ValueError("mesh receipt link set mismatch")

        from isaacsim import SimulationApp
        app = SimulationApp({"headless": True, "multi_gpu": False})
        import carb.settings
        import numpy as np
        import omni.replicator.core as rep
        import omni.usd
        import trimesh
        from isaacsim.core.experimental.utils.semantics import add_labels
        from PIL import Image, ImageDraw
        from pxr import Gf, UsdGeom, UsdLux

        rep.orchestrator.set_capture_on_play(False)
        carb.settings.get_settings().set("rtx/post/dlss/execMode", 2)
        omni.usd.get_context().new_stage()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        root = UsdGeom.Xform.Define(stage, "/World").GetPrim()
        stage.SetDefaultPrim(root)

        board = context.scene.board
        _cube(stage, "/World/Board", (board.minimum.x, board.minimum.y, board.minimum.z - 4.0),
              (board.maximum.x, board.maximum.y, board.minimum.z), (0.72, 0.72, 0.72), Gf, UsdGeom)
        for name, device in sorted(context.scene.devices.items()):
            if name == "tcp_target":
                continue
            envelope = device.envelope
            _cube(stage, f"/World/Devices/{name}",
                  (envelope.minimum.x, envelope.minimum.y, envelope.minimum.z),
                  (envelope.maximum.x, envelope.maximum.y, envelope.maximum.z),
                  (0.18, 0.2, 0.24) if name == "keyboard" else (0.1, 0.11, 0.13), Gf, UsdGeom)
        all_targets = [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()]
        for index, target in enumerate(sorted(all_targets, key=lambda item: (item.device, item.target_id))):
            left, front, right, rear = target.safe_rectangle_board_mm
            _cube(stage, f"/World/Targets/T{index:03d}", (left, front, target.center.z),
                  (right, rear, target.center.z + 0.6), (0.35, 0.38, 0.44), Gf, UsdGeom)

        model = UrdfModel.from_file(model_path)
        mesh_bytes_by_link: dict[str, bytes] = {}
        for link in LINKS:
            git_path = inventory[link]["git_path"]
            payload = _git(upstream, "show", f"{UPSTREAM_COMMIT}:{git_path}", binary=True)
            assert isinstance(payload, bytes)
            if _sha256(payload) != inventory[link]["sha256"]:
                raise ValueError(f"mesh bytes changed for {link}")
            mesh_bytes_by_link[link] = payload

        pose_prim_paths: dict[str, list[str]] = {}
        pose_joint_positions: dict[str, dict[str, float]] = {}
        for pose_id, values in poses.items():
            joints = _joint_positions(context, ARM_CAMERA_JOINT_ORDER, values)
            pose_joint_positions[pose_id] = {
                name: value.value for name, value in sorted(joints.items())
            }
            transforms = model.forward_kinematics(joints)
            paths = []
            for link_index, link in enumerate(LINKS):
                loaded = trimesh.load_mesh(BytesIO(mesh_bytes_by_link[link]), file_type="stl", process=True)
                board_T_link = context.scenario.board_T_world.compose(transforms[link])
                vertices = _matrix_points(loaded.vertices, board_T_link, np)
                path = f"/World/Robot_{pose_id}/{link}"
                usd_mesh = UsdGeom.Mesh.Define(stage, path)
                usd_mesh.CreatePointsAttr([Gf.Vec3f(*map(float, point)) for point in vertices])
                usd_mesh.CreateFaceVertexCountsAttr([3] * len(loaded.faces))
                usd_mesh.CreateFaceVertexIndicesAttr(np.asarray(loaded.faces, dtype=np.int32).reshape(-1).tolist())
                color = ((35 + link_index * 31) / 255.0, (45 + link_index * 23) / 255.0,
                         (55 + link_index * 17) / 255.0)
                usd_mesh.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
                add_labels(usd_mesh.GetPrim(), labels=[link], taxonomy="class")
                paths.append(path)
            pose_prim_paths[pose_id] = paths
            for path in paths:
                UsdGeom.Imageable(stage.GetPrimAtPath(path)).MakeInvisible()

        dome = UsdLux.DomeLight.Define(stage, "/World/Dome")
        dome.CreateIntensityAttr(900.0)
        distant = UsdLux.DistantLight.Define(stage, "/World/KeyLight")
        distant.CreateIntensityAttr(1800.0)
        distant.CreateAngleAttr(1.0)

        camera = rep.functional.create.camera(
            position=(0.305, 0.2285, 0.5),
            look_at=(0.305, 0.2285, 0.0),
            look_at_up_axis=(0.0, 1.0, 0.0),
            focal_length=24.0,
            horizontal_aperture=46.08,
            clipping_range=(0.01, 5.0),
            name="FixedOverviewCamera",
        )
        render_product = rep.create.render_product(camera, (WIDTH, HEIGHT), name="fixed_overview")
        rgb_annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        semantic_annotator = rep.AnnotatorRegistry.get_annotator(
            "semantic_segmentation", init_params={"colorize": False}
        )
        depth_annotator = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
        for annotator in (rgb_annotator, semantic_annotator, depth_annotator):
            annotator.attach(render_product)

        capsule_layers = {layer["pose_id"]: layer for layer in capsule_manifest["pose_layers"]}
        targets = _project_targets(context, Point3Mm)
        pose_results = []
        mask_hashes: set[str] = set()
        try:
            for pose_id in poses:
                for other in poses:
                    for path in pose_prim_paths[other]:
                        imageable = UsdGeom.Imageable(stage.GetPrimAtPath(path))
                        imageable.MakeVisible() if other == pose_id else imageable.MakeInvisible()
                app.update()
                app.update()
                rep.orchestrator.step(delta_time=0.0, rt_subframes=4)
                rgb = np.asarray(rgb_annotator.get_data())
                semantic, semantic_info = _semantic_array(semantic_annotator.get_data(), np)
                depth_m = _depth_array(depth_annotator.get_data(), np)
                robot_mask = np.isin(semantic, tuple(sorted(_robot_semantic_ids(semantic_info))))
                if not robot_mask.any():
                    raise RuntimeError(f"Isaac semantic mask is empty for {pose_id}")
                robot_depth_mm = np.where(robot_mask & np.isfinite(depth_m),
                                          np.clip(np.rint(depth_m * 1000.0), 1, 65535), 0).astype(np.uint16)
                label_path = output_dir / f"{pose_id}__isaac_robot_mask.png"
                depth_path = output_dir / f"{pose_id}__isaac_robot_depth_mm.png"
                rgb_path = output_dir / f"{pose_id}__isaac_rgb.jpg"
                Image.fromarray((robot_mask.astype(np.uint8) * 255), mode="L").save(label_path, "PNG")
                Image.fromarray(robot_depth_mm).save(depth_path, "PNG")
                Image.fromarray(rgb[..., :3].astype(np.uint8), mode="RGB").save(
                    rgb_path, "JPEG", quality=92, optimize=False, progressive=False, subsampling=0)

                cad_pixels = int(np.count_nonzero(robot_mask))
                comparison: dict[str, object] = {"capsule_comparison_available": False}
                if pose_id in capsule_layers:
                    capsule_path = capsule_manifest_path.parent / capsule_layers[pose_id]["robot_label_path"]
                    capsule_mask = np.asarray(Image.open(capsule_path).convert("L")) != 0
                    intersection = int(np.count_nonzero(robot_mask & capsule_mask))
                    union = int(np.count_nonzero(robot_mask | capsule_mask))
                    comparison = {
                        "capsule_comparison_available": True,
                        "capsule_pixels": int(np.count_nonzero(capsule_mask)),
                        "intersection_pixels": intersection,
                        "union_pixels": union,
                        "mask_iou": intersection / union,
                        "official_mesh_outside_capsule_pixels": int(np.count_nonzero(robot_mask & ~capsule_mask)),
                        "capsule_outside_official_mesh_pixels": int(np.count_nonzero(capsule_mask & ~robot_mask)),
                    }
                mask_hash = _sha256(label_path.read_bytes())
                mask_hashes.add(mask_hash)
                labeled_targets = []
                for target in targets:
                    center_occluded, overlap = _target_occlusion(
                        target, robot_mask, Image, ImageDraw, np
                    )
                    labeled_targets.append({
                        **target,
                        "center_occluded_by_official_mesh": center_occluded,
                        "safe_region_official_mesh_overlap_fraction": overlap,
                    })
                pose_results.append({
                    "pose_id": pose_id,
                    "pose_group": next(
                        group for group, pose_ids in pose_groups.items() if pose_id in pose_ids
                    ),
                    "joint_positions_rad": pose_joint_positions[pose_id],
                    "rgb_path": rgb_path.name,
                    "rgb_sha256": _sha256(rgb_path.read_bytes()),
                    "robot_mask_path": label_path.name,
                    "robot_mask_sha256": mask_hash,
                    "robot_depth_path": depth_path.name,
                    "robot_depth_sha256": _sha256(depth_path.read_bytes()),
                    "semantic_info": semantic_info,
                    "official_mesh_pixels": cad_pixels,
                    **comparison,
                    "robot_depth_min_mm": int(robot_depth_mm[robot_depth_mm > 0].min()),
                    "robot_depth_max_mm": int(robot_depth_mm.max()),
                    "targets": labeled_targets,
                })
            if len(mask_hashes) != len(poses):
                raise RuntimeError("official mesh semantic masks are not pose-distinct")
        finally:
            for annotator in (rgb_annotator, semantic_annotator, depth_annotator):
                annotator.detach()
            render_product.destroy()
            rep.orchestrator.wait_until_complete()

        artifact_atlases: dict[str, dict[str, str]] = {}
        retained_atlas_paths: set[Path] = set()
        chunks = [
            pose_results[start:start + ATLAS_CHUNK_SIZE]
            for start in range(0, len(pose_results), ATLAS_CHUNK_SIZE)
        ]
        for chunk_index, chunk in enumerate(chunks):
            suffix = "" if len(chunks) == 1 else f"_{chunk_index:03d}"
            keys = {
                "rgb": f"rgb{suffix}",
                "robot_mask": f"robot_mask{suffix}",
                "robot_depth_mm": f"robot_depth_mm{suffix}",
            }
            paths = {
                "rgb": output_dir / f"official_mesh_rgb_atlas{suffix}.jpg",
                "robot_mask": output_dir / f"official_mesh_mask_atlas{suffix}.png",
                "robot_depth_mm": output_dir / f"official_mesh_depth_mm_atlas{suffix}.png",
            }
            atlas_columns, atlas_rows, atlas_boxes = _atlas_layout(len(chunk))
            rgb_atlas = np.zeros(
                (atlas_rows * HEIGHT, atlas_columns * WIDTH, 3), dtype=np.uint8,
            )
            mask_atlas = np.zeros(
                (atlas_rows * HEIGHT, atlas_columns * WIDTH), dtype=np.uint8,
            )
            depth_atlas = np.zeros(
                (atlas_rows * HEIGHT, atlas_columns * WIDTH), dtype=np.uint16,
            )
            for row, (left, top, right, bottom) in zip(
                    chunk, atlas_boxes, strict=True):
                rgb_atlas[top:bottom, left:right] = np.asarray(
                    Image.open(output_dir / row["rgb_path"]).convert("RGB")
                )
                mask_atlas[top:bottom, left:right] = np.asarray(
                    Image.open(output_dir / row["robot_mask_path"]).convert("L")
                )
                depth_atlas[top:bottom, left:right] = np.asarray(
                    Image.open(output_dir / row["robot_depth_path"]), dtype=np.uint16,
                )
            Image.fromarray(rgb_atlas).save(
                paths["rgb"], "JPEG", quality=92, optimize=False,
                progressive=False, subsampling=0,
            )
            Image.fromarray(mask_atlas).save(paths["robot_mask"], "PNG")
            Image.fromarray(depth_atlas).save(paths["robot_depth_mm"], "PNG")
            decoded_rgb = np.asarray(Image.open(paths["rgb"]).convert("RGB"))
            decoded_depth = np.asarray(
                Image.open(paths["robot_depth_mm"]), dtype=np.uint16,
            )
            for row, (left, top, right, bottom) in zip(
                    chunk, atlas_boxes, strict=True):
                for field in (
                    "rgb_path", "rgb_sha256", "robot_mask_path", "robot_mask_sha256",
                    "robot_depth_path", "robot_depth_sha256",
                ):
                    del row[field]
                row["rgb_atlas_key"] = keys["rgb"]
                row["atlas_crop_px"] = [left, top, right, bottom]
                row["rgb_crop_pixel_sha256"] = _sha256(
                    decoded_rgb[top:bottom, left:right].tobytes()
                )
                row["robot_mask_crop_pixel_sha256"] = _sha256(
                    mask_atlas[top:bottom, left:right].tobytes()
                )
                row["robot_depth_crop_pixel_sha256"] = _sha256(
                    decoded_depth[top:bottom, left:right].tobytes()
                )
            for kind, key in keys.items():
                artifact_atlases[key] = {
                    "path": paths[kind].name,
                    "sha256": _sha256(paths[kind].read_bytes()),
                }
                retained_atlas_paths.add(paths[kind])
        for path in output_dir.iterdir():
            if path not in retained_atlas_paths:
                path.unlink()

        comparable = [row for row in pose_results if row["capsule_comparison_available"]]
        receipt: dict[str, object] = {
            "schema": receipt_schema,
            "campaign": args.campaign,
            "evidence_class": "OFFICIAL_VISUAL_MESH_PERCEPTION_COMPARISON_ONLY",
            "upstream_commit": UPSTREAM_COMMIT,
            "governed_urdf_sha256": EXPECTED_URDF_SHA256,
            "mesh_receipt_file_sha256": _sha256(mesh_receipt_path.read_bytes()),
            "mesh_receipt_sha256": mesh_receipt["receipt_sha256"],
            "capsule_manifest_file_sha256": _sha256(capsule_manifest_path.read_bytes()),
            "capsule_corpus_sha256": capsule_manifest["corpus_sha256"],
            "schedule_bundle_file_sha256": expected_schedule_file_sha256,
            "schedule_bundle_sha256": schedule_bundle["bundle_sha256"],
            "pose_groups": {name: list(pose_ids) for name, pose_ids in pose_groups.items()},
            "target_catalog_sha256": context.targets.content_sha256,
            "camera": {
                "resolution_px": [WIDTH, HEIGHT],
                "position_board_m": [0.305, 0.2285, 0.5],
                "look_at_board_m": [0.305, 0.2285, 0.0],
                "focal_length_mm": 24.0,
                "horizontal_aperture_mm": 46.08,
                "nominal_fx_px": 1000.0,
                "fixed_across_poses": True,
            },
            "artifact_atlases": artifact_atlases,
            "pose_results": pose_results,
            "result_status": "PASS_WITH_BLOCKERS",
            "result_summary": {
                "minimum_mask_iou": min(
                    (row["mask_iou"] for row in comparable), default=None,
                ),
                "maximum_official_mesh_outside_capsule_pixels": max(
                    (row["official_mesh_outside_capsule_pixels"] for row in comparable),
                    default=None,
                ),
            },
            "visual_meshes_used_for_collision": False,
            "physics_steps": 0,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_movements": 0,
            "physical_authority": False,
            "limitations": [
                "official upstream visual meshes are perception geometry only",
                "render materials and lighting are synthetic",
                "camera and robot placement are nominal and unmeasured",
                "Isaac semantic rasterization does not establish collision clearance",
                "no tool or camera-support geometry is present",
            ],
        }
        receipt["receipt_sha256"] = _sha256(_canonical(receipt))
        args.receipt.write_bytes(_canonical(receipt) + b"\n")
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            "minimum_mask_iou": min(
                (row["mask_iou"] for row in comparable), default=None,
            ),
            "maximum_official_mesh_outside_capsule_pixels": max(
                (row["official_mesh_outside_capsule_pixels"] for row in comparable),
                default=None,
            ),
            "hardware_writes": 0,
            "physical_movements": 0,
        }, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
            "hardware_writes": 0, "physical_movements": 0,
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
