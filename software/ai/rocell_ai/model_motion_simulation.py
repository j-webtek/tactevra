"""Nominal static simulation of one assured keyboard contact proposal."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from rocell.application.simulate import run_scenario_ik
from rocell.application.static_simulation_context import (
    load_static_simulation_context,
    revalidate_static_simulation_context,
    static_simulation_context_hashes,
)
from rocell.application.trajectory_simulation import screen_scenario_route, validate_scene_park_xy
from rocell.application.robot_layout_overlay import promoted_rank1_robot_layout
from rocell.models import ActionPlan, Device, PressKey, Point3Mm
from rocell.motion import GeometricDryRunEngine, GeometricSimulationSettings
from rocell.simulation.profile import (
    SimulatedArmIdentity,
    SimulatedCameraIdentity,
    SimulationHardwareProfile,
)
from rocell.targets import TargetRegion
from rocell.typing.static_development_profiles import static_development_keyboard_profile

from .motion_assurance import build as build_assurance
from .scene_observation import SHA256_PATTERN, canonical_hash


SCHEMA = "rocell.ai_model_motion_simulation.v0"
REPORT_FIELDS = {
    "schema", "proposal_sha256", "candidate_sha256", "assurance_bundle_sha256",
    "static_context_bundle_sha256", "static_target_catalog_sha256",
    "simulation_target_overlay", "plan_hash", "geometry_report_sha256",
    "geometry_all_checks_pass", "sampled_ik_all_converged", "dense_route_status",
    "dense_route_all_waypoints_accepted", "evaluated_waypoint_count", "first_failure",
    "simulation_status", "physical_calibration_verified", "continuous_path_proven",
    "full_arm_collision_checked", "physical_execution_authorized", "hardware_commands",
    "hardware_writes", "physical_input_events_observed", "limitations", "simulation_sha256",
}


def _simulation_profile(context: Any) -> SimulationHardwareProfile:
    sources = static_simulation_context_hashes(context)
    return SimulationHardwareProfile(
        profile_id="ROCELL-MODEL-MOTION-NUMERICAL-001",
        design_revision=context.snapshot.design_revision,
        source_profile_sha256=context.bundle.source_sha256,
        source_freeze_id=context.snapshot.manifest_id,
        source_manifest_sha256=context.snapshot.manifest_sha256,
        source_camera_binding_id="static-overhead-b0477-phase1.v1",
        source_camera_manifest_sha256=sources["camera_architecture_plan"],
        source_manifest_status="STATIC_SOFTWARE_OVERLAY_NOT_PHYSICAL_FREEZE",
        source_physical_release_status="UNRELEASED",
        arm=SimulatedArmIdentity("Waveshare", "RoArm-M3-Pro"),
        camera=SimulatedCameraIdentity("Arducam", "B0477", "B0477", "USB", "Sony IMX283"),
        assumptions=(
            "Nominal geometry and unmeasured tool offset only",
            "Model target coordinate is a simulation overlay, not installed calibration",
        ),
    )


def validate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"layout_study_assumptions"} != REPORT_FIELDS:
        raise ValueError("model motion simulation report has invalid fields")
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported model motion simulation schema")
    for key in (
        "proposal_sha256", "candidate_sha256", "assurance_bundle_sha256",
        "static_context_bundle_sha256", "static_target_catalog_sha256", "plan_hash",
        "geometry_report_sha256", "simulation_sha256",
    ):
        if not isinstance(value[key], str) or SHA256_PATTERN.fullmatch(value[key]) is None:
            raise ValueError(f"invalid model motion simulation {key}")
    assumptions = value.get("layout_study_assumptions")
    if "layout_study_assumptions" in value:
        if not isinstance(assumptions, dict):
            raise ValueError("layout assumptions must be an object")
        for key in ("installed_position_verified", "installed_tool_verified", "physical_execution_authorized"):
            if assumptions.get(key) is not False:
                raise ValueError("layout study cannot assert physical verification or authority")
        layout = assumptions.get("robot_layout_overlay")
        if layout is not None:
            if not isinstance(layout, dict) or layout.get("motion_authorized") is not False:
                raise ValueError("layout overlay cannot authorize motion")
            layout_core = {key: item for key, item in layout.items() if key != "overlay_sha256"}
            if layout.get("overlay_sha256") != canonical_hash(layout_core):
                raise ValueError("layout overlay hash mismatch")
    overlay = value["simulation_target_overlay"]
    if not isinstance(overlay, dict) or overlay.get("simulation_only") is not True:
        raise ValueError("model motion simulation requires a simulation-only overlay")
    overlay_core = {key: item for key, item in overlay.items() if key != "overlay_sha256"}
    if overlay.get("overlay_sha256") != canonical_hash(overlay_core):
        raise ValueError("model motion simulation overlay hash mismatch")
    if overlay.get("model_candidate_sha256") != value["candidate_sha256"]:
        raise ValueError("model motion simulation candidate binding mismatch")
    if overlay.get("base_static_target_catalog_sha256") != value["static_target_catalog_sha256"]:
        raise ValueError("model motion simulation catalog binding mismatch")
    for key in (
        "physical_calibration_verified", "continuous_path_proven", "full_arm_collision_checked",
        "physical_execution_authorized",
    ):
        if value[key] is not False:
            raise ValueError(f"model motion simulation cannot assert {key}")
    for key in ("geometry_all_checks_pass", "sampled_ik_all_converged", "dense_route_all_waypoints_accepted"):
        if type(value[key]) is not bool:
            raise ValueError(f"{key} must be Boolean")
    if value["hardware_commands"] != [] or type(value["hardware_writes"]) is not int or value["hardware_writes"] != 0:
        raise ValueError("model motion simulation must remain zero-write")
    if type(value["physical_input_events_observed"]) is not int or value["physical_input_events_observed"] != 0:
        raise ValueError("model motion simulation cannot claim physical input events")
    if value["dense_route_all_waypoints_accepted"] is True:
        expected_status = "SAMPLES_PASS_NOT_EXECUTABLE"
        if value["first_failure"] is not None:
            raise ValueError("passing route cannot have a first failure")
    else:
        expected_status = "SIMULATION_BLOCKED"
        if not isinstance(value["first_failure"], dict):
            raise ValueError("blocked simulation requires first failure evidence")
    if value["simulation_status"] != expected_status:
        raise ValueError("model motion simulation status mismatch")
    core = {key: item for key, item in value.items() if key != "simulation_sha256"}
    if value["simulation_sha256"] != canonical_hash(core):
        raise ValueError("model motion simulation report hash mismatch")
    return value


def _run_with_route_evidence(
    value: object,
    *,
    workspace: Path,
    minimum_confidence: float = 0.9,
    park_xy_board_mm: tuple[float, float] | None = None,
    robot_layout_profile: Path | None = None,
    initial_arm_joint_positions_rad: dict[str, float] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    assurance = build_assurance(value, workspace=workspace, minimum_confidence=minimum_confidence)
    candidate = assurance["candidate"]
    if candidate["device"] != "keyboard" or candidate["interaction"] != "CONTACT":
        raise ValueError("model motion simulation v0 supports keyboard CONTACT only")

    context = load_static_simulation_context(workspace)
    target_id = candidate["target_id"]
    original = context.targets.resolve("keyboard", target_id)
    point = candidate["proposed_surface_target_board_mm"]
    simulated = TargetRegion(
        "keyboard", target_id,
        Point3Mm("board", point["x"], point["y"], point["z"]),
        original.half_extent_x_mm, original.half_extent_y_mm,
    )
    keyboard_targets = dict(context.targets.keyboard_targets)
    keyboard_targets[target_id] = simulated
    overlay_core = {
        "schema": "rocell.model_motion_target_overlay.v0",
        "base_static_target_catalog_sha256": context.targets.content_sha256,
        "model_candidate_sha256": candidate["candidate_sha256"],
        "device": "keyboard",
        "target_id": target_id,
        "center_board_mm": [simulated.center.x, simulated.center.y, simulated.center.z],
        "simulation_only": True,
    }
    overlay_sha256 = canonical_hash(overlay_core)
    targets = replace(
        context.targets,
        keyboard_targets=keyboard_targets,
        content_sha256=overlay_sha256,
    )
    profile = static_development_keyboard_profile()
    plan = ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id=profile.profile_id,
        text=f"model-proposal:{candidate['proposal_id']}",
        actions=(PressKey(target_id),),
        required_calibrations=profile.required_calibrations,
    )
    path = context.scenario.path_policy
    settings = GeometricSimulationSettings(
        clearance_above_highest_obstacle_mm=path.clearance_above_highest_obstacle_mm,
        segment_clearance_mm=path.segment_clearance_mm,
        hover_height_mm=path.hover_height_mm,
        approach_height_mm=path.approach_height_mm,
        contact_overtravel_mm=path.contact_overtravel_mm,
        park_xy_board_mm=path.park_xy_board_mm if park_xy_board_mm is None else park_xy_board_mm,
    )
    validate_scene_park_xy(context.scene, settings.park_xy_board_mm)
    scenario = context.scenario
    layout = None
    if robot_layout_profile is not None:
        scenario, layout = promoted_rank1_robot_layout(context, robot_layout_profile)
    hardware_profile = _simulation_profile(context)
    geometry = GeometricDryRunEngine(settings).run(
        plan, context.snapshot, hardware_profile, context.scene, targets,
    )
    ik = run_scenario_ik(scenario, geometry)
    route = screen_scenario_route(
        scenario,
        plan,
        geometry,
        initial_arm_joint_positions_rad=initial_arm_joint_positions_rad,
    )
    route_passed = route["all_waypoints_accepted"] is True
    route_round = route.get("round") or {}
    failed = next((row for row in route_round.get("joint_results", []) if not row["accepted"]), None)
    revalidate_static_simulation_context(context)
    core = {
        "schema": SCHEMA,
        "proposal_sha256": candidate["proposal_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "assurance_bundle_sha256": assurance["bundle_sha256"],
        "static_context_bundle_sha256": context.bundle.source_sha256,
        "static_target_catalog_sha256": context.targets.content_sha256,
        "simulation_target_overlay": {**overlay_core, "overlay_sha256": overlay_sha256},
        "plan_hash": plan.plan_hash,
        "geometry_report_sha256": geometry.report_hash,
        "geometry_all_checks_pass": geometry.all_checks_pass,
        "sampled_ik_all_converged": ik.all_sampled_converged,
        "dense_route_status": route["status"],
        "dense_route_all_waypoints_accepted": route_passed,
        "evaluated_waypoint_count": route_round.get("evaluated_waypoint_count"),
        "first_failure": (None if route_passed else {"reason": route["status"], "phase": "GEOMETRY", "target": None, "waypoint_sequence": None}) if failed is None else {
            "waypoint_sequence": failed["waypoint_sequence"],
            "target": failed["semantic_target"],
            "phase": failed["phase"],
            "reason": failed["failure_reason"],
        },
        "simulation_status": "SAMPLES_PASS_NOT_EXECUTABLE" if route_passed else "SIMULATION_BLOCKED",
        "physical_calibration_verified": False,
        "continuous_path_proven": False,
        "full_arm_collision_checked": False,
        "physical_execution_authorized": False,
        "hardware_commands": [],
        "hardware_writes": 0,
        "physical_input_events_observed": 0,
        "limitations": [
            "Model coordinate evaluated against nominal simulation geometry only",
            "Route uses the static scenario clearance and cadence; proposal speed and requested waypoints are not simulated",
            "Target placement, board-to-arm correlation, and tool transform are unmeasured",
            "IK is sampled and full arm, tool, cable, and environment collision are incomplete",
            "No controller encoding, transport access, contact, or input-event observation occurred",
        ],
    }
    if park_xy_board_mm is not None or layout is not None:
        core["layout_study_assumptions"] = {
            "park_xy_board_mm": list(settings.park_xy_board_mm),
            "robot_layout_overlay": layout,
            "installed_position_verified": False,
            "installed_tool_verified": False,
            "physical_execution_authorized": False,
        }
    return validate({**core, "simulation_sha256": canonical_hash(core)}), route


def run(value: object, *, workspace: Path, minimum_confidence: float = 0.9,
        park_xy_board_mm: tuple[float, float] | None = None,
        robot_layout_profile: Path | None = None,
        initial_arm_joint_positions_rad: dict[str, float] | None = None) -> dict[str, Any]:
    """Return the stable compact simulation report."""

    report, _ = _run_with_route_evidence(
        value,
        workspace=workspace,
        minimum_confidence=minimum_confidence,
        park_xy_board_mm=park_xy_board_mm,
        robot_layout_profile=robot_layout_profile,
        initial_arm_joint_positions_rad=initial_arm_joint_positions_rad,
    )
    return report


def run_with_route_evidence(
    value: object,
    *,
    workspace: Path,
    minimum_confidence: float = 0.9,
    park_xy_board_mm: tuple[float, float] | None = None,
    robot_layout_profile: Path | None = None,
    initial_arm_joint_positions_rad: dict[str, float] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the compact report and the zero-authority dense-route evidence.

    This additive analysis API exposes the already-computed route details.  It
    does not alter the stable report schema or add execution authority.
    """

    return _run_with_route_evidence(
        value,
        workspace=workspace,
        minimum_confidence=minimum_confidence,
        park_xy_board_mm=park_xy_board_mm,
        robot_layout_profile=robot_layout_profile,
        initial_arm_joint_positions_rad=initial_arm_joint_positions_rad,
    )
