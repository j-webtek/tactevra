from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import jsonschema
import pytest

from rocell.geometry import Vec3
from rocell.simulation.collision import (
    CapsuleMm,
    CollisionEvidenceState,
    SampledCollisionGeometry,
)
from rocell.application.conservative_segment_sweep_qualification import (
    MeasuredConfigurationSweepEnvelopeBinding,
)
from rocell.application.fixed_camera_keyboard_profiled_collision_evidence_admission_v1 import (
    RECEIPT_SCHEMA as ADMISSION_RECEIPT_SCHEMA,
    RECEIPT_STATUS as ADMISSION_RECEIPT_STATUS,
    SCHEMA as ADMISSION_SCHEMA,
    STATUS as ADMISSION_STATUS,
    ZERO_AUTHORITY as ADMISSION_ZERO_AUTHORITY,
    AdmittedProfileCollisionEvidenceV1,
    FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1,
)
from rocell.application.fk_collision_pose_adapter import (
    MeasuredConfigurationGeometryBinding,
)

from rocell.application.installed_cable_envelope_intake_v1 import (
    InstalledCableEnvelopeIntakeV1,
)
from rocell.application.installed_geometry_cable_rehearsal_v1 import (
    build_synthetic_installed_collision_profile_v1,
)
from rocell.application.profiled_route_cable_envelope_binding_v1 import (
    ProfiledRouteCableEnvelopeBindingV1Error,
    bind_admitted_profiled_route_configuration_envelope_v1,
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
ADMITTED_SCHEMA_PATH = ROOT / (
    "software/ai/schemas/"
    "admitted_profiled_route_configuration_envelope_binding_v1.schema.json"
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
        "required_evidence_slots": {
            "unique_route_configuration_count": 329,
            "route_segment_count": 328,
        },
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


def _reviewed_admission(document: dict, profile):
    source = sorted(profile.source_bindings.values())[0]
    geometry_partitions = []
    sweep_partitions = []
    for partition_index, partition in enumerate(document["partitions"]):
        samples = partition["bounded_joint_sample_plan"]
        geometry_rows = []
        for sample in samples:
            position = float(sample["joint_positions_rad"]["joint"])
            geometry = SampledCollisionGeometry(
                (
                    CapsuleMm(
                        Vec3(position, 0.0, 0.0),
                        Vec3(position + 1.0, 0.0, 0.0),
                        1.0,
                    ),
                ),
                CollisionEvidenceState.ACCEPTED_MEASURED,
                "independently reviewed route posture",
            )
            geometry_rows.append(
                MappingProxyType(
                    {
                        "attachment:moving_camera_cable": (
                            MeasuredConfigurationGeometryBinding(
                                "attachment:moving_camera_cable", geometry, source
                            )
                        )
                    }
                )
            )
        sweep_rows = []
        for sequence, (start, end) in enumerate(zip(samples, samples[1:])):
            geometry = SampledCollisionGeometry(
                (
                    CapsuleMm(
                        Vec3(float(start["source_segment_index"]), 0.0, 0.0),
                        Vec3(float(end["source_segment_index"]) + 1.0, 0.0, 0.0),
                        1.5,
                    ),
                ),
                CollisionEvidenceState.ACCEPTED_MEASURED,
                "independently reviewed route sweep",
            )
            sweep_rows.append(
                MappingProxyType(
                    {
                        "attachment:moving_camera_cable": (
                            MeasuredConfigurationSweepEnvelopeBinding(
                                sequence,
                                _sha(start),
                                _sha(end),
                                "attachment:moving_camera_cable",
                                geometry,
                                source,
                            )
                        )
                    }
                )
            )
        geometry_partitions.append(tuple(geometry_rows))
        sweep_partitions.append(tuple(sweep_rows))

    completion = "c" * 64
    review = "d" * 64
    selected = AdmittedProfileCollisionEvidenceV1(
        "stylus_attachment",
        (),
        tuple(geometry_partitions),
        tuple(sweep_partitions),
        completion,
        review,
    )
    other = AdmittedProfileCollisionEvidenceV1(
        "no_attachment", (), (), (), "a" * 64, "b" * 64
    )
    manifest_core = {
        "schema": ADMISSION_SCHEMA,
        "status": ADMISSION_STATUS,
        "source_profiled_collision_evidence_template_manifest_sha256": "e" * 64,
        "profiles": {
            "no_attachment": {
                "installed_collision_profile_sha256": "f" * 64,
                "completion_sha256": other.completion_sha256,
                "review_sha256": other.review_sha256,
                "required_evidence_slots": document["required_evidence_slots"],
            },
            "stylus_attachment": {
                "installed_collision_profile_sha256": profile.content_sha256,
                "completion_sha256": completion,
                "review_sha256": review,
                "required_evidence_slots": document["required_evidence_slots"],
            },
        },
        "profile_separation_preserved": True,
        "independent_reviews_verified": True,
        "typed_evaluator_inputs_decoded": True,
        "next_required_stage": "RUN_PROFILE_BOUND_PARTITION_COLLISION_EVALUATORS",
        "authority": dict(ADMISSION_ZERO_AUTHORITY),
    }
    manifest = {
        **manifest_core,
        "profiled_collision_evidence_admission_manifest_sha256": _sha(manifest_core),
    }
    receipt = {
        "schema": ADMISSION_RECEIPT_SCHEMA,
        "status": ADMISSION_RECEIPT_STATUS,
        "profile_separation_preserved": True,
        "independent_reviews_verified": True,
        "authority": dict(ADMISSION_ZERO_AUTHORITY),
    }
    return FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1(
        ROOT,
        ROOT / "manifest.json",
        ROOT / "receipt.json",
        MappingProxyType(
            {"no_attachment": other, "stylus_attachment": selected}
        ),
        MappingProxyType(manifest),
        MappingProxyType(receipt),
    )


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


def test_binds_reviewed_admitted_evidence_to_exact_route() -> None:
    document, envelope = _document_and_envelope()
    admission = _reviewed_admission(document, envelope.profile)

    result = bind_admitted_profiled_route_configuration_envelope_v1(
        document,
        envelope.profile,
        admission,
        attachment_profile="stylus_attachment",
    )

    assert result["route_sample_count"] == 329
    assert result["route_segment_count"] == 328
    assert result["independent_review_sha256"] == "d" * 64
    assert result["authority"]["physical_authority"] is False
    jsonschema.Draft202012Validator(
        json.loads(ADMITTED_SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)


def test_rejects_changed_rechecked_boundary_geometry() -> None:
    document, envelope = _document_and_envelope()
    admission = _reviewed_admission(document, envelope.profile)
    admitted = admission.admitted_profiles["stylus_attachment"]
    partitions = [list(partition) for partition in admitted.configuration_geometry_by_partition]
    binding = partitions[1][0]["attachment:moving_camera_cable"]
    changed = SampledCollisionGeometry(
        (CapsuleMm(Vec3(9000.0, 0.0, 0.0), Vec3(9001.0, 0.0, 0.0), 1.0),),
        CollisionEvidenceState.ACCEPTED_MEASURED,
        binding.geometry.source_reference,
    )
    partitions[1][0] = MappingProxyType(
        {
            "attachment:moving_camera_cable": MeasuredConfigurationGeometryBinding(
                binding.body_id, changed, binding.source_sha256
            )
        }
    )
    crossed = AdmittedProfileCollisionEvidenceV1(
        admitted.profile,
        admitted.attachment_bindings,
        tuple(tuple(partition) for partition in partitions),
        admitted.sweep_envelopes_by_partition,
        admitted.completion_sha256,
        admitted.review_sha256,
    )
    object.__setattr__(
        admission,
        "admitted_profiles",
        MappingProxyType(
            {
                **admission.admitted_profiles,
                "stylus_attachment": crossed,
            }
        ),
    )

    with pytest.raises(
        ProfiledRouteCableEnvelopeBindingV1Error,
        match="rechecked boundary geometry differs",
    ):
        bind_admitted_profiled_route_configuration_envelope_v1(
            document,
            envelope.profile,
            admission,
            attachment_profile="stylus_attachment",
        )
