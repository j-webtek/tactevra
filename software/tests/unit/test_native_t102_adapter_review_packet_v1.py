"""Review-only packet tests for the exact merged ARM-054 candidate."""

from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pytest

from rocell.application.native_t102_adapter_review_packet_v1 import (
    NativeT102AdapterReviewPacketError,
    build_native_t102_adapter_review_packet_v1,
    inspect_native_t102_adapter_review_packet_v1,
)


ROOT = Path(__file__).resolve().parents[3]


def inputs():
    return {
        "candidate_members": {
            "source/native_t102_serial_transport_v1.py": (
                ROOT / "software/native/review/arm054-candidate/source/"
                "native_t102_serial_transport_v1.py").read_bytes(),
            "tests/test_windows_native_t102_serial_transport_v1.py": (
                ROOT / "software/native/review/arm054-candidate/tests/"
                "test_windows_native_t102_serial_transport_v1.py").read_bytes(),
            "docs/WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md": (
                ROOT / "software/native/review/arm054-candidate/docs/"
                "WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md").read_bytes(),
        },
        "verification_record": (
            ROOT / "software/native/review/arm054-offline-verification.json"
        ).read_bytes(),
    }


def test_exact_candidate_packet_is_deterministic_and_review_only():
    first = build_native_t102_adapter_review_packet_v1(**inputs())
    second = build_native_t102_adapter_review_packet_v1(**inputs())
    assert first.packet_bytes == second.packet_bytes
    assert first.packet_sha256 == second.packet_sha256
    assert first.member_count == 5
    assert first.candidate_commit == "9bd17ac21d7fd00d18f3dd4378b9bea529b5b681"
    report = first.to_dict()
    assert report["independent_review_complete"] is False
    assert report["endpoint_open_authorized"] is False
    assert report["execution_authorized"] is False
    assert report["physical_authority"] is False
    assert inspect_native_t102_adapter_review_packet_v1(
        first.packet_bytes).packet_sha256 == first.packet_sha256


def test_changed_candidate_source_is_rejected_by_retained_verification():
    values = inputs()
    values["candidate_members"] = dict(values["candidate_members"])
    values["candidate_members"][
        "source/native_t102_serial_transport_v1.py"] += b"\n# changed\n"
    with pytest.raises(NativeT102AdapterReviewPacketError, match="exact"):
        build_native_t102_adapter_review_packet_v1(**values)


def test_current_adapter_requires_fresh_offline_verification():
    values = inputs()
    values["candidate_members"] = dict(values["candidate_members"])
    values["candidate_members"]["source/native_t102_serial_transport_v1.py"] = (
        ROOT / "software/src/rocell/providers/windows/"
        "native_t102_serial_transport_v1.py").read_bytes()
    with pytest.raises(NativeT102AdapterReviewPacketError, match="exact"):
        build_native_t102_adapter_review_packet_v1(**values)


@pytest.mark.parametrize("field,value", [
    ("real_endpoint_opened", True),
    ("hardware_writes", 1),
    ("physical_movements", 1),
    ("independent_review_complete", True),
    ("physical_authority", True),
])
def test_verification_cannot_promote_physical_or_review_claims(field, value):
    values = inputs()
    verification = json.loads(values["verification_record"])
    verification[field] = value
    values["verification_record"] = json.dumps(verification).encode()
    with pytest.raises(NativeT102AdapterReviewPacketError, match="exceeds"):
        build_native_t102_adapter_review_packet_v1(**values)


def test_inspector_rejects_added_or_tampered_members():
    packet = build_native_t102_adapter_review_packet_v1(**inputs()).packet_bytes
    source = zipfile.ZipFile(io.BytesIO(packet), "r")
    added = io.BytesIO()
    with zipfile.ZipFile(added, "w") as archive:
        for item in source.infolist():
            archive.writestr(item.filename, source.read(item.filename))
        archive.writestr("unexpected.txt", b"no")
    with pytest.raises(NativeT102AdapterReviewPacketError, match="membership"):
        inspect_native_t102_adapter_review_packet_v1(added.getvalue())

    source = zipfile.ZipFile(io.BytesIO(packet), "r")
    tampered = io.BytesIO()
    with zipfile.ZipFile(tampered, "w") as archive:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.endswith("native_t102_serial_transport_v1.py"):
                data += b"tamper"
            archive.writestr(item.filename, data)
    with pytest.raises(NativeT102AdapterReviewPacketError, match="digest"):
        inspect_native_t102_adapter_review_packet_v1(tampered.getvalue())


def test_inspector_rejects_compressed_expected_members_before_expansion():
    packet = build_native_t102_adapter_review_packet_v1(**inputs()).packet_bytes
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(packet)) as source, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for item in source.infolist():
            archive.writestr(item.filename, source.read(item.filename))
    with pytest.raises(NativeT102AdapterReviewPacketError, match="format bound"):
        inspect_native_t102_adapter_review_packet_v1(output.getvalue())
