"""Private application orchestration for one owned calibrated feedback query.

This boundary validates the offline approval chain before staging, claims one
attempt directory, supervises the source-pinned child once, verifies its
retained journal, and only then completes the calibrated execution receipt.
It exposes no CLI and grants no motion, retry, or continuing connection.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from threading import Event
import time
from typing import Any, Callable, Mapping

from rocell.calibration.position_vector_campaign import canonical_sha256
from rocell.providers.windows.arm_feedback_worker import ReviewedControllerBinding
from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
    canonical,
    decode_request,
    verify_exported_journal,
)
from rocell.providers.windows.calibrated_position_vector_owned_supervisor import (
    stage_calibrated_position_vector_worker,
)
from rocell.providers.windows.owned_worker_process import (
    OwnedWindowsWorker,
    OwnedWorkerResult,
    owned_request_wire,
)

from .calibrated_position_vector_feedback_execution import (
    complete_qualified_calibrated_feedback_request,
    prepare_qualified_calibrated_feedback_request,
)


CLAIM_SCHEMA = "rocell.calibrated_position_vector_owned_execution_claim.v1"


@dataclass(frozen=True, slots=True)
class CalibratedPositionVectorOwnedExecutionOutcome:
    stage: str
    owned: OwnedWorkerResult | None
    verified_child_result: Mapping[str, Any] | None
    execution_receipt: Mapping[str, Any] | None
    working_directory: Path | None
    error_type: str | None
    automatic_retry_allowed: bool = False
    motion_authorized: bool = False
    physical_authority: bool = False


def _publish_document(path: Path, value: Mapping[str, Any] | bytes) -> None:
    """Create one durable attempt document; an existing file is never reused."""

    raw = value if type(value) is bytes else canonical(value) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def run_owned_qualified_calibrated_feedback_request(
    root: Path,
    *,
    feedback_request_execution_approval_receipt_document: Mapping[str, Any],
    execution_prerequisites_document: Mapping[str, Any],
    calibration_document: Mapping[str, Any],
    approval_arguments: Mapping[str, Any],
    reviewed_controller: ReviewedControllerBinding,
    fresh_identity: Any,
    installed_firmware_sha256: str,
    source_sha256: str,
    expires_monotonic_ns: int,
    cancellation: Event,
    check_current: Callable[[], Any],
    wall_clock: Callable[[], str],
    monotonic_clock: Callable[[], int] = time.monotonic_ns,
    _worker_factory: Callable[..., Any] = OwnedWindowsWorker,
) -> CalibratedPositionVectorOwnedExecutionOutcome:
    """Redeem, supervise, retain, and complete exactly one approved query.

    Failures are returned with their last owned evidence.  No branch retries an
    attempt, and creation of the attempt directory makes the attempt ID
    terminal even if dispatch or retention later fails.
    """

    if (
        type(cancellation) is not Event
        or not callable(check_current)
        or not callable(wall_clock)
        or not callable(monotonic_clock)
        or not callable(_worker_factory)
    ):
        raise ValueError("exact owned execution host inputs required")

    stage = "PREPARATION"
    owned = None
    verified = None
    receipt = None
    working = None
    try:
        prepared = prepare_qualified_calibrated_feedback_request(
            feedback_request_execution_approval_receipt_document=(
                feedback_request_execution_approval_receipt_document
            ),
            execution_prerequisites_document=execution_prerequisites_document,
            calibration_document=calibration_document,
            prepared_at=wall_clock(),
            approval_arguments=approval_arguments,
        )

        def current() -> None:
            if cancellation.is_set():
                raise ValueError("calibrated feedback execution cancelled")
            if check_current() is not None:
                raise ValueError("calibrated feedback host context changed")
            if monotonic_clock() >= expires_monotonic_ns:
                raise ValueError("calibrated feedback monotonic lifetime expired")

        current()
        staged = stage_calibrated_position_vector_worker(
            Path(root),
            reviewed_controller=reviewed_controller,
            fresh_identity=fresh_identity,
            request=dict(prepared.request),
            controller_binding=dict(prepared.controller_binding),
            installed_firmware_sha256=installed_firmware_sha256,
            source_sha256=source_sha256,
            expires_monotonic_ns=expires_monotonic_ns,
        )
        working = staged.working_directory
        decoded_wire = decode_request(staged.wire)
        claim = {
            "schema": CLAIM_SCHEMA,
            "attempt_id": prepared.request["attempt_id"],
            "runtime_session_id": prepared.request["runtime_session_id"],
            "request_sha256": decoded_wire["request_sha256"],
            "request_execution_approval_receipt_sha256": canonical_sha256(
                prepared.approval_receipt
            ),
            "execution_prerequisites_sha256": canonical_sha256(
                prepared.prerequisites
            ),
            "calibration_sha256": canonical_sha256(prepared.calibration),
            "source_sha256": source_sha256,
            "expires_monotonic_ns": expires_monotonic_ns,
            "automatic_retry_allowed": False,
            "motion_authorized": False,
            "physical_authority": False,
        }
        _publish_document(working / "application-claim.json", claim)
        _publish_document(working / "supervisor-request.json", staged.wire)
        _, request_digest = owned_request_wire(
            staged.registration,
            staged.request,
            deadline_ns=expires_monotonic_ns,
        )

        def authorize(registration, request, actual_digest) -> None:
            if (
                registration != staged.registration
                or request != staged.request
                or actual_digest != request_digest
            ):
                raise ValueError("calibrated feedback dispatch inputs changed")
            current()

        current()
        stage = "SUPERVISION"
        owned = _worker_factory(
            staged.registration,
            authorizer=authorize,
            _clock=monotonic_clock,
        ).run(
            staged.request,
            cancellation=cancellation,
            deadline_ns=expires_monotonic_ns,
        )
        stage = "RETENTION"
        if type(owned) is not OwnedWorkerResult or type(owned.parsed_result) is not dict:
            raise ValueError("exact owned position-vector result required")
        _publish_document(working / "supervisor-result.json", owned.parsed_result)
        verified = verify_exported_journal(
            owned.parsed_result,
            wire=decoded_wire,
            working_directory=working,
        )
        child = verified["child_result"]
        if owned.status != "SUCCEEDED" or child["status"] != "SUCCEEDED":
            return CalibratedPositionVectorOwnedExecutionOutcome(
                "RETAINED_FAILED_NO_RETRY",
                owned,
                verified,
                None,
                working,
                owned.primary_error or child["error"],
            )
        stage = "COMPLETION"
        receipt = complete_qualified_calibrated_feedback_request(
            prepared,
            exchange_evidence_document=child["exchange_evidence"],
            executed_at=wall_clock(),
        )
        return CalibratedPositionVectorOwnedExecutionOutcome(
            "COMPLETED", owned, verified, receipt, working, None
        )
    except Exception as error:
        return CalibratedPositionVectorOwnedExecutionOutcome(
            stage + "_FAILED",
            owned,
            verified,
            receipt,
            working,
            type(error).__name__,
        )


__all__ = [
    "CLAIM_SCHEMA",
    "CalibratedPositionVectorOwnedExecutionOutcome",
    "run_owned_qualified_calibrated_feedback_request",
]
