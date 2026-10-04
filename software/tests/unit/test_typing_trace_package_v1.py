from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.typing_trace_journal_v1 import (
    build_typing_trace_journal_v1,
)
from rocell.application.typing_trace_package_v1 import (
    TypingTracePackageV1Error,
    replay_typing_trace_package_v1,
    write_typing_trace_package_v1,
)

import test_typing_trace_journal_v1 as trace_support


CORRELATION = "trace-robot-001"
REQUEST = "request-robot"
WORKSPACE = Path(__file__).resolve().parents[3]


def _package(tmp_path: Path):
    artifacts = trace_support._artifacts()
    journal = build_typing_trace_journal_v1(
        artifacts, correlation_id=CORRELATION, request_id=REQUEST,
        ordered_target_ids=("R", "O", "B", "O", "T"))
    package = write_typing_trace_package_v1(
        tmp_path, journal, artifacts, expected_correlation_id=CORRELATION,
        expected_request_id=REQUEST)
    return package, journal, artifacts


def test_contained_package_replays_identically_without_authority(tmp_path: Path):
    package, _, _ = _package(tmp_path)
    report = replay_typing_trace_package_v1(
        tmp_path, package.name, expected_correlation_id=CORRELATION,
        expected_request_id=REQUEST)
    assert package.parent == tmp_path.resolve()
    assert report["status"] == "IDENTICAL"
    assert report["replay"]["identical"] is True
    assert report["controller_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((
        WORKSPACE / "software/ai/schemas/typing_trace_package_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(manifest)


@pytest.mark.parametrize("fault", ["mutate", "delete", "extra"])
def test_package_rejects_mutation_deletion_and_unexpected_files(tmp_path: Path, fault):
    package, _, _ = _package(tmp_path)
    artifact = package / "artifacts" / "05-ik-screen.json"
    if fault == "mutate":
        artifact.write_bytes(artifact.read_bytes() + b"x")
    elif fault == "delete":
        artifact.unlink()
    else:
        (package / "artifacts" / "unexpected.json").write_text("{}")
    with pytest.raises(TypingTracePackageV1Error):
        replay_typing_trace_package_v1(
            tmp_path, package.name, expected_correlation_id=CORRELATION,
            expected_request_id=REQUEST)


@pytest.mark.parametrize("package_id", ["../escape", "typing-trace-not-a-hash", "C:/x"])
def test_package_id_cannot_escape_evidence_root(tmp_path: Path, package_id):
    with pytest.raises(TypingTracePackageV1Error, match="package_id"):
        replay_typing_trace_package_v1(
            tmp_path, package_id, expected_correlation_id=CORRELATION,
            expected_request_id=REQUEST)


@pytest.mark.parametrize("unsafe", [
    {"password": "not-retained"},
    {"nested": {"serial_port": "COM7"}},
    {"source_path": "C:/Users/example/private.json"},
    {"source_path": "/private/capture.json"},
])
def test_package_creation_rejects_sensitive_fields_and_absolute_paths(
    tmp_path: Path, unsafe,
):
    artifacts = trace_support._artifacts()
    artifacts["REQUEST"] = json.dumps(
        unsafe, sort_keys=True, separators=(",", ":")).encode()
    journal = build_typing_trace_journal_v1(
        artifacts, correlation_id=CORRELATION, request_id=REQUEST,
        ordered_target_ids=("R",))
    with pytest.raises(TypingTracePackageV1Error, match="redaction policy"):
        write_typing_trace_package_v1(
            tmp_path, journal, artifacts, expected_correlation_id=CORRELATION,
            expected_request_id=REQUEST)


def test_noncanonical_or_non_json_artifact_cannot_enter_package(tmp_path: Path):
    artifacts = trace_support._artifacts()
    artifacts["REQUEST"] = b'{ "request": 1 }'
    journal = build_typing_trace_journal_v1(
        artifacts, correlation_id=CORRELATION, request_id=REQUEST,
        ordered_target_ids=("R",))
    with pytest.raises(TypingTracePackageV1Error, match="canonical JSON"):
        write_typing_trace_package_v1(
            tmp_path, journal, artifacts, expected_correlation_id=CORRELATION,
            expected_request_id=REQUEST)
