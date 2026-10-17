"""Create or consume the static-overhead installed-collision evidence packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.static_overhead_collision_profile_intake_v1 import (
    build_static_overhead_collision_profile_v1,
    prepare_static_overhead_measurement_packet_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--measurement-manifest", type=Path)
    parser.add_argument("--measurement-manifest-sha256")
    parser.add_argument("--measurement-manifest-id")
    parser.add_argument("--captured-at-utc")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument("--worksheet-output", type=Path)
    args = parser.parse_args()

    if args.measurement_manifest is None:
        if not args.measurement_manifest_id or not args.captured_at_utc:
            parser.error(
                "pending packet mode requires --measurement-manifest-id and --captured-at-utc"
            )
        report, payload, _, worksheet = prepare_static_overhead_measurement_packet_v1(
            args.workspace,
            measurement_manifest_id=args.measurement_manifest_id,
            captured_at_utc=args.captured_at_utc,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
        if args.worksheet_output is not None:
            args.worksheet_output.parent.mkdir(parents=True, exist_ok=True)
            args.worksheet_output.write_text(
                worksheet,
                encoding="utf-8",
                newline="\n",
            )
        if args.report_output is not None:
            args.report_output.parent.mkdir(parents=True, exist_ok=True)
            args.report_output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    if args.measurement_manifest_sha256 is None:
        parser.error("complete-manifest mode requires --measurement-manifest-sha256")
    result = build_static_overhead_collision_profile_v1(
        args.workspace,
        args.measurement_manifest,
        args.measurement_manifest_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if result.profile_bytes is not None:
        if args.profile_output is None:
            parser.error("a built profile requires --profile-output")
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output.write_bytes(result.profile_bytes)
    return 0 if result.profile_bytes is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
