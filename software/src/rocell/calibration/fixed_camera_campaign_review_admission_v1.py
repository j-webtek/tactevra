"""Admit one external fixed-camera campaign review from exact retained files.

This offline boundary pins the exported review packet and the independently
authored decision by their exact file hashes, invokes the existing strict
in-memory intake, and publishes its outcome into a new directory.  A reviewed
measurement is written only for an accepted decision.  The canonical receipt
is written last and remains the completion marker for either terminal outcome.
No camera, robot, serial, motion, contact, or release capability is present.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

from .fixed_camera_campaign_review_intake_v1 import (
    ACCEPTED_STATUS,
    MAX_DECISION_BYTES,
    FixedCameraCampaignReviewIntakeResultV1,
    intake_fixed_camera_campaign_review_decision_v1,
)
from .fixed_camera_campaign_review_packet_v1 import MAX_PACKET_BYTES


RECEIPT_NAME = "review-intake-receipt.json"
REVIEWED_MEASUREMENT_NAME = "reviewed-board-to-robot-measurement.json"
ZERO_AUTHORITY: Mapping[str, object] = {
    "camera_opened": False,
    "robot_provider_called": False,
    "controller_commands": [],
    "motion_targets_emitted": False,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_release_effect": "NONE",
}


class FixedCameraCampaignReviewAdmissionError(ValueError):
    """The retained review files cannot be admitted or published safely."""


def _canonical(value: Mapping[str, object]) -> bytes:
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


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraCampaignReviewAdmissionError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _read_pinned(
    path: str | Path,
    *,
    expected_sha256: str,
    maximum_bytes: int,
    label: str,
) -> tuple[Path, bytes]:
    source = Path(path).expanduser()
    expected = _digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraCampaignReviewAdmissionError(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraCampaignReviewAdmissionError(
            f"cannot inspect {label} file: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > maximum_bytes:
        raise FixedCameraCampaignReviewAdmissionError(f"{label} file size is invalid")
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise FixedCameraCampaignReviewAdmissionError(
            f"cannot read {label} file: {exc}"
        ) from exc
    if len(payload) != size:
        raise FixedCameraCampaignReviewAdmissionError(
            f"{label} file changed while being read"
        )
    if _sha256(payload) != expected:
        raise FixedCameraCampaignReviewAdmissionError(
            f"{label} bytes differ from expected file SHA-256"
        )
    return source.resolve(), payload


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraCampaignReviewAdmissionError(
            f"cannot publish new review outcome file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraCampaignReviewAdmissionResultV1:
    """Paths and canonical receipt for one completed review admission."""

    output_directory: Path
    receipt_path: Path
    reviewed_measurement_path: Path | None
    receipt: Mapping[str, object]
    intake: FixedCameraCampaignReviewIntakeResultV1


def admit_fixed_camera_campaign_review_v1(
    packet_path: str | Path,
    *,
    expected_packet_file_sha256: str,
    decision_path: str | Path,
    expected_decision_file_sha256: str,
    output_directory: str | Path,
) -> FixedCameraCampaignReviewAdmissionResultV1:
    """Validate exact review files and publish a terminal zero-authority outcome."""

    packet_source, packet = _read_pinned(
        packet_path,
        expected_sha256=expected_packet_file_sha256,
        maximum_bytes=MAX_PACKET_BYTES,
        label="review packet",
    )
    decision_source, decision = _read_pinned(
        decision_path,
        expected_sha256=expected_decision_file_sha256,
        maximum_bytes=MAX_DECISION_BYTES,
        label="review decision",
    )
    intake = intake_fixed_camera_campaign_review_decision_v1(packet, decision)

    measurement_bytes: bytes | None = None
    measurement_artifact: Mapping[str, object] | None = None
    if intake.status == ACCEPTED_STATUS:
        if intake.reviewed_measurement is None:
            raise FixedCameraCampaignReviewAdmissionError(
                "accepted review did not produce a reviewed measurement"
            )
        measurement_bytes = _canonical(intake.reviewed_measurement)
        measurement_artifact = {
            "name": REVIEWED_MEASUREMENT_NAME,
            "size_bytes": len(measurement_bytes),
            "file_sha256": _sha256(measurement_bytes),
            "meaning_sha256": intake.reviewed_measurement_sha256,
        }
    elif intake.reviewed_measurement is not None:
        raise FixedCameraCampaignReviewAdmissionError(
            "rejected review unexpectedly produced a reviewed measurement"
        )

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraCampaignReviewAdmissionError(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraCampaignReviewAdmissionError(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraCampaignReviewAdmissionError(
            "output_directory already exists; refusing to overwrite"
        )

    receipt: Mapping[str, object] = {
        "schema": "rocell.fixed_camera_campaign_review_admission_receipt.v1",
        "status": intake.status,
        "sources": {
            "review_packet": {
                "name": packet_source.name,
                "size_bytes": len(packet),
                "sha256": _sha256(packet),
            },
            "review_decision": {
                "name": decision_source.name,
                "size_bytes": len(decision),
                "sha256": _sha256(decision),
            },
        },
        "intake": intake.receipt(),
        "artifacts": {
            "reviewed_measurement": measurement_artifact,
            "completion_receipt": {
                "name": RECEIPT_NAME,
                "written_last": True,
            },
        },
        "measurement_published": measurement_bytes is not None,
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_bytes = _canonical(receipt)

    try:
        destination.mkdir(mode=0o700, exist_ok=False)
    except OSError as exc:
        raise FixedCameraCampaignReviewAdmissionError(
            f"cannot reserve output_directory: {exc}"
        ) from exc
    measurement_path = (
        destination / REVIEWED_MEASUREMENT_NAME
        if measurement_bytes is not None
        else None
    )
    receipt_path = destination / RECEIPT_NAME
    try:
        if measurement_path is not None and measurement_bytes is not None:
            _write_new(measurement_path, measurement_bytes)
        _write_new(receipt_path, receipt_bytes)
    except Exception:
        for path in (receipt_path, measurement_path):
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            destination.rmdir()
        except OSError:
            pass
        raise

    return FixedCameraCampaignReviewAdmissionResultV1(
        output_directory=destination,
        receipt_path=receipt_path,
        reviewed_measurement_path=measurement_path,
        receipt=receipt,
        intake=intake,
    )


__all__ = [
    "RECEIPT_NAME",
    "REVIEWED_MEASUREMENT_NAME",
    "FixedCameraCampaignReviewAdmissionError",
    "FixedCameraCampaignReviewAdmissionResultV1",
    "admit_fixed_camera_campaign_review_v1",
]
