from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.calibration.fixed_camera_calibration_observation_v1 import REVIEW_STATUS
from rocell.calibration.fixed_camera_physical_intrinsics_v1 import (
    FixedCameraPhysicalIntrinsicsError,
    load_reviewed_native_intrinsics_record_v1,
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def record() -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "rocell.reviewed_native_fixed_camera_intrinsics_record.v1",
        "status": REVIEW_STATUS,
        "calibration_record_id": "b0477-native-physical-intrinsics-2026-10-18",
        "camera_binding": {
            "persistent_camera_identity_sha256": "1" * 64,
            "settings_sha256": "2" * 64,
            "mode": {
                "width_px": 5472,
                "height_px": 3648,
                "fps": 9.0,
                "pixel_format": "YUY2",
            },
            "native_mode_verified": True,
            "full_frame_without_crop_or_rescale": True,
        },
        "solution": {
            "calibration_id": "b0477-native-reviewed-2026-10-18",
            "calibration_producer_id": "optics-calibration-operator-1",
            "source_artifact_sha256": "3" * 64,
            "camera_frame": "b0477_camera_optical",
            "pixel_space": "UNDISTORTED_PINHOLE_PIXELS",
            "distortion_model": "OPENCV_RATIONAL_POLYNOMIAL_8",
            "distortion_coefficients": [0.1, -0.2, 0.001, 0.002, 0.01, 0.0, 0.0, 0.0],
            "rectified_camera_matrix_row_major": [
                5000.0,
                0.0,
                2735.5,
                0.0,
                5005.0,
                1823.5,
                0.0,
                0.0,
                1.0,
            ],
            "rectification_configuration_sha256": "4" * 64,
        },
        "board_binding": {"tag_map_sha256": "5" * 64},
        "physical_validation": {
            "physical_calibration_valid": True,
            "dataset_manifest_sha256": "6" * 64,
            "split_commitment_sha256": "7" * 64,
            "training_view_count": 20,
            "held_out_view_count": 6,
            "metrics_px": {
                "training_rms": 0.42,
                "held_out_rms": 0.56,
                "held_out_p95": 0.81,
                "maximum_view_rms": 0.93,
            },
            "acceptance_limits_px": {
                "training_rms": 0.70,
                "held_out_rms": 0.90,
                "held_out_p95": 1.00,
                "maximum_view_rms": 1.25,
            },
        },
        "independent_review": {
            "decision": "ACCEPT",
            "reviewer_id": "external-optics-reviewer-1",
            "reviewed_at": "2026-10-18T01:00:00-04:00",
            "review_record_sha256": "8" * 64,
        },
        "authority": {
            "camera_opened": False,
            "robot_provider_called": False,
            "motion_targets_emitted": False,
            "motion_authorized": False,
            "contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    body["integrity_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    return body


def write_record(tmp_path: Path, value: object | None = None) -> tuple[Path, str]:
    selected = record() if value is None else value
    payload = canonical(selected)
    path = tmp_path / "reviewed-native-intrinsics.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def reseal(value: dict[str, object]) -> None:
    value.pop("integrity_sha256", None)
    value["integrity_sha256"] = hashlib.sha256(canonical(value)).hexdigest()


def test_loads_pinned_reviewed_record_and_builds_existing_binding(
    tmp_path: Path,
) -> None:
    path, sha256 = write_record(tmp_path)
    retained = load_reviewed_native_intrinsics_record_v1(
        path, expected_file_sha256=sha256
    )
    binding = retained.to_reviewed_binding()

    assert retained.source_file_sha256 == sha256
    assert retained.training_view_count == 20
    assert retained.held_out_view_count == 6
    assert binding.status == REVIEW_STATUS
    assert binding.intrinsics.width_px == 5472
    assert binding.intrinsics.height_px == 3648
    assert binding.intrinsics.fx_px == 5000.0
    assert binding.intrinsics.source_sha256 == "3" * 64
    assert binding.rectification_configuration_sha256 == "4" * 64
    receipt = retained.receipt()
    assert receipt["status"] == "REVIEWED_PHYSICAL_INTRINSICS_RECORD_ACCEPTED"
    assert receipt["authority"]["motion_authorized"] is False  # type: ignore[index]


def test_requires_caller_pinned_exact_file_bytes(tmp_path: Path) -> None:
    path, _ = write_record(tmp_path)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match="bytes differ"):
        load_reviewed_native_intrinsics_record_v1(path, expected_file_sha256="0" * 64)


def test_rejects_changed_meaning_even_when_file_hash_is_updated(tmp_path: Path) -> None:
    value = record()
    value["calibration_record_id"] = "changed"
    path, sha256 = write_record(tmp_path, value)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match="integrity_sha256"):
        load_reviewed_native_intrinsics_record_v1(path, expected_file_sha256=sha256)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        ("camera_binding", "native_mode_verified", False, "must be True"),
        (
            "camera_binding",
            "full_frame_without_crop_or_rescale",
            False,
            "must be True",
        ),
        ("independent_review", "decision", "REJECT", "must be 'ACCEPT'"),
        ("authority", "motion_authorized", True, "must be False"),
    ),
)
def test_rejects_unqualified_review_and_authority_claims(
    tmp_path: Path,
    section: str,
    field: str,
    value: object,
    message: str,
) -> None:
    document = record()
    nested = document[section]
    assert isinstance(nested, dict)
    nested[field] = value
    reseal(document)
    path, sha256 = write_record(tmp_path, document)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match=message):
        load_reviewed_native_intrinsics_record_v1(path, expected_file_sha256=sha256)


def test_rejects_metrics_outside_reviewed_limits(tmp_path: Path) -> None:
    document = record()
    validation = document["physical_validation"]
    assert isinstance(validation, dict)
    metrics = validation["metrics_px"]
    assert isinstance(metrics, dict)
    metrics["held_out_rms"] = 0.91
    reseal(document)
    path, sha256 = write_record(tmp_path, document)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match="acceptance limits"):
        load_reviewed_native_intrinsics_record_v1(path, expected_file_sha256=sha256)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("distortion_model", "OPENCV_5", "distortion_model"),
        (
            "rectified_camera_matrix_row_major",
            [5000.0, 0.0, 2735.5, 1.0, 5005.0, 1823.5, 0.0, 0.0, 1.0],
            "canonical pinhole",
        ),
    ),
)
def test_rejects_wrong_optical_model(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    document = record()
    solution = document["solution"]
    assert isinstance(solution, dict)
    solution[field] = value
    reseal(document)
    path, sha256 = write_record(tmp_path, document)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match=message):
        load_reviewed_native_intrinsics_record_v1(path, expected_file_sha256=sha256)


def test_rejects_duplicate_keys_and_nonfinite_values(tmp_path: Path) -> None:
    duplicate = b'{"schema":"a","schema":"b"}'
    path = tmp_path / "duplicate.json"
    path.write_bytes(duplicate)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match="duplicate key"):
        load_reviewed_native_intrinsics_record_v1(
            path, expected_file_sha256=hashlib.sha256(duplicate).hexdigest()
        )


def test_requires_declared_reviewer_independence(tmp_path: Path) -> None:
    document = record()
    review = document["independent_review"]
    assert isinstance(review, dict)
    review["reviewer_id"] = "optics-calibration-operator-1"
    reseal(document)
    path, sha256 = write_record(tmp_path, document)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match="must differ"):
        load_reviewed_native_intrinsics_record_v1(path, expected_file_sha256=sha256)

    nonfinite = canonical(record()).replace(
        b'"training_rms":0.42', b'"training_rms":NaN'
    )
    path.write_bytes(nonfinite)
    with pytest.raises(FixedCameraPhysicalIntrinsicsError, match="nonfinite"):
        load_reviewed_native_intrinsics_record_v1(
            path, expected_file_sha256=hashlib.sha256(nonfinite).hexdigest()
        )
