"""Read-only structural preflight for final-camera arrival evidence.

This module inventories the canonical PC9 evidence slots beneath an external
root.  It validates sidecars and their referenced source bytes, but it cannot
accept calibration, advance an epoch, update a registry, or authorize hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .camera_arrival_kit_v1 import build_camera_arrival_kit_v1


SCHEMA = "rocell.camera_arrival_evidence_preflight.v1"
READY_STATUS = "READY_FOR_OFFLINE_QUALIFICATION_REVIEW"
BLOCKED_STATUS = "BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE"
MAX_SIDECAR_BYTES = 1_048_576
_SIDECAR_FIELDS = {
    "schema",
    "artifact_id",
    "artifact_class",
    "captured_at_utc",
    "source_relative_path",
    "source_size_bytes",
    "source_sha256",
    "units",
    "uncertainty",
    "configuration_epoch_id",
    "review",
}
_ARTIFACT_CLASSES = {
    "CAMERA_ORIGINAL",
    "INSTALLATION_ORIGINAL",
    "CALIBRATION_ORIGINAL",
    "WORKCELL_ORIGINAL",
    "DEVICE_ORIGINAL",
    "TOOL_ORIGINAL",
    "CAMPAIGN_ORIGINAL",
    "EVALUATION_ORIGINAL",
}
_UNITS = {"px", "mm", "rad"}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema",
    "status",
    "evidence_root",
    "arrival_kit_sha256",
    "sidecar_schema_sha256",
    "required_slot_count",
    "valid_slot_count",
    "configuration_epoch_ids",
    "global_blockers",
    "slots",
    "ready_for_offline_qualification_review",
    "configuration_epoch_advanced",
    "deployment_registry_updated",
    "qualification_installed",
    "camera_opened",
    "controller_started",
    "hardware_writes",
    "physical_movements",
    "physical_authority",
    "preflight_sha256",
}
_SLOT_REPORT_FIELDS = {
    "artifact_id",
    "sidecar_relative_path",
    "status",
    "blockers",
    "sidecar_sha256",
    "source_relative_path",
    "source_sha256",
    "configuration_epoch_id",
    "review_disposition",
}
_SLOT_BLOCKERS = {
    "SIDECAR_MISSING",
    "SIDECAR_UNSAFE",
    "SIDECAR_INVALID_JSON",
    "SIDECAR_TOO_LARGE",
    "SIDECAR_SCHEMA_INVALID",
    "ARTIFACT_ID_MISMATCH",
    "ARTIFACT_CLASS_MISMATCH",
    "UNITS_MISMATCH",
    "SOURCE_PATH_UNSAFE",
    "SOURCE_MISSING_OR_UNSAFE",
    "SOURCE_READ_FAILED",
    "SOURCE_SIZE_MISMATCH",
    "SOURCE_HASH_MISMATCH",
    "SOURCE_PATH_INVALID",
    "REVIEW_NOT_ACCEPTED",
}


class CameraArrivalEvidencePreflightV1Error(ValueError):
    """The requested evidence root or repository schema is unsafe."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CameraArrivalEvidencePreflightV1Error(
                f"duplicate JSON member in sidecar: {key}"
            )
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _root(path: Path, *, label: str) -> Path:
    candidate = path.resolve()
    if path.is_symlink() or not candidate.is_dir():
        raise CameraArrivalEvidencePreflightV1Error(
            f"{label} must be an existing non-symlink directory"
        )
    return candidate


def _contained_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if root not in candidate.parents or candidate == root:
        raise CameraArrivalEvidencePreflightV1Error(
            "evidence path escapes the external evidence root"
        )
    return candidate


def _timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _sidecar_contract_valid(document: object) -> bool:
    if not isinstance(document, Mapping) or set(document) != _SIDECAR_FIELDS:
        return False
    source_relative = document.get("source_relative_path")
    units = document.get("units")
    review = document.get("review")
    uncertainty = document.get("uncertainty")
    size = document.get("source_size_bytes")
    if (
        document.get("schema") != "rocell.camera_arrival_original.v1"
        or not isinstance(document.get("artifact_id"), str)
        or not 1 <= len(document["artifact_id"]) <= 128
        or document.get("artifact_class") not in _ARTIFACT_CLASSES
        or not _timestamp(document.get("captured_at_utc"))
        or not isinstance(source_relative, str)
        or not 1 <= len(source_relative) <= 512
        or Path(source_relative).is_absolute()
        or ".." in source_relative
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 1 <= size <= 10_737_418_240
        or not _hash(document.get("source_sha256"))
        or not isinstance(units, list)
        or len(units) > 3
        or len(set(units)) != len(units)
        or any(unit not in _UNITS for unit in units)
        or not isinstance(document.get("configuration_epoch_id"), str)
        or not 1 <= len(document["configuration_epoch_id"]) <= 128
        or not isinstance(review, Mapping)
        or set(review)
        != {"reviewer_id", "reviewed_at_utc", "disposition", "review_sha256"}
        or not isinstance(review.get("reviewer_id"), str)
        or not 1 <= len(review["reviewer_id"]) <= 128
        or not _timestamp(review.get("reviewed_at_utc"))
        or review.get("disposition") not in {"ACCEPTED", "REJECTED"}
        or not _hash(review.get("review_sha256"))
    ):
        return False
    requires_uncertainty = document["artifact_class"] in {
        "CALIBRATION_ORIGINAL",
        "WORKCELL_ORIGINAL",
        "DEVICE_ORIGINAL",
        "TOOL_ORIGINAL",
        "EVALUATION_ORIGINAL",
    }
    if uncertainty is None:
        return not requires_uncertainty
    if not isinstance(uncertainty, Mapping) or set(uncertainty) != {
        "value",
        "unit",
        "method",
        "evidence_sha256",
    }:
        return False
    value = uncertainty.get("value")
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
        and uncertainty.get("unit") in _UNITS
        and isinstance(uncertainty.get("method"), str)
        and 1 <= len(uncertainty["method"]) <= 256
        and _hash(uncertainty.get("evidence_sha256"))
    )


def _slot_result(slot: Mapping[str, Any], evidence_root: Path) -> dict[str, Any]:
    artifact_id = str(slot["artifact_id"])
    sidecar_relative = str(slot["destination_relative_to_external_evidence_root"])
    result: dict[str, Any] = {
        "artifact_id": artifact_id,
        "sidecar_relative_path": sidecar_relative,
        "status": "MISSING",
        "blockers": ["SIDECAR_MISSING"],
        "sidecar_sha256": None,
        "source_relative_path": None,
        "source_sha256": None,
        "configuration_epoch_id": None,
        "review_disposition": None,
    }
    sidecar = _contained_file(evidence_root, sidecar_relative)
    if not sidecar.exists():
        return result
    if sidecar.is_symlink() or not sidecar.is_file():
        return {**result, "status": "INVALID", "blockers": ["SIDECAR_UNSAFE"]}
    try:
        if not 1 <= sidecar.stat().st_size <= MAX_SIDECAR_BYTES:
            return {
                **result, "status": "INVALID", "blockers": ["SIDECAR_TOO_LARGE"]
            }
        sidecar_bytes = sidecar.read_bytes()
        document = json.loads(
            sidecar_bytes.decode("utf-8"), object_pairs_hook=_strict_object
        )
    except (
        OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError,
        CameraArrivalEvidencePreflightV1Error,
    ):
        return {**result, "status": "INVALID", "blockers": ["SIDECAR_INVALID_JSON"]}

    blockers: list[str] = []
    if not _sidecar_contract_valid(document):
        blockers.append("SIDECAR_SCHEMA_INVALID")
    if not isinstance(document, Mapping):
        return {
            **result,
            "status": "INVALID",
            "blockers": blockers or ["SIDECAR_SCHEMA_INVALID"],
            "sidecar_sha256": _sha256_bytes(sidecar_bytes),
        }
    if document.get("artifact_id") != artifact_id:
        blockers.append("ARTIFACT_ID_MISMATCH")
    if document.get("artifact_class") != slot["artifact_class"]:
        blockers.append("ARTIFACT_CLASS_MISMATCH")
    if document.get("units") != slot["required_units"]:
        blockers.append("UNITS_MISMATCH")

    source_relative = document.get("source_relative_path")
    source_hash = document.get("source_sha256")
    if isinstance(source_relative, str):
        try:
            source = _contained_file(evidence_root, source_relative)
        except CameraArrivalEvidencePreflightV1Error:
            blockers.append("SOURCE_PATH_UNSAFE")
        else:
            if source.is_symlink() or not source.is_file():
                blockers.append("SOURCE_MISSING_OR_UNSAFE")
            else:
                try:
                    source_bytes = source.read_bytes()
                except OSError:
                    blockers.append("SOURCE_READ_FAILED")
                else:
                    if len(source_bytes) != document.get("source_size_bytes"):
                        blockers.append("SOURCE_SIZE_MISMATCH")
                    if _sha256_bytes(source_bytes) != source_hash:
                        blockers.append("SOURCE_HASH_MISMATCH")
    else:
        blockers.append("SOURCE_PATH_INVALID")

    review = document.get("review")
    review_disposition = (
        review.get("disposition") if isinstance(review, Mapping) else None
    )
    if review_disposition != "ACCEPTED":
        blockers.append("REVIEW_NOT_ACCEPTED")
    blockers = list(dict.fromkeys(blockers))
    return {
        **result,
        "status": "VALID" if not blockers else "INVALID",
        "blockers": blockers,
        "sidecar_sha256": _sha256_bytes(sidecar_bytes),
        "source_relative_path": source_relative,
        "source_sha256": source_hash,
        "configuration_epoch_id": document.get("configuration_epoch_id"),
        "review_disposition": review_disposition,
    }


def inspect_camera_arrival_evidence_v1(
    workspace: Path, evidence_root: Path
) -> dict[str, Any]:
    """Return a deterministic, zero-write inventory of the 15 arrival slots."""

    repository = _root(workspace, label="workspace")
    external = _root(evidence_root, label="external evidence root")
    schema_path = repository / (
        "software/ai/schemas/camera_arrival_original_v1.schema.json"
    )
    if schema_path.is_symlink() or not schema_path.is_file():
        raise CameraArrivalEvidencePreflightV1Error(
            "camera arrival sidecar schema is unavailable"
        )
    schema_bytes = schema_path.read_bytes()
    try:
        schema = json.loads(schema_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CameraArrivalEvidencePreflightV1Error(
            "camera arrival sidecar schema is invalid JSON"
        ) from exc
    kit = build_camera_arrival_kit_v1()
    slots = [_slot_result(slot, external) for slot in kit["slots"]]
    valid_count = sum(slot["status"] == "VALID" for slot in slots)
    epochs = sorted(
        {
            str(slot["configuration_epoch_id"])
            for slot in slots
            if slot["status"] == "VALID" and slot["configuration_epoch_id"]
        }
    )
    global_blockers: list[str] = []
    if valid_count != len(slots):
        global_blockers.append("REQUIRED_ORIGINALS_INCOMPLETE")
    if len(epochs) > 1:
        global_blockers.append("CONFIGURATION_EPOCH_MISMATCH")
    ready = not global_blockers and len(epochs) == 1
    core = {
        "schema": SCHEMA,
        "status": READY_STATUS if ready else BLOCKED_STATUS,
        "evidence_root": str(external),
        "arrival_kit_sha256": kit["arrival_kit_sha256"],
        "sidecar_schema_sha256": _sha256_bytes(schema_bytes),
        "required_slot_count": len(slots),
        "valid_slot_count": valid_count,
        "configuration_epoch_ids": epochs,
        "global_blockers": global_blockers,
        "slots": slots,
        "ready_for_offline_qualification_review": ready,
        "configuration_epoch_advanced": False,
        "deployment_registry_updated": False,
        "qualification_installed": False,
        "camera_opened": False,
        "controller_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "preflight_sha256": _sha256_bytes(_canonical(core))}


def parse_camera_arrival_evidence_preflight_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Verify a report before a downstream offline consumer trusts its fields."""

    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise CameraArrivalEvidencePreflightV1Error(
            "preflight report fields differ from the v1 contract"
        )
    unsigned = dict(value)
    digest = unsigned.pop("preflight_sha256")
    if not _hash(digest) or _sha256_bytes(_canonical(unsigned)) != digest:
        raise CameraArrivalEvidencePreflightV1Error(
            "preflight report hash does not match its content"
        )
    slots = value.get("slots")
    if not isinstance(slots, list) or len(slots) != 15:
        raise CameraArrivalEvidencePreflightV1Error(
            "preflight report must contain 15 slots"
        )
    expected_slots = build_camera_arrival_kit_v1()["slots"]
    expected_ids = [slot["artifact_id"] for slot in expected_slots]
    actual_ids = [
        slot.get("artifact_id") if isinstance(slot, Mapping) else None for slot in slots
    ]
    if actual_ids != expected_ids:
        raise CameraArrivalEvidencePreflightV1Error(
            "preflight slot order or identity differs from the arrival kit"
        )
    for slot, expected in zip(slots, expected_slots):
        if not isinstance(slot, Mapping) or set(slot) != _SLOT_REPORT_FIELDS:
            raise CameraArrivalEvidencePreflightV1Error(
                "preflight slot fields differ from the v1 contract"
            )
        status = slot.get("status")
        slot_blockers = slot.get("blockers")
        if (
            slot.get("sidecar_relative_path")
            != expected["destination_relative_to_external_evidence_root"]
            or status not in {"MISSING", "INVALID", "VALID"}
            or not isinstance(slot_blockers, list)
            or len(slot_blockers) != len(set(slot_blockers))
            or any(blocker not in _SLOT_BLOCKERS for blocker in slot_blockers)
            or not (
                slot.get("sidecar_sha256") is None or _hash(slot.get("sidecar_sha256"))
            )
            or not (
                slot.get("source_sha256") is None or _hash(slot.get("source_sha256"))
            )
            or slot.get("review_disposition") not in {None, "ACCEPTED", "REJECTED"}
        ):
            raise CameraArrivalEvidencePreflightV1Error(
                "preflight slot semantics are inconsistent"
            )
        if status == "VALID" and (
            slot_blockers
            or slot.get("sidecar_sha256") is None
            or slot.get("source_sha256") is None
            or not isinstance(slot.get("source_relative_path"), str)
            or not isinstance(slot.get("configuration_epoch_id"), str)
            or slot.get("review_disposition") != "ACCEPTED"
        ):
            raise CameraArrivalEvidencePreflightV1Error(
                "valid preflight slot is not fully bound"
            )
        if status == "MISSING" and slot_blockers != ["SIDECAR_MISSING"]:
            raise CameraArrivalEvidencePreflightV1Error(
                "missing preflight slot has inconsistent blockers"
            )
    valid_count = sum(
        isinstance(slot, Mapping) and slot.get("status") == "VALID" for slot in slots
    )
    ready = value.get("ready_for_offline_qualification_review") is True
    epochs = value.get("configuration_epoch_ids")
    blockers = value.get("global_blockers")
    if (
        value.get("schema") != SCHEMA
        or value.get("required_slot_count") != 15
        or value.get("valid_slot_count") != valid_count
        or not isinstance(epochs, list)
        or not isinstance(blockers, list)
        or ready != (valid_count == 15 and len(epochs) == 1 and not blockers)
        or value.get("status") != (READY_STATUS if ready else BLOCKED_STATUS)
        or any(
            value.get(field) is not False
            for field in (
                "configuration_epoch_advanced",
                "deployment_registry_updated",
                "qualification_installed",
                "camera_opened",
                "controller_started",
                "physical_authority",
            )
        )
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise CameraArrivalEvidencePreflightV1Error(
            "preflight report semantics are inconsistent"
        )
    return MappingProxyType(dict(value))


def main(argv: Sequence[str] | None = None) -> int:
    """Installed, read-only command entry point."""

    parser = argparse.ArgumentParser(
        description="Inspect final-camera arrival evidence without device access."
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_camera_arrival_evidence_v1(args.workspace, args.evidence_root)
    except CameraArrivalEvidencePreflightV1Error as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready_for_offline_qualification_review"] else 2


__all__ = [
    "BLOCKED_STATUS",
    "MAX_SIDECAR_BYTES",
    "READY_STATUS",
    "SCHEMA",
    "CameraArrivalEvidencePreflightV1Error",
    "inspect_camera_arrival_evidence_v1",
    "main",
    "parse_camera_arrival_evidence_preflight_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
