"""Create or fit the installed-base position-correspondence packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.installed_base_correspondence_packet_v1 import (
    build_pending_installed_base_correspondence_packet_v1,
    fit_installed_base_position_candidate_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path)
    parser.add_argument("--intake-sha256")
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--packet-id")
    parser.add_argument("--created-at-utc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.packet is None:
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
