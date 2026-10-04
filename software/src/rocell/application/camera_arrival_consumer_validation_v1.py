"""Aggregate exact camera-arrival consumer receipts without invoking consumers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .camera_arrival_consumer_handoff_v1 import (
    parse_camera_arrival_consumer_handoff_v1,
)
from .camera_arrival_kit_v1 import REQUIRED_SLOT_IDS


RECEIPT_SCHEMA = "rocell.camera_arrival_consumer_validation_receipt.v1"
ASSESSMENT_SCHEMA = "rocell.camera_arrival_consumer_validation_assessment.v1"
COMPLETE_STATUS = "CONSUMER_VALIDATION_COMPLETE_FOR_OFFLINE_REVIEW"
AWAITING_STATUS = "AWAITING_CONSUMER_VALIDATION"
BLOCKED_STATUS = "BLOCKED_HANDOFF_NOT_READY"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_FIELDS = {
    "schema", "artifact_id", "handoff_sha256", "preflight_sha256",
    "consumer_map_sha256", "sidecar_sha256", "source_sha256",
    "consumer_source", "consumer_source_sha256", "downstream_schema",
    "downstream_schema_sha256", "consumer_binding", "validator_id",
    "validator_version_sha256", "validated_at_utc", "validation_status",
    "blockers", "output_sha256", "consumer_invoked", "camera_opened",
    "controller_started", "hardware_writes", "physical_movements",
    "qualification_installed", "physical_admission_ready",
    "physical_authority", "receipt_sha256",
}
_ASSESSMENT_FIELDS = {
    "schema", "status", "handoff_sha256", "slot_count", "pass_count",
    "blocked_count", "pending_count", "route_results",
    "complete_for_offline_review", "configuration_epoch_advanced",
    "deployment_registry_updated", "qualification_installed", "camera_opened",
    "controller_started", "hardware_writes", "physical_movements",
    "physical_authority", "assessment_sha256",
}
_RESULT_FIELDS = {
    "artifact_id", "status", "receipt_sha256", "output_sha256", "blockers",
    "physical_admission_ready",
}


class CameraArrivalConsumerValidationV1Error(ValueError):
    """A consumer receipt or assessment is malformed or inconsistently bound."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _is_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def parse_camera_arrival_consumer_validation_receipt_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Verify one consumer-produced receipt and its zero-authority semantics."""

    if not isinstance(value, Mapping) or set(value) != _RECEIPT_FIELDS:
        raise CameraArrivalConsumerValidationV1Error(
            "consumer receipt fields differ from the v1 contract"
        )
    unsigned = dict(value)
    digest = unsigned.pop("receipt_sha256")
    if not _is_hash(digest) or _digest(unsigned) != digest:
        raise CameraArrivalConsumerValidationV1Error("consumer receipt hash mismatch")
    status = value.get("validation_status")
    blockers = value.get("blockers")
    output = value.get("output_sha256")
    if (
        value.get("schema") != RECEIPT_SCHEMA
        or value.get("artifact_id") not in REQUIRED_SLOT_IDS
        or any(not _is_hash(value.get(field)) for field in (
            "handoff_sha256", "preflight_sha256", "consumer_map_sha256",
            "sidecar_sha256", "source_sha256", "consumer_source_sha256",
            "downstream_schema_sha256", "validator_version_sha256",
        ))
        or any(not isinstance(value.get(field), str) or not value.get(field)
               for field in (
                   "consumer_source", "downstream_schema", "consumer_binding",
                   "validator_id",
               ))
        or not _is_timestamp(value.get("validated_at_utc"))
        or status not in {"PASS", "BLOCKED"}
        or not isinstance(blockers, list)
        or not all(isinstance(item, str) and item for item in blockers)
        or len(blockers) != len(set(blockers))
        or (status == "PASS" and (blockers or not _is_hash(output)))
        or (status == "BLOCKED" and (not blockers or not _is_hash(output)))
        or value.get("consumer_invoked") is not True
        or any(value.get(field) is not False for field in (
            "camera_opened", "controller_started", "qualification_installed",
            "physical_admission_ready", "physical_authority",
        ))
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise CameraArrivalConsumerValidationV1Error(
            "consumer receipt semantics are inconsistent"
        )
    return MappingProxyType(dict(value))


def assess_camera_arrival_consumer_validation_v1(
    handoff: Mapping[str, Any], receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind zero or more receipts to a handoff and report aggregate readiness."""

    try:
        verified_handoff = parse_camera_arrival_consumer_handoff_v1(handoff)
    except ValueError as exc:
        raise CameraArrivalConsumerValidationV1Error(str(exc)) from exc
    parsed: dict[str, Mapping[str, Any]] = {}
    for candidate in receipts:
        receipt = parse_camera_arrival_consumer_validation_receipt_v1(candidate)
        artifact_id = str(receipt["artifact_id"])
        if artifact_id in parsed:
            raise CameraArrivalConsumerValidationV1Error(
                f"duplicate consumer receipt: {artifact_id}"
            )
        parsed[artifact_id] = receipt

    route_results: list[dict[str, Any]] = []
    handoff_ready = verified_handoff[
        "ready_for_offline_consumer_validation"
    ] is True
    for route in verified_handoff["routes"]:
        artifact_id = route["artifact_id"]
        receipt = parsed.get(artifact_id)
        if receipt is not None:
            expected = {
                "handoff_sha256": verified_handoff["handoff_sha256"],
                "preflight_sha256": verified_handoff["preflight_sha256"],
                "consumer_map_sha256": verified_handoff["consumer_map_sha256"],
                "sidecar_sha256": route["sidecar_sha256"],
                "source_sha256": route["source_sha256"],
                "consumer_source": route["consumer_source"],
                "consumer_source_sha256": route["consumer_source_sha256"],
                "downstream_schema": route["downstream_schema"],
                "downstream_schema_sha256": route["downstream_schema_sha256"],
                "consumer_binding": route["consumer_binding"],
            }
            if not handoff_ready or any(receipt[key] != value for key, value in expected.items()):
                raise CameraArrivalConsumerValidationV1Error(
                    f"consumer receipt binding differs: {artifact_id}"
                )
            state = receipt["validation_status"]
            receipt_hash = receipt["receipt_sha256"]
            output_hash = receipt["output_sha256"]
            blockers = list(receipt["blockers"])
        else:
            state = "PENDING" if handoff_ready else "BLOCKED_HANDOFF"
            receipt_hash = None
            output_hash = None
            blockers = [] if handoff_ready else ["HANDOFF_NOT_READY"]
        route_results.append({
            "artifact_id": artifact_id,
            "status": state,
            "receipt_sha256": receipt_hash,
            "output_sha256": output_hash,
            "blockers": blockers,
            "physical_admission_ready": False,
        })

    unknown = sorted(set(parsed) - set(REQUIRED_SLOT_IDS))
    if unknown:
        raise CameraArrivalConsumerValidationV1Error(
            "consumer receipt has unknown artifact identity"
        )
    passed = sum(row["status"] == "PASS" for row in route_results)
    blocked = sum(row["status"] in {"BLOCKED", "BLOCKED_HANDOFF"}
                  for row in route_results)
    pending = sum(row["status"] == "PENDING" for row in route_results)
    complete = handoff_ready and passed == len(REQUIRED_SLOT_IDS)
    status = (
        BLOCKED_STATUS if not handoff_ready
        else COMPLETE_STATUS if complete
        else AWAITING_STATUS
    )
    core = {
        "schema": ASSESSMENT_SCHEMA,
        "status": status,
        "handoff_sha256": verified_handoff["handoff_sha256"],
        "slot_count": len(route_results),
        "pass_count": passed,
        "blocked_count": blocked,
        "pending_count": pending,
        "route_results": route_results,
        "complete_for_offline_review": complete,
        "configuration_epoch_advanced": False,
        "deployment_registry_updated": False,
        "qualification_installed": False,
        "camera_opened": False,
        "controller_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "assessment_sha256": _digest(core)}


def parse_camera_arrival_consumer_validation_assessment_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Verify an aggregate assessment before any later offline review."""

    if not isinstance(value, Mapping) or set(value) != _ASSESSMENT_FIELDS:
        raise CameraArrivalConsumerValidationV1Error(
            "consumer assessment fields differ from the v1 contract"
        )
    unsigned = dict(value)
    digest = unsigned.pop("assessment_sha256")
    if not _is_hash(digest) or _digest(unsigned) != digest:
        raise CameraArrivalConsumerValidationV1Error("consumer assessment hash mismatch")
    results = value.get("route_results")
    if (
        not isinstance(results, list)
        or len(results) != len(REQUIRED_SLOT_IDS)
        or tuple(
            row.get("artifact_id") if isinstance(row, Mapping) else None
            for row in results
        ) != REQUIRED_SLOT_IDS
    ):
        raise CameraArrivalConsumerValidationV1Error(
            "consumer assessment route identity differs"
        )
    for row in results:
        if not isinstance(row, Mapping) or set(row) != _RESULT_FIELDS:
            raise CameraArrivalConsumerValidationV1Error(
                "consumer assessment result fields differ"
            )
        status = row.get("status")
        blockers = row.get("blockers")
        if (
            status not in {"PENDING", "PASS", "BLOCKED", "BLOCKED_HANDOFF"}
            or not isinstance(blockers, list)
            or not all(isinstance(item, str) and item for item in blockers)
            or len(blockers) != len(set(blockers))
            or row.get("physical_admission_ready") is not False
            or (status == "PASS" and (
                not _is_hash(row.get("receipt_sha256"))
                or not _is_hash(row.get("output_sha256")) or blockers
            ))
            or (status == "BLOCKED" and (
                not _is_hash(row.get("receipt_sha256"))
                or not _is_hash(row.get("output_sha256")) or not blockers
            ))
            or (status in {"PENDING", "BLOCKED_HANDOFF"} and (
                row.get("receipt_sha256") is not None
                or row.get("output_sha256") is not None
            ))
            or (status == "PENDING" and blockers)
            or (status == "BLOCKED_HANDOFF" and blockers != ["HANDOFF_NOT_READY"])
        ):
            raise CameraArrivalConsumerValidationV1Error(
                "consumer assessment result semantics are inconsistent"
            )
    passed = sum(row["status"] == "PASS" for row in results)
    blocked = sum(row["status"] in {"BLOCKED", "BLOCKED_HANDOFF"} for row in results)
    pending = sum(row["status"] == "PENDING" for row in results)
    complete = value.get("complete_for_offline_review") is True
    expected_status = (
        COMPLETE_STATUS if complete else
        BLOCKED_STATUS if all(row["status"] == "BLOCKED_HANDOFF" for row in results)
        else AWAITING_STATUS
    )
    if (
        value.get("schema") != ASSESSMENT_SCHEMA
        or value.get("status") != expected_status
        or not _is_hash(value.get("handoff_sha256"))
        or value.get("slot_count") != 15
        or value.get("pass_count") != passed
        or value.get("blocked_count") != blocked
        or value.get("pending_count") != pending
        or complete != (passed == 15)
        or any(value.get(field) is not False for field in (
            "configuration_epoch_advanced", "deployment_registry_updated",
            "qualification_installed", "camera_opened", "controller_started",
            "physical_authority",
        ))
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise CameraArrivalConsumerValidationV1Error(
            "consumer assessment semantics are inconsistent"
        )
    return MappingProxyType(dict(value))


__all__ = [
    "ASSESSMENT_SCHEMA", "AWAITING_STATUS", "BLOCKED_STATUS", "COMPLETE_STATUS",
    "RECEIPT_SCHEMA", "CameraArrivalConsumerValidationV1Error",
    "assess_camera_arrival_consumer_validation_v1",
    "parse_camera_arrival_consumer_validation_assessment_v1",
    "parse_camera_arrival_consumer_validation_receipt_v1",
]
