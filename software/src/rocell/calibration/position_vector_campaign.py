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

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_HEX4 = re.compile(r"^[0-9a-f]{4}$")
_CONTROLLER_FIELDS = frozenset({"vid", "pid", "unit_serial", "firmware_sha256"})
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
    "DATASET_SCHEMA",
    "FIT_REPORT_SCHEMA",
    "OBSERVATIONS_SCHEMA",
    "PLAN_SCHEMA",
    "PREPARATION_RECEIPT_SCHEMA",
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
    "assess_reviewed_readiness_evidence",
    "build_calibration_artifact",
    "canonical_bytes",
    "canonical_sha256",
    "collection_observations_template",
    "compile_planned_dataset",
    "create_assessed_collection_package",
    "create_collection_plan",
    "create_reviewed_dataset_package",
    "create_reviewed_collection_package",
    "fit_campaign_dataset",
    "load_campaign_dataset",
    "load_collection_readiness",
    "load_collection_plan",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
