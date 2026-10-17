"""Derive source-bound candidate collision envelopes without installation authority."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any


SCHEMA = "rocell.static_overhead_collision_candidate_envelopes.v1"
STATUS = "CANDIDATE_ENVELOPES_DERIVED_PLACEMENT_AND_UNCERTAINTY_REVIEW_PENDING"
WORK_ORDER_SCHEMA = "rocell.static_overhead_collision_qualification_work_order.v1"
WORK_ORDER_STATUS = "READY_FOR_REVIEWED_QUALIFICATION_ZERO_AUTHORITY"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_work_order(path: Path, file_sha256: str) -> dict[str, Any]:
    if _file_sha(path) != file_sha256:
        raise ValueError("work order file hash mismatch")
    value = _load_json(path)
    if value.get("schema") != WORK_ORDER_SCHEMA or value.get("status") != WORK_ORDER_STATUS:
        raise ValueError("work order schema or status mismatch")
    claimed = value.get("work_order_sha256")
    core = {key: item for key, item in value.items() if key != "work_order_sha256"}
    if claimed != _sha(core):
        raise ValueError("work order canonical hash mismatch")
    rows = value.get("body_qualification_work")
    if not isinstance(rows, list) or len(rows) != 19:
        raise ValueError("work order must contain exactly 19 body rows")
    return value


def _mesh_points(path: Path) -> list[tuple[float, float, float]]:
    data = path.read_bytes()
    points: list[tuple[float, float, float]] = []
    if len(data) >= 84:
        triangle_count = struct.unpack("<I", data[80:84])[0]
        if 84 + triangle_count * 50 == len(data):
            for index in range(triangle_count):
                start = 84 + index * 50
                values = struct.unpack("<12fH", data[start : start + 50])
                points.extend((values[3:6], values[6:9], values[9:12]))
            return points
    for line in data.decode("ascii", errors="ignore").splitlines():
        fields = line.strip().split()
        if len(fields) == 4 and fields[0].lower() == "vertex":
            points.append(tuple(float(item) for item in fields[1:4]))
    if not points:
        raise ValueError(f"STL contains no vertices: {path}")
    return points


def _bounds(points: list[tuple[float, float, float]]) -> dict[str, list[float]]:
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    return {
        "minimum_mm": [round(item, 6) for item in minimum],
        "maximum_mm": [round(item, 6) for item in maximum],
        "size_mm": [round(maximum[i] - minimum[i], 6) for i in range(3)],
    }


def _stl_bounds(path: Path) -> dict[str, list[float]]:
    return _bounds(_mesh_points(path))


def _union_bounds(items: list[dict[str, list[float]]]) -> dict[str, list[float]]:
    points = []
    for item in items:
        points.extend((tuple(item["minimum_mm"]), tuple(item["maximum_mm"])))
    return _bounds(points)


def _box(origin: list[float], size: list[float]) -> dict[str, list[float]]:
    return {
        "minimum_mm": [round(item, 6) for item in origin],
        "maximum_mm": [round(origin[i] + size[i], 6) for i in range(3)],
        "size_mm": [round(item, 6) for item in size],
    }


def _candidate_box_corners(primitive: dict[str, Any]) -> list[tuple[float, float, float]]:
    center = primitive["center_mm"]
    half = primitive["half_extents_mm"]
    rotation = primitive["rotation_row_major"]
    if len(center) != 3 or len(half) != 3 or len(rotation) != 9:
        raise ValueError("invalid candidate oriented box")
    corners = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                local = [sx * half[0], sy * half[1], sz * half[2]]
                rotated = [
                    sum(rotation[row * 3 + col] * local[col] for col in range(3))
                    for row in range(3)
                ]
                point = tuple(center[axis] + rotated[axis] for axis in range(3))
                if not all(math.isfinite(item) for item in point):
                    raise ValueError("candidate oriented box contains non-finite coordinates")
                corners.append(point)
    return corners


def _source(path: Path, workspace: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(workspace).as_posix(),
        "byte_length": path.stat().st_size,
        "sha256": _file_sha(path),
    }


def build_static_overhead_collision_candidate_envelopes_v1(
    workspace: Path,
    work_order_path: Path,
    work_order_file_sha256: str,
) -> dict[str, Any]:
    """Derive reproducible candidate bounds while leaving installation gates closed."""

    workspace = workspace.resolve()
    work_order = _load_work_order(work_order_path, work_order_file_sha256)
    paths = {
        "robot": workspace / "software/integrations/isaac_sim/evidence/roarm_m3_link_mesh_reduction_20260929.json",
        "layout": workspace / "active-project/RoCell_v0_3/config/workcell_layout.json",
        "support": workspace / "hardware/static_overhead_camera/config/support_design.json",
        "portal": workspace / "hardware/static_overhead_camera/cad/output/assembly/printable_camera_portal_printed_parts_only.stl",
        "cage": workspace / "hardware/static_overhead_camera/cad/output/stl/camera_cage_body.stl",
        "keeper": workspace / "hardware/static_overhead_camera/cad/output/stl/camera_cage_keeper.stl",
        "connector": workspace / "hardware/static_overhead_camera/cad/output/revisions/08D-C2_usb_keeper_v1/08D-C2_ABS_USB_clearance_keeper_v1.stl",
        "keyboard_left": workspace / "active-project/RoCell_v0_3/stl/keyboard_station_left.stl",
        "keyboard_right": workspace / "active-project/RoCell_v0_3/stl/keyboard_station_right.stl",
        "phone_tcp": workspace / "active-project/RoCell_v0_3/stl/phone_tcp_station.stl",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError(f"candidate source file missing: {missing[0]}")

    robot = _load_json(paths["robot"])
    layout = _load_json(paths["layout"])
    support = _load_json(paths["support"])
    work_ids = [row["body_id"] for row in work_order["body_qualification_work"]]
    if len(set(work_ids)) != 19:
        raise ValueError("work order body IDs must be unique")

    rows: dict[str, dict[str, Any]] = {}
    links = robot.get("links")
    if not isinstance(links, list) or len(links) != 7:
        raise ValueError("robot reduction must contain seven links")
    for link in links:
        body_name = "gripper" if link["link_name"] == "gripper_link" else link["link_name"]
        body_id = f"robot:{body_name}"
        points = []
        for component in link["components"]:
            points.extend(_candidate_box_corners(component["candidate_primitive"]))
        rows[body_id] = {
            "body_id": body_id,
            "candidate_state": "LOCAL_LINK_FRAME_ENVELOPE_DERIVED",
            "frame": link["link_name"],
            "envelope": _bounds(points),
            "primitive_count": len(link["components"]),
            "candidate_placement_available": False,
            "uncertainty_available": False,
            "remaining_requirements": [
                "review whole-link coverage and non-watertight source components",
                "accept installed base transform and placement uncertainty",
                "accept geometry uncertainty and false-positive behavior",
            ],
        }

    board = layout["board"]
    rows["workcell:board_solid"] = {
        "body_id": "workcell:board_solid",
        "candidate_state": "BOARD_FRAME_ENVELOPE_DERIVED_FROM_RETAINED_DIMENSIONS",
        "frame": "B",
        "envelope": _box([0.0, 0.0, board["bottom_surface_z"]], [board["width"], board["depth"], board["thickness"]]),
        "candidate_placement_available": True,
        "uncertainty_available": False,
        "repeat_dimension_measurement_requested": False,
        "remaining_requirements": ["accept board-frame datum and installed uncertainty"],
    }
    for device_name in ("keyboard", "phone"):
        device = layout["devices"][device_name]
        size_key = "nominal_size" if device_name == "keyboard" else "configured_size"
        rows[f"workcell:{device_name}"] = {
            "body_id": f"workcell:{device_name}",
            "candidate_state": "BOARD_FRAME_ENVELOPE_DERIVED_FROM_RETAINED_DIMENSIONS",
            "frame": "B",
            "envelope": _box([*device["nominal_origin_xy"], device["support_plane_z"]], device[size_key]),
            "candidate_placement_available": True,
            "uncertainty_available": False,
            "repeat_dimension_measurement_requested": False,
            "remaining_requirements": ["accept installed placement and uncertainty"],
        }

    for station_name in ("keyboard_left", "keyboard_right", "phone_tcp"):
        station = layout["stations"][station_name]
        local = _stl_bounds(paths[station_name])
        origin = [*station["origin_xy"], station["installed_z"]]
        rows[f"workcell:station:{station_name}"] = {
            "body_id": f"workcell:station:{station_name}",
            "candidate_state": "BOARD_FRAME_ENVELOPE_DERIVED_FROM_CONTROLLED_STL",
            "frame": "B",
            "local_envelope": local,
            "envelope": _box(origin, local["size_mm"]),
            "candidate_placement_available": True,
            "uncertainty_available": False,
            "remaining_requirements": ["verify installed article and accept placement uncertainty"],
        }

    portal = _stl_bounds(paths["portal"])
    rows["installation:static_camera_support"] = {
        "body_id": "installation:static_camera_support",
        "candidate_state": "BOARD_FRAME_CAD_ENVELOPE_DERIVED",
        "frame": "B",
        "envelope": portal,
        "candidate_placement_available": True,
        "uncertainty_available": False,
        "remaining_requirements": ["verify installed support revision and accept placement and geometry uncertainty"],
    }
    rows["installation:static_camera_module"] = {
        "body_id": "installation:static_camera_module",
        "candidate_state": "LOCAL_CAGE_FRAME_ENVELOPE_DERIVED",
        "frame": "CAMERA_CAGE_LOCAL",
        "envelope": _union_bounds([_stl_bounds(paths["cage"]), _stl_bounds(paths["keeper"])]),
        "candidate_placement_available": False,
        "uncertainty_available": False,
        "remaining_requirements": ["bind the received camera/cage installed transform", "accept geometry and placement uncertainty"],
    }
    rows["installation:static_camera_connector"] = {
        "body_id": "installation:static_camera_connector",
        "candidate_state": "LOCAL_CONNECTOR_FRAME_ENVELOPE_DERIVED",
        "frame": "CAMERA_CONNECTOR_LOCAL",
        "envelope": _stl_bounds(paths["connector"]),
        "candidate_placement_available": False,
        "uncertainty_available": False,
        "remaining_requirements": ["bind the installed connector transform", "accept geometry and placement uncertainty"],
    }
    rows["installation:base_and_factory_clamp"] = {
        "body_id": "installation:base_and_factory_clamp",
        "candidate_state": "ENVELOPE_PENDING",
        "candidate_placement_available": False,
        "uncertainty_available": False,
        "remaining_requirements": ["record a conservative installed base-and-clamp envelope", "accept board-frame placement and uncertainty"],
    }
    rows["installation:static_camera_cable"] = {
        "body_id": "installation:static_camera_cable",
        "candidate_state": "FLEXIBLE_ENVELOPE_PENDING",
        "candidate_placement_available": False,
        "uncertainty_available": False,
        "remaining_requirements": ["record the fixed cable occupied region and routing variability"],
    }
    rows["attachment:contact_tool"] = {
        "body_id": "attachment:contact_tool",
        "candidate_state": "BARE_JAW_ABSENCE_DECLARATION_PENDING_ACCEPTANCE",
        "attachment_profile": "BARE_JAW",
        "candidate_placement_available": False,
        "uncertainty_available": False,
        "remaining_requirements": ["accept that BARE_JAW has no contact-tool body", "qualify every future stylus as a separate attachment profile"],
    }
    if set(rows) != set(work_ids):
        raise ValueError("derived body roster does not match work order")

    ordered = [rows[body_id] for body_id in work_ids]
    envelope_count = sum("envelope" in row for row in ordered)
    placement_count = sum(row["candidate_placement_available"] for row in ordered)
    uncertainty_count = sum(row["uncertainty_available"] for row in ordered)
    source_bindings = [_source(path, workspace) for path in paths.values()]
    source_bindings.sort(key=lambda item: item["path"])
    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "work_order_file_sha256": work_order_file_sha256,
        "work_order_sha256": work_order["work_order_sha256"],
        "source_bindings": source_bindings,
        "support_design_state": support["state"],
        "required_body_count": len(ordered),
        "candidate_envelope_body_count": envelope_count,
        "candidate_board_or_link_frame_placement_body_count": placement_count,
        "accepted_uncertainty_body_count": uncertainty_count,
        "body_candidates": ordered,
        "bodies_without_candidate_envelope": [row["body_id"] for row in ordered if "envelope" not in row],
        "bodies_without_candidate_placement": [row["body_id"] for row in ordered if not row["candidate_placement_available"]],
        "bodies_without_accepted_uncertainty": [row["body_id"] for row in ordered if not row["uncertainty_available"]],
        "repeat_dimension_measurement_body_ids": [],
        "installed_profile_eligible": False,
        "profile_generated": False,
        "collision_screening_executed": False,
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
        "next_required_stage": "REVIEW_INSTALLED_PLACEMENTS_AND_ASSIGN_CONSERVATIVE_UNCERTAINTIES",
    }
    return {**core, "report_sha256": _sha(core)}


__all__ = ["SCHEMA", "STATUS", "build_static_overhead_collision_candidate_envelopes_v1"]
