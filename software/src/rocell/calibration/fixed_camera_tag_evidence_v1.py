"""Strict retained-file replay for fixed-camera six-tag evidence.

The native fixed-camera observation coordinator accepts a frame detector and a
reviewed rectifier as narrow in-memory protocols.  This module supplies those
protocols from one exact, caller-pinned JSON artifact.  It performs no camera
or robot I/O and cannot create physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.vision.camera import FramePacket
from rocell.vision.detections import (
    AprilTagDetectionBatch,
    VisionRecordError,
    april_tag_detection_batch_from_dict,
)


SCHEMA = "rocell.retained_fixed_camera_tag_evidence.v1"
STATUS = "RETAINED_FIXED_CAMERA_TAG_EVIDENCE"
DESTINATION_PIXEL_SPACE = "UNDISTORTED_PINHOLE_PIXELS"
MAX_RECORD_BYTES = 1024 * 1024

_ROOT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "pixel_spaces",
        "rectification",
        "raw_detection_batch",
        "rectified_detection_batch",
        "authority",
        "integrity_sha256",
    }
)
_PIXEL_SPACE_FIELDS = frozenset({"source", "destination"})
_RECTIFICATION_FIELDS = frozenset(
    {"configuration_sha256", "implementation_sha256"}
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


class FixedCameraTagEvidenceError(ValueError):
    """Retained tag evidence is malformed, crossed, or unpinned."""


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
        raise FixedCameraTagEvidenceError(
            "fixed-camera tag evidence is not canonical JSON"
        ) from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _reject_constant(value: str) -> None:
    raise FixedCameraTagEvidenceError(
        f"fixed-camera tag evidence contains nonfinite constant {value!r}"
    )


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraTagEvidenceError(
                f"fixed-camera tag evidence contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixedCameraTagEvidenceError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise FixedCameraTagEvidenceError(
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
        raise FixedCameraTagEvidenceError(
            f"{label} must be non-empty bounded trimmed text"
        )
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraTagEvidenceError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _false(value: object, label: str) -> None:
    if value is not False:
        raise FixedCameraTagEvidenceError(f"{label} must be False")


def _detection_signature(batch: AprilTagDetectionBatch) -> tuple[object, ...]:
    """Return all detector facts that rectification is forbidden to change."""

    return tuple(
        (
            detection.tag,
            detection.decision_margin,
            detection.hamming,
            detection.rejection_reason,
        )
        for detection in batch.detections
    )


@dataclass(frozen=True, slots=True)
class RetainedFixedCameraTagEvidenceV1:
    """Exact detector and rectifier replay for one immutable frame."""

    source_path: Path
    source_file_sha256: str
    canonical_sha256: str
    integrity_sha256: str
    source_pixel_space: str
    destination_pixel_space: str
    configuration_sha256: str
    rectifier_implementation_sha256: str
    raw_batch: AprilTagDetectionBatch
    rectified_batch: AprilTagDetectionBatch

    def detect(self, frame: FramePacket) -> AprilTagDetectionBatch:
        """Replay raw detections only for the exact retained frame."""

        if not isinstance(frame, FramePacket):
            raise TypeError("frame must be FramePacket")
        try:
            self.raw_batch.frame.assert_matches(
                frame, host_clock=self.raw_batch.frame.host_clock
            )
        except VisionRecordError as exc:
            raise FixedCameraTagEvidenceError(
                "retained tag evidence cannot replay against a different frame"
            ) from exc
        return self.raw_batch

    def rectify_detection_batch(
        self, batch: AprilTagDetectionBatch
    ) -> AprilTagDetectionBatch:
        """Replay rectified corners only for the exact retained raw batch."""

        if not isinstance(batch, AprilTagDetectionBatch):
            raise TypeError("batch must be AprilTagDetectionBatch")
        if batch.content_hash != self.raw_batch.content_hash:
            raise FixedCameraTagEvidenceError(
                "rectifier input differs from the retained raw detection batch"
            )
        return self.rectified_batch

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "rocell.retained_fixed_camera_tag_evidence_receipt.v1",
            "status": "RETAINED_FIXED_CAMERA_TAG_EVIDENCE_ACCEPTED",
            "source_path": str(self.source_path),
            "source_file_sha256": self.source_file_sha256,
            "canonical_sha256": self.canonical_sha256,
            "integrity_sha256": self.integrity_sha256,
            "capture_id": self.raw_batch.frame.capture_id,
            "frame_sha256": self.raw_batch.frame.jpeg_sha256,
            "raw_detection_batch_sha256": self.raw_batch.content_hash,
            "rectified_detection_batch_sha256": self.rectified_batch.content_hash,
            "rectification_configuration_sha256": self.configuration_sha256,
            "rectifier_implementation_sha256": (
                self.rectifier_implementation_sha256
            ),
            "source_pixel_space": self.source_pixel_space,
            "destination_pixel_space": self.destination_pixel_space,
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }


def parse_retained_fixed_camera_tag_evidence_v1(
    value: Mapping[str, Any],
    *,
    source_path: Path,
    source_file_sha256: str,
) -> RetainedFixedCameraTagEvidenceV1:
    """Parse one already byte-pinned retained tag evidence record."""

    raw = _mapping(value, "record")
    _exact(raw, _ROOT_FIELDS, "record")
    if raw.get("schema") != SCHEMA or raw.get("status") != STATUS:
        raise FixedCameraTagEvidenceError(
            "fixed-camera tag evidence schema or status is invalid"
        )

    pixel_spaces = _mapping(raw.get("pixel_spaces"), "pixel_spaces")
    _exact(pixel_spaces, _PIXEL_SPACE_FIELDS, "pixel_spaces")
    source_pixel_space = _text(pixel_spaces.get("source"), "pixel_spaces.source")
    destination_pixel_space = _text(
        pixel_spaces.get("destination"), "pixel_spaces.destination"
    )
    if source_pixel_space == destination_pixel_space:
        raise FixedCameraTagEvidenceError(
            "source and destination pixel spaces must differ"
        )
    if destination_pixel_space != DESTINATION_PIXEL_SPACE:
        raise FixedCameraTagEvidenceError(
            "destination pixel space must be UNDISTORTED_PINHOLE_PIXELS"
        )

    rectification = _mapping(raw.get("rectification"), "rectification")
    _exact(rectification, _RECTIFICATION_FIELDS, "rectification")
    configuration_sha256 = _digest(
        rectification.get("configuration_sha256"),
        "rectification.configuration_sha256",
    )
    implementation_sha256 = _digest(
        rectification.get("implementation_sha256"),
        "rectification.implementation_sha256",
    )

    try:
        raw_batch = april_tag_detection_batch_from_dict(
            raw.get("raw_detection_batch")
        )
        rectified_batch = april_tag_detection_batch_from_dict(
            raw.get("rectified_detection_batch")
        )
    except (TypeError, ValueError, VisionRecordError) as exc:
        raise FixedCameraTagEvidenceError(
            f"retained detection batch is invalid: {exc}"
        ) from exc
    if raw_batch.frame != rectified_batch.frame:
        raise FixedCameraTagEvidenceError(
            "raw and rectified detections bind different frames"
        )
    if _detection_signature(raw_batch) != _detection_signature(rectified_batch):
        raise FixedCameraTagEvidenceError(
            "rectification changed tag identity, decision, margin, or hamming evidence"
        )
    if raw_batch.detector == rectified_batch.detector:
        raise FixedCameraTagEvidenceError(
            "rectified detections must carry a distinct processing identity"
        )
    if rectified_batch.detector.implementation_sha256 != implementation_sha256:
        raise FixedCameraTagEvidenceError(
            "rectified detector implementation differs from rectification evidence"
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
        _false(authority.get(name), f"authority.{name}")
    if authority.get("physical_release_effect") != "NONE":
        raise FixedCameraTagEvidenceError(
            "authority.physical_release_effect must be 'NONE'"
        )

    integrity_sha256 = _digest(raw.get("integrity_sha256"), "integrity_sha256")
    meaning = dict(raw)
    meaning.pop("integrity_sha256")
    if integrity_sha256 != _hash(meaning):
        raise FixedCameraTagEvidenceError(
            "integrity_sha256 does not match the record meaning"
        )

    return RetainedFixedCameraTagEvidenceV1(
        source_path=source_path,
        source_file_sha256=_digest(
            source_file_sha256, "source_file_sha256"
        ),
        canonical_sha256=_hash(raw),
        integrity_sha256=integrity_sha256,
        source_pixel_space=source_pixel_space,
        destination_pixel_space=destination_pixel_space,
        configuration_sha256=configuration_sha256,
        rectifier_implementation_sha256=implementation_sha256,
        raw_batch=raw_batch,
        rectified_batch=rectified_batch,
    )


def load_retained_fixed_camera_tag_evidence_v1(
    path: str | Path, *, expected_file_sha256: str
) -> RetainedFixedCameraTagEvidenceV1:
    """Load one exact caller-pinned retained tag evidence package."""

    expected = _digest(expected_file_sha256, "expected_file_sha256")
    source_path = Path(path).resolve()
    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        raise FixedCameraTagEvidenceError(
            f"cannot read fixed-camera tag evidence: {exc}"
        ) from exc
    if not payload or len(payload) > MAX_RECORD_BYTES:
        raise FixedCameraTagEvidenceError(
            f"fixed-camera tag evidence must be 1..{MAX_RECORD_BYTES} bytes"
        )
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise FixedCameraTagEvidenceError(
            "fixed-camera tag evidence bytes differ from expected_file_sha256"
        )
    try:
        decoded = payload.decode("utf-8", errors="strict")
        raw = json.loads(
            decoded,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraTagEvidenceError(
            f"fixed-camera tag evidence is not strict JSON: {exc}"
        ) from exc
    return parse_retained_fixed_camera_tag_evidence_v1(
        _mapping(raw, "record"),
        source_path=source_path,
        source_file_sha256=actual,
    )


__all__ = [
    "DESTINATION_PIXEL_SPACE",
    "FixedCameraTagEvidenceError",
    "MAX_RECORD_BYTES",
    "RetainedFixedCameraTagEvidenceV1",
    "SCHEMA",
    "STATUS",
    "load_retained_fixed_camera_tag_evidence_v1",
    "parse_retained_fixed_camera_tag_evidence_v1",
]
