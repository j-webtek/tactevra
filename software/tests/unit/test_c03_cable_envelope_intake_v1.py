from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import rocell.application.c03_route_collision_handoff_v1 as handoff_module
from rocell.application.c03_cable_envelope_intake_v1 import (
    READY_STATUS,
    C03CableEnvelopeIntakeV1Error,
    load_c03_cable_envelope_intake_v1,
)
from rocell.application.c03_installed_collision_qualification_v1 import (
    prepare_c03_installed_collision_qualification_v1,
)
from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.c03_rigid_attachment_binding_v1 import (
    load_c03_rigid_attachment_binding_v1,
)
from rocell.application.context import load_simulation_context

from test_c03_rigid_attachment_binding_v1 import _manifest as _rigid_manifest
from test_c03_route_collision_handoff_v1 import _result
from test_installed_collision_profile_builder_v1 import _document


WORKSPACE = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = WORKSPACE / "software/config/system_manifest.json"
SCHEMA_PATH = WORKSPACE / "software/ai/schemas/c03_cable_envelope_manifest_v1.schema.json"
CAPTURED = "2026-10-07T20:00:00Z"
EVALUATED = "2026-10-07T20:30:00Z"
VALID_UNTIL = "2026-10-07T21:00:00Z"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rehash(document: dict[str, object]) -> None:
    unsigned = {key: value for key, value in document.items() if key != "content_sha256"}
    document["content_sha256"] = _hash(unsigned)


def _write(tmp_path: Path, name: str, document: dict[str, object]) -> tuple[Path, str]:
    payload = _canonical(document)
    path = tmp_path / name
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, SYSTEM_MANIFEST)


@pytest.fixture(scope="module")
def qualified(tmp_path_factory, sim_context):
    tmp_path = tmp_path_factory.mktemp("c03-cable-qualified")
    route = _result(sim_context)
    original_result = handoff_module.EXPECTED_RESULT_RECEIPT_SHA256
    original_route = handoff_module.EXPECTED_ROUTE_RECEIPT_SHA256
    handoff_module.EXPECTED_RESULT_RECEIPT_SHA256 = route["receipt_sha256"]
    handoff_module.EXPECTED_ROUTE_RECEIPT_SHA256 = route["route_result"]["receipt_sha256"]
    try:
        measurement_path, measurement_hash = _write(
            tmp_path, "measurements.json", _document()
        )
        qualification = prepare_c03_installed_collision_qualification_v1(
            route,
            sim_context,
            measurement_manifest_path=measurement_path,
            expected_measurement_manifest_file_sha256=measurement_hash,
            sampling_policy=BoundedSegmentSamplingPolicy(maximum_samples=4),
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
        return qualification, rigid
    finally:
        handoff_module.EXPECTED_RESULT_RECEIPT_SHA256 = original_result
        handoff_module.EXPECTED_ROUTE_RECEIPT_SHA256 = original_route


def _capsule(offset: float = 0.0) -> dict[str, object]:
    return {
        "start_mm": [1000.0 + offset, -50.0, 100.0],
        "end_mm": [1010.0 + offset, -50.0, 100.0],
        "measured_radius_mm": 2.0,
        "capture_uncertainty_mm": 0.5,
        "unobserved_deformation_mm": 1.25,
    }


def _body(body_id: str, source_id: str, offset: float) -> dict[str, object]:
    return {
        "body_id": body_id,
        "source_id": source_id,
        "capsules": [_capsule(offset)],
    }


def _manifest(qualified) -> dict[str, object]:
    qualification, rigid = qualified
    intake = qualification["c03_collision_handoff"]["collision_intake"]
    source_hash = intake["accepted_profile_source_sha256_values"][0]
    source_id = "synthetic-cable-metrology"
    body_ids = intake["required_configuration_body_ids"]
    samples: list[dict[str, object]] = []
    sweeps: list[dict[str, object]] = []
    geometry_offset_by_sample: dict[str, float] = {}
    owned_segment_sequence = 0
    for partition in intake["partitions"]:
        partition_index = partition["partition_index"]
        plan = partition["bounded_joint_sample_plan"]
        for sample_sequence, sample in enumerate(plan):
            sample_hash = _hash(sample)
            posture_hash = _hash(sample["joint_positions_rad"])
            offset = geometry_offset_by_sample.setdefault(
                posture_hash, float(len(geometry_offset_by_sample))
            )
            samples.append({
                "partition_index": partition_index,
                "sample_sequence": sample_sequence,
                "sample_plan_sha256": sample_hash,
                "captured_at_utc": CAPTURED,
                "method": "DIRECT_CAPTURED_CAPSULE_CHAIN",
                "bodies": [
                    _body(body_id, source_id, offset) for body_id in body_ids
                ],
            })
        for segment_sequence, (start, end) in enumerate(zip(plan, plan[1:])):
            sweeps.append({
                "partition_index": partition_index,
                "segment_sequence": segment_sequence,
                "owned_segment_sequence": owned_segment_sequence,
                "start_sample_sha256": _hash(start),
                "end_sample_sha256": _hash(end),
                "captured_at_utc": CAPTURED,
                "construction_method": "DIRECT_CAPTURED_CONSERVATIVE_ENVELOPE",
                "intermediate_observation_count": 3,
                "bodies": [
                    _body(body_id, source_id, 5000.0 + owned_segment_sequence)
                    for body_id in body_ids
                ],
            })
            owned_segment_sequence += 1
    document: dict[str, object] = {
        "schema": "tactevra.c03_cable_envelope_manifest.v1",
        "cable_manifest_id": "synthetic-c03-cable-fixture-v1",
        "captured_at_utc": CAPTURED,
        "valid_until_utc": VALID_UNTIL,
        "c03_installed_collision_qualification_sha256": qualification[
            "c03_installed_collision_qualification_sha256"
        ],
        "c03_rigid_attachment_binding_report_sha256": rigid[
            "c03_rigid_attachment_binding_report_sha256"
        ],
        "partitioned_typing_collision_intake_sha256": intake[
            "partitioned_typing_collision_intake_sha256"
        ],
        "collision_contract_sha256": intake["collision_contract_sha256"],
        "installed_collision_profile_content_sha256": intake[
            "installed_collision_profile_sha256"
        ],
        "installed_collision_profile_file_sha256": qualification["profile_file_sha256"],
        "measurement_manifest_file_sha256": qualification[
            "measurement_manifest_file_sha256"
        ],
        "measurement_manifest_content_sha256": qualification[
            "measurement_manifest_content_sha256"
        ],
        "root_frame": rigid["root_frame"],
        "sources": [{
            "source_id": source_id,
            "sha256": source_hash,
            "captured_at_utc": CAPTURED,
            "method": "SYNTHETIC_TEST_ONLY",
            "notes": "software contract test, not installed evidence",
        }],
        "samples": samples,
        "sweeps": sweeps,
    }
    _rehash(document)
    return document


def _load(tmp_path, qualified, document, *, evaluated=EVALUATED):
    path, digest = _write(tmp_path, "cables.json", document)
    return load_c03_cable_envelope_intake_v1(
        path, digest, qualified[0], qualified[1], evaluated_at_utc=evaluated
    )


def test_exact_c03_cable_evidence_passes_with_inflation_and_zero_authority(
    tmp_path, qualified
):
    document = _manifest(qualified)
    assert list(Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).iter_errors(document)) == []

    first = _load(tmp_path, qualified, document)
    second = _load(tmp_path, qualified, document)
    report = first.report
    intake = qualified[0]["c03_collision_handoff"]["collision_intake"]
    slots = intake["required_evidence_slots"]
    assert report == second.report
    assert report["status"] == READY_STATUS
    assert report["partition_count"] == slots["partition_count"]
    assert report["sample_count_including_boundary_rechecks"] == slots[
        "partition_sample_count_including_boundary_rechecks"
    ]
    assert report["owned_segment_count"] == slots[
        "partition_owned_adjacent_sample_segment_count"
    ]
    assert report["boundary_recheck_count"] == slots[
        "conservative_boundary_recheck_count"
    ]
    assert report["boundary_rechecks"][0]["exact_match"] is True
    assert len(first.configuration_samples_by_partition) == slots["partition_count"]
    assert [len(rows) for rows in first.configuration_samples_by_partition] == [
        partition["bounded_sample_count"] for partition in intake["partitions"]
    ]
    assert [len(rows) for rows in first.sweep_envelopes_by_partition] == [
        partition["bounded_sample_count"] - 1 for partition in intake["partitions"]
    ]
    geometry = next(iter(
        first.configuration_samples_by_partition[0][0].geometry_by_body.values()
    )).geometry
    assert geometry.primitives[0].radius_mm == 3.75
    assert report["installed_geometry_collision_screening_executed"] is False
    assert report["controller_commands"] == report["wire_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


@pytest.mark.parametrize("collection", ("samples", "sweeps"))
def test_missing_evidence_row_rejects(tmp_path, qualified, collection):
    document = _manifest(qualified)
    document[collection] = document[collection][:-1]
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="coverage differs"):
        _load(tmp_path, qualified, document)


def test_crossed_profile_or_route_lineage_rejects(tmp_path, qualified):
    document = _manifest(qualified)
    document["partitioned_typing_collision_intake_sha256"] = "a" * 64
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="lineage differs"):
        _load(tmp_path, qualified, document)


def test_stale_manifest_rejects(tmp_path, qualified):
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="stale"):
        _load(
            tmp_path, qualified, _manifest(qualified),
            evaluated="2026-10-07T21:00:00.001000Z",
        )


def test_unbound_source_rejects(tmp_path, qualified):
    document = _manifest(qualified)
    document["sources"][0]["sha256"] = "b" * 64
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="unbound"):
        _load(tmp_path, qualified, document)


def test_crossed_sample_posture_rejects(tmp_path, qualified):
    document = _manifest(qualified)
    document["samples"][0]["sample_plan_sha256"] = document["samples"][1][
        "sample_plan_sha256"
    ]
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="posture lineage"):
        _load(tmp_path, qualified, document)


def test_endpoint_only_sweep_rejects(tmp_path, qualified):
    document = _manifest(qualified)
    document["sweeps"][0]["construction_method"] = "ENDPOINT_INTERPOLATION"
    document["sweeps"][0]["intermediate_observation_count"] = 0
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="endpoint-only"):
        _load(tmp_path, qualified, document)


def test_crossed_sweep_sample_pair_rejects(tmp_path, qualified):
    document = _manifest(qualified)
    document["sweeps"][0]["end_sample_sha256"] = document["sweeps"][1][
        "end_sample_sha256"
    ]
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="sample-pair lineage"):
        _load(tmp_path, qualified, document)


def test_negative_uncertainty_rejects(tmp_path, qualified):
    document = _manifest(qualified)
    document["samples"][0]["bodies"][0]["capsules"][0][
        "capture_uncertainty_mm"
    ] = -0.01
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="outside its bound"):
        _load(tmp_path, qualified, document)


def test_partition_boundary_geometry_mismatch_rejects(tmp_path, qualified):
    document = _manifest(qualified)
    successor_first = next(
        row for row in document["samples"]
        if row["partition_index"] == 1 and row["sample_sequence"] == 0
    )
    successor_first["bodies"][0]["capsules"][0]["start_mm"][0] += 1.0
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="shared-boundary"):
        _load(tmp_path, qualified, document)


def test_reordered_rows_reject(tmp_path, qualified):
    document = _manifest(qualified)
    document["sweeps"][0], document["sweeps"][1] = (
        document["sweeps"][1], document["sweeps"][0]
    )
    _rehash(document)
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="unexpected or duplicated"):
        _load(tmp_path, qualified, document)


def test_altered_file_bytes_reject_before_parse(tmp_path, qualified):
    document = _manifest(qualified)
    path, digest = _write(tmp_path, "cables.json", document)
    changed = copy.deepcopy(document)
    changed["cable_manifest_id"] = "altered"
    path.write_bytes(_canonical(changed))
    with pytest.raises(C03CableEnvelopeIntakeV1Error, match="file hash mismatch"):
        load_c03_cable_envelope_intake_v1(
            path, digest, qualified[0], qualified[1], evaluated_at_utc=EVALUATED
        )
