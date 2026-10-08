"""Strict zero-authority handoff from an admitted C03 route to collision intake."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from typing import Any, Mapping

from rocell.models.frames import Point3Mm

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .context import SimulationContext
from .installed_collision_measurement_manifest_v1 import (
    build_installed_collision_nominal_envelope_audit_v1,
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


__all__ = [
    "SCHEMA",
    "EXPECTED_RESULT_RECEIPT_SHA256",
    "EXPECTED_ROUTE_RECEIPT_SHA256",
    "C03RouteCollisionHandoffV1Error",
    "STATION_HEIGHT_SENSITIVITY_SCHEMA",
    "assess_c03_station_height_route_sensitivity_v1",
    "prepare_c03_route_collision_handoff_v1",
]
