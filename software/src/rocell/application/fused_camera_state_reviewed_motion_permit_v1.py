"""Issue one exact supervisor permit from one fused camera-state review.

This orchestration boundary owns the transition from a fused, zero-authority
execution review to the existing safety supervisor.  It derives the capability
from the review, uses one monotonic clock for consumption and authorization,
and prevents a permit from outliving the review that justified it.  It performs
no transport access and writes no controller command.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from rocell.arm.protocol import decode_line
from rocell.calibration.artifacts import CalibrationResolution
from rocell.rc03.build_snapshot import Capability
from rocell.safety.interlocks import InterlockSnapshot
from rocell.safety.permit import MotionPermit, goal_hash
from rocell.safety.preflight import RuntimeStatus
from rocell.safety.supervisor import SafetySupervisor

from .native_t102_handoff_journal_v1 import (
    DurableNativeT102HandoffV1,
    NativeT102HandoffPhase,
    NativeT102HandoffSnapshotV1,
)
from .production_controller_runtime_contract_v1 import (
    ProductionControllerRuntimeContractV1,
    RuntimeCommandFrameV1,
)
from .reviewed_motion_permit_bridge_v1 import (
    ReviewedActionLifecycleV1,
    ReviewedMotionPermitAdmissionV1,
    issue_reviewed_motion_permit_v1,
)
from .reviewed_motion_sole_writer_v1 import IncapableReviewedMotionIoV1
from .reviewed_t102_runtime_bridge_v1 import (
    JointSettlementPolicyV1,
    execute_reviewed_t102_runtime_rehearsal_v1,
)
from .single_action_execution_review_v1 import (
    SingleActionExecutionReviewV1,
    SingleUseExecutionReviewGateV1,
)


class FusedCameraStateReviewedMotionPermitError(ValueError):
    """A fused review cannot safely enter the supervisor permit boundary."""


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FusedCameraStateReviewedMotionPermitError(
            f"{label} must be positive nanoseconds"
        )
    return value


@dataclass(frozen=True, slots=True)
class FusedCameraStateReviewedMotionPermitResultV1:
    """Typed in-memory result; the permit remains opaque and single use."""

    permit: MotionPermit
    admission: ReviewedMotionPermitAdmissionV1
    lifecycle: ReviewedActionLifecycleV1
    consumption_receipt: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.permit, MotionPermit):
            raise TypeError("permit must be a MotionPermit")
        if not isinstance(self.admission, ReviewedMotionPermitAdmissionV1):
            raise TypeError("admission must be a ReviewedMotionPermitAdmissionV1")
        if not isinstance(self.lifecycle, ReviewedActionLifecycleV1):
            raise TypeError("lifecycle must be a ReviewedActionLifecycleV1")
        if not isinstance(self.consumption_receipt, Mapping):
            raise TypeError("consumption_receipt must be a mapping")
        receipt = dict(self.consumption_receipt)
        if (
            self.permit.plan_hash != self.admission.review_sha256
            or receipt.get("review_sha256") != self.admission.review_sha256
            or receipt.get("consumption_sha256")
            != self.admission.consumption_sha256
            or self.lifecycle.snapshot().get("permit_binding_sha256")
            != self.admission.permit_binding_sha256
        ):
            raise FusedCameraStateReviewedMotionPermitError(
                "orchestration result lineages differ"
            )
        object.__setattr__(
            self, "consumption_receipt", MappingProxyType(receipt)
        )


class FusedCameraStateReviewedMotionPermitSessionV1:
    """Own exactly one fused review consumption and permit attempt."""

    def __init__(self, review: SingleActionExecutionReviewV1) -> None:
        if not isinstance(review, SingleActionExecutionReviewV1):
            raise TypeError("review must be a SingleActionExecutionReviewV1")
        if review.fused_camera_state_action_review_admission_sha256 is None:
            raise FusedCameraStateReviewedMotionPermitError(
                "fused camera-state action review admission is required"
            )
        if review.device != "keyboard":
            raise FusedCameraStateReviewedMotionPermitError(
                "fused camera-state review must target the keyboard"
            )
        document = review.to_dict()
        if (
            document.get("permit_issued") is not False
            or document.get("hardware_access") is not False
            or document.get("physical_authority") is not False
            or document.get("contact_authority") is not False
        ):
            raise FusedCameraStateReviewedMotionPermitError(
                "fused review must enter with zero authority"
            )
        self._review = review
        self._gate = SingleUseExecutionReviewGateV1(review)

    @property
    def state(self) -> str:
        return self._gate.state

    def issue(
        self,
        supervisor: SafetySupervisor,
        *,
        calibrations: CalibrationResolution,
        interlocks: InterlockSnapshot,
        runtime: RuntimeStatus,
        now_monotonic_ns: int,
        permit_ttl_ns: int,
    ) -> FusedCameraStateReviewedMotionPermitResultV1:
        """Consume the fused review and make its sole supervisor permit attempt."""

        now = _positive_ns(now_monotonic_ns, "now_monotonic_ns")
        ttl = _positive_ns(permit_ttl_ns, "permit_ttl_ns")
        if not self._review.issued_monotonic_ns <= now < (
            self._review.deadline_monotonic_ns
        ):
            raise FusedCameraStateReviewedMotionPermitError(
                "fused execution review is unavailable or expired"
            )
        if now + ttl > self._review.deadline_monotonic_ns:
            raise FusedCameraStateReviewedMotionPermitError(
                "motion permit would outlive the fused execution review"
            )
        capability = (
            Capability.EMPTY_CELL_MOTION
            if self._review.interaction == "HOVER"
            else Capability.KEYBOARD_CONTACT
        )
        receipt = self._gate.consume(
            self._review.review_sha256, consumed_monotonic_ns=now
        )
        permit, admission = issue_reviewed_motion_permit_v1(
            supervisor,
            self._review,
            receipt,
            capability,
            calibrations=calibrations,
            interlocks=interlocks,
            runtime=runtime,
            ttl_s=ttl / 1_000_000_000,
            now_monotonic=now / 1_000_000_000,
        )
        if (
            admission.fused_camera_state_action_review_admission_sha256
            != self._review.fused_camera_state_action_review_admission_sha256
        ):
            raise FusedCameraStateReviewedMotionPermitError(
                "fused action-review lineage was not preserved"
            )
        lifecycle = ReviewedActionLifecycleV1(admission)
        return FusedCameraStateReviewedMotionPermitResultV1(
            permit, admission, lifecycle, receipt
        )


def prepare_fused_camera_state_native_t102_handoff_v1(
    result: FusedCameraStateReviewedMotionPermitResultV1,
    frame: RuntimeCommandFrameV1,
    handoff_root: Path,
    *,
    adapter_candidate_sha256: str,
    created_monotonic_ns: int,
) -> DurableNativeT102HandoffV1:
    """Persist one fused permit as a cancellation-safe native handoff.

    This stops at the prepared phase.  It neither consumes the motion permit nor
    claims a writer, opens a transport, captures feedback, or creates physical
    authority.
    """

    if not isinstance(result, FusedCameraStateReviewedMotionPermitResultV1):
        raise TypeError(
            "result must be a FusedCameraStateReviewedMotionPermitResultV1"
        )
    if not isinstance(frame, RuntimeCommandFrameV1):
        raise TypeError("frame must be a RuntimeCommandFrameV1")
    created = _positive_ns(created_monotonic_ns, "created_monotonic_ns")
    lifecycle = result.lifecycle.snapshot()
    fused_digest = (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    receipt = dict(result.consumption_receipt)
    if (
        lifecycle.get("phase") != "ACCEPTED"
        or fused_digest is None
        or receipt.get("consumption_sha256")
        != result.admission.consumption_sha256
        or result.permit.remaining_uses != 1
    ):
        raise FusedCameraStateReviewedMotionPermitError(
            "fused permit is not available for native handoff preparation"
        )
    try:
        message = decode_line(frame.wire_bytes)
    except Exception as exc:
        raise FusedCameraStateReviewedMotionPermitError(
            "native handoff frame is not a canonical command"
        ) from exc
    permit_expiry_ns = round(
        result.admission.permit_expires_at_monotonic * 1_000_000_000
    )
    if (
        goal_hash(message) not in result.admission.ordered_goal_sha256
        or frame.expires_monotonic_ns > permit_expiry_ns
        or created >= permit_expiry_ns
    ):
        raise FusedCameraStateReviewedMotionPermitError(
            "native handoff frame differs from or outlives the fused permit"
        )
    journal = DurableNativeT102HandoffV1.prepare(
        handoff_root,
        frame,
        result.admission,
        adapter_candidate_sha256=adapter_candidate_sha256,
        created_monotonic_ns=created,
    )
    snapshot = journal.snapshot()
    if (
        snapshot.phase is not NativeT102HandoffPhase.PREPARED
        or snapshot.permit_binding_sha256
        != result.admission.permit_binding_sha256
        or snapshot.fused_camera_state_action_review_admission_sha256
        != fused_digest
        or snapshot.review_consumption_sha256
        != result.admission.consumption_sha256
    ):
        raise FusedCameraStateReviewedMotionPermitError(
            "prepared native handoff did not preserve fused lineage"
        )
    return journal


def claim_fused_camera_state_native_t102_writer_v1(
    result: FusedCameraStateReviewedMotionPermitResultV1,
    frame: RuntimeCommandFrameV1,
    handoff: DurableNativeT102HandoffV1,
    *,
    adapter_candidate_sha256: str,
    claimed_monotonic_ns: int,
) -> NativeT102HandoffSnapshotV1:
    """Commit the sole-writer ambiguity boundary for one fused handoff.

    The durable claim forbids automatic retry after recovery, but it still
    grants no transport-open or physical authority and does not consume the
    motion permit.  Callers must therefore make this transition only when the
    external-authority workflow is ready to continue from the exact claim.
    """

    if not isinstance(result, FusedCameraStateReviewedMotionPermitResultV1):
        raise TypeError(
            "result must be a FusedCameraStateReviewedMotionPermitResultV1"
        )
    if not isinstance(frame, RuntimeCommandFrameV1):
        raise TypeError("frame must be a RuntimeCommandFrameV1")
    if not isinstance(handoff, DurableNativeT102HandoffV1):
        raise TypeError("handoff must be a DurableNativeT102HandoffV1")
    claimed = _positive_ns(claimed_monotonic_ns, "claimed_monotonic_ns")
    before = handoff.snapshot()
    fused_digest = (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    permit_expiry_ns = round(
        result.admission.permit_expires_at_monotonic * 1_000_000_000
    )
    if (
        result.lifecycle.snapshot().get("phase") != "ACCEPTED"
        or result.permit.remaining_uses != 1
        or fused_digest is None
        or before.phase is not NativeT102HandoffPhase.PREPARED
        or before.permit_binding_sha256
        != result.admission.permit_binding_sha256
        or before.fused_camera_state_action_review_admission_sha256
        != fused_digest
        or before.review_consumption_sha256
        != result.admission.consumption_sha256
    ):
        raise FusedCameraStateReviewedMotionPermitError(
            "fused native handoff is not available for writer claim"
        )
    if not (
        frame.issued_monotonic_ns <= claimed < frame.expires_monotonic_ns
        and claimed < permit_expiry_ns
    ):
        raise FusedCameraStateReviewedMotionPermitError(
            "fused native writer claim is outside the authorized lifetime"
        )

    snapshot = handoff.claim_writer(
        frame,
        result.admission,
        adapter_candidate_sha256=adapter_candidate_sha256,
        claimed_monotonic_ns=claimed,
    )
    document = snapshot.to_dict()
    if (
        snapshot.phase is not NativeT102HandoffPhase.WRITER_CLAIMED
        or snapshot.permit_binding_sha256
        != result.admission.permit_binding_sha256
        or snapshot.fused_camera_state_action_review_admission_sha256
        != fused_digest
        or snapshot.review_consumption_sha256
        != result.admission.consumption_sha256
        or document.get("transport_open_count") != 0
        or document.get("physical_command_writes") != 0
        or result.permit.remaining_uses != 1
        or result.lifecycle.snapshot().get("phase") != "ACCEPTED"
    ):
        raise FusedCameraStateReviewedMotionPermitError(
            "claimed native handoff did not preserve fused lineage"
        )
    return snapshot


def execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1(
    result: FusedCameraStateReviewedMotionPermitResultV1,
    frame: RuntimeCommandFrameV1,
    runtime: ProductionControllerRuntimeContractV1,
    io: IncapableReviewedMotionIoV1,
    acknowledgment_bytes: bytes,
    feedback_samples: Iterable[Mapping[str, Any]] = (),
    *,
    writer_instance_id: str,
    dispatch_monotonic_ns: int,
    assessment_monotonic_ns: int,
    settlement_policy: JointSettlementPolicyV1 = JointSettlementPolicyV1(),
) -> dict[str, Any]:
    """Rehearse one fused permit through the hardware-incapable T=102 boundary."""

    if not isinstance(result, FusedCameraStateReviewedMotionPermitResultV1):
        raise TypeError(
            "result must be a FusedCameraStateReviewedMotionPermitResultV1"
        )
    fused_digest = (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    if fused_digest is None:
        raise FusedCameraStateReviewedMotionPermitError(
            "fused camera-state action review lineage is required"
        )
    dispatch_ns = _positive_ns(
        dispatch_monotonic_ns, "dispatch_monotonic_ns"
    )
    assessment_ns = _positive_ns(
        assessment_monotonic_ns, "assessment_monotonic_ns"
    )
    if result.lifecycle.snapshot().get("phase") != "ACCEPTED":
        raise FusedCameraStateReviewedMotionPermitError(
            "fused reviewed motion lifecycle is not accepted"
        )

    report = execute_reviewed_t102_runtime_rehearsal_v1(
        frame,
        result.permit,
        result.admission,
        result.lifecycle,
        runtime,
        io,
        acknowledgment_bytes,
        feedback_samples,
        writer_instance_id=writer_instance_id,
        now_monotonic=dispatch_ns / 1_000_000_000,
        dispatch_monotonic_ns=dispatch_ns,
        assessment_monotonic_ns=assessment_ns,
        settlement_policy=settlement_policy,
    )
    if (
        report.get("fused_camera_state_action_review_admission_sha256")
        != fused_digest
        or report.get("review_consumption_sha256")
        != result.admission.consumption_sha256
        or report.get("permit_binding_sha256")
        != result.admission.permit_binding_sha256
    ):
        raise FusedCameraStateReviewedMotionPermitError(
            "fused runtime rehearsal lineage was not preserved"
        )
    return report


__all__ = [
    "claim_fused_camera_state_native_t102_writer_v1",
    "FusedCameraStateReviewedMotionPermitError",
    "FusedCameraStateReviewedMotionPermitResultV1",
    "FusedCameraStateReviewedMotionPermitSessionV1",
    "execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1",
    "prepare_fused_camera_state_native_t102_handoff_v1",
]
