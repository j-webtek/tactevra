from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from rocell.calibration.fixed_camera_retained_observation_v1 import (
    compile_retained_fixed_camera_calibration_observation_v1,
)
from rocell.calibration.fixed_camera_physical_intrinsics_v1 import (
    CAMERA_FRAME as PHYSICAL_CAMERA_FRAME,
)
from rocell.geometry import Point3Mm
from rocell.vision.detections import (
    AprilTagDetectionBatch,
    DetectorIdentity,
)

from test_fixed_camera_bare_jaw_landmark_evidence_v1 import reference_model
from test_fixed_camera_bare_jaw_observer_v1 import (
    BOARD_FRAME,
    GROUND_TRUTH,
    calibration_document,
)
from test_fixed_camera_bracket_evidence_v1 import (
    _record as bracket_record,
)
from test_fixed_camera_calibration_observation_v1 import (
    IDENTITY_SHA,
    SETTINGS_SHA,
    frame,
    intrinsics,
    scaled_batch,
)
from test_fixed_camera_physical_intrinsics_v1 import record as intrinsics_record
from test_fixed_camera_tag_evidence_v1 import record as tag_record
from test_fixed_camera_board_pose_extractor_v1 import _tag_map


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def reseal(value: dict[str, object]) -> None:
    value.pop("integrity_sha256", None)
    value["integrity_sha256"] = hashlib.sha256(canonical(value)).hexdigest()


def write(path: Path, value: object | bytes) -> str:
    payload = value if isinstance(value, bytes) else canonical(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def native_bracket_record() -> dict[str, object]:
    packet = frame()
    document = bracket_record(packet.jpeg_bytes)
    bracket = document["bracket"]
    assert isinstance(bracket, dict)
    bracket["camera_identity_sha256"] = IDENTITY_SHA
    frame_value = bracket["frame"]
    assert isinstance(frame_value, dict)
    frame_value.update(
        {
            "capture_id": packet.capture_id,
            "width_px": packet.width_px,
            "height_px": packet.height_px,
            "source_sequence": packet.source_sequence,
            "source_timestamp_ns": packet.source_timestamp_ns,
            "source_clock": packet.source_clock,
            "host_request_ns": packet.host_request_ns,
            "host_first_byte_ns": packet.host_first_byte_ns,
            "host_complete_ns": packet.host_complete_ns,
            "settings_sha256": packet.settings_hash,
            "timestamp_quality": packet.timestamp_quality.value,
            "freshness_token": packet.freshness_token,
            "freshness_basis": packet.freshness_basis,
        }
    )
    reseal(document)
    return document


def native_intrinsics():
    return replace(intrinsics(), camera_frame=PHYSICAL_CAMERA_FRAME)


def reviewed_intrinsics_record() -> dict[str, object]:
    document = intrinsics_record()
    camera = document["camera_binding"]
    solution = document["solution"]
    board = document["board_binding"]
    assert isinstance(camera, dict)
    assert isinstance(solution, dict)
    assert isinstance(board, dict)
    reviewed = native_intrinsics()
    camera["persistent_camera_identity_sha256"] = IDENTITY_SHA
    camera["settings_sha256"] = SETTINGS_SHA
    solution["calibration_id"] = reviewed.calibration_id
    solution["source_artifact_sha256"] = reviewed.source_sha256
    solution["camera_frame"] = reviewed.camera_frame
    solution["rectified_camera_matrix_row_major"] = [
        reviewed.fx_px,
        reviewed.skew_px,
        reviewed.cx_px,
        0.0,
        reviewed.fy_px,
        reviewed.cy_px,
        0.0,
        0.0,
        1.0,
    ]
    solution["rectification_configuration_sha256"] = "3" * 64
    board["tag_map_sha256"] = _tag_map().content_hash
    reseal(document)
    return document


def retained_tag_record(*, crossed_capture: bool = False) -> dict[str, object]:
    packet = frame()
    raw = scaled_batch(packet)
    if crossed_capture:
        crossed = replace(packet, capture_id="crossed-capture")
        raw = scaled_batch(crossed)
    rectified = AprilTagDetectionBatch(
        frame=raw.frame,
        detector=DetectorIdentity(
            detector_id="rocell.b0477.rectified-apriltag",
            version="1.0.0",
            configuration_sha256="7" * 64,
            implementation_sha256="9" * 64,
        ),
        detections=raw.detections,
    )
    document = tag_record()
    rectification = document["rectification"]
    assert isinstance(rectification, dict)
    rectification["configuration_sha256"] = "3" * 64
    rectification["implementation_sha256"] = "9" * 64
    document["raw_detection_batch"] = raw.to_dict()
    document["rectified_detection_batch"] = rectified.to_dict()
    reseal(document)
    return document


def bare_jaw_landmark_record() -> tuple[dict[str, object], str]:
    packet = frame()
    reviewed = native_intrinsics()
    model = reference_model()
    model_sha256 = hashlib.sha256(canonical(model)).hexdigest()
    board_point = Point3Mm(BOARD_FRAME, 200.0, 150.0, 50.0)
    camera_point = GROUND_TRUTH.transform_point(board_point)
    translation = (camera_point.x, camera_point.y, camera_point.z)
    landmarks = model["landmarks"]
    assert isinstance(landmarks, list)
    pixels: list[dict[str, object]] = []
    for index, landmark in enumerate(landmarks):
        assert isinstance(landmark, dict)
        xyz = landmark["xyz_mm"]
        assert isinstance(xyz, list)
        x = float(xyz[0]) + translation[0]
        y = float(xyz[1]) + translation[1]
        z = float(xyz[2]) + translation[2]
        pixels.append(
            {
                "landmark_id": landmark["landmark_id"],
                "x_px": reviewed.fx_px * x / z + reviewed.cx_px,
                "y_px": reviewed.fy_px * y / z + reviewed.cy_px,
                "role": "FIT" if index < 4 else "HOLDOUT",
            }
        )
    document: dict[str, object] = {
        "schema": "rocell.retained_bare_jaw_landmark_evidence.v1",
        "status": "RETAINED_BARE_JAW_LANDMARK_EVIDENCE",
        "frame_binding": {
            "capture_id": packet.capture_id,
            "frame_sha256": packet.sha256,
            "settings_sha256": packet.settings_hash,
            "width_px": packet.width_px,
            "height_px": packet.height_px,
            "camera_frame": PHYSICAL_CAMERA_FRAME,
            "pixel_space": reviewed.pixel_space,
            "intrinsics_sha256": reviewed.content_hash,
        },
        "detector": {
            "id": "rocell.fixed-camera-bare-jaw-reference",
            "version": "1.0.0",
            "configuration_sha256": "1" * 64,
            "implementation_sha256": "2" * 64,
        },
        "reference_model": model,
        "estimate": {
            "parent_frame": PHYSICAL_CAMERA_FRAME,
            "child_frame": "bare_jaw_reference",
            "rotation_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "translation_mm": list(translation),
            "uncertainty_mm": 0.5,
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
    reseal(document)
    return document, model_sha256


def bare_jaw_calibration_record(model_sha256: str) -> dict[str, object]:
    document = calibration_document()
    bindings = document["bindings"]
    assert isinstance(bindings, dict)
    bindings["camera_intrinsics_sha256"] = native_intrinsics().content_hash
    bindings["tag_map_sha256"] = _tag_map().content_hash
    bindings["camera_frame"] = PHYSICAL_CAMERA_FRAME
    bindings["reference_model_sha256"] = model_sha256
    reseal(document)
    return document


def evidence_files(tmp_path: Path, *, crossed_tags: bool = False) -> dict[str, object]:
    landmark_document, model_sha = bare_jaw_landmark_record()
    paths = {
        "bracket_record_path": tmp_path / "bracket.json",
        "jpeg_path": tmp_path / "frame.jpg",
        "intrinsics_record_path": tmp_path / "intrinsics.json",
        "tag_evidence_path": tmp_path / "tags.json",
        "bare_jaw_calibration_path": tmp_path / "jaw-calibration.json",
        "bare_jaw_landmark_evidence_path": tmp_path / "jaw-landmarks.json",
    }
    hashes = {
        "expected_bracket_record_file_sha256": write(
            paths["bracket_record_path"], native_bracket_record()
        ),
        "expected_jpeg_file_sha256": write(
            paths["jpeg_path"], frame().jpeg_bytes
        ),
        "expected_intrinsics_file_sha256": write(
            paths["intrinsics_record_path"], reviewed_intrinsics_record()
        ),
        "expected_tag_evidence_file_sha256": write(
            paths["tag_evidence_path"], retained_tag_record(crossed_capture=crossed_tags)
        ),
        "expected_bare_jaw_calibration_file_sha256": write(
            paths["bare_jaw_calibration_path"],
            bare_jaw_calibration_record(model_sha),
        ),
        "expected_bare_jaw_landmark_evidence_file_sha256": write(
            paths["bare_jaw_landmark_evidence_path"], landmark_document
        ),
    }
    return {**paths, **hashes, "tag_map": _tag_map(), "role": "FIT"}


def test_compiles_all_pinned_retained_inputs_into_passive_capture(
    tmp_path: Path,
) -> None:
    result = compile_retained_fixed_camera_calibration_observation_v1(
        **evidence_files(tmp_path)
    )

    assert result.observation.compiled_capture["status"] == (
        "PASSIVE_CORRESPONDENCE_CAPTURED"
    )
    assert result.observation.compiled_capture["role"] == "FIT"
    assert result.observation.compiled_capture["profile"] == "no_attachment"
    receipt = result.receipt()
    assert receipt["capture_id"] == frame().capture_id
    assert len(receipt["source_file_sha256"]) == 6
    assert receipt["authority"]["controller_commands"] == []
    assert receipt["authority"]["physical_release_effect"] == "NONE"
    assert len(result.sha256) == 64


def test_refuses_crossed_tag_frame_before_emitting_capture(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="different frame"):
        compile_retained_fixed_camera_calibration_observation_v1(
            **evidence_files(tmp_path, crossed_tags=True)
        )


def test_requires_every_exact_file_pin(tmp_path: Path) -> None:
    values = evidence_files(tmp_path)
    values["expected_bare_jaw_landmark_evidence_file_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="bytes differ"):
        compile_retained_fixed_camera_calibration_observation_v1(**values)
