"""Reviewed bare-jaw observation in the fixed-camera board frame.

This offline boundary consumes a detector-produced 3D bare-jaw reference in
the camera optical frame and the six-tag board pose from the same immutable
frame.  It validates a retained, independently reviewed detector calibration,
converts the point into ``RC03_board``, and emits the exact tool-reference
mapping accepted by the passive calibration-capture compiler.

The module reads retained JSON only.  It cannot open a camera, contact a robot,
generate motion, or promote a physical calibration gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from rocell.geometry import Point3Mm
from rocell.vision.camera import FramePacket
from rocell.vision.fixed_camera_board_pose_extractor_v1 import (
    FixedCameraBoardPoseResult,
)


SCHEMA = "rocell.reviewed_fixed_camera_bare_jaw_detector.v1"
STATUS = "REVIEWED_PHYSICAL_BARE_JAW_DETECTOR"
METHOD = "CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE"
BOARD_FRAME = "RC03_board"
REFERENCE_FRAME = "bare_jaw_reference"
MAX_RECORD_BYTES = 512 * 1024
MAX_TOOL_REFERENCE_UNCERTAINTY_MM = 3.0

_ROOT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "calibration_record_id",
        "detector",
        "bindings",
        "physical_validation",
        "independent_review",
        "authority",
        "integrity_sha256",
    }
)
_DETECTOR_FIELDS = frozenset(
    {"id", "version", "configuration_sha256", "implementation_sha256"}
)
_BINDING_FIELDS = frozenset(
    {
        "camera_intrinsics_sha256",
        "tag_map_sha256",
        "camera_frame",
        "reference_frame",
        "reference_model_sha256",
    }
)
_VALIDATION_FIELDS = frozenset(
    {
        "physical_calibration_valid",
        "dataset_manifest_sha256",
        "training_view_count",
        "held_out_view_count",
        "held_out_rms_mm",
        "held_out_maximum_mm",
        "maximum_detector_uncertainty_mm",
    }
)
_REVIEW_FIELDS = frozenset(
    {"producer_id", "reviewer_id", "decision", "reviewed_at", "review_record_sha256"}
)
_AUTHORITY_FIELDS = frozenset(
    {
        "camera_opened",
        "robot_provider_called",
        "motion_targets_emitted",
        "motion_authorized",
        "contact_authorized",
        "physical_release_effect",
    }
)


class FixedCameraBareJawObserverError(ValueError):
    """Retained calibration or bare-jaw evidence is inconsistent."""


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
        raise FixedCameraBareJawObserverError(
            "bare-jaw evidence is not canonical JSON"
        ) from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixedCameraBareJawObserverError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise FixedCameraBareJawObserverError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _text(value: object, label: str, *, maximum: int = 160) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise FixedCameraBareJawObserverError(
            f"{label} must be non-empty bounded trimmed text"
        )
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraBareJawObserverError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _boolean(value: object, expected: bool, label: str) -> bool:
    if type(value) is not bool or value is not expected:
        raise FixedCameraBareJawObserverError(f"{label} must be {expected}")
    return expected


def _integer(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FixedCameraBareJawObserverError(
            f"{label} must be an integer >= {minimum}"
        )
    return value


def _finite(value: object, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraBareJawObserverError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise FixedCameraBareJawObserverError(
            f"{label} must be finite and in [{minimum}, {maximum}]"
        )
    return result


def _reject_constant(value: str) -> None:
    raise FixedCameraBareJawObserverError(
        f"bare-jaw calibration contains nonfinite constant {value!r}"
    )


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraBareJawObserverError(
                f"bare-jaw calibration contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _review_time(value: object) -> str:
    text = _text(value, "independent_review.reviewed_at", maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixedCameraBareJawObserverError(
            "independent_review.reviewed_at must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixedCameraBareJawObserverError(
            "independent_review.reviewed_at must include a UTC offset"
        )
    return text


@dataclass(frozen=True, slots=True)
class ReviewedBareJawDetectorCalibrationV1:
    """Validated retained detector calibration and review binding."""

    source_path: Path
    source_file_sha256: str
    canonical_sha256: str
    integrity_sha256: str
    calibration_record_id: str
    detector_id: str
    detector_version: str
    configuration_sha256: str
    implementation_sha256: str
    camera_intrinsics_sha256: str
    tag_map_sha256: str
    camera_frame: str
    reference_model_sha256: str
    maximum_detector_uncertainty_mm: float
    dataset_manifest_sha256: str
    training_view_count: int
    held_out_view_count: int
    held_out_rms_mm: float
    held_out_maximum_mm: float
    producer_id: str
    reviewer_id: str
    reviewed_at: str
    review_record_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_path, Path):
            raise TypeError("source_path must be Path")
        for value, label in (
            (self.source_file_sha256, "source_file_sha256"),
            (self.canonical_sha256, "canonical_sha256"),
            (self.integrity_sha256, "integrity_sha256"),
            (self.configuration_sha256, "configuration_sha256"),
            (self.implementation_sha256, "implementation_sha256"),
            (self.camera_intrinsics_sha256, "camera_intrinsics_sha256"),
            (self.tag_map_sha256, "tag_map_sha256"),
            (self.reference_model_sha256, "reference_model_sha256"),
            (self.dataset_manifest_sha256, "dataset_manifest_sha256"),
            (self.review_record_sha256, "review_record_sha256"),
        ):
            _digest(value, label)
        for value, label in (
            (self.calibration_record_id, "calibration_record_id"),
            (self.detector_id, "detector_id"),
            (self.detector_version, "detector_version"),
            (self.camera_frame, "camera_frame"),
            (self.producer_id, "producer_id"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _text(value, label)
        if self.producer_id == self.reviewer_id:
            raise FixedCameraBareJawObserverError(
                "independent reviewer must differ from the calibration producer"
            )
        _review_time(self.reviewed_at)
        _integer(self.training_view_count, "training_view_count", minimum=3)
        _integer(self.held_out_view_count, "held_out_view_count", minimum=2)
        detector_limit = _finite(
            self.maximum_detector_uncertainty_mm,
            "maximum_detector_uncertainty_mm",
            minimum=0.0,
            maximum=MAX_TOOL_REFERENCE_UNCERTAINTY_MM,
        )
        rms = _finite(
            self.held_out_rms_mm,
            "held_out_rms_mm",
            minimum=0.0,
            maximum=MAX_TOOL_REFERENCE_UNCERTAINTY_MM,
        )
        maximum = _finite(
            self.held_out_maximum_mm,
            "held_out_maximum_mm",
            minimum=0.0,
            maximum=MAX_TOOL_REFERENCE_UNCERTAINTY_MM,
        )
        if rms > maximum or maximum > detector_limit:
            raise FixedCameraBareJawObserverError(
                "reviewed held-out metrics exceed the detector uncertainty limit"
            )

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "rocell.reviewed_fixed_camera_bare_jaw_detector_receipt.v1",
            "status": "REVIEWED_BARE_JAW_DETECTOR_ACCEPTED",
            "source_file_sha256": self.source_file_sha256,
            "canonical_sha256": self.canonical_sha256,
            "integrity_sha256": self.integrity_sha256,
            "calibration_record_id": self.calibration_record_id,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "reviewer_id": self.reviewer_id,
            "reviewed_at": self.reviewed_at,
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }


@dataclass(frozen=True, slots=True)
class BareJawCameraObservationV1:
    """One calibrated 3D bare-jaw reference in the camera optical frame."""

    frame_sha256: str
    calibration_record_sha256: str
    detector_id: str
    detector_version: str
    configuration_sha256: str
    implementation_sha256: str
    camera_frame: str
    camera_xyz_mm: tuple[float, float, float]
    uncertainty_mm: float

    def __post_init__(self) -> None:
        for value, label in (
            (self.frame_sha256, "frame_sha256"),
            (self.calibration_record_sha256, "calibration_record_sha256"),
            (self.configuration_sha256, "configuration_sha256"),
            (self.implementation_sha256, "implementation_sha256"),
        ):
            _digest(value, label)
        _text(self.detector_id, "detector_id")
        _text(self.detector_version, "detector_version")
        _text(self.camera_frame, "camera_frame")
        if len(self.camera_xyz_mm) != 3:
            raise FixedCameraBareJawObserverError(
                "camera_xyz_mm must contain exactly three values"
            )
        xyz = tuple(
            _finite(value, f"camera_xyz_mm[{index}]", minimum=-10000.0, maximum=10000.0)
            for index, value in enumerate(self.camera_xyz_mm)
        )
        object.__setattr__(self, "camera_xyz_mm", xyz)
        object.__setattr__(
            self,
            "uncertainty_mm",
            _finite(
                self.uncertainty_mm,
                "uncertainty_mm",
                minimum=0.0,
                maximum=MAX_TOOL_REFERENCE_UNCERTAINTY_MM,
            ),
        )


class CalibratedBareJawDetector(Protocol):
    """Side-effect-free detector already configured by the retained record."""

    def detect(self, frame: FramePacket) -> BareJawCameraObservationV1: ...


def parse_reviewed_bare_jaw_detector_calibration_v1(
    raw: Mapping[str, Any], *, source_path: Path, source_file_sha256: str
) -> ReviewedBareJawDetectorCalibrationV1:
    """Validate parsed calibration meaning and independent review evidence."""

    _exact(raw, _ROOT_FIELDS, "record")
    if raw.get("schema") != SCHEMA:
        raise FixedCameraBareJawObserverError(f"schema must be {SCHEMA!r}")
    if raw.get("status") != STATUS:
        raise FixedCameraBareJawObserverError(f"status must be {STATUS!r}")
    calibration_record_id = _text(
        raw.get("calibration_record_id"), "calibration_record_id"
    )

    detector = _mapping(raw.get("detector"), "detector")
    _exact(detector, _DETECTOR_FIELDS, "detector")
    detector_id = _text(detector.get("id"), "detector.id")
    detector_version = _text(detector.get("version"), "detector.version")
    configuration_sha256 = _digest(
        detector.get("configuration_sha256"), "detector.configuration_sha256"
    )
    implementation_sha256 = _digest(
        detector.get("implementation_sha256"), "detector.implementation_sha256"
    )

    bindings = _mapping(raw.get("bindings"), "bindings")
    _exact(bindings, _BINDING_FIELDS, "bindings")
    intrinsics_sha256 = _digest(
        bindings.get("camera_intrinsics_sha256"),
        "bindings.camera_intrinsics_sha256",
    )
    tag_map_sha256 = _digest(bindings.get("tag_map_sha256"), "bindings.tag_map_sha256")
    camera_frame = _text(bindings.get("camera_frame"), "bindings.camera_frame")
    if bindings.get("reference_frame") != REFERENCE_FRAME:
        raise FixedCameraBareJawObserverError(
            f"bindings.reference_frame must be {REFERENCE_FRAME!r}"
        )
    reference_model_sha256 = _digest(
        bindings.get("reference_model_sha256"), "bindings.reference_model_sha256"
    )

    validation = _mapping(raw.get("physical_validation"), "physical_validation")
    _exact(validation, _VALIDATION_FIELDS, "physical_validation")
    _boolean(
        validation.get("physical_calibration_valid"),
        True,
        "physical_validation.physical_calibration_valid",
    )
    dataset_manifest_sha256 = _digest(
        validation.get("dataset_manifest_sha256"),
        "physical_validation.dataset_manifest_sha256",
    )
    training_view_count = _integer(
        validation.get("training_view_count"),
        "physical_validation.training_view_count",
        minimum=3,
    )
    held_out_view_count = _integer(
        validation.get("held_out_view_count"),
        "physical_validation.held_out_view_count",
        minimum=2,
    )
    held_out_rms_mm = _finite(
        validation.get("held_out_rms_mm"),
        "physical_validation.held_out_rms_mm",
        minimum=0.0,
        maximum=MAX_TOOL_REFERENCE_UNCERTAINTY_MM,
    )
    held_out_maximum_mm = _finite(
        validation.get("held_out_maximum_mm"),
        "physical_validation.held_out_maximum_mm",
        minimum=0.0,
        maximum=MAX_TOOL_REFERENCE_UNCERTAINTY_MM,
    )
    maximum_detector_uncertainty_mm = _finite(
        validation.get("maximum_detector_uncertainty_mm"),
        "physical_validation.maximum_detector_uncertainty_mm",
        minimum=0.0,
        maximum=MAX_TOOL_REFERENCE_UNCERTAINTY_MM,
    )
    if held_out_rms_mm > held_out_maximum_mm:
        raise FixedCameraBareJawObserverError(
            "held-out RMS cannot exceed held-out maximum"
        )
    if held_out_maximum_mm > maximum_detector_uncertainty_mm:
        raise FixedCameraBareJawObserverError(
            "held-out maximum exceeds the reviewed detector uncertainty"
        )

    review = _mapping(raw.get("independent_review"), "independent_review")
    _exact(review, _REVIEW_FIELDS, "independent_review")
    producer_id = _text(review.get("producer_id"), "independent_review.producer_id")
    reviewer_id = _text(review.get("reviewer_id"), "independent_review.reviewer_id")
    if producer_id == reviewer_id:
        raise FixedCameraBareJawObserverError(
            "independent reviewer must differ from the calibration producer"
        )
    if review.get("decision") != "ACCEPT":
        raise FixedCameraBareJawObserverError(
            "independent_review.decision must be 'ACCEPT'"
        )
    reviewed_at = _review_time(review.get("reviewed_at"))
    review_record_sha256 = _digest(
        review.get("review_record_sha256"),
        "independent_review.review_record_sha256",
    )

    authority = _mapping(raw.get("authority"), "authority")
    _exact(authority, _AUTHORITY_FIELDS, "authority")
    for name in (
        "camera_opened",
        "robot_provider_called",
        "motion_targets_emitted",
        "motion_authorized",
        "contact_authorized",
    ):
        _boolean(authority.get(name), False, f"authority.{name}")
    if authority.get("physical_release_effect") != "NONE":
        raise FixedCameraBareJawObserverError(
            "authority.physical_release_effect must be 'NONE'"
        )

    integrity_sha256 = _digest(raw.get("integrity_sha256"), "integrity_sha256")
    meaning = dict(raw)
    meaning.pop("integrity_sha256")
    if integrity_sha256 != _hash(meaning):
        raise FixedCameraBareJawObserverError(
            "integrity_sha256 does not match the record meaning"
        )

    return ReviewedBareJawDetectorCalibrationV1(
        source_path=source_path,
        source_file_sha256=source_file_sha256,
        canonical_sha256=_hash(raw),
        integrity_sha256=integrity_sha256,
        calibration_record_id=calibration_record_id,
        detector_id=detector_id,
        detector_version=detector_version,
        configuration_sha256=configuration_sha256,
        implementation_sha256=implementation_sha256,
        camera_intrinsics_sha256=intrinsics_sha256,
        tag_map_sha256=tag_map_sha256,
        camera_frame=camera_frame,
        reference_model_sha256=reference_model_sha256,
        maximum_detector_uncertainty_mm=maximum_detector_uncertainty_mm,
        dataset_manifest_sha256=dataset_manifest_sha256,
        training_view_count=training_view_count,
        held_out_view_count=held_out_view_count,
        held_out_rms_mm=held_out_rms_mm,
        held_out_maximum_mm=held_out_maximum_mm,
        producer_id=producer_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_record_sha256=review_record_sha256,
    )


def load_reviewed_bare_jaw_detector_calibration_v1(
    path: str | Path, *, expected_file_sha256: str
) -> ReviewedBareJawDetectorCalibrationV1:
    """Load one exact caller-pinned retained detector calibration record."""

    expected = _digest(expected_file_sha256, "expected_file_sha256")
    source_path = Path(path).resolve()
    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        raise FixedCameraBareJawObserverError(
            f"cannot read bare-jaw calibration record: {exc}"
        ) from exc
    if not payload or len(payload) > MAX_RECORD_BYTES:
        raise FixedCameraBareJawObserverError(
            f"bare-jaw calibration record must be 1..{MAX_RECORD_BYTES} bytes"
        )
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise FixedCameraBareJawObserverError(
            "bare-jaw calibration bytes differ from expected_file_sha256"
        )
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraBareJawObserverError(
            f"bare-jaw calibration record is not strict JSON: {exc}"
        ) from exc
    return parse_reviewed_bare_jaw_detector_calibration_v1(
        _mapping(raw, "record"),
        source_path=source_path,
        source_file_sha256=actual,
    )


@dataclass(frozen=True, slots=True)
class FixedCameraBareJawObserverV1:
    """Convert one reviewed camera-frame detection into ``RC03_board``."""

    calibration: ReviewedBareJawDetectorCalibrationV1
    detector: CalibratedBareJawDetector

    def __post_init__(self) -> None:
        if not isinstance(self.calibration, ReviewedBareJawDetectorCalibrationV1):
            raise TypeError("calibration must be ReviewedBareJawDetectorCalibrationV1")
        if not callable(getattr(self.detector, "detect", None)):
            raise TypeError("detector must provide detect(frame)")

    def observe(
        self, frame: FramePacket, board_pose: FixedCameraBoardPoseResult
    ) -> Mapping[str, Any]:
        if not isinstance(frame, FramePacket):
            raise TypeError("frame must be FramePacket")
        if not isinstance(board_pose, FixedCameraBoardPoseResult):
            raise TypeError("board_pose must be FixedCameraBoardPoseResult")
        fit = board_pose.fit_observation
        pose = fit.pose
        if board_pose.full_detection_batch.frame.jpeg_sha256 != frame.sha256:
            raise FixedCameraBareJawObserverError(
                "board pose and bare-jaw detector must use the same frame"
            )
        if fit.camera_intrinsics_sha256 != self.calibration.camera_intrinsics_sha256:
            raise FixedCameraBareJawObserverError(
                "board pose intrinsics differ from the reviewed bare-jaw calibration"
            )
        if board_pose.full_tag_map_sha256 != self.calibration.tag_map_sha256:
            raise FixedCameraBareJawObserverError(
                "board pose tag map differs from the reviewed bare-jaw calibration"
            )
        if (
            pose.parent_frame != self.calibration.camera_frame
            or pose.child_frame != BOARD_FRAME
        ):
            raise FixedCameraBareJawObserverError(
                "board pose frames differ from the reviewed bare-jaw calibration"
            )

        detected = self.detector.detect(frame)
        if not isinstance(detected, BareJawCameraObservationV1):
            raise TypeError("bare-jaw detector must return BareJawCameraObservationV1")
        expected_bindings = (
            (detected.frame_sha256, frame.sha256, "frame"),
            (
                detected.calibration_record_sha256,
                self.calibration.canonical_sha256,
                "calibration record",
            ),
            (detected.detector_id, self.calibration.detector_id, "detector id"),
            (
                detected.detector_version,
                self.calibration.detector_version,
                "detector version",
            ),
            (
                detected.configuration_sha256,
                self.calibration.configuration_sha256,
                "detector configuration",
            ),
            (
                detected.implementation_sha256,
                self.calibration.implementation_sha256,
                "detector implementation",
            ),
            (detected.camera_frame, self.calibration.camera_frame, "camera frame"),
        )
        for actual, expected, label in expected_bindings:
            if actual != expected:
                raise FixedCameraBareJawObserverError(
                    f"bare-jaw {label} differs from reviewed calibration"
                )
        if detected.uncertainty_mm > self.calibration.maximum_detector_uncertainty_mm:
            raise FixedCameraBareJawObserverError(
                "bare-jaw uncertainty exceeds the reviewed detector limit"
            )

        camera_point = Point3Mm(
            detected.camera_frame,
            detected.camera_xyz_mm[0],
            detected.camera_xyz_mm[1],
            detected.camera_xyz_mm[2],
        )
        board_point = pose.inverse().transform_point(camera_point)
        translation_sigma_mm = math.sqrt(
            max(fit.covariance.row_major[index] for index in (0, 7, 14))
        )
        uncertainty_mm = detected.uncertainty_mm + translation_sigma_mm
        if uncertainty_mm > MAX_TOOL_REFERENCE_UNCERTAINTY_MM:
            raise FixedCameraBareJawObserverError(
                "combined bare-jaw and board-pose uncertainty exceeds 3 mm"
            )
        board_xyz = [board_point.x, board_point.y, board_point.z]
        if not (0.0 <= board_point.x <= 610.0 and 0.0 <= board_point.y <= 457.0):
            raise FixedCameraBareJawObserverError(
                "bare-jaw reference lies outside the 610 x 457 mm RC03 board"
            )

        body: dict[str, object] = {
            "method": METHOD,
            "frame_sha256": frame.sha256,
            "detector_id": self.calibration.detector_id,
            "detector_version": self.calibration.detector_version,
            "configuration_sha256": self.calibration.configuration_sha256,
            "implementation_sha256": self.calibration.implementation_sha256,
            "board_xyz_mm": board_xyz,
            "uncertainty_mm": uncertainty_mm,
        }
        return {"observation_sha256": _hash(body), **body}


__all__ = [
    "BOARD_FRAME",
    "BareJawCameraObservationV1",
    "CalibratedBareJawDetector",
    "FixedCameraBareJawObserverError",
    "FixedCameraBareJawObserverV1",
    "MAX_RECORD_BYTES",
    "MAX_TOOL_REFERENCE_UNCERTAINTY_MM",
    "METHOD",
    "REFERENCE_FRAME",
    "ReviewedBareJawDetectorCalibrationV1",
    "SCHEMA",
    "STATUS",
    "load_reviewed_bare_jaw_detector_calibration_v1",
    "parse_reviewed_bare_jaw_detector_calibration_v1",
]
