from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

import pytest

from rocell.calibration.static_camera_intrinsics import (
    MAX_INTRINSICS_IMAGES,
    MAX_STATIC_CAMERA_INTRINSICS_BYTES,
    STATIC_CAMERA_INTRINSICS_ASSESSMENT_SCHEMA,
    STATIC_CAMERA_INTRINSICS_SCHEMA,
    TARGET_PROFILE_ID,
    TARGET_PROFILE_SOURCE_SHA256,
    StaticCameraIntrinsicsError,
    assess_static_camera_intrinsics_rehearsal,
    load_static_camera_intrinsics_rehearsal,
    parse_static_camera_intrinsics_json,
)
from rocell.vision.camera_profile import load_camera_profile


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "camera"
FIXTURE_PATH = FIXTURE_ROOT / "b0477_synthetic_intrinsics_rehearsal.json"


def _document() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _seal(document: dict[str, Any]) -> None:
    document["integrity_sha256"] = _canonical_hash(
        {key: value for key, value in document.items() if key != "integrity_sha256"}
    )


def _refresh_derived(document: dict[str, Any]) -> None:
    camera = document["camera_binding"]
    camera["settings_binding_sha256"] = _canonical_hash(
        {
            "persistent_camera_identity_sha256": camera[
                "persistent_camera_identity_sha256"
            ],
            "mode": camera["mode"],
            "focus_lock_evidence_sha256": camera["focus_lock_evidence_sha256"],
            "aperture_lock_evidence_sha256": camera[
                "aperture_lock_evidence_sha256"
            ],
            "controls_snapshot_sha256": camera["controls_snapshot_sha256"],
        }
    )
    target = document["calibration_target"]
    target["definition_sha256"] = _canonical_hash(target["definition"])
    print_scale = target["print_scale_verification"]
    print_scale["evidence_manifest_sha256"] = _canonical_hash(
        {
            "evidence_state": print_scale["evidence_state"],
            "measurement_count": print_scale["measurement_count"],
            "evidence_file_sha256": print_scale["evidence_file_sha256"],
        }
    )
    dataset = document["dataset"]
    dataset["images_manifest_sha256"] = _canonical_hash(dataset["images"])
    dataset["split_commitment_sha256"] = _canonical_hash(dataset["splits"])
    solution = document["solution"]
    solution["input_bindings_sha256"] = _canonical_hash(
        {
            "profile_id": document["profile_binding"]["profile_id"],
            "profile_source_file_sha256": document["profile_binding"][
                "profile_source_file_sha256"
            ],
            "persistent_camera_identity_sha256": camera[
                "persistent_camera_identity_sha256"
            ],
            "settings_binding_sha256": camera["settings_binding_sha256"],
            "board_definition_sha256": target["definition_sha256"],
            "print_scale_evidence_manifest_sha256": print_scale[
                "evidence_manifest_sha256"
            ],
            "images_manifest_sha256": dataset["images_manifest_sha256"],
            "split_commitment_sha256": dataset["split_commitment_sha256"],
        }
    )
    residuals = solution["per_view_residuals"]
    training = [
        item["reprojection_rms_px"]
        for item in residuals
        if item["split"] == "TRAINING"
    ]
    held_out = [
        item["reprojection_rms_px"]
        for item in residuals
        if item["split"] == "HELD_OUT"
    ]

    def p95(values: list[float]) -> float:
        return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)]

    solution["aggregate_residuals"] = {
        "training_rms_px": math.sqrt(
            sum(value * value for value in training) / len(training)
        ),
        "training_p95_px": p95(training),
        "held_out_rms_px": math.sqrt(
            sum(value * value for value in held_out) / len(held_out)
        ),
        "held_out_p95_px": p95(held_out),
        "maximum_view_rms_px": max(training + held_out),
    }
    _seal(document)


def _payload(document: object) -> bytes:
    return json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")


def test_nominal_rehearsal_binds_every_input_but_grants_no_authority() -> None:
    artifact = load_static_camera_intrinsics_rehearsal(
        FIXTURE_PATH.name, fixture_root=FIXTURE_ROOT
    )
    assessment = assess_static_camera_intrinsics_rehearsal(
        artifact, purchased_profile=load_camera_profile()
    )

    assert artifact.source_path == FIXTURE_PATH.resolve()
    assert artifact.artifact_class == "SYNTHETIC_REHEARSAL_ONLY"
    assert artifact.profile_id == TARGET_PROFILE_ID
    assert artifact.profile_source_file_sha256 == TARGET_PROFILE_SOURCE_SHA256
    assert len(artifact.training_image_ids) == 24
    assert len(artifact.held_out_image_ids) == 8
    assert artifact.board.maximum_corner_count == 88
    assert artifact.mode.to_dict() == {
        "width_px": 5472,
        "height_px": 3648,
        "fps": 9.0,
        "pixel_format": "YUY2",
    }
    assert artifact.controls_snapshot_sha256 == _document()["camera_binding"][
        "controls_snapshot_sha256"
    ]
    assert artifact.persistent_camera_identity_sha256 == (
        "ba5a62b5a58d06721fa4086aa1ed822988b46a072276f5f3e75284961d5b2a6e"
    )
    assert artifact.controls_snapshot_sha256 == (
        "993f750d48b8d3aafbf15b87a60c68ab7b23f93c5e61e6861e25cedf712ac7f8"
    )
    assert len(artifact.focus_lock_evidence_sha256) == 64
    assert len(artifact.aperture_lock_evidence_sha256) == 64
    assert artifact.distortion_model == "OPENCV_RATIONAL_POLYNOMIAL_8"
    assert len(artifact.distortion_coefficients) == 8
    assert len(artifact.camera_matrix_row_major) == 9
    assert artifact.valid_pixel_roi == (16, 14, 5440, 3620)
    assert artifact.output_crop == (32, 24, 5408, 3600)
    assert len(artifact.per_view_residuals) == len(artifact.images) == 32
    assert artifact.physical_calibration_valid is False
    assert artifact.commissioned is False
    assert artifact.robot_motion_authority is False
    assert artifact.contact_authority is False

    report = assessment.to_dict()
    assert report["schema"] == STATIC_CAMERA_INTRINSICS_ASSESSMENT_SCHEMA
    assert assessment.structural_gates_passed is True
    assert assessment.status == "SYNTHETIC_REHEARSAL_ONLY"
    assert assessment.thresholds_authority == (
        "SYNTHETIC_REHEARSAL_NOT_PHYSICALLY_APPROVED"
    )
    assert assessment.physical_calibration_valid is False
    assert assessment.commissioned is False
    assert assessment.hardware_accessed is False
    assert assessment.camera_frames_requested == 0
    assert assessment.arm_motion_commands == 0
    assert assessment.contact_commands == 0
    assert assessment.robot_motion_authority is False
    assert assessment.contact_authority is False
    assert assessment.physical_release_effect == "NONE"
    assert len(assessment.canonical_sha256) == 64


def test_fixture_profile_source_hash_is_the_exact_current_profile_bytes() -> None:
    profile = load_camera_profile()
    assert profile.source_file_sha256 == TARGET_PROFILE_SOURCE_SHA256
    assert profile.profile_id == TARGET_PROFILE_ID


def test_models_and_assessment_are_frozen() -> None:
    artifact = parse_static_camera_intrinsics_json(FIXTURE_PATH.read_bytes())
    assessment = assess_static_camera_intrinsics_rehearsal(artifact)

    with pytest.raises(FrozenInstanceError):
        artifact.artifact_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        artifact.images[0].split = "HELD_OUT"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        assessment.physical_calibration_valid = True  # type: ignore[misc]


def test_canonical_digest_is_semantic_and_source_digest_is_byte_exact() -> None:
    document = _document()
    compact = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    pretty = json.dumps(document, indent=7, ensure_ascii=False).encode("utf-8")

    compact_artifact = parse_static_camera_intrinsics_json(compact)
    pretty_artifact = parse_static_camera_intrinsics_json(pretty)

    assert compact_artifact.canonical_sha256 == pretty_artifact.canonical_sha256
    assert compact_artifact.source_file_sha256 != pretty_artifact.source_file_sha256
    assert compact_artifact.source_file_sha256 == hashlib.sha256(compact).hexdigest()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda doc: doc["profile_binding"].__setitem__("profile_id", "wrong"),
            "profile_id",
        ),
        (
            lambda doc: doc["profile_binding"].__setitem__(
                "profile_source_file_sha256", "1" * 64
            ),
            "profile_source_file_sha256",
        ),
        (
            lambda doc: doc["camera_binding"]["mode"].__setitem__(
                "width_px", 3840
            ),
            "mode.width_px",
        ),
        (
            lambda doc: doc["camera_binding"]["mode"].__setitem__(
                "pixel_format", "MJPG"
            ),
            "pixel_format",
        ),
        (
            lambda doc: doc["camera_binding"].__setitem__(
                "settings_binding_sha256", "2" * 64
            ),
            "settings binding hash mismatch",
        ),
        (
            lambda doc: doc["calibration_target"].__setitem__(
                "definition_sha256", "3" * 64
            ),
            "board definition hash mismatch",
        ),
        (
            lambda doc: doc["calibration_target"][
                "print_scale_verification"
            ].__setitem__("evidence_manifest_sha256", "4" * 64),
            "print-scale evidence manifest hash mismatch",
        ),
        (
            lambda doc: doc["dataset"].__setitem__(
                "images_manifest_sha256", "5" * 64
            ),
            "image manifest hash mismatch",
        ),
        (
            lambda doc: doc["dataset"].__setitem__(
                "split_commitment_sha256", "6" * 64
            ),
            "split commitment hash mismatch",
        ),
        (
            lambda doc: doc["solution"].__setitem__(
                "input_bindings_sha256", "7" * 64
            ),
            "input bindings hash mismatch",
        ),
        (
            lambda doc: doc["solution"]["undistortion_map"].__setitem__(
                "width_px", 2736
            ),
            "undistortion_map.width_px",
        ),
    ],
)
def test_wrong_profile_mode_and_binding_hashes_fail_closed(
    mutation: Callable[[dict[str, Any]], object], message: str
) -> None:
    document = deepcopy(_document())
    mutation(document)
    _seal(document)

    with pytest.raises(StaticCameraIntrinsicsError, match=message):
        parse_static_camera_intrinsics_json(_payload(document))


def test_image_byte_hash_change_is_detected_by_manifest() -> None:
    document = deepcopy(_document())
    document["dataset"]["images"][0]["source_image_sha256"] = "8" * 64
    _seal(document)

    with pytest.raises(StaticCameraIntrinsicsError, match="image manifest hash mismatch"):
        parse_static_camera_intrinsics_json(_payload(document))


def test_split_overlap_is_rejected_even_with_recomputed_hashes() -> None:
    document = deepcopy(_document())
    document["dataset"]["splits"]["held_out_image_ids"][0] = "synthetic-view-01"
    _refresh_derived(document)

    with pytest.raises(StaticCameraIntrinsicsError, match="not disjoint"):
        parse_static_camera_intrinsics_json(_payload(document))


def test_split_label_mismatch_is_rejected() -> None:
    document = deepcopy(_document())
    document["dataset"]["images"][0]["split"] = "HELD_OUT"
    _refresh_derived(document)

    with pytest.raises(StaticCameraIntrinsicsError, match="label disagrees"):
        parse_static_camera_intrinsics_json(_payload(document))


@pytest.mark.parametrize(
    ("split", "remove_count", "message"),
    [("TRAINING", 5, "insufficient training views"), ("HELD_OUT", 3, "insufficient held-out views")],
)
def test_insufficient_precommitted_split_counts_fail(
    split: str, remove_count: int, message: str
) -> None:
    document = deepcopy(_document())
    ids_key = "training_image_ids" if split == "TRAINING" else "held_out_image_ids"
    removed = set(document["dataset"]["splits"][ids_key][-remove_count:])
    document["dataset"]["splits"][ids_key] = document["dataset"]["splits"][ids_key][
        :-remove_count
    ]
    document["dataset"]["images"] = [
        item for item in document["dataset"]["images"] if item["image_id"] not in removed
    ]
    document["solution"]["per_view_residuals"] = [
        item
        for item in document["solution"]["per_view_residuals"]
        if item["image_id"] not in removed
    ]
    _refresh_derived(document)

    with pytest.raises(StaticCameraIntrinsicsError, match=message):
        parse_static_camera_intrinsics_json(_payload(document))


def test_insufficient_corners_and_spatial_coverage_fail() -> None:
    corners = deepcopy(_document())
    corners["dataset"]["images"][0]["detected_charuco_corners"] = 29
    _refresh_derived(corners)
    with pytest.raises(StaticCameraIntrinsicsError, match="insufficient ChArUco corners"):
        parse_static_camera_intrinsics_json(_payload(corners))

    coverage = deepcopy(_document())
    for image in coverage["dataset"]["images"]:
        if image["split"] == "TRAINING":
            image["board_centroid_normalized"][0] = 0.5
    _refresh_derived(coverage)
    with pytest.raises(StaticCameraIntrinsicsError, match="insufficient view coverage"):
        parse_static_camera_intrinsics_json(_payload(coverage))


def test_held_out_quadrant_coverage_is_required() -> None:
    document = deepcopy(_document())
    held_index = 0
    for image in document["dataset"]["images"]:
        if image["split"] == "HELD_OUT":
            image["board_centroid_normalized"] = (
                [0.24, 0.25] if held_index % 2 == 0 else [0.76, 0.75]
            )
            held_index += 1
    _refresh_derived(document)

    with pytest.raises(StaticCameraIntrinsicsError, match="held-out"):
        parse_static_camera_intrinsics_json(_payload(document))


def test_wrong_image_resolution_fails_even_when_manifest_is_resealed() -> None:
    document = deepcopy(_document())
    document["dataset"]["images"][0]["width_px"] = 2736
    _refresh_derived(document)

    with pytest.raises(StaticCameraIntrinsicsError, match="resolution"):
        parse_static_camera_intrinsics_json(_payload(document))


def test_residual_coverage_and_aggregate_tampering_fail() -> None:
    missing = deepcopy(_document())
    missing["solution"]["per_view_residuals"].pop()
    _refresh_derived(missing)
    with pytest.raises(StaticCameraIntrinsicsError, match="do not exactly cover"):
        parse_static_camera_intrinsics_json(_payload(missing))

    aggregate = deepcopy(_document())
    aggregate["solution"]["aggregate_residuals"]["held_out_rms_px"] = 0.1
    _seal(aggregate)
    with pytest.raises(StaticCameraIntrinsicsError, match="does not match"):
        parse_static_camera_intrinsics_json(_payload(aggregate))


def test_synthetic_residual_thresholds_enforce_the_rehearsal_only() -> None:
    document = deepcopy(_document())
    for residual in document["solution"]["per_view_residuals"]:
        if residual["split"] == "HELD_OUT":
            residual["reprojection_rms_px"] = 0.95
            residual["maximum_residual_px"] = 1.1
    _refresh_derived(document)

    with pytest.raises(StaticCameraIntrinsicsError, match="held-out RMS"):
        parse_static_camera_intrinsics_json(_payload(document))


def test_distortion_matrix_roi_and_map_contracts_are_exact() -> None:
    coefficients = deepcopy(_document())
    coefficients["solution"]["distortion_coefficients"].pop()
    _seal(coefficients)
    with pytest.raises(StaticCameraIntrinsicsError, match="exactly 8"):
        parse_static_camera_intrinsics_json(_payload(coefficients))

    matrix = deepcopy(_document())
    matrix["solution"]["camera_matrix_row_major"][6] = 1.0
    _seal(matrix)
    with pytest.raises(StaticCameraIntrinsicsError, match="pinhole structure"):
        parse_static_camera_intrinsics_json(_payload(matrix))

    crop = deepcopy(_document())
    crop["solution"]["output_crop"]["x_px"] = 0
    _seal(crop)
    with pytest.raises(StaticCameraIntrinsicsError, match="inside the valid-pixel ROI"):
        parse_static_camera_intrinsics_json(_payload(crop))


def test_authority_cannot_be_promoted_even_after_resealing() -> None:
    for field, value in (
        ("physical_calibration_valid", True),
        ("commissioned", True),
        ("hardware_accessed", True),
        ("camera_frames_requested", 1),
        ("arm_motion_commands", 1),
        ("contact_commands", 1),
        ("robot_motion_authority", True),
        ("contact_authority", True),
        ("physical_release_effect", "PASS"),
    ):
        document = deepcopy(_document())
        document["authority"][field] = value
        _seal(document)
        with pytest.raises(StaticCameraIntrinsicsError, match=f"authority.{field}"):
            parse_static_camera_intrinsics_json(_payload(document))


def test_unresealed_tampering_is_detected_before_use() -> None:
    document = deepcopy(_document())
    document["artifact_id"] = "tampered-artifact"

    with pytest.raises(StaticCameraIntrinsicsError, match="tampering detected"):
        parse_static_camera_intrinsics_json(_payload(document))


def test_exact_fields_duplicate_keys_nonfinite_and_resource_bounds() -> None:
    unknown = deepcopy(_document())
    unknown["unexpected"] = True
    _seal(unknown)
    with pytest.raises(StaticCameraIntrinsicsError, match="unknown=.*unexpected"):
        parse_static_camera_intrinsics_json(_payload(unknown))

    with pytest.raises(StaticCameraIntrinsicsError, match="duplicate key"):
        parse_static_camera_intrinsics_json(b'{"schema":"one","schema":"two"}')

    nonfinite = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        '"board_tilt_deg":5.0', '"board_tilt_deg":NaN', 1
    )
    with pytest.raises(StaticCameraIntrinsicsError, match="nonfinite"):
        parse_static_camera_intrinsics_json(nonfinite.encode("utf-8"))

    too_many = deepcopy(_document())
    extra = deepcopy(too_many["dataset"]["images"][0])
    while len(too_many["dataset"]["images"]) <= MAX_INTRINSICS_IMAGES:
        extra = deepcopy(extra)
        extra["image_id"] = f"overflow-{len(too_many['dataset']['images']):02d}"
        too_many["dataset"]["images"].append(extra)
    _seal(too_many)
    with pytest.raises(StaticCameraIntrinsicsError, match="maximum"):
        parse_static_camera_intrinsics_json(_payload(too_many))

    with pytest.raises(StaticCameraIntrinsicsError, match="exceeds"):
        parse_static_camera_intrinsics_json(
            b" " * (MAX_STATIC_CAMERA_INTRINSICS_BYTES + 1)
        )
    with pytest.raises(StaticCameraIntrinsicsError, match="empty"):
        parse_static_camera_intrinsics_json(b"")
    with pytest.raises(StaticCameraIntrinsicsError, match="UTF-8"):
        parse_static_camera_intrinsics_json(b"\xff")


def test_fixture_loader_rejects_path_escape(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    fixture_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(FIXTURE_PATH.read_bytes())

    with pytest.raises(StaticCameraIntrinsicsError, match="escapes"):
        load_static_camera_intrinsics_rehearsal(outside, fixture_root=fixture_root)


def test_fixture_loader_rejects_oversized_file_at_boundary(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (MAX_STATIC_CAMERA_INTRINSICS_BYTES + 1))
    with pytest.raises(StaticCameraIntrinsicsError, match="cannot read"):
        load_static_camera_intrinsics_rehearsal(path, fixture_root=tmp_path)


def test_assessor_requires_the_exact_profile_source_hash() -> None:
    artifact = parse_static_camera_intrinsics_json(FIXTURE_PATH.read_bytes())
    profile = load_camera_profile()
    wrong_profile = replace(profile, source_file_sha256="0" * 64)

    with pytest.raises(StaticCameraIntrinsicsError, match="source hash"):
        assess_static_camera_intrinsics_rehearsal(
            artifact, purchased_profile=wrong_profile
        )
    with pytest.raises(TypeError, match="purchased_profile"):
        assess_static_camera_intrinsics_rehearsal(
            artifact, purchased_profile=object()  # type: ignore[arg-type]
        )


def test_schema_and_fixture_class_are_pinned() -> None:
    document = deepcopy(_document())
    assert document["schema"] == STATIC_CAMERA_INTRINSICS_SCHEMA
    document["schema"] = "rocell.camera_intrinsics.v0"
    _seal(document)
    with pytest.raises(StaticCameraIntrinsicsError, match="schema"):
        parse_static_camera_intrinsics_json(_payload(document))

    document = deepcopy(_document())
    document["artifact_class"] = "PHYSICAL_CALIBRATION"
    _seal(document)
    with pytest.raises(StaticCameraIntrinsicsError, match="artifact_class"):
        parse_static_camera_intrinsics_json(_payload(document))
