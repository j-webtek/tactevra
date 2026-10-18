from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.calibration.fixed_camera_bracket_evidence_v1 import (
    FixedCameraBracketEvidenceError,
    load_retained_fixed_camera_bracket_evidence_v1,
)
from rocell.kinematics.firmware_reference import forward


def _jpeg(width: int = 4, height: int = 3) -> bytes:
    sof = (
        b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8\xff\xc0" + (len(sof) + 2).to_bytes(2, "big") + sof + b"\xff\xd9"


def _feedback_line() -> str:
    xyz = forward(0.0, 0.0, 0.0, 0.0)[:3]
    return (
        json.dumps(
            {
                "T": 1051,
                "x": xyz[0],
                "y": xyz[1],
                "z": xyz[2],
                "tit": 0.0,
                "b": 0.0,
                "s": 0.0,
                "e": 0.0,
                "t": 0.0,
                "r": 0.0,
                "g": 0.0,
            },
            separators=(",", ":"),
        )
        + "\n"
    )


def _hash(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _record(jpeg: bytes) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "rocell.retained_fixed_camera_acquisition_bracket.v1",
        "status": "RETAINED_READ_ONLY_STATIONARY_BRACKET",
        "jpeg_binding": {
            "jpeg_sha256": hashlib.sha256(jpeg).hexdigest(),
            "byte_count": len(jpeg),
        },
        "bracket": {
            "permit_sha256": "1" * 64,
            "installation_epoch_id": "rc03-static-camera-epoch-1",
            "camera_identity_sha256": "2" * 64,
            "frame": {
                "capture_id": "fit-a",
                "width_px": 4,
                "height_px": 3,
                "source_sequence": 7,
                "source_timestamp_ns": 130,
                "source_clock": "camera-device-clock",
                "host_request_ns": 120,
                "host_first_byte_ns": 140,
                "host_complete_ns": 160,
                "settings_sha256": "3" * 64,
                "timestamp_quality": "host_receipt",
                "freshness_token": "sequence:7",
                "freshness_basis": "source_sequence",
            },
            "robot_feedback": {
                "robot_base_identity": "ROARM-M3-S2-INSTALLED",
                "clock_id": "host-monotonic-ns",
                "pre_timestamp_ns": 100,
                "post_timestamp_ns": 180,
                "pre_feedback_line": _feedback_line(),
                "post_feedback_line": _feedback_line(),
            },
            "quality": {
                "feedback_bracket_ns": 80,
                "maximum_joint_span_rad": 0.0,
                "endpoint_span_mm": 0.0,
                "maximum_reported_fk_error_mm": 0.0,
            },
        },
        "authority": {
            "camera_opened": False,
            "robot_provider_called": False,
            "motion_targets_emitted": False,
            "motion_authorized": False,
            "contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    value["integrity_sha256"] = _hash(value)
    return value


def _write(
    tmp_path: Path, value: dict[str, object], jpeg: bytes | None = None
) -> tuple[Path, Path, str, str]:
    image = _jpeg() if jpeg is None else jpeg
    record_path = tmp_path / "bracket.json"
    jpeg_path = tmp_path / "frame.jpg"
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    record_path.write_bytes(payload)
    jpeg_path.write_bytes(image)
    return (
        record_path,
        jpeg_path,
        hashlib.sha256(payload).hexdigest(),
        hashlib.sha256(image).hexdigest(),
    )


def _load(paths: tuple[Path, Path, str, str]):
    record_path, jpeg_path, record_sha, jpeg_sha = paths
    return load_retained_fixed_camera_bracket_evidence_v1(
        record_path,
        jpeg_path,
        expected_record_file_sha256=record_sha,
        expected_jpeg_file_sha256=jpeg_sha,
    )


def test_loads_exact_jpeg_and_reconstructs_shared_policy_bracket(
    tmp_path: Path,
) -> None:
    jpeg = _jpeg()
    evidence = _load(_write(tmp_path, _record(jpeg), jpeg))

    assert evidence.bracket.frame.jpeg_bytes == jpeg
    assert evidence.bracket.frame.source_sequence == 7
    assert evidence.bracket.frame.freshness_token == "sequence:7"
    assert evidence.bracket.pre_feedback.received_at_ns == 100
    assert evidence.bracket.post_feedback.received_at_ns == 180
    receipt = evidence.receipt()
    assert receipt["status"] == "RETAINED_STATIONARY_BRACKET_ACCEPTED"
    assert receipt["authority"]["motion_authorized"] is False


def test_requires_both_exact_caller_pins(tmp_path: Path) -> None:
    paths = _write(tmp_path, _record(_jpeg()))
    record_path, jpeg_path, record_sha, jpeg_sha = paths
    with pytest.raises(FixedCameraBracketEvidenceError, match="record bytes differ"):
        load_retained_fixed_camera_bracket_evidence_v1(
            record_path,
            jpeg_path,
            expected_record_file_sha256="0" * 64,
            expected_jpeg_file_sha256=jpeg_sha,
        )
    with pytest.raises(FixedCameraBracketEvidenceError, match="JPEG bytes differ"):
        load_retained_fixed_camera_bracket_evidence_v1(
            record_path,
            jpeg_path,
            expected_record_file_sha256=record_sha,
            expected_jpeg_file_sha256="0" * 64,
        )


def test_rejects_jpeg_binding_drift(tmp_path: Path) -> None:
    value = _record(_jpeg())
    value["jpeg_binding"]["jpeg_sha256"] = "9" * 64
    value["integrity_sha256"] = _hash(
        {k: v for k, v in value.items() if k != "integrity_sha256"}
    )
    with pytest.raises(FixedCameraBracketEvidenceError, match="JPEG bytes differ"):
        _load(_write(tmp_path, value))


def test_rejects_structurally_invalid_jpeg_as_bracket_evidence(tmp_path: Path) -> None:
    jpeg = b"not-a-jpeg"
    value = _record(jpeg)
    with pytest.raises(FixedCameraBracketEvidenceError, match="JPEG is invalid"):
        _load(_write(tmp_path, value, jpeg))


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda value: value["bracket"]["quality"].update(
                {"maximum_joint_span_rad": 0.001}
            ),
            "joint span differs",
        ),
        (
            lambda value: value["bracket"]["frame"].update({"host_complete_ns": 181}),
            "do not bracket",
        ),
        (
            lambda value: value["bracket"]["quality"].update(
                {"feedback_bracket_ns": 81}
            ),
            "duration differs",
        ),
    ),
)
def test_rejects_tampered_stationarity_or_timing(
    tmp_path: Path, mutate, message: str
) -> None:
    value = _record(_jpeg())
    mutate(value)
    with pytest.raises(FixedCameraBracketEvidenceError, match=message):
        _load(_write(tmp_path, value))


def test_rejects_authority_substitution(tmp_path: Path) -> None:
    value = _record(_jpeg())
    value["authority"]["motion_authorized"] = True
    with pytest.raises(FixedCameraBracketEvidenceError, match="must be False"):
        _load(_write(tmp_path, value))


def test_rejects_integrity_drift(tmp_path: Path) -> None:
    value = _record(_jpeg())
    value["integrity_sha256"] = "0" * 64
    with pytest.raises(FixedCameraBracketEvidenceError, match="integrity_sha256"):
        _load(_write(tmp_path, value))


def test_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path: Path) -> None:
    jpeg = _jpeg()
    jpeg_path = tmp_path / "frame.jpg"
    jpeg_path.write_bytes(jpeg)
    jpeg_sha = hashlib.sha256(jpeg).hexdigest()

    for payload, message in (
        (b'{"schema":"a","schema":"b"}', "duplicate key"),
        (b'{"schema":NaN}', "nonfinite"),
    ):
        record_path = tmp_path / f"{message}.json"
        record_path.write_bytes(payload)
        with pytest.raises(FixedCameraBracketEvidenceError, match=message):
            load_retained_fixed_camera_bracket_evidence_v1(
                record_path,
                jpeg_path,
                expected_record_file_sha256=hashlib.sha256(payload).hexdigest(),
                expected_jpeg_file_sha256=jpeg_sha,
            )
