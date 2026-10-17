#!/usr/bin/env python3
"""Bind saved current-camera evidence to offline bare-jaw route readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-observation", type=Path, required=True)
    parser.add_argument("--hover-draft", type=Path, required=True)
    parser.add_argument(
        "--route-readiness",
        type=Path,
        default=ROOT / "software/ai/eval/bare_jaw_route_readiness_20261016.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "software/src"))
    from rocell.application.current_bare_jaw_route_intake import (
        build_current_bare_jaw_route_intake,
    )

    report = build_current_bare_jaw_route_intake(
        args.current_observation,
        args.hover_draft,
        args.route_readiness,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "target_id": report["selected_target"]["target_id"],
                "current_center_px": report["selected_target"]["current_center_px"],
                "blockers": report["blockers"],
                "intake_sha256": report["intake_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
