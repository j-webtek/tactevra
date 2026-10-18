"""Compile one passive fixed-camera observation from retained evidence files.

Every physical input to the native-frame observation coordinator already has a
strict, caller-pinned loader.  This module composes those loaders without
opening a camera or robot and preserves their existing cross-record checks.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from rocell.vision.planar_pose_estimator import PlanarBoardTagMap

from .fixed_camera_bare_jaw_landmark_evidence_v1 import (
    RetainedBareJawLandmarkEvidenceV1,
    load_retained_bare_jaw_landmark_evidence_v1,
)
from .fixed_camera_bare_jaw_observer_v1 import (
    FixedCameraBareJawObserverV1,
    ReviewedBareJawDetectorCalibrationV1,
    load_reviewed_bare_jaw_detector_calibration_v1,
)
from .fixed_camera_bracket_evidence_v1 import (
    RetainedFixedCameraBracketEvidenceV1,
    load_retained_fixed_camera_bracket_evidence_v1,
)
from .fixed_camera_calibration_observation_v1 import (
    FixedCameraCalibrationObservationV1,
    compile_fixed_camera_calibration_observation_v1,
)
from .fixed_camera_physical_intrinsics_v1 import (
    PhysicalNativeIntrinsicsRecordV1,
    load_reviewed_native_intrinsics_record_v1,
)
from .fixed_camera_tag_evidence_v1 import (
    RetainedFixedCameraTagEvidenceV1,
    load_retained_fixed_camera_tag_evidence_v1,
)


class FixedCameraRetainedObservationError(ValueError):
    """The retained observation inputs are incomplete or internally crossed."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraRetainedObservationError(
            "retained observation receipt is not canonical JSON"
        ) from exc


@dataclass(frozen=True, slots=True)
class RetainedFixedCameraCalibrationObservationV1:
    """Validated source records plus their passive compiled observation."""

    bracket_evidence: RetainedFixedCameraBracketEvidenceV1
    intrinsics_record: PhysicalNativeIntrinsicsRecordV1
    tag_evidence: RetainedFixedCameraTagEvidenceV1
    bare_jaw_calibration: ReviewedBareJawDetectorCalibrationV1
    bare_jaw_landmark_evidence: RetainedBareJawLandmarkEvidenceV1
    observation: FixedCameraCalibrationObservationV1

    def receipt(self) -> dict[str, object]:
        """Return a compact provenance receipt with explicitly zero authority."""

        return {
            "schema": "rocell.retained_fixed_camera_calibration_observation_receipt.v1",
            "status": "RETAINED_PASSIVE_CALIBRATION_OBSERVATION_COMPILED",
            "capture_id": self.bracket_evidence.bracket.frame.capture_id,
            "installation_epoch_id": (
                self.bracket_evidence.bracket.installation_epoch_id
            ),
            "role": self.observation.compiled_capture["role"],
            "source_file_sha256": {
                "bracket_record": self.bracket_evidence.record_file_sha256,
                "jpeg": self.bracket_evidence.jpeg_file_sha256,
                "intrinsics": self.intrinsics_record.source_file_sha256,
                "tag_evidence": self.tag_evidence.source_file_sha256,
                "bare_jaw_calibration": (
                    self.bare_jaw_calibration.source_file_sha256
                ),
                "bare_jaw_landmarks": (
                    self.bare_jaw_landmark_evidence.source_file_sha256
                ),
            },
            "validated_binding_sha256": {
                "bracket": self.bracket_evidence.bracket.sha256,
                "intrinsics_review": self.intrinsics_record.to_reviewed_binding().sha256,
                "tag_evidence": self.tag_evidence.canonical_sha256,
                "bare_jaw_calibration": self.bare_jaw_calibration.canonical_sha256,
                "bare_jaw_landmarks": (
                    self.bare_jaw_landmark_evidence.canonical_sha256
                ),
                "tag_map": self.observation.board_pose.full_tag_map_sha256,
            },
            "compiled_observation_sha256": self.observation.sha256,
            "compiled_capture_sha256": hashlib.sha256(
                _canonical(self.observation.compiled_capture)
            ).hexdigest(),
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "controller_commands": [],
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical(self.receipt())).hexdigest()


def compile_retained_fixed_camera_calibration_observation_v1(
    *,
    bracket_record_path: str | Path,
    jpeg_path: str | Path,
    intrinsics_record_path: str | Path,
    tag_evidence_path: str | Path,
    bare_jaw_calibration_path: str | Path,
    bare_jaw_landmark_evidence_path: str | Path,
    expected_bracket_record_file_sha256: str,
    expected_jpeg_file_sha256: str,
    expected_intrinsics_file_sha256: str,
    expected_tag_evidence_file_sha256: str,
    expected_bare_jaw_calibration_file_sha256: str,
    expected_bare_jaw_landmark_evidence_file_sha256: str,
    tag_map: PlanarBoardTagMap,
    role: str,
) -> RetainedFixedCameraCalibrationObservationV1:
    """Load exact retained inputs and compile one passive correspondence.

    The typed ``tag_map`` is independently bound by hash in the intrinsics and
    bare-jaw calibration records.  All frame, settings, detector, model, timing,
    and robot-state bindings remain enforced by the underlying reviewed
    loaders and observation coordinator.
    """

    if not isinstance(tag_map, PlanarBoardTagMap):
        raise TypeError("tag_map must be PlanarBoardTagMap")

    bracket = load_retained_fixed_camera_bracket_evidence_v1(
        bracket_record_path,
        jpeg_path,
        expected_record_file_sha256=expected_bracket_record_file_sha256,
        expected_jpeg_file_sha256=expected_jpeg_file_sha256,
    )
    intrinsics = load_reviewed_native_intrinsics_record_v1(
        intrinsics_record_path,
        expected_file_sha256=expected_intrinsics_file_sha256,
    )
    tags = load_retained_fixed_camera_tag_evidence_v1(
        tag_evidence_path,
        expected_file_sha256=expected_tag_evidence_file_sha256,
    )
    bare_jaw_calibration = load_reviewed_bare_jaw_detector_calibration_v1(
        bare_jaw_calibration_path,
        expected_file_sha256=expected_bare_jaw_calibration_file_sha256,
    )
    bare_jaw_landmarks = load_retained_bare_jaw_landmark_evidence_v1(
        bare_jaw_landmark_evidence_path,
        expected_file_sha256=expected_bare_jaw_landmark_evidence_file_sha256,
    )

    reviewed_intrinsics = intrinsics.to_reviewed_binding()
    detector = bare_jaw_landmarks.build_detector(
        bare_jaw_calibration,
        reviewed_intrinsics.intrinsics,
    )
    observer = FixedCameraBareJawObserverV1(bare_jaw_calibration, detector)
    observation = compile_fixed_camera_calibration_observation_v1(
        bracket.bracket,
        reviewed_intrinsics,
        tags,
        tags,
        tag_map,
        observer,
        role=role,
    )
    return RetainedFixedCameraCalibrationObservationV1(
        bracket_evidence=bracket,
        intrinsics_record=intrinsics,
        tag_evidence=tags,
        bare_jaw_calibration=bare_jaw_calibration,
        bare_jaw_landmark_evidence=bare_jaw_landmarks,
        observation=observation,
    )


__all__ = [
    "FixedCameraRetainedObservationError",
    "RetainedFixedCameraCalibrationObservationV1",
    "compile_retained_fixed_camera_calibration_observation_v1",
]
