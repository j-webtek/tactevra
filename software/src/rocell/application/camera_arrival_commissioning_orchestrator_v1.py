"""One-command, zero-authority camera-arrival commissioning rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
    parse_camera_arrival_consumer_handoff_v1,
)
from .camera_arrival_consumer_validation_v1 import (
    assess_camera_arrival_consumer_validation_v1,
    parse_camera_arrival_consumer_validation_assessment_v1,
    parse_camera_arrival_consumer_validation_receipt_v1,
)
from .camera_arrival_evidence_preflight_v1 import (
    inspect_camera_arrival_evidence_v1,
    parse_camera_arrival_evidence_preflight_v1,
)
from .camera_arrival_kit_v1 import REQUIRED_SLOT_IDS


SCHEMA = "rocell.camera_arrival_commissioning_orchestrator.v1"
BLOCKED_STATUS = "BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE"
AWAITING_STATUS = "AWAITING_CONSUMER_VALIDATION"
VALIDATION_BLOCKED_STATUS = "CONSUMER_VALIDATION_BLOCKED"
COMPLETE_STATUS = "COMPLETE_FOR_OFFLINE_REVIEW"
MAX_RECEIPT_BYTES = 262_144
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema", "status", "evidence_root", "receipt_root", "receipt_files",
    "preflight", "handoff", "assessment", "complete_for_offline_review",
    "configuration_epoch_advanced", "deployment_registry_updated",
    "qualification_installed", "camera_opened", "transport_opened",
    "controller_started", "controller_commands", "hardware_writes",
    "physical_movements", "physical_authority", "orchestrator_sha256",
}
_FILE_FIELDS = {
    "artifact_id", "relative_path", "size_bytes", "file_sha256",
    "receipt_sha256",
}


class CameraArrivalCommissioningOrchestratorV1Error(ValueError):
    """The commissioning inputs or report violate the offline contract."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CameraArrivalCommissioningOrchestratorV1Error(
                f"duplicate JSON member in receipt: {key}"
            )
        result[key] = value
    return result


def _safe_root(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_dir():
        raise CameraArrivalCommissioningOrchestratorV1Error(
            f"{label} must be an existing non-symlink directory"
        )
    return resolved


def load_camera_arrival_consumer_receipts_v1(
    receipt_root: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load canonical receipt files without accepting extra directory content."""

    if receipt_root is None:
        return [], []
    root = _safe_root(receipt_root, label="receipt root")
    allowed = {f"{artifact_id}.json" for artifact_id in REQUIRED_SLOT_IDS}
    entries = sorted(root.iterdir(), key=lambda item: item.name)
    for entry in entries:
        if entry.name not in allowed:
            raise CameraArrivalCommissioningOrchestratorV1Error(
                f"unexpected receipt-root entry: {entry.name}"
            )
        if entry.is_symlink() or not entry.is_file():
            raise CameraArrivalCommissioningOrchestratorV1Error(
                f"receipt entry must be a regular non-symlink file: {entry.name}"
            )

    receipts: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for artifact_id in REQUIRED_SLOT_IDS:
        path = root / f"{artifact_id}.json"
        if not path.exists():
            continue
        size = path.stat().st_size
        if not 1 <= size <= MAX_RECEIPT_BYTES:
            raise CameraArrivalCommissioningOrchestratorV1Error(
                f"receipt size is outside the bounded contract: {artifact_id}"
            )
        raw = path.read_bytes()
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise CameraArrivalCommissioningOrchestratorV1Error(
                f"receipt is not strict UTF-8 JSON: {artifact_id}"
            ) from exc
        try:
            parsed = dict(parse_camera_arrival_consumer_validation_receipt_v1(value))
        except (TypeError, ValueError) as exc:
            raise CameraArrivalCommissioningOrchestratorV1Error(
                f"receipt contract rejected: {artifact_id}: {exc}"
            ) from exc
        if parsed["artifact_id"] != artifact_id:
            raise CameraArrivalCommissioningOrchestratorV1Error(
                f"receipt filename identity differs: {artifact_id}"
            )
        receipts.append(parsed)
        files.append({
            "artifact_id": artifact_id,
            "relative_path": path.name,
            "size_bytes": len(raw),
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "receipt_sha256": parsed["receipt_sha256"],
        })
    return receipts, files


def run_camera_arrival_commissioning_orchestrator_v1(
    workspace: Path, evidence_root: Path, receipt_root: Path | None = None,
) -> dict[str, Any]:
    """Run all currently available read-only commissioning composition stages."""

    workspace_root = _safe_root(workspace, label="workspace")
    evidence = _safe_root(evidence_root, label="evidence root")
    receipts, receipt_files = load_camera_arrival_consumer_receipts_v1(receipt_root)
    preflight = inspect_camera_arrival_evidence_v1(workspace_root, evidence)
    handoff = build_camera_arrival_consumer_handoff_v1(workspace_root, evidence)
    assessment = assess_camera_arrival_consumer_validation_v1(handoff, receipts)

    if preflight["ready_for_offline_qualification_review"] is not True:
        status = BLOCKED_STATUS
    elif assessment["complete_for_offline_review"] is True:
        status = COMPLETE_STATUS
    elif assessment["blocked_count"]:
        status = VALIDATION_BLOCKED_STATUS
    else:
        status = AWAITING_STATUS

    core = {
        "schema": SCHEMA,
        "status": status,
        "evidence_root": str(evidence),
        "receipt_root": None if receipt_root is None else str(receipt_root.resolve()),
        "receipt_files": receipt_files,
        "preflight": preflight,
        "handoff": handoff,
        "assessment": assessment,
        "complete_for_offline_review": status == COMPLETE_STATUS,
        "configuration_epoch_advanced": False,
        "deployment_registry_updated": False,
        "qualification_installed": False,
        "camera_opened": False,
        "transport_opened": False,
        "controller_started": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "orchestrator_sha256": _digest(core)}


def parse_camera_arrival_commissioning_orchestrator_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Fail closed on altered, inconsistent, or authority-bearing reports."""

    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise CameraArrivalCommissioningOrchestratorV1Error(
            "orchestrator report fields differ from the v1 contract"
        )
    unsigned = dict(value)
    digest = unsigned.pop("orchestrator_sha256")
    if not _is_hash(digest) or _digest(unsigned) != digest:
        raise CameraArrivalCommissioningOrchestratorV1Error(
            "orchestrator report hash mismatch"
        )
    try:
        preflight = parse_camera_arrival_evidence_preflight_v1(value["preflight"])
        handoff = parse_camera_arrival_consumer_handoff_v1(value["handoff"])
        assessment = parse_camera_arrival_consumer_validation_assessment_v1(
            value["assessment"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CameraArrivalCommissioningOrchestratorV1Error(str(exc)) from exc
    if (
        handoff["preflight_sha256"] != preflight["preflight_sha256"]
        or assessment["handoff_sha256"] != handoff["handoff_sha256"]
    ):
        raise CameraArrivalCommissioningOrchestratorV1Error(
            "orchestrator stage lineage differs"
        )
    receipt_files = value.get("receipt_files")
    if not isinstance(receipt_files, list) or len(receipt_files) > 15:
        raise CameraArrivalCommissioningOrchestratorV1Error(
            "orchestrator receipt file list is invalid"
        )
    seen: list[str] = []
    for item in receipt_files:
        if (
            not isinstance(item, Mapping)
            or set(item) != _FILE_FIELDS
            or item.get("artifact_id") not in REQUIRED_SLOT_IDS
            or item.get("artifact_id") in seen
            or item.get("relative_path") != f"{item.get('artifact_id')}.json"
            or not isinstance(item.get("size_bytes"), int)
            or isinstance(item.get("size_bytes"), bool)
            or not 1 <= item["size_bytes"] <= MAX_RECEIPT_BYTES
            or not _is_hash(item.get("file_sha256"))
            or not _is_hash(item.get("receipt_sha256"))
        ):
            raise CameraArrivalCommissioningOrchestratorV1Error(
                "orchestrator receipt file metadata is inconsistent"
            )
        seen.append(str(item["artifact_id"]))
    expected_order = [item for item in REQUIRED_SLOT_IDS if item in set(seen)]
    if seen != expected_order:
        raise CameraArrivalCommissioningOrchestratorV1Error(
            "orchestrator receipt file order differs"
        )
    if len(receipt_files) != assessment["pass_count"] + sum(
        row["status"] == "BLOCKED" for row in assessment["route_results"]
    ):
        raise CameraArrivalCommissioningOrchestratorV1Error(
            "orchestrator receipt count differs from assessment"
        )

    if preflight["ready_for_offline_qualification_review"] is not True:
        expected_status = BLOCKED_STATUS
    elif assessment["complete_for_offline_review"] is True:
        expected_status = COMPLETE_STATUS
    elif assessment["blocked_count"]:
        expected_status = VALIDATION_BLOCKED_STATUS
    else:
        expected_status = AWAITING_STATUS
    if (
        value.get("schema") != SCHEMA
        or value.get("status") != expected_status
        or not isinstance(value.get("evidence_root"), str)
        or not value["evidence_root"]
        or not (
            value.get("receipt_root") is None
            or isinstance(value.get("receipt_root"), str)
            and bool(value["receipt_root"])
        )
        or value.get("complete_for_offline_review")
        is not (expected_status == COMPLETE_STATUS)
        or any(value.get(field) is not False for field in (
            "configuration_epoch_advanced", "deployment_registry_updated",
            "qualification_installed", "camera_opened", "transport_opened",
            "controller_started", "physical_authority",
        ))
        or value.get("controller_commands") != []
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise CameraArrivalCommissioningOrchestratorV1Error(
            "orchestrator report semantics are inconsistent"
        )
    return MappingProxyType(dict(value))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run camera-arrival preflight, handoff, and receipt aggregation "
            "without camera, controller, transport, or movement authority."
        )
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_camera_arrival_commissioning_orchestrator_v1(
            args.workspace, args.evidence_root, args.receipt_root
        )
        parse_camera_arrival_commissioning_orchestrator_v1(report)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["complete_for_offline_review"] else 2


__all__ = [
    "AWAITING_STATUS", "BLOCKED_STATUS", "COMPLETE_STATUS", "MAX_RECEIPT_BYTES",
    "SCHEMA", "VALIDATION_BLOCKED_STATUS",
    "CameraArrivalCommissioningOrchestratorV1Error",
    "load_camera_arrival_consumer_receipts_v1", "main",
    "parse_camera_arrival_commissioning_orchestrator_v1",
    "run_camera_arrival_commissioning_orchestrator_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
