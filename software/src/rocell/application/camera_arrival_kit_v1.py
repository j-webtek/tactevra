"""Fail-closed PC9 camera-arrival evidence map and synthetic dry run.

The kit describes where physical originals belong and who consumes them.  It
cannot capture an image, populate a measured evidence hash, advance a
configuration epoch, install a qualification, or authorize hardware access.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA = "rocell.camera_arrival_kit.v1"
STATUS = "BLOCKED_AWAITING_PHYSICAL_ORIGINALS"
EVIDENCE_CLASS = "SYNTHETIC_DRY_RUN_ONLY"
ORIGINAL_SCHEMA = "software/ai/schemas/camera_arrival_original_v1.schema.json"

_SLOT_ROWS = (
    ("camera_receipt", "CAMERA_ORIGINAL", "originals/camera/receipt.json",
     (), ("camera_support_optics_epoch_intake",)),
    ("camera_identity", "CAMERA_ORIGINAL", "originals/camera/identity.json",
     (), ("camera_support_optics_epoch_intake", "capture_service")),
    ("camera_mode_controls", "CAMERA_ORIGINAL",
     "originals/camera/mode-controls.json", (),
     ("camera_support_optics_epoch_intake", "capture_service")),
    ("support_witnesses", "INSTALLATION_ORIGINAL",
     "originals/support/witnesses.json", ("mm",),
     ("camera_support_optics_epoch_intake", "installed_collision_geometry")),
    ("camera_intrinsics", "CALIBRATION_ORIGINAL",
     "calibration/camera-intrinsics.json", ("px",),
     ("localization_campaign", "coordinate_transform_graph")),
    ("camera_to_board_transform", "CALIBRATION_ORIGINAL",
     "calibration/camera-to-board.json", ("mm", "rad"),
     ("localization_evaluator", "coordinate_transform_graph")),
    ("board_to_robot_transform", "CALIBRATION_ORIGINAL",
     "calibration/board-to-robot.json", ("mm", "rad"),
     ("motion_planner", "localization_evaluator")),
    ("keyboard_to_board_transform", "CALIBRATION_ORIGINAL",
     "calibration/keyboard-to-board.json", ("mm", "rad"),
     ("target_resolver", "localization_evaluator")),
    ("tool_to_joint_transform", "CALIBRATION_ORIGINAL",
     "calibration/tool-to-joint.json", ("mm", "rad"),
     ("motion_planner", "installed_collision_geometry")),
    ("installed_geometry", "WORKCELL_ORIGINAL",
     "workcell/installed-geometry.json", ("mm",),
     ("collision_intake", "motion_planner")),
    ("cable_envelope", "WORKCELL_ORIGINAL",
     "workcell/cable-envelope.json", ("mm",),
     ("collision_intake",)),
    ("keyboard_profile", "DEVICE_ORIGINAL",
     "devices/keyboard-profile.json", ("mm",),
     ("target_resolver", "collision_intake")),
    ("tool_profile", "TOOL_ORIGINAL", "tools/tool-profile.json", ("mm",),
     ("motion_planner", "collision_intake", "localization_evaluator")),
    ("localization_campaign", "CAMPAIGN_ORIGINAL",
     "localization/campaign.json", ("px", "mm"),
     ("physical_camera_localization_preflight",)),
    ("localization_evaluation", "EVALUATION_ORIGINAL",
     "localization/evaluation.json", ("mm",),
     ("deployment_qualification_review",)),
)

REQUIRED_SLOT_IDS = tuple(row[0] for row in _SLOT_ROWS)
REVIEW_FIELDS = (
    "reviewer_id", "reviewed_at_utc", "disposition", "review_sha256",
)
STOP_CONDITIONS = (
    "CAMERA_IDENTITY_DRIFT",
    "MODE_OR_CONTROL_DRIFT",
    "SUPPORT_OR_WORKCELL_MOVED",
    "CALIBRATION_ORIGINAL_MISSING",
    "HASH_MISMATCH",
    "UNREVIEWED_OR_REJECTED_ORIGINAL",
    "SPLIT_OR_SESSION_OVERLAP",
    "UNCERTAINTY_EXCEEDS_SAFE_REGION",
    "INSTALLED_GEOMETRY_INCOMPLETE",
)


class CameraArrivalKitV1Error(ValueError):
    """Arrival evidence map is malformed or attempts to imply qualification."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CameraArrivalKitV1Error("value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _slot_template(row: tuple[Any, ...]) -> dict[str, Any]:
    slot_id, artifact_class, destination, units, consumers = row
    template = {
        "artifact_id": slot_id,
        "artifact_class": artifact_class,
        "destination_relative_to_external_evidence_root": destination,
        "schema": ORIGINAL_SCHEMA,
        "required_units": list(units),
        "uncertainty_required": artifact_class in {
            "CALIBRATION_ORIGINAL", "WORKCELL_ORIGINAL", "DEVICE_ORIGINAL",
            "TOOL_ORIGINAL", "EVALUATION_ORIGINAL",
        },
        "review_fields": list(REVIEW_FIELDS),
        "downstream_consumers": list(consumers),
        "physical_original_required": True,
        "measured_evidence_sha256": None,
        "review_disposition": "PENDING_PHYSICAL_ORIGINAL",
    }
    return {**template, "template_sha256": _sha256(template)}


def build_camera_arrival_kit_v1() -> dict[str, Any]:
    """Build the canonical synthetic-only arrival map with blank measured slots."""

    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_class": EVIDENCE_CLASS,
        "external_evidence_root": None,
        "slots": [_slot_template(row) for row in _SLOT_ROWS],
        "required_slot_count": len(_SLOT_ROWS),
        "measured_slot_count": 0,
        "stop_conditions": list(STOP_CONDITIONS),
        "synthetic_dry_run_complete": True,
        "synthetic_may_populate_measured_slots": False,
        "configuration_epoch_advanced": False,
        "deployment_registry_updated": False,
        "qualification_installed": False,
        "camera_opened": False,
        "model_loaded": False,
        "controller_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "arrival_kit_sha256": _sha256(core)}


def validate_camera_arrival_kit_v1(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate exact dry-run semantics and return an immutable shallow view."""

    if not isinstance(value, Mapping):
        raise CameraArrivalKitV1Error("arrival kit must be an object")
    expected = build_camera_arrival_kit_v1()
    if dict(value) != expected:
        raise CameraArrivalKitV1Error(
            "arrival kit differs from the canonical fail-closed dry run")
    return MappingProxyType(dict(value))


__all__ = [
    "EVIDENCE_CLASS", "ORIGINAL_SCHEMA", "REQUIRED_SLOT_IDS", "SCHEMA",
    "STATUS", "STOP_CONDITIONS", "CameraArrivalKitV1Error",
    "build_camera_arrival_kit_v1", "validate_camera_arrival_kit_v1",
]
