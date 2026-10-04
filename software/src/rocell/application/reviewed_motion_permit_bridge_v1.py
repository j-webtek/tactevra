"""Bridge one consumed execution review into the existing safety supervisor.

The bridge has no transport and performs no write.  It verifies the ARM-046
consumption receipt, asks ``SafetySupervisor`` to re-evaluate current physical
conditions, and binds any resulting exact-goal permit to an append-only action
lifecycle.  A failed admission burns the consumed review; no retry is implied.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from threading import Lock
from typing import Any, Mapping

from rocell.calibration.artifacts import CalibrationResolution
from rocell.rc03.build_snapshot import Capability
from rocell.safety.interlocks import InterlockSnapshot
from rocell.safety.permit import MotionPermit, goal_hash
from rocell.safety.preflight import RuntimeStatus
from rocell.safety.supervisor import SafetySupervisor

from .single_action_execution_review_v1 import SingleActionExecutionReviewV1
from .t102_machine_ledger_v1 import reserve_review


ADMISSION_SCHEMA = "rocell.reviewed_motion_permit_admission.v1"
LIFECYCLE_SCHEMA = "rocell.reviewed_action_lifecycle.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DISPATCH_RECEIPT_ISSUER = object()


class ReviewedMotionPermitBridgeError(ValueError):
    """Review consumption, permit binding, or lifecycle is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ReviewedMotionPermitBridgeError(f"{label} must be a SHA-256 digest")
    return value


def _verified_hash(report: Mapping[str, Any], field: str) -> str:
    claimed = _digest(report.get(field), field)
    unsigned = {key: value for key, value in report.items() if key != field}
    if _sha256(unsigned) != claimed:
        raise ReviewedMotionPermitBridgeError(f"{field} content hash is invalid")
    return claimed


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReviewedMotionPermitBridgeError(f"{label} must be positive nanoseconds")
    return value


@dataclass(frozen=True, slots=True)
class ReviewedMotionPermitAdmissionV1:
    review_sha256: str
    consumption_sha256: str
    capability: Capability
    snapshot_sha256: str
    ordered_goal_sha256: tuple[str, ...]
    permit_expires_at_monotonic: float
    permit_binding_sha256: str

    def __post_init__(self) -> None:
        for field in (
            "review_sha256", "consumption_sha256", "snapshot_sha256",
            "permit_binding_sha256",
        ):
            _digest(getattr(self, field), field)
        if not isinstance(self.capability, Capability):
            raise ReviewedMotionPermitBridgeError("capability must be typed")
        if not self.ordered_goal_sha256:
            raise ReviewedMotionPermitBridgeError("goal hashes cannot be empty")
        for digest in self.ordered_goal_sha256:
            _digest(digest, "ordered_goal_sha256")
        if (
            not isinstance(self.permit_expires_at_monotonic, float)
            or not math.isfinite(self.permit_expires_at_monotonic)
        ):
            raise ReviewedMotionPermitBridgeError("permit expiry must be float")
        expected = _sha256({
            "review_sha256": self.review_sha256,
            "consumption_sha256": self.consumption_sha256,
            "capability": self.capability.value,
            "snapshot_sha256": self.snapshot_sha256,
            "plan_hash": self.review_sha256,
            "ordered_goal_sha256": list(self.ordered_goal_sha256),
            "permit_expires_at_monotonic": self.permit_expires_at_monotonic,
        })
        if expected != self.permit_binding_sha256:
            raise ReviewedMotionPermitBridgeError("permit binding hash is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADMISSION_SCHEMA,
            "status": "MOTION_PERMIT_ISSUED_BY_SAFETY_SUPERVISOR",
            "review_sha256": self.review_sha256,
            "consumption_sha256": self.consumption_sha256,
            "capability": self.capability.value,
            "snapshot_sha256": self.snapshot_sha256,
            "ordered_goal_sha256": list(self.ordered_goal_sha256),
            "permit_expires_at_monotonic": self.permit_expires_at_monotonic,
            "permit_binding_sha256": self.permit_binding_sha256,
            "single_use_exact_goals": True,
            "automatic_retry_allowed": False,
            "hardware_access": False,
            "physical_authority": True,
        }


class ReviewedMotionDispatchReceiptV1:
    """Opaque verified receipt issued only by the owned writer boundary."""

    def __init__(self, document: Mapping[str, Any], *, _issuer: object) -> None:
        if _issuer is not _DISPATCH_RECEIPT_ISSUER:
            raise ReviewedMotionPermitBridgeError(
                "dispatch receipts may only be issued by the sole writer")
        if not isinstance(document, Mapping):
            raise ReviewedMotionPermitBridgeError("dispatch receipt must be a mapping")
        copy = dict(document)
        required = {
            "schema", "status", "review_sha256", "permit_binding_sha256",
            "goal_sha256", "payload_sha256", "payload_bytes",
            "confirmed_bytes", "retained_bytes_sha256", "write_attempts",
            "permit_consumed", "dispatched_monotonic_ns", "error_code",
            "composition", "automatic_retry_allowed", "hardware_access",
            "physical_authority", "physical_command_writes",
            "dispatch_receipt_sha256",
        }
        if set(copy) != required:
            raise ReviewedMotionPermitBridgeError(
                "dispatch receipt fields are not exact")
        _verified_hash(copy, "dispatch_receipt_sha256")
        for field in (
            "review_sha256", "permit_binding_sha256", "goal_sha256",
            "payload_sha256", "retained_bytes_sha256",
        ):
            _digest(copy.get(field), field)
        payload_bytes = copy.get("payload_bytes")
        confirmed_bytes = copy.get("confirmed_bytes")
        if (
            isinstance(payload_bytes, bool) or not isinstance(payload_bytes, int)
            or payload_bytes <= 0
            or not (
                confirmed_bytes is None
                or (
                    not isinstance(confirmed_bytes, bool)
                    and isinstance(confirmed_bytes, int)
                    and 0 <= confirmed_bytes <= payload_bytes
                )
            )
            or not (
                copy.get("error_code") is None
                or (
                    isinstance(copy.get("error_code"), str)
                    and bool(copy.get("error_code"))
                )
            )
        ):
            raise ReviewedMotionPermitBridgeError(
                "dispatch receipt byte accounting is invalid")
        status = copy.get("status")
        error_code = copy.get("error_code")
        status_matches_bytes = (
            (status == "REPLAY_WRITE_CONFIRMED"
             and confirmed_bytes == payload_bytes and error_code is None)
            or (status == "ZERO_WRITE_CONFIRMED"
                and confirmed_bytes == 0 and error_code is None)
            or (status == "PARTIAL_WRITE_CONFIRMED"
                and isinstance(confirmed_bytes, int)
                and 0 < confirmed_bytes < payload_bytes and error_code is None)
            or (status == "WRITE_COMPLETION_UNCERTAIN"
                and confirmed_bytes is None and error_code is not None)
        )
        if not status_matches_bytes:
            raise ReviewedMotionPermitBridgeError(
                "dispatch receipt status does not match byte accounting")
        if (
            copy.get("schema") != "rocell.reviewed_motion_dispatch_receipt.v1"
            or copy.get("status") not in {
                "REPLAY_WRITE_CONFIRMED", "ZERO_WRITE_CONFIRMED",
                "PARTIAL_WRITE_CONFIRMED", "WRITE_COMPLETION_UNCERTAIN",
            }
            or copy.get("write_attempts") != 1
            or copy.get("permit_consumed") is not True
            or copy.get("composition") != "HARDWARE_INCAPABLE_REPLAY"
            or copy.get("automatic_retry_allowed") is not False
            or copy.get("hardware_access") is not False
            or copy.get("physical_authority") is not False
            or copy.get("physical_command_writes") != 0
        ):
            raise ReviewedMotionPermitBridgeError(
                "dispatch receipt authority or status is invalid")
        _positive_ns(copy.get("dispatched_monotonic_ns"),
                     "dispatched_monotonic_ns")
        self._document = copy

    @classmethod
    def _issue_from_owned_writer(
        cls, document: Mapping[str, Any],
    ) -> "ReviewedMotionDispatchReceiptV1":
        return cls(document, _issuer=_DISPATCH_RECEIPT_ISSUER)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._document)


def issue_reviewed_motion_permit_v1(
    supervisor: SafetySupervisor,
    review: SingleActionExecutionReviewV1,
    consumption_receipt: Mapping[str, Any],
    capability: Capability,
    *,
    calibrations: CalibrationResolution,
    interlocks: InterlockSnapshot,
    runtime: RuntimeStatus,
    ttl_s: float,
    now_monotonic: float,
) -> tuple[MotionPermit, ReviewedMotionPermitAdmissionV1]:
    """Ask the sole supervisor to issue an exact-goal permit after review use."""

    if not isinstance(supervisor, SafetySupervisor):
        raise TypeError("supervisor must be a SafetySupervisor")
    if not isinstance(review, SingleActionExecutionReviewV1):
        raise TypeError("review must be a SingleActionExecutionReviewV1")
    if not isinstance(consumption_receipt, Mapping):
        raise TypeError("consumption_receipt must be a mapping")
    if not isinstance(capability, Capability):
        raise TypeError("capability must be a Capability")
    consumption_sha256 = _verified_hash(
        consumption_receipt, "consumption_sha256")
    if (
        consumption_receipt.get("status") != "REVIEW_ADMISSION_CONSUMED"
        or consumption_receipt.get("review_sha256") != review.review_sha256
        or consumption_receipt.get("batch_sha256") != review.batch_sha256
        or consumption_receipt.get("action_index") != review.action_index
        or consumption_receipt.get("proposal_v2_sha256")
        != review.proposal_v2_sha256
        or consumption_receipt.get("permit_issued") is not False
        or consumption_receipt.get("hardware_access") is not False
        or consumption_receipt.get("physical_authority") is not False
    ):
        raise ReviewedMotionPermitBridgeError(
            "consumption receipt differs from the reviewed action")
    expected_capability = (
        Capability.EMPTY_CELL_MOTION
        if review.interaction == "HOVER"
        else Capability.KEYBOARD_CONTACT
        if review.device == "keyboard"
        else Capability.PHONE_CONTACT
    )
    if review.to_dict().get("contact_authority") is not False:
        raise ReviewedMotionPermitBridgeError("review unexpectedly grants contact")
    if capability is not expected_capability:
        raise ReviewedMotionPermitBridgeError(
            "capability differs from reviewed device/interaction")
    goal_tuple = (dict(review.reviewed_t102_goal),)
    goal_hashes = tuple(goal_hash(goal) for goal in goal_tuple)
    if goal_hashes != (review.reviewed_t102_goal_sha256,):
        raise ReviewedMotionPermitBridgeError(
            "requested goal differs from the reviewed T102 trajectory and profile")
    # A failed preflight still burns this review. Re-presenting a copied
    # consumption receipt cannot mint another physical permit.
    reserve_review(
        consumption_sha256, review.review_sha256,
        review.reviewed_t102_goal_sha256)
    report = supervisor.evaluate(
        capability,
        plan_hash=review.review_sha256,
        calibrations=calibrations,
        interlocks=interlocks,
        runtime=runtime,
        now_monotonic=now_monotonic,
    )
    permit = supervisor.authorize(
        report, goals=goal_tuple, ttl_s=ttl_s, now_monotonic=now_monotonic)
    unsigned = {
        "review_sha256": review.review_sha256,
        "consumption_sha256": consumption_sha256,
        "capability": capability.value,
        "snapshot_sha256": permit.snapshot_hash,
        "plan_hash": permit.plan_hash,
        "ordered_goal_sha256": list(goal_hashes),
        "permit_expires_at_monotonic": permit.expires_at_monotonic,
    }
    admission = ReviewedMotionPermitAdmissionV1(
        review.review_sha256, consumption_sha256, capability,
        permit.snapshot_hash, goal_hashes, permit.expires_at_monotonic,
        _sha256(unsigned),
    )
    return permit, admission


class ReviewedActionLifecycleV1:
    """Correlated ACCEPTED/STARTED/terminal acknowledgements, no retry path."""

    def __init__(self, admission: ReviewedMotionPermitAdmissionV1) -> None:
        if not isinstance(admission, ReviewedMotionPermitAdmissionV1):
            raise TypeError("admission must be ReviewedMotionPermitAdmissionV1")
        self._admission = admission
        self._events: list[dict[str, Any]] = []
        self._phase = "ACCEPTED"
        self._lock = Lock()
        self._append("ACCEPTED", None, None)

    def _append(
        self, phase: str, event_monotonic_ns: int | None,
        detail_sha256: str | None,
    ) -> dict[str, Any]:
        previous = self._events[-1]["event_sha256"] if self._events else None
        event = {
            "ordinal": len(self._events), "phase": phase,
            "permit_binding_sha256": self._admission.permit_binding_sha256,
            "event_monotonic_ns": event_monotonic_ns,
            "detail_sha256": detail_sha256, "previous_event_sha256": previous,
            "automatic_retry_allowed": False,
        }
        sealed = {**event, "event_sha256": _sha256(event)}
        self._events.append(sealed)
        return sealed

    def started_from_dispatch(
        self, dispatch_receipt: ReviewedMotionDispatchReceiptV1, *,
        event_monotonic_ns: int,
    ) -> dict[str, Any]:
        """Accept STARTED only from a sealed final-boundary dispatch receipt.

        ARM-047 allowed a caller to supply only a goal digest.  That was useful
        for defining the lifecycle, but it was not evidence that the permit had
        actually been consumed at a writer boundary.  ARM-048 requires the
        complete content-addressed receipt emitted by the sole-writer rehearsal.
        """

        if type(dispatch_receipt) is not ReviewedMotionDispatchReceiptV1:
            raise ReviewedMotionPermitBridgeError(
                "dispatch_receipt must be a verified sole-writer receipt")
        document = dispatch_receipt.to_dict()
        receipt_sha256 = _verified_hash(
            document, "dispatch_receipt_sha256")
        digest = _digest(document.get("goal_sha256"), "goal_sha256")
        now = _positive_ns(event_monotonic_ns, "event_monotonic_ns")
        with self._lock:
            if (
                self._phase != "ACCEPTED"
                or digest not in self._admission.ordered_goal_sha256
                or document.get("schema")
                != "rocell.reviewed_motion_dispatch_receipt.v1"
                or document.get("permit_binding_sha256")
                != self._admission.permit_binding_sha256
                or document.get("review_sha256")
                != self._admission.review_sha256
                or document.get("permit_consumed") is not True
                or document.get("write_attempts") != 1
                or document.get("automatic_retry_allowed") is not False
            ):
                raise ReviewedMotionPermitBridgeError("invalid STARTED acknowledgement")
            self._phase = "STARTED"
            return self._append("STARTED", now, receipt_sha256)

    def terminal(
        self, phase: str, *, detail_sha256: str, event_monotonic_ns: int,
    ) -> dict[str, Any]:
        if phase not in ("COMPLETED", "FAILED", "UNCERTAIN"):
            raise ReviewedMotionPermitBridgeError("terminal phase is invalid")
        detail = _digest(detail_sha256, "detail_sha256")
        now = _positive_ns(event_monotonic_ns, "event_monotonic_ns")
        with self._lock:
            if self._phase != "STARTED":
                raise ReviewedMotionPermitBridgeError(
                    "terminal acknowledgement requires STARTED")
            self._phase = phase
            return self._append(phase, now, detail)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            report = {
                "schema": LIFECYCLE_SCHEMA, "phase": self._phase,
                "review_sha256": self._admission.review_sha256,
                "permit_binding_sha256": self._admission.permit_binding_sha256,
                "events": list(self._events), "automatic_retry_allowed": False,
                "follow_on_movement_authorized": False,
            }
            return {**report, "lifecycle_sha256": _sha256(report)}


__all__ = [
    "ADMISSION_SCHEMA", "LIFECYCLE_SCHEMA", "ReviewedActionLifecycleV1",
    "ReviewedMotionDispatchReceiptV1",
    "ReviewedMotionPermitAdmissionV1", "ReviewedMotionPermitBridgeError",
    "issue_reviewed_motion_permit_v1",
]
