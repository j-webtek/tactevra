from __future__ import annotations

import json
from dataclasses import replace
import importlib.util
from pathlib import Path

import jsonschema
import pytest

from rocell.application.native_t102_current_provider_owner_ai_review_acceptance_v1 import (
    REQUIRED_SOURCE_BLOCKERS,
    NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
    accept_current_provider_internal_ai_review_v1,
    build_current_provider_internal_ai_review_v1,
    parse_current_provider_owner_ai_review_acceptance_v1,
)


ROOT = Path(__file__).resolve().parents[2]


def _load_builder():
    path = ROOT / "scripts/build_arm171_current_provider_owner_ai_acceptance.py"
    spec = importlib.util.spec_from_file_location("arm171_acceptance_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _review():
    return build_current_provider_internal_ai_review_v1(
        review_id="arm-171-current-provider-ai-review",
        review_started_utc="2026-10-31T21:34:00Z",
        review_completed_utc="2026-10-31T21:35:00Z",
        decision_valid_until_utc="2027-01-31T21:35:00Z",
    )


def _accept():
    decision, report = _review()
    return accept_current_provider_internal_ai_review_v1(
        decision,
        report,
        acceptance_id="arm-171-current-provider-owner-ai-acceptance",
        owner_id="project-owner",
        accepted_utc="2026-10-31T21:36:00Z",
    )


def test_owner_accepts_exact_nonindependent_review_without_authority():
    decision, report = _review()
    assert report.status == "BLOCKED"
    assert report.blockers == REQUIRED_SOURCE_BLOCKERS
    assert decision.reviewer_independence_asserted is False
    assert decision.reviewer_was_implementation_author is True

    accepted = _accept()
    document = accepted.to_dict()
    assert document["status"] == "OWNER_ACCEPTED_AI_REVIEW_GOVERNANCE_OVERRIDE"
    assert document["technical_checks_passed"] is True
    assert document["human_review_claimed"] is False
    assert document["external_independence_claimed"] is False
    assert document["owner_governance_override"] is True
    assert document["ready_for_owner_governed_read_only_endpoint_intake"] is True
    for field in (
        "endpoint_open_authorized", "controller_start_authorized",
        "transport_write_authorized", "execution_authorized",
        "hardware_access", "physical_authority",
    ):
        assert document[field] is False

    schema = json.loads((
        ROOT / "ai/schemas" /
        "native_t102_current_provider_owner_ai_review_acceptance_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    assert parse_current_provider_owner_ai_review_acceptance_v1(document) == accepted


def test_parser_rejects_provenance_authority_and_hash_tampering():
    document = _accept().to_dict()
    document["external_independence_claimed"] = True
    with pytest.raises(
        NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
        match="provenance, status, or authority",
    ):
        parse_current_provider_owner_ai_review_acceptance_v1(document)

    document = _accept().to_dict()
    document["accepted_utc"] = "2026-10-31"
    with pytest.raises(
        NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
        match="invalid typed values",
    ):
        parse_current_provider_owner_ai_review_acceptance_v1(document)

    document = _accept().to_dict()
    document["endpoint_open_authorized"] = True
    with pytest.raises(
        NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
        match="provenance, status, or authority",
    ):
        parse_current_provider_owner_ai_review_acceptance_v1(document)

    document = _accept().to_dict()
    document["acceptance_sha256"] = "0" * 64
    with pytest.raises(
        NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
        match="acceptance hash",
    ):
        parse_current_provider_owner_ai_review_acceptance_v1(document)


def test_acceptance_rejects_crossed_or_incomplete_ai_review():
    decision, report = _review()
    changed = replace(decision, findings=("open technical finding",))
    with pytest.raises(
        NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
        match="not the exact passing",
    ):
        accept_current_provider_internal_ai_review_v1(
            changed,
            report,
            acceptance_id="arm-171-current-provider-owner-ai-acceptance",
            owner_id="project-owner",
            accepted_utc="2026-10-31T21:36:00Z",
        )
    with pytest.raises(
        NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
        match="must follow review",
    ):
        accept_current_provider_internal_ai_review_v1(
            decision,
            report,
            acceptance_id="arm-171-current-provider-owner-ai-acceptance",
            owner_id="project-owner",
            accepted_utc="2026-10-31T21:33:00Z",
        )


def test_parser_rejects_extra_field_and_invalid_timestamp():
    document = _accept().to_dict()
    document["extra"] = False
    with pytest.raises(
        NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
        match="exactly the closed fields",
    ):
        parse_current_provider_owner_ai_review_acceptance_v1(document)


def test_builder_matches_retained_record_and_refuses_overwrite(tmp_path):
    builder = _load_builder()
    output = tmp_path / "acceptance.json"
    result = builder.build(output)
    retained = json.loads(output.read_text(encoding="utf-8"))
    expected = json.loads((
        ROOT / "ai/eval/arm171_current_provider_owner_ai_review_acceptance.json"
    ).read_text(encoding="utf-8"))
    assert retained == result == expected
    with pytest.raises(FileExistsError):
        builder.build(output)
