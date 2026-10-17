"""Compare the retained register pose with the passing current H route."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


AI_DIR = Path(__file__).resolve().parent
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.current_start_route_sensitivity import run  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--simulation-workspace", type=Path, required=True)
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("software/config/virtual_commissioning_profile.json"),
    )
    args = parser.parse_args()
    workspace = args.simulation_workspace.resolve(strict=True)
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    result = run(intake, workspace=workspace, profile_path=workspace / args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(result["status"])
    print(
        "first_max_delta_rad",
        result["first_route_transition"]["maximum_absolute_joint_delta_rad"],
    )
    print(
        "route_step_limit_rad",
        result["first_route_transition"]["maximum_joint_step_rad"],
    )
