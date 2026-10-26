"""Redeem one admitted calibrated observation for one named consumer.

This file-only gate rechecks the admission, consumer context, and freshness at
the instant of use.  It durably occupies a path derived from the exact
admission before returning the observation, so concurrent or later attempts
cannot redeem the same admission again.  It opens no hardware and grants no
motion, connection, contact, retry, or physical authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.calibration.position_vector_campaign import canonical_sha256
from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
    canonical,
)

from .calibrated_position_vector_observation_admission import (
    ADMISSION_RECEIPT_SCHEMA,
    MAX_ADMISSION_LIFETIME_SECONDS,
    MAX_OBSERVATION_AGE_SECONDS,
)


REDEMPTION_RECEIPT_SCHEMA = (
    "rocell.calibrated_position_vector_observation_redemption_receipt.v1"
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ADMISSION_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "attempt_id", "runtime_session_id",
        "calibration_id", "attachment_profile", "consumer_id",
        "consumer_context_sha256", "executed_at", "reviewed_at",
        "admitted_at", "valid_until", "execution_receipt_sha256",
        "review_receipt_sha256", "calibration_sha256",
        "controller_binding_sha256", "admission_sha256", "freshness_policy",
        "calibrated_feedback", "next_required_gate", "limitations",
        "calibrated_feedback_observation_admitted",
        "named_consumer_state_use_authorized", "automatic_retry_allowed",
        "motion_authorized", "physical_authority",
    }
)
_FRESHNESS_FIELDS = frozenset(
    {"maximum_observation_age_seconds", "maximum_admission_lifetime_seconds"}
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "redemption_id", "consumer_id",
        "consumer_context_sha256", "attempt_id", "runtime_session_id",
        "calibration_id", "attachment_profile", "executed_at", "admitted_at",
        "valid_until", "redeemed_at", "admission_receipt_sha256",
        "execution_receipt_sha256", "review_receipt_sha256",
        "calibration_sha256", "controller_binding_sha256",
        "calibrated_feedback", "next_required_gate", "limitations",
        "calibrated_feedback_observation_redeemed_once",
        "redemption_replay_allowed", "automatic_retry_allowed",
        "motion_authorized", "physical_authority",
    }
)


class CalibratedPositionVectorObservationRedemptionError(ValueError):
    """The admitted observation cannot be redeemed by this consumer."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibratedPositionVectorObservationRedemptionError(message)


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
        raise CalibratedPositionVectorObservationRedemptionError(
            f"{label} is invalid"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _redemption_root(value: Path) -> Path:
    path = Path(value)
    _require(
        path.is_absolute() and path.is_dir() and not path.is_symlink(),
        "existing absolute nonsymlink redemption directory required",
    )
    return path.resolve()


def _publish_once(path: Path, receipt: Mapping[str, Any]) -> None:
    raw = canonical(receipt) + b"\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CalibratedPositionVectorObservationRedemptionError(
            "admission was already redeemed or a prior redemption became terminal"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def redeem_calibrated_position_vector_observation(
    redemption_directory: Path,
    *,
    admission_receipt_document: Mapping[str, Any],
    consumer_id: str,
    consumer_context_document: Mapping[str, Any],
    redeemed_at: str,
) -> dict[str, Any]:
    """Durably redeem one fresh admission and return its observation once."""

    root = _redemption_root(redemption_directory)
    admission = _mapping(admission_receipt_document, "admission receipt")
    consumer_context = _mapping(consumer_context_document, "consumer context")
    _exact(admission, _ADMISSION_RECEIPT_FIELDS, "admission receipt")
    _identifier(consumer_id, "consumer_id")

    _require(
        admission["schema"] == ADMISSION_RECEIPT_SCHEMA
        and admission["status"]
        == "CALIBRATED_POSITION_VECTOR_OBSERVATION_STATE_ADMITTED"
        and admission["next_required_gate"]
        == "NAMED_DOWNSTREAM_CONSUMER_OBSERVATION_USE"
        and admission["calibrated_feedback_observation_admitted"] is True
        and admission["named_consumer_state_use_authorized"] is True,
        "admission receipt is not eligible for named-consumer redemption",
    )
    _require(
        admission["automatic_retry_allowed"] is False
        and admission["motion_authorized"] is False
        and admission["physical_authority"] is False,
        "admission receipt authority is invalid",
    )
    _require(admission["consumer_id"] == consumer_id, "consumer_id mismatch")
    _require(
        consumer_context.get("consumer_id") == consumer_id,
        "consumer context does not identify the named consumer",
    )
    context_sha = canonical_sha256(consumer_context)
    _require(
        admission["consumer_context_sha256"] == context_sha,
        "consumer context differs from the admitted context",
    )

    for field in (
        "consumer_context_sha256", "execution_receipt_sha256",
        "review_receipt_sha256", "calibration_sha256",
        "controller_binding_sha256", "admission_sha256",
    ):
        _digest(admission[field], field)
    for field in (
        "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile",
    ):
        _identifier(admission[field], field)
    policy = _mapping(admission["freshness_policy"], "freshness policy")
    _exact(policy, _FRESHNESS_FIELDS, "freshness policy")
    maximum_age = policy["maximum_observation_age_seconds"]
    maximum_lifetime = policy["maximum_admission_lifetime_seconds"]
    _require(
        type(maximum_age) is int and 0 < maximum_age <= MAX_OBSERVATION_AGE_SECONDS,
        "maximum observation age is outside the bounded contract",
    )
    _require(
        type(maximum_lifetime) is int
        and 0 < maximum_lifetime <= MAX_ADMISSION_LIFETIME_SECONDS,
        "maximum admission lifetime is outside the bounded contract",
    )
    _require(
        isinstance(admission["calibrated_feedback"], Mapping),
        "admitted calibrated feedback must be an object",
    )

    executed = _timestamp(admission["executed_at"], "executed_at")
    reviewed = _timestamp(admission["reviewed_at"], "reviewed_at")
    admitted = _timestamp(admission["admitted_at"], "admitted_at")
    valid_until = _timestamp(admission["valid_until"], "valid_until")
    consumed = _timestamp(redeemed_at, "redeemed_at")
    _require(
        executed <= reviewed <= admitted <= consumed < valid_until,
        "observation is not fresh at redemption",
    )
    _require(
        valid_until <= executed + timedelta(seconds=maximum_age)
        and valid_until <= admitted + timedelta(seconds=maximum_lifetime),
        "admission validity exceeds its freshness policy",
    )

    admission_receipt_sha = canonical_sha256(admission)
    redemption_id = f"observation-redemption:{admission_receipt_sha}"
    receipt = {
        "schema": REDEMPTION_RECEIPT_SCHEMA,
        "status": "CALIBRATED_POSITION_VECTOR_OBSERVATION_REDEEMED",
        "redemption_id": redemption_id,
        "consumer_id": consumer_id,
        "consumer_context_sha256": context_sha,
        "attempt_id": admission["attempt_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "calibration_id": admission["calibration_id"],
        "attachment_profile": admission["attachment_profile"],
        "executed_at": admission["executed_at"],
        "admitted_at": admission["admitted_at"],
        "valid_until": admission["valid_until"],
        "redeemed_at": redeemed_at,
        "admission_receipt_sha256": admission_receipt_sha,
        "execution_receipt_sha256": admission["execution_receipt_sha256"],
        "review_receipt_sha256": admission["review_receipt_sha256"],
        "calibration_sha256": admission["calibration_sha256"],
        "controller_binding_sha256": admission["controller_binding_sha256"],
        "calibrated_feedback": dict(admission["calibrated_feedback"]),
        "next_required_gate": "NAMED_CONSUMER_IDEMPOTENT_STATE_INGESTION",
        "limitations": [
            "This receipt records one redemption by the exact named consumer and context only.",
            "The consumer state store must ingest redemption_id idempotently.",
            "The admission cannot be redeemed again, including after an interrupted write.",
            "Redemption grants no motion, retry, connection, contact, or physical authority.",
        ],
        "calibrated_feedback_observation_redeemed_once": True,
        "redemption_replay_allowed": False,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "physical_authority": False,
    }
    _exact(receipt, _RECEIPT_FIELDS, "redemption receipt")
    destination = root / f"{admission_receipt_sha}.json"
    _publish_once(destination, receipt)
    return receipt


__all__ = [
    "REDEMPTION_RECEIPT_SCHEMA",
    "CalibratedPositionVectorObservationRedemptionError",
    "redeem_calibrated_position_vector_observation",
]
