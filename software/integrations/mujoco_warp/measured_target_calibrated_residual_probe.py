"""Apply the frozen MW2UC calibrated-residual grid to measured catalog targets."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import nominal_target_uncertainty_probe as frozen


EXPECTED = {
    "target_catalog": "0fe3c013a30c42e5b0bb663571f6a5b2996e353b0130c1a6905cb34101b011d8",
    "virtual_profile": "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634",
    "mjcf": "448b711ae30ed3df8a5f5eff66ecb53034f6540eade7264388d86e3911a7a8a0",
    "frozen_mw2uc_probe": "5570a43c39c15e2c7edac2c4526430228f6a8921de5f9944cf475fb9eeaa3c63",
}
EXPECTED_POSE_BUNDLE_SHA256 = {
    "five": "0b4d3da8a8299387558b1373f8d5433d3d1063c2e1bff68ff32ec678c85f1665",
    "candidate51": "267534d7247b43732be15d54e4036738e179829ba0f4bf1ba8b3807b71f7861f",
}
FIVE_TARGET_IDS = ("BACKSLASH", "GRAVE", "LEFT_BRACKET", "RIGHT_BRACKET", "SHIFT")
TARGET_IDS = FIVE_TARGET_IDS
TARGET_COUNT = len(FIVE_TARGET_IDS)
JOINT_ORDER = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
)
WORLDS_PER_TARGET = frozen.WORLDS_PER_TARGET
SEED = frozen.SEED + 3
HALF_WIDTH_MM = 4.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_pose_bundle(
    workspace: Path, target_catalog: Path, target_scope: str = "five"
) -> dict[str, Any]:
    ai_dir = workspace / "software/ai"
    source_dir = workspace / "software/src"
    sys.path[:0] = [str(ai_dir), str(source_dir)]
    from rocell.application.robot_layout_overlay import promoted_rank1_robot_layout
    from rocell.application.static_simulation_context import (
        load_static_simulation_context,
    )
    from rocell.application.trajectory_simulation import (
        screen_scenario_route,
        validate_scene_park_xy,
    )
    from rocell.models import ActionPlan, Device, PressKey
    from rocell.motion import GeometricDryRunEngine, GeometricSimulationSettings
    from rocell.targets.nominal import load_nominal_target_catalog
    from rocell.typing.development_profiles import development_keyboard_profile
    from rocell_ai.model_motion_simulation import _simulation_profile

    profile_path = workspace / "software/config/virtual_commissioning_profile.json"
    if sha256(target_catalog) != EXPECTED["target_catalog"]:
        raise ValueError("measured target candidate SHA-256 mismatch")
    if sha256(profile_path) != EXPECTED["virtual_profile"]:
        raise ValueError("virtual profile SHA-256 mismatch")
    base_context = load_static_simulation_context(workspace)
    candidate = load_nominal_target_catalog(workspace, target_catalog)
    if len(candidate.keyboard_targets) != 51 or len(candidate.phone_targets) != 29:
        raise ValueError("measured target candidate coverage mismatch")
    if not set(FIVE_TARGET_IDS) <= set(candidate.keyboard_targets):
        raise ValueError("measured target candidate lacks extension targets")
    target_ids = (
        FIVE_TARGET_IDS
        if target_scope == "five"
        else tuple(candidate.keyboard_targets)
    )
    if target_scope not in EXPECTED_POSE_BUNDLE_SHA256:
        raise ValueError("unsupported measured target scope")
    if target_scope == "candidate51" and len(target_ids) != 51:
        raise ValueError("measured candidate keyboard target count changed")
    hardware_profile = _simulation_profile(base_context)
    context = replace(base_context, targets=candidate)
    scenario, layout = promoted_rank1_robot_layout(context, profile_path)
    path_policy = context.scenario.path_policy
    settings = GeometricSimulationSettings(
        clearance_above_highest_obstacle_mm=(
            path_policy.clearance_above_highest_obstacle_mm
        ),
        segment_clearance_mm=path_policy.segment_clearance_mm,
        hover_height_mm=path_policy.hover_height_mm,
        approach_height_mm=path_policy.approach_height_mm,
        contact_overtravel_mm=path_policy.contact_overtravel_mm,
        park_xy_board_mm=(290.0, 10.0),
    )
    validate_scene_park_xy(context.scene, settings.park_xy_board_mm)
    typing_profile = development_keyboard_profile()
    poses = []
    for target_id in target_ids:
        plan = ActionPlan.from_text(
            device=Device.KEYBOARD,
            profile_id=typing_profile.profile_id,
            text=f"mw2uc-{target_scope}-pose:{target_id}",
            actions=(PressKey(target_id),),
            required_calibrations=typing_profile.required_calibrations,
        )
        geometry = GeometricDryRunEngine(settings).run(
            plan,
            context.snapshot,
            hardware_profile,
            context.scene,
            candidate,
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
            raise ValueError(
                f"target does not have exactly one contact pose: {target_id}"
            )
        contact = contacts[0]
        joints = contact.get("solution_arm_joint_positions_rad", {})
        if tuple(joints) != JOINT_ORDER:
            raise ValueError(f"target joint identity/order changed: {target_id}")
        target = candidate.keyboard_targets[target_id]
        poses.append({
            "target_id": target_id,
            "center_board_mm": [target.center.x, target.center.y, target.center.z],
            "candidate_safe_half_extent_mm": [
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
        })
    result = {
        "schema": "rocell.mujoco_warp_measured_target_pose_bundle.v1",
        "status": (
            "PASS_EXPLORATORY_EXTENSION_POSE_SOURCE"
            if target_scope == "five"
            else "PASS_EXPLORATORY_CANDIDATE51_POSE_SOURCE"
        ),
        "scope": (
            "FIVE_TARGET_MEASURED_CANDIDATE_RANK1_SIMULATION_ONLY"
            if target_scope == "five"
            else "EXACT_51_KEY_MEASURED_CANDIDATE_RANK1_SIMULATION_ONLY"
        ),
        "target_scope": target_scope,
        "source_sha256": {
            "target_catalog": sha256(target_catalog),
            "virtual_profile": sha256(profile_path),
        },
        "base_catalog_sha256": base_context.targets.content_sha256,
        "layout_overlay": layout,
        "target_count": len(poses),
        "target_ids": list(target_ids),
        "joint_order": list(JOINT_ORDER),
        "poses": poses,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "external measured catalog candidate is not installed",
            "rank-1 placement and 120 mm tool remain unmeasured simulation inputs",
            "bracket and backslash X coordinates are topology inferences",
            "no physical safe region, footprint, collision qualification, or calibration",
        ],
    }
    result["receipt_sha256"] = hashlib.sha256(
        frozen.canonical_bytes(result)
    ).hexdigest()
    return result


def _validate_pose_bundle(
    bundle: dict[str, Any], target_scope: str = "five"
) -> tuple[str, ...]:
    target_ids = tuple(bundle.get("target_ids", []))
    expected_status = (
        "PASS_EXPLORATORY_EXTENSION_POSE_SOURCE"
        if target_scope == "five"
        else "PASS_EXPLORATORY_CANDIDATE51_POSE_SOURCE"
    )
    expected_scope = (
        "FIVE_TARGET_MEASURED_CANDIDATE_RANK1_SIMULATION_ONLY"
        if target_scope == "five"
        else "EXACT_51_KEY_MEASURED_CANDIDATE_RANK1_SIMULATION_ONLY"
    )
    if (
        bundle.get("schema") != "rocell.mujoco_warp_measured_target_pose_bundle.v1"
        or bundle.get("status") != expected_status
        or bundle.get("scope") != expected_scope
        or bundle.get("target_scope") != target_scope
        or bundle.get("target_count") != len(target_ids)
        or len(bundle.get("poses", [])) != len(target_ids)
        or (target_scope == "five" and target_ids != FIVE_TARGET_IDS)
        or (target_scope == "candidate51" and len(target_ids) != 51)
        or len(set(target_ids)) != len(target_ids)
    ):
        raise ValueError("unsupported measured-target pose bundle")
    unsigned = dict(bundle)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(frozen.canonical_bytes(unsigned)).hexdigest():
        raise ValueError("measured-target pose bundle canonical receipt mismatch")
    if [row.get("target_id") for row in bundle["poses"]] != list(target_ids):
        raise ValueError("measured-target pose identity/order changed")
    if bundle.get("source_sha256", {}).get("target_catalog") != EXPECTED["target_catalog"]:
        raise ValueError("measured-target pose catalog binding mismatch")
    if bundle.get("hardware_access") is not False or bundle.get("physical_authority") is not False:
        raise ValueError("measured-target pose bundle carries authority")
    if bundle.get("hardware_write_count") != 0 or bundle.get("physical_movement_count") != 0:
        raise ValueError("measured-target pose bundle records physical activity")
    return target_ids


def _score_cells(tips, centers, poses, np) -> dict[str, Any]:
    target_count = len(poses)
    extents = np.full((target_count, 2), HALF_WIDTH_MM, dtype=np.float64)
    _, margins, misses = frozen._score_absolute_target_rectangles(
        tips[:, :, :2], centers[:, :2], extents, np
    )
    targets = []
    for index, pose in enumerate(poses):
        miss_count = int(misses[index].sum())
        targets.append({
            "target_id": pose["target_id"],
            "miss_count": miss_count,
            "miss_rate_one_sided_95_wilson_upper": frozen._wilson_upper(
                miss_count, WORLDS_PER_TARGET
            ),
            "p01_margin_mm": float(np.quantile(margins[index], 0.01)),
            "minimum_margin_mm": float(margins[index].min()),
        })
    return {
        "effective_safe_half_width_mm": HALF_WIDTH_MM,
        "feasible": all(
            row["miss_rate_one_sided_95_wilson_upper"] <= frozen.MISS_UCB_LIMIT
            and row["p01_margin_mm"] >= 0.0
            for row in targets
        ),
        "total_misses": sum(row["miss_count"] for row in targets),
        "minimum_target_p01_margin_mm": min(row["p01_margin_mm"] for row in targets),
        "minimum_margin_mm": min(row["minimum_margin_mm"] for row in targets),
        "targets": targets,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "target_catalog": args.target_catalog,
        "virtual_profile": args.virtual_profile,
        "mjcf": args.mjcf,
        "frozen_mw2uc_probe": Path(frozen.__file__),
    }
    for name, expected in EXPECTED.items():
        actual = sha256(paths[name])
        if actual != expected:
            raise ValueError(f"{name} SHA-256 mismatch: {actual}")
    expected_pose_sha256 = EXPECTED_POSE_BUNDLE_SHA256[args.target_scope]
    if expected_pose_sha256 == "PENDING_GENERATION":
        raise ValueError("candidate51 pose bundle SHA-256 is not frozen")
    actual_pose_sha256 = sha256(args.pose_bundle)
    if actual_pose_sha256 != expected_pose_sha256:
        raise ValueError(f"pose_bundle SHA-256 mismatch: {actual_pose_sha256}")

    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    bundle = json.loads(args.pose_bundle.read_text(encoding="utf-8"))
    profile = json.loads(args.virtual_profile.read_text(encoding="utf-8"))
    target_ids = _validate_pose_bundle(bundle, args.target_scope)
    target_count = len(target_ids)
    if profile.get("status") != "UNMEASURED_SENSITIVITY_OVERLAY":
        raise ValueError("virtual profile is no longer an unmeasured overlay")
    poses = bundle["poses"]
    nominal_q = np.asarray([pose["joint_positions_rad"] + [0.0] for pose in poses])
    centers = np.asarray([pose["center_board_mm"] for pose in poses], dtype=np.float64)
    board_t_world = np.asarray(
        profile["study_input"]["derived_solver_transform"]["matrix_row_major"],
        dtype=np.float64,
    ).reshape(4, 4)
    tool_length_mm = float(
        profile["study_input"]["route_tool_lengths_mm"]["keyboard"]
    )

    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    data = mujoco.MjData(model)
    hand_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand_tcp")
    if hand_id < 0 or model.nq != 6:
        raise ValueError("MJCF joint/body contract changed")
    wp.init()
    wp.set_device(args.device)
    warp_model = mjw.put_model(model)
    total_worlds = target_count * WORLDS_PER_TARGET
    warp_data = mjw.put_data(model, data, nworld=total_worlds)

    rng = np.random.Generator(np.random.PCG64(SEED))
    fixed_signs = (
        rng.integers(0, 2, size=(target_count, 5), dtype=np.int8).astype(np.float64)
        * 2.0
        - 1.0
    )
    systematic_unit = rng.uniform(-1.0, 1.0, size=5)
    random_unit = rng.normal(
        0.0, 1.0, size=(target_count, WORLDS_PER_TARGET, 5)
    )
    scenarios = []
    for fixed_magnitude in frozen.CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD:
        fixed_offsets = fixed_signs * fixed_magnitude + systematic_unit * fixed_magnitude
        fixed_q = nominal_q.copy()
        fixed_q[:, :5] += fixed_offsets
        warp_data.qpos.assign(np.repeat(fixed_q, WORLDS_PER_TARGET, axis=0))
        mjw.forward(warp_model, warp_data)
        wp.synchronize_device(wp.get_device())
        fixed_tips = frozen._board_tips(
            warp_data, hand_id, board_t_world, tool_length_mm, np
        ).reshape(target_count, WORLDS_PER_TARGET, 3)[:, 0, :]
        fixed_cartesian_delta = fixed_tips - centers
        for noise_level in frozen.CALIBRATED_RANDOM_LEVELS_RAD:
            qpos = np.broadcast_to(
                fixed_q[:, None, :], (target_count, WORLDS_PER_TARGET, 6)
            ).copy()
            qpos[:, :, :5] += random_unit * noise_level
            warp_data.qpos.assign(qpos.reshape(total_worlds, 6))
            mjw.forward(warp_model, warp_data)
            wp.synchronize_device(wp.get_device())
            raw_tips = frozen._board_tips(
                warp_data, hand_id, board_t_world, tool_length_mm, np
            ).reshape(target_count, WORLDS_PER_TARGET, 3)
            for residual_fraction in frozen.CALIBRATED_RESIDUAL_FRACTIONS:
                corrected = frozen._apply_cartesian_calibration(
                    raw_tips, fixed_cartesian_delta, residual_fraction
                )
                scenarios.append({
                    "fixed_backlash_and_systematic_magnitude_rad_each": fixed_magnitude,
                    "random_joint_noise_sigma_rad": noise_level,
                    "per_key_calibration_residual_fraction": residual_fraction,
                    "safe_width_cell": _score_cells(corrected, centers, poses, np),
                })
    result = {
        "schema": "rocell.mujoco_warp_measured_target_calibrated_residual.v1",
        "status": (
            "PASS_EXPLORATORY_FROZEN_MW2UC_EXTENSION"
            if args.target_scope == "five"
            else "PASS_EXPLORATORY_EXACT_CANDIDATE51_MW2UC"
        ),
        "scope": (
            "FIVE_TARGET_FROZEN_CALIBRATED_RESIDUAL_APPLICATION_ONLY"
            if args.target_scope == "five"
            else "EXACT_51_KEY_MEASURED_CANDIDATE_FROZEN_MW2UC_ONLY"
        ),
        "source_sha256": {
            **EXPECTED,
            "pose_bundle": expected_pose_sha256,
        },
        "stack": frozen._stack(args.device),
        "device": args.device,
        "seed": SEED,
        "target_count": target_count,
        "target_ids": list(target_ids),
        "worlds_per_target_per_fk_scenario": WORLDS_PER_TARGET,
        "grids": {
            "effective_safe_half_width_mm": [HALF_WIDTH_MM],
            "random_joint_noise_sigma_rad": frozen.CALIBRATED_RANDOM_LEVELS_RAD,
            "fixed_backlash_and_systematic_magnitude_rad_each": (
                frozen.CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD
            ),
            "per_key_calibration_residual_fraction": (
                frozen.CALIBRATED_RESIDUAL_FRACTIONS
            ),
        },
        "scenarios": scenarios,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physics_step_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "applies the frozen MW2UC grid without reopening thresholds",
            "fixed approach signs and source magnitudes remain synthetic",
            "per-key Cartesian correction is a local equivalent, not corrected IK",
            "4 mm is a sensitivity width, not a measured physical safe region",
            "external catalog candidate, placement, tool, and footprint are uncommissioned",
            "no collision, dynamics, contact, servo, camera, or physical qualification",
        ],
    }
    result["receipt_sha256"] = hashlib.sha256(frozen.canonical_bytes(result)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("pose", "residual"), required=True)
    parser.add_argument(
        "--target-scope", choices=("five", "candidate51"), default="five"
    )
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--pose-bundle", type=Path)
    parser.add_argument("--target-catalog", type=Path, required=True)
    parser.add_argument("--virtual-profile", type=Path)
    parser.add_argument("--mjcf", type=Path)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "pose":
        if args.workspace is None or any(
            value is not None
            for value in (args.pose_bundle, args.virtual_profile, args.mjcf, args.device)
        ):
            parser.error("pose mode requires only --workspace, --target-catalog, --output")
        result = build_pose_bundle(
            args.workspace.resolve(strict=True),
            args.target_catalog.resolve(strict=True),
            args.target_scope,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "status": result["status"],
            "target_count": result["target_count"],
        }, sort_keys=True))
        return 0
    if any(
        value is None
        for value in (args.pose_bundle, args.virtual_profile, args.mjcf, args.device)
    ) or args.workspace is not None:
        parser.error(
            "residual mode requires --pose-bundle, --target-catalog, "
            "--virtual-profile, --mjcf, --device, --output"
        )
    result = run(args)
    print(json.dumps({
        "status": result["status"],
        "scenario_count": len(result["scenarios"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
