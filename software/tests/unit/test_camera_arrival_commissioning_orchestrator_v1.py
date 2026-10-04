from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from rocell.application.camera_arrival_commissioning_orchestrator_v1 import (
    AWAITING_STATUS, BLOCKED_STATUS, COMPLETE_STATUS,
    VALIDATION_BLOCKED_STATUS, CameraArrivalCommissioningOrchestratorV1Error,
    parse_camera_arrival_commissioning_orchestrator_v1,
    run_camera_arrival_commissioning_orchestrator_v1,
)
from rocell.application.camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
)
from rocell.application.camera_arrival_consumer_validation_v1 import RECEIPT_SCHEMA
from rocell.application.camera_arrival_kit_v1 import build_camera_arrival_kit_v1


ROOT = Path(__file__).resolve().parents[3]
H = "a" * 64
VALIDATOR = Draft202012Validator(json.loads(
    (ROOT / "software/ai/schemas/camera_arrival_commissioning_orchestrator_v1.schema.json").read_text()
))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _populate(root: Path) -> None:
    for slot in build_camera_arrival_kit_v1()["slots"]:
        relative = f"sources/{slot['artifact_id']}.bin"
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        payload = slot["artifact_id"].encode()
        source.write_bytes(payload)
        uncertainty = None if not slot["uncertainty_required"] else {
            "value": 0.1, "unit": slot["required_units"][0],
            "method": "fixture bound", "evidence_sha256": H,
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
            "configuration_epoch_id": "camera-epoch-001",
            "review": {
                "reviewer_id": "owner-ai-review",
                "reviewed_at_utc": "2026-09-29T13:00:00Z",
                "disposition": "ACCEPTED", "review_sha256": H,
            },
        }), encoding="utf-8")


def _receipt(handoff: dict, route: dict, *, status: str = "PASS") -> dict:
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
        "validator_id": "fixture-consumer-validator",
        "validator_version_sha256": H,
        "validated_at_utc": "2026-09-29T14:00:00Z",
        "validation_status": status,
        "blockers": [] if status == "PASS" else ["FIXTURE_REJECTED"],
        "output_sha256": H, "consumer_invoked": True,
        "camera_opened": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
        "qualification_installed": False,
        "physical_admission_ready": False, "physical_authority": False,
    }
    return {**core, "receipt_sha256": hashlib.sha256(_canonical(core)).hexdigest()}


def _write_receipts(evidence: Path, receipts: Path, *, blocked: int | None = None) -> None:
    receipts.mkdir()
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, evidence)
    for index, route in enumerate(handoff["routes"]):
        value = _receipt(
            handoff, route, status="BLOCKED" if index == blocked else "PASS"
        )
        (receipts / f"{route['artifact_id']}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )


def _assert_report(report: dict) -> None:
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(parse_camera_arrival_commissioning_orchestrator_v1(report)) == report
    assert report["camera_opened"] is report["transport_opened"] is False
    assert report["controller_started"] is report["physical_authority"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0


def test_empty_arrival_root_blocks_without_hardware(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    report = run_camera_arrival_commissioning_orchestrator_v1(ROOT, evidence)
    _assert_report(report)
    assert report["status"] == BLOCKED_STATUS
    assert report["assessment"]["blocked_count"] == 15
    assert report["complete_for_offline_review"] is False


def test_complete_evidence_without_receipts_awaits_validation(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _populate(evidence)
    first = run_camera_arrival_commissioning_orchestrator_v1(ROOT, evidence)
    second = run_camera_arrival_commissioning_orchestrator_v1(ROOT, evidence)
    _assert_report(first)
    assert first == second
    assert first["status"] == AWAITING_STATUS
    assert first["assessment"]["pending_count"] == 15


def test_all_receipts_complete_only_offline_review(tmp_path: Path):
    evidence = tmp_path / "evidence"
    receipts = tmp_path / "receipts"
    evidence.mkdir()
    _populate(evidence)
    _write_receipts(evidence, receipts)
    report = run_camera_arrival_commissioning_orchestrator_v1(
        ROOT, evidence, receipts
    )
    _assert_report(report)
    assert report["status"] == COMPLETE_STATUS
    assert report["assessment"]["pass_count"] == 15
    assert len(report["receipt_files"]) == 15
    assert report["complete_for_offline_review"] is True
    assert report["qualification_installed"] is False


def test_blocked_consumer_is_explicit_and_cannot_complete(tmp_path: Path):
    evidence = tmp_path / "evidence"
    receipts = tmp_path / "receipts"
    evidence.mkdir()
    _populate(evidence)
    _write_receipts(evidence, receipts, blocked=4)
    report = run_camera_arrival_commissioning_orchestrator_v1(
        ROOT, evidence, receipts
    )
    _assert_report(report)
    assert report["status"] == VALIDATION_BLOCKED_STATUS
    assert report["assessment"]["pass_count"] == 14
    assert report["assessment"]["blocked_count"] == 1


@pytest.mark.parametrize("mutation", ("unexpected", "symlink", "duplicate_json", "crossed_name"))
def test_receipt_root_fails_closed(tmp_path: Path, mutation: str):
    evidence = tmp_path / "evidence"
    receipts = tmp_path / "receipts"
    evidence.mkdir()
    _populate(evidence)
    _write_receipts(evidence, receipts)
    first = next(iter(receipts.iterdir()))
    if mutation == "unexpected":
        (receipts / "notes.txt").write_text("unexpected", encoding="utf-8")
    elif mutation == "symlink":
        first.unlink()
        try:
            first.symlink_to(receipts / "missing.json")
        except OSError:
            pytest.skip("symlink creation unavailable")
    elif mutation == "duplicate_json":
        first.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    else:
        value = json.loads(first.read_text(encoding="utf-8"))
        value["artifact_id"] = "camera_identity"
        core = {key: item for key, item in value.items() if key != "receipt_sha256"}
        value["receipt_sha256"] = hashlib.sha256(_canonical(core)).hexdigest()
        first.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CameraArrivalCommissioningOrchestratorV1Error):
        run_camera_arrival_commissioning_orchestrator_v1(ROOT, evidence, receipts)


def test_outer_mutation_is_rejected(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    report = run_camera_arrival_commissioning_orchestrator_v1(ROOT, evidence)
    report["physical_authority"] = True
    core = {key: value for key, value in report.items() if key != "orchestrator_sha256"}
    report["orchestrator_sha256"] = hashlib.sha256(_canonical(core)).hexdigest()
    with pytest.raises(CameraArrivalCommissioningOrchestratorV1Error):
        parse_camera_arrival_commissioning_orchestrator_v1(report)
