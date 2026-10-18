"""Strict retained-file intake for bare-jaw landmark pose evidence.

The audited landmark adapter accepts an injected pose source so that image
processing remains outside its policy boundary.  This module supplies the
content-addressed retained-file implementation of that source.  It validates
one exact native-frame evidence package, reconstructs the rigid jaw model and
camera pose, and refuses to replay the estimate against any other frame,
intrinsics, settings, or model.

The loader performs bounded filesystem reads only.  It cannot open a camera,
read a robot, emit a command, authorize motion or contact, or promote a
physical calibration freeze.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.geometry import Point3Mm, RigidTransform, Rotation3, Vec3
from rocell.vision.camera import FramePacket
from rocell.vision.planar_pose_estimator import PinholeIntrinsics

from .fixed_camera_bare_jaw_landmarks_v1 import (
    REFERENCE_FRAME,
    AuditedBareJawLandmarkDetectorV1,
    BareJawLandmarkPoseEstimateV1,
    BareJawPixelLandmarkV1,
    BareJawReferenceLandmarkV1,
    BareJawReferenceModelV1,
)
from .fixed_camera_bare_jaw_observer_v1 import (
    ReviewedBareJawDetectorCalibrationV1,
)


SCHEMA = "rocell.retained_bare_jaw_landmark_evidence.v1"
STATUS = "RETAINED_BARE_JAW_LANDMARK_EVIDENCE"
MAX_RECORD_BYTES = 512 * 1024

_ROOT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "frame_binding",
        "detector",
        "reference_model",
        "estimate",
        "authority",
        "integrity_sha256",
    }
)
_FRAME_FIELDS = frozenset(
    {
        "capture_id",
        "frame_sha256",
        "settings_sha256",
        "width_px",
        "height_px",
        "camera_frame",
        "pixel_space",
        "intrinsics_sha256",
    }
)
_DETECTOR_FIELDS = frozenset(
    {"id", "version", "configuration_sha256", "implementation_sha256"}
)
_MODEL_FIELDS = frozenset({"model_id", "reference_frame", "landmarks"})
_MODEL_LANDMARK_FIELDS = frozenset({"landmark_id", "xyz_mm"})
_ESTIMATE_FIELDS = frozenset(
    {
        "parent_frame",
        "child_frame",
        "rotation_row_major",
        "translation_mm",
        "uncertainty_mm",
        "landmarks",
    }
)
_PIXEL_LANDMARK_FIELDS = frozenset({"landmark_id", "x_px", "y_px", "role"})
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


class FixedCameraBareJawLandmarkEvidenceError(ValueError):
    """Retained landmark evidence is malformed, crossed, or unpinned."""


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
        raise FixedCameraBareJawLandmarkEvidenceError(
            "bare-jaw landmark evidence is not canonical JSON"
        ) from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _reject_constant(value: str) -> None:
    raise FixedCameraBareJawLandmarkEvidenceError(
        f"bare-jaw landmark evidence contains nonfinite constant {value!r}"
    )


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraBareJawLandmarkEvidenceError(
                f"bare-jaw landmark evidence contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixedCameraBareJawLandmarkEvidenceError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _text(value: object, label: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"{label} must be non-empty bounded trimmed text"
        )
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _integer(value: object, label: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"{label} must be an integer >= {minimum}"
        )
    return value


def _finite(
    value: object, label: str, *, minimum: float, maximum: float
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraBareJawLandmarkEvidenceError(f"{label} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"{label} must be finite and in [{minimum}, {maximum}]"
        )
    return parsed


def _numeric_array(
    value: object,
    label: str,
    *,
    length: int,
    minimum: float,
    maximum: float,
) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"{label} must contain exactly {length} values"
        )
    return tuple(
        _finite(item, f"{label}[{index}]", minimum=minimum, maximum=maximum)
        for index, item in enumerate(value)
    )


def _false(value: object, label: str) -> None:
    if type(value) is not bool or value is not False:
        raise FixedCameraBareJawLandmarkEvidenceError(f"{label} must be False")


@dataclass(frozen=True, slots=True)
class RetainedBareJawLandmarkPoseSourceV1:
    """One exact retained estimate replayable only for its bound inputs."""

    detector_id: str
    detector_version: str
    configuration_sha256: str
    implementation_sha256: str
    capture_id: str
    frame_sha256: str
    settings_sha256: str
    width_px: int
    height_px: int
    camera_frame: str
    pixel_space: str
    intrinsics_sha256: str
    reference_model_sha256: str
    estimate_value: BareJawLandmarkPoseEstimateV1

    def __post_init__(self) -> None:
        for value, label in (
            (self.detector_id, "detector_id"),
            (self.detector_version, "detector_version"),
            (self.capture_id, "capture_id"),
            (self.camera_frame, "camera_frame"),
            (self.pixel_space, "pixel_space"),
        ):
            _text(value, label)
        for value, label in (
            (self.configuration_sha256, "configuration_sha256"),
            (self.implementation_sha256, "implementation_sha256"),
            (self.frame_sha256, "frame_sha256"),
            (self.settings_sha256, "settings_sha256"),
            (self.intrinsics_sha256, "intrinsics_sha256"),
            (self.reference_model_sha256, "reference_model_sha256"),
        ):
            _digest(value, label)
        _integer(self.width_px, "width_px")
        _integer(self.height_px, "height_px")
        if not isinstance(self.estimate_value, BareJawLandmarkPoseEstimateV1):
            raise TypeError("estimate_value must be BareJawLandmarkPoseEstimateV1")
        if self.estimate_value.frame_sha256 != self.frame_sha256:
            raise FixedCameraBareJawLandmarkEvidenceError(
                "estimate frame differs from retained frame binding"
            )
        transform = self.estimate_value.camera_T_reference
        if (
            transform.parent_frame != self.camera_frame
            or transform.child_frame != REFERENCE_FRAME
        ):
            raise FixedCameraBareJawLandmarkEvidenceError(
                "estimate transform frames differ from retained frame binding"
            )

    def estimate(
        self,
        frame: FramePacket,
        intrinsics: PinholeIntrinsics,
        model: BareJawReferenceModelV1,
    ) -> BareJawLandmarkPoseEstimateV1:
        if not isinstance(frame, FramePacket):
            raise TypeError("frame must be FramePacket")
        if not isinstance(intrinsics, PinholeIntrinsics):
            raise TypeError("intrinsics must be PinholeIntrinsics")
        if not isinstance(model, BareJawReferenceModelV1):
            raise TypeError("model must be BareJawReferenceModelV1")
        bindings = (
            (frame.capture_id, self.capture_id, "capture id"),
            (frame.sha256, self.frame_sha256, "frame"),
            (frame.settings_hash, self.settings_sha256, "camera settings"),
            (frame.width_px, self.width_px, "frame width"),
            (frame.height_px, self.height_px, "frame height"),
            (intrinsics.camera_frame, self.camera_frame, "camera frame"),
            (intrinsics.pixel_space, self.pixel_space, "pixel space"),
            (intrinsics.content_hash, self.intrinsics_sha256, "intrinsics"),
            (model.source_sha256, self.reference_model_sha256, "reference model"),
        )
        for actual, expected, label in bindings:
            if actual != expected:
                raise FixedCameraBareJawLandmarkEvidenceError(
                    f"{label} differs from retained landmark evidence"
                )
        return self.estimate_value


@dataclass(frozen=True, slots=True)
class RetainedBareJawLandmarkEvidenceV1:
    """Validated record plus objects accepted by the audited adapter."""

    source_path: Path
    source_file_sha256: str
    canonical_sha256: str
    integrity_sha256: str
    model: BareJawReferenceModelV1
    pose_source: RetainedBareJawLandmarkPoseSourceV1

    def build_detector(
        self,
        calibration: ReviewedBareJawDetectorCalibrationV1,
        intrinsics: PinholeIntrinsics,
    ) -> AuditedBareJawLandmarkDetectorV1:
        """Compose the existing audited adapter from the retained evidence."""

        return AuditedBareJawLandmarkDetectorV1(
            calibration=calibration,
            intrinsics=intrinsics,
            model=self.model,
            source=self.pose_source,
        )

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "rocell.retained_bare_jaw_landmark_evidence_receipt.v1",
            "status": "RETAINED_BARE_JAW_LANDMARK_EVIDENCE_ACCEPTED",
            "source_file_sha256": self.source_file_sha256,
            "canonical_sha256": self.canonical_sha256,
            "integrity_sha256": self.integrity_sha256,
            "frame_sha256": self.pose_source.frame_sha256,
            "intrinsics_sha256": self.pose_source.intrinsics_sha256,
            "reference_model_sha256": self.model.source_sha256,
            "landmark_count": len(self.model.landmarks),
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }


def parse_retained_bare_jaw_landmark_evidence_v1(
    raw: Mapping[str, Any], *, source_path: Path, source_file_sha256: str
) -> RetainedBareJawLandmarkEvidenceV1:
    """Validate parsed retained evidence and reconstruct its typed objects."""

    _exact(raw, _ROOT_FIELDS, "record")
    if raw.get("schema") != SCHEMA:
        raise FixedCameraBareJawLandmarkEvidenceError(f"schema must be {SCHEMA!r}")
    if raw.get("status") != STATUS:
        raise FixedCameraBareJawLandmarkEvidenceError(f"status must be {STATUS!r}")

    frame = _mapping(raw.get("frame_binding"), "frame_binding")
    _exact(frame, _FRAME_FIELDS, "frame_binding")
    capture_id = _text(frame.get("capture_id"), "frame_binding.capture_id")
    frame_sha256 = _digest(frame.get("frame_sha256"), "frame_binding.frame_sha256")
    settings_sha256 = _digest(
        frame.get("settings_sha256"), "frame_binding.settings_sha256"
    )
    width_px = _integer(frame.get("width_px"), "frame_binding.width_px")
    height_px = _integer(frame.get("height_px"), "frame_binding.height_px")
    camera_frame = _text(frame.get("camera_frame"), "frame_binding.camera_frame")
    pixel_space = _text(frame.get("pixel_space"), "frame_binding.pixel_space")
    intrinsics_sha256 = _digest(
        frame.get("intrinsics_sha256"), "frame_binding.intrinsics_sha256"
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

    model_raw = _mapping(raw.get("reference_model"), "reference_model")
    _exact(model_raw, _MODEL_FIELDS, "reference_model")
    if model_raw.get("reference_frame") != REFERENCE_FRAME:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"reference_model.reference_frame must be {REFERENCE_FRAME!r}"
        )
    model_id = _text(model_raw.get("model_id"), "reference_model.model_id")
    model_landmarks_raw = model_raw.get("landmarks")
    if not isinstance(model_landmarks_raw, list):
        raise FixedCameraBareJawLandmarkEvidenceError(
            "reference_model.landmarks must be an array"
        )
    model_landmarks: list[BareJawReferenceLandmarkV1] = []
    for index, item in enumerate(model_landmarks_raw):
        landmark = _mapping(item, f"reference_model.landmarks[{index}]")
        _exact(
            landmark,
            _MODEL_LANDMARK_FIELDS,
            f"reference_model.landmarks[{index}]",
        )
        landmark_id = _text(
            landmark.get("landmark_id"),
            f"reference_model.landmarks[{index}].landmark_id",
        )
        xyz = _numeric_array(
            landmark.get("xyz_mm"),
            f"reference_model.landmarks[{index}].xyz_mm",
            length=3,
            minimum=-1000.0,
            maximum=1000.0,
        )
        model_landmarks.append(
            BareJawReferenceLandmarkV1(
                landmark_id,
                Point3Mm(REFERENCE_FRAME, xyz[0], xyz[1], xyz[2]),
            )
        )
    reference_model_sha256 = _hash(model_raw)
    try:
        model = BareJawReferenceModelV1(
            model_id=model_id,
            source_sha256=reference_model_sha256,
            landmarks=tuple(model_landmarks),
        )
    except (TypeError, ValueError) as exc:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"reference_model is invalid: {exc}"
        ) from exc

    estimate = _mapping(raw.get("estimate"), "estimate")
    _exact(estimate, _ESTIMATE_FIELDS, "estimate")
    if estimate.get("parent_frame") != camera_frame:
        raise FixedCameraBareJawLandmarkEvidenceError(
            "estimate.parent_frame must match frame_binding.camera_frame"
        )
    if estimate.get("child_frame") != REFERENCE_FRAME:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"estimate.child_frame must be {REFERENCE_FRAME!r}"
        )
    rotation_values = _numeric_array(
        estimate.get("rotation_row_major"),
        "estimate.rotation_row_major",
        length=9,
        minimum=-1.0,
        maximum=1.0,
    )
    translation = _numeric_array(
        estimate.get("translation_mm"),
        "estimate.translation_mm",
        length=3,
        minimum=-10000.0,
        maximum=10000.0,
    )
    uncertainty_mm = _finite(
        estimate.get("uncertainty_mm"),
        "estimate.uncertainty_mm",
        minimum=0.0,
        maximum=100.0,
    )
    try:
        transform = RigidTransform(
            camera_frame,
            REFERENCE_FRAME,
            Rotation3(rotation_values),
            Vec3(*translation),
        )
    except ValueError as exc:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"estimate transform is invalid: {exc}"
        ) from exc

    pixel_landmarks_raw = estimate.get("landmarks")
    if not isinstance(pixel_landmarks_raw, list):
        raise FixedCameraBareJawLandmarkEvidenceError(
            "estimate.landmarks must be an array"
        )
    pixel_landmarks: list[BareJawPixelLandmarkV1] = []
    for index, item in enumerate(pixel_landmarks_raw):
        landmark = _mapping(item, f"estimate.landmarks[{index}]")
        _exact(
            landmark,
            _PIXEL_LANDMARK_FIELDS,
            f"estimate.landmarks[{index}]",
        )
        try:
            pixel_landmarks.append(
                BareJawPixelLandmarkV1(
                    landmark_id=_text(
                        landmark.get("landmark_id"),
                        f"estimate.landmarks[{index}].landmark_id",
                    ),
                    x_px=_finite(
                        landmark.get("x_px"),
                        f"estimate.landmarks[{index}].x_px",
                        minimum=0.0,
                        maximum=float(width_px) - 1e-9,
                    ),
                    y_px=_finite(
                        landmark.get("y_px"),
                        f"estimate.landmarks[{index}].y_px",
                        minimum=0.0,
                        maximum=float(height_px) - 1e-9,
                    ),
                    role=landmark.get("role"),
                )
            )
        except (TypeError, ValueError) as exc:
            raise FixedCameraBareJawLandmarkEvidenceError(
                f"estimate.landmarks[{index}] is invalid: {exc}"
            ) from exc

    authority = _mapping(raw.get("authority"), "authority")
    _exact(authority, _AUTHORITY_FIELDS, "authority")
    for name in (
        "camera_opened",
        "robot_provider_called",
        "motion_targets_emitted",
        "motion_authorized",
        "contact_authorized",
    ):
        _false(authority.get(name), f"authority.{name}")
    if authority.get("physical_release_effect") != "NONE":
        raise FixedCameraBareJawLandmarkEvidenceError(
            "authority.physical_release_effect must be 'NONE'"
        )

    integrity_sha256 = _digest(raw.get("integrity_sha256"), "integrity_sha256")
    meaning = dict(raw)
    meaning.pop("integrity_sha256")
    if integrity_sha256 != _hash(meaning):
        raise FixedCameraBareJawLandmarkEvidenceError(
            "integrity_sha256 does not match the record meaning"
        )

    pose_estimate = BareJawLandmarkPoseEstimateV1(
        frame_sha256=frame_sha256,
        camera_T_reference=transform,
        landmarks=tuple(pixel_landmarks),
        uncertainty_mm=uncertainty_mm,
    )
    pose_source = RetainedBareJawLandmarkPoseSourceV1(
        detector_id=detector_id,
        detector_version=detector_version,
        configuration_sha256=configuration_sha256,
        implementation_sha256=implementation_sha256,
        capture_id=capture_id,
        frame_sha256=frame_sha256,
        settings_sha256=settings_sha256,
        width_px=width_px,
        height_px=height_px,
        camera_frame=camera_frame,
        pixel_space=pixel_space,
        intrinsics_sha256=intrinsics_sha256,
        reference_model_sha256=reference_model_sha256,
        estimate_value=pose_estimate,
    )
    return RetainedBareJawLandmarkEvidenceV1(
        source_path=source_path,
        source_file_sha256=source_file_sha256,
        canonical_sha256=_hash(raw),
        integrity_sha256=integrity_sha256,
        model=model,
        pose_source=pose_source,
    )


def load_retained_bare_jaw_landmark_evidence_v1(
    path: str | Path, *, expected_file_sha256: str
) -> RetainedBareJawLandmarkEvidenceV1:
    """Load one exact caller-pinned retained landmark evidence package."""

    expected = _digest(expected_file_sha256, "expected_file_sha256")
    source_path = Path(path).resolve()
    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"cannot read bare-jaw landmark evidence: {exc}"
        ) from exc
    if not payload or len(payload) > MAX_RECORD_BYTES:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"bare-jaw landmark evidence must be 1..{MAX_RECORD_BYTES} bytes"
        )
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise FixedCameraBareJawLandmarkEvidenceError(
            "bare-jaw landmark evidence bytes differ from expected_file_sha256"
        )
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraBareJawLandmarkEvidenceError(
            f"bare-jaw landmark evidence is not strict JSON: {exc}"
        ) from exc
    return parse_retained_bare_jaw_landmark_evidence_v1(
        _mapping(raw, "record"),
        source_path=source_path,
        source_file_sha256=actual,
    )


__all__ = [
    "FixedCameraBareJawLandmarkEvidenceError",
    "MAX_RECORD_BYTES",
    "RetainedBareJawLandmarkEvidenceV1",
    "RetainedBareJawLandmarkPoseSourceV1",
    "SCHEMA",
    "STATUS",
    "load_retained_bare_jaw_landmark_evidence_v1",
    "parse_retained_bare_jaw_landmark_evidence_v1",
]
