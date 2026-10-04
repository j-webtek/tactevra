"""Retain one admitted rank-1 contact pose for every current keyboard target."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


EXPECTED = {
    "target_catalog": "6779213e832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2",
    "virtual_profile": "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634",
    "prior_coverage": "a4528e510eb5e8af515905733c5433a859e6e17731e18664c6c63ae62741dabf",
}
TARGET_COUNT = 46
JOINT_ORDER = [
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build(workspace: Path) -> dict:
    ai_dir = workspace / "software/ai"
    source_dir = workspace / "software/src"
    sys.path[:0] = [str(ai_dir), str(source_dir)]
    from rocell.application.robot_layout_overlay import promoted_rank1_robot_layout
    from rocell.application.static_simulation_context import (
        load_static_simulation_context,
        revalidate_static_simulation_context,
    )
    from rocell.application.trajectory_simulation import (
        screen_scenario_route,
        validate_scene_park_xy,
    )
    from rocell.models import ActionPlan, Device, PressKey
    from rocell.motion import GeometricDryRunEngine, GeometricSimulationSettings
    from rocell.typing.static_development_profiles import (
        static_development_keyboard_profile,
    )
    from rocell_ai.model_motion_simulation import _simulation_profile

    paths = {
        "target_catalog": workspace / "software/config/nominal_target_profiles.json",
        "virtual_profile": workspace / "software/config/virtual_commissioning_profile.json",
        "prior_coverage": workspace / "software/ai/eval/keyboard_route_coverage_v0.json",
    }
    for name, path in paths.items():
        if sha256(path) != EXPECTED[name]:
            raise ValueError(f"{name} SHA-256 mismatch")
    prior = json.loads(paths["prior_coverage"].read_text(encoding="utf-8"))
    if (
        prior.get("schema") != "rocell.ai_keyboard_route_coverage.v0"
        or prior.get("target_count") != TARGET_COUNT
        or prior.get("passing_count") != TARGET_COUNT
        or prior.get("blocked_count") != 0
        or prior.get("hardware_writes") != 0
        or prior.get("physical_execution_authorized") is not False
    ):
        raise ValueError("prior route coverage is not the exact zero-authority 46-target pass")

    context = load_static_simulation_context(workspace)
    scenario, layout = promoted_rank1_robot_layout(context, paths["virtual_profile"])
    target_ids = sorted(context.targets.keyboard_targets)
    if len(target_ids) != TARGET_COUNT or target_ids != prior["passing_targets"]:
        raise ValueError("current keyboard target identity differs from prior coverage")
    path_policy = context.scenario.path_policy
    settings = GeometricSimulationSettings(
        clearance_above_highest_obstacle_mm=path_policy.clearance_above_highest_obstacle_mm,
        segment_clearance_mm=path_policy.segment_clearance_mm,
        hover_height_mm=path_policy.hover_height_mm,
        approach_height_mm=path_policy.approach_height_mm,
        contact_overtravel_mm=path_policy.contact_overtravel_mm,
        park_xy_board_mm=(290.0, 10.0),
    )
    validate_scene_park_xy(context.scene, settings.park_xy_board_mm)
    hardware_profile = _simulation_profile(context)
    typing_profile = static_development_keyboard_profile()
    poses = []
    for target_id in target_ids:
        plan = ActionPlan.from_text(
            device=Device.KEYBOARD,
            profile_id=typing_profile.profile_id,
            text=f"mw2u-pose-source:{target_id}",
            actions=(PressKey(target_id),),
            required_calibrations=typing_profile.required_calibrations,
        )
        geometry = GeometricDryRunEngine(settings).run(
            plan,
            context.snapshot,
            hardware_profile,
            context.scene,
            context.targets,
        )
        route = screen_scenario_route(scenario, plan, geometry)
        round_ = route.get("round") or {}
        if route.get("all_waypoints_accepted") is not True:
            raise ValueError(f"target route did not pass: {target_id}")
        contacts = [
            row
            for row in round_.get("joint_results", [])
            if row.get("phase") == "CONTACT"
            and row.get("semantic_target") == f"keyboard:{target_id}"
        ]
        if len(contacts) != 1:
            raise ValueError(f"target does not have exactly one contact pose: {target_id}")
        contact = contacts[0]
        joints = contact.get("solution_arm_joint_positions_rad", {})
        if list(joints) != JOINT_ORDER:
            raise ValueError(f"target joint identity/order changed: {target_id}")
        target = context.targets.keyboard_targets[target_id]
        poses.append(
            {
                "target_id": target_id,
                "center_board_mm": [target.center.x, target.center.y, target.center.z],
                "nominal_keycap_half_extent_mm": [
                    target.half_extent_x_mm,
                    target.half_extent_y_mm,
                ],
                "contact_target_board_mm": contact["solver_weighted_task_jacobian"][
                    "target_tip_position_board_mm"
                ],
                "achieved_tip_board_mm": contact["achieved_tip_position_board_mm"],
                "joint_positions_rad": [joints[name] for name in JOINT_ORDER],
                "ik_position_error_mm": contact["position_error_mm"],
                "solver_weighted_jacobian_condition_number": contact[
                    "solver_weighted_task_jacobian"
                ]["condition_number"],
                "minimum_arm_joint_margin_rad": contact["minimum_arm_joint_margin_rad"],
                "route_evaluated_waypoint_count": round_["evaluated_waypoint_count"],
            }
        )
    revalidate_static_simulation_context(context)
    result = {
        "schema": "rocell.mujoco_warp_nominal_target_pose_bundle.v1",
        "status": "PASS_EXPLORATORY_POSE_SOURCE",
        "scope": "SYNTHETIC_UNMEASURED_RANK1_KEYBOARD_CONTACTS_ONLY",
        "source_sha256": dict(EXPECTED),
        "static_target_catalog_sha256": context.targets.content_sha256,
        "layout_overlay": layout,
        "target_count": len(poses),
        "joint_order": JOINT_ORDER,
        "poses": poses,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "46-target catalog and rank-1 placement/tool are nominal unmeasured simulation inputs",
            "contact poses come from independent park-to-target-to-park route screens",
            "no physical safe region, tool footprint, collision qualification, or installed calibration",
        ],
    }
    result["receipt_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.workspace.resolve(strict=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "target_count": result["target_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
