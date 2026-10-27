"""Create one execution review from an exact fused camera/state admission.

This is the zero-authority join between the camera-selected action pipeline and
``single_action_execution_review_v1``.  It authenticates the sealed admission,
checks the semantic fields shared by both pipelines, bounds the review lifetime
by the admission's earliest upstream expiry, and delegates every controller,
collision, contact-envelope, T102, configuration, and trajectory check to the
existing review builder.

The result remains a single-use review candidate.  It does not consume the
review, issue a permit, encode wire bytes, open hardware, or move the arm.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping

from rocell.models import ModelMotionBatchV2, ModelMotionProposalV2

from .fused_camera_state_action_review_admission import (
    NEXT_REQUIRED_GATE,
    SCHEMA as ACTION_ADMISSION_SCHEMA,
    STATUS as ACTION_ADMISSION_STATUS,
    ZERO_AUTHORITY as ACTION_ADMISSION_ZERO_AUTHORITY,
)
from .installed_controller_qualification_v1 import (
    InstalledControllerQualificationEvidenceV1,
    InstalledControllerQualificationReportV1,
)
from .single_action_execution_review_v1 import (
    InstalledCollisionPolicyQualificationV1,
    InstalledT102CommandProfileV1,
    SingleActionExecutionReviewV1,
    build_single_action_execution_review_v1,
)
from .trajectory_execution_envelope_v2 import TrajectoryExecutionEnvelopeV2


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ADMISSION_FIELDS = {
    "schema",
    "status",
    "route_entry_admission_sha256",
    "route_qualification_admission_sha256",
    "route_bound_entry_qualification_sha256",
    "action_review_policy_sha256",
    "operator_confirmation_sha256",
    "effect_verifier_binding_sha256",
    "target_key_id",
    "action_index",
    "interaction",
    "expected_effect_sha256",
    "attachment_profile",
    "runtime_session_id",
    "route_envelope_binding_sha256",
    "installed_collision_profile_sha256",
    "observed_route_entry_coverage_sha256",
    "consumed_at",
    "valid_until",
    "fresh_route_entry_verified",
    "entry_dynamics_and_coverage_verified",
    "current_operator_verified",
    "independent_effect_verifier_verified",
    "per_action_policy_verified",
    "next_required_gate",
    "authority",
    "action_review_admission_sha256",
}
_DIGEST_FIELDS = {
    "route_entry_admission_sha256",
    "route_qualification_admission_sha256",
    "route_bound_entry_qualification_sha256",
    "action_review_policy_sha256",
    "operator_confirmation_sha256",
    "effect_verifier_binding_sha256",
    "expected_effect_sha256",
    "route_envelope_binding_sha256",
    "installed_collision_profile_sha256",
    "observed_route_entry_coverage_sha256",
}


class FusedCameraStateSingleActionExecutionReviewError(ValueError):
    """The fused admission is malformed, stale, crossed, or authority-bearing."""


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
        raise FusedCameraStateSingleActionExecutionReviewError(
            "fused action review value is not canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FusedCameraStateSingleActionExecutionReviewError(message)


def _timestamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be an ISO-8601 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FusedCameraStateSingleActionExecutionReviewError(
            f"{label} must be an ISO-8601 timestamp"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _sealed_admission(value: object) -> dict[str, Any]:
    _require(isinstance(value, Mapping), "action-review admission must be an object")
    document = dict(value)  # type: ignore[arg-type]
    _require(
        set(document) == _ADMISSION_FIELDS,
        "action-review admission fields differ",
    )
    supplied = document.get("action_review_admission_sha256")
    unsigned = dict(document)
    unsigned.pop("action_review_admission_sha256")
    _require(
        isinstance(supplied, str)
        and _SHA256.fullmatch(supplied) is not None
        and supplied == _sha256(unsigned),
        "action-review admission hash differs",
    )
    _require(
        all(
            isinstance(document.get(field), str)
            and _SHA256.fullmatch(document[field]) is not None
            for field in _DIGEST_FIELDS
        ),
        "action-review admission contains an invalid digest",
    )
    _require(
        document.get("schema") == ACTION_ADMISSION_SCHEMA
        and document.get("status") == ACTION_ADMISSION_STATUS
        and document.get("next_required_gate") == NEXT_REQUIRED_GATE
        and document.get("fresh_route_entry_verified") is True
        and document.get("entry_dynamics_and_coverage_verified") is True
        and document.get("current_operator_verified") is True
        and document.get("independent_effect_verifier_verified") is True
        and document.get("per_action_policy_verified") is True
        and document.get("authority") == dict(ACTION_ADMISSION_ZERO_AUTHORITY),
        "action-review admission is not eligible and zero-authority",
    )
    return document


def _timedelta_ns(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    return (
        delta.days * 86_400_000_000_000
        + delta.seconds * 1_000_000_000
        + delta.microseconds * 1_000
    )


def build_fused_camera_state_single_action_execution_review_v1(
    action_review_admission_document: Mapping[str, Any],
    batch: ModelMotionBatchV2,
    proposal: ModelMotionProposalV2,
    envelope: TrajectoryExecutionEnvelopeV2,
    contact_gate_report: Mapping[str, Any],
    collision_qualification: InstalledCollisionPolicyQualificationV1,
    controller_evidence: InstalledControllerQualificationEvidenceV1,
    controller_qualification: InstalledControllerQualificationReportV1,
    t102_profile: InstalledT102CommandProfileV1,
    *,
    review_id: str,
    reviewed_at: str,
    issued_monotonic_ns: int,
    deadline_monotonic_ns: int,
) -> SingleActionExecutionReviewV1:
    """Bind one fresh fused action admission into the existing review gate."""

    admission = _sealed_admission(action_review_admission_document)
    reviewed = _timestamp(reviewed_at, "reviewed_at")
    consumed = _timestamp(admission.get("consumed_at"), "admission consumed_at")
    valid_until = _timestamp(admission.get("valid_until"), "admission valid_until")
    _require(
        consumed <= reviewed <= valid_until,
        "action-review admission is unavailable or stale",
    )
    _require(
        type(issued_monotonic_ns) is int
        and type(deadline_monotonic_ns) is int
        and issued_monotonic_ns > 0
        and deadline_monotonic_ns > issued_monotonic_ns,
        "execution review monotonic lifetime is invalid",
    )
    _require(
        deadline_monotonic_ns - issued_monotonic_ns
        <= _timedelta_ns(valid_until, reviewed),
        "execution review outlives the fused action admission",
    )
    _require(
        isinstance(batch, ModelMotionBatchV2)
        and isinstance(proposal, ModelMotionProposalV2)
        and isinstance(envelope, TrajectoryExecutionEnvelopeV2)
        and isinstance(contact_gate_report, Mapping)
        and isinstance(
            collision_qualification, InstalledCollisionPolicyQualificationV1
        ),
        "model action and trajectory inputs have the wrong type",
    )
    _require(
        proposal.device.value == "keyboard"
        and admission.get("target_key_id") == proposal.target_id
        and admission.get("action_index") == proposal.action_index
        and admission.get("interaction") == proposal.interaction.value,
        "fused admission differs from the selected model action",
    )
    _require(
        admission.get("runtime_session_id")
        == envelope.measured_envelope.controller_session_id,
        "fused admission differs from the execution controller session",
    )
    _require(
        admission.get("installed_collision_profile_sha256")
        == collision_qualification.installed_collision_profile_sha256
        == contact_gate_report.get("installed_collision_profile_sha256"),
        "fused admission differs from the installed collision profile",
    )

    return build_single_action_execution_review_v1(
        batch,
        proposal,
        envelope,
        contact_gate_report,
        collision_qualification,
        controller_evidence,
        controller_qualification,
        t102_profile,
        review_id=review_id,
        issued_monotonic_ns=issued_monotonic_ns,
        deadline_monotonic_ns=deadline_monotonic_ns,
        fused_camera_state_action_review_admission_sha256=admission[
            "action_review_admission_sha256"
        ],
    )


__all__ = [
    "FusedCameraStateSingleActionExecutionReviewError",
    "build_fused_camera_state_single_action_execution_review_v1",
]
