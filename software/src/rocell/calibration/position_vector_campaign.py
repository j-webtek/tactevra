"""Offline producer for reviewed T=1051 count-to-joint calibration artifacts.

The campaign consumes retained observations and independent joint truth.  It
does not open a controller, request feedback, or issue motion.  Training and
held-out samples remain disjoint, and an accepted artifact is emitted only
after a separate reviewer accepts the exact dataset and deterministic fit.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.arm.position_vector_calibration import (
    JOINT_ORDER,
    PRIMARY_INDEX,
    PROFILE,
    SCHEMA as ARTIFACT_SCHEMA,
    SERVO_ORDER,
    load_position_vector_calibration,
)


DATASET_SCHEMA = "rocell.position_vector_calibration_dataset.v1"
FIT_REPORT_SCHEMA = "rocell.position_vector_calibration_fit_report.v1"
REVIEW_SCHEMA = "rocell.position_vector_calibration_review.v1"
PLAN_SCHEMA = "rocell.position_vector_calibration_collection_plan.v1"
OBSERVATIONS_SCHEMA = "rocell.position_vector_calibration_observations.v1"
READINESS_SCHEMA = "rocell.position_vector_calibration_collection_readiness.v1"
PREPARATION_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_preparation_receipt.v1"
)
READINESS_EVIDENCE_SCHEMA = "rocell.position_vector_calibration_readiness_evidence.v1"
READINESS_EVIDENCE_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_readiness_evidence_receipt.v1"
)
CANDIDATE_INVENTORY_SCHEMA = (
    "rocell.position_vector_calibration_candidate_inventory.v1"
)
CANDIDATE_COVERAGE_SCHEMA = (
    "rocell.position_vector_calibration_candidate_coverage.v1"
)
CANDIDATE_AUGMENTATION_SCHEMA = (
    "rocell.position_vector_calibration_candidate_augmentation.v1"
)
CANDIDATE_PROPOSAL_SCHEMA = (
    "rocell.position_vector_calibration_candidate_proposal.v1"
)
CANDIDATE_PREFLIGHT_SCHEMA = (
    "rocell.position_vector_calibration_candidate_preflight.v1"
)
CANDIDATE_QUALIFICATION_PLAN_SCHEMA = (
    "rocell.position_vector_calibration_candidate_qualification_plan.v1"
)
CANDIDATE_QUALIFICATION_EVIDENCE_SCHEMA = (
    "rocell.position_vector_calibration_candidate_qualification_evidence.v1"
)
CANDIDATE_QUALIFICATION_ASSESSMENT_SCHEMA = (
    "rocell.position_vector_calibration_candidate_qualification_assessment.v1"
)
CANDIDATE_QUALIFICATION_HANDOFF_SCHEMA = (
    "rocell.position_vector_calibration_candidate_qualification_handoff.v1"
)
CANDIDATE_INVENTORY_ADMISSION_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_candidate_inventory_admission_receipt.v1"
)
CANDIDATE_TRAINING_SPLIT_PLAN_SCHEMA = (
    "rocell.position_vector_calibration_candidate_training_split_plan.v1"
)
QUALIFIED_COLLECTION_PREPARATION_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_qualified_collection_preparation_receipt.v1"
)
QUALIFIED_COLLECTION_READINESS_PLAN_SCHEMA = (
    "rocell.position_vector_calibration_qualified_collection_readiness_plan.v1"
)
QUALIFIED_COLLECTION_READINESS_EVIDENCE_SCHEMA = (
    "rocell.position_vector_calibration_qualified_collection_readiness_evidence.v1"
)
QUALIFIED_COLLECTION_READINESS_ASSESSMENT_SCHEMA = (
    "rocell.position_vector_calibration_qualified_collection_readiness_assessment.v1"
)
QUALIFIED_COLLECTION_READINESS_HANDOFF_SCHEMA = (
    "rocell.position_vector_calibration_qualified_collection_readiness_handoff.v1"
)
QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_SCHEMA = (
    "rocell.position_vector_calibration_qualified_stationary_observation_evidence.v1"
)
QUALIFIED_STATIONARY_OBSERVATION_INGESTION_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_qualified_stationary_observation_ingestion_receipt.v1"
)
REVIEWED_PREPARATION_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_reviewed_preparation_receipt.v1"
)
REVIEWED_COMPILATION_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_reviewed_compilation_receipt.v1"
)
SUPPORTED_ATTACHMENTS = ("no_attachment", "stylus_attachment")
TRUTH_METHODS = (
    "encoder_reference_fixture",
    "link_fiducial_pose",
    "manufacturer_traceable_fixture",
    "mechanical_angle_fixture",
)
_QUALIFIED_COLLECTION_READINESS_REQUIREMENTS = (
    ("INSTALLED_FIRMWARE_BINDING", "controller"),
    ("FIXED_CAMERA_INTRINSICS", "camera"),
    ("CAMERA_TO_BOARD_REGISTRATION", "camera_board"),
    ("BOARD_GEOMETRY", "board"),
    ("ATTACHMENT_PROFILE_GEOMETRY", "attachment"),
    ("COLLECTION_COLLISION_ENVELOPE", "workspace"),
    ("INDEPENDENT_TRUTH_PROCEDURES", "pose_catalog"),
    ("COLLECTION_OPERATOR_REVIEW", "campaign"),
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_HEX4 = re.compile(r"^[0-9a-f]{4}$")
_CONTROLLER_FIELDS = frozenset({"vid", "pid", "unit_serial", "firmware_sha256"})
_CANDIDATE_PROPOSAL_FIELDS = frozenset(
    {
        "schema", "inventory_sha256", "label", "attachment_profile",
        "raw_position_counts", "source_ref",
    }
)
_CANDIDATE_QUALIFICATION_EVIDENCE_FIELDS = frozenset(
    {
        "schema", "qualification_plan_sha256", "inventory_sha256",
        "candidate_sha256", "attachment_profile", "producer_id", "evidence",
    }
)
_CANDIDATE_QUALIFICATION_EVIDENCE_ITEM_FIELDS = frozenset(
    {"requirement", "evidence_sha256", "reviewer_id", "decision"}
)
_QUALIFIED_COLLECTION_READINESS_EVIDENCE_FIELDS = frozenset(
    {
        "schema",
        "readiness_plan_sha256",
        "inventory_sha256",
        "collection_plan_sha256",
        "preparation_receipt_sha256",
        "attachment_profile",
        "producer_id",
        "evidence",
    }
)
_QUALIFIED_COLLECTION_READINESS_EVIDENCE_ITEM_FIELDS = frozenset(
    {"requirement", "evidence_sha256", "reviewer_id", "decision"}
)
_QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_FIELDS = frozenset(
    {
        "schema",
        "readiness_handoff_sha256",
        "current_observations_sha256",
        "sample_id",
        "source_pose",
        "observation_producer_id",
        "truth_reviewer_id",
        "raw_position_counts",
        "canonical_joints_rad",
        "controller_feedback_evidence_sha256",
        "camera_observation_receipt_sha256",
        "truth_evidence_sha256",
        "stationary",
        "motion_active",
        "trajectory_progress_permille",
    }
)
_DATASET_FIELDS = frozenset(
    {
        "schema",
        "dataset_id",
        "producer_id",
        "controller_binding",
        "attachment_profile",
        "position_order_servo_ids",
        "joint_order",
        "samples",
    }
)
_SAMPLE_FIELDS = frozenset(
    {
        "sample_id",
        "split",
        "source_pose",
        "raw_position_counts",
        "canonical_joints_rad",
        "truth_method",
        "truth_evidence_sha256",
        "stationary",
        "motion_active",
        "trajectory_progress_permille",
    }
)
_REVIEW_FIELDS = frozenset(
    {
        "schema",
        "dataset_sha256",
        "fit_report_sha256",
        "producer_id",
        "reviewer_id",
        "decision",
        "reviewed_at",
        "review_notes_sha256",
    }
)
_PLAN_FIELDS = frozenset(
    {
        "schema",
        "dataset_id",
        "producer_id",
        "controller_binding",
        "attachment_profile",
        "position_order_servo_ids",
        "joint_order",
        "policy",
        "slots",
        "authority",
    }
)
_PLAN_SLOT_FIELDS = frozenset({"sample_id", "split", "source_pose", "truth_method"})
_PLAN_AUTHORITY_FIELDS = frozenset(
    {
        "controller_opened",
        "camera_opened",
        "commands_sent",
        "motion_authorized",
        "physical_authority",
    }
)
_OBSERVATIONS_FIELDS = frozenset({"schema", "plan_sha256", "samples"})
_OBSERVATION_FIELDS = frozenset(
    {
        "sample_id",
        "raw_position_counts",
        "canonical_joints_rad",
        "truth_evidence_sha256",
        "stationary",
        "motion_active",
        "trajectory_progress_permille",
    }
)
_READINESS_FIELDS = frozenset(
    {
        "schema",
        "status",
        "controller_identity",
        "installed_firmware_sha256",
        "attachment_profile",
        "truth_method",
        "retained_pose_labels",
        "requirements",
        "blockers",
        "ready_to_prepare",
        "authority",
    }
)
_READINESS_REQUIREMENT_FIELDS = frozenset(
    {
        "minimum_training_samples",
        "minimum_held_out_samples",
        "minimum_unique_source_poses",
    }
)
_READINESS_EVIDENCE_FIELDS = frozenset(
    {
        "schema", "campaign_id", "producer_id", "controller_identity",
        "installed_firmware_sha256", "firmware_evidence_sha256",
        "firmware_verifier_id", "attachment_profile", "truth_method", "poses",
    }
)
_REVIEWED_POSE_FIELDS = frozenset(
    {"label", "truth_procedure_sha256", "reviewer_id"}
)
_CANDIDATE_INVENTORY_FIELDS = frozenset(
    {
        "schema", "inventory_id", "controller_binding", "attachment_profile",
        "count_kind", "poses",
    }
)
_CANDIDATE_POSE_FIELDS = frozenset(
    {"label", "raw_position_counts", "source_ref"}
)
_CANDIDATE_INVENTORY_ADMISSION_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "source_inventory_id", "source_inventory_sha256",
        "admitted_inventory_id", "admitted_inventory_sha256", "candidate_sha256",
        "attachment_profile", "qualification_handoff_sha256",
        "resulting_coverage_sha256", "resulting_pose_count", "blockers",
        "limitations", "authority",
    }
)


class PositionVectorCampaignError(ValueError):
    """Retained campaign evidence cannot support an accepted calibration."""


@dataclass(frozen=True)
class CampaignPolicy:
    minimum_training_samples: int = 5
    minimum_held_out_samples: int = 3
    minimum_training_count_span: int = 128
    accepted_max_abs_error_rad: float = 0.035
    shoulder_runtime_tolerance_counts: int = 24

    def __post_init__(self) -> None:
        if self.minimum_training_samples < 2:
            raise PositionVectorCampaignError("at least two training samples are required")
        if self.minimum_held_out_samples < 1:
            raise PositionVectorCampaignError("at least one held-out sample is required")
        if not 1 <= self.minimum_training_count_span <= 4095:
            raise PositionVectorCampaignError("training count span is outside its bound")
        if not 0.0 < self.accepted_max_abs_error_rad <= math.pi:
            raise PositionVectorCampaignError("accepted joint error is outside its bound")
        if not 0 <= self.shoulder_runtime_tolerance_counts <= 256:
            raise PositionVectorCampaignError("shoulder tolerance is outside its bound")

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_training_samples": self.minimum_training_samples,
            "minimum_held_out_samples": self.minimum_held_out_samples,
            "minimum_training_count_span": self.minimum_training_count_span,
            "accepted_max_abs_error_rad": self.accepted_max_abs_error_rad,
            "shoulder_runtime_tolerance_counts": self.shoulder_runtime_tolerance_counts,
        }


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def assess_collection_readiness(
    *,
    controller_identity: Mapping[str, Any],
    installed_firmware_sha256: str | None,
    attachment_profile: str,
    truth_method: str,
    retained_pose_labels: list[str] | tuple[str, ...],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Report whether retained facts can support freezing a collection plan.

    Missing facts become explicit blockers rather than placeholders in a plan.
    This pure assessment performs no controller, camera, or filesystem access.
    """

    identity = _mapping(controller_identity, "controller_identity")
    if set(identity) != {"vid", "pid", "unit_serial"}:
        raise PositionVectorCampaignError("controller_identity fields do not match the contract")
    vid = identity.get("vid")
    pid = identity.get("pid")
    if not isinstance(vid, str) or _HEX4.fullmatch(vid) is None:
        raise PositionVectorCampaignError("controller_identity.vid is invalid")
    if not isinstance(pid, str) or _HEX4.fullmatch(pid) is None:
        raise PositionVectorCampaignError("controller_identity.pid is invalid")
    serial = _identifier(identity.get("unit_serial"), "controller_identity.unit_serial")
    if attachment_profile not in SUPPORTED_ATTACHMENTS:
        raise PositionVectorCampaignError("readiness attachment profile is invalid")
    if truth_method not in TRUTH_METHODS:
        raise PositionVectorCampaignError("readiness truth method is unsupported")
    if not isinstance(retained_pose_labels, (list, tuple)):
        raise PositionVectorCampaignError("retained pose labels must be an array")
    poses = [
        _identifier(value, f"retained_pose_labels[{index}]")
        for index, value in enumerate(retained_pose_labels)
    ]
    unique_poses = list(dict.fromkeys(poses))
    required_pose_count = (
        policy.minimum_training_samples + policy.minimum_held_out_samples
    )
    blockers = []
    firmware = None
    if installed_firmware_sha256 is None:
        blockers.append("INSTALLED_FIRMWARE_SHA256_UNVERIFIED")
    else:
        firmware = _digest(installed_firmware_sha256, "installed_firmware_sha256")
    if len(unique_poses) < required_pose_count:
        blockers.append(
            f"UNIQUE_SOURCE_POSE_COUNT_{len(unique_poses)}_BELOW_{required_pose_count}"
        )
    if len(unique_poses) != len(poses):
        blockers.append("SOURCE_POSE_LABELS_NOT_UNIQUE")
    return {
        "schema": READINESS_SCHEMA,
        "status": "READY_TO_PREPARE" if not blockers else "BLOCKED",
        "controller_identity": {"vid": vid, "pid": pid, "unit_serial": serial},
        "installed_firmware_sha256": firmware,
        "attachment_profile": attachment_profile,
        "truth_method": truth_method,
        "retained_pose_labels": unique_poses,
        "requirements": {
            "minimum_training_samples": policy.minimum_training_samples,
            "minimum_held_out_samples": policy.minimum_held_out_samples,
            "minimum_unique_source_poses": required_pose_count,
        },
        "blockers": blockers,
        "ready_to_prepare": not blockers,
        "authority": {
            "controller_opened": False,
            "camera_opened": False,
            "commands_sent": 0,
            "motion_authorized": False,
            "physical_authority": False,
        },
    }


def load_collection_readiness(document: Mapping[str, Any]) -> dict[str, Any]:
    """Strict-decode and reproduce an offline readiness assessment."""

    raw = _mapping(document, "collection_readiness")
    _exact(raw, _READINESS_FIELDS, "collection_readiness")
    if raw.get("schema") != READINESS_SCHEMA:
        raise PositionVectorCampaignError("collection readiness schema mismatch")
    requirements = _mapping(raw.get("requirements"), "collection_readiness.requirements")
    _exact(
        requirements,
        _READINESS_REQUIREMENT_FIELDS,
        "collection_readiness.requirements",
    )
    minimum_training = requirements.get("minimum_training_samples")
    minimum_held_out = requirements.get("minimum_held_out_samples")
    if (
        isinstance(minimum_training, bool)
        or not isinstance(minimum_training, int)
        or isinstance(minimum_held_out, bool)
        or not isinstance(minimum_held_out, int)
    ):
        raise PositionVectorCampaignError("collection readiness requirements are invalid")
    policy = CampaignPolicy(
        minimum_training_samples=minimum_training,
        minimum_held_out_samples=minimum_held_out,
    )
    expected = assess_collection_readiness(
        controller_identity=_mapping(
            raw.get("controller_identity"), "collection_readiness.controller_identity"
        ),
        installed_firmware_sha256=raw.get("installed_firmware_sha256"),
        attachment_profile=raw.get("attachment_profile"),
        truth_method=raw.get("truth_method"),
        retained_pose_labels=raw.get("retained_pose_labels"),
        policy=policy,
    )
    if expected != dict(raw):
        raise PositionVectorCampaignError("collection readiness does not reproduce")
    return expected


def assess_reviewed_readiness_evidence(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive readiness from independently reviewed retained evidence."""

    raw = _mapping(document, "readiness_evidence")
    _exact(raw, _READINESS_EVIDENCE_FIELDS, "readiness_evidence")
    if raw.get("schema") != READINESS_EVIDENCE_SCHEMA:
        raise PositionVectorCampaignError("readiness evidence schema mismatch")
    campaign_id = _identifier(raw.get("campaign_id"), "readiness_evidence.campaign_id")
    producer_id = _identifier(raw.get("producer_id"), "readiness_evidence.producer_id")
    verifier_id = _identifier(
        raw.get("firmware_verifier_id"), "readiness_evidence.firmware_verifier_id"
    )
    if verifier_id == producer_id:
        raise PositionVectorCampaignError("firmware verifier must be independent")
    firmware = _digest(
        raw.get("installed_firmware_sha256"),
        "readiness_evidence.installed_firmware_sha256",
    )
    firmware_evidence = _digest(
        raw.get("firmware_evidence_sha256"),
        "readiness_evidence.firmware_evidence_sha256",
    )
    values = raw.get("poses")
    if not isinstance(values, list):
        raise PositionVectorCampaignError("readiness evidence poses must be an array")
    poses = []
    for index, value in enumerate(values):
        label = f"readiness_evidence.poses[{index}]"
        pose = _mapping(value, label)
        _exact(pose, _REVIEWED_POSE_FIELDS, label)
        reviewer_id = _identifier(pose.get("reviewer_id"), f"{label}.reviewer_id")
        if reviewer_id == producer_id:
            raise PositionVectorCampaignError("pose reviewer must be independent")
        poses.append(
            {
                "label": _identifier(pose.get("label"), f"{label}.label"),
                "truth_procedure_sha256": _digest(
                    pose.get("truth_procedure_sha256"),
                    f"{label}.truth_procedure_sha256",
                ),
                "reviewer_id": reviewer_id,
            }
        )
    pose_labels = [pose["label"] for pose in poses]
    procedure_hashes = [pose["truth_procedure_sha256"] for pose in poses]
    if len(set(pose_labels)) != len(pose_labels):
        raise PositionVectorCampaignError("reviewed pose labels must be unique")
    if len(set(procedure_hashes)) != len(procedure_hashes):
        raise PositionVectorCampaignError("pose truth procedure hashes must be unique")
    normalized = {
        "schema": READINESS_EVIDENCE_SCHEMA,
        "campaign_id": campaign_id,
        "producer_id": producer_id,
        "controller_identity": dict(
            _mapping(raw.get("controller_identity"), "readiness_evidence.controller_identity")
        ),
        "installed_firmware_sha256": firmware,
        "firmware_evidence_sha256": firmware_evidence,
        "firmware_verifier_id": verifier_id,
        "attachment_profile": raw.get("attachment_profile"),
        "truth_method": raw.get("truth_method"),
        "poses": poses,
    }
    readiness = assess_collection_readiness(
        controller_identity=normalized["controller_identity"],
        installed_firmware_sha256=firmware,
        attachment_profile=normalized["attachment_profile"],
        truth_method=normalized["truth_method"],
        retained_pose_labels=pose_labels,
    )
    receipt = {
        "schema": READINESS_EVIDENCE_RECEIPT_SCHEMA,
        "campaign_id": campaign_id,
        "status": readiness["status"],
        "evidence_sha256": canonical_sha256(normalized),
        "readiness_sha256": canonical_sha256(readiness),
        "authority": dict(readiness["authority"]),
    }
    return readiness, receipt


def audit_candidate_count_coverage(
    document: Mapping[str, Any], policy: CampaignPolicy = CampaignPolicy()
) -> dict[str, Any]:
    """Audit whether retained candidate counts can possibly meet fit coverage.

    Candidate goals are planning evidence, not stationary observations or joint
    truth.  This pure audit catches catalogs that are guaranteed to fail the
    later training-span gate before a physical collection plan is frozen.
    """

    raw = _mapping(document, "candidate_inventory")
    _exact(raw, _CANDIDATE_INVENTORY_FIELDS, "candidate_inventory")
    if raw.get("schema") != CANDIDATE_INVENTORY_SCHEMA:
        raise PositionVectorCampaignError("candidate inventory schema mismatch")
    attachment = raw.get("attachment_profile")
    if attachment not in SUPPORTED_ATTACHMENTS:
        raise PositionVectorCampaignError("candidate inventory attachment profile is invalid")
    if raw.get("count_kind") not in {"PLANNED_GOAL", "RETAINED_STATIONARY_READBACK"}:
        raise PositionVectorCampaignError("candidate inventory count kind is invalid")
    values = raw.get("poses")
    if not isinstance(values, list):
        raise PositionVectorCampaignError("candidate inventory poses must be an array")
    poses = []
    for index, value in enumerate(values):
        label = f"candidate_inventory.poses[{index}]"
        pose = _mapping(value, label)
        _exact(pose, _CANDIDATE_POSE_FIELDS, label)
        counts = pose.get("raw_position_counts")
        if (
            not isinstance(counts, list)
            or len(counts) != len(SERVO_ORDER)
            or any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or not 0 <= item <= 4095
                for item in counts
            )
        ):
            raise PositionVectorCampaignError(f"{label}.raw_position_counts is invalid")
        poses.append(
            {
                "label": _identifier(pose.get("label"), f"{label}.label"),
                "raw_position_counts": list(counts),
                "source_ref": _identifier(pose.get("source_ref"), f"{label}.source_ref"),
            }
        )
    labels = [pose["label"] for pose in poses]
    if len(set(labels)) != len(labels):
        raise PositionVectorCampaignError("candidate inventory pose labels must be unique")

    coverage = []
    blockers = []
    required_pose_count = (
        policy.minimum_training_samples + policy.minimum_held_out_samples
    )
    if len(poses) < required_pose_count:
        blockers.append(
            f"UNIQUE_SOURCE_POSE_COUNT_{len(poses)}_BELOW_{required_pose_count}"
        )
    for joint in JOINT_ORDER:
        position_index = PRIMARY_INDEX[joint]
        counts = [pose["raw_position_counts"][position_index] for pose in poses]
        minimum = min(counts) if counts else None
        maximum = max(counts) if counts else None
        span = maximum - minimum if counts else 0
        meets = span >= policy.minimum_training_count_span
        coverage.append(
            {
                "joint": joint,
                "position_index": position_index,
                "minimum_count": minimum,
                "maximum_count": maximum,
                "span_counts": span,
                "minimum_required_span_counts": policy.minimum_training_count_span,
                "meets_minimum": meets,
            }
        )
        if not meets:
            blockers.append(
                f"CANDIDATE_COUNT_SPAN_{joint.upper()}_{span}_BELOW_"
                f"{policy.minimum_training_count_span}"
            )

    normalized = {
        "schema": CANDIDATE_INVENTORY_SCHEMA,
        "inventory_id": _identifier(raw.get("inventory_id"), "candidate_inventory.inventory_id"),
        "controller_binding": _controller(raw.get("controller_binding")),
        "attachment_profile": attachment,
        "count_kind": raw.get("count_kind"),
        "poses": poses,
    }
    return {
        "schema": CANDIDATE_COVERAGE_SCHEMA,
        "status": "CANDIDATE_COVERAGE_PASS" if not blockers else "CANDIDATE_COVERAGE_BLOCKED",
        "inventory_id": normalized["inventory_id"],
        "inventory_sha256": canonical_sha256(normalized),
        "attachment_profile": attachment,
        "pose_count": len(poses),
        "position_order_servo_ids": list(SERVO_ORDER),
        "joint_order": list(JOINT_ORDER),
        "joint_coverage": coverage,
        "blockers": blockers,
        "limitations": [
            "Candidate counts are not stationary observations.",
            "Candidate counts do not provide independent joint-angle truth.",
            "A passing full-catalog audit does not prove the selected training subset spans every joint.",
            "A passing audit does not authorize hardware access, motion, or collection.",
        ],
        "authority": {
            "controller_opened": False,
            "camera_opened": False,
            "commands_sent": 0,
            "motion_authorized": False,
            "physical_authority": False,
        },
    }


def plan_candidate_count_augmentation(
    document: Mapping[str, Any], policy: CampaignPolicy = CampaignPolicy()
) -> dict[str, Any]:
    """Derive algebraic count targets for gaps in a candidate inventory.

    The ranges only describe counts that would make the full catalog span meet
    policy. They do not select a pose, establish mechanical feasibility, or
    authorize hardware access or motion.
    """

    coverage = audit_candidate_count_coverage(document, policy)
    requirements = []
    for row in coverage["joint_coverage"]:
        if row["meets_minimum"]:
            continue
        minimum = row["minimum_count"]
        maximum = row["maximum_count"]
        ranges = []
        if minimum is not None and maximum is not None:
            lower_maximum = maximum - policy.minimum_training_count_span
            upper_minimum = minimum + policy.minimum_training_count_span
            if lower_maximum >= 0:
                ranges.append({"minimum_count": 0, "maximum_count": lower_maximum})
            if upper_minimum <= 4095:
                ranges.append({"minimum_count": upper_minimum, "maximum_count": 4095})
        requirements.append(
            {
                "joint": row["joint"],
                "position_index": row["position_index"],
                "current_minimum_count": minimum,
                "current_maximum_count": maximum,
                "current_span_counts": row["span_counts"],
                "additional_span_needed_counts": max(
                    0, policy.minimum_training_count_span - row["span_counts"]
                ),
                "catalog_span_closing_count_ranges": ranges,
            }
        )

    required_pose_count = (
        policy.minimum_training_samples + policy.minimum_held_out_samples
    )
    pose_deficit = max(0, required_pose_count - coverage["pose_count"])
    algebraic_lower_bound = max(pose_deficit, 1 if requirements else 0)
    return {
        "schema": CANDIDATE_AUGMENTATION_SCHEMA,
        "status": (
            "CANDIDATE_AUGMENTATION_REQUIRED"
            if coverage["blockers"]
            else "NO_CANDIDATE_AUGMENTATION_REQUIRED"
        ),
        "inventory_id": coverage["inventory_id"],
        "inventory_sha256": coverage["inventory_sha256"],
        "coverage_sha256": canonical_sha256(coverage),
        "attachment_profile": coverage["attachment_profile"],
        "minimum_required_span_counts": policy.minimum_training_count_span,
        "catalog_minimum_additional_pose_lower_bound": algebraic_lower_bound,
        "joint_requirements": requirements,
        "unresolved_blockers": list(coverage["blockers"]),
        "limitations": [
            "Each span-closing range is an algebraic full-catalog count target, "
            "not a motion target.",
            "The lower bound does not prove one pose can safely or physically "
            "satisfy every range.",
            "Candidate counts are not stationary observations or independent "
            "joint-angle truth.",
            "A passing augmented catalog does not prove a five-pose training "
            "subset spans every joint.",
            "Mechanical feasibility, collision clearance, cable clearance, and "
            "attachment geometry remain unassessed.",
            "This plan does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(coverage["authority"]),
    }


def evaluate_candidate_count_augmentation(
    inventory_document: Mapping[str, Any],
    candidate_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Evaluate one proposed count vector against catalog coverage gaps.

    This is an algebraic, offline preflight. A passing result says only that
    appending the proposed vector closes the full-catalog count spans. It does
    not establish that the pose is reachable, safe, measurable, or approved.
    """

    augmentation = plan_candidate_count_augmentation(inventory_document, policy)
    raw = _mapping(candidate_document, "candidate_proposal")
    _exact(raw, _CANDIDATE_PROPOSAL_FIELDS, "candidate_proposal")
    if raw.get("schema") != CANDIDATE_PROPOSAL_SCHEMA:
        raise PositionVectorCampaignError("candidate proposal schema mismatch")
    if raw.get("inventory_sha256") != augmentation["inventory_sha256"]:
        raise PositionVectorCampaignError(
            "candidate proposal does not bind the assessed inventory"
        )
    attachment = raw.get("attachment_profile")
    if attachment != augmentation["attachment_profile"]:
        raise PositionVectorCampaignError(
            "candidate proposal attachment profile does not match inventory"
        )
    label = _identifier(raw.get("label"), "candidate_proposal.label")
    source_ref = _identifier(raw.get("source_ref"), "candidate_proposal.source_ref")
    counts = raw.get("raw_position_counts")
    if (
        not isinstance(counts, list)
        or len(counts) != len(SERVO_ORDER)
        or any(isinstance(item, bool) or not isinstance(item, int)
               or not 0 <= item <= 4095 for item in counts)
    ):
        raise PositionVectorCampaignError(
            "candidate_proposal.raw_position_counts is invalid"
        )

    inventory = _mapping(inventory_document, "candidate_inventory")
    existing_labels = {
        _mapping(item, f"candidate_inventory.poses[{index}]").get("label")
        for index, item in enumerate(inventory.get("poses", []))
    }
    if label in existing_labels:
        raise PositionVectorCampaignError(
            "candidate proposal label already exists in inventory"
        )

    normalized_candidate = {
        "schema": CANDIDATE_PROPOSAL_SCHEMA,
        "inventory_sha256": augmentation["inventory_sha256"],
        "label": label,
        "attachment_profile": attachment,
        "raw_position_counts": list(counts),
        "source_ref": source_ref,
    }
    evaluations = []
    for requirement in augmentation["joint_requirements"]:
        count = counts[requirement["position_index"]]
        matches = [
            range_index
            for range_index, allowed in enumerate(
                requirement["catalog_span_closing_count_ranges"]
            )
            if allowed["minimum_count"] <= count <= allowed["maximum_count"]
        ]
        evaluations.append(
            {
                "joint": requirement["joint"],
                "position_index": requirement["position_index"],
                "proposed_count": count,
                "matches_catalog_span_closing_range": bool(matches),
                "matching_range_indexes": matches,
            }
        )

    augmented_inventory = dict(inventory)
    augmented_inventory["poses"] = [
        *inventory.get("poses", []),
        {
            "label": label,
            "raw_position_counts": list(counts),
            "source_ref": source_ref,
        },
    ]
    resulting_coverage = audit_candidate_count_coverage(augmented_inventory, policy)
    closes_all = not resulting_coverage["blockers"]
    return {
        "schema": CANDIDATE_PREFLIGHT_SCHEMA,
        "status": (
            "NO_AUGMENTATION_REQUIRED"
            if not augmentation["joint_requirements"]
            else (
                "COUNT_VECTOR_CLOSES_CATALOG_GAPS"
                if closes_all else "COUNT_VECTOR_LEAVES_CATALOG_GAPS"
            )
        ),
        "inventory_id": augmentation["inventory_id"],
        "inventory_sha256": augmentation["inventory_sha256"],
        "augmentation_sha256": canonical_sha256(augmentation),
        "attachment_profile": attachment,
        "candidate": normalized_candidate,
        "candidate_sha256": canonical_sha256(normalized_candidate),
        "requirement_evaluations": evaluations,
        "resulting_coverage_sha256": canonical_sha256(resulting_coverage),
        "resulting_coverage_status": resulting_coverage["status"],
        "remaining_blockers": list(resulting_coverage["blockers"]),
        "closes_all_catalog_count_gaps": closes_all,
        "limitations": [
            "This preflight evaluates count-span algebra only.",
            "The proposed vector is not a motion command or stationary observation.",
            "A passing result does not establish reachability, joint limits, "
            "collision clearance, cable clearance, attachment clearance, or "
            "independent joint truth.",
            "A passing full-catalog result does not prove a five-pose training "
            "subset spans every joint.",
            "This preflight does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(augmentation["authority"]),
    }


def create_candidate_qualification_plan(
    inventory_document: Mapping[str, Any],
    candidate_document: Mapping[str, Any],
    preflight_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Create the evidence checklist for one count-closing candidate.

    The supplied preflight must reproduce exactly from the inventory and
    proposal. The result contains no accepted evidence: it identifies the
    independent physical and engineering reviews that still remain.
    """

    reproduced = evaluate_candidate_count_augmentation(
        inventory_document, candidate_document, policy
    )
    supplied = _mapping(preflight_document, "candidate_preflight")
    if dict(supplied) != reproduced:
        raise PositionVectorCampaignError(
            "candidate preflight does not reproduce from inventory and proposal"
        )
    if reproduced["status"] != "COUNT_VECTOR_CLOSES_CATALOG_GAPS":
        raise PositionVectorCampaignError(
            "candidate does not close every catalog count gap"
        )

    requirements = [
        (
            "CALIBRATED_COUNT_TO_JOINT_MAPPING",
            "Accepted attachment-specific conversion from controller counts to "
            "independently measured canonical joint angles.",
        ),
        (
            "KINEMATIC_REACHABILITY_AND_JOINT_LIMIT_ASSESSMENT",
            "Reviewed reachability and joint-limit result from a kinematic model "
            "bound to the installed build.",
        ),
        (
            "INSTALLED_COLLISION_GEOMETRY",
            "Measured and accepted installed collision profile for the exact "
            "attachment configuration.",
        ),
        (
            "INSTALLED_CABLE_CLEARANCE_ENVELOPE",
            "Reviewed cable routing and clearance evidence for the proposed pose.",
        ),
        (
            "ATTACHMENT_TCP_GEOMETRY",
            "Measured jaw, tool-center-point, and attachment geometry for the "
            "selected attachment profile.",
        ),
        (
            "CONTINUOUS_SWEPT_PATH_SCREENING",
            "Reviewed continuous-path collision and clearance result for a qualified "
            "route to and from the candidate.",
        ),
        (
            "INDEPENDENT_JOINT_TRUTH_PROCEDURE",
            "A retained independent procedure for measuring every canonical joint "
            "at the stationary candidate pose.",
        ),
        (
            "ENGINEERING_QUALIFICATION_REVIEW",
            "Independent engineering acceptance of the exact evidence-bound pose.",
        ),
    ]
    return {
        "schema": CANDIDATE_QUALIFICATION_PLAN_SCHEMA,
        "status": "QUALIFICATION_EVIDENCE_REQUIRED",
        "inventory_id": reproduced["inventory_id"],
        "inventory_sha256": reproduced["inventory_sha256"],
        "attachment_profile": reproduced["attachment_profile"],
        "candidate": dict(reproduced["candidate"]),
        "candidate_sha256": reproduced["candidate_sha256"],
        "candidate_preflight_sha256": canonical_sha256(reproduced),
        "qualification_requirements": [
            {
                "requirement": requirement,
                "description": description,
                "status": "EVIDENCE_REQUIRED",
                "accepted_evidence_sha256": None,
            }
            for requirement, description in requirements
        ],
        "blockers": [f"{requirement}_EVIDENCE_REQUIRED" for requirement, _ in requirements],
        "limitations": [
            "This plan inventories missing evidence; it does not assess or accept it.",
            "A count-closing candidate is not thereby reachable, within joint limits, "
            "or collision-free.",
            "No cable, attachment, swept-path, or independent joint-truth evidence "
            "has been supplied by this plan.",
            "This plan does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(reproduced["authority"]),
    }


def assess_candidate_qualification_evidence(
    inventory_document: Mapping[str, Any],
    candidate_document: Mapping[str, Any],
    preflight_document: Mapping[str, Any],
    plan_document: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Assess declared evidence for one exact candidate qualification plan.

    This validates the chain, decisions, and independent reviewers. It does
    not inspect the referenced evidence content or grant physical authority.
    """

    reproduced_plan = create_candidate_qualification_plan(
        inventory_document, candidate_document, preflight_document, policy
    )
    supplied_plan = _mapping(plan_document, "candidate_qualification_plan")
    if dict(supplied_plan) != reproduced_plan:
        raise PositionVectorCampaignError(
            "candidate qualification plan does not reproduce from its inputs"
        )

    raw = _mapping(evidence_document, "candidate_qualification_evidence")
    _exact(
        raw,
        _CANDIDATE_QUALIFICATION_EVIDENCE_FIELDS,
        "candidate_qualification_evidence",
    )
    if raw.get("schema") != CANDIDATE_QUALIFICATION_EVIDENCE_SCHEMA:
        raise PositionVectorCampaignError(
            "candidate qualification evidence schema mismatch"
        )
    plan_hash = canonical_sha256(reproduced_plan)
    bindings = {
        "qualification_plan_sha256": plan_hash,
        "inventory_sha256": reproduced_plan["inventory_sha256"],
        "candidate_sha256": reproduced_plan["candidate_sha256"],
        "attachment_profile": reproduced_plan["attachment_profile"],
    }
    if any(raw.get(name) != expected for name, expected in bindings.items()):
        raise PositionVectorCampaignError(
            "candidate qualification evidence binding mismatch"
        )
    producer_id = _identifier(
        raw.get("producer_id"), "candidate_qualification_evidence.producer_id"
    )
    evidence_items = raw.get("evidence")
    if not isinstance(evidence_items, list):
        raise PositionVectorCampaignError(
            "candidate_qualification_evidence.evidence must be a list"
        )

    required = [
        item["requirement"] for item in reproduced_plan["qualification_requirements"]
    ]
    supplied_by_requirement: dict[str, dict[str, str]] = {}
    for index, value in enumerate(evidence_items):
        label = f"candidate_qualification_evidence.evidence[{index}]"
        item = _mapping(value, label)
        _exact(item, _CANDIDATE_QUALIFICATION_EVIDENCE_ITEM_FIELDS, label)
        requirement = item.get("requirement")
        if requirement not in required:
            raise PositionVectorCampaignError(f"{label}.requirement is unknown")
        if requirement in supplied_by_requirement:
            raise PositionVectorCampaignError(
                "candidate qualification evidence repeats a requirement"
            )
        reviewer_id = _identifier(item.get("reviewer_id"), f"{label}.reviewer_id")
        if reviewer_id == producer_id:
            raise PositionVectorCampaignError(
                f"{label}.reviewer_id is not independent of the producer"
            )
        decision = item.get("decision")
        if decision not in {"ACCEPT", "REJECT"}:
            raise PositionVectorCampaignError(f"{label}.decision is invalid")
        supplied_by_requirement[requirement] = {
            "requirement": requirement,
            "evidence_sha256": _digest(
                item.get("evidence_sha256"), f"{label}.evidence_sha256"
            ),
            "reviewer_id": reviewer_id,
            "decision": decision,
        }

    assessments = []
    blockers = []
    normalized_items = []
    for requirement in required:
        item = supplied_by_requirement.get(requirement)
        if item is None:
            assessments.append(
                {
                    "requirement": requirement,
                    "status": "EVIDENCE_MISSING",
                    "evidence_sha256": None,
                    "reviewer_id": None,
                }
            )
            blockers.append(f"{requirement}_EVIDENCE_REQUIRED")
            continue
        normalized_items.append(item)
        status = "EVIDENCE_ACCEPTED" if item["decision"] == "ACCEPT" else "EVIDENCE_REJECTED"
        assessments.append(
            {
                "requirement": requirement,
                "status": status,
                "evidence_sha256": item["evidence_sha256"],
                "reviewer_id": item["reviewer_id"],
            }
        )
        if item["decision"] == "REJECT":
            blockers.append(f"{requirement}_EVIDENCE_REJECTED")

    normalized_evidence = {
        "schema": CANDIDATE_QUALIFICATION_EVIDENCE_SCHEMA,
        **bindings,
        "producer_id": producer_id,
        "evidence": normalized_items,
    }
    return {
        "schema": CANDIDATE_QUALIFICATION_ASSESSMENT_SCHEMA,
        "status": (
            "EVIDENCE_CHAIN_COMPLETE" if not blockers else "EVIDENCE_CHAIN_BLOCKED"
        ),
        **bindings,
        "evidence_sha256": canonical_sha256(normalized_evidence),
        "requirement_assessments": assessments,
        "blockers": blockers,
        "limitations": [
            "This assessment validates declared hashes, decisions, and reviewer "
            "independence; it does not inspect referenced evidence content.",
            "EVIDENCE_CHAIN_COMPLETE does not itself establish physical correctness, "
            "reachability, collision clearance, or safe motion.",
            "This assessment does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(reproduced_plan["authority"]),
    }


def create_candidate_qualification_handoff(
    inventory_document: Mapping[str, Any],
    candidate_document: Mapping[str, Any],
    preflight_document: Mapping[str, Any],
    plan_document: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    assessment_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Create a reproducible receipt for one complete qualification chain.

    The receipt is an offline handoff boundary. It preserves the accepted
    evidence order and exact upstream hashes, but grants no physical authority.
    """

    reproduced = assess_candidate_qualification_evidence(
        inventory_document,
        candidate_document,
        preflight_document,
        plan_document,
        evidence_document,
        policy,
    )
    supplied = _mapping(assessment_document, "candidate_qualification_assessment")
    if dict(supplied) != reproduced:
        raise PositionVectorCampaignError(
            "candidate qualification assessment does not reproduce from its inputs"
        )
    if reproduced["status"] != "EVIDENCE_CHAIN_COMPLETE":
        raise PositionVectorCampaignError(
            "candidate qualification evidence chain is not complete"
        )

    evidence = _mapping(evidence_document, "candidate_qualification_evidence")
    plan = _mapping(plan_document, "candidate_qualification_plan")
    return {
        "schema": CANDIDATE_QUALIFICATION_HANDOFF_SCHEMA,
        "status": "QUALIFICATION_HANDOFF_READY",
        "inventory_id": plan["inventory_id"],
        "inventory_sha256": reproduced["inventory_sha256"],
        "candidate": dict(plan["candidate"]),
        "candidate_sha256": reproduced["candidate_sha256"],
        "attachment_profile": reproduced["attachment_profile"],
        "qualification_plan_sha256": reproduced["qualification_plan_sha256"],
        "evidence_sha256": reproduced["evidence_sha256"],
        "qualification_assessment_sha256": canonical_sha256(reproduced),
        "evidence_producer_id": evidence["producer_id"],
        "accepted_evidence": [
            {
                "requirement": item["requirement"],
                "evidence_sha256": item["evidence_sha256"],
                "reviewer_id": item["reviewer_id"],
            }
            for item in reproduced["requirement_assessments"]
        ],
        "blockers": [],
        "limitations": [
            "This receipt reproduces and binds accepted evidence declarations; it "
            "does not inspect the referenced evidence content.",
            "QUALIFICATION_HANDOFF_READY is an artifact-transfer state, not proof "
            "of physical correctness or safe motion.",
            "This handoff does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(reproduced["authority"]),
    }


def create_qualified_candidate_inventory_package(
    inventory_document: Mapping[str, Any],
    candidate_document: Mapping[str, Any],
    preflight_document: Mapping[str, Any],
    plan_document: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    assessment_document: Mapping[str, Any],
    handoff_document: Mapping[str, Any],
    admitted_inventory_id: str,
    policy: CampaignPolicy = CampaignPolicy(),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append one qualified candidate to a new offline inventory artifact."""

    reproduced_handoff = create_candidate_qualification_handoff(
        inventory_document,
        candidate_document,
        preflight_document,
        plan_document,
        evidence_document,
        assessment_document,
        policy,
    )
    supplied_handoff = _mapping(
        handoff_document, "candidate_qualification_handoff"
    )
    if dict(supplied_handoff) != reproduced_handoff:
        raise PositionVectorCampaignError(
            "candidate qualification handoff does not reproduce from its inputs"
        )

    source = _mapping(inventory_document, "candidate_inventory")
    source_coverage = audit_candidate_count_coverage(source, policy)
    new_inventory_id = _identifier(
        admitted_inventory_id, "admitted_inventory_id"
    )
    if new_inventory_id == source_coverage["inventory_id"]:
        raise PositionVectorCampaignError(
            "admitted inventory id must differ from the source inventory id"
        )
    candidate = reproduced_handoff["candidate"]
    admitted = {
        "schema": CANDIDATE_INVENTORY_SCHEMA,
        "inventory_id": new_inventory_id,
        "controller_binding": dict(source["controller_binding"]),
        "attachment_profile": source["attachment_profile"],
        "count_kind": source["count_kind"],
        "poses": [
            *[dict(_mapping(item, "candidate_inventory.pose")) for item in source["poses"]],
            {
                "label": candidate["label"],
                "raw_position_counts": list(candidate["raw_position_counts"]),
                "source_ref": candidate["source_ref"],
            },
        ],
    }
    resulting_coverage = audit_candidate_count_coverage(admitted, policy)
    if resulting_coverage["status"] != "CANDIDATE_COVERAGE_PASS":
        raise PositionVectorCampaignError(
            "qualified candidate inventory does not pass the coverage audit"
        )

    receipt = {
        "schema": CANDIDATE_INVENTORY_ADMISSION_RECEIPT_SCHEMA,
        "status": "QUALIFIED_CANDIDATE_INVENTORY_READY",
        "source_inventory_id": source_coverage["inventory_id"],
        "source_inventory_sha256": source_coverage["inventory_sha256"],
        "admitted_inventory_id": new_inventory_id,
        "admitted_inventory_sha256": canonical_sha256(admitted),
        "candidate_sha256": reproduced_handoff["candidate_sha256"],
        "attachment_profile": reproduced_handoff["attachment_profile"],
        "qualification_handoff_sha256": canonical_sha256(reproduced_handoff),
        "resulting_coverage_sha256": canonical_sha256(resulting_coverage),
        "resulting_pose_count": resulting_coverage["pose_count"],
        "blockers": [],
        "limitations": [
            "The admitted candidate remains a planned goal, not a stationary "
            "controller readback or independent joint-truth observation.",
            "The output is a proposed inventory artifact and does not replace a "
            "retained inventory automatically.",
            "This admission does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(reproduced_handoff["authority"]),
    }
    return admitted, receipt


def plan_qualified_candidate_training_split(
    inventory_document: Mapping[str, Any],
    admission_receipt_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Select the smallest count-spanning training subset deterministically."""

    coverage = audit_candidate_count_coverage(inventory_document, policy)
    receipt = _mapping(
        admission_receipt_document, "candidate_inventory_admission_receipt"
    )
    _exact(
        receipt,
        _CANDIDATE_INVENTORY_ADMISSION_RECEIPT_FIELDS,
        "candidate_inventory_admission_receipt",
    )
    if receipt.get("schema") != CANDIDATE_INVENTORY_ADMISSION_RECEIPT_SCHEMA:
        raise PositionVectorCampaignError(
            "candidate inventory admission receipt schema mismatch"
        )
    if receipt.get("status") != "QUALIFIED_CANDIDATE_INVENTORY_READY":
        raise PositionVectorCampaignError(
            "candidate inventory admission receipt is not ready"
        )
    expected_bindings = {
        "admitted_inventory_id": coverage["inventory_id"],
        "admitted_inventory_sha256": coverage["inventory_sha256"],
        "attachment_profile": coverage["attachment_profile"],
        "resulting_coverage_sha256": canonical_sha256(coverage),
        "resulting_pose_count": coverage["pose_count"],
    }
    if any(receipt.get(name) != value for name, value in expected_bindings.items()):
        raise PositionVectorCampaignError(
            "candidate inventory admission receipt binding mismatch"
        )
    _identifier(
        receipt.get("source_inventory_id"),
        "candidate_inventory_admission_receipt.source_inventory_id",
    )
    for name in (
        "source_inventory_sha256",
        "candidate_sha256",
        "qualification_handoff_sha256",
    ):
        _digest(
            receipt.get(name),
            f"candidate_inventory_admission_receipt.{name}",
        )
    if receipt.get("blockers") != []:
        raise PositionVectorCampaignError(
            "candidate inventory admission receipt has blockers"
        )
    if receipt.get("authority") != coverage["authority"]:
        raise PositionVectorCampaignError(
            "candidate inventory admission receipt grants physical authority"
        )

    inventory = _mapping(inventory_document, "candidate_inventory")
    poses = inventory["poses"]
    maximum_training = len(poses) - policy.minimum_held_out_samples
    selected_indexes: tuple[int, ...] | None = None
    selected_coverage: list[dict[str, Any]] = []
    for training_count in range(policy.minimum_training_samples, maximum_training + 1):
        for indexes in combinations(range(len(poses)), training_count):
            joint_coverage = []
            for joint in JOINT_ORDER:
                position_index = PRIMARY_INDEX[joint]
                counts = [poses[index]["raw_position_counts"][position_index]
                          for index in indexes]
                minimum = min(counts)
                maximum = max(counts)
                joint_coverage.append(
                    {
                        "joint": joint,
                        "position_index": position_index,
                        "minimum_count": minimum,
                        "maximum_count": maximum,
                        "span_counts": maximum - minimum,
                        "minimum_required_span_counts": (
                            policy.minimum_training_count_span
                        ),
                        "meets_minimum": (
                            maximum - minimum
                            >= policy.minimum_training_count_span
                        ),
                    }
                )
            if all(row["meets_minimum"] for row in joint_coverage):
                selected_indexes = indexes
                selected_coverage = joint_coverage
                break
        if selected_indexes is not None:
            break

    if selected_indexes is None:
        training_labels: list[str] = []
        held_out_labels = [pose["label"] for pose in poses]
        blockers = ["NO_TRAINING_SUBSET_MEETS_COUNT_SPAN_POLICY"]
        status = "TRAINING_SPLIT_BLOCKED"
    else:
        selected = set(selected_indexes)
        training_labels = [
            pose["label"] for index, pose in enumerate(poses) if index in selected
        ]
        held_out_labels = [
            pose["label"] for index, pose in enumerate(poses) if index not in selected
        ]
        blockers = []
        status = "TRAINING_SPLIT_READY"

    return {
        "schema": CANDIDATE_TRAINING_SPLIT_PLAN_SCHEMA,
        "status": status,
        "inventory_id": coverage["inventory_id"],
        "inventory_sha256": coverage["inventory_sha256"],
        "admission_receipt_sha256": canonical_sha256(receipt),
        "attachment_profile": coverage["attachment_profile"],
        "policy": {
            "minimum_training_samples": policy.minimum_training_samples,
            "minimum_held_out_samples": policy.minimum_held_out_samples,
            "minimum_training_count_span": policy.minimum_training_count_span,
        },
        "training_pose_labels": training_labels,
        "held_out_pose_labels": held_out_labels,
        "training_joint_coverage": selected_coverage,
        "blockers": blockers,
        "limitations": [
            "This split proves count-span coverage only; it does not provide "
            "stationary observations or independent joint truth.",
            "The deterministic first feasible subset is not an optimization of "
            "conditioning, geometry, clearance, or measurement quality.",
            "This plan does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(coverage["authority"]),
    }


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PositionVectorCampaignError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if set(value) != fields:
        raise PositionVectorCampaignError(f"{label} fields do not match the contract")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise PositionVectorCampaignError(f"{label} is not a bounded identifier")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise PositionVectorCampaignError(f"{label} is not a lowercase SHA-256")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PositionVectorCampaignError(f"{label} is not a finite number")
    result = float(value)
    if not -2 * math.pi <= result <= 2 * math.pi:
        raise PositionVectorCampaignError(f"{label} is outside the joint-angle bound")
    return result


def _controller(value: Any) -> dict[str, str]:
    raw = _mapping(value, "controller_binding")
    _exact(raw, _CONTROLLER_FIELDS, "controller_binding")
    vid = raw.get("vid")
    pid = raw.get("pid")
    if not isinstance(vid, str) or _HEX4.fullmatch(vid) is None:
        raise PositionVectorCampaignError("controller_binding.vid is invalid")
    if not isinstance(pid, str) or _HEX4.fullmatch(pid) is None:
        raise PositionVectorCampaignError("controller_binding.pid is invalid")
    return {
        "vid": vid,
        "pid": pid,
        "unit_serial": _identifier(raw.get("unit_serial"), "controller_binding.unit_serial"),
        "firmware_sha256": _digest(
            raw.get("firmware_sha256"), "controller_binding.firmware_sha256"
        ),
    }


def _sample(value: Any, index: int) -> dict[str, Any]:
    label = f"samples[{index}]"
    raw = _mapping(value, label)
    _exact(raw, _SAMPLE_FIELDS, label)
    split = raw.get("split")
    if split not in {"TRAINING", "HELD_OUT"}:
        raise PositionVectorCampaignError(f"{label}.split is invalid")
    counts = raw.get("raw_position_counts")
    if (
        not isinstance(counts, list)
        or len(counts) != 7
        or any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 4095
               for item in counts)
    ):
        raise PositionVectorCampaignError(f"{label}.raw_position_counts is invalid")
    joints = _mapping(raw.get("canonical_joints_rad"), f"{label}.canonical_joints_rad")
    if set(joints) != set(JOINT_ORDER):
        raise PositionVectorCampaignError(f"{label}.canonical joints are invalid")
    method = raw.get("truth_method")
    if method not in TRUTH_METHODS:
        raise PositionVectorCampaignError(f"{label}.truth_method is unsupported")
    if raw.get("stationary") is not True or raw.get("motion_active") is not False:
        raise PositionVectorCampaignError(f"{label} is not a stationary observation")
    if raw.get("trajectory_progress_permille") != 1000:
        raise PositionVectorCampaignError(f"{label} trajectory is not complete")
    return {
        "sample_id": _identifier(raw.get("sample_id"), f"{label}.sample_id"),
        "split": split,
        "source_pose": _identifier(raw.get("source_pose"), f"{label}.source_pose"),
        "raw_position_counts": list(counts),
        "canonical_joints_rad": {
            joint: _number(joints.get(joint), f"{label}.{joint}") for joint in JOINT_ORDER
        },
        "truth_method": method,
        "truth_evidence_sha256": _digest(
            raw.get("truth_evidence_sha256"), f"{label}.truth_evidence_sha256"
        ),
        "stationary": True,
        "motion_active": False,
        "trajectory_progress_permille": 1000,
    }


def load_campaign_dataset(document: Mapping[str, Any]) -> dict[str, Any]:
    """Strict-decode retained physical observations without performing I/O."""

    raw = _mapping(document, "dataset")
    _exact(raw, _DATASET_FIELDS, "dataset")
    if raw.get("schema") != DATASET_SCHEMA:
        raise PositionVectorCampaignError("dataset schema mismatch")
    if raw.get("position_order_servo_ids") != list(SERVO_ORDER):
        raise PositionVectorCampaignError("dataset servo order mismatch")
    if raw.get("joint_order") != list(JOINT_ORDER):
        raise PositionVectorCampaignError("dataset joint order mismatch")
    attachment = raw.get("attachment_profile")
    if attachment not in SUPPORTED_ATTACHMENTS:
        raise PositionVectorCampaignError("dataset attachment profile is invalid")
    values = raw.get("samples")
    if not isinstance(values, list):
        raise PositionVectorCampaignError("dataset samples must be an array")
    samples = [_sample(item, index) for index, item in enumerate(values)]
    ids = [item["sample_id"] for item in samples]
    evidence = [item["truth_evidence_sha256"] for item in samples]
    if len(set(ids)) != len(ids):
        raise PositionVectorCampaignError("sample IDs must be unique")
    if len(set(evidence)) != len(evidence):
        raise PositionVectorCampaignError("truth evidence hashes must be unique")
    return {
        "schema": DATASET_SCHEMA,
        "dataset_id": _identifier(raw.get("dataset_id"), "dataset_id"),
        "producer_id": _identifier(raw.get("producer_id"), "producer_id"),
        "controller_binding": _controller(raw.get("controller_binding")),
        "attachment_profile": attachment,
        "position_order_servo_ids": list(SERVO_ORDER),
        "joint_order": list(JOINT_ORDER),
        "samples": samples,
    }


def create_collection_plan(
    *,
    dataset_id: str,
    producer_id: str,
    controller_binding: Mapping[str, Any],
    attachment_profile: str,
    training_poses: list[str] | tuple[str, ...],
    held_out_poses: list[str] | tuple[str, ...],
    truth_method: str,
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Freeze a finite collection campaign without opening any hardware."""

    if attachment_profile not in SUPPORTED_ATTACHMENTS:
        raise PositionVectorCampaignError("collection plan attachment profile is invalid")
    if truth_method not in TRUTH_METHODS:
        raise PositionVectorCampaignError("collection plan truth method is unsupported")
    if not isinstance(training_poses, (list, tuple)) or not isinstance(
        held_out_poses, (list, tuple)
    ):
        raise PositionVectorCampaignError("collection plan poses must be arrays")
    if len(training_poses) < policy.minimum_training_samples:
        raise PositionVectorCampaignError("collection plan has insufficient training slots")
    if len(held_out_poses) < policy.minimum_held_out_samples:
        raise PositionVectorCampaignError("collection plan has insufficient held-out slots")
    poses = [
        _identifier(value, f"training_poses[{index}]")
        for index, value in enumerate(training_poses)
    ] + [
        _identifier(value, f"held_out_poses[{index}]")
        for index, value in enumerate(held_out_poses)
    ]
    if len(set(poses)) != len(poses):
        raise PositionVectorCampaignError("collection plan source poses must be unique")
    slots = []
    for index, source_pose in enumerate(poses):
        training = index < len(training_poses)
        prefix = "train" if training else "holdout"
        ordinal = index if training else index - len(training_poses)
        slots.append(
            {
                "sample_id": f"{prefix}-{ordinal + 1:02d}",
                "split": "TRAINING" if training else "HELD_OUT",
                "source_pose": source_pose,
                "truth_method": truth_method,
            }
        )
    return load_collection_plan(
        {
            "schema": PLAN_SCHEMA,
            "dataset_id": dataset_id,
            "producer_id": producer_id,
            "controller_binding": dict(controller_binding),
            "attachment_profile": attachment_profile,
            "position_order_servo_ids": list(SERVO_ORDER),
            "joint_order": list(JOINT_ORDER),
            "policy": policy.to_dict(),
            "slots": slots,
            "authority": {
                "controller_opened": False,
                "camera_opened": False,
                "commands_sent": 0,
                "motion_authorized": False,
                "physical_authority": False,
            },
        }
    )


def create_qualified_candidate_collection_package(
    *,
    inventory_document: Mapping[str, Any],
    admission_receipt_document: Mapping[str, Any],
    training_split_document: Mapping[str, Any],
    dataset_id: str,
    producer_id: str,
    truth_method: str,
    policy: CampaignPolicy = CampaignPolicy(),
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prepare a zero-authority collection package from the qualified split."""

    expected_split = plan_qualified_candidate_training_split(
        inventory_document,
        admission_receipt_document,
        policy,
    )
    supplied_split = _mapping(training_split_document, "candidate_training_split")
    if dict(supplied_split) != expected_split:
        raise PositionVectorCampaignError(
            "candidate training split does not reproduce from its inputs"
        )
    if expected_split["status"] != "TRAINING_SPLIT_READY":
        raise PositionVectorCampaignError(
            "candidate training split is blocked: "
            + ", ".join(expected_split["blockers"])
        )

    inventory = _mapping(inventory_document, "candidate_inventory")
    plan = create_collection_plan(
        dataset_id=dataset_id,
        producer_id=producer_id,
        controller_binding=inventory["controller_binding"],
        attachment_profile=expected_split["attachment_profile"],
        training_poses=expected_split["training_pose_labels"],
        held_out_poses=expected_split["held_out_pose_labels"],
        truth_method=truth_method,
        policy=policy,
    )
    observations = collection_observations_template(plan)
    receipt = {
        "schema": QUALIFIED_COLLECTION_PREPARATION_RECEIPT_SCHEMA,
        "status": "QUALIFIED_COLLECTION_PACKAGE_PREPARED",
        "dataset_id": plan["dataset_id"],
        "producer_id": plan["producer_id"],
        "inventory_sha256": expected_split["inventory_sha256"],
        "admission_receipt_sha256": expected_split["admission_receipt_sha256"],
        "training_split_sha256": canonical_sha256(expected_split),
        "plan_sha256": canonical_sha256(plan),
        "observations_sha256": canonical_sha256(observations),
        "pose_count": len(plan["slots"]),
        "training_count": len(expected_split["training_pose_labels"]),
        "held_out_count": len(expected_split["held_out_pose_labels"]),
        "next_required_gate": "REVIEWED_COLLECTION_READINESS",
        "limitations": [
            "The inventory entries remain planned goals, not stationary controller "
            "readbacks or independent joint-truth observations.",
            "The empty observation template cannot establish installed firmware, "
            "camera, board, attachment, or truth-procedure readiness.",
            "Reviewed collection readiness must bind this same controller, firmware, "
            "attachment profile, truth method, and nine-pose catalog before collection.",
            "This package does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(plan["authority"]),
    }
    return plan, observations, receipt


def create_qualified_collection_readiness_plan(
    *,
    inventory_document: Mapping[str, Any],
    admission_receipt_document: Mapping[str, Any],
    training_split_document: Mapping[str, Any],
    collection_plan_document: Mapping[str, Any],
    observations_document: Mapping[str, Any],
    preparation_receipt_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Freeze the reviewed evidence still required before collection."""

    supplied_plan = load_collection_plan(collection_plan_document)
    truth_methods = {slot["truth_method"] for slot in supplied_plan["slots"]}
    if len(truth_methods) != 1:
        raise PositionVectorCampaignError(
            "qualified collection plan must use one truth method"
        )
    expected_plan, expected_observations, expected_receipt = (
        create_qualified_candidate_collection_package(
            inventory_document=inventory_document,
            admission_receipt_document=admission_receipt_document,
            training_split_document=training_split_document,
            dataset_id=supplied_plan["dataset_id"],
            producer_id=supplied_plan["producer_id"],
            truth_method=next(iter(truth_methods)),
            policy=policy,
        )
    )
    if supplied_plan != expected_plan:
        raise PositionVectorCampaignError(
            "qualified collection plan does not reproduce from its inputs"
        )
    supplied_observations = _mapping(
        observations_document, "qualified_collection_observations"
    )
    if dict(supplied_observations) != expected_observations:
        raise PositionVectorCampaignError(
            "qualified collection observations do not reproduce from the plan"
        )
    supplied_receipt = _mapping(
        preparation_receipt_document, "qualified_collection_preparation_receipt"
    )
    if dict(supplied_receipt) != expected_receipt:
        raise PositionVectorCampaignError(
            "qualified collection preparation receipt does not reproduce"
        )

    requirements = [
        {"requirement": requirement, "scope": scope, "status": "MISSING"}
        for requirement, scope in _QUALIFIED_COLLECTION_READINESS_REQUIREMENTS
    ]
    return {
        "schema": QUALIFIED_COLLECTION_READINESS_PLAN_SCHEMA,
        "status": "QUALIFIED_COLLECTION_READINESS_EVIDENCE_REQUIRED",
        "dataset_id": supplied_plan["dataset_id"],
        "producer_id": supplied_plan["producer_id"],
        "inventory_sha256": expected_receipt["inventory_sha256"],
        "admission_receipt_sha256": expected_receipt["admission_receipt_sha256"],
        "training_split_sha256": expected_receipt["training_split_sha256"],
        "collection_plan_sha256": canonical_sha256(expected_plan),
        "observations_sha256": canonical_sha256(expected_observations),
        "preparation_receipt_sha256": canonical_sha256(expected_receipt),
        "controller_binding": dict(supplied_plan["controller_binding"]),
        "attachment_profile": supplied_plan["attachment_profile"],
        "truth_method": next(iter(truth_methods)),
        "pose_labels": [slot["source_pose"] for slot in supplied_plan["slots"]],
        "evidence_requirements": requirements,
        "blockers": [
            f"{requirement}_EVIDENCE_MISSING"
            for requirement, _scope in _QUALIFIED_COLLECTION_READINESS_REQUIREMENTS
        ],
        "limitations": [
            "This checklist identifies required evidence but does not inspect or "
            "accept any referenced evidence.",
            "Camera and board evidence must describe the fixed collection setup, "
            "not a phone image or an unrelated camera mode.",
            "Attachment, collision-envelope, and truth-procedure evidence must match "
            "the exact controller-bound pose catalog.",
            "This plan does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(supplied_plan["authority"]),
    }


def assess_qualified_collection_readiness_evidence(
    *,
    inventory_document: Mapping[str, Any],
    admission_receipt_document: Mapping[str, Any],
    training_split_document: Mapping[str, Any],
    collection_plan_document: Mapping[str, Any],
    observations_document: Mapping[str, Any],
    preparation_receipt_document: Mapping[str, Any],
    readiness_plan_document: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Assess reviewed evidence declared for one qualified collection package.

    The assessment reproduces every upstream planning artifact, validates
    independent review declarations, and preserves missing or rejected gates as
    blockers. It does not inspect evidence content or grant physical authority.
    """

    reproduced_plan = create_qualified_collection_readiness_plan(
        inventory_document=inventory_document,
        admission_receipt_document=admission_receipt_document,
        training_split_document=training_split_document,
        collection_plan_document=collection_plan_document,
        observations_document=observations_document,
        preparation_receipt_document=preparation_receipt_document,
        policy=policy,
    )
    supplied_plan = _mapping(
        readiness_plan_document, "qualified_collection_readiness_plan"
    )
    if dict(supplied_plan) != reproduced_plan:
        raise PositionVectorCampaignError(
            "qualified collection readiness plan does not reproduce from its inputs"
        )

    raw = _mapping(evidence_document, "qualified_collection_readiness_evidence")
    _exact(
        raw,
        _QUALIFIED_COLLECTION_READINESS_EVIDENCE_FIELDS,
        "qualified_collection_readiness_evidence",
    )
    if raw.get("schema") != QUALIFIED_COLLECTION_READINESS_EVIDENCE_SCHEMA:
        raise PositionVectorCampaignError(
            "qualified collection readiness evidence schema mismatch"
        )
    bindings = {
        "readiness_plan_sha256": canonical_sha256(reproduced_plan),
        "inventory_sha256": reproduced_plan["inventory_sha256"],
        "collection_plan_sha256": reproduced_plan["collection_plan_sha256"],
        "preparation_receipt_sha256": reproduced_plan[
            "preparation_receipt_sha256"
        ],
        "attachment_profile": reproduced_plan["attachment_profile"],
    }
    if any(raw.get(name) != expected for name, expected in bindings.items()):
        raise PositionVectorCampaignError(
            "qualified collection readiness evidence binding mismatch"
        )
    producer_id = _identifier(
        raw.get("producer_id"),
        "qualified_collection_readiness_evidence.producer_id",
    )
    evidence_items = raw.get("evidence")
    if not isinstance(evidence_items, list):
        raise PositionVectorCampaignError(
            "qualified_collection_readiness_evidence.evidence must be a list"
        )

    required = [
        item["requirement"] for item in reproduced_plan["evidence_requirements"]
    ]
    supplied_by_requirement: dict[str, dict[str, str]] = {}
    for index, value in enumerate(evidence_items):
        label = f"qualified_collection_readiness_evidence.evidence[{index}]"
        item = _mapping(value, label)
        _exact(item, _QUALIFIED_COLLECTION_READINESS_EVIDENCE_ITEM_FIELDS, label)
        requirement = item.get("requirement")
        if requirement not in required:
            raise PositionVectorCampaignError(f"{label}.requirement is unknown")
        if requirement in supplied_by_requirement:
            raise PositionVectorCampaignError(
                "qualified collection readiness evidence repeats a requirement"
            )
        reviewer_id = _identifier(item.get("reviewer_id"), f"{label}.reviewer_id")
        if reviewer_id == producer_id:
            raise PositionVectorCampaignError(
                f"{label}.reviewer_id is not independent of the producer"
            )
        decision = item.get("decision")
        if decision not in {"ACCEPT", "REJECT"}:
            raise PositionVectorCampaignError(f"{label}.decision is invalid")
        supplied_by_requirement[requirement] = {
            "requirement": requirement,
            "evidence_sha256": _digest(
                item.get("evidence_sha256"), f"{label}.evidence_sha256"
            ),
            "reviewer_id": reviewer_id,
            "decision": decision,
        }

    assessments = []
    blockers = []
    normalized_items = []
    for requirement in required:
        item = supplied_by_requirement.get(requirement)
        if item is None:
            assessments.append(
                {
                    "requirement": requirement,
                    "status": "EVIDENCE_MISSING",
                    "evidence_sha256": None,
                    "reviewer_id": None,
                }
            )
            blockers.append(f"{requirement}_EVIDENCE_REQUIRED")
            continue
        normalized_items.append(item)
        status = (
            "EVIDENCE_ACCEPTED"
            if item["decision"] == "ACCEPT"
            else "EVIDENCE_REJECTED"
        )
        assessments.append(
            {
                "requirement": requirement,
                "status": status,
                "evidence_sha256": item["evidence_sha256"],
                "reviewer_id": item["reviewer_id"],
            }
        )
        if item["decision"] == "REJECT":
            blockers.append(f"{requirement}_EVIDENCE_REJECTED")

    normalized_evidence = {
        "schema": QUALIFIED_COLLECTION_READINESS_EVIDENCE_SCHEMA,
        **bindings,
        "producer_id": producer_id,
        "evidence": normalized_items,
    }
    return {
        "schema": QUALIFIED_COLLECTION_READINESS_ASSESSMENT_SCHEMA,
        "status": (
            "QUALIFIED_COLLECTION_READINESS_COMPLETE"
            if not blockers
            else "QUALIFIED_COLLECTION_READINESS_BLOCKED"
        ),
        "dataset_id": reproduced_plan["dataset_id"],
        **bindings,
        "evidence_sha256": canonical_sha256(normalized_evidence),
        "requirement_assessments": assessments,
        "blockers": blockers,
        "limitations": [
            "This assessment validates declared hashes, decisions, and reviewer "
            "independence; it does not inspect referenced evidence content.",
            "QUALIFIED_COLLECTION_READINESS_COMPLETE does not itself prove physical "
            "correctness, reachability, collision clearance, or safe motion.",
            "This assessment does not authorize hardware access, motion, or collection.",
        ],
        "authority": dict(reproduced_plan["authority"]),
    }


def create_qualified_collection_readiness_handoff(
    *,
    inventory_document: Mapping[str, Any],
    admission_receipt_document: Mapping[str, Any],
    training_split_document: Mapping[str, Any],
    collection_plan_document: Mapping[str, Any],
    observations_document: Mapping[str, Any],
    preparation_receipt_document: Mapping[str, Any],
    readiness_plan_document: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    assessment_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Create an artifact handoff for one complete readiness assessment.

    This receipt binds the already prepared plan and observation template to
    the accepted readiness declarations. It grants no collection or motion
    authority and performs no hardware access.
    """

    reproduced = assess_qualified_collection_readiness_evidence(
        inventory_document=inventory_document,
        admission_receipt_document=admission_receipt_document,
        training_split_document=training_split_document,
        collection_plan_document=collection_plan_document,
        observations_document=observations_document,
        preparation_receipt_document=preparation_receipt_document,
        readiness_plan_document=readiness_plan_document,
        evidence_document=evidence_document,
        policy=policy,
    )
    supplied = _mapping(
        assessment_document, "qualified_collection_readiness_assessment"
    )
    if dict(supplied) != reproduced:
        raise PositionVectorCampaignError(
            "qualified collection readiness assessment does not reproduce"
        )
    if reproduced["status"] != "QUALIFIED_COLLECTION_READINESS_COMPLETE":
        raise PositionVectorCampaignError(
            "qualified collection readiness assessment is not complete"
        )

    readiness_plan = _mapping(
        readiness_plan_document, "qualified_collection_readiness_plan"
    )
    evidence = _mapping(
        evidence_document, "qualified_collection_readiness_evidence"
    )
    return {
        "schema": QUALIFIED_COLLECTION_READINESS_HANDOFF_SCHEMA,
        "status": "QUALIFIED_COLLECTION_READINESS_HANDOFF_READY",
        "dataset_id": reproduced["dataset_id"],
        "inventory_sha256": reproduced["inventory_sha256"],
        "admission_receipt_sha256": readiness_plan[
            "admission_receipt_sha256"
        ],
        "training_split_sha256": readiness_plan["training_split_sha256"],
        "collection_plan_sha256": reproduced["collection_plan_sha256"],
        "observations_sha256": readiness_plan["observations_sha256"],
        "preparation_receipt_sha256": reproduced[
            "preparation_receipt_sha256"
        ],
        "readiness_plan_sha256": reproduced["readiness_plan_sha256"],
        "evidence_sha256": reproduced["evidence_sha256"],
        "readiness_assessment_sha256": canonical_sha256(reproduced),
        "controller_binding": dict(readiness_plan["controller_binding"]),
        "attachment_profile": reproduced["attachment_profile"],
        "truth_method": readiness_plan["truth_method"],
        "pose_labels": list(readiness_plan["pose_labels"]),
        "evidence_producer_id": evidence["producer_id"],
        "accepted_evidence": [
            {
                "requirement": item["requirement"],
                "evidence_sha256": item["evidence_sha256"],
                "reviewer_id": item["reviewer_id"],
            }
            for item in reproduced["requirement_assessments"]
        ],
        "next_required_gate": "RETAINED_STATIONARY_OBSERVATION_COLLECTION",
        "blockers": [],
        "limitations": [
            "This receipt reproduces and binds accepted evidence declarations; it "
            "does not inspect the referenced evidence content.",
            "QUALIFIED_COLLECTION_READINESS_HANDOFF_READY is an artifact-transfer "
            "state, not authorization to access hardware or collect observations.",
            "Physical collection still requires the separate operator and safety "
            "controls applicable to the installed system.",
        ],
        "authority": dict(reproduced["authority"]),
    }


def ingest_qualified_stationary_observation(
    *,
    inventory_document: Mapping[str, Any],
    admission_receipt_document: Mapping[str, Any],
    training_split_document: Mapping[str, Any],
    collection_plan_document: Mapping[str, Any],
    observations_document: Mapping[str, Any],
    preparation_receipt_document: Mapping[str, Any],
    readiness_plan_document: Mapping[str, Any],
    readiness_evidence_document: Mapping[str, Any],
    readiness_assessment_document: Mapping[str, Any],
    readiness_handoff_document: Mapping[str, Any],
    observation_evidence_document: Mapping[str, Any],
    policy: CampaignPolicy = CampaignPolicy(),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ingest one retained stationary observation into its exact empty slot.

    This is a pure artifact operation. The caller supplies retained feedback,
    camera, and independent truth hashes; this function neither opens hardware
    nor performs capture or feedback requests.
    """

    expected_handoff = create_qualified_collection_readiness_handoff(
        inventory_document=inventory_document,
        admission_receipt_document=admission_receipt_document,
        training_split_document=training_split_document,
        collection_plan_document=collection_plan_document,
        observations_document=collection_observations_template(
            collection_plan_document
        ),
        preparation_receipt_document=preparation_receipt_document,
        readiness_plan_document=readiness_plan_document,
        evidence_document=readiness_evidence_document,
        assessment_document=readiness_assessment_document,
        policy=policy,
    )
    supplied_handoff = _mapping(
        readiness_handoff_document, "qualified_collection_readiness_handoff"
    )
    if dict(supplied_handoff) != expected_handoff:
        raise PositionVectorCampaignError(
            "qualified collection readiness handoff does not reproduce"
        )

    plan = load_collection_plan(collection_plan_document)
    observations = _mapping(observations_document, "qualified_observations")
    _exact(observations, _OBSERVATIONS_FIELDS, "qualified_observations")
    if observations.get("schema") != OBSERVATIONS_SCHEMA:
        raise PositionVectorCampaignError("qualified observations schema mismatch")
    if observations.get("plan_sha256") != canonical_sha256(plan):
        raise PositionVectorCampaignError("qualified observations plan hash mismatch")
    values = observations.get("samples")
    if not isinstance(values, list) or len(values) != len(plan["slots"]):
        raise PositionVectorCampaignError(
            "qualified observations do not preserve every planned slot"
        )

    normalized_samples = []
    filled_truth_hashes = []
    empty_fields = _OBSERVATION_FIELDS - {"sample_id"}
    for index, (value, slot) in enumerate(zip(values, plan["slots"], strict=True)):
        label = f"qualified_observations.samples[{index}]"
        observation = _mapping(value, label)
        _exact(observation, _OBSERVATION_FIELDS, label)
        if observation.get("sample_id") != slot["sample_id"]:
            raise PositionVectorCampaignError(
                "qualified observation sample order differs from plan"
            )
        if all(observation.get(name) is None for name in empty_fields):
            normalized_samples.append(dict(observation))
            continue
        validated = _sample(
            {
                **dict(observation),
                "split": slot["split"],
                "source_pose": slot["source_pose"],
                "truth_method": slot["truth_method"],
            },
            index,
        )
        normalized = {
            name: validated[name] for name in _OBSERVATION_FIELDS
        }
        if normalized != dict(observation):
            raise PositionVectorCampaignError(
                "qualified observations do not reproduce after validation"
            )
        normalized_samples.append(normalized)
        filled_truth_hashes.append(normalized["truth_evidence_sha256"])
    if len(set(filled_truth_hashes)) != len(filled_truth_hashes):
        raise PositionVectorCampaignError(
            "qualified observation truth evidence hashes must be unique"
        )
    normalized_observations = {
        "schema": OBSERVATIONS_SCHEMA,
        "plan_sha256": canonical_sha256(plan),
        "samples": normalized_samples,
    }

    raw = _mapping(
        observation_evidence_document, "qualified_stationary_observation_evidence"
    )
    _exact(
        raw,
        _QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_FIELDS,
        "qualified_stationary_observation_evidence",
    )
    if raw.get("schema") != QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_SCHEMA:
        raise PositionVectorCampaignError(
            "qualified stationary observation evidence schema mismatch"
        )
    if raw.get("readiness_handoff_sha256") != canonical_sha256(expected_handoff):
        raise PositionVectorCampaignError(
            "qualified stationary observation handoff binding mismatch"
        )
    current_hash = canonical_sha256(normalized_observations)
    if raw.get("current_observations_sha256") != current_hash:
        raise PositionVectorCampaignError(
            "qualified stationary observation current-template binding mismatch"
        )
    sample_id = _identifier(
        raw.get("sample_id"), "qualified_stationary_observation_evidence.sample_id"
    )
    matching_indexes = [
        index for index, slot in enumerate(plan["slots"])
        if slot["sample_id"] == sample_id
    ]
    if len(matching_indexes) != 1:
        raise PositionVectorCampaignError(
            "qualified stationary observation sample is not in the plan"
        )
    target_index = matching_indexes[0]
    target_slot = plan["slots"][target_index]
    if raw.get("source_pose") != target_slot["source_pose"]:
        raise PositionVectorCampaignError(
            "qualified stationary observation source pose mismatch"
        )
    if any(
        normalized_samples[target_index].get(name) is not None
        for name in empty_fields
    ):
        raise PositionVectorCampaignError(
            "qualified stationary observation slot is already filled"
        )

    producer_id = _identifier(
        raw.get("observation_producer_id"),
        "qualified_stationary_observation_evidence.observation_producer_id",
    )
    reviewer_id = _identifier(
        raw.get("truth_reviewer_id"),
        "qualified_stationary_observation_evidence.truth_reviewer_id",
    )
    if reviewer_id == producer_id:
        raise PositionVectorCampaignError(
            "qualified stationary observation truth reviewer is not independent"
        )
    retained = _sample(
        {
            "sample_id": sample_id,
            "split": target_slot["split"],
            "source_pose": target_slot["source_pose"],
            "raw_position_counts": raw.get("raw_position_counts"),
            "canonical_joints_rad": raw.get("canonical_joints_rad"),
            "truth_method": target_slot["truth_method"],
            "truth_evidence_sha256": raw.get("truth_evidence_sha256"),
            "stationary": raw.get("stationary"),
            "motion_active": raw.get("motion_active"),
            "trajectory_progress_permille": raw.get(
                "trajectory_progress_permille"
            ),
        },
        target_index,
    )
    if retained["truth_evidence_sha256"] in filled_truth_hashes:
        raise PositionVectorCampaignError(
            "qualified stationary observation truth evidence hash is reused"
        )
    controller_feedback_hash = _digest(
        raw.get("controller_feedback_evidence_sha256"),
        "qualified_stationary_observation_evidence.controller_feedback_evidence_sha256",
    )
    camera_receipt_hash = _digest(
        raw.get("camera_observation_receipt_sha256"),
        "qualified_stationary_observation_evidence.camera_observation_receipt_sha256",
    )
    normalized_evidence = {
        "schema": QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_SCHEMA,
        "readiness_handoff_sha256": canonical_sha256(expected_handoff),
        "current_observations_sha256": current_hash,
        "sample_id": sample_id,
        "source_pose": target_slot["source_pose"],
        "observation_producer_id": producer_id,
        "truth_reviewer_id": reviewer_id,
        "raw_position_counts": retained["raw_position_counts"],
        "canonical_joints_rad": retained["canonical_joints_rad"],
        "controller_feedback_evidence_sha256": controller_feedback_hash,
        "camera_observation_receipt_sha256": camera_receipt_hash,
        "truth_evidence_sha256": retained["truth_evidence_sha256"],
        "stationary": True,
        "motion_active": False,
        "trajectory_progress_permille": 1000,
    }
    if normalized_evidence != dict(raw):
        raise PositionVectorCampaignError(
            "qualified stationary observation evidence does not reproduce"
        )

    updated_samples = [dict(item) for item in normalized_samples]
    updated_samples[target_index] = {
        name: retained[name] for name in _OBSERVATION_FIELDS
    }
    updated_observations = {
        "schema": OBSERVATIONS_SCHEMA,
        "plan_sha256": canonical_sha256(plan),
        "samples": updated_samples,
    }
    filled_count = sum(
        item["truth_evidence_sha256"] is not None for item in updated_samples
    )
    remaining_count = len(updated_samples) - filled_count
    receipt = {
        "schema": QUALIFIED_STATIONARY_OBSERVATION_INGESTION_RECEIPT_SCHEMA,
        "status": "QUALIFIED_STATIONARY_OBSERVATION_INGESTED",
        "dataset_id": plan["dataset_id"],
        "sample_id": sample_id,
        "source_pose": target_slot["source_pose"],
        "split": target_slot["split"],
        "readiness_handoff_sha256": canonical_sha256(expected_handoff),
        "collection_plan_sha256": canonical_sha256(plan),
        "previous_observations_sha256": current_hash,
        "observation_evidence_sha256": canonical_sha256(normalized_evidence),
        "resulting_observations_sha256": canonical_sha256(updated_observations),
        "controller_feedback_evidence_sha256": controller_feedback_hash,
        "camera_observation_receipt_sha256": camera_receipt_hash,
        "truth_evidence_sha256": retained["truth_evidence_sha256"],
        "observation_producer_id": producer_id,
        "truth_reviewer_id": reviewer_id,
        "filled_sample_count": filled_count,
        "remaining_sample_count": remaining_count,
        "next_required_gate": (
            "QUALIFIED_OBSERVATION_SET_COMPILATION"
            if remaining_count == 0
            else "RETAINED_STATIONARY_OBSERVATION_COLLECTION"
        ),
        "limitations": [
            "This receipt validates retained declarations and hashes; it does not "
            "perform camera capture or controller feedback requests.",
            "The referenced camera, feedback, and joint-truth evidence remains "
            "subject to its own retained-evidence review.",
            "This ingestion grants no hardware, collection, or motion authority.",
        ],
        "authority": dict(expected_handoff["authority"]),
    }
    return updated_observations, receipt


def create_assessed_collection_package(
    *,
    readiness_document: Mapping[str, Any],
    dataset_id: str,
    producer_id: str,
    training_poses: list[str] | tuple[str, ...],
    held_out_poses: list[str] | tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prepare a plan from the exact facts in a passing readiness report."""

    readiness = load_collection_readiness(readiness_document)
    if not readiness["ready_to_prepare"]:
        raise PositionVectorCampaignError(
            "collection readiness is blocked: " + ", ".join(readiness["blockers"])
        )
    if not isinstance(training_poses, (list, tuple)) or not isinstance(
        held_out_poses, (list, tuple)
    ):
        raise PositionVectorCampaignError("assessed collection poses must be arrays")
    selected_poses = [
        _identifier(value, f"training_poses[{index}]")
        for index, value in enumerate(training_poses)
    ] + [
        _identifier(value, f"held_out_poses[{index}]")
        for index, value in enumerate(held_out_poses)
    ]
    retained_poses = readiness["retained_pose_labels"]
    if len(selected_poses) != len(set(selected_poses)):
        raise PositionVectorCampaignError("assessed collection poses must be unique")
    if set(selected_poses) != set(retained_poses):
        raise PositionVectorCampaignError(
            "assessed collection poses do not match readiness evidence"
        )
    requirements = readiness["requirements"]
    policy = CampaignPolicy(
        minimum_training_samples=requirements["minimum_training_samples"],
        minimum_held_out_samples=requirements["minimum_held_out_samples"],
    )
    identity = readiness["controller_identity"]
    plan = create_collection_plan(
        dataset_id=dataset_id,
        producer_id=producer_id,
        controller_binding={
            **identity,
            "firmware_sha256": readiness["installed_firmware_sha256"],
        },
        attachment_profile=readiness["attachment_profile"],
        training_poses=training_poses,
        held_out_poses=held_out_poses,
        truth_method=readiness["truth_method"],
        policy=policy,
    )
    observations = collection_observations_template(plan)
    receipt = {
        "schema": PREPARATION_RECEIPT_SCHEMA,
        "status": "PREPARED_FROM_ASSESSED_EVIDENCE",
        "dataset_id": plan["dataset_id"],
        "producer_id": plan["producer_id"],
        "readiness_sha256": canonical_sha256(readiness),
        "plan_sha256": canonical_sha256(plan),
        "observations_sha256": canonical_sha256(observations),
        "authority": dict(plan["authority"]),
    }
    return plan, observations, receipt


def create_reviewed_collection_package(
    *,
    evidence_document: Mapping[str, Any],
    readiness_document: Mapping[str, Any],
    readiness_receipt_document: Mapping[str, Any],
    training_poses: list[str] | tuple[str, ...],
    held_out_poses: list[str] | tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prepare directly from one exact reviewed-evidence assessment chain."""

    expected_readiness, expected_readiness_receipt = assess_reviewed_readiness_evidence(
        evidence_document
    )
    supplied_readiness = load_collection_readiness(readiness_document)
    if supplied_readiness != expected_readiness:
        raise PositionVectorCampaignError(
            "reviewed readiness does not match the retained evidence"
        )
    supplied_readiness_receipt = _mapping(
        readiness_receipt_document, "readiness_evidence_receipt"
    )
    if dict(supplied_readiness_receipt) != expected_readiness_receipt:
        raise PositionVectorCampaignError(
            "readiness evidence receipt does not reproduce"
        )
    evidence = _mapping(evidence_document, "readiness_evidence")
    plan, observations, assessed_receipt = create_assessed_collection_package(
        readiness_document=supplied_readiness,
        dataset_id=evidence["campaign_id"],
        producer_id=evidence["producer_id"],
        training_poses=training_poses,
        held_out_poses=held_out_poses,
    )
    receipt = {
        "schema": REVIEWED_PREPARATION_RECEIPT_SCHEMA,
        "status": "PREPARED_FROM_REVIEWED_EVIDENCE",
        "campaign_id": evidence["campaign_id"],
        "producer_id": evidence["producer_id"],
        "evidence_sha256": expected_readiness_receipt["evidence_sha256"],
        "readiness_evidence_receipt_sha256": canonical_sha256(
            expected_readiness_receipt
        ),
        "readiness_sha256": canonical_sha256(supplied_readiness),
        "assessed_preparation_receipt_sha256": canonical_sha256(assessed_receipt),
        "plan_sha256": canonical_sha256(plan),
        "observations_sha256": canonical_sha256(observations),
        "authority": dict(plan["authority"]),
    }
    return plan, observations, receipt


def load_collection_plan(document: Mapping[str, Any]) -> dict[str, Any]:
    """Strict-decode a frozen, offline collection plan."""

    raw = _mapping(document, "collection_plan")
    _exact(raw, _PLAN_FIELDS, "collection_plan")
    if raw.get("schema") != PLAN_SCHEMA:
        raise PositionVectorCampaignError("collection plan schema mismatch")
    if raw.get("position_order_servo_ids") != list(SERVO_ORDER):
        raise PositionVectorCampaignError("collection plan servo order mismatch")
    if raw.get("joint_order") != list(JOINT_ORDER):
        raise PositionVectorCampaignError("collection plan joint order mismatch")
    attachment = raw.get("attachment_profile")
    if attachment not in SUPPORTED_ATTACHMENTS:
        raise PositionVectorCampaignError("collection plan attachment profile is invalid")
    policy = _policy(raw.get("policy"), label="collection_plan.policy")
    authority = _mapping(raw.get("authority"), "collection_plan.authority")
    _exact(authority, _PLAN_AUTHORITY_FIELDS, "collection_plan.authority")
    if authority != {
        "controller_opened": False,
        "camera_opened": False,
        "commands_sent": 0,
        "motion_authorized": False,
        "physical_authority": False,
    }:
        raise PositionVectorCampaignError("collection plan cannot grant physical authority")
    values = raw.get("slots")
    if not isinstance(values, list):
        raise PositionVectorCampaignError("collection plan slots must be an array")
    slots = []
    for index, value in enumerate(values):
        label = f"collection_plan.slots[{index}]"
        slot = _mapping(value, label)
        _exact(slot, _PLAN_SLOT_FIELDS, label)
        split = slot.get("split")
        if split not in {"TRAINING", "HELD_OUT"}:
            raise PositionVectorCampaignError(f"{label}.split is invalid")
        method = slot.get("truth_method")
        if method not in TRUTH_METHODS:
            raise PositionVectorCampaignError(f"{label}.truth_method is unsupported")
        slots.append(
            {
                "sample_id": _identifier(slot.get("sample_id"), f"{label}.sample_id"),
                "split": split,
                "source_pose": _identifier(slot.get("source_pose"), f"{label}.source_pose"),
                "truth_method": method,
            }
        )
    ids = [slot["sample_id"] for slot in slots]
    poses = [slot["source_pose"] for slot in slots]
    if len(set(ids)) != len(ids):
        raise PositionVectorCampaignError("collection plan sample IDs must be unique")
    if len(set(poses)) != len(poses):
        raise PositionVectorCampaignError("collection plan source poses must be unique")
    if sum(slot["split"] == "TRAINING" for slot in slots) < policy.minimum_training_samples:
        raise PositionVectorCampaignError("collection plan has insufficient training slots")
    if sum(slot["split"] == "HELD_OUT" for slot in slots) < policy.minimum_held_out_samples:
        raise PositionVectorCampaignError("collection plan has insufficient held-out slots")
    return {
        "schema": PLAN_SCHEMA,
        "dataset_id": _identifier(raw.get("dataset_id"), "dataset_id"),
        "producer_id": _identifier(raw.get("producer_id"), "producer_id"),
        "controller_binding": _controller(raw.get("controller_binding")),
        "attachment_profile": attachment,
        "position_order_servo_ids": list(SERVO_ORDER),
        "joint_order": list(JOINT_ORDER),
        "policy": policy.to_dict(),
        "slots": slots,
        "authority": dict(authority),
    }


def collection_observations_template(plan_document: Mapping[str, Any]) -> dict[str, Any]:
    """Return explicit empty evidence slots for a previously frozen plan."""

    plan = load_collection_plan(plan_document)
    return {
        "schema": OBSERVATIONS_SCHEMA,
        "plan_sha256": canonical_sha256(plan),
        "samples": [
            {
                "sample_id": slot["sample_id"],
                "raw_position_counts": None,
                "canonical_joints_rad": None,
                "truth_evidence_sha256": None,
                "stationary": None,
                "motion_active": None,
                "trajectory_progress_permille": None,
            }
            for slot in plan["slots"]
        ],
    }


def compile_planned_dataset(
    plan_document: Mapping[str, Any], observations_document: Mapping[str, Any]
) -> dict[str, Any]:
    """Combine a frozen plan with complete retained observations."""

    plan = load_collection_plan(plan_document)
    observations = _mapping(observations_document, "observations")
    _exact(observations, _OBSERVATIONS_FIELDS, "observations")
    if observations.get("schema") != OBSERVATIONS_SCHEMA:
        raise PositionVectorCampaignError("observations schema mismatch")
    if observations.get("plan_sha256") != canonical_sha256(plan):
        raise PositionVectorCampaignError("observations plan hash mismatch")
    values = observations.get("samples")
    if not isinstance(values, list) or len(values) != len(plan["slots"]):
        raise PositionVectorCampaignError("observations do not fill every planned slot")
    samples = []
    for index, (value, slot) in enumerate(zip(values, plan["slots"], strict=True)):
        label = f"observations.samples[{index}]"
        observation = _mapping(value, label)
        _exact(observation, _OBSERVATION_FIELDS, label)
        if observation.get("sample_id") != slot["sample_id"]:
            raise PositionVectorCampaignError("observation sample order differs from plan")
        samples.append(
            {
                **dict(observation),
                "split": slot["split"],
                "source_pose": slot["source_pose"],
                "truth_method": slot["truth_method"],
            }
        )
    return load_campaign_dataset(
        {
            "schema": DATASET_SCHEMA,
            "dataset_id": plan["dataset_id"],
            "producer_id": plan["producer_id"],
            "controller_binding": plan["controller_binding"],
            "attachment_profile": plan["attachment_profile"],
            "position_order_servo_ids": list(SERVO_ORDER),
            "joint_order": list(JOINT_ORDER),
            "samples": samples,
        }
    )


def create_reviewed_dataset_package(
    *,
    evidence_document: Mapping[str, Any],
    readiness_document: Mapping[str, Any],
    readiness_receipt_document: Mapping[str, Any],
    preparation_receipt_document: Mapping[str, Any],
    plan_document: Mapping[str, Any],
    observations_document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile observations only after reproducing their reviewed preparation chain."""

    supplied_plan = load_collection_plan(plan_document)
    training_poses = [
        slot["source_pose"]
        for slot in supplied_plan["slots"]
        if slot["split"] == "TRAINING"
    ]
    held_out_poses = [
        slot["source_pose"]
        for slot in supplied_plan["slots"]
        if slot["split"] == "HELD_OUT"
    ]
    expected_plan, _, expected_preparation_receipt = (
        create_reviewed_collection_package(
            evidence_document=evidence_document,
            readiness_document=readiness_document,
            readiness_receipt_document=readiness_receipt_document,
            training_poses=training_poses,
            held_out_poses=held_out_poses,
        )
    )
    if supplied_plan != expected_plan:
        raise PositionVectorCampaignError(
            "collection plan does not reproduce from reviewed preparation"
        )
    supplied_preparation_receipt = _mapping(
        preparation_receipt_document, "reviewed_preparation_receipt"
    )
    if dict(supplied_preparation_receipt) != expected_preparation_receipt:
        raise PositionVectorCampaignError(
            "reviewed preparation receipt does not reproduce"
        )
    observations = _mapping(observations_document, "observations")
    dataset = compile_planned_dataset(supplied_plan, observations)
    receipt = {
        "schema": REVIEWED_COMPILATION_RECEIPT_SCHEMA,
        "status": "COMPILED_FROM_REVIEWED_COLLECTION",
        "campaign_id": expected_preparation_receipt["campaign_id"],
        "producer_id": expected_preparation_receipt["producer_id"],
        "evidence_sha256": expected_preparation_receipt["evidence_sha256"],
        "readiness_evidence_receipt_sha256": expected_preparation_receipt[
            "readiness_evidence_receipt_sha256"
        ],
        "readiness_sha256": expected_preparation_receipt["readiness_sha256"],
        "reviewed_preparation_receipt_sha256": canonical_sha256(
            expected_preparation_receipt
        ),
        "plan_sha256": canonical_sha256(supplied_plan),
        "observations_sha256": canonical_sha256(observations),
        "dataset_sha256": canonical_sha256(dataset),
        "authority": dict(supplied_plan["authority"]),
    }
    return dataset, receipt


def _linear_fit(points: list[tuple[int, float]], joint: str) -> tuple[float, float]:
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    denominator = sum((point[0] - mean_x) ** 2 for point in points)
    if denominator == 0:
        raise PositionVectorCampaignError(f"{joint} training counts have no span")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
    if not math.isfinite(slope) or abs(slope) < 1e-12:
        raise PositionVectorCampaignError(f"{joint} fitted scale is degenerate")
    count_zero = mean_x - mean_y / slope
    if not 0.0 <= count_zero <= 4095.0 or not -0.1 <= slope <= 0.1:
        raise PositionVectorCampaignError(f"{joint} fitted parameters are outside bounds")
    return count_zero, slope


def fit_campaign_dataset(
    document: Mapping[str, Any],
    *,
    calibration_id: str,
    policy: CampaignPolicy = CampaignPolicy(),
) -> dict[str, Any]:
    """Fit affine joint models and evaluate a disjoint held-out split."""

    dataset = load_campaign_dataset(document)
    calibration = _identifier(calibration_id, "calibration_id")
    training = [item for item in dataset["samples"] if item["split"] == "TRAINING"]
    held_out = [item for item in dataset["samples"] if item["split"] == "HELD_OUT"]
    if len(training) < policy.minimum_training_samples:
        raise PositionVectorCampaignError("insufficient training samples")
    if len(held_out) < policy.minimum_held_out_samples:
        raise PositionVectorCampaignError("insufficient held-out samples")

    joints: list[dict[str, Any]] = []
    for joint in JOINT_ORDER:
        primary = PRIMARY_INDEX[joint]
        points = [
            (item["raw_position_counts"][primary], item["canonical_joints_rad"][joint])
            for item in training
        ]
        span = max(point[0] for point in points) - min(point[0] for point in points)
        if span < policy.minimum_training_count_span:
            raise PositionVectorCampaignError(f"{joint} training count span is insufficient")
        zero, scale = _linear_fit(points, joint)
        held_errors = [
            abs(
                (item["raw_position_counts"][primary] - zero) * scale
                - item["canonical_joints_rad"][joint]
            )
            for item in held_out
        ]
        maximum_error = max(held_errors)
        if maximum_error > policy.accepted_max_abs_error_rad:
            raise PositionVectorCampaignError(f"{joint} held-out error exceeds policy")
        all_angles = [item["canonical_joints_rad"][joint] for item in dataset["samples"]]
        joints.append(
            {
                "joint": joint,
                "primary_index": primary,
                "count_zero": zero,
                "radians_per_count": scale,
                "minimum_rad": min(all_angles),
                "maximum_rad": max(all_angles),
                "training_sample_count": len(training),
                "held_out_sample_count": len(held_out),
                "held_out_max_abs_error_rad": maximum_error,
                "accepted_max_abs_error_rad": policy.accepted_max_abs_error_rad,
                "training_count_span": span,
            }
        )

    training_sums = [item["raw_position_counts"][1] + item["raw_position_counts"][2]
                     for item in training]
    held_out_sums = [item["raw_position_counts"][1] + item["raw_position_counts"][2]
                     for item in held_out]
    nominal_sum = round(sum(training_sums) / len(training_sums))
    training_residual = max(abs(value - nominal_sum) for value in training_sums)
    held_out_residual = max(abs(value - nominal_sum) for value in held_out_sums)
    if max(training_residual, held_out_residual) > policy.shoulder_runtime_tolerance_counts:
        raise PositionVectorCampaignError("mirrored shoulder residual exceeds policy")

    return {
        "schema": FIT_REPORT_SCHEMA,
        "status": "PASS",
        "calibration_id": calibration,
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": canonical_sha256(dataset),
        "producer_id": dataset["producer_id"],
        "attachment_profile": dataset["attachment_profile"],
        "policy": policy.to_dict(),
        "joints": joints,
        "shoulder_pair": {
            "driving_index": 1,
            "driven_index": 2,
            "nominal_sum_counts": nominal_sum,
            "runtime_tolerance_counts": policy.shoulder_runtime_tolerance_counts,
            "training_max_abs_residual_counts": training_residual,
            "held_out_max_abs_residual_counts": held_out_residual,
        },
        "motion_authorized": False,
        "physical_authority": False,
    }


def _policy(value: Any, *, label: str = "fit_report.policy") -> CampaignPolicy:
    raw = _mapping(value, label)
    if set(raw) != set(CampaignPolicy().to_dict()):
        raise PositionVectorCampaignError("fit report policy fields do not match")
    try:
        return CampaignPolicy(**raw)
    except TypeError as exc:
        raise PositionVectorCampaignError("fit report policy is invalid") from exc


def _review(
    document: Mapping[str, Any], *, dataset_sha256: str, fit_report_sha256: str,
    producer_id: str,
) -> dict[str, Any]:
    raw = _mapping(document, "review")
    _exact(raw, _REVIEW_FIELDS, "review")
    if raw.get("schema") != REVIEW_SCHEMA:
        raise PositionVectorCampaignError("review schema mismatch")
    if raw.get("dataset_sha256") != dataset_sha256:
        raise PositionVectorCampaignError("review dataset hash mismatch")
    if raw.get("fit_report_sha256") != fit_report_sha256:
        raise PositionVectorCampaignError("review fit report hash mismatch")
    if raw.get("producer_id") != producer_id:
        raise PositionVectorCampaignError("review producer mismatch")
    reviewer = _identifier(raw.get("reviewer_id"), "reviewer_id")
    if reviewer == producer_id:
        raise PositionVectorCampaignError("reviewer must be independent of producer")
    if raw.get("decision") != "ACCEPT":
        raise PositionVectorCampaignError("review decision is not ACCEPT")
    reviewed_at = raw.get("reviewed_at")
    if not isinstance(reviewed_at, str):
        raise PositionVectorCampaignError("reviewed_at is invalid")
    try:
        timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PositionVectorCampaignError("reviewed_at is invalid") from exc
    if timestamp.tzinfo is None:
        raise PositionVectorCampaignError("reviewed_at must include a UTC offset")
    normalized = dict(raw)
    normalized["review_notes_sha256"] = _digest(
        raw.get("review_notes_sha256"), "review_notes_sha256"
    )
    return normalized


def build_calibration_artifact(
    dataset_document: Mapping[str, Any],
    fit_report_document: Mapping[str, Any],
    review_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify dataset, deterministic fit, and independent review, then emit v1."""

    dataset = load_campaign_dataset(dataset_document)
    fit = _mapping(fit_report_document, "fit_report")
    policy = _policy(fit.get("policy"))
    expected = fit_campaign_dataset(
        dataset, calibration_id=_identifier(fit.get("calibration_id"), "calibration_id"),
        policy=policy,
    )
    if canonical_bytes(fit) != canonical_bytes(expected):
        raise PositionVectorCampaignError("fit report does not reproduce from the dataset")
    dataset_hash = canonical_sha256(dataset)
    fit_hash = canonical_sha256(expected)
    review = _review(
        review_document,
        dataset_sha256=dataset_hash,
        fit_report_sha256=fit_hash,
        producer_id=dataset["producer_id"],
    )
    review_hash = canonical_sha256(review)
    if len({dataset_hash, fit_hash, review_hash}) != 3:
        raise PositionVectorCampaignError("campaign evidence hashes are not distinct")
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "calibration_id": expected["calibration_id"],
        "response_profile": PROFILE,
        "controller_binding": dataset["controller_binding"],
        "position_order_servo_ids": list(SERVO_ORDER),
        "joint_order": list(JOINT_ORDER),
        "joints": [
            {key: value for key, value in row.items() if key != "training_count_span"}
            for row in expected["joints"]
        ],
        "shoulder_pair": expected["shoulder_pair"],
        "evidence": {
            "dataset_sha256": dataset_hash,
            "fit_report_sha256": fit_hash,
            "independent_review_sha256": review_hash,
        },
    }
    load_position_vector_calibration(artifact)
    return artifact


def _read_json(path: str) -> Mapping[str, Any]:
    try:
        value = json.loads(Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise PositionVectorCampaignError(f"cannot read JSON input {path}") from exc
    return _mapping(value, path)


def _write_new(path: str, value: Mapping[str, Any]) -> None:
    try:
        with Path(path).open("xb") as stream:
            stream.write(canonical_bytes(value) + b"\n")
    except FileExistsError as exc:
        raise PositionVectorCampaignError(f"refusing to replace existing output {path}") from exc


def main(argv: list[str] | None = None) -> int:
    """Assess, prepare, compile, fit, or finalize evidence without hardware imports."""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    assess_parser = commands.add_parser(
        "assess", help="report retained-evidence blockers before preparing a plan"
    )
    assess_parser.add_argument("--vid", required=True)
    assess_parser.add_argument("--pid", required=True)
    assess_parser.add_argument("--unit-serial", required=True)
    assess_parser.add_argument("--firmware-sha256")
    assess_parser.add_argument("--attachment-profile", choices=SUPPORTED_ATTACHMENTS, required=True)
    assess_parser.add_argument("--truth-method", choices=TRUTH_METHODS, required=True)
    assess_parser.add_argument("--retained-pose", action="append", default=[])
    assess_parser.add_argument("--output", required=True)
    reviewed_assess_parser = commands.add_parser(
        "assess-reviewed", help="derive readiness from reviewed retained evidence"
    )
    reviewed_assess_parser.add_argument("--evidence", required=True)
    reviewed_assess_parser.add_argument("--readiness-output", required=True)
    reviewed_assess_parser.add_argument("--receipt-output", required=True)
    candidate_audit_parser = commands.add_parser(
        "audit-candidates",
        help="audit whether retained candidate counts can meet fit coverage",
    )
    candidate_audit_parser.add_argument("--inventory", required=True)
    candidate_audit_parser.add_argument("--output", required=True)
    candidate_augmentation_parser = commands.add_parser(
        "plan-candidate-augmentation",
        help="derive zero-authority count ranges for candidate coverage gaps",
    )
    candidate_augmentation_parser.add_argument("--inventory", required=True)
    candidate_augmentation_parser.add_argument("--output", required=True)
    candidate_preflight_parser = commands.add_parser(
        "preflight-candidate-augmentation",
        help="evaluate one proposed count vector against catalog gaps offline",
    )
    candidate_preflight_parser.add_argument("--inventory", required=True)
    candidate_preflight_parser.add_argument("--candidate", required=True)
    candidate_preflight_parser.add_argument("--output", required=True)
    candidate_qualification_parser = commands.add_parser(
        "prepare-candidate-qualification",
        help="prepare the missing-evidence checklist for one passing candidate",
    )
    candidate_qualification_parser.add_argument("--inventory", required=True)
    candidate_qualification_parser.add_argument("--candidate", required=True)
    candidate_qualification_parser.add_argument("--preflight", required=True)
    candidate_qualification_parser.add_argument("--output", required=True)
    candidate_assessment_parser = commands.add_parser(
        "assess-candidate-qualification",
        help="assess the reviewed evidence chain for one candidate plan",
    )
    candidate_assessment_parser.add_argument("--inventory", required=True)
    candidate_assessment_parser.add_argument("--candidate", required=True)
    candidate_assessment_parser.add_argument("--preflight", required=True)
    candidate_assessment_parser.add_argument("--plan", required=True)
    candidate_assessment_parser.add_argument("--evidence", required=True)
    candidate_assessment_parser.add_argument("--output", required=True)
    candidate_handoff_parser = commands.add_parser(
        "create-candidate-qualification-handoff",
        help="bind one complete candidate qualification chain into a receipt",
    )
    candidate_handoff_parser.add_argument("--inventory", required=True)
    candidate_handoff_parser.add_argument("--candidate", required=True)
    candidate_handoff_parser.add_argument("--preflight", required=True)
    candidate_handoff_parser.add_argument("--plan", required=True)
    candidate_handoff_parser.add_argument("--evidence", required=True)
    candidate_handoff_parser.add_argument("--assessment", required=True)
    candidate_handoff_parser.add_argument("--output", required=True)
    candidate_admission_parser = commands.add_parser(
        "admit-qualified-candidate",
        help="append one qualified candidate to a new offline inventory",
    )
    candidate_admission_parser.add_argument("--inventory", required=True)
    candidate_admission_parser.add_argument("--candidate", required=True)
    candidate_admission_parser.add_argument("--preflight", required=True)
    candidate_admission_parser.add_argument("--plan", required=True)
    candidate_admission_parser.add_argument("--evidence", required=True)
    candidate_admission_parser.add_argument("--assessment", required=True)
    candidate_admission_parser.add_argument("--handoff", required=True)
    candidate_admission_parser.add_argument("--inventory-id", required=True)
    candidate_admission_parser.add_argument("--inventory-output", required=True)
    candidate_admission_parser.add_argument("--receipt-output", required=True)
    candidate_split_parser = commands.add_parser(
        "plan-qualified-candidate-split",
        help="choose a deterministic count-spanning training and held-out split",
    )
    candidate_split_parser.add_argument("--inventory", required=True)
    candidate_split_parser.add_argument("--admission-receipt", required=True)
    candidate_split_parser.add_argument("--output", required=True)
    qualified_prepare_parser = commands.add_parser(
        "prepare-qualified-candidate-collection",
        help="prepare a collection package from an exact qualified inventory split",
    )
    qualified_prepare_parser.add_argument("--inventory", required=True)
    qualified_prepare_parser.add_argument("--admission-receipt", required=True)
    qualified_prepare_parser.add_argument("--training-split", required=True)
    qualified_prepare_parser.add_argument("--dataset-id", required=True)
    qualified_prepare_parser.add_argument("--producer-id", required=True)
    qualified_prepare_parser.add_argument(
        "--truth-method", choices=TRUTH_METHODS, required=True
    )
    qualified_prepare_parser.add_argument("--plan-output", required=True)
    qualified_prepare_parser.add_argument("--observations-output", required=True)
    qualified_prepare_parser.add_argument("--receipt-output", required=True)
    qualified_readiness_parser = commands.add_parser(
        "plan-qualified-collection-readiness",
        help="freeze the reviewed evidence required before qualified collection",
    )
    qualified_readiness_parser.add_argument("--inventory", required=True)
    qualified_readiness_parser.add_argument("--admission-receipt", required=True)
    qualified_readiness_parser.add_argument("--training-split", required=True)
    qualified_readiness_parser.add_argument("--collection-plan", required=True)
    qualified_readiness_parser.add_argument("--observations", required=True)
    qualified_readiness_parser.add_argument("--preparation-receipt", required=True)
    qualified_readiness_parser.add_argument("--output", required=True)
    qualified_readiness_assess_parser = commands.add_parser(
        "assess-qualified-collection-readiness",
        help="assess reviewed evidence for one qualified collection package",
    )
    qualified_readiness_assess_parser.add_argument("--inventory", required=True)
    qualified_readiness_assess_parser.add_argument(
        "--admission-receipt", required=True
    )
    qualified_readiness_assess_parser.add_argument("--training-split", required=True)
    qualified_readiness_assess_parser.add_argument("--collection-plan", required=True)
    qualified_readiness_assess_parser.add_argument("--observations", required=True)
    qualified_readiness_assess_parser.add_argument(
        "--preparation-receipt", required=True
    )
    qualified_readiness_assess_parser.add_argument("--readiness-plan", required=True)
    qualified_readiness_assess_parser.add_argument("--evidence", required=True)
    qualified_readiness_assess_parser.add_argument("--output", required=True)
    qualified_readiness_handoff_parser = commands.add_parser(
        "create-qualified-collection-readiness-handoff",
        help="create a handoff receipt for one complete readiness assessment",
    )
    qualified_readiness_handoff_parser.add_argument("--inventory", required=True)
    qualified_readiness_handoff_parser.add_argument(
        "--admission-receipt", required=True
    )
    qualified_readiness_handoff_parser.add_argument("--training-split", required=True)
    qualified_readiness_handoff_parser.add_argument("--collection-plan", required=True)
    qualified_readiness_handoff_parser.add_argument("--observations", required=True)
    qualified_readiness_handoff_parser.add_argument(
        "--preparation-receipt", required=True
    )
    qualified_readiness_handoff_parser.add_argument("--readiness-plan", required=True)
    qualified_readiness_handoff_parser.add_argument("--evidence", required=True)
    qualified_readiness_handoff_parser.add_argument("--assessment", required=True)
    qualified_readiness_handoff_parser.add_argument("--output", required=True)
    qualified_observation_parser = commands.add_parser(
        "ingest-qualified-stationary-observation",
        help="ingest one retained stationary observation into its planned slot",
    )
    qualified_observation_parser.add_argument("--inventory", required=True)
    qualified_observation_parser.add_argument("--admission-receipt", required=True)
    qualified_observation_parser.add_argument("--training-split", required=True)
    qualified_observation_parser.add_argument("--collection-plan", required=True)
    qualified_observation_parser.add_argument("--observations", required=True)
    qualified_observation_parser.add_argument("--preparation-receipt", required=True)
    qualified_observation_parser.add_argument("--readiness-plan", required=True)
    qualified_observation_parser.add_argument("--readiness-evidence", required=True)
    qualified_observation_parser.add_argument("--readiness-assessment", required=True)
    qualified_observation_parser.add_argument("--readiness-handoff", required=True)
    qualified_observation_parser.add_argument("--observation-evidence", required=True)
    qualified_observation_parser.add_argument("--observations-output", required=True)
    qualified_observation_parser.add_argument("--receipt-output", required=True)
    prepare_parser = commands.add_parser(
        "prepare", help="freeze a collection plan and empty observation template"
    )
    prepare_parser.add_argument("--dataset-id", required=True)
    prepare_parser.add_argument("--producer-id", required=True)
    prepare_parser.add_argument("--vid", required=True)
    prepare_parser.add_argument("--pid", required=True)
    prepare_parser.add_argument("--unit-serial", required=True)
    prepare_parser.add_argument("--firmware-sha256", required=True)
    prepare_parser.add_argument("--attachment-profile", choices=SUPPORTED_ATTACHMENTS, required=True)
    prepare_parser.add_argument("--truth-method", choices=TRUTH_METHODS, required=True)
    prepare_parser.add_argument("--training-pose", action="append", required=True)
    prepare_parser.add_argument("--held-out-pose", action="append", required=True)
    prepare_parser.add_argument("--plan-output", required=True)
    prepare_parser.add_argument("--observations-output", required=True)
    assessed_parser = commands.add_parser(
        "prepare-assessed",
        help="prepare from one exact passing readiness report",
    )
    assessed_parser.add_argument("--readiness", required=True)
    assessed_parser.add_argument("--dataset-id", required=True)
    assessed_parser.add_argument("--producer-id", required=True)
    assessed_parser.add_argument("--training-pose", action="append", required=True)
    assessed_parser.add_argument("--held-out-pose", action="append", required=True)
    assessed_parser.add_argument("--plan-output", required=True)
    assessed_parser.add_argument("--observations-output", required=True)
    assessed_parser.add_argument("--receipt-output", required=True)
    reviewed_prepare_parser = commands.add_parser(
        "prepare-reviewed",
        help="prepare from one exact reviewed-evidence assessment chain",
    )
    reviewed_prepare_parser.add_argument("--evidence", required=True)
    reviewed_prepare_parser.add_argument("--readiness", required=True)
    reviewed_prepare_parser.add_argument("--readiness-receipt", required=True)
    reviewed_prepare_parser.add_argument("--training-pose", action="append", required=True)
    reviewed_prepare_parser.add_argument("--held-out-pose", action="append", required=True)
    reviewed_prepare_parser.add_argument("--plan-output", required=True)
    reviewed_prepare_parser.add_argument("--observations-output", required=True)
    reviewed_prepare_parser.add_argument("--receipt-output", required=True)
    compile_parser = commands.add_parser(
        "compile", help="compile complete observations into the strict dataset"
    )
    compile_parser.add_argument("--plan", required=True)
    compile_parser.add_argument("--observations", required=True)
    compile_parser.add_argument("--output", required=True)
    reviewed_compile_parser = commands.add_parser(
        "compile-reviewed",
        help="compile observations from one exact reviewed preparation chain",
    )
    reviewed_compile_parser.add_argument("--evidence", required=True)
    reviewed_compile_parser.add_argument("--readiness", required=True)
    reviewed_compile_parser.add_argument("--readiness-receipt", required=True)
    reviewed_compile_parser.add_argument("--preparation-receipt", required=True)
    reviewed_compile_parser.add_argument("--plan", required=True)
    reviewed_compile_parser.add_argument("--observations", required=True)
    reviewed_compile_parser.add_argument("--output", required=True)
    reviewed_compile_parser.add_argument("--receipt-output", required=True)
    fit_parser = commands.add_parser("fit", help="fit and validate a retained dataset")
    fit_parser.add_argument("--dataset", required=True)
    fit_parser.add_argument("--calibration-id", required=True)
    fit_parser.add_argument("--output", required=True)
    fit_parser.add_argument("--minimum-training-samples", type=int, default=5)
    fit_parser.add_argument("--minimum-held-out-samples", type=int, default=3)
    fit_parser.add_argument("--minimum-training-count-span", type=int, default=128)
    fit_parser.add_argument("--accepted-max-abs-error-rad", type=float, default=0.035)
    fit_parser.add_argument("--shoulder-runtime-tolerance-counts", type=int, default=24)
    build_parser = commands.add_parser("build", help="verify review and emit calibration")
    build_parser.add_argument("--dataset", required=True)
    build_parser.add_argument("--fit-report", required=True)
    build_parser.add_argument("--review", required=True)
    build_parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    if args.command == "assess":
        result = assess_collection_readiness(
            controller_identity={
                "vid": args.vid,
                "pid": args.pid,
                "unit_serial": args.unit_serial,
            },
            installed_firmware_sha256=args.firmware_sha256,
            attachment_profile=args.attachment_profile,
            truth_method=args.truth_method,
            retained_pose_labels=args.retained_pose,
        )
        _write_new(args.output, result)
        return 0
    if args.command == "assess-reviewed":
        readiness, receipt = assess_reviewed_readiness_evidence(
            _read_json(args.evidence)
        )
        output_paths = (Path(args.readiness_output), Path(args.receipt_output))
        if len(set(output_paths)) != len(output_paths) or any(
            path.exists() for path in output_paths
        ):
            raise PositionVectorCampaignError(
                "refusing to replace or alias reviewed readiness output"
            )
        _write_new(args.readiness_output, readiness)
        _write_new(args.receipt_output, receipt)
        return 0
    if args.command == "audit-candidates":
        result = audit_candidate_count_coverage(_read_json(args.inventory))
        _write_new(args.output, result)
        return 0
    if args.command == "plan-candidate-augmentation":
        result = plan_candidate_count_augmentation(_read_json(args.inventory))
        _write_new(args.output, result)
        return 0
    if args.command == "preflight-candidate-augmentation":
        result = evaluate_candidate_count_augmentation(
            _read_json(args.inventory), _read_json(args.candidate)
        )
        _write_new(args.output, result)
        return 0
    if args.command == "prepare-candidate-qualification":
        result = create_candidate_qualification_plan(
            _read_json(args.inventory),
            _read_json(args.candidate),
            _read_json(args.preflight),
        )
        _write_new(args.output, result)
        return 0
    if args.command == "assess-candidate-qualification":
        result = assess_candidate_qualification_evidence(
            _read_json(args.inventory),
            _read_json(args.candidate),
            _read_json(args.preflight),
            _read_json(args.plan),
            _read_json(args.evidence),
        )
        _write_new(args.output, result)
        return 0
    if args.command == "create-candidate-qualification-handoff":
        result = create_candidate_qualification_handoff(
            _read_json(args.inventory),
            _read_json(args.candidate),
            _read_json(args.preflight),
            _read_json(args.plan),
            _read_json(args.evidence),
            _read_json(args.assessment),
        )
        _write_new(args.output, result)
        return 0
    if args.command == "admit-qualified-candidate":
        inventory, receipt = create_qualified_candidate_inventory_package(
            _read_json(args.inventory),
            _read_json(args.candidate),
            _read_json(args.preflight),
            _read_json(args.plan),
            _read_json(args.evidence),
            _read_json(args.assessment),
            _read_json(args.handoff),
            args.inventory_id,
        )
        output_paths = (Path(args.inventory_output), Path(args.receipt_output))
        if len(set(output_paths)) != len(output_paths) or any(
            path.exists() for path in output_paths
        ):
            raise PositionVectorCampaignError(
                "refusing to replace or alias candidate admission output"
            )
        _write_new(args.inventory_output, inventory)
        _write_new(args.receipt_output, receipt)
        return 0
    if args.command == "plan-qualified-candidate-split":
        result = plan_qualified_candidate_training_split(
            _read_json(args.inventory),
            _read_json(args.admission_receipt),
        )
        _write_new(args.output, result)
        return 0
    if args.command == "prepare-qualified-candidate-collection":
        plan, observations, receipt = create_qualified_candidate_collection_package(
            inventory_document=_read_json(args.inventory),
            admission_receipt_document=_read_json(args.admission_receipt),
            training_split_document=_read_json(args.training_split),
            dataset_id=args.dataset_id,
            producer_id=args.producer_id,
            truth_method=args.truth_method,
        )
        output_paths = (
            Path(args.plan_output),
            Path(args.observations_output),
            Path(args.receipt_output),
        )
        if len(set(output_paths)) != len(output_paths) or any(
            path.exists() for path in output_paths
        ):
            raise PositionVectorCampaignError(
                "refusing to replace or alias qualified collection output"
            )
        _write_new(args.plan_output, plan)
        _write_new(args.observations_output, observations)
        _write_new(args.receipt_output, receipt)
        return 0
    if args.command == "plan-qualified-collection-readiness":
        result = create_qualified_collection_readiness_plan(
            inventory_document=_read_json(args.inventory),
            admission_receipt_document=_read_json(args.admission_receipt),
            training_split_document=_read_json(args.training_split),
            collection_plan_document=_read_json(args.collection_plan),
            observations_document=_read_json(args.observations),
            preparation_receipt_document=_read_json(args.preparation_receipt),
        )
        _write_new(args.output, result)
        return 0
    if args.command == "assess-qualified-collection-readiness":
        result = assess_qualified_collection_readiness_evidence(
            inventory_document=_read_json(args.inventory),
            admission_receipt_document=_read_json(args.admission_receipt),
            training_split_document=_read_json(args.training_split),
            collection_plan_document=_read_json(args.collection_plan),
            observations_document=_read_json(args.observations),
            preparation_receipt_document=_read_json(args.preparation_receipt),
            readiness_plan_document=_read_json(args.readiness_plan),
            evidence_document=_read_json(args.evidence),
        )
        _write_new(args.output, result)
        return 0
    if args.command == "create-qualified-collection-readiness-handoff":
        result = create_qualified_collection_readiness_handoff(
            inventory_document=_read_json(args.inventory),
            admission_receipt_document=_read_json(args.admission_receipt),
            training_split_document=_read_json(args.training_split),
            collection_plan_document=_read_json(args.collection_plan),
            observations_document=_read_json(args.observations),
            preparation_receipt_document=_read_json(args.preparation_receipt),
            readiness_plan_document=_read_json(args.readiness_plan),
            evidence_document=_read_json(args.evidence),
            assessment_document=_read_json(args.assessment),
        )
        _write_new(args.output, result)
        return 0
    if args.command == "ingest-qualified-stationary-observation":
        observations, receipt = ingest_qualified_stationary_observation(
            inventory_document=_read_json(args.inventory),
            admission_receipt_document=_read_json(args.admission_receipt),
            training_split_document=_read_json(args.training_split),
            collection_plan_document=_read_json(args.collection_plan),
            observations_document=_read_json(args.observations),
            preparation_receipt_document=_read_json(args.preparation_receipt),
            readiness_plan_document=_read_json(args.readiness_plan),
            readiness_evidence_document=_read_json(args.readiness_evidence),
            readiness_assessment_document=_read_json(args.readiness_assessment),
            readiness_handoff_document=_read_json(args.readiness_handoff),
            observation_evidence_document=_read_json(args.observation_evidence),
        )
        output_paths = (
            Path(args.observations_output),
            Path(args.receipt_output),
        )
        if len(set(output_paths)) != len(output_paths) or any(
            path.exists() for path in output_paths
        ):
            raise PositionVectorCampaignError(
                "refusing to replace or alias qualified observation output"
            )
        _write_new(args.observations_output, observations)
        _write_new(args.receipt_output, receipt)
        return 0
    if args.command == "prepare":
        plan = create_collection_plan(
            dataset_id=args.dataset_id,
            producer_id=args.producer_id,
            controller_binding={
                "vid": args.vid,
                "pid": args.pid,
                "unit_serial": args.unit_serial,
                "firmware_sha256": args.firmware_sha256,
            },
            attachment_profile=args.attachment_profile,
            training_poses=args.training_pose,
            held_out_poses=args.held_out_pose,
            truth_method=args.truth_method,
        )
        plan_path = Path(args.plan_output)
        observations_path = Path(args.observations_output)
        if plan_path.exists() or observations_path.exists():
            raise PositionVectorCampaignError("refusing to replace existing preparation output")
        _write_new(args.plan_output, plan)
        _write_new(args.observations_output, collection_observations_template(plan))
        return 0
    if args.command == "prepare-assessed":
        plan, observations, receipt = create_assessed_collection_package(
            readiness_document=_read_json(args.readiness),
            dataset_id=args.dataset_id,
            producer_id=args.producer_id,
            training_poses=args.training_pose,
            held_out_poses=args.held_out_pose,
        )
        output_paths = (
            Path(args.plan_output),
            Path(args.observations_output),
            Path(args.receipt_output),
        )
        if len(set(output_paths)) != len(output_paths) or any(
            path.exists() for path in output_paths
        ):
            raise PositionVectorCampaignError(
                "refusing to replace or alias assessed preparation output"
            )
        _write_new(args.plan_output, plan)
        _write_new(args.observations_output, observations)
        _write_new(args.receipt_output, receipt)
        return 0
    if args.command == "prepare-reviewed":
        plan, observations, receipt = create_reviewed_collection_package(
            evidence_document=_read_json(args.evidence),
            readiness_document=_read_json(args.readiness),
            readiness_receipt_document=_read_json(args.readiness_receipt),
            training_poses=args.training_pose,
            held_out_poses=args.held_out_pose,
        )
        output_paths = (
            Path(args.plan_output),
            Path(args.observations_output),
            Path(args.receipt_output),
        )
        if len(set(output_paths)) != len(output_paths) or any(
            path.exists() for path in output_paths
        ):
            raise PositionVectorCampaignError(
                "refusing to replace or alias reviewed preparation output"
            )
        _write_new(args.plan_output, plan)
        _write_new(args.observations_output, observations)
        _write_new(args.receipt_output, receipt)
        return 0
    if args.command == "compile":
        result = compile_planned_dataset(
            _read_json(args.plan), _read_json(args.observations)
        )
    elif args.command == "compile-reviewed":
        dataset, receipt = create_reviewed_dataset_package(
            evidence_document=_read_json(args.evidence),
            readiness_document=_read_json(args.readiness),
            readiness_receipt_document=_read_json(args.readiness_receipt),
            preparation_receipt_document=_read_json(args.preparation_receipt),
            plan_document=_read_json(args.plan),
            observations_document=_read_json(args.observations),
        )
        output_paths = (Path(args.output), Path(args.receipt_output))
        if len(set(output_paths)) != len(output_paths) or any(
            path.exists() for path in output_paths
        ):
            raise PositionVectorCampaignError(
                "refusing to replace or alias reviewed compilation output"
            )
        _write_new(args.output, dataset)
        _write_new(args.receipt_output, receipt)
        return 0
    elif args.command == "fit":
        policy = CampaignPolicy(
            minimum_training_samples=args.minimum_training_samples,
            minimum_held_out_samples=args.minimum_held_out_samples,
            minimum_training_count_span=args.minimum_training_count_span,
            accepted_max_abs_error_rad=args.accepted_max_abs_error_rad,
            shoulder_runtime_tolerance_counts=args.shoulder_runtime_tolerance_counts,
        )
        result = fit_campaign_dataset(
            _read_json(args.dataset), calibration_id=args.calibration_id, policy=policy
        )
    else:
        result = build_calibration_artifact(
            _read_json(args.dataset),
            _read_json(args.fit_report),
            _read_json(args.review),
        )
    _write_new(args.output, result)
    return 0


__all__ = [
    "CANDIDATE_QUALIFICATION_ASSESSMENT_SCHEMA",
    "CANDIDATE_INVENTORY_ADMISSION_RECEIPT_SCHEMA",
    "CANDIDATE_QUALIFICATION_EVIDENCE_SCHEMA",
    "CANDIDATE_QUALIFICATION_HANDOFF_SCHEMA",
    "CANDIDATE_QUALIFICATION_PLAN_SCHEMA",
    "CANDIDATE_TRAINING_SPLIT_PLAN_SCHEMA",
    "DATASET_SCHEMA",
    "FIT_REPORT_SCHEMA",
    "OBSERVATIONS_SCHEMA",
    "PLAN_SCHEMA",
    "PREPARATION_RECEIPT_SCHEMA",
    "QUALIFIED_COLLECTION_PREPARATION_RECEIPT_SCHEMA",
    "QUALIFIED_COLLECTION_READINESS_ASSESSMENT_SCHEMA",
    "QUALIFIED_COLLECTION_READINESS_EVIDENCE_SCHEMA",
    "QUALIFIED_COLLECTION_READINESS_HANDOFF_SCHEMA",
    "QUALIFIED_COLLECTION_READINESS_PLAN_SCHEMA",
    "QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_SCHEMA",
    "QUALIFIED_STATIONARY_OBSERVATION_INGESTION_RECEIPT_SCHEMA",
    "READINESS_EVIDENCE_RECEIPT_SCHEMA",
    "READINESS_EVIDENCE_SCHEMA",
    "READINESS_SCHEMA",
    "REVIEWED_COMPILATION_RECEIPT_SCHEMA",
    "REVIEWED_PREPARATION_RECEIPT_SCHEMA",
    "REVIEW_SCHEMA",
    "SUPPORTED_ATTACHMENTS",
    "TRUTH_METHODS",
    "CampaignPolicy",
    "PositionVectorCampaignError",
    "assess_collection_readiness",
    "assess_candidate_qualification_evidence",
    "assess_qualified_collection_readiness_evidence",
    "assess_reviewed_readiness_evidence",
    "build_calibration_artifact",
    "canonical_bytes",
    "canonical_sha256",
    "collection_observations_template",
    "compile_planned_dataset",
    "create_assessed_collection_package",
    "create_candidate_qualification_plan",
    "create_candidate_qualification_handoff",
    "create_qualified_candidate_inventory_package",
    "create_qualified_candidate_collection_package",
    "create_qualified_collection_readiness_plan",
    "create_qualified_collection_readiness_handoff",
    "create_collection_plan",
    "create_reviewed_dataset_package",
    "create_reviewed_collection_package",
    "fit_campaign_dataset",
    "ingest_qualified_stationary_observation",
    "load_campaign_dataset",
    "load_collection_readiness",
    "load_collection_plan",
    "main",
    "plan_qualified_candidate_training_split",
]


if __name__ == "__main__":
    raise SystemExit(main())
