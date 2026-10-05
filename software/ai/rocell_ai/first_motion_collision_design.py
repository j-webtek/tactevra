"""Exploratory A-D collision design and structural-contact evidence.

This module creates no controller frame, transport, permit, or physical
authority. All dimensions are frozen candidate ranges and every exclusion is a
proposal for later human review, never an installed collision policy.
"""
from __future__ import annotations

import hashlib
from itertools import combinations, product
import json
from pathlib import Path
from typing import Any, Iterable

from rocell.application.context import load_simulation_context
from rocell.geometry import (
    JointPosition, Point3Mm, RigidTransform, Rotation3, UrdfModel, Vec3,
)
from rocell.kinematics.ik import BoardToolTipTarget, RoArmM3NumericalIk
from rocell.simulation.collision import (
    CapsuleMm, CollisionBindingMode, CollisionBody, CollisionBodyRequirement,
    CollisionBodyRole, CollisionClearanceEvidenceState, CollisionClearancePolicy,
    CollisionEvaluationPolicy, CollisionEvidenceState, CollisionGeometryContract,
    CollisionPose, OrientedBoxMm, SampledCollisionGeometry,
    build_roarm_m3_prehardware_collision_contract, evaluate_collision_pose,
)

from rocell_ai.first_motion_controller_emulator import (
    SCOPE, _baseline_joints, load_emulator_fixture,
)
from rocell_ai.first_motion_drills import load_collision_attribution_fixture
from rocell_ai.simulation_program_cpu import (
    _binary_stl_bounds, _collision_primitive, load_program_fixture,
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_collision_design_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("collision-design fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in ("cable_design", "stage_trajectories", "test_pad_design",
                 "structural_review"):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _sha(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("collision-design fixture changed zero-authority scope")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound collision-design input changed: {source}")
    return value


def _interpolate(start: tuple[float, ...], end: tuple[float, ...], count: int) -> list[tuple[float, ...]]:
    return [tuple(left + (right - left) * index / (count - 1)
                  for left, right in zip(start, end, strict=True))
            for index in range(count)]


def _pad_variants(spec: dict[str, Any]) -> list[dict[str, float]]:
    axes = {
        "center_x_mm": spec["center_board_x_mm_range"],
        "center_y_mm": spec["center_board_y_mm_range"],
        "top_z_mm": spec["top_board_z_mm_range"],
        "width_mm": spec["width_mm_range"],
        "depth_mm": spec["depth_mm_range"],
        "thickness_mm": spec["thickness_mm_range"],
    }
    baseline = {name: sum(values) / 2 for name, values in axes.items()}
    rows = [{"variant_id": "baseline", **baseline}]
    seen = {_sha(baseline)}
    for name, values in axes.items():
        for endpoint in values:
            row = dict(baseline)
            row[name] = endpoint
            digest = _sha(row)
            if digest not in seen:
                seen.add(digest)
                rows.append({"variant_id": f"{name}={endpoint}", **row})
    return rows


class _World:
    def __init__(self, fixture: dict[str, Any], workspace: Path) -> None:
        self.fixture = fixture
        self.workspace = workspace
        program_path = Path(fixture["bindings"]["program_fixture"]["path"])
        if not program_path.is_absolute():
            program_path = workspace / program_path
        self.program = load_program_fixture(program_path)
        self.section = self.program["sections"]["phase0_collision_mode"]
        self.context = load_simulation_context(
            workspace, workspace / "software/config/system_manifest.json")
        self.model = UrdfModel.from_file(self.context.scenario.model_path)
        base = build_roarm_m3_prehardware_collision_contract(
            self.model, self.context.scene)
        self.workcell = [body for body in base.bodies
                         if body.body_id.startswith("workcell:")]
        reduction = json.loads(Path(self.program["bindings"][
            "link_box_reduction"]["path"]).read_text())
        self.robot = []
        for link in reduction["links"]:
            body_id = f"robot:{'gripper' if link['link_name'] == 'gripper_link' else link['link_name']}"
            self.robot.append(CollisionBody(
                body_id, link["link_name"], CollisionBodyRole.ROBOT_LINK,
                CollisionEvidenceState.PINNED_DIGITAL,
                tuple(_collision_primitive(item["candidate_primitive"])
                      for item in link["components"]),
                CollisionBindingMode.RIGID_FRAME,
                f"mesh_sha256:{link['mesh_sha256']}",
            ))
        pose_bundle = json.loads(Path(fixture["bindings"]["pose_bundle"]["path"]).read_text())
        self.pose_bundle = pose_bundle
        overlay = pose_bundle["layout_overlay"]["board_T_vendor_world_matrix_row_major"]
        self.board_t_world = RigidTransform(
            "board", "world",
            Rotation3(tuple(overlay[index] for index in (0, 1, 2, 4, 5, 6, 8, 9, 10))),
            Vec3(overlay[3], overlay[7], overlay[11]),
        )
        self.cage = _binary_stl_bounds(Path(self.program["bindings"]["camera_cage_mesh"]["path"]))
        self.carriage = _binary_stl_bounds(Path(self.program["bindings"]["camera_carriage_mesh"]["path"]))

    def solver(self, tool_length_mm: float) -> RoArmM3NumericalIk:
        return RoArmM3NumericalIk(
            model=self.model,
            board_T_world=self.board_t_world,
            hand_tcp_to_tip_z_mm=-tool_length_mm,
            fixed_gripper_position=self.context.scenario.fixed_gripper_position,
            ready_arm_joint_positions=self.context.scenario.ready_arm_joint_positions_rad,
            gripper_bounds_rad=self.context.scenario.controller_gripper_intersection_rad,
            joint_bounds_rad=self.context.scenario.controller_joint_intersection_rad,
        )

    def solve(self, solver: RoArmM3NumericalIk, xyz: tuple[float, float, float]) -> tuple[float, ...] | None:
        result = solver.solve(BoardToolTipTarget(Point3Mm("board", *xyz)))
        if not result.converged:
            return None
        by_name = {row.name: row.position.value
                   for row in result.solution_arm_joint_positions}
        return tuple(by_name[name] for name in self.pose_bundle["joint_order"])

    def _camera_bodies(self) -> list[CollisionBody]:
        spec = self.section["static_camera"]
        xy = spec["optical_center_board_xy_mm"]
        height = spec["height_mm_samples"][-1]
        depth = spec["module_depth_mm_range"][0]
        result = []
        for name, bounds, binding in (
            ("cage", self.cage, "camera_cage_mesh"),
            ("carriage", self.carriage, "camera_carriage_mesh"),
        ):
            center = bounds["center_mm"]
            result.append(CollisionBody(
                f"static_camera:{name}", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionEvidenceState.PINNED_DIGITAL,
                (OrientedBoxMm(Vec3(xy[0] + center[0], xy[1] + center[1],
                                    height + center[2]), Vec3(*bounds["half_extents_mm"])),),
                CollisionBindingMode.STATIC_ROOT,
                f"sha256:{self.program['bindings'][binding]['sha256']}",
            ))
        result.append(CollisionBody(
            "static_camera:module_range", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (OrientedBoxMm(Vec3(xy[0], xy[1], height - depth / 2),
                           Vec3(20, 20, depth / 2)),),
            CollisionBindingMode.STATIC_ROOT, "candidate high/thin camera design",
        ))
        return result

    def contract(self, *, tool_length: float, tool_radius: float,
                 pad: dict[str, float] | None,
                 include_moving_cable: bool = True) -> CollisionGeometryContract:
        clamp_spec = self.section["installed_base_clamp"]
        half = Vec3(*(clamp_spec["half_extents_mm_ranges"][axis][0]
                      for axis in ("x", "y", "z")))
        clamp = CollisionBody(
            "installation:base_and_factory_clamp", "board",
            CollisionBodyRole.BASE_CLAMP, CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (OrientedBoxMm(Vec3(clamp_spec["arm_axis_board_x_mm_range"][0],
                                clamp_spec["rear_edge_board_y_mm"], -half.z), half),),
            CollisionBindingMode.STATIC_ROOT, "candidate minimum clamp envelope",
        )
        tool = CollisionBody(
            "attachment:contact_tool", "hand_tcp", CollisionBodyRole.TOOL,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (CapsuleMm(Vec3.zero(), Vec3(0, 0, -tool_length), tool_radius),),
            CollisionBindingMode.RIGID_FRAME, "candidate ranged tool",
        )
        attachments = [clamp, tool]
        if include_moving_cable:
            attachments.append(CollisionBody(
                "attachment:moving_cable", "board", CollisionBodyRole.CABLE,
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY, (),
                CollisionBindingMode.CONFIGURATION_SAMPLED, "candidate managed cable",
            ))
        bodies = self.robot + attachments + self.workcell + self._camera_bodies()
        if pad is not None:
            half_pad = Vec3(pad["width_mm"] / 2, pad["depth_mm"] / 2,
                            pad["thickness_mm"] / 2)
            bodies.append(CollisionBody(
                "workcell:test_pad", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
                (OrientedBoxMm(Vec3(pad["center_x_mm"], pad["center_y_mm"],
                                    pad["top_z_mm"] - half_pad.z), half_pad),),
                CollisionBindingMode.STATIC_ROOT, "candidate temporary touch surface",
            ))
        requirements = tuple(CollisionBodyRequirement(
            body.body_id, body.parent_frame, body.role, body.binding_mode,
            "exploratory design-closure coverage",
        ) for body in bodies)
        return CollisionGeometryContract(
            "TACTEVRA-COLLISION-DESIGN", "board", requirements, tuple(bodies), ())

    def evaluate(self, contract: CollisionGeometryContract, joints: tuple[float, ...],
                 cable: tuple[float, float, float, float] | None) -> set[str]:
        positions = {name: JointPosition.radians(value) for name, value in zip(
            self.pose_bundle["joint_order"], joints, strict=True)}
        positions["link5_to_gripper_link"] = self.context.scenario.fixed_gripper_position
        fk = self.model.forward_kinematics(positions)
        transforms = {name: self.board_t_world.compose(transform)
                      for name, transform in fk.items()}
        transforms["board"] = RigidTransform.identity("board")
        sampled_geometry = {}
        if cable is not None:
            gripper = transforms["gripper_link"].translation_mm
            anchor_x, anchor_z, sag, radius = cable
            cable_spec = self.section["moving_cable"]
            anchor = Vec3(anchor_x,
                          cable_spec["route_family"]["fixed_anchor_board_y_mm"], anchor_z)
            midpoint = ((gripper + anchor).scaled(0.5)
                        + Vec3(0, 0, -sag * cable_spec["swept_offset_mm_range"][1]))
            sampled_geometry["attachment:moving_cable"] = SampledCollisionGeometry(
                (CapsuleMm(gripper, midpoint, radius), CapsuleMm(midpoint, anchor, radius)),
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY, "managed cable endpoint",
            )
        evaluation = evaluate_collision_pose(
            contract,
            CollisionPose("collision-design", "board", transforms, sampled_geometry),
            CollisionEvaluationPolicy(clearance_policy=CollisionClearancePolicy(
                self.section["clearance_margin_mm_range"][1], 0, 0,
                CollisionClearanceEvidenceState.SYNTHETIC_TEST_ONLY,
                "maximum nonzero candidate clearance",
            )),
        )
        return {"|".join(sorted((row.first_body_id, row.second_body_id)))
                for row in evaluation.collisions}


def _raw_stage_trajectories(world: _World, fixture: dict[str, Any],
                            baseline: tuple[float, ...], park: tuple[float, ...],
                            tool_length: float) -> tuple[dict[str, list[tuple[float, ...]]], list[str]]:
    spec = fixture["stage_trajectories"]
    count = spec["samples_per_segment"]
    stages: dict[str, list[tuple[float, ...]]] = {"A": [], "B": [], "C": []}
    failures = []
    for delta in spec["A"]["base_delta_rad"]:
        end = list(baseline)
        end[0] += delta
        stages["A"].extend(_interpolate(baseline, tuple(end), count))
    stages["B"] = _interpolate(baseline, park, count)
    target = next(row for row in world.pose_bundle["poses"]
                  if row["target_id"] == spec["C"]["target_id"])
    solver = world.solver(tool_length)
    for hover in spec["C"]["hover_height_above_contact_mm_range"]:
        xyz = tuple(target["contact_target_board_mm"][axis] for axis in ("x", "y", "z"))
        solved = world.solve(solver, (xyz[0], xyz[1], xyz[2] + hover))
        if solved is None:
            failures.append(f"C_IK:{tool_length}:{hover}")
        else:
            stages["C"].extend(_interpolate(park, solved, count))
    return stages, failures


def _d_trajectory(world: _World, fixture: dict[str, Any], park: tuple[float, ...],
                  tool_length: float, pad: dict[str, float]) -> tuple[list[tuple[str, tuple[float, ...]]], str | None]:
    spec = fixture["test_pad_design"]
    solver = world.solver(tool_length)
    points = {
        "HOVER": (pad["center_x_mm"], pad["center_y_mm"],
                  pad["top_z_mm"] + spec["hover_mm"]),
        "APPROACH": (pad["center_x_mm"], pad["center_y_mm"],
                     pad["top_z_mm"] + spec["approach_mm"]),
        "CONTACT": (pad["center_x_mm"], pad["center_y_mm"],
                    pad["top_z_mm"] - spec["contact_overtravel_mm"]),
    }
    solved = {name: world.solve(solver, point) for name, point in points.items()}
    missing = [name for name, joints in solved.items() if joints is None]
    if missing:
        return [], f"D_IK:{pad['variant_id']}:{tool_length}:{','.join(missing)}"
    count = fixture["stage_trajectories"]["samples_per_segment"]
    labelled = []
    legs = (("TRANSIT_TO_HOVER", park, solved["HOVER"]),
            ("APPROACH", solved["HOVER"], solved["APPROACH"]),
            ("CONTACT", solved["APPROACH"], solved["CONTACT"]),
            ("RETRACT", solved["CONTACT"], solved["HOVER"]))
    for label, start, end in legs:
        assert start is not None and end is not None
        labelled.extend((label, row) for row in _interpolate(start, end, count))
    return labelled, None


def _concerning(pairs: Iterable[str], expected: set[str], *, stage: str,
                phase: str | None = None) -> set[str]:
    result = set(pairs) - expected
    tool_pad = "attachment:contact_tool|workcell:test_pad"
    if stage == "D" and phase == "CONTACT":
        result.discard(tool_pad)
    return result


def run_collision_design_closure(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    world = _World(fixture, workspace)
    emulator_path = Path(fixture["bindings"]["emulator_fixture"]["path"])
    if not emulator_path.is_absolute():
        emulator_path = workspace / emulator_path
    baseline = tuple(_baseline_joints(load_emulator_fixture(emulator_path))[:5])
    park_report = json.loads(Path(fixture["bindings"]["park_screen"]["path"]).read_text())
    park_row = next(row for row in park_report["top_candidates"]
                    if row["pose_id"] == fixture["stage_trajectories"]["B"]["park_pose_id"])
    park = tuple(park_row["joint_positions_rad"][name]
                 for name in world.pose_bundle["joint_order"])
    attribution_path = Path(fixture["bindings"]["attribution_fixture"]["path"])
    if not attribution_path.is_absolute():
        attribution_path = workspace / attribution_path
    attribution = load_collision_attribution_fixture(attribution_path)
    expected = set(attribution["contact_classes"]["DECLARED_EXPECTED_BUT_UNREVIEWED"])
    cable_spec = fixture["cable_design"]
    cables = list(product(
        cable_spec["anchor_board_x_mm_range"],
        cable_spec["anchor_height_board_z_mm_range"],
        cable_spec["maximum_sag_fraction_range"],
        cable_spec["cable_radius_mm_range"],
    ))
    tools = list(product(world.section["tool"]["length_mm_range"],
                         world.section["tool"]["radius_mm_range"]))
    pads = _pad_variants(fixture["test_pad_design"])
    stage_counts = {name: {"evaluations": 0, "concerning": 0, "pairs": {}}
                    for name in "ABCDEF"}
    failures = []
    # Cache IK trajectories by tool length; radius and cable do not change IK.
    stage_cache = {}
    d_cache = {}
    for tool_length in sorted(set(item[0] for item in tools)):
        stages, local_failures = _raw_stage_trajectories(
            world, fixture, baseline, park, tool_length)
        stage_cache[tool_length] = stages
        failures.extend(local_failures)
        for pad in pads:
            d_cache[(tool_length, pad["variant_id"])] = _d_trajectory(
                world, fixture, park, tool_length, pad)
            if d_cache[(tool_length, pad["variant_id"])][1]:
                failures.append(d_cache[(tool_length, pad["variant_id"])][1])

    def record(stage: str, pairs: set[str]) -> None:
        stage_counts[stage]["evaluations"] += 1
        if pairs:
            stage_counts[stage]["concerning"] += 1
            for pair in pairs:
                counts = stage_counts[stage]["pairs"]
                counts[pair] = counts.get(pair, 0) + 1

    for tool_length, tool_radius in tools:
        contract = world.contract(tool_length=tool_length, tool_radius=tool_radius, pad=None)
        for cable in cables:
            for stage in "ABC":
                for joints in stage_cache[tool_length][stage]:
                    record(stage, _concerning(world.evaluate(contract, joints, cable),
                                              expected, stage=stage))
            for pose in world.pose_bundle["poses"]:
                joints = tuple(pose["joint_positions_rad"])
                pairs = _concerning(world.evaluate(contract, joints, cable), expected,
                                     stage="E")
                record("E", pairs)
                record("F", pairs)
            for pad in pads:
                labelled, failure = d_cache[(tool_length, pad["variant_id"])]
                if failure:
                    continue
                pad_contract = world.contract(
                    tool_length=tool_length, tool_radius=tool_radius, pad=pad)
                for phase, joints in labelled:
                    record("D", _concerning(
                        world.evaluate(pad_contract, joints, cable), expected,
                        stage="D", phase=phase))

    for stage, row in stage_counts.items():
        row["pairs"] = dict(sorted(row["pairs"].items()))
        row["clear"] = row["concerning"] == 0 and not any(
            item.startswith(f"{stage}_IK") for item in failures)
        row["status"] = "CLEAR_EXPLORATORY_DISCRETE" if row["clear"] else "STOP"

    # Structural review uses one representative design but the full A-F pose corpus.
    reference_cable = (225.0, 100.0, 0.25, 2.0)
    reference_contract = world.contract(tool_length=80.0, tool_radius=1.0,
                                        pad=pads[0])
    corpus: list[tuple[float, ...]] = []
    for values in stage_cache[80.0].values():
        corpus.extend(values)
    labelled_d, d_failure = d_cache[(80.0, pads[0]["variant_id"])]
    if d_failure is None:
        corpus.extend(joints for _, joints in labelled_d)
    corpus.extend(tuple(row["joint_positions_rad"]) for row in world.pose_bundle["poses"])
    body_ids = [body.body_id for body in reference_contract.bodies
                if body.role in {CollisionBodyRole.ROBOT_LINK, CollisionBodyRole.TOOL,
                                 CollisionBodyRole.CABLE, CollisionBodyRole.BASE_CLAMP}]
    universe = {"|".join(sorted(pair)) for pair in combinations(body_ids, 2)}
    raw_counts = {pair: 0 for pair in universe}
    for joints in corpus:
        for pair in world.evaluate(reference_contract, joints, reference_cable):
            if pair in raw_counts:
                raw_counts[pair] += 1
    structural = []
    for pair in sorted(universe):
        count = raw_counts[pair]
        classification = ("NEVER_TOUCHING" if count == 0 else
                          "ALWAYS_TOUCHING" if count == len(corpus) else
                          "SOMETIMES_TOUCHING")
        proposed = classification == "ALWAYS_TOUCHING" and pair in expected
        structural.append({"pair": pair, "touch_count": count,
                           "pose_count": len(corpus), "classification": classification,
                           "proposed_for_human_exclusion_review": proposed})
    proposed = [row["pair"] for row in structural
                if row["proposed_for_human_exclusion_review"]]
    all_stages_clear = all(row["clear"] for row in stage_counts.values())
    report = {
        "schema": "tactevra.first_motion_collision_design_closure.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "design_population": {
            "cable_endpoint_combinations": len(cables),
            "tool_endpoint_combinations": len(tools),
            "test_pad_variants": len(pads),
        },
        "stage_results": stage_counts,
        "ik_failures": sorted(set(failures)),
        "structural_pose_count": len(corpus),
        "structural_pair_classification": structural,
        "proposed_exclusion_candidates": proposed,
        "installed_exclusions_created": 0,
        "decision": ("PASS_ALL_STAGES_EXPLORATORY_DISCRETE"
                     if all_stages_clear else "STOP_DESIGN_RANGE_OR_IK_REQUIRES_REFINEMENT"),
        "continuous_swept_volume_qualified": False,
        "official_readiness_changed": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    report["receipt_sha256"] = _sha(report)
    return report


__all__ = ["load_collision_design_fixture", "run_collision_design_closure"]
