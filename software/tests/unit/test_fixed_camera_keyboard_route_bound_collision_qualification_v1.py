from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from rocell.application.fixed_camera_keyboard_route_bound_collision_qualification_v1 import (
    FixedCameraKeyboardRouteBoundCollisionQualificationV1Error,
    qualify_fixed_camera_keyboard_route_bound_collisions_v1,
)
from rocell.application.fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
    STATUS_BLOCKED as RECONSTRUCTION_BLOCKED,
    STATUS_READY as RECONSTRUCTION_READY,
    STATUS_REJECTED as RECONSTRUCTION_REJECTED,
)
from rocell.application.partitioned_typing_collision_intake_v1 import (
    READY_STATUS,
    SCHEMA as PARTITION_SCHEMA,
)
from rocell.application.profiled_route_cable_envelope_binding_v1 import (
    ADMITTED_SCHEMA,
    ADMITTED_STATUS,
    ZERO_AUTHORITY as ROUTE_BINDING_ZERO_AUTHORITY,
)


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / (
    "software/ai/schemas/"
    "fixed_camera_keyboard_route_bound_collision_qualification_v1.schema.json"
)
PROFILES = ("no_attachment", "stylus_attachment")


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


def _fixtures():
    documents = {}
    evidence = {}
    installed = {}
    bindings = {}
    for profile_index, profile_name in enumerate(PROFILES):
        installed_hash = str(profile_index + 1) * 64
        completion = str(profile_index + 3) * 64
        review = str(profile_index + 5) * 64
        source = str(profile_index + 7) * 64
        policy = SimpleNamespace(
            minimum_separation_mm=2.0,
            geometry_uncertainty_mm_per_body=0.5,
            pose_uncertainty_mm_per_body=0.25,
            source_reference="reviewed-installed-policy",
        )
        installed[profile_name] = SimpleNamespace(
            content_sha256=installed_hash,
            clearance_policy=policy,
        )
        evidence[profile_name] = SimpleNamespace(
            profile=profile_name,
            completion_sha256=completion,
            review_sha256=review,
        )
        route = [
            {
                "sample_sequence": sequence,
                "joint_positions_rad": {"joint": float(sequence)},
            }
            for sequence in range(329)
        ]
        partition_core = {
            "schema": PARTITION_SCHEMA,
            "status": READY_STATUS,
            "installed_collision_profile_sha256": installed_hash,
            "partitions": [
                {
                    "partition_index": 0,
                    "bounded_joint_sample_plan": route,
                }
            ],
        }
        document = {
            **partition_core,
            "partitioned_typing_collision_intake_sha256": _sha(partition_core),
        }
        documents[profile_name] = document
        posture_rows = [
            {
                "route_sample_sequence": sequence,
                "route_sample_sha256": _sha(sample),
                "joint_state_sha256": _sha(sample["joint_positions_rad"]),
                "configuration_geometry_sha256": _sha(
                    {"profile": profile_name, "posture": sequence}
                ),
                "source_sha256": source,
                "primitive_count": 1,
            }
            for sequence, sample in enumerate(route)
        ]
        segment_rows = [
            {
                "route_segment_sequence": sequence,
                "start_route_sample_sha256": _sha(route[sequence]),
                "end_route_sample_sha256": _sha(route[sequence + 1]),
                "sweep_geometry_sha256": _sha(
                    {"profile": profile_name, "segment": sequence}
                ),
                "source_sha256": source,
                "primitive_count": 1,
            }
            for sequence in range(328)
        ]
        binding_core = {
            "schema": ADMITTED_SCHEMA,
            "status": ADMITTED_STATUS,
            "evidence_class": "REVIEWED_INSTALLED",
            "attachment_profile": profile_name,
            "installed_collision_profile_sha256": installed_hash,
            "partitioned_typing_collision_intake_sha256": document[
                "partitioned_typing_collision_intake_sha256"
            ],
            "profiled_collision_evidence_admission_manifest_sha256": "a" * 64,
            "completion_sha256": completion,
            "independent_review_sha256": review,
            "sampled_body_id": "attachment:moving_camera_cable",
            "accepted_source_sha256_values": [source],
            "clearance_policy": {
                "minimum_separation_mm": 2.0,
                "geometry_uncertainty_mm_per_body": 0.5,
                "pose_uncertainty_mm_per_body": 0.25,
                "source_reference": "reviewed-installed-policy",
            },
            "route_sample_count": 329,
            "route_segment_count": 328,
            "posture_bindings": posture_rows,
            "segment_bindings": segment_rows,
            "next_required_stage": "RUN_PROFILE_BOUND_PARTITION_COLLISION_EVALUATORS",
            "authority": dict(ROUTE_BINDING_ZERO_AUTHORITY),
        }
        bindings[profile_name] = {
            **binding_core,
            "admitted_profiled_route_configuration_envelope_binding_sha256": _sha(
                binding_core
            ),
        }
    return documents, evidence, installed, bindings


def _install_downstream_stubs(monkeypatch, reconstruction_status=RECONSTRUCTION_READY):
    calls = []

    def evaluate(context, snapshot, documents, evidence, installed):
        calls.append(("evaluate", context, snapshot, documents, evidence, installed))
        return {"profiled_partition_collision_evaluation_sha256": "b" * 64}

    def reconstruct(documents, evaluation):
        calls.append(("reconstruct", documents, evaluation))
        disposition = "REJECT" if reconstruction_status == RECONSTRUCTION_REJECTED else "BLOCKED"
        blocker = {
            RECONSTRUCTION_READY: "FRESH_OBSERVED_START_AND_ENTRY_QUALIFICATION_REQUIRED",
            RECONSTRUCTION_REJECTED: "PROFILE_BOUND_ROUTE_COLLISION_DETECTED",
            RECONSTRUCTION_BLOCKED: "PROFILE_BOUND_ROUTE_CLEARANCE_EVIDENCE_INCOMPLETE",
        }[reconstruction_status]
        return {
            "status": reconstruction_status,
            "disposition": disposition,
            "profiled_route_clearance_reconstruction_sha256": "c" * 64,
            "blockers": [blocker],
            "next_required_stage": "NEXT_STAGE",
        }

    monkeypatch.setattr(
        "rocell.application.fixed_camera_keyboard_profiled_partition_collision_evaluator_v1."
        "evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1",
        evaluate,
    )
    monkeypatch.setattr(
        "rocell.application.fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1."
        "reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1",
        reconstruct,
    )
    return calls


@pytest.mark.parametrize(
    ("reconstruction_status", "expected_status"),
    (
        (
            RECONSTRUCTION_READY,
            "ROUTE_BOUND_CLEARANCE_RECONSTRUCTED_FRESH_ENTRY_REQUIRED",
        ),
        (RECONSTRUCTION_REJECTED, "REJECTED_ROUTE_BOUND_COLLISION_DETECTED"),
        (
            RECONSTRUCTION_BLOCKED,
            "BLOCKED_ROUTE_BOUND_CLEARANCE_EVIDENCE_INCOMPLETE",
        ),
    ),
)
def test_route_bound_receipts_gate_evaluation_and_reconstruction(
    monkeypatch, reconstruction_status, expected_status
):
    documents, evidence, installed, bindings = _fixtures()
    calls = _install_downstream_stubs(monkeypatch, reconstruction_status)

    first = qualify_fixed_camera_keyboard_route_bound_collisions_v1(
        "context", "snapshot", documents, evidence, installed, bindings
    )
    second = qualify_fixed_camera_keyboard_route_bound_collisions_v1(
        "context", "snapshot", documents, evidence, installed, bindings
    )

    assert first == second
    assert first["status"] == expected_status
    assert first["exact_route_binding_verified_before_evaluation"] is True
    assert first["authority"]["physical_authority"] is False
    assert first["authority"]["controller_commands"] == []
    assert [call[0] for call in calls] == [
        "evaluate",
        "reconstruct",
        "evaluate",
        "reconstruct",
    ]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(first)


@pytest.mark.parametrize(
    "mutation",
    (
        "route_sample_hash",
        "route_segment_endpoint",
        "completion_lineage",
        "profile_crossing",
        "clearance_policy",
    ),
)
def test_tampered_or_crossed_binding_fails_before_evaluation(monkeypatch, mutation):
    documents, evidence, installed, bindings = _fixtures()
    calls = _install_downstream_stubs(monkeypatch)
    changed = copy.deepcopy(bindings)
    row = changed["no_attachment"]
    if mutation == "route_sample_hash":
        row["posture_bindings"][17]["route_sample_sha256"] = "f" * 64
    elif mutation == "route_segment_endpoint":
        row["segment_bindings"][23]["end_route_sample_sha256"] = "f" * 64
    elif mutation == "completion_lineage":
        row["completion_sha256"] = "f" * 64
    elif mutation == "profile_crossing":
        row["attachment_profile"] = "stylus_attachment"
    else:
        row["clearance_policy"]["minimum_separation_mm"] = 1.0
    core = dict(row)
    core.pop("admitted_profiled_route_configuration_envelope_binding_sha256")
    row["admitted_profiled_route_configuration_envelope_binding_sha256"] = _sha(core)

    with pytest.raises(
        FixedCameraKeyboardRouteBoundCollisionQualificationV1Error
    ):
        qualify_fixed_camera_keyboard_route_bound_collisions_v1(
            "context", "snapshot", documents, evidence, installed, changed
        )
    assert calls == []


def test_missing_profile_fails_closed_before_evaluation(monkeypatch):
    documents, evidence, installed, bindings = _fixtures()
    calls = _install_downstream_stubs(monkeypatch)
    bindings.pop("stylus_attachment")

    with pytest.raises(
        FixedCameraKeyboardRouteBoundCollisionQualificationV1Error,
        match="exact supported profile set",
    ):
        qualify_fixed_camera_keyboard_route_bound_collisions_v1(
            "context", "snapshot", documents, evidence, installed, bindings
        )
    assert calls == []
