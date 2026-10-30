"""Offline tests for the current-provider external review exchange."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from rocell.application.native_t102_current_provider_review_packet_v1 import (
    CANDIDATE_COMMIT,
    inspect_native_t102_current_provider_review_packet_v1,
)


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/scripts"))

from build_current_native_t102_provider_review_exchange import build  # noqa: E402


def test_exchange_is_deterministic_closed_and_authority_free(tmp_path: Path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = build(ROOT, first_dir)
    second = build(ROOT, second_dir)

    assert first["candidate_commit"] == CANDIDATE_COMMIT
    assert first["packet_sha256"] == second["packet_sha256"]
    assert first["packet_manifest_sha256"] == second[
        "packet_manifest_sha256"]
    assert first["exchange_manifest_sha256"] == second[
        "exchange_manifest_sha256"]
    assert sorted(path.name for path in first_dir.iterdir()) == [
        "REVIEWER_PROCEDURE.md",
        "arm165-current-native-t102-provider-review-packet.zip",
        "exchange-manifest.json",
    ]
    for name in (
        "independent_review_complete",
        "transport_implementation_qualified",
        "endpoint_open_authorized",
        "execution_authorized",
        "hardware_access",
        "physical_authority",
    ):
        assert first[name] is False

    packet_path = first_dir / (
        "arm165-current-native-t102-provider-review-packet.zip")
    packet_bytes = packet_path.read_bytes()
    assert hashlib.sha256(packet_bytes).hexdigest() == first["packet_sha256"]
    inspected = inspect_native_t102_current_provider_review_packet_v1(
        packet_bytes)
    assert inspected.packet_sha256 == first["packet_sha256"]
    with zipfile.ZipFile(packet_path) as archive:
        assert archive.read("manifest.json")

    manifest_bytes = (first_dir / "exchange-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest_bytes == (json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ) + "\n").encode()
    assert manifest["external_decision_present"] is False
    procedure = (first_dir / "REVIEWER_PROCEDURE.md").read_text()
    assert first["packet_sha256"] in procedure
    assert "separately authenticated decision" in procedure


def test_exchange_refuses_to_overwrite(tmp_path: Path):
    output = tmp_path / "exchange"
    build(ROOT, output)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build(ROOT, output)
