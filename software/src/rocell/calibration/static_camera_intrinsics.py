"""Strict, hardware-free B0477 static-camera intrinsics rehearsal contract.

The production intrinsics artifact will need to bind the received camera,
locked optical/settings state, calibration target, input frames, held-out split,
fit, residuals, crop, and generated undistortion maps.  This module defines and
exercises that boundary before hardware exists.  It intentionally accepts only
``SYNTHETIC_REHEARSAL_ONLY`` evidence and can never assert that a physical
calibration is valid, commission a camera, authorize robot motion, or authorize
contact.

No OpenCV, camera, transport, or arm module is imported.  Parsing is bounded,
rejects duplicate keys/non-finite numbers/unknown fields, checks internal
content hashes, and verifies an integrity digest over the complete JSON meaning
apart from the digest field itself.  The numeric gates are synthetic rehearsal
thresholds, not approved physical acceptance limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.vision.camera_profile import PurchasedCameraProfile


STATIC_CAMERA_INTRINSICS_SCHEMA = "rocell.static_camera_intrinsics_rehearsal.v1"
STATIC_CAMERA_INTRINSICS_ASSESSMENT_SCHEMA = (
    "rocell.static_camera_intrinsics_rehearsal_assessment.v1"
)
MAX_STATIC_CAMERA_INTRINSICS_BYTES = 256 * 1024
MAX_INTRINSICS_IMAGES = 64

TARGET_PROFILE_ID = "arducam-b0477-imx283-16mm-purchased-001"
TARGET_PROFILE_SOURCE_SHA256 = (
    "c15264f866d81b99cc1155171e21d3416d3a1fa7a244b5ae97642cc989f2e024"
)

_ARTIFACT_CLASS = "SYNTHETIC_REHEARSAL_ONLY"
_SYNTHETIC_EVIDENCE = "SYNTHETIC_GENERATED_NO_CAMERA"
_SYNTHETIC_LOCK = "SYNTHETIC_LOCK_EVIDENCE_NOT_PHYSICAL"
_SYNTHETIC_PRINT = "SYNTHETIC_PRINT_SCALE_REHEARSAL_NOT_MEASURED"
_SYNTHETIC_SOLUTION = "SYNTHETIC_NUMERIC_OUTPUT_NOT_PHYSICAL_CALIBRATION"
_SYNTHETIC_THRESHOLDS = "SYNTHETIC_REHEARSAL_NOT_PHYSICALLY_APPROVED"
_NATIVE_WIDTH = 5472
_NATIVE_HEIGHT = 3648
_NATIVE_FPS = 9.0
_NATIVE_PIXEL_FORMAT = "YUY2"
_MAX_CHARUCO_CORNERS = 88

_ROOT_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "artifact_id",
        "artifact_class",
        "profile_binding",
        "camera_binding",
        "calibration_target",
        "dataset",
        "synthetic_thresholds",
        "solution",
        "authority",
        "integrity_sha256",
    }
)
_PROFILE_FIELDS = frozenset({"profile_id", "profile_source_file_sha256"})
_CAMERA_FIELDS = frozenset(
    {
        "evidence_state",
        "persistent_camera_identity_sha256",
        "mode",
        "focus_lock_evidence_sha256",
        "aperture_lock_evidence_sha256",
        "controls_snapshot_sha256",
        "settings_binding_sha256",
    }
)
_MODE_FIELDS = frozenset({"width_px", "height_px", "fps", "pixel_format"})
_TARGET_FIELDS = frozenset(
    {"kind", "definition", "definition_sha256", "print_scale_verification"}
)
_BOARD_FIELDS = frozenset(
    {
        "squares_x",
        "squares_y",
        "square_length_mm",
        "marker_length_mm",
        "dictionary",
        "printed_on_rigid_backing",
    }
)
_PRINT_FIELDS = frozenset(
    {
        "evidence_state",
        "measurement_count",
        "evidence_file_sha256",
        "evidence_manifest_sha256",
    }
)
_DATASET_FIELDS = frozenset(
    {
        "evidence_state",
        "images_manifest_sha256",
        "split_commitment_sha256",
        "images",
        "splits",
    }
)
_IMAGE_FIELDS = frozenset(
    {
        "image_id",
        "source_image_sha256",
        "width_px",
        "height_px",
        "split",
        "detected_charuco_corners",
        "board_centroid_normalized",
        "board_area_fraction",
        "board_tilt_deg",
        "board_rotation_deg",
    }
)
_SPLIT_FIELDS = frozenset({"training_image_ids", "held_out_image_ids"})
_THRESHOLD_FIELDS = frozenset(
    {
        "evidence_state",
        "minimum_training_views",
        "minimum_held_out_views",
        "minimum_corners_per_view",
        "minimum_training_centroid_span_x",
        "minimum_training_centroid_span_y",
        "minimum_held_out_centroid_span_x",
        "minimum_held_out_centroid_span_y",
        "minimum_training_area_span",
        "minimum_training_rotation_span_deg",
        "minimum_quadrants_per_split",
        "maximum_training_rms_px",
        "maximum_held_out_rms_px",
        "maximum_held_out_p95_px",
        "maximum_view_rms_px",
    }
)
_SOLUTION_FIELDS = frozenset(
    {
        "evidence_state",
        "input_bindings_sha256",
        "distortion_model",
        "distortion_coefficients",
        "camera_matrix_row_major",
        "valid_pixel_roi",
        "output_crop",
        "per_view_residuals",
        "aggregate_residuals",
        "undistortion_map",
    }
)
_RECT_FIELDS = frozenset({"x_px", "y_px", "width_px", "height_px"})
_VIEW_RESIDUAL_FIELDS = frozenset(
    {"image_id", "split", "reprojection_rms_px", "maximum_residual_px"}
)
_AGGREGATE_FIELDS = frozenset(
    {
        "training_rms_px",
        "training_p95_px",
        "held_out_rms_px",
        "held_out_p95_px",
        "maximum_view_rms_px",
    }
)
_MAP_FIELDS = frozenset(
    {"width_px", "height_px", "coordinate_encoding", "map_sha256"}
)
_AUTHORITY_FIELDS = frozenset(
    {
        "physical_calibration_valid",
        "commissioned",
        "hardware_accessed",
        "camera_frames_requested",
        "arm_motion_commands",
        "contact_commands",
        "robot_motion_authority",
        "contact_authority",
        "physical_release_effect",
    }
)

_THRESHOLD_VALUES: Mapping[str, int | float | str] = {
    "evidence_state": _SYNTHETIC_THRESHOLDS,
    "minimum_training_views": 20,
    "minimum_held_out_views": 6,
    "minimum_corners_per_view": 30,
    "minimum_training_centroid_span_x": 0.60,
    "minimum_training_centroid_span_y": 0.60,
    "minimum_held_out_centroid_span_x": 0.40,
    "minimum_held_out_centroid_span_y": 0.40,
    "minimum_training_area_span": 0.08,
    "minimum_training_rotation_span_deg": 90.0,
    "minimum_quadrants_per_split": 4,
    "maximum_training_rms_px": 0.70,
    "maximum_held_out_rms_px": 0.90,
    "maximum_held_out_p95_px": 1.00,
    "maximum_view_rms_px": 1.25,
}


class StaticCameraIntrinsicsError(ValueError):
    """The intrinsics rehearsal is malformed, inconsistent, or overclaims."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StaticCameraIntrinsicsError(
            "static-camera intrinsics document cannot be canonicalized"
        ) from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _reject_constant(value: str) -> None:
    raise StaticCameraIntrinsicsError(
        f"static-camera intrinsics document contains nonfinite constant {value!r}"
    )


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StaticCameraIntrinsicsError(
                f"static-camera intrinsics document contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StaticCameraIntrinsicsError(f"{label} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise StaticCameraIntrinsicsError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _exact(value: object, expected: object, label: str) -> None:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StaticCameraIntrinsicsError(
                f"{label} must be numeric value {expected!r}"
            )
        numeric = float(value)
        if not math.isfinite(numeric) or numeric != float(expected):
            raise StaticCameraIntrinsicsError(
                f"{label} must be {expected!r}, got {value!r}"
            )
        if isinstance(expected, int) and not isinstance(value, int):
            raise StaticCameraIntrinsicsError(
                f"{label} must be integer value {expected!r}"
            )
        return
    if type(value) is not type(expected) or value != expected:
        raise StaticCameraIntrinsicsError(
            f"{label} must be {expected!r}, got {value!r}"
        )


def _text(value: object, label: str, *, maximum: int = 128) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise StaticCameraIntrinsicsError(
            f"{label} must be non-empty bounded trimmed text"
        )
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StaticCameraIntrinsicsError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _integer(
    value: object, label: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise StaticCameraIntrinsicsError(
            f"{label} must be an integer >= {minimum}"
        )
    if maximum is not None and value > maximum:
        raise StaticCameraIntrinsicsError(
            f"{label} must be an integer <= {maximum}"
        )
    return value


def _finite(
    value: object, label: str, *, minimum: float, maximum: float
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StaticCameraIntrinsicsError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise StaticCameraIntrinsicsError(f"{label} must be finite")
    if not minimum <= result <= maximum:
        raise StaticCameraIntrinsicsError(
            f"{label} must be within [{minimum}, {maximum}]"
        )
    return result


def _array(value: object, label: str, *, maximum: int) -> list[Any]:
    if not isinstance(value, list):
        raise StaticCameraIntrinsicsError(f"{label} must be an array")
    if len(value) > maximum:
        raise StaticCameraIntrinsicsError(
            f"{label} exceeds the maximum of {maximum} entries"
        )
    return value


@dataclass(frozen=True, slots=True)
class StaticIntrinsicsMode:
    """Exact full-resolution physical target mode for the purchased B0477."""

    width_px: int
    height_px: int
    fps: float
    pixel_format: str

    def to_dict(self) -> dict[str, object]:
        return {
            "width_px": self.width_px,
            "height_px": self.height_px,
            "fps": self.fps,
            "pixel_format": self.pixel_format,
        }


@dataclass(frozen=True, slots=True)
class CharucoBoardDefinition:
    """Metric ChArUco target definition whose bytes are separately evidenced."""

    squares_x: int
    squares_y: int
    square_length_mm: float
    marker_length_mm: float
    dictionary: str
    printed_on_rigid_backing: bool

    @property
    def maximum_corner_count(self) -> int:
        return (self.squares_x - 1) * (self.squares_y - 1)

    def to_dict(self) -> dict[str, object]:
        return {
            "squares_x": self.squares_x,
            "squares_y": self.squares_y,
            "square_length_mm": self.square_length_mm,
            "marker_length_mm": self.marker_length_mm,
            "dictionary": self.dictionary,
            "printed_on_rigid_backing": self.printed_on_rigid_backing,
        }


@dataclass(frozen=True, slots=True)
class IntrinsicsImageObservation:
    """One content-addressed synthetic calibration-view observation."""

    image_id: str
    source_image_sha256: str
    width_px: int
    height_px: int
    split: str
    detected_charuco_corners: int
    centroid_x: float
    centroid_y: float
    board_area_fraction: float
    board_tilt_deg: float
    board_rotation_deg: float


@dataclass(frozen=True, slots=True)
class IntrinsicsViewResidual:
    """Synthetic solver residual for one input image."""

    image_id: str
    split: str
    reprojection_rms_px: float
    maximum_residual_px: float


@dataclass(frozen=True, slots=True)
class StaticCameraIntrinsicsRehearsal:
    """Validated immutable rehearsal; its physical authority is always zero."""

    source_path: Path | None
    source_file_sha256: str
    canonical_sha256: str
    integrity_sha256: str
    artifact_id: str
    profile_id: str
    profile_source_file_sha256: str
    persistent_camera_identity_sha256: str
    mode: StaticIntrinsicsMode
    focus_lock_evidence_sha256: str
    aperture_lock_evidence_sha256: str
    controls_snapshot_sha256: str
    settings_binding_sha256: str
    board: CharucoBoardDefinition
    board_definition_sha256: str
    print_scale_manifest_sha256: str
    images_manifest_sha256: str
    split_commitment_sha256: str
    images: tuple[IntrinsicsImageObservation, ...]
    training_image_ids: tuple[str, ...]
    held_out_image_ids: tuple[str, ...]
    distortion_model: str
    distortion_coefficients: tuple[float, ...]
    camera_matrix_row_major: tuple[float, ...]
    valid_pixel_roi: tuple[int, int, int, int]
    output_crop: tuple[int, int, int, int]
    per_view_residuals: tuple[IntrinsicsViewResidual, ...]
    aggregate_residuals: tuple[tuple[str, float], ...]
    undistortion_map_sha256: str
    input_bindings_sha256: str

    @property
    def artifact_class(self) -> str:
        return _ARTIFACT_CLASS

    @property
    def physical_calibration_valid(self) -> bool:
        return False

    @property
    def commissioned(self) -> bool:
        return False

    @property
    def robot_motion_authority(self) -> bool:
        return False

    @property
    def contact_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class StaticCameraIntrinsicsAssessment:
    """Structural pass report which explicitly withholds every physical claim."""

    artifact_id: str
    artifact_canonical_sha256: str
    input_bindings_sha256: str
    training_view_count: int
    held_out_view_count: int
    structural_gates_passed: bool = field(init=False, default=True)
    status: str = field(init=False, default="SYNTHETIC_REHEARSAL_ONLY")
    thresholds_authority: str = field(
        init=False, default=_SYNTHETIC_THRESHOLDS
    )
    physical_calibration_valid: bool = field(init=False, default=False)
    commissioned: bool = field(init=False, default=False)
    hardware_accessed: bool = field(init=False, default=False)
    camera_frames_requested: int = field(init=False, default=0)
    arm_motion_commands: int = field(init=False, default=0)
    contact_commands: int = field(init=False, default=0)
    robot_motion_authority: bool = field(init=False, default=False)
    contact_authority: bool = field(init=False, default=False)
    physical_release_effect: str = field(init=False, default="NONE")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": STATIC_CAMERA_INTRINSICS_ASSESSMENT_SCHEMA,
            "artifact_id": self.artifact_id,
            "artifact_canonical_sha256": self.artifact_canonical_sha256,
            "input_bindings_sha256": self.input_bindings_sha256,
            "training_view_count": self.training_view_count,
            "held_out_view_count": self.held_out_view_count,
            "structural_gates_passed": self.structural_gates_passed,
            "status": self.status,
            "thresholds_authority": self.thresholds_authority,
            "physical_calibration_valid": self.physical_calibration_valid,
            "commissioned": self.commissioned,
            "hardware_accessed": self.hardware_accessed,
            "camera_frames_requested": self.camera_frames_requested,
            "arm_motion_commands": self.arm_motion_commands,
            "contact_commands": self.contact_commands,
            "robot_motion_authority": self.robot_motion_authority,
            "contact_authority": self.contact_authority,
            "physical_release_effect": self.physical_release_effect,
        }

    @property
    def canonical_sha256(self) -> str:
        return _hash(self.to_dict())


def _parse_mode(raw: object) -> StaticIntrinsicsMode:
    mode = _mapping(raw, "camera_binding.mode")
    _exact_fields(mode, _MODE_FIELDS, "camera_binding.mode")
    expected = {
        "width_px": _NATIVE_WIDTH,
        "height_px": _NATIVE_HEIGHT,
        "fps": _NATIVE_FPS,
        "pixel_format": _NATIVE_PIXEL_FORMAT,
    }
    for name, value in expected.items():
        _exact(mode.get(name), value, f"camera_binding.mode.{name}")
    return StaticIntrinsicsMode(
        _NATIVE_WIDTH, _NATIVE_HEIGHT, _NATIVE_FPS, _NATIVE_PIXEL_FORMAT
    )


def _parse_board(raw: object) -> CharucoBoardDefinition:
    board = _mapping(raw, "calibration_target.definition")
    _exact_fields(board, _BOARD_FIELDS, "calibration_target.definition")
    expected = {
        "squares_x": 12,
        "squares_y": 9,
        "square_length_mm": 30.0,
        "marker_length_mm": 22.0,
        "dictionary": "DICT_5X5_1000",
        "printed_on_rigid_backing": True,
    }
    for name, value in expected.items():
        _exact(board.get(name), value, f"calibration_target.definition.{name}")
    typed = CharucoBoardDefinition(12, 9, 30.0, 22.0, "DICT_5X5_1000", True)
    if typed.maximum_corner_count != _MAX_CHARUCO_CORNERS:
        raise StaticCameraIntrinsicsError("internal ChArUco corner count mismatch")
    return typed


def _parse_image(raw: object, index: int) -> IntrinsicsImageObservation:
    label = f"dataset.images[{index}]"
    image = _mapping(raw, label)
    _exact_fields(image, _IMAGE_FIELDS, label)
    image_id = _text(image.get("image_id"), f"{label}.image_id", maximum=64)
    source_hash = _digest(
        image.get("source_image_sha256"), f"{label}.source_image_sha256"
    )
    width = _integer(image.get("width_px"), f"{label}.width_px", minimum=1)
    height = _integer(image.get("height_px"), f"{label}.height_px", minimum=1)
    if (width, height) != (_NATIVE_WIDTH, _NATIVE_HEIGHT):
        raise StaticCameraIntrinsicsError(
            f"{label} resolution must match the exact B0477 target mode"
        )
    split = _text(image.get("split"), f"{label}.split", maximum=16)
    if split not in {"TRAINING", "HELD_OUT"}:
        raise StaticCameraIntrinsicsError(
            f"{label}.split must be TRAINING or HELD_OUT"
        )
    centroid = _array(
        image.get("board_centroid_normalized"),
        f"{label}.board_centroid_normalized",
        maximum=2,
    )
    if len(centroid) != 2:
        raise StaticCameraIntrinsicsError(
            f"{label}.board_centroid_normalized must have exactly two values"
        )
    return IntrinsicsImageObservation(
        image_id=image_id,
        source_image_sha256=source_hash,
        width_px=width,
        height_px=height,
        split=split,
        detected_charuco_corners=_integer(
            image.get("detected_charuco_corners"),
            f"{label}.detected_charuco_corners",
            minimum=1,
            maximum=_MAX_CHARUCO_CORNERS,
        ),
        centroid_x=_finite(
            centroid[0], f"{label}.board_centroid_normalized[0]", minimum=0.0, maximum=1.0
        ),
        centroid_y=_finite(
            centroid[1], f"{label}.board_centroid_normalized[1]", minimum=0.0, maximum=1.0
        ),
        board_area_fraction=_finite(
            image.get("board_area_fraction"),
            f"{label}.board_area_fraction",
            minimum=0.005,
            maximum=0.95,
        ),
        board_tilt_deg=_finite(
            image.get("board_tilt_deg"),
            f"{label}.board_tilt_deg",
            minimum=0.0,
            maximum=80.0,
        ),
        board_rotation_deg=_finite(
            image.get("board_rotation_deg"),
            f"{label}.board_rotation_deg",
            minimum=-180.0,
            maximum=180.0,
        ),
    )


def _parse_residual(raw: object, index: int) -> IntrinsicsViewResidual:
    label = f"solution.per_view_residuals[{index}]"
    residual = _mapping(raw, label)
    _exact_fields(residual, _VIEW_RESIDUAL_FIELDS, label)
    rms = _finite(
        residual.get("reprojection_rms_px"),
        f"{label}.reprojection_rms_px",
        minimum=0.0,
        maximum=100.0,
    )
    maximum = _finite(
        residual.get("maximum_residual_px"),
        f"{label}.maximum_residual_px",
        minimum=0.0,
        maximum=1000.0,
    )
    if maximum < rms:
        raise StaticCameraIntrinsicsError(
            f"{label}.maximum_residual_px cannot be below its RMS"
        )
    split = _text(residual.get("split"), f"{label}.split", maximum=16)
    if split not in {"TRAINING", "HELD_OUT"}:
        raise StaticCameraIntrinsicsError(f"{label}.split is invalid")
    return IntrinsicsViewResidual(
        image_id=_text(residual.get("image_id"), f"{label}.image_id", maximum=64),
        split=split,
        reprojection_rms_px=rms,
        maximum_residual_px=maximum,
    )


def _rect(raw: object, label: str) -> tuple[int, int, int, int]:
    rect = _mapping(raw, label)
    _exact_fields(rect, _RECT_FIELDS, label)
    result = (
        _integer(rect.get("x_px"), f"{label}.x_px"),
        _integer(rect.get("y_px"), f"{label}.y_px"),
        _integer(rect.get("width_px"), f"{label}.width_px", minimum=1),
        _integer(rect.get("height_px"), f"{label}.height_px", minimum=1),
    )
    x, y, width, height = result
    if x + width > _NATIVE_WIDTH or y + height > _NATIVE_HEIGHT:
        raise StaticCameraIntrinsicsError(f"{label} exceeds the native image bounds")
    return result


def _nearest_rank_p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _root_integrity(document: Mapping[str, Any]) -> str:
    return _hash({key: value for key, value in document.items() if key != "integrity_sha256"})


def _validate_coverage(
    images: tuple[IntrinsicsImageObservation, ...],
    training_ids: tuple[str, ...],
    held_out_ids: tuple[str, ...],
) -> None:
    by_id = {image.image_id: image for image in images}
    training = [by_id[item] for item in training_ids]
    held_out = [by_id[item] for item in held_out_ids]
    if len(training) < int(_THRESHOLD_VALUES["minimum_training_views"]):
        raise StaticCameraIntrinsicsError("insufficient training views")
    if len(held_out) < int(_THRESHOLD_VALUES["minimum_held_out_views"]):
        raise StaticCameraIntrinsicsError("insufficient held-out views")
    minimum_corners = int(_THRESHOLD_VALUES["minimum_corners_per_view"])
    if any(image.detected_charuco_corners < minimum_corners for image in images):
        raise StaticCameraIntrinsicsError("insufficient ChArUco corners in a view")

    def span(group: Sequence[IntrinsicsImageObservation], name: str) -> float:
        values = [float(getattr(image, name)) for image in group]
        return max(values) - min(values)

    coverage_checks = (
        (span(training, "centroid_x"), "minimum_training_centroid_span_x"),
        (span(training, "centroid_y"), "minimum_training_centroid_span_y"),
        (span(held_out, "centroid_x"), "minimum_held_out_centroid_span_x"),
        (span(held_out, "centroid_y"), "minimum_held_out_centroid_span_y"),
        (span(training, "board_area_fraction"), "minimum_training_area_span"),
        (span(training, "board_rotation_deg"), "minimum_training_rotation_span_deg"),
    )
    for actual, threshold_name in coverage_checks:
        if actual + 1e-12 < float(_THRESHOLD_VALUES[threshold_name]):
            raise StaticCameraIntrinsicsError(
                f"insufficient view coverage for {threshold_name}"
            )
    minimum_quadrants = int(_THRESHOLD_VALUES["minimum_quadrants_per_split"])
    for label, group in (("training", training), ("held-out", held_out)):
        quadrants = {
            (image.centroid_x >= 0.5, image.centroid_y >= 0.5) for image in group
        }
        if len(quadrants) < minimum_quadrants:
            raise StaticCameraIntrinsicsError(
                f"insufficient {label} centroid quadrant coverage"
            )


def _validate_aggregate_residuals(
    residuals: tuple[IntrinsicsViewResidual, ...], raw: Mapping[str, Any]
) -> tuple[tuple[str, float], ...]:
    _exact_fields(raw, _AGGREGATE_FIELDS, "solution.aggregate_residuals")
    training = [item.reprojection_rms_px for item in residuals if item.split == "TRAINING"]
    held_out = [item.reprojection_rms_px for item in residuals if item.split == "HELD_OUT"]
    if not training or not held_out:
        raise StaticCameraIntrinsicsError("residuals must cover both dataset splits")
    expected = {
        "training_rms_px": math.sqrt(sum(value * value for value in training) / len(training)),
        "training_p95_px": _nearest_rank_p95(training),
        "held_out_rms_px": math.sqrt(sum(value * value for value in held_out) / len(held_out)),
        "held_out_p95_px": _nearest_rank_p95(held_out),
        "maximum_view_rms_px": max(training + held_out),
    }
    result: list[tuple[str, float]] = []
    for name, computed in expected.items():
        declared = _finite(
            raw.get(name), f"solution.aggregate_residuals.{name}", minimum=0.0, maximum=100.0
        )
        if not math.isclose(declared, computed, rel_tol=0.0, abs_tol=1e-9):
            raise StaticCameraIntrinsicsError(
                f"solution.aggregate_residuals.{name} does not match per-view residuals"
            )
        result.append((name, declared))
    if expected["training_rms_px"] > float(_THRESHOLD_VALUES["maximum_training_rms_px"]):
        raise StaticCameraIntrinsicsError("synthetic training RMS threshold exceeded")
    if expected["held_out_rms_px"] > float(_THRESHOLD_VALUES["maximum_held_out_rms_px"]):
        raise StaticCameraIntrinsicsError("synthetic held-out RMS threshold exceeded")
    if expected["held_out_p95_px"] > float(_THRESHOLD_VALUES["maximum_held_out_p95_px"]):
        raise StaticCameraIntrinsicsError("synthetic held-out p95 threshold exceeded")
    if expected["maximum_view_rms_px"] > float(_THRESHOLD_VALUES["maximum_view_rms_px"]):
        raise StaticCameraIntrinsicsError("synthetic maximum-view RMS threshold exceeded")
    return tuple(result)


def parse_static_camera_intrinsics_json(
    payload: bytes, *, source_path: Path | None = None
) -> StaticCameraIntrinsicsRehearsal:
    """Parse and validate one sealed, synthetic-only intrinsics rehearsal."""

    if not isinstance(payload, bytes):
        raise StaticCameraIntrinsicsError("intrinsics payload must be bytes")
    if not payload:
        raise StaticCameraIntrinsicsError("intrinsics payload is empty")
    if len(payload) > MAX_STATIC_CAMERA_INTRINSICS_BYTES:
        raise StaticCameraIntrinsicsError(
            f"intrinsics payload exceeds {MAX_STATIC_CAMERA_INTRINSICS_BYTES} bytes"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StaticCameraIntrinsicsError("intrinsics payload must be UTF-8") from exc
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except StaticCameraIntrinsicsError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise StaticCameraIntrinsicsError(f"invalid intrinsics JSON: {exc}") from exc
    document = _mapping(decoded, "root")
    _exact_fields(document, _ROOT_FIELDS, "root")
    declared_integrity = _digest(document.get("integrity_sha256"), "integrity_sha256")
    computed_integrity = _root_integrity(document)
    if declared_integrity != computed_integrity:
        raise StaticCameraIntrinsicsError("intrinsics integrity hash mismatch (tampering detected)")
    _exact(document.get("schema"), STATIC_CAMERA_INTRINSICS_SCHEMA, "schema")
    _exact(document.get("schema_version"), 1, "schema_version")
    artifact_id = _text(document.get("artifact_id"), "artifact_id", maximum=96)
    _exact(document.get("artifact_class"), _ARTIFACT_CLASS, "artifact_class")

    profile = _mapping(document.get("profile_binding"), "profile_binding")
    _exact_fields(profile, _PROFILE_FIELDS, "profile_binding")
    _exact(profile.get("profile_id"), TARGET_PROFILE_ID, "profile_binding.profile_id")
    _exact(
        profile.get("profile_source_file_sha256"),
        TARGET_PROFILE_SOURCE_SHA256,
        "profile_binding.profile_source_file_sha256",
    )

    camera = _mapping(document.get("camera_binding"), "camera_binding")
    _exact_fields(camera, _CAMERA_FIELDS, "camera_binding")
    _exact(camera.get("evidence_state"), _SYNTHETIC_LOCK, "camera_binding.evidence_state")
    identity_hash = _digest(
        camera.get("persistent_camera_identity_sha256"),
        "camera_binding.persistent_camera_identity_sha256",
    )
    mode = _parse_mode(camera.get("mode"))
    focus_hash = _digest(
        camera.get("focus_lock_evidence_sha256"),
        "camera_binding.focus_lock_evidence_sha256",
    )
    aperture_hash = _digest(
        camera.get("aperture_lock_evidence_sha256"),
        "camera_binding.aperture_lock_evidence_sha256",
    )
    controls_hash = _digest(
        camera.get("controls_snapshot_sha256"),
        "camera_binding.controls_snapshot_sha256",
    )
    settings_hash = _digest(
        camera.get("settings_binding_sha256"),
        "camera_binding.settings_binding_sha256",
    )
    expected_settings_hash = _hash(
        {
            "persistent_camera_identity_sha256": identity_hash,
            "mode": mode.to_dict(),
            "focus_lock_evidence_sha256": focus_hash,
            "aperture_lock_evidence_sha256": aperture_hash,
            "controls_snapshot_sha256": controls_hash,
        }
    )
    if settings_hash != expected_settings_hash:
        raise StaticCameraIntrinsicsError("camera settings binding hash mismatch")

    target = _mapping(document.get("calibration_target"), "calibration_target")
    _exact_fields(target, _TARGET_FIELDS, "calibration_target")
    _exact(target.get("kind"), "CHARUCO", "calibration_target.kind")
    board_raw = _mapping(target.get("definition"), "calibration_target.definition")
    board = _parse_board(board_raw)
    board_hash = _digest(
        target.get("definition_sha256"), "calibration_target.definition_sha256"
    )
    if board_hash != _hash(board_raw):
        raise StaticCameraIntrinsicsError("ChArUco board definition hash mismatch")
    print_scale = _mapping(
        target.get("print_scale_verification"),
        "calibration_target.print_scale_verification",
    )
    _exact_fields(print_scale, _PRINT_FIELDS, "calibration_target.print_scale_verification")
    _exact(
        print_scale.get("evidence_state"),
        _SYNTHETIC_PRINT,
        "calibration_target.print_scale_verification.evidence_state",
    )
    _integer(
        print_scale.get("measurement_count"),
        "calibration_target.print_scale_verification.measurement_count",
        minimum=6,
        maximum=64,
    )
    print_files = _array(
        print_scale.get("evidence_file_sha256"),
        "calibration_target.print_scale_verification.evidence_file_sha256",
        maximum=16,
    )
    if len(print_files) < 2:
        raise StaticCameraIntrinsicsError("print-scale verification requires at least two evidence hashes")
    parsed_print_files = tuple(
        _digest(value, f"print-scale evidence hash {index}")
        for index, value in enumerate(print_files)
    )
    if len(set(parsed_print_files)) != len(parsed_print_files):
        raise StaticCameraIntrinsicsError("duplicate print-scale evidence hash")
    print_manifest_hash = _digest(
        print_scale.get("evidence_manifest_sha256"),
        "calibration_target.print_scale_verification.evidence_manifest_sha256",
    )
    expected_print_hash = _hash(
        {
            "evidence_state": _SYNTHETIC_PRINT,
            "measurement_count": print_scale.get("measurement_count"),
            "evidence_file_sha256": print_files,
        }
    )
    if print_manifest_hash != expected_print_hash:
        raise StaticCameraIntrinsicsError("print-scale evidence manifest hash mismatch")

    thresholds = _mapping(document.get("synthetic_thresholds"), "synthetic_thresholds")
    _exact_fields(thresholds, _THRESHOLD_FIELDS, "synthetic_thresholds")
    for name, expected in _THRESHOLD_VALUES.items():
        _exact(thresholds.get(name), expected, f"synthetic_thresholds.{name}")

    dataset = _mapping(document.get("dataset"), "dataset")
    _exact_fields(dataset, _DATASET_FIELDS, "dataset")
    _exact(dataset.get("evidence_state"), _SYNTHETIC_EVIDENCE, "dataset.evidence_state")
    raw_images = _array(dataset.get("images"), "dataset.images", maximum=MAX_INTRINSICS_IMAGES)
    if not raw_images:
        raise StaticCameraIntrinsicsError("dataset.images cannot be empty")
    images = tuple(_parse_image(item, index) for index, item in enumerate(raw_images))
    image_ids = tuple(image.image_id for image in images)
    image_hashes = tuple(image.source_image_sha256 for image in images)
    if len(set(image_ids)) != len(image_ids):
        raise StaticCameraIntrinsicsError("dataset contains duplicate image ids")
    if len(set(image_hashes)) != len(image_hashes):
        raise StaticCameraIntrinsicsError("dataset contains duplicate image hashes")
    images_manifest_hash = _digest(
        dataset.get("images_manifest_sha256"), "dataset.images_manifest_sha256"
    )
    if images_manifest_hash != _hash(raw_images):
        raise StaticCameraIntrinsicsError("dataset image manifest hash mismatch")
    splits = _mapping(dataset.get("splits"), "dataset.splits")
    _exact_fields(splits, _SPLIT_FIELDS, "dataset.splits")
    raw_training = _array(
        splits.get("training_image_ids"), "dataset.splits.training_image_ids", maximum=MAX_INTRINSICS_IMAGES
    )
    raw_held_out = _array(
        splits.get("held_out_image_ids"), "dataset.splits.held_out_image_ids", maximum=MAX_INTRINSICS_IMAGES
    )
    training_ids = tuple(
        _text(item, f"training_image_ids[{index}]", maximum=64)
        for index, item in enumerate(raw_training)
    )
    held_out_ids = tuple(
        _text(item, f"held_out_image_ids[{index}]", maximum=64)
        for index, item in enumerate(raw_held_out)
    )
    if len(set(training_ids)) != len(training_ids) or len(set(held_out_ids)) != len(held_out_ids):
        raise StaticCameraIntrinsicsError("dataset split contains duplicate image ids")
    if set(training_ids) & set(held_out_ids):
        raise StaticCameraIntrinsicsError("training and held-out splits are not disjoint")
    if set(training_ids) | set(held_out_ids) != set(image_ids):
        raise StaticCameraIntrinsicsError("dataset split is not an exact image partition")
    expected_labels = {item: "TRAINING" for item in training_ids}
    expected_labels.update({item: "HELD_OUT" for item in held_out_ids})
    if any(image.split != expected_labels[image.image_id] for image in images):
        raise StaticCameraIntrinsicsError("image split label disagrees with split commitment")
    split_hash = _digest(
        dataset.get("split_commitment_sha256"), "dataset.split_commitment_sha256"
    )
    if split_hash != _hash(splits):
        raise StaticCameraIntrinsicsError("dataset split commitment hash mismatch")
    _validate_coverage(images, training_ids, held_out_ids)

    solution = _mapping(document.get("solution"), "solution")
    _exact_fields(solution, _SOLUTION_FIELDS, "solution")
    _exact(solution.get("evidence_state"), _SYNTHETIC_SOLUTION, "solution.evidence_state")
    input_bindings_hash = _digest(
        solution.get("input_bindings_sha256"), "solution.input_bindings_sha256"
    )
    expected_input_bindings = _hash(
        {
            "profile_id": TARGET_PROFILE_ID,
            "profile_source_file_sha256": TARGET_PROFILE_SOURCE_SHA256,
            "persistent_camera_identity_sha256": identity_hash,
            "settings_binding_sha256": settings_hash,
            "board_definition_sha256": board_hash,
            "print_scale_evidence_manifest_sha256": print_manifest_hash,
            "images_manifest_sha256": images_manifest_hash,
            "split_commitment_sha256": split_hash,
        }
    )
    if input_bindings_hash != expected_input_bindings:
        raise StaticCameraIntrinsicsError("solution input bindings hash mismatch")
    _exact(
        solution.get("distortion_model"),
        "OPENCV_RATIONAL_POLYNOMIAL_8",
        "solution.distortion_model",
    )
    raw_coefficients = _array(
        solution.get("distortion_coefficients"),
        "solution.distortion_coefficients",
        maximum=8,
    )
    if len(raw_coefficients) != 8:
        raise StaticCameraIntrinsicsError("distortion model requires exactly 8 coefficients")
    coefficients = tuple(
        _finite(value, f"distortion_coefficients[{index}]", minimum=-5.0, maximum=5.0)
        for index, value in enumerate(raw_coefficients)
    )
    raw_matrix = _array(
        solution.get("camera_matrix_row_major"),
        "solution.camera_matrix_row_major",
        maximum=9,
    )
    if len(raw_matrix) != 9:
        raise StaticCameraIntrinsicsError("camera matrix must contain exactly 9 values")
    matrix = tuple(
        _finite(value, f"camera_matrix_row_major[{index}]", minimum=-100_000.0, maximum=100_000.0)
        for index, value in enumerate(raw_matrix)
    )
    if matrix[1] != 0.0 or matrix[3] != 0.0 or matrix[6:] != (0.0, 0.0, 1.0):
        raise StaticCameraIntrinsicsError("camera matrix must have canonical pinhole structure")
    if not 100.0 <= matrix[0] <= 20_000.0 or not 100.0 <= matrix[4] <= 20_000.0:
        raise StaticCameraIntrinsicsError("camera focal lengths are outside rehearsal bounds")
    if not 0.0 <= matrix[2] < _NATIVE_WIDTH or not 0.0 <= matrix[5] < _NATIVE_HEIGHT:
        raise StaticCameraIntrinsicsError("camera principal point is outside the image")
    roi = _rect(solution.get("valid_pixel_roi"), "solution.valid_pixel_roi")
    crop = _rect(solution.get("output_crop"), "solution.output_crop")
    rx, ry, rw, rh = roi
    cx, cy, cw, ch = crop
    if cx < rx or cy < ry or cx + cw > rx + rw or cy + ch > ry + rh:
        raise StaticCameraIntrinsicsError("output crop must remain inside the valid-pixel ROI")
    raw_residuals = _array(
        solution.get("per_view_residuals"),
        "solution.per_view_residuals",
        maximum=MAX_INTRINSICS_IMAGES,
    )
    residuals = tuple(
        _parse_residual(item, index) for index, item in enumerate(raw_residuals)
    )
    residual_ids = tuple(item.image_id for item in residuals)
    if len(set(residual_ids)) != len(residual_ids):
        raise StaticCameraIntrinsicsError("duplicate per-view residual image id")
    if set(residual_ids) != set(image_ids) or len(residuals) != len(images):
        raise StaticCameraIntrinsicsError("per-view residuals do not exactly cover input images")
    image_split = {image.image_id: image.split for image in images}
    if any(item.split != image_split[item.image_id] for item in residuals):
        raise StaticCameraIntrinsicsError("residual split disagrees with image split")
    aggregate = _mapping(solution.get("aggregate_residuals"), "solution.aggregate_residuals")
    aggregate_values = _validate_aggregate_residuals(residuals, aggregate)
    map_record = _mapping(solution.get("undistortion_map"), "solution.undistortion_map")
    _exact_fields(map_record, _MAP_FIELDS, "solution.undistortion_map")
    _exact(map_record.get("width_px"), _NATIVE_WIDTH, "solution.undistortion_map.width_px")
    _exact(map_record.get("height_px"), _NATIVE_HEIGHT, "solution.undistortion_map.height_px")
    _exact(
        map_record.get("coordinate_encoding"),
        "CV_32FC1_XY_PAIR",
        "solution.undistortion_map.coordinate_encoding",
    )
    map_hash = _digest(map_record.get("map_sha256"), "solution.undistortion_map.map_sha256")

    authority = _mapping(document.get("authority"), "authority")
    _exact_fields(authority, _AUTHORITY_FIELDS, "authority")
    expected_authority: Mapping[str, object] = {
        "physical_calibration_valid": False,
        "commissioned": False,
        "hardware_accessed": False,
        "camera_frames_requested": 0,
        "arm_motion_commands": 0,
        "contact_commands": 0,
        "robot_motion_authority": False,
        "contact_authority": False,
        "physical_release_effect": "NONE",
    }
    for name, authority_expected in expected_authority.items():
        _exact(authority.get(name), authority_expected, f"authority.{name}")

    return StaticCameraIntrinsicsRehearsal(
        source_path=source_path.resolve() if source_path is not None else None,
        source_file_sha256=hashlib.sha256(payload).hexdigest(),
        canonical_sha256=_hash(document),
        integrity_sha256=declared_integrity,
        artifact_id=artifact_id,
        profile_id=TARGET_PROFILE_ID,
        profile_source_file_sha256=TARGET_PROFILE_SOURCE_SHA256,
        persistent_camera_identity_sha256=identity_hash,
        mode=mode,
        focus_lock_evidence_sha256=focus_hash,
        aperture_lock_evidence_sha256=aperture_hash,
        controls_snapshot_sha256=controls_hash,
        settings_binding_sha256=settings_hash,
        board=board,
        board_definition_sha256=board_hash,
        print_scale_manifest_sha256=print_manifest_hash,
        images_manifest_sha256=images_manifest_hash,
        split_commitment_sha256=split_hash,
        images=images,
        training_image_ids=training_ids,
        held_out_image_ids=held_out_ids,
        distortion_model="OPENCV_RATIONAL_POLYNOMIAL_8",
        distortion_coefficients=coefficients,
        camera_matrix_row_major=matrix,
        valid_pixel_roi=roi,
        output_crop=crop,
        per_view_residuals=residuals,
        aggregate_residuals=aggregate_values,
        undistortion_map_sha256=map_hash,
        input_bindings_sha256=input_bindings_hash,
    )


def load_static_camera_intrinsics_rehearsal(
    path: Path | str, *, fixture_root: Path | str
) -> StaticCameraIntrinsicsRehearsal:
    """Load a JSON rehearsal only from within the explicitly supplied root."""

    from rocell.application.physical_onboarding_durability import (
        PhysicalOnboardingDurabilityError,
        read_bounded_regular_file,
    )

    root = Path(fixture_root).resolve()
    selected = Path(path)
    if not selected.is_absolute():
        selected = root / selected
    selected = selected.resolve()
    try:
        selected.relative_to(root)
    except ValueError as exc:
        raise StaticCameraIntrinsicsError("intrinsics fixture path escapes fixture root") from exc
    try:
        payload = read_bounded_regular_file(
            selected, maximum_bytes=MAX_STATIC_CAMERA_INTRINSICS_BYTES,
            label="intrinsics fixture",
        )
    except (OSError, PhysicalOnboardingDurabilityError) as exc:
        raise StaticCameraIntrinsicsError(f"cannot read intrinsics fixture {selected}: {exc}") from exc
    return parse_static_camera_intrinsics_json(payload, source_path=selected)


def assess_static_camera_intrinsics_rehearsal(
    artifact: StaticCameraIntrinsicsRehearsal,
    *,
    purchased_profile: PurchasedCameraProfile | None = None,
) -> StaticCameraIntrinsicsAssessment:
    """Report a structural rehearsal pass while retaining zero authority."""

    if not isinstance(artifact, StaticCameraIntrinsicsRehearsal):
        raise TypeError("artifact must be StaticCameraIntrinsicsRehearsal")
    if purchased_profile is not None:
        if not isinstance(purchased_profile, PurchasedCameraProfile):
            raise TypeError("purchased_profile must be PurchasedCameraProfile")
        if purchased_profile.profile_id != artifact.profile_id:
            raise StaticCameraIntrinsicsError("intrinsics profile id binding mismatch")
        if purchased_profile.source_file_sha256 != artifact.profile_source_file_sha256:
            raise StaticCameraIntrinsicsError("intrinsics profile source hash binding mismatch")
        if purchased_profile.live_ready:
            raise StaticCameraIntrinsicsError("purchase profile unexpectedly grants live readiness")
    return StaticCameraIntrinsicsAssessment(
        artifact_id=artifact.artifact_id,
        artifact_canonical_sha256=artifact.canonical_sha256,
        input_bindings_sha256=artifact.input_bindings_sha256,
        training_view_count=len(artifact.training_image_ids),
        held_out_view_count=len(artifact.held_out_image_ids),
    )


__all__ = [
    "MAX_INTRINSICS_IMAGES",
    "MAX_STATIC_CAMERA_INTRINSICS_BYTES",
    "STATIC_CAMERA_INTRINSICS_ASSESSMENT_SCHEMA",
    "STATIC_CAMERA_INTRINSICS_SCHEMA",
    "TARGET_PROFILE_ID",
    "TARGET_PROFILE_SOURCE_SHA256",
    "CharucoBoardDefinition",
    "IntrinsicsImageObservation",
    "IntrinsicsViewResidual",
    "StaticCameraIntrinsicsAssessment",
    "StaticCameraIntrinsicsError",
    "StaticCameraIntrinsicsRehearsal",
    "StaticIntrinsicsMode",
    "assess_static_camera_intrinsics_rehearsal",
    "load_static_camera_intrinsics_rehearsal",
    "parse_static_camera_intrinsics_json",
]
