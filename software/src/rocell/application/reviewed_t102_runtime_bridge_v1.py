"""Bind reviewed motion authority to the production-shaped T=102 runtime.

ARM-048 qualified one final-boundary write and settlement lifecycle using a
Cartesian fixture.  The actual trajectory encoder and production-runtime
contract use ordered T=102 joint frames.  This bridge resolves that seam without
opening hardware: it binds the exact supervisor permit to the decoded T=102
message, the controller session/configuration epoch/profile, one modeled write,
one correlated T=1021 acknowledgment, and fresh T=1051 joint feedback.

No object in this module owns a serial factory, port, socket, callback, device
handle, firmware operation, or live transport.  Native enablement remains a
separate physical qualification and authorization step.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from rocell.arm.all_joint_command import JOINT_FIELDS
from rocell.arm.protocol import decode_line, encode_line, feedback_request
from rocell.safety.permit import MotionPermit, goal_hash

from .production_controller_runtime_contract_v1 import (
    ProductionControllerRuntimeContractV1,
    ProductionRuntimeState,
    RuntimeCommandFrameV1,
)
from .reviewed_motion_permit_bridge_v1 import (
    ReviewedActionLifecycleV1,
    ReviewedMotionPermitAdmissionV1,
)
from .reviewed_motion_sole_writer_v1 import (
    IncapableReviewedMotionIoV1,
    _dispatch_receipt,
)


SCHEMA = "rocell.reviewed_t102_runtime_execution_rehearsal.v1"
SETTLEMENT_SCHEMA = "rocell.reviewed_t102_joint_settlement.v1"
_FEEDBACK_FIELDS = ("b", "s", "e", "t", "r", "g")


class ReviewedT102RuntimeBridgeError(ValueError):
    """The reviewed permit, frame, runtime, or feedback binding is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReviewedT102RuntimeBridgeError(
            f"{label} must be positive nanoseconds")
    return value


@dataclass(frozen=True, slots=True)
class JointSettlementPolicyV1:
    tolerance_rad: float = 0.04
    required_consecutive_samples: int = 2
    max_feedback_age_ns: int = 500_000_000

    def __post_init__(self) -> None:
        if (
            isinstance(self.tolerance_rad, bool)
            or not isinstance(self.tolerance_rad, (int, float))
            or not math.isfinite(float(self.tolerance_rad))
            or float(self.tolerance_rad) < 0
        ):
            raise ReviewedT102RuntimeBridgeError(
                "tolerance_rad must be finite and nonnegative")
        object.__setattr__(self, "tolerance_rad", float(self.tolerance_rad))
        if (
            isinstance(self.required_consecutive_samples, bool)
            or not isinstance(self.required_consecutive_samples, int)
            or not 2 <= self.required_consecutive_samples <= 16
        ):
            raise ReviewedT102RuntimeBridgeError(
                "required_consecutive_samples must be in 2..16")
        _positive_ns(self.max_feedback_age_ns, "max_feedback_age_ns")


def _joint_settlement(
    runtime: ProductionControllerRuntimeContractV1,
    frame: RuntimeCommandFrameV1,
    feedback_samples: Iterable[Mapping[str, Any]], *,
    policy: JointSettlementPolicyV1, dispatch_ns: int, assessment_ns: int,
) -> dict[str, Any]:
    target_message = decode_line(frame.wire_bytes)
    targets = tuple(float(target_message[name]) for name in JOINT_FIELDS)
    previous_ns = dispatch_ns
    previous_values: tuple[float, ...] | None = None
    consecutive = 0
    max_error = 0.0
    accepted_hashes: list[str] = []
    rejected_codes: list[str] = []
    request = encode_line(feedback_request())
    runtime_fault = False

    try:
        samples = tuple(feedback_samples)
    except Exception:
        samples = ()
        rejected_codes.append("FEEDBACK_COLLECTION_ERROR")
        runtime_fault = True

    for sample in samples:
        if not isinstance(sample, Mapping):
            rejected_codes.append("MALFORMED_SAMPLE")
            consecutive = 0
            previous_values = None
            continue
        captured = sample.get("captured_monotonic_ns")
        response = sample.get("response_bytes")
        if (
            isinstance(captured, bool) or not isinstance(captured, int)
            or captured <= previous_ns
        ):
            rejected_codes.append("NON_MONOTONIC_OR_PRE_DISPATCH")
            consecutive = 0
            previous_values = None
            continue
        previous_ns = captured
        if (
            captured > assessment_ns
            or assessment_ns - captured > policy.max_feedback_age_ns
        ):
            rejected_codes.append("STALE_OR_FUTURE_FEEDBACK")
            consecutive = 0
            previous_values = None
            continue
        if not isinstance(response, bytes):
            rejected_codes.append("MALFORMED_RESPONSE_BYTES")
            consecutive = 0
            previous_values = None
            continue
        try:
            parsed = runtime.rehearse_feedback_exchange(request, response)
        except Exception:
            rejected_codes.append("RUNTIME_REJECTED_FEEDBACK")
            consecutive = 0
            previous_values = None
            runtime_fault = True
            break
        values = tuple(float(parsed[name]) for name in _FEEDBACK_FIELDS)
        error = max(abs(value - target) for value, target in zip(values, targets))
        max_error = max(max_error, error)
        stable = previous_values is None or max(
            abs(value - previous) for value, previous in zip(values, previous_values)
        ) <= policy.tolerance_rad
        consecutive = consecutive + 1 if error <= policy.tolerance_rad and stable else 0
        previous_values = values
        accepted_hashes.append(hashlib.sha256(response).hexdigest())

    settled = (
        not runtime_fault
        and consecutive >= policy.required_consecutive_samples
    )
    unsigned = {
        "schema": SETTLEMENT_SCHEMA,
        "status": "OBSERVED_SETTLED_JOINT_ARRIVAL" if settled else "JOINT_ARRIVAL_UNVERIFIED",
        "frame_sha256": frame.frame_sha256,
        "goal_sha256": goal_hash(target_message),
        "assessed_monotonic_ns": assessment_ns,
        "accepted_sample_count": len(accepted_hashes),
        "feedback_response_sha256": accepted_hashes,
        "rejected_sample_codes": rejected_codes,
        "consecutive_settled_samples": consecutive,
        "required_consecutive_samples": policy.required_consecutive_samples,
        "tolerance_rad": policy.tolerance_rad,
        "max_joint_error_rad": max_error,
        "controller_receipt_claimed": True,
        "controller_arrival_claimed": settled,
        "independent_task_outcome_verified": False,
    }
    return {**unsigned, "settlement_sha256": _sha256(unsigned)}


def execute_reviewed_t102_runtime_rehearsal_v1(
    frame: RuntimeCommandFrameV1,
    permit: MotionPermit,
    admission: ReviewedMotionPermitAdmissionV1,
    lifecycle: ReviewedActionLifecycleV1,
    runtime: ProductionControllerRuntimeContractV1,
    io: IncapableReviewedMotionIoV1,
    acknowledgment_bytes: bytes,
    feedback_samples: Iterable[Mapping[str, Any]] = (), *,
    writer_instance_id: str,
    now_monotonic: float,
    dispatch_monotonic_ns: int,
    assessment_monotonic_ns: int,
    settlement_policy: JointSettlementPolicyV1 = JointSettlementPolicyV1(),
) -> dict[str, Any]:
    """Run one T=102 frame through the reviewed, hardware-free runtime seam."""

    if not isinstance(frame, RuntimeCommandFrameV1):
        raise TypeError("frame must be RuntimeCommandFrameV1")
    if not isinstance(permit, MotionPermit):
        raise TypeError("permit must be MotionPermit")
    if not isinstance(admission, ReviewedMotionPermitAdmissionV1):
        raise TypeError("admission must be ReviewedMotionPermitAdmissionV1")
    if not isinstance(lifecycle, ReviewedActionLifecycleV1):
        raise TypeError("lifecycle must be ReviewedActionLifecycleV1")
    if not isinstance(runtime, ProductionControllerRuntimeContractV1):
        raise TypeError("runtime must be ProductionControllerRuntimeContractV1")
    if type(io) is not IncapableReviewedMotionIoV1:
        raise TypeError("exact hardware-incapable I/O is required")
    if not isinstance(settlement_policy, JointSettlementPolicyV1):
        raise TypeError("settlement_policy must be JointSettlementPolicyV1")
    dispatch_ns = _positive_ns(dispatch_monotonic_ns, "dispatch_monotonic_ns")
    assessment_ns = _positive_ns(
        assessment_monotonic_ns, "assessment_monotonic_ns")
    if assessment_ns < dispatch_ns:
        raise ReviewedT102RuntimeBridgeError("assessment precedes dispatch")

    message = decode_line(frame.wire_bytes)
    digest = goal_hash(message)
    manifest = runtime.manifest
    if (
        message.get("T") != 102
        or tuple(message) != ("T", *JOINT_FIELDS, "spd", "acc")
        or digest not in admission.ordered_goal_sha256
        or permit.plan_hash != admission.review_sha256
        or permit.snapshot_hash != admission.snapshot_sha256
        or permit.expires_at_monotonic != admission.permit_expires_at_monotonic
        or frame.writer_instance_id != writer_instance_id
        or frame.controller_session_id != manifest.controller_session_id
        or frame.configuration_epoch_sha256 != manifest.configuration_epoch_sha256
        or frame.encoding_profile_sha256
        != manifest.expected_encoding_profile_sha256
    ):
        raise ReviewedT102RuntimeBridgeError(
            "reviewed permit, T102 frame, or runtime identity differs")

    runtime.claim_writer(writer_instance_id)
    runtime.admit_t102(frame, now_monotonic_ns=dispatch_ns)
    io.claim()
    if permit.allows(message, now_monotonic=now_monotonic) is not True:
        runtime.mark_command_write_uncertain()
        raise ReviewedT102RuntimeBridgeError(
            "exact permit was not consumable; no write attempted")

    confirmed: int | None = None
    error_code: str | None = None
    try:
        confirmed = io._write_once(frame.wire_bytes)
    except ConnectionError:
        error_code = "DISCONNECT_AFTER_WRITE"
    except Exception as exc:
        error_code = type(exc).__name__.upper()
    typed_receipt = _dispatch_receipt(
        admission=admission, goal=message, payload=frame.wire_bytes, io=io,
        confirmed_bytes=confirmed, dispatched_monotonic_ns=dispatch_ns,
        error_code=error_code,
    )
    receipt = typed_receipt.to_dict()
    lifecycle.started_from_dispatch(typed_receipt, event_monotonic_ns=dispatch_ns)

    acknowledgment: dict[str, Any] | None = None
    settlement: dict[str, Any] | None = None
    if receipt["status"] == "ZERO_WRITE_CONFIRMED":
        runtime.mark_command_zero_write()
        terminal = "FAILED"
        detail_sha256 = receipt["dispatch_receipt_sha256"]
    elif receipt["status"] != "REPLAY_WRITE_CONFIRMED":
        runtime.mark_command_write_uncertain()
        terminal = "UNCERTAIN"
        detail_sha256 = receipt["dispatch_receipt_sha256"]
    else:
        try:
            ack = runtime.rehearse_command_acknowledgment(acknowledgment_bytes)
            acknowledgment = {
                **ack.to_dict(),
                "frame_sha256": frame.frame_sha256,
                "correlation_id": frame.correlation_id,
                "controller_session_id": frame.controller_session_id,
                "modeled_controller_receipt": True,
                "authentic_physical_receipt": False,
            }
            acknowledgment["acknowledgment_sha256"] = _sha256(acknowledgment)
        except Exception as exc:
            acknowledgment = {
                "status": "ACKNOWLEDGMENT_REJECTED",
                "error_code": type(exc).__name__,
                "response_bytes_sha256": (
                    hashlib.sha256(acknowledgment_bytes).hexdigest()
                    if isinstance(acknowledgment_bytes, bytes) else None
                ),
                "authentic_physical_receipt": False,
            }
            acknowledgment["acknowledgment_sha256"] = _sha256(acknowledgment)
            terminal = "UNCERTAIN"
            detail_sha256 = acknowledgment["acknowledgment_sha256"]
        else:
            settlement = _joint_settlement(
                runtime, frame, feedback_samples, policy=settlement_policy,
                dispatch_ns=dispatch_ns, assessment_ns=assessment_ns,
            )
            terminal = (
                "COMPLETED"
                if settlement["status"] == "OBSERVED_SETTLED_JOINT_ARRIVAL"
                else "UNCERTAIN"
            )
            if runtime.state is ProductionRuntimeState.WRITER_CLAIMED:
                runtime.close_single_action(settled=terminal == "COMPLETED")
            detail_sha256 = settlement["settlement_sha256"]

    lifecycle.terminal(
        terminal, detail_sha256=detail_sha256,
        event_monotonic_ns=assessment_ns,
    )
    runtime_report = runtime.report()
    unsigned = {
        "schema": SCHEMA,
        "status": terminal,
        "permit_binding_sha256": admission.permit_binding_sha256,
        "frame_sha256": frame.frame_sha256,
        "dispatch": receipt,
        "acknowledgment": acknowledgment,
        "settlement": settlement,
        "runtime_report": runtime_report,
        "lifecycle": lifecycle.snapshot(),
        "automatic_retry_allowed": False,
        "follow_on_movement_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
        "physical_command_writes": 0,
        "limitations": [
            "HARDWARE_INCAPABLE_RUNTIME_REHEARSAL",
            "NO_AUTHENTIC_PHYSICAL_CONTROLLER_RECEIPT",
            "NO_INDEPENDENT_TASK_OUTCOME",
        ],
    }
    if admission.fused_camera_state_action_review_admission_sha256 is not None:
        unsigned["fused_camera_state_action_review_admission_sha256"] = (
            admission.fused_camera_state_action_review_admission_sha256
        )
        unsigned["review_consumption_sha256"] = admission.consumption_sha256
    return {**unsigned, "execution_sha256": _sha256(unsigned)}


__all__ = [
    "SCHEMA", "SETTLEMENT_SCHEMA", "JointSettlementPolicyV1",
    "ReviewedT102RuntimeBridgeError",
    "execute_reviewed_t102_runtime_rehearsal_v1",
]
