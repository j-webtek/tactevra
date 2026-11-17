"""Audit the pinned SPACE source route with offline URDF kinematics, not Isaac."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import scipy
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/src"))

from nominal_route_component_obb_clearance import check_continuous_self_clearance
from nominal_route_native_component_obb_binding import (
    EXPECTED_DOF_NAMES,
    NATIVE_LINKS,
    NativeComponentObbRuntime,
    _sha,
    build_definition,
)
from rocell.geometry.urdf import JointPosition, UrdfModel

ROUTE_SHA256 = "d22fffa61b4d481e8c90956828c3c2a58634e9408108f00a2521501e331c0449"
EPISODE = "episode-ef340d0ad2740c118d87"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signed(core: dict, key: str) -> dict:
    data = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {**core, key: hashlib.sha256(data).hexdigest()}


class _OfflineArticulation:
    """Implement the narrow link-view protocol using offline URDF FK."""

    dof_names = EXPECTED_DOF_NAMES
    link_names = NATIVE_LINKS

    def __init__(self, urdf: Path) -> None:
        self.model = UrdfModel.from_file(urdf)
        self.positions = None

    def set_dof_positions(self, rows):
        self.positions = rows[0]

    def get_link_transforms(self):
        transforms = self.model.forward_kinematics({
            name: JointPosition.radians(value)
            for name, value in zip(self.dof_names, self.positions)
        })
        result = []
        for name in self.link_names:
            transform = transforms[name]
            translation = transform.translation_mm
            matrix = transform.rotation.matrix
            quaternion = Rotation.from_matrix([matrix[i:i + 3] for i in (0, 3, 6)]).as_quat()
            result.append([translation.x / 1000, translation.y / 1000,
                           translation.z / 1000, *quaternion.tolist()])
        return [result]


def _verify_whole_component_inventory(definition: dict, reduction: dict) -> None:
    """Ensure every offline box is exactly the pinned whole-component box."""
    expected = {}
    for row in reduction["links"]:
        for component in row["components"]:
            box = component["candidate_primitive"]
            if box.get("kind") != "oriented_box" or component["maximum_vertex_overflow_mm"] != 0.0:
                raise ValueError("whole-component box containment changed")
            key = (row["link_name"], component["component_index"])
            if key in expected:
                raise ValueError("duplicate whole-component box")
            expected[key] = (box["center_mm"], box["rotation_row_major"], box["half_extents_mm"])
    actual = {}
    for component in definition["component_obbs"]:
        key = (component["native_link_name"], int(component["primitive_name"].rsplit(":", 1)[1]))
        if key in actual:
            raise ValueError("duplicate candidate box")
        actual[key] = (component["local_center_mm"], component["local_rotation_row_major"],
                       component["half_extents_mm"])
    if len(expected) != 14 or actual != expected:
        raise ValueError("whole-component box inventory differs from reduction")


def _regenerated_rows(route: dict, artifacts: Path) -> tuple[list, dict]:
    from nominal_route_arm298_continuity_qualification import (
        EXPECTED_ADAPTER_FILE_SHA256, EXPECTED_ADAPTER_REVIEW_FILE_SHA256,
        _production_runtime, evaluate_route_continuity,
    )

    definition = artifacts / "arm267-canonical-ik-row-adapter-001/adapter.json"
    review = artifacts / "arm267-canonical-ik-row-adapter-review-001/review.json"
    if (_file_sha(definition) != EXPECTED_ADAPTER_FILE_SHA256
            or _file_sha(review) != EXPECTED_ADAPTER_REVIEW_FILE_SHA256):
        raise ValueError("canonical IK adapter evidence changed")
    solver = _production_runtime(ROOT, json.loads(definition.read_bytes()), json.loads(review.read_bytes()))
    rows = list(route["joint_targets"])

    class RecordingSolver:
        def regenerate_row(self, **kwargs):
            result = solver.regenerate_row(**kwargs)
            rows[result["sequence"]] = dict(result)
            return result

    continuity = evaluate_route_continuity(route, RecordingSolver())
    expected = "7d5b329e0a29a308f5e4fa9e42a3d4f9173560a61b32fd8d09795102d946919c"
    if continuity["canonical_rows_sha256"] != expected:
        raise ValueError("canonical IK rows differ from retained ARM-298 qualification")
    return rows, continuity


def _workcell_boxes(route: dict, layout: dict, urdf: Path):
    """Express board-coordinate obstacles in the URDF world used by offline FK."""
    import numpy as np
    from nominal_route_component_obb_clearance import OrientedBoxIntervalBound

    board_from_base = np.array(route["robot_placement_matrix_row_major"]).reshape(4, 4)
    model = UrdfModel.from_file(urdf)
    base = model.forward_kinematics({name: JointPosition.radians(0.0) for name in EXPECTED_DOF_NAMES})["base_link"]
    world_from_base = np.eye(4)
    world_from_base[:3, :3] = np.array(base.rotation.matrix).reshape(3, 3)
    t = base.translation_mm
    world_from_base[:3, 3] = [t.x, t.y, t.z]
    world_from_board = world_from_base @ np.linalg.inv(board_from_base)

    def box(name, lower, size):
        half = np.array(size) / 2
        center = world_from_board @ np.append(np.array(lower) + half, 1.0)
        return OrientedBoxIntervalBound(name, name, tuple(center[:3]),
                                        tuple(world_from_board[:3, :3].flat), tuple(half), 0.0)

    board = layout["board"]
    keyboard = layout["devices"]["keyboard"]
    return (
        box("board", (0, 0, board["bottom_surface_z"]),
            (board["width"], board["depth"], board["thickness"])),
        box("keyboard_envelope", (*keyboard["nominal_origin_xy"], keyboard["support_plane_z"]),
            keyboard["nominal_size"]),
    )


def _screen_workcell(runtime, rows, obstacles, sequences=range(653, 941)):
    from nominal_route_component_obb_clearance import _separating_axis_gap_mm

    results = {box.link_name: {"segments_screened": 0, "segments_unresolved": 0} for box in obstacles}
    for sequence in sequences:
        moving = runtime.bound_link_obbs(
            start_joint_targets_rad=rows[sequence]["joint_position_target_rad"],
            end_joint_targets_rad=rows[sequence + 1]["joint_position_target_rad"],
        )
        for obstacle in obstacles:
            residual, primitive = min(
                (_separating_axis_gap_mm(part, obstacle) - part.max_point_path_deviation_mm,
                 part.primitive_name) for part in moving
            )
            result = results[obstacle.link_name]
            result["segments_screened"] += 1
            result["segments_unresolved"] += int(residual <= 0.5)
            if residual < result.get("minimum_interval_bound_mm", float("inf")):
                result.update(minimum_interval_bound_mm=residual, limiting_primitive=primitive,
                              limiting_segment=[sequence, sequence + 1])
    return results


def _screen_tip(route, rows, urdf, profile_path, layout_path):
    """Evaluate commanded tip samples using the episode's own virtual tool."""
    import numpy as np
    from nominal_route_concrete_native_attempt_binding import EXPECTED_LAYOUT_SHA256

    if (_file_sha(profile_path) != route["runtime_files"]["virtual_profile"]["sha256"]
            or _file_sha(layout_path) != EXPECTED_LAYOUT_SHA256):
        raise ValueError("tip screen profile or key layout digest changed")
    profile = json.loads(profile_path.read_bytes())
    study = profile["study_input"]
    placement = study["physical_placement_input"]["matrix_row_major"]
    if not np.allclose(placement, route["robot_placement_matrix_row_major"], rtol=0, atol=1e-12):
        raise ValueError("virtual profile and episode base placements disagree")
    if tuple(route["joint_order"]) != tuple(EXPECTED_DOF_NAMES):
        raise ValueError("tip screen joint order changed")
    board_from_world = np.array(study["derived_solver_transform"]["matrix_row_major"]).reshape(4, 4)
    length = study["route_tool_lengths_mm"]["keyboard"]
    top = json.loads(layout_path.read_bytes())["keyboard"]["target_plane_z_board_mm"]
    center = route["randomized_key_center_board_xy_mm"]
    half = route["target_region"]["half_extent_mm"]
    model = UrdfModel.from_file(urdf)
    endpoints = []
    ranges = []
    for joint_row, source in zip(rows, route["joint_targets"], strict=True):
        joints = joint_row["joint_position_target_rad"]
        state = {name: JointPosition.radians(q) for name, q in zip(EXPECTED_DOF_NAMES, joints, strict=True)}
        hand = model.forward_kinematics(state)["hand_tcp"]
        t = hand.translation_mm
        z_axis = np.array(hand.rotation.matrix).reshape(3, 3)[:, 2]
        world = np.array([t.x, t.y, t.z]) - length * z_axis
        x, y, z, _ = board_from_world @ np.append(world, 1.0)
        gap = float(z - top)
        inside = bool(abs(x - center[0]) <= half[0] and abs(y - center[1]) <= half[1])
        sequence, phase = source["sequence"], source["phase"]
        if not ranges or ranges[-1]["phase"] != phase:
            ranges.append(dict(phase=phase, first=sequence, min_gap_mm=gap, max_gap_mm=gap))
        span = ranges[-1]
        span.update(last=sequence, min_gap_mm=min(gap, span["min_gap_mm"]),
                    max_gap_mm=max(gap, span["max_gap_mm"]))
        if sequence in route["contact_endpoint_sequences"]:
            endpoints.append(dict(sequence=sequence, tip_board_mm=[x, y, z],
                                  gap_to_undeformed_top_mm=gap, inside_key_xy=inside))
    return dict(profile_id=profile["profile_id"], profile_file_sha256=_file_sha(profile_path),
                layout_file_sha256=_file_sha(layout_path), keyboard_tool_length_mm=length,
                sampled_rows=len(rows), key_center_board_xy_mm=center, key_top_mm=top,
                contact_endpoints=endpoints, phase_runs=ranges)


def _corrected_space_cycle(route, paths):
    """Offline local press stroke at the episode target, including tool-tip geometry."""
    import math
    from nominal_route_concrete_native_attempt_binding import (
        _build_solver_kwargs,
        EXPECTED_LAYOUT_SHA256,
    )
    from representative_key_mechanics import MECHANICS_PRIOR
    from rocell.geometry import Point3Mm, RigidTransform, Rotation3, Vec3
    from rocell.kinematics.ik import (
        ARM_JOINT_NAMES,
        BoardToolTipTarget,
        RoArmM3NumericalIk,
    )

    profile_path = ROOT / "software/config/virtual_commissioning_profile.json"
    if (
        _file_sha(profile_path) != route["source_bindings"]["virtual_profile_sha256"]
        or _file_sha(paths.layout) != EXPECTED_LAYOUT_SHA256
    ):
        raise ValueError("cycle tool profile or keyboard layout changed")
    profile = json.loads(profile_path.read_bytes())
    study = profile["study_input"]
    if any(
        abs(a - b) > 1e-12
        for a, b in zip(
            study["physical_placement_input"]["matrix_row_major"],
            route["robot_placement_matrix_row_major"],
            strict=True,
        )
    ):
        raise ValueError("cycle base placement differs from episode")
    m = study["derived_solver_transform"]["matrix_row_major"]
    board = RigidTransform(
        "board",
        "world",
        Rotation3(tuple(m[4 * i + j] for i in range(3) for j in range(3))),
        Vec3(m[3], m[7], m[11]),
    )
    length = study["route_tool_lengths_mm"]["keyboard"]
    options = _build_solver_kwargs(paths)
    options.update(board_T_world=board, hand_tcp_to_tip_z_mm=-length)
    solver = RoArmM3NumericalIk(**options)
    x, y = route["randomized_key_center_board_xy_mm"]
    half_x, half_y = route["target_region"]["half_extent_mm"]
    rest = json.loads(paths.layout.read_bytes())["keyboard"]["target_plane_z_board_mm"]
    radius = MECHANICS_PRIOR["tip_radius_mm"]
    activation = MECHANICS_PRIOR["activation_mm"]["range"][1]
    max_depth = MECHANICS_PRIOR["travel_mm"]["range"][0]
    # Leave a symmetric allowance between the deepest activation and shallowest stop.
    depth = (activation + max_depth) / 2
    hover = rest + 9.0
    bottom = rest - depth
    segments = math.ceil((hover - bottom) / 0.5)
    z_targets = [hover + (bottom - hover) * i / segments for i in range(segments + 1)]
    seed = {
        name: JointPosition.radians(q)
        for name, q in zip(
            ARM_JOINT_NAMES,
            route["joint_targets"][route["contact_endpoint_sequences"][0]][
                "joint_position_target_rad"
            ][:5],
            strict=True,
        )
    }
    joints = []
    for z in z_targets:
        solved = solver.solve(
            BoardToolTipTarget(Point3Mm("board", x, y, z)), seed_joint_positions=(seed,)
        )
        if not solved.converged:
            raise ValueError(f"SPACE IK failed at height {z}")
        seed = {v.name: v.position for v in solved.solution_arm_joint_positions}
        joints.append(
            [seed[n].value for n in ARM_JOINT_NAMES]
            + [solver.fixed_gripper_position.value]
        )
    joints += joints[-2::-1]
    z_targets += z_targets[-2::-1]
    max_error = 0.0
    min_edge = float("inf")
    gaps = []
    for index, (left, right) in enumerate(zip(joints, joints[1:])):
        for step in range(0 if index == 0 else 1, 11):
            t = step / 10
            q = [a + (b - a) * t for a, b in zip(left, right)]
            state = {
                n: JointPosition.radians(v)
                for n, v in zip(EXPECTED_DOF_NAMES, q, strict=True)
            }
            hand = board.compose(solver.model.forward_kinematics(state)["hand_tcp"])
            center = hand.transform_position_mm(Vec3(0, 0, -length + radius))
            gap = center.z - radius - rest
            gaps.append(gap)
            target_z = z_targets[index] + (z_targets[index + 1] - z_targets[index]) * t
            max_error = max(max_error, abs(gap + rest - target_z))
            min_edge = min(
                min_edge,
                half_x - abs(center.x - x) - radius,
                half_y - abs(center.y - y) - radius,
            )
    stop = segments * 10
    if not (
        min_edge >= MECHANICS_PRIOR["center_margin_mm"]
        and max_error <= 0.05
        and activation <= -min(gaps) < max_depth
        and gaps[-1] > 0
        and all(a >= b for a, b in zip(gaps[:stop], gaps[1 : stop + 1]))
        and all(a <= b for a, b in zip(gaps[stop:], gaps[stop + 1 :]))
    ):
        raise ValueError("sampled SPACE stroke outside tool/key envelope")
    return dict(
        schema="tactevra.offline_space_local_stroke.v1",
        episode_id=route["episode_id"],
        profile_id=profile["profile_id"],
        profile_file_sha256=_file_sha(profile_path),
        route_file_sha256=_file_sha(paths.route),
        layout_file_sha256=_file_sha(paths.layout),
        joint_order=list(EXPECTED_DOF_NAMES),
        keyboard_tool_length_mm=length,
        target_xy_mm=[x, y],
        hover_above_rest_mm=hover - rest,
        target_depth_mm=depth,
        waypoints_rad=joints,
        interpolation="LINEAR_JOINT_SPACE",
        samples=len(gaps),
        maximum_surface_height_error_mm=max_error,
        minimum_xy_edge_margin_mm=min_edge,
        maximum_geometric_depth_mm=-min(gaps),
        final_gap_mm=gaps[-1],
        hardware_access=False,
        key_displacement_measured=False,
        validated_scope="SAMPLED_LOCAL_STROKE_GEOMETRY_ONLY",
    )


def _connected_stroke(route, paths):
    """Join the saved park pose to the local stroke, then return along the approach."""
    import math
    from nominal_route_native_component_obb_binding import (
        _component_coefficients,
        _joint_chain,
    )
    from nominal_route_whole_component_candidate import build_candidate
    from representative_key_mechanics import MECHANICS_PRIOR
    from rocell.geometry import Vec3

    local = _corrected_space_cycle(route, paths)
    park_row = route["joint_targets"][0]
    if park_row["phase"] != "PARK":
        raise ValueError("SPACE route does not start at park")
    park = park_row["joint_position_target_rad"]
    stroke = local["waypoints_rad"]
    hover = stroke[0]
    steps = math.ceil(max(abs(a - b) for a, b in zip(park, hover, strict=True)) / 0.005)
    approach = [
        [a + (b - a) * i / steps for a, b in zip(park, hover, strict=True)]
        for i in range(steps)
    ]
    joints = approach + stroke + approach[::-1]
    integration = Path(__file__).resolve().parent
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    layout = ROOT / "active-project/RoCell_v0_3/config/workcell_layout.json"
    definition = build_candidate(ROOT)
    # This ephemeral record supplies the offline FK adapter only.
    review = _signed(
        dict(
            schema="tactevra.isaac_lm4_native_component_obb_binding_review.v1",
            status="ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION",
            source_binding_sha256=definition["binding_sha256"],
            runtime_instantiation_admitted=True,
            launch_admitted=False,
            hardware_access=False,
            physical_authority=False,
        ),
        "review_sha256",
    )
    fk = _OfflineArticulation(urdf)
    runtime = NativeComponentObbRuntime(
        definition, binding_review=review, articulation=fk
    )
    obstacles = _workcell_boxes(route, json.loads(layout.read_bytes()), urdf)
    rows = [{"joint_position_target_rad": q} for q in joints]
    segments = range(len(rows) - 1)
    workcell = _screen_workcell(runtime, rows, obstacles, segments)
    if any(box["segments_unresolved"] for box in workcell.values()):
        raise ValueError(
            f"connected stroke has unresolved workcell intervals: {workcell}"
        )
    minimum_self = min(
        check_continuous_self_clearance(
            runtime,
            start_sequence=i,
            end_sequence=i + 1,
            start_joint_targets_rad=joints[i],
            end_joint_targets_rad=joints[i + 1],
            reviewed_excluded_pairs=tuple(runtime.excluded_pairs),
        )["minimum_clearance_mm"]
        for i in segments
    )
    radius = MECHANICS_PRIOR["tip_radius_mm"]
    length = local["keyboard_tool_length_mm"]
    coefficients = _component_coefficients(
        "hand_tcp", (0, 0, -length + radius), (0, 0, 0), _joint_chain(urdf.read_text())
    )
    # Work in URDF world. The pinned board pose is yaw-only; its top-plane
    # normal is +Z here as well. Include the fixed URDF base height offset.
    board_box, keyboard_box = obstacles
    if tuple(round(v, 10) for v in keyboard_box.start_axes_row_major[6:]) != (0, 0, 1):
        raise ValueError("tool-height certificate requires board Z aligned to world Z")
    upper = max(box.start_center_mm[2] + box.half_extents_mm[2] for box in obstacles)
    gap = math.inf
    for i in range(steps):
        state = {
            name: JointPosition.radians(v)
            for name, v in zip(EXPECTED_DOF_NAMES, joints[i], strict=True)
        }
        hand = fk.model.forward_kinematics(state)["hand_tcp"]
        tip_center = hand.transform_position_mm(Vec3(0, 0, -length + radius))
        drift = sum(
            coefficients.get(name, 0) * abs(b - a)
            for name, a, b in zip(
                EXPECTED_DOF_NAMES, joints[i], joints[i + 1], strict=True
            )
        )
        gap = min(
            gap, min(hand.translation_mm.z, tip_center.z) - radius - drift - upper
        )
    if gap <= 0.5:
        raise ValueError(f"approach tool clearance unresolved: {gap}")
    return dict(
        schema="tactevra.offline_space_connected_stroke.v1",
        episode_id=route["episode_id"],
        local_stroke_sha256=_sha(local),
        profile_file_sha256=local["profile_file_sha256"],
        route_file_sha256=local["route_file_sha256"],
        workcell_file_sha256=_file_sha(layout),
        audit_source_sha256=_file_sha(integration / "arm301_source_route_obb_audit.py"),
        component_definition_sha256=definition["binding_sha256"],
        waypoints_rad=joints,
        joint_order=list(EXPECTED_DOF_NAMES),
        approach_segments=steps,
        stroke_segments=len(stroke) - 1,
        return_segments=steps,
        clearance_segments=len(segments),
        minimum_arm_self_clearance_mm=minimum_self,
        arm_workcell_clearance=workcell,
        approach_return_virtual_capsule_radius_mm=radius,
        approach_return_minimum_tool_clearance_mm=gap,
        modeled_tip_stroke_samples=local["samples"],
        hardware_access=False,
        physical_authority=False,
        key_displacement_measured=False,
    )


def _timed_key_response(route, paths, connected, *, substeps=4):
    """Prescribed joint motion with a one-dimensional unilateral spring-damper key."""
    import math
    from nominal_route_concrete_native_attempt_binding import EXPECTED_MECHANICS_SHA256
    from representative_key_mechanics import build_profile, evaluate_trace
    from rocell.geometry import Vec3

    receipt_hash = connected["receipt_sha256"]
    if (
        _sha(connected["waypoints_rad"])
        != "74964ffb203378200ac0280a9f51a97f17a357926bc7aedc8518623f97e4f1c5"
        or connected["joint_order"] != list(EXPECTED_DOF_NAMES)
        or connected["episode_id"] != route["episode_id"]
        or receipt_hash
        != _sha({k: v for k, v in connected.items() if k != "receipt_sha256"})
        or connected["route_file_sha256"] != _file_sha(paths.route)
        or _file_sha(paths.mechanics) != EXPECTED_MECHANICS_SHA256
    ):
        raise ValueError("timed simulation inputs differ from screened path")
    profile = build_profile(paths.layout)
    if (
        profile["profile_sha256"]
        != route["source_bindings"]["key_mechanics_profile_sha256"]
    ):
        raise ValueError("key mechanics profile changed")
    virtual = ROOT / "software/config/virtual_commissioning_profile.json"
    if _file_sha(virtual) != connected["profile_file_sha256"]:
        raise ValueError("virtual placement changed")
    study = json.loads(virtual.read_bytes())["study_input"]
    board = study["derived_solver_transform"]["matrix_row_major"]
    length = study["route_tool_lengths_mm"]["keyboard"]
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    if _file_sha(urdf) != "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190":
        raise ValueError("timed path FK model changed")
    model = UrdfModel.from_file(urdf)
    params = route["randomized_parameters"]
    mass, damping, stiffness = (
        params[name]
        for name in ("key_mass_kg", "key_damping_n_s_per_m", "key_stiffness_n_per_m")
    )
    angle = math.radians(params["keyboard_yaw_deg"])
    prior = profile["mechanics_prior"]
    radius = prior["tip_radius_mm"]
    drive = json.loads(paths.mechanics.read_bytes())
    tick = drive["physics_dt_s"]
    speed_limit = drive["dof"]["maximum_velocity_rad_s"]
    dt = tick / substeps
    joints = connected["waypoints_rad"]
    trace, events, waypoint_ticks = [], [], [0]
    released = True
    travel = velocity = peak_speed = 0.0
    for i, (left, right) in enumerate(zip(joints, joints[1:])):
        delta = max(abs(a - b) for a, b in zip(left, right))
        ticks = max(1, math.ceil(delta / (speed_limit * tick)))
        waypoint_ticks.append(waypoint_ticks[-1] + ticks)
        peak_speed = max(peak_speed, delta / (tick * ticks))
        count = ticks * substeps
        for j in range(0 if i == 0 else 1, count + 1):
            q = [a + (b - a) * j / count for a, b in zip(left, right)]
            state = {
                n: JointPosition.radians(v)
                for n, v in zip(EXPECTED_DOF_NAMES, q, strict=True)
            }
            hand = model.forward_kinematics(state)["hand_tcp"]
            tip = hand.transform_position_mm(
                Vec3(0, 0, -length + radius)
            )
            world = (tip.x, tip.y, tip.z, 1)
            x, y, z = (
                sum(board[4 * r + c] * v for c, v in enumerate(world)) for r in range(3)
            )
            x -= params["keyboard_offset_x_mm"]
            y -= params["keyboard_offset_y_mm"]
            # Evaluate guard regions in their original keyboard placement.
            px = math.cos(angle) * x + math.sin(angle) * y
            py = -math.sin(angle) * x + math.cos(angle) * y
            depth = max(0.0, profile["target_plane_z_board_mm"] - z + radius)
            if depth > prior["travel_mm"]["range"][0]:
                raise ValueError(
                    "prescribed tool exceeds shallowest modeled travel stop"
                )
            # Backward Euler free response followed by the unilateral tip/rest constraint.
            # The centered stroke has a rigid tip and no arm tracking lag.
            free_v = (mass * velocity - dt * stiffness * travel) / (
                mass + dt * damping + dt * dt * stiffness
            )
            next_travel = max(depth, travel + dt * free_v)
            velocity = (next_travel - travel) / dt
            travel = next_travel
            time = len(trace) * dt
            trace.append(
                dict(
                    time_s=time,
                    tip_x_board_mm=px,
                    tip_y_board_mm=py,
                    compression_mm=travel,
                )
            )
            if released and travel >= prior["activation_mm"]["nominal"]:
                events.append(dict(event="down", time_s=time, displacement_mm=travel))
                released = False
            elif not released and travel <= prior["release_mm"]["nominal"]:
                events.append(dict(event="up", time_s=time, displacement_mm=travel))
                released = True
    evaluation = evaluate_trace(profile, trace)
    if (
        not evaluation["accepted"]
        or evaluation["resolved_key"] != "SPACE"
        or [e["event"] for e in events] != ["down", "up"]
        or evaluation["max_compression_mm"] < prior["activation_mm"]["range"][1]
        or travel > prior["release_mm"]["range"][0]
    ):
        raise ValueError(f"timed SPACE response failed: {evaluation}, {events}")
    return dict(
        schema="tactevra.offline_timed_space_key_response.v1",
        source_path_sha256=receipt_hash,
        episode_id=route["episode_id"],
        substeps_per_tick=substeps,
        waypoint_ticks=waypoint_ticks,
        tick_s=tick,
        duration_s=trace[-1]["time_s"],
        events=events,
        maximum_prescribed_joint_speed_rad_s=peak_speed,
        modeled_key_mass_kg=mass,
        modeled_key_stiffness_n_m=stiffness,
        modeled_key_damping_n_s_m=damping,
        trace_evaluation=evaluation,
        trace_sha256=_sha(trace),
        key_response_model="PRESCRIBED_TIP_UNILATERAL_1D_IMPLICIT_EULER",
        isaac_started=False,
        hardware_access=False,
        physical_authority=False,
    )


def audit(route: Path, *, whole_components: bool = False, ik_artifacts: Path | None = None, screen_workcell: bool = False, screen_tip: bool = False) -> dict:
    integration = Path(__file__).resolve().parent
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    partition = integration / "evidence/roarm_m3_triangle_partition_link2_20261005.json"
    binding = integration / "nominal_route_native_component_obb_binding.py"
    proof = integration / "nominal_route_component_obb_clearance.py"
    if _file_sha(route) != ROUTE_SHA256:
        raise ValueError("route file digest changed")
    data = json.loads(route.read_bytes())
    if data.get("episode_id") != EPISODE:
        raise ValueError("route episode changed")
    rows = data["joint_targets"]
    definition = build_definition(
        json.loads(partition.read_bytes()), partition_file_sha256=_file_sha(partition),
        urdf_file_sha256=_file_sha(urdf), binding_source_file_sha256=_file_sha(binding),
        urdf_text=urdf.read_text(encoding="utf-8"),
    )
    reduction = integration / "evidence/roarm_m3_link_mesh_reduction_20261004.json"
    if whole_components:
        from nominal_route_whole_component_candidate import build_candidate
        definition = build_candidate(ROOT)
        _verify_whole_component_inventory(definition, json.loads(reduction.read_bytes()))
    # This local record enables the offline mathematical audit only; it is not
    # an independent review or permission to construct a live Isaac runtime.
    review = _signed({
        "schema": "tactevra.isaac_lm4_native_component_obb_binding_review.v1",
        "status": "ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True, "launch_admitted": False,
        "hardware_access": False, "physical_authority": False,
    }, "review_sha256")
    runtime = NativeComponentObbRuntime(
        definition, binding_review=review, articulation=_OfflineArticulation(urdf)
    )
    regenerated = {}
    if ik_artifacts is not None:
        if not whole_components:
            raise ValueError("regenerated route audit requires whole-component geometry")
        rows, continuity = _regenerated_rows(data, ik_artifacts)
        regenerated = {
            "route_input": "CANONICAL_IK_653_THROUGH_940_SOURCE_EXIT_941",
            "continuity": continuity,
            "screened_joint_rows_sha256": _sha([row["joint_position_target_rad"] for row in rows[653:942]]),
        }
    if screen_workcell:
        if not regenerated:
            raise ValueError("workcell screen requires regenerated whole-component geometry")
        layout = ROOT / "active-project/RoCell_v0_3/config/workcell_layout.json"
        obstacles = _workcell_boxes(data, json.loads(layout.read_bytes()), urdf)
        regenerated["nominal_workcell_screen"] = {
            "layout_file_sha256": _file_sha(layout),
            "geometry": "BOARD_AND_SOLID_NOMINAL_KEYBOARD_ENVELOPE",
            "obstacles": _screen_workcell(runtime, rows, obstacles),
        }
    if screen_tip:
        if not regenerated:
            raise ValueError("tip screen requires regenerated whole-component route")
        regenerated["sampled_tip_path"] = _screen_tip(
            data, rows, urdf, ROOT / "software/config/virtual_commissioning_profile.json",
            ROOT / "software/config/nominal_target_profiles.json",
        )
    outcomes = []
    for sequence in range(653, 941):
        left, right = rows[sequence], rows[sequence + 1]
        if left["sequence"] != sequence or right["sequence"] != sequence + 1:
            raise ValueError("route sequence changed")
        outcomes.append(check_continuous_self_clearance(
            runtime, start_sequence=sequence, end_sequence=sequence + 1,
            start_joint_targets_rad=left["joint_position_target_rad"],
            end_joint_targets_rad=right["joint_position_target_rad"],
            reviewed_excluded_pairs=tuple(runtime.excluded_pairs),
        ))
    return _signed({
        "schema": "tactevra.arm301.offline_source_route_obb_audit.v1",
        "source_files_sha256": {"route": _file_sha(route), "urdf": _file_sha(urdf),
            "partition": _file_sha(partition), "binding": _file_sha(binding),
            "proof": _file_sha(proof), "audit": _file_sha(Path(__file__)),
            **({"whole_component_reduction": _file_sha(reduction),
                "whole_component_builder": _file_sha(integration / "nominal_route_whole_component_candidate.py")}
               if whole_components else {})},
        "component_definition_sha256": definition["binding_sha256"],
        "geometry_candidate": "WHOLE_COMPONENT_BOXES" if whole_components else "TRIANGLE_PARTITION_BOXES",
        "component_count": len(definition["component_obbs"]), **regenerated,
        "episode_id": EPISODE, "first_sequence": 653, "last_sequence": 941,
        "segment_count": len(outcomes),
        "intervals_inspected": sum(row["intervals_inspected"] for row in outcomes),
        "terminal_proof_intervals": sum((row["intervals_inspected"] + 1) // 2 for row in outcomes),
        "subdivided_segments": sum(row["maximum_subdivision_depth"] > 0 for row in outcomes),
        "maximum_subdivision_depth": max(row["maximum_subdivision_depth"] for row in outcomes),
        "minimum_certified_residual_mm": min(row["minimum_clearance_mm"] for row in outcomes),
        "direct_joint_exclusions": [list(pair) for pair in sorted(runtime.excluded_pairs)],
        "clearance_margin_mm": 0.5, "python_version": sys.version.split()[0],
        "scipy_version": scipy.__version__, "isaac_started": False,
        "hardware_access": False, "physical_authority": False,
        "scope": ("REGENERATED_ROUTE_NONADJACENT_CONVEX_HULL_SURROGATE_CLEARANCE" if regenerated else "SOURCE_ROUTE_NONADJACENT_CONVEX_HULL_SURROGATE_CLEARANCE"
                  if whole_components else "SOURCE_ROUTE_NONADJACENT_MESH_SURFACE_CLEARANCE"),
        "modeled_solid_semantics": (
            "CONVEX_HULL_OF_EACH_SOURCE_COMPONENT_OR_WHOLE_LINK_FALLBACK"
            if whole_components else "SURFACE_ONLY"
        ),
        "limitations": ["offline URDF FK", *([] if regenerated else ["not regenerated IK"]), "no environment proof",
                        "no Isaac validation", "local review is not independent",
                        "mesh-to-robot frame alignment not established by this audit",
                        "physical robot, attachments and omitted geometry not bounded",
                        "link1 and link5 source meshes are non-watertight"]
        + ([] if whole_components else ["surface containment does not establish solid non-nesting"]),
    }, "receipt_sha256")


def prepare_native_space_plan(route_path, connected_path, response_path):
    """Map the screened stroke and its exact tick schedule to native target rows."""
    route = json.loads(route_path.read_bytes())
    path = json.loads(connected_path.read_bytes())
    timing = json.loads(response_path.read_bytes())
    for document, digest in (
        (path, "96b8bbb027bb468855bc3fc0284e23f47b3fa648b41f458f8c043eb56d276c85"),
        (timing, "ba9fa1a744ad060d8fe4e7b210f8206d6b1dd350de64939b773fbd04805a40ae"),
    ):
        if (document["receipt_sha256"] != digest
                or _sha({k: v for k, v in document.items() if k != "receipt_sha256"}) != digest):
            raise ValueError("screened SPACE input digest changed")
    if (_file_sha(route_path) != ROUTE_SHA256 or path["route_file_sha256"] != ROUTE_SHA256
            or timing["source_path_sha256"] != path["receipt_sha256"]):
        raise ValueError("screened SPACE lineage changed")
    start = path["approach_segments"]
    bottom = start + path["stroke_segments"] // 2
    end = start + path["stroke_segments"]
    ticks = timing["waypoint_ticks"]
    if ticks != list(range(423)):
        raise ValueError("native one-target-per-tick schedule changed")
    targets = []
    for tick, joints in zip(ticks, path["waypoints_rad"], strict=True):
        phase = "TRANSIT"
        if tick in (0, ticks[-1]):
            phase = "PARK"
        elif tick in (start, end):
            phase = "HOVER"
        elif start < tick <= bottom:
            phase = "CONTACT"
        elif bottom < tick < end:
            phase = "RETRACT"
        targets.append(dict(sequence=tick, action_index=0, target_id="SPACE", phase=phase,
                            phase_endpoint=tick==bottom, joint_position_target_rad=joints,
                            time_from_start_ns=round(tick * timing["tick_s"] * 1e9)))
    plan = {key: route[key] for key in (
        "episode_id", "target_id", "target_region", "joint_order", "robot_placement_matrix_row_major",
        "randomized_parameters", "randomized_key_center_board_xy_mm", "source_bindings",
        "execution_contract", "limitations", "hardware_access", "physical_authority",
        "hardware_writes", "physical_movements", "controller_commands", "gate_promotions",
    )}
    plan.update(schema="tactevra.arm301.corrected_space_native_plan.v1",
                source_connected_sha256=path["receipt_sha256"], source_timing_sha256=timing["receipt_sha256"],
                source_route_file_sha256=ROUTE_SHA256, joint_targets=targets, action_count=1,
                contact_endpoint_sequences=[bottom], sample_count=len(targets),
                initialization_sequence=0, scheduled_physics_steps=ticks[-1])
    return _signed(plan, "plan_sha256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--whole-components", action="store_true", help="audit exploratory whole-component boxes")
    parser.add_argument("--ik-artifacts", type=Path, help="regenerate the governed IK window using retained adapter artifacts")
    parser.add_argument("--screen-workcell", action="store_true", help="screen the nominal board and keyboard envelope")
    parser.add_argument("--screen-tip", action="store_true", help="evaluate sampled virtual keyboard tip through contact and retraction")
    parser.add_argument("--plan-local-stroke", action="store_true", help="generate offline episode-profile SPACE stroke")
    parser.add_argument("--plan-connected-stroke", action="store_true", help="screen park, SPACE stroke and return offline")
    parser.add_argument("--time-connected-stroke", type=Path, help="evaluate retained connected path with the episode key dynamics")
    parser.add_argument("--prepare-native-space", nargs=2, type=Path, metavar=("CONNECTED", "TIMED"),
                        help="prepare the one-action native plan offline")
    args = parser.parse_args()
    if args.prepare_native_space:
        result = prepare_native_space_plan(args.route, *args.prepare_native_space)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(result["plan_sha256"])
        return 0
    if args.plan_local_stroke or args.plan_connected_stroke or args.time_connected_stroke:
        from nominal_route_concrete_native_attempt_binding import BindingPaths
        if _file_sha(args.route) != ROUTE_SHA256 or args.ik_artifacts is None:
            parser.error("local stroke requires pinned route and --ik-artifacts")
        paths = BindingPaths(args.ik_artifacts, ROOT, args.output)
        if paths.route.resolve() != args.route.resolve():
            parser.error("artifact root and supplied route differ")
        planner = _connected_stroke if args.plan_connected_stroke else _corrected_space_cycle
        route = json.loads(args.route.read_bytes())
        if args.time_connected_stroke:
            connected = json.loads(args.time_connected_stroke.read_bytes())
            result = _timed_key_response(route, paths, connected)
        else:
            result = planner(route, paths)
        result = _signed(result, "receipt_sha256")
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(json.dumps({k:v for k,v in result.items() if k != "waypoints_rad"}))
        return 0
    result = audit(args.route, whole_components=args.whole_components, ik_artifacts=args.ik_artifacts,
                   screen_workcell=args.screen_workcell, screen_tip=args.screen_tip)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
