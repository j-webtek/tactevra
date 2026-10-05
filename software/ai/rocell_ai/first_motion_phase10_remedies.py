"""Frozen simulation-only follow-up for Phase 10 camera, pad, and cable findings."""
from __future__ import annotations

import hashlib
import importlib.util
from itertools import product
import json
import math
from pathlib import Path
from typing import Any

from rocell.targets.nominal import load_nominal_target_catalog

from rocell_ai.first_motion_clearance_waypoints import (
    _clearance_route,
    _joint_map,
    _pad_contract,
    _pad_variants,
    _solve_seeded,
    _tip_xyz,
    load_waypoint_fixture,
)
from rocell_ai.first_motion_collision_design import _World, _interpolate
from rocell_ai.first_motion_controller_emulator import SCOPE
from rocell_ai.first_motion_drills import load_collision_attribution_fixture


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_remedy_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("phase10 remedy fixture hash mismatch")
    value["fixture_sha256"] = claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("phase10 remedy fixture changed zero-authority scope")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if _file_sha(source) != binding["sha256"]:
            raise ValueError(f"bound remedy input changed: {source}")
    return value


def _bound_path(binding: dict[str, str], workspace: Path) -> Path:
    path = Path(binding["path"])
    return path if path.is_absolute() else workspace / path


def _park_values(fixture: dict[str, Any], workspace: Path) -> tuple[float, ...]:
    report = json.loads(_bound_path(fixture["bindings"]["park_screen"], workspace).read_text())
    pose_id = fixture["camera_screen"]["pose_id"]
    row = next(item for item in report["top_candidates"] if item["pose_id"] == pose_id)
    order = ("base_link_to_link1", "link1_to_link2", "link2_to_link3",
             "link3_to_link4", "link4_to_link5")
    return tuple(row["joint_positions_rad"][name] for name in order)


def _camera_screen(fixture: dict[str, Any], workspace: Path,
                   world: _World, park: tuple[float, ...]) -> dict[str, Any]:
    family = json.loads(_bound_path(fixture["bindings"]["camera_family"], workspace).read_text())
    height = json.loads(_bound_path(fixture["bindings"]["height_fixture"], workspace).read_text())
    projection_path = _bound_path(fixture["bindings"]["projection_implementation"], workspace)
    spec = importlib.util.spec_from_file_location("phase10_projection", projection_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("projection implementation unavailable")
    projection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(projection)
    catalog = load_nominal_target_catalog(
        workspace, _bound_path(fixture["bindings"]["target_catalog"], workspace))
    targets = sorted([*catalog.keyboard_targets.values(), *catalog.phone_targets.values()],
                     key=lambda row: (row.device, row.target_id))
    sensor = family["sensor_mode"]
    lens = family["lens_candidates"][0]
    width, image_height = sensor["width_px"], sensor["height_px"]
    intrinsics = projection._native_sensor_intrinsics(
        width, image_height, sensor["pixel_pitch_um"], lens["focal_length_mm"])
    center = height["camera"]["center_board_xy_mm"]
    radii = {"base_link": 32.0, "link1": 27.0, "link2": 25.0,
             "link3": 23.0, "link4": 21.0, "link5": 19.0,
             "gripper_link": 24.0, "hand_tcp": 10.0}
    transforms = world.model.forward_kinematics(_joint_map(world, park))
    points = {name: world.board_t_world.compose(value).translation_mm
              for name, value in transforms.items()}
    segments = [(points[joint.parent_link], points[joint.child_link],
                 radii.get(joint.child_link, 18.0), joint.child_link)
                for joint in world.model.joints]
    rows = []
    for camera_height in fixture["camera_screen"]["screening_heights_board_mm"]:
        for profile in family["distortion"]["screening_profiles"]:
            distortion = {name: profile[name] for name in ("k1", "k2", "p1", "p2", "k3")}
            polygons = []
            crops_in_frame = True
            targets_in_frame = True
            for target in targets:
                left, front, right, rear = target.safe_rectangle_board_mm
                polygon = [projection._project_nadir_board_point(
                    (x, y, target.center.z), center, camera_height, intrinsics, distortion,
                    width_px=width, height_px=image_height, board_y_to_image_v_sign=-1)[:2]
                    for x, y in ((left, front), (right, front), (right, rear), (left, rear))]
                polygons.append(polygon)
                targets_in_frame &= all(0 <= x <= width and 0 <= y <= image_height
                                        for x, y in polygon)
                box = projection._fixed_physical_crop_box(
                    (target.center.x, target.center.y, target.center.z), (48.0, 48.0),
                    center, camera_height, intrinsics, distortion, width_px=width,
                    height_px=image_height, board_y_to_image_v_sign=-1)["native_box_ltrb_px"]
                crops_in_frame &= 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= image_height
            projected = []
            for start, end, radius_mm, link in segments:
                a = projection._project_nadir_board_point(
                    (start.x, start.y, start.z), center, camera_height, intrinsics, distortion,
                    width_px=width, height_px=image_height, board_y_to_image_v_sign=-1)
                b = projection._project_nadir_board_point(
                    (end.x, end.y, end.z), center, camera_height, intrinsics, distortion,
                    width_px=width, height_px=image_height, board_y_to_image_v_sign=-1)
                radius_px = intrinsics["fx_px"] * radius_mm / min(a[2], b[2])
                projected.append((a, b, radius_px, link))
            clearances = [min(projection._capsule_polygon_clearance_px(
                a[:2], b[:2], radius, polygon) for a, b, radius, _ in projected)
                for polygon in polygons]
            limiting = min(range(len(clearances)), key=clearances.__getitem__)
            rows.append({"height_board_mm": camera_height,
                         "distortion_profile_id": profile["id"],
                         "all_targets_in_frame": bool(targets_in_frame),
                         "all_48_mm_crops_in_frame": bool(crops_in_frame),
                         "minimum_capsule_clearance_px": clearances[limiting],
                         "limiting_target": {"device": targets[limiting].device,
                                             "target_id": targets[limiting].target_id}})
    passed = all(row["all_targets_in_frame"] and row["all_48_mm_crops_in_frame"]
                 and row["minimum_capsule_clearance_px"] > 0 for row in rows)
    return {"pose_id": fixture["camera_screen"]["pose_id"], "target_count": len(targets),
            "rows": rows, "minimum_capsule_clearance_px": min(
                row["minimum_capsule_clearance_px"] for row in rows),
            "status": "PASS_EXPLORATORY_CAPSULE_SCREEN" if passed else "STOP_CAMERA_CLEARANCE"}


def _pad_screen(fixture: dict[str, Any], workspace: Path, world: _World,
                park: tuple[float, ...], *, variant_indexes: set[int] | None = None
                ) -> list[dict[str, Any]]:
    waypoint = load_waypoint_fixture(_bound_path(fixture["bindings"]["clearance_fixture"], workspace))
    design_path = _bound_path(waypoint["bindings"]["collision_design_fixture"], workspace)
    design = json.loads(design_path.read_text())
    attribution_path = _bound_path(design["bindings"]["attribution_fixture"], workspace)
    expected = set(load_collision_attribution_fixture(attribution_path)[
        "contact_classes"]["DECLARED_EXPECTED_BUT_UNREVIEWED"])
    cable = design["cable_design"]
    include_moving_cable = fixture.get("attachment_configuration", {}).get(
        "moving_cable_present", True)
    cables = list(product(cable["anchor_board_x_mm_range"],
                          cable["anchor_height_board_z_mm_range"],
                          cable["maximum_sag_fraction_range"],
                          cable["cable_radius_mm_range"])) if include_moving_cable else [None]
    tools = list(product(world.section["tool"]["length_mm_range"],
                         world.section["tool"]["radius_mm_range"]))
    spec = waypoint["waypoint_study"]
    pad_spec = waypoint["swappable_pad"]
    tool_pad = pad_spec["expected_contact_pair"]
    modes = fixture["pad_contact"]["modes"]
    totals_by_mode = {mode: {"evaluations": 0, "concerning": 0,
                             "tool_pad_contacts": 0,
                             "noncontiguous_contact_sequences": 0, "pairs": {}}
                      for mode in modes}
    removed = {"workcell:station:keyboard_left", "workcell:station:keyboard_right"}
    pads = _pad_variants(pad_spec)
    fixed_top_z = fixture["pad_contact"].get("fixed_top_board_z_mm")
    if fixed_top_z is not None:
        pads = [{**pad, "top_z_mm": fixed_top_z} for pad in pads]
    for pad_index, pad in enumerate(pads):
        if variant_indexes is not None and pad_index not in variant_indexes:
            continue
        for tool_length, tool_radius in tools:
            contract = _pad_contract(world, tool_length=tool_length,
                                     tool_radius=tool_radius, pad=pad, spec=pad_spec,
                                     include_moving_cable=include_moving_cable)
            center = pad_spec["center_board_xy_mm"]
            for hover, approach, depth in product(
                    pad_spec["hover_mm_range"], pad_spec["approach_mm_range"],
                    pad_spec["contact_depth_mm_range"]):
                points = ((center[0], center[1], pad["top_z_mm"] + hover),
                          (center[0], center[1], pad["top_z_mm"] + approach),
                          (center[0], center[1], pad["top_z_mm"] - depth))
                solver = world.solver(tool_length)
                solved = []
                seed = park
                for point in points:
                    value = _solve_seeded(world, solver, point, seed)
                    if value is None:
                        solved = []
                        break
                    solved.append(value)
                    seed = value
                if len(solved) != 3:
                    for totals in totals_by_mode.values():
                        totals["concerning"] += 1
                    continue
                transit, failure = _clearance_route(
                    world, start=park, end=solved[0], end_xyz=points[0],
                    tool_length=tool_length,
                    transit_z=spec["transit_height_board_z_mm_range"][1],
                    samples=spec["samples_per_cartesian_leg"])
                if failure:
                    for totals in totals_by_mode.values():
                        totals["concerning"] += 1
                    continue
                labelled = list(transit)
                labelled += [("APPROACH", row) for row in _interpolate(
                    solved[0], solved[1], spec["samples_per_cartesian_leg"])]
                labelled += [("NOMINAL_PRESS", row) for row in _interpolate(
                    solved[1], solved[2], spec["samples_per_cartesian_leg"])]
                labelled += [("RETRACT", row) for row in _interpolate(
                    solved[2], solved[0], spec["samples_per_cartesian_leg"])]
                for cable_endpoint in cables:
                    sequence = [world.evaluate(contract, joints, cable_endpoint)
                                for _, joints in labelled]
                    for mode in modes:
                        totals = totals_by_mode[mode]
                        filtered = sequence
                        if mode == "TRAY_REPLACES_KEYBOARD_AND_NEIGHBOR_STATIONS":
                            filtered = [{pair for pair in pairs if not any(
                                station in pair.split("|") for station in removed)}
                                        for pairs in sequence]
                        contact_indices = [index for index, pairs in enumerate(filtered)
                                           if tool_pad in pairs]
                        if contact_indices:
                            contiguous = contact_indices == list(range(
                                contact_indices[0], contact_indices[-1] + 1))
                            totals["noncontiguous_contact_sequences"] += int(not contiguous)
                        for index, pairs in enumerate(filtered):
                            totals["evaluations"] += 1
                            totals["tool_pad_contacts"] += int(tool_pad in pairs)
                            concerning = set(pairs) - expected
                            if index in contact_indices:
                                concerning.discard(tool_pad)
                            totals["concerning"] += int(bool(concerning))
                            for pair in concerning:
                                totals["pairs"][pair] = totals["pairs"].get(pair, 0) + 1
    output = []
    for mode in modes:
        totals = totals_by_mode[mode]
        clear = totals["concerning"] == 0 and totals["noncontiguous_contact_sequences"] == 0
        output.append({"mode": mode, **totals,
                       "status": "CLEAR_EXPLORATORY_DISCRETE" if clear else "STOP"})
    return output


def _wrist_screen(fixture: dict[str, Any], workspace: Path, world: _World,
                  park: tuple[float, ...]) -> list[dict[str, Any]]:
    waypoint = load_waypoint_fixture(_bound_path(fixture["bindings"]["clearance_fixture"], workspace))
    design_path = _bound_path(waypoint["bindings"]["collision_design_fixture"], workspace)
    design = json.loads(design_path.read_text())
    cable = design["cable_design"]
    cables = list(product(cable["anchor_board_x_mm_range"],
                          cable["anchor_height_board_z_mm_range"],
                          cable["maximum_sag_fraction_range"],
                          cable["cable_radius_mm_range"]))
    tools = list(product(world.section["tool"]["length_mm_range"],
                         world.section["tool"]["radius_mm_range"]))
    target = next(row for row in world.pose_bundle["poses"]
                  if row["target_id"] == fixture["stage_c_wrist"]["target_id"])
    contact = target["contact_target_board_mm"]
    hover = waypoint["waypoint_study"]["hover_height_above_contact_mm_range"][1]
    target_xyz = (contact["x"], contact["y"], contact["z"] + hover)
    pair = "attachment:moving_cable|robot:link4"
    output = []
    for mode in fixture["stage_c_wrist"]["modes"]:
        row = {"mode": mode, "evaluations": 0, "cable_link4_findings": 0,
               "ik_failures": 0, "endpoint_errors_mm": [], "error_band_counts": {}}
        for tool_length, tool_radius in tools:
            end = _solve_seeded(world, world.solver(tool_length), target_xyz, park)
            if end is None:
                row["ik_failures"] += 1
                continue
            contract = world.contract(tool_length=tool_length, tool_radius=tool_radius, pad=None)
            for transit_z in waypoint["waypoint_study"]["transit_height_board_z_mm_range"]:
                route, failure = _clearance_route(
                    world, start=park, end=end, end_xyz=target_xyz,
                    tool_length=tool_length, transit_z=transit_z,
                    samples=waypoint["waypoint_study"]["samples_per_cartesian_leg"])
                if failure:
                    row["ik_failures"] += 1
                    continue
                descent = [(phase, joints) for phase, joints in route if phase == "DESCEND"]
                start = descent[0][1]
                modified = []
                for _, joints in descent:
                    values = list(joints)
                    if mode in ("FIX_WRIST_PITCH", "FIX_BOTH_WRIST_JOINTS"):
                        values[3] = start[3]
                    if mode in ("FIX_WRIST_ROLL", "FIX_BOTH_WRIST_JOINTS"):
                        values[4] = start[4]
                    modified.append(tuple(values))
                endpoint = _tip_xyz(world, modified[-1], tool_length)
                error = math.dist(endpoint, target_xyz)
                row["endpoint_errors_mm"].append(error)
                for band in fixture["stage_c_wrist"]["absolute_final_tool_error_bands_mm"]:
                    key = str(band)
                    row["error_band_counts"][key] = row["error_band_counts"].get(key, 0) + int(error <= band)
                for cable_endpoint in cables:
                    for joints in modified:
                        row["evaluations"] += 1
                        row["cable_link4_findings"] += int(pair in world.evaluate(
                            contract, joints, cable_endpoint))
        row["maximum_endpoint_error_mm"] = max(row["endpoint_errors_mm"], default=None)
        row["minimum_endpoint_error_mm"] = min(row["endpoint_errors_mm"], default=None)
        output.append(row)
    return output


def run_phase10_remedy_audit(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    waypoint = load_waypoint_fixture(_bound_path(fixture["bindings"]["clearance_fixture"], workspace))
    design = json.loads(_bound_path(
        waypoint["bindings"]["collision_design_fixture"], workspace).read_text())
    world = _World(design, workspace)
    park = _park_values(fixture, workspace)
    result = {
        "schema": "tactevra.first_motion_phase10_remedy_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "camera_screen": _camera_screen(fixture, workspace, world, park),
        "pad_contact_screen": _pad_screen(fixture, workspace, world, park),
        "stage_c_wrist_screen": _wrist_screen(fixture, workspace, world, park),
        "installed_geometry_changed": False,
        "motion_policy_installed": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


def run_phase10_pad_partition(fixture: dict[str, Any], *, workspace: Path,
                              variant_indexes: set[int]) -> dict[str, Any]:
    """Run an execution partition without changing the frozen matrix."""
    waypoint = load_waypoint_fixture(
        _bound_path(fixture["bindings"]["clearance_fixture"], workspace))
    design = json.loads(_bound_path(
        waypoint["bindings"]["collision_design_fixture"], workspace).read_text())
    world = _World(design, workspace)
    park = _park_values(fixture, workspace)
    result = {
        "schema": "tactevra.first_motion_phase10_pad_partition.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "variant_indexes": sorted(variant_indexes),
        "pad_contact_screen": _pad_screen(
            fixture, workspace, world, park, variant_indexes=variant_indexes),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


def run_phase10_nonpad(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    waypoint = load_waypoint_fixture(
        _bound_path(fixture["bindings"]["clearance_fixture"], workspace))
    design = json.loads(_bound_path(
        waypoint["bindings"]["collision_design_fixture"], workspace).read_text())
    world = _World(design, workspace)
    park = _park_values(fixture, workspace)
    result = {
        "schema": "tactevra.first_motion_phase10_nonpad_partition.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "camera_screen": _camera_screen(fixture, workspace, world, park),
        "stage_c_wrist_screen": _wrist_screen(fixture, workspace, world, park),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


__all__ = ["load_remedy_fixture", "run_phase10_nonpad", "run_phase10_pad_partition",
           "run_phase10_remedy_audit"]
