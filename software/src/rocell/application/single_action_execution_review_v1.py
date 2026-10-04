"""Single-use, zero-authority review admission for one exact v2 action.

This boundary joins model, trajectory, collision/contact, and installed-controller
lineage. It derives an offline exact T102 goal hash, but never encodes wire
bytes, opens hardware, or issues a motion permit.
Consumption only records that the exact review was used once by a future permit
issuer; the safety supervisor remains the sole source of physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from threading import Lock
from types import MappingProxyType
from typing import Any, Mapping

from rocell.models import ModelMotionBatchV2, ModelMotionProposalV2
from rocell.arm.all_joint_command import all_joint_command
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.safety.permit import goal_hash

from .installed_controller_qualification_v1 import (
    EvidenceOrigin as ControllerEvidenceOrigin,
    InstalledControllerQualificationEvidenceV1,
    InstalledControllerQualificationReportV1,
    ReviewDisposition as ControllerReviewDisposition,
)
from .trajectory_execution_envelope_v2 import TrajectoryExecutionEnvelopeV2


QUALIFICATION_SCHEMA = "rocell.installed_collision_policy_qualification.v1"
REVIEW_SCHEMA = "rocell.single_action_execution_review.v1"
CONSUMPTION_SCHEMA = "rocell.single_action_execution_review_consumption.v1"
MAX_REVIEW_TTL_NS = 30_000_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class SingleActionExecutionReviewError(ValueError):
    """Review evidence is malformed, crossed, stale, cancelled, or reused."""


@dataclass(frozen=True, slots=True)
class InstalledT102CommandProfileV1:
    """Physical review of the missing hand, firmware settings, and path."""

    trajectory_execution_envelope_v2_sha256: str
    controller_qualification_evidence_sha256: str
    observed_hand_feedback_sha256: str
    reviewed_path_evidence_sha256: str
    independent_approval_sha256: str
    hand_target_rad: float
    speed: int
    acceleration: int
    captured_monotonic_ns: int
    valid_until_monotonic_ns: int
    evidence_origin: PhysicalEvidenceOrigin
    review_disposition: PhysicalReviewDisposition

    def __post_init__(self) -> None:
        for field in (
            "trajectory_execution_envelope_v2_sha256",
            "controller_qualification_evidence_sha256",
            "observed_hand_feedback_sha256", "reviewed_path_evidence_sha256",
            "independent_approval_sha256",
        ):
            _digest(getattr(self, field), field)
        if isinstance(self.hand_target_rad, bool) or not isinstance(
            self.hand_target_rad, (int, float)
        ) or not math.isfinite(self.hand_target_rad):
            raise SingleActionExecutionReviewError("hand target must be finite")
        if type(self.speed) is not int or not 1 <= self.speed <= 65535:
            raise SingleActionExecutionReviewError("T102 speed is invalid")
        if type(self.acceleration) is not int or not 1 <= self.acceleration <= 255:
            raise SingleActionExecutionReviewError("T102 acceleration is invalid")
        captured = _positive_ns(
            self.captured_monotonic_ns, "captured_monotonic_ns")
        valid_until = _positive_ns(
            self.valid_until_monotonic_ns, "valid_until_monotonic_ns")
        if valid_until <= captured:
            raise SingleActionExecutionReviewError(
                "T102 profile expiry must follow capture")
        if not isinstance(self.evidence_origin, PhysicalEvidenceOrigin) or not isinstance(
            self.review_disposition, PhysicalReviewDisposition
        ):
            raise SingleActionExecutionReviewError("T102 profile provenance is invalid")

    @property
    def profile_sha256(self) -> str:
        return _sha256({
            "schema": "rocell.installed_t102_command_profile.v1",
            "trajectory_execution_envelope_v2_sha256":
                self.trajectory_execution_envelope_v2_sha256,
            "controller_qualification_evidence_sha256":
                self.controller_qualification_evidence_sha256,
            "observed_hand_feedback_sha256": self.observed_hand_feedback_sha256,
            "reviewed_path_evidence_sha256": self.reviewed_path_evidence_sha256,
            "independent_approval_sha256": self.independent_approval_sha256,
            "hand_target_rad": self.hand_target_rad,
            "speed": self.speed, "acceleration": self.acceleration,
            "captured_monotonic_ns": self.captured_monotonic_ns,
            "valid_until_monotonic_ns": self.valid_until_monotonic_ns,
            "evidence_origin": self.evidence_origin.value,
            "review_disposition": self.review_disposition.value,
        })


class PhysicalEvidenceOrigin(str, Enum):
    PHYSICAL_RETAINED_ORIGINALS = "PHYSICAL_RETAINED_ORIGINALS"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


class PhysicalReviewDisposition(str, Enum):
    INDEPENDENTLY_APPROVED = "INDEPENDENTLY_APPROVED"
    UNREVIEWED = "UNREVIEWED"
    REJECTED = "REJECTED"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SingleActionExecutionReviewError(
            "review value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise SingleActionExecutionReviewError(
            f"{label} must be a lowercase SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise SingleActionExecutionReviewError(
            f"{label} must be a bounded identifier")
    return value


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SingleActionExecutionReviewError(f"{label} must be positive nanoseconds")
    return value


def _verified_report_hash(
    report: Mapping[str, Any], field: str, *, label: str,
) -> str:
    claimed = _digest(report.get(field), field)
    unsigned = {key: value for key, value in report.items() if key != field}
    if _sha256(unsigned) != claimed:
        raise SingleActionExecutionReviewError(f"{label} content hash is invalid")
    return claimed


@dataclass(frozen=True, slots=True)
class InstalledCollisionPolicyQualificationV1:
    """Reviewed physical evidence for one installed profile/contact policy."""

    qualification_id: str
    installed_collision_profile_sha256: str
    phase_local_contact_allowance_sha256: str | None
    physical_measurement_evidence_sha256: str
    independent_review_decision_sha256: str
    captured_monotonic_ns: int
    valid_until_monotonic_ns: int
    evidence_origin: PhysicalEvidenceOrigin
    review_disposition: PhysicalReviewDisposition
    schema: str = QUALIFICATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != QUALIFICATION_SCHEMA:
            raise SingleActionExecutionReviewError(
                "unsupported collision-policy qualification schema")
        _identifier(self.qualification_id, "qualification_id")
        for field in (
            "installed_collision_profile_sha256",
            "physical_measurement_evidence_sha256",
            "independent_review_decision_sha256",
        ):
            _digest(getattr(self, field), field)
        if self.phase_local_contact_allowance_sha256 is not None:
            _digest(
                self.phase_local_contact_allowance_sha256,
                "phase_local_contact_allowance_sha256",
            )
        captured = _positive_ns(self.captured_monotonic_ns, "captured_monotonic_ns")
        valid_until = _positive_ns(
            self.valid_until_monotonic_ns, "valid_until_monotonic_ns")
        if valid_until <= captured:
            raise SingleActionExecutionReviewError(
                "collision-policy qualification expiry must follow capture")
        if not isinstance(self.evidence_origin, PhysicalEvidenceOrigin):
            raise SingleActionExecutionReviewError("evidence_origin must be typed")
        if not isinstance(self.review_disposition, PhysicalReviewDisposition):
            raise SingleActionExecutionReviewError(
                "review_disposition must be typed")

    @property
    def execution_review_ready(self) -> bool:
        return (
            self.evidence_origin is PhysicalEvidenceOrigin.PHYSICAL_RETAINED_ORIGINALS
            and self.review_disposition
            is PhysicalReviewDisposition.INDEPENDENTLY_APPROVED
        )

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "qualification_id": self.qualification_id,
            "installed_collision_profile_sha256": (
                self.installed_collision_profile_sha256),
            "phase_local_contact_allowance_sha256": (
                self.phase_local_contact_allowance_sha256),
            "physical_measurement_evidence_sha256": (
                self.physical_measurement_evidence_sha256),
            "independent_review_decision_sha256": (
                self.independent_review_decision_sha256),
            "captured_monotonic_ns": self.captured_monotonic_ns,
            "valid_until_monotonic_ns": self.valid_until_monotonic_ns,
            "evidence_origin": self.evidence_origin.value,
            "review_disposition": self.review_disposition.value,
            "execution_review_ready": self.execution_review_ready,
            "hardware_access": False,
            "physical_authority": False,
            "contact_authority": False,
        }

    @property
    def qualification_sha256(self) -> str:
        return _sha256(self.unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.unsigned_dict(),
            "qualification_sha256": self.qualification_sha256,
        }


@dataclass(frozen=True, slots=True)
class SingleActionExecutionReviewV1:
    review_id: str
    batch_sha256: str
    action_index: int
    proposal_v2_sha256: str
    device: str
    interaction: str
    trajectory_execution_envelope_v2_sha256: str
    contact_envelope_gate_sha256: str
    installed_collision_policy_qualification_sha256: str
    installed_controller_qualification_evidence_sha256: str
    installed_controller_qualification_report_sha256: str
    t102_command_profile_sha256: str
    reviewed_t102_goal: Mapping[str, Any]
    reviewed_t102_goal_sha256: str
    configuration_epoch_sha256: str
    controller_session_id: str
    issued_monotonic_ns: int
    deadline_monotonic_ns: int
    schema: str = REVIEW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REVIEW_SCHEMA:
            raise SingleActionExecutionReviewError("unsupported execution review schema")
        _identifier(self.review_id, "review_id")
        _identifier(self.controller_session_id, "controller_session_id")
        for field in (
            "batch_sha256", "proposal_v2_sha256",
            "trajectory_execution_envelope_v2_sha256",
            "contact_envelope_gate_sha256",
            "installed_collision_policy_qualification_sha256",
            "installed_controller_qualification_evidence_sha256",
            "installed_controller_qualification_report_sha256",
            "t102_command_profile_sha256", "reviewed_t102_goal_sha256",
            "configuration_epoch_sha256",
        ):
            _digest(getattr(self, field), field)
        if not isinstance(self.reviewed_t102_goal, Mapping):
            raise SingleActionExecutionReviewError("reviewed T102 goal is required")
        goal = dict(self.reviewed_t102_goal)
        if (
            tuple(goal) != ("T", "base", "shoulder", "elbow", "wrist",
                            "roll", "hand", "spd", "acc")
            or goal.get("T") != 102
            or goal_hash(goal) != self.reviewed_t102_goal_sha256
        ):
            raise SingleActionExecutionReviewError("reviewed T102 goal is invalid")
        object.__setattr__(self, "reviewed_t102_goal", MappingProxyType(goal))
        if isinstance(self.action_index, bool) or not isinstance(
            self.action_index, int
        ) or self.action_index < 0:
            raise SingleActionExecutionReviewError(
                "action_index must be a nonnegative integer")
        if self.device not in ("keyboard", "phone"):
            raise SingleActionExecutionReviewError("device is invalid")
        if self.interaction not in ("HOVER", "CONTACT"):
            raise SingleActionExecutionReviewError("interaction is invalid")
        issued = _positive_ns(self.issued_monotonic_ns, "issued_monotonic_ns")
        deadline = _positive_ns(self.deadline_monotonic_ns, "deadline_monotonic_ns")
        if deadline <= issued or deadline - issued > MAX_REVIEW_TTL_NS:
            raise SingleActionExecutionReviewError(
                "execution review lifetime is invalid or too long")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": "REVIEWED_FOR_SINGLE_USE_DOWNSTREAM_PERMIT",
            "review_id": self.review_id,
            "batch_sha256": self.batch_sha256,
            "action_index": self.action_index,
            "proposal_v2_sha256": self.proposal_v2_sha256,
            "device": self.device,
            "interaction": self.interaction,
            "trajectory_execution_envelope_v2_sha256": (
                self.trajectory_execution_envelope_v2_sha256),
            "contact_envelope_gate_sha256": self.contact_envelope_gate_sha256,
            "installed_collision_policy_qualification_sha256": (
                self.installed_collision_policy_qualification_sha256),
            "installed_controller_qualification_report_sha256": (
                self.installed_controller_qualification_report_sha256),
            "t102_command_profile_sha256": self.t102_command_profile_sha256,
            "reviewed_t102_goal": dict(self.reviewed_t102_goal),
            "reviewed_t102_goal_sha256": self.reviewed_t102_goal_sha256,
            "installed_controller_qualification_evidence_sha256": (
                self.installed_controller_qualification_evidence_sha256),
            "configuration_epoch_sha256": self.configuration_epoch_sha256,
            "controller_session_id": self.controller_session_id,
            "issued_monotonic_ns": self.issued_monotonic_ns,
            "deadline_monotonic_ns": self.deadline_monotonic_ns,
            "single_use_required": True,
            "permit_issued": False,
            "automatic_retry_allowed": False,
            "controller_commands": [],
            "wire_commands": [],
            "hardware_access": False,
            "physical_authority": False,
            "contact_authority": False,
        }

    @property
    def review_sha256(self) -> str:
        return _sha256(self.unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "review_sha256": self.review_sha256}


def build_single_action_execution_review_v1(
    batch: ModelMotionBatchV2,
    proposal: ModelMotionProposalV2,
    envelope: TrajectoryExecutionEnvelopeV2,
    contact_gate_report: Mapping[str, Any],
    collision_qualification: InstalledCollisionPolicyQualificationV1,
    controller_evidence: InstalledControllerQualificationEvidenceV1,
    controller_qualification: InstalledControllerQualificationReportV1,
    t102_profile: InstalledT102CommandProfileV1,
    *,
    review_id: str,
    issued_monotonic_ns: int,
    deadline_monotonic_ns: int,
) -> SingleActionExecutionReviewV1:
    """Bind all exact lineages for later one-time permit consideration."""

    if not isinstance(batch, ModelMotionBatchV2):
        raise TypeError("batch must be a ModelMotionBatchV2")
    if not isinstance(proposal, ModelMotionProposalV2):
        raise TypeError("proposal must be a ModelMotionProposalV2")
    if not isinstance(envelope, TrajectoryExecutionEnvelopeV2):
        raise TypeError("envelope must be a TrajectoryExecutionEnvelopeV2")
    if not isinstance(contact_gate_report, Mapping):
        raise TypeError("contact_gate_report must be a mapping")
    if not isinstance(
        collision_qualification, InstalledCollisionPolicyQualificationV1
    ):
        raise TypeError("collision_qualification has the wrong type")
    if not isinstance(
        controller_evidence, InstalledControllerQualificationEvidenceV1
    ):
        raise TypeError("controller_evidence has the wrong type")
    if not isinstance(
        controller_qualification, InstalledControllerQualificationReportV1
    ):
        raise TypeError("controller_qualification has the wrong type")
    if not isinstance(t102_profile, InstalledT102CommandProfileV1):
        raise TypeError("t102_profile has the wrong type")
    now = _positive_ns(issued_monotonic_ns, "issued_monotonic_ns")
    contact_hash = _verified_report_hash(
        contact_gate_report, "contact_envelope_gate_sha256",
        label="contact envelope gate",
    )
    if proposal.action_index >= len(batch.proposals) or (
        batch.proposals[proposal.action_index] != proposal
    ):
        raise SingleActionExecutionReviewError(
            "proposal is not the indexed batch action")
    if (
        envelope.batch_sha256 != batch.batch_sha256
        or envelope.action_index != proposal.action_index
        or envelope.proposal_v2_sha256 != proposal.proposal_sha256
        or contact_gate_report.get("proposal_v2_sha256")
        != proposal.proposal_sha256
        or contact_gate_report.get("trajectory_execution_envelope_v2_sha256")
        != envelope.envelope_v2_sha256
    ):
        raise SingleActionExecutionReviewError(
            "model, trajectory, and collision lineages are crossed")
    for report in (contact_gate_report, controller_qualification.to_dict()):
        if (
            report.get("hardware_access") is not False
            or report.get("physical_authority") is not False
        ):
            raise SingleActionExecutionReviewError(
                "upstream qualification violates zero authority")
    if (
        contact_gate_report.get("status")
        != "COLLISION_POLICY_BOUND_NO_WRITE_ENVELOPE"
        or contact_gate_report.get("controller_commands") != []
        or contact_gate_report.get("wire_commands") != []
        or contact_gate_report.get("contact_authority") is not False
    ):
        raise SingleActionExecutionReviewError(
            "contact envelope gate is not zero-authority ready")
    if not collision_qualification.execution_review_ready:
        raise SingleActionExecutionReviewError(
            "installed collision-policy qualification is not independently approved")
    if not (
        collision_qualification.captured_monotonic_ns <= now
        <= collision_qualification.valid_until_monotonic_ns
    ):
        raise SingleActionExecutionReviewError(
            "installed collision-policy qualification is unavailable or stale")
    if (
        collision_qualification.installed_collision_profile_sha256
        != contact_gate_report.get("installed_collision_profile_sha256")
        or collision_qualification.phase_local_contact_allowance_sha256
        != contact_gate_report.get("phase_local_contact_allowance_sha256")
    ):
        raise SingleActionExecutionReviewError(
            "collision qualification differs from contact envelope gate")
    controller_report = controller_qualification.to_dict()
    if (
        controller_report["status"] != "READY_FOR_ZERO_WRITE_PROFILE_BINDING"
        or controller_report["profile_binding_ready"] is not True
        or controller_report["execution_authorized"] is not False
    ):
        raise SingleActionExecutionReviewError(
            "installed controller qualification is not ready")
    if (
        controller_qualification.qualification_evidence_sha256
        != controller_evidence.evidence_sha256
        or controller_evidence.evidence_origin
        is not ControllerEvidenceOrigin.PHYSICAL_RETAINED_ORIGINALS
        or controller_evidence.review_disposition
        is not ControllerReviewDisposition.INDEPENDENTLY_APPROVED
        or not (
            controller_evidence.captured_monotonic_ns <= now
            <= controller_evidence.valid_until_monotonic_ns
        )
        or controller_evidence.configuration_epoch_sha256
        != envelope.measured_envelope.configuration_epoch_sha256
        or controller_evidence.controller_session_id
        != envelope.measured_envelope.controller_session_id
    ):
        raise SingleActionExecutionReviewError(
            "installed controller evidence differs from the execution envelope")
    latest_deadline = min(
        envelope.measured_envelope.deadline_monotonic_ns,
        collision_qualification.valid_until_monotonic_ns,
        controller_evidence.valid_until_monotonic_ns,
        t102_profile.valid_until_monotonic_ns,
    )
    if deadline_monotonic_ns > latest_deadline:
        raise SingleActionExecutionReviewError(
            "execution review outlives a reviewed envelope or qualification")
    if (
        t102_profile.trajectory_execution_envelope_v2_sha256
        != envelope.envelope_v2_sha256
        or t102_profile.controller_qualification_evidence_sha256
        != controller_evidence.evidence_sha256
        or t102_profile.evidence_origin
        is not PhysicalEvidenceOrigin.PHYSICAL_RETAINED_ORIGINALS
        or t102_profile.review_disposition
        is not PhysicalReviewDisposition.INDEPENDENTLY_APPROVED
        or not t102_profile.captured_monotonic_ns <= now
        <= t102_profile.valid_until_monotonic_ns
        or len(envelope.measured_envelope.waypoints) != 2
    ):
        raise SingleActionExecutionReviewError(
            "an approved single-T102 command profile is required")
    endpoint = envelope.measured_envelope.waypoints[-1].joint_positions_rad
    reviewed_goal = all_joint_command(
        [*(endpoint[name] for name in ARM_JOINT_NAMES),
         t102_profile.hand_target_rad],
        speed=t102_profile.speed, acceleration=t102_profile.acceleration,
    )
    return SingleActionExecutionReviewV1(
        review_id=review_id,
        batch_sha256=batch.batch_sha256,
        action_index=proposal.action_index,
        proposal_v2_sha256=proposal.proposal_sha256,
        device=proposal.device.value,
        interaction=proposal.interaction.value,
        trajectory_execution_envelope_v2_sha256=envelope.envelope_v2_sha256,
        contact_envelope_gate_sha256=contact_hash,
        installed_collision_policy_qualification_sha256=(
            collision_qualification.qualification_sha256),
        installed_controller_qualification_evidence_sha256=(
            controller_evidence.evidence_sha256),
        installed_controller_qualification_report_sha256=(
            controller_qualification.report_sha256),
        t102_command_profile_sha256=t102_profile.profile_sha256,
        reviewed_t102_goal=reviewed_goal,
        reviewed_t102_goal_sha256=goal_hash(reviewed_goal),
        configuration_epoch_sha256=(
            envelope.measured_envelope.configuration_epoch_sha256),
        controller_session_id=envelope.measured_envelope.controller_session_id,
        issued_monotonic_ns=now,
        deadline_monotonic_ns=deadline_monotonic_ns,
    )


class SingleUseExecutionReviewGateV1:
    """Atomically consume or cancel one review, without issuing authority."""

    def __init__(self, review: SingleActionExecutionReviewV1) -> None:
        if not isinstance(review, SingleActionExecutionReviewV1):
            raise TypeError("review must be a SingleActionExecutionReviewV1")
        self._review = review
        self._state = "PENDING"
        self._lock = Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def cancel(self) -> None:
        with self._lock:
            if self._state != "PENDING":
                raise SingleActionExecutionReviewError(
                    "only a pending execution review can be cancelled")
            self._state = "CANCELLED"

    def consume(
        self, review_sha256: str, *, consumed_monotonic_ns: int,
    ) -> dict[str, Any]:
        claimed = _digest(review_sha256, "review_sha256")
        now = _positive_ns(consumed_monotonic_ns, "consumed_monotonic_ns")
        with self._lock:
            if self._state == "CANCELLED":
                raise SingleActionExecutionReviewError(
                    "execution review was cancelled")
            if self._state == "CONSUMED":
                raise SingleActionExecutionReviewError(
                    "execution review was already consumed")
            if claimed != self._review.review_sha256:
                raise SingleActionExecutionReviewError(
                    "execution review digest does not match")
            if not (
                self._review.issued_monotonic_ns <= now
                <= self._review.deadline_monotonic_ns
            ):
                raise SingleActionExecutionReviewError(
                    "execution review is unavailable or expired")
            self._state = "CONSUMED"
            report: dict[str, Any] = {
                "schema": CONSUMPTION_SCHEMA,
                "status": "REVIEW_ADMISSION_CONSUMED",
                "review_sha256": claimed,
                "batch_sha256": self._review.batch_sha256,
                "action_index": self._review.action_index,
                "proposal_v2_sha256": self._review.proposal_v2_sha256,
                "consumed_monotonic_ns": now,
                "permit_issued": False,
                "automatic_retry_allowed": False,
                "controller_commands": [],
                "wire_commands": [],
                "hardware_access": False,
                "physical_authority": False,
                "contact_authority": False,
            }
            return {**report, "consumption_sha256": _sha256(report)}


__all__ = [
    "CONSUMPTION_SCHEMA", "MAX_REVIEW_TTL_NS", "QUALIFICATION_SCHEMA",
    "REVIEW_SCHEMA", "InstalledCollisionPolicyQualificationV1",
    "InstalledT102CommandProfileV1",
    "PhysicalEvidenceOrigin", "PhysicalReviewDisposition",
    "SingleActionExecutionReviewError", "SingleActionExecutionReviewV1",
    "SingleUseExecutionReviewGateV1", "build_single_action_execution_review_v1",
]
