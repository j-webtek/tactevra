"""Reproducible synthetic fault campaign for camera-arrival commissioning."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .camera_arrival_commissioning_orchestrator_v1 import (
    CameraArrivalCommissioningOrchestratorV1Error,
    run_camera_arrival_commissioning_orchestrator_v1,
)
from .camera_arrival_consumer_handoff_v1 import build_camera_arrival_consumer_handoff_v1
from .camera_arrival_consumer_validation_v1 import RECEIPT_SCHEMA
from .camera_arrival_kit_v1 import build_camera_arrival_kit_v1


SCHEMA = "rocell.camera_arrival_fault_campaign.v1"
CAMPAIGN_ID = "PC12_SYNTHETIC_CAMERA_ARRIVAL_FAULTS_V1"
H = "a" * 64
CASE_EXPECTATIONS = MappingProxyType({
    "EMPTY_EVIDENCE": ("BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE", "REQUIRED_ORIGINALS_INCOMPLETE"),
    "COMPLETE_NO_RECEIPTS": ("AWAITING_CONSUMER_VALIDATION", "RECEIPTS_PENDING"),
    "ALL_RECEIPTS_PASS": ("COMPLETE_FOR_OFFLINE_REVIEW", "ALL_EXACT_RECEIPTS_PASS"),
    "ONE_RECEIPT_BLOCKED": ("CONSUMER_VALIDATION_BLOCKED", "CONSUMER_BLOCKER_RETAINED"),
    "ONE_RECEIPT_MISSING": ("AWAITING_CONSUMER_VALIDATION", "ONE_RECEIPT_PENDING"),
    "SOURCE_HASH_MISMATCH": ("BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE", "SOURCE_HASH_MISMATCH"),
    "REVIEW_REJECTED": ("BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE", "REVIEW_NOT_ACCEPTED"),
    "MIXED_CONFIGURATION_EPOCH": ("BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE", "CONFIGURATION_EPOCH_MISMATCH"),
    "SIDECAR_MISSING": ("BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE", "SIDECAR_MISSING"),
    "SIDECAR_DUPLICATE_MEMBER": ("BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE", "SIDECAR_INVALID_JSON"),
    "SIDECAR_OVERSIZED": ("BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE", "SIDECAR_TOO_LARGE"),
    "RECEIPT_UNEXPECTED_ENTRY": ("REJECTED_INPUT", "UNEXPECTED_RECEIPT_ENTRY"),
    "RECEIPT_UNSAFE_ENTRY": ("REJECTED_INPUT", "UNSAFE_RECEIPT_ENTRY"),
    "RECEIPT_DUPLICATE_MEMBER": ("REJECTED_INPUT", "DUPLICATE_RECEIPT_MEMBER"),
    "RECEIPT_CROSSED_FILENAME": ("REJECTED_INPUT", "RECEIPT_FILENAME_IDENTITY_DIFFERS"),
    "RECEIPT_AUTHORITY_CLAIM": ("REJECTED_INPUT", "RECEIPT_CONTRACT_REJECTED"),
    "RECEIPT_OVERSIZED": ("REJECTED_INPUT", "RECEIPT_SIZE_OUTSIDE_BOUND"),
    "RECEIPT_TRUNCATED": ("REJECTED_INPUT", "RECEIPT_NOT_STRICT_JSON"),
})
_REPORT_FIELDS = {
    "schema", "campaign_id", "evidence_class", "case_count", "pass_count",
    "failure_count", "observations", "all_cases_passed", "camera_opened",
    "transport_opened", "controller_started", "controller_commands",
    "hardware_writes", "physical_movements", "physical_authority",
    "campaign_sha256",
}
_OBSERVATION_FIELDS = {
    "case_id", "expected_outcome", "observed_outcome", "expected_detail",
    "observed_detail", "passed",
}


class CameraArrivalFaultCampaignV1Error(ValueError):
    """The synthetic campaign or its retained report is inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _populate(root: Path) -> None:
    for slot in build_camera_arrival_kit_v1()["slots"]:
        relative = f"sources/{slot['artifact_id']}.bin"
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        payload = slot["artifact_id"].encode()
        source.write_bytes(payload)
        uncertainty = None if not slot["uncertainty_required"] else {
            "value": 0.1, "unit": slot["required_units"][0],
            "method": "synthetic fault-campaign bound", "evidence_sha256": H,
        }
        sidecar = root / slot["destination_relative_to_external_evidence_root"]
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps({
            "schema": "rocell.camera_arrival_original.v1",
            "artifact_id": slot["artifact_id"],
            "artifact_class": slot["artifact_class"],
            "captured_at_utc": "2026-09-29T12:00:00Z",
            "source_relative_path": relative,
            "source_size_bytes": len(payload),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "units": slot["required_units"], "uncertainty": uncertainty,
            "configuration_epoch_id": "synthetic-camera-epoch-001",
            "review": {
                "reviewer_id": "synthetic-campaign",
                "reviewed_at_utc": "2026-09-29T13:00:00Z",
                "disposition": "ACCEPTED", "review_sha256": H,
            },
        }), encoding="utf-8")


def _receipt(handoff: Mapping[str, Any], route: Mapping[str, Any], status: str) -> dict[str, Any]:
    core = {
        "schema": RECEIPT_SCHEMA, "artifact_id": route["artifact_id"],
        "handoff_sha256": handoff["handoff_sha256"],
        "preflight_sha256": handoff["preflight_sha256"],
        "consumer_map_sha256": handoff["consumer_map_sha256"],
        "sidecar_sha256": route["sidecar_sha256"],
        "source_sha256": route["source_sha256"],
        "consumer_source": route["consumer_source"],
        "consumer_source_sha256": route["consumer_source_sha256"],
        "downstream_schema": route["downstream_schema"],
        "downstream_schema_sha256": route["downstream_schema_sha256"],
        "consumer_binding": route["consumer_binding"],
        "validator_id": "synthetic-fault-campaign",
        "validator_version_sha256": H,
        "validated_at_utc": "2026-09-29T14:00:00Z",
        "validation_status": status,
        "blockers": [] if status == "PASS" else ["SYNTHETIC_EXPECTED_BLOCKER"],
        "output_sha256": H, "consumer_invoked": True,
        "camera_opened": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
        "qualification_installed": False,
        "physical_admission_ready": False, "physical_authority": False,
    }
    return {**core, "receipt_sha256": _digest(core)}


def _write_receipts(
    workspace: Path, evidence: Path, receipts: Path, *, blocked: int | None = None
) -> None:
    receipts.mkdir()
    handoff = build_camera_arrival_consumer_handoff_v1(workspace, evidence)
    for index, route in enumerate(handoff["routes"]):
        status = "BLOCKED" if index == blocked else "PASS"
        value = _receipt(handoff, route, status)
        (receipts / f"{route['artifact_id']}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )


def _sidecar(evidence: Path, index: int = 0) -> Path:
    slot = build_camera_arrival_kit_v1()["slots"][index]
    return evidence / slot["destination_relative_to_external_evidence_root"]


def _status_detail(report: Mapping[str, Any], case_id: str) -> tuple[str, str]:
    if case_id == "COMPLETE_NO_RECEIPTS":
        detail = "RECEIPTS_PENDING"
    elif case_id == "ALL_RECEIPTS_PASS":
        detail = "ALL_EXACT_RECEIPTS_PASS"
    elif case_id == "ONE_RECEIPT_BLOCKED":
        detail = "CONSUMER_BLOCKER_RETAINED"
    elif case_id == "ONE_RECEIPT_MISSING":
        detail = "ONE_RECEIPT_PENDING"
    else:
        blockers = list(report["preflight"]["global_blockers"])
        blockers.extend(
            blocker
            for slot in report["preflight"]["slots"]
            for blocker in slot["blockers"]
        )
        expected_detail = CASE_EXPECTATIONS[case_id][1]
        detail = expected_detail if expected_detail in blockers else "UNEXPECTED_BLOCKER"
    return str(report["status"]), detail


def _rejection_detail(case_id: str, message: str) -> str:
    checks = {
        "RECEIPT_UNEXPECTED_ENTRY": "unexpected receipt-root entry",
        "RECEIPT_UNSAFE_ENTRY": "regular non-symlink file",
        "RECEIPT_DUPLICATE_MEMBER": "duplicate JSON member",
        "RECEIPT_CROSSED_FILENAME": "receipt filename identity differs",
        "RECEIPT_AUTHORITY_CLAIM": "receipt contract rejected",
        "RECEIPT_OVERSIZED": "receipt size is outside",
        "RECEIPT_TRUNCATED": "not strict UTF-8 JSON",
    }
    return CASE_EXPECTATIONS[case_id][1] if checks[case_id] in message else "UNEXPECTED_REJECTION"


def _run_case(workspace: Path, case_id: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="rocell-pc12-") as raw:
        root = Path(raw)
        evidence = root / "evidence"
        receipts = root / "receipts"
        evidence.mkdir()
        if case_id != "EMPTY_EVIDENCE":
            _populate(evidence)

        if case_id in {
            "ALL_RECEIPTS_PASS", "ONE_RECEIPT_BLOCKED", "ONE_RECEIPT_MISSING",
            "RECEIPT_UNEXPECTED_ENTRY", "RECEIPT_UNSAFE_ENTRY",
            "RECEIPT_DUPLICATE_MEMBER", "RECEIPT_CROSSED_FILENAME",
            "RECEIPT_AUTHORITY_CLAIM", "RECEIPT_OVERSIZED", "RECEIPT_TRUNCATED",
        }:
            _write_receipts(
                workspace, evidence, receipts,
                blocked=3 if case_id == "ONE_RECEIPT_BLOCKED" else None,
            )

        if case_id == "ONE_RECEIPT_MISSING":
            next(iter(receipts.iterdir())).unlink()
        elif case_id == "SOURCE_HASH_MISMATCH":
            source = evidence / "sources" / "camera_receipt.bin"
            source.write_bytes(source.read_bytes() + b"mutated")
        elif case_id == "REVIEW_REJECTED":
            path = _sidecar(evidence)
            value = json.loads(path.read_text())
            value["review"]["disposition"] = "REJECTED"
            path.write_text(json.dumps(value), encoding="utf-8")
        elif case_id == "MIXED_CONFIGURATION_EPOCH":
            path = _sidecar(evidence, 1)
            value = json.loads(path.read_text())
            value["configuration_epoch_id"] = "synthetic-camera-epoch-002"
            path.write_text(json.dumps(value), encoding="utf-8")
        elif case_id == "SIDECAR_MISSING":
            _sidecar(evidence).unlink()
        elif case_id == "SIDECAR_DUPLICATE_MEMBER":
            _sidecar(evidence).write_text(
                '{"schema":"rocell.camera_arrival_original.v1","schema":"duplicate"}',
                encoding="utf-8",
            )
        elif case_id == "SIDECAR_OVERSIZED":
            _sidecar(evidence).write_bytes(b" " * 1_048_577)
        elif case_id == "RECEIPT_UNEXPECTED_ENTRY":
            (receipts / "notes.txt").write_text("unexpected", encoding="utf-8")
        elif case_id == "RECEIPT_UNSAFE_ENTRY":
            path = next(iter(receipts.iterdir()))
            path.unlink()
            path.mkdir()
        elif case_id in {
            "RECEIPT_DUPLICATE_MEMBER", "RECEIPT_CROSSED_FILENAME",
            "RECEIPT_AUTHORITY_CLAIM", "RECEIPT_OVERSIZED", "RECEIPT_TRUNCATED",
        }:
            path = next(iter(receipts.iterdir()))
            if case_id == "RECEIPT_DUPLICATE_MEMBER":
                path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            elif case_id == "RECEIPT_OVERSIZED":
                path.write_bytes(b" " * 262_145)
            elif case_id == "RECEIPT_TRUNCATED":
                path.write_text('{"schema":', encoding="utf-8")
            else:
                value = json.loads(path.read_text())
                if case_id == "RECEIPT_CROSSED_FILENAME":
                    value["artifact_id"] = "camera_identity"
                else:
                    value["physical_authority"] = True
                core = {k: v for k, v in value.items() if k != "receipt_sha256"}
                value["receipt_sha256"] = _digest(core)
                path.write_text(json.dumps(value), encoding="utf-8")

        try:
            report = run_camera_arrival_commissioning_orchestrator_v1(
                workspace, evidence, receipts if receipts.exists() else None
            )
        except CameraArrivalCommissioningOrchestratorV1Error as exc:
            return "REJECTED_INPUT", _rejection_detail(case_id, str(exc))
        return _status_detail(report, case_id)


def run_camera_arrival_fault_campaign_v1(workspace: Path) -> dict[str, Any]:
    """Run every frozen synthetic case through the actual PC11 boundary."""

    observations = []
    for case_id, (expected_outcome, expected_detail) in CASE_EXPECTATIONS.items():
        observed_outcome, observed_detail = _run_case(workspace.resolve(), case_id)
        observations.append({
            "case_id": case_id, "expected_outcome": expected_outcome,
            "observed_outcome": observed_outcome,
            "expected_detail": expected_detail, "observed_detail": observed_detail,
            "passed": (
                expected_outcome == observed_outcome
                and expected_detail == observed_detail
            ),
        })
    passed = sum(item["passed"] for item in observations)
    core = {
        "schema": SCHEMA, "campaign_id": CAMPAIGN_ID,
        "evidence_class": "SYNTHETIC_OFFLINE", "case_count": len(observations),
        "pass_count": passed, "failure_count": len(observations) - passed,
        "observations": observations, "all_cases_passed": passed == len(observations),
        "camera_opened": False, "transport_opened": False,
        "controller_started": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _digest(core)}


def parse_camera_arrival_fault_campaign_v1(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise CameraArrivalFaultCampaignV1Error("campaign fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("campaign_sha256")
    if not isinstance(digest, str) or _digest(unsigned) != digest:
        raise CameraArrivalFaultCampaignV1Error("campaign hash mismatch")
    observations = value.get("observations")
    if not isinstance(observations, list) or len(observations) != len(CASE_EXPECTATIONS):
        raise CameraArrivalFaultCampaignV1Error("campaign case count differs")
    for row, (case_id, expected) in zip(observations, CASE_EXPECTATIONS.items()):
        if (
            not isinstance(row, Mapping) or set(row) != _OBSERVATION_FIELDS
            or row.get("case_id") != case_id
            or (row.get("expected_outcome"), row.get("expected_detail")) != expected
            or row.get("passed") is not (
                row.get("observed_outcome") == expected[0]
                and row.get("observed_detail") == expected[1]
            )
        ):
            raise CameraArrivalFaultCampaignV1Error("campaign observation differs")
    passed = sum(row["passed"] is True for row in observations)
    if (
        value.get("schema") != SCHEMA or value.get("campaign_id") != CAMPAIGN_ID
        or value.get("evidence_class") != "SYNTHETIC_OFFLINE"
        or value.get("case_count") != len(CASE_EXPECTATIONS)
        or value.get("pass_count") != passed
        or value.get("failure_count") != len(CASE_EXPECTATIONS) - passed
        or value.get("all_cases_passed") is not (passed == len(CASE_EXPECTATIONS))
        or any(value.get(field) is not False for field in (
            "camera_opened", "transport_opened", "controller_started",
            "physical_authority",
        ))
        or value.get("controller_commands") != []
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise CameraArrivalFaultCampaignV1Error("campaign semantics differ")
    return MappingProxyType(dict(value))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_camera_arrival_fault_campaign_v1(args.workspace)
        parse_camera_arrival_fault_campaign_v1(report)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_cases_passed"] else 2


__all__ = [
    "CAMPAIGN_ID", "CASE_EXPECTATIONS", "SCHEMA",
    "CameraArrivalFaultCampaignV1Error", "main",
    "parse_camera_arrival_fault_campaign_v1",
    "run_camera_arrival_fault_campaign_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
