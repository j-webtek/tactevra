#!/usr/bin/env python3
"""Build the precommitted B0477 physical-intrinsics capture contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.static_intrinsics_multiview_contract import build_static_intrinsics_multiview_contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_static_intrinsics_multiview_contract(args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
