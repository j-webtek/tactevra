from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from rocell.application.camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
)
from rocell.application.camera_arrival_consumer_validation_v1 import (
    AWAITING_STATUS, BLOCKED_STATUS, COMPLETE_STATUS, RECEIPT_SCHEMA,
    CameraArrivalConsumerValidationV1Error,
    assess_camera_arrival_consumer_validation_v1,
    parse_camera_arrival_consumer_validation_assessment_v1,
    parse_camera_arrival_consumer_validation_receipt_v1,
)
from rocell.application.camera_arrival_kit_v1 import build_camera_arrival_kit_v1


ROOT = Path(__file__).resolve().parents[3]
H = "a" * 64
RECEIPT_VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "software/ai/schemas/camera_arrival_consumer_validation_receipt_v1.schema.json").read_text()),
    format_checker=FormatChecker(),
)
ASSESSMENT_VALIDATOR = Draft202012Validator(json.loads(
    (ROOT / "software/ai/schemas/camera_arrival_consumer_validation_assessment_v1.schema.json").read_text()
))


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
        "schema": RECEIPT_SCHEMA,
        "artifact_id": route["artifact_id"],
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
        "output_sha256": H,
        "consumer_invoked": True,
        "camera_opened": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
        "qualification_installed": False, "physical_admission_ready": False,
        "physical_authority": False,
    }
    raw = json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    return {**core, "receipt_sha256": hashlib.sha256(raw).hexdigest()}


def test_blocked_handoff_yields_no_consumer_invocation_claim(tmp_path: Path):
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    report = assess_camera_arrival_consumer_validation_v1(handoff, [])
    assert list(ASSESSMENT_VALIDATOR.iter_errors(report)) == []
    assert dict(parse_camera_arrival_consumer_validation_assessment_v1(report)) == report
    assert report["status"] == BLOCKED_STATUS
    assert report["blocked_count"] == 15
    assert report["pass_count"] == report["pending_count"] == 0
    assert report["complete_for_offline_review"] is False
    assert report["physical_authority"] is False


def test_ready_handoff_without_receipts_remains_pending(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    report = assess_camera_arrival_consumer_validation_v1(handoff, [])
    assert report["status"] == AWAITING_STATUS
    assert report["pending_count"] == 15
    assert report["pass_count"] == report["blocked_count"] == 0


def test_all_exact_pass_receipts_complete_only_offline_review(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    receipts = [_receipt(handoff, route) for route in handoff["routes"]]
    assert all(list(RECEIPT_VALIDATOR.iter_errors(item)) == [] for item in receipts)
    assert all(dict(parse_camera_arrival_consumer_validation_receipt_v1(item)) == item for item in receipts)
    report = assess_camera_arrival_consumer_validation_v1(handoff, receipts)
    assert list(ASSESSMENT_VALIDATOR.iter_errors(report)) == []
    assert dict(parse_camera_arrival_consumer_validation_assessment_v1(report)) == report
    assert report["status"] == COMPLETE_STATUS
    assert report["pass_count"] == 15
    assert report["complete_for_offline_review"] is True
    assert report["qualification_installed"] is False
    assert report["physical_authority"] is False


def test_blocked_receipt_preserves_failure_and_prevents_completion(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    receipts = [_receipt(handoff, route) for route in handoff["routes"]]
    receipts[3] = _receipt(handoff, handoff["routes"][3], status="BLOCKED")
    report = assess_camera_arrival_consumer_validation_v1(handoff, receipts)
    assert report["status"] == AWAITING_STATUS
    assert report["pass_count"] == 14
    assert report["blocked_count"] == 1
    assert report["route_results"][3]["blockers"] == ["FIXTURE_REJECTED"]


@pytest.mark.parametrize("mutation", ("binding", "duplicate", "authority"))
def test_receipt_intake_fails_closed(tmp_path: Path, mutation: str):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    receipt = _receipt(handoff, handoff["routes"][0])
    if mutation == "binding":
        receipt["source_sha256"] = H
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = hashlib.sha256(json.dumps(
            unsigned, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        with pytest.raises(CameraArrivalConsumerValidationV1Error):
            assess_camera_arrival_consumer_validation_v1(handoff, [receipt])
    elif mutation == "duplicate":
        with pytest.raises(CameraArrivalConsumerValidationV1Error):
            assess_camera_arrival_consumer_validation_v1(handoff, [receipt, receipt])
    else:
        receipt["physical_authority"] = True
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = hashlib.sha256(json.dumps(
            unsigned, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        with pytest.raises(CameraArrivalConsumerValidationV1Error):
            parse_camera_arrival_consumer_validation_receipt_v1(receipt)
