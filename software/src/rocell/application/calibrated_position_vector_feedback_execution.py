"""One-shot calibrated position-vector feedback execution boundary.

This module joins the offline position-vector approval chain to one injected
transport operation.  It owns no native adapter and exposes no live CLI.  A
caller must supply fresh physical prerequisites and a transport that returns
the exact bounded exchange evidence.  The request cannot represent motion and
is invoked once with no retry loop.
"""

from __future__ import annotations

import hashlib
import re
import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from rocell.arm.feedback_profile import (
    Feedback1051Profile,
    classify_feedback_1051_profile,
)
from rocell.arm.feedback_wire import FeedbackWireError, validate_feedback_response_line
from rocell.arm.position_vector_calibration import (
    convert_position_vector_feedback,
    load_position_vector_calibration,
)
from rocell.calibration.position_vector_campaign import (
    CALIBRATED_FEEDBACK_REQUEST_CONTRACT,
    QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTION_APPROVAL_RECEIPT_SCHEMA,
    approve_qualified_calibrated_feedback_request_execution,
    canonical_sha256,
)


PREREQUISITES_SCHEMA = (
    "rocell.position_vector_calibration_qualified_feedback_request_"
    "execution_prerequisites.v1"
)
EXCHANGE_EVIDENCE_SCHEMA = (
    "rocell.position_vector_calibration_qualified_feedback_request_"
    "exchange_evidence.v1"
)
EXECUTION_RECEIPT_SCHEMA = (
    "rocell.position_vector_calibration_qualified_feedback_request_"
    "execution_receipt.v1"
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PREREQUISITE_FIELDS = frozenset(
    {
        "schema",
        "attempt_id",
        "runtime_session_id",
        "request_execution_approval_receipt_sha256",
        "operator_id",
        "confirmed_at",
        "expires_at",
        "operator_present",
        "adapter_powered",
        "usb_connected",
        "arm_secured",
        "arm_stationary",
        "area_clear",
        "firmware_unchanged",
    }
)
_EXCHANGE_FIELDS = frozenset(
    {
        "schema",
        "attempt_id",
        "status",
        "request_line_utf8",
        "response_line_utf8",
        "request_count",
        "write_attempt_count",
        "confirmed_write_bytes",
        "automatic_retry_count",
        "response_count",
        "cleanup_confirmed",
        "motion_command_count",
        "started_at",
        "finished_at",
        "errors",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "attempt_id",
        "runtime_session_id",
        "calibration_id",
        "attachment_profile",
        "controller_binding_sha256",
        "request_contract",
        "request_contract_sha256",
        "request_execution_approval_receipt_sha256",
        "execution_prerequisites_sha256",
        "exchange_evidence_sha256",
        "response_line_sha256",
        "response_message",
        "calibrated_feedback",
        "operator_id",
        "confirmed_at",
        "executed_at",
        "next_required_gate",
        "limitations",
        "authority",
        "calibrated_feedback_request_executed",
        "calibrated_feedback_conversion_accepted",
        "motion_authorized",
        "physical_authority",
    }
)


class CalibratedFeedbackExecutionError(ValueError):
    """The approved one-shot execution boundary was not satisfied."""


@dataclass(frozen=True, slots=True)
class PreparedCalibratedFeedbackRequest:
    """Validated immutable-by-copy inputs for one exact feedback exchange."""

    approval_receipt: Mapping[str, Any]
    prerequisites: Mapping[str, Any]
    calibration: Mapping[str, Any]
    controller_binding: Mapping[str, Any]
    request: Mapping[str, Any]
    approval_arguments: Mapping[str, Any]


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibratedFeedbackExecutionError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if set(value) != fields:
        raise CalibratedFeedbackExecutionError(
            f"{label} fields do not match the contract"
        )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise CalibratedFeedbackExecutionError(
            f"{label} is not a bounded identifier"
        )
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise CalibratedFeedbackExecutionError(
            f"{label} is not a lowercase SHA-256"
        )
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise CalibratedFeedbackExecutionError(f"{label} is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CalibratedFeedbackExecutionError(f"{label} is invalid") from exc
    if result.tzinfo is None:
        raise CalibratedFeedbackExecutionError(f"{label} must include a UTC offset")
    return result


def _validate_prerequisites(
    document: Mapping[str, Any],
    *,
    approval_receipt: Mapping[str, Any],
    executed_at: str,
) -> Mapping[str, Any]:
    prerequisites = _mapping(document, "execution prerequisites")
    _exact(prerequisites, _PREREQUISITE_FIELDS, "execution prerequisites")
    if prerequisites["schema"] != PREREQUISITES_SCHEMA:
        raise CalibratedFeedbackExecutionError(
            "execution prerequisites schema is invalid"
        )
    _identifier(prerequisites["attempt_id"], "attempt_id")
    _identifier(prerequisites["operator_id"], "operator_id")
    if prerequisites["runtime_session_id"] != approval_receipt["runtime_session_id"]:
        raise CalibratedFeedbackExecutionError(
            "execution prerequisites runtime session mismatch"
        )
    expected_approval_hash = canonical_sha256(approval_receipt)
    if prerequisites["request_execution_approval_receipt_sha256"] != (
        expected_approval_hash
    ):
        raise CalibratedFeedbackExecutionError(
            "execution prerequisites approval receipt mismatch"
        )
    _digest(
        prerequisites["request_execution_approval_receipt_sha256"],
        "request_execution_approval_receipt_sha256",
    )
    required = (
        "operator_present",
        "adapter_powered",
        "usb_connected",
        "arm_secured",
        "arm_stationary",
        "area_clear",
        "firmware_unchanged",
    )
    if any(prerequisites[name] is not True for name in required):
        raise CalibratedFeedbackExecutionError(
            "all live execution prerequisites must be freshly confirmed"
        )
    confirmed = _timestamp(prerequisites["confirmed_at"], "confirmed_at")
    expires = _timestamp(prerequisites["expires_at"], "expires_at")
    execution = _timestamp(executed_at, "executed_at")
    if not confirmed <= execution <= expires:
        raise CalibratedFeedbackExecutionError(
            "execution is outside the confirmed prerequisite interval"
        )
    if not 0 < (expires - confirmed).total_seconds() <= 300:
        raise CalibratedFeedbackExecutionError(
            "execution prerequisite interval must be positive and at most five minutes"
        )
    return prerequisites


def _validate_exchange(
    value: Mapping[str, Any],
    *,
    attempt_id: str,
    confirmed_at: str,
    executed_at: str,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    evidence = _mapping(value, "exchange evidence")
    _exact(evidence, _EXCHANGE_FIELDS, "exchange evidence")
    if (
        evidence["schema"] != EXCHANGE_EVIDENCE_SCHEMA
        or evidence["attempt_id"] != attempt_id
        or evidence["status"] != "RESPONSE_OBSERVED_CLOSED"
    ):
        raise CalibratedFeedbackExecutionError(
            "exchange evidence does not record one completed response"
        )
    request_line = CALIBRATED_FEEDBACK_REQUEST_CONTRACT["request_line_utf8"]
    if evidence["request_line_utf8"] != request_line:
        raise CalibratedFeedbackExecutionError("exchange request line is not exact")
    expected_counts = {
        "request_count": 1,
        "write_attempt_count": 1,
        "confirmed_write_bytes": len(request_line.encode("utf-8")),
        "automatic_retry_count": 0,
        "response_count": 1,
        "motion_command_count": 0,
    }
    for name, expected in expected_counts.items():
        if type(evidence[name]) is not int or evidence[name] != expected:
            raise CalibratedFeedbackExecutionError(
                f"exchange evidence {name} is not exact"
            )
    if evidence["cleanup_confirmed"] is not True or evidence["errors"] != []:
        raise CalibratedFeedbackExecutionError(
            "exchange cleanup or error evidence is not successful"
        )
    started = _timestamp(evidence["started_at"], "exchange started_at")
    finished = _timestamp(evidence["finished_at"], "exchange finished_at")
    confirmed = _timestamp(confirmed_at, "prerequisites confirmed_at")
    execution = _timestamp(executed_at, "executed_at")
    if not confirmed <= started <= finished <= execution:
        raise CalibratedFeedbackExecutionError(
            "exchange timestamps are not ordered within the confirmed execution interval"
        )
    response_line = evidence["response_line_utf8"]
    if not isinstance(response_line, str):
        raise CalibratedFeedbackExecutionError("exchange response line is not text")
    try:
        message = validate_feedback_response_line(
            response_line,
            max_line_bytes=CALIBRATED_FEEDBACK_REQUEST_CONTRACT[
                "maximum_response_line_bytes"
            ],
        )
    except FeedbackWireError as exc:
        raise CalibratedFeedbackExecutionError(
            "exchange response does not satisfy the feedback wire contract"
        ) from exc
    if classify_feedback_1051_profile(message) is not (
        Feedback1051Profile.POSITION_VECTOR_NAMED_POSE
    ):
        raise CalibratedFeedbackExecutionError(
            "exchange response is not the installed position-vector profile"
        )
    return evidence, message


def prepare_qualified_calibrated_feedback_request(
    *,
    feedback_request_execution_approval_receipt_document: Mapping[str, Any],
    execution_prerequisites_document: Mapping[str, Any],
    calibration_document: Mapping[str, Any],
    prepared_at: str,
    approval_arguments: Mapping[str, Any],
) -> PreparedCalibratedFeedbackRequest:
    """Validate and freeze one request before an exchange can be dispatched."""
    arguments = _mapping(approval_arguments, "approval arguments")
    expected_approval_receipt = (
        approve_qualified_calibrated_feedback_request_execution(**arguments)
    )
    supplied_approval_receipt = _mapping(
        feedback_request_execution_approval_receipt_document,
        "feedback request execution approval receipt",
    )
    if dict(supplied_approval_receipt) != expected_approval_receipt:
        raise CalibratedFeedbackExecutionError(
            "feedback request execution approval receipt does not reproduce"
        )
    if (
        supplied_approval_receipt.get("schema")
        != QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTION_APPROVAL_RECEIPT_SCHEMA
        or supplied_approval_receipt.get(
            "calibrated_feedback_request_execution_authorized"
        )
        is not True
        or supplied_approval_receipt.get("calibrated_feedback_requests_authorized")
        is not True
        or supplied_approval_receipt.get("request_contract")
        != CALIBRATED_FEEDBACK_REQUEST_CONTRACT
    ):
        raise CalibratedFeedbackExecutionError(
            "feedback request execution is not exactly authorized"
        )

    prerequisites = _validate_prerequisites(
        execution_prerequisites_document,
        approval_receipt=supplied_approval_receipt,
        executed_at=prepared_at,
    )
    calibration = _mapping(calibration_document, "calibration document")
    loaded_calibration = load_position_vector_calibration(calibration)
    if canonical_sha256(calibration) != supplied_approval_receipt["artifact_sha256"]:
        raise CalibratedFeedbackExecutionError(
            "calibration artifact does not match execution approval"
        )
    controller_binding = dict(loaded_calibration.controller_binding)
    if canonical_sha256(controller_binding) != supplied_approval_receipt[
        "controller_binding_sha256"
    ]:
        raise CalibratedFeedbackExecutionError(
            "calibration controller binding does not match execution approval"
        )

    attempt_id = prerequisites["attempt_id"]
    request = {
        "schema": "rocell.position_vector_calibration_qualified_feedback_request.v1",
        "attempt_id": attempt_id,
        "runtime_session_id": supplied_approval_receipt["runtime_session_id"],
        "request_execution_approval_receipt_sha256": canonical_sha256(
            supplied_approval_receipt
        ),
        "execution_prerequisites_sha256": canonical_sha256(prerequisites),
        "request_contract": dict(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
    }
    return PreparedCalibratedFeedbackRequest(
        copy.deepcopy(dict(supplied_approval_receipt)),
        copy.deepcopy(dict(prerequisites)),
        copy.deepcopy(dict(calibration)),
        copy.deepcopy(controller_binding),
        copy.deepcopy(request),
        copy.deepcopy(dict(arguments)),
    )


def complete_qualified_calibrated_feedback_request(
    prepared: PreparedCalibratedFeedbackRequest,
    *,
    exchange_evidence_document: Mapping[str, Any],
    executed_at: str,
) -> dict[str, Any]:
    """Accept verified exchange evidence and produce the calibrated receipt."""

    if type(prepared) is not PreparedCalibratedFeedbackRequest:
        raise CalibratedFeedbackExecutionError("exact prepared request is required")
    reproduced = prepare_qualified_calibrated_feedback_request(
        feedback_request_execution_approval_receipt_document=(
            prepared.approval_receipt
        ),
        execution_prerequisites_document=prepared.prerequisites,
        calibration_document=prepared.calibration,
        prepared_at=executed_at,
        approval_arguments=prepared.approval_arguments,
    )
    if (
        reproduced.request != prepared.request
        or reproduced.controller_binding != prepared.controller_binding
    ):
        raise CalibratedFeedbackExecutionError("prepared request changed")
    prerequisites = reproduced.prerequisites
    supplied_approval_receipt = reproduced.approval_receipt
    attempt_id = prerequisites["attempt_id"]
    exchange_evidence, response_message = _validate_exchange(
        exchange_evidence_document,
        attempt_id=attempt_id,
        confirmed_at=prerequisites["confirmed_at"],
        executed_at=executed_at,
    )
    calibrated_feedback = convert_position_vector_feedback(
        response_message, reproduced.calibration, reproduced.controller_binding
    )
    response_line = exchange_evidence["response_line_utf8"].encode("utf-8")
    receipt = {
        "schema": EXECUTION_RECEIPT_SCHEMA,
        "status": "QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTED",
        "attempt_id": attempt_id,
        "runtime_session_id": supplied_approval_receipt["runtime_session_id"],
        "calibration_id": supplied_approval_receipt["calibration_id"],
        "attachment_profile": supplied_approval_receipt["attachment_profile"],
        "controller_binding_sha256": supplied_approval_receipt[
            "controller_binding_sha256"
        ],
        "request_contract": dict(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
        "request_contract_sha256": canonical_sha256(
            CALIBRATED_FEEDBACK_REQUEST_CONTRACT
        ),
        "request_execution_approval_receipt_sha256": canonical_sha256(
            supplied_approval_receipt
        ),
        "execution_prerequisites_sha256": canonical_sha256(prerequisites),
        "exchange_evidence_sha256": canonical_sha256(exchange_evidence),
        "response_line_sha256": hashlib.sha256(response_line).hexdigest(),
        "response_message": response_message,
        "calibrated_feedback": calibrated_feedback,
        "operator_id": prerequisites["operator_id"],
        "confirmed_at": prerequisites["confirmed_at"],
        "executed_at": executed_at,
        "next_required_gate": (
            "CALIBRATED_POSITION_VECTOR_FEEDBACK_REQUEST_EXECUTION_REVIEW"
        ),
        "limitations": [
            "This receipt covers one exact T=105 request and one bounded T=1051 position-vector response.",
            "The calibrated observation grants no motion, contact, retry, or continuing connection authority.",
            "Any later request requires a new approval and fresh physical prerequisites.",
        ],
        "authority": {
            "controller_opened": True,
            "camera_opened": False,
            "commands_sent": 1,
            "motion_commands_sent": 0,
            "automatic_retries": 0,
            "motion_authorized": False,
            "physical_authority": False,
        },
        "calibrated_feedback_request_executed": True,
        "calibrated_feedback_conversion_accepted": True,
        "motion_authorized": False,
        "physical_authority": False,
    }
    _exact(receipt, _RECEIPT_FIELDS, "execution receipt")
    return receipt


def execute_qualified_calibrated_feedback_request(
    *,
    feedback_request_execution_approval_receipt_document: Mapping[str, Any],
    execution_prerequisites_document: Mapping[str, Any],
    calibration_document: Mapping[str, Any],
    executed_at: str,
    exchange: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    approval_arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute one approved request through one explicit injected exchange."""

    if not callable(exchange):
        raise CalibratedFeedbackExecutionError("an explicit exchange is required")
    prepared = prepare_qualified_calibrated_feedback_request(
        feedback_request_execution_approval_receipt_document=(
            feedback_request_execution_approval_receipt_document
        ),
        execution_prerequisites_document=execution_prerequisites_document,
        calibration_document=calibration_document,
        prepared_at=executed_at,
        approval_arguments=approval_arguments,
    )
    evidence = exchange(dict(prepared.request))
    return complete_qualified_calibrated_feedback_request(
        prepared,
        exchange_evidence_document=evidence,
        executed_at=executed_at,
    )


__all__ = [
    "CalibratedFeedbackExecutionError",
    "PreparedCalibratedFeedbackRequest",
    "EXCHANGE_EVIDENCE_SCHEMA",
    "EXECUTION_RECEIPT_SCHEMA",
    "PREREQUISITES_SCHEMA",
    "complete_qualified_calibrated_feedback_request",
    "execute_qualified_calibrated_feedback_request",
    "prepare_qualified_calibrated_feedback_request",
]
