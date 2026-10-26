"""Admit one fused camera/state receipt to bounded planning intake."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
import re
from typing import Any, Mapping

from rocell.calibration.position_vector_campaign import canonical_sha256

from .camera_feedback_state_fusion_admission import (
    BOARD_REGISTRATION_SCHEMA,
    FUSION_ADMISSION_RECEIPT_SCHEMA,
)


PLANNING_ADMISSION_SCHEMA = "rocell.fused_camera_state_planning_admission.v1"
PLANNING_ADMISSION_RECEIPT_SCHEMA = (
    "rocell.fused_camera_state_planning_admission_receipt.v1"
)
ROBOT_LOCALIZATION_SCHEMA = "rocell.fixed_camera_keyboard_robot_localization.v1"
CLEARANCE_INTAKE_SCHEMA = "rocell.fixed_camera_keyboard_clearance_intake.v1"
MAX_PLANNING_LIFETIME_SECONDS = 15
MAX_PLAN_CANDIDATE_WAYPOINTS = 128
MAX_HOVER_CLEARANCE_MM = 100.0

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ADMISSION_FIELDS = frozenset(
    {
        "schema", "planner_id", "planning_context_sha256",
        "fusion_receipt_sha256", "board_registration_sha256",
        "robot_localization_sha256", "clearance_intake_sha256",
        "attachment_profile", "target_key_id", "admitted_at", "valid_until",
        "maximum_planning_lifetime_seconds", "maximum_waypoint_count",
        "requested_hover_clearance_mm",
    }
)


class FusedCameraStatePlanningAdmissionError(ValueError):
    """Fused state or profile-specific planning evidence is ineligible."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FusedCameraStatePlanningAdmissionError(message)


def _mapping(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return dict(value)  # type: ignore[arg-type]


def _identifier(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None,
        f"{label} is not a bounded identifier",
    )
    return value


def _digest(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _DIGEST.fullmatch(value) is not None,
        f"{label} is not a lowercase SHA-256",
    )
    return value


def _timestamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FusedCameraStatePlanningAdmissionError(f"{label} is invalid") from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _finite_vector(value: object, size: int, label: str) -> list[float]:
    _require(isinstance(value, list) and len(value) == size, f"{label} is invalid")
    _require(
        all(
            not isinstance(item, bool)
            and isinstance(item, (int, float))
            and math.isfinite(float(item))
            for item in value
        ),
        f"{label} is invalid",
    )
    return [float(item) for item in value]


def _unique_target(
    candidates: object, *, key_id: str, coordinate_field: str, size: int,
    label: str, expected_count: int = 46,
) -> list[float]:
    _require(isinstance(candidates, list), f"{label} candidates are invalid")
    _require(
        len(candidates) == expected_count,
        f"{label} candidate coverage is incomplete",
    )
    matches = []
    seen: set[str] = set()
    for candidate in candidates:
        item = _mapping(candidate, f"{label} candidate")
        candidate_key = _identifier(item.get("key_id"), f"{label} key_id")
        _require(candidate_key not in seen, f"{label} key candidates are duplicated")
        seen.add(candidate_key)
        point = _finite_vector(
            item.get(coordinate_field), size, f"{label} {coordinate_field}"
        )
        if candidate_key == key_id:
            matches.append(point)
    _require(len(matches) == 1, f"target key is absent from {label} candidates")
    return matches[0]


def _validate_fusion(fusion: Mapping[str, Any]) -> None:
    _require(
        fusion.get("schema") == FUSION_ADMISSION_RECEIPT_SCHEMA
        and fusion.get("status") == "CAMERA_FEEDBACK_STATE_FUSION_ADMITTED"
        and fusion.get("next_required_gate")
        == "FUSED_CAMERA_STATE_PLANNING_ADMISSION"
        and fusion.get("camera_feedback_state_fusion_admitted") is True,
        "camera/state fusion is not eligible for planning admission",
    )
    _require(
        fusion.get("planning_authorized") is False
        and fusion.get("automatic_retry_allowed") is False
        and fusion.get("motion_authorized") is False
        and fusion.get("contact_authorized") is False
        and fusion.get("physical_authority") is False,
        "camera/state fusion authority is invalid",
    )


def _validate_registration(
    registration: Mapping[str, Any], *, profile: str, target_key: str,
) -> list[float]:
    _require(
        registration.get("schema") == BOARD_REGISTRATION_SCHEMA
        and registration.get("status")
        == "ABSOLUTE_KEYBOARD_TO_BOARD_LOCALIZATION_READY"
        and registration.get("profile") == profile
        and registration.get("absolute_keyboard_to_board_transform_verified")
        is True
        and registration.get("board_space_key_candidates_emitted") is True,
        "board registration is not ready for planning",
    )
    _require(
        registration.get("motion_targets_emitted") is False
        and registration.get("motion_authorized") is False
        and registration.get("contact_authorized") is False,
        "board registration authority is invalid",
    )
    return _unique_target(
        registration.get("board_space_key_candidates"),
        key_id=target_key,
        coordinate_field="board_xy_mm",
        size=2,
        label="board registration",
    )


def _validate_localization(
    localization: Mapping[str, Any], *, profile: str, target_key: str,
    registration: Mapping[str, Any],
) -> tuple[list[float], list[Mapping[str, Any]]]:
    _require(
        localization.get("schema") == ROBOT_LOCALIZATION_SCHEMA
        and localization.get("status")
        == "ROBOT_FRAME_LOCALIZATION_CANDIDATES_READY"
        and localization.get("board_to_robot_transform_verified") is True
        and localization.get("profile_separation_preserved") is True,
        "robot localization is not ready for planning",
    )
    _require(
        localization.get("target_profile_sha256")
        == registration.get("target_profile_sha256"),
        "board registration and robot localization target profiles differ",
    )
    _require(
        localization.get("motion_targets_emitted") is False
        and localization.get("physical_clearance_verified") is False
        and localization.get("motion_authorized") is False
        and localization.get("contact_authorized") is False,
        "robot localization authority is invalid",
    )
    profiles = _mapping(localization.get("profiles"), "localization profiles")
    _require(
        set(profiles) == {"no_attachment", "stylus_attachment"},
        "robot localization profile separation is incomplete",
    )
    selected = _mapping(profiles.get(profile), "selected localization profile")
    _require(
        selected.get("profile") == profile
        and selected.get("board_to_robot_transform_verified") is True
        and selected.get("robot_frame_localization_candidates_emitted") is True
        and selected.get("motion_targets_emitted") is False
        and selected.get("physical_clearance_verified") is False
        and selected.get("motion_authorized") is False
        and selected.get("contact_authorized") is False,
        "selected localization profile is invalid",
    )
    candidates = selected.get("robot_frame_localization_candidates")
    point = _unique_target(
        candidates,
        key_id=target_key,
        coordinate_field="robot_xyz_mm",
        size=3,
        label="robot localization",
    )
    return point, candidates  # type: ignore[return-value]


def _validate_clearance_intake(
    clearance: Mapping[str, Any], *, profile: str,
    localization_sha256: str, localization_candidates: list[Mapping[str, Any]],
) -> Mapping[str, Any]:
    _require(
        clearance.get("schema") == CLEARANCE_INTAKE_SCHEMA
        and clearance.get("status")
        == "READY_FOR_PROFILE_SPECIFIC_ROUTE_CONSTRUCTION"
        and clearance.get("robot_localization_sha256") == localization_sha256
        and clearance.get("profile_separation_preserved") is True,
        "clearance intake is not bound to the current localization",
    )
    _require(
        clearance.get("trajectory_generated") is False
        and clearance.get("collision_screening_executed") is False
        and clearance.get("continuous_clearance_verified") is False
        and clearance.get("controller_commands") == []
        and clearance.get("hardware_commands_generated") == 0
        and clearance.get("hardware_access") is False
        and clearance.get("motion_authorized") is False
        and clearance.get("contact_authorized") is False
        and clearance.get("physical_authority") is False,
        "clearance intake authority is invalid",
    )
    profiles = _mapping(clearance.get("profiles"), "clearance profiles")
    _require(
        set(profiles) == {"no_attachment", "stylus_attachment"},
        "clearance profile separation is incomplete",
    )
    selected = _mapping(profiles.get(profile), "selected clearance profile")
    _require(
        selected.get("profile") == profile
        and selected.get("route_construction_ready") is True
        and selected.get("collision_screening_executed") is False
        and selected.get("continuous_clearance_verified") is False,
        "selected clearance profile is not ready for route construction",
    )
    _require(
        selected.get("robot_frame_localization_candidates_sha256")
        == canonical_sha256(localization_candidates),
        "clearance intake localization candidates differ",
    )
    _digest(
        selected.get("installed_collision_profile_content_sha256"),
        "installed collision profile",
    )
    _digest(selected.get("clearance_policy_sha256"), "clearance policy")
    return selected


def admit_fused_camera_state_planning(
    *,
    fusion_receipt_document: Mapping[str, Any],
    board_registration_document: Mapping[str, Any],
    robot_localization_document: Mapping[str, Any],
    clearance_intake_document: Mapping[str, Any],
    admission_document: Mapping[str, Any],
    planning_context_document: Mapping[str, Any],
    current_attachment_profile: str,
) -> dict[str, Any]:
    """Select one exact target and emit a zero-authority plan candidate."""

    fusion = _mapping(fusion_receipt_document, "fusion receipt")
    registration = _mapping(board_registration_document, "board registration")
    localization = _mapping(robot_localization_document, "robot localization")
    clearance = _mapping(clearance_intake_document, "clearance intake")
    admission = _mapping(admission_document, "planning admission")
    context = _mapping(planning_context_document, "planning context")
    _require(
        set(admission) == _ADMISSION_FIELDS,
        "planning admission fields do not match the contract",
    )
    _require(
        admission["schema"] == PLANNING_ADMISSION_SCHEMA,
        "planning admission schema is invalid",
    )
    _validate_fusion(fusion)

    planner_id = _identifier(admission["planner_id"], "planner_id")
    _require(
        context.get("planner_id") == planner_id
        and context.get("fusion_consumer_id") == fusion.get("fusion_consumer_id"),
        "planning context does not own the fused state",
    )
    context_sha = canonical_sha256(context)
    _require(
        admission["planning_context_sha256"] == context_sha,
        "planning context differs from the admitted context",
    )
    profile = _identifier(current_attachment_profile, "current_attachment_profile")
    _require(
        admission["attachment_profile"] == profile
        == fusion.get("attachment_profile"),
        "current attachment profile differs across planning inputs",
    )

    bindings = (
        ("fusion_receipt_sha256", fusion),
        ("board_registration_sha256", registration),
        ("robot_localization_sha256", localization),
        ("clearance_intake_sha256", clearance),
    )
    for field, document in bindings:
        _require(
            admission[field] == canonical_sha256(document), f"{field} mismatch"
        )
    _require(
        admission["board_registration_sha256"]
        == fusion.get("board_registration_sha256"),
        "planning and fusion board registrations differ",
    )

    target_key = _identifier(admission["target_key_id"], "target_key_id")
    board_xy = _validate_registration(
        registration, profile=profile, target_key=target_key
    )
    localization_sha = canonical_sha256(localization)
    robot_xyz, localization_candidates = _validate_localization(
        localization,
        profile=profile,
        target_key=target_key,
        registration=registration,
    )
    selected_clearance = _validate_clearance_intake(
        clearance,
        profile=profile,
        localization_sha256=localization_sha,
        localization_candidates=localization_candidates,
    )

    lifetime = admission["maximum_planning_lifetime_seconds"]
    waypoint_count = admission["maximum_waypoint_count"]
    hover_clearance = admission["requested_hover_clearance_mm"]
    _require(
        type(lifetime) is int and 0 < lifetime <= MAX_PLANNING_LIFETIME_SECONDS,
        "maximum planning lifetime is outside the bounded contract",
    )
    _require(
        type(waypoint_count) is int
        and 2 <= waypoint_count <= MAX_PLAN_CANDIDATE_WAYPOINTS,
        "maximum waypoint count is outside the bounded contract",
    )
    _require(
        not isinstance(hover_clearance, bool)
        and isinstance(hover_clearance, (int, float))
        and math.isfinite(float(hover_clearance))
        and 0.0 < float(hover_clearance) <= MAX_HOVER_CLEARANCE_MM,
        "requested hover clearance is outside the bounded contract",
    )
    fused = _timestamp(fusion.get("fused_at"), "fusion fused_at")
    admitted = _timestamp(admission["admitted_at"], "admitted_at")
    valid_until = _timestamp(admission["valid_until"], "valid_until")
    fusion_valid_until = _timestamp(fusion.get("valid_until"), "fusion valid_until")
    _require(fused <= admitted < valid_until, "planning timestamp ordering is invalid")
    _require(
        valid_until <= admitted + timedelta(seconds=lifetime)
        and valid_until <= fusion_valid_until,
        "planning validity exceeds a source lifetime",
    )

    candidate = {
        "target_key_id": target_key,
        "attachment_profile": profile,
        "board_xy_mm": board_xy,
        "robot_xyz_mm": robot_xyz,
        "requested_hover_clearance_mm": float(hover_clearance),
        "maximum_waypoint_count": waypoint_count,
        "installed_collision_profile_content_sha256": selected_clearance[
            "installed_collision_profile_content_sha256"
        ],
        "clearance_policy_sha256": selected_clearance["clearance_policy_sha256"],
    }
    basis = {
        "fusion_receipt_sha256": admission["fusion_receipt_sha256"],
        "planning_context_sha256": context_sha,
        "plan_candidate": candidate,
    }
    return {
        "schema": PLANNING_ADMISSION_RECEIPT_SCHEMA,
        "status": "FUSED_CAMERA_STATE_PLANNING_ADMITTED",
        "planning_admission_id": (
            f"fused-camera-state-planning:{canonical_sha256(basis)}"
        ),
        "planner_id": planner_id,
        "planning_context_sha256": context_sha,
        **{field: admission[field] for field, _ in bindings},
        "attachment_profile": profile,
        "admitted_at": admission["admitted_at"],
        "valid_until": admission["valid_until"],
        "plan_candidate": candidate,
        "calibrated_feedback": dict(fusion["calibrated_feedback"]),
        "camera_observation": dict(fusion["camera_observation"]),
        "next_required_gate": (
            "PROFILE_SPECIFIC_TRAJECTORY_CONSTRUCTION_AND_COLLISION_QUALIFICATION"
        ),
        "blockers": [
            "TRAJECTORY_NOT_CONSTRUCTED",
            "CONTINUOUS_COLLISION_NOT_QUALIFIED",
            "PHYSICAL_CLEARANCE_NOT_ESTABLISHED",
            "EXECUTION_ADMISSION_NOT_GRANTED",
        ],
        "limitations": [
            "This receipt selects one profile-bound localization candidate.",
            "The installed collision profile and clearance policy are planning inputs only.",
            "A bounded trajectory and continuous collision qualification remain mandatory.",
            "Planning admission grants no retry, motion, contact, or physical authority.",
        ],
        "fused_camera_state_planning_admitted": True,
        "plan_candidate_emitted": True,
        "trajectory_generated": False,
        "collision_screening_executed": False,
        "continuous_clearance_verified": False,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }


__all__ = [
    "CLEARANCE_INTAKE_SCHEMA",
    "MAX_HOVER_CLEARANCE_MM",
    "MAX_PLAN_CANDIDATE_WAYPOINTS",
    "MAX_PLANNING_LIFETIME_SECONDS",
    "PLANNING_ADMISSION_RECEIPT_SCHEMA",
    "PLANNING_ADMISSION_SCHEMA",
    "ROBOT_LOCALIZATION_SCHEMA",
    "FusedCameraStatePlanningAdmissionError",
    "admit_fused_camera_state_planning",
]
