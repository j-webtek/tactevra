"""CPU-only exploratory harnesses for the governed simulation program.

This module has zero hardware, command, permit, transport, or physical authority.
The external 80-target catalog is a labelled shadow input and is never installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
from typing import Any

from .adapter import compile_virtual_us_sticky_keys, replay_virtual_us_sticky_keys

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
CANDIDATE_MODE = "EXPLORATORY_UNINSTALLED_CANDIDATE80"
COLLISION_CANDIDATE_MODE = "EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_program_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("simulation-program fixture hash mismatch")
    value["fixture_sha256"] = claimed
    if value["scope"] != SCOPE or value["gpu_execution_authorized"]:
        raise ValueError("fixture is not CPU-only zero-authority")
    if any(value["counters"].values()):
        raise ValueError("fixture contains authority-bearing counters")
    for name, section in value["sections"].items():
        expected = section.pop("section_sha256")
        actual = _sha(section)
        section["section_sha256"] = expected
        if actual != expected:
            raise ValueError(f"section hash mismatch: {name}")
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = path.resolve().parents[4] / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source changed: {binding['path']}")
    return value


def _catalog_ids(document: dict[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    for row in document["keyboard"].get("rows", []):
        ids.extend(row["key_ids"])
    ids.extend(document["keyboard"].get("explicit_targets", {}).keys())
    return tuple(dict.fromkeys(ids))


def candidate_catalog_semantic_check(fixture: dict[str, Any]) -> dict[str, Any]:
    installed = json.loads(Path(fixture["bindings"]["installed_catalog"]["path"]).read_text())
    candidate = json.loads(Path(fixture["bindings"]["candidate_catalog"]["path"]).read_text())
    installed_ids, candidate_ids = _catalog_ids(installed), _catalog_ids(candidate)
    rejection = None
    try:
        compile_virtual_us_sticky_keys("Hello 2026!", commissioned_key_ids=installed_ids)
    except ValueError as exc:
        rejection = str(exc)
    if rejection is None or "SHIFT" not in rejection:
        raise AssertionError("installed catalog did not preserve expected SHIFT rejection")
    receipts = []
    for text in fixture["sections"]["workstream_1_cpu"]["candidate_cases"]:
        targets = compile_virtual_us_sticky_keys(text, commissioned_key_ids=candidate_ids)
        replay = replay_virtual_us_sticky_keys(targets, five_shift_shortcut_disabled=True,
                                               turn_off_on_two_keys_disabled=True)
        if replay["text"] != text:
            raise AssertionError("candidate shadow replay altered requested text")
        receipts.append({"text": text, "targets": list(targets),
                         "replayed_text": replay["text"]})
    return {"mode": CANDIDATE_MODE, "candidate_installed": False,
            "candidate_target_count": len(candidate_ids),
            "installed_target_count": len(installed_ids),
            "installed_expected_rejection": rejection, "cases": receipts}


def actuation_smoke(fixture: dict[str, Any]) -> dict[str, Any]:
    section = fixture["sections"]["workstream_2"]
    rows = []
    for travel in section["travel_mm"]:
        for fraction in section["actuation_fraction"]:
            for depth in section["press_depth_mm"]:
                for dwell in section["dwell_ms"]:
                    actuated = depth >= travel * fraction
                    repeated = actuated and dwell >= min(section["repeat_delay_ms"])
                    rows.append((actuated, repeated))
    singles = sum(actuated and not repeated for actuated, repeated in rows)
    if not singles:
        raise AssertionError("analytic key model has no single-actuation smoke cell")
    return {"status": "CPU_ANALYTIC_SMOKE_ONLY", "key_cells": len(rows),
            "single_actuation_cells": singles,
            "phone_cells": len(section["phone_duration_ms"]) * len(section["phone_long_press_ms"]),
            "finite": True}


def recovery_sweep(fixture: dict[str, Any]) -> dict[str, Any]:
    recoverable = {"MISSED_PRESS", "WRONG_KEY", "DOUBLE_PRESS", "STALE_FRAME",
                   "TARGET_DISPLACEMENT"}
    rows = []
    for fault in fixture["sections"]["workstream_4"]["faults"]:
        if fault == "AMBIGUOUS_READBACK":
            path, recovered = ["VERIFY", "STOP", "ABORT"], False
        elif fault in {"WRONG_KEY", "DOUBLE_PRESS"}:
            path = ["VERIFY", "STOP", "REOBSERVE", "RELOCALIZE",
                    "BACKSPACE_CORRECT", "VERIFY", "COMPLETE"]
            recovered = True
        else:
            path = ["VERIFY", "STOP", "REOBSERVE", "RELOCALIZE",
                    "SIMULATE_PRESS", "VERIFY", "COMPLETE"]
            recovered = True
        rows.append({"fault": fault, "path": path, "detected": True,
                     "recovered": recovered,
                     "wrong_characters_before_detection": int(fault in {"WRONG_KEY", "DOUBLE_PRESS"})})
    if any(row["recovered"] != (row["fault"] in recoverable) for row in rows):
        raise AssertionError("recovery classification changed")
    return {"status": "CPU_STATE_MACHINE_COMPLETE", "cases": rows,
            "recoverable_success_rate": 1.0, "ambiguous_continuations": 0}


def continuous_policy_smoke(fixture: dict[str, Any]) -> dict[str, Any]:
    candidate = json.loads(Path(fixture["bindings"]["candidate_catalog"]["path"]).read_text())
    ids = _catalog_ids(candidate)
    section = fixture["sections"]["workstream_3"]
    pairs = len(ids) * len(ids)
    if pairs != 2601 or not all(value > 0 for value in section["hover_mm"]):
        raise AssertionError("continuous-policy pair space or hover range changed")
    return {"status": "CPU_ENUMERATION_READY_GPU_SCREENING_DEFERRED",
            "catalog_mode": CANDIDATE_MODE, "target_count": len(ids),
            "ordered_pair_count": pairs, "self_transition_count": len(ids),
            "policy_cells": pairs * len(section["hover_mm"]) * len(section["transition_mm_s"]),
            "recommended_policy": None}


def mid_motion_mask_smoke(fixture: dict[str, Any]) -> dict[str, Any]:
    section = fixture["sections"]["workstream_6"]
    # Synthetic rectangles exercise positive overlap, uncovered admission, and
    # conservative covered-target abstention without rendering any pixels.
    arm = (20, 20, 60, 60)
    targets = {"covered": (40, 40, 50, 50), "clear": (70, 70, 80, 80)}
    def overlap(a: tuple[int, ...], b: tuple[int, ...]) -> int:
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
            0, min(a[3], b[3]) - max(a[1], b[1]))
    decisions = {name: "ABSTAIN_ARM_COVERED" if overlap(arm, box) else "ELIGIBLE_FOR_OBSTRUCTION_CHECK"
                 for name, box in targets.items()}
    if overlap(arm, targets["covered"]) <= 0 or decisions["clear"].startswith("ABSTAIN"):
        raise AssertionError("mid-motion positive-overlap sentinel failed")
    return {"status": "CPU_MASK_SENTINEL_READY_ISAAC_DEFERRED",
            "positive_arm_mask_overlap": True, "decisions": decisions,
            "exposure_cases": len(section["exposure_seconds"]),
            "camera_height_cases": len(section["camera_height_mm"]),
            "physical_mid_motion_use": "BLOCKED"}


def calibration_budget(fixture: dict[str, Any]) -> dict[str, Any]:
    section = fixture["sections"]["workstream_5"]
    rng = random.Random(section["seed"])
    trials = section["trials"]
    q_index = math.ceil(section["confidence_quantile"] * trials) - 1
    table = []
    for noise in section["noise_mm"]:
        for bias in section["initial_bias_mm"]:
            for target in section["residual_fraction"]:
                selected, observed = None, None
                for count in section["probe_counts"]:
                    ratios = []
                    for _ in range(trials):
                        mean = sum(bias + rng.gauss(0.0, noise) for _ in range(count)) / count
                        ratios.append(abs(bias - mean) / bias)
                    observed = sorted(ratios)[q_index]
                    if observed <= target:
                        selected = count
                        break
                table.append({"noise_mm": noise, "initial_bias_mm": bias,
                              "target_fraction": target, "selected_probes": selected,
                              "q95_residual_fraction": observed,
                              "status": "ADMITTED" if selected else "INSUFFICIENT_THROUGH_34"})
    counts = [r["selected_probes"] for r in table if r["selected_probes"]]
    seconds = ([51 * min(counts) * min(section["probe_seconds"]),
                51 * max(counts) * max(section["probe_seconds"])] if counts else None)
    intervals = [margin / rate for margin in (0.5, 3.0)
                 for rate in section["translational_drift_mm_per_hour"]]
    return {"status": "EXPLORATORY_CPU_COMPLETE", "rows": table,
            "admitted_rows": len(counts), "failed_rows": len(table) - len(counts),
            "commissioning_seconds_range": seconds,
            "recalibration_hours_range": [min(intervals), max(intervals)]}


def calibration_attribution(fixture: dict[str, Any]) -> dict[str, Any]:
    receipt = json.loads(Path(fixture["bindings"]["ws5_cpu_receipt"]["path"]).read_text())
    rows = receipt["workstream_5"]["rows"]
    sentinel = fixture["sections"]["workstream_5_attribution"]["outcome_for_insufficient_cells"]
    outcomes = [row["selected_probes"] or sentinel for row in rows]
    grand = sum(outcomes) / len(outcomes)
    total_ss = sum((value - grand) ** 2 for value in outcomes)
    factors = {}
    for factor in fixture["sections"]["workstream_5_attribution"]["factors"]:
        levels = {}
        for row, outcome in zip(rows, outcomes, strict=True):
            levels.setdefault(str(row[factor]), []).append((outcome, row["selected_probes"] is None))
        between = sum(len(values) * ((sum(v for v, _ in values) / len(values)) - grand) ** 2
                      for values in levels.values())
        factors[factor] = {
            "one_way_eta_squared": 0.0 if total_ss == 0 else between / total_ss,
            "levels": {level: {"mean_outcome": sum(v for v, _ in values) / len(values),
                               "insufficient_count": sum(failed for _, failed in values),
                               "cell_count": len(values)}
                       for level, values in sorted(levels.items(), key=lambda item: float(item[0]))},
        }
    ranked = sorted(factors, key=lambda name: (-factors[name]["one_way_eta_squared"], name))
    insufficient = [row for row in rows if row["selected_probes"] is None]
    return {"status": "EXPLORATORY_CPU_ATTRIBUTION_COMPLETE", "factor_ranking": ranked,
            "factors": factors, "insufficient_cell_count": len(insufficient),
            "insufficient_cells": insufficient,
            "insufficient_noise_levels_mm": sorted({row["noise_mm"] for row in insufficient}),
            "insufficient_bias_levels_mm": sorted({row["initial_bias_mm"] for row in insufficient}),
            "visual_correction_region": "CANDIDATE_WHEN_PROBING_INSUFFICIENT_NOT_SELECTED_POLICY"}


def _binary_stl_bounds(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    triangles = struct.unpack_from("<I", raw, 80)[0]
    if len(raw) != 84 + triangles * 50:
        raise ValueError(f"unsupported or malformed binary STL: {path}")
    points = []
    for index in range(triangles):
        offset = 84 + index * 50 + 12
        points.extend(struct.unpack_from("<9f", raw, offset))
    axes = [points[index::3] for index in range(3)]
    minimum = [min(axis) for axis in axes]
    maximum = [max(axis) for axis in axes]
    return {"minimum_mm": minimum, "maximum_mm": maximum,
            "center_mm": [(a + b) / 2 for a, b in zip(minimum, maximum, strict=True)],
            "half_extents_mm": [(b - a) / 2 for a, b in zip(minimum, maximum, strict=True)],
            "triangle_count": triangles}


def collision_candidate(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    from rocell.application.collision_readiness import assess_current_collision_readiness
    from rocell.application.context import load_simulation_context

    context = load_simulation_context(workspace, workspace / "software/config/system_manifest.json")
    readiness = assess_current_collision_readiness(context).to_dict()
    reduction = json.loads(Path(fixture["bindings"]["link_box_reduction"]["path"]).read_text())
    robot = []
    for link in reduction["links"]:
        robot.append({"body_id": f"robot:{'gripper' if link['link_name'] == 'gripper_link' else link['link_name']}",
                      "parent_frame": link["link_name"], "evidence_state": "PINNED_DIGITAL_CANDIDATE",
                      "mesh_sha256": link["mesh_sha256"],
                      "primitives": [component["candidate_primitive"] for component in link["components"]]})
    workcell = [body for body in readiness["contract"]["bodies"]
                if body["body_id"].startswith("workcell:")]
    cage_path = Path(fixture["bindings"]["camera_cage_mesh"]["path"])
    carriage_path = Path(fixture["bindings"]["camera_carriage_mesh"]["path"])
    blockers = ["INSTALLED_CLAMP_GEOMETRY_UNMEASURED", "MOVING_CABLE_GEOMETRY_UNMEASURED",
                "CONTACT_TOOL_IS_RANGE_FAMILY", "ARM_ATTACHED_CAMERA_FRAMES_NOT_BOUND",
                "SELF_COLLISION_EXCLUSIONS_UNREVIEWED", "INSTALLED_PROFILE_REQUIRES_ACCEPTED_MEASURED"]
    core = {"schema": "tactevra.simulation_collision_candidate.v1", "scope": SCOPE,
            "status": "EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE_FAMILY",
            "fixture_sha256": fixture["fixture_sha256"], "installed": False,
            "installed_profile_eligible": False, "robot_bodies": robot,
            "workcell_bodies": workcell,
            "static_camera_environment": {
                "cage": {"sha256": fixture["bindings"]["camera_cage_mesh"]["sha256"],
                         "local_bounds": _binary_stl_bounds(cage_path)},
                "carriage": {"sha256": fixture["bindings"]["camera_carriage_mesh"]["sha256"],
                             "local_bounds": _binary_stl_bounds(carriage_path)},
                "placement_state": "UNBOUND_RANGE_REQUIRED"},
            "range_family": fixture["sections"]["collision_candidate"]["unmeasured_ranges"],
            "blockers": blockers, "simulation_diagnostic_ready": False,
            "hardware_write_count": 0, "physical_movement_count": 0,
            "commands": [], "physical_authority": False}
    core["candidate_sha256"] = _sha(core)
    return core


def _collision_primitive(document: dict[str, Any]):
    from rocell.geometry import Rotation3, Vec3
    from rocell.simulation.collision import OrientedBoxMm

    if document["kind"] != "oriented_box":
        raise ValueError("phase-zero reduction supports only oriented boxes")
    return OrientedBoxMm(
        Vec3(*document["center_mm"]), Vec3(*document["half_extents_mm"]),
        Rotation3(tuple(document["rotation_row_major"])),
    )


def _phase0_collision_variants(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the frozen one-factor-at-a-time family without a hidden cross product."""

    clamp = section["installed_base_clamp"]
    camera = section["static_camera"]
    cable = section["moving_cable"]
    baseline = {
        "tool_length_mm": section["tool"]["provisional_nominal_length_mm"],
        "tool_radius_mm": section["tool"]["provisional_nominal_radius_mm"],
        "clamp_x_mm": sum(clamp["arm_axis_board_x_mm_range"]) / 2,
        "clamp_half_x_mm": sum(clamp["half_extents_mm_ranges"]["x"]) / 2,
        "clamp_half_y_mm": sum(clamp["half_extents_mm_ranges"]["y"]) / 2,
        "clamp_half_z_mm": sum(clamp["half_extents_mm_ranges"]["z"]) / 2,
        "camera_height_mm": camera["height_mm_samples"][1],
        "camera_depth_mm": sum(camera["module_depth_mm_range"]) / 2,
        "cable_radius_mm": sum(cable["radius_mm_range"]) / 2,
        "cable_offset_fraction": 0.5,
        "cable_anchor_x_mm": sum(cable["route_family"]["fixed_anchor_board_x_mm_range"]) / 2,
        "cable_anchor_z_mm": sum(cable["route_family"]["fixed_anchor_board_z_mm_range"]) / 2,
        "clearance_margin_mm": sum(section["clearance_margin_mm_range"]) / 2,
    }
    axes = {
        "tool_length_mm": section["tool"]["length_mm_range"],
        "tool_radius_mm": section["tool"]["radius_mm_range"],
        "clamp_x_mm": clamp["arm_axis_board_x_mm_range"],
        "clamp_half_x_mm": clamp["half_extents_mm_ranges"]["x"],
        "clamp_half_y_mm": clamp["half_extents_mm_ranges"]["y"],
        "clamp_half_z_mm": clamp["half_extents_mm_ranges"]["z"],
        "camera_height_mm": camera["height_mm_samples"],
        "camera_depth_mm": camera["module_depth_mm_range"],
        "cable_radius_mm": cable["radius_mm_range"],
        "cable_offset_fraction": cable["configuration_samples"],
        "cable_anchor_x_mm": cable["route_family"]["fixed_anchor_board_x_mm_range"],
        "cable_anchor_z_mm": cable["route_family"]["fixed_anchor_board_z_mm_range"],
        "clearance_margin_mm": section["clearance_margin_mm_range"],
    }
    variants = [{"variant_id": "baseline", **baseline}]
    seen = {_sha(baseline)}
    for axis, values in axes.items():
        for value in values:
            row = dict(baseline)
            row[axis] = value
            digest = _sha(row)
            if digest in seen:
                continue
            seen.add(digest)
            variants.append({"variant_id": f"{axis}={value}", **row})
    return variants


def phase0_collision_intake(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    """Run a zero-authority candidate screen through the production collision kernel."""

    from rocell.application.context import load_simulation_context
    from rocell.geometry import JointPosition, RigidTransform, Rotation3, UrdfModel, Vec3
    from rocell.simulation.collision import (
        CapsuleMm, CollisionBindingMode, CollisionBody, CollisionBodyRequirement,
        CollisionBodyRole, CollisionClearanceEvidenceState, CollisionClearancePolicy,
        CollisionEvaluationPolicy, CollisionEvidenceState, CollisionGeometryContract,
        CollisionPose, OrientedBoxMm, SampledCollisionGeometry,
        audit_collision_geometry, build_roarm_m3_prehardware_collision_contract,
        evaluate_collision_pose,
    )

    section = fixture["sections"]["phase0_collision_mode"]
    if section["mode"] != COLLISION_CANDIDATE_MODE or section["installed_profile_eligible"]:
        raise ValueError("phase-zero candidate mode changed authority")
    context = load_simulation_context(workspace, workspace / "software/config/system_manifest.json")
    model = UrdfModel.from_file(context.scenario.model_path)
    base_contract = build_roarm_m3_prehardware_collision_contract(model, context.scene)
    workcell = [body for body in base_contract.bodies if body.body_id.startswith("workcell:")]
    reduction = json.loads(Path(fixture["bindings"]["link_box_reduction"]["path"]).read_text())
    pose_bundle = json.loads(Path(fixture["bindings"]["pose_bundle"]["path"]).read_text())
    overlay = pose_bundle["layout_overlay"]["board_T_vendor_world_matrix_row_major"]
    board_t_world = RigidTransform(
        "board", "world", Rotation3(tuple(overlay[index] for index in (0, 1, 2, 4, 5, 6, 8, 9, 10))),
        Vec3(overlay[3], overlay[7], overlay[11]),
    )
    robot = []
    def body_name(link: str) -> str:
        return f"robot:{'gripper' if link == 'gripper_link' else link}"
    for link in reduction["links"]:
        robot.append(CollisionBody(
            body_name(link["link_name"]), link["link_name"], CollisionBodyRole.ROBOT_LINK,
            CollisionEvidenceState.PINNED_DIGITAL,
            tuple(_collision_primitive(item["candidate_primitive"]) for item in link["components"]),
            CollisionBindingMode.RIGID_FRAME, f"mesh_sha256:{link['mesh_sha256']}",
        ))
    cage = _binary_stl_bounds(Path(fixture["bindings"]["camera_cage_mesh"]["path"]))
    carriage = _binary_stl_bounds(Path(fixture["bindings"]["camera_carriage_mesh"]["path"]))
    variants = _phase0_collision_variants(section)
    status_counts: dict[str, int] = {}
    collision_pairs: dict[str, int] = {}
    variant_rows = []
    first_audit = None
    for variant in variants:
        clamp_half = Vec3(variant["clamp_half_x_mm"], variant["clamp_half_y_mm"], variant["clamp_half_z_mm"])
        clamp = CollisionBody(
            "installation:base_and_factory_clamp", "board", CollisionBodyRole.BASE_CLAMP,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (OrientedBoxMm(Vec3(variant["clamp_x_mm"], section["installed_base_clamp"]["rear_edge_board_y_mm"], -clamp_half.z), clamp_half),),
            CollisionBindingMode.STATIC_ROOT, "frozen phase-zero unmeasured range",
        )
        camera_xy = section["static_camera"]["optical_center_board_xy_mm"]
        camera_bodies = []
        for name, bounds, binding in (("cage", cage, "camera_cage_mesh"), ("carriage", carriage, "camera_carriage_mesh")):
            local_center = bounds["center_mm"]
            camera_bodies.append(CollisionBody(
                f"static_camera:{name}", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionEvidenceState.PINNED_DIGITAL,
                (OrientedBoxMm(Vec3(camera_xy[0] + local_center[0], camera_xy[1] + local_center[1], variant["camera_height_mm"] + local_center[2]), Vec3(*bounds["half_extents_mm"])),),
                CollisionBindingMode.STATIC_ROOT, f"sha256:{fixture['bindings'][binding]['sha256']}",
            ))
        camera_bodies.append(CollisionBody(
            "static_camera:module_range", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (OrientedBoxMm(Vec3(camera_xy[0], camera_xy[1], variant["camera_height_mm"] - variant["camera_depth_mm"] / 2), Vec3(20, 20, variant["camera_depth_mm"] / 2)),),
            CollisionBindingMode.STATIC_ROOT, "frozen phase-zero depth range",
        ))
        tool = CollisionBody(
            "attachment:contact_tool", "hand_tcp", CollisionBodyRole.TOOL,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (CapsuleMm(Vec3.zero(), Vec3(0, 0, -variant["tool_length_mm"]), variant["tool_radius_mm"]),),
            CollisionBindingMode.RIGID_FRAME, "frozen phase-zero range; replaced by WS2",
        )
        cable = CollisionBody(
            "attachment:moving_cable", "board", CollisionBodyRole.CABLE,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY, (),
            CollisionBindingMode.CONFIGURATION_SAMPLED, "frozen phase-zero route family",
        )
        bodies = tuple(robot + [clamp, tool, cable] + workcell + camera_bodies)
        requirements = tuple(CollisionBodyRequirement(
            body.body_id, body.parent_frame, body.role, body.binding_mode,
            "phase-zero exploratory candidate requires complete sampled coverage",
        ) for body in bodies)
        contract = CollisionGeometryContract(
            f"TACTEVRA-PHASE0-{variant['variant_id']}", "board", requirements, bodies, (),
        )
        audit = audit_collision_geometry(contract)
        if first_audit is None:
            first_audit = audit.to_dict()
        margin = variant["clearance_margin_mm"]
        if margin == 0:
            variant_rows.append({"variant_id": variant["variant_id"], "pose_count": len(pose_bundle["poses"]),
                                 "status": "BLOCKED_ZERO_CLEARANCE_POLICY", "clear_count": 0,
                                 "collision_count": 0, "blocked_count": len(pose_bundle["poses"])})
            status_counts["BLOCKED_ZERO_CLEARANCE_POLICY"] = status_counts.get("BLOCKED_ZERO_CLEARANCE_POLICY", 0) + len(pose_bundle["poses"])
            continue
        policy = CollisionEvaluationPolicy(clearance_policy=CollisionClearancePolicy(
            margin, 0, 0, CollisionClearanceEvidenceState.SYNTHETIC_TEST_ONLY,
            "frozen phase-zero clearance range",
        ))
        local_counts = {"clear": 0, "collision": 0, "blocked": 0}
        for source_pose in pose_bundle["poses"]:
            positions = {name: JointPosition.radians(value) for name, value in zip(pose_bundle["joint_order"], source_pose["joint_positions_rad"], strict=True)}
            # The gripper joint is fixed at the frozen virtual scenario value.
            positions["link5_to_gripper_link"] = context.scenario.fixed_gripper_position
            fk = model.forward_kinematics(positions)
            transforms = {name: board_t_world.compose(transform) for name, transform in fk.items()}
            transforms["board"] = RigidTransform.identity("board")
            gripper = transforms["gripper_link"].translation_mm
            anchor = Vec3(variant["cable_anchor_x_mm"], section["moving_cable"]["route_family"]["fixed_anchor_board_y_mm"], variant["cable_anchor_z_mm"])
            midpoint = (gripper + anchor).scaled(0.5) + Vec3(0, 0, -variant["cable_offset_fraction"] * section["moving_cable"]["swept_offset_mm_range"][1])
            sampled = SampledCollisionGeometry(
                (CapsuleMm(gripper, midpoint, variant["cable_radius_mm"]), CapsuleMm(midpoint, anchor, variant["cable_radius_mm"])),
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY, "frozen phase-zero sampled cable",
            )
            pose = CollisionPose(
                f"{variant['variant_id']}:{source_pose['target_id']}", "board", transforms,
                {"attachment:moving_cable": sampled},
            )
            evaluation = evaluate_collision_pose(contract, pose, policy)
            status_counts[evaluation.status.value] = status_counts.get(evaluation.status.value, 0) + 1
            if evaluation.collision_free_diagnostic:
                local_counts["clear"] += 1
            elif evaluation.evaluation_complete:
                local_counts["collision"] += 1
                for pair in evaluation.collisions:
                    key = "|".join(sorted((pair.first_body_id, pair.second_body_id)))
                    collision_pairs[key] = collision_pairs.get(key, 0) + 1
            else:
                local_counts["blocked"] += 1
        variant_rows.append({"variant_id": variant["variant_id"], "pose_count": len(pose_bundle["poses"]),
                             "status": "SCREENED", **{f"{key}_count": value for key, value in local_counts.items()}})
    result = {
        "schema": "tactevra.phase0_collision_intake.v1", "scope": SCOPE,
        "mode": COLLISION_CANDIDATE_MODE, "installed": False,
        "installed_profile_eligible": False, "fixture_sha256": fixture["fixture_sha256"],
        "variant_count": len(variants), "pose_count_per_variant": len(pose_bundle["poses"]),
        "status_counts": status_counts, "collision_pairs": dict(sorted(collision_pairs.items())),
        "variants": variant_rows, "geometry_audit": first_audit,
        "decision": "STOP" if any(row.get("collision_count", 0) or row.get("blocked_count", 0) for row in variant_rows) else "CLEAR_EXPLORATORY_ONLY",
        "limitations": ["unmeasured candidate ranges", "no self-collision exclusions", "cannot release physical or installed collision gates"],
        "hardware_write_count": 0, "physical_movement_count": 0, "physical_authority": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


def landing_sensor_comparison(fixture: dict[str, Any]) -> dict[str, Any]:
    """Compare frozen landing-sensor ranges without selecting physical hardware."""

    section = fixture["sections"]["phase0_landing_sensors"]
    candidate = json.loads(Path(fixture["bindings"]["candidate_catalog"]["path"]).read_text())
    target_count = len(_catalog_ids(candidate))
    option_rows = []
    for option_index, (name, option) in enumerate(sorted(section["options"].items())):
        noise_values = [option["noise_mm_range"][0] + index * (option["noise_mm_range"][1] - option["noise_mm_range"][0]) / (section["noise_samples_per_range"] - 1) for index in range(section["noise_samples_per_range"])]
        cells = []
        for bias in section["bias_mm"]:
            for target in section["residual_fraction"]:
                selected = None
                worst_q95 = None
                for count in section["probe_counts"]:
                    quantiles = []
                    for noise_index, noise in enumerate(noise_values):
                        rng = random.Random(section["seed"] + option_index * 1_000_000 + int(bias * 10_000) + int(target * 100_000) + count * 100 + noise_index)
                        ratios = []
                        for _ in range(section["trial_count"]):
                            estimate = sum(bias + rng.gauss(0, noise) for _ in range(count)) / count
                            ratios.append(abs(estimate - bias) / bias)
                        quantiles.append(sorted(ratios)[math.ceil(0.95 * len(ratios)) - 1])
                    worst_q95 = max(quantiles)
                    if worst_q95 <= target:
                        selected = count
                        break
                cells.append({"bias_mm": bias, "target_fraction": target,
                              "selected_probes": selected, "worst_noise_q95_residual_fraction": worst_q95,
                              "status": "FEASIBLE" if selected else "INSUFFICIENT_THROUGH_34"})
        selected_counts = [row["selected_probes"] for row in cells if row["selected_probes"]]
        commissioning = None if not selected_counts else [
            target_count * min(selected_counts) * section["probe_seconds_range"][0],
            target_count * max(selected_counts) * section["probe_seconds_range"][1],
        ]
        option_rows.append({"option": name, "noise_mm_samples": noise_values,
                            "contact_visibility": option["contact_visibility"], "cells": cells,
                            "feasible_cells": len(selected_counts), "failed_cells": len(cells) - len(selected_counts),
                            "commissioning_seconds_range": commissioning})
    result = {"schema": "tactevra.phase0_landing_sensor_comparison.v1", "scope": SCOPE,
              "fixture_sha256": fixture["fixture_sha256"], "target_count": target_count,
              "options": option_rows, "selected_option": None,
              "overhead_camera_contact_visibility": section["overhead_camera_contact_visibility"],
              "decision": "NO_PHYSICAL_SENSOR_SELECTED_EXPLORATORY_RANGES_ONLY",
              "hardware_write_count": 0, "physical_movement_count": 0, "physical_authority": False}
    result["receipt_sha256"] = _sha(result)
    return result


def gpu_readiness(fixture: dict[str, Any]) -> dict[str, Any]:
    return {"workstream_1_isaac_subset": "WAITING_FOR_ACTIVE_96_192_JOB",
            "workstream_2_warp": "FIXTURE_AND_CPU_SMOKE_READY",
            "workstream_3_warp": "FIXTURE_READY_WAITING_FOR_WS2_GPU_RESULT",
            "workstream_4_optional_warp": "CPU_STATE_MACHINE_READY_WAITING_FOR_WS2",
            "workstream_6_isaac": "FIXTURE_READY_WAITING_FOR_WS3_TRAJECTORIES",
            "gpu_execution_authorized": fixture["gpu_execution_authorized"]}


def run_all(fixture_path: Path) -> dict[str, Any]:
    fixture = load_program_fixture(fixture_path)
    core = {"schema": "tactevra.simulation_program_cpu_receipt.v1", "scope": SCOPE,
            "fixture_sha256": fixture["fixture_sha256"],
            "runtime_stack": fixture["runtime_stack"],
            "candidate_catalog": candidate_catalog_semantic_check(fixture),
            "workstream_2_smoke": actuation_smoke(fixture),
            "workstream_3_smoke": continuous_policy_smoke(fixture),
            "workstream_4": recovery_sweep(fixture),
            "workstream_5": calibration_budget(fixture),
            "workstream_5_attribution": calibration_attribution(fixture),
            "workstream_6_smoke": mid_motion_mask_smoke(fixture),
            "gpu_readiness": gpu_readiness(fixture), "counters": fixture["counters"]}
    core["receipt_sha256"] = _sha(core)
    return core


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_all(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("schema", "scope", "receipt_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
