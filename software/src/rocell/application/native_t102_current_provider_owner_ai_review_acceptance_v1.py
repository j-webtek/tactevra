"""Owner acceptance of the current-provider internal AI technical review.

This is a governance override, not an external-review decision.  It preserves
the synthetic and implementation-author provenance blockers while allowing the
owner to use the exact passing technical review as the prerequisite for a later
owner-governed, read-only endpoint intake.  It grants no endpoint, transport,
execution, hardware, or physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from .installed_controller_qualification_v1 import ReviewDisposition
from .native_t102_current_provider_review_decision_v1 import (
    CANDIDATE_COMMIT,
    MANIFEST_SHA256,
    PACKET_SHA256,
    PROVIDER_SOURCE_SHA256,
    NativeT102CurrentProviderReviewCheck,
    NativeT102CurrentProviderReviewCheckResultV1,
    NativeT102CurrentProviderReviewDecisionReportV1,
    NativeT102CurrentProviderReviewDecisionV1,
    NativeT102CurrentProviderReviewEvidenceOrigin,
    assess_native_t102_current_provider_review_decision_v1,
)


SCHEMA = "rocell.native_t102_current_provider_owner_ai_review_acceptance.v1"
REQUIRED_SOURCE_STATUS = "BLOCKED"
REQUIRED_SOURCE_BLOCKERS = (
    "SYNTHETIC_EVIDENCE_NOT_INDEPENDENT",
    "INDEPENDENCE_NOT_ASSERTED",
    "IMPLEMENTATION_AUTHOR_CONFLICT",
)
GOVERNANCE_CAVEAT = "OWNER_ACCEPTED_NONINDEPENDENT_AI_TECHNICAL_REVIEW"
AI_REVIEWER_ID = "openai-codex-primary-agent"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class NativeT102CurrentProviderOwnerAIReviewAcceptanceError(ValueError):
    """The owner override or its bound AI review is invalid."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "value is not canonical JSON") from exc


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            f"{label} must be a bounded identifier")
    return value


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            f"{label} must be whole-second UTC")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError as exc:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            f"{label} must be valid UTC") from exc


@dataclass(frozen=True, slots=True)
class NativeT102CurrentProviderOwnerAIReviewAcceptanceV1:
    acceptance_id: str
    owner_id: str
    accepted_utc: str
    source_ai_decision_sha256: str
    source_ai_report_sha256: str
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
                "unsupported owner acceptance schema")
        _identifier(self.acceptance_id, "acceptance_id")
        _identifier(self.owner_id, "owner_id")
        _utc(self.accepted_utc, "accepted_utc")
        for name in ("source_ai_decision_sha256", "source_ai_report_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA.fullmatch(value) is None:
                raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
                    f"{name} must be a SHA-256 digest")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": "OWNER_ACCEPTED_AI_REVIEW_GOVERNANCE_OVERRIDE",
            "acceptance_id": self.acceptance_id,
            "owner_id": self.owner_id,
            "accepted_utc": self.accepted_utc,
            "source_ai_decision_sha256": self.source_ai_decision_sha256,
            "source_ai_report_sha256": self.source_ai_report_sha256,
            "source_ai_review_status": REQUIRED_SOURCE_STATUS,
            "source_ai_review_blockers": list(REQUIRED_SOURCE_BLOCKERS),
            "reviewed_packet_sha256": PACKET_SHA256,
            "reviewed_manifest_sha256": MANIFEST_SHA256,
            "reviewed_candidate_commit": CANDIDATE_COMMIT,
            "reviewed_provider_source_sha256": PROVIDER_SOURCE_SHA256,
            "governance_caveat": GOVERNANCE_CAVEAT,
            "technical_checks_passed": True,
            "reviewer_participated_in_implementation_chain": True,
            "human_review_required": False,
            "human_review_claimed": False,
            "external_independence_claimed": False,
            "owner_governance_override": True,
            "ready_for_owner_governed_read_only_endpoint_intake": True,
            "endpoint_open_authorized": False,
            "controller_start_authorized": False,
            "transport_write_authorized": False,
            "execution_authorized": False,
            "hardware_access": False,
            "physical_authority": False,
        }

    @property
    def acceptance_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "acceptance_sha256": self.acceptance_sha256}


def build_current_provider_internal_ai_review_v1(
    *, review_id: str, review_started_utc: str, review_completed_utc: str,
    decision_valid_until_utc: str,
) -> tuple[
    NativeT102CurrentProviderReviewDecisionV1,
    NativeT102CurrentProviderReviewDecisionReportV1,
]:
    """Build the exact non-independent technical review accepted by the owner."""

    _identifier(review_id, "review_id")
    _utc(review_started_utc, "review_started_utc")
    _utc(review_completed_utc, "review_completed_utc")
    _utc(decision_valid_until_utc, "decision_valid_until_utc")
    attestation = hashlib.sha256(_canonical({
        "authority": "INTERNAL_AI_TECHNICAL_REVIEW_ONLY",
        "review_id": review_id,
        "reviewer_id": AI_REVIEWER_ID,
        "reviewed_packet_sha256": PACKET_SHA256,
        "reviewed_manifest_sha256": MANIFEST_SHA256,
        "reviewed_candidate_commit": CANDIDATE_COMMIT,
        "reviewed_provider_source_sha256": PROVIDER_SOURCE_SHA256,
    })).hexdigest()
    decision = NativeT102CurrentProviderReviewDecisionV1(
        decision_id=review_id,
        reviewer_id=AI_REVIEWER_ID,
        reviewer_affiliation="INTERNAL_AI_TECHNICAL_REVIEW",
        reviewer_attestation_sha256=attestation,
        review_started_utc=review_started_utc,
        review_completed_utc=review_completed_utc,
        decision_valid_until_utc=decision_valid_until_utc,
        reviewed_packet_sha256=PACKET_SHA256,
        reviewed_manifest_sha256=MANIFEST_SHA256,
        reviewed_candidate_commit=CANDIDATE_COMMIT,
        reviewed_provider_source_sha256=PROVIDER_SOURCE_SHA256,
        evidence_origin=(
            NativeT102CurrentProviderReviewEvidenceOrigin.SYNTHETIC_TEST_ONLY),
        reviewer_independence_asserted=False,
        reviewer_was_implementation_author=True,
        checks=tuple(
            NativeT102CurrentProviderReviewCheckResultV1(check=item, passed=True)
            for item in NativeT102CurrentProviderReviewCheck
        ),
        findings=(),
        disposition=ReviewDisposition.INDEPENDENTLY_APPROVED,
    )
    report = assess_native_t102_current_provider_review_decision_v1(
        decision, assessment_utc=review_completed_utc)
    if report.status != REQUIRED_SOURCE_STATUS or report.blockers != REQUIRED_SOURCE_BLOCKERS:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "internal AI review escaped its closed provenance boundary")
    return decision, report


def accept_current_provider_internal_ai_review_v1(
    decision: NativeT102CurrentProviderReviewDecisionV1,
    report: NativeT102CurrentProviderReviewDecisionReportV1,
    *, acceptance_id: str, owner_id: str, accepted_utc: str,
) -> NativeT102CurrentProviderOwnerAIReviewAcceptanceV1:
    """Accept one exact technical review without claiming human independence."""

    if not isinstance(decision, NativeT102CurrentProviderReviewDecisionV1):
        raise TypeError("decision must be a current-provider review decision")
    if not isinstance(report, NativeT102CurrentProviderReviewDecisionReportV1):
        raise TypeError("report must be a current-provider review report")
    accepted = _utc(accepted_utc, "accepted_utc")
    completed = _utc(decision.review_completed_utc, "review_completed_utc")
    valid_until = _utc(
        decision.decision_valid_until_utc, "decision_valid_until_utc")
    if accepted < completed or accepted >= valid_until:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "owner acceptance must follow review and precede decision expiry")
    reassessed = assess_native_t102_current_provider_review_decision_v1(
        decision, assessment_utc=report.assessment_utc)
    if (
        reassessed != report
        or report.status != REQUIRED_SOURCE_STATUS
        or report.blockers != REQUIRED_SOURCE_BLOCKERS
        or decision.reviewer_id != AI_REVIEWER_ID
        or decision.evidence_origin is not
        NativeT102CurrentProviderReviewEvidenceOrigin.SYNTHETIC_TEST_ONLY
        or decision.reviewer_independence_asserted is not False
        or decision.reviewer_was_implementation_author is not True
        or not all(item.passed for item in decision.checks)
        or decision.findings
        or decision.reviewed_packet_sha256 != PACKET_SHA256
        or decision.reviewed_manifest_sha256 != MANIFEST_SHA256
        or decision.reviewed_candidate_commit != CANDIDATE_COMMIT
        or decision.reviewed_provider_source_sha256 != PROVIDER_SOURCE_SHA256
    ):
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "AI review is not the exact passing non-independent current-provider review")
    return NativeT102CurrentProviderOwnerAIReviewAcceptanceV1(
        acceptance_id=acceptance_id,
        owner_id=owner_id,
        accepted_utc=accepted_utc,
        source_ai_decision_sha256=decision.decision_sha256,
        source_ai_report_sha256=report.report_sha256,
    )


def parse_current_provider_owner_ai_review_acceptance_v1(
    document: dict[str, Any],
) -> NativeT102CurrentProviderOwnerAIReviewAcceptanceV1:
    """Strictly parse one retained owner acceptance and verify its hash."""

    template = NativeT102CurrentProviderOwnerAIReviewAcceptanceV1(
        acceptance_id="field-template", owner_id="field-template",
        accepted_utc="2000-01-01T00:00:00Z",
        source_ai_decision_sha256="0" * 64,
        source_ai_report_sha256="0" * 64,
    ).to_dict()
    if type(document) is not dict or set(document) != set(template):
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "owner acceptance must contain exactly the closed fields")
    constants = {
        key: value for key, value in template.items()
        if key not in {
            "acceptance_id", "owner_id", "accepted_utc",
            "source_ai_decision_sha256", "source_ai_report_sha256",
            "acceptance_sha256",
        }
    }
    if any(document.get(key) != value for key, value in constants.items()):
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "owner acceptance provenance, status, or authority differs")
    try:
        parsed = NativeT102CurrentProviderOwnerAIReviewAcceptanceV1(
            acceptance_id=document["acceptance_id"],
            owner_id=document["owner_id"],
            accepted_utc=document["accepted_utc"],
            source_ai_decision_sha256=document["source_ai_decision_sha256"],
            source_ai_report_sha256=document["source_ai_report_sha256"],
            schema=document["schema"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "owner acceptance contains invalid typed values") from exc
    if document["acceptance_sha256"] != parsed.acceptance_sha256:
        raise NativeT102CurrentProviderOwnerAIReviewAcceptanceError(
            "owner acceptance hash differs")
    return parsed


__all__ = [
    "AI_REVIEWER_ID", "GOVERNANCE_CAVEAT", "REQUIRED_SOURCE_BLOCKERS",
    "REQUIRED_SOURCE_STATUS", "SCHEMA",
    "NativeT102CurrentProviderOwnerAIReviewAcceptanceError",
    "NativeT102CurrentProviderOwnerAIReviewAcceptanceV1",
    "accept_current_provider_internal_ai_review_v1",
    "build_current_provider_internal_ai_review_v1",
    "parse_current_provider_owner_ai_review_acceptance_v1",
]
