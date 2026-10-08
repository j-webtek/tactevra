from __future__ import annotations

from pathlib import Path

import pytest

import rocell.application.c03_partition_collision_evaluator_v1 as evaluator_module
import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.c03_cable_envelope_intake_v1 import (
    C03CableEnvelopeIntakeV1Result,
)
from rocell.application.c03_partition_collision_evaluator_v1 import (
    CLEAR_STATUS,
    COLLISION_STATUS,
    ERROR_STATUS,
    INCOMPLETE_STATUS,
    RESOURCE_STATUS,
    C03PartitionCollisionResourcePolicy,
    evaluate_c03_collision_partition_v1,
)
from rocell.application.installed_collision_profile_builder_v1 import (
    build_installed_collision_profile_v1,
    load_installed_collision_geometry_profile_from_bytes_v1,
)
from rocell.application.c03_installed_collision_qualification_v1 import (
    prepare_c03_installed_collision_qualification_v1,
)
from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.context import load_simulation_context

from test_c03_cable_envelope_intake_v1 import (
    _canonical,
    _load,
    _manifest,
)
from test_partitioned_typing_collision_intake_v1 import _inputs
from test_installed_collision_profile_builder_v1 import _document
from test_installed_collision_profile_builder_v1 import _rehash as _rehash_measurement
from test_c03_route_collision_handoff_v1 import _result as _route_result
from test_c03_rigid_attachment_binding_v1 import (
    EVALUATED,
    _manifest as _rigid_manifest,
    _rehash as _rehash_rigid,
    _write as _write_rigid,
)
from rocell.application.c03_rigid_attachment_binding_v1 import (
    load_c03_rigid_attachment_binding_v1,
)


WORKSPACE = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)


@pytest.fixture
def admitted(tmp_path, monkeypatch, sim_context):
    route = _route_result(sim_context)
    monkeypatch.setattr(
        handoff_module, "EXPECTED_RESULT_RECEIPT_SHA256", route["receipt_sha256"]
    )
    monkeypatch.setattr(
        handoff_module, "EXPECTED_ROUTE_RECEIPT_SHA256",
        route["route_result"]["receipt_sha256"],
    )
    measurement = _document()
    for index, body in enumerate(measurement["body_measurements"]):
        offset = 1_000_000.0 * (index + 1)
        for primitive in body["envelope_primitives"]:
            for field in ("center_mm", "start_mm", "end_mm"):
                if field in primitive:
                    primitive[field][0] += offset
    _rehash_measurement(measurement)
    measurement_bytes = _canonical(measurement)
    measurement_path = tmp_path / "clear-measurements.json"
    measurement_path.write_bytes(measurement_bytes)
    import hashlib
    qualification = prepare_c03_installed_collision_qualification_v1(
        route, sim_context,
        measurement_manifest_path=measurement_path,
        expected_measurement_manifest_file_sha256=hashlib.sha256(
            measurement_bytes
        ).hexdigest(),
        sampling_policy=BoundedSegmentSamplingPolicy(maximum_samples=4),
    )
    rigid_document = _rigid_manifest(qualification, sim_context)
    for index, row in enumerate(rigid_document["transforms"]):
        row["translation_mm"] = [5_000.0 + 1_000.0 * index, 0.0, 0.0]
        row["translation_uncertainty_mm"] = 0.0
        row["rotation_uncertainty_deg"] = 0.0
    _rehash_rigid(rigid_document)
    rigid_path, rigid_hash = _write_rigid(tmp_path, "clear-rigid.json", rigid_document)
    rigid = load_c03_rigid_attachment_binding_v1(
        rigid_path, rigid_hash, qualification,
        context=sim_context, evaluated_at_utc=EVALUATED,
    )
    built = build_installed_collision_profile_v1(
        measurement_path,
        hashlib.sha256(measurement_bytes).hexdigest(),
        context=sim_context,
    )
    assert built.profile_bytes is not None
    assert built.profile_file_sha256 == qualification["profile_file_sha256"]
    profile = load_installed_collision_geometry_profile_from_bytes_v1(
        built.profile_bytes,
        built.profile_file_sha256,
        context=sim_context,
        expected_source_bindings=built.profile_document["source_bindings"],
    )
    rebound = (qualification, rigid)
    cable_document = _manifest(rebound)
    for collection in ("samples", "sweeps"):
        for row in cable_document[collection]:
            for body in row["bodies"]:
                for capsule in body["capsules"]:
                    capsule["start_mm"][0] += 1_000_000.0
                    capsule["end_mm"][0] += 1_000_000.0
    unsigned = {
        key: value for key, value in cable_document.items()
        if key != "content_sha256"
    }
    cable_document["content_sha256"] = hashlib.sha256(
        _canonical(unsigned)
    ).hexdigest()
    cable = _load(tmp_path, rebound, cable_document)
    snapshot = _inputs(sim_context)[0]
    return qualification, rigid, profile, cable, snapshot


def _evaluate(sim_context, admitted, cable=None, *, policy=None):
    qualification, rigid, profile, original, snapshot = admitted
    return evaluate_c03_collision_partition_v1(
        sim_context,
        snapshot,
        profile,
        qualification,
        rigid,
        original if cable is None else cable,
        0,
        resource_policy=policy,
    )


def test_clear_partition_is_deterministic_and_retains_continuous_proof_blocker(
    sim_context, admitted
):
    first = _evaluate(sim_context, admitted)
    second = _evaluate(sim_context, admitted)

    assert first == second
    assert first["status"] == CLEAR_STATUS, [
        item["collisions"] for item in first["sample_reports"][:1]
    ]
    assert first["all_declared_evidence_slots_consumed_exactly_once"] is True
    assert first["sample_count"] > 1
    assert first["segment_count"] == first["sample_count"] - 1
    assert first["continuous_collision_proven"] is False
    assert "ICQ6_CONTINUOUS_SEGMENT_PROOF_REQUIRED" in first["blockers"]
    assert first["sample_reports"][0]["tested_body_pair_count"] > 0
    assert first["sample_reports"][0]["limiting_body_pair"] is not None
    assert first["sample_reports"][0]["minimum_clearance_lower_bound_mm"] >= 0.0
    assert first["controller_commands"] == first["wire_commands"] == []
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_collision_outcome_is_distinct_from_incomplete_evidence(
    tmp_path, sim_context, admitted
):
    rebound = (admitted[0], admitted[1])
    document = _manifest(rebound)
    for collection in ("samples", "sweeps"):
        for row in document[collection]:
            for body in row["bodies"]:
                body["capsules"][0].update({
                    "start_mm": [0.0, 0.0, 0.0],
                    "end_mm": [0.0, 0.0, 0.0],
                    "measured_radius_mm": 100_000_000.0,
                })
    unsigned = {key: value for key, value in document.items() if key != "content_sha256"}
    import hashlib
    document["content_sha256"] = hashlib.sha256(_canonical(unsigned)).hexdigest()
    cable = _load(tmp_path, rebound, document)

    report = _evaluate(sim_context, admitted, cable)
    assert report["status"] == COLLISION_STATUS
    assert any(item["collisions"] for item in report["sample_reports"])
    assert report["evaluator_error"] is None


def test_missing_typed_slot_returns_incomplete_receipt(sim_context, admitted):
    cable = admitted[3]
    changed = C03CableEnvelopeIntakeV1Result(
        cable.report,
        (cable.configuration_samples_by_partition[0][:-1],)
        + cable.configuration_samples_by_partition[1:],
        cable.sweep_envelopes_by_partition,
    )
    report = _evaluate(sim_context, admitted, changed)
    assert report["status"] == INCOMPLETE_STATUS
    assert report["all_declared_evidence_slots_consumed_exactly_once"] is False


def test_typed_evidence_tampering_returns_incomplete_receipt(sim_context, admitted):
    cable = admitted[3]
    first_partition = list(cable.configuration_samples_by_partition[0])
    first_partition[0] = first_partition[1]
    changed = C03CableEnvelopeIntakeV1Result(
        cable.report,
        (tuple(first_partition),) + cable.configuration_samples_by_partition[1:],
        cable.sweep_envelopes_by_partition,
    )
    report = _evaluate(sim_context, admitted, changed)
    assert report["status"] == INCOMPLETE_STATUS
    assert "typed cable evidence differs" in report["evaluator_error"]["message"]


def test_resource_limit_is_distinct(sim_context, admitted):
    report = _evaluate(
        sim_context,
        admitted,
        policy=C03PartitionCollisionResourcePolicy(
            maximum_samples=1,
            maximum_segments=1,
            maximum_total_primitive_pair_tests=1,
        ),
    )
    assert report["status"] == RESOURCE_STATUS
    assert report["sample_reports"] == []


def test_evaluator_failure_is_a_deterministic_error_receipt(
    monkeypatch, sim_context, admitted
):
    def fail(*args, **kwargs):
        raise RuntimeError("injected evaluator failure")

    monkeypatch.setattr(evaluator_module, "evaluate_collision_pose", fail)
    first = _evaluate(sim_context, admitted)
    second = _evaluate(sim_context, admitted)
    assert first == second
    assert first["status"] == ERROR_STATUS
    assert first["evaluator_error"] == {
        "type": "RuntimeError",
        "message": "injected evaluator failure",
    }
