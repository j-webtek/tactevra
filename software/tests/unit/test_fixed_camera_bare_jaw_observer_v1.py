from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.geometry import Point3Mm
from rocell.calibration.fixed_camera_bare_jaw_observer_v1 import (
    BareJawCameraObservationV1,
    FixedCameraBareJawObserverError,
    FixedCameraBareJawObserverV1,
    SCHEMA,
    STATUS,
    load_reviewed_bare_jaw_detector_calibration_v1,
    parse_reviewed_bare_jaw_detector_calibration_v1,
)
from rocell.vision.fixed_camera_board_pose_extractor_v1 import (
    estimate_fixed_camera_board_pose,
)

from test_fixed_camera_board_pose_extractor_v1 import (
    BOARD_FRAME,
    CAMERA_FRAME,
    GROUND_TRUTH,
    _batch,
    _frame,
    _intrinsics,
    _tag_map,
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def calibration_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": SCHEMA,
        "status": STATUS,
        "calibration_record_id": "rc03-bare-jaw-detector-physical-1",
        "detector": {
            "id": "rocell.fixed-camera-bare-jaw-reference",
            "version": "1.0.0",
            "configuration_sha256": "1" * 64,
            "implementation_sha256": "2" * 64,
        },
        "bindings": {
            "camera_intrinsics_sha256": _intrinsics().content_hash,
            "tag_map_sha256": _tag_map().content_hash,
            "camera_frame": CAMERA_FRAME,
            "reference_frame": "bare_jaw_reference",
            "reference_model_sha256": "3" * 64,
        },
        "physical_validation": {
            "physical_calibration_valid": True,
            "dataset_manifest_sha256": "4" * 64,
            "training_view_count": 8,
            "held_out_view_count": 3,
            "held_out_rms_mm": 0.4,
            "held_out_maximum_mm": 0.8,
            "maximum_detector_uncertainty_mm": 1.5,
        },
        "independent_review": {
            "producer_id": "calibration-producer-a",
            "reviewer_id": "physical-reviewer-b",
            "decision": "ACCEPT",
            "reviewed_at": "2026-10-17T20:00:00-04:00",
            "review_record_sha256": "5" * 64,
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
    document.update(changes)
    document["integrity_sha256"] = hashlib.sha256(canonical(document)).hexdigest()
    return document


def calibration(document: dict[str, object] | None = None):
    raw = document or calibration_document()
    return parse_reviewed_bare_jaw_detector_calibration_v1(
        raw,
        source_path=Path("retained-bare-jaw.json"),
        source_file_sha256="6" * 64,
    )


def board_pose():
    return estimate_fixed_camera_board_pose(_batch(), _intrinsics(), _tag_map())


class Detector:
    def __init__(
        self,
        reviewed,
        *,
        board_xyz: tuple[float, float, float] = (200.0, 150.0, 50.0),
        uncertainty_mm: float = 0.5,
        frame_sha256: str | None = None,
        calibration_sha256: str | None = None,
    ) -> None:
        board_point = Point3Mm(BOARD_FRAME, *board_xyz)
        camera_point = GROUND_TRUTH.transform_point(board_point)
        self.reviewed = reviewed
        self.camera_xyz = (camera_point.x, camera_point.y, camera_point.z)
        self.uncertainty_mm = uncertainty_mm
        self.frame_sha256 = frame_sha256
        self.calibration_sha256 = calibration_sha256
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        return BareJawCameraObservationV1(
            frame_sha256=self.frame_sha256 or frame.sha256,
            calibration_record_sha256=(
                self.calibration_sha256 or self.reviewed.canonical_sha256
            ),
            detector_id=self.reviewed.detector_id,
            detector_version=self.reviewed.detector_version,
            configuration_sha256=self.reviewed.configuration_sha256,
            implementation_sha256=self.reviewed.implementation_sha256,
            camera_frame=self.reviewed.camera_frame,
            camera_xyz_mm=self.camera_xyz,
            uncertainty_mm=self.uncertainty_mm,
        )


def test_observer_converts_camera_reference_to_exact_board_contract() -> None:
    reviewed = calibration()
    detector = Detector(reviewed)
    pose = board_pose()
    result = FixedCameraBareJawObserverV1(reviewed, detector).observe(_frame(), pose)

    assert detector.calls == 1
    assert result["method"] == "CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE"
    assert result["frame_sha256"] == pose.full_detection_batch.frame.jpeg_sha256
    assert result["detector_id"] == reviewed.detector_id
    assert result["board_xyz_mm"] == pytest.approx([200.0, 150.0, 50.0])
    assert 0.5 <= result["uncertainty_mm"] <= 3.0
    body = dict(result)
    observation_sha256 = body.pop("observation_sha256")
    assert observation_sha256 == hashlib.sha256(canonical(body)).hexdigest()


def test_loader_requires_exact_file_bytes_and_emits_zero_authority_receipt(
    tmp_path: Path,
) -> None:
    payload = canonical(calibration_document())
    path = tmp_path / "bare-jaw.json"
    path.write_bytes(payload)
    record = load_reviewed_bare_jaw_detector_calibration_v1(
        path, expected_file_sha256=hashlib.sha256(payload).hexdigest()
    )

    assert record.receipt()["authority"]["camera_opened"] is False
    with pytest.raises(FixedCameraBareJawObserverError, match="bytes differ"):
        load_reviewed_bare_jaw_detector_calibration_v1(
            path, expected_file_sha256="f" * 64
        )


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (
            lambda value: value["physical_validation"].update(
                {"physical_calibration_valid": False}
            ),
            "physical_calibration_valid",
        ),
        (
            lambda value: value["independent_review"].update(
                {"reviewer_id": "calibration-producer-a"}
            ),
            "reviewer must differ",
        ),
        (
            lambda value: value["authority"].update({"motion_authorized": True}),
            "motion_authorized",
        ),
        (
            lambda value: value["physical_validation"].update(
                {"held_out_maximum_mm": 2.0}
            ),
            "held-out maximum exceeds",
        ),
    ),
)
def test_calibration_rejects_unreviewed_or_overstated_meaning(
    mutator, message: str
) -> None:
    document = calibration_document()
    mutator(document)
    document["integrity_sha256"] = hashlib.sha256(
        canonical(
            {key: value for key, value in document.items() if key != "integrity_sha256"}
        )
    ).hexdigest()
    with pytest.raises(FixedCameraBareJawObserverError, match=message):
        calibration(document)


def test_calibration_rejects_integrity_tampering() -> None:
    document = calibration_document()
    document["detector"]["version"] = "2.0.0"
    with pytest.raises(FixedCameraBareJawObserverError, match="integrity_sha256"):
        calibration(document)


@pytest.mark.parametrize(
    ("detector_change", "message"),
    (
        ({"frame_sha256": "f" * 64}, "frame differs"),
        ({"calibration_sha256": "e" * 64}, "calibration record differs"),
        ({"uncertainty_mm": 2.0}, "reviewed detector limit"),
    ),
)
def test_observer_rejects_crossed_or_excessive_detector_evidence(
    detector_change: dict[str, object], message: str
) -> None:
    reviewed = calibration()
    pose = board_pose()
    observer = FixedCameraBareJawObserverV1(
        reviewed, Detector(reviewed, **detector_change)
    )
    with pytest.raises(FixedCameraBareJawObserverError, match=message):
        observer.observe(_frame(), pose)


def test_observer_rejects_reference_outside_board() -> None:
    reviewed = calibration()
    pose = board_pose()
    observer = FixedCameraBareJawObserverV1(
        reviewed, Detector(reviewed, board_xyz=(611.0, 100.0, 20.0))
    )
    with pytest.raises(FixedCameraBareJawObserverError, match="outside"):
        observer.observe(_frame(), pose)


def test_observer_rejects_board_pose_with_different_tag_map() -> None:
    document = calibration_document()
    document["bindings"]["tag_map_sha256"] = "a" * 64
    document["integrity_sha256"] = hashlib.sha256(
        canonical(
            {key: value for key, value in document.items() if key != "integrity_sha256"}
        )
    ).hexdigest()
    reviewed = calibration(document)
    pose = board_pose()
    detector = Detector(reviewed)
    with pytest.raises(FixedCameraBareJawObserverError, match="tag map differs"):
        FixedCameraBareJawObserverV1(reviewed, detector).observe(_frame(), pose)
    assert detector.calls == 0


def test_observation_rejects_nonfinite_camera_coordinate() -> None:
    with pytest.raises(FixedCameraBareJawObserverError, match="camera_xyz_mm"):
        BareJawCameraObservationV1(
            frame_sha256="1" * 64,
            calibration_record_sha256="2" * 64,
            detector_id="detector",
            detector_version="1",
            configuration_sha256="3" * 64,
            implementation_sha256="4" * 64,
            camera_frame=CAMERA_FRAME,
            camera_xyz_mm=(1.0, float("nan"), 2.0),
            uncertainty_mm=1.0,
        )
