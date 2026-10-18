from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from rocell.calibration.fixed_camera_tag_evidence_v1 import (
    FixedCameraTagEvidenceError,
    load_retained_fixed_camera_tag_evidence_v1,
)
from rocell.vision.detections import (
    AprilTagDetection,
    AprilTagDetectionBatch,
    DetectorIdentity,
    PixelCorner,
)
from rocell.vision.fixed_camera_board_pose_extractor_v1 import (
    extract_fixed_camera_board_pose,
)

from test_fixed_camera_board_pose_extractor_v1 import (
    _batch,
    _frame,
    _intrinsics,
    _tag_map,
)


RECTIFICATION_SHA = "8" * 64
IMPLEMENTATION_SHA = "9" * 64


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def rectified_batch() -> AprilTagDetectionBatch:
    raw = _batch()
    return AprilTagDetectionBatch(
        frame=raw.frame,
        detector=DetectorIdentity(
            detector_id="rocell.b0477.rectified-apriltag",
            version="1.0.0",
            configuration_sha256="7" * 64,
            implementation_sha256=IMPLEMENTATION_SHA,
        ),
        detections=tuple(
            AprilTagDetection(
                tag=detection.tag,
                corners_px=tuple(
                    PixelCorner(corner.x_px, corner.y_px)
                    for corner in detection.corners_px
                ),  # type: ignore[arg-type]
                decision_margin=detection.decision_margin,
                hamming=detection.hamming,
                rejection_reason=detection.rejection_reason,
            )
            for detection in raw.detections
        ),
    )


def record() -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "rocell.retained_fixed_camera_tag_evidence.v1",
        "status": "RETAINED_FIXED_CAMERA_TAG_EVIDENCE",
        "pixel_spaces": {
            "source": "B0477_CAPTURE_DISTORTED_PIXELS",
            "destination": "UNDISTORTED_PINHOLE_PIXELS",
        },
        "rectification": {
            "configuration_sha256": RECTIFICATION_SHA,
            "implementation_sha256": IMPLEMENTATION_SHA,
        },
        "raw_detection_batch": _batch().to_dict(),
        "rectified_detection_batch": rectified_batch().to_dict(),
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
    path = tmp_path / "fixed-camera-tag-evidence.json"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def load(tmp_path: Path):
    path, file_sha256 = write_record(tmp_path)
    return load_retained_fixed_camera_tag_evidence_v1(
        path, expected_file_sha256=file_sha256
    )


def test_pinned_evidence_replays_detector_and_rectifier_into_board_pose(
    tmp_path: Path,
) -> None:
    evidence = load(tmp_path)
    result = extract_fixed_camera_board_pose(
        _frame(), evidence, evidence, _intrinsics(), _tag_map()
    )

    assert result.full_detection_batch == evidence.rectified_batch
    assert result.held_out_maximum_px == pytest.approx(0.0, abs=1e-8)
    assert evidence.configuration_sha256 == RECTIFICATION_SHA
    assert evidence.receipt()["authority"]["motion_authorized"] is False  # type: ignore[index]


def test_requires_caller_pinned_exact_file_bytes(tmp_path: Path) -> None:
    path, _ = write_record(tmp_path)
    with pytest.raises(FixedCameraTagEvidenceError, match="bytes differ"):
        load_retained_fixed_camera_tag_evidence_v1(
            path, expected_file_sha256="0" * 64
        )


def test_detector_refuses_replay_against_another_frame(tmp_path: Path) -> None:
    evidence = load(tmp_path)
    with pytest.raises(FixedCameraTagEvidenceError, match="different frame"):
        evidence.detect(replace(_frame(), capture_id="another-capture"))


def test_rectifier_refuses_another_raw_batch(tmp_path: Path) -> None:
    evidence = load(tmp_path)
    changed = AprilTagDetectionBatch(
        frame=evidence.raw_batch.frame,
        detector=replace(
            evidence.raw_batch.detector, implementation_sha256="a" * 64
        ),
        detections=evidence.raw_batch.detections,
    )
    with pytest.raises(FixedCameraTagEvidenceError, match="rectifier input"):
        evidence.rectify_detection_batch(changed)


def test_rejects_crossed_frames_and_changed_detection_facts(tmp_path: Path) -> None:
    crossed = record()
    rectified = crossed["rectified_detection_batch"]
    assert isinstance(rectified, dict)
    frame = rectified["frame"]
    assert isinstance(frame, dict)
    frame["capture_id"] = "crossed-capture"
    reseal(crossed)
    path, file_sha256 = write_record(tmp_path, crossed)
    with pytest.raises(FixedCameraTagEvidenceError, match="different frames"):
        load_retained_fixed_camera_tag_evidence_v1(
            path, expected_file_sha256=file_sha256
        )

    changed = record()
    changed_batch = changed["rectified_detection_batch"]
    assert isinstance(changed_batch, dict)
    detections = changed_batch["detections"]
    assert isinstance(detections, list)
    first = detections[0]
    assert isinstance(first, dict)
    first["decision_margin"] = float(first["decision_margin"]) + 1.0
    reseal(changed)
    path, file_sha256 = write_record(tmp_path, changed)
    with pytest.raises(FixedCameraTagEvidenceError, match="rectification changed"):
        load_retained_fixed_camera_tag_evidence_v1(
            path, expected_file_sha256=file_sha256
        )


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        ("authority", "motion_authorized", True, "must be False"),
        (
            "pixel_spaces",
            "destination",
            "RAW_PIXELS",
            "UNDISTORTED_PINHOLE_PIXELS",
        ),
        (
            "rectification",
            "implementation_sha256",
            "a" * 64,
            "implementation differs",
        ),
    ),
)
def test_rejects_authority_pixel_space_and_rectifier_drift(
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
    with pytest.raises(FixedCameraTagEvidenceError, match=message):
        load_retained_fixed_camera_tag_evidence_v1(
            path, expected_file_sha256=file_sha256
        )


def test_rejects_changed_meaning_duplicate_keys_and_nonfinite_values(
    tmp_path: Path,
) -> None:
    changed = record()
    spaces = changed["pixel_spaces"]
    assert isinstance(spaces, dict)
    spaces["source"] = "CHANGED_RAW_PIXELS"
    path, file_sha256 = write_record(tmp_path, changed)
    with pytest.raises(FixedCameraTagEvidenceError, match="integrity_sha256"):
        load_retained_fixed_camera_tag_evidence_v1(
            path, expected_file_sha256=file_sha256
        )

    duplicate = b'{"schema":"a","schema":"b"}'
    path.write_bytes(duplicate)
    with pytest.raises(FixedCameraTagEvidenceError, match="duplicate key"):
        load_retained_fixed_camera_tag_evidence_v1(
            path, expected_file_sha256=hashlib.sha256(duplicate).hexdigest()
        )

    nonfinite = canonical(record()).replace(
        b'"decision_margin":100.0', b'"decision_margin":NaN', 1
    )
    path.write_bytes(nonfinite)
    with pytest.raises(FixedCameraTagEvidenceError, match="nonfinite"):
        load_retained_fixed_camera_tag_evidence_v1(
            path, expected_file_sha256=hashlib.sha256(nonfinite).hexdigest()
        )
