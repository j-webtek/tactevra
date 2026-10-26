"""Bind fused calibrated state to one route-qualified observed entry.

The camera pipeline and the retained typing-entry pipeline historically met at
the installed route profile, but did not prove that their physical start state
was the same observation.  This adapter closes that final lineage gap.  It
walks the complete snapshot -> fusion -> planning -> route chain, requires a
passing route-bound entry qualification, and compares the calibrated joints
with the exact start joints retained by that qualification.

The receipt is advisory and zero-authority.  It opens no camera, controller,
simulator, or hardware transport and emits no command.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from typing import Any, Mapping

from rocell.arm.position_vector_calibration import JOINT_ORDER
from rocell.calibration.position_vector_campaign import canonical_sha256
from rocell.kinematics import ARM_JOINT_NAMES

from .calibrated_position_vector_state_snapshot_read_admission import (
    SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA,
)
from .camera_feedback_state_fusion_admission import (
    FUSION_ADMISSION_RECEIPT_SCHEMA,
)
from .fixed_camera_keyboard_route_bound_entry_qualification_v1 import (
    SCHEMA as ENTRY_QUALIFICATION_SCHEMA,
    STATUS_PASS as ENTRY_QUALIFICATION_PASS,
    ZERO_AUTHORITY as ENTRY_ZERO_AUTHORITY,
    FixedCameraKeyboardRouteBoundEntryQualificationV1Error,
    parse_fixed_camera_keyboard_route_bound_entry_v1,
)
from .fused_camera_state_planning_admission import (
    PLANNING_ADMISSION_RECEIPT_SCHEMA,
)
from .fused_camera_state_route_qualification_admission import (
    SCHEMA as ROUTE_ADMISSION_SCHEMA,
    STATUS as ROUTE_ADMISSION_STATUS,
    ZERO_AUTHORITY as ROUTE_ZERO_AUTHORITY,
)
from .typing_observed_route_entry_v1 import (
    TypingObservedRouteEntryV1Error,
    parse_typing_observed_route_entry_v1,
)


SCHEMA = "rocell.fused_camera_state_route_entry_admission.v1"
STATUS = "FUSED_CAMERA_STATE_ROUTE_ENTRY_QUALIFIED_ZERO_AUTHORITY"
NEXT_REQUIRED_GATE = "INDEPENDENT_EXECUTION_RELEASE_GATES"
ZERO_AUTHORITY: Mapping[str, object] = {
    "fresh_calibrated_start_state_bound": True,
    "exact_route_entry_qualification_verified": True,
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
_FEEDBACK_SCHEMA = "rocell.calibrated_position_vector_feedback.v1"
_MODEL_JOINTS = dict(zip(ARM_JOINT_NAMES, JOINT_ORDER[:5], strict=True))


class FusedCameraStateRouteEntryAdmissionError(ValueError):
    """Fresh calibrated state and route-entry evidence do not agree."""


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
        raise FusedCameraStateRouteEntryAdmissionError(
            "route-entry admission is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FusedCameraStateRouteEntryAdmissionError(message)


def _mapping(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return dict(value)  # type: ignore[arg-type]


def _timestamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be an ISO-8601 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FusedCameraStateRouteEntryAdmissionError(
            f"{label} must be an ISO-8601 timestamp"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _sealed_route_admission(value: Mapping[str, Any]) -> dict[str, Any]:
    route = _mapping(value, "route qualification admission")
    core = dict(route)
    supplied = core.pop("route_qualification_admission_sha256", None)
    _require(
        isinstance(supplied, str) and supplied == _sha(core),
        "route qualification admission hash differs",
    )
    _require(
        route.get("schema") == ROUTE_ADMISSION_SCHEMA
        and route.get("status") == ROUTE_ADMISSION_STATUS
        and route.get("exact_target_route_binding_verified") is True
        and route.get("profile_separation_preserved") is True
        and route.get("next_required_gate")
        == "ROUTE_BOUND_FRESH_OBSERVED_ENTRY_QUALIFICATION"
        and route.get("authority") == dict(ROUTE_ZERO_AUTHORITY),
        "route qualification admission is not eligible and zero-authority",
    )
    return route


def _calibrated_arm_joints(feedback_value: object) -> dict[str, float]:
    feedback = _mapping(feedback_value, "calibrated feedback")
    joints = _mapping(feedback.get("canonical_joints_rad"), "canonical joints")
    _require(
        feedback.get("schema") == _FEEDBACK_SCHEMA
        and feedback.get("canonical_joint_order") == list(JOINT_ORDER)
        and feedback.get("accepted_as_calibrated_joint_state") is True
        and feedback.get("motion_authorized") is False
        and feedback.get("physical_authority") is False
        and set(joints) == set(JOINT_ORDER),
        "calibrated feedback is not an accepted zero-authority joint state",
    )
    result: dict[str, float] = {}
    for arm_name, feedback_name in _MODEL_JOINTS.items():
        raw = joints[feedback_name]
        _require(
            not isinstance(raw, bool)
            and isinstance(raw, (int, float))
            and math.isfinite(float(raw)),
            f"calibrated joint {feedback_name} is not finite",
        )
        result[arm_name] = float(raw)
    return result


def admit_fused_camera_state_route_entry(
    *,
    snapshot_read_receipt_document: Mapping[str, Any],
    fusion_receipt_document: Mapping[str, Any],
    planning_receipt_document: Mapping[str, Any],
    route_qualification_admission_document: Mapping[str, Any],
    route_bound_entry_qualification_document: Mapping[str, Any],
    observed_route_entry_document: Mapping[str, Any],
    current_attachment_profile: str,
    consumed_at: str,
) -> dict[str, Any]:
    """Admit a fresh fused state only to its exact qualified route entry."""

    snapshot = _mapping(snapshot_read_receipt_document, "snapshot read receipt")
    fusion = _mapping(fusion_receipt_document, "fusion receipt")
    planning = _mapping(planning_receipt_document, "planning receipt")
    route = _sealed_route_admission(route_qualification_admission_document)
    try:
        entry_qualification = parse_fixed_camera_keyboard_route_bound_entry_v1(
            route_bound_entry_qualification_document
        )
        observed_entry = parse_typing_observed_route_entry_v1(
            observed_route_entry_document
        )
    except (
        FixedCameraKeyboardRouteBoundEntryQualificationV1Error,
        TypingObservedRouteEntryV1Error,
    ) as exc:
        raise FusedCameraStateRouteEntryAdmissionError(str(exc)) from exc

    _require(
        snapshot.get("schema") == SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA
        and snapshot.get("status") == "CALIBRATED_STATE_SNAPSHOT_READ_ADMITTED"
        and snapshot.get("calibrated_state_snapshot_read_admitted") is True
        and snapshot.get("named_reader_snapshot_use_authorized") is True
        and snapshot.get("automatic_retry_allowed") is False
        and snapshot.get("motion_authorized") is False
        and snapshot.get("physical_authority") is False,
        "snapshot read receipt is not eligible and zero-authority",
    )
    _require(
        fusion.get("schema") == FUSION_ADMISSION_RECEIPT_SCHEMA
        and fusion.get("status") == "CAMERA_FEEDBACK_STATE_FUSION_ADMITTED"
        and fusion.get("camera_feedback_state_fusion_admitted") is True
        and fusion.get("planning_authorized") is False
        and fusion.get("automatic_retry_allowed") is False
        and fusion.get("motion_authorized") is False
        and fusion.get("contact_authorized") is False
        and fusion.get("physical_authority") is False,
        "fusion receipt is not eligible and zero-authority",
    )
    _require(
        planning.get("schema") == PLANNING_ADMISSION_RECEIPT_SCHEMA
        and planning.get("status") == "FUSED_CAMERA_STATE_PLANNING_ADMITTED"
        and planning.get("fused_camera_state_planning_admitted") is True
        and planning.get("plan_candidate_emitted") is True
        and planning.get("automatic_retry_allowed") is False
        and planning.get("motion_authorized") is False
        and planning.get("contact_authorized") is False
        and planning.get("physical_authority") is False,
        "planning receipt is not eligible and zero-authority",
    )

    snapshot_sha = canonical_sha256(snapshot)
    fusion_sha = canonical_sha256(fusion)
    planning_sha = canonical_sha256(planning)
    _require(
        fusion.get("snapshot_read_receipt_sha256") == snapshot_sha
        and fusion.get("snapshot_id") == snapshot.get("snapshot_id")
        and planning.get("fusion_receipt_sha256") == fusion_sha
        and route.get("planning_receipt_sha256") == planning_sha
        and route.get("planning_admission_id") == planning.get("planning_admission_id"),
        "snapshot, fusion, planning, or route admission lineage differs",
    )
    _require(
        snapshot.get("calibrated_feedback") == fusion.get("calibrated_feedback")
        == planning.get("calibrated_feedback"),
        "calibrated feedback differs across snapshot, fusion, and planning",
    )
    _require(
        current_attachment_profile in {"no_attachment", "stylus_attachment"}
        and snapshot.get("attachment_profile") == current_attachment_profile
        and fusion.get("attachment_profile") == current_attachment_profile
        and planning.get("attachment_profile") == current_attachment_profile
        and route.get("attachment_profile") == current_attachment_profile
        and entry_qualification.get("active_profile") == current_attachment_profile,
        "active attachment profile differs across route-entry inputs",
    )

    consumed = _timestamp(consumed_at, "consumed_at")
    snapshot_valid = _timestamp(snapshot.get("valid_until"), "snapshot valid_until")
    fusion_valid = _timestamp(fusion.get("valid_until"), "fusion valid_until")
    planning_valid = _timestamp(planning.get("valid_until"), "planning valid_until")
    route_consumed = _timestamp(route.get("consumed_at"), "route consumed_at")
    _require(
        route_consumed <= consumed <= snapshot_valid
        and consumed <= fusion_valid
        and consumed <= planning_valid,
        "camera/state route-entry evidence is stale or consumed out of order",
    )

    _require(
        entry_qualification.get("schema") == ENTRY_QUALIFICATION_SCHEMA
        and entry_qualification.get("status") == ENTRY_QUALIFICATION_PASS
        and entry_qualification.get("disposition") == "PASS"
        and entry_qualification.get("blockers") == []
        and entry_qualification.get("authority") == dict(ENTRY_ZERO_AUTHORITY),
        "route-bound entry qualification is not a zero-authority PASS",
    )
    _require(
        entry_qualification.get("route_bound_collision_qualification_sha256")
        == route.get("route_bound_collision_qualification_sha256")
        and entry_qualification.get("route_envelope_binding_sha256")
        == route.get("route_envelope_binding_sha256")
        and entry_qualification.get("installed_collision_profile_sha256")
        == route.get("installed_collision_profile_sha256")
        and entry_qualification.get("observed_route_entry_sha256")
        == observed_entry.get("observed_route_entry_sha256"),
        "qualified route and observed entry lineage differs",
    )
    _require(
        snapshot.get("runtime_session_id")
        == observed_entry.get("controller_session_id"),
        "observed entry belongs to a different controller runtime session",
    )
    calibrated_joints = _calibrated_arm_joints(snapshot.get("calibrated_feedback"))
    _require(
        observed_entry.get("start_joint_positions_rad") == calibrated_joints,
        "observed entry start joints differ from calibrated camera/state feedback",
    )

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "snapshot_read_receipt_sha256": snapshot_sha,
        "fusion_receipt_sha256": fusion_sha,
        "planning_receipt_sha256": planning_sha,
        "route_qualification_admission_sha256": route[
            "route_qualification_admission_sha256"
        ],
        "route_bound_entry_qualification_sha256": entry_qualification[
            "route_bound_entry_qualification_sha256"
        ],
        "observed_route_entry_sha256": observed_entry[
            "observed_route_entry_sha256"
        ],
        "attachment_profile": current_attachment_profile,
        "target_key_id": route["target_key_id"],
        "runtime_session_id": snapshot["runtime_session_id"],
        "calibrated_start_joint_positions_rad": calibrated_joints,
        "route_envelope_binding_sha256": route["route_envelope_binding_sha256"],
        "installed_collision_profile_sha256": route[
            "installed_collision_profile_sha256"
        ],
        "consumed_at": consumed_at,
        "fresh_state_lineage_verified": True,
        "calibrated_start_matches_observed_entry": True,
        "profile_separation_preserved": True,
        "next_required_gate": NEXT_REQUIRED_GATE,
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "route_entry_admission_sha256": _sha(core)}


__all__ = [
    "NEXT_REQUIRED_GATE",
    "SCHEMA",
    "STATUS",
    "ZERO_AUTHORITY",
    "FusedCameraStateRouteEntryAdmissionError",
    "admit_fused_camera_state_route_entry",
]
