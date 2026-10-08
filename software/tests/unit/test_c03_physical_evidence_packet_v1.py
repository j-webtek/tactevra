from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.c03_installed_collision_qualification_v1 import (
    prepare_c03_installed_collision_qualification_v1,
)
from rocell.application.c03_physical_evidence_packet_v1 import (
    BLOCKED_MEASUREMENTS,
    BLOCKED_RIGID,
    READY_FOR_EVALUATION,
    C03PhysicalEvidencePacketV1Error,
    build_c03_physical_evidence_packet_v1,
    load_c03_route_result_v1,
    main,
    render_c03_physical_evidence_packet_markdown_v1,
)
from rocell.application.c03_rigid_attachment_binding_v1 import (
    load_c03_rigid_attachment_binding_v1,
)
from rocell.application.context import load_simulation_context

from test_c03_cable_envelope_intake_v1 import (
    EVALUATED,
    _manifest as _cable_manifest,
)
from test_c03_rigid_attachment_binding_v1 import _manifest as _rigid_manifest
from test_c03_route_collision_handoff_v1 import _result
from test_installed_collision_profile_builder_v1 import _document


WORKSPACE = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = WORKSPACE / "software/config/system_manifest.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write(tmp_path: Path, name: str, document: dict[str, object]):
    payload = _canonical(document)
    path = tmp_path / name
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)


@pytest.fixture
def route(sim_context, monkeypatch):
    result = _result(sim_context)
    monkeypatch.setattr(
        handoff_module, "EXPECTED_RESULT_RECEIPT_SHA256", result["receipt_sha256"]
    )
    monkeypatch.setattr(
        handoff_module,
        "EXPECTED_ROUTE_RECEIPT_SHA256",
        result["route_result"]["receipt_sha256"],
    )
    return result


def test_missing_physical_evidence_produces_exact_zero_authority_packet(
    sim_context, route
):
    first = build_c03_physical_evidence_packet_v1(route, sim_context)
    second = build_c03_physical_evidence_packet_v1(route, sim_context)

    assert first == second
    assert first["status"] == BLOCKED_MEASUREMENTS
    assert first["installed_body_requirements"]
    slots = first["required_partitioned_evidence_slots"]
    assert slots["route_segment_count"] > 0
    assert (
        slots["partition_owned_adjacent_sample_segment_count"]
        == slots["route_segment_count"]
    )
    assert first["fresh_observed_entry_requirement"]["required"] is True
    assert first["controller_commands"] == []
    assert first["wire_commands"] == []
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_complete_measurements_advance_only_to_rigid_capture(
    tmp_path, sim_context, route
):
    measurement_path, measurement_hash = _write(
        tmp_path, "measurements.json", _document()
    )
    packet = build_c03_physical_evidence_packet_v1(
        route,
        sim_context,
        measurement_manifest_path=measurement_path,
        expected_measurement_manifest_file_sha256=measurement_hash,
    )

    assert packet["status"] == BLOCKED_RIGID
    assert packet["stages"][0]["status"] == "READY"
    assert packet["stages"][1]["status"] == "MISSING"
    assert packet["installed_collision_gate_cleared"] is False


def test_path_hash_inputs_are_atomic_and_dependency_order_is_strict(
    sim_context, route
):
    with pytest.raises(C03PhysicalEvidencePacketV1Error, match="supplied together"):
        build_c03_physical_evidence_packet_v1(
            route, sim_context, measurement_manifest_path="measurements.json"
        )
    with pytest.raises(C03PhysicalEvidencePacketV1Error, match="requires a supplied"):
        build_c03_physical_evidence_packet_v1(
            route,
            sim_context,
            rigid_binding_manifest_path="rigid.json",
            expected_rigid_binding_manifest_file_sha256="0" * 64,
            evaluated_at_utc=EVALUATED,
        )


def test_all_capture_artifacts_are_revalidated_before_evaluation_readiness(
    tmp_path, sim_context, route
):
    policy = BoundedSegmentSamplingPolicy(maximum_samples=4)
    measurement_path, measurement_hash = _write(
        tmp_path, "measurements.json", _document()
    )
    qualification = prepare_c03_installed_collision_qualification_v1(
        route,
        sim_context,
        measurement_manifest_path=measurement_path,
        expected_measurement_manifest_file_sha256=measurement_hash,
        sampling_policy=policy,
    )
    rigid_document = _rigid_manifest(qualification, sim_context)
    rigid_path, rigid_hash = _write(tmp_path, "rigid.json", rigid_document)
    rigid = load_c03_rigid_attachment_binding_v1(
        rigid_path,
        rigid_hash,
        qualification,
        context=sim_context,
        evaluated_at_utc=EVALUATED,
    )
    cable_path, cable_hash = _write(
        tmp_path,
        "cables.json",
        _cable_manifest((qualification, rigid)),
    )

    packet = build_c03_physical_evidence_packet_v1(
        route,
        sim_context,
        measurement_manifest_path=measurement_path,
        expected_measurement_manifest_file_sha256=measurement_hash,
        rigid_binding_manifest_path=rigid_path,
        expected_rigid_binding_manifest_file_sha256=rigid_hash,
        cable_manifest_path=cable_path,
        expected_cable_manifest_file_sha256=cable_hash,
        evaluated_at_utc=EVALUATED,
        sampling_policy=policy,
    )

    assert packet["status"] == READY_FOR_EVALUATION
    assert [row["status"] for row in packet["stages"][:3]] == [
        "READY", "READY", "READY"
    ]
    assert packet["stages"][3]["status"] == "NOT_RUN"
    assert packet["installed_geometry_collision_screening_executed"] is False
    assert packet["physical_authority"] is False


def test_mutated_supplied_artifact_is_rejected_by_existing_validator(
    tmp_path, sim_context, route
):
    path, digest = _write(tmp_path, "measurements.json", _document())
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file hash mismatch"):
        build_c03_physical_evidence_packet_v1(
            route,
            sim_context,
            measurement_manifest_path=path,
            expected_measurement_manifest_file_sha256=digest,
        )


def test_markdown_is_a_read_only_capture_summary(sim_context, route):
    packet = build_c03_physical_evidence_packet_v1(route, sim_context)
    rendered = render_c03_physical_evidence_packet_markdown_v1(packet)

    assert "Exact capture population" in rendered
    assert "Fresh observed entry state" in rendered
    assert "zero commands, writes, or physical movement" in rendered
    assert "authorize execution" in rendered


def test_route_loader_binds_exact_bytes_and_rejects_mutation(tmp_path, route):
    path, digest = _write(tmp_path, "route.json", route)
    assert load_c03_route_result_v1(path, digest) == route

    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(C03PhysicalEvidencePacketV1Error, match="hash mismatch"):
        load_c03_route_result_v1(path, digest)


def test_route_loader_rejects_duplicate_json_fields(tmp_path):
    payload = b'{"schema":"first","schema":"second"}'
    path = tmp_path / "duplicate-route.json"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    with pytest.raises(C03PhysicalEvidencePacketV1Error, match="duplicate"):
        load_c03_route_result_v1(path, digest)


def test_cli_emits_read_only_blocked_worksheet_and_nonzero_status(
    tmp_path, route, capsys
):
    path, digest = _write(tmp_path, "route.json", route)
    result = main([
        "--workspace", str(WORKSPACE),
        "--route-result", str(path),
        "--route-result-sha256", digest,
        "--format", "markdown",
    ])

    captured = capsys.readouterr()
    assert result == 2
    assert "BLOCKED_INSTALLED_MEASUREMENTS_REQUIRED" in captured.out
    assert "zero commands, writes, or physical movement" in captured.out


def test_module_entrypoint_exposes_cli_help():
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(WORKSPACE / "software/src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "rocell.application.c03_physical_evidence_packet_v1",
            "--help",
        ],
        cwd=WORKSPACE,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0
    assert "--route-result-sha256" in completed.stdout
    assert "--measurement-manifest-sha256" in completed.stdout
