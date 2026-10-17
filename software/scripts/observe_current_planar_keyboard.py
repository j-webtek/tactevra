#!/usr/bin/env python3
"""Project retained keyboard targets into a current saved camera frame."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-directory", type=Path, required=True)
    parser.add_argument("--stationary-observation", type=Path, required=True)
    parser.add_argument(
        "--registration",
        type=Path,
        default=ROOT / "software/ai/eval/b0477_fixed_board_registration_20261016.json",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        default=ROOT / "software/ai/eval/b0477_keyboard_overlay_20261016.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", type=Path)
    parser.add_argument("--created-at")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "software/src"))
    from rocell.application.current_planar_keyboard_observation import (
        build_current_planar_observation,
        render_current_overlay,
    )

    report = build_current_planar_observation(
        ROOT,
        args.frames_directory,
        args.stationary_observation,
        args.registration,
        args.overlay,
        created_at=args.created_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.render:
        render_current_overlay(report, args.render, workspace=ROOT)
    print(
        json.dumps(
            {
                "status": report["status"],
                "selected_frame": report["inputs"]["selected_frame_path"],
                "target_count": report["target_count"],
                "world_corner_fit_rmse_px": report["current_frame"][
                    "world_corner_fit_rmse_px"
                ],
                "observation_sha256": report["observation_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
