"""Admit one fused, route-qualified action to independent execution review.

The camera/state pipeline ends with a fresh observed entry for an exact route.
The physical review pipeline begins with one exact action, a current operator,
and an independent observer prepared to verify that action's effect.  This
adapter joins those boundaries without creating a review, permit, command, or
hardware access.

Every input is content addressed.  The selected action must belong to the
camera-selected target, the route-entry receipt must still be fresh, the
operator confirmation is short lived, and the verifier and per-action policy
must agree on the exact expected effect.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import re
from typing import Any, Mapping

from .fixed_camera_keyboard_route_bound_entry_qualification_v1 import (
    STATUS_PASS as ENTRY_PASS,
    ZERO_AUTHORITY as ENTRY_ZERO_AUTHORITY,
    FixedCameraKeyboardRouteBoundEntryQualificationV1Error,
    parse_fixed_camera_keyboard_route_bound_entry_v1,
)
from .fused_camera_state_route_entry_admission import (
    SCHEMA as ROUTE_ENTRY_SCHEMA,
    STATUS as ROUTE_ENTRY_STATUS,
    ZERO_AUTHORITY as ROUTE_ENTRY_ZERO_AUTHORITY,
)
from .fused_camera_state_route_qualification_admission import (
    SCHEMA as ROUTE_SCHEMA,
    STATUS as ROUTE_STATUS,
    ZERO_AUTHORITY as ROUTE_ZERO_AUTHORITY,
)


SCHEMA = "rocell.fused_camera_state_action_review_admission.v1"
STATUS = "FUSED_CAMERA_STATE_ACTION_REVIEW_ADMITTED_ZERO_AUTHORITY"
EFFECT_VERIFIER_SCHEMA = "rocell.independent_action_effect_verifier_binding.v1"
EFFECT_VERIFIER_STATUS = "INDEPENDENT_EFFECT_VERIFIER_READY_FOR_ONE_ACTION"
OPERATOR_CONFIRMATION_SCHEMA = "rocell.current_operator_action_confirmation.v1"
OPERATOR_CONFIRMATION_STATUS = "CURRENT_OPERATOR_CONFIRMED_FOR_ONE_ACTION_REVIEW"
ACTION_POLICY_SCHEMA = "rocell.fused_route_action_review_policy.v1"
ACTION_POLICY_STATUS = "PER_ACTION_EXECUTION_REVIEW_REQUIRED"
NEXT_REQUIRED_GATE = "SINGLE_ACTION_EXECUTION_REVIEW_V1"
MAX_ROUTE_ENTRY_AGE_SECONDS = 5
MAX_OPERATOR_CONFIRMATION_LIFETIME_SECONDS = 30
MAX_EFFECT_VERIFIER_LIFETIME_SECONDS = 300
ZERO_AUTHORITY: Mapping[str, object] = {
    "exact_action_selected": True,
    "current_operator_confirmation_verified": True,
    "independent_effect_verifier_bound": True,
    "single_action_execution_review_created": False,
    "permit_issued": False,
    "controller_commands": [],
    "wire_commands": [],
    "hardware_commands_generated": 0,
    "hardware_writes": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COMMON_ACTION_FIELDS = {
    "route_entry_admission_sha256",
    "route_qualification_admission_sha256",
    "target_key_id",
    "action_index",
    "attachment_profile",
}
_EFFECT_VERIFIER_FIELDS = _COMMON_ACTION_FIELDS | {
    "schema",
    "status",
    "verifier_id",
    "observer_context_sha256",
    "expected_effect_sha256",
    "evidence_origin",
    "review_disposition",
    "independent_from_motion_writer",
    "configured_at",
    "valid_until",
    "maximum_observation_latency_ms",
    "automatic_retry_allowed",
    "controller_commands",
    "hardware_access",
    "physical_authority",
    "effect_verifier_binding_sha256",
}
_OPERATOR_FIELDS = _COMMON_ACTION_FIELDS | {
    "schema",
    "status",
    "operator_id",
    "runtime_session_id",
    "confirmed_at",
    "valid_until",
    "operator_present",
    "shutdown_reachable",
    "area_clear",
    "arm_secured_and_stationary",
    "automatic_retry_allowed",
    "motion_authorized",
    "physical_authority",
    "operator_confirmation_sha256",
}
_ACTION_POLICY_FIELDS = _COMMON_ACTION_FIELDS | {
    "schema",
    "status",
    "policy_id",
    "interaction",
    "expected_effect_sha256",
    "effect_verifier_binding_sha256",
    "per_action_review_required",
    "single_use_required",
    "automatic_retry_allowed",
    "review_issued",
    "permit_issued",
    "controller_commands",
    "hardware_access",
    "physical_authority",
    "action_review_policy_sha256",
}


class FusedCameraStateActionReviewAdmissionError(ValueError):
    """The route, action, operator, verifier, or review policy differs."""


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
        raise FusedCameraStateActionReviewAdmissionError(
            "action-review admission is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FusedCameraStateActionReviewAdmissionError(message)


def _mapping(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return dict(value)  # type: ignore[arg-type]


def _digest(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _SHA.fullmatch(value) is not None,
        f"{label} must be a lowercase SHA-256 digest",
    )
    return value


def _identifier(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None,
        f"{label} must be a bounded identifier",
    )
    return value


def _timestamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be an ISO-8601 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FusedCameraStateActionReviewAdmissionError(
            f"{label} must be an ISO-8601 timestamp"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _sealed(value: object, hash_field: str, label: str) -> dict[str, Any]:
    document = _mapping(value, label)
    unsigned = dict(document)
    supplied = unsigned.pop(hash_field, None)
    _require(
        isinstance(supplied, str) and supplied == _sha(unsigned),
        f"{label} hash differs",
    )
    return document


def _route_entry(value: object) -> dict[str, Any]:
    document = _sealed(value, "route_entry_admission_sha256", "route-entry admission")
    _require(
        document.get("schema") == ROUTE_ENTRY_SCHEMA
        and document.get("status") == ROUTE_ENTRY_STATUS
        and document.get("fresh_state_lineage_verified") is True
        and document.get("calibrated_start_matches_observed_entry") is True
        and document.get("profile_separation_preserved") is True
        and document.get("next_required_gate") == "INDEPENDENT_EXECUTION_RELEASE_GATES"
        and document.get("authority") == dict(ROUTE_ENTRY_ZERO_AUTHORITY),
        "route-entry admission is not eligible and zero-authority",
    )
    return document


def _route(value: object) -> dict[str, Any]:
    document = _sealed(
        value, "route_qualification_admission_sha256", "route qualification admission"
    )
    action_indices = document.get("target_action_indices")
    _require(
        document.get("schema") == ROUTE_SCHEMA
        and document.get("status") == ROUTE_STATUS
        and document.get("exact_target_route_binding_verified") is True
        and document.get("profile_separation_preserved") is True
        and document.get("next_required_gate")
        == "ROUTE_BOUND_FRESH_OBSERVED_ENTRY_QUALIFICATION"
        and document.get("authority") == dict(ROUTE_ZERO_AUTHORITY)
        and isinstance(action_indices, list)
        and bool(action_indices)
        and all(type(index) is int and index >= 0 for index in action_indices)
        and len(action_indices) == len(set(action_indices)),
        "route qualification admission is not eligible and zero-authority",
    )
    return document


def _effect_verifier(value: object, consumed: datetime) -> dict[str, Any]:
    document = _sealed(
        value, "effect_verifier_binding_sha256", "effect verifier binding"
    )
    configured = _timestamp(document.get("configured_at"), "verifier configured_at")
    valid_until = _timestamp(document.get("valid_until"), "verifier valid_until")
    latency = document.get("maximum_observation_latency_ms")
    _require(
        set(document) == _EFFECT_VERIFIER_FIELDS
        and document.get("schema") == EFFECT_VERIFIER_SCHEMA
        and document.get("status") == EFFECT_VERIFIER_STATUS
        and _identifier(document.get("verifier_id"), "verifier_id")
        and _digest(document.get("observer_context_sha256"), "observer_context_sha256")
        and _digest(document.get("expected_effect_sha256"), "expected_effect_sha256")
        and document.get("evidence_origin") == "PHYSICAL_RETAINED_ORIGINALS"
        and document.get("review_disposition") == "INDEPENDENTLY_APPROVED"
        and document.get("independent_from_motion_writer") is True
        and type(latency) is int
        and 1 <= latency <= 5_000
        and configured <= consumed <= valid_until
        and valid_until
        <= configured + timedelta(seconds=MAX_EFFECT_VERIFIER_LIFETIME_SECONDS)
        and document.get("automatic_retry_allowed") is False
        and document.get("controller_commands") == []
        and document.get("hardware_access") is False
        and document.get("physical_authority") is False,
        "effect verifier is not fresh, independent, approved, and zero-authority",
    )
    return document


def _operator_confirmation(value: object, consumed: datetime) -> dict[str, Any]:
    document = _sealed(
        value, "operator_confirmation_sha256", "operator confirmation"
    )
    confirmed = _timestamp(document.get("confirmed_at"), "operator confirmed_at")
    valid_until = _timestamp(document.get("valid_until"), "operator valid_until")
    _require(
        set(document) == _OPERATOR_FIELDS
        and document.get("schema") == OPERATOR_CONFIRMATION_SCHEMA
        and document.get("status") == OPERATOR_CONFIRMATION_STATUS
        and _identifier(document.get("operator_id"), "operator_id")
        and confirmed <= consumed <= valid_until
        and valid_until
        <= confirmed
        + timedelta(seconds=MAX_OPERATOR_CONFIRMATION_LIFETIME_SECONDS)
        and document.get("operator_present") is True
        and document.get("shutdown_reachable") is True
        and document.get("area_clear") is True
        and document.get("arm_secured_and_stationary") is True
        and document.get("automatic_retry_allowed") is False
        and document.get("motion_authorized") is False
        and document.get("physical_authority") is False,
        "operator confirmation is not current, complete, and zero-authority",
    )
    return document


def _action_policy(value: object) -> dict[str, Any]:
    document = _sealed(value, "action_review_policy_sha256", "action review policy")
    _require(
        set(document) == _ACTION_POLICY_FIELDS
        and document.get("schema") == ACTION_POLICY_SCHEMA
        and document.get("status") == ACTION_POLICY_STATUS
        and _identifier(document.get("policy_id"), "policy_id")
        and document.get("interaction") in {"HOVER", "CONTACT"}
        and document.get("per_action_review_required") is True
        and document.get("single_use_required") is True
        and document.get("automatic_retry_allowed") is False
        and document.get("review_issued") is False
        and document.get("permit_issued") is False
        and document.get("controller_commands") == []
        and document.get("hardware_access") is False
        and document.get("physical_authority") is False,
        "per-action review policy is not eligible and zero-authority",
    )
    return document


def admit_fused_camera_state_action_review(
    *,
    route_entry_admission_document: Mapping[str, Any],
    route_qualification_admission_document: Mapping[str, Any],
    route_bound_entry_qualification_document: Mapping[str, Any],
    effect_verifier_binding_document: Mapping[str, Any],
    operator_confirmation_document: Mapping[str, Any],
    action_review_policy_document: Mapping[str, Any],
    selected_action_index: int,
    consumed_at: str,
) -> dict[str, Any]:
    """Admit one fresh, observable action to the existing review boundary."""

    _require(
        type(selected_action_index) is int and selected_action_index >= 0,
        "selected_action_index must be a nonnegative integer",
    )
    consumed = _timestamp(consumed_at, "consumed_at")
    route_entry = _route_entry(route_entry_admission_document)
    route = _route(route_qualification_admission_document)
    try:
        entry = parse_fixed_camera_keyboard_route_bound_entry_v1(
            route_bound_entry_qualification_document
        )
    except (TypeError, FixedCameraKeyboardRouteBoundEntryQualificationV1Error) as exc:
        raise FusedCameraStateActionReviewAdmissionError(str(exc)) from exc
    verifier = _effect_verifier(effect_verifier_binding_document, consumed)
    operator = _operator_confirmation(operator_confirmation_document, consumed)
    policy = _action_policy(action_review_policy_document)

    route_entry_hash = route_entry["route_entry_admission_sha256"]
    route_hash = route["route_qualification_admission_sha256"]
    entry_hash = entry["route_bound_entry_qualification_sha256"]
    verifier_hash = verifier["effect_verifier_binding_sha256"]
    expected_effect = _digest(policy.get("expected_effect_sha256"), "expected_effect_sha256")

    _require(
        route_entry.get("route_qualification_admission_sha256") == route_hash
        and route_entry.get("route_bound_entry_qualification_sha256") == entry_hash
        and route_entry.get("target_key_id") == route.get("target_key_id")
        and route_entry.get("route_envelope_binding_sha256")
        == route.get("route_envelope_binding_sha256")
        and route_entry.get("installed_collision_profile_sha256")
        == route.get("installed_collision_profile_sha256"),
        "route-entry and exact-route lineage differs",
    )
    _require(
        entry.get("status") == ENTRY_PASS
        and entry.get("disposition") == "PASS"
        and entry.get("blockers") == []
        and entry.get("authority") == dict(ENTRY_ZERO_AUTHORITY)
        and entry.get("route_bound_collision_qualification_sha256")
        == route.get("route_bound_collision_qualification_sha256"),
        "route-bound entry qualification is not a zero-authority PASS",
    )
    nested = _mapping(
        entry.get("profiled_entry_route_qualification"),
        "profiled entry-route qualification",
    )
    _require(
        nested.get("retained_entry_telemetry_coverage_qualified") is True
        and nested.get("selected_profile_route_continuously_clear") is True
        and nested.get("observed_entry_continuously_clear") is True
        and nested.get("entry_route_joint_continuity_proven") is True,
        "entry dynamics, coverage, continuity, or collision evidence is incomplete",
    )
    route_entry_time = _timestamp(route_entry.get("consumed_at"), "route entry consumed_at")
    valid_until = min(
        route_entry_time + timedelta(seconds=MAX_ROUTE_ENTRY_AGE_SECONDS),
        _timestamp(operator.get("valid_until"), "operator valid_until"),
        _timestamp(verifier.get("valid_until"), "verifier valid_until"),
    )
    _require(
        route_entry_time <= consumed
        <= route_entry_time + timedelta(seconds=MAX_ROUTE_ENTRY_AGE_SECONDS),
        "route-entry admission is stale at action-review admission",
    )
    _require(
        selected_action_index in route["target_action_indices"],
        "selected action does not belong to the camera-selected target route",
    )

    shared = {
        "route_entry_admission_sha256": route_entry_hash,
        "route_qualification_admission_sha256": route_hash,
        "target_key_id": route["target_key_id"],
        "action_index": selected_action_index,
        "attachment_profile": route_entry["attachment_profile"],
    }
    for document, label in (
        (verifier, "effect verifier"),
        (operator, "operator confirmation"),
        (policy, "action review policy"),
    ):
        _require(
            all(document.get(field) == value for field, value in shared.items()),
            f"{label} differs from the selected route action",
        )
    _require(
        operator.get("runtime_session_id") == route_entry.get("runtime_session_id"),
        "operator confirmation belongs to a different runtime session",
    )
    _require(
        policy.get("effect_verifier_binding_sha256") == verifier_hash
        and verifier.get("expected_effect_sha256") == expected_effect,
        "per-action policy and effect verifier binding differ",
    )

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "route_entry_admission_sha256": route_entry_hash,
        "route_qualification_admission_sha256": route_hash,
        "route_bound_entry_qualification_sha256": entry_hash,
        "action_review_policy_sha256": policy["action_review_policy_sha256"],
        "operator_confirmation_sha256": operator["operator_confirmation_sha256"],
        "effect_verifier_binding_sha256": verifier_hash,
        "target_key_id": route["target_key_id"],
        "action_index": selected_action_index,
        "interaction": policy["interaction"],
        "expected_effect_sha256": expected_effect,
        "attachment_profile": route_entry["attachment_profile"],
        "runtime_session_id": route_entry["runtime_session_id"],
        "route_envelope_binding_sha256": route["route_envelope_binding_sha256"],
        "installed_collision_profile_sha256": route[
            "installed_collision_profile_sha256"
        ],
        "observed_route_entry_coverage_sha256": entry[
            "observed_route_entry_coverage_sha256"
        ],
        "consumed_at": consumed_at,
        "valid_until": valid_until.isoformat(),
        "fresh_route_entry_verified": True,
        "entry_dynamics_and_coverage_verified": True,
        "current_operator_verified": True,
        "independent_effect_verifier_verified": True,
        "per_action_policy_verified": True,
        "next_required_gate": NEXT_REQUIRED_GATE,
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "action_review_admission_sha256": _sha(core)}


__all__ = [
    "ACTION_POLICY_SCHEMA",
    "ACTION_POLICY_STATUS",
    "EFFECT_VERIFIER_SCHEMA",
    "EFFECT_VERIFIER_STATUS",
    "MAX_EFFECT_VERIFIER_LIFETIME_SECONDS",
    "MAX_OPERATOR_CONFIRMATION_LIFETIME_SECONDS",
    "MAX_ROUTE_ENTRY_AGE_SECONDS",
    "NEXT_REQUIRED_GATE",
    "OPERATOR_CONFIRMATION_SCHEMA",
    "OPERATOR_CONFIRMATION_STATUS",
    "SCHEMA",
    "STATUS",
    "ZERO_AUTHORITY",
    "FusedCameraStateActionReviewAdmissionError",
    "admit_fused_camera_state_action_review",
]
