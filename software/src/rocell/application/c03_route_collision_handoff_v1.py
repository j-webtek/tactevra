"""Strict zero-authority handoff from an admitted C03 route to collision intake."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from typing import Any, Mapping

from rocell.models.frames import Point3Mm

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext
from .installed_collision_measurement_manifest_v1 import (
    build_installed_collision_nominal_envelope_audit_v1,
    build_installed_collision_nominal_source_inventory_v1,
    build_installed_collision_nominal_proxy_audit_v1,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .partitioned_typing_collision_intake_v1 import (
    prepare_partitioned_typing_collision_intake_v1,
)


SCHEMA = "tactevra.c03_collision_handoff.v1"
STATION_HEIGHT_SENSITIVITY_SCHEMA = (
    "tactevra.c03_station_height_route_sensitivity.v1"
)
EXPECTED_RESULT_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1_9"
EXPECTED_ROUTE_SCHEMA = "tactevra.c03_exact_route_reconstruction_result.v1"
EXPECTED_SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
EXPECTED_RESULT_RECEIPT_SHA256 = (
    "e8dcaa9b34e46ee5fb8ec4290c18f316c393894dc87c9ba8612a457f3ef2fd60"
)
EXPECTED_ROUTE_RECEIPT_SHA256 = (
    "f64b2c30099be8494bba052cfcb707562ece61a21694e81c9187d19ceae973e4"
)
EXPECTED_DECISION = "PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY"
EXPECTED_TARGETS = ("H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6")


class C03RouteCollisionHandoffV1Error(ValueError):
    """C03 route evidence is incomplete, mutated, or authority bearing."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _verified_receipt(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = dict(value)
    claimed = document.pop(field, None)
    if not isinstance(claimed, str) or claimed != _sha256(document):
        raise C03RouteCollisionHandoffV1Error(f"invalid {field}")
    return dict(value)


def _require_zero_authority(value: Mapping[str, Any], label: str) -> None:
    zero_counts = (
        value.get("hardware_commands_generated"),
        value.get("hardware_writes"),
        value.get("physical_movements"),
    )
    if (
        value.get("controller_commands") != []
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
        or any(type(count) is not int or count != 0 for count in zero_counts)
    ):
        raise C03RouteCollisionHandoffV1Error(
            f"{label} carries or omits zero-authority evidence"
        )


def prepare_c03_route_collision_handoff_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    installed_profile: InstalledCollisionGeometryProfile | None = None,
    sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    maximum_partitions: int = 64,
) -> dict[str, Any]:
    """Verify the exact route result and enumerate its collision partitions."""

    outer = _verified_receipt(result, "receipt_sha256")
    route_value = outer.get("route_result")
    if not isinstance(route_value, Mapping):
        raise C03RouteCollisionHandoffV1Error("route_result must be an object")
    route = _verified_receipt(route_value, "receipt_sha256")
    if (
        outer["receipt_sha256"] != EXPECTED_RESULT_RECEIPT_SHA256
        or route["receipt_sha256"] != EXPECTED_ROUTE_RECEIPT_SHA256
    ):
        raise C03RouteCollisionHandoffV1Error(
            "C03 source receipt identity differs from the qualified route"
        )
    if (
        outer.get("schema") != EXPECTED_RESULT_SCHEMA
        or route.get("schema") != EXPECTED_ROUTE_SCHEMA
        or outer.get("scope") != EXPECTED_SCOPE
        or route.get("scope") != EXPECTED_SCOPE
        or outer.get("decision") != EXPECTED_DECISION
        or route.get("decision") != EXPECTED_DECISION
        or tuple(route.get("ordered_targets", ())) != EXPECTED_TARGETS
        or route.get("canonical_ik_route_accepted") is not True
        or route.get("canonical_joint_continuity_accepted") is not True
        or route.get("trajectory_sample_count") != route.get("ik_accepted_sample_count")
        or route.get("collision_screen_executed") is not False
        or outer.get("collision_screen_executed") is not False
        or outer.get("installed_collision_gate_cleared") is not False
    ):
        raise C03RouteCollisionHandoffV1Error("C03 route admission contract differs")
    _require_zero_authority(outer, "C03 reconstruction result")
    _require_zero_authority(route, "C03 route result")

    intake = prepare_partitioned_typing_collision_intake_v1(
        route["ik_screen"],
        context,
        expected_execution_plan_sha256=route["execution_plan_sha256"],
        expected_trajectory_plan_sha256=route["trajectory_plan_sha256"],
        expected_calibration_snapshot_sha256=route["calibration_snapshot_sha256"],
        installed_profile=installed_profile,
        sampling_policy=sampling_policy,
        maximum_partitions=maximum_partitions,
    )
    core = {
        "schema": SCHEMA,
        "source_result_receipt_sha256": outer["receipt_sha256"],
        "source_route_receipt_sha256": route["receipt_sha256"],
        "ordered_targets": list(EXPECTED_TARGETS),
        "trajectory_sample_count": route["trajectory_sample_count"],
        "collision_intake": intake,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "c03_collision_handoff_sha256": _sha256(core)}


def assess_c03_station_height_route_sensitivity_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    segment_clearance_mm: float = 5.0,
) -> dict[str, Any]:
    """Compare exact-route tool-tip segments under proxy and bare-CAD heights."""

    handoff = prepare_c03_route_collision_handoff_v1(result, context)
    if (
        isinstance(segment_clearance_mm, bool)
        or not isinstance(segment_clearance_mm, (int, float))
        or not math.isfinite(float(segment_clearance_mm))
        or not 0.0 <= float(segment_clearance_mm) <= 25.0
    ):
        raise C03RouteCollisionHandoffV1Error(
            "segment clearance must be finite and in [0, 25] mm"
        )
    clearance = float(segment_clearance_mm)
    route = result["route_result"]
    joint_results = route["ik_screen"].get("joint_results")
    if not isinstance(joint_results, list) or len(joint_results) < 2:
        raise C03RouteCollisionHandoffV1Error(
            "C03 route must contain at least two admitted joint results"
        )
    points = []
    for index, row in enumerate(joint_results):
        if not isinstance(row, Mapping) or row.get("waypoint_sequence") != index:
            raise C03RouteCollisionHandoffV1Error(
                "C03 route waypoint sequence differs"
            )
        value = row.get("achieved_tip_position_board_mm")
        if (
            not isinstance(value, list)
            or len(value) != 3
            or any(
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
                for item in value
            )
        ):
            raise C03RouteCollisionHandoffV1Error(
                "C03 route achieved tip position differs"
            )
        points.append(Point3Mm("board", *(float(item) for item in value)))

    proxy_audit = build_installed_collision_nominal_proxy_audit_v1(context)
    envelope_audit = build_installed_collision_nominal_envelope_audit_v1(context)
    nominal_maximum = {
        row["obstacle_id"]: row["nominal_maximum_mm"]
        for row in proxy_audit["comparisons"]
    }
    station_ids = set(proxy_audit["conservative_height_proxy_ids"])
    cad_obstacles = []
    for obstacle in context.scene.obstacles:
        if obstacle.obstacle_id not in station_ids:
            cad_obstacles.append(obstacle)
            continue
        maximum = nominal_maximum[obstacle.obstacle_id]
        cad_obstacles.append(replace(
            obstacle,
            maximum=Point3Mm("board", *maximum),
            kind="station_bare_cad_height_sensitivity",
            source="ARM-507 nominal STL bound; diagnostic only",
            conservative_proxy=False,
        ))
    cad_scene = replace(context.scene, obstacles=tuple(cad_obstacles))
    local_phases = {"HOVER", "APPROACH", "CONTACT", "RETRACT"}
    comparisons = []
    for index in range(1, len(points)):
        previous = joint_results[index - 1]
        current = joint_results[index]
        same_action = (
            previous.get("action_index") is not None
            and previous.get("action_index") == current.get("action_index")
        )
        local_keyboard_corridor = same_action and (
            previous.get("phase") in local_phases
            or current.get("phase") in local_phases
        )
        ignored = (
            ("keyboard", "station:keyboard_left", "station:keyboard_right")
            if local_keyboard_corridor
            else ()
        )
        active_result = context.scene.check_segment_clearance(
            points[index - 1], points[index], clearance_mm=clearance,
            ignored_obstacle_ids=ignored,
        )
        cad_result = cad_scene.check_segment_clearance(
            points[index - 1], points[index], clearance_mm=clearance,
            ignored_obstacle_ids=ignored,
        )
        active_ids = list(active_result.colliding_obstacle_ids)
        cad_ids = list(cad_result.colliding_obstacle_ids)
        comparisons.append({
            "segment_index": index - 1,
            "start_waypoint_sequence": index - 1,
            "end_waypoint_sequence": index,
            "action_index": current.get("action_index"),
            "semantic_target": current.get("semantic_target"),
            "start_phase": previous.get("phase"),
            "end_phase": current.get("phase"),
            "ignored_obstacle_ids": list(ignored),
            "active_35mm_collision_ids": active_ids,
            "bare_cad_collision_ids": cad_ids,
            "decision_differs": active_ids != cad_ids,
        })
    differing = [row for row in comparisons if row["decision_differs"]]
    core = {
        "schema": STATION_HEIGHT_SENSITIVITY_SCHEMA,
        "source_result_receipt_sha256": result["receipt_sha256"],
        "source_route_receipt_sha256": route["receipt_sha256"],
        "source_handoff_sha256": handoff["c03_collision_handoff_sha256"],
        "source_proxy_audit_sha256": proxy_audit["content_sha256"],
        "source_envelope_audit_sha256": envelope_audit["content_sha256"],
        "segment_clearance_mm": clearance,
        "waypoint_count": len(points),
        "segment_count": len(comparisons),
        "active_35mm_collision_segment_count": sum(
            bool(row["active_35mm_collision_ids"]) for row in comparisons
        ),
        "bare_cad_collision_segment_count": sum(
            bool(row["bare_cad_collision_ids"]) for row in comparisons
        ),
        "decision_difference_count": len(differing),
        "decision_differences": differing,
        "all_nominal_solids_contained": proxy_audit[
            "all_nominal_solids_contained"
        ],
        "proxy_change_authorized": False,
        "scope": "TOOL_TIP_CENTRELINE_DIAGNOSTIC_ONLY",
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "station_height_sensitivity_sha256": _sha256(core)}


FULL_BODY_GEOMETRY_SCHEMA = "tactevra.c03_full_body_geometry_audit.v1"
NOMINAL_TOOL_BINDING_SCHEMA = "tactevra.c03_nominal_tool_binding_readiness.v1"
BASE_CAMERA_GEOMETRY_SCHEMA = "tactevra.c03_base_camera_geometry_readiness.v1"
EXPECTED_STATIC_SUPPORT_SHA256 = (
    "2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b"
)
MESH_BINDING_SCHEMA = "tactevra.isaac_sim_upstream_link_mesh_binding.v1"
MESH_REDUCTION_SCHEMA = "tactevra.isaac_sim_link_mesh_reduction.v1"
EXPECTED_MESH_BINDING_RECEIPT_SHA256 = (
    "dbb8b56a602ac4c2b69073af23d61700aee12c0153080bdf58b7f5990b92646e"
)
EXPECTED_MESH_REDUCTION_RECEIPT_SHA256 = (
    "ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178"
)
ROBOT_LINK_BODY_IDS = {
    "base_link": "robot:base_link",
    "link1": "robot:link1",
    "link2": "robot:link2",
    "link3": "robot:link3",
    "link4": "robot:link4",
    "link5": "robot:link5",
    "gripper_link": "robot:gripper",
}


class C03FullBodyGeometryAuditV1Error(ValueError):
    """A retained geometry input is malformed, mutated, or authority bearing."""


def _verified_geometry_receipt(
    value: Mapping[str, Any], *, schema: str, expected_receipt: str, label: str
) -> dict[str, Any]:
    document = dict(value)
    claimed = document.pop("receipt_sha256", None)
    if (
        value.get("schema") != schema
        or claimed != expected_receipt
        or claimed != _sha256(document)
    ):
        raise C03FullBodyGeometryAuditV1Error(f"{label} identity differs")
    if (
        value.get("hardware_access") is not False
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
        or value.get("physical_authority") is not False
    ):
        raise C03FullBodyGeometryAuditV1Error(f"{label} carries authority")
    return dict(value)


def assess_c03_full_body_geometry_readiness_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    mesh_binding: Mapping[str, Any],
    mesh_reduction: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind candidate geometry identities and enumerate blockers before screening."""

    handoff = prepare_c03_route_collision_handoff_v1(result, context)
    binding = _verified_geometry_receipt(
        mesh_binding,
        schema=MESH_BINDING_SCHEMA,
        expected_receipt=EXPECTED_MESH_BINDING_RECEIPT_SHA256,
        label="mesh binding",
    )
    reduction = _verified_geometry_receipt(
        mesh_reduction,
        schema=MESH_REDUCTION_SCHEMA,
        expected_receipt=EXPECTED_MESH_REDUCTION_RECEIPT_SHA256,
        label="mesh reduction",
    )
    source = reduction.get("source_bindings")
    if (
        not isinstance(source, Mapping)
        or source.get("mesh_receipt_sha256") != binding["receipt_sha256"]
        or reduction.get("candidate_profile_installable") is not False
        or reduction.get("clearance_replay_admissible") is not False
        or reduction.get("reduced_collision_geometry_admissible") is not False
    ):
        raise C03FullBodyGeometryAuditV1Error(
            "mesh reduction does not retain its fail-closed source binding"
        )

    rows = reduction.get("links")
    if not isinstance(rows, list):
        raise C03FullBodyGeometryAuditV1Error("mesh reduction links must be an array")
    candidate_links: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise C03FullBodyGeometryAuditV1Error("mesh reduction link is malformed")
        link_name = row.get("link_name")
        components = row.get("components")
        if (
            link_name not in ROBOT_LINK_BODY_IDS
            or link_name in candidate_links
            or not isinstance(components, list)
            or not components
        ):
            raise C03FullBodyGeometryAuditV1Error(
                "mesh reduction link inventory differs"
            )
        candidate_links[str(link_name)] = {
            "body_id": ROBOT_LINK_BODY_IDS[str(link_name)],
            "link_name": link_name,
            "candidate_primitive_count": len(components),
            "candidate_only": True,
        }
    if set(candidate_links) != set(ROBOT_LINK_BODY_IDS):
        raise C03FullBodyGeometryAuditV1Error("mesh reduction omits a robot link")

    readiness = assess_current_collision_readiness(context)
    required = {item.body_id for item in readiness.contract.requirements}
    candidate_body_ids = {row["body_id"] for row in candidate_links.values()}
    proxy_audit = build_installed_collision_nominal_proxy_audit_v1(context)
    static_proxy_ids = {
        "workcell:board_solid",
        "workcell:keyboard",
        "workcell:phone",
        "workcell:station:keyboard_left",
        "workcell:station:keyboard_right",
        "workcell:station:phone_tcp",
    }
    if not proxy_audit["all_nominal_solids_contained"]:
        raise C03FullBodyGeometryAuditV1Error(
            "nominal environment proxies do not contain their source solids"
        )
    source_inventory = build_installed_collision_nominal_source_inventory_v1(context)
    source_rows = {
        row["body_id"]: row for row in source_inventory["bodies"]
    }
    source_only_ids = sorted(required - candidate_body_ids - static_proxy_ids)
    if set(source_rows) != required:
        raise C03FullBodyGeometryAuditV1Error(
            "nominal source inventory differs from the active body contract"
        )
    configuration_sampled_missing_ids = sorted(
        item.body_id
        for item in readiness.contract.requirements
        if item.binding_mode.value == "CONFIGURATION_SAMPLED"
    )
    blockers = [
        "CANDIDATE_ROBOT_BOXES_NOT_QUALIFIED",
        "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
        "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
        "CONTACT_TOOL_TRANSFORM_AND_ENVELOPE_NOT_INSTALLED",
        "BASE_AND_FACTORY_CLAMP_GEOMETRY_NOT_INSTALLED",
        "CAMERA_ATTACHMENT_GEOMETRY_NOT_INSTALLED",
        "MOVING_CAMERA_CABLE_CONFIGURATION_SAMPLES_MISSING",
        "INSTALLED_CLEARANCE_POLICY_PENDING",
    ]
    core = {
        "schema": FULL_BODY_GEOMETRY_SCHEMA,
        "source_result_receipt_sha256": result["receipt_sha256"],
        "source_handoff_sha256": handoff["c03_collision_handoff_sha256"],
        "mesh_binding_receipt_sha256": binding["receipt_sha256"],
        "mesh_reduction_receipt_sha256": reduction["receipt_sha256"],
        "nominal_source_inventory_sha256": source_inventory["content_sha256"],
        "nominal_proxy_audit_sha256": proxy_audit["content_sha256"],
        "route_waypoint_count": handoff["trajectory_sample_count"],
        "required_body_count": len(required),
        "candidate_robot_body_count": len(candidate_body_ids),
        "candidate_robot_primitive_count": sum(
            row["candidate_primitive_count"] for row in candidate_links.values()
        ),
        "candidate_robot_bodies": [candidate_links[key] for key in sorted(candidate_links)],
        "nominal_static_proxy_body_ids": sorted(static_proxy_ids),
        "source_only_body_ids": source_only_ids,
        "configuration_sampled_missing_body_ids": configuration_sampled_missing_ids,
        "blockers": blockers,
        "full_body_geometry_complete": False,
        "candidate_profile_installable": False,
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "full_body_geometry_audit_sha256": _sha256(core)}


def assess_c03_nominal_tool_binding_readiness_v1(
    result: Mapping[str, Any], context: SimulationContext
) -> dict[str, Any]:
    """Bind the planning tip and tool CAD identities without inventing assembly."""

    handoff = prepare_c03_route_collision_handoff_v1(result, context)
    route = result["route_result"]
    tool_length = route.get("tool_total_length_mm")
    tool_identity = route.get("tool_configuration_sha256")
    if tool_length != 110.0 or not isinstance(tool_identity, str):
        raise C03FullBodyGeometryAuditV1Error(
            "C03 route tool identity differs from the exact candidate"
        )
    envelope = build_installed_collision_nominal_envelope_audit_v1(context)
    bounds = envelope["mesh_bounds"]
    body = bounds["compliant_tool_body"]
    cap = bounds["compliant_tool_top_cap"]
    missing = [
        "HAND_TCP_TO_TOOL_BODY_RIGID_TRANSFORM",
        "TOOL_BODY_TO_TOP_CAP_ASSEMBLY_TRANSFORM",
        "INSTALLED_ROD_OR_STYLUS_GEOMETRY",
        "FREE_AND_COMPRESSED_COMPLIANCE_ENVELOPES",
        "GRIP_DEPTH_AND_RETENTION_HARDWARE_ENVELOPE",
        "MOUNTED_JAW_REFERENCE_TO_TIP_MEASUREMENT",
    ]
    core = {
        "schema": NOMINAL_TOOL_BINDING_SCHEMA,
        "source_result_receipt_sha256": result["receipt_sha256"],
        "source_handoff_sha256": handoff["c03_collision_handoff_sha256"],
        "source_envelope_audit_sha256": envelope["content_sha256"],
        "planning_tip_transform": {
            "parent_frame": "hand_tcp",
            "child_frame": "tool_tip",
            "translation_mm": [0.0, 0.0, -tool_length],
            "rotation_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "tool_configuration_sha256": tool_identity,
            "planning_only": True,
        },
        "nominal_mesh_envelopes": {
            "compliant_tool_body": body,
            "compliant_tool_top_cap": cap,
        },
        "missing_binding_inputs": missing,
        "single_collision_envelope_defined": False,
        "installed_tool_geometry_ready": False,
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "nominal_tool_binding_sha256": _sha256(core)}


def assess_c03_base_camera_geometry_readiness_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    support_design: Mapping[str, Any],
    support_design_file_sha256: str,
) -> dict[str, Any]:
    """Compare active collision bodies with the static-camera support design."""

    handoff = prepare_c03_route_collision_handoff_v1(result, context)
    if (
        support_design_file_sha256 != EXPECTED_STATIC_SUPPORT_SHA256
        or support_design.get("schema") != "rocell.static_overhead_camera_support.v1"
        or support_design.get("state")
        != "SCREENING_CANDIDATE_PHYSICAL_QUALIFICATION_OPEN"
    ):
        raise C03FullBodyGeometryAuditV1Error(
            "static camera support identity differs"
        )
    authority = support_design.get("authority")
    if not isinstance(authority, Mapping) or any(
        authority.get(field) is not False
        for field in (
            "fabrication_authority",
            "physical_installation_authority",
            "powered_motion_authority",
            "contact_authority",
        )
    ):
        raise C03FullBodyGeometryAuditV1Error(
            "static camera support carries physical authority"
        )
    robot = support_design.get("robot_screening")
    support = support_design.get("support")
    if (
        not isinstance(robot, Mapping)
        or robot.get("state") != "ASSUMED_ONLY_NOT_COLLISION_OR_REACH_PROOF"
        or robot.get("assumed_base_axis_xy_mm") != [305.0, 457.0]
        or not isinstance(support, Mapping)
        or support.get("topology") != "front_portal_on_common_metal_u_frame"
    ):
        raise C03FullBodyGeometryAuditV1Error(
            "static support screening geometry differs"
        )
    readiness = assess_current_collision_readiness(context)
    camera_requirements = [
        {
            "body_id": item.body_id,
            "parent_frame": item.parent_frame,
            "binding_mode": item.binding_mode.value,
        }
        for item in readiness.contract.requirements
        if item.body_id.startswith("attachment:camera_")
        or item.body_id == "attachment:moving_camera_cable"
    ]
    expected_camera_ids = {
        "attachment:camera_holder",
        "attachment:camera_module",
        "attachment:camera_connector",
        "attachment:moving_camera_cable",
    }
    if {row["body_id"] for row in camera_requirements} != expected_camera_ids:
        raise C03FullBodyGeometryAuditV1Error(
            "active camera collision requirements differ"
        )
    inventory = build_installed_collision_nominal_source_inventory_v1(context)
    source_rows = {row["body_id"]: row for row in inventory["bodies"]}
    if any(source_rows[body_id]["measured"] for body_id in expected_camera_ids):
        raise C03FullBodyGeometryAuditV1Error(
            "camera source inventory unexpectedly claims measurement"
        )
    base_missing = [
        "INSTALLED_BASE_Z_ROLL_PITCH_YAW",
        "FACTORY_CLAMP_FOOTPRINT_AND_HEIGHT",
        "REINFORCEMENT_PLATE_AND_FASTENER_ENVELOPE",
        "BOARD_AND_CLAMP_DEFLECTION_ENVELOPE",
    ]
    camera_missing = [
        "COLLISION_CONTRACT_STATIC_CAMERA_ARCHITECTURE_REVISION",
        "INSTALLED_PORTAL_AND_HOLDER_TRANSFORMS",
        "RECEIVED_CAMERA_CASE_LENS_CONNECTOR_ENVELOPE",
        "STATIC_USB_CABLE_ROUTE_AND_STRAIN_RELIEF_ENVELOPE",
    ]
    core = {
        "schema": BASE_CAMERA_GEOMETRY_SCHEMA,
        "source_result_receipt_sha256": result["receipt_sha256"],
        "source_handoff_sha256": handoff["c03_collision_handoff_sha256"],
        "source_inventory_sha256": inventory["content_sha256"],
        "support_design_file_sha256": support_design_file_sha256,
        "nominal_base_axis_xy_mm": [305.0, 457.0],
        "nominal_base_axis_state": "ASSUMED_ONLY_NOT_COLLISION_OR_REACH_PROOF",
        "base_missing_inputs": base_missing,
        "support_topology": support["topology"],
        "nominal_camera_axis_xy_mm": support["camera_axis_xy_mm"],
        "nominal_camera_entrance_pupil_z_mm": support[
            "nominal_entrance_pupil_z_mm"
        ],
        "active_camera_collision_requirements": camera_requirements,
        "camera_architecture_compatible": False,
        "camera_architecture_mismatch": (
            "active collision contract describes rigid camera attachment frames "
            "and a moving cable; current design is a static overhead portal"
        ),
        "camera_missing_inputs": camera_missing,
        "installed_base_geometry_ready": False,
        "installed_camera_geometry_ready": False,
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "base_camera_geometry_sha256": _sha256(core)}

__all__ = [
    "SCHEMA",
    "EXPECTED_RESULT_RECEIPT_SHA256",
    "EXPECTED_ROUTE_RECEIPT_SHA256",
    "C03FullBodyGeometryAuditV1Error",
    "BASE_CAMERA_GEOMETRY_SCHEMA",
    "C03RouteCollisionHandoffV1Error",
    "FULL_BODY_GEOMETRY_SCHEMA",
    "NOMINAL_TOOL_BINDING_SCHEMA",
    "STATION_HEIGHT_SENSITIVITY_SCHEMA",
    "assess_c03_full_body_geometry_readiness_v1",
    "assess_c03_base_camera_geometry_readiness_v1",
    "assess_c03_nominal_tool_binding_readiness_v1",
    "assess_c03_station_height_route_sensitivity_v1",
    "prepare_c03_route_collision_handoff_v1",
]
