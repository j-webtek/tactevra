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
import rocell.application.static_overhead_collision_profile_intake_v1 as intake
import rocell.application.static_overhead_collision_source_audit_v1 as subject
from rocell.application.static_overhead_collision_profile_intake_v1 import (
    build_pending_static_overhead_measurement_manifest_v1,
)
from rocell.application.static_overhead_collision_source_audit_v1 import (
    audit_static_overhead_collision_sources_for_bindings_v1,
)
from rocell.simulation.collision import build_roarm_m3_static_overhead_collision_contract


WORKSPACE = Path(__file__).resolve().parents[3]
WHEN = "2026-10-17T04:00:00Z"
REVISION = "a" * 40


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


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


def _pending_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, str, InstalledCollisionMeasurementBindingsV1]:
    bindings = _bindings()
    monkeypatch.setattr(
        intake,
        "static_overhead_measurement_bindings_v1",
        lambda context: bindings,
    )
    document = build_pending_static_overhead_measurement_manifest_v1(
        SimpleNamespace(),
        measurement_manifest_id="static-overhead-audit-fixture-v1",
        captured_at_utc=WHEN,
    )
    payload = _canonical(document)
    path = tmp_path / "pending.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest(), bindings


def test_audit_hashes_candidate_sources_for_every_required_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, manifest_sha256, bindings = _pending_manifest(tmp_path, monkeypatch)

    first = audit_static_overhead_collision_sources_for_bindings_v1(
        WORKSPACE,
        manifest,
        manifest_sha256,
        bindings=bindings,
        source_revision=REVISION,
    )
    second = audit_static_overhead_collision_sources_for_bindings_v1(
        WORKSPACE,
        manifest,
        manifest_sha256,
        bindings=bindings,
        source_revision=REVISION,
    )

    required_ids = {item.body_id for item in bindings.contract.requirements}
    rows = {row["body_id"]: row for row in first["body_source_coverage"]}
    assert first == second
    assert set(rows) == required_ids
    assert first["required_body_count"] == 19
    assert first["candidate_body_count"] == 19
    assert first["accepted_measurement_body_count"] == 0
    assert first["missing_candidate_body_count"] == 0
    assert first["profile_generated"] is False
    assert first["collision_screening_executed"] is False
    assert first["controller_commands"] == []
    assert first["hardware_access"] is False
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False

    assert "installation:static_camera_support" in rows
    assert "installation:static_camera_module" in rows
    assert "installation:static_camera_connector" in rows
    assert "installation:static_camera_cable" in rows
    assert "attachment:camera_holder" not in rows
    assert "attachment:camera_module" not in rows

    for row in rows.values():
        assert row["decision"] == "CANDIDATE_ONLY"
        assert row["accepted_measurement_source_count"] == 0
        assert row["candidate_sources"]
        for source in row["candidate_sources"]:
            payload = (WORKSPACE / source["path"]).read_bytes()
            assert source["sha256"] == hashlib.sha256(payload).hexdigest()
            assert source["byte_count"] == len(payload)
            assert source["qualification"] == "CANDIDATE_ONLY"

    board = rows["workcell:board_solid"]["candidate_sources"][0]
    keyboard = rows["workcell:keyboard"]["candidate_sources"][0]
    robot = rows["robot:base_link"]["candidate_sources"][0]
    assert board["evidence_class"] == "FROZEN_DIGITAL_PHYSICAL_MEASUREMENT_OPEN"
    assert keyboard["evidence_class"] == "MANUAL_PHOTO_ESTIMATE_ONLY"
    assert robot["evidence_class"] == "CONSERVATIVE_BOX_CANDIDATES_ONLY"


def test_audit_rejects_catalog_that_does_not_match_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, manifest_sha256, bindings = _pending_manifest(tmp_path, monkeypatch)
    incomplete = dict(subject._CATALOG)
    incomplete.pop("workcell:phone")
    monkeypatch.setattr(subject, "_CATALOG", incomplete)

    with pytest.raises(ValueError, match="source catalog differs"):
        audit_static_overhead_collision_sources_for_bindings_v1(
            WORKSPACE,
            manifest,
            manifest_sha256,
            bindings=bindings,
            source_revision=REVISION,
        )


def test_audit_rejects_missing_source_and_invalid_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, manifest_sha256, bindings = _pending_manifest(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="lowercase 40-character Git SHA"):
        audit_static_overhead_collision_sources_for_bindings_v1(
            WORKSPACE,
            manifest,
            manifest_sha256,
            bindings=bindings,
            source_revision="main",
        )

    catalog = dict(subject._CATALOG)
    catalog["workcell:phone"] = (
        ("does/not/exist.json", "MISSING_TEST_SOURCE", "synthetic test"),
    )
    monkeypatch.setattr(subject, "_CATALOG", catalog)
    with pytest.raises(FileNotFoundError, match="does/not/exist.json"):
        audit_static_overhead_collision_sources_for_bindings_v1(
            WORKSPACE,
            manifest,
            manifest_sha256,
            bindings=bindings,
            source_revision=REVISION,
        )
