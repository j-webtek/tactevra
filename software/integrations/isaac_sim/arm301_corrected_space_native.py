"""Execute the retained ARM-301 SPACE plan once with native key mechanics."""

import argparse
from pathlib import Path

from representative_key_mechanics import COMPENSATED_SPACE_DIRECTORY, run_drive_controlled_robot_h_replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--compensated", action="store_true", help="use the screened 470-tick drive targets")
    args = parser.parse_args()
    root = Path("C:/IsaacSim/artifacts/issue190")
    config = Path(__file__).resolve().parents[2] / "config"
    directory = root / "arm301-corrected-space-native-attempt-001"
    candidate = None
    if args.compensated:
        candidate = root / "arm301-space-compensated-schedule-001/candidate.json"
        directory = root / COMPENSATED_SPACE_DIRECTORY
    result = run_drive_controlled_robot_h_replay(
        replay_plan_path=root / "arm301-corrected-space-native-plan-001/plan.json",
        corrected_space_authorization=args.authorization,
        compensated_space_candidate=candidate,
        layout_path=config / "nominal_target_profiles.json",
        drive_profile_path=config / "isaac_lm0b_geometry_prior_profile.json",
        robot_usd_path=root / "wp1-import-003/roarm_m3_kinematic_40dbd84/roarm_m3_kinematic_40dbd84.usda",
        output_path=directory / "receipt.json",
        status_path=directory / "status.json",
    )
    print(result["status"])
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
