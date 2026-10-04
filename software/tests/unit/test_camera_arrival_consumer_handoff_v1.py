from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from rocell.application.camera_arrival_consumer_handoff_v1 import (
    BLOCKED_STATUS, READY_STATUS, CameraArrivalConsumerHandoffV1Error,
    build_camera_arrival_consumer_handoff_v1,
    compose_camera_arrival_consumer_handoff_v1,
    parse_camera_arrival_consumer_handoff_v1,
)
from rocell.application.camera_arrival_consumer_map_v1 import (
    build_camera_arrival_consumer_map_v1,
)
from rocell.application.camera_arrival_evidence_preflight_v1 import (
    inspect_camera_arrival_evidence_v1,
)
from rocell.application.camera_arrival_kit_v1 import build_camera_arrival_kit_v1


ROOT = Path(__file__).resolve().parents[3]
H = "a" * 64
SCHEMA = json.loads(
    (ROOT / "software/ai/schemas/camera_arrival_consumer_handoff_v1.schema.json")
    .read_text(encoding="utf-8")
)
VALIDATOR = Draft202012Validator(SCHEMA)


def _populate(root: Path, *, epoch: str = "camera-epoch-001") -> None:
    for slot in build_camera_arrival_kit_v1()["slots"]:
        source_relative = f"sources/{slot['artifact_id']}.bin"
        source = root / source_relative
        source.parent.mkdir(parents=True, exist_ok=True)
        payload = f"measured-{slot['artifact_id']}".encode()
        source.write_bytes(payload)
        uncertainty = None
        if slot["uncertainty_required"]:
            uncertainty = {
                "value": 0.1, "unit": slot["required_units"][0],
                "method": "fixture residual bound", "evidence_sha256": H,
            }
        sidecar = root / slot["destination_relative_to_external_evidence_root"]
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps({
            "schema": "rocell.camera_arrival_original.v1",
            "artifact_id": slot["artifact_id"],
            "artifact_class": slot["artifact_class"],
            "captured_at_utc": "2026-09-28T12:00:00Z",
            "source_relative_path": source_relative,
            "source_size_bytes": len(payload),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "units": slot["required_units"], "uncertainty": uncertainty,
            "configuration_epoch_id": epoch,
            "review": {
                "reviewer_id": "owner-ai-review",
                "reviewed_at_utc": "2026-09-28T13:00:00Z",
                "disposition": "ACCEPTED", "review_sha256": H,
            },
        }), encoding="utf-8")


def _rehash(report: dict[str, object]) -> None:
    report.pop("handoff_sha256", None)
    raw = json.dumps(
        report, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    report["handoff_sha256"] = hashlib.sha256(raw).hexdigest()


def test_empty_root_routes_every_slot_but_grants_no_authority(tmp_path: Path):
    report = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(parse_camera_arrival_consumer_handoff_v1(report)) == report
    assert report["status"] == BLOCKED_STATUS
    assert report["slot_count"] == 15
    assert report["ready_slot_count"] == 0
    assert all(route["preflight_status"] == "MISSING" for route in report["routes"])
    assert all(route["consumer_dependency_resolved"] for route in report["routes"])
    assert all(not route["physical_admission_ready"] for route in report["routes"])
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_complete_set_is_only_ready_for_offline_consumer_validation(tmp_path: Path):
    _populate(tmp_path)
    report = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(parse_camera_arrival_consumer_handoff_v1(report)) == report
    assert report["status"] == READY_STATUS
    assert report["configuration_epoch_ids"] == ["camera-epoch-001"]
    assert report["ready_slot_count"] == 15
    assert all(
        route["ready_for_offline_consumer_validation"]
        and not route["consumer_validation_completed"]
        and not route["physical_admission_ready"]
        for route in report["routes"]
    )
    assert report["consumer_validation_completed"] is False
    assert report["qualification_installed"] is False


def test_one_invalid_source_blocks_all_routes_until_epoch_complete(tmp_path: Path):
    _populate(tmp_path)
    (tmp_path / "sources/camera_identity.bin").write_bytes(b"changed")
    report = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    identity = next(
        route for route in report["routes"] if route["artifact_id"] == "camera_identity"
    )
    assert identity["preflight_status"] == "INVALID"
    assert "SOURCE_HASH_MISMATCH" in identity["preflight_blockers"]
    assert report["ready_slot_count"] == 0


def test_composer_rejects_tampered_consumer_map(tmp_path: Path):
    preflight = inspect_camera_arrival_evidence_v1(ROOT, tmp_path)
    consumer_map = build_camera_arrival_consumer_map_v1(ROOT)
    consumer_map["mappings"][0]["consumer_binding"] = "wrong"
    with pytest.raises(CameraArrivalConsumerHandoffV1Error):
        compose_camera_arrival_consumer_handoff_v1(preflight, consumer_map)


@pytest.mark.parametrize("mutation", ("hash", "authority", "route"))
def test_parser_rejects_mutated_or_rehashed_handoff(tmp_path: Path, mutation: str):
    changed = json.loads(json.dumps(
        build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    ))
    if mutation == "hash":
        changed["handoff_sha256"] = H
    elif mutation == "authority":
        changed["physical_authority"] = True
        _rehash(changed)
    else:
        changed["routes"][0]["physical_admission_ready"] = True
        _rehash(changed)
    with pytest.raises(CameraArrivalConsumerHandoffV1Error):
        parse_camera_arrival_consumer_handoff_v1(changed)
