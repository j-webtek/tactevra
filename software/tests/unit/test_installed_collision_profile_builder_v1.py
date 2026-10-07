from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.collision_readiness import assess_current_collision_readiness
from rocell.application.context import load_simulation_context
from rocell.application.installed_collision_geometry import (
    load_installed_collision_geometry_for_context,
)
from rocell.application.installed_collision_profile_builder_v1 import (
    BLOCKED_CLEARANCE_STATUS,
    BLOCKED_MEASUREMENTS_STATUS,
    BUILT_STATUS,
    build_installed_collision_profile_v1,
)
from rocell.simulation.collision import CollisionBindingMode


WORKSPACE = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = WORKSPACE / "software/config/system_manifest.json"
WHEN = "2026-10-07T18:00:00Z"
SOURCE_HASH = "a" * 64


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


def _document(*, pending_body: str | None = None) -> dict[str, object]:
    context = load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)
    readiness = assess_current_collision_readiness(context)
    bodies = []
    primitive_kinds = ("sphere", "capsule", "oriented_box")
    primitive_index = 0
    for requirement in readiness.contract.requirements:
        pending = requirement.body_id == pending_body
        sampled = requirement.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
        primitives = []
        if not pending and not sampled:
            kind = primitive_kinds[primitive_index % len(primitive_kinds)]
            primitive_index += 1
            if kind == "sphere":
                primitives = [{
                    "kind": kind,
                    "center_mm": [-1.0, 2.0, 3.0],
                    "radius_mm": 2.0,
                }]
            elif kind == "capsule":
                primitives = [{
                    "kind": kind,
                    "start_mm": [-1.0, 0.0, 0.0],
                    "end_mm": [1.0, 0.0, 0.0],
                    "radius_mm": 2.0,
                }]
            else:
                primitives = [{
                    "kind": kind,
                    "center_mm": [0.0, 0.0, 0.0],
                    "half_extents_mm": [1.0, 2.0, 3.0],
                    "rotation_row_major": [
                        1.0, 0.0, 0.0,
                        0.0, 1.0, 0.0,
                        0.0, 0.0, 1.0,
                    ],
                }]
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
            "envelope_primitives": primitives,
            "notes": "synthetic builder fixture",
        })
    document: dict[str, object] = {
        "schema": "rocell.installed_collision_measurement_manifest.v1",
        "measurement_manifest_id": "installed-measurements-builder-fixture-v1",
        "captured_at_utc": WHEN,
        "manifest_id": readiness.manifest_id,
        "manifest_sha256": readiness.manifest_sha256,
        "active_build_id": readiness.active_build_id,
        "build_snapshot_sha256": readiness.build_snapshot_hash,
        "robot_model_sha256": readiness.urdf_sha256,
        "base_contract_sha256": readiness.contract.content_hash,
        "root_frame": readiness.contract.root_frame,
        "sources": [{
            "source_id": "metrology",
            "sha256": SOURCE_HASH,
            "measurement_method": "CALIPER",
            "captured_at_utc": WHEN,
            "instrument_id": "synthetic-caliper",
            "instrument_resolution_mm": 0.1,
            "notes": "synthetic rejection and determinism fixture only",
        }],
        "body_measurements": bodies,
        "clearance_measurement": {
            "status": "ACCEPTED_MEASURED",
            "source_ids": ["metrology"],
            "minimum_separation_mm": 2.0,
            "geometry_uncertainty_mm_per_body": 0.5,
            "pose_uncertainty_mm_per_body": 0.5,
            "notes": "synthetic policy fixture",
        },
    }
    _rehash(document)
    return document


def _write(tmp_path: Path, document: dict[str, object]) -> tuple[Path, str]:
    payload = _canonical(document)
    path = tmp_path / "measurements.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _build(tmp_path: Path, document: dict[str, object]):
    path, digest = _write(tmp_path, document)
    context = load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)
    return build_installed_collision_profile_v1(path, digest, context=context)


def test_build_is_byte_stable_hash_bound_and_zero_authority(tmp_path: Path) -> None:
    first = _build(tmp_path, _document())
    second = _build(tmp_path, _document())

    assert first.status == BUILT_STATUS
    assert first.profile_bytes == second.profile_bytes
    assert first.profile_file_sha256 == second.profile_file_sha256
    assert first.difference_report == second.difference_report
    assert first.to_dict()["profile_generated"] is True
    assert first.to_dict()["collision_screening_executed"] is False
    assert first.to_dict()["controller_commands"] == []
    assert first.to_dict()["hardware_access"] is False
    assert first.to_dict()["physical_authority"] is False


def test_conservative_fit_inflates_each_supported_primitive(tmp_path: Path) -> None:
    result = _build(tmp_path, _document())
    bodies = result.profile_document["bodies"]
    primitives = [
        body["primitives"][0]
        for body in bodies
        if body["primitives"]
    ]

    sphere = next(item for item in primitives if item["kind"] == "sphere")
    capsule = next(item for item in primitives if item["kind"] == "capsule")
    box = next(item for item in primitives if item["kind"] == "oriented_box")
    assert sphere["radius_mm"] == 2.5
    assert capsule["radius_mm"] == 2.5
    assert box["half_extents_mm"] == [1.5, 2.5, 3.5]


def test_configuration_sampled_body_is_declared_without_static_geometry(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path, _document())
    cable = next(
        body
        for body in result.profile_document["bodies"]
        if body["body_id"] == "attachment:moving_camera_cable"
    )

    assert cable["binding_mode"] == "CONFIGURATION_SAMPLED"
    assert cable["evidence_state"] == "ACCEPTED_MEASURED"
    assert cable["primitives"] == []
    assert result.difference_report["configuration_sampled_body_ids"] == [
        "attachment:moving_camera_cable"
    ]


def test_every_body_is_present_once_and_strict_consumer_accepts_output(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path, _document())
    body_ids = [body["body_id"] for body in result.profile_document["bodies"]]
    assert len(body_ids) == len(set(body_ids)) == 19
    assert all(
        body["evidence_state"] == "ACCEPTED_MEASURED"
        for body in result.profile_document["bodies"]
    )

    profile_path = tmp_path / "profile.json"
    profile_path.write_bytes(result.profile_bytes)
    context = load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)
    profile = load_installed_collision_geometry_for_context(
        profile_path,
        result.profile_file_sha256,
        context=context,
        expected_source_bindings=result.profile_document["source_bindings"],
    )
    assert profile.content_sha256 == result.profile_document["content_sha256"]
    assert profile.to_dict()["physical_authority"] is False


def test_incomplete_measurements_return_named_block_without_profile(
    tmp_path: Path,
) -> None:
    result = _build(
        tmp_path,
        _document(pending_body="attachment:camera_holder"),
    )

    assert result.status == BLOCKED_MEASUREMENTS_STATUS
    assert result.blockers == ("PENDING:attachment:camera_holder",)
    assert result.profile_document is None
    assert result.profile_bytes is None
    assert result.profile_file_sha256 is None
    assert result.difference_report is None
    assert result.to_dict()["profile_generated"] is False


def test_source_and_manifest_hashes_are_bound_into_profile(tmp_path: Path) -> None:
    result = _build(tmp_path, _document())

    assert result.profile_document["source_bindings"] == {
        "measurement_manifest:content": result.measurement_manifest_content_sha256,
        "measurement_manifest:file": result.measurement_manifest_file_sha256,
        "measurement_source:metrology": SOURCE_HASH,
    }
    assert (
        result.difference_report["measurement_manifest_file_sha256"]
        == result.measurement_manifest_file_sha256
    )


def test_pending_clearance_returns_specific_block_without_profile(
    tmp_path: Path,
) -> None:
    document = _document()
    document["clearance_measurement"] = {
        "status": "PENDING",
        "source_ids": [],
        "minimum_separation_mm": None,
        "geometry_uncertainty_mm_per_body": None,
        "pose_uncertainty_mm_per_body": None,
        "notes": "not yet measured",
    }
    _rehash(document)

    result = _build(tmp_path, document)
    assert result.status == BLOCKED_CLEARANCE_STATUS
    assert result.blockers == ("PENDING:CLEARANCE_POLICY",)
    assert result.profile_document is None
