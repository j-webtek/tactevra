"""Admit one reviewed calibrated observation to one named state consumer.

This file-only gate binds an accepted independent review back to the original
execution time and current configuration.  It grants a short, explicit state
observation use window to one consumer.  It opens no hardware and grants no
motion, connection, contact, retry, or physical authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any, Mapping

from rocell.calibration.position_vector_campaign import canonical_sha256

from .calibrated_position_vector_execution_review import REVIEW_RECEIPT_SCHEMA
from .calibrated_position_vector_feedback_execution import EXECUTION_RECEIPT_SCHEMA


ADMISSION_SCHEMA = "rocell.calibrated_position_vector_observation_admission.v1"
ADMISSION_RECEIPT_SCHEMA = (
    "rocell.calibrated_position_vector_observation_admission_receipt.v1"
)
MAX_OBSERVATION_AGE_SECONDS = 300
MAX_ADMISSION_LIFETIME_SECONDS = 60

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile", "controller_binding_sha256", "request_contract",
        "request_contract_sha256", "request_execution_approval_receipt_sha256",
        "execution_prerequisites_sha256", "exchange_evidence_sha256",
        "response_line_sha256", "response_message", "calibrated_feedback",
        "operator_id", "confirmed_at", "executed_at", "next_required_gate",
        "limitations", "authority", "calibrated_feedback_request_executed",
        "calibrated_feedback_conversion_accepted", "motion_authorized",
        "physical_authority",
    }
)
_REVIEW_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile", "execution_receipt_sha256",
        "application_claim_sha256", "supervisor_request_sha256",
        "supervisor_result_sha256", "journal_manifest_sha256",
        "calibration_sha256", "review_sha256", "reviewer_id", "reviewed_at",
        "decision", "calibrated_feedback", "next_required_gate", "limitations",
        "calibrated_feedback_observation_accepted", "automatic_retry_allowed",
        "motion_authorized", "physical_authority",
    }
)
_ADMISSION_FIELDS = frozenset(
    {
        "schema", "consumer_id", "consumer_context_sha256", "admitted_at",
        "valid_until", "review_receipt_sha256", "execution_receipt_sha256",
        "calibration_sha256", "controller_binding_sha256", "attempt_id",
        "runtime_session_id", "calibration_id", "attachment_profile",
        "freshness_policy",
    }
)
_FRESHNESS_FIELDS = frozenset(
    {"maximum_observation_age_seconds", "maximum_admission_lifetime_seconds"}
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile", "consumer_id", "consumer_context_sha256",
        "executed_at", "reviewed_at", "admitted_at", "valid_until",
        "execution_receipt_sha256", "review_receipt_sha256",
        "calibration_sha256", "controller_binding_sha256", "admission_sha256",
        "freshness_policy", "calibrated_feedback", "next_required_gate",
        "limitations", "calibrated_feedback_observation_admitted",
        "named_consumer_state_use_authorized", "automatic_retry_allowed",
        "motion_authorized", "physical_authority",
    }
)


class CalibratedPositionVectorObservationAdmissionError(ValueError):
    """The reviewed observation is not eligible for state admission."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibratedPositionVectorObservationAdmissionError(message)


def _mapping(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return dict(value)  # type: ignore[arg-type]


def _exact(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    _require(set(value) == fields, f"{label} fields do not match the contract")


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
        raise CalibratedPositionVectorObservationAdmissionError(
            f"{label} is invalid"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _positive_bounded_seconds(value: object, maximum: int, label: str) -> int:
    _require(
        type(value) is int and 0 < value <= maximum,
        f"{label} must be between 1 and {maximum} seconds",
    )
    return value


def admit_calibrated_position_vector_observation(
    *,
    execution_receipt_document: Mapping[str, Any],
    review_receipt_document: Mapping[str, Any],
    admission_document: Mapping[str, Any],
    consumer_context_document: Mapping[str, Any],
    current_calibration_document: Mapping[str, Any],
    current_controller_binding_document: Mapping[str, Any],
    current_attachment_profile: str,
) -> dict[str, Any]:
    """Issue a bounded state-use receipt for one exact reviewed observation."""

    execution = _mapping(execution_receipt_document, "execution receipt")
    review = _mapping(review_receipt_document, "review receipt")
    admission = _mapping(admission_document, "admission")
    consumer_context = _mapping(consumer_context_document, "consumer context")
    current_calibration = _mapping(
        current_calibration_document, "current calibration"
    )
    current_controller_binding = _mapping(
        current_controller_binding_document, "current controller binding"
    )
    _exact(execution, _EXECUTION_RECEIPT_FIELDS, "execution receipt")
    _exact(review, _REVIEW_RECEIPT_FIELDS, "review receipt")
    _exact(admission, _ADMISSION_FIELDS, "admission")

    _require(
        execution["schema"] == EXECUTION_RECEIPT_SCHEMA
        and execution["status"]
        == "QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTED"
        and execution["calibrated_feedback_request_executed"] is True
        and execution["calibrated_feedback_conversion_accepted"] is True,
        "execution receipt is not state-admission eligible",
    )
    _require(
        review["schema"] == REVIEW_RECEIPT_SCHEMA
        and review["status"]
        == "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_ACCEPTED"
        and review["decision"] == "ACCEPT"
        and review["calibrated_feedback_observation_accepted"] is True
        and review["next_required_gate"]
        == "CALIBRATED_POSITION_VECTOR_OBSERVATION_STATE_ADMISSION",
        "review receipt is not accepted for state admission",
    )
    _require(
        execution["motion_authorized"] is False
        and execution["physical_authority"] is False
        and review["automatic_retry_allowed"] is False
        and review["motion_authorized"] is False
        and review["physical_authority"] is False,
        "source receipt authority is invalid",
    )

    execution_sha = canonical_sha256(execution)
    review_sha = canonical_sha256(review)
    consumer_context_sha = canonical_sha256(consumer_context)
    current_calibration_sha = canonical_sha256(current_calibration)
    current_controller_binding_sha = canonical_sha256(current_controller_binding)
    _identifier(current_attachment_profile, "current_attachment_profile")
    for field, expected in (
        ("execution_receipt_sha256", execution_sha),
        ("review_receipt_sha256", review_sha),
        ("consumer_context_sha256", consumer_context_sha),
        ("calibration_sha256", current_calibration_sha),
        ("controller_binding_sha256", current_controller_binding_sha),
        ("attempt_id", execution["attempt_id"]),
        ("runtime_session_id", execution["runtime_session_id"]),
        ("calibration_id", execution["calibration_id"]),
        ("attachment_profile", current_attachment_profile),
    ):
        _require(admission[field] == expected, f"admission binding mismatch: {field}")

    _require(
        review["execution_receipt_sha256"] == execution_sha,
        "review receipt is crossed with a different execution receipt",
    )
    _require(
        review["calibration_sha256"] == current_calibration_sha
        and execution["controller_binding_sha256"]
        == current_controller_binding_sha
        and execution["attachment_profile"] == current_attachment_profile,
        "current calibration, controller, or attachment differs from execution",
    )
    for field in (
        "attempt_id", "runtime_session_id", "calibration_id", "attachment_profile",
    ):
        _require(review[field] == execution[field], f"review binding mismatch: {field}")
    _require(
        review["calibrated_feedback"] == execution["calibrated_feedback"],
        "reviewed observation differs from execution receipt",
    )

    _identifier(admission["consumer_id"], "consumer_id")
    for field in (
        "consumer_context_sha256", "review_receipt_sha256",
        "execution_receipt_sha256", "calibration_sha256",
        "controller_binding_sha256",
    ):
        _digest(admission[field], field)
    policy = _mapping(admission["freshness_policy"], "freshness policy")
    _exact(policy, _FRESHNESS_FIELDS, "freshness policy")
    maximum_age = _positive_bounded_seconds(
        policy["maximum_observation_age_seconds"],
        MAX_OBSERVATION_AGE_SECONDS,
        "maximum_observation_age_seconds",
    )
    maximum_lifetime = _positive_bounded_seconds(
        policy["maximum_admission_lifetime_seconds"],
        MAX_ADMISSION_LIFETIME_SECONDS,
        "maximum_admission_lifetime_seconds",
    )

    executed_at = _timestamp(execution["executed_at"], "executed_at")
    reviewed_at = _timestamp(review["reviewed_at"], "reviewed_at")
    admitted_at = _timestamp(admission["admitted_at"], "admitted_at")
    valid_until = _timestamp(admission["valid_until"], "valid_until")
    _require(
        executed_at <= reviewed_at <= admitted_at < valid_until,
        "execution, review, admission, and expiry timestamps are not ordered",
    )
    _require(
        admitted_at <= executed_at + timedelta(seconds=maximum_age),
        "observation is stale at admission",
    )
    _require(
        valid_until <= executed_at + timedelta(seconds=maximum_age),
        "validity exceeds the observation freshness window",
    )
    _require(
        valid_until <= admitted_at + timedelta(seconds=maximum_lifetime),
        "validity exceeds the admission lifetime",
    )

    receipt = {
        "schema": ADMISSION_RECEIPT_SCHEMA,
        "status": "CALIBRATED_POSITION_VECTOR_OBSERVATION_STATE_ADMITTED",
        "attempt_id": execution["attempt_id"],
        "runtime_session_id": execution["runtime_session_id"],
        "calibration_id": execution["calibration_id"],
        "attachment_profile": execution["attachment_profile"],
        "consumer_id": admission["consumer_id"],
        "consumer_context_sha256": admission["consumer_context_sha256"],
        "executed_at": execution["executed_at"],
        "reviewed_at": review["reviewed_at"],
        "admitted_at": admission["admitted_at"],
        "valid_until": admission["valid_until"],
        "execution_receipt_sha256": execution_sha,
        "review_receipt_sha256": review_sha,
        "calibration_sha256": review["calibration_sha256"],
        "controller_binding_sha256": execution["controller_binding_sha256"],
        "admission_sha256": canonical_sha256(admission),
        "freshness_policy": dict(policy),
        "calibrated_feedback": review["calibrated_feedback"],
        "next_required_gate": "NAMED_DOWNSTREAM_CONSUMER_OBSERVATION_USE",
        "limitations": [
            "This receipt admits one reviewed calibrated T=1051 observation to one named state consumer only.",
            "The consumer must verify its context digest and use the observation before valid_until.",
            "Any physical use requires a new current operator and hardware-state confirmation.",
            "Admission grants no motion, retry, connection, contact, or physical authority.",
        ],
        "calibrated_feedback_observation_admitted": True,
        "named_consumer_state_use_authorized": True,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "physical_authority": False,
    }
    _exact(receipt, _RECEIPT_FIELDS, "admission receipt")
    return receipt


__all__ = [
    "ADMISSION_RECEIPT_SCHEMA",
    "ADMISSION_SCHEMA",
    "MAX_ADMISSION_LIFETIME_SECONDS",
    "MAX_OBSERVATION_AGE_SECONDS",
    "CalibratedPositionVectorObservationAdmissionError",
    "admit_calibrated_position_vector_observation",
]
