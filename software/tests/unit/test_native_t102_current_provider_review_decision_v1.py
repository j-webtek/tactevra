from dataclasses import replace
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.installed_controller_qualification_v1 import (
    ReviewDisposition,
)
from rocell.application.native_t102_current_provider_review_decision_v1 import (
    PROVIDER_SOURCE_SHA256,
    CANDIDATE_COMMIT,
    EXPECTED_CHECKS,
    MANIFEST_SHA256,
    PACKET_SHA256,
    NativeT102CurrentProviderReviewCheck,
    NativeT102CurrentProviderReviewCheckResultV1,
    NativeT102CurrentProviderReviewDecisionError,
    NativeT102CurrentProviderReviewDecisionV1,
    NativeT102CurrentProviderReviewEvidenceOrigin,
    assess_native_t102_current_provider_review_decision_v1,
    build_synthetic_native_t102_current_provider_review_rehearsal_v1,
    parse_native_t102_current_provider_review_decision_v1,
)


ROOT = Path(__file__).resolve().parents[2]
ASSESSMENT = "2026-09-27T12:45:00Z"


def _checks(*, failed: NativeT102CurrentProviderReviewCheck | None = None):
    return tuple(
        NativeT102CurrentProviderReviewCheckResultV1(
            check=item, passed=item is not failed)
        for item in NativeT102CurrentProviderReviewCheck
    )


def _decision(**changes):
    # Test fixture only. Declaring the external enum does not prove provenance.
    values = {
        "decision_id": "synthetic-arm056-decision",
        "reviewer_id": "synthetic-reviewer",
        "reviewer_affiliation": "test-fixture-only",
        "reviewer_attestation_sha256": "a" * 64,
        "review_started_utc": "2026-09-27T12:00:00Z",
        "review_completed_utc": "2026-09-27T12:30:00Z",
        "decision_valid_until_utc": "2026-10-04T12:30:00Z",
        "reviewed_packet_sha256": PACKET_SHA256,
        "reviewed_manifest_sha256": MANIFEST_SHA256,
        "reviewed_candidate_commit": CANDIDATE_COMMIT,
        "reviewed_provider_source_sha256": PROVIDER_SOURCE_SHA256,
        "evidence_origin": (
            NativeT102CurrentProviderReviewEvidenceOrigin.EXTERNAL_INDEPENDENT),
        "reviewer_independence_asserted": True,
        "reviewer_was_implementation_author": False,
        "checks": _checks(),
        "findings": (),
        "disposition": ReviewDisposition.INDEPENDENTLY_APPROVED,
    }
    values.update(changes)
    return NativeT102CurrentProviderReviewDecisionV1(**values)


def _schema(name):
    return json.loads((ROOT / "ai/schemas" / name).read_text(encoding="utf-8"))


def test_exact_accepted_decision_is_only_ready_for_read_only_intake():
    decision = _decision()
    report = assess_native_t102_current_provider_review_decision_v1(
        decision, assessment_utc=ASSESSMENT)
    assert tuple(item.check.value for item in decision.checks) == EXPECTED_CHECKS
    assert report.status == "INDEPENDENT_REVIEW_ACCEPTED"
    assert report.blockers == ()
    document = report.to_dict()
    assert document["ready_for_read_only_endpoint_qualification_intake"] is True
    assert document["endpoint_open_authorized"] is False
    assert document["controller_start_authorized"] is False
    assert document["execution_authorized"] is False
    assert document["hardware_access"] is False
    assert document["physical_authority"] is False
    jsonschema.Draft202012Validator(_schema(
        "native_t102_current_provider_review_decision_v1.schema.json"
    )).validate(decision.to_dict())
    jsonschema.Draft202012Validator(_schema(
        "native_t102_current_provider_review_decision_report_v1.schema.json"
    )).validate(document)


@pytest.mark.parametrize("field,value,blocker", [
    ("reviewed_packet_sha256", "1" * 64, "PACKET_IDENTITY_MISMATCH"),
    ("reviewed_manifest_sha256", "2" * 64, "MANIFEST_IDENTITY_MISMATCH"),
    ("reviewed_candidate_commit", "3" * 40, "CANDIDATE_COMMIT_MISMATCH"),
    ("reviewed_provider_source_sha256", "4" * 64,
     "PROVIDER_SOURCE_IDENTITY_MISMATCH"),
    ("reviewer_independence_asserted", False, "INDEPENDENCE_NOT_ASSERTED"),
    ("reviewer_was_implementation_author", True,
     "IMPLEMENTATION_AUTHOR_CONFLICT"),
    ("findings", ("open finding",), "APPROVAL_HAS_OPEN_FINDINGS"),
    ("disposition", ReviewDisposition.REJECTED, "DECISION_NOT_APPROVED"),
])
def test_material_review_failures_block(field, value, blocker):
    report = assess_native_t102_current_provider_review_decision_v1(
        _decision(**{field: value}), assessment_utc=ASSESSMENT)
    assert report.status == "BLOCKED"
    assert blocker in report.blockers
    assert report.to_dict()[
        "ready_for_read_only_endpoint_qualification_intake"] is False


def test_failed_check_blocks():
    report = assess_native_t102_current_provider_review_decision_v1(
        _decision(checks=_checks(
            failed=NativeT102CurrentProviderReviewCheck.EXECUTION_GRANT_REQUIRED_BEFORE_OPEN)),
        assessment_utc=ASSESSMENT,
    )
    assert report.blockers == ("CHECKLIST_INCOMPLETE",)


@pytest.mark.parametrize("assessment,blocker", [
    ("2026-09-27T12:29:59Z", "ASSESSMENT_PREDATES_REVIEW"),
    ("2026-10-04T12:30:00Z", "DECISION_EXPIRED"),
    ("2026-10-04T12:30:01Z", "DECISION_EXPIRED"),
])
def test_future_or_expired_decision_blocks(assessment, blocker):
    report = assess_native_t102_current_provider_review_decision_v1(
        _decision(), assessment_utc=assessment)
    assert blocker in report.blockers


def test_synthetic_review_is_quarantined_from_endpoint_intake():
    decision, report = build_synthetic_native_t102_current_provider_review_rehearsal_v1(
        rehearsal_id="arm-056",
        review_started_utc="2026-09-27T12:00:00Z",
        review_completed_utc="2026-09-27T12:30:00Z",
        decision_valid_until_utc="2026-10-04T12:30:00Z",
    )
    assert (decision.evidence_origin is
            NativeT102CurrentProviderReviewEvidenceOrigin.SYNTHETIC_TEST_ONLY)
    assert report.status == "SYNTHETIC_REHEARSAL_ACCEPTED"
    assert report.blockers == ("SYNTHETIC_EVIDENCE_NOT_INDEPENDENT",)
    assert report.to_dict()["synthetic_rehearsal_ready"] is True
    assert report.to_dict()[
        "ready_for_read_only_endpoint_qualification_intake"] is False


@pytest.mark.parametrize("checks", [(), _checks()[:-1], _checks()[::-1]])
def test_checklist_membership_and_order_are_closed(checks):
    with pytest.raises(NativeT102CurrentProviderReviewDecisionError,
                       match="closed checklist"):
        _decision(checks=checks)


@pytest.mark.parametrize("changes,match", [
    ({"review_started_utc": "not-utc"}, "whole-second UTC"),
    ({"review_completed_utc": "2026-09-27T11:59:59Z"}, "predate"),
    ({"decision_valid_until_utc": "2026-09-27T12:30:00Z"},
     "end after"),
])
def test_review_times_are_valid_and_ordered(changes, match):
    with pytest.raises(NativeT102CurrentProviderReviewDecisionError, match=match):
        _decision(**changes)


def test_decision_digest_is_deterministic_and_materially_bound():
    first = _decision()
    assert first.decision_sha256 == _decision().decision_sha256
    assert replace(first, reviewer_attestation_sha256="b" * 64).decision_sha256 != (
        first.decision_sha256)
    assert replace(first, decision_valid_until_utc=(
        "2026-10-05T12:30:00Z")).decision_sha256 != first.decision_sha256


def test_decision_json_round_trip_is_strict_hash_bound_and_non_authorizing():
    original = _decision()
    parsed = parse_native_t102_current_provider_review_decision_v1(original.to_dict())
    assert parsed == original
    for authority_field in (
        "endpoint_open_authorized", "controller_start_authorized",
        "execution_authorized", "physical_authority",
    ):
        promoted = original.to_dict()
        promoted[authority_field] = True
        with pytest.raises(NativeT102CurrentProviderReviewDecisionError,
                           match="must remain false"):
            parse_native_t102_current_provider_review_decision_v1(promoted)
    tampered = original.to_dict()
    tampered["reviewer_affiliation"] = "changed-after-signing"
    with pytest.raises(NativeT102CurrentProviderReviewDecisionError, match="hash"):
        parse_native_t102_current_provider_review_decision_v1(tampered)
    extra = original.to_dict()
    extra["unexpected"] = True
    with pytest.raises(NativeT102CurrentProviderReviewDecisionError,
                       match="closed fields"):
        parse_native_t102_current_provider_review_decision_v1(extra)


def test_assessment_requires_typed_decision():
    with pytest.raises(TypeError, match="NativeT102CurrentProviderReviewDecisionV1"):
        assess_native_t102_current_provider_review_decision_v1(
            {}, assessment_utc=ASSESSMENT)
