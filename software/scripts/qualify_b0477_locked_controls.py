#!/usr/bin/env python3
"""Seal external B0477 control and reopen receipts into a compact artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.b0477_locked_controls_qualification import qualify_b0477_locked_controls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = qualify_b0477_locked_controls(args.lock, args.capture, args.observation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
