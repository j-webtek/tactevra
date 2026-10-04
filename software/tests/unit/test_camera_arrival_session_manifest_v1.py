from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from rocell.application.camera_arrival_commissioning_orchestrator_v1 import (
    run_camera_arrival_commissioning_orchestrator_v1,
)
from rocell.application.camera_arrival_fault_campaign_v1 import _populate, _write_receipts
from rocell.application.camera_arrival_session_manifest_v1 import (
    BLOCKED_STATE, COLLECTION_STATE, COMPLETE_HELD_STATE, MAX_MANIFEST_BYTES,
    PENDING_STATE, STRUCTURALLY_COMPLETE_STATE,
    CameraArrivalSessionManifestV1Error,
    build_camera_arrival_session_manifest_v1,
    load_camera_arrival_session_manifest_v1,
    parse_camera_arrival_session_manifest_v1,
    reconstruct_camera_arrival_session_manifest_v1,
)


ROOT = Path(__file__).resolve().parents[3]
H1 = "1" * 64
H2 = "2" * 64
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/camera_arrival_session_manifest_v1.schema.json"
).read_text(encoding="utf-8")))


def _build(evidence: Path, receipts: Path | None = None) -> dict:
    orchestrator = run_camera_arrival_commissioning_orchestrator_v1(
        ROOT, evidence, receipts
    )
    return build_camera_arrival_session_manifest_v1(
        orchestrator, session_id="arrival-session-001",
        configuration_epoch_candidate="camera-epoch-001",
        camera_profile_id="fixed-camera-profile-v1", camera_profile_sha256=H1,
        tool_profile_id="bare-gripper-profile-v1", tool_profile_sha256=H2,
    )


def test_empty_session_is_restart_safe_collection_state(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    manifest = _build(evidence)
    VALIDATOR.validate(manifest)
    assert dict(parse_camera_arrival_session_manifest_v1(manifest)) == manifest
    assert manifest["state"] == COLLECTION_STATE
    assert len(manifest["originals"]) == len(manifest["routes"]) == 15
    assert len(manifest["receipts"]) == 15
    assert manifest["measured_commissioning_held"] is True
    assert reconstruct_camera_arrival_session_manifest_v1(
        manifest, workspace=ROOT, evidence_root=evidence, receipt_root=None
    ) == manifest


def test_complete_originals_without_validation_root_are_structurally_complete(
    tmp_path: Path,
):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _populate(evidence)
    manifest = _build(evidence)
    assert manifest["state"] == STRUCTURALLY_COMPLETE_STATE
    assert all(row["status"] == "PENDING" for row in manifest["receipts"])


def test_empty_validation_root_is_pending(tmp_path: Path):
    evidence = tmp_path / "evidence"
    receipts = tmp_path / "receipts"
    evidence.mkdir()
    receipts.mkdir()
    _populate(evidence)
    manifest = _build(evidence, receipts)
    assert manifest["state"] == PENDING_STATE
    assert all(row["status"] == "PENDING" for row in manifest["receipts"])


def test_blocked_receipt_state_is_retained(tmp_path: Path):
    evidence = tmp_path / "evidence"
    receipts = tmp_path / "receipts"
    evidence.mkdir()
    _populate(evidence)
    _write_receipts(ROOT, evidence, receipts, blocked=7)
    manifest = _build(evidence, receipts)
    assert manifest["state"] == BLOCKED_STATE
    assert sum(row["status"] == "BLOCKED" for row in manifest["receipts"]) == 1


def test_all_receipts_reach_offline_review_but_commissioning_stays_held(tmp_path: Path):
    evidence = tmp_path / "evidence"
    receipts = tmp_path / "receipts"
    evidence.mkdir()
    _populate(evidence)
    _write_receipts(ROOT, evidence, receipts)
    manifest = _build(evidence, receipts)
    assert manifest["state"] == COMPLETE_HELD_STATE
    assert all(row["status"] == "PASS" for row in manifest["receipts"])
    assert manifest["configuration_epoch_advanced"] is False
    assert manifest["qualification_installed"] is False
    assert manifest["camera_opened"] is manifest["transport_opened"] is False
    assert manifest["controller_commands"] == []
    assert manifest["hardware_writes"] == manifest["physical_movements"] == 0
    assert manifest["physical_authority"] is False


def test_restart_detects_changed_original(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _populate(evidence)
    manifest = _build(evidence)
    source = evidence / "sources" / "camera_receipt.bin"
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(CameraArrivalSessionManifestV1Error, match="differs"):
        reconstruct_camera_arrival_session_manifest_v1(
            manifest, workspace=ROOT, evidence_root=evidence, receipt_root=None
        )


@pytest.mark.parametrize("mutation", ("authority", "original"))
def test_manifest_mutations_reject(tmp_path: Path, mutation: str):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    manifest = _build(evidence)
    if mutation == "authority":
        manifest["physical_authority"] = True
    else:
        manifest["originals"][0]["status"] = "VALID"
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    with pytest.raises(CameraArrivalSessionManifestV1Error):
        parse_camera_arrival_session_manifest_v1(manifest)


def test_changed_profile_or_epoch_is_a_distinct_manifest_not_a_resume(
    tmp_path: Path,
):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    original = _build(evidence)
    orchestrator = original["orchestrator"]
    changed = build_camera_arrival_session_manifest_v1(
        orchestrator, session_id="arrival-session-001",
        configuration_epoch_candidate="camera-epoch-002",
        camera_profile_id="fixed-camera-profile-v2",
        camera_profile_sha256="3" * 64,
        tool_profile_id="bare-gripper-profile-v1", tool_profile_sha256=H2,
    )
    assert dict(parse_camera_arrival_session_manifest_v1(changed)) == changed
    assert changed["manifest_sha256"] != original["manifest_sha256"]
    assert reconstruct_camera_arrival_session_manifest_v1(
        original, workspace=ROOT, evidence_root=evidence, receipt_root=None
    ) == original


def test_strict_loader_rejects_duplicate_and_oversized_documents(tmp_path: Path):
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    with pytest.raises(CameraArrivalSessionManifestV1Error, match="duplicate"):
        load_camera_arrival_session_manifest_v1(duplicate)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (MAX_MANIFEST_BYTES + 1))
    with pytest.raises(CameraArrivalSessionManifestV1Error, match="size"):
        load_camera_arrival_session_manifest_v1(oversized)
