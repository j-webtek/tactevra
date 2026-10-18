"""Strict retained-file replay for one fixed-camera acquisition bracket.

The live acquisition coordinator intentionally returns an in-memory frame and
stationary feedback bracket.  This module restores that exact typed object from
one caller-pinned JSON record and one separately pinned JPEG.  It performs
bounded file reads only and delegates timing, stationarity, and firmware
kinematic checks to the same validator used by live acquisition.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.vision.camera import CameraError, FramePacket, TimestampQuality

from .fixed_camera_robot_acquisition_v1 import (
    CalibrationCaptureBracketV1,
    FixedCameraRobotAcquisitionError,
    RetainedFeedbackSampleV1,
    validate_calibration_bracket_v1,
)


SCHEMA = "rocell.retained_fixed_camera_acquisition_bracket.v1"
STATUS = "RETAINED_READ_ONLY_STATIONARY_BRACKET"
MAX_RECORD_BYTES = 512 * 1024
MAX_JPEG_BYTES = 64 * 1024 * 1024

_ROOT_FIELDS = frozenset(
    {"schema", "status", "jpeg_binding", "bracket", "authority", "integrity_sha256"}
)
_JPEG_FIELDS = frozenset({"jpeg_sha256", "byte_count"})
_BRACKET_FIELDS = frozenset(
    {
        "permit_sha256",
        "installation_epoch_id",
        "camera_identity_sha256",
        "frame",
        "robot_feedback",
        "quality",
    }
)
_FRAME_FIELDS = frozenset(
    {
        "capture_id",
        "width_px",
        "height_px",
        "source_sequence",
        "source_timestamp_ns",
        "source_clock",
        "host_request_ns",
        "host_first_byte_ns",
        "host_complete_ns",
        "settings_sha256",
        "timestamp_quality",
        "freshness_token",
        "freshness_basis",
    }
)
_FEEDBACK_FIELDS = frozenset(
    {
        "robot_base_identity",
        "clock_id",
        "pre_timestamp_ns",
        "post_timestamp_ns",
        "pre_feedback_line",
        "post_feedback_line",
    }
)
_QUALITY_FIELDS = frozenset(
    {
        "feedback_bracket_ns",
        "maximum_joint_span_rad",
        "endpoint_span_mm",
        "maximum_reported_fk_error_mm",
    }
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


class FixedCameraBracketEvidenceError(ValueError):
    """Retained bracket evidence is malformed, crossed, or unpinned."""


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
        raise FixedCameraBracketEvidenceError(
            "retained bracket record is not canonical JSON"
        ) from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _reject_constant(value: str) -> None:
    raise FixedCameraBracketEvidenceError(
        f"retained bracket record contains nonfinite constant {value!r}"
    )


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraBracketEvidenceError(
                f"retained bracket record contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixedCameraBracketEvidenceError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise FixedCameraBracketEvidenceError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _text(value: object, label: str, *, maximum: int = 1024) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise FixedCameraBracketEvidenceError(
            f"{label} must be non-empty bounded trimmed text"
        )
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraBracketEvidenceError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FixedCameraBracketEvidenceError(
            f"{label} must be an integer >= {minimum}"
        )
    return value


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraBracketEvidenceError(f"{label} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise FixedCameraBracketEvidenceError(f"{label} must be finite and nonnegative")
    return parsed


def _feedback_line(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 65536:
        raise FixedCameraBracketEvidenceError(
            f"{label} must be non-empty UTF-8 text within 65536 bytes"
        )
    return value


def _false(value: object, label: str) -> None:
    if type(value) is not bool or value is not False:
        raise FixedCameraBracketEvidenceError(f"{label} must be False")


@dataclass(frozen=True, slots=True)
class RetainedFixedCameraBracketEvidenceV1:
    """Validated retained files and their shared-policy bracket object."""

    record_path: Path
    record_file_sha256: str
    jpeg_path: Path
    jpeg_file_sha256: str
    canonical_sha256: str
    integrity_sha256: str
    bracket: CalibrationCaptureBracketV1

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "rocell.retained_fixed_camera_acquisition_bracket_receipt.v1",
            "status": "RETAINED_STATIONARY_BRACKET_ACCEPTED",
            "record_file_sha256": self.record_file_sha256,
            "jpeg_file_sha256": self.jpeg_file_sha256,
            "canonical_sha256": self.canonical_sha256,
            "integrity_sha256": self.integrity_sha256,
            "bracket_sha256": self.bracket.sha256,
            "capture_id": self.bracket.frame.capture_id,
            "installation_epoch_id": self.bracket.installation_epoch_id,
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }


def parse_retained_fixed_camera_bracket_evidence_v1(
    raw: Mapping[str, Any],
    *,
    record_path: Path,
    record_file_sha256: str,
    jpeg_path: Path,
    jpeg_bytes: bytes,
    jpeg_file_sha256: str,
) -> RetainedFixedCameraBracketEvidenceV1:
    """Validate parsed record meaning and reconstruct the typed bracket."""

    _exact(raw, _ROOT_FIELDS, "record")
    if raw.get("schema") != SCHEMA:
        raise FixedCameraBracketEvidenceError(f"schema must be {SCHEMA!r}")
    if raw.get("status") != STATUS:
        raise FixedCameraBracketEvidenceError(f"status must be {STATUS!r}")

    jpeg = _mapping(raw.get("jpeg_binding"), "jpeg_binding")
    _exact(jpeg, _JPEG_FIELDS, "jpeg_binding")
    declared_jpeg_sha = _digest(jpeg.get("jpeg_sha256"), "jpeg_binding.jpeg_sha256")
    declared_byte_count = _integer(
        jpeg.get("byte_count"), "jpeg_binding.byte_count", minimum=1
    )
    if declared_jpeg_sha != jpeg_file_sha256:
        raise FixedCameraBracketEvidenceError(
            "retained JPEG bytes differ from jpeg_binding.jpeg_sha256"
        )
    if declared_byte_count != len(jpeg_bytes):
        raise FixedCameraBracketEvidenceError(
            "retained JPEG byte count differs from jpeg_binding.byte_count"
        )

    bracket_raw = _mapping(raw.get("bracket"), "bracket")
    _exact(bracket_raw, _BRACKET_FIELDS, "bracket")
    permit_sha256 = _digest(bracket_raw.get("permit_sha256"), "bracket.permit_sha256")
    installation_epoch_id = _text(
        bracket_raw.get("installation_epoch_id"), "bracket.installation_epoch_id"
    )
    camera_identity_sha256 = _digest(
        bracket_raw.get("camera_identity_sha256"),
        "bracket.camera_identity_sha256",
    )

    frame_raw = _mapping(bracket_raw.get("frame"), "bracket.frame")
    _exact(frame_raw, _FRAME_FIELDS, "bracket.frame")
    try:
        timestamp_quality = TimestampQuality(frame_raw.get("timestamp_quality"))
    except (TypeError, ValueError) as exc:
        raise FixedCameraBracketEvidenceError(
            "bracket.frame.timestamp_quality is invalid"
        ) from exc
    try:
        frame = FramePacket(
            capture_id=_text(frame_raw.get("capture_id"), "bracket.frame.capture_id"),
            jpeg_bytes=jpeg_bytes,
            width_px=_integer(
                frame_raw.get("width_px"), "bracket.frame.width_px", minimum=1
            ),
            height_px=_integer(
                frame_raw.get("height_px"), "bracket.frame.height_px", minimum=1
            ),
            source_sequence=_optional_integer(
                frame_raw.get("source_sequence"), "bracket.frame.source_sequence"
            ),
            source_timestamp_ns=_optional_integer(
                frame_raw.get("source_timestamp_ns"),
                "bracket.frame.source_timestamp_ns",
            ),
            source_clock=_optional_text(
                frame_raw.get("source_clock"), "bracket.frame.source_clock"
            ),
            host_request_ns=_integer(
                frame_raw.get("host_request_ns"), "bracket.frame.host_request_ns"
            ),
            host_first_byte_ns=_integer(
                frame_raw.get("host_first_byte_ns"),
                "bracket.frame.host_first_byte_ns",
            ),
            host_complete_ns=_integer(
                frame_raw.get("host_complete_ns"), "bracket.frame.host_complete_ns"
            ),
            settings_hash=_digest(
                frame_raw.get("settings_sha256"), "bracket.frame.settings_sha256"
            ),
            timestamp_quality=timestamp_quality,
            freshness_token=_optional_text(
                frame_raw.get("freshness_token"), "bracket.frame.freshness_token"
            ),
            freshness_basis=_text(
                frame_raw.get("freshness_basis"), "bracket.frame.freshness_basis"
            ),
        )
    except (TypeError, ValueError, CameraError) as exc:
        raise FixedCameraBracketEvidenceError(
            f"retained frame metadata or JPEG is invalid: {exc}"
        ) from exc

    feedback_raw = _mapping(bracket_raw.get("robot_feedback"), "bracket.robot_feedback")
    _exact(feedback_raw, _FEEDBACK_FIELDS, "bracket.robot_feedback")
    robot_base_identity = _text(
        feedback_raw.get("robot_base_identity"),
        "bracket.robot_feedback.robot_base_identity",
    )
    clock_id = _text(feedback_raw.get("clock_id"), "bracket.robot_feedback.clock_id")
    pre_timestamp_ns = _integer(
        feedback_raw.get("pre_timestamp_ns"),
        "bracket.robot_feedback.pre_timestamp_ns",
    )
    post_timestamp_ns = _integer(
        feedback_raw.get("post_timestamp_ns"),
        "bracket.robot_feedback.post_timestamp_ns",
    )
    try:
        pre = RetainedFeedbackSampleV1(
            _feedback_line(
                feedback_raw.get("pre_feedback_line"),
                "bracket.robot_feedback.pre_feedback_line",
            ),
            pre_timestamp_ns,
            clock_id,
            robot_base_identity,
        )
        post = RetainedFeedbackSampleV1(
            _feedback_line(
                feedback_raw.get("post_feedback_line"),
                "bracket.robot_feedback.post_feedback_line",
            ),
            post_timestamp_ns,
            clock_id,
            robot_base_identity,
        )
    except (TypeError, ValueError, FixedCameraRobotAcquisitionError) as exc:
        raise FixedCameraBracketEvidenceError(
            f"retained feedback is invalid: {exc}"
        ) from exc

    quality = _mapping(bracket_raw.get("quality"), "bracket.quality")
    _exact(quality, _QUALITY_FIELDS, "bracket.quality")
    feedback_bracket_ns = _integer(
        quality.get("feedback_bracket_ns"), "bracket.quality.feedback_bracket_ns"
    )
    if feedback_bracket_ns != post_timestamp_ns - pre_timestamp_ns:
        raise FixedCameraBracketEvidenceError(
            "retained feedback bracket duration differs from timestamps"
        )
    bracket = CalibrationCaptureBracketV1(
        permit_sha256=permit_sha256,
        installation_epoch_id=installation_epoch_id,
        frame=frame,
        camera_identity_sha256=camera_identity_sha256,
        pre_feedback=pre,
        post_feedback=post,
        maximum_joint_span_rad=_finite(
            quality.get("maximum_joint_span_rad"),
            "bracket.quality.maximum_joint_span_rad",
        ),
        endpoint_span_mm=_finite(
            quality.get("endpoint_span_mm"), "bracket.quality.endpoint_span_mm"
        ),
        maximum_reported_fk_error_mm=_finite(
            quality.get("maximum_reported_fk_error_mm"),
            "bracket.quality.maximum_reported_fk_error_mm",
        ),
    )
    try:
        validate_calibration_bracket_v1(bracket)
    except (TypeError, FixedCameraRobotAcquisitionError) as exc:
        raise FixedCameraBracketEvidenceError(
            f"retained bracket fails shared acquisition policy: {exc}"
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
        raise FixedCameraBracketEvidenceError(
            "authority.physical_release_effect must be 'NONE'"
        )

    integrity_sha256 = _digest(raw.get("integrity_sha256"), "integrity_sha256")
    meaning = dict(raw)
    meaning.pop("integrity_sha256")
    if integrity_sha256 != _hash(meaning):
        raise FixedCameraBracketEvidenceError(
            "integrity_sha256 does not match the record meaning"
        )
    return RetainedFixedCameraBracketEvidenceV1(
        record_path=record_path,
        record_file_sha256=_digest(record_file_sha256, "record_file_sha256"),
        jpeg_path=jpeg_path,
        jpeg_file_sha256=jpeg_file_sha256,
        canonical_sha256=_hash(raw),
        integrity_sha256=integrity_sha256,
        bracket=bracket,
    )


def load_retained_fixed_camera_bracket_evidence_v1(
    record_path: str | Path,
    jpeg_path: str | Path,
    *,
    expected_record_file_sha256: str,
    expected_jpeg_file_sha256: str,
) -> RetainedFixedCameraBracketEvidenceV1:
    """Load one exact caller-pinned bracket record and its exact JPEG."""

    expected_record = _digest(
        expected_record_file_sha256, "expected_record_file_sha256"
    )
    expected_jpeg = _digest(expected_jpeg_file_sha256, "expected_jpeg_file_sha256")
    resolved_record = Path(record_path).resolve()
    resolved_jpeg = Path(jpeg_path).resolve()
    try:
        record_bytes = resolved_record.read_bytes()
        jpeg_bytes = resolved_jpeg.read_bytes()
    except OSError as exc:
        raise FixedCameraBracketEvidenceError(
            f"cannot read retained bracket evidence: {exc}"
        ) from exc
    if not record_bytes or len(record_bytes) > MAX_RECORD_BYTES:
        raise FixedCameraBracketEvidenceError(
            f"retained bracket record must be 1..{MAX_RECORD_BYTES} bytes"
        )
    if not jpeg_bytes or len(jpeg_bytes) > MAX_JPEG_BYTES:
        raise FixedCameraBracketEvidenceError(
            f"retained JPEG must be 1..{MAX_JPEG_BYTES} bytes"
        )
    actual_record = hashlib.sha256(record_bytes).hexdigest()
    actual_jpeg = hashlib.sha256(jpeg_bytes).hexdigest()
    if actual_record != expected_record:
        raise FixedCameraBracketEvidenceError(
            "retained bracket record bytes differ from expected_record_file_sha256"
        )
    if actual_jpeg != expected_jpeg:
        raise FixedCameraBracketEvidenceError(
            "retained JPEG bytes differ from expected_jpeg_file_sha256"
        )
    try:
        decoded = record_bytes.decode("utf-8", errors="strict")
        raw = json.loads(
            decoded,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraBracketEvidenceError(
            f"retained bracket evidence is not strict JSON: {exc}"
        ) from exc
    return parse_retained_fixed_camera_bracket_evidence_v1(
        _mapping(raw, "record"),
        record_path=resolved_record,
        record_file_sha256=actual_record,
        jpeg_path=resolved_jpeg,
        jpeg_bytes=jpeg_bytes,
        jpeg_file_sha256=actual_jpeg,
    )


__all__ = [
    "FixedCameraBracketEvidenceError",
    "MAX_JPEG_BYTES",
    "MAX_RECORD_BYTES",
    "RetainedFixedCameraBracketEvidenceV1",
    "SCHEMA",
    "STATUS",
    "load_retained_fixed_camera_bracket_evidence_v1",
    "parse_retained_fixed_camera_bracket_evidence_v1",
]
