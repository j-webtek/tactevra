from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.installed_controller_qualification_v1 import (
    ReviewDisposition,
)
from rocell.application.native_t102_current_provider_review_decision_v1 import (
    CANDIDATE_COMMIT,
    MANIFEST_SHA256,
    PACKET_SHA256,
    PROVIDER_SOURCE_SHA256,
    NativeT102CurrentProviderReviewCheck,
    NativeT102CurrentProviderReviewCheckResultV1,
    NativeT102CurrentProviderReviewDecisionV1,
    NativeT102CurrentProviderReviewEvidenceOrigin,
)
from rocell.application.native_t102_current_provider_read_only_intake_v1 import (
    NativeT102CurrentProviderReadOnlyIntakeError,
    build_native_t102_current_provider_read_only_intake_v1,
    parse_native_t102_current_provider_read_only_intake_v1,
)
from rocell.application.native_t102_production_transport_v1 import (
    PinnedNativeT102EndpointV1,
)


ROOT = Path(__file__).resolve().parents[2]


def decision(**changes):
    values = {
        "decision_id": "external-arm168-fixture",
        "reviewer_id": "external-reviewer",
        "reviewer_affiliation": "external-lab",
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
        "checks": tuple(
            NativeT102CurrentProviderReviewCheckResultV1(check=item, passed=True)
            for item in NativeT102CurrentProviderReviewCheck
        ),
        "findings": (),
        "disposition": ReviewDisposition.INDEPENDENTLY_APPROVED,
    }
    values.update(changes)
    return NativeT102CurrentProviderReviewDecisionV1(**values)


def endpoint(**changes):
    values = {
        "port_name": "COM7",
        "usb_vid": "10C4",
        "usb_pid": "EA60",
        "usb_serial_number": "SYNTHETIC-ARM168",
    }
    values.update(changes)
    return PinnedNativeT102EndpointV1(**values)


def intake(**changes):
    values = {
        "decision": decision(),
        "endpoint": endpoint(),
        "intake_id": "arm168-read-only-fixture",
        "host_id": "synthetic-windows-host",
        "created_utc": "2026-09-27T12:45:00Z",
    }
    values.update(changes)
    return build_native_t102_current_provider_read_only_intake_v1(**values)


def test_intake_binds_current_review_endpoint_and_zero_write_policy():
    result = intake().to_dict()
    assert result["review_decision_sha256"] == decision().decision_sha256
    assert result["endpoint"] == endpoint().to_dict()
    assert result["transport_write_count_limit"] == 0
    assert result["active_request_count_limit"] == 0
    assert result["movement_command_count_limit"] == 0
    assert result["ready_for_separate_read_only_authorization"] is True
    for field in (
        "read_only_endpoint_authorized", "endpoint_open_authorized",
        "controller_start_authorized", "transport_write_authorized",
        "execution_authorized", "hardware_access", "physical_authority",
    ):
        assert result[field] is False


def test_schema_and_strict_round_trip():
    original = intake()
    document = original.to_dict()
    schema = json.loads((
        ROOT / "ai/schemas/native_t102_current_provider_read_only_intake_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    assert parse_native_t102_current_provider_read_only_intake_v1(
        document) == original


@pytest.mark.parametrize("changes", [
    {"evidence_origin": NativeT102CurrentProviderReviewEvidenceOrigin.SYNTHETIC_TEST_ONLY},
    {"disposition": ReviewDisposition.REJECTED},
    {"reviewer_independence_asserted": False},
])
def test_non_independent_or_blocked_decision_cannot_build(changes):
    with pytest.raises(
        NativeT102CurrentProviderReadOnlyIntakeError,
        match="not eligible",
    ):
        intake(decision=decision(**changes))


def test_expired_decision_cannot_build():
    with pytest.raises(
        NativeT102CurrentProviderReadOnlyIntakeError,
        match="not eligible",
    ):
        intake(created_utc="2026-10-04T12:30:00Z")


@pytest.mark.parametrize("field,value", [
    ("transport_write_count_limit", 1),
    ("active_request_count_limit", 1),
    ("automatic_retry_allowed", True),
    ("endpoint_open_authorized", True),
    ("physical_authority", True),
    ("reviewed_candidate_commit", "0" * 40),
])
def test_policy_subject_or_authority_promotion_rejects(field, value):
    document = intake().to_dict()
    document[field] = value
    with pytest.raises(
        NativeT102CurrentProviderReadOnlyIntakeError,
        match="policy, subject, or authority",
    ):
        parse_native_t102_current_provider_read_only_intake_v1(document)


def test_crossed_endpoint_and_content_hash_reject():
    document = intake().to_dict()
    document["endpoint"]["usb_serial_number"] = "CROSSED"
    with pytest.raises(NativeT102CurrentProviderReadOnlyIntakeError):
        parse_native_t102_current_provider_read_only_intake_v1(document)
    document = intake().to_dict()
    document["intake_sha256"] = "0" * 64
    with pytest.raises(
        NativeT102CurrentProviderReadOnlyIntakeError,
        match="content hash",
    ):
        parse_native_t102_current_provider_read_only_intake_v1(document)


def test_module_has_no_hardware_opener_enumerator_or_writer():
    source = (ROOT / "src/rocell/application" /
              "native_t102_current_provider_read_only_intake_v1.py").read_text(
                  encoding="utf-8")
    for prohibited in (
        "import serial", "serial.tools", ".open()", ".write(",
        "list_ports", "comports", "feedback_request(",
    ):
        assert prohibited not in source
