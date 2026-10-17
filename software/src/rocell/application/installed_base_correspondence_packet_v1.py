"""Precommit and fit position correspondences for the installed robot base.

The packet joins simultaneous controller feedback and board observations while
keeping collection, fitting, and physical acceptance separate.  The fitter is
offline and returns a position-only candidate with zero physical authority.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from rocell.calibration.rigid_correspondence import (
    CorrespondenceOrigin,
    DEFAULT_RIGID_CORRESPONDENCE_POLICY,
    RigidCorrespondenceInput,
    RigidPointPair,
    fit_rigid_correspondence,
)
from rocell.models.frames import Point3Mm


SCHEMA = "rocell.installed_base_correspondence_packet.v1"
PENDING_STATUS = "BLOCKED_PREREQUISITES_THEN_CORRESPONDENCE_COLLECTION"
COLLECTING_STATUS = "CORRESPONDENCE_COLLECTION_IN_PROGRESS"
PREREQUISITE_BLOCKED_FIT_STATUS = "BLOCKED_PREREQUISITES_BEFORE_OFFLINE_FIT"
READY_STATUS = "READY_FOR_OFFLINE_POSITION_FIT"
CANDIDATE_STATUS = "POSITION_CANDIDATE_ONLY_ORIENTATION_AND_RESEAT_PENDING"
FAILED_STATUS = "POSITION_DIAGNOSTIC_FAILED"
_HASH = re.compile(r"[0-9a-f]{64}\Z")

_SLOT_ROWS = (
    ("train-front-left-low", "TRAINING", "FRONT_LEFT", "LOW"),
    ("train-front-right-low", "TRAINING", "FRONT_RIGHT", "LOW"),
    ("train-rear-left-low", "TRAINING", "REAR_LEFT", "LOW"),
    ("train-rear-right-low", "TRAINING", "REAR_RIGHT", "LOW"),
    ("train-center-left-high", "TRAINING", "CENTER_LEFT", "HIGH"),
    ("train-center-right-high", "TRAINING", "CENTER_RIGHT", "HIGH"),
    ("heldout-center-front", "HELD_OUT", "CENTER_FRONT", "HELD_OUT"),
    ("heldout-center-rear", "HELD_OUT", "CENTER_REAR", "HELD_OUT"),
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_bound_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("installed base intake file hash mismatch")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("installed base intake must be a JSON object")
    unsigned = {key: item for key, item in value.items() if key != "content_sha256"}
    if value.get("content_sha256") != _sha(unsigned):
        raise ValueError("installed base intake content hash mismatch")
    return value


def _validate_packet_integrity(packet: dict[str, Any]) -> None:
    if packet.get("schema") != SCHEMA:
        raise ValueError("unsupported correspondence packet schema")
    unsigned = {key: value for key, value in packet.items() if key != "content_sha256"}
    if packet.get("content_sha256") != _sha(unsigned):
        raise ValueError("correspondence packet content hash mismatch")
    slots = packet.get("precommitted_split", {}).get("slots", [])
    actual_split = [(row.get("slot_id"), row.get("split")) for row in slots]
    expected_split = [(row[0], row[1]) for row in _SLOT_ROWS]
    if actual_split != expected_split:
        raise ValueError("precommitted split must remain six training and two held out")


def _point_values(value: object, name: str) -> list[float]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or abs(item) > 10_000.0
            for item in value
        )
    ):
        raise ValueError(f"{name} must contain three finite millimetre values")
    return [float(item) for item in value]


def record_installed_base_correspondence_sample_v1(
    packet: dict[str, Any],
    *,
    slot_id: str,
    pose_label: str,
    base_point_xyz_mm: object,
    board_point_xyz_mm: object,
    controller_feedback_sha256: str,
    base_point_derivation_sha256: str,
    camera_observation_sha256: str,
    board_point_measurement_sha256: str,
    captured_at_utc: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Record one immutable synchronized sample without touching hardware."""

    _validate_packet_integrity(packet)
    if not isinstance(slot_id, str) or not slot_id:
        raise ValueError("slot_id is required")
    if (
        not isinstance(pose_label, str)
        or not pose_label.strip()
        or len(pose_label) > 128
    ):
        raise ValueError("pose_label must be bounded non-empty text")
    if not isinstance(captured_at_utc, str) or not captured_at_utc.endswith("Z"):
        raise ValueError("captured_at_utc must be an ISO-8601 UTC timestamp")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 512):
        raise ValueError("notes must be null or bounded text")
    evidence = {
        "controller_feedback_sha256": controller_feedback_sha256,
        "base_point_derivation_sha256": base_point_derivation_sha256,
        "camera_observation_sha256": camera_observation_sha256,
        "board_point_measurement_sha256": board_point_measurement_sha256,
    }
    for name, digest in evidence.items():
        if not isinstance(digest, str) or not _HASH.fullmatch(digest) or digest == "0" * 64:
            raise ValueError(f"{name} must be a nonzero lowercase SHA-256 digest")

    updated = json.loads(json.dumps(packet, allow_nan=False))
    slots = updated["precommitted_split"]["slots"]
    matching = [row for row in slots if row["slot_id"] == slot_id]
    if len(matching) != 1:
        raise ValueError("slot_id is not in the precommitted split")
    row = matching[0]
    if row["status"] != "PENDING":
        raise ValueError(f"correspondence slot {slot_id} is already recorded")
    row.update(
        status="MEASURED",
        pose_label=pose_label.strip(),
        base_point_xyz_mm=_point_values(base_point_xyz_mm, "base_point_xyz_mm"),
        board_point_xyz_mm=_point_values(board_point_xyz_mm, "board_point_xyz_mm"),
        captured_at_utc=captured_at_utc,
        notes=notes,
        **evidence,
    )
    measured = sum(item["status"] == "MEASURED" for item in slots)
    if measured < len(slots):
        updated["status"] = COLLECTING_STATUS
    elif all(
        value == "ACCEPTED_PHYSICAL_ARTIFACT"
        for value in updated["prerequisite_status"].values()
    ):
        updated["status"] = READY_STATUS
    else:
        updated["status"] = PREREQUISITE_BLOCKED_FIT_STATUS
    unsigned = {key: value for key, value in updated.items() if key != "content_sha256"}
    updated["content_sha256"] = _sha(unsigned)
    return updated


def build_pending_installed_base_correspondence_packet_v1(
    intake_path: Path,
    intake_file_sha256: str,
    *,
    packet_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    """Create the precommitted collection split from one exact intake."""

    if not packet_id or not created_at_utc.endswith("Z"):
        raise ValueError("packet id and ISO-8601 UTC timestamp are required")
    intake = _load_bound_json(intake_path, intake_file_sha256)
    retained = intake["retained_context"]
    target = intake["target_artifact"]
    historical_path = [
        "KEYBOARD_FIELD_APPROACH_25",
        "KEYBOARD_FIELD_APPROACH_20",
        "KEYBOARD_FIELD_APPROACH_10",
        "KEYBOARD_FIELD_CAL_3",
        "KEYBOARD_DIAGONAL_CAL_2",
        "KEYBOARD_FORWARD_CAL_1",
    ]
    slots = []
    for slot_id, split, region, height_class in _SLOT_ROWS:
        slots.append(
            {
                "slot_id": slot_id,
                "split": split,
                "required_board_region": region,
                "required_height_class": height_class,
                "status": "PENDING",
                "pose_label": None,
                "base_point_xyz_mm": None,
                "board_point_xyz_mm": None,
                "controller_feedback_sha256": None,
                "base_point_derivation_sha256": None,
                "camera_observation_sha256": None,
                "board_point_measurement_sha256": None,
                "captured_at_utc": None,
                "attachment_profile_id": retained["attachment_profile_id"],
                "workcell_epoch_id": retained["workcell_epoch_id"],
                "notes": None,
            }
        )
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "packet_id": packet_id,
        "created_at_utc": created_at_utc,
        "status": PENDING_STATUS,
        "intake_binding": {
            "path": intake_path.as_posix(),
            "file_sha256": intake_file_sha256,
            "content_sha256": intake["content_sha256"],
            "intake_id": intake["intake_id"],
        },
        "transform_contract": {
            "target_frame": "B",
            "source_frame": "base_link",
            "units": "mm",
            "candidate_kind": "POSITION_ONLY_PROPER_RIGID_TRANSFORM",
            "physical_acceptance_artifact": target["artifact_id"],
        },
        "prerequisite_status": target["prerequisite_status"],
        "fixed_context": {
            "workcell_epoch_id": retained["workcell_epoch_id"],
            "attachment_profile": retained["attachment_profile"],
            "attachment_profile_id": retained["attachment_profile_id"],
            "board_size_xy_mm": retained["board_size_xy_mm"],
            "installed_tag_centers_xy_mm": retained["installed_tag_centers_xy_mm"],
            "neutral_observation_pose": retained["neutral_observation_pose"],
            "neutral_observation_servo_positions": retained[
                "neutral_observation_servo_positions"
            ],
        },
        "retained_pose_labels_for_collection_planning_only": historical_path,
        "retained_pose_reuse_rule": (
            "A retained label is a collection-planning candidate only. Each slot "
            "requires fresh synchronized feedback and camera evidence in this epoch."
        ),
        "precommitted_split": {
            "training_slot_count": 6,
            "held_out_slot_count": 2,
            "held_out_used_for_fit": False,
            "slots": slots,
        },
        "collection_requirements": [
            "accept all phase1_arm_board prerequisite artifacts",
            "keep board, arm base, camera support, tags, and attachment fixed",
            "record one immutable controller feedback receipt per slot",
            "bind the base_link witness-point derivation from accepted controller correlation",
            "record one immutable camera observation receipt per slot",
            "bind the board-frame witness-point measurement derived from that observation",
            "bind the same timestamp, workcell epoch, and attachment profile",
            "measure the same rigid witness point in base_link and board frames",
            "preserve the precommitted training and held-out split",
            "include at least three board regions and two height classes",
        ],
        "solver_policy": {
            "minimum_training_points": 6,
            "minimum_held_out_points": 2,
            "maximum_points": 8,
            "proper_rigid_transform_only": True,
            "scale_or_shear_fit_allowed": False,
        },
        "remaining_after_position_fit": [
            "orientation-diverse pose validation",
            "held-out orientation residuals",
            "installed base and clamp envelope plus uncertainty",
            "at least two reseat repeatability trials",
            "reviewed physical acceptance thresholds",
        ],
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "content_sha256": _sha(core)}


def _completed_input(packet: dict[str, Any]) -> RigidCorrespondenceInput:
    _validate_packet_integrity(packet)
    if any(
        value != "ACCEPTED_PHYSICAL_ARTIFACT"
        for value in packet["prerequisite_status"].values()
    ):
        raise ValueError("phase1_arm_board prerequisites are not accepted")

    fixed = packet["fixed_context"]
    slots = packet["precommitted_split"]["slots"]
    training: list[RigidPointPair] = []
    held_out: list[RigidPointPair] = []
    for row in slots:
        if row.get("status") != "MEASURED":
            raise ValueError(f"correspondence slot {row.get('slot_id')} is incomplete")
        if (
            row.get("attachment_profile_id") != fixed["attachment_profile_id"]
            or row.get("workcell_epoch_id") != fixed["workcell_epoch_id"]
        ):
            raise ValueError("slot epoch or attachment binding mismatch")
        for name in (
            "pose_label",
            "controller_feedback_sha256",
            "base_point_derivation_sha256",
            "camera_observation_sha256",
            "board_point_measurement_sha256",
            "captured_at_utc",
        ):
            if not row.get(name):
                raise ValueError(f"slot {row['slot_id']} missing {name}")
        for name in (
            "controller_feedback_sha256",
            "base_point_derivation_sha256",
            "camera_observation_sha256",
            "board_point_measurement_sha256",
        ):
            if not _HASH.fullmatch(row[name]) or row[name] == "0" * 64:
                raise ValueError(f"slot {row['slot_id']} has invalid {name}")
        if not row["captured_at_utc"].endswith("Z"):
            raise ValueError(f"slot {row['slot_id']} timestamp is not UTC")
        pair = RigidPointPair(
            row["slot_id"],
            Point3Mm("base_link", *row["base_point_xyz_mm"]),
            Point3Mm("B", *row["board_point_xyz_mm"]),
        )
        (training if row["split"] == "TRAINING" else held_out).append(pair)
    if len(training) != 6 or len(held_out) != 2:
        raise ValueError("precommitted split must remain six training and two held out")
    return RigidCorrespondenceInput(
        packet["packet_id"],
        "base_link",
        "B",
        tuple(training),
        tuple(held_out),
        packet["intake_binding"]["file_sha256"],
        packet["content_sha256"],
        CorrespondenceOrigin.UNVERIFIED_SUPPLIED_OBSERVATIONS,
    )


def fit_installed_base_position_candidate_v1(packet: dict[str, Any]) -> dict[str, Any]:
    """Fit the precommitted points and retain the remaining physical blockers."""

    data = _completed_input(packet)
    policy = replace(
        DEFAULT_RIGID_CORRESPONDENCE_POLICY,
        minimum_training_points=6,
        minimum_held_out_points=2,
        maximum_points=8,
    )
    result = fit_rigid_correspondence(data, policy=policy)
    fit_report = result.to_dict()
    core = {
        "schema": "rocell.installed_base_position_candidate.v1",
        "status": CANDIDATE_STATUS if result.diagnostic_pass else FAILED_STATUS,
        "packet_id": packet["packet_id"],
        "packet_content_sha256": packet["content_sha256"],
        "rigid_correspondence_report_sha256": result.report_sha256,
        "rigid_correspondence": fit_report,
        "position_diagnostic_pass": result.diagnostic_pass,
        "remaining_requirements": packet["remaining_after_position_fit"],
        "installed_base_transform_complete": False,
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "content_sha256": _sha(core)}


__all__ = [
    "CANDIDATE_STATUS",
    "COLLECTING_STATUS",
    "FAILED_STATUS",
    "PENDING_STATUS",
    "PREREQUISITE_BLOCKED_FIT_STATUS",
    "READY_STATUS",
    "SCHEMA",
    "build_pending_installed_base_correspondence_packet_v1",
    "fit_installed_base_position_candidate_v1",
    "record_installed_base_correspondence_sample_v1",
]
