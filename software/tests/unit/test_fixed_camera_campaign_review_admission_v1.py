from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import rocell.calibration.fixed_camera_campaign_review_admission_v1 as subject
from rocell.calibration.fixed_camera_campaign_review_admission_v1 import (
    RECEIPT_NAME,
    REVIEWED_MEASUREMENT_NAME,
    FixedCameraCampaignReviewAdmissionError,
    admit_fixed_camera_campaign_review_v1,
)
from rocell.cli import build_parser, main

from test_fixed_camera_campaign_review_intake_v1 import (
    canonical,
    final_decision,
    packet_and_template,
)


def retain_review_files(
    tmp_path: Path, *, outcome: str = "ACCEPT"
) -> tuple[Path, str, Path, str]:
    packet, template = packet_and_template()
    decision = canonical(final_decision(packet, template, outcome=outcome))
    packet_path = tmp_path / "fixed-camera-campaign-review.zip"
    decision_path = tmp_path / "review-decision.json"
    packet_path.write_bytes(packet)
    decision_path.write_bytes(decision)
    return (
        packet_path,
        hashlib.sha256(packet).hexdigest(),
        decision_path,
        hashlib.sha256(decision).hexdigest(),
    )


def test_acceptance_publishes_measurement_then_canonical_receipt(
    tmp_path: Path,
) -> None:
    packet, packet_hash, decision, decision_hash = retain_review_files(tmp_path)
    output = tmp_path / "admitted"

    result = admit_fixed_camera_campaign_review_v1(
        packet,
        expected_packet_file_sha256=packet_hash,
        decision_path=decision,
        expected_decision_file_sha256=decision_hash,
        output_directory=output,
    )

    assert result.reviewed_measurement_path == output / REVIEWED_MEASUREMENT_NAME
    assert result.reviewed_measurement_path.is_file()
    measurement = json.loads(result.reviewed_measurement_path.read_bytes())
    assert measurement["status"] == ("REVIEWED_INDEPENDENT_BOARD_TO_ROBOT_MEASUREMENTS")
    receipt = json.loads((output / RECEIPT_NAME).read_bytes())
    assert receipt == result.receipt
    assert receipt["measurement_published"] is True
    assert receipt["sources"]["review_packet"]["sha256"] == packet_hash
    assert receipt["sources"]["review_decision"]["sha256"] == decision_hash
    artifact = receipt["artifacts"]["reviewed_measurement"]
    assert (
        artifact["file_sha256"]
        == hashlib.sha256(result.reviewed_measurement_path.read_bytes()).hexdigest()
    )
    assert artifact["meaning_sha256"] == result.intake.reviewed_measurement_sha256
    assert receipt["authority"]["physical_release_effect"] == "NONE"


def test_rejection_publishes_terminal_receipt_without_measurement(
    tmp_path: Path,
) -> None:
    packet, packet_hash, decision, decision_hash = retain_review_files(
        tmp_path, outcome="REJECT"
    )
    output = tmp_path / "rejected"

    result = admit_fixed_camera_campaign_review_v1(
        packet,
        expected_packet_file_sha256=packet_hash,
        decision_path=decision,
        expected_decision_file_sha256=decision_hash,
        output_directory=output,
    )

    assert result.reviewed_measurement_path is None
    assert not (output / REVIEWED_MEASUREMENT_NAME).exists()
    receipt = json.loads((output / RECEIPT_NAME).read_bytes())
    assert receipt["status"] == "EXTERNAL_INDEPENDENT_REVIEW_REJECTED"
    assert receipt["measurement_published"] is False
    assert receipt["artifacts"]["reviewed_measurement"] is None


def test_hash_mismatch_and_existing_output_fail_without_overwrite(
    tmp_path: Path,
) -> None:
    packet, packet_hash, decision, decision_hash = retain_review_files(tmp_path)
    output = tmp_path / "admitted"

    with pytest.raises(
        FixedCameraCampaignReviewAdmissionError, match="differ from expected"
    ):
        admit_fixed_camera_campaign_review_v1(
            packet,
            expected_packet_file_sha256="0" * 64,
            decision_path=decision,
            expected_decision_file_sha256=decision_hash,
            output_directory=output,
        )
    assert not output.exists()

    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(
        FixedCameraCampaignReviewAdmissionError, match="refusing to overwrite"
    ):
        admit_fixed_camera_campaign_review_v1(
            packet,
            expected_packet_file_sha256=packet_hash,
            decision_path=decision,
            expected_decision_file_sha256=decision_hash,
            output_directory=output,
        )
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_cli_registers_and_reports_review_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "out"
    receipt = output / RECEIPT_NAME
    measurement = output / REVIEWED_MEASUREMENT_NAME
    result = SimpleNamespace(
        receipt={
            "schema": "rocell.fixed_camera_campaign_review_admission_receipt.v1",
            "status": "EXTERNAL_INDEPENDENT_REVIEW_ACCEPTED",
            "authority": {"physical_release_effect": "NONE"},
        },
        output_directory=output,
        receipt_path=receipt,
        reviewed_measurement_path=measurement,
    )
    monkeypatch.setattr(
        subject,
        "admit_fixed_camera_campaign_review_v1",
        lambda *_args, **_kwargs: result,
    )
    arguments = (
        "admit-fixed-camera-campaign-review",
        "--review-packet",
        str(tmp_path / "packet.zip"),
        "--review-packet-sha256",
        "a" * 64,
        "--review-decision",
        str(tmp_path / "decision.json"),
        "--review-decision-sha256",
        "b" * 64,
        "--output-directory",
        str(output),
        "--json",
    )
    parsed = build_parser().parse_args(arguments)
    assert parsed.handler.__name__ == "_command_admit_fixed_camera_campaign_review"
    assert main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "EXTERNAL_INDEPENDENT_REVIEW_ACCEPTED"
    assert report["reviewed_measurement_path"] == str(measurement)
