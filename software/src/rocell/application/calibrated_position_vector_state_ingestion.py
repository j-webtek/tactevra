"""Idempotently ingest one redeemed calibrated observation into consumer state.

The first valid delivery is durably published under its redemption identity.
An identical later delivery returns that original result without applying the
observation again.  No hardware is opened and no motion authority is granted.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Mapping

from rocell.calibration.position_vector_campaign import canonical_sha256
from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
    canonical,
)

from .calibrated_position_vector_observation_redemption import (
    REDEMPTION_RECEIPT_SCHEMA,
)


STATE_INGESTION_RECEIPT_SCHEMA = (
    "rocell.calibrated_position_vector_state_ingestion_receipt.v1"
)
MAX_STATE_INGESTION_RECEIPT_BYTES = 1024 * 1024

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REDEMPTION_PREFIX = "observation-redemption:"
_REDEMPTION_FIELDS = frozenset(
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
_RECEIPT_FIELDS = frozenset(
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


class CalibratedPositionVectorStateIngestionError(ValueError):
    """The redeemed observation cannot be ingested into consumer state."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibratedPositionVectorStateIngestionError(message)


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
        raise CalibratedPositionVectorStateIngestionError(
            f"{label} is invalid"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _ingestion_root(value: Path) -> Path:
    path = Path(value)
    _require(
        path.is_absolute() and path.is_dir() and not path.is_symlink(),
        "existing absolute nonsymlink state ingestion directory required",
    )
    return path.resolve()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CalibratedPositionVectorStateIngestionError(
                "stored state ingestion receipt has duplicate fields"
            )
        result[key] = value
    return result


def _read_existing(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), "stored receipt is unsafe")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_STATE_INGESTION_RECEIPT_BYTES + 1)
    except OSError as exc:
        raise CalibratedPositionVectorStateIngestionError(
            "stored state ingestion receipt cannot be read"
        ) from exc
    _require(
        0 < len(raw) <= MAX_STATE_INGESTION_RECEIPT_BYTES,
        "stored state ingestion receipt is empty or oversized",
    )
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibratedPositionVectorStateIngestionError(
            "stored state ingestion receipt is invalid JSON"
        ) from exc
    receipt = _mapping(value, "stored state ingestion receipt")
    _require(
        raw == canonical(receipt) + b"\n",
        "stored state ingestion receipt is not canonical",
    )
    return receipt


def _write_new(path: Path, raw: bytes) -> None:
    _require(
        len(raw) <= MAX_STATE_INGESTION_RECEIPT_BYTES,
        "state ingestion receipt exceeds the size limit",
    )
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise CalibratedPositionVectorStateIngestionError(
            "cannot stage state ingestion receipt"
        ) from exc


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        if os.name == "nt":
            return
        raise CalibratedPositionVectorStateIngestionError(
            "cannot open state ingestion directory for durability sync"
        ) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if os.name != "nt":
            raise CalibratedPositionVectorStateIngestionError(
                "cannot durability-sync state ingestion directory"
            ) from exc
    finally:
        os.close(descriptor)


def _receipt_for(
    redemption: Mapping[str, Any], *, consumer_id: str,
    consumer_context_sha256: str, redemption_sha256: str, ingested_at: str,
) -> dict[str, Any]:
    redemption_id = redemption["redemption_id"]
    redemption_key = redemption_id[len(_REDEMPTION_PREFIX):]
    return {
        "schema": STATE_INGESTION_RECEIPT_SCHEMA,
        "status": "CALIBRATED_POSITION_VECTOR_STATE_INGESTED",
        "ingestion_id": f"state-ingestion:{redemption_key}",
        "redemption_id": redemption_id,
        "consumer_id": consumer_id,
        "consumer_context_sha256": consumer_context_sha256,
        "attempt_id": redemption["attempt_id"],
        "runtime_session_id": redemption["runtime_session_id"],
        "calibration_id": redemption["calibration_id"],
        "attachment_profile": redemption["attachment_profile"],
        "executed_at": redemption["executed_at"],
        "redeemed_at": redemption["redeemed_at"],
        "ingested_at": ingested_at,
        "redemption_receipt_sha256": redemption_sha256,
        "admission_receipt_sha256": redemption["admission_receipt_sha256"],
        "execution_receipt_sha256": redemption["execution_receipt_sha256"],
        "review_receipt_sha256": redemption["review_receipt_sha256"],
        "calibration_sha256": redemption["calibration_sha256"],
        "controller_binding_sha256": redemption["controller_binding_sha256"],
        "calibrated_feedback": dict(redemption["calibrated_feedback"]),
        "next_required_gate": "CALIBRATED_STATE_SNAPSHOT_READ_ADMISSION",
        "limitations": [
            "This receipt records one immutable state observation event only.",
            "A duplicate delivery returns this exact result without reapplying state.",
            "A separate read-admission gate must select and expose a current snapshot.",
            "Ingestion grants no motion, retry, connection, contact, or physical authority.",
        ],
        "calibrated_feedback_state_ingested": True,
        "duplicate_delivery_idempotent": True,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "physical_authority": False,
    }


def _validate_stored(
    receipt: Mapping[str, Any], *, redemption: Mapping[str, Any],
    redemption_sha256: str, consumer_id: str, consumer_context_sha256: str,
) -> dict[str, Any]:
    stored = dict(receipt)
    _exact(stored, _RECEIPT_FIELDS, "stored state ingestion receipt")
    _require(
        stored["schema"] == STATE_INGESTION_RECEIPT_SCHEMA
        and stored["status"] == "CALIBRATED_POSITION_VECTOR_STATE_INGESTED"
        and stored["next_required_gate"]
        == "CALIBRATED_STATE_SNAPSHOT_READ_ADMISSION"
        and stored["calibrated_feedback_state_ingested"] is True
        and stored["duplicate_delivery_idempotent"] is True,
        "stored state ingestion receipt is not eligible",
    )
    _require(
        stored["automatic_retry_allowed"] is False
        and stored["motion_authorized"] is False
        and stored["physical_authority"] is False,
        "stored state ingestion receipt authority is invalid",
    )
    _require(
        stored["redemption_id"] == redemption["redemption_id"]
        and stored["redemption_receipt_sha256"] == redemption_sha256,
        "redemption_id already belongs to a different payload",
    )
    _require(
        stored["consumer_id"] == consumer_id
        and stored["consumer_context_sha256"] == consumer_context_sha256,
        "stored state ingestion consumer binding differs",
    )
    for field in (
        "redemption_receipt_sha256", "consumer_context_sha256",
        "admission_receipt_sha256", "execution_receipt_sha256",
        "review_receipt_sha256", "calibration_sha256",
        "controller_binding_sha256",
    ):
        _digest(stored[field], field)
    for field in ("executed_at", "redeemed_at", "ingested_at"):
        _timestamp(stored[field], field)
    _require(
        isinstance(stored["calibrated_feedback"], Mapping),
        "stored calibrated feedback must be an object",
    )
    expected = _receipt_for(
        redemption,
        consumer_id=consumer_id,
        consumer_context_sha256=consumer_context_sha256,
        redemption_sha256=redemption_sha256,
        ingested_at=stored["ingested_at"],
    )
    _require(
        stored == expected,
        "stored state ingestion receipt differs from the original result",
    )
    return stored


def ingest_calibrated_position_vector_state(
    ingestion_directory: Path,
    *,
    redemption_receipt_document: Mapping[str, Any],
    consumer_id: str,
    consumer_context_document: Mapping[str, Any],
    ingested_at: str,
) -> dict[str, Any]:
    """Apply a redeemed observation once, or return its original result."""

    root = _ingestion_root(ingestion_directory)
    redemption = _mapping(redemption_receipt_document, "redemption receipt")
    context = _mapping(consumer_context_document, "consumer context")
    _exact(redemption, _REDEMPTION_FIELDS, "redemption receipt")
    _identifier(consumer_id, "consumer_id")

    _require(
        redemption["schema"] == REDEMPTION_RECEIPT_SCHEMA
        and redemption["status"]
        == "CALIBRATED_POSITION_VECTOR_OBSERVATION_REDEEMED"
        and redemption["next_required_gate"]
        == "NAMED_CONSUMER_IDEMPOTENT_STATE_INGESTION"
        and redemption["calibrated_feedback_observation_redeemed_once"] is True
        and redemption["redemption_replay_allowed"] is False,
        "redemption receipt is not eligible for state ingestion",
    )
    _require(
        redemption["automatic_retry_allowed"] is False
        and redemption["motion_authorized"] is False
        and redemption["physical_authority"] is False,
        "redemption receipt authority is invalid",
    )
    _require(redemption["consumer_id"] == consumer_id, "consumer_id mismatch")
    _require(
        context.get("consumer_id") == consumer_id,
        "consumer context does not identify the named consumer",
    )
    context_sha = canonical_sha256(context)
    _require(
        redemption["consumer_context_sha256"] == context_sha,
        "consumer context differs from the redeemed context",
    )

    for field in (
        "consumer_context_sha256", "admission_receipt_sha256",
        "execution_receipt_sha256", "review_receipt_sha256",
        "calibration_sha256", "controller_binding_sha256",
    ):
        _digest(redemption[field], field)
    for field in (
        "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile",
    ):
        _identifier(redemption[field], field)
    _require(
        isinstance(redemption["calibrated_feedback"], Mapping),
        "redeemed calibrated feedback must be an object",
    )

    redemption_id = redemption["redemption_id"]
    _require(
        isinstance(redemption_id, str)
        and redemption_id.startswith(_REDEMPTION_PREFIX),
        "redemption_id is invalid",
    )
    redemption_key = _digest(
        redemption_id[len(_REDEMPTION_PREFIX):], "redemption_id digest"
    )
    _require(
        redemption_key == redemption["admission_receipt_sha256"],
        "redemption_id does not bind the admission receipt",
    )
    executed = _timestamp(redemption["executed_at"], "executed_at")
    admitted = _timestamp(redemption["admitted_at"], "admitted_at")
    valid_until = _timestamp(redemption["valid_until"], "valid_until")
    redeemed = _timestamp(redemption["redeemed_at"], "redeemed_at")
    ingested = _timestamp(ingested_at, "ingested_at")
    _require(
        executed <= admitted <= redeemed < valid_until,
        "redemption receipt timestamp ordering is invalid",
    )

    redemption_sha = canonical_sha256(redemption)
    destination = root / f"{redemption_key}.json"
    if destination.exists() or destination.is_symlink():
        return _validate_stored(
            _read_existing(destination),
            redemption=redemption,
            redemption_sha256=redemption_sha,
            consumer_id=consumer_id,
            consumer_context_sha256=context_sha,
        )

    _require(
        redeemed <= ingested < valid_until,
        "redeemed observation is not fresh at first state ingestion",
    )
    receipt = _receipt_for(
        redemption,
        consumer_id=consumer_id,
        consumer_context_sha256=context_sha,
        redemption_sha256=redemption_sha,
        ingested_at=ingested_at,
    )
    _exact(receipt, _RECEIPT_FIELDS, "state ingestion receipt")
    temporary = root / f".partial-{redemption_key}-{secrets.token_hex(8)}"
    _write_new(temporary, canonical(receipt) + b"\n")
    try:
        try:
            os.link(temporary, destination)
            _fsync_directory(root)
            return receipt
        except FileExistsError:
            return _validate_stored(
                _read_existing(destination),
                redemption=redemption,
                redemption_sha256=redemption_sha,
                consumer_id=consumer_id,
                consumer_context_sha256=context_sha,
            )
        except OSError as exc:
            raise CalibratedPositionVectorStateIngestionError(
                "cannot atomically publish state ingestion receipt"
            ) from exc
    finally:
        try:
            if temporary.is_file() and not temporary.is_symlink():
                temporary.unlink()
        except OSError:
            pass


__all__ = [
    "MAX_STATE_INGESTION_RECEIPT_BYTES",
    "STATE_INGESTION_RECEIPT_SCHEMA",
    "CalibratedPositionVectorStateIngestionError",
    "ingest_calibrated_position_vector_state",
]
