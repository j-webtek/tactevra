from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.collision_readiness import assess_current_collision_readiness
from rocell.application.context import load_simulation_context
from rocell.application.installed_collision_measurement_manifest_v1 import (
    BLOCKED_STATUS,
    READY_STATUS,
    InstalledCollisionMeasurementManifestV1Error,
    load_and_validate_installed_collision_measurement_manifest_v1,
    render_installed_collision_measurement_worksheet_v1,
)
from rocell.simulation.collision import CollisionBindingMode


WORKSPACE = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = WORKSPACE / "software/config/system_manifest.json"
WHEN = "2026-10-07T16:00:00Z"
SOURCE_HASH = "a" * 64


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _document(*, pending_body: str | None = None) -> dict[str, object]:
    context = load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)
    readiness = assess_current_collision_readiness(context)
    bodies = []
    for requirement in readiness.contract.requirements:
        pending = requirement.body_id == pending_body
        sampled = requirement.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
        bodies.append({
            "body_id": requirement.body_id,
            "parent_frame": requirement.parent_frame,
            "role": requirement.role.value,
            "binding_mode": requirement.binding_mode.value,
            "status": "PENDING" if pending else "MEASURED",
            "source_ids": [] if pending else ["metrology"],
            "coordinate_frame": requirement.parent_frame,
            "units": "mm",
            "geometry_uncertainty_mm": None if pending else 0.5,
            "envelope_primitives": (
                []
                if pending or sampled
                else [{
                    "kind": "sphere", "center_mm": [0.0, 0.0, 0.0],
                    "radius_mm": 1.0,
                }]
            ),
            "notes": "unit-test measurement",
        })
    document: dict[str, object] = {
        "schema": "rocell.installed_collision_measurement_manifest.v1",
        "measurement_manifest_id": "installed-measurements-unit-v1",
        "captured_at_utc": WHEN,
        "manifest_id": readiness.manifest_id,
        "manifest_sha256": readiness.manifest_sha256,
        "active_build_id": readiness.active_build_id,
        "build_snapshot_sha256": readiness.build_snapshot_hash,
        "robot_model_sha256": readiness.urdf_sha256,
        "base_contract_sha256": readiness.contract.content_hash,
        "root_frame": readiness.contract.root_frame,
        "sources": [{
            "source_id": "metrology", "sha256": SOURCE_HASH,
            "measurement_method": "CALIPER", "captured_at_utc": WHEN,
            "instrument_id": "unit-caliper", "instrument_resolution_mm": 0.1,
            "notes": "synthetic unit-test source",
        }],
        "body_measurements": bodies,
        "clearance_measurement": {
            "status": "ACCEPTED_MEASURED", "source_ids": ["metrology"],
            "minimum_separation_mm": 2.0,
            "geometry_uncertainty_mm_per_body": 0.5,
            "pose_uncertainty_mm_per_body": 0.5,
            "notes": "unit-test policy",
        },
    }
    document["content_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    return document


def _write(tmp_path: Path, document: dict[str, object]) -> tuple[Path, str]:
    payload = _canonical(document)
    path = tmp_path / "measurements.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _load(tmp_path: Path, document: dict[str, object]) -> dict[str, object]:
    path, digest = _write(tmp_path, document)
    context = load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)
    return load_and_validate_installed_collision_measurement_manifest_v1(
        path, digest, context=context
    )


def _rehash(document: dict[str, object]) -> None:
    unsigned = {key: value for key, value in document.items() if key != "content_sha256"}
    document["content_sha256"] = hashlib.sha256(_canonical(unsigned)).hexdigest()


def test_complete_manifest_is_ready_but_creates_no_profile_or_authority(
    tmp_path: Path,
) -> None:
    report = _load(tmp_path, _document())

    assert report["status"] == READY_STATUS
    assert report["required_body_count"] == 19
    assert report["measured_body_count"] == 19
    assert report["blockers"] == []
    assert report["profile_generated"] is False
    assert report["collision_screening_executed"] is False
    assert report["controller_commands"] == []
    assert report["hardware_access"] is False
    assert report["physical_authority"] is False


def test_pending_body_is_valid_but_fails_closed(tmp_path: Path) -> None:
    report = _load(tmp_path, _document(pending_body="attachment:camera_holder"))

    assert report["status"] == BLOCKED_STATUS
    assert report["pending_body_ids"] == ["attachment:camera_holder"]
    assert report["blockers"] == ["PENDING:attachment:camera_holder"]


def test_worksheet_names_every_required_body_and_preserves_sampled_scope() -> None:
    context = load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)
    contract = assess_current_collision_readiness(context).contract
    worksheet = render_installed_collision_measurement_worksheet_v1(contract)

    body_rows = [line for line in worksheet.splitlines() if line.startswith("| `")]
    assert len(body_rows) == 19
    assert "`attachment:moving_camera_cable`" in worksheet
    assert "per-configuration geometry in ICQ-4" in worksheet
    assert "no profile, collision result, command, or physical authority" in worksheet


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda document: document["body_measurements"][0].update(units="in"),
            "frame, role, binding mode, or units differ",
        ),
        (
            lambda document: document["body_measurements"][0].update(
                coordinate_frame="anonymous_xyz"
            ),
            "frame, role, binding mode, or units differ",
        ),
        (
            lambda document: document["sources"][0].update(
                measurement_method="PHOTO_ESTIMATE"
            ),
            "measurement method is unsupported",
        ),
        (
            lambda document: document["body_measurements"][0].update(
                source_ids=["unknown"]
            ),
            "references unknown sources",
        ),
    ],
)
def test_rejects_ambiguous_units_frames_methods_and_sources(
    tmp_path: Path, mutation, message: str
) -> None:
    document = _document()
    mutation(document)
    _rehash(document)
    with pytest.raises(InstalledCollisionMeasurementManifestV1Error, match=message):
        _load(tmp_path, document)


def test_rejects_static_geometry_for_configuration_sampled_cable(
    tmp_path: Path,
) -> None:
    document = _document()
    cable = next(
        body
        for body in document["body_measurements"]
        if body["body_id"] == "attachment:moving_camera_cable"
    )
    cable["envelope_primitives"] = [{
        "kind": "capsule", "start_mm": [0, 0, 0], "end_mm": [1, 1, 1],
        "radius_mm": 1,
    }]
    _rehash(document)
    with pytest.raises(
        InstalledCollisionMeasurementManifestV1Error,
        match="must not store static primitives",
    ):
        _load(tmp_path, document)


def test_rejects_crossed_context_and_content_tamper(tmp_path: Path) -> None:
    document = _document()
    document["manifest_sha256"] = "b" * 64
    _rehash(document)
    with pytest.raises(
        InstalledCollisionMeasurementManifestV1Error,
        match="context binding mismatch: manifest_sha256",
    ):
        _load(tmp_path, document)

    document = _document()
    document["captured_at_utc"] = "2026-10-08T16:00:00Z"
    with pytest.raises(
        InstalledCollisionMeasurementManifestV1Error,
        match="content hash mismatch",
    ):
        _load(tmp_path, document)


def test_declared_absence_requires_evidence_and_remains_blocked(tmp_path: Path) -> None:
    document = _document()
    holder = next(
        body
        for body in document["body_measurements"]
        if body["body_id"] == "attachment:camera_holder"
    )
    holder.update(
        status="DECLARED_ABSENT",
        geometry_uncertainty_mm=None,
        envelope_primitives=[],
    )
    _rehash(document)
    report = _load(tmp_path, document)
    assert report["status"] == BLOCKED_STATUS
    assert report["declared_absent_body_ids"] == ["attachment:camera_holder"]
    assert report["blockers"] == ["DECLARED_ABSENT:attachment:camera_holder"]

    holder["source_ids"] = []
    _rehash(document)
    with pytest.raises(
        InstalledCollisionMeasurementManifestV1Error,
        match="requires a reviewed source",
    ):
        _load(tmp_path, document)
