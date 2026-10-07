from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.c03_installed_collision_qualification_v1 import (
    prepare_c03_installed_collision_qualification_v1,
)
from rocell.application.c03_rigid_attachment_binding_v1 import (
    READY_STATUS,
    C03RigidAttachmentBindingV1Error,
    load_c03_rigid_attachment_binding_v1,
)
from rocell.application.context import load_simulation_context
from rocell.application.collision_readiness import assess_current_collision_readiness

from test_c03_route_collision_handoff_v1 import _result
from test_installed_collision_profile_builder_v1 import _document


WORKSPACE = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = WORKSPACE / "software/config/system_manifest.json"
CAPTURED = "2026-10-07T20:00:00Z"
EVALUATED = "2026-10-07T20:30:00Z"
VALID_UNTIL = "2026-10-07T21:00:00Z"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _rehash(document: dict[str, object]) -> None:
    unsigned = {key: value for key, value in document.items() if key != "content_sha256"}
    document["content_sha256"] = hashlib.sha256(_canonical(unsigned)).hexdigest()


def _write(tmp_path: Path, name: str, document: dict[str, object]) -> tuple[Path, str]:
    payload = _canonical(document)
    path = tmp_path / name
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)


@pytest.fixture
def qualification(tmp_path, sim_context, monkeypatch):
    route = _result(sim_context)
    monkeypatch.setattr(
        handoff_module, "EXPECTED_RESULT_RECEIPT_SHA256", route["receipt_sha256"]
    )
    monkeypatch.setattr(
        handoff_module,
        "EXPECTED_ROUTE_RECEIPT_SHA256",
        route["route_result"]["receipt_sha256"],
    )
    measurement_path, measurement_hash = _write(
        tmp_path, "measurements.json", _document()
    )
    return prepare_c03_installed_collision_qualification_v1(
        route,
        sim_context,
        measurement_manifest_path=measurement_path,
        expected_measurement_manifest_file_sha256=measurement_hash,
    )


def _manifest(qualification: dict[str, object], sim_context) -> dict[str, object]:
    intake = qualification["c03_collision_handoff"]["collision_intake"]
    frames = intake["required_rigid_attachment_frames"]
    root_frame = assess_current_collision_readiness(sim_context).contract.root_frame
    document: dict[str, object] = {
        "schema": "tactevra.c03_rigid_attachment_binding_manifest.v1",
        "binding_manifest_id": "synthetic-rigid-binding-fixture-v1",
        "captured_at_utc": CAPTURED,
        "valid_until_utc": VALID_UNTIL,
        "c03_installed_collision_qualification_sha256": qualification[
            "c03_installed_collision_qualification_sha256"
        ],
        "collision_contract_sha256": intake["collision_contract_sha256"],
        "installed_collision_profile_content_sha256": intake[
            "installed_collision_profile_sha256"
        ],
        "installed_collision_profile_file_sha256": qualification[
            "profile_file_sha256"
        ],
        "measurement_manifest_file_sha256": qualification[
            "measurement_manifest_file_sha256"
        ],
        "measurement_manifest_content_sha256": qualification[
            "measurement_manifest_content_sha256"
        ],
        "root_frame": root_frame,
        "sources": [
            {
                "source_id": "synthetic-metrology",
                "sha256": "b" * 64,
                "captured_at_utc": CAPTURED,
                "method": "SYNTHETIC_TEST_ONLY",
                "notes": "not installed evidence",
            }
        ],
        "transforms": [
            {
                "frame": frame,
                "to_frame": root_frame,
                "from_frame": frame,
                "rotation_row_major": [
                    1.0, 0.0, 0.0,
                    0.0, 1.0, 0.0,
                    0.0, 0.0, 1.0,
                ],
                "translation_mm": [float(index), 2.0, 3.0],
                "translation_uncertainty_mm": 0.5,
                "rotation_uncertainty_deg": 0.25,
                "source_ids": ["synthetic-metrology"],
                "captured_at_utc": CAPTURED,
            }
            for index, frame in enumerate(frames)
        ],
    }
    _rehash(document)
    return document


def _load(tmp_path, sim_context, qualification, document, *, evaluated=EVALUATED):
    path, digest = _write(tmp_path, "bindings.json", document)
    return load_c03_rigid_attachment_binding_v1(
        path,
        digest,
        qualification,
        context=sim_context,
        evaluated_at_utc=evaluated,
    )


def test_exact_required_frames_pass_with_zero_authority(
    tmp_path, sim_context, qualification
):
    first = _load(tmp_path, sim_context, qualification, _manifest(qualification, sim_context))
    second = _load(tmp_path, sim_context, qualification, _manifest(qualification, sim_context))

    assert first == second
    assert first["status"] == READY_STATUS
    assert first["required_frames"] == ["camera_module", "holder"]
    assert len(first["transform_bindings"]) == 2
    assert first["installed_geometry_collision_screening_executed"] is False
    assert first["continuous_collision_proven"] is False
    assert first["controller_commands"] == []
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_missing_required_frame_rejects(tmp_path, sim_context, qualification):
    document = _manifest(qualification, sim_context)
    document["transforms"] = document["transforms"][:-1]
    _rehash(document)
    with pytest.raises(C03RigidAttachmentBindingV1Error, match="coverage differs"):
        _load(tmp_path, sim_context, qualification, document)


def test_reversed_transform_direction_rejects(tmp_path, sim_context, qualification):
    document = _manifest(qualification, sim_context)
    row = document["transforms"][0]
    row["to_frame"], row["from_frame"] = row["from_frame"], row["to_frame"]
    _rehash(document)
    with pytest.raises(C03RigidAttachmentBindingV1Error, match="direction"):
        _load(tmp_path, sim_context, qualification, document)


def test_reflected_rotation_rejects(tmp_path, sim_context, qualification):
    document = _manifest(qualification, sim_context)
    document["transforms"][0]["rotation_row_major"] = [
        -1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    ]
    _rehash(document)
    with pytest.raises(ValueError, match="right-handed"):
        _load(tmp_path, sim_context, qualification, document)


def test_stale_binding_rejects(tmp_path, sim_context, qualification):
    document = _manifest(qualification, sim_context)
    with pytest.raises(C03RigidAttachmentBindingV1Error, match="stale"):
        _load(
            tmp_path,
            sim_context,
            qualification,
            document,
            evaluated="2026-10-07T21:00:00.001000Z",
        )


def test_crossed_profile_lineage_rejects(tmp_path, sim_context, qualification):
    document = _manifest(qualification, sim_context)
    document["installed_collision_profile_file_sha256"] = "c" * 64
    _rehash(document)
    with pytest.raises(C03RigidAttachmentBindingV1Error, match="lineage differs"):
        _load(tmp_path, sim_context, qualification, document)


def test_altered_file_bytes_reject_before_parse(tmp_path, sim_context, qualification):
    document = _manifest(qualification, sim_context)
    path, digest = _write(tmp_path, "bindings.json", document)
    changed = copy.deepcopy(document)
    changed["binding_manifest_id"] = "altered"
    path.write_bytes(_canonical(changed))
    with pytest.raises(C03RigidAttachmentBindingV1Error, match="file hash mismatch"):
        load_c03_rigid_attachment_binding_v1(
            path,
            digest,
            qualification,
            context=sim_context,
            evaluated_at_utc=EVALUATED,
        )
