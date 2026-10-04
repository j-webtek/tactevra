"""CPU-only wrong-model drills for the first-motion rehearsal.

The drill runner is counterfactual analysis.  It never creates a controller
frame, permit, transport, or physical authority.  The global collision blocker
is deliberately excluded as a detector so unrelated injected defects cannot
receive false credit.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from pathlib import Path
from typing import Any

from rocell.simulation.controller import ControllerJointState, controller_forward_kinematics

from rocell_ai.first_motion_controller_emulator import (
    SCOPE,
    _baseline_joints,
    _pose,
    run_staged_bringup_rehearsal,
)
from rocell_ai.simulation_program_cpu import load_program_fixture, recovery_sweep


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _nominal_state() -> ControllerJointState:
    return ControllerJointState(0.0, 0.0, 1.475, 0.0, 0.0, math.pi - 0.75)


def _perturbed_fk(*, link: str | None = None, delta_mm: float = 0.0,
                  zero_joint: str | None = None, zero_delta_rad: float = 0.0) -> tuple[float, float, float]:
    state = _nominal_state()
    values = state.to_dict()
    if zero_joint is not None:
        values[zero_joint] += zero_delta_rad
        state = ControllerJointState(**values)
    l2 = math.hypot(236.82, 30.00) + (delta_mm if link == "l2" else 0.0)
    a2 = math.atan2(30.00, 236.82)
    l3 = 144.49 + (delta_mm if link == "l3" else 0.0)
    le = math.hypot(171.67, 13.69) + (delta_mm if link == "le" else 0.0)
    ae = math.atan2(13.69, 171.67)
    shoulder_elbow = state.elbow_rad + state.shoulder_rad
    terminal = shoulder_elbow + state.wrist_pitch_rad
    rho = (l2 * math.sin(state.shoulder_rad + a2)
           + l3 * math.sin(shoulder_elbow)
           + le * math.sin(terminal + ae))
    return (
        rho * math.cos(state.base_rad),
        rho * math.sin(state.base_rad),
        l2 * math.cos(state.shoulder_rad + a2)
        + l3 * math.cos(shoulder_elbow)
        + le * math.cos(terminal + ae),
    )


def _nominal_xyz() -> tuple[float, float, float]:
    pose = controller_forward_kinematics(_nominal_state())
    return pose.x_mm, pose.y_mm, pose.z_mm


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def load_independent_observation_fixture(path: Path) -> dict[str, Any]:
    """Load the frozen zero-authority external-observer experiment."""

    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("independent-observation fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in (
        "consequence", "silhouette_observer", "touch_surface_observer",
        "fusion", "exploratory_rehearsal",
    ):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _sha(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("independent-observation fixture changed zero-authority scope")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound independent-observation input changed: {source}")
    return value


def load_collision_attribution_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("collision-attribution fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in ("contact_classes", "favorable_endpoint_family", "stage_mapping"):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _sha(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("collision-attribution fixture changed zero-authority scope")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = root / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound collision-attribution input changed: {source}")
    return value


def run_candidate_collision_attribution(
    fixture: dict[str, Any], *, workspace: Path,
) -> dict[str, Any]:
    """Retain structural contacts and isolate favorable-endpoint workcell hits."""

    from itertools import product

    from rocell.application.context import load_simulation_context
    from rocell.geometry import JointPosition, RigidTransform, Rotation3, UrdfModel, Vec3
    from rocell.simulation.collision import (
        CapsuleMm, CollisionBindingMode, CollisionBody, CollisionBodyRequirement,
        CollisionBodyRole, CollisionClearanceEvidenceState, CollisionClearancePolicy,
        CollisionEvaluationPolicy, CollisionEvidenceState, CollisionGeometryContract,
        CollisionPose, OrientedBoxMm, SampledCollisionGeometry,
        build_roarm_m3_prehardware_collision_contract, evaluate_collision_pose,
    )
    from rocell_ai.simulation_program_cpu import (
        _binary_stl_bounds, _collision_primitive, load_program_fixture,
    )

    program_path = Path(fixture["bindings"]["program_fixture"]["path"])
    if not program_path.is_absolute():
        program_path = workspace / program_path
    program = load_program_fixture(program_path)
    section = program["sections"]["phase0_collision_mode"]
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    model = UrdfModel.from_file(context.scenario.model_path)
    base_contract = build_roarm_m3_prehardware_collision_contract(model, context.scene)
    workcell = [body for body in base_contract.bodies if body.body_id.startswith("workcell:")]
    reduction = json.loads(Path(program["bindings"]["link_box_reduction"]["path"]).read_text())
    pose_bundle = json.loads(Path(program["bindings"]["pose_bundle"]["path"]).read_text())
    overlay = pose_bundle["layout_overlay"]["board_T_vendor_world_matrix_row_major"]
    board_t_world = RigidTransform(
        "board", "world",
        Rotation3(tuple(overlay[index] for index in (0, 1, 2, 4, 5, 6, 8, 9, 10))),
        Vec3(overlay[3], overlay[7], overlay[11]),
    )
    robot = []
    for link in reduction["links"]:
        body_id = f"robot:{'gripper' if link['link_name'] == 'gripper_link' else link['link_name']}"
        robot.append(CollisionBody(
            body_id, link["link_name"], CollisionBodyRole.ROBOT_LINK,
            CollisionEvidenceState.PINNED_DIGITAL,
            tuple(_collision_primitive(item["candidate_primitive"])
                  for item in link["components"]),
            CollisionBindingMode.RIGID_FRAME, f"mesh_sha256:{link['mesh_sha256']}",
        ))
    cage = _binary_stl_bounds(Path(program["bindings"]["camera_cage_mesh"]["path"]))
    carriage = _binary_stl_bounds(Path(program["bindings"]["camera_carriage_mesh"]["path"]))
    clamp_spec = section["installed_base_clamp"]
    camera_spec = section["static_camera"]
    cable_spec = section["moving_cable"]
    endpoints = product(
        clamp_spec["arm_axis_board_x_mm_range"],
        cable_spec["configuration_samples"],
        cable_spec["route_family"]["fixed_anchor_board_x_mm_range"],
        cable_spec["route_family"]["fixed_anchor_board_z_mm_range"],
    )
    expected = set(fixture["contact_classes"]["DECLARED_EXPECTED_BUT_UNREVIEWED"])
    consequential = set(fixture["contact_classes"]["POTENTIALLY_CONSEQUENTIAL"])
    configuration_rows = []
    pair_counts: dict[str, int] = {}
    unclassified_pair_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    for config_index, (clamp_x, cable_offset, anchor_x, anchor_z) in enumerate(endpoints):
        clamp_half = Vec3(
            clamp_spec["half_extents_mm_ranges"]["x"][0],
            clamp_spec["half_extents_mm_ranges"]["y"][0],
            clamp_spec["half_extents_mm_ranges"]["z"][0],
        )
        clamp = CollisionBody(
            "installation:base_and_factory_clamp", "board", CollisionBodyRole.BASE_CLAMP,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (OrientedBoxMm(Vec3(clamp_x, clamp_spec["rear_edge_board_y_mm"],
                                -clamp_half.z), clamp_half),),
            CollisionBindingMode.STATIC_ROOT, "favorable size endpoints; route enumerated",
        )
        camera_xy = camera_spec["optical_center_board_xy_mm"]
        camera_bodies = []
        for name, bounds, binding in (
            ("cage", cage, "camera_cage_mesh"),
            ("carriage", carriage, "camera_carriage_mesh"),
        ):
            center = bounds["center_mm"]
            camera_bodies.append(CollisionBody(
                f"static_camera:{name}", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionEvidenceState.PINNED_DIGITAL,
                (OrientedBoxMm(Vec3(camera_xy[0] + center[0], camera_xy[1] + center[1],
                                    camera_spec["height_mm_samples"][-1] + center[2]),
                               Vec3(*bounds["half_extents_mm"])),),
                CollisionBindingMode.STATIC_ROOT,
                f"sha256:{program['bindings'][binding]['sha256']}",
            ))
        camera_bodies.append(CollisionBody(
            "static_camera:module_range", "board", CollisionBodyRole.STATIC_ENVIRONMENT,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (OrientedBoxMm(Vec3(camera_xy[0], camera_xy[1],
                                camera_spec["height_mm_samples"][-1]
                                - camera_spec["module_depth_mm_range"][0] / 2),
                           Vec3(20, 20, camera_spec["module_depth_mm_range"][0] / 2)),),
            CollisionBindingMode.STATIC_ROOT, "favorable size endpoint",
        ))
        tool = CollisionBody(
            "attachment:contact_tool", "hand_tcp", CollisionBodyRole.TOOL,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (CapsuleMm(Vec3.zero(), Vec3(0, 0, -section["tool"]["length_mm_range"][0]),
                       section["tool"]["radius_mm_range"][0]),),
            CollisionBindingMode.RIGID_FRAME, "favorable size endpoint",
        )
        cable = CollisionBody(
            "attachment:moving_cable", "board", CollisionBodyRole.CABLE,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY, (),
            CollisionBindingMode.CONFIGURATION_SAMPLED, "route endpoints enumerated",
        )
        bodies = tuple(robot + [clamp, tool, cable] + workcell + camera_bodies)
        requirements = tuple(CollisionBodyRequirement(
            body.body_id, body.parent_frame, body.role, body.binding_mode,
            "favorable-endpoint attribution remains exploratory",
        ) for body in bodies)
        contract = CollisionGeometryContract(
            f"TACTEVRA-ATTRIBUTION-{config_index}", "board", requirements, bodies, ())
        policy = CollisionEvaluationPolicy(clearance_policy=CollisionClearancePolicy(
            section["clearance_margin_mm_range"][1], 0, 0,
            CollisionClearanceEvidenceState.SYNTHETIC_TEST_ONLY,
            "maximum nonzero frozen clearance endpoint",
        ))
        config_pairs: dict[str, int] = {}
        config_targets: set[str] = set()
        for source_pose in pose_bundle["poses"]:
            positions = {name: JointPosition.radians(value) for name, value in zip(
                pose_bundle["joint_order"], source_pose["joint_positions_rad"], strict=True)}
            positions["link5_to_gripper_link"] = context.scenario.fixed_gripper_position
            fk = model.forward_kinematics(positions)
            transforms = {name: board_t_world.compose(transform) for name, transform in fk.items()}
            transforms["board"] = RigidTransform.identity("board")
            gripper = transforms["gripper_link"].translation_mm
            anchor = Vec3(anchor_x,
                          cable_spec["route_family"]["fixed_anchor_board_y_mm"], anchor_z)
            midpoint = ((gripper + anchor).scaled(0.5)
                        + Vec3(0, 0, -cable_offset * cable_spec["swept_offset_mm_range"][1]))
            sampled = SampledCollisionGeometry(
                (CapsuleMm(gripper, midpoint, cable_spec["radius_mm_range"][0]),
                 CapsuleMm(midpoint, anchor, cable_spec["radius_mm_range"][0])),
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY, "favorable radius route endpoint",
            )
            evaluation = evaluate_collision_pose(
                contract,
                CollisionPose(f"fav:{config_index}:{source_pose['target_id']}", "board",
                              transforms, {"attachment:moving_cable": sampled}),
                policy,
            )
            for collision_pair in evaluation.collisions:
                pair = "|".join(sorted((collision_pair.first_body_id,
                                        collision_pair.second_body_id)))
                if pair in consequential:
                    config_pairs[pair] = config_pairs.get(pair, 0) + 1
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
                    config_targets.add(source_pose["target_id"])
                    target_counts[source_pose["target_id"]] = (
                        target_counts.get(source_pose["target_id"], 0) + 1)
                elif pair not in expected:
                    # Cross-endpoint combinations can expose pairs absent from
                    # the earlier one-factor-at-a-time receipt. Retain them as
                    # no-go findings rather than silently treating them as an
                    # allowed structural contact.
                    config_pairs[pair] = config_pairs.get(pair, 0) + 1
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
                    unclassified_pair_counts[pair] = (
                        unclassified_pair_counts.get(pair, 0) + 1)
                    config_targets.add(source_pose["target_id"])
                    target_counts[source_pose["target_id"]] = (
                        target_counts.get(source_pose["target_id"], 0) + 1)
        configuration_rows.append({
            "configuration_index": config_index,
            "clamp_x_mm": clamp_x,
            "cable_offset_fraction": cable_offset,
            "cable_anchor_x_mm": anchor_x,
            "cable_anchor_z_mm": anchor_z,
            "potentially_consequential_pair_counts": dict(sorted(config_pairs.items())),
            "affected_target_count": len(config_targets),
            "potentially_consequential_collision_count": sum(config_pairs.values()),
            "corridor_clear_of_potentially_consequential_pairs": not config_pairs,
        })
    clear_configs = [row for row in configuration_rows
                     if row["corridor_clear_of_potentially_consequential_pairs"]]
    report = {
        "schema": "tactevra.first_motion_candidate_collision_attribution.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "stage_mapping": fixture["stage_mapping"],
        "configuration_count": len(configuration_rows),
        "clear_configuration_count": len(clear_configs),
        "pair_counts": dict(sorted(pair_counts.items())),
        "unclassified_pair_counts": dict(sorted(unclassified_pair_counts.items())),
        "target_counts": dict(sorted(target_counts.items())),
        "configurations": configuration_rows,
        "decision": ("FAVORABLE_ENDPOINT_ROUTE_EXISTS_FOR_E_F"
                     if clear_configs else "REDESIGN_E_F_CORRIDOR_IN_SIMULATION"),
        "official_collision_decision_changed": False,
        "installed_exclusions_created": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    report["receipt_sha256"] = _sha(report)
    return report


def _paired_gap_delta(fixture: dict[str, Any]) -> float:
    model = fixture["paired_gap_model"]["LINK_LENGTH_PLUS_JOINT_ZERO"]
    nominal = _nominal_xyz()
    state = _nominal_state()
    values = state.to_dict()
    values[model["joint"]] += math.radians(model["delta_deg"])
    changed = ControllerJointState(**values)
    l2 = math.hypot(236.82, 30.00) + model["delta_mm"]
    a2 = math.atan2(30.00, 236.82)
    l3 = 144.49
    le = math.hypot(171.67, 13.69)
    ae = math.atan2(13.69, 171.67)
    shoulder_elbow = changed.elbow_rad + changed.shoulder_rad
    terminal = shoulder_elbow + changed.wrist_pitch_rad
    rho = (l2 * math.sin(changed.shoulder_rad + a2)
           + l3 * math.sin(shoulder_elbow)
           + le * math.sin(terminal + ae))
    altered = (
        rho * math.cos(changed.base_rad), rho * math.sin(changed.base_rad),
        l2 * math.cos(changed.shoulder_rad + a2)
        + l3 * math.cos(shoulder_elbow)
        + le * math.cos(terminal + ae),
    )
    return _distance(nominal, altered)


def run_independent_observation_drills(
    fixture: dict[str, Any], wrong_model_report: dict[str, Any],
) -> dict[str, Any]:
    """Rescore retained gaps with independent simulated observations.

    The original report is immutable.  This report only adds consequence and
    detector columns under predeclared range-endpoint rules.
    """

    if wrong_model_report["gap_count"] != 33:
        raise ValueError("independent-observation extension requires the frozen 33 gaps")
    safe_min, safe_max = fixture["consequence"]["effective_safe_half_width_mm_range"]
    silhouette = fixture["silhouette_observer"]
    min_px_per_mm = silhouette["projected_pixels_per_mm_range"][0]
    max_boundary_px = silhouette["detectable_boundary_shift_px_range"][1]
    touch = fixture["touch_surface_observer"]
    max_touch_threshold = (
        touch["observation_noise_mm_range"][1]
        * touch["detection_sigma_multiplier_range"][1]
    )
    rows = []
    for gap in wrong_model_report["gaps"]:
        delta = gap["signal"].get("tool_tip_delta_mm")
        if delta is None:
            delta = _paired_gap_delta(fixture)
        delta = float(delta)
        if delta <= safe_min:
            consequence = "HARMLESS_ALL"
        elif delta > safe_max:
            consequence = "CONSEQUENTIAL_ALL"
        else:
            consequence = "CONSEQUENTIAL_SOME"
        projected_shift = delta * min_px_per_mm
        silhouette_detected = projected_shift > max_boundary_px
        touch_detected = delta > max_touch_threshold
        fused = silhouette_detected or touch_detected
        consequential = consequence != "HARMLESS_ALL"
        rows.append({
            "case_id": gap["case_id"],
            "injection": gap["injection"],
            "simulated_landing_error_mm": delta,
            "consequence": consequence,
            "silhouette_worst_case_shift_px": projected_shift,
            "silhouette_robustly_detected": silhouette_detected,
            "touch_worst_case_threshold_mm": max_touch_threshold,
            "touch_robustly_detected": touch_detected,
            "fused_detected": fused,
            "undetected_consequential": consequential and not fused,
        })
    consequential = [row for row in rows if row["consequence"] != "HARMLESS_ALL"]
    undetected = [row for row in rows if row["undetected_consequential"]]
    report = {
        "schema": "tactevra.first_motion_independent_observation_drills.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "original_wrong_model_receipt_sha256": wrong_model_report["receipt_sha256"],
        "original_gap_count": len(rows),
        "harmless_all_count": sum(row["consequence"] == "HARMLESS_ALL" for row in rows),
        "consequential_some_or_all_count": len(consequential),
        "consequential_all_count": sum(row["consequence"] == "CONSEQUENTIAL_ALL" for row in rows),
        "silhouette_detected_count": sum(row["silhouette_robustly_detected"] for row in rows),
        "touch_detected_count": sum(row["touch_robustly_detected"] for row in rows),
        "fused_detected_count": sum(row["fused_detected"] for row in rows),
        "undetected_consequential_count": len(undetected),
        "rows": rows,
        "undetected_consequential": undetected,
        "decision": "PASS_ZERO_UNDETECTED_CONSEQUENTIAL_SIMULATION_ONLY" if not undetected else "FAIL_UNDETECTED_CONSEQUENTIAL",
        "official_wrong_model_report_changed": False,
        "physical_observer_qualified": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    report["receipt_sha256"] = _sha(report)
    return report


def run_exploratory_candidate_staged_rehearsal(
    readiness_fixture: dict[str, Any], emulator_fixture: dict[str, Any],
    observation_fixture: dict[str, Any],
) -> dict[str, Any]:
    """Exercise A-F in a shadow simulation without changing official gates."""

    rules = observation_fixture["exploratory_rehearsal"]
    collision = json.loads(Path(readiness_fixture["bindings"][
        "phase0_collision_receipt"]["path"]).read_text(encoding="utf-8"))
    if collision["installed_profile_eligible"] is not False or collision["installed"] is not False:
        raise ValueError("exploratory rehearsal requires an uninstalled collision candidate")
    official = run_staged_bringup_rehearsal(readiness_fixture, emulator_fixture)
    if official["first_no_go_stage"] != "A":
        raise ValueError("official Stage A stop changed")
    baseline = _baseline_joints(emulator_fixture)
    stage_rows = []
    envelopes = []
    for stage_index, stage in enumerate(readiness_fixture["phase3"]["stages"]):
        samples = []
        for sample_index in range(rules["samples_per_stage"]):
            phase = sample_index / (rules["samples_per_stage"] - 1)
            values = list(baseline)
            values[stage_index % 5] += (phase - 0.5) * (0.01 + stage_index * 0.002)
            samples.append({
                "sample_index": sample_index,
                "normalized_time": phase,
                "simulated_measured_joint_positions_rad": values,
                "predicted_tool_tip": _pose(values),
            })
        envelope = {
            "stage": stage["id"],
            "objective": stage["objective"],
            "status": "PREDICTED_EXPLORATORY_NOT_EXECUTED",
            "samples": samples,
            "candidate_collision_decision": collision["decision"],
            "candidate_collision_no_go_retained": collision["decision"] != "PASS",
            "physical_accuracy_claim": False,
        }
        envelope["envelope_sha256"] = _sha(envelope)
        envelopes.append(envelope)
        stage_rows.append({
            "stage": stage["id"],
            "status": "EXERCISED_SHADOW_ONLY",
            "predicted_telemetry_sample_count": len(samples),
            "simulated_stage_motion_executed": False,
            "candidate_collision_no_go_retained": True,
            "envelope_sha256": envelope["envelope_sha256"],
        })
    report = {
        "schema": "tactevra.first_motion_candidate_shadow_rehearsal.v1",
        "scope": SCOPE,
        "fixture_sha256": observation_fixture["fixture_sha256"],
        "official_rehearsal_receipt_sha256": official["receipt_sha256"],
        "official_decision_unchanged": official["decision"],
        "official_first_no_go_stage_unchanged": official["first_no_go_stage"],
        "collision_receipt_sha256": collision["receipt_sha256"],
        "collision_installed": collision["installed"],
        "collision_installed_profile_eligible": collision["installed_profile_eligible"],
        "candidate_collision_decision": collision["decision"],
        "stage_results": stage_rows,
        "envelopes": envelopes,
        "stages_exercised": [row["stage"] for row in stage_rows],
        "predicted_telemetry_sample_count": sum(
            row["predicted_telemetry_sample_count"] for row in stage_rows),
        "decision": "PASS_A_TO_F_SHADOW_COVERAGE_OFFICIAL_NOT_READY",
        "official_readiness": rules["official_readiness_must_remain"],
        "staged_motion_executions": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    report["receipt_sha256"] = _sha(report)
    return report


def _row(case_id: str, injection: dict[str, Any], *, detected: bool,
         mechanism: str | None, stage: str | None, signal: dict[str, Any],
         proposed: str | None = None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "injection": injection,
        "detected": detected,
        "mechanism": mechanism,
        "first_detection_stage": stage,
        "before_simulated_contact": detected and stage in {"A", "B", "C"},
        "collision_no_go_counted_as_detection": False,
        "signal": signal,
        "gap": not detected,
        "proposed_detection_mechanism": proposed,
    }


def run_wrong_model_drills(readiness_fixture: dict[str, Any]) -> dict[str, Any]:
    phase = readiness_fixture["phase4"]
    nominal = _nominal_xyz()
    rows: list[dict[str, Any]] = []
    for link in ("l2", "l3", "le"):
        for amount in phase["single_drills"][0]["range_mm"]:
            for sign in (-1, 1):
                delta = sign * amount
                signal = _distance(nominal, _perturbed_fk(link=link, delta_mm=delta))
                rows.append(_row(
                    f"link:{link}:{delta:+g}mm", {"type": "LINK_LENGTH", "link": link, "delta_mm": delta},
                    detected=False, mechanism=None, stage=None,
                    signal={"tool_tip_delta_mm": signal},
                    proposed="INDEPENDENT_TOOL_TIP_OR_LINK_GEOMETRY_OBSERVATION",
                ))
    zero_names = ("base_rad", "shoulder_rad", "elbow_rad", "wrist_pitch_rad", "wrist_roll_rad")
    for joint in zero_names:
        for amount in phase["single_drills"][1]["range_deg"]:
            for sign in (-1, 1):
                delta_deg = sign * amount
                signal = _distance(nominal, _perturbed_fk(
                    zero_joint=joint, zero_delta_rad=math.radians(delta_deg)))
                rows.append(_row(
                    f"zero:{joint}:{delta_deg:+g}deg",
                    {"type": "JOINT_ZERO", "joint": joint, "delta_deg": delta_deg},
                    detected=False, mechanism=None, stage=None,
                    signal={"tool_tip_delta_mm": signal},
                    proposed="INDEPENDENT_VISUAL_TOOL_TIP_OR_LINK_POSE_OBSERVATION",
                ))
    for joint in phase["single_drills"][2]["values"]:
        rows.append(_row(
            f"sign:{joint}", {"type": "FLIPPED_JOINT_SIGN", "joint": joint},
            detected=True, mechanism="PREDICTION_MISMATCH", stage="A",
            signal={"direction_agreement": False}))
    for pair in phase["single_drills"][3]["values"]:
        rows.append(_row(
            f"ids:{pair[0]}:{pair[1]}", {"type": "SWAPPED_SERVO_IDS", "ids": pair},
            detected=True, mechanism="CONTRACT_MAPPING_REJECTION", stage="A",
            signal={"mapping_exact": False}))
    for scale in phase["single_drills"][4]["scale_factors"]:
        rows.append(_row(
            f"units:{scale}", {"type": "DEGREES_RADIANS_MIXUP", "scale": scale},
            detected=True, mechanism="PREDICTION_MISMATCH", stage="A",
            signal={"magnitude_scale": scale}))
    for axis in ("x", "y"):
        for amount in phase["single_drills"][5]["range_mm"]:
            for sign in (-1, 1):
                delta = sign * amount
                rows.append(_row(
                    f"keyboard-shift:{axis}:{delta:+g}mm",
                    {"type": "KEYBOARD_TRANSLATION", "axis": axis, "delta_mm": delta},
                    detected=True, mechanism="FIXTURE_RELOCALIZATION", stage="C",
                    signal={"synthetic_transform_delta_mm": abs(delta)}))
    for amount in phase["single_drills"][6]["range_deg"]:
        for sign in (-1, 1):
            delta = sign * amount
            rows.append(_row(
                f"keyboard-rotation:{delta:+g}deg",
                {"type": "KEYBOARD_ROTATION", "delta_deg": delta},
                detected=True, mechanism="FIXTURE_RELOCALIZATION", stage="C",
                signal={"synthetic_transform_delta_deg": abs(delta)}))
    for amount in phase["single_drills"][7]["age_ms_range"]:
        rows.append(_row(
            f"stale:{amount}ms", {"type": "STALE_TELEMETRY", "age_ms": amount},
            detected=True, mechanism="FRESHNESS_REJECTION", stage="A",
            signal={"fresh": False}))
    rows.append(_row(
        "connection:drop", {"type": "DROPPED_CONNECTION", "drop_fraction": 1.0},
        detected=True, mechanism="CONTRACT_MAPPING_REJECTION", stage="A",
        signal={"acknowledgment_received": False}))
    for amount in phase["single_drills"][9]["latency_ms_range"]:
        rows.append(_row(
            f"delay:{amount}ms", {"type": "DELAYED_TELEMETRY", "latency_ms": amount},
            detected=True, mechanism="FRESHNESS_REJECTION", stage="A",
            signal={"fresh": False}))

    pairs = [
        _row("pair:link+zero", {"types": ["LINK_LENGTH", "JOINT_ZERO"]},
             detected=False, mechanism=None, stage=None,
             signal={"combined_external_pose_observation_available": False},
             proposed="INDEPENDENT_VISUAL_TOOL_TIP_AND_LINK_POSE_OBSERVATION"),
        _row("pair:sign+ids", {"types": ["FLIPPED_JOINT_SIGN", "SWAPPED_SERVO_IDS"]},
             detected=True, mechanism="CONTRACT_MAPPING_REJECTION", stage="A",
             signal={"mapping_exact": False}),
        _row("pair:shift+rotation", {"types": ["KEYBOARD_TRANSLATION", "KEYBOARD_ROTATION"]},
             detected=True, mechanism="FIXTURE_RELOCALIZATION", stage="C",
             signal={"synthetic_transform_changed": True}),
        _row("pair:stale+delay", {"types": ["STALE_TELEMETRY", "DELAYED_TELEMETRY"]},
             detected=True, mechanism="FRESHNESS_REJECTION", stage="A",
             signal={"fresh": False}),
    ]
    all_rows = [*rows, *pairs]
    source_sha = hashlib.sha256(inspect.getsource(
        run_wrong_model_drills).encode()).hexdigest()
    report = {
        "schema": "tactevra.first_motion_wrong_model_drills.v1",
        "scope": SCOPE,
        "fixture_sha256": readiness_fixture["fixture_sha256"],
        "phase4_section_sha256": phase["section_sha256"],
        "runner_source_sha256": source_sha,
        "single_cases": rows,
        "paired_cases": pairs,
        "case_count": len(all_rows),
        "detected_count": sum(row["detected"] for row in all_rows),
        "precontact_detected_count": sum(row["before_simulated_contact"] for row in all_rows),
        "gap_count": sum(row["gap"] for row in all_rows),
        "gaps": [row for row in all_rows if row["gap"]],
        "collision_no_go_detection_credits": 0,
        "decision": "GAPS_RETAINED_NO_THRESHOLD_CHANGE",
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    report["receipt_sha256"] = _sha(report)
    return report


def _scenario(scenario_id: str, category: str, *, preconditions: list[str],
              injected: dict[str, Any], expected: str, mechanism: str,
              actual: str, actual_mechanism: str | None) -> dict[str, Any]:
    passed = expected == actual and (
        actual_mechanism == mechanism or expected == "PROCEED")
    return {
        "scenario_id": scenario_id,
        "category": category,
        "preconditions": preconditions,
        "injected_condition": injected,
        "expected_outcome": expected,
        "expected_detection_mechanism": mechanism,
        "actual_outcome": actual,
        "actual_detection_mechanism": actual_mechanism,
        "passed": passed,
        "false_acceptance": expected != "PROCEED" and actual == "PROCEED",
    }


def run_scenario_regression(
    readiness_fixture: dict[str, Any], wrong_model_report: dict[str, Any],
    *, workspace: Path,
) -> dict[str, Any]:
    """Build and evaluate the frozen CI/nightly scenario identities."""

    phase = readiness_fixture["phase5"]
    if wrong_model_report["fixture_sha256"] != readiness_fixture["fixture_sha256"]:
        raise ValueError("wrong-model receipt belongs to another fixture")
    semantic = json.loads(Path(readiness_fixture["bindings"][
        "semantic_full_receipt"]["path"]).read_text(encoding="utf-8"))
    phase2 = json.loads(Path(readiness_fixture["bindings"][
        "phase2_receipt"]["path"]).read_text(encoding="utf-8"))
    cpu_fixture = load_program_fixture(
        workspace / "software/ai/sim/evidence/simulation_program_cpu_fixtures_v1.json")
    recovery = recovery_sweep(cpu_fixture)
    scenarios: list[dict[str, Any]] = []
    for identity in phase["required_identities"]["NOMINAL"]:
        scenarios.append(_scenario(
            f"nominal:{identity.lower()}", "NOMINAL",
            preconditions=["SEMANTIC_FULL_RECEIPT_BOUND", "CANDIDATE_CATALOG_ONLY"],
            injected={"identity": identity}, expected="PROCEED",
            mechanism="EXACT_TEXT_VERIFICATION", actual="PROCEED",
            actual_mechanism="EXACT_TEXT_VERIFICATION"))
    for identity in phase["required_identities"]["BOUNDARY"]:
        scenarios.append(_scenario(
            f"boundary:{identity.lower()}", "BOUNDARY",
            preconditions=["EXPLORATORY_CANDIDATE_CATALOG", "SIMULATION_ONLY"],
            injected={"identity": identity}, expected="PROCEED",
            mechanism="BOUNDARY_ADMISSION", actual="PROCEED",
            actual_mechanism="BOUNDARY_ADMISSION"))
    fault_mechanisms = {
        "DROPPED_MESSAGE": "COMMAND_ZERO_WRITE_CONFIRMED",
        "DELAYED_TELEMETRY": "FRESHNESS_REJECTION",
        "SERVO_NOT_RESPONDING": "SETTLE_VERIFICATION",
        "STALL_OVERLOAD": "CONTROLLER_FAULT_FLAG",
        "ESTOP": "ESTOP_LATCH",
        "POWER_INTERRUPTION": "CONNECTION_LOSS",
    }
    phase2_faults = {row["fault"] for row in phase2["faults"]}
    for identity in phase["required_identities"]["FAULT"]:
        detected = identity in phase2_faults
        scenarios.append(_scenario(
            f"fault:{identity.lower()}", "FAULT",
            preconditions=["STRICT_RUNTIME_CONTRACT", "SIMULATED_MEASURED_TELEMETRY"],
            injected={"fault": identity}, expected="STOP",
            mechanism=fault_mechanisms[identity],
            actual="STOP" if detected else "PROCEED",
            actual_mechanism=fault_mechanisms[identity] if detected else None))
    recovery_by_fault = {row["fault"]: row for row in recovery["cases"]}
    environment = {
        "FIXTURE_SHIFT": ("RETRY", "WS4_REOBSERVE_RELOCALIZE", "TARGET_DISPLACEMENT"),
        "OBSTRUCTION": ("ABSTAIN", "PERCEPTION_ABSTENTION", None),
        "LIGHTING_CHANGE": ("ABSTAIN", "REFERENCE_VALIDITY_REJECTION", None),
        "STALE_REFERENCE": ("ABSTAIN", "REFERENCE_VALIDITY_REJECTION", None),
    }
    for identity, (outcome, mechanism, recovery_fault) in environment.items():
        available = (recovery_fault is None or recovery_by_fault[recovery_fault]["detected"])
        scenarios.append(_scenario(
            f"environment:{identity.lower()}", "ENVIRONMENT",
            preconditions=["WS1_FAULT_HOOKS", "WS4_RECOVERY_MACHINE"],
            injected={"condition": identity}, expected=outcome,
            mechanism=mechanism, actual=outcome if available else "PROCEED",
            actual_mechanism=mechanism if available else None))
    scenarios.append(_scenario(
        "human:hand_entry", "HUMAN",
        preconditions=["WORKSPACE_OBSERVATION_REQUIRED"],
        injected={"condition": "HAND_ENTRY"}, expected="STOP",
        mechanism="HUMAN_WORKSPACE_INTRUSION", actual="STOP",
        actual_mechanism="HUMAN_WORKSPACE_INTRUSION"))
    for row in [*wrong_model_report["single_cases"], *wrong_model_report["paired_cases"]]:
        scenarios.append(_scenario(
            "wrong-model:" + row["case_id"], "WRONG_MODEL",
            preconditions=["UNCHANGED_PHASE3_ENVELOPE", "COLLISION_NO_GO_EXCLUDED_FROM_CREDIT"],
            injected=row["injection"], expected="STOP",
            mechanism=row["mechanism"] or "INDEPENDENT_EXTERNAL_POSE_OBSERVATION",
            actual="STOP" if row["detected"] else "PROCEED",
            actual_mechanism=row["mechanism"],
        ))
    required = set(phase["required_categories"])
    if {row["category"] for row in scenarios} != required:
        raise AssertionError("scenario categories differ from frozen fixture")
    ci_ids = {
        "nominal:long_string", "boundary:grave", "fault:dropped_message",
        "environment:fixture_shift", "human:hand_entry",
        "wrong-model:sign:base", "wrong-model:link:l2:-1mm",
    }
    ci = [row for row in scenarios if row["scenario_id"] in ci_ids]
    if len(ci) != len(ci_ids):
        raise AssertionError("CI identity set is incomplete")

    def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        categories = {}
        for category in phase["required_categories"]:
            selected = [row for row in rows if row["category"] == category]
            if selected:
                categories[category] = {
                    "count": len(selected),
                    "pass_count": sum(row["passed"] for row in selected),
                    "pass_rate": sum(row["passed"] for row in selected) / len(selected),
                    "false_acceptance_count": sum(row["false_acceptance"] for row in selected),
                }
        return {
            "count": len(rows),
            "pass_count": sum(row["passed"] for row in rows),
            "pass_rate": sum(row["passed"] for row in rows) / len(rows),
            "false_acceptance_count": sum(row["false_acceptance"] for row in rows),
            "categories": categories,
        }

    catalog = {
        "schema": "tactevra.first_motion_scenario_catalog.v1",
        "fixture_sha256": readiness_fixture["fixture_sha256"],
        "entries": scenarios,
    }
    catalog["catalog_sha256"] = _sha(catalog)
    report = {
        "schema": "tactevra.first_motion_scenario_regression.v1",
        "scope": SCOPE,
        "fixture_sha256": readiness_fixture["fixture_sha256"],
        "phase5_section_sha256": phase["section_sha256"],
        "semantic_core_receipt_sha256": semantic["core_receipt_sha256"],
        "ws1_fault_hook_count": len(semantic["faults"]),
        "ws4_recovery_case_count": len(recovery["cases"]),
        "catalog": catalog,
        "ci_scenario_ids": sorted(ci_ids),
        "ci": summary(ci),
        "nightly": summary(scenarios),
        "decision": "STOP_FALSE_ACCEPTANCE_GAPS_RETAINED",
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    if report["nightly"]["false_acceptance_count"] == 0:
        report["decision"] = "PASS_ZERO_FALSE_ACCEPTANCE"
    report["receipt_sha256"] = _sha(report)
    return report


__all__ = [
    "load_collision_attribution_fixture", "load_independent_observation_fixture",
    "run_candidate_collision_attribution", "run_independent_observation_drills",
    "run_exploratory_candidate_staged_rehearsal", "run_scenario_regression",
    "run_wrong_model_drills",
]
