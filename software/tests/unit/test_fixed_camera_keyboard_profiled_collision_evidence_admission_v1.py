from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.fixed_camera_keyboard_profiled_collision_evidence_admission_v1 import (
    COMPLETION_NAMES,
    COMPLETION_SCHEMA,
    COMPLETION_STATUS,
    MANIFEST_NAME,
    RECEIPT_NAME,
    RECEIPT_STATUS,
    REVIEW_NAMES,
    REVIEW_SCHEMA,
    REVIEW_STATUS,
    STATUS,
    ZERO_AUTHORITY,
    FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error,
    admit_fixed_camera_keyboard_profiled_collision_evidence_v1,
)
from rocell.application.fk_collision_pose_adapter import (
    MeasuredConfigurationGeometryBinding,
    MeasuredRigidAttachmentBinding,
)

from test_fixed_camera_keyboard_profiled_collision_evidence_template_v1 import (
    PROFILES,
    _call as template_call,
    _source,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def _meaning(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_bytes(_canonical(value) + b"\n")


def _geometry(profile: str) -> dict[str, object]:
    return {
        "evidence_state": "ACCEPTED_MEASURED",
        "source_reference": f"reviewed {profile} metrology",
        "primitives": [
            {
                "kind": "capsule",
                "start_mm": [0.0, 0.0, 0.0],
                "end_mm": [0.0, 0.0, 12.0],
                "radius_mm": 3.0,
            }
        ],
    }


def _completion(template: dict, profile: str) -> dict:
    result = copy.deepcopy(template)
    result.pop("profiled_collision_evidence_template_sha256")
    result.pop("completion_rule")
    result.pop("next_required_stage")
    result["schema"] = COMPLETION_SCHEMA
    result["status"] = COMPLETION_STATUS
    result["source_profiled_collision_evidence_template_sha256"] = template[
        "profiled_collision_evidence_template_sha256"
    ]
    result["measurement_producer_id"] = f"metrologist:{profile}"
    result["authority"] = dict(ZERO_AUTHORITY)
    source = template["accepted_profile_source_sha256_values"][0]
    for row in result["rigid_attachment_bindings"]:
        row["anchor_link_frame"] = "base_link"
        row["anchor_t_parent"] = {
            "parent_frame": "base_link",
            "child_frame": row["parent_frame"],
            "rotation_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "translation_mm": [1.0, 2.0, 3.0],
        }
        row["source_sha256"] = source
        row["source_reference"] = f"reviewed {profile} attachment metrology"
        row["evidence_state"] = "ACCEPTED_MEASURED"
    for partition in result["partitions"]:
        for sample in partition["configuration_samples"]:
            for body in sample["geometry_by_body"]:
                body["geometry_root_frame"] = _geometry(profile)
                body["source_sha256"] = source
                body["evidence_state"] = "ACCEPTED_MEASURED"
        for segment in partition["configuration_sweep_envelopes"]:
            for body in segment["envelope_by_body"]:
                body["geometry_root_frame"] = _geometry(profile)
                body["source_sha256"] = source
                body["evidence_state"] = "ACCEPTED_MEASURED"
    result["completion_sha256"] = _meaning(result)
    return result


def _review(profile: str, completion: dict, completion_path: Path) -> dict:
    result = {
        "schema": REVIEW_SCHEMA,
        "status": REVIEW_STATUS,
        "profile": profile,
        "completion_sha256": completion["completion_sha256"],
        "completion_file_sha256": _file(completion_path),
        "measurement_producer_id": completion["measurement_producer_id"],
        "independent_reviewer_id": f"reviewer:{profile}",
        "review_decision": "ACCEPT",
        "review_source_sha256": hashlib.sha256(
            f"review:{profile}".encode()
        ).hexdigest(),
        "physical_authority": False,
    }
    return {**result, "review_sha256": _meaning(result)}


def _bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    templates = template_call(tmp_path, _source(tmp_path, monkeypatch))
    evidence_dir = tmp_path / "completed-evidence"
    evidence_dir.mkdir()
    completion_paths = {}
    review_paths = {}
    completions = {}
    for profile in PROFILES:
        completion = _completion(dict(templates.templates[profile]), profile)
        completion_path = evidence_dir / COMPLETION_NAMES[profile]
        _write(completion_path, completion)
        review = _review(profile, completion, completion_path)
        review_path = evidence_dir / REVIEW_NAMES[profile]
        _write(review_path, review)
        completion_paths[profile] = completion_path
        review_paths[profile] = review_path
        completions[profile] = completion
    return templates, completion_paths, review_paths, completions


def _call(tmp_path: Path, templates, completion_paths, review_paths):
    return admit_fixed_camera_keyboard_profiled_collision_evidence_v1(
        templates.receipt_path,
        expected_template_receipt_file_sha256=_file(templates.receipt_path),
        template_manifest_path=templates.manifest_path,
        expected_template_manifest_file_sha256=_file(templates.manifest_path),
        template_paths=templates.template_paths,
        expected_template_file_sha256={
            profile: _file(templates.template_paths[profile]) for profile in PROFILES
        },
        completion_paths=completion_paths,
        expected_completion_file_sha256={
            profile: _file(completion_paths[profile]) for profile in PROFILES
        },
        review_paths=review_paths,
        expected_review_file_sha256={
            profile: _file(review_paths[profile]) for profile in PROFILES
        },
        output_directory=tmp_path / "admitted-evidence",
    )


def test_exact_reviewed_profile_evidence_decodes_typed_evaluator_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates, completions, reviews, _ = _bundle(tmp_path, monkeypatch)

    result = _call(tmp_path, templates, completions, reviews)

    assert result.manifest["status"] == STATUS
    assert result.receipt["status"] == RECEIPT_STATUS
    assert result.manifest_path.name == MANIFEST_NAME
    assert result.receipt_path.name == RECEIPT_NAME
    assert result.manifest["independent_reviews_verified"] is True
    assert result.manifest["authority"]["physical_authority"] is False
    assert (
        result.admitted_profiles["no_attachment"].completion_sha256
        != result.admitted_profiles["stylus_attachment"].completion_sha256
    )
    for profile in PROFILES:
        admitted = result.admitted_profiles[profile]
        assert all(
            isinstance(item, MeasuredRigidAttachmentBinding)
            for item in admitted.attachment_bindings
        )
        assert all(
            isinstance(item, MeasuredConfigurationGeometryBinding)
            for partition in admitted.configuration_geometry_by_partition
            for sample in partition
            for item in sample.values()
        )
        assert len(admitted.configuration_geometry_by_partition) == len(
            templates.templates[profile]["partitions"]
        )


def test_unaccepted_measurement_source_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates, completions, reviews, values = _bundle(tmp_path, monkeypatch)
    profile = "no_attachment"
    completion = values[profile]
    completion["partitions"][0]["configuration_samples"][0]["geometry_by_body"][0][
        "source_sha256"
    ] = "f" * 64
    completion["completion_sha256"] = _meaning(
        {key: value for key, value in completion.items() if key != "completion_sha256"}
    )
    _write(completions[profile], completion)
    review = _review(profile, completion, completions[profile])
    _write(reviews[profile], review)

    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error,
        match="absent from installed profile",
    ):
        _call(tmp_path, templates, completions, reviews)
    assert not (tmp_path / "admitted-evidence").exists()


def test_producer_cannot_review_either_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates, completions, reviews, values = _bundle(tmp_path, monkeypatch)
    profile = "stylus_attachment"
    review = json.loads(reviews[profile].read_bytes())
    review["independent_reviewer_id"] = values[profile]["measurement_producer_id"]
    review["review_sha256"] = _meaning(
        {key: value for key, value in review.items() if key != "review_sha256"}
    )
    _write(reviews[profile], review)

    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error,
        match="not an independent acceptance",
    ):
        _call(tmp_path, templates, completions, reviews)


def test_crossed_profile_completion_names_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates, completions, reviews, _ = _bundle(tmp_path, monkeypatch)
    crossed = {
        "no_attachment": completions["stylus_attachment"],
        "stylus_attachment": completions["no_attachment"],
    }
    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error,
        match="file names differ",
    ):
        _call(tmp_path, templates, crossed, reviews)


def test_existing_destination_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates, completions, reviews, _ = _bundle(tmp_path, monkeypatch)
    destination = tmp_path / "admitted-evidence"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error,
        match="already exists",
    ):
        _call(tmp_path, templates, completions, reviews)
    assert sentinel.read_text() == "keep"
