"""Offline tests for the refreshed current-provider review packet."""

from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pytest

from rocell.application.native_t102_current_provider_review_packet_v1 import (
    CANDIDATE_COMMIT,
    CANDIDATE_FILES,
    VERIFICATION_SCHEMA,
    NativeT102CurrentProviderReviewPacketError,
    build_native_t102_current_provider_review_packet_v1,
    inspect_native_t102_current_provider_review_packet_v1,
)


ROOT = Path(__file__).resolve().parents[3]


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ) + "\n").encode()


def _members() -> dict[str, bytes]:
    return {path: (ROOT / path).read_bytes() for path in CANDIDATE_FILES}


def _verification(members: dict[str, bytes]) -> bytes:
    import hashlib

    document = {
        "schema": VERIFICATION_SCHEMA,
        "status": "PASS_OFFLINE_NO_HARDWARE",
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_files": [
            {
                "path": path,
                "bytes": len(members[path]),
                "sha256": hashlib.sha256(members[path]).hexdigest(),
            }
            for path in sorted(members)
        ],
        "focused_tests_passed": 40,
        "github_checks_passed": 14,
        "execution_grant_gate_tested": True,
        "fused_composition_tested": True,
        "real_endpoint_opened": False,
        "os_device_handles": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "physical_authority": False,
    }
    return _canonical(document)


def _inputs() -> dict[str, object]:
    members = _members()
    return {
        "candidate_members": members,
        "verification_record": _verification(members),
    }


def test_live_candidate_matches_closed_arm165_identity_and_build_is_deterministic():
    first = build_native_t102_current_provider_review_packet_v1(**_inputs())
    second = build_native_t102_current_provider_review_packet_v1(**_inputs())

    assert first == second
    assert first.packet_bytes == second.packet_bytes
    assert first.candidate_commit == CANDIDATE_COMMIT
    assert first.member_count == len(CANDIDATE_FILES) + 2
    assert inspect_native_t102_current_provider_review_packet_v1(
        first.packet_bytes) == first


def test_packet_retains_review_only_authority_and_current_grant_scope():
    result = build_native_t102_current_provider_review_packet_v1(**_inputs())
    document = result.to_dict()

    assert document["status"] == "AWAITING_EXTERNAL_INDEPENDENT_REVIEW"
    assert document["independent_review_complete"] is False
    assert document["transport_implementation_qualified"] is False
    assert document["endpoint_open_authorized"] is False
    assert document["execution_authorized"] is False
    assert document["hardware_access"] is False
    assert document["physical_authority"] is False
    with zipfile.ZipFile(io.BytesIO(result.packet_bytes)) as archive:
        instructions = archive.read("REVIEW_INSTRUCTIONS.md").decode()
        manifest = json.loads(archive.read("manifest.json"))
    assert "execution grant" in instructions
    assert "fused composition" in instructions
    assert manifest["execution_grant_gate_present"] is True
    assert manifest["transport_implementation_qualified"] is False


def test_changed_provider_or_composition_surface_requires_explicit_refresh():
    values = _inputs()
    members = dict(values["candidate_members"])
    provider = next(iter(CANDIDATE_FILES))
    members[provider] += b"\n# changed\n"
    values["candidate_members"] = members
    values["verification_record"] = _verification(members)

    with pytest.raises(
        NativeT102CurrentProviderReviewPacketError, match="member differs"
    ):
        build_native_t102_current_provider_review_packet_v1(**values)


@pytest.mark.parametrize(("field", "value"), [
    ("independent_review_complete", True),
    ("transport_implementation_qualified", True),
    ("physical_authority", True),
    ("real_endpoint_opened", True),
    ("os_device_handles", 1),
    ("hardware_writes", 1),
])
def test_offline_verification_cannot_promote_physical_claims(field, value):
    values = _inputs()
    verification = json.loads(values["verification_record"])
    verification[field] = value
    values["verification_record"] = _canonical(verification)

    with pytest.raises(
        NativeT102CurrentProviderReviewPacketError,
        match="differs or exceeds",
    ):
        build_native_t102_current_provider_review_packet_v1(**values)


def test_verification_must_be_canonical_and_duplicate_free():
    values = _inputs()
    verification = json.loads(values["verification_record"])
    values["verification_record"] = json.dumps(
        verification, indent=2).encode()
    with pytest.raises(
        NativeT102CurrentProviderReviewPacketError, match="canonical"
    ):
        build_native_t102_current_provider_review_packet_v1(**values)

    values = _inputs()
    values["verification_record"] = (
        b'{"schema":"x","schema":"y"}\n'
    )
    with pytest.raises(
        NativeT102CurrentProviderReviewPacketError, match="repeats"
    ):
        build_native_t102_current_provider_review_packet_v1(**values)


def test_inspector_rejects_added_member_and_tampered_manifest():
    packet = build_native_t102_current_provider_review_packet_v1(
        **_inputs()).packet_bytes
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(packet), "r") as source, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_STORED,
    ) as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr("extra.txt", b"unexpected")
    with pytest.raises(
        NativeT102CurrentProviderReviewPacketError, match="membership"
    ):
        inspect_native_t102_current_provider_review_packet_v1(output.getvalue())

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(packet), "r") as source, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_STORED,
    ) as target:
        for item in source.infolist():
            payload = source.read(item.filename)
            if item.filename == "manifest.json":
                document = json.loads(payload)
                document["execution_authorized"] = True
                payload = _canonical(document)
            target.writestr(item, payload)
    with pytest.raises(
        NativeT102CurrentProviderReviewPacketError, match="manifest differs"
    ):
        inspect_native_t102_current_provider_review_packet_v1(output.getvalue())
