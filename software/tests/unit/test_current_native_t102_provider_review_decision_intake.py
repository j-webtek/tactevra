import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from rocell.application.installed_controller_qualification_v1 import (
    ReviewDisposition,
)
from rocell.application.native_t102_current_provider_review_decision_v1 import (
    PROVIDER_SOURCE_SHA256,
    CANDIDATE_COMMIT,
    MANIFEST_SHA256,
    PACKET_SHA256,
    NativeT102CurrentProviderReviewCheck,
    NativeT102CurrentProviderReviewCheckResultV1,
    NativeT102CurrentProviderReviewDecisionError,
    NativeT102CurrentProviderReviewDecisionV1,
    NativeT102CurrentProviderReviewEvidenceOrigin,
)


ROOT = Path(__file__).resolve().parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


intake = _load(
    "current_provider_review_intake",
    ROOT / "software/scripts/assess_current_native_t102_provider_review_decision.py",
)


def _decision(**changes):
    values = {
        "decision_id": "external-fixture-decision",
        "reviewer_id": "external-fixture-reviewer",
        "reviewer_affiliation": "external-fixture-affiliation",
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


def _write_decision(path, decision):
    data = (json.dumps(decision.to_dict(), indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(data)
    return data


def test_intake_normalizes_assesses_and_retains_non_authority(tmp_path):
    decision_path = tmp_path / "returned-decision.json"
    raw = _write_decision(decision_path, _decision())
    output = tmp_path / "assessment"
    summary = intake.assess(
        decision_path, output, assessment_utc="2026-09-27T12:45:00Z")
    report = json.loads((
        output / "assessment-report.json").read_text(encoding="utf-8"))
    normalized = json.loads((
        output / "normalized-decision.json").read_text(encoding="utf-8"))
    retained = json.loads((
        output / "intake-summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "INDEPENDENT_REVIEW_ACCEPTED"
    assert summary["input_document_sha256"] == hashlib.sha256(raw).hexdigest()
    assert summary["decision_sha256"] == normalized["decision_sha256"]
    assert summary["report_sha256"] == report["report_sha256"]
    assert retained == {key: value for key, value in summary.items()
                        if key != "output_dir"}
    assert summary["ready_for_read_only_endpoint_qualification_intake"] is True
    for field in (
        "endpoint_open_authorized", "controller_start_authorized",
        "execution_authorized", "hardware_access", "physical_authority",
    ):
        assert summary[field] is False
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        intake.assess(
            decision_path, output, assessment_utc="2026-09-27T12:45:00Z")


def test_blocked_decision_is_retained_but_never_intake_ready(tmp_path):
    decision_path = tmp_path / "rejected.json"
    _write_decision(decision_path, _decision(
        disposition=ReviewDisposition.REJECTED,
        findings=("external reviewer rejected candidate",),
    ))
    summary = intake.assess(
        decision_path, tmp_path / "blocked",
        assessment_utc="2026-09-27T12:45:00Z",
    )
    assert summary["status"] == "BLOCKED"
    assert summary["ready_for_read_only_endpoint_qualification_intake"] is False


def test_intake_rejects_duplicate_fields_oversize_and_symlink(tmp_path):
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(NativeT102CurrentProviderReviewDecisionError, match="duplicate"):
        intake.assess(
            duplicate, tmp_path / "duplicate-out",
            assessment_utc="2026-09-27T12:45:00Z")

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (intake.MAX_DECISION_BYTES + 1))
    with pytest.raises(NativeT102CurrentProviderReviewDecisionError, match="size"):
        intake.assess(
            oversized, tmp_path / "oversized-out",
            assessment_utc="2026-09-27T12:45:00Z")

    target = tmp_path / "target.json"
    _write_decision(target, _decision())
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(NativeT102CurrentProviderReviewDecisionError, match="non-symlink"):
        intake.assess(
            linked, tmp_path / "linked-out",
            assessment_utc="2026-09-27T12:45:00Z")
