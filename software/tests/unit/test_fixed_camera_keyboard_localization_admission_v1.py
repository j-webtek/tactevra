from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import rocell.calibration.fixed_camera_keyboard_localization_admission_v1 as subject
from rocell.calibration.fixed_camera_campaign_review_admission_v1 import (
    RECEIPT_NAME as REVIEW_RECEIPT_NAME,
    REVIEWED_MEASUREMENT_NAME,
    ZERO_AUTHORITY as REVIEW_ZERO_AUTHORITY,
)
from rocell.calibration.fixed_camera_campaign_review_intake_v1 import ACCEPTED_STATUS
from rocell.calibration.fixed_camera_keyboard_localization_admission_v1 import (
    ADMITTED_STATUS,
    LOCALIZATION_NAME,
    RECEIPT_NAME,
    FixedCameraKeyboardLocalizationAdmissionError,
    admit_fixed_camera_keyboard_localization_v1,
)
from rocell.cli import build_parser, main

from test_fixed_camera_keyboard_robot_localization_v1 import (
    TARGETS,
    _keyboard_package,
    _measurement,
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _meaning(value: object) -> str:
    return hashlib.sha256(_canonical(value).rstrip(b"\n")).hexdigest()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _retain_inputs(
    tmp_path: Path,
    *,
    measurement_mutation=None,
) -> tuple[dict[str, Path], dict[str, str]]:
    package, _targets = _keyboard_package()
    measurement = _measurement()
    if measurement_mutation is not None:
        measurement_mutation(measurement)

    admitted = tmp_path / "review-admission"
    admitted.mkdir()
    measurement_path = admitted / REVIEWED_MEASUREMENT_NAME
    measurement_bytes = _canonical(measurement)
    measurement_path.write_bytes(measurement_bytes)
    receipt = {
        "schema": "rocell.fixed_camera_campaign_review_admission_receipt.v1",
        "status": ACCEPTED_STATUS,
        "sources": {},
        "intake": {},
        "artifacts": {
            "reviewed_measurement": {
                "name": REVIEWED_MEASUREMENT_NAME,
                "size_bytes": len(measurement_bytes),
                "file_sha256": _sha(measurement_bytes),
                "meaning_sha256": _meaning(measurement),
            },
            "completion_receipt": {
                "name": REVIEW_RECEIPT_NAME,
                "written_last": True,
            },
        },
        "measurement_published": True,
        "authority": dict(REVIEW_ZERO_AUTHORITY),
    }
    receipt_path = admitted / REVIEW_RECEIPT_NAME
    receipt_bytes = _canonical(receipt)
    receipt_path.write_bytes(receipt_bytes)

    package_path = tmp_path / "keyboard-package.json"
    package_bytes = _canonical(package)
    package_path.write_bytes(package_bytes)
    target_path = tmp_path / "target-profile.json"
    target_bytes = TARGETS.read_bytes()
    target_path.write_bytes(target_bytes)
    paths = {
        "receipt": receipt_path,
        "measurement": measurement_path,
        "package": package_path,
        "target": target_path,
    }
    hashes = {
        "receipt": _sha(receipt_bytes),
        "measurement": _sha(measurement_bytes),
        "package": _sha(package_bytes),
        "target": _sha(target_bytes),
    }
    return paths, hashes


def _admit(tmp_path: Path, paths: dict[str, Path], hashes: dict[str, str]):
    return admit_fixed_camera_keyboard_localization_v1(
        paths["receipt"],
        expected_review_admission_receipt_file_sha256=hashes["receipt"],
        reviewed_measurement_path=paths["measurement"],
        expected_reviewed_measurement_file_sha256=hashes["measurement"],
        keyboard_package_path=paths["package"],
        expected_keyboard_package_file_sha256=hashes["package"],
        target_profile_path=paths["target"],
        expected_target_profile_file_sha256=hashes["target"],
        output_directory=tmp_path / "localized",
    )


def test_exact_accepted_review_publishes_both_profiles_and_receipt_last(
    tmp_path: Path,
) -> None:
    paths, hashes = _retain_inputs(tmp_path)
    result = _admit(tmp_path, paths, hashes)

    assert result.localization_path == tmp_path / "localized" / LOCALIZATION_NAME
    assert result.receipt_path == tmp_path / "localized" / RECEIPT_NAME
    localization = json.loads(result.localization_path.read_bytes())
    assert localization["status"] == "ROBOT_FRAME_LOCALIZATION_CANDIDATES_READY"
    assert localization["board_to_robot_transform_verified"] is True
    assert set(localization["profiles"]) == {
        "no_attachment",
        "stylus_attachment",
    }
    assert all(
        len(profile["robot_frame_localization_candidates"]) == 46
        for profile in localization["profiles"].values()
    )
    receipt = json.loads(result.receipt_path.read_bytes())
    assert receipt == result.receipt
    assert receipt["status"] == ADMITTED_STATUS
    assert receipt["profile_separation_preserved"] is True
    assert receipt["artifacts"]["localization"]["profile_candidate_counts"] == {
        "no_attachment": 46,
        "stylus_attachment": 46,
    }
    assert receipt["artifacts"]["completion_receipt"]["written_last"] is True
    assert receipt["authority"]["physical_release_effect"] == "NONE"
    assert receipt["authority"]["trajectory_generated"] is False


def test_crossed_receipt_tampered_input_and_existing_output_fail_closed(
    tmp_path: Path,
) -> None:
    paths, hashes = _retain_inputs(tmp_path)
    crossed = tmp_path / "crossed"
    crossed.mkdir()
    crossed_measurement = crossed / REVIEWED_MEASUREMENT_NAME
    crossed_measurement.write_bytes(paths["measurement"].read_bytes())
    with pytest.raises(
        FixedCameraKeyboardLocalizationAdmissionError,
        match="must share one directory",
    ):
        admit_fixed_camera_keyboard_localization_v1(
            paths["receipt"],
            expected_review_admission_receipt_file_sha256=hashes["receipt"],
            reviewed_measurement_path=crossed_measurement,
            expected_reviewed_measurement_file_sha256=hashes["measurement"],
            keyboard_package_path=paths["package"],
            expected_keyboard_package_file_sha256=hashes["package"],
            target_profile_path=paths["target"],
            expected_target_profile_file_sha256=hashes["target"],
            output_directory=tmp_path / "localized",
        )

    with pytest.raises(
        FixedCameraKeyboardLocalizationAdmissionError,
        match="differ from expected",
    ):
        admit_fixed_camera_keyboard_localization_v1(
            paths["receipt"],
            expected_review_admission_receipt_file_sha256="0" * 64,
            reviewed_measurement_path=paths["measurement"],
            expected_reviewed_measurement_file_sha256=hashes["measurement"],
            keyboard_package_path=paths["package"],
            expected_keyboard_package_file_sha256=hashes["package"],
            target_profile_path=paths["target"],
            expected_target_profile_file_sha256=hashes["target"],
            output_directory=tmp_path / "localized",
        )

    output = tmp_path / "localized"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(
        FixedCameraKeyboardLocalizationAdmissionError,
        match="refusing to overwrite",
    ):
        _admit(tmp_path, paths, hashes)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_failed_holdout_residual_publishes_nothing(tmp_path: Path) -> None:
    def change(measurement: dict) -> None:
        measurement["correspondences"][-1]["robot_xyz_mm"][0] += 8.0

    paths, hashes = _retain_inputs(tmp_path, measurement_mutation=change)
    with pytest.raises(
        FixedCameraKeyboardLocalizationAdmissionError,
        match="residual checks did not pass",
    ):
        _admit(tmp_path, paths, hashes)
    assert not (tmp_path / "localized").exists()


def test_receipt_measurement_binding_is_enforced(tmp_path: Path) -> None:
    paths, hashes = _retain_inputs(tmp_path)
    receipt = json.loads(paths["receipt"].read_bytes())
    changed = copy.deepcopy(receipt)
    changed["artifacts"]["reviewed_measurement"]["meaning_sha256"] = "f" * 64
    changed_bytes = _canonical(changed)
    paths["receipt"].write_bytes(changed_bytes)
    hashes["receipt"] = _sha(changed_bytes)
    with pytest.raises(
        FixedCameraKeyboardLocalizationAdmissionError,
        match="differs from the accepted review artifact",
    ):
        _admit(tmp_path, paths, hashes)


def test_cli_registers_and_reports_localization_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "out"
    localization = output / LOCALIZATION_NAME
    receipt = output / RECEIPT_NAME
    result = SimpleNamespace(
        receipt={
            "schema": "rocell.fixed_camera_keyboard_localization_admission_receipt.v1",
            "status": ADMITTED_STATUS,
            "authority": {"physical_release_effect": "NONE"},
        },
        output_directory=output,
        localization_path=localization,
        receipt_path=receipt,
    )
    monkeypatch.setattr(
        subject,
        "admit_fixed_camera_keyboard_localization_v1",
        lambda *_args, **_kwargs: result,
    )
    arguments = (
        "admit-fixed-camera-keyboard-localization",
        "--review-admission-receipt",
        str(tmp_path / REVIEW_RECEIPT_NAME),
        "--review-admission-receipt-sha256",
        "a" * 64,
        "--reviewed-measurement",
        str(tmp_path / REVIEWED_MEASUREMENT_NAME),
        "--reviewed-measurement-sha256",
        "b" * 64,
        "--keyboard-package",
        str(tmp_path / "keyboard.json"),
        "--keyboard-package-sha256",
        "c" * 64,
        "--target-profile",
        str(tmp_path / "targets.json"),
        "--target-profile-sha256",
        "d" * 64,
        "--output-directory",
        str(output),
        "--json",
    )
    parsed = build_parser().parse_args(arguments)
    assert parsed.handler.__name__ == (
        "_command_admit_fixed_camera_keyboard_localization"
    )
    assert main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == ADMITTED_STATUS
    assert report["localization_path"] == str(localization)
