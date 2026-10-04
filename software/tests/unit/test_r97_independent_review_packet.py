import io
import json
import zipfile

import pytest

from rocell.application.r97_independent_review_packet import (
    R97IndependentReviewPacketError,
    build_r97_review_packet,
    inspect_r97_review_packet,
)


def _inputs():
    app = b"exact-r97-app"
    import hashlib

    app_sha = hashlib.sha256(app).hexdigest()
    return {
        "sources": {
            "RoArm-M3_example.ino": b"void setup(){}\n",
            "production_runtime_v1.h": b"class ProductionRuntimeV1 {};\n",
        },
        "app_image": app,
        "elf_image": b"exact-r97-elf",
        "compile_report": json.dumps({
            "status": "COMPILED",
            "artifact_hashes": {"RoArm-M3_example.ino.bin": app_sha},
        }).encode(),
        "first_party_report": json.dumps({
            "status": "COMPILED_AWAITING_INDEPENDENT_REVIEW_NOT_INSTALLED",
            "app_sha256": app_sha,
            "compile_export_id": "compile-1",
            "independent_review_complete": False,
            "hardware_access": False,
            "physical_authority": False,
        }).encode(),
    }


def test_packet_is_deterministic_and_review_only():
    first = build_r97_review_packet(**_inputs())
    second = build_r97_review_packet(**_inputs())
    assert first.packet_bytes == second.packet_bytes
    assert first.packet_sha256 == second.packet_sha256
    assert first.member_count == 7
    report = first.to_dict()
    assert report["independent_review_complete"] is False
    assert report["configuration_epoch_bound"] is False
    assert report["physical_authority"] is False
    assert inspect_r97_review_packet(first.packet_bytes).app_sha256 == first.app_sha256


def test_packet_rejects_compile_app_mismatch():
    values = _inputs()
    values["app_image"] = b"different"
    with pytest.raises(R97IndependentReviewPacketError, match="does not bind"):
        build_r97_review_packet(**values)


def test_packet_rejects_first_party_promotion():
    values = _inputs()
    report = json.loads(values["first_party_report"])
    report["independent_review_complete"] = True
    values["first_party_report"] = json.dumps(report).encode()
    with pytest.raises(R97IndependentReviewPacketError, match="blocker"):
        build_r97_review_packet(**values)


def test_inspector_rejects_added_archive_member():
    packet = build_r97_review_packet(**_inputs()).packet_bytes
    source = zipfile.ZipFile(io.BytesIO(packet), "r")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for item in source.infolist():
            archive.writestr(item.filename, source.read(item.filename))
        archive.writestr("unexpected.txt", b"no")
    with pytest.raises(R97IndependentReviewPacketError, match="membership"):
        inspect_r97_review_packet(output.getvalue())


def test_inspector_rejects_tampered_member():
    packet = build_r97_review_packet(**_inputs()).packet_bytes
    source = zipfile.ZipFile(io.BytesIO(packet), "r")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "source/production_runtime_v1.h":
                data += b"tamper"
            archive.writestr(item.filename, data)
    with pytest.raises(R97IndependentReviewPacketError, match="digest"):
        inspect_r97_review_packet(output.getvalue())


def test_inspector_rejects_compressed_expected_members_before_expansion():
    packet = build_r97_review_packet(**_inputs()).packet_bytes
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(packet)) as source, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for item in source.infolist():
            archive.writestr(item.filename, source.read(item.filename))
    with pytest.raises(R97IndependentReviewPacketError, match="format bound"):
        inspect_r97_review_packet(output.getvalue())
