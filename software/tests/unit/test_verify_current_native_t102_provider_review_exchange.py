"""Tests for recipient-side verification of the ARM-166 review exchange."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "software/scripts"
sys.path.insert(0, str(SCRIPTS))

from build_current_native_t102_provider_review_exchange import build  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load(
    "verify_current_native_t102_provider_review_exchange",
    SCRIPTS / "verify_current_native_t102_provider_review_exchange.py",
)


def test_verifies_exact_exchange_without_writing(tmp_path: Path):
    exchange = tmp_path / "exchange"
    built = build(ROOT, exchange)
    before = {path.name: path.read_bytes() for path in exchange.iterdir()}
    result = verifier.verify(exchange)
    after = {path.name: path.read_bytes() for path in exchange.iterdir()}
    assert before == after
    assert result["status"] == "PASS_UNCHANGED_REVIEW_INPUT"
    assert result["exchange_manifest_sha256"] == built[
        "exchange_manifest_sha256"]
    assert result["packet_sha256"] == built["packet_sha256"]
    assert result["packet_manifest_sha256"] == built[
        "packet_manifest_sha256"]
    assert result["packet_member_count"] == 6
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


@pytest.mark.parametrize("name", [
    "REVIEWER_PROCEDURE.md",
    "arm165-current-native-t102-provider-review-packet.zip",
])
def test_rejects_changed_member(tmp_path: Path, name: str):
    exchange = tmp_path / "exchange"
    build(ROOT, exchange)
    with (exchange / name).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(
        verifier.CurrentNativeT102ProviderReviewExchangeError,
        match="member identity",
    ):
        verifier.verify(exchange)


def test_rejects_extra_member(tmp_path: Path):
    exchange = tmp_path / "exchange"
    build(ROOT, exchange)
    (exchange / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(
        verifier.CurrentNativeT102ProviderReviewExchangeError,
        match="membership differs",
    ):
        verifier.verify(exchange)


def test_rejects_directory_symlink(tmp_path: Path):
    target = tmp_path / "target"
    build(ROOT, target)
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(
        verifier.CurrentNativeT102ProviderReviewExchangeError,
        match="non-symlink directory",
    ):
        verifier.verify(linked)


def test_rejects_noncanonical_and_duplicate_manifest(tmp_path: Path):
    exchange = tmp_path / "exchange"
    build(ROOT, exchange)
    manifest_path = exchange / "exchange-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(
        verifier.CurrentNativeT102ProviderReviewExchangeError,
        match="canonical JSON",
    ):
        verifier.verify(exchange)

    duplicate = tmp_path / "duplicate"
    build(ROOT, duplicate)
    duplicate_manifest = duplicate / "exchange-manifest.json"
    duplicate_manifest.write_text(
        '{"schema":"a","schema":"b"}\n', encoding="utf-8")
    with pytest.raises(
        verifier.CurrentNativeT102ProviderReviewExchangeError,
        match="repeats 'schema'",
    ):
        verifier.verify(duplicate)
