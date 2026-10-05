"""Continuous, tool-bound keycap clearance for the exploratory first-motion twin.

This module has no controller, transport, permit, or hardware adapter.  It
turns each fixed-orientation linear path segment into one convex swept volume
and computes its distance to convex key boxes with GJK.  Therefore a contact
between discrete samples cannot disappear by changing a sample spacing.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from rocell.geometry import RigidTransform, Vec3
from rocell_ai.first_motion_clearance_waypoints import (
    _World,
    _hand_board_transform,
    _solve_seeded,
    _tip_xyz,
    load_passive_tool_rerun_fixture,
    validate_pose_bundle_tool_configuration,
)

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def _sha(document: dict[str, Any]) -> str:
    import hashlib

    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _bound_path(binding: dict[str, Any], workspace: Path) -> Path:
    path = Path(binding["path"])
    return path if path.is_absolute() else workspace / path


def load_pose_family_result(path: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    """Load and revalidate every emitted pose/configuration pair."""

    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema") != "tactevra.tool_bound_pose_family_result.v1":
        raise ValueError("unexpected tool-bound pose-family schema")
    if result.get("fixture_sha256") != fixture["fixture_sha256"]:
        raise ValueError("pose-family result is bound to another fixture")
    unsigned = dict(result)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != _sha(unsigned):
        raise ValueError("pose-family result receipt mismatch")
    for profile in result["profiles"]:
        bundle = profile["pose_bundle"]
        validate_pose_bundle_tool_configuration(bundle, bundle["tool_configuration"])
        if profile["tool_configuration_sha256"] != bundle["tool_configuration_sha256"]:
            raise ValueError("profile and pose-bundle tool hashes differ")
    if any(result.get(name) for name in (
        "hardware_write_count", "physical_movement_count", "real_command_count",
        "permit_count", "transport_count",
    )) or result.get("physical_authority") is not False:
        raise ValueError("pose-family result carries authority")
    return result


def _transform_points(transform: Any, local_points: np.ndarray) -> np.ndarray:
    rows = []
    for xyz in local_points:
        point = transform.translation_mm + transform.rotation.apply(
            Vec3(float(xyz[0]), float(xyz[1]), float(xyz[2])))
        rows.append((point.x, point.y, point.z))
    return np.asarray(rows, dtype=float)


def _mesh_component_vertices(
    mesh_path: Path, *, start_mm: float, end_mm: float,
) -> np.ndarray:
    """Normalize a controlled mesh hull into its frozen axial assembly slot."""

    import trimesh

    mesh = trimesh.load_mesh(mesh_path, process=False).convex_hull
    vertices = np.asarray(mesh.vertices, dtype=float)
    low = vertices.min(axis=0)
    high = vertices.max(axis=0)
    span = high - low
    if not np.all(np.isfinite(vertices)) or span[2] <= 0:
        raise ValueError(f"invalid controlled convex hull: {mesh_path}")
    local = vertices.copy()
    local[:, 0] -= (low[0] + high[0]) / 2.0
    local[:, 1] -= (low[1] + high[1]) / 2.0
    axial = start_mm + ((vertices[:, 2] - low[2]) / span[2]) * (end_mm - start_mm)
    local[:, 2] = -axial
    return local


def _swept_vertices(
    local_vertices: np.ndarray, start_transform: Any, end_transform: Any,
) -> np.ndarray:
    return np.vstack((
        _transform_points(start_transform, local_vertices),
        _transform_points(end_transform, local_vertices),
    ))


def convex_sweep_box_distance_mm(
    local_vertices: np.ndarray, start_transform: Any, end_transform: Any,
    *, box_center_mm: tuple[float, float, float],
    box_size_mm: tuple[float, float, float], margin_mm: float = 0.0,
) -> float:
    """Return continuous distance from a translated convex shape to an AABB.

    The orientation at the two endpoints must be identical.  The convex hull
    of both endpoint vertex sets is exactly the swept volume of a convex shape
    under linear translation.  ``margin_mm`` expands it by a spherical radius,
    which represents the distal capsule without polygonal sampling.
    """

    from distance3d import colliders, gjk

    start_rotation = np.asarray(
        start_transform.rotation.matrix, dtype=float).reshape(3, 3)
    end_rotation = np.asarray(
        end_transform.rotation.matrix, dtype=float).reshape(3, 3)
    if not np.allclose(start_rotation, end_rotation, atol=1e-12, rtol=0.0):
        raise ValueError("continuous sweep requires fixed orientation")
    swept = colliders.ConvexHullVertices(
        np.ascontiguousarray(_swept_vertices(
            local_vertices, start_transform, end_transform)))
    if margin_mm:
        swept = colliders.Margin(swept, float(margin_mm))
    pose = np.eye(4)
    pose[:3, 3] = np.asarray(box_center_mm, dtype=float)
    box = colliders.Box(pose, np.asarray(box_size_mm, dtype=float))
    distance, _, _, _ = gjk.gjk(
        swept, box, tolerance=1e-10,
        max_distance_squared=float("inf"), sanity_check=float("inf"))
    if not math.isfinite(float(distance)):
        raise ValueError("nonfinite GJK distance")
    return float(distance)


def _translated_transform(transform: Any, tip_xyz: tuple[float, float, float],
                          tool_length: float):
    """Retain orientation while placing the distal axis end at ``tip_xyz``."""

    offset = transform.rotation.apply(Vec3(0.0, 0.0, tool_length))
    translation = Vec3(tip_xyz[0] + offset.x, tip_xyz[1] + offset.y,
                       tip_xyz[2] + offset.z)
    return RigidTransform(
        transform.parent_frame, transform.child_frame,
        transform.rotation, translation)


def _key_boxes(bundle: dict[str, Any], width: float, thickness: float):
    rows = []
    for pose in bundle["poses"]:
        xyz = pose["contact_target_board_mm"]
        rows.append({
            "target_id": pose["target_id"],
            "center": (xyz["x"], xyz["y"], xyz["z"] - thickness / 2.0),
            "size": (width, width, thickness),
        })
    return rows


def _component_shapes(
    fixture: dict[str, Any], workspace: Path, configuration: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    prior = json.loads(_bound_path(
        fixture["bindings"]["prior_fixture"], workspace).read_text(encoding="utf-8"))
    spec = prior["tool_component_model"]
    length = float(configuration["total_hand_tcp_to_tip_length_mm"])
    exposed = float(configuration["distal_tip_exposed_length_mm"])
    radius = float(configuration["distal_tip_radius_mm"])
    collar_length = float(spec["collar_axial_length_mm"][0])
    body_length = float(spec["body_axial_length_mm"][0])
    collar_end = max(0.0, length - exposed)
    collar_start = max(0.0, collar_end - collar_length)
    body_start = max(0.0, collar_start - body_length)
    collar = _mesh_component_vertices(
        _bound_path(fixture["bindings"]["stylus_collar_mesh"], workspace),
        start_mm=collar_start, end_mm=collar_end)
    body = _mesh_component_vertices(
        _bound_path(fixture["bindings"]["tool_body_mesh"], workspace),
        start_mm=body_start, end_mm=collar_start)
    distal_spine = np.asarray([
        (0.0, 0.0, -collar_end), (0.0, 0.0, -length)], dtype=float)
    return (
        {"component": "DISTAL_TIP", "vertices": distal_spine, "margin_mm": radius},
        {"component": "COLLAR", "vertices": collar, "margin_mm": 0.0},
        {"component": "BODY", "vertices": body, "margin_mm": 0.0},
    )


def run_continuous_key_clearance(
    fixture: dict[str, Any], pose_family: dict[str, Any], *, workspace: Path,
) -> dict[str, Any]:
    """Screen every reachable profile with continuous fixed-orientation sweeps."""

    prior_path = _bound_path(fixture["bindings"]["prior_fixture"], workspace)
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    passive_path = _bound_path(prior["bindings"]["prior_fixture"], workspace)
    passive = load_passive_tool_rerun_fixture(passive_path)
    design_path = _bound_path(passive["bindings"]["collision_design_fixture"], workspace)
    world = _World(json.loads(design_path.read_text(encoding="utf-8")), workspace)
    park_report = json.loads(_bound_path(
        prior["bindings"]["park_screen"], workspace).read_text(encoding="utf-8"))
    park_id = prior["stage_c"]["park_pose_id"]
    park_row = next(row for row in park_report["top_candidates"]
                    if row["pose_id"] == park_id)
    park = tuple(park_row["joint_positions_rad"][name]
                 for name in world.pose_bundle["joint_order"])

    widths = tuple(float(value) for value in prior["keycap_contact"][
        "keycap_width_height_mm"])
    thicknesses = tuple(float(value) for value in prior["keycap_contact"][
        "keycap_thickness_mm"])
    transit_heights = tuple(float(value) for value in prior["stage_c"][
        "transit_height_board_z_mm"])
    hover_heights = tuple(float(value) for value in prior["stage_c"][
        "hover_height_above_contact_mm"])
    thresholds = tuple(float(value) for value in fixture["continuous_geometry"][
        "minimum_clearance_mm_range"])

    profiles = []
    global_minimum = float("inf")
    for profile in pose_family["profiles"]:
        bundle = profile["pose_bundle"]
        config = bundle["tool_configuration"]
        validate_pose_bundle_tool_configuration(bundle, config)
        length = float(config["total_hand_tcp_to_tip_length_mm"])
        reach = pose_family["reach_by_length_mm"][str(length)]
        row = {
            "tool_configuration_sha256": bundle["tool_configuration_sha256"],
            "tool_length_mm": length,
            "tip_exposed_length_mm": config["distal_tip_exposed_length_mm"],
            "tip_radius_mm": config["distal_tip_radius_mm"],
            "reachable_target_count": reach["solved_target_count"],
            "failed_target_ids": reach["failed_target_ids"],
            "minimum_non_target_clearance_mm": None,
            "limiting_case": None,
            "threshold_pass": {str(value): False for value in thresholds},
        }
        if not reach["all_targets_reached"]:
            row["decision"] = "STOP_UNREACHABLE_TARGET"
            profiles.append(row)
            continue
        components = _component_shapes(fixture, workspace, config)
        minimum = float("inf")
        limiting = None
        boxes_by_shape = {
            (width, thickness): _key_boxes(bundle, width, thickness)
            for width in widths for thickness in thicknesses}
        for target in bundle["poses"]:
            target_id = target["target_id"]
            xyz_document = target["contact_target_board_mm"]
            contact_xyz = (float(xyz_document["x"]), float(xyz_document["y"]),
                           float(xyz_document["z"]))
            target_joints = tuple(float(value) for value in target["joint_positions_rad"])
            final_transform = _hand_board_transform(world, target_joints)
            park_tip = _tip_xyz(world, park, length)
            for transit_z in transit_heights:
                for hover in hover_heights:
                    hover_xyz = (contact_xyz[0], contact_xyz[1], contact_xyz[2] + hover)
                    hover_joints = _solve_seeded(
                        world, world.solver(length), hover_xyz, target_joints)
                    if hover_joints is None:
                        raise ValueError(f"hover IK failed after reach pass: {target_id}")
                    # The frozen path keeps the final approach orientation and
                    # translates the TCP through rise, transit, and descent.
                    safe_z = max(transit_z, park_tip[2], hover_xyz[2])
                    tip_points = (
                        park_tip,
                        (park_tip[0], park_tip[1], safe_z),
                        (hover_xyz[0], hover_xyz[1], safe_z),
                        hover_xyz,
                        contact_xyz,
                    )
                    phase_names = ("ASCEND", "TRANSIT", "DESCEND", "PRESS")
                    transforms = tuple(_translated_transform(
                        final_transform, point, length) for point in tip_points)
                    for segment_index, phase in enumerate(phase_names):
                        start_transform = transforms[segment_index]
                        end_transform = transforms[segment_index + 1]
                        for width in widths:
                            for thickness in thicknesses:
                                for key in boxes_by_shape[(width, thickness)]:
                                    for component in components:
                                        admitted = (
                                            phase == "PRESS"
                                            and key["target_id"] == target_id
                                            and component["component"] == "DISTAL_TIP")
                                        if admitted:
                                            continue
                                        distance = convex_sweep_box_distance_mm(
                                            component["vertices"], start_transform,
                                            end_transform, box_center_mm=key["center"],
                                            box_size_mm=key["size"],
                                            margin_mm=component["margin_mm"])
                                        if distance < minimum:
                                            minimum = distance
                                            limiting = {
                                                "requested_target_id": target_id,
                                                "key_id": key["target_id"],
                                                "phase": phase,
                                                "component": component["component"],
                                                "transit_height_mm": transit_z,
                                                "hover_height_mm": hover,
                                                "key_width_mm": width,
                                                "key_thickness_mm": thickness,
                                            }
        row["minimum_non_target_clearance_mm"] = minimum
        row["limiting_case"] = limiting
        row["threshold_pass"] = {str(value): minimum + 1e-9 >= value
                                  for value in thresholds}
        row["decision"] = ("PASS_ALL_CLEARANCE_THRESHOLDS" if all(
            row["threshold_pass"].values()) else "STOP_CLEARANCE_MARGIN")
        global_minimum = min(global_minimum, minimum)
        profiles.append(row)

    result = {
        "schema": "tactevra.tool_bound_continuous_key_clearance_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "pose_family_receipt_sha256": pose_family["receipt_sha256"],
        "method": fixture["continuous_geometry"]["distance_method"],
        "profiles": profiles,
        "profile_count": len(profiles),
        "global_minimum_non_target_clearance_mm": (
            global_minimum if math.isfinite(global_minimum) else None),
        "decision": ("PASS_EXPLORATORY_CONTINUOUS_KEY_CLEARANCE" if all(
            row["decision"] == "PASS_ALL_CLEARANCE_THRESHOLDS" for row in profiles)
            else "STOP_REACH_OR_CONTINUOUS_CLEARANCE"),
        "evaluation_opened": False,
        "gpu_job_count": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
        "limitations": [
            "Fixed final-approach orientation is frozen and does not prove a rotating sweep.",
            "Keycaps are ranged boxes and tool assembly transforms remain exploratory.",
            "Shared kinematics and controlled meshes establish simulation consistency, not physical accuracy.",
            "This keycap screen does not install or qualify workcell collision geometry.",
        ],
    }
    result["receipt_sha256"] = _sha(result)
    return result


__all__ = [
    "convex_sweep_box_distance_mm",
    "load_pose_family_result",
    "run_continuous_key_clearance",
]
