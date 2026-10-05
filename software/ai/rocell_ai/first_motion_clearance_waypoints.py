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


__all__ = [
    "load_passive_tool_rerun_fixture",
    "load_waypoint_fixture",
    "run_clearance_waypoint_study",
    "run_passive_tool_first_motion_rerun",
]
