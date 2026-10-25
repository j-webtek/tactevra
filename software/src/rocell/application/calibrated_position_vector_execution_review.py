"""Independent review of one retained calibrated position-vector execution.

The gate replays the supervisor protocol validation, verifies the exported
journal bytes, and reproduces the calibrated observation before accepting or
rejecting it for a later state-admission decision.  It opens no hardware and
grants no motion, retry, connection, or physical authority.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.arm.feedback_wire import validate_feedback_response_line
from rocell.arm.position_vector_calibration import (
    convert_position_vector_feedback,
    load_position_vector_calibration,
)
from rocell.calibration.position_vector_campaign import canonical_sha256
from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
    decode_request,
    verify_exported_journal,
)
from rocell.providers.windows.owned_worker_process import decode_owned_json

from .calibrated_position_vector_feedback_execution import EXECUTION_RECEIPT_SCHEMA
from .calibrated_position_vector_owned_execution import CLAIM_SCHEMA


REVIEW_SCHEMA = "rocell.calibrated_position_vector_execution_review.v1"
REVIEW_RECEIPT_SCHEMA = (
    "rocell.calibrated_position_vector_execution_review_receipt.v1"
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CLAIM_FIELDS = frozenset(
    {
        "schema", "attempt_id", "runtime_session_id", "request_sha256",
        "request_execution_approval_receipt_sha256",
        "execution_prerequisites_sha256", "calibration_sha256", "source_sha256",
        "expires_monotonic_ns", "automatic_retry_allowed", "motion_authorized",
        "physical_authority",
    }
)
_REVIEW_FIELDS = frozenset(
    {
        "schema", "decision", "reviewer_id", "reviewed_at",
        "execution_receipt_sha256", "application_claim_sha256",
        "supervisor_request_sha256", "supervisor_result_sha256",
        "journal_manifest_sha256", "calibration_sha256", "review_notes_sha256",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema", "status", "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile", "execution_receipt_sha256",
        "application_claim_sha256", "supervisor_request_sha256",
        "supervisor_result_sha256", "journal_manifest_sha256",
        "calibration_sha256", "review_sha256", "reviewer_id", "reviewed_at",
        "decision", "calibrated_feedback", "next_required_gate", "limitations",
        "calibrated_feedback_observation_accepted", "automatic_retry_allowed",
        "motion_authorized", "physical_authority",
    }
)


class CalibratedPositionVectorExecutionReviewError(ValueError):
    """The retained execution or its independent review is not exact."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibratedPositionVectorExecutionReviewError(message)


def _exact(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    _require(set(value) == fields, f"{label} fields do not match the contract")


def _identifier(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None,
        f"{label} is not a bounded identifier",
    )
    return value


def _digest(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _DIGEST.fullmatch(value) is not None,
        f"{label} is not a lowercase SHA-256",
    )
    return value


def _timestamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CalibratedPositionVectorExecutionReviewError(
            f"{label} is invalid"
        ) from exc
    _require(result.tzinfo is not None, f"{label} must include a UTC offset")
    return result


def _working_directory(value: Path) -> Path:
    path = Path(value)
    _require(
        path.is_absolute() and path.is_dir() and not path.is_symlink(),
        "existing absolute nonsymlink execution directory required",
    )
    return path.resolve()


def _read(path: Path, maximum: int) -> bytes:
    _require(
        path.is_file() and not path.is_symlink(),
        f"retained execution file unavailable: {path.name}",
    )
    raw = path.read_bytes()
    _require(0 < len(raw) <= maximum, f"retained execution file is out of bounds: {path.name}")
    return raw


def _receipt(value: Mapping[str, Any]) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), "execution receipt must be an object")
    receipt = dict(value)
    required = {
        "schema", "status", "attempt_id", "runtime_session_id", "calibration_id",
        "attachment_profile", "controller_binding_sha256", "request_contract",
        "request_contract_sha256", "request_execution_approval_receipt_sha256",
        "execution_prerequisites_sha256", "exchange_evidence_sha256",
        "response_line_sha256", "response_message", "calibrated_feedback",
        "operator_id", "confirmed_at", "executed_at", "next_required_gate",
        "limitations", "authority", "calibrated_feedback_request_executed",
        "calibrated_feedback_conversion_accepted", "motion_authorized",
        "physical_authority",
    }
    _exact(receipt, frozenset(required), "execution receipt")
    _require(
        receipt["schema"] == EXECUTION_RECEIPT_SCHEMA
        and receipt["status"] == "QUALIFIED_CALIBRATED_FEEDBACK_REQUEST_EXECUTED"
        and receipt["next_required_gate"]
        == "CALIBRATED_POSITION_VECTOR_FEEDBACK_REQUEST_EXECUTION_REVIEW"
        and receipt["calibrated_feedback_request_executed"] is True
        and receipt["calibrated_feedback_conversion_accepted"] is True,
        "execution receipt is not review-ready",
    )
    _require(
        receipt["authority"]
        == {
            "controller_opened": True, "camera_opened": False, "commands_sent": 1,
            "motion_commands_sent": 0, "automatic_retries": 0,
            "motion_authorized": False, "physical_authority": False,
        }
        and receipt["motion_authorized"] is False
        and receipt["physical_authority"] is False,
        "execution receipt authority is invalid",
    )
    for name in (
        "controller_binding_sha256", "request_contract_sha256",
        "request_execution_approval_receipt_sha256",
        "execution_prerequisites_sha256", "exchange_evidence_sha256",
        "response_line_sha256",
    ):
        _digest(receipt[name], name)
    _identifier(receipt["attempt_id"], "attempt_id")
    _identifier(receipt["runtime_session_id"], "runtime_session_id")
    _identifier(receipt["operator_id"], "operator_id")
    return receipt


def build_calibrated_position_vector_execution_review_basis(
    working_directory: Path,
    *,
    execution_receipt_document: Mapping[str, Any],
    calibration_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Reproduce the retained execution and return the exact review bindings."""

    working = _working_directory(working_directory)
    receipt = _receipt(execution_receipt_document)
    calibration = dict(calibration_document)
    loaded = load_position_vector_calibration(calibration)

    claim_raw = _read(working / "application-claim.json", 64 * 1024)
    request_raw = _read(working / "supervisor-request.json", 64 * 1024)
    result_raw = _read(working / "supervisor-result.json", 256 * 1024)
    claim = decode_owned_json(claim_raw, maximum=64 * 1024)
    result = decode_owned_json(result_raw, maximum=256 * 1024)
    wire = decode_request(request_raw)
    _exact(claim, _CLAIM_FIELDS, "application claim")
    _require(claim["schema"] == CLAIM_SCHEMA, "application claim schema is invalid")
    _require(
        claim["automatic_retry_allowed"] is False
        and claim["motion_authorized"] is False
        and claim["physical_authority"] is False,
        "application claim authority is invalid",
    )
    verified = verify_exported_journal(result, wire=wire, working_directory=working)
    child = verified["child_result"]
    _require(
        child["status"] == "SUCCEEDED" and child["error"] is None,
        "retained child execution did not succeed",
    )
    application_request = wire["payload"]["binding"]["request"]
    controller_binding = wire["payload"]["binding"]["controller_binding"]
    evidence = child["exchange_evidence"]
    expected = {
        "attempt_id": receipt["attempt_id"],
        "runtime_session_id": receipt["runtime_session_id"],
        "request_execution_approval_receipt_sha256": receipt[
            "request_execution_approval_receipt_sha256"
        ],
        "execution_prerequisites_sha256": receipt["execution_prerequisites_sha256"],
        "request_contract": receipt["request_contract"],
    }
    _require(
        application_request
        == {
            "schema": "rocell.position_vector_calibration_qualified_feedback_request.v1",
            **expected,
        },
        "retained application request differs from the execution receipt",
    )
    _require(
        claim["attempt_id"] == receipt["attempt_id"]
        and claim["runtime_session_id"] == receipt["runtime_session_id"]
        and claim["request_sha256"] == wire["request_sha256"]
        and claim["request_execution_approval_receipt_sha256"]
        == receipt["request_execution_approval_receipt_sha256"]
        and claim["execution_prerequisites_sha256"]
        == receipt["execution_prerequisites_sha256"],
        "application claim differs from the retained execution",
    )
    calibration_sha = canonical_sha256(calibration)
    _require(
        claim["calibration_sha256"] == calibration_sha
        and receipt["calibration_id"] == loaded.calibration_id
        and canonical_sha256(controller_binding)
        == receipt["controller_binding_sha256"],
        "calibration or controller binding differs from the execution",
    )
    _require(
        canonical_sha256(receipt["request_contract"])
        == receipt["request_contract_sha256"]
        and canonical_sha256(evidence) == receipt["exchange_evidence_sha256"],
        "request contract or exchange evidence digest differs",
    )
    response_line = evidence["response_line_utf8"]
    _require(
        hashlib.sha256(response_line.encode("utf-8")).hexdigest()
        == receipt["response_line_sha256"],
        "response line digest differs",
    )
    response = validate_feedback_response_line(
        response_line,
        max_line_bytes=receipt["request_contract"]["maximum_response_line_bytes"],
    )
    reproduced = convert_position_vector_feedback(
        response, calibration, controller_binding
    )
    _require(
        response == receipt["response_message"]
        and reproduced == receipt["calibrated_feedback"],
        "calibrated feedback does not reproduce",
    )
    export_directory = Path(child["journal_export"]["export_directory"])
    manifest_raw = _read(export_directory / "manifest.json", 64 * 1024)
    return {
        "execution_receipt_sha256": canonical_sha256(receipt),
        "application_claim_sha256": hashlib.sha256(claim_raw).hexdigest(),
        "supervisor_request_sha256": hashlib.sha256(request_raw).hexdigest(),
        "supervisor_result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "journal_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "calibration_sha256": calibration_sha,
        "attempt_id": receipt["attempt_id"],
        "runtime_session_id": receipt["runtime_session_id"],
        "operator_id": receipt["operator_id"],
        "executed_at": receipt["executed_at"],
        "calibration_id": receipt["calibration_id"],
        "attachment_profile": receipt["attachment_profile"],
        "calibrated_feedback": dict(reproduced),
    }


def review_calibrated_position_vector_execution(
    working_directory: Path,
    *,
    execution_receipt_document: Mapping[str, Any],
    calibration_document: Mapping[str, Any],
    review_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Accept or reject one independently reproduced retained observation."""

    basis = build_calibrated_position_vector_execution_review_basis(
        working_directory,
        execution_receipt_document=execution_receipt_document,
        calibration_document=calibration_document,
    )
    _require(isinstance(review_document, Mapping), "review must be an object")
    review = dict(review_document)
    _exact(review, _REVIEW_FIELDS, "review")
    _require(review["schema"] == REVIEW_SCHEMA, "review schema is invalid")
    for field in (
        "execution_receipt_sha256", "application_claim_sha256",
        "supervisor_request_sha256", "supervisor_result_sha256",
        "journal_manifest_sha256", "calibration_sha256",
    ):
        _require(review[field] == basis[field], f"review binding mismatch: {field}")
    _digest(review["review_notes_sha256"], "review_notes_sha256")
    reviewer = _identifier(review["reviewer_id"], "reviewer_id")
    _require(reviewer != basis["operator_id"], "reviewer must be independent of operator")
    reviewed_at = _timestamp(review["reviewed_at"], "reviewed_at")
    _require(
        reviewed_at >= _timestamp(basis["executed_at"], "executed_at"),
        "review predates execution",
    )
    decision = review["decision"]
    _require(decision in {"ACCEPT", "REJECT"}, "review decision is invalid")
    accepted = decision == "ACCEPT"
    receipt = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "status": (
            "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_ACCEPTED"
            if accepted
            else "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_REJECTED"
        ),
        "attempt_id": basis["attempt_id"],
        "runtime_session_id": basis["runtime_session_id"],
        "calibration_id": basis["calibration_id"],
        "attachment_profile": basis["attachment_profile"],
        **{field: review[field] for field in (
            "execution_receipt_sha256", "application_claim_sha256",
            "supervisor_request_sha256", "supervisor_result_sha256",
            "journal_manifest_sha256", "calibration_sha256",
        )},
        "review_sha256": canonical_sha256(review),
        "reviewer_id": reviewer,
        "reviewed_at": review["reviewed_at"],
        "decision": decision,
        "calibrated_feedback": basis["calibrated_feedback"] if accepted else None,
        "next_required_gate": (
            "CALIBRATED_POSITION_VECTOR_OBSERVATION_STATE_ADMISSION"
            if accepted
            else "CALIBRATED_POSITION_VECTOR_EXECUTION_REVIEW_REMEDIATION"
        ),
        "limitations": [
            "This receipt reviews one retained calibrated T=1051 observation only.",
            "A separate state-admission gate is required before any downstream state consumer may use an accepted observation.",
            "Review grants no motion, retry, connection, contact, or physical authority.",
        ],
        "calibrated_feedback_observation_accepted": accepted,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "physical_authority": False,
    }
    _exact(receipt, _RECEIPT_FIELDS, "review receipt")
    return receipt


__all__ = [
    "CalibratedPositionVectorExecutionReviewError",
    "REVIEW_RECEIPT_SCHEMA",
    "REVIEW_SCHEMA",
    "build_calibrated_position_vector_execution_review_basis",
    "review_calibrated_position_vector_execution",
]
