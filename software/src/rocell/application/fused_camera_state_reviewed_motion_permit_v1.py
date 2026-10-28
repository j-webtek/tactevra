"""Issue one exact supervisor permit from one fused camera-state review.

This orchestration boundary owns the transition from a fused, zero-authority
execution review to the existing safety supervisor.  It derives the capability
from the review, uses one monotonic clock for consumption and authorization,
and prevents a permit from outliving the review that justified it.  It performs
no transport access and writes no controller command.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from rocell.calibration.artifacts import CalibrationResolution
from rocell.rc03.build_snapshot import Capability
from rocell.safety.interlocks import InterlockSnapshot
from rocell.safety.permit import MotionPermit
from rocell.safety.preflight import RuntimeStatus
from rocell.safety.supervisor import SafetySupervisor

from .reviewed_motion_permit_bridge_v1 import (
    ReviewedActionLifecycleV1,
    ReviewedMotionPermitAdmissionV1,
    issue_reviewed_motion_permit_v1,
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


__all__ = [
    "FusedCameraStateReviewedMotionPermitError",
    "FusedCameraStateReviewedMotionPermitResultV1",
    "FusedCameraStateReviewedMotionPermitSessionV1",
]
