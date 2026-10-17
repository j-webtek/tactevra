"""Create or fit the installed-base position-correspondence packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rocell.application.installed_base_correspondence_packet_v1 import (
    build_pending_installed_base_correspondence_packet_v1,
    fit_installed_base_position_candidate_v1,
    record_installed_base_correspondence_sample_v1,
)


MAX_EVIDENCE_BYTES = 16_000_000


def _sha256(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"evidence path must be a regular file: {path}")
    if path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise ValueError(f"evidence file exceeds {MAX_EVIDENCE_BYTES} bytes: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path)
    parser.add_argument("--intake-sha256")
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--record-slot")
    parser.add_argument("--packet-id")
    parser.add_argument("--created-at-utc")
    parser.add_argument("--pose-label")
    parser.add_argument("--base-point-xyz-mm", nargs=3, type=float)
    parser.add_argument("--board-point-xyz-mm", nargs=3, type=float)
    parser.add_argument("--controller-feedback-evidence", type=Path)
    parser.add_argument("--base-point-derivation-evidence", type=Path)
    parser.add_argument("--camera-observation-evidence", type=Path)
    parser.add_argument("--board-point-measurement-evidence", type=Path)
    parser.add_argument("--captured-at-utc")
    parser.add_argument("--notes")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.record_slot is not None:
        required = (
            args.packet,
            args.pose_label,
            args.base_point_xyz_mm,
            args.board_point_xyz_mm,
            args.controller_feedback_evidence,
            args.base_point_derivation_evidence,
            args.camera_observation_evidence,
            args.board_point_measurement_evidence,
            args.captured_at_utc,
        )
        if not all(value is not None for value in required):
            parser.error("record mode requires the packet, points, and four evidence files")
        report = record_installed_base_correspondence_sample_v1(
            json.loads(args.packet.read_text(encoding="utf-8")),
            slot_id=args.record_slot,
            pose_label=args.pose_label,
            base_point_xyz_mm=args.base_point_xyz_mm,
            board_point_xyz_mm=args.board_point_xyz_mm,
            controller_feedback_sha256=_sha256(args.controller_feedback_evidence),
            base_point_derivation_sha256=_sha256(
                args.base_point_derivation_evidence
            ),
            camera_observation_sha256=_sha256(args.camera_observation_evidence),
            board_point_measurement_sha256=_sha256(
                args.board_point_measurement_evidence
            ),
            captured_at_utc=args.captured_at_utc,
            notes=args.notes,
        )
        exit_code = 0
    elif args.packet is None:
        if not all(
            (args.intake, args.intake_sha256, args.packet_id, args.created_at_utc)
        ):
            parser.error(
                "pending mode requires intake binding, packet id, and timestamp"
            )
        report = build_pending_installed_base_correspondence_packet_v1(
            args.intake,
            args.intake_sha256,
            packet_id=args.packet_id,
            created_at_utc=args.created_at_utc,
        )
        exit_code = 2
    else:
        report = fit_installed_base_position_candidate_v1(
            json.loads(args.packet.read_text(encoding="utf-8"))
        )
        exit_code = 0 if report["position_diagnostic_pass"] else 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
