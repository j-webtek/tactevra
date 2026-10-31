"""Tests for the deterministic ARM-166 outer review-transfer archive."""

from __future__ import annotations

import importlib.util
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "software/scripts"
sys.path.insert(0, str(SCRIPTS))

from build_current_native_t102_provider_review_exchange import build as build_exchange  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transfer = _load(
    "build_current_native_t102_provider_review_transfer",
    SCRIPTS / "build_current_native_t102_provider_review_transfer.py",
)


def _built(tmp_path: Path, name: str = "transfer.zip") -> Path:
    exchange = tmp_path / (name + "-exchange")
    build_exchange(ROOT, exchange)
    output = tmp_path / name
    transfer.build(exchange, output)
    return output


def test_transfer_is_deterministic_and_verifies_without_extraction(tmp_path: Path):
    first = _built(tmp_path, "first.zip")
    second = _built(tmp_path, "second.zip")
    assert first.read_bytes() == second.read_bytes()
    before = first.read_bytes()
    result = transfer.verify_transfer(first)
    assert first.read_bytes() == before
    assert result["status"] == "PASS_UNCHANGED_REVIEW_TRANSFER"
    assert result["transfer_sha256"] == transfer.EXPECTED_TRANSFER_SHA256
    with zipfile.ZipFile(first) as archive:
        assert tuple(archive.namelist()) == transfer.ARCHIVE_MEMBERS
    for field in (
        "external_decision_present",
        "independent_review_complete",
        "transport_implementation_qualified",
        "endpoint_open_authorized",
        "execution_authorized",
        "hardware_access",
        "physical_authority",
    ):
        assert result[field] is False


def test_transfer_refuses_overwrite_and_rejects_changed_bytes(tmp_path: Path):
    output = _built(tmp_path)
    exchange = tmp_path / "another-exchange"
    build_exchange(ROOT, exchange)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        transfer.build(exchange, output)
    with output.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(
        transfer.CurrentNativeT102ProviderReviewTransferError,
        match="identity differs",
    ):
        transfer.verify_transfer(output)


def test_builder_refuses_unpinned_output_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    exchange = tmp_path / "exchange"
    build_exchange(ROOT, exchange)
    output = tmp_path / "transfer.zip"
    monkeypatch.setattr(transfer, "EXPECTED_TRANSFER_SHA256", "0" * 64)
    with pytest.raises(
        transfer.CurrentNativeT102ProviderReviewTransferError,
        match="built review transfer identity differs",
    ):
        transfer.build(exchange, output)
    assert not output.exists()


def test_transfer_rejects_symlink(tmp_path: Path):
    target = _built(tmp_path)
    linked = tmp_path / "linked.zip"
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(
        transfer.CurrentNativeT102ProviderReviewTransferError,
        match="non-symlink file",
    ):
        transfer.verify_transfer(linked)


def test_transfer_rejects_path_traversal_after_outer_rebinding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    original = _built(tmp_path)
    changed = BytesIO()
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(
        changed, "w", allowZip64=False,
    ) as target:
        for index, entry in enumerate(source.infolist()):
            name = "../REVIEWER_PROCEDURE.md" if index == 0 else entry.filename
            target.writestr(transfer._entry(name), source.read(entry))
    changed_path = tmp_path / "traversal.zip"
    changed_path.write_bytes(changed.getvalue())
    monkeypatch.setattr(
        transfer,
        "EXPECTED_TRANSFER_SHA256",
        hashlib.sha256(changed.getvalue()).hexdigest(),
    )
    with pytest.raises(
        transfer.CurrentNativeT102ProviderReviewTransferError,
        match="membership or order differs",
    ):
        transfer.verify_transfer(changed_path)
