from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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


builder = _load(
    "current_provider_read_only_builder",
    ROOT / "software/scripts/build_current_native_t102_read_only_endpoint_intake.py",
)


def decision(**changes):
    values = {
        "decision_id": "external-arm168-cli-fixture",
        "reviewer_id": "external-reviewer",
        "reviewer_affiliation": "external-lab",
        "reviewer_attestation_sha256": "b" * 64,
        "review_started_utc": "2026-09-27T12:00:00Z",
        "review_completed_utc": "2026-09-27T12:30:00Z",
        "decision_valid_until_utc": "2026-10-04T12:30:00Z",
        "reviewed_packet_sha256": PACKET_SHA256,
        "reviewed_manifest_sha256": MANIFEST_SHA256,
        "reviewed_candidate_commit": CANDIDATE_COMMIT,
        "reviewed_provider_source_sha256": PROVIDER_SOURCE_SHA256,
        "evidence_origin": NativeT102CurrentProviderReviewEvidenceOrigin.EXTERNAL_INDEPENDENT,
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


def invoke(path, output, **changes):
    values = {
        "intake_id": "arm168-cli-fixture",
        "host_id": "synthetic-windows-host",
        "created_utc": "2026-09-27T12:45:00Z",
        "port_name": "COM7",
        "usb_vid": "10C4",
        "usb_pid": "EA60",
        "usb_serial_number": "SYNTHETIC-ARM168-CLI",
    }
    values.update(changes)
    return builder.build(path, output, **values)


def test_builder_retains_exact_non_authorizing_intake(tmp_path):
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(
        json.dumps(decision().to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "intake"
    summary = invoke(decision_path, output)
    intake = json.loads((
        output / "read-only-endpoint-intake.json").read_text(encoding="utf-8"))
    assert summary["intake_sha256"] == intake["intake_sha256"]
    assert summary["endpoint_sha256"] == intake["endpoint_sha256"]
    assert intake["transport_write_count_limit"] == 0
    assert intake["endpoint_open_authorized"] is False
    assert intake["physical_authority"] is False
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        invoke(decision_path, output)


def test_builder_rejects_blocked_and_duplicate_decisions(tmp_path):
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps(decision(
        disposition=ReviewDisposition.REJECTED).to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="not eligible"):
        invoke(blocked, tmp_path / "blocked-output")

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(
        NativeT102CurrentProviderReviewDecisionError,
        match="duplicate",
    ):
        invoke(duplicate, tmp_path / "duplicate-output")
