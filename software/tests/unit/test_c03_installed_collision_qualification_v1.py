from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.c03_installed_collision_qualification_v1 import (
    MANIFEST_REQUIRED_STATUS,
    READY_FOR_EVIDENCE_STATUS,
    C03InstalledCollisionQualificationV1Error,
    prepare_c03_installed_collision_qualification_v1,
)
from rocell.application.installed_collision_profile_builder_v1 import (
    BLOCKED_MEASUREMENTS_STATUS,
)
from rocell.application.partitioned_typing_collision_intake_v1 import READY_STATUS
from rocell.application.context import load_simulation_context

from test_c03_route_collision_handoff_v1 import _result
from test_installed_collision_profile_builder_v1 import _document


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, MANIFEST)


@pytest.fixture
def synthetic_result(sim_context, monkeypatch):
    result = _result(sim_context)
    monkeypatch.setattr(
        handoff_module,
        "EXPECTED_RESULT_RECEIPT_SHA256",
        result["receipt_sha256"],
    )
    monkeypatch.setattr(
        handoff_module,
        "EXPECTED_ROUTE_RECEIPT_SHA256",
        result["route_result"]["receipt_sha256"],
    )
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write(tmp_path: Path, document: dict[str, object]) -> tuple[Path, str]:
    payload = _canonical(document)
    path = tmp_path / "installed-measurements.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def test_missing_manifest_retains_exact_route_and_all_authority_blockers(
    sim_context, synthetic_result
):
    report = prepare_c03_installed_collision_qualification_v1(
        synthetic_result,
        sim_context,
    )

    assert report["status"] == MANIFEST_REQUIRED_STATUS
    assert report["measurement_manifest_supplied"] is False
    assert report["profile_build"] is None
    assert report["c03_collision_handoff"]["ordered_targets"] == [
        "H",
        "E",
        "L",
        "L",
        "O",
        "SPACE",
        "2",
        "0",
        "2",
        "6",
    ]
    assert "INSTALLED_COLLISION_MEASUREMENT_MANIFEST_REQUIRED" in report["blockers"]
    assert report["continuous_collision_proven"] is False
    assert report["installed_collision_gate_cleared"] is False
    assert report["physical_authority"] is False


def test_incomplete_measurement_manifest_fails_closed(
    tmp_path, sim_context, synthetic_result
):
    path, digest = _write(
        tmp_path,
        _document(pending_body="attachment:camera_holder"),
    )
    report = prepare_c03_installed_collision_qualification_v1(
        synthetic_result,
        sim_context,
        measurement_manifest_path=path,
        expected_measurement_manifest_file_sha256=digest,
    )

    assert report["status"] == BLOCKED_MEASUREMENTS_STATUS
    assert "PENDING:attachment:camera_holder" in report["blockers"]
    assert report["profile_file_sha256"] is None
    assert (
        report["c03_collision_handoff"]["collision_intake"][
            "installed_collision_profile_sha256"
        ]
        is None
    )
    assert report["installed_geometry_collision_screening_executed"] is False


def test_complete_synthetic_fixture_builds_profile_but_not_collision_clearance(
    tmp_path, sim_context, synthetic_result
):
    path, digest = _write(tmp_path, _document())
    first = prepare_c03_installed_collision_qualification_v1(
        synthetic_result,
        sim_context,
        measurement_manifest_path=path,
        expected_measurement_manifest_file_sha256=digest,
    )
    second = prepare_c03_installed_collision_qualification_v1(
        synthetic_result,
        sim_context,
        measurement_manifest_path=path,
        expected_measurement_manifest_file_sha256=digest,
    )

    assert first == second
    assert first["status"] == READY_FOR_EVIDENCE_STATUS
    assert first["c03_collision_handoff"]["collision_intake"]["status"] == READY_STATUS
    assert first["profile_file_sha256"] is not None
    assert (
        "CONFIGURATION_GEOMETRY_REQUIRED_FOR_EVERY_PARTITION_SAMPLE"
        in first["blockers"]
    )
    assert (
        "CONSERVATIVE_SWEEP_ENVELOPES_REQUIRED_FOR_EVERY_ROUTE_SEGMENT"
        in first["blockers"]
    )
    assert first["continuous_collision_proven"] is False
    assert first["installed_collision_gate_cleared"] is False
    assert first["controller_commands"] == []
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0


def test_manifest_path_and_hash_are_atomic_inputs(sim_context, synthetic_result):
    with pytest.raises(C03InstalledCollisionQualificationV1Error, match="together"):
        prepare_c03_installed_collision_qualification_v1(
            synthetic_result,
            sim_context,
            measurement_manifest_path="measurements.json",
        )


def test_altered_manifest_hash_is_rejected(tmp_path, sim_context, synthetic_result):
    path, digest = _write(tmp_path, _document())
    changed = copy.deepcopy(_document())
    changed["measurement_manifest_id"] = "crossed-measurement-manifest"
    path.write_bytes(_canonical(changed))

    with pytest.raises(ValueError, match="file hash mismatch"):
        prepare_c03_installed_collision_qualification_v1(
            synthetic_result,
            sim_context,
            measurement_manifest_path=path,
            expected_measurement_manifest_file_sha256=digest,
        )


def test_unqualified_route_is_rejected_before_manifest_access(sim_context):
    with pytest.raises(ValueError, match="receipt identity"):
        prepare_c03_installed_collision_qualification_v1(
            _result(sim_context),
            sim_context,
            measurement_manifest_path="manifest-must-not-be-read.json",
            expected_measurement_manifest_file_sha256="0" * 64,
        )
