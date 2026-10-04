from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

import rocell.application.wizard_diagnostic_export as exports
from rocell.application.wizard_diagnostic_export import (
    WizardDiagnosticExporter,
    WizardDiagnosticExportError,
    verify_export,
    sanitize_diagnostic_record,
)


def test_shared_sanitizer_is_bounded_and_redacts_before_persistence() -> None:
    assert sanitize_diagnostic_record({"API-KEY": "secret"}) == {
        "API-KEY": "[REDACTED]"
    }
    with pytest.raises(WizardDiagnosticExportError):
        sanitize_diagnostic_record({"value": "large"}, maximum_bytes=5)
    with pytest.raises(WizardDiagnosticExportError):
        sanitize_diagnostic_record({}, maximum_bytes=True)


@pytest.mark.parametrize("key", [
    "api_token", "auth_token", "github_token", "id_token",
    "Bearer-Token", "API.Token", "refresh_token",
])
def test_shared_sanitizer_redacts_token_key_variants(key: str) -> None:
    assert sanitize_diagnostic_record({key: "bare-secret-value"}) == {
        key: "[REDACTED]"
    }


def _snapshot() -> dict[str, Any]:
    return {
        "session_id": "rehearsal-001",
        "mode": "REHEARSAL",
        "source_binding_sha256": "a" * 64,
        "source_identity": {"build": "unit-test-fixture"},
        "physical_authority": "NONE",
        "camera": {
            "implementation": "IMPLEMENTED",
            "verification": "INTEGRATION_REHEARSED",
        },
    }


def _prepared(tmp_path: Path) -> WizardDiagnosticExporter:
    exporter = WizardDiagnosticExporter(tmp_path / "assigned-exports")
    exporter.prepare(create=True)
    return exporter


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows directory sharing")
@pytest.mark.parametrize("ancestor", [False, True])
def test_guard_blocks_directory_rename_but_allows_child_publication(
    tmp_path: Path, ancestor: bool
) -> None:
    parent = tmp_path / "assigned-parent"
    leaf = parent / "assigned-leaf"
    leaf.mkdir(parents=True)
    selected = parent if ancestor else leaf
    moved = selected.with_name(selected.name + "-after-release")
    with exports._directory_guard(leaf):
        with pytest.raises(OSError):
            selected.rename(moved)
        assert selected.is_dir() and not moved.exists()
        # The guard must not block normal creation of this operation's files.
        (leaf / "fixture.txt").write_text("retained fixture", encoding="utf-8")
    selected.rename(moved)
    assert moved.is_dir() and not selected.exists()
    retained = (
        moved / "assigned-leaf/fixture.txt" if ancestor else moved / "fixture.txt"
    )
    assert retained.read_text(encoding="utf-8") == "retained fixture"


def test_constructor_has_no_filesystem_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assigned = tmp_path / "not-created"

    def unexpected(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("constructor performed filesystem I/O")

    with monkeypatch.context() as patched:
        for name in ("stat", "resolve", "open", "mkdir"):
            patched.setattr(Path, name, unexpected)
        patched.setattr(os.path, "lexists", unexpected)
        exporter = WizardDiagnosticExporter(assigned)
    assert exporter.export_root == assigned
    assert not assigned.exists()


def test_validate_is_read_only_and_creation_is_explicit(tmp_path: Path) -> None:
    exporter = WizardDiagnosticExporter(tmp_path / "assigned")
    assert exporter.validate()["status"] == "EXPLICIT_CREATION_REQUIRED"
    assert not exporter.export_root.exists()
    with pytest.raises(WizardDiagnosticExportError, match="create=True"):
        exporter.prepare()
    assert not exporter.export_root.exists()
    with pytest.raises(WizardDiagnosticExportError, match="prepare"):
        exporter.export(_snapshot(), [])
    assert exporter.prepare(create=True)["created"] is True
    assert exporter.prepare()["created"] is False
    assert list(exporter.export_root.iterdir()) == []


def test_prepare_never_recursively_creates_missing_parents(tmp_path: Path) -> None:
    exporter = WizardDiagnosticExporter(tmp_path / "missing-parent" / "assigned")
    with pytest.raises(WizardDiagnosticExportError):
        exporter.prepare(create=True)
    assert not (tmp_path / "missing-parent").exists()


@pytest.mark.parametrize(
    "relative",
    ["../escape", "NUL", "COM1.txt", "LPT²", "trailing.", "trailing ", "foo:stream"],
)
def test_unsafe_destination_components_rejected(tmp_path: Path, relative: str) -> None:
    with pytest.raises(WizardDiagnosticExportError):
        WizardDiagnosticExporter(tmp_path / relative)


def test_export_receipt_and_report_have_provenance_and_no_authority(
    tmp_path: Path,
) -> None:
    exporter = _prepared(tmp_path)
    receipt = exporter.export(
        _snapshot(),
        [{"event": "PREVIEW_COMPLETE", "frame_count": 3}],
        attachments={"diagnostic.txt": b"No devices opened.\n"},
    )
    destination = Path(receipt["path"])
    assert destination.parent == exporter.export_root
    assert destination.name.startswith("wizard-")
    assert receipt["physical_authority"] == "NONE"
    assert receipt["provenance"]["source_binding_sha256"] == "a" * 64
    assert receipt["total_bytes"] == sum(item["bytes"] for item in receipt["files"])
    assert receipt["valid"]
    report = json.loads((destination / "report.json").read_text())
    assert report["provenance"]["mode"] == "REHEARSAL"
    assert report["kind"] == "DIAGNOSTIC_ONLY"
    assert report["event_count"] == 1
    assert report["limitations"]
    assert "not authenticate" in (destination / "README.md").read_text()
    verified = verify_export(destination)
    assert verified["valid"]
    assert verified["manifest_sha256"] == receipt["manifest_sha256"]
    assert len(verified["files"]) == 4
    json.dumps(receipt)


def test_exports_are_unique_and_existing_files_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _prepared(tmp_path)
    first = exporter.export(_snapshot(), [])
    second = exporter.export(_snapshot(), [])
    assert first["path"] != second["path"]
    before = (Path(first["path"]) / "manifest.json").read_bytes()
    monkeypatch.setattr(exports, "_new_export_name", lambda: Path(first["path"]).name)
    with pytest.raises(WizardDiagnosticExportError, match="no overwrite"):
        exporter.export({"different": True}, [])
    assert (Path(first["path"]) / "manifest.json").read_bytes() == before
    assert verify_export(Path(first["path"]))["valid"]


def test_manifest_published_last_and_failure_retains_incomplete_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _prepared(tmp_path)
    original = exports._write_new
    writes: list[str] = []

    def fail_final(path: Path, payload: bytes) -> dict[str, Any]:
        writes.append(path.name)
        if path.name == "manifest.json":
            raise OSError("injected unavailable disk")
        return original(path, payload)

    monkeypatch.setattr(exports, "_write_new", fail_final)
    with pytest.raises(WizardDiagnosticExportError, match="no overwrite"):
        exporter.export(_snapshot(), [])
    assert writes == ["README.md", "report.json", "events.jsonl", "manifest.json"]
    remaining = list(exporter.export_root.iterdir())
    assert len(remaining) == 1
    assert (remaining[0] / "report.json").is_file()
    assert not (remaining[0] / "manifest.json").exists()
    assert not verify_export(remaining[0])["valid"]


def test_credentials_redacted_recursively_and_in_text_attachments(
    tmp_path: Path,
) -> None:
    exporter = _prepared(tmp_path)
    snapshot = _snapshot() | {
        "API-Key": "SECRET_ONE",
        "nested": [{"AUTHORIZATION": "SECRET_TWO", "Client.Secret": "SECRET_THREE"}],
        "message": "password=SECRET_FOUR https://alice:SECRET_FIVE@example.test Bearer SECRET_SIX",
    }
    receipt = exporter.export(
        snapshot,
        [{"Access-Token": "SECRET_SEVEN"}],
        attachments={
            "trace.log": (
                b"token=SECRET_EIGHT\napi_key: SECRET_NINE\n"
                b"Authorization: Bearer SECRET_TWELVE\n"
                b"Cookie: session=SECRET_THIRTEEN; another=SECRET_FOURTEEN\n"
                b"authorization = Basic SECRET_FIFTEEN\n"
            ),
            "metadata.json": b'{"Set-Cookie":"SECRET_TEN","value":1}',
            "trace.jsonl": b'{"refresh_token":"SECRET_ELEVEN"}\n',
        },
    )
    text = "\n".join(path.read_text() for path in Path(receipt["path"]).iterdir())
    assert "SECRET_" not in text
    assert "[REDACTED]" in text
    assert snapshot["API-Key"] == "SECRET_ONE"  # Caller state is not mutated.
    assert verify_export(Path(receipt["path"]))["valid"]


@pytest.mark.parametrize(
    "snapshot",
    [
        [],
        {"value": math.nan},
        {"value": math.inf},
        {"value": b"binary"},
        {"value": object()},
        {"value": 2**65},
        {1: "bad-key"},
        {"value": "\x1b[31m"},
    ],
)
def test_bad_snapshot_is_rejected_before_publication(
    tmp_path: Path, snapshot: Any
) -> None:
    exporter = _prepared(tmp_path)
    with pytest.raises(WizardDiagnosticExportError):
        exporter.export(snapshot, [])
    assert list(exporter.export_root.iterdir()) == []


@pytest.mark.parametrize(
    "name,payload",
    [
        ("../outside.log", b"x"),
        ("dir/log.txt", b"x"),
        ("CON.txt", b"x"),
        ("NUL", b"x"),
        ("stream.txt:secret", b"x"),
        ("archive.zip", b"PK"),
        ("camera.png", b"pixels"),
        ("run.exe", b"MZ"),
        ("bad.txt", b"\xff"),
        ("bad.log", b"secret\0value"),
        ("bad.json", b'{"a":1,"a":2}'),
        ("bad.json", b'{"n":NaN}'),
        ("bad.jsonl", b"{}\n\n"),
        ("b" * 76 + ".txt", b"too-long-after-prefix"),
    ],
)
def test_attachment_validation_precedes_directory_publication(
    tmp_path: Path, name: str, payload: bytes
) -> None:
    exporter = _prepared(tmp_path)
    with pytest.raises(WizardDiagnosticExportError):
        exporter.export(_snapshot(), [], attachments={name: payload})
    assert list(exporter.export_root.iterdir()) == []


def test_byte_count_depth_and_attachment_name_collisions_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _prepared(tmp_path)
    with pytest.raises(WizardDiagnosticExportError):
        exporter.export(_snapshot(), [{}] * (exports.MAX_EVENTS + 1))
    with pytest.raises(WizardDiagnosticExportError):
        exporter.export(_snapshot(), [], attachments={"LOG.txt": b"1", "log.txt": b"2"})
    with pytest.raises(WizardDiagnosticExportError):
        exporter.export(
            _snapshot(),
            [],
            attachments={"large.txt": b"x" * (exports.MAX_ATTACHMENT_BYTES + 1)},
        )
    deep: dict[str, Any] = {}
    for _ in range(exports.MAX_DEPTH + 2):
        deep = {"nested": deep}
    with pytest.raises(WizardDiagnosticExportError):
        exporter.export(deep, [])
    monkeypatch.setattr(exports, "MAX_EXPORT_BYTES", 64)
    with pytest.raises(WizardDiagnosticExportError):
        exporter.export(_snapshot(), [])
    assert list(exporter.export_root.iterdir()) == []


@pytest.mark.parametrize(
    "change", ["file", "manifest", "extra", "missing", "partial-manifest"]
)
def test_verifier_rejects_tampered_or_incomplete_export(
    tmp_path: Path, change: str
) -> None:
    receipt = _prepared(tmp_path).export(_snapshot(), [])
    directory = Path(receipt["path"])
    if change == "file":
        (directory / "report.json").write_text("{}")
    elif change == "manifest":
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["complete"] = False
        (directory / "manifest.json").write_text(json.dumps(manifest))
    elif change == "extra":
        (directory / "unlisted.txt").write_text("unexpected")
    elif change == "missing":
        (directory / "events.jsonl").unlink()
    else:
        (directory / "manifest.json").write_text('{"schema":')
    result = verify_export(directory)
    assert not result["valid"]
    assert result["physical_authority"] == "NONE"
    assert result["reasons"]


def test_rehashed_manifest_cannot_escape_folder(tmp_path: Path) -> None:
    receipt = _prepared(tmp_path).export(_snapshot(), [])
    directory = Path(receipt["path"])
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["files"][0]["name"] = "../outside.txt"
    del manifest["manifest_sha256"]
    manifest["manifest_sha256"] = exports._sha256(exports._json_bytes(manifest))
    (directory / "manifest.json").write_bytes(exports._json_bytes(manifest))
    assert not verify_export(directory)["valid"]


def test_changed_root_identity_requires_explicit_rebind(tmp_path: Path) -> None:
    exporter = _prepared(tmp_path)
    exporter.export_root.rename(tmp_path / "old-assigned-exports")
    exporter.export_root.mkdir()
    with pytest.raises(WizardDiagnosticExportError, match="identity changed"):
        exporter.export(_snapshot(), [])
    assert list(exporter.export_root.iterdir()) == []


def test_symlink_root_and_file_are_rejected(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(actual, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host does not grant symlink creation: {exc}")
    with pytest.raises(WizardDiagnosticExportError):
        WizardDiagnosticExporter(linked).prepare()
    receipt = _prepared(tmp_path).export(_snapshot(), [])
    directory = Path(receipt["path"])
    report = directory / "report.json"
    actual_report = actual / "report.json"
    report.rename(actual_report)
    report.symlink_to(actual_report)
    assert not verify_export(directory)["valid"]


def test_hardlinked_export_file_rejected(tmp_path: Path) -> None:
    receipt = _prepared(tmp_path).export(_snapshot(), [])
    directory = Path(receipt["path"])
    os.link(directory / "report.json", tmp_path / "report-link.json")
    assert not verify_export(directory)["valid"]
