"""Build the static-overhead collision qualification work order."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.static_overhead_collision_qualification_work_order_v1 import (
    build_static_overhead_collision_qualification_work_order_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-audit", type=Path, required=True)
    parser.add_argument("--source-audit-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_static_overhead_collision_qualification_work_order_v1(
        args.source_audit,
        args.source_audit_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
