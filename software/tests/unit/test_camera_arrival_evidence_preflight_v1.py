from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from rocell.application.camera_arrival_evidence_preflight_v1 import (
    BLOCKED_STATUS,
    READY_STATUS,
    CameraArrivalEvidencePreflightV1Error,
    inspect_camera_arrival_evidence_v1,
    parse_camera_arrival_evidence_preflight_v1,
)
from rocell.application.camera_arrival_kit_v1 import build_camera_arrival_kit_v1


ROOT = Path(__file__).resolve().parents[3]
H = "a" * 64
REPORT_SCHEMA = json.loads(
    (
        ROOT / "software/ai/schemas/camera_arrival_evidence_preflight_v1.schema.json"
    ).read_text(encoding="utf-8")
)
REPORT_VALIDATOR = Draft202012Validator(REPORT_SCHEMA)


def _rehash(document: dict[str, object]) -> None:
    document.pop("preflight_sha256", None)
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    document["preflight_sha256"] = hashlib.sha256(payload).hexdigest()


def _populate(root: Path, *, epoch: str = "camera-epoch-001") -> None:
    for slot in build_camera_arrival_kit_v1()["slots"]:
        source_relative = f"sources/{slot['artifact_id']}.bin"
        source = root / source_relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source_bytes = f"measured-{slot['artifact_id']}".encode("utf-8")
        source.write_bytes(source_bytes)
        uncertainty = None
        if slot["uncertainty_required"]:
            uncertainty = {
                "value": 0.1,
                "unit": slot["required_units"][0],
                "method": "fixture residual bound",
                "evidence_sha256": H,
            }
        document = {
            "schema": "rocell.camera_arrival_original.v1",
            "artifact_id": slot["artifact_id"],
            "artifact_class": slot["artifact_class"],
            "captured_at_utc": "2026-09-28T12:00:00Z",
            "source_relative_path": source_relative,
            "source_size_bytes": len(source_bytes),
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "units": slot["required_units"],
            "uncertainty": uncertainty,
            "configuration_epoch_id": epoch,
            "review": {
                "reviewer_id": "owner-ai-review",
                "reviewed_at_utc": "2026-09-28T13:00:00Z",
                "disposition": "ACCEPTED",
                "review_sha256": H,
            },
        }
        sidecar = root / slot["destination_relative_to_external_evidence_root"]
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(document), encoding="utf-8")


def test_empty_root_reports_all_slots_missing_without_authority(tmp_path: Path):
    report = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    assert list(REPORT_VALIDATOR.iter_errors(report)) == []
    assert dict(parse_camera_arrival_evidence_preflight_v1(report)) == report
    assert report["status"] == BLOCKED_STATUS
    assert report["required_slot_count"] == 15
    assert report["valid_slot_count"] == 0
    assert all(slot["status"] == "MISSING" for slot in report["slots"])
    assert report["global_blockers"] == ["REQUIRED_ORIGINALS_INCOMPLETE"]
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_complete_structural_set_is_ready_only_for_offline_review(tmp_path: Path):
    _populate(tmp_path)
    first = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    second = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    assert first == second
    assert list(REPORT_VALIDATOR.iter_errors(first)) == []
    assert dict(parse_camera_arrival_evidence_preflight_v1(first)) == first
    assert first["status"] == READY_STATUS
    assert first["valid_slot_count"] == 15
    assert first["configuration_epoch_ids"] == ["camera-epoch-001"]
    assert first["ready_for_offline_qualification_review"] is True
    assert first["qualification_installed"] is False
    assert first["camera_opened"] is first["controller_started"] is False


def test_changed_source_bytes_fail_closed(tmp_path: Path):
    _populate(tmp_path)
    (tmp_path / "sources/camera_identity.bin").write_bytes(b"changed")
    report = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    slot = next(
        row for row in report["slots"] if row["artifact_id"] == "camera_identity"
    )
    assert slot["status"] == "INVALID"
    assert "SOURCE_SIZE_MISMATCH" in slot["blockers"]
    assert "SOURCE_HASH_MISMATCH" in slot["blockers"]
    assert report["ready_for_offline_qualification_review"] is False


def test_malformed_sidecar_and_rejected_review_fail_closed(tmp_path: Path):
    _populate(tmp_path)
    malformed = tmp_path / "originals/camera/receipt.json"
    document = json.loads(malformed.read_text(encoding="utf-8"))
    document["unexpected"] = True
    malformed.write_text(json.dumps(document), encoding="utf-8")
    rejected = tmp_path / "originals/camera/identity.json"
    document = json.loads(rejected.read_text(encoding="utf-8"))
    document["review"]["disposition"] = "REJECTED"
    rejected.write_text(json.dumps(document), encoding="utf-8")

    report = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    by_id = {slot["artifact_id"]: slot for slot in report["slots"]}
    assert "SIDECAR_SCHEMA_INVALID" in by_id["camera_receipt"]["blockers"]
    assert "REVIEW_NOT_ACCEPTED" in by_id["camera_identity"]["blockers"]
    assert report["ready_for_offline_qualification_review"] is False


def test_mixed_configuration_epochs_fail_closed(tmp_path: Path):
    _populate(tmp_path)
    sidecar = tmp_path / "originals/camera/identity.json"
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    document["configuration_epoch_id"] = "camera-epoch-002"
    sidecar.write_text(json.dumps(document), encoding="utf-8")
    report = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    assert report["valid_slot_count"] == 15
    assert report["global_blockers"] == ["CONFIGURATION_EPOCH_MISMATCH"]
    assert report["ready_for_offline_qualification_review"] is False


def test_nonexistent_or_symlink_root_is_rejected(tmp_path: Path):
    with pytest.raises(CameraArrivalEvidencePreflightV1Error):
        inspect_camera_arrival_evidence_v1(ROOT, tmp_path / "missing")


@pytest.mark.parametrize("mutation", ("hash", "authority", "slot"))
def test_parser_rejects_mutated_or_rehashed_reports(tmp_path: Path, mutation: str):
    report = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    changed = json.loads(json.dumps(report))
    if mutation == "hash":
        changed["preflight_sha256"] = H
    elif mutation == "authority":
        changed["physical_authority"] = True
        _rehash(changed)
    else:
        changed["slots"][0]["status"] = "VALID"
        _rehash(changed)
    with pytest.raises(CameraArrivalEvidencePreflightV1Error):
        parse_camera_arrival_evidence_preflight_v1(changed)
