from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rocell.application._pinned_model import load_pinned_urdf
from rocell.application.context import load_simulation_context
from rocell.application.installed_collision_measurement_manifest_v1 import (
    InstalledCollisionMeasurementBindingsV1,
)
import rocell.application.static_overhead_collision_profile_intake_v1 as subject
from rocell.application.static_overhead_collision_profile_intake_v1 import (
    PENDING_STATUS,
    build_pending_static_overhead_measurement_manifest_v1,
    build_static_overhead_collision_profile_v1,
    prepare_static_overhead_measurement_packet_v1,
)
from rocell.simulation.collision import build_roarm_m3_static_overhead_collision_contract


WORKSPACE = Path(__file__).resolve().parents[3]
WHEN = "2026-10-17T04:00:00Z"


def _bindings() -> InstalledCollisionMeasurementBindingsV1:
    context = load_simulation_context(
        WORKSPACE,
        WORKSPACE / "software/config/system_manifest.json",
    )
    loaded = load_pinned_urdf(
        context.scenario.model_path,
        context.scenario.model_sha256,
    )
    return InstalledCollisionMeasurementBindingsV1(
        contract=build_roarm_m3_static_overhead_collision_contract(
            loaded.model,
            context.scene,
        ),
        manifest_id="static-test-manifest",
        manifest_sha256="b" * 64,
        active_build_id="static-test-build",
        build_snapshot_sha256="c" * 64,
        robot_model_sha256=loaded.sha256,
    )


def _patch_static_context(monkeypatch: pytest.MonkeyPatch) -> None:
    bindings = _bindings()
    monkeypatch.setattr(subject, "load_static_simulation_context", lambda workspace: object())
    monkeypatch.setattr(
        subject,
        "static_overhead_measurement_bindings_v1",
        lambda context: bindings,
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _rehash(document: dict[str, object]) -> bytes:
    unsigned = {key: value for key, value in document.items() if key != "content_sha256"}
    document["content_sha256"] = hashlib.sha256(_canonical(unsigned)).hexdigest()
    return _canonical(document)


def test_pending_packet_uses_static_camera_roster_and_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_static_context(monkeypatch)
    first, payload, digest, worksheet = prepare_static_overhead_measurement_packet_v1(
        WORKSPACE,
        measurement_manifest_id="static-overhead-installed-measurements-v1",
        captured_at_utc=WHEN,
    )
    second = prepare_static_overhead_measurement_packet_v1(
        WORKSPACE,
        measurement_manifest_id="static-overhead-installed-measurements-v1",
        captured_at_utc=WHEN,
    )

    document = json.loads(payload)
    body_ids = {row["body_id"] for row in document["body_measurements"]}
    assert first["status"] == PENDING_STATUS
    assert first == second[0]
    assert payload == second[1]
    assert digest == second[2] == hashlib.sha256(payload).hexdigest()
    assert "installation:static_camera_support" in body_ids
    assert "installation:static_camera_module" in body_ids
    assert "installation:static_camera_connector" in body_ids
    assert "installation:static_camera_cable" in body_ids
    assert "attachment:camera_holder" not in body_ids
    assert "attachment:camera_module" not in body_ids
    assert "attachment:camera_connector" not in body_ids
    assert "attachment:moving_camera_cable" not in body_ids
    assert first["validation"]["required_body_count"] == len(body_ids)
    assert first["validation"]["pending_body_ids"] == sorted(body_ids)
    assert first["profile_generated"] is False
    assert first["collision_screening_executed"] is False
    assert first["controller_commands"] == []
    assert first["hardware_access"] is False
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False
    assert "Base contract SHA-256" in worksheet
    assert "static_camera_support" in worksheet


def test_complete_static_manifest_builds_zero_authority_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_static_context(monkeypatch)
    context = SimpleNamespace()
    document = build_pending_static_overhead_measurement_manifest_v1(
        context,
        measurement_manifest_id="static-overhead-builder-fixture-v1",
        captured_at_utc=WHEN,
    )
    document["sources"] = [
        {
            "source_id": "reviewed-metrology",
            "sha256": "a" * 64,
            "measurement_method": "CALIPER",
            "captured_at_utc": WHEN,
            "instrument_id": "synthetic-test-caliper",
            "instrument_resolution_mm": 0.1,
            "notes": "synthetic contract test only",
        }
    ]
    for index, row in enumerate(document["body_measurements"]):
        row.update(
            status="MEASURED",
            source_ids=["reviewed-metrology"],
            geometry_uncertainty_mm=0.5,
            envelope_primitives=[
                {
                    "kind": "sphere",
                    "center_mm": [float(index), 0.0, 0.0],
                    "radius_mm": 2.0,
                }
            ],
            notes="synthetic contract test only",
        )
    document["clearance_measurement"] = {
        "status": "ACCEPTED_MEASURED",
        "source_ids": ["reviewed-metrology"],
        "minimum_separation_mm": 2.0,
        "geometry_uncertainty_mm_per_body": 0.5,
        "pose_uncertainty_mm_per_body": 0.5,
        "notes": "synthetic contract test only",
    }
    payload = _rehash(document)
    manifest = tmp_path / "static-measurements.json"
    manifest.write_bytes(payload)

    result = build_static_overhead_collision_profile_v1(
        WORKSPACE,
        manifest,
        hashlib.sha256(payload).hexdigest(),
    )

    assert result.status == "BUILT_ZERO_AUTHORITY"
    assert result.profile_bytes is not None
    assert result.profile_document["base_contract_sha256"] == document[
        "base_contract_sha256"
    ]
    profile_ids = {row["body_id"] for row in result.profile_document["bodies"]}
    assert "installation:static_camera_support" in profile_ids
    assert "attachment:camera_holder" not in profile_ids
    assert result.to_dict()["collision_screening_executed"] is False
    assert result.to_dict()["controller_commands"] == []
    assert result.to_dict()["hardware_access"] is False
    assert result.to_dict()["physical_movements"] == 0
    assert result.to_dict()["physical_authority"] is False
