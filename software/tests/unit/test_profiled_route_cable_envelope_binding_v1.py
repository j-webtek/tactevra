from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.installed_cable_envelope_intake_v1 import (
    InstalledCableEnvelopeIntakeV1,
)
from rocell.application.installed_geometry_cable_rehearsal_v1 import (
    build_synthetic_installed_collision_profile_v1,
)
from rocell.application.profiled_route_cable_envelope_binding_v1 import (
    ProfiledRouteCableEnvelopeBindingV1Error,
    bind_profiled_route_cable_envelope_v1,
)
from rocell.application.partitioned_typing_collision_intake_v1 import (
    READY_STATUS,
    SCHEMA as PARTITION_SCHEMA,
)


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    ROOT
    / "software/ai/schemas/profiled_route_cable_envelope_binding_v1.schema.json"
)
INTAKE_SCHEMA_PATH = (
    ROOT / "software/ai/schemas/installed_cable_envelope_intake_v1.schema.json"
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _reseal_document(document: dict) -> None:
    core = dict(document)
    core.pop("partitioned_typing_collision_intake_sha256", None)
    document["partitioned_typing_collision_intake_sha256"] = _sha(core)


def _partition_document() -> dict:
    partitions = []
    start = 0
    for partition_index, count in enumerate((255, 73)):
        plan = [
            {
                "sample_sequence": local,
                "source_segment_index": start + max(0, local - 1),
                "joint_positions_rad": {
                    "joint": float(
                        start - 1
                        if partition_index > 0 and local == 0
                        else start + max(0, local - 1)
                    )
                },
            }
            for local in range(count + 1)
        ]
        core = {
            "partition_index": partition_index,
            "source_result_start_index": start,
            "source_result_end_index_exclusive": start + count,
            "source_result_count": count,
            "bounded_joint_sample_plan": plan,
        }
        partitions.append({**core, "partition_intake_sha256": _sha(core)})
        start += count
    boundary_core = {
        "predecessor_partition_index": 0,
        "successor_partition_index": 1,
        "source_boundary_result_index": 254,
        "predecessor_terminal_sample_sha256": _sha(
            partitions[0]["bounded_joint_sample_plan"][-1]
        ),
        "successor_boundary_recheck_sample_sha256": _sha(
            partitions[1]["bounded_joint_sample_plan"][0]
        ),
        "maximum_joint_difference_rad": 0.0,
        "boundary_recheck_required": True,
        "extra_zero_length_sweep_envelope_required": False,
    }
    core = {
        "schema": PARTITION_SCHEMA,
        "status": READY_STATUS,
        "installed_collision_profile_sha256": "0" * 64,
        "partitions": partitions,
        "boundary_lineage": [
            {**boundary_core, "boundary_lineage_sha256": _sha(boundary_core)}
        ],
        "required_evidence_slots": {"route_segment_count": 328},
    }
    return {**core, "partitioned_typing_collision_intake_sha256": _sha(core)}


def _document_and_envelope():
    document = _partition_document()
    profile = build_synthetic_installed_collision_profile_v1(ROOT)
    document["installed_collision_profile_sha256"] = profile.content_sha256
    _reseal_document(document)

    route = list(document["partitions"][0]["bounded_joint_sample_plan"])
    route.extend(document["partitions"][1]["bounded_joint_sample_plan"][1:])
    postures = tuple(
        {
            "sequence": sequence,
            "posture_id": f"route-posture-{sequence:04d}",
            "joint_state_sha256": _sha(sample["joint_positions_rad"]),
            "capsules": [
                {
                    "kind": "capsule",
                    "start_mm": [50000.0 + sequence, 0.0, 0.0],
                    "end_mm": [50001.0 + sequence, 0.0, 0.0],
                    "radius_mm": 0.5,
                }
            ],
        }
        for sequence, sample in enumerate(route)
    )
    sweeps = tuple(
        {
            "sequence": sequence,
            "start_posture_id": postures[sequence]["posture_id"],
            "end_posture_id": postures[sequence + 1]["posture_id"],
            "capsules": [
                {
                    "kind": "capsule",
                    "start_mm": [50000.0 + sequence, 0.0, 0.0],
                    "end_mm": [50002.0 + sequence, 0.0, 0.0],
                    "radius_mm": 0.75,
                }
            ],
        }
        for sequence in range(len(route) - 1)
    )
    source = sorted(profile.source_bindings.values())[0]
    envelope = InstalledCableEnvelopeIntakeV1(
        profile,
        "attachment:moving_camera_cable",
        source,
        0.5,
        postures,
        sweeps,
    )
    return document, envelope


def test_binds_all_329_route_samples_and_328_segments() -> None:
    document, envelope = _document_and_envelope()

    result = bind_profiled_route_cable_envelope_v1(document, envelope)

    assert result["route_sample_count"] == 329
    assert result["route_segment_count"] == 328
    assert result["installed_collision_profile_sha256"] == profile_hash(document)
    assert result["authority"]["physical_authority"] is False
    assert result["blockers"] == [
        "REVIEWED_INSTALLED_CONFIGURATION_ENVELOPE_EVIDENCE_REQUIRED"
    ]
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)
    jsonschema.Draft202012Validator(
        json.loads(INTAKE_SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(envelope.to_dict())


def profile_hash(document: dict) -> str:
    return document["installed_collision_profile_sha256"]


def test_rejects_incomplete_route_envelope_coverage() -> None:
    document, envelope = _document_and_envelope()
    shortened = InstalledCableEnvelopeIntakeV1(
        envelope.profile,
        envelope.sampled_body_id,
        envelope.source_sha256,
        envelope.maximum_uncertainty_mm,
        envelope.postures[:-1],
        envelope.swept_envelopes[:-1],
    )

    with pytest.raises(
        ProfiledRouteCableEnvelopeBindingV1Error,
        match="does not cover every route sample",
    ):
        bind_profiled_route_cable_envelope_v1(document, shortened)


def test_rejects_posture_reuse_at_a_different_joint_state() -> None:
    document, envelope = _document_and_envelope()
    postures = copy.deepcopy(envelope.postures)
    postures[100]["joint_state_sha256"] = "f" * 64
    crossed = InstalledCableEnvelopeIntakeV1(
        envelope.profile,
        envelope.sampled_body_id,
        envelope.source_sha256,
        envelope.maximum_uncertainty_mm,
        postures,
        envelope.swept_envelopes,
    )

    with pytest.raises(
        ProfiledRouteCableEnvelopeBindingV1Error,
        match="posture differs from route sample: 100",
    ):
        bind_profiled_route_cable_envelope_v1(document, crossed)


def test_rejects_crossed_attachment_profile() -> None:
    document, envelope = _document_and_envelope()
    document["installed_collision_profile_sha256"] = "f" * 64
    _reseal_document(document)

    with pytest.raises(
        ProfiledRouteCableEnvelopeBindingV1Error,
        match="profile lineage differ",
    ):
        bind_profiled_route_cable_envelope_v1(document, envelope)


def test_rejects_partition_boundary_tamper() -> None:
    document, envelope = _document_and_envelope()
    document["boundary_lineage"][0]["maximum_joint_difference_rad"] = 0.01
    _reseal_document(document)

    with pytest.raises(
        ProfiledRouteCableEnvelopeBindingV1Error,
        match="partition boundary 0 hash differs",
    ):
        bind_profiled_route_cable_envelope_v1(document, envelope)
