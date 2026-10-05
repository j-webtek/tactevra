"""Exploratory clearance-waypoint, park-feasibility, and pad study.

This is a simulation probe of an arm-runtime planning design. It emits no
motion policy, controller data, permit, transport operation, or authority.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
from itertools import product
import json
import math
from pathlib import Path
from typing import Any, Iterable

from rocell.geometry import JointPosition, Point3Mm, Vec3
from rocell.kinematics.ik import BoardToolTipTarget
from rocell.simulation.collision import (
    CollisionBindingMode, CollisionBody, CollisionBodyRequirement,
    CollisionBodyRole, CollisionEvidenceState, OrientedBoxMm,
)

from rocell_ai.first_motion_collision_design import _World, _interpolate
from rocell_ai.first_motion_controller_emulator import SCOPE, _baseline_joints, load_emulator_fixture
from rocell_ai.first_motion_drills import load_collision_attribution_fixture


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_waypoint_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("clearance-waypoint fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in ("waypoint_study", "swappable_pad"):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _sha(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("fixture changed zero-authority scope")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound waypoint input changed: {source}")
    return value


def load_passive_tool_rerun_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("passive-tool rerun fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in ("waypoint_rerun", "shadow_rehearsal"):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _sha(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("passive-tool rerun changed zero-authority scope")
    if value["attachment_configuration"]["moving_cable_present"] is not False:
        raise ValueError("passive-tool rerun requires no moving cable")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound passive-tool rerun input changed: {source}")
    return value


def load_target_contact_cad_fixture(path: Path) -> dict[str, Any]:
    """Load the frozen CAD/keycap successor without opening result evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("target/contact CAD fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in ("station_cad", "tool_component_model", "stage_c", "keycap_contact"):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _sha(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("target/contact CAD fixture changed zero-authority scope")
    if value["physical_authority"] is not False:
        raise ValueError("target/contact CAD fixture claims physical authority")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound target/contact CAD input changed: {source}")
    return value


def load_tool_bound_exact_clearance_fixture(path: Path) -> dict[str, Any]:
    """Load the frozen tool-bound successor and verify every source binding."""

    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("tool-bound exact-clearance fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in (
        "tool_configuration_contract", "length_sweep", "continuous_geometry",
        "calibrated_residual",
    ):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _sha(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("tool-bound fixture changed zero-authority scope")
    if value["physical_authority"] is not False:
        raise ValueError("tool-bound fixture claims physical authority")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound tool-clearance input changed: {source}")
    return value


def tool_configuration(
    fixture: dict[str, Any], legacy_pose_bundle: dict[str, Any], *,
    total_length_mm: float, exposed_length_mm: float, tip_radius_mm: float,
) -> dict[str, Any]:
    """Build the only canonical configuration identity accepted by pose bundles."""

    bindings = fixture["bindings"]
    board_transform = legacy_pose_bundle["layout_overlay"][
        "board_T_vendor_world_matrix_row_major"
    ]
    return {
        "total_hand_tcp_to_tip_length_mm": float(total_length_mm),
        "distal_tip_exposed_length_mm": float(exposed_length_mm),
        "distal_tip_radius_mm": float(tip_radius_mm),
        "keyboard_tip_mesh_sha256": bindings["keyboard_tip_mesh"]["sha256"],
        "stylus_collar_mesh_sha256": bindings["stylus_collar_mesh"]["sha256"],
        "tool_body_mesh_sha256": bindings["tool_body_mesh"]["sha256"],
        "solver_model_sha256": bindings["mjcf"]["sha256"],
        "target_catalog_sha256": bindings["target_catalog"]["sha256"],
        "board_transform_sha256": _sha(board_transform),
    }


def bind_pose_bundle_tool_configuration(
    pose_bundle: dict[str, Any], configuration: dict[str, Any],
) -> dict[str, Any]:
    """Return a zero-authority pose bundle cryptographically bound to one tool."""

    result = json.loads(json.dumps(pose_bundle))
    result["schema"] = "tactevra.tool_bound_pose_bundle.v1"
    result["tool_configuration"] = configuration
    result["tool_configuration_sha256"] = _sha(configuration)
    result["hardware_access"] = False
    result["hardware_write_count"] = 0
    result["physical_movement_count"] = 0
    result["physical_authority"] = False
    result["controller_commands"] = []
    result.pop("receipt_sha256", None)
    result["receipt_sha256"] = _sha(result)
    return result


def validate_pose_bundle_tool_configuration(
    pose_bundle: dict[str, Any], configuration: dict[str, Any],
) -> None:
    """Fail before screening if bundle bytes and requested tool do not agree."""

    unsigned = dict(pose_bundle)
    claimed_receipt = unsigned.pop("receipt_sha256", None)
    if claimed_receipt != _sha(unsigned):
        raise ValueError("tool-bound pose bundle receipt mismatch")
    if pose_bundle.get("schema") != "tactevra.tool_bound_pose_bundle.v1":
        raise ValueError("unsupported tool-bound pose bundle schema")
    claimed_config = pose_bundle.get("tool_configuration")
    claimed_hash = pose_bundle.get("tool_configuration_sha256")
    if claimed_hash != _sha(claimed_config):
        raise ValueError("pose bundle tool configuration hash mismatch")
    if claimed_hash != _sha(configuration) or claimed_config != configuration:
        raise ValueError("pose bundle does not match requested tool configuration")
    if (
        pose_bundle.get("hardware_access") is not False
        or pose_bundle.get("hardware_write_count") != 0
        or pose_bundle.get("physical_movement_count") != 0
        or pose_bundle.get("physical_authority") is not False
        or pose_bundle.get("controller_commands") != []
    ):
        raise ValueError("tool-bound pose bundle carries physical authority")


def solve_tool_bound_pose_families(
    fixture: dict[str, Any], *, workspace: Path,
) -> dict[str, Any]:
    """Solve one independently bound target-pose family per frozen tool profile."""

    prior_path = Path(fixture["bindings"]["prior_fixture"]["path"])
    if not prior_path.is_absolute():
        prior_path = workspace / prior_path
    prior = load_target_contact_cad_fixture(prior_path)
    passive_path = Path(prior["bindings"]["prior_fixture"]["path"])
    if not passive_path.is_absolute():
        passive_path = workspace / passive_path
    passive = load_passive_tool_rerun_fixture(passive_path)
    design_path = Path(passive["bindings"]["collision_design_fixture"]["path"])
    if not design_path.is_absolute():
        design_path = workspace / design_path
    world = _World(json.loads(design_path.read_text(encoding="utf-8")), workspace)

    legacy_path = Path(fixture["bindings"]["legacy_pose_bundle"]["path"])
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    targets = legacy["poses"]
    if len(targets) != 46:
        raise ValueError("tool-bound successor requires exactly 46 target poses")
    profiles: list[dict[str, Any]] = []
    reach_by_length: dict[str, dict[str, Any]] = {}
    solved_by_length: dict[float, tuple[list[dict[str, Any]], list[str]]] = {}

    for length in fixture["length_sweep"]["total_hand_tcp_to_tip_length_mm"]:
        solver = world.solver(float(length))
        poses: list[dict[str, Any]] = []
        failures: list[str] = []
        for source in targets:
            seed = tuple(float(value) for value in source["joint_positions_rad"])
            xyz = source["contact_target_board_mm"]
            target = (float(xyz["x"]), float(xyz["y"]), float(xyz["z"]))
            solved = _solve_seeded(world, solver, target, seed)
            if solved is None:
                failures.append(source["target_id"])
                continue
            achieved = _tip_xyz(world, solved, float(length))
            error = math.sqrt(sum(
                (actual - expected) ** 2
                for actual, expected in zip(achieved, target, strict=True)
            ))
            poses.append({
                "target_id": source["target_id"],
                "contact_target_board_mm": dict(source["contact_target_board_mm"]),
                "joint_positions_rad": list(solved),
                "achieved_tip_board_mm": list(achieved),
                "ik_position_error_mm": error,
            })
        solved_by_length[float(length)] = (poses, failures)
        reach_by_length[str(float(length))] = {
            "solved_target_count": len(poses),
            "failed_target_ids": failures,
            "all_targets_reached": not failures and len(poses) == len(targets),
            "maximum_ik_position_error_mm": max(
                (row["ik_position_error_mm"] for row in poses), default=None),
        }

    for length, exposed, radius in product(
        fixture["length_sweep"]["total_hand_tcp_to_tip_length_mm"],
        fixture["length_sweep"]["distal_tip_exposed_length_mm"],
        fixture["length_sweep"]["distal_tip_radius_mm"],
    ):
        poses, failures = solved_by_length[float(length)]
        config = tool_configuration(
            fixture, legacy, total_length_mm=float(length),
            exposed_length_mm=float(exposed), tip_radius_mm=float(radius),
        )
        base = {
            "scope": SCOPE,
            "status": "PASS_EXPLORATORY_POSE_SOURCE" if not failures
            else "STOP_UNREACHABLE_TARGETS",
            "fixture_sha256": fixture["fixture_sha256"],
            "joint_order": list(legacy["joint_order"]),
            "layout_overlay": legacy["layout_overlay"],
            "target_count": len(targets),
            "solved_target_count": len(poses),
            "failed_target_ids": list(failures),
            "poses": poses,
            "limitations": [
                "All geometry, placement, tool dimensions, and solver inputs are exploratory.",
                "Pose reach does not prove collision clearance or landing robustness.",
            ],
        }
        bundle = bind_pose_bundle_tool_configuration(base, config)
        validate_pose_bundle_tool_configuration(bundle, config)
        profiles.append({
            "tool_configuration_sha256": bundle["tool_configuration_sha256"],
            "pose_bundle": bundle,
        })

    result = {
        "schema": "tactevra.tool_bound_pose_family_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "reach_by_length_mm": reach_by_length,
        "profiles": profiles,
        "profile_count": len(profiles),
        "decision": "PASS_ALL_LENGTHS_REACH_ALL_TARGETS" if all(
            row["all_targets_reached"] for row in reach_by_length.values()
        ) else "STOP_ONE_OR_MORE_LENGTHS_UNREACHABLE",
        "evaluation_opened": False,
        "gpu_job_count": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


def _joint_map(world: _World, joints: tuple[float, ...]) -> dict[str, JointPosition]:
    values = {name: JointPosition.radians(value) for name, value in zip(
        world.pose_bundle["joint_order"], joints, strict=True)}
    values["link5_to_gripper_link"] = world.context.scenario.fixed_gripper_position
    return values


def _tip_xyz(world: _World, joints: tuple[float, ...], tool_length: float) -> tuple[float, float, float]:
    fk = world.model.forward_kinematics(_joint_map(world, joints))
    board_hand = world.board_t_world.compose(fk["hand_tcp"])
    tip = board_hand.translation_mm + board_hand.rotation.apply(Vec3(0, 0, -tool_length))
    return (tip.x, tip.y, tip.z)


def _hand_board_transform(world: _World, joints: tuple[float, ...]):
    fk = world.model.forward_kinematics(_joint_map(world, joints))
    return world.board_t_world.compose(fk["hand_tcp"])


def _component_profiles(
    spec: dict[str, Any], *, tool_length: float, exposed_length: float,
    tip_radius: float,
) -> tuple[dict[str, float], ...]:
    """Return distal-to-proximal axial envelopes in hand-TCP coordinates."""

    collar_length = spec["collar_axial_length_mm"][0]
    body_length = spec["body_axial_length_mm"][0]
    collar_top = max(0.0, tool_length - exposed_length - collar_length)
    collar_bottom = max(0.0, tool_length - exposed_length)
    body_top = max(0.0, collar_top - body_length)
    return (
        {"component": "DISTAL_TIP", "start_mm": collar_bottom,
         "end_mm": tool_length, "radius_mm": tip_radius},
        {"component": "COLLAR", "start_mm": collar_top,
         "end_mm": collar_bottom, "radius_mm": spec["collar_radius_mm"][0]},
        {"component": "BODY", "start_mm": body_top,
         "end_mm": collar_top,
         "radius_mm": spec["body_conservative_radial_envelope_mm"][0]},
    )


def _component_axis_points(
    transform: Any, component: dict[str, float], spacing_mm: float,
):
    import numpy as np

    length = component["end_mm"] - component["start_mm"]
    count = max(2, int(math.ceil(length / spacing_mm)) + 1)
    distances = np.linspace(component["start_mm"], component["end_mm"], count)
    rows = []
    for distance in distances:
        point = transform.translation_mm + transform.rotation.apply(
            Vec3(0.0, 0.0, -float(distance)))
        rows.append((point.x, point.y, point.z))
    return np.asarray(rows, dtype=float)


def _point_box_min_distance(points: Any, center: tuple[float, float, float],
                            half: tuple[float, float, float]) -> float:
    import numpy as np

    delta = np.maximum(np.abs(points - np.asarray(center)) - np.asarray(half), 0.0)
    return float(np.sqrt(np.sum(delta * delta, axis=1)).min())


def _station_voxel_trees(fixture: dict[str, Any], workspace: Path):
    """Build two frozen-resolution CAD-derived occupancy screens."""

    import numpy as np
    from scipy.spatial import cKDTree
    import trimesh

    layout_path = Path(fixture["bindings"]["workcell_layout"]["path"])
    if not layout_path.is_absolute():
        layout_path = workspace / layout_path
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    result = {}
    for pitch in fixture["station_cad"]["voxel_pitch_mm"]:
        by_station = {}
        for side in ("left", "right"):
            binding = fixture["bindings"][f"station_{side}_mesh"]
            path = Path(binding["path"])
            if not path.is_absolute():
                path = workspace / path
            mesh = trimesh.load_mesh(path, process=False)
            points = np.asarray(mesh.voxelized(float(pitch)).fill().points, dtype=float)
            placement = layout["stations"][f"keyboard_{side}"]
            points += np.asarray((*placement["origin_xy"], placement["installed_z"]),
                                 dtype=float)
            by_station[f"keyboard_{side}"] = {
                "tree": cKDTree(points),
                "bounds": (points.min(axis=0), points.max(axis=0)),
                "point_count": int(points.shape[0]),
            }
        result[float(pitch)] = by_station
    return result


def _station_contacts(
    points: Any, *, radius_mm: float, spacing_mm: float, pitch_mm: float,
    station_trees: dict[str, Any],
) -> list[dict[str, Any]]:
    import numpy as np

    inflation = math.sqrt(3.0) * pitch_mm / 2.0 + spacing_mm / 2.0
    rows = []
    low = points.min(axis=0) - radius_mm - inflation
    high = points.max(axis=0) + radius_mm + inflation
    for station_id, data in station_trees.items():
        bounds_low, bounds_high = data["bounds"]
        if np.any(high < bounds_low) or np.any(low > bounds_high):
            continue
        distance = float(data["tree"].query(points, k=1, workers=1)[0].min())
        clearance = distance - radius_mm - inflation
        if clearance <= 0.0:
            rows.append({"station_id": station_id,
                         "conservative_clearance_mm": clearance})
    return rows


def _keycap_geometry(
    targets: dict[str, dict[str, Any]], *, width_mm: float, thickness_mm: float,
):
    import numpy as np

    ids = tuple(targets)
    centers = []
    for target_id in ids:
        xyz = targets[target_id]["contact_target_board_mm"]
        centers.append((xyz["x"], xyz["y"], xyz["z"] - thickness_mm / 2.0))
    return ids, np.asarray(centers, dtype=float), np.asarray(
        (width_mm / 2.0, width_mm / 2.0, thickness_mm / 2.0), dtype=float)


def _keycap_contacts(
    points: Any, *, component: str, radius_mm: float, spacing_mm: float,
    geometry: tuple[Any, Any, Any],
) -> list[dict[str, Any]]:
    import numpy as np

    ids, centers, half = geometry
    inflated_radius = radius_mm + spacing_mm / 2.0
    top = float((centers[:, 2] + half[2]).max())
    bottom = float((centers[:, 2] - half[2]).min())
    if (float(points[:, 2].min()) - inflated_radius > top
            or float(points[:, 2].max()) + inflated_radius < bottom):
        return []
    delta = np.maximum(
        np.abs(points[:, None, :] - centers[None, :, :]) - half[None, None, :],
        0.0)
    clearances = np.sqrt(np.sum(delta * delta, axis=2)).min(axis=0) - inflated_radius
    return [{"target_id": ids[index], "component": component,
             "conservative_clearance_mm": float(clearances[index])}
            for index in np.flatnonzero(clearances <= 0.0)]


def _solve_seeded(world: _World, solver: Any, xyz: tuple[float, float, float],
                  seed: tuple[float, ...]) -> tuple[float, ...] | None:
    seed_map = {name: JointPosition.radians(value) for name, value in zip(
        world.pose_bundle["joint_order"], seed, strict=True)}
    result = solver.solve(BoardToolTipTarget(Point3Mm("board", *xyz)),
                          seed_joint_positions=(seed_map,))
    if not result.converged:
        return None
    by_name = {row.name: row.position.value for row in result.solution_arm_joint_positions}
    return tuple(by_name[name] for name in world.pose_bundle["joint_order"])


def _clearance_route(world: _World, *, start: tuple[float, ...], end: tuple[float, ...],
                     end_xyz: tuple[float, float, float], tool_length: float,
                     transit_z: float, samples: int) -> tuple[list[tuple[str, tuple[float, ...]]], str | None]:
    solver = world.solver(tool_length)
    start_xyz = _tip_xyz(world, start, tool_length)
    safe_z = max(transit_z, start_xyz[2], end_xyz[2])
    rise = _solve_seeded(world, solver, (start_xyz[0], start_xyz[1], safe_z), start)
    if rise is None:
        return [], "ASCEND_IK"
    across = _solve_seeded(world, solver, (end_xyz[0], end_xyz[1], safe_z), rise)
    if across is None:
        return [], "TRANSIT_IK"
    legs = (("ASCEND", start, rise), ("TRANSIT", rise, across), ("DESCEND", across, end))
    rows: list[tuple[str, tuple[float, ...]]] = []
    for phase, left, right in legs:
        rows.extend((phase, joints) for joints in _interpolate(left, right, samples))
    return rows, None


def _pad_variants(spec: dict[str, Any]) -> list[dict[str, float]]:
    axes = {
        "width_mm": spec["width_mm_range"], "depth_mm": spec["depth_mm_range"],
        "top_z_mm": spec["top_board_z_mm_range"],
        "thickness_mm": spec["thickness_mm_range"],
        "repeatability_mm": spec["locating_repeatability_mm_range"],
        "yaw_deg": spec["locating_yaw_deg_range"],
    }
    baseline = {name: sum(values) / 2 for name, values in axes.items()}
    rows = [{"variant_id": "baseline", **baseline}]
    for name, values in axes.items():
        for value in values:
            if value == baseline[name]:
                continue
            row = dict(baseline)
            row[name] = value
            rows.append({"variant_id": f"{name}={value}", **row})
    return rows


def _pad_contract(world: _World, *, tool_length: float, tool_radius: float,
                  pad: dict[str, float], spec: dict[str, Any],
                  include_moving_cable: bool = True):
    contract = world.contract(
        tool_length=tool_length, tool_radius=tool_radius, pad=None,
        include_moving_cable=include_moving_cable)
    kept = tuple(body for body in contract.bodies if body.body_id != "workcell:keyboard")
    center = spec["center_board_xy_mm"]
    half = Vec3(pad["width_mm"] / 2, pad["depth_mm"] / 2, pad["thickness_mm"] / 2)
    body = CollisionBody(
        "workcell:test_pad", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
        CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
        (OrientedBoxMm(Vec3(center[0], center[1], pad["top_z_mm"] - half.z), half),),
        CollisionBindingMode.STATIC_ROOT, "candidate swappable locating-pin tray",
    )
    bodies = kept + (body,)
    requirements = tuple(CollisionBodyRequirement(
        item.body_id, item.parent_frame, item.role, item.binding_mode,
        "exploratory swappable-pad coverage") for item in bodies)
    return replace(contract, requirements=requirements, bodies=bodies)


def _concerning(pairs: Iterable[str], expected: set[str], *, phase: str,
                pad_expected: str | None = None) -> set[str]:
    result = set(pairs) - expected
    if phase == "PRESS" and pad_expected is not None:
        result.discard(pad_expected)
    return result


def run_clearance_waypoint_study(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    design_path = Path(fixture["bindings"]["collision_design_fixture"]["path"])
    if not design_path.is_absolute():
        design_path = workspace / design_path
    design = json.loads(design_path.read_text())
    world = _World(design, workspace)
    emulator_path = Path(design["bindings"]["emulator_fixture"]["path"])
    if not emulator_path.is_absolute():
        emulator_path = workspace / emulator_path
    baseline = tuple(_baseline_joints(load_emulator_fixture(emulator_path))[:5])
    park_report = json.loads(Path(fixture["bindings"]["park_screen"]["path"]).read_text())
    parks = {row["pose_id"]: tuple(row["joint_positions_rad"][name]
             for name in world.pose_bundle["joint_order"])
             for row in park_report["top_candidates"]
             if row["pose_id"] in fixture["waypoint_study"]["park_pose_ids"]}
    attribution_path = Path(design["bindings"]["attribution_fixture"]["path"])
    if not attribution_path.is_absolute():
        attribution_path = workspace / attribution_path
    attribution = load_collision_attribution_fixture(attribution_path)
    expected = set(attribution["contact_classes"]["DECLARED_EXPECTED_BUT_UNREVIEWED"])
    cable = design["cable_design"]
    cables = list(product(cable["anchor_board_x_mm_range"],
                          cable["anchor_height_board_z_mm_range"],
                          cable["maximum_sag_fraction_range"],
                          cable["cable_radius_mm_range"]))
    tools = list(product(world.section["tool"]["length_mm_range"],
                         world.section["tool"]["radius_mm_range"]))
    spec = fixture["waypoint_study"]
    targets = {row["target_id"]: row for row in world.pose_bundle["poses"]}
    failures: list[str] = []

    def target_xyz(row: dict[str, Any], hover: float = 0.0) -> tuple[float, float, float]:
        xyz = row["contact_target_board_mm"]
        return (xyz["x"], xyz["y"], xyz["z"] + hover)

    # Rank park candidates with one explicitly frozen reference design.
    ref = spec["reference_screen_for_park_scoring"]
    ref_cable = (ref["cable_anchor_x_mm"], ref["cable_anchor_z_mm"],
                 ref["cable_sag_fraction"], ref["cable_radius_mm"])
    ref_contract = world.contract(tool_length=ref["tool_length_mm"],
                                  tool_radius=ref["tool_radius_mm"], pad=None)
    park_rows = []
    route_cache: dict[tuple[str, str, float, float], tuple[list[Any], str | None]] = {}
    for camera_rank, pose_id in enumerate(spec["park_pose_ids"], 1):
        feasible = 0
        phase_pairs: dict[str, dict[str, int]] = {}
        for target_id, row in targets.items():
            destination = tuple(row["joint_positions_rad"])
            route, failure = _clearance_route(
                world, start=parks[pose_id], end=destination,
                end_xyz=target_xyz(row), tool_length=ref["tool_length_mm"],
                transit_z=spec["transit_height_board_z_mm_range"][1],
                samples=spec["samples_per_cartesian_leg"])
            route_cache[(pose_id, target_id, ref["tool_length_mm"],
                         spec["transit_height_board_z_mm_range"][1])] = (route, failure)
            clear = failure is None
            if failure:
                failures.append(f"PARK:{pose_id}:{target_id}:{failure}")
            for phase, joints in route:
                pairs = _concerning(world.evaluate(ref_contract, joints, ref_cable),
                                     expected, phase=phase)
                if pairs:
                    clear = False
                for pair in pairs:
                    phase_pairs.setdefault(phase, {})[pair] = (
                        phase_pairs.setdefault(phase, {}).get(pair, 0) + 1)
            feasible += int(clear)
        park_rows.append({"pose_id": pose_id, "camera_rank": camera_rank,
                          "feasible_target_count": feasible,
                          "target_count": len(targets), "phase_pairs": phase_pairs})
    park_rows.sort(key=lambda row: (-row["feasible_target_count"], row["camera_rank"]))

    # Robust endpoint screen for baseline->park (B) and park->G hover (C).
    robust = {stage: {"evaluations": 0, "concerning": 0, "phase_pairs": {}}
              for stage in ("B", "C")}
    for pose_id in spec["park_pose_ids"]:
        for tool_length, tool_radius in tools:
            contract = world.contract(tool_length=tool_length, tool_radius=tool_radius, pad=None)
            park_xyz = _tip_xyz(world, parks[pose_id], tool_length)
            for transit_z in spec["transit_height_board_z_mm_range"]:
                b_route, b_failure = _clearance_route(
                    world, start=baseline, end=parks[pose_id], end_xyz=park_xyz,
                    tool_length=tool_length, transit_z=transit_z,
                    samples=spec["samples_per_cartesian_leg"])
                g = targets[spec["target_ids_for_stage_c"][0]]
                hover = spec["hover_height_above_contact_mm_range"][1]
                g_end = world.solve(world.solver(tool_length), target_xyz(g, hover))
                c_route, c_failure = ([], "DESTINATION_IK") if g_end is None else _clearance_route(
                    world, start=parks[pose_id], end=g_end, end_xyz=target_xyz(g, hover),
                    tool_length=tool_length, transit_z=transit_z,
                    samples=spec["samples_per_cartesian_leg"])
                for stage, route, failure in (("B", b_route, b_failure),
                                              ("C", c_route, c_failure)):
                    if failure:
                        failures.append(f"{stage}:{pose_id}:{tool_length}:{transit_z}:{failure}")
                    for cable_endpoint in cables:
                        for phase, joints in route:
                            pairs = _concerning(world.evaluate(contract, joints, cable_endpoint),
                                                 expected, phase=phase)
                            robust[stage]["evaluations"] += 1
                            robust[stage]["concerning"] += int(bool(pairs))
                            for pair in pairs:
                                by_phase = robust[stage]["phase_pairs"].setdefault(phase, {})
                                by_phase[pair] = by_phase.get(pair, 0) + 1
    for row in robust.values():
        row["clear"] = row["concerning"] == 0
        row["status"] = "CLEAR_EXPLORATORY_DISCRETE" if row["clear"] else "STOP"

    # Swappable pad: keyboard body absent; only bounded PRESS tool-pad contact is expected.
    pad_spec = fixture["swappable_pad"]
    pad_rows = []
    selected_park = parks[park_rows[0]["pose_id"]]
    for pad in _pad_variants(pad_spec):
        local = {"variant_id": pad["variant_id"], "evaluations": 0,
                 "concerning": 0, "phase_pairs": {}, "ik_failures": []}
        for tool_length, tool_radius in tools:
            contract = _pad_contract(world, tool_length=tool_length,
                                     tool_radius=tool_radius, pad=pad, spec=pad_spec)
            center = pad_spec["center_board_xy_mm"]
            for hover, approach, depth in product(
                    pad_spec["hover_mm_range"], pad_spec["approach_mm_range"],
                    pad_spec["contact_depth_mm_range"]):
                points = {
                    "HOVER": (center[0], center[1], pad["top_z_mm"] + hover),
                    "APPROACH": (center[0], center[1], pad["top_z_mm"] + approach),
                    "PRESS": (center[0], center[1], pad["top_z_mm"] - depth),
                }
                solver = world.solver(tool_length)
                solved = {}
                seed = selected_park
                for phase in ("HOVER", "APPROACH", "PRESS"):
                    solved[phase] = _solve_seeded(world, solver, points[phase], seed)
                    if solved[phase] is None:
                        local["ik_failures"].append(f"{tool_length}:{hover}:{approach}:{depth}:{phase}")
                        break
                    seed = solved[phase]
                if len(solved) != 3 or any(value is None for value in solved.values()):
                    continue
                transit, failure = _clearance_route(
                    world, start=selected_park, end=solved["HOVER"], end_xyz=points["HOVER"],
                    tool_length=tool_length,
                    transit_z=spec["transit_height_board_z_mm_range"][1],
                    samples=spec["samples_per_cartesian_leg"])
                if failure:
                    local["ik_failures"].append(f"TRANSIT:{failure}")
                    continue
                labelled = list(transit)
                labelled.extend(("APPROACH", row) for row in _interpolate(
                    solved["HOVER"], solved["APPROACH"], spec["samples_per_cartesian_leg"]))
                labelled.extend(("PRESS", row) for row in _interpolate(
                    solved["APPROACH"], solved["PRESS"], spec["samples_per_cartesian_leg"]))
                labelled.extend(("RETRACT", row) for row in _interpolate(
                    solved["PRESS"], solved["HOVER"], spec["samples_per_cartesian_leg"]))
                for cable_endpoint in cables:
                    for phase, joints in labelled:
                        pairs = _concerning(
                            world.evaluate(contract, joints, cable_endpoint), expected,
                            phase=phase, pad_expected=pad_spec["expected_contact_pair"])
                        local["evaluations"] += 1
                        local["concerning"] += int(bool(pairs))
                        for pair in pairs:
                            by_phase = local["phase_pairs"].setdefault(phase, {})
                            by_phase[pair] = by_phase.get(pair, 0) + 1
        local["clear"] = local["concerning"] == 0 and not local["ik_failures"]
        local["status"] = "CLEAR_EXPLORATORY_DISCRETE" if local["clear"] else "STOP"
        pad_rows.append(local)

    cable_link4 = "attachment:moving_cable|robot:link4"
    cable_link4_by_stage_phase = {
        stage: {phase: pairs.get(cable_link4, 0)
                for phase, pairs in row["phase_pairs"].items()}
        for stage, row in robust.items()
    }
    result = {
        "schema": "tactevra.first_motion_clearance_waypoint_result.v1",
        "scope": SCOPE, "fixture_sha256": fixture["fixture_sha256"],
        "park_path_feasibility_ranking": park_rows,
        "robust_stage_results": robust,
        "cable_link4_by_stage_phase": cable_link4_by_stage_phase,
        "swappable_pad_results": pad_rows,
        "ik_failures": sorted(set(failures)),
        "selected_park_for_pad_simulation": park_rows[0]["pose_id"],
        "rrt_connect_required": not any(row["feasible_target_count"] == len(targets)
                                         for row in park_rows),
        "production_planner_installed": False,
        "installed_collision_geometry_changed": False,
        "installed_exclusions_created": 0,
        "official_readiness_changed": False,
        "hardware_write_count": 0, "physical_movement_count": 0,
        "real_command_count": 0, "permit_count": 0, "transport_count": 0,
        "physical_authority": False,
    }
    result["decision"] = (
        "PASS_EXPLORATORY_DISCRETE_DESIGN" if all(row["clear"] for row in robust.values())
        and any(row["clear"] for row in pad_rows)
        else "STOP_ROUTE_OR_PAD_REFINEMENT_REQUIRED")
    result["receipt_sha256"] = _sha(result)
    return result


def run_passive_tool_first_motion_rerun(
    fixture: dict[str, Any], *, workspace: Path,
) -> dict[str, Any]:
    """Screen the selected passive-tool A-F shadow without cable geometry."""

    design_path = Path(fixture["bindings"]["collision_design_fixture"]["path"])
    if not design_path.is_absolute():
        design_path = workspace / design_path
    design = json.loads(design_path.read_text(encoding="utf-8"))
    world = _World(design, workspace)

    emulator_path = Path(fixture["bindings"]["emulator_fixture"]["path"])
    if not emulator_path.is_absolute():
        emulator_path = workspace / emulator_path
    baseline = tuple(_baseline_joints(load_emulator_fixture(emulator_path))[:5])

    park_report = json.loads(Path(fixture["bindings"]["park_screen"]["path"]).read_text())
    spec = fixture["waypoint_rerun"]
    park_row = next(
        row for row in park_report["top_candidates"]
        if row["pose_id"] == spec["park_pose_id"]
    )
    park = tuple(
        park_row["joint_positions_rad"][name]
        for name in world.pose_bundle["joint_order"]
    )

    attribution_path = Path(fixture["bindings"]["attribution_fixture"]["path"])
    if not attribution_path.is_absolute():
        attribution_path = workspace / attribution_path
    attribution = load_collision_attribution_fixture(attribution_path)
    expected = set(attribution["contact_classes"]["DECLARED_EXPECTED_BUT_UNREVIEWED"])
    tools = list(product(spec["tool_length_mm_range"], spec["tool_radius_mm_range"]))
    targets = {row["target_id"]: row for row in world.pose_bundle["poses"]}

    stage_rows = {
        stage: {
            "stage": stage,
            "evaluations": 0,
            "concerning": 0,
            "phase_pairs": {},
            "ik_failures": [],
        }
        for stage in "ABCEF"
    }

    def record(stage: str, phase: str, pairs: Iterable[str]) -> None:
        remaining = _concerning(pairs, expected, phase=phase)
        row = stage_rows[stage]
        row["evaluations"] += 1
        row["concerning"] += int(bool(remaining))
        by_phase = row["phase_pairs"].setdefault(phase, {})
        for pair in remaining:
            by_phase[pair] = by_phase.get(pair, 0) + 1

    # A: the previously frozen small base-joint range, now screened with no cable.
    for tool_length, tool_radius in tools:
        contract = world.contract(
            tool_length=tool_length, tool_radius=tool_radius, pad=None,
            include_moving_cable=False,
        )
        for delta in spec["stage_a_base_delta_rad"]:
            end = list(baseline)
            end[0] += delta
            for joints in _interpolate(baseline, tuple(end), 33):
                record("A", "SMALL_JOINT_MOVE", world.evaluate(contract, joints, None))

    # B: baseline to the route-aware park through rise, transit, and descend.
    for tool_length, tool_radius in tools:
        contract = world.contract(
            tool_length=tool_length, tool_radius=tool_radius, pad=None,
            include_moving_cable=False,
        )
        park_xyz = _tip_xyz(world, park, tool_length)
        for transit_z in spec["transit_height_board_z_mm_range"]:
            route, failure = _clearance_route(
                world, start=baseline, end=park, end_xyz=park_xyz,
                tool_length=tool_length, transit_z=transit_z,
                samples=spec["samples_per_cartesian_leg"],
            )
            if failure:
                stage_rows["B"]["ik_failures"].append(
                    f"{tool_length}:{tool_radius}:{transit_z}:{failure}")
            for phase, joints in route:
                record("B", phase, world.evaluate(contract, joints, None))

    # C: park to G hover across every frozen tool, transit, and hover endpoint.
    target = targets[spec["stage_c_target_id"]]
    xyz = target["contact_target_board_mm"]
    for tool_length, tool_radius in tools:
        contract = world.contract(
            tool_length=tool_length, tool_radius=tool_radius, pad=None,
            include_moving_cable=False,
        )
        solver = world.solver(tool_length)
        for transit_z, hover in product(
            spec["transit_height_board_z_mm_range"],
            spec["stage_c_hover_height_above_contact_mm_range"],
        ):
            end_xyz = (xyz["x"], xyz["y"], xyz["z"] + hover)
            end = _solve_seeded(world, solver, end_xyz, park)
            if end is None:
                stage_rows["C"]["ik_failures"].append(
                    f"{tool_length}:{tool_radius}:{transit_z}:{hover}:DESTINATION_IK")
                continue
            route, failure = _clearance_route(
                world, start=park, end=end, end_xyz=end_xyz,
                tool_length=tool_length, transit_z=transit_z,
                samples=spec["samples_per_cartesian_leg"],
            )
            if failure:
                stage_rows["C"]["ik_failures"].append(
                    f"{tool_length}:{tool_radius}:{transit_z}:{hover}:{failure}")
            for phase, joints in route:
                record("C", phase, world.evaluate(contract, joints, None))

    # E/F: exact bound keyboard target poses under the same passive-tool inventory.
    for tool_length, tool_radius in tools:
        contract = world.contract(
            tool_length=tool_length, tool_radius=tool_radius, pad=None,
            include_moving_cable=False,
        )
        for target_id, target_row in targets.items():
            joints = tuple(target_row["joint_positions_rad"])
            pairs = world.evaluate(contract, joints, None)
            record("E", target_id, pairs)
            record("F", target_id, pairs)

    for row in stage_rows.values():
        if not all(math.isfinite(value) for value in (
            row["evaluations"], row["concerning"],
        )):
            raise ValueError("nonfinite stage counter")
        row["clear"] = row["concerning"] == 0 and not row["ik_failures"]
        row["status"] = (
            "CLEAR_EXPLORATORY_DISCRETE" if row["clear"] else "STOP"
        )

    pad_result = json.loads(
        Path(fixture["bindings"]["passive_pad_result"]["path"]).read_text())
    pad_mode = fixture["shadow_rehearsal"]["stage_d_mode"]
    pad_row = next(row for row in pad_result["pad_contact_screen"] if row["mode"] == pad_mode)
    stage_d = {
        "stage": "D",
        "source_receipt_sha256": pad_result["receipt_sha256"],
        "mode": pad_mode,
        "evaluations": pad_row["evaluations"],
        "concerning": pad_row["concerning"],
        "tool_pad_contacts": pad_row["tool_pad_contacts"],
        "noncontiguous_contact_sequences": pad_row["noncontiguous_contact_sequences"],
        "pairs": pad_row["pairs"],
        "clear": pad_row["status"] == "CLEAR_EXPLORATORY_DISCRETE",
        "status": pad_row["status"],
    }

    ordered = [stage_rows[stage] if stage != "D" else stage_d for stage in "ABCDEF"]
    all_clear = all(row["clear"] for row in ordered)
    result = {
        "schema": "tactevra.first_motion_passive_tool_rerun_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "attachment_configuration": fixture["attachment_configuration"],
        "selected_park_pose_id": spec["park_pose_id"],
        "clearance_waypoint_results": {
            "B": stage_rows["B"],
            "C": stage_rows["C"],
        },
        "stage_results": ordered,
        "stages_exercised": list("ABCDEF"),
        "decision": (
            "PASS_A_TO_F_SHADOW_COVERAGE_PASSIVE_TOOL_SIMULATION_ONLY"
            if all_clear else "STOP_PASSIVE_TOOL_STAGE_BLOCKER_RETAINED"
        ),
        "official_readiness": fixture["shadow_rehearsal"][
            "official_readiness_must_remain"],
        "official_readiness_changed": False,
        "installed_collision_geometry_changed": False,
        "installed_exclusions_created": 0,
        "production_motion_policy_created": False,
        "optional_arm_camera_route_changed": False,
        "staged_motion_executions": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
        "limitations": [
            "All geometry and route endpoints remain exploratory simulation inputs.",
            "Discrete samples do not prove continuous swept-volume clearance.",
            "The corrected tray result is bound evidence rather than a second pad rescore.",
            "Fixed workcell cables are unmodeled pending physical measurement.",
            "No installed collision profile or physical plant bound is qualified.",
        ],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def run_target_contact_cad_refinement(
    fixture: dict[str, Any], *, workspace: Path,
) -> dict[str, Any]:
    """Resolve C/E/F tool contacts with controlled CAD and per-key geometry."""

    prior_fixture_path = Path(fixture["bindings"]["prior_fixture"]["path"])
    if not prior_fixture_path.is_absolute():
        prior_fixture_path = workspace / prior_fixture_path
    prior_fixture = load_passive_tool_rerun_fixture(prior_fixture_path)
    design_path = Path(prior_fixture["bindings"]["collision_design_fixture"]["path"])
    if not design_path.is_absolute():
        design_path = workspace / design_path
    world = _World(json.loads(design_path.read_text(encoding="utf-8")), workspace)

    park_report = json.loads(Path(fixture["bindings"]["park_screen"]["path"]).read_text())
    stage_c = fixture["stage_c"]
    park_row = next(row for row in park_report["top_candidates"]
                    if row["pose_id"] == stage_c["park_pose_id"])
    park = tuple(park_row["joint_positions_rad"][name]
                 for name in world.pose_bundle["joint_order"])
    targets = {row["target_id"]: row for row in world.pose_bundle["poses"]}
    if len(targets) != 46:
        raise ValueError("successor requires the exact 46-target pose bundle")

    station_trees = _station_voxel_trees(fixture, workspace)
    tool_spec = fixture["tool_component_model"]
    key_spec = fixture["keycap_contact"]
    profiles = list(product(
        tool_spec["total_hand_tcp_to_tip_length_mm"],
        tool_spec["distal_tip_exposed_length_mm"],
        tool_spec["distal_tip_radius_mm"],
    ))
    discretizations = list(product(
        fixture["station_cad"]["voxel_pitch_mm"],
        fixture["station_cad"]["tool_axis_sample_spacing_mm"],
    ))
    key_shapes = list(product(
        key_spec["keycap_width_height_mm"], key_spec["keycap_thickness_mm"]))
    key_geometries = {
        (float(width), float(thickness)): _keycap_geometry(
            targets, width_mm=width, thickness_mm=thickness)
        for width, thickness in key_shapes}

    stage_c_counts: dict[tuple[Any, ...], int] = {}
    press_counts: dict[tuple[Any, ...], int] = {}
    ik_failures: list[str] = []
    c_contact_sets: dict[tuple[float, float], set[tuple[Any, ...]]] = {
        tuple(map(float, row)): set() for row in discretizations}
    press_contact_sets: dict[tuple[float, float], set[tuple[Any, ...]]] = {
        tuple(map(float, row)): set() for row in discretizations}

    def count(store: dict[tuple[Any, ...], int], key: tuple[Any, ...]) -> None:
        store[key] = store.get(key, 0) + 1

    # Stage C: all targets, not the prior G-only route. Kinematic routes are
    # reused across appearance-only tip/collar endpoints without changing the
    # frozen population.
    for target_id, target in targets.items():
        xyz = target["contact_target_board_mm"]
        for tool_length in tool_spec["total_hand_tcp_to_tip_length_mm"]:
            solver = world.solver(tool_length)
            route_rows = {}
            for transit_z, hover in product(
                stage_c["transit_height_board_z_mm"],
                stage_c["hover_height_above_contact_mm"],
            ):
                end_xyz = (xyz["x"], xyz["y"], xyz["z"] + hover)
                end = _solve_seeded(world, solver, end_xyz, park)
                if end is None:
                    ik_failures.append(
                        f"C:{target_id}:{tool_length}:{transit_z}:"
                        f"{hover}:DESTINATION_IK")
                    continue
                route, failure = _clearance_route(
                    world, start=park, end=end, end_xyz=end_xyz,
                    tool_length=tool_length, transit_z=transit_z,
                    samples=stage_c["samples_per_cartesian_leg"])
                if failure:
                    ik_failures.append(
                        f"C:{target_id}:{tool_length}:{transit_z}:"
                        f"{hover}:{failure}")
                route_rows[(transit_z, hover)] = [
                    (sample_index, phase, _hand_board_transform(world, joints))
                    for sample_index, (phase, joints) in enumerate(route)]
            for exposed_length, tip_radius in product(
                tool_spec["distal_tip_exposed_length_mm"],
                tool_spec["distal_tip_radius_mm"],
            ):
                components = _component_profiles(
                    tool_spec, tool_length=tool_length,
                    exposed_length=exposed_length, tip_radius=tip_radius)
                for (transit_z, hover), route in route_rows.items():
                    for sample_index, phase, transform in route:
                        for spacing in fixture["station_cad"][
                                "tool_axis_sample_spacing_mm"]:
                            points_by_component = {
                                component["component"]: _component_axis_points(
                                    transform, component, spacing)
                                for component in components}
                            key_contacts = {}
                            for component in components:
                                points = points_by_component[component["component"]]
                                for width, thickness in key_shapes:
                                    key_contacts[(
                                        component["component"], width, thickness
                                    )] = _keycap_contacts(
                                        points, component=component["component"],
                                        radius_mm=component["radius_mm"],
                                        spacing_mm=spacing,
                                        geometry=key_geometries[
                                            (float(width), float(thickness))])
                            for pitch in fixture["station_cad"]["voxel_pitch_mm"]:
                                disc = (float(pitch), float(spacing))
                                for component in components:
                                    points = points_by_component[component["component"]]
                                    for station in _station_contacts(
                                        points, radius_mm=component["radius_mm"],
                                        spacing_mm=spacing, pitch_mm=pitch,
                                        station_trees=station_trees[float(pitch)]):
                                        identity = (
                                            target_id, phase, sample_index, tool_length,
                                            exposed_length, tip_radius, transit_z, hover,
                                            component["component"], "STATION",
                                            station["station_id"], None, None)
                                        c_contact_sets[disc].add(identity)
                                        count(stage_c_counts,
                                              identity[:2] + identity[8:11])
                                    for width, thickness in key_shapes:
                                        for key in key_contacts[(
                                                component["component"], width, thickness)]:
                                            identity = (
                                                target_id, phase, sample_index, tool_length,
                                                exposed_length, tip_radius, transit_z, hover,
                                                component["component"], "KEYCAP",
                                                key["target_id"], width, thickness)
                                            c_contact_sets[disc].add(identity)
                                            count(stage_c_counts,
                                                  identity[:2] + identity[8:11]
                                                  + (width, thickness))

    # E/F: exact press poses. Only target-tip contact is admitted.
    missing_target_contacts = 0
    for requested_id, target in targets.items():
        joints = tuple(target["joint_positions_rad"])
        transform = _hand_board_transform(world, joints)
        for tool_length, exposed_length, tip_radius in profiles:
            components = _component_profiles(
                tool_spec, tool_length=tool_length,
                exposed_length=exposed_length, tip_radius=tip_radius)
            for pitch, spacing in discretizations:
                disc = (float(pitch), float(spacing))
                component_points = {
                    row["component"]: _component_axis_points(transform, row, spacing)
                    for row in components}
                by_component = {row["component"]: row for row in components}
                for component_name, points in component_points.items():
                    component = by_component[component_name]
                    for station in _station_contacts(
                        points, radius_mm=component["radius_mm"],
                        spacing_mm=spacing, pitch_mm=pitch,
                        station_trees=station_trees[float(pitch)]):
                        identity = (requested_id, tool_length, exposed_length,
                                    tip_radius, component_name, "STATION",
                                    station["station_id"], None, None)
                        press_contact_sets[disc].add(identity)
                        count(press_counts, identity[:1] + identity[4:7])
                for width, thickness in key_shapes:
                    tip_touched_target = False
                    for component_name, points in component_points.items():
                        component = by_component[component_name]
                        contacts = _keycap_contacts(
                            points, component=component_name,
                            radius_mm=component["radius_mm"], spacing_mm=spacing,
                            geometry=key_geometries[(float(width), float(thickness))])
                        for contact in contacts:
                            admitted = (component_name == "DISTAL_TIP"
                                        and contact["target_id"] == requested_id)
                            tip_touched_target |= admitted
                            if admitted:
                                continue
                            identity = (requested_id, tool_length, exposed_length,
                                        tip_radius, component_name, "KEYCAP",
                                        contact["target_id"], width, thickness)
                            press_contact_sets[disc].add(identity)
                            count(press_counts, identity[:1] + identity[4:])
                    if not tip_touched_target:
                        missing_target_contacts += 1
                        identity = (requested_id, tool_length, exposed_length,
                                    tip_radius, "DISTAL_TIP", "MISSING_TARGET",
                                    requested_id, width, thickness)
                        press_contact_sets[disc].add(identity)
                        count(press_counts, identity[:1] + identity[4:])

    def disagreements(sets: dict[tuple[float, float], set[tuple[Any, ...]]]):
        union = set().union(*sets.values())
        common = set.intersection(*sets.values())
        return sorted(union - common, key=repr)

    c_disagreements = disagreements(c_contact_sets)
    press_disagreements = disagreements(press_contact_sets)
    c_union = set().union(*c_contact_sets.values())
    press_union = set().union(*press_contact_sets.values())

    def compact_counts(values: dict[tuple[Any, ...], int]) -> list[dict[str, Any]]:
        return [{"identity": list(key), "count": value}
                for key, value in sorted(values.items(), key=lambda item: repr(item[0]))]

    prior_result = json.loads(Path(fixture["bindings"]["prior_result"]["path"])
                              .read_text(encoding="utf-8"))
    result = {
        "schema": "tactevra.first_motion_target_contact_cad_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "prior_result_receipt_sha256": prior_result["receipt_sha256"],
        "selected_park_pose_id": stage_c["park_pose_id"],
        "target_count": len(targets),
        "target_ids": sorted(targets),
        "station_voxel_point_counts": {
            str(pitch): {name: row["point_count"] for name, row in stations.items()}
            for pitch, stations in station_trees.items()},
        "stage_c": {
            "contact_identity_count": len(c_union),
            "discretization_disagreement_count": len(c_disagreements),
            "ik_failures": sorted(ik_failures),
            "counts_by_target_phase_component_surface": compact_counts(stage_c_counts),
            "clear": not c_union and not c_disagreements and not ik_failures,
        },
        "stage_e_f": {
            "contact_identity_count": len(press_union),
            "discretization_disagreement_count": len(press_disagreements),
            "missing_target_contact_observations": missing_target_contacts,
            "counts_by_target_component_surface": compact_counts(press_counts),
            "clear": not press_union and not press_disagreements,
        },
        "discretization_disagreements": {
            "stage_c": [list(row) for row in c_disagreements],
            "stage_e_f": [list(row) for row in press_disagreements],
        },
        "decision": "PASS_EXPLORATORY_TARGET_CONTACT_SCREEN" if (
            not c_union and not c_disagreements and not ik_failures
            and not press_union and not press_disagreements
        ) else "STOP_TARGET_CONTACT_OR_CAD_REFINEMENT_REQUIRED",
        "official_readiness": "NOT_READY_FOR_FIRST_POWERED_MOTION",
        "official_readiness_changed": False,
        "installed_collision_geometry_changed": False,
        "production_motion_policy_created": False,
        "evaluation_opened": False,
        "gpu_job_count": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
        "runtime_stack": fixture["runtime_stack"],
        "limitations": [
            "Station occupancy is derived from non-watertight controlled STL at two frozen voxel pitches.",
            "Passive stylus exposure and exact assembly transform remain unmeasured ranges.",
            "Keycaps remain ranged WS2 boxes rather than measured installed key geometry.",
            "Discrete route samples do not prove continuous swept-volume clearance.",
            "Consistency with shared CAD does not qualify physical dimensional accuracy.",
        ],
    }
    result["receipt_sha256"] = _sha(result)
    return result


__all__ = [
    "bind_pose_bundle_tool_configuration",
    "load_passive_tool_rerun_fixture",
    "load_target_contact_cad_fixture",
    "load_tool_bound_exact_clearance_fixture",
    "load_waypoint_fixture",
    "run_clearance_waypoint_study",
    "run_passive_tool_first_motion_rerun",
    "run_target_contact_cad_refinement",
    "solve_tool_bound_pose_families",
    "tool_configuration",
    "validate_pose_bundle_tool_configuration",
]
