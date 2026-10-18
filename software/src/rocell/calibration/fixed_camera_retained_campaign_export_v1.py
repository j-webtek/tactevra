"""Export one retained fixed-camera campaign for independent review.

This is an offline publication boundary around the manifest compiler. It first
compiles and verifies the complete retained campaign in memory, then reserves a
new output directory and writes the deterministic review packet followed by a
canonical completion receipt. Existing paths are never reused or overwritten.
The module has no camera, robot, serial, motion, contact, or release capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

from .fixed_camera_retained_campaign_manifest_v1 import (
    FixedCameraRetainedCampaignManifestResultV1,
    compile_fixed_camera_retained_campaign_manifest_v1,
)


PACKET_NAME = "fixed-camera-campaign-review.zip"
RECEIPT_NAME = "export-receipt.json"
ZERO_AUTHORITY: Mapping[str, object] = {
    "camera_opened": False,
    "robot_provider_called": False,
    "controller_commands": [],
    "motion_targets_emitted": False,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_release_effect": "NONE",
}


class FixedCameraRetainedCampaignExportError(ValueError):
    """The requested review export cannot be published safely."""


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


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraRetainedCampaignExportError(
            f"cannot publish new export file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraRetainedCampaignExportResultV1:
    """Paths and canonical receipt for one completed offline export."""

    output_directory: Path
    packet_path: Path
    receipt_path: Path
    receipt: Mapping[str, object]
    compiled: FixedCameraRetainedCampaignManifestResultV1


def export_fixed_camera_retained_campaign_v1(
    manifest_path: str | Path,
    *,
    expected_manifest_file_sha256: str,
    output_directory: str | Path,
) -> FixedCameraRetainedCampaignExportResultV1:
    """Compile exact retained evidence and publish a new review-only export."""

    # Complete every expensive and evidence-sensitive check before reserving an
    # output path. A failed compilation therefore leaves no export directory.
    compiled = compile_fixed_camera_retained_campaign_manifest_v1(
        manifest_path,
        expected_file_sha256=expected_manifest_file_sha256,
    )
    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraRetainedCampaignExportError(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraRetainedCampaignExportError(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraRetainedCampaignExportError(
            "output_directory already exists; refusing to overwrite"
        )

    packet = compiled.review_packet.packet_bytes
    packet_hash = _sha256(packet)
    if packet_hash != compiled.review_packet.packet_sha256:
        raise FixedCameraRetainedCampaignExportError(
            "review packet bytes differ from compiled packet_sha256"
        )
    receipt: Mapping[str, object] = {
        "schema": "rocell.fixed_camera_retained_campaign_export_receipt.v1",
        "status": "REVIEW_PACKET_EXPORTED_FOR_INDEPENDENT_REVIEW",
        "source": compiled.receipt(),
        "artifacts": {
            "review_packet": {
                "name": PACKET_NAME,
                "size_bytes": len(packet),
                "sha256": packet_hash,
            },
            "completion_receipt": {
                "name": RECEIPT_NAME,
                "written_last": True,
            },
        },
        "review_packet": compiled.review_packet.to_dict(),
        "independent_review_complete": False,
        "measurement_promoted": False,
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_bytes = _canonical(receipt)

    try:
        destination.mkdir(mode=0o700, exist_ok=False)
    except OSError as exc:
        raise FixedCameraRetainedCampaignExportError(
            f"cannot reserve output_directory: {exc}"
        ) from exc
    packet_path = destination / PACKET_NAME
    receipt_path = destination / RECEIPT_NAME
    try:
        _write_new(packet_path, packet)
        _write_new(receipt_path, receipt_bytes)
    except Exception:
        # Best-effort rollback applies only to files created by this call. If a
        # crash interrupts publication, the absent completion receipt makes the
        # remaining directory fail closed and prevents accidental reuse.
        for path in (receipt_path, packet_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    return FixedCameraRetainedCampaignExportResultV1(
        output_directory=destination,
        packet_path=packet_path,
        receipt_path=receipt_path,
        receipt=receipt,
        compiled=compiled,
    )


__all__ = [
    "PACKET_NAME",
    "RECEIPT_NAME",
    "FixedCameraRetainedCampaignExportError",
    "FixedCameraRetainedCampaignExportResultV1",
    "export_fixed_camera_retained_campaign_v1",
]
