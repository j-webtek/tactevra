"""Intake one external decision for an exact fixed-camera campaign packet.

The caller supplies separately authored canonical decision bytes.  This module
validates their identity, packet bindings, independence, and installation
attestations.  Acceptance may produce the reviewed board-to-robot measurement
document already required by localization; neither outcome opens hardware,
emits commands, or grants motion, contact, or physical-release authority.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
from typing import Any, Mapping
import zipfile

from .fixed_camera_campaign_review_packet_v1 import (
    FixedCameraCampaignReviewPacketError,
    inspect_fixed_camera_campaign_review_packet_v1,
)


SCHEMA = "rocell.fixed_camera_campaign_review_decision.v1"
FINAL_STATUS = "FINAL_EXTERNAL_INDEPENDENT_REVIEW_DECISION"
ACCEPTED_STATUS = "EXTERNAL_INDEPENDENT_REVIEW_ACCEPTED"
REJECTED_STATUS = "EXTERNAL_INDEPENDENT_REVIEW_REJECTED"
REVIEWED_MEASUREMENT_STATUS = (
    "REVIEWED_INDEPENDENT_BOARD_TO_ROBOT_MEASUREMENTS"
)
MAX_DECISION_BYTES = 32 * 1024
MAX_FINDINGS = 64
MAX_FINDING_CHARACTERS = 1024

_DECISION_FIELDS = {
    "schema",
    "status",
    "review_packet_sha256",
    "campaign_result_sha256",
    "measurement_draft_sha256",
    "campaign_receipt_sha256",
    "producer_id",
    "reviewer_id",
    "decision",
    "reviewed_at",
    "installation_unchanged",
    "reseat_check_passed",
    "findings",
    "physical_authority",
}


class FixedCameraCampaignReviewIntakeError(ValueError):
    """The external decision is malformed, crossed, or over-authoritative."""


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraCampaignReviewIntakeError(
            "review decision is not canonical JSON"
        ) from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _meaning_sha256(value: object) -> str:
    return _sha256(_canonical(value).rstrip(b"\n"))


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FixedCameraCampaignReviewIntakeError(
            f"{label} must be nonempty text"
        )
    return value.strip()


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraCampaignReviewIntakeError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _strict_json(payload: bytes, label: str) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise FixedCameraCampaignReviewIntakeError(
                    f"{label} contains duplicate field {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                FixedCameraCampaignReviewIntakeError(
                    f"{label} contains non-finite value {item}"
                )
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FixedCameraCampaignReviewIntakeError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise FixedCameraCampaignReviewIntakeError(f"{label} must be an object")
    return value


def _review_time(value: object) -> str:
    reviewed_at = _text(value, "reviewed_at")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixedCameraCampaignReviewIntakeError(
            "reviewed_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise FixedCameraCampaignReviewIntakeError(
            "reviewed_at must include a UTC offset"
        )
    return reviewed_at


def _packet_members(packet: bytes) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(packet), "r") as archive:
            template = _strict_json(
                archive.read("review-decision-template.json"),
                "review decision template",
            )
            measurement = _strict_json(
                archive.read("evidence/measurement-draft.json"),
                "measurement draft",
            )
    except (KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        raise FixedCameraCampaignReviewIntakeError(
            "review packet members cannot be read"
        ) from exc
    return template, measurement


def _validate_findings(value: object, *, accepted: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_FINDINGS:
        raise FixedCameraCampaignReviewIntakeError(
            "findings must be a bounded array"
        )
    findings: list[str] = []
    for index, finding in enumerate(value):
        text = _text(finding, f"findings[{index}]")
        if len(text) > MAX_FINDING_CHARACTERS:
            raise FixedCameraCampaignReviewIntakeError(
                f"findings[{index}] exceeds the character bound"
            )
        findings.append(text)
    if not accepted and not findings:
        raise FixedCameraCampaignReviewIntakeError(
            "a rejected decision must retain at least one finding"
        )
    return tuple(findings)


@dataclass(frozen=True, slots=True)
class FixedCameraCampaignReviewIntakeResultV1:
    status: str
    packet_sha256: str
    decision_sha256: str
    campaign_result_sha256: str
    measurement_draft_sha256: str
    producer_id: str
    reviewer_id: str
    decision: str
    reviewed_at: str
    findings: tuple[str, ...]
    reviewed_measurement: dict[str, Any] | None
    reviewed_measurement_sha256: str | None

    def receipt(self) -> dict[str, object]:
        """Return the zero-authority immutable outcome binding."""

        return {
            "schema": "rocell.fixed_camera_campaign_review_intake_receipt.v1",
            "status": self.status,
            "review_packet_sha256": self.packet_sha256,
            "review_decision_sha256": self.decision_sha256,
            "campaign_result_sha256": self.campaign_result_sha256,
            "measurement_draft_sha256": self.measurement_draft_sha256,
            "producer_id": self.producer_id,
            "reviewer_id": self.reviewer_id,
            "decision": self.decision,
            "reviewed_at": self.reviewed_at,
            "findings": list(self.findings),
            "reviewed_measurement_sha256": self.reviewed_measurement_sha256,
            "measurement_eligible_for_localization": self.decision == "ACCEPT",
            "hardware_access": False,
            "controller_commands": [],
            "motion_targets_emitted": False,
            "motion_authorized": False,
            "contact_authorized": False,
            "physical_release_effect": "NONE",
        }


def intake_fixed_camera_campaign_review_decision_v1(
    packet: bytes,
    decision_bytes: bytes,
) -> FixedCameraCampaignReviewIntakeResultV1:
    """Validate a separate external decision and return its bounded outcome."""

    try:
        packet_result = inspect_fixed_camera_campaign_review_packet_v1(packet)
    except FixedCameraCampaignReviewPacketError as exc:
        raise FixedCameraCampaignReviewIntakeError(
            "review packet failed inspection"
        ) from exc
    if (
        not isinstance(decision_bytes, bytes)
        or not decision_bytes
        or len(decision_bytes) > MAX_DECISION_BYTES
    ):
        raise FixedCameraCampaignReviewIntakeError(
            "review decision size is invalid"
        )
    decision = _strict_json(decision_bytes, "review decision")
    if decision_bytes != _canonical(decision):
        raise FixedCameraCampaignReviewIntakeError(
            "review decision must use exact canonical JSON bytes"
        )
    if set(decision) != _DECISION_FIELDS:
        raise FixedCameraCampaignReviewIntakeError(
            "review decision fields differ"
        )
    if decision.get("schema") != SCHEMA or decision.get("status") != FINAL_STATUS:
        raise FixedCameraCampaignReviewIntakeError(
            "review decision meaning differs"
        )

    template, measurement = _packet_members(packet)
    packet_sha256 = _sha256(packet)
    if _digest(
        decision.get("review_packet_sha256"), "review_packet_sha256"
    ) != packet_sha256:
        raise FixedCameraCampaignReviewIntakeError(
            "review decision binds another packet"
        )
    for field in (
        "campaign_result_sha256",
        "measurement_draft_sha256",
        "campaign_receipt_sha256",
        "producer_id",
    ):
        if decision.get(field) != template.get(field):
            raise FixedCameraCampaignReviewIntakeError(
                f"review decision {field} differs from the packet"
            )
    if decision.get("campaign_result_sha256") != packet_result.campaign_result_sha256:
        raise FixedCameraCampaignReviewIntakeError(
            "review decision campaign digest differs"
        )
    if decision.get("measurement_draft_sha256") != (
        packet_result.measurement_draft_sha256
    ):
        raise FixedCameraCampaignReviewIntakeError(
            "review decision measurement digest differs"
        )
    if _meaning_sha256(measurement) != packet_result.measurement_draft_sha256:
        raise FixedCameraCampaignReviewIntakeError(
            "packet measurement draft digest differs"
        )

    producer_id = _text(decision.get("producer_id"), "producer_id")
    reviewer_id = _text(decision.get("reviewer_id"), "reviewer_id")
    if reviewer_id == producer_id:
        raise FixedCameraCampaignReviewIntakeError(
            "independent reviewer must differ from the campaign producer"
        )
    reviewed_at = _review_time(decision.get("reviewed_at"))
    outcome = decision.get("decision")
    if outcome not in {"ACCEPT", "REJECT"}:
        raise FixedCameraCampaignReviewIntakeError(
            "decision must be ACCEPT or REJECT"
        )
    accepted = outcome == "ACCEPT"
    for field in ("installation_unchanged", "reseat_check_passed"):
        if type(decision.get(field)) is not bool:
            raise FixedCameraCampaignReviewIntakeError(
                f"{field} must be boolean"
            )
    if accepted and (
        decision.get("installation_unchanged") is not True
        or decision.get("reseat_check_passed") is not True
    ):
        raise FixedCameraCampaignReviewIntakeError(
            "accepted review requires installation continuity and reseat checks"
        )
    if decision.get("physical_authority") is not False:
        raise FixedCameraCampaignReviewIntakeError(
            "review decision physical_authority must remain false"
        )
    findings = _validate_findings(decision.get("findings"), accepted=accepted)

    reviewed_measurement: dict[str, Any] | None = None
    reviewed_measurement_sha256: str | None = None
    if accepted:
        reviewed_measurement = deepcopy(dict(measurement))
        reviewed_measurement["status"] = REVIEWED_MEASUREMENT_STATUS
        installation = reviewed_measurement.get("installation")
        review = reviewed_measurement.get("review")
        if not isinstance(installation, dict) or not isinstance(review, dict):
            raise FixedCameraCampaignReviewIntakeError(
                "measurement draft review structure differs"
            )
        installation["installation_unchanged"] = True
        installation["reseat_check_passed"] = True
        review["reviewed"] = True
        review["reviewer"] = reviewer_id
        review["reviewed_at"] = reviewed_at
        review["notes"] = (
            f"External decision {_sha256(decision_bytes)}; "
            + ("; ".join(findings) if findings else "no findings recorded")
        )
        reviewed_measurement_sha256 = _meaning_sha256(reviewed_measurement)

    return FixedCameraCampaignReviewIntakeResultV1(
        status=ACCEPTED_STATUS if accepted else REJECTED_STATUS,
        packet_sha256=packet_sha256,
        decision_sha256=_sha256(decision_bytes),
        campaign_result_sha256=packet_result.campaign_result_sha256,
        measurement_draft_sha256=packet_result.measurement_draft_sha256,
        producer_id=producer_id,
        reviewer_id=reviewer_id,
        decision=outcome,
        reviewed_at=reviewed_at,
        findings=findings,
        reviewed_measurement=reviewed_measurement,
        reviewed_measurement_sha256=reviewed_measurement_sha256,
    )


__all__ = [
    "ACCEPTED_STATUS",
    "FINAL_STATUS",
    "MAX_DECISION_BYTES",
    "REJECTED_STATUS",
    "REVIEWED_MEASUREMENT_STATUS",
    "SCHEMA",
    "FixedCameraCampaignReviewIntakeError",
    "FixedCameraCampaignReviewIntakeResultV1",
    "intake_fixed_camera_campaign_review_decision_v1",
]
