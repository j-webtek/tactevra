"""Admit one camera observation and one calibrated arm snapshot for fusion."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any, Mapping

from rocell.calibration.position_vector_campaign import canonical_sha256

from .calibrated_position_vector_state_snapshot_read_admission import (
    SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA,
)


FUSION_ADMISSION_SCHEMA = "rocell.camera_feedback_state_fusion_admission.v1"
FUSION_ADMISSION_RECEIPT_SCHEMA = (
    "rocell.camera_feedback_state_fusion_admission_receipt.v1"
)
CAMERA_OBSERVATION_SCHEMA = "rocell.fixed_camera_board_pose_observation.v1"
BOARD_REGISTRATION_SCHEMA = (
    "rocell.fixed_camera_keyboard_board_registration.v1"
)
MAX_CAMERA_STATE_SKEW_SECONDS = 2
MAX_FUSION_LIFETIME_SECONDS = 30

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ADMISSION_FIELDS = frozenset(
    {
        "schema", "fusion_consumer_id", "fusion_context_sha256",
        "snapshot_read_receipt_sha256", "camera_observation_sha256",
        "camera_calibration_sha256", "board_registration_sha256",
        "attachment_profile", "camera_observed_at", "fused_at",
        "valid_until", "maximum_camera_state_skew_seconds",
        "maximum_fusion_lifetime_seconds",
    }
)


class CameraFeedbackStateFusionAdmissionError(ValueError):
    """Camera and calibrated state evidence is ineligible for fusion."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CameraFeedbackStateFusionAdmissionError(message)


def _mapping(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return dict(value)  # type: ignore[arg-type]


def _identifier(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None,
        f"{label} is not a bounded identifier",
    )
    return value


def _digest(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _DIGEST.fullmatch(value) is not None,
        f"{label} is not a lowercase SHA-256",
    )
    return value


def _timestamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CameraFeedbackStateFusionAdmissionError(
            f"{label} is invalid"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    _require(
        snapshot.get("schema") == SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA
        and snapshot.get("status") == "CALIBRATED_STATE_SNAPSHOT_READ_ADMITTED"
        and snapshot.get("next_required_gate")
        == "CAMERA_FEEDBACK_STATE_FUSION_ADMISSION"
        and snapshot.get("calibrated_state_snapshot_read_admitted") is True
        and snapshot.get("named_reader_snapshot_use_authorized") is True,
        "calibrated state snapshot is not eligible for camera fusion",
    )
    _require(
        snapshot.get("automatic_retry_allowed") is False
        and snapshot.get("motion_authorized") is False
        and snapshot.get("physical_authority") is False,
        "calibrated state snapshot authority is invalid",
    )
    _identifier(snapshot.get("reader_id"), "snapshot reader_id")
    _identifier(snapshot.get("attachment_profile"), "snapshot attachment_profile")
    _digest(snapshot.get("reader_context_sha256"), "snapshot reader context")
    _require(
        isinstance(snapshot.get("calibrated_feedback"), Mapping),
        "calibrated feedback must be an object",
    )


def _validate_observation(observation: Mapping[str, Any]) -> tuple[str, str]:
    _require(
        observation.get("schema") == CAMERA_OBSERVATION_SCHEMA,
        "camera observation schema is invalid",
    )
    quality = _mapping(observation.get("quality"), "camera observation quality")
    authority = _mapping(
        observation.get("authority"), "camera observation authority"
    )
    sources = _mapping(
        observation.get("source_hashes"), "camera observation source hashes"
    )
    _require(quality.get("passed") is True, "camera observation quality failed")
    _require(
        authority.get("physical_authority") == "NONE"
        and authority.get("physical_commands_generated") == 0
        and authority.get("can_authorize_motion") is False
        and authority.get("can_release_physical_gates") is False,
        "camera observation authority is invalid",
    )
    return (
        _digest(sources.get("camera_intrinsics_sha256"), "camera intrinsics"),
        _digest(sources.get("tag_map_sha256"), "camera tag map"),
    )


def _validate_camera_calibration(
    calibration: Mapping[str, Any], *, intrinsics_sha256: str,
    tag_map_sha256: str, board_registration_sha256: str,
) -> None:
    _require(
        calibration.get("schema") == "rocell.camera_fusion_calibration_binding.v1"
        and calibration.get("status") == "CAMERA_FUSION_CALIBRATION_READY"
        and calibration.get("safe_for_runtime_observation_fusion") is True
        and calibration.get("motion_authorized") is False,
        "camera calibration is not eligible for fusion",
    )
    _require(
        calibration.get("camera_intrinsics_sha256") == intrinsics_sha256,
        "camera observation and calibration intrinsics differ",
    )
    _require(
        calibration.get("tag_map_sha256") == tag_map_sha256,
        "camera observation and calibration tag map differ",
    )
    _require(
        calibration.get("board_registration_sha256")
        == board_registration_sha256,
        "camera calibration and board registration differ",
    )


def _validate_board_registration(
    registration: Mapping[str, Any], *, tag_map_sha256: str,
    attachment_profile: str,
) -> None:
    _require(
        registration.get("schema") == BOARD_REGISTRATION_SCHEMA
        and registration.get("status")
        == "ABSOLUTE_KEYBOARD_TO_BOARD_LOCALIZATION_READY"
        and registration.get("absolute_keyboard_to_board_transform_verified")
        is True
        and registration.get("board_space_key_candidates_emitted") is True,
        "board registration is not ready for fusion",
    )
    _require(
        registration.get("profile") == attachment_profile,
        "board registration attachment profile differs",
    )
    _require(
        registration.get("motion_targets_emitted") is False
        and registration.get("motion_authorized") is False
        and registration.get("contact_authorized") is False,
        "board registration authority is invalid",
    )


def admit_camera_feedback_state_fusion(
    *,
    snapshot_read_receipt_document: Mapping[str, Any],
    camera_observation_document: Mapping[str, Any],
    camera_calibration_document: Mapping[str, Any],
    board_registration_document: Mapping[str, Any],
    admission_document: Mapping[str, Any],
    fusion_context_document: Mapping[str, Any],
    current_attachment_profile: str,
) -> dict[str, Any]:
    """Bind one qualified camera observation to one calibrated state snapshot."""

    snapshot = _mapping(snapshot_read_receipt_document, "snapshot read receipt")
    observation = _mapping(camera_observation_document, "camera observation")
    calibration = _mapping(camera_calibration_document, "camera calibration")
    registration = _mapping(board_registration_document, "board registration")
    admission = _mapping(admission_document, "fusion admission")
    context = _mapping(fusion_context_document, "fusion context")
    _require(
        set(admission) == _ADMISSION_FIELDS,
        "fusion admission fields do not match the contract",
    )
    _require(
        admission["schema"] == FUSION_ADMISSION_SCHEMA,
        "fusion admission schema is invalid",
    )

    _validate_snapshot(snapshot)
    intrinsics_sha, tag_map_sha = _validate_observation(observation)
    _validate_camera_calibration(
        calibration,
        intrinsics_sha256=intrinsics_sha,
        tag_map_sha256=tag_map_sha,
        board_registration_sha256=canonical_sha256(registration),
    )
    _identifier(current_attachment_profile, "current_attachment_profile")
    _validate_board_registration(
        registration,
        tag_map_sha256=tag_map_sha,
        attachment_profile=current_attachment_profile,
    )

    consumer_id = _identifier(admission["fusion_consumer_id"], "fusion_consumer_id")
    _require(
        context.get("reader_id") == consumer_id
        and snapshot.get("reader_id") == consumer_id,
        "fusion consumer does not own the admitted snapshot",
    )
    context_sha = canonical_sha256(context)
    _require(
        admission["fusion_context_sha256"] == context_sha
        == snapshot.get("reader_context_sha256"),
        "fusion context differs from the snapshot reader context",
    )
    _require(
        admission["attachment_profile"] == current_attachment_profile
        == snapshot.get("attachment_profile"),
        "current attachment profile differs across fusion inputs",
    )

    bindings = (
        ("snapshot_read_receipt_sha256", snapshot),
        ("camera_observation_sha256", observation),
        ("camera_calibration_sha256", calibration),
        ("board_registration_sha256", registration),
    )
    for field, document in bindings:
        _require(
            admission[field] == canonical_sha256(document),
            f"{field} mismatch",
        )

    maximum_skew = admission["maximum_camera_state_skew_seconds"]
    maximum_lifetime = admission["maximum_fusion_lifetime_seconds"]
    _require(
        type(maximum_skew) is int
        and 0 <= maximum_skew <= MAX_CAMERA_STATE_SKEW_SECONDS,
        "maximum camera/state skew is outside the bounded contract",
    )
    _require(
        type(maximum_lifetime) is int
        and 0 < maximum_lifetime <= MAX_FUSION_LIFETIME_SECONDS,
        "maximum fusion lifetime is outside the bounded contract",
    )
    state_time = _timestamp(snapshot.get("executed_at"), "state executed_at")
    observed = _timestamp(admission["camera_observed_at"], "camera_observed_at")
    fused = _timestamp(admission["fused_at"], "fused_at")
    valid_until = _timestamp(admission["valid_until"], "valid_until")
    snapshot_valid_until = _timestamp(
        snapshot.get("valid_until"), "snapshot valid_until"
    )
    _require(
        abs((observed - state_time).total_seconds()) <= maximum_skew,
        "camera observation and calibrated state exceed the admitted skew",
    )
    _require(
        state_time <= fused and observed <= fused < valid_until,
        "fusion timestamp ordering is invalid",
    )
    _require(
        valid_until <= fused + timedelta(seconds=maximum_lifetime)
        and valid_until <= snapshot_valid_until,
        "fusion validity exceeds a source lifetime",
    )

    basis = {
        "snapshot_read_receipt_sha256": admission[
            "snapshot_read_receipt_sha256"
        ],
        "camera_observation_sha256": admission["camera_observation_sha256"],
        "camera_calibration_sha256": admission["camera_calibration_sha256"],
        "board_registration_sha256": admission["board_registration_sha256"],
        "fusion_consumer_id": consumer_id,
        "fusion_context_sha256": context_sha,
    }
    return {
        "schema": FUSION_ADMISSION_RECEIPT_SCHEMA,
        "status": "CAMERA_FEEDBACK_STATE_FUSION_ADMITTED",
        "fusion_id": f"camera-state-fusion:{canonical_sha256(basis)}",
        "fusion_consumer_id": consumer_id,
        "fusion_context_sha256": context_sha,
        "snapshot_id": snapshot["snapshot_id"],
        "attachment_profile": current_attachment_profile,
        "camera_observed_at": admission["camera_observed_at"],
        "state_executed_at": snapshot["executed_at"],
        "fused_at": admission["fused_at"],
        "valid_until": admission["valid_until"],
        **{field: admission[field] for field, _ in bindings},
        "camera_intrinsics_sha256": intrinsics_sha,
        "tag_map_sha256": tag_map_sha,
        "calibrated_feedback": dict(snapshot["calibrated_feedback"]),
        "camera_observation": dict(observation),
        "next_required_gate": "FUSED_CAMERA_STATE_PLANNING_ADMISSION",
        "limitations": [
            "This receipt binds observation and state evidence for read-only planning intake.",
            "It does not infer unobserved geometry or certify physical clearance.",
            "A separate planning admission must validate targets and trajectories.",
            "Fusion admission grants no retry, motion, contact, or physical authority.",
        ],
        "camera_feedback_state_fusion_admitted": True,
        "planning_authorized": False,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }


__all__ = [
    "BOARD_REGISTRATION_SCHEMA",
    "CAMERA_OBSERVATION_SCHEMA",
    "FUSION_ADMISSION_RECEIPT_SCHEMA",
    "FUSION_ADMISSION_SCHEMA",
    "MAX_CAMERA_STATE_SKEW_SECONDS",
    "MAX_FUSION_LIFETIME_SECONDS",
    "CameraFeedbackStateFusionAdmissionError",
    "admit_camera_feedback_state_fusion",
]
