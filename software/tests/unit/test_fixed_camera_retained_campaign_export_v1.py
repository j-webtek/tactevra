from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import rocell.calibration.fixed_camera_retained_campaign_export_v1 as subject
from rocell.calibration.fixed_camera_retained_campaign_export_v1 import (
    PACKET_NAME,
    RECEIPT_NAME,
    FixedCameraRetainedCampaignExportError,
    export_fixed_camera_retained_campaign_v1,
)
from rocell.cli import build_parser, main


def compiled(packet: bytes = b"deterministic-review-packet") -> SimpleNamespace:
    packet_hash = hashlib.sha256(packet).hexdigest()
    review_packet = SimpleNamespace(
        packet_bytes=packet,
        packet_sha256=packet_hash,
        to_dict=lambda: {
            "schema": "rocell.fixed_camera_campaign_review_packet_result.v1",
            "packet_sha256": packet_hash,
            "physical_authority": False,
        },
    )
    return SimpleNamespace(
        review_packet=review_packet,
        receipt=lambda: {
            "schema": "rocell.fixed_camera_retained_campaign_manifest_receipt.v1",
            "authority": {"physical_release_effect": "NONE"},
        },
    )


def test_exports_packet_then_canonical_completion_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = compiled()
    observed: dict[str, object] = {}

    def compile_manifest(path: object, *, expected_file_sha256: str) -> object:
        observed["path"] = path
        observed["digest"] = expected_file_sha256
        return value

    monkeypatch.setattr(
        subject, "compile_fixed_camera_retained_campaign_manifest_v1", compile_manifest
    )
    output = tmp_path / "review-export"
    result = export_fixed_camera_retained_campaign_v1(
        tmp_path / "campaign.json",
        expected_manifest_file_sha256="a" * 64,
        output_directory=output,
    )

    assert observed == {
        "path": tmp_path / "campaign.json",
        "digest": "a" * 64,
    }
    assert result.packet_path.read_bytes() == value.review_packet.packet_bytes
    receipt = json.loads(result.receipt_path.read_bytes())
    assert result.packet_path.name == PACKET_NAME
    assert result.receipt_path.name == RECEIPT_NAME
    assert receipt == result.receipt
    assert receipt["status"] == "REVIEW_PACKET_EXPORTED_FOR_INDEPENDENT_REVIEW"
    assert receipt["independent_review_complete"] is False
    assert receipt["measurement_promoted"] is False
    assert receipt["authority"]["physical_release_effect"] == "NONE"


def test_existing_output_is_never_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subject,
        "compile_fixed_camera_retained_campaign_manifest_v1",
        lambda *_args, **_kwargs: compiled(),
    )
    output = tmp_path / "review-export"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(
        FixedCameraRetainedCampaignExportError, match="refusing to overwrite"
    ):
        export_fixed_camera_retained_campaign_v1(
            tmp_path / "campaign.json",
            expected_manifest_file_sha256="a" * 64,
            output_directory=output,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_packet_hash_mismatch_leaves_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = compiled()
    value.review_packet.packet_sha256 = "0" * 64
    monkeypatch.setattr(
        subject,
        "compile_fixed_camera_retained_campaign_manifest_v1",
        lambda *_args, **_kwargs: value,
    )
    output = tmp_path / "review-export"

    with pytest.raises(FixedCameraRetainedCampaignExportError, match="bytes differ"):
        export_fixed_camera_retained_campaign_v1(
            tmp_path / "campaign.json",
            expected_manifest_file_sha256="a" * 64,
            output_directory=output,
        )

    assert not output.exists()


def test_cli_registers_and_reports_offline_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import rocell.calibration.fixed_camera_retained_campaign_export_v1 as export_module

    packet = tmp_path / "out" / PACKET_NAME
    receipt = tmp_path / "out" / RECEIPT_NAME
    result = SimpleNamespace(
        receipt={
            "schema": "rocell.fixed_camera_retained_campaign_export_receipt.v1",
            "status": "REVIEW_PACKET_EXPORTED_FOR_INDEPENDENT_REVIEW",
            "authority": {"physical_release_effect": "NONE"},
        },
        output_directory=tmp_path / "out",
        packet_path=packet,
        receipt_path=receipt,
    )
    monkeypatch.setattr(
        export_module,
        "export_fixed_camera_retained_campaign_v1",
        lambda *_args, **_kwargs: result,
    )
    parsed = build_parser().parse_args(
        (
            "export-fixed-camera-retained-campaign",
            "--campaign-manifest",
            str(tmp_path / "campaign.json"),
            "--campaign-manifest-sha256",
            "a" * 64,
            "--output-directory",
            str(tmp_path / "out"),
            "--json",
        )
    )
    assert parsed.handler.__name__ == "_command_export_fixed_camera_retained_campaign"

    assert (
        main(
            (
                "export-fixed-camera-retained-campaign",
                "--campaign-manifest",
                str(tmp_path / "campaign.json"),
                "--campaign-manifest-sha256",
                "a" * 64,
                "--output-directory",
                str(tmp_path / "out"),
                "--json",
            )
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "REVIEW_PACKET_EXPORTED_FOR_INDEPENDENT_REVIEW"
    assert report["review_packet_path"] == str(packet)
