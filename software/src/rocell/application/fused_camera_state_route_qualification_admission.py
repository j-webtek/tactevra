"""Bind one fused-camera target to an exact qualified profile route.

The camera/state planning boundary selects a key, attachment profile, and
installed collision profile, while the established fixed-camera keyboard
pipeline constructs and qualifies complete routes.  This adapter proves that
the selected target is represented by the exact execution and trajectory
artifacts whose partitioned route passed reviewed installed-geometry collision
qualification.

The result remains zero-authority.  In particular, retained route clearance
does not replace a fresh observed route-entry qualification.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from typing import Any, Mapping

from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_collision_partitions_v1 import (
    SCHEMA as PARTITIONS_SCHEMA,
    STATUS as PARTITIONS_STATUS,
    ZERO_AUTHORITY as PARTITIONS_ZERO_AUTHORITY,
)
from .fixed_camera_keyboard_profiled_route_screen_v1 import (
    SCHEMA as ROUTE_SCREEN_SCHEMA,
    STATUS as ROUTE_SCREEN_STATUS,
    ZERO_AUTHORITY as ROUTE_SCREEN_ZERO_AUTHORITY,
)
from .fixed_camera_keyboard_route_bound_collision_qualification_v1 import (
    SCHEMA as ROUTE_BOUND_SCHEMA,
    STATUS_READY as ROUTE_BOUND_READY,
    ZERO_AUTHORITY as ROUTE_BOUND_ZERO_AUTHORITY,
)
from .fused_camera_state_planning_admission import (
    PLANNING_ADMISSION_RECEIPT_SCHEMA,
)
from .typing_execution_plan_v1 import (
    TypingExecutionPlanV1,
    TypingExecutionPlanV1Error,
)
from .typing_trajectory_plan_v1 import (
    SCHEMA as TRAJECTORY_SCHEMA,
    STATUS as TRAJECTORY_STATUS,
)


SCHEMA = "rocell.fused_camera_state_route_qualification_admission.v1"
STATUS = "FUSED_CAMERA_TARGET_EXACT_ROUTE_QUALIFIED_FRESH_ENTRY_REQUIRED"
_PLANNING_FIELDS = {
    "schema",
    "status",
    "planning_admission_id",
    "planner_id",
    "planning_context_sha256",
    "fusion_receipt_sha256",
    "board_registration_sha256",
    "robot_localization_sha256",
    "clearance_intake_sha256",
    "attachment_profile",
    "admitted_at",
    "valid_until",
    "plan_candidate",
    "calibrated_feedback",
    "camera_observation",
    "next_required_gate",
    "blockers",
    "limitations",
    "fused_camera_state_planning_admitted",
    "plan_candidate_emitted",
    "trajectory_generated",
    "collision_screening_executed",
    "continuous_clearance_verified",
    "automatic_retry_allowed",
    "motion_authorized",
    "contact_authorized",
    "physical_authority",
}
_CANDIDATE_FIELDS = {
    "target_key_id",
    "attachment_profile",
    "board_xy_mm",
    "robot_xyz_mm",
    "requested_hover_clearance_mm",
    "maximum_waypoint_count",
    "installed_collision_profile_content_sha256",
    "clearance_policy_sha256",
}
ZERO_AUTHORITY: Mapping[str, object] = {
    "trajectory_compiled_offline": True,
    "exact_route_collision_qualification_verified": True,
    "fresh_observed_route_entry_present": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_writes": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}


class FusedCameraStateRouteQualificationAdmissionError(ValueError):
    """The selected camera target and exact qualified route do not agree."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FusedCameraStateRouteQualificationAdmissionError(
            "route qualification input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FusedCameraStateRouteQualificationAdmissionError(message)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value  # type: ignore[return-value]


def _sealed(
    value: object, hash_field: str, label: str,
) -> Mapping[str, Any]:
    document = _mapping(value, label)
    core = dict(document)
    supplied = core.pop(hash_field, None)
    _require(
        isinstance(supplied, str) and supplied == _sha(core),
        f"{label} hash differs",
    )
    return document


def _timestamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be an ISO-8601 timestamp")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FusedCameraStateRouteQualificationAdmissionError(
            f"{label} must be an ISO-8601 timestamp"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _number(value: object, label: str) -> float:
    _require(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


def _point_xy(value: object, label: str) -> tuple[float, float]:
    point = _mapping(value, label)
    _require(point.get("frame") == "board", f"{label} must use the board frame")
    return _number(point.get("x"), f"{label}.x"), _number(
        point.get("y"), f"{label}.y"
    )


def _point_document(point: object) -> dict[str, object]:
    return {
        "frame": getattr(point, "frame"),
        "x": float(getattr(point, "x")),
        "y": float(getattr(point, "y")),
        "z": float(getattr(point, "z")),
    }


def _validate_planning(
    value: object, active_profile: str, consumed_at: datetime,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    receipt = _mapping(value, "planning receipt")
    candidate = _mapping(receipt.get("plan_candidate"), "plan candidate")
    _require(
        set(receipt) == _PLANNING_FIELDS
        and set(candidate) == _CANDIDATE_FIELDS
        and receipt.get("schema") == PLANNING_ADMISSION_RECEIPT_SCHEMA
        and receipt.get("status") == "FUSED_CAMERA_STATE_PLANNING_ADMITTED"
        and receipt.get("fused_camera_state_planning_admitted") is True
        and receipt.get("plan_candidate_emitted") is True,
        "planning receipt is not admitted",
    )
    expected_id = "fused-camera-state-planning:" + _sha(
        {
            "fusion_receipt_sha256": receipt.get("fusion_receipt_sha256"),
            "planning_context_sha256": receipt.get("planning_context_sha256"),
            "plan_candidate": candidate,
        }
    )
    _require(
        receipt.get("planning_admission_id") == expected_id,
        "planning admission identity differs",
    )
    _require(
        active_profile in SUPPORTED_PROFILES
        and receipt.get("attachment_profile") == active_profile
        and candidate.get("attachment_profile") == active_profile,
        "active attachment profile differs from the planning receipt",
    )
    _require(
        receipt.get("trajectory_generated") is False
        and receipt.get("collision_screening_executed") is False
        and receipt.get("continuous_clearance_verified") is False
        and receipt.get("automatic_retry_allowed") is False
        and receipt.get("motion_authorized") is False
        and receipt.get("contact_authorized") is False
        and receipt.get("physical_authority") is False,
        "planning receipt authority is invalid",
    )
    admitted = _timestamp(receipt.get("admitted_at"), "planning admitted_at")
    valid_until = _timestamp(receipt.get("valid_until"), "planning valid_until")
    _require(
        admitted <= consumed_at <= valid_until,
        "planning receipt is not fresh at route admission",
    )
    board_xy = candidate.get("board_xy_mm")
    _require(
        isinstance(board_xy, list) and len(board_xy) == 2,
        "plan candidate board coordinates differ",
    )
    _number(board_xy[0], "plan candidate board x")
    _number(board_xy[1], "plan candidate board y")
    robot_xyz = candidate.get("robot_xyz_mm")
    _require(
        isinstance(robot_xyz, list) and len(robot_xyz) == 3,
        "plan candidate robot coordinates differ",
    )
    for index, coordinate in enumerate(robot_xyz):
        _number(coordinate, f"plan candidate robot coordinate {index}")
    _require(
        isinstance(candidate.get("target_key_id"), str)
        and bool(candidate["target_key_id"]),
        "plan candidate target is invalid",
    )
    return receipt, candidate


def _validate_target_route(
    plan_document: object,
    trajectory_document: object,
    candidate: Mapping[str, Any],
) -> tuple[TypingExecutionPlanV1, Mapping[str, Any], list[int]]:
    try:
        plan = TypingExecutionPlanV1.from_mapping(plan_document)
    except (TypingExecutionPlanV1Error, TypeError, ValueError) as exc:
        raise FusedCameraStateRouteQualificationAdmissionError(str(exc)) from exc
    trajectory = _sealed(
        trajectory_document, "trajectory_plan_sha256", "typing trajectory plan"
    )
    _require(
        trajectory.get("schema") == TRAJECTORY_SCHEMA
        and trajectory.get("source_plan_sha256") == plan.plan_sha256
        and trajectory.get("status") == TRAJECTORY_STATUS
        and trajectory.get("ik_screening_executed") is False
        and trajectory.get("collision_screening_executed") is False
        and trajectory.get("continuous_collision_proven") is False
        and trajectory.get("controller_commands") == []
        and trajectory.get("hardware_commands_generated") == 0
        and trajectory.get("hardware_access") is False
        and trajectory.get("physical_authority") is False,
        "typing trajectory plan is invalid or authority-bearing",
    )
    target = candidate["target_key_id"]
    actions = [action for action in plan.actions if action.target_id == target]
    _require(bool(actions), "selected target is absent from the execution plan")
    candidate_xy = tuple(
        _number(item, "plan candidate board coordinate")
        for item in candidate["board_xy_mm"]
    )
    for action in actions:
        action_xy = (action.contact_point.x, action.contact_point.y)
        _require(
            all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(action_xy, candidate_xy)),
            "selected target board coordinates differ from the execution plan",
        )
        clearance = action.hover_point.z - action.contact_point.z
        _require(
            math.isclose(
                clearance,
                _number(
                    candidate.get("requested_hover_clearance_mm"),
                    "requested hover clearance",
                ),
                abs_tol=1e-9,
            ),
            "selected target hover clearance differs from the execution plan",
        )

    waypoints = trajectory.get("phase_waypoints")
    _require(isinstance(waypoints, list), "trajectory phase waypoints are absent")
    action_indices = [action.action_index for action in actions]
    for action in actions:
        rows = [
            row
            for row in waypoints
            if isinstance(row, Mapping)
            and row.get("action_index") == action.action_index
            and row.get("target_id") == target
        ]
        _require(
            [row.get("phase") for row in rows] == ["HOVER", "CONTACT", "RETRACT"],
            "selected target trajectory phases differ",
        )
        expected_points = (
            _point_document(action.hover_point),
            _point_document(action.contact_point),
            _point_document(action.retract_point),
        )
        _require(
            all(row.get("point") == point for row, point in zip(rows, expected_points)),
            "selected target trajectory waypoints differ from the execution plan",
        )
        _point_xy(rows[1].get("point"), "selected contact waypoint")
    maximum_waypoints = candidate.get("maximum_waypoint_count")
    _require(
        type(maximum_waypoints) is int
        and len(actions) * 3 <= maximum_waypoints,
        "selected target trajectory exceeds the admitted waypoint bound",
    )
    return plan, trajectory, action_indices


def admit_fused_camera_state_route_qualification(
    planning_receipt_document: Mapping[str, Any],
    typing_execution_plan_document: Mapping[str, Any],
    typing_trajectory_plan_document: Mapping[str, Any],
    profiled_route_screen_manifest_document: Mapping[str, Any],
    profiled_collision_partitions_manifest_document: Mapping[str, Any],
    route_bound_collision_qualification_document: Mapping[str, Any],
    *,
    current_attachment_profile: str,
    consumed_at: str,
) -> dict[str, Any]:
    """Admit one fresh planned target only onto its exact qualified route."""

    consumed = _timestamp(consumed_at, "consumed_at")
    planning, candidate = _validate_planning(
        planning_receipt_document, current_attachment_profile, consumed
    )
    plan, trajectory, action_indices = _validate_target_route(
        typing_execution_plan_document, typing_trajectory_plan_document, candidate
    )

    route_screen = _sealed(
        profiled_route_screen_manifest_document,
        "profiled_route_screen_manifest_sha256",
        "profiled route screen manifest",
    )
    route_profiles = _mapping(route_screen.get("profiles"), "route profiles")
    _require(
        route_screen.get("schema") == ROUTE_SCREEN_SCHEMA
        and route_screen.get("status") == ROUTE_SCREEN_STATUS
        and set(route_profiles) == set(SUPPORTED_PROFILES)
        and route_screen.get("profile_separation_preserved") is True
        and route_screen.get("authority") == ROUTE_SCREEN_ZERO_AUTHORITY,
        "profiled route screen manifest is invalid or authority-bearing",
    )
    route_row = _mapping(
        route_profiles.get(current_attachment_profile), "selected route profile"
    )
    _require(
        route_row.get("profile") == current_attachment_profile
        and route_row.get("typing_execution_plan_sha256") == plan.plan_sha256
        and route_row.get("typing_trajectory_policy_sha256")
        == trajectory.get("policy_sha256")
        and route_row.get("typing_trajectory_plan_sha256")
        == trajectory.get("trajectory_plan_sha256")
        and route_row.get("installed_collision_profile_content_sha256")
        == candidate.get("installed_collision_profile_content_sha256"),
        "selected target differs from the profiled route screen lineage",
    )

    partitions = _sealed(
        profiled_collision_partitions_manifest_document,
        "profiled_collision_partitions_manifest_sha256",
        "profiled collision partitions manifest",
    )
    partition_profiles = _mapping(
        partitions.get("profiles"), "collision partition profiles"
    )
    _require(
        partitions.get("schema") == PARTITIONS_SCHEMA
        and partitions.get("status") == PARTITIONS_STATUS
        and partitions.get("source_profiled_route_screen_manifest_sha256")
        == route_screen["profiled_route_screen_manifest_sha256"]
        and set(partition_profiles) == set(SUPPORTED_PROFILES)
        and partitions.get("profile_separation_preserved") is True
        and partitions.get("authority") == PARTITIONS_ZERO_AUTHORITY,
        "collision partition manifest differs from the route screen",
    )
    partition_row = _mapping(
        partition_profiles.get(current_attachment_profile),
        "selected collision partition profile",
    )
    _require(
        partition_row.get("typing_execution_plan_sha256") == plan.plan_sha256
        and partition_row.get("typing_trajectory_plan_sha256")
        == trajectory.get("trajectory_plan_sha256")
        and partition_row.get("installed_collision_profile_content_sha256")
        == candidate.get("installed_collision_profile_content_sha256"),
        "selected collision partition lineage differs",
    )

    route_bound = _sealed(
        route_bound_collision_qualification_document,
        "route_bound_collision_qualification_sha256",
        "route-bound collision qualification",
    )
    qualified_profiles = _mapping(
        route_bound.get("profiles"), "route-bound profiles"
    )
    _require(
        route_bound.get("schema") == ROUTE_BOUND_SCHEMA
        and route_bound.get("status") == ROUTE_BOUND_READY
        and set(qualified_profiles) == set(SUPPORTED_PROFILES)
        and route_bound.get("profile_separation_preserved") is True
        and route_bound.get("exact_route_binding_verified_before_evaluation") is True
        and route_bound.get("authority") == ROUTE_BOUND_ZERO_AUTHORITY,
        "route-bound collision qualification is not ready and zero-authority",
    )
    qualified_row = _mapping(
        qualified_profiles.get(current_attachment_profile),
        "selected qualified route profile",
    )
    _require(
        qualified_row.get("profile") == current_attachment_profile
        and qualified_row.get("installed_collision_profile_sha256")
        == candidate.get("installed_collision_profile_content_sha256")
        and qualified_row.get("partitioned_typing_collision_intake_sha256")
        == partition_row.get("partitioned_typing_collision_intake_sha256"),
        "selected qualified route differs from the planned profile",
    )

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "planning_admission_id": planning.get("planning_admission_id"),
        "planning_receipt_sha256": _sha(planning),
        "attachment_profile": current_attachment_profile,
        "target_key_id": candidate["target_key_id"],
        "target_action_indices": action_indices,
        "board_xy_mm": list(candidate["board_xy_mm"]),
        "robot_xyz_mm": list(candidate["robot_xyz_mm"]),
        "typing_execution_plan_sha256": plan.plan_sha256,
        "typing_trajectory_plan_sha256": trajectory["trajectory_plan_sha256"],
        "profiled_route_screen_manifest_sha256": route_screen[
            "profiled_route_screen_manifest_sha256"
        ],
        "profiled_collision_partitions_manifest_sha256": partitions[
            "profiled_collision_partitions_manifest_sha256"
        ],
        "partitioned_typing_collision_intake_sha256": partition_row[
            "partitioned_typing_collision_intake_sha256"
        ],
        "route_bound_collision_qualification_sha256": route_bound[
            "route_bound_collision_qualification_sha256"
        ],
        "route_envelope_binding_sha256": qualified_row[
            "route_envelope_binding_sha256"
        ],
        "installed_collision_profile_sha256": qualified_row[
            "installed_collision_profile_sha256"
        ],
        "consumed_at": consumed_at,
        "profile_separation_preserved": True,
        "exact_target_route_binding_verified": True,
        "blockers": ["FRESH_OBSERVED_ROUTE_ENTRY_QUALIFICATION_REQUIRED"],
        "next_required_gate": "ROUTE_BOUND_FRESH_OBSERVED_ENTRY_QUALIFICATION",
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "route_qualification_admission_sha256": _sha(core)}


__all__ = [
    "SCHEMA",
    "STATUS",
    "ZERO_AUTHORITY",
    "FusedCameraStateRouteQualificationAdmissionError",
    "admit_fused_camera_state_route_qualification",
]
