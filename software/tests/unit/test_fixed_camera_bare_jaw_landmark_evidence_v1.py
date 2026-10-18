from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from rocell.calibration.fixed_camera_bare_jaw_landmark_evidence_v1 import (
    FixedCameraBareJawLandmarkEvidenceError,
    load_retained_bare_jaw_landmark_evidence_v1,
)
from rocell.calibration.fixed_camera_bare_jaw_landmarks_v1 import REFERENCE_FRAME

from test_fixed_camera_bare_jaw_observer_v1 import calibration
from test_fixed_camera_board_pose_extractor_v1 import CAMERA_FRAME, _frame, _intrinsics


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def reference_model() -> dict[str, object]:
    return {
        "model_id": "rc03-bare-jaw-landmarks-physical-1",
        "reference_frame": REFERENCE_FRAME,
        "landmarks": [
            {"landmark_id": name, "xyz_mm": [x, y, 0.0]}
            for name, x, y in (
                ("left-top", -60.0, -35.0),
                ("right-top", 60.0, -35.0),
                ("left-middle", -60.0, 0.0),
                ("right-middle", 60.0, 0.0),
                ("left-bottom", -60.0, 35.0),
                ("right-bottom", 60.0, 35.0),
            )
        ],
    }


def record() -> dict[str, object]:
    frame = _frame()
    intrinsics = _intrinsics()
    model = reference_model()
    translation = (25.0, -10.0, 900.0)
    pixels = []
    landmarks = model["landmarks"]
    assert isinstance(landmarks, list)
    for index, item in enumerate(landmarks):
        assert isinstance(item, dict)
        xyz = item["xyz_mm"]
        assert isinstance(xyz, list)
        camera_x = float(xyz[0]) + translation[0]
        camera_y = float(xyz[1]) + translation[1]
        camera_z = float(xyz[2]) + translation[2]
        pixels.append(
            {
                "landmark_id": item["landmark_id"],
                "x_px": intrinsics.fx_px * camera_x / camera_z + intrinsics.cx_px,
                "y_px": intrinsics.fy_px * camera_y / camera_z + intrinsics.cy_px,
                "role": "FIT" if index < 4 else "HOLDOUT",
            }
        )
    body: dict[str, object] = {
        "schema": "rocell.retained_bare_jaw_landmark_evidence.v1",
        "status": "RETAINED_BARE_JAW_LANDMARK_EVIDENCE",
        "frame_binding": {
            "capture_id": frame.capture_id,
            "frame_sha256": frame.sha256,
            "settings_sha256": frame.settings_hash,
            "width_px": frame.width_px,
            "height_px": frame.height_px,
            "camera_frame": CAMERA_FRAME,
            "pixel_space": intrinsics.pixel_space,
            "intrinsics_sha256": intrinsics.content_hash,
        },
        "detector": {
            "id": "rocell.fixed-camera-bare-jaw-reference",
            "version": "1.0.0",
            "configuration_sha256": "1" * 64,
            "implementation_sha256": "2" * 64,
        },
        "reference_model": model,
        "estimate": {
            "parent_frame": CAMERA_FRAME,
            "child_frame": REFERENCE_FRAME,
            "rotation_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "translation_mm": list(translation),
            "uncertainty_mm": 0.7,
            "landmarks": pixels,
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


def reseal(value: dict[str, object]) -> None:
    value.pop("integrity_sha256", None)
    value["integrity_sha256"] = hashlib.sha256(canonical(value)).hexdigest()


def write_record(tmp_path: Path, value: object | None = None) -> tuple[Path, str]:
    selected = record() if value is None else value
    payload = canonical(selected)
    path = tmp_path / "bare-jaw-landmark-evidence.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def test_pinned_evidence_builds_audited_detector_and_replays_exact_frame(
    tmp_path: Path,
) -> None:
    document = record()
    model = document["reference_model"]
    assert isinstance(model, dict)
    model_sha256 = hashlib.sha256(canonical(model)).hexdigest()
    path, file_sha256 = write_record(tmp_path, document)

    evidence = load_retained_bare_jaw_landmark_evidence_v1(
        path, expected_file_sha256=file_sha256
    )
    reviewed = replace(calibration(), reference_model_sha256=model_sha256)
    result = evidence.build_detector(reviewed, _intrinsics()).detect(_frame())

    assert evidence.model.source_sha256 == model_sha256
    assert result.frame_sha256 == _frame().sha256
    assert result.camera_xyz_mm == pytest.approx((25.0, -10.0, 900.0))
    assert result.uncertainty_mm == pytest.approx(0.7)
    assert evidence.receipt()["authority"]["motion_authorized"] is False  # type: ignore[index]


def test_requires_caller_pinned_exact_file_bytes(tmp_path: Path) -> None:
    path, _ = write_record(tmp_path)
    with pytest.raises(FixedCameraBareJawLandmarkEvidenceError, match="bytes differ"):
        load_retained_bare_jaw_landmark_evidence_v1(
            path, expected_file_sha256="0" * 64
        )


def test_rejects_changed_meaning_even_when_file_hash_is_updated(tmp_path: Path) -> None:
    document = record()
    frame = document["frame_binding"]
    assert isinstance(frame, dict)
    frame["capture_id"] = "changed"
    path, file_sha256 = write_record(tmp_path, document)
    with pytest.raises(
        FixedCameraBareJawLandmarkEvidenceError, match="integrity_sha256"
    ):
        load_retained_bare_jaw_landmark_evidence_v1(
            path, expected_file_sha256=file_sha256
        )


def test_pose_source_refuses_replay_against_another_capture(tmp_path: Path) -> None:
    path, file_sha256 = write_record(tmp_path)
    evidence = load_retained_bare_jaw_landmark_evidence_v1(
        path, expected_file_sha256=file_sha256
    )
    other_frame = replace(_frame(), capture_id="another-capture")
    with pytest.raises(FixedCameraBareJawLandmarkEvidenceError, match="capture id"):
        evidence.pose_source.estimate(other_frame, _intrinsics(), evidence.model)

    other_intrinsics = replace(_intrinsics(), calibration_id="another-calibration")
    with pytest.raises(FixedCameraBareJawLandmarkEvidenceError, match="intrinsics"):
        evidence.pose_source.estimate(_frame(), other_intrinsics, evidence.model)

    other_model = replace(evidence.model, source_sha256="f" * 64)
    with pytest.raises(FixedCameraBareJawLandmarkEvidenceError, match="reference model"):
        evidence.pose_source.estimate(_frame(), _intrinsics(), other_model)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        ("authority", "motion_authorized", True, "must be False"),
        ("estimate", "parent_frame", "wrong-camera", "parent_frame"),
        (
            "estimate",
            "rotation_row_major",
            [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0],
            "right-handed",
        ),
    ),
)
def test_rejects_authority_and_invalid_transform(
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
    path, file_sha256 = write_record(tmp_path, document)
    with pytest.raises(FixedCameraBareJawLandmarkEvidenceError, match=message):
        load_retained_bare_jaw_landmark_evidence_v1(
            path, expected_file_sha256=file_sha256
        )


def test_rejects_duplicate_keys_and_nonfinite_values(tmp_path: Path) -> None:
    duplicate = b'{"schema":"a","schema":"b"}'
    path = tmp_path / "duplicate.json"
    path.write_bytes(duplicate)
    with pytest.raises(FixedCameraBareJawLandmarkEvidenceError, match="duplicate key"):
        load_retained_bare_jaw_landmark_evidence_v1(
            path, expected_file_sha256=hashlib.sha256(duplicate).hexdigest()
        )

    nonfinite = canonical(record()).replace(b'"uncertainty_mm":0.7', b'"uncertainty_mm":NaN')
    path.write_bytes(nonfinite)
    with pytest.raises(FixedCameraBareJawLandmarkEvidenceError, match="nonfinite"):
        load_retained_bare_jaw_landmark_evidence_v1(
            path, expected_file_sha256=hashlib.sha256(nonfinite).hexdigest()
        )
