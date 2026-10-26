"""Admit one stored calibrated state event for one named read-only consumer."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.calibration.position_vector_campaign import canonical_sha256
from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
    canonical,
)

from .calibrated_position_vector_state_ingestion import (
    MAX_STATE_INGESTION_RECEIPT_BYTES,
    STATE_INGESTION_RECEIPT_SCHEMA,
)


SNAPSHOT_READ_ADMISSION_SCHEMA = (
    "rocell.calibrated_state_snapshot_read_admission.v1"
)
SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA = (
    "rocell.calibrated_state_snapshot_read_admission_receipt.v1"
)
MAX_SNAPSHOT_AGE_SECONDS = 300
MAX_READ_ADMISSION_LIFETIME_SECONDS = 60

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_INGESTION_PREFIX = "state-ingestion:"
_INGESTION_FIELDS = frozenset(
    {
        "schema", "status", "ingestion_id", "redemption_id", "consumer_id",
        "consumer_context_sha256", "attempt_id", "runtime_session_id",
        "calibration_id", "attachment_profile", "executed_at", "redeemed_at",
        "ingested_at", "redemption_receipt_sha256",
        "admission_receipt_sha256", "execution_receipt_sha256",
        "review_receipt_sha256", "calibration_sha256",
        "controller_binding_sha256", "calibrated_feedback",
        "next_required_gate", "limitations",
        "calibrated_feedback_state_ingested",
        "duplicate_delivery_idempotent", "automatic_retry_allowed",
        "motion_authorized", "physical_authority",
    }
)
_ADMISSION_FIELDS = frozenset(
    {
        "schema", "reader_id", "reader_context_sha256", "consumer_id",
        "consumer_context_sha256", "state_ingestion_receipt_sha256",
        "calibration_sha256", "controller_binding_sha256", "calibration_id",
        "attachment_profile", "admitted_at", "valid_until",
        "freshness_policy",
    }
)
_FRESHNESS_FIELDS = frozenset(
    {"maximum_snapshot_age_seconds", "maximum_read_lifetime_seconds"}
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "snapshot_id", "reader_id",
        "reader_context_sha256", "consumer_id", "consumer_context_sha256",
        "ingestion_id", "redemption_id", "attempt_id", "runtime_session_id",
        "calibration_id", "attachment_profile", "executed_at", "ingested_at",
        "admitted_at", "valid_until", "state_ingestion_receipt_sha256",
        "redemption_receipt_sha256", "admission_receipt_sha256",
        "execution_receipt_sha256", "review_receipt_sha256",
        "calibration_sha256", "controller_binding_sha256", "freshness_policy",
        "calibrated_feedback", "next_required_gate", "limitations",
        "calibrated_state_snapshot_read_admitted",
        "named_reader_snapshot_use_authorized", "automatic_retry_allowed",
        "motion_authorized", "physical_authority",
    }
)


class CalibratedStateSnapshotReadAdmissionError(ValueError):
    """A stored calibrated state event is ineligible for named-reader use."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibratedStateSnapshotReadAdmissionError(message)


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
        raise CalibratedStateSnapshotReadAdmissionError(
            f"{label} is invalid"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "stored state event has duplicate fields")
        result[key] = value
    return result


def _stored_event(
    root_value: Path, ingestion: Mapping[str, Any], ingestion_key: str,
) -> dict[str, Any]:
    root = Path(root_value)
    _require(
        root.is_absolute() and root.is_dir() and not root.is_symlink(),
        "existing absolute nonsymlink state ingestion directory required",
    )
    path = root.resolve() / f"{ingestion_key}.json"
    _require(path.is_file() and not path.is_symlink(), "stored state event is unsafe")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_STATE_INGESTION_RECEIPT_BYTES + 1)
    except OSError as exc:
        raise CalibratedStateSnapshotReadAdmissionError(
            "stored state event cannot be read"
        ) from exc
    _require(
        0 < len(raw) <= MAX_STATE_INGESTION_RECEIPT_BYTES,
        "stored state event is empty or oversized",
    )
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibratedStateSnapshotReadAdmissionError(
            "stored state event is invalid JSON"
        ) from exc
    stored = _mapping(value, "stored state event")
    _require(raw == canonical(stored) + b"\n", "stored state event is not canonical")
    _require(stored == ingestion, "stored state event differs from the selected receipt")
    return stored


def admit_calibrated_state_snapshot_read(
    ingestion_directory: Path,
    *,
    state_ingestion_receipt_document: Mapping[str, Any],
    admission_document: Mapping[str, Any],
    reader_context_document: Mapping[str, Any],
    current_consumer_context_document: Mapping[str, Any],
    current_calibration_document: Mapping[str, Any],
    current_controller_binding_document: Mapping[str, Any],
    current_attachment_profile: str,
) -> dict[str, Any]:
    """Issue a bounded typed snapshot to one named read-only consumer."""

    ingestion = _mapping(
        state_ingestion_receipt_document, "state ingestion receipt"
    )
    admission = _mapping(admission_document, "snapshot read admission")
    reader_context = _mapping(reader_context_document, "reader context")
    consumer_context = _mapping(
        current_consumer_context_document, "current consumer context"
    )
    calibration = _mapping(current_calibration_document, "current calibration")
    controller = _mapping(
        current_controller_binding_document, "current controller binding"
    )
    _exact(ingestion, _INGESTION_FIELDS, "state ingestion receipt")
    _exact(admission, _ADMISSION_FIELDS, "snapshot read admission")

    _require(
        ingestion["schema"] == STATE_INGESTION_RECEIPT_SCHEMA
        and ingestion["status"] == "CALIBRATED_POSITION_VECTOR_STATE_INGESTED"
        and ingestion["next_required_gate"]
        == "CALIBRATED_STATE_SNAPSHOT_READ_ADMISSION"
        and ingestion["calibrated_feedback_state_ingested"] is True
        and ingestion["duplicate_delivery_idempotent"] is True,
        "state ingestion receipt is not eligible for snapshot read admission",
    )
    _require(
        ingestion["automatic_retry_allowed"] is False
        and ingestion["motion_authorized"] is False
        and ingestion["physical_authority"] is False,
        "state ingestion receipt authority is invalid",
    )
    for field in (
        "consumer_context_sha256", "redemption_receipt_sha256",
        "admission_receipt_sha256", "execution_receipt_sha256",
        "review_receipt_sha256", "calibration_sha256",
        "controller_binding_sha256",
    ):
        _digest(ingestion[field], field)
    for field in (
        "consumer_id", "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile",
    ):
        _identifier(ingestion[field], field)
    _require(
        isinstance(ingestion["calibrated_feedback"], Mapping),
        "ingested calibrated feedback must be an object",
    )

    ingestion_id = ingestion["ingestion_id"]
    _require(
        isinstance(ingestion_id, str) and ingestion_id.startswith(_INGESTION_PREFIX),
        "ingestion_id is invalid",
    )
    ingestion_key = _digest(
        ingestion_id[len(_INGESTION_PREFIX):], "ingestion_id digest"
    )
    _require(
        ingestion_key == ingestion["admission_receipt_sha256"],
        "ingestion_id does not bind the admission receipt",
    )
    _stored_event(ingestion_directory, ingestion, ingestion_key)

    _require(
        admission["schema"] == SNAPSHOT_READ_ADMISSION_SCHEMA,
        "snapshot read admission schema is invalid",
    )
    reader_id = _identifier(admission["reader_id"], "reader_id")
    _require(
        reader_context.get("reader_id") == reader_id,
        "reader context does not identify the named reader",
    )
    reader_context_sha = canonical_sha256(reader_context)
    consumer_context_sha = canonical_sha256(consumer_context)
    ingestion_sha = canonical_sha256(ingestion)
    calibration_sha = canonical_sha256(calibration)
    controller_sha = canonical_sha256(controller)
    _require(
        admission["reader_context_sha256"] == reader_context_sha,
        "reader context differs from the admitted context",
    )
    _require(
        admission["consumer_id"] == ingestion["consumer_id"]
        and consumer_context.get("consumer_id") == ingestion["consumer_id"],
        "current consumer identity differs from the stored state event",
    )
    _require(
        admission["consumer_context_sha256"] == consumer_context_sha
        == ingestion["consumer_context_sha256"],
        "current consumer context differs from the stored state event",
    )
    _require(
        admission["state_ingestion_receipt_sha256"] == ingestion_sha,
        "state_ingestion_receipt_sha256 mismatch",
    )
    _require(
        admission["calibration_id"] == ingestion["calibration_id"]
        == calibration.get("calibration_id")
        and admission["calibration_sha256"] == calibration_sha
        == ingestion["calibration_sha256"],
        "current calibration differs from the stored state event",
    )
    _require(
        admission["controller_binding_sha256"] == controller_sha
        == ingestion["controller_binding_sha256"],
        "current controller binding differs from the stored state event",
    )
    _identifier(current_attachment_profile, "current_attachment_profile")
    _require(
        admission["attachment_profile"] == current_attachment_profile
        == ingestion["attachment_profile"],
        "current attachment profile differs from the stored state event",
    )

    policy = _mapping(admission["freshness_policy"], "freshness policy")
    _exact(policy, _FRESHNESS_FIELDS, "freshness policy")
    maximum_age = policy["maximum_snapshot_age_seconds"]
    maximum_lifetime = policy["maximum_read_lifetime_seconds"]
    _require(
        type(maximum_age) is int and 0 < maximum_age <= MAX_SNAPSHOT_AGE_SECONDS,
        "maximum snapshot age is outside the bounded contract",
    )
    _require(
        type(maximum_lifetime) is int
        and 0 < maximum_lifetime <= MAX_READ_ADMISSION_LIFETIME_SECONDS,
        "maximum read lifetime is outside the bounded contract",
    )
    executed = _timestamp(ingestion["executed_at"], "executed_at")
    ingested = _timestamp(ingestion["ingested_at"], "ingested_at")
    admitted = _timestamp(admission["admitted_at"], "admitted_at")
    valid_until = _timestamp(admission["valid_until"], "valid_until")
    _require(
        executed <= ingested <= admitted < valid_until,
        "snapshot read admission timestamp ordering is invalid",
    )
    _require(
        valid_until <= executed + timedelta(seconds=maximum_age)
        and valid_until <= admitted + timedelta(seconds=maximum_lifetime),
        "snapshot read admission exceeds its freshness policy",
    )

    snapshot_basis = {
        "state_ingestion_receipt_sha256": ingestion_sha,
        "reader_id": reader_id,
        "reader_context_sha256": reader_context_sha,
    }
    receipt = {
        "schema": SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA,
        "status": "CALIBRATED_STATE_SNAPSHOT_READ_ADMITTED",
        "snapshot_id": f"calibrated-state-snapshot:{canonical_sha256(snapshot_basis)}",
        "reader_id": reader_id,
        "reader_context_sha256": reader_context_sha,
        "consumer_id": ingestion["consumer_id"],
        "consumer_context_sha256": consumer_context_sha,
        "ingestion_id": ingestion_id,
        "redemption_id": ingestion["redemption_id"],
        "attempt_id": ingestion["attempt_id"],
        "runtime_session_id": ingestion["runtime_session_id"],
        "calibration_id": ingestion["calibration_id"],
        "attachment_profile": ingestion["attachment_profile"],
        "executed_at": ingestion["executed_at"],
        "ingested_at": ingestion["ingested_at"],
        "admitted_at": admission["admitted_at"],
        "valid_until": admission["valid_until"],
        "state_ingestion_receipt_sha256": ingestion_sha,
        "redemption_receipt_sha256": ingestion["redemption_receipt_sha256"],
        "admission_receipt_sha256": ingestion["admission_receipt_sha256"],
        "execution_receipt_sha256": ingestion["execution_receipt_sha256"],
        "review_receipt_sha256": ingestion["review_receipt_sha256"],
        "calibration_sha256": calibration_sha,
        "controller_binding_sha256": controller_sha,
        "freshness_policy": dict(policy),
        "calibrated_feedback": dict(ingestion["calibrated_feedback"]),
        "next_required_gate": "CAMERA_FEEDBACK_STATE_FUSION_ADMISSION",
        "limitations": [
            "This receipt exposes one bounded read-only calibrated state snapshot.",
            "Only the exact named reader and reader context may use this snapshot.",
            "Camera feedback must pass a separate fusion-admission boundary.",
            "Snapshot admission grants no motion, retry, connection, contact, or physical authority.",
        ],
        "calibrated_state_snapshot_read_admitted": True,
        "named_reader_snapshot_use_authorized": True,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "physical_authority": False,
    }
    _exact(receipt, _RECEIPT_FIELDS, "snapshot read admission receipt")
    return receipt


__all__ = [
    "MAX_READ_ADMISSION_LIFETIME_SECONDS",
    "MAX_SNAPSHOT_AGE_SECONDS",
    "SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA",
    "SNAPSHOT_READ_ADMISSION_SCHEMA",
    "CalibratedStateSnapshotReadAdmissionError",
    "admit_calibrated_state_snapshot_read",
]
