"""Generate the zero-authority installed base-transform evidence intake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.installed_base_transform_intake_v1 import (
    build_installed_base_transform_intake_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--intake-id", required=True)
    parser.add_argument("--captured-at-utc", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_installed_base_transform_intake_v1(
        args.workspace,
        intake_id=args.intake_id,
        captured_at_utc=args.captured_at_utc,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
