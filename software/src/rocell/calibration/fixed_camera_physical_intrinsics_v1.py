"""Strict retained-file intake for reviewed B0477 physical intrinsics.

The native-frame observation coordinator intentionally accepts only a typed
``ReviewedNativeIntrinsicsV1``.  This module supplies the file boundary that
precedes it.  It validates one content-addressed physical calibration record,
checks its internal integrity digest and review decision, reconstructs the
undistorted pinhole intrinsics, and emits the existing coordinator binding.

The loader performs filesystem reads only.  It opens no camera or robot,
requests no frame or feedback, and grants no motion or contact authority.
Reviewer identity remains an external trust decision; this module binds the
declared review record but cannot authenticate the human reviewer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.vision.planar_pose_estimator import PinholeIntrinsics

from .fixed_camera_calibration_observation_v1 import (
    NATIVE_HEIGHT_PX,
    NATIVE_WIDTH_PX,
    REVIEW_STATUS,
    ReviewedNativeIntrinsicsV1,
)


SCHEMA = "rocell.reviewed_native_fixed_camera_intrinsics_record.v1"
MAX_RECORD_BYTES = 512 * 1024
DISTORTION_MODEL = "OPENCV_RATIONAL_POLYNOMIAL_8"
PIXEL_SPACE = "UNDISTORTED_PINHOLE_PIXELS"
CAMERA_FRAME = "b0477_camera_optical"
NATIVE_FPS = 9.0
NATIVE_PIXEL_FORMAT = "YUY2"

_ROOT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "calibration_record_id",
        "camera_binding",
        "solution",
        "board_binding",
        "physical_validation",
        "independent_review",
        "authority",
        "integrity_sha256",
    }
)
_CAMERA_FIELDS = frozenset(
    {
        "persistent_camera_identity_sha256",
        "settings_sha256",
        "mode",
        "native_mode_verified",
        "full_frame_without_crop_or_rescale",
    }
)
_MODE_FIELDS = frozenset({"width_px", "height_px", "fps", "pixel_format"})
_SOLUTION_FIELDS = frozenset(
    {
        "calibration_id",
        "calibration_producer_id",
        "source_artifact_sha256",
        "camera_frame",
        "pixel_space",
        "distortion_model",
        "distortion_coefficients",
        "rectified_camera_matrix_row_major",
        "rectification_configuration_sha256",
    }
)
_BOARD_FIELDS = frozenset({"tag_map_sha256"})
_VALIDATION_FIELDS = frozenset(
    {
        "physical_calibration_valid",
        "dataset_manifest_sha256",
        "split_commitment_sha256",
        "training_view_count",
        "held_out_view_count",
        "metrics_px",
        "acceptance_limits_px",
    }
)
_METRIC_FIELDS = frozenset(
    {
        "training_rms",
        "held_out_rms",
        "held_out_p95",
        "maximum_view_rms",
    }
)
_REVIEW_FIELDS = frozenset(
    {"decision", "reviewer_id", "reviewed_at", "review_record_sha256"}
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


class FixedCameraPhysicalIntrinsicsError(ValueError):
    """A retained physical intrinsics record is malformed or inconsistent."""


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
        raise FixedCameraPhysicalIntrinsicsError(
            "physical intrinsics record is not canonical JSON"
        ) from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _reject_constant(value: str) -> None:
    raise FixedCameraPhysicalIntrinsicsError(
        f"physical intrinsics record contains nonfinite constant {value!r}"
    )


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraPhysicalIntrinsicsError(
                f"physical intrinsics record contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixedCameraPhysicalIntrinsicsError(f"{label} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise FixedCameraPhysicalIntrinsicsError(
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
        raise FixedCameraPhysicalIntrinsicsError(
            f"{label} must be non-empty bounded trimmed text"
        )
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraPhysicalIntrinsicsError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _boolean(value: object, expected: bool, label: str) -> bool:
    if type(value) is not bool or value is not expected:
        raise FixedCameraPhysicalIntrinsicsError(f"{label} must be {expected}")
    return expected


def _integer(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FixedCameraPhysicalIntrinsicsError(
            f"{label} must be an integer >= {minimum}"
        )
    return value


def _finite(
    value: object,
    label: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraPhysicalIntrinsicsError(f"{label} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise FixedCameraPhysicalIntrinsicsError(
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
        raise FixedCameraPhysicalIntrinsicsError(
            f"{label} must contain exactly {length} values"
        )
    return tuple(
        _finite(item, f"{label}[{index}]", minimum=minimum, maximum=maximum)
        for index, item in enumerate(value)
    )


def _review_time(value: object) -> str:
    text = _text(value, "independent_review.reviewed_at", maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixedCameraPhysicalIntrinsicsError(
            "independent_review.reviewed_at must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixedCameraPhysicalIntrinsicsError(
            "independent_review.reviewed_at must include a UTC offset"
        )
    return text


def _metric_mapping(value: object, label: str) -> dict[str, float]:
    raw = _mapping(value, label)
    _exact_fields(raw, _METRIC_FIELDS, label)
    return {
        name: _finite(raw.get(name), f"{label}.{name}", minimum=0.0, maximum=1000.0)
        for name in sorted(_METRIC_FIELDS)
    }


@dataclass(frozen=True, slots=True)
class PhysicalNativeIntrinsicsRecordV1:
    """Validated retained record and its coordinator-ready binding."""

    source_path: Path
    source_file_sha256: str
    canonical_sha256: str
    integrity_sha256: str
    calibration_record_id: str
    calibration_producer_id: str
    persistent_camera_identity_sha256: str
    settings_sha256: str
    intrinsics: PinholeIntrinsics
    distortion_coefficients: tuple[float, ...]
    rectification_configuration_sha256: str
    tag_map_sha256: str
    dataset_manifest_sha256: str
    split_commitment_sha256: str
    training_view_count: int
    held_out_view_count: int
    metrics_px: tuple[tuple[str, float], ...]
    acceptance_limits_px: tuple[tuple[str, float], ...]
    reviewer_id: str
    reviewed_at: str
    review_record_sha256: str

    def to_reviewed_binding(self) -> ReviewedNativeIntrinsicsV1:
        """Return the exact typed input consumed by the observation coordinator."""

        return ReviewedNativeIntrinsicsV1(
            calibration_record_id=self.calibration_record_id,
            camera_identity_sha256=self.persistent_camera_identity_sha256,
            settings_sha256=self.settings_sha256,
            intrinsics=self.intrinsics,
            tag_map_sha256=self.tag_map_sha256,
            distortion_model=DISTORTION_MODEL,
            rectification_configuration_sha256=(
                self.rectification_configuration_sha256
            ),
            review_record_sha256=self.review_record_sha256,
            physical_calibration_valid=True,
            native_mode_verified=True,
            full_frame_without_crop_or_rescale=True,
        )

    def receipt(self) -> dict[str, object]:
        """Emit a compact zero-authority validation receipt."""

        return {
            "schema": "rocell.reviewed_native_fixed_camera_intrinsics_receipt.v1",
            "status": "REVIEWED_PHYSICAL_INTRINSICS_RECORD_ACCEPTED",
            "source_file_sha256": self.source_file_sha256,
            "canonical_sha256": self.canonical_sha256,
            "integrity_sha256": self.integrity_sha256,
            "reviewed_binding_sha256": self.to_reviewed_binding().sha256,
            "calibration_record_id": self.calibration_record_id,
            "calibration_producer_id": self.calibration_producer_id,
            "training_view_count": self.training_view_count,
            "held_out_view_count": self.held_out_view_count,
            "review_record_sha256": self.review_record_sha256,
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


def parse_reviewed_native_intrinsics_record_v1(
    raw: Mapping[str, Any],
    *,
    source_path: Path,
    source_file_sha256: str,
) -> PhysicalNativeIntrinsicsRecordV1:
    """Validate parsed JSON meaning and construct the retained record."""

    _exact_fields(raw, _ROOT_FIELDS, "record")
    if raw.get("schema") != SCHEMA:
        raise FixedCameraPhysicalIntrinsicsError(f"schema must be {SCHEMA!r}")
    if raw.get("status") != REVIEW_STATUS:
        raise FixedCameraPhysicalIntrinsicsError(f"status must be {REVIEW_STATUS!r}")
    calibration_record_id = _text(
        raw.get("calibration_record_id"), "calibration_record_id"
    )

    camera = _mapping(raw.get("camera_binding"), "camera_binding")
    _exact_fields(camera, _CAMERA_FIELDS, "camera_binding")
    camera_identity = _digest(
        camera.get("persistent_camera_identity_sha256"),
        "camera_binding.persistent_camera_identity_sha256",
    )
    settings_sha256 = _digest(
        camera.get("settings_sha256"), "camera_binding.settings_sha256"
    )
    mode = _mapping(camera.get("mode"), "camera_binding.mode")
    _exact_fields(mode, _MODE_FIELDS, "camera_binding.mode")
    expected_mode = {
        "width_px": NATIVE_WIDTH_PX,
        "height_px": NATIVE_HEIGHT_PX,
        "fps": NATIVE_FPS,
        "pixel_format": NATIVE_PIXEL_FORMAT,
    }
    for name, expected in expected_mode.items():
        if type(mode.get(name)) is not type(expected) or mode.get(name) != expected:
            raise FixedCameraPhysicalIntrinsicsError(
                f"camera_binding.mode.{name} must be {expected!r}"
            )
    _boolean(
        camera.get("native_mode_verified"),
        True,
        "camera_binding.native_mode_verified",
    )
    _boolean(
        camera.get("full_frame_without_crop_or_rescale"),
        True,
        "camera_binding.full_frame_without_crop_or_rescale",
    )

    solution = _mapping(raw.get("solution"), "solution")
    _exact_fields(solution, _SOLUTION_FIELDS, "solution")
    calibration_id = _text(solution.get("calibration_id"), "solution.calibration_id")
    calibration_producer_id = _text(
        solution.get("calibration_producer_id"),
        "solution.calibration_producer_id",
    )
    source_artifact_sha256 = _digest(
        solution.get("source_artifact_sha256"), "solution.source_artifact_sha256"
    )
    if solution.get("camera_frame") != CAMERA_FRAME:
        raise FixedCameraPhysicalIntrinsicsError(
            f"solution.camera_frame must be {CAMERA_FRAME!r}"
        )
    if solution.get("pixel_space") != PIXEL_SPACE:
        raise FixedCameraPhysicalIntrinsicsError(
            f"solution.pixel_space must be {PIXEL_SPACE!r}"
        )
    if solution.get("distortion_model") != DISTORTION_MODEL:
        raise FixedCameraPhysicalIntrinsicsError(
            f"solution.distortion_model must be {DISTORTION_MODEL!r}"
        )
    distortion = _numeric_array(
        solution.get("distortion_coefficients"),
        "solution.distortion_coefficients",
        length=8,
        minimum=-1000.0,
        maximum=1000.0,
    )
    matrix = _numeric_array(
        solution.get("rectified_camera_matrix_row_major"),
        "solution.rectified_camera_matrix_row_major",
        length=9,
        minimum=-10_000_000.0,
        maximum=10_000_000.0,
    )
    if any(
        abs(matrix[index] - expected) > 1e-12
        for index, expected in ((3, 0.0), (6, 0.0), (7, 0.0), (8, 1.0))
    ):
        raise FixedCameraPhysicalIntrinsicsError(
            "rectified camera matrix must have canonical pinhole bottom rows"
        )
    rectification_sha256 = _digest(
        solution.get("rectification_configuration_sha256"),
        "solution.rectification_configuration_sha256",
    )
    try:
        intrinsics = PinholeIntrinsics(
            calibration_id=calibration_id,
            width_px=NATIVE_WIDTH_PX,
            height_px=NATIVE_HEIGHT_PX,
            fx_px=matrix[0],
            fy_px=matrix[4],
            cx_px=matrix[2],
            cy_px=matrix[5],
            skew_px=matrix[1],
            source_sha256=source_artifact_sha256,
            camera_frame=CAMERA_FRAME,
            pixel_space=PIXEL_SPACE,
        )
    except ValueError as exc:
        raise FixedCameraPhysicalIntrinsicsError(
            f"solution rectified pinhole intrinsics are invalid: {exc}"
        ) from exc

    board = _mapping(raw.get("board_binding"), "board_binding")
    _exact_fields(board, _BOARD_FIELDS, "board_binding")
    tag_map_sha256 = _digest(
        board.get("tag_map_sha256"), "board_binding.tag_map_sha256"
    )

    validation = _mapping(raw.get("physical_validation"), "physical_validation")
    _exact_fields(validation, _VALIDATION_FIELDS, "physical_validation")
    _boolean(
        validation.get("physical_calibration_valid"),
        True,
        "physical_validation.physical_calibration_valid",
    )
    dataset_manifest_sha256 = _digest(
        validation.get("dataset_manifest_sha256"),
        "physical_validation.dataset_manifest_sha256",
    )
    split_commitment_sha256 = _digest(
        validation.get("split_commitment_sha256"),
        "physical_validation.split_commitment_sha256",
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
    metrics = _metric_mapping(
        validation.get("metrics_px"), "physical_validation.metrics_px"
    )
    limits = _metric_mapping(
        validation.get("acceptance_limits_px"),
        "physical_validation.acceptance_limits_px",
    )
    failed = [name for name in sorted(_METRIC_FIELDS) if metrics[name] > limits[name]]
    if failed:
        raise FixedCameraPhysicalIntrinsicsError(
            f"physical validation exceeds reviewed acceptance limits: {failed}"
        )

    review = _mapping(raw.get("independent_review"), "independent_review")
    _exact_fields(review, _REVIEW_FIELDS, "independent_review")
    if review.get("decision") != "ACCEPT":
        raise FixedCameraPhysicalIntrinsicsError(
            "independent_review.decision must be 'ACCEPT'"
        )
    reviewer_id = _text(review.get("reviewer_id"), "independent_review.reviewer_id")
    if reviewer_id == calibration_producer_id:
        raise FixedCameraPhysicalIntrinsicsError(
            "independent reviewer must differ from the calibration producer"
        )
    reviewed_at = _review_time(review.get("reviewed_at"))
    review_record_sha256 = _digest(
        review.get("review_record_sha256"),
        "independent_review.review_record_sha256",
    )

    authority = _mapping(raw.get("authority"), "authority")
    _exact_fields(authority, _AUTHORITY_FIELDS, "authority")
    for name in (
        "camera_opened",
        "robot_provider_called",
        "motion_targets_emitted",
        "motion_authorized",
        "contact_authorized",
    ):
        _boolean(authority.get(name), False, f"authority.{name}")
    if authority.get("physical_release_effect") != "NONE":
        raise FixedCameraPhysicalIntrinsicsError(
            "authority.physical_release_effect must be 'NONE'"
        )

    integrity_sha256 = _digest(raw.get("integrity_sha256"), "integrity_sha256")
    meaning = dict(raw)
    meaning.pop("integrity_sha256")
    expected_integrity = _hash(meaning)
    if integrity_sha256 != expected_integrity:
        raise FixedCameraPhysicalIntrinsicsError(
            "integrity_sha256 does not match the record meaning"
        )

    return PhysicalNativeIntrinsicsRecordV1(
        source_path=source_path,
        source_file_sha256=source_file_sha256,
        canonical_sha256=_hash(raw),
        integrity_sha256=integrity_sha256,
        calibration_record_id=calibration_record_id,
        calibration_producer_id=calibration_producer_id,
        persistent_camera_identity_sha256=camera_identity,
        settings_sha256=settings_sha256,
        intrinsics=intrinsics,
        distortion_coefficients=distortion,
        rectification_configuration_sha256=rectification_sha256,
        tag_map_sha256=tag_map_sha256,
        dataset_manifest_sha256=dataset_manifest_sha256,
        split_commitment_sha256=split_commitment_sha256,
        training_view_count=training_view_count,
        held_out_view_count=held_out_view_count,
        metrics_px=tuple(sorted(metrics.items())),
        acceptance_limits_px=tuple(sorted(limits.items())),
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_record_sha256=review_record_sha256,
    )


def load_reviewed_native_intrinsics_record_v1(
    path: str | Path,
    *,
    expected_file_sha256: str,
) -> PhysicalNativeIntrinsicsRecordV1:
    """Load one exact, caller-pinned retained physical calibration record."""

    expected = _digest(expected_file_sha256, "expected_file_sha256")
    source_path = Path(path).resolve()
    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        raise FixedCameraPhysicalIntrinsicsError(
            f"cannot read physical intrinsics record: {exc}"
        ) from exc
    if not payload or len(payload) > MAX_RECORD_BYTES:
        raise FixedCameraPhysicalIntrinsicsError(
            f"physical intrinsics record must be 1..{MAX_RECORD_BYTES} bytes"
        )
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise FixedCameraPhysicalIntrinsicsError(
            "physical intrinsics record bytes differ from expected_file_sha256"
        )
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FixedCameraPhysicalIntrinsicsError(
            "physical intrinsics record must be strict UTF-8"
        ) from exc
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, FixedCameraPhysicalIntrinsicsError) as exc:
        if isinstance(exc, FixedCameraPhysicalIntrinsicsError):
            raise
        raise FixedCameraPhysicalIntrinsicsError(
            f"physical intrinsics record is not valid JSON: {exc}"
        ) from exc
    return parse_reviewed_native_intrinsics_record_v1(
        _mapping(raw, "record"),
        source_path=source_path,
        source_file_sha256=actual,
    )


__all__ = [
    "CAMERA_FRAME",
    "DISTORTION_MODEL",
    "FixedCameraPhysicalIntrinsicsError",
    "MAX_RECORD_BYTES",
    "NATIVE_FPS",
    "NATIVE_PIXEL_FORMAT",
    "PIXEL_SPACE",
    "PhysicalNativeIntrinsicsRecordV1",
    "SCHEMA",
    "load_reviewed_native_intrinsics_record_v1",
    "parse_reviewed_native_intrinsics_record_v1",
]
