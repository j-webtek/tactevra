"""Emit the retained bare-jaw route-readiness audit without hardware access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from rocell.application.bare_jaw_route_readiness import (
    assess_bare_jaw_route_readiness,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = assess_bare_jaw_route_readiness(args.workspace)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
