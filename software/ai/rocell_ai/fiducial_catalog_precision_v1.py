"""Fail-closed fiducial plus catalog precision observations.

This is an additive precision source.  It consumes RoCell's existing typed
AprilTag pose observation and simulation-only nominal target catalog.  It does
not infer coordinates from pixels, construct a motion batch, or authorize any
physical action.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from rocell.targets.nominal import NominalTargetCatalog
from rocell.vision.pose_estimation_records import AprilTagPoseObservation

from .scene_observation import SHA256_PATTERN, canonical_hash


SCHEMA = "rocell.ai_fiducial_catalog_precision_observation.v1"
QUALIFICATION_SCHEMA = "rocell.ai_fiducial_catalog_qualification.v1"
SCOPE = "SYNTHETIC_OFFLINE_ONLY"
SOURCE_KIND = "APRILTAG_POSE_PLUS_FROZEN_CATALOG"

OBSERVATION_FIELDS = {
    "schema", "scope", "source_kind", "domain_id", "device",
    "required_target_ids", "targets", "pose_observation_sha256", "frame",
    "source_hashes", "fit", "qualification_sha256", "coverage_probability",
    "conservative_planar_error_bound_mm", "abstain", "abstain_reasons",
    "authority", "observation_sha256",
}

QUALIFICATION_FIELDS = {
    "schema",
    "scope",
    "domain_id",
    "device",
    "detector_configuration_sha256",
    "detector_implementation_sha256",
    "estimator_configuration_sha256",
    "estimator_implementation_sha256",
    "camera_intrinsics_sha256",
    "camera_settings_sha256",
    "tag_map_sha256",
    "target_catalog_sha256",
    "board_frame_definition_sha256",
    "camera_frame",
    "board_frame",
    "calibration_dataset_sha256",
    "evaluation_dataset_sha256",
    "coverage_probability",
    "conservative_planar_error_bound_mm",
    "minimum_inlier_tags",
    "maximum_inlier_rmse_px",
    "covered_target_ids",
    "qualification_sha256",
}


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be non-empty text without surrounding whitespace")
    return value


def validate_qualification(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != QUALIFICATION_FIELDS:
        raise ValueError("Invalid fiducial catalog qualification fields")
    if value["schema"] != QUALIFICATION_SCHEMA or value["scope"] != SCOPE:
        raise ValueError("Only synthetic offline fiducial qualification is supported")
    for key in (
        "detector_configuration_sha256",
        "detector_implementation_sha256",
        "estimator_configuration_sha256",
        "estimator_implementation_sha256",
        "camera_intrinsics_sha256",
        "camera_settings_sha256",
        "tag_map_sha256",
        "target_catalog_sha256",
        "board_frame_definition_sha256",
        "calibration_dataset_sha256",
        "evaluation_dataset_sha256",
        "qualification_sha256",
    ):
        _digest(value[key], key)
    if value["calibration_dataset_sha256"] == value["evaluation_dataset_sha256"]:
        raise ValueError("Calibration and evaluation datasets must differ")
    for key in ("domain_id", "device", "camera_frame", "board_frame"):
        _text(value[key], key)
    if value["device"] not in {"keyboard", "phone"}:
        raise ValueError("qualification device must be keyboard or phone")
    coverage = value["coverage_probability"]
    error = value["conservative_planar_error_bound_mm"]
    rmse = value["maximum_inlier_rmse_px"]
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in (coverage, error, rmse)):
        raise ValueError("Qualification bounds must be finite numbers")
    if not 0.95 <= float(coverage) < 1.0 or not 0.0 < float(error) <= 100.0:
        raise ValueError("Invalid qualification coverage or planar error bound")
    if not 0.0 < float(rmse) <= 100.0:
        raise ValueError("Invalid maximum inlier RMSE")
    minimum = value["minimum_inlier_tags"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= 256:
        raise ValueError("minimum_inlier_tags must be an integer in [1, 256]")
    targets = value["covered_target_ids"]
    if (
        not isinstance(targets, list)
        or not 1 <= len(targets) <= 256
        or any(not isinstance(item, str) or not item for item in targets)
        or len(set(targets)) != len(targets)
    ):
        raise ValueError("covered_target_ids must be a non-empty unique string list")
    unsigned = {key: item for key, item in value.items() if key != "qualification_sha256"}
    if value["qualification_sha256"] != canonical_hash(unsigned):
        raise ValueError("Fiducial catalog qualification hash mismatch")
    return value


def build_qualification(**fields: Any) -> dict[str, Any]:
    """Build a canonical synthetic qualification fixture.

    A future measured physical qualification needs a separately reviewed
    schema.  Changing ``scope`` here cannot produce physical evidence.
    """

    core = {"schema": QUALIFICATION_SCHEMA, "scope": SCOPE, **fields}
    result = {**core, "qualification_sha256": canonical_hash(core)}
    validate_qualification(result)
    return result


def validate_observation(value: object) -> Mapping[str, Any]:
    """Strictly validate an emitted observation and its redundant hash."""

    if not isinstance(value, Mapping) or set(value) != OBSERVATION_FIELDS:
        raise ValueError("Invalid fiducial catalog precision observation fields")
    if (
        value["schema"] != SCHEMA
        or value["scope"] != SCOPE
        or value["source_kind"] != SOURCE_KIND
    ):
        raise ValueError("Unsupported fiducial catalog precision observation")
    _text(value["domain_id"], "domain_id")
    if value["device"] not in {"keyboard", "phone"}:
        raise ValueError("observation device must be keyboard or phone")
    required = value["required_target_ids"]
    rows = value["targets"]
    if (
        not isinstance(required, list)
        or not required
        or len(set(required)) != len(required)
        or any(not isinstance(item, str) or not item for item in required)
        or not isinstance(rows, list)
        or [row.get("target_id") if isinstance(row, Mapping) else None for row in rows]
        != required
    ):
        raise ValueError("observation target rows must exactly preserve required target order")
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "target_id", "center_board_mm", "safe_rectangle_board_mm", "source_state"
        }:
            raise ValueError("Invalid target row")
        for key, length in (("center_board_mm", 3), ("safe_rectangle_board_mm", 4)):
            numbers = row[key]
            if (
                not isinstance(numbers, list)
                or len(numbers) != length
                or any(type(item) not in (int, float) or not math.isfinite(item) for item in numbers)
            ):
                raise ValueError(f"Invalid target {key}")
    _digest(value["pose_observation_sha256"], "pose_observation_sha256")
    frame = value["frame"]
    if not isinstance(frame, Mapping) or set(frame) != {
        "capture_id", "image_sha256", "host_complete_ns", "host_clock", "camera_settings_sha256"
    }:
        raise ValueError("Invalid frame binding")
    _text(frame["capture_id"], "capture_id")
    _text(frame["host_clock"], "host_clock")
    _digest(frame["image_sha256"], "image_sha256")
    _digest(frame["camera_settings_sha256"], "camera_settings_sha256")
    if isinstance(frame["host_complete_ns"], bool) or not isinstance(frame["host_complete_ns"], int):
        raise ValueError("host_complete_ns must be an integer")
    source_hashes = value["source_hashes"]
    if not isinstance(source_hashes, Mapping) or set(source_hashes) != {
        "camera_intrinsics_sha256", "tag_map_sha256", "target_catalog_sha256",
        "board_frame_definition_sha256",
    }:
        raise ValueError("Invalid source hash binding")
    for key, digest in source_hashes.items():
        _digest(digest, key)
    fit = value["fit"]
    if not isinstance(fit, Mapping) or set(fit) != {"used_tag_ids", "inlier_rmse_px"}:
        raise ValueError("Invalid fit summary")
    if (
        not isinstance(fit["used_tag_ids"], list)
        or not fit["used_tag_ids"]
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in fit["used_tag_ids"])
        or len(set(fit["used_tag_ids"])) != len(fit["used_tag_ids"])
        or type(fit["inlier_rmse_px"]) not in (int, float)
        or not math.isfinite(fit["inlier_rmse_px"])
        or fit["inlier_rmse_px"] < 0
    ):
        raise ValueError("Invalid fit values")
    qualification_sha256 = value["qualification_sha256"]
    if qualification_sha256 is not None:
        _digest(qualification_sha256, "qualification_sha256")
    reasons = value["abstain_reasons"]
    if (
        not isinstance(value["abstain"], bool)
        or not isinstance(reasons, list)
        or any(not isinstance(item, str) or not item for item in reasons)
        or len(set(reasons)) != len(reasons)
        or value["abstain"] is not bool(reasons)
    ):
        raise ValueError("Abstention fields are inconsistent")
    coverage = value["coverage_probability"]
    error = value["conservative_planar_error_bound_mm"]
    if qualification_sha256 is None:
        if coverage is not None or error is not None or "localization_uncalibrated" not in reasons:
            raise ValueError("Unqualified observation must abstain as localization_uncalibrated")
    elif (
        type(coverage) not in (int, float)
        or not 0.95 <= coverage < 1.0
        or type(error) not in (int, float)
        or not 0.0 < error <= 100.0
    ):
        raise ValueError("Qualified observation bounds are invalid")
    if value["authority"] != {
        "physical_authority": "NONE",
        "physical_commands_generated": 0,
        "can_authorize_motion": False,
        "can_release_physical_gates": False,
    }:
        raise ValueError("Observation must declare exactly zero physical authority")
    unsigned = {key: item for key, item in value.items() if key != "observation_sha256"}
    if value["observation_sha256"] != canonical_hash(unsigned):
        raise ValueError("Fiducial catalog precision observation hash mismatch")
    return value


def _target_rows(
    catalog: NominalTargetCatalog,
    device: str,
    target_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target_id in target_ids:
        target = catalog.resolve(device, target_id)
        rows.append(
            {
                "target_id": target_id,
                "center_board_mm": [target.center.x, target.center.y, target.center.z],
                "safe_rectangle_board_mm": list(target.safe_rectangle_board_mm),
                "source_state": target.source_state,
            }
        )
    return rows


def adapt_fiducial_catalog_precision_v1(
    observation: AprilTagPoseObservation,
    catalog: NominalTargetCatalog,
    *,
    device: str,
    required_target_ids: Sequence[str],
    domain_id: str,
    board_frame_definition_sha256: str,
    trusted_qualifications: Mapping[str, Mapping[str, Any]],
    qualification_sha256: str | None,
    current_host_ns: int,
    maximum_age_ns: int,
) -> dict[str, Any]:
    """Bind a pose observation to catalog targets or return an abstention.

    Applicability failures become explicit abstentions.  Malformed records and
    qualifications raise instead of being normalized or partially accepted.
    """

    if not isinstance(observation, AprilTagPoseObservation):
        raise TypeError("observation must be an AprilTagPoseObservation")
    if not isinstance(catalog, NominalTargetCatalog):
        raise TypeError("catalog must be a NominalTargetCatalog")
    if device not in {"keyboard", "phone"}:
        raise ValueError("device must be keyboard or phone")
    domain_id = _text(domain_id, "domain_id")
    board_frame_definition_sha256 = _digest(
        board_frame_definition_sha256, "board_frame_definition_sha256"
    )
    targets = tuple(required_target_ids)
    if (
        not targets
        or len(targets) > 256
        or any(not isinstance(item, str) or not item for item in targets)
        or len(set(targets)) != len(targets)
    ):
        raise ValueError("required_target_ids must be a non-empty unique sequence")
    target_rows = _target_rows(catalog, device, targets)
    if isinstance(current_host_ns, bool) or not isinstance(current_host_ns, int):
        raise ValueError("current_host_ns must be an integer")
    if isinstance(maximum_age_ns, bool) or not isinstance(maximum_age_ns, int) or maximum_age_ns <= 0:
        raise ValueError("maximum_age_ns must be a positive integer")

    frame = observation.detection_batch.frame
    detector = observation.detection_batch.detector
    estimator = observation.estimator
    reasons: list[str] = []
    qualification: Mapping[str, Any] | None = None
    if qualification_sha256 is None or qualification_sha256 not in trusted_qualifications:
        reasons.append("localization_uncalibrated")
    else:
        _digest(qualification_sha256, "qualification_sha256")
        qualification = validate_qualification(trusted_qualifications[qualification_sha256])
        if qualification["qualification_sha256"] != qualification_sha256:
            raise ValueError("Trusted qualification lookup key does not match its content")
        checks = (
            (qualification["domain_id"] == domain_id, "wrong_domain"),
            (qualification["device"] == device, "wrong_device"),
            (qualification["detector_configuration_sha256"] == detector.configuration_sha256, "wrong_detector"),
            (qualification["detector_implementation_sha256"] == detector.implementation_sha256, "wrong_detector"),
            (qualification["estimator_configuration_sha256"] == estimator.configuration_sha256, "wrong_estimator"),
            (qualification["estimator_implementation_sha256"] == estimator.implementation_sha256, "wrong_estimator"),
            (qualification["camera_intrinsics_sha256"] == observation.camera_intrinsics_sha256, "wrong_camera_intrinsics"),
            (qualification["camera_settings_sha256"] == frame.settings_sha256, "wrong_camera_settings"),
            (qualification["tag_map_sha256"] == observation.tag_map_sha256, "wrong_tag_map"),
            (qualification["target_catalog_sha256"] == catalog.content_sha256, "wrong_target_catalog"),
            (qualification["board_frame_definition_sha256"] == board_frame_definition_sha256, "wrong_board_frame"),
            (qualification["camera_frame"] == observation.pose.parent_frame, "wrong_camera_frame"),
            (qualification["board_frame"] == observation.pose.child_frame, "wrong_board_frame"),
            (set(targets).issubset(set(qualification["covered_target_ids"])), "uncovered_target"),
            (len(observation.used_tags) >= qualification["minimum_inlier_tags"], "insufficient_inlier_tags"),
            (observation.inlier_rmse_px <= qualification["maximum_inlier_rmse_px"], "reprojection_residual_exceeded"),
        )
        for passed, reason in checks:
            if not passed and reason not in reasons:
                reasons.append(reason)
        age_ns = current_host_ns - frame.host_complete_ns
        if current_host_ns < frame.host_complete_ns or age_ns > maximum_age_ns:
            reasons.append("stale_evidence")

    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "source_kind": SOURCE_KIND,
        "domain_id": domain_id,
        "device": device,
        "required_target_ids": list(targets),
        "targets": target_rows,
        "pose_observation_sha256": observation.content_hash,
        "frame": {
            "capture_id": frame.capture_id,
            "image_sha256": frame.jpeg_sha256,
            "host_complete_ns": frame.host_complete_ns,
            "host_clock": frame.host_clock,
            "camera_settings_sha256": frame.settings_sha256,
        },
        "source_hashes": {
            "camera_intrinsics_sha256": observation.camera_intrinsics_sha256,
            "tag_map_sha256": observation.tag_map_sha256,
            "target_catalog_sha256": catalog.content_sha256,
            "board_frame_definition_sha256": board_frame_definition_sha256,
        },
        "fit": {
            "used_tag_ids": [tag.tag_id for tag in observation.used_tags],
            "inlier_rmse_px": observation.inlier_rmse_px,
        },
        "qualification_sha256": None if qualification is None else qualification_sha256,
        "coverage_probability": None if qualification is None else qualification["coverage_probability"],
        "conservative_planar_error_bound_mm": (
            None if qualification is None else qualification["conservative_planar_error_bound_mm"]
        ),
        "abstain": bool(reasons),
        "abstain_reasons": reasons,
        "authority": {
            "physical_authority": "NONE",
            "physical_commands_generated": 0,
            "can_authorize_motion": False,
            "can_release_physical_gates": False,
        },
    }
    result = {**core, "observation_sha256": canonical_hash(core)}
    validate_observation(result)
    return result


__all__ = [
    "QUALIFICATION_SCHEMA",
    "SCHEMA",
    "SCOPE",
    "adapt_fiducial_catalog_precision_v1",
    "build_qualification",
    "validate_observation",
    "validate_qualification",
]
